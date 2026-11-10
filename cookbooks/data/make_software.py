"""Snapshots of code import graphs for the Software cookbook (reproducible
numbers: the live packages change between versions).

    cd py && .venv/bin/python ../cookbooks/data/make_software.py

networkx-imports.gdf   the networkx package (BSD licence) as installed here
guess-imports.gdf      GUESS's own Python package, at the time of the snapshot
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "py"))


def main():
    import networkx
    from guess import Session
    s = Session(lambda m: print(m.get("text", "")) if m.get("type") == "error" else None)
    for target, out in (("networkx", "networkx-imports.gdf"), (str(ROOT / "py" / "guess"), "guess-imports.gdf")):
        assert s.run(f"makeFromImports({target!r})")
        assert s.run(f"exportGDF({str(HERE / out)!r})")
        print(f"  {out}: {len(s.graph.nodes)} modules, {len(s.graph.edges)} imports")
    print(f"  (networkx {networkx.__version__})")


if __name__ == "__main__":
    main()
