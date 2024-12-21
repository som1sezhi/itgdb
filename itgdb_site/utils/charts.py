"""Helper functions for analyzing charts and determining chart information
using the `simfile` library.
"""

from typing import Tuple, Dict, Iterable
import hashlib
import re
import os
from math import isclose
import subprocess
from fractions import Fraction
from simfile.types import Chart, Simfile
from simfile.dir import SimfileDirectory, SimfilePack
from simfile.notes import NoteData, NoteType, Note
from simfile.notes.group import group_notes, SameBeatNotes, OrphanedNotes, NoteWithTail
from simfile.notes.count import *
from simfile.timing import TimingData, BeatValues, Beat
from simfile.timing.engine import TimingEngine
from PIL import Image

from .analysis import SongAnalyzer


IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
SOUND_EXTS = ('.mp3', '.oga', '.ogg', '.wav')


def _normalize_decimal(decimal):
    rounded = round(float(decimal), 3)
    return '%.3f' % (rounded,)


def _normalize_float_digits(param):
    param_parts = []
    for beat_bpm in re.findall('[^,]+', param):
        m = re.search('(.+)=(.+)', beat_bpm)
        normd = _normalize_decimal(m[1]) + '=' + _normalize_decimal(m[2])
        param_parts.append(normd)
    return ','.join(param_parts)


def _minimize_measure(measure):
    if not measure:
        # if the measure is empty, it will cause an infinite loop in
        # the while loop after this, so we have to catch it now
        # TODO: figure out a more proper way of dealing with empty measures
        raise RuntimeError('chart contains an empty measure')
    minimal = False
    while not minimal and len(measure) % 2 == 0:
        all_zeroes = True
        for row in measure[1::2]:
            if row != '0' * len(row):
                all_zeroes = False
                break
        if all_zeroes:
            measure = measure[::2]
        else:
            minimal = True
    return measure


def _minimize_chart(chart_str):
    final_data = []
    cur_measure = []
    for line in chart_str.split('\n'):
        if line == ',':
            cur_measure = _minimize_measure(cur_measure)
            final_data.extend(cur_measure)
            final_data.append(',')
            cur_measure.clear()
        else:
            cur_measure.append(line)
    if cur_measure:
        cur_measure = _minimize_measure(cur_measure)
        final_data.extend(cur_measure)
    return '\n'.join(final_data)


def get_hash(sim: Simfile, chart: Chart) -> str:
    """Get the Groovestats hash of a chart."""
    # TODO: is all this necessary?
    notedata = chart.notes
    notedata = re.sub(r'\r\n?', r'\n', notedata)
    notedata = notedata.strip()
    notedata = re.sub(r'//[^\n]*', '', notedata)
    notedata = re.sub(r'[\r\t\f\v ]+', '', notedata)
    notedata = _minimize_chart(notedata)
    # use .get() to handle SMChart gracefully
    bpms = _normalize_float_digits(chart.get('BPMS') or sim.bpms)
    return hashlib.sha1((notedata + bpms).encode()).hexdigest()


# https://stackoverflow.com/a/37708342
def _find_case_sensitive_path(dir: str, insensitive_path: str):
    insensitive_path = os.path.normpath(insensitive_path)
    insensitive_path = insensitive_path.lstrip(os.path.sep)

    parts = insensitive_path.split(os.path.sep, 1)
    next_name = parts[0]
    for name in os.listdir(dir):
        if next_name.lower() == name.lower():
            improved_path = os.path.join(dir, name)
            if len(parts) == 1:
                return improved_path
            else:
                return _find_case_sensitive_path(
                    improved_path, parts[1]
                )
    return None


def _get_full_validated_asset_path(sim_dir_path: str, path: str):
    if not path:
        return None
    path = path.strip()
    pack_path = os.path.dirname(sim_dir_path)
    insensitive_full_path = os.path.normpath(os.path.join(sim_dir_path, path))
    # get the true, case-sensitive path to the asset.
    # we start the case-sensitive search from the pack directory so we can find
    # assets outside the simfile directory but still in the pack directory
    full_path = _find_case_sensitive_path(
        pack_path, os.path.relpath(insensitive_full_path, start=pack_path)
    )
    
    # ensure path exists and does not point outside the pack
    if full_path and full_path.startswith(pack_path):
        # ensure path is a file
        if os.path.isfile(full_path):
            return full_path
    return None


ASSET_FILENAME_PATTERNS = {
    'BANNER': re.compile('banner| bn$'),
    'BACKGROUND': re.compile('background|bg$'),
    'CDTITLE': re.compile('cdtitle'),
    'JACKET': re.compile('^jk_|jacket|albumart'),
    'CDIMAGE': re.compile('-cd$'),
    'DISC': re.compile(' disc$| title$')
}

def get_assets(simfile_dir: SimfileDirectory) -> Dict[str, str | None]:
    """Get a dict of absolute paths to various asset files for a simfile.
    If the asset doesn't exist, its value is None.

    dictionary keys:
    'MUSIC', 'BANNER', 'BACKGROUND', 'CDTITLE', 'JACKET', 'CDIMAGE', 'DISC'
    """
    # NOTE: currently, simfile.assets can fail to find assets in cases where
    # there are no filename hints. to remedy this, we reproduce stepmania's
    # algorithm here.
    # see TidyUpData() in Song.cpp in the stepmania source code for the
    # original algorithm

    sim = simfile_dir.open(strict=False)
    sim_dir_path = os.path.normpath(simfile_dir.simfile_dir)

    # first, try to populate fields using the simfile's fields
    assets = {
        prop: _get_full_validated_asset_path(sim_dir_path, sim.get(prop))
        for prop in (
            'MUSIC', 'BANNER', 'BACKGROUND',
            'CDTITLE', 'JACKET', 'CDIMAGE', 'DISC'
        )
    }

    # stepmania represents directories as what is essentially an
    # std::set<File>, where File::operator<() compares by lowercased filename.
    # Thus, stepmania fetches files by (lowercase) alphabetical filename order.
    file_list = sorted(os.listdir(sim_dir_path), key=str.lower)
    # ignore filenames starting with "._" (macOS stuff)
    file_list = list(filter(
        lambda fname: not fname.startswith('._'),
        file_list
    ))

    image_list = list(filter(
        lambda fname: any(fname.lower().endswith(ext) for ext in IMAGE_EXTS),
        file_list
    ))
    
    # if music isn't found yet, use the first file with an audio extension
    if not assets['MUSIC']:
        for fname in file_list:
            if any(fname.lower().endswith(ext) for ext in SOUND_EXTS):
                assets['MUSIC'] = os.path.join(sim_dir_path, fname)
                break
    
    # for image assets that aren't found yet, check if filename matches the
    # appropriate asset pattern, and use it if so.
    for prop in assets:
        if prop == 'MUSIC' or assets[prop]:
            continue
        pattern = ASSET_FILENAME_PATTERNS[prop]
        for fname in image_list:
            base_fname_lower = fname.rsplit('.', 1)[0].lower()
            if re.search(pattern, base_fname_lower):
                assets[prop] = os.path.join(sim_dir_path, fname)
                break
    
    used_images = set(
        os.path.basename(v) for k, v in assets.items() if v and k != 'MUSIC'
    )
    
    # if assets still aren't found yet, look at the image dimensions
    # of the remaining images.
    for fname in image_list:
        # exit loop if "done"
        if assets['BANNER'] and assets['BACKGROUND'] and assets['CDTITLE']:
            break
        # don't consider images that are already used
        if fname in used_images:
            continue

        full_path = os.path.join(sim_dir_path, fname)
        try:
            image = Image.open(full_path)
        except:
            continue # could not open image, skip
        w, h = image.size

        if not assets['BACKGROUND'] and w >= 320 and h >= 240:
            assets['BACKGROUND'] = full_path

        elif not assets['BANNER'] and 100 <= w <= 320 and 50 <= h <= 240:
            assets['BANNER'] = full_path

        elif not assets['BANNER'] and w > 200 and w / h > 2:
            assets['BANNER'] = full_path

        elif not assets['CDTITLE'] and w <= 100 and h <= 48:
            assets['CDTITLE'] = full_path

        elif not assets['JACKET'] and w == h:
            assets['JACKET'] = full_path

        elif not assets['DISC'] and w > h and assets['BANNER']:
            # this condition is separated out to match the logic of the
            # original stepmania code as close as possible
            if assets['BANNER'] != full_path:
                assets['DISC'] = full_path

        elif not assets['CDIMAGE'] and w == h:
            assets['CDIMAGE'] = full_path
    
    return assets


def get_pack_banner_path(pack_path: str, simfile_pack: SimfilePack) -> str | None:
    # NOTE: currently the simfile library (2.1.1) doesn't reproduce the exact 
    # behavior of stepmania when looking for pack banners, so we write our
    # own function.
    # as in get_assets(), stepmania draws potential pack banner files from
    # a std::set<File> which is sorted by (lowercase) alphabet order,
    # so here we sort the directory listing before iterating through.
    for image_type in IMAGE_EXTS:
        for item in sorted(os.listdir(pack_path), key=str.lower):
            if item.lower().endswith(image_type):
                return os.path.join(pack_path, item)

    # let's just use simfile's implementation for the case where
    # the banner is outside the pack directory
    return simfile_pack.banner()


def get_song_lengths(
    music_path: str, song_analyzer: SongAnalyzer
) -> Tuple[float, float] | None:
    """Return the song length (as displayed on the songwheel in StepMania).
    If the music file could not be opened, None is returned.
    """
    # fetch music file duration using ffprobe
    completed_process = subprocess.run([
        'ffprobe', '-i', music_path, '-show_entries', 'format=duration',
        '-v', 'quiet', '-of', 'csv=p=0'
    ], capture_output=True, encoding='utf-8')
    # check for failure
    if completed_process.returncode != 0:
        return None

    music_len = float(completed_process.stdout)

    chart_end = song_analyzer.get_chart_len()
    return max(music_len, chart_end), chart_end