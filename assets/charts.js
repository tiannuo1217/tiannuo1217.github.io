/* Small SVG chart kit for the case-study page: heatmap, lines, grouped bars, dot + CI, single bars.
   Every chart re-renders on resize and on light/dark change, has a hover/focus tooltip, and a table view. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const charts = [];

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function label(parent, x, y, str, attrs) {
    const t = el("text", Object.assign({ x, y, fill: css("--muted"), "font-size": 12 }, attrs || {}), parent);
    t.textContent = str;
    return t;
  }
  function svgFor(container, height) {
    container.textContent = "";
    const width = Math.max(280, container.clientWidth);
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img" }, container);
    return { svg, width };
  }
  function niceMax(v) {
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }
  function ticks(min, max, n) {
    const step = niceStep((max - min) / n);
    const out = [];
    for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function niceStep(raw) {
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= raw) return m * p;
    return 10 * p;
  }
  // Rounded data-end, square at the baseline (horizontal bar growing right from x0).
  function hbarPath(x0, y, w, h, r) {
    r = Math.min(r, h / 2, Math.max(0, w));
    if (w <= 0) return "";
    return `M${x0},${y}H${x0 + w - r}Q${x0 + w},${y} ${x0 + w},${y + r}V${y + h - r}Q${x0 + w},${y + h} ${x0 + w - r},${y + h}H${x0}Z`;
  }

  /* ---------- tooltip ---------- */
  const tip = document.createElement("div");
  tip.className = "viz-tip";
  tip.setAttribute("role", "status");
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(tip));
  function showTip(evt, title, rows) {
    tip.textContent = "";
    if (title) {
      const t = document.createElement("div");
      t.className = "t-title";
      t.textContent = title;
      tip.appendChild(t);
    }
    rows.forEach((r) => {
      const row = document.createElement("div");
      row.className = "t-row";
      if (r.color) {
        const k = document.createElement("span");
        k.className = "t-key";
        k.style.background = r.color;
        row.appendChild(k);
      }
      const v = document.createElement("span");
      v.className = "t-val";
      v.textContent = r.value;
      row.appendChild(v);
      if (r.label) {
        const l = document.createElement("span");
        l.className = "t-lab";
        l.textContent = r.label;
        row.appendChild(l);
      }
      tip.appendChild(row);
    });
    let x, y;
    if (evt.clientX !== undefined && evt.type !== "focus") {
      x = evt.clientX; y = evt.clientY;
    } else {
      const b = evt.target.getBoundingClientRect();
      x = b.left + b.width / 2; y = b.top;
    }
    tip.style.opacity = 1;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = x + 14, top = y - th - 10;
    if (left + tw > window.innerWidth - 8) left = x - tw - 14;
    if (top < 8) top = y + 16;
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = top + "px";
  }
  const hideTip = () => (tip.style.opacity = 0);
  function bindHit(node, title, rows) {
    node.setAttribute("tabindex", "0");
    node.classList.add("hit");
    node.addEventListener("pointermove", (e) => showTip(e, title, rows()));
    node.addEventListener("pointerleave", hideTip);
    node.addEventListener("focus", (e) => showTip(e, title, rows()));
    node.addEventListener("blur", hideTip);
  }

  /* ---------- legend & table view ---------- */
  function legend(container, items) {
    const box = document.createElement("div");
    box.className = "legend";
    items.forEach((it) => {
      const k = document.createElement("span");
      k.className = "key";
      const s = document.createElement("span");
      s.className = it.kind === "line" ? "line" : it.kind === "ramp" ? "ramp" : "swatch";
      s.style.background = it.color.startsWith("--") ? `var(${it.color})` : it.color;
      k.appendChild(s);
      const t = document.createElement("span");
      t.textContent = it.label;
      k.appendChild(t);
      box.appendChild(k);
    });
    container.appendChild(box);
  }
  function tableView(container, headers, rows) {
    const d = document.createElement("details");
    d.className = "table-view";
    const s = document.createElement("summary");
    s.textContent = "View as table";
    d.appendChild(s);
    const wrap = document.createElement("div");
    wrap.className = "table-scroll";
    const t = document.createElement("table");
    const tr = document.createElement("tr");
    headers.forEach((h) => { const th = document.createElement("th"); th.textContent = h; tr.appendChild(th); });
    t.appendChild(tr);
    rows.forEach((r) => {
      const row = document.createElement("tr");
      r.forEach((c) => { const td = document.createElement("td"); td.textContent = c; row.appendChild(td); });
      t.appendChild(row);
    });
    wrap.appendChild(t);
    d.appendChild(wrap);
    container.appendChild(d);
  }
  function register(container, render) {
    const holder = document.createElement("div");
    container.appendChild(holder);
    const chart = { holder, render };
    charts.push(chart);
    render(holder);
    return holder;
  }

  /* ---------- sequential colour ---------- */
  function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  function mix(a, b, t) {
    const A = hexToRgb(a), B = hexToRgb(b);
    return "rgb(" + A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(",") + ")";
  }
  function seq(t) {
    t = Math.max(0, Math.min(1, t));
    return t < 0.5 ? mix(css("--seq-low"), css("--seq-mid"), t * 2) : mix(css("--seq-mid"), css("--seq-high"), (t - 0.5) * 2);
  }

  /* ---------- 1. heatmap ---------- */
  function heatmap(container, o) {
    register(container, (holder) => {
      const left = 78, top = 40, gap = 2, cellH = 24;
      const h = top + o.rows.length * (cellH + gap) + 8;
      const { svg, width } = svgFor(holder, h);
      const cellW = (width - left) / o.cols.length;
      label(svg, left + (width - left) / 2, 11, o.colTitle, { "text-anchor": "middle", fill: css("--ink-2") });
      o.cols.forEach((c, j) => label(svg, left + j * cellW + cellW / 2, top - 7, c, { "text-anchor": "middle" }));
      o.rows.forEach((r, i) => {
        const y = top + i * (cellH + gap);
        label(svg, 0, y + cellH / 2 + 4, r + (o.flagRow === i ? " *" : ""), { fill: css("--ink-2") });
        o.cols.forEach((c, j) => {
          const v = o.value(i, j);
          if (v === null || v === undefined) return;
          const t = v / o.max;
          const rect = el("rect", { x: left + j * cellW + gap / 2, y, width: Math.max(1, cellW - gap), height: cellH, rx: 3, fill: seq(t) }, svg);
          bindHit(rect, r, () => o.tooltip(i, j));
        });
      });
    });
    legend(container, [{ kind: "ramp", color: "linear-gradient(90deg, var(--seq-low), var(--seq-mid), var(--seq-high))", label: o.legendLabel }]);
  }

  /* ---------- 2. lines with crosshair ---------- */
  function lines(container, o) {
    if (o.legend !== false) legend(container, o.series.map((s) => ({ kind: "line", color: s.color, label: s.name })));
    register(container, (holder) => {
      const H = o.height || 300, m = { l: 56, r: o.right ?? 92, t: 14, b: 40 };
      const { svg, width } = svgFor(holder, H);
      const pw = width - m.l - m.r, ph = H - m.t - m.b;
      const maxV = o.yMax || niceMax(Math.max(...o.series.flatMap((s) => s.values)));
      const x = (i) => m.l + (i / (o.x.length - 1)) * pw;
      const y = (v) => m.t + ph - (v / maxV) * ph;
      ticks(0, maxV, 4).forEach((tv) => {
        el("line", { x1: m.l, x2: m.l + pw, y1: y(tv), y2: y(tv), stroke: tv === 0 ? css("--axis") : css("--grid"), "stroke-width": 1 }, svg);
        label(svg, m.l - 8, y(tv) + 4, o.yFmt(tv), { "text-anchor": "end" });
      });
      // Widen the label step on narrow screens so tick labels never collide.
      let every = o.xEvery;
      while (every < o.x.length && (every * pw) / (o.x.length - 1) < 40) every *= 2;
      o.x.forEach((xv, i) => {
        const last = i === o.x.length - 1 && i % every >= every / 2;
        if (i % every === 0 || last) label(svg, x(i), H - m.b + 18, o.xFmt ? o.xFmt(xv) : String(xv), { "text-anchor": "middle" });
      });
      label(svg, m.l + pw / 2, H - 6, o.xTitle, { "text-anchor": "middle", fill: css("--ink-2") });
      o.series.forEach((s) => {
        el("path", { d: s.values.map((v, i) => (i ? "L" : "M") + x(i) + "," + y(v)).join(""), fill: "none", stroke: css(s.color), "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round", "stroke-dasharray": s.dashed ? "4 4" : "none" }, svg);
        if (s.endLabel) {
          const last = s.values.length - 1;
          el("circle", { cx: x(last), cy: y(s.values[last]), r: 4, fill: css(s.color), stroke: css("--surface"), "stroke-width": 2 }, svg);
          label(svg, x(last) + 9, y(s.values[last]) + 4, s.endLabel, { fill: css("--ink"), "font-weight": 600 });
        }
      });
      const cross = el("line", { y1: m.t, y2: m.t + ph, stroke: css("--axis"), "stroke-width": 1, opacity: 0 }, svg);
      const dots = o.series.map((s) => el("circle", { r: 4, fill: css(s.color), stroke: css("--surface"), "stroke-width": 2, opacity: 0 }, svg));
      const hit = el("rect", { x: m.l, y: m.t, width: pw, height: ph, fill: "transparent" }, svg);
      hit.setAttribute("tabindex", "0");
      const at = (i, evt) => {
        cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("opacity", 1);
        dots.forEach((d, k) => { d.setAttribute("cx", x(i)); d.setAttribute("cy", y(o.series[k].values[i])); d.setAttribute("opacity", 1); });
        const rows = o.series.map((s) => ({ color: css(s.color), value: o.yFmt(s.values[i], true), label: s.name, v: s.values[i] })).sort((a, b) => b.v - a.v);
        showTip(evt, o.xTip(o.x[i]), rows);
      };
      let focusIdx = o.x.length - 1;
      hit.addEventListener("pointermove", (e) => {
        const r = svg.getBoundingClientRect();
        const i = Math.round(((e.clientX - r.left - m.l) / pw) * (o.x.length - 1));
        at(Math.max(0, Math.min(o.x.length - 1, i)), e);
      });
      const off = () => { hideTip(); cross.setAttribute("opacity", 0); dots.forEach((d) => d.setAttribute("opacity", 0)); };
      hit.addEventListener("pointerleave", off);
      hit.addEventListener("blur", off);
      hit.addEventListener("focus", (e) => at(focusIdx, e));
      hit.addEventListener("keydown", (e) => {
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          focusIdx = Math.max(0, Math.min(o.x.length - 1, focusIdx + (e.key === "ArrowRight" ? 1 : -1)));
          at(focusIdx, { type: "focus", target: dots[0] });
          e.preventDefault();
        }
      });
    });
  }

  /* ---------- 3. grouped horizontal bars ---------- */
  function groupedBars(container, o) {
    legend(container, o.series.map((s) => ({ kind: "swatch", color: s.color, label: s.name })));
    register(container, (holder) => {
      const barH = 11, inner = 2, groupGap = 16, left = o.labelWidth || 120, right = 52;
      const groupH = o.series.length * barH + (o.series.length - 1) * inner;
      const H = o.cats.length * (groupH + groupGap) + 4;
      const { svg, width } = svgFor(holder, H);
      const pw = width - left - right;
      const maxV = o.max || Math.max(...o.series.flatMap((s) => s.values));
      o.cats.forEach((c, i) => {
        const gy = i * (groupH + groupGap) + 2;
        label(svg, 0, gy + groupH / 2 + 4, c, { fill: css("--ink") });
        o.series.forEach((s, k) => {
          const v = s.values[i], y = gy + k * (barH + inner), w = (v / maxV) * pw;
          el("path", { d: hbarPath(left, y, w, barH, 4), fill: css(s.color) }, svg);
          label(svg, left + w + 6, y + barH - 1.5, o.fmt(v), { fill: css("--ink-2"), "font-size": 11.5 });
          const hit = el("rect", { x: left, y: y - 1, width: Math.max(w + 40, 24), height: barH + 2, fill: "transparent" }, svg);
          bindHit(hit, c, () => o.series.map((ss) => ({ color: css(ss.color), value: o.fmt(ss.values[i]), label: ss.name })));
        });
      });
      el("line", { x1: left, x2: left, y1: 0, y2: H, stroke: css("--axis"), "stroke-width": 1 }, svg);
    });
  }

  /* ---------- 4. dot + confidence interval ---------- */
  function dotCI(container, o) {
    if (o.legend !== false) legend(container, o.series.map((s) => ({ kind: "swatch", color: s.color, label: s.name })));
    register(container, (holder) => {
      const rowH = o.rowH || (o.series.length > 1 ? 40 : 34), left = o.labelWidth || 150, right = 16, top = 6, bottom = o.xTitle ? 46 : 28;
      const H = top + o.cats.length * rowH + bottom;
      const { svg, width } = svgFor(holder, H);
      const pw = width - left - right;
      const all = o.series.flatMap((s) => s.points.flatMap((p) => [p.lo, p.hi]));
      let lo = Math.min(0, ...all), hi = Math.max(0, ...all);
      const pad = (hi - lo) * 0.06; lo -= lo < 0 ? pad : 0; hi += pad;
      const tk = ticks(lo, hi, Math.max(2, Math.min(o.tickCount || 4, Math.floor(pw / 60))));
      lo = Math.min(lo, tk[0]); hi = Math.max(hi, tk[tk.length - 1]);
      const x = (v) => left + ((v - lo) / (hi - lo)) * pw;
      tk.forEach((tv) => {
        el("line", { x1: x(tv), x2: x(tv), y1: top, y2: H - bottom, stroke: tv === 0 ? css("--axis") : css("--grid"), "stroke-width": 1 }, svg);
        label(svg, x(tv), H - bottom + 16, Math.abs(tv) < 1e-12 ? "0" : o.fmt(tv, false), { "text-anchor": "middle" });
      });
      o.cats.forEach((c, i) => {
        const cy = top + i * rowH + rowH / 2;
        label(svg, 0, cy + 4, c, { fill: css("--ink") });
        o.series.forEach((s, k) => {
          const p = s.points[i];
          const off = o.series.length > 1 ? (k - (o.series.length - 1) / 2) * 11 : 0;
          const y = cy + off, col = css(p.color || s.color);
          el("line", { x1: x(p.lo), x2: x(p.hi), y1: y, y2: y, stroke: col, "stroke-width": 2, "stroke-linecap": "round" }, svg);
          el("circle", { cx: x(p.est), cy: y, r: 5, fill: col, stroke: css("--surface"), "stroke-width": 2 }, svg);
          const hit = el("rect", { x: Math.min(x(p.lo), x(p.est) - 12), y: y - 6, width: Math.max(24, x(p.hi) - x(p.lo) + 24), height: 12, fill: "transparent" }, svg);
          bindHit(hit, c, () => [{ color: col, value: o.fmt(p.est, true), label: s.name }, { value: `${o.fmt(p.lo, true)} to ${o.fmt(p.hi, true)}`, label: "95% CI" }]);
        });
      });
      if (o.xTitle) label(svg, width / 2, H - 4, o.xTitle, { "text-anchor": "middle", fill: css("--ink-2") });
    });
  }

  /* ---------- 5. single-series bars with one highlighted ---------- */
  function emphasisBars(container, o) {
    register(container, (holder) => {
      const barH = 22, gap = 14, left = o.labelWidth || 210, right = 70;
      const H = o.cats.length * (barH + gap);
      const { svg, width } = svgFor(holder, H);
      const pw = width - left - right;
      const maxV = Math.max(...o.values);
      o.cats.forEach((c, i) => {
        const y = i * (barH + gap) + 4, w = (o.values[i] / maxV) * pw, on = i === o.highlight;
        label(svg, 0, y + barH / 2 + 4, c, { fill: css(on ? "--ink" : "--ink-2"), "font-weight": on ? 600 : 400 });
        el("path", { d: hbarPath(left, y, w, barH, 4), fill: on ? css("--series-1") : css("--deemph") }, svg);
        label(svg, left + w + 8, y + barH / 2 + 4, o.fmt(o.values[i]), { fill: css("--ink"), "font-weight": on ? 650 : 500, "font-size": 13 });
        const hit = el("rect", { x: left, y, width: Math.max(w + 60, 24), height: barH, fill: "transparent" }, svg);
        bindHit(hit, c, () => [{ color: on ? css("--series-1") : css("--deemph"), value: o.fmt(o.values[i]), label: o.valueLabel }]);
      });
      el("line", { x1: left, x2: left, y1: 0, y2: H, stroke: css("--axis"), "stroke-width": 1 }, svg);
    });
  }

  let raf;
  const rerender = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => charts.forEach((c) => c.render(c.holder))); };
  window.addEventListener("resize", rerender);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rerender);
  new MutationObserver(rerender).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  window.Charts = { heatmap, lines, groupedBars, dotCI, emphasisBars, tableView, legend };
})();
