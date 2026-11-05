// Style and Filter panels. Both are GUI front ends that write Gython into the
// console (so every change is visible, reproducible and undoable).

export interface FieldInfo {
  name: string;
  type: string;
  builtin: boolean;
  numeric: boolean;
  min?: number;
  max?: number;
  integer?: boolean;
  hist?: number[];
  values?: [string | number | boolean | null, number][];
  distinct?: number;
}

export interface PanelHost {
  fields(kind: "n" | "e"): Promise<FieldInfo[]>;
  submit(code: string): Promise<boolean>;
  /** names of saved styles */
  styles(): string[];
  /** Gython for the current selection's first node, if any */
  selectedNode(): string | null;
}

import { ask } from "./dialog";

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text = "") => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
};

/** A Python literal for a field value. */
export function pyLit(v: unknown): string {
  if (v === null || v === undefined) return "None";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return String(v);
  return JSON.stringify(String(v));
}

/** Gython naming a field of the given kind (Edge.<f> when a node field shadows it). */
function fieldRef(name: string, kind: "n" | "e", nodeFields: Set<string>) {
  return kind === "e" && nodeFields.has(name) ? `Edge.${name}` : name;
}

function labelled(text: string, control: HTMLElement) {
  const l = el("label", "pf-row");
  l.append(el("span", "pf-label", text), control);
  return l;
}

function select(options: [string, string][], value?: string) {
  const s = el("select") as HTMLSelectElement;
  for (const [v, t] of options) {
    const o = el("option") as HTMLOptionElement;
    o.value = v;
    o.textContent = t;
    s.append(o);
  }
  if (value !== undefined) s.value = value;
  return s;
}

function colorInput(value: string) {
  const c = el("input") as HTMLInputElement;
  c.type = "color";
  c.value = value;
  return c;
}

function numberInput(value: number, step = "any") {
  const n = el("input") as HTMLInputElement;
  n.type = "number";
  n.step = step;
  n.value = String(value);
  n.className = "pf-num";
  return n;
}

// ---------------------------------------------------------------------------
// Style panel
// ---------------------------------------------------------------------------

export class StylePanel {
  private rules: string[] = [];
  private form = el("div", "pf-form");
  private rulesEl = el("div", "pf-rules");
  private savedEl = el("div", "pf-saved");
  private nodeFields = new Set<string>();

  constructor(readonly root: HTMLElement, private host: PanelHost) {
    root.classList.add("pf");
    root.append(el("h3", "", "Map a field to a look"), this.form,
      el("h3", "", "This style"), this.rulesEl,
      el("h3", "", "Saved styles"), this.savedEl,
      el("h3", "", "Display"), this.displaySection());
  }

  async show() {
    await this.build();
    this.renderRules();
    this.renderSaved();
  }

  /** Overlay changed (saved style names). */
  refreshSaved() {
    if (!this.root.hidden) this.renderSaved();
  }

  private async build() {
    const [nf, ef] = await Promise.all([this.host.fields("n"), this.host.fields("e")]);
    this.nodeFields = new Set(nf.map((f) => f.name));
    const skip = new Set(["x", "y", "visible", "color", "strokecolor", "labelcolor", "fixed", "style", "width", "height", "label", "labelvisible", "directed"]);
    this.form.replaceChildren();
    const target = select([["n", "Nodes"], ["e", "Edges"]]);
    const prop = select([]);
    const field = select([]);
    const opts = el("div", "pf-opts");
    const legendBox = el("input") as HTMLInputElement;
    legendBox.type = "checkbox";
    legendBox.checked = true;
    const apply = el("button", "pf-apply", "Apply");
    const fill = () => {
      const kind = target.value as "n" | "e";
      const fields = (kind === "n" ? nf : ef).filter((f) => !skip.has(f.name) || f.name === "totaldegree");
      const p = prop.value;
      prop.replaceChildren(...(kind === "n"
        ? [["color", "Colour"], ["size", "Size"], ["label", "Label"], ["shape", "Shape"]]
        : [["color", "Colour"], ["size", "Width"], ["label", "Label"]]).map(([v, t]) => {
        const o = el("option") as HTMLOptionElement;
        o.value = v;
        o.textContent = t;
        return o;
      }));
      if ([...prop.options].some((o) => o.value === p)) prop.value = p;
      const usable = fields.filter((f) => (prop.value === "size" ? f.numeric : true));
      const cur = field.value;
      field.replaceChildren(...usable.map((f) => {
        const o = el("option") as HTMLOptionElement;
        o.value = f.name;
        o.textContent = `${f.name}${f.numeric ? " (number)" : f.distinct !== undefined ? ` (${f.distinct} values)` : ""}`;
        return o;
      }));
      if (usable.some((f) => f.name === cur)) field.value = cur;
      options();
    };
    let getCode: () => string = () => "";
    const options = () => {
      opts.replaceChildren();
      const kind = target.value as "n" | "e";
      const info = (kind === "n" ? nf : ef).find((f) => f.name === field.value);
      const ref = fieldRef(field.value, kind, this.nodeFields);
      if (!info) {
        getCode = () => "";
        return;
      }
      if (prop.value === "color") {
        const mode = select([["cat", "A colour per value"], ["grad", "Gradient by value"]], info.numeric && (info.distinct ?? 99) > 12 ? "grad" : "cat");
        if (!info.numeric) mode.disabled = true;
        const c1 = colorInput("#fff3b0"), c2 = colorInput("#d7263d");
        const mid = el("input") as HTMLInputElement;
        mid.type = "checkbox";
        const c3 = colorInput("#f4a259");
        const scale = select([["linear", "linear"], ["log", "log"], ["sqrt", "square root"], ["rank", "rank"]]);
        const grad = el("div", "pf-sub");
        const midRow = el("span", "pf-inline");
        midRow.append(mid, " middle ", c3);
        grad.append(labelled("from / to", (() => { const s = el("span", "pf-inline"); s.append(c1, c2); return s; })()),
          labelled("", midRow), labelled("scale", scale));
        const sync = () => { grad.hidden = mode.value !== "grad"; };
        mode.onchange = sync;
        sync();
        opts.append(labelled("mapping", mode), grad, labelled("legend", legendBox));
        getCode = () => {
          const lines = [mode.value === "grad"
            ? `colorBy(${ref}, ${JSON.stringify(c1.value)}, ${JSON.stringify(c2.value)}, ${JSON.stringify(scale.value)}${mid.checked ? `, middle=${JSON.stringify(c3.value)}` : ""})`
            : `colorize(${ref})`];
          if (legendBox.checked) lines.push(`legendFor(${ref})`);
          return lines.join("\n");
        };
      } else if (prop.value === "size") {
        const lo = numberInput(kind === "n" ? 6 : 1), hi = numberInput(kind === "n" ? 40 : 8);
        const scale = select([["linear", "linear"], ["log", "log"], ["sqrt", "square root"], ["rank", "rank"]], "sqrt");
        const range = el("span", "pf-inline");
        range.append(lo, " to ", hi);
        opts.append(labelled("from / to", range), labelled("scale", scale));
        getCode = () => `sizeBy(${ref}, ${Number(lo.value)}, ${Number(hi.value)}, ${JSON.stringify(scale.value)})`;
      } else if (prop.value === "label") {
        const show = el("input") as HTMLInputElement;
        show.type = "checkbox";
        show.checked = true;
        opts.append(labelled("show labels", show));
        getCode = () => `labelBy(${ref}${show.checked ? "" : ", false"})`;
      } else {
        getCode = () => `shapeBy(${ref})`;
      }
    };
    target.onchange = fill;
    prop.onchange = fill;
    field.onchange = options;
    apply.onclick = async () => {
      const code = getCode();
      if (!code) return;
      if (await this.host.submit(code)) {
        this.rules.push(...code.split("\n"));
        this.renderRules();
      }
    };
    this.form.append(labelled("apply to", target), labelled("property", prop), labelled("field", field), opts, apply);
    fill();
  }

  private renderRules() {
    this.rulesEl.replaceChildren();
    if (!this.rules.length) {
      this.rulesEl.append(el("p", "pf-note", "Mappings you apply collect here; save them as a named style to reapply later."));
      return;
    }
    this.rules.forEach((r, i) => {
      const row = el("div", "pf-rule");
      row.append(el("code", "", r));
      const x = el("button", "pf-x", "✕");
      x.title = "Remove from this style (does not undo it)";
      x.onclick = () => {
        this.rules.splice(i, 1);
        this.renderRules();
      };
      row.append(x);
      this.rulesEl.append(row);
    });
    const actions = el("div", "pf-actions");
    const save = el("button", "", "Save as style…");
    save.onclick = async () => {
      const name = await ask({ title: "Save as style", note: "The mappings listed here, saved under a name you can apply later (and saved with the session).", label: "Name", value: "my style", ok: "Save" });
      if (!name) return;
      await this.host.submit(`defineStyle(${JSON.stringify(name)}, [${this.rules.map((r) => JSON.stringify(r)).join(", ")}])`);
    };
    const clear = el("button", "", "Clear list");
    clear.onclick = () => {
      this.rules = [];
      this.renderRules();
    };
    actions.append(save, clear);
    this.rulesEl.append(actions);
  }

  private renderSaved() {
    this.savedEl.replaceChildren();
    const names = this.host.styles();
    if (!names.length) {
      this.savedEl.append(el("p", "pf-note", "No saved styles yet."));
      return;
    }
    for (const n of names) {
      const row = el("div", "pf-rule");
      row.append(el("span", "", n));
      const ap = el("button", "", "Apply");
      ap.onclick = () => this.host.submit(`applyStyle(${JSON.stringify(n)})`);
      const del = el("button", "pf-x", "✕");
      del.title = "Delete this style";
      del.onclick = () => this.host.submit(`removeStyle(${JSON.stringify(n)})`);
      row.append(ap, del);
      this.savedEl.append(row);
    }
  }

  private displaySection() {
    const box = el("div", "pf-form");
    const mode = select([["original", "own colour"], ["source", "source node"], ["target", "target node"], ["mixed", "mix of both"]]);
    mode.onchange = () => this.host.submit(`setEdgeColorMode(${JSON.stringify(mode.value)})`);
    const toggle = (label: string, on: string, off: string) => {
      const b = el("input") as HTMLInputElement;
      b.type = "checkbox";
      b.onchange = () => this.host.submit(b.checked ? on : off);
      return labelled(label, b);
    };
    box.append(labelled("edge colours", mode),
      toggle("curved edges", "curvedEdges()", "curvedEdges(false)"),
      toggle("label outlines", "labelOutlines()", "labelOutlines(false)"),
      toggle("hide overlapping labels", "hideOverlappingLabels()", "hideOverlappingLabels(false)"));
    return box;
  }
}

// ---------------------------------------------------------------------------
// Filter panel
// ---------------------------------------------------------------------------

type Filter =
  | { type: "range"; kind: "n" | "e"; field: FieldInfo; lo: number; hi: number; on: boolean }
  | { type: "values"; kind: "n" | "e"; field: FieldInfo; keep: Set<string>; on: boolean }
  | { type: "kcore"; k: number; on: boolean }
  | { type: "giant"; on: boolean }
  | { type: "ego"; node: string; depth: number; on: boolean }
  | { type: "groups"; field: string; min: number; on: boolean };

export class FilterPanel {
  private filters: Filter[] = [];
  private list = el("div", "pf-filters");
  private adder = el("div", "pf-form");
  private nf: FieldInfo[] = [];
  private ef: FieldInfo[] = [];
  private status = el("p", "pf-note");

  constructor(readonly root: HTMLElement, private host: PanelHost) {
    root.classList.add("pf");
    const actions = el("div", "pf-actions");
    const reset = el("button", "", "Show all");
    reset.onclick = () => {
      this.filters = [];
      this.render();
      void this.host.submit("showAll()");
    };
    actions.append(reset);
    root.append(el("h3", "", "Add a filter"), this.adder, el("h3", "", "Filters (all must match)"), this.list, this.status, actions);
  }

  async show() {
    [this.nf, this.ef] = await Promise.all([this.host.fields("n"), this.host.fields("e")]);
    this.buildAdder();
    this.render();
  }

  private buildAdder() {
    this.adder.replaceChildren();
    const opts: [string, string][] = [];
    for (const f of this.nf) if (!["x", "y", "visible", "fixed", "width", "height", "style", "labelvisible", "strokecolor", "labelcolor"].includes(f.name)) opts.push([`n:${f.name}`, `node ${f.name}`]);
    for (const f of this.ef) if (!["visible", "labelvisible", "labelcolor"].includes(f.name)) opts.push([`e:${f.name}`, `edge ${f.name}`]);
    opts.push(["s:kcore", "k-core (structure)"], ["s:giant", "largest component"], ["s:ego", "ego network of a node"], ["s:groups", "groups of at least N"]);
    const pick = select(opts);
    const add = el("button", "", "Add");
    add.onclick = () => {
      const [k, name] = pick.value.split(/:(.*)/s);
      if (k === "s") {
        if (name === "kcore") this.filters.push({ type: "kcore", k: 2, on: true });
        else if (name === "giant") this.filters.push({ type: "giant", on: true });
        else if (name === "ego") this.filters.push({ type: "ego", node: this.host.selectedNode() ?? "", depth: 1, on: true });
        else this.filters.push({ type: "groups", field: this.nf.find((f) => f.name === "modularity_class")?.name ?? this.nf.find((f) => !f.numeric && !f.builtin)?.name ?? "", min: 3, on: true });
        if (name !== "ego") void this.apply();
      } else {
        const field = (k === "n" ? this.nf : this.ef).find((f) => f.name === name)!;
        if (field.numeric) this.filters.push({ type: "range", kind: k as "n" | "e", field, lo: field.min!, hi: field.max!, on: true });
        else this.filters.push({ type: "values", kind: k as "n" | "e", field, keep: new Set((field.values ?? []).map(([v]) => String(v))), on: true });
      }
      this.render();
    };
    const row = el("div", "pf-inline");
    row.append(pick, add);
    this.adder.append(row);
  }

  private render() {
    this.list.replaceChildren();
    if (!this.filters.length) this.list.append(el("p", "pf-note", "No filters. Each change hides what doesn't match, by running showOnly(...) in the console."));
    this.filters.forEach((f, i) => this.list.append(this.card(f, i)));
  }

  private card(f: Filter, i: number): HTMLElement {
    const card = el("div", "pf-card");
    const head = el("div", "pf-card-head");
    const on = el("input") as HTMLInputElement;
    on.type = "checkbox";
    on.checked = f.on;
    on.onchange = () => {
      f.on = on.checked;
      void this.apply();
    };
    const title = f.type === "range" || f.type === "values" ? `${f.kind === "n" ? "node" : "edge"} ${f.field.name}`
      : f.type === "kcore" ? "k-core" : f.type === "giant" ? "largest component" : f.type === "ego" ? "ego network" : "group size";
    const x = el("button", "pf-x", "✕");
    x.onclick = () => {
      this.filters.splice(i, 1);
      this.render();
      void this.apply();
    };
    head.append(on, el("span", "", title), x);
    card.append(head);
    const changed = () => void this.apply();
    if (f.type === "range") {
      const info = f.field;
      card.append(histogram(info, () => [f.lo, f.hi]));
      const step = info.integer ? "1" : String((info.max! - info.min!) / 200 || 1);
      const lo = el("input") as HTMLInputElement, hi = el("input") as HTMLInputElement;
      for (const [r, v] of [[lo, f.lo], [hi, f.hi]] as const) {
        r.type = "range";
        r.min = String(info.min);
        r.max = String(info.max);
        r.step = step;
        r.value = String(v);
      }
      const out = el("div", "pf-range-val");
      const show = () => { out.textContent = `${fmt(f.lo)} – ${fmt(f.hi)}`; };
      const upd = () => {
        f.lo = Math.min(Number(lo.value), Number(hi.value));
        f.hi = Math.max(Number(lo.value), Number(hi.value));
        show();
        card.querySelector(".pf-hist")?.replaceWith(histogram(info, () => [f.lo, f.hi]));
      };
      lo.oninput = hi.oninput = upd;
      lo.onchange = hi.onchange = changed;
      show();
      const ranges = el("div", "pf-ranges");
      ranges.append(lo, hi);
      card.append(ranges, out);
    } else if (f.type === "values") {
      const box = el("div", "pf-values");
      for (const [v, n] of f.field.values ?? []) {
        const l = el("label", "pf-value");
        const c = el("input") as HTMLInputElement;
        c.type = "checkbox";
        c.checked = f.keep.has(String(v));
        c.onchange = () => {
          if (c.checked) f.keep.add(String(v));
          else f.keep.delete(String(v));
          changed();
        };
        l.append(c, ` ${v === null ? "(none)" : v} `, el("span", "pf-count", String(n)));
        box.append(l);
      }
      const all = el("button", "", "all"), none = el("button", "", "none");
      all.onclick = () => { f.keep = new Set((f.field.values ?? []).map(([v]) => String(v))); this.render(); changed(); };
      none.onclick = () => { f.keep.clear(); this.render(); changed(); };
      const acts = el("div", "pf-inline");
      acts.append(all, none);
      card.append(acts, box);
    } else if (f.type === "kcore") {
      const n = numberInput(f.k, "1");
      n.min = "1";
      n.onchange = () => { f.k = Math.max(1, Math.round(Number(n.value))); changed(); };
      card.append(labelled("at least k neighbours", n));
    } else if (f.type === "ego") {
      const node = el("input") as HTMLInputElement;
      node.value = f.node;
      node.placeholder = "node name (or select one first)";
      const d = numberInput(f.depth, "1");
      d.min = "1";
      node.onchange = () => { f.node = node.value.trim(); changed(); };
      d.onchange = () => { f.depth = Math.max(1, Math.round(Number(d.value))); changed(); };
      card.append(labelled("node", node), labelled("depth", d));
    } else if (f.type === "groups") {
      const field = select(this.nf.filter((x) => !x.numeric || x.integer).map((x) => [x.name, x.name]), f.field);
      const n = numberInput(f.min, "1");
      field.onchange = () => { f.field = field.value; changed(); };
      n.onchange = () => { f.min = Math.max(1, Math.round(Number(n.value))); changed(); };
      card.append(labelled("field", field), labelled("min size", n));
    }
    return card;
  }

  /** Gython for the active filters, or null when nothing is filtered. */
  code(): string | null {
    const nodes: string[] = [], edges: string[] = [];
    const nodeFields = new Set(this.nf.map((f) => f.name));
    for (const f of this.filters) {
      if (!f.on) continue;
      if (f.type === "range") {
        const r = fieldRef(f.field.name, f.kind, nodeFields);
        const parts: string[] = [];
        if (f.lo > f.field.min!) parts.push(`(${r} >= ${num(f.lo)})`);
        if (f.hi < f.field.max!) parts.push(`(${r} <= ${num(f.hi)})`);
        if (parts.length) (f.kind === "n" ? nodes : edges).push(parts.length > 1 ? `(${parts.join(" & ")})` : parts[0]);
      } else if (f.type === "values") {
        const all = (f.field.values ?? []).map(([v]) => String(v));
        if (f.keep.size === all.length && (f.field.distinct ?? 0) <= all.length) continue;
        const r = fieldRef(f.field.name, f.kind, nodeFields);
        const kept = (f.field.values ?? []).filter(([v]) => f.keep.has(String(v)));
        const expr = kept.length ? `(${kept.map(([v]) => `(${r} == ${pyLit(v)})`).join(" | ")})` : (f.kind === "n" ? "ninverse(g.nodes)" : "einverse(g.edges)");
        (f.kind === "n" ? nodes : edges).push(expr);
      } else if (f.type === "kcore") nodes.push(`kCore(${f.k})`);
      else if (f.type === "giant") nodes.push("giantComponent()");
      else if (f.type === "ego" && f.node) nodes.push(`egoNetwork(${/^[A-Za-z_]\w*$/.test(f.node) ? f.node : `g.getNodeByName(${JSON.stringify(f.node)})`}, ${f.depth})`);
      else if (f.type === "groups" && f.field) nodes.push(`groupsOfSize(${f.field}, ${f.min})`);
    }
    if (!nodes.length && !edges.length) return null;
    const lines: string[] = [];
    if (nodes.length) {
      lines.push(`showOnly(${nodes.join(" & ")})`);
      if (edges.length) lines.push(`einverse(${edges.join(" & ")}).visible = false`);
    } else {
      lines.push(`showOnly(${edges.join(" & ")})`);
    }
    return lines.join("\n");
  }

  private async apply() {
    const code = this.code();
    this.status.textContent = "";
    await this.host.submit(code ?? "showAll()");
  }
}

function fmt(v: number) {
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
}

function num(v: number) {
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 1e6) / 1e6);
}

function histogram(info: FieldInfo, range: () => [number, number]): HTMLElement {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "pf-hist");
  svg.setAttribute("viewBox", "0 0 240 40");
  svg.setAttribute("preserveAspectRatio", "none");
  const h = info.hist ?? [];
  const top = Math.max(1, ...h);
  const [lo, hi] = range();
  const span = (info.max! - info.min!) || 1;
  h.forEach((c, k) => {
    const x0 = info.min! + (k / h.length) * span, x1 = info.min! + ((k + 1) / h.length) * span;
    const r = document.createElementNS(NS, "rect");
    const w = 240 / h.length;
    const bh = c ? Math.max(1.5, (Math.log1p(c) / Math.log1p(top)) * 38) : 0;
    r.setAttribute("x", String(k * w + 0.5));
    r.setAttribute("width", String(Math.max(w - 1, 0.5)));
    r.setAttribute("y", String(40 - bh));
    r.setAttribute("height", String(bh));
    r.setAttribute("class", x1 >= lo && x0 <= hi ? "in" : "out");
    svg.append(r);
  });
  return svg as unknown as HTMLElement;
}

// ---------------------------------------------------------------------------
// Variables panel (workspace)
// ---------------------------------------------------------------------------

export interface WorkspaceVar { name: string; type: string; value: string; items?: ["n" | "e", number][] }
export interface Workspace { vars: WorkspaceVar[]; states: string[]; styles: string[] }

export interface VarsHost {
  load(): Promise<Workspace>;
  hover(items: ["n" | "e", number][] | null): void;
  select(items: ["n" | "e", number][]): void;
  table(items: ["n" | "e", number][]): void;
  insert(code: string): void;
  submit(code: string): void;
}

export class VarsPanel {
  constructor(readonly root: HTMLElement, private host: VarsHost) {
    root.classList.add("pf");
  }

  async show() {
    const ws = await this.host.load();
    this.root.replaceChildren();
    this.root.append(el("h3", "", "Variables"));
    if (!ws.vars.length) this.root.append(el("p", "pf-note", "Variables you assign in the console appear here, e.g. hubs = (totaldegree > 10)."));
    for (const v of ws.vars) {
      const row = el("div", "ws-row");
      const name = el("button", "ws-name", v.name);
      name.title = "Insert the name into the code cell";
      name.onclick = () => this.host.insert(v.name);
      row.append(name, el("span", "ws-type", v.type), el("span", "ws-value", v.value));
      if (v.items?.length) {
        row.classList.add("linked");
        row.onmouseenter = () => this.host.hover(v.items!);
        row.onmouseleave = () => this.host.hover(null);
        const sel = el("button", "", "select");
        sel.title = "Select these in the graph";
        sel.onclick = () => this.host.select(v.items!);
        const tab = el("button", "", "table");
        tab.title = "Show them in the data table";
        tab.onclick = () => this.host.table(v.items!);
        row.append(sel, tab);
      }
      this.root.append(row);
    }
    if (ws.states.length) {
      this.root.append(el("h3", "", "Saved states"));
      for (const st of ws.states) {
        const row = el("div", "ws-row");
        const lit = JSON.stringify(st);
        const morph = el("button", "", "morph to");
        morph.onclick = () => this.host.submit(`morph(${lit}, 1500)`);
        const load = el("button", "", "load");
        load.onclick = () => this.host.submit(`ls(${lit})`);
        row.append(el("span", "ws-name-text", st), morph, load);
        this.root.append(row);
      }
    }
    if (ws.styles.length) {
      this.root.append(el("h3", "", "Styles"));
      for (const st of ws.styles) {
        const row = el("div", "ws-row");
        const ap = el("button", "", "apply");
        ap.onclick = () => this.host.submit(`applyStyle(${JSON.stringify(st)})`);
        row.append(el("span", "ws-name-text", st), ap);
        this.root.append(row);
      }
    }
  }
}
