// Font lookup by family name and variant selection by weight/style.
import { warn } from "./state";

const fontCache: Record<string, any> = {};

/** Penpot font by name (exact, then case-insensitive, then Penpot's own lookup). Throws if missing. */
export const font = (name: string): any => {
  if (fontCache[name]) return fontCache[name];
  const all = penpot.fonts.all;
  const found = all.find((candidate: any) => candidate.name === name)
    || all.find((candidate: any) => candidate.name.toLowerCase() === String(name).toLowerCase())
    || penpot.fonts.findByName(name);
  if (!found) throw new Error("font not found: " + name);
  return (fontCache[name] = found);
};

/** Variant with this weight and style, else the nearest weight (with a warning). */
export const variant = (fontObj: any, weight: number | string = 400, italic = false): any => {
  const wantedWeight = String(weight === "bold" ? 700 : weight === "normal" ? 400 : weight);
  const variants: any[] = fontObj.variants;
  const wantedStyle = italic ? "italic" : "normal";
  let chosen = variants.find(candidate => String(candidate.fontWeight) === wantedWeight && (candidate.fontStyle || "normal") === wantedStyle);
  if (!chosen) {
    const sameStyle = variants.filter(candidate => (candidate.fontStyle || "normal") === wantedStyle);
    const distance = (candidate: any) => Math.abs(+candidate.fontWeight - +wantedWeight);
    chosen = (sameStyle.length ? sameStyle : variants).slice().sort((first, second) => distance(first) - distance(second))[0];
    warn(`font ${fontObj.name} has no weight ${wantedWeight}${italic ? " italic" : ""}, using ${chosen && chosen.fontWeight}`);
  }
  return chosen;
};
