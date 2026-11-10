from guess import Session
from tests.test_gython import Recorder


def _s():
    rec = Recorder()
    s = Session(rec)
    s.rec = rec
    return s


def _w(g, a, b):
    for e in g.edges:
        if {e._n1.label, e._n2.label} == {a, b}:
            return e.weight
    return None


def test_make_from_text_terms_units_and_window(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("Alice met Bob. Bob left.\n\nCarol saw Alice.\n\nThe Doctor and Bob talked. Alice too.\n")
    s = _s()
    assert s.run(f"makeFromText({str(p)!r}, {{'Alice': ['Alice'], 'Bob': ['Bob'], 'Carol': ['Carol'], "
                 f"'Dr Who': ['the Doctor', 'Doctor'], 'Nobody': ['Zed']}})"), s.rec.of("error")
    g = s.graph
    assert sorted(n.label for n in g.nodes) == ["Alice", "Bob", "Carol", "Dr Who"]
    assert _w(g, "Alice", "Bob") == 2 and _w(g, "Alice", "Carol") == 1 and _w(g, "Bob", "Carol") is None
    alice = [n for n in g.nodes if n.label == "Alice"][0]
    bob = [n for n in g.nodes if n.label == "Bob"][0]
    assert (alice.count, alice.units, alice.first) == (3, 3, 0) and bob.count == 3 and bob.units == 2
    assert "never found: Nobody" in "".join(m.get("text", "") for m in s.rec.msgs)
    assert s.run(f"makeFromText({str(p)!r}, ['Alice', 'Bob', 'Carol'], by='sentence')")
    assert _w(s.graph, "Alice", "Bob") == 1          # only "Alice met Bob."
    assert s.run(f"makeFromText({str(p)!r}, ['Alice', 'Bob', 'Carol'], window=2)")
    # within 2 words, in the same paragraph: Alice-met-Bob and Bob-talked-Alice; not Bob|Carol
    assert _w(s.graph, "Alice", "Bob") == 2 and _w(s.graph, "Carol", "Alice") == 1
    assert _w(s.graph, "Bob", "Carol") is None


def test_make_from_text_frequent_words(tmp_path):
    p = tmp_path / "w.txt"
    p.write_text(("graph layout graph drawing the of and\n\n" * 4) + "layout tree\n")
    s = _s()
    assert s.run(f"makeFromText({str(p)!r}, minCount=4, maxTerms=10)")
    assert sorted(n.label for n in s.graph.nodes) == ["drawing", "graph", "layout"]   # stopwords dropped
    assert _w(s.graph, "graph", "layout") == 4


def test_make_from_two_mode(tmp_path):
    p = tmp_path / "pa.csv"
    p.write_text("paper,author,n\np1,ann,1\np1,bo,2\np2,ann,1\np2,ann,1\n")
    s = _s()
    assert s.run(f"makeFromTwoMode({str(p)!r}, 'paper', 'author', weight='n')"), s.rec.of("error")
    g = s.graph
    kinds = sorted((n.label, n.kind) for n in g.nodes)
    assert kinds == [("ann", "author"), ("bo", "author"), ("p1", "paper"), ("p2", "paper")]
    assert _w(g, "p2", "ann") == 2.0 and _w(g, "p1", "bo") == 2.0
    assert s.run("project(kind, 'author')") and len(s.graph.edges) == 1


def test_make_from_similarity(tmp_path):
    wide = tmp_path / "wide.csv"
    wide.write_text("Id,group,a,b,c\nx,one,1,0,0\ny,one,0.9,0.1,0\nz,two,0,0,1\nw,two,0,0.1,0.9\n")
    s = _s()
    assert s.run(f"makeFromSimilarity({str(wide)!r}, k=1)"), s.rec.of("error")
    g = s.graph
    pairs = sorted(tuple(sorted((e._n1.label, e._n2.label))) for e in g.edges)
    assert pairs == [("w", "z"), ("x", "y")]
    assert g.getNodeByName("x").group == "one"          # text columns become fields
    assert s.run(f"makeFromSimilarity({str(wide)!r}, threshold=0.99, method='cosine')")
    assert len(s.graph.edges) == 0 or all(e.weight >= 0.99 for e in s.graph.edges)
    long = tmp_path / "long.csv"
    long.write_text("doc,term,score\nd1,cat,1\nd1,dog,1\nd2,cat,1\nd2,dog,1\nd3,fish,1\n")
    assert s.run(f"makeFromSimilarity({str(long)!r}, features='term', values='score', method='jaccard', threshold=0.5)")
    assert [tuple(sorted((e._n1.label, e._n2.label))) for e in s.graph.edges] == [("d1", "d2")]
    assert not s.run(f"makeFromSimilarity({str(wide)!r}, method='magic')")


def test_main_path():
    s = _s()
    # a citation DAG: two recent papers cite through b, which cites the classic a
    for x, y in (("c1", "b"), ("c2", "b"), ("b", "a"), ("c1", "a"), ("d", "e")):
        s.run(f"addDirectedEdge(addNode({x!r}), addNode({y!r}))")
    assert s.run("__mp = mainPath()"), s.rec.of("error")
    names = [x.name for x in s.ns["__mp"] if hasattr(x, "_inc")]
    assert names[-2:] == ["b", "a"] and names[0] in ("c1", "c2")
    g = s.graph
    spc = {(e._n1.name, e._n2.name): e.spc for e in g.edges}
    # paths source->sink: c1-b-a, c2-b-a, c1-a, d-e = 4; b->a carries 2
    assert spc[("b", "a")] == 0.5 and spc[("c1", "a")] == 0.25 and spc[("d", "e")] == 0.25
