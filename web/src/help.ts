// Help browser: searchable commands (signature + docstring) and curated examples.
// Examples insert into the working cell or run directly.
import { classHighlighter, highlightCode } from "@lezer/highlight";
import { pythonLanguage } from "@codemirror/lang-python";
import { GESTURE_SECTIONS, type Gesture } from "./gestures";

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
  private tabs = el("div", "help-tabs");

  constructor(readonly root: HTMLElement, private host: HelpHost, private load: () => Promise<HelpIndex>) {
    root.classList.add("help");
    this.search.type = "search";
    this.search.placeholder = "Search commands and examples…";
    this.search.addEventListener("input", () => {
      // searching inside the gestures guide filters its cards
      if (!this.current?.startsWith("gestures")) this.current = null;
      this.render();
    });
    this.search.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        const first = this.body.querySelector<HTMLElement>("[data-cmd], .help-example button");
        first?.click();
      }
    });
    // two kinds of help: the language (commands, examples) and the mouse (gestures)
    this.tabs.setAttribute("role", "tablist");
    for (const [id, label] of [["commands", "Commands & examples"], ["gestures", "Mouse & gestures"]]) {
      const b = el("button", "", label);
      b.dataset.tab = id;
      b.setAttribute("role", "tab");
      b.onclick = () => {
        this.current = id === "gestures" ? "gestures" : null;
        this.search.value = "";
        this.render();
      };
      this.tabs.append(b);
    }
    root.append(this.tabs, this.search, this.body);
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
    const gestures = !!this.current?.startsWith("gestures");
    for (const b of this.tabs.querySelectorAll<HTMLElement>("button")) {
      b.setAttribute("aria-selected", String((b.dataset.tab === "gestures") === gestures));
    }
    this.search.placeholder = gestures ? "Search gestures…" : "Search commands and examples…";
    const idx = this.index;
    this.body.replaceChildren();
    if (!idx) return;
    if (this.current === "gestures" || this.current?.startsWith("gestures:")) return this.renderGestures(this.current.split(":")[1]);
    if (this.current) return this.renderCommand(this.current);
    const q = this.search.value.trim();
    if (q) return this.renderSearch(q);
    const intro = el("p", "help-intro");
    intro.innerHTML = "Search above, or browse. <kbd>Cmd/Ctrl+K</kbd> searches commands, examples, nodes and values from anywhere; <code>help(name)</code> in the console shows one command.";
    const guide = el("button", "help-guide-link");
    guide.innerHTML = "<strong>Mouse and gestures</strong><span>selecting, dragging with meaning, click tools, panels — with pictures</span>";
    guide.onclick = () => {
      this.current = "gestures";
      this.render();
    };
    this.body.append(intro, guide);
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

  /** The illustrated guide to direct manipulation; `focus` scrolls to one card. */
  private renderGestures(focus?: string) {
    this.body.append(el("p", "help-intro", "Everything you do with the mouse also appears as Gython in the console, so it can be read, undone (Cmd/Ctrl+Z) and run again."));
    const q = this.search.value.trim().toLowerCase();
    let target: HTMLElement | null = null;
    for (const sec of GESTURE_SECTIONS) {
      const items = sec.items.filter((g) => !q || `${g.title} ${g.how} ${g.what} ${g.when ?? ""}`.toLowerCase().includes(q));
      if (!items.length) continue;
      this.body.append(el("h4", "", sec.title));
      for (const g of items) {
        const card = this.gestureCard(g);
        if (g.id === focus) {
          card.classList.add("flash");
          target = card;
        }
        this.body.append(card);
      }
    }
    if (target) requestAnimationFrame(() => target!.scrollIntoView({ block: "start", behavior: "smooth" }));
  }

  private gestureCard(g: Gesture): HTMLElement {
    const card = el("section", "gesture");
    card.id = `gesture-${g.id}`;
    card.append(el("div", "gesture-title", g.title));
    if (g.when) card.append(el("div", "gesture-when", g.when));
    if (g.img) {
      const img = el("img", "gesture-img") as HTMLImageElement;
      img.src = `help/${g.img}.png`;
      img.alt = g.title;
      img.loading = "lazy";
      card.append(img);
    }
    const how = el("div", "gesture-how");
    how.append(el("span", "gesture-label", "Do"), document.createTextNode(g.how));
    const what = el("div", "gesture-what");
    what.append(el("span", "gesture-label", "Then"), document.createTextNode(g.what));
    card.append(how, what);
    return card;
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
