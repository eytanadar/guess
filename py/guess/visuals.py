"""Display-level objects: convex hulls, legends, background, arrow sizes.

These live in the session and are sent to the front end as one "overlay"
message whenever they change (they are small). Hull geometry is computed by
the renderer from the member nodes' current positions, so hulls follow
layouts and dragging automatically.
"""
import base64
import mimetypes
import os

from . import colors
from .model import Edge, GSet, GuessError, Node, elements_of

DEFAULT_CURVATURE = 1.2    # Gephi's default arc curviness (radius = length / curvature)


class ConvexHull:
    """A shaded hull around a group of nodes. Returned by createConvexHull."""

    def __init__(self, view, hid, nodes, color):
        object.__setattr__(self, "_view", view)
        object.__setattr__(self, "_id", hid)
        object.__setattr__(self, "_nodes", nodes)
        object.__setattr__(self, "_color", colors.normalize(color))

    @property
    def nodes(self):
        return GSet(self._nodes, f"hull {self._id}")

    @property
    def color(self):
        return self._color

    def __setattr__(self, name, value):
        if name != "color":
            raise GuessError(f"convex hulls have no settable attribute '{name}'")
        object.__setattr__(self, "_color", colors.normalize(value))
        self._view.changed()

    def __repr__(self):
        return f"<hull {self._id}: {len(self._nodes)} nodes>"

    def record(self):
        rgb, a = colors.to_rgba_int(self._color)
        return {"i": self._id, "nodes": [n._id for n in self._nodes], "c": rgb, "a": a}


class Legend:
    """A legend box on the display. ``l = Legend(); l.add(bob, "managers")``.

    Entries snapshot the look of the node, edge or hull at the time they are added.
    """

    def __init__(self, view, lid):
        self._view = view
        self._id = lid
        self._entries = []

    def add(self, obj, annotation):
        if isinstance(obj, Node):
            rgb, a = colors.to_rgba_int(obj.color)
            entry = {"k": "n", "c": rgb, "a": a, "s": obj.style, "t": str(annotation)}
        elif isinstance(obj, Edge):
            rgb, a = colors.to_rgba_int(obj.color)
            entry = {"k": "e", "c": rgb, "a": a, "w": obj.width, "t": str(annotation)}
        elif isinstance(obj, ConvexHull):
            rgb, a = colors.to_rgba_int(obj.color)
            entry = {"k": "h", "c": rgb, "a": a, "t": str(annotation)}
        elif isinstance(obj, str) and colors.parse(obj) is not None:
            rgb, a = colors.to_rgba_int(obj)
            entry = {"k": "n", "c": rgb, "a": a, "s": 1, "t": str(annotation)}
        else:
            raise GuessError("Legend.add needs a node, edge, convex hull or color")
        self._entries = [e for e in self._entries if e["t"] != entry["t"]] + [entry]
        self._view.changed()

    def remove(self, annotation=None):
        """remove(text) drops one entry; remove() deletes the whole legend."""
        if annotation is None:
            self._view.legends.pop(self._id, None)
        else:
            self._entries = [e for e in self._entries if e["t"] != str(annotation)]
        self._view.changed()

    def removeAll(self):
        self._entries = []
        self._view.changed()

    def __repr__(self):
        return f"<legend {self._id}: {len(self._entries)} entries>"

    def record(self):
        return {"i": self._id, "entries": self._entries}


class GradientLegend(Legend):
    """A color ramp legend: GradientLegend(startColor, endColor, min, max)."""

    def __init__(self, view, lid, start, end, lo=0, hi=1):
        super().__init__(view, lid)
        self._ramp = {"from": colors.to_rgba_int(start)[0], "to": colors.to_rgba_int(end)[0],
                      "min": lo, "max": hi}

    def record(self):
        r = super().record()
        r["ramp"] = self._ramp
        return r


class View:
    def __init__(self, session):
        self.session = session
        self.hulls = {}
        self.legends = {}
        self.background = None      # None: the theme's background (white, or dark in dark mode)
        self.image = None           # {"url", "x", "y"}
        self.arrow = {"length": None, "width": None}
        self.curvature = 0.0        # 0 = straight edges; > 0 = Gephi-style curves
        self.edge_color = "original"  # or source / target / mixed (node colours)
        self.labels = {"outline": False, "cull": False}
        self.styles = {}            # name -> [Gython lines] (defineStyle / applyStyle)
        self.pie = None             # pie-chart nodes (glyphs.py)
        self.border_width = 0.75
        self._next = 1
        self.dirty = True
        self.version = 0

    def changed(self):
        self.dirty = True
        self.version += 1

    def capture(self):
        """Everything undo needs to put the view back as it is now."""
        return {"hulls": [(h, h._color, list(h._nodes)) for h in self.hulls.values()],
                "legends": [(lg, list(lg._entries)) for lg in self.legends.values()],
                "background": self.background, "image": self.image, "arrow": dict(self.arrow),
                "curvature": self.curvature, "edge_color": self.edge_color, "labels": dict(self.labels),
                "styles": {k: list(v) for k, v in self.styles.items()},
                "pie": self.pie, "border_width": self.border_width,
                "slides": [dict(s) for s in getattr(self, "slides", [])]}

    def restore(self, snap):
        self.hulls = {}
        for h, color, nodes in snap["hulls"]:
            object.__setattr__(h, "_color", color)
            h._nodes[:] = nodes
            self.hulls[h._id] = h
        self.legends = {}
        for lg, entries in snap["legends"]:
            lg._entries = list(entries)
            self.legends[lg._id] = lg
        self.background, self.image = snap["background"], snap["image"]
        self.arrow, self.curvature = dict(snap["arrow"]), snap["curvature"]
        self.edge_color, self.labels = snap["edge_color"], dict(snap["labels"])
        self.styles = {k: list(v) for k, v in snap.get("styles", {}).items()}
        self.pie, self.border_width = snap.get("pie"), snap.get("border_width", 0.75)
        self.slides = [dict(s) for s in snap.get("slides", [])]
        self.session.emit({"type": "slides", "slides": [{"note": s["note"]} for s in self.slides], "index": None})
        for n in self.session.graph._nodes_list():
            self.session.graph._mark(n)
        self.changed()

    def next_id(self):
        self._next += 1
        return self._next

    def record(self):
        live = self.session.graph._node_ids
        hulls = []
        for h in self.hulls.values():
            h._nodes[:] = [n for n in h._nodes if live.get(n._id) is n]
            hulls.append(h.record())
        bg = None if self.background is None else colors.to_rgba_int(self.background, (255, 255, 255, 255))[0]
        return {"type": "overlay", "background": bg, "image": self.image, "arrow": self.arrow,
                "curvature": self.curvature, "edgeColor": self.edge_color, "labels": dict(self.labels), "styles": list(self.styles),
                "pie": [colors.to_rgba_int(c)[0] for c in self.pie["colors"]] if self.pie else None,
                "borderWidth": self.border_width, "hulls": hulls, "legends": [l.record() for l in self.legends.values()]}


def _data_url(path):
    with open(path, "rb") as fh:
        data = fh.read()
    mime = mimetypes.guess_type(path)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def install(session):
    view = View(session)
    session.view = view
    reg = session.register_command

    def createConvexHull(seq, color="200,200,255,90"):
        """Shade the convex hull around the nodes in seq (edges contribute their endpoints)."""
        nodes = []
        seen = set()
        for x in elements_of(seq):
            for n in ((x,) if isinstance(x, Node) else (x._n1, x._n2) if isinstance(x, Edge) else ()):
                if id(n) not in seen:
                    seen.add(id(n))
                    nodes.append(n)
        if not nodes:
            raise GuessError("createConvexHull needs nodes or edges")
        h = ConvexHull(view, view.next_id(), nodes, color)
        view.hulls[h._id] = h
        view.changed()
        return h

    def removeConvexHull(hull):
        """Remove one hull."""
        view.hulls.pop(hull._id, None)
        view.changed()

    def removeConvexHulls(seq=None):
        """Remove the given hulls, or all hulls."""
        if seq is None:
            view.hulls.clear()
        else:
            for h in seq:
                view.hulls.pop(h._id, None)
        view.changed()

    def getConvexHulls():
        """All hulls currently shown."""
        return list(view.hulls.values())

    def make_legend():
        lg = Legend(view, view.next_id())
        view.legends[lg._id] = lg
        view.changed()
        return lg
    make_legend.__name__ = "Legend"
    make_legend.__doc__ = Legend.__doc__

    def make_gradient(start, end, lo=0, hi=1):
        lg = GradientLegend(view, view.next_id(), start, end, lo, hi)
        view.legends[lg._id] = lg
        view.changed()
        return lg
    make_gradient.__name__ = "GradientLegend"
    make_gradient.__doc__ = GradientLegend.__doc__

    def setDisplayBackground(color):
        """Set the display's background color; setDisplayBackground(None) goes back
        to the theme's (white, or dark in dark mode)."""
        view.background = None if color is None else colors.normalize(color)
        view.changed()

    def getDisplayBackground():
        """The display background color, or None when it follows the light/dark theme."""
        return view.background

    def setBackgroundImage(source, x=0, y=0):
        """Show an image (a file you opened, or a URL) behind the graph with its
        top-left corner at (x, y) in graph coordinates."""
        url = source
        if os.path.exists(source):
            url = _data_url(source)
        view.image = {"url": url, "x": float(x), "y": float(y)}
        view.changed()

    def removeBackgroundImage():
        """Remove the background image set with setBackgroundImage."""
        view.image = None
        view.changed()

    def overrideArrowLength(length):
        """Fix the arrowhead length (graph units) for all directed edges; None resets."""
        view.arrow["length"] = None if length is None else float(length)
        view.changed()

    def overrideArrowWidth(width):
        """Fix the arrowhead width (graph units) for all directed edges; None resets."""
        view.arrow["width"] = None if width is None else float(width)
        view.changed()

    def curvedEdges(on=True):
        """curvedEdges() draws every edge as a circular arc running clockwise from
        source to target, as in Gephi's preview, so a->b and b->a separate and
        direction reads without arrows. curvedEdges(false) goes back to straight
        lines; curvedEdges(k) sets the curvature: the arc radius is edge length / k
        (default 1.2, as in Gephi; 2 gives semicircles)."""
        if isinstance(on, bool) or on is None:
            view.curvature = DEFAULT_CURVATURE if on else 0.0
        else:
            c = float(on)
            if not 0 <= c <= 2:
                raise GuessError("curvature should be between 0 (straight) and 2 (semicircles)")
            view.curvature = c
        view.changed()

    def setEdgeColorMode(mode="original"):
        """setEdgeColorMode("mixed") draws each edge in the blend of its endpoints'
        colours; "source" / "target" use one endpoint's colour; "original" (the
        default) uses the edge's own color field. As in Gephi's preview."""
        mode = str(mode).lower()
        if mode not in ("original", "source", "target", "mixed"):
            raise GuessError('edge colour mode is "original", "source", "target" or "mixed"')
        view.edge_color = mode
        view.changed()

    def labelOutlines(on=True):
        """labelOutlines() draws a halo in the background colour around labels so
        they stay readable over edges; labelOutlines(false) turns it off."""
        view.labels["outline"] = bool(on)
        view.changed()

    def hideOverlappingLabels(on=True):
        """hideOverlappingLabels() hides labels that would overlap a label of a
        bigger node, rechecked as you zoom; hideOverlappingLabels(false) shows all."""
        view.labels["cull"] = bool(on)
        view.changed()

    def select(seq=None):
        """select(seq) selects these nodes on the display (edges select their
        endpoints) and binds them to `sel`, as a box, lasso or shift-click does;
        select() clears the selection. On the display: shift-drag draws a box,
        alt-drag a lasso, shift-click adds or removes one node."""
        ids, seen = [], set()
        for x in (elements_of(seq) if seq is not None else ()):
            for n in ((x,) if isinstance(x, Node) else (x._n1, x._n2) if isinstance(x, Edge) else ()):
                if n._id not in seen:
                    seen.add(n._id)
                    ids.append(n._id)
        session.set_selection(ids)
        session.emit({"type": "select", "nodes": ids})
        return session.ns["sel"]

    session.set_selection([])

    def _export(fmt):
        def fn(filename=f"guess.{fmt}"):
            session.emit({"type": "export", "format": fmt, "name": os.path.basename(filename)})
        fn.__name__ = f"export{fmt.upper()}"
        fn.__doc__ = (f"Save the display as {fmt.upper()} (downloaded by the browser)."
                      + (" Vector: the whole graph, not just the visible area." if fmt == "svg" else ""))
        return fn

    recording = {"on": False}

    def startMovie(fps=30, filename="guess.webm"):
        """Record the display (graph canvas) as a WebM video until stopMovie().
        Everything shown — layouts, morphs, edits, panning — is captured."""
        name = os.path.basename(str(filename))
        if not name.lower().endswith(".webm"):
            name = os.path.splitext(name)[0] + ".webm"
        recording["on"] = True
        session.emit({"type": "movie", "op": "start", "fps": int(fps), "name": name})

    def stopMovie():
        """Stop recording and download the video."""
        if not recording["on"]:
            raise GuessError("no movie is being recorded (use startMovie)")
        recording["on"] = False
        session.emit({"type": "movie", "op": "stop"})

    reg("startMovie", startMovie)
    reg("stopMovie", stopMovie)

    for fmt in ("png", "jpg", "svg"):
        f = _export(fmt)
        reg(f.__name__, f)

    for fn in (createConvexHull, removeConvexHull, removeConvexHulls, getConvexHulls,
               setDisplayBackground, getDisplayBackground, setBackgroundImage,
               removeBackgroundImage, overrideArrowLength, overrideArrowWidth, curvedEdges,
               setEdgeColorMode, labelOutlines, hideOverlappingLabels, select):
        reg(fn.__name__, fn)
    # Legend()/GradientLegend() are constructors: don't auto-call on a bare name
    session._bind("Legend", make_legend, kind="command")
    session._bind("GradientLegend", make_gradient, kind="command")
