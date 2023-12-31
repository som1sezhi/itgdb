import hashlib
import re
from fractions import Fraction
from simfile.base import BaseChart, BaseSimfile
from simfile.notes import NoteData, NoteType
from simfile.notes.group import SameBeatNotes, OrphanedNotes
from simfile.notes.count import *
from simfile.timing import TimingData, BeatValues
from simfile.timing.engine import TimingEngine


def _normalize_decimal(decimal):
    rounded = round(float(decimal), 3)
    return '%.3f' % (rounded,)


def _normalize_float_digits(param):
    param_parts = []
    for beat_bpm in re.findall('[^,]+', param):
        m = re.match('(.+)=(.+)', beat_bpm)
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


def get_hash(sim: BaseSimfile, chart: BaseChart) -> str:
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


def get_counts(sim: BaseSimfile, chart: BaseChart) -> dict:
    """Get notecount statistics for a chart."""
    notes = NoteData(chart)
    # as of current, the simfile package counters count notes in fake
    # segments, while stepmania doesn't, so we'll have to filter it
    # ourselves first
    fake_segs = _get_fake_segments(sim, chart)
    engine = TimingEngine(TimingData(sim, chart))
    hittables = NoteData.from_notes(filter(
        lambda note: \
            engine.hittable(note.beat) and \
            not _is_in_fake_segment(fake_segs, note.beat),
        notes
    ), notes.columns)
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
        'hands': count_hands(hittables),
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
