# Gython API reference

Generated from the docstrings by `py/tools/gen_api_docs.py`; do not edit by hand.
In the console, `help(name)` shows the same text, and hovering a command name
in an executed cell shows it as a tooltip.

Commands can be called without parentheses when they take no arguments
(`gemLayout` is `gemLayout()`). Colors are names (`red`), `"r,g,b[,a]"` or `"#rrggbb"`.

## Contents

- [Graph structure, loading and saving, mapping, view](#graph-structure-loading-and-saving-mapping-view) (50)
- [Undo, redo, history and logging](#undo-redo-history-and-logging) (6)
- [Statistics, communities, filters and paths](#statistics-communities-filters-and-paths) (20)
- [Clustering and generators](#clustering-and-generators) (11)
- [Layouts](#layouts) (28)
- [Display: hulls, legends, background, edges, labels, selection, export](#display-hulls-legends-background-edges-labels-selection-export) (22)
- [States and morphing](#states-and-morphing) (12)
- [Ranges (existence intervals)](#ranges-existence-intervals) (6)
- [Charts](#charts) (4)
- [Interface building (panels, widgets, timers, events)](#interface-building-panels-widgets-timers-events) (11)
- [Sessions and apps](#sessions-and-apps) (3)
- [SQL](#sql) (1)
- [Colors](#colors) (4)
- [Fields](#fields)
- [Gython syntax](#gython-syntax)

## Graph structure, loading and saving, mapping, view

### `add(seq)`

Re-add removed nodes/edges, e.g. add(g.deleted).

### `addDirectedEdge(node1, node2, **attrs)`

Add a directed edge from node1 to node2.

### `addEdge(node1, node2, **attrs)`

Add an undirected edge.

### `addEdgeField(fieldName, sqlType='VARCHAR', defaultValue=None)`

Create an edge field, e.g. addEdgeField("kind", VARCHAR, "").

### `addNode(name, **attrs)`

Add a node (or return the existing one with that name).

### `addNodeField(fieldName, sqlType='VARCHAR', defaultValue=None)`

Create a node field, e.g. addNodeField("score", DOUBLE, 0).

### `addUndirectedEdge(node1, node2, **attrs)`

Add an undirected edge between two nodes (by node or name).

### `averageEdgeColor(edges=None)`

Color edges the average of their endpoint colors (all edges by default).

### `center(*d)`

center() fits the whole graph; center(seq) zooms to the given elements.

### `colorBy(field, start, end, scale='linear', middle=None)`

colorBy(field, startColor, endColor) colours elements along a gradient in
proportion to a numeric field's value; scale may be "linear", "log",
"sqrt" or "rank"; middle=color adds a midpoint colour. Compare colorize,
which spaces distinct values evenly.

### `colorize(field, *cs)`

colorize(field) gives each value its own clearly different colour (the
largest group first; see distinctColors); colorize(field, start, end) or
colorize(field, start, middle, end) a gradient over the sorted values.

### `complement(seq)`

Everything (nodes if seq has nodes, edges if it has edges) not in seq.

### `condenseGraph()`

removeDisconnected, removeSelfLoops, then alternate removeLeaves and
shortcutNodes until nothing changes. Returns [removed, added].

### `copyNode(template, name, **extra)`

Create node `name` with all field values copied from `template`.

### `density()`

Edges divided by the number of possible undirected node pairs.

### `distance(node1, node2)`

Euclidean distance between two nodes' positions.

### `einverse(seq)`

All edges not in seq.

### `execfile(filename)`

Run a Gython script file in the current namespace.

### `exportCSV(filename='edges.csv', table='edges')`

exportCSV("edges.csv") writes the edge table (Source, Target, Type, Weight,
Label and edge fields); exportCSV("nodes.csv", "nodes") the node table.

### `exportGDF(filename)`

Write the graph to a GDF file (offered as a download in the browser).

### `exportGEXF(filename='graph.gexf')`

Write the graph as GEXF 1.3 for Gephi (offered as a download).

### `exportGraphML(filename)`

Write the graph as GraphML (offered as a download in the browser).

### `floatRange(a, b, inc)`

Like range() but for floats.

### `getEdgeSchema()`

The edge fields.

### `getNodeSchema()`

The node fields.

### `groupAndSortBy(*d)`

Like groupBy, with the groups ordered by value.

### `groupBy(*d)`

groupBy(field) or groupBy(seq, field): groups of elements sharing a value.

### `help(obj=None)`

help(command) shows documentation; help() lists commands.

### `hideDisconnected()`

Hide nodes with no edges other than self loops.

### `makeFromCSV(filename, nodes=None, directed=False)`

makeFromCSV("edges.csv") replaces the graph with a spreadsheet table as
Gephi reads it: an edge table (Source, Target[, Type, Weight, Label, ...]),
an adjacency matrix or an adjacency list. makeFromCSV("edges.csv",
"nodes.csv") also reads a node table (Id[, Label, ...]). Opening just a node
table adds its columns to the current graph's nodes (matched by Id).
Other columns become fields; directed=true makes edges without a Type
directed.

### `makeFromDL(filename)`

Replace the current graph with a UCINET DL file (fullmatrix, edgelist1, nodelist1).

### `makeFromGDF(filename)`

Replace the current graph with the contents of a GDF file.

### `makeFromGEXF(filename)`

Replace the current graph with a GEXF file (Gephi's format): attributes,
colours, positions, sizes, edge weights and thickness.

### `makeFromGML(filename)`

Replace the current graph with a GraphML file.

### `makeFromGraphML(filename)`

Replace the current graph with a GraphML file.

### `makeFromPajek(filename)`

Replace the current graph with a Pajek .net file (nodes are named pajek<id>).

### `ninverse(seq)`

All nodes not in seq.

### `remove(seq)`

Remove nodes and/or edges (a node takes its edges). Undo with add(...).

### `removeComplete(seq)`

Remove nodes and/or edges permanently (they cannot be re-added).

### `removeDisconnected()`

Remove (and return) nodes with no edges other than self loops.

### `removeEdge(e)`

Remove one edge.

### `removeLeaves()`

Repeatedly remove nodes of total degree <= 1. Returns what was removed.

### `removeNode(n)`

Remove one node and its edges (undo with add(g.deleted) or undo()).

### `removeSelfLoops()`

Remove (and return) all edges whose endpoints are the same node.

### `resizeLinear(field, start, end)`

Size nodes (or edge widths) by rank of field value, from start to end.

### `resizeRandom(field, start, end)`

Give each distinct value of field a random size (or edge width) between start and end.

### `shortcutNodes()`

Repeatedly replace degree-2 nodes by an edge between their neighbours.
Returns [removed, added].

### `sizeBy(field, smallest, largest, scale='linear')`

sizeBy(field, min, max) sizes nodes (or edge widths, for an edge field) in
proportion to a numeric field's value, from min to max. scale may be
"linear", "log", "sqrt" or "rank" (as in Gephi's ranking). Compare
resizeLinear, which spaces distinct values evenly.

### `skitter(field)`

Nodes around a circle ordered by field; radius shrinks with outdegree.

### `sortBy(*d)`

sortBy(field) or sortBy(seq, field).

## Undo, redo, history and logging

### `history()`

history() lists every command run this session, in order.

### `log(filename='session.py')`

Start recording every successful command (save with stoplog()).

### `redo()`

redo() re-applies the last command undone with undo().

### `saveHistory(filename='history.py')`

saveHistory("work.py") downloads every command run this session as a
script (run it again with execfile).

### `stoplog()`

Stop recording and save the log (offered as a download); replay with execfile.

### `undo()`

undo() reverses the most recent command that changed the graph, its
fields, states, hulls, legends or display settings (Ctrl/Cmd+Z outside
the code cell). Repeat to go further back (up to 50 steps); redo()
re-applies. Variables and downloaded files are not undone.

## Statistics, communities, filters and paths

### `averageClustering()`

The mean local clustering coefficient.

### `averagePathLength()`

Mean shortest-path length (hops, ignoring direction) over all connected pairs.

### `diameter()`

The longest shortest path (in hops, ignoring direction) between any two
connected nodes.

### `egoNetwork(center, depth=1)`

egoNetwork(node, depth=1): the node and everything within `depth` hops of
it (ignoring direction).

### `giantComponent()`

The nodes of the largest connected component (ignoring direction).

### `graphStats()`

Print a summary: size, density, degree, components, diameter, average
path length, clustering and (if computed) modularity.

### `groupsOfSize(field, smallest, largest=None)`

groupsOfSize(field, min[, max]): the nodes (or edges) whose value of
field is shared by at least min (and at most max) elements — e.g. drop
tiny communities with showOnly(groupsOfSize(modularity_class, 5)).

### `heatMap(center, near='red', far='lightgray', unreachable='white')`

heatMap(node) colours every node by its distance (hops, ignoring
direction) from node — near colour at the node, fading to far — and stores
the distance in the hops field (-1 if unreachable). Gephi's heat map tool.

### `interEdges(field)`

interEdges(field): edges joining nodes with different values of the field.

### `intraEdges(field)`

intraEdges(field): edges whose two endpoints share the field's value
(e.g. edges inside each community).

### `kCore(k)`

kCore(k): the nodes of the k-core — the largest subgraph in which every
node has at least k neighbours. E.g. showOnly(kCore(3)).

### `louvainClusters(resolution=1.0, seed=0)`

louvainClusters() finds communities by Louvain modularity optimisation
(Gephi's Modularity statistic) using edge weights, stores each node's
community in the modularity_class field (0 = largest) and returns the
communities. Try colorize(modularity_class). resolution > 1 gives more,
smaller communities; seed=None varies the result between runs.

### `modularity(field)`

modularity(field): the modularity Q of the partition given by a node
field (e.g. modularity(dept), modularity(modularity_class)).

### `mutualEdges()`

Directed edges whose reverse edge also exists.

### `paint(center, color, depth=0)`

paint(node, color, depth=0) colours a node, and with depth=k everything
within k hops of it (Gephi's brush).

### `radius()`

The smallest eccentricity among nodes with at least one neighbour.

### `recompute(*fields)`

recompute(pagerank, coreness, ...) recalculates computed fields (betweenness,
pagerank, closeness, ...) after the graph has changed; recompute() redoes
every computed field that has been used so far.

### `shortestPath(source, target, weighted=False)`

shortestPath(a, b): the nodes and edges of a shortest path from a to b
(following edge direction), or an empty set if there is none.
weighted=true uses edge weights as lengths. E.g. shortestPath(a, b).color = red

### `showAll()`

Make every node and edge visible again.

### `showOnly(seq)`

showOnly(seq) hides every node and edge not in seq (nodes in seq keep the
edges between them; edges in seq keep their endpoints). Undo with showAll().

## Clustering and generators

### `biComponentClusters()`

Biconnected components (ignoring edge direction).

### `edgeBetweennessClusters(count)`

Split the graph into `count` communities with Girvan-Newman.

### `makeBarabasiAlbertRandom(*args)`

makeBarabasiAlbertRandom(vert, edges, evolve): preferential attachment; starts from `vert` nodes and adds `evolve` nodes with `edges` edges each.

### `makeEppsteinRandom(*args)`

makeEppsteinRandom(nodes, edges, r): power-law graph by r rounds of degree-biased rewiring of a uniform random graph (Eppstein & Wang).

### `makeErdosRenyiRandom(*args)`

makeErdosRenyiRandom(nodes, p): each edge present with probability p.

### `makeKleinbergRandom(*args)`

makeKleinbergRandom(size, clust): Kleinberg small world on a size x size torus with one long-range edge per node, distance exponent clust.

### `makeLattice1DRandom(*args)`

makeLattice1DRandom(nodes, toroidal): a path (or ring if toroidal).

### `makeLattice2DRandom(*args)`

makeLattice2DRandom(size, toroidal): a size x size grid (torus if toroidal).

### `makeSimpleDirectedRandom(*args)`

makeSimpleDirectedRandom(nodes, edges): uniform random directed graph.

### `makeSimpleRandom(*args)`

makeSimpleRandom(nodes, edges): uniform random undirected graph.

### `weakComponentClusters()`

Connected components (ignoring edge direction).

## Layouts

### `binPackLayout(rescale=True)`

binPackLayout() packs the connected components next to each other,
first rescaling them to similar densities; binPackLayout(false) packs
them without rescaling.

### `centerAfterLayout(state)`

centerAfterLayout(state): whether the view re-centres after each layout
(default true). Disable it to control the view yourself.

### `circleLayout(field=None, center=None, x=None, y=None)`

circleLayout() places all nodes evenly on a circle (radius 450 around 500,500).

circleLayout(field, centerNode) puts centerNode at (500, 500) and its
neighbours on a circle around it, ordered by `field`, at a radius
proportional to `field` (a node field of the neighbours, or an edge
field of the connecting edges). Other nodes are left alone.
circleLayout(field, centerNode, x, y) uses (x, y) as the centre.

### `dagLayout()`

dagLayout() lays out a directed acyclic graph with a spring layout,
keeping each node on a horizontal line for its level (sources at the
top), for 500 iterations (fewer on graphs over 1000 nodes). Cycles are
broken first.

### `forceAtlas2Layout(iterations=None, scaling=None, gravity=1.0, strongGravity=False, linLog=False, dissuadeHubs=False, preventOverlap=False, edgeWeightInfluence=1.0)`

forceAtlas2Layout() runs Gephi's ForceAtlas2 from the current positions
(animated; Stop ends it early). Options, by keyword:
  iterations           steps to run (default 500, fewer on big graphs)
  scaling              repulsion strength (default 2, or 10 under 100 nodes)
  gravity              pull toward the centre (default 1)
  strongGravity=true   gravity grows with distance (keeps components close)
  linLog=true          LinLog mode: tighter, more separated clusters
  dissuadeHubs=true    pushes hubs to the periphery (authorities central)
  preventOverlap=true  keep node discs apart (best run after a first pass)
  edgeWeightInfluence  0 ignores weights, 1 uses them, >1 exaggerates
E.g. forceAtlas2Layout(linLog=true, preventOverlap=true)

### `frLayout(width=None, height=None)`

frLayout() runs Fruchterman-Rheingold (as in Pajek) starting from the
current positions and fits the result into a 1000 x 1000 grid with cells
the size of the largest node; frLayout(width, height) uses that area.

### `gemLayout(seed=None)`

gemLayout() runs the GEM force-directed layout (Frick et al.);
gemLayout(seed) seeds the random generator for a repeatable layout.

### `isomLayout(max=None)`

isomLayout() runs the JUNG ISOM (self-organising map) layout for 2000
epochs; isomLayout(n) runs n epochs.

### `jfrLayout()`

jfrLayout() runs the JUNG Fruchterman-Rheingold layout (random start in
a 1000 x 1000 area, up to 700 cooling iterations).

### `jkkLayout1()`

jkkLayout1() runs the JUNG Kamada-Kawai layout: unweighted graph
distances, random start, 2000 iterations each moving the worst-placed
node.

### `jkkLayout2()`

jkkLayout2() runs the JUNG Kamada-Kawai layout with integer distances
(same algorithm as jkkLayout1).

### `jSpringLayout(max=None)`

jSpringLayout() runs the JUNG spring layout from random positions until
it settles or for 500 iterations (fewer on graphs over 1000 nodes);
jSpringLayout(n) runs exactly n iterations.

### `kkLayout(width=None, height=None)`

kkLayout() runs Kamada-Kawai on each connected component, starting from
a circle, then fits the result into 1000 x 1000; kkLayout(width, height)
uses that area instead.

### `mdsLayout()`

mdsLayout() places nodes by classical multidimensional scaling of the
edge weights (an edge's weight is the distance between its endpoints,
every other pair is at distance 1). Nodes without edges are not moved.

### `mirrorLayout(horizontal=True)`

mirrorLayout() flips the layout left-right; mirrorLayout(false) flips it
upside down.

### `moveLayout(newX, newY)`

moveLayout(x, y) moves the layout so its top-left corner is at (x, y).

### `noverlapLayout(margin=5, ratio=1.2)`

noverlapLayout() nudges nodes apart until none overlap (Gephi's Noverlap):
each node is treated as a disc of ratio x its size plus margin.

### `physicsLayout(max=None)`

physicsLayout() runs the graphopt physics layout (charged nodes, springs)
for 500 steps from the current positions (fewer on graphs over 1000
nodes); physicsLayout(n) runs n steps.

### `radialLayout(center, edges=None)`

radialLayout(centerNode) lays the graph out as a radial tree around
centerNode (placed at 0,0), following a breadth-first spanning tree
(Eades' radial drawing). Nodes not reachable from the centre stay put.
radialLayout(centerNode, edges) restricts the tree to the given edges.

### `randomLayout(width=None, height=None)`

randomLayout() places nodes at random in a 1000 x 1000 area;
randomLayout(width, height) uses a width x height area.

### `rescaleLayout(*d)`

rescaleLayout(percent) scales the layout by percent (0.5 = half size)
about its top-left corner; rescaleLayout(xpercent, ypercent) scales each
axis separately; rescaleLayout(width, height) with integers fits the
layout into a width x height box at the origin.

### `rotateLayout(degrees=90)`

rotateLayout(degrees) turns the layout clockwise about its centre.

### `springLayout(max=None)`

springLayout() runs the GUESS spring layout from the current positions
until it settles or for 1000 iterations (fewer on graphs over 1000
nodes: 1000 * 1000 / nodes, at least 100); springLayout(n) runs exactly
n iterations. Stop it early with the Stop button.

### `sugiyamaLayout(bends=False)`

sugiyamaLayout() draws the graph in layers (Sugiyama): edges are made
acyclic, nodes put on levels so every edge points down, crossings reduced
by barycentres, on a 250 x 150 grid. sugiyamaLayout(true) also routes
long edges through dummy positions.

### `sugiyamaLayout2()`

sugiyamaLayout2() is a simpler layered layout: levels 200 apart, each
node given horizontal room in proportion to its children.

### `translateLayout(newX, newY)`

translateLayout(dx, dy) moves every node by (dx, dy).

### `weightedKKLayout()`

weightedKKLayout() runs the JUNG Kamada-Kawai layout using shortest
paths where each edge's `weight` is its length.

### `weightedSpringLayout(minLength, maxLength, max=None)`

weightedSpringLayout(minLength, maxLength[, iterations]) is springLayout
with each edge's natural length mapped linearly from its `weight`
(lowest weight -> minLength, highest -> maxLength). Iterations as for
springLayout.

## Display: hulls, legends, background, edges, labels, selection, export

### `createConvexHull(seq, color='200,200,255,90')`

Shade the convex hull around the nodes in seq (edges contribute their endpoints).

### `curvedEdges(on=True)`

curvedEdges() draws every edge as a circular arc running clockwise from
source to target, as in Gephi's preview, so a->b and b->a separate and
direction reads without arrows. curvedEdges(false) goes back to straight
lines; curvedEdges(k) sets the curvature: the arc radius is edge length / k
(default 1.2, as in Gephi; 2 gives semicircles).

### `exportJPG(filename='guess.jpg')`

Save the display as JPG (downloaded by the browser).

### `exportPNG(filename='guess.png')`

Save the display as PNG (downloaded by the browser).

### `exportSVG(filename='guess.svg')`

Save the display as SVG (downloaded by the browser). Vector: the whole graph, not just the visible area.

### `getConvexHulls()`

All hulls currently shown.

### `getDisplayBackground()`

The display background color, or None when it follows the light/dark theme.

### `GradientLegend(start, end, lo=0, hi=1)`

A color ramp legend: GradientLegend(startColor, endColor, min, max).

### `hideOverlappingLabels(on=True)`

hideOverlappingLabels() hides labels that would overlap a label of a
bigger node, rechecked as you zoom; hideOverlappingLabels(false) shows all.

### `labelOutlines(on=True)`

labelOutlines() draws a halo in the background colour around labels so
they stay readable over edges; labelOutlines(false) turns it off.

### `Legend()`

A legend box on the display. ``l = Legend(); l.add(bob, "managers")``.

Entries snapshot the look of the node, edge or hull at the time they are added.

### `overrideArrowLength(length)`

Fix the arrowhead length (graph units) for all directed edges; None resets.

### `overrideArrowWidth(width)`

Fix the arrowhead width (graph units) for all directed edges; None resets.

### `removeBackgroundImage()`

Remove the background image set with setBackgroundImage.

### `removeConvexHull(hull)`

Remove one hull.

### `removeConvexHulls(seq=None)`

Remove the given hulls, or all hulls.

### `select(seq=None)`

select(seq) selects these nodes on the display (edges select their
endpoints) and binds them to `sel`, as a box, lasso or shift-click does;
select() clears the selection. On the display: shift-drag draws a box,
alt-drag a lasso, shift-click adds or removes one node.

### `setBackgroundImage(source, x=0, y=0)`

Show an image (a file you opened, or a URL) behind the graph with its
top-left corner at (x, y) in graph coordinates.

### `setDisplayBackground(color)`

Set the display's background color; setDisplayBackground(None) goes back
to the theme's (white, or dark in dark mode).

### `setEdgeColorMode(mode='original')`

setEdgeColorMode("mixed") draws each edge in the blend of its endpoints'
colours; "source" / "target" use one endpoint's colour; "original" (the
default) uses the edge's own color field. As in Gephi's preview.

### `startMovie(fps=30, filename='guess.webm')`

Record the display (graph canvas) as a WebM video until stopMovie().
Everything shown — layouts, morphs, edits, panning — is captured.

### `stopMovie()`

Stop recording and download the video.

## States and morphing

### `getEdgeAppearAfter()`

The current edgeAppearAfter fraction (see setEdgeAppearAfter).

### `getEdgeDisappearBy()`

The current edgeDisappearBy fraction (see setEdgeDisappearBy).

### `getNodeAppearAfter()`

The current nodeAppearAfter fraction (see setNodeAppearAfter).

### `getNodeDisappearBy()`

The current nodeDisappearBy fraction (see setNodeDisappearBy).

### `getStates()`

Names of the saved states.

### `ls(state)`

Load a saved state: restores which nodes/edges exist and all their values.

### `morph(state, duration=1000)`

Animate from the current display to a saved state over `duration` ms.

### `setEdgeAppearAfter(v)`

Fraction (0..1) of a morph by which edgeAppearAfter takes effect.

### `setEdgeDisappearBy(v)`

Fraction (0..1) of a morph by which edgeDisappearBy takes effect.

### `setNodeAppearAfter(v)`

Fraction (0..1) of a morph by which nodeAppearAfter takes effect.

### `setNodeDisappearBy(v)`

Fraction (0..1) of a morph by which nodeDisappearBy takes effect.

### `ss(state)`

Save the current graph (membership and all field values) as a named state.

## Ranges (existence intervals)

### `addRange(obj, spec)`

Attach an existence range like "1,5-10,20" to nodes/edges (adds to any existing range).

### `getRange(obj)`

The range of a node or edge as a string.

### `searchContained(spec)`

Nodes and edges whose range lies inside the given range.

### `searchContains(spec)`

Nodes and edges whose range contains the given range.

### `searchExact(spec)`

Nodes and edges whose range equals the given range.

### `searchOverlap(spec)`

Nodes and edges whose range overlaps the given range.

## Charts

### `plotDistrib(field, sortField=None)`

Each element's value of field, in rank order (or ordered by sortField).

### `plotHistogram(field, bins=10)`

Histogram of a numeric field's values in `bins` equal-width bins.

### `plotSizes(field)`

Bar chart of how many elements share each value of field (largest first).

### `plotSizesPie(field)`

Pie chart of how many elements share each value of field.

## Interface building (panels, widgets, timers, events)

### `after(seconds, fn)`

Call fn() once after `seconds` seconds; returns a timer with .stop().

### `Button(*a, **k)`

Button(text, onClick=fn): calls fn() when clicked; .enabled turns it on/off.

### `Checkbox(*a, **k)`

Checkbox(text, checked=False, onChange=fn): calls fn(checked) when toggled.

### `Dropdown(*a, **k)`

Dropdown(options, value=None, label="", onChange=fn): a choice list; calls
fn(value) when the selection changes.

### `every(seconds, fn)`

Call fn() every `seconds` seconds; returns a timer with .stop().

### `Label(*a, **k)`

Label(text): a line of text in a panel; set .text to change it.

### `openURL(url)`

Open a web page in a new browser tab.

### `Panel(*a, **k)`

Panel(title, *widgets, position="bottom", vertical=False). Show with ui.dock(p).

### `Slider(*a, **k)`

Slider(min, max, value=None, step=1, label="", onChange=None, onSlide=None).
onChange fires on release, onSlide while dragging.

### `stopTimers()`

Stop all timers.

### `TextField(*a, **k)`

TextField(value="", placeholder="", onEnter=None): onEnter(text) on Return.

## Sessions and apps

### `exportApp(filename='app.guess', script=None)`

Save a session that opens as an app: with ?app=1 the console is hidden
and `script` (Gython source, or the name of a .py file) runs on load —
e.g. to dock panels and set graphevents handlers.

### `makeFromSession(filename)`

Load a .guess session file, replacing the current graph.

### `saveSession(filename='session.guess')`

Save the graph, fields, states, hulls, legends and view to a .guess file
(downloaded by the browser). User variables are not saved.

## SQL

### `sql(query)`

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

## Colors

### `averageColor(c1, c2)`

The color halfway between two colors.

### `distinctColors(n, seed=1)`

distinctColors(n): n clearly different colours (as "r,g,b" strings), the
most different first — the categorical palette colorize(field) uses.

### `generateColors(*args)`

generateColors(start, end, n) or generateColors(start, middle, end, n).

### `randomColor(alpha=None)`

A random color "r,g,b"; randomColor(alpha) adds an alpha (0..255).

## Fields

Built-in node fields:

| field | type | default |
|---|---|---|
| `name` | VARCHAR | None (read-only) |
| `x` | DOUBLE | 500.0 |
| `y` | DOUBLE | 500.0 |
| `visible` | BOOLEAN | True |
| `color` | VARCHAR | 'cornflowerblue' |
| `strokecolor` | VARCHAR | None |
| `labelcolor` | VARCHAR | None |
| `fixed` | BOOLEAN | False |
| `style` | INTEGER | 2 |
| `width` | DOUBLE | 10.0 |
| `height` | DOUBLE | 10.0 |
| `label` | VARCHAR | None |
| `image` | VARCHAR | None |
| `labelvisible` | BOOLEAN | False |
| `indegree` | INTEGER | 0 (read-only) |
| `outdegree` | INTEGER | 0 (read-only) |
| `totaldegree` | INTEGER | 0 (read-only) |

Built-in edge fields:

| field | type | default |
|---|---|---|
| `node1` | VARCHAR | None (read-only) |
| `node2` | VARCHAR | None (read-only) |
| `directed` | BOOLEAN | False (read-only) |
| `color` | VARCHAR | 'dandelion' |
| `labelcolor` | VARCHAR | None |
| `visible` | BOOLEAN | True |
| `width` | DOUBLE | 2.0 |
| `weight` | DOUBLE | 1.0 |
| `label` | VARCHAR | None |
| `labelvisible` | BOOLEAN | False |

Computed node fields (calculated the first time they are used, by name or
as `n.<field>`; `recompute()` after editing the graph): `pagerank`, `hub`, `authority`, `eigenvector`, `closeness`, `harmonic`, `eccentricity`, `clustering`, `triangles`, `coreness`, `strength`, `component`, `strongcomponent`, `betweenness`; edge field `betweenness`.

## Gython syntax

Gython is Python 3 plus these graph operators (see the CHI 2006 paper):

| expression | meaning |
|---|---|
| `freq > 10` | elements whose field matches (`==`, `!=`, `<`, `>`, `<=`, `>=`, `like`) |
| `(freq > 10).color = blue` | setting a field on a set sets it on every element |
| `a & b`, `a \| b` | intersection / union of element sets |
| `a -> b`, `a <- b` | directed edges from a to b / from b to a |
| `a <-> b`, `a - b` | undirected edges between a and b |
| `a ? b` | any edges between a and b |
| `s.difference(t)` | set difference |
| `bob[1999].color` | a value in a saved state |
| `Node rcontains 5` | range queries (`rcontains`, `roverlaps`, `rcontained`) |
| `g.nodes`, `g.edges` | all nodes / edges |
| `sel` | the current display selection |
