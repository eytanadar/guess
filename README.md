# GUESS for the web

A browser reimplementation of [GUESS](http://www.cond.org/chi2006-final2.pdf) (Adar, CHI 2006):
graph exploration driven by **Gython**, Python 3 extended with graph operators.
Everything runs client-side; Python runs in a Web Worker via Pyodide.
Documentation: [user guide](docs/USER_GUIDE.md), [API reference](docs/API.md),
[architecture](docs/ARCHITECTURE.md), [developer guide](docs/DEVELOPER.md),
[deployment](docs/DEPLOY.md). [PLAN.md](PLAN.md) has the design log and roadmap.

## Manual

The GUESS manual (tutorial, data formats, queries, layouts, analysis, states,
gestures, interface building, deployment, and the full command reference):

- **Download:** [PDF](https://raw.githubusercontent.com/eytanadar/guess/main/docs/manual/build/GUESS-manual.pdf) ·
  [EPUB](https://raw.githubusercontent.com/eytanadar/guess/main/docs/manual/build/GUESS-manual.epub) ·
  [Word](https://raw.githubusercontent.com/eytanadar/guess/main/docs/manual/build/GUESS-manual.docx) ·
  [web page](https://raw.githubusercontent.com/eytanadar/guess/main/docs/manual/build/GUESS-manual.html) (save it and open it in a browser)
- **Source:** [docs/manual/MANUAL.md](docs/manual/MANUAL.md) (readable here on GitHub)
- **Build it yourself:** `python3 docs/manual/build.py` writes all formats and an
  index page to `docs/manual/build/` (needs pandoc 3 and XeLaTeX; see
  [docs/manual/README.md](docs/manual/README.md)).

In a deployed copy of the app, **Help → Manual** opens the same manual.

## Run

```sh
cd web
npm install
npm run dev          # http://localhost:5173
```

The dev server sends COOP/COEP headers so the **Stop** button (and Esc / Ctrl-C
in the console) can interrupt running Python. Pyodide is loaded from jsDelivr,
so the first load needs network access.

### Apps

`exportApp("app.guess", "ui.py")` saves the graph plus a startup script. Opening
`/?load=app.guess&app=1` hides the console and runs the script — the
replacement for GUESS applets. Try the bundled example:
http://localhost:5173/?load=examples/demo.guess&app=1 (source:
`web/public/examples/demo-ui.py`).

Work is autosaved in the browser (IndexedDB) and restored on reload; **Save**
downloads a `.guess` session file you can reopen later.

## Tests

```sh
cd py
uv venv -p 3.14 .venv && uv pip install -p .venv -r requirements-dev.txt
.venv/bin/python -m pytest          # model, language, layouts, persistence

cd ../web
npm run typecheck
npm run test:e2e                    # Playwright, in your installed Chrome
```

CI (`.github/workflows/ci.yml`) runs both and, on `main`, deploys `web/dist`
to GitHub Pages.

## Deploying

```sh
cd web
npm run bundle                 # web/bundle/guess-web-<version>/ + .zip/.tar.gz
npm run bundle -- --offline    # also bundles Pyodide: no CDN needed at run time
```

Upload the folder's contents to any web server or static host (any sub-path).
Server configs for Apache (`.htaccess`, included), nginx, Caddy and
Netlify/Cloudflare (`_headers`, included) set the cross-origin-isolation
headers; without them `coi-serviceworker.js` adds them after one reload. See
[docs/DEPLOY.md](docs/DEPLOY.md).

## Demo video

`cd web && npm run demo` records a narrated demo (at most 5 minutes) from
`web/demo/script.json`; `npm run demo:script` has Claude rewrite that script
from the current docs, in the voice of the CHI paper. See
[web/demo/README.md](web/demo/README.md).

## Layout

- `py/guess/` — the Python package that runs inside Pyodide (compiler, model,
  commands). Pure Python; tested under CPython 3.14 (Pyodide's version).
- `web/` — Vite + TypeScript front end: PixiJS renderer, console, worker.
- `gdfs/` — `sample.gdf` (the built-in sample graph) and other GDF files.
- `guess-orig/` — the original Java/Jython GUESS distribution (reference only; not in git, not needed to build).

## Gython at a glance

```python
(freq > 10).color = blue           # queries return sets; setters broadcast
name like 'v1%'                    # SQL-style LIKE
(bob, alice) & (dept == 'IT')      # set algebra on node tuples
bob -> alice    bob <- alice       # directed edges
bob <-> alice   bob ? g.nodes      # undirected / any edges
colorize(dept); resizeLinear(totaldegree, 5, 30)
for grp in groupBy(dept): grp.color = randomColor()
center(dept == 'dept3')
gemLayout                          # commands work without parentheses
ss(1); circleLayout; morph(1, 2000) # save a state, change, animate back
for c in edgeBetweennessClusters(7): createConvexHull(c, randomColor(120))
```

Building interfaces:

```python
s = Slider(freq.min, freq.max, label="min freq")
def hideshow(val):
    (freq < val).visible = false
    (freq >= val).visible = true
s.onChange = hideshow                        # or s.mouseReleased, as in the paper
ui.dock(Panel("Edges", s, Button("Center", onClick=center)))
graphevents.clickNode = lambda n: center([n] + n.getNeighbors())
plotSizesPie(dept)                           # linked chart
startMovie(30, "run.webm"); gemLayout; stopMovie()
curvedEdges(); setEdgeColorMode("mixed")       # Gephi-style arcs and edge colours
```

Gephi-style analysis and layout:

```python
cl = louvainClusters(); colorize(modularity_class)   # communities, distinct colours
forceAtlas2Layout(linLog=true)                       # also scaling=, gravity=, preventOverlap=...
sizeBy(pagerank, 5, 40, "sqrt"); colorBy(closeness, yellow, red)
graphStats()                                         # diameter, path length, clustering, ...
showOnly(kCore(3)); showAll()                        # also egoNetwork, giantComponent, intraEdges
shortestPath(v1, v14).color = red; heatMap(v1)
labelOutlines(); hideOverlappingLabels(); noverlapLayout()
makeFromGEXF("graph.gexf"); exportGEXF("out.gexf"); makeFromCSV("edges.csv", "nodes.csv")
```

Statistics such as `pagerank`, `hub`, `authority`, `eigenvector`, `closeness`,
`harmonic`, `eccentricity`, `clustering`, `triangles`, `coreness`, `strength` and
`component` are node fields computed the first time you use them
(`recompute()` after editing the graph). In the toolbar, **Select** mode
highlights a clicked node's neighbourhood (click again or press Esc to clear);
**Path**, **Heat** and **Paint** turn clicks into `shortestPath`, `heatMap` and
`paint` commands using the colour beside them.

**Undo/Redo** (toolbar, Cmd/Ctrl+Z outside the code cell, or `undo()`/`redo()`)
step back through commands and node drags; undone cells are struck through.
`history()` lists everything run. Shift-drag box-selects, Alt-drag lassos, and
the selection is `sel` in the console. The theme button switches Auto/Light/Dark.

The code console sits to the right of the graph (below it on narrow screens; drag
the divider to resize). Write one or more lines in the working cell at the bottom
and press **Shift+Enter** (or Cmd/Ctrl+Enter) to run them; Enter just adds a line.
Tab completes (and accepts a suggestion), ↑/↓ on the first/last line walk the
history, Esc interrupts. Executed cells stack up above with their output: click
**Edit** (or double-click the code) to copy one back into the working cell,
**Run again** to re-run it, and its `[n]` to fold its output.

Hover output to highlight the matching nodes and edges. Right-click a node, an
edge, or console output for a context menu.

## Third-party components

GUESS runs Python in the browser with [Pyodide](https://pyodide.org) (MPL-2.0)
and uses [numpy](https://numpy.org) (BSD), [networkx](https://networkx.org)
(BSD), [igraph](https://igraph.org) (GPL-2.0-or-later, loaded at run time
from Pyodide's package set) and [Graphviz](https://graphviz.org) (EPL-2.0;
source at https://gitlab.com/graphviz/graphviz) through
[@hpcc-js/wasm-graphviz](https://github.com/hpcc-systems/hpcc-js-wasm)
(Apache-2.0), unmodified. The display uses [PixiJS](https://pixijs.com) (MIT)
and the console [CodeMirror](https://codemirror.net) (MIT).

