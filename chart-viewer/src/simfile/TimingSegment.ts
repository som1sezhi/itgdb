import { findGreaterThan } from "./utils";

const ROWS_PER_BEAT = 48;
function beatToRow(beat: number): number {
  return Math.round(beat * ROWS_PER_BEAT);
}
function rowToBeat(row: number): number {
  return row / ROWS_PER_BEAT;
}

// matches TimingSegment::AreEqual()
function almostEqual(a: number, b: number): boolean {
  return Math.abs(a - b) < 1e-6;
}

/**
 * - "row" -> effect only happens on a single row
 * - "range" -> effect applies to a range of rows
 * - "indefinite" -> effect applies until the next segment
 */
export type SegmentEffectType = "row" | "range" | "indefinite";

export abstract class TimingSegment {
  row: number;

  constructor(beat: number) {
    this.row = beatToRow(beat);
  }

  getBeat(): number {
    return rowToBeat(this.row);
  }

  abstract getEffectType(): SegmentEffectType;
  abstract isNotable(): boolean;
  abstract isEqual(other: this): boolean;
}

export abstract class TimingSegmentWithValue extends TimingSegment {
  constructor(beat: number, public value: number) {
    super(beat);
  }
  isEqual(other: this): boolean {
    return almostEqual(this.value, other.value);
  }
}

export abstract class TimingSegmentWithLength extends TimingSegment {
  lenRows: number;

  constructor(beat: number, lenBeats: number) {
    super(beat);
    this.lenRows = beatToRow(lenBeats);
  }
  getEffectType = (): SegmentEffectType => "range";
  isNotable = () => this.lenRows > 0;
  isEqual(other: this): boolean {
    return this.lenRows == other.lenRows;
  }
}

export class BPMSegment extends TimingSegmentWithValue {
  getEffectType = (): SegmentEffectType => "indefinite";
  isNotable = () => true;
}

export class StopSegment extends TimingSegmentWithValue {
  getEffectType = (): SegmentEffectType => "row";
  isNotable = () => this.value > 0;
}

export class DelaySegment extends TimingSegmentWithValue {
  getEffectType = (): SegmentEffectType => "row";
  isNotable = () => this.value > 0;
}

export class WarpSegment extends TimingSegmentWithLength {}

export class SpeedSegment extends TimingSegment {
  constructor(
    beat: number,
    public ratio: number,
    public delay: number,
    public unit: "beats" | "seconds"
  ) {
    super(beat);
  }
  getEffectType = (): SegmentEffectType => "indefinite";
  isNotable = () => true;
  isEqual(other: this): boolean {
    return (
      almostEqual(this.ratio, other.ratio) &&
      almostEqual(this.delay, other.delay) &&
      this.unit === other.unit
    );
  }
}

export class ScrollSegment extends TimingSegmentWithValue {
  getEffectType = (): SegmentEffectType => "indefinite";
  isNotable = () => true;
}

export class FakeSegment extends TimingSegmentWithLength {}

export class TimeSignatureSegment extends TimingSegment {
  constructor(beat: number, public upper: number, public lower: number) {
    super(beat);
  }
  getEffectType = (): SegmentEffectType => "indefinite";
  isNotable = () => true;
  isEqual(other: this): boolean {
    return this.upper === other.upper && this.lower === other.lower;
  }
}

/**
 * Given an array of TimingSegments in order of insertion/creation, return an
 * array that matches the result of repeatedly inserting segments using
 * TimingData::AddSegment() in SM. This involves sorting and removing non-
 * consequential and redundant segments.
 */
export function cleanUpSegments<T extends TimingSegment>(segs: T[]): T[] {
  if (segs.length === 0) return segs;

  const newSegs: T[] = [];
  const effectType = segs[0].getEffectType();

  for (const seg of segs) {
    if (newSegs.length === 0) {
      newSegs.push(seg);
      continue;
    }

    const insertIdx = findGreaterThan(newSegs, seg.row, (s) => s.row);
    const idx = Math.max(0, insertIdx - 1);
    const curSeg = newSegs[idx];
    const isNotable = seg.isNotable();
    const isOverwriting = seg.row === curSeg.row;

    if (!isNotable && !isOverwriting) continue;

    if (effectType !== "indefinite") {
      // effectType is "row" or "range"
      // are we overwriting a seg with a non-notable seg?
      if (isOverwriting && !isNotable) {
        newSegs.splice(idx, 1); // just delete the old seg
        continue;
      }
    } else {
      // effectType is "indefinite", so we need to worry about
      // cleaning up redundant segments
      const wantOverwrite = isOverwriting && idx > 0;
      const prevSeg = wantOverwrite ? newSegs[idx - 1] : curSeg;
      if (seg.row < curSeg.row) {
        // special case: this segment should go first, before curSeg,
        // so really curSeg should be treated as the next segment.
        // this check is not in SM but i added it here for more robustness
        if (seg.isEqual(curSeg)) {
          // move nextSeg to this row
          curSeg.row = seg.row;
          continue;
        }
      } else if (idx < newSegs.length - 1) {
        // check seg after this one to see if it will become redundant
        const nextSeg = newSegs[idx + 1];
        if (seg.isEqual(nextSeg)) {
          // nextSeg is redundant
          if (prevSeg.isEqual(seg)) {
            // seg is redundant; delete nextSeg, don't add this seg
            newSegs.splice(idx + 1, 1);
            if (wantOverwrite)
              // curSeg replaced by redundant seg; remove
              newSegs.splice(idx, 1);
            continue;
          } else {
            // move nextSeg to this row
            nextSeg.row = seg.row;
            if (wantOverwrite)
              // curSeg replaced by redundant seg; remove
              newSegs.splice(idx, 1);
            continue;
          }
        } else {
          if (prevSeg.isEqual(seg)) {
            // seg is redundant; don't add this seg
            if (wantOverwrite)
              // curSeg replaced by redundant seg; remove
              newSegs.splice(idx, 1);
            continue;
          }
        }
      } else {
        if (prevSeg.isEqual(seg)) {
          // seg is redundant; don't add this seg
          if (wantOverwrite)
            // curSeg replaced by redundant seg; remove
            newSegs.splice(idx, 1);
          continue;
        }
      }
    }

    if (isOverwriting && curSeg.isEqual(seg)) continue;

    // actually write the seg
    if (isOverwriting) newSegs[idx] = seg;
    else newSegs.splice(insertIdx, 0, seg);
  }

  return newSegs;
}

// notes for future me:
// in SM, Song::ReloadFromSongDir() runs the AddSegment process twice:
// - once from the initial simfile parse
// - once via TimingData::Copy(), called from copy assignment of the Song
//   from the line `*this = copy;` below `copy.RemoveAutoGenNotes();`
// between these two processes, TimingData::TidyUpData() is called.
//
// an example of how this can change the result:
// e.g. #BPMS:5.0=161.00,10.0=165.0,0.0=165.0;
// 1st pass: (5, 161), (0, 165)
// TidyUpData: (0, 161), (0, 165)
// 2nd pass: (0, 165)
// idk if this is a bug or just running up against unsupported behavior due
// to inserting segments out of order, but i added a condition to handle these
// cases just in case
