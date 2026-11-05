"""GDF reader/writer, ported from com/hp/hpl/guess/io/GDFReader.java.

    nodedef> name,x,y,jobfun VARCHAR(100),dept VARCHAR(32)
    v1,254.6,370.9,employee,dept
    edgedef> node1,node2,hierarchy BIT default true, freq INT default 0
    v298,v123,true,103
"""
import random

from .model import BOOL, DOUBLE, INT, STRING, GuessError, coerce, normalize_type


def split_line(line):
    """Split a GDF data line on commas, honouring single/double quotes and \\n, \\t."""
    if "'" not in line and '"' not in line and "\\" not in line:
        return line.split(",")
    out = []
    cur = None
    in_quote = False
    quote = "'"
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] in "nt":
            cur = (cur or "") + ("\n" if line[i + 1] == "n" else "\t")
            i += 2
            continue
        if in_quote:
            if ch == quote:
                in_quote = False
                out.append(cur or "")
                cur = None
                i += 1
                continue
        else:
            if ch == ",":
                if cur is not None:
                    out.append(cur)
                elif i > 0 and line[i - 1] == ",":
                    out.append("")
                cur = None
                i += 1
                continue
            if ch in "'\"":
                in_quote = True
                quote = ch
                cur = ""
                i += 1
                continue
        cur = (cur or "") + ch
        i += 1
    if cur is not None or line.endswith(","):
        out.append(cur or "")
    return out


def _parse_def(defn, schema, add_field, kind):
    cols = []
    for raw in defn.split(","):
        parts = raw.strip().split()
        if not parts:
            continue
        name = parts[0].lower()
        ftype = None
        default = None
        j = 1
        while j < len(parts):
            if parts[j].lower() == "default" and j + 1 < len(parts):
                default = parts[j + 1].strip("'\"")
                j += 2
                continue
            if ftype is None:
                ftype = normalize_type(parts[j])
            j += 1
        if name in ("node1", "node2", "directed", "__edgeid") and kind == "edge":
            cols.append(name)
            continue
        f = schema.get(name)
        if f is None:
            add_field(name, ftype or STRING, default)
        elif default is not None and not f.readonly:
            f.default = coerce(f.type, default)
        cols.append(name)
    return cols


def read(graph, text):
    """Load GDF text into graph. Returns (nodes_added, edges_added)."""
    node_cols = edge_cols = None
    mode = None
    has_xy = False
    added_nodes = []
    added_edges = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        if low.startswith("nodedef>"):
            node_cols = _parse_def(line[8:], graph.node_schema, graph.addNodeField, "node")
            if "name" not in node_cols:
                raise GuessError("No name column, invalid GDF file")
            has_xy = "x" in node_cols or "y" in node_cols
            mode = "node"
            continue
        if low.startswith("edgedef>"):
            edge_cols = _parse_def(line[8:], graph.edge_schema, graph.addEdgeField, "edge")
            if "node1" not in edge_cols or "node2" not in edge_cols:
                raise GuessError("No node1/node2 column, invalid GDF file")
            mode = "edge"
            continue
        vals = split_line(line)
        if mode == "node":
            name = vals[node_cols.index("name")].strip()
            n = graph.addNode(name)
            n.label = name
            for col, v in zip(node_cols, vals):
                if col == "name":
                    continue
                _set(n, graph.node_schema[col], v, lineno)
            if not has_xy:
                n.x = random.random() * 500
                n.y = random.random() * 500
            added_nodes.append(n)
        elif mode == "edge":
            row = dict(zip(edge_cols, vals))
            directed = False
            if "directed" in row:
                directed = coerce(BOOL, row["directed"])
            n1 = graph.getNodeByName(row["node1"].strip())
            n2 = graph.getNodeByName(row["node2"].strip())
            if n1 is None or n2 is None:
                missing = row["node1"] if n1 is None else row["node2"]
                raise GuessError(f"line {lineno}: edge refers to unknown node {missing!r}")
            e = graph.addEdge(n1, n2, directed)
            for col, v in row.items():
                if col in ("node1", "node2", "directed", "__edgeid"):
                    continue
                _set(e, graph.edge_schema[col], v, lineno)
            added_edges += 1
        else:
            raise GuessError(f"line {lineno}: data before nodedef>/edgedef>: {line!r}")
    return len(added_nodes), added_edges


def _set(elem, field, raw, lineno):
    if field.readonly:
        return
    raw = raw.strip()
    if raw == "" and field.type != STRING:
        return
    try:
        field.set(elem, raw if raw != "" else None)
    except GuessError as e:
        raise GuessError(f"line {lineno}: {e}") from None


_SQL = {STRING: "VARCHAR(256)", INT: "INT", DOUBLE: "DOUBLE", BOOL: "BOOLEAN"}


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v)
    if any(c in s for c in ",'\"\n"):
        s = "'" + s.replace("\n", "\\n").replace("'", "") + "'"
    return s


def write(graph):
    nfields = [f for f in graph.node_schema.values() if f.compute is None or f.name == "name"]
    efields = [f for f in graph.edge_schema.values() if f.compute is None]
    out = ["nodedef> " + ",".join(
        f.name if f.name == "name" else f"{f.name} {_SQL[f.type]}" for f in nfields)]
    for n in graph._nodes_list():
        out.append(",".join(_fmt(f.get(n)) for f in nfields))
    out.append("edgedef> node1,node2,directed BOOLEAN," + ",".join(
        f"{f.name} {_SQL[f.type]}" for f in efields))
    for e in graph._edges_list():
        out.append(",".join([_fmt(e._n1._name), _fmt(e._n2._name), _fmt(e._directed)] +
                            [_fmt(f.get(e)) for f in efields]))
    return "\n".join(out) + "\n"


__all__ = ["read", "write", "split_line", "DOUBLE", "INT"]
