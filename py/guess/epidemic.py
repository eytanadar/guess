"""Epidemiology: outbreaks on contact networks, transmission trees and
travel networks. (spread(), the single simulated outbreak, is in extras and
shares the simulation here.)

    outbreaks(runs=200)              many simulated outbreaks: size, risk per node
    offspring()                      R, dispersion k and superspreading in a transmission tree
    effectiveDistance(origin)        Brockmann-Helbing distance through a travel network
"""
import math
import random

import numpy as np

from .model import BOOL, DOUBLE, INT, Field, GuessError, Node, elements_of

MODELS = ("si", "sir", "sis", "sirs", "seir", "cascade", "threshold")
MODEL_NAMES = '"SI", "SIR", "SIS", "SIRS", "SEIR", "cascade" or "threshold"'


class Counts(list):
    """[(step, S, I, R)] per step; .exposed lists E per step for SEIR."""


def contacts(gr, beta, weight=None, follow_direction=True):
    """({node: [(neighbour, chance per step)]}, {node: [nodes that reach it]}).
    With a weight field, an edge of weight w transmits with chance
    1 - (1 - beta)**w per step (beta per unit of weight: per minute, say)."""
    out = {n: [] for n in gr._nodes_list()}
    inc = {n: [] for n in gr._nodes_list()}
    b = float(beta)
    for e in gr._edges_list():
        if e._n1 is e._n2:
            continue
        p = b
        if weight is not None:
            w = weight.get(e)
            w = float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0
            p = 1.0 - (1.0 - b) ** max(0.0, w)
        out[e._n1].append((e._n2, p))
        inc[e._n2].append(e._n1)
        if not (e._directed and follow_direction):
            out[e._n2].append((e._n1, p))
            inc[e._n1].append(e._n2)
    return out, inc


def simulate(nodes, out, inc, start, model, gamma, threshold, steps, rng, immune=(), waning=0.0, sigma=0.5,
             duration=None):
    """One outbreak. Returns ({node: S/E/I/R/V}, {node: step first reached or -1},
    Counts [(step, S, I, R)] with .exposed for SEIR). Immune nodes are V: never
    infected. SIS: infected nodes recover to S with probability gamma per step;
    SIRS: recovered nodes lose immunity with probability `waning` per step;
    SEIR: infected nodes are first Exposed (not yet infectious) and become
    infectious with probability `sigma` per step. duration=k: infectious for
    exactly k steps instead of recovering with probability gamma (then SIR is
    exactly bond percolation with T = 1 - (1 - beta)**k). counts.infected_steps
    gives each node's number of steps spent infectious."""
    m = model
    state = {n: "S" for n in nodes}
    for n in immune:
        state[n] = "V"
    when = {n: -1 for n in nodes}
    for n in start:
        if state[n] == "S":
            state[n], when[n] = "I", 0
    fresh = [n for n in start if when[n] == 0]
    n_v = sum(1 for v in state.values() if v == "V")
    counts = Counts([(0, sum(1 for v in state.values() if v == "S"), len(fresh), 0)])
    counts.exposed = [0]
    since = {n: 0 for n in start if when[n] == 0}       # step each infectious node became infectious
    steps_in = {n: 0 for n in nodes}
    dur = None if duration is None else max(1, int(duration))
    g_, th, w_, s_ig = float(gamma), float(threshold), float(waning), float(sigma)
    for t in range(1, int(steps) + 1):
        new, seen = [], set()
        if m == "threshold":
            for n in nodes:
                if state[n] == "S" and inc[n]:
                    if sum(1 for p in inc[n] if state[p] == "I") / len(inc[n]) >= th:
                        new.append(n)
        else:
            sources = fresh if m == "cascade" else [n for n in nodes if state[n] == "I"]
            for n in sources:
                for nb, p in out[n]:
                    if state[nb] == "S" and nb not in seen and rng.random() < p:
                        new.append(nb)
                        seen.add(nb)
        recovered, waned, onset = [], [], []
        for n in nodes:
            if state[n] == "I":
                steps_in[n] += 1
        if m in ("sir", "sis", "sirs", "seir"):
            if dur is not None:
                recovered = [n for n in nodes if state[n] == "I" and t - since.get(n, 0) >= dur]
            else:
                recovered = [n for n in nodes if state[n] == "I" and rng.random() < g_]
        if m == "sirs" and w_ > 0:
            waned = [n for n in nodes if state[n] == "R" and rng.random() < w_]
        if m == "seir":
            onset = [n for n in nodes if state[n] == "E" and rng.random() < s_ig]
        for n in new:
            state[n] = "E" if m == "seir" else "I"
            if m != "seir":
                since[n] = t
            if when[n] < 0:
                when[n] = t
        for n in onset:
            state[n] = "I"
            since[n] = t
        for n in recovered:
            state[n] = "S" if m == "sis" else "R"
        for n in waned:
            state[n] = "S"
        fresh = new
        s_ = sum(1 for v in state.values() if v == "S")
        i_ = sum(1 for v in state.values() if v == "I")
        e_ = sum(1 for v in state.values() if v == "E")
        counts.append((t, s_, i_, len(state) - s_ - i_ - e_ - n_v))
        counts.exposed.append(e_)
        if m in ("sir", "sis", "sirs", "seir"):
            if i_ == 0 and e_ == 0:
                break
        elif not new:
            break
    counts.infected_steps = steps_in
    return state, when, counts


class OutbreakSizes(list):
    """The final size of each simulated outbreak (nodes reached, seeds included),
    with a summary: .mean, .median, .large (share of runs reaching more than
    `large` of the nodes) and .meanLarge (mean size of those)."""

    def __init__(self, sizes, n, large):
        super().__init__(sizes)
        object.__setattr__(self, "n", n)
        a = np.array(sizes, dtype=float) if sizes else np.zeros(1)
        big = a[a > large * n]
        object.__setattr__(self, "mean", float(a.mean()))
        object.__setattr__(self, "median", float(np.median(a)))
        object.__setattr__(self, "large", float(len(big) / len(a)))
        object.__setattr__(self, "meanLarge", float(big.mean()) if len(big) else 0.0)

    def __repr__(self):
        return (f"<{len(self)} outbreaks: mean size {self.mean:.1f} of {self.n}, "
                f"{self.large:.0%} large (mean {self.meanLarge:.1f})>")


class Offspring(dict):
    """{case: number it infected}, with .R (mean), .k (dispersion), .zero (share
    infecting no one) and .top20 (share of transmissions from the most
    infectious 20% of cases)."""

    def __repr__(self):
        return (f"<{len(self)} cases: R = {self.R:.2f}, k = {self.k:.2f}, "
                f"{self.zero:.0%} infected no one, the top 20% caused {self.top20:.0%}>")


def nb_dispersion(xs):
    """Maximum-likelihood dispersion k of a negative binomial with the sample's mean."""
    xs = [int(x) for x in xs]
    mu = sum(xs) / len(xs) if xs else 0.0
    if mu <= 0:
        return float("inf")

    def ll(k):
        return sum(math.lgamma(x + k) - math.lgamma(k) - math.lgamma(x + 1)
                   + k * math.log(k / (k + mu)) + x * math.log(mu / (k + mu)) for x in xs)

    lo, hi = math.log(1e-3), math.log(1e3)            # golden-section search on log k
    r = (math.sqrt(5) - 1) / 2
    a, b = hi - r * (hi - lo), lo + r * (hi - lo)
    fa, fb = ll(math.exp(a)), ll(math.exp(b))
    for _ in range(80):
        if fa > fb:
            hi, b, fb = b, a, fa
            a = hi - r * (hi - lo)
            fa = ll(math.exp(a))
        else:
            lo, a, fa = a, b, fb
            b = lo + r * (hi - lo)
            fb = ll(math.exp(b))
    k = math.exp((lo + hi) / 2)
    return float("inf") if k > 999 else k


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    def node_list(seq, what):
        out = [x for x in elements_of(seq) if isinstance(x, Node)]
        if not out:
            raise GuessError(f"{what} needs nodes")
        return out

    def weight_field(weight):
        if weight is None:
            return None
        if isinstance(weight, str):
            f = g().edge_schema.get(weight)
            if f is None:
                raise GuessError(f"there's no edge field '{weight}'")
            return f
        if isinstance(weight, Field):
            return weight
        raise GuessError("weight should be an edge field, e.g. weight")

    @cmd
    def outbreaks(runs=200, seeds=1, model="SIR", beta=0.3, gamma=0.1, threshold=0.5, immune=None,
                  weight=None, steps=1000, large=0.1, seed=0, name="risk", show=True, waning=0.05, sigma=0.5,
                  duration=None):
        """outbreaks(runs) repeats spread() many times, because one simulated
        outbreak is an anecdote. Each run starts from `seeds` random nodes (a
        number) or from the given nodes. immune=nodes (vaccinated, isolated)
        can't be infected or start an outbreak; weight=field makes long
        contacts riskier (see spread). Stores each node's share of runs it was
        reached in `risk` (name=...), charts the final sizes (hover a bar to see
        where those outbreaks started), and returns them
        (.mean, .median, .large = share of runs reaching more than `large` of
        the nodes)."""
        gr = g()
        m = str(model).lower()
        if m not in MODELS:
            raise GuessError(f"model should be {MODEL_NAMES}")
        nodes = gr._nodes_list()
        out, inc = contacts(gr, beta, weight_field(weight))
        imm = set(node_list(immune, "immune")) if immune is not None else set()
        pool = [n for n in nodes if n not in imm]
        fixed = None if isinstance(seeds, (int, float)) and not isinstance(seeds, bool) else node_list(seeds, "seeds")
        if fixed is None and not pool:
            raise GuessError("every node is immune")
        rng = random.Random(seed)
        hits = {n: 0 for n in nodes}
        sizes, starts = [], []
        runs = max(1, int(runs))
        for _ in range(runs):
            start = fixed if fixed is not None else rng.sample(pool, min(len(pool), max(1, int(seeds))))
            _st, when, _c = simulate(nodes, out, inc, start, m, gamma, threshold, steps, rng, imm,
                                     waning=waning, sigma=sigma, duration=duration)
            reached = [n for n, t in when.items() if t >= 0]
            for n in reached:
                hits[n] += 1
            sizes.append(len(reached))
            starts.append(start)
        f = gr.addNodeField(str(name), DOUBLE, 0.0)
        for n in nodes:
            f.set(n, hits[n] / runs)
        res = OutbreakSizes(sizes, len(nodes), float(large))
        if show:
            print(f"{runs} outbreaks ({model}): mean size {res.mean:.1f} of {len(nodes)} "
                  f"({res.mean / max(1, len(nodes)):.0%}); {res.large:.0%} reached more than {float(large):.0%}")
            bins = 10
            width = max(1.0, len(nodes) / bins)
            counts = [0] * bins
            seeds = [dict() for _ in range(bins)]     # bar -> the people those runs started from
            for x, st in zip(sizes, starts):
                b = min(bins - 1, int(x / width))
                counts[b] += 1
                for n in st:
                    seeds[b][n._id] = None
            items = [{"label": f"{round(i * width)}–{round((i + 1) * width)}", "value": c, "color": 0xd7191c,
                      "ids": [["n", i_] for i_ in seeds[i]]} for i, c in enumerate(counts)]
            session.chart_out({"type": "chart", "id": "chart:bar:outbreaks", "kind": "bar", "title": "Outbreak sizes",
                          "xlabel": "nodes reached", "ylabel": "runs", "items": items})
        return res

    @cmd
    def offspring(cases=None, show=True):
        """offspring() reads a transmission tree (directed edges from infector
        to infected) and counts how many each case infected (its outdegree).
        Returns them with R (the mean), the dispersion k of a negative
        binomial fitted to them (small k, below 1: a few superspreaders cause
        most transmission), the share who infected no one, and the share of
        transmissions caused by the top 20% of cases. offspring(cases) uses
        only those cases, e.g. offspring(onset < 28); their infections count
        wherever they lead. Stores the count in the field `offspring`."""
        gr = g()
        if not any(e._directed for e in gr._edges_list()):
            raise GuessError("offspring() needs a directed transmission tree (infector -> infected)")
        nodes = gr._nodes_list() if cases is None else node_list(cases, "offspring")
        kids = {n: 0 for n in gr._nodes_list()}
        for e in gr._edges_list():
            if e._directed and e._n1 is not e._n2:
                kids[e._n1] += 1
        f = gr.addNodeField("offspring", INT, 0)
        for n, c in kids.items():
            f.set(n, c)
        res = Offspring((n, kids[n]) for n in nodes)
        xs = sorted(res.values(), reverse=True)
        total = sum(xs)
        res.R = total / len(xs) if xs else 0.0
        res.k = nb_dispersion(xs)
        res.zero = sum(1 for x in xs if x == 0) / len(xs) if xs else 0.0
        top = xs[:max(1, round(0.2 * len(xs)))]
        res.top20 = sum(top) / total if total else 0.0
        if show:
            print(repr(res)[1:-1])
            hi = max(xs) if xs else 0
            items = [{"label": str(c), "value": sum(1 for x in xs if x == c), "color": 0xd7191c,
                      "ids": [n._id for n in nodes if kids[n] == c]} for c in range(hi + 1)]
            session.chart_out({"type": "chart", "id": "chart:bar:offspring", "kind": "bar", "title": "Offspring",
                          "xlabel": "people infected", "ylabel": "cases", "items": items})
        return res

    @cmd
    def effectiveDistance(origin, weight="weight", name="eff_distance"):
        """effectiveDistance(origin) measures how 'close' every node is to the
        origin through a travel network, as an epidemic would see it
        (Brockmann and Helbing, Science 2013). From node m, the share of m's
        traffic (weight) that goes to n is P; the step m -> n costs
        1 - ln P, so busy routes are short and a route among many is long.
        Stores the shortest total in `eff_distance` (name=...; unreachable
        nodes get None) and marks the edges of the shortest-path tree in the
        edge field `eff_tree`. Arrival times of real epidemics grow almost
        linearly with it. Returns the field."""
        gr = g()
        src = node_list(origin, "effectiveDistance")[0]
        wf = weight_field(weight) if weight is not None else None
        out = {n: [] for n in gr._nodes_list()}
        for e in gr._edges_list():
            if e._n1 is e._n2:
                continue
            w = wf.get(e) if wf is not None else 1.0
            w = float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0 else 0.0
            if w <= 0:
                continue
            out[e._n1].append((e._n2, w, e))
            if not e._directed:
                out[e._n2].append((e._n1, w, e))
        cost = {}
        for m, lst in out.items():
            tot = sum(w for _n, w, _e in lst)
            cost[m] = [(n, 1.0 - math.log(w / tot), e) for n, w, e in lst]
        import heapq
        dist, via = {src: 0.0}, {}
        heap, k = [(0.0, 0, src)], 1
        done = set()
        while heap:
            d, _k, m = heapq.heappop(heap)
            if m in done:
                continue
            done.add(m)
            for n, c, e in cost[m]:
                if n not in dist or d + c < dist[n] - 1e-12:
                    dist[n], via[n] = d + c, e
                    heapq.heappush(heap, (d + c, k, n))
                    k += 1
        f = gr.addNodeField(str(name), DOUBLE, None)
        for n in gr._nodes_list():
            f.set(n, round(dist[n], 4) if n in dist else None)
        t = gr.addEdgeField("eff_tree", BOOL, False)
        tree = {id(e) for e in via.values()}
        for e in gr._edges_list():
            t.set(e, id(e) in tree)
        return f
