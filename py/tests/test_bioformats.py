"""Biological network formats: PSI-MI TAB and XML, SBML, BioPAX, KGML, GPML."""
from tests.test_gython import s  # noqa: F401  (fixture)

T = "\t"


def _row(a, b, alt_a, alt_b, method, pub, conf, iid, extra=()):
    cols = [a, b, alt_a, alt_b, "-", "-", method, "Smith et al. (2010)", pub,
            "taxid:9606(human)|taxid:9606(Homo sapiens)", "taxid:9606(human)|taxid:9606(Homo sapiens)",
            'psi-mi:"MI:0915"(physical association)', 'psi-mi:"MI:0469"(IntAct)', iid, conf, *extra]
    return T.join(cols)


MITAB25 = "\n".join([
    "#ID(s) interactor A\tID(s) interactor B\t...",
    _row("uniprotkb:P04637", "uniprotkb:Q00987", "uniprotkb:TP53(gene name)", "uniprotkb:MDM2(gene name)",
         'psi-mi:"MI:0018"(two hybrid)', "pubmed:111", "intact-miscore:0.56", "intact:EBI-1"),
    _row("uniprotkb:Q00987", "uniprotkb:P04637", "uniprotkb:MDM2(gene name)", "uniprotkb:TP53(gene name)",
         'psi-mi:"MI:0019"(coimmunoprecipitation)', "pubmed:222|imex:IM-1", "intact-miscore:0.81", "intact:EBI-2"),
    _row("uniprotkb:P04637", "-", "uniprotkb:TP53(gene name)", "-",
         'psi-mi:"MI:0018"(two hybrid)', "pubmed:333", "intact-miscore:0.3", "intact:EBI-3"),
    # two different interactors whose gene name is the same: names must stay unique
    _row("uniprotkb:P38398", "uniprotkb:P38398-5", "uniprotkb:BRCA1(gene name)", "uniprotkb:BRCA1(gene name)",
         'psi-mi:"MI:0018"(two hybrid)', "pubmed:444", "intact-miscore:0.4", "intact:EBI-4"),
])


def test_mitab_25_merge_self_loop_and_names(s, tmp_path):
    f = tmp_path / "i.txt"
    f.write_text(MITAB25)
    assert s.run(f"makeFromMITAB({str(f)!r})"), s.rec.of("error")
    g = s.graph
    assert {"TP53", "MDM2"} <= set(g._nodes)
    brca = sorted(n for n in g._nodes if n.startswith("BRCA1"))
    assert len(brca) == 2 and brca[0] != brca[1]
    assert s.run("assert TP53.taxid == 9606 and TP53.species == 'Homo sapiens' and TP53.ident == 'uniprotkb:P04637'")
    tm = [e for e in g._edges_list() if {e._n1._name, e._n2._name} == {"TP53", "MDM2"}]
    assert len(tm) == 1                                   # two rows merged into one edge
    e = tm[0]
    assert e.evidence == 2 and abs(e.miscore - 0.81) < 1e-9
    assert set(e.method.split("|")) == {"two hybrid", "coimmunoprecipitation"}
    assert set(e.pubmed.split("|")) == {"111", "222", "IM-1"}
    loops = [e for e in g._edges_list() if e._n1 is e._n2]
    assert len(loops) == 1 and loops[0]._n1._name == "TP53"
    assert s.run(f"makeFromMITAB({str(f)!r}, merge=false)")
    assert len(s.graph._edges) == 4


def test_mitab_27_columns(s, tmp_path):
    extra = ['psi-mi:"MI:1060"(spoke expansion)', "-", "-", "-", "-", 'psi-mi:"MI:0326"(protein)',
             'psi-mi:"MI:0326"(protein)'] + ["-"] * 13 + ["false"] + ["-"] * 6
    row = _row("uniprotkb:P1", "uniprotkb:P2", "uniprotkb:AAA(gene name)", "uniprotkb:BBB(gene name)",
               'psi-mi:"MI:0018"(two hybrid)', "pubmed:1", "intact-miscore:0.5", "intact:EBI-9", extra)
    assert len(row.split(T)) == 42
    f = tmp_path / "i27.txt"
    f.write_text(row + "\n")
    assert s.run(f"makeFromMITAB({str(f)!r})"), s.rec.of("error")
    assert s.run("assert AAA.kind == 'protein'")
    e = s.graph._edges_list()[0]
    assert e.expansion == "spoke expansion" and e.kind == "physical association" and e.sourcedb == "IntAct"
    bad = tmp_path / "bad.txt"
    bad.write_text("a\tb\tc\n")
    assert not s.run(f"makeFromMITAB({str(bad)!r})")


PSI25 = """<?xml version="1.0"?>
<entrySet xmlns="net:sf:psidev:mi" level="2" version="5">
 <entry>
  <experimentList>
   <experimentDescription id="10">
    <bibref><xref><primaryRef db="pubmed" id="12345"/></xref></bibref>
    <interactionDetectionMethod><names><shortLabel>pull down</shortLabel></names></interactionDetectionMethod>
   </experimentDescription>
  </experimentList>
  <interactorList>
   <interactor id="1"><names><shortLabel>p53_human</shortLabel><alias type="gene name">TP53</alias></names>
    <xref><primaryRef db="uniprotkb" id="P04637"/></xref>
    <interactorType><names><shortLabel>protein</shortLabel></names></interactorType>
    <organism ncbiTaxId="9606"><names><shortLabel>human</shortLabel><fullName>Homo sapiens</fullName></names></organism>
   </interactor>
   <interactor id="2"><names><shortLabel>mdm2_human</shortLabel><alias type="gene name">MDM2</alias></names>
    <xref><primaryRef db="uniprotkb" id="Q00987"/></xref></interactor>
   <interactor id="3"><names><shortLabel>ep300_human</shortLabel></names>
    <xref><primaryRef db="uniprotkb" id="Q09472"/></xref></interactor>
  </interactorList>
  <interactionList>
   <interaction id="100">
    <experimentList><experimentRef>10</experimentRef></experimentList>
    <participantList>
     <participant id="1"><interactorRef>1</interactorRef>
      <experimentalRoleList><experimentalRole><names><shortLabel>bait</shortLabel></names></experimentalRole></experimentalRoleList>
     </participant>
     <participant id="2"><interactorRef>2</interactorRef>
      <experimentalRoleList><experimentalRole><names><shortLabel>prey</shortLabel></names></experimentalRole></experimentalRoleList>
     </participant>
     <participant id="3"><interactorRef>3</interactorRef>
      <experimentalRoleList><experimentalRole><names><shortLabel>prey</shortLabel></names></experimentalRole></experimentalRoleList>
     </participant>
    </participantList>
    <interactionType><names><shortLabel>association</shortLabel></names></interactionType>
    <confidenceList><confidence><unit><names><shortLabel>intact-miscore</shortLabel></names></unit><value>0.7</value></confidence></confidenceList>
   </interaction>
  </interactionList>
 </entry>
</entrySet>"""

PSI30 = """<?xml version="1.0"?>
<entrySet xmlns="http://psi.hupo.org/mi/mif300" level="3" version="0">
 <entry>
  <interactionList>
   <interaction id="7">
    <experimentList><experimentDescription id="8">
     <interactionDetectionMethod><names><shortLabel>tap</shortLabel></names></interactionDetectionMethod>
    </experimentDescription></experimentList>
    <participantList>
     <participant id="1"><interactor id="11"><names><shortLabel>A1</shortLabel></names><xref><primaryRef db="uniprotkb" id="X1"/></xref></interactor></participant>
     <participant id="2"><interactor id="12"><names><shortLabel>B2</shortLabel></names><xref><primaryRef db="uniprotkb" id="X2"/></xref></interactor></participant>
     <participant id="3"><interactor id="13"><names><shortLabel>C3</shortLabel></names><xref><primaryRef db="uniprotkb" id="X3"/></xref></interactor></participant>
    </participantList>
   </interaction>
  </interactionList>
 </entry>
</entrySet>"""


def test_psimi_xml_spoke_and_matrix(s, tmp_path):
    f = tmp_path / "a.xml"
    f.write_text(PSI25)
    assert s.run(f"makeFromPSIMI({str(f)!r})"), s.rec.of("error")
    g = s.graph
    assert {"TP53", "MDM2", "ep300_human"} == set(g._nodes)
    pairs = {frozenset((e._n1._name, e._n2._name)) for e in g._edges_list()}
    assert pairs == {frozenset(("TP53", "MDM2")), frozenset(("TP53", "ep300_human"))}   # spoke from the bait
    e = g._edges_list()[0]
    assert e.expansion == "spoke expansion" and e.method == "pull down" and e.pubmed == "12345"
    assert abs(e.miscore - 0.7) < 1e-9
    assert s.run("assert TP53.species == 'Homo sapiens' and TP53.kind == 'protein'")
    f3 = tmp_path / "b.xml"
    f3.write_text(PSI30)
    assert s.run(f"makeFromPSIMI({str(f3)!r})"), s.rec.of("error")
    assert len(s.graph._edges) == 3                       # no bait: every pair
    assert all(e.expansion == "matrix expansion" for e in s.graph._edges_list())


SBML2 = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4">
 <model id="m">
  <listOfCompartments><compartment id="cyt" name="cytosol"/><compartment id="mit" name="mitochondrion"/></listOfCompartments>
  <listOfSpecies>
   <species id="glc" name="glucose" compartment="cyt" initialConcentration="5"/>
   <species id="g6p" name="G6P" compartment="cyt"/>
   <species id="atp_c" name="ATP" compartment="cyt"/>
   <species id="atp_m" name="ATP" compartment="mit"/>
   <species id="hk" name="hexokinase" compartment="cyt" sboTerm="SBO:0000252"/>
  </listOfSpecies>
  <listOfReactions>
   <reaction id="r1" name="hexokinase reaction" reversible="false">
    <listOfReactants><speciesReference species="glc"/><speciesReference species="atp_c" stoichiometry="1"/></listOfReactants>
    <listOfProducts><speciesReference species="g6p"/></listOfProducts>
    <listOfModifiers><modifierSpeciesReference species="hk"/></listOfModifiers>
   </reaction>
  </listOfReactions>
 </model>
</sbml>"""

SBML3 = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2"
      xmlns:layout="http://www.sbml.org/sbml/level3/version1/layout/version1">
 <model id="m">
  <listOfCompartments><compartment id="c"/></listOfCompartments>
  <listOfSpecies>
   <species id="A" compartment="c" initialAmount="10" hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
   <species id="B" compartment="c" initialAmount="0" hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
   <species id="E" compartment="c" hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
  </listOfSpecies>
  <listOfReactions>
   <reaction id="conv" reversible="true">
    <listOfReactants><speciesReference species="A" stoichiometry="2" constant="true"/></listOfReactants>
    <listOfProducts><speciesReference species="B" stoichiometry="1" constant="true"/></listOfProducts>
    <listOfModifiers><modifierSpeciesReference species="E"/></listOfModifiers>
   </reaction>
  </listOfReactions>
  <layout:listOfLayouts>
   <layout:layout layout:id="l1">
    <layout:listOfSpeciesGlyphs>
     <layout:speciesGlyph layout:id="gA" layout:species="A">
      <layout:boundingBox><layout:position layout:x="100" layout:y="50"/><layout:dimensions layout:width="40" layout:height="20"/></layout:boundingBox>
     </layout:speciesGlyph>
    </layout:listOfSpeciesGlyphs>
   </layout:layout>
  </layout:listOfLayouts>
 </model>
</sbml>"""


def test_sbml_levels_modifiers_and_layout(s, tmp_path):
    f = tmp_path / "m2.xml"
    f.write_text(SBML2)
    assert s.run(f"makeFromSBML({str(f)!r})"), s.rec.of("error")
    g = s.graph
    assert {"ATP [cytosol]", "ATP [mitochondrion]", "glucose", "hexokinase reaction"} <= set(g._nodes)
    roles = {(e._n1._name, e._n2._name): e.role for e in g._edges_list()}
    assert roles[("glucose", "hexokinase reaction")] == "reactant"
    assert roles[("hexokinase reaction", "G6P")] == "product"
    assert roles[("hexokinase", "hexokinase reaction")] == "modifier"
    assert all(e._directed for e in g._edges_list())
    assert g._nodes["glucose"].initial == 5 and g._nodes["hexokinase"].sbo == "SBO:0000252"
    assert s.run(f"makeFromSBML({str(f)!r}, reactions='edges')")
    pairs = {(e._n1._name, e._n2._name) for e in s.graph._edges_list()}
    assert ("glucose", "G6P") in pairs and ("hexokinase", "G6P") in pairs
    assert "hexokinase reaction" not in s.graph._nodes
    f3 = tmp_path / "m3.xml"
    f3.write_text(SBML3)
    assert s.run(f"makeFromSBML({str(f3)!r})"), s.rec.of("error")
    a = s.graph._nodes["A"]
    assert (a.x, a.y, a.width, a.height) == (100, 50, 40, 20)
    st = {e._n1._name: e.stoichiometry for e in s.graph._edges_list() if e.role == "reactant"}
    assert st == {"A": 2}
    assert not s.run(f"makeFromSBML({str(f3)!r}, reactions='other')")


BIOPAX = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:bp="http://www.biopax.org/release/biopax-level3.owl#"
         xml:base="http://example.org/">
 <bp:ProteinReference rdf:about="PR_HK"><bp:displayName>HK1</bp:displayName>
  <bp:xref><bp:UnificationXref rdf:about="X1"><bp:db>UniProt</bp:db><bp:id>P19367</bp:id></bp:UnificationXref></bp:xref>
 </bp:ProteinReference>
 <bp:Protein rdf:about="HK_cyt"><bp:entityReference rdf:resource="PR_HK"/></bp:Protein>
 <bp:Protein rdf:about="HK_mit"><bp:entityReference rdf:resource="PR_HK"/><bp:displayName>HK1 (mito)</bp:displayName></bp:Protein>
 <bp:SmallMolecule rdf:about="GLC"><bp:displayName>glucose</bp:displayName></bp:SmallMolecule>
 <bp:SmallMolecule rdf:about="G6P"><bp:displayName>glucose-6-phosphate</bp:displayName></bp:SmallMolecule>
 <bp:Protein rdf:about="A"><bp:displayName>ProtA</bp:displayName></bp:Protein>
 <bp:Protein rdf:about="B"><bp:displayName>ProtB</bp:displayName></bp:Protein>
 <bp:Complex rdf:about="AB"><bp:displayName>A:B complex</bp:displayName>
  <bp:component rdf:resource="A"/><bp:component rdf:resource="B"/></bp:Complex>
 <bp:BiochemicalReaction rdf:about="R1"><bp:displayName>glucose phosphorylation</bp:displayName>
  <bp:left rdf:resource="GLC"/><bp:right rdf:resource="G6P"/></bp:BiochemicalReaction>
 <bp:Catalysis rdf:about="C1"><bp:controller rdf:resource="HK_cyt"/><bp:controlled rdf:resource="R1"/>
  <bp:controlType>ACTIVATION</bp:controlType></bp:Catalysis>
 <bp:MolecularInteraction rdf:about="MI1"><bp:participant rdf:resource="A"/><bp:participant rdf:resource="HK_mit"/></bp:MolecularInteraction>
</rdf:RDF>"""


def test_biopax_sif_and_reactions(s, tmp_path):
    f = tmp_path / "p.owl"
    f.write_text(BIOPAX)
    assert s.run(f"makeFromBioPAX({str(f)!r})"), s.rec.of("error")
    g = s.graph
    names = set(g._nodes)
    assert {"glucose", "glucose-6-phosphate", "ProtA", "ProtB", "A:B complex"} <= names
    hk = [n for n in g._nodes_list() if n.xref == "UniProt:P19367"]
    assert len(hk) == 1                                   # both forms of HK1 are one node
    kinds = {(e._n1._name, e._n2._name): e.kind for e in g._edges_list()}
    assert kinds[("glucose", "glucose-6-phosphate")] == "used-to-produce"
    assert kinds[(hk[0]._name, "glucose-6-phosphate")] == "controls-production-of"
    ctl = next(e for e in g._edges_list() if e.kind == "controls-production-of")
    assert ctl.sign == "activation"
    assert any(e.kind == "interacts-with" and {e._n1._name, e._n2._name} == {"ProtA", hk[0]._name}
               for e in g._edges_list())
    assert sum(e.kind == "in-complex-with" for e in g._edges_list()) == 2
    assert s.run(f"makeFromBioPAX({str(f)!r}, mode='reactions')"), s.rec.of("error")
    roles = {(e._n1._name, e._n2._name): e.kind for e in s.graph._edges_list()}
    assert roles[("glucose", "glucose phosphorylation")] == "left"
    assert roles[("glucose phosphorylation", "glucose-6-phosphate")] == "right"
    assert any(k == "controller" for k in roles.values())
    bad = tmp_path / "x.owl"
    bad.write_text('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>')
    assert not s.run(f"makeFromBioPAX({str(bad)!r})")


KGML = """<?xml version="1.0"?>
<!DOCTYPE pathway SYSTEM "https://www.kegg.jp/kegg/xml/KGML_v0.7.2_.dtd">
<pathway name="path:hsa04115" org="hsa" number="04115" title="p53 signaling pathway">
 <entry id="1" name="hsa:7157" type="gene" link="https://www.kegg.jp/dbget-bin/www_bget?hsa:7157">
  <graphics name="TP53, BCC7, LFS1..." fgcolor="#000000" bgcolor="#BFFFBF" type="rectangle" x="300" y="200" width="46" height="17"/>
 </entry>
 <entry id="2" name="hsa:4193" type="gene">
  <graphics name="MDM2, ACTFS" fgcolor="#000000" bgcolor="#BFFFBF" type="rectangle" x="400" y="200" width="46" height="17"/>
 </entry>
 <entry id="3" name="hsa:7157" type="gene">
  <graphics name="TP53" fgcolor="#000000" bgcolor="#BFFFBF" type="rectangle" x="300" y="300" width="46" height="17"/>
 </entry>
 <entry id="4" name="cpd:C00002" type="compound">
  <graphics name="C00002" fgcolor="#000000" bgcolor="#FFFFFF" type="circle" x="500" y="100" width="8" height="8"/>
 </entry>
 <entry id="5" name="cpd:C00008" type="compound">
  <graphics name="C00008" fgcolor="#000000" bgcolor="#FFFFFF" type="circle" x="550" y="100" width="8" height="8"/>
 </entry>
 <entry id="6" name="hsa:1111" type="gene" reaction="rn:R00001">
  <graphics name="KIN1" type="rectangle" x="525" y="150" width="46" height="17"/>
 </entry>
 <entry id="7" name="undefined" type="group">
  <graphics fgcolor="#000000" bgcolor="#FFFFFF" type="rectangle" x="0" y="0" width="0" height="0"/>
  <component id="1"/><component id="2"/>
 </entry>
 <relation entry1="2" entry2="1" type="PPrel">
  <subtype name="inhibition" value="--|"/><subtype name="ubiquitination" value="+u"/>
 </relation>
 <reaction id="6" name="rn:R00001" type="irreversible">
  <substrate id="4" name="cpd:C00002"/><product id="5" name="cpd:C00008"/>
 </reaction>
</pathway>"""


def test_kgml(s, tmp_path):
    f = tmp_path / "hsa04115.xml"
    f.write_text(KGML)
    assert s.run(f"makeFromKGML({str(f)!r})"), s.rec.of("error")
    g = s.graph
    tp53 = [n for n in g._nodes_list() if n.label == "TP53"]
    assert len(tp53) == 2 and tp53[0]._name != tp53[1]._name    # two boxes for one gene
    a = next(n for n in tp53 if n.entry == 1)
    assert (a.x, a.y, a.width, a.height) == (300 - 23, 200 - 8.5, 46, 17)
    assert a.color == "#BFFFBF" and a.group and a.kegg == "hsa:7157"
    rel = next(e for e in g._edges_list() if e.kind == "PPrel")
    assert rel._directed and rel._n1.label == "MDM2" and rel.subtype == "inhibition|ubiquitination"
    rx = next(e for e in g._edges_list() if e.kind == "reaction")
    assert rx._n1.label == "C00002" and rx._n2.label == "C00008" and rx.enzyme == "KIN1"


GPML = """<?xml version="1.0" encoding="UTF-8"?>
<Pathway xmlns="http://pathvisio.org/GPML/2013a" Name="Test pathway" Organism="Homo sapiens">
  <DataNode TextLabel="GLC" GraphId="a1" Type="Metabolite">
    <Graphics CenterX="100" CenterY="100" Width="60" Height="20" ZOrder="1" Color="0000ff"/>
    <Xref Database="ChEBI" ID="CHEBI:4167"/>
  </DataNode>
  <DataNode TextLabel="G6P" GraphId="a2" Type="Metabolite">
    <Graphics CenterX="300" CenterY="100" Width="60" Height="20" ZOrder="1"/>
    <Xref Database="ChEBI" ID="CHEBI:4170"/>
  </DataNode>
  <DataNode TextLabel="HK1" GraphId="a3" Type="GeneProduct" GroupRef="g1">
    <Graphics CenterX="200" CenterY="40" Width="60" Height="20" ZOrder="1" FillColor="ffcc00" ShapeType="RoundedRectangle"/>
    <Xref Database="Entrez Gene" ID="3098"/>
  </DataNode>
  <Interaction GraphId="i1">
    <Graphics ZOrder="12288" LineThickness="1.0">
      <Point X="130" Y="100" GraphRef="a1" RelX="1.0" RelY="0.0"/>
      <Point X="270" Y="100" GraphRef="a2" RelX="-1.0" RelY="0.0" ArrowHead="mim-conversion"/>
      <Anchor Position="0.5" Shape="None" GraphId="an1"/>
    </Graphics>
    <Xref Database="" ID=""/>
  </Interaction>
  <Interaction GraphId="i2">
    <Graphics ZOrder="12288" LineThickness="1.0">
      <Point X="200" Y="50" GraphRef="a3" RelX="0.0" RelY="1.0"/>
      <Point X="200" Y="100" GraphRef="an1" RelX="0.0" RelY="0.0" ArrowHead="mim-catalysis"/>
    </Graphics>
    <Xref Database="" ID=""/>
  </Interaction>
  <Group GroupId="g1" GraphId="gr1" Style="Complex"/>
</Pathway>"""


def test_gpml(s, tmp_path):
    f = tmp_path / "WP1.gpml"
    f.write_text(GPML)
    assert s.run(f"makeFromGPML({str(f)!r})"), s.rec.of("error")
    g = s.graph
    glc = g._nodes["GLC"]
    assert (glc.x, glc.y, glc.width, glc.height) == (70, 90, 60, 20)
    assert glc.xref_db == "ChEBI" and glc.xref_id == "CHEBI:4167" and glc.kind == "Metabolite"
    assert g._nodes["HK1"].color == "#ffcc00" and g._nodes["HK1"].style == 3 and g._nodes["HK1"].group == "Complex"
    anchor = next(n for n in g._nodes_list() if n.kind == "anchor")
    assert (anchor.x + 2, anchor.y + 2) == (200, 100)
    ends = {(e._n1._name, e._n2._name): e for e in g._edges_list()}
    assert ("GLC", anchor._name) in ends and (anchor._name, "G6P") in ends
    assert ends[(anchor._name, "G6P")].arrow == "mim-conversion" and ends[(anchor._name, "G6P")]._directed
    cat = ends[("HK1", anchor._name)]
    assert cat.arrow == "mim-catalysis" and cat._directed
    bad = tmp_path / "x.gpml"
    bad.write_text("<NotAPathway/>")
    assert not s.run(f"makeFromGPML({str(bad)!r})")


GPML2021 = """<?xml version="1.0" encoding="UTF-8"?>
<Pathway xmlns="http://pathvisio.org/GPML/2021" title="New style">
  <DataNodes>
    <DataNode elementId="d1" textLabel="EGFR" type="GeneProduct">
      <Xref identifier="1956" dataSource="Entrez Gene"/>
      <Graphics centerX="100.0" centerY="50.0" width="80.0" height="20.0" textColor="000000" fillColor="ffffff" shapeType="Rectangle"/>
    </DataNode>
    <DataNode elementId="d2" textLabel="GRB2" type="GeneProduct">
      <Xref identifier="2885" dataSource="Entrez Gene"/>
      <Graphics centerX="100.0" centerY="150.0" width="80.0" height="20.0"/>
    </DataNode>
  </DataNodes>
  <Interactions>
    <Interaction elementId="e1">
      <Waypoints>
        <Point elementId="p1" x="100.0" y="60.0" elementRef="d1"/>
        <Point elementId="p2" x="100.0" y="140.0" elementRef="d2" arrowHead="mim-binding"/>
      </Waypoints>
    </Interaction>
  </Interactions>
</Pathway>"""


def test_gpml_2021_and_kgml_groups(s, tmp_path):
    f = tmp_path / "new.gpml"
    f.write_text(GPML2021)
    assert s.run(f"makeFromGPML({str(f)!r})"), s.rec.of("error")
    g = s.graph
    assert g._nodes["EGFR"].xref_id == "1956" and g._nodes["EGFR"].y == 40
    e = g._edges_list()[0]
    assert (e._n1._name, e._n2._name, e.arrow) == ("EGFR", "GRB2", "mim-binding")
    k = tmp_path / "k.xml"
    k.write_text(KGML)
    assert s.run(f"makeFromKGML({str(k)!r})")
    grp = next(n for n in s.graph._nodes_list() if n.kind == "group")
    assert grp.y > 200 and grp.width == 8


def test_make_from_url_recognises_the_formats(s, tmp_path, monkeypatch):
    from guess import bioformats, connectors
    monkeypatch.chdir(tmp_path)
    pages = {"https://x.org/interactions": MITAB25, "https://x.org/model.xml": SBML2,
             "https://x.org/data?id=1": PSI25, "https://x.org/p.owl": BIOPAX, "https://x.org/map": KGML,
             "https://x.org/wp/WP1": GPML}
    monkeypatch.setattr(connectors, "http", lambda url, **kw: pages[url])
    expect = {"https://x.org/interactions": "TP53", "https://x.org/model.xml": "G6P",
              "https://x.org/data?id=1": "MDM2", "https://x.org/p.owl": "ProtA", "https://x.org/map": "MDM2",
              "https://x.org/wp/WP1": "GLC"}
    for url, name in expect.items():
        assert s.run(f"makeFromURL({url!r})"), (url, s.rec.of("error"))
        assert any(n.label == name or n._name == name for n in s.graph._nodes_list()), url
    assert bioformats.sniff("Source,Target\na,b\n", ".csv") is None
    assert bioformats.sniff("<graphml/>", ".graphml") is None
