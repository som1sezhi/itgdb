import { useApplication, useTick } from "@pixi/react";
import { Notefield, NotefieldProps } from "./notefield/Notefield";
import { useState } from "react";

export function PixiApp(props: NotefieldProps) {
  const { app } = useApplication();
  const [screenWidth, setScreenWidth] = useState<number>(app.screen.width);

  useTick(() => {
    setScreenWidth(app.screen.width);
  });

  return (
    <>
      <pixiContainer x={screenWidth / 2} y={50}>
        <Notefield {...props} />
      </pixiContainer>
    </>
  );
}
