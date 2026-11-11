"""makeFromFile: the reader chosen by extension, or by content for .xml/.txt/.json."""
from tests.test_gython import s  # noqa: F401  (fixture)

MITAB = ("uniprotkb:P04637\tuniprotkb:Q00987\t-\t-\tpsi-mi:p53_human(display_short)|uniprotkb:TP53(gene name)\t"
         "psi-mi:mdm2_human(display_short)|uniprotkb:MDM2(gene name)\tpsi-mi:\"MI:0018\"(two hybrid)\tSmith et al.\t"
         "pubmed:123\ttaxid:9606(human)\ttaxid:9606(human)\tpsi-mi:\"MI:0915\"(physical association)\t"
         "psi-mi:\"MI:0469\"(IntAct)\tintact:EBI-1\tintact-miscore:0.56\n")
SBML = ('<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">'
        '<model id="m"><listOfSpecies><species id="A" compartment="c"/><species id="B" compartment="c"/></listOfSpecies>'
        '<listOfReactions><reaction id="r1" reversible="false"><listOfReactants><speciesReference species="A"/>'
        '</listOfReactants><listOfProducts><speciesReference species="B"/></listOfProducts></reaction></listOfReactions>'
        '</model></sbml>')
GRAPHML = ('<?xml version="1.0"?><graphml xmlns="http://graphml.graphdrawing.org/xmlns"><graph edgedefault="undirected">'
           '<node id="a"/><node id="b"/><edge source="a" target="b"/></graph></graphml>')
CYJS = '{"elements": {"nodes": [{"data": {"id": "1", "name": "x"}}, {"data": {"id": "2", "name": "y"}}], "edges": [{"data": {"source": "1", "target": "2"}}]}}'
SIF = "A pp B C\nB pd D\nE\n"


def test_sniffs_by_content(s, tmp_path):
    for fname, text, nodes, edges in [("i.txt", MITAB, 2, 1), ("model.xml", SBML, 3, 2), ("g.xml", GRAPHML, 2, 1),
                                      ("c.json", CYJS, 2, 1), ("net.txt", SIF, 5, 3)]:
        f = tmp_path / fname
        f.write_text(text)
        assert s.run(f"makeFromFile({str(f)!r})"), (fname, s.rec.of("error"))
        assert (len(s.graph._nodes), len(s.graph._edges)) == (nodes, edges), fname
    assert not s.run("makeFromFile('nope.xml')")
