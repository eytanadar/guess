"""streamFrom(): follow a live graph stream (Gephi's Graph Streaming plugin).

    streamFrom("http://localhost:8080/workspace1?operation=getGraph")
    streamFrom("ws://example.org/graph")       # one JSON event per message
    stopStream()

Each event is a JSON object (one per line over HTTP), in the Gephi streaming
format:

    {"an": {"A": {"label": "Alice", "size": 10, "r": 1, "g": 0, "b": 0}}}   add nodes
    {"cn": {"A": {"dept": "sales"}}}                                       change nodes
    {"dn": {"A": {}}}                                                      delete nodes
    {"ae": {"AB": {"source": "A", "target": "B", "directed": false, "weight": 2}}}
    {"ce": {"AB": {"weight": 3}}}   {"de": {"AB": {}}}                     edges

The page reads the stream; the session applies events in batches between
commands. Streamed changes are not undo steps (they come from outside, like a
live feed).
"""
import math
import random

from .model import BOOL, DOUBLE, EDGE, NODE, STRING, Edge, GuessError

# Gephi attribute names -> GUESS fields
_NODE_ATTRS = {"label": "label", "x": "x", "y": "y"}
_SKIP = {"r", "g", "b", "size", "color", "z", "source", "target", "directed", "id"}


def _ftype(v):
    if isinstance(v, bool):
        return BOOL
    if isinstance(v, (int, float)):
        return DOUBLE
    return STRING


def _colour(attrs):
    if "color" in attrs and attrs["color"]:
        return attrs["color"]
    if all(k in attrs for k in ("r", "g", "b")):
        try:
            rgb = [float(attrs[k]) for k in ("r", "g", "b")]
        except (TypeError, ValueError):
            return None
        # Gephi sends 0..1; some clients send 0..255
        scale = 255 if max(rgb) <= 1 else 1
        return ",".join(str(int(round(max(0, min(255, c * scale))))) for c in rgb)
    return None


class Stream:
    def __init__(self, session):
        self.session = session
        self.edges = {}          # stream edge id -> Edge
        self.active = {}         # stream id -> url
        self.count = 0
        self.errors = 0
        self.unplaced = set()    # node ids added without a position (placed by their first edge)

    def _set(self, elem, kind, attrs):
        g = self.session.graph
        schema = g.node_schema if kind == NODE else g.edge_schema
        for k, v in attrs.items():
            if k in _SKIP or v is None:
                continue
            name = _NODE_ATTRS.get(k, k) if kind == NODE else ("label" if k == "label" else k)
            if not name.isidentifier():
                name = "".join(c if c.isalnum() or c == "_" else "_" for c in name).strip("_") or "attr"
            if name == "y" and kind == NODE:
                v = -float(v)                              # Gephi's y points up
            if name not in schema:
                ftype = _ftype(v)
                (g.addNodeField if kind == NODE else g.addEdgeField)(name, ftype, None)
            f = schema[name]
            if f.readonly:
                continue
            try:
                f.set(elem, v)
            except Exception:   # noqa: BLE001 - a value of the wrong type: keep the stream going
                self.errors += 1
        c = _colour(attrs)
        if c:
            elem.color = c
        if kind == NODE and "size" in attrs:
            try:
                s = max(1.0, float(attrs["size"]))
                elem.width = elem.height = s
            except (TypeError, ValueError):
                pass

    def _place(self, n, attrs):
        """A new node without a position: next to a neighbour if it has one,
        otherwise somewhere in the drawing."""
        if "x" in attrs and "y" in attrs:
            return
        g = self.session.graph
        others = [m for m in g._nodes_list() if m is not n]
        if not others:
            n.x, n.y = 500.0, 500.0
            return
        xs = [float(m.x) for m in others]
        ys = [float(m.y) for m in others]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        span = max(x1 - x0, y1 - y0, 200.0)
        n.x = (x0 + x1) / 2 + random.uniform(-0.5, 0.5) * span
        n.y = (y0 + y1) / 2 + random.uniform(-0.5, 0.5) * span

    def _near(self, n, other):
        """Put an unplaced node next to a placed neighbour."""
        if n._id in self.unplaced and other._id not in self.unplaced:
            a = random.uniform(0, 2 * math.pi)
            r = 20 + float(other.width)
            n.x = float(other.x) + r * math.cos(a)
            n.y = float(other.y) + r * math.sin(a)
            self.unplaced.discard(n._id)

    def apply(self, events):
        """Apply a batch of events (dicts); returns how many were applied."""
        g = self.session.graph
        done = 0
        for ev in events:
            if not isinstance(ev, dict):
                self.errors += 1
                continue
            for op, items in ev.items():
                if not isinstance(items, dict):
                    continue
                for ident, attrs in items.items():
                    attrs = attrs if isinstance(attrs, dict) else {}
                    try:
                        self._op(g, op, str(ident), attrs)
                        done += 1
                    except GuessError:
                        self.errors += 1
        self.count += done
        return done

    def _op(self, g, op, ident, attrs):
        if op in ("an", "cn"):
            new = ident not in g._nodes
            if op == "cn" and new:
                return
            n = g.addNode(ident)
            if new:
                self._place(n, attrs)
                if not ("x" in attrs and "y" in attrs):
                    self.unplaced.add(n._id)
            self._set(n, NODE, attrs)
        elif op == "dn":
            if ident in g._nodes:
                n = g._nodes[ident]
                for eid, e in list(self.edges.items()):
                    if e._n1 is n or e._n2 is n:
                        del self.edges[eid]
                g.removeNode(n)
        elif op == "ae":
            if ident in self.edges and self.edges[ident]._id in g._edges:
                self._set(self.edges[ident], EDGE, attrs)
                return
            s, t = attrs.get("source"), attrs.get("target")
            if s is None or t is None:
                raise GuessError(f"edge {ident} has no source or target")
            ends = []
            for name in (str(s), str(t)):
                n = g._nodes.get(name)
                if n is None:
                    n = g.addNode(name)
                    self._place(n, {})
                    self.unplaced.add(n._id)
                ends.append(n)
            a, b = ends
            self._near(a, b)
            self._near(b, a)
            e = g.addEdge(a, b, bool(attrs.get("directed", False)))
            self.edges[ident] = e
            self._set(e, EDGE, attrs)
        elif op == "ce":
            e = self.edges.get(ident)
            if e is not None and e._id in g._edges:
                self._set(e, EDGE, attrs)
        elif op == "de":
            e = self.edges.pop(ident, None)
            if isinstance(e, Edge) and e._id in g._edges:
                g.removeEdge(e)
        # "cg" (graph attributes) and anything else: ignored


def install(session):
    stream = Stream(session)
    session.stream = stream

    def streamFrom(url):
        """streamFrom(url) follows a live graph stream in the Gephi streaming
        format (Gephi's Graph Streaming plugin): an HTTP URL that sends one
        JSON event per line, such as Gephi's own
        "http://localhost:8080/workspace1?operation=getGraph", or a ws:// or
        wss:// WebSocket sending one event per message. Nodes and edges are
        added, changed and removed as events arrive (between commands, so a
        long command delays them); new nodes appear next to a neighbour.
        Streamed changes are not undo steps. stopStream() stops it. The
        server must allow cross-origin requests (CORS) from this page."""
        url = str(url).strip()
        if not url.startswith(("http://", "https://", "ws://", "wss://", "data:")):
            raise GuessError("streamFrom needs an http(s):// or ws(s):// URL")
        sid = f"s{len(stream.active) + stream.count + 1}"
        stream.active[sid] = url
        session.emit({"type": "stream", "op": "start", "id": sid, "url": url})
        print(f"following {url} (stopStream() stops it)")

    def stopStream():
        """stopStream() stops every stream started with streamFrom."""
        n = len(stream.active)
        stream.active.clear()
        session.emit({"type": "stream", "op": "stop"})
        print(f"stopped {n} stream{'' if n == 1 else 's'}" if n else "no stream was running")

    for fn in (streamFrom, stopStream):
        session.register_command(fn.__name__, fn)


def apply_batch(session, sid, events):
    """Called by the page with events from stream `sid`: apply them outside any
    command (no undo step) and send the changes to the display."""
    stream = session.stream
    if sid not in stream.active:
        return 0
    g = session.graph
    saved, g.journal = g.journal, None
    try:
        done = stream.apply(events)
    finally:
        g.journal = saved
        session.flush()
    return done


def end(session, sid, error=None):
    """The page says stream `sid` ended (closed, or failed)."""
    url = session.stream.active.pop(sid, None)
    if url is None:
        return
    text = f"stream from {url} {'failed: ' + error if error else 'ended'} ({session.stream.count} events applied)\n"
    session.emit({"type": "text", "text": text})


__all__ = ["install", "apply_batch", "end", "Stream"]
