// ELK (elkjs: the Eclipse Layout Kernel compiled to JavaScript), called
// synchronously from Python (py/guess/elk.py), like Graphviz.
//
// elk-worker's own code is synchronous; only its message passing is not. We
// evaluate the file against a stand-in `self` (inheriting the real globals),
// so it installs its dispatcher there instead of on this worker's onmessage,
// and call that dispatcher directly. py/guess/elk.py's node_runner does the same.

const REGISTER = ["layered", "stress", "mrtree", "radial", "force", "disco", "sporeOverlap", "sporeCompaction", "rectpacking"];

type Reply = { id: number; data?: unknown; error?: { message?: string } | string };
type Host = { onmessage?: (e: { data: unknown }) => void; postMessage: (m: Reply) => void };

export async function loadElk(): Promise<(json: string) => string> {
  const src = (await import("elkjs/lib/elk-worker.min.js?raw")).default;
  let reply: Reply | null = null;
  // reads fall through to the real globals; plain functions (setTimeout, ...) are
  // bound to them, since browsers refuse them with another `this` ("Illegal
  // invocation"); constructors (Array, Date, ...) pass through unbound
  const own: Record<PropertyKey, unknown> = {};
  const bound = new Map<PropertyKey, unknown>();
  const g = globalThis as unknown as Record<PropertyKey, unknown>;
  const host = new Proxy(own, {
    get(t, k) {
      if (k in t) return t[k];
      const v = g[k];
      if (typeof v !== "function" || typeof k !== "string" || !/^[a-z]/.test(k)) return v;
      if (!bound.has(k)) bound.set(k, (v as (...a: unknown[]) => unknown).bind(globalThis));
      return bound.get(k);
    },
    set(t, k, v) { t[k] = v; return true; },
    has(t, k) { return k in t || k in g; },
  }) as unknown as Host;
  host.postMessage = (m) => { reply = m; };
  // no window/global/module, a stand-in self: it takes the web-worker branch on `host`
  new Function("self", "window", "global", "module", "exports", "document", src)(host, undefined, undefined, undefined, undefined, undefined);
  if (!host.onmessage) throw new Error("elk-worker did not install its dispatcher");
  const call = (msg: Record<string, unknown>) => {
    reply = null;
    host.onmessage!({ data: msg });
    const r = reply as Reply | null;
    if (!r) throw new Error("ELK returned nothing");
    if (r.error) throw new Error(typeof r.error === "string" ? r.error : String(r.error.message ?? r.error));
    return r.data;
  };
  call({ cmd: "register", id: -1, algorithms: REGISTER });
  return (json: string) => {
    const { graph, layoutOptions } = JSON.parse(json);
    return JSON.stringify(call({ cmd: "layout", id: 0, graph, layoutOptions }));
  };
}
