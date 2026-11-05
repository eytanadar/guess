"""Collapse groups of nodes into meta-nodes and expand them again (Cytoscape
groups, yEd folding).

    collapse(dept == 'dept3')            one meta-node standing for those nodes
    collapseBy(modularity_class)         a meta-node per community
    expand(group1); expandAll()          bring the members back

A meta-node sits at its members' centre, is sized by how many it holds, takes
their most common colour, and has the field `members` (the count). Edges to the
outside are merged into one edge per neighbour (weight = sum of weights, width
grows with the count). Members and their edges are kept (as with remove) and
come back where they were, shifted if the meta-node was moved. Double-click a
meta-node to expand it. Collapsing and expanding are ordinary undo steps.
"""
import math
from collections import Counter

from .model import INT, GSet, GuessError, Node, elements_of


def install(session):
    g = session.graph
    groups = session.groups = {}   # meta node id -> {"members", "edges", "centre"}

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def alive(x):
        return g._alive(x)

    def unique_name(base):
        name, k = base, 2
        while name in g._nodes:
            name, k = f"{base}_{k}", k + 1
        return name

    @cmd
    def collapse(seq, name=None):
        """collapse(seq) replaces those nodes with one meta-node (see module help);
        collapse(seq, "name") names it. Returns the meta-node."""
        members = [x for x in elements_of(seq) if isinstance(x, Node) and alive(x)]
        members = list(dict.fromkeys(members))
        if not members:
            raise GuessError("collapse needs some nodes")
        inside = set(members)
        cx = sum(_num(n.x) + _num(n.width) / 2 for n in members) / len(members)
        cy = sum(_num(n.y) + _num(n.height) / 2 for n in members) / len(members)
        colour = Counter(n.color for n in members).most_common(1)[0][0]
        base = name or f"group{len(groups) + 1}"
        mname = unique_name(str(base).replace(" ", "_"))
        size = 12 + 6 * math.sqrt(len(members))
        g.addNodeField("members", INT, 0)
        meta = g.addNode(mname, color=colour, style=3, members=len(members))
        meta.width = meta.height = size
        meta.x, meta.y = cx - size / 2, cy - size / 2
        meta.label = f"{base} ({len(members)})"
        meta.labelvisible = True
        # merge edges to the outside: one per (neighbour, direction)
        boundary = {}
        removed_edges, seen = [], set()
        for n in members:
            for e in list(n._inc.values()):
                if e._id in seen:
                    continue
                seen.add(e._id)
                removed_edges.append(e)
                a_in, b_in = e._n1 in inside, e._n2 in inside
                if a_in and b_in:
                    continue
                other = e._n2 if a_in else e._n1
                key = (other, e._directed and a_in, e._directed and not a_in)
                w = boundary.setdefault(key, [0.0, 0])
                w[0] += _num(e.weight, 1.0)
                w[1] += 1
        groups[meta._id] = {"members": members, "edges": removed_edges, "centre": (cx, cy)}
        g.remove(members)
        for (other, out_dir, in_dir), (weight, count) in boundary.items():
            if out_dir:
                e = g.addEdge(meta, other, True)
            elif in_dir:
                e = g.addEdge(other, meta, True)
            else:
                e = g.addEdge(meta, other, False)
            e.weight = weight
            e.width = min(1.5 + 1.5 * math.log1p(count), 10)
            if count > 1:
                e.label = str(count)
        return meta

    @cmd
    def collapseBy(field, minimum=2):
        """collapseBy(field) collapses each group of nodes sharing a value of field
        (with at least `minimum` members) into a meta-node named after the value."""
        from .model import Field, NODE, group_by
        if not isinstance(field, Field) or field.kind != NODE:
            raise GuessError("collapseBy needs a node field, e.g. collapseBy(dept)")
        made = GSet(annotation=f"groups by {field.name}")
        for grp in group_by(field.elements(), field):
            live = [n for n in grp if alive(n)]
            if len(live) >= int(minimum):
                made.append(collapse(live, f"{field.name}_{field.get(live[0])}"))
        return made

    @cmd
    def expand(meta):
        """expand(metaNode) brings back the nodes a meta-node stands for (also:
        double-click it). Returns them."""
        if isinstance(meta, str):
            meta = g._nodes.get(meta)
        info = groups.get(getattr(meta, "_id", None))
        if info is None or not isinstance(meta, Node) or not alive(meta):
            raise GuessError(f"{getattr(meta, '_name', meta)!r} is not a collapsed group")
        dx = _num(meta.x) + _num(meta.width) / 2 - info["centre"][0]
        dy = _num(meta.y) + _num(meta.height) / 2 - info["centre"][1]
        g.remove(meta, keep=False)
        restored = g.add(info["members"])
        for n in info["members"]:
            if dx or dy:
                n.x, n.y = _num(n.x) + dx, _num(n.y) + dy
        reconnect()
        return GSet([x for x in restored if isinstance(x, Node)], f"members of {meta._name}")

    def reconnect():
        """Restore stored edges whose endpoints are visible again; an endpoint
        still inside a collapsed group is represented by that group's meta-node."""
        owner_of = {}
        for mid, info in groups.items():
            for n in info["members"]:
                owner_of[n._id] = mid

        def owner(n, depth=0):
            while not alive(n) and n._id in owner_of and depth < 50:
                n = g._node_ids.get(owner_of[n._id]) or _dead(owner_of[n._id])
                depth += 1
            return n if alive(n) else None

        def _dead(mid):
            # a meta-node that was itself collapsed into another group
            for info in groups.values():
                for m in info["members"]:
                    if m._id == mid:
                        return m
            return None

        for info in groups.values():
            for e in info["edges"]:
                if alive(e):
                    continue
                a, b = owner(e._n1), owner(e._n2)
                if a is None or b is None:
                    continue
                if a is e._n1 and b is e._n2:      # both ends visible (self-loops too)
                    g.add([e])
                elif a is b:
                    continue
                elif not any(x.opposite(a) is b for x in a._inc.values()):
                    m = g.addEdge(a, b, False)
                    m.weight = _num(e.weight, 1.0)

    @cmd
    def expandAll():
        """Expand every collapsed group (repeatedly, for nested groups)."""
        while True:
            metas = [g._node_ids[i] for i in groups if i in g._node_ids and alive(g._node_ids[i])]
            if not metas:
                return
            for m in metas:
                expand(m)

    @cmd
    def isGroup(node):
        """True if node is a collapsed group (meta-node)."""
        return isinstance(node, Node) and node._id in groups and alive(node)


def _num(v, d=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return d
    return f if math.isfinite(f) else d
