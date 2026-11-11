"""Names from the 2006 GUESS manual that the Jython version provided, so its
examples run unchanged (see docs/MANUAL_COMPARISON.md).

    g.gemLayout(), g.colorize(…)        every command is also a Graph method
    random(), random(w, h)              the random layout (and still Python's random module)
    findNodes(set), findEdges(set)      the nodes / edges in a mixed set
    NodeEditorPopup / EdgeEditorPopup / GraphElementPopup.addItem("…")

The Java-only names (Types.INTEGER, Integer(0), Morpher, readjustEdges,
setSynchronous, infowindow, InfoWindow, getAppletContext, the display object
`v`, and SWF/Java/CGM/EMF export) were removed in 2026; see the manual's
Appendix C for their replacements.

These are ordinary variables, not protected system names, so scripts can reuse
them (e.g. `import random` or `for v in g.nodes` still work).
"""
import random as _random_module

from .model import EDGE, NODE, Edge, Field, GSet, Node, elements_of


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


    def findNodes(seq):
        """The nodes among the members of a (possibly mixed) set."""
        return GSet((x for x in elements_of(seq) if isinstance(x, Node)), "nodes")

    def findEdges(seq):
        """The edges among the members of a (possibly mixed) set."""
        return GSet((x for x in elements_of(seq) if isinstance(x, Edge)), "edges")

    for fn in (findNodes, findEdges):
        reg(fn.__name__, fn)

    # plain variables (not protected): scripts may rebind them
    ns = session.ns
    ns["random"] = _RandomCompat(cmd_lookup["randomLayout"][0])
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
