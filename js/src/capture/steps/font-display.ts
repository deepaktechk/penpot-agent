// Rewrites `font-display: optional` to `swap` in the page's HTML and CSS responses.
//
// With `optional`, Chrome paints the real web font only when it is already in its cache at the first
// layout; otherwise the fallback font stays for the whole page view. Reloading in the hope that the
// cache has the font by then is not reliable (uncacheable responses, cache misses on CI runners), and
// serving the font faster does not help either: a network answer, however fast, counts as too late.
// With `swap`, the real font replaces the fallback as soon as it has loaded, and the capture waits for
// fonts anyway. Enabled only after a load painted a fallback font, so other sites are untouched.
import type { CDPSession, Page, Protocol } from "puppeteer-core";
import { log } from "../page-lib";

const OPTIONAL_DISPLAY = /font-display\s*:\s*optional/gi;
// the body handed back is decoded, so these headers would no longer describe it
const STALE_HEADERS = new Set(["content-length", "content-encoding"]);

export class FontDisplayOverride {
  private session: CDPSession | null = null;
  private rewrittenResponses = 0;

  constructor(private readonly page: Page) {}

  get rewritten(): number { return this.rewrittenResponses; }

  /** From the next navigation on, rewrite `font-display: optional` in documents and stylesheets. */
  async enable(): Promise<void> {
    if (this.session) return;
    const session = await this.page.createCDPSession();
    this.session = session;
    session.on("Fetch.requestPaused", (event: Protocol.Fetch.RequestPausedEvent) => {
      this.rewrite(session, event).catch(() =>
        session.send("Fetch.continueRequest", { requestId: event.requestId }).catch(() => undefined));
    });
    await session.send("Fetch.enable", { patterns: [
      { resourceType: "Document", requestStage: "Response" },
      { resourceType: "Stylesheet", requestStage: "Response" },
    ] });
    log("font-display: optional -> swap from now on");
  }

  private async rewrite(session: CDPSession, event: Protocol.Fetch.RequestPausedEvent): Promise<void> {
    const requestId = event.requestId;
    const status = event.responseStatusCode;
    if (event.responseErrorReason || !status || (status >= 300 && status < 400)) {
      await session.send("Fetch.continueRequest", { requestId });
      return;
    }
    const response = await session.send("Fetch.getResponseBody", { requestId });
    // latin1 maps every byte to one character and back, so the body survives whatever its charset
    const text = Buffer.from(response.body, response.base64Encoded ? "base64" : "utf8").toString("latin1");
    const patched = text.replace(OPTIONAL_DISPLAY, "font-display: swap");
    if (patched === text) {
      await session.send("Fetch.continueRequest", { requestId });
      return;
    }
    this.rewrittenResponses++;
    const headers = (event.responseHeaders || []).filter(header => !STALE_HEADERS.has(header.name.toLowerCase()));
    await session.send("Fetch.fulfillRequest", { requestId, responseCode: status, responseHeaders: headers,
      body: Buffer.from(patched, "latin1").toString("base64") });
  }
}
