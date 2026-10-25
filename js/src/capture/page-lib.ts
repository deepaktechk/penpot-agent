// Call the browser-side library (bundles/capture-page.js) from node.
//
// The bundle is evaluated in the page on demand (navigation discards it), then
// `pageCall(page, "fn", ...args)` runs `window.__pbCapture.fn(...args)` and returns its result.
import fs from "node:fs";
import path from "node:path";
import type { Page } from "puppeteer-core";
import type { PageApi } from "./page/index";

const PAGE_LIB = fs.readFileSync(path.join(__dirname, "capture-page.js"), "utf8");
const INJECT = `(() => { if (!window.__pbCapture) {\n${PAGE_LIB}\n} return true; })()`;

export const ensurePageLib = async (page: Page): Promise<void> => { await page.evaluate(INJECT); };

export const pageCall = async <K extends keyof PageApi>(page: Page, functionName: K, ...args: Parameters<PageApi[K]>): Promise<Awaited<ReturnType<PageApi[K]>>> => {
  await ensurePageLib(page);
  return page.evaluate((name: string, callArgs: unknown[]) => ((window as any).__pbCapture[name] as (...values: unknown[]) => unknown)(...callArgs), functionName as string, args) as Promise<Awaited<ReturnType<PageApi[K]>>>;
};

export const sleep = (milliseconds: number): Promise<void> => new Promise(resolve => setTimeout(resolve, milliseconds));

export const log = (...parts: unknown[]): void => console.error("[capture]", ...parts);
