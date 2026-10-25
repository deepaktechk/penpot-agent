// Locate a Chrome/Chromium binary (puppeteer-core does not download one).
// Keep the list in sync with CHROME_CANDIDATES in src/pbridge/cli/commands/setup.py.
import fs from "node:fs";
import puppeteer, { type Browser, type LaunchOptions } from "puppeteer-core";

export const CHROME_CANDIDATES: string[] = [
  process.env.CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
].filter((path): path is string => Boolean(path));

/** Explicit path, else the first installed candidate, else undefined. */
export const findChrome = (explicit?: string): string | undefined => explicit || CHROME_CANDIDATES.find(path => fs.existsSync(path));

/** Chrome refuses to start its sandbox as root (Docker containers, some CI). There - or when
 *  PBRIDGE_CHROME_NO_SANDBOX=1 - run without it; everywhere else keep the sandbox. */
const sandboxArgs = (): string[] => {
  const isRoot = typeof process.getuid === "function" && process.getuid() === 0;
  return isRoot || process.env.PBRIDGE_CHROME_NO_SANDBOX === "1" ? ["--no-sandbox"] : [];
};

/** Launch headless Chrome; `userDataDir` reuses a profile (e.g. one where the user logged in by hand). */
export const launchChrome = (executablePath: string, args: string[] = [], userDataDir: string | null = null): Promise<Browser> =>
  puppeteer.launch({ executablePath, headless: true, args: [...args, ...sandboxArgs()],
                     ...(userDataDir ? { userDataDir } : {}) } as LaunchOptions);
