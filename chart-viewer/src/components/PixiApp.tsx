import { Notefield, NotefieldProps } from "./notefield/Notefield";
import { useCallback, useEffect, useState } from "react";

export function PixiApp(props: NotefieldProps) {
  const [screenWidth, setScreenWidth] = useState<number>(window.innerWidth);

  const resizeListener = useCallback(() => {
    setScreenWidth(window.innerWidth);
  }, []);

  useEffect(() => {
    window.addEventListener("resize", resizeListener);
    return () => window.removeEventListener("resize", resizeListener);
  }, [resizeListener]);

  return (
    <>
      <pixiContainer x={screenWidth / 2} y={50}>
        <Notefield {...props} />
      </pixiContainer>
    </>
  );
}
