// Dock area: user widget panels (from the Python `ui` API) and linked charts.
import type { ChartMsg, PanelRec, WidgetRec } from "./protocol";

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
}

const SVG = "http://www.w3.org/2000/svg";
const hex = (c: number) => "#" + c.toString(16).padStart(6, "0");

export class Dock {
  private panels = new Map<string, HTMLElement>();
  private widgets = new Map<string, HTMLElement>();
  /** chart id -> marks (each with the elements it stands for) */
  private marks = new Map<string, { el: SVGElement; keys: Set<string> }[]>();

  constructor(private bottom: HTMLElement, private right: HTMLElement, private host: DockHost) {}

  // ---- panels ---------------------------------------------------------------------
  dockPanel(p: PanelRec) {
    const body = this.frame(p.id, String(p.props.title ?? ""), p.props.position === "right" ? "right" : "bottom");
    body.classList.toggle("vertical", Boolean(p.props.vertical));
    body.replaceChildren(...p.children.map((w) => this.widget(w)));
  }

  close(id: string) {
    this.panels.get(id)?.remove();
    this.panels.delete(id);
    this.marks.delete(id);
    this.layoutChanged();
  }

  private frame(id: string, title: string, where: "bottom" | "right"): HTMLElement {
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
      (where === "right" ? this.right : this.bottom).append(panel);
    }
    panel.querySelector("header span")!.textContent = title;
    this.layoutChanged();
    return panel.querySelector(".panel-body") as HTMLElement;
  }

  private layoutChanged() {
    this.bottom.hidden = !this.bottom.childElementCount;
    this.right.hidden = !this.right.childElementCount;
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
    body.classList.add("chart-body");
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
      const left = 34, bottom = 30, top = 8, right = 8;
      const pw = W - left - right, ph = H - top - bottom;
      const all = (c.series ?? []).flatMap((s) => s.points);
      const xmin = Math.min(0, ...all.map((p) => p[0])), xmax = Math.max(1e-9, ...all.map((p) => p[0]));
      const ymin = Math.min(0, ...all.map((p) => p[1])), ymax = Math.max(1e-9, ...all.map((p) => p[1]));
      const X = (v: number) => left + (pw * (v - xmin)) / (xmax - xmin || 1);
      const Y = (v: number) => top + ph * (1 - (v - ymin) / (ymax - ymin || 1));
      const axis = document.createElementNS(SVG, "path");
      axis.setAttribute("d", `M${left},${top} V${top + ph} H${W - right}`);
      axis.setAttribute("class", "axis");
      svg.append(axis);
      for (const [v, isX] of [[ymin, false], [ymax, false], [xmin, true], [xmax, true]] as [number, boolean][]) {
        const t = document.createElementNS(SVG, "text");
        t.setAttribute("x", String(isX ? X(v) : left - 4));
        t.setAttribute("y", String(isX ? top + ph + 11 : Y(v) + 3));
        t.setAttribute("class", isX ? "xtick" : "tick");
        t.textContent = fmt(v);
        svg.append(t);
      }
      (c.series ?? []).forEach((s, i) => {
        const line = document.createElementNS(SVG, "polyline");
        line.setAttribute("points", s.points.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join(" "));
        line.setAttribute("fill", "none");
        line.setAttribute("stroke", hex(s.color));
        line.setAttribute("stroke-width", "1.8");
        svg.append(line);
        const key = document.createElementNS(SVG, "text");
        key.setAttribute("x", String(W - right - 2));
        key.setAttribute("y", String(top + 10 + i * 12));
        key.setAttribute("class", "tick");
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
      const maxV = Math.max(1e-9, ...items.map((it) => it.value));
      const minV = Math.min(0, ...items.map((it) => it.value));
      const pw = W - left - right, ph = H - top - bottom;
      const y = (v: number) => top + ph * (1 - (v - minV) / (maxV - minV || 1));
      const bw = pw / Math.max(items.length, 1);
      const axis = document.createElementNS(SVG, "path");
      axis.setAttribute("d", `M${left},${top} V${top + ph} H${W - right}`);
      axis.setAttribute("class", "axis");
      svg.append(axis);
      for (const v of [minV, maxV]) {
        const t = document.createElementNS(SVG, "text");
        t.setAttribute("x", String(left - 4));
        t.setAttribute("y", String(y(v) + 3));
        t.setAttribute("class", "tick");
        t.textContent = fmt(v);
        svg.append(t);
      }
      items.forEach((it, i) => {
        const rect = document.createElementNS(SVG, "rect");
        const y0 = y(Math.max(0, minV)), y1 = y(it.value);
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
    }
    body.replaceChildren(svg);
    this.marks.set(c.id, marks);
  }

  /** Highlight marks whose elements intersect the given ones (from graph/console hover). */
  highlight(items: Item[] | null) {
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
  return Number.isInteger(v) ? String(v) : v.toPrecision(4);
}
