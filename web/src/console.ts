// The interactive console: a CodeMirror "working cell" at the bottom (Shift+Enter
// runs it) above which executed cells stack up with their output. Output spans
// are linked to graph elements; an executed cell can be pulled back into the
// working cell to edit and run again.
import { Compartment, EditorState, Prec, StateField, type Extension } from "@codemirror/state";
import {
  EditorView, hoverTooltip, keymap, placeholder, drawSelection, tooltips, showTooltip, rectangularSelection,
  crosshairCursor, type Command, type Tooltip,
} from "@codemirror/view";
import { highlightSelectionMatches, searchKeymap } from "@codemirror/search";
import { vim } from "@replit/codemirror-vim";
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
  run(code: string, cell: number, quiet?: boolean): Promise<boolean>;
  completions(text: string): Promise<{ prefix: string; items: string[] }>;
  /** Hovering a documented name in an executed cell. */
  doc(name: string | null, ev: MouseEvent | null): void;
  interrupt(): void;
  /** items === null means the pointer left all linked output. */
  hover(items: Item[] | null, el: HTMLElement | null, ev: MouseEvent | null): void;
  context(items: Item[], ev: MouseEvent, expr?: string): void;
  /** Clicking linked output (a node, an edge or a group). */
  click(items: Item[], ev: MouseEvent, expr?: string): void;
  /** Hovering a cell's number: show what it changed (null: left it). */
  cellHover?(cell: number | null): void;
  /** Hovering a name or a query in executed code: what it means now (null: left it). */
  peek?(expr: string | null, ev: MouseEvent | null): void;
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
  /** edits made to recalled commands while browsing history (cleared on run) */
  private recalledEdits = new Map<number, string>();
  private hpos = 0;
  private draft = "";
  private _busy = false;
  /** a cell is running */
  get busy() {
    return this._busy;
  }
  private queue: Promise<unknown> = Promise.resolve();
  private cellCount = 0;
  /** where output goes while a cell runs (null: loose output, e.g. from timers) */
  private current: HTMLElement | null = null;
  private currentCell: HTMLElement | null = null;
  private currentCode = "";
  private hot: HTMLElement | null = null;
  private linkedEls: HTMLElement[] = [];
  private lastText: HTMLElement | null = null;
  docs: Record<string, string> = {};
  private vimMode = new Compartment();
  /** watched cells: re-run (quietly, in place) after every other command */
  private watched = new Map<HTMLElement, { code: string; n: number; out: HTMLElement }>();
  private findBar = el("div", "console-find");
  private findInput = el("input") as HTMLInputElement;
  private findCount = el("span", "console-find-count");

  constructor(root: HTMLElement, private host: ConsoleHost) {
    root.classList.add("console");
    this.out = el("div", "console-out");
    this.findInput.type = "search";
    this.findInput.placeholder = "Find in output…";
    this.findInput.oninput = () => this.applyFind();
    this.findInput.onkeydown = (ev) => {
      if (ev.key === "Escape") {
        ev.stopPropagation();
        this.closeFind();
      }
    };
    const findClose = el("button", "console-find-close");
    findClose.textContent = "✕";
    findClose.title = "Close (Esc)";
    findClose.onclick = () => this.closeFind();
    this.findBar.append(this.findInput, this.findCount, findClose);
    this.findBar.hidden = true;
    root.append(this.findBar);
    this.inputBox = el("div", "console-in");
    const gutter = el("div", "cell-gutter");
    gutter.textContent = "▶";
    gutter.title = "Run (Shift+Enter)";
    gutter.onclick = () => this.runEditor();
    const hint = el("div", "cell-hint");
    hint.textContent = "Shift+Enter to run · Tab completes · ↑ on the first line for history · Esc interrupts";
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
      const peek = fn ? null : this.peekAt(ev.target as HTMLElement);
      if (!peek) this.host.doc(fn ? fn.textContent : null, fn ? ev : null);
      this.setPeek(peek, ev);
      this.onOver(ev);
    });
    this.out.addEventListener("mousemove", (ev) => {
      if (this.hot) this.host.hover(collect(this.hot), this.hot, ev);
    });
    this.out.addEventListener("mouseleave", (ev) => {
      this.setHot(null, null);
      this.setPeek(null, ev);
    });
    this.out.addEventListener("click", (ev) => {
      const t = (ev.target as HTMLElement).closest<HTMLElement>("[data-k]");
      if (!t || t.closest(".stale") || window.getSelection()?.toString()) return;
      this.host.click(collect(t), ev, t.dataset.q);
    });
    this.out.addEventListener("contextmenu", (ev) => {
      const t = (ev.target as HTMLElement).closest<HTMLElement>("[data-k]");
      if (!t || t.closest(".stale")) return;
      ev.preventDefault();
      this.host.context(collect(t), ev, t.dataset.q);
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
    // ↑ on the first line of the cell recalls the previous command; ↓ on the last
    // line goes forward again, back to the unsaved cell (kept intact); at that
    // cell ↓ does nothing. Inside a cell the arrows just move between lines.
    const lineOf = (v: EditorView) => v.state.doc.lineAt(v.state.selection.main.head).number;
    const up: Command = (v) => {
      if (completionStatus(v.state) || !v.state.selection.main.empty || lineOf(v) > 1) return false;
      this.recall(-1);
      return true;
    };
    const down: Command = (v) => {
      if (completionStatus(v.state) || !v.state.selection.main.empty || lineOf(v) < v.state.doc.lines) return false;
      if (this.hpos < this.history.length) this.recall(1);
      return true; // at the present cell: nothing
    };
    const tab: Command = (v) => {
      if (completionStatus(v.state) === "active") return acceptCompletion(v);
      const sel = v.state.selection.main;
      const before = lineBefore(v.state, sel.head);
      if (!sel.empty || !/[\w.]$/.test(before)) return false; // indent
      void this.tabComplete(v, before);
      return true;
    };
    let vimOn = false;
    try {
      vimOn = localStorage.getItem("guess.vim") === "1";
    } catch {
      /* storage unavailable */
    }
    return [
      this.vimMode.of(vimOn ? vim() : []),
      history(),
      drawSelection(),
      EditorState.allowMultipleSelections.of(true),
      rectangularSelection(),
      crosshairCursor(),
      highlightSelectionMatches(),
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
      keymap.of([...closeBracketsKeymap, ...completionKeymap, ...historyKeymap, ...searchKeymap, indentWithTab, ...defaultKeymap]),
      this.signatureHelp(),
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

  /** Parameter hints: inside `name(`, show its signature with the current argument in bold. */
  private signatureHelp(): Extension {
    const compute = (state: EditorState): Tooltip | null => {
      const sel = state.selection.main;
      if (!sel.empty) return null;
      const call = enclosingCall(state.sliceDoc(Math.max(0, sel.head - 3000), sel.head));
      if (!call) return null;
      const doc = this.docs[call.name];
      if (!doc) return null;
      const sig = doc.split("\n")[0];
      const open = sel.head - call.offsetFromEnd;
      return {
        pos: open, above: true, strictSide: true, arrow: false,
        create: () => ({ dom: sigDom(sig, call.name, call.arg, call.keyword) }),
      };
    };
    return StateField.define<Tooltip | null>({
      create: compute,
      update: (old, tr) => (tr.docChanged || tr.selection ? compute(tr.state) : old),
      provide: (f) => showTooltip.from(f),
    });
  }

  private toggleWatch(root: HTMLElement, code: string, n: number, out: HTMLElement, btn: HTMLElement) {
    if (this.watched.has(root)) {
      this.watched.delete(root);
      root.classList.remove("watched");
      btn.textContent = "Watch";
    } else {
      this.watched.set(root, { code, n, out });
      root.classList.add("watched");
      btn.textContent = "Unwatch";
    }
  }

  private async runWatched() {
    for (const [root, w] of [...this.watched]) {
      if (!root.isConnected) {
        this.watched.delete(root);
        continue;
      }
      w.out.replaceChildren();
      this.current = w.out;
      this.currentCell = root;
      this.currentCode = w.code;
      this.lastText = null;
      root.classList.add("refreshing");
      try {
        const ok = await this.host.run(w.code, w.n, true);
        root.classList.toggle("failed", !ok);
      } finally {
        root.classList.remove("refreshing");
        this.current = null;
        this.currentCell = null;
      }
    }
  }

  /** The executed cells, for notebook and report export. */
  cellsForExport(): { n: number; code: string; output: string; failed: boolean; undone: boolean; hidden: boolean }[] {
    const out = [];
    for (const c of this.out.querySelectorAll<HTMLElement>(".cell")) {
      const code = [...c.querySelectorAll(".cell-code .code-line")].map((l) => l.textContent ?? "").join("\n");
      const o = c.querySelector<HTMLElement>(".cell-out");
      const output = o ? [...o.children].map((x) => {
        const full = x.querySelector(".error-full");
        return full ? full.textContent : (x as HTMLElement).innerText ?? x.textContent;
      }).join("\n") : "";
      out.push({ n: Number(c.dataset.n), code, output: output.replace(/\n+$/, ""), failed: c.classList.contains("failed"), undone: c.classList.contains("undone"),
                hidden: c.classList.contains("hidden-move") && !this.out.classList.contains("show-moves") });
    }
    return out;
  }

  /** Vim key bindings in the working cell (remembered). */
  setVim(on: boolean) {
    this.view.dispatch({ effects: this.vimMode.reconfigure(on ? vim() : []) });
    try {
      localStorage.setItem("guess.vim", on ? "1" : "0");
    } catch {
      /* storage unavailable */
    }
  }

  get vim(): boolean {
    try {
      return localStorage.getItem("guess.vim") === "1";
    } catch {
      return false;
    }
  }

  /** Show the cells recorded for node drags (hidden by default; remembered). */
  setShowMoves(on: boolean) {
    this.out.classList.toggle("show-moves", on);
    this.scroll();
    try {
      localStorage.setItem("guess.showMoves", on ? "1" : "0");
    } catch {
      /* storage unavailable */
    }
  }

  get showMoves(): boolean {
    try {
      return localStorage.getItem("guess.showMoves") === "1";
    } catch {
      return false;
    }
  }

  /** Find in output: show only cells whose code or output contains the text. */
  openFind() {
    this.findBar.hidden = false;
    this.findInput.focus();
    this.findInput.select();
    this.applyFind();
  }

  closeFind() {
    this.findBar.hidden = true;
    this.findInput.value = "";
    this.applyFind();
    this.focus();
  }

  private applyFind() {
    const q = this.findInput.value.trim().toLowerCase();
    let n = 0;
    for (const c of this.out.children as HTMLCollectionOf<HTMLElement>) {
      const hit = !q || (c.textContent ?? "").toLowerCase().includes(q);
      c.classList.toggle("find-hidden", !hit);
      if (q && hit) n++;
    }
    this.findCount.textContent = q ? `${n} match${n === 1 ? "" : "es"}` : "";
  }

  /** Put code in the working cell: replace it if empty, else add on a new line. */
  insert(code: string) {
    const cur = this.code();
    if (!cur.trim()) this.setCode(code);
    else this.setCode(cur.replace(/\s+$/, "") + "\n" + code);
    this.focus();
  }

  /** Most recent commands first (for the palette). */
  recent(n = 30): string[] {
    const out: string[] = [];
    for (let i = this.history.length - 1; i >= 0 && out.length < n; i--) {
      if (!out.includes(this.history[i])) out.push(this.history[i]);
    }
    return out;
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
    // keep what's in the cell: the unsaved draft, or edits to a recalled command
    if (this.hpos === this.history.length) this.draft = this.code();
    else if (this.code() !== this.history[this.hpos]) this.recalledEdits.set(this.hpos, this.code());
    this.hpos = n;
    const text = n === this.history.length ? this.draft : (this.recalledEdits.get(n) ?? this.history[n]);
    // going back, the caret lands on the first line (↑ again goes further back);
    // going forward, on the last line (↓ again goes further forward)
    this.setCode(text, dir < 0 ? "end-of-first" : "end");
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

  /** Scroll to a cell and flash it ("show the code that changed it"). */
  reveal(n: number): boolean {
    const cell = this.out.querySelector<HTMLElement>(`.cell[data-n="${n}"]`);
    if (!cell) return false;
    cell.scrollIntoView({ block: "center", behavior: "smooth" });
    cell.classList.remove("flash");
    void cell.offsetWidth;
    cell.classList.add("flash");
    return true;
  }

  /** Put text at the caret of the working cell (replacing any selection). */
  insertAtCursor(text: string) {
    const sel = this.view.state.selection.main;
    this.view.dispatch({ changes: { from: sel.from, to: sel.to, insert: text },
                         selection: { anchor: sel.from + text.length }, scrollIntoView: true });
    this.focus();
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
  submit(code: string, opts: { hidden?: boolean } = {}): Promise<boolean> {
    const run = this.queue.then(() => this.execute(code, opts.hidden ?? false));
    this.queue = run.catch(() => false);
    return run;
  }

  /** A hidden cell (a node drag) is a normal command — history(), undo, logs and
   * exports include it — but stays out of sight unless "Show node moves" is on,
   * or it fails. */
  private async execute(code: string, hidden = false): Promise<boolean> {
    const cell = this.newCell(code, hidden);
    if (!hidden) this.remember(code);
    this.current = cell.out;
    this.currentCell = cell.root;
    this.currentCode = code;
    this.lastText = null;
    this.setBusy(true, cell);
    const t0 = performance.now();
    let ok = false;
    try {
      ok = await this.host.run(code, cell.n);
      return ok;
    } finally {
      this.current = null;
      this.currentCell = null;
      this.lastText = null;
      this.setBusy(false, cell);
      cell.root.classList.add(ok ? "ok" : "failed");
      if (!ok) cell.root.classList.remove("hidden-move");
      const secs = (performance.now() - t0) / 1000;
      if (secs >= 0.5) {
        const t = el("span", "cell-time");
        t.textContent = secs < 60 ? `${secs.toFixed(1)}s` : `${Math.floor(secs / 60)}m${Math.round(secs % 60)}s`;
        cell.root.querySelector(".cell-actions")!.before(t);
      }
      if (!cell.out.childElementCount) cell.root.classList.add("empty");
      if (this.watched.size) await this.runWatched();
      if (!hidden) this.focus();
    }
  }

  private newCell(code: string, hidden = false): Cell {
    const n = ++this.cellCount;
    const root = el("div", hidden ? "cell hidden-move" : "cell");
    root.dataset.n = String(n);
    const head = el("div", "cell-head");
    const num = el("button", "cell-num");
    num.textContent = `[${n}]`;
    num.title = "Collapse/expand output · hover: what this cell changed";
    num.onmouseenter = () => this.host.cellHover?.(n);
    num.onmouseleave = () => this.host.cellHover?.(null);
    num.onclick = () => root.classList.toggle("collapsed");
    const src = el("div", "cell-code echo");
    src.dataset.code = code;
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
    const watch = el("button", "cell-watch");
    watch.textContent = "Watch";
    watch.title = "Re-run this cell after every command (live statistics, charts, legends)";
    watch.onclick = () => this.toggleWatch(root, code, n, out, watch);
    actions.append(editBtn, rerun, watch);
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

  /** Syntax-highlighted source; documented command names become hoverable,
   *  and every token knows its offset (for hovering names and queries). */
  private renderCode(code: string): DocumentFragment {
    // one block per line, so an error can mark the line it happened on
    const frag = document.createDocumentFragment();
    const tree = pythonLanguage.parser.parse(code);
    let line = el("span", "code-line");
    let pos = 0;
    highlightCode(code, tree, classHighlighter, (text, classes) => {
      const span = el("span", classes || "tok");
      if (classes && text in this.docs && classes.includes("variableName")) span.classList.add("fn");
      span.dataset.from = String(pos);
      span.textContent = text;
      line.append(span);
      pos += text.length;
    }, () => {
      frag.append(line);
      line = el("span", "code-line");
      pos += 1;
    });
    frag.append(line);
    return frag;
  }

  // ---- hovering names and queries in executed code -------------------------------------
  private peekState: { expr: string; spans: HTMLElement[] } | null = null;

  /** The name or query under a token of executed code, with the tokens it spans. */
  private peekAt(t: HTMLElement): { expr: string; spans: HTMLElement[] } | null {
    const src = t.closest<HTMLElement>(".cell-code");
    if (!src || t.dataset.from === undefined || !src.dataset.code) return null;
    const code = src.dataset.code;
    const range = peekRange(code, Number(t.dataset.from));
    if (!range) return null;
    const spans = [...src.querySelectorAll<HTMLElement>("[data-from]")].filter((s) => {
      const f = Number(s.dataset.from);
      return f >= range[0] && f < range[1];
    });
    return { expr: code.slice(range[0], range[1]), spans };
  }

  private setPeek(p: { expr: string; spans: HTMLElement[] } | null, ev: MouseEvent) {
    if (p?.expr === this.peekState?.expr && p?.spans[0] === this.peekState?.spans[0]) return;
    for (const s of this.peekState?.spans ?? []) s.classList.remove("peeking");
    this.peekState = p;
    for (const s of p?.spans ?? []) s.classList.add("peeking");
    this.host.peek?.(p ? p.expr : null, p ? ev : null);
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

  print(segs: Seg[], gid?: number) {
    const d = el("div", "result");
    if (gid !== undefined) {
      d.dataset.gid = String(gid);
      if (this.graph && gid !== this.graph.gid) d.classList.add("stale");
    }
    for (const s of segs) d.append(renderSeg(s));
    this.append(d);
  }

  private graph: { gid: number; name: string } | null = null;
  private graphNames = new Map<number, string>();

  /** A new graph is showing: output about earlier graphs stops linking (its
   *  element ids now mean other elements, or nothing). */
  setGraph(gid: number, name: string) {
    this.graph = { gid, name };
    this.graphNames.set(gid, name);
    this.out.querySelectorAll<HTMLElement>(".result[data-gid]").forEach((r) => {
      const stale = Number(r.dataset.gid) !== gid;
      r.classList.toggle("stale", stale);
      if (stale && !r.title) {
        const n = this.graphNames.get(Number(r.dataset.gid));
        r.title = `From an earlier graph${n ? ` (${n})` : ""}: not linked to this one`;
      }
    });
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

  /** An error: the one-line summary, with the full traceback behind "details";
   *  `line` marks that line of the running cell. */
  error(t: string, summary?: string, line?: number) {
    const d = el("div", "error");
    const short = summary && summary.trim() !== t.trim() ? summary : null;
    const where = line && this.currentCell && this.currentCode.split("\n").length > 1 ? `Line ${line}: ` : "";
    if (short) {
      const s = el("span", "error-summary");
      s.textContent = where + short;
      const more = el("button", "error-more");
      more.textContent = "details";
      more.title = "Show the full traceback";
      const full = el("div", "error-full");
      full.textContent = t;
      full.hidden = true;
      more.onclick = () => {
        full.hidden = !full.hidden;
        more.textContent = full.hidden ? "details" : "hide";
      };
      d.append(s, " ", more, full);
    } else {
      d.textContent = where + t;
    }
    if (line && this.currentCell) {
      const lines = this.currentCell.querySelectorAll(".cell-code .code-line");
      lines[line - 1]?.classList.add("err-line");
    }
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
    this._busy = busy;
    this.inputBox.classList.toggle("busy", busy);
    cell?.root.classList.toggle("running", busy);
  }

  private remember(code: string) {
    if (this.history[this.history.length - 1] !== code) this.history.push(code);
    this.history = this.history.slice(-500);
    this.recalledEdits.clear();
    this.hpos = this.history.length;
    this.draft = "";
    try {
      localStorage.setItem("guess.history", JSON.stringify(this.history));
    } catch {
      /* storage unavailable */
    }
  }

  /** Mark the output that mentions these elements (hovered in the graph, a table, a chart or a legend). */
  highlight(items: Item[] | null) {
    for (const el of this.linkedEls) el.classList.remove("linked");
    this.linkedEls = [];
    if (!items || !items.length || items.length > 5000) return;
    const keys = new Set(items.map(([k, id]) => k + id));
    this.out.querySelectorAll<HTMLElement>(".result:not(.stale) [data-k=n], .result:not(.stale) [data-k=e]").forEach((x) => {
      if (keys.has(x.dataset.k! + x.dataset.id) && x !== this.hot) {
        x.classList.add("linked");
        this.linkedEls.push(x);
      }
    });
  }

  // ---- linked hovering ---------------------------------------------------------------
  private onOver(ev: MouseEvent) {
    const t = (ev.target as HTMLElement).closest<HTMLElement>("[data-k]");
    this.setHot(t && this.out.contains(t) && !t.closest(".stale") ? t : null, ev);
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

/** The [from, to) of what hovering offset `pos` of `code` should show: a
 *  comparison (with its whole chain, as in 3 < degree < 6) when the name is part
 *  of one, the whole expression when on & | and or not, otherwise the name.
 *  Calls are never included (the worker refuses them anyway). */
export function peekRange(code: string, pos: number): [number, number] | null {
  const tree = pythonLanguage.parser.parse(code);
  let node = tree.resolveInner(pos, 1);
  const isCmp = (n: typeof node | null) => !!n && n.name === "BinaryExpression" &&
    !!(n.getChild("CompareOp") || n.getChild("in") || n.getChild("is"));
  const chain = (n: typeof node) => {
    while (n.parent && isCmp(n.parent)) n = n.parent;
    return n;
  };
  const p = node.parent;
  if (["CompareOp", "in", "is"].includes(node.name) && p && isCmp(p)) return [chain(p).from, chain(p).to];
  if (["BitOp", "and", "or"].includes(node.name) && p?.name === "BinaryExpression") return [p.from, p.to];
  if (node.name === "not" && p?.name === "UnaryExpression") return [p.from, p.to];
  if (node.name !== "VariableName") return null;
  // a callee (colorize in colorize(dept)) has its documentation instead
  if (p?.name === "CallExpression" && p.firstChild?.from === node.from) return null;
  for (let a = node.parent; a; a = a.parent) {
    if (isCmp(a)) {
      const c = chain(a);
      return [c.from, c.to];
    }
    if (!["BinaryExpression", "ParenthesizedExpression", "UnaryExpression"].includes(a.name)) break;
  }
  return [node.from, node.to];
}

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
    if (s.x?.length) span.dataset.x = JSON.stringify(s.x);
    if (s.q) span.dataset.q = s.q;
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
  // members past the display limit, and the elements behind a summary
  for (const g of [t, ...t.querySelectorAll<HTMLElement>("[data-x]")]) {
    if (g.dataset.x) for (const it of JSON.parse(g.dataset.x) as Item[]) out.push(it);
  }
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


/** The innermost unclosed call before the cursor: its name, argument index and
 *  any keyword being typed; offsetFromEnd is the distance back to its "(". */
export function enclosingCall(text: string): { name: string; arg: number; keyword: string | null; offsetFromEnd: number } | null {
  let depth = 0, arg = 0, quote = "";
  for (let i = text.length - 1; i >= 0; i--) {
    const ch = text[i];
    if (quote) {
      if (ch === quote && text[i - 1] !== "\\") quote = "";
      continue;
    }
    if (ch === '"' || ch === "'") quote = ch;
    else if (ch === ")" || ch === "]" || ch === "}") depth++;
    else if (ch === "[" || ch === "{") {
      if (depth === 0) return null;
      depth--;
    } else if (ch === "(") {
      if (depth > 0) {
        depth--;
        continue;
      }
      const m = /([A-Za-z_]\w*)\s*$/.exec(text.slice(0, i));
      if (!m) return null;
      const segment = text.slice(i + 1);
      const kw = /(?:^|,)\s*([A-Za-z_]\w*)\s*=[^=]*$/.exec(segment);
      return { name: m[1], arg, keyword: kw ? kw[1] : null, offsetFromEnd: text.length - i };
    } else if (ch === "," && depth === 0) arg++;
  }
  return null;
}

function sigDom(sig: string, name: string, arg: number, keyword: string | null): HTMLElement {
  const box = el("div", "cm-sig");
  const open = sig.indexOf("(");
  const inner = open >= 0 ? sig.slice(open + 1, sig.lastIndexOf(")")) : "";
  const params: string[] = [];
  let depth = 0, cur = "";
  for (const ch of inner) {
    if (ch === "," && depth === 0) {
      params.push(cur.trim());
      cur = "";
      continue;
    }
    if ("([{".includes(ch)) depth++;
    if (")]}".includes(ch)) depth--;
    cur += ch;
  }
  if (cur.trim()) params.push(cur.trim());
  let active = -1;
  if (keyword) active = params.findIndex((p) => p.replace(/^\*+/, "").split(/[=:]/)[0].trim() === keyword);
  if (active < 0) {
    active = Math.min(arg, params.length - 1);
    const star = params.findIndex((p) => p.startsWith("*") && !p.startsWith("**"));
    if (star >= 0 && arg >= star) active = star;
  }
  const nameEl = el("span", "cm-sig-name");
  nameEl.textContent = name;
  box.append(nameEl, "(");
  params.forEach((p, k) => {
    if (k) box.append(", ");
    const pe = el("span", k === active ? "cm-sig-param active" : "cm-sig-param");
    pe.textContent = p;
    box.append(pe);
  });
  box.append(")");
  return box;
}
