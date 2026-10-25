// Text measurement: the browser's exact line boxes, and the visible part of ellipsized text.
import type { TextLine } from "../../shared/layout-types";
import { round2 } from "./geometry";

/** A line being accumulated: its text, horizontal extent, vertical extent and vertical centre. */
interface LineAcc { t: string; x0: number; x1: number; top: number; bot: number; mid: number }

/** Lines of an element's own inline text, measured per character with DOM Ranges.
 *  A new line starts when a character's vertical centre moves by more than half its height. */
export const textLines = (element: Element): TextLine[] => {
  const lines: LineAcc[] = []; let current: LineAcc | null = null;
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let textNode: Node | null;
  while ((textNode = walker.nextNode())) {
    // only text that belongs to this element's inline formatting (skip block descendants)
    let ancestor = textNode.parentElement, inline = true;
    while (ancestor && ancestor !== element) {
      if (!/inline|contents/.test(getComputedStyle(ancestor).display)) { inline = false; break; }
      ancestor = ancestor.parentElement;
    }
    if (!inline) continue;
    const text = textNode.textContent || "";
    for (let i = 0; i < text.length; i++) {
      const range = document.createRange(); range.setStart(textNode, i); range.setEnd(textNode, i + 1);
      const box = range.getClientRects()[0];
      if (!box || box.width === 0 && /\s/.test(text[i])) { if (current) current.t += text[i]; continue; }
      const mid = box.top + box.height / 2;
      if (!current || Math.abs(mid - current.mid) > box.height * 0.5) {
        if (current) lines.push(current);
        current = { t: text[i], x0: box.left, x1: box.right, top: box.top, bot: box.bottom, mid };
      } else {
        current.t += text[i]; current.x0 = Math.min(current.x0, box.left); current.x1 = Math.max(current.x1, box.right);
        current.top = Math.min(current.top, box.top); current.bot = Math.max(current.bot, box.bottom);
      }
    }
  }
  if (current) lines.push(current);
  const own = element.getBoundingClientRect();
  return lines.map(line => {
    const measured: TextLine = { t: line.t.replace(/\s+/g, " ").trim(),
      r: [round2(line.x0), round2(line.top), round2(line.x1 - line.x0), round2(line.bot - line.top)] };
    // a line outside the element's own box is only kept if it is really painted there
    const centerY = (line.top + line.bot) / 2, probeX = Math.min(line.x1 - 1, line.x0 + 6);
    if (centerY < own.top - 1 || centerY > own.bottom + 1) {
      const hit = document.elementFromPoint(probeX, centerY);
      if (!hit || !(element === hit || element.contains(hit) || hit.contains(element))) measured.hid = 1;
    }
    return measured;
  }).filter(line => line.t);
};

/** Visible text of a single-line `text-overflow: ellipsis` element, or null if it fits. */
export const ellipsisText = (element: HTMLElement, style: CSSStyleDeclaration): string | null => {
  const full = element.innerText; const canvas = document.createElement("canvas").getContext("2d")!;
  canvas.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  const rect = element.getBoundingClientRect();
  const available = rect.width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  if (canvas.measureText(full).width <= available + 0.5) return null;
  // binary search for the longest prefix that fits together with "…"
  const ellipsisWidth = canvas.measureText("…").width; let low = 0, high = full.length;
  while (low < high) {
    const middle = (low + high + 1) >> 1;
    if (canvas.measureText(full.slice(0, middle)).width + ellipsisWidth <= available + 0.01) low = middle; else high = middle - 1;
  }
  return full.slice(0, low) + "…";
};
