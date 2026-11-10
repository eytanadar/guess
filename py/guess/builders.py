"""Networks built from other kinds of data.

    makeFromText("story.txt", terms={"Holmes": ["Holmes", "Sherlock"], ...})
        terms (characters, concepts) linked when they occur in the same
        paragraph, sentence, line or window of words
    makeFromSimilarity("profiles.csv", k=5)
        rows of a feature table linked to their most similar rows
"""
import bisect
import csv
import re

import numpy as np

from .model import DOUBLE, INT, STRING, GuessError

STOPWORDS = set("""
a about above after again against all also am an and any are aren't as at be because been before
being below between both but by can can't cannot could couldn't did didn't do does doesn't doing
don't down during each few for from further had hadn't has hasn't have haven't having he he'd
he'll he's her here here's hers herself him himself his how how's i i'd i'll i'm i've if in into
is isn't it it's its itself let's me more most mustn't my myself no nor not of off on once only
or other ought our ours ourselves out over own same shan't she she'd she'll she's should
shouldn't so some such than that that's the their theirs them themselves then there there's
these they they'd they'll they're they've this those through to too under until up upon very
was wasn't we we'd we'll we're we've were weren't what what's when when's where where's which
while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your
yours yourself yourselves one two may might must shall will said say says like just now well
even much many every ever never still yet back again us into within without very quite rather
""".split())

_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")


def split_units(text, by):
    if by == "paragraph":
        units = re.split(r"\n\s*\n", text)
    elif by == "line":
        units = text.splitlines()
    elif by == "sentence":
        flat = re.sub(r"\s+", " ", text)
        units = re.split(r"(?<=[.!?])[\"”’)]*\s+(?=[\"“‘(]*[A-Z0-9])", flat)
    else:
        raise GuessError('by should be "paragraph", "sentence" or "line" (or use window=)')
    return [u for u in units if u.strip()]


def _alias_patterns(terms, case):
    """{node name: compiled regex} from a list of terms or {name: [aliases]}."""
    if isinstance(terms, dict):
        items = [(str(k), [str(a) for a in (v if isinstance(v, (list, tuple, set)) else [v])])
                 for k, v in terms.items()]
    else:
        items = [(str(t), [str(t)]) for t in terms]
    flags = 0 if case else re.IGNORECASE
    out = {}
    for name, aliases in items:
        alts = "|".join(re.escape(a).replace(r"\ ", r"\s+") for a in sorted(aliases, key=len, reverse=True))
        out[name] = re.compile(rf"(?<![\w’'])(?:{alts})(?![\w])", flags)
    return out


def _ident(s):
    s = re.sub(r"\W+", "_", str(s)).strip("_") or "term"
    return "_" + s if s[0].isdigit() else s


def _cosine(X):
    norm = np.linalg.norm(X, axis=1)
    norm[norm == 0] = 1
    Y = X / norm[:, None]
    return Y @ Y.T


def similarity_matrix(X, method):
    if method == "cosine":
        return _cosine(X)
    if method == "correlation":
        Z = X - X.mean(axis=1, keepdims=True)
        return _cosine(Z)
    if method == "jaccard":
        B = (X != 0).astype(float)
        inter = B @ B.T
        sizes = B.sum(axis=1)
        union = sizes[:, None] + sizes[None, :] - inter
        with np.errstate(invalid="ignore", divide="ignore"):
            S = np.where(union > 0, inter / union, 0.0)
        return S
    if method == "euclidean":
        sq = (X ** 2).sum(axis=1)
        D = np.sqrt(np.maximum(sq[:, None] + sq[None, :] - 2 * X @ X.T, 0))
        return 1 / (1 + D)
    raise GuessError('method should be "cosine", "correlation", "jaccard" or "euclidean"')


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    def layout():
        session.ns["frLayout"]()
        session.scene()

    @cmd
    def makeFromText(filename, terms=None, by="paragraph", window=None, minCount=3, maxTerms=60,
                     caseSensitive=False, stopwords=None):
        """makeFromText("story.txt", terms) builds a co-occurrence network: one
        node per term, linked when two terms occur in the same paragraph
        (by="sentence" or "line" for smaller units; window=k for within k
        words of each other, in the same paragraph). terms is a list of names, or a dict from each
        node's name to its aliases, e.g. {"Holmes": ["Holmes", "Sherlock"],
        "Adler": ["Irene Adler", "Miss Adler", "the woman"]} (matching ignores
        case unless caseSensitive=true). Without terms, the maxTerms most
        frequent words (at least minCount times, minus common words and
        stopwords=[...]) are used. Nodes get `count` (occurrences), `units`
        (paragraphs etc. containing them) and `first` (the first unit, for
        story order); edges get `weight`, the number of shared units (or
        windows)."""
        with open(filename, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if window is not None:
            window = int(window)
            if window < 1:
                raise GuessError("window should be at least 1 word")
        if terms is None:
            stop = STOPWORDS | {str(w).lower() for w in (stopwords or [])}
            counts = {}
            for w in _WORD.findall(text):
                lw = w.lower().strip("'’-")
                if len(lw) > 2 and lw not in stop:
                    counts[lw] = counts.get(lw, 0) + 1
            top = sorted((w for w, c in counts.items() if c >= int(minCount)), key=lambda w: (-counts[w], w))
            terms = top[:int(maxTerms)]
            if not terms:
                raise GuessError(f"no word occurs {minCount} times or more")
            caseSensitive = False
        pats = _alias_patterns(terms, caseSensitive)
        names = {name: _ident(name) for name in pats}
        stats = {name: {"count": 0, "units": 0, "first": None} for name in pats}
        pairs = {}

        def link(present):
            ps = sorted(present)
            for i, a in enumerate(ps):
                for b in ps[i + 1:]:
                    pairs[(a, b)] = pairs.get((a, b), 0) + 1

        if window is None:
            units = split_units(text, by)
            for ui, u in enumerate(units):
                present = set()
                for name, rx in pats.items():
                    hits = len(rx.findall(u))
                    if hits:
                        st = stats[name]
                        st["count"] += hits
                        st["units"] += 1
                        if st["first"] is None:
                            st["first"] = ui
                        present.add(name)
                link(present)
        else:
            # word positions of every match, then pairs within `window` words
            # of each other in the same paragraph
            offsets = [m.start() for m in re.finditer(r"\S+", text)]
            breaks = [m.start() for m in re.finditer(r"\n\s*\n", text)]
            occ = []
            para = {}
            for name, rx in pats.items():
                for m in rx.finditer(text):
                    w = bisect.bisect_right(offsets, m.start()) - 1
                    occ.append((w, name))
                    para[w] = bisect.bisect_right(breaks, m.start())
                    stats[name]["count"] += 1
            occ.sort()
            for name in pats:
                pos = [p for p, n in occ if n == name]
                stats[name]["units"] = len(pos)
                stats[name]["first"] = pos[0] if pos else None
            j = 0
            for i, (p, a) in enumerate(occ):
                while occ[j][0] < p - window:
                    j += 1
                near = {b for q, b in occ[j:i] if b != a and para[q] == para[p]}
                for b in near:
                    key = (min(a, b), max(a, b))
                    pairs[key] = pairs.get(key, 0) + 1
        gr = g()
        gr.clear()
        gr.addNodeField("count", INT, 0)
        gr.addNodeField("units", INT, 0)
        gr.addNodeField("first", INT, -1)
        if "weight" not in gr.edge_schema:
            gr.addEdgeField("weight", DOUBLE, 1.0)
        kept = [n for n in pats if stats[n]["count"] > 0]
        for name in kept:
            n = gr.addNode(names[name])
            n.label = name
            n.count, n.units = stats[name]["count"], stats[name]["units"]
            n.first = stats[name]["first"] if stats[name]["first"] is not None else -1
        for (a, b), w in pairs.items():
            if a in kept and b in kept:
                gr.addUndirectedEdge(names[a], names[b], weight=float(w))
        missing = [n for n in pats if stats[n]["count"] == 0]
        layout()
        unit = f"within {window} words" if window else f"per {by}"
        print(f"{len(kept)} terms, {len(gr._edges)} co-occurrence links ({unit})"
              + (f"; never found: {', '.join(missing[:8])}" if missing else ""))

    @cmd
    def makeFromTwoMode(filename, a=None, b=None, weight=None):
        """makeFromTwoMode("paper-authors.csv", "paper", "author") reads a table
        with one row per pair (a paper and one of its authors, a gene and one
        of its terms, a person and an event) as a two-mode network: a node
        for every value of each column, an edge for every row, and `kind` set
        to the column's name, ready for bipartiteLayout(kind) or
        project(kind, "author"). a= and b= name the columns (default: the
        first two); weight= names a numeric column to use as edge weight.
        Repeated rows add to the weight."""
        with open(filename, encoding="utf-8", errors="replace", newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            delim = "\t" if sample.count("\t") > sample.count(",") else ","
            rows = list(csv.DictReader(fh, delimiter=delim))
        if not rows:
            raise GuessError(f"{filename} has no rows")
        cols = list(rows[0])
        a, b = a or cols[0], b or cols[1]
        for c in (a, b) + ((weight,) if weight else ()):
            if c not in cols:
                raise GuessError(f"no column {c!r} (columns: {', '.join(cols)})")
        if a == b:
            raise GuessError("the two columns must differ")
        gr = g()
        gr.clear()
        gr.addNodeField("kind", STRING, None)
        if "weight" not in gr.edge_schema:
            gr.addEdgeField("weight", DOUBLE, 1.0)
        names = {}

        def node(col, value):
            key = (col, value)
            if key not in names:
                nm = _ident(value)
                if nm in gr._nodes:
                    nm = _ident(f"{col}_{value}")
                    k = 2
                    while nm in gr._nodes:
                        nm, k = _ident(f"{col}_{value}_{k}"), k + 1
                n = gr.addNode(nm)
                n.label = str(value)
                n.kind = col
                names[key] = nm
            return names[key]

        edges = {}
        for r in rows:
            va, vb = (r.get(a) or "").strip(), (r.get(b) or "").strip()
            if not va or not vb:
                continue
            na, nb = node(a, va), node(b, vb)
            w = 1.0
            if weight:
                try:
                    w = float(r[weight])
                except (TypeError, ValueError):
                    w = 1.0
            edges[(na, nb)] = edges.get((na, nb), 0.0) + w
        for (na, nb), w in edges.items():
            gr.addUndirectedEdge(na, nb, weight=w)
        layout()
        na = sum(1 for k in names if k[0] == a)
        print(f"{na} {a} and {len(names) - na} {b} nodes, {len(edges)} links; "
              f"try bipartiteLayout(kind) or project(kind, {b!r})")

    @cmd
    def makeFromSimilarity(filename, k=5, threshold=None, method="cosine", id=None, columns=None,  # noqa: A002
                           features=None, values=None, mutual=False):
        """makeFromSimilarity("profiles.csv") links each row of a feature table
        to the k rows most similar to it (k=5), or, with threshold=t, every
        pair at least t similar. The table is wide (an id column, here the
        first or id=..., then numeric columns; columns=[...] picks them, and
        text columns become node fields) or long, one row per (id, feature,
        value): features="keyword", values="score" (values default to 1).
        method: "cosine" (default; profiles pointing the same way),
        "correlation" (same ups and downs), "jaccard" (shared nonzero
        features) or "euclidean" (close values; 1/(1+distance)). mutual=true
        keeps only pairs that are in each other's top k. Edges get `weight`
        = similarity. Typical uses: co-expression networks, documents by
        term profile, people by votes or answers."""
        with open(filename, encoding="utf-8", errors="replace", newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            delim = "\t" if sample.count("\t") > sample.count(",") else ","
            rows = list(csv.DictReader(fh, delimiter=delim))
        if not rows:
            raise GuessError(f"{filename} has no rows")
        cols = list(rows[0])
        idc = id or cols[0]
        if idc not in cols:
            raise GuessError(f"no column {idc!r} (columns: {', '.join(cols)})")

        def num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        extra = {}
        if features is not None:
            if features not in cols or (values is not None and values not in cols):
                raise GuessError(f"columns are {', '.join(cols)}")
            ids, feats, cell = [], [], {}
            fi = {}
            for r in rows:
                i, f = r[idc], r[features]
                if not i or not f:
                    continue
                if i not in cell:
                    ids.append(i)
                    cell[i] = {}
                if f not in fi:
                    fi[f] = len(feats)
                    feats.append(f)
                v = 1.0 if values is None else (num(r[values]) or 0.0)
                cell[i][fi[f]] = cell[i].get(fi[f], 0.0) + v
            X = np.zeros((len(ids), len(feats)))
            for a, i in enumerate(ids):
                for f, v in cell[i].items():
                    X[a, f] = v
        else:
            use = [c for c in (columns or cols) if c != idc]
            numeric = [c for c in use if all(num(r[c]) is not None for r in rows if r[c] not in ("", None))]
            if columns:
                bad = [c for c in use if c not in numeric]
                if bad:
                    raise GuessError(f"not numeric: {', '.join(bad)}")
            if not numeric:
                raise GuessError("no numeric columns to compare")
            ids = [r[idc] for r in rows]
            X = np.array([[num(r[c]) or 0.0 for c in numeric] for r in rows])
            extra = {c: [r[c] for r in rows] for c in cols if c != idc and c not in numeric}
        n = len(ids)
        if n < 2:
            raise GuessError("need at least two rows")
        S = similarity_matrix(X, method)
        np.fill_diagonal(S, -np.inf)
        pairs = {}
        if threshold is not None:
            t = float(threshold)
            a, b = np.nonzero(np.triu(S >= t, 1))
            for i, j in zip(a, b):
                pairs[(i, j)] = S[i, j]
        else:
            k = max(1, min(int(k), n - 1))
            top = np.argsort(-S, axis=1)[:, :k]
            chosen = {(i, int(j)) for i in range(n) for j in top[i] if np.isfinite(S[i, j])}
            for i, j in chosen:
                if mutual and (j, i) not in chosen:
                    continue
                pairs[(min(i, j), max(i, j))] = S[i, j]
        gr = g()
        gr.clear()
        if "weight" not in gr.edge_schema:
            gr.addEdgeField("weight", DOUBLE, 1.0)
        for c in extra:
            gr.addNodeField(_ident(c), STRING, None)
        names = []
        for a, i in enumerate(ids):
            nm = _ident(i) if _ident(i) not in gr._nodes else f"{_ident(i)}_{a}"
            node = gr.addNode(nm)
            node.label = str(i)
            for c, vals in extra.items():
                setattr(node, _ident(c), vals[a])
            names.append(nm)
        for (i, j), s in pairs.items():
            gr.addUndirectedEdge(names[i], names[j], weight=float(s))
        layout()
        rule = f"similarity >= {threshold}" if threshold is not None else f"{'mutual ' if mutual else ''}top {k}"
        print(f"{n} rows, {len(pairs)} links ({method}, {rule})")

