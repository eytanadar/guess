"""Geographic layout: place nodes by latitude and longitude, with a map drawn
underneath (Natural Earth outlines, public domain).

    geoLayout()                         latitude/longitude fields, Mercator, a fitting map
    geoLayout(lat, lon, projection="albers", map="usa")
    removeMap()
"""
import math

from .model import Field, GuessError

LAT_NAMES = ("latitude", "lat")
LON_NAMES = ("longitude", "lon", "lng", "long")


def _rings(encoded):
    out = []
    for ring in encoded.split(";"):
        pts = []
        for p in ring.split(" "):
            lon, lat = p.split(",")
            pts.append((float(lon), float(lat)))
        out.append(pts)
    return out


_CACHE = {}


def outlines(name):
    if name not in _CACHE:
        from . import mapdata
        _CACHE[name] = _rings(mapdata.WORLD if name == "world" else mapdata.USA)
    return _CACHE[name]


def projector(projection, parallels=(29.5, 45.5), center=(-96.0, 37.5)):
    """(lon, lat) in degrees -> (x, y) with y north-up, unitless."""
    p = str(projection).lower()
    if p in ("equirectangular", "plate carree", "platecarree", "latlon"):
        return lambda lon, lat: (lon, lat)
    if p == "mercator":
        def merc(lon, lat):
            lat = max(-85.0, min(85.0, lat))
            return math.radians(lon), math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
        return merc
    if p in ("albers", "conic", "equal-area"):
        p1, p2 = (math.radians(v) for v in parallels)
        lon0, lat0 = math.radians(center[0]), math.radians(center[1])
        n = (math.sin(p1) + math.sin(p2)) / 2
        c = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
        rho0 = math.sqrt(max(c - 2 * n * math.sin(lat0), 0)) / n

        def albers(lon, lat):
            lam = math.radians(lon) - lon0
            lam = (lam + math.pi) % (2 * math.pi) - math.pi
            rho = math.sqrt(max(c - 2 * n * math.sin(math.radians(lat)), 0)) / n
            th = n * lam
            return rho * math.sin(th), rho0 - rho * math.cos(th)
        return albers
    raise GuessError('projection should be "mercator", "equirectangular" or "albers"')


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def field(f, names, what):
        g = session.graph
        if isinstance(f, Field):
            return f
        if isinstance(f, str) and f in g.node_schema:
            return g.node_schema[f]
        if f is None:
            for nm in names:
                if nm in g.node_schema:
                    return g.node_schema[nm]
        raise GuessError(f"geoLayout needs a {what} field (looked for {', '.join(names)}); "
                         f"name it, e.g. geoLayout(lat, lon)")

    def num(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v if math.isfinite(v) else None

    @cmd
    def geoLayout(lat=None, lon=None, projection="mercator", map="auto", width=1000,  # noqa: A002
                  land=None, borders=None, parallels=(29.5, 45.5), center=(-96.0, 37.5)):
        """geoLayout() places nodes by their latitude and longitude fields
        (found by name: latitude/lat and longitude/lon/lng, or pass them:
        geoLayout(lat, lon)) and draws a map underneath. projection:
        "mercator" (default; shapes kept, high latitudes enlarged),
        "equirectangular" (longitude and latitude as x and y) or "albers"
        (equal-area conic; with parallels= and center=, US by default, which
        suits the lower 48 states). map: "world" (land outlines), "usa" (the
        states), None for no map, or "auto" (usa when every node is in the
        US, else world). land= and borders= set the map's colours (default:
        light or dark grey to suit the theme). The layout fits nodes into
        `width` units across; nodes without coordinates are set in a row
        below. Outlines: Natural Earth 1:110m, public domain."""
        g = session.graph
        flat, flon = field(lat, LAT_NAMES, "latitude"), field(lon, LON_NAMES, "longitude")
        proj = projector(projection, parallels, center)
        placed, missing = [], []
        for n in g._nodes_list():
            la, lo = num(flat.get(n)), num(flon.get(n))
            if la is None or lo is None or not (-90 <= la <= 90 and -180 <= lo <= 360):
                missing.append(n)
            else:
                placed.append((n, lo - 360 if lo > 180 else lo, la))
        if not placed:
            raise GuessError(f"no node has a usable {flat.name} and {flon.name}")
        pts = [proj(lo, la) for _n, lo, la in placed]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        span = max(x1 - x0, y1 - y0) or 1.0
        s = float(width) / span

        def to_graph(x, y):
            return (x - x0) * s, (y1 - y) * s     # north up

        for (n, _lo, _la), (x, y) in zip(placed, pts):
            gx, gy = to_graph(x, y)
            n.x, n.y = gx - n.width / 2, gy - n.height / 2
        if missing:
            base = (y1 - y0) * s + 80
            for i, n in enumerate(missing):
                n.x, n.y = (i % 40) * 25.0, base + (i // 40) * 25.0
        which = map
        if which == "auto":
            in_us = all(18 <= la <= 72 and (-180 <= lo <= -60) for _n, lo, la in placed)
            which = "usa" if in_us else "world"
        view = session.view
        if which in (None, False, "none"):
            view.map = None
        elif which in ("world", "usa"):
            # outlines near the nodes only (keeps the drawing light and avoids
            # the far-flung shapes a conic projection makes of the other side of the world)
            pad = 0.25 * span
            rings = []
            for ring in outlines(which):
                proj_ring = [proj(lo, la) for lo, la in ring]
                rx = [p[0] for p in proj_ring]
                ry = [p[1] for p in proj_ring]
                if max(rx) < x0 - pad or min(rx) > x1 + pad or max(ry) < y0 - pad or min(ry) > y1 + pad:
                    continue
                flat_pts = []
                for x, y in proj_ring:
                    gx, gy = to_graph(x, y)
                    flat_pts += [round(gx, 1), round(gy, 1)]
                rings.append(flat_pts)
            from . import colors
            view.map = {"rings": rings,
                        "fill": None if land is None else colors.to_rgba_int(land)[0],
                        "stroke": None if borders is None else colors.to_rgba_int(borders)[0]}
        else:
            raise GuessError('map should be "world", "usa", "auto" or None')
        view.changed()
        session.scene()
        msg = f"placed {len(placed)} nodes ({projection}" + (f", {which} map)" if view.map else ")")
        if missing:
            msg += f"; {len(missing)} without coordinates are in a row below"
        print(msg)

    @cmd
    def geoDistance(name="km", lat=None, lon=None):
        """geoDistance() stores each edge's great-circle length in kilometres
        (from its ends' latitude and longitude fields, as geoLayout finds them)
        in the edge field `km` (or name=...). Use it as a cost:
        for e in g.edges: e.weight = e.km, then shortestPath(a, b,
        weighted=true) is the shortest route by distance. Returns the field."""
        g = session.graph
        flat, flon = field(lat, LAT_NAMES, "latitude"), field(lon, LON_NAMES, "longitude")
        f = g.addEdgeField(str(name), "DOUBLE", None)
        missing = 0
        for e in g._edges_list():
            a1, o1, a2, o2 = (num(flat.get(e._n1)), num(flon.get(e._n1)), num(flat.get(e._n2)), num(flon.get(e._n2)))
            if None in (a1, o1, a2, o2):
                missing += 1
                continue
            p1, p2 = math.radians(a1), math.radians(a2)
            c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(math.radians(o2 - o1))
            f.set(e, 6371.0088 * math.acos(max(-1.0, min(1.0, c))))
        if missing:
            print(f"{missing} edges have an end without coordinates (left empty)")
        return f

    @cmd
    def removeMap():
        """removeMap() removes the map drawn by geoLayout (the positions stay)."""
        session.view.map = None
        session.view.changed()
