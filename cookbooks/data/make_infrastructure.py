"""Fetch the Infrastructure cookbook's airline data (needs the network).

    cd py && .venv/bin/python ../cookbooks/data/make_infrastructure.py

From OpenFlights (openflights.org; airports and routes databases, Open Database
License: share-alike, attribution). The routes are a 2014 snapshot.

us-airports.gdf     airports in the United States with domestic routes; edges are
                    airport pairs served by any airline (direction merged), weight =
                    the number of airline-route listings between them
world-airports.gdf  every airport with a route, worldwide, likewise
"""
import csv
import io
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "py"))
BASE = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/"


def get(name):
    req = urllib.request.Request(BASE + name, headers={"User-Agent": "guess-cookbook-data/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", errors="replace")


def build(airports, routes, keep, out, title):
    from guess import Session
    s = Session(lambda m: print(m.get("text", "")) if m.get("type") == "error" else None)
    g = s.graph
    pairs = {}
    for r in routes:
        a, b = r["src"], r["dst"]
        if a in airports and b in airports and a != b and keep(airports[a], airports[b]):
            k = tuple(sorted((a, b)))
            pairs[k] = pairs.get(k, 0) + 1
    used = {x for k in pairs for x in k}
    s.run("addNodeField('iata', VARCHAR, None); addNodeField('city', VARCHAR, None); "
          "addNodeField('country', VARCHAR, None); addNodeField('latitude', DOUBLE, 0); "
          "addNodeField('longitude', DOUBLE, 0); addNodeField('airport', VARCHAR, None)")
    for code in sorted(used):
        ap = airports[code]
        n = g.addNode(code if re.match(r"^[A-Z][A-Z0-9]{2}$", code) and code not in ("AND", "NOT", "DEL") else "_" + code)
        n.iata, n.label = code, code
        n.city, n.country, n.airport = ap["city"], ap["country"], ap["name"][:80]
        n.latitude, n.longitude = ap["lat"], ap["lon"]
    if "weight" not in g.edge_schema:
        g.addEdgeField("weight", "DOUBLE", 1.0)
    names = {n.iata: n.name for n in g.nodes}
    for (a, b), w in pairs.items():
        g.addUndirectedEdge(names[a], names[b], weight=float(w))
    s.run("geoLayout()")
    s.run("removeMap()")
    assert s.run(f"exportGDF({str(HERE / out)!r})")
    print(f"  {out}: {len(g.nodes)} {title} airports, {len(g.edges)} routes")


def main():
    airports = {}
    for row in csv.reader(io.StringIO(get("airports.dat"))):
        if len(row) < 8 or row[4] in ("", "\\N"):
            continue
        try:
            airports[row[4]] = {"name": row[1], "city": row[2], "country": row[3],
                                "lat": float(row[6]), "lon": float(row[7])}
        except ValueError:
            continue
    routes = []
    for row in csv.reader(io.StringIO(get("routes.dat"))):
        if len(row) >= 5:
            routes.append({"src": row[2], "dst": row[4]})
    us = "United States"
    build(airports, routes, lambda a, b: a["country"] == us and b["country"] == us, "us-airports.gdf", "US")
    build(airports, routes, lambda a, b: True, "world-airports.gdf", "world")


if __name__ == "__main__":
    main()
