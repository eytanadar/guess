"""ELK layouts: the Eclipse Layout Kernel (elkjs, compiled to JavaScript) in the page.
    elkLayout()                                   layered (Sugiyama-style), edges routed
    elkLayout("mrtree"); elkLayout("radial")      trees; radial trees
    elkLayout("stress"); elkLayout("force")       distance-based and force-directed
    elkLayout("layered", direction="RIGHT", spacing=40, options={"layered.crossingMinimization.strategy": "INTERACTIVE"})
The page loads ELK (about 1.6 MB) in the background after start-up, like
Graphviz; Python calls it synchronously with an ELK JSON graph.
"""
import json

import numpy as np

from .model import GuessError

ALGORITHMS = ("layered", "mrtree", "radial", "stress", "force", "disco", "box",
              "rectpacking", "random", "sporeOverlap", "sporeCompaction")
_DIRECTIONS = ("RIGHT", "LEFT", "DOWN", "UP")
# what elk-api registers by default ("box" and "random" are built in)
REGISTER = ("layered", "stress", "mrtree", "radial", "force", "disco",
            "sporeOverlap", "sporeCompaction", "rectpacking")

_RUNNER = [None]          # set by tests / tools: fn(json text) -> json text


def runner():
    """A function (ELK json graph text) -> laid-out json text, or None."""
    if _RUNNER[0] is not None:
        return _RUNNER[0]
    try:
        from js import guessElkLayout       # the page's worker (Pyodide)
    except ImportError:
        return None
    try:
        if guessElkLayout is None or not callable(guessElkLayout):
            return None
    except Exception:  # noqa: BLE001 - a JsProxy for undefined
        return None
    return lambda text: str(guessElkLayout(text))


def need():
    r = runner()
    if r is None:
        raise GuessError("ELK loads in the background a few seconds after GUESS starts; "
                         "try again in a moment")
    return r


def node_runner(web_dir):
    """A runner that calls the same elkjs through Node (for the Python tests).
    None if Node or elkjs isn't installed."""
    import pathlib
    import shutil
    import subprocess
    mod = pathlib.Path(web_dir).resolve() / "node_modules" / "elkjs" / "lib" / "elk-worker.min.js"
    node = shutil.which("node")
    if not node or not mod.exists():
        return None
    # the same loading as web/src/elk.ts: a stand-in self, the dispatcher called synchronously
    script = (f"const src=require('fs').readFileSync({json.dumps(str(mod))},'utf8');"
              "let r=null;const host=Object.create(globalThis);host.postMessage=m=>{r=m;};"
              "new Function('self','window','global','module','exports','document',src)(host,undefined,undefined,undefined,undefined,undefined);"
              "const call=m=>{r=null;host.onmessage({data:m});if(r.error){process.stderr.write(String(r.error.message||r.error));process.exit(1);}return r.data;};"
              f"call({{cmd:'register',id:-1,algorithms:{json.dumps(list(REGISTER))}}});"
              "const c=[];process.stdin.on('data',d=>c.push(d));process.stdin.on('end',()=>{"
              "const a=JSON.parse(Buffer.concat(c).toString());"
              "process.stdout.write(JSON.stringify(call({cmd:'layout',id:0,graph:a.graph,layoutOptions:a.layoutOptions})));});")

    def run(text):
        p = subprocess.run([node, "-e", script], input=text, capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise GuessError(f"ELK: {p.stderr.strip().splitlines()[-1] if p.stderr.strip() else 'failed'}")
        return p.stdout
    return run


def build_graph(snap, edges, algorithm, options):
    """The ELK JSON graph: nodes with their sizes (pinned nodes at their
    positions), edges by id, and layout options with the elk. prefix."""
    children = []
    for i, n in enumerate(snap.nodes):
        c = {"id": f"n{n._id}", "width": max(float(snap.size[i, 0]), 1.0),
             "height": max(float(snap.size[i, 1]), 1.0)}
        if snap.fixed[i]:
            c["x"], c["y"] = float(snap.pos[i, 0]), float(snap.pos[i, 1])
        children.append(c)
    elk_edges = [{"id": f"e{e._id}", "sources": [f"n{e._n1._id}"], "targets": [f"n{e._n2._id}"]}
                 for e in edges if e._n1 is not e._n2]
    opts = {"elk.algorithm": algorithm}
    for k, v in options.items():
        key = k if k.startswith(("elk.", "org.eclipse.elk.")) else f"elk.{k}"
        opts[key] = v if isinstance(v, str) else json.dumps(v)
    return {"id": "root", "layoutOptions": opts, "children": children, "edges": elk_edges}


def install(session):
    from .layouts import _Layouts
    lay = _Layouts(session)

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    @cmd
    def elkLayout(algorithm="layered", direction=None, spacing=None, route=True, options=None):
        """elkLayout() runs an ELK (Eclipse Layout Kernel) layout; the default,
        "layered", is a Sugiyama-style layered drawing with its edges routed
        around the nodes. Other algorithms: "mrtree", "radial", "stress",
        "force", "disco", "box", "rectpacking", "random". direction= "DOWN"
        (default for layered), "RIGHT", "LEFT" or "UP"; spacing= the space
        between nodes; route=false keeps edges straight; options= any other ELK
        options, e.g. options={"layered.spacing.nodeNodeBetweenLayers": 80}
        (the "elk." prefix is added). Pinned nodes keep their positions where
        the algorithm supports it."""
        if algorithm not in ALGORITHMS:
            raise GuessError(f"elkLayout: unknown algorithm {algorithm!r}; one of {', '.join(ALGORITHMS)}")
        opts = dict(options or {})
        if direction is not None:
            d = str(direction).upper()
            if d not in _DIRECTIONS:
                raise GuessError(f'elkLayout direction is "DOWN", "RIGHT", "LEFT" or "UP", not {direction!r}')
            opts["direction"] = d
        elif algorithm == "layered":
            opts.setdefault("direction", "DOWN")
        if spacing is not None:
            opts["spacing.nodeNode"] = float(spacing)
            if algorithm == "layered":
                opts.setdefault("layered.spacing.nodeNodeBetweenLayers", float(spacing))
        if algorithm == "layered" and not route:
            opts.setdefault("edgeRouting", "POLYLINE")
        run = need()
        s = lay.snap()
        if s.n == 0:
            return
        g = session.graph
        edges = [e for e in g._edges_list() if e._n1._id in s.index and e._n2._id in s.index]
        text = json.dumps({"graph": build_graph(s, edges, algorithm, opts), "layoutOptions": {}})
        try:
            result = json.loads(run(text))
        except ValueError:
            raise GuessError("ELK returned no layout") from None
        P = np.array(s.pos, float, copy=True)
        index = {f"n{n._id}": i for i, n in enumerate(s.nodes)}
        for c in result.get("children", []):
            i = index.get(c.get("id"))
            if i is not None and not s.fixed[i] and "x" in c:
                P[i] = (float(c["x"]), float(c["y"]))
        lay.apply(s, P)
        by_id = {f"e{e._id}": e for e in edges}
        for ee in result.get("edges", []):
            e = by_id.get(ee.get("id"))
            if e is None or e._n1 is e._n2:
                continue
            pts = [(p["x"], p["y"]) for sec in ee.get("sections", []) for p in sec.get("bendPoints", [])]
            # only layered routes edges around nodes; other algorithms leave them straight
            g.set_bends(e, pts if route and algorithm == "layered" else [])
