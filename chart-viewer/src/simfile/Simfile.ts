import { Chart } from "./Chart";
import {
  BPMSegment,
  DelaySegment,
  FakeSegment,
  parseBPMs,
  parseDelays,
  parseFakes,
  parseScrolls,
  parseSpeeds,
  parseStops,
  parseTimeSignatures,
  parseWarps,
  ScrollSegment,
  SpeedSegment,
  StopSegment,
  strToFloat,
  TimeSignatureSegment,
  WarpSegment,
} from "./field-parsing";
// import { BeatValues } from "./field-parsing";
import { MSDRecord, parseMSD } from "./msd";

export class Simfile {
  charts: Chart[] = [];

  offset: number;
  bpms: BPMSegment[];
  stops: StopSegment[];
  delays: DelaySegment[];
  warps: WarpSegment[];
  speeds: SpeedSegment[];
  scrolls: ScrollSegment[];
  fakes: FakeSegment[];
  timeSignatures: TimeSignatureSegment[];
  // displayBPM: [number, number] | "?" | undefined;
  lastSecondHint: number | undefined;

  constructor(data: string, format: "sm" | "ssc") {
    const msd = parseMSD(data);
    const simfileProps: MSDRecord = {};

    if (format === "ssc") {
      let curChartProps: MSDRecord | null = null;

      for (const param of msd) {
        // note: parseMSD guarantees that param.length > 0,
        // so we don't have to handle that case
        const key = param[0].toUpperCase();
        const value = param.slice(1);
        if (key === "NOTEDATA") {
          // finalize current chart
          if (curChartProps) this.charts.push(new Chart(curChartProps, "ssc"));
          // start new chart
          curChartProps = {};
        } else if (curChartProps) {
          // we are under a #NOTEDATA, so add prop to current chart
          curChartProps[key] = value;
        } else {
          // add prop to simfile itself
          simfileProps[key] = value;
        }
      }
      // finalize last chart
      if (curChartProps) this.charts.push(new Chart(curChartProps, "ssc"));

      // set ssc-only timing data
      const sscVersion = strToFloat(simfileProps.VERSION?.[0] ?? "0.83");
      this.warps = parseWarps(simfileProps.WARPS?.[0], sscVersion);
      this.speeds = parseSpeeds(simfileProps.SPEEDS?.[0]);
      this.scrolls = parseScrolls(simfileProps.SCROLLS?.[0]);
      this.fakes = parseFakes(simfileProps.FAKES?.[0]);
    } else {
      // format === "sm"

      for (const param of msd) {
        // note: parseMSD guarantees that param.length > 0,
        // so we don't have to handle that case
        let key = param[0].toUpperCase();
        const value = param.slice(1);
        if (key === "FREEZES") key = "STOPS"; // alias FREEZES to STOPS
        if (key === "NOTES" || key === "NOTES2") {
          if (value.length < 6) continue; // if not enough fields, skip
          const curChartProps = {
            [key]: value,
          };
          this.charts.push(new Chart(curChartProps, "sm"));
        } else {
          // add prop to simfile itself
          simfileProps[key] = value;
        }
      }

      // set ssc-only timing data to default values by passing in undefined
      this.warps = parseWarps(undefined, 0.83);
      this.speeds = parseSpeeds(undefined);
      this.scrolls = parseScrolls(undefined);
      this.fakes = parseFakes(undefined);
    }

    this.offset = strToFloat(simfileProps.OFFSET?.[0] ?? "0");
    this.bpms = parseBPMs(simfileProps.BPMS?.[0], format);
    this.stops = parseStops(simfileProps.STOPS?.[0], format);
    this.delays = parseDelays(simfileProps.DELAYS?.[0]);
    this.timeSignatures = parseTimeSignatures(simfileProps.TIMESIGNATURES?.[0]);

    // TODO: for sm files, process negative bpms
  }
}
