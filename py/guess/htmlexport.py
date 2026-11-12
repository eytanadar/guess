"""exportHTML(): the graph as one self-contained web page (Gephi's Sigma
exporter, Loxa, OpenSeadragon and "publish to the web" plugins).

The page needs nothing else: the graph, its fields, legends and images are
inlined with a small canvas viewer (pan, zoom, search, hover tooltips, click
for a node's neighbours and fields). Open it from disk, email it or put it on
any web server.
"""
import html
import json

from .model import GuessError

# fields left out of the tooltip: they are drawn, not read
_PLUMBING = {"x", "y", "visible", "color", "strokecolor", "labelcolor", "fixed", "style", "width", "height",
             "image", "label", "labelvisible", "labelsize", "labelpos", "node1", "node2", "source",
             "destination", "directed"}


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    return str(v)


def page_data(session, visible_only=True, fields=True):
    """The viewer's data: node and edge records as the renderer gets them, plus
    each element's data fields for the tooltip, legends and images."""
    g = session.graph
    nodes, edges = [], []
    nf = [n for n in g.node_schema if n not in _PLUMBING] if fields else []
    ef = [n for n in g.edge_schema if n not in _PLUMBING] if fields else []
    keep = set()
    for n in g._nodes_list():
        r = session.node_record(n)
        if visible_only and not r["v"]:
            continue
        keep.add(n._id)
        r["f"] = {k: _jsonable(g.node_schema[k].get(n)) for k in nf}
        nodes.append(r)
    for e in g._edges_list():
        r = session.edge_record(e)
        if r["s"] not in keep or r["t"] not in keep or (visible_only and not r["v"]):
            continue
        r["n"] = repr(e)
        r["f"] = {k: _jsonable(g.edge_schema[k].get(e)) for k in ef}
        edges.append(r)
    images = {}
    if any(r.get("img") for r in nodes):
        import os
        from .visuals import _data_url
        for source, key in session._images.items():
            try:
                images[key] = _data_url(source) if os.path.exists(source) else source
            except OSError:
                images[key] = source
    legends = []
    for lg in session.view.legends.values():
        rec = lg.record()
        legends.append({"entries": [{"k": x.get("k"), "c": x.get("c"), "t": x.get("t")}
                                    for x in rec.get("entries", []) if not x.get("more")]})
    bg = session.view.background
    if bg is not None:
        from . import colors
        bg = colors.to_rgba_int(bg, (255, 255, 255, 255))[0]
    return {"nodes": nodes, "edges": edges, "images": images, "legends": legends, "background": bg,
            "curvature": session.view.curvature, "directed": session.view.directed}


def render(data, title):
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return (VIEWER.replace("__TITLE__", html.escape(title))
                  .replace("__DATA__", blob))


def install(session):
    def exportHTML(filename="graph.html", title=None, hidden=False, fields=True):
        """exportHTML("graph.html") writes the graph as one self-contained web
        page: open it in any browser, from disk or a web server, with nothing
        else to install. It shows the graph as drawn here (colours, sizes,
        shapes, labels, legends, images) and lets the reader pan and zoom,
        search by name, hover for a node's fields and click to see its
        neighbours. hidden=true includes hidden nodes and edges; fields=false
        leaves the data fields out (a smaller, more private page)."""
        g = session.graph
        if not g._nodes:
            raise GuessError("the graph is empty: nothing to export")
        name = title or getattr(g, "name", None) or "Graph"
        text = render(page_data(session, visible_only=not hidden, fields=bool(fields)), str(name))
        from .persist import _write_and_offer
        _write_and_offer(session, str(filename), text)
        n = sum(1 for _ in g._nodes_list())
        print(f"wrote {filename}: a standalone page of {n} nodes")

    session.register_command("exportHTML", exportHTML)


VIEWER = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="GUESS exportHTML">
<title>__TITLE__</title>
<style>
:root { --bg: #ffffff; --fg: #1d1d1f; --muted: #6b6b70; --panel: rgba(255,255,255,0.94); --border: #d8d8dc; --hl: #ff1f6b; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #18181b; --fg: #ececf0; --muted: #a0a0a8; --panel: rgba(32,32,36,0.94); --border: #3a3a40; }
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg); font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; overflow: hidden; }
canvas { display: block; width: 100vw; height: 100vh; touch-action: none; cursor: grab; }
canvas.dragging { cursor: grabbing; }
.bar { position: fixed; top: 12px; left: 12px; right: 12px; display: flex; gap: 8px; align-items: center; pointer-events: none; }
.bar > * { pointer-events: auto; }
h1 { font-size: 15px; margin: 0; padding: 6px 10px; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 40vw; }
input { font: inherit; color: inherit; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; width: min(260px, 50vw); }
button { font: inherit; color: inherit; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; cursor: pointer; }
#tip, #info, #legend { position: fixed; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12.5px; }
#tip { pointer-events: none; max-width: 320px; display: none; }
#info { right: 12px; top: 60px; width: min(300px, calc(100vw - 24px)); max-height: calc(100vh - 140px); overflow: auto; display: none; }
#legend { left: 12px; bottom: 12px; max-height: 40vh; overflow: auto; display: none; }
.t { font-weight: 600; margin-bottom: 4px; }
.row { display: flex; gap: 6px; } .row b { font-weight: 500; color: var(--muted); }
.sw { display: inline-block; width: 11px; height: 11px; border-radius: 50%; margin-right: 6px; vertical-align: -1px; }
#info a { color: inherit; cursor: pointer; text-decoration: underline; text-decoration-color: var(--border); }
.foot { position: fixed; right: 12px; bottom: 10px; font-size: 11px; color: var(--muted); }
</style>
</head>
<body>
<canvas id="c" aria-label="Network diagram"></canvas>
<div class="bar"><h1 id="title">__TITLE__</h1><input id="q" type="search" placeholder="Find a node…" aria-label="Find a node" list="names"><datalist id="names"></datalist><button id="fit" title="Show the whole graph">Fit</button></div>
<div id="tip" role="tooltip"></div>
<div id="info" aria-live="polite"></div>
<div id="legend"></div>
<div class="foot">Drag to pan · wheel or pinch to zoom · click a node</div>
<script id="data" type="application/json">__DATA__</script>
<script>
(() => {
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const cv = document.getElementById("c"), ctx = cv.getContext("2d");
const tip = document.getElementById("tip"), info = document.getElementById("info");
const byId = new Map(D.nodes.map(n => [n.i, n]));
const adj = new Map(D.nodes.map(n => [n.i, []]));
for (const e of D.edges) { adj.get(e.s)?.push(e); if (e.t !== e.s) adj.get(e.t)?.push(e); }
const imgs = {};
for (const [k, url] of Object.entries(D.images || {})) { const im = new Image(); im.onload = draw; im.src = url; imgs[k] = im; }
const hex = (c, a = 1) => `rgba(${(c >> 16) & 255},${(c >> 8) & 255},${c & 255},${a})`;
const dark = () => matchMedia("(prefers-color-scheme: dark)").matches;
let view = { x: 0, y: 0, k: 1 }, W = 0, H = 0, dpr = 1;
let hover = null, focus = null;

function resize() {
  dpr = window.devicePixelRatio || 1; W = innerWidth; H = innerHeight;
  cv.width = W * dpr; cv.height = H * dpr; draw();
}
function fit(list) {
  const ns = (list && list.length ? list : D.nodes);
  if (!ns.length) return;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const n of ns) { x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x + n.w); y1 = Math.max(y1, n.y + n.h); }
  const pad = 60, k = Math.min((W - 2 * pad) / Math.max(x1 - x0, 1), (H - 2 * pad) / Math.max(y1 - y0, 1), list && list.length < 3 ? 4 : 50);
  view = { k, x: W / 2 - k * (x0 + x1) / 2, y: H / 2 - k * (y0 + y1) / 2 };
  draw();
}
const sx = x => x * view.k + view.x, sy = y => y * view.k + view.y;
function poly(n) {
  const { x, y, w, h } = n, cx = x + w / 2, cy = y + h / 2, s = n.s;
  if (s >= 103 && s <= 164) { const k = s - 100, o = []; for (let i = 0; i < k; i++) { const t = -Math.PI / 2 + i * 2 * Math.PI / k; o.push(cx + w / 2 * Math.cos(t), cy + h / 2 * Math.sin(t)); } return o; }
  switch (s) {
    case 11: return [cx, y, x + w, y + h, x, y + h];
    case 12: return [cx, y, x + w, cy, cx, y + h, x, cy];
    case 13: return [x + w * .25, y, x + w * .75, y, x + w, cy, x + w * .75, y + h, x + w * .25, y + h, x, cy];
    case 14: { const kx = w * .29, ky = h * .29; return [x + kx, y, x + w - kx, y, x + w, y + ky, x + w, y + h - ky, x + w - kx, y + h, x + kx, y + h, x, y + h - ky, x, y + ky]; }
  }
  return null;
}
function shapePath(n) {
  ctx.beginPath();
  const p = poly(n);
  if (p) { ctx.moveTo(p[0], p[1]); for (let i = 2; i < p.length; i += 2) ctx.lineTo(p[i], p[i + 1]); ctx.closePath(); }
  else if (n.s === 2 || n.s === 5 || n.s === 9) ctx.ellipse(n.x + n.w / 2, n.y + n.h / 2, n.w / 2, n.h / 2, 0, 0, Math.PI * 2);
  else if ((n.s === 3 || n.s === 6 || n.s === 10) && ctx.roundRect) ctx.roundRect(n.x, n.y, n.w, n.h, Math.min(n.w, n.h) * .25);
  else ctx.rect(n.x, n.y, n.w, n.h);
}
const centre = n => [n.x + n.w / 2, n.y + n.h / 2];
function lit() {
  const t = focus ?? hover;
  if (t == null) return null;
  const s = new Set([t]), es = new Set();
  for (const e of adj.get(t) || []) { s.add(e.s); s.add(e.t); es.add(e); }
  return { nodes: s, edges: es };
}
function draw() {
  const bg = D.background != null ? hex(D.background) : getComputedStyle(document.body).backgroundColor;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
  ctx.setTransform(dpr * view.k, 0, 0, dpr * view.k, dpr * view.x, dpr * view.y);
  const L = lit(), px = 1 / view.k;
  for (const e of D.edges) {
    const a = byId.get(e.s), b = byId.get(e.t);
    if (!a || !b) continue;
    const on = !L || L.edges.has(e);
    const [ax, ay] = centre(a), [bx, by] = centre(b);
    ctx.strokeStyle = on && L ? (dark() ? "#ffd1e0" : "#c2185b") : hex(e.c, e.a * (on ? 1 : .12));
    ctx.lineWidth = Math.max(e.w, .6 * px);
    if (e.d && a !== b && D.directed !== "arrow" && !(e.b && e.b.length) && !(D.curvature > 0)) {
      // directed edges as in the app: tapered (wide at the source, a point at the target) or dark to light
      const len = Math.hypot(bx - ax, by - ay) || 1, nx = -(by - ay) / len, ny = (bx - ax) / len;
      if (D.directed === "fade") {
        const gr = ctx.createLinearGradient(ax, ay, bx, by);
        gr.addColorStop(0, ctx.strokeStyle); gr.addColorStop(1, dark() ? "rgba(255,255,255,.08)" : "rgba(255,255,255,.9)");
        ctx.strokeStyle = gr; ctx.lineWidth = Math.max(e.w, 1.5); ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
      } else {
        const h = Math.max(e.w * 2.4, 3) / 2;
        ctx.fillStyle = ctx.strokeStyle; ctx.beginPath();
        ctx.moveTo(ax + nx * h, ay + ny * h); ctx.lineTo(bx, by); ctx.lineTo(ax - nx * h, ay - ny * h); ctx.fill();
      }
      continue;
    }
    ctx.beginPath(); ctx.moveTo(ax, ay);
    if (e.b && e.b.length) for (let i = 0; i < e.b.length; i += 2) ctx.lineTo(e.b[i], e.b[i + 1]);
    if (a === b) { const r = Math.max(a.w, a.h) * .6; ctx.moveTo(ax + r, a.y - r * .6); ctx.arc(ax, a.y - r * .6, r, 0, Math.PI * 2); }
    else if (D.curvature > 0 && !(e.b && e.b.length)) {
      const mx = (ax + bx) / 2, my = (ay + by) / 2, dx = bx - ax, dy = by - ay;
      ctx.quadraticCurveTo(mx + dy * D.curvature * .5, my - dx * D.curvature * .5, bx, by);
    } else ctx.lineTo(bx, by);
    ctx.stroke();
    if (e.d && a !== b) {
      const fx = e.b && e.b.length ? e.b[e.b.length - 2] : ax, fy = e.b && e.b.length ? e.b[e.b.length - 1] : ay;
      const len = Math.hypot(bx - fx, by - fy) || 1, ux = (bx - fx) / len, uy = (by - fy) / len;
      const r = Math.min(b.w, b.h) / 2, tx = bx - ux * r, ty = by - uy * r, s = Math.max(6, e.w * 3), hw = s * .45;
      ctx.fillStyle = ctx.strokeStyle; ctx.beginPath();
      ctx.moveTo(tx, ty); ctx.lineTo(tx - ux * s - uy * hw, ty - uy * s + ux * hw); ctx.lineTo(tx - ux * s + uy * hw, ty - uy * s - ux * hw); ctx.fill();
    }
  }
  for (const n of D.nodes) {
    const on = !L || L.nodes.has(n.i);
    const alpha = n.a * (on ? 1 : .15);
    const im = n.img && n.s === 7 ? imgs[n.img] : null;
    if (im && im.complete && im.naturalWidth) { ctx.globalAlpha = on ? 1 : .15; ctx.drawImage(im, n.x, n.y, n.w, n.h); ctx.globalAlpha = 1; continue; }
    shapePath(n);
    if (n.s === 4 || n.s === 5 || n.s === 6) { ctx.strokeStyle = hex(n.c, alpha); ctx.lineWidth = 1.5 * px; ctx.stroke(); }
    else { ctx.fillStyle = hex(n.c, alpha); ctx.fill(); ctx.strokeStyle = n.sc >= 0 ? hex(n.sc, alpha) : `rgba(0,0,0,${.35 * alpha})`; ctx.lineWidth = .75 * px; ctx.stroke(); }
    if (L && n.i === (focus ?? hover)) { shapePath(n); ctx.strokeStyle = "#ff1f6b"; ctx.lineWidth = 2.5 * px; ctx.stroke(); }
  }
  // labels, at a constant screen size
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.textBaseline = "middle";
  const fg = getComputedStyle(document.body).color;
  for (const n of D.nodes) {
    const show = n.lv || (L && L.nodes.has(n.i) && (L.nodes.size <= 40 || n.i === (focus ?? hover)));
    if (!show || !n.l) continue;
    if (L && !L.nodes.has(n.i)) continue;
    const size = 12 * (n.ls || 1);
    ctx.font = `${n.i === (focus ?? hover) ? 600 : 400} ${size}px system-ui, sans-serif`;
    const x = sx(n.x + n.w) + 4, y = sy(n.y + n.h / 2);
    ctx.lineWidth = 3; ctx.strokeStyle = bg; ctx.strokeText(n.l, x, y);
    ctx.fillStyle = n.lc >= 0 ? hex(n.lc) : fg; ctx.fillText(n.l, x, y);
  }
}
function hit(mx, my) {
  const x = (mx - view.x) / view.k, y = (my - view.y) / view.k, slop = 3 / view.k;
  for (let i = D.nodes.length - 1; i >= 0; i--) {
    const n = D.nodes[i];
    if (x >= n.x - slop && x <= n.x + n.w + slop && y >= n.y - slop && y <= n.y + n.h + slop) return n;
  }
  return null;
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fieldRows(f) {
  return Object.entries(f || {}).filter(([, v]) => v !== null && v !== "").map(([k, v]) =>
    `<div class="row"><b>${esc(k)}</b><span>${esc(typeof v === "number" && !Number.isInteger(v) ? v.toPrecision(4) : v)}</span></div>`).join("");
}
function showInfo(n) {
  if (!n) { info.style.display = "none"; return; }
  const nb = [...new Set((adj.get(n.i) || []).map(e => e.s === n.i ? e.t : e.s))].map(i => byId.get(i)).filter(Boolean);
  nb.sort((a, b) => String(a.l).localeCompare(String(b.l)));
  info.innerHTML = `<div class="t"><span class="sw" style="background:${hex(n.c)}"></span>${esc(n.l || n.name)}</div>${fieldRows(n.f)}` +
    `<div class="t" style="margin-top:8px">${nb.length} neighbour${nb.length === 1 ? "" : "s"}</div>` +
    nb.slice(0, 200).map(m => `<div><a data-i="${m.i}">${esc(m.l || m.name)}</a></div>`).join("") + (nb.length > 200 ? `<div>… ${nb.length - 200} more</div>` : "");
  info.style.display = "block";
}
info.addEventListener("click", ev => { const a = ev.target.closest("a[data-i]"); if (a) select(byId.get(Number(a.dataset.i)), true); });
function select(n, zoom) {
  focus = n ? n.i : null; showInfo(n);
  if (n && zoom) { const nb = [n, ...(adj.get(n.i) || []).map(e => byId.get(e.s === n.i ? e.t : e.s))]; fit(nb); } else draw();
}
// pan, zoom, hover, click
let drag = null, moved = false;
const pointers = new Map();
cv.addEventListener("pointerdown", ev => { cv.setPointerCapture(ev.pointerId); pointers.set(ev.pointerId, [ev.clientX, ev.clientY]); drag = { x: ev.clientX, y: ev.clientY, vx: view.x, vy: view.y }; moved = false; });
cv.addEventListener("pointermove", ev => {
  if (pointers.has(ev.pointerId)) {
    const prev = pointers.get(ev.pointerId);
    pointers.set(ev.pointerId, [ev.clientX, ev.clientY]);
    if (pointers.size === 2) {
      const [p, q] = [...pointers.values()], other = p === pointers.get(ev.pointerId) ? q : p;
      const d0 = Math.hypot(prev[0] - other[0], prev[1] - other[1]), d1 = Math.hypot(ev.clientX - other[0], ev.clientY - other[1]);
      if (d0 > 0) zoomAt((ev.clientX + other[0]) / 2, (ev.clientY + other[1]) / 2, d1 / d0);
      moved = true; return;
    }
  }
  if (drag && pointers.size === 1) {
    const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) { moved = true; cv.classList.add("dragging"); }
    if (moved) { view.x = drag.vx + dx; view.y = drag.vy + dy; draw(); }
    return;
  }
  const n = hit(ev.clientX, ev.clientY);
  if ((n ? n.i : null) !== hover) { hover = n ? n.i : null; draw(); }
  if (n) {
    tip.innerHTML = `<div class="t">${esc(n.l || n.name)}</div>${fieldRows(n.f)}`;
    tip.style.display = "block";
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(ev.clientX + 14, W - r.width - 8) + "px";
    tip.style.top = (ev.clientY + 16 + r.height > H ? ev.clientY - r.height - 10 : ev.clientY + 16) + "px";
  } else tip.style.display = "none";
});
cv.addEventListener("pointerup", ev => {
  pointers.delete(ev.pointerId); cv.classList.remove("dragging");
  if (!moved && drag) select(hit(ev.clientX, ev.clientY), false);
  drag = null;
});
cv.addEventListener("pointerleave", () => { if (hover != null) { hover = null; draw(); } tip.style.display = "none"; });
function zoomAt(mx, my, f) {
  const k = Math.max(1e-4, Math.min(1e4, view.k * f));
  view.x = mx - (mx - view.x) * k / view.k; view.y = my - (my - view.y) * k / view.k; view.k = k; draw();
}
cv.addEventListener("wheel", ev => { ev.preventDefault(); zoomAt(ev.clientX, ev.clientY, Math.exp(-ev.deltaY * (ev.ctrlKey ? .01 : .0015))); }, { passive: false });
cv.addEventListener("dblclick", () => fit());
document.getElementById("fit").onclick = () => { select(null); fit(); };
addEventListener("keydown", ev => { if (ev.key === "Escape") { select(null); } });
// search
const names = document.getElementById("names"), q = document.getElementById("q");
const labelOf = n => String(n.l || n.name);
if (D.nodes.length <= 5000) names.innerHTML = D.nodes.map(n => `<option value="${esc(labelOf(n))}">`).join("");
q.addEventListener("change", () => {
  const t = q.value.trim().toLowerCase();
  if (!t) return;
  const n = D.nodes.find(m => labelOf(m).toLowerCase() === t || String(m.name).toLowerCase() === t) || D.nodes.find(m => labelOf(m).toLowerCase().includes(t));
  if (n) select(n, true);
});
// legends
const lg = document.getElementById("legend");
const rows = (D.legends || []).flatMap(l => l.entries || []).filter(e => e.t);
if (rows.length) {
  lg.innerHTML = rows.map(e => e.k === "x" ? `<div>${esc(e.t)}</div>` : `<div><span class="sw" style="background:${hex(e.c)};${e.k === "e" ? "border-radius:2px;height:3px" : ""}"></span>${esc(e.t)}</div>`).join("");
  lg.style.display = "block";
}
matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", draw);
addEventListener("resize", resize);
resize(); fit();
})();
</script>
</body>
</html>
"""

__all__ = ["install", "page_data", "render", "VIEWER"]
