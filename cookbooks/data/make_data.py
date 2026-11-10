"""Regenerate the cookbook datasets that come from networkx's bundled copies
of classic, freely available networks. Each is written through GUESS itself
(fromNetworkX + exportGDF), so the files are known to load.

    cd py && .venv/bin/python ../cookbooks/data/make_data.py

Sources and licences are in cookbooks/data/README.md.
"""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "py"))
import networkx as nx  # noqa: E402
from guess import Session  # noqa: E402


def ident(s):
    """A node name GUESS can bind as a variable: letters, digits, underscore."""
    s = re.sub(r"[^0-9A-Za-z_]+", "_", str(s)).strip("_")
    return s if s and not s[0].isdigit() else "n" + s


def relabel(G, name):
    """Rename nodes to identifiers; the original goes in `label`."""
    mapping = {v: name(v) for v in G}
    assert len(set(mapping.values())) == len(mapping), "names collide"
    H = nx.relabel_nodes(G, mapping)
    for old, new in mapping.items():
        H.nodes[new].setdefault("label", str(old))
    return H


def karate():
    G = nx.karate_club_graph()
    H = relabel(G, lambda v: f"m{v + 1}")
    for v in H:
        H.nodes[v]["label"] = v[1:]
        H.nodes[v]["club"] = "Mr Hi" if H.nodes[v]["club"] == "Mr. Hi" else "Officer"
    return H


def florentine():
    return relabel(nx.florentine_families_graph(), ident)


def southern_women():
    G = nx.davis_southern_women_graph()
    H = relabel(G, lambda v: ident(v.split()[0]) if G.nodes[v]["bipartite"] == 0 else v)
    for v in H:
        b = H.nodes[v].pop("bipartite")
        H.nodes[v]["kind"] = "woman" if b == 0 else "event"
    return H


def lesmis():
    return relabel(nx.les_miserables_graph(), ident)


DATASETS = {"karate": karate, "florentine": florentine,
            "southern-women": southern_women, "lesmis": lesmis}


def main(names):
    s = Session(lambda m: print(m.get("text", "").rstrip()) if m.get("type") == "error" else None)
    for name in names or DATASETS:
        G = DATASETS[name]()
        s.ns["__G__"] = G
        assert s.run("fromNetworkX(__G__)"), name
        out = HERE / f"{name}.gdf"
        assert s.run(f"exportGDF({str(out)!r})"), name
        print(f"  {out.relative_to(ROOT)}: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")


if __name__ == "__main__":
    os.chdir(HERE)
    main(sys.argv[1:])
