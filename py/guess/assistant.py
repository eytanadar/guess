"""connectAssistant(): let an AI assistant (Claude Desktop, Claude Code or any
MCP client) work in this session through the bridge in mcp/guess-mcp.mjs.

The assistant's commands run as ordinary console cells marked "assistant":
the user sees them, and undo, history and logs include them.
"""
from .model import GuessError


def summary(session):
    """A plain-text description of the current graph for an assistant: size,
    direction, components, degrees and the fields with a few example values.
    Reads only; computes nothing that isn't cheap."""
    g = session.graph
    nodes, edges = g._nodes_list(), g._edges_list()
    n, m = len(nodes), len(edges)
    directed = sum(1 for e in edges if e._directed)
    lines = [f"graph: {n} nodes, {m} edges"
             + (f" ({directed} directed)" if directed else " (undirected)")]
    if n > 1:
        lines.append(f"density: {m / (n * (n - 1) / 2):.4f}")
    if n:
        degs = sorted(len(x._inc) for x in nodes)
        lines.append(f"degree: min {degs[0]}, median {degs[len(degs) // 2]}, max {degs[-1]}, "
                     f"mean {sum(degs) / n:.2f}; {sum(1 for d in degs if d == 0)} isolated")
        # components by union-find (cheap)
        parent = {x._id: x._id for x in nodes}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for e in edges:
            a, b = find(e._n1._id), find(e._n2._id)
            if a != b:
                parent[a] = b
        sizes = {}
        for x in nodes:
            r = find(x._id)
            sizes[r] = sizes.get(r, 0) + 1
        big = sorted(sizes.values(), reverse=True)
        lines.append(f"components: {len(big)} (largest {big[0]} nodes)")
    plumbing = {"x", "y", "visible", "strokecolor", "labelcolor", "fixed", "style", "width", "height", "image",
                "labelvisible", "labelsize", "labelpos", "node1", "node2", "source", "destination", "directed"}
    for kind, schema, elems in (("node", g.node_schema, nodes), ("edge", g.edge_schema, edges)):
        parts = []
        for name, f in schema.items():
            if name in plumbing:
                continue
            vals = []
            for x in elems[:200]:
                try:
                    v = f.get(x)
                except Exception:   # noqa: BLE001
                    continue
                if v is not None and v not in vals:
                    vals.append(v)
                if len(vals) >= 3:
                    break
            ex = ", ".join(repr(v) for v in vals)
            parts.append(f"{name} ({f.type.lower()}{'; e.g. ' + ex if ex else ''})")
        lines.append(f"{kind} fields: " + "; ".join(parts))
    computed = sorted({name for (k, name) in g.lazy_fields if k == "node"} - set(g.node_schema))
    if computed:
        lines.append("computed node fields (calculated when first used): " + ", ".join(computed))
    names = [x._name for x in nodes[:8]]
    if names:
        lines.append("example node names (each is a variable): " + ", ".join(names))
    others = [x for x in getattr(session, "graphs", {}) if x != getattr(g, "name", None)] \
        if isinstance(getattr(session, "graphs", None), dict) else []
    if others:
        lines.append("other graphs in this session: " + ", ".join(map(str, others)))
    return "\n".join(lines)


def install(session):
    def connectAssistant(port=7777):
        """connectAssistant() connects this page to an AI assistant through the
        GUESS MCP bridge (mcp/guess-mcp.mjs, which the assistant starts; see
        the manual). The assistant can then run Gython here, read a summary
        of the graph and the command help, and see the view. Everything it
        runs appears in the console marked "assistant" and can be undone.
        disconnectAssistant() ends it. port= must match GUESS_MCP_PORT."""
        try:
            p = int(port)
        except (TypeError, ValueError):
            raise GuessError("connectAssistant needs a port number, e.g. connectAssistant(7777)") from None
        if not 1 <= p <= 65535:
            raise GuessError("the port must be between 1 and 65535")
        session.emit({"type": "assistant", "op": "connect", "url": f"ws://127.0.0.1:{p}"})

    def disconnectAssistant():
        """disconnectAssistant() disconnects the AI assistant (see connectAssistant)."""
        session.emit({"type": "assistant", "op": "disconnect"})

    for fn in (connectAssistant, disconnectAssistant):
        session.register_command(fn.__name__, fn)


__all__ = ["install", "summary"]
