"""Getting data in from the web: URLs, SPARQL (Wikidata), NDEx and Neo4j, and
installing extra Python packages.

    makeFromURL("https://example.org/graph.gexf")
    rows = sparql("SELECT ?item WHERE { ... } LIMIT 10")
    makeFromSPARQL(query)              ?source ?target [?sourceLabel ?targetLabel ...]
    makeFromNDEx("<network uuid>")     a public network from ndexbio.org
    makeFromCypher("MATCH p=()-->() RETURN p LIMIT 200", "http://localhost:7474", "neo4j", "pw")
    installPackage("python-louvain")   pip-install a pure-Python package (micropip)

Requests are made from the browser (a synchronous request inside the Python
worker), so the server must allow cross-origin requests (CORS); Wikidata,
NDEx and Neo4j's HTTP API do.
"""
import base64
import json
import os
import random
import re
import urllib.parse

from .model import DOUBLE, INT, STRING, GuessError


def http(url, method="GET", body=None, headers=None):
    """Fetch a URL synchronously and return the response text."""
    headers = dict(headers or {})
    try:
        import js  # Pyodide: synchronous XMLHttpRequest is allowed in a worker
    except ImportError:
        js = None
    if js is not None and hasattr(js, "XMLHttpRequest"):
        req = js.XMLHttpRequest.new()
        req.open(method, url, False)
        for k, v in headers.items():
            req.setRequestHeader(k, v)
        try:
            req.send(body)
        except Exception as e:  # noqa: BLE001 - network errors surface as JS exceptions
            raise GuessError(f"could not fetch {url}: {e} (the server may not allow cross-origin requests)") from None
        if not 200 <= req.status < 300:
            raise GuessError(f"{url}: HTTP {req.status} {req.statusText}")
        return str(req.responseText)
    import urllib.request
    data = body.encode() if isinstance(body, str) else body
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=60) as resp:  # noqa: S310 - user-supplied URL by design
        return resp.read().decode("utf-8", errors="replace")


_LOADERS = [(".gdf", "makeFromGDF"), (".gexf", "makeFromGEXF"), (".graphml", "makeFromGraphML"),
            (".xml", "makeFromGraphML"), (".gml", "makeFromGML"), (".dot", "makeFromDOT"), (".gv", "makeFromDOT"), (".net", "makeFromPajek"), (".paj", "makeFromPajek"),
            (".dl", "makeFromDL"), (".csv", "makeFromCSV"), (".tsv", "makeFromCSV"),
            (".guess", "makeFromSession"), (".py", "execfile")]


def install(session):
    g = session.graph

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def loader(name):
        return session.system[name][0]

    @cmd
    def makeFromURL(url, format=None):
        """makeFromURL(url) downloads a graph (GDF, GEXF, GraphML, GML, DOT, Pajek, DL, CSV, a
        .guess session or a .py script) and opens it; format=".gexf" etc. when
        the URL doesn't end in the extension."""
        text = http(url)
        path = urllib.parse.urlparse(url).path
        ext = (format or os.path.splitext(path)[1] or "").lower()
        if not ext.startswith("."):
            ext = "." + ext
        if ext not in dict(_LOADERS):
            head = text.lstrip()[:200].lower()
            ext = (".gexf" if "<gexf" in head else ".graphml" if "<graphml" in head
                   else ".gdf" if head.startswith("nodedef") else ".net" if head.startswith("*vertices")
                   else ".gml" if re.match(r"(#[^\n]*\n\s*)*(creator\s|version\s|graph\s*\[)", head)
                   else ".dot" if re.match(r"(strict\s+)?(di)?graph\b[^{]*\{", head)
                   else ".guess" if '"guess-session"' in text[:400] else ".csv")
        name = os.path.basename(path) or "download"
        if not name.lower().endswith(ext):
            name += ext
        with open(name, "w", encoding="utf-8") as fh:
            fh.write(text)
        loader(dict(_LOADERS)[ext])(name)

    # ---- SPARQL ---------------------------------------------------------------
    WIKIDATA = "https://query.wikidata.org/sparql"

    @cmd
    def sparql(query, endpoint=WIKIDATA):
        """sparql(query[, endpoint]) runs a SPARQL query (Wikidata by default) and
        returns the rows as a list of {variable: value} dicts."""
        url = f"{endpoint}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
        data = json.loads(http(url, headers={"Accept": "application/sparql-results+json"}))
        return [{k: _term(v) for k, v in row.items()} for row in data["results"]["bindings"]]

    @cmd
    def makeFromSPARQL(query, endpoint=WIKIDATA, directed=True):
        """makeFromSPARQL(query) builds a graph from a SPARQL query whose rows bind
        ?source and ?target (optionally ?sourceLabel / ?targetLabel, used as
        labels; any other variables become edge fields). E.g. a Wikidata query
        for "influenced by" links."""
        rows = sparql(query, endpoint)
        if rows and not {"source", "target"} <= set(rows[0]):
            raise GuessError("the query must bind ?source and ?target")
        g.clear()
        extra = sorted({k for r in rows for k in r} - {"source", "target", "sourceLabel", "targetLabel"})
        for k in extra:
            g.addEdgeField(_ident(k), STRING, None)
        for r in rows:
            a = _node(g, r["source"], r.get("sourceLabel"))
            b = _node(g, r["target"], r.get("targetLabel"))
            e = g.addEdge(a, b, bool(directed))
            for k in extra:
                if k in r:
                    setattr(e, _ident(k), str(r[k]))
        _scatter(g)
        session.scene()
        print(f"built {len(g._nodes)} nodes, {len(g._edges)} edges from {len(rows)} rows")

    # ---- NDEx -----------------------------------------------------------------
    @cmd
    def makeFromNDEx(uuid, server="https://www.ndexbio.org"):
        """makeFromNDEx(uuid) opens a public network from the NDEx repository
        (Cytoscape's network commons), with its attributes and layout."""
        cx = json.loads(http(f"{server}/v3/networks/{uuid}"))
        aspects = {}
        for a in cx:
            for k, v in a.items():
                aspects.setdefault(k, []).extend(v if isinstance(v, list) else [v])
        nodes, edges = aspects.get("nodes", []), aspects.get("edges", [])
        if not nodes:
            raise GuessError("no nodes in that network (is it public?)")
        g.clear()
        decl = (aspects.get("attributeDeclarations") or [{}])[0]
        for kind, add in (("nodes", g.addNodeField), ("edges", g.addEdgeField)):
            for attr, spec in (decl.get(kind) or {}).items():
                t = {"integer": INT, "long": INT, "double": DOUBLE}.get(spec.get("d"), STRING)
                if attr not in ("name",):
                    add(_ident(attr), t, None)
        index = {}
        for nrec in nodes:
            v = nrec.get("v", {})
            label = v.get("name", str(nrec["id"]))
            n = g.addNode(f"n{nrec['id']}")
            n.label = str(label)
            for k, val in v.items():
                if k != "name":
                    _set(n, _ident(k), val)
            if "x" in nrec:
                n.x, n.y = float(nrec["x"]), float(nrec.get("y", 0))
            else:
                n.x, n.y = random.random() * 800, random.random() * 800
            index[nrec["id"]] = n
        for erec in edges:
            e = g.addEdge(index[erec["s"]], index[erec["t"]], True)
            for k, val in erec.get("v", {}).items():
                _set(e, _ident(k), val)
        session.scene()
        name = (aspects.get("networkAttributes") or [{}])[0].get("name", uuid)
        print(f"loaded NDEx network {name!r}: {len(g._nodes)} nodes, {len(g._edges)} edges")

    # ---- Neo4j ------------------------------------------------------------------
    @cmd
    def makeFromCypher(query, url="http://localhost:7474", user=None, password=None, database="neo4j"):
        """makeFromCypher(query, url, user, password) runs a Cypher query on a
        Neo4j server's HTTP API and builds the graph from the nodes and
        relationships it returns (properties become fields)."""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if user is not None:
            headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{password or ''}".encode()).decode()
        body = json.dumps({"statements": [{"statement": query, "resultDataContents": ["graph"]}]})
        res = json.loads(http(f"{url.rstrip('/')}/db/{database}/tx/commit", "POST", body, headers))
        if res.get("errors"):
            raise GuessError(res["errors"][0].get("message", "Cypher error"))
        g.clear()
        index, seen = {}, set()
        for result in res.get("results", []):
            for row in result.get("data", []):
                graph = row.get("graph", {})
                for nrec in graph.get("nodes", []):
                    if nrec["id"] in index:
                        continue
                    props = nrec.get("properties", {})
                    n = g.addNode(f"n{nrec['id']}")
                    n.label = str(props.get("name") or props.get("title") or (nrec.get("labels") or ["node"])[0])
                    if nrec.get("labels"):
                        g.addNodeField("kind", STRING, None)
                        n.kind = nrec["labels"][0]
                    for k, val in props.items():
                        _set(n, _ident(k), val, create=g.addNodeField)
                    index[nrec["id"]] = n
                for r in graph.get("relationships", []):
                    if r["id"] in seen:
                        continue
                    seen.add(r["id"])
                    e = g.addEdge(index[r["startNode"]], index[r["endNode"]], True)
                    g.addEdgeField("type", STRING, None)
                    e.type = r.get("type")
                    for k, val in r.get("properties", {}).items():
                        _set(e, _ident(k), val, create=g.addEdgeField)
        _scatter(g)
        session.scene()
        print(f"loaded {len(g._nodes)} nodes, {len(g._edges)} relationships from Neo4j")

    # ---- extra packages ------------------------------------------------------
    @cmd
    def installPackage(name):
        """installPackage("name") installs a Python package into this session
        (pure-Python wheels from PyPI, or Pyodide's own packages such as scipy),
        in the background; a note appears when it's ready to import."""
        session.emit({"type": "install", "name": str(name)})
        print(f"installing {name}…")


def _term(v):
    t, val = v.get("type"), v.get("value")
    if t == "literal" and v.get("datatype", "").endswith(("#integer", "#int", "#long")):
        try:
            return int(val)
        except ValueError:
            return val
    if t == "literal" and v.get("datatype", "").endswith(("#double", "#decimal", "#float")):
        try:
            return float(val)
        except ValueError:
            return val
    return val


def _ident(s):
    import re
    s = re.sub(r"\W", "_", str(s)) or "attr"
    return "_" + s if s[0].isdigit() else s


def _node(g, uri, label=None):
    key = str(uri).rsplit("/", 1)[-1] or str(uri)
    n = g._nodes.get(key) or g.addNode(key)
    if label:
        n.label = str(label)
    return n


def _set(elem, name, value, create=None):
    if isinstance(value, (list, dict)):
        value = json.dumps(value)
    schema = elem._g.node_schema if create is None or create.__name__ == "addNodeField" else elem._g.edge_schema
    if create is not None and name not in schema:
        t = INT if isinstance(value, int) and not isinstance(value, bool) else DOUBLE if isinstance(value, float) else STRING
        create(name, t, None)
    try:
        setattr(elem, name, value)
    except Exception:  # noqa: BLE001 - skip values that don't fit the field
        pass


def _scatter(g):
    for n in g._nodes_list():
        n.x, n.y = random.random() * 800, random.random() * 800
