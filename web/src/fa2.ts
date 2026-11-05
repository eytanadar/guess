// ForceAtlas2 with Barnes–Hut repulsion, for large graphs. Runs inside the
// Python worker and is called synchronously from layouts.py (forceAtlas2Layout
// on big graphs), a few iterations at a time, so the layout still animates and
// the Stop button still works between calls. Same forces and adaptive speed as
// the numpy version (Gephi's ForceAtlas2.java).

export interface FA2Options {
  scaling: number; gravity: number; strong: boolean; linlog: boolean;
  dissuade: boolean; overlap: boolean; theta: number; jitter: number;
}

export class GuessFA2 {
  private n: number;
  private x: Float64Array; private y: Float64Array;
  private dx: Float64Array; private dy: Float64Array;
  private ox: Float64Array; private oy: Float64Array;
  private mass: Float64Array; private radius: Float64Array; private fixed: Uint8Array;
  private src: Int32Array; private dst: Int32Array; private w: Float64Array;
  private o: FA2Options;
  private speed = 1;
  private efficiency = 1;
  private coef: number;
  // quadtree storage (rebuilt every iteration)
  private qx = new Float64Array(0); private qy = new Float64Array(0); private qm = new Float64Array(0);
  private qsize = new Float64Array(0); private qcx = new Float64Array(0); private qcy = new Float64Array(0);
  private qchild = new Int32Array(0); private qbody = new Int32Array(0); private qcount = 0;

  constructor(pos: ArrayLike<number>, mass: ArrayLike<number>, radius: ArrayLike<number>, fixed: ArrayLike<number>,
              src: ArrayLike<number>, dst: ArrayLike<number>, weight: ArrayLike<number>, opts: string) {
    this.n = mass.length;
    const n = this.n;
    this.x = new Float64Array(n); this.y = new Float64Array(n);
    for (let i = 0; i < n; i++) { this.x[i] = pos[2 * i]; this.y[i] = pos[2 * i + 1]; }
    this.dx = new Float64Array(n); this.dy = new Float64Array(n);
    this.ox = new Float64Array(n); this.oy = new Float64Array(n);
    this.mass = Float64Array.from(mass); this.radius = Float64Array.from(radius);
    this.fixed = Uint8Array.from(fixed);
    this.src = Int32Array.from(src); this.dst = Int32Array.from(dst); this.w = Float64Array.from(weight);
    this.o = JSON.parse(opts);
    let m = 0;
    for (let i = 0; i < n; i++) m += this.mass[i];
    this.coef = this.o.dissuade ? m / Math.max(n, 1) : 1;
  }

  /** Run k iterations; returns positions as [x0, y0, x1, y1, ...]. */
  step(k: number): Float64Array {
    for (let it = 0; it < k; it++) this.iterate();
    const out = new Float64Array(2 * this.n);
    for (let i = 0; i < this.n; i++) { out[2 * i] = this.x[i]; out[2 * i + 1] = this.y[i]; }
    return out;
  }

  private iterate() {
    const { n, x, y, dx, dy, mass, o } = this;
    dx.fill(0); dy.fill(0);
    this.buildTree();
    const kr = o.scaling;
    for (let i = 0; i < n; i++) this.repulse(i, kr);
    // gravity toward the origin
    for (let i = 0; i < n; i++) {
      const d = Math.hypot(x[i], y[i]);
      if (d <= 0) continue;
      const f = o.strong ? mass[i] * o.gravity : (mass[i] * o.gravity) / d;
      dx[i] -= x[i] * f; dy[i] -= y[i] * f;
    }
    // attraction
    const { src, dst, w, radius } = this;
    for (let e = 0; e < src.length; e++) {
      const a = src[e], b = dst[e];
      const ex = x[a] - x[b], ey = y[a] - y[b];
      let d = Math.hypot(ex, ey);
      if (o.overlap) d -= radius[a] + radius[b];
      let f: number;
      if (o.overlap && d <= 0) continue;
      if (o.linlog) f = d > 0 ? -this.coef * w[e] * Math.log1p(d) / Math.hypot(ex, ey) : 0;
      else f = -this.coef * w[e];
      if (o.dissuade) f /= mass[a];
      dx[a] += ex * f; dy[a] += ey * f;
      dx[b] -= ex * f; dy[b] -= ey * f;
    }
    // adaptive speed (ForceAtlas2.java)
    let swing = 0, traction = 0;
    const { ox, oy, fixed } = this;
    for (let i = 0; i < n; i++) {
      if (fixed[i]) continue;
      swing += mass[i] * Math.hypot(dx[i] - ox[i], dy[i] - oy[i]);
      traction += 0.5 * mass[i] * Math.hypot(dx[i] + ox[i], dy[i] + oy[i]);
    }
    traction = traction || 1e-9;
    const est = 0.05 * Math.sqrt(n);
    let jt = o.jitter * Math.max(Math.sqrt(est), Math.min(10, (est * traction) / (n * n)));
    if (swing / traction > 2) {
      if (this.efficiency > 0.05) this.efficiency *= 0.5;
      jt = Math.max(jt, o.jitter);
    }
    const target = (jt * this.efficiency * traction) / Math.max(swing, 1e-9);
    if (swing > jt * traction) {
      if (this.efficiency > 0.05) this.efficiency *= 0.7;
    } else if (this.speed < 1000) this.efficiency *= 1.3;
    this.speed += Math.min(target - this.speed, 0.5 * this.speed);
    for (let i = 0; i < n; i++) {
      if (fixed[i]) { ox[i] = 0; oy[i] = 0; continue; }
      const sw = mass[i] * Math.hypot(dx[i] - ox[i], dy[i] - oy[i]);
      let f = this.speed / (1 + Math.sqrt(this.speed * sw));
      if (o.overlap) {
        const df = Math.hypot(dx[i], dy[i]);
        f = df > 0 ? Math.min(0.1 * f * df, 10) / df : 0;
      }
      x[i] += dx[i] * f; y[i] += dy[i] * f;
      ox[i] = dx[i]; oy[i] = dy[i];
    }
  }

  // ---- Barnes–Hut quadtree --------------------------------------------------------
  private alloc(cap: number) {
    if (this.qx.length >= cap) return;
    const grow = (a: Float64Array) => { const b = new Float64Array(cap); b.set(a); return b; };
    this.qx = grow(this.qx); this.qy = grow(this.qy); this.qm = grow(this.qm);
    this.qsize = grow(this.qsize); this.qcx = grow(this.qcx); this.qcy = grow(this.qcy);
    const c = new Int32Array(cap * 4); c.set(this.qchild); this.qchild = c;
    const b = new Int32Array(cap); b.set(this.qbody); this.qbody = b;
  }

  private newCell(cx: number, cy: number, size: number) {
    const k = this.qcount++;
    if (k >= this.qx.length) this.alloc(Math.max(64, this.qx.length * 2));
    this.qx[k] = 0; this.qy[k] = 0; this.qm[k] = 0;
    this.qcx[k] = cx; this.qcy[k] = cy; this.qsize[k] = size;
    this.qchild.fill(-1, 4 * k, 4 * k + 4);
    this.qbody[k] = -1;
    return k;
  }

  private buildTree() {
    const { n, x, y, mass } = this;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (let i = 0; i < n; i++) {
      x0 = Math.min(x0, x[i]); x1 = Math.max(x1, x[i]);
      y0 = Math.min(y0, y[i]); y1 = Math.max(y1, y[i]);
    }
    const size = Math.max(x1 - x0, y1 - y0, 1e-6) * 1.01;
    this.qcount = 0;
    this.alloc(Math.max(64, 4 * n));
    const root = this.newCell((x0 + x1) / 2, (y0 + y1) / 2, size);
    for (let i = 0; i < n; i++) this.insert(root, i, 0);
    // centres of mass
    const order: number[] = [];
    const stack = [root];
    while (stack.length) {
      const c = stack.pop()!;
      order.push(c);
      for (let q = 0; q < 4; q++) { const ch = this.qchild[4 * c + q]; if (ch >= 0) stack.push(ch); }
    }
    for (let k = order.length - 1; k >= 0; k--) {
      const c = order[k];
      const b = this.qbody[c];
      if (b >= 0) { this.qm[c] = mass[b]; this.qx[c] = x[b]; this.qy[c] = y[b]; continue; }
      let m = 0, sx = 0, sy = 0;
      for (let q = 0; q < 4; q++) {
        const ch = this.qchild[4 * c + q];
        if (ch < 0 || this.qm[ch] === 0) continue;
        m += this.qm[ch]; sx += this.qx[ch] * this.qm[ch]; sy += this.qy[ch] * this.qm[ch];
      }
      this.qm[c] = m;
      if (m > 0) { this.qx[c] = sx / m; this.qy[c] = sy / m; }
    }
  }

  private insert(c: number, i: number, depth: number) {
    const { x, y } = this;
    for (;;) {
      const leaf = this.qbody[c];
      const hasKids = this.qchild[4 * c] >= 0 || this.qchild[4 * c + 1] >= 0 || this.qchild[4 * c + 2] >= 0 || this.qchild[4 * c + 3] >= 0;
      if (leaf < 0 && !hasKids) { this.qbody[c] = i; return; }
      if (leaf >= 0) {
        if (depth > 40 || (x[leaf] === x[i] && y[leaf] === y[i])) {
          // coincident: nudge the newcomer
          x[i] += (Math.random() - 0.5) * 1e-3; y[i] += (Math.random() - 0.5) * 1e-3;
          if (depth > 40) return;
        }
        this.qbody[c] = -1;
        this.push(c, leaf);
      }
      const q = (x[i] >= this.qcx[c] ? 1 : 0) + (y[i] >= this.qcy[c] ? 2 : 0);
      let ch = this.qchild[4 * c + q];
      if (ch < 0) {
        const h = this.qsize[c] / 4;
        ch = this.newCell(this.qcx[c] + (q & 1 ? h : -h), this.qcy[c] + (q & 2 ? h : -h), this.qsize[c] / 2);
        this.qchild[4 * c + q] = ch;
        this.qbody[ch] = i;
        return;
      }
      c = ch;
      depth++;
    }
  }

  private push(c: number, i: number) {
    const q = (this.x[i] >= this.qcx[c] ? 1 : 0) + (this.y[i] >= this.qcy[c] ? 2 : 0);
    const h = this.qsize[c] / 4;
    const ch = this.newCell(this.qcx[c] + (q & 1 ? h : -h), this.qcy[c] + (q & 2 ? h : -h), this.qsize[c] / 2);
    this.qchild[4 * c + q] = ch;
    this.qbody[ch] = i;
  }

  private repulse(i: number, kr: number) {
    const { x, y, mass, radius, o } = this;
    const theta2 = o.theta * o.theta;
    const stack = [0];
    let fx = 0, fy = 0;
    while (stack.length) {
      const c = stack.pop()!;
      const m = this.qm[c];
      if (m === 0) continue;
      const b = this.qbody[c];
      if (b === i) continue;
      const ex = x[i] - this.qx[c], ey = y[i] - this.qy[c];
      const d2 = ex * ex + ey * ey;
      const s = this.qsize[c];
      if (b >= 0 || s * s < theta2 * d2) {
        if (d2 > 0) {
          let f: number;
          if (o.overlap && b >= 0) {
            const d = Math.sqrt(d2) - radius[i] - radius[b];
            f = d > 0 ? (kr * mass[i] * m) / (d * d) : d < 0 ? 100 * kr * mass[i] * m : 0;
          } else f = (kr * mass[i] * m) / d2;
          fx += ex * f; fy += ey * f;
        }
        continue;
      }
      for (let q = 0; q < 4; q++) { const ch = this.qchild[4 * c + q]; if (ch >= 0) stack.push(ch); }
    }
    this.dx[i] += fx; this.dy[i] += fy;
  }
}
