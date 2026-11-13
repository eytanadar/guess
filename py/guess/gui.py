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
    """Label(text): a line of text in a panel; set .text to change it.
    Label(lambda: f"{len(sel)} selected") is live: the function runs again
    after every command and the label follows."""
    kind = "label"
    _props = ("text",)

    def __init__(self, gui, text=""):
        fn = text if callable(text) else None
        super().__init__(gui, text=gui.evaluate(fn) if fn else str(text))
        if fn:
            gui.bound[self._id] = fn


class Markdown(Widget):
    """Markdown(text): a block of formatted text in a panel (headings, **bold**,
    *italics*, `code`, lists and links). Set .text to change it; a function
    makes it live, like Label."""
    kind = "markdown"
    _props = ("text",)

    def __init__(self, gui, text=""):
        fn = text if callable(text) else None
        super().__init__(gui, text=gui.evaluate(fn) if fn else str(text))
        if fn:
            gui.bound[self._id] = fn


class Chart(Widget):
    """Chart(lambda: plotHistogram(degree)) puts a chart inside a panel
    instead of the dock: the function makes the chart (any plot command, or
    an Altair chart) and runs again after every command, so the chart
    follows the graph. .refresh() redraws it now."""
    kind = "chart"
    _props = ("spec",)

    def __init__(self, gui, fn):
        if not callable(fn):
            raise GuessError("Chart needs a function that makes a chart, e.g. Chart(lambda: plotHistogram(degree))")
        super().__init__(gui)
        object.__setattr__(self, "_fn", fn)
        gui.bound_charts[self._id] = fn
        self._state["spec"] = gui.capture_chart(fn)

    def refresh(self):
        spec = self._gui.capture_chart(self._fn)
        self._state["spec"] = spec
        self._gui.emit_update(self, {"spec": spec})


class View(Widget):
    """View(name) puts one of GUESS's own views inside a panel or tab: "table"
    (the data table), "style", "filter", "variables", "help", "timeline" or
    "console"."""
    kind = "view"
    _props = ("name",)
    NAMES = ("table", "style", "filter", "variables", "help", "timeline", "console")

    def __init__(self, gui, name):
        name = {"vars": "variables", "data": "table"}.get(str(name).lower(), str(name).lower())
        if name not in self.NAMES:
            raise GuessError(f"View names a built-in view: {', '.join(self.NAMES)}")
        super().__init__(gui, name=name)


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


class _Container(Widget):
    """A widget holding others (Panel, Tabs, Tab, Group, Row, Column)."""

    def _init_children(self, children):
        object.__setattr__(self, "_children", [])
        self.add(*children)

    def add(self, *widgets):
        for w in widgets:
            if isinstance(w, str):
                w = Label(self._gui, w)
            if not isinstance(w, Widget) or w is self:
                raise GuessError(f"cannot add {w!r} to a {self.kind}")
            object.__setattr__(w, "_parent", self)
            self._children.append(w)
        root = self._gui.root_of(self)
        if root is not None:
            self._gui.emit_dock(root)
        return self

    def record(self):
        r = super().record()
        r["children"] = [c.record() for c in self._children]
        return r


class Panel(_Container):
    """Panel(title, *widgets, position="bottom", vertical=False). Show with
    ui.dock(p), or place it with ui.layout(left=p, …). position is "bottom",
    "right" or "left"."""
    kind = "panel"
    _props = ("title", "position", "vertical", "bare")

    def __init__(self, gui, title="", *children, position="bottom", vertical=False):
        super().__init__(gui, title=str(title), position=position, vertical=bool(vertical))
        self._init_children(children)

    def dock(self):
        self._gui.dock(self)
        return self

    def close(self):
        self._gui.close(self)



class Tabs(_Container):
    """Tabs(Tab("Network", …), Tab("Style", View("style")), …): tabbed pages
    in a panel; .selected is the title of the tab showing."""
    kind = "tabs"
    _props = ("selected",)
    _events = ("onChange",)

    def __init__(self, gui, *tabs, selected=None, onChange=None):
        for t in tabs:
            if not isinstance(t, Tab):
                raise GuessError("Tabs takes Tab(title, …) pages")
        super().__init__(gui, selected=selected if selected is not None else (tabs[0].title if tabs else None),
                         onChange=onChange)
        self._init_children(tabs)

    def _receive(self, name, value):
        self._state["selected"] = value
        return self._handlers.get("onChange")


class Tab(_Container):
    """Tab(title, *widgets): one page of a Tabs."""
    kind = "tab"
    _props = ("title", "vertical")

    def __init__(self, gui, title, *children, vertical=True):
        super().__init__(gui, title=str(title), vertical=bool(vertical))
        self._init_children(children)


class Group(_Container):
    """Group(title, *widgets, collapsed=False): a titled box that can be folded."""
    kind = "group"
    _props = ("title", "collapsed", "vertical")

    def __init__(self, gui, title, *children, collapsed=False, vertical=True):
        super().__init__(gui, title=str(title), collapsed=bool(collapsed), vertical=bool(vertical))
        self._init_children(children)


class Row(_Container):
    """Row(*widgets): widgets side by side."""
    kind = "row"

    def __init__(self, gui, *children):
        super().__init__(gui)
        self._init_children(children)


class Column(_Container):
    """Column(*widgets): widgets one under another."""
    kind = "column"

    def __init__(self, gui, *children):
        super().__init__(gui)
        self._init_children(children)


class MenuItem(Widget):
    """MenuItem(label, run="code" or onClick=fn, shortcut=""): an item for
    Menu(...) or a menu bar. run= runs Gython as a command (one undo step)."""
    kind = "menuitem"
    _props = ("text", "run", "enabled", "shortcut")
    _events = ("onClick",)

    def __init__(self, gui, text, run=None, onClick=None, shortcut=""):
        super().__init__(gui, text=str(text), run=None if run is None else str(run), enabled=True,
                         shortcut=str(shortcut), onClick=onClick)


class Action:
    """Action(name): one of GUESS's own commands for a menu or toolbar: "open",
    "save", "png", "svg", "sample", "share-link", "share-viewer", "table",
    "style", "filter", "variables", "help", "history", "search", "stop",
    "tour", "manual", "fit", the tools "tool:select", "tool:lens",
    "tool:path", "tool:heat", "tool:paint", "tool:cluster", "tools"
    (the whole tool strip, for a toolbar) and "source" (an app's code)."""
    NAMES = ("open", "save", "png", "svg", "sample", "share-link", "share-viewer", "table", "style", "filter",
             "variables", "help", "history", "search", "stop", "tour", "manual", "fit", "tools", "source",
             "tool:select", "tool:lens", "tool:path", "tool:heat", "tool:paint", "tool:cluster")

    def __init__(self, name, label=None):
        name = str(name)
        if name not in self.NAMES:
            raise GuessError(f"unknown action '{name}' (actions: {', '.join(self.NAMES)})")
        self.name, self.label = name, label

    def record(self):
        return {"kind": "action", "name": self.name, **({"text": str(self.label)} if self.label else {})}

    def __repr__(self):
        return f"Action({self.name!r})"


class Separator:
    """Separator(): a line between menu or toolbar items."""

    def record(self):
        return {"kind": "sep"}

    def __repr__(self):
        return "Separator()"


class Menu:
    """Menu(title, *items): a menu for ui.menubar; items are MenuItem, Action,
    Separator (or "-")."""

    def __init__(self, title, *items):
        self.title = str(title)
        self.items = list(items)

    def record(self):
        out = []
        for it in self.items:
            if it == "-" or isinstance(it, Separator):
                out.append({"kind": "sep"})
            elif isinstance(it, (MenuItem, Action)):
                out.append(it.record())
            elif isinstance(it, str):
                out.append(Action(it).record())
            else:
                raise GuessError(f"a Menu holds MenuItem, Action or Separator, not {it!r}")
        return {"title": self.title, "items": out}

    def __repr__(self):
        return f"Menu({self.title!r})"


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


class PacedTimer:
    """Calls fn() repeatedly, slowly at first, faster in the middle and slowly
    again near the end (see everyPaced)."""

    def __init__(self, gui, fn, steps, slow, fast, ramp):
        self._gui, self.fn, self.steps = gui, fn, steps
        self.slow, self.fast, self.ramp = float(slow), float(fast), max(1, int(ramp))
        self.count, self.running, self._timer = 0, True, None
        self._schedule(None)

    def delay(self, left):
        """Seconds before the next call: slow for the first and last `ramp` calls."""
        start = min(1.0, self.count / self.ramp)
        end = 1.0 if left is None else min(1.0, max(0, left - 1) / self.ramp)
        return self.slow + (self.fast - self.slow) * min(start, end)

    def _schedule(self, left):
        self._timer = self._gui.add_timer(self._tick, self.delay(left), False)

    def _tick(self):
        if not self.running:
            return
        result = self.fn()
        self.count += 1
        if result is False or (self.steps is not None and self.count >= self.steps):
            self.running = False
            return
        left = result if isinstance(result, int) and not isinstance(result, bool) else (
            self.steps - self.count if self.steps is not None else None)
        self._schedule(left)

    def stop(self):
        self.running = False
        if self._timer is not None:
            self._timer.stop()

    def __repr__(self):
        return f"<paced timer: {self.count} calls, {'running' if self.running else 'stopped'}>"


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
    """ui.dock(panel) shows a panel; ui.layout, ui.menubar, ui.toolbar,
    ui.statusbar, ui.title and ui.console arrange the whole window (for apps)."""

    def __init__(self, gui):
        self._gui = gui

    def dock(self, panel):
        """Show a Panel in the dock area (bottom, right or left of the graph)."""
        self._gui.dock(panel)

    def undock(self, panel):
        self._gui.close(panel)

    def layout(self, left=None, right=None, bottom=None, sizes=None):
        """ui.layout(left=…, right=…, bottom=…, sizes={"left": 300}) arranges
        the window: each region takes a Panel, any widget (Tabs, a Column, a
        View, …) or a list of them; regions not given are emptied.
        sizes= sets a region's width (left, right) or height (bottom) in
        pixels; the edges can be dragged too."""
        g = self._gui
        for pid in list(g.docked):
            w = g.widgets.get(pid)
            if w is not None and w.position in ("left", "right", "bottom"):
                g.close(w)
        for where, content in (("left", left), ("right", right), ("bottom", bottom)):
            if content is None:
                continue
            for item in (content if isinstance(content, (list, tuple)) else [content]):
                if not isinstance(item, Panel):
                    p = Panel(g, "", item, position=where, vertical=True)
                    p.bare = True
                    item = p
                else:
                    item.position = where
                g.dock(item)
        g.session.emit({"type": "ui", "op": "regions", "sizes": {k: float(v) for k, v in (sizes or {}).items()}})

    def menubar(self, *menus, keep=()):
        """ui.menubar(Menu("File", Action("open"), MenuItem("Report", run="report()")), …)
        replaces the menu bar; keep=["Help"] keeps some of GUESS's own menus
        (after yours). ui.menubar() with nothing removes the menus."""
        for m in menus:
            if not isinstance(m, Menu):
                raise GuessError("ui.menubar takes Menu(title, …) items")
        g = self._gui
        g.chrome["menubar"] = [it for m in menus for it in m.items if isinstance(it, Widget)]
        g.session.emit({"type": "ui", "op": "menubar", "menus": [m.record() for m in menus],
                        "keep": [str(k) for k in keep]})

    def toolbar(self, *items):
        """ui.toolbar(Action("open"), "|", Button("Run", onClick=fn), Action("tools"), …)
        shows a toolbar under the menu bar: actions, widgets, "|" (a
        separator) and "search". ui.toolbar() removes it."""
        g = self._gui
        g.chrome["toolbar"] = [it for it in items if isinstance(it, Widget)]
        g.session.emit({"type": "ui", "op": "toolbar", "items": [_item_record(it) for it in items]})

    def statusbar(self, *items):
        """ui.statusbar(Label(lambda: f"{len(g.nodes)} nodes"), …): a bar along
        the bottom of the window. ui.statusbar() removes it."""
        g = self._gui
        g.chrome["statusbar"] = [it for it in items if isinstance(it, Widget)]
        g.session.emit({"type": "ui", "op": "statusbar", "items": [_item_record(it) for it in items]})

    def title(self, text, subtitle=None):
        """ui.title("Interactome Explorer") names the window (in place of GUESS)."""
        self._gui.session.emit({"type": "ui", "op": "title", "text": str(text),
                                "subtitle": None if subtitle is None else str(subtitle)})

    def console(self, mode):
        """ui.console("hidden") hides the console; "toggle" hides it but Ctrl+`
        brings it back; "shown" shows it."""
        mode = str(mode)
        if mode not in ("hidden", "toggle", "shown"):
            raise GuessError('ui.console takes "hidden", "toggle" or "shown"')
        self._gui.session.emit({"type": "ui", "op": "console", "mode": mode})

    def __repr__(self):
        return "ui"


def _item_record(it):
    if it == "|" or isinstance(it, Separator):
        return {"kind": "sep"}
    if it == "search":
        return {"kind": "action", "name": "search"}
    if isinstance(it, str):
        return Action(it).record()
    if isinstance(it, Action):
        return it.record()
    if isinstance(it, Widget):
        return it.record()
    raise GuessError(f"toolbar and status bar items are actions, widgets or \"|\", not {it!r}")


class Gui:
    def __init__(self, session):
        self.session = session
        self.widgets = {}
        self.docked = set()
        self.timers = {}
        self.defaults = {"highlight": True, "zoom": True, "edgeHighlight": True, "edgeZoom": True}
        self._next = 0
        self.events = GraphEvents(self)
        self.bound = {}          # widget id -> function giving its text (live labels)
        self.bound_charts = {}   # Chart widget id -> function making its chart
        self.chrome = {}         # "menubar" / "toolbar" / "statusbar" -> their widgets

    def next_id(self):
        self._next += 1
        return f"w{self._next}"

    def emit_update(self, w, props):
        if self._shown(w):
            self.session.emit({"type": "ui", "op": "update", "id": w._id, "props": props})

    def root_of(self, w):
        """The docked panel a widget is inside, or None."""
        while w is not None:
            if w._id in self.docked:
                return w
            w = w.__dict__.get("_parent")
        return None

    def _shown(self, w):
        if self.root_of(w) is not None:
            return True
        top = w
        while top.__dict__.get("_parent") is not None:
            top = top.__dict__["_parent"]
        return any(top in items for items in self.chrome.values())

    def evaluate(self, fn):
        try:
            v = fn()
        except Exception as e:  # noqa: BLE001 - a live label must never break a command
            return f"⚠ {type(e).__name__}: {e}"
        return "" if v is None else str(v)

    def capture_chart(self, fn):
        """Run fn, keeping the chart it makes (for a Chart widget) instead of
        sending it to the dock. An Altair chart returned is drawn too."""
        s = self.session
        prev = getattr(s, "_chart_capture", None)
        got = []
        s._chart_capture = got
        try:
            v = fn()
            if v is not None and hasattr(v, "to_dict") and hasattr(v, "mark_point"):
                show = s.ns.get("showChart")
                if show is not None:
                    show(v)
        except Exception as e:  # noqa: BLE001 - a chart widget must never break a command
            return {"type": "error", "text": f"{type(e).__name__}: {e}"}
        finally:
            s._chart_capture = prev
        return got[-1] if got else None

    def refresh_bound(self):
        """Live labels: run their functions again and send what changed."""
        for wid, fn in list(self.bound_charts.items()):
            w = self.widgets.get(wid)
            if w is None:
                self.bound_charts.pop(wid, None)
                continue
            if not self._shown(w):
                continue
            spec = self.capture_chart(fn)
            if spec != w._state.get("spec"):
                w._state["spec"] = spec
                self.emit_update(w, {"spec": spec})
        for wid, fn in list(self.bound.items()):
            w = self.widgets.get(wid)
            if w is None:
                self.bound.pop(wid, None)
                continue
            text = self.evaluate(fn)
            if text != w._state.get("text"):
                w._state["text"] = text
                self.emit_update(w, {"text": text})

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

    for cls in (Panel, Label, Button, Slider, Checkbox, Dropdown, TextField, Markdown, Chart, View, Tabs, Tab, Group,
                Row, Column, MenuItem):
        session._bind(cls.__name__, ctor(cls), kind="command")

    def every(seconds, fn):
        """Call fn() every `seconds` seconds; returns a timer with .stop()."""
        return gui.add_timer(fn, seconds, True)

    def after(seconds, fn):
        """Call fn() once after `seconds` seconds; returns a timer with .stop()."""
        return gui.add_timer(fn, seconds, False)

    def everyPaced(fn, steps=None, slow=0.9, fast=0.15, ramp=3):
        """everyPaced(step) calls step() again and again, slow-fast-slow, so a
        process can be followed on screen: `slow` seconds apart for the first
        `ramp` calls, speeding up to `fast`, and slowing down again over the
        last `ramp` calls. Give steps= when the number of calls is known, or
        let step() return how many calls are left (an int); returning False
        stops. Returns a timer with .stop()."""
        if not callable(fn):
            raise GuessError("everyPaced needs a function to call")
        return PacedTimer(gui, fn, None if steps is None else int(steps), slow, fast, ramp)

    def stopTimers():
        """Stop all timers."""
        for t in list(gui.timers.values()):
            t.stop()

    def openURL(url):
        """Open a web page in a new browser tab."""
        session.emit({"type": "ui", "op": "open", "url": str(url)})

    for cls in (Action, Separator, Menu):
        session._bind(cls.__name__, cls, kind="command")
    session._bind("every", every, kind="command")
    session._bind("after", after, kind="command")
    session._bind("everyPaced", everyPaced, kind="command")

    def linkTo(element, text=None):
        """linkTo(node) is Markdown for a small chip naming a node (or edge):
        in a Markdown panel, pointing at the chip highlights the element in the
        graph and clicking selects it. Good for listing a queue, a path or
        search results beside the graph:
            Markdown(lambda: "Queue: " + " ".join(linkTo(n) for n in queue))
        text= replaces the shown name (e.g. "v3 (d=2)")."""
        from .model import Edge, GuessError, Node
        if isinstance(element, Node):
            k, label = "n", element._name
        elif isinstance(element, Edge):
            k, label = "e", f"{element._n1._name}–{element._n2._name}"
        else:
            raise GuessError("linkTo takes a node or an edge")
        label = str(label if text is None else text).replace("[", "(").replace("]", ")")
        return f"[{label}](guess:{k}{element._id})"

    session.register_command("linkTo", linkTo)
    session.register_command("stopTimers", stopTimers)
    session._bind("openURL", openURL, kind="command")
    session._bind("ui", UI(gui), kind="graph")
    session._bind("graphevents", gui.events, kind="graph")
    session._bind("vf", VisFactory(gui), kind="graph")
    session._bind("StatusBar", StatusBar(gui), kind="graph")
