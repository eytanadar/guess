// Timeline bar: scrub or play through time (existence ranges or a numeric field
// such as year), with a sparkline of how much exists at each step. Scrubbing
// runs showTime(...) quietly; "Keep" records the current time as a command.

export interface TimelineInfo {
  source: string | null; min: number; max: number; steps: number[]; counts: number[]; kind?: string;
}

export interface TimelineHost {
  info(source: string): Promise<TimelineInfo>;
  /** numeric fields that can act as time */
  fields(): Promise<string[]>;
  quiet(code: string): Promise<boolean>;
  submit(code: string): void;
}

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text = "") => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
};

export class TimelineBar {
  private source = el("select");
  private windowIn = el("input") as HTMLInputElement;
  private slider = el("input") as HTMLInputElement;
  private play = el("button", "tl-play", "▶");
  private speed = el("select");
  private label = el("span", "tl-time");
  private spark = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  private info: TimelineInfo | null = null;
  private timer = 0;
  private busy = false;
  private pending: number | null = null;

  constructor(readonly root: HTMLElement, private host: TimelineHost) {
    root.classList.add("timeline");
    this.windowIn.type = "number";
    this.windowIn.min = "0";
    this.windowIn.placeholder = "all";
    this.windowIn.title = "Show only the last N time units (blank: everything up to now)";
    this.windowIn.className = "tl-window";
    this.slider.type = "range";
    this.slider.className = "tl-slider";
    this.slider.oninput = () => this.scrub(Number(this.slider.value));
    for (const [v, t] of [["1200", "slow"], ["500", "normal"], ["150", "fast"]]) {
      const o = el("option", "", t) as HTMLOptionElement;
      o.value = v;
      this.speed.append(o);
    }
    this.speed.value = "500";
    this.play.title = "Play / pause";
    this.play.onclick = () => this.toggle();
    this.source.onchange = () => void this.load();
    this.windowIn.onchange = () => this.scrub(Number(this.slider.value));
    const keep = el("button", "", "Keep");
    keep.title = "Record this moment as a command (showTime) in the console";
    keep.onclick = () => this.host.submit(this.code(this.time()));
    const all = el("button", "", "Show all");
    all.onclick = () => {
      this.stop();
      this.host.submit("showAll()");
    };
    this.spark.setAttribute("class", "tl-spark");
    this.spark.setAttribute("viewBox", "0 0 300 28");
    this.spark.setAttribute("preserveAspectRatio", "none");
    const track = el("div", "tl-track");
    track.append(this.spark, this.slider);
    const src = el("label", "tl-field");
    src.append("time from ", this.source);
    const win = el("label", "tl-field");
    win.append("window ", this.windowIn);
    root.append(this.play, track, this.label, src, win, this.speed, keep, all);
  }

  async show() {
    const fields = await this.host.fields();
    const cur = this.source.value;
    this.source.replaceChildren();
    const r = el("option", "", "ranges") as HTMLOptionElement;
    r.value = "";
    this.source.append(r);
    for (const f of fields) {
      const o = el("option", "", f) as HTMLOptionElement;
      o.value = f;
      this.source.append(o);
    }
    const guess = fields.find((f) => /year|time|date|period|step/i.test(f));
    this.source.value = cur || guess || "";
    await this.load();
  }

  hide() {
    this.stop();
  }

  private async load() {
    try {
      this.info = await this.host.info(this.source.value);
    } catch {
      this.info = null;
    }
    const info = this.info;
    if (!info || !info.steps.length) {
      this.label.textContent = this.source.value ? "no numbers" : "no ranges — addRange(...) or pick a field";
      this.slider.disabled = true;
      this.spark.replaceChildren();
      return;
    }
    this.slider.disabled = false;
    this.slider.min = "0";
    this.slider.max = String(info.steps.length - 1);
    this.slider.step = "1";
    this.slider.value = String(info.steps.length - 1);
    this.label.textContent = fmt(info.steps[info.steps.length - 1]);
    const top = Math.max(1, ...info.counts);
    const w = 300 / info.counts.length;
    this.spark.replaceChildren();
    info.counts.forEach((c, k) => {
      const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      const h = (c / top) * 26;
      r.setAttribute("x", String(k * w));
      r.setAttribute("width", String(Math.max(w - 0.6, 0.4)));
      r.setAttribute("y", String(28 - h));
      r.setAttribute("height", String(h));
      this.spark.append(r);
    });
  }

  private time() {
    return this.info?.steps[Number(this.slider.value)] ?? 0;
  }

  private code(t: number) {
    const f = this.source.value;
    const w = this.windowIn.value.trim();
    return f ? `showTime(${fmt(t)}, ${f}${w ? `, window=${Number(w)}` : ""})` : `showTime(${fmt(t)})`;
  }

  /** Show time step k; coalesces while a previous update is still running. */
  private scrub(k: number) {
    if (!this.info?.steps.length) return;
    this.label.textContent = fmt(this.info.steps[k]);
    if (this.busy) {
      this.pending = k;
      return;
    }
    this.busy = true;
    void this.host.quiet(this.code(this.info.steps[k])).finally(() => {
      this.busy = false;
      if (this.pending !== null) {
        const p = this.pending;
        this.pending = null;
        this.scrub(p);
      }
    });
  }

  private toggle() {
    if (this.timer) return this.stop();
    if (!this.info?.steps.length) return;
    if (Number(this.slider.value) >= this.info.steps.length - 1) this.slider.value = "0";
    this.play.textContent = "❚❚";
    const tick = () => {
      const k = Number(this.slider.value) + 1;
      if (!this.info || k >= this.info.steps.length) return this.stop();
      this.slider.value = String(k);
      this.scrub(k);
    };
    tick();
    this.timer = window.setInterval(tick, Number(this.speed.value));
  }

  private stop() {
    clearInterval(this.timer);
    this.timer = 0;
    this.play.textContent = "▶";
  }
}

function fmt(t: number) {
  return Number.isInteger(t) ? String(t) : String(Math.round(t * 1000) / 1000);
}
