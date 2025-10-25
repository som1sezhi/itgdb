import { Chart } from "./Chart";
import { Simfile } from "./Simfile";
import {
  BPMSegment,
  DelaySegment,
  StopSegment,
  WarpSegment,
} from "./TimingSegment";

// if any of these tags are present in the chart, use chart timing
const CHART_TIMING_PROPS = [
  "BPMS",
  "STOPS",
  "DELAYS",
  "TIMESIGNATURES",
  "TICKCOUNTS",
  "COMBOS",
  "WARPS",
  "SPEEDS",
  "SCROLLS",
  "FAKES",
  "LABELS",
];

export class TimingData {
  offset: number;
  bpms: BPMSegment[];
  stops: StopSegment[];
  delays: DelaySegment[];
  warps: WarpSegment[];

  constructor(sim: Simfile, chart?: Chart) {
    let useChartTiming = chart !== undefined && (sim.sscVersion ?? 0) >= 0.7;
    useChartTiming &&= CHART_TIMING_PROPS.some(
      (prop) => chart?.props[prop] !== undefined
    );

    if (useChartTiming) {
      this.offset = chart!.offset ?? sim.offset;
      this.bpms = chart!.bpms ?? [new BPMSegment(0, 60)];
      this.stops = chart!.stops ?? [];
      this.delays = chart!.delays ?? [];
      this.warps = chart!.warps ?? [];
      // TODO: if chart timing is "empty" (see Steps::GetTimingData(),
      // TimingData::empty()), use song timing instead

      // TODO: account for the fact that TimingData::TidyUpData() does not
      // populate empty fields if steps timing is given, while our parse functions
      // perform tidying up
    } else {
      this.offset = sim.offset;
      this.bpms = sim.bpms;
      this.stops = sim.stops;
      this.delays = sim.delays;
      this.warps = sim.warps;
    }
  }
}
