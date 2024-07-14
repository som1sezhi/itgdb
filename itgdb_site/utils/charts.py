"""Helper functions for analyzing charts and determining chart information
using the `simfile` library.
"""

from typing import Tuple, Dict
import hashlib
import re
import os
from math import isclose
import subprocess
from fractions import Fraction
from simfile.types import Chart, Simfile
from simfile.dir import SimfileDirectory, SimfilePack
from simfile.notes import NoteData, NoteType
from simfile.notes.group import group_notes, SameBeatNotes, OrphanedNotes, NoteWithTail
from simfile.notes.count import *
from simfile.timing import TimingData, BeatValues, Beat
from simfile.timing.engine import TimingEngine
from PIL import Image


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


def _get_fake_segments(sim, chart):
    # use .get() to handle SMChart/SMSimfile gracefully
    fakes_str = chart.get('FAKES') or sim.get('FAKES')
    if fakes_str:
        return BeatValues.from_str(fakes_str)
    return []


def _is_in_fake_segment(fake_segs, beat):
    return any(
        seg.beat <= beat < seg.beat + Fraction(seg.value)
        for seg in fake_segs
    )


def _get_hittable_arrows(sim: Simfile, chart: Chart) -> NoteData:
    notes = NoteData(chart)
    fake_segs = _get_fake_segments(sim, chart)
    engine = TimingEngine(TimingData(sim, chart))
    # as of current, the simfile package counters count notes in fake
    # segments, while stepmania doesn't, so we'll have to filter it
    # ourselves first
    return NoteData.from_notes(filter(
        lambda note: \
            # keep all tails to avoid orphaning hold heads whose tails are in
            # a fake segment.
            # any orphaned tails will be dropped later by the counting functions
            note.note_type == NoteType.TAIL or \
            (
                engine.hittable(note.beat) and \
                not _is_in_fake_segment(fake_segs, note.beat)
            ),
        notes
    ), notes.columns)


def _count_hands(sim: Simfile, chart: Chart) -> int:
    """Count hands according to StepMania's counting behavior."""
    # currently, the simfile library's count_hands function does not count all
    # hands in cases where notes happen during holds/rolls, so we roll our
    # own function instead
    notes = NoteData(chart)
    grouped_notes = group_notes(
        notes,
        include_note_types=frozenset((
            NoteType.TAP,
            NoteType.HOLD_HEAD,
            NoteType.ROLL_HEAD,
            NoteType.LIFT,
            NoteType.TAIL
        )),
        join_heads_to_tails=True,
        same_beat_notes=SameBeatNotes.JOIN_ALL
    )
    fake_segs = _get_fake_segments(sim, chart)
    engine = TimingEngine(TimingData(sim, chart))

    tail_beats = [None] * notes.columns
    hands_count = 0
    for group in grouped_notes:
        cur_beat = group[0].beat
        # clear tails that have passed
        for i, tail_beat in enumerate(tail_beats):
            if tail_beat and tail_beat < cur_beat:
                tail_beats[i] = None
        # skip if notes are unhittable on this beat
        if not engine.hittable(cur_beat) or \
            _is_in_fake_segment(fake_segs, cur_beat):
            continue
        # detect and count hands
        active_holds_count = sum(t is not None for t in tail_beats)
        cur_row_note_count = len(group)
        if active_holds_count + cur_row_note_count > 2:
            hands_count += 1
        # add new tails for holds/rolls that start on this beat
        for note in group:
            if isinstance(note, NoteWithTail):
                tail_beats[note.column] = note.tail_beat
    
    return hands_count


def get_counts(sim: Simfile, chart: Chart) -> dict:
    """Get notecount statistics for a chart."""
    notes = NoteData(chart)
    hittables = _get_hittable_arrows(sim, chart)
    return {
        'objects': count_steps(
            notes,
            include_note_types=frozenset((
                NoteType.TAP,
                NoteType.HOLD_HEAD,
                NoteType.ROLL_HEAD,
                NoteType.LIFT,
                NoteType.MINE,
                NoteType.FAKE,
            )),
            same_beat_notes=SameBeatNotes.KEEP_SEPARATE
        ),
        'steps': count_steps(hittables),
        'combo': count_steps(
            hittables, same_beat_notes=SameBeatNotes.KEEP_SEPARATE
        ),
        'jumps': count_jumps(hittables),
        'mines': count_mines(hittables),
        'hands': _count_hands(sim, chart),
        'holds': count_holds(
            hittables, orphaned_tail=OrphanedNotes.DROP_ORPHAN
        ),
        'rolls': count_rolls(
            hittables, orphaned_tail=OrphanedNotes.DROP_ORPHAN
        ),
        'lifts': count_steps(
            hittables,
            include_note_types=frozenset((NoteType.LIFT,)),
            same_beat_notes=SameBeatNotes.KEEP_SEPARATE
        ),
        'fakes': count_steps(
            notes,
            include_note_types=frozenset((NoteType.FAKE,)),
            same_beat_notes=SameBeatNotes.KEEP_SEPARATE
        ),
    }


def get_density_graph(sim: Simfile, chart: Chart, chart_len: float) -> list:
    hittables = _get_hittable_arrows(sim, chart)
    grouped_notes = group_notes(
        hittables,
        include_note_types=frozenset(
            (
                NoteType.TAP,
                NoteType.HOLD_HEAD,
                NoteType.ROLL_HEAD,
            )
        ),
        same_beat_notes=SameBeatNotes.JOIN_ALL
    )

    # get number of notes per measure
    count_per_measure = []
    cur_measure_start = 0
    cur_measure_count = 0
    for note_row in grouped_notes:
        beat = note_row[0].beat
        # if we've exited the current measure,
        # finish the count for that measure and advance
        if beat >= cur_measure_start + 4:
            count_per_measure.append(cur_measure_count)
            cur_measure_count = 0
            cur_measure_start += 4
            while beat - cur_measure_start >= 4:
                count_per_measure.append(0)
                cur_measure_start += 4
        cur_measure_count += 1
    # append final measure
    count_per_measure.append(cur_measure_count)

    nps_data = [] # list of (measure time, nps) points in graph
    def append_point(time, nps):
        # if last 2 points in graph have same nps,
        # just move the 2nd one to current measure time
        # (idea stolen from simply love's code)
        if len(nps_data) >= 2 and \
            isclose(nps, nps_data[-1][1]) and \
            isclose(nps, nps_data[-2][1]):
            nps_data[-1][0] = time
        else:
            nps_data.append([time, nps])
    
    # get nps for each measure, assemble final graph data
    engine = TimingEngine(TimingData(sim, chart))
    start_t = engine.time_at(Beat(0))
    deferred_count = 0 # count of notes not put in the graph yet
    for i, count in enumerate(count_per_measure):
        end_beat = Beat((i + 1) * 4)
        end_t = engine.time_at(end_beat)
        measure_len = end_t - start_t
        # as it turns out, time_at() is not necessary monotonic w.r.t. beat #,
        # so we should check if measure is of positive length and only
        # advance the time if so.
        # also, the simply love code warns of certain scenarios, e.g.
        # measures 48 and 49 of "Mudkyp Korea/Can't Nobody" contain a negative
        # stop that creates a very small but positive-length measure
        # that can inflate the NPS. so here, if the measure does not meet a
        # certain length, we defer calculating the NPS until we
        # accumulate more time from future measures
        if measure_len > 0.12:
            # calculate the NPS, including notes deferred from previous
            # skipped measures
            nps = (count + deferred_count) / measure_len
            # reset the deferred count now that we've actually counted them
            deferred_count = 0
            append_point(start_t, nps)
            start_t = end_t # end of measure is start of next measure
        # as per above, if measure is too short/nonpositive length,
        # defer its count until later
        else:
            deferred_count += count
    # in the rare case where there are still deferred counts at the end,
    # let's just ditch them

    # add 0 nps point right after last measure
    beat = Beat(len(count_per_measure) * 4)
    time = engine.time_at(beat)
    append_point(time, 0)

    # add 0 nps point at *very* end of song:
    if chart_len > nps_data[-1][0] + 0.1:
        append_point(chart_len, 0)
    
    return nps_data


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
    full_path = _find_case_sensitive_path(sim_dir_path, path)
    pack_path = os.path.dirname(sim_dir_path)
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

    sim = simfile_dir.open()
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


def get_song_lengths(music_path: str, sim: Simfile) -> Tuple[float, float] | None:
    """Return two floats:
    - the music length (as displayed on the songwheel in StepMania)
    - the time when the song's charts ends (the rightmost bound of density 
      graphs). This is the maximum of:
        - the LASTSECONDHINT value
        - the time of the last note in any chart in the simfile (edit charts
          are ignored unless the only chart is a single edit chart)
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

    # init charts' end as the LASTSECONDHINT value
    chart_end = float(sim.get('LASTSECONDHINT', '0'))
    
    for chart in sim.charts:
        # NOTE: it is intended behavior for the chart length to be affected
        # by charts with stepstype that are not 4/8-panel-based (e.g. pump)
        # -- see the test_longer_chart test case.
        # TODO: ignore lights chart?
        # see Song::ReCalculateRadarValuesAndLastSecond() in SM source code

        # ignore edit charts (unless it is the only chart)
        # NOTE: SM doesn't like it if the simfile consists entirely of 2+ edit
        # charts (the chart ends basically immediately). I think leaving
        # chart_end at 0 is acceptable behavior in this case.
        if chart.difficulty.lower() == 'edit' and len(sim.charts) > 1:
            continue

        notes = NoteData(chart)
        # get the last note by exhausting the iterator
        last_note = None
        for last_note in notes:
            pass

        if last_note:
            engine = TimingEngine(TimingData(sim, chart))
            last_note_time = engine.time_at(last_note.beat)
            chart_end = max(chart_end, last_note_time)
    
    return max(music_len, chart_end), chart_end


