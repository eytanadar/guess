"""makeFromCSV column choice (as Cytoscape's table import)."""
from tests.test_gython import s  # noqa: F401  (fixture)


def test_choose_columns(s, tmp_path):
    f = tmp_path / "ppi.tsv"
    f.write_text("gene_a\tgene_b\ttype\tscore\tSource\nTP53\tMDM2\tbinds\t0.9\tlab1\nTP53\tATM\tphospho\t0.7\tlab2\n")
    assert s.run(f"makeFromCSV({str(f)!r}, source='gene_a', target='GENE_B', interaction='type', weight='score')"), s.rec.of("error")
    g = s.graph
    assert sorted(g._nodes) == ["ATM", "MDM2", "TP53"]
    e = next(e for e in g._edges_list() if e._n2._name == "MDM2")
    assert e.interaction == "binds" and e.weight == 0.9 and e.Source_ == "lab1"
    assert not s.run(f"makeFromCSV({str(f)!r}, source='gene_x', target='gene_b')")
    assert "no column 'gene_x'" in s.rec.of("error")[-1]["summary"]


def test_no_header_and_numbers(s, tmp_path):
    f = tmp_path / "pairs.csv"
    f.write_text("a,b,3\nb,c,4\n")
    assert s.run(f"makeFromCSV({str(f)!r}, header=false, source=0, target=1, weight=2)"), s.rec.of("error")
    assert len(s.graph._edges) == 2 and sorted(s.graph._nodes) == ["a", "b", "c"]
    assert not s.run(f"makeFromCSV({str(f)!r}, header=false, source=0, target=9)")
