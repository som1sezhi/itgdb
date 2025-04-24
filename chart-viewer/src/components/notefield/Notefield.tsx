import { PixiReactElementProps } from "@pixi/react";
import { Sprite } from "pixi.js";
import { useState, useEffect, useMemo, Fragment, useRef } from "react";
import { loadAssets, TextureID, useTexture } from "./useTexture";
import { Chart } from "../../simfile/Chart";
import { NoteType, NoteTypes } from "../../simfile/Note";
import Fraction from "fraction.js";

const BASE_ARROW_SIZE = 64;
const COLUMN_TO_ROTATION = [
  // assumes default rotation is down
  Math.PI / 2,
  0,
  Math.PI,
  -Math.PI / 2,
  Math.PI / 2,
  0,
  Math.PI,
  -Math.PI / 2,
];

export interface ScrollSpeed {
  type: "X" | "C" | "M";
  value: number;
}

function Receptor(props: PixiReactElementProps<typeof Sprite>) {
  const receptorTex = useTexture("receptor");
  return <pixiSprite {...props} anchor={0.5} texture={receptorTex} />;
}

function ReceptorRow({
  numColumns,
  arrowSize,
}: {
  numColumns: 4 | 8;
  arrowSize: number;
}) {
  return (
    <>
      {[...Array(numColumns)].map((_, i) => (
        <Receptor
          key={i}
          x={i * arrowSize}
          y={0}
          rotation={COLUMN_TO_ROTATION[i]}
          width={arrowSize}
          height={arrowSize}
        />
      ))}
    </>
  );
}

const QUANT_TO_TEX_ID: Record<number, TextureID> = {
  [4]: "tap4",
  [8]: "tap8",
  [12]: "tap12",
  [16]: "tap16",
  [24]: "tap24",
  [32]: "tap32",
  [48]: "tap48",
  [64]: "tap64",
  [192]: "tap192",
};

interface NoteProps extends PixiReactElementProps<typeof Sprite> {
  quant: number;
  column: number;
  noteType: NoteType;
  arrowSize: number;
}

function Note({ quant, noteType, column, arrowSize, ...props }: NoteProps) {
  let texId: TextureID;
  if (noteType === NoteTypes.MINE) texId = "mine";
  else if (noteType === NoteTypes.LIFT) texId = "lift";
  else texId = QUANT_TO_TEX_ID[quant] ?? "tap192";

  const tex = useTexture(texId);
  const scale = noteType === NoteTypes.MINE ? 0.75 * arrowSize : arrowSize;
  const rotation = noteType === NoteTypes.MINE ? 0 : COLUMN_TO_ROTATION[column];

  return (
    <pixiSprite
      {...props}
      anchor={0.5}
      texture={tex}
      x={column * arrowSize}
      rotation={rotation}
      width={scale}
      height={scale}
    />
  );
}

interface HoldProps {
  column: number;
  noteType: NoteType;
  startBeat: Fraction;
  endBeat: Fraction;
  songPos: number;
  scroll: ScrollSpeed;
  arrowSize: number;
}

function Hold({
  column,
  noteType,
  startBeat,
  endBeat,
  songPos,
  scroll,
  arrowSize,
}: HoldProps) {
  const texId = noteType === NoteTypes.HOLD_HEAD ? "hold_body" : "roll_body";
  const tex = useTexture(texId);
  const anchor = useMemo(() => ({ x: 0.5, y: 0 }), []);
  const y = (startBeat.valueOf() - songPos) * arrowSize * scroll.value;
  const height = endBeat.sub(startBeat).valueOf() * arrowSize * scroll.value;
  return (
    <pixiSprite
      anchor={anchor}
      texture={tex}
      x={column * arrowSize}
      y={y}
      width={arrowSize}
      height={height}
    />
  );
}

export interface NotefieldProps {
  chart?: Chart;
  beat: number;
  scroll: ScrollSpeed;
  mini: number;
}

export function Notefield({ chart, beat, scroll, mini }: NotefieldProps) {
  const [ready, setReady] = useState(false);
  const lastLoadedChartRef = useRef<Chart>(undefined);
  // The Pixi.js `Sprite`
  //const spriteRef = useRef<Sprite>(null);

  //const [texture, setTexture] = useState(Texture.EMPTY);
  //const [rotation, setRotation] = useState(0);
  // const [isHovered, setIsHover] = useState(false);
  // const [isActive, setIsActive] = useState(false);

  // preload textures
  useEffect(() => {
    loadAssets().then(() => {
      setReady(true);
    });
  }, []);

  // for some godforsaken reason, upon a refresh, after the chart is loaded in,
  // sometimes Playfield will rerender with "default" props
  // (i.e. chart = undefined), causing the chart to not show up until props are
  // updated some other way. i don't know why this happens, but to guard
  // against this, we store the last-loaded chart and use it in case
  // an undefined chart gets passed down
  useEffect(() => {
    if (chart) {
      lastLoadedChartRef.current = chart;
    }
  }, [chart]);

  chart = chart ?? lastLoadedChartRef.current;

  // const updateFunc = useCallback<TickerCallback<unknown>>((ticker) => {
  //   setRotation((r) => r - 0.02 * ticker.deltaTime);
  // }, []);

  //useTick(updateFunc);

  const notes = useMemo(
    () => (chart ? [...chart.notesWithTailIterator()] : null),
    [chart]
  );

  if (!ready || !chart || !notes) {
    return null;
  }

  const numColumns = chart.getNumColumns();
  const arrowSize = (1 - mini / 200) * BASE_ARROW_SIZE;
  const xOff = (numColumns / 2 - 0.5) * arrowSize;

  // TODO: add useTick(?) to update x pos on screen resize

  return (
    <pixiContainer
      x={-xOff}
      //rotation={rotation * 0}
    >
      <ReceptorRow numColumns={4} arrowSize={arrowSize} />
      {notes.map((note, i) => {
        const quant = Number(note.beat.d) * 4;
        const y = (note.beat.valueOf() - beat) * arrowSize * scroll.value;
        return (
          <Fragment key={i}>
            {note.tailBeat ? (
              <Hold
                noteType={note.noteType}
                column={note.column}
                startBeat={note.beat}
                endBeat={note.tailBeat}
                songPos={beat}
                scroll={scroll}
                arrowSize={arrowSize}
              />
            ) : null}
            <Note
              noteType={note.noteType}
              quant={quant}
              column={note.column}
              arrowSize={arrowSize}
              y={y}
            />
          </Fragment>
        );
      })}
    </pixiContainer>
  );
}
