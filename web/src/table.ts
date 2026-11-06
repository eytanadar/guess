// Data table (Cytoscape's table panel / Gephi's Data Laboratory): node or edge
// fields as sortable, searchable columns, linked to the graph selection, with
// inline editing that writes Gython.

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
}

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
  private head = document.createElement("div");
  private scroller = document.createElement("div");
  private spacer = document.createElement("div");
  private rowsEl = document.createElement("div");
  private search = document.createElement("input");
  private count = document.createElement("span");
  private scope = document.createElement("button");
  private cols: number[] = [];
  private loading = false;
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
    this.search.placeholder = "Filter rows…";
    this.search.oninput = () => this.refilter();
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
    bar.append(tabs, this.search, sel, all, this.scope, this.count);
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
    this.kind = kind;
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

  setSelection(ids: Iterable<number>) {
    this.selection = new Set(ids);
    if (this.selOnly) {
      this.refilter();
      return;
    }
    // update the rows in place (repainting would swallow a double-click)
    if (this.kind !== "n") return;
    for (const row of this.rowsEl.children as HTMLCollectionOf<HTMLElement>) {
      row.classList.toggle("selected", this.selection.has(Number(row.dataset.id)));
    }
  }

  private async reload() {
    this.loading = true;
    try {
      this.data = await this.host.load(this.kind, this.ids);
    } finally {
      this.loading = false;
    }
    this.layoutColumns();
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

  private refilter() {
    const q = this.search.value.trim().toLowerCase();
    let rows = this.data.rows;
    if (this.selOnly) {
      rows = rows.filter((r) => this.kind === "n" ? this.selection.has(r[0] as number) : false);
    }
    if (q) rows = rows.filter((r) => r.some((v, k) => k > 0 && v !== null && String(v).toLowerCase().includes(q)));
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
    this.count.textContent = `${rows.length} of ${this.data.rows.length} ${this.kind === "n" ? "nodes" : "edges"}`;
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
      row.className = "dtable-row" + (this.kind === "n" && this.selection.has(id) ? " selected" : "");
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
      row.onclick = (ev) => this.host.select(this.kind, [id], ev.shiftKey || ev.metaKey || ev.ctrlKey);
      name.ondblclick = () => this.host.center(this.kind, id);
      row.onmouseenter = () => this.host.hover(this.kind, id);
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
