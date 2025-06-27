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

interface TimingSegment {
  beat: number;
}

interface TimingSegmentWithValue extends TimingSegment {
  value: number;
}

export type BPMSegment = TimingSegmentWithValue;
export type StopSegment = TimingSegmentWithValue;
export type DelaySegment = TimingSegmentWithValue;
export type WarpSegment = TimingSegmentWithValue;
export interface SpeedSegment extends TimingSegment {
  ratio: number;
  delay: number;
  unit: "beats" | "seconds";
}
export type ScrollSegment = TimingSegmentWithValue;
export type FakeSegment = TimingSegmentWithValue;
export interface TimeSignatureSegment extends TimingSegment {
  numerator: number;
  denominator: number;
}

export function parseBPMs(
  str: string | undefined,
  format: "sm" | "ssc"
): BPMSegment[] {
  const ret = parseBeatValues(str)
    .filter(([beat, value]) => {
      if (format === "ssc") return beat >= 0 || value > 0;
      else return value !== 0; // just skip 0bpm segments for .sm files
    })
    .map(([beat, value]) => ({ beat, value }));
  if (ret.length === 0) ret.push({ beat: 0, value: 60 });
  if (ret[0].beat !== 0) ret[0].beat = 0;
  return ret;
}

export function parseStops(
  str: string | undefined,
  format: "sm" | "ssc"
): StopSegment[] {
  return parseBeatValues(str)
    .filter(([beat, value]) => {
      if (format === "ssc") return beat >= 0 || value > 0;
      else return value !== 0; // just skip 0-len segments for .sm files
    })
    .map(([beat, value]) => ({ beat, value }));
}

export function parseDelays(str: string | undefined): DelaySegment[] {
  return parseBeatValues(str)
    .filter(([, value]) => value > 0) // positive-length delays only
    .map(([beat, value]) => ({ beat, value }));
}

export function parseWarps(
  str: string | undefined,
  sscVersion: number
): WarpSegment[] {
  // NOTE: SSC versions before 0.7 specify warps in terms of absolute beats,
  // not relative
  const isAbsolute = sscVersion < 0.7;
  return parseBeatValues(str)
    .filter(([beat, value]) => (isAbsolute ? value > beat : value > 0))
    .map(([beat, value]) =>
      isAbsolute ? { beat, value: value - beat } : { beat, value }
    );
}

export function parseSpeeds(str: string | undefined): SpeedSegment[] {
  const ret = splitBeatValues(str)
    .filter((item) => item.length === 3 || item.length === 4)
    .map((item) => [
      strToFloat(item[0]),
      strToFloat(item[1]),
      strToFloat(item[2]),
      item.length === 4 ? strToInt(item[3]) : 0,
    ])
    .filter(([beat, , delay]) => beat >= 0 && delay >= 0)
    .map(([beat, ratio, delay, unit]) => ({
      beat,
      ratio,
      delay,
      unit: (unit === 0 ? "beats" : "seconds") as "beats" | "seconds",
    }));
  if (ret.length === 0)
    ret.push({ beat: 0, ratio: 1, delay: 0, unit: "beats" });
  return ret;
}

export function parseScrolls(str: string | undefined): ScrollSegment[] {
  const ret = splitBeatValues(str)
    .filter((item) => item.length >= 2)
    .map((item) => [strToFloat(item[0]), strToFloat(item[1])])
    .filter(([beat]) => beat >= 0)
    .map(([beat, value]) => ({ beat, value }));
  if (ret.length === 0) ret.push({ beat: 0, value: 1 });
  return ret;
}

export function parseFakes(str: string | undefined): FakeSegment[] {
  return parseBeatValues(str)
    .filter(([, value]) => value > 0)
    .map(([beat, value]) => ({ beat, value }));
}

export function parseTimeSignatures(
  str: string | undefined
): TimeSignatureSegment[] {
  const ret = splitBeatValues(str)
    .filter((item) => item.length >= 3)
    .map((item) => [strToFloat(item[0]), strToInt(item[1]), strToInt(item[2])])
    .filter(([beat, num, denom]) => beat >= 0 && num >= 1 && denom >= 1)
    .map(([beat, numerator, denominator]) => ({
      beat,
      numerator,
      denominator,
    }));
  if (ret.length === 0) ret.push({ beat: 0, numerator: 4, denominator: 4 });
  return ret;
}
