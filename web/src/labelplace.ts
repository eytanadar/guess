// Label placement: where labels go so they cover as little as possible.
//
// Three methods over the same cost model (overlap with other labels and nodes,
// edges crossed, and a preference for the usual positions):
//   greedy + repair  candidate positions around each node (8 positions plus
//                    sliding along each side), placed by priority, then
//                    conflicted labels re-placed (Wagner, Wolff et al., "Three
//                    rules suffice for good label placement", 2001)
//   particles        spiral outward from the node to the first free spot,
//                    in an occupancy grid that also holds the edges, with a
//                    leader line when the label lands away from its node
//                    (Luboschik, Schumann, Cords, "Particle-based labeling", 2008)
//   annealing        simulated annealing over the candidate positions, for a
//                    time budget (Christensen, Marks, Shieber, 1995)
// and zoom activation scales for labels of constant screen size (Been,
// Daiches, Yap, "Dynamic map labeling", 2006): each label appears at one
// zoom level and stays as you zoom in.

export type Rect = [number, number, number, number];   // x0, y0, x1, y1

export interface Candidate {
  x: number; y: number;      // anchor point
  ax: number; ay: number;    // anchor within the label box
  pref: number;              // 0 = the most preferred position
  rot?: number;              // edge labels along their edge
}

export interface Item {
  key: string;
  owner: number;             // node id (node labels) or -1 - edge id (edge labels)
  priority: number;
  w: number; h: number;
  cands: Candidate[];
  /** node box, for particle search and leader lines */
  node?: Rect;
}

export interface Choice { cand: Candidate; leader?: [number, number, number, number]; cost: number }

const W_LABEL = 12, W_NODE = 8, W_EDGE = 1.5, W_PREF = 0.6;

export function rectOf(c: Candidate, w: number, h: number): Rect {
  const x0 = c.x - c.ax * w, y0 = c.y - c.ay * h;
  return [x0, y0, x0 + w, y0 + h];
}

function overlap(a: Rect, b: Rect) {
  const ix = Math.min(a[2], b[2]) - Math.max(a[0], b[0]);
  const iy = Math.min(a[3], b[3]) - Math.max(a[1], b[1]);
  return ix > 0 && iy > 0 ? ix * iy : 0;
}

/** Does segment (x0, y0)-(x1, y1) cross the rectangle? (Liang-Barsky) */
function segHitsRect(x0: number, y0: number, x1: number, y1: number, r: Rect) {
  let t0 = 0, t1 = 1;
  const dx = x1 - x0, dy = y1 - y0;
  const p = [-dx, dx, -dy, dy], q = [x0 - r[0], r[2] - x0, y0 - r[1], r[3] - y0];
  for (let i = 0; i < 4; i++) {
    if (p[i] === 0) {
      if (q[i] < 0) return false;
    } else {
      const t = q[i] / p[i];
      if (p[i] < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
    }
  }
  return true;
}

/** Uniform grid of rectangles (nodes, placed labels) and segments (edges). */
export class Occupancy {
  private cells = new Map<number, { rects: { r: Rect; owner: number; label: boolean }[]; segs: number[][] }>();
  constructor(private cell: number) {}

  /** a copy whose rectangle lists can change without touching this one */
  clone(): Occupancy {
    const o = new Occupancy(this.cell);
    for (const [k, v] of this.cells) o.cells.set(k, { rects: [...v.rects], segs: v.segs });
    return o;
  }

  private keys(r: Rect, fn: (k: number) => void) {
    const c = this.cell;
    for (let gx = Math.floor(r[0] / c); gx <= Math.floor(r[2] / c); gx++)
      for (let gy = Math.floor(r[1] / c); gy <= Math.floor(r[3] / c); gy++) fn(gx * 1_000_003 + gy);
  }

  private at(k: number) {
    let v = this.cells.get(k);
    if (!v) this.cells.set(k, (v = { rects: [], segs: [] }));
    return v;
  }

  addRect(r: Rect, owner: number, label: boolean) {
    const entry = { r, owner, label };
    this.keys(r, (k) => this.at(k).rects.push(entry));
    return entry;
  }

  removeRect(entry: { r: Rect }) {
    this.keys(entry.r, (k) => {
      const v = this.cells.get(k);
      if (v) v.rects = v.rects.filter((x) => x !== entry);
    });
  }

  /** an edge's polyline, owner = -1 - edge id; ends = the two node ids */
  addPolyline(pts: number[], owner: number, a: number, b: number) {
    for (let i = 0; i + 3 < pts.length; i += 2) {
      const s = [pts[i], pts[i + 1], pts[i + 2], pts[i + 3], owner, a, b];
      this.keys([Math.min(s[0], s[2]), Math.min(s[1], s[3]), Math.max(s[0], s[2]), Math.max(s[1], s[3])], (k) => this.at(k).segs.push(s));
    }
  }

  /** Overlap cost of a label box: other labels, nodes (not its own), edges
   *  crossed (not its own edge; a node label ignores its own edges' first
   *  stretch, which always touches it). */
  cost(r: Rect, owner: number, h: number): number {
    let c = 0;
    const seenR = new Set<unknown>(), seenS = new Set<unknown>();
    const area = h * h;
    this.keys(r, (k) => {
      const v = this.cells.get(k);
      if (!v) return;
      for (const e of v.rects) {
        if (seenR.has(e) || (!e.label && e.owner === owner)) continue;
        seenR.add(e);
        const o = overlap(r, e.r);
        if (o > 0) c += (e.label ? W_LABEL : W_NODE) * Math.min(4, o / area);
      }
      for (const s of v.segs) {
        if (seenS.has(s) || s[4] === owner || s[5] === owner || s[6] === owner) continue;
        seenS.add(s);
        if (segHitsRect(s[0], s[1], s[2], s[3], r)) c += W_EDGE;
      }
    });
    return c;
  }
}

function costOf(occ: Occupancy, it: Item, c: Candidate) {
  return occ.cost(rectOf(c, it.w, it.h), it.owner, it.h) + W_PREF * c.pref;
}

/** Greedy by priority, then up to `passes` repair passes re-placing labels
 *  that still conflict, against everything else as it now stands. */
export function greedyRepair(items: Item[], occ: Occupancy, passes = 2): Map<string, Choice> {
  const out = new Map<string, Choice>();
  const entries = new Map<string, { r: Rect }>();
  const order = [...items].sort((a, b) => b.priority - a.priority);
  const place = (it: Item) => {
    let best: Choice | null = null;
    for (const c of it.cands) {
      const cost = costOf(occ, it, c);
      if (!best || cost < best.cost) best = { cand: c, cost };
      if (cost === 0) break;
    }
    out.set(it.key, best!);
    entries.set(it.key, occ.addRect(rectOf(best!.cand, it.w, it.h), it.owner, true));
  };
  for (const it of order) if (it.cands.length) place(it);
  for (let p = 0; p < passes; p++) {
    let changed = false;
    for (const it of order) {
      const cur = out.get(it.key);
      if (!cur || cur.cost < W_PREF + 1e-9) continue;
      occ.removeRect(entries.get(it.key)!);
      const before = cur.cand;
      place(it);
      if (out.get(it.key)!.cand !== before) changed = true;
    }
    if (!changed) break;
  }
  return out;
}

/** Particle-based: rings of positions spiralling out from the node; the first
 *  with no conflict wins (else the least costly seen). A leader line joins
 *  labels placed beyond the usual ring to their node. */
export function particles(items: Item[], occ: Occupancy, maxRings = 8): Map<string, Choice> {
  const out = new Map<string, Choice>();
  const order = [...items].sort((a, b) => b.priority - a.priority);
  for (const it of order) {
    let best: Choice | null = null;
    // ring 0: the usual candidates (no leader); then rings around the node
    for (const c of it.cands) {
      const cost = costOf(occ, it, c);
      if (!best || cost < best.cost) best = { cand: c, cost };
      if (cost === 0) break;
    }
    if (best && best.cost > W_PREF && it.node) {
      const [x0, y0, x1, y1] = it.node;
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
      const step = Math.max(it.h, 4);
      for (let ring = 1; ring <= maxRings && best.cost > W_PREF; ring++) {
        const R = Math.max(x1 - x0, y1 - y0) / 2 + ring * step * 1.2;
        const n = 8 + ring * 4;
        for (let k = 0; k < n; k++) {
          const a = (2 * Math.PI * k) / n;
          const c: Candidate = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a), ax: Math.cos(a) >= 0 ? 0 : 1, ay: 0.5, pref: 1 + ring * 0.25 };
          const cost = costOf(occ, it, c);
          if (cost < best.cost) {
            const r = rectOf(c, it.w, it.h);
            const lx = Math.max(r[0], Math.min(cx, r[2])), ly = Math.max(r[1], Math.min(cy, r[3]));
            best = { cand: c, cost, leader: [cx, cy, lx, ly] };
            if (cost <= W_PREF * c.pref + 1e-9) break;
          }
        }
      }
    }
    if (!best) continue;
    out.set(it.key, best);
    occ.addRect(rectOf(best.cand, it.w, it.h), it.owner, true);
  }
  return out;
}

/** Simulated annealing over candidate indices for `ms` milliseconds,
 *  starting from greedy. Returns each item's chosen candidate index. */
export function anneal(items: Item[], obstacles: Occupancy, ms: number, seed = 1): Map<string, number> {
  let s = seed >>> 0 || 1;
  const rand = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  const occ = obstacles.clone();
  const live = items.filter((it) => it.cands.length > 1);
  const fixed = items.filter((it) => it.cands.length === 1);
  for (const it of fixed) occ.addRect(rectOf(it.cands[0], it.w, it.h), it.owner, true);
  // start from greedy
  const g = greedyRepair(live, occ.clone(), 1);
  const choice = new Map<string, number>();
  const entry = new Map<string, { r: Rect }>();
  for (const it of live) {
    const c = g.get(it.key)?.cand ?? it.cands[0];
    const i = Math.max(0, it.cands.indexOf(c));
    choice.set(it.key, i);
    entry.set(it.key, occ.addRect(rectOf(it.cands[i], it.w, it.h), it.owner, true));
  }
  if (!live.length) return choice;
  const t0 = performance.now();
  let T = 4;
  while (performance.now() - t0 < ms) {
    for (let k = 0; k < 200; k++) {
      const it = live[Math.floor(rand() * live.length)];
      const cur = choice.get(it.key)!;
      const nxt = Math.floor(rand() * it.cands.length);
      if (nxt === cur) continue;
      const e = entry.get(it.key)!;
      occ.removeRect(e);
      const before = costOf(occ, it, it.cands[cur]);
      const after = costOf(occ, it, it.cands[nxt]);
      const d = after - before;
      if (d <= 0 || rand() < Math.exp(-d / T)) {
        choice.set(it.key, nxt);
        entry.set(it.key, occ.addRect(rectOf(it.cands[nxt], it.w, it.h), it.owner, true));
      } else {
        entry.set(it.key, occ.addRect(e.r, it.owner, true));
      }
    }
    T = Math.max(0.02, 4 * (1 - (performance.now() - t0) / ms));
  }
  return choice;
}

/** Zoom activation scales for labels drawn at a constant size on screen
 *  (Been et al.): label i appears at scale s_i and stays as you zoom in.
 *  Labels are given by their anchor in graph units and their box in screen
 *  pixels relative to that anchor; higher priority first claims the space.
 *  A pair stops overlapping from the scale where their separation along x or
 *  y outgrows their boxes; a lower-priority label waits until every
 *  higher-priority label it would collide with has moved clear. */
export function activationScales(
  labels: { key: string; priority: number; ax: number; ay: number; box: Rect }[],
  minScale: number,
): Map<string, number> {
  const order = [...labels].sort((a, b) => b.priority - a.priority);
  const out = new Map<string, number>();
  // candidate pairs: boxes that overlap at minScale (cell = largest box in graph units there)
  let big = 1;
  for (const l of order) big = Math.max(big, l.box[2] - l.box[0], l.box[3] - l.box[1]);
  const cell = big / minScale;
  const grid = new Map<number, number[]>();
  order.forEach((l, i) => {
    const k = Math.floor(l.ax / cell) * 1_000_003 + Math.floor(l.ay / cell);
    const list = grid.get(k);
    if (list) list.push(i);
    else grid.set(k, [i]);
  });
  const sepScale = (a: { ax: number; ay: number; box: Rect }, b: { ax: number; ay: number; box: Rect }) => {
    // screen x of a box edge at scale s: anchor * s + box offset; they separate on x when
    // (b.ax - a.ax) s >= a.box[2] - b.box[0] (b to the right) or the mirror case
    const axis = (d: number, lo: number, hi: number) => {
      if (d > 0) return Math.max(0, lo / d);
      if (d < 0) return Math.max(0, hi / -d);
      return lo <= 0 || hi <= 0 ? 0 : Infinity;
    };
    const sx = axis(b.ax - a.ax, a.box[2] - b.box[0], b.box[2] - a.box[0]);
    const sy = axis(b.ay - a.ay, a.box[3] - b.box[1], b.box[3] - a.box[1]);
    return Math.min(sx, sy);
  };
  for (let i = 0; i < order.length; i++) {
    const l = order[i];
    let s = 0;
    const gx = Math.floor(l.ax / cell), gy = Math.floor(l.ay / cell);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const j of grid.get((gx + dx) * 1_000_003 + gy + dy) ?? []) {
        if (j >= i) continue;
        const sij = sepScale(order[j], l);
        const sj = out.get(order[j].key)!;
        if (sij > sj) s = Math.max(s, sij);       // they would clash once j is shown
      }
    }
    out.set(l.key, s);
  }
  return out;
}
