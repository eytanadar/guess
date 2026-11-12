"""Regenerate guess/regiondata.py, the region adjacency networks behind
makeFromMap: which US states and which countries share a border, with a
centre point for each. From Natural Earth (naturalearthdata.com; public
domain) 1:50m data, where neighbouring regions share boundary vertices.

    cd py && .venv/bin/python tools/make_regiondata.py
"""
import json
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
OUT = Path(__file__).resolve().parents[1] / "guess" / "regiondata.py"


def fetch(name):
    with urllib.request.urlopen(BASE + name, timeout=180) as r:
        return json.loads(r.read())


def points(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly:
            for lon, lat in ring:
                yield round(lon, 3), round(lat, 3)


def centre(geom):
    """The centre of the largest polygon's outer ring (by vertex average; fine for labels)."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    ring = max((p[0] for p in polys), key=len)
    return round(sum(p[0] for p in ring) / len(ring), 3), round(sum(p[1] for p in ring) / len(ring), 3)


def adjacency(features, name_of):
    owners = {}
    for f in features:
        for p in set(points(f["geometry"])):
            owners.setdefault(p, set()).add(name_of(f))
    shared = {}
    for names in owners.values():
        names = sorted(names)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                shared[(names[i], names[j])] = shared.get((names[i], names[j]), 0) + 1
    # a border, not just a corner: at least two shared boundary points (so the
    # Four Corners states, which meet at one point, aren't joined diagonally)
    return sorted(p for p, k in shared.items() if k >= 2)


def main():
    states = [f for f in fetch("ne_50m_admin_1_states_provinces.geojson")["features"]
              if f["properties"].get("iso_a2") == "US"
              and f["properties"]["name"] not in ("Alaska", "Hawaii", "District of Columbia")]
    st_name = lambda f: f["properties"]["name"]
    usa = {"nodes": {st_name(f): {"abbrev": f["properties"]["postal"], "pos": centre(f["geometry"])} for f in states},
           "edges": adjacency(states, st_name)}
    countries = [f for f in fetch("ne_50m_admin_0_countries.geojson")["features"]
                 if f["properties"]["CONTINENT"] != "Antarctica"]
    co_name = lambda f: f["properties"]["NAME"]
    world = {"nodes": {co_name(f): {"abbrev": f["properties"]["ISO_A3"], "continent": f["properties"]["CONTINENT"],
                                    "pos": centre(f["geometry"])} for f in countries},
             "edges": adjacency(countries, co_name)}
    OUT.write_text('"""Region adjacency networks for makeFromMap, from Natural Earth 1:50m\n'
                   '(public domain): regions, a centre (lon, lat) each, and pairs sharing a\n'
                   'border. Regenerate with tools/make_regiondata.py."""\n\n'
                   f"USA = {json.dumps(usa, ensure_ascii=False)}\n\nWORLD = {json.dumps(world, ensure_ascii=False)}\n")
    print(f"usa: {len(usa['nodes'])} states, {len(usa['edges'])} borders; "
          f"world: {len(world['nodes'])} countries, {len(world['edges'])} borders -> {OUT}")


if __name__ == "__main__":
    main()
