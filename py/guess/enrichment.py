"""Set enrichment: is a group of nodes (a module, a community, a selection)
over-represented in some annotation (a GO term, a pathway, a category)?

    sets = readSets("go.csv")                 # {term: {genes}} from a two-column table
    enrichment(leiden_class == 0, sets)       # hypergeometric test, BH-adjusted
"""
import csv
import math

from .model import Field, GSet, GuessError, Node, elements_of


def _log_choose(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def hypergeom_sf(k, N, K, n):
    """P(X >= k) for X ~ Hypergeometric(population N, K successes, n draws)."""
    lo, hi = max(k, 0), min(K, n)
    if lo > hi:
        return 0.0
    base = _log_choose(N, n)
    terms = [_log_choose(K, i) + _log_choose(N - K, n - i) - base for i in range(lo, hi + 1)]
    m = max(terms)
    return min(1.0, math.exp(m) * sum(math.exp(t - m) for t in terms))


def bh(ps):
    """Benjamini-Hochberg adjusted p-values (q-values), in the input order."""
    n = len(ps)
    order = sorted(range(n), key=lambda i: ps[i])
    q = [0.0] * n
    best = 1.0
    for rank in range(n, 0, -1):
        i = order[rank - 1]
        best = min(best, ps[i] * n / rank)
        q[i] = best
    return q


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    _set = set

    @cmd
    def readSets(filename, item=None, set=None, where=None):  # noqa: A002 - `set` reads well here
        """readSets("go.csv") reads a table with one row per (item, set) pair,
        e.g. gene,term, into {set: {items}} for enrichment(). item= and set=
        name the columns (default: the first two); where={"aspect": "process"}
        keeps only matching rows. A row's set may list several, separated by
        ";" or "|"."""
        with open(filename, encoding="utf-8", errors="replace", newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            delim = "\t" if sample.count("\t") > sample.count(",") else ","
            rows = list(csv.DictReader(fh, delimiter=delim))
        if not rows:
            raise GuessError(f"{filename} has no rows")
        cols = list(rows[0])
        icol, scol = item or cols[0], set or cols[1]
        for c in (icol, scol, *(where or {})):
            if c not in cols:
                raise GuessError(f"{filename} has no column {c!r} (columns: {', '.join(cols)})")
        out = {}
        for r in rows:
            if where and any(str(r.get(k)) != str(v) for k, v in where.items()):
                continue
            it = (r[icol] or "").strip()
            for s in (r[scol] or "").replace("|", ";").split(";"):
                s = s.strip()
                if it and s:
                    out.setdefault(s, _set()).add(it)
        print(f"{len(out)} sets over {len({i for v in out.values() for i in v})} items from {filename}")
        return out

    def _members(seq):
        if isinstance(seq, Field):
            raise GuessError("enrichment needs a set of nodes, e.g. enrichment(leiden_class == 0, sets)")
        return [x for x in elements_of(seq) if isinstance(x, Node)]

    @cmd
    def enrichment(seq, sets, background=None, top=10, minSize=2, show=True):
        """enrichment(nodes, sets) tests which sets (from readSets, or any
        {name: [node names]}) are over-represented among the nodes, against
        the background (default: every node in the graph that is in at least
        one set). For each set it gives the overlap k of n nodes, the set's
        size K among the N background nodes, the fold enrichment
        (k/n)/(K/N), the hypergeometric p-value and the Benjamini-Hochberg
        q-value (the false discovery rate over all sets tested). Sets with
        fewer than minSize background members are skipped. Prints the `top`
        rows by p-value and returns all rows as dicts, best first."""
        gr = g()

        def key(n):
            return n._name

        names = {}
        for n in gr._nodes_list():
            names[n._name] = n
            lab = n._vals.get("label")
            if lab is not None:
                names.setdefault(str(lab), n)
        resolved = {}
        for s, items in dict(sets).items():
            ms = {names[str(i)] for i in items if str(i) in names}
            if ms:
                resolved[s] = ms
        if not resolved:
            raise GuessError("none of the sets' items match node names or labels")
        if background is None:
            bg = {n for ms in resolved.values() for n in ms}
        else:
            bg = _set(_members(background))
        query = _set(_members(seq)) & bg
        N, n = len(bg), len(query)
        if n == 0:
            raise GuessError("none of those nodes are in the background (or annotated in any set)")
        rows = []
        for s, ms in resolved.items():
            ms = ms & bg
            K = len(ms)
            if K < minSize:
                continue
            hit = ms & query
            k = len(hit)
            if k == 0:
                continue
            rows.append({"set": s, "k": k, "n": n, "K": K, "N": N, "fold": (k / n) / (K / N),
                         "p": hypergeom_sf(k, N, K, n),
                         "members": GSet(sorted(hit, key=key), annotation=str(s))})
        tested = sum(1 for ms in resolved.values() if len(ms & bg) >= minSize)
        # BH over every set tested (sets with no overlap have p = 1)
        qs = bh([r["p"] for r in rows] + [1.0] * (tested - len(rows)))
        for r, q in zip(rows, qs):
            r["q"] = q
        rows.sort(key=lambda r: (r["p"], -r["fold"]))
        if show:
            w = min(46, max([len(str(r["set"])) for r in rows[:top]] + [3]))
            print(f"{n} of {N} annotated nodes; {tested} sets tested")
            print(f"{'set':<{w}}  {'k/n':>7}  {'K/N':>8}  {'fold':>5}  {'p':>8}  {'q':>8}")
            for r in rows[:top]:
                name = str(r["set"])[:w]                  # the set's name links to its members in the selection
                session.say((name, r["members"]), " " * (w - len(name)),
                            f"  {r['k']:>3}/{r['n']:<3}  {r['K']:>4}/{r['N']:<3}  "
                            f"{r['fold']:5.1f}  {r['p']:8.1e}  {r['q']:8.1e}")
        return rows
