"""Tests for guess.layouts (ports of the GUESS / JUNG layouts)."""
import json
import math
import pathlib

import numpy as np
import pytest

from guess import Session, layouts

SAMPLE = pathlib.Path(__file__).resolve().parents[2] / "gdfs" / "sample.gdf"

# every command with arguments valid on sample.gdf (v1 exists there)
SAMPLE_COMMANDS = [
    "randomLayout()", "randomLayout(400, 300)",
    "circleLayout()", "circleLayout(freq, v1)", "circleLayout(dept, v1, 100, 100)",
    "frLayout()", "frLayout(800, 600)", "jfrLayout()",
    "kkLayout()", "kkLayout(800, 600)", "jkkLayout1()", "jkkLayout2()", "weightedKKLayout()",
    "springLayout()", "springLayout(30)", "jSpringLayout()", "jSpringLayout(30)",
    "weightedSpringLayout(10, 100)", "weightedSpringLayout(10, 100, 30)",
    "gemLayout()", "gemLayout(3)", "isomLayout()", "isomLayout(300)",
    "physicsLayout()", "physicsLayout(40)", "radialLayout(v1)", "mdsLayout()",
    "sugiyamaLayout()", "sugiyamaLayout(true)", "sugiyamaLayout2()", "dagLayout()",
    "binPackLayout()", "binPackLayout(false)",
    "rescaleLayout(0.5)", "rescaleLayout(0.5, 2.0)", "rescaleLayout(500, 400)",
    "translateLayout(25, -10)", "moveLayout(0, 0)",
]

ALL_NAMES = [
    "randomLayout", "circleLayout", "frLayout", "jfrLayout", "kkLayout", "jkkLayout1",
    "jkkLayout2", "weightedKKLayout", "springLayout", "jSpringLayout", "weightedSpringLayout",
    "gemLayout", "isomLayout", "physicsLayout", "radialLayout", "mdsLayout", "sugiyamaLayout",
    "sugiyamaLayout2", "dagLayout", "binPackLayout", "rescaleLayout", "translateLayout",
    "moveLayout", "centerAfterLayout",
]


class Recorder:
    def __init__(self):
        self.msgs = []

    def __call__(self, msg):
        json.dumps(msg)
        self.msgs.append(msg)

    def of(self, kind):
        return [m for m in self.msgs if m["type"] == kind]


def make_session():
    rec = Recorder()
    sess = Session(rec)
    layouts.install(sess)
    sess.rec = rec
    return sess


def run(sess, src):
    sess.rec.msgs.clear()
    ok = sess.run(src)
    assert ok, sess.rec.of("error")


def positions(sess):
    return np.array([[n.x, n.y] for n in sess.graph._nodes_list()], float)


def pos_of(sess, name):
    n = sess.graph.getNodeByName(name)
    return np.array([n.x, n.y])


@pytest.fixture(scope="module")
def sample_text():
    if not SAMPLE.exists():
        pytest.skip("sample.gdf missing")
    return SAMPLE


def sample_session():
    sess = make_session()
    run(sess, f"makeFromGDF({str(SAMPLE)!r})")
    return sess


# ---------------------------------------------------------------------------
# every command on sample.gdf
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", SAMPLE_COMMANDS)
def test_command_on_sample(sample_text, cmd):
    sess = sample_session()
    g = sess.graph
    pinned = ["v2", "v10", "v123", "v298"]
    for name in pinned:
        g.getNodeByName(name).fixed = True
    before = {name: pos_of(sess, name) for name in pinned}
    start = positions(sess)
    run(sess, cmd)
    P = positions(sess)
    assert np.isfinite(P).all()
    for name in pinned:
        assert np.array_equal(pos_of(sess, name), before[name]), (cmd, name)
    moved = (P != start).any(1)
    assert moved.any(), f"{cmd} moved nothing"
    # moves go through attribute assignment, so they show up as patches
    patched = {r["i"] for m in sess.rec.of("patch") for r in m["nodes"]}
    patched |= {i for m in sess.rec.of("patch") for i in m.get("pos", [])[::3]}
    ids = [n._id for n in g._nodes_list()]
    assert {ids[i] for i in np.flatnonzero(moved)} <= patched
    assert sess.rec.of("center"), "view should re-centre after a layout"


def test_all_commands_registered_with_help():
    sess = make_session()
    for name in ALL_NAMES:
        fn = sess.ns[name]
        assert fn.__doc__ and fn.__doc__.strip(), name
        assert sess.is_protected(name)
    sess.rec.msgs.clear()
    run(sess, "help(circleLayout)")
    text = "".join(m["text"] for m in sess.rec.of("text"))
    assert "circleLayout(field=None, center=None, x=None, y=None)" in text
    assert "centerNode" in text


def test_wrong_argument_counts_are_errors():
    sess = make_session()
    run(sess, "addNode('a'); addNode('b'); addEdge(a, b)")
    for bad in ("randomLayout(5)", "circleLayout(1)", "circleLayout(x, a, 5)",
                "frLayout(5)", "kkLayout(5)", "rescaleLayout()", "rescaleLayout(1, 2, 3)"):
        assert not sess.run(bad), bad


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------

def build(sess, nodes, edges=(), directed=False, same_pos=False):
    g = sess.graph
    for i, name in enumerate(nodes):
        n = g.addNode(name)
        if same_pos:
            n.x, n.y = 500.0, 500.0
        else:
            n.x, n.y = 37.0 * i % 300, 91.0 * i % 280
    for a, b in edges:
        g.addEdge(a, b, directed)


EDGE_CASES = {
    "empty": dict(nodes=[]),
    "single": dict(nodes=["a"]),
    "single_selfloop": dict(nodes=["a"], edges=[("a", "a"), ("a", "a")]),
    "two_isolated": dict(nodes=["a", "b"]),
    "pair": dict(nodes=["a", "b"], edges=[("a", "b")]),
    "multi_and_loops": dict(nodes=["a", "b", "c"],
                            edges=[("a", "b"), ("a", "b"), ("b", "a"), ("b", "b"), ("c", "c")]),
    "disconnected": dict(nodes=list("abcdefg"),
                         edges=[("a", "b"), ("b", "c"), ("c", "a"), ("d", "e")]),
    "coincident": dict(nodes=list("abcdef"),
                       edges=[("a", "b"), ("b", "c"), ("d", "e")], same_pos=True),
    "directed_cycle": dict(nodes=list("abcd"),
                           edges=[("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("d", "d")],
                           directed=True),
}

EDGE_CASE_COMMANDS = [
    "randomLayout()", "circleLayout()", "frLayout()", "jfrLayout()", "kkLayout()",
    "jkkLayout1()", "jkkLayout2()", "weightedKKLayout()", "springLayout(40)", "springLayout()",
    "jSpringLayout(40)", "weightedSpringLayout(10, 50, 40)", "gemLayout(1)", "isomLayout(200)",
    "physicsLayout(40)", "mdsLayout()", "sugiyamaLayout()", "sugiyamaLayout(true)",
    "sugiyamaLayout2()", "dagLayout()", "binPackLayout()", "rescaleLayout(0.5)",
    "rescaleLayout(100, 100)", "translateLayout(5, 5)", "moveLayout(10, 10)",
]
CENTERED = ["circleLayout(Node.x, a)", "circleLayout(Edge.weight, a, 0, 0)", "radialLayout(a)"]


@pytest.mark.parametrize("case", list(EDGE_CASES))
def test_edge_case_graphs(case):
    spec = EDGE_CASES[case]
    cmds = EDGE_CASE_COMMANDS + (CENTERED if spec["nodes"] else [])
    for cmd in cmds:
        sess = make_session()
        build(sess, **spec)
        if len(spec["nodes"]) > 1:
            sess.graph._nodes_list()[-1].fixed = True
        fixed_before = [(n.x, n.y) for n in sess.graph._nodes_list() if n.fixed]
        run(sess, cmd)
        P = positions(sess)
        assert np.isfinite(P).all(), (case, cmd)
        assert [(n.x, n.y) for n in sess.graph._nodes_list() if n.fixed] == fixed_before, (case, cmd)


def test_coincident_nodes_get_separated():
    sess = make_session()
    build(sess, list("abcdef"), [("a", "b"), ("b", "c"), ("d", "e")], same_pos=True)
    run(sess, "springLayout(50)")
    P = positions(sess)
    assert len(np.unique(P, axis=0)) == len(P)


# ---------------------------------------------------------------------------
# algorithm-specific properties
# ---------------------------------------------------------------------------

def test_circle_layout_equidistant(sample_text):
    sess = sample_session()
    run(sess, "circleLayout()")
    P = positions(sess)
    r = np.hypot(P[:, 0] - 500, P[:, 1] - 500)
    assert np.allclose(r, 450)
    ang = np.sort(np.arctan2(P[:, 1] - 500, P[:, 0] - 500))
    gaps = np.diff(ang)
    assert np.allclose(gaps, 2 * math.pi / len(P))


def test_circle_layout_constrained():
    sess = make_session()
    build(sess, ["c", "n1", "n2", "n3", "far"], [("c", "n1"), ("c", "n2"), ("c", "n3")])
    g = sess.graph
    g.addNodeField("score", "DOUBLE", 0)
    for name, v in (("n1", 1.0), ("n2", 2.0), ("n3", 4.0)):
        g.getNodeByName(name).score = v
    far = pos_of(sess, "far")
    run(sess, "circleLayout(score, c, 100, 200)")
    assert np.allclose(pos_of(sess, "c"), (100, 200))
    radius = {k: np.hypot(*(pos_of(sess, k) - (100, 200))) for k in ("n1", "n2", "n3")}
    # radius = 30 + 470 * value / max  (CircularConstrained)
    assert radius["n1"] == pytest.approx(30 + 470 * 1 / 4)
    assert radius["n2"] == pytest.approx(30 + 470 * 2 / 4)
    assert radius["n3"] == pytest.approx(500)
    assert np.array_equal(pos_of(sess, "far"), far)  # non-neighbours untouched
    run(sess, "circleLayout(Node.label, c)")  # non-numeric field: all on one circle
    r = [np.hypot(*(pos_of(sess, k) - (500, 500))) for k in ("n1", "n2", "n3")]
    assert np.allclose(r, r[0])


DAG = [("r", "a"), ("r", "b"), ("a", "c"), ("b", "c"), ("c", "d"), ("a", "d"),
       ("r", "d"), ("e", "d"), ("d", "f"), ("b", "f")]


@pytest.mark.parametrize("cmd", ["sugiyamaLayout()", "sugiyamaLayout(true)",
                                 "sugiyamaLayout2()", "dagLayout()"])
def test_layered_layouts_point_edges_down(cmd):
    sess = make_session()
    build(sess, list("rabcdef"), DAG, directed=True)
    run(sess, cmd)
    ys = {n.name: n.y for n in sess.graph._nodes_list()}
    levels = sorted(set(ys.values()))
    layer = {k: levels.index(y) for k, y in ys.items()}
    for a, b in DAG:
        assert layer[a] < layer[b], (cmd, a, b, layer)


def test_sugiyama_breaks_cycles_and_orients_undirected():
    sess = make_session()
    build(sess, list("abcd"), [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")], directed=True)
    sess.graph.addEdge("d", "a")  # undirected
    run(sess, "sugiyamaLayout()")
    ys = [n.y for n in sess.graph._nodes_list()]
    assert len(set(ys)) >= 2
    assert np.isfinite(positions(sess)).all()


def test_radial_layout_root_at_centre():
    sess = make_session()
    build(sess, ["root", "a", "b", "c", "a1", "a2", "lonely"],
          [("root", "a"), ("root", "b"), ("root", "c"), ("a", "a1"), ("a", "a2"), ("a1", "a2")])
    lonely = pos_of(sess, "lonely")
    run(sess, "radialLayout(root)")
    assert np.allclose(pos_of(sess, "root"), (0, 0))
    layer = 50.0  # max(10, 5 * node width)
    for k in ("a", "b", "c"):
        assert np.hypot(*pos_of(sess, k)) == pytest.approx(layer)
    for k in ("a1", "a2"):
        assert np.hypot(*pos_of(sess, k)) == pytest.approx(2 * layer)
    assert np.array_equal(pos_of(sess, "lonely"), lonely)


def test_rescale_translate_move(sample_text):
    sess = sample_session()
    P0 = positions(sess)
    run(sess, "rescaleLayout(500, 400)")
    P = positions(sess)
    assert np.allclose(P.min(0), 0) and np.allclose(P.max(0), (500, 400))
    run(sess, "rescaleLayout(0.5)")
    assert np.allclose(np.ptp(positions(sess), 0), (250, 200))
    run(sess, "translateLayout(10, -20)")
    assert np.allclose(positions(sess).min(0), (10, -20))
    run(sess, "moveLayout(100, 100)")
    assert np.allclose(positions(sess).min(0), (100, 100))
    assert np.allclose(np.ptp(positions(sess), 0), (250, 200))
    assert not np.allclose(P0, positions(sess))


def test_binpack_separates_components():
    sess = make_session()
    build(sess, list("abcdefghij"),
          [("a", "b"), ("b", "c"), ("d", "e"), ("e", "f"), ("f", "d"), ("g", "h")])
    for n in sess.graph._nodes_list():   # pile every component on top of each other
        n.x, n.y = 100 + 10 * (ord(n.name) % 3), 100 + 10 * (ord(n.name) % 2)
    run(sess, "binPackLayout()")
    comps = [list("abc"), list("def"), list("gh"), ["i"], ["j"]]
    boxes = []
    for c in comps:
        P = np.array([pos_of(sess, k) for k in c])
        boxes.append((P.min(0), P.max(0) + 10))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (alo, ahi), (blo, bhi) = boxes[i], boxes[j]
            overlap = (alo < bhi).all() and (blo < ahi).all()
            assert not overlap, (comps[i], comps[j])


def test_gem_seed_is_repeatable(sample_text):
    a = sample_session()
    b = sample_session()
    run(a, "gemLayout(42)")
    run(b, "gemLayout(42)")
    assert np.array_equal(positions(a), positions(b))


def test_force_layouts_shorten_edges(sample_text):
    """After a force layout, connected nodes are closer than random pairs."""
    for cmd in ("frLayout()", "jfrLayout()", "kkLayout()", "jkkLayout1()", "gemLayout(1)",
                "springLayout()", "jSpringLayout()", "physicsLayout()", "isomLayout()"):
        sess = sample_session()
        run(sess, "randomLayout()")
        run(sess, cmd)
        P = positions(sess)
        g = sess.graph
        idx = {n._id: i for i, n in enumerate(g._nodes_list())}
        e = np.array([[idx[x._n1._id], idx[x._n2._id]] for x in g._edges_list()
                      if x._n1 is not x._n2])
        edge_len = np.median(np.hypot(*(P[e[:, 0]] - P[e[:, 1]]).T))
        rng = np.random.default_rng(0)
        r = rng.integers(0, len(P), (2000, 2))
        rand_len = np.median(np.hypot(*(P[r[:, 0]] - P[r[:, 1]]).T))
        assert edge_len < 0.6 * rand_len, (cmd, edge_len, rand_len)


def _smds_reference(n, edges):
    """Classical MDS of SMDS's matrix: 1 everywhere, edge weight on edges."""
    D = np.ones((n, n))
    for i, j, w in edges:
        D[i, j] = D[j, i] = w
    J = np.eye(n) - 1.0 / n
    B = -0.5 * J @ (D * D) @ J
    vals, vecs = np.linalg.eigh(B)
    top = np.argsort(vals)[::-1][:2]
    X = vecs[:, top] * np.sqrt(np.maximum(vals[top], 0)) * 1000
    return np.hypot(*(X[:, None, :] - X[None, :, :]).transpose(2, 0, 1))


@pytest.mark.parametrize("n", [12, 450])   # dense eigensolver / Lanczos path
def test_mds_matches_classical_mds(n):
    sess = make_session()
    rng = np.random.default_rng(n)
    names = [f"n{i}" for i in range(n)]
    pairs = {(i, (i + 1) % n) for i in range(n)} | {
        tuple(sorted(rng.choice(n, 2, replace=False))) for _ in range(n)}
    pairs = sorted((a, b) for a, b in pairs if a != b)
    build(sess, names, [(names[a], names[b]) for a, b in pairs])
    weights = rng.uniform(1, 5, len(pairs))
    for e, w in zip(sess.graph._edges_list(), weights):
        e.weight = float(w)
    run(sess, "mdsLayout()")
    P = positions(sess)
    got = np.hypot(*(P[:, None, :] - P[None, :, :]).transpose(2, 0, 1))
    ref = _smds_reference(n, [(a, b, w) for (a, b), w in zip(pairs, weights)])
    assert np.corrcoef(got.ravel(), ref.ravel())[0, 1] > 0.999


def test_mds_equal_weights_falls_back_to_graph_distance():
    sess = make_session()
    build(sess, list("abcde"), [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")])
    run(sess, "mdsLayout()")
    assert any("graph distances" in m["text"] for m in sess.rec.of("text"))
    P = positions(sess)
    assert np.hypot(*(P[0] - P[4])) > np.hypot(*(P[0] - P[1])) * 2


def test_weighted_spring_lengths_follow_weights():
    sess = make_session()
    build(sess, list("abcd"), [("a", "b"), ("c", "d")])
    g = sess.graph
    g._edges_list()[0].weight = 1.0
    g._edges_list()[1].weight = 10.0
    run(sess, "weightedSpringLayout(20, 200, 400)")
    assert np.hypot(*(pos_of(sess, "c") - pos_of(sess, "d"))) > \
        np.hypot(*(pos_of(sess, "a") - pos_of(sess, "b")))


# ---------------------------------------------------------------------------
# iteration driver: ticks and interrupts
# ---------------------------------------------------------------------------

def test_iterative_layout_ticks_every_iteration(sample_text):
    sess = sample_session()
    calls = []
    orig = sess.tick
    sess.tick = lambda force=False: (calls.append(1), orig(force))
    run(sess, "springLayout(25)")
    assert len(calls) >= 25


@pytest.mark.parametrize("cmd", ["springLayout()", "frLayout()", "gemLayout()", "kkLayout()",
                                 "jkkLayout1()", "physicsLayout()", "isomLayout()",
                                 "jfrLayout()", "dagLayout()"])
def test_interrupt_leaves_valid_positions(sample_text, cmd):
    sess = sample_session()
    g = sess.graph
    g.getNodeByName("v5").fixed = True
    fixed = pos_of(sess, "v5")
    start = positions(sess)
    count = [0]

    def tick(force=False):
        count[0] += 1
        if count[0] == 8:
            raise KeyboardInterrupt

    sess.tick = tick
    sess.rec.msgs.clear()
    assert not sess.run(cmd)
    assert sess.rec.of("error")[-1]["text"] == "Interrupted"
    P = positions(sess)
    assert np.isfinite(P).all()
    assert np.array_equal(pos_of(sess, "v5"), fixed)
    assert (P != start).any(), "partial progress should be kept"


def test_center_after_layout_can_be_disabled(sample_text):
    sess = sample_session()
    run(sess, "centerAfterLayout(false)")
    run(sess, "circleLayout()")
    assert not sess.rec.of("center")
    run(sess, "centerAfterLayout(true)")
    run(sess, "circleLayout()")
    assert sess.rec.of("center")


# ---------------------------------------------------------------------------
# Kamada-Kawai fast path (sampled stress majorization for large components)
# ---------------------------------------------------------------------------

KK_CMDS = ["kkLayout()", "jkkLayout1()", "jkkLayout2()", "weightedKKLayout()"]


def _kk_energy(P, D):
    iu = np.triu_indices(len(P), 1)
    t = D[iu].astype(float)
    ok = t > 0
    d = np.hypot(*(P[iu[0]] - P[iu[1]]).T)
    # scale-free: best uniform scale, as both layouts are rescaled afterwards
    r = d[ok] / t[ok]
    s = r.sum() / (r * r).sum()
    return float(((s * d[ok] - t[ok]) ** 2 / t[ok] ** 2).sum())


def _sample_hops(sess):
    g = sess.graph
    nodes = g._nodes_list()
    idx = {n._id: i for i, n in enumerate(nodes)}
    import networkx as nx
    G = nx.Graph()
    G.add_nodes_from(range(len(nodes)))
    G.add_edges_from((idx[e._n1._id], idx[e._n2._id]) for e in g._edges_list())
    comp = max(nx.connected_components(G), key=len)
    comp = sorted(comp)
    D = np.array([[dict(nx.single_source_shortest_path_length(G, i)).get(j, 0) for j in comp] for i in comp])
    return comp, D


@pytest.mark.parametrize("cmd", KK_CMDS)
def test_kk_fast_path_matches_exact_energy(sample_text, monkeypatch, cmd):
    exact = sample_session()
    run(exact, "randomLayout()")
    run(exact, cmd)
    monkeypatch.setattr(layouts, "_KK_FAST", 50)
    fast = sample_session()
    run(fast, "randomLayout()")
    run(fast, cmd)
    comp, D = _sample_hops(exact)
    e_exact = _kk_energy(positions(exact)[comp], D)
    e_fast = _kk_energy(positions(fast)[comp], D)
    # the JUNG variants start the exact solver from an unseeded random layout, so
    # its own energy varies by about +-12% between runs; kkLayout is deterministic
    slack = 1.15 if cmd == "kkLayout()" else 1.3
    assert e_fast < slack * e_exact, (cmd, e_fast, e_exact)


@pytest.mark.parametrize("case", list(EDGE_CASES))
def test_kk_fast_path_edge_cases(monkeypatch, case):
    monkeypatch.setattr(layouts, "_KK_FAST", 1)
    spec = EDGE_CASES[case]
    for cmd in KK_CMDS:
        sess = make_session()
        build(sess, **spec)
        if len(spec["nodes"]) > 1:
            sess.graph._nodes_list()[-1].fixed = True
        fixed_before = [(n.x, n.y) for n in sess.graph._nodes_list() if n.fixed]
        run(sess, cmd)
        assert np.isfinite(positions(sess)).all(), (case, cmd)
        assert [(n.x, n.y) for n in sess.graph._nodes_list() if n.fixed] == fixed_before, (case, cmd)


def test_legend_for_tells_categories_from_gradients():
    """legendFor on a numeric field: categories after colorize (e.g. 44
    communities), a ramp after colorBy (any scale, with or without a middle)."""
    s = make_session()
    run(s, f"makeFromGDF({str(SAMPLE)!r})")
    run(s, "louvainClusters()\ncolorize(modularity_class)\nlg = legendFor(modularity_class)")
    lg = s.ns["lg"]
    groups = len({n.modularity_class for n in s.graph.nodes})
    assert groups > 16 and not hasattr(lg, "_ramp")
    rows = lg.record()["entries"]
    assert len(rows) == 13 and rows[-1]["k"] == "x" and rows[-1]["t"].startswith(f"… {groups - 12} more")
    assert len({r["c"] for r in rows[:-1]}) == 12            # each community its own colour
    for scale, middle in (("linear", None), ("log", None), ("rank", "white")):
        extra = ", middle=white" if middle else ""
        run(s, f"colorBy(totaldegree, yellow, red, '{scale}'{extra})\nlg = legendFor(totaldegree)")
        assert hasattr(s.ns["lg"], "_ramp"), scale
    run(s, "colorize(totaldegree)\nlg = legendFor(totaldegree)")
    assert not hasattr(s.ns["lg"], "_ramp")
