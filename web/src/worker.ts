/// <reference lib="webworker" />
// Runs Pyodide and the `guess` Python package. The graph model lives here.
import type { FromWorker, ToWorker } from "./protocol";

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
  globals: { set(name: string, v: unknown): void; get(name: string): any };
  FS: { mkdirTree(p: string): void; writeFile(p: string, data: string | Uint8Array): void };
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
}

// Pyodide's networkx recipe depends on matplotlib (and numpy, Pillow, ...).
// We only need the pure-Python core, so load the wheel by URL, which skips
// dependency resolution.
async function loadWithoutDeps(py: Py, names: string[]) {
  const lock = await (await fetch(PYODIDE_URL + "pyodide-lock.json")).json();
  const urls = names.map((n) => PYODIDE_URL + lock.packages[n].file_name);
  await py.loadPackage(urls);
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
      session.current_cell = msg.cell ?? null;
      const ok = call("run", msg.code) as boolean;
      post({ type: "done", id: msg.id, ok });
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
    case "move":
      py!.globals.set("__mv", JSON.stringify(msg.moves));
      py!.runPython("__m = json.loads(__mv)\nsession.move_nodes([__m[k:k + 3] for k in range(0, len(__m), 3)])");
      break;
    case "select":
      py!.globals.set("__sel", JSON.stringify(msg.nodes));
      py!.runPython("session.set_selection(json.loads(__sel))");
      break;
    case "writeFile":
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
