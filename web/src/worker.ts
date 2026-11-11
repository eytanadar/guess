/// <reference lib="webworker" />
// Runs Pyodide and the `guess` Python package. The graph model lives here.
import type { FromWorker, ToWorker } from "./protocol";
import { GuessFA2 } from "./fa2";

// fast layouts implemented in JS, called synchronously from Python (layouts.py)
(self as unknown as { GuessFA2: typeof GuessFA2 }).GuessFA2 = GuessFA2;

// Where Pyodide comes from: jsDelivr by default; `npm run bundle -- --offline` builds
// with VITE_PYODIDE_URL=../pyodide/ (resolved against this worker script) so a
// self-hosted copy is used instead.
const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const PYODIDE_URL = new URL(import.meta.env.VITE_PYODIDE_URL || PYODIDE_CDN, self.location.href).href;

declare const self: DedicatedWorkerGlobalScope;

type Py = {
  runPython(code: string): unknown;
  loadPackage(names: string[]): Promise<unknown>;
  setInterruptBuffer(buf: Uint8Array): void;
  pyimport(name: string): any;
  globals: { set(name: string, v: unknown): void; get(name: string): any };
  FS: {
    mkdirTree(p: string): void;
    writeFile(p: string, data: string | Uint8Array): void;
    createLazyFile(parent: string, name: string, url: string, canRead: boolean, canWrite: boolean): unknown;
    analyzePath(p: string): { exists: boolean };
    unlink(p: string): void;
  };
};

let py: Py | null = null;
let session: any = null;
const queue: ToWorker[] = [];

function post(msg: FromWorker) {
  self.postMessage(msg);
}

async function init(msg: Extract<ToWorker, { type: "init" }>) {
  post({ type: "status", text: "Loading Python…" });
  const mod = await import(/* @vite-ignore */ PYODIDE_URL + "pyodide.mjs");
  py = (await mod.loadPyodide({ indexURL: PYODIDE_URL })) as Py;
  post({ type: "status", text: "Loading numpy and networkx…" });
  await Promise.all([py.loadPackage(["numpy"]), loadWithoutDeps(py, ["networkx"])]);

  py.FS.mkdirTree("/guess_py/guess");
  for (const [name, text] of Object.entries(msg.files)) {
    py.FS.writeFile(`/guess_py/guess/${name}`, text);
  }
  py.FS.mkdirTree("/data");
  for (const [name, text] of Object.entries(msg.data)) {
    py.FS.writeFile(`/data/${name}`, text);
  }
  // the cookbooks' datasets: listed now, downloaded the first time they're read
  for (const [name, url] of Object.entries(msg.lazy ?? {})) {
    if (!py.FS.analyzePath(`/data/${name}`).exists) py.FS.createLazyFile("/data", name, url, true, false);
  }
  let interruptible = false;
  if (msg.interrupt) {
    py.setInterruptBuffer(new Uint8Array(msg.interrupt));
    interruptible = true;
  }
  py.globals.set("__js_emit", (s: string) => post(JSON.parse(s)));
  py.runPython(`
import sys, os, json
sys.path.insert(0, "/guess_py")
os.chdir("/data")
from guess import Session
session = Session(lambda m: __js_emit(json.dumps(m)))
`);
  session = py.globals.get("session");
  post({ type: "ready", interruptible });
  // igraph (C core, about 1 MB) in the background: statistics use it once it is
  // here (py/guess/igr.py), and nothing waits for it
  const p = py;
  p.loadPackage(["igraph"])
    .then(() => p.runPython("import importlib; importlib.invalidate_caches()"))
    .catch((e: unknown) => console.warn("igraph did not load; GUESS uses networkx/numpy instead", e))
    // then Graphviz (WebAssembly, about 0.8 MB): Python calls it synchronously (py/guess/gv.py)
    .then(() => import("@hpcc-js/wasm-graphviz"))
    .then(({ Graphviz }) => Graphviz.load())
    .then((gv) => {
      (self as unknown as { guessGraphvizLayout: unknown }).guessGraphvizLayout =
        (dot: string, engine: string, nop: number) =>
          gv.layout(dot, "json", engine as Parameters<typeof gv.layout>[2], nop ? { nop } : undefined);
    })
    .catch((e: unknown) => console.warn("Graphviz did not load; its layouts are unavailable", e));
}

// Pyodide's networkx recipe depends on matplotlib (and numpy, Pillow, ...).
// We only need the pure-Python core, so load the wheel by URL, which skips
// dependency resolution.
let lockPromise: Promise<any> | null = null;
function pyodideLock(): Promise<any> {
  lockPromise ??= fetch(PYODIDE_URL + "pyodide-lock.json").then((r) => r.json());
  return lockPromise;
}

async function loadWithoutDeps(py: Py, names: string[]) {
  const lock = await pyodideLock();
  const urls = names.map((n) => PYODIDE_URL + lock.packages[n].file_name);
  await py.loadPackage(urls);
}

/** Before a cell runs: load the Pyodide packages it imports (altair, pandas,
 *  scipy, …), and Altair when it uses `alt.` without importing it. Packages
 *  GUESS loads itself (networkx, igraph) are left alone. */
const ALT_USE = /(?<![\w.])alt\./;
const SKIP = new Set(["networkx", "igraph"]);
const loaded = new Set<string>();
async function loadImports(code: string) {
  let mods: string[] = [];
  try {
    py!.globals.set("__src", code);
    const found = py!.runPython("from pyodide.code import find_imports as __fi\n__fi(__src)") as any;
    mods = found?.toJs ? found.toJs() : [];
    found?.destroy?.();
  } catch {
    /* a syntax error: the run reports it */
  }
  if (ALT_USE.test(code)) mods.push("altair");
  if (!mods.length) return;
  const lock = await pyodideLock();
  const byImport = new Map<string, string>();
  for (const [name, rec] of Object.entries<any>(lock.packages)) for (const m of rec.imports ?? []) byImport.set(m, name);
  const want = [...new Set(mods.map((m) => byImport.get(m.split(".")[0])).filter((n): n is string => !!n))]
    .filter((n) => !SKIP.has(n) && !loaded.has(n) && !(n in ((py as any).loadedPackages ?? {})));
  if (!want.length) return;
  post({ type: "text", text: `loading ${want.join(", ")} (first use)…\n` });
  await py!.loadPackage(want);
  for (const n of want) loaded.add(n);
  py!.runPython("import importlib; importlib.invalidate_caches()");
}

/** installPackage(): micropip, in the background (between commands). */
async function installPackage(name: string) {
  try {
    await py!.loadPackage(["micropip"]);
    const micropip = py!.pyimport("micropip");
    await micropip.install(name);
    micropip.destroy?.();
    post({ type: "text", text: `installed ${name}; you can import it now\n` });
  } catch (e) {
    post({ type: "error", text: `could not install ${name}: ${String(e).split("\n").filter(Boolean).pop()}` });
  }
}

function call(fn: string, ...args: unknown[]): unknown {
  const result = session[fn](...args);
  if (result && typeof result === "object" && "toJs" in result) {
    const v = (result as any).toJs({ dict_converter: Object.fromEntries });
    (result as any).destroy?.();
    return v;
  }
  return result;
}

function handle(msg: ToWorker) {
  switch (msg.type) {
    case "run": {
      const go = () => {
        session.current_cell = msg.cell ?? null;
        session.quiet_next = !!msg.quiet;
        const ok = call("run", msg.code) as boolean;
        post({ type: "done", id: msg.id, ok });
      };
      // packages it imports load first (a few seconds, once); then it runs
      loadImports(msg.code).then(go, (e) => {
        post({ type: "error", text: `could not load a package: ${String(e).split("\n").filter(Boolean).pop()}` });
        go();
      });
      break;
    }
    case "complete":
      post({ type: "reply", id: msg.id, value: call("is_complete", msg.code) });
      break;
    case "completions":
      post({ type: "reply", id: msg.id, value: call("completions", msg.text) });
      break;
    case "event":
      py!.globals.set("__ev", JSON.stringify([msg.target, msg.name, msg.value]));
      post({ type: "reply", id: msg.id, value: py!.runPython(
        "__t, __n, __v = json.loads(__ev)\nsession.dispatch(__t, __n, json.loads(__v) if __v else None)") });
      break;
    case "snapshot":
      post({ type: "reply", id: msg.id, value: call("save_state_json", msg.since) });
      break;
    case "docs":
      post({ type: "reply", id: msg.id, value: call("command_docs") });
      break;
    case "describe":
      post({ type: "reply", id: msg.id, value: call("describe", msg.kind, msg.ident) });
      break;
    case "peek":
      post({ type: "reply", id: msg.id, value: call("peek", msg.expr) });
      break;
    case "cellChanges":
      post({ type: "reply", id: msg.id, value: call("cell_changes", msg.cell) });
      break;
    case "historySteps":
      post({ type: "reply", id: msg.id, value: call("history_steps") });
      break;
    case "historyItems":
      post({ type: "reply", id: msg.id, value: call("history_items", msg.step) });
      break;
    case "historyGoto":
      post({ type: "reply", id: msg.id, value: call("history_goto", msg.at) });
      break;
    case "live":
      post({ type: "reply", id: msg.id, value: call("set_live", msg.chart, msg.on) });
      break;
    case "clusterInfo":
      post({ type: "reply", id: msg.id, value: call("cluster_info", msg.field) });
      break;
    case "tableQuery":
      post({ type: "reply", id: msg.id, value: call("table_query", msg.expr, msg.kind, msg.full) });
      break;
    case "assign": {
      py!.globals.set("__items", JSON.stringify(msg.items));
      py!.globals.set("__name", msg.name);
      let value: unknown;
      try {
        value = py!.runPython("session.assign(__name, json.loads(__items))");
      } catch (e) {
        value = String(e).split("\n").filter(Boolean).pop();
      }
      post({ type: "reply", id: msg.id, value });
      break;
    }
    case "install":
      void installPackage(msg.name);
      break;
    case "click":
      py!.runPython(`session.last_click = (${Number(msg.x)}, ${Number(msg.y)})`);
      break;
    case "select":
      py!.globals.set("__sel", JSON.stringify(msg.nodes));
      py!.runPython("session.set_selection(json.loads(__sel))");
      break;
    case "query": {
      py!.globals.set("__q", JSON.stringify([msg.what, msg.kind ?? "n", msg.ids ?? null]));
      const text = py!.runPython(`
__w, __k, __i = json.loads(__q)
json.dumps(session.help_index() if __w == "help" else session.panel_data(__w, __k, __i))`) as string;
      post({ type: "reply", id: msg.id, value: JSON.parse(text) });
      break;
    }
    case "writeFile":
      // a dataset not yet downloaded is a lazy, read-only file: replace it
      if (py!.FS.analyzePath(`/data/${msg.name}`).exists) py!.FS.unlink(`/data/${msg.name}`);
      py!.FS.writeFile(`/data/${msg.name}`, msg.data);
      post({ type: "reply", id: msg.id, value: `/data/${msg.name}` });
      break;
  }
}

self.onmessage = async (ev: MessageEvent<ToWorker>) => {
  const msg = ev.data;
  if (msg.type === "init") {
    try {
      await init(msg);
    } catch (e) {
      post({ type: "error", text: `Failed to start Python: ${e}` });
      return;
    }
    while (queue.length) handle(queue.shift()!);
    return;
  }
  if (!py) {
    queue.push(msg);
    return;
  }
  try {
    handle(msg);
  } catch (e) {
    post({ type: "error", text: String(e) });
    if (msg.type === "run") post({ type: "done", id: msg.id, ok: false });
  }
};
