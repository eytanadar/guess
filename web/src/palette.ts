// Command palette (Cmd/Ctrl+K): fuzzy search over commands, examples, nodes,
// field values, toolbar actions and recent commands.
import { fuzzy } from "./help";

export type PaletteKind = "command" | "example" | "node" | "value" | "action" | "recent";

export interface PaletteItem {
  kind: PaletteKind;
  label: string;
  /** shown dimmed after the label; also searched */
  detail?: string;
  run(): void;
}

const KIND_LABEL: Record<PaletteKind, string> = {
  command: "command", example: "example", node: "node", value: "select", action: "action", recent: "recent",
};
const KIND_BONUS: Record<PaletteKind, number> = { action: 60, command: 50, recent: 30, example: 20, node: 10, value: 0 };

export class Palette {
  private root = document.createElement("div");
  private input = document.createElement("input");
  private list = document.createElement("div");
  private items: PaletteItem[] = [];
  private shown: PaletteItem[] = [];
  private active = 0;
  private restoreFocus: HTMLElement | null = null;

  constructor(private source: () => Promise<PaletteItem[]>) {
    this.root.className = "palette-backdrop";
    this.root.hidden = true;
    const box = document.createElement("div");
    box.className = "palette";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-label", "Command palette");
    this.input.type = "text";
    this.input.placeholder = "Search commands, examples, nodes, values, actions…";
    this.input.setAttribute("aria-label", "Search");
    this.list.className = "palette-list";
    this.list.setAttribute("role", "listbox");
    const hint = document.createElement("div");
    hint.className = "palette-hint";
    hint.textContent = "↑↓ to move · Enter to choose · Esc to close · try “dept3”, “layout”, “v12”, “undo”";
    box.append(this.input, this.list, hint);
    this.root.append(box);
    document.body.append(this.root);
    this.root.addEventListener("pointerdown", (ev) => {
      if (ev.target === this.root) this.close();
    });
    this.input.addEventListener("input", () => {
      this.active = 0;
      this.render();
    });
    this.input.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        const n = this.shown.length;
        if (n) this.active = (this.active + (ev.key === "ArrowDown" ? 1 : n - 1)) % n;
        this.render(false);
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        this.choose(this.shown[this.active]);
      } else if (ev.key === "Escape") {
        ev.preventDefault();
        ev.stopPropagation();
        this.close();
      }
    });
  }

  get isOpen() {
    return !this.root.hidden;
  }

  async open(query = "") {
    this.restoreFocus = document.activeElement as HTMLElement | null;
    this.items = await this.source();
    this.root.hidden = false;
    this.input.value = query;
    this.active = 0;
    this.render();
    this.input.focus();
    this.input.select();
  }

  close() {
    if (this.root.hidden) return;
    this.root.hidden = true;
    this.restoreFocus?.focus?.();
  }

  private choose(item?: PaletteItem) {
    if (!item) return;
    this.root.hidden = true;
    item.run();
  }

  private render(rebuild = true) {
    if (rebuild) {
      const q = this.input.value.trim();
      if (!q) {
        this.shown = this.items.filter((i) => i.kind === "recent").slice(0, 8)
          .concat(this.items.filter((i) => i.kind === "action"))
          .concat(this.items.filter((i) => i.kind === "example").slice(0, 6));
      } else {
        this.shown = this.items
          .map((it) => ({ it, s: Math.max(fuzzy(q, it.label), it.detail ? fuzzy(q, it.detail) - 150 : -1) }))
          .filter((x) => x.s >= 0)
          .sort((a, b) => b.s + KIND_BONUS[b.it.kind] - (a.s + KIND_BONUS[a.it.kind]))
          .slice(0, 60)
          .map((x) => x.it);
      }
    }
    this.list.replaceChildren();
    this.shown.forEach((it, k) => {
      const row = document.createElement("div");
      row.className = "palette-item" + (k === this.active ? " active" : "");
      row.setAttribute("role", "option");
      const kind = document.createElement("span");
      kind.className = `palette-kind k-${it.kind}`;
      kind.textContent = KIND_LABEL[it.kind];
      const label = document.createElement("span");
      label.className = "palette-label";
      label.textContent = it.label;
      row.append(kind, label);
      if (it.detail) {
        const d = document.createElement("span");
        d.className = "palette-detail";
        d.textContent = it.detail;
        row.append(d);
      }
      row.addEventListener("pointerenter", () => {
        this.active = k;
        for (const r of this.list.children) r.classList.remove("active");
        row.classList.add("active");
      });
      row.addEventListener("click", () => this.choose(it));
      this.list.append(row);
    });
    if (!this.shown.length) {
      const none = document.createElement("div");
      none.className = "palette-empty";
      none.textContent = "No matches";
      this.list.append(none);
    }
    this.list.children[this.active]?.scrollIntoView({ block: "nearest" });
  }
}
