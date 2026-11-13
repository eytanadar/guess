// Dock area: user widget panels (from the Python `ui` API) and linked charts.
import type { ChartMsg, PanelRec, WidgetRec } from "./protocol";
import type { VegaChart, VegaMsg } from "./vegachart";

export type Item = ["n" | "e", number];

export interface DockHost {
  /** A widget event (click/change/slide/enter) for Python. */
  event(target: string, name: string, value: unknown): void;
  /** Hovering a chart mark: highlight its elements (null = clear). */
  hover(items: Item[] | null, title: string, lines: string[], ev: MouseEvent | null): void;
  /** Clicking a mark selects its elements (shift adds). */
  click(items: Item[], ev: MouseEvent, expr?: string): void;
  /** Right-clicking a mark: the element menu (on its query, when the chart knows one). */
  context(items: Item[], ev: MouseEvent, expr: string | undefined, title: string): void;
  /** Pointing at a line chart: the values there, and (with a query) the elements
   *  it stands for; ev null = left the chart. click: true when clicked. */
  lineAt(expr: string | null, title: string, lines: string[], ev: MouseEvent | null, click?: boolean): void;
  /** Altair charts: the elements a query gives now */
  resolve?(expr: string): Promise<Item[]>;
  /** Altair charts: a selection (brush) changed; null when cleared */
  brush?(expr: string | null): void;
  /** dark theme now? (Altair charts pick their theme when drawn) */
  dark?(): boolean;
  /** make a chart live or not; resolves with its state */
  live?(id: string, on: boolean): Promise<boolean>;
  /** View(name): put one of the page's own views (table, style, …) into el */
  mountView?(name: string, el: HTMLElement): void;
}

export type Region = "bottom" | "right" | "left";

/** A little Markdown, safely: headings, **bold**, *italics*, `code`, lists,
 *  [links](https://…) and paragraphs. Everything else is text. */
export function markdown(text: string): DocumentFragment {
  const f = document.createDocumentFragment();
  const inline = (s: string, into: HTMLElement) => {
    for (const part of s.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)\s]+\))/)) {
      if (!part) continue;
      let m: RegExpExecArray | null;
      if (part.startsWith("`") && part.endsWith("`") && part.length > 1) {
        const c = document.createElement("code"); c.textContent = part.slice(1, -1); into.append(c);
      } else if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        const b = document.createElement("strong"); b.textContent = part.slice(2, -2); into.append(b);
      } else if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
        const i = document.createElement("em"); i.textContent = part.slice(1, -1); into.append(i);
      } else if ((m = /^\[([^\]]+)\]\(guess:([ne])(\d+)\)$/.exec(part))) {
        // linkTo(node): a chip for a node or edge; pointing at it highlights the element (see the markdown widget)
        const c = document.createElement("span");
        c.className = "md-el";
        c.dataset.k = m[2];
        c.dataset.id = m[3];
        c.textContent = m[1];
        into.append(c);
      } else if ((m = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part)) && /^https?:\/\//.test(m[2])) {
        const a = document.createElement("a"); a.textContent = m[1]; a.href = m[2]; a.target = "_blank"; a.rel = "noopener";
        into.append(a);
      } else into.append(part);
    }
  };
  let list: HTMLElement | null = null;
  // a paragraph's (or list item's) lines are joined first, so **bold** and
  // *italics* may wrap onto the next line
  let para: string[] = [];
  let item: { el: HTMLElement; text: string[] } | null = null;
  const flush = () => {
    if (para.length) {
      const p = document.createElement("p");
      inline(para.join(" "), p);
      f.append(p);
      para = [];
    }
    if (item) {
      inline(item.text.join(" "), item.el);
      item = null;
    }
  };
  let table: HTMLTableElement | null = null;
  const cells = (line: string) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
  for (const block of text.replace(/\r/g, "").split(/\n\s*\n/)) {
    list = null;
    table = null;
    for (const line of block.split("\n")) {
      // a table: rows of | a | b |, the second row a separator like |---|---|
      if (/^\s*\|.*\|\s*$/.test(line)) {
        flush();
        if (/^\s*\|[\s:|-]+\|\s*$/.test(line) && table) continue;
        const head = !table;
        if (!table) { table = document.createElement("table"); table.className = "md-table"; f.append(table); }
        const tr = document.createElement("tr");
        for (const c of cells(line)) {
          const td = document.createElement(head ? "th" : "td");
          inline(c, td);
          tr.append(td);
        }
        table.append(tr);
        continue;
      }
      table = null;
      const h = /^(#{1,4})\s+(.*)$/.exec(line);
      const li = /^\s*(?:[-*]|\d+\.)\s+(.*)$/.exec(line);
      if (h) {
        flush();
        const el = document.createElement(`h${Math.min(6, h[1].length + 2)}`);
        inline(h[2], el); f.append(el); list = null;
      } else if (li) {
        flush();
        if (!list) { list = document.createElement(/^\s*\d/.test(line) ? "ol" : "ul"); f.append(list); }
        const el = document.createElement("li"); list.append(el);
        item = { el, text: [li[1]] };
      } else if (line.trim()) {
        if (item) item.text.push(line.trim());       // a list item continued on the next line
        else para.push(line.trim());
      }
    }
    flush();
    f.append(document.createComment("block"));
  }
  return f;
}

const SVG = "http://www.w3.org/2000/svg";
const hex = (c: number) => "#" + c.toString(16).padStart(6, "0");

export class Dock {
  private panels = new Map<string, HTMLElement>();
  private widgets = new Map<string, HTMLElement>();
  /** chart id -> marks (each with the elements it stands for) */
  private marks = new Map<string, { el: SVGElement; keys: Set<string> }[]>();
  /** panels that want to know when they are closed (pinned cells, history) */
  private onClose = new Map<string, () => void>();
  /** Altair charts by panel id */
  private vegas = new Map<string, VegaChart>();

  constructor(private bottom: HTMLElement, private right: HTMLElement, private host: DockHost,
              private left: HTMLElement | null = null) {}

  // ---- panels ---------------------------------------------------------------------
  dockPanel(p: PanelRec) {
    const where: Region = p.props.position === "right" ? "right" : p.props.position === "left" && this.left ? "left" : "bottom";
    const body = this.frame(p.id, String(p.props.title ?? ""), where);
    const panel = this.panels.get(p.id)!;
    panel.classList.toggle("bare", Boolean(p.props.bare));
    // a panel moved to another region (ui.layout again)
    const region = this.regionEl(where);
    if (panel.parentElement !== region) region.append(panel);
    body.classList.toggle("vertical", Boolean(p.props.vertical));
    body.replaceChildren(...p.children.map((w) => this.widget(w)));
    this.layoutChanged();
  }

  /** A widget made outside a panel (toolbar, status bar). */
  makeWidget(w: { id: string; kind: string; props: Record<string, unknown>; children?: unknown[] }): HTMLElement {
    return this.widget(w as never);
  }

  private regionEl(where: Region): HTMLElement {
    return where === "right" ? this.right : where === "left" && this.left ? this.left : this.bottom;
  }

  close(id: string) {
    this.vegas.get(id)?.destroy();
    this.vegas.delete(id);
    this.panels.get(id)?.remove();
    this.panels.delete(id);
    this.marks.delete(id);
    this.layoutChanged();
    const done = this.onClose.get(id);
    this.onClose.delete(id);
    done?.();
  }

  /** The ● Live toggle in a chart's header (charts that know how they were made). */
  private liveButton(id: string, can: boolean, on: boolean) {
    const head = this.panels.get(id)?.querySelector("header");
    if (!head) return;
    let b = head.querySelector<HTMLButtonElement>(".panel-live");
    if (!can) {
      b?.remove();
      return;
    }
    if (!b) {
      b = document.createElement("button");
      b.className = "panel-live";
      b.textContent = "● Live";
      b.onclick = async () => {
        const want = b!.getAttribute("aria-pressed") !== "true";
        const state = this.host.live ? await this.host.live(id, want) : false;
        this.setLive(id, state);
      };
      head.querySelector(".panel-close")?.before(b);
    }
    this.setLive(id, on);
  }

  /** Show whether a chart is live (Python says when one stops). */
  setLive(id: string, on: boolean) {
    const b = this.panels.get(id)?.querySelector<HTMLButtonElement>(".panel-live");
    if (!b) return;
    b.setAttribute("aria-pressed", String(on));
    b.title = on ? "Live: recomputed after every change to the graph (click to stop)"
      : "Make this chart live: recompute it after every change to the graph";
  }

  /** A panel for the page's own use (a pinned cell, the history): its body. */
  pane(id: string, title: string, where: Region = "right", onClose?: () => void): HTMLElement {
    const body = this.frame(id, title, where);
    if (onClose) this.onClose.set(id, onClose);
    return body;
  }

  has(id: string) {
    return this.panels.has(id);
  }

  private frame(id: string, title: string, where: Region): HTMLElement {
    let panel = this.panels.get(id);
    if (!panel) {
      panel = document.createElement("section");
      panel.className = "panel";
      const head = document.createElement("header");
      const h = document.createElement("span");
      const x = document.createElement("button");
      x.className = "panel-close";
      x.textContent = "×";
      x.title = "Close";
      x.onclick = () => this.close(id);
      head.append(h, x);
      const body = document.createElement("div");
      body.className = "panel-body";
      panel.append(head, body);
      this.panels.set(id, panel);
      this.regionEl(where).append(panel);
    }
    panel.querySelector("header span")!.textContent = title;
    this.layoutChanged();
    return panel.querySelector(".panel-body") as HTMLElement;
  }

  private layoutChanged() {
    for (const r of [this.bottom, this.right, this.left]) {
      if (r) r.hidden = !r.querySelector(":scope > .panel");
    }
  }

  private widget(w: WidgetRec): HTMLElement {
    const p = w.props as Record<string, any>;
    let el: HTMLElement;
    const send = (name: string, value: unknown) => this.host.event(w.id, name, value);
    switch (w.kind) {
      case "label":
        el = document.createElement("span");
        el.className = "w-label";
        break;
      case "button": {
        const b = document.createElement("button");
        b.onclick = () => send("click", null);
        el = b;
        break;
      }
      case "slider": {
        el = document.createElement("label");
        el.className = "w-slider";
        const cap = document.createElement("span");
        const input = document.createElement("input");
        input.type = "range";
        const out = document.createElement("output");
        input.oninput = () => {
          out.textContent = input.value;
          send("slide", Number(input.value));
        };
        input.onchange = () => send("change", Number(input.value));
        el.append(cap, input, out);
        break;
      }
      case "checkbox": {
        el = document.createElement("label");
        el.className = "w-check";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.onchange = () => send("change", input.checked);
        el.append(input, document.createElement("span"));
        break;
      }
      case "dropdown": {
        el = document.createElement("label");
        el.className = "w-select";
        const sel = document.createElement("select");
        sel.onchange = () => send("change", sel.value);
        el.append(document.createElement("span"), sel);
        break;
      }
      case "textfield": {
        const input = document.createElement("input");
        input.type = "text";
        input.onkeydown = (ev) => {
          if (ev.key === "Enter") send("enter", input.value);
        };
        input.onchange = () => send("change", input.value);
        el = input;
        break;
      }
      case "markdown": {
        el = document.createElement("div");
        el.className = "w-markdown";
        // chips made by linkTo(): hover highlights their element in the graph, click selects it
        const item = (ev: Event): Item[] | null => {
          const t = (ev.target as HTMLElement).closest?.(".md-el") as HTMLElement | null;
          return t ? [[t.dataset.k as "n" | "e", Number(t.dataset.id)]] : null;
        };
        el.addEventListener("mouseover", (ev) => {
          const it = item(ev);
          if (it) this.host.hover(it, (ev.target as HTMLElement).textContent ?? "", [], ev as MouseEvent);
        });
        el.addEventListener("mouseout", (ev) => { if (item(ev)) this.host.hover(null, "", [], null); });
        el.addEventListener("click", (ev) => { const it = item(ev); if (it) this.host.click(it, ev as MouseEvent); });
        break;
      }
      case "chart":
        el = document.createElement("div");
        el.className = "w-chart";
        break;
      case "view":
        el = document.createElement("div");
        el.className = "w-view";
        queueMicrotask(() => this.host.mountView?.(String(p.name), el));
        break;
      case "row": case "column": {
        el = document.createElement("div");
        el.className = `w-${w.kind}`;
        el.append(...(w.children ?? []).map((c) => this.widget(c)));
        break;
      }
      case "group": {
        const d = document.createElement("details");
        d.className = "w-group";
        d.open = !p.collapsed;
        const sum = document.createElement("summary");
        const inner = document.createElement("div");
        inner.className = p.vertical === false ? "w-row" : "w-column";
        inner.append(...(w.children ?? []).map((c) => this.widget(c)));
        d.append(sum, inner);
        el = d;
        break;
      }
      case "tabs": {
        el = document.createElement("div");
        el.className = "w-tabs";
        const bar = document.createElement("div");
        bar.className = "w-tabbar";
        bar.setAttribute("role", "tablist");
        const pages = document.createElement("div");
        pages.className = "w-tabpages";
        const show = (title: string, tell: boolean) => {
          for (const b of bar.children) b.setAttribute("aria-selected", String((b as HTMLElement).dataset.title === title));
          for (const pg of pages.children) (pg as HTMLElement).hidden = (pg as HTMLElement).dataset.title !== title;
          if (tell) send("change", title);
        };
        for (const t of w.children ?? []) {
          const title = String(t.props.title ?? "");
          const b = document.createElement("button");
          b.setAttribute("role", "tab");
          b.textContent = title;
          b.dataset.title = title;
          b.onclick = () => show(title, true);
          bar.append(b);
          const page = this.widget(t);
          page.dataset.title = title;
          pages.append(page);
        }
        el.append(bar, pages);
        (el as any)._show = show;
        show(String(p.selected ?? w.children?.[0]?.props.title ?? ""), false);
        break;
      }
      case "tab": {
        el = document.createElement("div");
        el.className = p.vertical === false ? "w-tab w-row" : "w-tab w-column";
        el.setAttribute("role", "tabpanel");
        el.append(...(w.children ?? []).map((c) => this.widget(c)));
        break;
      }
      case "menuitem": {
        const b = document.createElement("button");
        b.onclick = () => send("click", null);
        el = b;
        break;
      }
      default:
        el = document.createElement("span");
    }
    el.dataset.kind = w.kind;
    this.widgets.set(w.id, el);
    this.update(w.id, p);
    return el;
  }

  update(id: string, props: Record<string, any>) {
    const el = this.widgets.get(id);
    if (!el) {
      const panel = this.panels.get(id);
      if (panel && "title" in props) panel.querySelector("header span")!.textContent = props.title;
      return;
    }
    const kind = el.dataset.kind;
    const input = el.querySelector("input, select") as HTMLInputElement | HTMLSelectElement | null;
    for (const [k, v] of Object.entries(props)) {
      if (k === "enabled") {
        (input ?? (el as HTMLButtonElement)).toggleAttribute("disabled", !v);
      } else if (kind === "label" && k === "text") {
        el.textContent = String(v);
      } else if (kind === "markdown" && k === "text") {
        el.replaceChildren(markdown(String(v)));
      } else if (kind === "chart" && k === "spec") {
        this.widgetChart(id, el, v as ChartMsg | VegaMsg | { type: "error"; text: string } | null);
      } else if (kind === "group" && k === "title") {
        el.querySelector("summary")!.textContent = String(v);
      } else if (kind === "tabs" && k === "selected" && v != null) {
        (el as any)._show?.(String(v), false);
      } else if (kind === "menuitem" && k === "text") {
        el.textContent = String(v);
      } else if (kind === "button" && k === "text") {
        el.textContent = String(v);
      } else if (kind === "slider") {
        const r = input as HTMLInputElement;
        if (k === "label") el.querySelector("span")!.textContent = String(v);
        else if (k === "value") {
          r.value = String(v);
          el.querySelector("output")!.textContent = String(v);
        } else if (k === "min" || k === "max" || k === "step") r[k] = String(v);
      } else if (kind === "checkbox") {
        if (k === "text") el.querySelector("span")!.textContent = String(v);
        if (k === "checked") (input as HTMLInputElement).checked = Boolean(v);
      } else if (kind === "dropdown") {
        const sel = input as HTMLSelectElement;
        if (k === "label") el.querySelector("span")!.textContent = String(v);
        if (k === "options") {
          sel.replaceChildren(...(v as string[]).map((o) => new Option(o, o)));
        }
        if (k === "value") sel.value = String(v);
      } else if (kind === "textfield") {
        const t = el as HTMLInputElement;
        if (k === "value") t.value = String(v);
        if (k === "placeholder") t.placeholder = String(v);
      }
    }
    // a slider's value may arrive before its min/max: re-apply
    if (kind === "slider" && "value" in props) (input as HTMLInputElement).value = String(props.value);
  }

  // ---- charts ----------------------------------------------------------------------
  chart(c: ChartMsg) {
    const body = this.frame(c.id, c.title, "right");
    this.liveButton(c.id, !!c.canLive, !!c.live);
    this.drawChart(c, body, c.id);
  }

  /** Draw a chart into body; key names its marks (the panel, or a Chart widget). */
  private drawChart(c: ChartMsg, body: HTMLElement, key: string) {
    body.classList.add("chart-body");
    if (c.kind === "matrix") {
      this.drawMatrix(c, body, key);
      return;
    }
    const W = 300, H = c.kind === "pie" ? 230 : 190;
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "chart");
    const marks: { el: SVGElement; keys: Set<string> }[] = [];
    const items = c.items;
    const add = (el: SVGElement, i: number) => {
      const it = items[i];
      el.setAttribute("fill", hex(it.color));
      el.classList.add("mark");
      const keys = new Set(it.ids.map(([k, id]) => k + id));
      marks.push({ el, keys });
      el.addEventListener("mouseenter", (ev) => {
        el.classList.add("hot");
        this.host.hover(it.ids as Item[], `${it.label}`, [`${c.ylabel}: ${fmt(it.value)}`], ev);
      });
      el.addEventListener("mousemove", (ev) => this.host.hover(it.ids as Item[], `${it.label}`, [`${c.ylabel}: ${fmt(it.value)}`], ev));
      el.addEventListener("mouseleave", () => {
        el.classList.remove("hot");
        this.host.hover(null, "", [], null);
      });
      if (it.ids.length) {
        el.addEventListener("click", (ev) => this.host.click(it.ids as Item[], ev, it.q));
        el.addEventListener("contextmenu", (ev) => {
          ev.preventDefault();
          this.host.context(it.ids as Item[], ev, it.q, it.label);
        });
      } else {
        el.style.cursor = "default";
      }
      svg.append(el);
    };
    if (c.kind === "line") {
      // the series key goes in rows above the plot, never over the data
      const keyPos: [number, number][] = [];
      const keyed = (c.series ?? []).filter((s) => !s.line && s.name);    // scatter reference lines have no key
      if (keyed.length > 1) {                                   // one series: the axis label says it
        let kx = 40, ky = 9;
        for (const s of keyed) {
          const w = s.name.length * 5.6 + 14;
          if (kx + w > W - 4 && kx > 40) { kx = 40; ky += 12; }
          keyPos.push([kx, ky]);
          kx += w;
        }
      }
      const keyRows = keyPos.length ? keyPos[keyPos.length - 1][1] / 12 + 0.25 : 0;
      const left = 40, bottom = 30, right = 8;
      const keyH = keyPos.length ? Math.round(6 + 12 * keyRows) : 0;
      const top = keyH + (c.ylabel ? 18 : 8);                 // room above the plot for the key, then the y label
      const pw = W - left - right, ph = H - top - bottom;
      const all = (c.series ?? []).flatMap((s) => s.points)
        .filter((p) => (!c.logX || p[0] > 0) && (!c.logY || p[1] > 0));
      const tx = c.logX ? Math.log10 : (v: number) => v, ty = c.logY ? Math.log10 : (v: number) => v;
      const txs = all.map((p) => tx(p[0])), tys = all.map((p) => ty(p[1]));
      let xmin = c.logX ? Math.min(...txs) : Math.min(0, ...txs), xmax = c.logX ? Math.max(...txs) : Math.max(1e-9, ...txs);
      let ymin = c.logY ? Math.min(...tys) : Math.min(0, ...tys), ymax = c.logY ? Math.max(...tys) : Math.max(1e-9, ...tys);
      // round outward to a 1-2-5 step, so the axis ends are round numbers
      const pad = (lo: number, hi: number): [number, number] => {
        const raw = ((hi - lo) || Math.abs(hi) || 1) / 5;
        const mag = Math.pow(10, Math.floor(Math.log10(raw)));
        const step = [1, 2, 5, 10].map((m) => m * mag).find((v) => v >= raw) ?? 10 * mag;
        const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step;
        const r = (v: number) => +v.toPrecision(12);
        return [r(a), r(b > a ? b : a + step)];
      };
      if (c.scatter && all.length) {
        // scatter plots fit the data rather than always including zero
        if (!c.logX) [xmin, xmax] = pad(Math.min(...txs), Math.max(...txs));
        if (!c.logY) [ymin, ymax] = pad(Math.min(...tys), Math.max(...tys));
      } else if (all.length && !c.logY && ymax > ymin) {
        [ymin, ymax] = pad(ymin, ymax);                   // line charts: a round number at the top
      }
      if (!all.length) { xmin = 0; xmax = 1; ymin = 0; ymax = 1; }
      if (c.xRange) [xmin, xmax] = c.logX ? [Math.log10(c.xRange[0]), Math.log10(c.xRange[1])] : c.xRange;
      if (c.yRange) [ymin, ymax] = c.logY ? [Math.log10(c.yRange[0]), Math.log10(c.yRange[1])] : c.yRange;
      // a single point (or all at one value): give the axis a sensible span
      if (!c.logX && xmax - xmin < 1e-6) xmax = xmin + (Math.abs(xmin) || 1);
      if (!c.logY && ymax - ymin < 1e-6) ymax = ymin + (Math.abs(ymin) || 1);
      if (c.logX && xmax - xmin < 1) { xmin = Math.floor(xmin); xmax = Math.max(xmax, xmin + 1); }
      if (c.logY && ymax - ymin < 1) { ymin = Math.floor(ymin); ymax = Math.max(ymax, ymin + 1); }
      // X, Y take data values; XT, YT values already on the axis' scale
      const XT = (v: number) => left + (pw * (v - xmin)) / (xmax - xmin || 1);
      const YT = (v: number) => top + ph * (1 - (v - ymin) / (ymax - ymin || 1));
      const X = (v: number) => XT(tx(v)), Y = (v: number) => YT(ty(v));
      // fixed ranges (xrange=/yrange=) can leave points outside: clip them to the plot
      let clip = "";
      if (c.xRange || c.yRange) {
        clip = `clip${Math.random().toString(36).slice(2, 9)}`;
        const cp = document.createElementNS(SVG, "clipPath");
        cp.setAttribute("id", clip);
        const cr = document.createElementNS(SVG, "rect");
        cr.setAttribute("x", String(left - 4)); cr.setAttribute("y", String(top - 4));
        cr.setAttribute("width", String(pw + 8)); cr.setAttribute("height", String(ph + 8));
        cp.append(cr);
        svg.append(cp);
      }
      const clipped = (el: SVGElement) => { if (clip) el.setAttribute("clip-path", `url(#${clip})`); return el; };
      const axis = document.createElementNS(SVG, "path");
      axis.setAttribute("d", `M${left},${top} V${top + ph} H${W - right}`);
      axis.setAttribute("class", "axis");
      svg.append(axis);
      /** tick values (on the axis' own scale): the ends, or the powers of ten between them */
      const ticks = (lo: number, hi: number, log: boolean | undefined) => {
        if (!log) return [lo, hi];
        // powers of ten; with fewer than two of them, 1-2-5 steps
        for (const ms of [[1], [1, 2, 5], [1, 2, 3, 5, 7]]) {
          const out: number[] = [];
          for (let k = Math.floor(lo) - 1; k <= Math.ceil(hi); k++) {
            for (const m of ms) {
              const v = k + Math.log10(m);
              if (v >= lo - 1e-9 && v <= hi + 1e-9) out.push(v);
            }
          }
          if (out.length >= 2) return out.length > 7 ? out.filter((_, i) => i % Math.ceil(out.length / 7) === 0) : out;
        }
        return [lo, hi];
      };
      const label = (v: number, log: boolean | undefined) => {
        if (!log) return fmt(v);
        const x = +Math.pow(10, v).toPrecision(2);
        return x >= 1e4 || (x < 1e-3 && x > 0) ? x.toExponential(0) : String(x);
      };
      for (const v of ticks(ymin, ymax, c.logY)) {
        const t = document.createElementNS(SVG, "text");
        t.setAttribute("x", String(left - 4));
        t.setAttribute("y", String(YT(v) + 3));
        t.setAttribute("class", "tick");
        t.textContent = label(v, c.logY);
        svg.append(t);
      }
      for (const v of ticks(xmin, xmax, c.logX)) {
        const t = document.createElementNS(SVG, "text");
        t.setAttribute("x", String(XT(v)));
        if (XT(v) > W - right - 12) t.style.textAnchor = "end";      // the last label stays inside the chart
        t.setAttribute("y", String(top + ph + 11));
        t.setAttribute("class", "xtick");
        t.textContent = label(v, c.logX);
        svg.append(t);
      }
      if (c.logX || c.logY) {
        const note = document.createElementNS(SVG, "text");
        note.setAttribute("x", "2");
        note.setAttribute("y", String(H - 2));
        note.setAttribute("class", "tick");
        note.style.textAnchor = "start";
        note.textContent = c.logX && c.logY ? "log–log" : c.logX ? "log x" : "log y";
        svg.append(note);
      }
      if (c.scatter) {
        // one dot per element: pointing highlights it, clicking selects it
        for (const s of c.series ?? []) {
          if (s.line) {
            const ln = document.createElementNS(SVG, "polyline");
            ln.setAttribute("points", s.points.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join(" "));
            ln.setAttribute("fill", "none");
            ln.setAttribute("stroke", hex(s.color));
            ln.setAttribute("stroke-dasharray", "4 3");
            ln.setAttribute("stroke-width", "1.2");
            svg.append(clipped(ln));
            continue;
          }
          const r = s.points.length > 400 ? 1.8 : s.points.length > 100 ? 2.5 : 3.2;
          s.points.forEach(([x, y], k) => {
            if ((c.logX && x <= 0) || (c.logY && y <= 0)) return;
            const dot = document.createElementNS(SVG, "circle");
            dot.setAttribute("cx", X(x).toFixed(1));
            dot.setAttribute("cy", Y(y).toFixed(1));
            dot.setAttribute("r", String(r));
            dot.setAttribute("fill", hex(s.colors?.[k] ?? s.color));
            dot.setAttribute("fill-opacity", "0.8");
            dot.setAttribute("stroke", "rgba(0,0,0,.35)");
            dot.setAttribute("stroke-width", "0.5");
            dot.classList.add("mark");
            const ids = (s.ids?.[k] ?? []) as Item[];
            const title = s.labels?.[k] ?? s.name;
            const lines = [`${c.xlabel}: ${fmt(x)}`, `${c.ylabel}: ${fmt(y)}`];
            dot.addEventListener("mouseenter", (ev) => {
              dot.classList.add("hot");
              dot.setAttribute("r", String(r * 1.8));
              this.host.hover(ids, title, lines, ev);
            });
            dot.addEventListener("mouseleave", () => {
              dot.classList.remove("hot");
              dot.setAttribute("r", String(r));
              this.host.hover(null, "", [], null);
            });
            if (ids.length) dot.addEventListener("click", (ev) => this.host.click(ids, ev));
            if (ids.length) marks.push({ el: dot, keys: new Set(ids.map(([kk, id]) => kk + id)) });
            svg.append(clipped(dot));
          });
        }
      }
      if (c.ylabel) {
        const yl = document.createElementNS(SVG, "text");
        yl.setAttribute("x", "2");
        yl.setAttribute("y", String(keyH + 11));
        yl.setAttribute("class", "tick");
        yl.style.textAnchor = "start";
        yl.textContent = c.ylabel;
        svg.append(yl);
      }
      (c.scatter ? [] : c.series ?? []).forEach((s, i) => {
        const pts = s.points.filter((p) => (!c.logX || p[0] > 0) && (!c.logY || p[1] > 0));
        const line = document.createElementNS(SVG, "polyline");
        line.setAttribute("points", pts.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join(" "));
        line.setAttribute("fill", "none");
        line.setAttribute("stroke", hex(s.color));
        line.setAttribute("stroke-width", c.dots && !s.dash ? "1" : "1.8");
        if (c.dots && !s.dash) line.setAttribute("stroke-opacity", "0.5");
        if (s.dash) line.setAttribute("stroke-dasharray", "5 3");
        svg.append(clipped(line));
        if (c.dots && !s.dash) {
          for (const [x, y] of pts) {
            const dot = document.createElementNS(SVG, "circle");
            dot.setAttribute("cx", X(x).toFixed(1));
            dot.setAttribute("cy", Y(y).toFixed(1));
            dot.setAttribute("r", "2.2");
            dot.setAttribute("fill", hex(s.color));
            svg.append(clipped(dot));
          }
        }
      });
      keyed.forEach((s, i) => {
        if (!keyPos[i]) return;
        const [kx, ky] = keyPos[i];
        const sw = document.createElementNS(SVG, "rect");
        sw.setAttribute("x", String(kx));
        sw.setAttribute("y", String(ky - 6));
        sw.setAttribute("width", "8");
        sw.setAttribute("height", "3");
        sw.setAttribute("fill", hex(s.color));
        svg.append(sw);
        const key = document.createElementNS(SVG, "text");
        key.setAttribute("x", String(kx + 11));
        key.setAttribute("y", String(ky));
        key.setAttribute("class", "tick");
        key.style.textAnchor = "start";
        key.setAttribute("fill", hex(s.color));
        key.textContent = s.name;
        svg.append(key);
      });
      const xl = document.createElementNS(SVG, "text");
      xl.setAttribute("x", String(left + pw / 2));
      xl.setAttribute("y", String(H - 2));
      xl.setAttribute("class", "axis-label");
      xl.textContent = c.xlabel;
      svg.append(xl);
      // pointing: a guide at the nearest x, every series' value there, and
      // for charts that know their elements (spread), those elements in the graph
      const xs = [...new Set(all.map((p) => p[0]))].sort((a, b) => a - b);
      if (xs.length && !c.scatter) {
        const guide = document.createElementNS(SVG, "line");
        guide.setAttribute("class", "guide");
        guide.setAttribute("y1", String(top));
        guide.setAttribute("y2", String(top + ph));
        guide.style.display = "none";
        svg.append(guide);
        const hit = document.createElementNS(SVG, "rect");
        hit.setAttribute("x", String(left));
        hit.setAttribute("y", String(top));
        hit.setAttribute("width", String(pw));
        hit.setAttribute("height", String(ph));
        hit.setAttribute("class", "line-hit");
        svg.append(hit);
        const at = (ev: MouseEvent) => {
          const r = svg.getBoundingClientRect();
          const sx = ((ev.clientX - r.left) / r.width) * W;
          const v = xmin + ((sx - left) / pw) * (xmax - xmin);
          let best = xs[0];
          for (const x of xs) if (Math.abs(tx(x) - v) < Math.abs(tx(best) - v)) best = x;
          guide.setAttribute("x1", String(X(best)));
          guide.setAttribute("x2", String(X(best)));
          guide.style.display = "";
          const lines = (c.series ?? []).map((s) => {
            const p = s.points.find((q) => q[0] === best);
            return `${s.name}: ${p ? fmt(p[1]) : "–"}`;
          });
          return { x: best, title: `${c.xlabel} ${fmt(best)}`, lines };
        };
        const expr = (x: number) => (c.xq ? c.xq.split("{x}").join(String(x)) : null);
        hit.addEventListener("mousemove", (ev) => {
          const a = at(ev);
          this.host.lineAt(expr(a.x), a.title, a.lines, ev);
        });
        hit.addEventListener("mouseleave", () => {
          guide.style.display = "none";
          this.host.lineAt(null, "", [], null);
        });
        hit.addEventListener("click", (ev) => {
          const a = at(ev);
          if (c.xq) this.host.lineAt(expr(a.x), a.title, a.lines, ev, true);
        });
      }
    } else if (c.kind === "pie") {
      const total = items.reduce((s, it) => s + Math.max(0, it.value), 0) || 1;
      const cx = W / 2, cy = H / 2, r = H / 2 - 12;
      let a0 = -Math.PI / 2;
      items.forEach((it, i) => {
        const a1 = a0 + (2 * Math.PI * Math.max(0, it.value)) / total;
        const path = document.createElementNS(SVG, "path");
        const mid = (a0 + a1) / 2;
        path.setAttribute("d", arc(cx, cy, r, a0, a1));
        path.style.setProperty("--dx", `${Math.cos(mid) * 8}px`);
        path.style.setProperty("--dy", `${Math.sin(mid) * 8}px`);
        path.setAttribute("stroke", "#fff");
        add(path, i);
        if (a1 - a0 > 0.25) {
          const t = document.createElementNS(SVG, "text");
          t.setAttribute("x", String(cx + Math.cos(mid) * r * 0.65));
          t.setAttribute("y", String(cy + Math.sin(mid) * r * 0.65));
          t.setAttribute("class", "pie-label");
          t.textContent = it.label;
          svg.append(t);
        }
        a0 = a1;
      });
    } else {
      const left = 34, bottom = c.kind === "distrib" ? 16 : 34, top = 8, right = 6;
      const pos = items.map((it) => it.value).filter((v) => v > 0);
      const maxV = c.logY ? Math.max(1, ...pos) : Math.max(1e-9, ...items.map((it) => it.value));
      // log axis: bars start a little below the smallest value so it still shows
      const minV = c.logY ? Math.min(...pos, maxV) / 2 : Math.min(0, ...items.map((it) => it.value));
      const pw = W - left - right, ph = H - top - bottom;
      const y = c.logY
        ? (v: number) => top + ph * (1 - (Math.log10(Math.max(v, minV)) - Math.log10(minV)) / (Math.log10(maxV) - Math.log10(minV) || 1))
        : (v: number) => top + ph * (1 - (v - minV) / (maxV - minV || 1));
      const bw = pw / Math.max(items.length, 1);
      const axis = document.createElementNS(SVG, "path");
      axis.setAttribute("d", `M${left},${top} V${top + ph} H${W - right}`);
      axis.setAttribute("class", "axis");
      svg.append(axis);
      for (const v of c.logY ? [Math.min(...pos, maxV), maxV] : [minV, maxV]) {
        const t = document.createElementNS(SVG, "text");
        t.setAttribute("x", String(left - 4));
        t.setAttribute("y", String(y(v) + 3));
        t.setAttribute("class", "tick");
        t.textContent = fmt(v);
        svg.append(t);
      }
      if (c.logY) {
        const note = document.createElementNS(SVG, "text");
        note.setAttribute("x", String(W - right));
        note.setAttribute("y", String(top + 9));
        note.setAttribute("class", "tick");
        note.textContent = "log scale";
        svg.append(note);
      }
      items.forEach((it, i) => {
        const rect = document.createElementNS(SVG, "rect");
        const y0 = c.logY ? top + ph : y(Math.max(0, minV)), y1 = c.logY && it.value <= 0 ? top + ph : y(it.value);
        rect.setAttribute("x", String(left + i * bw + (bw > 3 ? bw * 0.1 : 0)));
        rect.setAttribute("width", String(Math.max(bw > 3 ? bw * 0.8 : bw, 0.5)));
        rect.setAttribute("y", String(Math.min(y0, y1)));
        rect.setAttribute("height", String(Math.max(Math.abs(y0 - y1), 0.5)));
        add(rect, i);
        if (c.kind === "bar" && items.length <= 24) {
          const t = document.createElementNS(SVG, "text");
          const x = left + (i + 0.5) * bw;
          t.setAttribute("transform", `translate(${x},${top + ph + 4}) rotate(${items.length > 8 ? 40 : 0})`);
          t.setAttribute("class", items.length > 8 ? "xtick slanted" : "xtick");
          t.textContent = it.label.length > 12 ? it.label.slice(0, 11) + "…" : it.label;
          svg.append(t);
        }
      });
      const xl = document.createElementNS(SVG, "text");
      xl.setAttribute("x", String(left + pw / 2));
      xl.setAttribute("y", String(H - 2));
      xl.setAttribute("class", "axis-label");
      xl.textContent = c.kind === "distrib" ? c.xlabel : "";
      svg.append(xl);
      this.brush(svg, W, left, top, pw, ph, bw, items, c);
    }
    body.replaceChildren(svg);
    this.marks.set(key, marks);
  }

  /** showMatrix: one cell per edge (both ways when undirected), rows and columns in the given
   *  order, lines between groups; hovering a cell highlights its edge and nodes. */
  private drawMatrix(c: ChartMsg, body: HTMLElement, key: string) {
    const rl = c.labels ?? [], rids = c.ids ?? [], cells = c.cells ?? [];
    const cl = c.clabels ?? rl, cids = c.cids ?? rids;
    const nr = Math.max(rl.length, 1), nc = Math.max(cl.length, 1);
    const named = Math.max(nr, nc) <= 40;
    const pad = named ? 46 : 6, W = 300;
    const step = (W - pad - 10) / Math.max(nr, nc);
    const wid = step * nc, hei = step * nr;
    const H = pad + hei + 4;
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "chart matrix");
    const frame = document.createElementNS(SVG, "rect");
    frame.setAttribute("x", String(pad)); frame.setAttribute("y", String(pad));
    frame.setAttribute("width", String(wid)); frame.setAttribute("height", String(hei));
    frame.setAttribute("class", "matrix-frame");
    svg.append(frame);
    const line = (x1: number, y1: number, x2: number, y2: number) => {
      const l = document.createElementNS(SVG, "line");
      l.setAttribute("x1", String(x1)); l.setAttribute("y1", String(y1));
      l.setAttribute("x2", String(x2)); l.setAttribute("y2", String(y2));
      l.setAttribute("class", "matrix-group");
      svg.append(l);
    };
    const rg = c.groups, cg = c.cgroups ?? (c.clabels ? undefined : c.groups);
    if (rg) for (let i = 1; i < nr; i++) if (rg[i] !== rg[i - 1]) line(pad, pad + i * step, pad + wid, pad + i * step);
    if (cg) for (let j = 1; j < nc; j++) if (cg[j] !== cg[j - 1]) line(pad + j * step, pad, pad + j * step, pad + hei);
    const short = (t: string) => (t.length > 8 ? t.slice(0, 7) + "…" : t);
    // name labels as big as the rows allow (readable on small matrices)
    const labelPx = Math.max(5, Math.min(11, step * 0.55));
    if (named) {
      rl.forEach((t, i) => {
        const row = document.createElementNS(SVG, "text");
        row.setAttribute("x", String(pad - 3)); row.setAttribute("y", String(pad + (i + 0.5) * step));
        row.setAttribute("class", "tick matrix-row"); row.style.fontSize = `${labelPx}px`;
        row.textContent = short(t);
        svg.append(row);
      });
      cl.forEach((t, j) => {
        const col = document.createElementNS(SVG, "text");
        col.setAttribute("transform", `translate(${pad + (j + 0.5) * step},${pad - 3}) rotate(-90)`);
        col.setAttribute("class", "xtick matrix-col"); col.style.fontSize = `${labelPx}px`;
        col.textContent = short(t);
        svg.append(col);
      });
    }
    const max = Math.max(1e-9, ...cells.map((x) => Math.abs(x[2])));
    const shaded = c.weighted || cells.some((x) => x[2] !== 1);
    const numbers = !!c.numbers && Math.max(nr, nc) <= 30;
    const fontPx = Math.max(4, Math.min(11, step * 0.5));

    const marks: { el: SVGElement; keys: Set<string> }[] = [];
    for (const [r, k, v, eid] of cells) {

      const rect = document.createElementNS(SVG, "rect");
      rect.setAttribute("x", String(pad + k * step)); rect.setAttribute("y", String(pad + r * step));
      rect.setAttribute("width", String(Math.max(step, 0.6))); rect.setAttribute("height", String(Math.max(step, 0.6)));
      rect.setAttribute("class", "mark matrix-cell");
      rect.setAttribute("fill-opacity", String(shaded ? 0.25 + (0.75 * Math.abs(v)) / max : 1));
      const items: Item[] = [["e", eid], ["n", rids[r]], ["n", cids[k]]];
      const title = `${rl[r]} → ${cl[k]}`;
      const lines = [`value: ${fmt(v)}`];
      rect.addEventListener("mouseenter", (ev) => { rect.classList.add("hot"); this.host.hover(items, title, lines, ev); });
      rect.addEventListener("mousemove", (ev) => this.host.hover(items, title, lines, ev));
      rect.addEventListener("mouseleave", () => { rect.classList.remove("hot"); this.host.hover(null, "", [], null); });
      rect.addEventListener("click", (ev) => this.host.click(items, ev));
      rect.addEventListener("contextmenu", (ev) => { ev.preventDefault(); this.host.context(items, ev, undefined, title); });
      marks.push({ el: rect, keys: new Set([`e${eid}`]) });
      svg.append(rect);
    }
    if (numbers) {
      const valueAt = new Map(cells.map(([r, k, v]) => [`${r},${k}`, v]));
      for (let r = 0; r < nr; r++) {
        for (let k = 0; k < nc; k++) {
          const v = valueAt.get(`${r},${k}`) ?? 0;
          const t = document.createElementNS(SVG, "text");
          t.setAttribute("x", String(pad + (k + 0.5) * step));
          t.setAttribute("y", String(pad + (r + 0.5) * step));
          t.setAttribute("class", v ? "matrix-num on" : "matrix-num");
          t.style.fontSize = `${fontPx}px`;
          t.textContent = fmt(v);
          svg.append(t);
        }
      }
    }
    body.replaceChildren(svg);
    this.marks.set(key, marks);
  }

  /** Drag across bars to pick a range of them: while dragging, the graph shows
   *  their elements; letting go selects them (shift adds). The query is the
   *  bars' queries joined with |, when every bar has one. */
  private brush(svg: SVGSVGElement, W: number, left: number, top: number, pw: number, ph: number, bw: number,
                items: ChartMsg["items"], c: ChartMsg) {
    if (items.length < 2 || !items.some((it) => it.ids.length)) return;
    const band = document.createElementNS(SVG, "rect");
    band.setAttribute("class", "brush");
    band.setAttribute("y", String(top));
    band.setAttribute("height", String(ph));
    band.style.display = "none";
    svg.append(band);
    const toX = (ev: MouseEvent) => {
      const r = svg.getBoundingClientRect();
      return ((ev.clientX - r.left) / r.width) * W;
    };
    const bar = (x: number) => Math.max(0, Math.min(items.length - 1, Math.floor((x - left) / bw)));
    let start: number | null = null, dragging = false, swallowClick = false;
    const range = (ev: MouseEvent) => {
      const a = bar(start!), b = bar(toX(ev));
      return [Math.min(a, b), Math.max(a, b)] as const;
    };
    const picked = (lo: number, hi: number) => {
      const chosen = items.slice(lo, hi + 1);
      const ids = chosen.flatMap((it) => it.ids) as Item[];
      const qs = chosen.filter((it) => it.ids.length).map((it) => it.q);
      const expr = qs.length && qs.every(Boolean) ? (qs.length === 1 ? qs[0] : qs.map((q) => `(${q})`).join(" | ")) : undefined;
      const total = chosen.reduce((t, it) => t + it.value, 0);
      const title = hi > lo ? `${chosen[0].label} … ${chosen[chosen.length - 1].label}` : chosen[0].label;
      return { ids, expr, title, lines: [`${hi - lo + 1} bars · ${c.ylabel}: ${fmt(total)}`] };
    };
    const move = (ev: MouseEvent) => {
      if (start === null) return;
      if (!dragging && Math.abs(toX(ev) - start) < 4) return;
      dragging = true;
      svg.classList.add("brushing");
      const [lo, hi] = range(ev);
      band.setAttribute("x", String(left + lo * bw));
      band.setAttribute("width", String((hi - lo + 1) * bw));
      band.style.display = "";
      const p = picked(lo, hi);
      this.host.hover(p.ids, p.title, p.lines, ev);
    };
    const up = (ev: MouseEvent) => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      if (start === null) return;
      const was = dragging;
      dragging = false;
      svg.classList.remove("brushing");
      band.style.display = "none";
      if (was) {
        const [lo, hi] = range(ev);
        const p = picked(lo, hi);
        this.host.hover(null, "", [], null);
        if (p.ids.length) this.host.click(p.ids, ev, p.expr);
        swallowClick = true;          // the click that follows this mouseup isn't a bar click
      }
      start = null;
    };
    svg.addEventListener("mousedown", (ev) => {
      if (ev.button !== 0) return;
      const x = toX(ev);
      if (x < left || x > left + pw) return;
      start = x;
      dragging = false;
      swallowClick = false;
      ev.preventDefault();
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
    });
    svg.addEventListener("click", (ev) => {
      if (!swallowClick) return;
      swallowClick = false;
      ev.stopPropagation();
    }, true);
  }

  /** An Altair chart: drawn by Vega (loaded on first use); the same id redraws in place. */
  async vega(m: VegaMsg) {
    const body = this.frame(m.id, m.title, "right");
    this.liveButton(m.id, !!m.canLive, !!m.live);
    await this.drawVega(m, body, m.id);
  }

  private async drawVega(m: VegaMsg, body: HTMLElement, key: string) {
    body.classList.add("vega-body");
    this.vegas.get(key)?.destroy();
    this.vegas.delete(key);
    const holder = document.createElement("div");
    body.replaceChildren(holder);
    const h = this.host;
    const resolve = (expr: string) => (h.resolve ? h.resolve(expr) : Promise.resolve([] as Item[]));
    try {
      const { renderVega } = await import("./vegachart");
      const chart = await renderVega(holder, m, {
        hover: (items, _expr, title, lines, ev) => h.hover(items && items.length ? items : null, title, lines, ev),
        click: (items, expr, ev) => {
          if (items.length) h.click(items, ev, expr ?? undefined);
        },
        context: (items, expr, title, ev) => h.context(items, ev, expr ?? undefined, title),
        brush: (expr) => h.brush?.(expr),
        resolve,
      }, h.dark?.() ?? false);
      if (body.firstChild === holder) this.vegas.set(key, chart);
      else chart.destroy();
    } catch (e) {
      const err = document.createElement("div");
      err.className = "vega-error";
      err.textContent = `Couldn't draw this chart: ${String(e).split("\n")[0]}`;
      body.replaceChildren(err);
    }
  }

  /** A Chart widget's chart: the title above, drawn like a dock chart. */
  private widgetChart(id: string, el: HTMLElement, spec: ChartMsg | VegaMsg | { type: "error"; text: string } | null) {
    this.vegas.get(id)?.destroy();
    this.vegas.delete(id);
    this.marks.delete(id);
    el.replaceChildren();
    if (!spec) {
      // nothing to show yet (the function made no chart): take no room
      el.classList.add("w-chart-empty");
      return;
    }
    el.classList.remove("w-chart-empty");
    const type = (spec as { type?: string }).type;
    if (type === "error") {
      el.textContent = `⚠ ${(spec as { text: string }).text}`;
      el.classList.add("w-chart-empty");
      return;
    }
    const title = document.createElement("div");
    title.className = "w-chart-title";
    title.textContent = (spec as ChartMsg).title;
    const body = document.createElement("div");
    el.append(title, body);
    if (type === "vega") void this.drawVega(spec as VegaMsg, body, id);
    else this.drawChart(spec as ChartMsg, body, id);
  }

  /** Highlight marks whose elements intersect the given ones (from graph/console hover). */
  highlight(items: Item[] | null) {
    for (const v of this.vegas.values()) v.highlight(items);
    const keys = new Set((items ?? []).map(([k, id]) => k + id));
    for (const marks of this.marks.values()) {
      for (const m of marks) {
        let hit = false;
        if (keys.size) for (const k of keys) if (m.keys.has(k)) { hit = true; break; }
        m.el.classList.toggle("linked", hit);
      }
    }
  }
}

function arc(cx: number, cy: number, r: number, a0: number, a1: number) {
  if (a1 - a0 >= 2 * Math.PI - 1e-6) {
    return `M${cx - r},${cy} a${r},${r} 0 1,0 ${2 * r},0 a${r},${r} 0 1,0 ${-2 * r},0`;
  }
  const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
  const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
  return `M${cx},${cy} L${x0},${y0} A${r},${r} 0 ${a1 - a0 > Math.PI ? 1 : 0},1 ${x1},${y1} Z`;
}

function fmt(v: number) {
  return Number.isInteger(v) ? String(v) : String(+v.toPrecision(4));   // 0.05, not 0.05000
}
