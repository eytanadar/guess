"""More analysis: spreading, motifs, a report, the rich club, routing,
and node embeddings.

    spread([v1], model="SIR")      simulate an epidemic or a cascade
    findMotifs("fan")              NodeXL-style fans, connectors and cliques
    collapseMotifs("fan")          ... each into one meta-node
    report("report.html")          a one-page summary of the graph
    richClub()                     do the hubs link to each other?
    minCostFlow(a, b, 10)          the cheapest way to send a flow
    travelingSalesman(stops)       a short round trip through some nodes
    embed(dims=8)                  node2vec-style coordinates for machine learning
"""
import html as _html
import os
import random

import numpy as np

from .model import DOUBLE, INT, NODE, STRING, GSet, GuessError, Node, elements_of


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    def nodes_of(seq, what):
        out = [x for x in elements_of(seq) if isinstance(x, Node)] if seq is not None else []
        if seq is not None and not out:
            raise GuessError(f"{what} needs nodes")
        return out

    def neighbours(gr, follow_direction=True):
        """{node: [nodes it reaches in one step]}"""
        out = {n: [] for n in gr._nodes_list()}
        for e in gr._edges_list():
            if e._n1 is e._n2:
                continue
            out[e._n1].append(e._n2)
            if not (e._directed and follow_direction):
                out[e._n2].append(e._n1)
        return out

    # ---- spreading -------------------------------------------------------------
    @cmd
    def spread(seeds, model="SIR", beta=0.3, gamma=0.1, threshold=0.5, steps=100, seed=0, show=True,
               immune=None, weight=None, waning=0.05, sigma=0.5, duration=None):
        """spread([v1, v2], model="SIR") simulates something spreading from
        the seed nodes, one step at a time:
          "SI"         each step, every infected node infects each susceptible
                       neighbour with probability beta
          "SIR"        the same, and each infected node recovers (and can't be
                       infected again) with probability gamma
          "SIS"        the same, but recovered nodes can be infected again (no
                       immunity): the infection can settle at an endemic level
          "SIRS"       SIR, but immunity wanes: each recovered node becomes
                       susceptible again with probability `waning` per step
          "SEIR"       SIR with a latent stage: newly infected nodes are Exposed
                       and become infectious with probability `sigma` per step
          "cascade"    independent cascade: a newly active node gets one chance
                       (probability beta) to activate each neighbour
          "threshold"  a node becomes active when at least `threshold` of its
                       neighbours are (complex contagion: ideas, adoption)
        duration=k makes every infection last exactly k steps (instead of
        recovering with probability gamma); SIR is then exactly bond percolation
        with transmissibility T = 1 - (1 - beta)**k.
        Directed edges are followed in their direction. immune=nodes can't be
        infected (vaccinated, say: state V). weight=field makes long contacts
        riskier: beta is then the chance per unit of weight, so an edge of
        weight w transmits with chance 1 - (1 - beta)**w per step. Stores
        `infected_at` (the step a node was reached; -1 = never), `state`
        (S, E, I, R or V at the end) and `infected_steps` (steps spent
        infected, e.g. for SIS prevalence by degree), plots how many are in each state at each
        step, and returns those counts. Replay it with showTime(t,
        infected_at); outbreaks() repeats it many times."""
        from . import epidemic
        gr = g()
        start = nodes_of(seeds, "spread")
        m = str(model).lower()
        if m not in epidemic.MODELS:
            raise GuessError(f"model should be {epidemic.MODEL_NAMES}")
        rng = random.Random(seed)
        if isinstance(weight, str):
            weight = gr.edge_schema.get(weight) or session.ns.get(weight)
        out, inc = epidemic.contacts(gr, beta, weight)
        imm = nodes_of(immune, "immune") if immune is not None else []
        state, when, counts = epidemic.simulate(gr._nodes_list(), out, inc, start, m, gamma, threshold,
                                                steps, rng, imm, waning=waning, sigma=sigma, duration=duration)
        f_at = gr.addNodeField("infected_at", INT, -1)
        f_st = gr.addNodeField("state", STRING, None)
        f_steps = gr.addNodeField("infected_steps", INT, 0)
        for n in gr._nodes_list():
            f_at.set(n, when[n])
            f_st.set(n, state[n])
            f_steps.set(n, counts.infected_steps.get(n, 0))
        reached = sum(1 for v in when.values() if v >= 0)
        if show:
            print(f"{model}: reached {reached} of {len(state)} nodes ({reached / max(1, len(state)):.0%}) "
                  f"in {counts[-1][0]} steps")
            series = [{"name": "susceptible", "color": 0x2c7bb6, "points": [[t, s] for t, s, _i, _r in counts]},
                      {"name": "infected", "color": 0xd7191c, "points": [[t, i] for t, _s, i, _r in counts]}]
            if m == "seir":
                series.append({"name": "exposed", "color": 0xfdae61,
                               "points": [[t, e] for (t, *_x), e in zip(counts, counts.exposed)]})
            if m in ("sir", "sirs", "seir"):
                series.append({"name": "recovered", "color": 0x1a9641, "points": [[t, r] for t, _s, _i, r in counts]})
            session.chart_out({"type": "chart", "id": "chart:line:spread", "kind": "line", "title": f"Spread ({model})",
                          "xlabel": "step", "ylabel": "nodes", "items": [], "series": series,
                          "xq": "(infected_at >= 0) & (infected_at <= {x})"})
        return counts

    # ---- motifs ----------------------------------------------------------------
    def motifs(kind, minimum):
        gr = g()
        nb = neighbours(gr, follow_direction=False)
        k = str(kind).lower()
        groups = []
        if k == "fan":
            # leaves (one neighbour) hanging off the same node
            by_anchor = {}
            for n, ns in nb.items():
                uniq = set(ns)
                if len(uniq) == 1:
                    by_anchor.setdefault(next(iter(uniq)), []).append(n)
            groups = [(a, sorted(ls, key=lambda x: x._id)) for a, ls in by_anchor.items() if len(ls) >= minimum]
        elif k == "connector":
            # nodes linked to exactly the same 2 (or more) anchors and nothing else
            by_set = {}
            for n, ns in nb.items():
                uniq = frozenset(ns)
                if 2 <= len(uniq) <= 4:
                    by_set.setdefault(uniq, []).append(n)
            groups = [(sorted(a, key=lambda x: x._id), sorted(ms, key=lambda x: x._id))
                      for a, ms in by_set.items() if len(ms) >= minimum]
        elif k == "clique":
            from .algorithms import _nx
            nx = _nx()
            G = nx.Graph()
            G.add_nodes_from(n._id for n in gr._nodes_list())
            G.add_edges_from((e._n1._id, e._n2._id) for e in gr._edges_list() if e._n1 is not e._n2)
            used = set()
            for c in sorted(nx.find_cliques(G), key=len, reverse=True):
                c = [i for i in c if i not in used]
                if len(c) >= minimum:
                    used.update(c)
                    groups.append((None, sorted((gr._node_ids[i] for i in c), key=lambda x: x._id)))
        else:
            raise GuessError('kind should be "fan", "connector" or "clique"')
        return groups

    @cmd
    def findMotifs(kind="fan", smallest=3, show=True):
        """findMotifs("fan") finds NodeXL-style motifs, the small repeated
        shapes that clutter big drawings:
          "fan"        several leaves (nodes with one neighbour) on the same node
          "connector"  several nodes linked to exactly the same 2-4 others and
                       nothing else (e.g. people who all know the same two)
          "clique"     groups where everyone is linked to everyone (each node
                       in at most one, largest first)
        with at least `smallest` members. Returns the groups (members only);
        collapseMotifs(kind) replaces each with one meta-node."""
        groups = motifs(kind, int(smallest))
        if show:
            session.say((f"{len(groups)} {kind} motifs", [x for _a, m in groups for x in m]),
                        f" of {smallest}+ nodes, covering {sum(len(m) for _a, m in groups)} nodes")
        return GSet([GSet(m, annotation=f"{kind} {i + 1}") for i, (_a, m) in enumerate(groups)],
                    annotation=f"{kind} motifs")

    @cmd
    def collapseMotifs(kind="fan", smallest=3):
        """collapseMotifs("fan") collapses every motif found by findMotifs into
        one meta-node (labelled with the kind and its size), which simplifies
        the drawing without losing anything: expand(node) or expandAll() bring
        the members back. Returns the meta-nodes."""
        groups = motifs(kind, int(smallest))
        collapse = session.ns["collapse"]
        metas = []
        for i, (_a, members) in enumerate(groups):
            members = [m for m in members if g()._node_ids.get(m._id) is m]
            if len(members) >= int(smallest):
                meta = collapse(members, f"{kind}{i + 1}")
                meta.label = f"{kind} ({len(members)})"
                metas.append(meta)
        session.say("collapsed ", (f"{len(metas)} {kind} motifs", metas), " into meta-nodes")
        return GSet(metas, annotation=f"{kind} motifs")

    # ---- report ----------------------------------------------------------------
    @cmd
    def report(filename=None, top=5):
        """report() writes a one-page summary of the graph: size, density,
        components, degree distribution, path lengths, clustering,
        assortativity, the `top` nodes by degree, betweenness and PageRank,
        and the communities if any have been found (louvain_class,
        leiden_class, infomap_class). report("summary.html") saves it as a web
        page (offered as a download in the browser) and report("summary.md")
        as Markdown; with no name it's printed. Returns the Markdown."""
        gr = g()
        ns = session.ns
        nodes, edges = gr._nodes_list(), gr._edges_list()
        n, m = len(nodes), len(edges)
        lines = ["# Network report", "", f"{n} nodes, {m} edges"
                 + (f" ({sum(1 for e in edges if e._directed)} directed)" if any(e._directed for e in edges) else "") + ".", ""]
        if n == 0:
            text = "\n".join(lines)
        else:
            degs = sorted(len(x._inc) for x in nodes)
            comps = ns["groupBy"](gr.node_schema["component"] if "component" in gr.node_schema
                                  else gr._lazy_field(NODE, "component"))
            rows = [("density", f"{ns['density']():.4f}"),
                    ("components", f"{len(comps)} (largest {len(comps[0])} nodes, {len(comps[0]) / n:.0%})"),
                    ("degree", f"mean {sum(degs) / n:.2f}, median {degs[n // 2]}, max {degs[-1]}"),
                    ("isolated nodes", str(sum(1 for d in degs if d == 0)))]
            for label, fn in (("average path length", "averagePathLength"), ("diameter", "diameter"),
                              ("average clustering", "averageClustering"), ("transitivity", "transitivity"),
                              ("degree assortativity", "assortativity")):
                try:
                    v = ns[fn]()
                    rows.append((label, f"{v:.3f}" if isinstance(v, float) else str(v)))
                except Exception:  # noqa: BLE001 - some measures don't apply to every graph
                    pass
            lines += ["| measure | value |", "|---|---|"] + [f"| {a} | {b} |" for a, b in rows] + [""]
            for title, fname in (("Most connected", "degree"), ("Most between", "betweenness"), ("Highest PageRank", "pagerank")):
                f = gr.node_schema.get(fname) or gr._lazy_field(NODE, fname)
                best = sorted(nodes, key=lambda x: (-(f.get(x) or 0), x._id))[:int(top)]
                lines.append(f"**{title}:** " + ", ".join(f"{x._vals.get('label') or x._name} ({f.get(x):.3g})" for x in best))
                lines.append("")
            for cf in ("louvain_class", "leiden_class", "infomap_class"):
                if cf in gr.node_schema:
                    grps = ns["groupBy"](gr.node_schema[cf])
                    sizes = ", ".join(str(len(x)) for x in grps[:10])
                    q = ns["modularity"](gr.node_schema[cf])
                    lines += [f"**Communities ({cf}):** {len(grps)}, modularity {q:.3f}; largest: {sizes}", ""]
            text = "\n".join(lines)
        if filename is None:
            print(text)
            return text
        name = str(filename)
        if name.lower().endswith((".html", ".htm")):
            body = []
            for line in text.split("\n"):
                if line.startswith("# "):
                    body.append(f"<h1>{_html.escape(line[2:])}</h1>")
                elif line.startswith("| measure"):
                    body.append("<table>")
                elif line.startswith("|---"):
                    continue
                elif line.startswith("| "):
                    a, b = [c.strip() for c in line.strip("|").split("|")]
                    body.append(f"<tr><th>{_html.escape(a)}</th><td>{_html.escape(b)}</td></tr>")
                elif line == "" and body and body[-1].startswith("<tr>"):
                    body.append("</table>")
                elif line:
                    s = _html.escape(line)
                    if s.startswith("**"):
                        s = "<b>" + s[2:].replace("**", "</b>", 1)
                    body.append(f"<p>{s}</p>")
            out = ("<!doctype html><html><head><meta charset='utf-8'><title>Network report</title>"
                   "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 16px}"
                   "th{text-align:left;padding-right:1.5em;font-weight:500}</style></head><body>"
                   + "\n".join(body) + "</body></html>")
        else:
            out = text + "\n"
        with open(name, "w", encoding="utf-8") as fh:
            fh.write(out)
        session.emit({"type": "download", "name": os.path.basename(name), "text": out})
        print(f"wrote {name}")
        return text

    # ---- rich club -------------------------------------------------------------
    @cmd
    def richClub(normalized=True, trials=5, seed=0, show=True):
        """richClub() asks whether the well-connected nodes are densely linked
        to each other: for each degree k, the rich-club coefficient is the
        density of the links among nodes with degree > k. normalized=True
        divides it by the same coefficient in degree-preserving random
        networks (averaged over `trials`): above 1 = a rich club (hubs prefer
        each other, as in airline or scientific elites), below 1 = hubs avoid
        each other. Prints a table and returns {k: value}."""
        from .algorithms import _nx
        nx = _nx()
        gr = g()
        G = nx.Graph()
        G.add_nodes_from(x._id for x in gr._nodes_list())
        G.add_edges_from((e._n1._id, e._n2._id) for e in gr._edges_list() if e._n1 is not e._n2)
        if G.number_of_edges() < 4:
            raise GuessError("richClub needs a few edges")
        raw = nx.rich_club_coefficient(G, normalized=False)
        result = dict(raw)
        if normalized:
            acc = {k: 0.0 for k in raw}
            rng = random.Random(seed)
            for t in range(max(1, int(trials))):
                R = G.copy()
                try:
                    nx.double_edge_swap(R, nswap=4 * R.number_of_edges(), max_tries=40 * R.number_of_edges(),
                                        seed=rng.randint(0, 10 ** 9))
                except nx.NetworkXException:
                    pass
                rr = nx.rich_club_coefficient(R, normalized=False)
                for k in acc:
                    acc[k] += rr.get(k, 0.0)
            result = {k: (raw[k] / (acc[k] / trials) if acc[k] else float("nan")) for k in raw}
        if show:
            ks = sorted(result)
            step = max(1, len(ks) // 12)
            print(f"rich-club coefficient{' (normalised: > 1 = rich club)' if normalized else ''}")
            for k in ks[::step]:
                members = sum(1 for _n, d in G.degree() if d > k)
                print(f"  degree > {k:>3}: {result[k]:6.2f}  ({members} nodes)")
        return result

    # ---- routing ---------------------------------------------------------------
    @cmd
    def minCostFlow(source, target, amount, capacity="capacity", cost="weight"):
        """minCostFlow(a, b, 100) finds the cheapest way to send `amount` units
        from a to b: each edge can carry up to its `capacity` field (missing
        or empty = unlimited) at its `cost` field per unit (default: weight;
        missing = 1). Direction is followed for directed edges; an undirected
        edge can carry flow either way. Stores each edge's flow in `flow` and
        returns the total cost (an error if the amount can't get through)."""
        from .algorithms import _nx
        nx = _nx()
        gr = g()
        a, b = nodes_of([source], "minCostFlow")[0], nodes_of([target], "minCostFlow")[0]
        D = nx.DiGraph()
        capf = gr.edge_schema.get(capacity) if capacity else None
        costf = gr.edge_schema.get(cost) if cost else None
        arc = {}
        for e in gr._edges_list():
            if e._n1 is e._n2:
                continue
            cap = capf.get(e) if capf is not None else None
            c = costf.get(e) if costf is not None else None
            c = 1 if c is None else c
            if c < 0:
                raise GuessError("costs can't be negative")
            pairs = [(e._n1._id, e._n2._id)] + ([] if e._directed else [(e._n2._id, e._n1._id)])
            for u, v in pairs:
                # parallel edges between the same two nodes: the cheapest one is used
                if (u, v) in arc and arc[(u, v)][1] <= c:
                    continue
                attrs = {"weight": int(round(c * 1000))}
                if cap is not None:
                    attrs["capacity"] = float(cap)
                D.add_edge(u, v, **attrs)
                arc[(u, v)] = (e, c)
        D.add_node(a._id, demand=-float(amount))
        D.add_node(b._id, demand=float(amount))
        try:
            flow = nx.min_cost_flow(D)
        except nx.NetworkXUnfeasible:
            raise GuessError(f"can't send {amount} from {a._name} to {b._name} within the capacities") from None
        f = gr.addEdgeField("flow", DOUBLE, 0.0)
        for e in gr._edges_list():
            f.set(e, 0.0)
        total = 0.0
        for u, vs in flow.items():
            for v, x in vs.items():
                if x > 0:
                    e, c = arc[(u, v)]
                    f.set(e, (f.get(e) or 0.0) + x)
                    total += x * c
        session.say(f"sent {amount} from ", a, " to ", b, f" at total cost {total:g}")
        return total

    @cmd
    def travelingSalesman(stops=None, weight="weight", cycle=True):
        """travelingSalesman(stops) finds a short route that visits every node
        in `stops` (default: all) and returns to the start (cycle=False: an
        open path), travelling along the graph's edges with `weight` as the
        length (missing = 1); a stop can be passed through more than once.
        It's an approximation (Christofides' algorithm on undirected graphs,
        a greedy method otherwise), fine for planning, not a proof of
        optimality. Returns the route's nodes and edges in order; .length
        holds its total length."""
        from .algorithms import _nx
        nx = _nx()
        gr = g()
        S = nodes_of(stops, "travelingSalesman") if stops is not None else gr._nodes_list()
        if len(S) < 2:
            raise GuessError("travelingSalesman needs two stops or more")
        wf = gr.edge_schema.get(weight) if weight else None
        directed = any(e._directed for e in gr._edges_list())
        G = nx.DiGraph() if directed else nx.Graph()
        best = {}
        for e in gr._edges_list():
            if e._n1 is e._n2:
                continue
            w = wf.get(e) if wf is not None else None
            w = 1.0 if w is None else float(w)
            pairs = [(e._n1._id, e._n2._id)] + ([(e._n2._id, e._n1._id)] if directed and not e._directed else [])
            for u, v in pairs:
                key = (u, v) if directed else tuple(sorted((u, v)))
                if key not in best or best[key][1] > w:
                    best[key] = (e, w)
                    G.add_edge(u, v, weight=w)
        ids = [x._id for x in S]
        if not all(i in G for i in ids):
            raise GuessError("every stop needs at least one edge")
        try:
            tour = nx.approximation.traveling_salesman_problem(G, nodes=ids, cycle=bool(cycle), weight="weight")
        except (nx.NetworkXError, nx.NetworkXNoPath):
            raise GuessError("the stops aren't all connected") from None
        # start at the first stop given: an open route reads from it, a round trip begins and ends there
        first = ids[0]
        if not cycle and tour[0] != first and tour[-1] == first:
            tour = tour[::-1]
        elif cycle and tour[0] != first and first in tour:
            k = tour.index(first)
            tour = tour[k:-1] + tour[:k] + [first]
        route, length = [], 0.0
        for u, v in zip(tour, tour[1:]):
            key = (u, v) if directed else tuple(sorted((u, v)))
            e, w = best[key]
            route += [gr._node_ids[u], e]
            length += w
        route.append(gr._node_ids[tour[-1]])
        out = GSet(route, annotation=f"route of {len(set(tour))} nodes, length {length:g}")
        object.__setattr__(out, "length", length)    # on the set itself, not its members
        session.say("route through ", (f"{len(S)} stops", S), ": ", (f"{len(tour) - 1} steps", out),
                    f", length {length:g}")
        return out

    # ---- embeddings ------------------------------------------------------------
    @cmd
    def embed(dims=8, walks=10, length=40, window=5, p=1.0, q=1.0, seed=0, name="emb"):
        """embed(dims=8) gives every node coordinates in `dims` dimensions such
        that nodes in similar network positions are close (node2vec, Grover
        and Leskovec 2016): random walks from every node (`walks` of `length`
        steps; p and q bias them towards returning or exploring), then a
        factorisation of how often nodes co-occur within `window` steps. The
        coordinates are stored in fields emb0, emb1, ... (name=...), ready for
        scatterLayout(emb0, emb1), similarity searches or a classifier
        (toNetworkX(), or export the table). Fine up to a few thousand nodes."""
        gr = g()
        nodes = gr._nodes_list()
        n = len(nodes)
        if n < 3:
            raise GuessError("embed needs at least three nodes")
        idx = {x: i for i, x in enumerate(nodes)}
        nb = [[] for _ in range(n)]
        for e in gr._edges_list():
            if e._n1 is not e._n2:
                a, b = idx[e._n1], idx[e._n2]
                nb[a].append(b)
                nb[b].append(a)
        nbset = [set(x) for x in nb]
        rng = random.Random(seed)
        C = np.zeros((n, n))
        for _ in range(int(walks)):
            for s in range(n):
                walk = [s]
                while len(walk) < int(length) and nb[walk[-1]]:
                    cur = walk[-1]
                    if len(walk) == 1 or (p == 1 and q == 1):
                        walk.append(rng.choice(nb[cur]))
                        continue
                    prev = walk[-2]
                    ws = [(1 / p) if x == prev else (1.0 if x in nbset[prev] else 1 / q) for x in nb[cur]]
                    walk.append(rng.choices(nb[cur], weights=ws)[0])
                for i, u in enumerate(walk):
                    for v in walk[i + 1:i + 1 + int(window)]:
                        C[u, v] += 1
                        C[v, u] += 1
        total = C.sum()
        if total == 0:
            raise GuessError("the graph has no edges to walk along")
        row = C.sum(axis=1, keepdims=True)
        col = C.sum(axis=0, keepdims=True)
        with np.errstate(divide="ignore", invalid="ignore"):
            pmi = np.log(C * total / (row @ col))
        P = np.where(np.isfinite(pmi) & (pmi > 0), pmi, 0.0)      # positive PMI
        U, S, _vt = np.linalg.svd(P, hermitian=True)
        k = min(int(dims), n)
        X = U[:, :k] * np.sqrt(S[:k])
        fields = []
        for d in range(k):
            f = gr.addNodeField(f"{name}{d}", DOUBLE, 0.0)
            for i, x in enumerate(nodes):
                f.set(x, float(X[i, d]))
            fields.append(f)
        print(f"embedded {n} nodes in {k} dimensions: fields {name}0 ... {name}{k - 1}")
        return fields

