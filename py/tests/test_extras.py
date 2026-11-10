import json

from guess import Session
from tests.test_gython import Recorder


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    return s


def _path(s, n):
    for i in range(n - 1):
        s.run(f"addEdge(addNode('p{i}'), addNode('p{i + 1}'))")


def test_spread_models():
    s = _s()
    _path(s, 6)
    assert s.run("__c = spread([p0], 'SI', beta=1.0)"), s.rec.of("error")
    g = s.graph
    assert [g.getNodeByName(f"p{i}").infected_at for i in range(6)] == [0, 1, 2, 3, 4, 5]
    assert s.ns["__c"][-1][2] == 6                 # everyone infected
    assert s.run("spread([p0], 'SIR', beta=1.0, gamma=1.0)")
    assert all(n.state == "R" for n in g.nodes)     # infected then recovered, every step
    assert s.run("spread([p0], 'threshold', threshold=0.6)")
    # p1 has 2 neighbours, 1 infected: 0.5 < 0.6, so nothing spreads
    assert sorted(n.name for n in g.nodes if n.infected_at >= 0) == ["p0"]
    assert s.run("spread([p0], 'cascade', beta=0.0)")
    assert sorted(n.name for n in g.nodes if n.infected_at >= 0) == ["p0"]
    assert not s.run("spread([p0], 'zombie')")


def test_motifs_and_collapse():
    s = _s()
    for leaf in "abc":
        s.run(f"addEdge(addNode('hub'), addNode({leaf!r}))")
    for m in ("x", "y"):                      # x and y both link to only hub and k
        s.run(f"addEdge(addNode({m!r}), hub); addEdge({m}, addNode('k'))")
    assert s.run("__f = findMotifs('fan', 3)")
    assert [sorted(n.name for n in grp) for grp in s.ns["__f"]] == [["a", "b", "c"]]
    assert s.run("__c = findMotifs('connector', 2)")
    assert [sorted(n.name for n in grp) for grp in s.ns["__c"]] == [["x", "y"]]
    assert s.run("collapseMotifs('fan', 3)")
    assert "a" not in [n.name for n in s.graph.nodes] and len(s.graph.nodes) == 5


def test_report(tmp_path):
    s = _s()
    _path(s, 4)
    assert s.run("__t = report()")
    text = s.ns["__t"]
    assert "4 nodes, 3 edges" in text and "| diameter | 3 |" in text and "**Most between:**" in text
    out = tmp_path / "r.html"
    assert s.run(f"report({str(out)!r})")
    page = out.read_text()
    assert page.startswith("<!doctype html>") and "<th>diameter</th><td>3</td>" in page


def test_rich_club_and_routing():
    s = _s()
    # two triangles joined by a path: a-b-c, c-d, d-e-f
    for a, b in (("a", "b"), ("b", "c"), ("a", "c"), ("c", "d"), ("d", "e"), ("e", "f"), ("d", "f")):
        s.run(f"addEdge(addNode({a!r}), addNode({b!r}))")
    assert s.run("__r = richClub(normalized=False, show=False)")
    assert s.ns["__r"][2] == 1.0                    # nodes of degree > 2 (c, d) are linked
    s.run("for e in g.edges: e.weight = 1")
    s.run("(c <-> d).weight = 10")
    s.run("addEdge(b, e).weight = 2")
    assert s.run("__cost = minCostFlow(a, f, 1, capacity=None)"), s.rec.of("error")
    assert s.ns["__cost"] == 4.0                    # a-b-e-f (1 + 2 + 1), not through c-d
    assert s.run("__t = travelingSalesman([a, f], cycle=False)")
    t = s.ns["__t"]
    assert t.length == 4.0 and [x.name for x in t if hasattr(x, "_inc")] == ["a", "b", "e", "f"]


def test_embed_groups_structure():
    s = _s()
    # two cliques joined by one edge: embeddings should separate them
    for side in "LR":
        for i in range(5):
            for j in range(i + 1, 5):
                s.run(f"addEdge(addNode('{side}{i}'), addNode('{side}{j}'))")
    s.run("addEdge(L0, R0)")
    assert s.run("__f = embed(2, walks=20, seed=1)"), s.rec.of("error")
    g = s.graph
    import math
    def vec(n):
        return [g.getNodeByName(n).emb0, g.getNodeByName(n).emb1]
    def dist(a, b):
        return math.dist(vec(a), vec(b))
    assert dist("L1", "L2") < dist("L1", "R2")


def test_wikipedia_and_openalex_offline(monkeypatch):
    from guess import connectors
    pages = {"Graph drawing": ["Planar graph", "Force-directed graph drawing", "Doi (identifier)"],
             "Planar graph": ["Graph drawing"], "Force-directed graph drawing": ["Planar graph", "Graph drawing"]}
    works = {"results": [
        {"id": "https://openalex.org/W1", "title": "New", "publication_year": 2020, "cited_by_count": 5,
         "referenced_works": ["https://openalex.org/W2"], "authorships": [{"author": {"display_name": "Ann Lee"}}],
         "primary_location": {"source": {"display_name": "Venue"}}},
        {"id": "https://openalex.org/W2", "title": "Old", "publication_year": 1990, "cited_by_count": 50,
         "referenced_works": [], "authorships": [{"author": {"display_name": "Bo Chan"}}], "primary_location": None}]}

    def fake(url, *a, **k):
        import urllib.parse
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        if "wikipedia" in url:
            titles = q["titles"].split("|")
            return json.dumps({"query": {"pages": {str(i): {"title": t, "links": [{"title": x} for x in pages.get(t, [])]}
                                                   for i, t in enumerate(titles)}}})
        return json.dumps(works if q.get("page") == "1" else {"results": []})
    monkeypatch.setattr(connectors, "http", fake)
    s = _s()
    assert s.run("makeFromWikipedia('Graph drawing')"), s.rec.of("error")
    g = s.graph
    assert sorted(n.label for n in g.nodes) == ["Force-directed graph drawing", "Graph drawing", "Planar graph"]
    assert len(g.edges) == 5
    assert s.run("makeFromOpenAlex('graphs', limit=5)"), s.rec.of("error")
    g = s.graph
    assert sorted((n.name, n.year) for n in g.nodes) == [("W1", 2020), ("W2", 1990)]
    assert [(e._n1.name, e._n2.name) for e in g.edges] == [("W1", "W2")]
    assert s.run("makeFromOpenAlex('graphs', mode='authors')")
    assert sorted(n.kind for n in s.graph.nodes) == ["author", "author", "paper", "paper"]


def test_round_trip_starts_at_first_stop():
    s = _s()
    for a, b in (("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")):
        s.run(f"addEdge(addNode({a!r}), addNode({b!r}))")
    assert s.run("__t = travelingSalesman([c, a, b, d])")
    names = [x.name for x in s.ns["__t"] if hasattr(x, "_inc")]
    assert names[0] == names[-1] == "c" and sorted(set(names)) == ["a", "b", "c", "d"]
