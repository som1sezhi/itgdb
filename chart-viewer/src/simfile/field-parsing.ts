import {
  BPMSegment,
  cleanUpSegments,
  DelaySegment,
  FakeSegment,
  ScrollSegment,
  SpeedSegment,
  StopSegment,
  TimeSignatureSegment,
  WarpSegment,
} from "./TimingSegment";

export function strToFloat(str: string): number {
  const num = parseFloat(str);
  return isFinite(num) ? num : 0;
}

export function strToInt(str: string): number {
  const num = parseInt(str, 10);
  return isFinite(num) ? num : 0;
}

function splitBeatValues(str: string | undefined): string[][] {
  if (str === undefined) return [];
  return str.split(",").map((item) => item.split("="));
}

function parseBeatValues(str: string | undefined): [number, number][] {
  return splitBeatValues(str)
    .filter((item) => item.length === 2)
    .map((item) => [strToFloat(item[0]), strToFloat(item[1])]);
}

export interface PartiallyProcessedSegment {
  beat: number;
  value: number;
}

// we separate this part out since .sm parsing uses these partial
// values to convert bpms/stops into warps
export function parseBPMsPartial(
  str: string | undefined,
  format: "sm" | "ssc"
): PartiallyProcessedSegment[] {
  return parseBeatValues(str)
    .filter(([beat, value]) => {
      if (format === "ssc") return beat >= 0 || value > 0;
      else return value !== 0; // just skip 0bpm segments for .sm files
    })
    .map(([beat, value]) => ({ beat, value }));
}

/** note: this function should really only be used for .ssc parsing. */
export function parseBPMs(
  str: string | undefined,
  format: "sm" | "ssc"
): BPMSegment[] {
  const bpmsPartial = parseBPMsPartial(str, format);
  let segs = bpmsPartial.map(({ beat, value }) => new BPMSegment(beat, value));
  segs = cleanUpSegments(segs);
  // match TimingData::TidyUpData()
  if (segs.length === 0) segs.push(new BPMSegment(0, 60));
  if (segs[0].row !== 0) segs[0].row = 0;
  return segs;
}

// we separate this part out since .sm parsing uses these partial
// values to convert bpms/stops into warps
export function parseStopsPartial(
  str: string | undefined,
  format: "sm" | "ssc"
): PartiallyProcessedSegment[] {
  return parseBeatValues(str)
    .filter(([beat, value]) => {
      if (format === "ssc") return beat >= 0 || value > 0;
      else return value !== 0; // just skip 0-len segments for .sm files
    })
    .map(([beat, value]) => ({ beat, value }));
}

/** note: this function should really only be used for .ssc parsing. */
export function parseStops(
  str: string | undefined,
  format: "sm" | "ssc"
): StopSegment[] {
  const segs = parseStopsPartial(str, format).map(
    ({ beat, value }) => new StopSegment(beat, value)
  );
  return cleanUpSegments(segs);
}

export function parseDelays(str: string | undefined): DelaySegment[] {
  const segs = parseBeatValues(str)
    .filter(([, value]) => value > 0) // positive-length delays only
    .map(([beat, value]) => new DelaySegment(beat, value));
  return cleanUpSegments(segs);
}

export function parseWarps(
  str: string | undefined,
  sscVersion: number
): WarpSegment[] {
  // NOTE: SSC versions before 0.7 specify warps in terms of absolute beats,
  // not relative
  const isAbsolute = sscVersion < 0.7;
  const segs = parseBeatValues(str)
    .filter(([beat, value]) => (isAbsolute ? value > beat : value > 0))
    .map(([beat, value]) =>
      isAbsolute
        ? new WarpSegment(beat, value - beat)
        : new WarpSegment(beat, value)
    );
  return cleanUpSegments(segs);
}

export function parseSpeeds(str: string | undefined): SpeedSegment[] {
  let segs = splitBeatValues(str)
    .filter((item) => item.length === 3 || item.length === 4)
    .map((item) => [
      strToFloat(item[0]),
      strToFloat(item[1]),
      strToFloat(item[2]),
      item.length === 4 ? strToInt(item[3]) : 0,
    ])
    .filter(([beat, , delay]) => beat >= 0 && delay >= 0)
    .map(
      ([beat, ratio, delay, unit]) =>
        new SpeedSegment(beat, ratio, delay, unit === 0 ? "beats" : "seconds")
    );
  segs = cleanUpSegments(segs);
  // match TimingData::TidyUpData()
  if (segs.length === 0) segs.push(new SpeedSegment(0, 1, 0, "beats"));
  return segs;
}

export function parseScrolls(str: string | undefined): ScrollSegment[] {
  let segs = splitBeatValues(str)
    .filter((item) => item.length >= 2)
    .map((item) => [strToFloat(item[0]), strToFloat(item[1])])
    .filter(([beat]) => beat >= 0)
    .map(([beat, value]) => new ScrollSegment(beat, value));
  segs = cleanUpSegments(segs);
  // match TimingData::TidyUpData()
  if (segs.length === 0) segs.push(new ScrollSegment(0, 1));
  return segs;
}

export function parseFakes(str: string | undefined): FakeSegment[] {
  const segs = parseBeatValues(str)
    .filter(([, value]) => value > 0)
    .map(([beat, value]) => new FakeSegment(beat, value));
  return cleanUpSegments(segs);
}

export function parseTimeSignatures(
  str: string | undefined
): TimeSignatureSegment[] {
  let segs = splitBeatValues(str)
    .filter((item) => item.length >= 3)
    .map((item) => [strToFloat(item[0]), strToInt(item[1]), strToInt(item[2])])
    .filter(([beat, num, denom]) => beat >= 0 && num >= 1 && denom >= 1)
    .map(([beat, num, denom]) => new TimeSignatureSegment(beat, num, denom));
  segs = cleanUpSegments(segs);
  // match TimingData::TidyUpData()
  if (segs.length === 0) segs.push(new TimeSignatureSegment(0, 4, 4));
  return segs;
}
