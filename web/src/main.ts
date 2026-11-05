import "./style.css";
import { Console, groupTip, type Item } from "./console";
import type { FromWorker, Info, LegendRec, ToWorker } from "./protocol";
import { Renderer, type Hit } from "./renderer";
import { Dock } from "./dock";
import * as store from "./store";
import sampleGdf from "../../guess-orig/sample.gdf?raw";

// The Python package, shipped into the worker's virtual filesystem.
const pyFiles = import.meta.glob("../../py/guess/*.py", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

const $ = <T extends HTMLElement>(sel: string) => document.querySelector(sel) as T;

// ?load=<url> opens a graph or session file; &app=1 hides the console (applet-style deployment)
const params = new URLSearchParams(location.search);
const appMode = params.get("app") === "1";
const loadUrl = params.get("load");
if (appMode) document.body.classList.add("app");

// ---- worker plumbing ----------------------------------------------------------
const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
let nextId = 1;
const pending = new Map<number, (v: any) => void>();
const interruptBuf = typeof SharedArrayBuffer !== "undefined" && crossOriginIsolated ? new SharedArrayBuffer(1) : undefined;

function send(msg: ToWorker) {
  worker.postMessage(msg);
}

function request<T>(build: (id: number) => ToWorker): Promise<T> {
  const id = nextId++;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    send(build(id));
  });
}

// ---- UI --------------------------------------------------------------------------
const pendingMoves: number[] = [];
let themeReady: () => void = () => {};
const status = $("#status");
const tip = $("#tip");
const menu = $("#menu");

const renderer = new Renderer($("#graph"), {
  hover: (hit, x, y) => onGraphHover(hit, x, y),
  context: (hit, x, y) => {
    // right-clicking a selected node acts on the whole selection
    if (hit?.kind === "n" && renderer.selection.has(hit.id) && renderer.selection.size > 1) {
      openMenu([...renderer.selection].map((id) => ["n", id] as Item), x, y);
    } else if (hit) openMenu([[hit.kind, hit.id]], x, y);
  },
  moved: (ident, x, y) => {
    // a group drag reports each node in turn; send them as one move (one undo step)
    if (!pendingMoves.length) queueMicrotask(() => {
      send({ type: "move", moves: pendingMoves.splice(0) });
      scheduleAutosave();
    });
    pendingMoves.push(ident, x, y);
  },
  click: (hit, shift) => onGraphClick(hit, shift),
  selected: (ids) => syncSelection(ids),
});

/** Tell Python about a selection made on the display (bound to `sel`). */
function syncSelection(ids: number[]) {
  send({ type: "select", nodes: ids });
  status.textContent = ids.length ? `${ids.length} selected — sel in the console` : "";
}

// ---- click tools (Gephi's toolbar: neighbourhood highlight, shortest path, heat map, painter) ----
type Tool = "select" | "path" | "heat" | "paint";
let tool: Tool = "select";
let pathStart: number | null = null;
const paintColor = $<HTMLInputElement>("#paint-color");
const PY_KEYWORDS = new Set(["False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield"]);

/** Gython that refers to a node: its name when that is a plain identifier. */
function nodeExpr(id: number): string {
  const name = renderer.nodes.get(id)?.name ?? "";
  return /^[A-Za-z_]\w*$/.test(name) && !PY_KEYWORDS.has(name) ? name : `g.getNodeByName(${JSON.stringify(name)})`;
}

function setTool(t: Tool) {
  tool = t;
  pathStart = null;
  renderer.setFocus(null);
  for (const b of document.querySelectorAll<HTMLButtonElement>("[data-tool]")) b.setAttribute("aria-pressed", String(b.dataset.tool === t));
  $("#graph").dataset.tool = t;
  status.textContent = { select: "", path: "Path: click the first node", heat: "Heat map: click a node", paint: "Paint: click nodes (shift-click: with neighbours)" }[t];
}

for (const b of document.querySelectorAll<HTMLButtonElement>("[data-tool]")) b.addEventListener("click", () => setTool(b.dataset.tool as Tool));

function onGraphClick(hit: Hit, shift: boolean) {
  if (tool !== "select") {
    if (hit?.kind !== "n") return;
    const c = JSON.stringify(paintColor.value);
    if (tool === "path") {
      if (pathStart === null || pathStart === hit.id) {
        pathStart = hit.id;
        renderer.setFocus(hit.id);
        status.textContent = `Path from ${renderer.nodes.get(hit.id)?.name}: click the target node`;
      } else {
        const from = pathStart;
        pathStart = null;
        renderer.setFocus(null);
        status.textContent = "Path: click the first node";
        term.submit(`shortestPath(${nodeExpr(from)}, ${nodeExpr(hit.id)}).color = ${c}`);
      }
    } else if (tool === "heat") {
      term.submit(`heatMap(${nodeExpr(hit.id)})`);
    } else {
      term.submit(`paint(${nodeExpr(hit.id)}, ${c}${shift ? ", 1" : ""})`);
    }
    return;
  }
  if (hit) {
    const name = `${shift ? "shiftClick" : "click"}${hit.kind === "n" ? "Node" : "Edge"}`;
    if (graphEvents.has(name)) {
      uiEvent("graph", name, [hit.kind, hit.id]);
      return;
    }
  }
  if (shift && hit?.kind === "n") {
    syncSelection(renderer.toggleSelected(hit.id));
    return;
  }
  if (!hit && renderer.selection.size) {
    renderer.setSelection([]);
    syncSelection([]);
  }
  if (!defaultHighlight) return;
  // clicking a node keeps its neighbourhood bright and dims the rest; click it again or the background to clear
  if (hit?.kind === "n") renderer.setFocus(renderer.focused === hit.id ? null : hit.id);
  else if (!hit) renderer.setFocus(null);
}

// ---- Python-defined UI: panels, charts, timers, graph events ------------------------
const graphEvents = new Set<string>();
let defaultHighlight = true;
const timers = new Map<string, number>();
const timerBusy = new Set<string>();

async function uiEvent(target: string, name: string, value: unknown): Promise<unknown> {
  const r = await request((id) => ({ type: "event", id, target, name, value: JSON.stringify(value ?? null) }));
  scheduleAutosave();
  return r;
}

// ---- autosave (IndexedDB) -------------------------------------------------------------
let saveTimer = 0;
let savedRevision = -1;
function scheduleAutosave() {
  if (appMode) return;
  clearTimeout(saveTimer);
  saveTimer = window.setTimeout(async () => {
    const r = await request<[number, string] | null>((id) => ({ type: "snapshot", id, since: savedRevision }));
    if (!r) return;
    savedRevision = r[0];
    await store.set("autosave", r[1]);
  }, 2000);
}

const dock = new Dock($("#dock-bottom"), $("#dock-right"), {
  event: (target, name, value) => void uiEvent(target, name, value),
  hover: (items, title, lines, ev) => {
    if (!items || !ev) {
      highlightItems(null);
      hideTip();
      return;
    }
    highlightItems(items, false);
    tipToken++;
    showTip(title, lines, ev.clientX, ev.clientY);
  },
});

/** Highlight elements in the graph and any linked charts. */
function highlightItems(items: Item[] | null, charts = true) {
  const list = items ?? [];
  renderer.highlight(list.filter((i) => i[0] === "n").map((i) => i[1]),
                     list.filter((i) => i[0] === "e").map((i) => i[1]));
  if (charts) dock.highlight(items);
}

function onUi(m: Extract<FromWorker, { type: "ui" }>) {
  switch (m.op) {
    case "dock": dock.dockPanel(m.panel); break;
    case "update": dock.update(m.id, m.props); break;
    case "close": dock.close(m.id); break;
    case "events":
      graphEvents.clear();
      m.enabled.forEach((e) => graphEvents.add(e));
      defaultHighlight = m.defaults.highlight;
      renderer.zoomOnDoubleClick = m.defaults.zoom;
      break;
    case "status": status.textContent = m.text; break;
    case "open": window.open(m.url, "_blank", "noopener"); break;
    case "timer": {
      clearTimer(m.id);
      const fire = async () => {
        if (timerBusy.has(m.id)) return; // never queue up behind a slow handler
        timerBusy.add(m.id);
        try { await uiEvent(m.id, "fire", null); } finally { timerBusy.delete(m.id); }
      };
      timers.set(m.id, m.repeat ? window.setInterval(fire, m.ms) : window.setTimeout(fire, m.ms));
      break;
    }
    case "cancelTimer": clearTimer(m.id); break;
  }
}

function clearTimer(id: string) {
  const t = timers.get(id);
  if (t !== undefined) {
    clearInterval(t);
    clearTimeout(t);
    timers.delete(id);
  }
}

const term = new Console($("#console"), {
  run: async (code) => {
    if (interruptBuf) new Uint8Array(interruptBuf)[0] = 0;
    const ok = await request<boolean>((id) => ({ type: "run", id, code }));
    scheduleAutosave();
    return ok;
  },
  completions: (text) => request((id) => ({ type: "completions", id, text })),
  doc: (name, ev) => {
    if (!name || !ev) {
      if (!lastConsoleEl) hideTip();
      return;
    }
    const [sig, ...rest] = (term.docs[name] || name).split("\n");
    tipToken++;
    showTip(sig, rest, ev.clientX, ev.clientY);
  },
  interrupt: () => {
    if (interruptBuf) new Uint8Array(interruptBuf)[0] = 2; // SIGINT
    else term.note("Interrupt is unavailable (page is not cross-origin isolated).");
  },
  hover: (items, el, ev) => onConsoleHover(items, el, ev),
  context: (items, ev) => openMenu(items, ev.clientX, ev.clientY),
  // clicking a node, edge or group in the output selects it (shift: adds) and shows it
  click: (items, ev) => {
    const nodes = new Set<number>(ev.shiftKey ? renderer.selection : []);
    for (const [k, id] of items) {
      if (k === "n") nodes.add(id);
      else {
        const e = renderer.edges.get(id);
        if (e) nodes.add(e.s).add(e.t);
      }
    }
    renderer.setSelection(nodes);
    syncSelection([...renderer.selection]);
    renderer.center(items.filter((i) => i[0] === "n").map((i) => i[1]), items.filter((i) => i[0] === "e").map((i) => i[1]));
  },
});

worker.onmessage = (ev: MessageEvent<FromWorker>) => {
  const m = ev.data;
  switch (m.type) {
    case "status":
      status.textContent = m.text;
      break;
    case "ready":
      status.textContent = "Ready";
      $("#stop").toggleAttribute("disabled", !m.interruptible);
      onReady();
      break;
    case "scene":
      if (renderer.selection.size) syncSelection([]);
      renderer.setScene(m.nodes, m.edges);
      requestAnimationFrame(() => renderer.center([], [], false));
      break;
    case "patch":
      renderer.applyPatch(m.nodes, m.edges, m.removedNodes, m.removedEdges, m.morph, m.pos);
      break;
    case "out":
      term.print(m.segs);
      break;
    case "text":
      term.text(m.text);
      break;
    case "error":
      term.error(m.text);
      break;
    case "center":
      renderer.center(m.nodes, m.edges);
      break;
    case "overlay":
      renderer.setOverlay(m);
      renderLegends(m.legends);
      $("#curved").setAttribute("aria-pressed", String(m.curvature > 0));
      break;
    case "export":
      exportView(m.format, m.name);
      break;
    case "ui":
      onUi(m);
      break;
    case "chart":
      dock.chart(m);
      break;
    case "movie":
      if (m.op === "start") startMovie(m.fps, m.name);
      else stopMovie();
      break;
    case "image":
      renderer.addImage(m.key, m.url);
      break;
    case "download":
      download(m.name, new Blob([m.text], { type: "text/plain" }));
      break;
    case "select":
      renderer.setSelection(m.nodes);
      status.textContent = m.nodes.length ? `${m.nodes.length} selected` : "";
      break;
    case "done":
    case "reply": {
      const resolve = pending.get(m.id);
      pending.delete(m.id);
      resolve?.(m.type === "done" ? m.ok : m.value);
      break;
    }
  }
};

// ---- hover / tooltips -----------------------------------------------------------
let tipToken = 0;

function showTip(title: string, lines: string[], x: number, y: number) {
  tip.replaceChildren();
  const h = document.createElement("div");
  h.className = "tip-title";
  h.textContent = title;
  tip.append(h);
  for (const l of lines) {
    const d = document.createElement("div");
    d.textContent = l;
    tip.append(d);
  }
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  const px = Math.min(x + 14, window.innerWidth - r.width - 8);
  const py = y + 16 + r.height > window.innerHeight ? y - r.height - 10 : y + 16;
  tip.style.transform = `translate(${Math.max(8, px)}px, ${Math.max(8, py)}px)`;
}

function hideTip() {
  tipToken++;
  tip.hidden = true;
}

async function describeTip(kind: "n" | "e", ident: number, x: number, y: number) {
  const token = ++tipToken;
  const info = await request<Info | null>((id) => ({ type: "describe", id, kind, ident }));
  if (token !== tipToken || !info) return;
  const rows = info.rows.filter(([k, v]) => v !== "" && !HIDDEN_ROWS.has(k));
  showTip(info.title, rows.map(([k, v]) => `${k}: ${v}`), x, y);
}

const HIDDEN_ROWS = new Set(["name", "image", "labelcolor", "strokecolor", "node1", "node2"]);

let lastGraphHit = "";
function onGraphHover(hit: Hit, x: number, y: number) {
  const key = hit ? `${hit.kind}${hit.id}` : "";
  if (key !== lastGraphHit) graphEnterLeave(lastGraphHit, key);
  if (!hit) {
    if (lastGraphHit) {
      highlightItems(null);
      hideTip();
      status.textContent = "";
    }
    lastGraphHit = "";
    return;
  }
  if (key === lastGraphHit) {
    if (!tip.hidden) showTipPosition(x, y);
    return;
  }
  lastGraphHit = key;
  if (defaultHighlight) highlightItems([[hit.kind, hit.id]]);
  else dock.highlight([[hit.kind, hit.id]]);
  const name = hit.kind === "n" ? renderer.nodes.get(hit.id)?.name : edgeName(hit.id);
  status.textContent = name ?? "";
  describeTip(hit.kind, hit.id, x, y);
}

function graphEnterLeave(prev: string, next: string) {
  const ev = (key: string, verb: string) => {
    const kind = key[0] as "n" | "e";
    const name = `${verb}${kind === "n" ? "Node" : "Edge"}`;
    if (graphEvents.has(name)) uiEvent("graph", name, [kind, Number(key.slice(1))]);
  };
  if (prev) ev(prev, "mouseLeave");
  if (next) ev(next, "mouseEnter");
}

function showTipPosition(x: number, y: number) {
  const r = tip.getBoundingClientRect();
  const px = Math.min(x + 14, window.innerWidth - r.width - 8);
  const py = y + 16 + r.height > window.innerHeight ? y - r.height - 10 : y + 16;
  tip.style.transform = `translate(${Math.max(8, px)}px, ${Math.max(8, py)}px)`;
}

function edgeName(id: number) {
  const e = renderer.edges.get(id);
  if (!e) return "";
  return `${renderer.nodes.get(e.s)?.name}${e.d ? "->" : "-"}${renderer.nodes.get(e.t)?.name}`;
}

let lastConsoleEl: HTMLElement | null = null;
function onConsoleHover(items: Item[] | null, el: HTMLElement | null, ev: MouseEvent | null) {
  if (!items || !el || !ev) {
    lastConsoleEl = null;
    highlightItems(null);
    hideTip();
    return;
  }
  if (el === lastConsoleEl) {
    showTipPosition(ev.clientX, ev.clientY);
    return;
  }
  lastConsoleEl = el;
  highlightItems(items);
  if (el.dataset.k === "g") {
    const t = groupTip(el);
    tipToken++;
    showTip(t.title, t.lines, ev.clientX, ev.clientY);
  } else {
    describeTip(el.dataset.k as "n" | "e", Number(el.dataset.id), ev.clientX, ev.clientY);
  }
}

// ---- context menu -------------------------------------------------------------------
const SWATCHES = ["red", "orange", "yellow", "green", "blue", "purple", "gray", "black", "cornflowerblue", "dandelion"];

async function targetExpr(items: Item[]): Promise<string> {
  const selIds = renderer.selection;
  if (items.length > 1 && items.length === selIds.size && items.every((i) => i[0] === "n" && selIds.has(i[1]))) return "sel";
  if (items.length === 1 && items[0][0] === "n") {
    const name = renderer.nodes.get(items[0][1])?.name ?? "";
    if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) return name;
  }
  await request((id) => ({ type: "assign", id, name: "_sel", items }));
  return "_sel";
}

function openMenu(items: Item[], x: number, y: number) {
  if (!items.length) return;
  hideTip();
  const nodes = items.filter((i) => i[0] === "n").length;
  const edges = items.length - nodes;
  menu.replaceChildren();
  const head = document.createElement("div");
  head.className = "menu-head";
  head.textContent = items.length === 1
    ? (nodes ? renderer.nodes.get(items[0][1])?.name ?? "" : edgeName(items[0][1]))
    : [nodes && `${nodes} nodes`, edges && `${edges} edges`].filter(Boolean).join(", ");
  menu.append(head);

  const act = (label: string, fn: () => unknown) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.onclick = async () => {
      closeMenu();
      await fn();
    };
    menu.append(b);
  };
  const runOn = (code: (t: string) => string) => async () => term.submit(code(await targetExpr(items)));

  const sw = document.createElement("div");
  sw.className = "swatches";
  for (const c of SWATCHES) {
    const b = document.createElement("button");
    b.title = c;
    b.style.background = c === "dandelion" ? "#fcd870" : c === "cornflowerblue" ? "#9ceefd" : c;
    b.onclick = async () => {
      closeMenu();
      await runOn((t) => `${t}.color = ${c}`)();
    };
    sw.append(b);
  }
  menu.append(sw);
  if (nodes) {
    act("Show labels", runOn((t) => `${t}.labelvisible = true`));
    act("Hide labels", runOn((t) => `${t}.labelvisible = false`));
    act("Size 5 / 10 / 20 …", async () => {
      const v = prompt("Node size", "15");
      if (v && !isNaN(Number(v))) await runOn((t) => `${t}.size = ${Number(v)}`)();
    });
    act("Style: circle", runOn((t) => `${t}.style = 2`));
    act("Style: square", runOn((t) => `${t}.style = 1`));
  }
  if (edges && !nodes) {
    act("Width…", async () => {
      const v = prompt("Edge width", "3");
      if (v && !isNaN(Number(v))) await runOn((t) => `${t}.width = ${Number(v)}`)();
    });
  }
  act("Hide", runOn((t) => `${t}.visible = false`));
  act("Center on", runOn((t) => `center(${t})`));
  act("Assign to variable…", async () => {
    const name = prompt("Variable name", "foo");
    if (!name) return;
    const res = await request<unknown>((id) => ({ type: "assign", id, name, items }));
    if (typeof res === "number") term.note(`${name} = ${res === 1 ? "1 item" : `${res} items`}`);
    else term.error(String(res));
  });

  menu.hidden = false;
  const r = menu.getBoundingClientRect();
  menu.style.left = `${Math.min(x, window.innerWidth - r.width - 8)}px`;
  menu.style.top = `${Math.min(y, window.innerHeight - r.height - 8)}px`;
}

function closeMenu() {
  menu.hidden = true;
}

document.addEventListener("pointerdown", (ev) => {
  if (!menu.hidden && !menu.contains(ev.target as Node)) closeMenu();
});
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Escape") return;
  closeMenu();
  if (!$("#console").contains(ev.target as Node)) {
    if (tool !== "select") setTool("select");
    else if (renderer.focused !== null) renderer.setFocus(null);
    else if (renderer.selection.size) {
      renderer.setSelection([]);
      syncSelection([]);
    }
  }
});

// ---- toolbar ------------------------------------------------------------------------
$("#open").addEventListener("click", () => $<HTMLInputElement>("#file").click());
$<HTMLInputElement>("#file").addEventListener("change", async (ev) => {
  const input = ev.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  input.value = "";
  for (const file of files) await openFile(file);
});

const LOADERS: [RegExp, string][] = [
  [/\.gdf$/i, "makeFromGDF"],
  [/\.(net|paj)$/i, "makeFromPajek"],
  [/\.(graphml|xml)$/i, "makeFromGML"],
  [/\.dl$/i, "makeFromDL"],
  [/\.gexf$/i, "makeFromGEXF"],
  [/\.(csv|tsv)$/i, "makeFromCSV"],
  [/\.py$/i, "execfile"],
  [/\.guess$/i, "makeFromSession"],
];

async function openFile(file: File) {
  const name = file.name.replace(/[^\w.\-]/g, "_");
  const data = new Uint8Array(await file.arrayBuffer());
  await request((id) => ({ type: "writeFile", id, name, data }));
  const loader = LOADERS.find(([re]) => re.test(name));
  if (loader) await term.submit(`${loader[1]}(${JSON.stringify(name)})`);
  else term.note(`Saved ${name} — use it by name, e.g. setBackgroundImage("${name}") or bob.image = "${name}"`);
}

// drag and drop files onto the page
document.addEventListener("dragover", (ev) => ev.preventDefault());
document.addEventListener("drop", async (ev) => {
  ev.preventDefault();
  for (const file of Array.from(ev.dataTransfer?.files ?? [])) await openFile(file);
});

// ---- legends ------------------------------------------------------------------------
const hex = (c: number) => "#" + c.toString(16).padStart(6, "0");

function renderLegends(legends: LegendRec[]) {
  const host = $("#legends");
  host.replaceChildren();
  for (const lg of legends) {
    if (!lg.entries.length && !lg.ramp) continue;
    const box = document.createElement("div");
    box.className = "legend";
    if (lg.ramp) {
      const bar = document.createElement("div");
      bar.className = "ramp";
      bar.style.background = `linear-gradient(to right, ${hex(lg.ramp.from)}, ${hex(lg.ramp.to)})`;
      const ends = document.createElement("div");
      ends.className = "ramp-ends";
      ends.innerHTML = "<span></span><span></span>";
      ends.children[0].textContent = String(lg.ramp.min);
      ends.children[1].textContent = String(lg.ramp.max);
      box.append(bar, ends);
    }
    for (const e of lg.entries) {
      const row = document.createElement("div");
      row.className = "legend-row";
      const sw = document.createElement("span");
      sw.className = `sw sw-${e.k}` + (e.k === "n" && (e.s === 2 || e.s === 5 || e.s === 9) ? " round" : "");
      sw.style.setProperty("--c", hex(e.c));
      sw.style.opacity = String(e.k === "h" ? Math.max(e.a, 0.35) : e.a);
      if (e.k === "e") sw.style.setProperty("--w", `${Math.min(Math.max(e.w ?? 2, 1), 8)}px`);
      const t = document.createElement("span");
      t.textContent = e.t;
      row.append(sw, t);
      box.append(row);
    }
    host.append(box);
  }
}

$("#sample").addEventListener("click", () => term.submit(`makeFromGDF("sample.gdf")`));
$("#save").addEventListener("click", () => term.submit(`saveSession("session.guess")`));
$("#curved").addEventListener("click", () => term.submit(`curvedEdges(${renderer.curvature > 0 ? "false" : "true"})`));
$("#center").addEventListener("click", () => renderer.center());
// ---- light / dark theme: Auto follows the system; the button cycles Auto -> Light -> Dark
{
  type Theme = "auto" | "light" | "dark";
  const KEY = "guess.theme";
  const btn = $("#theme");
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let theme: Theme = "auto";
  try {
    const t = localStorage.getItem(KEY);
    if (t === "light" || t === "dark") theme = t;
  } catch {
    /* storage unavailable */
  }
  const apply = () => {
    if (theme === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    const dark = theme === "dark" || (theme === "auto" && system.matches);
    renderer.setTheme(dark);
    btn.textContent = theme === "auto" ? "◐ Auto" : theme === "dark" ? "☾ Dark" : "☀ Light";
    btn.title = `Theme: ${theme} (click to change)`;
  };
  btn.addEventListener("click", () => {
    theme = theme === "auto" ? "light" : theme === "light" ? "dark" : "auto";
    try {
      if (theme === "auto") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, theme);
    } catch {
      /* storage unavailable */
    }
    apply();
  });
  system.addEventListener("change", apply);
  themeReady = apply;
}

$("#undo").addEventListener("click", () => term.submit("undo()"));
$("#redo").addEventListener("click", () => term.submit("redo()"));
// Cmd/Ctrl+Z (and Shift+Cmd/Ctrl+Z or Ctrl+Y) undo commands when the code cell isn't focused
document.addEventListener("keydown", (ev) => {
  const mod = ev.metaKey || ev.ctrlKey;
  if (!mod || ev.altKey) return;
  const t = ev.target as HTMLElement | null;
  if (t?.closest(".cm-editor, input, textarea, select, [contenteditable=true]")) return;
  const k = ev.key.toLowerCase();
  if (k === "z" || k === "y") {
    ev.preventDefault();
    term.submit(k === "y" || ev.shiftKey ? "redo()" : "undo()");
  }
});
$("#stop").addEventListener("click", () => {
  if (interruptBuf) new Uint8Array(interruptBuf)[0] = 2;
});
$("#png").addEventListener("click", () => exportView("png", "guess.png"));
$("#svg").addEventListener("click", () => exportView("svg", "guess.svg"));

async function exportView(format: "png" | "jpg" | "svg", name: string) {
  if (format === "svg") {
    download(name, new Blob([renderer.exportSVG()], { type: "image/svg+xml" }));
    return;
  }
  const a = document.createElement("a");
  a.href = await renderer.exportImage(format);
  a.download = name;
  a.click();
}

// ---- movies (startMovie / stopMovie) ---------------------------------------------------
let recorder: { rec: MediaRecorder; chunks: Blob[]; name: string } | null = null;

function startMovie(fps: number, name: string) {
  stopMovie(false);
  const canvas = renderer.app.canvas as HTMLCanvasElement;
  if (!canvas.captureStream || typeof MediaRecorder === "undefined") {
    term.error("This browser cannot record video.");
    return;
  }
  const type = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((t) => MediaRecorder.isTypeSupported(t));
  const rec = new MediaRecorder(canvas.captureStream(fps), type ? { mimeType: type } : undefined);
  const chunks: Blob[] = [];
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  recorder = { rec, chunks, name };
  rec.start(250);
  status.textContent = "● recording";
}

function stopMovie(save = true) {
  const r = recorder;
  if (!r) return;
  recorder = null;
  r.rec.onstop = () => {
    if (save) download(r.name, new Blob(r.chunks, { type: "video/webm" }));
    status.textContent = "";
  };
  r.rec.stop();
}

function download(name: string, blob: Blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ---- start --------------------------------------------------------------------------
async function onReady() {
  term.docs = await request<Record<string, string>>((id) => ({ type: "docs", id }));
  if (loadUrl) {
    await openUrl(loadUrl);
  } else if (await restoreAutosave()) {
    term.note("Restored your previous session (variables are not restored). Sample graph starts over.");
  } else {
    showWelcome();
    await term.submit(`makeFromGDF("sample.gdf")`);
  }
  term.focus();
}

function showWelcome() {
  term.note("GUESS — write Gython in the cell below and press Shift+Enter. Click an example to try it:");
  term.examples([
    "(freq > 100).color = red",
    "colorize(dept)",
    "groupBy(dept)",
    "v1 ? g.nodes",
    "gemLayout()",
    "plotSizesPie(dept)",
    "for n in (dept == 'dept3'):\n    n.labelvisible = true",
    "help",
  ]);
}

async function restoreAutosave(): Promise<boolean> {
  const saved = await store.get<string>("autosave");
  if (!saved) return false;
  await request((id) => ({ type: "writeFile", id, name: "autosave.guess", data: new TextEncoder().encode(saved) }));
  return term.submit(`makeFromSession("autosave.guess")`);
}

async function openUrl(url: string) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const name = (new URL(url, location.href).pathname.split("/").pop() || "graph").replace(/[^\w.\-]/g, "_");
    await openFile(new File([await res.arrayBuffer()], name));
  } catch (e) {
    term.error(`Could not load ${url}: ${e}`);
  }
}

async function main() {
  await renderer.init();
  themeReady();
  const files: Record<string, string> = {};
  for (const [path, text] of Object.entries(pyFiles)) files[path.split("/").pop()!] = text;
  status.textContent = "Starting…";
  send({ type: "init", files, data: { "sample.gdf": sampleGdf }, interrupt: interruptBuf });
}

main();

// ---- resizable console (beside the graph; below it on narrow screens) ---------------------
{
  const divider = $("#divider");
  const consoleEl = $("#console");
  const narrow = window.matchMedia("(max-width: 760px)");
  const vertical = () => narrow.matches;
  const KEY = "guess.consoleWidth";
  const applyStored = () => {
    // a dragged size only applies in the orientation it was made in
    consoleEl.style.flex = "";
    if (vertical()) return;
    try {
      const w = Number(localStorage.getItem(KEY));
      if (w > 0) consoleEl.style.flex = `0 0 ${Math.min(w, window.innerWidth - 240)}px`;
    } catch {
      /* storage unavailable */
    }
  };
  applyStored();
  narrow.addEventListener("change", applyStored);
  divider.addEventListener("pointerdown", (ev) => {
    divider.setPointerCapture(ev.pointerId);
    const col = vertical();
    const start = col ? ev.clientY : ev.clientX;
    const rect = consoleEl.getBoundingClientRect();
    const startSize = col ? rect.height : rect.width;
    let size = startSize;
    const move = (e: PointerEvent) => {
      const delta = (col ? e.clientY : e.clientX) - start;
      const limit = (col ? window.innerHeight - 140 : window.innerWidth - 240);
      size = Math.max(col ? 60 : 260, Math.min(limit, startSize - delta));
      consoleEl.style.flex = `0 0 ${size}px`;
    };
    const up = () => {
      divider.removeEventListener("pointermove", move);
      divider.removeEventListener("pointerup", up);
      if (!col) {
        try {
          localStorage.setItem(KEY, String(Math.round(size)));
        } catch {
          /* storage unavailable */
        }
      }
    };
    divider.addEventListener("pointermove", move);
    divider.addEventListener("pointerup", up);
  });
}
