import { Composition } from "remotion";
import { Cartoes } from "./Cartoes";

export const Root = () => (
  <Composition id="Cartoes" component={Cartoes} durationInFrames={450} fps={30} width={1080} height={1920} />
);
