import Fraction from "fraction.js";
import { MSDRecord } from "./msd";
import { NoteType, NoteTypes, Note, NoteWithTail } from "./Note";

const acceptedNoteTypes: string[] = Object.values(NoteTypes);

export class Chart {
  stepsType: string;
  difficulty: string;
  meter: string;
  props: MSDRecord;
  notes: string;

  constructor(props: MSDRecord) {
    this.props = props;
    this.notes = props.NOTES?.[0] ?? props.NOTES2?.[0];
    if (!this.notes) throw Error("NOTES or NOTES2 property not given");
    this.stepsType = props.STEPSTYPE?.[0] ?? "";
    this.difficulty = props.DIFFICULTY?.[0] ?? "";
    this.meter = props.METER?.[0] ?? "";
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
        if (buffer.length > 0)
          buffer.push(note);
        else
          // skip the buffer if it's empty
          yield note;
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
