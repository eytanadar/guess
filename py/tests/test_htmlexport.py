"""exportHTML(): one self-contained page with the graph inlined."""
import json
import re

from tests.test_gython import s  # noqa: F401  (fixture)


def _data(text):
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', text, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_export_html_is_standalone(s, tmp_path):
    assert s.run("bob.color = red\nbob.style = polygon(5)\naddNodeField('note', VARCHAR, '')\nbob.note = '</script><b>x'")
    f = tmp_path / "g.html"
    assert s.run(f"exportHTML({str(f)!r}, title='Small <graph>')")
    text = f.read_text()
    assert text.startswith("<!doctype html>") and "Small &lt;graph&gt;" in text
    assert "http://" not in text and "https://" not in text          # nothing to fetch
    d = _data(text)
    bob = next(n for n in d["nodes"] if n["name"] == "bob")
    assert bob["c"] == 0xFF0000 and bob["s"] == 105 and bob["f"]["note"] == "</script><b>x"
    assert "x" not in bob["f"] and len(d["edges"]) == len(list(s.graph._edges_list()))
    download = s.rec.of("download")[-1]
    assert download["name"] == "g.html"


def test_export_html_hidden_and_fields(s, tmp_path):
    assert s.run("bob.visible = false")
    f = tmp_path / "g.html"
    assert s.run(f"exportHTML({str(f)!r}, fields=false)")
    d = _data(f.read_text())
    assert all(n["name"] != "bob" for n in d["nodes"]) and all(not n["f"] for n in d["nodes"])
    assert s.run(f"exportHTML({str(f)!r}, hidden=true)")
    assert any(n["name"] == "bob" for n in _data(f.read_text())["nodes"])
