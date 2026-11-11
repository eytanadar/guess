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

from .model import BOOL, DOUBLE, INT, STRING, GuessError


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
    # outside the browser: some services (Wikidata) refuse urllib's default agent
    headers.setdefault("User-Agent", "GUESS-graph-exploration-system/1.0 (+https://github.com/eytanadar/guess)")
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=60) as resp:  # noqa: S310 - user-supplied URL by design
        return resp.read().decode("utf-8", errors="replace")


_LOADERS = [(".gdf", "makeFromGDF"), (".gexf", "makeFromGEXF"), (".graphml", "makeFromGraphML"),
            (".xml", "makeFromGraphML"), (".gml", "makeFromGML"), (".dot", "makeFromDOT"), (".gv", "makeFromDOT"), (".net", "makeFromPajek"), (".paj", "makeFromPajek"),
            (".dl", "makeFromDL"), (".csv", "makeFromCSV"), (".tsv", "makeFromCSV"),
            (".ttl", "makeFromRDF"), (".nt", "makeFromRDF"), (".n3", "makeFromRDF"), (".rdf", "makeFromRDF"),
            (".owl", "makeFromRDF"),
            (".sif", "makeFromSIF"), (".nnf", "makeFromNNF"), (".cyjs", "makeFromCYJS"),
            (".cx", "makeFromCX"), (".cx2", "makeFromCX"), (".xgmml", "makeFromXGMML"),
            (".guess", "makeFromSession"), (".py", "execfile"),
            (".mitab", "makeFromMITAB"), (".psimitab", "makeFromMITAB"), (".mif", "makeFromPSIMI"),
            (".psi", "makeFromPSIMI"), (".sbml", "makeFromSBML"), (".kgml", "makeFromKGML"),
            (".gpml", "makeFromGPML"), (".biopax", "makeFromBioPAX")]


# extensions that don't say which format a file is in: look inside
_AMBIGUOUS = {"", ".xml", ".txt", ".tab", ".json", ".owl", ".rdf", ".dat", ".tsv", ".csv"}


def detect_format(text, ext, forced=False):
    """The loader extension for a file's text: its own extension when that
    names one format, otherwise what the content looks like (the biological
    formats, XGMML, CX, Cytoscape.js JSON, GEXF, GraphML, RDF, …)."""
    from . import bioformats
    ext = (ext or "").lower()
    if not forced:
        ext = bioformats.sniff(text, ext) or ext       # PSI-MI, SBML, BioPAX, KGML, GPML by content
    if ext in dict(_LOADERS) and (forced or ext not in _AMBIGUOUS - {".csv", ".tsv", ".rdf", ".owl"}):
        return ext
    head = text.lstrip()[:200].lower()
    return (".gexf" if "<gexf" in head else ".graphml" if "<graphml" in head
            else ".xgmml" if "xgmml" in text[:2000].lower()
            else ".cx" if head.startswith("[") and any(k in text[:3000].lower() for k in (
                '"cxversion"', '"numberverification"', '"metadata"', '"attributedeclarations"'))
            else ".cyjs" if head.startswith(("{", "[")) and ('"elements"' in text[:5000] or '"group"' in text[:3000])
            else ".rdf" if "<rdf:rdf" in head
            else ".ttl" if re.match(r"(#[^\n]*\n\s*)*(@prefix|@base|prefix\s)", head)
            else ".gdf" if head.startswith("nodedef") else ".net" if head.startswith("*vertices")
            else ".gml" if re.match(r"(#[^\n]*\n\s*)*(creator\s|version\s|graph\s*\[)", head)
            else ".dot" if re.match(r"(strict\s+)?(di)?graph\b[^{]*\{", head)
            else ".guess" if '"guess-session"' in text[:400]
            else ".sif" if ext in ("", ".txt", ".tab", ".dat") and _looks_like_sif(text)
            else ext if ext in dict(_LOADERS) else ".csv")


def _looks_like_sif(text):
    """Cytoscape SIF: every line one name, or source, type and targets; no
    commas, and no header naming Source/Target columns."""
    lines = [ln for ln in text.splitlines()[:40] if ln.strip()]
    if not lines or "," in "".join(lines):
        return False
    if any(h in lines[0].lower().split() for h in ("source", "target", "id")):
        return False
    sep = "\t" if any("\t" in ln for ln in lines) else None
    counts = [len(ln.split(sep)) for ln in lines]
    return all(c == 1 or c >= 3 for c in counts) and any(c >= 3 for c in counts)


def install(session):
    g = session.graph

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def loader(name):
        return session.system[name][0]

    @cmd
    def makeFromURL(url, format=None):
        """makeFromURL(url) downloads a graph (GDF, GEXF, GraphML, GML, DOT, Pajek, DL, CSV,
        RDF (Turtle, N-Triples, RDF/XML), Cytoscape's SIF, NNF, Cytoscape.js JSON, CX/CX2 and XGMML, PSI-MI TAB or XML, SBML, BioPAX, KEGG KGML, WikiPathways GPML, a .guess
        session or a .py script) and opens it; format=".gexf" etc. when the URL doesn't end in the extension (the
        biological formats are also recognised by their content)."""
        text = http(url)
        path = urllib.parse.urlparse(url).path
        ext = (format or os.path.splitext(path)[1] or "").lower()
        if not ext.startswith("."):
            ext = "." + ext
        ext = detect_format(text, ext, forced=bool(format))
        name = os.path.basename(path) or "download"
        if not name.lower().endswith(ext):
            name += ext
        with open(name, "w", encoding="utf-8") as fh:
            fh.write(text)
        loader(dict(_LOADERS)[ext])(name)

    @cmd
    def makeFromFile(filename):
        """makeFromFile(filename) opens a graph file in any format GUESS reads,
        choosing the reader from the file's extension or, when the extension
        doesn't say (.xml, .txt, .json, …), from its content: GraphML, XGMML,
        SBML, PSI-MI, KGML or GPML in .xml; PSI-MI TAB, SIF or CSV in .txt;
        Cytoscape.js JSON or CX in .json. Opening a file in the page (File →
        Open, or dropping it) does this."""
        name = str(filename)
        ext = os.path.splitext(name)[1].lower()
        binary = {".xlsx": "makeFromExcel", ".xlsm": "makeFromExcel", ".cys": "makeFromCYS"}
        if ext in binary:
            return loader(binary[ext])(name)
        if not os.path.exists(name):
            raise GuessError(f"no file named {name!r}")
        with open(name, encoding="utf-8", errors="replace") as fh:
            text = fh.read(262144)
        found = detect_format(text, ext)
        if found not in dict(_LOADERS):
            raise GuessError(f"GUESS can't tell what kind of file {name} is")
        if found != ext:
            print(f"{os.path.basename(name)}: reading it as {found[1:].upper()}")
        loader(dict(_LOADERS)[found])(name)

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
        from . import cyformats
        cx = json.loads(http(f"{server}/v3/networks/{uuid}"))
        net, title = cyformats.cx_net(cx, names="id", directed=True)
        if not net.nodes:
            raise GuessError("no nodes in that network (is it public?)")
        g.clear()
        cyformats.build(g, net, scatter=800)
        session.scene()
        print(f"loaded NDEx network {title or uuid!r}: {len(g._nodes)} nodes, {len(g._edges)} edges")

    @cmd
    def makeFromSTRING(genes, species=9606, score=0.7, add=0, server="https://string-db.org"):
        """makeFromSTRING(["TP53", "MDM2", "ATM"]) opens the protein interactions
        among those genes from the STRING database (string-db.org): species is
        an NCBI taxon (9606 human, 10090 mouse, 4932 yeast, 7227 fly, 6239
        worm, 3702 Arabidopsis, 511145 E. coli), score the minimum combined
        confidence (0.4 medium, 0.7 high, 0.9 highest), add=n also brings in
        the n proteins that interact most with the query. Genes may be a list
        or one string separated by spaces/commas. Nodes get `description`,
        `stringId` and `query` (true for the genes you asked for); edges get
        `score` (also `weight`) and the evidence behind it: `experiments`,
        `databases`, `textmining`, `coexpression`, `neighborhood`, `fusion`,
        `cooccurrence` (each 0..1). STRING data are CC BY 4.0: cite it."""
        if isinstance(genes, str):
            genes = [x for x in genes.replace(",", " ").split() if x]
        genes = [str(x) for x in genes]
        if not genes:
            raise GuessError("makeFromSTRING needs some gene names")
        q = urllib.parse.urlencode({"identifiers": "\r".join(genes), "species": int(species),
                                    "limit": 1, "echo_query": 1, "caller_identity": "guess"})
        ids = _tsv(http(f"{server}/api/tsv/get_string_ids?{q}"))
        if not ids:
            raise GuessError(f"STRING knows none of those genes in species {species}")
        asked = {r["stringId"] for r in ids}
        q = urllib.parse.urlencode({"identifiers": "\r".join(asked), "species": int(species),
                                    "required_score": int(round(float(score) * 1000)),
                                    "add_nodes": int(add), "caller_identity": "guess"})
        rows = _tsv(http(f"{server}/api/tsv/network?{q}"))
        g.clear()
        for f, t in (("description", STRING), ("stringId", STRING), ("query", BOOL)):
            g.addNodeField(f, t, None if t != BOOL else False)
        channels = (("experiments", "escore"), ("databases", "dscore"), ("textmining", "tscore"),
                    ("coexpression", "ascore"), ("neighborhood", "nscore"), ("fusion", "fscore"),
                    ("cooccurrence", "pscore"))
        g.addEdgeField("score", DOUBLE, 0.0)
        if "weight" not in g.edge_schema:
            g.addEdgeField("weight", DOUBLE, 1.0)
        for f, _ in channels:
            g.addEdgeField(f, DOUBLE, 0.0)
        nodes = {}

        def node(sid, name, desc=None):
            if sid not in nodes:
                n = g.addNode(_ident(name) if _ident(name) not in g._nodes else _ident(sid))
                n.label = str(name)
                n.stringId = sid
                n.query = sid in asked
                nodes[sid] = n
            if desc:
                nodes[sid].description = desc.split(";")[0][:200]
            return nodes[sid]

        for r in ids:
            node(r["stringId"], r["preferredName"], r.get("annotation"))
        seen = set()
        for r in rows:
            a = node(r["stringId_A"], r["preferredName_A"])
            b = node(r["stringId_B"], r["preferredName_B"])
            key = tuple(sorted((a._id, b._id)))
            if key in seen:
                continue
            seen.add(key)
            e = g.addUndirectedEdge(a, b)
            e.score = e.weight = float(r["score"])
            for f, col in channels:
                e._g.edge_schema[f].set(e, float(r.get(col) or 0))
        _scatter(g)
        session.ns["frLayout"]()
        session.scene()
        print(f"loaded {len(g._nodes)} proteins, {len(g._edges)} interactions from STRING "
              f"(score >= {float(score):g}); data CC BY 4.0, string-db.org")

    @cmd
    def makeFromWikipedia(title, limit=150, lang="en"):
        """makeFromWikipedia("Graph drawing") opens a page's link network: the
        page, up to `limit` articles it links to, and every link among them
        (directed: linking page -> linked page). Node `hop` is 0 for the start
        page and 1 for the others; `indegree` then shows which linked
        articles the neighbourhood itself points to most (identifier pages
        such as "Doi (identifier)", linked by citation templates, are left
        out). lang= picks the
        language edition ("de", "fr", ...). Wikipedia text is CC BY-SA; the
        link structure is what's loaded here."""
        api = f"https://{lang}.wikipedia.org/w/api.php"

        def links(titles):
            out = {}
            params = {"action": "query", "prop": "links", "titles": "|".join(titles), "plnamespace": 0,
                      "pllimit": "max", "format": "json", "origin": "*", "redirects": 1}
            for _ in range(40):
                data = json.loads(http(f"{api}?{urllib.parse.urlencode(params)}"))
                q = data.get("query", {})
                rename = {r["from"]: r["to"] for r in q.get("redirects", [])}
                for page in q.get("pages", {}).values():
                    if "missing" in page:
                        continue
                    out.setdefault(page["title"], set()).update(l["title"] for l in page.get("links", []))
                if "continue" not in data:
                    break
                params.update(data["continue"])
            return out, rename

        first, rename = links([str(title)])
        if not first:
            raise GuessError(f"no Wikipedia page {title!r} ({lang})")
        root = next(iter(first))
        # citation templates link every article to "Doi (identifier)" etc.: not content
        targets = sorted(t for t in first[root] if not t.endswith("(identifier)"))[: int(limit)]
        found = {root: first[root]}
        for k in range(0, len(targets), 50):
            more, _r = links(targets[k:k + 50])
            found.update(more)
        keep = {root} | set(targets)
        g.clear()
        g.addNodeField("hop", INT, 1)
        names = {}
        for t in [root] + targets:
            n = g.addNode(_ident(t) if _ident(t) not in g._nodes else _ident(t) + "_")
            n.label, n.hop = t, 0 if t == root else 1
            names[t] = n
        count = 0
        for src, dsts in found.items():
            if src not in names:
                continue
            for d in dsts:
                if d in keep and d != src:
                    g.addDirectedEdge(names[src], names[d])
                    count += 1
        _scatter(g)
        session.ns["frLayout"]()
        session.scene()
        print(f"{len(names)} Wikipedia articles around {root!r}, {count} links among them")

    @cmd
    def makeFromOpenAlex(search, limit=200, mode="citations"):
        """makeFromOpenAlex("graph drawing") searches OpenAlex (the open
        catalogue of scholarly works, CC0) for works with those words in the
        title, takes the `limit` most cited, and opens their citation network
        (citing -> cited) with `title`, `year`, `cites` (citations from
        anywhere), `venue` and `firstauthor`. mode="authors" opens a two-mode
        paper-author network instead (kind = paper or author), ready for
        project(kind, "author"). Ready for mainPath(), leidenClusters() and
        the Text cookbook's recipes."""
        want = max(1, min(int(limit), 1000))
        sel = "id,title,publication_year,cited_by_count,referenced_works,authorships,primary_location"
        works, page = [], 1
        while len(works) < want and page <= 5:
            q = urllib.parse.urlencode({"filter": f"title.search:{search}", "sort": "cited_by_count:desc",
                                        "per-page": min(200, want), "page": page, "select": sel})
            batch = json.loads(http(f"https://api.openalex.org/works?{q}")).get("results", [])
            if not batch:
                break
            works += batch
            page += 1
        works = works[:want]
        if not works:
            raise GuessError(f"no OpenAlex works with {search!r} in the title")
        short = {w["id"]: "W" + w["id"].rsplit("/W", 1)[-1] for w in works}
        g.clear()
        for f, t in (("title", STRING), ("year", INT), ("cites", INT), ("venue", STRING),
                     ("firstauthor", STRING), ("kind", STRING)):
            g.addNodeField(f, t, None)
        for w in works:
            n = g.addNode(short[w["id"]])
            auth = w.get("authorships") or []
            last = auth[0]["author"]["display_name"].split()[-1] if auth else "?"
            n.title = re.sub(r"<[^>]+>", "", w.get("title") or "")[:200]
            n.year, n.cites = int(w.get("publication_year") or 0), int(w.get("cited_by_count") or 0)
            n.venue = (((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "")[:120]
            n.firstauthor, n.kind = last, "paper"
            n.label = f"{last} {n.year}"
        links = 0
        if mode == "authors":
            people = {}
            for w in works:
                for a in (w.get("authorships") or [])[:25]:
                    who = a["author"]["display_name"]
                    if who not in people:
                        p = g.addNode(_ident(who) if _ident(who) not in g._nodes else _ident(who) + "_a")
                        p.label, p.kind = who, "author"
                        people[who] = p
                    g.addUndirectedEdge(short[w["id"]], people[who])
                    links += 1
        else:
            for w in works:
                for r in w.get("referenced_works") or []:
                    if r in short and r != w["id"]:
                        g.addDirectedEdge(short[w["id"]], short[r])
                        links += 1
        _scatter(g)
        session.ns["frLayout"]()
        session.scene()
        what = "authorships" if mode == "authors" else "citations among them"
        print(f"{len(works)} works matching {search!r} (most cited first), {links} {what}; OpenAlex, CC0")

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


def _tsv(text):
    import csv
    import io
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


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
