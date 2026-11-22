/* Read-only scene graph probe. No DOM writes, canvas drawing, or page callbacks.
 * The caller evaluates this IIFE after the render readiness contract settles.
 * Bounds are deliberate: at most 1600 elements and 600 visible text nodes.
 */
(() => {
  "use strict";
  const MAX_ELEMENTS = 1600, MAX_TEXTS = 600;
  const root = document.documentElement;
  const canvas = {width: innerWidth, height: innerHeight};
  const elements = {}, texts = {};
  const round = n => Math.round(n * 1000) / 1000;
  const box = r => ({x:round(r.x), y:round(r.y), width:round(r.width), height:round(r.height)});
  const selector = el => {
    if (el.id && document.querySelectorAll(`#${CSS.escape(el.id)}`).length === 1)
      return `#${CSS.escape(el.id)}`;
    const parts = [];
    for (let p = el; p && p.nodeType === 1; p = p.parentElement) {
      if (p.id && document.querySelectorAll(`#${CSS.escape(p.id)}`).length === 1) {
        parts.unshift(`#${CSS.escape(p.id)}`); break;
      }
      let n = 1;
      for (let q = p.previousElementSibling; q; q = q.previousElementSibling)
        if (q.localName === p.localName) n++;
      parts.unshift(`${p.localName}:nth-of-type(${n})`);
    }
    return parts.join(" > ");
  };
  const parseColor = value => {
    if (!value || value === "transparent") return [0,0,0,0];
    const m = value.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)$/i);
    return m ? [Number(m[1]), Number(m[2]), Number(m[3]), m[4] === undefined ? 1 : Number(m[4])] : null;
  };
  const over = (top, bottom) => {
    const a = top[3], b = bottom[3], alpha = a + b * (1-a);
    if (!alpha) return [0,0,0,0];
    return [0,1,2].map(i => (top[i]*a + bottom[i]*b*(1-a))/alpha).concat(alpha);
  };
  const cssColor = c => `rgb(${c.slice(0,3).map(n => Math.round(n)).join(", ")})`;
  const gradient = (value, el, x, y) => {
    // Deliberately narrow: a two-stop CSS linear gradient with an explicit
    // angle and rgb/rgba stops. Any other syntax returns null, not a guess.
    const m = value.match(/^linear-gradient\((90deg|270deg|180deg|0deg),\s*(rgba?\([^)]*\)),\s*(rgba?\([^)]*\))\)$/i);
    if (!m) return null;
    const a = parseColor(m[2]), b = parseColor(m[3]);
    if (!a || !b) return null;
    const r = el.getBoundingClientRect();
    let t = (m[1] === "90deg" || m[1] === "270deg") ? (x-r.left)/r.width : (y-r.top)/r.height;
    if (m[1] === "270deg" || m[1] === "0deg") t = 1-t;
    t = Math.min(1,Math.max(0,t));
    return a.map((v,i) => v + (b[i]-v)*t);
  };
  const ownPaint = (el, x, y, pseudo) => {
    const s = getComputedStyle(el, pseudo || null);
    if (s.filter !== "none" || s.mixBlendMode !== "normal" ||
        s.backdropFilter !== "none" || s.backgroundBlendMode !== "normal" ||
        Number(s.opacity) !== 1) return null;
    let color = parseColor(s.backgroundColor);
    if (color === null) return null;
    if (s.backgroundImage !== "none") {
      const g = gradient(s.backgroundImage, el, x, y);
      if (!g) return null;
      color = over(g, color);
    }
    return color;
  };
  const backgroundAt = (el, x, y) => {
    // elementsFromPoint is in paint order and includes sibling layers behind
    // the label. Fold their backgrounds bottom-to-top. ::before is included
    // only for the full-cover inset:0 case, where its bounds are provable.
    const stack = document.elementsFromPoint(x,y);
    if (!stack.includes(el)) return null;
    let color = [255,255,255,1]; // Chrome render's declared opaque white backdrop.
    const labelIndex = stack.indexOf(el);
    for (let i=stack.length-1; i>=labelIndex; i--) {
      const layer = stack[i];
      const own = ownPaint(layer,x,y,null);
      if (!own) return null;
      color = over(own,color);
      for (const pseudo of ["::before","::after"]) {
        const ps = getComputedStyle(layer,pseudo);
        if (ps.content === "none" || ps.content === "normal") continue;
        const p = ownPaint(layer,x,y,pseudo);
        if (!p) return null;
        if (p[3] === 0) continue;
        if (pseudo === "::after" || ps.position !== "absolute" ||
            ![ps.top,ps.right,ps.bottom,ps.left].every(v => v === "0px")) return null;
        color = over(p,color);
      }
    }
    return {color:cssColor(color), rgba:color.map(round), sample:{x:round(x),y:round(y)},
            method:"bounded-css-paint-composition"};
  };
  const luminance = c => {
    const linear = n => {n/=255; return n<=.04045 ? n/12.92 : ((n+.055)/1.055)**2.4;};
    return .2126*linear(c[0]) + .7152*linear(c[1]) + .0722*linear(c[2]);
  };
  const contrast = (a,b) => {
    const x=luminance(a), y=luminance(b);
    return round((Math.max(x,y)+.05)/(Math.min(x,y)+.05));
  };
  const candidates = Array.from(document.querySelectorAll("*"));
  if (candidates.length > MAX_ELEMENTS) return {error:`element limit exceeded: ${candidates.length} > ${MAX_ELEMENTS}`};
  for (const el of candidates) {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width <= 0 || r.height <= 0 || s.display === "none") continue;
    const key = selector(el);
    elements[key] = {box:box(r), overflow:{left:round(Math.max(0,-r.left)),
      top:round(Math.max(0,-r.top)), right:round(Math.max(0,r.right-canvas.width)),
      bottom:round(Math.max(0,r.bottom-canvas.height))}, overlaps:[]};
  }
  for (const el of candidates) {
    const a = elements[selector(el)];
    if (!a || !el.parentElement) continue;
    let next = el.nextElementSibling;
    while (next) {
      const b = elements[selector(next)];
      if (b) {
        const w = Math.max(0,Math.min(a.box.x+a.box.width,b.box.x+b.box.width)-Math.max(a.box.x,b.box.x));
        const h = Math.max(0,Math.min(a.box.y+a.box.height,b.box.y+b.box.height)-Math.max(a.box.y,b.box.y));
        if (w*h > 0) {
          a.overlaps.push({selector:selector(next),area:round(w*h)});
          b.overlaps.push({selector:selector(el),area:round(w*h)});
        }
      }
      next = next.nextElementSibling;
    }
  }
  let textCount=0;
  const walker = document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node=walker.currentNode, el=node.parentElement;
    if (!el || !node.textContent.trim()) continue;
    const parent=selector(el), s=getComputedStyle(el);
    if (!elements[parent] || s.visibility === "hidden" || Number(s.opacity) === 0) continue;
    const range=document.createRange(); range.selectNodeContents(node);
    const r=range.getBoundingClientRect();
    if (r.width<=0 || r.height<=0) continue;
    if (++textCount > MAX_TEXTS) return {error:`text limit exceeded: ${textCount} > ${MAX_TEXTS}`};
    const index=Array.prototype.indexOf.call(el.childNodes,node);
    const x=Math.min(canvas.width-1,Math.max(0,r.x+r.width/2));
    const y=Math.min(canvas.height-1,Math.max(0,r.y+r.height/2));
    // The painted glyph colour: SVG text paints `fill`; HTML text paints
    // -webkit-text-fill-color (which defaults to `color`); background-clip:text
    // paints the element's background through the glyphs, so no plain colour.
    const svgText=el instanceof SVGElement;
    const clipText=(s.webkitBackgroundClip||s.backgroundClip||"").includes("text");
    const fgValue=svgText ? s.fill : (s.webkitTextFillColor || s.color);
    const fg=clipText ? null : parseColor(fgValue);
    const bg=backgroundAt(el,x,y);
    const actualFg=fg && bg ? over(fg,bg.rgba) : null;
    const size=parseFloat(s.fontSize);
    if (!texts[parent]) texts[parent]=[];
    const allLines=Array.from(range.getClientRects()).filter(q => q.width>0 && q.height>0);
    const intersects=(q) => q.right>r.left && q.left<r.right && q.bottom>r.top && q.top<r.bottom;
    // Effects on the text or an ancestor transform the painted glyph colour,
    // so the computed colour is not what a reader sees; record them by name.
    // Opacity is foldable only when nothing inside the faded group paints
    // under the text: then the glyph is the text colour at that alpha over the
    // pixel behind. Any painted layer in the group (ancestor, sibling, or
    // pseudo-element) is composited into the group first, so the twin pixel no
    // longer shows what the glyph blends with. Boxes, not elementsFromPoint,
    // so pointer-events:none overlays are seen.
    const paints=(st) => (parseColor(st.backgroundColor)||[0,0,0,1])[3]>0 || st.backgroundImage!=="none";
    const paintsUnder=(g) => [g, ...Array.from(g.querySelectorAll("*")).slice(0,400)].some(n => {
      if (!intersects(n.getBoundingClientRect())) return false;
      const ns=getComputedStyle(n);
      if (paints(ns) || (n instanceof SVGGeometryElement && ns.fill!=="none")) return true;
      return ["::before","::after"].some(ps => {const pst=getComputedStyle(n,ps);
        return pst.content!=="none" && pst.content!=="normal" && paints(pst);});
    });
    const effects=clipText ? ["background-clip:text"] : [];
    let alpha=1;
    // The visible clip: ancestors (and the text's own element) whose overflow
    // clips their content bound what of the text can paint at all.
    let clipBox=null, clipUnknown=false;
    for (let a=el; a && a.nodeType===1; a=a.parentElement) {
      const as=getComputedStyle(a);
      if (as.filter!=="none") effects.push("filter");
      if (as.mixBlendMode!=="normal") effects.push("mix-blend-mode");
      if (Number(as.opacity)!==1) { if (paintsUnder(a)) effects.push("opacity"); else alpha*=Number(as.opacity); }
      if ((as.clip && as.clip!=="auto") || (as.clipPath && as.clipPath!=="none")) clipUnknown=true;
      if (a!==root && a!==document.body && (as.overflowX!=="visible" || as.overflowY!=="visible")) {
        const q=a.getBoundingClientRect();
        clipBox=clipBox ? {left:Math.max(clipBox.left,q.left),top:Math.max(clipBox.top,q.top),
          right:Math.min(clipBox.right,q.right),bottom:Math.min(clipBox.bottom,q.bottom)}
          : {left:q.left,top:q.top,right:q.right,bottom:q.bottom};
      }
    }
    texts[parent].push({parent_selector:parent,child_index:index,content:node.textContent,
      computed_size_px:round(size),box:box(r),lines:allLines.slice(0,32).map(box),line_count:allLines.length,
      clip_box:clipBox ? box({x:clipBox.left,y:clipBox.top,width:Math.max(0,clipBox.right-clipBox.left),
        height:Math.max(0,clipBox.bottom-clipBox.top)}) : null,clip_unknown:clipUnknown,
      requested_font_family:s.fontFamily,
      resolved_fonts:[],background:bg,foreground:fgValue,foreground_effects:[...new Set(effects)],foreground_opacity:round(alpha),
      contrast_ratio:actualFg && bg ? contrast(actualFg,bg.rgba) : null});
  }
  const annotations = Array.from(document.querySelectorAll("[data-series][data-value]"));
  const annotation = annotations.length ? {present:true,marks:[],labels:[],associations:[],collisions:[]} : {present:false};
  if (annotations.length) {
    for (const el of annotations) {
      // Non-colour channels only: what would still distinguish this mark from
      // another series in greyscale. Colour itself is deliberately excluded.
      const ms=getComputedStyle(el);
      // A url(#id) reference counts only by the GEOMETRY it draws: gradients
      // are colour (null), and patterns, markers and symbols are compared by
      // their child shapes, so two that differ only in colour still match.
      const geometry=ref => {
        const m=ref && ref.match(/url\(["']?#([^"')]+)["']?\)|^#(.+)$/);
        const target=m && document.getElementById(m[1]||m[2]);
        if (!target || /gradient/i.test(target.localName)) return null;
        return target.localName+":"+Array.from(target.querySelectorAll("*")).slice(0,40).map(c =>
          c.localName+"("+["d","points","r","rx","ry","width","height","x1","y1","x2","y2"].map(k =>
          c.getAttribute(k)||"").join(",")+")").join(";");
      };
      const use=el.localName==="use" ? (el.getAttribute("href") || el.getAttribute("xlink:href")) : null;
      annotation.marks.push({selector:selector(el),series:el.dataset.series,value:el.dataset.value,
        box:box(el.getBoundingClientRect()),
        channels:{element:el.localName,dash:ms.strokeDasharray||"none",
          marker:[ms.markerStart,ms.markerMid,ms.markerEnd].filter(v => v && v!=="none").map(geometry).join(" ")||null,
          pattern:geometry(ms.fill) || geometry(ms.backgroundImage),symbol:use ? geometry(use) : null,
          shape:el.dataset.shape || null}});
    }
    const textEntries=Object.entries(texts).flatMap(([key,items]) => items.map(item => ({selector:key,...item})));
    const distance=(a,b) => {
      const ax=a.x+a.width/2, ay=a.y+a.height/2, bx=b.x+b.width/2, by=b.y+b.height/2;
      return Math.hypot(ax-bx,ay-by);
    };
    for (const mark of annotation.marks) {
      const candidates=textEntries.filter(t => t.content.trim()===mark.value &&
        t.selector!==mark.selector && !document.querySelector(mark.selector).contains(document.querySelector(t.selector)));
      candidates.sort((a,b) => distance(a.box,mark.box)-distance(b.box,mark.box));
      if (candidates.length) {
        const label=candidates[0];
        annotation.associations.push({mark:mark.selector,label:label.selector,
          method:"value-text-match-nearest",distance_px:round(distance(label.box,mark.box))});
        if (!annotation.labels.some(x => x.selector===label.selector))
          annotation.labels.push({selector:label.selector,box:label.box});
      }
    }
    for (let i=0;i<annotation.labels.length;i++) for (let j=i+1;j<annotation.labels.length;j++) {
      const a=annotation.labels[i],b=annotation.labels[j];
      const w=Math.max(0,Math.min(a.box.x+a.box.width,b.box.x+b.box.width)-Math.max(a.box.x,b.box.x));
      const h=Math.max(0,Math.min(a.box.y+a.box.height,b.box.y+b.box.height)-Math.max(a.box.y,b.box.y));
      if (w*h>0) annotation.collisions.push({a:a.selector,b:b.selector,area:round(w*h)});
    }
  }
  // Declared @font-face rules and their load status: lets a reader tell an
  // alias that loaded from one that failed, which CDP's internal family name
  // cannot. Reading FontFaceSet does not trigger loads.
  const fontFaces=[];
  for (const face of document.fonts) {
    if (fontFaces.length>=64) break;
    fontFaces.push({family:face.family.replace(/^["']|["']$/g,""),status:face.status,
      weight:face.weight,style:face.style});
  }
  return {canvas,elements,texts,annotation,font_faces:fontFaces,
    counts:{elements:Object.keys(elements).length,texts:textCount}};
})()
