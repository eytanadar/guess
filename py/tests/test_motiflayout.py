"""motifLayout (LUMINA port) and the shapes around groups (box, ellipse)."""
import math

import numpy as np

from tests.test_gython import s  # noqa: F401  (fixture)

BUILD = """
newGraph("shapes")
for i in range(8): addNode('h%d' % i)
# a backbone h0..h7 with a ring of 6, a star, a chain and a parallel group hanging off it
for i in range(7): addEdge('h%d' % i, 'h%d' % (i + 1))
for i in range(6): addNode('r%d' % i)
for i in range(6): addEdge('r%d' % i, 'r%d' % ((i + 1) % 6))
addEdge('r0', 'h0')
addNode('hub'); addEdge('hub', 'h3')
for i in range(7): addNode('l%d' % i); addEdge('hub', 'l%d' % i)
for i in range(3): addNode('c%d' % i)
addEdge('h7', 'c0'); addEdge('c0', 'c1'); addEdge('c1', 'c2')
for i in range(4): addNode('p%d' % i); addEdge('p%d' % i, 'h5'); addEdge('p%d' % i, 'h6')
"""


def centre(s, name):
    n = s.graph._nodes[name]
    return np.array([float(n.x) + float(n.width) / 2, float(n.y) + float(n.height) / 2])


def test_motif_layout_finds_and_draws_each_shape(s):
    assert s.run(BUILD), s.rec.of("error")
    assert s.run("motifLayout()"), s.rec.of("error")
    m = {n._name: n.motif for n in s.graph._nodes_list()}
    assert {m[f"r{i}"] for i in range(6)} == {"cycle 1"}
    assert {m["hub"]} | {m[f"l{i}"] for i in range(7)} == {"star 1"}
    assert {m[f"c{i}"] for i in range(3)} == {"chain 1"}
    assert {m[f"p{i}"] for i in range(4)} == {"parallel 1"}
    # the ring is a circle
    pts = np.array([centre(s, f"r{i}") for i in range(6)])
    d = np.hypot(*(pts - pts.mean(0)).T)
    assert d.std() < 0.02 * d.mean()
    # the star's leaves sit on a ring around the hub
    hub = centre(s, "hub")
    r = [np.hypot(*(centre(s, f"l{i}") - hub)) for i in range(7)]
    assert max(r) - min(r) < 1e-6
    # no two nodes on top of each other
    P = np.array([centre(s, n._name) for n in s.graph._nodes_list()])
    dd = np.hypot(P[:, None, 0] - P[None, :, 0], P[:, None, 1] - P[None, :, 1]) + np.eye(len(P)) * 1e9
    assert dd.min() > 5
    assert s.run("undo()")


def test_motif_layout_outline_and_sizes(s):
    assert s.run(BUILD)
    assert s.run("motifLayout(outline=true, spacing=40)")
    shapes = [h.shape for h in s.view.hulls.values()]
    assert sorted(shapes) == ["box", "ellipse", "ellipse", "ellipse"]
    assert all(h.rotate for h in s.view.hulls.values())
    assert not s.run("motifLayout(spacing=-1)")


def test_motif_layout_on_real_networks(s, tmp_path):
    from tests.test_gython import SAMPLE
    assert s.run(f"makeFromGDF({str(SAMPLE)!r})")
    assert s.run("motifLayout()"), s.rec.of("error")
    assert s.run("makeSample('karate')\nmotifLayout()"), s.rec.of("error")


def test_encircle_shapes_and_undo(s, tmp_path):
    assert s.run("e = encircle(g.nodes)")
    h = next(iter(s.view.hulls.values()))
    assert h.shape == "ellipse" and h.rotate and h.record()["sh"] == "ellipse" and h.record()["rot"]
    assert s.run("e.shape = 'box'\ne.rotate = false")
    assert s.run("undo()")
    assert h.shape == "ellipse" and h.rotate                       # undo restores the look
    assert not s.run("e.shape = 'triangle'")
    assert s.run("createConvexHull(g.nodes, shape='box')")
    assert s.run("addNodeField('team', VARCHAR, '')\nbob.team = 'x'\nalice.team = 'x'")
    assert s.run("shapes = encircleBy(team)")
    f = tmp_path / "s.guess"
    assert s.run(f"saveSession({str(f)!r})\nmakeFromSession({str(f)!r})")
    kinds = sorted((h.shape, h.rotate) for h in s.view.hulls.values())
    assert ("box", False) in kinds and ("ellipse", True) in kinds
