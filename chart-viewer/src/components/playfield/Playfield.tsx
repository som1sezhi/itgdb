import { PixiReactElementProps, useApplication, useTick } from "@pixi/react";
import { Sprite, TickerCallback } from "pixi.js";
import { useState, useCallback, useEffect } from "react";
import { loadAssets, useTexture } from "./useTexture";

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

function Receptor(props: PixiReactElementProps<typeof Sprite>) {
  const receptorTex = useTexture("receptor");
  return <pixiSprite {...props} anchor={0.5} texture={receptorTex} />;
}

function ReceptorRow({ numColumns }: { numColumns: 4 | 8 }) {
  const xOff = numColumns / 2 - 0.5;
  return (
    <>
      {[...Array(numColumns)].map((_, i) => (
        <Receptor
          key={i}
          x={(i - xOff) * BASE_ARROW_SIZE}
          y={0}
          rotation={COLUMN_TO_ROTATION[i]}
          width={BASE_ARROW_SIZE}
          height={BASE_ARROW_SIZE}
        />
      ))}
    </>
  );
}

export function Playfield() {
  const [ready, setReady] = useState(false);
  const { app } = useApplication();
  // The Pixi.js `Sprite`
  //const spriteRef = useRef<Sprite>(null);

  //const [texture, setTexture] = useState(Texture.EMPTY);
  const [rotation, setRotation] = useState(0);
  // const [isHovered, setIsHover] = useState(false);
  // const [isActive, setIsActive] = useState(false);

  // preload textures
  useEffect(() => {
    loadAssets().then(() => {
      setReady(true);
    });
  }, []);

  const updateFunc = useCallback<TickerCallback<unknown>>((ticker) => {
    setRotation((r) => r - 0.02 * ticker.deltaTime);
  }, []);

  useTick(updateFunc);

  if (!ready) return null;

  return (
    <pixiContainer x={app.screen.width / 2} y={50} rotation={rotation * 0}>
      <ReceptorRow numColumns={4} />
    </pixiContainer>
  );
}
