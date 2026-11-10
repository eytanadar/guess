"""Several graphs in one session (Cytoscape's network collection).

    subgraph(sel)            a new graph from those nodes and the edges among them
    newGraph("scratch")      an empty graph
    use("main")              switch graphs (the page shows tabs when there are several)
    graphNames(); closeGraph("scratch"); renameGraph("other name")

Each graph keeps its fields, states, hulls, legends, groups and display
settings. Switching saves the current graph and loads the other; Python
variables stay (names of nodes are rebound), and undo history starts afresh.
"""
from . import persist
from .model import Edge, GuessError, Node, elements_of


def install(session):
    ws = session.workspaces = {"current": "main", "stored": {}}

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def announce():
        names = [ws["current"]] + [n for n in ws["stored"] if n != ws["current"]]
        order = session.__dict__.setdefault("_graph_order", ["main"])
        for n in names:
            if n not in order:
                order.append(n)
        order[:] = [n for n in order if n in names]
        session.emit({"type": "graphs", "names": list(order), "current": ws["current"]})

    def switch_to(name, data):
        ws["stored"][ws["current"]] = persist.serialize(session, workspaces=False)
        ws["current"] = name
        ws["stored"].pop(name, None)
        persist.load(session, data)
        session.undo_stack.clear()
        session.redo_stack.clear()
        session._history_op = True     # switching isn't an undo step
        announce()

    def fresh_name(base):
        taken = set(ws["stored"]) | {ws["current"]}
        name, k = base, 2
        while name in taken:
            name, k = f"{base} {k}", k + 1
        return name

    @cmd
    def subgraph(seq=None, name=None):
        """subgraph(seq) makes a new graph from those nodes (edges select their
        endpoints) and the edges among them, keeping fields, positions and look,
        and switches to it; subgraph(seq, "name") names it. Use use(name) to go back."""
        items = list(elements_of(seq)) if seq is not None else list(session.ns.get("sel") or [])
        ids = set()
        for x in items:
            if isinstance(x, Node):
                ids.add(x._id)
            elif isinstance(x, Edge):
                ids.update((x._n1._id, x._n2._id))
        if not ids:
            raise GuessError("subgraph needs some nodes (or select some first)")
        data = persist.serialize(session, subset=ids)
        switch_to(fresh_name(str(name) if name else f"{ws['current']} part"), data)
        print(f"now in graph '{ws['current']}' ({len(ids)} nodes); use({persist_lit(ws['stored'] and next(iter(ws['stored'])) or 'main')}) to go back")

    @cmd
    def project(kindField, keep, method="count", name=None):
        """project(kind, "woman") turns a two-mode network (people and the
        events, groups or papers they belong to) into a one-mode network of
        just the nodes whose `kind` is "woman": two are linked when they share
        a neighbour of the other kind. It opens as a new graph (the two-mode
        one stays; use() goes back), keeping fields and positions. Each edge
        gets `shared` (how many neighbours in common) and `weight`, by method:
          "count"    the number shared (default)
          "jaccard"  shared / neighbours of either (0..1; removes the size
                     effect of very active nodes)
          "newman"   each shared neighbour adds 1/(its degree - 1), so a
                     small event counts more than a crowded one
        Each kept node also gets `affiliations`: its number of other-kind
        neighbours. E.g. project(kind, "event") gives the event network."""
        from .model import Field
        gr = session.graph
        f = kindField if isinstance(kindField, Field) else gr.node_schema.get(str(kindField))
        if f is None or f.kind != "node":
            raise GuessError("project needs a node field that says which kind each node is")
        if method not in ("count", "jaccard", "newman"):
            raise GuessError('method should be "count", "jaccard" or "newman"')
        kept = [n for n in gr._nodes_list() if f.get(n) == keep]
        if not kept:
            raise GuessError(f"no nodes have {f.name} == {keep!r} (values: {', '.join(map(repr, f.distinct))})")
        kept_ids = {n._id for n in kept}
        nbrs = {}        # kept node id -> set of other-kind neighbour ids
        pairs = {}       # (id, id) -> [shared count, newman weight]
        for o in gr._nodes_list():
            if o._id in kept_ids:
                continue
            ks = sorted({x._id for e in o._inc.values() for x in (e._n1, e._n2)
                         if x._id in kept_ids})
            for k in ks:
                nbrs.setdefault(k, set()).add(o._id)
            if len(ks) < 2:
                continue
            w = 1.0 / (len(ks) - 1)
            for i, a in enumerate(ks):
                for b in ks[i + 1:]:
                    p = pairs.setdefault((a, b), [0, 0.0])
                    p[0] += 1
                    p[1] += w
        names = {n._id: n._name for n in kept}
        data = persist.serialize(session, subset=kept_ids)
        data["edges"] = []
        came_from = ws["current"]
        switch_to(fresh_name(str(name) if name else f"{keep} projection"), data)
        g = session.graph
        g.addEdgeField("shared", "INTEGER", 0)
        if "weight" not in g.edge_schema:
            g.addEdgeField("weight", "DOUBLE", 1.0)
        g.addNodeField("affiliations", "INTEGER", 0)
        for nid, nm in names.items():
            g.getNodeByName(nm).affiliations = len(nbrs.get(nid, ()))
        for (a, b), (count, newman) in pairs.items():
            if method == "count":
                w = float(count)
            elif method == "newman":
                w = newman
            else:
                w = count / len(nbrs[a] | nbrs[b])
            g.addUndirectedEdge(names[a], names[b], shared=count, weight=w)
        session.scene()
        print(f"now in graph '{ws['current']}': {len(kept)} nodes, {len(pairs)} edges "
              f"(weight = {method}); use({persist_lit(came_from)}) to go back")

    @cmd
    def newGraph(name="untitled"):
        """newGraph(name) starts an empty graph and switches to it."""
        empty = {"format": "guess-session", "version": persist.VERSION, "nodes": [], "edges": []}
        switch_to(fresh_name(str(name)), empty)

    @cmd
    def use(name):
        """use(name) switches to another graph of this session (see graphNames())."""
        name = str(name)
        if name == ws["current"]:
            return
        if name not in ws["stored"]:
            raise GuessError(f"no graph {name!r} (graphs: {', '.join(map(repr, graphNames()))})")
        switch_to(name, ws["stored"][name])

    @cmd
    def graphNames():
        """The graphs in this session; the current one first."""
        return [ws["current"]] + list(ws["stored"])

    @cmd
    def closeGraph(name):
        """closeGraph(name) discards a graph that isn't the current one."""
        name = str(name)
        if name == ws["current"]:
            raise GuessError("can't close the current graph; use() another one first")
        if ws["stored"].pop(name, None) is None:
            raise GuessError(f"no graph {name!r}")
        announce()

    @cmd
    def renameGraph(name):
        """renameGraph(name) renames the current graph."""
        name = str(name)
        if name in ws["stored"]:
            raise GuessError(f"there is already a graph {name!r}")
        order = session.__dict__.setdefault("_graph_order", ["main"])
        order[:] = [name if n == ws["current"] else n for n in order]
        ws["current"] = name
        announce()


def persist_lit(s):
    return repr(str(s))
