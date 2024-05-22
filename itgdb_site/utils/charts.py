import hashlib
import re
from math import isclose
from fractions import Fraction
from simfile.types import Chart, Simfile
from simfile.notes import NoteData, NoteType
from simfile.notes.group import group_notes, SameBeatNotes, OrphanedNotes, NoteWithTail
from simfile.notes.count import *
from simfile.timing import TimingData, BeatValues, Beat
from simfile.timing.engine import TimingEngine


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


def get_density_graph(sim: Simfile, chart: Chart) -> list:
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
    # find last note in chart
    last = None
    for last in NoteData(chart):
        pass
    if last:
        last_t = engine.time_at(last.beat)
    else:
        last_t = 0
    # get lastsecondhint
    last_sec_hint = float(sim.get('LASTSECONDHINT', '0'))
    last_t = max(last_t, last_sec_hint)
    if last_t > nps_data[-1][0] + 0.1:
        append_point(last_t, 0)
    
    return nps_data
