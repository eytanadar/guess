"""Gython -> Python 3 compiler.

Stage 1 (tokens): the Gython infix operators are rewritten into a chained
``is`` comparison around a marker name, e.g. ``a->b`` becomes
``a is __gop_dir__ is b``. Python's own parser then gives them comparison
precedence, which is where the original grammar (python.jjt) put them.

Stage 2 (AST):
  * marker comparisons      -> ``__gop__('dir', a, b)``
  * attribute load / store  -> ``__ggetattr__`` / ``__gsetattr__`` (broadcast over tuples/lists)
  * ``a & b``, ``a | b``    -> ``__gand__`` / ``__gor__`` (set algebra on tuples of nodes)
  * ``a - b``               -> ``__gsub__`` (undirected edges between, as in the original)
  * ``3 < degree < 6``      -> ``__gchain__`` (query sets intersect; plain values compare as usual)
  * ``degree in (1, 2)``    -> ``__gin__`` (a membership query when the left side is a field)
  * f-strings               -> ``__gfstr__`` (the same text, remembering the nodes and
    edges in it, so print() can link them)
  * ``a and b``, ``a or b``, ``not a`` used as values -> ``__gbool__`` / ``__gnot__``
    (on query sets: intersection, union, complement). In the test of an if, while,
    conditional expression, assert or comprehension filter they stay plain Python.
  * bare-name statement     -> ``__autocall__(name)`` (``randomLayout`` without parens)
  * top-level expressions   -> ``__display__(value)`` (interactive echo)
  * rebinding a protected name (``g = 5``) at module scope is a compile error
"""
import ast
import io
import keyword
import tokenize

MARKERS = {
    "__gop_dir__": "dir",          # ->
    "__gop_rdir__": "rdir",        # <-
    "__gop_bi__": "bi",            # <->
    "__gop_any__": "any",          # ?
    "__gop_like__": "like",
    "__gop_roverlaps__": "roverlaps",
    "__gop_rcontains__": "rcontains",
    "__gop_rexact__": "rexact",
    "__gop_rcontained__": "rcontained",
}
_MARKER_FOR = {v: k for k, v in MARKERS.items()}
WORD_OPS = {"like", "roverlaps", "rcontains", "rexact", "rcontained", "roverlap"}

_OPEN = "([{"
_CLOSE = ")]}"


class GythonSyntaxError(SyntaxError):
    pass


class ProtectedNameError(GythonSyntaxError):
    pass


# --------------------------------------------------------------------------
# Stage 1: token rewrite
# --------------------------------------------------------------------------

def _ends_operand(tok):
    if tok is None:
        return False
    if tok.type == tokenize.NAME:
        return not keyword.iskeyword(tok.string) or tok.string in ("None", "True", "False")
    if tok.type in (tokenize.NUMBER, tokenize.STRING):
        return True
    if tok.type == tokenize.OP and tok.string in _CLOSE:
        return True
    return getattr(tokenize, "FSTRING_END", -1) == tok.type or getattr(tokenize, "TSTRING_END", -1) == tok.type


def _starts_operand(tok):
    if tok is None:
        return False
    if tok.type == tokenize.NAME:
        return tok.string not in ("and", "or", "if", "else", "for", "in", "is") or tok.string == "not"
    if tok.type in (tokenize.NUMBER, tokenize.STRING):
        return True
    if tok.type == tokenize.OP and tok.string in "([{-+~":
        return True
    return getattr(tokenize, "FSTRING_START", -1) == tok.type or getattr(tokenize, "TSTRING_START", -1) == tok.type


def rewrite_tokens(source):
    """Return source with Gython operators replaced by marker comparisons."""
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(source).readline)
                if t.type not in (tokenize.COMMENT, tokenize.NL)]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return source  # let the parser report the problem
    edits = []  # (start(row,col), end(row,col), text)
    depth = 0
    in_def = False
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        prev = toks[i - 1] if i > 0 else None
        nxt = toks[i + 1] if i + 1 < n else None
        if t.type == tokenize.NAME and t.string == "def":
            in_def = True
        elif t.type == tokenize.OP:
            s = t.string
            if s in _OPEN:
                depth += 1
            elif s in _CLOSE:
                depth = max(0, depth - 1)
            elif s == ":" and depth == 0:
                in_def = False
            elif s == "->" and not in_def:
                edits.append((t.start, t.end, "dir"))
            elif s == "<" and nxt is not None and nxt.type == tokenize.OP and nxt.start == t.end:
                if nxt.string == "->":
                    edits.append((t.start, nxt.end, "bi"))
                    i += 2
                    continue
                after = toks[i + 2] if i + 2 < n else None
                if nxt.string == "-" and not (after is not None and after.type == tokenize.NUMBER):
                    edits.append((t.start, nxt.end, "rdir"))
                    i += 2
                    continue
            elif s == "?":
                edits.append((t.start, t.end, "any"))
        elif t.type == tokenize.NAME and t.string in WORD_OPS:
            if _ends_operand(prev) and _starts_operand(nxt):
                op = "roverlaps" if t.string == "roverlap" else t.string
                edits.append((t.start, t.end, op))
        i += 1
    if not edits:
        return source
    lines = source.splitlines(keepends=True)
    for (srow, scol), (erow, ecol), op in reversed(edits):
        assert srow == erow
        line = lines[srow - 1]
        lines[srow - 1] = line[:scol] + f" is {_MARKER_FOR[op]} is " + line[ecol:]
    return "".join(lines)


# --------------------------------------------------------------------------
# Stage 2: AST transform
# --------------------------------------------------------------------------

def _call(name, *args):
    return ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=list(args), keywords=[])


def _is_marker(node):
    return isinstance(node, ast.Name) and node.id in MARKERS


_NO_THUNK = (ast.NamedExpr, ast.Yield, ast.YieldFrom, ast.Await)


def _thunkable(*nodes):
    """Whether these expressions can be wrapped in ``lambda: ...`` unchanged."""
    return not any(isinstance(n, _NO_THUNK) for x in nodes for n in ast.walk(x))


def _thunk(expr):
    args = ast.arguments(posonlyargs=[], args=[], vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None,
                         defaults=[])
    return ast.Lambda(args=args, body=expr)


_WHAT = {
    "command": "'{n}' is the GUESS command {n}(); call yours something else ({n}_, say), "
               "or import your own explicitly (from module import {n})",
    "color": "'{n}' is a GUESS colour; call yours something else ({n}_, say)",
    "field": "'{n}' is a field of this graph (n.{n} on a node, Node.{n} for the field); "
             "call yours something else",
    "node": "'{n}' is a node of this graph (write {n}.color = red to change it); call yours something else",
    "graph": "'{n}' is the graph; call yours something else",
}


class _Transformer(ast.NodeTransformer):
    def __init__(self, is_protected, interactive, imports=None):
        self.is_protected = is_protected or (lambda name: False)
        self.interactive = interactive
        self.imports = imports           # protected names an import takes over (filled in)
        self.loop_target = False
        self.scope = 0                 # >0 inside function/class/lambda bodies
        self.globals_stack = [set()]   # names declared `global` in the current function

    # ---- protected names -------------------------------------------------
    def _check_store(self, name, node):
        at_module = self.scope == 0 or name in self.globals_stack[-1]
        kind = self.is_protected(name) if at_module else None
        if kind and self.loop_target and kind == "node":
            return          # for n in g.nodes: is fine even with a node called n (for this cell)
        if kind:
            text = _WHAT.get(kind if isinstance(kind, str) else "", "'{n}' is a GUESS system name "
                             "(graph, node, field or color) and cannot be reassigned").format(n=name)
            err = ProtectedNameError(text)
            err.lineno = getattr(node, "lineno", None)
            err.offset = getattr(node, "col_offset", 0) + 1
            raise err

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._check_store(node.id, node)
        elif _is_marker(node):
            raise GythonSyntaxError("misplaced graph operator")
        return node

    def _enter_function(self, node):
        declared = set()
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Global):
                declared.update(stmt.names)
        self.globals_stack.append(declared)
        self.scope += 1

    def _leave_function(self):
        self.globals_stack.pop()
        self.scope -= 1

    def visit_FunctionDef(self, node):
        self._check_store(node.name, node)
        for d in node.decorator_list:
            self.visit(d)
        self.visit(node.args)
        self._enter_function(node)
        node.body = [self.visit(s) for s in node.body]
        node.body = _flatten_stmts(node.body)
        self._leave_function()
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._check_store(node.name, node)
        node.bases = [self.visit(b) for b in node.bases]
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        self.scope += 1
        self.globals_stack.append(set())
        node.body = _flatten_stmts([self.visit(s) for s in node.body])
        self.globals_stack.pop()
        self.scope -= 1
        return node

    def visit_Lambda(self, node):
        self.visit(node.args)
        self.scope += 1
        self.globals_stack.append(set())
        node.body = self.visit(node.body)
        self.globals_stack.pop()
        self.scope -= 1
        return node

    def _visit_comp(self, node):
        self.scope += 1
        self.globals_stack.append(set())
        node = self.generic_visit(node)
        self.globals_stack.pop()
        self.scope -= 1
        return node

    visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _visit_comp

    def visit_alias(self, node):
        name = node.asname or node.name.split(".")[0]
        if name != "*":
            at_module = self.scope == 0 or name in self.globals_stack[-1]
            kind = self.is_protected(name) if at_module else None
            if kind and kind != "graph" and self.imports is not None:
                self.imports.add(name)       # an explicit import wins (the session says so)
            else:
                self._check_store(name, node)
        return node

    def visit_For(self, node):
        self.loop_target = True
        node.target = self.visit(node.target)
        self.loop_target = False
        node.iter = self.visit(node.iter)
        node.body = _flatten_stmts([self.visit(s) for s in node.body])
        node.orelse = _flatten_stmts([self.visit(s) for s in node.orelse])
        return node

    visit_AsyncFor = visit_For

    # ---- graph operators -----------------------------------------------
    def visit_Compare(self, node):
        node = self.generic_visit_compare(node)
        operands = [node.left] + list(node.comparators)
        ops = list(node.ops)
        if not any(_is_marker(o) for o in operands):
            return self._plain_compare(node)
        i = 0
        while i < len(ops):
            if i + 1 < len(operands) and _is_marker(operands[i + 1]):
                if not (i + 2 < len(operands) and isinstance(ops[i], ast.Is)
                        and isinstance(ops[i + 1], ast.Is)):
                    raise GythonSyntaxError("malformed graph operator expression")
                call = _call("__gop__", ast.Constant(MARKERS[operands[i + 1].id]),
                             operands[i], operands[i + 2])
                operands[i:i + 3] = [call]
                ops[i:i + 2] = []
                continue
            i += 1
        if len(operands) == 1:
            return ast.copy_location(operands[0], node)
        return ast.copy_location(ast.Compare(left=operands[0], ops=ops, comparators=operands[1:]), node)

    def _plain_compare(self, node):
        ops = node.ops
        if len(ops) == 1 and isinstance(ops[0], (ast.In, ast.NotIn)):
            return ast.copy_location(_call("__gin__", node.left, node.comparators[0],
                                           ast.Constant(isinstance(ops[0], ast.NotIn))), node)
        if len(ops) > 1 and _thunkable(*node.comparators):
            pairs = [ast.Tuple(elts=[ast.Constant(type(op).__name__), _thunk(c)], ctx=ast.Load())
                     for op, c in zip(ops, node.comparators)]
            return ast.copy_location(_call("__gchain__", node.left, *pairs), node)
        return node

    # ---- f-strings ------------------------------------------------------------
    def visit_JoinedStr(self, node):
        parts = []
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                spec = self.visit(v.format_spec) if v.format_spec is not None else ast.Constant(None)
                parts.append(ast.Tuple(elts=[self.visit(v.value), ast.Constant(v.conversion), spec],
                                       ctx=ast.Load()))
            else:
                parts.append(v)
        return ast.copy_location(_call("__gfstr__", *parts), node)

    # ---- and / or / not ----------------------------------------------------
    def _visit_test(self, expr):
        """The boolean skeleton of a test stays plain Python (``if s and t:``)."""
        if isinstance(expr, ast.BoolOp):
            expr.values = [self._visit_test(v) for v in expr.values]
            return expr
        if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
            expr.operand = self._visit_test(expr.operand)
            return expr
        return self.visit(expr)

    def visit_BoolOp(self, node):
        node.values = [self.visit(v) for v in node.values]
        if not _thunkable(*node.values[1:]):
            return node
        op = "and" if isinstance(node.op, ast.And) else "or"
        return ast.copy_location(_call("__gbool__", ast.Constant(op), node.values[0],
                                       *[_thunk(v) for v in node.values[1:]]), node)

    def visit_UnaryOp(self, node):
        node.operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return ast.copy_location(_call("__gnot__", node.operand), node)
        return node

    def visit_If(self, node):
        node.test = self._visit_test(node.test)
        node.body = _flatten_stmts([self.visit(s) for s in node.body])
        node.orelse = _flatten_stmts([self.visit(s) for s in node.orelse])
        return node

    visit_While = visit_If

    def visit_IfExp(self, node):
        node.test = self._visit_test(node.test)
        node.body = self.visit(node.body)
        node.orelse = self.visit(node.orelse)
        return node

    def visit_Assert(self, node):
        node.test = self._visit_test(node.test)
        if node.msg is not None:
            node.msg = self.visit(node.msg)
        return node

    def visit_comprehension(self, node):
        node.target = self.visit(node.target)
        node.iter = self.visit(node.iter)
        node.ifs = [self._visit_test(t) for t in node.ifs]
        return node

    def generic_visit_compare(self, node):
        node.left = self._visit_operand(node.left)
        node.comparators = [self._visit_operand(c) for c in node.comparators]
        return node

    def _visit_operand(self, n):
        return n if _is_marker(n) else self.visit(n)

    def visit_BinOp(self, node):
        node = self.generic_visit(node)
        if isinstance(node.op, ast.BitAnd):
            return ast.copy_location(_call("__gand__", node.left, node.right), node)
        if isinstance(node.op, ast.BitOr):
            return ast.copy_location(_call("__gor__", node.left, node.right), node)
        if isinstance(node.op, ast.Sub):
            return ast.copy_location(_call("__gsub__", node.left, node.right), node)
        return node

    # ---- attribute broadcast -------------------------------------------
    def visit_Attribute(self, node):
        node.value = self.visit(node.value)
        if isinstance(node.ctx, ast.Load):
            return ast.copy_location(_call("__ggetattr__", node.value, ast.Constant(node.attr)), node)
        return node

    def visit_Assign(self, node):
        node.value = self.visit(node.value)
        if not any(isinstance(t, ast.Attribute) for t in node.targets):
            node.targets = [self.visit(t) for t in node.targets]
            return node
        out = []
        if len(node.targets) == 1:
            value = node.value
        else:
            out.append(ast.Assign(targets=[ast.Name(id="__gtmp__", ctx=ast.Store())], value=node.value))
            value = ast.Name(id="__gtmp__", ctx=ast.Load())
        for t in node.targets:
            if isinstance(t, ast.Attribute):
                out.append(ast.Expr(_call("__gsetattr__", self.visit(t.value), ast.Constant(t.attr), value)))
            else:
                out.append(ast.Assign(targets=[self.visit(t)], value=value))
        for s in out:
            ast.copy_location(s, node)
        return out

    def visit_AugAssign(self, node):
        node.value = self.visit(node.value)
        if isinstance(node.target, ast.Attribute):
            op = type(node.op).__name__
            return ast.copy_location(ast.Expr(_call(
                "__gaugattr__", self.visit(node.target.value), ast.Constant(node.target.attr),
                ast.Constant(op), node.value)), node)
        if isinstance(node.op, ast.Sub) and isinstance(node.target, ast.Name):
            # s -= t means s = s - t, as `-` does (edges between node sets)
            target = self.visit(node.target)
            load = ast.Name(id=target.id, ctx=ast.Load())
            return ast.copy_location(ast.Assign(targets=[target], value=_call("__gisub__", load, node.value)), node)
        node.target = self.visit(node.target)
        return node

    # ---- statements -------------------------------------------------------
    def visit_Expr(self, node):
        value = node.value
        if isinstance(value, ast.Name):
            node.value = _call("__autocall__", value)
        else:
            node.value = self.visit(value)
        return node

    def visit_Module(self, node):
        body = []
        for stmt in node.body:
            new = self.visit(stmt)
            if self.interactive and isinstance(stmt, ast.Expr) and isinstance(new, ast.Expr):
                new.value = _call("__display__", new.value)
            body.extend(new if isinstance(new, list) else [new])
        node.body = body
        return node


def _flatten_stmts(stmts):
    out = []
    for s in stmts:
        if isinstance(s, list):
            out.extend(s)
        elif s is not None:
            out.append(s)
    return out


def transform(source, *, is_protected=None, interactive=True, filename="<console>", imports=None):
    rewritten = rewrite_tokens(source)
    tree = ast.parse(rewritten, filename=filename, mode="exec")
    tree = _Transformer(is_protected, interactive, imports).visit(tree)
    ast.fix_missing_locations(tree)
    return tree


def compile_gython(source, *, is_protected=None, interactive=True, filename="<console>", names=None,
                   imports=None):
    """Compile Gython to a code object. If `names` is a set, the bare names the
    code reads are added to it (so computed fields can be prepared first). If
    `imports` is a set, protected names that the code imports are added to it
    (and allowed); otherwise importing one is an error."""
    tree = transform(source, is_protected=is_protected, interactive=interactive, filename=filename,
                     imports=imports)
    if names is not None:
        names.update(n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load))
    return compile(tree, filename, "exec")


def to_python(source, **kw):
    """Debug helper: show the Python 3 the Gython source compiles to."""
    return ast.unparse(transform(source, **kw))
