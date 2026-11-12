/**
 * Edge line styles and arrowheads as plain geometry ("primitives"), so the
 * screen (PixiJS) and SVG export draw them the same way.
 *
 * Line styles: solid, dashed, dotted, taper (wide at the source, a point at the
 * target), wave, double, fuzzy, gradient (source colour to target colour) and
 * flow (dashes moving from source to target). Arrowheads: triangle, swept,
 * open, diamond, circle, tee and none.
 */

export const LINE_STYLES = ["solid", "dashed", "dotted", "taper", "wave", "double", "fuzzy", "gradient", "flow"] as const;
export const ARROWHEADS = ["triangle", "swept", "open", "diamond", "circle", "tee", "none"] as const;

/** A stroked polyline (optionally dashed: [on, off]; on = 0 draws dots), a filled polygon, or a filled dot. */
export type Prim =
  | { k: "line"; p: number[]; w: number; c: number; a: number; dash?: [number, number]; flow?: boolean; grad?: [number, number] }
  | { k: "poly"; p: number[]; c: number; a: number }
  | { k: "dot"; x: number; y: number; r: number; c: number; a: number };

export function dashFor(style: string, w: number): [number, number] | undefined {
  if (style === "dashed") return [Math.max(4, w * 3), Math.max(3, w * 2)];
  if (style === "dotted") return [0, Math.max(3, w * 2.2)];
  if (style === "flow") return [Math.max(5, w * 3), Math.max(4, w * 2.5)];
  return undefined;
}

function lengths(p: number[]): number[] {
  const out = [0];
  for (let k = 2; k < p.length; k += 2) out.push(out[out.length - 1] + Math.hypot(p[k] - p[k - 2], p[k + 1] - p[k - 1]));
  return out;
}

/** The point and unit direction at distance s along a polyline. */
function at(p: number[], cum: number[], s: number): [number, number, number, number] {
  let i = 1;
  while (i < cum.length - 1 && cum[i] < s) i++;
  const seg = cum[i] - cum[i - 1] || 1;
  const t = Math.max(0, Math.min(1, (s - cum[i - 1]) / seg));
  const x0 = p[2 * i - 2], y0 = p[2 * i - 1], x1 = p[2 * i], y1 = p[2 * i + 1];
  const ux = (x1 - x0) / seg, uy = (y1 - y0) / seg;
  return [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, ux, uy];
}

/** The polyline resampled every `step` (keeps both ends). */
function resample(p: number[], step: number): { pts: number[]; dirs: number[]; total: number } {
  const cum = lengths(p), total = cum[cum.length - 1];
  const n = Math.max(2, Math.min(800, Math.ceil(total / step) + 1));
  const pts: number[] = [], dirs: number[] = [];
  for (let k = 0; k < n; k++) {
    const [x, y, ux, uy] = at(p, cum, (total * k) / (n - 1));
    pts.push(x, y);
    dirs.push(ux, uy);
  }
  return { pts, dirs, total };
}

/** The polyline shifted sideways by d (left of the direction of travel). */
function offset(p: number[], d: number): number[] {
  const { pts, dirs } = resample(p, 4);
  const out: number[] = [];
  for (let k = 0; k < pts.length; k += 2) out.push(pts[k] - dirs[k + 1] * d, pts[k + 1] + dirs[k] * d);
  return out;
}

/** Dash pieces [polyline, ...] along p, shifted by phase (for flow). on = 0: dot centres. */
export function dashes(p: number[], on: number, off: number, phase = 0): number[][] {
  const cum = lengths(p), total = cum[cum.length - 1];
  const period = on + off;
  if (period <= 0 || total <= 0) return [p];
  const out: number[][] = [];
  let s = (phase % period) - period;
  for (; s < total; s += period) {
    if (on === 0) {
      if (s >= 0) {
        const [x, y] = at(p, cum, s);
        out.push([x, y]);
      }
      continue;
    }
    const s0 = Math.max(0, s), s1 = Math.min(total, s + on);
    if (s1 <= s0) continue;
    const piece: number[] = [];
    const [x0, y0] = at(p, cum, s0);
    piece.push(x0, y0);
    for (let i = 1; i < cum.length - 1; i++) if (cum[i] > s0 && cum[i] < s1) piece.push(p[2 * i], p[2 * i + 1]);
    const [x1, y1] = at(p, cum, s1);
    piece.push(x1, y1);
    out.push(piece);
  }
  return out;
}

/**
 * The primitives for one edge's line. p: the polyline from source to target
 * (centre coordinates); c0/c1: the source and target node colours (gradient).
 */
export function linePrims(style: string, p: number[], w: number, c: number, a: number, c0: number, c1: number): Prim[] {
  switch (style) {
    case "dashed": case "dotted": case "flow":
      return [{ k: "line", p, w, c, a, dash: dashFor(style, w), flow: style === "flow" }];
    case "taper": {
      // wide at the source, narrowing to a point at the target: direction without arrowheads
      const { pts, dirs } = resample(p, 4);
      const n = pts.length / 2, w0 = Math.max(w * 2.4, 3);
      const left: number[] = [], right: number[] = [];
      for (let k = 0; k < n; k++) {
        const h = (w0 * (1 - k / (n - 1)) + 0.4) / 2;
        const x = pts[2 * k], y = pts[2 * k + 1], nx = -dirs[2 * k + 1], ny = dirs[2 * k];
        left.push(x + nx * h, y + ny * h);
        right.push(x - nx * h, y - ny * h);
      }
      for (let k = right.length - 2; k >= 0; k -= 2) left.push(right[k], right[k + 1]);
      return [{ k: "poly", p: left, c, a }];
    }
    case "wave": {
      const amp = Math.max(2, w * 1.4), wl = Math.max(7, w * 4.5);
      const { pts, dirs, total } = resample(p, Math.min(wl / 8, 2));
      const n = pts.length / 2, out: number[] = [];
      for (let k = 0; k < n; k++) {
        const s = (total * k) / (n - 1);
        // fade the wave in and out so it starts and ends on the nodes' centres
        const fade = Math.min(1, s / wl, (total - s) / wl);
        const d = Math.sin((2 * Math.PI * s) / wl) * amp * fade;
        out.push(pts[2 * k] - dirs[2 * k + 1] * d, pts[2 * k + 1] + dirs[2 * k] * d);
      }
      return [{ k: "line", p: out, w, c, a }];
    }
    case "double": {
      const half = Math.max(w * 0.45, 0.6), gap = Math.max(w * 0.7, 1.4);
      return [{ k: "line", p: offset(p, gap), w: half, c, a }, { k: "line", p: offset(p, -gap), w: half, c, a }];
    }
    case "fuzzy":
      return [
        { k: "line", p, w: w * 4, c, a: a * 0.08 },
        { k: "line", p, w: w * 2.6, c, a: a * 0.14 },
        { k: "line", p, w: w * 1.6, c, a: a * 0.3 },
        { k: "line", p, w: w * 0.8, c, a: a * 0.7 },
      ];
    case "gradient":
      return [{ k: "line", p, w, c, a, grad: [c0, c1] }];
    default:
      return [{ k: "line", p, w, c, a }];
  }
}

/**
 * The primitives for an arrowhead whose tip is at (px, py), pointing along
 * (ux, uy), `size` long and `half` wide on each side.
 */
export function headPrims(kind: string, px: number, py: number, ux: number, uy: number, size: number, half: number,
                          w: number, c: number, a: number): Prim[] {
  const qx = px - ux * size, qy = py - uy * size;
  const nx = -uy, ny = ux;
  switch (kind) {
    case "none": return [];
    case "swept": {
      // a swept-back head (a notch in the base), slightly larger, as in curved flow maps
      const s = size * 1.25, hh = half * 1.25;
      const bx = px - ux * s, by = py - uy * s, mx = px - ux * s * 0.62, my = py - uy * s * 0.62;
      return [{ k: "poly", p: [px, py, bx + nx * hh, by + ny * hh, mx, my, bx - nx * hh, by - ny * hh], c, a }];
    }
    case "open":
      return [{ k: "line", p: [qx + nx * half, qy + ny * half, px, py, qx - nx * half, qy - ny * half], w: Math.max(1, w * 0.8), c, a }];
    case "diamond": {
      const L = size * 1.3, mx = px - ux * L * 0.5, my = py - uy * L * 0.5, h = half * 1.05;
      const ex = px - ux * L, ey = py - uy * L;
      return [{ k: "poly", p: [px, py, mx + nx * h, my + ny * h, ex, ey, mx - nx * h, my - ny * h], c, a }];
    }
    case "circle": {
      const r = circleRadius(size, half, w);
      return [{ k: "dot", x: px - ux * r, y: py - uy * r, r, c, a }];
    }
    case "tee": {
      const tx = px - ux * Math.max(1, w * 0.6), ty = py - uy * Math.max(1, w * 0.6);
      return [{ k: "line", p: [tx + nx * half, ty + ny * half, tx - nx * half, ty - ny * half], w: Math.max(1.5, w * 1.1), c, a }];
    }
    default:
      return [{ k: "poly", p: [px, py, qx + nx * half, qy + ny * half, qx - nx * half, qy - ny * half], c, a }];
  }
}

const circleRadius = (size: number, half: number, w: number) => Math.max(half * 1.05, w * 0.9, size * 0.4);

/** How far back from its tip an arrowhead reaches along the edge (where the line should stop). */
export function headDepth(kind: string, size: number, half: number, w: number): number {
  switch (kind) {
    case "none": return 0;
    case "swept": return size * 1.25 * 0.62;
    case "open": return Math.max(1, w * 0.8) * 0.7;
    case "diamond": return size * 1.3;
    case "circle": return 2 * circleRadius(size, half, w);
    case "tee": return Math.max(1, w * 0.6);
    default: return size * 0.6;
  }
}

/** A polyline with d cut off its end. */
export function trimEnd(p: number[], d: number): number[] {
  if (d <= 0) return p;
  const cum = lengths(p), total = cum[cum.length - 1];
  const keep = Math.max(total * 0.02, total - d);
  const out = [p[0], p[1]];
  for (let i = 1; i < cum.length - 1 && cum[i] < keep; i++) out.push(p[2 * i], p[2 * i + 1]);
  const [x, y] = at(p, cum, keep);
  out.push(x, y);
  return out;
}

/** Mix two 0xRRGGBB colours. */
export function mix(c0: number, c1: number, t: number): number {
  const r = ((c0 >> 16) & 255) * (1 - t) + ((c1 >> 16) & 255) * t;
  const g = ((c0 >> 8) & 255) * (1 - t) + ((c1 >> 8) & 255) * t;
  const b = (c0 & 255) * (1 - t) + (c1 & 255) * t;
  return (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b);
}

/** Split a polyline into n pieces with their colours along a gradient. */
export function gradientPieces(p: number[], c0: number, c1: number, n = 16): [number[], number][] {
  const cum = lengths(p), total = cum[cum.length - 1];
  const out: [number[], number][] = [];
  for (let k = 0; k < n; k++) {
    const s0 = (total * k) / n, s1 = (total * (k + 1)) / n;
    const [x0, y0] = at(p, cum, s0), [x1, y1] = at(p, cum, s1);
    const piece = [x0, y0];
    for (let i = 1; i < cum.length - 1; i++) if (cum[i] > s0 && cum[i] < s1) piece.push(p[2 * i], p[2 * i + 1]);
    piece.push(x1, y1);
    out.push([piece, mix(c0, c1, (k + 0.5) / n)]);
  }
  return out;
}
