import Fraction from "fraction.js";
import { MSDRecord } from "./msd";
import { NoteType, NoteTypes, Note, NoteWithTail } from "./Note";
import {
  parseBPMs,
  parseDelays,
  parseFakes,
  parseScrolls,
  parseSpeeds,
  parseStops,
  parseTimeSignatures,
  parseWarps,
  strToFloat,
  strToInt,
} from "./field-parsing";
import {
  BPMSegment,
  StopSegment,
  DelaySegment,
  WarpSegment,
  SpeedSegment,
  ScrollSegment,
  FakeSegment,
  TimeSignatureSegment,
} from "./TimingSegment";
// import { BeatValues } from "./field-parsing";

const acceptedNoteTypes: string[] = Object.values(NoteTypes);

type Difficulty = 0 | 1 | 2 | 3 | 4 | 5;

const DIFFICULTY_MAPPING: Record<string, Difficulty> = {
  beginner: 0,
  easy: 1,
  medium: 2,
  hard: 3,
  challenge: 4,
  edit: 5,
};

const OLD_STYLE_DIFFICULTY_MAPPING: Record<string, Difficulty> = {
  beginner: 0,
  easy: 1,
  basic: 1,
  light: 1,
  medium: 2,
  another: 2,
  trick: 2,
  standard: 2,
  difficult: 2,
  hard: 3,
  ssr: 3,
  maniac: 3,
  heavy: 3,
  challenge: 4,
  smaniac: 4,
  expert: 4,
  oni: 4,
  edit: 5,
};

function difficultyStrToInt(
  diff: string,
  description: string,
  meter: number
): Difficulty {
  diff = diff.trim().toLowerCase();
  let ret = OLD_STYLE_DIFFICULTY_MAPPING[diff];
  if (ret !== undefined) return ret;
  // resolve invalid difficulty according to Steps::TidyUpData()
  ret = DIFFICULTY_MAPPING[description];
  if (ret !== undefined) return ret;
  else if (meter == 1) return 0; // beginner
  else if (meter <= 3) return 1; // easy
  else if (meter <= 6) return 2;
  return 3; // hard
}

function meterStrToInt(meter: string): number {
  return strToInt(meter);
}

export class Chart {
  stepsType: string;
  description: string;
  difficulty: Difficulty;
  meter: number;
  props: MSDRecord;
  notes: string;

  offset?: number;
  bpms?: BPMSegment[];
  stops?: StopSegment[];
  delays?: DelaySegment[];
  warps?: WarpSegment[];
  speeds?: SpeedSegment[];
  scrolls?: ScrollSegment[];
  fakes?: FakeSegment[];
  timeSignatures?: TimeSignatureSegment[];
  // displayBPM: [number, number] | "?" | undefined;

  constructor(props: MSDRecord, format: "sm" | "ssc") {
    if (format === "ssc") {
      this.props = props;
      this.notes = props.NOTES?.[0] ?? props.NOTES2?.[0];
      if (!this.notes) throw Error("NOTES or NOTES2 property not given");
      this.stepsType = props.STEPSTYPE?.[0].toLowerCase() ?? "";
      // apparently for SSC versions prior to 0.74, #DESCRIPTION
      // should be assigned to the chart name instead of the description field?
      // (see SetDescription() in NotesLoaderSSC.cpp in SM source code)
      // ignoring this since it seems like an extreme edge case we don't need
      // to care about
      this.description = props.DESCRIPTION?.[0].trim() ?? "";
      this.meter = meterStrToInt(props.METER?.[0] ?? "");
      this.difficulty = difficultyStrToInt(
        props.DIFFICULTY?.[0] ?? "",
        this.description,
        this.meter
      );

      if (props.OFFSET !== undefined) this.offset = strToFloat(props.OFFSET[0]);
      if (props.BPMS !== undefined)
        this.bpms = parseBPMs(props.BPMS[0], format);
      if (props.STOPS !== undefined)
        this.stops = parseStops(props.STOPS[0], format);
      if (props.DELAYS !== undefined)
        this.delays = parseDelays(props.DELAYS[0]);
      if (props.TIMESIGNATURES !== undefined)
        this.timeSignatures = parseTimeSignatures(props.TIMESIGNATURES[0]);
      if (props.WARPS !== undefined)
        // note: the ssc version that introduced split timing also made warps relative,
        // so warps specified in split timing will always be relative; thus we can
        // just pass the latest ssc version into this function to get relative warps
        this.warps = parseWarps(props.WARPS[0], 0.83);
      if (props.SPEEDS !== undefined)
        this.speeds = parseSpeeds(props.SPEEDS[0]);
      if (props.SCROLLS !== undefined)
        this.scrolls = parseScrolls(props.SCROLLS[0]);
      if (props.FAKES !== undefined) this.fakes = parseFakes(props.FAKES[0]);
    } else {
      // format === "sm"
      this.props = props;
      const notedata = props.NOTES ?? props.NOTES2;
      if (!notedata) throw Error("NOTES or NOTES2 property not given");
      if (notedata.length < 6)
        throw Error("not enough values in NOTES property");
      // notedata = [stepsType, desc, diff, meter, radarVals, notes]
      this.stepsType = notedata[0].trim();
      this.description = notedata[1].trim();
      this.meter = meterStrToInt(notedata[3]);
      this.difficulty = difficultyStrToInt(
        notedata[2].trim(),
        this.description,
        this.meter
      );
      this.notes = notedata[5];
    }
  }

  getNumColumns(): number {
    switch (this.stepsType) {
      case "dance-single":
        return 4;
      case "dance-double":
        return 8;
      default:
        throw Error("unsupported steps type");
    }
  }

  *notesIterator(): Generator<Note, void> {
    const numCols = this.getNumColumns();
    for (const [measureIdx, measure] of this.notes.split(",").entries()) {
      const measureLines = measure
        .split("\n")
        .map((l) => l.replace(/^[\r\n\t]+|[\r\n\t]+$/g, "")) // trim whitespace
        .filter((l) => l.length > 0); // filter out empty lines
      const numLines = measureLines.length;

      for (const [lineIdx, line] of measureLines.entries()) {
        // TODO: handle keysounds
        for (let c = 0; c < Math.min(numCols, line.length); c++) {
          const chr = line[c];
          if (acceptedNoteTypes.includes(chr))
            yield {
              beat: new Fraction(
                measureIdx * 4 * numLines + lineIdx * 4,
                numLines
              ),
              column: c,
              noteType: chr as NoteType,
            };
        }
      }
    }
  }

  *notesWithTailIterator(): Generator<NoteWithTail, void> {
    const numCols = this.getNumColumns();
    // for each column, stores any hold/roll note currently awaiting its tail
    const incompleteHolds: (Note | null)[] = new Array(numCols).fill(null);
    const buffer: NoteWithTail[] = [];

    function* flushUntilNextIncompleteHold() {
      while (buffer.length > 0) {
        const note = buffer[0];
        if (
          note.noteType === NoteTypes.HOLD_HEAD ||
          note.noteType === NoteTypes.ROLL_HEAD
        ) {
          if (note.tailBeat !== undefined) {
            // matching tail was found for this hold
            yield buffer.shift()!;
          } else if (incompleteHolds[note.column] !== note) {
            // if this hold is incomplete yet not in incompleteHolds,
            // then this is an orphaned hold head; discard
            buffer.shift();
            continue;
          } else {
            // we're still looking for the tail for this hold,
            // stop the flush for now
            break;
          }
        } else {
          // normal note
          yield buffer.shift()!;
        }
      }
    }

    for (const note of this.notesIterator()) {
      const { column, noteType } = note;

      if (
        noteType === NoteTypes.HOLD_HEAD ||
        noteType === NoteTypes.ROLL_HEAD
      ) {
        // we need to keep this hold/roll until we match it with a tail.
        // set it as the currently incomplete hold for its column
        // (we can throw away any incomplete hold that was previously there)
        incompleteHolds[column] = note;
        buffer.push(note);
        // we modified incompleteHolds; try flushing in case that orphaned
        // hold head was blocking the buffer
        yield* flushUntilNextIncompleteHold();
      } else if (noteType === NoteTypes.TAIL) {
        // try matching it with a hold head
        if (incompleteHolds[column] !== null) {
          // if matched, convert the held note to a NoteWithTail
          const hold: NoteWithTail = incompleteHolds[column];
          hold.tailBeat = note.beat;
          incompleteHolds[column] = null;
          // we matched a hold head; try flushing
          yield* flushUntilNextIncompleteHold();
        }
        // if there is no matching head (orphan tail), discard the tail
      } else {
        if (buffer.length > 0) buffer.push(note);
        // skip the buffer if it's empty
        else yield note;
      }
    }

    // there are no more notes; any hold heads left in incompleteHolds
    // are orphans. set all entries to null so that flushUntilNextIncompleteHold
    // can recognize them as orphans
    incompleteHolds.fill(null);
    // empty the buffer
    yield* flushUntilNextIncompleteHold();
  }
}
