"""Tools for investigations: entity resolution, group profiles, cycles.

    findDuplicates(name)              likely duplicate entities, for review
    mergeNodes(a, b, ...)             merge them into one (edges and fields)
    groupStats(louvain_class)      size, density, boundary of each group
    findCycles(maxLength=5)           closed loops (round-tripping)
"""
import difflib
import re
import unicodedata

from .model import INT, NODE, STRING, Field, GSet, GuessError, Node, elements_of

_SUFFIXES = r"\b(ltd|limited|llc|inc|corp|corporation|co|company|plc|sa|gmbh|bv|ag|the|mr|mrs|ms|dr)\b"


def normalize_name(s):
    """Lower case, no accents or punctuation, common company suffixes and
    titles dropped, words sorted: 'Acme Ltd.' and 'ACME' compare equal."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    s = re.sub(_SUFFIXES, " ", s)
    return " ".join(sorted(s.split()))


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    def node_field(f, what):
        gr = g()
        if isinstance(f, Field) and f.kind == NODE:
            return f
        if isinstance(f, str) and f in gr.node_schema:
            return gr.node_schema[f]
        if isinstance(f, str) and (NODE, f) in gr.lazy_fields:
            return gr._lazy_field(NODE, f)
        raise GuessError(f"{what} needs a node field, e.g. {what}(name)")

    @cmd
    def findDuplicates(field=None, threshold=0.85, among=None, top=50, show=True):
        """findDuplicates(name) lists pairs of nodes whose values of a text
        field look like the same entity: compared after normalising (case,
        accents, punctuation, word order, company suffixes and titles like
        Ltd, Inc, Mr), scored 0..1 by string similarity, best first, at least
        `threshold`. among=nodes restricts the search (e.g. one kind of
        entity). Default field: label. Returns (node, node, score) for review
        and mergeNodes; it never merges anything itself."""
        gr = g()
        f = node_field(field, "findDuplicates") if field is not None else gr.node_schema["label"]
        nodes = [x for x in (elements_of(among) if among is not None else gr._nodes_list()) if isinstance(x, Node)]
        norm = {}
        for n in nodes:
            v = f.get(n)
            if v not in (None, ""):
                norm[n] = normalize_name(v)
        # block by the first letters of the normalised words to keep it fast
        blocks = {}
        for n, s in norm.items():
            for w in set(s.split()):
                blocks.setdefault(w[:3], []).append(n)
        seen, out = set(), []
        for members in blocks.values():
            if len(members) > 400:
                continue          # a very common token: no evidence on its own
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    key = (min(a._id, b._id), max(a._id, b._id))
                    if key in seen:
                        continue
                    seen.add(key)
                    sa, sb = norm[a], norm[b]
                    score = 1.0 if sa == sb else difflib.SequenceMatcher(None, sa, sb).ratio()
                    if score >= float(threshold):
                        out.append((a, b, round(score, 3)))
        out.sort(key=lambda t: (-t[2], t[0]._id, t[1]._id))
        if show:
            session.say((f"{len(out)} likely duplicate pairs", [x for a, b, _s in out for x in (a, b)]),
                        f" (score >= {threshold})")
            for a, b, sc in out[:int(top)]:
                session.say(f"  {sc:.2f}  ", (f"{f.get(a)!s}", [a]), "  ~  ", (f"{f.get(b)!s}", [b]))
        return out

    @cmd
    def mergeNodes(*nodes, name=None):
        """mergeNodes(a, b, ...) merges nodes that are the same entity into
        the first (or name=...): every edge of the others moves to it
        (parallel edges are combined, adding their weights; edges between the
        merged nodes disappear), empty fields of the kept node are filled
        from the others, `aliases` records the other names and labels, and
        `merged` counts the nodes it stands for. One undo step. Also takes a
        set or a list of pairs from findDuplicates (each pair merged)."""
        gr = g()
        if len(nodes) == 1 and isinstance(nodes[0], list) and nodes[0] and isinstance(nodes[0][0], tuple):
            groups = _pairs_to_groups(nodes[0])
        else:
            items = [x for x in elements_of(nodes) if isinstance(x, Node)]
            groups = [items]
        done, kept = 0, []
        for items in groups:
            items = [x for x in items if gr._node_ids.get(x._id) is x]
            if len(items) < 2:
                continue
            keep = items[0]
            if name is not None and len(groups) == 1:
                hit = gr._nodes.get(str(name))
                if hit is None or hit not in items:
                    raise GuessError("name= must be one of the nodes being merged")
                keep = hit
            others = [x for x in items if x is not keep]
            _merge(gr, keep, others)
            done += 1
            kept.append(keep)
        if not done:
            raise GuessError("mergeNodes needs at least two nodes (or duplicate pairs)")
        session.scene()
        session.say("merged ", (f"{done} group{'s' if done != 1 else ''}", kept), " (into these nodes)")
        return done

    def _merge(gr, keep, others):
        if "aliases" not in gr.node_schema:
            gr.addNodeField("aliases", STRING, None)
        if "merged" not in gr.node_schema:
            gr.addNodeField("merged", INT, 1)
        weight = gr.edge_schema.get("weight")
        group = {keep._id} | {o._id for o in others}
        # existing edges of keep, by (other end, direction)
        def key(e, me):
            other = e._n2 if e._n1 is me else e._n1
            return (other._id, e._directed, e._n1 is me)
        existing = {key(e, keep): e for e in list(keep._inc.values())}
        aliases = [a for a in (keep.aliases or "").split("; ") if a]
        count = keep.merged or 1
        for o in others:
            for e in list(o._inc.values()):
                other = e._n2 if e._n1 is o else e._n1
                if other._id in group:
                    continue                       # an edge inside the group disappears
                k = (other._id, e._directed, e._n1 is o)
                w = (weight.get(e) if weight is not None else None) or 1.0
                if k in existing:
                    tgt = existing[k]
                    if weight is not None:
                        weight.set(tgt, (weight.get(tgt) or 1.0) + w)
                    continue
                a, b = (keep, other) if e._n1 is o else (other, keep)
                ne = gr.addEdge(a, b, e._directed)
                for fname, fld in gr.edge_schema.items():
                    if fld.compute is None and not fld.readonly and fname in e._vals:
                        ne._vals[fname] = e._vals[fname]
                existing[k] = ne
            for fname, fld in gr.node_schema.items():
                if fld.compute is not None or fld.readonly or fld.builtin or fname in ("aliases", "merged"):
                    continue
                if keep._vals.get(fname) in (None, "") and o._vals.get(fname) not in (None, ""):
                    fld.set(keep, o._vals[fname])
            for a in (o._name, o._vals.get("label")):
                if a and a not in aliases and a != keep._name and a != keep._vals.get("label"):
                    aliases.append(str(a))
            count += o.merged or 1
        gr.remove(others, keep=True)
        keep.aliases = "; ".join(aliases) or None
        keep.merged = count

    def _pairs_to_groups(pairs):
        parent = {}

        def find(x):
            while parent.setdefault(x, x) is not x:
                x = parent[x]
            return x
        for a, b, *_ in pairs:
            ra, rb = find(a), find(b)
            if ra is not rb:
                parent[rb] = ra
        groups = {}
        for x in list(parent):
            groups.setdefault(find(x), []).append(x)
        return [sorted(v, key=lambda n: (n is not k, n._id)) for k, v in groups.items() if len(v) > 1]

    @cmd
    def groupStats(field, top=12, show=True):
        """groupStats(louvain_class) profiles each group of nodes sharing a
        value of a field: size, internal edges, density (internal edges /
        possible pairs), boundary edges (to the rest), conductance (boundary
        / all edges touching the group: low = well separated), and the
        group's most connected member. Prints the largest `top` groups and
        returns a row per group, largest first; a dense, isolated group of
        entities that should be unrelated is a classic red flag."""
        gr = g()
        f = node_field(field, "groupStats")
        groups = {}
        for n in gr._nodes_list():
            v = f.get(n)
            if v is not None:
                groups.setdefault(v, []).append(n)
        rows = []
        for v, members in groups.items():
            ids = {m._id for m in members}
            internal = boundary = 0
            seen = set()
            for m in members:
                for e in m._inc.values():
                    if e._id in seen:
                        continue
                    seen.add(e._id)
                    if e._n1._id in ids and e._n2._id in ids:
                        internal += 1
                    else:
                        boundary += 1
            k = len(members)
            pairs = k * (k - 1) / 2
            vol = 2 * internal + boundary
            hub = max(members, key=lambda m: (len(m._inc), -m._id))
            rows.append({"group": v, "size": k, "internal": internal,
                         "density": internal / pairs if pairs else 0.0, "boundary": boundary,
                         "conductance": boundary / vol if vol else 0.0, "hub": hub,
                         "members": GSet(members, annotation=f"{f.name} == {v!r}")})
        rows.sort(key=lambda r: (-r["size"], str(r["group"])))
        if show:
            print(f"{'group':>14}  {'size':>5}  {'inside':>6}  {'density':>7}  {'boundary':>8}  {'conduct.':>8}  hub")
            for r in rows[:int(top)]:
                gname = str(r["group"])[:14]
                session.say(" " * (14 - len(gname)), (gname, r["members"]),
                            f"  {r['size']:>5}  {r['internal']:>6}  {r['density']:7.2f}  "
                            f"{r['boundary']:>8}  {r['conductance']:8.2f}  ",
                            (str(r["hub"].label or r["hub"].name), [r["hub"]]))
            if len(rows) > top:
                print(f"  … {len(rows) - top} more groups")
        return rows

    @cmd
    def findCycles(maxLength=5, among=None, limit=1000):
        """findCycles(maxLength=5) finds directed cycles (A -> B -> ... -> A)
        of up to maxLength nodes, e.g. money sent round a ring of accounts
        back to where it started. among=nodes restricts the search. Each
        cycle is a set of its nodes and edges (shortest first); at most
        `limit` are returned. Undirected edges count both ways."""
        from .algorithms import _nx
        nx = _nx()
        gr = g()
        keep = None if among is None else {x._id for x in elements_of(among) if isinstance(x, Node)}
        G = nx.DiGraph()
        edge_of = {}
        for e in gr._edges_list():
            a, b = e._n1, e._n2
            if keep is not None and (a._id not in keep or b._id not in keep):
                continue
            G.add_edge(a._id, b._id)
            edge_of.setdefault((a._id, b._id), e)
            if not e._directed:
                G.add_edge(b._id, a._id)
                edge_of.setdefault((b._id, a._id), e)
        out = []
        for cyc in nx.simple_cycles(G, length_bound=int(maxLength)):
            if len(cyc) < 2 or (len(cyc) == 2 and edge_of[(cyc[0], cyc[1])] is edge_of[(cyc[1], cyc[0])]):
                continue        # an undirected edge isn't a cycle
            nodes = [gr._node_ids[i] for i in cyc]
            edges = [edge_of[(a, b)] for a, b in zip(cyc, cyc[1:] + cyc[:1])]
            out.append(GSet(nodes + edges, annotation=" -> ".join(n._name for n in nodes)))
            if len(out) >= int(limit):
                break
        out.sort(key=len)
        session.say((f"{len(out)} cycles", out), f" of up to {maxLength} nodes",
                    " (limit reached)" if len(out) >= int(limit) else "")
        return GSet(out, annotation="cycles")

