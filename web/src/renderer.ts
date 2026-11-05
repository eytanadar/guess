// Graph renderer on PixiJS. Holds only visual state; the model lives in the worker.
import { Application, BitmapFont, BitmapText, Container, Graphics, Sprite, Texture } from "pixi.js";
import type { EdgeRec, HullRec, Morph, NodeRec, Overlay } from "./protocol";

interface Anim {
  t0: number;
  m: Morph;
  nodes: Map<number, { from: NodeRec; to: NodeRec | null; fresh: boolean }>;
  edges: Map<number, { from: EdgeRec; to: EdgeRec | null; fresh: boolean }>;
}

export type Hit = { kind: "n" | "e"; id: number } | null;

export interface RendererEvents {
  hover(hit: Hit, clientX: number, clientY: number): void;
  context(hit: Hit, clientX: number, clientY: number): void;
  moved(id: number, x: number, y: number): void;
  click(hit: Hit, shift: boolean): void;
  /** the selection changed by a box or lasso gesture */
  selected(ids: number[]): void;
  /** double-click; return true if handled (otherwise it zooms) */
  dblclick?(hit: Hit): boolean;
}

const HIGHLIGHT = 0xff1f6b;
const SELECT = 0x1d6fe8;
const CURVE_SPACING = 12;   // graph units between parallel edges
const CURVE_SAMPLES = 16;
// Labels are BitmapText rendered at 4x and scaled down, so they stay crisp
// when zoomed in and are cheap to create in the thousands.
const LABEL_STYLE = { fontFamily: "Helvetica, Arial, sans-serif", fontSize: 40, fill: 0xffffff };
const LABEL_SCALE = 0.25;
const THEME_BG = { light: 0xffffff, dark: 0x18181a };
// the same glyphs with a thick stroke, drawn underneath in the background colour; installed
// once by name (a stroked style passed directly would make Pixi build a font per label)
const HALO_STYLE = { fontFamily: "guess-label-halo", fontSize: 40 };
function installHaloFont() {
  BitmapFont.install({
    name: "guess-label-halo",
    style: { ...LABEL_STYLE, stroke: { color: 0xffffff, width: 12, join: "round" } },
    chars: " ",
    dynamicFill: true,
  });
}
const DIM_EDGE = 0.08, DIM_NODE = 0.15;

export class Renderer {
  readonly app = new Application();
  private world = new Container();
  private backdrop = new Container();
  private hullG = new Graphics();
  private imageLayer = new Container();
  private edgeG = new Graphics();
  private nodeG = new Graphics();
  private labels = new Container();
  private labelPool = new Map<string, BitmapText>();
  private halos = new Container();
  private haloPool = new Map<string, BitmapText>();
  private labelPriority = new Map<string, number>();
  private labelOutline = false;
  private labelCull = false;
  private cullScale = 0;
  /** selected nodes (box, lasso, shift-click, select()) */
  readonly selection = new Set<number>();
  /** box / lasso being drawn, in world coordinates */
  private marquee: { mode: "box" | "lasso"; pts: number[] } | null = null;
  /** display background set from Python (null: the theme's) */
  private userBg: number | null = null;
  private dark = false;
  /** default label colour: dark on light backgrounds, light on dark ones */
  private labelColor = 0x222222;
  /** a clicked node whose neighbourhood stays bright while the rest dims */
  private focus: { id: number; nodes: Set<number>; edges: Set<number> } | null = null;
  private overlay = new Graphics();

  nodes = new Map<number, NodeRec>();
  edges = new Map<number, EdgeRec>();
  private order: number[] = [];          // node draw order
  private dirty = true;
  private labelsDirty = true;
  private hl = { nodes: new Set<number>(), edges: new Set<number>() };
  private tween: { from: number[]; to: number[]; t0: number; ms: number } | null = null;
  private hulls: HullRec[] = [];
  private arrowLen: number | null = null;
  private arrowWidth: number | null = null;
  /** Gephi-style curvature for all edges (0 = straight) */
  curvature = 0;
  /** where edge colours come from (Gephi's preview edge colour modes) */
  private edgeColorMode: "original" | "source" | "target" | "mixed" = "original";
  private textures = new Map<string, Texture>();
  private bgKey = "";
  private anim: Anim | null = null;
  /** perpendicular offset (in multiples of CURVE_SPACING) for parallel edges */
  private curveOffset = new Map<number, number>();
  private curvesDirty = true;
  /** double-click zooms to the element under the pointer (vf.defaultNodeZooming) */
  zoomOnDoubleClick = true;

  constructor(private host: HTMLElement, private events: RendererEvents) {}

  async init() {
    await this.app.init({
      resizeTo: this.host,
      background: 0xffffff,
      antialias: true,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    });
    this.host.appendChild(this.app.canvas);
    installHaloFont();
    // the host also changes size when the console divider is dragged, not just with the window
    new ResizeObserver(() => this.app.queueResize()).observe(this.host);
    this.world.addChild(this.backdrop, this.hullG, this.edgeG, this.nodeG, this.imageLayer, this.halos, this.labels, this.overlay);
    this.app.stage.addChild(this.world);
    this.app.ticker.add(() => this.frame());
    this.bindInput();
  }

  // ---- model updates ----------------------------------------------------
  setScene(nodes: NodeRec[], edges: EdgeRec[]) {
    this.anim = null;
    this.nodes = new Map(nodes.map((n) => [n.i, n]));
    this.edges = new Map(edges.map((e) => [e.i, e]));
    this.order = nodes.map((n) => n.i);
    this.hl = { nodes: new Set(), edges: new Set() };
    this.selection.clear();
    this.curvesDirty = true;
    this.invalidate(true);
  }

  applyPatch(nodes: NodeRec[], edges: EdgeRec[], removedNodes: number[], removedEdges: number[], morph?: Morph, pos?: number[]) {
    this.finishAnim();
    if (pos?.length) {
      if (morph && morph.duration > 0) {
        // fold position-only changes into full records so they animate too
        const extra: NodeRec[] = [];
        for (let k = 0; k < pos.length; k += 3) {
          const n = this.nodes.get(pos[k]);
          if (n) extra.push({ ...n, x: pos[k + 1], y: pos[k + 2] });
        }
        nodes = nodes.concat(extra);
      } else {
        for (let k = 0; k < pos.length; k += 3) {
          const n = this.nodes.get(pos[k]);
          if (n) { n.x = pos[k + 1]; n.y = pos[k + 2]; }
        }
      }
    }
    if (morph && morph.duration > 0) {
      this.startAnim(nodes, edges, removedNodes, removedEdges, morph);
      return;
    }
    for (const id of removedEdges) this.edges.delete(id);
    if (removedEdges.length || edges.some((e) => !this.edges.has(e.i))) this.curvesDirty = true;
    if (removedNodes.length) {
      const gone = new Set(removedNodes);
      for (const id of removedNodes) this.nodes.delete(id);
      this.order = this.order.filter((id) => !gone.has(id));
    }
    for (const n of nodes) {
      if (!this.nodes.has(n.i)) this.order.push(n.i);
      this.nodes.set(n.i, n);
    }
    for (const e of edges) this.edges.set(e.i, e);
    this.invalidate(true);
  }

  // ---- morph animation (ls with tweening) ---------------------------------------
  private startAnim(nodes: NodeRec[], edges: EdgeRec[], removedNodes: number[], removedEdges: number[], m: Morph) {
    const a: Anim = { t0: performance.now(), m, nodes: new Map(), edges: new Map() };
    for (const id of removedNodes) {
      const cur = this.nodes.get(id);
      if (cur) a.nodes.set(id, { from: { ...cur }, to: null, fresh: false });
    }
    for (const id of removedEdges) {
      const cur = this.edges.get(id);
      if (cur) a.edges.set(id, { from: { ...cur }, to: null, fresh: false });
    }
    for (const n of nodes) {
      const cur = this.nodes.get(n.i);
      if (!cur) {
        this.order.push(n.i);
        this.nodes.set(n.i, { ...n, a: 0 });
      }
      a.nodes.set(n.i, { from: cur ? { ...cur } : { ...n, a: 0 }, to: n, fresh: !cur });
    }
    for (const e of edges) {
      const cur = this.edges.get(e.i);
      if (!cur) this.edges.set(e.i, { ...e, a: 0 });
      a.edges.set(e.i, { from: cur ? { ...cur } : { ...e, a: 0 }, to: e, fresh: !cur });
    }
    this.anim = a;
  }

  private stepAnim(now: number) {
    const a = this.anim!;
    const t = Math.min(1, (now - a.t0) / a.m.duration);
    const k = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    for (const [id, { from, to, fresh }] of a.nodes) {
      const n = this.nodes.get(id);
      if (!n) continue;
      if (!to) {
        n.a = from.a * fade(t, 0, a.m.nodeDisappearBy);
      } else {
        n.x = lerp(from.x, to.x, k); n.y = lerp(from.y, to.y, k);
        n.w = lerp(from.w, to.w, k); n.h = lerp(from.h, to.h, k);
        n.c = lerpColor(from.c, to.c, k);
        n.v = from.v || to.v;
        n.a = fresh ? to.a * (1 - fade(t, a.m.nodeAppearAfter, 1)) : lerp(from.v ? from.a : 0, to.v ? to.a : 0, k);
      }
    }
    for (const [id, { from, to, fresh }] of a.edges) {
      const e = this.edges.get(id);
      if (!e) continue;
      if (!to) {
        e.a = from.a * fade(t, 0, a.m.edgeDisappearBy);
      } else {
        e.w = lerp(from.w, to.w, k);
        e.c = lerpColor(from.c, to.c, k);
        e.v = from.v || to.v;
        e.a = fresh ? to.a * (1 - fade(t, a.m.edgeAppearAfter, 1)) : lerp(from.v ? from.a : 0, to.v ? to.a : 0, k);
      }
    }
    this.invalidate(true);
    if (t >= 1) this.finishAnim();
  }

  private finishAnim() {
    const a = this.anim;
    if (!a) return;
    this.anim = null;
    for (const [id, { to }] of a.nodes) {
      if (to) this.nodes.set(id, to);
      else this.nodes.delete(id);
    }
    for (const [id, { to }] of a.edges) {
      if (to) this.edges.set(id, to);
      else this.edges.delete(id);
    }
    this.order = this.order.filter((id) => this.nodes.has(id));
    this.invalidate(true);
  }

  setOverlay(ov: Overlay) {
    this.userBg = ov.background;
    this.applyBackground();
    this.hulls = ov.hulls;
    this.arrowLen = ov.arrow.length;
    this.arrowWidth = ov.arrow.width;
    this.curvature = ov.curvature ?? 0;
    this.edgeColorMode = ov.edgeColor ?? "original";
    const outline = !!ov.labels?.outline, cull = !!ov.labels?.cull;
    if (outline !== this.labelOutline || cull !== this.labelCull) {
      this.labelOutline = outline;
      this.labelCull = cull;
      this.labelsDirty = true;
    }
    const key = ov.image ? `${ov.image.url.length}:${ov.image.url.slice(-64)}:${ov.image.x}:${ov.image.y}` : "";
    if (key !== this.bgKey) {
      this.bgKey = key;
      for (const c of this.backdrop.removeChildren()) c.destroy();
      if (ov.image) {
        const { url, x, y } = ov.image;
        loadTexture(url).then((tex) => {
          if (this.bgKey !== key) return;
          const sp = new Sprite(tex);
          sp.position.set(x, y);
          this.backdrop.addChild(sp);
        }).catch((e) => console.warn("background image failed", e));
      }
    }
    this.invalidate();
  }

  /** Register an image (by key) for nodes with style 7. */
  addImage(key: string, url: string) {
    loadTexture(url).then((tex) => {
      this.textures.set(key, tex);
      this.invalidate();
    }).catch((e) => console.warn("image failed", key, e));
  }

  private invalidate(labels = false) {
    this.dirty = true;
    if (labels) this.labelsDirty = true;
  }

  setTheme(dark: boolean) {
    this.dark = dark;
    this.applyBackground();
  }

  private applyBackground() {
    const bg = this.userBg ?? (this.dark ? THEME_BG.dark : THEME_BG.light);
    this.app.renderer.background.color = bg;
    const lum = 0.2126 * ((bg >> 16) & 255) + 0.7152 * ((bg >> 8) & 255) + 0.0722 * (bg & 255);
    this.labelColor = lum < 128 ? 0xe6e5e1 : 0x222222;
    for (const h of this.haloPool.values()) h.tint = bg;
    this.invalidate(true);
  }

  /** Dim everything except a node and its neighbours (null clears). */
  setFocus(id: number | null) {
    this.focus = id === null || !this.nodes.has(id) ? null : { id, nodes: new Set(), edges: new Set() };
    this.invalidate(true);
  }

  get focused(): number | null {
    return this.focus?.id ?? null;
  }

  private updateFocus() {
    const f = this.focus;
    if (!f) return;
    if (!this.nodes.has(f.id)) {
      this.focus = null;
      return;
    }
    f.nodes = new Set([f.id]);
    f.edges = new Set();
    for (const e of this.edges.values()) {
      if (e.s !== f.id && e.t !== f.id) continue;
      f.edges.add(e.i);
      f.nodes.add(e.s).add(e.t);
    }
  }

  highlight(nodes: Iterable<number>, edges: Iterable<number>) {
    this.hl = { nodes: new Set(nodes), edges: new Set(edges) };
    this.drawOverlay();
  }

  // ---- camera ---------------------------------------------------------------
  get scale() {
    return this.world.scale.x;
  }

  toWorld(sx: number, sy: number) {
    return { x: (sx - this.world.x) / this.scale, y: (sy - this.world.y) / this.scale };
  }

  center(nodeIds: number[] = [], edgeIds: number[] = [], animate = true) {
    const ids = new Set(nodeIds);
    for (const eid of edgeIds) {
      const e = this.edges.get(eid);
      if (e) ids.add(e.s).add(e.t);
    }
    const pick = ids.size ? [...ids].map((i) => this.nodes.get(i)).filter(Boolean) as NodeRec[]
      : [...this.nodes.values()].filter((n) => n.v);
    if (!pick.length) return;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of pick) {
      x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y);
      x1 = Math.max(x1, n.x + n.w); y1 = Math.max(y1, n.y + n.h);
    }
    const W = this.app.screen.width, H = this.app.screen.height;
    const pad = 40;
    const bw = Math.max(x1 - x0, 1), bh = Math.max(y1 - y0, 1);
    let s = Math.min((W - 2 * pad) / bw, (H - 2 * pad) / bh);
    s = Math.min(Math.max(s, 0.01), ids.size ? 8 : 4);
    const tx = W / 2 - ((x0 + x1) / 2) * s;
    const ty = H / 2 - ((y0 + y1) / 2) * s;
    const to = [tx, ty, s];
    if (!animate) {
      this.setCamera(to);
      return;
    }
    this.tween = { from: [this.world.x, this.world.y, this.scale], to, t0: performance.now(), ms: 450 };
  }

  private setCamera([x, y, s]: number[]) {
    this.world.position.set(x, y);
    this.world.scale.set(s);
    this.drawOverlay();
  }

  // ---- drawing ----------------------------------------------------------------
  private frame() {
    if (this.tween) {
      const { from, to, t0, ms } = this.tween;
      const t = Math.min(1, (performance.now() - t0) / ms);
      const k = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      // interpolate scale geometrically so zooming feels even
      const s = from[2] * Math.pow(to[2] / from[2], k);
      const W = this.app.screen.width / 2, H = this.app.screen.height / 2;
      const cxFrom = (W - from[0]) / from[2], cyFrom = (H - from[1]) / from[2];
      const cxTo = (W - to[0]) / to[2], cyTo = (H - to[1]) / to[2];
      const cx = cxFrom + (cxTo - cxFrom) * k, cy = cyFrom + (cyTo - cyFrom) * k;
      this.setCamera([W - cx * s, H - cy * s, s]);
      if (t >= 1) this.tween = null;
    }
    if (this.anim) this.stepAnim(performance.now());
    if (this.dirty) {
      this.dirty = false;
      this.updateFocus();
      this.drawHulls();
      this.drawEdges();
      this.drawNodes();
      if (this.labelsDirty) {
        this.labelsDirty = false;
        this.drawLabels();
        this.cullLabels();
      }
      this.drawOverlay();
    }
    if (this.labelCull && Math.abs(this.scale / (this.cullScale || 1) - 1) > 0.03) this.cullLabels();
  }

  private drawHulls() {
    const g = this.hullG;
    g.clear();
    for (const h of this.hulls) {
      const pts: [number, number][] = [];
      for (const id of h.nodes) {
        const n = this.nodes.get(id);
        if (!n || !n.v) continue;
        const pad = 6;
        pts.push([n.x - pad, n.y - pad], [n.x + n.w + pad, n.y - pad],
                 [n.x - pad, n.y + n.h + pad], [n.x + n.w + pad, n.y + n.h + pad]);
      }
      if (!pts.length) continue;
      const hull = convexHull(pts);
      g.poly(hull.flat());
      g.fill({ color: h.c, alpha: h.a });
      g.stroke({ width: 1, color: darken(h.c), alpha: Math.min(1, h.a + 0.2), join: "round" });
    }
  }

  private drawEdges() {
    const g = this.edgeG;
    g.clear();
    if (this.curvesDirty) this.computeCurves();
    for (const e of this.edges.values()) {
      const a = this.nodes.get(e.s), b = this.nodes.get(e.t);
      if (!e.v || !a || !b || !a.v || !b.v) continue;
      this.edgePath(g, e, a, b);
      const c = this.edgeColor(e, a, b);
      const alpha = this.focus && !this.focus.edges.has(e.i) ? e.a * DIM_EDGE : e.a;
      g.stroke({ width: Math.max(e.w, 0.1), color: c, alpha, cap: "round", join: "round" });
      if (e.d && a !== b) {
        this.arrow(g, e, a, b);
        g.fill({ color: c, alpha });
      }
    }
  }

  private edgeColor(e: EdgeRec, a: NodeRec, b: NodeRec): number {
    switch (this.edgeColorMode) {
      case "source": return a.c;
      case "target": return b.c;
      case "mixed": return lerpColor(a.c, b.c, 0.5);
      default: return e.c;
    }
  }

  /** Parallel edges between the same two nodes are drawn as separate curves. */
  private computeCurves() {
    this.curvesDirty = false;
    const groups = new Map<string, number[]>();
    for (const e of this.edges.values()) {
      if (e.s === e.t) continue;
      const key = e.s < e.t ? `${e.s}-${e.t}` : `${e.t}-${e.s}`;
      const list = groups.get(key);
      if (list) list.push(e.i);
      else groups.set(key, [e.i]);
    }
    this.curveOffset.clear();
    for (const ids of groups.values()) {
      if (ids.length < 2) continue;
      ids.sort((p, q) => p - q);
      ids.forEach((id, k) => this.curveOffset.set(id, k - (ids.length - 1) / 2));
    }
  }

  /** Polyline (centre coordinates) for an edge between distinct nodes. */
  edgePoints(e: EdgeRec, a: NodeRec, b: NodeRec): number[] {
    const ax = a.x + a.w / 2, ay = a.y + a.h / 2, bx = b.x + b.w / 2, by = b.y + b.h / 2;
    if (e.b && e.b.length >= 2) return [ax, ay, ...e.b, bx, by];
    const off = this.curveOffset.get(e.i);
    if (this.curvature > 0) {
      // parallel edges in the same direction get different curvatures (Gephi overlaps them)
      const k = off ? Math.min(1.98, Math.max(0.05, this.curvature * (1 + 0.45 * off * (e.s < e.t ? 1 : -1)))) : this.curvature;
      return arcPoints(ax, ay, bx, by, k);
    }
    if (!off) return [ax, ay, bx, by];
    // control point offset perpendicular to the canonical (low id -> high id) direction,
    // so a->b and b->a bend to different sides
    const [lo, hi] = e.s < e.t ? [[ax, ay], [bx, by]] : [[bx, by], [ax, ay]];
    const dx = hi[0] - lo[0], dy = hi[1] - lo[1];
    const len = Math.hypot(dx, dy) || 1;
    const bend = off * Math.max(CURVE_SPACING, len * 0.12) * 2;
    const cx = (ax + bx) / 2 - (dy / len) * bend, cy = (ay + by) / 2 + (dx / len) * bend;
    const pts: number[] = [];
    for (let k = 0; k <= CURVE_SAMPLES; k++) {
      const t = k / CURVE_SAMPLES, u = 1 - t;
      pts.push(u * u * ax + 2 * u * t * cx + t * t * bx, u * u * ay + 2 * u * t * cy + t * t * by);
    }
    return pts;
  }

  private edgePath(g: Graphics, e: EdgeRec, a: NodeRec, b: NodeRec) {
    if (a === b) {
      const r = Math.max(a.w, a.h) * 0.6;
      g.circle(a.x + a.w / 2, a.y - r * 0.6, r);
      return;
    }
    const p = this.edgePoints(e, a, b);
    g.moveTo(p[0], p[1]);
    for (let k = 2; k < p.length; k += 2) g.lineTo(p[k], p[k + 1]);
  }

  /** Arrowhead triangle [tip, left, right] at the target end of an edge. */
  arrowPoints(e: EdgeRec, a: NodeRec, b: NodeRec): number[] {
    const p = this.edgePoints(e, a, b);
    const bx = p[p.length - 2], by = p[p.length - 1];
    const fx = p[p.length - 4], fy = p[p.length - 3];
    const dx = bx - fx, dy = by - fy;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    const tip = boundaryDistance(b, ux, uy);
    const px = bx - ux * tip, py = by - uy * tip;
    const size = this.arrowLen ?? Math.max(6, e.w * 3);
    const half = this.arrowWidth != null ? this.arrowWidth / 2 : size * 0.45;
    const qx = px - ux * size, qy = py - uy * size;
    return [px, py, qx - uy * half, qy + ux * half, qx + uy * half, qy - ux * half];
  }

  private arrow(g: Graphics, e: EdgeRec, a: NodeRec, b: NodeRec) {
    g.poly(this.arrowPoints(e, a, b));
  }

  private drawNodes() {
    const g = this.nodeG;
    g.clear();
    for (const c of this.imageLayer.removeChildren()) c.destroy();
    for (const id of this.order) {
      const n = this.nodes.get(id);
      if (!n || !n.v) continue;
      const alpha = this.focus && !this.focus.nodes.has(id) ? n.a * DIM_NODE : n.a;
      const tex = n.s === 7 && n.img ? this.textures.get(n.img) : undefined;
      if (tex) {
        const sp = new Sprite(tex);
        sp.position.set(n.x, n.y);
        sp.width = n.w;
        sp.height = n.h;
        sp.alpha = alpha;
        this.imageLayer.addChild(sp);
        continue;
      }
      shape(g, n);
      g.fill({ color: n.c, alpha });
      g.stroke({ width: n.m ? 2.5 : 0.75, color: n.sc >= 0 ? n.sc : darken(n.c), alpha });
    }
  }

  private drawLabels() {
    const used = new Set<string>();
    const bg = this.app.renderer.background.color.toNumber();
    const pool = (map: Map<string, BitmapText>, layer: Container, style: object, key: string, text: string) => {
      let t = map.get(key);
      if (!t) {
        t = new BitmapText({ text, style });
        t.scale.set(LABEL_SCALE);
        map.set(key, t);
        layer.addChild(t);
      } else if (t.text !== text) {
        t.text = text;
      }
      return t;
    };
    const place = (key: string, text: string, color: number, x: number, y: number, ax: number, priority: number) => {
      used.add(key);
      this.labelPriority.set(key, priority);
      const t = pool(this.labelPool, this.labels, LABEL_STYLE, key, text);
      t.tint = color;
      t.anchor.set(ax, 0.5);
      t.position.set(x, y);
      if (this.labelOutline) {
        const h = pool(this.haloPool, this.halos, HALO_STYLE, key, text);
        h.tint = bg;
        h.anchor.set(ax, 0.5);
        h.position.set(x, y);
      }
    };
    const focus = this.focus;
    for (const id of this.order) {
      const n = this.nodes.get(id);
      const isText = n && n.s >= 4 && n.s <= 6;
      if (!n || !n.v) continue;
      if (focus) {
        // the focused neighbourhood is labelled (by name if it has no label); the rest is not
        if (!focus.nodes.has(id)) continue;
        if (!n.l && !n.name) continue;
        const color = n.lc >= 0 ? n.lc : this.labelColor;
        const text = n.l || n.name;
        if (isText) place(`n${id}`, text, color, n.x + n.w / 2, n.y + n.h / 2, 0.5, Infinity);
        else place(`n${id}`, text, color, n.x + n.w + 2, n.y + n.h / 2, 0, id === focus.id ? Infinity : n.w * n.h);
        continue;
      }
      if (!(n.lv || isText) || !n.l) continue;
      const color = n.lc >= 0 ? n.lc : this.labelColor;
      if (isText) place(`n${id}`, n.l, color, n.x + n.w / 2, n.y + n.h / 2, 0.5, n.w * n.h);
      else place(`n${id}`, n.l, color, n.x + n.w + 2, n.y + n.h / 2, 0, n.w * n.h);
    }
    for (const e of this.edges.values()) {
      const a = this.nodes.get(e.s), b = this.nodes.get(e.t);
      if (!e.v || !e.lv || !e.l || !a || !b || !a.v || !b.v) continue;
      if (focus && !focus.edges.has(e.i)) continue;
      const p = a === b ? [a.x + a.w / 2, a.y - Math.max(a.w, a.h) * 1.3] : this.edgePoints(e, a, b);
      const m = Math.floor(p.length / 4) * 2;   // middle vertex of the polyline
      const [lx, ly] = p.length === 4 ? [(p[0] + p[2]) / 2, (p[1] + p[3]) / 2] : [p[m], p[m + 1]];
      place(`e${e.i}`, e.l, e.lc >= 0 ? e.lc : this.labelColor, lx, ly, 0.5, -1);
    }
    for (const map of [this.labelPool, this.haloPool]) {
      for (const [key, t] of map) {
        if (!used.has(key) || (map === this.haloPool && !this.labelOutline)) {
          t.destroy();
          map.delete(key);
        }
      }
    }
    for (const key of this.labelPriority.keys()) if (!used.has(key)) this.labelPriority.delete(key);
  }

  /** Hide labels that would overlap a higher-priority (bigger node's) label at this zoom. */
  private cullLabels() {
    this.cullScale = this.scale;
    const setVis = (key: string, t: BitmapText, v: boolean) => {
      t.visible = v;
      const h = this.haloPool.get(key);
      if (h) h.visible = v;
    };
    if (!this.labelCull) {
      for (const [key, t] of this.labelPool) if (!t.visible) setVis(key, t, true);
      return;
    }
    const s = this.scale, CELL = 96;
    const grid = new Map<number, number[][]>();
    const keys = [...this.labelPool.keys()].sort((p, q) => (this.labelPriority.get(q) ?? 0) - (this.labelPriority.get(p) ?? 0));
    for (const key of keys) {
      const t = this.labelPool.get(key)!;
      const w = t.width * s, h = t.height * s;
      const x0 = t.x * s - t.anchor.x * w, y0 = t.y * s - h / 2, x1 = x0 + w, y1 = y0 + h;
      const cx0 = Math.floor(x0 / CELL), cx1 = Math.floor(x1 / CELL), cy0 = Math.floor(y0 / CELL), cy1 = Math.floor(y1 / CELL);
      let clash = false;
      for (let cx = cx0; cx <= cx1 && !clash; cx++) {
        for (let cy = cy0; cy <= cy1 && !clash; cy++) {
          for (const r of grid.get(cx * 1_000_003 + cy) ?? []) {
            if (x0 < r[2] && r[0] < x1 && y0 < r[3] && r[1] < y1) { clash = true; break; }
          }
        }
      }
      setVis(key, t, !clash);
      if (clash) continue;
      const rect = [x0, y0, x1, y1];
      for (let cx = cx0; cx <= cx1; cx++) {
        for (let cy = cy0; cy <= cy1; cy++) {
          const k = cx * 1_000_003 + cy;
          const list = grid.get(k);
          if (list) list.push(rect);
          else grid.set(k, [rect]);
        }
      }
    }
  }

  setSelection(ids: Iterable<number>) {
    this.selection.clear();
    for (const id of ids) if (this.nodes.has(id)) this.selection.add(id);
    this.drawOverlay();
  }

  /** Add or remove one node; returns the new selection. */
  toggleSelected(id: number): number[] {
    if (this.selection.has(id)) this.selection.delete(id);
    else this.selection.add(id);
    this.drawOverlay();
    return [...this.selection];
  }

  private drawOverlay() {
    const g = this.overlay;
    g.clear();
    const px = 1 / this.scale;
    for (const id of this.selection) {
      const n = this.nodes.get(id);
      if (!n) {
        this.selection.delete(id);
        continue;
      }
      if (!n.v) continue;
      const grow = 2.5 * px;
      shape(g, { ...n, x: n.x - grow, y: n.y - grow, w: n.w + 2 * grow, h: n.h + 2 * grow });
      g.stroke({ width: 2 * px, color: SELECT, alpha: 1 });
    }
    const m = this.marquee;
    if (m && m.pts.length >= 4) {
      if (m.mode === "box") {
        const [x0, y0, x1, y1] = [m.pts[0], m.pts[1], m.pts[m.pts.length - 2], m.pts[m.pts.length - 1]];
        g.rect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
      } else {
        g.poly(m.pts);
      }
      g.fill({ color: SELECT, alpha: 0.08 });
      g.stroke({ width: 1.25 * px, color: SELECT, alpha: 0.9 });
    }
    if (!this.hl.nodes.size && !this.hl.edges.size) return;
    for (const id of this.hl.edges) {
      const e = this.edges.get(id);
      const a = e && this.nodes.get(e.s), b = e && this.nodes.get(e.t);
      if (!e || !a || !b || !e.v || !a.v || !b.v) continue;
      this.edgePath(g, e, a, b);
      g.stroke({ width: Math.max(e.w + 2 * px, 3 * px), color: HIGHLIGHT, alpha: 0.9, cap: "round" });
    }
    for (const id of this.hl.nodes) {
      const n = this.nodes.get(id);
      if (!n || !n.v) continue;
      const grow = 3 * px;
      shape(g, { ...n, x: n.x - grow, y: n.y - grow, w: n.w + 2 * grow, h: n.h + 2 * grow });
      g.stroke({ width: 2.5 * px, color: HIGHLIGHT, alpha: 1 });
    }
  }

  // ---- hit testing & input ----------------------------------------------------
  hitTest(sx: number, sy: number): Hit {
    const { x, y } = this.toWorld(sx, sy);
    const slop = 3 / this.scale;
    for (let i = this.order.length - 1; i >= 0; i--) {
      const n = this.nodes.get(this.order[i]);
      if (!n || !n.v) continue;
      if (x < n.x - slop || x > n.x + n.w + slop || y < n.y - slop || y > n.y + n.h + slop) continue;
      if (n.s === 2 || n.s === 5 || n.s === 9) {
        const rx = n.w / 2 + slop, ry = n.h / 2 + slop;
        const dx = (x - n.x - n.w / 2) / rx, dy = (y - n.y - n.h / 2) / ry;
        if (dx * dx + dy * dy > 1) continue;
      }
      return { kind: "n", id: n.i };
    }
    let best: Hit = null;
    let bestD = Infinity;
    for (const e of this.edges.values()) {
      const a = this.nodes.get(e.s), b = this.nodes.get(e.t);
      if (!e.v || !a || !b || !a.v || !b.v || a === b) continue;
      const p = this.edgePoints(e, a, b);
      let d = Infinity;
      for (let k = 0; k + 3 < p.length; k += 2) d = Math.min(d, segDist(x, y, p[k], p[k + 1], p[k + 2], p[k + 3]));
      const tol = Math.max(e.w / 2, 4 / this.scale);
      if (d < tol && d < bestD) {
        bestD = d;
        best = { kind: "e", id: e.i };
      }
    }
    return best;
  }

  private bindInput() {
    const el = this.app.canvas;
    let drag: { mode: "pan" | "node" | "box" | "lasso"; id?: number; hit: Hit; lx: number; ly: number; moved: boolean; add?: boolean } | null = null;
    const local = (ev: PointerEvent | WheelEvent | MouseEvent) => {
      const r = el.getBoundingClientRect();
      return { sx: ev.clientX - r.left, sy: ev.clientY - r.top };
    };
    el.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      const { sx, sy } = local(ev);
      const hit = this.hitTest(sx, sy);
      this.tween = null;
      el.setPointerCapture(ev.pointerId);
      if (hit?.kind !== "n" && (ev.shiftKey || ev.altKey)) {
        // shift-drag: box, alt-drag: lasso (add Cmd/Ctrl to extend the selection)
        const w = this.toWorld(sx, sy);
        const mode = ev.altKey ? "lasso" : "box";
        drag = { mode, hit, lx: sx, ly: sy, moved: false, add: ev.metaKey || ev.ctrlKey };
        this.marquee = { mode, pts: [w.x, w.y] };
        el.style.cursor = "crosshair";
        return;
      }
      drag = hit?.kind === "n"
        ? { mode: "node", id: hit.id, hit, lx: sx, ly: sy, moved: false }
        : { mode: "pan", hit, lx: sx, ly: sy, moved: false };
      el.style.cursor = drag.mode === "pan" ? "grabbing" : "move";
    });
    el.addEventListener("pointermove", (ev) => {
      const { sx, sy } = local(ev);
      if (drag) {
        const dx = sx - drag.lx, dy = sy - drag.ly;
        drag.lx = sx; drag.ly = sy;
        drag.moved ||= Math.abs(dx) + Math.abs(dy) > 2;
        if (drag.mode === "box" || drag.mode === "lasso") {
          const w = this.toWorld(sx, sy);
          const pts = this.marquee!.pts;
          if (drag.mode === "box") pts.splice(2, 2, w.x, w.y);
          else pts.push(w.x, w.y);
          this.drawOverlay();
        } else if (drag.mode === "pan") {
          this.world.position.set(this.world.x + dx, this.world.y + dy);
        } else {
          // dragging a selected node moves the whole selection
          const ids = this.selection.has(drag.id!) ? this.selection : [drag.id!];
          for (const id of ids) {
            const n = this.nodes.get(id);
            if (!n) continue;
            n.x += dx / this.scale;
            n.y += dy / this.scale;
          }
          this.invalidate(true);
        }
        return;
      }
      this.events.hover(this.hitTest(sx, sy), ev.clientX, ev.clientY);
    });
    const end = (ev: PointerEvent) => {
      if (drag?.mode === "node" && drag.moved) {
        const ids = this.selection.has(drag.id!) ? [...this.selection] : [drag.id!];
        for (const id of ids) {
          const n = this.nodes.get(id);
          if (n) this.events.moved(n.i, n.x, n.y);
        }
      }
      if (drag && (drag.mode === "box" || drag.mode === "lasso")) {
        const m = this.marquee!;
        this.marquee = null;
        if (drag.moved) {
          const inside = this.nodesInside(m.mode, m.pts);
          if (!drag.add) this.selection.clear();
          for (const id of inside) this.selection.add(id);
          this.events.selected([...this.selection]);
        } else {
          this.events.click(null, ev.shiftKey);
        }
        this.drawOverlay();
      } else if (drag && !drag.moved) this.events.click(drag.hit, ev.shiftKey);
      drag = null;
      el.style.cursor = "";
      if (el.hasPointerCapture(ev.pointerId)) el.releasePointerCapture(ev.pointerId);
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
    el.addEventListener("pointerleave", () => {
      if (!drag) this.events.hover(null, 0, 0);
    });
    el.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      this.tween = null;
      const { sx, sy } = local(ev);
      const before = this.toWorld(sx, sy);
      const factor = Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015));
      const s = Math.min(Math.max(this.scale * factor, 0.005), 200);
      this.world.scale.set(s);
      this.world.position.set(sx - before.x * s, sy - before.y * s);
      this.drawOverlay();
    }, { passive: false });
    el.addEventListener("dblclick", (ev) => {
      const { sx, sy } = local(ev);
      if (!this.zoomOnDoubleClick) {
        this.events.dblclick?.(this.hitTest(sx, sy));
        return;
      }
      const hit = this.hitTest(sx, sy);
      if (this.events.dblclick?.(hit)) return;
      if (hit) this.center(hit.kind === "n" ? [hit.id] : [], hit.kind === "e" ? [hit.id] : []);
      else this.center();
    });
    el.addEventListener("contextmenu", (ev) => {
      ev.preventDefault();
      const { sx, sy } = local(ev);
      this.events.context(this.hitTest(sx, sy), ev.clientX, ev.clientY);
    });
  }

  /** Visible nodes whose centre lies in the box (corner points) or lasso polygon. */
  private nodesInside(mode: "box" | "lasso", pts: number[]): number[] {
    const out: number[] = [];
    if (pts.length < 4) return out;
    const x0 = Math.min(pts[0], pts[pts.length - 2]), x1 = Math.max(pts[0], pts[pts.length - 2]);
    const y0 = Math.min(pts[1], pts[pts.length - 1]), y1 = Math.max(pts[1], pts[pts.length - 1]);
    for (const n of this.nodes.values()) {
      if (!n.v) continue;
      const cx = n.x + n.w / 2, cy = n.y + n.h / 2;
      if (mode === "box" ? cx >= x0 && cx <= x1 && cy >= y0 && cy <= y1 : pointInPolygon(cx, cy, pts)) out.push(n.i);
    }
    return out;
  }

  /** Raster export of the current view (with the display background). */
  async exportImage(format: "png" | "jpg"): Promise<string> {
    return this.app.renderer.extract.base64({
      target: this.app.stage,
      frame: this.app.screen,
      clearColor: this.app.renderer.background.color.toHex(),
      format: format === "jpg" ? "jpg" : "png",
    } as any);
  }

  /** Vector export of the whole graph. */
  exportSVG(): string {
    const vis = [...this.nodes.values()].filter((n) => n.v);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of vis) {
      x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y);
      x1 = Math.max(x1, n.x + n.w + (n.lv ? 8 * n.l.length : 0)); y1 = Math.max(y1, n.y + n.h);
    }
    if (!vis.length) { x0 = y0 = 0; x1 = y1 = 100; }
    const pad = 20;
    const col = (c: number) => "#" + c.toString(16).padStart(6, "0");
    const esc = (t: string) => t.replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]!);
    const out: string[] = [];
    const W = x1 - x0 + 2 * pad, H = y1 - y0 + 2 * pad;
    out.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${x0 - pad} ${y0 - pad} ${W} ${H}" width="${W}" height="${H}">`);
    out.push(`<rect x="${x0 - pad}" y="${y0 - pad}" width="${W}" height="${H}" fill="${col(this.app.renderer.background.color.toNumber())}"/>`);
    for (const h of this.hulls) {
      const pts: [number, number][] = [];
      for (const id of h.nodes) {
        const n = this.nodes.get(id);
        if (n?.v) pts.push([n.x - 6, n.y - 6], [n.x + n.w + 6, n.y - 6], [n.x - 6, n.y + n.h + 6], [n.x + n.w + 6, n.y + n.h + 6]);
      }
      if (pts.length) out.push(`<polygon points="${convexHull(pts).map((p) => p.join(",")).join(" ")}" fill="${col(h.c)}" fill-opacity="${h.a}" stroke="${col(darken(h.c))}"/>`);
    }
    for (const e of this.edges.values()) {
      const a = this.nodes.get(e.s), b = this.nodes.get(e.t);
      if (!e.v || !a || !b || !a.v || !b.v) continue;
      const ax = a.x + a.w / 2, ay = a.y + a.h / 2, bx = b.x + b.w / 2, by = b.y + b.h / 2;
      const ec = this.edgeColor(e, a, b);
      const stroke = `stroke="${col(ec)}" stroke-opacity="${e.a}" stroke-width="${e.w}" fill="none" stroke-linecap="round"`;
      if (a === b) {
        const r = Math.max(a.w, a.h) * 0.6;
        out.push(`<circle cx="${ax}" cy="${a.y - r * 0.6}" r="${r}" ${stroke}/>`);
        continue;
      }
      const p = this.edgePoints(e, a, b);
      out.push(p.length === 4
        ? `<line x1="${p[0]}" y1="${p[1]}" x2="${p[2]}" y2="${p[3]}" ${stroke}/>`
        : `<polyline points="${p.join(" ")}" stroke-linejoin="round" ${stroke}/>`);
      if (e.d) {
        const q = this.arrowPoints(e, a, b);
        out.push(`<polygon points="${q.join(" ")}" fill="${col(ec)}" fill-opacity="${e.a}"/>`);
      }
    }
    for (const id of this.order) {
      const n = this.nodes.get(id);
      if (!n || !n.v) continue;
      const fill = `fill="${col(n.c)}" fill-opacity="${n.a}" stroke="${col(n.sc >= 0 ? n.sc : darken(n.c))}" stroke-width="0.75"`;
      if (n.s === 2 || n.s === 5 || n.s === 9) out.push(`<ellipse cx="${n.x + n.w / 2}" cy="${n.y + n.h / 2}" rx="${n.w / 2}" ry="${n.h / 2}" ${fill}/>`);
      else if (n.s === 3 || n.s === 6 || n.s === 10) out.push(`<rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="${Math.min(n.w, n.h) * 0.25}" ${fill}/>`);
      else out.push(`<rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" ${fill}/>`);
      const isText = n.s >= 4 && n.s <= 6;
      if ((n.lv || isText) && n.l) {
        const lc = col(n.lc >= 0 ? n.lc : this.labelColor) + (this.labelOutline
          ? `" stroke="${col(this.app.renderer.background.color.toNumber())}" stroke-width="3" stroke-linejoin="round" paint-order="stroke` : "");
        out.push(isText
          ? `<text x="${n.x + n.w / 2}" y="${n.y + n.h / 2}" font-size="10" font-family="Helvetica, Arial, sans-serif" text-anchor="middle" dominant-baseline="central" fill="${lc}">${esc(n.l)}</text>`
          : `<text x="${n.x + n.w + 2}" y="${n.y + n.h / 2}" font-size="10" font-family="Helvetica, Arial, sans-serif" dominant-baseline="central" fill="${lc}">${esc(n.l)}</text>`);
      }
    }
    out.push("</svg>");
    return out.join("\n");
  }
}

// ---- geometry helpers -------------------------------------------------------

function lerp(a: number, b: number, k: number) {
  return a + (b - a) * k;
}

function lerpColor(a: number, b: number, k: number) {
  const ch = (c: number, s: number) => (c >> s) & 255;
  return (Math.round(lerp(ch(a, 16), ch(b, 16), k)) << 16) |
    (Math.round(lerp(ch(a, 8), ch(b, 8), k)) << 8) | Math.round(lerp(ch(a, 0), ch(b, 0), k));
}

/** 1 before `start`, 0 after `end`, linear in between (time fractions). */
function fade(t: number, start: number, end: number) {
  if (t <= start) return 1;
  if (t >= end) return 0;
  return 1 - (t - start) / Math.max(end - start, 1e-6);
}

async function loadTexture(url: string): Promise<Texture> {
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.src = url;
  await img.decode();
  return Texture.from(img);
}

/** Andrew's monotone chain. */
function convexHull(points: [number, number][]): [number, number][] {
  const p = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (p.length < 3) return p;
  const cross = (o: number[], a: number[], b: number[]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: [number, number][] = [];
  for (const q of p) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop();
    lower.push(q);
  }
  const upper: [number, number][] = [];
  for (let i = p.length - 1; i >= 0; i--) {
    const q = p[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop();
    upper.push(q);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

function shape(g: Graphics, n: { x: number; y: number; w: number; h: number; s: number }) {
  switch (n.s) {
    case 2: case 5: case 9:
      g.ellipse(n.x + n.w / 2, n.y + n.h / 2, n.w / 2, n.h / 2);
      break;
    case 3: case 6: case 10:
      g.roundRect(n.x, n.y, n.w, n.h, Math.min(n.w, n.h) * 0.25);
      break;
    default:
      g.rect(n.x, n.y, n.w, n.h);
  }
}

/**
 * Gephi's curved edge (PreviewPlugin EdgeRenderer.CurvedEdgeRenderer): a circular
 * arc of radius length / k from source to target, running clockwise on screen
 * (bowing to the left of the source->target direction), so a->b and b->a separate.
 */
export function arcPoints(ax: number, ay: number, bx: number, by: number, k: number): number[] {
  const dx = bx - ax, dy = by - ay;
  const L = Math.hypot(dx, dy);
  if (L < 1e-9) return [ax, ay, bx, by];
  const r = L / k;
  const b = Math.sqrt(Math.max(r * r - (L * L) / 4, 0));
  const cx = (ax + bx) / 2 - (b * dy) / L, cy = (ay + by) / 2 + (b * dx) / L;
  const a1 = Math.atan2(ay - cy, ax - cx);
  let sweep = Math.atan2(by - cy, bx - cx) - a1;
  while (sweep <= -Math.PI) sweep += 2 * Math.PI;
  while (sweep > Math.PI) sweep -= 2 * Math.PI;
  const pts: number[] = [ax, ay];
  for (let i = 1; i < CURVE_SAMPLES; i++) {
    const t = a1 + (sweep * i) / CURVE_SAMPLES;
    pts.push(cx + r * Math.cos(t), cy + r * Math.sin(t));
  }
  pts.push(bx, by);
  return pts;
}

/** Even-odd rule; pts is [x0, y0, x1, y1, ...] (closed implicitly). */
function pointInPolygon(x: number, y: number, pts: number[]) {
  let inside = false;
  for (let i = 0, j = pts.length - 2; i < pts.length; j = i, i += 2) {
    const xi = pts[i], yi = pts[i + 1], xj = pts[j], yj = pts[j + 1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function boundaryDistance(n: NodeRec, ux: number, uy: number) {
  const rx = n.w / 2, ry = n.h / 2;
  if (n.s === 2 || n.s === 5 || n.s === 9) {
    return 1 / Math.sqrt((ux * ux) / (rx * rx || 1) + (uy * uy) / (ry * ry || 1));
  }
  const tx = ux ? rx / Math.abs(ux) : Infinity;
  const ty = uy ? ry / Math.abs(uy) : Infinity;
  return Math.min(tx, ty);
}

function segDist(px: number, py: number, ax: number, ay: number, bx: number, by: number) {
  const dx = bx - ax, dy = by - ay;
  const l2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2));
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}

function darken(c: number) {
  const r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255;
  return ((r * 0.55) << 16) | ((g * 0.55) << 8) | (b * 0.55);
}
