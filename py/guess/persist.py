"""Session files (.guess, JSON): the graph with all fields, removed elements,
saved states, ranges, hulls, legends and display settings — plus, for apps, a
startup script.

    saveSession("work.guess")          download a session file
    makeFromSession("work.guess")      load one (also: Open… / drag and drop)
    exportApp("app.guess", "ui.py")    a session that runs ui.py when opened with ?app=1

User variables are not saved (use log()/stoplog() to keep a script).
"""
import json
import os

from .colors import normalize
from .model import EDGE, NODE, Edge, GuessError, Node
from .states import Snapshot

VERSION = 2   # 2: background None means "follow the light/dark theme"


def _jsonable(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def _vals(d):
    return {k: _jsonable(v) for k, v in d.items()}


def serialize(session, script=None, app=False, subset=None, workspaces=True):
    """The session as JSON-able data. subset: node ids to keep (a subgraph:
    those nodes, the edges among them, the view settings; no history)."""
    g = session.graph
    # every element we know about: current, deleted, and referenced by states
    nodes, edges = [], []
    nidx, eidx = {}, {}

    def note_node(n):
        if id(n) not in nidx:
            nidx[id(n)] = len(nodes)
            nodes.append(n)

    def note_edge(e):
        if id(e) not in eidx:
            note_node(e._n1)
            note_node(e._n2)
            eidx[id(e)] = len(edges)
            edges.append(e)

    if subset is not None:
        for n in g._nodes_list():
            if n._id in subset:
                note_node(n)
        for e in g._edges_list():
            if e._n1._id in subset and e._n2._id in subset:
                note_edge(e)
        return _data(session, g, nodes, edges, nidx, eidx, subset=True)
    for n in g._nodes_list():
        note_node(n)
    for e in g._edges_list():
        note_edge(e)
    for x in g._deleted.values():
        (note_node if isinstance(x, Node) else note_edge)(x)
    for snap in g.states.values():
        for n in snap.nodes:
            note_node(n)
        for e in snap.edges:
            note_edge(e)
    groups = getattr(session, "groups", {})
    for mid, info in groups.items():
        meta = g._node_ids.get(mid)
        if meta is not None:
            note_node(meta)
        for n in info["members"]:
            note_node(n)
        for e in info["edges"]:
            note_edge(e)

    data = _data(session, g, nodes, edges, nidx, eidx)
    ws = getattr(session, "workspaces", None)
    if workspaces and ws and ws["stored"]:
        data["workspaces"] = {"current": ws["current"], "stored": ws["stored"],
                              "order": list(getattr(session, "_graph_order", []))}
    if script is not None:
        data["script"] = script
    if app:
        data["app"] = True
    return data


def _data(session, g, nodes, edges, nidx, eidx, subset=False):
    groups = {} if subset else getattr(session, "groups", {})

    def fields(schema):
        return [{"name": f.name, "type": f.type, "default": _jsonable(f.default)}
                for f in schema.values() if not f.builtin and f.compute is None]

    view = session.view
    data = {
        "format": "guess-session",
        "version": VERSION,
        "nodeFields": fields(g.node_schema),
        "edgeFields": fields(g.edge_schema),
        "nodes": [{"name": n._name, "alive": g._nodes.get(n._name) is n, "vals": _vals(n._vals)} for n in nodes],
        "edges": [{"s": nidx[id(e._n1)], "t": nidx[id(e._n2)], "d": e._directed,
                   "alive": e._id in g._edges and g._edges[e._id] is e, "vals": _vals(e._vals)} for e in edges],
        "deleted": [["n", nidx[id(x)]] if isinstance(x, Node) else ["e", eidx[id(x)]] for x in (() if subset else g._deleted.values())],
        "states": [{"key": k, "nodes": [[nidx[id(n)], _vals(v)] for n, v in snap.nodes.items()],
                    "edges": [[eidx[id(e)], _vals(v)] for e, v in snap.edges.items()]}
                   for k, snap in (() if subset else g.states.items())],
        "ranges": [["n", nidx[id(x)], iv] if isinstance(x, Node) else ["e", eidx[id(x)], iv]
                   for x, iv in g.ranges.items() if id(x) in nidx or id(x) in eidx],
        "bends": [[eidx[id(e)], pts] for e, pts in g.bends.items() if id(e) in eidx],
        "hulls": [{"nodes": [nidx[id(n)] for n in h._nodes if id(n) in nidx], "color": h._color}
                  for h in (() if subset else view.hulls.values())],
        "legends": [lg.record() for lg in view.legends.values()],
        "groups": [[nidx[id(g._node_ids[mid])], [nidx[id(n)] for n in info["members"]],
                    [eidx[id(e)] for e in info["edges"]], list(info["centre"])]
                   for mid, info in groups.items() if mid in g._node_ids],
        "view": {"background": view.background, "image": view.image, "arrow": view.arrow,
                 "curvature": view.curvature, "edgeColor": view.edge_color, "labels": view.labels,
                 "styles": view.styles, "pie": view.pie, "borderWidth": view.border_width,
                 "slides": getattr(view, "slides", [])},
    }
    if subset:
        data["ranges"] = []
        for n_rec in data["nodes"]:
            n_rec["alive"] = True
    return data


def load(session, data):
    if data.get("format") != "guess-session":
        raise GuessError("not a GUESS session file")
    if data.get("version", 0) > VERSION:
        raise GuessError("session file is from a newer version of GUESS")
    g = session.graph
    g.clear()
    g.states.clear()
    g.ranges.clear()
    view = session.view
    view.hulls.clear()
    view.legends.clear()
    for spec in data.get("nodeFields", []):
        g.addNodeField(spec["name"], spec["type"], spec["default"])
    for spec in data.get("edgeFields", []):
        g.addEdgeField(spec["name"], spec["type"], spec["default"])
    nodes = []
    for rec in data["nodes"]:
        n = g.addNode(rec["name"])
        n._vals.update(rec["vals"])
        nodes.append(n)
    edges = []
    for rec in data["edges"]:
        e = g.addEdge(nodes[rec["s"]], nodes[rec["t"]], rec["d"])
        e._vals.update(rec["vals"])
        edges.append(e)

    def elem(kind, i):
        return nodes[i] if kind == "n" else edges[i]

    # states reference element objects, so build them before removing anything
    for st in data.get("states", []):
        snap = Snapshot.__new__(Snapshot)
        snap.nodes = {nodes[i]: dict(v) for i, v in st["nodes"]}
        snap.edges = {edges[i]: dict(v) for i, v in st["edges"]}
        g.states[st["key"]] = snap
    for i, pts in data.get("bends", []):
        g.bends[edges[i]] = [tuple(p) for p in pts]
    for kind, i, iv in data.get("ranges", []):
        g.ranges[elem(kind, i)] = [tuple(p) for p in iv]
    deleted = {(k, i) for k, i in data.get("deleted", [])}
    gone = [e for i, (e, rec) in enumerate(zip(edges, data["edges"])) if not rec["alive"]]
    gone += [n for i, (n, rec) in enumerate(zip(nodes, data["nodes"])) if not rec["alive"]]
    g.remove(gone, keep=False)
    for k, i in deleted:
        x = elem(k, i)
        g._deleted[(type(x).__name__, x._id)] = x
    if hasattr(session, "groups"):
        session.groups.clear()
        for mi, members, eds, centre in data.get("groups", []):
            session.groups[nodes[mi]._id] = {"members": [nodes[i] for i in members],
                                             "edges": [edges[i] for i in eds], "centre": tuple(centre)}
    from .visuals import ConvexHull, GradientLegend, Legend
    for h in data.get("hulls", []):
        hull = ConvexHull(view, view.next_id(), [nodes[i] for i in h["nodes"]], h["color"])
        view.hulls[hull._id] = hull
    for rec in data.get("legends", []):
        if "ramp" in rec:
            lg = GradientLegend.__new__(GradientLegend)
            Legend.__init__(lg, view, view.next_id())
            lg._ramp = rec["ramp"]
        else:
            lg = Legend(view, view.next_id())
        lg._entries = rec["entries"]
        view.legends[lg._id] = lg
    v = data.get("view", {})
    bg = v.get("background")
    if data.get("version", 1) < 2 and bg == "white":
        bg = None    # version 1 stored the old default explicitly; let it follow the theme
    view.background = None if bg is None else normalize(bg)
    view.image = v.get("image")
    view.arrow = v.get("arrow", {"length": None, "width": None})
    view.curvature = float(v.get("curvature", 0.0))
    view.edge_color = v.get("edgeColor", "original")
    view.labels = {"outline": False, "cull": False, **v.get("labels", {})}
    view.styles = {str(k): list(map(str, c)) for k, c in v.get("styles", {}).items()}
    view.pie = v.get("pie")
    view.border_width = float(v.get("borderWidth", 0.75))
    view.slides = [dict(s) for s in v.get("slides", []) if s.get("state") in g.states or s.get("camera")]
    session.emit({"type": "slides", "slides": [{"note": s["note"]} for s in view.slides], "index": None})
    ws = getattr(session, "workspaces", None)
    if ws is not None and "workspaces" in data:
        ws["current"] = data["workspaces"]["current"]
        ws["stored"] = dict(data["workspaces"]["stored"])
        session._graph_order = list(data["workspaces"].get("order") or [ws["current"], *ws["stored"]])
        session.emit({"type": "graphs", "names": session._graph_order, "current": ws["current"]})
    view.changed()
    session.scene()
    return data


def install(session):
    def saveSession(filename="session.guess"):
        """Save the graph, fields, states, hulls, legends and view to a .guess file
        (downloaded by the browser). User variables are not saved."""
        text = json.dumps(serialize(session))
        _write_and_offer(session, filename, text)

    def makeFromSession(filename):
        """Load a .guess session file, replacing the current graph."""
        with open(filename, encoding="utf-8") as fh:
            data = json.load(fh)
        load(session, data)
        if data.get("script"):
            session.run_script(data["script"], filename=f"{filename}:script")
        print(f"loaded session {os.path.basename(filename)}: "
              f"{len(session.graph._nodes)} nodes, {len(session.graph._edges)} edges")

    def exportApp(filename="app.guess", script=None):
        """Save a session that opens as an app: with ?app=1 the console is hidden
        and `script` (Gython source, or the name of a .py file) runs on load —
        e.g. to dock panels and set graphevents handlers."""
        if script is not None and os.path.exists(str(script)):
            with open(script, encoding="utf-8") as fh:
                script = fh.read()
        text = json.dumps(serialize(session, script=script, app=True))
        _write_and_offer(session, filename, text)

    for fn in (saveSession, makeFromSession, exportApp):
        session.register_command(fn.__name__, fn)


def _write_and_offer(session, filename, text):
    with open(filename, "w", encoding="utf-8") as fh:
        fh.write(text)
    session.emit({"type": "download", "name": os.path.basename(filename), "text": text})


__all__ = ["serialize", "load", "install", "NODE", "EDGE", "Edge"]
