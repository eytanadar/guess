// The guided tour (demo()): one step at a time in a panel below the graph.
// Each step explains an idea, shows its code, and runs it as an ordinary
// console cell; after it runs, a note says what to look for.
import type { Dock } from "./dock";

export interface TourStep {
  level: string;
  title: string;
  text: string;
  code: string;
  notice: string;
}

export interface TourHost {
  /** run code as a console cell; resolves with success */
  run(code: string): Promise<boolean>;
  /** put code in the working cell to edit before running */
  edit(code: string): void;
}

const ID = "tour";

/** `code` and *emphasis* in a step's text. */
function rich(text: string): DocumentFragment {
  const f = document.createDocumentFragment();
  for (const part of text.split(/(`[^`]+`|\*[^*]+\*)/)) {
    if (!part) continue;
    if (part.startsWith("`") && part.endsWith("`")) {
      const c = document.createElement("code");
      c.textContent = part.slice(1, -1);
      f.append(c);
    } else if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      const e = document.createElement("em");
      e.textContent = part.slice(1, -1);
      f.append(e);
    } else {
      f.append(part);
    }
  }
  return f;
}

export class Tour {
  private steps: TourStep[] = [];
  private at = 0;
  private ran = new Set<number>();
  private body: HTMLElement | null = null;
  private running = false;

  constructor(private dock: Dock, private host: TourHost) {}

  start(steps: TourStep[], at: number) {
    this.steps = steps;
    this.at = Math.max(0, Math.min(steps.length - 1, at));
    if (!this.body || !this.dock.has(ID)) {
      this.body = this.dock.pane(ID, "Tour", "bottom", () => (this.body = null));
      this.body.classList.add("tour-body");
    }
    this.render();
  }

  private go(i: number) {
    this.at = Math.max(0, Math.min(this.steps.length - 1, i));
    this.render();
  }

  private async runStep() {
    if (this.running) return;
    const i = this.at;
    this.running = true;
    this.render();
    try {
      if (await this.host.run(this.steps[i].code)) this.ran.add(i);
    } finally {
      this.running = false;
      if (this.at === i) this.render();
    }
  }

  private render() {
    const body = this.body;
    if (!body) return;
    const s = this.steps[this.at];
    const n = this.steps.length;

    // progress: one segment per step, grouped by level; click to jump
    const bar = document.createElement("div");
    bar.className = "tour-progress";
    let level = "";
    this.steps.forEach((st, i) => {
      if (st.level !== level) {
        level = st.level;
        const l = document.createElement("button");
        l.className = "tour-level-jump";
        l.textContent = level;
        l.title = `Jump to the first ${level.toLowerCase()} step`;
        l.onclick = () => this.go(i);
        bar.append(l);
      }
      const dot = document.createElement("button");
      dot.className = "tour-dot" + (i === this.at ? " current" : "") + (this.ran.has(i) ? " done" : "");
      dot.title = `${i + 1}. ${st.title}`;
      dot.setAttribute("aria-label", dot.title);
      dot.onclick = () => this.go(i);
      bar.append(dot);
    });

    const head = document.createElement("div");
    head.className = "tour-head";
    const chip = document.createElement("span");
    chip.className = `tour-chip ${s.level.toLowerCase()}`;
    chip.textContent = s.level;
    const title = document.createElement("strong");
    title.textContent = `${this.at + 1}. ${s.title}`;
    head.append(chip, title);

    const text = document.createElement("p");
    text.className = "tour-text";
    text.append(rich(s.text));

    const code = document.createElement("pre");
    code.className = "tour-code";
    code.textContent = s.code;

    const buttons = document.createElement("div");
    buttons.className = "tour-buttons";
    const back = document.createElement("button");
    back.textContent = "◂ Back";
    back.disabled = this.at === 0;
    back.onclick = () => this.go(this.at - 1);
    const run = document.createElement("button");
    run.className = "primary tour-run";
    run.textContent = this.running ? "Running…" : this.ran.has(this.at) ? "Run again" : "Run it";
    run.disabled = this.running;
    run.onclick = () => void this.runStep();
    const edit = document.createElement("button");
    edit.textContent = "Edit first";
    edit.title = "Put the code in the console to change it before running";
    edit.onclick = () => this.host.edit(s.code);
    const next = document.createElement("button");
    next.className = "tour-next";
    next.textContent = this.at === n - 1 ? "Finish" : "Next ▸";
    next.onclick = () => (this.at === n - 1 ? this.dock.close(ID) : this.go(this.at + 1));
    const count = document.createElement("span");
    count.className = "tour-count";
    count.textContent = `${this.at + 1} / ${n}`;
    buttons.append(back, run, edit, next, count);

    const left = document.createElement("div");
    left.className = "tour-left";
    left.append(head, text);
    if (this.ran.has(this.at)) {
      const note = document.createElement("p");
      note.className = "tour-notice";
      note.append(rich(s.notice));
      left.append(note);
    }
    const right = document.createElement("div");
    right.className = "tour-right";
    right.append(code, buttons);
    const main = document.createElement("div");
    main.className = "tour-main";
    main.append(left, right);
    body.replaceChildren(bar, main);
  }
}
