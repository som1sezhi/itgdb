import os
import shutil
import zipfile
import csv
import time
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from simfile.dir import SimfilePack
from celery import shared_task
from celery.signals import task_postrun
from celery.utils.log import get_task_logger
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import patoolib

from .utils.uploads import upload_pack, ProgressTrackingInfo
from .utils.url_fetch import fetch_from_url

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


@shared_task(bind=True)
def process_pack_upload(self, pack_data, filename):
    # TODO: error handling

    prog_tracker = ProgressTracker(self)

    prog_tracker.update_progress(0, f'Extracting {filename}')
    file = default_storage.open(filename)
    extract_dir = os.path.basename(filename).rsplit('.')[0]
    extract_path = os.path.join(settings.MEDIA_ROOT, 'extracted', extract_dir)
    # TODO: support for other archive types, maybe
    # TODO: likely susceptible to malicious zips (zip bombs, etc.)
    with zipfile.ZipFile(file) as z:
        z.extractall(extract_path)
    default_storage.delete(filename)

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

    try:
        filename = os.path.basename(file_path)
        prog_tracker.update_progress(0, f'Extracting {filename}')
        extract_dir = filename.rsplit('.', 1)[0]
        extract_path = os.path.join(settings.MEDIA_ROOT, 'extracted', extract_dir)
        patoolib.extract_archive(
            file_path, verbosity=-1, outdir=extract_path, interactive=False
        )
    finally:
        os.remove(file_path)

    try:
        pack_names = [data['name'] for data in pack_data_list]
        packs = _find_packs(pack_names, extract_path)

        with transaction.atomic():
            num_packs = len(pack_data_list)
            for i, (pack, pack_data) in enumerate(zip(packs, pack_data_list)):
                upload_pack(
                    pack, pack_data,
                    ProgressTrackingInfo(prog_tracker, i, num_packs)
                )
    finally:
        shutil.rmtree(extract_path)



@shared_task(bind=True)
def test_task(self, sleep_time):
    prog_tracker = ProgressTracker(self)
    for i in range(sleep_time):
        time.sleep(1)
        prog_tracker.update_progress(
            (i + 1) / sleep_time,
            f'sleeping for {i+1}/{sleep_time} seconds'
        )
        if i == 5 and sleep_time == 13:
            raise ValueError('hello')
    return sleep_time + 1