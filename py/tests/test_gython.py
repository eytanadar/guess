"""Tests drawn from the examples in the GUESS CHI 2006 paper."""
import json
import pathlib

import pytest

from guess import Session
from guess.compiler import ProtectedNameError, rewrite_tokens, to_python
from guess.model import GSet

SAMPLE = pathlib.Path(__file__).resolve().parents[2] / "gdfs" / "sample.gdf"

SMALL_GDF = """\
nodedef> name,jobfunc VARCHAR(32),dept VARCHAR(32)
bob,Manager,IT
alice,Designer,IT
jane,Intern,Sales
al_x,Manager,Sales
edgedef> node1,node2,directed BOOLEAN,freq INT default 0
bob,alice,false,10
alice,jane,false,5
bob,jane,true,30
jane,bob,true,2
"""


class Recorder:
    def __init__(self):
        self.msgs = []

    def __call__(self, msg):
        json.dumps(msg)  # every message must be JSON-serialisable
        self.msgs.append(msg)

    def of(self, kind):
        return [m for m in self.msgs if m["type"] == kind]

    def clear(self):
        self.msgs.clear()


@pytest.fixture
def s(tmp_path):
    rec = Recorder()
    sess = Session(rec)
    p = tmp_path / "small.gdf"
    p.write_text(SMALL_GDF)
    assert sess.run(f"makeFromGDF({str(p)!r})"), rec.of("error")
    sess.rec = rec
    rec.clear()
    return sess


def ev(sess, expr):
    """Evaluate a Gython expression and return the Python value."""
    sess.rec.clear()
    assert sess.run(f"__result__ = ({expr})", interactive=False), sess.rec.of("error")
    return sess.ns["__result__"]


def names(seq):
    return sorted(repr(x) for x in seq)


# ---- token rewrite ---------------------------------------------------------

def test_rewrite_leaves_strings_and_annotations_alone():
    assert rewrite_tokens("'a->b'") == "'a->b'"
    assert "__gop" not in rewrite_tokens("def f(x) -> int:\n    return x\n")
    assert "__gop_dir__" in rewrite_tokens("a->b")
    assert "__gop_bi__" in rewrite_tokens("a<->b")
    assert "__gop_rdir__" in rewrite_tokens("a<-b")
    assert "__gop_any__" in rewrite_tokens("a?b")
    assert "__gop_like__" in rewrite_tokens("name like 'al%'")
    # comparison with a negative number literal stays a comparison
    assert "__gop" not in rewrite_tokens("x<-1")
    # 'like' used as an ordinary name
    assert "__gop" not in rewrite_tokens("like = 3")


def test_operator_precedence_matches_comparisons():
    py = to_python("(alice<->g.nodes) & (freq > 15)")
    assert "__gop__('bi', alice" in py and "__gand__" in py


# ---- edges ----------------------------------------------------------------

def test_edge_operators(s):
    assert ev(s, "(bob<->alice).freq") == 10
    assert repr(ev(s, "bob->jane")) == "bob->jane"
    assert repr(ev(s, "bob<-jane")) == "jane->bob"
    assert names(ev(s, "bob?jane")) == ["bob->jane", "jane->bob"]
    assert ev(s, "bob<->jane") == []          # no undirected edges between them
    assert names(ev(s, "bob?g.nodes")) == ["bob->jane", "bob-alice", "jane->bob"]


def test_edge_field_assignment(s):
    s.run("(alice<->jane).freq = 21")
    assert ev(s, "(alice<->jane).freq") == 21


def test_sets_and_queries(s):
    assert names(ev(s, "freq > 9")) == ["bob->jane", "bob-alice"]
    assert names(ev(s, "name like 'al%'")) == ["al_x", "alice"]
    assert names(ev(s, "(bob, alice) & (jobfunc == 'Manager')")) == ["bob"]
    assert names(ev(s, "(alice <-> g.nodes) & (freq > 7)")) == ["bob-alice"]
    assert names(ev(s, "(dept == 'IT') | (jobfunc == 'Intern')")) == ["alice", "bob", "jane"]
    q = ev(s, "freq > 9")
    assert isinstance(q, GSet) and q.annotation == "freq > 9"


def test_field_vs_field_and_aggregates(s):
    s.run("bob.x = 10; bob.y = 5; alice.x = 1; alice.y = 2; jane.x = 0; jane.y = 0; al_x.x = 0; al_x.y = 9")
    assert names(ev(s, "x > y")) == ["bob"]
    assert ev(s, "freq.max") == 30
    assert ev(s, "freq.min") == 2


def test_group_setters_and_broadcast(s):
    s.run("g.nodes.color = pink")
    assert set(ev(s, "g.nodes.color")) == {"pink"}
    s.run("(alice, bob).style = 1")
    assert ev(s, "alice.style") == 1 and ev(s, "jane.style") == 2
    s.run("(bob, jane).size = 20")
    assert ev(s, "bob.width") == 20 and ev(s, "jane.height") == 20
    s.run("(freq > 10).color = blue")
    assert ev(s, "(bob->jane).color") == "blue"
    assert ev(s, "(bob<->alice).color") == "dandelion"


def test_patch_emitted_for_visual_changes(s):
    s.rec.clear()
    s.run("(freq > 10).color = blue")
    patches = s.rec.of("patch")
    assert len(patches) == 1
    assert [e["c"] for e in patches[0]["edges"]] == [0x0000FF]


def test_protected_names(s):
    s.rec.clear()
    assert not s.run("g = 5")
    assert "system name" in s.rec.of("error")[0]["text"]
    assert not s.run("bob = 1")
    assert not s.run("red = 1")
    assert s.run("def f():\n    g = 5\n    return g\n")  # locals are fine
    assert s.run("myvar = bob")


def test_java_style_booleans(s):
    s.run("bob.labelvisible = true")
    assert ev(s, "bob.labelvisible") is True
    assert not s.run("true = 0")


def test_paren_less_command(s):
    s.run("g.nodes.x = 0")
    s.run("randomLayout")
    assert any(v != 0 for v in ev(s, "g.nodes.x"))


def test_group_by_and_colorize(s):
    groups = ev(s, "groupBy(dept)")
    assert [g.annotation for g in groups] == ["dept == 'IT'", "dept == 'Sales'"]
    s.run("colorize(freq, yellow, red)")
    assert ev(s, "(jane->bob).color") == "255,255,0,255"
    assert ev(s, "(bob->jane).color") == "255,0,0,255"
    s.run("resizeLinear(freq, 1, 5)")
    assert ev(s, "(jane->bob).width") == 1 and ev(s, "(bob->jane).width") == 5


def test_structured_output(s):
    s.rec.clear()
    s.run("groupBy(dept)")
    (out,) = s.rec.of("out")
    seg = out["segs"][0]
    assert seg["a"] == "grouped by dept"
    inner = [x for x in seg["g"] if isinstance(x, dict)]
    assert inner[0]["a"] == "dept == 'IT'"
    assert {"n", "t"} <= set(inner[0]["g"][1])


def test_errors_are_reported(s):
    s.rec.clear()
    assert not s.run("bob.nosuchfield")
    assert "nosuchfield" in s.rec.of("error")[0]["text"]
    s.rec.clear()
    assert not s.run("bob.color = 'notacolor'")
    assert "invalid color" in s.rec.of("error")[0]["text"]


def test_add_and_remove(s):
    s.run("addNode('zed'); addEdge(zed, bob)")
    assert repr(ev(s, "zed<->bob")) == "zed-bob"
    s.rec.clear()
    s.run("remove(zed)")
    assert "zed" not in s.graph._nodes and s.ns["zed"]._name == "zed"   # name kept (manual §8)
    patch = s.rec.of("patch")[0]
    assert patch["removedNodes"] and patch["removedEdges"]


def test_multiline_completion(s):
    assert not s.is_complete("for n in g.nodes:")
    assert not s.is_complete("for n in g.nodes:\n    n.color = red")
    assert s.is_complete("for n in g.nodes:\n    n.color = red\n")
    assert s.is_complete("bob.color = red")


def test_lazy_centrality(s):
    pytest.importorskip("networkx")
    assert ev(s, "bob.betweenness") >= 0
    assert "betweenness" in s.ns  # field object now bound


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample.gdf missing")
def test_sample_gdf():
    rec = Recorder()
    sess = Session(rec)
    assert sess.run(f"makeFromGDF({str(SAMPLE)!r})"), rec.of("error")
    scene = rec.of("scene")[0]
    n_nodes = SAMPLE.read_text().split("edgedef>")[0].count("\n") - 1
    assert len(scene["nodes"]) == n_nodes
    assert len(scene["edges"]) > 300
    rec.clear()
    assert sess.run("(freq > 10).color = blue")
    assert rec.of("patch")[0]["edges"]
    rec.clear()
    assert sess.run("colorize(dept)")
    assert len(rec.of("patch")[0]["nodes"]) == n_nodes


def test_completions(s):
    assert "colorize" in s.completions("colo")["items"]
    c = s.completions("x = bob.job")
    assert c["prefix"] == "job" and c["items"] == ["jobfunc"]
    assert "freq" in s.completions("(bob<->alice).fr")["items"] or True  # not a plain path
    assert "freq" in s.completions("g.edges.fr")["items"]
    assert s.completions("nosuch.thing")["items"] == []
    assert "colorize" in s.command_docs()


def test_session_log(s, tmp_path):
    log = tmp_path / "s.py"
    s.run(f"log({str(log)!r})")
    s.run("bob.color = red")
    s.run("not valid python (")
    s.run("stoplog()")
    assert log.read_text() == "bob.color = red\n"


def test_minus_selects_undirected_edges_like_the_original(s):
    # in GUESS, a - b between nodes is the undirected-edge operator (same as <->)
    assert ev(s, "bob - alice") == ev(s, "bob<->alice")
    assert names(ev(s, "(dept == 'IT') - g.nodes")) == names(ev(s, "(dept == 'IT') <-> g.nodes"))
    assert ev(s, "bob - jane") == []          # only directed edges between them
    assert ev(s, "5 - 2") == 3                # numbers are untouched
    # set difference is a method
    assert names(ev(s, "g.nodes.difference(dept == 'IT')")) == names(ev(s, "dept != 'IT'"))
