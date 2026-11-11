"""An interactive GUESS session: namespace, execution, output and render patches.

The session talks to the front end only through ``emit(message: dict)``.
Message types:

  {"type": "scene", "nodes": [...], "edges": [...]}            full redraw
  {"type": "patch", "nodes": [...], "edges": [...],
                    "removedNodes": [...], "removedEdges": [...]}
  {"type": "out",   "segs": [...]}     structured interpreter output
  {"type": "text",  "text": "..."}     plain stdout
  {"type": "error", "text": "..."}
  {"type": "center", "nodes": [...], "edges": [...]}  (empty lists = everything)

Output segments: a str, or {"n": id, "t": text} (node), {"e": id, "t": text}
(edge), or {"g": [segs...], "a": annotation} (a group).
"""
import io
import keyword
import re
import sys
import time
import traceback

from . import colors, compiler, runtime
from . import colors as colors_mod
from .model import (EDGE, NODE, DistinctValues, Edge, Field, FieldNamespace, Graph, GSet, GuessError, Journal, Node)

MAX_ITEMS = 500
_MISSING = object()


class _Writer:
    def __init__(self, session):
        self.session = session

    def write(self, s):
        if s:
            self.session.emit({"type": "text", "text": s})
        return len(s)

    def flush(self):
        pass


class Session:
    def __init__(self, emit=None):
        self.emit = emit or (lambda msg: None)
        self.graph = Graph()
        self.graph.listeners.append(self)
        self.ns = {"__name__": "__console__", "__builtins__": __builtins__}
        self.system = {}          # name -> object for protected bindings
        self._shadowed = {}       # system names replaced by the user's own imports
        self.graph_gen = 0        # counts graph loads/switches: output is tagged with it
        self.provenance = {}      # ("n"|"e", id) -> {aspect: cell} : which cell last changed what
        self.cell_code = {}       # cell -> its code (first line), for "color <- [12] colorize(dept)"
        self.cell_items = {}      # cell -> [(kind, id)] it changed
        self.running_cell = None  # the console cell being run (charts made by it are keyed by it)
        self.chart_seq = 0        # charts made so far by the running cell
        # live charts: how each chart was made (command, args), and which recompute after changes
        self.chart_recipes = {}   # chart id -> (fn, args, kwargs)
        self.live_charts = set()
        self.all_live = False     # liveCharts(): every chart is live
        self._recipe = None       # the chart command running now
        self._refreshing = None   # the chart id being recomputed
        self.ns.update(runtime.HELPERS)
        self.ns["__display__"] = self.display
        self.ns["__gnot__"] = self._gnot
        self.ns["__gfstr__"] = fstring
        self.ns["print"] = self._print
        from . import commands
        commands.install(self)
        from . import algorithms, analysis, builders, charts, codegraphs, compat, connectors, ecology, enrichment, epidemic, extras, geo, glyphs, investigate, groups, gui, gv, igr, interop, layouts, persist, ranges, slides, states, structure, styles, timeline, visuals, workspaces
        gui.install(self)
        charts.install(self)
        from . import vlcharts
        vlcharts.install(self)
        from . import demo as demo_mod
        demo_mod.install(self)
        persist.install(self)
        from . import sqlquery
        sqlquery.install(self)
        layouts.install(self)
        algorithms.install(self)
        analysis.install(self)
        structure.install(self)
        interop.install(self)
        igr.install(self)
        gv.install(self)
        visuals.install(self)
        styles.install(self)
        groups.install(self)
        workspaces.install(self)
        glyphs.install(self)
        connectors.install(self)
        enrichment.install(self)
        builders.install(self)
        geo.install(self)
        codegraphs.install(self)
        investigate.install(self)
        ecology.install(self)
        extras.install(self)
        epidemic.install(self)
        timeline.install(self)
        slides.install(self)
        compat.install(self)
        states.install(self)
        ranges.install(self)
        self.pending_morph = None
        self.revision = 0         # bumps whenever the display changes (for autosave)
        self.log_lines = None     # list while log() is recording
        self.executed = []        # every console command, in order (history())
        self.undo_stack = []
        self.redo_stack = []
        self._run_depth = 0
        self.current_cell = None  # console cell number of the next run (marks undone cells)
        self.quiet_next = False   # the next run is a watched-cell refresh: no history or undo step
        self._history_op = False

        def undo():
            """undo() reverses the most recent command that changed the graph, its
            fields, states, hulls, legends or display settings (Ctrl/Cmd+Z outside
            the code cell). Repeat to go further back (up to 50 steps); redo()
            re-applies. Variables and downloaded files are not undone."""
            self.undo()

        def redo():
            """redo() re-applies the last command undone with undo()."""
            self.redo()

        def history():
            """history() lists every command run this session, in order."""
            self.history()

        def saveHistory(filename="history.py"):
            """saveHistory("work.py") downloads every command run this session as a
            script (run it again with execfile)."""
            import os
            text = "\n".join(src.rstrip() for src in self.executed) + "\n"
            with open(filename, "w", encoding="utf-8") as fh:
                fh.write(text)
            self.emit({"type": "download", "name": os.path.basename(filename), "text": text})

        for fn in (undo, redo, history, saveHistory):
            self.register_command(fn.__name__, fn)
        # names present at startup (type names etc.) are not "your" variables
        self._baseline = {k: id(v) for k, v in self.ns.items()}

        def log(filename="session.py"):
            """Start recording every successful command (save with stoplog())."""
            self.log_lines = []
            self._log_file = filename

        def stoplog():
            """Stop recording and save the log (offered as a download); replay with execfile."""
            if self.log_lines is None:
                raise GuessError("not logging; start with log('file.py')")
            lines = [l for l in self.log_lines if not l.lstrip().startswith(("log(", "stoplog"))]
            text = "\n".join(lines) + "\n"
            self.log_lines = None
            with open(self._log_file, "w", encoding="utf-8") as fh:
                fh.write(text)
            import os
            self.emit({"type": "download", "name": os.path.basename(self._log_file), "text": text})

        self.register_command("log", log)
        self.register_command("stoplog", stoplog)
        self._images = {}         # image source -> key already sent to the front end
        for name in colors.COLORS:
            if name.isidentifier() and not keyword.iskeyword(name):
                self._bind(name, colors.Color(name), kind="color")
        self._bind("g", self.graph, kind="graph")
        self._bind("Node", FieldNamespace(self.graph, NODE), kind="graph")
        self._bind("Edge", FieldNamespace(self.graph, EDGE), kind="graph")
        for f in self.graph.node_schema.values():
            self.on_field_added(f)
        for f in self.graph.edge_schema.values():
            self.on_field_added(f)

    # ---- namespace ------------------------------------------------------
    _PRIORITY = {"command": 4, "graph": 4, "field": 3, "node": 2, "color": 1}

    def _bind(self, name, obj, kind):
        cur = self.system.get(name)
        if cur is not None and self._PRIORITY[cur[1]] > self._PRIORITY[kind]:
            return False
        if cur is None and name in self.ns and not name.startswith("__"):
            # a user variable with this name exists; system binding wins
            pass
        self.system[name] = (obj, kind)
        self.ns[name] = obj
        return True

    def _unbind(self, name, obj):
        cur = self.system.get(name)
        if cur is not None and cur[0] is obj:
            del self.system[name]
            self.ns.pop(name, None)

    def is_protected(self, name):
        """The kind of system name this is ("command", "color", "field", "node",
        "graph"), or None."""
        cur = self.system.get(name)
        return cur[1] if cur is not None else None

    def _builtin_name(self, name):
        import builtins
        return not name.startswith("_") and hasattr(builtins, name) and name not in self.system

    def _take_over(self, names):
        """`from math import log`: an explicit import replaces a GUESS name for the
        session (del log brings it back)."""
        for name in names:
            cur = self.system.pop(name, None)
            if cur is None:
                continue
            self._shadowed[name] = cur
            what = {"command": f"the command {name}()", "color": f"the colour {name}",
                    "field": f"the field {name} (still Node.{name} / Edge.{name})",
                    "node": f"the node {name} (still g.getNodeByName({name!r}))"}.get(cur[1], name)
            self.emit({"type": "text", "text": f"note: {name} is now your import, not {what}; "
                                               f"del {name} brings it back\n"})

    # commands that draw a chart: they record how they were called, so the chart can be live
    CHART_COMMANDS = {"plotHistogram", "plotSizes", "plotSizesPie", "plotDistrib", "showChart",
                      "extinctions", "outbreaks", "offspring", "spread", "robustness"}

    def register_command(self, name, fn):
        if name in self.CHART_COMMANDS:
            fn = self._recording(fn)
        runtime.command(fn)
        self._bind(name, fn, kind="command")

    def _recording(self, fn):
        import functools

        @functools.wraps(fn)
        def chart_command(*args, **kwargs):
            outer = self._recipe
            if outer is None:
                self._recipe = (fn, args, kwargs)
            try:
                return fn(*args, **kwargs)
            finally:
                self._recipe = outer
        return chart_command

    # ---- live charts ------------------------------------------------------------
    MAX_RECIPES = 100

    def chart_out(self, msg):
        """Send a chart (or Altair chart) message, noting how it was made so it
        can be live."""
        cid = msg["id"]
        if self._recipe is not None and self._refreshing is None:
            self.chart_recipes.pop(cid, None)
            self.chart_recipes[cid] = self._recipe
            while len(self.chart_recipes) > self.MAX_RECIPES:
                old = next(iter(self.chart_recipes))
                del self.chart_recipes[old]
                self.live_charts.discard(old)
            if self.all_live:
                self.live_charts.add(cid)
        msg["canLive"] = cid in self.chart_recipes
        msg["live"] = cid in self.live_charts
        self.emit(msg)

    def set_live(self, cid, on=True):
        """Make a chart live (recomputed after every change) or not. Returns its state."""
        if cid not in self.chart_recipes:
            return False
        if on:
            self.live_charts.add(cid)
            self._refresh_live([cid])
        else:
            self.live_charts.discard(cid)
        return cid in self.live_charts

    def _refresh_live(self, ids=None):
        """Recompute live charts from their recipes. Isolated: whatever a chart
        command changes in the graph (spread colours nodes, say) is put back, and
        only chart messages get out."""
        ids = [c for c in (ids if ids is not None else list(self.live_charts)) if c in self.chart_recipes]
        if not ids or self._refreshing is not None:
            return
        g = self.graph
        before = self._undo_snapshot()
        outer, g.journal = g.journal, Journal()
        emit = self.emit
        self.emit = lambda m: emit(m) if m.get("type") in ("chart", "vega") else None
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = io.StringIO()
        failed = []
        try:
            for cid in ids:
                fn, args, kwargs = self.chart_recipes[cid]
                self._refreshing = cid
                try:
                    fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001 - a chart that can't be recomputed stops being live
                    failed.append((cid, e))
                finally:
                    self._refreshing = None
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self.emit = emit
            j, g.journal = g.journal, outer
            if self.graph is g:
                if j:
                    g.revert(j)
                if self.view.version != before["view_version"]:
                    self.view.restore(before["view"])
                g.states.clear()
                g.states.update(before["states"])
                g.ranges.clear()
                g.ranges.update(before["ranges"])
        for cid, e in failed:
            self.live_charts.discard(cid)
            self.emit({"type": "liveState", "id": cid, "live": False})
            self.emit({"type": "text", "text": f"note: a live chart stopped updating ({type(e).__name__}: {e})\n"})
        if j:
            self.flush()


    # graph listener callbacks
    def on_node_added(self, node):
        name = node._name
        # a node named len or max would hide the Python builtin: reach it with
        # g.getNodeByName('len') instead
        if name.isidentifier() and not keyword.iskeyword(name) and not self._builtin_name(name):
            self._bind(name, node, kind="node")

    def on_node_removed(self, node):
        # as in the original, nodes removed with remove()/removeNode() keep their
        # names (so removeNode(vx) … addNode(vx) works); undo, states and loading
        # a graph drop the names of nodes that are gone
        if not self.graph._keep_names:
            self._unbind(node._name, node)

    def on_graph_cleared(self):
        # output printed before this refers to elements of a graph that's gone
        self.graph_gen += 1
        self.provenance.clear()
        self.cell_items.clear()
        view = getattr(self, "view", None)
        if view is not None:
            view.reset_for_new_graph()
        if hasattr(self, "groups"):
            self.groups.clear()
        if "sel" in self.ns:
            self.ns["sel"] = GSet(annotation="selection")

    def on_field_removed(self, field):
        self._unbind(field.name, field)

    def on_field_added(self, field):
        if field.kind == EDGE and field.name in self.graph.node_schema:
            return  # node field wins; use Edge.<name>
        if self._builtin_name(field.name) or keyword.iskeyword(field.name):
            return  # a field called type, id or class: use Node.type, n.type, Node.class_
        self._bind(field.name, field, kind="field")

    def _restore_system(self):
        for name, (obj, _kind) in self.system.items():
            if self.ns.get(name) is not obj:
                self.ns[name] = obj
        # `del log` after `from math import log`: the GUESS name comes back
        for name in [n for n in self._shadowed if n not in self.ns or self.ns[n] is self._shadowed[n][0]]:
            obj, kind = self._shadowed.pop(name)
            self._bind(name, obj, kind)

    # ---- execution --------------------------------------------------------
    def run(self, source, *, interactive=True, filename="<console>"):
        """Compile and run Gython source. Returns True on success. The outermost
        run records an undo entry for whatever the code changed."""
        if self._run_depth:
            return self._run(source, interactive, filename)
        g = self.graph
        cell, self.current_cell = self.current_cell, None
        self.running_cell, self.chart_seq = cell, 0
        quiet, self.quiet_next = self.quiet_next, False
        before = self._undo_snapshot()
        g.journal = Journal()
        self._history_op = False
        if interactive and not quiet:
            self.executed.append(source)
        self._run_depth += 1
        try:
            ok = self._run(source, interactive, filename)
        finally:
            self._run_depth -= 1
            j, g.journal = g.journal, None
            if not self._history_op and not quiet:
                self._record_undo(source, j, before, cell)
            self._edge_colour_hint(j)
            if self.live_charts and (j or self._history_op or self.view.version != before["view_version"]
                                     or self.graph is not g):
                self._refresh_live()
        return ok

    def _run(self, source, interactive, filename):
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = _Writer(self)
        ok = True
        try:
            names, imports = set(), set()
            code = compiler.compile_gython(source, is_protected=self.is_protected,
                                           interactive=interactive, filename=filename, names=names,
                                           imports=imports)
            self._take_over(imports)
            self._prepare_fields(names)
            if "alt" not in self.ns and _ALT_USE.search(source):
                from . import vlcharts
                vlcharts.ensure_alt(self)
            exec(code, self.ns)
            if self.log_lines is not None and interactive:
                self.log_lines.append(source)
        except SyntaxError as e:
            ok = False
            self.emit(self._error_message(e, _format_syntax_error(e), filename))
        except BaseException as e:  # noqa: BLE001 - includes KeyboardInterrupt from interrupts
            ok = False
            self.emit(self._error_message(e, _format_exception(e), filename))
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self._restore_system()
            if self._run_depth <= 1:
                try:
                    self.view.refresh_legends()     # legendFor legends follow the colours
                except Exception:   # noqa: BLE001 - a stale legend must never break a command
                    pass
            self.flush()
        return ok

    # ---- undo / redo --------------------------------------------------------
    UNDO_LIMIT = 50
    UNDO_BUDGET = 3_000_000     # recorded values/ops kept across the whole stack

    def _edge_colour_hint(self, journal):
        """Setting edge colours has no visible effect while edges are drawn in
        their endpoints' colours: say so (once per command)."""
        mode = getattr(self.view, "edge_color", "original")
        if mode == "original" or journal is None:
            return
        if any(name == "color" and isinstance(elem, Edge) for elem, name, _old in journal.values.values()):
            self.emit({"type": "text", "text": f"note: edges are drawn in their nodes' colours (setEdgeColorMode(\"{mode}\")), "
                                               f"so their own colour doesn't show; setEdgeColorMode(\"original\") shows it\n"})

    def _undo_snapshot(self):
        g = self.graph
        return {"view": self.view.capture(), "view_version": self.view.version,
                "states": dict(g.states),
                "ranges": {k: list(v) for k, v in g.ranges.items()}}

    def _record_undo(self, label, journal, before, cell=None):
        g = self.graph
        entry = {"label": label, "journal": journal, "cell": cell}
        if self.view.version != before["view_version"]:
            entry["view"] = before["view"]
        if g.states != before["states"]:
            entry["states"] = before["states"]
        if {k: list(v) for k, v in g.ranges.items()} != before["ranges"]:
            entry["ranges"] = before["ranges"]
        if not journal and len(entry) == 3:
            return                      # nothing changed (a query, print, help, ...)
        self.undo_stack.append(entry)
        self.redo_stack.clear()
        if cell is not None and journal:
            self._note_provenance(cell, label, journal)
        total = sum(e["journal"].size() for e in self.undo_stack)
        while self.undo_stack and (len(self.undo_stack) > self.UNDO_LIMIT or total > self.UNDO_BUDGET):
            total -= self.undo_stack.pop(0)["journal"].size()

    # what each cell changed -------------------------------------------------------
    _ASPECT = {"x": "position", "y": "position", "width": "size", "height": "size", "size": "size",
               "labelvisible": "label", "labelcolor": "label", "labelsize": "label", "labelpos": "label",
               "strokecolor": "border"}
    PROVENANCE_CAP = 50000

    def _note_provenance(self, cell, code, journal):
        lines = [ln for ln in str(code).strip().splitlines() if ln.strip()]
        first = lines[0] if lines else ""
        self.cell_code[cell] = first[:70] + (" …" if len(first) > 70 or len(lines) > 1 else "")
        touched = {}
        for elem, name, _old in journal.values.values():
            if not isinstance(elem, (Node, Edge)):
                continue
            key = ("n" if isinstance(elem, Node) else "e", elem._id)
            aspect = self._ASPECT.get(name, name)
            if isinstance(elem, Edge) and name == "width":
                aspect = "width"
            touched.setdefault(key, set()).add(aspect)
        for op in journal.ops:
            if op[0] == "add" and isinstance(op[1], (Node, Edge)):
                key = ("n" if isinstance(op[1], Node) else "e", op[1]._id)
                touched.setdefault(key, set()).add("added")
        for key, aspects in touched.items():
            if "added" in aspects:
                aspects = {"added"}          # a new element: its fields came with it
            rec = self.provenance.setdefault(key, {})
            for a in aspects:
                rec[a] = cell
        self.cell_items[cell] = list(touched)[:self.PROVENANCE_CAP]

    def cell_changes(self, cell):
        """The elements a console cell changed (hover its number to see them)."""
        return [list(k) for k in self.cell_items.get(cell, [])]

    def _forget_cell(self, cell):
        """After undo: what that cell did is gone."""
        for key in self.cell_items.pop(cell, []):
            rec = self.provenance.get(key)
            if rec:
                for a in [a for a, c in rec.items() if c == cell]:
                    del rec[a]

    def _revert(self, entry):
        g = self.graph
        inv = {"label": entry["label"], "journal": g.revert(entry["journal"]), "cell": entry.get("cell")}
        if entry.get("cell") is not None:
            self._forget_cell(entry["cell"])
        if "view" in entry:
            inv["view"] = self.view.capture()
            self.view.restore(entry["view"])
        if "states" in entry:
            inv["states"] = dict(g.states)
            g.states.clear()
            g.states.update(entry["states"])
        if "ranges" in entry:
            inv["ranges"] = {k: list(v) for k, v in g.ranges.items()}
            g.ranges.clear()
            g.ranges.update(entry["ranges"])
        return inv

    def undo(self):
        """Reverse the most recent command that changed the graph or display."""
        self._history_op = True
        if not self.undo_stack:
            print("nothing to undo")
            return
        print(f"undid: {_first_line(self._step(back=True)['label'])}")

    def redo(self):
        """Re-apply the last command undone with undo()."""
        self._history_op = True
        if not self.redo_stack:
            print("nothing to redo")
            return
        print(f"redid: {_first_line(self._step(back=False)['label'])}")

    def _step(self, back):
        """One undo (back) or redo step; returns the entry it reversed."""
        src, dst = (self.undo_stack, self.redo_stack) if back else (self.redo_stack, self.undo_stack)
        entry = src.pop()
        dst.append(self._revert(entry))
        if entry.get("cell") is not None:
            self.emit({"type": "undone", "cell": entry["cell"], "undone": back})
        return entry

    # ---- the history scrubber ------------------------------------------------
    MAX_STEP_ITEMS = 5000

    @staticmethod
    def _journal_items(journal):
        """The nodes and edges a recorded step touched (changed, added or removed)."""
        seen = {}
        for elem, _name, _old in journal.values.values():
            if isinstance(elem, (Node, Edge)):
                seen[("n" if isinstance(elem, Node) else "e", elem._id)] = None
        for op in journal.ops:
            if op[0] in ("add", "rem") and isinstance(op[1], (Node, Edge)):
                seen[("n" if isinstance(op[1], Node) else "e", op[1]._id)] = None
        return list(seen)

    def history_steps(self):
        """The undo history for the scrubber: every recorded step, oldest first
        (undone ones after `at`), with the elements each touched."""
        def info(entry, done):
            items = self._journal_items(entry["journal"])
            what = []
            if "view" in entry:
                what.append("display")
            if "states" in entry:
                what.append("states")
            return {"label": _first_line(entry["label"])[:90], "cell": entry.get("cell"), "done": done,
                    "count": len(items), "also": what}
        steps = [info(e, True) for e in self.undo_stack] + [info(e, False) for e in reversed(self.redo_stack)]
        return {"steps": steps, "at": len(self.undo_stack), "gid": self.graph_gen}

    def history_items(self, i):
        """The elements step i (as listed by history_steps) touched."""
        steps = self.undo_stack + self.redo_stack[::-1]
        if not 0 <= i < len(steps):
            return []
        return [list(k) for k in self._journal_items(steps[i]["journal"])[:self.MAX_STEP_ITEMS]]

    def history_goto(self, at):
        """Undo or redo until `at` steps are applied (the scrubber); quietly,
        then redraw. Returns the new position."""
        at = max(0, min(int(at), len(self.undo_stack) + len(self.redo_stack)))
        while len(self.undo_stack) > at:
            self._step(back=True)
        while len(self.undo_stack) < at:
            self._step(back=False)
        try:
            self.view.refresh_legends()
        except Exception:   # noqa: BLE001 - a stale legend must never break the scrubber
            pass
        self.flush()
        self._refresh_live()
        return at

    def history(self):
        """Every command run in this session, in order (including Run again)."""
        for i, src in enumerate(self.executed, 1):
            lines = src.splitlines() or [""]
            print(f"[{i}] {lines[0]}")
            for line in lines[1:]:
                print(" " * (len(str(i)) + 3) + line)

    def set_selection(self, ids):
        """The display's selection (box/lasso/shift-click) as the variable `sel`."""
        g = self.graph
        self.ns["sel"] = GSet((n for n in map(g.node_by_id, ids) if n is not None), "selection")
        return len(self.ns["sel"])

    def _prepare_fields(self, names):
        """Compute fields such as pagerank or closeness that the code names but
        that have not been used yet, so `sizeBy(pagerank, 5, 20)` just works."""
        g = self.graph
        for name in names:
            if name in self.ns or name in g.node_schema or name in g.edge_schema:
                continue
            for kind in (NODE, EDGE):
                if (kind, name) in g.lazy_fields:
                    g._lazy_field(kind, name)
                    break

    # ---- introspection for the console ----------------------------------------------
    def completions(self, text):
        """Tab completion for the identifier (or dotted path) ending `text`."""
        import builtins
        import re
        m = re.search(r"([A-Za-z_][\w]*(?:\.[A-Za-z_]\w*)*)?\.?$", text)
        token = m.group(0) if m else ""
        if "." in token:
            path, prefix = token.rsplit(".", 1)
            obj = self._resolve_path(path)
            if obj is _MISSING:
                return {"prefix": prefix, "items": []}
            try:
                names = dir(obj)
            except Exception:  # noqa: BLE001
                names = []
            if isinstance(obj, GSet) and obj:
                try:
                    names = sorted(set(names) | set(dir(obj[0])))
                except Exception:  # noqa: BLE001
                    pass
        else:
            prefix = token
            names = set(self.ns) | set(dir(builtins)) | set(keyword.kwlist)
        items = sorted(n for n in names if n.startswith(prefix) and not n.startswith("__")
                       and (prefix.startswith("_") or not n.startswith("_")))
        return {"prefix": prefix, "items": items[:200]}

    def _resolve_path(self, path):
        import builtins
        parts = path.split(".")
        obj = self.ns.get(parts[0], getattr(builtins, parts[0], _MISSING))
        for p in parts[1:]:
            if obj is _MISSING:
                break
            # never trigger lazy computations (e.g. betweenness) from completion
            if isinstance(obj, (Node, Edge)):
                return _MISSING
            obj = getattr(obj, p, _MISSING)
        return obj

    def _error_message(self, e, text, filename="<console>"):
        """An error for the console: the full text, a one-line summary (with a
        "did you mean" suggestion when a name is misspelt) and the line of the
        cell it happened on."""
        line = None
        if isinstance(e, SyntaxError):
            line = e.lineno
            summary = f"{'Syntax error' if type(e) is SyntaxError else 'Error'}: {e.msg}"
        elif isinstance(e, KeyboardInterrupt):
            summary = "Interrupted"
        else:
            tb = e.__traceback__
            while tb is not None:
                if tb.tb_frame.f_code.co_filename == filename:
                    line = tb.tb_lineno
                tb = tb.tb_next
            summary = str(e) if isinstance(e, GuessError) else f"{type(e).__name__}: {e}"
            hint = self._suggest(e)
            if hint and "did you mean" not in summary.lower():
                summary += f" — did you mean {hint}?"
        msg = {"type": "error", "text": text, "summary": summary}
        if line:
            msg["line"] = line
        try:
            segs = self._link_text(summary, e)
        except Exception:   # noqa: BLE001 - linking must never hide the error itself
            segs = None
        if segs:
            msg["segs"], msg["gid"] = segs, self.graph_gen
        return msg

    # a quoted name, an edge written a-b or a->b, or a plain name
    _LINK_TOKEN = re.compile(r"""'([^'\n]{1,80})'|"([^"\n]{1,80})"|\b([A-Za-z_]\w*)(?:(->|-)([A-Za-z_]\w*))?\b""")
    MAX_ERROR_LINKS = 40

    def _link_text(self, text, e=None):
        """The text with the nodes and edges it names made into links (hover
        highlights them; click selects), or None when it names none. A name
        links when it is quoted and is a node's name, when it is a variable
        holding that node (v1), or when the exception carries the element."""
        g = self.graph
        carried = {}
        for a in getattr(e, "args", ()) or ():
            for x in (a if isinstance(a, (list, tuple, set, frozenset, GSet)) else [a]):
                if isinstance(x, Node):
                    carried[x._name] = x
                elif isinstance(x, Edge):
                    carried[repr(x)] = x

        def node(name, quoted):
            el = carried.get(name)
            if isinstance(el, Node):
                return el
            if quoted:
                return g._nodes.get(name)
            v = self.ns.get(name)
            return v if isinstance(v, Node) and v._name == name else None

        def alive(el):
            if isinstance(el, Node):
                return g._nodes.get(el._name) is el
            return el is not None and alive(el._n1) and alive(el._n2) and \
                any(x is el for x in el._n1._inc.values())

        def edge(a, arrow, b):
            el = carried.get(f"{a}{arrow}{b}")
            if isinstance(el, Edge):
                return el
            na, nb = g._nodes.get(a), g._nodes.get(b)
            if na is None or nb is None:
                return None
            for x in na._inc.values():
                if x.opposite(na) is nb and (arrow == "-") != x._directed:
                    if arrow == "-" or x._n1 is na:
                        return x
            return None

        segs, pos, links = [], 0, 0
        for m in self._LINK_TOKEN.finditer(text):
            if links >= self.MAX_ERROR_LINKS:
                break
            quoted = m.group(1) or m.group(2)
            el = None
            if quoted is not None:
                el = node(quoted, True)
                if el is None and quoted in carried:
                    el = carried[quoted]
            elif m.group(4):
                el = edge(m.group(3), m.group(4), m.group(5))
            else:
                el = node(m.group(3), False)
            if el is None or not alive(el):
                continue
            if m.start() > pos:
                segs.append(text[pos:m.start()])
            seg = {"n": el._id, "t": el._name} if isinstance(el, Node) else edge_seg(el)
            if quoted is not None:
                q = text[m.start()]
                segs += [q, seg, q]
            else:
                segs.append(seg)
            pos = m.end()
            links += 1
        if not links:
            return None
        if pos < len(text):
            segs.append(text[pos:])
        return segs

    def _gnot(self, v):
        """``not s`` used as a value: on a set of nodes (or edges), the others."""
        if not isinstance(v, GSet):
            return not v
        items = list(v)
        g = items[0]._g if items and isinstance(items[0], (Node, Edge)) else self.graph
        every = g._edges_list() if items and isinstance(items[0], Edge) else g._nodes_list()
        keep = set(map(id, items))
        ann = getattr(v, "annotation", None)
        return GSet((x for x in every if id(x) not in keep), annotation=f"not ({ann})" if ann else None)

    def _suggest(self, e):
        import difflib
        name, pool = None, []
        g = self.graph
        if isinstance(e, NameError):
            name = getattr(e, "name", None)
            pool = list(self.ns) + list(g.node_schema) + list(g.edge_schema)
        elif isinstance(e, AttributeError):
            name = getattr(e, "name", None)
            m = None
            if name is None:
                import re
                m = re.search(r"no (?:field|attribute) '(\w+)'", str(e))
                name = m.group(1) if m else None
            obj = getattr(e, "obj", None)
            pool = list(g.node_schema) + list(g.edge_schema)
            if obj is not None and not isinstance(obj, (Node, Edge, GSet)):
                try:
                    pool = [n for n in dir(obj) if not n.startswith("_")]
                except Exception:  # noqa: BLE001
                    pool = []
        if not name:
            return None
        if isinstance(e, AttributeError) and "'NoneType'" in str(e):
            return None                   # the object is missing, not misspelt (e.g. no such node)
        close = difflib.get_close_matches(name, [p for p in pool if not p.startswith("_") and p != name],
                                          n=1, cutoff=0.75)
        return f"'{close[0]}'" if close else None

    def help_index(self):
        """Commands (name, signature, doc, group) and curated examples for the
        help browser and the command palette."""
        import inspect
        from . import helpdata
        titles = dict(helpdata.GROUPS)
        cmds = []
        for name, (obj, kind) in self.system.items():
            if kind != "command" or not callable(obj) or name.startswith("_"):
                continue
            try:
                sig = str(inspect.signature(obj))
            except (TypeError, ValueError):
                sig = "(...)"
            key = helpdata.group_of(name, obj)
            cmds.append({"name": name, "sig": f"{name}{sig}", "doc": inspect.getdoc(obj) or "",
                         "group": titles[key]})
        cmds.sort(key=lambda c: c["name"].lower())
        return {"commands": cmds, "groups": [t for _k, t in helpdata.GROUPS],
                "examples": helpdata.examples()}

    def workspace(self):
        """User variables (name, type, short value, linked elements) plus saved
        states and styles, for the Variables panel."""
        import types
        out = []
        hidden = set(runtime.HELPERS) | {"__name__", "__builtins__", "__display__", "__gnot__", "__gfstr__", "_", "print", "__result__"}
        for name, v in self.ns.items():
            if name in hidden or name.startswith("__") or name in self.system:
                continue
            if name != "sel" and self._baseline.get(name) == id(v):
                continue
            if isinstance(v, types.ModuleType):
                continue
            rec = {"name": name, "type": type(v).__name__}
            items = []
            if isinstance(v, (Node, Edge)):
                items = [v]
                rec["value"] = repr(v) if isinstance(v, Edge) else v._name
            elif isinstance(v, (GSet, list, tuple, set)) and _contains_elements(v):
                flat = [x for x in _flatten(v) if isinstance(x, (Node, Edge))]
                items = flat
                nn = sum(isinstance(x, Node) for x in flat)
                parts = [f"{nn} node{'s' * (nn != 1)}" if nn else "", f"{len(flat) - nn} edge{'s' * (len(flat) - nn != 1)}" if len(flat) > nn else ""]
                rec["value"] = ", ".join(p for p in parts if p)
            elif callable(v):
                rec["type"] = "function"
                rec["value"] = ""
            else:
                try:
                    r = repr(v)
                except Exception:  # noqa: BLE001
                    r = "?"
                rec["value"] = r if len(r) <= 80 else r[:77] + "..."
            if items:
                rec["items"] = [["n" if isinstance(x, Node) else "e", x._id] for x in items[:2000]]
            out.append(rec)
        out.sort(key=lambda r: (r["type"] == "function", r["name"].lower()))
        return {"vars": out, "states": [str(k) for k in self.graph.states if not str(k).startswith("slide:")],
                "styles": list(self.view.styles)}

    def panel_data(self, what, kind="n", ids=None):
        """Data for the page's panels: "table" rows, "fields" summaries or "workspace"."""
        from . import styles
        if what == "suggest":
            return self.suggestions()
        if what == "workspace":
            return self.workspace()
        if what == "timeline":
            from . import timeline
            return timeline.info(self.graph, kind or None)
        if what == "table":
            return styles.table_data(self.graph, kind, ids)
        return styles.field_info(self.graph, kind)

    def command_docs(self):
        """name -> 'signature\ndoc' for every system command (for hover help)."""
        import inspect
        out = {}
        for name, (obj, kind) in self.system.items():
            if kind != "command" or not callable(obj):
                continue
            try:
                sig = str(inspect.signature(obj))
            except (TypeError, ValueError):
                sig = "(...)"
            out[name] = f"{name}{sig}\n{inspect.getdoc(obj) or ''}".strip()
        return out

    def dispatch(self, target, name, value=None):
        """Run the Python handler for a front-end event (widget, timer, graph mouse)."""
        from .gui import call_flexibly
        if name == "menuEvent":
            from .compat import menu_handler
            fn, args = menu_handler(self, target, value)
        else:
            fn, args = self.gui.handler_for(target, name, value)
        if fn is None:
            return False
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = _Writer(self)
        try:
            call_flexibly(fn, args)
        except BaseException as e:  # noqa: BLE001
            self.emit({"type": "error", "text": _format_exception(e)})
            # a timer whose handler fails is stopped, so errors don't repeat forever
            t = self.gui.timers.get(target)
            if t is not None:
                t.stop()
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self._restore_system()
            self.flush()
        return True

    def run_script(self, source, filename="<script>"):
        """Execute Gython source non-interactively in the session namespace."""
        code = compiler.compile_gython(source, is_protected=self.is_protected,
                                       interactive=False, filename=filename)
        exec(code, self.ns)

    def save_state_json(self, since=-1):
        """Serialized session for autosave (a JSON string), or None if nothing
        visible has changed since revision `since`. Returns [revision, json]."""
        import json
        from . import persist
        if self.revision == since:
            return None
        return [self.revision, json.dumps(persist.serialize(self))]

    def is_complete(self, source):
        """True if source is a complete statement (used for multi-line entry)."""
        try:
            compiler.transform(source + "\n", is_protected=None)
        except SyntaxError as e:
            msg = str(e.msg or "")
            if "unexpected EOF" in msg or "was never closed" in msg or "expected an indented block" in msg:
                return False
            return True
        lines = source.split("\n")
        if len(lines) > 1:
            return lines[-1].strip() == ""   # a blank line ends a block
        return not lines[0].rstrip().endswith(":")

    # ---- output -----------------------------------------------------------
    def _print(self, *args, sep=" ", end="\n", file=None, flush=False):
        """print(), except that nodes, edges and sets of them come out as linked
        output (hover to highlight, click to select) like displayed values."""
        import builtins
        if (file is not None or end != "\n" or not isinstance(sep, str)
                or not any(_linkable(a) for a in args)):
            return builtins.print(*args, sep=sep, end=end, file=file, flush=flush)
        segs = []
        for i, a in enumerate(args):
            if i:
                segs.append(sep)
            if isinstance(a, LinkedStr) and a.linked:
                segs.extend(a.segs)            # printed text: no quotes
            else:
                segs.append(segment(a) if _linkable(a) else str(a))
        self.emit({"type": "out", "segs": segs, "gid": self.graph_gen})

    def display(self, value):
        if value is None:
            return
        self.ns["_"] = value
        from .vlcharts import is_altair
        if is_altair(value):
            self.system["showChart"][0](value)
            return
        self.emit({"type": "out", "segs": [segment(value)], "gid": self.graph_gen})

    # ---- render state ---------------------------------------------------------
    def node_record(self, n):
        v = n._vals
        d = self.graph.node_schema
        def val(name):
            return v.get(name, d[name].default)
        color, alpha = colors.to_rgba_int(val("color"), (100, 149, 237, 255))
        stroke = val("strokecolor")
        lc = val("labelcolor")
        return {
            "i": n._id, "name": n._name,
            "x": val("x"), "y": val("y"), "w": val("width"), "h": val("height"),
            "c": color, "a": alpha, "s": val("style"),
            "sc": colors.to_rgba_int(stroke)[0] if stroke else -1,
            "l": val("label") if val("label") is not None else n._name,
            "lv": bool(val("labelvisible")),
            "lc": colors.to_rgba_int(lc)[0] if lc else -1,
            "v": bool(val("visible")),
            "img": self._image_key(val("image")),
            **({"lp": val("labelpos")} if val("labelpos") not in (None, "right") else {}),
            **({"ls": float(val("labelsize"))} if val("labelsize") not in (None, 1.0) else {}),
            **({"m": 1} if n._id in getattr(self, "groups", ()) else {}),
            **({"p": self._pie(n)} if getattr(self.view, "pie", None) else {}),
        }

    def _pie(self, n):
        pie = self.view.pie
        if pie["mode"] == "fields":
            out = []
            schema = self.graph.node_schema
            for f in pie["fields"]:
                try:
                    v = float(schema[f].get(n) or 0) if f in schema else 0.0
                except (TypeError, ValueError):
                    v = 0.0
                out.append(max(v, 0.0) if v == v else 0.0)
            return out
        field = self.graph.node_schema.get(pie["field"])
        counts = [0] * len(pie["labels"])
        if field is None:
            return counts
        index = {v: i for i, v in enumerate(pie["values"])}
        for e in n._inc.values():
            other = e.opposite(n)
            if other is n:
                continue
            k = index.get(field.get(other), len(pie["labels"]) - 1 if len(pie["labels"]) > len(pie["values"]) else None)
            if k is not None:
                counts[k] += 1
        return counts

    def _image_key(self, source):
        """Register an image with the front end once; node records carry the key."""
        if not source:
            return None
        key = self._images.get(source)
        if key is None:
            import os
            from .visuals import _data_url
            try:
                url = _data_url(source) if os.path.exists(source) else source
            except OSError:
                url = source
            key = f"img{len(self._images) + 1}"
            self._images[source] = key
            self.emit({"type": "image", "key": key, "url": url})
        return key

    def edge_record(self, e):
        v = e._vals
        d = self.graph.edge_schema
        def val(name):
            return v.get(name, d[name].default)
        color, alpha = colors.to_rgba_int(val("color"), (252, 216, 112, 255))
        lc = val("labelcolor")
        return {
            "i": e._id, "s": e._n1._id, "t": e._n2._id, "d": e._directed,
            "c": color, "a": alpha, "w": val("width"), "v": bool(val("visible")),
            "l": val("label") if val("label") is not None else "",
            "lv": bool(val("labelvisible")),
            "lc": colors.to_rgba_int(lc)[0] if lc else -1,
            "b": [c for p in self.graph.bends.get(e, ()) for c in p] or None,
            **({"ls": float(val("labelsize"))} if val("labelsize") not in (None, 1.0) else {}),
        }

    def scene(self):
        g = self.graph
        # a new graph was loaded: computed fields the old one was using are
        # computed again, so code that names them (pagerank, ...) still works
        dropped, g._dropped_lazy = g._dropped_lazy, set()
        for kind, name in sorted(dropped):
            schema = g.node_schema if kind == NODE else g.edge_schema
            if name not in schema:
                f = g._lazy_field(kind, name)
                if f is not None and g.journal is not None:
                    g.journal.ops.append(("field", schema, name, f))   # undo takes it away again
        g.reset_dirty()
        ws = getattr(self, "workspaces", None)
        self.emit({"type": "scene", "gid": self.graph_gen, "gname": ws["current"] if ws else "",
                   "nodes": [self.node_record(n) for n in g._nodes_list()],
                   "edges": [self.edge_record(e) for e in g._edges_list()]})
        self.view.dirty = True
        self._flush_overlay()

    def _flush_overlay(self):
        if self.view.dirty:
            self.revision += 1
            self.view.dirty = False
            self.emit(self.view.record())

    def tick_due(self):
        """True when tick() would actually send an update now."""
        return time.monotonic() - getattr(self, "_last_tick", 0.0) >= 1 / 30

    def tick(self, force=False):
        """Send pending visual changes now (at most ~30 times a second).

        Long-running commands (iterative layouts, animations) call this so the
        display updates while they run.
        """
        now = time.monotonic()
        if force or now - getattr(self, "_last_tick", 0.0) >= 1 / 30:
            self._last_tick = now
            self.flush()

    def flush(self):
        g = self.graph
        if not (g.dirty_nodes or g.dirty_edges or g.removed_nodes or g.removed_edges or g.moved_nodes):
            self._flush_overlay()
            return
        nodes = [self.node_record(g._node_ids[i]) for i in sorted(g.dirty_nodes) if i in g._node_ids]
        # nodes whose only change is position: a flat [id, x, y, ...] array
        pos = []
        for i in g.moved_nodes - g.dirty_nodes:
            n = g._node_ids.get(i)
            if n is not None:
                pos += [i, n._vals.get("x", 500.0), n._vals.get("y", 500.0)]
        edges = [self.edge_record(g._edges[i]) for i in sorted(g.dirty_edges) if i in g._edges]
        msg = {"type": "patch", "nodes": nodes, "edges": edges,
               "removedNodes": sorted(g.removed_nodes), "removedEdges": sorted(g.removed_edges)}
        if pos:
            msg["pos"] = pos
        if self.pending_morph:
            msg["morph"] = self.pending_morph
            self.pending_morph = None
        g.reset_dirty()
        self.revision += 1
        self.emit(msg)
        if msg["removedNodes"]:
            self.view.dirty = True   # hull membership may have changed
        self._flush_overlay()

    # ---- queries from the front end ------------------------------------------
    def describe(self, kind, ident):
        """Tooltip/info text for a node or edge id."""
        g = self.graph
        elem = g.node_by_id(ident) if kind == "n" else g.edge_by_id(ident)
        if elem is None:
            return None
        schema = g.node_schema if kind == "n" else g.edge_schema
        rows = []
        for name, f in schema.items():
            try:
                rows.append([name, _short(f.get(elem))])
            except Exception as ex:  # noqa: BLE001
                rows.append([name, f"<{type(ex).__name__}>"])
        prov = sorted(self.provenance.get((kind, ident), {}).items(), key=lambda kv: -kv[1])
        made = [[aspect, cell, self.cell_code.get(cell, "")] for aspect, cell in prov]
        return {"title": repr(elem), "rows": rows, "prov": made}

    # ---- hovering code -------------------------------------------------------------
    _PEEK_OK = None

    def peek(self, expr):
        """What a name or a query in executed code means now, for hovering it:
        {title, lines, items, colors?}. Only side-effect-free expressions are
        evaluated (names, constants, comparisons, & | and or not in, tuples;
        no calls), and nothing is recorded."""
        import ast
        expr = str(expr).strip()
        if not expr or len(expr) > 400:
            return None
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError:
            return None
        ok = (ast.Expression, ast.Name, ast.Load, ast.Constant, ast.Compare, ast.BoolOp, ast.And, ast.Or,
              ast.BinOp, ast.BitAnd, ast.BitOr, ast.UnaryOp, ast.Not, ast.USub, ast.Tuple, ast.List,
              ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
              ast.Attribute)
        for node in ast.walk(tree):
            if not isinstance(node, ok):
                return None
            if isinstance(node, ast.BinOp) and not isinstance(node.op, (ast.BitAnd, ast.BitOr)):
                return None
            if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or not isinstance(node.value, ast.Name)):
                return None
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        if any(n.startswith("__") for n in names):
            return None
        try:
            self._prepare_fields(names)
            code = compiler.compile_gython(f"__peek__ = ({expr})", is_protected=None, interactive=False)
            ns = self.ns
            old_out = sys.stdout
            sys.stdout = io.StringIO()            # a peek prints nothing
            try:
                exec(code, ns)
                value = ns.pop("__peek__", None)
            finally:
                sys.stdout = old_out
        except Exception:  # noqa: BLE001 - a hover must never fail loudly
            return None
        return self._peek_value(expr, value)

    def cluster_info(self, field):
        """For the Cluster tool: the nodes labelled in `field` ([[id, value], ...]),
        the field's type, and the next numeric id (one past the largest)."""
        f = self.graph.node_schema.get(str(field))
        if f is None:
            return {"exists": False, "type": None, "labels": [], "next": 1, "total": len(self.graph.nodes)}
        labels, nums = [], []
        for n in self.graph._nodes_list():
            v = n._vals.get(f.name, f.default)
            if v is None or v == "":
                continue
            labels.append([n._id, v])
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                nums.append(v)
        nxt = int(max(nums)) + 1 if nums else 1
        return {"exists": True, "type": f.type, "labels": labels, "next": nxt, "total": len(self.graph.nodes)}

    # display plumbing: never suggested
    _PLUMBING = {"x", "y", "visible", "strokecolor", "labelcolor", "fixed", "style", "width", "height", "image",
                 "labelvisible", "labelsize", "labelpos", "label", "color", "name", "node1", "node2", "source",
                 "destination", "size"}

    def suggestions(self, limit=12):
        """Short commands worth trying on the graph showing now, for the code
        box's rotating hint: they use its own fields (a category to colour by,
        a number to rank by) and node names, so each one works as written."""
        import random
        g = self.graph
        if not g._nodes:
            return ['makeFromGDF("sample.gdf")', "demo()", "help()"]
        nodes = g._nodes_list()[:2000]

        def usable(name):
            return name.isidentifier() and not keyword.iskeyword(name) and \
                self.is_protected(name) in (None, "field") and name not in self._PLUMBING

        cats, nums = [], []
        for name, f in g.node_schema.items():
            if not usable(name) or getattr(f, "builtin", False) and name not in ("degree",):
                continue
            vals = [n._vals.get(name, f.default) for n in nodes]
            vals = [v for v in vals if v not in (None, "")]
            if not vals:
                continue
            if f.type == "VARCHAR" or f.type == "BOOLEAN":
                k = len(set(vals))
                if 2 <= k <= 40 and k < len(vals):
                    cats.append(name)
            elif f.type in ("INTEGER", "DOUBLE") and name != "degree" and len(set(vals)) > 2 \
                    and name.lower() not in ("lat", "lon", "lng", "latitude", "longitude", "id", "year"):
                nums.append(name)
        enums = [name for name, f in g.edge_schema.items()
                 if usable(name) and f.type in ("INTEGER", "DOUBLE") and not getattr(f, "builtin", False)]
        named = [n._name for n in nodes if n._name.isidentifier() and not keyword.iskeyword(n._name)
                 and self.ns.get(n._name) is n]
        degs = sorted(n.degree for n in nodes)
        cut = degs[int(len(degs) * 0.9)] if degs else 5

        out = []
        for c in cats[:2]:
            out += [f"colorize({c})", f"groupBy({c})", f"plotSizes({c})", f"interEdges({c}).color = red"]
        for v in nums[:2]:
            out += [f"highest({v}, 5)", f"plotHistogram({v})"]
        for e in enums[:1]:
            out += [f"plotHistogram({e})", f"({e} > {e}.median).color = red"]
        if named:
            a = named[0]
            out += [f"{a}.getNeighbors()", f"center({a})"]
            if len(named) > 1:
                out.append(f"shortestPath({a}, {named[-1]}).color = red")
        out += [f"(degree > {cut}).color = orange", "highest(betweenness, 5)", "louvainClusters()",
                "plotHistogram(degree)", "gemLayout()", "resizeLinear(degree, 5, 30)", "demo('advanced')"]
        seen, uniq = set(), []
        for c in out:
            if c not in seen and len(c) <= 40:
                seen.add(c)
                uniq.append(c)
        random.shuffle(uniq)
        return uniq[:limit]

    def table_query(self, expr, kind="n", full=False):
        """Filter the data table with Gython: the ids (of kind "n" or "e") of
        the nodes or edges `expr` gives. Plain queries (names, comparisons,
        & | and or not in) are evaluated as they're typed (full=False); with
        full=True (Enter) any expression runs, calls included, inside a scratch
        copy of the graph with output muted, so it changes nothing.
        Returns {ids, other, title} or {error} (or None: not a query; the
        table then matches the text instead)."""
        import ast
        expr = str(expr).strip()
        if not expr:
            return None
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            return {"error": f"syntax error: {e.msg}"} if full else None
        body = tree.body
        if isinstance(body, ast.Name):
            v = self.ns.get(body.id)
            if isinstance(v, (Node, Edge)) or v is None:
                return None              # a bare name: v1 matches v1, v10, … as text
        if not full:
            info = self.peek(expr)
            if info is None or not info.get("items") and "empty now" not in info.get("title", ""):
                return None
            value_items = [tuple(x) for x in info["items"]]
            if len(value_items) >= MAX_EXTRA:      # peek caps its items: evaluate fully
                return self.table_query(expr, kind, full=True) if not _has_call(tree) else None
        else:
            value_items = self._eval_isolated(expr)
            if isinstance(value_items, str):
                return {"error": value_items}
        ids = [i for k, i in value_items if k == kind]
        other = sum(1 for k, _i in value_items if k != kind)
        return {"ids": ids, "other": other, "title": expr}

    def _eval_isolated(self, expr):
        """Evaluate an expression with output muted and its changes to the graph
        and display reverted (as undo would): its elements as [(kind, id)], or
        an error message."""
        g = self.graph
        before = self._undo_snapshot()
        outer, g.journal = g.journal, Journal()
        emit, self.emit = self.emit, (lambda msg: None)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = io.StringIO()
        try:
            names = set()
            code = compiler.compile_gython(f"__tq__ = ({expr})", is_protected=self.is_protected,
                                           interactive=False, names=names)
            self._prepare_fields(names)
            exec(code, self.ns)
            value = self.ns.pop("__tq__", None)
            if isinstance(value, (Node, Edge)):
                value = [value]
            if not isinstance(value, (GSet, list, tuple, set, frozenset, dict)):
                return f"{expr} isn't a set of nodes or edges"
            return [("n" if isinstance(x, Node) else "e", x._id) for x in _walk_elements(value) if x._g is g]
        except Exception as e:  # noqa: BLE001 - shown in the table, not raised
            return str(e) if isinstance(e, GuessError) else f"{type(e).__name__}: {e}"
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self.ns.pop("__tq__", None)
            j, g.journal = g.journal, outer
            if self.graph is g:
                if j:
                    g.revert(j)
                if self.view.version != before["view_version"]:
                    self.view.restore(before["view"])
                g.states.clear()
                g.states.update(before["states"])
                g.ranges.clear()
                g.ranges.update(before["ranges"])
            self.emit = emit
            if j:
                self.flush()        # whatever it touched is redrawn as it was

    def _peek_value(self, expr, value):
        def item(x):
            return ["n" if isinstance(x, Node) else "e", x._id]
        if isinstance(value, (Node, Edge)):
            return {"title": f"{expr}: {value!r}", "lines": [], "items": [item(value)]}
        if isinstance(value, Field):
            return self._peek_field(expr, value)
        if isinstance(value, (GSet, list, tuple, set, frozenset, dict)) and _contains_elements(value):
            els = list(_walk_elements(value))
            nodes = sum(1 for x in els if isinstance(x, Node))
            what = ", ".join(p for p in (f"{nodes} node{'s' * (nodes != 1)}" if nodes else "",
                                         f"{len(els) - nodes} edge{'s' * (len(els) - nodes != 1)}"
                                         if len(els) > nodes else "") if p) or "empty"
            ann = getattr(value, "annotation", None) if isinstance(value, GSet) else None
            names = [x._name if isinstance(x, Node) else repr(x) for x in els[:12]]
            lines = [", ".join(names) + (" …" if len(els) > 12 else "")] if names else []
            import re
            same = ann and re.sub(r"\W", "", ann.replace('"', "'")) == re.sub(r"\W", "", expr.replace('"', "'"))
            return {"title": f"{expr} — {what} now" + (f" ({ann})" if ann and not same else ""),
                    "lines": lines, "items": [item(x) for x in els[:MAX_EXTRA]]}
        if isinstance(value, GSet):
            return {"title": f"{expr} — empty now", "lines": [], "items": []}
        return {"title": f"{expr} = {_safe_repr(value)[:200]}", "lines": [], "items": []}

    def _peek_field(self, expr, f):
        """A field: what's in it, and the colours colouring by it would give (shown
        while hovering, never applied)."""
        elems = f.elements()
        vals = [(e, f.get(e)) for e in elems]
        nums = [v for _e, v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        kind = "edge" if f.kind == EDGE else "node"
        lines, colors = [], []
        groups = {}
        for e, v in vals:
            try:
                groups.setdefault(v, []).append(e)
            except TypeError:
                pass
        if nums and len(groups) > 12:
            lo, hi = min(nums), max(nums)
            srt = sorted(nums)
            lines.append(f"min {lo:.4g} · median {srt[len(srt) // 2]:.4g} · max {hi:.4g} ({len(nums)} values)")
            yel, red = (255, 255, 0), (255, 0, 0)
            for e, v in vals:
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    t = (v - lo) / (hi - lo) if hi > lo else 0.5
                    rgb = [round(a + (b - a) * t) for a, b in zip(yel, red)]
                    colors.append([e._id, (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]])
            lines.append("shown: coloured by it, yellow (low) to red (high)")
        else:
            order = sorted(groups.items(), key=lambda kv: -len(kv[1]))
            palette = colors_mod.distinctColors(len(order)) if order else []
            for (v, members), c in zip(order, palette):
                cint = colors_mod.to_rgba_int(c)[0]
                for e in members:
                    colors.append([e._id, cint])
            lines += [f"{_safe_repr(v)}: {len(m)}" for v, m in order[:8]]
            if len(order) > 8:
                lines.append(f"… {len(order) - 8} more values")
            lines.append("shown: a colour per value")
        return {"title": f"{expr}: {f.type.lower()} {kind} field, {len(groups)} distinct value{'s' * (len(groups) != 1)}",
                "lines": lines, "items": [], "colors": {kind[0]: colors}}

    def assign(self, varname, kind_ids):
        """Bind a user variable to the given elements (context menu "assign to")."""
        if not varname.isidentifier() or keyword.iskeyword(varname):
            raise GuessError(f"invalid variable name: {varname!r}")
        if self.is_protected(varname):
            raise GuessError(f"'{varname}' is a system name")
        g = self.graph
        items = GSet()
        for kind, ident in kind_ids:
            elem = g.node_by_id(ident) if kind == "n" else g.edge_by_id(ident)
            if elem is not None:
                items.append(elem)
        self.ns[varname] = items[0] if len(items) == 1 else items
        return len(items)


def _short(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return "" if v is None else str(v)


# --------------------------------------------------------------------------
# Structured output
# --------------------------------------------------------------------------

MAX_EXTRA = 20000      # elements beyond MAX_ITEMS still linked (hover, select), just not shown

_PLAIN_REPRS = {list.__repr__, tuple.__repr__, dict.__repr__, set.__repr__, frozenset.__repr__}


def _custom_repr(value):
    """A container subclass that prints a summary of itself (e.g. offspring())."""
    return type(value).__repr__ not in _PLAIN_REPRS and not isinstance(value, GSet)


def _all_items(value, limit=MAX_EXTRA):
    out = []
    for x in _walk_elements(value):
        out.append(["n" if isinstance(x, Node) else "e", x._id])
        if len(out) >= limit:
            break
    return out


def _walk_elements(value, depth=0):
    if isinstance(value, (Node, Edge)):
        yield value
    elif depth < 20 and isinstance(value, dict):
        for k, v in value.items():
            yield from _walk_elements(k, depth + 1)
            yield from _walk_elements(v, depth + 1)
    elif depth < 20 and isinstance(value, (list, tuple, set, frozenset)):
        for x in value:
            yield from _walk_elements(x, depth + 1)


def edge_seg(e, t=None):
    """An edge's output segment. Shown as "a-b" (or "a->b"), it also names its
    ends, so the page links each end to its node and the connector to the edge."""
    t = repr(e) if t is None else t
    seg = {"e": e._id, "t": t}
    if t == repr(e):
        seg["ends"] = [[e._n1._id, e._n1._name], [e._n2._id, e._n2._name]]
    return seg


def segment(value, depth=0):
    if isinstance(value, Node):
        return {"n": value._id, "t": value._name}
    if isinstance(value, Edge):
        return edge_seg(value)
    if isinstance(value, Field):
        return f"{value.name}"
    if isinstance(value, LinkedStr) and value.linked:
        return {"g": ["'", *value.segs, "'"]}
    if isinstance(value, DistinctValues) and value.name and value.source is not None and value:
        groups = value.groups()
        kind = "edges" if value.source and isinstance(value.source[0], Edge) else "nodes"
        parts = ["["]
        for i, v in enumerate(value):
            if i:
                parts.append(", ")
            if i >= MAX_ITEMS:
                parts.append(f"... {len(value) - MAX_ITEMS} more")
                break
            try:
                members = groups.get(v, [])
            except TypeError:
                members = []
            q = f"{value.name} == {v!r}"
            sub_ = {"g": [_safe_repr(v)], "a": q if value.whole else f"{q} (in the set)",
                    "x": [["n" if isinstance(x, Node) else "e", x._id] for x in members[:MAX_EXTRA]]}
            if value.whole:
                sub_["q"] = q
            parts.append(sub_)
        parts.append("]")
        return {"g": parts, "a": f"{len(value)} values of {value.name} ({kind})"}
    linkable = (isinstance(value, (GSet, list, tuple, dict, set, frozenset))
                and depth < 20 and _contains_elements(value))
    if linkable and depth == 0 and isinstance(value, (GSet, list)) and _many_groups(value):
        return _compact_groups(value)
    if linkable and _custom_repr(value):
        # keep the object's own summary, but link every element it holds
        return {"g": [_safe_repr(value)], "x": _all_items(value)}
    if linkable:
        if isinstance(value, dict):
            open_, close, entries = "{", "}", list(value.items())
        else:
            open_, close = (("(", ")") if isinstance(value, tuple)
                            else ("{", "}") if isinstance(value, (set, frozenset)) else ("[", "]"))
            entries = list(value)
        parts = [open_]
        out = {"g": parts}
        for i, x in enumerate(entries):
            if i:
                parts.append(", ")
            if i >= MAX_ITEMS:
                parts.append(f"... {len(entries) - MAX_ITEMS} more")
                rest = entries[MAX_ITEMS:]
                out["x"] = _all_items(rest)
                break
            if isinstance(value, dict):
                parts.extend([segment(x[0], depth + 1), ": ", segment(x[1], depth + 1)])
            else:
                parts.append(segment(x, depth + 1))
        if isinstance(value, tuple) and len(value) == 1:
            parts.append(",")
        parts.append(close)
        ann = getattr(value, "annotation", None) if isinstance(value, GSet) else None
        if ann:
            out["a"] = ann
        return out
    if isinstance(value, GSet):
        out = {"g": ["[]"]}
        if value.annotation:
            out["a"] = value.annotation
        return out
    return _safe_repr(value)


def _many_groups(value):
    """A set of sets too big to print member by member (louvainClusters(), groupBy)."""
    if not value or not all(isinstance(x, (GSet, list, tuple)) and not isinstance(x, (Node, Edge)) for x in value):
        return False
    return len(value) > 8 or sum(len(x) for x in value) > 150


def _compact_groups(value):
    """'45 groups: [32] [28] [20] …', each [n] linked to its members."""
    sizes = [len(x) for x in value]
    ann = getattr(value, "annotation", None) if isinstance(value, GSet) else None
    import re
    parts = [f"{len(value)} group{'s' * (len(value) != 1)} ({sum(sizes)} elements): "]
    for i, grp in enumerate(value):
        if i >= MAX_ITEMS:
            parts.append(f" … {len(value) - MAX_ITEMS} more")
            break
        if i:
            parts.append(" ")
        sub_ann = getattr(grp, "annotation", None) if isinstance(grp, GSet) else None
        m = re.fullmatch(r"\w+ == (.+)", sub_ann or "")
        label = f"{m.group(1).strip(chr(39))}: {len(grp)}" if m else str(len(grp))
        parts.append({"g": [f"[{label}]"], "a": sub_ann or f"group {i}", "x": _all_items(grp)})
    out = {"g": parts}
    if ann:
        out["a"] = ann
    return out


def _safe_repr(value):
    try:
        text = repr(value)
    except Exception as ex:  # noqa: BLE001
        text = f"<unprintable {type(value).__name__}: {ex}>"
    if len(text) > 20000:
        text = text[:20000] + " ..."
    return text


class LinkedStr(str):
    """The value of an f-string in Gython: an ordinary string, which also
    remembers the nodes and edges written into it, so print() can link them."""

    def __new__(cls, text, segs):
        obj = super().__new__(cls, text)
        obj.segs = segs
        obj.linked = any(isinstance(sg, dict) for sg in segs)
        return obj


def fstring(*parts):
    """__gfstr__: build an f-string, keeping the elements in it as segments."""
    texts, segs = [], []
    for p in parts:
        if isinstance(p, str):
            texts.append(p)
            if segs and isinstance(segs[-1], str):
                segs[-1] += p
            else:
                segs.append(p)
            continue
        v, conv, spec = p
        if conv == 114:
            t = repr(v)
        elif conv == 115:
            t = str(v)
        elif conv == 97:
            t = ascii(v)
        else:
            t = None
        if t is not None:
            t = format(t, spec) if spec else t
        else:
            t = format(v, spec) if spec else format(v)
        texts.append(t)
        plain = conv == -1 and not spec
        if plain and isinstance(v, (Node, Edge)):
            segs.append({"n": v._id, "t": t} if isinstance(v, Node) else edge_seg(v, t))
        elif plain and isinstance(v, LinkedStr) and v.linked:
            segs.extend(v.segs)
        elif plain and isinstance(v, (GSet, list, tuple, set, frozenset, dict)) and _contains_elements(v):
            segs.append({"g": [t], "x": _all_items(v), **({"a": v.annotation}
                                                         if isinstance(v, GSet) and v.annotation else {})})
        elif segs and isinstance(segs[-1], str):
            segs[-1] += t
        else:
            segs.append(t)
    return LinkedStr("".join(texts), segs)


def _flatten(seq, depth=0):
    for x in seq:
        if isinstance(x, (GSet, list, tuple, set)) and depth < 5:
            yield from _flatten(x, depth + 1)
        else:
            yield x


def _contains_elements(seq, depth=0):
    if depth > 20:
        return False
    if isinstance(seq, dict):
        seq = [x for kv in seq.items() for x in kv]
    for x in seq:
        if isinstance(x, (Node, Edge)):
            return True
        if isinstance(x, LinkedStr) and x.linked:
            return True
        if isinstance(x, (GSet, list, tuple, set, frozenset, dict)) and _contains_elements(x, depth + 1):
            return True
    return False


def _linkable(a):
    return (isinstance(a, (Node, Edge)) or (isinstance(a, LinkedStr) and a.linked)
            or (isinstance(a, (GSet, list, tuple, set, frozenset, dict)) and _contains_elements(a)))


# --------------------------------------------------------------------------
# Error formatting
# --------------------------------------------------------------------------

def _format_syntax_error(e):
    if isinstance(e, compiler.GythonSyntaxError) and not e.text:
        loc = f" (line {e.lineno})" if e.lineno else ""
        return f"Error: {e.msg}{loc}"
    return "".join(traceback.format_exception_only(type(e), e)).rstrip()


def _format_exception(e):
    if isinstance(e, GuessError):
        return f"Error: {e}"
    if isinstance(e, KeyboardInterrupt):
        return "Interrupted"
    tb = e.__traceback__
    # drop frames that belong to the session machinery itself
    while tb is not None and tb.tb_frame.f_code.co_filename == __file__:
        tb = tb.tb_next
    # and the helpers compiled Gython calls (attribute broadcast, set operators,
    # comparisons): they're how the language works, not where the problem is
    plumbing = (runtime.__file__,)
    frames = [f for f in traceback.extract_tb(tb) if f.filename not in plumbing]
    lines = (["Traceback (most recent call last):\n"] + traceback.format_list(frames) if frames else []) + \
        traceback.format_exception_only(type(e), e)
    return "".join(lines).rstrip()


_ALT_USE = re.compile(r"(?<![\w.])alt\.")


def _has_call(tree):
    import ast
    return any(isinstance(n, ast.Call) for n in ast.walk(tree))


def _first_line(src):
    lines = src.strip().splitlines() or [""]
    return lines[0] + (" ..." if len(lines) > 1 else "")
