"""sql(): SQL over the graph's fields (the original exposed its HSQLDB tables).

Two tables are materialised in an in-memory SQLite database on each call:

    nodes(name, <every node field>)
    edges(__edgeid, node1, node2, directed, <every edge field>)

    sql("SELECT dept, count(*) FROM nodes GROUP BY dept ORDER BY 2 DESC")
    sql("SELECT name FROM nodes WHERE x > y")            -> a set of nodes
    sql("SELECT __edgeid FROM edges WHERE freq > 100")   -> a set of edges
    sql("UPDATE nodes SET color = 'red' WHERE dept = 'dept3'")

SELECTs whose only column is `name` (nodes) or `__edgeid` (edges) return graph
elements, so they combine with the rest of Gython; other queries return rows.
UPDATEs are written back through the normal field setters (the display
updates). Inserting or deleting rows is not supported — use addNode/remove.
"""
import sqlite3

from .model import BOOL, DOUBLE, INT, GSet, GuessError

_SQL_TYPES = {INT: "INTEGER", DOUBLE: "REAL", BOOL: "INTEGER"}


def _q(name):
    return '"' + name.replace('"', '""') + '"'


def install(session):
    g = session.graph

    def build():
        db = sqlite3.connect(":memory:")
        nfields = [f for f in g.node_schema.values() if f.name != "name"]
        efields = [f for f in g.edge_schema.values() if f.name not in ("node1", "node2", "directed", "source", "destination")]
        db.execute("CREATE TABLE nodes (name TEXT PRIMARY KEY, "
                   + ", ".join(f"{_q(f.name)} {_SQL_TYPES.get(f.type, 'TEXT')}" for f in nfields) + ")")
        db.execute("CREATE TABLE edges (__edgeid INTEGER PRIMARY KEY, node1 TEXT, node2 TEXT, directed INTEGER, "
                   + ", ".join(f"{_q(f.name)} {_SQL_TYPES.get(f.type, 'TEXT')}" for f in efields) + ")")
        nodes = g._nodes_list()
        edges = g._edges_list()
        db.executemany(f"INSERT INTO nodes VALUES ({','.join('?' * (len(nfields) + 1))})",
                       ([n._name] + [f.get(n) for f in nfields] for n in nodes))
        db.executemany(f"INSERT INTO edges VALUES ({','.join('?' * (len(efields) + 4))})",
                       ([e._id, e._n1._name, e._n2._name, int(e._directed)] + [f.get(e) for f in efields]
                        for e in edges))
        return db, nfields, efields

    def sql(query):
        """Run SQL over tables `nodes` and `edges` (see help(sql) in the docs)."""
        db, nfields, efields = build()
        try:
            before = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("nodes", "edges")}
            cur = db.execute(query)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall() if cols else []
            after = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("nodes", "edges")}
        except sqlite3.Error as e:
            raise GuessError(f"SQL error: {e}") from None
        if before != after:
            raise GuessError("sql() can't add or delete rows; use addNode/addEdge/remove")
        if db.total_changes:
            _write_back(db, nfields, efields)
        if cols == ["name"]:
            return GSet((g._nodes[r[0]] for r in rows if r[0] in g._nodes), f"sql: {query}")
        if cols == ["__edgeid"]:
            return GSet((g._edges[r[0]] for r in rows if r[0] in g._edges), f"sql: {query}")
        return [r[0] for r in rows] if len(cols) == 1 else rows

    def _write_back(db, nfields, efields):
        writable = [f for f in nfields if not f.readonly]
        for row in db.execute("SELECT name, " + ", ".join(_q(f.name) for f in writable) + " FROM nodes"):
            n = g._nodes.get(row[0])
            for f, v in zip(writable, row[1:]):
                if n is not None and f.get(n) != _back(f, v):
                    f.set(n, _back(f, v))
        writable = [f for f in efields if not f.readonly]
        for row in db.execute("SELECT __edgeid, " + ", ".join(_q(f.name) for f in writable) + " FROM edges"):
            e = g._edges.get(row[0])
            for f, v in zip(writable, row[1:]):
                if e is not None and f.get(e) != _back(f, v):
                    f.set(e, _back(f, v))

    sql.__doc__ = __doc__.split("\n", 1)[1].strip()
    session.register_command("sql", sql)


def _back(field, v):
    if v is None:
        return None
    if field.type == BOOL:
        return bool(v)
    return v
