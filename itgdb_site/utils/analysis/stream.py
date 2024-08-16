from math import isclose
from simfile.types import Chart, Simfile
from simfile.notes import NoteType
from simfile.notes.group import group_notes, SameBeatNotes
from simfile.notes.count import *
from simfile.timing import TimingData, Beat
from simfile.timing.engine import TimingEngine

from ..charts import _get_hittable_arrows

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

    # get number of notes per beat
    count_per_beat = []
    cur_beat = 0
    cur_beat_count = 0
    for note_row in grouped_notes:
        beat = note_row[0].beat
        # if we've exited the current measure,
        # finish the count for that measure and advance
        if beat >= cur_beat + 1:
            count_per_beat.append(cur_beat_count)
            cur_beat_count = 0
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

