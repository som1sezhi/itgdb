"""Routines for uploading packs/songs/charts to the database.
"""

import os
import magic
import uuid
from collections import namedtuple
import re
import fnmatch
from django.core.files import File
from simfile.dir import SimfilePack, SimfileDirectory
from simfile.timing.displaybpm import displaybpm, BeatValues
from simfile.types import Simfile, Chart as SimfileChart
from celery.utils.log import get_task_logger
import cv2
from PIL import Image

from ..models import Pack, Song, Chart, ImageFile
from .charts import (
    get_hash, get_assets, get_pack_banner_path, get_song_lengths
)
from .analysis import SongAnalyzer, get_chart_key

logger = get_task_logger('itgdb_site.tasks')


ProgressTrackingInfo = namedtuple(
    'ProgressTrackingTask',
    ['progress_tracker', 'finished_subparts', 'num_subparts']
)


def _determine_has_alpha(file):
    with Image.open(file) as img:
        mode = img.mode
    return mode in {'RGBA', 'LA', 'PA', 'RGBa', 'La'}


def _get_image(path, parent_obj, cache, generate_thumbnail=False):
    if not path or not os.path.isfile(path):
        return None
    if path in cache:
        return cache[path]
    
    mimetype = magic.from_file(path, mime=True)
    img_path = None
    if mimetype.startswith('image'):
        img_path = path 
    elif mimetype.startswith('video'):
        # get first frame of video
        video_capture = cv2.VideoCapture(path)
        success, img = video_capture.read()
        if success:
            img_path = path + '.png'
            cv2.imwrite(img_path, img)
        video_capture.release()

    if img_path:
        with open(img_path, 'rb') as f:
            has_alpha = _determine_has_alpha(f)
            base_filename = os.path.basename(img_path)
            if isinstance(parent_obj, Pack):
                img_file = ImageFile(
                    pack = parent_obj,
                    image = File(f, name=f'{uuid.uuid4()}_{base_filename}'),
                    has_alpha = has_alpha
                )
            else: # parent_obj is a Song
                img_file = ImageFile(
                    song = parent_obj,
                    image = File(f, name=f'{uuid.uuid4()}_{base_filename}'),
                    has_alpha = has_alpha
                )
            img_file.save()
            if generate_thumbnail:
                # pregenerate thumbnail
                img_file.get_thumbnail()
            cache[path] = img_file
            return img_file
    
    return None


# match the behavior of NotesLoader::GetMainAndSubTitlesFromFullTitle()
def _get_title_and_subtitles_from_full_title(full_title: str):
    for sep in ('\t', ' -', ' ~', ' (', ' ['):
        i = full_title.find(sep)
        if i >= 0:
            return full_title[:i], full_title[i + 1:]
    return full_title, ''


SIMFILE_FILENAME_PATTERNS = (
    re.compile(fnmatch.translate('*.sm'), re.IGNORECASE),
    re.compile(fnmatch.translate('*.ssc'), re.IGNORECASE)
)
def delete_dupe_sims(simfile_pack: SimfilePack):
    for song_dir_path in simfile_pack.simfile_dir_paths:
        all_fnames = os.listdir(song_dir_path)
        for pattern in SIMFILE_FILENAME_PATTERNS:
            fnames = list(filter(lambda f: pattern.match(f), all_fnames))
            fnames.sort(key=str.lower)
            # keep the first file alphabetically, delete the rest
            for fname in fnames[1:]:
                path = os.path.join(song_dir_path, fname)
                os.remove(path)


def upload_pack(
    simfile_pack: SimfilePack,
    pack_data: dict,
    prog_tracking_info: ProgressTrackingInfo | None = None
):
    pack_path = simfile_pack.pack_dir
    image_cache = {}
    delete_dupe_sims(simfile_pack) # kind of redundant but i think it's fine

    p = Pack(
        name = pack_data['name'] or simfile_pack.name,
        author = pack_data['author'],
        release_date = pack_data['release_date'],
        release_date_year_only = pack_data['release_date_year_only'],
        category_id = pack_data['category'],
        links = pack_data['links']
    )
    p.save()
    p.tags.add(*pack_data['tags'])
    pack_bn_path = get_pack_banner_path(pack_path, simfile_pack)
    p.banner = _get_image(pack_bn_path, p, image_cache, True)
    p.save()

    simfile_dirs = list(simfile_pack.simfile_dirs())
    total_count = len(simfile_dirs)
    for i, simfile_dir in enumerate(simfile_dirs):
        # update progress bar, if needed
        if prog_tracking_info:
            prog_tracker, finished_subparts, num_subparts = prog_tracking_info
            basename = os.path.basename(simfile_dir.simfile_dir)
            prog_tracker.update_progress(
                (finished_subparts + (i / total_count)) / num_subparts,
                f'[{i + 1}/{total_count}] Processing {p.name}/{basename}'
            )
        upload_song(simfile_dir, p, image_cache)


def upload_song(
    simfile_dir: SimfileDirectory,
    p: Pack | None = None,
    image_cache: dict | None = None
):
    if image_cache is None:
        image_cache = {}

    sim = simfile_dir.open(strict=False)
    assets = get_assets(simfile_dir)
    sim_path = simfile_dir.simfile_path
    sim_filename = os.path.basename(sim_path)

    logger.info(f'Processing {p.name if p else "<single>"}/{sim.title}')

    song_analyzer = SongAnalyzer(sim)

    music_path = assets['MUSIC']
    if not music_path:
        return
    song_lengths = get_song_lengths(music_path, song_analyzer)
    if not song_lengths:
        return
    music_len, chart_len = song_lengths

    # bit of a hack: temporarily filter out 0 bpm segments to match the 
    # behavior of stepmania
    old_bpms = sim.bpms
    if old_bpms is not None:
        sim.bpms = str(BeatValues(
            bpm for bpm in BeatValues.from_str(old_bpms) if bpm.value != 0
        ))
    bpm = displaybpm(sim, ignore_specified=True)
    disp = displaybpm(sim)
    bpm_range = (bpm.min, bpm.max)
    disp_range = (disp.min, disp.max)
    sim.bpms = old_bpms # restore

    sim_uuid = uuid.uuid4()

    # matching the behavior of TidyUpData() in Song.cpp
    title = (sim.title or '').strip()
    subtitle = (sim.subtitle or '').strip()
    artist = (sim.artist or '').strip()
    if not title:
        # if title is empty, stepmania pulls from the directory name instead
        basename = os.path.basename(simfile_dir.simfile_dir)
        title, subtitle = _get_title_and_subtitles_from_full_title(basename)

    with open(sim_path, 'rb') as f:
        s = Song(
            pack = p,
            title = title,
            subtitle = subtitle,
            artist = artist,
            title_translit = sim.titletranslit or '',
            subtitle_translit = sim.subtitletranslit or '',
            artist_translit = sim.artisttranslit or '',
            credit = (sim.credit or '').strip(),
            min_bpm = bpm_range[0],
            max_bpm = bpm_range[1],
            min_display_bpm = disp_range[0],
            max_display_bpm = disp_range[1],
            music_length = music_len,
            chart_length = chart_len,
            release_date = p.release_date if p else None,
            release_date_year_only = p.release_date_year_only,
            simfile = File(f, name=f'{sim_uuid}_{sim_filename}'),
            has_bgchanges = bool((sim.bgchanges or '').strip()),
            has_fgchanges = bool((sim.fgchanges or '').strip()),
            has_attacks = bool((sim.attacks or '').strip()),
            has_sm = bool(simfile_dir.sm_path),
            has_ssc = bool(simfile_dir.ssc_path),
        )
        s.save()
        img_parent = p or s
        s.banner = _get_image(assets['BANNER'], img_parent, image_cache, True)
        s.bg = _get_image(assets['BACKGROUND'], img_parent, image_cache, True)
        s.cdtitle = _get_image(assets['CDTITLE'], img_parent, image_cache)
        s.jacket = _get_image(assets['JACKET'], img_parent, image_cache)
        s.save()

    # upload the charts for this song.
    # try not to upload multiple charts for the same stepstype and difficulty
    # slot (unless it is an edit chart, then we also consider description)
    # TODO: see if description is necessary or sufficient to distinguish
    # between edit charts?
    chart_keys_already_uploaded = set()
    for chart in sim.charts:
        chart_key = get_chart_key(chart)
        if chart_key not in chart_keys_already_uploaded:
            upload_chart(chart, s, song_analyzer)
            chart_keys_already_uploaded.add(chart_key)


def upload_chart(chart: SimfileChart, s: Song, song_analyzer: SongAnalyzer):
    steps_type = Chart.steps_type_to_int(chart.stepstype)
    if steps_type is None:
        # ignore charts with unsupported stepstype
        return
    difficulty = Chart.difficulty_str_to_int(chart.difficulty)
    if difficulty is None:
        # TODO: investigate what the best way to handle this
        # should be (for now, raise an error so we can know about it).
        # NOTE: ITGmania + Simply Love seems to like putting 
        # charts with invalid difficulty in the Novice slot.
        raise ValueError(f'"{chart.difficulty}" is not a valid difficulty')
    try:
        meter = int(chart.meter)
    except ValueError:
        # apparently it's possible for the meter to not be a
        # number -- use -1 as a placeholder/fallback
        meter = -1
    
    chart_hash = get_hash(song_analyzer.sim, chart)

    analyzer = song_analyzer.get_chart_analyzer(chart)
    counts = analyzer.get_counts()
    counts = {k + '_count': v for k, v in counts.items()}
    analysis = {
        'density_graph': analyzer.get_density_graph(),
        'stream_info': analyzer.get_stream_info(),
    }
    
    # stepmania trims whitespace from description and chartname,
    # but not credit. thanks stepmania
    s.chart_set.create(
        steps_type = steps_type,
        difficulty = difficulty,
        meter = meter,
        credit = chart.get('CREDIT') or '',
        description = (chart.description or '').strip(),
        chart_name = (chart.get('CHARTNAME') or '').strip(),
        chart_hash = chart_hash,
        analysis = analysis,
        release_date = s.release_date,
        release_date_year_only = s.release_date_year_only,
        has_attacks = bool((chart.get('ATTACKS') or '').strip()),
        **counts
    )