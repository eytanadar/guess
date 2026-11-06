"""Extending the interface from Gython: dockable widget panels, timers and
graph mouse events. Replaces the original's Swing docking API.

    s = Slider(0, freq.max, label="min freq")
    def update(v):
        (freq < v).visible = false
        (freq >= v).visible = true
    s.onChange = update                      # fires when the slider is released
    ui.dock(Panel("Edges", s, Button("Center", onClick=center)))

    graphevents.clickNode = lambda n: center([n] + n.getNeighbors())
    t = every(1.0, step)                     # call step() every second; t.stop()

Messages to the front end are {"type": "ui", "op": ...}; events come back
through Session.dispatch(target, name, value).
"""
import inspect

from .model import Edge, GuessError, Node

# event-property aliases matching the names used by original GUESS scripts
_ALIASES = {"actionPerformed": "onClick", "mouseReleased": "onChange", "stateChanged": "onSlide"}


class Widget:
    kind = "widget"
    _events = ()
    _props = ()

    def __init__(self, gui, **props):
        object.__setattr__(self, "_gui", gui)
        object.__setattr__(self, "_id", gui.next_id())
        object.__setattr__(self, "_state", {})
        object.__setattr__(self, "_handlers", {})
        gui.widgets[self._id] = self
        for k, v in props.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        name = _ALIASES.get(name, name)
        if name in self._events:
            return self._handlers.get(name)
        if name in self._props:
            return self._state.get(name)
        raise AttributeError(f"{self.kind} has no attribute '{name}'")

    def __setattr__(self, name, value):
        name = _ALIASES.get(name, name)
        if name in self._events:
            if value is not None and not callable(value):
                raise GuessError(f"{name} must be a function")
            self._handlers[name] = value
        elif name in self._props:
            self._state[name] = value
            self._gui.emit_update(self, {name: _plain(value)})
        else:
            raise GuessError(f"{self.kind} has no property '{name}' "
                             f"(properties: {', '.join(self._props + self._events)})")

    def record(self):
        return {"id": self._id, "kind": self.kind,
                "props": {k: _plain(v) for k, v in self._state.items()}}

    def __repr__(self):
        return f"<{self.kind} {self._id}>"

    # called by the dispatcher with the front end's new value
    def _receive(self, name, value):
        if name in ("change", "slide") and "value" in self._props:
            self._state["value"] = value
        if name == "change" and "checked" in self._props:
            self._state["checked"] = value
        return self._handlers.get({"click": "onClick", "change": "onChange",
                                   "slide": "onSlide", "enter": "onEnter"}.get(name, ""))


class Label(Widget):
    """Label(text): a line of text in a panel; set .text to change it."""
    kind = "label"
    _props = ("text",)

    def __init__(self, gui, text=""):
        super().__init__(gui, text=str(text))


class Button(Widget):
    """Button(text, onClick=fn): calls fn() when clicked; .enabled turns it on/off."""
    kind = "button"
    _props = ("text", "enabled")
    _events = ("onClick",)

    def __init__(self, gui, text="Button", onClick=None):
        super().__init__(gui, text=str(text), enabled=True, onClick=onClick)


class Slider(Widget):
    """Slider(min, max, value=None, step=1, label="", onChange=None, onSlide=None).
    onChange fires on release, onSlide while dragging."""
    kind = "slider"
    _props = ("min", "max", "value", "step", "label", "enabled")
    _events = ("onChange", "onSlide")

    def __init__(self, gui, min=0, max=100, value=None, step=1, label="", onChange=None, onSlide=None):
        super().__init__(gui, min=min, max=max, value=min if value is None else value, step=step,
                         label=str(label), enabled=True, onChange=onChange, onSlide=onSlide)

    def getValue(self):
        return self.value

    def setValue(self, v):
        self.value = v


class Checkbox(Widget):
    """Checkbox(text, checked=False, onChange=fn): calls fn(checked) when toggled."""
    kind = "checkbox"
    _props = ("text", "checked", "enabled")
    _events = ("onChange",)

    def __init__(self, gui, text="", checked=False, onChange=None):
        super().__init__(gui, text=str(text), checked=bool(checked), enabled=True, onChange=onChange)


class Dropdown(Widget):
    """Dropdown(options, value=None, label="", onChange=fn): a choice list; calls
    fn(value) when the selection changes."""
    kind = "dropdown"
    _props = ("options", "value", "label", "enabled")
    _events = ("onChange",)

    def __init__(self, gui, options=(), value=None, label="", onChange=None):
        options = [str(o) for o in options]
        super().__init__(gui, options=options, value=value if value is not None else (options[0] if options else ""),
                         label=str(label), enabled=True, onChange=onChange)


class TextField(Widget):
    """TextField(value="", placeholder="", onEnter=None): onEnter(text) on Return."""
    kind = "textfield"
    _props = ("value", "placeholder", "enabled")
    _events = ("onEnter", "onChange")

    def __init__(self, gui, value="", placeholder="", onEnter=None, onChange=None):
        super().__init__(gui, value=str(value), placeholder=str(placeholder), enabled=True,
                         onEnter=onEnter, onChange=onChange)

    def _receive(self, name, value):
        self._state["value"] = value
        return self._handlers.get("onEnter" if name == "enter" else "onChange")


class Panel(Widget):
    """Panel(title, *widgets, position="bottom", vertical=False). Show with ui.dock(p)."""
    kind = "panel"
    _props = ("title", "position", "vertical")

    def __init__(self, gui, title="", *children, position="bottom", vertical=False):
        super().__init__(gui, title=str(title), position=position, vertical=bool(vertical))
        object.__setattr__(self, "_children", [])
        self.add(*children)

    def add(self, *widgets):
        for w in widgets:
            if not isinstance(w, Widget) or w is self:
                raise GuessError(f"cannot add {w!r} to a panel")
            self._children.append(w)
        if self._id in self._gui.docked:
            self._gui.emit_dock(self)
        return self

    def dock(self):
        self._gui.dock(self)
        return self

    def close(self):
        self._gui.close(self)

    def record(self):
        r = super().record()
        r["children"] = [c.record() for c in self._children]
        return r


class Timer:
    def __init__(self, gui, tid, fn, seconds, repeat):
        self._gui, self._id, self.fn, self.seconds, self.repeat = gui, tid, fn, seconds, repeat
        self.running = True

    def stop(self):
        if self.running:
            self.running = False
            self._gui.timers.pop(self._id, None)
            self._gui.session.emit({"type": "ui", "op": "cancelTimer", "id": self._id})

    def __repr__(self):
        state = "running" if self.running else "stopped"
        return f"<timer {self._id}: every {self.seconds}s, {state}>" if self.repeat else f"<timer {self._id}: {state}>"


GRAPH_EVENTS = ("clickNode", "clickEdge", "shiftClickNode", "shiftClickEdge",
                "mouseEnterNode", "mouseLeaveNode", "mouseEnterEdge", "mouseLeaveEdge")


class GraphEvents:
    """graphevents.clickNode = fn(node), and clickEdge, shiftClickNode, shiftClickEdge,
    mouseEnterNode, mouseLeaveNode, mouseEnterEdge, mouseLeaveEdge."""

    def __init__(self, gui):
        object.__setattr__(self, "_gui", gui)
        object.__setattr__(self, "_handlers", {})

    def __getattr__(self, name):
        if name in GRAPH_EVENTS:
            return self._handlers.get(name)
        raise AttributeError(name)

    def __setattr__(self, name, fn):
        if name not in GRAPH_EVENTS:
            raise GuessError(f"unknown graph event '{name}' (events: {', '.join(GRAPH_EVENTS)})")
        if fn is not None and not callable(fn):
            raise GuessError(f"{name} must be a function")
        self._handlers[name] = fn
        self._gui.emit_events()

    def __repr__(self):
        return "graphevents"


class VisFactory:
    """vf: switches for default display behaviours."""

    def __init__(self, gui):
        self._gui = gui

    def defaultNodeHighlights(self, on):
        """Turn the built-in hover highlight on or off."""
        self._gui.defaults["highlight"] = bool(on)
        self._gui.emit_events()

    def defaultNodeZooming(self, on):
        """Turn double-click-to-zoom on nodes (and the background) on or off."""
        self._gui.defaults["zoom"] = bool(on)
        self._gui.emit_events()

    def defaultEdgeHighlights(self, on):
        """Turn the built-in hover highlight of edges on or off."""
        self._gui.defaults["edgeHighlight"] = bool(on)
        self._gui.emit_events()

    def defaultEdgeZooming(self, on):
        """Turn double-click-to-zoom on edges on or off."""
        self._gui.defaults["edgeZoom"] = bool(on)
        self._gui.emit_events()

    def __repr__(self):
        return "vf"


class StatusBar:
    def __init__(self, gui):
        self._gui = gui

    def setStatus(self, text):
        """Show text in the status area."""
        self._gui.session.emit({"type": "ui", "op": "status", "text": str(text)})

    setErrorStatus = setStatus

    def __repr__(self):
        return "StatusBar"


class UI:
    def __init__(self, gui):
        self._gui = gui

    def dock(self, panel):
        """Show a Panel in the dock area (bottom or right of the graph)."""
        self._gui.dock(panel)

    def undock(self, panel):
        self._gui.close(panel)

    def __repr__(self):
        return "ui"


class Gui:
    def __init__(self, session):
        self.session = session
        self.widgets = {}
        self.docked = set()
        self.timers = {}
        self.defaults = {"highlight": True, "zoom": True, "edgeHighlight": True, "edgeZoom": True}
        self._next = 0
        self.events = GraphEvents(self)

    def next_id(self):
        self._next += 1
        return f"w{self._next}"

    def emit_update(self, w, props):
        if self._root_docked(w):
            self.session.emit({"type": "ui", "op": "update", "id": w._id, "props": props})

    def _root_docked(self, w):
        if w._id in self.docked:
            return True
        return any(w in p._children for p in (self.widgets[i] for i in self.docked))

    def emit_dock(self, panel):
        self.session.emit({"type": "ui", "op": "dock", "panel": panel.record()})

    def dock(self, panel):
        if not isinstance(panel, Panel):
            raise GuessError("ui.dock needs a Panel(...)")
        self.docked.add(panel._id)
        self.emit_dock(panel)

    def close(self, panel):
        self.docked.discard(panel._id)
        self.session.emit({"type": "ui", "op": "close", "id": panel._id})

    def emit_events(self):
        enabled = [k for k, v in self.events._handlers.items() if v is not None]
        self.session.emit({"type": "ui", "op": "events", "enabled": enabled, "defaults": dict(self.defaults)})

    def add_timer(self, fn, seconds, repeat):
        if not callable(fn):
            raise GuessError("timer needs a function")
        tid = self.next_id()
        t = Timer(self, tid, fn, float(seconds), repeat)
        self.timers[tid] = t
        self.session.emit({"type": "ui", "op": "timer", "id": tid, "ms": max(16, float(seconds) * 1000),
                           "repeat": repeat})
        return t

    def handler_for(self, target, name, value):
        """Resolve a front-end event to (function, args)."""
        if target == "graph":
            fn = self.events._handlers.get(name)
            kind, ident = value
            g = self.session.graph
            elem = g.node_by_id(ident) if kind == "n" else g.edge_by_id(ident)
            if fn is None or elem is None:
                return None, ()
            return fn, (elem,)
        if target in self.timers:
            t = self.timers[target]
            if not t.repeat:
                t.running = False
                self.timers.pop(target, None)
            return t.fn, ()
        w = self.widgets.get(target)
        if w is None:
            return None, ()
        fn = w._receive(name, value)
        return fn, (value,)


def _plain(v):
    if isinstance(v, (Node, Edge)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, float) and v.is_integer():
        return v
    return v


def call_flexibly(fn, args):
    """Call fn with args, or with fewer if it takes fewer (lambda: ... handlers)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(*args)
    params = list(sig.parameters.values())
    if any(p.kind == p.VAR_POSITIONAL for p in params):
        return fn(*args)
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return fn(*args[:len(positional)])


def install(session):
    gui = Gui(session)
    session.gui = gui

    def ctor(cls):
        def make(*a, **k):
            return cls(gui, *a, **k)
        make.__name__ = cls.__name__
        make.__doc__ = cls.__doc__
        return make

    for cls in (Panel, Label, Button, Slider, Checkbox, Dropdown, TextField):
        session._bind(cls.__name__, ctor(cls), kind="command")

    def every(seconds, fn):
        """Call fn() every `seconds` seconds; returns a timer with .stop()."""
        return gui.add_timer(fn, seconds, True)

    def after(seconds, fn):
        """Call fn() once after `seconds` seconds; returns a timer with .stop()."""
        return gui.add_timer(fn, seconds, False)

    def stopTimers():
        """Stop all timers."""
        for t in list(gui.timers.values()):
            t.stop()

    def openURL(url):
        """Open a web page in a new browser tab."""
        session.emit({"type": "ui", "op": "open", "url": str(url)})

    session._bind("every", every, kind="command")
    session._bind("after", after, kind="command")
    session.register_command("stopTimers", stopTimers)
    session._bind("openURL", openURL, kind="command")
    session._bind("ui", UI(gui), kind="graph")
    session._bind("graphevents", gui.events, kind="graph")
    session._bind("vf", VisFactory(gui), kind="graph")
    session._bind("StatusBar", StatusBar(gui), kind="graph")
