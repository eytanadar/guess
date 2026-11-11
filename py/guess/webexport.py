"""More ways in and out: spreadsheets, RDF, Bluesky, and JSON (sigma.js),
KML (Google Earth) and shapefiles (GIS) out. The Gephi plugins Excel/CSV
importer, SemanticWebImport, Bluesky Gephi, JSON Exporter, SigmaExporter,
ExportToEarth and SHPExporter, without extra packages.

    makeFromExcel("people.xlsx")            an edge sheet (Source, Target, ...), and a node sheet (Id, ...)
    makeFromCooccurrence("papers.csv", "authors")   link values sharing a cell
    makeFromRDF("foaf.ttl")                 Turtle, N-Triples or RDF/XML
    makeFromBluesky("alice.bsky.social")    who an account follows
    exportJSON("graph.json")                graphology / sigma.js (format="sigma": the older sigma JSON)
    exportKML("graph.kml")                  Google Earth: nodes as placemarks, edges as lines
    exportSHP("graph.zip")                  shapefiles: points and lines, with fields
"""
import base64
import io
import itertools
import json
import math
import os
import random
import re
import struct
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import escape

from . import colors, connectors, gexf
from .geo import LAT_NAMES, LON_NAMES
from .model import BOOL, DOUBLE, INT, STRING, Field, GuessError

# fields every node and edge has that say how it's drawn, not what it is
_PLUMBING = {"name", "x", "y", "visible", "color", "strokecolor", "labelcolor", "fixed", "style", "width",
             "height", "label", "image", "labelvisible", "labelpos", "labelsize", "node1", "node2",
             "directed", "source", "destination", "weight"}


def _offer_bytes(session, filename, data):
    """Write a binary file and offer it as a download (the page decodes b64)."""
    with open(filename, "wb") as fh:
        fh.write(data)
    session.emit({"type": "download", "name": os.path.basename(filename), "text": "",
                  "b64": base64.b64encode(data).decode()})


def _offer_text(session, filename, text):
    with open(filename, "w", encoding="utf-8") as fh:
        fh.write(text)
    session.emit({"type": "download", "name": os.path.basename(filename), "text": text})


def _data_fields(schema):
    """The fields that are data (dept, freq, computed ones already used), not drawing."""
    return [f for f in schema.values() if f.name not in _PLUMBING and not f.name.startswith("_")]


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    return str(v)


def _hex(c):
    r, g, b, _a = colors.parse(c, (128, 128, 128, 255))
    return f"#{r:02x}{g:02x}{b:02x}"


def _get(f, e):
    try:
        return f.get(e)
    except Exception:  # noqa: BLE001 - a computed field that can't be computed here
        return None


# --------------------------------------------------------------------------
# JSON (graphology / sigma.js)
# --------------------------------------------------------------------------

def to_json(g, format="graphology"):  # noqa: A002
    """The graph as graphology's serialised form (or the older sigma JSON)."""
    nf, ef = _data_fields(g.node_schema), _data_fields(g.edge_schema)

    def node_attrs(n):
        a = {"label": n.label if n.label is not None else n._name, "x": n.x, "y": -n.y,
             "size": max(n.width, n.height) / 2, "color": _hex(n.color)}
        if not n.visible:
            a["hidden"] = True
        for f in nf:
            a[f.name] = _jsonable(_get(f, n))
        return a

    def edge_attrs(e):
        a = {"weight": _jsonable(e.weight), "size": e.width, "color": _hex(e.color)}
        if e.label:
            a["label"] = e.label
        if not e.visible:
            a["hidden"] = True
        for f in ef:
            a[f.name] = _jsonable(_get(f, e))
        return a

    nodes, edges = g._nodes_list(), g._edges_list()
    if format == "sigma":
        out_nodes = []
        for n in nodes:
            a = node_attrs(n)
            out_nodes.append({"id": n._name, "label": a.pop("label"), "x": a.pop("x"), "y": a.pop("y"),
                              "size": a.pop("size"), "color": a.pop("color"), "attributes": a})
        out_edges = []
        for e in edges:
            a = edge_attrs(e)
            rec = {"id": str(e._id), "source": e._n1._name, "target": e._n2._name,
                   "size": a.pop("size"), "color": a.pop("color"), "attributes": a}
            if "label" in a:
                rec["label"] = a.pop("label")
            if e._directed:
                rec["type"] = "arrow"
            out_edges.append(rec)
        return {"nodes": out_nodes, "edges": out_edges}
    if format != "graphology":
        raise GuessError('exportJSON format is "graphology" (sigma.js 2 and later) or "sigma" (older sigma.js)')
    directed = [e._directed for e in edges]
    kind = "directed" if directed and all(directed) else "undirected" if not any(directed) else "mixed"
    multi = len({frozenset((e._n1._id, e._n2._id)) for e in edges}) < len(edges)
    out = {"attributes": {"name": getattr(g, "name", None) or "graph"},
           "options": {"type": kind, "multi": multi, "allowSelfLoops": True},
           "nodes": [{"key": n._name, "attributes": node_attrs(n)} for n in nodes],
           "edges": []}
    for e in edges:
        rec = {"key": str(e._id), "source": e._n1._name, "target": e._n2._name, "attributes": edge_attrs(e)}
        if kind == "mixed" and not e._directed:
            rec["undirected"] = True
        out["edges"].append(rec)
    return out


# --------------------------------------------------------------------------
# geography: KML and shapefiles
# --------------------------------------------------------------------------

def _geo_fields(g, lat, lon, what):
    def pick(f, names, label):
        if isinstance(f, Field):
            return f
        if isinstance(f, str) and f in g.node_schema:
            return g.node_schema[f]
        if f is None:
            for nm in names:
                if nm in g.node_schema:
                    return g.node_schema[nm]
        raise GuessError(f"{what} needs a {label} field (looked for {', '.join(names)}); "
                         f"name it, e.g. {what}(lat=\"y_coord\", lon=\"x_coord\")")
    return pick(lat, LAT_NAMES, "latitude"), pick(lon, LON_NAMES, "longitude")


def _coords(g, flat, flon):
    out = {}
    for n in g._nodes_list():
        try:
            la, lo = float(flat.get(n)), float(flon.get(n))
        except (TypeError, ValueError):
            continue
        if math.isfinite(la) and math.isfinite(lo) and -90 <= la <= 90:
            out[n._id] = (lo, la)
    return out


def _kml_color(c, alpha=None):
    r, g, b, a = colors.parse(c, (128, 128, 128, 255))
    return f"{alpha if alpha is not None else a:02x}{b:02x}{g:02x}{r:02x}"


def to_kml(g, flat, flon):
    pos = _coords(g, flat, flon)
    nf, ef = _data_fields(g.node_schema), _data_fields(g.edge_schema)
    styles, out = {}, []

    def style(kind, c, width=None):
        key = (kind, _kml_color(c), width)
        if key not in styles:
            sid = f"s{len(styles)}"
            if kind == "n":
                body = (f"<IconStyle><color>{key[1]}</color><scale>0.8</scale>"
                        "<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>"
                        "</IconStyle>")
            else:
                body = f"<LineStyle><color>{key[1]}</color><width>{width:g}</width></LineStyle>"
            styles[key] = (sid, body)
        return styles[key][0]

    def extended(e, fields):
        rows = [f'<Data name="{escape(f.name)}"><value>{escape(str(v))}</value></Data>'
                for f in fields for v in [_get(f, e)] if v is not None]
        return f"<ExtendedData>{''.join(rows)}</ExtendedData>" if rows else ""

    places = []
    for n in g._nodes_list():
        if n._id not in pos:
            continue
        lo, la = pos[n._id]
        name = n.label if n.label is not None else n._name
        places.append(f"<Placemark><name>{escape(str(name))}</name><styleUrl>#{style('n', n.color)}</styleUrl>"
                      f"{extended(n, nf)}<Point><coordinates>{lo:.6f},{la:.6f},0</coordinates></Point></Placemark>")
    lines = []
    for e in g._edges_list():
        a, b = pos.get(e._n1._id), pos.get(e._n2._id)
        if a is None or b is None:
            continue
        lines.append(f"<Placemark><name>{escape(repr(e))}</name><styleUrl>#{style('e', e.color, max(1.0, e.width))}"
                     f"</styleUrl>{extended(e, ef)}<LineString><tessellate>1</tessellate><coordinates>"
                     f"{a[0]:.6f},{a[1]:.6f},0 {b[0]:.6f},{b[1]:.6f},0</coordinates></LineString></Placemark>")
    out.append('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>')
    out.append(f"<name>{escape(getattr(g, 'name', None) or 'GUESS graph')}</name>")
    out.extend(f'<Style id="{sid}">{body}</Style>' for sid, body in styles.values())
    out.append("<Folder><name>Nodes</name>" + "".join(places) + "</Folder>")
    out.append("<Folder><name>Edges</name>" + "".join(lines) + "</Folder>")
    out.append("</Document></kml>\n")
    return "\n".join(out), len(places), len(lines), len(g._nodes) - len(places)


_PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')


def _shp(shape_type, shapes):
    """(.shp bytes, .shx bytes) for points [(x, y)] or polylines [[(x, y), ...]]."""
    recs = []
    for i, s in enumerate(shapes, 1):
        if shape_type == 1:
            content = struct.pack("<idd", 1, s[0], s[1])
        else:
            xs, ys = [p[0] for p in s], [p[1] for p in s]
            content = struct.pack("<i4dii", 3, min(xs), min(ys), max(xs), max(ys), 1, len(s))
            content += struct.pack("<i", 0) + b"".join(struct.pack("<dd", *p) for p in s)
        recs.append(struct.pack(">ii", i, len(content) // 2) + content)
    pts = [p for s in shapes for p in ([s] if shape_type == 1 else s)]
    box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)) \
        if pts else (0.0, 0.0, 0.0, 0.0)

    def header(length_bytes):
        return (struct.pack(">i5ii", 9994, 0, 0, 0, 0, 0, length_bytes // 2)
                + struct.pack("<ii4d4d", 1000, shape_type, *box, 0.0, 0.0, 0.0, 0.0))
    body = b"".join(recs)
    shp = header(100 + len(body)) + body
    index, off = [], 50
    for r in recs:
        index.append(struct.pack(">ii", off, (len(r) - 8) // 2))
        off += len(r) // 2
    shx = header(100 + 8 * len(recs)) + b"".join(index)
    return shp, shx


def _dbf(columns, rows):
    """dBASE III table. columns: [(name, GUESS type)]; rows: lists of values."""
    used, specs = set(), []
    for name, ftype in columns:
        short = re.sub(r"[^A-Za-z0-9_]", "_", name)[:10] or "field"
        k = 1
        while short.upper() in used:
            k += 1
            short = f"{short[:10 - len(str(k)) - 1]}_{k}"
        used.add(short.upper())
        if ftype == INT:
            specs.append((short, "N", 18, 0))
        elif ftype == DOUBLE:
            specs.append((short, "N", 24, 8))
        elif ftype == BOOL:
            specs.append((short, "L", 1, 0))
        else:
            width = max([1] + [len(str(r[i]).encode("utf-8")) for r in rows
                               for i in [len(specs)] if r[i] is not None])
            specs.append((short, "C", min(254, width), 0))

    def cell(v, spec):
        _n, kind, width, dec = spec
        if kind == "L":
            return b"?" if v is None else (b"T" if v else b"F")
        if kind == "N":
            try:
                x = float(v)
                if not math.isfinite(x):
                    raise ValueError
                s = f"{int(round(x))}" if dec == 0 else f"{x:.{dec}f}"
            except (TypeError, ValueError):
                s = ""
            return s.rjust(width)[:width].encode("ascii")
        raw = ("" if v is None else str(v)).encode("utf-8")[:width]
        return raw.ljust(width, b" ")

    rec_len = 1 + sum(s[2] for s in specs)
    head_len = 32 + 32 * len(specs) + 1
    out = struct.pack("<BBBBIHH20x", 3, 126, 1, 1, len(rows), head_len, rec_len)
    for name, kind, width, dec in specs:
        out += struct.pack("<11sc4xBB14x", name.encode("ascii"), kind.encode("ascii"), width, dec)
    out += b"\r"
    for r in rows:
        out += b" " + b"".join(cell(v, s) for v, s in zip(r, specs))
    return out + b"\x1a"


def to_shapefiles(g, flat, flon):
    """{filename: bytes} for nodes.* (points) and edges.* (lines)."""
    pos = _coords(g, flat, flon)
    nf = [f for f in _data_fields(g.node_schema) if f not in (flat, flon)]
    ef = _data_fields(g.edge_schema)
    nodes = [n for n in g._nodes_list() if n._id in pos]
    edges = [e for e in g._edges_list() if e._n1._id in pos and e._n2._id in pos]
    files = {}
    ncols = [("name", STRING), ("label", STRING), ("color", STRING)] + [(f.name, f.type) for f in nf]
    nrows = [[n._name, n.label, _hex(n.color)] + [_get(f, n) for f in nf] for n in nodes]
    files["nodes.shp"], files["nodes.shx"] = _shp(1, [pos[n._id] for n in nodes])
    files["nodes.dbf"] = _dbf(ncols, nrows)
    ecols = [("source", STRING), ("target", STRING), ("directed", BOOL), ("weight", DOUBLE),
             ("color", STRING)] + [(f.name, f.type) for f in ef]
    erows = [[e._n1._name, e._n2._name, e._directed, e.weight, _hex(e.color)] + [_get(f, e) for f in ef]
             for e in edges]
    files["edges.shp"], files["edges.shx"] = _shp(3, [[pos[e._n1._id], pos[e._n2._id]] for e in edges])
    files["edges.dbf"] = _dbf(ecols, erows)
    for stem in ("nodes", "edges"):
        files[f"{stem}.prj"] = _PRJ.encode()
        files[f"{stem}.cpg"] = b"UTF-8"
    return files, len(nodes), len(edges), len(g._nodes) - len(nodes)


# --------------------------------------------------------------------------
# Excel (.xlsx), without openpyxl
# --------------------------------------------------------------------------

_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    k = 0
    for ch in letters:
        k = k * 26 + ord(ch) - 64
    return k - 1


def read_xlsx(path):
    """{sheet name: rows of strings} in workbook order."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as ex:
        raise GuessError(f"{os.path.basename(str(path))} isn't an Excel .xlsx file ({ex})") from None
    with z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            # plain <si><t>…</t></si>, or rich text: runs <r><t>…</t></r>; phonetic runs (rPh) left out
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(_X + "si"):
                parts = []
                for child in si:
                    if child.tag == _X + "t":
                        parts.append(child.text or "")
                    elif child.tag == _X + "r":
                        parts.extend(t.text or "" for t in child.iter(_X + "t"))
                shared.append("".join(parts))
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
                target = rel.get("Target", "")
                target = target.lstrip("/") if target.startswith("/") else "xl/" + target
                rels[rel.get("Id")] = target
        book = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = {}
        for sh in book.iter(_X + "sheet"):
            target = rels.get(sh.get(_R + "id"))
            if not target or target not in names:
                continue
            rows = []
            for row in ET.fromstring(z.read(target)).iter(_X + "row"):
                cells = {}
                for k, c in enumerate(row.iter(_X + "c")):
                    ref = c.get("r")
                    col = _col_index(ref) if ref else k
                    t = c.get("t")
                    v = c.find(_X + "v")
                    if t == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(_X + "t"))
                    elif t == "b" and v is not None:
                        val = "true" if v.text == "1" else "false"
                    elif t == "e":
                        val = ""
                    elif v is not None and v.text is not None:
                        val = v.text
                        if t not in ("str",):
                            try:
                                x = float(val)
                                val = str(int(x)) if x.is_integer() and abs(x) < 1e15 else repr(x)
                            except ValueError:
                                pass
                    else:
                        val = ""
                    cells[col] = val
                if cells:
                    r = [""] * (max(cells) + 1)
                    for col, val in cells.items():
                        r[col] = val
                    rows.append(r)
            sheets[sh.get("name")] = rows
    return sheets


def _pick_sheet(sheets, which, path):
    names = list(sheets)
    if isinstance(which, int) and not isinstance(which, bool):
        if not 0 <= which < len(names):
            raise GuessError(f"{os.path.basename(path)} has sheets 0 to {len(names) - 1}")
        return names[which]
    if which not in sheets:
        raise GuessError(f"{os.path.basename(path)} has no sheet {which!r} (it has {', '.join(map(repr, names))})")
    return which


def _table_rows(path, sheet=None):
    """Rows of strings from a .csv/.tsv or one sheet of an .xlsx."""
    if str(path).lower().endswith((".xlsx", ".xlsm")):
        sheets = read_xlsx(path)
        if not sheets:
            raise GuessError(f"{os.path.basename(path)} has no sheets")
        return sheets[_pick_sheet(sheets, 0 if sheet is None else sheet, path)]
    with open(path, encoding="utf-8", errors="replace") as fh:
        return gexf._rows(fh.read())


# --------------------------------------------------------------------------
# RDF: N-Triples, Turtle, RDF/XML
# --------------------------------------------------------------------------

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"
_LABELS = (RDFS + "label", "http://xmlns.com/foaf/0.1/name", "http://www.w3.org/2004/02/skos/core#prefLabel",
           "http://purl.org/dc/elements/1.1/title", "http://purl.org/dc/terms/title", "http://schema.org/name",
           "https://schema.org/name")

# terms: ("iri", s) | ("bnode", id) | ("lit", value, lang, datatype)

_TOKEN = re.compile(r'''
    (?P<ws>\s+|\#[^\n]*)
  | (?P<iri><[^<>"{}|^`\\\s]*>)
  | (?P<lit3>"""(?:[^"\\]|\\.|"(?!""))*"""|\'\'\'(?:[^'\\]|\\.|'(?!''))*\'\'\')
  | (?P<lit>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')
  | (?P<lang>@[A-Za-z]+(?:-[A-Za-z0-9]+)*)
  | (?P<dt>\^\^)
  | (?P<bnode>_:[A-Za-z0-9_][\w.\-]*(?<!\.))
  | (?P<num>[+-]?(?:\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+|\d+))
  | (?P<pname>(?:[A-Za-z][\w\-.]*(?<!\.))?:(?:[\w\-:%]|\.(?=[\w\-:%]))*)
  | (?P<word>[A-Za-z]+)
  | (?P<punct>[.;,\[\]()])
''', re.X)

_ESC = {"t": "\t", "b": "\b", "n": "\n", "r": "\r", "f": "\f", '"': '"', "'": "'", "\\": "\\"}


def _unescape(s):
    def rep(m):
        x = m.group(1)
        if x[0] in "uU":
            return chr(int(x[1:], 16))
        return _ESC.get(x, x)
    return re.sub(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)", rep, s)


def _tokens(text):
    pos, out = 0, []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            line = text.count("\n", 0, pos) + 1
            raise GuessError(f"Turtle: can't read {text[pos:pos + 20]!r} on line {line}")
        pos = m.end()
        kind = m.lastgroup
        if kind != "ws":
            out.append((kind, m.group(kind), text.count("\n", 0, m.start()) + 1))
    return out


def parse_turtle(text, base=""):
    """Triples from Turtle (or N-Triples, a subset of it)."""
    toks = _tokens(text)
    prefixes, triples = {}, []
    state = {"i": 0, "base": base, "blank": 0}

    def peek(k=0):
        j = state["i"] + k
        return toks[j] if j < len(toks) else (None, None, toks[-1][2] if toks else 0)

    def take():
        t = peek()
        state["i"] += 1
        return t

    def fail(msg):
        raise GuessError(f"Turtle: {msg} on line {peek()[2]}")

    def expect(value):
        kind, v, _ = take()
        if v != value:
            state["i"] -= 1
            fail(f"expected {value!r}, found {v!r}")

    def new_blank():
        state["blank"] += 1
        return ("bnode", f"b{state['blank']}")

    def iri(raw):
        return urllib.parse.urljoin(state["base"], _unescape(raw[1:-1])) if state["base"] else _unescape(raw[1:-1])

    def pname(raw):
        pre, _, local = raw.partition(":")
        if pre not in prefixes:
            fail(f"the prefix {pre + ':'!r} isn't declared")
        return prefixes[pre] + re.sub(r"\\(.)", r"\1", local)

    def term(allow_literal=True):
        kind, v, _ = peek()
        if kind == "iri":
            take()
            return ("iri", iri(v))
        if kind == "pname":
            take()
            return ("iri", pname(v))
        if kind == "bnode":
            take()
            return ("bnode", v[2:])
        if v == "[":
            take()
            b = new_blank()
            if peek()[1] != "]":
                predicate_objects(b)
            expect("]")
            return b
        if v == "(":
            fail("RDF collections ( … ) aren't supported")
        if not allow_literal:
            fail(f"expected a resource, found {v!r}")
        if kind in ("lit", "lit3"):
            take()
            q = 3 if kind == "lit3" else 1
            value, lang, dt = _unescape(v[q:-q]), None, None
            if peek()[0] == "lang":
                lang = take()[1][1:].lower()
            elif peek()[0] == "dt":
                take()
                t = term(False)
                dt = t[1]
            return ("lit", value, lang, dt)
        if kind == "num":
            take()
            dt = XSD + ("integer" if re.fullmatch(r"[+-]?\d+", v) else "double" if "e" in v.lower() else "decimal")
            return ("lit", v, None, dt)
        if kind == "word" and v in ("true", "false"):
            take()
            return ("lit", v, None, XSD + "boolean")
        fail(f"unexpected {v!r}")

    def predicate_objects(subject):
        while True:
            kind, v, _ = peek()
            if kind == "word" and v == "a":
                take()
                pred = RDF + "type"
            else:
                t = term(False)
                pred = t[1]
            while True:
                triples.append((subject, pred, term()))
                if peek()[1] != ",":
                    break
                take()
            if peek()[1] != ";":
                return
            while peek()[1] == ";":
                take()
            if peek()[1] in (".", "]", None):
                return

    while state["i"] < len(toks):
        kind, v, _ = peek()
        if kind == "lang" and v in ("@prefix", "@base") or (kind == "word" and v.upper() in ("PREFIX", "BASE")):
            take()
            directive = v.lstrip("@").lower()
            if directive == "prefix":
                k, p, _ = take()
                if k != "pname" or not p.endswith(":"):
                    fail("expected a prefix such as foaf:")
                k, u, _ = take()
                if k != "iri":
                    fail("expected <IRI> after the prefix")
                prefixes[p[:-1]] = iri(u)
            else:
                k, u, _ = take()
                if k != "iri":
                    fail("expected <IRI> after base")
                state["base"] = iri(u)
            if v.startswith("@"):
                expect(".")
            continue
        subject = term(False)
        if not (subject[0] == "bnode" and peek()[1] == "."):
            predicate_objects(subject)
        expect(".")
    return triples


def parse_rdfxml(text, base=""):
    """Triples from RDF/XML (node and property elements, rdf:about/ID/nodeID,
    rdf:resource, property attributes, parseType="Resource", typed nodes)."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as ex:
        raise GuessError(f"RDF/XML: {ex}") from None
    triples, count = [], [0]
    XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"
    XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

    def iri_of(tag):
        return tag[1:].replace("}", "", 1) if tag.startswith("{") else tag

    def blank():
        count[0] += 1
        return ("bnode", f"x{count[0]}")

    def subject_of(el, b):
        if el.get(RDF_ + "about") is not None:
            return ("iri", urllib.parse.urljoin(b, el.get(RDF_ + "about")))
        if el.get(RDF_ + "ID") is not None:
            return ("iri", urllib.parse.urljoin(b, "#" + el.get(RDF_ + "ID")))
        if el.get(RDF_ + "nodeID") is not None:
            return ("bnode", el.get(RDF_ + "nodeID"))
        return blank()

    RDF_ = "{" + RDF + "}"
    SKIP = {RDF_ + k for k in ("about", "ID", "nodeID", "resource", "parseType", "datatype", "type")}

    def node(el, b, lang):
        b = urllib.parse.urljoin(b, el.get(XML_BASE)) if el.get(XML_BASE) else b
        lang = el.get(XML_LANG, lang)
        s = subject_of(el, b)
        if el.tag != RDF_ + "Description":
            triples.append((s, RDF + "type", ("iri", iri_of(el.tag))))
        if el.get(RDF_ + "type"):
            triples.append((s, RDF + "type", ("iri", urllib.parse.urljoin(b, el.get(RDF_ + "type")))))
        for k, v in el.attrib.items():
            if k in SKIP or k.startswith("{http://www.w3.org/XML/1998/namespace}") or not k.startswith("{"):
                continue
            triples.append((s, iri_of(k), ("lit", v, lang, None)))
        properties(el, s, b, lang)
        return s

    def properties(el, s, b, lang):
        for p in el:
            pred = iri_of(p.tag)
            plang = p.get(XML_LANG, lang)
            if p.get(RDF_ + "resource") is not None:
                triples.append((s, pred, ("iri", urllib.parse.urljoin(b, p.get(RDF_ + "resource")))))
            elif p.get(RDF_ + "nodeID") is not None:
                triples.append((s, pred, ("bnode", p.get(RDF_ + "nodeID"))))
            elif p.get(RDF_ + "parseType") == "Resource":
                o = blank()
                triples.append((s, pred, o))
                properties(p, o, b, plang)
            elif len(p):
                triples.append((s, pred, node(p[0], b, plang)))
            else:
                extra = {k: v for k, v in p.attrib.items() if k not in SKIP and k.startswith("{")
                         and not k.startswith("{http://www.w3.org/XML/1998/namespace}")}
                if extra:                       # property attributes on an empty property: a blank node
                    o = blank()
                    triples.append((s, pred, o))
                    for k, v in extra.items():
                        triples.append((o, iri_of(k), ("lit", v, plang, None)))
                else:
                    dt = p.get(RDF_ + "datatype")
                    triples.append((s, pred, ("lit", p.text or "", None if dt else plang, dt)))

    base = urllib.parse.urljoin(base, root.get(XML_BASE)) if root.get(XML_BASE) else base
    tops = list(root) if root.tag == RDF_ + "RDF" else [root]
    for el in tops:
        node(el, base, root.get(XML_LANG))
    return triples


def _local_name(uri):
    s = str(uri).rstrip("/#")
    for sep in ("#", "/", ":"):
        if sep in s:
            s = s.rsplit(sep, 1)[-1]
            break
    return urllib.parse.unquote(s) or str(uri)


def _typed(value, dt):
    if dt in (XSD + "integer", XSD + "int", XSD + "long", XSD + "short", XSD + "nonNegativeInteger",
              XSD + "positiveInteger", XSD + "negativeInteger", XSD + "nonPositiveInteger"):
        try:
            return int(value), INT
        except ValueError:
            pass
    if dt in (XSD + "decimal", XSD + "double", XSD + "float"):
        try:
            return float(value), DOUBLE
        except ValueError:
            pass
    if dt == XSD + "boolean":
        return value.strip().lower() in ("true", "1"), BOOL
    return value, STRING


def build_rdf(g, triples, types=True):
    """Resources as nodes, resource-valued properties as edges (with
    `predicate`), literal properties as node fields. Returns (nodes, edges)."""
    resources, labels, names = {}, {}, {}
    lits = {}                     # (term, predicate) -> [values]
    links = []
    for s, p, o in triples:
        resources.setdefault(s, None)
        if o[0] == "lit":
            if p in _LABELS:
                lang = o[2]
                old = labels.get(s)
                # prefer English or untagged labels, then the first
                if old is None or (old[1] not in (None, "en") and lang in (None, "en")):
                    labels[s] = (o[1], lang)
            lits.setdefault((s, p), []).append(o)
        else:
            if p == RDF + "type" and not types:
                lits.setdefault((s, p), []).append(("lit", _local_name(o[1]), None, None))
                continue
            resources.setdefault(o, None)
            links.append((s, p, o))
    used = set()
    for t in resources:
        base = _local_name(t[1]) if t[0] == "iri" else f"_{t[1]}"
        base = base.strip() or "resource"
        name, k = base, 1
        while name in used:
            k += 1
            name = f"{base}_{k}"
        used.add(name)
        names[t] = name
    # literal fields: one per predicate, typed when every value agrees
    by_pred = {}
    for (s, p), vals in lits.items():
        if p in _LABELS:
            continue
        by_pred.setdefault(p, []).append((s, vals))
    fields = {}
    for p, items in by_pred.items():
        fname = gexf._field_name(_local_name(p) if p != RDF + "type" else "type", g.node_schema)
        while fname in fields.values():
            fname += "_"
        typed = [_typed(v[1], v[3]) for _s, vals in items for v in vals]
        kinds = {t for _v, t in typed}
        ftype = kinds.pop() if len(kinds) == 1 else STRING
        fields[p] = fname
        if fname not in g.node_schema:
            g.addNodeField(fname, ftype, None)
    if "uri" not in g.node_schema:
        g.addNodeField("uri", STRING, None)
    if "predicate" not in g.edge_schema:
        g.addEdgeField("predicate", STRING, None)
    nodes = {}
    for t, name in names.items():
        n = g.addNode(name)
        n.label = labels[t][0] if t in labels else (_local_name(t[1]) if t[0] == "iri" else name)
        if t[0] == "iri":
            n.uri = t[1]
        n.x, n.y = random.random() * 800, random.random() * 800
        nodes[t] = n
    for (s, p), vals in lits.items():
        if p in _LABELS or p not in fields:
            continue
        f = g.node_schema[fields[p]]
        if f.type == STRING:
            # several values (names in different languages, keywords): prefer one
            # untagged or English value for a short field; keep them all otherwise
            pick = [v for v in vals if v[2] in (None, "en")] or vals
            seen = list(dict.fromkeys(str(v[1]) for v in pick))
            value = seen[0] if len(seen) == 1 else "; ".join(seen)
        else:
            value = _typed(vals[0][1], vals[0][3])[0]
        try:
            setattr(nodes[s], fields[p], value)
        except (GuessError, ValueError, TypeError):
            pass
    for s, p, o in links:
        e = g.addEdge(nodes[s], nodes[o], True)
        e.predicate = _local_name(p) if p != RDF + "type" else "type"
        e.label = e.predicate
    return len(nodes), len(links)


# --------------------------------------------------------------------------
# Bluesky
# --------------------------------------------------------------------------

BSKY = "https://public.api.bsky.app/xrpc/"


def _bsky(method, **params):
    url = BSKY + method + "?" + urllib.parse.urlencode(params, doseq=True)
    try:
        return json.loads(connectors.http(url))
    except GuessError as ex:
        if "HTTP 400" in str(ex):
            raise GuessError(f"Bluesky doesn't know {params.get('actor', params.get('actors'))!r}: "
                             "check the handle (e.g. alice.bsky.social)") from None
        raise


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    @cmd
    def exportJSON(filename="graph.json", format="graphology"):  # noqa: A002
        """exportJSON("graph.json") writes the graph for sigma.js and graphology
        (graph.import(data)): nodes with label, x, y, size, colour and every data
        field, edges with weight, size, colour and fields; hidden elements are
        marked hidden. format="sigma" writes the older sigma.js JSON ({nodes:
        [{id, label, x, y, size, color, attributes}], edges: [...]}) that
        Gephi's JSON Exporter makes. Offered as a download."""
        data = to_json(session.graph, format)
        _offer_text(session, filename, json.dumps(data, indent=1, ensure_ascii=False))
        print(f"wrote {len(data['nodes'])} nodes, {len(data['edges'])} edges to {os.path.basename(filename)}")

    @cmd
    def exportKML(filename="graph.kml", lat=None, lon=None):
        """exportKML("graph.kml") writes the graph for Google Earth and other
        maps: each node with coordinates a placemark (its colour, label and
        fields), each edge between two placed nodes a line (its colour and
        width). Coordinates come from the latitude/lat and longitude/lon/lng
        fields, or name them: exportKML("x.kml", lat="y", lon="x"). Offered as
        a download."""
        g = session.graph
        flat, flon = _geo_fields(g, lat, lon, "exportKML")
        text, nn, ne, missing = to_kml(g, flat, flon)
        _offer_text(session, filename, text)
        note = f" ({missing} nodes without coordinates left out)" if missing else ""
        print(f"wrote {nn} placemarks and {ne} lines to {os.path.basename(filename)}{note}")

    @cmd
    def exportSHP(filename="graph.zip", lat=None, lon=None):
        """exportSHP("graph.zip") writes shapefiles for GIS (QGIS, ArcGIS) in a
        zip: nodes.shp (points, with name, label, colour and the node fields)
        and edges.shp (lines between placed nodes, with source, target,
        weight, colour and the edge fields), in WGS 84 longitude/latitude.
        Coordinates come from latitude/lat and longitude/lon/lng fields, or
        name them with lat= and lon=. Field names are cut to 10 characters,
        as the format requires. Offered as a download."""
        g = session.graph
        flat, flon = _geo_fields(g, lat, lon, "exportSHP")
        files, nn, ne, missing = to_shapefiles(g, flat, flon)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in files.items():
                z.writestr(name, data)
        _offer_bytes(session, filename, buf.getvalue())
        note = f" ({missing} nodes without coordinates left out)" if missing else ""
        print(f"wrote {nn} points and {ne} lines to {os.path.basename(filename)}{note}")

    @cmd
    def makeFromExcel(filename, sheet=None, nodes=None, directed=False):
        """makeFromExcel("data.xlsx") replaces the graph with an Excel workbook
        read as makeFromCSV reads tables: an edge sheet (Source, Target[, Type,
        Weight, Label, ...]), an adjacency matrix or list; with a node sheet
        (Id[, Label, ...]) too when the workbook has one. sheet= picks the edge
        sheet by name or number (0 = first); nodes= names the node sheet, or
        another file (.xlsx or .csv). Other columns become fields; directed=true
        makes edges without a Type directed. makeFromCSV("data.xlsx") does the same."""
        g = session.graph
        sheets = read_xlsx(filename)
        if not sheets:
            raise GuessError(f"{os.path.basename(filename)} has no sheets")
        kinds = {name: gexf.rows_kind([[c.strip() for c in r] for r in rows])[0] if rows else "empty"
                 for name, rows in sheets.items()}
        if sheet is None:
            sheet = next((n for n, k in kinds.items() if k == "edges"), None) or next(
                (n for n, k in kinds.items() if k in ("matrix", "list")), None) or next(iter(sheets))
        else:
            sheet = _pick_sheet(sheets, sheet, filename)
        node_rows = None
        if nodes is None:
            other = next((n for n, k in kinds.items() if k == "nodes" and n != sheet), None)
            if other is not None and kinds[sheet] != "nodes":
                node_rows, nodes_from = sheets[other], f"sheet {other!r}"
        elif isinstance(nodes, str) and os.path.exists(nodes) and nodes not in sheets:
            node_rows, nodes_from = _table_rows(nodes), os.path.basename(nodes)
        else:
            nodes_from = _pick_sheet(sheets, nodes, filename)
            node_rows = sheets[nodes_from]
            nodes_from = f"sheet {nodes_from!r}"
        kind = kinds[sheet]
        if kind == "nodes" and node_rows is None and len(g._nodes):
            _k, added, _ne = gexf.read_csv(g, None, rows=sheets[sheet])
            session.scene()
            print(f"node sheet {sheet!r}: {added} new nodes, {len(g._nodes) - added} updated")
            return
        g.clear()
        kind, _nn, ne = gexf.read_csv(g, None, bool(directed), rows=sheets[sheet])
        extra = ""
        if node_rows is not None:
            _k, more, _ = gexf.read_csv(g, None, rows=node_rows)
            extra = f", nodes from {nodes_from}"
        session.scene()
        what = "edge table" if kind == "edges" else "adjacency " + kind if kind in ("matrix", "list") else kind
        print(f"loaded {len(g._nodes)} nodes, {ne} edges from {os.path.basename(filename)} "
              f"(sheet {sheet!r}: {what}{extra})")

    @cmd
    def makeFromCooccurrence(filename, column=None, separator=";", sheet=None, keep=True):
        """makeFromCooccurrence("papers.csv", "authors") builds a network of the
        values that share a cell: each row's list (split at separator, ";" by
        default; also "," or "|") links every pair in it, as co-authors on a
        paper or keywords on an article. Nodes get `count` (rows they appear
        in); edges `weight` (rows they share). Works on .csv, .tsv and .xlsx
        (sheet= picks a sheet); column= is a header name or a number (0 =
        first; default: the first column whose cells hold lists). keep=true
        also adds a node for a value that never shares a row."""
        g = session.graph
        rows = _table_rows(filename, sheet)
        if len(rows) < 2:
            raise GuessError(f"{os.path.basename(filename)} needs a header row and at least one row of data")
        head = rows[0]
        if column is None:
            col = next((k for k in range(len(head))
                        if any(separator in (r[k] if k < len(r) else "") for r in rows[1:])), None)
            if col is None:
                raise GuessError(f"no column holds lists separated by {separator!r}: "
                                 f"name the column and separator, e.g. makeFromCooccurrence(file, \"authors\", \",\")")
        elif isinstance(column, int) and not isinstance(column, bool):
            col = column
        else:
            low = [h.strip().lower() for h in head]
            if str(column).strip().lower() not in low:
                raise GuessError(f"no column {column!r} (the columns are {', '.join(map(repr, head))})")
            col = low.index(str(column).strip().lower())
        counts, pairs = {}, {}
        for r in rows[1:]:
            vals = list(dict.fromkeys(v.strip() for v in (r[col] if col < len(r) else "").split(separator)
                                      if v.strip()))
            for v in vals:
                counts[v] = counts.get(v, 0) + 1
            for a, b in itertools.combinations(sorted(vals), 2):
                pairs[(a, b)] = pairs.get((a, b), 0) + 1
        g.clear()
        g.addNodeField("count", INT, 0)
        linked = {v for p in pairs for v in p}
        for v, c in counts.items():
            if keep or v in linked:
                n = g.addNode(v)
                n.label = v
                n.count = c
                n.x, n.y = random.random() * 800, random.random() * 800
        for (a, b), w in pairs.items():
            g.addEdge(g._nodes[a], g._nodes[b], False, weight=float(w))
        session.scene()
        print(f"built {len(g._nodes)} nodes, {len(pairs)} edges from {len(rows) - 1} rows "
              f"of {head[col] if col < len(head) else 'column ' + str(col)!r}")

    @cmd
    def makeFromRDF(filename, format=None, types=True):  # noqa: A002
        """makeFromRDF("data.ttl") replaces the graph with RDF data (Turtle,
        N-Triples or RDF/XML, by extension or content; format="turtle", "nt"
        or "xml" to say). Each resource becomes a node (labelled by rdfs:label,
        foaf:name, skos:prefLabel or its local name; its IRI in `uri`), each
        property linking two resources an edge (its name in `predicate`), and
        each literal property a node field (numbers and booleans typed).
        types=false keeps rdf:type as a `type` field instead of edges to class
        nodes. For SPARQL endpoints use makeFromSPARQL."""
        g = session.graph
        with open(filename, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        fmt = (format or "").lower().lstrip(".")
        if not fmt:
            ext = os.path.splitext(str(filename))[1].lower()
            fmt = {".nt": "nt", ".ttl": "turtle", ".n3": "turtle", ".rdf": "xml", ".owl": "xml",
                   ".xml": "xml"}.get(ext, "")
            if not fmt:
                head = text.lstrip()[:400]
                fmt = "xml" if head.startswith("<?xml") or "<rdf:RDF" in head else "turtle"
        base = "file:///" + os.path.basename(str(filename))
        if fmt in ("xml", "rdfxml", "rdf/xml", "rdf", "owl"):
            triples = parse_rdfxml(text, base)
        elif fmt in ("turtle", "ttl", "nt", "ntriples", "n-triples", "n3"):
            triples = parse_turtle(text, base)
        else:
            raise GuessError('makeFromRDF format is "turtle", "nt" or "xml"')
        if not triples:
            raise GuessError(f"no RDF triples in {os.path.basename(filename)}")
        g.clear()
        nn, ne = build_rdf(g, triples, bool(types))
        session.scene()
        print(f"loaded {nn} nodes, {ne} edges from {len(triples)} triples in {os.path.basename(filename)}")

    @cmd
    def makeFromBluesky(handle, depth=1, limit=100, mode="follows", maxNodes=500):
        """makeFromBluesky("alice.bsky.social") opens a Bluesky account's
        network from the public API: the account and up to `limit` accounts it
        follows, with directed "follows" edges. mode="followers" fetches who
        follows it instead, "both" both. depth=2 also fetches the same for
        each account found, adding the ties among them and new accounts, up
        to maxNodes accounts in all. Nodes get handle, did, followers,
        follows, posts and description; labels are display names."""
        g = session.graph
        if mode not in ("follows", "followers", "both"):
            raise GuessError('mode is "follows", "followers" or "both"')
        handle = str(handle).strip().lstrip("@")
        if not handle:
            raise GuessError('makeFromBluesky needs a handle, e.g. makeFromBluesky("alice.bsky.social")')
        depth, limit, cap = max(1, int(depth)), max(1, int(limit)), max(1, int(maxNodes))
        accounts, edges = {}, set()

        def remember(a):
            did = a.get("did")
            if did and did not in accounts:
                if len(accounts) >= cap:
                    return None
                accounts[did] = dict(a)
            return did if did in accounts else None

        def page(method, key, actor):
            out, cursor = [], None
            while len(out) < limit:
                params = {"actor": actor, "limit": min(100, limit - len(out))}
                if cursor:
                    params["cursor"] = cursor
                data = _bsky(method, **params)
                out.extend(data.get(key, []))
                cursor = data.get("cursor")
                if not cursor or not data.get(key):
                    break
            return data.get("subject"), out[:limit]

        frontier = [handle]
        for level in range(depth):
            nxt = []
            for actor in frontier:
                for method, key, outward in (("app.bsky.graph.getFollows", "follows", True),
                                             ("app.bsky.graph.getFollowers", "followers", False)):
                    if mode == "follows" and not outward or mode == "followers" and outward:
                        continue
                    try:
                        subject, people = page(method, key, actor)
                    except GuessError:
                        if level == 0:
                            raise
                        continue             # a private or deleted account further out: skip it
                    me = remember(subject) if subject else None
                    if not me:
                        continue
                    for p in people:
                        known = p.get("did") in accounts
                        other = remember(p)
                        if other is None:
                            continue
                        edges.add((me, other) if outward else (other, me))
                        if not known and level + 1 < depth:
                            nxt.append(other)
            frontier = nxt
        if not accounts:
            raise GuessError(f"Bluesky returned nothing for {handle!r}")
        # counts (followers, follows, posts) come with full profiles, 25 at a time
        dids = list(accounts)
        for k in range(0, len(dids), 25):
            try:
                for prof in _bsky("app.bsky.actor.getProfiles", actors=dids[k:k + 25]).get("profiles", []):
                    if prof.get("did") in accounts:
                        accounts[prof["did"]].update(prof)
            except GuessError:
                break                        # the network is still useful without the counts
        g.clear()
        for name, ftype in (("handle", STRING), ("did", STRING), ("followers", INT), ("follows", INT),
                            ("posts", INT), ("description", STRING)):
            g.addNodeField(name, ftype, None)
        nodes = {}
        for did, a in accounts.items():
            n = g.addNode(a.get("handle") or did)
            n.label = a.get("displayName") or a.get("handle") or did
            n.handle, n.did = a.get("handle"), did
            for f, key in (("followers", "followersCount"), ("follows", "followsCount"), ("posts", "postsCount")):
                if isinstance(a.get(key), int):
                    setattr(n, f, a[key])
            if a.get("description"):
                n.description = a["description"]
            n.x, n.y = random.random() * 800, random.random() * 800
            nodes[did] = n
        for a, b in edges:
            g.addEdge(nodes[a], nodes[b], True)
        session.scene()
        print(f"built {len(nodes)} accounts and {len(edges)} follows around {handle}")


__all__ = ["install", "to_json", "to_kml", "to_shapefiles", "read_xlsx", "parse_turtle", "parse_rdfxml",
           "build_rdf"]
