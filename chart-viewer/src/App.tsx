import {
  PropsWithChildren,
  useEffect,
  useRef,
  useState,
} from "react";
import "./App.css";
import { Application, extend } from "@pixi/react";
import { Container, Graphics, Sprite } from "pixi.js";
import { Notefield, ScrollSpeed } from "./components/notefield/Notefield";
import { Simfile } from "./simfile/Simfile";
import { NumberInput } from "./components/NumberInput";

extend({
  Container,
  Graphics,
  Sprite,
});

function BarItem({ label, children }: PropsWithChildren<{ label?: string }>) {
  return (
    <div className="bar-item">
      {label ? (
        <label>
          {label}
          {children}
        </label>
      ) : (
        children
      )}
    </div>
  );
}

function App({ simfileURL }: { simfileURL: string }) {
  const [simfile, setSimfile] = useState<Simfile | null>(null);
  const [chartIdx, setChartIdx] = useState<number>(0);
  const [beat, setBeat] = useState<number>(0);
  const [scroll, setScroll] = useState<ScrollSpeed>({
    type: "X",
    value: 2,
  });
  const [mini, setMini] = useState<number>(50);
  const viewportRef = useRef<HTMLDivElement>(null);

  // load simfile
  useEffect(() => {
    fetch(simfileURL)
      .then((res) => res.text())
      .then((text) => {
        const sim = new Simfile(text, "ssc");
        setSimfile(sim);
      });
  }, [simfileURL]);

  return (
    <>
      <div id="top-bar">
        <BarItem>
          <label htmlFor="scroll-input">Scroll:</label>
          <select>
            <option>X</option>
          </select>
          <NumberInput
            id="scroll-input"
            value={scroll.value}
            step={0.5}
            min={0}
            onChange={(value) => setScroll((scroll) => ({ ...scroll, value }))}
          />
        </BarItem>
        <BarItem label="Mini:">
          <NumberInput value={mini} step={5} onChange={setMini} />
        </BarItem>
        <button onClick={() => setBeat(60)}>test button</button>
      </div>
      <div id="viewport" ref={viewportRef}>
        <Application background="#000" resizeTo={viewportRef}>
          <Notefield
            chart={simfile?.charts[chartIdx]}
            beat={beat}
            scroll={scroll}
            mini={mini}
          />
        </Application>
      </div>
      <div id="bottom-bar">
        <BarItem label="Chart:">
          <select
            value={chartIdx}
            onChange={(e) => setChartIdx(Number(e.target.value))}
          >
            {simfile &&
              simfile.charts.map((chart, i) => (
                <option key={i} value={i}>
                  {chart.stepsType} {chart.difficulty} {chart.meter}
                </option>
              ))}
          </select>
        </BarItem>
        <BarItem label="Beat:">
          <NumberInput value={beat} min={0} onChange={setBeat} />
        </BarItem>
      </div>
    </>
  );
}

export default App;
