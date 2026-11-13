"""ch18-kleinberg and ch18-hierarchical-search: greedy routing in navigable small worlds."""
import random

from tests.test_explainers import App, _in_data_folder  # noqa: F401


def test_kleinberg_greedy_routing_and_the_best_alpha():
    a = App("ch18-kleinberg")
    assert not a.errors(), a.errors()
    assert a.ev("len(g.nodes)") == 225 and a.ev("len([e for e in g.edges if e.kind == 'long'])") == 225
    before = a.ev("{v.name: (v.x, v.y) for v in g.nodes}")
    # every greedy hop gets at least one step closer, and the message arrives
    a.press("Send a message")
    a.tick(80)
    d = a.ev("msg['dist']")
    assert a.ev("msg['at'] == msg['dst']") and all(x > y for x, y in zip(d, d[1:]))
    assert "Delivered" in a.markdown()
    assert a.ev("{v.name: (v.x, v.y) for v in g.nodes}") == before          # nodes never move
    # contacts thin out with distance: higher alpha, nearer contacts
    mean_r = {}
    for alpha in (0.0, 3.0):
        rnd = random.Random(4)
        draws = [a["draw_contact"](7, 7, 15, alpha, rnd) for _ in range(2000)]
        mean_r[alpha] = sum(abs(x - 7) + abs(y - 7) for x, y in draws) / len(draws)
        assert all(0 <= x < 15 and 0 <= y < 15 and (x, y) != (7, 7) for x, y in draws)
    assert mean_r[3.0] < 0.5 * mean_r[0.0]
    # clicking picks a start and then a target; the slider rebuilds the contacts
    a.click("c02_03")
    a.click("c12_11")
    assert a.ev("(msg['src'], msg['dst'])") == ((2, 3), (12, 11))
    a.s.run("aslider.value = 3\nset_alpha()")
    assert a.ev("net['alpha']") == 3.0 and not a.errors()
    # on a hundred million people alpha = 2 beats alpha = 0 and alpha = 3, and the best alpha moves up with n
    a.tab("Best α")
    a.press("Simulate: delivery time at each α")
    a.tick(12)
    rows = a.ev("sweep['rows']")
    big = dict(rows["n = 10⁸ (10,000 × 10,000)"])
    assert big[2.0] < big[0.0] and big[2.0] < big[3.0]
    best = [min(pts, key=lambda p: p[1])[0] for pts in rows.values()]
    assert best[-1] >= best[0] and 1.5 <= best[-1] <= 2.0
    assert "creeps" in a.markdown()
    a.press("400 messages on this grid")
    assert len(a.ev("hist['times']")) == 400 and not a.errors()
    # as n grows, alpha = 2 ends up far ahead
    a.tab("As n grows")
    a.press("Simulate: growing grids")
    a.tick(10)
    sc = a.ev("scale['rows']")
    last = {al: pts[-1][1] for al, pts in sc.items()}
    assert last[2.0] < last[0.0] < last[3.0]
    assert not a.errors(), a.errors()


def test_hierarchical_model_routing_and_searchability():
    a = App("ch18-hierarchical-search")
    assert not a.errors(), a.errors()
    assert a.ev("len(g.nodes)") == 128
    # distances in a hierarchy: same group 1, sibling groups 2, opposite halves of 16 groups 5
    assert a.ev("hdist(3, 3)") == 1 and a.ev("hdist(2, 3)") == 2 and a.ev("hdist(0, 15)") == 5
    # the first letter on a fresh network arrives, along friendships only
    a.press("Send the letter")
    a.tick(80)
    assert a.ev("msg['state']") == "delivered"
    path = a.ev("msg['path']")
    adj = a.ev("net['adj']")
    assert all(v in adj[u] for u, v in zip(path, path[1:])) and path[-1] == a.ev("msg['dst']")
    assert "Delivered" in a.markdown()
    # linked friendships come out where homophily says: alpha = 2 keeps most friends in the same small group
    a.s.run("hslider.value = 1\nset_h()\naslider.value = 2\nset_alpha()")
    assert not a.errors(), a.errors()
    leaf, adj = a.ev("net['leaf']"), a.ev("net['adj']")
    same = sum(1 for u in range(len(adj)) for v in adj[u] if leaf[0][u] == leaf[0][v])
    total = sum(len(x) for x in adj)
    assert same > 0.6 * total
    # with nobody giving up, greedy search on two hierarchies nearly always arrives
    leaf2, adj2 = a["make_model"](4, 8, 2, 1.0, 4, 3)
    rnd = random.Random(5)
    ok = sum(a["route"](rnd.randrange(128), rnd.randrange(128), leaf2, adj2, 2, 0.0, rnd)[0] for _ in range(100))
    assert ok >= 90
    # searchability: one hierarchy fails at strong homophily, two keep working
    a.tab("Searchable networks")
    a.press("Simulate: letters at each homophily")
    a.tick(12)
    rows = a.ev("sim['rows']")
    one, two = dict(rows["1 hierarchy"]), dict(rows["2 hierarchies"])
    assert one[2.0] < 0.15 and two[2.0] > 0.4 and two[1.0] > one[1.0]
    assert "Watts, Dodds and Newman" in a.markdown()
    assert not a.errors(), a.errors()
