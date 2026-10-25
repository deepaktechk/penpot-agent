// Command line of `node-cli.js capture` (called by Python: src/pbridge/capture/runner.py).
//
// usage: node node-cli.js capture --url URL --out DIR [--width 1920] [--dpr 1] [--fonts "Outfit,Inter"]
//        [--no-scroll] [--no-freeze] [--no-warmup] [--keep-overlays] [--hide "sel,sel"]
//        [--click "sel,sel"] [--wait 1500] [--timeout 90000] [--chrome PATH] [--height N]
//        [--selector "main"] [--color-scheme dark|light] [--cookies cookies.json] [--user-data-dir DIR]

export interface CaptureOptions {
  url: string;
  out: string;
  width: number;
  dpr: number;
  waitMs: number;         // pause after sizing the viewport, before the dump
  timeoutMs: number;      // navigation timeout
  fonts: string[];        // families that must be loaded
  click: string[];
  hide: string[];
  height: number;         // 0 = full document height
  selector: string | null;
  chrome?: string;
  warmup: boolean;
  scroll: boolean;
  freeze: boolean;
  keepOverlays: boolean;
  colorScheme: "dark" | "light";          // emulated prefers-color-scheme; default light, so captures do not
                                          // depend on the OS appearance of the machine running them
  cookies: string | null;                 // JSON file with cookies to set before loading (logged-in pages)
  userDataDir: string | null;             // Chrome profile folder (a session logged in by hand)
}

/** `--name value`; a flag given without a value (or followed by another flag) reads as true. */
const makeReader = (argv: string[]) => ({
  opt: <T>(name: string, fallback: T): string | true | T => {
    const index = argv.indexOf("--" + name); if (index < 0) return fallback;
    const value = argv[index + 1];
    return (value === undefined || value.startsWith("--")) ? true : value;
  },
  flag: (name: string): boolean => argv.includes("--" + name),
});

const list = (value: unknown): string[] => String(value || "").split(",").map(item => item.trim()).filter(Boolean);

export const parseOptions = (argv: string[]): CaptureOptions | null => {
  const { opt, flag } = makeReader(argv);
  const url = opt("url", undefined), out = opt("out", undefined);
  if (!url || !out) return null;
  const chrome = opt("chrome", undefined);
  const colorScheme = opt("color-scheme", "light");
  if (colorScheme !== "dark" && colorScheme !== "light") throw new Error("--color-scheme must be dark or light");
  const textOrNull = (value: unknown): string | null => (typeof value === "string" ? value : null);
  return {
    url: String(url), out: String(out),
    width: +opt("width", 1920), dpr: +opt("dpr", 1), waitMs: +opt("wait", 1500), timeoutMs: +opt("timeout", 90000),
    fonts: list(opt("fonts", "")), click: list(opt("click", "")), hide: list(opt("hide", "")),
    height: +opt("height", 0) || 0,
    selector: opt("selector", null) as string | null,
    chrome: chrome ? String(chrome) : undefined,
    warmup: !flag("no-warmup"), scroll: !flag("no-scroll"), freeze: !flag("no-freeze"), keepOverlays: flag("keep-overlays"),
    colorScheme, cookies: textOrNull(opt("cookies", null)), userDataDir: textOrNull(opt("user-data-dir", null)),
  };
};
