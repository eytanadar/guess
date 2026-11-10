"""Fetch the Biology cookbook's yeast data (needs the network; re-run to refresh).

    cd py && .venv/bin/python ../cookbooks/data/make_biology.py

yeast-modules.gdf   STRING (string-db.org, CC BY 4.0) interactions with combined
                    score >= 0.7 among genes from seven well-known complexes and
                    pathways; `module` says which list each gene was taken from.
yeast-go-slim.csv   SGD's GO-slim mapping (yeastgenome.org, CC BY 4.0) for those
                    genes: one row per gene and term.
"""
import csv
import io
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "py"))

MODULES = {
    "proteasome": "RPT1 RPT2 RPT3 RPT4 RPT5 RPT6 RPN1 RPN2 RPN3 RPN5 RPN6 RPN7 RPN8 RPN9 RPN10 RPN11 RPN12 "
                  "PRE1 PRE2 PRE3 PRE4 PRE5 PRE6 PRE7 PRE8 PRE9 PRE10 PUP1 PUP2 PUP3 SCL1",
    "RNA polymerase II": "RPO21 RPB2 RPB3 RPB4 RPB5 RPB7 RPB8 RPB9 RPB10 RPB11 RPC10",
    "pheromone response": "STE2 STE3 GPA1 STE4 STE18 STE5 STE20 STE11 STE7 FUS3 KSS1 STE12 FAR1 DIG1 DIG2 "
                          "CDC42 BEM1 SST2 MSG5 FUS1",
    "cell cycle": "CDC28 CLN1 CLN2 CLN3 CLB1 CLB2 CLB3 CLB4 CLB5 CLB6 SIC1 CDC20 CDH1 CDC14 SWI4 SWI6 "
                  "MBP1 WHI5 CDC6 CDC53 CDC4 SKP1 CDC34 APC1 CDC16 CDC23 CDC27",
    "TCA cycle": "CIT1 CIT2 ACO1 IDH1 IDH2 KGD1 KGD2 LSC1 LSC2 SDH1 SDH2 SDH3 SDH4 FUM1 MDH1 LPD1",
    "small ribosomal subunit": "RPS0A RPS1A RPS2 RPS3 RPS5 RPS6A RPS8A RPS9A RPS11A RPS13 RPS14A RPS15 "
                               "RPS16A RPS17A RPS18A RPS19A RPS20 RPS24A RPS31",
    "DNA repair": "MSH2 MSH3 MSH6 MLH1 PMS1 RAD51 RAD52 RAD54 RAD55 RAD57",
}
API = "https://string-db.org/api/tsv"
UA = {"User-Agent": "guess-cookbook-data/1.0"}


def get(url, data=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def tsv(text):
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def main():
    genes = {g: m for m, gs in MODULES.items() for g in gs.split()}
    ids = tsv(get(f"{API}/get_string_ids", {"identifiers": "\r".join(genes), "species": 4932, "limit": 1,
                                            "echo_query": 1}))
    by_query = {r["queryItem"].upper(): r for r in ids}
    missing = [g for g in genes if g not in by_query]
    if missing:
        print("not found in STRING:", " ".join(missing))
    sid = {by_query[g]["stringId"]: g for g in genes if g in by_query}
    edges = tsv(get(f"{API}/network", {"identifiers": "\r".join(sid), "species": 4932,
                                       "required_score": 700}))
    from guess import Session
    s = Session(lambda m: print(m.get("text", "")) if m.get("type") == "error" else None)
    g = s.graph
    s.run("addNodeField('module', VARCHAR, None); addNodeField('orf', VARCHAR, None); "
          "addNodeField('description', VARCHAR, None)")
    for st, name in sid.items():
        n = g.addNode(name)
        n.module = genes[name]
        n.orf = st.split(".", 1)[1]
        n.label = name
        n.description = by_query[name]["annotation"].split(";")[0][:160]
    for f in ("score", "experiments", "databases", "textmining", "coexpression"):
        g.addEdgeField(f, "DOUBLE", 0.0)
    seen = set()
    for e in edges:
        a, b = sid.get(e["stringId_A"]), sid.get(e["stringId_B"])
        if not a or not b or (a, b) in seen or (b, a) in seen:
            continue
        seen.add((a, b))
        g.addUndirectedEdge(a, b, score=float(e["score"]), weight=float(e["score"]),
                            experiments=float(e["escore"]), databases=float(e["dscore"]),
                            textmining=float(e["tscore"]), coexpression=float(e["ascore"]))
    s.run("frLayout()")
    out = HERE / "yeast-modules.gdf"
    assert s.run(f"exportGDF({str(out)!r})")
    print(f"  {out.name}: {len(g.nodes)} genes, {len(g.edges)} interactions")

    slim = get("https://downloads.yeastgenome.org/curation/literature/go_slim_mapping.tab")
    orfs = {n.orf: n.name for n in g.nodes}
    rows = set()
    for line in slim.splitlines():
        f = line.split("\t")
        if len(f) >= 6 and f[0] in orfs and f[4] not in ("other", "") and f[3] in ("P", "C", "F"):
            aspect = {"P": "process", "C": "component", "F": "function"}[f[3]]
            rows.add((orfs[f[0]], aspect, f[4]))
    with open(HERE / "yeast-go-slim.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["gene", "aspect", "term"])
        w.writerows(sorted(rows))
    print(f"  yeast-go-slim.csv: {len(rows)} gene-term rows")


if __name__ == "__main__":
    main()
