"""Ecological networks: food webs and mutualistic networks.

Edges in food webs run from food to eater (the direction energy flows), so a
species' indegree is how many things it eats and its outdegree how many eat it.

    makeNicheModel(40, 0.12)        a model food web (Williams and Martinez 2000)
    makeFromGloBI(["Vulpes vulpes"]) observed interactions from GloBI
    trophicLevels()                  trophic level, omnivory, basal/intermediate/top
    extinctions()                    secondary extinction cascades
    nestedness(kind)                 NODF of a two-mode (e.g. plant-pollinator) network
"""
import random
import urllib.parse

import numpy as np

from .model import DOUBLE, NODE, STRING, Field, GuessError


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    def prey_lists(gr):
        """{species: [its food]} from food -> eater edges (undirected edges count both ways)."""
        prey = {n: [] for n in gr._nodes_list()}
        for e in gr._edges_list():
            if e._n1 is e._n2:
                continue
            prey[e._n2].append(e._n1)
            if not e._directed:
                prey[e._n1].append(e._n2)
        return prey

    @cmd
    def makeNicheModel(species=30, connectance=0.15, seed=0):
        """makeNicheModel(species, connectance) builds a food web with the niche
        model (Williams and Martinez 2000), which reproduces the structure of
        real food webs well: each species has a niche value (0..1) and eats
        every species whose niche falls in a range below its own. connectance
        (links / species^2) is typically 0.05-0.3. Edges run from food to
        eater; nodes get `niche` and `range`. Species left without any link
        are dropped. seed= gives a different web."""
        S, C = int(species), float(connectance)
        if S < 3 or not 0 < C < 0.5:
            raise GuessError("makeNicheModel needs species >= 3 and 0 < connectance < 0.5")
        rng = random.Random(seed)
        beta = 1 / (2 * C) - 1
        niche = sorted(rng.random() for _ in range(S))
        ranges = [n * rng.betavariate(1, beta) for n in niche]
        ranges[0] = 0.0                                  # the lowest species is basal
        centres = [rng.uniform(r / 2, n) for n, r in zip(niche, ranges)]
        links = [(j, i) for i in range(S) for j in range(S)
                 if ranges[i] > 0 and centres[i] - ranges[i] / 2 <= niche[j] <= centres[i] + ranges[i] / 2]
        used = {i for e in links for i in e}
        gr = g()
        gr.clear()
        gr.addNodeField("niche", DOUBLE, 0.0)
        gr.addNodeField("range", DOUBLE, 0.0)
        for i in range(S):
            if i in used:
                n = gr.addNode(f"s{i + 1}")
                n.niche, n.range = round(niche[i], 4), round(ranges[i], 4)
        for j, i in links:
            gr.addDirectedEdge(f"s{j + 1}", f"s{i + 1}")
        session.ns["frLayout"]()
        session.scene()
        kept = len(used)
        print(f"niche model: {kept} species, {len(links)} feeding links, connectance "
              f"{len(links) / kept ** 2:.3f}" + (f" ({S - kept} unlinked species dropped)" if kept < S else ""))

    @cmd
    def trophicLevels():
        """trophicLevels() computes each species' prey-averaged trophic level
        (`trophic`: 1 for species that eat nothing in the web, otherwise 1 + the
        mean level of what it eats), `omnivory` (the spread of its food's
        levels: 0 = eats on one level) and `role` (basal: eats nothing here;
        top: nothing eats it; else intermediate). Prints a summary."""
        gr = g()
        nodes = gr._nodes_list()
        if not nodes:
            raise GuessError("no species")
        idx = {n: i for i, n in enumerate(nodes)}
        prey = prey_lists(gr)
        n = len(nodes)
        A = np.eye(n)
        b = np.ones(n)
        for sp, food in prey.items():
            food = [f for f in food if f is not sp]
            if food:
                for f in food:
                    A[idx[sp], idx[f]] -= 1 / len(food)
        try:
            tl = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            tl = np.linalg.lstsq(A, b, rcond=None)[0]
        eaten = {f for food in prey.values() for f in food}
        ftl = gr.addNodeField("trophic", DOUBLE, 1.0)
        fom = gr.addNodeField("omnivory", DOUBLE, 0.0)
        frole = gr.addNodeField("role", STRING, None)
        for sp in nodes:
            i = idx[sp]
            ftl.set(sp, float(tl[i]))
            food = [f for f in prey[sp] if f is not sp]
            fom.set(sp, float(np.std([tl[idx[f]] for f in food])) if food else 0.0)
            frole.set(sp, "basal" if not food else ("top" if sp not in eaten else "intermediate"))
        roles = [frole.get(sp) for sp in nodes]
        print(f"trophic levels 1 to {tl.max():.2f} (mean {tl.mean():.2f}); "
              f"basal {roles.count('basal')}, intermediate {roles.count('intermediate')}, top {roles.count('top')}")

    @cmd
    def extinctions(orders=("random", "degree"), trials=10, seed=0, show=True):
        """extinctions() simulates species loss in a food web: species are
        removed one at a time ("primary" extinctions) and any species left
        with nothing to eat dies out too ("secondary" extinctions; species
        that eat nothing in the web, the basal ones, never starve). orders:
        "random" (averaged over `trials`), "degree" (most connected first),
        "least" (least connected first), "basal" (producers first) or a node
        field (highest first). Plots the share of species surviving against
        the share removed, and prints R50, the share of primary removals
        that brings total losses to half the species (higher = more robust).
        The graph isn't changed. Returns {order: [(removed, surviving)...]}."""
        gr = g()
        nodes = gr._nodes_list()
        S = len(nodes)
        if S < 2:
            raise GuessError("extinctions needs a food web (two species or more)")
        idx = {n: i for i, n in enumerate(nodes)}
        prey = prey_lists(gr)
        food = [[idx[f] for f in prey[n] if f is not n] for n in nodes]
        eaters = [[] for _ in range(S)]
        for i, fs in enumerate(food):
            for f in fs:
                eaters[f].append(i)
        basal = [not fs for fs in food]
        deg = [len(food[i]) + len(eaters[i]) for i in range(S)]

        def run(order):
            alive = [True] * S
            left = [len(fs) for fs in food]
            pts, count = [(0.0, 1.0)], S
            for k, v in enumerate(order, start=1):
                if alive[v]:
                    stack = [v]
                    alive[v] = False
                    count -= 1
                    while stack:
                        x = stack.pop()
                        for c in eaters[x]:
                            if alive[c]:
                                left[c] -= 1
                                if left[c] == 0 and not basal[c]:
                                    alive[c] = False
                                    count -= 1
                                    stack.append(c)
                pts.append((k / S, count / S))
            return pts

        if isinstance(orders, (str, Field)):
            orders = [orders]
        results = {}
        for o in orders:
            name = o.name if isinstance(o, Field) else str(o)
            if name == "random":
                rng = random.Random(seed)
                runs = []
                for _ in range(max(1, int(trials))):
                    order = list(range(S))
                    rng.shuffle(order)
                    runs.append(run(order))
                pts = [(runs[0][i][0], sum(r[i][1] for r in runs) / len(runs)) for i in range(len(runs[0]))]
            elif name in ("degree", "least", "basal"):
                key = {"degree": lambda i: (-deg[i], i), "least": lambda i: (deg[i], i),
                       "basal": lambda i: (not basal[i], -deg[i], i)}[name]
                pts = run(sorted(range(S), key=key))
            else:
                f = o if isinstance(o, Field) else gr.node_schema.get(name)
                if f is None and (NODE, name) in gr.lazy_fields:
                    f = gr._lazy_field(NODE, name)
                if f is None:
                    raise GuessError(f"unknown order {name!r}: random, degree, least, basal or a node field")
                vals = [f.get(n) for n in nodes]
                pts = run(sorted(range(S), key=lambda i: (-(vals[i] if isinstance(vals[i], (int, float)) else 0), i)))
            results[name] = pts
        if show:
            for k, v in results.items():
                r50 = next((x for x, y in v if y <= 0.5), 1.0)
                print(f"{k:>10}: R50 = {r50:.2f} (half the species gone after removing {r50:.0%})")
            palette = [0x2c7bb6, 0xd7191c, 0x1a9641, 0x8e5fbf, 0xfdae61]
            series = [{"name": k, "color": palette[i % 5], "points": [[round(x, 4), round(y, 4)] for x, y in v]}
                      for i, (k, v) in enumerate(results.items())]
            session.emit({"type": "chart", "id": "chart:line:extinctions", "kind": "line",
                          "title": "Extinction cascades", "xlabel": "share of species removed",
                          "ylabel": "share surviving", "items": [], "series": series})
        return results

    @cmd
    def nestedness(field, rows=None):
        """nestedness(kind) measures how nested a two-mode network is (NODF,
        Almeida-Neto et al. 2008; 0 = not at all, 100 = perfectly): in a
        nested plant-pollinator network, the specialists interact with
        subsets of the species the generalists interact with. kind is the
        field saying which side each node is on; rows= names one side
        (default: the first value). Returns (NODF, NODF of the rows, NODF of
        the columns). Compare with a randomised network (rewire()) to judge
        whether a value is high."""
        gr = g()
        f = field if isinstance(field, Field) else gr.node_schema.get(str(field))
        if f is None:
            raise GuessError("nestedness needs the field that says which side each node is on")
        vals = [v for v in f.distinct if v is not None]
        if len(vals) != 2:
            raise GuessError(f"{f.name} should have two values (it has {len(vals)})")
        side = rows if rows is not None else vals[0]
        R = [n for n in gr._nodes_list() if f.get(n) == side]
        Cn = [n for n in gr._nodes_list() if f.get(n) is not None and f.get(n) != side]
        ci = {n: j for j, n in enumerate(Cn)}
        M = np.zeros((len(R), len(Cn)), bool)
        for i, n in enumerate(R):
            for e in n._inc.values():
                o = e._n2 if e._n1 is n else e._n1
                if o in ci:
                    M[i, ci[o]] = True

        def paired(mat):
            deg = mat.sum(axis=1)
            total, pairs = 0.0, 0
            for a in range(len(mat)):
                for b in range(len(mat)):
                    if a == b:
                        continue
                    if deg[a] > deg[b] > 0:
                        total += (mat[a] & mat[b]).sum() / deg[b]
                        pairs += 1
                    elif deg[a] > deg[b] or (deg[a] == deg[b] and a < b):
                        pairs += 1          # equal (or empty) fills count as 0
            return total, pairs
        tr, pr = paired(M)
        tc, pc = paired(M.T)
        nodf = 100 * (tr + tc) / (pr + pc) if pr + pc else 0.0
        nr = 100 * tr / pr if pr else 0.0
        nc = 100 * tc / pc if pc else 0.0
        print(f"NODF {nodf:.1f} (rows {nr:.1f}, columns {nc:.1f}) for {len(R)} x {len(Cn)}")
        return round(nodf, 2), round(nr, 2), round(nc, 2)

    @cmd
    def makeFromGloBI(taxa, interaction="eats", limit=500, server="https://api.globalbioticinteractions.org"):
        """makeFromGloBI(["Vulpes vulpes", "Lynx lynx"]) opens observed species
        interactions from the Global Biotic Interactions database (GloBI):
        for each taxon, what it `interaction`s (eats, preysOn, pollinates,
        parasiteOf, visitsFlowersOf, ...), up to `limit` records each.
        Feeding links run from food to eater, other kinds from the taxon to
        its partner. Edges get `weight` (records) and `interaction`; nodes
        `taxon` (the full name) and `query` (true for the taxa you asked
        for). GloBI aggregates many studies with their own licences: cite
        GloBI and the sources you use."""
        from .connectors import http
        if isinstance(taxa, str):
            taxa = [taxa]
        feeding = interaction in ("eats", "preysOn")
        gr = g()
        gr.clear()
        gr.addNodeField("taxon", STRING, None)
        gr.addNodeField("query", "BOOLEAN", False)
        gr.addEdgeField("interaction", STRING, None)
        if "weight" not in gr.edge_schema:
            gr.addEdgeField("weight", DOUBLE, 1.0)
        names, edges = {}, {}

        def node(t):
            if t not in names:
                import re
                nm = re.sub(r"\W+", "_", t).strip("_") or "taxon"
                while nm in gr._nodes:
                    nm += "_"
                n = gr.addNode(nm)
                n.label = n.taxon = t
                names[t] = nm
            return names[t]
        import json
        for t in taxa:
            q = urllib.parse.urlencode({"sourceTaxon": t, "interactionType": interaction, "limit": int(limit),
                                        "fields": "source_taxon_name,target_taxon_name"})
            data = json.loads(http(f"{server}/interaction?{q}"))
            for src, tgt in data.get("data", []):
                if not src or not tgt or src == tgt:
                    continue
                a, b = (node(tgt), node(src)) if feeding else (node(src), node(tgt))
                edges[(a, b)] = edges.get((a, b), 0) + 1
            gr.getNodeByName(node(t)).query = True
        for (a, b), w in edges.items():
            gr.addDirectedEdge(a, b, weight=float(w), interaction=interaction)
        session.ns["frLayout"]()
        session.scene()
        print(f"{len(names)} taxa, {len(edges)} '{interaction}' links from GloBI "
              "(cite GloBI and its sources)")

