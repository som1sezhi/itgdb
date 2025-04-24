import { Chart } from "./Chart";
import { MSDRecord, parseMSD } from "./parseMSD";

export class Simfile {
  charts: Chart[] = [];

  constructor(data: string, format: 'ssc') {
    const msd = parseMSD(data);

    if (format === 'ssc') {
      const simfileProps: MSDRecord = {};
      let curChartProps: MSDRecord | null = null;
      for (const param of msd) {
        // note: parseMSD guarantees that param.length > 0,
        // so we don't have to handle that case
        const key = param[0].toUpperCase();
        const value = param.slice(1);
        if (key === "NOTEDATA") {
          // finalize current chart
          if (curChartProps)
            this.charts.push(new Chart(curChartProps));
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
      if (curChartProps)
        this.charts.push(new Chart(curChartProps));
    }
  }
}
