// Browser session before the first visit: colour scheme and cookies (for pages behind a login).
//
// Cookie files: a JSON array as exported by browser extensions ("EditThisCookie", "Cookie-Editor")
// or by puppeteer itself. Extension field names (expirationDate, sameSite "no_restriction") are
// converted to puppeteer's CookieParam.
import fs from "node:fs";
import type { CookieParam, Page } from "puppeteer-core";
import { log } from "../page-lib";

const SAME_SITE: Record<string, CookieParam["sameSite"]> = {
  no_restriction: "None", none: "None", lax: "Lax", strict: "Strict",
};

/** One exported cookie -> puppeteer cookie (unknown sameSite values are dropped, Chrome then uses its default). */
export const toCookieParam = (cookie: Record<string, any>, pageUrl: string): CookieParam => {
  const param: CookieParam = { name: String(cookie.name), value: String(cookie.value ?? "") };
  if (cookie.domain) param.domain = String(cookie.domain); else param.url = cookie.url ? String(cookie.url) : pageUrl;
  if (cookie.path) param.path = String(cookie.path);
  if (cookie.secure !== undefined) param.secure = Boolean(cookie.secure);
  if (cookie.httpOnly !== undefined) param.httpOnly = Boolean(cookie.httpOnly);
  const expires = cookie.expires ?? cookie.expirationDate;
  if (typeof expires === "number" && expires > 0) param.expires = expires;
  const sameSite = SAME_SITE[String(cookie.sameSite || "").toLowerCase()];
  if (sameSite) param.sameSite = sameSite;
  return param;
};

export const prepareSession = async (page: Page, pageUrl: string, colorScheme: "dark" | "light",
                                     cookieFile: string | null): Promise<void> => {
  // always set: headless Chrome otherwise follows the OS appearance (a dark-mode Mac captures dark pages)
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: colorScheme }]);
  log(`colour scheme: ${colorScheme}`);
  if (cookieFile) {
    const exported = JSON.parse(fs.readFileSync(cookieFile, "utf8"));
    const cookies = (Array.isArray(exported) ? exported : exported.cookies || []).map((cookie: Record<string, any>) => toCookieParam(cookie, pageUrl));
    await page.setCookie(...cookies);
    log(`cookies set: ${cookies.length}`);
  }
};
