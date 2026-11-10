from tests.test_gython import Recorder, ev, names, s  # noqa: F401


def test_save_load_and_indexing(s):
    s.run("j = jane; ss(1999)")
    s.run("bob.jobfunc = 'CEO'; (bob<->alice).freq = 50; remove(jane)")
    s.run("ss(2000)")
    assert ev(s, "bob[1999].jobfunc") == "Manager"
    assert ev(s, "bob[2000].jobfunc") == "CEO"
    assert names(ev(s, "freq[2000] > freq[1999]")) == ["bob-alice"]
    assert ev(s, "j[2000].jobfunc") is None
    s.run("ls(1999)")
    assert ev(s, "bob.jobfunc") == "Manager" and "jane" in s.ns
    assert len(s.graph.edges) == 4
    s.run("ls(2000)")
    assert "jane" not in s.ns and ev(s, "bob.jobfunc") == "CEO"
    assert ev(s, "getStates()") == [1999, 2000]
    s.rec.clear()
    assert not s.run("ls('nope')")
    assert "no saved state" in s.rec.of("error")[0]["text"]


def test_morph_marks_patch(s):
    s.run("ss('a'); g.nodes.x = 0; ss('b'); ls('a')")
    s.rec.clear()
    s.run("morph('b', 500)")
    patch = s.rec.of("patch")[-1]
    assert patch["morph"]["duration"] == 500
    assert all(n["x"] == 0 for n in patch["nodes"])


def test_ranges(s):
    s.run("addRange(bob, '1,5-10,20'); addRange(alice, '3-6'); addRange(bob<->alice, '7')")
    assert names(ev(s, "Node rcontains 5")) == ["alice", "bob"]
    assert names(ev(s, "Node rcontains (5, 7)")) == ["bob"]
    assert names(ev(s, "Edge roverlaps (4, 8)")) == ["bob-alice"]
    assert names(ev(s, "g rcontained '0-12'")) == ["alice", "bob-alice"]
    assert names(ev(s, "Node rexact '3-6'")) == ["alice"]
    assert names(ev(s, "searchOverlap('19-30')")) == ["bob"]
    assert ev(s, "getRange(bob)") == "1,5-10,20"
    s.run("addNodeField('span', VARCHAR, '')\nbob.span = '2-4'")
    assert names(ev(s, "span rcontains 3")) == ["bob"]



def test_field_find(s):
    assert names(ev(s, "jobfunc.find('Manager')")) == names(ev(s, "jobfunc == 'Manager'"))
    assert names(ev(s, "jobfunc.find('nobody')")) == []
    assert names(ev(s, "freq.find(freq.max)")) == names(ev(s, "freq == freq.max"))
