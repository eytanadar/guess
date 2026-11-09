"""networkx in both directions, and classic sample graphs.

    G = toNetworkX()                         the graph with its fields (node key = name)
    setField(nx.katz_centrality(G), "katz")  any networkx result becomes a field
    fromNetworkX(G)                          a networkx graph into GUESS (fields, positions)
    makeSample("karate")                     karate, lesmis, florentine, davis, petersen, ...

networkx is already loaded in the page, so `import networkx as nx` works in
the console; these commands carry fields, positions and direction across.
"""
import math
import random

from .algorithms import _nx
from .model import BOOL, DOUBLE, EDGE, INT, STRING, Edge, GuessError, Node, coerce

# fields that describe the structure itself, not attributes to copy
_SKIP_NODE = {"name", "indegree", "outdegree", "totaldegree"}
_SKIP_EDGE = {"node1", "node2", "source", "destination", "directed"}


def _copyable(schema, skip):
    return [f for f in schema.values() if f.name not in skip and f.compute is None]


def graph_to_nx(graph, directed=None, visible_only=False):
    """The GUESS graph as a networkx graph whose node keys are node names.

    Every stored field (user fields, look, and computed fields already in use)
    becomes an attribute; positions are also given as ``pos`` = (x, y). A
    mixed graph becomes directed, with undirected edges in both directions.
    Parallel edges give a MultiGraph / MultiDiGraph keyed by GUESS edge id."""
    nx = _nx()
    nodes = [n for n in graph._nodes_list() if not visible_only or n.visible]
    keep = {n._id for n in nodes}
    edges = [e for e in graph._edges_list()
             if e._n1._id in keep and e._n2._id in keep and (not visible_only or e.visible)]
    if directed is None:
        directed = any(e._directed for e in edges)
    pairs = set()
    multi = False
    for e in edges:
        k = (e._n1._id, e._n2._id) if directed else tuple(sorted((e._n1._id, e._n2._id)))
        if k in pairs:
            multi = True
            break
        pairs.add(k)
    cls = {(False, False): nx.Graph, (True, False): nx.DiGraph,
           (False, True): nx.MultiGraph, (True, True): nx.MultiDiGraph}[(bool(directed), multi)]
    G = cls()
    nf = _copyable(graph.node_schema, _SKIP_NODE)
    ef = _copyable(graph.edge_schema, _SKIP_EDGE)
    for n in nodes:
        attrs = {f.name: f.get(n) for f in nf if f.get(n) is not None}
        attrs["pos"] = (n.x, n.y)
        G.add_node(n._name, **attrs)
    mixed = False
    for e in edges:
        attrs = {f.name: f.get(e) for f in ef if f.get(e) is not None}
        a, b = e._n1._name, e._n2._name
        if multi:
            G.add_edge(a, b, key=e._id, **attrs)
        else:
            G.add_edge(a, b, **attrs)
        if directed and not e._directed:
            mixed = True
            if multi:
                G.add_edge(b, a, key=-e._id - 1, **attrs)
            else:
                G.add_edge(b, a, **attrs)
    if mixed:
        G.graph["mixed"] = True
    return G


def _infer_type(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    if all(isinstance(v, bool) for v in vals):
        return BOOL
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return INT
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return DOUBLE
    if all(isinstance(v, (int, float, str, bool)) for v in vals):
        return STRING
    return None          # lists, dicts, tuples: not a field


def _field_name(key):
    import re
    name = re.sub(r"\W", "_", str(key))
    return name if name and not name[0].isdigit() else "_" + name


def _node_name(key, used):
    """A GUESS name for a networkx node key: strings as they are, numbers as
    n<k> (so they can be typed in the console), anything else as its str()."""
    if isinstance(key, str) and key:
        name = key
    elif isinstance(key, (int, float)) and not isinstance(key, bool):
        name = f"n{key:g}" if isinstance(key, float) else f"n{key}"
    else:
        name = str(key)
    base, k = name, 2
    while name in used:
        name, k = f"{base}_{k}", k + 1
    used.add(name)
    return name


def nx_into(graph, G, *, layout=True):
    """Replace the GUESS graph's contents with networkx graph G. Returns
    (nodes, edges)."""
    graph.clear()
    directed = G.is_directed()
    # fields from the attributes (types inferred from the values)
    for recs, schema, add, skip in (
            ([d for _n, d in G.nodes(data=True)], graph.node_schema, graph.addNodeField, _SKIP_NODE | {"pos"}),
            ([d for *_e, d in G.edges(data=True)], graph.edge_schema, graph.addEdgeField, _SKIP_EDGE)):
        keys = {}
        for d in recs:
            for k, v in d.items():
                keys.setdefault(k, []).append(v)
        for k, vals in keys.items():
            name = _field_name(k)
            if name in skip or name in schema:
                continue
            t = _infer_type(vals)
            if t is not None:
                add(name, t, coerce(t, None))
    keys_kept = not all(isinstance(k, str) for k in G.nodes)
    if keys_kept and "nxkey" not in graph.node_schema:
        graph.addNodeField("nxkey", STRING, None)
    used, names = set(), {}
    have_pos = True
    for key, d in G.nodes(data=True):
        name = _node_name(key, used)
        names[key] = name
        n = graph.addNode(name)
        if keys_kept:
            n.nxkey = str(key)
        pos = d.get("pos")
        if pos is None and isinstance(d.get("x"), (int, float)) and isinstance(d.get("y"), (int, float)):
            pos = (d["x"], d["y"])
        if pos is not None and len(pos) >= 2:
            n.x, n.y = float(pos[0]), float(pos[1])
        else:
            have_pos = False
        _set_attrs(graph.node_schema, n, d, _SKIP_NODE | {"pos"})
        if not n.label:
            n.label = name
    edges = 0
    for *ends, d in G.edges(data=True):
        a, b = ends[0], ends[1]
        e = graph.addEdge(names[a], names[b], directed)
        _set_attrs(graph.edge_schema, e, d, _SKIP_EDGE)
        edges += 1
    if not have_pos and layout and len(G):
        _spread(graph, G, names)
    return len(G), edges


def _spread(graph, G, names):
    """Positions for a graph that brought none: networkx's spring layout
    (seeded, so the same graph always looks the same)."""
    nx = _nx()
    try:
        pos = nx.spring_layout(G, seed=1)
    except Exception:  # noqa: BLE001 - e.g. scipy missing for large graphs
        pos = {k: (random.random(), random.random()) for k in G}
    for key, (x, y) in pos.items():
        n = graph._nodes[names[key]]
        n.x, n.y = 500 + 450 * float(x), 500 + 450 * float(y)


def _set_attrs(schema, elem, d, skip):
    for k, v in d.items():
        name = _field_name(k)
        if name in skip:
            continue
        f = schema.get(name)
        if f is None or f.readonly or f.compute is not None:
            continue
        try:
            f.set(elem, v)
        except (GuessError, TypeError, ValueError):
            pass


# sample graphs: name -> (builder, description)
def _samples():
    return {
        "karate": (lambda nx: nx.karate_club_graph(),
                   "Zachary's karate club: 34 members, `club` = the side each joined after the split"),
        "lesmis": (lambda nx: nx.les_miserables_graph(),
                   "Les Misérables co-appearances: 77 characters, `weight` = scenes together"),
        "florentine": (lambda nx: nx.florentine_families_graph(),
                       "Florentine families: marriage ties between 15 Renaissance families"),
        "davis": (lambda nx: nx.davis_southern_women_graph(),
                  "Davis' Southern Women: 18 women x 14 events (two-mode; `bipartite` = 0 women, 1 events)"),
        "petersen": (lambda nx: nx.petersen_graph(), "the Petersen graph"),
        "kite": (lambda nx: nx.krackhardt_kite_graph(), "Krackhardt's kite (centrality teaching example)"),
        "tutte": (lambda nx: nx.tutte_graph(), "the Tutte graph"),
        "dodecahedron": (lambda nx: nx.dodecahedral_graph(), "the dodecahedron"),
        "caveman": (lambda nx: nx.connected_caveman_graph(6, 6), "6 connected cliques of 6 (clear communities)"),
    }


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    @cmd
    def toNetworkX(directed=None, visibleOnly=False):
        """toNetworkX() returns the graph as a networkx graph, to use any networkx
        algorithm: node keys are node names, and every field (dept, color, x, y,
        pagerank once used, ...) is an attribute; positions are also `pos`.
        directed=True/False forces the type (a mixed graph becomes directed, with
        undirected edges both ways); visibleOnly=True leaves out hidden elements.
        Bring results back with setField:
            import networkx as nx
            setField(nx.katz_centrality(toNetworkX()), "katz")"""
        return graph_to_nx(g(), directed, visibleOnly)

    @cmd
    def fromNetworkX(G, name=None):
        """fromNetworkX(G) replaces the graph with networkx graph G: its node and
        edge attributes become fields (types from the values), `pos` or x/y give
        positions (otherwise a spring layout), and direction is kept. String keys
        become node names; other keys become n0, n1, ... with the original in
        `nxkey`. fromNetworkX(G, "name") opens it in a new tab instead and
        switches to it (use("main") goes back)."""
        if not hasattr(G, "nodes") or not hasattr(G, "is_directed"):
            raise GuessError("fromNetworkX needs a networkx graph")
        if name is not None:
            session.ns["newGraph"](str(name))
        nn, ne = nx_into(g(), G)
        session.scene()
        print(f"loaded {nn} nodes, {ne} edges from networkx")

    @cmd
    def setField(values, name, kind=None):
        """setField(values, "name") stores a result as a field: a dict from nodes
        (or node names) to values, as networkx centralities return; a dict from
        node pairs (a, b) to values gives an edge field; a list of node sets (as
        community algorithms return) gives each node its set's index, largest
        first. The type is taken from the values. Returns the field.
            setField(nx.core_number(toNetworkX()), "core")
            setField(nx.community.greedy_modularity_communities(toNetworkX()), "greedy")"""
        gr = g()
        name = str(name)
        if not name.isidentifier():
            raise GuessError(f"invalid field name: {name!r}")
        nodes_by_name = gr._nodes

        def node_of(k):
            if isinstance(k, Node):
                return k
            n = nodes_by_name.get(k if isinstance(k, str) else str(k))
            if n is None and not isinstance(k, str):
                n = nodes_by_name.get(_node_name(k, set()))
            return n

        if isinstance(values, dict):
            items = list(values.items())
        else:
            # communities: an iterable of node collections
            groups = [list(c) for c in values]
            groups.sort(key=len, reverse=True)
            items = [(m, i) for i, c in enumerate(groups) for m in c]
        if not items:
            raise GuessError("setField: no values")
        edge_keyed = kind == EDGE or kind == "edge" or (
            kind is None and all(isinstance(k, (tuple, Edge)) for k, _v in items))
        resolved = []
        if edge_keyed:
            index = {}
            for e in gr._edges_list():
                index.setdefault((e._n1._name, e._n2._name), []).append(e)
                if not e._directed:
                    index.setdefault((e._n2._name, e._n1._name), []).append(e)
            for k, v in items:
                if isinstance(k, Edge):
                    resolved.append((k, v))
                    continue
                a, b = (x._name if isinstance(x, Node) else str(x) for x in k[:2])
                for e in index.get((a, b), []):
                    resolved.append((e, v))
        else:
            for k, v in items:
                n = node_of(k)
                if n is not None:
                    resolved.append((n, v))
        if not resolved:
            raise GuessError("setField: none of the keys match nodes or edges of this graph")
        vals = [v.item() if hasattr(v, "item") else v for _x, v in resolved]
        ftype = _infer_type(vals)
        if ftype is None:
            raise GuessError("setField: values should be numbers, strings or booleans")
        schema = gr.edge_schema if edge_keyed else gr.node_schema
        f = schema.get(name)
        if f is not None and (f.readonly or f.compute is not None):
            raise GuessError(f"'{name}' is a built-in field and can't be set")
        if f is None:
            add = gr.addEdgeField if edge_keyed else gr.addNodeField
            f = add(name, ftype, None)
        for (elem, _v), v in zip(resolved, vals):
            if isinstance(v, float) and math.isnan(v):
                v = None
            f.set(elem, v)
        return f

    @cmd
    def makeSample(name=None):
        """makeSample("karate") loads a classic network: karate, lesmis,
        florentine, davis, petersen, kite, tutte, dodecahedron, caveman.
        makeSample() lists them. They come with their attributes (karate's
        `club`, lesmis' `weight`, davis' `bipartite`) and a spring layout."""
        samples = _samples()
        if name is None:
            for k, (_b, desc) in samples.items():
                print(f"{k:13} {desc}")
            return None
        key = str(name).lower()
        if key not in samples:
            raise GuessError(f"no sample {name!r} (samples: {', '.join(samples)})")
        G = samples[key][0](_nx())
        nn, ne = nx_into(g(), G)
        session.scene()
        print(f"loaded sample '{key}': {nn} nodes, {ne} edges")

