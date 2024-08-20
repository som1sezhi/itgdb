"""Classes for analyzing simfiles and charts.

My main reason for using classes here is so that I can more easily cache certain
expensive-to-compute results, hence the @cached_property decorators.
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
from itertools import zip_longest
from functools import cached_property
from math import isclose
from fractions import Fraction
from simfile.types import Chart, Simfile
from simfile.notes import NoteData, NoteType, Note
from simfile.notes.group import group_notes, SameBeatNotes, OrphanedNotes, NoteWithTail
from simfile.notes.count import *
from simfile.timing import TimingData, BeatValues, BeatValue, Beat
from simfile.timing.engine import TimingEngine


@dataclass
class StreamRun:
    start: int
    len: int


class SongAnalyzer:
    """A class facilitating the analysis of songs."""

    def __init__(self, sim: Simfile):
        self.sim = sim
        self.chart_analyzers: Dict[tuple, ChartAnalyzer] = {}
        for chart in sim.charts:
            self.chart_analyzers[self._chart_key(chart)] = ChartAnalyzer(
                chart, self
            )

    @staticmethod
    def _chart_key(chart: Chart):
        return (
            chart.stepstype, chart.difficulty, chart.meter, chart.description
        )

    @cached_property
    def chart_len(self) -> float:
        """The time when the song's charts ends (the rightmost bound of density
        graphs). This is the maximum of:
        - the LASTSECONDHINT value
        - the time of the last note in any chart in the simfile (edit charts
        are ignored unless the only chart is a single edit chart)"""
        # init charts' end as the LASTSECONDHINT value
        chart_end = float(self.sim.get('LASTSECONDHINT', '0'))
        
        for analyzer in self.chart_analyzers.values():
            chart = analyzer.chart

            # NOTE: it is intended behavior for the chart length to be affected
            # by charts with stepstype that are not 4/8-panel-based (e.g. pump)
            # -- see the test_longer_chart test case.
            # TODO: ignore lights chart?
            # see Song::ReCalculateRadarValuesAndLastSecond() in SM source code

            # ignore edit charts (unless it is the only chart)
            # NOTE: SM doesn't like it if the simfile consists entirely of 2+ edit
            # charts (the chart ends basically immediately). I think leaving
            # chart_end at 0 is acceptable behavior in this case.
            if chart.difficulty.lower() == 'edit' and len(self.sim.charts) > 1:
                continue

            if analyzer.last_note_beat:
                last_note_time = analyzer.engine.time_at(
                    analyzer.last_note_beat
                )
                chart_end = max(chart_end, last_note_time)
        
        return chart_end
    
    def get_chart_analyzer(self, chart: Chart) -> 'ChartAnalyzer':
        return self.chart_analyzers[self._chart_key(chart)]
    
    def get_chart_len(self):
        return self.chart_len


class ChartAnalyzer:
    """A class facilitating the analysis of charts.
    Note: This class should not be instantiated directly. Instead, create
    a SongAnalyzer and fetch an instance using
    `song_analyzer.get_chart_analyzer(chart)`."""

    def __init__(self, chart: Chart, song_analyzer: SongAnalyzer):
        self.sim = song_analyzer.sim
        self.chart = chart
        self.notes = NoteData(chart)
        self.engine = TimingEngine(TimingData(self.sim, chart))
        self.song_analyzer = song_analyzer

    @cached_property
    def fake_segments(self) -> List[BeatValue]:
        # use .get() to handle SMChart/SMSimfile gracefully
        fakes_str = self.chart.get('FAKES') or self.sim.get('FAKES')
        if fakes_str:
            fake_segs = BeatValues.from_str(fakes_str)
            # observed behavior from experimenting with the game:
            # - game will handle out-of-order fake segments just fine
            # - negative beat values work properly
            # - negative segment lengths act like 0 length
            # - if segment length is < ~1/96, it effectively doesn't exist
            #   - the exact value is between 0.01041666744 and 0.01041666745,
            #     though at this point we're basically running into float
            #     imprecision so idk. i think it's alright to just call it 1/96
            # - if fake segments overlap, the fake region ends at the ending
            #   point of the later segment
            fake_segs = [seg for seg in fake_segs if seg.value >= 1/96]
            fake_segs.sort(key=lambda seg: seg.beat)
            return fake_segs
        return []

    @cached_property
    def hittables(self) -> List[Note]:
        # as of current, the simfile package counters count notes in fake
        # segments, while stepmania doesn't, so we'll have to filter it
        # ourselves first.

        # turns out it's quite a bit faster to just store all the hittable notes
        # in a list and reuse that than to use an iterator and run through
        # the notedata iteration process multiple times. i don't think the 
        # memory cost will be super bad either (1M notes will take up around 
        # 88 MB if my math is correct)
        def generator():
            start_idx = -1
            for note in self.notes:
                if note.note_type == NoteType.TAIL:
                    # keep all tails to avoid orphaning hold heads whose tails
                    # are in a fake segment.
                    # any orphaned tails will be dropped later by the
                    # counting functions
                    yield note
                elif not self.engine.hittable(note.beat):
                    continue
                else:
                    in_fake_seg, start_idx = self._is_in_fake_segment(
                        note.beat, start_idx
                    )
                    if not in_fake_seg:
                        yield note

        return list(generator())

    @cached_property
    def notes_per_measure(self) -> List[int]:
        grouped_notes = group_notes(
            self.hittables,
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

        return count_per_measure

    @cached_property
    def last_note_beat(self) -> Beat:
        """The beat value of the last note/mine/object in the chart."""
        # get the last note by exhausting the iterator
        last_note = None
        for last_note in self.notes:
            pass
        return last_note.beat

    def _is_in_fake_segment(
            self, beat: Beat, start_idx: int
    ) -> Tuple[bool, int]:
        """Checks whether the given beat lands within a fake segment.

        start_idx is the index into self.fake_segments where we should start
        searching. start_idx must be <= the index of the last segment with
        start time <= the given beat. start_idx should initially be -1
        (meaning no fake segments are before the given beat).

        Returns the result of the check, and a new value of start_idx to use
        for next time.
        """
        # advance start_idx to the last segment with start time <= beat
        while start_idx < len(self.fake_segments) - 1 \
            and self.fake_segments[start_idx + 1].beat <= beat:
            start_idx += 1
        result = False
        if start_idx >= 0:
            # check if inside this segment
            seg = self.fake_segments[start_idx]
            result = beat < seg.beat + Fraction(seg.value)
        return result, start_idx
    
    def _count_hands(self) -> int:
        """Count hands according to StepMania's counting behavior."""
        # currently, the simfile library's count_hands function does not count all
        # hands in cases where notes happen during holds/rolls, so we roll our
        # own function instead
        grouped_notes = group_notes(
            self.notes,
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

        tail_beats = [None] * self.notes.columns
        hands_count = 0
        fake_seg_start_idx = -1
        for group in grouped_notes:
            cur_beat = group[0].beat
            # clear tails that have passed
            for i, tail_beat in enumerate(tail_beats):
                if tail_beat and tail_beat < cur_beat:
                    tail_beats[i] = None
            # skip if notes are unhittable on this beat
            if not self.engine.hittable(cur_beat):
                continue
            in_fake_seg, fake_seg_start_idx = self._is_in_fake_segment(
                cur_beat, fake_seg_start_idx
            )
            if in_fake_seg:
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

    def get_counts(self) -> Dict[str, int]:
        """Get notecount statistics for a chart."""
        return {
            'objects': count_steps(
                self.notes,
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
            'steps': count_steps(self.hittables),
            'combo': count_steps(
                self.hittables, same_beat_notes=SameBeatNotes.KEEP_SEPARATE
            ),
            'jumps': count_jumps(self.hittables),
            'mines': count_mines(self.hittables),
            'hands': self._count_hands(),
            'holds': count_holds(
                self.hittables, orphaned_tail=OrphanedNotes.DROP_ORPHAN
            ),
            'rolls': count_rolls(
                self.hittables, orphaned_tail=OrphanedNotes.DROP_ORPHAN
            ),
            'lifts': count_steps(
                self.hittables,
                include_note_types=frozenset((NoteType.LIFT,)),
                same_beat_notes=SameBeatNotes.KEEP_SEPARATE
            ),
            'fakes': count_steps(
                self.notes,
                include_note_types=frozenset((NoteType.FAKE,)),
                same_beat_notes=SameBeatNotes.KEEP_SEPARATE
            ),
        }
    
    def get_density_graph(self) -> list:
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
        start_t = self.engine.time_at(Beat(0))
        deferred_count = 0 # count of notes not put in the graph yet
        for i, count in enumerate(self.notes_per_measure):
            end_beat = Beat((i + 1) * 4)
            end_t = self.engine.time_at(end_beat)
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
        beat = Beat(len(self.notes_per_measure) * 4)
        time = self.engine.time_at(beat)
        append_point(time, 0)

        # add 0 nps point at *very* end of song:
        chart_len = self.song_analyzer.chart_len
        if chart_len > nps_data[-1][0] + 0.1:
            append_point(chart_len, 0)
        
        return nps_data
    
    def get_stream_info(self) -> dict:
        # calculate the bpm of each measure based on the measure's duration
        measure_bpms = []
        num_measures = self.last_note_beat // 4 + 1
        start_t = self.engine.time_at(Beat(0))
        for i in range(num_measures):
            end_beat = Beat((i + 1) * 4)
            end_t = self.engine.time_at(end_beat)
            measure_len = end_t - start_t
            if measure_len != 0:
                measure_bpms.append(240 / measure_len) # convert length to bpm
            else:
                # fallback to avoid division by 0
                measure_bpms.append(0)
            start_t = end_t
        
        # try to build up stream runs for all the following quants
        quants = (32, 24, 20, 16)
        stream_runs = {q: [] for q in quants}
        # keep track of measure bpms ourselves (i'd like to not rely on 
        # displaybpm, see e.g. "Stamina RPG 7 - FE/Burning Throb")
        min_bpm = {q: None for q in quants}
        max_bpm = {q: None for q in quants}
        for i, (count, bpm) in enumerate(zip_longest(
            self.notes_per_measure, measure_bpms, fillvalue=0
        )):
            for q in quants:
                if count >= q:
                    # this is a stream measure
                    runs = stream_runs[q]
                    # can we extend the last stream run to include
                    # this measure?
                    if runs and runs[-1].start + runs[-1].len == i:
                        runs[-1].len += 1
                    # if not, create a new stream run
                    else:
                        runs.append(StreamRun(i, 1))
                    
                    if min_bpm[q] is None:
                        # neither min_bpm nor max_bpm has been populated
                        # yet; populate them now
                        min_bpm[q] = bpm
                        max_bpm[q] = bpm
                    else:
                        min_bpm[q] = min(min_bpm[q], bpm)
                        max_bpm[q] = max(max_bpm[q], bpm)
        
        # figure out what quant to use for the breakdown.
        # similar to zmod, this will be the first of (32nds, 24ths, 20ths) 
        # whose total density (including breaks before/after all stream runs)
        # is at least 20%, or 16ths if none of the previous quants' breakdowns
        # were dense enough.
        for q in quants:
            total_stream = sum(run.len for run in stream_runs[q])
            entire_chart_density = total_stream / num_measures
            if entire_chart_density >= 0.2:
                break
        # since variables in python for loops persist after the loop ends,
        # q and total_stream should now contain the correct values for the
        # desired quant.

        # segments shall be a list of numeric values representing stream
        # and break segments (positive for stream, negative for break).
        # segment lengths are measured in original chart measures (quant
        # adjustment will happen in the views).
        # consecutive positive values imply a 1 measure break in between
        segments = []
        runs = stream_runs[q]
        for i in range(len(runs)):
            if i > 0:
                # add break segment
                break_start = runs[i - 1].start + runs[i - 1].len
                break_end = runs[i].start
                break_len = break_end - break_start
                if break_len > 1:
                    segments.append(-break_len)
            # add stream segment
            segments.append(runs[i].len)
        
        # number of measures in the chart, disregarding breaks before
        # first run and after last run
        if runs:
            adj_measure_count = (runs[-1].start + runs[-1].len) - runs[0].start
        else:
            adj_measure_count = 0
        total_break = adj_measure_count - total_stream

        return {
            'segments': segments,
            'quant': q,
            'bpms': [min_bpm[q], max_bpm[q]],
            'total_stream': total_stream,
            'total_break': total_break
        }




        
        
