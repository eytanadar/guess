// Excentric labelling lens (Fekete & Plaisant 1999; extended as in Bertini,
// Rigamonti & Lalanne, "Extended Excentric Labeling", EuroVis 2009).
//
// A circle follows the pointer. The labels of the nodes inside it are listed
// in two columns beside it, ordered radially so the lines joining labels to
// nodes don't cross; labels take their node's colour and (within bounds) its
// size. When there are more than fit, the lists scroll (Shift+wheel). The
// wheel resizes the lens, or it sizes itself to the density under it. A bar
// chart under the lens counts the nodes by colour (the categories after
// colorize). Clicking pins the lens ("detail state"): the bars then filter the
// labels, and the lens selects — click a label to select its node (Shift:
// add/remove), or "Select" for everything in the lens.
import type { NodeRec } from "./protocol";
import type { Renderer } from "./renderer";

export interface LensHooks {
  /** replace (or add to) the selection */
  select(ids: number[], add: boolean): void;
  /** add or remove one node */
  toggle(id: number): void;
  /** double-click a label: zoom to its node */
  zoomTo(id: number): void;
}

interface Inside { n: NodeRec; sx: number; sy: number; angle: number }

const SVG = "http://www.w3.org/2000/svg";
const ROW = 17;          // label row height at the normal size, px
const GAP = 22;          // between the circle and the label columns, px

function hex(c: number) {
  return "#" + c.toString(16).padStart(6, "0");
}

/** The node colour, darkened enough to read as text on a light panel. */
function inkFor(c: number, dark: boolean) {
  const r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255;
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  if (!dark && lum > 0.62) {
    const k = 0.62 / lum;
    return `rgb(${Math.round(r * k)},${Math.round(g * k)},${Math.round(b * k)})`;
  }
  if (dark && lum < 0.35) {
    const k = 0.35 / Math.max(lum, 0.01);
    return `rgb(${Math.min(255, Math.round(r * k + 40))},${Math.min(255, Math.round(g * k + 40))},${Math.min(255, Math.round(b * k + 40))})`;
  }
  return hex(c);
}

export class ExcentricLens {
  private layer: HTMLDivElement;
  private svg: SVGSVGElement;
  private cols: HTMLDivElement;
  private panel: HTMLDivElement;
  private active = false;
  private stuck = false;
  private x = 0;
  private y = 0;
  private hasPointer = false;
  /** lens radius (px) and whether it follows the density */
  radius = 60;
  auto = false;
  /** most labels per side before scrolling */
  maxPerSide = 15;
  private scroll = { left: 0, right: 0 };
  private filter = new Set<number>();
  private lastKey = "";
  private inside: Inside[] = [];
  private raf = 0;

  constructor(private host: HTMLElement, private renderer: Renderer, private hooks: LensHooks) {
    this.layer = document.createElement("div");
    this.layer.className = "lens-layer";
    this.layer.hidden = true;
    this.svg = document.createElementNS(SVG, "svg");
    this.svg.classList.add("lens-svg");
    this.cols = document.createElement("div");
    this.cols.className = "lens-cols";
    this.panel = document.createElement("div");
    this.panel.className = "lens-panel";
    this.layer.append(this.svg, this.cols, this.panel);
    host.append(this.layer);
    host.addEventListener("pointermove", (ev) => {
      if (!this.active || this.stuck) return;
      if ((ev.target as HTMLElement).closest?.(".lens-cols, .lens-panel")) return;
      const r = host.getBoundingClientRect();
      this.x = ev.clientX - r.left;
      this.y = ev.clientY - r.top;
      this.hasPointer = true;
      this.scroll = { left: 0, right: 0 };
      this.schedule();
    });
    host.addEventListener("pointerleave", () => {
      if (!this.active || this.stuck) return;
      this.hasPointer = false;
      this.schedule();
    });
  }

  isActive() {
    return this.active;
  }

  setActive(on: boolean) {
    this.active = on;
    this.stuck = false;
    this.filter.clear();
    this.lastKey = "";
    if (!on) this.hooksClear();
    this.schedule();
  }

  /** set from Python: excentricLens(radius=, autoSize=, maxLabels=) */
  configure(o: { radius?: number; auto?: boolean; max?: number }) {
    if (o.radius) this.radius = Math.max(15, Math.min(400, o.radius));
    if (o.auto !== undefined) this.auto = o.auto;
    if (o.max) this.maxPerSide = Math.max(3, Math.min(60, o.max));
    this.lastKey = "";
    this.schedule();
  }

  /** A click on the graph in lens mode: pin or release the lens. */
  click() {
    if (!this.active) return;
    this.stuck = !this.stuck;
    if (!this.stuck) this.filter.clear();
    this.lastKey = "";
    this.schedule();
  }

  /** Esc: release a pinned lens; false if there was nothing to release. */
  release(): boolean {
    if (!this.stuck) return false;
    this.stuck = false;
    this.filter.clear();
    this.lastKey = "";
    this.schedule();
    return true;
  }

  /** Wheel over the graph in lens mode: resize (Shift: scroll the lists). */
  wheel(ev: WheelEvent): boolean {
    if (!this.active) return false;
    if (ev.shiftKey) {
      const d = Math.sign(ev.deltaY || ev.deltaX);
      this.scroll.left = Math.max(0, this.scroll.left + d * 3);
      this.scroll.right = Math.max(0, this.scroll.right + d * 3);
    } else {
      this.auto = false;
      this.radius = Math.max(15, Math.min(400, this.radius * Math.exp(-ev.deltaY * 0.002)));
    }
    this.lastKey = "";
    this.schedule();
    return true;
  }

  /** Call when the graph or camera may have changed. */
  schedule() {
    if (this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.render();
    });
  }

  /** Keep up with camera moves and data changes while active. */
  tick() {
    if (!this.active || !this.hasPointer) return;
    const key = `${this.renderer.cameraKey()}|${this.renderer.nodes.size}`;
    if (key !== this.lastKey.split("#")[0]) this.schedule();
  }

  private hooksClear() {
    this.renderer.highlight([], []);
  }

  private nodesIn(r: number): Inside[] {
    const out: Inside[] = [];
    for (const n of this.renderer.nodes.values()) {
      if (!n.v) continue;
      const { sx, sy } = this.renderer.toScreen(n.x + n.w / 2, n.y + n.h / 2);
      const dx = sx - this.x, dy = sy - this.y;
      if (dx * dx + dy * dy <= r * r) out.push({ n, sx, sy, angle: Math.atan2(dy, dx) });
    }
    return out;
  }

  private render() {
    const show = this.active && this.hasPointer;
    this.layer.hidden = !show;
    if (!show) return;
    this.lastKey = `${this.renderer.cameraKey()}|${this.renderer.nodes.size}#${this.x},${this.y},${this.radius},${this.stuck}`;
    // focus area: fixed, or sized to the density (about 20 nodes under it)
    let r = this.radius;
    if (this.auto && !this.stuck) {
      const c0 = this.nodesIn(this.radius).length;
      r = Math.max(25, Math.min(180, this.radius * Math.sqrt(20 / Math.max(c0, 1))));
    }
    this.inside = this.nodesIn(r);
    const theme = document.documentElement.dataset.theme;
    const dark = theme === "dark" || (theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
    const shown = this.filter.size ? this.inside.filter((i) => this.filter.has(i.n.c)) : this.inside;
    // radial order: each label goes to the side its node is on, in the order
    // of the node's projection onto the circle, so the lines don't cross
    const left = shown.filter((i) => Math.cos(i.angle) < 0).sort((a, b) => Math.sin(a.angle) - Math.sin(b.angle));
    const right = shown.filter((i) => Math.cos(i.angle) >= 0).sort((a, b) => Math.sin(a.angle) - Math.sin(b.angle));
    const H = this.host.clientHeight;
    const cap = Math.max(3, Math.min(this.maxPerSide, Math.floor((H - 60) / ROW) - 2));

    // the circle
    const svg = this.svg;
    svg.replaceChildren();
    svg.setAttribute("width", String(this.host.clientWidth));
    svg.setAttribute("height", String(H));
    const circle = document.createElementNS(SVG, "circle");
    circle.setAttribute("cx", String(this.x));
    circle.setAttribute("cy", String(this.y));
    circle.setAttribute("r", String(r));
    circle.setAttribute("class", this.stuck ? "lens-circle stuck" : "lens-circle");
    svg.append(circle);

    this.cols.replaceChildren();
    const column = (items: Inside[], side: "left" | "right") => {
      const off = Math.min(this.scroll[side], Math.max(0, items.length - cap));
      this.scroll[side] = off;
      const visible = items.slice(off, off + cap);
      const before = off, after = Math.max(0, items.length - off - cap);
      const rows = visible.length + (before ? 1 : 0) + (after ? 1 : 0);
      const colX = side === "left" ? this.x - r - GAP : this.x + r + GAP;
      let y = Math.max(8, Math.min(H - rows * ROW - 8, this.y - (rows * ROW) / 2));
      const col = document.createElement("div");
      col.className = `lens-col ${side}`;
      col.style.top = `${y}px`;
      if (side === "left") col.style.right = `${this.host.clientWidth - colX}px`;
      else col.style.left = `${colX}px`;
      const more = (k: number, dir: string) => {
        const d = document.createElement("div");
        d.className = "lens-more";
        d.textContent = `${dir} ${k} more`;
        d.title = "Shift+wheel scrolls the labels";
        col.append(d);
        y += ROW;
      };
      if (before) more(before, "↑");
      for (const it of visible) {
        const n = it.n;
        const lab = document.createElement("div");
        lab.className = "lens-label";
        if (this.renderer.selection.has(n.i)) lab.classList.add("selected");
        lab.textContent = n.l || n.name;
        const size = Math.max(10, Math.min(17, 10 + 2.2 * Math.log2(Math.max(n.w, 4) / 8)));
        lab.style.fontSize = `${size.toFixed(1)}px`;
        lab.style.color = inkFor(n.c, dark);
        lab.title = `${n.name} · click selects (Shift: add/remove) · double-click zooms`;
        const rowY = y + ROW / 2;
        // node -> circle (radially) -> label
        const bx = this.x + r * Math.cos(it.angle), by = this.y + r * Math.sin(it.angle);
        const line = document.createElementNS(SVG, "polyline");
        line.setAttribute("points", `${it.sx},${it.sy} ${bx},${by} ${side === "left" ? colX + 2 : colX - 2},${rowY}`);
        line.setAttribute("class", "lens-line");
        line.setAttribute("stroke", inkFor(n.c, dark));
        svg.append(line);
        lab.addEventListener("pointerenter", () => {
          line.classList.add("hot");
          this.renderer.highlight([n.i], []);
        });
        lab.addEventListener("pointerleave", () => {
          line.classList.remove("hot");
          this.renderer.highlight([], []);
        });
        lab.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (ev.shiftKey) this.hooks.toggle(n.i);
          else this.hooks.select([n.i], false);
          this.lastKey = "";
          this.schedule();
        });
        lab.addEventListener("dblclick", (ev) => {
          ev.stopPropagation();
          this.hooks.zoomTo(n.i);
        });
        col.append(lab);
        y += ROW;
      }
      if (after) more(after, "↓");
      this.cols.append(col);
    };
    column(left, "left");
    column(right, "right");

    // summary: nodes under the lens by colour; pinned, the bars filter
    this.panel.replaceChildren();
    const counts = new Map<number, number>();
    for (const it of this.inside) counts.set(it.n.c, (counts.get(it.n.c) ?? 0) + 1);
    const groups = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
    const top = groups.length ? groups[0][1] : 1;
    const head = document.createElement("div");
    head.className = "lens-head";
    head.textContent = `${this.inside.length} node${this.inside.length === 1 ? "" : "s"}` + (this.filter.size ? ` · ${shown.length} shown` : "");
    this.panel.append(head);
    if (groups.length > 1) {
      const bars = document.createElement("div");
      bars.className = "lens-bars";
      for (const [c, k] of groups) {
        const b = document.createElement("button");
        b.className = "lens-bar";
        if (this.filter.size && !this.filter.has(c)) b.classList.add("off");
        b.style.setProperty("--h", `${Math.max(3, (k / top) * 28)}px`);
        b.style.setProperty("--c", hex(c));
        b.title = `${k} node${k === 1 ? "" : "s"}` + (this.stuck ? " · click to show only these (again to include others)" : " · click the lens to pin it, then filter");
        b.disabled = !this.stuck;
        b.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (this.filter.has(c)) this.filter.delete(c);
          else this.filter.add(c);
          this.lastKey = "";
          this.schedule();
        });
        bars.append(b);
      }
      this.panel.append(bars);
    }
    if (this.stuck) {
      const row = document.createElement("div");
      row.className = "lens-actions";
      const sel = document.createElement("button");
      sel.textContent = `Select ${shown.length}`;
      sel.title = "Select the nodes under the lens (those shown, if filtered); Shift adds to the selection";
      sel.disabled = !shown.length;
      sel.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this.hooks.select(shown.map((i) => i.n.i), ev.shiftKey);
        this.lastKey = "";
        this.schedule();
      });
      const close = document.createElement("button");
      close.textContent = "Release";
      close.title = "Let the lens follow the pointer again (or click the graph, or Esc)";
      close.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this.release();
      });
      row.append(sel, close);
      this.panel.append(row);
    }
    const below = this.y + r + 10 + 70 < H;
    this.panel.style.left = `${this.x}px`;
    this.panel.style.top = below ? `${this.y + r + 10}px` : "";
    this.panel.style.bottom = below ? "" : `${H - (this.y - r - 10)}px`;
    this.panel.classList.toggle("stuck", this.stuck);
  }
}
