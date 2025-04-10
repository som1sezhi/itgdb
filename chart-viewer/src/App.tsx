import { useEffect, useRef } from "react";
import "./App.css";
import { parseMSD } from "./simfile/parseMSD";
import { Application, extend } from "@pixi/react";
import { Container, Graphics, Sprite } from "pixi.js";
import { Playfield } from "./components/playfield/Playfield";

extend({
  Container,
  Graphics,
  Sprite,
});

function App({ simfileURL }: { simfileURL: string }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    fetch(simfileURL)
      .then((res) => res.text())
      .then((text) => {
        console.log(parseMSD(text));
      });
  }, [simfileURL]);

  return (
    <>
      <div id="top-bar">hello</div>
      <div id="viewport" ref={viewportRef}>
        <Application background="#1099bb" resizeTo={viewportRef}>
          <Playfield />
        </Application>
      </div>
    </>
  );
}

export default App;
