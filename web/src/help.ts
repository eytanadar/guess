// Help browser: searchable commands (signature + docstring) and curated examples.
// Examples insert into the working cell or run directly.
import { classHighlighter, highlightCode } from "@lezer/highlight";
import { pythonLanguage } from "@codemirror/lang-python";

export interface HelpCommand { name: string; sig: string; doc: string; group: string }
export interface HelpExample { group: string; title: string; code: string; tags: string }
export interface HelpIndex { commands: HelpCommand[]; groups: string[]; examples: HelpExample[] }

export interface HelpHost {
  insert(code: string): void;
  run(code: string): void;
}

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text = "") => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
};

/** Syntax-highlighted code (same classes as the console). */
export function codeBlock(code: string): HTMLElement {
  const pre = el("pre", "help-code");
  const tree = pythonLanguage.parser.parse(code);
  highlightCode(code, tree, classHighlighter, (text, classes) => {
    const s = document.createElement("span");
    if (classes) s.className = classes;
    s.textContent = text;
    pre.append(s);
  }, () => pre.append("\n"));
  return pre;
}

/** Score a fuzzy match of query against text (higher is better; -1 = no match). */
export function fuzzy(query: string, text: string): number {
  const q = query.toLowerCase(), t = text.toLowerCase();
  if (!q) return 0;
  const at = t.indexOf(q);
  if (at >= 0) return 1000 - at * 2 - (t.length - q.length) * 0.1 + (at === 0 ? 500 : 0);
  let score = 0, ti = 0, prev = -2;
  for (const ch of q) {
    const k = t.indexOf(ch, ti);
    if (k < 0) return -1;
    score += k === prev + 1 ? 8 : (k === 0 || /[\s_.(-]/.test(t[k - 1]) || (text[k] >= "A" && text[k] <= "Z")) ? 6 : 1;
    prev = k;
    ti = k + 1;
  }
  return score;
}

export class HelpPanel {
  private index: HelpIndex | null = null;
  private search = el("input", "help-search") as HTMLInputElement;
  private body = el("div", "help-body");
  private current: string | null = null;

  constructor(readonly root: HTMLElement, private host: HelpHost, private load: () => Promise<HelpIndex>) {
    root.classList.add("help");
    this.search.type = "search";
    this.search.placeholder = "Search commands and examples…";
    this.search.addEventListener("input", () => {
      this.current = null;
      this.render();
    });
    this.search.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        const first = this.body.querySelector<HTMLElement>("[data-cmd], .help-example button");
        first?.click();
      }
    });
    root.append(this.search, this.body);
  }

  async show(topic: string | null = null) {
    if (!this.index) this.index = await this.load();
    this.current = topic;
    if (topic) this.search.value = "";
    this.render();
    if (!topic) this.search.focus();
  }

  /** Called when commands may have changed (new session). */
  invalidate() {
    this.index = null;
  }

  private render() {
    const idx = this.index;
    this.body.replaceChildren();
    if (!idx) return;
    if (this.current) return this.renderCommand(this.current);
    const q = this.search.value.trim();
    if (q) return this.renderSearch(q);
    const intro = el("p", "help-intro");
    intro.innerHTML = "Search above, or browse. <kbd>Cmd/Ctrl+K</kbd> searches commands, examples, nodes and values from anywhere; <code>help(name)</code> in the console shows one command.";
    this.body.append(intro);
    const ex = el("details", "help-group");
    ex.open = true;
    ex.append(el("summary", "", "Examples"));
    const exGroups = [...new Set(idx.examples.map((e) => e.group))];
    for (const g of exGroups) {
      const d = el("details", "help-subgroup");
      d.append(el("summary", "", g));
      for (const e of idx.examples.filter((x) => x.group === g)) d.append(this.example(e));
      ex.append(d);
    }
    this.body.append(ex);
    const cmds = el("details", "help-group");
    cmds.append(el("summary", "", `Commands (${idx.commands.length})`));
    for (const g of idx.groups) {
      const list = idx.commands.filter((c) => c.group === g);
      if (!list.length) continue;
      const d = el("details", "help-subgroup");
      d.append(el("summary", "", `${g} (${list.length})`));
      for (const c of list) d.append(this.commandLink(c));
      cmds.append(d);
    }
    this.body.append(cmds);
  }

  private renderSearch(q: string) {
    const idx = this.index!;
    const cmds = idx.commands
      .map((c) => ({ c, s: Math.max(fuzzy(q, c.name) * 2, c.doc.toLowerCase().includes(q.toLowerCase()) ? 300 : -1) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 25);
    const exs = idx.examples
      .map((e) => ({ e, s: Math.max(fuzzy(q, e.title), fuzzy(q, e.tags) - 50, e.code.toLowerCase().includes(q.toLowerCase()) ? 400 : -1) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 12);
    if (!cmds.length && !exs.length) {
      this.body.append(el("p", "help-intro", `Nothing matches “${q}”.`));
      return;
    }
    if (cmds.length) {
      this.body.append(el("h4", "", "Commands"));
      for (const { c } of cmds) this.body.append(this.commandLink(c, true));
    }
    if (exs.length) {
      this.body.append(el("h4", "", "Examples"));
      for (const { e } of exs) this.body.append(this.example(e));
    }
  }

  private renderCommand(name: string) {
    const idx = this.index!;
    const c = idx.commands.find((x) => x.name === name);
    const back = el("button", "help-back", "← All help");
    back.onclick = () => {
      this.current = null;
      this.render();
    };
    this.body.append(back);
    if (!c) {
      this.body.append(el("p", "help-intro", `No command named ${name}.`));
      return;
    }
    this.body.append(el("div", "help-group-name", c.group));
    this.body.append(codeBlock(c.sig));
    this.body.append(el("div", "help-doc", c.doc || "(no description)"));
    const act = el("div", "help-actions");
    const ins = el("button", "", "Insert");
    ins.onclick = () => this.host.insert(`${c.name}(`);
    act.append(ins);
    this.body.append(act);
    const related = idx.examples.filter((e) => new RegExp(`\\b${c.name}\\b`).test(e.code));
    if (related.length) {
      this.body.append(el("h4", "", "Examples"));
      for (const e of related) this.body.append(this.example(e));
    }
    const sameGroup = idx.commands.filter((x) => x.group === c.group && x.name !== c.name).slice(0, 30);
    if (sameGroup.length) {
      this.body.append(el("h4", "", "Related commands"));
      const wrap = el("div", "help-related");
      for (const x of sameGroup) wrap.append(this.commandLink(x, false, true));
      this.body.append(wrap);
    }
  }

  private commandLink(c: HelpCommand, withDoc = false, compact = false): HTMLElement {
    const b = el("button", compact ? "help-cmd compact" : "help-cmd");
    b.dataset.cmd = c.name;
    b.append(el("code", "", compact ? c.name : c.sig));
    if (!compact) b.append(el("span", "help-cmd-doc", (withDoc ? c.doc : c.doc).split("\n")[0]));
    b.onclick = () => {
      this.current = c.name;
      this.render();
      this.root.scrollTop = 0;
    };
    return b;
  }

  private example(e: HelpExample): HTMLElement {
    const box = el("div", "help-example");
    const head = el("div", "help-example-head");
    head.append(el("span", "", e.title));
    const ins = el("button", "", "Insert");
    ins.title = "Put this code in the working cell";
    ins.onclick = () => this.host.insert(e.code);
    const run = el("button", "", "Run");
    run.onclick = () => this.host.run(e.code);
    head.append(ins, run);
    box.append(head, codeBlock(e.code));
    return box;
  }
}
