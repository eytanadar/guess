// Altair (Vega-Lite) charts in the dock, linked to the graph. Loaded on first
// use: vega, vega-lite and vega-embed are about 1 MB.
//
// A mark that stands for one element (its datum carries _node or _edge) links
// to it directly. A mark that summarises many (a bar of count() by dept, a bin)
// links through a query made from the fields it is grouped by, such as
// (dept == 'dept1') or (degree >= 4) & (degree < 6). Interval and point
// selections (brushes, clickable legends) become queries too.
import type { Item } from "./dock";

export interface VegaMsg {
  id: string;
  title: string;
  spec: any;
  cell: number | null;
  fields: { n: string[]; e: string[] };
  live?: boolean;
  canLive?: boolean;
}

export interface VegaHooks {
  /** hovering a mark (null: left it); expr when it stands for a query */
  hover(items: Item[] | null, expr: string | null, title: string, lines: string[], ev: MouseEvent | null): void;
  click(items: Item[], expr: string | null, ev: MouseEvent): void;
  context(items: Item[], expr: string | null, title: string, ev: MouseEvent): void;
  /** a selection (brush) on the chart changed: its query, or null when cleared */
  brush(expr: string | null): void;
  /** the elements a query gives now */
  resolve(expr: string): Promise<Item[]>;
}

export interface VegaChart {
  highlight(items: Item[] | null): void;
  destroy(): void;
}

const HL = "guess_hl";

/** Python literal for a datum value. */
function lit(v: unknown): string | null {
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "string") return JSON.stringify(v);
  return null;
}

/** The rows' element key (_node or _edge), from the inline datasets. */
function rowKey(spec: any): "_node" | "_edge" | null {
  for (const rows of Object.values<any>(spec.datasets ?? {})) {
    const r = Array.isArray(rows) ? rows[0] : null;
    if (r && "_node" in r) return "_node";
    if (r && "_edge" in r) return "_edge";
  }
  const v = spec.data?.values;
  if (Array.isArray(v) && v[0]) return "_node" in v[0] ? "_node" : "_edge" in v[0] ? "_edge" : null;
  return null;
}

/** Fade the marks of unaggregated views that aren't hovered elsewhere: a
 *  top-level variable holds the hovered ids, and each such view's opacity
 *  tests its datum against it. Views that aggregate, or set opacity, are left alone. */
function addHighlight(spec: any, key: string) {
  const aggregates = (u: any) =>
    Object.values<any>(u.encoding ?? {}).some((c) => c && typeof c === "object" && (c.aggregate || c.bin)) ||
    (u.transform ?? []).some((t: any) => t.aggregate || t.bin || t.joinaggregate || t.window);
  const walk = (u: any) => {
    if (!u || typeof u !== "object") return;
    if (u.mark && !aggregates(u) && !(u.encoding && "opacity" in u.encoding)) {
      u.encoding = { ...(u.encoding ?? {}),
        opacity: { condition: { test: `!length(${HL}) || indexof(${HL}, datum['${key}']) >= 0`, value: 1 }, value: 0.12 } };
    }
    for (const k of ["layer", "hconcat", "vconcat", "concat"]) for (const c of u[k] ?? []) walk(c);
    if (u.spec) walk(u.spec);
  };
  walk(spec);
  spec.params = [...(spec.params ?? []), { name: HL, value: [] }];
}

/** Every selection parameter in the spec: name -> "interval" | "point". */
function selections(spec: any): Map<string, string> {
  const out = new Map<string, string>();
  const walk = (u: any) => {
    if (!u || typeof u !== "object") return;
    for (const p of u.params ?? []) {
      if (p?.select) out.set(p.name, typeof p.select === "string" ? p.select : p.select.type);
    }
    for (const k of ["layer", "hconcat", "vconcat", "concat"]) for (const c of u[k] ?? []) walk(c);
    if (u.spec) walk(u.spec);
  };
  walk(spec);
  return out;
}

export async function renderVega(body: HTMLElement, m: VegaMsg, hooks: VegaHooks, dark: boolean): Promise<VegaChart> {
  const { default: embed } = await import("vega-embed");
  const spec = structuredClone(m.spec);
  const key = rowKey(spec);
  const fields = new Set(key === "_edge" ? m.fields.e : m.fields.n);
  if (key) addHighlight(spec, key);
  const sels = selections(spec);
  const hasTooltip = JSON.stringify(spec).includes('"tooltip"');
  spec.background ??= "transparent";
  // a single (or layered) view with no width of its own fits the panel
  if ((spec.mark || spec.layer) && spec.width === undefined) {
    spec.width = "container";
    spec.autosize ??= { type: "fit-x", contains: "padding" };
  }

  // a datum -> the element(s) it stands for, or the query for them
  const linkOf = (d: any): { items: Item[]; expr: string | null; title: string } | null => {
    if (!d || typeof d !== "object") return null;
    if (typeof d._node === "number") return { items: [["n", d._node]], expr: null, title: String(d.name ?? "") };
    if (typeof d._edge === "number") return { items: [["e", d._edge]], expr: null, title: String(d.name ?? "") };
    // a mark for several elements listed by id (a word in wordCloud)
    if (Array.isArray(d._nodes)) return { items: d._nodes.map((i: number) => ["n", i] as Item), expr: null, title: String(d.text ?? "") };
    if (Array.isArray(d._edges)) return { items: d._edges.map((i: number) => ["e", i] as Item), expr: null, title: String(d.text ?? "") };
    const parts: string[] = [];
    for (const k of Object.keys(d)) {
      if (k.startsWith("_") || k.endsWith("_end")) continue;
      // a binned field: bin_maxbins_10_degree with its _end
      const bin = /^bin_.*?_([A-Za-z_]\w*)$/.exec(k);
      const f = bin ? [...fields].find((x) => k.endsWith(`_${x}`)) : fields.has(k) ? k : null;
      if (!f) continue;
      if (bin && typeof d[k] === "number" && typeof d[`${k}_end`] === "number") {
        parts.push(`(${f} >= ${d[k]}) & (${f} < ${d[`${k}_end`]})`);
      } else if (!bin) {
        const v = lit(d[k]);
        if (v !== null) parts.push(`(${f} == ${v})`);
      }
    }
    if (!parts.length) return null;
    const expr = parts.length === 1 ? parts[0].replace(/^\((.*)\)$/, "$1") : parts.join(" & ");
    return { items: [], expr, title: expr };
  };
  const describe = (d: any) => Object.entries(d ?? {})
    .filter(([k, v]) => !k.startsWith("_") && (typeof v === "number" || typeof v === "string"))
    .slice(0, 6).map(([k, v]) => `${k}: ${typeof v === "number" && !Number.isInteger(v) ? v.toPrecision(4) : v}`);

  const res = await embed(body, spec, {
    actions: { export: true, source: false, compiled: false, editor: false },
    theme: dark ? "dark" : undefined,
    renderer: "svg",
    // Vega's own tooltips only for charts that ask for them
    tooltip: hasTooltip,
  });
  const view = res.view;
  let hoverToken = 0;
  view.addEventListener("mouseover", async (ev: any, item: any) => {
    const link = linkOf(item?.datum);
    if (!link) return;
    const token = ++hoverToken;
    const items = link.expr ? await hooks.resolve(link.expr) : link.items;
    if (token !== hoverToken) return;
    hooks.hover(items, link.expr, hasTooltip ? "" : link.title, hasTooltip ? [] : describe(item.datum), ev as MouseEvent);
  });
  view.addEventListener("mouseout", () => {
    ++hoverToken;
    hooks.hover(null, null, "", [], null);
  });
  view.addEventListener("click", async (ev: any, item: any) => {
    const link = linkOf(item?.datum);
    if (!link) return;
    hooks.click(link.expr ? await hooks.resolve(link.expr) : link.items, link.expr, ev as MouseEvent);
  });
  // right-click: Vega doesn't route contextmenu to items, so find the item under the pointer
  const onContext = async (ev: MouseEvent) => {
    const el = ev.target as any;
    const item = el?.__data__;
    const link = linkOf(item?.datum);
    if (!link) return;
    ev.preventDefault();
    const items = link.expr ? await hooks.resolve(link.expr) : link.items;
    if (items.length) hooks.context(items, link.expr, link.title, ev);
  };
  body.addEventListener("contextmenu", onContext);

  // selections: a brush's ranges, or a point selection's values, as a query
  for (const [name, type] of sels) {
    try {
      view.addSignalListener(name, (_n: string, value: any) => {
        const parts: string[] = [];
        for (const [k, v] of Object.entries<any>(value ?? {})) {
          if (k.startsWith("vl") || !fields.has(k) || !Array.isArray(v) || !v.length) continue;
          if (type === "interval" && v.length === 2 && v.every((x) => typeof x === "number")) {
            const round = (x: number) => Number(x.toPrecision(6));
            const [a, b] = [round(Math.min(v[0], v[1])), round(Math.max(v[0], v[1]))];
            parts.push(`(${k} >= ${a}) & (${k} <= ${b})`);
          } else {
            const vals = v.map(lit).filter((x): x is string => x !== null);
            if (vals.length) parts.push(`(${k} in (${vals.join(", ")}${vals.length === 1 ? "," : ""}))`);
          }
        }
        hooks.brush(parts.length ? parts.join(" & ") : null);
      });
    } catch {
      /* not a top-level signal (e.g. inside a concatenated view) */
    }
  }

  return {
    highlight(items) {
      if (!key) return;
      const want = key === "_node" ? "n" : "e";
      const ids = (items ?? []).filter((i) => i[0] === want).map((i) => i[1]);
      try {
        void view.signal(HL, ids).runAsync();
      } catch {
        /* the chart was replaced */
      }
    },
    destroy() {
      body.removeEventListener("contextmenu", onContext);
      res.finalize();
    },
  };
}
