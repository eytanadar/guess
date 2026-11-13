import math

from guess import Session
from guess.enrichment import bh, hypergeom_sf
from tests.test_gython import Recorder


def test_hypergeom_and_bh():
    # 10 balls, 4 red; draw 3: P(>=2 red) = (C(4,2)C(6,1) + C(4,3)) / C(10,3) = 40/120
    assert abs(hypergeom_sf(2, 10, 4, 3) - 40 / 120) < 1e-12
    assert hypergeom_sf(0, 10, 4, 3) == 1.0 and hypergeom_sf(4, 10, 4, 3) == 0.0
    assert bh([0.01, 0.04, 0.03]) == [0.03, 0.04, 0.04]


def _session(tmp_path):
    rec = Recorder()
    s = Session(rec)
    for n in "abcdefghij":
        s.run(f"addNode({n!r})")
    (tmp_path / "sets.csv").write_text(
        "gene,term,aspect\n" + "".join(f"{n},red,p\n" for n in "abcd") +
        "".join(f"{n},blue,p\n" for n in "efghij") + "a,green;blue,f\nb,green,f\n")
    s.rec = rec
    return s


def _all_text(s):
    """Printed text, plain or linked (linked lines' segments joined)."""
    def seg_text(sg):
        if isinstance(sg, str):
            return sg
        return sg.get("t") or "".join(seg_text(x) for x in sg.get("g", []))
    return "".join(m.get("text", "") if m.get("type") == "text" else "".join(seg_text(x) for x in m.get("segs", []))
                   for m in s.rec.msgs if m.get("type") in ("text", "out"))


def test_read_sets_and_enrichment(tmp_path):
    s = _session(tmp_path)
    p = str(tmp_path / "sets.csv")
    assert s.run(f"__sets = readSets({p!r})")
    sets = s.ns["__sets"]
    assert sets["red"] == set("abcd") and sets["green"] == {"a", "b"} and "a" in sets["blue"]
    assert s.run(f"__p = readSets({p!r}, where={{'aspect': 'p'}})")
    assert "green" not in s.ns["__p"]
    s.rec.clear()
    assert s.run("__r = enrichment((a, b, c), __p)"), s.rec.of("error")
    rows = s.ns["__r"]
    top = rows[0]
    assert top["set"] == "red" and (top["k"], top["n"], top["K"], top["N"]) == (3, 3, 4, 10)
    assert abs(top["p"] - math.comb(4, 3) / math.comb(10, 3)) < 1e-12
    assert abs(top["fold"] - (3 / 3) / (4 / 10)) < 1e-12
    assert sorted(x.name for x in top["members"]) == ["a", "b", "c"]
    assert "red" in _all_text(s)
    # a smaller background raises K/N; nodes outside every set are ignored
    assert s.run("__r = enrichment((a, b), __p, background=(a, b, c, d, e))")
    assert s.ns["__r"][0]["N"] == 5
    s.rec.clear()
    assert not s.run("enrichment(g.nodes, {'x': ['nobody']})")
    assert "match node names" in s.rec.of("error")[0]["text"]


def test_make_from_string_offline(monkeypatch):
    from guess import connectors
    ids = ("queryIndex\tqueryItem\tstringId\tncbiTaxonId\ttaxonName\tpreferredName\tannotation\n"
           "0\tTP53\t9606.P1\t9606\tHomo sapiens\tTP53\tCellular tumor antigen p53; more\n"
           "1\tMDM2\t9606.P2\t9606\tHomo sapiens\tMDM2\tE3 ubiquitin-protein ligase Mdm2\n")
    net = ("stringId_A\tstringId_B\tpreferredName_A\tpreferredName_B\tncbiTaxonId\tscore\tnscore\tfscore\tpscore\tascore\tescore\tdscore\ttscore\n"
           "9606.P1\t9606.P2\tTP53\tMDM2\t9606\t0.999\t0\t0\t0\t0.1\t0.99\t0.9\t0.95\n"
           "9606.P2\t9606.P1\tMDM2\tTP53\t9606\t0.999\t0\t0\t0\t0.1\t0.99\t0.9\t0.95\n"
           "9606.P1\t9606.P3\tTP53\tATM\t9606\t0.8\t0\t0\t0\t0\t0.5\t0.5\t0.6\n")
    urls = []

    def fake(url, *a, **k):
        urls.append(url)
        return ids if "get_string_ids" in url else net
    monkeypatch.setattr(connectors, "http", fake)
    rec = Recorder()
    s = Session(rec)
    assert s.run('makeFromSTRING("TP53, MDM2", score=0.9, add=1)'), rec.of("error")
    g = s.graph
    assert sorted(n.name for n in g.nodes) == ["ATM", "MDM2", "TP53"]
    assert g.getNodeByName("TP53").query and not g.getNodeByName("ATM").query
    assert g.getNodeByName("TP53").description == "Cellular tumor antigen p53"
    assert len(g.edges) == 2                                    # the reversed duplicate is merged
    e = [e for e in g.edges if {e._n1.name, e._n2.name} == {"TP53", "MDM2"}][0]
    assert e.score == e.weight == 0.999 and e.experiments == 0.99 and e.coexpression == 0.1
    assert "required_score=900" in urls[1] and "add_nodes=1" in urls[1] and "species=9606" in urls[0]
