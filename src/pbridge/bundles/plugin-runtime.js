(() => {
  // src/plugin/state.ts
  var VERSION = "__PB_VERSION__";
  var previous = storage.pb;
  var runtime = {
    version: VERSION,
    imgs: previous && previous.imgs || {},
    chunks: previous && previous.chunks || {},
    ids: previous && previous.ids || {},
    warnings: [],
    _fit: [],
    _ranges: []
  };
  var isArray = Array.isArray;
  var toNumber = (value, fallback = 0) => value === void 0 || value === null || isNaN(+value) ? fallback : +value;
  var byId = (id) => {
    if (!id) return null;
    const current = penpot.currentPage;
    const found = current && current.getShapeById(id);
    if (found) return found;
    for (const page of penpotUtils.getPages()) {
      if (current && page.id === current.id) continue;
      const shape = page.getShapeById && page.getShapeById(id);
      if (shape) return shape;
    }
    return null;
  };
  var warn = (message) => {
    runtime.warnings.push(String(message));
  };
  var sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  // src/plugin/analysis.ts
  var rootOf = (rootId) => rootId ? byId(rootId) : penpot.root;
  var stats = (rootId) => {
    const counts = {};
    const fonts = {};
    const colors = {};
    penpotUtils.findShapes((shape) => {
      counts[shape.type] = (counts[shape.type] || 0) + 1;
      if (shape.type === "text") {
        const style = `${shape.fontFamily} ${shape.fontWeight} ${shape.fontSize}`;
        fonts[style] = (fonts[style] || 0) + 1;
      }
      if (isArray(shape.fills)) {
        for (const fill of shape.fills) if (fill.fillColor) colors[fill.fillColor] = (colors[fill.fillColor] || 0) + 1;
      }
      return false;
    }, rootOf(rootId));
    return { counts, fonts, colors };
  };
  var lint = (rootId) => {
    const issues = [];
    penpotUtils.findShapes((shape) => {
      if (shape.type === "text" && (!shape.characters || !String(shape.characters).trim())) issues.push({ id: shape.id, n: shape.name, issue: "empty text" });
      if (shape.width < 0.5 || shape.height < 0.5) issues.push({ id: shape.id, n: shape.name, issue: "degenerate size" });
      if (shape.type === "group" && (!shape.children || shape.children.length === 0)) issues.push({ id: shape.id, n: shape.name, issue: "empty group" });
      if (/^(Rectangle|Ellipse|Path|Board|Group)\s*\d*$/.test(shape.name)) issues.push({ id: shape.id, n: shape.name, issue: "default name" });
      return false;
    }, rootOf(rootId));
    return issues.slice(0, 500);
  };

  // src/plugin/paints.ts
  var colorAndOpacity = (color) => {
    if (isArray(color)) return { color: color[0].slice(0, 7).toUpperCase(), opacity: toNumber(color[1], 1) };
    const hex = String(color);
    if (hex.length === 9) return { color: hex.slice(0, 7).toUpperCase(), opacity: parseInt(hex.slice(7), 16) / 255 };
    return { color: hex.toUpperCase(), opacity: 1 };
  };
  var paint = (spec) => {
    if (spec === null || spec === void 0 || spec === false) return [];
    if (isArray(spec) && (isArray(spec[0]) || spec[0] && typeof spec[0] === "object")) return spec.flatMap(paint);
    const fill = spec;
    if (fill && fill.g) {
      const [startX, startY, endX, endY, stops] = fill.g;
      return [{ fillOpacity: toNumber(fill.op, 1), fillColorGradient: {
        type: fill.radial ? "radial" : "linear",
        startX,
        startY,
        endX,
        endY,
        width: 1,
        stops: stops.map(([color2, opacity2, offset]) => ({ color: color2.toUpperCase(), opacity: toNumber(opacity2, 1), offset }))
      } }];
    }
    if (fill && fill.img) {
      const image = runtime.imgs[fill.img];
      if (!image) {
        warn("image not uploaded: " + fill.img);
        return [];
      }
      return [{ fillOpacity: toNumber(fill.op, 1), fillImage: image }];
    }
    const { color, opacity } = colorAndOpacity(spec);
    return [{ fillColor: color, fillOpacity: opacity }];
  };
  var strokes = (spec) => {
    if (!spec) return [];
    const list = isArray(spec) && typeof spec[0] === "object" && !isArray(spec[0]) ? spec : [spec];
    return list.map((stroke) => {
      if (isArray(stroke)) stroke = { c: stroke[0], w: stroke[1], op: stroke[2], style: stroke[3], align: stroke[4] };
      const { color, opacity } = colorAndOpacity(stroke.c || "#000000");
      return {
        strokeColor: color,
        strokeOpacity: toNumber(stroke.op, opacity),
        strokeWidth: toNumber(stroke.w, 1),
        strokeAlignment: stroke.align || "inner",
        strokeStyle: stroke.style || "solid",
        strokeCapStart: stroke.cap,
        strokeCapEnd: stroke.cap
      };
    });
  };
  var shadows = (spec) => (spec || []).map((shadow) => {
    if (isArray(shadow)) shadow = { x: shadow[0], y: shadow[1], blur: shadow[2], spread: shadow[3], c: shadow[4], op: shadow[5], inner: shadow[6] };
    const { color, opacity } = colorAndOpacity(shadow.c || "#000000");
    return {
      style: shadow.inner ? "inner-shadow" : "drop-shadow",
      offsetX: toNumber(shadow.x),
      offsetY: toNumber(shadow.y),
      blur: toNumber(shadow.blur),
      spread: toNumber(shadow.spread),
      color: { color, opacity: toNumber(shadow.op, opacity) },
      hidden: false
    };
  });

  // src/plugin/common.ts
  var applyCommon = (shape, node) => {
    if (node.name) shape.name = node.name;
    if (node.tag) {
      try {
        shape.setPluginData("pb", String(node.tag));
      } catch (error) {
      }
    }
    if (node.fill !== void 0 && shape.type !== "text" && shape.type !== "group") shape.fills = paint(node.fill);
    if (node.stroke) shape.strokes = strokes(node.stroke);
    if (node.sh) shape.shadows = shadows(node.sh);
    if (node.blur) shape.blur = { type: "layer-blur", value: toNumber(node.blur), hidden: false };
    if (node.op !== void 0) shape.opacity = toNumber(node.op, 1);
    if (node.blend) shape.blendMode = node.blend;
    if (node.r !== void 0 && "borderRadius" in shape) {
      if (isArray(node.r)) {
        shape.borderRadiusTopLeft = toNumber(node.r[0]);
        shape.borderRadiusTopRight = toNumber(node.r[1]);
        shape.borderRadiusBottomRight = toNumber(node.r[2]);
        shape.borderRadiusBottomLeft = toNumber(node.r[3]);
      } else shape.borderRadius = toNumber(node.r);
    }
    if (node.hidden) shape.hidden = true;
    if (node.locked) shape.blocked = true;
    if (node.flipX) shape.flipX = true;
    if (node.flipY) shape.flipY = true;
    if (node.cons) {
      if (node.cons[0]) shape.constraintsHorizontal = node.cons[0];
      if (node.cons[1]) shape.constraintsVertical = node.cons[1];
    }
    if (node.data) for (const [key, value] of Object.entries(node.data)) shape.setPluginData(key, String(value));
  };
  var place = (shape, node) => {
    if (node.x !== void 0) shape.x = toNumber(node.x);
    if (node.y !== void 0) shape.y = toNumber(node.y);
  };
  var size = (shape, node) => {
    const width = Math.max(toNumber(node.w, shape.width) || 1, 0.01), height = Math.max(toNumber(node.h, shape.height) || 1, 0.01);
    if (Math.abs(shape.width - width) > 1e-3 || Math.abs(shape.height - height) > 1e-3) shape.resize(width, height);
  };

  // src/plugin/layout.ts
  var sides = (value) => {
    if (value === void 0) return [0, 0, 0, 0];
    if (!isArray(value)) return [toNumber(value), toNumber(value), toNumber(value), toNumber(value)];
    if (value.length === 2) return [toNumber(value[0]), toNumber(value[1]), toNumber(value[0]), toNumber(value[1])];
    return [toNumber(value[0]), toNumber(value[1]), toNumber(value[2]), toNumber(value[3])];
  };
  var track = (value) => {
    if (typeof value === "number") return { type: "fixed", value };
    const text = String(value).trim();
    if (text === "auto") return { type: "auto" };
    if (text.endsWith("fr")) return { type: "flex", value: toNumber(text.slice(0, -2), 1) };
    if (text.endsWith("%")) return { type: "percent", value: toNumber(text.slice(0, -1)) };
    return { type: "fixed", value: toNumber(text.replace("px", "")) };
  };
  var applyLayout = (board, spec) => {
    const layout = spec.type === "grid" ? board.addGridLayout() : board.addFlexLayout();
    if (spec.dir) layout.dir = spec.dir;
    if (spec.type !== "grid" && spec.wrap !== void 0) layout.wrap = spec.wrap ? "wrap" : "nowrap";
    if (spec.gap !== void 0) {
      const [rowGap, columnGap] = isArray(spec.gap) ? spec.gap : [spec.gap, spec.gap];
      layout.rowGap = toNumber(rowGap);
      layout.columnGap = toNumber(columnGap);
    }
    if (spec.padding !== void 0) {
      const [top, right, bottom, left] = sides(spec.padding);
      layout.topPadding = top;
      layout.rightPadding = right;
      layout.bottomPadding = bottom;
      layout.leftPadding = left;
    }
    if (spec.align) layout.alignItems = spec.align;
    if (spec.justify) layout.justifyContent = spec.justify;
    if (spec.alignContent) layout.alignContent = spec.alignContent;
    if (spec.sizing) {
      layout.horizontalSizing = spec.sizing[0];
      layout.verticalSizing = spec.sizing[1];
    }
    if (spec.type === "grid") {
      for (const column of spec.columns || []) {
        const parsed = track(column);
        layout.addColumn(parsed.type, parsed.value);
      }
      for (const row of spec.rows || []) {
        const parsed = track(row);
        layout.addRow(parsed.type, parsed.value);
      }
    }
    return layout;
  };
  var applyChildLayout = (shape, spec) => {
    const child = shape.layoutChild;
    if (!child) return;
    if (spec.sizing) {
      child.horizontalSizing = spec.sizing[0];
      child.verticalSizing = spec.sizing[1];
    }
    if (spec.alignSelf) child.alignSelf = spec.alignSelf;
    if (spec.margin !== void 0) {
      const [top, right, bottom, left] = sides(spec.margin);
      child.topMargin = top;
      child.rightMargin = right;
      child.bottomMargin = bottom;
      child.leftMargin = left;
    }
    if (spec.absolute !== void 0) child.absolute = spec.absolute;
    if (spec.zIndex !== void 0) child.zIndex = spec.zIndex;
    if (spec.minW !== void 0) child.minWidth = spec.minW;
    if (spec.maxW !== void 0) child.maxWidth = spec.maxW;
    if (spec.minH !== void 0) child.minHeight = spec.minH;
    if (spec.maxH !== void 0) child.maxHeight = spec.maxH;
  };

  // src/plugin/fonts.ts
  var fontCache = {};
  var font = (name) => {
    if (fontCache[name]) return fontCache[name];
    const all = penpot.fonts.all;
    const found = all.find((candidate) => candidate.name === name) || all.find((candidate) => candidate.name.toLowerCase() === String(name).toLowerCase()) || penpot.fonts.findByName(name);
    if (!found) throw new Error("font not found: " + name);
    return fontCache[name] = found;
  };
  var variant = (fontObj, weight = 400, italic = false) => {
    const wantedWeight = String(weight === "bold" ? 700 : weight === "normal" ? 400 : weight);
    const variants = fontObj.variants;
    const wantedStyle = italic ? "italic" : "normal";
    let chosen = variants.find((candidate) => String(candidate.fontWeight) === wantedWeight && (candidate.fontStyle || "normal") === wantedStyle);
    if (!chosen) {
      const sameStyle = variants.filter((candidate) => (candidate.fontStyle || "normal") === wantedStyle);
      const distance = (candidate) => Math.abs(+candidate.fontWeight - +wantedWeight);
      chosen = (sameStyle.length ? sameStyle : variants).slice().sort((first, second) => distance(first) - distance(second))[0];
      warn(`font ${fontObj.name} has no weight ${wantedWeight}${italic ? " italic" : ""}, using ${chosen && chosen.fontWeight}`);
    }
    return chosen;
  };

  // src/plugin/text.ts
  var applyTextStyle = (target, style, baseFont) => {
    const fontObj = style.font ? font(style.font) : baseFont;
    if (style.font || style.weight !== void 0 || style.italic !== void 0) {
      const chosen = variant(fontObj, style.weight ?? 400, !!style.italic);
      if (target.type === "text") fontObj.applyToText(target, chosen);
      else fontObj.applyToRange(target, chosen);
    }
    if (style.size !== void 0) target.fontSize = String(style.size);
    if (style.lh !== void 0 && style.size !== void 0) target.lineHeight = String(+(toNumber(style.lh) / toNumber(style.size)).toFixed(4));
    else if (style.lhr !== void 0) target.lineHeight = String(style.lhr);
    if (style.ls !== void 0) target.letterSpacing = String(toNumber(style.ls));
    if (style.color !== void 0) target.fills = paint(style.color);
    if (style.upper) target.textTransform = "uppercase";
    if (style.lower) target.textTransform = "lowercase";
    if (style.cap) target.textTransform = "capitalize";
    if (style.deco) target.textDecoration = style.deco;
  };
  var makeText = (parent, node) => {
    const spec = node.text;
    const text = penpot.createText(spec.text === "" ? " " : spec.text);
    if (!text) throw new Error("createText failed for " + JSON.stringify(spec.text).slice(0, 40));
    runtime._made && runtime._made.push(text);
    const family = spec.font || runtime.defaultFont || "Inter";
    const baseFont = font(family);
    applyTextStyle(text, {
      font: family,
      weight: spec.weight ?? 400,
      italic: spec.italic,
      size: spec.size ?? 16,
      lh: spec.lh,
      lhr: spec.lhr,
      ls: spec.ls,
      color: spec.color ?? "#000000",
      upper: spec.upper,
      lower: spec.lower,
      cap: spec.cap,
      deco: spec.deco
    }, baseFont);
    text.align = spec.align || "left";
    if (spec.valign) text.verticalAlign = spec.valign;
    parent.appendChild(text);
    let grow = spec.grow || (spec.align && spec.align !== "left" ? "auto-height" : "auto-width");
    if (spec.fitW && !spec.text.includes("\n")) grow = "auto-width";
    if (grow === "auto-width") text.growType = "auto-width";
    else {
      text.resize(Math.max(toNumber(node.w, text.width), 1), Math.max(toNumber(node.h, text.height), 1));
      text.growType = grow;
    }
    applyRanges(text, node, baseFont);
    place(text, node);
    if (spec.fitW) {
      const align = spec.align || "left";
      const anchor = align === "center" ? node.x + node.w / 2 : align === "right" ? node.x + node.w : node.x;
      runtime._fit.push({ id: text.id, w: spec.fitW, anchor, align, multi: spec.text.includes("\n"), text: spec.text });
    }
    return text;
  };
  var baseStyleFor = (spec, style) => {
    const family = spec.font || runtime.defaultFont || "Inter";
    const undo = {};
    for (const key of Object.keys(style)) {
      if (key === "color") undo.color = spec.color ?? "#000000";
      else if (key === "weight") {
        undo.weight = spec.weight ?? 400;
        undo.font = family;
      } else if (key === "size") {
        undo.size = spec.size;
        if (spec.lh) undo.lh = spec.lh;
      } else if (key === "deco") undo.deco = "none";
      else if (key === "italic") {
        undo.italic = false;
        undo.weight = spec.weight ?? 400;
      } else if (key === "font") undo.font = family;
    }
    return undo;
  };
  var applyRanges = (text, node, baseFont) => {
    const spec = node.text;
    const length = spec.text.length;
    const ranges = spec.ranges || [];
    for (const range of ranges) {
      const [start, end, style] = range;
      if (start >= end || end > length) {
        warn(`bad range ${start}-${end} on ${node.name || ""}`);
        continue;
      }
      if (end === length && start > 0 && !ranges.some((other) => other !== range && other[1] > start)) {
        applyTextStyle(text, style, baseFont);
        applyTextStyle(text.getRange(0, start), baseStyleFor(spec, style), baseFont);
        for (const earlier of ranges) {
          if (earlier !== range && earlier[1] <= start) applyTextStyle(text.getRange(earlier[0], earlier[1]), earlier[2], baseFont);
        }
        continue;
      }
      applyTextStyle(text.getRange(start, end), style, baseFont);
    }
    if (ranges.length) runtime._ranges.push({ id: text.id, ranges, font: spec.font || runtime.defaultFont || "Inter" });
  };
  var fitTexts = (items, phase) => {
    let changed = 0;
    for (const item of items) {
      const text = byId(item.id);
      if (!text) continue;
      if (phase === 1) {
        const lines = item.text.split("\n");
        const longest = lines.reduce((best, line) => line.length > best.length ? line : best, "");
        if (text.growType !== "auto-width") continue;
        const current = +text.letterSpacing || 0;
        const fitted = +(current + (item.w - text.width) / Math.max(1, longest.length - 1)).toFixed(3);
        if (Math.abs(fitted - current) > 0.01 && Math.abs(fitted - current) < 3) {
          text.letterSpacing = String(fitted);
          changed++;
        }
      } else {
        if (item.align === "center" && text.growType === "auto-width") {
          text.x = item.anchor - text.width / 2;
          changed++;
        } else if (item.align === "right" && text.growType === "auto-width") {
          text.x = item.anchor - text.width;
          changed++;
        }
      }
    }
    return changed;
  };
  var verifyRanges = (items) => {
    let fixed = 0;
    const bad = [];
    const normalize = (color) => String(color || "").toUpperCase();
    for (const item of items) {
      const text = byId(item.id);
      if (!text) continue;
      for (const [start, end, style] of item.ranges) {
        try {
          const range = text.getRange(start, end);
          let ok = true;
          if (style.color !== void 0 && !(style.color && style.color.g)) {
            const wanted = isArray(style.color) ? style.color[0] : style.color;
            const got = isArray(range.fills) && range.fills[0] ? range.fills[0].fillColor : null;
            if (normalize(got) !== normalize(wanted)) ok = false;
          }
          if (style.weight !== void 0 && String(range.fontWeight) !== String(style.weight)) ok = false;
          if (style.size !== void 0 && String(range.fontSize) !== String(style.size)) ok = false;
          if (!ok) {
            applyTextStyle(range, style, font(item.font));
            fixed++;
            bad.push([item.id, start, end]);
          }
        } catch (error) {
          bad.push([item.id, start, end, String(error.message || error)]);
        }
      }
    }
    return { fixed, bad: bad.slice(0, 20) };
  };

  // src/plugin/builder.ts
  var buildFittedImage = (parent, node, image) => {
    const fit = node.fit;
    const naturalWidth = toNumber(image.width) || node.nat && toNumber(node.nat[0]) || node.w;
    const naturalHeight = toNumber(image.height) || node.nat && toNumber(node.nat[1]) || node.h;
    const scale = fit === "cover" ? Math.max(node.w / naturalWidth, node.h / naturalHeight) : Math.min(node.w / naturalWidth, node.h / naturalHeight);
    const imageWidth = naturalWidth * scale, imageHeight = naturalHeight * scale;
    const alignX = node.pos ? toNumber(node.pos[0], 0.5) : 0.5, alignY = node.pos ? toNumber(node.pos[1], 0.5) : 0.5;
    let shape;
    if (fit === "contain") {
      shape = penpot.createRectangle();
      parent.appendChild(shape);
      shape.resize(imageWidth, imageHeight);
      shape.x = node.x + (node.w - imageWidth) * alignX;
      shape.y = node.y + (node.h - imageHeight) * alignY;
      shape.fills = [{ fillOpacity: toNumber(node.iop, 1), fillImage: image }];
      applyCommon(shape, { ...node, fill: void 0 });
    } else {
      shape = penpot.createBoard();
      parent.appendChild(shape);
      shape.resize(node.w, node.h);
      shape.x = node.x;
      shape.y = node.y;
      shape.fills = [];
      shape.clipContent = true;
      applyCommon(shape, { ...node, fill: void 0 });
      const picture = penpot.createRectangle();
      shape.appendChild(picture);
      picture.resize(imageWidth, imageHeight);
      picture.x = node.x + (node.w - imageWidth) * alignX;
      picture.y = node.y + (node.h - imageHeight) * alignY;
      picture.fills = [{ fillOpacity: toNumber(node.iop, 1), fillImage: image }];
      picture.name = (node.name || node.img) + " image";
    }
    return shape;
  };
  var build = (root, parent, timings) => {
    const made = runtime._made = [];
    const buildNode = (node, container) => {
      let shape = null;
      const type = node.t;
      const started = Date.now();
      if (type === "board" || type === "frame") {
        shape = penpot.createBoard();
        container.appendChild(shape);
        size(shape, node);
        place(shape, node);
        shape.fills = paint(node.fill === void 0 ? null : node.fill);
        shape.clipContent = !!node.clip;
        applyCommon(shape, { ...node, fill: void 0 });
        const layout = node.layout ? applyLayout(shape, node.layout) : null;
        for (const child of node.children || []) {
          const built = buildNode(child, shape);
          if (built && layout && node.layout.type === "grid" && child.child && child.child.cell) {
            layout.appendChild(built, child.child.cell[0], child.child.cell[1]);
          }
        }
        if (node.flex) {
          const rawLayout = shape.addFlexLayout();
          Object.assign(rawLayout, node.flex);
        }
      } else if (type === "rect") {
        shape = penpot.createRectangle();
        container.appendChild(shape);
        size(shape, node);
        place(shape, node);
        applyCommon(shape, node);
      } else if (type === "ellipse") {
        shape = penpot.createEllipse();
        container.appendChild(shape);
        size(shape, node);
        place(shape, node);
        applyCommon(shape, node);
      } else if (type === "path" || type === "line") {
        shape = penpot.createPath();
        shape.content = node.d;
        container.appendChild(shape);
        shape.fills = paint(node.fill === void 0 ? null : node.fill);
        applyCommon(shape, { ...node, fill: void 0 });
        if (node.stroke) shape.strokes = strokes(node.stroke).map((stroke) => ({ ...stroke, strokeAlignment: "center" }));
      } else if (type === "text") {
        shape = makeText(container, node);
        applyCommon(shape, { ...node, fill: void 0, stroke: void 0 });
      } else if (type === "image") {
        const image = runtime.imgs[node.img];
        if (!image) {
          warn("image not uploaded: " + node.img);
          return null;
        }
        const fit = node.fit || "fill";
        if (fit === "cover" || fit === "contain") shape = buildFittedImage(container, node, image);
        else {
          shape = penpot.createRectangle();
          container.appendChild(shape);
          size(shape, node);
          place(shape, node);
          shape.fills = [{ fillOpacity: toNumber(node.iop, 1), fillImage: image }];
          applyCommon(shape, { ...node, fill: void 0 });
        }
        if (!node.name) shape.name = node.img;
      } else if (type === "svg") {
        shape = penpot.createShapeFromSvg(node.svg);
        if (!shape) {
          warn("svg import failed: " + (node.name || ""));
          return null;
        }
        container.appendChild(shape);
        if (node.w && node.h && (Math.abs(shape.width - node.w) > 0.5 || Math.abs(shape.height - node.h) > 0.5)) shape.resize(node.w, node.h);
        place(shape, node);
        applyCommon(shape, { ...node, fill: void 0, stroke: void 0, r: void 0 });
      } else if (type === "group") {
        const children = (node.children || []).map((child) => buildNode(child, container)).filter(Boolean);
        if (!children.length) return null;
        shape = penpot.group(children);
        if (!shape) return null;
        applyCommon(shape, { ...node, fill: void 0, stroke: void 0, r: void 0 });
      } else if (type === "component") {
        const component = penpot.library.local.components.find((candidate) => candidate.name === node.ref || candidate.id === node.ref);
        if (!component) {
          warn("component not found: " + node.ref);
          return null;
        }
        shape = component.instance();
        container.appendChild(shape);
        place(shape, node);
        if (node.w && node.h) size(shape, node);
        applyCommon(shape, node);
      } else {
        throw new Error("unknown node type: " + type);
      }
      if (shape && node.child) applyChildLayout(shape, node.child);
      if (shape && node.key) runtime.ids[node.key] = shape.id;
      if (shape && node.component) {
        const component = penpot.library.local.createComponent([shape]);
        if (component && typeof node.component === "string") component.name = node.component;
      }
      if (shape) made.push(shape);
      if (timings && !node.children) timings[type] = (timings[type] || 0) + Date.now() - started;
      return shape;
    };
    return buildNode(root, parent);
  };
  var buildMany = (nodes, parentId) => {
    const parent = parentId ? byId(parentId) : penpot.root;
    if (!parent) throw new Error("parent not found " + parentId);
    runtime.warnings = [];
    runtime._fit = [];
    runtime._ranges = [];
    const started = Date.now();
    const msByType = {};
    let count = 0;
    for (const node of nodes) {
      let shape;
      try {
        shape = build(node, parent, msByType);
      } catch (error) {
        for (const made of (runtime._made || []).slice().reverse()) {
          try {
            made.remove();
          } catch (_) {
          }
        }
        throw error;
      }
      if (shape) count++;
    }
    const allKeys = {};
    const collect = (node) => {
      if (node.key && runtime.ids[node.key]) allKeys[node.key] = runtime.ids[node.key];
      (node.children || []).forEach(collect);
    };
    nodes.forEach(collect);
    return {
      built: count,
      ids: allKeys,
      ms: Date.now() - started,
      msByType,
      warnings: runtime.warnings.slice(0, 50),
      fit: runtime._fit.length,
      ranges: runtime._ranges.length,
      fitItems: runtime._fit,
      rangeItems: runtime._ranges
    };
  };
  var removeMany = (ids) => {
    let removed = 0;
    for (const id of ids) {
      const shape = byId(id);
      if (shape) {
        shape.remove();
        removed++;
      }
    }
    return removed;
  };
  var existing = (ids) => ids.filter((id) => !!byId(id));
  var groupShapes = (ids, name) => {
    const group = penpot.group(ids.map(byId).filter(Boolean));
    if (group && name) group.name = name;
    return group && group.id;
  };
  var ungroup = (id) => {
    const group = byId(id);
    if (group) penpot.ungroup(group);
    return true;
  };

  // src/plugin/chunks.ts
  var chunkPut = (id, index, total, data) => {
    (runtime.chunks[id] = runtime.chunks[id] || { total, parts: [] }).parts[index] = data;
    return index;
  };
  var chunkTake = (id) => {
    const transfer = runtime.chunks[id];
    if (!transfer) throw new Error("chunk " + id + " missing");
    if (transfer.parts.filter((part) => part !== void 0).length !== transfer.total) throw new Error("chunk " + id + " incomplete");
    delete runtime.chunks[id];
    return transfer.parts.join("");
  };

  // src/plugin/query.ts
  var find = (query = {}) => {
    if (query.id) {
      const shape = byId(query.id);
      return shape ? [shape] : [];
    }
    if (query.ids) return query.ids.map(byId).filter(Boolean);
    if (query.key) {
      const shape = byId(runtime.ids[query.key]);
      return shape ? [shape] : [];
    }
    const root = query.within ? byId(query.within) : null;
    const namePattern = query.re ? new RegExp(query.re, query.flags || "i") : null;
    const matches = (shape) => {
      if (query.name !== void 0 && shape.name !== query.name) return false;
      if (namePattern && !namePattern.test(shape.name)) return false;
      if (query.type && shape.type !== query.type) return false;
      if (query.text !== void 0 && !(shape.type === "text" && String(shape.characters).includes(query.text))) return false;
      if (query.bbox) {
        const [x, y, width, height] = query.bbox;
        if (shape.x > x + width || shape.x + shape.width < x || shape.y > y + height || shape.y + shape.height < y) return false;
      }
      return true;
    };
    const found = penpotUtils.findShapes(matches, root);
    return query.limit ? found.slice(0, query.limit) : found;
  };

  // src/plugin/patch.ts
  var applyOp = (shape, operation) => {
    const changes = operation.set || {};
    if (operation.move) {
      shape.x += toNumber(operation.move[0]);
      shape.y += toNumber(operation.move[1]);
    }
    if (operation.scale) {
      shape.resize(shape.width * operation.scale, shape.height * operation.scale);
    }
    if (changes.w !== void 0 || changes.h !== void 0) {
      if (shape.type === "text") {
        shape.resize(toNumber(changes.w, shape.width), toNumber(changes.h, shape.height));
        shape.growType = changes.grow || "auto-height";
      } else shape.resize(toNumber(changes.w, shape.width), toNumber(changes.h, shape.height));
    }
    if (changes.x !== void 0) shape.x = toNumber(changes.x);
    if (changes.y !== void 0) shape.y = toNumber(changes.y);
    if (changes.text !== void 0 && shape.type === "text") shape.characters = changes.text;
    if (changes.textStyle && shape.type === "text") {
      const baseFont = font(changes.textStyle.font || shape.fontFamily);
      const target = changes.textStyle.range ? shape.getRange(changes.textStyle.range[0], changes.textStyle.range[1]) : shape;
      applyTextStyle(target, changes.textStyle, baseFont);
    }
    if (changes.align && shape.type === "text") shape.align = changes.align;
    if (changes.grow && shape.type === "text") shape.growType = changes.grow;
    applyCommon(shape, { ...changes, x: void 0, y: void 0, fill: shape.type === "text" ? void 0 : changes.fill });
    if (shape.type === "text" && changes.fill !== void 0) shape.fills = paint(changes.fill);
    if (changes.visible !== void 0) shape.hidden = !changes.visible;
    if (operation.rename) shape.name = operation.rename;
    if (operation.z === "front") shape.bringToFront();
    else if (operation.z === "back") shape.sendToBack();
    else if (typeof operation.z === "number") shape.setParentIndex(operation.z);
    if (operation.reparent) {
      const newParent = byId(operation.reparent);
      const keepX = shape.x, keepY = shape.y;
      newParent.appendChild(shape);
      shape.x = keepX;
      shape.y = keepY;
    }
  };
  var patch = (ops) => {
    const report = [];
    for (const operation of ops) {
      const shapes = find(operation.sel || {});
      if (!shapes.length) {
        report.push({ sel: operation.sel, error: "no match" });
        continue;
      }
      for (const shape of shapes) {
        try {
          if (operation.remove) {
            shape.remove();
            report.push({ id: shape.id, removed: true });
            continue;
          }
          applyOp(shape, operation);
          report.push({ id: shape.id, name: shape.name, ok: true });
        } catch (error) {
          report.push({ id: shape.id, error: String(error.message || error) });
        }
      }
    }
    return report;
  };

  // src/plugin/serialize.ts
  var TYPE_MAP = {
    rectangle: "rect",
    ellipse: "ellipse",
    text: "text",
    path: "path",
    board: "board",
    group: "group",
    image: "image",
    "svg-raw": "svg",
    bool: "group"
  };
  var round2 = (value) => Math.round(value * 100) / 100;
  var paintOut = (fills) => {
    if (!isArray(fills)) return fills === "mixed" ? "mixed" : null;
    const paints = fills.map((fill) => {
      if (fill.fillImage) return { img: fill.fillImage.name || fill.fillImage.id, op: fill.fillOpacity };
      if (fill.fillColorGradient) {
        const gradient = fill.fillColorGradient;
        const stops = gradient.stops.map((stop) => [stop.color, stop.opacity, stop.offset]);
        return {
          g: [gradient.startX, gradient.startY, gradient.endX, gradient.endY, stops],
          radial: gradient.type === "radial" ? 1 : void 0,
          op: fill.fillOpacity
        };
      }
      const color = (fill.fillColor || "").toUpperCase();
      return (fill.fillOpacity ?? 1) >= 0.999 ? color : [color, +(+fill.fillOpacity).toFixed(3)];
    });
    return paints.length === 0 ? null : paints.length === 1 ? paints[0] : paints;
  };
  var serialize = (shape, depth = 99, opts = {}) => {
    if (!shape) return null;
    const node = {
      t: TYPE_MAP[shape.type] || shape.type,
      id: shape.id,
      name: shape.name,
      x: round2(shape.x),
      y: round2(shape.y),
      w: round2(shape.width),
      h: round2(shape.height)
    };
    if (shape.type !== "group" && shape.type !== "text") {
      const fill = paintOut(shape.fills);
      if (fill !== null) node.fill = fill;
    }
    if (isArray(shape.strokes) && shape.strokes.length) {
      node.stroke = shape.strokes.map((stroke) => ({
        c: stroke.strokeColor,
        w: stroke.strokeWidth,
        op: stroke.strokeOpacity,
        style: stroke.strokeStyle,
        align: stroke.strokeAlignment
      }));
    }
    if (isArray(shape.shadows) && shape.shadows.length) {
      node.sh = shape.shadows.map((shadow) => [
        shadow.offsetX,
        shadow.offsetY,
        shadow.blur,
        shadow.spread,
        shadow.color && shadow.color.color,
        shadow.color && shadow.color.opacity,
        shadow.style === "inner-shadow" ? 1 : void 0
      ]);
    }
    if (shape.opacity !== void 0 && shape.opacity < 0.999) node.op = shape.opacity;
    if (shape.hidden) node.hidden = true;
    if ("borderRadius" in shape && shape.type !== "text") {
      const corners = [shape.borderRadiusTopLeft, shape.borderRadiusTopRight, shape.borderRadiusBottomRight, shape.borderRadiusBottomLeft].map((value) => toNumber(value));
      if (corners.some((value) => value)) node.r = corners.every((value) => value === corners[0]) ? corners[0] : corners;
    }
    if (shape.type === "board") {
      node.clip = !!shape.clipContent;
      if (shape.flex) node.flex = { dir: shape.flex.dir, rowGap: shape.flex.rowGap, columnGap: shape.flex.columnGap };
    }
    if (shape.type === "path" && opts.paths) node.d = String(shape.content);
    if (shape.type === "text") {
      node.text = {
        text: shape.characters,
        font: shape.fontFamily,
        weight: shape.fontWeight,
        size: +shape.fontSize || shape.fontSize,
        lhr: +shape.lineHeight || shape.lineHeight,
        ls: +shape.letterSpacing || 0,
        color: paintOut(shape.fills),
        align: shape.align,
        grow: shape.growType
      };
      if (shape.textTransform && shape.textTransform !== "none") node.text.transform = shape.textTransform;
    }
    if (shape.isComponentMainInstance && shape.isComponentMainInstance()) node.mainComponent = true;
    if (depth > 0 && shape.children && shape.children.length) node.children = shape.children.map((child) => serialize(child, depth - 1, opts));
    return node;
  };
  var tree = (root, depth = 3) => {
    const entry = (shape, levels) => {
      const item = {
        id: shape.id,
        n: shape.name,
        t: shape.type,
        b: [Math.round(shape.x), Math.round(shape.y), Math.round(shape.width), Math.round(shape.height)]
      };
      if (shape.type === "text") item.txt = String(shape.characters).slice(0, 40);
      if (levels > 0 && shape.children && shape.children.length) item.c = shape.children.map((child) => entry(child, levels - 1));
      else if (shape.children && shape.children.length) item.nc = shape.children.length;
      return item;
    };
    return entry(root, depth);
  };

  // src/plugin/assets.ts
  var b64 = (encoded) => {
    const binary = atob(encoded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  };
  var BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  var toBase64 = (bytes) => {
    const parts = [];
    for (let i = 0; i < bytes.length; i += 3) {
      const first = bytes[i], second = bytes[i + 1], third = bytes[i + 2];
      const triple = first << 16 | (second ?? 0) << 8 | (third ?? 0);
      parts.push(BASE64_ALPHABET[triple >> 18 & 63] + BASE64_ALPHABET[triple >> 12 & 63] + (second === void 0 ? "=" : BASE64_ALPHABET[triple >> 6 & 63]) + (third === void 0 ? "=" : BASE64_ALPHABET[triple & 63]));
    }
    return parts.join("");
  };
  var exportShape = async (id, type = "png", scale = 1) => {
    const shape = byId(id);
    if (!shape) throw new Error("shape not found: " + id);
    const bytes = await shape.export({ type, scale });
    return { id, name: shape.name, type, scale, base64: toBase64(bytes) };
  };
  var crc32 = (bytes) => {
    let value, crc = 4294967295;
    for (let i = 0; i < bytes.length; i++) {
      value = (crc ^ bytes[i]) & 255;
      for (let bit = 0; bit < 8; bit++) value = value & 1 ? value >>> 1 ^ 3988292384 : value >>> 1;
      crc = crc >>> 8 ^ value;
    }
    return (crc ^ 4294967295) >>> 0;
  };
  var uploadB64 = async (key, data, mime, crc) => {
    const bytes = b64(data);
    if (crc !== void 0 && crc32(bytes) !== crc) throw new Error("CRC mismatch for " + key);
    const image = await penpot.uploadMediaData(key, bytes, mime || "image/png");
    runtime.imgs[key] = image;
    return image;
  };
  var uploadUrl = async (key, url) => {
    const image = await penpot.uploadMediaUrl(key, url);
    runtime.imgs[key] = image;
    return image;
  };
  var uploadUrls = async (items) => {
    const settled = await Promise.allSettled(items.map((item) => penpot.uploadMediaUrl(item.key, item.url)));
    const results = {};
    settled.forEach((outcome, i) => {
      const key = items[i].key;
      if (outcome.status === "fulfilled" && outcome.value) {
        runtime.imgs[key] = outcome.value;
        results[key] = outcome.value;
      } else results[key] = { error: String(outcome.status === "rejected" ? outcome.reason && outcome.reason.message || outcome.reason : "empty result") };
    });
    return results;
  };
  var registerImages = (descriptors) => {
    for (const [key, image] of Object.entries(descriptors)) runtime.imgs[key] = image;
    return Object.keys(runtime.imgs).length;
  };

  // src/plugin/library.ts
  var addColor = (name, hex, opacity = 1) => {
    const library = penpot.library.local;
    let color = library.colors.find((candidate) => candidate.name === name);
    if (!color) color = library.createColor();
    color.name = name;
    color.color = hex;
    color.opacity = opacity;
    return color.id;
  };
  var addTypography = (name, style) => {
    const library = penpot.library.local;
    let typography = library.typographies.find((candidate) => candidate.name === name);
    if (!typography) typography = library.createTypography();
    typography.name = name;
    if (style.font) {
      const fontObj = font(style.font);
      typography.fontId = fontObj.fontId;
      typography.fontFamily = fontObj.fontFamily;
      const chosen = variant(fontObj, style.weight || 400, style.italic);
      typography.fontVariantId = chosen.fontVariantId;
      typography.fontWeight = String(chosen.fontWeight);
    }
    if (style.size) typography.fontSize = String(style.size);
    if (style.lh && style.size) typography.lineHeight = String(+(style.lh / style.size).toFixed(4));
    if (style.ls !== void 0) typography.letterSpacing = String(style.ls);
    if (style.upper) typography.textTransform = "uppercase";
    return typography.id;
  };
  var makeComponent = (ids, name) => {
    const component = penpot.library.local.createComponent(ids.map(byId).filter(Boolean));
    if (component && name) component.name = name;
    return component && component.id;
  };

  // src/plugin/index.ts
  var api = Object.assign(runtime, {
    // utils
    sleep,
    byId,
    warn,
    // chunked transfer
    chunkPut,
    chunkTake,
    // fonts & paints
    font,
    variant,
    paint,
    strokes,
    shadows,
    // building
    makeText,
    build,
    buildMany,
    fitTexts,
    verifyRanges,
    groupShapes,
    ungroup,
    removeMany,
    existing,
    // reading
    serialize,
    tree,
    find,
    // editing
    patch,
    // assets
    b64,
    crc32,
    uploadB64,
    uploadUrl,
    uploadUrls,
    registerImages,
    toBase64,
    exportShape,
    // library
    addColor,
    addTypography,
    makeComponent,
    // analysis
    stats,
    lint
  });
  storage.pb = api;
})();
