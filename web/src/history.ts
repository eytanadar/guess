// The history scrubber: the undo history as a list with a slider. Dragging the
// slider (or clicking a step) undoes or redoes to that point; hovering a step
// highlights what it touched.
import type { Dock, Item } from "./dock";

export interface HistoryStep {
  label: string;
  cell: number | null;
  done: boolean;
  count: number;
  /** also changed: "display" settings, saved "states" */
  also: string[];
}

export interface HistoryHost {
  steps(): Promise<{ steps: HistoryStep[]; at: number }>;
  items(i: number): Promise<Item[]>;
  /** Undo/redo until `at` steps are applied; resolves with the position reached. */
  goto(at: number): Promise<number>;
  hover(items: Item[] | null): void;
  /** Scroll the console to a cell and flash it. */
  reveal(cell: number): void;
  /** After moving through the history (watched cells refresh). */
  moved(): void;
  /** The panel opened or closed. */
  toggled?(open: boolean): void;
}

const ID = "history";

export class HistoryPanel {
  private body: HTMLElement | null = null;
  private steps: HistoryStep[] = [];
  private at = 0;
  private slider = document.createElement("input");
  private where = document.createElement("div");
  private list = document.createElement("ol");
  private moving = false;
  private target: number | null = null;
  private hoverToken = 0;

  constructor(private dock: Dock, private host: HistoryHost) {
    this.slider.type = "range";
    this.slider.min = "0";
    this.slider.className = "history-slider";
    this.slider.setAttribute("aria-label", "Steps applied");
    this.slider.addEventListener("input", () => this.goto(Number(this.slider.value)));
    this.slider.addEventListener("pointerleave", () => this.host.hover(null));
    this.where.className = "history-where";
    this.list.className = "history-list";
    this.list.addEventListener("mouseleave", () => this.host.hover(null));
  }

  get open() {
    return this.body !== null && this.dock.has(ID);
  }

  toggle() {
    if (this.open) this.dock.close(ID);
    else void this.show();
  }

  async show() {
    this.body = this.dock.pane(ID, "History", "right", () => {
      this.body = null;
      this.host.hover(null);
      this.host.toggled?.(false);
    });
    this.host.toggled?.(true);
    this.body.classList.add("history-body");
    const bar = document.createElement("div");
    bar.className = "history-bar";
    const back = document.createElement("button");
    back.textContent = "◀";
    back.title = "Undo one step";
    back.onclick = () => this.goto(this.at - 1);
    const fwd = document.createElement("button");
    fwd.textContent = "▶";
    fwd.title = "Redo one step";
    fwd.onclick = () => this.goto(this.at + 1);
    bar.append(back, this.slider, fwd);
    this.body.replaceChildren(bar, this.where, this.list);
    await this.refresh();
  }

  /** Re-read the history (after a command). */
  async refresh() {
    if (!this.open || this.moving) return;
    const h = await this.host.steps();
    this.steps = h.steps;
    this.at = h.at;
    this.render();
  }

  private render() {
    const n = this.steps.length;
    this.slider.max = String(n);
    this.slider.value = String(this.at);
    this.slider.disabled = n === 0;
    const cur = this.steps[this.at - 1];
    this.where.textContent = n === 0 ? "Nothing to undo yet." :
      this.at === 0 ? `At the start: all ${n} steps undone` :
      `After step ${this.at} of ${n}: ${cur.label}`;
    const rows: HTMLElement[] = [];
    const start = document.createElement("li");
    start.className = "history-step start" + (this.at === 0 ? " current" : "");
    start.textContent = "Start";
    start.title = "Undo every step";
    start.onclick = () => this.goto(0);
    start.onmouseenter = () => this.host.hover(null);
    rows.push(start);
    this.steps.forEach((s, i) => {
      const li = document.createElement("li");
      li.className = "history-step" + (i < this.at ? "" : " undone") + (i === this.at - 1 ? " current" : "");
      const num = document.createElement("span");
      num.className = "history-cell";
      num.textContent = s.cell != null ? `[${s.cell}]` : "·";
      if (s.cell != null) {
        num.title = "Show the cell in the console";
        num.onclick = (ev) => {
          ev.stopPropagation();
          this.host.reveal(s.cell!);
        };
      }
      const label = document.createElement("code");
      label.textContent = s.label;
      const what = document.createElement("span");
      what.className = "history-count";
      const parts = s.count ? [`${s.count} element${s.count === 1 ? "" : "s"}`] : [];
      what.textContent = [...parts, ...s.also].join(" · ");
      li.append(num, label, what);
      li.title = i < this.at ? "Click: go back to just after this step" : "Click: redo up to this step";
      li.onclick = () => this.goto(i + 1);
      li.onmouseenter = () => void this.hoverStep(i);
      rows.push(li);
    });
    this.list.replaceChildren(...rows);
    this.list.querySelector(".current")?.scrollIntoView({ block: "nearest" });
  }

  private async hoverStep(i: number) {
    const token = ++this.hoverToken;
    const items = await this.host.items(i);
    if (token === this.hoverToken) this.host.hover(items.length ? items : null);
  }

  /** Move to a position; while a move is under way, only the latest target counts. */
  private async goto(at: number) {
    at = Math.max(0, Math.min(this.steps.length, at));
    this.target = at;
    if (this.moving) return;
    this.moving = true;
    try {
      while (this.target !== null && this.target !== this.at) {
        const want = this.target;
        // the step just crossed is what changed: show it
        const crossed = want > this.at ? want - 1 : want;
        this.at = await this.host.goto(want);
        const token = ++this.hoverToken;
        const items = crossed >= 0 && crossed < this.steps.length ? await this.host.items(crossed) : [];
        if (token === this.hoverToken) this.host.hover(items.length ? items : null);
      }
    } finally {
      this.target = null;
      this.moving = false;
    }
    const h = await this.host.steps();
    this.steps = h.steps;
    this.at = h.at;
    this.render();
    this.host.moved();
  }
}
