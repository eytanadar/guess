"""Fetch the Text cookbook's data (needs the network; re-run to refresh).

    cd py && .venv/bin/python ../cookbooks/data/make_text.py

scandal-in-bohemia.txt   A. Conan Doyle, "A Scandal in Bohemia" (1891), public
                         domain; text from Project Gutenberg eBook #1661.
vis-papers.gdf           OpenAlex (openalex.org, CC0): highly cited works on graph
                         and network visualisation, with the citations among them
                         (citing -> cited).
vis-paper-authors.csv    paper, author (two-mode)
vis-paper-keywords.csv   paper, keyword, score (two-mode, OpenAlex keyword scores)
"""
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "py"))
UA = {"User-Agent": "guess-cookbook-data/1.0"}


def get(url, tries=6):
    import time
    import urllib.error
    for k in range(tries):
        time.sleep(1.0)                    # be gentle with public APIs
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code != 429 or k == tries - 1:
                raise
            time.sleep(5 * 2 ** k)          # rate-limited: back off


def holmes():
    text = get("https://www.gutenberg.org/cache/epub/1661/pg1661.txt").replace("\r\n", "\n")
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "I. A SCANDAL IN BOHEMIA")
    end = next(i for i, l in enumerate(lines) if l.strip() == "II. THE RED-HEADED LEAGUE")
    story = "\n".join(lines[start:end]).strip() + "\n"
    head = ("A Scandal in Bohemia, by Arthur Conan Doyle (1891). Public domain.\n"
            "Text from Project Gutenberg eBook #1661, The Adventures of Sherlock Holmes\n"
            "(www.gutenberg.org). Paragraphs are separated by blank lines.\n\n")
    (HERE / "scandal-in-bohemia.txt").write_text(head + story)
    print(f"  scandal-in-bohemia.txt: {len(story.split())} words")


def short(oa_id):
    return "W" + oa_id.rsplit("/W", 1)[-1]


def papers():
    sel = "id,title,publication_year,cited_by_count,referenced_works,keywords,authorships,primary_location,type"
    works, seen = [], set()
    # the phrases must be in the title: a plain search also matches deep-learning
    # papers that "visualize" neural networks
    for query in ("graph drawing", "graph layout", "network visualization", "graph visualization",
                  "force-directed", "visualizing networks", "visual analytics of graphs"):
        for page in (1, 2):
            q = urllib.parse.urlencode({"sort": "cited_by_count:desc", "per-page": 100,
                                        "page": page, "select": sel,
                                        "filter": f"title.search:{query},publication_year:1980-2024"})
            for w in json.loads(get(f"https://api.openalex.org/works?{q}"))["results"]:
                if w["id"] not in seen and w.get("title"):
                    seen.add(w["id"])
                    works.append(w)
    ids = {w["id"] for w in works}
    from guess import Session
    s = Session(lambda m: print(m.get("text", "")) if m.get("type") == "error" else None)
    g = s.graph
    s.run("addNodeField('title', VARCHAR, None); addNodeField('year', INTEGER, 0); "
          "addNodeField('cites', INTEGER, 0); addNodeField('venue', VARCHAR, None); "
          "addNodeField('firstauthor', VARCHAR, None)")
    for w in works:
        n = g.addNode(short(w["id"]))
        n.title = re.sub(r"<[^>]+>", "", w["title"])[:200]
        n.year = int(w["publication_year"] or 0)
        n.cites = int(w["cited_by_count"] or 0)
        src = ((w.get("primary_location") or {}).get("source") or {})
        n.venue = (src.get("display_name") or "")[:120]
        auth = w.get("authorships") or []
        last = (auth[0]["author"]["display_name"].split()[-1] if auth else "?")
        n.firstauthor = last
        n.label = f"{last} {n.year}"
    edges = 0
    for w in works:
        for r in w.get("referenced_works") or []:
            if r in ids and r != w["id"]:
                g.addDirectedEdge(short(w["id"]), short(r))
                edges += 1
    s.run("frLayout()")
    assert s.run(f"exportGDF({str(HERE / 'vis-papers.gdf')!r})")
    print(f"  vis-papers.gdf: {len(works)} papers, {edges} citations among them")
    with open(HERE / "vis-papers-nodes.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["Id", "title", "year", "cites", "firstauthor", "venue"])
        for n in g.nodes:
            wr.writerow([n.name, n.title, n.year, n.cites, n.firstauthor, n.venue])
    with open(HERE / "vis-paper-authors.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["paper", "author"])
        for w in works:
            for a in (w.get("authorships") or [])[:25]:
                wr.writerow([short(w["id"]), a["author"]["display_name"]])
    with open(HERE / "vis-paper-keywords.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["paper", "keyword", "score"])
        for w in works:
            for k in w.get("keywords") or []:
                wr.writerow([short(w["id"]), k["display_name"], round(float(k.get("score") or 0), 3)])
    print("  vis-paper-authors.csv, vis-paper-keywords.csv")


def institutions():
    """vis-institutions.gdf: the institutions of the papers' authors (OpenAlex
    geo), linked when they co-author a paper; `firstyear` is their first paper
    in the set, `papers` how many."""
    import csv as _csv
    from guess import Session
    ids = [r["Id"] for r in _csv.DictReader(open(HERE / "vis-papers-nodes.csv"))]
    years = {r["Id"]: int(r["year"] or 0) for r in _csv.DictReader(open(HERE / "vis-papers-nodes.csv"))}
    paper_inst = {}
    for k in range(0, len(ids), 50):
        q = urllib.parse.urlencode({"filter": "openalex:" + "|".join(ids[k:k + 50]),
                                    "select": "id,authorships", "per-page": 50})
        for w in json.loads(get(f"https://api.openalex.org/works?{q}"))["results"]:
            insts = {i["id"].rsplit("/", 1)[-1] for a in (w.get("authorships") or [])
                     for i in (a.get("institutions") or []) if i.get("id")}
            paper_inst[short(w["id"])] = insts
    all_inst = sorted({i for v in paper_inst.values() for i in v})
    geo = {}
    for k in range(0, len(all_inst), 50):
        q = urllib.parse.urlencode({"filter": "openalex:" + "|".join(all_inst[k:k + 50]),
                                    "select": "id,display_name,geo,country_code,type", "per-page": 50})
        for r in json.loads(get(f"https://api.openalex.org/institutions?{q}"))["results"]:
            gg = r.get("geo") or {}
            if gg.get("latitude") is not None:
                geo[r["id"].rsplit("/", 1)[-1]] = (r["display_name"], gg["latitude"], gg["longitude"],
                                                   gg.get("country") or r.get("country_code") or "", r.get("type") or "")
    s = Session(lambda m: print(m.get("text", "")) if m.get("type") == "error" else None)
    g = s.graph
    s.run("addNodeField('institution', VARCHAR, None); addNodeField('country', VARCHAR, None); "
          "addNodeField('itype', VARCHAR, None); addNodeField('latitude', DOUBLE, None); "
          "addNodeField('longitude', DOUBLE, None); addNodeField('firstyear', INTEGER, 0); "
          "addNodeField('papers', INTEGER, 0)")
    if "weight" not in g.edge_schema:
        g.addEdgeField("weight", "DOUBLE", 1.0)
    g.addEdgeField("firstyear", "INTEGER", 0)
    stats = {}
    for p, insts in paper_inst.items():
        for i in insts:
            if i in geo:
                st = stats.setdefault(i, [0, 9999])
                st[0] += 1
                st[1] = min(st[1], years.get(p, 9999))
    for i, (papers, first) in stats.items():
        name, lat, lon, country, itype = geo[i]
        n = g.addNode(i)
        n.label, n.institution, n.country, n.itype = name[:60], name, country, itype
        n.latitude, n.longitude, n.firstyear, n.papers = lat, lon, first, papers
    pairs = {}
    for p, insts in paper_inst.items():
        insts = sorted(i for i in insts if i in stats)
        for a in range(len(insts)):
            for b in range(a + 1, len(insts)):
                k = (insts[a], insts[b])
                w = pairs.setdefault(k, [0, 9999])
                w[0] += 1
                w[1] = min(w[1], years.get(p, 9999))
    for (a, b), (w, y) in pairs.items():
        g.addUndirectedEdge(a, b, weight=float(w), firstyear=y)
    s.run("geoLayout(map=None)")
    assert s.run(f"exportGDF({str(HERE / 'vis-institutions.gdf')!r})")
    print(f"  vis-institutions.gdf: {len(g.nodes)} institutions, {len(g.edges)} co-authorship links")


if __name__ == "__main__":
    if "holmes" in sys.argv[1:] or not sys.argv[1:]:
        holmes()
    if "papers" in sys.argv[1:] or not sys.argv[1:]:
        papers()
    if "institutions" in sys.argv[1:] or not sys.argv[1:]:
        institutions()
