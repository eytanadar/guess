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
from .model import NODE, Edge, GSet, GuessError, Node, elements_of

DEFAULT_CURVATURE = 1.2    # Gephi's default arc curviness (radius = length / curvature)


HULL_SHAPES = ("hull", "box", "ellipse")


def _hull_shape(shape):
    s = str(shape).lower()
    if s not in HULL_SHAPES:
        raise GuessError('the shape around a group is "hull", "box" or "ellipse"')
    return s


class ConvexHull:
    """A shaded shape around a group of nodes: its convex hull (the default),
    a box or an ellipse, either upright or turned to fit the group (rotate).
    Returned by createConvexHull and encircle; .color, .shape, .rotate and
    .padding can be changed."""

    def __init__(self, view, hid, nodes, color, shape="hull", rotate=False, padding=6):
        object.__setattr__(self, "_view", view)
        object.__setattr__(self, "_id", hid)
        object.__setattr__(self, "_nodes", nodes)
        object.__setattr__(self, "_color", colors.normalize(color))
        object.__setattr__(self, "_shape", _hull_shape(shape))
        object.__setattr__(self, "_rotate", bool(rotate))
        object.__setattr__(self, "_pad", float(padding))

    @property
    def nodes(self):
        return GSet(self._nodes, f"hull {self._id}")

    @property
    def color(self):
        return self._color

    @property
    def shape(self):
        return self._shape

    @property
    def rotate(self):
        return self._rotate

    @property
    def padding(self):
        return self._pad

    def __setattr__(self, name, value):
        if name == "color":
            object.__setattr__(self, "_color", colors.normalize(value))
        elif name == "shape":
            object.__setattr__(self, "_shape", _hull_shape(value))
        elif name == "rotate":
            object.__setattr__(self, "_rotate", bool(value))
        elif name == "padding":
            object.__setattr__(self, "_pad", float(value))
        else:
            raise GuessError(f"convex hulls have no settable attribute '{name}' (color, shape, rotate, padding)")
        self._view.changed()

    def __repr__(self):
        kind = "hull" if self._shape == "hull" else ("turned " if self._rotate else "") + self._shape
        return f"<{kind} {self._id}: {len(self._nodes)} nodes>"

    def record(self):
        rgb, a = colors.to_rgba_int(self._color)
        r = {"i": self._id, "nodes": [n._id for n in self._nodes], "c": rgb, "a": a}
        if self._shape != "hull":
            r["sh"] = self._shape
        if self._rotate:
            r["rot"] = True
        if self._pad != 6:
            r["pad"] = self._pad
        return r


class Legend:
    """A legend box on the display. ``l = Legend(); l.add(bob, "managers")``.

    Entries snapshot the look of the node, edge or hull at the time they are added.
    """

    def __init__(self, view, lid):
        self._view = view
        self._id = lid
        self._entries = []
        self._ramp = None       # a colour ramp (GradientLegend, or legendFor on a gradient)
        self._auto = None       # legendFor: {"field", "kind", "title"}; rebuilt when colours change

    def add(self, obj, annotation):
        """add(node, edge, hull or colour, text) adds an entry. A legend made by
        legendFor stops following the colours once you change it yourself."""
        self._auto = None
        self._add(obj, annotation)

    def _add(self, obj, annotation, notify=True):
        if isinstance(obj, (list, tuple, GSet)) and len(obj) == 1:   # e.g. lg.add(v1 - v2, "…")
            obj = obj[0]
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
        if notify:
            self._view.changed()

    def note(self, text):
        """A line of text with no swatch, e.g. "… 32 more"."""
        self._auto = None
        self._note(text)

    def _note(self, text, notify=True):
        self._entries = [e for e in self._entries if e["t"] != str(text)] + [{"k": "x", "c": 0, "a": 0, "t": str(text)}]
        if notify:
            self._view.changed()

    def remove(self, annotation=None):
        """remove(text) drops one entry; remove() deletes the whole legend."""
        if annotation is None:
            self._view.legends.pop(self._id, None)
        else:
            self._auto = None
            self._entries = [e for e in self._entries if e["t"] != str(annotation)]
        self._view.changed()

    def removeAll(self):
        self._auto = None
        self._entries = []
        self._view.changed()

    def __repr__(self):
        if self._ramp:
            return f"<gradient legend {self._id}: {self._ramp['min']} to {self._ramp['max']}>"
        return f"<legend {self._id}: {len(self._entries)} entries>"

    def record(self):
        r = {"i": self._id, "entries": self._entries}
        if self._ramp:
            r["ramp"] = self._ramp
        if self._auto:
            r["auto"] = self._auto
        return r

    def refresh(self):
        """legendFor legends: rebuild from the field's current colours. True if
        anything changed."""
        if not self._auto:
            return False
        g = self._view.session.graph
        schema = g.node_schema if self._auto["kind"] == NODE else g.edge_schema
        f = schema.get(self._auto["field"])
        if f is None:
            return False
        from .styles import fill_legend
        before = (self._entries, self._ramp)
        fill_legend(self, f, self._auto.get("title"))
        return (self._entries, self._ramp) != before


class GradientLegend(Legend):
    """A color ramp legend: GradientLegend(startColor, endColor, min, max[, tickEvery])
    shows the ramp from min to max, with a tick mark every tickEvery units."""

    def __init__(self, view, lid, start, end, lo=0, hi=1, ticks=None):
        super().__init__(view, lid)
        self._ramp = {"from": colors.to_rgba_int(start)[0], "to": colors.to_rgba_int(end)[0],
                      "min": lo, "max": hi}
        if ticks:
            self._ramp["ticks"] = float(ticks)



class Drawing:
    """A line, text, box or circle drawn on the display (drawLine, drawText,
    drawRect, drawCircle). .remove() takes it away."""

    def __init__(self, view, did):
        self._view, self._id = view, did

    def _rec(self):
        return next((d for d in self._view.drawings if d["i"] == self._id), None)

    def remove(self):
        self._view.drawings = [d for d in self._view.drawings if d["i"] != self._id]
        self._view.changed()

    def __eq__(self, other):
        return isinstance(other, Drawing) and other._id == self._id

    def __hash__(self):
        return hash(("drawing", self._id))

    def __repr__(self):
        d = self._rec()
        if d is None:
            return f"<drawing {self._id}: removed>"
        if d["k"] == "text":
            return f"<drawing {self._id}: text {d['t']!r}>"
        return f"<drawing {self._id}: {d['k']}>"


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
        self.directed = "taper"     # how directed edges show direction: taper / fade / arrow (directedEdges)
        self.labels = {"outline": False, "cull": False, "along": False, "placement": "candidates", "screen": False}
        self.styles = {}            # name -> [Gython lines] (defineStyle / applyStyle)
        self.pie = None             # pie-chart nodes (glyphs.py)
        self.drag = {}              # declarative dragging context: ring, axes
        self.guides = []            # labelled lines drawn under the graph (hive plot axes)
        self.map = None             # geoLayout's outlines: {"rings", "fill", "stroke"}
        self.guides_note = ""
        self.drawings = []          # drawLine/drawText/drawRect/drawCircle records (plain dicts)
        self.border_width = 0.75
        self.raise_changed = True   # a node or edge whose appearance changes is drawn on top
        self.hover_fields = {"n": [], "e": []}   # fields the hover tooltip shows at once (hoverFields)
        self._next = 1
        self.dirty = True
        self.version = 0

    def changed(self):
        self.dirty = True
        self.version += 1

    def reset_for_new_graph(self):
        """A new graph was loaded: drop what belonged to the old one (legends,
        hulls, hive plot axes, pies, drag context, slides, and the geoLayout map
        and background image, which are placed in the old graph's coordinates).
        Display preferences (background colour, curved edges, edge colours,
        label options, styles) stay."""
        had = bool(self.legends or self.hulls or self.guides or self.pie or self.drag or getattr(self, "slides", None)
                   or self.map or self.image or self.drawings)
        self.map = None
        self.drawings = []
        self.image = None
        self.legends = {}
        self.hulls = {}
        self.guides = []
        self.guides_note = ""
        self.drag = {}
        self.pie = None
        self.pie_legend = None
        if getattr(self, "slides", None):
            self.slides = []
            self.session.emit({"type": "slides", "slides": [], "index": None})
        if had:
            self.changed()

    def refresh_legends(self):
        """Bring legendFor legends up to date with the colours (after each command)."""
        if any(lg._auto for lg in self.legends.values()):
            if [lg.refresh() for lg in list(self.legends.values())].count(True):
                self.changed()

    def _drag_record(self):
        return dict(self.drag)

    def capture(self):
        """Everything undo needs to put the view back as it is now."""
        return {"hulls": [(h, h._color, list(h._nodes), (h._shape, h._rotate, h._pad)) for h in self.hulls.values()],
                "legends": [(lg, list(lg._entries), lg._ramp, lg._auto) for lg in self.legends.values()],
                "background": self.background, "image": self.image, "arrow": dict(self.arrow),
                "curvature": self.curvature, "edge_color": self.edge_color, "labels": dict(self.labels),
                "directed": self.directed,
                "styles": {k: list(v) for k, v in self.styles.items()},
                "pie": self.pie, "border_width": self.border_width,
                "slides": [dict(s) for s in getattr(self, "slides", [])],
                "guides": [dict(x) for x in self.guides], "guides_note": self.guides_note,
                "map": self.map, "raise_changed": self.raise_changed,
                "drawings": [dict(d) for d in self.drawings],
                "hover_fields": {k: list(v) for k, v in self.hover_fields.items()}}

    def restore(self, snap):
        self.hulls = {}
        for h, color, nodes, *look in snap["hulls"]:
            object.__setattr__(h, "_color", color)
            if look:
                shape, rotate, pad = look[0]
                object.__setattr__(h, "_shape", shape)
                object.__setattr__(h, "_rotate", rotate)
                object.__setattr__(h, "_pad", pad)
            h._nodes[:] = nodes
            self.hulls[h._id] = h
        self.legends = {}
        for lg, entries, ramp, auto in snap["legends"]:
            lg._entries, lg._ramp, lg._auto = list(entries), ramp, auto
            self.legends[lg._id] = lg
        self.background, self.image = snap["background"], snap["image"]
        self.arrow, self.curvature = dict(snap["arrow"]), snap["curvature"]
        self.edge_color, self.labels = snap["edge_color"], dict(snap["labels"])
        self.directed = snap.get("directed", "taper")
        self.styles = {k: list(v) for k, v in snap.get("styles", {}).items()}
        self.pie, self.border_width = snap.get("pie"), snap.get("border_width", 0.75)
        self.slides = [dict(s) for s in snap.get("slides", [])]
        self.guides = [dict(x) for x in snap.get("guides", [])]
        self.guides_note = snap.get("guides_note", "")
        self.map = snap.get("map")
        self.drawings = [dict(d) for d in snap.get("drawings", [])]
        self.raise_changed = snap.get("raise_changed", True)
        self.hover_fields = {k: list(v) for k, v in snap.get("hover_fields", {"n": [], "e": []}).items()}
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
                "curvature": self.curvature, "edgeColor": self.edge_color, "directedStyle": self.directed,
                "labels": dict(self.labels), "styles": list(self.styles),
                "pie": [colors.to_rgba_int(c)[0] for c in self.pie["colors"]] if self.pie else None,
                "borderWidth": self.border_width, "raiseChanged": self.raise_changed,
                "hoverFields": {k: list(v) for k, v in self.hover_fields.items()}, "drag": self._drag_record(),
                "guides": self.guides, "guidesNote": self.guides_note, "map": self.map, "drawings": self.drawings, "hulls": hulls, "legends": [l.record() for l in self.legends.values()]}


def _data_url(path):
    with open(path, "rb") as fh:
        data = fh.read()
    mime = mimetypes.guess_type(path)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def install(session):
    view = View(session)
    session.view = view
    reg = session.register_command

    def _hull_nodes(seq):
        nodes = []
        seen = set()
        for x in elements_of(seq):
            for n in ((x,) if isinstance(x, Node) else (x._n1, x._n2) if isinstance(x, Edge) else ()):
                if id(n) not in seen:
                    seen.add(id(n))
                    nodes.append(n)
        if not nodes:
            raise GuessError("a shape around a group needs nodes or edges")
        return nodes

    def createConvexHull(seq, color="200,200,255,90", shape="hull", rotate=False, padding=6):
        """createConvexHull(seq) shades the convex hull around the nodes in seq
        (edges contribute their endpoints). shape="box" or "ellipse" draws a
        box or an ellipse around them instead; rotate=true turns the box or
        ellipse to fit the group (the smallest box at any angle) rather than
        keeping it upright; padding= is the room left around the nodes.
        encircle(seq) is the same with an ellipse."""
        h = ConvexHull(view, view.next_id(), _hull_nodes(seq), color, shape, rotate, padding)
        view.hulls[h._id] = h
        view.changed()
        return h

    def encircle(seq, shape="ellipse", color=None, rotate=True, padding=10):
        """encircle(seq) draws a shaded ellipse around a group of nodes, turned
        to fit it; encircle(seq, "box") a box, encircle(seq, "hull") the
        convex hull. rotate=false keeps the shape upright. Without a color,
        each group gets its own (light) colour. Returns the shape: .color,
        .shape, .rotate and .padding change it; removeConvexHull removes it."""
        if color is None:
            pal = colors.distinctColors(12)
            color = f"{pal[len(view.hulls) % len(pal)]},55"
        return createConvexHull(seq, color, shape, rotate, padding)

    def encircleBy(field, shape="ellipse", rotate=True, padding=10, smallest=2):
        """encircleBy(field) draws one shape around each group of nodes that
        share a value of a node field (with at least `smallest` members), each
        in its own colour: encircleBy(louvain_class), encircleBy(dept, "box").
        Returns the shapes."""
        from .model import NODE, as_field, group_by
        f = as_field(session.graph, field, "encircleBy")
        if f.kind != NODE:
            raise GuessError("encircleBy needs a node field")
        groups = [grp for grp in sorted(group_by(f.elements(), f), key=len, reverse=True)
                  if len(grp) >= int(smallest) and f.get(grp[0]) not in (None, "")]
        pal = colors.distinctColors(max(1, min(len(groups), 24)))
        out = [createConvexHull(grp, f"{pal[i % len(pal)]},55", shape, rotate, padding) for i, grp in enumerate(groups)]
        return out

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

    def make_gradient(start, end, lo=0, hi=1, ticks=None):
        lg = GradientLegend(view, view.next_id(), start, end, lo, hi, ticks)
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

    def directedEdges(style="taper"):
        """directedEdges(style) sets how directed edges show which way they go.
        "taper" (the default): wide at the source, narrowing to a point at the
        target, with no arrowhead. "fade": dark at the source, light at the
        target. "arrow": a line with an arrowhead at the target. Holten and van
        Wijk's user study (CHI 2009) found tapered edges were read fastest and most
        accurately, dark-to-light next, and standard arrows among the worst, and
        that adding a second cue did not help, so the default uses the taper
        alone. An edge's own arrowhead or linestyle still applies: dashed, dotted
        and similar styles keep an arrowhead, since they cannot show direction."""
        s = str(style).lower()
        s = {"tapered": "taper", "arrows": "arrow", "arrowhead": "arrow", "arrowheads": "arrow",
             "intensity": "fade", "dark-to-light": "fade"}.get(s, s)
        if s not in ("taper", "fade", "arrow"):
            raise GuessError('directedEdges takes "taper", "fade" or "arrow"')
        view.directed = s
        view.changed()

    def labelOutlines(on=True):
        """labelOutlines() draws a halo in the background colour around labels so
        they stay readable over edges; labelOutlines(false) turns it off."""
        view.labels["outline"] = bool(on)
        view.changed()

    def raiseChanged(on=True):
        """raiseChanged() (the default) draws a node or edge on top of the others
        once its appearance changes (colour, size, shape, label, visibility),
        so what you just changed isn't hidden under its neighbours; edges stay
        under nodes. raiseChanged(false) keeps the drawing order fixed."""
        view.raise_changed = bool(on)
        view.changed()

    def hoverFields(*fields, nodes=None, edges=None):
        """hoverFields(dept, degree) sets the fields the tooltip shows as soon as
        the pointer is on a node or edge; by default it shows only the label.
        Waiting a moment shows every field. Node fields go to nodes' tooltips
        and edge fields to edges'; a kind you don't mention keeps its fields.
        hoverFields(nodes=["dept"], edges=["weight"]) names them by kind (for a
        field both have, such as color); hoverFields() goes back to labels
        only. View → Hover fields… picks them from a list."""
        from .model import EDGE, NODE, as_field
        g = session.graph
        new = {}
        for f in fields:
            fld = as_field(g, f, "hoverFields")
            new.setdefault("n" if fld.kind == NODE else "e", []).append(fld.name)
        for key, kind, given in (("n", NODE, nodes), ("e", EDGE, edges)):
            if given is not None:
                if isinstance(given, str) or not hasattr(given, "__iter__"):
                    given = [given]
                new[key] = [as_field(g, f, "hoverFields", kinds=(kind,)).name for f in given]
        if not fields and nodes is None and edges is None:
            new = {"n": [], "e": []}
        for key, names in new.items():
            view.hover_fields[key] = list(dict.fromkeys(names))
        view.changed()

    def edgeLabelsAlong(on=True):
        """edgeLabelsAlong() turns edge labels to run along their edges (kept
        upright, so they read left to right); edgeLabelsAlong(false) keeps them
        horizontal (the default)."""
        view.labels["along"] = bool(on)
        view.changed()

    def excentricLens(on=True, radius=None, autoSize=None, maxLabels=None):
        """excentricLens() turns on the lens tool (the toolbar's Lens): a circle
        that follows the pointer and lists the labels of the nodes under it
        beside it, each joined to its node by a line (excentric labelling).
        The wheel resizes it, Shift+wheel scrolls long lists; a click pins it,
        and then clicking a label selects its node (Shift: add or remove),
        "Select" takes everything under the lens, and the colour bars filter
        the list. radius in pixels; autoSize=true sizes the lens to the
        density under it; maxLabels per side. excentricLens(false) turns it
        off."""
        msg = {"type": "lens", "on": bool(on)}
        if radius is not None:
            msg["radius"] = float(radius)
        if autoSize is not None:
            msg["auto"] = bool(autoSize)
        if maxLabels is not None:
            msg["max"] = int(maxLabels)
        session.emit(msg)

    def labelPlacement(method="candidates"):
        """labelPlacement("candidates") or labelPlacement("particles") chooses how
        labels with labelpos "outside" (and edge labels, which slide along their
        edge) find room. "candidates" (default) tries 16 positions around each
        node, biggest nodes first, then re-places labels that still collide;
        "particles" also searches further out, ring by ring, and draws a leader
        line to labels it places away from their node. Both avoid other labels,
        nodes and edges."""
        m = str(method).lower()
        if m not in ("candidates", "particles"):
            raise GuessError('method should be "candidates" or "particles"')
        view.labels["placement"] = m
        view.changed()

    def constantLabelSize(on=True, size=None):
        """constantLabelSize() keeps labels the same size on screen as you zoom
        (they grow with the graph otherwise); each label appears once there is
        room for it and stays as you zoom further in, so zooming in reveals more
        labels. size= sets that size in pixels (default 10; a node's labelsize
        still scales its own label). Labels inside nodes keep fitting their
        nodes. constantLabelSize(false) turns it off."""
        view.labels["screen"] = bool(on)
        if size is not None:
            if float(size) <= 0:
                raise GuessError("size is a label height in pixels, e.g. 14")
            view.labels["screenSize"] = float(size)
        view.changed()

    def optimizeLabels(seconds=2):
        """optimizeLabels() improves the positions of labels placed "outside"
        (and of edge labels) by simulated annealing for a few seconds, trading
        overlaps with labels, nodes and edges against the preferred positions;
        the result stays until the graph is replaced, labelPlacement changes or
        you run it again. Good before exporting a figure."""
        session.emit({"type": "labels", "op": "optimize", "ms": int(float(seconds) * 1000)})

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

    collecting = {"name": None}

    def _export(fmt):
        def fn(filename=f"guess.{fmt}"):
            # the display catches up first (it waits for animations too), so an
            # export inside a loop shows that step
            session.flush()
            session.emit({"type": "export", "format": fmt, "name": os.path.basename(filename)})
        fn.__name__ = f"export{fmt.upper()}"
        fn.__doc__ = (f"Save the display as {fmt.upper()} (downloaded by the browser, or added to "
                      "the zip after startImages())."
                      + (" Vector: the whole graph, not just the visible area." if fmt == "svg" else ""))
        return fn

    def startImages(filename="images.zip"):
        """Collect the images that exportPNG() and the other exports save into one
        zip file, downloaded by stopImages(), instead of downloading each:
            startImages('frames.zip')
            for t in range(1990, 2001):
                showTime(t, 'year', 1)
                exportPNG('year_%d.png' % t)
            stopImages()
        Each export shows the display as it is at that point in the script.
        Repeated names get -2, -3, ... added."""
        if collecting["name"]:
            raise GuessError(f"already collecting images for {collecting['name']} (call stopImages() first)")
        name = os.path.basename(str(filename)) or "images.zip"
        if not name.lower().endswith(".zip"):
            name = os.path.splitext(name)[0] + ".zip"
        collecting["name"] = name
        session.emit({"type": "images", "op": "start", "name": name})

    def stopImages():
        """Stop collecting images (see startImages) and download the zip."""
        if not collecting["name"]:
            raise GuessError("no images are being collected (use startImages)")
        collecting["name"] = None
        session.flush()
        session.emit({"type": "images", "op": "stop"})

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

    # ---- drawings: plain lines, text and shapes in graph coordinates ----------------
    def _ink(color):
        if color is None:
            return None, 1.0
        return colors.to_rgba_int(colors.normalize(color))

    def _line_style(style):
        style = str(style)
        if style not in ("solid", "dashed", "dotted"):
            raise GuessError('style is "solid", "dashed" or "dotted"')
        return style

    def _add_drawing(rec):
        rec["i"] = view.next_id()
        view.drawings.append(rec)
        view.changed()
        return Drawing(view, rec["i"])

    def drawLine(x1, y1, x2, y2, color=None, width=1.5, style="solid", arrow=False):
        """drawLine(x1, y1, x2, y2) draws a line on the display, under the
        graph, in graph coordinates (the same as node x and y; a node's
        centre is n.x + n.width/2, n.y + n.height/2). color= (default: the
        theme's text colour), width=, style="dashed" or "dotted", arrow=true
        puts an arrowhead at (x2, y2). Returns the drawing (.remove())."""
        c, a = _ink(color)
        return _add_drawing({"k": "line", "x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2),
                             "c": c, "a": a, "w": float(width), "st": _line_style(style), "ar": bool(arrow)})

    def drawText(x, y, text, color=None, size=14, anchor="middle"):
        """drawText(x, y, "text") writes text on the display at (x, y) in graph
        coordinates, above the graph. size= is in graph units (it zooms with
        the graph); anchor= "start", "middle" or "end" (horizontal)."""
        if anchor not in ("start", "middle", "end"):
            raise GuessError('anchor is "start", "middle" or "end"')
        c, a = _ink(color)
        return _add_drawing({"k": "text", "x": float(x), "y": float(y), "t": str(text), "c": c, "a": a,
                             "s": float(size), "an": anchor})

    def _shape(kind, geom, color, fill, lineWidth, style):
        c, a = _ink(color)
        f, fa = (None, 0.0) if fill is None else colors.to_rgba_int(colors.normalize(fill))
        return _add_drawing({"k": kind, **geom, "c": c, "a": a, "f": f, "fa": fa,
                             "w": float(lineWidth), "st": _line_style(style)})

    def drawRect(x, y, w, h, color=None, fill=None, lineWidth=1.5, style="solid"):
        """drawRect(x, y, w, h) draws a box with its top-left corner at (x, y)
        (graph coordinates), under the graph. fill= a colour fills it
        (e.g. "255,200,0,60" for a translucent one); color= is the outline
        (default: the theme's text colour) and lineWidth=0 leaves it out."""
        return _shape("rect", {"x": float(x), "y": float(y), "ww": float(w), "hh": float(h)},
                      color, fill, lineWidth, style)

    def drawCircle(x, y, r, color=None, fill=None, lineWidth=1.5, style="solid"):
        """drawCircle(x, y, r) draws a circle centred at (x, y) with radius r
        (graph coordinates), under the graph. fill=, lineWidth= and style= as
        for drawRect."""
        return _shape("circle", {"x": float(x), "y": float(y), "r": float(r)}, color, fill, lineWidth, style)

    def removeDrawing(d):
        """Remove one drawing (from drawLine, drawText, drawRect or drawCircle)."""
        i = d._id if isinstance(d, Drawing) else int(d)
        view.drawings = [x for x in view.drawings if x["i"] != i]
        view.changed()

    def clearDrawings():
        """Remove every drawing made with drawLine, drawText, drawRect and drawCircle."""
        if view.drawings:
            view.drawings = []
            view.changed()

    def getDrawings():
        """The drawings on the display."""
        return [Drawing(view, d["i"]) for d in view.drawings]

    for fn in (drawLine, drawText, drawRect, drawCircle, removeDrawing, clearDrawings, getDrawings):
        reg(fn.__name__, fn)

    reg("startMovie", startMovie)
    reg("stopMovie", stopMovie)
    reg("startImages", startImages)
    reg("stopImages", stopImages)

    for fmt in ("png", "jpg", "svg", "gif", "pdf", "ps", "eps"):
        f = _export(fmt)
        if fmt in ("gif", "pdf", "ps", "eps"):
            f.__doc__ = (f"Save the display as {fmt.upper()} (downloaded by the browser): an image "
                         "of the current view inside the file. For vector output use exportSVG.")
        reg(f.__name__, f)

    for fn in (createConvexHull, encircle, encircleBy, removeConvexHull, removeConvexHulls, getConvexHulls,
               setDisplayBackground, getDisplayBackground, setBackgroundImage,
               removeBackgroundImage, overrideArrowLength, overrideArrowWidth, curvedEdges,
               setEdgeColorMode, directedEdges, labelOutlines, hideOverlappingLabels, edgeLabelsAlong, raiseChanged, hoverFields,
               labelPlacement, constantLabelSize, optimizeLabels, excentricLens, select):
        reg(fn.__name__, fn)
    # Legend()/GradientLegend() are constructors: don't auto-call on a bare name
    session._bind("Legend", make_legend, kind="command")
    session._bind("GradientLegend", make_gradient, kind="command")
