# GUESS for the Web — Implementation Plan

Reimplementation of GUESS (Adar, CHI 2006; sources in `guess-orig/`, paper in
`output-md/guess-chi2006/`) as a browser application.

## Decisions

| Question | Decision |
|---|---|
| Hosting | **Fully in-browser**, static site, no server |
| Language | **Python 3** (Pyodide) + Gython extensions; no Python 2 / Java-interop compatibility |
| v1 scope | **Core exploration** — phases 0–5 below. GUI extension, standalone export, movies are later |

## Source inventory (reference implementation)

- `guess-orig/guess-src.jar` — ~175 GUESS Java files under `com/hp/hpl/guess`:
  model (`Graph`, `Node`, `Edge`, `Field`, `StateGraph`, `*Query`), 21 layouts
  (`layout/`), Piccolo renderer (`piccolo/`), console (`ui/TextPaneJythonConsole`,
  `util/intervals`), charts, readers (GDF, GraphML, Pajek).
- Modified Jython grammar `org/python/parser/python.jjt`: adds `->`, `<-`, `<->`,
  `?`, `like`, `roverlaps`, `rcontains`, `rexact`, `rcontained` at comparison level.
- `guess-orig/scripts/Main.py` — ~200 global wrapper commands; the API surface.
- `guess-orig/sample.gdf` (300 nodes) and `scripts/dockexample*.py` — acceptance material.
- Built-in field defaults (from `db/DBServer.java`):
  - node: name, x=500, y=500, visible=true, color=cornflowerblue, strokecolor,
    labelcolor, fixed=false, style=2, width=10, height=10, label, image, labelvisible=false
  - edge: node1, node2, color=dandelion, labelcolor, visible=true, width=2,
    weight=1, directed=false, label, labelvisible=false
- Styles (`ui/VisFactory.java`): 1 rect, 2 ellipse, 3 roundrect, 4–6 text variants,
  7 image, 8–10 3D variants.

## Architecture

```
┌──────────── Main thread (TypeScript) ─────────────┐    ┌──── Web Worker ─────────────────┐
│ Renderer (PixiJS / WebGL)  ◄── patch stream ──────┼────┤ Pyodide (CPython 3 + numpy,      │
│ Console (input + structured output)               │    │   networkx)                      │
│ Panels, info window, charts                       │───►│ Gython compiler (tokens + AST)   │
│ Event bus: hover/select highlight everywhere      │cmds│ Graph model, fields, states      │
└───────────────────────────────────────────────────┘    │ Layouts / algorithms             │
                                                         └──────────────────────────────────┘
```

- **Worker owns the model**; main thread keeps only visual attributes
  (x, y, color, size, shape, label, visibility). Each command's mutations are
  collected and flushed as a batched patch (and periodically during long
  operations such as iterative layouts).
- **Interrupts**: Pyodide interrupt buffer over SharedArrayBuffer (requires
  COOP/COEP; dev server sets headers, static hosting uses `coi-serviceworker`).
  Falls back gracefully (no interrupt) when not cross-origin isolated.
- **Hover / highlight** resolved locally in main thread, no worker round-trip.

### Gython on Python 3

1. **Token rewrite** (`tokenize`, so strings/comments untouched): each Gython infix
   operator becomes `is <MARKER> is`, e.g. `a->b` → `a is _GOP_DIR_ is b`.
   Python's own parser then gives it comparison precedence, matching the
   original grammar (verified: `(alice<->g.nodes) & (freq > 15)`,
   `(a->b).width = 3`).
2. **AST transform**:
   - `Compare` with a marker → `__gop__('dir', a, b)`.
   - Expression statement that is a bare name bound to a GUESS command →
     call it (`randomLayout` without parens).
   - Attribute load/store, `&`, `|` → helpers that broadcast over
     tuples/lists of graph objects (`(alice,bob).style = 2`).
3. **Runtime**: `Node`, `Edge`, `NodeSet`/`EdgeSet` (attribute set broadcasts),
   `Field` objects in the namespace with overloaded comparisons returning sets,
   `.max/.min/.avg`, `field[state]`; namespace mapping that protects `g`, node
   names, colors and fields from rebinding.

Known edge case (same as original): `x<-1` parses as an edge operator; write `x < -1`.

## Feature mapping

| Original | Web |
|---|---|
| HSQLDB-backed fields, `sql()` | Python column store; `sql()` later via sqlite3 materialisation |
| JUNG algorithms (centrality, PageRank, clustering, generators) | networkx |
| GEM, Sugiyama, Radial, BinPack, Physics, Spring, MDS, ISOM, CircularConstrained | Ported from Java to Python/numpy; FR/KK/circle/random from networkx |
| `ss`/`ls`, `bob[1999]`, `_deleted`, Morpher tweening | Snapshot store in worker; tweening in renderer |
| Range fields, `rcontains` etc. | Interval index |
| Interpreter hover via interval tree | Structured output segments tagged with object ids → nested DOM spans |
| Context menus, "assign to variable" | Shared context-menu component |
| Image export | PNG / SVG |
| GDF / GraphML / Pajek I/O | Python readers/writers |
| Persistent mode, session log | IndexedDB autosave, replayable command log |
| Swing docking, applets, movies, R, Prefuse/TouchGraph, remote module | Out of v1 scope |

## Stack

Vite + TypeScript, PixiJS v8 (renderer), Pyodide 314.x (Python 3.14) in a
worker, plain DOM console (CodeMirror later if needed). Tests: pytest on the
`py/` package under CPython 3.14 (same version as Pyodide), Vitest for TS.

## Repository layout

```
PLAN.md
py/guess/         Python package loaded into Pyodide (pure Python, testable in CPython)
  compiler.py     Gython → Python 3 (token rewrite + AST transform)
  model.py        Graph, Node, Edge, sets, schema
  fields.py       Field objects and queries
  colors.py       Named colors (from Colors.java)
  gdf.py          GDF reader/writer
  session.py      Namespace, exec, structured output, patch collection
py/tests/         pytest
web/              Vite app (main thread + worker)
```

## Phases

0. **Spike** — worker + Gython compiler + render `sample.gdf`. Exit criteria:
   `(freq > 10).color = blue` updates the display; hovering console output
   highlights nodes.
1. **Core model & language** — schema/typed fields, GDF loader, edge operators,
   queries + `like`, set ops, broadcast setters, protected names, bare-name calls,
   colors, lazy degree & centrality fields, `addNode`/`addEdge`/`remove`.
2. **Renderer** — shapes per style, labels, directed edges/arrows, selection,
   pan/zoom, `center()`, convex hulls, legends, image nodes, background.
3. **Console** — multi-line blocks, history, structured output, linked
   highlighting, tooltips (top 15 / annotations / docs / exceptions), context menus.
4. **Algorithms & layouts** — networkx-backed and ported layouts; iterative
   layouts stream positions; `colorize`, `resizeLinear`, `groupBy`, `sortBy`,
   clustering.
5. **States & dynamic graphs** — `ss`/`ls`, state-indexed fields, range fields
   and operators, tweening, `_deleted` state.
6. **Applications** (post-v1), replacing Swing docking / applets:
   - 6a. Python widget API (`Panel`, `Button`, `Slider`, `Checkbox`, `Dropdown`,
     `TextField`, `Label`; `ui.dock(panel)`), timers (`every`, `after`),
     `graphevents.clickNode = fn` & friends, `vf.defaultNodeHighlights(false)`,
     `StatusBar.setStatus`, `openURL`.
   - 6b. Linked charts: `plotHistogram`, `plotSizes`, `plotSizesPie`,
     `plotDistrib` in dock panels; hovering a bar/slice highlights its
     elements; hovering elements elsewhere highlights (pulls out) bars/slices.
   - 6c. Session files (`.guess` JSON: graph, fields, states, ranges, hulls,
     legends, background) — `saveSession`/open, autosave to IndexedDB with
     restore on reload; app mode (`?load=<url>&app=1`: console hidden,
     startup script runs) as the applet replacement; `exportApp(script)`.
   - 6d. Movies: `startMovie(fps, name)` / `stopMovie()` → WebM via MediaRecorder.

## Testing strategy

- pytest for compiler and model (CPython 3.14 locally = Pyodide's version).
- Re-express paper examples as tests (`freq > 10`, `name like 'al%'`, `x > y`,
  `(alice,bob) & (jobfunc == 'manager')`, `colorize(dept)`, ...).
- Optionally run the original GUESS (`guess-orig/guess.sh`, no-OpenGL) on a
  modern JVM to capture reference outputs.

## Progress

- [x] **Phase 0 spike** (2026-11-04) — see `README.md` to run. Verified in headless
  Chrome: sample.gdf loads (402 nodes / 725 edges, ~2.3 s cold start),
  `(freq > 100).color = red` recolors edges, hovering console output highlights
  nodes/groups with tooltips, Stop interrupts `while True: pass`, protected
  names rejected. 18 pytest tests pass on CPython 3.14.
  Already pulled forward from Phase 1: GDF reader/writer, all Gython operators
  except range ops, broadcast setters, `groupBy`/`sortBy`/`colorize`/
  `resizeLinear`, lazy `betweenness`/`pagerank`, add/remove, context menu.
- [x] **Phase 1 core model & language** — plus Pajek / GraphML / UCINET DL
  import, GraphML export, the JUNG random generators (via networkx),
  `remove`/`add`/`removeComplete` with a recoverable `g.deleted`,
  `removeLeaves`, `shortcutNodes`, `condenseGraph`, `complement`, `copyNode`,
  `skitter`, `biComponentClusters`, ...
- [x] **Phase 2 renderer** — convex hulls (follow their nodes), `Legend()` /
  `GradientLegend()`, background color/image, image nodes (style 7), arrow
  overrides, PNG/JPG/SVG export (`exportPNG` etc. and toolbar). Labels are
  pooled BitmapText. At 5,000 nodes / 8,000 edges a full restyle is ~150–300 ms
  and idle rendering holds 60 fps.
- [x] **Phase 3 console** — Tab completion (names, fields after `.`), doc
  tooltips on command names in echoed input, `log()`/`stoplog()` session
  recording (replay with `execfile`), drag-and-drop file open.
- [x] **Phase 4 layouts** — `py/guess/layouts.py` (numpy): random, circle
  (+ CircularConstrained), fr/jfr, kk/jkk1/jkk2/weightedKK, spring/jSpring/
  weightedSpring, gem, isom, physics, radial, mds, sugiyama/sugiyama2/dag,
  binPack, rescale/translate/move, `centerAfterLayout`. Iterative layouts animate
  (position-only patches) and can be interrupted. All 23 run in the browser on
  sample.gdf in 30 ms – 2.3 s.
- [x] **Phase 5 states** — `ss`/`ls`/`getStates`, `morph(state, ms)` with
  tweening and `set{Node,Edge}{AppearAfter,DisappearBy}`, `bob[1999].field`,
  `freq[2000] > freq[1999]`, range queries (`Node rcontains 5`, `roverlaps`,
  `rcontained`, `rexact`, `addRange`, `search*`).

- [x] **Phase 6 applications** (2026-11-04)
  - 6a `gui.py`: `Panel`/`Button`/`Slider`/`Checkbox`/`Dropdown`/`TextField`/
    `Label`, `ui.dock`, `every`/`after` timers, `graphevents.*`, `vf`,
    `StatusBar`, `openURL`. Original handler names (`actionPerformed`,
    `mouseReleased`) work as aliases; the paper's slider example runs as written
    (with `def hideshow(val):`).
  - 6b `charts.py`: `plotHistogram`, `plotSizes`, `plotSizesPie`, `plotDistrib`;
    bars/slices highlight their elements, and hovering elements in the graph or
    console highlights (pulls out) the bars/slices containing them.
  - 6c `persist.py`: `.guess` session files (`saveSession`, `makeFromSession`,
    Save button, Open/drop), autosave to IndexedDB with restore on reload,
    `exportApp(file, script)` + `?load=<url>&app=1` app mode. Example:
    `web/public/examples/demo.guess` (built from `demo-ui.py`).
  - 6d `startMovie`/`stopMovie` → WebM of the graph canvas.

- [x] **Hardening** (2026-11-04)
  - Static hosting: relative `base`, `coi-serviceworker` for COOP/COEP on hosts
    that can't set headers (verified: isolated + interruptible from a plain
    static server); CI workflow (pytest, typecheck, build, Playwright e2e) with
    GitHub Pages deploy from `main`. Browser tests live in `web/e2e` (12 tests).
  - `sql()` over in-memory SQLite tables `nodes` / `edges` (SELECT → rows or
    graph elements; UPDATE writes back).
  - Edge routing: `sugiyamaLayout(true)` stores bend points (cleared by other
    layouts, kept in session files); parallel / reciprocal edges draw as
    separate curves; hit-testing, arrows, labels and SVG follow the geometry.
  - Large graphs: GEM inserts breadth-first layers at once above 1,000 nodes
    (5k-node GEM 22 s → 9 s in the browser); Barabási–Albert generator is
    linear (5.3 s → 0.9 s).

### Cell console (2026-11-05)

- [x] The console is a CodeMirror 6 working cell (Python highlighting, async
  completion from the worker with doc popups, hover docs, bracket closing) plus
  a stack of executed cells with their output (numbered, timed when slow, marked
  on error, foldable, Edit / Run again / double-click to reuse). Runs from menus
  and toolbar become cells too and queue in order; output from timers and events
  goes to loose log blocks between cells.
- [x] Layout: graph on the left, code on the right (resizable, width remembered),
  stacked vertically below 760 px. The canvas follows its container size.

- [x] Gython `a - b` between nodes selects the undirected edges between them,
  as in the original (it had been set difference). Set difference is
  `s.difference(t)`.
- [x] KK at scale: components over 1000 nodes (kkLayout) / graphs over 1000
  nodes (jkk*, weightedKK) use PivotMDS + sampled stress majorization (edges
  plus 48 random partners per node per iteration, 60 iterations) — the same
  energy, within ~1–3% of exact Newton KK, 8–30x faster. 5k nodes: 12–19 s ->
  ~7 s in the browser (the all-pairs BFS is now the bulk).

- [x] Gephi-style curved edges: `curvedEdges()` / `curvedEdges(k)` / toolbar
  "Curved" — Gephi Preview's geometry (PreviewPlugin EdgeRenderer.CurvedEdgeRenderer):
  a circular arc of radius length/k (default k = 1.2), clockwise from source to
  target, so a->b and b->a separate. Same-direction parallel edges get different
  curvatures (Gephi overlaps them). `setEdgeColorMode("original"|"source"|"target"|"mixed")`.
  Both saved in sessions; used by hover, labels and SVG export.

### Gephi features (2026-11-05) — the top 10 below, built

- Statistics (`analysis.py`): computed node fields pagerank, hub/authority,
  eigenvector (numpy power iteration — networkx's pagerank/hits need scipy,
  which isn't loaded, so `pagerank` used to fail in the browser), closeness,
  harmonic, eccentricity (blocked numpy BFS; hops, ignoring direction),
  clustering, triangles, coreness, strength, component, strongcomponent.
  Bare field names in code compute on first use (`sizeBy(pagerank, ...)`);
  `recompute()` refreshes them. `graphStats`, `diameter`, `radius`,
  `averagePathLength`, `averageClustering`, `modularity(field)`.
- `louvainClusters(resolution, seed)` -> `modularity_class` + Q (networkx).
  `distinctColors(n)`: iWantHue-style k-means in Lab; `colorize(field)` now
  uses it (largest group first) instead of random colours.
- Filters returning sets: `kCore`, `egoNetwork`, `giantComponent`,
  `intraEdges`/`interEdges`, `mutualEdges`, `groupsOfSize`; `showOnly`/`showAll`.
- `forceAtlas2Layout` (ForceAtlas2.java forces and adaptive speed; mass-weighted
  grid repulsion stands in for Barnes-Hut), `noverlapLayout`, `rotateLayout`,
  `mirrorLayout`. `_repulsion` gained per-node masses.
- `sizeBy` / `colorBy` (value-proportional; linear, log, sqrt, rank).
- Labels: `labelOutlines()` (background-colour halo, also in SVG),
  `hideOverlappingLabels()` (bigger nodes win; rechecked on zoom). Saved in sessions.
- GEXF in/out (`gexf.py`: attributes, viz colour/position/size/shape, weights,
  thickness; y flipped, positions are centres) and CSV tables (edge table,
  node table merged by Id, adjacency matrix/list, delimiter sniffing;
  `exportCSV`). Open… accepts .gexf/.csv/.tsv.
- Front end: Select mode focuses a clicked node's neighbourhood (others dim,
  focused labels shown); Path/Heat/Paint tools with a colour picker emit
  `shortestPath(a, b).color = c`, `heatMap(a)`, `paint(a, c[, 1])`.
- Not done from the list: Label Adjust (needs measured label boxes in the
  worker), in/out edge colouring in the focus view, label size field.

### Usability round (2026-11-05)

- Selection: shift-drag box, alt-drag lasso (+Cmd/Ctrl adds), shift-click
  toggles, group drag, right-click acts on the selection; bound to `sel`;
  `select(seq)` from code. Clicking linked console output selects and zooms.
- `print()` of nodes/edges/sets emits linked output.
- Undo/redo: per-command journal in the model (`Journal`, `Graph.revert`),
  plus view/states/ranges snapshots; 50 steps; node drags are steps; undone
  cells struck through (`undone` message carries the console cell number).
  `history()` / `saveHistory()` list every command run.
- Dark mode: CSS tokens with `prefers-color-scheme` and an Auto/Light/Dark
  toggle; display background `None` follows the theme (session format v2
  migrates the old explicit "white" default); label colour adapts to the
  background.
- Taller working cell (3 lines minimum).
- Docs in `docs/` (user guide, generated API reference with a staleness test,
  architecture, developer, deploy). `npm run bundle [-- --offline]` builds a
  deployable folder + zip/tar.gz; offline bundles include Pyodide (~18 MB),
  verified loading with the CDN blocked from a plain static server.

### Competitive-analysis round (2026-11-05)

Built from docs/COMPETITIVE_ANALYSIS.md (everything except the assistant and
collaboration) plus docs/DECLARATIVE_DRAGGING.md:
- Help browser (searchable commands and curated examples, `helpdata.py`),
  Cmd/Ctrl+K palette, parameter hints, one-line errors with the failing line
  marked and "did you mean" suggestions.
- Data table (virtualised, linked selection, inline edits as Gython),
  Style panel (mappings → colorize/colorBy/sizeBy/labelBy/shapeBy/legendFor,
  saved styles), Filter panel (histograms, range sliders, categories,
  k-core/ego/component/group size → showOnly), Variables panel.
- Menu bar (File, Edit, View, Layout, Analyze, Help) replacing the toolbar.
- Watched (live) cells; charts re-plot in place. Notebook (.ipynb) and HTML
  report export. Vim keys, multi-cursor, editor search, find in output.
- Groups: collapse / collapseBy / expand (double-click), nested, undoable,
  saved. Several graphs per session: subgraph / use / newGraph, tabs.
- Pie nodes (pieChart / pieNeighbors), borderBy, bundleEdges (B-spline
  routes through group centres). treeLayout, labelAdjustLayout, scatterLayout.
- Connectors: makeFromURL, sparql / makeFromSPARQL (Wikidata), makeFromNDEx,
  makeFromCypher (Neo4j HTTP), installPackage (micropip), paste a table.
- Timeline bar (ranges or a numeric field; scrub, play, window, sparkline)
  with quiet runs; Presentation mode (slides = state + camera + note).
- Share links (gzip session in the URL hash; viewer links open in app mode).
- Scale: ForceAtlas2 in JS with Barnes-Hut inside the Python worker for
  graphs over 1,000 nodes (about 9x faster at 20k nodes / 80k edges),
  on-demand rendering, batched edge drawing, quick-reject edge hit tests.
- Declarative dragging: group drop, ring slide, Alt-drag edges, scatter edit.

### Gephi-inspired candidates (survey of gephi/modules, 2026-11-05)

S = under a day, M = a few days, L = a week+. "nx" = networkx already has it.

Top picks by value for effort (all built except as noted above):
1. Louvain modularity (resolution) -> `modularity_class` + Q (nx), with an
   iWantHue-style distinct palette (port of AppearancePlugin PaletteGenerator). S
2. ForceAtlas2 (LinLog, gravity/strong gravity, dissuade hubs, prevent overlap,
   Barnes-Hut), animated step by step. M
3. GEXF import/export (nx read/write_gexf; Gephi's native format). S
4. Selection highlight: dim non-neighbours, in/out/both edge colours. S, front end
5. Centrality pack: HITS, eigenvector, closeness, harmonic, eccentricity,
   diameter/radius/avg path length, clustering coefficient/triangles,
   weighted degree, strongly connected components (all nx). S
6. Structural filters: k-core, ego network depth N, giant component,
   intra/inter-partition edges, partition size >= k, mutual edges. S
7. Ranking mappings with log / spline interpolation; label halos and
   label-overlap culling; node borders; edge weight -> thickness rescale. S/M
8. CSV node/edge table import (edge list, adjacency list/matrix). S/M
9. Noverlap layout; Rotate/Mirror; Label Adjust (needs label metrics). S/M
10. Click tools: shortest path between two nodes, heat map (colour by distance
    from a node), brush/painter with neighbour diffusion, node/edge pencil. S

Next tier: Yifan Hu (multilevel), OpenOrd (L); Statistical Inference
Clustering (SBM/MDL, L); dynamic graphs — element lifetimes and time-varying
attributes, a timeline slider with play and sparkline, dynamic range filter,
dynamic statistics (L; states/ranges are a partial substitute); data-lab
operations (merge nodes with sum/avg/median/... strategies, merge duplicates,
regex column ops, search & replace, value-frequency tables, CSV table export);
more formats (DOT, TLP, VNA, TGF in; JSON/graphology, GML, CSV matrix out);
import-and-merge into the current graph; style presets (DefaultCurved,
BlackBackground, TextOutline, ...); edge labels on the arc midpoint; Gephi-style
self-loop arcs; generators (multi-edge-type, dynamic test graphs, plus nx
classics such as SBM, Watts-Strogatz, karate club, Les Misérables).

### Next candidates

- Live (auto-refreshing) charts; GraphML export of states/ranges.

### Deviations from the original (deliberate)

Layouts (details in the `layouts.py` docstrings):
- Iterative layouts run a default number of iterations / until converged
  instead of asking every 30 s; an explicit count is always honoured.
- Fixed nodes are pinned inside force simulations (the original simulated
  them and just didn't write them back).
- Bugs not reproduced: GEM placing only the first component, kkLayout
  indexing across components, translateLayout shifting twice, FR resetting its
  displacement inside the repulsion loop, MDS collapsing on equal weights
  (falls back to hop-distance MDS), Sugiyama levels from DFS depth (now longest
  path), sugiyamaLayout2 stacking tiers in 200 px.
- `dagLayout` puts sources on top (JUNG put sinks on top).
- `sugiyamaLayout(true)` routes long edges through its dummy positions
  (polyline edges); other layouts clear the routes.
- `gemLayout` on graphs over 1,000 nodes inserts whole BFS layers at once
  instead of one node at a time (the arrangement phase is unchanged).

Language/model:

- `x<-1` (`<-` followed by a number literal) stays a comparison; the original
  always treated `<-` as the edge operator.
- `resizeLinear` reaches the `end` size for the top group (original divided by
  the group count, so it never did).
- GUI extension uses a small Python widget API instead of Swing/Java classes;
  charts are snapshots (re-run to refresh) drawn as SVG; movies are WebM and
  capture the graph canvas only (not legends or panels).
- Session files don't include user variables; autosave restores the graph,
  states and view, not the namespace.
- `true` / `false` are bound as protected names for compatibility with
  Java-era scripts.
- `g.deleted` holds removed elements (the original's `_deleted` state);
  `add(g.deleted)` restores them.
- Range queries take the element ranges set by `addRange`, or any string field
  holding a range (`span rcontains 3`).
- `colorize(field)` with no colours uses a distinct categorical palette
  (largest group first) instead of random colours.
- Images (`setBackgroundImage`, node `image`) are files opened into the session
  or URLs; they are sent to the renderer as data URLs.
- networkx is loaded from its wheel URL to skip Pyodide's matplotlib/numpy
  dependency chain (cold start ~10 s → ~2 s). Layout ports in Phase 4 will
  add numpy explicitly.
