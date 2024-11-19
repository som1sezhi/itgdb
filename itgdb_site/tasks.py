import os
import shutil
import zipfile
import uuid
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
import simfile
from simfile.dir import SimfilePack
from celery import shared_task
from celery.signals import task_postrun
from celery.utils.log import get_task_logger
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import patoolib

from .utils.uploads import upload_pack, ProgressTrackingInfo
from .utils.url_fetch import fetch_from_url
from .utils.analysis import SongAnalyzer
from .models import Song, Chart

logger = get_task_logger(__name__)
channel_layer = get_channel_layer()

# Routines and classes for keeping track of progress: ================

def _send_progress_update(task_id, state, progress, message):
    async_to_sync(channel_layer.group_send)(task_id, {
        'type': 'progress.update',
        'data': {
            'id': task_id,
            'state': state,
            'progress': progress,
            'message': message
        }
    })


@task_postrun.connect
def task_postrun_handler(**kwargs):
    state = kwargs['state']
    retval = kwargs['retval']
    if state == 'SUCCESS':
        message = f'Success! {retval}'
    elif state == 'FAILURE':
        message = f'Failure: {retval}'
    else:
        message = f'{state}: {retval}'
    _send_progress_update(kwargs['task_id'], state, 1, message)


class ProgressTracker:
    def __init__(self, task):
        self.task = task
    
    def update_progress(self, progress, message=''):
        self.task.update_state(
            state='PROGRESS',
            meta={
                'progress': progress,
                'message': message
            }
        )
        _send_progress_update(self.task.request.id, 'PROGRESS', progress, message)


# Tasks and task helper functions: ===================================

def _open_pack_if_exists(dir_path):
    simfile_pack = SimfilePack(dir_path)
    # check if this directory is actually a pack directory by checking
    # if simfiles are present
    if next(simfile_pack.simfile_dirs(), None) is None:
        return None
    return simfile_pack


def _find_packs(pack_names, extracted_path):

    found_packs = {}
    # get all candidate pack directories
    for name in os.listdir(extracted_path):
        subdir_path = os.path.join(extracted_path, name)
        if os.path.isdir(subdir_path):
            pack = _open_pack_if_exists(subdir_path)
            if pack:
                found_packs[name.lower()] = pack

    # if we haven't found a pack yet, we can try interpreting the
    # extraction destination directory as a pack (if only 1 pack is requested)
    if not found_packs and len(pack_names) == 1:
        pack = _open_pack_if_exists(extracted_path)
        if pack:
            return [pack]
    
    # give an error if we didn't find enough packs
    if len(found_packs) < len(pack_names):
        raise RuntimeError(
            f'requested {len(pack_names)} packs '
            f'but only {len(found_packs)} were found'
        )

    # if only 1 pack is found, just use that one if only 1 pack is requested
    if len(found_packs) == 1 and len(pack_names) == 1:
        return [pack for pack in found_packs.values()]
    
    # otherwise, match packs with pack names by their directory name
    packs_to_return = []
    for pack_name in pack_names:
        name_lower = pack_name.lower()
        if name_lower in found_packs:
            packs_to_return.append(found_packs[name_lower])
        else:
            raise RuntimeError(
                f'could not find pack with name {pack_name} '
                f'(found names: {list(found_packs.keys())})'
            )
    
    return packs_to_return


def _extract_pack(file_path):
    # TODO: likely susceptible to malicious zips (zip bombs, etc.)
    try:
        filename = os.path.basename(file_path)
        extract_dir = filename.rsplit('.', 1)[0]
        extract_path = os.path.join(settings.MEDIA_ROOT, 'extracted', extract_dir)
        patoolib.extract_archive(
            file_path, verbosity=-1, outdir=extract_path, interactive=False
        )
    except Exception as e:
        # cleanup in case the extraction was partially complete before
        # being interrupted
        if os.path.exists(extract_path) and os.path.isdir(extract_path):
            shutil.rmtree(extract_path)
        raise e
    finally:
        os.remove(file_path)
    return extract_path


@shared_task(bind=True)
def process_pack_upload(self, pack_data, filename):
    # TODO: error handling

    prog_tracker = ProgressTracker(self)

    prog_tracker.update_progress(0, f'Extracting {filename}')
    file_path = default_storage.path(filename)
    extract_path = _extract_pack(file_path)

    try:
        # TODO: we assume that the zip contains only a pack directory, with all
        # the song folders inside. is this a good assumption?
        pack_name = next(os.walk(extract_path))[1][0]
        pack_path = os.path.join(extract_path, pack_name)
        # TODO: handle uploaded image/sim files better on rollback
        # https://github.com/un1t/django-cleanup/issues/43
        with transaction.atomic():
            simfile_pack = SimfilePack(pack_path)
            upload_pack(
                simfile_pack, pack_data,
                ProgressTrackingInfo(prog_tracker, 0, 1)
            )
    finally:
        shutil.rmtree(extract_path)


@shared_task(bind=True)
def process_pack_from_web(self, pack_data_list, source_link):
    prog_tracker = ProgressTracker(self)

    prog_tracker.update_progress(0, f'Downloading {source_link}')
    file_path = fetch_from_url(source_link)

    filename = os.path.basename(file_path)
    prog_tracker.update_progress(0, f'Extracting {filename}')
    extract_path = _extract_pack(file_path)

    try:
        pack_names = [data['name'] for data in pack_data_list]
        try:
            packs = _find_packs(pack_names, extract_path)
        except RuntimeError as e:
            # sometimes, unar will create an additional directory within
            # the extraction destination and extract all the files into there.
            # check that directory first
            contents = os.listdir(extract_path)
            if len(contents) == 1 and os.path.isdir(
                new_extract_path := os.path.join(extract_path, contents[0])
            ):
                packs = _find_packs(pack_names, new_extract_path)
            else:
                raise e

        with transaction.atomic():
            num_packs = len(pack_data_list)
            for i, (pack, pack_data) in enumerate(zip(packs, pack_data_list)):
                upload_pack(
                    pack, pack_data,
                    ProgressTrackingInfo(prog_tracker, i, num_packs)
                )
    finally:
        shutil.rmtree(extract_path)


# this task is pretty messy...
# it's basically an ad-hoc way of collectng/updating data for every song/chart
# in the db whenever i make changes to how charts are analyzed
@shared_task(bind=True)
def update_analyses(self, form_data):
    to_update = set(form_data['which'])
    prog_tracker = ProgressTracker(self)
    song_count = Song.objects.count()

    # if no fields are specified, update nothing
    if not to_update:
        return
    
    ret = []
    
    # figure out whether we need to access Chart model instances
    need_chart_obj = bool({'stream_info', 'counts'} & to_update)

    for i, song in enumerate(Song.objects.all()):
        prog_tracker.update_progress(
            i / song_count, f'[{i + 1}/{song_count}] Updating {str(song)}'
        )

        file = song.simfile
        ext = file.name.rsplit('.', 1)[1]
        tmp_path = os.path.join(settings.MEDIA_ROOT, f'{uuid.uuid4()}.{ext}')
        try:
            # copy simfile contents to a temp file on disk so that we can
            # use simfile.open() with its encoding autodetection
            with file.open(mode='rb') as f, open(tmp_path, 'wb') as tmp:
                shutil.copyfileobj(f, tmp)

            sim = simfile.open(tmp_path, strict=False)
            song_analyzer = SongAnalyzer(sim)

            if 'chart_length' in to_update:
                chart_len = song_analyzer.get_chart_len()
                song.chart_length = chart_len
                song.save()

            for chart in sim.charts:
                if 'unusual_diff_check' in to_update:
                    diff = (chart.difficulty or '').lower().strip()
                    usual_diffs = Chart.DIFFICULTY_CHOICES.values()
                    if diff not in usual_diffs:
                        ret.append([
                            song.id,
                            song.pack.name if song.pack else '',
                            song.title,
                            diff
                        ])

                if not need_chart_obj:
                    continue

                try:
                    chart_obj = song.chart_set.get(
                        steps_type=Chart.steps_type_to_int(
                            chart.stepstype
                        ),
                        difficulty=Chart.difficulty_str_to_int(
                            chart.difficulty
                        ),
                        description=(chart.description or '').strip()
                    )
                except Chart.DoesNotExist:
                    continue

                chart_analyzer = \
                    song_analyzer.get_chart_analyzer(chart)

                if 'stream_info' in to_update:
                    stream_info = chart_analyzer.get_stream_info()
                    chart_obj.analysis['stream_info'] = stream_info
                
                if 'counts' in to_update:
                    counts = chart_analyzer.get_counts()
                    for k, v in counts.items():
                        setattr(chart_obj, k + '_count', v)
                
                chart_obj.save()
                        
        except FileNotFoundError:
            continue
        finally:
            # cleanup temp file
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
    
    return ret
            