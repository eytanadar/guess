import "./style.css";
import { Console, groupTip, type Item } from "./console";
import type { DragContext, FromWorker, Info, LegendEntry, LegendRec, ToWorker } from "./protocol";
import { Renderer, type DragBehaviour, type DragFrame, type Hit } from "./renderer";
import { Dock } from "./dock";
import { ask } from "./dialog";
import { toGIF, toPDF, toPS } from "./rasterexport";
import { HelpPanel, type HelpIndex } from "./help";
import { Palette, type PaletteItem } from "./palette";
import { DataTable, type TableData } from "./table";
import { TimelineBar, type TimelineInfo } from "./timeline";
import { ExcentricLens } from "./lens";
import { FilterPanel, StylePanel, VarsPanel, pyLit, type FieldInfo, type PanelHost, type Workspace } from "./panels";
import * as store from "./store";
import sampleGdf from "../../gdfs/sample.gdf?raw";

// The Python package, shipped into the worker's virtual filesystem.
const pyFiles = import.meta.glob("../../py/guess/*.py", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

const $ = <T extends HTMLElement>(sel: string) => document.querySelector(sel) as T;

// ?load=<url> opens a graph or session file; &app=1 hides the console (applet-style deployment)
const params = new URLSearchParams(location.search);
// a shared link carries the session in the hash: #s=<gzip+base64url>[&app=1]
const hashParams = new URLSearchParams(location.hash.slice(1));
const sharedSession = hashParams.get("s");
const appMode = params.get("app") === "1" || hashParams.get("app") === "1";
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
    // a group drag reports each node in turn; run them as one cell (one undo step).
    // The cell is hidden unless View → Show node moves is on, but it is in
    // history(), saveHistory(), log() and exports like any other command.
    if (!pendingMoves.length) queueMicrotask(() => {
      const moves = pendingMoves.splice(0);
      const lines: string[] = [];
      for (let k = 0; k < moves.length; k += 3) {
        const e = nodeExpr(moves[k]);
        lines.push(`${e}.x = ${fmtNum(moves[k + 1], false)}; ${e}.y = ${fmtNum(moves[k + 2], false)}`);
      }
      void term.submit(lines.join("\n"), { hidden: true });
    });
    pendingMoves.push(ident, x, y);
  },
  click: (hit, shift) => onGraphClick(hit, shift),
  selected: (ids) => syncSelection(ids),
  clickedAt: (x, y) => send({ type: "click", x, y }),
  dragBehaviour: (id, alt) => (tool === "select" ? dragBehaviour(id, alt) : null),
  wheel: (ev) => tool === "lens" && lens.wheel(ev),
  dragHint: (text) => {
    status.textContent = text ?? "";
  },
  // double-clicking a collapsed group expands it
  dblclick: (hit) => {
    if (hit?.kind !== "n" || !renderer.nodes.get(hit.id)?.m) return false;
    void term.submit(`expand(${nodeExpr(hit.id)})`);
    return true;
  },
});

/** Tell Python about a selection made on the display (bound to `sel`). */
function syncSelection(ids: number[]) {
  send({ type: "select", nodes: ids });
  dataTable.setSelection(ids);
  status.textContent = ids.length ? `${ids.length} selected — sel in the console` : "";
}

// ---- click tools (Gephi's toolbar: neighbourhood highlight, shortest path, heat map, painter) ----
type Tool = "select" | "path" | "heat" | "paint" | "lens";
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
  status.textContent = { select: "", path: "Path: click the first node", heat: "Heat map: click a node", paint: "Paint: click nodes (shift-click: with neighbours)",
    lens: "Lens: point at nodes to list them · wheel resizes · Shift+wheel scrolls · click pins it, then select or filter" }[t];
  lens.setActive(t === "lens");
}

// excentric labelling lens (src/lens.ts): a click tool that lists and selects the nodes under it
const lens = new ExcentricLens($("#graph"), renderer, {
  select: (ids, add) => {
    const next = add ? [...new Set([...renderer.selection, ...ids])] : ids;
    renderer.setSelection(next);
    syncSelection([...renderer.selection]);
  },
  toggle: (id) => syncSelection(renderer.toggleSelected(id)),
  zoomTo: (id) => renderer.center([id]),
});
const lensLoop = () => {
  lens.tick();
  requestAnimationFrame(lensLoop);
};
requestAnimationFrame(lensLoop);

for (const b of document.querySelectorAll<HTMLButtonElement>("[data-tool]")) b.addEventListener("click", () => setTool(b.dataset.tool as Tool));

function onGraphClick(hit: Hit, shift: boolean) {
  if (tool === "lens") {
    lens.click();
    return;
  }
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
let defaultEdgeHighlight = true;
/** context-menu entries added from Python (NodeEditorPopup.addItem) */
let customMenuItems: { id: string; label: string; scope: "n" | "e" | "ne" }[] = [];
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
      defaultEdgeHighlight = m.defaults.edgeHighlight ?? true;
      renderer.zoomOnDoubleClick = m.defaults.zoom;
      renderer.zoomEdgesOnDoubleClick = m.defaults.edgeZoom ?? true;
      break;
    case "menu":
      customMenuItems = m.items;
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
  run: async (code, cell, quiet) => {
    if (interruptBuf) new Uint8Array(interruptBuf)[0] = 0;
    const ok = await request<boolean>((id) => ({ type: "run", id, code, cell, quiet }));
    scheduleAutosave();
    afterRun();
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
      term.error(m.text, m.summary, m.line);
      break;
    case "help":
      void openSide("help", m.topic);
      break;
    case "graphs":
      renderGraphTabs(m.names, m.current);
      break;
    case "slides":
      slideList = m.slides;
      slideIndex = m.index;
      renderSlides();
      break;
    case "camera":
      renderer.setView(m.camera, m.ms);
      break;
    case "install":
      send({ type: "install", name: m.name });
      break;
    case "table":
      void openTable(m.kind, m.ids);
      break;
    case "center":
      renderer.center(m.nodes, m.edges);
      break;
    case "overlay":
      renderer.setOverlay(m);
      renderLegends(m.legends);
      $("#curved").setAttribute("aria-pressed", String(m.curvature > 0));
      $("#label-outlines").setAttribute("aria-pressed", String(!!m.labels?.outline));
      $("#label-cull").setAttribute("aria-pressed", String(!!m.labels?.cull));
      savedStyles = m.styles ?? [];
      dragCtx = m.drag ?? {};
      tipsForDragContext(dragCtx);
      stylePanel.refreshSaved();
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
    case "lens":
      lens.configure({ radius: m.radius, auto: m.auto, max: m.max });
      setTool(m.on ? "lens" : "select");
      break;
    case "labels": {
      // after the current redraw, so the labels being optimised are laid out
      requestAnimationFrame(() => {
        const r = renderer.optimizeLabels(Math.max(100, Math.min(m.ms, 30000)));
        status.textContent = r.labels
          ? `optimizeLabels: ${r.labels} labels, overlap cost ${r.before.toFixed(1)} → ${r.after.toFixed(1)}`
          : "optimizeLabels: no labels to place (labelpos \"outside\" or edge labels)";
      });
      break;
    }
    case "download":
      download(m.name, new Blob([m.text], { type: "text/plain" }));
      break;
    case "undone":
      term.markUndone(m.cell, m.undone);
      break;
    case "select":
      renderer.setSelection(m.nodes);
      dataTable.setSelection(m.nodes);
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

const HIDDEN_ROWS = new Set(["name", "image", "labelcolor", "strokecolor", "node1", "node2", "source", "destination"]);

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
  if (hit.kind === "n" ? defaultHighlight : defaultEdgeHighlight) highlightItems([[hit.kind, hit.id]]);
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

let menuExpr: string | null = null;   // the open menu acts on this expression (legend rows), not on ids

async function targetExpr(items: Item[]): Promise<string> {
  if (menuExpr) return menuExpr;
  const selIds = renderer.selection;
  if (items.length > 1 && items.length === selIds.size && items.every((i) => i[0] === "n" && selIds.has(i[1]))) return "sel";
  if (items.length === 1 && items[0][0] === "n") {
    const name = renderer.nodes.get(items[0][1])?.name ?? "";
    if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) return name;
  }
  await request((id) => ({ type: "assign", id, name: "_sel", items }));
  return "_sel";
}

function openMenu(items: Item[], x: number, y: number, opts: { expr?: string; title?: string } = {}) {
  if (!items.length) return;
  hideTip();
  menuExpr = opts.expr ?? null;
  const nodes = items.filter((i) => i[0] === "n").length;
  const edges = items.length - nodes;
  menu.replaceChildren();
  const head = document.createElement("div");
  head.className = "menu-head";
  const count = [nodes && `${nodes} node${nodes === 1 ? "" : "s"}`, edges && `${edges} edge${edges === 1 ? "" : "s"}`].filter(Boolean).join(", ");
  head.textContent = opts.title ? `${opts.title} (${count})`
    : items.length === 1
    ? (nodes ? renderer.nodes.get(items[0][1])?.name ?? "" : edgeName(items[0][1]))
    : count;
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
      const v = await ask({ title: "Node size", label: "Size", value: "15", type: "number" });
      if (v && !isNaN(Number(v))) await runOn((t) => `${t}.size = ${Number(v)}`)();
    });
    act("Style: circle", runOn((t) => `${t}.style = 2`));
    act("Style: square", runOn((t) => `${t}.style = 1`));
  }
  if (edges && !nodes) {
    act("Width…", async () => {
      const v = await ask({ title: "Edge width", label: "Width", value: "3", type: "number" });
      if (v && !isNaN(Number(v))) await runOn((t) => `${t}.width = ${Number(v)}`)();
    });
  }
  act("Hide", runOn((t) => `${t}.visible = false`));
  act("Delete", async () => {
    const ok = await runOn((t) => `remove(${t})`)();
    if (ok && items.some((i) => i[0] === "n" && renderer.selection.has(i[1]))) {
      renderer.setSelection([]);
      syncSelection([]);
    }
  });
  act("Center on", runOn((t) => `center(${t})`));
  // entries added from Python: NodeEditorPopup / EdgeEditorPopup / GraphElementPopup
  const scope = nodes && edges ? "ne" : nodes ? "n" : "e";
  const extra = customMenuItems.filter((i) => i.scope === scope);
  if (extra.length) {
    const sep = document.createElement("div");
    sep.className = "menu-sep";
    menu.append(sep);
    for (const it of extra) act(it.label, () => uiEvent(it.id, "menuEvent", items));
  }
  act("Assign to variable…", async () => {
    const name = await ask({ title: "Assign to a variable", note: `${items.length === 1 ? "This item" : `These ${items.length} items`} will be available in the console under this name.`, label: "Name", value: "foo", ok: "Assign" });
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
    if (tool === "lens" && lens.release()) return;
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
  [/\.(graphml|xml)$/i, "makeFromGraphML"],
  [/\.gml$/i, "makeFromGML"],
  [/\.(dot|gv)$/i, "makeFromDOT"],
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

/** Numbers on a gradient legend: at most 4 significant digits (23104.45… → 23,100). */
function legendNumber(v: number): string {
  if (!Number.isFinite(v)) return String(v);
  return Number(v.toPrecision(4)).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

/** What a legend row stands for: legendFor rows carry ids; rows added by hand
 *  match the visible elements drawn in their colour; "… N more" the rest. */
function legendItems(e: LegendEntry, lg: LegendRec): Item[] {
  if (e.ids) return e.ids.filter((i) => (e.ik === "e" ? renderer.edges : renderer.nodes).has(i)).map((i) => [e.ik ?? "n", i] as Item);
  if (e.k === "n") return [...renderer.nodes.values()].filter((n) => n.v && n.c === e.c).map((n) => ["n", n.i] as Item);
  if (e.k === "e") return [...renderer.edges.values()].filter((x) => x.v && x.c === e.c).map((x) => ["e", x.i] as Item);
  void lg;
  return [];
}

// legends the user expanded ("… N more"), by id; kept across re-renders
const expandedLegends = new Set<number>();
let lastLegends: LegendRec[] = [];

function renderLegends(legends: LegendRec[]) {
  lastLegends = legends;
  const host = $("#legends");
  // keep each legend's scroll position across re-renders
  const scrolls = new Map([...host.querySelectorAll<HTMLElement>(".legend")].map((b) => [Number(b.dataset.i), b.scrollTop]));
  host.replaceChildren();
  for (const id of [...expandedLegends]) if (!legends.some((lg) => lg.i === id)) expandedLegends.delete(id);
  for (const lg of legends) {
    if (!lg.entries.length && !lg.ramp) continue;
    const box = document.createElement("div");
    box.className = "legend";
    box.dataset.i = String(lg.i);
    const expanded = expandedLegends.has(lg.i);
    const close = document.createElement("button");
    close.className = "legend-close";
    close.textContent = "×";
    close.title = `Remove this legend (removeLegend(${lg.i}))`;
    close.setAttribute("aria-label", "Remove legend");
    close.addEventListener("click", () => void term.submit(`removeLegend(${lg.i})`));
    box.append(close);
    if (lg.ramp) {
      const bar = document.createElement("div");
      bar.className = "ramp";
      bar.style.background = `linear-gradient(to right, ${hex(lg.ramp.from)}, ${hex(lg.ramp.to)})`;
      const ends = document.createElement("div");
      ends.className = "ramp-ends";
      ends.innerHTML = "<span></span><span></span>";
      ends.children[0].textContent = legendNumber(lg.ramp.min);
      ends.children[1].textContent = legendNumber(lg.ramp.max);
      box.append(bar);
      // GradientLegend(…, min, max, tickEvery): tick marks along the ramp
      const span = lg.ramp.max - lg.ramp.min;
      if (lg.ramp.ticks && span > 0 && span / lg.ramp.ticks <= 50) {
        const ticks = document.createElement("div");
        ticks.className = "ramp-ticks";
        const first = Math.ceil(lg.ramp.min / lg.ramp.ticks) * lg.ramp.ticks;
        for (let v = first; v <= lg.ramp.max + 1e-9; v += lg.ramp.ticks) {
          const t = document.createElement("span");
          t.style.left = `${((v - lg.ramp.min) / span) * 100}%`;
          ticks.append(t);
        }
        box.append(ticks);
      }
      box.append(ends);
    }
    for (const e of lg.entries) {
      if (e.hid && !expanded) continue;
      const row = document.createElement("div");
      row.className = "legend-row";
      const sw = document.createElement("span");
      sw.className = `sw sw-${e.k}` + (e.k === "n" && (e.s === 2 || e.s === 5 || e.s === 9) ? " round" : "");
      sw.style.setProperty("--c", hex(e.c));
      sw.style.opacity = String(e.k === "h" ? Math.max(e.a, 0.35) : e.a);
      if (e.k === "e") sw.style.setProperty("--w", `${Math.min(Math.max(e.w ?? 2, 1), 8)}px`);
      const t = document.createElement("span");
      t.textContent = e.t;
      if (e.more && expanded) {
        const listed = lg.entries.filter((x) => x.k !== "x").length;
        const unlisted = lg.entries.some((x) => x.k === "x" && x.hid);    // over 300 groups
        t.textContent = unlisted ? `${listed} largest shown` : `all ${listed} shown`;
      }
      row.append(sw, t);
      if (e.more) {
        // "… N more": click to list every group (scrolls when long); again to collapse
        const toggle = document.createElement("button");
        toggle.className = "legend-more";
        toggle.textContent = expanded ? "Show fewer" : "Show all";
        toggle.addEventListener("click", () => {
          if (expanded) expandedLegends.delete(lg.i);
          else expandedLegends.add(lg.i);
          renderLegends(lastLegends);
        });
        row.append(toggle);
      }
      // live rows: hover highlights what the row stands for; right-click acts on it
      const items = legendItems(e, lg);
      if (items.length) {
        row.classList.add("live");
        row.title = `${items.length} ${items[0][0] === "n" ? "node" : "edge"}${items.length === 1 ? "" : "s"} · right-click for actions`;
        row.addEventListener("mouseenter", () => highlightItems(legendItems(e, lg)));
        row.addEventListener("mouseleave", () => highlightItems(null));
        row.addEventListener("contextmenu", (ev) => {
          ev.preventDefault();
          highlightItems(null);
          openMenu(legendItems(e, lg), ev.clientX, ev.clientY, e.q ? { expr: `(${e.q})`, title: e.t } : { title: e.t });
        });
      }
      box.append(row);
    }
    host.append(box);
    box.scrollTop = scrolls.get(lg.i) ?? 0;
    // a legend taller than its share of the graph scrolls, so it must take the wheel
    requestAnimationFrame(() => box.classList.toggle("scrolls", box.scrollHeight > box.clientHeight + 1));
  }
}

$("#sample").addEventListener("click", () => term.submit(`makeFromGDF("sample.gdf")`));
$("#save").addEventListener("click", () => term.submit(`saveSession("session.guess")`));
$("#curved").addEventListener("click", () => term.submit(`curvedEdges(${renderer.curvature > 0 ? "false" : "true"})`));
$("#center").addEventListener("click", () => renderer.center());
// ---- light / dark theme: Automatic follows the system (View menu) ----------------------
{
  type Theme = "auto" | "light" | "dark";
  const KEY = "guess.theme";
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
    renderer.setTheme(theme === "dark" || (theme === "auto" && system.matches));
    for (const b of document.querySelectorAll<HTMLElement>("[data-theme-choice]")) b.setAttribute("aria-pressed", String(b.dataset.themeChoice === theme));
  };
  for (const b of document.querySelectorAll<HTMLElement>("[data-theme-choice]")) {
    b.addEventListener("click", () => {
      theme = b.dataset.themeChoice as Theme;
      try {
        if (theme === "auto") localStorage.removeItem(KEY);
        else localStorage.setItem(KEY, theme);
      } catch {
        /* storage unavailable */
      }
      apply();
    });
  }
  system.addEventListener("change", apply);
  themeReady = apply;
}

// ---- menus ---------------------------------------------------------------------------
{
  const roots = [...document.querySelectorAll<HTMLElement>(".menu-root")];
  let openRoot: HTMLElement | null = null;
  const pop = (r: HTMLElement) => r.querySelector<HTMLElement>(".menu-pop")!;
  const title = (r: HTMLElement) => r.querySelector<HTMLElement>(".menu-title")!;
  const items = (r: HTMLElement) => [...pop(r).querySelectorAll<HTMLButtonElement>("button:not([disabled])")];
  const close = () => {
    if (!openRoot) return;
    pop(openRoot).hidden = true;
    title(openRoot).setAttribute("aria-expanded", "false");
    openRoot = null;
  };
  const open = (r: HTMLElement, focusFirst = false) => {
    if (openRoot !== r) close();
    openRoot = r;
    pop(r).hidden = false;
    title(r).setAttribute("aria-expanded", "true");
    if (focusFirst) items(r)[0]?.focus();
  };
  for (const r of roots) {
    title(r).addEventListener("click", () => (openRoot === r ? close() : open(r)));
    title(r).addEventListener("pointerenter", () => {
      if (openRoot && openRoot !== r) open(r);
    });
    title(r).addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        open(r, true);
      }
    });
    pop(r).addEventListener("click", (ev) => {
      if ((ev.target as HTMLElement).closest("button")) close();
    });
    pop(r).addEventListener("keydown", (ev) => {
      const list = items(r);
      const k = list.indexOf(document.activeElement as HTMLButtonElement);
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        list[(k + (ev.key === "ArrowDown" ? 1 : list.length - 1)) % list.length]?.focus();
      } else if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
        const next = roots[(roots.indexOf(r) + (ev.key === "ArrowRight" ? 1 : roots.length - 1)) % roots.length];
        open(next, true);
      } else if (ev.key === "Escape") {
        ev.stopPropagation();
        close();
        title(r).focus();
      }
    });
  }
  document.addEventListener("pointerdown", (ev) => {
    if (openRoot && !openRoot.contains(ev.target as Node)) close();
  });
  // menu items that run a Gython command
  for (const b of document.querySelectorAll<HTMLButtonElement>("[data-run]")) {
    b.addEventListener("click", () => void term.submit(b.dataset.run!));
  }
}
$("#find-output").addEventListener("click", () => term.openFind());
$("#vim-keys").setAttribute("aria-pressed", String(term.vim));
$("#vim-keys").addEventListener("click", () => {
  const on = !term.vim;
  term.setVim(on);
  $("#vim-keys").setAttribute("aria-pressed", String(on));
});
term.setShowMoves(term.showMoves);
$("#show-moves").setAttribute("aria-pressed", String(term.showMoves));
$("#show-moves").addEventListener("click", () => {
  const on = !term.showMoves;
  term.setShowMoves(on);
  $("#show-moves").setAttribute("aria-pressed", String(on));
});
document.addEventListener("keydown", (ev) => {
  if ((ev.metaKey || ev.ctrlKey) && ev.shiftKey && ev.key.toLowerCase() === "f") {
    ev.preventDefault();
    term.openFind();
  }
});
$("#label-outlines").addEventListener("click", () => term.submit(`labelOutlines(${$("#label-outlines").getAttribute("aria-pressed") === "true" ? "false" : "true"})`));
$("#label-cull").addEventListener("click", () => term.submit(`hideOverlappingLabels(${$("#label-cull").getAttribute("aria-pressed") === "true" ? "false" : "true"})`));
document.addEventListener("keydown", (ev) => {
  if (!(ev.metaKey || ev.ctrlKey) || ev.altKey || ev.shiftKey) return;
  const k = ev.key.toLowerCase();
  if (k === "o") {
    ev.preventDefault();
    $("#open").click();
  } else if (k === "s") {
    ev.preventDefault();
    $("#save").click();
  }
});

// Delete selected nodes: Edit menu, or Delete/Backspace when no text field has focus
async function deleteSelection() {
  if (!renderer.selection.size) {
    status.textContent = "Nothing selected: shift-drag a box or Alt-drag a lasso first";
    return;
  }
  if (await term.submit("remove(sel)")) {
    renderer.setSelection([]);
    syncSelection([]);
  }
}
$("#delete-sel").addEventListener("click", () => void deleteSelection());
document.addEventListener("keydown", (ev) => {
  if ((ev.key !== "Delete" && ev.key !== "Backspace") || ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const t = ev.target as HTMLElement | null;
  if (t?.closest(".cm-editor, input, textarea, select, [contenteditable=true], dialog")) return;
  if (!renderer.selection.size) return;
  ev.preventDefault();
  void deleteSelection();
});
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

async function exportView(format: "png" | "jpg" | "svg" | "gif" | "pdf" | "ps" | "eps", name: string) {
  if (format === "svg") {
    download(name, new Blob([renderer.exportSVG()], { type: "image/svg+xml" }));
    return;
  }
  if (format === "pdf") return download(name, await toPDF(await renderer.exportImage("jpg")));
  if (format === "ps" || format === "eps") return download(name, await toPS(await renderer.exportImage("png"), format === "eps"));
  if (format === "gif") return download(name, await toGIF(await renderer.exportImage("png")));
  const a = document.createElement("a");
  a.href = await renderer.exportImage(format);
  a.download = name;
  a.click();
}

// ---- timeline ------------------------------------------------------------------------
const timeline = new TimelineBar($("#timeline"), {
  info: (source) => request<TimelineInfo>((id) => ({ type: "query", id, what: "timeline", kind: source })),
  fields: async () => {
    const [nf, ef] = await Promise.all([loadFields("n"), loadFields("e")]);
    const skip = new Set(["x", "y", "width", "height", "style", "indegree", "outdegree", "totaldegree", "weight"]);
    return [...nf, ...ef].filter((f) => f.numeric && !skip.has(f.name)).map((f) => f.name).filter((v, i, a) => a.indexOf(v) === i);
  },
  quiet: async (code) => {
    if (term.busy) return false;
    return request<boolean>((id) => ({ type: "run", id, code, quiet: true }));
  },
  submit: (code) => void term.submit(code),
});
$("#btn-timeline").addEventListener("click", () => {
  const bar = $("#timeline");
  bar.hidden = !bar.hidden;
  $("#btn-timeline").setAttribute("aria-pressed", String(!bar.hidden));
  if (bar.hidden) timeline.hide();
  else void timeline.show();
});

// ---- declarative dragging (docs/DECLARATIVE_DRAGGING.md) ------------------------------------
// Each drag works out its candidate states when it starts, follows the pointer
// through them (snapping, previewing other nodes), and on drop runs one Gython
// command — visible in the console, undoable, reproducible.
let dragCtx: DragContext = {};
const fmtNum = (v: number, int: boolean) => (int ? String(Math.round(v)) : String(Math.round(v * 1000) / 1000));

function dragBehaviour(id: number, alt: boolean): DragBehaviour | null {
  const n = renderer.nodes.get(id);
  if (!n) return null;
  const expr = nodeExpr(id);
  const centre = (m: { x: number; y: number; w: number; h: number }) => [m.x + m.w / 2, m.y + m.h / 2] as const;

  // Alt-drag from a node: a rubber-band edge that snaps to the nearest node
  if (alt) {
    const [ax, ay] = centre(n);
    let target: number | null = null;
    return {
      move(wx, wy): DragFrame {
        const px = wx + n.w / 2, py = wy + n.h / 2;
        const snap = 40 / renderer.scale;
        target = null;
        let best = snap;
        for (const m of renderer.nodes.values()) {
          if (m.i === id || !m.v) continue;
          const [mx, my] = centre(m);
          const d = Math.hypot(mx - px, my - py);
          if (d < best) { best = d; target = m.i; }
        }
        const t = target !== null ? renderer.nodes.get(target)! : null;
        const [ex, ey] = t ? centre(t) : [px, py];
        return { x: n.x, y: n.y, line: [ax, ay, ex, ey], ring: t ? { x: ex, y: ey, r: Math.max(t.w, t.h) * 0.8 } : undefined,
                 hint: t ? `release to connect ${n.name} — ${t.name}` : "drag to another node to connect" };
      },
      drop() {
        if (target !== null) void term.submit(`addEdge(${expr}, ${nodeExpr(target)})`);
      },
    };
  }

  // scatterLayout: dragging edits the fields on the axes
  const ax = dragCtx.axes;
  if (ax && (ax.xedit || ax.yedit)) {
    const ox = n.x, oy = n.y;
    const vals = (x: number, y: number) => [ax.x0 + x / ax.sx, ax.y0 + (ax.h - y) / ax.sy];
    return {
      move(wx, wy): DragFrame {
        const x = ax.xedit ? wx : ox, y = ax.yedit ? wy : oy;
        const [vx, vy] = vals(x, y);
        return { x, y, hint: [ax.xedit && `${ax.x} = ${fmtNum(vx, ax.xint)}`, ax.yedit && `${ax.y} = ${fmtNum(vy, ax.yint)}`].filter(Boolean).join(", ") };
      },
      drop(f) {
        const [vx, vy] = vals(f.x, f.y);
        const lines: string[] = [];
        if (ax.xedit) lines.push(`${expr}.${ax.x} = ${fmtNum(vx, ax.xint)}`);
        if (ax.yedit) lines.push(`${expr}.${ax.y} = ${fmtNum(vy, ax.yint)}`);
        lines.push(`${expr}.x = ${fmtNum(f.x, false)}; ${expr}.y = ${fmtNum(f.y, false)}`);
        void term.submit(lines.join("\n"));
      },
    };
  }

  // circleLayout: slide around the ring; the others make room
  const ring = dragCtx.ring;
  if (ring && ring.ids.includes(id)) {
    const others = ring.ids.filter((i) => i !== id && renderer.nodes.has(i));
    const total = others.length + 1;
    let slot = ring.ids.indexOf(id);
    return {
      move(wx, wy): DragFrame {
        let t = Math.atan2(wy - ring.cy, wx - ring.cx);
        if (t < 0) t += 2 * Math.PI;
        slot = Math.round((t / (2 * Math.PI)) * total) % total;
        const order = [...others];
        order.splice(slot, 0, id);
        const pos = new Map<number, [number, number]>();
        order.forEach((nid, j) => {
          const a = (2 * Math.PI * j) / total;
          if (nid !== id) pos.set(nid, [ring.cx + ring.r * Math.cos(a), ring.cy + ring.r * Math.sin(a)]);
        });
        return { x: ring.cx + ring.r * Math.cos(t), y: ring.cy + ring.r * Math.sin(t), others: pos,
                 hint: `${n.name}: position ${slot + 1} of ${total}` };
      },
      drop() {
        void term.submit(`ringMove(${expr}, ${slot})`);
      },
    };
  }

  return null;
}

// ---- gesture guide and one-time tips -------------------------------------------------
$("#btn-gestures").addEventListener("click", () => void openSide("help", "gestures"));
// the built manual is deployed next to the app (scripts/copy-manuals.mjs; the dev server serves it too)
$("#btn-manual").addEventListener("click", () => window.open(new URL("manuals/", location.href).href, "_blank", "noopener"));
$("#btn-github").addEventListener("click", () => window.open("https://github.com/eytanadar/guess", "_blank", "noopener"));
const TIPS: Record<string, string> = {
  ring: "Tip: drag a node around the circle to reorder it; the others make room.",
  scatter: "Tip: drag a node in the scatter plot to edit its two values.",
  box: "Tip: shift-drag to box-select, Alt-drag to lasso, click a node to see its neighbours.",
};
let tipTimer = 0;
function seenTips(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem("guess.tips") || "[]"));
  } catch {
    return new Set();
  }
}
/** Show a tip once per browser, linking to its card in the gestures guide. */
function offerTip(id: string) {
  const seen = seenTips();
  if (seen.has(id) || appMode) return;
  seen.add(id);
  try {
    localStorage.setItem("guess.tips", JSON.stringify([...seen]));
  } catch {
    /* storage unavailable */
  }
  const card = $("#tipcard");
  card.querySelector(".tipcard-text")!.textContent = TIPS[id];
  card.hidden = false;
  (card.querySelector(".tipcard-show") as HTMLButtonElement).onclick = () => {
    card.hidden = true;
    void openSide("help", `gestures:${id}`);
  };
  clearTimeout(tipTimer);
  tipTimer = window.setTimeout(() => (card.hidden = true), 14000);
}
$(".tipcard-close").addEventListener("click", () => ($("#tipcard").hidden = true));
let lastDragKinds = "";
function tipsForDragContext(ctx: DragContext) {
  const kinds = [ctx.ring && "ring", ctx.axes && "scatter"].filter(Boolean).join(",");
  if (kinds === lastDragKinds) return;
  lastDragKinds = kinds;
  if (ctx.axes) offerTip("scatter");
  else if (ctx.ring) offerTip("ring");
}

// ---- presentation (slides) ------------------------------------------------------------
let slideList: { note: string }[] = [];
let slideIndex: number | null = null;
function renderSlides() {
  const n = slideList.length;
  $("#slide-pos").textContent = n ? `${slideIndex === null ? "–" : slideIndex + 1} / ${n}` : "no slides";
  $("#slide-note").textContent = slideIndex !== null ? slideList[slideIndex]?.note ?? "" : n ? "← → to step through" : "Arrange the graph, then Add slide";
  $<HTMLButtonElement>("#slide-prev").disabled = !n || slideIndex === 0;
  $<HTMLButtonElement>("#slide-next").disabled = !n || slideIndex === n - 1;
  $<HTMLButtonElement>("#slide-remove").disabled = slideIndex === null;
}
function gotoSlide(k: number) {
  if (k < 0 || k >= slideList.length) return;
  void term.submit(`showSlide(${k})`);
}
const presenting = () => !$("#present").hidden;
function setPresenting(on: boolean) {
  $("#present").hidden = !on;
  $("#btn-present").setAttribute("aria-pressed", String(on));
  renderSlides();
}
$("#btn-present").addEventListener("click", () => setPresenting(!presenting()));
$("#present-close").addEventListener("click", () => setPresenting(false));
$("#slide-prev").addEventListener("click", () => gotoSlide((slideIndex ?? 1) - 1));
$("#slide-next").addEventListener("click", () => gotoSlide(slideIndex === null ? 0 : slideIndex + 1));
$("#slide-add").addEventListener("click", () => {
  const note = $<HTMLInputElement>("#slide-new-note").value.trim();
  const cam = renderer.getView().map((v) => Math.round(v * 1000) / 1000);
  void term.submit(`addSlide(${JSON.stringify(note)}, camera=[${cam.join(", ")}]${slideIndex !== null ? `, at=${slideIndex + 1}` : ""})`);
  $<HTMLInputElement>("#slide-new-note").value = "";
});
$("#slide-remove").addEventListener("click", () => {
  if (slideIndex !== null) void term.submit(`removeSlide(${slideIndex})`);
});
document.addEventListener("keydown", (ev) => {
  if (!presenting() || ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const t = ev.target as HTMLElement | null;
  if (t?.closest(".cm-editor, input, textarea, select")) return;
  if (ev.key === "ArrowRight" || ev.key === "PageDown" || ev.key === " ") {
    ev.preventDefault();
    gotoSlide(slideIndex === null ? 0 : slideIndex + 1);
  } else if (ev.key === "ArrowLeft" || ev.key === "PageUp") {
    ev.preventDefault();
    gotoSlide((slideIndex ?? 1) - 1);
  }
});

// ---- getting data in: URL, pasted tables, NDEx, Wikidata ---------------------------------
$("#open-url").addEventListener("click", async () => {
  const url = await ask({ title: "Open from URL", note: "A GDF, GEXF, GraphML, Pajek, DL or CSV file, or a .guess session. The server must allow cross-origin requests.", label: "URL", placeholder: "https://…", type: "url", ok: "Open" });
  if (url) void term.submit(`makeFromURL(${JSON.stringify(url)})`);
});
$("#open-ndex").addEventListener("click", async () => {
  const id = await ask({ title: "Open from NDEx", note: "The UUID of a public network on www.ndexbio.org (it is in the network's address).", label: "UUID", placeholder: "e.g. 9c38ce6e-…", ok: "Open" });
  if (id) void term.submit(`makeFromNDEx(${JSON.stringify(id.trim())})`);
});
$("#paste-data").addEventListener("click", () => {
  const dlg = $<HTMLDialogElement>("#paste-dialog");
  const area = dlg.querySelector("textarea")!;
  area.value = "";
  dlg.showModal();
  navigator.clipboard?.readText?.().then((t) => {
    if (!area.value && t) area.value = t;
  }).catch(() => {});
});
$("#paste-load").addEventListener("click", async () => {
  const dlg = $<HTMLDialogElement>("#paste-dialog");
  const text = dlg.querySelector("textarea")!.value;
  dlg.close();
  if (!text.trim()) return;
  await request((id) => ({ type: "writeFile", id, name: "pasted.csv", data: new TextEncoder().encode(text) }));
  await term.submit(`makeFromCSV("pasted.csv")`);
});
$("#paste-cancel").addEventListener("click", () => $<HTMLDialogElement>("#paste-dialog").close());

// ---- graph tabs (several graphs in one session) ------------------------------------------
function renderGraphTabs(names: string[], current: string) {
  const bar = $("#graph-tabs");
  bar.hidden = names.length < 2;
  bar.replaceChildren();
  for (const name of names) {
    const tab = document.createElement("span");
    tab.className = "graph-tab" + (name === current ? " current" : "");
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(name === current));
    const b = document.createElement("button");
    b.textContent = name;
    b.title = name === current ? "Current graph (renameGraph(...) to rename)" : `Switch to ${name}`;
    b.onclick = () => {
      if (name !== current) void term.submit(`use(${JSON.stringify(name)})`);
    };
    tab.append(b);
    if (name !== current) {
      const x = document.createElement("button");
      x.className = "graph-tab-close";
      x.textContent = "✕";
      x.title = `Close ${name}`;
      x.onclick = () => void term.submit(`closeGraph(${JSON.stringify(name)})`);
      tab.append(x);
    }
    bar.append(tab);
  }
}

// ---- share by link, publish a viewer ---------------------------------------------------
const b64url = (bytes: Uint8Array) => {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};
async function packSession(text: string): Promise<string> {
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream("gzip"));
  return b64url(new Uint8Array(await new Response(stream).arrayBuffer()));
}
async function unpackSession(data: string): Promise<string> {
  const bin = atob(data.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
}
async function shareLink(app: boolean) {
  const snap = await request<[number, string] | null>((id) => ({ type: "snapshot", id, since: -1 }));
  if (!snap) return;
  const packed = await packSession(snap[1]);
  const url = `${location.origin}${location.pathname}#s=${packed}${app ? "&app=1" : ""}`;
  try {
    await navigator.clipboard.writeText(url);
    term.note(`Link copied (${Math.round(url.length / 1024)} KB)${url.length > 64000 ? " — long links may be cut off by some apps; for big graphs share a saved .guess file instead" : ""}. It opens this graph${app ? " as a read-only viewer" : ""} for anyone with the link.`);
  } catch {
    term.note(`Copy this link: ${url}`);
  }
}
$("#share-link").addEventListener("click", () => void shareLink(false));
$("#share-viewer").addEventListener("click", () => void shareLink(true));

// ---- notebook and report export ---------------------------------------------------------
async function exportNotebook() {
  const png = await renderer.exportImage("png");
  const cells: object[] = [{
    cell_type: "markdown", metadata: {},
    source: [`# GUESS session\n\nExported ${new Date().toLocaleString()}. The code is Gython (GUESS's Python with graph operators); `,
      "run it in GUESS, or adapt it with networkx.\n\n![graph](attachment:graph.png)"],
    attachments: { "graph.png": { "image/png": png.split(",")[1] } },
  }];
  for (const c of term.cellsForExport()) {
    if (c.undone) continue;
    cells.push({
      cell_type: "code", execution_count: c.n, metadata: {},
      source: c.code.split("\n").map((l, i, a) => (i < a.length - 1 ? l + "\n" : l)),
      outputs: c.output ? [c.failed
        ? { output_type: "error", ename: "Error", evalue: c.output.split("\n")[0], traceback: c.output.split("\n") }
        : { output_type: "stream", name: "stdout", text: c.output.split("\n").map((l, i, a) => (i < a.length - 1 ? l + "\n" : l)) }] : [],
    });
  }
  const nb = { nbformat: 4, nbformat_minor: 5, metadata: { language_info: { name: "python" }, kernelspec: { name: "python3", display_name: "Python 3", language: "python" } }, cells };
  download("guess.ipynb", new Blob([JSON.stringify(nb, null, 1)], { type: "application/x-ipynb+json" }));
}

async function exportReport() {
  const png = await renderer.exportImage("png");
  const esc = (t: string) => t.replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[ch]!);
  const legendCopy = $("#legends").cloneNode(true) as HTMLElement;
  for (const b of legendCopy.querySelectorAll(".legend-close")) b.remove();   // no buttons in the report
  const legends = legendCopy.innerHTML;
  const css = getComputedStyle(document.documentElement);
  const v = (n: string) => css.getPropertyValue(n).trim();
  const cells = term.cellsForExport().filter((c) => !c.undone && !c.hidden).map((c) => `<section class="cell${c.failed ? " failed" : ""}"><div class="n">[${c.n}]</div><pre class="code">${esc(c.code)}</pre>${c.output ? `<pre class="out">${esc(c.output)}</pre>` : ""}</section>`).join("\n");
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>GUESS report</title>
<style>body{font:15px system-ui,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:${v("--text")};background:${v("--bg")}}
h1{font-size:22px}figure{margin:0;position:relative;border:1px solid ${v("--border")};border-radius:8px;overflow:hidden}figure img{display:block;width:100%}
.legends{position:absolute;top:10px;right:10px;display:flex;flex-direction:column;gap:8px}.legend{background:${v("--legend-bg")};border:1px solid ${v("--border")};border-radius:6px;padding:6px 9px;font-size:12px}
.legend-row{display:flex;align-items:center;gap:7px}.sw{display:inline-block;width:12px;height:12px;background:var(--c);border:1px solid #0005}.sw.round{border-radius:50%}.sw-e{width:18px;height:var(--w);border:0}.ramp{width:160px;height:10px}.ramp-ends{display:flex;justify-content:space-between;font-size:11px}
.cell{display:grid;grid-template-columns:3.5em 1fr;gap:0 8px;border-top:1px solid ${v("--border")};padding:8px 0}.n{color:${v("--muted")};font:12px ui-monospace,monospace}
pre{margin:0;font:12.5px/1.45 ui-monospace,Menlo,monospace;white-space:pre-wrap}.out{grid-column:2;color:${v("--echo")};margin-top:4px}.failed .out{color:${v("--error")}}</style></head>
<body><h1>GUESS report</h1><p>${esc(new Date().toLocaleString())}</p><figure><img alt="graph" src="${png}"><div class="legends">${legends}</div></figure><h2>Commands</h2>${cells}</body></html>`;
  download("guess-report.html", new Blob([html], { type: "text/html" }));
}
$("#export-notebook").addEventListener("click", () => void exportNotebook());
$("#export-report").addEventListener("click", () => void exportReport());

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

// ---- help, palette, data table, style and filter panels ------------------------------
let savedStyles: string[] = [];
let helpIndex: Promise<HelpIndex> | null = null;
const loadHelp = () => (helpIndex ??= request<HelpIndex>((id) => ({ type: "query", id, what: "help" })));
const loadFields = (kind: "n" | "e") => request<FieldInfo[]>((id) => ({ type: "query", id, what: "fields", kind }));

const panelHost: PanelHost = {
  fields: loadFields,
  submit: (code) => term.submit(code),
  styles: () => savedStyles,
  selectedNode: () => {
    const first = [...renderer.selection][0];
    return first === undefined ? null : renderer.nodes.get(first)?.name ?? null;
  },
};

const helpPanel = new HelpPanel($("#side-help"), {
  insert: (code) => term.insert(code),
  run: (code) => void term.submit(code),
}, loadHelp);
const stylePanel = new StylePanel($("#side-style"), panelHost);
const filterPanel = new FilterPanel($("#side-filter"), panelHost);
const varsPanel = new VarsPanel($("#side-vars"), {
  load: () => request<Workspace>((id) => ({ type: "query", id, what: "workspace" })),
  hover: (items) => highlightItems(items),
  select: (items) => {
    const nodes = new Set<number>();
    for (const [k, id] of items) {
      if (k === "n") nodes.add(id);
      else {
        const e = renderer.edges.get(id);
        if (e) nodes.add(e.s).add(e.t);
      }
    }
    renderer.setSelection(nodes);
    syncSelection([...renderer.selection]);
    renderer.center([...nodes]);
  },
  table: (items) => {
    const nodes = items.filter((i) => i[0] === "n").map((i) => i[1]);
    void openTable(nodes.length ? "n" : "e", nodes.length ? nodes : items.map((i) => i[1]));
  },
  insert: (code) => term.insert(code),
  submit: (code) => void term.submit(code),
});

type Side = "help" | "style" | "filter" | "vars";
let side: Side | null = null;
async function openSide(which: Side | null, topic: string | null = null) {
  side = which;
  $("#sidebar").hidden = which === null;
  for (const s of ["help", "style", "filter", "vars"] as Side[]) {
    $(`#side-${s}`).hidden = s !== which;
    $(`#btn-${s}`).setAttribute("aria-pressed", String(s === which));
  }
  for (const b of document.querySelectorAll<HTMLButtonElement>("[data-side]")) b.setAttribute("aria-selected", String(b.dataset.side === which));
  if (which === "help") await helpPanel.show(topic);
  else if (which === "style") await stylePanel.show();
  else if (which === "filter") await filterPanel.show();
  else if (which === "vars") await varsPanel.show();
}
for (const s of ["help", "style", "filter", "vars"] as Side[]) {
  $(`#btn-${s}`).addEventListener("click", () => void openSide(side === s ? null : s));
}
for (const b of document.querySelectorAll<HTMLButtonElement>("[data-side]")) b.addEventListener("click", () => void openSide(b.dataset.side as Side));
$(".sidebar-close").addEventListener("click", () => void openSide(null));

// data table
const edgeExpr = (id: number) => `g.edge_by_id(${id})`;
const dataTable = new DataTable($("#table-body"), {
  load: (kind, ids) => request<TableData>((id) => ({ type: "query", id, what: "table", kind, ids })),
  select: (kind, ids, add) => {
    const nodes = new Set<number>(add ? renderer.selection : []);
    for (const id of ids) {
      if (kind === "n") {
        if (add && nodes.has(id)) nodes.delete(id);
        else nodes.add(id);
      } else {
        const e = renderer.edges.get(id);
        if (e) nodes.add(e.s).add(e.t);
      }
    }
    renderer.setSelection(nodes);
    syncSelection([...renderer.selection]);
  },
  hover: (kind, id) => highlightItems(id === null ? null : [[kind, id]]),
  center: (kind, id) => renderer.center(kind === "n" ? [id] : [], kind === "e" ? [id] : []),
  edit: (kind, id, field, value, type) => {
    const target = kind === "n" ? nodeExpr(id) : edgeExpr(id);
    let lit: string;
    const v = value.trim();
    if (v === "") lit = "None";
    else if (type === "BOOLEAN") lit = /^(true|1|yes|t)$/i.test(v) ? "true" : "false";
    else if ((type === "DOUBLE" || type === "INTEGER") && !isNaN(Number(v))) lit = String(Number(v));
    else lit = pyLit(value);
    void term.submit(`${target}.${field} = ${lit}`);
  },
});
dataTable.root.hidden = false;

async function openTable(kind: "n" | "e" = "n", ids: number[] | null = null) {
  $("#table-pane").hidden = false;
  $("#btn-table").setAttribute("aria-pressed", "true");
  dataTable.setSelection(renderer.selection);
  await dataTable.show(kind, ids);
}
function closeTable() {
  $("#table-pane").hidden = true;
  $("#btn-table").setAttribute("aria-pressed", "false");
}
$("#btn-table").addEventListener("click", () => ($("#table-pane").hidden ? void openTable() : closeTable()));
$(".table-close").addEventListener("click", closeTable);
Object.defineProperty(dataTable, "visible", { get: () => !$("#table-pane").hidden });
{
  // drag the table's top edge to resize
  const pane = $("#table-pane");
  const KEY = "guess.tableHeight";
  try {
    const h = Number(localStorage.getItem(KEY));
    if (h > 60) pane.style.height = `${h}px`;
  } catch { /* storage unavailable */ }
  const handle = $(".table-resize");
  handle.addEventListener("pointerdown", (ev) => {
    handle.setPointerCapture(ev.pointerId);
    const y0 = ev.clientY, h0 = pane.getBoundingClientRect().height;
    const move = (e: PointerEvent) => {
      pane.style.height = `${Math.max(80, Math.min(window.innerHeight - 200, h0 - (e.clientY - y0)))}px`;
    };
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      try { localStorage.setItem(KEY, String(Math.round(pane.getBoundingClientRect().height))); } catch { /* ignore */ }
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
  });
}

let refreshTimer = 0;
/** After any command: refresh the open table (coalesced). */
function afterRun() {
  clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => {
    void dataTable.refresh();
    if (side === "vars") void varsPanel.show();
  }, 150);
}

// command palette
const palette = new Palette(async () => {
  const items: PaletteItem[] = [];
  const idx = await loadHelp();
  for (const c of idx.commands) {
    const noArgs = /\(\)$/.test(c.sig);
    items.push({ kind: "command", label: c.name, detail: c.doc.split("\n")[0] || c.sig, run: () => term.insert(noArgs ? `${c.name}()` : `${c.name}(`) });
  }
  for (const e of idx.examples) items.push({ kind: "example", label: e.title, detail: e.code.split("\n")[0] + (e.code.includes("\n") ? " …" : "") + ` ${e.tags}`, run: () => term.insert(e.code) });
  for (const code of term.recent()) items.push({ kind: "recent", label: code.split("\n")[0], detail: code.includes("\n") ? "…" : "", run: () => term.insert(code) });
  for (const b of document.querySelectorAll<HTMLButtonElement>(".menu-pop button, [data-tool], #stop")) {
    if (b.id === "btn-palette" || b.disabled) continue;
    const label = [...b.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent).join("").trim();
    if (!label) continue;
    const menu = b.closest(".menu-root")?.querySelector(".menu-title")?.textContent;
    items.push({ kind: "action", label: menu ? `${menu} › ${label}` : `Tool: ${label}`, detail: b.title || b.dataset.run || "", run: () => b.click() });
  }
  for (const n of renderer.nodes.values()) {
    items.push({ kind: "node", label: n.name, detail: n.l && n.l !== n.name ? n.l : "", run: () => {
      renderer.setSelection([n.i]);
      syncSelection([n.i]);
      renderer.center([n.i]);
    } });
  }
  try {
    for (const f of await loadFields("n")) {
      if (f.numeric || !f.values || ["color", "strokecolor", "labelcolor", "label", "image"].includes(f.name)) continue;
      for (const [v, count] of f.values.slice(0, 40)) {
        if (v === null) continue;
        items.push({ kind: "value", label: `${f.name} == ${String(v)}`, detail: `${count} node${count === 1 ? "" : "s"}`, run: () => void term.submit(`select(${f.name} == ${pyLit(v)})`) });
      }
    }
  } catch { /* busy */ }
  return items;
});
$("#btn-palette").addEventListener("click", () => void palette.open());
$("#search").addEventListener("click", () => void palette.open());
document.addEventListener("keydown", (ev) => {
  if ((ev.metaKey || ev.ctrlKey) && !ev.altKey && ev.key.toLowerCase() === "k") {
    ev.preventDefault();
    if (palette.isOpen) palette.close();
    else void palette.open();
  } else if (ev.key === "F1") {
    ev.preventDefault();
    void openSide(side === "help" ? null : "help");
  }
}, true);

// ---- start --------------------------------------------------------------------------
async function onReady() {
  term.docs = await request<Record<string, string>>((id) => ({ type: "docs", id }));
  if (sharedSession) {
    try {
      const text = await unpackSession(sharedSession);
      await request((id) => ({ type: "writeFile", id, name: "shared.guess", data: new TextEncoder().encode(text) }));
      await term.submit(`makeFromSession("shared.guess")`);
    } catch (e) {
      term.error(`Could not open the shared link: ${e}`);
    }
  } else if (loadUrl) {
    await openUrl(loadUrl);
  } else if (await restoreAutosave()) {
    term.note("Restored your previous session (variables are not restored). Sample graph starts over.");
  } else {
    showWelcome();
    await term.submit(`makeFromGDF("sample.gdf")`);
  }
  window.setTimeout(() => offerTip("box"), 2500);
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

// for debugging and tests in the dev server only
if (import.meta.env.DEV) (window as unknown as { __guess: unknown }).__guess = { renderer, term };
