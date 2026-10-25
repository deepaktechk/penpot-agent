// Auto-hide consent banners and chat launchers: fixed/sticky overlays that are not page content.
// A full-width bar at the very top (the site header) is never hidden.

const OVERLAY_RE = /(cookie|consent|gdpr|ccpa|onetrust|cookiebot|cky-|cmplz|osano|truste|quantcast|didomi|usercentrics|intercom|crisp|drift|hubspot-messages|hs-beacon|zendesk|zEWidget|livechat|tawk|olark|freshchat|launcher|chat-widget|chatbot|tidio|smartsupp|userlike)/i;
const OVERLAY_IFRAME_RE = /(intercom|crisp|drift|hubspot|zendesk|livechat|tawk|chat|consent|cookie)/i;

/** Hide matching overlays; returns short descriptions of what was hidden. */
export const hideOverlays = (): string[] => {
  const hidden: string[] = [];
  for (const element of document.querySelectorAll("body *")) {
    const style = getComputedStyle(element); if (style.position !== "fixed" && style.position !== "sticky") continue;
    // what the element calls itself: id, classes, aria-label, iframe src/title
    const iframeInfo = element.tagName === "IFRAME" ? (element as HTMLIFrameElement).src || (element as HTMLIFrameElement).title : "";
    const signature = (element.id + " " + (typeof element.className === "string" ? element.className : "") + " "
      + (element.getAttribute("aria-label") || "") + " " + iframeInfo).slice(0, 400);
    const rect = element.getBoundingClientRect();
    const isHeader = rect.top <= 1 && rect.height < 160 && rect.width > window.innerWidth * 0.8 && !OVERLAY_RE.test(signature);
    if (!isHeader && OVERLAY_RE.test(signature)) {
      (element as HTMLElement).style.setProperty("display", "none", "important"); hidden.push(signature.trim().slice(0, 60));
    }
  }
  document.querySelectorAll("iframe").forEach(iframe => {
    const signature = (iframe.id + " " + iframe.title + " " + iframe.src);
    if (OVERLAY_IFRAME_RE.test(signature)) { iframe.style.setProperty("display", "none", "important"); hidden.push("iframe " + signature.slice(0, 50)); }
  });
  return hidden;
};
