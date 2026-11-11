"""SIMULATED data for the Epidemiology cookbook (seeded, so it's the same
every time). The school, its pupils and the outbreak are invented. Their
shape follows what studies of real schools and outbreaks report (contacts
mostly within a class, outbreaks driven by a few superspreaders), but never
mistake this for real data.

    cd py && .venv/bin/python ../cookbooks/data/make_epidemiology.py

school-contacts-SIMULATED.gdf
    a primary school: 5 grades of 2 classes (1A ... 5B) and their teachers.
    Edge `weight` = minutes of close contact on a school day, as a wearable-
    sensor study would record. Node fields: role, room (the class: 1A ... 5B), grade.
outbreak-cases-SIMULATED.csv, outbreak-transmissions-SIMULATED.csv
    a line list of a respiratory outbreak in a town, where gatherings were
    banned and distancing advised from day 28: one row per case (Id,
    onset day, age, ward) and one per known transmission (Source = infector,
    Target = case, setting). Some cases have no known infector, as in real
    contact tracing.
"""
import csv
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "py"))


def school(rng):
    from guess import Session
    s = Session(lambda m: print(m.get("text", "")) if m.get("type") == "error" else None)
    g = s.graph
    s.run("addNodeField('role', VARCHAR, None); addNodeField('room', VARCHAR, None); "
          "addNodeField('grade', INTEGER, None)")
    if "weight" not in g.edge_schema:
        g.addEdgeField("weight", "DOUBLE", 1.0)
    pupils, teachers = [], []
    social = {}
    k = 0
    for grade in range(1, 6):
        for room in "AB":
            cls = f"{grade}{room}"
            t = g.addNode(f"T{cls}")
            t.role, t.grade = "teacher", grade
            t.room = cls
            teachers.append(t)
            for _ in range(rng.randint(22, 26)):
                k += 1
                p = g.addNode(f"p{k:03d}")
                p.role, p.grade = "pupil", grade
                p.room = cls
                pupils.append(p)
                social[p] = rng.lognormvariate(0, 0.55)     # some children mix far more than others

    def link(a, b, minutes):
        e = g.addEdge(a, b)
        e.weight = round(max(1.0, minutes), 1)

    def cls(n):
        return n.room

    for i, a in enumerate(pupils):
        for b in pupils[i + 1:]:
            mix = social[a] * social[b]
            if cls(a) == cls(b):
                p, m = 0.42, 22
            elif a.grade == b.grade:
                p, m = 0.06, 9
            elif abs(a.grade - b.grade) == 1:
                p, m = 0.010, 5
            else:
                p, m = 0.003, 4
            if rng.random() < min(1.0, p * mix):
                link(a, b, rng.lognormvariate(math.log(m), 0.8))
    for t in teachers:
        for p in pupils:
            if cls(p) == cls(t) and rng.random() < 0.55:
                link(t, p, rng.lognormvariate(math.log(8), 0.7))
    for i, a in enumerate(teachers):
        for b in teachers[i + 1:]:
            if rng.random() < (0.9 if a.grade == b.grade else 0.25):
                link(a, b, rng.lognormvariate(math.log(10), 0.6))
    s.run("forceAtlas2Layout()" if "forceAtlas2Layout" in s.ns else "frLayout()")
    s.run('g.edges.color = "205,205,205"; g.edges.width = 1.0')
    out = HERE / "school-contacts-SIMULATED.gdf"
    assert s.run(f"exportGDF({str(out)!r})")
    print(f"  {out.name}: {len(g.nodes)} people, {len(g.edges)} contacts")


def outbreak(rng, R=1.6, k=0.25, end=70, cap=600, ban=28, R_after=0.6):
    """A branching process with overdispersed (negative binomial) offspring:
    most cases infect no one, a few infect many."""
    def offspring(day):
        r = R if day < ban else R_after           # day `ban`: gatherings banned, distancing
        lam = rng.gammavariate(k, r / k)          # gamma-Poisson mixture = negative binomial
        n, p, x = 0, math.exp(-lam), rng.random()
        c = p
        while x > c:
            n += 1
            p *= lam / n
            c += p
        return n

    wards = list("ABCDEF")
    cases = []                                    # (id, onset, age, ward, infector, setting)
    queue = []
    for i in range(3):
        cases.append([f"c{len(cases) + 1:03d}", rng.randint(0, 4), rng.randint(20, 60), rng.choice(wards), None, None])
        queue.append(cases[-1])
    events = 0
    while queue and len(cases) < cap:
        queue.sort(key=lambda c: c[1])
        parent = queue.pop(0)
        n = offspring(parent[1])
        if n >= 10 and parent[1] < ban:                               # a superspreading event: a gathering
            events += 1
            where = "gathering"
        else:
            where = None
        for _ in range(n):
            onset = parent[1] + max(1, round(rng.gammavariate(4, 1.25)))
            if onset > end or len(cases) >= cap:
                continue
            setting = where if where and rng.random() < 0.75 else rng.choices(["household", "school", "work", "social"], [5, 2, 2, 2])[0]
            if setting == "household":
                ward, age = parent[3], rng.choice([rng.randint(1, 17), rng.randint(25, 80)])
            else:
                ward = parent[3] if rng.random() < 0.6 else rng.choice(wards)
                age = rng.randint(5, 11) if setting == "school" else rng.randint(18, 75)
            cases.append([f"c{len(cases) + 1:03d}", onset, age, ward, parent[0], setting])
            queue.append(cases[-1])
    if not 200 <= len(cases) < cap:                          # died out early: most chains do
        return False
    cases.sort(key=lambda c: (c[1], c[0]))
    known = 0
    with open(HERE / "outbreak-cases-SIMULATED.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Id", "onset", "age", "ward"])
        for c in cases:
            w.writerow(c[:4])
    with open(HERE / "outbreak-transmissions-SIMULATED.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Source", "Target", "Type", "setting"])
        for c in cases:
            if c[4] and rng.random() < 0.88:     # contact tracing finds most infectors, not all
                w.writerow([c[4], c[0], "Directed", c[5]])
                known += 1
    print(f"  outbreak: {len(cases)} cases, {known} known transmissions, {events} gatherings")
    return True


if __name__ == "__main__":
    school(random.Random(21))
    seed = 22
    while not outbreak(random.Random(seed)):      # the first seed whose outbreak takes off
        seed += 1
    print(f"  (outbreak seed {seed})")
