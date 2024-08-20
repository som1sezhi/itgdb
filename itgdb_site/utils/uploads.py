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
from PIL import Image

from ..models import Pack, Song, Chart, ImageFile
from .charts import (
    get_hash, get_assets, get_pack_banner_path, get_song_lengths
)
from .analysis import SongAnalyzer

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


def upload_song(
    simfile_dir: SimfileDirectory,
    p: Pack | None = None,
    image_cache: dict | None = None
):
    if image_cache is None:
        image_cache = {}

    sim = simfile_dir.open()
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

    bpm = displaybpm(sim, ignore_specified=True)
    disp = displaybpm(sim)
    bpm_range = (bpm.min, bpm.max)
    disp_range = (disp.min, disp.max)

    sim_uuid = uuid.uuid4()

    with open(sim_path, 'rb') as f:
        s = Song(
            pack = p,
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
            music_length = music_len,
            chart_length = chart_len,
            release_date = p.release_date if p else None,
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

    for chart in sim.charts:
        upload_chart(chart, s, song_analyzer)


def upload_chart(chart: SimfileChart, s: Song, song_analyzer: SongAnalyzer):
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
    
    chart_hash = get_hash(song_analyzer.sim, chart)

    analyzer = song_analyzer.get_chart_analyzer(chart)
    counts = analyzer.get_counts()
    counts = {k + '_count': v for k, v in counts.items()}
    analysis = {
        'density_graph': analyzer.get_density_graph(),
        'stream_info': analyzer.get_stream_info(),
    }
    
    s.chart_set.create(
        steps_type = steps_type,
        difficulty = difficulty,
        meter = meter,
        credit = chart.get('CREDIT', ''),
        description = chart.description or '',
        chart_name = chart.get('CHARTNAME', ''),
        chart_hash = chart_hash,
        analysis = analysis,
        release_date = s.release_date,
        has_attacks = bool(chart.get('ATTACKS', '').strip()),
        **counts
    )