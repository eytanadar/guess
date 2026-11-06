"""Names from the 2006 GUESS manual that the Jython version provided, so its
examples run unchanged (see docs/MANUAL_COMPARISON.md).

    g.gemLayout(), g.colorize(…)        every command is also a Graph method
    random(), random(w, h)              the random layout (and still Python's random module)
    biComponentCluster()                the manual's spelling
    findNodes(set), findEdges(set)      the nodes / edges in a mixed set
    Types.INTEGER, Integer(0), …        Java type names
    Morpher.setNodeDisappearBy(.2) …    morph timing
    readjustEdges(), setSynchronous(…)  accepted (parallel edges are always curved;
                                        layouts always run in order)
    infowindow(), InfoWindow.details(x) the data table
    getAppletContext().showDocument(url[, window])
    v.setBackgroundImage(…), v.repaint(), v.getLastClickedPosition(), v.center(…)
    NodeEditorPopup / EdgeEditorPopup / GraphElementPopup.addItem("…")

These are ordinary variables, not protected system names, so scripts can reuse
them (e.g. `import random` or `for v in g.nodes` still work).
"""
import random as _random_module
import types

from .model import EDGE, NODE, Edge, Field, GSet, GuessError, Node, elements_of


class _RandomCompat:
    """random(): the random layout (manual §6); random.choice(…) etc.: Python's module."""

    def __init__(self, layout):
        self._layout = layout

    def __call__(self, *args):
        return self._layout(*args)

    def __getattr__(self, name):
        return getattr(_random_module, name)

    def __repr__(self):
        return "<random: randomLayout() when called; otherwise Python's random module>"


class _Morpher:
    """Morpher.setNodeDisappearBy(n) etc. (manual §11)."""

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        fn = self._s.system.get(name)
        if fn is None or not name.startswith(("set", "get")):
            raise AttributeError(f"Morpher has no {name}")
        return fn[0]

    def __repr__(self):
        return "Morpher"


class _InfoWindow:
    """InfoWindow.details(name): show a node or edge in the data table (manual §5.2)."""

    def __init__(self, session):
        self._s = session

    def details(self, x):
        g = self._s.graph
        if isinstance(x, str):
            x = g._nodes.get(x) or next((e for e in g._edges_list() if repr(e) == x), None)
        if not isinstance(x, (Node, Edge)):
            raise GuessError("InfoWindow.details needs a node or edge (or its name)")
        self._s.system["table"][0](x)

    def __repr__(self):
        return "InfoWindow"


class _AppletContext:
    def __init__(self, session):
        self._s = session

    def showDocument(self, url, window=None):
        """Open a URL in a new browser window (manual §16.3)."""
        self._s.system["openURL"][0](str(url))


class MenuItem:
    """A context-menu entry added with NodeEditorPopup.addItem(label). Set
    item.menuEvent = fn; fn receives the right-clicked element (or a set)."""

    def __init__(self, popup, iid, label):
        self._popup = popup
        self._id = iid
        self.label = str(label)
        self.menuEvent = None

    def remove(self):
        self._popup.removeItem(self)

    def __repr__(self):
        return f"<menu item {self.label!r}>"


class Popup:
    """NodeEditorPopup / EdgeEditorPopup / GraphElementPopup (manual §15.5.2)."""

    def __init__(self, session, scope):
        self._s = session
        self._scope = scope       # "n", "e" or "ne"
        self._items = []

    def addItem(self, label):
        item = MenuItem(self, self._s.gui.next_id(), label)
        self._items.append(item)
        _menus(self._s).register(item)
        return item

    def removeItem(self, item):
        if item in self._items:
            self._items.remove(item)
            _menus(self._s).unregister(item)

    def __repr__(self):
        return {"n": "NodeEditorPopup", "e": "EdgeEditorPopup", "ne": "GraphElementPopup"}[self._scope]


class _Menus:
    def __init__(self, session):
        self.s = session
        self.items = {}

    def register(self, item):
        self.items[item._id] = item
        self.emit()

    def unregister(self, item):
        self.items.pop(item._id, None)
        self.emit()

    def emit(self):
        self.s.emit({"type": "ui", "op": "menu",
                     "items": [{"id": i._id, "label": i.label, "scope": i._popup._scope} for i in self.items.values()]})


def _menus(session):
    if not hasattr(session, "_menus"):
        session._menus = _Menus(session)
    return session._menus


class _Display:
    """`v`, the display object of the Jython version (manual §15)."""

    def __init__(self, session):
        self._s = session

    def setBackgroundImage(self, source, x=0, y=0):
        self._s.system["setBackgroundImage"][0](source, x, y)

    def repaint(self):
        """Not needed: the display redraws itself; kept for old scripts."""

    def getLastClickedPosition(self):
        """Where the user last clicked on the graph (graph coordinates), or None.
        Use .getX() / .getY() as in the manual, or .x / .y."""
        p = getattr(self._s, "last_click", None)
        return None if p is None else _Point(*p)

    def center(self, *args):
        return self._s.system["center"][0](*args)

    def __repr__(self):
        return "v (the display)"


class _Point:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)

    def getX(self):
        return self.x

    def getY(self):
        return self.y

    def __repr__(self):
        return f"({self.x:g}, {self.y:g})"


def install(session):
    g = session.graph
    reg = session.register_command
    cmd_lookup = session.system

    # every command is also a Graph method (the Jython version's real API)
    def command(name):
        rec = cmd_lookup.get(name)
        if rec is not None and rec[1] == "command" and callable(rec[0]):
            return rec[0]
        return None
    g.command_lookup = command

    def biComponentCluster():
        """Same as biComponentClusters() (the manual's spelling)."""
        return cmd_lookup["biComponentClusters"][0]()

    def findNodes(seq):
        """The nodes among the members of a (possibly mixed) set."""
        return GSet((x for x in elements_of(seq) if isinstance(x, Node)), "nodes")

    def findEdges(seq):
        """The edges among the members of a (possibly mixed) set."""
        return GSet((x for x in elements_of(seq) if isinstance(x, Edge)), "edges")

    def readjustEdges():
        """Kept for old scripts: parallel edges are always drawn as separate curves."""

    def setSynchronous(state=True):
        """Kept for old scripts: layouts always run in order (animated, interruptible)."""

    def infowindow():
        """Open the data table (the Jython version's information window)."""
        cmd_lookup["table"][0]()

    def getAppletContext():
        """For old applet scripts: .showDocument(url) opens a browser window."""
        return _AppletContext(session)

    for fn in (biComponentCluster, findNodes, findEdges, readjustEdges, setSynchronous, infowindow, getAppletContext):
        reg(fn.__name__, fn)

    # plain variables (not protected): scripts may rebind them
    ns = session.ns
    ns["random"] = _RandomCompat(cmd_lookup["randomLayout"][0])
    ns["Types"] = types.SimpleNamespace(**{t: t for t in (
        "INTEGER", "INT", "TINYINT", "SMALLINT", "BIGINT", "DOUBLE", "FLOAT", "REAL", "DECIMAL",
        "NUMERIC", "VARCHAR", "LONGVARCHAR", "CHAR", "BOOLEAN", "BIT")})
    ns.update(Integer=int, Long=int, Short=int, Double=float, Float=float, String=str, Boolean=bool)
    ns["Morpher"] = _Morpher(session)
    ns["InfoWindow"] = _InfoWindow(session)
    ns["v"] = _Display(session)
    ns["NodeEditorPopup"] = Popup(session, "n")
    ns["EdgeEditorPopup"] = Popup(session, "e")
    ns["GraphElementPopup"] = Popup(session, "ne")
    _menus(session)


def menu_handler(session, target, value):
    """(function, args) for a custom context-menu click, or (None, ())."""
    menus = getattr(session, "_menus", None)
    item = menus.items.get(target) if menus else None
    if item is None or item.menuEvent is None:
        return None, ()
    g = session.graph
    elems = [x for x in (g.node_by_id(i) if k == "n" else g.edge_by_id(i) for k, i in value or []) if x is not None]
    arg = elems[0] if len(elems) == 1 else GSet(elems, "selection")
    return item.menuEvent, (arg,)


__all__ = ["install", "menu_handler", "Field", "NODE", "EDGE"]
