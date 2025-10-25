import { TimingData } from "./TimingData";
import { WarpSegment } from "./TimingSegment";
import {
  beatToRow,
  beatToRowUnrounded,
  findLessOrEqual,
  rowsToTime,
} from "./utils";

// this is basically a port of simfile.timing.engine

const EventTypes = {
  WARP: 0,
  WARP_END: 1,
  BPM: 2,
  DELAY: 3,
  DELAY_END: 4,
  STOP: 5,
  STOP_END: 6,
} as const;

type EventType = (typeof EventTypes)[keyof typeof EventTypes];

interface TimingEvent {
  row: number;
  type: EventType;
  value: number;
}

interface TimingState {
  event: TimingEvent;
  bpm: number;
  time: number;
  warp: boolean;
}

// merge overlapping warps together, to ensure alternating warpStart and warpEnd
// events in order
function warpsToEventArrays(warps: WarpSegment[]): TimingEvent[][] {
  const warpStarts: TimingEvent[] = [];
  const warpEnds: TimingEvent[] = [];
  for (const warp of warps) {
    const start = warp.row;
    const end = start + warp.lenRows;
    const lastWarpEnd =
      warpEnds.length > 0 ? warpEnds[warpEnds.length - 1].row : -1;
    if (start > lastWarpEnd) {
      // no overlap with the last warp; add this warp
      warpStarts.push({ row: start, type: EventTypes.WARP, value: 0 });
      warpEnds.push({ row: end, type: EventTypes.WARP_END, value: 0 });
    } else if (end > lastWarpEnd) {
      // merge this warp by extending the previous warp
      warpEnds[warpEnds.length - 1].row = end;
    }
    // otherwise, this warp is completely inside the previous warp
    // and we can skip it
  }
  return [warpStarts, warpEnds];
}

function mergeEventArrays(arrs: TimingEvent[][]): TimingEvent[] {
  const idxs = Array(arrs.length).fill(0);
  const lengths = arrs.map((a) => a.length);
  const merged: TimingEvent[] = [];
  while (!idxs.every((idx, i) => idx === lengths[i])) {
    let earliestArrIdx = -1;
    let earliestRow = -1;
    for (let i = 0; i < arrs.length; i++) {
      if (idxs[i] < lengths[i]) {
        const event = arrs[i][idxs[i]];
        if (earliestRow === -1 || event.row < earliestRow) {
          earliestArrIdx = i;
          earliestRow = event.row;
        }
      }
    }
    const event = arrs[earliestArrIdx][idxs[earliestArrIdx]];
    merged.push(event);
    idxs[earliestArrIdx]++;
  }
  return merged;
}

// get time elapsed between state and an event with the
// given type at the given row
function timeUntil(state: TimingState, row: number, type: EventType): number {
  let time = 0;
  if (!state.warp) {
    time += rowsToTime(row - state.event.row, state.bpm);
  }
  if (
    (state.event.type === EventTypes.DELAY && type === EventTypes.DELAY_END) ||
    (state.event.type === EventTypes.STOP && type === EventTypes.STOP_END)
  ) {
    time += state.event.value;
  }
  return time;
}

export class TimingEngine {
  timingData: TimingData;
  timingStates: TimingState[];

  constructor(timingData: TimingData) {
    this.timingData = timingData;

    const timingEventArrs = warpsToEventArrays(timingData.warps);
    timingEventArrs.push(
      timingData.bpms.slice(1).map((seg) => ({
        row: seg.row,
        type: EventTypes.BPM,
        value: seg.value,
      })),
      timingData.delays.map((seg) => ({
        row: seg.row,
        type: EventTypes.DELAY,
        value: seg.value,
      })),
      timingData.delays.map((seg) => ({
        row: seg.row,
        type: EventTypes.DELAY_END,
        value: seg.value,
      })),
      timingData.stops.map((seg) => ({
        row: seg.row,
        type: EventTypes.STOP,
        value: seg.value,
      })),
      timingData.stops.map((seg) => ({
        row: seg.row,
        type: EventTypes.STOP_END,
        value: seg.value,
      }))
    );
    const timingEvents = mergeEventArrays(timingEventArrs);

    this.timingStates = this.generateTimingStates(timingEvents);
  }

  private generateTimingStates(timingEvents: TimingEvent[]): TimingState[] {
    let bpm = this.timingData.bpms[0].value;
    let time = -this.timingData.offset;
    let warp = false;

    const states: TimingState[] = [
      {
        event: { row: 0, type: EventTypes.BPM, value: bpm },
        bpm,
        time,
        warp,
      },
    ];

    for (const event of timingEvents) {
      time += timeUntil(states[states.length - 1], event.row, event.type);
      if (event.type === EventTypes.WARP) warp = true;
      else if (event.type === EventTypes.WARP_END) warp = false;
      else if (event.type === EventTypes.BPM) bpm = event.value;
      states.push({ event, bpm, time, warp });
    }

    return states;
  }

  private getLastStateByRow(row: number, eventType: EventType) {
    const idx = findLessOrEqual(
      this.timingStates,
      [row, eventType],
      (state) => [state.event.row, state.event.type],
      (a, b) => a[0] < b[0] && a[1] < b[1]
    );
    return Math.max(0, idx);
  }

  /**
   * Gets the time at which a note placed at the given beat would
   * need to be hit.
   */
  timeAt(beat: number): number {
    const row = beatToRowUnrounded(beat);
    const lastStateIdx = this.getLastStateByRow(row, EventTypes.STOP);
    const lastState = this.timingStates[lastStateIdx];
    let time = lastState.time;
    time += timeUntil(lastState, row, EventTypes.STOP);
    return time;
  }

  /**
   * Returns true if a note placed at `beat` (rounded to nearest row)
   * would be hittable.
   * */
  hittable(beat: number): boolean {
    const row = beatToRow(beat);
    const lastStateIdx = this.getLastStateByRow(row, EventTypes.STOP_END);
    const lastState = this.timingStates[Math.max(0, lastStateIdx)];

    if (!lastState.warp) return true;

    const type = lastState.event.type;
    return (
      (type === EventTypes.STOP_END || type === EventTypes.DELAY_END) &&
      row == lastState.event.row
    );
  }
}
