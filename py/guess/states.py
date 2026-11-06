"""Saved graph states: ss / ls / morph, and state-indexed access.

    ss(1999)                   save the current graph as state 1999
    ls(1999)                   restore it (membership and every field value)
    morph(2000, 2000)          animate to state 2000 over 2000 ms
    bob[1999].jobfunc          a field value in a saved state
    freq[2000] > freq[1999]    edges whose freq grew between the states
"""
from .model import Edge, Field, GSet, GuessError, Node


class Snapshot:
    def __init__(self, graph):
        self.nodes = {n: dict(n._vals) for n in graph._nodes_list()}
        self.edges = {e: dict(e._vals) for e in graph._edges_list()}

    def values_for(self, elem):
        table = self.nodes if isinstance(elem, Node) else self.edges
        return table.get(elem)


class StateField(Field):
    """``freq[2000]``: a field read from a saved state."""

    def __init__(self, field, state, snap):
        super().__init__(field.graph, f"{field.name}[{state!r}]", field.kind, field.type,
                         field.default, readonly=True)
        self._base = field
        self._snap = snap

    def get(self, elem):
        if self._base.compute is not None:
            return self._base.compute(elem)
        vals = self._snap.values_for(elem)
        if vals is None:
            return None
        return vals.get(self._base.name, self._base.default)

    def elements(self):
        return list(self._snap.nodes if self.kind == "node" else self._snap.edges)


class ElementState:
    """``bob[1999]``: read-only view of an element's fields in a saved state."""

    def __init__(self, elem, state, snap):
        object.__setattr__(self, "_elem", elem)
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_vals", snap.values_for(elem))

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        elem = self._elem
        schema = elem._g.node_schema if isinstance(elem, Node) else elem._g.edge_schema
        f = schema.get(name)
        if f is None:
            raise AttributeError(f"no field '{name}'")
        if f.compute is not None:
            return f.compute(elem)
        if self._vals is None:
            return None
        return self._vals.get(name, f.default)

    def __setattr__(self, name, value):
        raise GuessError("saved states are read-only; ls() the state to edit it")

    def __repr__(self):
        return f"{self._elem!r}[{self._state!r}]"


def install(session):
    g = session.graph
    states = {}
    g.states = states
    timing = {"nodeAppearAfter": 0.5, "nodeDisappearBy": 0.5,
              "edgeAppearAfter": 0.5, "edgeDisappearBy": 0.5}
    session.morph_timing = timing

    def lookup(state):
        if state == "_deleted":
            # weight['_deleted'] > 5: values of removed elements (manual §8)
            snap = Snapshot.__new__(Snapshot)
            snap.nodes = {x: dict(x._vals) for x in g._deleted.values() if isinstance(x, Node)}
            snap.edges = {x: dict(x._vals) for x in g._deleted.values() if not isinstance(x, Node)}
            return snap
        snap = states.get(state)
        if snap is None:
            raise GuessError(f"no saved state {state!r} (saved: {', '.join(map(repr, states)) or 'none'})")
        return snap

    g.state_lookup = lookup

    def ss(state):
        """Save the current graph (membership and all field values) as a named state."""
        states[state] = Snapshot(g)

    def ls(state):
        """Load a saved state: restores which nodes/edges exist and all their values."""
        _restore(lookup(state))

    def _restore(snap):
        g.remove([e for e in g._edges_list() if e not in snap.edges])
        g.remove([n for n in g._nodes_list() if n not in snap.nodes])
        g.add([n for n in snap.nodes if g._nodes.get(n._name) is not n])
        g.add([e for e in snap.edges if e._id not in g._edges])
        for n, vals in snap.nodes.items():
            if g._nodes.get(n._name) is n:
                n._vals.clear()
                n._vals.update(vals)
                g._mark(n)
        for e, vals in snap.edges.items():
            if e._id in g._edges:
                e._vals.clear()
                e._vals.update(vals)
                g._mark(e)

    def morph(state, duration=1000):
        """Animate from the current display to a saved state over `duration` ms."""
        snap = lookup(state)
        session.flush()
        _restore(snap)
        session.pending_morph = dict(timing, duration=float(duration))

    def getStates():
        """Names of the saved states."""
        return list(states)

    def make_timing(key):
        def setter(v):
            timing[key] = max(0.0, min(1.0, float(v)))
        def getter():
            return timing[key]
        cap = key[0].upper() + key[1:]
        setter.__name__, getter.__name__ = f"set{cap}", f"get{cap}"
        setter.__doc__ = f"Fraction (0..1) of a morph by which {key} takes effect."
        getter.__doc__ = f"The current {key} fraction (see set{cap})."
        return setter, getter

    for fn in (ss, ls, morph, getStates):
        session.register_command(fn.__name__, fn)
    for key in timing:
        for fn in make_timing(key):
            session.register_command(fn.__name__, fn)


def field_in_state(field, state):
    snap = field.graph.state_lookup(state)
    return StateField(field, state, snap)


def element_in_state(elem, state):
    snap = elem._g.state_lookup(state)
    return ElementState(elem, state, snap)


__all__ = ["install", "field_in_state", "element_in_state", "GSet"]
