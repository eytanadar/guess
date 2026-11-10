from guess import Session
from tests.test_gython import Recorder


def _pkg(tmp_path):
    p = tmp_path / "pkg"
    (p / "sub").mkdir(parents=True)
    (p / "tests").mkdir()
    (p / "__init__.py").write_text("from .core import run\n")
    (p / "core.py").write_text("import os\nfrom . import util\nfrom .sub import deep\n\n"
                               "def run():\n    from .sub import late\n    return util.helper()\n\n"
                               "class Thing:\n    pass\n")
    (p / "util.py").write_text("def helper():\n    return 1\n")
    (p / "sub" / "__init__.py").write_text("")
    (p / "sub" / "deep.py").write_text("from ..util import helper\nfrom pkg import core\n")
    (p / "sub" / "late.py").write_text("import pkg.util\n")
    (p / "tests" / "test_x.py").write_text("import pkg\n")
    return p


def _edges(g):
    return sorted((e._n1.module, e._n2.module, e.toplevel) for e in g.edges)


def test_make_from_imports(tmp_path):
    s = Session(Recorder())
    p = _pkg(tmp_path)
    assert s.run(f"makeFromImports({str(p)!r})")
    g = s.graph
    mods = sorted(n.module for n in g.nodes)
    assert mods == ["pkg", "pkg.core", "pkg.sub", "pkg.sub.deep", "pkg.sub.late", "pkg.util"]   # no tests
    assert _edges(g) == [
        ("pkg", "pkg.core", True),
        ("pkg.core", "pkg.sub.deep", True),
        ("pkg.core", "pkg.sub.late", False),          # imported inside run(): deferred
        ("pkg.core", "pkg.util", True),
        ("pkg.sub.deep", "pkg.core", True),           # a cycle with core
        ("pkg.sub.deep", "pkg.util", True),
        ("pkg.sub.late", "pkg.util", True),
    ]
    core = g.getNodeByName("pkg_core")
    assert (core.functions, core.classes, core.package, core.depth) == (1, 1, "pkg", 1)
    assert s.run(f"makeFromImports({str(p)!r}, external=true, tests=true)")
    mods = {n.module: n.external for n in s.graph.nodes}
    assert mods["os"] is True and "pkg.tests.test_x" in mods
    assert s.run(f"makeFromImports({str(p)!r}, level=2)")
    assert sorted(n.module for n in s.graph.nodes) == ["pkg", "pkg.core", "pkg.sub", "pkg.util"]


def test_make_from_calls(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def a():\n    b(); b()\n    return C().go()\n\ndef b():\n    return 1\n\n"
                 "class C:\n    def go(self):\n        return self._help()\n    def _help(self):\n        return b()\n")
    s = Session(Recorder())
    assert s.run(f"makeFromCalls({str(f)!r})")
    g = s.graph
    calls = sorted((e._n1.function, e._n2.function, e.weight) for e in g.edges)
    assert calls == [("C._help", "b", 1.0), ("C.go", "C._help", 1.0), ("a", "b", 2.0)]
    assert not g.getNodeByName("C__help").public and g.getNodeByName("a").public
