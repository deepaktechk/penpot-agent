// Making the page still before the dump: reflow, images, animations, JS timers.
//
// Order used by the capture (see ../steps/settle.ts):
//   1. pause CSS animations             (pauseAnimations)
//   2. wait until positions stop moving (layoutSignature sampled from node)
//   3. stop every JS timer and rAF      (stopTimers) - carousels freeze between slides
//   4. inject hide/freeze CSS           (applyHideAndFreeze)

export const scrollHeight = (): number => document.documentElement.scrollHeight;

export const scrollTo = (y: number): void => window.scrollTo(0, y);

/** Document height after two animation frames (i.e. after pending reflow). */
export const frameHeight = (): Promise<number> =>
  new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve(document.documentElement.scrollHeight))));

/** Full document height for the single-layout screenshot. */
export const fullHeight = (): number => Math.ceil(Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));

/** Resolve when every incomplete image loads or errors (8 s cap each). */
export const waitForImages = async (): Promise<void> => {
  await Promise.all([...document.images].filter(image => !image.complete).map(image => new Promise<void>(resolve => {
    image.onload = image.onerror = () => resolve(); setTimeout(resolve, 8000);
  })));
};

export const pauseAnimations = (): void => {
  const styleTag = document.createElement("style");
  styleTag.textContent = "*,*::before,*::after{animation-play-state:paused!important}";
  document.head.appendChild(styleTag);
};

/** Hash of every element's box and inline transform: equal hashes = nothing moved. */
export const layoutSignature = (): number => {
  let hash = 0; const elements = document.querySelectorAll("body *");
  for (let i = 0; i < elements.length; i += 1) {
    const rect = elements[i].getBoundingClientRect();
    hash = (hash * 31 + Math.round(rect.left * 2) * 7 + Math.round(rect.top * 2)) | 0;
    const transform = (elements[i] as HTMLElement).style.transform;
    if (transform) for (let j = 0; j < transform.length; j++) hash = (hash * 31 + transform.charCodeAt(j)) | 0;
  }
  return hash;
};

/** Clear every timeout/interval created so far and disable requestAnimationFrame. */
export const stopTimers = (): void => {
  const maxId = setTimeout(() => { }, 0) as unknown as number;
  for (let i = 0; i <= maxId; i++) { clearTimeout(i); clearInterval(i); }
  window.requestAnimationFrame = () => 0;
};

/** Hide user-selected elements; freeze transitions/animations/caret; pause videos. */
export const applyHideAndFreeze = (hide: string[], freeze: boolean): void => {
  const styleTag = document.createElement("style");
  let css = hide.map(selector => `${selector}{display:none!important}`).join("\n");
  if (freeze) css += "\n*,*::before,*::after{animation-play-state:paused!important;transition:none!important;caret-color:transparent!important}";
  styleTag.textContent = css; document.head.appendChild(styleTag);
  document.querySelectorAll("video").forEach(video => { try { video.pause(); } catch (error) { /* ignore */ } });
};
