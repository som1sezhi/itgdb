import { Chart } from "./Chart";
import {
  parseBPMs,
  parseBPMsPartial,
  parseDelays,
  parseFakes,
  parseScrolls,
  parseSpeeds,
  parseStops,
  parseStopsPartial,
  parseTimeSignatures,
  parseWarps,
  PartiallyProcessedSegment,
  strToFloat,
} from "./field-parsing";
// import { BeatValues } from "./field-parsing";
import { MSDRecord, parseMSD } from "./msd";
import {
  BPMSegment,
  StopSegment,
  DelaySegment,
  WarpSegment,
  SpeedSegment,
  ScrollSegment,
  FakeSegment,
  TimeSignatureSegment,
  cleanUpSegments,
} from "./TimingSegment";

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

    // common to sm and ssc
    // (except for bpms and stops, which are handled differently between sm and ssc)
    this.offset = strToFloat(simfileProps.OFFSET?.[0] ?? "0");
    this.delays = parseDelays(simfileProps.DELAYS?.[0]);
    this.timeSignatures = parseTimeSignatures(simfileProps.TIMESIGNATURES?.[0]);

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

      // set ssc-only timing data (and bpms+stops)
      const sscVersion = strToFloat(simfileProps.VERSION?.[0] ?? "0.83");
      this.bpms = parseBPMs(simfileProps.BPMS?.[0], "ssc");
      this.stops = parseStops(simfileProps.STOPS?.[0], "ssc");
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

      // partial bpm + stops processing
      const bpmVals = parseBPMsPartial(simfileProps.BPMS?.[0], format);
      const stopVals = parseStopsPartial(simfileProps.STOPS?.[0], format);
      // set ssc-only timing data to default values by passing in undefined
      this.speeds = parseSpeeds(undefined);
      this.scrolls = parseScrolls(undefined);
      this.fakes = parseFakes(undefined);

      this.bpms = [];
      this.stops = [];
      this.warps = [];
      // convert negative bpms and stops to warps
      // (this sets this.bpms, this.stops, and this.warps)
      this.smPostProcessBPMsAndStops(bpmVals, stopVals);
    }
  }

  // for .sm files, process negative bpms
  // this is basically a port of SMLoader::ProcessBPMsAndStops()
  // from the SM source code
  private smPostProcessBPMsAndStops(
    bpmVals: PartiallyProcessedSegment[],
    stopVals: PartiallyProcessedSegment[]
  ) {
    // fastest allowable bpm before it gets turned into a warp
    const FAST_BPM_WARP = 9999999;
    let ibpm = 0;
    let istop = 0;
    let curBpm = 0; // current bpm (positive or negative)
    let prevBeat = 0; // beat at which previous timing change occurred
    let warpStart = -1; // start of current warp (-1 if not currently warping)
    let warpEnd = -1; // end of current warp
    let preWarpBpm = 0; // bpm prior to current warp
    let timeOffset = 0; // how far off we have gotten due to negative changes

    // ensure beat order
    bpmVals.sort((a, b) => a.beat - b.beat);
    stopVals.sort((a, b) => a.beat - b.beat);

    // convert stops before beat 0 to song offset nudges instead
    for (const stop of stopVals) {
      if (stop.beat >= 0) break;
      this.offset -= stop.value;
    }

    // ignore bpm changes before beat 0
    for (; ibpm < bpmVals.length; ibpm++) {
      const bpmSeg = bpmVals[ibpm];
      // note the strict greater-than, so that a beat 0 bpm segment will get
      // recorded here
      if (bpmSeg.beat > 0) break;
      curBpm = bpmSeg.value;
    }

    // we are now at beat 0. do we know the bpm?
    if (curBpm === 0) {
      // no; can we use the next bpm value instead?
      if (ibpm === bpmVals.length) {
        // no, default to 60
        curBpm = 60;
      } else {
        // yes, get the next bpm
        // the original SM source code here actually does ibpm++ *before*
        // setting the bpm, which seems like an error. shouldn't ibpm
        // already be pointing to the correct bpm segment?
        // TODO: investigate
        curBpm = bpmVals[ibpm].value;
      }
    }

    // if we're not starting with a warp, add this starting segment
    if (curBpm > 0 && curBpm <= FAST_BPM_WARP) {
      this.bpms.push(new BPMSegment(0, curBpm));
    }

    while (ibpm < bpmVals.length || istop < stopVals.length) {
      // pick either bpm change or stop, depending on which is next
      const changeIsBpm =
        istop == stopVals.length ||
        (ibpm < bpmVals.length && bpmVals[ibpm] <= stopVals[istop]);
      const change = changeIsBpm ? bpmVals[ibpm] : stopVals[istop];

      if (curBpm <= FAST_BPM_WARP) {
        // add time since last change
        timeOffset += ((change.beat - prevBeat) * 60) / curBpm;

        // if we were in a warp but it ended, create the warp segment
        if (warpStart >= 0 && curBpm > 0 && timeOffset > 0) {
          warpEnd = change.beat - (timeOffset * curBpm) / 60;
          this.warps.push(new WarpSegment(warpStart, warpEnd - warpStart));
          // if bpm changed during the warp, place the bpm change
          // at the start of the warp
          if (curBpm != preWarpBpm) {
            this.bpms.push(new BPMSegment(warpStart, curBpm));
          }
          warpStart = -1; // not warping anymore
        }
      }

      // now handle the timing change
      prevBeat = change.beat;
      if (changeIsBpm) {
        if (
          warpStart < 0 &&
          (change.value < 0 || change.value > FAST_BPM_WARP)
        ) {
          // start new warp
          warpStart = change.beat;
          preWarpBpm = curBpm;
          timeOffset = 0;
        } else if (warpStart < 0) {
          // not starting a new warp, and not currently warping;
          // just a regular bpm change
          this.bpms.push(new BPMSegment(change.beat, change.value));
        }
        curBpm = change.value;
        ibpm++;
      } else {
        // this is a stop
        if (warpStart < 0 && change.value < 0) {
          // start new warp
          warpStart = change.beat;
          preWarpBpm = curBpm;
          timeOffset = change.value;
        } else if (warpStart < 0) {
          // not starting a new warp, and not currently warping;
          // just a regular stop
          this.stops.push(new StopSegment(change.beat, change.value));
        } else {
          // we're in a warp; stops affect the time offset directly
          timeOffset += change.value;
          // handle if a stop makes up for all of the time deficit (and then some)
          if (change.value > 0 && timeOffset > 0) {
            // end the warp and stop for the amount it goes over
            warpEnd = change.beat;
            this.warps.push(new WarpSegment(warpStart, warpEnd - warpStart));
            this.stops.push(new StopSegment(change.beat, timeOffset));
            // are we still warping due to bpm?
            if (curBpm < 0 || curBpm > FAST_BPM_WARP) {
              // yes; restart warp
              warpStart = change.beat;
              timeOffset = 0;
            } else {
              // no; end warp, add any bpm change that may have happened in the
              // meantime
              if (curBpm != preWarpBpm) {
                this.bpms.push(new BPMSegment(warpStart, curBpm));
              }
              warpStart = -1;
            }
          }
        }
        istop++;
      }
    }

    // we're at the end; check if we're still warping
    if (warpStart >= 0) {
      // check if this warp will ever end
      if (curBpm < 0 || curBpm > FAST_BPM_WARP) {
        // no; end the chart immediately
        warpEnd = 99999999; // lmao
      } else {
        // yes; calculate when it will end
        warpEnd = prevBeat - (timeOffset * curBpm) / 60;
      }
      this.warps.push(new WarpSegment(warpStart, warpEnd - warpStart));
      // add any bpm change that happened during this warp
      if (curBpm != preWarpBpm) {
        this.bpms.push(new BPMSegment(warpStart, curBpm));
      }
    }

    this.bpms = cleanUpSegments(this.bpms);
    this.stops = cleanUpSegments(this.stops);
    this.warps = cleanUpSegments(this.warps);
  }
}
