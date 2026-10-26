(() => {
  // src/capture/page/geometry.ts
  var SVGNS = "http://www.w3.org/2000/svg";
  var round2 = (value) => Math.round(value * 100) / 100;
  var toRect = (rect) => [round2(rect.left), round2(rect.top), round2(rect.width), round2(rect.height)];
  var isGenericFamily = (family) => !family || family.startsWith("-") || /^(system-ui|sans-serif|serif|monospace)$/.test(family);

  // src/capture/page/effective.ts
  var UNCLIPPED = { op: 1, clip: [-1e6, -1e6, 2e6, 2e6], vis: true, rendered: true };
  var clipsEverything = (clipPath, box) => {
    const shape = /^(circle|ellipse|inset)\((.*)\)$/.exec(clipPath.trim());
    if (!shape) return false;
    const [, kind, args] = shape;
    const sizes = args.split(/\s+at\s+/)[0].split(/\s+round\s+/)[0].trim().split(/\s+/).filter(Boolean);
    const length = (value, reference) => value.endsWith("%") ? parseFloat(value) / 100 * reference : parseFloat(value);
    if (kind === "circle") return sizes.length > 0 && length(sizes[0], Math.hypot(box.width, box.height) / Math.SQRT2) <= 0;
    if (kind === "ellipse") return sizes.length === 2 && (length(sizes[0], box.width) <= 0 || length(sizes[1], box.height) <= 0);
    const [top, right = top, bottom = top, left = right] = sizes;
    if (top === void 0) return false;
    return length(top, box.height) + length(bottom, box.height) >= box.height || length(left, box.width) + length(right, box.width) >= box.width;
  };
  var createEffectiveResolver = () => {
    const cache = /* @__PURE__ */ new Map();
    const resolve = (element) => {
      if (!element || element === document.documentElement) return UNCLIPPED;
      const cached = cache.get(element);
      if (cached) return cached;
      const parent = resolve(element.parentElement);
      const style = getComputedStyle(element);
      const opacity = parent.op * parseFloat(style.opacity || "1");
      const rendered = parent.rendered && style.display !== "none" && style.contentVisibility !== "hidden" && !(style.clipPath !== "none" && clipsEverything(style.clipPath, element.getBoundingClientRect()));
      const visible = rendered && style.visibility !== "hidden" && style.visibility !== "collapse";
      let clip = parent.clip;
      const overflow = style.overflow + " " + style.overflowX + " " + style.overflowY;
      if (/hidden|clip|auto|scroll/.test(overflow) && element.namespaceURI !== SVGNS) {
        const border = element.getBoundingClientRect();
        const padding = {
          left: border.left + parseFloat(style.borderLeftWidth || "0"),
          top: border.top + parseFloat(style.borderTopWidth || "0"),
          right: border.right - parseFloat(style.borderRightWidth || "0"),
          bottom: border.bottom - parseFloat(style.borderBottomWidth || "0")
        };
        const left = Math.max(clip[0], padding.left), top = Math.max(clip[1], padding.top);
        const right = Math.min(clip[0] + clip[2], padding.right), bottom = Math.min(clip[1] + clip[3], padding.bottom);
        clip = [left, top, Math.max(0, right - left), Math.max(0, bottom - top)];
      }
      const effective = { op: opacity, clip, vis: visible, rendered };
      cache.set(element, effective);
      return effective;
    };
    return resolve;
  };

  // src/capture/page/svg.ts
  var PAINT_PROPS = [
    "fill",
    "stroke",
    "stroke-width",
    "stroke-dasharray",
    "stroke-linecap",
    "stroke-linejoin",
    "opacity",
    "fill-opacity",
    "stroke-opacity",
    "fill-rule"
  ];
  var SHAPES = /* @__PURE__ */ new Set(["path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "use", "image"]);
  var inlineStyles = (originals, copies, texts) => {
    originals.forEach((original, i) => {
      const copy = copies[i];
      if (!copy || original.namespaceURI !== SVGNS) return;
      const style = getComputedStyle(original);
      for (const property of PAINT_PROPS) {
        const value = style.getPropertyValue(property);
        if (value && value !== "normal") copy.setAttribute(property, value);
      }
      copy.removeAttribute("class");
      copy.removeAttribute("style");
      if (original.tagName.toLowerCase() === "text") {
        const bounds = original.getBoundingClientRect();
        const screenMatrix = original.getScreenCTM();
        const scale = screenMatrix ? Math.hypot(screenMatrix.a, screenMatrix.b) : 1;
        const tspans = [...original.querySelectorAll("tspan")];
        texts.push({
          text: original.textContent,
          r: toRect(bounds),
          scale: Math.round(scale * 1e4) / 1e4,
          font: [
            style.fontFamily.split(",")[0].replace(/["']/g, ""),
            style.fontSize,
            style.fontWeight,
            style.letterSpacing,
            style.fill,
            style.opacity,
            style.textAnchor
          ],
          lines: tspans.length ? tspans.map((tspan) => ({ t: tspan.textContent, r: toRect(tspan.getBoundingClientRect()) })) : [{ t: original.textContent, r: toRect(bounds) }]
        });
        copy.remove();
      }
    });
  };
  var bakeTransforms = (svg, originals, copies, clone) => {
    const svgBounds = svg.getBoundingClientRect();
    originals.forEach((original, i) => {
      const copy = copies[i];
      if (!copy || original.namespaceURI !== SVGNS || original === svg) return;
      if (copy.hasAttribute("transform")) copy.removeAttribute("transform");
      if (!SHAPES.has(original.tagName.toLowerCase()) || !copy.isConnected && !clone.contains(copy)) return;
      const graphic = original;
      let matrix;
      try {
        matrix = graphic.getScreenCTM();
      } catch (error) {
        matrix = null;
      }
      if (!matrix) return;
      const { a: m11, b: m12, c: m21, d: m22 } = matrix;
      let translateX = matrix.e - svgBounds.left, translateY = matrix.f - svgBounds.top;
      try {
        const box = graphic.getBBox();
        const painted = graphic.getBoundingClientRect();
        const predictedX = m11 * (box.x + box.width / 2) + m21 * (box.y + box.height / 2) + translateX + svgBounds.left;
        const predictedY = m12 * (box.x + box.width / 2) + m22 * (box.y + box.height / 2) + translateY + svgBounds.top;
        const paintedX = painted.left + painted.width / 2, paintedY = painted.top + painted.height / 2;
        if (painted.width > 0 && (Math.abs(predictedX - paintedX) > 1 || Math.abs(predictedY - paintedY) > 1)) {
          translateX += paintedX - predictedX;
          translateY += paintedY - predictedY;
        }
      } catch (error) {
      }
      copy.setAttribute("transform", `matrix(${m11} ${m12} ${m21} ${m22} ${translateX} ${translateY})`);
      const style = getComputedStyle(original);
      if (style.vectorEffect === "non-scaling-stroke") {
        const strokeScale = Math.sqrt(Math.abs(m11 * m22 - m12 * m21)) || 1;
        const strokeWidth = parseFloat(style.strokeWidth) || 1;
        copy.setAttribute("stroke-width", String(strokeWidth / strokeScale));
        const dashes = style.strokeDasharray;
        if (dashes && dashes !== "none") copy.setAttribute("stroke-dasharray", dashes.split(",").map((dash) => parseFloat(dash) / strokeScale).join(" "));
      }
    });
  };
  var sanitizeSvg = (svg) => {
    const clone = svg.cloneNode(true);
    const originals = [svg, ...svg.querySelectorAll("*")], copies = [clone, ...clone.querySelectorAll("*")];
    const texts = [];
    inlineStyles(originals, copies, texts);
    clone.querySelectorAll("foreignObject").forEach((foreign) => foreign.remove());
    clone.setAttribute("xmlns", SVGNS);
    bakeTransforms(svg, originals, copies, clone);
    clone.querySelectorAll("g,svg").forEach((group) => {
      if (group !== clone) group.removeAttribute("transform");
    });
    const bounds = svg.getBoundingClientRect();
    clone.setAttribute("viewBox", `0 0 ${bounds.width} ${bounds.height}`);
    clone.removeAttribute("preserveAspectRatio");
    clone.setAttribute("width", String(bounds.width));
    clone.setAttribute("height", String(bounds.height));
    return { markup: clone.outerHTML, texts };
  };

  // src/capture/page/text.ts
  var textLines = (element) => {
    const lines = [];
    let current = null;
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let textNode;
    while (textNode = walker.nextNode()) {
      let ancestor = textNode.parentElement, inline = true;
      while (ancestor && ancestor !== element) {
        if (!/inline|contents/.test(getComputedStyle(ancestor).display)) {
          inline = false;
          break;
        }
        ancestor = ancestor.parentElement;
      }
      if (!inline) continue;
      const text = textNode.textContent || "";
      for (let i = 0; i < text.length; i++) {
        const range = document.createRange();
        range.setStart(textNode, i);
        range.setEnd(textNode, i + 1);
        const box = range.getClientRects()[0];
        if (!box || box.width === 0 && /\s/.test(text[i])) {
          if (current) current.t += text[i];
          continue;
        }
        const mid = box.top + box.height / 2;
        if (!current || Math.abs(mid - current.mid) > box.height * 0.5) {
          if (current) lines.push(current);
          current = { t: text[i], x0: box.left, x1: box.right, top: box.top, bot: box.bottom, mid };
        } else {
          current.t += text[i];
          current.x0 = Math.min(current.x0, box.left);
          current.x1 = Math.max(current.x1, box.right);
          current.top = Math.min(current.top, box.top);
          current.bot = Math.max(current.bot, box.bottom);
        }
      }
    }
    if (current) lines.push(current);
    const own = element.getBoundingClientRect();
    return lines.map((line) => {
      const measured = {
        t: line.t.replace(/\s+/g, " ").trim(),
        r: [round2(line.x0), round2(line.top), round2(line.x1 - line.x0), round2(line.bot - line.top)]
      };
      const centerY = (line.top + line.bot) / 2, probeX = Math.min(line.x1 - 1, line.x0 + 6);
      if (centerY < own.top - 1 || centerY > own.bottom + 1) {
        const hit = document.elementFromPoint(probeX, centerY);
        if (!hit || !(element === hit || element.contains(hit) || hit.contains(element))) measured.hid = 1;
      }
      return measured;
    }).filter((line) => line.t);
  };
  var ellipsisText = (element, style) => {
    const full = element.innerText;
    const canvas = document.createElement("canvas").getContext("2d");
    canvas.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const layoutWidth = element.clientWidth || element.getBoundingClientRect().width;
    const available = layoutWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    if (canvas.measureText(full).width <= available + 0.5) return null;
    const ellipsisWidth = canvas.measureText("\u2026").width;
    let low = 0, high = full.length;
    while (low < high) {
      const middle = low + high + 1 >> 1;
      if (canvas.measureText(full.slice(0, middle)).width + ellipsisWidth <= available + 0.01) low = middle;
      else high = middle - 1;
    }
    return full.slice(0, low) + "\u2026";
  };

  // src/capture/page/elements.ts
  var SKIP_TAGS = ["script", "style", "noscript", "template", "meta", "link", "head", "title"];
  var CONTAINERS = /* @__PURE__ */ new Set([
    "header",
    "nav",
    "section",
    "footer",
    "main",
    "article",
    "aside",
    "li",
    "ul",
    "ol",
    "a",
    "button",
    "form",
    "figure",
    "label"
  ]);
  var fontTuple = (style) => [
    style.fontFamily.split(",")[0].replace(/["']/g, ""),
    style.fontSize,
    style.fontWeight,
    style.lineHeight,
    style.letterSpacing,
    style.color,
    style.textAlign,
    style.textTransform,
    style.fontStyle,
    style.textDecorationLine
  ];
  var isInSvg = (element) => element.namespaceURI === SVGNS && element.tagName.toLowerCase() !== "svg";
  var paddingOf = (style) => [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft].map(parseFloat);
  var imageFields = (record, image, style, rect) => {
    const insetLeft = parseFloat(style.paddingLeft) + parseFloat(style.borderLeftWidth);
    const insetTop = parseFloat(style.paddingTop) + parseFloat(style.borderTopWidth);
    const insetRight = parseFloat(style.paddingRight) + parseFloat(style.borderRightWidth);
    const insetBottom = parseFloat(style.paddingBottom) + parseFloat(style.borderBottomWidth);
    if (insetLeft || insetTop || insetRight || insetBottom) {
      record.cbox = [
        round2(rect.left + insetLeft),
        round2(rect.top + insetTop),
        round2(rect.width - insetLeft - insetRight),
        round2(rect.height - insetTop - insetBottom)
      ];
    }
    record.src = image.currentSrc || image.src;
    record.nat = [image.naturalWidth, image.naturalHeight];
    record.fit = style.objectFit;
    record.opos = style.objectPosition;
    record.radius = style.borderRadius;
    record.alt = image.alt;
  };
  var textFields = (record, element, style, clip) => {
    record.text = element.innerText;
    record.font = fontTuple(style);
    record.disp = style.display;
    record.lines = textLines(element);
    const singleLineEllipsis = style.textOverflow === "ellipsis" && style.whiteSpace === "nowrap";
    record.clamp = style.webkitLineClamp && style.webkitLineClamp !== "none" ? +style.webkitLineClamp : singleLineEllipsis ? 1 : 0;
    if (style.backgroundClip === "text" || style.webkitBackgroundClip === "text") record.textGradient = style.backgroundImage;
    if (style.textDecorationLine && style.textDecorationLine !== "none") {
      record.deco = {
        line: style.textDecorationLine,
        color: style.textDecorationColor,
        thick: style.textDecorationThickness,
        offset: style.textUnderlineOffset
      };
    }
    if (style.textOverflow === "ellipsis" && /nowrap|pre/.test(style.whiteSpace)) {
      const visible = ellipsisText(element, style);
      if (visible) record.visible = visible;
    }
    if (style.overflow !== "visible" || style.overflowY !== "visible") record.ovh = 1;
    if (clip[0] > -1e5) record.tclip = clip.map(round2);
    if (style.textOverflow && style.textOverflow !== "clip") record.tov = style.textOverflow;
    if (style.whiteSpace !== "normal") record.ws = style.whiteSpace;
    const lineClamp = style.webkitLineClamp || style.getPropertyValue("-webkit-line-clamp") || style.getPropertyValue("line-clamp");
    if (lineClamp && lineClamp !== "none") record.lc = parseInt(lineClamp) || 0;
    if (!record.lc) {
      let ancestor = element.parentElement;
      for (let level = 0; level < 4 && ancestor; level++, ancestor = ancestor.parentElement) {
        const ancestorClamp = getComputedStyle(ancestor).webkitLineClamp;
        if (ancestorClamp && ancestorClamp !== "none") {
          record.lc = parseInt(ancestorClamp) || 0;
          record.lcBox = toRect(ancestor.getBoundingClientRect());
          break;
        }
      }
    }
    record.pad = paddingOf(style);
  };
  var boxFields = (record, style) => {
    const background = style.backgroundColor, backgroundImage = style.backgroundImage;
    const borderWidths = [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth].map(parseFloat);
    const borderStyles = [style.borderTopStyle, style.borderRightStyle, style.borderBottomStyle, style.borderLeftStyle];
    const hasBorder = borderWidths.some((width) => width > 0) && borderStyles.some((borderStyle) => borderStyle !== "none");
    const hasBackground = background && background !== "rgba(0, 0, 0, 0)" && background !== "transparent";
    const hasImage = backgroundImage && backgroundImage !== "none" && !record.textGradient;
    if (hasBackground || hasImage || hasBorder || style.boxShadow !== "none" || style.clipPath !== "none" || style.backdropFilter !== "none") {
      record.box = {
        bg: background,
        bi: backgroundImage !== "none" && !record.textGradient ? backgroundImage : void 0,
        bsize: style.backgroundSize,
        bpos: style.backgroundPosition,
        brep: style.backgroundRepeat,
        bw: borderWidths,
        bs: borderStyles,
        bc: [style.borderTopColor, style.borderRightColor, style.borderBottomColor, style.borderLeftColor],
        radius: [style.borderTopLeftRadius, style.borderTopRightRadius, style.borderBottomRightRadius, style.borderBottomLeftRadius],
        shadow: style.boxShadow !== "none" ? style.boxShadow : void 0,
        clip: style.clipPath !== "none" ? style.clipPath : void 0,
        blur: style.backdropFilter !== "none" ? style.backdropFilter : void 0,
        filter: style.filter !== "none" ? style.filter : void 0,
        mix: style.mixBlendMode !== "normal" ? style.mixBlendMode : void 0
      };
    }
  };
  var layoutFields = (record, style) => {
    const display = style.display;
    if (display.includes("flex") || display.includes("grid")) {
      const pixels = (value) => parseFloat(value) || 0;
      const layout = {
        d: display.includes("flex") ? "flex" : "grid",
        dir: style.flexDirection,
        wrap: style.flexWrap,
        jc: style.justifyContent,
        ai: style.alignItems,
        gap: [pixels(style.rowGap), pixels(style.columnGap)],
        inset: [
          pixels(style.paddingTop) + pixels(style.borderTopWidth),
          pixels(style.paddingRight) + pixels(style.borderRightWidth),
          pixels(style.paddingBottom) + pixels(style.borderBottomWidth),
          pixels(style.paddingLeft) + pixels(style.borderLeftWidth)
        ]
      };
      record.lay = layout;
    }
  };
  var pseudoFields = (record, element) => {
    for (const pseudoElement of ["::before", "::after"]) {
      const style = getComputedStyle(element, pseudoElement);
      if (style.content && style.content !== "none" && style.content !== "normal" && style.display !== "none") {
        const paints = style.backgroundColor !== "rgba(0, 0, 0, 0)" || style.backgroundImage !== "none" || parseFloat(style.borderTopWidth) > 0 || style.content.length > 2;
        if (paints) {
          const box = {
            pe: pseudoElement,
            content: style.content.slice(0, 40),
            w: style.width,
            h: style.height,
            top: style.top,
            left: style.left,
            right: style.right,
            bottom: style.bottom,
            pos: style.position,
            bg: style.backgroundColor,
            bi: style.backgroundImage !== "none" ? style.backgroundImage.slice(0, 200) : void 0,
            radius: style.borderRadius,
            bw: style.borderTopWidth,
            bc: style.borderTopColor,
            op: style.opacity,
            color: style.color,
            font: style.fontSize,
            tf: style.transform
          };
          (record.pseudo = record.pseudo || []).push(box);
        }
      }
    }
  };
  var collectElements = (rootSelector) => {
    const root = rootSelector ? document.querySelector(rootSelector) : document.body;
    const elements = [...root.querySelectorAll("*")];
    const indexOf = /* @__PURE__ */ new Map();
    elements.forEach((element, i) => indexOf.set(element, i));
    const effectiveOf = createEffectiveResolver();
    const records = [];
    const emitted = /* @__PURE__ */ new Set();
    const nearestEmittedAncestor = (element) => {
      for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
        if (emitted.has(ancestor)) return indexOf.get(ancestor);
      }
      return -1;
    };
    const emit = (record, element) => {
      records.push(record);
      emitted.add(element);
    };
    for (const element of elements) {
      if (isInSvg(element)) continue;
      const tag = element.tagName.toLowerCase();
      if (SKIP_TAGS.includes(tag)) continue;
      const effective = effectiveOf(element);
      if (!effective.vis || effective.op < 0.01) continue;
      const rect = element.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      const clip = effectiveOf(element.parentElement).clip;
      const clipRight = clip[0] + clip[2], clipBottom = clip[1] + clip[3];
      if (rect.right <= clip[0] || rect.left >= clipRight || rect.bottom <= clip[1] || rect.top >= clipBottom) continue;
      const style = getComputedStyle(element);
      const html = element;
      const record = {
        i: indexOf.get(element),
        p: nearestEmittedAncestor(element),
        tag,
        r: toRect(rect),
        op: Math.round(effective.op * 1e3) / 1e3
      };
      if (html.offsetWidth && (Math.abs(html.offsetWidth - rect.width) > 1 || Math.abs(html.offsetHeight - rect.height) > 1)) {
        record.os = [html.offsetWidth, html.offsetHeight];
      }
      const partlyClipped = rect.left < clip[0] - 0.5 || rect.top < clip[1] - 0.5 || rect.right > clipRight + 0.5 || rect.bottom > clipBottom + 0.5;
      if (clip[0] > -1e5 && partlyClipped) record.clip = clip.map(round2);
      if (element.id) record.htmlId = element.id;
      const classes = typeof element.className === "string" ? element.className : "";
      if (classes) record.cls = classes.slice(0, 120);
      if (style.position !== "static") {
        record.pos = style.position;
        if (style.zIndex !== "auto") record.z = +style.zIndex;
      }
      if (style.transform && style.transform !== "none") record.tf = style.transform;
      if (tag === "svg") {
        const sanitized = sanitizeSvg(element);
        record.svg = sanitized.markup;
        if (sanitized.texts.length) record.svgTexts = sanitized.texts;
        record.color = style.color;
        emit(record, element);
        continue;
      }
      if (tag === "img") {
        imageFields(record, element, style, rect);
        emit(record, element);
        continue;
      }
      if (tag === "video") {
        const video = element;
        record.src = video.currentSrc;
        record.poster = video.poster;
        records.push(record);
        continue;
      }
      if (tag === "canvas") {
        try {
          record.dataUrl = element.toDataURL("image/png");
        } catch (error) {
        }
        records.push(record);
        continue;
      }
      if (tag === "input" || tag === "textarea" || tag === "select") {
        const input = element;
        record.input = { type: input.type, value: input.value, placeholder: input.placeholder };
        record.font = fontTuple(style);
        record.phColor = getComputedStyle(element, "::placeholder").color;
        record.pad = paddingOf(style);
      }
      const ownText = [...element.childNodes].some((child) => child.nodeType === 3 && child.textContent.trim());
      if (ownText) textFields(record, html, style, effective.clip);
      boxFields(record, style);
      pseudoFields(record, element);
      layoutFields(record, style);
      if (record.text || record.box || record.input || record.pseudo || CONTAINERS.has(tag) || element.children.length > 1) emit(record, element);
    }
    return records;
  };

  // src/capture/page/layout.ts
  var qualityEvidence = (records) => {
    const quality = { fontRender: {}, brokenImages: [], lazyPending: 0 };
    const canvas = document.createElement("canvas").getContext("2d");
    const deviationsByFamily = {};
    for (const record of records) {
      if (!record.lines || !record.font || record.lines.length < 1) continue;
      const family = record.font[0];
      if (isGenericFamily(family)) continue;
      const firstLine = record.lines[0];
      if (firstLine.t.length < 6 || record.tf) continue;
      canvas.font = `${record.font[8] || "normal"} ${record.font[2]} ${record.font[1]} "${family}"`;
      if (record.font[4] && record.font[4] !== "normal") continue;
      let text = firstLine.t;
      if (record.font[7] === "uppercase") text = text.toUpperCase();
      const expected = canvas.measureText(text).width;
      if (!expected) continue;
      (deviationsByFamily[family] = deviationsByFamily[family] || []).push(Math.abs(firstLine.r[2] - expected) / expected);
    }
    for (const [family, deviations] of Object.entries(deviationsByFamily)) {
      deviations.sort((first, second) => first - second);
      quality.fontRender[family] = {
        samples: deviations.length,
        medianDev: Math.round(deviations[deviations.length >> 1] * 1e4) / 1e4,
        loaded: document.fonts.check(`16px "${family}"`)
      };
    }
    for (const image of document.images) {
      const rect = image.getBoundingClientRect();
      if (rect.width > 4 && rect.height > 4 && (!image.complete || image.naturalWidth === 0)) {
        quality.brokenImages.push((image.currentSrc || image.src).slice(0, 200));
      }
    }
    quality.lazyPending = [...document.images].filter((image) => image.loading === "lazy" && !image.complete).length;
    return quality;
  };
  var dumpLayout = (rootSelector) => {
    const elements = collectElements(rootSelector);
    const quality = qualityEvidence(elements);
    const documentHeight = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
    const fontsUsed = [...document.fonts].filter((face) => face.status === "loaded").map((face) => `${face.family.replace(/["']/g, "")} ${face.weight} ${face.style}`);
    return {
      url: location.href,
      title: document.title,
      width: window.innerWidth,
      height: documentHeight,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      fonts: [...new Set(fontsUsed)],
      quality,
      elements
    };
  };

  // src/capture/page/fonts.ts
  var declaredFamily = (style) => style.fontFamily.split(",")[0].trim().replace(/["']/g, "");
  var warmupFonts = async () => {
    const combos = /* @__PURE__ */ new Set();
    document.querySelectorAll("body *").forEach((element) => {
      const style = getComputedStyle(element);
      combos.add(declaredFamily(style) + "|" + style.fontWeight);
    });
    await Promise.all([...combos].slice(0, 60).map((combo) => {
      const [family, weight] = combo.split("|");
      return document.fonts.load(`${weight} 16px "${family}"`, "AaBbCc0123").catch(() => null);
    }));
    await document.fonts.ready;
  };
  var fontsReady = async () => {
    await document.fonts.ready;
  };
  var fontPaintDeviation = () => {
    const canvas = document.createElement("canvas").getContext("2d");
    const deviations = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let textNode, visited = 0;
    while ((textNode = walker.nextNode()) && deviations.length < 40 && visited++ < 4e3) {
      const text = (textNode.textContent || "").trim();
      const element = textNode.parentElement;
      if (!element || text.length < 8 || text.length > 60 || element.children.length) continue;
      const style = getComputedStyle(element);
      const family = declaredFamily(style);
      const wraps = style.whiteSpace === "normal" && element.getClientRects().length > 1;
      if (isGenericFamily(family) || style.letterSpacing !== "normal" || style.textTransform !== "none" || wraps) continue;
      const range = document.createRange();
      range.selectNodeContents(textNode);
      const rects = range.getClientRects();
      if (rects.length !== 1) continue;
      canvas.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} "${family}"`;
      const expected = canvas.measureText(textNode.textContent || "").width;
      if (!expected) continue;
      deviations.push(Math.abs(rects[0].width - expected) / expected);
    }
    deviations.sort((first, second) => first - second);
    return deviations.length >= 5 ? deviations[deviations.length >> 1] : 0;
  };
  var requiredFontsLoaded = async (families) => {
    await document.fonts.ready;
    const faces = [...document.fonts];
    const loaded = new Set(faces.filter((face) => face.status === "loaded").map((face) => face.family.replace(/["']/g, "")));
    return families.every((family) => loaded.has(family)) && faces.every((face) => face.status !== "loading");
  };
  var forceLoadFonts = async () => {
    const samples = /* @__PURE__ */ new Map();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let textNode, budget = 2e4;
    while ((textNode = walker.nextNode()) && budget-- > 0) {
      const text = (textNode.textContent || "").trim();
      if (!text || !textNode.parentElement) continue;
      const style = getComputedStyle(textNode.parentElement);
      for (const family of style.fontFamily.split(",").map((name) => name.trim().replace(/["']/g, "")).slice(0, 1)) {
        const combo = `${style.fontStyle}|${style.fontWeight}|${family}`;
        const previous = samples.get(combo) || "";
        if (previous.length < 400) samples.set(combo, previous + text.slice(0, 200));
      }
    }
    const results = [];
    for (const [combo, sample] of samples) {
      const [style, weight, family] = combo.split("|");
      try {
        const faces = await document.fonts.load(`${style} ${weight} 16px "${family}"`, sample);
        results.push(`${family} ${weight} ${style}: ${faces.length}`);
      } catch (error) {
        results.push(`${family} ${weight}: ERR`);
      }
    }
    await document.fonts.ready;
    return results;
  };

  // src/capture/page/overlays.ts
  var OVERLAY_RE = /(cookie|consent|gdpr|ccpa|onetrust|cookiebot|cky-|cmplz|osano|truste|quantcast|didomi|usercentrics|intercom|crisp|drift|hubspot-messages|hs-beacon|zendesk|zEWidget|livechat|tawk|olark|freshchat|launcher|chat-widget|chatbot|tidio|smartsupp|userlike)/i;
  var OVERLAY_IFRAME_RE = /(intercom|crisp|drift|hubspot|zendesk|livechat|tawk|chat|consent|cookie)/i;
  var hideOverlays = () => {
    const hidden = [];
    for (const element of document.querySelectorAll("body *")) {
      const style = getComputedStyle(element);
      if (style.position !== "fixed" && style.position !== "sticky") continue;
      const iframeInfo = element.tagName === "IFRAME" ? element.src || element.title : "";
      const signature = (element.id + " " + (typeof element.className === "string" ? element.className : "") + " " + (element.getAttribute("aria-label") || "") + " " + iframeInfo).slice(0, 400);
      const rect = element.getBoundingClientRect();
      const isHeader = rect.top <= 1 && rect.height < 160 && rect.width > window.innerWidth * 0.8 && !OVERLAY_RE.test(signature);
      if (!isHeader && OVERLAY_RE.test(signature)) {
        element.style.setProperty("display", "none", "important");
        hidden.push(signature.trim().slice(0, 60));
      }
    }
    document.querySelectorAll("iframe").forEach((iframe) => {
      const signature = iframe.id + " " + iframe.title + " " + iframe.src;
      if (OVERLAY_IFRAME_RE.test(signature)) {
        iframe.style.setProperty("display", "none", "important");
        hidden.push("iframe " + signature.slice(0, 50));
      }
    });
    return hidden;
  };

  // src/capture/page/settle.ts
  var scrollHeight = () => document.documentElement.scrollHeight;
  var scrollTo = (y) => window.scrollTo(0, y);
  var frameHeight = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve(document.documentElement.scrollHeight))));
  var fullHeight = () => Math.ceil(Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  var loadLazyImages = () => {
    const lazy = [...document.images].filter((image) => image.loading === "lazy" && !image.complete);
    for (const image of lazy) image.loading = "eager";
    return lazy.length;
  };
  var waitForImages = async () => {
    await Promise.all([...document.images].filter((image) => !image.complete).map((image) => new Promise((resolve) => {
      image.onload = image.onerror = () => resolve();
      setTimeout(resolve, 8e3);
    })));
  };
  var pauseAnimations = () => {
    const styleTag = document.createElement("style");
    styleTag.textContent = "*,*::before,*::after{animation-play-state:paused!important}";
    document.head.appendChild(styleTag);
  };
  var layoutSignature = () => {
    let hash = 0;
    const elements = document.querySelectorAll("body *");
    for (let i = 0; i < elements.length; i += 1) {
      const rect = elements[i].getBoundingClientRect();
      hash = hash * 31 + Math.round(rect.left * 2) * 7 + Math.round(rect.top * 2) | 0;
      const transform = elements[i].style.transform;
      if (transform) for (let j = 0; j < transform.length; j++) hash = hash * 31 + transform.charCodeAt(j) | 0;
    }
    return hash;
  };
  var stopTimers = () => {
    const maxId = setTimeout(() => {
    }, 0);
    for (let i = 0; i <= maxId; i++) {
      clearTimeout(i);
      clearInterval(i);
    }
    window.requestAnimationFrame = () => 0;
  };
  var applyHideAndFreeze = (hide, freeze) => {
    const styleTag = document.createElement("style");
    let css = hide.map((selector) => `${selector}{display:none!important}`).join("\n");
    if (freeze) css += "\n*,*::before,*::after{animation-play-state:paused!important;transition:none!important;caret-color:transparent!important}";
    styleTag.textContent = css;
    document.head.appendChild(styleTag);
    document.querySelectorAll("video").forEach((video) => {
      try {
        video.pause();
      } catch (error) {
      }
    });
  };

  // src/capture/page/index.ts
  var pageApi = {
    warmupFonts,
    fontsReady,
    fontPaintDeviation,
    requiredFontsLoaded,
    forceLoadFonts,
    scrollHeight,
    scrollTo,
    frameHeight,
    fullHeight,
    loadLazyImages,
    waitForImages,
    pauseAnimations,
    layoutSignature,
    stopTimers,
    hideOverlays,
    applyHideAndFreeze,
    dumpLayout
  };
  window.__pbCapture = pageApi;
})();
