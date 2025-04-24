import tap4 from "../../assets/4th.png";
import tap8 from "../../assets/8th.png";
import tap12 from "../../assets/12th.png";
import tap16 from "../../assets/16th.png";
import tap24 from "../../assets/24th.png";
import tap32 from "../../assets/32nd.png";
import tap48 from "../../assets/48th.png";
import tap64 from "../../assets/64th.png";
import tap192 from "../../assets/192nd.png";
import receptor from "../../assets/receptor.png";
import mine from "../../assets/mine.png";
import lift from "../../assets/lift.png";
import holdBody from "../../assets/hold_body.png";
import holdBottomCap from "../../assets/hold_bottomcap.png";
import rollBody from "../../assets/roll_body.png";
import rollBottomCap from "../../assets/roll_bottomcap.png";
import { Assets, Texture } from "pixi.js";
import { useMemo } from "react";

const ASSET_PATHS = [
  ["tap4", tap4],
  ["tap8", tap8],
  ["tap12", tap12],
  ["tap16", tap16],
  ["tap24", tap24],
  ["tap32", tap32],
  ["tap48", tap48],
  ["tap64", tap64],
  ["tap192", tap192],
  ["receptor", receptor],
  ["mine", mine],
  ["lift", lift],
  ["hold_body", holdBody],
  ["hold_bottomcap", holdBottomCap],
  ["roll_body", rollBody],
  ["roll_bottomcap", rollBottomCap],
] as const;

const ASSETS = ASSET_PATHS.map((item) => ({ alias: item[0], src: item[1] }));

export type TextureID = (typeof ASSET_PATHS)[number][0];

/**
 * Load all the textures.
 */
export async function loadAssets() {
  await Assets.load(ASSETS);
}

/**
 * Get a texture from its ID. The texture must already be loaded via
 * loadAssets().
 */
export function useTexture(id: TextureID): Texture {
  return useMemo(() => Texture.from(id), [id]);
}
