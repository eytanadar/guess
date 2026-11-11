"""connectAssistant(): the page is told to connect; the summary describes the graph."""
from tests.test_gython import s  # noqa: F401  (fixture)


def test_connect_and_summary(s):
    assert s.run("connectAssistant()")
    assert s.rec.of("assistant")[-1] == {"type": "assistant", "op": "connect", "url": "ws://127.0.0.1:7777"}
    assert s.run("connectAssistant(9000)") and s.rec.of("assistant")[-1]["url"].endswith(":9000")
    assert not s.run("connectAssistant('x')") and not s.run("connectAssistant(0)")
    assert s.run("disconnectAssistant()") and s.rec.of("assistant")[-1]["op"] == "disconnect"
    text = s.panel_data("summary")
    n = len(list(s.graph._nodes_list()))
    assert text.startswith(f"graph: {n} nodes") and "node fields:" in text and "components:" in text
    assert "pagerank" in text                                   # computed fields are listed, not computed
    assert "pagerank" not in s.graph.node_schema
