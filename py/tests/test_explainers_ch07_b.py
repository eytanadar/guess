"""Batch 4 explainers: closeness and betweenness, and groups (cliques, cores, k-components)."""
import networkx as nx

from tests.test_explainers import App, _in_data_folder  # noqa: F401  (the fixture runs in the data folder)


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def _tab(a, title):
    a.s.dispatch(_tabs(a)._id, "change", title)
    assert not a.errors(), a.errors()


def test_closeness_betweenness():
    a = App("ch07-closeness-betweenness")
    assert "Valjean" in a.markdown() and "Harmonic" in a.markdown()
    a.press("Most peripheral")
    assert a.ev("centre[0]") == min(a["CLOSE"], key=lambda v: a["CLOSE"][v])
    a.click("Javert")
    assert a.node("Valjean").label == "1" and a.ev("close_chart()") is not None
    _tab(a, "Paths through a node")
    a.click("Napoleon")
    a.click("Gavroche")
    paths = list(nx.all_shortest_paths(a["G0"], "Napoleon", "Gavroche"))
    assert f"**{len(paths)}** shortest path" in a.markdown()
    assert a.node("Myriel").label.startswith("Myriel · ")          # Napoleon's only neighbour
    assert any(e.linestyle == "flow" for e in a.s.graph._edges_list())
    _tab(a, "Adding up")
    a.press("Add up over all pairs")
    a.tick(5)
    assert a.ev("acc['i']") == 5 and a.ev("acc_chart()") is not None
    a.press("All at once")
    assert "exactly the betweenness" in a.markdown() and "mismatch" not in a.markdown()
    a.press("Reset")
    assert a.ev("acc['i']") == 0
    _tab(a, "Brokers")
    assert a.ev("len(brokers())") >= 1 and "**Red**" in a.markdown()
    a.press("Remove the top broker")
    assert "Valjean" in a.ev("removed") and "pieces" in a.markdown()
    a.press("Restore")
    assert len(a.s.graph._nodes_list()) == 77
    assert a.ev("broker_chart()") is not None


def test_groups():
    a = App("ch07-groups")
    G0, core = a["G0"], a["CORE"]
    a.press("Peel")
    a.tick(3)
    assert len(a.ev("peel['gone']")) == 3 and a.ev("peel_chart()") is not None
    a.press("All at once")
    k = int(a.ev("kslider.value"))
    left = [v for v in G0 if v not in set(a.ev("peel['gone']"))]
    assert sorted(left) == sorted(v for v in G0 if core[v] >= k)
    assert f"{k}-core" in a.markdown()
    a.set("slider", "k", a["KMAX"] + 1)
    a.press("All at once")
    assert "no " in a.markdown() and len(a.ev("peel['gone']")) == len(G0)
    a.press("Colour by core")
    _tab(a, "Cliques")
    a.press("Next clique")
    c = a.ev("CLIQUES[0]")
    assert all(G0.has_edge(u, v) for u in c for v in c if u != v) and "Clique 1 of" in a.markdown()
    a.press("The largest")
    assert "largest cliques have" in a.markdown()
    _tab(a, "k-components")
    for b in ("Components", "Bicomponents", "Tricomponents", "All three, nested"):
        a.press(b)
    a.press("Bicomponents")
    assert "cut nodes" in a.markdown()
    a.press("Tricomponents")
    assert "3-core" in a.markdown()
    _tab(a, "Core ≠ component")
    assert len(a.s.graph._nodes_list()) == 10
    a.press("The 2-core")
    assert "One 2-core" in a.markdown()
    a.press("The 2-components")
    assert a.ev("len(kComponents(2))") == 2 and "Two 2-components" in a.markdown()
    _tab(a, "k-cores")
    assert len(a.s.graph._nodes_list()) == 62
