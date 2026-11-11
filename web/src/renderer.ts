// Graph renderer on PixiJS. Holds only visual state; the model lives in the worker.
import { Application, BitmapFont, BitmapText, Container, Graphics, Sprite, Texture } from "pixi.js";
import { activationScales, anneal, type Candidate, type Choice, greedyRepair, type Item, Occupancy, particles, type Rect, rectOf } from "./labelplace";
import type { EdgeRec, HullRec, Morph, NodeRec, Overlay } from "./protocol";

interface Anim {
  t0: number;
  m: Morph;
  nodes: Map<number, { from: NodeRec; to: NodeRec | null; fresh: boolean }>;
  edges: Map<number, { from: EdgeRec; to: EdgeRec | null; fresh: boolean }>;
}

export type Hit = { kind: "n" | "e"; id: number } | null;

/** A semantic drag (declarative dragging): where the dragged node goes for a
 *  pointer position, other nodes' preview positions, a target to highlight, and
 *  what to do on drop. Candidate states are computed in the page at drag start;
 *  Python is only called once, on drop. */
export interface DragFrame {
  x: number; y: number;                         // dragged node's top-left
  others?: Map<number, [number, number]>;       // preview positions of other nodes
  ring?: { x: number; y: number; r: number; color?: number };  // highlight circle (world)
  line?: [number, number, number, number];      // rubber band (world)
  hint?: string;
}
export interface DragBehaviour {
  move(wx: number, wy: number): DragFrame;
  drop(last: DragFrame): void;
}

export interface RendererEvents {
  hover(hit: Hit, clientX: number, clientY: number): void;
  context(hit: Hit, clientX: number, clientY: number): void;
  moved(id: number, x: number, y: number): void;
  click(hit: Hit, shift: boolean): void;
  /** the selection changed by a box or lasso gesture */
  selected(ids: number[]): void;
  /** double-click; return true if handled (otherwise it zooms) */
  dblclick?(hit: Hit): boolean;
  /** any click on the graph, in graph coordinates */
  clickedAt?(x: number, y: number): void;
  /** pointer down on a node: a semantic drag behaviour, or null for a plain move */
  dragBehaviour?(id: number, alt: boolean): DragBehaviour | null;
  /** hint text while dragging (null when done) */
  dragHint?(text: string | null): void;
  /** a wheel turn over the graph; return true to take it (no zoom) */
  wheel?(ev: WheelEvent): boolean;
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
/** edge labels are a little smaller than node labels */
const EDGE_LABEL = 0.85;

/** Where one label is drawn; computed once per redraw (layoutLabels) and
 *  used by the display and by SVG export alike. */
export interface LabelPlacement {
  key: string; text: string;
  x: number; y: number;        // anchor point, world coordinates
  ax: number; ay: number;      // anchor (0..1) within the text block
  scale: number;               // BitmapText scale (LABEL_SCALE x labelsize)
  color: number;
  rot: number;                 // radians (edge labels along their edge)
  pill: boolean;               // a background-coloured pill behind (edge labels)
  halo: boolean;               // may get the outline halo (not for labels inside nodes)
  priority: number;
  w: number; h: number;        // size in world units (unrotated)
  leader?: [number, number, number, number];   // a line from the node to a label placed away from it
}

/** Positions around a node for a label of w x h: the 8 classic positions and
 *  positions sliding along each side; pref 0 is the most preferred (right,
 *  then above-right, as cartographers prefer). */
function nodeCandidates(n: { x: number; y: number; w: number; h: number }, w: number, h: number): Candidate[] {
  const gap = 2, cx = n.x + n.w / 2, cy = n.y + n.h / 2;
  const R = n.x + n.w + gap, L = n.x - gap, T = n.y - gap, B = n.y + n.h + gap;
  return [
    { x: R, y: cy, ax: 0, ay: 0.5, pref: 0 },
    { x: n.x + n.w, y: n.y, ax: 0, ay: 1, pref: 0.15 },
    { x: R, y: cy - h * 0.45, ax: 0, ay: 0.5, pref: 0.2 },
    { x: R, y: cy + h * 0.45, ax: 0, ay: 0.5, pref: 0.22 },
    { x: n.x + n.w, y: n.y + n.h, ax: 0, ay: 0, pref: 0.25 },
    { x: L, y: cy, ax: 1, ay: 0.5, pref: 0.3 },
    { x: cx, y: T, ax: 0.5, ay: 1, pref: 0.35 },
    { x: cx, y: B, ax: 0.5, ay: 0, pref: 0.4 },
    { x: L, y: cy - h * 0.45, ax: 1, ay: 0.5, pref: 0.45 },
    { x: L, y: cy + h * 0.45, ax: 1, ay: 0.5, pref: 0.47 },
    { x: cx + w * 0.3, y: T, ax: 0.5, ay: 1, pref: 0.48 },
    { x: cx - w * 0.3, y: T, ax: 0.5, ay: 1, pref: 0.5 },
    { x: cx + w * 0.3, y: B, ax: 0.5, ay: 0, pref: 0.52 },
    { x: cx - w * 0.3, y: B, ax: 0.5, ay: 0, pref: 0.54 },
    { x: n.x, y: n.y, ax: 1, ay: 1, pref: 0.55 },
    { x: n.x, y: n.y + n.h, ax: 1, ay: 0, pref: 0.6 },
  ];
}

/** Positions along an edge's polyline (the middle first), turned along it when asked. */
function edgeCandidates(p: number[], along: boolean): Candidate[] {
  const seg: number[] = [0];
  for (let i = 0; i + 3 < p.length; i += 2) seg.push(seg[seg.length - 1] + Math.hypot(p[i + 2] - p[i], p[i + 3] - p[i + 1]));
  const total = seg[seg.length - 1] || 1;
  const at = (t: number) => {
    const d = t * total;
    let k = 1;
    while (k < seg.length - 1 && seg[k] < d) k++;
    const u = (d - seg[k - 1]) / ((seg[k] - seg[k - 1]) || 1);
    const i = (k - 1) * 2;
    const dx = p[i + 2] - p[i], dy = p[i + 3] - p[i + 1];
    let rot = 0;
    if (along) {
      rot = Math.atan2(dy, dx);
      if (rot > Math.PI / 2) rot -= Math.PI;        // keep the text upright
      else if (rot < -Math.PI / 2) rot += Math.PI;
    }
    return { x: p[i] + dx * u, y: p[i + 1] + dy * u, rot };
  };
  return [[0.5, 0], [0.4, 0.1], [0.6, 0.1], [0.3, 0.25], [0.7, 0.25]].map(([t, pref]) => ({ ...at(t), ax: 0.5, ay: 0.5, pref }));
}

/** Polygon outline of the shapes that have one (styles 11-14), [x0, y0, ...]. */
function polyPoints(n: { x: number; y: number; w: number; h: number; s: number }): number[] | null {
  const { x, y, w, h } = n, cx = x + w / 2, cy = y + h / 2;
  switch (n.s) {
    case 11: return [cx, y, x + w, y + h, x, y + h];                                   // triangle
    case 12: return [cx, y, x + w, cy, cx, y + h, x, cy];                               // diamond
    case 13: return [x + w * 0.25, y, x + w * 0.75, y, x + w, cy, x + w * 0.75, y + h, x + w * 0.25, y + h, x, cy];   // hexagon
    case 14: {                                                                         // octagon
      const kx = w * 0.29, ky = h * 0.29;
      return [x + kx, y, x + w - kx, y, x + w, y + ky, x + w, y + h - ky, x + w - kx, y + h, x + kx, y + h, x, y + h - ky, x, y + ky];
    }
    default: return null;
  }
}

const isRound = (s: number) => s === 2 || s === 5 || s === 9;

/** The share of a node's width and height a label inside it may use, and
 *  where the text sits vertically (0.5 = middle; a triangle's is lower). */
function insideBox(s: number): [number, number, number] {
  switch (s) {
    case 2: case 5: case 9: return [0.74, 0.72, 0.5];
    case 3: case 6: case 10: return [0.88, 0.85, 0.5];
    case 11: return [0.5, 0.5, 0.64];
    case 12: return [0.56, 0.56, 0.5];
    case 13: return [0.72, 0.86, 0.5];
    case 14: return [0.8, 0.8, 0.5];
    default: return [0.9, 0.88, 0.5];
  }
}

/** Black or white text, whichever reads better on a fill colour. */
function contrastText(fill: number) {
  const r = (fill >> 16) & 255, g = (fill >> 8) & 255, b = fill & 255;
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? 0x1a1a1a : 0xffffff;
}

export class Renderer {
  readonly app = new Application();
  private world = new Container();
  private backdrop = new Container();
  private hullG = new Graphics();
  private guideG = new Graphics();
  /** geographic outlines under the graph (geoLayout); redrawn when the map or theme changes */
  private mapG = new Graphics();
  private map: Overlay["map"] = null;
  private mapKey = "";
  private guideLabels = new Container();
  private guides: NonNullable<Overlay["guides"]> = [];
  private guidesNote = "";
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
  /** edge labels turned along their edges (edgeLabelsAlong) */
  private labelAlong = false;
  /** background pills behind edge labels, by label key */
  private pills = new Container();
  private pillPool = new Map<string, Graphics>();
  /** the current label layout (also used by SVG export) */
  private placements: LabelPlacement[] = [];
  /** text -> [width, height] at scale 1 (multi-line aware) */
  private measureCache = new Map<string, [number, number]>();
  /** "candidates" (greedy with repair) or "particles" for outside and edge labels */
  private labelMethod: "candidates" | "particles" = "candidates";
  /** candidate index per label key, from optimizeLabels() */
  private optimized = new Map<string, number>();
  private movable = new Set<string>();
  private movableItems: Item[] = [];
  private leaderG = new Graphics();
  /** labels keep their size on screen; each appears from its activation scale */
  private constantSize = false;
  private activation = new Map<string, number>();
  private sizedFor = 0;
  private probe: BitmapText | null = null;
  private cullScale = 0;
  /** selected nodes (box, lasso, shift-click, select()) */
  readonly selection = new Set<number>();
  /** box / lasso being drawn, in world coordinates */
  private marquee: { mode: "box" | "lasso"; pts: number[] } | null = null;
  /** display background set from Python (null: the theme's) */
  private userBg: number | null = null;
  private dark = false;
  private pieColors: number[] | null = null;
  private borderWidth = 0.75;
  /** default label colour: dark on light backgrounds, light on dark ones */
  private labelColor = 0x222222;
  /** a clicked node whose neighbourhood stays bright while the rest dims */
  private focus: { id: number; nodes: Set<number>; edges: Set<number> } | null = null;
  private overlay = new Graphics();

  nodes = new Map<number, NodeRec>();
  edges = new Map<number, EdgeRec>();
  private order: number[] = [];          // node draw order
  private dirty = true;
  /** render on demand: only frames where something changed are drawn */
  private needsRender = true;
  private labelsDirty = true;
  private hl = { nodes: new Set<number>(), edges: new Set<number>() };
  private tween: { from: number[]; to: number[]; t0: number; ms: number } | null = null;
  // the last center() request, so a panel or chart that opens just after it
  // (and shrinks the graph area) doesn't leave the graph cut off
  private fitted: { nodes: number[]; edges: number[]; at: number } | null = null;
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
  /** double-click on an edge zooms to it (vf.defaultEdgeZooming) */
  zoomEdgesOnDoubleClick = true;

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
    new ResizeObserver(() => {
      this.app.queueResize();
      this.needsRender = true;
      const f = this.fitted;
      if (f && performance.now() - f.at < 2000) {
        requestAnimationFrame(() => {
          if (this.fitted !== f) return;           // the user has moved the camera since
          this.app.resize();
          this.center(f.nodes, f.edges, !!this.tween);
          this.fitted = f;                          // keep the original time window
        });
      }
    }).observe(this.host);
    // draw only when something changed (idle graphs cost nothing)
    this.app.ticker.remove(this.app.render, this.app);
    this.world.addChild(this.backdrop, this.mapG, this.guideG, this.guideLabels, this.hullG, this.edgeG, this.nodeG, this.imageLayer, this.leaderG, this.pills, this.halos, this.labels, this.overlay);
    this.app.stage.addChild(this.world);
    this.app.ticker.add(() => this.frame());
    this.bindInput();
  }

  // ---- model updates ----------------------------------------------------
  setScene(nodes: NodeRec[], edges: EdgeRec[]) {
    this.optimized.clear();          // a new graph: optimizeLabels() positions no longer apply
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
    this.guides = ov.guides ?? [];
    this.guidesNote = ov.guidesNote ?? "";
    this.map = ov.map ?? null;
    this.pieColors = ov.pie ?? null;
    this.borderWidth = ov.borderWidth ?? 0.75;
    this.applyBackground();
    this.hulls = ov.hulls;
    this.arrowLen = ov.arrow.length;
    this.arrowWidth = ov.arrow.width;
    this.curvature = ov.curvature ?? 0;
    this.edgeColorMode = ov.edgeColor ?? "original";
    const outline = !!ov.labels?.outline, cull = !!ov.labels?.cull, along = !!ov.labels?.along;
    const method = ov.labels?.placement === "particles" ? "particles" : "candidates";
    const constant = !!ov.labels?.screen;
    if (method !== this.labelMethod) this.optimized.clear();      // a new method replaces optimizeLabels()
    if (outline !== this.labelOutline || cull !== this.labelCull || along !== this.labelAlong
        || method !== this.labelMethod || constant !== this.constantSize) {
      this.labelOutline = outline;
      this.labelCull = cull;
      this.labelAlong = along;
      this.labelMethod = method;
      this.constantSize = constant;
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
          this.needsRender = true;
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
    this.needsRender = true;
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

  /** Graph coordinates to canvas pixels (the inverse of toWorld). */
  toScreen(x: number, y: number) {
    return { sx: x * this.scale + this.world.x, sy: y * this.scale + this.world.y };
  }

  /** Changes whenever the camera moves (for overlays that follow it). */
  cameraKey(): string {
    return `${this.world.x.toFixed(2)},${this.world.y.toFixed(2)},${this.scale.toFixed(5)}`;
  }

  toWorld(sx: number, sy: number) {
    return { x: (sx - this.world.x) / this.scale, y: (sy - this.world.y) / this.scale };
  }

  center(nodeIds: number[] = [], edgeIds: number[] = [], animate = true) {
    this.fitted = { nodes: nodeIds, edges: edgeIds, at: performance.now() };
    // a panel may have opened in this same batch: measure the graph area now,
    // not at the next frame's queued resize
    const r = this.host.getBoundingClientRect();
    if (Math.round(r.width) !== Math.round(this.app.screen.width) || Math.round(r.height) !== Math.round(this.app.screen.height)) this.app.resize();
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
    if (!ids.size) {
      // fitting everything: include hive plot axes and their labels
      for (const gd of this.guides) {
        x0 = Math.min(x0, gd.x2 - 70); x1 = Math.max(x1, gd.x2 + 70);
        y0 = Math.min(y0, gd.y2 - 20); y1 = Math.max(y1, gd.y2 + 20);
      }
      if (this.guidesNote && this.guides.length) y1 += 50;
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

  /** The camera as [centre x, centre y, zoom] in graph coordinates. */
  getView(): number[] {
    const W = this.app.screen.width / 2, H = this.app.screen.height / 2;
    return [(W - this.world.x) / this.scale, (H - this.world.y) / this.scale, this.scale];
  }

  setView([cx, cy, s]: number[], ms = 600) {
    this.fitted = null;
    const W = this.app.screen.width / 2, H = this.app.screen.height / 2;
    const to = [W - cx * s, H - cy * s, s];
    if (ms <= 0) this.setCamera(to);
    else this.tween = { from: [this.world.x, this.world.y, this.scale], to, t0: performance.now(), ms };
  }

  private setCamera([x, y, s]: number[]) {
    this.needsRender = true;
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
      this.drawMap();
      this.drawGuides();
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
    if (this.constantSize && Math.abs(this.scale / (this.sizedFor || 1) - 1) > 0.01) {
      this.sizeForZoom();
      this.cullLabels();
      this.needsRender = true;
    } else if (this.labelCull && Math.abs(this.scale / (this.cullScale || 1) - 1) > 0.03) this.cullLabels();
    if (this.needsRender || this.app.renderer.width !== this.lastSize[0] || this.app.renderer.height !== this.lastSize[1]) {
      this.needsRender = false;
      this.lastSize = [this.app.renderer.width, this.app.renderer.height];
      this.app.render();
    }
  }

  private lastSize = [0, 0];

  /** Land/borders fill and line colours for the map: given, or from the theme. */
  private mapColors(): [number, number] {
    const bg = this.app.renderer.background.color.toNumber();
    const lum = 0.2126 * ((bg >> 16) & 255) + 0.7152 * ((bg >> 8) & 255) + 0.0722 * (bg & 255);
    const dark = lum < 128;
    return [this.map?.fill ?? (dark ? 0x2b2f36 : 0xeef0f2), this.map?.stroke ?? (dark ? 0x535a66 : 0xb9bfc8)];
  }

  private drawMap() {
    const m = this.map;
    const [fill, stroke] = this.mapColors();
    const key = m ? `${m.rings.length}:${m.rings[0]?.slice(0, 4).join(",")}:${fill}:${stroke}` : "";
    if (key === this.mapKey) return;
    this.mapKey = key;
    const g = this.mapG;
    g.clear();
    if (!m) return;
    for (const r of m.rings) {
      if (r.length < 6) continue;
      g.poly(r, true).fill({ color: fill });
    }
    for (const r of m.rings) {
      if (r.length < 4) continue;
      g.poly(r, true).stroke({ width: 1, color: stroke, pixelLine: true });
    }
  }

  /** Hive plot axes: a line per axis with its label beyond the outer end. */
  private drawGuides() {
    const g = this.guideG;
    g.clear();
    for (const t of this.guideLabels.removeChildren()) t.destroy();
    if (!this.guides.length) return;
    const ink = this.labelColor;
    for (const gd of this.guides) {
      g.moveTo(gd.x1, gd.y1).lineTo(gd.x2, gd.y2);
      g.stroke({ width: 2.5, color: ink, alpha: 0.35, cap: "round" });
      const dx = gd.x2 - gd.x1, dy = gd.y2 - gd.y1, len = Math.hypot(dx, dy) || 1;
      const t = new BitmapText({ text: gd.label, style: LABEL_STYLE });
      t.scale.set(LABEL_SCALE * 1.6);
      t.tint = ink;
      // centred on the axis direction, just past its end
      t.anchor.set(0.5 - (0.5 * dx) / len, 0.5 - (0.5 * dy) / len);
      t.position.set(gd.x2 + (dx / len) * 8, gd.y2 + (dy / len) * 8);
      this.guideLabels.addChild(t);
    }
    if (this.guidesNote) {
      const xs = this.guides.flatMap((gd) => [gd.x1, gd.x2]), ys = this.guides.flatMap((gd) => [gd.y1, gd.y2]);
      const t = new BitmapText({ text: this.guidesNote, style: LABEL_STYLE });
      t.scale.set(LABEL_SCALE * 1.2);
      t.tint = ink;
      t.alpha = 0.7;
      t.anchor.set(0.5, 0);
      t.position.set((Math.min(...xs) + Math.max(...xs)) / 2, Math.max(...ys) + 40);
      this.guideLabels.addChild(t);
    }
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
    // batch edges sharing colour, width and opacity into one stroke (one draw
    // call per style instead of per edge: big graphs draw much faster)
    const batches = new Map<string, { c: number; w: number; a: number; edges: [EdgeRec, NodeRec, NodeRec][] }>();
    for (const e of this.edges.values()) {
      const a = this.nodes.get(e.s), b = this.nodes.get(e.t);
      if (!e.v || !a || !b || !a.v || !b.v) continue;
      const c = this.edgeColor(e, a, b);
      const alpha = this.focus && !this.focus.edges.has(e.i) ? e.a * DIM_EDGE : e.a;
      const w = Math.max(e.w, 0.1);
      const key = `${c}|${w.toFixed(2)}|${alpha.toFixed(3)}`;
      let batch = batches.get(key);
      if (!batch) batches.set(key, (batch = { c, w, a: alpha, edges: [] }));
      batch.edges.push([e, a, b]);
    }
    for (const { c, w, a: alpha, edges } of batches.values()) {
      for (const [e, a, b] of edges) this.edgePath(g, e, a, b);
      g.stroke({ width: w, color: c, alpha, cap: "round", join: "round" });
      let arrows = false;
      for (const [e, a, b] of edges) {
        if (e.d && a !== b) {
          this.arrow(g, e, a, b);
          arrows = true;
        }
      }
      if (arrows) g.fill({ color: c, alpha });
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
      const border = n.m ? Math.max(2.5, this.borderWidth) : this.borderWidth;
      const pie = this.pieColors && n.p ? n.p : null;
      const total = pie ? pie.reduce((a, b) => a + b, 0) : 0;
      if (pie && total > 0) {
        // pie-chart node: slices clockwise from 12 o'clock
        const cx = n.x + n.w / 2, cy = n.y + n.h / 2, r = Math.min(n.w, n.h) / 2;
        let a0 = -Math.PI / 2;
        pie.forEach((v, k) => {
          if (v <= 0) return;
          const a1 = a0 + (v / total) * Math.PI * 2;
          g.moveTo(cx, cy).arc(cx, cy, r, a0, a1).lineTo(cx, cy);
          g.fill({ color: this.pieColors![k % this.pieColors!.length], alpha });
          a0 = a1;
        });
        g.circle(cx, cy, r);
        g.stroke({ width: border, color: n.sc >= 0 ? n.sc : darken(n.c), alpha });
        continue;
      }
      shape(g, n);
      g.fill({ color: n.c, alpha });
      g.stroke({ width: border, color: n.sc >= 0 ? n.sc : darken(n.c), alpha });
    }
  }

  /** [width, height] of a text at scale 1 (BitmapText units; multi-line aware). */
  private measure(text: string): [number, number] {
    let m = this.measureCache.get(text);
    if (m) return m;
    if (!this.probe) this.probe = new BitmapText({ text: "", style: LABEL_STYLE });
    this.probe.text = text;
    const b = this.probe.getLocalBounds();
    m = [b.width, b.height || LABEL_STYLE.fontSize * 1.15];
    if (this.measureCache.size > 20000) this.measureCache.clear();
    this.measureCache.set(text, m);
    return m;
  }

  /** Fit a label inside a node: wrap at spaces when the node is tall enough,
   *  shrink down to 45% of the size, and finally cut it short with an ellipsis.
   *  Returns null when not even one character fits. */
  private fitInside(text: string, n: NodeRec, scale: number): { text: string; scale: number } | null {
    const [kw, kh] = insideBox(n.s);
    const aw = n.w * kw, ah = n.h * kh;
    const fits = (t: string, sc: number) => {
      const [w, h] = this.measure(t);
      return w * sc <= aw && h * sc <= ah;
    };
    if (fits(text, scale)) return { text, scale };
    // candidate wrappings: 1..6 lines, balanced greedily by width
    const words = text.split(/[ \t]+/).filter(Boolean);
    const options = [text];
    const lineH = this.measure("Ag")[1];
    for (let k = 2; k <= Math.min(words.length, 6); k++) {
      if (k * lineH * scale * 0.45 > ah) break;
      const target = this.measure(text)[0] / k;
      const lines: string[] = [];
      let cur = "";
      for (const wd of words) {
        const next = cur ? `${cur} ${wd}` : wd;
        if (cur && this.measure(next)[0] > target * 1.15 && lines.length < k - 1) {
          lines.push(cur);
          cur = wd;
        } else cur = next;
      }
      lines.push(cur);
      const t = lines.join("\n");
      if (fits(t, scale)) return { text: t, scale };
      options.push(t);
    }
    // shrink: the option that needs the least shrinking, down to 45%
    let best = { text, scale: 0 };
    for (const t of options) {
      const [w, h] = this.measure(t);
      const sc = Math.min(scale, aw / (w || 1), ah / (h || 1));
      if (sc > best.scale) best = { text: t, scale: sc };
    }
    const least = scale * 0.45;
    if (best.scale >= least) return best;
    // cut short on one line at the smallest size
    if (lineH * least > ah) return null;
    let lo = 0, hi = text.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (this.measure(text.slice(0, mid).trimEnd() + "\u2026")[0] * least <= aw) lo = mid;
      else hi = mid - 1;
    }
    return lo === 0 ? null : { text: text.slice(0, lo).trimEnd() + "\u2026", scale: least };
  }

  /** Where every visible label goes. Node labels: labelpos right / left /
   *  above / below / inside (also styles 4-6) / outside (the first free side,
   *  bigger nodes first: the hook for smarter placement). Edge labels: at the
   *  middle of the edge, on a pill, optionally turned along it. */
  private layoutLabels(): LabelPlacement[] {
    const out: LabelPlacement[] = [];
    const focus = this.focus;
    const outside: { n: NodeRec; text: string; color: number; scale: number; priority: number }[] = [];
    const side = (n: NodeRec, pos: string): [number, number, number, number] => {
      const cx = n.x + n.w / 2, cy = n.y + n.h / 2, gap = 2;
      switch (pos) {
        case "left": return [n.x - gap, cy, 1, 0.5];
        case "above": return [cx, n.y - gap, 0.5, 1];
        case "below": return [cx, n.y + n.h + gap, 0.5, 0];
        case "above-right": return [n.x + n.w, n.y, 0, 1];
        case "below-right": return [n.x + n.w, n.y + n.h, 0, 0];
        case "above-left": return [n.x, n.y, 1, 1];
        case "below-left": return [n.x, n.y + n.h, 1, 0];
        default: return [n.x + n.w + gap, cy, 0, 0.5];
      }
    };
    for (const id of this.order) {
      const n = this.nodes.get(id);
      if (!n || !n.v) continue;
      const textStyle = n.s >= 4 && n.s <= 6;
      let text: string;
      let priority = n.w * n.h;
      if (focus) {
        // the focused neighbourhood is labelled (by name if it has no label); the rest is not
        if (!focus.nodes.has(id)) continue;
        text = n.l || n.name;
        if (!text) continue;
        if (id === focus.id) priority = Infinity;
      } else {
        if (!(n.lv || textStyle) || !n.l) continue;
        text = n.l;
      }
      const pos = textStyle ? "inside" : (n.lp || "right");
      const scale = LABEL_SCALE * (n.ls ?? 1);
      if (pos === "inside") {
        const fit = this.fitInside(text, n, scale);
        if (!fit) continue;
        const [, , vy] = insideBox(n.s);
        const color = n.lc >= 0 ? n.lc : n.a >= 0.5 && n.s !== 7 ? contrastText(n.c) : this.labelColor;
        const [w, h] = this.measure(fit.text);
        out.push({ key: `n${id}`, text: fit.text, x: n.x + n.w / 2, y: n.y + n.h * vy, ax: 0.5, ay: 0.5,
                   scale: fit.scale, color, rot: 0, pill: false, halo: false, priority: textStyle ? Math.max(priority, 1e9) : priority,
                   w: w * fit.scale, h: h * fit.scale });
        continue;
      }
      const color = n.lc >= 0 ? n.lc : this.labelColor;
      if (pos === "outside") {
        outside.push({ n, text, color, scale, priority });
        continue;
      }
      const [w, h] = this.measure(text);
      const [x, y, ax, ay] = side(n, pos);
      out.push({ key: `n${id}`, text, x, y, ax, ay, scale, color, rot: 0, pill: false, halo: true, priority, w: w * scale, h: h * scale });
    }
    // movable labels: outside node labels (candidates around the node) and
    // edge labels (sliding along the edge), placed by the chosen method
    const items: Item[] = [];
    const meta = new Map<string, { text: string; color: number; scale: number; pill: boolean; halo: boolean }>();
    for (const o of outside) {
      const [tw, th] = this.measure(o.text);
      const w = tw * o.scale, h = th * o.scale;
      const key = `n${o.n.i}`;
      items.push({ key, owner: o.n.i, priority: o.priority, w, h, cands: nodeCandidates(o.n, w, h), node: [o.n.x, o.n.y, o.n.x + o.n.w, o.n.y + o.n.h] });
      meta.set(key, { text: o.text, color: o.color, scale: o.scale, pill: false, halo: true });
    }
    for (const e of this.edges.values()) {
      const a = this.nodes.get(e.s), b = this.nodes.get(e.t);
      if (!e.v || !e.lv || !e.l || !a || !b || !a.v || !b.v) continue;
      if (focus && !focus.edges.has(e.i)) continue;
      const p = a === b ? [a.x + a.w / 2, a.y - Math.max(a.w, a.h) * 1.3, a.x + a.w / 2 + 1, a.y - Math.max(a.w, a.h) * 1.3] : this.edgePoints(e, a, b);
      const scale = LABEL_SCALE * EDGE_LABEL * (e.ls ?? 1);
      const [tw, th] = this.measure(e.l);
      const key = `e${e.i}`;
      items.push({ key, owner: -1 - e.i, priority: -1, w: tw * scale, h: th * scale, cands: edgeCandidates(p, this.labelAlong) });
      meta.set(key, { text: e.l, color: e.lc >= 0 ? e.lc : this.labelColor, scale, pill: true, halo: false });
    }
    this.movable = new Set(items.map((it) => it.key));
    this.movableItems = items;
    if (items.length) {
      const chosen = this.placeItems(items, out);
      for (const it of items) {
        const c = chosen.get(it.key);
        if (!c) continue;
        const m = meta.get(it.key)!;
        out.push({ key: it.key, text: m.text, x: c.cand.x, y: c.cand.y, ax: c.cand.ax, ay: c.cand.ay, scale: m.scale,
                   color: m.color, rot: c.cand.rot ?? 0, pill: m.pill, halo: m.halo, priority: it.priority, w: it.w, h: it.h,
                   leader: c.leader });
      }
    }
    return out;
  }

  /** The obstacles movable labels must avoid: nodes, edges, fixed labels. */
  private obstacles(fixed: LabelPlacement[]): Occupancy {
    let hsum = 0;
    for (const p of fixed) hsum += p.h;
    const occ = new Occupancy(Math.max(16, (fixed.length ? hsum / fixed.length : 10) * 3));
    for (const id of this.order) {
      const n = this.nodes.get(id);
      if (n && n.v) occ.addRect([n.x, n.y, n.x + n.w, n.y + n.h], n.i, false);
    }
    if (this.edges.size <= 40000) {
      for (const e of this.edges.values()) {
        const a = this.nodes.get(e.s), b = this.nodes.get(e.t);
        if (!e.v || !a || !b || !a.v || !b.v || a === b) continue;
        occ.addPolyline(this.edgePoints(e, a, b), -1 - e.i, a.i, b.i);
      }
    }
    for (const p of fixed) {
      const r: Rect = [p.x - p.ax * p.w, p.y - p.ay * p.h, p.x + (1 - p.ax) * p.w, p.y + (1 - p.ay) * p.h];
      occ.addRect(r, Number(p.key.slice(1)) * (p.key[0] === "e" ? -1 : 1), true);
    }
    return occ;
  }

  /** Place movable labels: positions kept from optimizeLabels() first, the
   *  rest by the current method (greedy with repair, or particles). */
  private placeItems(items: Item[], fixed: LabelPlacement[]): Map<string, Choice> {
    const occ = this.obstacles(fixed);
    const out = new Map<string, Choice>();
    const rest: Item[] = [];
    for (const it of items) {
      const i = this.optimized.get(it.key);
      if (i !== undefined && i < it.cands.length) {
        const cand = it.cands[i];
        out.set(it.key, { cand, cost: 0 });
        occ.addRect(rectOf(cand, it.w, it.h), it.owner, true);
      } else rest.push(it);
    }
    const placed = this.labelMethod === "particles" ? particles(rest, occ) : greedyRepair(rest, occ);
    for (const [k, v] of placed) out.set(k, v);
    return out;
  }

  /** optimizeLabels(): simulated annealing over the movable labels' candidate
   *  positions for `ms` milliseconds; the result is kept (until the graph is
   *  replaced, the method changes or this is run again). Returns the total
   *  cost before and after. */
  optimizeLabels(ms: number): { before: number; after: number; labels: number } {
    this.optimized.clear();
    const saved = this.labelMethod;
    this.labelMethod = "candidates";
    const all = this.layoutLabels();
    this.labelMethod = saved;
    const fixed = all.filter((p) => !this.movable.has(p.key));
    const items = this.movableItems;
    const occ = this.obstacles(fixed);
    const total = (choice: Map<string, number>) => {
      const o = occ.clone();
      let c = 0;
      for (const it of [...items].sort((a, b) => b.priority - a.priority)) {
        const i = choice.get(it.key) ?? 0;
        const cand = it.cands[i];
        c += o.cost(rectOf(cand, it.w, it.h), it.owner, it.h);
        o.addRect(rectOf(cand, it.w, it.h), it.owner, true);
      }
      return c;
    };
    const start = new Map<string, number>();
    const byKey = new Map(items.map((it) => [it.key, it]));
    for (const p of all) {
      const it = byKey.get(p.key);
      if (it) start.set(p.key, Math.max(0, it.cands.findIndex((c) => c.x === p.x && c.y === p.y)));
    }
    const before = total(start);
    const best = anneal(items, occ, ms);
    const after = total(best);
    for (const [k, i] of (after <= before ? best : start)) this.optimized.set(k, i);
    this.labelsDirty = true;
    this.invalidate(true);
    return { before, after: Math.min(before, after), labels: items.length };
  }

  private drawLabels() {
    const used = new Set<string>();
    const bg = this.app.renderer.background.color.toNumber();
    const pool = (map: Map<string, BitmapText>, layer: Container, style: object, key: string, text: string) => {
      let t = map.get(key);
      if (!t) {
        t = new BitmapText({ text, style });
        map.set(key, t);
        layer.addChild(t);
      } else if (t.text !== text) {
        t.text = text;
      }
      return t;
    };
    this.placements = this.layoutLabels();
    for (const p of this.placements) {
      used.add(p.key);
      this.labelPriority.set(p.key, p.priority);
      const t = pool(this.labelPool, this.labels, LABEL_STYLE, p.key, p.text);
      const align = p.text.includes("\n") ? "center" : "left";
      if (t.style.align !== align) t.style.align = align;
      t.scale.set(p.scale);
      t.tint = p.color;
      t.anchor.set(p.ax, p.ay);
      t.position.set(p.x, p.y);
      t.rotation = p.rot;
      if (this.labelOutline && p.halo) {
        const h = pool(this.haloPool, this.halos, HALO_STYLE, p.key, p.text);
        if (h.style.align !== align) h.style.align = align;
        h.scale.set(p.scale);
        h.tint = bg;
        h.anchor.set(p.ax, p.ay);
        h.position.set(p.x, p.y);
        h.rotation = p.rot;
      }
      if (p.pill) {
        let g = this.pillPool.get(p.key);
        if (!g) {
          g = new Graphics();
          this.pillPool.set(p.key, g);
          this.pills.addChild(g);
        }
        const pad = 1.5 * (p.scale / LABEL_SCALE);
        g.clear();
        g.roundRect(-p.ax * p.w - pad, -p.ay * p.h - pad * 0.4, p.w + 2 * pad, p.h + pad * 0.8, (p.h + pad) / 2);
        g.fill({ color: bg, alpha: 0.85 });
        g.position.set(p.x, p.y);
        g.rotation = p.rot;
      }
    }
    const haloKeys = new Set(this.labelOutline ? this.placements.filter((p) => p.halo).map((p) => p.key) : []);
    for (const map of [this.labelPool, this.haloPool]) {
      for (const [key, t] of map) {
        if (!used.has(key) || (map === this.haloPool && !haloKeys.has(key))) {
          t.destroy();
          map.delete(key);
        }
      }
    }
    for (const [key, g] of this.pillPool) {
      if (!used.has(key)) {
        g.destroy();
        this.pillPool.delete(key);
      }
    }
    for (const key of this.labelPriority.keys()) if (!used.has(key)) this.labelPriority.delete(key);
    // leader lines for labels placed away from their node
    const lg = this.leaderG;
    lg.clear();
    let leaders = 0;
    for (const p of this.placements) {
      if (!p.leader) continue;
      lg.moveTo(p.leader[0], p.leader[1]).lineTo(p.leader[2], p.leader[3]);
      leaders++;
    }
    if (leaders) lg.stroke({ width: 0.6, color: this.labelColor, alpha: 0.55 });
    // constant screen size: each label's activation zoom (Been et al.)
    this.activation.clear();
    if (this.constantSize) {
      const list = this.placements.filter((p) => p.halo || p.pill).map((p) => ({
        key: p.key, priority: p.priority, ax: p.x, ay: p.y,
        box: [-p.ax * p.w, -p.ay * p.h, (1 - p.ax) * p.w, (1 - p.ay) * p.h] as Rect,
      }));
      this.activation = activationScales(list, Math.max(this.scale / 16, 1e-6));
    }
    this.sizeForZoom();
  }

  /** Constant-size labels: scale them against the zoom and show those whose
   *  activation zoom has been reached. Graph-sized labels: all shown. */
  private sizeForZoom() {
    this.sizedFor = this.scale;
    const z = this.scale || 1;
    for (const p of this.placements) {
      const t = this.labelPool.get(p.key);
      if (!t) continue;
      const act = this.activation.get(p.key);
      const k = this.constantSize && act !== undefined ? 1 / z : 1;
      t.scale.set(p.scale * k);
      const h = this.haloPool.get(p.key);
      if (h) h.scale.set(p.scale * k);
      const pill = this.pillPool.get(p.key);
      if (pill) pill.scale.set(k);
      (t as unknown as { zoomHidden: boolean }).zoomHidden = this.constantSize && act !== undefined && z < act;
    }
  }

  /** Hide labels that would overlap a higher-priority (bigger node's) label at this zoom. */
  private cullLabels() {
    this.cullScale = this.scale;
    const setVis = (key: string, t: BitmapText, v: boolean) => {
      t.visible = v;
      const h = this.haloPool.get(key);
      if (h) h.visible = v;
      const pill = this.pillPool.get(key);
      if (pill) pill.visible = v;
    };
    const zoomHidden = (t: BitmapText) => !!(t as unknown as { zoomHidden?: boolean }).zoomHidden;
    if (!this.labelCull) {
      for (const [key, t] of this.labelPool) if (t.visible === zoomHidden(t)) setVis(key, t, !zoomHidden(t));
      return;
    }
    const s = this.scale, CELL = 96;
    const grid = new Map<number, number[][]>();
    const keys = [...this.labelPool.keys()].sort((p, q) => (this.labelPriority.get(q) ?? 0) - (this.labelPriority.get(p) ?? 0));
    for (const key of keys) {
      const t = this.labelPool.get(key)!;
      if (zoomHidden(t)) {
        setVis(key, t, false);
        continue;
      }
      const w = t.width * s, h = t.height * s;
      const x0 = t.x * s - t.anchor.x * w, y0 = t.y * s - t.anchor.y * h, x1 = x0 + w, y1 = y0 + h;
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
    this.needsRender = true;
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
    const df = this.dragOverlay;
    if (df?.ring) {
      g.circle(df.ring.x, df.ring.y, df.ring.r);
      g.fill({ color: df.ring.color ?? SELECT, alpha: 0.07 });
      g.stroke({ width: 2 * px, color: df.ring.color ?? SELECT, alpha: 0.85 });
    }
    if (df?.line) {
      g.moveTo(df.line[0], df.line[1]).lineTo(df.line[2], df.line[3]);
      g.stroke({ width: 2 * px, color: SELECT, alpha: 0.9 });
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
    // a highlighted edge also marks its two endpoints, so it's obvious where it ends
    const ends = new Set<number>();
    for (const id of this.hl.edges) {
      const e = this.edges.get(id);
      if (e && !this.hl.nodes.has(e.s)) ends.add(e.s);
      if (e && !this.hl.nodes.has(e.t)) ends.add(e.t);
    }
    for (const id of ends) {
      const n = this.nodes.get(id);
      if (!n || !n.v) continue;
      // at least 7 screen pixels, so tiny nodes are still easy to spot when zoomed out
      const r = Math.max(Math.max(n.w, n.h) / 2 + 6 * px, 9 * px);
      g.circle(n.x + n.w / 2, n.y + n.h / 2, r);
      g.fill({ color: HIGHLIGHT, alpha: 0.22 });
      g.stroke({ width: 3 * px, color: HIGHLIGHT, alpha: 1 });
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
      if (isRound(n.s)) {
        const rx = n.w / 2 + slop, ry = n.h / 2 + slop;
        const dx = (x - n.x - n.w / 2) / rx, dy = (y - n.y - n.h / 2) / ry;
        if (dx * dx + dy * dy > 1) continue;
      } else {
        const poly = polyPoints({ x: n.x - slop, y: n.y - slop, w: n.w + 2 * slop, h: n.h + 2 * slop, s: n.s });
        if (poly && !pointInPolygon(x, y, poly)) continue;
      }
      return { kind: "n", id: n.i };
    }
    let best: Hit = null;
    let bestD = Infinity;
    const tolMin = 4 / this.scale;
    for (const e of this.edges.values()) {
      const a = this.nodes.get(e.s), b = this.nodes.get(e.t);
      if (!e.v || !a || !b || !a.v || !b.v || a === b) continue;
      if (!e.b) {
        // quick reject: a curve bows at most half its length away from the chord
        const ax = a.x + a.w / 2, ay = a.y + a.h / 2, bx = b.x + b.w / 2, by = b.y + b.h / 2;
        const reach = (this.curvature > 0 || this.curveOffset.has(e.i) ? Math.hypot(bx - ax, by - ay) * 0.55 : 0) + Math.max(e.w / 2, tolMin);
        if (x < Math.min(ax, bx) - reach || x > Math.max(ax, bx) + reach || y < Math.min(ay, by) - reach || y > Math.max(ay, by) + reach) continue;
        if (!this.curvature && !this.curveOffset.has(e.i) && segDist(x, y, ax, ay, bx, by) > reach) continue;
      }
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
    let drag: { mode: "pan" | "node" | "box" | "lasso"; id?: number; hit: Hit; lx: number; ly: number; moved: boolean; add?: boolean;
      beh?: DragBehaviour | null; frame?: DragFrame; saved?: Map<number, [number, number]>; grab?: [number, number] } | null = null;
    const local = (ev: PointerEvent | WheelEvent | MouseEvent) => {
      const r = el.getBoundingClientRect();
      return { sx: ev.clientX - r.left, sy: ev.clientY - r.top };
    };
    el.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      const { sx, sy } = local(ev);
      const hit = this.hitTest(sx, sy);
      this.tween = null;
      this.fitted = null;
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
      if (drag.mode === "node" && !(this.selection.has(hit!.id) && this.selection.size > 1)) {
        const beh = this.events.dragBehaviour?.(hit!.id, ev.altKey) ?? null;
        if (beh) {
          const n = this.nodes.get(hit!.id)!;
          const w = this.toWorld(sx, sy);
          drag.beh = beh;
          drag.grab = [w.x - n.x, w.y - n.y];   // keep the grab point under the pointer
          drag.saved = new Map([[n.i, [n.x, n.y]]]);
        }
      }
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
          this.needsRender = true;
        } else if (drag.beh) {
          if (!drag.moved) return;
          const w = this.toWorld(sx, sy);
          const f = drag.beh.move(w.x - drag.grab![0], w.y - drag.grab![1]);
          drag.frame = f;
          this.showDragFrame(drag.id!, f, drag.saved!);
          this.events.dragHint?.(f.hint ?? null);
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
      if (drag?.beh) {
        this.dragOverlay = null;
        this.events.dragHint?.(null);
        if (drag.moved && drag.frame) drag.beh.drop(drag.frame);
        else this.restoreDrag(drag.saved!);
        if (!drag.moved) this.events.click(drag.hit, ev.shiftKey);
        this.drawOverlay();
        drag = null;
        el.style.cursor = "";
        if (el.hasPointerCapture(ev.pointerId)) el.releasePointerCapture(ev.pointerId);
        return;
      }
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
      if (this.events.wheel?.(ev)) return;
      this.tween = null;
      this.fitted = null;
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
      const hit = this.hitTest(sx, sy);
      const zoom = hit?.kind === "e" ? this.zoomEdgesOnDoubleClick : this.zoomOnDoubleClick;
      if (!zoom) {
        this.events.dblclick?.(hit);
        return;
      }
      if (this.events.dblclick?.(hit)) return;
      if (hit) this.center(hit.kind === "n" ? [hit.id] : [], hit.kind === "e" ? [hit.id] : []);
      else this.center();
    });
    // remember where the user last clicked (v.getLastClickedPosition())
    el.addEventListener("click", (ev) => {
      const { sx, sy } = local(ev);
      const w = this.toWorld(sx, sy);
      this.events.clickedAt?.(w.x, w.y);
    });
    el.addEventListener("contextmenu", (ev) => {
      ev.preventDefault();
      const { sx, sy } = local(ev);
      this.events.context(this.hitTest(sx, sy), ev.clientX, ev.clientY);
    });
  }

  /** Semantic drag preview: move the node (and others), draw the hint shapes. */
  private dragOverlay: DragFrame | null = null;
  private showDragFrame(id: number, f: DragFrame, saved: Map<number, [number, number]>) {
    const move = (nid: number, x: number, y: number) => {
      const n = this.nodes.get(nid);
      if (!n) return;
      if (!saved.has(nid)) saved.set(nid, [n.x, n.y]);
      n.x = x;
      n.y = y;
    };
    // put back nodes no longer previewed elsewhere
    for (const [nid, [x, y]] of saved) {
      if (nid !== id && !f.others?.has(nid)) {
        const n = this.nodes.get(nid);
        if (n) { n.x = x; n.y = y; }
      }
    }
    move(id, f.x, f.y);
    for (const [nid, [x, y]] of f.others ?? []) move(nid, x, y);
    this.dragOverlay = f;
    this.invalidate(true);
  }

  private restoreDrag(saved: Map<number, [number, number]>) {
    for (const [nid, [x, y]] of saved) {
      const n = this.nodes.get(nid);
      if (n) { n.x = x; n.y = y; }
    }
    this.invalidate(true);
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
    if (this.map) {
      const [fill, stroke] = this.mapColors();
      for (const r of this.map.rings) {
        if (r.length < 6) continue;
        const d = "M" + Array.from({ length: r.length / 2 }, (_, k) => `${r[2 * k].toFixed(1)},${r[2 * k + 1].toFixed(1)}`).join("L") + "Z";
        out.push(`<path d="${d}" fill="${col(fill)}" stroke="${col(stroke)}" stroke-width="0.6"/>`);
      }
    }
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
      const poly = polyPoints(n);
      if (poly) out.push(`<polygon points="${poly.join(" ")}" ${fill}/>`);
      else if (isRound(n.s)) out.push(`<ellipse cx="${n.x + n.w / 2}" cy="${n.y + n.h / 2}" rx="${n.w / 2}" ry="${n.h / 2}" ${fill}/>`);
      else if (n.s === 3 || n.s === 6 || n.s === 10) out.push(`<rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="${Math.min(n.w, n.h) * 0.25}" ${fill}/>`);
      else out.push(`<rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" ${fill}/>`);
    }
    // labels: the same placements as on screen (positions, wrapping, sizes, pills, rotation)
    const bgc = col(this.app.renderer.background.color.toNumber());
    const laid = this.layoutLabels();
    for (const p of laid) {
      if (p.leader) out.push(`<line x1="${p.leader[0]}" y1="${p.leader[1]}" x2="${p.leader[2]}" y2="${p.leader[3]}" stroke="${col(this.labelColor)}" stroke-opacity="0.55" stroke-width="0.6"/>`);
    }
    for (const p of laid) {
      const size = 10 * (p.scale / LABEL_SCALE);
      const lines = p.text.split("\n");
      const lineH = p.h / lines.length;
      const rot = p.rot ? ` transform="rotate(${(p.rot * 180) / Math.PI} ${p.x} ${p.y})"` : "";
      if (p.pill) {
        const pad = 1.5 * (p.scale / LABEL_SCALE);
        out.push(`<rect x="${p.x - p.ax * p.w - pad}" y="${p.y - p.ay * p.h - pad * 0.4}" width="${p.w + 2 * pad}" height="${p.h + pad * 0.8}" rx="${(p.h + pad) / 2}" fill="${bgc}" fill-opacity="0.85"${rot}/>`);
      }
      const anchor = p.ax === 0 ? "start" : p.ax === 1 ? "end" : "middle";
      const halo = this.labelOutline && p.halo ? ` stroke="${bgc}" stroke-width="3" stroke-linejoin="round" paint-order="stroke"` : "";
      const top = p.y - p.ay * p.h;
      const tspans = lines.map((ln, i) => `<tspan x="${p.x}" y="${top + (i + 0.5) * lineH}">${esc(ln)}</tspan>`).join("");
      out.push(`<text font-size="${size}" font-family="Helvetica, Arial, sans-serif" text-anchor="${anchor}" dominant-baseline="central" fill="${col(p.color)}"${halo}${rot}>${tspans}</text>`);
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
  const poly = polyPoints(n);
  if (poly) {
    g.poly(poly);
    return;
  }
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
  if (isRound(n.s)) {
    return 1 / Math.sqrt((ux * ux) / (rx * rx || 1) + (uy * uy) / (ry * ry || 1));
  }
  const poly = polyPoints({ x: -rx, y: -ry, w: n.w, h: n.h, s: n.s });
  if (poly) {
    // the ray from the centre along (ux, uy) meets the outline: nearest crossing of any side
    let best = Infinity;
    for (let i = 0; i < poly.length; i += 2) {
      const ax = poly[i], ay = poly[i + 1], bx = poly[(i + 2) % poly.length], by = poly[(i + 3) % poly.length];
      const ex = bx - ax, ey = by - ay, den = ux * ey - uy * ex;
      if (Math.abs(den) < 1e-12) continue;
      const t = (ax * ey - ay * ex) / den, u = (ax * uy - ay * ux) / den;
      if (t > 0 && u >= -1e-9 && u <= 1 + 1e-9) best = Math.min(best, t);
    }
    if (Number.isFinite(best)) return best;
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
