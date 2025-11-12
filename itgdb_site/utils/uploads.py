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
from .ini import IniFile
from .path import find_case_sensitive_path, convert_path_to_os_style

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


def _get_pack_ini_if_present(pack_path: str):
    pack_ini_path = find_case_sensitive_path(pack_path, 'Pack.ini')
    if pack_ini_path and os.path.isfile(pack_ini_path):
        return IniFile(pack_ini_path)
    return None


def upload_pack(
    simfile_pack: SimfilePack,
    pack_data: dict,
    prog_tracking_info: ProgressTrackingInfo | None = None
):
    pack_path = simfile_pack.pack_dir
    image_cache = {}
    delete_dupe_sims(simfile_pack) # kind of redundant but i think it's fine

    pack_ini = _get_pack_ini_if_present(pack_path)
    # only use pack.ini if a non-empty version value exists
    # (matches ITGmania behavior)
    if pack_ini and (pack_ini.get('Group', 'Version') or '').strip('\r\n\t '):
        pack_ini_raw = pack_ini.raw_text
        display_title = pack_ini.get('Group', 'DisplayTitle')
        pack_bn_path = pack_ini.get('Group', 'Banner')
        if pack_bn_path:
            pack_bn_path = convert_path_to_os_style(pack_bn_path)
            pack_bn_path = find_case_sensitive_path(pack_path, pack_bn_path)
    else:
        pack_ini_raw = ''
        display_title = None
        pack_bn_path = None

    p = Pack(
        name = display_title or pack_data['name'] or simfile_pack.name,
        author = pack_data['author'],
        release_date = pack_data['release_date'],
        release_date_year_only = pack_data['release_date_year_only'],
        category_id = pack_data['category'],
        links = pack_data['links'],
        pack_ini = pack_ini_raw,
    )
    p.save()

    p.tags.add(*pack_data['tags'])

    # find banner file
    banner = None
    # first, try the path specified in pack.ini, if present
    if pack_bn_path:
        banner = _get_image(pack_bn_path, p, image_cache, True)
    # if the path is not specified in pack.ini or the banner doesn't exist,
    # fall back to the default way of fetching the pack banner
    if banner is None:
        pack_bn_path = get_pack_banner_path(pack_path, simfile_pack)
        banner = _get_image(pack_bn_path, p, image_cache, True)
    p.banner = banner
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


def patch_pack(
    simfile_pack: SimfilePack,
    p: Pack,
    patch_params: dict,
    prog_tracking_info: ProgressTrackingInfo | None = None
):
    pack_path = simfile_pack.pack_dir
    image_cache = {}
    delete_dupe_sims(simfile_pack) # kind of redundant but i think it's fine

    pack_ini = _get_pack_ini_if_present(pack_path)
    # only use pack.ini if a non-empty version value exists
    # (matches ITGmania behavior)
    if pack_ini and (pack_ini.get('Group', 'Version') or '').strip('\r\n\t '):
        pack_ini_raw = pack_ini.raw_text
        display_title = pack_ini.get('Group', 'DisplayTitle')
        pack_bn_path = pack_ini.get('Group', 'Banner')
        if pack_bn_path:
            pack_bn_path = convert_path_to_os_style(pack_bn_path)
            pack_bn_path = find_case_sensitive_path(pack_path, pack_bn_path)
    else:
        pack_ini_raw = ''
        display_title = None
        pack_bn_path = None
    
    if pack_ini_raw:
        p.pack_ini = pack_ini_raw
        if display_title:
            p.name = display_title
    
    # TODO: the following code for patching the banner is not exactly the best
    # way to do things; it will create a new imagefile in the DB even if one
    # already exists, thus orphaning the old imagefile, unless a song uses the
    # pack banner for its own banner, in which case the song will still be 
    # using the old imagefile.
    # commenting this out for now until i feel like implementing this properly.
    # apply banner patches manually in the meantime
    '''
    # find banner file
    banner = None
    # first, try the path specified in pack.ini, if present
    if pack_bn_path:
        banner = _get_image(pack_bn_path, p, image_cache, True)
    # if the path is not specified in pack.ini or the banner doesn't exist,
    # fall back to the default way of fetching the pack banner
    if banner is None:
        pack_bn_path = get_pack_banner_path(pack_path, simfile_pack)
        banner = _get_image(pack_bn_path, p, image_cache, True)
    # only overwrite existing banner if we found a new one
    if banner:
        p.banner = banner
    '''

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
        upload_song(simfile_dir, p, image_cache, patch_params)


def upload_song(
    simfile_dir: SimfileDirectory,
    p: Pack | None = None,
    image_cache: dict | None = None,
    patch_params: dict | None = None
):
    if image_cache is None:
        image_cache = {}

    sim = simfile_dir.open(strict=False)
    assets = get_assets(simfile_dir)
    sim_path = simfile_dir.simfile_path
    sim_filename = os.path.basename(sim_path)

    logger.info(f'Processing {p.name if p else "<single>"}/{sim.title}')

    song_analyzer = SongAnalyzer(sim)

    # bit of a hack: temporarily filter out 0 bpm segments to match the 
    # behavior of stepmania
    def _filter_out_0bpm_segs(bpms):
        return str(BeatValues(
            bpm for bpm in BeatValues.from_str(bpms) if bpm.value != 0
        ))
    old_bpms = sim.bpms
    if old_bpms is not None:
        sim.bpms = _filter_out_0bpm_segs(old_bpms)
    try:
        bpm = displaybpm(sim, ignore_specified=True)
        disp = displaybpm(sim)
        bpm_range = (bpm.min, bpm.max)
        disp_range = (disp.min, disp.max)
    except KeyError:
        # if the simfile has no main #BPMS field, use a chart's #BPMS instead.
        # first, figure out which chart to use.
        # prioritize singles and higher difficulties (but leave edits for last)
        # TODO: this might be overcomplicated for handling a case this rare.
        # take another look later
        chart_keys = [get_chart_key(chart) for chart in sim.charts]
        chart_keys = sorted(
            # filter out unknown stepstype
            filter(
                lambda k: Chart.steps_type_to_int(k[0]) is not None,
                chart_keys
            ),
            key=lambda k: (
                Chart.steps_type_to_int(k[0]), # singles=1 < doubles=2
                -k[1] if k[1] <= 4 else k[1]   # diffs: -4, -3, -2, -1, 0, 5
            )
        )
        bpm, disp = None, None
        if len(chart_keys) > 0:
            chart_analyzer = song_analyzer.chart_analyzers[chart_keys[0]]
            chart = chart_analyzer.chart
            old_chart_bpms = chart.get('BPMS')
            if old_chart_bpms is not None:
                chart.bpms = _filter_out_0bpm_segs(old_chart_bpms)
                # this shouldn't KeyError this time
                bpm = displaybpm(sim, chart, ignore_specified=True)
                disp = displaybpm(sim, chart)
                chart.bpms = old_chart_bpms # restore
        if bpm is not None:
            bpm_range = (bpm.min, bpm.max)
            disp_range = (disp.min, disp.max)
        else:
            bpm_range = (60, 60)
            disp_range = (60, 60)
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
    
    # are we patching a pack?
    existing_song = None
    is_patching = patch_params is not None
    if is_patching:
        assert p is not None
        patch_results = patch_params['results']
        # try to match this song with an existing one based on (sub)title
        existing_songs = p.song_set.filter(title=title, subtitle=subtitle)
        count = existing_songs.count()
        log_name = title + ' ' + subtitle
        if count == 0: # song doesn't exist yet...
            patch_results.append(log_name, 'create')
        elif count > 1: # too many songs match the criteria
            patch_results.append(log_name, 'skip')
            return # bail out
        else: # count == 1
            patch_results.append(log_name, 'combine')
            existing_song = existing_songs.first()
    
    if existing_song is not None:
        # grab song lengths from existing song record in db
        music_len = existing_song.music_length
        chart_len = existing_song.chart_length
    else:
        # must figure out song length from file.
        # if we're uploading this sim for the first time, we should
        # have the song file available.
        music_path = assets['MUSIC']
        if not music_path:
            if is_patching:
                patch_results.append(log_name, 'err: no music')
            return
        song_lengths = get_song_lengths(music_path, song_analyzer)
        if not song_lengths:
            if is_patching:
                patch_results.append(log_name, 'err: can\'t open music')
            return
        music_len, chart_len = song_lengths

    with open(sim_path, 'rb') as f:
        fields = dict(
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
            # NOTE: we now fill in release date later
            simfile = File(f, name=f'{sim_uuid}_{sim_filename}'),
            has_bgchanges = bool((sim.bgchanges or '').strip()),
            has_fgchanges = bool((sim.fgchanges or '').strip()),
            has_attacks = bool((sim.attacks or '').strip()),
            has_sm = bool(simfile_dir.sm_path),
            has_ssc = bool(simfile_dir.ssc_path),
        )
        # if we're newly creating this song...
        if existing_song is None:
            # we need to fill in the release date as appropriate.
            # if this song is newly created via a pack patch,
            # set release date as patch release date
            if is_patching and patch_params['patch_date']:
                fields['release_date'] = patch_params['patch_date']
                fields['release_date_year_only'] = False
            # otherwise, use pack release date
            else:
                fields['release_date'] = p.release_date if p else None
                fields['release_date_year_only'] = \
                    p.release_date_year_only if p else False
            
            # create new song
            s = Song(**fields)
            s.save()
        else:
            # we are patching an existing song.
            # we keep the release date already on that song and just
            # update the rest of the fields
            s = existing_song
            for field, val in fields.items():
                setattr(s, field, val)

        s.save()

        img_parent = p or s
        # add assets, but only if they're found (so patches that don't include
        # asset files don't overwrite existing asset fields)
        if banner := _get_image(assets['BANNER'], img_parent, image_cache, True):
            s.banner = banner
        if bg := _get_image(assets['BACKGROUND'], img_parent, image_cache, True):
            s.bg = bg
        if cdtitle := _get_image(assets['CDTITLE'], img_parent, image_cache):
            s.cdtitle = cdtitle
        if jacket := _get_image(assets['JACKET'], img_parent, image_cache):
            s.jacket = jacket
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
            upload_chart(chart, s, song_analyzer, patch_params)
            chart_keys_already_uploaded.add(chart_key)
    
    # if we are patching, then there might be charts in diff slots that were
    # in the old version but are no longer in the patch simfile that we just
    # uploaded (e.g. a chart gets moved from Hard to Challenge).
    # we thus delete these old charts
    if is_patching:
        for c in list(s.chart_set.all()):
            if c.get_chart_key() not in chart_keys_already_uploaded:
                log_name = f'[{Chart.STEPS_TYPE_CHOICES[c.steps_type]} {Chart.DIFFICULTY_CHOICES[c.difficulty]}]'
                patch_results.append(log_name, 'delete')
                c.delete()


def upload_chart(
    chart: SimfileChart,
    s: Song,
    song_analyzer: SongAnalyzer,
    patch_params: dict | None = None
):
    steps_type = Chart.steps_type_to_int(chart.stepstype)
    if steps_type is None:
        # ignore charts with unsupported stepstype
        return
    description = (chart.description or '').strip()
    meter = Chart.meter_str_to_int(chart.meter)
    difficulty = Chart.difficulty_str_to_int(
        chart.difficulty or '', description, meter
    )

    existing_chart = None
    is_patching = patch_params is not None
    if is_patching:
        patch_results = patch_params['results']
        # try to match this chart with an existing one
        existing_charts = s.chart_set.filter(
            steps_type=steps_type, difficulty=difficulty
        )
        # if an edit chart, additionally filter by description
        if difficulty == 5:
            existing_charts = existing_charts.filter(description=description)
        count = existing_charts.count()
        assert count <= 1
        log_name = f'[{Chart.STEPS_TYPE_CHOICES[steps_type]} {Chart.DIFFICULTY_CHOICES[difficulty]}]'
        if count == 0: # chart doesn't exist yet...
            patch_results.append(log_name, 'new chart')
        else: # count == 1
            patch_results.append(log_name, 'overwrite')
            existing_chart = existing_charts.first()
    
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
    fields = dict(
        song = s,
        steps_type = steps_type,
        difficulty = difficulty,
        meter = meter,
        credit = chart.get('CREDIT') or '',
        description = description,
        chart_name = (chart.get('CHARTNAME') or '').strip(),
        chart_hash = chart_hash,
        analysis = analysis,
        # release_date = s.release_date,
        # release_date_year_only = s.release_date_year_only,
        has_attacks = bool((chart.get('ATTACKS') or '').strip()),
        **counts
    )

    if existing_chart is None:
        # we need to fill in the release date as appropriate.
        # if this chart is newly created via a pack patch,
        # set release date as patch release date
        if is_patching and patch_params['patch_date']:
            fields['release_date'] = patch_params['patch_date']
            fields['release_date_year_only'] = False
        # otherwise, use song release date
        else:
            fields['release_date'] = s.release_date
            fields['release_date_year_only'] = s.release_date_year_only
        
        # create new chart
        s.chart_set.create(**fields)
    else:
        # we are patching an existing song.
        # we keep the release date already on that song and just
        # update the rest of the fields
        for field, val in fields.items():
            setattr(existing_chart, field, val)
        existing_chart.save()