// The interactive console: a CodeMirror "working cell" at the bottom (Shift+Enter
// runs it) above which executed cells stack up with their output. Output spans
// are linked to graph elements; an executed cell can be pulled back into the
// working cell to edit and run again.
import { EditorState, Prec, type Extension } from "@codemirror/state";
import { EditorView, hoverTooltip, keymap, placeholder, drawSelection, tooltips, type Command } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { bracketMatching, indentOnInput, indentUnit, syntaxHighlighting, syntaxTree } from "@codemirror/language";
import { python, pythonLanguage } from "@codemirror/lang-python";
import {
  acceptCompletion, autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap, completionStatus,
  startCompletion, type CompletionContext, type CompletionResult,
} from "@codemirror/autocomplete";
import { classHighlighter, highlightCode } from "@lezer/highlight";
import type { Seg } from "./protocol";

export type Item = ["n" | "e", number];

export interface ConsoleHost {
  /** Run code; `cell` is the console cell number it belongs to. */
  run(code: string, cell: number): Promise<boolean>;
  completions(text: string): Promise<{ prefix: string; items: string[] }>;
  /** Hovering a documented name in an executed cell. */
  doc(name: string | null, ev: MouseEvent | null): void;
  interrupt(): void;
  /** items === null means the pointer left all linked output. */
  hover(items: Item[] | null, el: HTMLElement | null, ev: MouseEvent | null): void;
  context(items: Item[], ev: MouseEvent): void;
  /** Clicking linked output (a node, an edge or a group). */
  click(items: Item[], ev: MouseEvent): void;
}

const MAX_TIP_ITEMS = 15;
const MAX_CELLS = 300;

interface Cell {
  root: HTMLElement;
  out: HTMLElement;
  n: number;
}

export class Console {
  private out: HTMLElement;
  private inputBox: HTMLElement;
  private view: EditorView;
  private history: string[] = [];
  private hpos = 0;
  private draft = "";
  private busy = false;
  private queue: Promise<unknown> = Promise.resolve();
  private cellCount = 0;
  /** where output goes while a cell runs (null: loose output, e.g. from timers) */
  private current: HTMLElement | null = null;
  private hot: HTMLElement | null = null;
  private lastText: HTMLElement | null = null;
  docs: Record<string, string> = {};

  constructor(root: HTMLElement, private host: ConsoleHost) {
    root.classList.add("console");
    this.out = el("div", "console-out");
    this.inputBox = el("div", "console-in");
    const gutter = el("div", "cell-gutter");
    gutter.textContent = "▶";
    gutter.title = "Run (Shift+Enter)";
    gutter.onclick = () => this.runEditor();
    const hint = el("div", "cell-hint");
    hint.textContent = "Shift+Enter to run · Tab completes · ↑↓ history · Esc interrupts";
    const editorBox = el("div", "cell-editor");
    this.inputBox.append(gutter, editorBox, hint);
    root.append(this.out, this.inputBox);
    try {
      this.history = JSON.parse(localStorage.getItem("guess.history") || "[]");
    } catch {
      this.history = [];
    }
    this.hpos = this.history.length;
    this.view = new EditorView({ parent: editorBox, state: EditorState.create({ extensions: this.extensions() }) });

    root.addEventListener("click", (ev) => {
      const t = ev.target as HTMLElement;
      if (window.getSelection()?.toString()) return;
      if (t.closest("[data-k], button, .cell-code, .console-in")) return;
      this.focus();
    });
    this.out.addEventListener("mouseover", (ev) => {
      const fn = (ev.target as HTMLElement).closest<HTMLElement>(".fn");
      this.host.doc(fn ? fn.textContent : null, fn ? ev : null);
      this.onOver(ev);
    });
    this.out.addEventListener("mousemove", (ev) => {
      if (this.hot) this.host.hover(collect(this.hot), this.hot, ev);
    });
    this.out.addEventListener("mouseleave", () => this.setHot(null, null));
    this.out.addEventListener("click", (ev) => {
      const t = (ev.target as HTMLElement).closest<HTMLElement>("[data-k]");
      if (!t || window.getSelection()?.toString()) return;
      this.host.click(collect(t), ev);
    });
    this.out.addEventListener("contextmenu", (ev) => {
      const t = (ev.target as HTMLElement).closest<HTMLElement>("[data-k]");
      if (!t) return;
      ev.preventDefault();
      this.host.context(collect(t), ev);
    });
  }

  // ---- the working cell ----------------------------------------------------------
  private extensions(): Extension[] {
    const run: Command = () => {
      this.runEditor();
      return true;
    };
    const escape: Command = () => {
      if (!this.busy) return false;
      this.host.interrupt();
      return true;
    };
    const firstLine = (s: EditorState) => s.doc.lineAt(s.selection.main.head).number === 1;
    const lastLine = (s: EditorState) => s.doc.lineAt(s.selection.main.head).number === s.doc.lines;
    const up: Command = (v) => {
      if (completionStatus(v.state) || !v.state.selection.main.empty || !firstLine(v.state)) return false;
      return this.recall(-1);
    };
    const down: Command = (v) => {
      if (completionStatus(v.state) || !v.state.selection.main.empty || !lastLine(v.state)) return false;
      return this.recall(1);
    };
    const tab: Command = (v) => {
      if (completionStatus(v.state) === "active") return acceptCompletion(v);
      const sel = v.state.selection.main;
      const before = lineBefore(v.state, sel.head);
      if (!sel.empty || !/[\w.]$/.test(before)) return false; // indent
      void this.tabComplete(v, before);
      return true;
    };
    return [
      history(),
      drawSelection(),
      // the editor sits in a scroll box; keep popups from being clipped by it
      tooltips({ position: "fixed", parent: document.body }),
      indentUnit.of("    "),
      EditorState.tabSize.of(4),
      python(),
      syntaxHighlighting(classHighlighter),
      bracketMatching(),
      closeBrackets(),
      indentOnInput(),
      EditorView.lineWrapping,
      placeholder("Gython — e.g. colorize(dept)"),
      autocompletion({
        override: [(ctx) => this.complete(ctx)],
        activateOnTyping: true,
        icons: false,
        maxRenderedOptions: 80,
      }),
      Prec.highest(keymap.of([
        { key: "Shift-Enter", run },
        { key: "Mod-Enter", run },
        { key: "Escape", run: escape },
        { key: "Ctrl-l", run: () => (this.clear(), true) },
      ])),
      Prec.high(keymap.of([
        { key: "Tab", run: tab },
        { key: "ArrowUp", run: up },
        { key: "ArrowDown", run: down },
      ])),
      keymap.of([...closeBracketsKeymap, ...completionKeymap, ...historyKeymap, indentWithTab, ...defaultKeymap]),
      hoverTooltip((view, pos) => {
        const w = view.state.wordAt(pos);
        if (!w) return null;
        const name = view.state.sliceDoc(w.from, w.to);
        const doc = this.docs[name];
        if (!doc || view.state.sliceDoc(w.from - 1, w.from) === ".") return null;
        return {
          pos: w.from, end: w.to, above: true,
          create: () => ({ dom: docDom(doc) }),
        };
      }, { hoverTime: 400 }),
      EditorView.contentAttributes.of({ "aria-label": "GUESS code cell", autocapitalize: "off", spellcheck: "false" }),
    ];
  }

  private async complete(ctx: CompletionContext): Promise<CompletionResult | null> {
    const before = lineBefore(ctx.state, ctx.pos);
    const m = /([A-Za-z_]\w*)?$/.exec(before)!;
    const word = m[1] ?? "";
    const afterDot = before.slice(0, before.length - word.length).endsWith(".");
    if (!ctx.explicit) {
      if (!afterDot && word.length < 2) return null;
      const node = syntaxTree(ctx.state).resolveInner(ctx.pos, -1);
      if (/String|Comment/.test(node.name)) return null;
      if (afterDot && /\d\.$/.test(before.slice(0, before.length - word.length))) return null;
    }
    if (this.busy) return null; // the worker is occupied; don't queue requests behind the run
    const { prefix, items } = await this.host.completions(before);
    if (ctx.aborted || !items.length) return null;
    return {
      from: ctx.pos - prefix.length,
      options: items.map((label) => ({
        label,
        type: label in this.docs ? "function" : undefined,
        detail: label in this.docs ? signature(this.docs[label], label) : undefined,
        info: label in this.docs ? () => docDom(this.docs[label]) : undefined,
      })),
      validFor: /^\w*$/,
    };
  }

  /** Tab: insert the longest common completion; show the list if still ambiguous. */
  private async tabComplete(v: EditorView, before: string) {
    if (this.busy) return;
    const { prefix, items } = await this.host.completions(before);
    if (!items.length) return;
    let common = items[0];
    for (const it of items) while (!it.startsWith(common)) common = common.slice(0, -1);
    const head = v.state.selection.main.head;
    if (common.length > prefix.length) {
      v.dispatch({ changes: { from: head, insert: common.slice(prefix.length) }, selection: { anchor: head + common.length - prefix.length } });
    }
    if (items.length > 1) startCompletion(v);
  }

  private recall(dir: -1 | 1): boolean {
    const n = this.hpos + dir;
    if (n < 0 || n > this.history.length) return false;
    if (this.hpos === this.history.length) this.draft = this.code();
    this.hpos = n;
    this.setCode(n === this.history.length ? this.draft : this.history[n], dir < 0 ? "end-of-first" : "end");
    return true;
  }

  private code() {
    return this.view.state.doc.toString();
  }

  /** Replace the working cell (one undoable change, so Mod-z restores the old draft). */
  setCode(code: string, caret: "end" | "end-of-first" = "end") {
    const anchor = caret === "end" ? code.length : code.split("\n")[0].length;
    this.view.dispatch({ changes: { from: 0, to: this.view.state.doc.length, insert: code }, selection: { anchor }, scrollIntoView: true });
  }

  /** Pull an executed cell back into the working cell. */
  edit(code: string) {
    this.setCode(code);
    this.hpos = this.history.length;
    this.focus();
  }

  focus() {
    this.view.focus();
  }

  private runEditor() {
    const code = this.code().replace(/\s+$/, "");
    if (!code.trim()) return;
    if (this.busy) {
      this.inputBox.classList.remove("nudge");
      void this.inputBox.offsetWidth;
      this.inputBox.classList.add("nudge");
      return;
    }
    this.setCode("");
    void this.submit(code);
  }

  // ---- executed cells ----------------------------------------------------------------
  /** Run code as a new cell (also used by menus and toolbar buttons). Cells run in order. */
  submit(code: string): Promise<boolean> {
    const run = this.queue.then(() => this.execute(code));
    this.queue = run.catch(() => false);
    return run;
  }

  private async execute(code: string): Promise<boolean> {
    const cell = this.newCell(code);
    this.remember(code);
    this.current = cell.out;
    this.lastText = null;
    this.setBusy(true, cell);
    const t0 = performance.now();
    let ok = false;
    try {
      ok = await this.host.run(code, cell.n);
      return ok;
    } finally {
      this.current = null;
      this.lastText = null;
      this.setBusy(false, cell);
      cell.root.classList.add(ok ? "ok" : "failed");
      const secs = (performance.now() - t0) / 1000;
      if (secs >= 0.5) {
        const t = el("span", "cell-time");
        t.textContent = secs < 60 ? `${secs.toFixed(1)}s` : `${Math.floor(secs / 60)}m${Math.round(secs % 60)}s`;
        cell.root.querySelector(".cell-actions")!.before(t);
      }
      if (!cell.out.childElementCount) cell.root.classList.add("empty");
      this.focus();
    }
  }

  private newCell(code: string): Cell {
    const n = ++this.cellCount;
    const root = el("div", "cell");
    root.dataset.n = String(n);
    const head = el("div", "cell-head");
    const num = el("button", "cell-num");
    num.textContent = `[${n}]`;
    num.title = "Collapse/expand output";
    num.onclick = () => root.classList.toggle("collapsed");
    const src = el("div", "cell-code echo");
    src.append(this.renderCode(code));
    src.title = "Double-click to edit";
    src.ondblclick = (ev) => {
      ev.preventDefault();
      window.getSelection()?.removeAllRanges();
      this.edit(code);
    };
    const actions = el("span", "cell-actions");
    const editBtn = el("button", "cell-edit");
    editBtn.textContent = "Edit";
    editBtn.title = "Copy into the working cell";
    editBtn.onclick = () => this.edit(code);
    const rerun = el("button", "cell-rerun");
    rerun.textContent = "Run again";
    rerun.onclick = () => void this.submit(code);
    actions.append(editBtn, rerun);
    head.append(num, src, actions);
    const out = el("div", "cell-out");
    root.append(head, out);
    this.out.append(root);
    while (this.out.childElementCount > MAX_CELLS) this.out.firstElementChild?.remove();
    this.scroll();
    return { root, out, n };
  }

  /** Strike through a cell whose effect undo() reversed (redo() clears it). */
  markUndone(n: number, undone: boolean) {
    const cell = this.out.querySelector<HTMLElement>(`.cell[data-n="${n}"]`);
    if (!cell) return;
    cell.classList.toggle("undone", undone);
    cell.querySelector(".cell-num")?.setAttribute("title", undone ? "Undone (redo() re-applies it)" : "Collapse/expand output");
  }

  /** Syntax-highlighted source; documented command names become hoverable. */
  private renderCode(code: string): DocumentFragment {
    const frag = document.createDocumentFragment();
    const tree = pythonLanguage.parser.parse(code);
    highlightCode(code, tree, classHighlighter, (text, classes) => {
      if (!classes) {
        frag.append(text);
        return;
      }
      const span = el("span", classes);
      if (text in this.docs && classes.includes("variableName")) span.classList.add("fn");
      span.textContent = text;
      frag.append(span);
    }, () => frag.append("\n"));
    return frag;
  }

  // ---- output ---------------------------------------------------------------------
  /** The element output goes to: the running cell, or a loose log block. */
  private target(): HTMLElement {
    if (this.current) return this.current;
    const last = this.out.lastElementChild as HTMLElement | null;
    if (last?.classList.contains("log")) return last;
    const log = el("div", "log");
    this.out.append(log);
    return log;
  }

  print(segs: Seg[]) {
    const d = el("div", "result");
    for (const s of segs) d.append(renderSeg(s));
    this.append(d);
  }

  text(t: string) {
    const tgt = this.target();
    if (this.lastText && this.lastText === tgt.lastElementChild) {
      this.lastText.textContent += t;
      this.scroll();
      return;
    }
    this.lastText = el("div", "stdout");
    this.lastText.textContent = t;
    this.append(this.lastText);
  }

  error(t: string) {
    const d = el("div", "error");
    d.textContent = t;
    this.append(d);
  }

  note(t: string) {
    const d = el("div", "note");
    d.textContent = t;
    this.append(d);
  }

  /** Clickable snippets that load into the working cell. */
  examples(codes: string[]) {
    const d = el("div", "examples");
    for (const code of codes) {
      const b = el("button", "example");
      b.append(this.renderCode(code));
      b.title = "Copy into the working cell";
      b.onclick = () => this.edit(code);
      d.append(b);
    }
    this.append(d);
  }

  clear() {
    this.out.replaceChildren();
    this.lastText = null;
    if (this.current) {
      // keep showing the running cell's output
      const cell = this.current.closest(".cell");
      if (cell) this.out.append(cell);
    }
  }

  private append(node: HTMLElement) {
    const tgt = this.target();
    tgt.append(node);
    while (tgt.childElementCount > 2000) tgt.firstElementChild?.remove();
    this.scroll();
  }

  private scroll() {
    this.out.scrollTop = this.out.scrollHeight;
  }

  private setBusy(busy: boolean, cell?: Cell) {
    this.busy = busy;
    this.inputBox.classList.toggle("busy", busy);
    cell?.root.classList.toggle("running", busy);
  }

  private remember(code: string) {
    if (this.history[this.history.length - 1] !== code) this.history.push(code);
    this.history = this.history.slice(-500);
    this.hpos = this.history.length;
    this.draft = "";
    try {
      localStorage.setItem("guess.history", JSON.stringify(this.history));
    } catch {
      /* storage unavailable */
    }
  }

  // ---- linked hovering ---------------------------------------------------------------
  private onOver(ev: MouseEvent) {
    const t = (ev.target as HTMLElement).closest<HTMLElement>("[data-k]");
    this.setHot(t && this.out.contains(t) ? t : null, ev);
  }

  private setHot(t: HTMLElement | null, ev: MouseEvent | null) {
    if (t === this.hot) return;
    this.hot?.classList.remove("hot");
    this.hot = t;
    if (t) {
      t.classList.add("hot");
      this.host.hover(collect(t), t, ev);
    } else {
      this.host.hover(null, null, null);
    }
  }
}

// ---- helpers -------------------------------------------------------------------------

function el(tag: string, cls?: string) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}

function lineBefore(s: EditorState, pos: number) {
  const line = s.doc.lineAt(pos);
  return line.text.slice(0, pos - line.from);
}

function signature(doc: string, name: string) {
  const sig = doc.split("\n")[0];
  return sig.startsWith(name) ? sig.slice(name.length) : "";
}

function docDom(doc: string) {
  const d = el("div", "cm-doc");
  const [sig, ...rest] = doc.split("\n");
  const h = el("div", "cm-doc-sig");
  h.textContent = sig;
  d.append(h);
  const body = rest.join("\n").trim();
  if (body) {
    const p = el("div", "cm-doc-body");
    p.textContent = body;
    d.append(p);
  }
  return d;
}

export function renderSeg(s: Seg): Node {
  if (typeof s === "string") return document.createTextNode(s);
  if ("g" in s) {
    const span = el("span", "grp");
    span.dataset.k = "g";
    if (s.a) span.dataset.a = s.a;
    for (const c of s.g) span.append(renderSeg(c));
    return span;
  }
  const span = el("span", "n" in s ? "obj node" : "obj edge");
  span.dataset.k = "n" in s ? "n" : "e";
  span.dataset.id = String("n" in s ? s.n : s.e);
  span.textContent = s.t;
  return span;
}

/** All graph elements inside an output span (the span itself if it is one). */
export function collect(t: HTMLElement): Item[] {
  if (t.dataset.k === "n" || t.dataset.k === "e") return [[t.dataset.k, Number(t.dataset.id)]];
  const out: Item[] = [];
  t.querySelectorAll<HTMLElement>("[data-k=n],[data-k=e]").forEach((x) => {
    out.push([x.dataset.k as "n" | "e", Number(x.dataset.id)]);
  });
  return out;
}

/** Tooltip body for a group span: its annotation and the first few members. */
export function groupTip(t: HTMLElement): { title: string; lines: string[] } {
  const members = Array.from(t.children).filter((c) => (c as HTMLElement).dataset.k) as HTMLElement[];
  const items = collect(t);
  const nodes = items.filter((i) => i[0] === "n").length;
  const edges = items.length - nodes;
  const parts = [];
  if (nodes) parts.push(`${nodes} node${nodes === 1 ? "" : "s"}`);
  if (edges) parts.push(`${edges} edge${edges === 1 ? "" : "s"}`);
  const title = (t.dataset.a ? t.dataset.a + " — " : "") + (parts.join(", ") || "empty");
  const lines = members.slice(0, MAX_TIP_ITEMS).map((m) =>
    m.dataset.k === "g" ? (m.dataset.a || "group") + ` (${collect(m).length})` : m.textContent || "");
  if (members.length > MAX_TIP_ITEMS) lines.push(`… ${members.length - MAX_TIP_ITEMS} more`);
  return { title, lines };
}
