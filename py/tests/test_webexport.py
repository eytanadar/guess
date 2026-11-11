"""Import and export formats of webexport.py: JSON (graphology / sigma), KML,
shapefiles, Excel, co-occurrence, RDF (Turtle, N-Triples, RDF/XML) and Bluesky."""
import base64
import io
import json
import struct
import xml.etree.ElementTree as ET
import zipfile

import pytest

from guess import connectors
from tests.test_gython import Recorder, s  # noqa: F401  (fixture)


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def download(s, name):
    d = [m for m in s.rec.of("download") if m["name"] == name]
    assert d, s.rec.of("error")
    return d[-1]


# ---- JSON ----------------------------------------------------------------------

def test_export_json_graphology(s, here):
    assert s.run('bob.color = red; bob.x = 10; bob.y = 20; bob.label = "Bob"')
    assert s.run('exportJSON("g.json")'), s.rec.of("error")
    data = json.loads(download(s, "g.json")["text"])
    assert data["options"]["type"] == "mixed"           # the small graph has both kinds
    nodes = {n["key"]: n["attributes"] for n in data["nodes"]}
    assert nodes["bob"]["label"] == "Bob" and nodes["bob"]["color"] == "#ff0000"
    assert nodes["bob"]["x"] == 10 and nodes["bob"]["y"] == -20   # y points up
    assert nodes["alice"]["dept"] == "IT" and "visible" not in nodes["alice"]
    assert len(data["edges"]) == 4
    e = next(e for e in data["edges"] if {e["source"], e["target"]} == {"bob", "alice"})
    assert e["attributes"]["freq"] == 10 and e.get("undirected") is True


def test_export_json_sigma_and_bad_format(s, here):
    assert s.run('exportJSON("s.json", format="sigma")')
    data = json.loads(download(s, "s.json")["text"])
    n = next(n for n in data["nodes"] if n["id"] == "bob")
    assert {"label", "x", "y", "size", "color", "attributes"} <= set(n)
    assert n["attributes"]["jobfunc"] == "Manager"
    assert any(e.get("type") == "arrow" for e in data["edges"])
    assert not s.run('exportJSON("x.json", format="d3")')
    assert "graphology" in s.rec.of("error")[-1]["text"]


# ---- geography -----------------------------------------------------------------

GEO = """\
nodedef> name,lat DOUBLE,lon DOUBLE,city VARCHAR(20)
a,42.28,-83.74,Ann Arbor
b,41.88,-87.63,Chicago
c,,,Nowhere
edgedef> node1,node2,directed BOOLEAN,kind VARCHAR(10)
a,b,true,road
a,c,false,air
"""


@pytest.fixture
def geo(s, here):
    p = here / "geo.gdf"
    p.write_text(GEO)
    assert s.run(f"makeFromGDF({str(p)!r})")
    s.rec.clear()
    return s


def test_export_kml(geo, here):
    assert geo.run('a.color = "#102030"')
    assert geo.run('exportKML("g.kml")'), geo.rec.of("error")
    root = ET.fromstring(download(geo, "g.kml")["text"])
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    marks = root.findall(".//k:Placemark", ns)
    points = [m for m in marks if m.find("k:Point", ns) is not None]
    lines = [m for m in marks if m.find("k:LineString", ns) is not None]
    assert len(points) == 2 and len(lines) == 1          # c has no coordinates
    a = next(m for m in points if m.find("k:name", ns).text == "a")
    assert a.find(".//k:coordinates", ns).text.startswith("-83.740000,42.280000")
    style = a.find("k:styleUrl", ns).text[1:]
    color = root.find(f".//k:Style[@id='{style}']//k:color", ns).text
    assert color == "ff302010"                          # aabbggrr
    assert any(d.get("name") == "city" for d in a.findall(".//k:Data", ns))


def test_export_kml_needs_coordinates(s, here):
    assert not s.run('exportKML("x.kml")')
    assert "latitude" in s.rec.of("error")[-1]["text"]


def _read_shp(data):
    code, = struct.unpack(">i", data[:4])
    length, = struct.unpack(">i", data[24:28])
    version, shape = struct.unpack("<ii", data[28:36])
    box = struct.unpack("<4d", data[36:68])
    recs, pos = [], 100
    while pos < len(data):
        num, clen = struct.unpack(">ii", data[pos:pos + 8])
        content = data[pos + 8:pos + 8 + clen * 2]
        stype, = struct.unpack("<i", content[:4])
        if stype == 1:
            recs.append(struct.unpack("<dd", content[4:20]))
        else:
            nparts, npts = struct.unpack("<ii", content[36:44])
            pts = content[44 + 4 * nparts:]
            recs.append([struct.unpack("<dd", pts[16 * k:16 * k + 16]) for k in range(npts)])
        assert num == len(recs)
        pos += 8 + clen * 2
    return code, length * 2, version, shape, box, recs


def _read_dbf(data):
    n, head_len, rec_len = struct.unpack("<IHH", data[4:12])
    fields, pos = [], 32
    while data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\0")[0].decode()
        kind = chr(data[pos + 11])
        width = data[pos + 16]
        fields.append((name, kind, width))
        pos += 32
    rows = []
    for k in range(n):
        r = data[head_len + k * rec_len:head_len + (k + 1) * rec_len]
        off, row = 1, {}
        for name, kind, width in fields:
            row[name] = r[off:off + width].decode("utf-8").strip()
            off += width
        rows.append(row)
    assert data[-1] == 0x1A
    return fields, rows


def test_export_shapefiles(geo, here):
    assert geo.run('exportSHP("g.zip")'), geo.rec.of("error")
    msg = download(geo, "g.zip")
    data = base64.b64decode(msg["b64"])
    assert (here / "g.zip").read_bytes() == data
    z = zipfile.ZipFile(io.BytesIO(data))
    assert {"nodes.shp", "nodes.shx", "nodes.dbf", "nodes.prj", "edges.shp", "edges.dbf", "edges.prj"} <= set(z.namelist())
    code, length, version, shape, box, pts = _read_shp(z.read("nodes.shp"))
    assert (code, version, shape) == (9994, 1000, 1) and length == len(z.read("nodes.shp"))
    assert sorted(pts) == sorted([(-83.74, 42.28), (-87.63, 41.88)])
    assert box == (-87.63, 41.88, -83.74, 42.28)
    shx = z.read("nodes.shx")
    assert struct.unpack(">i", shx[24:28])[0] * 2 == len(shx) == 100 + 8 * 2
    fields, rows = _read_dbf(z.read("nodes.dbf"))
    assert ("city", "C") in [(f[0], f[1]) for f in fields]
    assert {r["name"]: r["city"] for r in rows} == {"a": "Ann Arbor", "b": "Chicago"}
    _c, _l, _v, shape, _b, lines = _read_shp(z.read("edges.shp"))
    assert shape == 3 and lines == [[(-83.74, 42.28), (-87.63, 41.88)]]
    fields, rows = _read_dbf(z.read("edges.dbf"))
    assert rows == [dict(rows[0], source="a", target="b", directed="T", kind="road")]
    assert "WGS_1984" in z.read("nodes.prj").decode()


# ---- Excel -------------------------------------------------------------------------

def make_xlsx(path, sheets):
    """A minimal .xlsx: sheets {name: rows}; strings go to sharedStrings, numbers inline."""
    shared, idx = [], {}

    def col(k):
        s = ""
        k += 1
        while k:
            k, r = divmod(k - 1, 26)
            s = chr(65 + r) + s
        return s
    xml_sheets = []
    for rows in sheets.values():
        out = []
        for i, row in enumerate(rows, 1):
            cells = []
            for k, v in enumerate(row):
                ref = f"{col(k)}{i}"
                if v is None:
                    continue
                if isinstance(v, bool):
                    cells.append(f'<c r="{ref}" t="b"><v>{int(v)}</v></c>')
                elif isinstance(v, (int, float)):
                    cells.append(f'<c r="{ref}"><v>{v}</v></c>')
                elif v.startswith("inline:"):
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{v[7:]}</t></is></c>')
                else:
                    if v not in idx:
                        idx[v] = len(shared)
                        shared.append(v)
                    cells.append(f'<c r="{ref}" t="s"><v>{idx[v]}</v></c>')
            out.append(f'<row r="{i}">{"".join(cells)}</row>')
        xml_sheets.append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                          f'<sheetData>{"".join(out)}</sheetData></worksheet>')
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>' + "".join(
            f'<sheet name="{n}" sheetId="{k + 1}" r:id="rId{k + 1}"/>' for k, n in enumerate(sheets))
            + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
                       f'<Relationship Id="rId{k + 1}" Target="worksheets/sheet{k + 1}.xml" Type="x"/>'
                       for k in range(len(sheets))) + "</Relationships>")
        for k, x in enumerate(xml_sheets):
            z.writestr(f"xl/worksheets/sheet{k + 1}.xml", x)
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{main}">' + "".join(
            f"<si><t>{t}</t></si>" if k % 2 else f"<si><r><t>{t[:1]}</t></r><r><t>{t[1:]}</t></r></si>"
            for k, t in enumerate(shared)) + "</sst>")


def test_make_from_excel_edges_and_nodes(s, here):
    make_xlsx(here / "w.xlsx", {
        "People": [["Id", "Label", "age", "staff"], ["p1", "Ann", 34, True], ["p2", "Bo", 29, False],
                   ["p3", "inline:Cy", 41.5, True]],
        "Ties": [["Source", "Target", "Weight", "kind"], ["p1", "p2", 2, "work"], ["p2", "p3", 1.5, "home"]],
    })
    assert s.run('makeFromExcel("w.xlsx")'), s.rec.of("error")
    g = s.graph
    assert len(g._nodes) == 3 and len(g._edges) == 2
    p1, p3 = g._nodes["p1"], g._nodes["p3"]
    assert p1.label == "Ann" and p1.age == 34 and p1.staff is True
    assert p3.label == "Cy" and p3.age == 41.5
    e = next(e for e in g._edges_list() if e._n2._name == "p3")
    assert e.weight == 1.5 and e.kind == "home"
    # makeFromCSV hands .xlsx over; a sheet by number
    assert s.run('makeFromCSV("w.xlsx")') and len(s.graph._edges) == 2
    assert s.run('makeFromExcel("w.xlsx", sheet=1, nodes="People")') and s.graph._nodes["p2"].label == "Bo"
    assert not s.run('makeFromExcel("w.xlsx", sheet="Nope")')
    assert "People" in s.rec.of("error")[-1]["text"]


def test_make_from_excel_not_a_workbook(s, here):
    (here / "bad.xlsx").write_text("hello")
    assert not s.run('makeFromExcel("bad.xlsx")')
    assert "isn't an Excel" in s.rec.of("error")[-1]["text"]


def test_cooccurrence_csv_and_xlsx(s, here):
    (here / "papers.csv").write_text("title,authors\nP1,Ann; Bo; Cy\nP2,Ann;Bo\nP3,Dee\n")
    assert s.run('makeFromCooccurrence("papers.csv")'), s.rec.of("error")
    g = s.graph
    assert sorted(g._nodes) == ["Ann", "Bo", "Cy", "Dee"]
    assert g._nodes["Ann"].count == 2
    ab = next(e for e in g._edges_list() if {e._n1._name, e._n2._name} == {"Ann", "Bo"})
    assert ab.weight == 2 and len(g._edges) == 3
    assert s.run('makeFromCooccurrence("papers.csv", "authors", keep=false)') and "Dee" not in s.graph._nodes
    make_xlsx(here / "k.xlsx", {"S": [["kw"], ["a|b"], ["b|c|a"]]})
    assert s.run('makeFromCooccurrence("k.xlsx", 0, "|")') and len(s.graph._edges) == 3
    assert not s.run('makeFromCooccurrence("papers.csv", "nope")')


# ---- RDF ---------------------------------------------------------------------------

TURTLE = r'''
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix ex: <http://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# people
ex:alice a foaf:Person ;
    foaf:name "Alice"@en, "Alicia"@es ;
    foaf:age 34 ;
    ex:height "1.68"^^xsd:decimal ;
    ex:active true ;
    foaf:knows ex:bob, <http://example.org/carol> .
ex:bob a foaf:Person ; foaf:name """Bob "the" builder""" ; foaf:knows [ foaf:name "Dan" ; ex:pet ex:rex ] .
<http://example.org/carol> rdfs:label 'Carolé' ; foaf:age 51 .
_:x1 foaf:knows ex:alice .
'''


def test_turtle(s, here):
    (here / "f.ttl").write_text(TURTLE)
    assert s.run('makeFromRDF("f.ttl")'), s.rec.of("error")
    g = s.graph
    alice = g._nodes["alice"]
    assert alice.label == "Alice" and alice.uri == "http://example.org/alice"
    assert alice.age == 34 and alice.height_ == 1.68 and alice.active is True
    assert g.node_schema["age"].type == "INTEGER"
    assert g._nodes["bob"].label == 'Bob "the" builder' and g._nodes["carol"].label == "Carolé"
    knows = [(e._n1.label, e._n2.label) for e in g._edges_list() if e.predicate == "knows"]
    assert ("Alice", "Bob \"the\" builder") in knows and ("Alice", "Carolé") in knows
    assert any(a == "Bob \"the\" builder" and b == "Dan" for a, b in knows)          # [ … ] blank node
    assert any(b == "Alice" for a, b in knows if a != "Bob \"the\" builder")         # _:x1
    person = g._nodes["Person"]
    assert sum(1 for e in g._edges_list() if e._n2 is person and e.predicate == "type") == 2
    # types as a field instead
    assert s.run('makeFromRDF("f.ttl", types=false)') and "Person" not in s.graph._nodes
    assert s.graph._nodes["alice"].type == "Person"


def test_ntriples_and_errors(s, here):
    (here / "d.nt").write_text(
        '<http://e.org/a> <http://e.org/p> <http://e.org/b> .\n'
        '<http://e.org/a> <http://www.w3.org/2000/01/rdf-schema#label> "A \\"q\\"" .\n'
        '_:n <http://e.org/p> <http://e.org/a> .\n')
    assert s.run('makeFromRDF("d.nt")'), s.rec.of("error")
    assert s.graph._nodes["a"].label == 'A "q"' and len(s.graph._edges) == 2
    (here / "bad.ttl").write_text("ex:a ex:b ex:c .")
    assert not s.run('makeFromRDF("bad.ttl")')
    assert "prefix" in s.rec.of("error")[-1]["text"]
    (here / "col.ttl").write_text("@prefix ex: <http://e.org/> .\nex:a ex:b ( ex:c ) .")
    assert not s.run('makeFromRDF("col.ttl")')
    assert "collections" in s.rec.of("error")[-1]["text"]


RDFXML = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:foaf="http://xmlns.com/foaf/0.1/"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/">
  <foaf:Person rdf:about="alice" foaf:nick="ali">
    <foaf:name xml:lang="en">Alice</foaf:name>
    <foaf:age rdf:datatype="http://www.w3.org/2001/XMLSchema#integer">34</foaf:age>
    <foaf:knows rdf:resource="bob"/>
    <foaf:knows>
      <foaf:Person rdf:about="carol"><foaf:name>Carol</foaf:name></foaf:Person>
    </foaf:knows>
    <foaf:based_near rdf:parseType="Resource"><foaf:name>Ann Arbor</foaf:name></foaf:based_near>
  </foaf:Person>
  <rdf:Description rdf:about="bob"><rdfs:label>Bob</rdfs:label></rdf:Description>
</rdf:RDF>
"""


def test_rdfxml(s, here):
    (here / "f.rdf").write_text(RDFXML)
    assert s.run('makeFromRDF("f.rdf")'), s.rec.of("error")
    g = s.graph
    alice = g._nodes["alice"]
    assert alice.label == "Alice" and alice.age == 34 and alice.nick == "ali"
    assert alice.uri == "http://example.org/alice"
    pairs = {(e._n1._name, e.predicate, e._n2.label) for e in g._edges_list()}
    assert ("alice", "knows", "Bob") in pairs and ("alice", "knows", "Carol") in pairs
    assert ("alice", "based_near", "Ann Arbor") in pairs
    assert ("carol", "type", "Person") in pairs
    # makeFromURL recognises RDF by content too
    assert s.run('makeFromRDF("f.rdf", format="xml")')


# ---- Bluesky ----------------------------------------------------------------------

def fake_bsky(monkeypatch, follows, profiles=None, fail_profiles=False):
    calls = []

    def http(url, method="GET", body=None, headers=None):
        from urllib.parse import parse_qs, urlparse
        u = urlparse(url)
        q = parse_qs(u.query)
        method_name = u.path.rsplit("/", 1)[-1]
        calls.append((method_name, q))
        actor = q.get("actor", [None])[0]
        if method_name == "app.bsky.graph.getFollows":
            me = next((a for a in follows if actor in (a, "did:" + a)), None)
            if me is None:
                raise connectors.GuessError(f"{url}: HTTP 400 Bad Request")
            people = [{"did": "did:" + h, "handle": h, "displayName": h.upper()} for h in follows[me]]
            start = int(q.get("cursor", ["0"])[0])
            n = int(q["limit"][0])
            page = people[start:start + n]
            out = {"subject": {"did": "did:" + me, "handle": me, "displayName": me.title()}, "follows": page}
            if start + n < len(people):
                out["cursor"] = str(start + n)
            return json.dumps(out)
        if method_name == "app.bsky.graph.getFollowers":
            fans = [h for h, fs in follows.items() if actor.removeprefix("did:") in fs]
            return json.dumps({"subject": {"did": actor if actor.startswith("did:") else "did:" + actor,
                                           "handle": actor.removeprefix("did:")},
                               "followers": [{"did": "did:" + h, "handle": h} for h in fans]})
        if method_name == "app.bsky.actor.getProfiles":
            if fail_profiles:
                raise connectors.GuessError("HTTP 500")
            return json.dumps({"profiles": [dict({"did": d, "followersCount": 7, "postsCount": 3},
                                                 **(profiles or {}).get(d, {})) for d in q["actors"]]})
        raise AssertionError(url)
    monkeypatch.setattr(connectors, "http", http)
    return calls


def test_bluesky_follows(s, monkeypatch):
    calls = fake_bsky(monkeypatch, {"me.bsky.social": ["a.bsky.social", "b.bsky.social", "c.bsky.social"],
                                    "a.bsky.social": ["b.bsky.social", "z.bsky.social"]},
                      {"did:a.bsky.social": {"description": "hi"}})
    assert s.run('makeFromBluesky("@me.bsky.social", limit=2)'), s.rec.of("error")
    g = s.graph
    assert sorted(g._nodes) == ["a.bsky.social", "b.bsky.social", "me.bsky.social"]     # limit=2, paged
    assert len(g._edges) == 2 and all(e._directed and e._n1._name == "me.bsky.social" for e in g._edges_list())
    a = g._nodes["a.bsky.social"]
    assert a.label == "A.BSKY.SOCIAL" and a.followers == 7 and a.posts == 3 and a.description == "hi"
    assert a.did == "did:a.bsky.social"
    assert [c[0] for c in calls].count("app.bsky.graph.getFollows") == 1       # one page reaches the limit
    # depth 2 adds a's follows (z) and the a -> b tie; maxNodes caps it
    assert s.run('makeFromBluesky("me.bsky.social", depth=2)')
    names = set(s.graph._nodes)
    assert "z.bsky.social" in names
    assert any(e._n1._name == "a.bsky.social" and e._n2._name == "b.bsky.social" for e in s.graph._edges_list())
    assert s.run('makeFromBluesky("me.bsky.social", depth=2, maxNodes=3)') and len(s.graph._nodes) == 3


def test_bluesky_followers_errors_and_missing_profiles(s, monkeypatch):
    fake_bsky(monkeypatch, {"me.bsky.social": ["a.bsky.social"], "a.bsky.social": ["me.bsky.social"]},
              fail_profiles=True)
    assert s.run('makeFromBluesky("me.bsky.social", mode="both")'), s.rec.of("error")
    g = s.graph
    assert {(e._n1._name, e._n2._name) for e in g._edges_list()} == {("me.bsky.social", "a.bsky.social"),
                                                                     ("a.bsky.social", "me.bsky.social")}
    assert g._nodes["a.bsky.social"].followers is None                  # profiles failed: still a network
    assert not s.run('makeFromBluesky("nobody.bsky.social")')
    assert "check the handle" in s.rec.of("error")[-1]["text"]
    assert not s.run('makeFromBluesky("me.bsky.social", mode="likes")')


def test_make_from_url_recognises_rdf(s, here, monkeypatch):
    monkeypatch.setattr(connectors, "http", lambda url, **k: "@prefix ex: <http://e.org/> .\nex:a ex:p ex:b .\n")
    assert s.run('makeFromURL("https://e.org/data")'), s.rec.of("error")
    assert sorted(s.graph._nodes) == ["a", "b"]
    monkeypatch.setattr(connectors, "http", lambda url, **k: RDFXML)
    assert s.run('makeFromURL("https://e.org/foaf")') and "alice" in s.graph._nodes
