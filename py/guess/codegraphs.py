"""Networks of code: which modules import which, which functions call which.

    makeFromImports("networkx")        a package's module import graph
    makeFromCalls("networkx.algorithms.shortest_paths.generic")
"""
import ast
import importlib.util
import os
import re

from .model import BOOL, DOUBLE, INT, STRING, GuessError


def _ident(s):
    s = re.sub(r"\W+", "_", str(s)).strip("_") or "m"
    return "_" + s if s[0].isdigit() else s


def package_files(target, tests=False):
    """[(dotted module name, path)] for a package name or a folder/file path."""
    if os.path.exists(target):
        root = os.path.abspath(target)
        if os.path.isfile(root):
            return [(os.path.splitext(os.path.basename(root))[0], root)], os.path.splitext(os.path.basename(root))[0]
        base = os.path.basename(root.rstrip(os.sep))
        parent = os.path.dirname(root.rstrip(os.sep))
    else:
        spec = importlib.util.find_spec(str(target))
        if spec is None:
            raise GuessError(f"no package or folder {target!r}")
        if spec.submodule_search_locations:
            root = list(spec.submodule_search_locations)[0]
            base, parent = str(target).split(".")[-1], os.path.dirname(root)
            prefix = str(target).rsplit(".", 1)[0] + "." if "." in str(target) else ""
        else:
            name = str(target)
            return [(name, spec.origin)], name
    prefix = locals().get("prefix", "")
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "__pycache__"))
                             and (tests or d not in ("tests", "test", "testing")))
        for f in sorted(filenames):
            if not f.endswith(".py"):
                continue
            if not tests and (f.startswith("test_") or f.endswith("_test.py") or f == "conftest.py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), parent)
            mod = rel[:-3].replace(os.sep, ".")
            if mod.endswith(".__init__"):
                mod = mod[: -len(".__init__")]
            out.append((prefix + mod, os.path.join(dirpath, f)))
    return out, prefix + base


def _parse(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        return ast.parse(src), src.count("\n") + 1
    except (SyntaxError, ValueError):
        return None, 0


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    def g():
        return session.graph

    @cmd
    def makeFromImports(target, external=False, tests=False, level=None):
        """makeFromImports("networkx") builds the import graph of a Python
        package (an installed package's name, or a folder or file of
        source): a node per module, an edge from each module to each module
        of the package it imports (importer -> imported). Nodes get `module`
        (the dotted name), `package` (its parent package), `depth`, `lines`,
        `functions` and `classes`; edges get `weight` (import statements) and
        `toplevel` (false when every import between the two happens inside a
        function: a deferred import, often used to dodge an import cycle).
        external=true also adds the outside packages imported (`external`
        true). level=k merges modules below depth k into their parent (e.g.
        level=2 gives one node per subpackage). Test modules are skipped
        unless tests=true. The code is parsed, never run."""
        files, root = package_files(str(target), tests)
        if not files:
            raise GuessError(f"no Python files in {target!r}")

        def cut(name):
            if level is None:
                return name
            parts = name.split(".")
            return ".".join(parts[:int(level)])

        modules = {m for m, _p in files}
        info, edges = {}, {}
        for mod, path in files:
            tree, lines = _parse(path)
            node = cut(mod)
            rec = info.setdefault(node, {"lines": 0, "functions": 0, "classes": 0, "files": 0})
            rec["lines"] += lines
            rec["files"] += 1
            if tree is None:
                continue
            is_pkg = os.path.basename(path) == "__init__.py"
            for item in ast.walk(tree):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    rec["functions"] += 1
                elif isinstance(item, ast.ClassDef):
                    rec["classes"] += 1
            # imports, noting whether each is at module level
            top = set()
            for stmt in tree.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)) and not any(
                            isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef))
                            for p in _ancestors(stmt, sub)):
                        top.add(id(sub))
            for sub in ast.walk(tree):
                if not isinstance(sub, (ast.Import, ast.ImportFrom)):
                    continue
                targets = []
                if isinstance(sub, ast.Import):
                    targets = [a.name for a in sub.names]
                else:
                    if sub.level:
                        base = mod.split(".") if is_pkg else mod.split(".")[:-1]
                        base = base[: len(base) - (sub.level - 1)] if sub.level > 1 else base
                        stem = ".".join(base + ([sub.module] if sub.module else []))
                    else:
                        stem = sub.module or ""
                    for a in sub.names:
                        full = f"{stem}.{a.name}" if stem else a.name
                        targets.append(full if full in modules else stem)
                for t in targets:
                    # the longest prefix that's a module of the package
                    parts = t.split(".")
                    hit = None
                    for k in range(len(parts), 0, -1):
                        cand = ".".join(parts[:k])
                        if cand in modules:
                            hit = cand
                            break
                    if hit is None:
                        if not external or t.split(".")[0] == root.split(".")[0]:
                            continue
                        hit = "ext:" + t.split(".")[0]
                    a, b = node, cut(hit) if not hit.startswith("ext:") else hit
                    if a == b:
                        continue
                    e = edges.setdefault((a, b), [0, False])
                    e[0] += 1
                    e[1] = e[1] or id(sub) in top
        gr = g()
        gr.clear()
        for f, t, d in (("module", STRING, None), ("package", STRING, None), ("depth", INT, 0),
                        ("lines", INT, 0), ("functions", INT, 0), ("classes", INT, 0), ("external", BOOL, False)):
            gr.addNodeField(f, t, d)
        gr.addEdgeField("toplevel", BOOL, True)
        if "weight" not in gr.edge_schema:
            gr.addEdgeField("weight", DOUBLE, 1.0)
        names = {}

        def node(m):
            if m not in names:
                ext = m.startswith("ext:")
                dotted = m[4:] if ext else m
                nm = _ident(dotted)
                while nm in gr._nodes:
                    nm += "_"
                n = gr.addNode(nm)
                n.label = dotted.split(".")[-1] if not ext else dotted
                n.module = dotted
                n.package = dotted.rsplit(".", 1)[0] if "." in dotted else dotted
                n.depth = dotted.count(".")
                n.external = ext
                r = info.get(m)
                if r:
                    n.lines, n.functions, n.classes = r["lines"], r["functions"], r["classes"]
                names[m] = nm
            return names[m]

        for m in sorted(info):
            node(m)
        for (a, b), (count, at_top) in sorted(edges.items()):
            gr.addDirectedEdge(node(a), node(b), weight=float(count), toplevel=at_top)
        session.ns["frLayout"]()
        session.scene()
        print(f"{len(info)} modules of {root}, {len(edges)} import links"
              + (f" ({sum(1 for k in names if k.startswith('ext:'))} outside packages)" if external else ""))

    @cmd
    def makeFromCalls(target):
        """makeFromCalls("package.module") builds a call graph of a module (a
        module name or a .py file): a node per function and method, an edge
        from each to the functions it calls. Calls are matched by name
        (f(), self.f(), cls.f(), Class.f()), so it's an approximation: calls
        through variables, other modules or dynamic dispatch are missed.
        Nodes get `function` (Class.name or name), `cls`, `lines`, `params`
        and `public` (no leading underscore); edges get `weight`, the number
        of call sites."""
        if os.path.exists(str(target)):
            path = str(target)
        else:
            spec = importlib.util.find_spec(str(target))
            if spec is None or not spec.origin or not spec.origin.endswith(".py"):
                raise GuessError(f"no Python module {target!r}")
            path = spec.origin
        tree, _lines = _parse(path)
        if tree is None:
            raise GuessError(f"can't parse {path}")
        defs = {}          # qualified name -> node info
        by_name = {}       # bare name -> [qualified names]

        def visit(body, cls=None):
            for item in body:
                if isinstance(item, ast.ClassDef):
                    visit(item.body, item.name)
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    q = f"{cls}.{item.name}" if cls else item.name
                    end = getattr(item, "end_lineno", item.lineno)
                    defs[q] = {"node": item, "cls": cls, "lines": end - item.lineno + 1,
                               "params": len(item.args.args) + len(item.args.kwonlyargs)}
                    by_name.setdefault(item.name, []).append(q)
                    visit(item.body, cls)          # nested functions belong to the same class
        visit(tree.body)
        if not defs:
            raise GuessError(f"no functions in {path}")
        calls = {}
        for q, d in defs.items():
            for sub in ast.walk(d["node"]):
                if not isinstance(sub, ast.Call):
                    continue
                f = sub.func
                name, owner = None, None
                if isinstance(f, ast.Name):
                    name = f.id
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    name, owner = f.attr, f.value.id
                if name not in by_name:
                    continue
                cands = by_name[name]
                if owner in ("self", "cls") and d["cls"]:
                    pick = [c for c in cands if c == f"{d['cls']}.{name}"] or cands
                elif owner and f"{owner}.{name}" in defs:
                    pick = [f"{owner}.{name}"]
                elif owner is None:
                    pick = [c for c in cands if "." not in c] or cands
                else:
                    continue
                for t in pick[:1]:
                    if t != q:
                        calls[(q, t)] = calls.get((q, t), 0) + 1
        gr = g()
        gr.clear()
        for fname, t, dflt in (("function", STRING, None), ("cls", STRING, None), ("lines", INT, 0),
                               ("params", INT, 0), ("public", BOOL, True)):
            gr.addNodeField(fname, t, dflt)
        if "weight" not in gr.edge_schema:
            gr.addEdgeField("weight", DOUBLE, 1.0)
        names = {}
        for q, d in defs.items():
            nm = _ident(q)
            while nm in gr._nodes:
                nm += "_"
            n = gr.addNode(nm)
            n.label, n.function, n.cls = q, q, d["cls"]
            n.lines, n.params = d["lines"], d["params"]
            n.public = not q.split(".")[-1].startswith("_")
            names[q] = nm
        for (a, b), w in calls.items():
            gr.addDirectedEdge(names[a], names[b], weight=float(w))
        session.ns["frLayout"]()
        session.scene()
        print(f"{len(defs)} functions, {len(calls)} call links in {os.path.basename(path)} "
              "(matched by name: an approximation)")


def _ancestors(root, target):
    """The nodes on the path from root down to target (exclusive), or []."""
    stack = [(root, [])]
    while stack:
        node, path = stack.pop()
        if node is target:
            return path
        for child in ast.iter_child_nodes(node):
            stack.append((child, path + [node]))
    return []
