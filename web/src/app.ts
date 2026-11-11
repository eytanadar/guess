// Apps: the window's menu bar, toolbar, status bar, title, console and region
// sizes, as an app's script arranges them (ui.menubar, ui.toolbar, ui.statusbar,
// ui.title, ui.console, ui.layout). Built-in actions reuse the page's own menu
// items and tool buttons, so they behave exactly as they do in GUESS.
import { pythonLanguage } from "@codemirror/lang-python";
import { classHighlighter, highlightCode } from "@lezer/highlight";
import type { BarItem, WidgetRec } from "./protocol";
import type { Dock } from "./dock";

/** A file an app is made of, for "Source". */
export interface AppFile { name: string; text: string }

export interface AppHost {
  dock: Dock;
  /** a widget event for Python (a menu item or toolbar button was clicked) */
  event(target: string, name: string, value: unknown): void;
  /** run Gython as a command (MenuItem(run=…), the "fit" action) */
  run(code: string): void;
  /** wire a menu so it opens and closes like the built-in ones */
  wireMenu(root: HTMLElement): void;
}

/** Built-in actions: the page element that does each one. */
export const ACTIONS: Record<string, string> = {
  open: "#open", save: "#save", png: "#png", svg: "#svg", sample: "#sample",
  "share-link": "#share-link", "share-viewer": "#share-viewer",
  table: "#btn-table", style: "#btn-style", filter: "#btn-filter", variables: "#btn-vars",
  help: "#btn-help", history: "#btn-history", search: "#search", stop: "#stop",
  tour: '[data-run="demo()"]', manual: "#btn-manual", source: "#app-source",
};

const $ = (sel: string) => document.querySelector<HTMLElement>(sel);

/** The visible text of a button (without its shortcut). */
function labelOf(el: HTMLElement): string {
  return [...el.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent).join("").trim()
    || el.textContent?.trim() || "";
}

export class AppChrome {
  private toolsHome: Comment | null = null;
  private customMenus: HTMLElement[] = [];
  private files: AppFile[] = [];
  consoleMode: "hidden" | "toggle" | "shown" = "shown";

  constructor(private host: AppHost) {
    $("#app-source")?.addEventListener("click", () => this.showSource());
    document.addEventListener("keydown", (ev) => {
      if (this.consoleMode === "toggle" && ev.ctrlKey && ev.key === "`") {
        ev.preventDefault();
        document.body.classList.toggle("console-hidden");
      }
    });
  }

  /** A button for a built-in action ("open", "tool:lens", "fit", "tools", …). */
  private action(name: string, text?: string): HTMLElement {
    if (name === "tools") {
      const group = $(".toolgroup");
      if (!group) return document.createElement("span");
      if (!this.toolsHome) {
        this.toolsHome = document.createComment("tools");
        group.before(this.toolsHome);
      }
      return group;
    }
    const b = document.createElement("button");
    b.dataset.action = name;
    if (name === "fit") {
      b.textContent = text ?? "Fit";
      b.title = "Show the whole graph";
      b.onclick = () => this.host.run("center()");
      return b;
    }
    const src = name.startsWith("tool:") ? $(`[data-tool="${name.slice(5)}"]`) : $(ACTIONS[name] ?? "");
    if (!src) {
      b.textContent = text ?? name;
      b.disabled = true;
      return b;
    }
    b.textContent = text ?? labelOf(src);
    b.title = src.title;
    b.onclick = () => src.click();
    // mirror pressed and disabled states (tools, panel toggles, Stop)
    const sync = () => {
      const pressed = src.getAttribute("aria-pressed");
      if (pressed !== null) b.setAttribute("aria-pressed", pressed);
      b.disabled = (src as HTMLButtonElement).disabled;
    };
    sync();
    new MutationObserver(sync).observe(src, { attributes: true, attributeFilter: ["aria-pressed", "disabled"] });
    return b;
  }

  private item(it: BarItem, inMenu = false): HTMLElement {
    if (it.kind === "sep") {
      return document.createElement(inMenu ? "hr" : "span");
    }
    if (it.kind === "action") {
      const el = this.action((it as { name: string }).name, (it as { text?: string }).text);
      if (inMenu) el.setAttribute("role", "menuitem");
      return el;
    }
    const w = it as WidgetRec;
    if (w.kind === "menuitem") {
      const b = this.host.dock.makeWidget(w) as HTMLButtonElement;
      const run = w.props.run as string | null;
      b.onclick = () => {
        if (run) this.host.run(run);
        this.host.event(w.id, "click", null);
      };
      if (inMenu) b.setAttribute("role", "menuitem");
      if (w.props.shortcut) {
        const k = document.createElement("kbd");
        k.textContent = String(w.props.shortcut);
        b.append(k);
      }
      return b;
    }
    return this.host.dock.makeWidget(w);
  }

  private fill(bar: HTMLElement, items: BarItem[]) {
    // the tool strip goes home before the bar is rebuilt
    const group = $(".toolgroup");
    if (group && this.toolsHome && bar.contains(group)) this.toolsHome.after(group);
    bar.replaceChildren(...items.map((it) => {
      const el = this.item(it);
      if (it.kind === "sep") el.className = "bar-sep";
      return el;
    }));
    bar.hidden = items.length === 0;
  }

  toolbar(items: BarItem[]) {
    this.fill($("#app-toolbar")!, items);
    document.body.classList.toggle("has-app-toolbar", items.length > 0);
  }

  statusbar(items: BarItem[]) {
    this.fill($("#app-statusbar")!, items);
  }

  menubar(menus: { title: string; items: BarItem[] }[], keep: string[]) {
    const nav = $(".menubar")!;
    for (const m of this.customMenus) m.remove();
    this.customMenus = [];
    const wanted = new Set(keep.map((k) => k.toLowerCase()));
    const builtIn = [...nav.querySelectorAll<HTMLElement>(":scope > .menu-root")];
    for (const r of builtIn) {
      const t = r.querySelector(".menu-title")?.textContent?.trim().toLowerCase() ?? "";
      r.hidden = !wanted.has(t);
    }
    const first = builtIn.find((r) => !r.hidden) ?? null;
    for (const m of menus) {
      const root = document.createElement("div");
      root.className = "menu-root app-menu";
      const title = document.createElement("button");
      title.className = "menu-title";
      title.setAttribute("aria-haspopup", "menu");
      title.setAttribute("aria-expanded", "false");
      title.textContent = m.title;
      const pop = document.createElement("div");
      pop.className = "menu-pop";
      pop.setAttribute("role", "menu");
      pop.hidden = true;
      pop.append(...m.items.map((it) => this.item(it, true)));
      root.append(title, pop);
      nav.insertBefore(root, first);
      this.host.wireMenu(root);
      this.customMenus.push(root);
    }
    document.body.classList.toggle("no-menus", !menus.length && !wanted.size);
  }

  /** The files the app was built from; shows the Source button. */
  setSource(files: AppFile[], show: boolean) {
    this.files = files;
    const b = $("#app-source");
    if (b) b.hidden = !show || !files.length;
  }

  /** A dialog with the app's script (highlighted) and manifest. */
  showSource(which = 0) {
    if (!this.files.length) return;
    const dlg = document.createElement("dialog");
    dlg.className = "source-dialog";
    const head = document.createElement("div");
    head.className = "source-head";
    const h = document.createElement("h3");
    h.textContent = `How ${document.title} is built`;
    const tabs = document.createElement("div");
    tabs.className = "w-tabbar";
    tabs.setAttribute("role", "tablist");
    const pre = document.createElement("pre");
    pre.className = "source-code";
    const note = document.createElement("p");
    note.className = "source-note";
    note.textContent = "An app is a manifest and a Gython script that arranges GUESS's window (ui.layout, ui.menubar, …). " +
      "Copy it to start your own; the manual's Apps section explains each part.";
    let current = which;
    const show = (k: number) => {
      current = k;
      for (const [i, b] of [...tabs.children].entries()) b.setAttribute("aria-selected", String(i === k));
      const f = this.files[k];
      pre.replaceChildren();
      if (/\.py$/.test(f.name)) {
        const tree = pythonLanguage.parser.parse(f.text);
        highlightCode(f.text, tree, classHighlighter, (text, classes) => {
          const span = document.createElement("span");
          if (classes) span.className = classes;
          span.textContent = text;
          pre.append(span);
        }, () => pre.append("\n"));
      } else {
        pre.textContent = f.text;
      }
      pre.scrollTop = 0;
    };
    this.files.forEach((f, i) => {
      const b = document.createElement("button");
      b.setAttribute("role", "tab");
      b.textContent = f.name;
      b.onclick = () => show(i);
      tabs.append(b);
    });
    const actions = document.createElement("div");
    actions.className = "source-actions";
    const copy = document.createElement("button");
    copy.textContent = "Copy";
    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(this.files[current].text);
        copy.textContent = "Copied";
      } catch {
        copy.textContent = "Copy failed";
      }
      setTimeout(() => (copy.textContent = "Copy"), 1500);
    };
    const save = document.createElement("button");
    save.textContent = "Download";
    save.onclick = () => {
      const f = this.files[current];
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([f.text], { type: "text/plain" }));
      a.download = f.name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    };
    const close = document.createElement("button");
    close.className = "primary";
    close.textContent = "Close";
    close.onclick = () => dlg.close();
    actions.append(copy, save, close);
    head.append(h, tabs);
    dlg.append(head, note, pre, actions);
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    show(which);
    dlg.showModal();
  }

  title(text: string, subtitle: string | null) {
    const brand = $(".brand")!;
    brand.textContent = text;
    if (subtitle) {
      const s = document.createElement("span");
      s.className = "brand-sub";
      s.textContent = subtitle;
      brand.append(s);
    }
    document.title = text;
  }

  console(mode: "hidden" | "toggle" | "shown") {
    this.consoleMode = mode;
    document.body.classList.toggle("console-hidden", mode !== "shown");
  }

  /** Region sizes (px) and drag handles on the region edges. */
  regions(sizes: Record<string, number>) {
    for (const [where, size] of Object.entries(sizes)) {
      const el = $(`#dock-${where}`);
      if (!el || !(size > 0)) continue;
      if (where === "bottom") {
        el.style.height = `${size}px`;
        el.classList.add("sized-bottom");
      } else {
        el.style.flex = `0 0 ${size}px`;
      }
    }
    for (const where of ["left", "right", "bottom"]) {
      const el = $(`#dock-${where}`);
      if (!el || el.querySelector(":scope > .region-resize")) continue;
      const h = document.createElement("div");
      h.className = "region-resize";
      h.title = "Drag to resize";
      h.addEventListener("pointerdown", (ev) => {
        ev.preventDefault();
        h.setPointerCapture(ev.pointerId);
        h.classList.add("dragging");
        const r0 = el.getBoundingClientRect();
        const x0 = ev.clientX, y0 = ev.clientY;
        const move = (e: PointerEvent) => {
          if (where === "bottom") {
            el.style.height = `${Math.max(60, r0.height - (e.clientY - y0))}px`;
            el.classList.add("sized-bottom");
          } else {
            const w = where === "left" ? r0.width + (e.clientX - x0) : r0.width - (e.clientX - x0);
            el.style.flex = `0 0 ${Math.max(160, Math.min(window.innerWidth * 0.6, w))}px`;
          }
          window.dispatchEvent(new Event("resize"));
        };
        const up = () => {
          h.classList.remove("dragging");
          h.removeEventListener("pointermove", move);
          h.removeEventListener("pointerup", up);
        };
        h.addEventListener("pointermove", move);
        h.addEventListener("pointerup", up);
      });
      el.prepend(h);
    }
  }
}

/** An app's manifest (?app=<url>). */
export interface AppManifest {
  "guess-app"?: number;
  name?: string;
  description?: string;
  /** "hidden" (default), "toggle" (Ctrl+` shows it) or "shown" */
  console?: "hidden" | "toggle" | "shown";
  theme?: "light" | "dark" | "auto";
  /** files fetched into the session's folder before the script runs (relative to the manifest) */
  data?: string[];
  /** the script: a file (relative to the manifest) */
  script?: string;
  /** or the code itself */
  code?: string;
  /** false: no Source button (the files the app is built from) */
  source?: boolean;
}
