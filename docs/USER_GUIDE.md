# User guide

GUESS is a graph exploration tool you drive with **Gython**: Python 3 with
operators for selecting and changing nodes and edges. The window has the graph
on the left and the code console on the right (below the graph on narrow
screens; drag the divider to resize).

## Getting a graph in

- **Sample graph** loads the bundled example (402 nodes).
- **Open…** or drag and drop: `.gdf`, `.gexf` (Gephi), `.graphml`/`.xml`, `.gml`, `.dot`/`.gv` (Graphviz),
  `.net` (Pajek), `.dl` (UCINET), `.csv`/`.tsv` (edge table, node table,
  adjacency matrix or list), `.guess` sessions, `.py` scripts (run), images
  (for `setBackgroundImage` or node images).
- From code: `makeFromGDF("file.gdf")`, `makeFromGEXF(...)`, `makeFromCSV("edges.csv", "nodes.csv")`,
  or generators such as `makeBarabasiAlbertRandom(5, 2, 300)`.

Your work is autosaved in the browser and restored when you come back
(variables excepted). **Save** downloads a `.guess` session file.

## The console

Type in the working cell at the bottom and press **Shift+Enter** (or
Cmd/Ctrl+Enter) to run; Enter adds a line, so multi-line code is natural.

| key / action | does |
|---|---|
| Shift+Enter, Cmd/Ctrl+Enter | run the cell |
| Tab | complete (commands, fields, nodes, attributes) |
| ↑ / ↓ on the first / last line | previous / next command from history |
| Esc | interrupt running code (also the **Stop** button) |
| Ctrl+L | clear the output |
| **Edit** (or double-click the code) on an executed cell | copy it back into the working cell |
| **Run again** | run that cell's code again as a new cell at the bottom |
| `[n]` | fold / unfold a cell's output |

Output that refers to nodes and edges is linked: **hover** to highlight them in
the graph, **click** to select them (and zoom to them), **right-click** for a
menu (colour, size, labels, hide, assign to a variable). This also works for
`print(n)`. Hover a command name for its documentation, or run `help(name)`.

`history()` lists every command you ran this session, in order;
`saveHistory("work.py")` downloads them as a script.

## Gython in five minutes

```python
dept                                  # a field; fields are named like variables
dept == 'dept1'                       # the nodes whose dept is dept1 (a set)
(freq > 100).color = red              # setting an attribute on a set sets it on each
v1.color, v1.size = blue, 20          # nodes are variables named after them
v1 -> v2        v1 <- v2              # directed edges between nodes or sets
v1 <-> v2       v1 - v2               # undirected edges
v1 ? g.nodes                          # any edges between v1 and anything
(dept == 'dept1') & (freq > 10)       # set intersection; | is union
(freq > 100).nodes                    # the nodes those edges touch; (dept == 'dept3').edges: their edges
for n in (dept == 'dept3'):           # sets are iterable
    n.labelvisible = true
colorize(dept); resizeLinear(totaldegree, 5, 30)
sizeBy(pagerank, 5, 40, "log"); colorBy(closeness, yellow, red)
gemLayout                             # commands without arguments need no ()
```

See [API.md](API.md) for every command and field.

## Clicking and selecting in the graph

The app explains these itself: **Help → Mouse and gestures** (or the "Mouse &
gestures" tab of the Help panel, F1) has a card with a screenshot for every
gesture below, and a tip appears the first time a gesture becomes available
(e.g. after `circleLayout()`, sliding nodes around the ring).

| gesture | does |
|---|---|
| drag background | pan; mouse wheel / pinch zooms; double-click fits |
| Delete / Backspace | remove the selected nodes (Edit → Delete selected nodes; undoable) |
| drag a node | move it (and the whole selection, if it is selected); recorded as a hidden command (View → Show node moves in the console) |
| click a node (**Select** tool) | highlight it and its neighbours; click again or Esc to clear |
| Shift-drag | box-select nodes |
| Alt/Option-drag | lasso-select nodes |
| add Cmd/Ctrl to a box or lasso | add to the selection |
| Shift-click a node | add / remove it from the selection |
| Esc, or click the background | clear the selection |
| right-click | context menu (for the whole selection if you right-click a selected node) |

**Dragging with meaning.**
- After `circleLayout()`, nodes slide around the circle and the others make room.
- Alt-drag from one node to another adds an edge.
- After `scatterLayout(x, y)`, dragging a node edits those two fields.

Each drop is one command in the console, so it can be undone.

The selection is the variable **`sel`** in the console (`sel.color = red`,
`center(sel)`, `showOnly(sel)`), and `select(dept == 'dept2')` selects from code.

The **Path**, **Heat** and **Paint** tools turn clicks into commands (shown in
the console, so you can edit and re-run them): click two nodes to colour a
shortest path; click a node for a distance heat map; click to paint nodes with
the colour next to the tools (Shift-click paints neighbours too).

## Undo

**Undo** / **Redo** in the toolbar, Cmd/Ctrl+Z and Shift+Cmd/Ctrl+Z (or Ctrl+Y)
when the code cell isn't focused, or `undo()` / `redo()` in the console. Each
command is one step (a layout, a file load, `colorize`, a node drag…), up to 50
steps back. Undone cells are struck through in the console; redo restores them.
Undo covers the graph, fields, states, ranges, hulls, legends and display
settings, but not Python variables or downloaded files.

## Layouts and analysis

Layouts animate while they run and can be stopped with Esc/Stop:
`forceAtlas2Layout()` (Gephi's; options such as `linLog=true`,
`preventOverlap=true`), `gemLayout`, `frLayout`, `kkLayout`, `springLayout`,
`mdsLayout`, `sugiyamaLayout`, `radialLayout(v1)`, `circleLayout`,
`binPackLayout`, `hiveLayout(field, position)` (a hive plot: radial axes per
group, nodes placed by a value), `treeLayout`, `noverlapLayout`, plus `rotateLayout`, `mirrorLayout`,
`rescaleLayout`.

Statistics are node fields computed on first use: `pagerank`, `betweenness`,
`closeness`, `harmonic`, `eccentricity`, `eigenvector`, `hub`, `authority`,
`clustering`, `triangles`, `coreness`, `strength`, `component`. Use them like
any field (`(pagerank > 0.01).labelvisible = true`) and run `recompute()` after
editing the graph. `graphStats()` prints a summary; `louvainClusters()` finds
communities (`colorize(modularity_class)`). Filters return sets: `kCore(3)`,
`egoNetwork(v1, 2)`, `giantComponent()`, `intraEdges(dept)`; `showOnly(...)`
hides the rest and `showAll()` brings it back.

## Display

- **Curved** toggles Gephi-style curved edges (`curvedEdges(0.6)` sets the
  curvature); `setEdgeColorMode("mixed")` colours edges by their endpoints.
- `labelOutlines()` and `hideOverlappingLabels()` keep labels readable.
- `createConvexHull(dept == 'dept1', "200,200,255,90")`, `Legend()`,
  `GradientLegend(...)`, `setDisplayBackground(black)` (`None` follows the theme).
- The theme button cycles **Auto** (follows the system), **Light** and **Dark**.
- **PNG** / **SVG** export the view; `startMovie()` / `stopMovie()` record WebM.

## States, ranges, charts, apps

`ss("before")`, change things, then `morph("before", 2000)` animates back.
`addRange(v1, "1-5")` and `Node rcontains 3` query existence intervals.
`plotSizesPie(dept)`, `plotSizes(dept)`, `plotHistogram(freq)` make charts linked to the graph.
`ui.dock(Panel("Edges", Slider(...), Button(...)))` builds controls, and
`exportApp("app.guess", "ui.py")` packages a graph with its interface for
`?load=app.guess&app=1`. See [API.md](API.md) for details.
