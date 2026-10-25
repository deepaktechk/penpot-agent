// Dump + screenshot from ONE consistent layout: the viewport is resized to the full document
// height first, so the layout dump and the screenshot describe the same pixels.
import fs from "node:fs";
import path from "node:path";
import type { Page } from "puppeteer-core";
import type { LayoutDump } from "../../shared/layout-types";
import { pageCall, sleep } from "../page-lib";

export interface DumpRequest {
  out: string;
  width: number;
  dpr: number;
  height: number;          // 0 = full document height
  waitMs: number;
  selector: string | null;
  stableSamples: number | null;
  freeze: boolean;
}

export const dumpAndScreenshot = async (page: Page, request: DumpRequest): Promise<LayoutDump> => {
  const fullHeight = request.height || await pageCall(page, "fullHeight");
  await page.setViewport({ width: request.width, height: fullHeight, deviceScaleFactor: request.dpr });
  await sleep(request.waitMs);
  const data = await pageCall(page, "dumpLayout", request.selector);
  data.quality.stableSamples = request.stableSamples;
  data.quality.freeze = request.freeze;
  fs.writeFileSync(path.join(request.out, "layout.json"), JSON.stringify(data));
  await page.screenshot({ path: path.join(request.out, "shot.png") as `${string}.png`, fullPage: false });
  return data;
};
