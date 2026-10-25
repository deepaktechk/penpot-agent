// Local library: colors, typographies and components (create or update by name).
import { font, variant } from "./fonts";
import { byId } from "./state";

export const addColor = (name: string, hex: string, opacity = 1): string => {
  const library = penpot.library.local;
  let color = library.colors.find((candidate: any) => candidate.name === name);
  if (!color) color = library.createColor();
  color.name = name; color.color = hex; color.opacity = opacity;
  return color.id;
};

export interface TypographySpec { font?: string; weight?: number; italic?: boolean; size?: number; lh?: number; ls?: number; upper?: boolean }

export const addTypography = (name: string, style: TypographySpec): string => {
  const library = penpot.library.local;
  let typography = library.typographies.find((candidate: any) => candidate.name === name);
  if (!typography) typography = library.createTypography();
  typography.name = name;
  if (style.font) {
    const fontObj = font(style.font); typography.fontId = fontObj.fontId; typography.fontFamily = fontObj.fontFamily;
    const chosen = variant(fontObj, style.weight || 400, style.italic);
    typography.fontVariantId = chosen.fontVariantId; typography.fontWeight = String(chosen.fontWeight);
  }
  if (style.size) typography.fontSize = String(style.size);
  if (style.lh && style.size) typography.lineHeight = String(+(style.lh / style.size).toFixed(4));
  if (style.ls !== undefined) typography.letterSpacing = String(style.ls);
  if (style.upper) typography.textTransform = "uppercase";
  return typography.id;
};

export const makeComponent = (ids: string[], name?: string): string | null => {
  const component = penpot.library.local.createComponent(ids.map(byId).filter(Boolean));
  if (component && name) component.name = name;
  return component && component.id;
};
