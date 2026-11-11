"""wordCloud(): a Vega word cloud of a text field, linked to its nodes."""
from tests.test_gython import s  # noqa: F401  (fixture)


def test_word_cloud(s):
    assert s.run("addNodeField('bio', VARCHAR, '')")
    assert s.run("bob.bio = 'Graph drawing and graph theory'\nalice.bio = 'Theory of the graph, again'")
    s.rec.clear()
    assert s.run("wordCloud(bio)")
    m = s.rec.of("vega")[-1]
    assert m["spec"]["$schema"].endswith("vega/v6.json")
    rows = {r["text"]: r for r in m["spec"]["data"][0]["values"]}
    assert rows["graph"]["count"] == 3 and len(rows["graph"]["_nodes"]) == 2
    assert "and" not in rows and "of" not in rows            # stop words
    assert not s.run("wordCloud(nosuchfield)")
