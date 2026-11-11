"""More clustering: Chinese Whispers, MCL, DBSCAN, MCODE, clique percolation,
link communities and showOverlaps."""
import numpy as np

from guess.moreclusters import dbscan, knee_eps
from tests.test_gython import Recorder, ev, s  # noqa: F401  (fixture)


def two_cliques(sess, size=5, bridge=True):
    """Two cliques a0..a4 and b0..b4, joined by the edge a0-b0."""
    code = ["newGraph('cliques')"]
    for p in "ab":
        for i in range(size):
            code.append(f"addNode('{p}{i}')")
        for i in range(size):
            for j in range(i + 1, size):
                code.append(f"addEdge({p}{i}, {p}{j})")
    if bridge:
        code.append("addEdge(a0, b0)")
    assert sess.run("\n".join(code)), sess.rec.of("error")


def classes(sess, field):
    return {n._name: n._vals.get(field) for n in sess.graph._nodes_list()}


def same_split(c):
    """a* share one class, b* another."""
    a = {v for k, v in c.items() if k.startswith("a")}
    b = {v for k, v in c.items() if k.startswith("b")}
    return len(a) == 1 and len(b) == 1 and a != b


def test_chinese_whispers_splits_two_cliques(s):
    two_cliques(s)
    out = ev(s, "chineseWhispersClusters()")
    assert len(out) == 2
    assert same_split(classes(s, "cw_class"))
    assert sorted(classes(s, "cw_class").values()) == [0] * 5 + [1] * 5


def test_mcl_splits_two_cliques_and_undo(s):
    two_cliques(s)
    assert s.run("mclClusters()"), s.rec.of("error")
    assert same_split(classes(s, "mcl_class"))
    assert s.run("undo()")
    assert "mcl_class" not in s.graph.node_schema


def test_mcl_rejects_bad_inflation(s):
    two_cliques(s)
    assert not s.run("mclClusters(inflation=1)")
    assert "inflation" in s.rec.of("error")[-1]["text"]


def test_dbscan_finds_planted_blobs_and_noise(s):
    rng = np.random.default_rng(1)
    code = ["newGraph('blobs')"]
    pts = [(100, 100), (600, 600)]
    k = 0
    for cx, cy in pts:
        for _ in range(30):
            x, y = rng.normal(cx, 10), rng.normal(cy, 10)
            code.append(f"addNode('p{k}', x={x:.2f}, y={y:.2f})")
            k += 1
    code.append("addNode('lonely', x=1000, y=50)")
    assert s.run("\n".join(code)), s.rec.of("error")
    out = ev(s, "dbscanClusters()")
    assert len(out) == 2 and sorted(map(len, out)) == [30, 30]
    c = classes(s, "dbscan_class")
    assert c["lonely"] == -1
    assert {c[f"p{i}"] for i in range(30)} != {c[f"p{i}"] for i in range(30, 60)}
    assert "eps =" in "".join(m.get("text", "") for m in s.rec.of("text"))


def test_dbscan_on_other_fields(s):
    assert s.run("makeSample('karate')"), s.rec.of("error")
    out = ev(s, "dbscanClusters((degree,), eps=0.5, minPts=3)")
    # each degree value shared by >= 3 nodes is a cluster of that value
    for c in out:
        assert len({n.degree for n in c}) == 1


def test_dbscan_helpers():
    X = np.array([[0, 0], [0, 1], [1, 0], [10, 10], [10, 11], [11, 10], [50, 50]], float)
    lab = dbscan(X, 1.5, 3)
    assert lab[0] == lab[1] == lab[2] != lab[3] == lab[4] == lab[5]
    assert lab[6] == -1
    assert 1 <= knee_eps(X, 2) <= 60


def test_mcode_finds_planted_dense_region(s):
    # a 6-clique with a sparse tree hanging off it
    code = ["newGraph('mcode')"]
    for i in range(6):
        code.append(f"addNode('c{i}')")
    for i in range(6):
        for j in range(i + 1, 6):
            code.append(f"addEdge(c{i}, c{j})")
    for i in range(8):
        code.append(f"addNode('t{i}')")
        code.append(f"addEdge({'c0' if i < 2 else f't{i // 2 - 1}'}, t{i})")
    assert s.run("\n".join(code)), s.rec.of("error")
    out = ev(s, "mcodeClusters()")
    assert len(out) >= 1
    best = {n.name for n in out[0]}
    assert best == {f"c{i}" for i in range(6)}
    c = classes(s, "mcode_class")
    assert all(c[f"c{i}"] == 0 for i in range(6))
    assert all(c[f"t{i}"] == -1 for i in range(8))
    assert classes(s, "mcode_score")["c1"] > classes(s, "mcode_score")["t5"]


def test_clique_percolation_overlaps(s):
    # two 4-cliques sharing node x (k=3: two communities, x in both)
    code = ["newGraph('cpm')"]
    for n in ["a1", "a2", "a3", "b1", "b2", "b3", "x", "lone"]:
        code.append(f"addNode('{n}')")
    for grp in (["a1", "a2", "a3", "x"], ["b1", "b2", "b3", "x"]):
        for i in range(4):
            for j in range(i + 1, 4):
                code.append(f"addEdge({grp[i]}, {grp[j]})")
    code.append("addEdge(lone, a1)")
    assert s.run("\n".join(code)), s.rec.of("error")
    out = ev(s, "cliquePercolationClusters(3)")
    assert len(out) == 2
    c = classes(s, "cpm_classes")
    assert sorted(c["x"].split(";")) == ["0", "1"]
    assert c["lone"] == ""
    assert classes(s, "cpm_count")["x"] == 2
    # shown as pies: x has two slices, a1 none (plain colour)
    s.rec.clear()
    assert s.run("showOverlaps(cpm_classes)"), s.rec.of("error")
    s.flush()
    recs = {r["name"]: r for m in s.rec.of("patch") + s.rec.of("scene") for r in m["nodes"]}
    assert recs["x"]["p"] == [1, 1]
    assert sum(recs["a1"]["p"]) == 0
    assert s.rec.of("overlay")[-1]["pie"] and len(s.rec.of("overlay")[-1]["pie"]) == 2
    assert s.graph._nodes["lone"]._vals["color"] == "lightgray"
    # one undo step takes it all back
    assert s.run("undo()")
    assert s.view.pie is None


def test_show_overlaps_takes_the_result_and_hulls(s):
    two_cliques(s)
    assert s.run("cs = cliquePercolationClusters(4)\nshowOverlaps(cs, hulls=true)"), s.rec.of("error")
    assert len(s.view.hulls) == 2
    assert s.run("removePies()")
    assert s.view.pie is None


def test_link_communities_on_two_cliques(s):
    two_cliques(s)
    out = ev(s, "linkCommunities()")
    assert len(out) == 2
    names = sorted(sorted(n.name for n in c) for c in out)
    assert names[0][:5] == [f"a{i}" for i in range(5)]
    ec = {repr(e): e._vals.get("link_class") for e in s.graph._edges_list()}
    assert ec["a0-b0"] == -1                      # the bridge is a community of one edge
    assert len({v for k, v in ec.items() if k.startswith("a") and "b" not in k}) == 1
    # the bridge's ends are in their own clique's community only
    assert classes(s, "link_count")["a0"] == 1


def test_link_communities_karate_overlap(s):
    assert s.run("makeSample('karate')"), s.rec.of("error")
    out = ev(s, "linkCommunities()")
    assert len(out) >= 2
    assert max(classes(s, "link_count").values()) >= 2     # some members belong to several
    assert s.run("showOverlaps(link_classes)"), s.rec.of("error")
