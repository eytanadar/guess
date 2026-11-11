# The 2006 GUESS manual vs. GUESS for the web (2026-11-06)

`old-manual.pdf` is the GUESS manual of 8/24/2006 (version 1.0.1 beta, 54
pages). This document compares it with the current implementation.

**Method.** The whole manual was read. Every code example in it (190
snippets) was then run against the current implementation, on the sample
graph and on the manual's own small GDF files (the office example, the range
example and the multi-edge example). Default values and the colour table were
checked against the original Java source and Appendix A.

**Summary.**
- Most of the language and the commands work as the manual describes:
  - queries and set operators;
  - edge operators;
  - broadcasting attribute assignment over sets;
  - fields and field statistics;
  - states, `morph` and state subscripts;
  - range operators;
  - legends and hulls;
  - clustering and grouping;
  - colours and colour mappings;
  - the generators;
  - graph events;
  - the Functions.py helpers.
- All 80 named colours match Appendix A exactly.
- Two outright bugs found by the manual's examples are **fixed** (section 1).
- The missing compatibility names and behaviour have been **added**
  (section 2). Of the manual's 190 code snippets, 181 now run unchanged. The
  other 9 are deliberate platform differences (section 3): SWF/Java/CGM/EMF
  export, assignment into a state subscript, the R interface and `javax`.
- One place where the manual is wrong rather than the code: §11.2's
  `Node roverlaps (2,5)` answer. See section 2.
- The remaining differences are deliberate consequences of moving from
  Java/Jython to the browser and Python 3 (section 3).

## 1. Bugs found and fixed

| Manual | Problem | Now |
|---|---|---|
| §7.1 `edgeBetweennessClusters(…)` | crashed (`AttributeError: _g`): networkx deep-copies the graph, and nodes weren't copyable | fixed (nodes and edges are copy-safe handles); 29 clusters on the sample |
| §7.3, §8 `v291.unweightedShortestPath(v376)` | returned a number (the distance), so `(…).color = blue` failed, and `len(v4.unweightedShortestPath(n))` (§8's example) failed | returns the path's edges, following direction, as the original did (JUNG `ShortestPathUtils.getPath`); `dijkstraShortestPath` (weighted) added |

## 2. Compatibility names and behaviour (added)

These appeared in the manual but were missing or behaved differently. All
now work as the manual describes. Most live in `py/guess/compat.py`. They
are ordinary variables, not protected names, so a script can still say
`import random` or `for v in g.nodes`.

| Manual | Now |
|---|---|
| `g.gemLayout()`, `g.frLayout()`, `g.radialLayout(v5)`, `g.colorize(…)` (§6, §7.3, §16.2) | every command is also a method of `g` |
| `random()`, `random(w, h)` (§6) | calling `random` runs the random layout; `random.choice(…)` etc. still reach Python's module |
| `biComponentCluster()` (§7.1) | removed in 2026: use `biComponentClusters()` |
| `findEdges(set)`, `findNodes(set)` (§5.1) | the edges / nodes among a set's members. (`set.edges` / `set.nodes` also include incident edges / endpoints) |
| `Types.INTEGER`, `Integer(0)`, `Double`, `String`, … (§8) | accepted |
| `Morpher.setNodeDisappearBy(.2)` etc. (§11) | accepted (the plain functions also work) |
| fields `degrank`, `hits`, `rwbetweenness` (§7.3) | added: degree rank (degree / total degree), HITS authority, and Newman's random-walk (current-flow) betweenness |
| `weight['_deleted'] > 5` (§8) | the `_deleted` pseudo-state can be queried by subscript |
| `removeNode(vx)` … `addNode(vx)` (§8) | a node removed with `remove`/`removeNode` keeps its name, so `addNode(vx)` puts it back. Undo, loading a state, `removeComplete` and loading a new graph still drop the names of nodes that are gone |
| `Node rcontains 5` with a text field called `range` (§11.2); `Node.setRangeField(f)`, `Node.rebuildRangeIndex()` | range queries read the `range` field (or the one named by `setRangeField`) for elements without `addRange`; `rebuildRangeIndex()` is accepted (ranges are computed on demand) |
| `GradientLegend(red, yellow, min, max, 10)` (§12) | the 5th argument sets the tick spacing |
| `vf.defaultEdgeHighlights(…)`, `vf.defaultEdgeZooming(…)` (§15.5.1) | added: they turn the endpoint highlight on hover and the zoom on double-click on or off |
| `NodeEditorPopup.addItem("…")` with `item.menuEvent = f` (§15.5.2); `EdgeEditorPopup`, `GraphElementPopup` | items appear in the right-click menu; `f` receives the element (or the selection) |
| `v.setBackgroundImage(f[, x, y])`, `v.repaint()`, `v.getLastClickedPosition()`, `v.center(…)` (§15.5) | a `v` display object; `getLastClickedPosition()` returns the last click in graph coordinates (`.getX()`, `.getY()`); `repaint()` is accepted (drawing is automatic) |
| `getAppletContext().showDocument(url[, name])` (§16.3) | opens the URL in a new window |
| `infowindow()`, `InfoWindow.details(name)` (§5.2) | open the data table (on that element) |
| `readjustEdges()`, `setSynchronous(state)` (§6) | accepted; parallel edges are always drawn as separate curves, and layouts always run in order |
| `exportGIF/PDF/PS/EPS` (§9) | added (each holds an image of the view; `exportSVG` is the vector format). `exportSWF/JAVA/CGM/EMF` give an error suggesting SVG or PDF |
| Visibility rules (§5): hiding a node hides its edges; showing an edge shows its endpoints | implemented as the manual's one-step rule (and undoable) |

**Where the manual is wrong.** §11.2 says `Node roverlaps (2,5)` gives
`v0, v1` on its example. The original IntervalTree treats intervals as
closed, so v3's range (5–7) touches 5 and overlaps too. The original code,
and this version, return `v0, v1, v3`.

## 3. Deliberate differences (platform and design)

**Platform:**
- **Running it:** the manual's Java runtime, JMF, `guess.bat`/`guess.sh`,
  persistent HSQLDB databases and start-up dialogs are replaced by a web page.
  Work is autosaved in the browser, and `.guess` session files hold
  persistent work.
- **Language:** Jython 2 (Python 2.x) is now Python 3. The manual's
  `print "node " + …`, `except (A, B), e` and Python 2 integer division don't
  apply. Gython's operators are unchanged.
- **Console:** the `>`/`.` prompt is replaced by the cell console
  (Shift+Enter), which adds history, completion and undo.
- **Interface building (§15):** extending Swing's `DockableAdapter` with
  `JButton`/`JSlider`, jfreechart, Java threads and sockets is replaced by
  the Python widget API: `Panel`, `Button`, `Slider`, `Checkbox`, `Dropdown`,
  `ui.dock`, linked charts, and `every()`/`after()` timers. Raw Java objects,
  threads and sockets don't exist, so §15.3's thread-driven monitor needs
  timers and §15.4's socket remote control isn't possible in a browser.
- **R interface (§13):** `r.x = …` and `rmode` are not available.
- **Applets (§16), front ends (§17), command line (§18):**
  - Applets, signing, `jythonc`, the DemoApp Java programs, the
    Prefuse/TouchGraph front ends and the command-line options are replaced
    by static hosting, `?load=<file>` and `?app=1` with `exportApp(…)`.
  - The bundle runs offline.

**Interaction (§3):**

| 2006 | now |
|---|---|
| clicking a node centres on it | clicking focuses its neighbourhood; double-click zooms |
| clicking an edge brings both endpoints into view | hovering rings the endpoints; double-click zooms |
| right-drag zooms | wheel or pinch zooms |
| shift-drag draws a zoom rectangle | shift-drag selects (box); Alt-drag lassos |
| five tool buttons: browse, node, edge, hull, annotate; node resize handles; annotations | Select, Path, Heat and Paint tools; drags with meaning (group, ring, edge, scatter); no resize handles, hull editing or annotations |

**Drawing and data:**
- **Node styles:** styles 8–10 ("3D") are drawn flat. Custom polygon shapes
  (`shapeDB.addShape`, style > 100) and Java images pushed onto nodes
  (`CustomNodes.py`) are not supported; node images come from files or URLs.
- **Multiple edges:** the manual allows at most three edges between two
  nodes (a→b, b→a, a–b), removes duplicates on load, and has a
  `--multiedge` option. Any number of edges is allowed here.
- **Defaults:** the manual lists nodes as blue, style 1, 4×4, and edges as
  green, width 0.3. The original code (DBServer.java) used cornflowerblue
  nodes, and GUESS for the web follows the code.
- **Movies:** QuickTime (`.mov`, frames per redraw) is replaced by WebM
  recorded in real time.
- **Image export:** the manual exported the visible window. PNG, JPG, GIF,
  PDF and PS/EPS export the view, and SVG exports the whole graph. SWF, Java,
  CGM and EMF are gone.
- **State subscripts** (`weight['s1']`) can be read but not assigned to.
- **Layouts:**
  - Iterative layouts run a default number of iterations instead of asking
    every 30 seconds; Stop/Esc interrupts.
  - `kkLayout` handles graphs with several components; the manual says it
    fails on them.
- **`density`:** the manual quotes .00827 for its sample; the bundled
  `sample.gdf` (402 nodes, 725 edges) gives 0.0090. The sample probably
  changed between versions.
- **Subgraphs (§10):** "API not finalized" in the manual. Here: `subgraph(…)`,
  `use(…)` and graph tabs.

## 4. Beyond the manual

Much of the current system has no counterpart in the 2006 manual:
- Gephi-style statistics, layouts (ForceAtlas2, hive plots, …) and filters.
- Undo/redo, help and search, the data table, and the style, filter and
  timeline panels.
- Selection gestures and dragging with meaning.
- Several graphs, groups, pie nodes, edge bundling and presentation slides.
- GEXF, CSV, URL, SPARQL, NDEx and Neo4j import.
- Notebooks, reports, share links and dark mode.

See PLAN.md and USER_GUIDE.md.
