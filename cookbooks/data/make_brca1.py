"""brca1-intact.gdf: BRCA1's interaction neighbourhood from IntAct (EMBL-EBI,
CC BY 4.0), taken from the Cytoscape export that LUMINA ships as demo data
(github.com/intact-portal/sub-structure-cyto-layout, demo/data/BRCA1.cyjs).

Repeated evidence for the same pair is merged into one edge (IntAct's summary
edges); `miscore` is IntAct's MI score for the pair, `evidence` the number of
summarised interactions.

    python make_brca1.py path/to/BRCA1.cyjs
"""
import json
import sys


def main(src):
    d = json.load(open(src))
    e = d.get("elements", d)
    nodes = {}
    for n in e["nodes"]:
        x = n["data"]
        if x.get("isParent"):
            continue
        nodes[x["id"]] = (x.get("name") or x["id"], x.get("IntAct_Preferred_Id", ""), x.get("IntAct_Species", ""),
                          x.get("IntAct_Type", ""), x.get("IntAct_Description", ""))
    pairs = {}
    for x in (y["data"] for y in e["edges"]):
        s, t = x["source"], x["target"]
        if s not in nodes or t not in nodes or s == t or not x.get("IntAct_Summary_Is_summary", True):
            continue
        key = tuple(sorted((s, t)))
        score = float(x.get("IntAct_MI_Score") or 0)
        ev = int(x.get("IntAct_Summary_Summarized_edges") or 1)
        old = pairs.get(key)
        pairs[key] = (max(score, old[0]), old[1] + ev) if old else (score, ev)
    # a gene name used by two entries (isoforms, say) gets the UniProt id added
    count = {}
    for name, *_rest in nodes.values():
        count[name] = count.get(name, 0) + 1
    names = {i: (name if count[name] == 1 else f"{name}_{uni or i}").replace("-", "_")
             for i, (name, uni, *_rest) in nodes.items()}

    def q(v):
        v = str(v).replace("'", "")
        return f"'{v}'" if ("," in v or " " in v) else v
    out = ["nodedef> name VARCHAR,uniprot VARCHAR,species VARCHAR,kind VARCHAR,description VARCHAR"]
    for i, (name, uni, sp, kind, desc) in nodes.items():
        out.append(",".join(q(v) for v in (names[i], uni, sp, kind, desc)))
    out.append("edgedef> node1 VARCHAR,node2 VARCHAR,miscore DOUBLE,evidence INT")
    for (a, b), (score, ev) in sorted(pairs.items()):
        out.append(f"{q(names[a])},{q(names[b])},{score:.3f},{ev}")
    open("brca1-intact.gdf", "w").write("\n".join(out) + "\n")
    print(len(nodes), "nodes,", len(pairs), "edges")


if __name__ == "__main__":
    main(sys.argv[1])
