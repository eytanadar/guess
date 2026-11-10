"""SIMULATED data for the Investigations cookbook (seeded, so it's the same
every time). The people, companies and accounts are invented; the patterns
planted in them (rings, duplicates, round trips, a mule) are what the recipes
find. Never mistake this for real data.

    cd py && .venv/bin/python ../cookbooks/data/make_investigations.py
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "py"))

FIRST = ("Alex Sam Jordan Casey Riley Morgan Taylor Jamie Robin Drew Avery Quinn Parker Reese Rowan "
         "Emery Sky Blake Hayden Kendall Logan Micah Noel Peyton Sage Shawn Toby Val Wren Ari").split()
LAST = ("Archer Bramble Calder Dorsey Ellery Fenwick Garrow Hollis Ingram Jessop Kestrel Lowry Marlow "
        "Norcott Oakes Pell Quarry Renwick Stroud Tamsin Upton Vance Wexley Yarrow Zell Ashby Birch "
        "Corran Dunmore Elstree").split()


def person_name(rng):
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def variant(name, rng):
    first, last = name.split()
    return rng.choice([f"{last} {first}", f"{first[0]}. {last}", f"{first} {last}".upper(),
                       f"{first} {last[:-1]}" if len(last) > 4 else f"{first}  {last}", f"{first}-{last}"])


def claims(rng):
    from guess import Session
    s = Session(lambda m: print(m.get("text", "")) if m.get("type") == "error" else None)
    g = s.graph
    s.run("addNodeField('kind', VARCHAR, None); addNodeField('amount', DOUBLE, None); "
          "addNodeField('day', INTEGER, None); addNodeField('ring', VARCHAR, None)")
    if "weight" not in g.edge_schema:
        g.addEdgeField("weight", "DOUBLE", 1.0)
    count = {"k": 0}

    def node(kind, label, **kv):
        count["k"] += 1
        n = g.addNode(f"{kind[0]}{count['k']}")
        n.kind, n.label = kind, label
        for k, v in kv.items():
            setattr(n, k, v)
        return n

    doctors = [node("doctor", f"Dr {rng.choice(LAST)} clinic {i + 1}") for i in range(30)]
    lawyers = [node("lawyer", f"{rng.choice(LAST)} & {rng.choice(LAST)} {i + 1}") for i in range(20)]
    people = []
    for i in range(600):
        p = node("person", person_name(rng))
        if rng.random() < 0.15 and people:                     # family: shares an address
            fam = rng.choice(people)
            addr = next(e._n2 if e._n1 is fam else e._n1 for e in fam._inc.values()
                        if (e._n2 if e._n1 is fam else e._n1).kind == "address")
        else:
            addr = node("address", f"{rng.randint(1, 999)} {rng.choice(LAST)} Road")
        g.addUndirectedEdge(p, addr)
        g.addUndirectedEdge(p, node("phone", f"555-{rng.randint(1000, 9999)}-{i}"))
        people.append(p)

    def claim(p, day, amount, doc, law, ring=None):
        c = node("claim", f"claim {count['k'] + 1}", amount=round(amount, 2), day=day, ring=ring)
        g.addUndirectedEdge(p, c)
        g.addUndirectedEdge(c, doc)
        if law is not None:
            g.addUndirectedEdge(c, law)
        return c

    for p in people:
        if rng.random() < 0.4:
            claim(p, rng.randint(1, 365), rng.lognormvariate(7.5, 0.8), rng.choice(doctors),
                  rng.choice(lawyers) if rng.random() < 0.3 else None)
    # three planted rings: members share phones and addresses, file several
    # claims each, all with one doctor and one lawyer, within a few weeks
    for r, size in enumerate((8, 6, 10), start=1):
        tag = f"ring {r}"
        members = [node("person", person_name(rng), ring=tag) for _ in range(size)]
        phones = [node("phone", f"555-{rng.randint(1000, 9999)}-r{r}{k}", ring=tag) for k in range(2)]
        addrs = [node("address", f"{rng.randint(1, 99)} {rng.choice(LAST)} Court", ring=tag) for _ in range(2)]
        doc, law = rng.choice(doctors), rng.choice(lawyers)
        start = rng.randint(30, 300)
        for m in members:
            g.addUndirectedEdge(m, rng.choice(phones))
            g.addUndirectedEdge(m, rng.choice(addrs))
            for _ in range(rng.randint(2, 4)):
                claim(m, start + rng.randint(0, 25), rng.uniform(4000, 9000), doc, law, ring=tag)
    # 25 planted duplicates: the same person entered twice, with a name variant,
    # sharing the original's phone
    for p in rng.sample(people, 25):
        d = node("person", variant(p.label, rng), ring="duplicate")
        phone = next((e._n2 if e._n1 is p else e._n1) for e in p._inc.values()
                     if (e._n2 if e._n1 is p else e._n1).kind == "phone")
        g.addUndirectedEdge(d, phone)
        claim(d, rng.randint(1, 365), rng.lognormvariate(7.5, 0.8), rng.choice(doctors), None)
    s.run("frLayout()")
    out = HERE / "claims-SIMULATED.gdf"
    assert s.run(f"exportGDF({str(out)!r})")
    print(f"  {out.name}: {len(g.nodes)} nodes, {len(g.edges)} edges")


def transfers(rng):
    from guess import Session
    s = Session(lambda m: print(m.get("text", "")) if m.get("type") == "error" else None)
    g = s.graph
    s.run("addNodeField('holder', VARCHAR, None); addEdgeField('amount', DOUBLE, 0); "
          "addEdgeField('day', INTEGER, 0); addEdgeField('pattern', VARCHAR, None)")
    accts = []
    for i in range(400):
        n = g.addNode(f"A{1000 + i}")
        n.holder = person_name(rng) if rng.random() < 0.8 else f"{rng.choice(LAST)} Trading {i}"
        n.label = n.name
        accts.append(n)
    for _ in range(1100):
        a, b = rng.sample(accts, 2)
        e = g.addDirectedEdge(a, b)
        e.amount, e.day = round(rng.lognormvariate(6, 1.2), 2), rng.randint(1, 180)
    # round trips: money goes round a loop of accounts back to its origin
    for k, size in enumerate((4, 5, 3, 6)):
        loop = rng.sample(accts, size)
        amt, day = rng.uniform(40000, 90000), rng.randint(10, 150)
        for i, a in enumerate(loop):
            e = g.addDirectedEdge(a, loop[(i + 1) % size])
            amt *= rng.uniform(0.96, 0.99)           # a fee skimmed at each hop
            e.amount, e.day, e.pattern = round(amt, 2), day + i, f"round trip {k + 1}"
    # a mule: many small deposits in, a few large transfers out
    mule = rng.choice(accts)
    senders = rng.sample([a for a in accts if a is not mule], 25)
    for a in senders:
        e = g.addDirectedEdge(a, mule)
        e.amount, e.day, e.pattern = round(rng.uniform(800, 990), 2), rng.randint(60, 70), "mule in"
    for a in rng.sample([x for x in accts if x is not mule and x not in senders], 3):
        e = g.addDirectedEdge(mule, a)
        e.amount, e.day, e.pattern = round(rng.uniform(6000, 8000), 2), 71, "mule out"
    s.run("frLayout()")
    out = HERE / "transfers-SIMULATED.gdf"
    assert s.run(f"exportGDF({str(out)!r})")
    print(f"  {out.name}: {len(g.nodes)} accounts, {len(g.edges)} transfers")


if __name__ == "__main__":
    claims(random.Random(11))
    transfers(random.Random(12))
