"""Biological network formats: PSI-MI (MITAB and XML), SBML, BioPAX, KEGG KGML
and WikiPathways GPML.

    makeFromMITAB("intact.txt")       molecular interactions, PSI-MI TAB 2.5-2.7
    makeFromPSIMI("intact.xml")       the same, PSI-MI XML 2.5 / 3.0
    makeFromSBML("model.xml")         a systems biology model (species, reactions)
    makeFromBioPAX("pathway.owl")     a BioPAX level 3 pathway, as a simple network
    makeFromKGML("hsa04115.xml")      a KEGG pathway map, with its layout
    makeFromGPML("WP707.gpml")        a WikiPathways pathway, with its layout

Each replaces the current graph. The readers use only the standard library;
names are made readable (gene names rather than accession numbers) and kept
unique (a clash gets its identifier appended).
"""
import os
import random
import re
import xml.etree.ElementTree as ET

from .model import BOOL, DOUBLE, INT, STRING, GuessError

# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _attr(el, name, default=None):
    """An attribute by local name (namespaced or not)."""
    v = el.get(name)
    if v is not None:
        return v
    for k, val in el.attrib.items():
        if _local(k) == name:
            return val
    return default


def _kids(el, name):
    if el is None:
        return []
    return [c for c in el if _local(c.tag) == name]


def _kid(el, name):
    if el is None:
        return None
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _path(el, *names):
    for n in names:
        el = _kid(el, n)
        if el is None:
            return None
    return el


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _parse_xml(text, what):
    try:
        return ET.fromstring(text)
    except ET.ParseError as ex:
        raise GuessError(f"{what}: not well-formed XML ({ex})") from None


def _num(v, default=None, kind=float):
    try:
        return kind(v)
    except (TypeError, ValueError):
        return default


def _hex(c):
    """A colour from KGML/GPML ("#BFFFBF", "BFFFBF", "Transparent") or None."""
    if not c:
        return None
    c = str(c).strip()
    if c.lower() in ("transparent", "none"):
        return None
    if re.fullmatch(r"[0-9A-Fa-f]{6}", c):
        c = "#" + c
    return c if re.fullmatch(r"#[0-9A-Fa-f]{6}", c) else None


class _Builder:
    """Typed fields, unique readable node names, edges with attributes."""

    def __init__(self, g, node_fields, edge_fields):
        self.g = g
        for name, ftype in node_fields.items():
            if name not in g.node_schema:
                g.addNodeField(name, ftype, None)
        for name, ftype in edge_fields.items():
            if name not in g.edge_schema:
                g.addEdgeField(name, ftype, None)
        self.nodes = {}            # key -> Node
        self.positions = False

    @staticmethod
    def unique_names(items):
        """{key: name} from [(key, preferred name, identifier)]: a name used by
        two keys gets its identifier (or a counter) appended."""
        count = {}
        for _k, name, _i in items:
            count[name] = count.get(name, 0) + 1
        out, used = {}, set()
        for key, name, ident in items:
            n = name if count[name] == 1 else f"{name}_{ident}" if ident and ident != name else name
            base, k = n, 1
            while n in used:
                k += 1
                n = f"{base}_{k}"
            used.add(n)
            out[key] = n
        return out

    def node(self, key, name, **vals):
        n = self.g.addNode(name)
        self.nodes[key] = n
        self.set(n, self.g.node_schema, vals)
        return n

    def edge(self, a, b, directed, **vals):
        e = self.g.addEdge(self.nodes[a], self.nodes[b], directed)
        self.set(e, self.g.edge_schema, vals)
        return e

    @staticmethod
    def set(elem, schema, vals):
        for k, v in vals.items():
            if v is None or v == "":
                continue
            f = schema.get(k)
            if f is None or f.readonly:
                continue
            try:
                f.set(elem, v)
            except (GuessError, ValueError, TypeError):
                pass

    def scatter(self):
        """Random positions when the file had none (a layout comes next)."""
        if not self.positions:
            for n in self.g._nodes_list():
                n.x, n.y = random.random() * 800, random.random() * 800


# --------------------------------------------------------------------------
# PSI-MI: interactions (shared by MITAB and XML)
# --------------------------------------------------------------------------

NODE_MI = {"kind": STRING, "ident": STRING, "taxid": INT, "species": STRING, "aliases": STRING}
EDGE_MI = {"kind": STRING, "method": STRING, "author": STRING, "pubmed": STRING, "sourcedb": STRING,
           "interaction": STRING, "miscore": DOUBLE, "confidence": STRING, "expansion": STRING,
           "negative": BOOL, "evidence": INT}


class _Interactions:
    """Collects interactors and pairwise evidence, then builds the graph."""

    def __init__(self, merge):
        self.merge = merge
        self.interactors = {}      # key -> dict(name, ident, kind, taxid, species, aliases)
        self.rows = []             # (keyA, keyB, attrs)

    def interactor(self, key, **info):
        old = self.interactors.get(key)
        if old is None:
            self.interactors[key] = info
        else:
            for k, v in info.items():
                if v and not old.get(k):
                    old[k] = v

    def add(self, a, b, attrs):
        self.rows.append((a, b, attrs))

    def build(self, g):
        b = _Builder(g, NODE_MI, EDGE_MI)
        items = [(k, v.get("name") or k, (v.get("ident") or k).split(":")[-1]) for k, v in self.interactors.items()]
        names = b.unique_names(items)
        for key, info in self.interactors.items():
            n = b.node(key, names[key], kind=info.get("kind"), ident=info.get("ident"), taxid=info.get("taxid"),
                       species=info.get("species"), aliases=info.get("aliases"))
            n.label = info.get("name") or names[key]
        lists = ("method", "author", "pubmed", "sourcedb", "interaction", "kind", "confidence", "expansion")
        if self.merge:
            merged = {}
            order = []
            for a, c, at in self.rows:
                key = (min(a, c), max(a, c), bool(at.get("negative")))
                m = merged.get(key)
                if m is None:
                    m = merged[key] = {"a": a, "b": c, "evidence": 0, "miscore": None,
                                       "negative": at.get("negative"), **{k: [] for k in lists}}
                    order.append(key)
                m["evidence"] += 1
                if at.get("miscore") is not None:
                    m["miscore"] = max(m["miscore"] or 0.0, at["miscore"])
                for k in lists:
                    for v in str(at.get(k) or "").split("|"):
                        if v and v not in m[k]:
                            m[k].append(v)
            for key in order:
                m = merged[key]
                b.edge(m["a"], m["b"], False, evidence=m["evidence"], miscore=m["miscore"],
                       negative=m["negative"], **{k: "|".join(m[k]) for k in lists})
            ne = len(order)
        else:
            for a, c, at in self.rows:
                b.edge(a, c, False, evidence=1, **at)
            ne = len(self.rows)
        b.scatter()
        return len(self.interactors), ne


# ---- MITAB ------------------------------------------------------------------

_ITEM = re.compile(r'''^\s*("(?:[^"\\]|\\.)*"|[^:"]*):("(?:[^"\\]|\\.)*"|[^(]*?)\s*(?:\((.*)\))?\s*$''')


def _split_items(field):
    """Split a MITAB field on '|' outside quotes and parentheses."""
    field = (field or "").strip()
    if field in ("", "-"):
        return []
    out, cur, depth, quote = [], [], 0, False
    for ch in field:
        if ch == '"':
            quote = not quote
        elif not quote and ch == "(":
            depth += 1
        elif not quote and ch == ")":
            depth = max(0, depth - 1)
        if ch == "|" and not quote and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [x for x in out if x.strip() and x.strip() != "-"]


def _items(field):
    """[(db, value, description)] from a MITAB field."""
    out = []
    for raw in _split_items(field):
        m = _ITEM.match(raw)
        if not m:
            out.append(("", raw.strip(), ""))
            continue
        db, val, desc = (x.strip() if x else "" for x in m.groups())
        out.append((db.strip('"'), val.strip('"'), (desc or "").strip('"')))
    return out


def _descs(field):
    return [d or v for _db, v, d in _items(field)]


def _mitab_name(alt, aliases, ident):
    for db, v, d in _items(alt) + _items(aliases):
        if d.lower() == "gene name":
            return v
    for db, v, d in _items(alt) + _items(aliases):
        if d.lower() in ("display_short", "short label", "shortlabel"):
            return v
    return ident.split(":", 1)[-1]


def _species(field):
    items = _items(field)
    if not items:
        return None, None
    tax = _num(items[0][1], None, int)
    desc = max((d for _db, _v, d in items), key=len, default="") or None
    return tax, desc


def read_mitab(text, merge=True):
    inter = _Interactions(merge)
    rows = 0
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        c = line.rstrip("\r\n").split("\t")
        if len(c) < 15:
            if rows == 0 and len(c) >= 2 and not any(":" in x for x in c[:2]):
                continue                       # a header without '#'
            raise GuessError(f"MITAB rows have at least 15 tab-separated columns; this one has {len(c)}")
        c += ["-"] * (42 - len(c))
        ids = []
        for side in (0, 1):
            first = _items(c[side])
            if not first:
                ids.append(None)
                continue
            db, v, _d = first[0]
            key = f"{db}:{v}" if db else v
            tax, species = _species(c[9 + side])
            kind = (_descs(c[20 + side]) or [None])[0] if len(c) > 21 else None
            aliases = "|".join(dict.fromkeys(v for _db, v, _d in _items(c[4 + side])))[:500]
            inter.interactor(key, name=_mitab_name(c[2 + side], c[4 + side], key), ident=key,
                             taxid=tax, species=species, kind=kind, aliases=aliases)
            ids.append(key)
        a, b = ids
        if a is None and b is None:
            continue
        if a is None:
            a = b
        if b is None:                          # intra-molecular: a self-loop
            b = a
        conf = _items(c[14])
        mi = next((_num(v) for db, v, _d in conf if "miscore" in db.lower()), None)
        attrs = dict(
            method="|".join(_descs(c[6])), author="|".join(v for v in c[7].split("|") if v and v != "-"),
            pubmed="|".join(v for db, v, _d in _items(c[8]) if db.lower() in ("pubmed", "imex", "doi")),
            kind="|".join(_descs(c[11])), sourcedb="|".join(_descs(c[12])),
            interaction="|".join(f"{db}:{v}" if db else v for db, v, _d in _items(c[13])),
            miscore=mi, confidence="|".join(f"{db}:{v}" for db, v, _d in conf if "miscore" not in db.lower()),
            expansion="|".join(_descs(c[15])) if c[15] not in ("", "-") else None,
            negative=c[35].strip().lower() == "true" if len(c) > 35 and c[35] not in ("", "-") else None)
        inter.add(a, b, attrs)
        rows += 1
    if not rows:
        raise GuessError("no interactions found (PSI-MI TAB has one interaction per line, 15+ columns)")
    return inter


# ---- PSI-MI XML -------------------------------------------------------------

def _label(el):
    """shortLabel, else fullName, of an element's <names>."""
    names = _kid(el, "names")
    return _text(_kid(names, "shortLabel")) or _text(_kid(names, "fullName"))


def _psi_interactor(el, inter):
    names = _kid(el, "names")
    gene = next((_text(a) for a in _kids(names, "alias") if (_attr(a, "type") or "").lower() == "gene name"), "") \
        if names is not None else ""
    ref = _path(el, "xref", "primaryRef")
    ident = f"{_attr(ref, 'db')}:{_attr(ref, 'id')}" if ref is not None else f"psi:{_attr(el, 'id')}"
    org = _kid(el, "organism")
    tax = _num(_attr(org, "ncbiTaxId"), None, int) if org is not None else None
    species = (_text(_path(org, "names", "fullName")) or _text(_path(org, "names", "shortLabel"))) if org is not None else None
    kind = _label(_kid(el, "interactorType")) if _kid(el, "interactorType") is not None else None
    aliases = "|".join(_text(a) for a in _kids(names, "alias"))[:500] if names is not None else ""
    inter.interactor(ident, name=gene or _label(el) or ident.split(":", 1)[-1], ident=ident, taxid=tax,
                     species=species, kind=kind, aliases=aliases)
    return ident


def read_psimi(text, merge=True):
    root = _parse_xml(text, "PSI-MI XML")
    if _local(root.tag) != "entrySet":
        raise GuessError("not PSI-MI XML (the root element should be <entrySet>)")
    inter = _Interactions(merge)
    count = 0
    for entry in _kids(root, "entry"):
        experiments, interactors = {}, {}
        for ex in _kids(_kid(entry, "experimentList"), "experimentDescription"):
            experiments[_attr(ex, "id")] = ex
        for el in _kids(_kid(entry, "interactorList"), "interactor"):
            interactors[_attr(el, "id")] = _psi_interactor(el, inter)
        for it in _kids(_kid(entry, "interactionList"), "interaction"):
            # experiments: by reference or inline
            exps = []
            exl = _kid(it, "experimentList")
            if exl is not None:
                for x in exl:
                    if _local(x.tag) == "experimentRef" and _text(x) in experiments:
                        exps.append(experiments[_text(x)])
                    elif _local(x.tag) == "experimentDescription":
                        exps.append(x)
            methods = [_label(_kid(e, "interactionDetectionMethod")) for e in exps
                       if _kid(e, "interactionDetectionMethod") is not None]
            pubs = []
            for e in exps:
                ref = _path(e, "bibref", "xref", "primaryRef")
                if ref is not None and _attr(ref, "id"):
                    pubs.append(_attr(ref, "id"))
            parts = []
            for p in _kids(_kid(it, "participantList"), "participant"):
                ref = _kid(p, "interactorRef")
                if ref is not None and _text(ref) in interactors:
                    key = interactors[_text(ref)]
                elif _kid(p, "interactor") is not None:
                    key = _psi_interactor(_kid(p, "interactor"), inter)
                else:
                    continue                    # an interactionRef (a complex as participant): skipped
                roles = [_label(r).lower() for r in _kids(_kid(p, "experimentalRoleList"),
                                                         "experimentalRole")]
                parts.append((key, "bait" in roles))
            if not parts:
                continue
            itype = "|".join(_label(t) for t in _kids(it, "interactionType"))
            conf = []
            mi = None
            for cf in _kids(_kid(it, "confidenceList"), "confidence"):
                unit = _label(_kid(cf, "unit")) if _kid(cf, "unit") is not None else ""
                val = _text(_kid(cf, "value"))
                if "miscore" in unit.lower():
                    mi = _num(val)
                elif unit or val:
                    conf.append(f"{unit}:{val}")
            neg = _text(_kid(it, "negative")).lower() == "true"
            iref = _path(it, "xref", "primaryRef")
            iid = f"{_attr(iref, 'db')}:{_attr(iref, 'id')}" if iref is not None else (_attr(it, "id") or "")
            keys = list(dict.fromkeys(k for k, _b in parts))
            baits = list(dict.fromkeys(k for k, b in parts if b))
            if len(keys) == 1:
                pairs, expansion = [(keys[0], keys[0])], None
            elif len(keys) == 2:
                pairs, expansion = [(keys[0], keys[1])], None
            elif baits:
                pairs = [(b, k) for b in baits for k in keys if k != b and not (k in baits and k < b)]
                expansion = "spoke expansion"
            else:
                pairs = [(keys[i], keys[j]) for i in range(len(keys)) for j in range(i + 1, len(keys))]
                expansion = "matrix expansion"
            attrs = dict(method="|".join(m for m in methods if m), pubmed="|".join(pubs), kind=itype,
                         interaction=iid, miscore=mi, confidence="|".join(conf), expansion=expansion,
                         negative=neg or None)
            for a, b in pairs:
                inter.add(a, b, dict(attrs))
            count += 1
    if not count:
        raise GuessError("no interactions found in the PSI-MI XML file")
    return inter


# --------------------------------------------------------------------------
# SBML
# --------------------------------------------------------------------------

NODE_SBML = {"kind": STRING, "sbml_id": STRING, "compartment": STRING, "initial": DOUBLE, "sbo": STRING,
             "boundary": BOOL, "reversible": BOOL}
EDGE_SBML = {"role": STRING, "stoichiometry": DOUBLE, "reaction": STRING}


def _sbo(el):
    v = _attr(el, "sboTerm")
    return v or None


def read_sbml(g, text, reactions="nodes"):
    root = _parse_xml(text, "SBML")
    if _local(root.tag) != "sbml":
        raise GuessError("not SBML (the root element should be <sbml>)")
    model = _kid(root, "model")
    if model is None:
        raise GuessError("the SBML file has no <model>")
    comps = {}
    for c in _kids(_kid(model, "listOfCompartments"), "compartment"):
        comps[_attr(c, "id")] = _attr(c, "name") or _attr(c, "id")
    species = _kids(_kid(model, "listOfSpecies"), "species")
    rxns = _kids(_kid(model, "listOfReactions"), "reaction")
    if not species:
        raise GuessError("the SBML model has no species")
    b = _Builder(g, NODE_SBML, EDGE_SBML)
    # names: a species name used in two compartments gets "[compartment]"
    sp_items = []
    for s in species:
        name = (_attr(s, "name") or _attr(s, "id")).strip()
        comp = comps.get(_attr(s, "compartment"), _attr(s, "compartment") or "")
        sp_items.append((("s", _attr(s, "id")), name, f"[{comp}]" if comp else _attr(s, "id")))
    count = {}
    for _k, n, _c in sp_items:
        count[n] = count.get(n, 0) + 1
    sp_items = [(k, n if count[n] == 1 else f"{n} {c}", k[1]) for k, n, c in sp_items]
    rx_items = [(("r", _attr(r, "id")), (_attr(r, "name") or _attr(r, "id")).strip(), _attr(r, "id")) for r in rxns]
    as_nodes = str(reactions).lower() != "edges"
    names = b.unique_names(sp_items + (rx_items if as_nodes else []))
    for s, (key, _n, _i) in zip(species, sp_items):
        init = _attr(s, "initialAmount") or _attr(s, "initialConcentration")
        n = b.node(key, names[key], kind="species", sbml_id=_attr(s, "id"),
                   compartment=comps.get(_attr(s, "compartment"), _attr(s, "compartment")),
                   initial=_num(init), sbo=_sbo(s), boundary=(_attr(s, "boundaryCondition") == "true") or None)
        n.label = _n
    refs = lambda r, lst, tag: [(x, _attr(x, "species")) for x in _kids(_kid(r, lst), tag)]
    ne = 0
    for r, (key, rname, rid) in zip(rxns, rx_items):
        reactants = refs(r, "listOfReactants", "speciesReference")
        products = refs(r, "listOfProducts", "speciesReference")
        modifiers = refs(r, "listOfModifiers", "modifierSpeciesReference")
        rev = _attr(r, "reversible", "true") != "false"
        st = lambda x: _num(_attr(x, "stoichiometry"), 1.0)
        if as_nodes:
            n = b.node(key, names[key], kind="reaction", sbml_id=rid, sbo=_sbo(r), reversible=rev)
            n.label = rname
            n.style, n.width, n.height, n.color = 1, 7.0, 7.0, "gray"
            for x, sid in reactants:
                if ("s", sid) in b.nodes:
                    b.edge(("s", sid), key, True, role="reactant", stoichiometry=st(x), reaction=rname)
                    ne += 1
            for x, sid in products:
                if ("s", sid) in b.nodes:
                    b.edge(key, ("s", sid), True, role="product", stoichiometry=st(x), reaction=rname)
                    ne += 1
            for x, sid in modifiers:
                if ("s", sid) in b.nodes:
                    b.edge(("s", sid), key, True, role="modifier", reaction=rname)
                    ne += 1
        else:
            for x, a in reactants:
                for y, c in products:
                    if ("s", a) in b.nodes and ("s", c) in b.nodes:
                        b.edge(("s", a), ("s", c), True, role="conversion", reaction=rname)
                        ne += 1
            for x, m in modifiers:
                for y, c in products:
                    if ("s", m) in b.nodes and ("s", c) in b.nodes:
                        b.edge(("s", m), ("s", c), True, role="modifier", reaction=rname)
                        ne += 1
    # the layout package: glyph bounding boxes
    for glyph in root.iter():
        tag = _local(glyph.tag)
        if tag not in ("speciesGlyph", "reactionGlyph"):
            continue
        ref = _attr(glyph, "species" if tag == "speciesGlyph" else "reaction")
        key = ("s" if tag == "speciesGlyph" else "r", ref)
        n = b.nodes.get(key)
        bb = _kid(glyph, "boundingBox")
        pos, dim = _kid(bb, "position"), _kid(bb, "dimensions")
        if n is None or pos is None:
            continue
        x, y = _num(_attr(pos, "x"), 0.0), _num(_attr(pos, "y"), 0.0)
        w = _num(_attr(dim, "width"), None) if dim is not None else None
        h = _num(_attr(dim, "height"), None) if dim is not None else None
        n.x, n.y = x, y
        if w and h and tag == "speciesGlyph":
            n.width, n.height = w, h
            n.style = 3
            n.labelpos = "inside"
            n.labelvisible = True
        b.positions = True
    b.scatter()
    return len(b.nodes), ne


# --------------------------------------------------------------------------
# BioPAX level 3
# --------------------------------------------------------------------------

BP = "http://www.biopax.org/release/biopax-level3.owl#"
_ENTITIES = {"Protein", "SmallMolecule", "Complex", "Rna", "Dna", "PhysicalEntity", "DnaRegion", "RnaRegion"}
_CONVERSIONS = {"Conversion", "BiochemicalReaction", "Transport", "TransportWithBiochemicalReaction",
                "ComplexAssembly", "Degradation"}
_CONTROLS = {"Control", "Catalysis", "Modulation", "TemplateReactionRegulation"}
_INTERACTIONS = {"MolecularInteraction", "GeneticInteraction"}

NODE_BP = {"kind": STRING, "xref": STRING, "uri": STRING}
EDGE_BP = {"kind": STRING, "sign": STRING, "count": INT, "reaction": STRING}


def _triples(text):
    from .webexport import parse_rdfxml, parse_turtle
    head = text.lstrip()[:400]
    if head.startswith("<"):
        return parse_rdfxml(text, "file:///biopax")
    return parse_turtle(text, "file:///biopax")


def read_biopax(g, text, mode="sif"):
    if "biopax-level2" in text[:5000] and BP not in text[:20000]:
        raise GuessError("this is BioPAX level 2; makeFromBioPAX reads level 3 (Pathway Commons and "
                         "Reactome export level 3)")
    triples = _triples(text)
    types, props = {}, {}
    for s, p, o in triples:
        if p == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type" and o[0] == "iri" and o[1].startswith(BP):
            types[s] = o[1][len(BP):]
            continue
        if p.startswith(BP):
            props.setdefault(s, {}).setdefault(p[len(BP):], []).append(o)
    if not types:
        raise GuessError("no BioPAX level 3 classes found (expected the namespace " + BP + ")")

    def lit(s, *names):
        for n in names:
            for o in props.get(s, {}).get(n, []):
                if o[0] == "lit" and str(o[1]).strip():
                    return str(o[1]).strip()
        return None

    def refs(s, name):
        return [o for o in props.get(s, {}).get(name, []) if o[0] != "lit"]

    def xref_of(s):
        for x in refs(s, "xref"):
            if types.get(x) == "UnificationXref":
                db, i = lit(x, "db"), lit(x, "id")
                if i:
                    return f"{db}:{i}" if db else i
        return None

    # an entity is merged with others of the same entityReference (one node per protein)
    def key_of(e):
        if types.get(e) == "Complex":
            return e
        er = refs(e, "entityReference")
        return er[0] if er else e

    def name_of(e):
        k = key_of(e)
        n = lit(e, "displayName", "standardName", "name") or lit(k, "displayName", "standardName", "name")
        if n:
            return n
        if types.get(e) == "Complex":
            comps = [name_of(c) for c in refs(e, "component")][:4]
            if comps:
                return ":".join(comps)
        uri = e[1] if e[0] == "iri" else str(e[1])
        return re.split(r"[#/]", uri)[-1] or "entity"

    entities = [s for s, t in types.items() if t in _ENTITIES]
    keys = {}
    for e in entities:
        k = key_of(e)
        if k not in keys:
            keys[k] = e
    edges = {}                 # (a, b, kind) -> [count, sign, reactions]

    def link(a, b, kind, sign=None, reaction=None, directed=True):
        ka, kb = key_of(a), key_of(b)
        if ka not in keys or kb not in keys or ka == kb:
            return
        if not directed and str(kb) < str(ka):
            ka, kb = kb, ka               # one undirected edge per pair
        rec = edges.setdefault((ka, kb, kind), [0, set(), set(), directed])
        rec[0] += 1
        if sign:
            rec[1].add(sign)
        if reaction:
            rec[2].add(reaction)

    reaction_nodes = {}
    as_reactions = str(mode).lower() == "reactions"
    for s, t in types.items():
        rname = lit(s, "displayName", "standardName", "name") or re.split(r"[#/]", s[1] if s[0] == "iri" else str(s[1]))[-1]
        if t in _CONVERSIONS:
            left, right = refs(s, "left"), refs(s, "right")
            if as_reactions:
                reaction_nodes[s] = (rname, t)
            else:
                for a in left:
                    for b_ in right:
                        link(a, b_, "used-to-produce", reaction=rname)
        elif t == "TemplateReaction" and as_reactions:
            reaction_nodes[s] = (rname, t)
        elif t in _INTERACTIONS:
            ps = refs(s, "participant")
            if as_reactions:
                reaction_nodes[s] = (rname, t)
            else:
                for i in range(len(ps)):
                    for j in range(i + 1, len(ps)):
                        link(ps[i], ps[j], "interacts-with", reaction=rname, directed=False)
        elif t in _CONTROLS and not as_reactions:
            sign = (lit(s, "controlType") or "").lower() or None
            for c in refs(s, "controller"):
                for target in refs(s, "controlled"):
                    tt = types.get(target)
                    if tt in _CONVERSIONS:
                        tname = lit(target, "displayName", "standardName", "name")
                        # small molecules it makes; molecules on either side that change state
                        for p in refs(target, "right"):
                            small = types.get(p) == "SmallMolecule"
                            link(c, p, "controls-production-of" if small else "controls-state-change-of", sign, tname)
                        for p in refs(target, "left"):
                            if types.get(p) != "SmallMolecule":
                                link(c, p, "controls-state-change-of", sign, tname)
                    elif tt == "TemplateReaction":
                        for p in refs(target, "product"):
                            link(c, p, "controls-expression-of", sign, lit(target, "displayName", "name"))
        if t == "Complex":
            for m in dict.fromkeys(refs(s, "component")):
                link(m, s, "in-complex-with", directed=False)
    b = _Builder(g, NODE_BP, EDGE_BP)
    items = []
    for k, e in keys.items():
        items.append((k, name_of(e), (xref_of(k) or xref_of(e) or "").split(":")[-1]))
    if as_reactions:
        for r, (rname, t) in reaction_nodes.items():
            items.append((r, rname, re.split(r"[#/]", r[1] if r[0] == "iri" else str(r[1]))[-1]))
    names = b.unique_names(items)
    for k, e in keys.items():
        n = b.node(k, names[k], kind=types.get(e), xref=xref_of(k) or xref_of(e),
                   uri=e[1] if e[0] == "iri" else None)
        n.label = name_of(e)
        if types.get(e) == "Complex":
            n.style = 3
        elif types.get(e) == "SmallMolecule":
            n.color = "orange"
    ne = 0
    if as_reactions:
        for r, (rname, t) in reaction_nodes.items():
            n = b.node(r, names[r], kind=t, uri=r[1] if r[0] == "iri" else None)
            n.label = rname
            n.style, n.width, n.height, n.color = 1, 7.0, 7.0, "gray"

        def rlink(a, r, role, reverse=False, sign=None):
            nonlocal ne
            ka = key_of(a)
            if ka not in b.nodes:
                return
            if reverse:
                b.edge(r, ka, True, kind=role, reaction=reaction_nodes[r][0], count=1)
            else:
                b.edge(ka, r, True, kind=role, sign=sign, reaction=reaction_nodes[r][0], count=1)
            ne += 1
        for r, (rname, t) in reaction_nodes.items():
            if t in _CONVERSIONS:
                for x in refs(r, "left"):
                    rlink(x, r, "left")
                for x in refs(r, "right"):
                    rlink(x, r, "right", reverse=True)
            elif t == "TemplateReaction":
                for x in refs(r, "template"):
                    rlink(x, r, "template")
                for x in refs(r, "product"):
                    rlink(x, r, "product", reverse=True)
            else:
                for x in refs(r, "participant"):
                    rlink(x, r, "participant")
        for s, t in types.items():
            if t in _CONTROLS:
                sign = (lit(s, "controlType") or "").lower() or None
                for c in refs(s, "controller"):
                    for target in refs(s, "controlled"):
                        if target in reaction_nodes:
                            rlink(c, target, "controller", sign=sign)
    for (ka, kb, kind), (cnt, signs, rx, directed) in edges.items():
        if ka not in b.nodes or kb not in b.nodes:
            continue
        b.edge(ka, kb, directed, kind=kind, sign="|".join(sorted(signs)) or None, count=cnt,
               reaction="|".join(sorted(rx))[:500] or None)
        ne += 1
    b.scatter()
    return len(b.nodes), ne


# --------------------------------------------------------------------------
# KEGG KGML
# --------------------------------------------------------------------------

NODE_KGML = {"kind": STRING, "kegg": STRING, "entry": INT, "group": STRING, "link": STRING}
EDGE_KGML = {"kind": STRING, "subtype": STRING, "compound": STRING, "reaction": STRING, "enzyme": STRING,
             "reversible": BOOL}
_KGML_SHAPES = {"rectangle": 1, "circle": 2, "roundrectangle": 3}


def read_kgml(g, text):
    root = _parse_xml(text, "KGML")
    if _local(root.tag) != "pathway":
        raise GuessError("not KGML (the root element should be <pathway>)")
    entries = {}
    for e in _kids(root, "entry"):
        entries[_attr(e, "id")] = e
    if not entries:
        raise GuessError("the KGML file has no entries")
    b = _Builder(g, NODE_KGML, EDGE_KGML)
    labels, items = {}, []
    for eid, e in entries.items():
        gr = _kid(e, "graphics")
        label = (_attr(gr, "name") or "") if gr is not None else ""
        label = label.split(",")[0].strip().rstrip(".").strip() or (_attr(e, "name") or eid).split()[0]
        if label.startswith(("cpd:", "gl:", "dr:")):
            label = label.split(":", 1)[1]
        labels[eid] = label
        items.append((eid, label, eid))
    names = b.unique_names(items)
    group_of = {}
    for eid, e in entries.items():
        if _attr(e, "type") == "group":
            for c in _kids(e, "component"):
                group_of.setdefault(_attr(c, "id"), labels[eid] if labels[eid] != eid else f"group {eid}")
    for eid, e in entries.items():
        gr = _kid(e, "graphics")
        n = b.node(eid, names[eid], kind=_attr(e, "type"), kegg=_attr(e, "name"), entry=_num(eid, None, int),
                   group=group_of.get(eid), link=_attr(e, "link"))
        n.label = labels[eid]
        if gr is None:
            continue
        w, h = _num(_attr(gr, "width"), None), _num(_attr(gr, "height"), None)
        x, y = _num(_attr(gr, "x"), None), _num(_attr(gr, "y"), None)
        if x is None and _attr(gr, "coords"):
            pts = [_num(v, 0.0) for v in _attr(gr, "coords").split(",")]
            if len(pts) >= 4:
                x, y = (pts[0] + pts[-2]) / 2, (pts[1] + pts[-1]) / 2
                w = h = 4.0
        if x is not None and y is not None:
            w, h = w or 10.0, h or 10.0
            n.width, n.height = w, h
            n.x, n.y = x - w / 2, y - h / 2
            b.positions = True
        n.style = _KGML_SHAPES.get(_attr(gr, "type"), 1)
        if _hex(_attr(gr, "bgcolor")):
            n.color = _hex(_attr(gr, "bgcolor"))
        if _hex(_attr(gr, "fgcolor")):
            n.strokecolor = _hex(_attr(gr, "fgcolor"))
        if n.style != 2:
            n.labelpos = "inside"
            n.labelvisible = True
            n.labelcolor = "black"
    # a group (complex) has no box of its own: a small dot under its members
    for eid, e in entries.items():
        if _attr(e, "type") != "group":
            continue
        ms = [b.nodes[_attr(c, "id")] for c in _kids(e, "component") if _attr(c, "id") in b.nodes]
        if ms:
            n = b.nodes[eid]
            x0 = min(float(m.x) for m in ms)
            x1 = max(float(m.x) + float(m.width) for m in ms)
            y1 = max(float(m.y) + float(m.height) for m in ms)
            n.x, n.y, n.width, n.height = (x0 + x1) / 2 - 4, y1 + 3, 8.0, 8.0
            n.style, n.color, n.labelvisible = 2, "lightgray", False
    ne = 0
    for r in _kids(root, "relation"):
        a, c = _attr(r, "entry1"), _attr(r, "entry2")
        if a not in b.nodes or c not in b.nodes:
            continue
        subs = _kids(r, "subtype")
        compound = [labels.get(_attr(s, "value"), _attr(s, "value")) for s in subs if _attr(s, "name") == "compound"]
        b.edge(a, c, True, kind=_attr(r, "type"),
               subtype="|".join(_attr(s, "name") for s in subs if _attr(s, "name") != "compound") or None,
               compound="|".join(compound) or None)
        ne += 1
    enzymes = {}
    for eid, e in entries.items():
        for rn in (_attr(e, "reaction") or "").split():
            enzymes.setdefault(rn, []).append(labels[eid])
    for rx in _kids(root, "reaction"):
        rname = _attr(rx, "name") or ""
        rev = _attr(rx, "type") == "reversible"
        subs = [_attr(s, "id") for s in _kids(rx, "substrate")]
        prods = [_attr(p, "id") for p in _kids(rx, "product")]
        enz = "|".join(dict.fromkeys(x for rn in rname.split() for x in enzymes.get(rn, []))) or None
        for s in subs:
            for p in prods:
                if s in b.nodes and p in b.nodes:
                    b.edge(s, p, True, kind="reaction", reaction=rname, enzyme=enz, reversible=rev)
                    ne += 1
    b.scatter()
    return len(b.nodes), ne


# --------------------------------------------------------------------------
# WikiPathways GPML
# --------------------------------------------------------------------------

NODE_GPML = {"kind": STRING, "xref_db": STRING, "xref_id": STRING, "graphid": STRING, "group": STRING}
EDGE_GPML = {"arrow": STRING, "kind": STRING, "graphid": STRING}
_GPML_SHAPES = {"rectangle": 1, "oval": 2, "ellipse": 2, "roundedrectangle": 3, "roundrectangle": 3}


def read_gpml(g, text):
    root = _parse_xml(text, "GPML")
    if _local(root.tag) != "Pathway":
        raise GuessError("not GPML (the root element should be <Pathway>)")
    new = "2021" in root.tag or _kid(root, "DataNodes") is not None

    def nodes_iter(name, plural):
        if new:
            return _kids(_kid(root, plural), name)
        return _kids(root, name)

    datanodes = nodes_iter("DataNode", "DataNodes")
    interactions = nodes_iter("Interaction", "Interactions")
    groups = nodes_iter("Group", "Groups")
    b = _Builder(g, NODE_GPML, EDGE_GPML)
    gid = (lambda el: _attr(el, "elementId")) if new else (lambda el: _attr(el, "GraphId"))
    group_label = {}
    for grp in groups:
        key = gid(grp) or _attr(grp, "GroupId")
        lab = _attr(grp, "textLabel") or _attr(grp, "TextLabel") or _attr(grp, "type") or _attr(grp, "Style") or "group"
        for k in {gid(grp), _attr(grp, "GroupId")} - {None}:
            group_label[k] = lab if lab != "None" else "group"
    members = {}
    items, info = [], {}
    for i, dn in enumerate(datanodes):
        key = gid(dn) or f"dn{i}"
        label = (_attr(dn, "textLabel") or _attr(dn, "TextLabel") or key).replace("\n", " ").strip()
        gr = _kid(dn, "Graphics")
        xr = _kid(dn, "Xref")
        info[key] = (dn, gr, xr, label)
        items.append((key, label, (_attr(xr, "identifier") or _attr(xr, "ID") or key) if xr is not None else key))
        gref = _attr(dn, "groupRef") or _attr(dn, "GroupRef")
        if gref:
            members.setdefault(gref, []).append(key)
    # groups that interactions point at become nodes too
    pointed = set()
    for it in interactions:
        for pt in _points(it, new):
            r = _attr(pt, "elementRef") or _attr(pt, "GraphRef")
            if r:
                pointed.add(r)
    for grp in groups:
        keys = {gid(grp), _attr(grp, "GroupId")} - {None}
        if keys & pointed:
            key = gid(grp) or _attr(grp, "GroupId")
            items.append((key, group_label.get(key, "group"), key))
            info[key] = (grp, None, None, group_label.get(key, "group"))
            for k in keys:
                members.setdefault(key, []).extend(members.get(k, []) if k != key else [])
    names = b.unique_names(items)
    for key, (el, gr, xr, label) in info.items():
        n = b.node(key, names[key], kind=_attr(el, "type") or _attr(el, "Type") or ("group" if gr is None else None),
                   xref_db=(_attr(xr, "dataSource") or _attr(xr, "Database")) if xr is not None else None,
                   xref_id=(_attr(xr, "identifier") or _attr(xr, "ID")) if xr is not None else None,
                   graphid=key, group=group_label.get(_attr(el, "groupRef") or _attr(el, "GroupRef") or ""))
        n.label = label
        if gr is None:
            continue
        cx = _num(_attr(gr, "centerX") or _attr(gr, "CenterX"))
        cy = _num(_attr(gr, "centerY") or _attr(gr, "CenterY"))
        w = _num(_attr(gr, "width") or _attr(gr, "Width"), 60.0)
        h = _num(_attr(gr, "height") or _attr(gr, "Height"), 20.0)
        if cx is not None and cy is not None:
            n.width, n.height = w, h
            n.x, n.y = cx - w / 2, cy - h / 2
            b.positions = True
        shape = (_attr(gr, "shapeType") or _attr(gr, "ShapeType") or "Rectangle").lower()
        n.style = _GPML_SHAPES.get(shape, 1)
        fill = _hex(_attr(gr, "fillColor") or _attr(gr, "FillColor"))
        n.color = fill or "white"
        border = _hex(_attr(gr, "borderColor") or _attr(gr, "Color") or _attr(gr, "textColor"))
        if border:
            n.strokecolor = border
            n.labelcolor = border
        else:
            n.labelcolor = "black"
        n.labelpos = "inside"
        n.labelvisible = True
    # group nodes: the box around their members
    for key, (el, gr, xr, label) in info.items():
        if gr is not None:
            continue
        ms = [b.nodes[m] for m in members.get(key, []) if m in b.nodes and info[m][1] is not None]
        if ms:
            x0 = min(float(m.x) for m in ms)
            y0 = min(float(m.y) for m in ms)
            x1 = max(float(m.x) + float(m.width) for m in ms)
            y1 = max(float(m.y) + float(m.height) for m in ms)
            n = b.nodes[key]
            n.x, n.y, n.width, n.height = x0 + (x1 - x0) / 2 - 4, y1 + 4, 8.0, 8.0
            n.style, n.color = 2, "lightgray"
    # anchors: a point on an interaction where another interaction ends (a
    # catalysis on a conversion). Each becomes a small node, and the
    # interaction it sits on runs source -> anchor -> target.
    anchors = {}
    lines = []
    for it in interactions:
        pts = _points(it, new)
        if len(pts) < 2:
            continue
        coords = [(_num(_attr(p, "x") or _attr(p, "X"), 0.0), _num(_attr(p, "y") or _attr(p, "Y"), 0.0)) for p in pts]
        src = _attr(pts[0], "elementRef") or _attr(pts[0], "GraphRef")
        dst = _attr(pts[-1], "elementRef") or _attr(pts[-1], "GraphRef")
        arrow = _attr(pts[-1], "arrowHead") or _attr(pts[-1], "ArrowHead") or _attr(pts[0], "arrowHead") \
            or _attr(pts[0], "ArrowHead")
        if not (_attr(pts[-1], "arrowHead") or _attr(pts[-1], "ArrowHead")) and arrow:
            src, dst = dst, src                       # the arrow was on the first point
            coords = coords[::-1]
        an = []
        gr = _kid(it, "Graphics")
        for a in (_kids(gr, "Anchor") if gr is not None else []) + _kids(_kid(it, "Anchors"), "Anchor"):
            pos = _num(_attr(a, "position") or _attr(a, "Position"), 0.5)
            ax = coords[0][0] + (coords[-1][0] - coords[0][0]) * pos
            ay = coords[0][1] + (coords[-1][1] - coords[0][1]) * pos
            aid = gid(a)
            if aid:
                anchors[aid] = (ax, ay)
                an.append((pos, aid))
        lines.append((it, src, dst, arrow, coords, sorted(an)))
    for aid, (ax, ay) in anchors.items():
        n = b.node(aid, b.unique_names([(aid, f"anchor {aid}", aid)])[aid], kind="anchor", graphid=aid)
        n.x, n.y, n.width, n.height = ax - 2, ay - 2, 4.0, 4.0
        n.style, n.color, n.label = 2, "gray", ""

    def endpoint(ref, xy, it):
        if ref and ref in b.nodes:
            return ref
        key = f"pt:{gid(it) or id(it)}:{xy}"
        if key not in b.nodes:
            n = b.node(key, b.unique_names([(key, f"point {len(b.nodes)}", key)])[key], kind="point")
            n.x, n.y, n.width, n.height = xy[0] - 2, xy[1] - 2, 4.0, 4.0
            n.style, n.color, n.label = 2, "gray", ""
        return key

    ne = 0
    for it, src, dst, arrow, coords, an in lines:
        a = endpoint(src, coords[0], it)
        z = endpoint(dst, coords[-1], it)
        chain = [a] + [aid for _p, aid in an] + [z]
        for i in range(len(chain) - 1):
            last = i == len(chain) - 2
            directed = bool(arrow and arrow != "Line") and last
            b.edge(chain[i], chain[i + 1], directed, arrow=(arrow if last else None), graphid=gid(it),
                   kind=_attr(it, "type"))
            ne += 1
    if not b.positions:
        b.scatter()
    return len(b.nodes), ne


def _points(it, new):
    if new:
        return _kids(_kid(it, "Waypoints"), "Point")
    gr = _kid(it, "Graphics")
    return _kids(gr, "Point") if gr is not None else []


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

# ---- protein structures (PDB, mmCIF) -> residue contact networks ------------------------------
AA3 = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E", "GLY": "G",
       "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P", "SER": "S",
       "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V", "SEC": "U", "PYL": "O", "MSE": "M"}


class _Residues:
    def __init__(self, residues, structure, cutoff):
        self.residues, self.structure, self.cutoff = residues, structure, cutoff

    def build(self, g):
        import math
        res = self.residues
        if not res:
            raise GuessError("no amino-acid alpha carbons found in this structure")
        chains = {r[0] for r in res}
        names = []
        for ch, seq, icode, rname, xyz in res:
            nm = f"{rname}{seq}{icode or ''}" + (f"_{ch}" if len(chains) > 1 else "")
            names.append(nm)
        # place by the two main directions of the alpha carbons (PCA by power iteration)
        n = len(res)
        cx = [sum(r[4][k] for r in res) / n for k in range(3)]
        pts = [[r[4][k] - cx[k] for k in range(3)] for r in res]
        cov = [[sum(p[a] * p[b] for p in pts) for b in range(3)] for a in range(3)]

        def top(m, avoid=None):
            v = [1.0, 0.7, 0.3]
            for _ in range(100):
                w = [sum(m[a][b] * v[b] for b in range(3)) for a in range(3)]
                if avoid is not None:
                    d = sum(w[k] * avoid[k] for k in range(3))
                    w = [w[k] - d * avoid[k] for k in range(3)]
                s = math.sqrt(sum(t * t for t in w)) or 1.0
                v = [t / s for t in w]
            return v
        e1 = top(cov)
        e2 = top(cov, e1)
        for k in ("residue", "aa", "chain", "structure"):
            g.addNodeField(k, STRING, "")
        g.addNodeField("seq", INT, 0)
        for k in ("x3", "y3", "z3"):
            g.addNodeField(k, DOUBLE, 0.0)
        g.addEdgeField("kind", STRING, "")
        g.addEdgeField("distance", DOUBLE, 0.0)
        nodes = []
        for nm, (ch, seq, icode, rname, xyz), p in zip(names, res, pts):
            x = 20 * sum(p[k] * e1[k] for k in range(3))
            y = 20 * sum(p[k] * e2[k] for k in range(3))
            nodes.append(g.addNode(nm, residue=rname, aa=AA3.get(rname, "X"), chain=ch, seq=seq,
                                   structure=self.structure.get((ch, seq), "coil"),
                                   x3=xyz[0], y3=xyz[1], z3=xyz[2], x=x, y=y, label=nm))
        ne = 0
        cut2 = self.cutoff * self.cutoff
        for i in range(n):
            for j in range(i + 1, n):
                a, b = res[i], res[j]
                d2 = sum((a[4][k] - b[4][k]) ** 2 for k in range(3))
                along = a[0] == b[0] and j == i + 1
                if along or d2 < cut2:
                    g.addEdge(nodes[i], nodes[j], kind="chain" if along else "contact", distance=round(math.sqrt(d2), 2))
                    ne += 1
        return n, ne


def read_pdb(text, cutoff=8.0, chain=None):
    """Alpha carbons (first model, first altloc) and HELIX/SHEET ranges from PDB or mmCIF text."""
    residues, seen, structure = [], set(), {}
    if text.lstrip().startswith("data_") or "_atom_site." in text[:200000]:
        cols, rows, in_loop = [], [], False
        for line in text.splitlines():
            if line.startswith("_atom_site."):
                cols.append(line.split(".", 1)[1].strip())
                in_loop = True
                continue
            if in_loop and cols and (line.startswith(("ATOM", "HETATM"))):
                rows.append(line.split())
            elif in_loop and cols and rows and (line.startswith(("#", "loop_", "_"))):
                break
        ix = {c: i for i, c in enumerate(cols)}
        for r in rows:
            try:
                if r[ix["label_atom_id"]].strip('"') != "CA" or r[ix.get("pdbx_PDB_model_num", 0)] not in ("1",):
                    continue
                rname = r[ix["label_comp_id"]]
                ch = r[ix.get("auth_asym_id", ix["label_asym_id"])]
                seq = int(r[ix.get("auth_seq_id", ix["label_seq_id"])])
                xyz = (float(r[ix["Cartn_x"]]), float(r[ix["Cartn_y"]]), float(r[ix["Cartn_z"]]))
            except (KeyError, ValueError, IndexError):
                continue
            if rname in AA3 and (chain is None or ch == chain) and (ch, seq) not in seen:
                seen.add((ch, seq))
                residues.append((ch, seq, "", rname, xyz))
        return _Residues(residues, structure, cutoff)
    for line in text.splitlines():
        rec = line[:6]
        if rec == "ENDMDL":
            break
        if rec == "HELIX ":
            try:
                ch, a, b = line[19], int(line[21:25]), int(line[33:37])
                for k in range(a, b + 1):
                    structure[(ch, k)] = "helix"
            except ValueError:
                pass
        elif rec == "SHEET ":
            try:
                ch, a, b = line[21], int(line[22:26]), int(line[33:37])
                for k in range(a, b + 1):
                    structure[(ch, k)] = "strand"
            except ValueError:
                pass
        elif rec in ("ATOM  ", "HETATM") and line[12:16].strip() == "CA":
            rname, ch, alt = line[17:20].strip(), line[21], line[16]
            try:
                seq = int(line[22:26])
                xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            except ValueError:
                continue
            icode = line[26].strip()
            key = (ch, seq, icode)
            if rname in AA3 and alt in (" ", "A") and key not in seen and (chain is None or ch == chain):
                seen.add(key)
                residues.append((ch, seq, icode, rname, xyz))
    return _Residues(residues, structure, cutoff)


def install(session):
    g = session.graph

    def load(filename, reader, label, **kw):
        if not os.path.exists(str(filename)):
            raise GuessError(f"no file named {filename!r}")
        with open(filename, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        g.clear()
        result = reader(g, text, **kw)
        session.scene()
        nn, ne = result
        print(f"loaded {nn} nodes, {ne} edges from {os.path.basename(str(filename))} ({label})")

    def mi(reader):
        def read(gr, text, merge=True):
            return reader(text, merge).build(gr)
        return read

    def makeFromMITAB(filename, merge=True):
        """makeFromMITAB("interactions.txt") opens molecular interactions in
        PSI-MI TAB (MITAB 2.5, 2.6 or 2.7), as IntAct, BioGRID, MINT and the
        IMEx databases export them. Each interactor becomes a node named by
        its gene name when the file gives one (else its short label or
        identifier), with `ident`, `taxid`, `species`, `kind` and `aliases`.
        Each pair becomes an edge with the detection `method`, `kind`
        (interaction type), `pubmed`, `author`, `sourcedb`, `interaction` ids
        and IntAct's `miscore`; repeated evidence for a pair is merged into
        one edge with an `evidence` count (merge=false keeps one edge per
        line). An interactor paired with itself is a self-loop."""
        load(filename, mi(read_mitab), "PSI-MI TAB", merge=bool(merge))

    def makeFromPSIMI(filename, merge=True):
        """makeFromPSIMI("interactions.xml") opens molecular interactions in
        PSI-MI XML (2.5 or 3.0), with the same nodes and fields as
        makeFromMITAB. An interaction with more than two participants is
        expanded into pairs: from the bait to each prey when a bait is named
        (spoke expansion), otherwise between every pair (matrix expansion);
        the edge field `expansion` says which."""
        load(filename, mi(read_psimi), "PSI-MI XML", merge=bool(merge))

    def makeFromSBML(filename, reactions="nodes"):
        """makeFromSBML("model.xml") opens a systems biology model (SBML level
        2 or 3). Species become nodes (`compartment`, `initial` amount or
        concentration, `sbo`); each reaction becomes a small grey node, with
        directed edges from its reactants and modifiers and to its products
        (`role`, `stoichiometry`). reactions="edges" draws each reaction as
        edges from reactants (and modifiers) to products instead. A species
        name used in two compartments gets the compartment added, as
        "ATP [cytosol]". Positions from the SBML layout package are kept."""
        r = str(reactions).lower()
        if r not in ("nodes", "edges"):
            raise GuessError('makeFromSBML reactions= is "nodes" or "edges"')
        load(filename, read_sbml, "SBML", reactions=r)

    def makeFromBioPAX(filename, mode="sif"):
        """makeFromBioPAX("pathway.owl") opens a BioPAX level 3 pathway (as
        Reactome, Pathway Commons and WikiPathways export them) as a simple
        network of molecules, after Pathway Commons' SIF rules: a reaction
        links what it uses to what it produces ("used-to-produce"); the
        controller of a reaction (a catalysis or other control) links to what
        it changes ("controls-state-change-of", or "controls-production-of"
        for small molecules) with the `sign` (activation, inhibition); the
        regulator of a gene's expression links to its product
        ("controls-expression-of"); molecular interactions link their
        participants ("interacts-with"); and each complex is a node linked
        to its components ("in-complex-with"). Forms of the same protein
        (states, places) are one node. mode="reactions" keeps the reactions
        as small nodes instead, with left, right, controller and participant
        edges."""
        m = str(mode).lower()
        if m not in ("sif", "reactions"):
            raise GuessError('makeFromBioPAX mode= is "sif" or "reactions"')
        load(filename, read_biopax, "BioPAX", mode=m)

    def makeFromKGML(filename):
        """makeFromKGML("hsa04115.xml") opens a KEGG pathway map (KGML), drawn
        as on KEGG: genes, compounds and linked maps at their positions, in
        their colours and shapes, labelled with the first name. Relations
        become directed edges with `kind` (PPrel, GErel, ECrel, PCrel) and
        `subtype` (activation, inhibition, phosphorylation, …); reactions
        become edges from substrates to products with the `enzyme`. Entries
        in a group (a complex) have the group in `group`."""
        load(filename, read_kgml, "KGML")

    def makeFromGPML(filename):
        """makeFromGPML("WP707.gpml") opens a WikiPathways pathway (GPML 2013a
        or 2021), drawn as on WikiPathways: data nodes at their positions,
        with their colours, shapes and database references (`xref_db`,
        `xref_id`). Interactions become edges with their `arrow`
        (mim-conversion, mim-catalysis, mim-inhibition, Arrow, TBar, …). An
        interaction that ends on another one (a catalysis on a conversion)
        meets it at a small anchor node; groups that interactions point at
        become nodes, and members have the group in `group`."""
        load(filename, read_gpml, "GPML")

    def makeFromPDB(source, cutoff=8.0, chain=None):
        """makeFromPDB("1ubq") or makeFromPDB("protein.pdb") turns a protein
        structure into a residue contact network: one node per amino acid
        (named like LYS48, with `residue`, `aa` (one letter), `seq`, `chain`,
        `structure` = helix, strand or coil from the file's HELIX/SHEET
        records, and its alpha-carbon's 3D position `x3`, `y3`, `z3`). Edges
        join residues next to each other along the chain (kind "chain") and
        residues whose alpha carbons are closer than `cutoff` angstroms
        (kind "contact", with `distance`). A four-character PDB id is
        downloaded from RCSB (files.rcsb.org); .pdb and .cif (mmCIF) files
        are read. chain="A" keeps one chain. Nodes are placed by the
        structure's two main directions, so the picture looks like the
        folded protein seen from its widest side."""
        src = str(source)
        if os.path.exists(src):
            with open(src, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            name = os.path.basename(src)
        elif re.fullmatch(r"[0-9][A-Za-z0-9]{3}", src):
            from .connectors import http
            text = http(f"https://files.rcsb.org/download/{src.upper()}.pdb")
            name = src.upper()
        else:
            raise GuessError(f"no file named {src!r} (or give a four-character PDB id such as '1ubq')")
        g.clear()
        nn, ne = read_pdb(text, float(cutoff), chain).build(g)
        session.scene()
        print(f"loaded {nn} residues, {ne} edges from {name} (contacts within {float(cutoff):g} Å)")

    for fn in (makeFromMITAB, makeFromPSIMI, makeFromSBML, makeFromBioPAX, makeFromKGML, makeFromGPML, makeFromPDB):
        session.register_command(fn.__name__, fn)


__all__ = ["install", "read_pdb", "read_mitab", "read_psimi", "read_sbml", "read_biopax", "read_kgml", "read_gpml"]


# --------------------------------------------------------------------------
# recognising a download (makeFromURL)
# --------------------------------------------------------------------------

LOADERS = [(".mitab", "makeFromMITAB"), (".psimitab", "makeFromMITAB"), (".mif", "makeFromPSIMI"),
           (".psi", "makeFromPSIMI"), (".sbml", "makeFromSBML"), (".kgml", "makeFromKGML"),
           (".gpml", "makeFromGPML"), (".biopax", "makeFromBioPAX")]

_MITAB_ROW = re.compile(r"^[^\t:]+:[^\t]+(\t[^\t]*){14,}$")


def sniff(text, ext):
    """The extension a downloaded file should be opened as, when its content
    shows one of these formats (whatever the URL said), or None. Files named
    as another XML or table format (.gexf, .graphml, .csv, …) are left alone,
    except that .xml, .owl and .rdf are looked into."""
    head = text.lstrip()[:3000]
    low = head.lower()
    if ext in (".owl", ".rdf", ".xml", "", ".") and "biopax-level3.owl" in text[:20000]:
        return ".biopax"
    named = (".gexf", ".graphml", ".gml", ".rdf", ".owl", ".ttl", ".nt", ".n3", ".csv", ".tsv", ".gdf",
             ".net", ".paj", ".dot", ".gv", ".dl", ".guess", ".py")
    if ext in named:
        return None
    if low.startswith("<"):
        if "<sbml" in low:
            return ".sbml"
        if "<entryset" in low:
            return ".mif"
        if re.search(r"<pathway\b", low) and ("pathvisio" in low or "genmapp" in low):
            return ".gpml"
        if re.search(r"<pathway\b", low) and ("kgml" in low or re.search(r'<pathway[^>]*\borg="', low)):
            return ".kgml"
        return None
    lines = [ln for ln in text.splitlines()[:5] if ln.strip() and not ln.startswith("#")]
    if lines and _MITAB_ROW.match(lines[0]):
        return ".mitab"
    return None
