"""Make the datasets taken from Mark Newman's network data page
(websites.umich.edu/~mejn/netdata/): small pieces of large networks, sized
for interactive use in the browser, with positions precomputed.

    cd py && .venv/bin/python ../cookbooks/data/make_newman.py [download-folder]

The zips are downloaded into download-folder (default: a temporary folder)
unless they are already there. Sources and citations: README.md.
"""
import os
import random
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "py"))
import networkx as nx  # noqa: E402
from guess import Session  # noqa: E402

BASE = "https://websites.umich.edu/~mejn/netdata/"


def fetch(name, folder):
    """The GML inside name.zip (downloaded once into folder)."""
    z = Path(folder) / f"{name}.zip"
    if not z.exists():
        req = urllib.request.Request(BASE + z.name, headers={"User-Agent": "Mozilla/5.0 (dataset script)"})
        with urllib.request.urlopen(req) as r:
            z.write_bytes(r.read())
    with zipfile.ZipFile(z) as zf:
        gml = next(n for n in zf.namelist() if n.endswith(".gml"))
        return nx.parse_gml(zf.read(gml).decode("utf-8", "replace").splitlines(), label="id")


def scaled(pos, span=900.0):
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    x0, y0 = min(xs), min(ys)
    k = span / max(max(xs) - x0, max(ys) - y0, 1e-9)
    return {v: ((p[0] - x0) * k, (p[1] - y0) * k) for v, p in pos.items()}


def power_region(folder, size=400):
    """A connected piece of the Western US power grid: the first `size`
    stations reached breadth-first from station 2000 (a node inside the grid,
    away from its fringe), laid out by Kamada-Kawai (GUESS's kkLayout),
    which suits a nearly planar network like a grid."""
    G = fetch("power", folder)
    order = list(nx.bfs_tree(G, 2000))[:size]
    H = nx.Graph(G.subgraph(order))
    out = nx.Graph()
    out.graph["layout"] = "kkLayout(900, 900)"
    for v in H:
        out.add_node(f"s{v}", label=str(v))
    out.add_edges_from((f"s{a}", f"s{b}") for a, b in H.edges())
    return out


def as_sample(folder, size=300, seed=7):
    """About `size` autonomous systems snowball-sampled from the 2006 snapshot:
    from a mid-sized AS, each AS reached adds up to four random neighbours,
    breadth-first; the result keeps every link among the sampled ASes."""
    G = fetch("as-22july06", folder)
    rnd = random.Random(seed)
    asn = {v: str(G.nodes[v].get("label", v)) for v in G}
    start = sorted((v for v in G if G.degree(v) == 12), key=lambda v: int(asn[v]))[0]
    seen, queue = [start], [start]
    while queue and len(seen) < size:
        v = queue.pop(0)
        nb = sorted(G[v], key=lambda u: int(asn[u]))
        rnd.shuffle(nb)
        for u in nb[:4]:
            if u not in seen and len(seen) < size:
                seen.append(u)
                queue.append(u)
    H = nx.Graph(G.subgraph(seen))
    pos = scaled(nx.spring_layout(H, seed=seed, iterations=300))
    out = nx.Graph()
    for v in H:
        out.add_node(f"AS{asn[v]}", label=asn[v], asn=int(asn[v]), fulldegree=G.degree(v), pos=pos[v])
    out.add_edges_from((f"AS{asn[a]}", f"AS{asn[b]}") for a, b in H.edges())
    return out


DATASETS = {"power-grid-region": power_region, "internet-as-sample": as_sample}


def main(folder, names):
    s = Session(lambda m: print(m.get("text", "").rstrip()) if m.get("type") == "error" else None)
    for name in names or DATASETS:
        G = DATASETS[name](folder)
        s.ns["__G__"] = G
        assert s.run("fromNetworkX(__G__)"), name
        if G.graph.get("layout"):
            assert s.run(G.graph["layout"]), name
        out = HERE / f"{name}.gdf"
        assert s.run(f"exportGDF({str(out)!r})"), name
        print(f"  {out.relative_to(ROOT)}: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")


if __name__ == "__main__":
    args = sys.argv[1:]
    folder = args.pop(0) if args and Path(args[0]).is_dir() else tempfile.mkdtemp()
    os.chdir(HERE)
    main(folder, args)
