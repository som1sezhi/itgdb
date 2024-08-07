"""Routines for uploading packs/songs/charts to the database.
"""

import os
import mimetypes
import uuid
from collections import namedtuple
from django.core.files import File
from django.utils import timezone
from simfile.dir import SimfilePack, SimfileDirectory
from simfile.timing.displaybpm import displaybpm
from simfile.types import Simfile, Chart as SimfileChart
from celery.utils.log import get_task_logger
import cv2
from sorl.thumbnail import get_thumbnail

from ..models import Pack, Song, Chart, ImageFile
from .charts import (
    get_hash, get_counts, get_density_graph, get_assets, get_pack_banner_path,
    get_song_lengths
)

logger = get_task_logger('itgdb_site.tasks')


ProgressTrackingInfo = namedtuple(
    'ProgressTrackingTask',
    ['progress_tracker', 'finished_subparts', 'num_subparts']
)


def _get_image(path, pack, cache, generate_thumbnail=False):
    if not path or not os.path.isfile(path):
        return None
    if path in cache:
        return cache[path]
    
    mimetype = mimetypes.guess_type(path)[0]
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
            base_filename = os.path.basename(img_path)
            img_file = ImageFile(
                pack = pack,
                image = File(f, name=f'{uuid.uuid4()}_{base_filename}')
            )
            img_file.save()
            if generate_thumbnail:
                # pregenerate thumbnail
                # NOTE: geometry string here is for banner thumbnails
                get_thumbnail(img_file.image, 'x50')
            cache[path] = img_file
            return img_file
    
    return None


def upload_pack(
    simfile_pack: SimfilePack,
    pack_data: dict,
    prog_tracking_info: ProgressTrackingInfo | None = None
):
    pack_path = simfile_pack.pack_dir
    image_cache = {}

    p = Pack(
        name = pack_data['name'] or simfile_pack.name,
        author = pack_data['author'],
        release_date = pack_data['release_date'],
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


def upload_song(simfile_dir: SimfileDirectory, p: Pack, image_cache: dict):
    sim = simfile_dir.open()
    assets = get_assets(simfile_dir)
    sim_path = simfile_dir.simfile_path
    sim_filename = os.path.basename(sim_path)

    logger.info(f'Processing {p.name}/{sim.title}')

    music_path = assets['MUSIC']
    if not music_path:
        return
    song_lengths = get_song_lengths(music_path, sim)
    if not song_lengths:
        return
    music_len, chart_len = song_lengths

    bpm = displaybpm(sim, ignore_specified=True)
    disp = displaybpm(sim)
    bpm_range = (bpm.min, bpm.max)
    disp_range = (disp.min, disp.max)

    sim_uuid = uuid.uuid4()

    with open(sim_path, 'rb') as f:
        s = p.song_set.create(
            title = sim.title,
            subtitle = sim.subtitle,
            artist = sim.artist,
            title_translit = sim.titletranslit,
            subtitle_translit = sim.subtitletranslit,
            artist_translit = sim.artisttranslit,
            credit = sim.credit,
            min_bpm = bpm_range[0],
            max_bpm = bpm_range[1],
            min_display_bpm = disp_range[0],
            max_display_bpm = disp_range[1],
            length = music_len,
            release_date = p.release_date,
            simfile = File(f, name=f'{sim_uuid}_{sim_filename}'),
            banner = _get_image(assets['BANNER'], p, image_cache, True),
            bg = _get_image(assets['BACKGROUND'], p, image_cache, True),
            cdtitle = _get_image(assets['CDTITLE'], p, image_cache),
            jacket = _get_image(assets['JACKET'], p, image_cache),
            has_bgchanges = bool((sim.bgchanges or '').strip()),
            has_fgchanges = bool((sim.fgchanges or '').strip()),
            has_attacks = bool((sim.attacks or '').strip())
        )

    for chart in sim.charts:
        upload_chart(chart, s, sim, chart_len)


def upload_chart(chart: SimfileChart, s: Song, sim: Simfile, chart_len: float):
    steps_type = Chart.steps_type_to_int(chart.stepstype)
    if steps_type is None:
        # ignore charts with unsupported stepstype
        return
    difficulty = Chart.difficulty_str_to_int(chart.difficulty)
    if difficulty is None:
        # TODO: investigate what the best way to handle this
        # should be (for now, just put it as an edit; i hope
        # this is rare enough where this shouldn't be too much
        # of an issue).
        # NOTE: ITGmania + Simply Love seems to like putting 
        # charts with invalid difficulty in the Novice slot.
        difficulty = 5
    try:
        meter = int(chart.meter)
    except ValueError:
        # apparently it's possible for the meter to not be a
        # number -- use -1 as a placeholder/fallback
        meter = -1
    chart_hash = get_hash(sim, chart)
    counts = get_counts(sim, chart)
    counts = {k + '_count': v for k, v in counts.items()}
    
    s.chart_set.create(
        steps_type = steps_type,
        difficulty = difficulty,
        meter = meter,
        credit = chart.get('CREDIT', ''),
        description = chart.description or '',
        chart_name = chart.get('CHARTNAME', ''),
        chart_hash = chart_hash,
        density_graph = get_density_graph(sim, chart, chart_len),
        release_date = s.release_date,
        has_attacks = bool(chart.get('ATTACKS', '').strip()),
        **counts
    )