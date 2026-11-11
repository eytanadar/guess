// The Cluster tool: label nodes by hand, one lasso (or box) per cluster.
// Each selection becomes labelCluster([...], id, field) — an ordinary, undoable
// command — and the ids count up. While the tool is on, labelled nodes show in
// their cluster's colour and the rest in grey (a preview: nothing is recoloured).
import type { Renderer } from "./renderer";

export interface ClusterInfo {
  exists: boolean;
  type: string | null;
  labels: [number, string | number][];
  next: number;
  total: number;
}

export interface ClusterHost {
  info(field: string): Promise<ClusterInfo>;
  /** run Gython as a (hidden) command; resolves with success */
  run(code: string): Promise<boolean>;
  /** run Gython as a visible cell */
  submit(code: string): void;
  nodeName(id: number): string | undefined;
  hover(ids: number[] | null): void;
  center(ids: number[]): void;
  /** ask for a field name (null: cancelled) */
  askField(current: string): Promise<string | null>;
  done(): void;
}

// categorical colours for the preview (repeat after 12)
const PALETTE = [0x4e79a7, 0xf28e2b, 0xe15759, 0x76b7b2, 0x59a14f, 0xedc948, 0xb07aa1, 0xff9da7, 0x9c755f, 0x17becf, 0xbcbd22, 0x8c564b];
const hex = (c: number) => "#" + c.toString(16).padStart(6, "0");

export class ClusterTool {
  active = false;
  field = "cluster";
  private type: string | null = null;
  private labels = new Map<number, string | number>();
  private order: (string | number)[] = [];
  private total = 0;
  private suggested = 1;
  private last: string | number | null = null;
  private bar = document.createElement("div");
  private fieldBtn = document.createElement("button");
  private nextInput = document.createElement("input");
  private swatch = document.createElement("span");
  private relabelBox = document.createElement("input");
  private counts = document.createElement("span");
  private left = document.createElement("button");
  private busy: Promise<unknown> = Promise.resolve();

  constructor(host: HTMLElement, private renderer: Renderer, private h: ClusterHost) {
    this.bar.className = "cluster-bar";
    this.bar.hidden = true;
    const title = document.createElement("strong");
    title.textContent = "Cluster";
    this.fieldBtn.className = "cluster-field";
    this.fieldBtn.title = "The node field the cluster ids go in (click to change)";
    this.fieldBtn.onclick = async () => {
      const f = await this.h.askField(this.field);
      if (f && f !== this.field) await this.start(f);
    };
    const nextLabel = document.createElement("label");
    nextLabel.textContent = "next id ";
    this.nextInput.className = "cluster-next";
    this.nextInput.size = 6;
    this.nextInput.title = "The id the next selection gets; it counts up after each (type your own to override)";
    this.nextInput.oninput = () => this.paintSwatch();
    this.nextInput.onkeydown = (ev) => {
      if (ev.key === "Enter" || ev.key === "Escape") this.nextInput.blur();
      ev.stopPropagation();
    };
    nextLabel.append(this.nextInput, this.swatch);
    this.swatch.className = "cluster-swatch";
    const relabel = document.createElement("label");
    this.relabelBox.type = "checkbox";
    this.relabelBox.checked = true;
    relabel.append(this.relabelBox, " relabel");
    relabel.title = "On: nodes a new selection catches move to the new cluster, even if they had one. Off: they keep the cluster they have, so quick lassos can overlap.";
    this.counts.className = "cluster-counts";
    this.left.className = "cluster-left";
    this.left.title = "Hover: show the nodes not labelled yet · click: zoom to them";
    this.left.onmouseenter = () => this.h.hover(this.unlabelled());
    this.left.onmouseleave = () => this.h.hover(null);
    this.left.onclick = () => {
      const ids = this.unlabelled();
      if (ids.length) this.h.center(ids);
    };
    const colour = document.createElement("button");
    colour.textContent = "Colour by it";
    colour.title = "colorize(field): keep these colours after the tool is off";
    colour.onclick = () => this.h.submit(`colorize(${this.field})`);
    const done = document.createElement("button");
    done.textContent = "Done";
    done.onclick = () => this.h.done();
    const hint = document.createElement("div");
    hint.className = "cluster-hint";
    hint.textContent = "Drag a lasso around nodes: they get the next id. Shift-drag: a box. " +
      "⌘/Ctrl-drag or click a node: add to the last cluster. Space-drag pans. ⌘Z undoes.";
    const row = document.createElement("div");
    row.className = "cluster-row";
    row.append(title, this.fieldBtn, nextLabel, relabel, this.counts, this.left, colour, done);
    this.bar.append(row, hint);
    host.append(this.bar);
  }

  async start(field: string) {
    this.field = field;
    this.active = true;
    this.last = null;
    this.nextInput.value = "";
    this.renderer.dragSelects = "lasso";
    this.bar.hidden = false;
    await this.refresh();
    this.nextInput.value = String(this.suggested);
    this.paintSwatch();
  }

  stop() {
    this.active = false;
    this.renderer.dragSelects = null;
    this.renderer.setPreviewColors(null);
    this.bar.hidden = true;
    this.h.hover(null);
  }

  /** Re-read the labels (after any command: undo, edits, a new graph). */
  async refresh() {
    if (!this.active) return;
    const info = await this.h.info(this.field);
    if (!this.active) return;
    this.type = info.type;
    this.total = info.total;
    this.suggested = info.next;
    this.labels = new Map(info.labels);
    const seen = new Set<string | number>();
    for (const [, v] of info.labels) seen.add(v);
    // keep earlier clusters' colours stable: first-seen order, new ones at the end
    this.order = [...this.order.filter((v) => seen.has(v)), ...[...seen].filter((v) => !this.order.includes(v))];
    // a numeric next id that is now taken (e.g. after undo/redo elsewhere) moves on
    const nv = this.nextValue();
    if (typeof nv === "number" && this.labelsHave(nv) && nv < info.next && this.last !== nv) this.nextInput.value = String(info.next);
    this.fieldBtn.textContent = this.field;
    this.paint();
  }

  /** A lasso or box was drawn: label what it caught (add: join the last cluster). */
  selected(ids: number[], add: boolean) {
    this.renderer.setSelection([]);
    if (!ids.length) return;
    this.busy = this.busy.then(() => this.assign(ids, add));
  }

  /** A click on a node: it joins the last cluster (or starts the next one). */
  click(id: number) {
    this.busy = this.busy.then(() => this.assign([id], true));
  }

  private async assign(ids: number[], add: boolean) {
    const joinLast = add && this.last !== null;
    const value = joinLast ? this.last! : this.nextValue();
    if (value === "") return;
    const names = ids.map((i) => this.h.nodeName(i)).filter((n): n is string => n !== undefined);
    if (!names.length) return;
    const lit = typeof value === "number" ? String(value) : JSON.stringify(value);
    const relabel = joinLast || this.relabelBox.checked;
    const ok = await this.h.run(`labelCluster(${JSON.stringify(names)}, ${lit}, ${JSON.stringify(this.field)}${relabel ? "" : ", relabel=false"})`);
    if (!ok) return;
    this.last = value;
    if (!joinLast) this.nextInput.value = advance(String(value), this.suggested + 1);
    await this.refresh();
  }

  /** The next id as typed: a number when it is one (and the field holds numbers or doesn't exist yet). */
  private nextValue(): string | number {
    const t = this.nextInput.value.trim();
    if (/^-?\d+$/.test(t) && this.type !== "VARCHAR") return Number(t);
    return t;
  }

  private labelsHave(v: string | number) {
    for (const x of this.labels.values()) if (x === v) return true;
    return false;
  }

  private unlabelled(): number[] {
    const out: number[] = [];
    for (const id of this.renderer.nodes.keys()) if (!this.labels.has(id)) out.push(id);
    return out;
  }

  private colorOf(v: string | number) {
    let i = this.order.indexOf(v);
    if (i < 0) i = this.order.length;
    return PALETTE[i % PALETTE.length];
  }

  private paintSwatch() {
    const v = this.nextValue();
    this.swatch.style.background = hex(this.colorOf(v));
    this.swatch.title = this.labelsHave(v) ? `${v} already has nodes: a selection adds to it` : `cluster ${v}`;
    this.swatch.classList.toggle("existing", this.labelsHave(v));
  }

  /** Labelled nodes in their cluster's colour, the rest grey; the counts. */
  private paint() {
    const dark = document.documentElement.dataset.theme === "dark" ||
      (document.documentElement.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
    const grey = dark ? 0x4a4d52 : 0xd4d6da;
    const colors = new Map<number, number>();
    for (const id of this.renderer.nodes.keys()) {
      const v = this.labels.get(id);
      colors.set(id, v === undefined ? grey : this.colorOf(v));
    }
    this.renderer.setPreviewColors(colors);
    const n = this.labels.size;
    this.counts.textContent = `${this.order.length} cluster${this.order.length === 1 ? "" : "s"} · ${n} labelled`;
    const rest = this.total - n;
    this.left.textContent = rest ? `${rest} left` : "all labelled ✓";
    this.left.classList.toggle("finished", rest === 0);
    this.paintSwatch();
  }
}

/** The id after this one: 4 → 5, a7 → a8; plain text → the next free number. */
function advance(v: string, fallback: number): string {
  if (/^-?\d+$/.test(v)) return String(Number(v) + 1);
  const m = /^(.*?)(\d+)$/.exec(v);
  if (m) return m[1] + String(Number(m[2]) + 1).padStart(m[2].length, "0");
  return String(fallback);
}
