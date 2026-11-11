// Data table (Cytoscape's table panel / Gephi's Data Laboratory): node or edge
// fields as sortable, searchable columns, linked to the graph selection, with
// inline editing that writes Gython.

type Item = ["n" | "e", number];

export interface TableData {
  fields: { name: string; type: string; editable: boolean }[];
  rows: (string | number | boolean | null)[][];   // [id, name, ...field values]
}

export interface TableHost {
  load(kind: "n" | "e", ids: number[] | null): Promise<TableData>;
  /** rows clicked: node ids (edges select their endpoints) */
  select(kind: "n" | "e", ids: number[], add: boolean): void;
  hover(kind: "n" | "e", id: number | null): void;
  center(kind: "n" | "e", id: number): void;
  /** commit an edit as Gython */
  edit(kind: "n" | "e", id: number, field: string, value: string, type: string): void;
  /** alt-click a row: put the element's name into the working cell */
  insert?(kind: "n" | "e", id: number): void;
  /** the filter box as Gython: the matching ids (full: run calls too, isolated);
   *  null when the text isn't a query (the rows are then matched as text) */
  query?(expr: string, kind: "n" | "e", full: boolean): Promise<QueryResult | null>;
  /** the element menu for these rows (right-click, or the Actions button) */
  context?(items: Item[], ev: MouseEvent, opts: { expr?: string; title?: string }): void;
}

export type QueryResult = { ids: number[]; other: number; title: string } | { error: string };

const ROW_H = 22;
// fields hidden unless "all fields" is ticked (display plumbing)
const VISUAL = new Set(["x", "y", "visible", "strokecolor", "labelcolor", "fixed", "style", "width", "height", "image", "labelvisible", "node1", "node2", "source", "destination"]);

export class DataTable {
  private kind: "n" | "e" = "n";
  private ids: number[] | null = null;
  private data: TableData = { fields: [], rows: [] };
  private view: TableData["rows"] = [];
  private sortCol = -2;   // -2: graph order, -1: name column, k: field k
  private sortDir = 1;
  private allFields = false;
  private selOnly = false;
  private selection = new Set<number>();
  private edgeSelection = new Set<number>();
  /** elements hovered elsewhere: their rows are marked (kept across repaints) */
  private linked = new Set<number>();
  private scrollTimer = 0;
  private head = document.createElement("div");
  private scroller = document.createElement("div");
  private spacer = document.createElement("div");
  private rowsEl = document.createElement("div");
  private search = document.createElement("input");
  private count = document.createElement("span");
  private scope = document.createElement("button");
  private cols: number[] = [];
  private loading = false;
  /** the filter box holds a Gython query: the ids it gives (null: text search) */
  private queryIds: Set<number> | null = null;
  private queryNote = "";
  private queryFull = false;
  private queryToken = 0;
  private queryTimer = 0;
  private actions = document.createElement("button");
  private editing = false;
  private dirty = false;

  constructor(readonly root: HTMLElement, private host: TableHost) {
    root.classList.add("dtable");
    const bar = document.createElement("div");
    bar.className = "dtable-bar";
    const tabs = document.createElement("span");
    tabs.className = "dtable-tabs";
    for (const [k, label] of [["n", "Nodes"], ["e", "Edges"]] as const) {
      const b = document.createElement("button");
      b.textContent = label;
      b.dataset.kind = k;
      b.onclick = () => this.show(k, null);
      tabs.append(b);
    }
    this.search.type = "search";
    this.search.placeholder = "Filter: text, or Gython (degree > 5, dept == 'x', sel)";
    this.search.title = "Text matches any cell. A Gython query (degree > 5 & dept == 'dept1', sel, a variable) " +
      "keeps the rows it gives; press Enter to run expressions with calls, such as highest(degree, 20) " +
      "(run on a scratch copy: nothing changes).";
    this.search.oninput = () => {
      this.queryFull = false;
      clearTimeout(this.queryTimer);
      this.queryTimer = window.setTimeout(() => void this.runQuery(), 200);
      if (!this.queryIds) this.refilter();       // text filtering stays instant
    };
    this.search.onkeydown = (ev) => {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      clearTimeout(this.queryTimer);
      this.queryFull = true;
      void this.runQuery();
    };
    this.actions.className = "dtable-actions";
    this.actions.textContent = "Actions ▾";
    this.actions.title = "Colour, label, hide, select … the selected rows (or every row shown)";
    this.actions.onclick = (ev) => this.openActions(ev);
    const sel = document.createElement("label");
    const selBox = document.createElement("input");
    selBox.type = "checkbox";
    selBox.onchange = () => {
      this.selOnly = selBox.checked;
      this.refilter();
    };
    sel.append(selBox, " selection only");
    const all = document.createElement("label");
    const allBox = document.createElement("input");
    allBox.type = "checkbox";
    allBox.onchange = () => {
      this.allFields = allBox.checked;
      this.layoutColumns();
    };
    all.append(allBox, " all fields");
    this.scope.className = "dtable-scope";
    this.scope.hidden = true;
    this.scope.title = "Show all rows again";
    this.scope.onclick = () => this.show(this.kind, null);
    this.count.className = "dtable-count";
    bar.append(tabs, this.search, this.actions, sel, all, this.scope, this.count);
    this.head.className = "dtable-head";
    this.scroller.className = "dtable-scroll";
    this.spacer.className = "dtable-spacer";
    this.rowsEl.className = "dtable-rows";
    this.scroller.append(this.spacer, this.rowsEl);
    this.scroller.addEventListener("scroll", () => {
      this.head.scrollLeft = this.scroller.scrollLeft;
      this.paint();
    });
    new ResizeObserver(() => this.paint()).observe(this.scroller);
    root.append(bar, this.head, this.scroller);
    this.rowsEl.addEventListener("mouseleave", () => this.host.hover(this.kind, null));
  }

  get visible() {
    return !this.root.hidden;
  }

  async show(kind: "n" | "e" = this.kind, ids: number[] | null = this.ids) {
    const kindChanged = kind !== this.kind;
    this.kind = kind;
    this.linked = new Set();
    if (kindChanged && this.search.value.trim()) queueMicrotask(() => void this.runQuery());
    this.ids = ids;
    for (const b of this.root.querySelectorAll<HTMLButtonElement>(".dtable-tabs button")) {
      b.setAttribute("aria-pressed", String(b.dataset.kind === kind));
    }
    this.scope.hidden = ids === null;
    this.scope.textContent = ids ? `${ids.length} chosen ✕` : "";
    await this.reload();
  }

  /** The graph changed: reload if visible (coalesced). */
  async refresh() {
    if (!this.visible) return;
    if (this.loading) {
      this.dirty = true;
      return;
    }
    await this.reload();
  }

  /** The selected nodes, and the edges among them (edge tables mark those). */
  setSelection(ids: Iterable<number>, edgeIds?: Iterable<number>) {
    this.selection = new Set(ids);
    this.edgeSelection = new Set(edgeIds ?? []);
    if (this.selOnly) {
      this.refilter();
      return;
    }
    // update the rows in place (repainting would swallow a double-click)
    const sel = this.kind === "n" ? this.selection : this.edgeSelection;
    for (const row of this.rowsEl.children as HTMLCollectionOf<HTMLElement>) {
      row.classList.toggle("selected", sel.has(Number(row.dataset.id)));
    }
  }

  /** Mark the rows of elements hovered elsewhere (graph, console, chart, legend). */
  highlight(items: Item[] | null) {
    const ids = new Set((items ?? []).filter((i) => i[0] === this.kind).map((i) => i[1]));
    this.linked = ids;
    for (const row of this.rowsEl.children as HTMLCollectionOf<HTMLElement>) {
      row.classList.toggle("linked", ids.has(Number(row.dataset.id)));
    }
    // hovering elsewhere (not in the table itself): bring the first marked row
    // into view when none is visible, after a short pause so sweeping past
    // nodes doesn't make the table jump
    clearTimeout(this.scrollTimer);
    if (!ids.size || this.root.hidden || !this.root.isConnected || this.root.matches(":hover")) return;
    this.scrollTimer = window.setTimeout(() => this.reveal(ids), 250);
  }

  /** Scroll so the first of these rows shows, unless one already does. */
  private reveal(ids: Set<number>) {
    if (this.linked !== ids || this.root.matches(":hover")) return;
    const h = this.scroller.clientHeight;
    if (!h) return;
    const top = this.scroller.scrollTop;
    let first = -1;
    for (let r = 0; r < this.view.length; r++) {
      if (!ids.has(this.view[r][0] as number)) continue;
      const y = r * ROW_H;
      if (y >= top && y + ROW_H <= top + h) return;      // one is visible already
      if (first < 0) first = r;
    }
    if (first < 0) return;
    this.scroller.scrollTop = Math.max(0, first * ROW_H - h / 2 + ROW_H / 2);
  }

  private async reload() {
    this.loading = true;
    try {
      this.data = await this.host.load(this.kind, this.ids);
    } finally {
      this.loading = false;
    }
    this.layoutColumns();
    // a typed query follows the graph (an Enter query with calls is kept as it
    // was: re-running it after every change would be costly)
    if (this.queryIds && !this.queryFull) void this.runQuery();
    if (this.dirty) {
      this.dirty = false;
      void this.reload();
    }
  }

  private layoutColumns() {
    const f = this.data.fields;
    this.cols = f.map((_x, i) => i).filter((i) => this.allFields || !VISUAL.has(f[i].name));
    this.head.replaceChildren();
    const mk = (text: string, col: number) => {
      const h = document.createElement("div");
      h.className = "dtable-cell dtable-th";
      h.textContent = text + (this.sortCol === col ? (this.sortDir > 0 ? " ▲" : " ▼") : "");
      h.title = col >= 0 ? `${f[col].name} (${f[col].type}) — click to sort` : "click to sort";
      h.onclick = () => {
        if (this.sortCol === col) this.sortDir = -this.sortDir;
        else { this.sortCol = col; this.sortDir = 1; }
        this.layoutColumns();
      };
      return h;
    };
    const row = document.createElement("div");
    row.className = "dtable-row";
    row.append(mk(this.kind === "n" ? "name" : "edge", -1));
    for (const i of this.cols) row.append(mk(f[i].name, i));
    this.head.append(row);
    this.refilter();
  }

  /** Read the filter box as Gython (see TableHost.query); falls back to text. */
  private async runQuery() {
    const text = this.search.value.trim();
    const token = ++this.queryToken;
    const res = text && this.host.query ? await this.host.query(text, this.kind, this.queryFull) : null;
    if (token !== this.queryToken) return;
    if (!res) {
      this.queryIds = null;
      this.queryNote = "";
    } else if ("error" in res) {
      this.queryIds = null;
      this.queryNote = `⚠ ${res.error}`;
    } else {
      this.queryIds = new Set(res.ids);
      const other = this.kind === "n" ? "edge" : "node";
      this.queryNote = "query" + (res.other ? ` (and ${res.other} ${other}${res.other === 1 ? "" : "s"}: see the ${other === "edge" ? "Edges" : "Nodes"} tab)` : "");
    }
    this.search.classList.toggle("query", this.queryIds !== null);
    this.refilter();
  }

  /** The rows a menu acts on: the selected ones, else every row shown. */
  private openActions(ev: MouseEvent) {
    const sel = this.kind === "n" ? this.selection : this.edgeSelection;
    const chosen = this.view.filter((r) => sel.has(r[0] as number));
    const kindName = this.kind === "n" ? "node" : "edge";
    if (chosen.length) {
      this.host.context?.(chosen.map((r) => [this.kind, r[0] as number] as Item), ev,
        { title: `${chosen.length} selected ${kindName}${chosen.length === 1 ? "" : "s"}` });
      return;
    }
    if (!this.view.length) return;
    const expr = this.queryIds && this.search.value.trim() && this.view.length === this.queryIds.size && !this.selOnly
      ? this.search.value.trim() : undefined;
    this.host.context?.(this.view.map((r) => [this.kind, r[0] as number] as Item), ev,
      { expr, title: `${this.view.length} ${kindName}${this.view.length === 1 ? "" : "s"} shown` });
  }

  /** Right-click on a row: the menu for it, or for every selected row when it is one of several. */
  private rowMenu(ev: MouseEvent, id: number) {
    ev.preventDefault();
    const sel = this.kind === "n" ? this.selection : this.edgeSelection;
    if (sel.has(id) && sel.size > 1) {
      const kindName = this.kind === "n" ? "node" : "edge";
      this.host.context?.([...sel].map((i) => [this.kind, i] as Item), ev, { title: `${sel.size} selected ${kindName}s` });
    } else {
      this.host.context?.([[this.kind, id]], ev, {});
    }
  }

  private refilter() {
    const q = this.search.value.trim().toLowerCase();
    let rows = this.data.rows;
    if (this.selOnly) {
      rows = rows.filter((r) => this.kind === "n" ? this.selection.has(r[0] as number) : false);
    }
    if (this.queryIds) {
      const ids = this.queryIds;
      rows = rows.filter((r) => ids.has(r[0] as number));
    } else if (q) {
      rows = rows.filter((r) => r.some((v, k) => k > 0 && v !== null && String(v).toLowerCase().includes(q)));
    }
    if (this.sortCol !== -2) {
      const k = this.sortCol + 2;
      const dir = this.sortDir;
      rows = [...rows].sort((a, b) => {
        const x = a[k], y = b[k];
        if (x === y) return 0;
        if (x === null) return 1;
        if (y === null) return -1;
        if (typeof x === "number" && typeof y === "number") return (x - y) * dir;
        return String(x).localeCompare(String(y), undefined, { numeric: true }) * dir;
      });
    }
    this.view = rows;
    this.count.textContent = `${rows.length} of ${this.data.rows.length} ${this.kind === "n" ? "nodes" : "edges"}` +
      (this.queryNote ? ` · ${this.queryNote}` : "");
    this.count.classList.toggle("error", this.queryNote.startsWith("⚠"));
    this.spacer.style.height = `${rows.length * ROW_H}px`;
    this.paint();
  }

  private paint() {
    if (this.editing) return;   // don't destroy an open editor; repaint when it closes
    const top = this.scroller.scrollTop, h = this.scroller.clientHeight || 200;
    const first = Math.max(0, Math.floor(top / ROW_H) - 5);
    const last = Math.min(this.view.length, Math.ceil((top + h) / ROW_H) + 5);
    this.rowsEl.style.transform = `translateY(${first * ROW_H}px)`;
    this.rowsEl.replaceChildren();
    const f = this.data.fields;
    for (let r = first; r < last; r++) {
      const rec = this.view[r];
      const id = rec[0] as number;
      const row = document.createElement("div");
      row.className = "dtable-row" + ((this.kind === "n" ? this.selection : this.edgeSelection).has(id) ? " selected" : "") +
        (this.linked.has(id) ? " linked" : "");
      row.dataset.id = String(id);
      const name = document.createElement("div");
      name.className = "dtable-cell dtable-name";
      name.textContent = String(rec[1]);
      name.title = "Click to select, double-click to zoom to it";
      row.append(name);
      for (const i of this.cols) {
        const c = document.createElement("div");
        c.className = "dtable-cell" + (typeof rec[i + 2] === "number" ? " num" : "");
        const v = rec[i + 2];
        c.textContent = v === null ? "" : typeof v === "number" && !Number.isInteger(v) ? String(Math.round(v * 1e4) / 1e4) : String(v);
        if (f[i].editable) {
          c.classList.add("editable");
          c.title = "Double-click to edit";
          c.ondblclick = (ev) => {
            ev.stopPropagation();
            this.startEdit(c, id, f[i].name, f[i].type, v);
          };
        }
        row.append(c);
      }
      row.onclick = (ev) => {
        if (ev.altKey && this.host.insert) this.host.insert(this.kind, id);
        else this.host.select(this.kind, [id], ev.shiftKey || ev.metaKey || ev.ctrlKey);
      };
      name.ondblclick = () => this.host.center(this.kind, id);
      row.onmouseenter = () => this.host.hover(this.kind, id);
      row.oncontextmenu = (ev) => this.rowMenu(ev, id);
      this.rowsEl.append(row);
    }
  }

  private startEdit(cell: HTMLElement, id: number, field: string, type: string, value: unknown) {
    const input = document.createElement("input");
    input.className = "dtable-edit";
    input.value = value === null || value === undefined ? "" : String(value);
    this.editing = true;
    cell.replaceChildren(input);
    input.focus();
    input.select();
    let done = false;
    const finish = (commit: boolean) => {
      if (done) return;
      done = true;
      this.editing = false;
      if (commit && input.value !== String(value ?? "")) this.host.edit(this.kind, id, field, input.value, type);
      else this.paint();
    };
    input.onkeydown = (ev) => {
      ev.stopPropagation();
      if (ev.key === "Enter") finish(true);
      if (ev.key === "Escape") finish(false);
    };
    input.onblur = () => finish(true);
    input.onclick = (ev) => ev.stopPropagation();
  }
}
