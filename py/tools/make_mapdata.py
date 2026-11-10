"""Regenerate guess/mapdata.py, the outlines geoLayout draws, from Natural Earth
(naturalearthdata.com; public domain) 1:110m data:

    cd py && .venv/bin/python tools/make_mapdata.py

world: land polygons; usa: the 50 states and DC. Coordinates are rounded to
0.1 degree (about 10 km), plenty at this scale, to keep the module small.
"""
import json
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
OUT = Path(__file__).resolve().parents[1] / "guess" / "mapdata.py"


def fetch(name):
    with urllib.request.urlopen(BASE + name, timeout=120) as r:
        return json.loads(r.read())


def rings(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly[:1]:            # outer rings only (lakes and holes are too small at 1:110m)
            pts, last = [], None
            for lon, lat in ring:
                p = (round(lon, 1), round(lat, 1))
                if p != last:
                    pts.append(p)
                    last = p
            if len(pts) >= 4:
                yield pts


def encode(ring_list):
    return ";".join(" ".join(f"{lon:g},{lat:g}" for lon, lat in r) for r in ring_list)


def main():
    land = [r for f in fetch("ne_110m_land.geojson")["features"] for r in rings(f["geometry"])]
    states = [r for f in fetch("ne_110m_admin_1_states_provinces_lakes.geojson")["features"]
              if f["properties"].get("adm0_a3") == "USA" for r in rings(f["geometry"])]
    OUT.write_text('"""Map outlines for geoLayout, from Natural Earth 1:110m (public domain):\n'
                   'rings of "lon,lat" points separated by spaces, rings by ";".\n'
                   'Regenerate with tools/make_mapdata.py."""\n\n'
                   f"WORLD = {encode(land)!r}\n\nUSA = {encode(states)!r}\n")
    print(f"  {OUT.name}: {len(land)} land rings, {len(states)} state rings, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
