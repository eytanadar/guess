

def test_project_bipartite(tmp_path):
    from tests.test_gython import Recorder
    from guess import Session
    rec = Recorder()
    s = Session(rec)
    # two people share two clubs; a third shares one of them; a fourth is alone
    s.run("addNodeField('kind', VARCHAR, None)")
    for n in ("ann", "bo", "cy", "di"):
        s.run(f"addNode({n!r}).kind = 'person'")
    for n in ("chess", "choir"):
        s.run(f"addNode({n!r}).kind = 'club'")
    for a, b in (("ann", "chess"), ("bo", "chess"), ("ann", "choir"), ("bo", "choir"), ("cy", "choir")):
        s.run(f"addEdge({a}, {b})")
    rec.clear()
    assert s.run("project(kind, 'person')"), rec.of("error")
    g = s.graph
    assert sorted(n.name for n in g.nodes) == ["ann", "bo", "cy", "di"]
    w = {tuple(sorted((e._n1.name, e._n2.name))): (e.shared, e.weight) for e in g.edges}
    assert w == {("ann", "bo"): (2, 2.0), ("ann", "cy"): (1, 1.0), ("bo", "cy"): (1, 1.0)}
    assert g.getNodeByName("ann").affiliations == 2 and g.getNodeByName("di").affiliations == 0
    assert "use('main')" in "".join(m.get("text", "") for m in rec.msgs)
    s.run("use('main'); project(kind, 'person', 'jaccard')")
    w = {tuple(sorted((e._n1.name, e._n2.name))): e.weight for e in s.graph.edges}
    assert w[("ann", "bo")] == 1.0 and w[("ann", "cy")] == 0.5
    s.run("use('main'); project(kind, 'club', 'newman')")
    (e,) = list(s.graph.edges)
    assert e.shared == 2 and abs(e.weight - 2.0) < 1e-9      # ann and bo are each in 2 clubs: 1/(2-1) each
    rec.clear()
    assert not s.run("project(kind, 'robot')")
    assert "no nodes have kind == 'robot'" in rec.of("error")[0]["text"]


def test_subgraph_and_show_only_keep_what_is_selected():
    from tests.test_gython import Recorder
    from guess import Session
    s = Session(Recorder())
    for a, b, w in (("a", "b", 5), ("b", "c", 1), ("a", "c", 5), ("c", "d", 5)):
        s.run(f"addEdge(addNode({a!r}), addNode({b!r})).weight = {w}")
    names = lambda g: (sorted(n.name for n in g.nodes), sorted("".join(sorted((e._n1.name, e._n2.name))) for e in g.edges))  # noqa: E731
    # edges select exactly those edges (b-c isn't heavy, though b and c are both endpoints)
    assert s.run("subgraph(weight > 2, 'heavy')")
    assert names(s.graph) == (["a", "b", "c", "d"], ["ab", "ac", "cd"])
    s.run("use('main')")
    assert s.run("subgraph(weight > 2, 'all', induced=true)")
    assert names(s.graph)[1] == ["ab", "ac", "bc", "cd"]
    s.run("use('main')")
    # nodes: the induced subgraph, as before
    assert s.run("subgraph((a, b, c), 'abc')")
    assert names(s.graph) == (["a", "b", "c"], ["ab", "ac", "bc"])
    s.run("use('main')")
    # a mixed set (a path) keeps only the path's edges, in subgraph and showOnly
    assert s.run("p = shortestPath(b, d)")
    assert s.run("showOnly(p)")
    vis = sorted("".join(sorted((e._n1.name, e._n2.name))) for e in s.graph.edges if e.visible)
    assert vis == ["bc", "cd"]
    assert s.run("showOnly(p, induced=true)")
    vis = sorted("".join(sorted((e._n1.name, e._n2.name))) for e in s.graph.edges if e.visible)
    assert vis == ["bc", "cd"]          # b, c, d: no other edges among them
    assert s.run("showOnly((a, b, c))")
    assert sum(e.visible for e in s.graph.edges) == 3
