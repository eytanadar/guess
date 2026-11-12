"""The Networks explainers (web/public/explainers/networks/*/main.gy): each
script runs, and its controls do what the panel says. Clicks, buttons and
timers are driven through the same entry points the browser uses."""
import json
import os
from pathlib import Path

import pytest

from guess import Session
from tests.test_gython import Recorder

ROOT = Path(__file__).resolve().parents[2]
EXPL = ROOT / "web" / "public" / "explainers" / "networks"
DATA = ROOT / "cookbooks" / "data"


@pytest.fixture(autouse=True)
def _in_data_folder(monkeypatch):
    monkeypatch.chdir(DATA)     # and back to where we were afterwards


class App:
    def __init__(self, name):
        self.rec = Recorder()
        self.s = Session(self.rec)
        self.s.rec = self.rec
        os.chdir(DATA)          # the bundled datasets open by name, as in the browser
        code = (EXPL / name / "main.gy").read_text()
        assert self.s.run(code, interactive=False, filename="main.gy"), self.errors()
        assert not self.errors()

    def errors(self):
        return [m.get("text") or m.get("summary") for m in self.rec.of("error")]

    def __getitem__(self, name):
        return self.s.ns[name]

    def call(self, code):
        """Run code as a handler would (an expression or statements)."""
        assert self.s.run(code), self.errors()
        assert not self.errors(), self.errors()

    def ev(self, code):
        assert self.s.run(f"__r = {code}"), self.errors()
        return self.s.ns["__r"]

    def node(self, name):
        n = self.s.graph.getNodeByName(name)
        assert n is not None, name
        return n

    def click(self, node):
        n = self.node(node) if isinstance(node, str) else node
        assert self.s.dispatch("graph", "clickNode", ["n", n._id]) is not False
        assert not self.errors(), self.errors()

    def widget(self, kind, text):
        for w in self.s.gui.widgets.values():
            st = w._state
            if w.kind == kind and text in str(st.get("text", "")) + str(st.get("label", "")):
                return w
        raise AssertionError(f"no {kind} {text!r}")

    def press(self, text):
        w = self.widget("button", text)
        self.s.dispatch(w._id, "click")
        assert not self.errors(), self.errors()

    def set(self, kind, text, value):
        w = self.widget(kind, text)
        self.s.dispatch(w._id, "change", value)
        assert not self.errors(), self.errors()

    def tick(self, times=1):
        """Fire every running timer `times` times."""
        for _ in range(times):
            for tid in list(self.s.gui.timers):
                self.s.dispatch(tid, "tick")
        assert not self.errors(), self.errors()

    def markdown(self):
        return "\n".join(str(w._state.get("text", "")) for w in self.s.gui.widgets.values() if w.kind == "markdown")


ALL = sorted(p.name for p in EXPL.iterdir() if (p / "main.gy").exists()) if EXPL.exists() else []


@pytest.mark.parametrize("name", ALL)
def test_manifest_and_script_run(name):
    m = json.loads((EXPL / name / "manifest.json").read_text())
    assert m["guess-app"] == 1 and m["script"] == "main.gy" and m["name"] and m["description"]
    App(name)


def test_index_lists_every_explainer():
    page = (EXPL / "index.html").read_text()
    for name in ALL:
        assert f'"{name}"' in page, name


def _tabs(a):
    return next(w for w in a.s.gui.widgets.values() if w.kind == "tabs")


def test_zoo_switches_between_the_four_families():
    a = App("ch01-zoo")
    assert len(a.s.graph.nodes) == 8 and len(a.s.graph.edges) == 10
    for choice, directed in (("Technological: US airports", False), ("Information: papers citing papers", True),
                             ("Social: a karate club", False), ("Biological: a food web", True)):
        a.set("dropdown", "Network", choice)
        assert ("· directed" in a.markdown()) == directed, choice


def test_properties_degree_paths_and_communities():
    a = App("ch01-properties")
    assert "members 34 and 1 have **17** and **16**" in a.markdown()
    a.s.dispatch(_tabs(a)._id, "change", "Small world")
    a.click("m1")
    a.click("m30")
    assert "From member 1 to member 30: **3** steps" in a.markdown()
    a.press("farthest")
    assert "**5** steps" in a.markdown()
    a.s.dispatch(_tabs(a)._id, "change", "Communities")
    a.set("checkbox", "real split", True)
    assert "went entirely to one side" in a.markdown()


def test_internet_levels_coarsen_the_network():
    a = App("ch02-internet-tiers")
    shown = {}
    for level in ("Everything", "Routers only (no end users)", "Class C subnets", "Domains", "Autonomous systems"):
        a.set("dropdown", "Show", level)
        shown[level] = a.ev("len([n for n in g.nodes if n.visible])")
    assert shown["Everything"] > shown["Class C subnets"] > shown["Domains"] > shown["Autonomous systems"]
    assert shown["Routers only (no end users)"] < shown["Everything"]
    a.set("dropdown", "Show", "Everything")
    a.click("pc0")
    a.click("pc100")
    assert "hops**: end user →" in a.markdown()


def test_traceroute_steps_and_maps():
    a = App("ch02-traceroute")
    nodes = list(a.s.graph.nodes)
    a.click(nodes[5])
    a.click(nodes[200])
    for _ in range(8):
        a.press("TTL + 1")
    assert "is the destination: done" in a.markdown()
    a.s.dispatch(_tabs(a)._id, "change", "Build a map")
    a.press("5 spread-out")
    one = a.ev("len(found)")
    for _ in range(5):
        a.press("Add a random")
    assert a.ev("len(found)") > one and "**10** sources" in a.markdown()
    chart = next(w for w in a.s.gui.widgets.values() if w.kind == "chart")
    assert len(chart.spec["series"][0]["points"]) == 10


def test_telephone_blocks_calls_when_trunks_are_full():
    a = App("ch02-telephone")
    a.set("slider", "circuits per", 1)
    a.set("slider", "share of calls", 0)
    a.press("Run")
    a.tick(12)
    a.press("Pause")
    assert a.ev("stats['blocked']") > 0 and a.ev("stats['long_blocked']") == a.ev("stats['blocked']")
    a.press("Reset")
    assert a.ev("stats['placed']") == 0 and a.ev("sum(load.values())") == 0


def test_power_cascade_spreads_and_records_outages():
    a = App("ch02-power-cascade")
    a.press("busiest")
    a.tick(20)
    assert a.ev("len(outages)") == 1 and a.ev("outages[0]") > 0.05
    a.press("Run 12")
    a.tick(14)
    assert a.ev("len(outages)") == 13


def test_rail_trips_count_trains_not_stops():
    a = App("ch02-rail-spaces")
    a.click("Ashby")
    a.click("Wexley")
    m = a.markdown()
    assert "stops network: **5** edges" in m and "**2** edges = 2 trains" in m and "2 trains" in m
    for view in ("One train between them", "Stations and lines (bipartite)"):
        a.set("dropdown", "Network", view)
    assert a.ev("len([e for e in g.edges if e.visible and e.kind == 'member'])") > 0


def test_river_is_a_tree_until_a_loop_is_added():
    a = App("ch02-river-trees")
    assert len(a.s.graph.edges) == len(a.s.graph.nodes) - 1
    a.click("p5_3")
    assert "exactly one route" in a.markdown()
    a.press("Add a loop")
    assert "**2 routes**" in a.markdown()
    a.press("Remove it")
    assert "exactly one route" in a.markdown()
    for d in ("0° (horizontal)", "90° (vertical)"):
        a.set("dropdown", "Lines", d)
    assert "True length" in a.markdown() and a.s.view.drawings


def test_crawler_finds_only_what_it_can_reach():
    a = App("ch03-web-crawler")
    a.click("news_3")
    a.press("Finish")
    m = a.markdown()
    assert "**Finished.**" in m and "have no incoming links at all" in m
    assert a.ev("all(G.in_degree(v) > 0 for v in crawl['seen'] if v != 'news_3')")
    a.press("Try every")
    assert "Colour = how many pages" in a.markdown()


def test_citations_loops_relations_and_derived_networks():
    a = App("ch03-citations")
    a.press("Look for loops")
    assert "short loops" in a.markdown()
    top = max(a.s.graph.nodes, key=lambda n: n.indegree)
    a.click(top)
    assert "**Cocited** with it" in a.markdown()
    a.press("Cocitation network")
    assert a.ev("graphNames()[0]") == "cocitation"
    a.press("Back to the citations")
    assert a.ev("graphNames()[0]") == "main"
    a.press("Main path")


def test_p2p_supernodes_send_fewer_messages():
    a = App("ch03-p2p-search")
    a.set("slider", "hop limit", 4)
    a.click("peer40")
    a.tick(10)
    flat = a.ev("results[0]['messages']")
    a.set("dropdown", "Network", "Two tiers (supernodes)")
    a.click("peer40")
    a.tick(10)
    assert a.ev("results[0]['mode']") == "supernodes" and a.ev("results[0]['messages']") < flat / 3


def test_recommender_recommends_and_beats_guessing():
    a = App("ch03-recommender")
    a.click("Ana")
    assert "Most similar people" in a.markdown() and "predicted +" in a.markdown()
    a.press("Test 50")
    assert a.ev("tests['hit']") > a.ev("tests['miss']")


def test_keyword_index_entries_and_similar_pages():
    a = App("ch03-keyword-index")
    a.click("w_irene")
    assert "Index entry: **irene**" in a.markdown()
    a.click("page5")
    assert "by **LSA**" in a.markdown()
    a.press("Place by LSA")
    a.press("Back to the index")
