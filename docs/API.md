# Gython API reference

Generated from the docstrings by `py/tools/gen_api_docs.py`; do not edit by hand.
In the console, `help(name)` shows the same text, and hovering a command name
in an executed cell shows it as a tooltip.

Commands can be called without parentheses when they take no arguments
(`gemLayout` is `gemLayout()`). Colors are names (`red`), `"r,g,b[,a]"` or `"#rrggbb"`.

## Contents

- [Graph structure, loading and saving, mapping, view](#graph-structure-loading-and-saving-mapping-view) (115)
- [Undo, redo, history and logging](#undo-redo-history-and-logging) (6)
- [Statistics, communities, filters and paths](#statistics-communities-filters-and-paths) (21)
- [Clustering and generators](#clustering-and-generators) (11)
- [More measures: Katz, prestige, bridging, cliques, MDS, k-brace; field tools and generators](#more-measures-katz-prestige-bridging-cliques-mds-k-brace;-field-tools-and-generators) (13)
- [More clustering: Chinese Whispers, MCL, DBSCAN, MCODE, overlapping communities](#more-clustering-chinese-whispers-mcl-dbscan-mcode-overlapping-communities) (7)
- [Structure: bridges, cut nodes, backbones, directed graphs, mixing, comparing partitions](#structure-bridges-cut-nodes-backbones-directed-graphs-mixing-comparing-partitions) (16)
- [networkx bridge and sample graphs](#networkx-bridge-and-sample-graphs) (4)
- [igraph: communities, large-graph layouts, similarity, patterns, cuts and flows](#igraph-communities-large-graph-layouts-similarity-patterns-cuts-and-flows) (29)
- [Graphviz layouts: dot, neato, sfdp, fdp, circo, twopi, osage; overlap removal](#graphviz-layouts-dot-neato-sfdp-fdp-circo-twopi-osage;-overlap-removal) (9)
- [Layouts](#layouts) (33)
- [Structure-aware layout (motifLayout, after LUMINA)](#structure-aware-layout-motiflayout-after-lumina) (1)
- [More layouts: multipartite, concentric, ordered, circle packing, isometric layers](#more-layouts-multipartite-concentric-ordered-circle-packing-isometric-layers) (7)
- [Display: hulls, legends, background, edges, labels, selection, export](#display-hulls-legends-background-edges-labels-selection-export) (45)
- [Styles and visual mappings](#styles-and-visual-mappings) (14)
- [Pie nodes, borders and edge bundling](#pie-nodes-borders-and-edge-bundling) (6)
- [Grouping: collapse and expand](#grouping-collapse-and-expand) (5)
- [Several graphs: subgraphs and tabs](#several-graphs-subgraphs-and-tabs) (7)
- [Time: ranges, years and the timeline](#time-ranges-years-and-the-timeline) (1)
- [Presentations (slides)](#presentations-slides) (6)
- [Data from the web: URLs, SPARQL, NDEx, Neo4j, packages](#data-from-the-web-urls-sparql-ndex-neo4j-packages) (10)
- [Standalone web pages (exportHTML)](#standalone-web-pages-exporthtml) (1)
- [Live graph streams (Gephi streaming protocol)](#live-graph-streams-gephi-streaming-protocol) (2)
- [AI assistants (MCP bridge)](#ai-assistants-mcp-bridge) (2)
- [Cytoscape formats: SIF, NNF, Cytoscape.js JSON, CX/CX2, XGMML, .cys sessions](#cytoscape-formats-sif-nnf-cytoscape.js-json-cx/cx2-xgmml-.cys-sessions) (7)
- [Biology formats: PSI-MI (MITAB, XML), SBML, BioPAX, KEGG KGML, WikiPathways GPML](#biology-formats-psi-mi-mitab-xml-sbml-biopax-kegg-kgml-wikipathways-gpml) (7)
- [Import and export: Excel, RDF, Bluesky, JSON, KML, shapefiles, standalone HTML](#import-and-export-excel-rdf-bluesky-json-kml-shapefiles-standalone-html) (7)
- [States and morphing](#states-and-morphing) (13)
- [Ranges (existence intervals)](#ranges-existence-intervals) (6)
- [Charts](#charts) (9)
- [Interface building (panels, widgets, timers, events)](#interface-building-panels-widgets-timers-events) (25)
- [Sessions and apps](#sessions-and-apps) (3)
- [SQL](#sql) (1)
- [Colors](#colors) (4)
- [Examples](#examples)
- [Fields](#fields)
- [Gython syntax](#gython-syntax)

## Graph structure, loading and saving, mapping, view

### `add(seq)`

Re-add removed nodes/edges, e.g. add(g.deleted).

### `addDirectedEdge(node1, node2, **attrs)`

Add a directed edge from node1 to node2.

### `addEdge(node1, node2, **attrs)`

Add an undirected edge.

### `addEdgeField(name, type='VARCHAR', default=None)`

Create an edge field, e.g. addEdgeField("kind", VARCHAR, "").

### `addNode(name, **attrs)`

Add a node (or return the existing one with that name). addNode(vx)
with a removed node puts it back, with its field values.

### `addNodeField(name, type='VARCHAR', default=None)`

Create a node field, e.g. addNodeField("score", DOUBLE, 0).

### `addUndirectedEdge(node1, node2, **attrs)`

Add an undirected edge between two nodes (by node or name).

### `averageEdgeColor(edges=None)`

Color edges the average of their endpoint colors (all edges by default).

### `bowTie(name='bowtie')`

bowTie() splits a directed network the way the Web was described in
2000: the largest strongly connected component ("core"), the nodes that
can reach it but not be reached from it ("in"), those reached from it
that can't reach back ("out"), "tube" nodes on paths from in to out that
bypass the core, "tendril" nodes hanging off in or out, and "other"
for nodes outside the core's weakly connected component. Sets the node
field `bowtie` and returns the sizes, e.g. {"core": 224, "in": 89, ...}.
Undirected edges count both ways.

### `center(*d)`

center() fits the whole graph; center(seq) zooms to the given elements.

### `collapseMotifs(kind='fan', smallest=3)`

collapseMotifs("fan") collapses every motif found by findMotifs into
one meta-node (labelled with the kind and its size), which simplifies
the drawing without losing anything: expand(node) or expandAll() bring
the members back. Returns the meta-nodes.

### `colorBy(field, start, end, scale='linear', middle=None, center=None)`

colorBy(field, startColor, endColor) colours elements along a gradient in
proportion to a numeric field's value; scale may be "linear", "log",
"sqrt" or "rank"; middle=color adds a midpoint colour. center=value
makes a diverging gradient: that value gets the middle colour (white
unless given) and the ends are equally far from it, so equal changes
up and down look equally strong, e.g. colorBy(lfc, blue, red,
center=0) for fold changes. Compare colorize, which spaces distinct
values evenly.

### `colorGraph(strategy='DSATUR', show=True)`

colorGraph() gives every node a colour class (`color_class`, 0, 1,
2, ...) so that no two neighbours share one, using as few as it can
find (greedy colouring; strategy "DSATUR" (default),
"largest_first", "smallest_last" or "random_sequential"); show=true
also colours the nodes by class. Returns the number of colours used.
Planar networks (maps) never need more than four, though greedy
methods sometimes use five.

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

### `demo(step=1)`

demo() starts a guided tour of GUESS for newcomers, from selecting
nodes to communities, what-if analysis, Altair charts, a contagion model
and a small app. Each step explains an idea and runs its code as a
normal console cell. demo(9) starts at step 9; demo("advanced") at the
first step of that level (basic, intermediate, advanced).

### `density()`

Edges divided by the number of possible undirected node pairs.

### `distance(node1, node2)`

Euclidean distance between two nodes' positions.

### `edgeCrossings(pairs=False)`

edgeCrossings() counts the pairs of edges that cross in the current
drawing (straight edges between node centres; edges sharing a node
don't count). pairs=true returns the crossing pairs instead, e.g.
for e1, e2 in edgeCrossings(pairs=true): e1.color = red. A planar
network can be drawn with no crossings; finding such a drawing is
another matter.

### `edgeData(*args)`

edgeData(field, ...) or edgeData(edges, field, ...): one row per edge
(`name` is "a-b"), with `_edge`, the edge's id, for linking.

### `effectiveDistance(origin, weight='weight', name='eff_distance')`

effectiveDistance(origin) measures how 'close' every node is to the
origin through a travel network, as an epidemic would see it
(Brockmann and Helbing, Science 2013). From node m, the share of m's
traffic (weight) that goes to n is P; the step m -> n costs
1 - ln P, so busy routes are short and a route among many is long.
Stores the shortest total in `eff_distance` (name=...; unreachable
nodes get None) and marks the edges of the shortest-path tree in the
edge field `eff_tree`. Arrival times of real epidemics grow almost
linearly with it. Returns the field.

### `einverse(seq)`

All edges not in seq.

### `embed(dims=8, walks=10, length=40, window=5, p=1.0, q=1.0, seed=0, name='emb')`

embed(dims=8) gives every node coordinates in `dims` dimensions such
that nodes in similar network positions are close (node2vec, Grover
and Leskovec 2016): random walks from every node (`walks` of `length`
steps; p and q bias them towards returning or exploring), then a
factorisation of how often nodes co-occur within `window` steps. The
coordinates are stored in fields emb0, emb1, ... (name=...), ready for
scatterLayout(emb0, emb1), similarity searches or a classifier
(toNetworkX(), or export the table). Fine up to a few thousand nodes.

### `enrichment(seq, sets, background=None, top=10, minSize=2, show=True)`

enrichment(nodes, sets) tests which sets (from readSets, or any
{name: [node names]}) are over-represented among the nodes, against
the background (default: every node in the graph that is in at least
one set). For each set it gives the overlap k of n nodes, the set's
size K among the N background nodes, the fold enrichment
(k/n)/(K/N), the hypergeometric p-value and the Benjamini-Hochberg
q-value (the false discovery rate over all sets tested). Sets with
fewer than minSize background members are skipped. Prints the `top`
rows by p-value and returns all rows as dicts, best first.

### `execfile(filename)`

Run a Gython script file in the current namespace.

### `expandLayers(field, order=None, directed=False, name='layers')`

expandLayers(kind) turns a multiplex network (one set of nodes,
several kinds of edge, told apart by the edge field `kind`) into a
multilayer one in a new graph tab: a copy of every node in each layer
it has edges in, the layer's edges between the copies, and
"interlayer" edges joining each node's copies in consecutive layers
(order= a list of the layer values; default sorted). directed=true
points the interlayer edges forward, as for time: a temporal network
where nothing travels back in time. Copies keep the node's position
and get `layer` and `original`; run isometricLayout(layer) to stack
the layers. use() goes back to the original.

### `exportCSV(filename='edges.csv', table='edges')`

exportCSV("edges.csv") writes the edge table (Source, Target, Type, Weight,
Label and edge fields); exportCSV("nodes.csv", "nodes") the node table.

### `exportDOT(filename='graph.dot', clusters='cluster', layout=True)`

exportDOT("graph.dot") writes the graph for Graphviz: positions (fixed
nodes pinned with !), sizes, shapes, colours, labels, hidden elements and
every user field; nodes are grouped into cluster subgraphs by the field
named by clusters= (default `cluster`, e.g. clusters="louvain_class").
layout=False leaves positions out so Graphviz lays the graph out itself.
makeFromDOT reads it back. Offered as a download.

### `exportGDF(filename)`

Write the graph to a GDF file (offered as a download in the browser).

### `exportGEXF(filename='graph.gexf')`

Write the graph as GEXF 1.3 for Gephi (offered as a download).

### `exportGML(filename)`

Write the graph as GML (networkx, igraph, yEd, Cytoscape and Gephi read
it): fields, positions, colours and sizes. Offered as a download.

### `exportGraphML(filename)`

Write the graph as GraphML (offered as a download in the browser).

### `extinctions(orders=('random', 'degree'), trials=10, seed=0, show=True)`

extinctions() simulates species loss in a food web: species are
removed one at a time ("primary" extinctions) and any species left
with nothing to eat dies out too ("secondary" extinctions; species
that eat nothing in the web, the basal ones, never starve). orders:
"random" (averaged over `trials`), "degree" (most connected first),
"least" (least connected first), "basal" (producers first) or a node
field (highest first). Plots the share of species surviving against
the share removed, and prints R50, the share of primary removals
that brings total losses to half the species (higher = more robust).
The graph isn't changed. Returns {order: [(removed, surviving)...]}.

### `findCycles(maxLength=5, among=None, limit=1000)`

findCycles(maxLength=5) finds directed cycles (A -> B -> ... -> A)
of up to maxLength nodes, e.g. money sent round a ring of accounts
back to where it started. among=nodes restricts the search. Each
cycle is a set of its nodes and edges (shortest first); at most
`limit` are returned. Undirected edges count both ways.

### `findDuplicates(field=None, threshold=0.85, among=None, top=50, show=True)`

findDuplicates(name) lists pairs of nodes whose values of a text
field look like the same entity: compared after normalising (case,
accents, punctuation, word order, company suffixes and titles like
Ltd, Inc, Mr), scored 0..1 by string similarity, best first, at least
`threshold`. among=nodes restricts the search (e.g. one kind of
entity). Default field: label. Returns (node, node, score) for review
and mergeNodes; it never merges anything itself.

### `findEdges(seq)`

The edges among the members of a (possibly mixed) set.

### `findMotifs(kind='fan', smallest=3, show=True)`

findMotifs("fan") finds NodeXL-style motifs, the small repeated
shapes that clutter big drawings:
  "fan"        several leaves (nodes with one neighbour) on the same node
  "connector"  several nodes linked to exactly the same 2-4 others and
               nothing else (e.g. people who all know the same two)
  "clique"     groups where everyone is linked to everyone (each node
               in at most one, largest first)
with at least `smallest` members. Returns the groups (members only);
collapseMotifs(kind) replaces each with one meta-node.

### `findNodes(seq)`

The nodes among the members of a (possibly mixed) set.

### `fitNodesToLabels(seq=None, padding=4)`

fitNodesToLabels() puts each node's label inside it (labelpos =
"inside") and resizes the node to fit the label, as in a flowchart or a
Graphviz drawing; fitNodesToLabels(dept == 'dept3') does some nodes.
padding is the space around the text. Labels with line breaks
(`\n`) make taller nodes.

### `fitPowerLaw(field='degree', kmin=None, shift=0)`

fitPowerLaw(degree) fits a power law p(k) ~ k^-alpha to the values
of a numeric node field (or a list of numbers) from kmin up, by maximum likelihood (Newman,
Networks, eq. 10.9, with the -1/2 correction for whole numbers), not
by drawing a line through a log-log plot. With kmin left out it is
chosen as the value that makes the fitted distribution closest to the
data (the smallest Kolmogorov-Smirnov distance; Clauset, Shalizi and
Newman 2009). Returns {"alpha", "sigma" (its standard error), "kmin",
"n" (values in the tail), "ks"}. shift=a fits a power law in k + a
rather than k, as Price's model gives (p_k ~ (k + a)^-alpha); kmin and
the returned kmin stay in units of k. plotFrequency(degree, cumulative=true,
log=true, fit=true) draws the fit.

### `floatRange(a, b, inc)`

Like range() but for floats.

### `geoDistance(name='km', lat=None, lon=None)`

geoDistance() stores each edge's great-circle length in kilometres
(from its ends' latitude and longitude fields, as geoLayout finds them)
in the edge field `km` (or name=...). Use it as a cost:
for e in g.edges: e.weight = e.km, then shortestPath(a, b,
weighted=true) is the shortest route by distance. Returns the field.

### `geoLayout(lat=None, lon=None, projection='mercator', map='auto', width=1000, land=None, borders=None, parallels=(29.5, 45.5), center=(-96.0, 37.5))`

geoLayout() places nodes by their latitude and longitude fields
(found by name: latitude/lat and longitude/lon/lng, or pass them:
geoLayout(lat, lon)) and draws a map underneath. projection:
"mercator" (default; shapes kept, high latitudes enlarged),
"equirectangular" (longitude and latitude as x and y) or "albers"
(equal-area conic; with parallels= and center=, US by default, which
suits the lower 48 states). map: "world" (land outlines), "usa" (the
states), None for no map, or "auto" (usa when every node is in the
US, else world). land= and borders= set the map's colours (default:
light or dark grey to suit the theme). The layout fits nodes into
`width` units across; nodes without coordinates are set in a row
below. Outlines: Natural Earth 1:110m, public domain.

### `getEdgeSchema()`

The edge fields.

### `getNodeSchema()`

The node fields.

### `groupAndSortBy(*d)`

Like groupBy, with the groups ordered by value.

### `groupBy(*d)`

groupBy(field) or groupBy(seq, field): groups of elements sharing a value.

### `groupStats(field, top=12, show=True)`

groupStats(louvain_class) profiles each group of nodes sharing a
value of a field: size, internal edges, density (internal edges /
possible pairs), boundary edges (to the rest), conductance (boundary
/ all edges touching the group: low = well separated), and the
group's most connected member. Prints the largest `top` groups and
returns a row per group, largest first; a dense, isolated group of
entities that should be unrelated is a classic red flag.

### `help(obj=None)`

help() opens the help browser (searchable commands and examples; also
F1 or Cmd/Ctrl+K for the command palette); help(command) prints that
command's documentation and shows it in the browser.

### `hideDisconnected()`

Hide nodes with no edges other than self loops.

### `highest(field, count=10, seq=None)`

highest(degree) is the 10 nodes (or edges) with the largest degree,
largest first; highest(degree, 5), or highest(degree, 5, seq) within a
set. Elements without a value are left out.

### `katzCentrality(alpha=None, beta=1.0, name='katz')`

katzCentrality(alpha, beta) gives each node x = alpha A x + beta: the
importance its in-neighbours pass on (scaled by alpha) plus a free amount
beta, so even nodes no one points to count. alpha must be below 1/kappa1
(the largest eigenvalue of A; returned along with the field) for the
sum to converge; small alpha ranks nodes almost by degree, alpha near
1/kappa1 almost like eigenvector centrality. With alpha left out it is
0.85/kappa1. Edges follow their direction (undirected ones both ways).
Stores the values in the field `name` (default "katz") and returns
(field, 1/kappa1).

### `kComponents(k=2, name='kcomponent')`

kComponents(k) finds the k-components: the largest groups of nodes in
which every pair is joined by at least k node-independent paths (k = 1:
components; 2: bicomponents; 3: tricomponents). Unlike k-cores they need
the paths, not just the degrees. Returns them as sets, largest first, and
stores each node's (first) one in the field `name` (-1 for none); a node
can belong to more than one, e.g. a cut node shared by two bicomponents.
Direction is ignored. Exact for k <= 2; for k >= 3 uses networkx's
k_components (Moody and White), which can be slow on big graphs.

### `labelCluster(nodes, value, field='cluster', relabel=True)`

labelCluster(nodes, value, field="cluster") puts `value` in `field` for
each of the nodes (a set, or a list of node names), making the field if
needed: INTEGER for a number, VARCHAR for text; nodes not labelled hold
None. relabel=False leaves nodes that already have a value alone. The
Cluster tool writes one of these per selection. Returns the nodes labelled.

### `labelSizeBy(field, smallest=0.8, largest=2.0, scale='linear')`

labelSizeBy(field, 0.8, 2) scales labels (of nodes, or of edges for an
edge field) in proportion to a numeric field: 1 is the normal size. Sets
the labelsize field; scale as in sizeBy ("linear", "log", "sqrt", "rank").

### `lastClick()`

lastClick() is where the display was last clicked, as (x, y) in graph
coordinates, or None before the first click.

### `lombardiEdges(iterations=300, limit=70)`

lombardiEdges() turns the edges into circular arcs, without moving
any node, so that each node's edges leave it as evenly spread as
possible (a "near-Lombardi" drawing, after the artist Mark Lombardi;
Chernobelskiy et al., GD 2011). Each edge's bend is the angle, in
degrees, at which it leaves its ends, stored in its `arc` field (0 =
straight; at most `limit`). Returns lombardiness() before and after.
straightenEdges() undoes it.

### `lombardiLayout(iterations=400, seed=0)`

lombardiLayout() makes a Lombardi-style drawing: circular-arc edges,
with each node's edges leaving it at (nearly) equal angles. It is the
tangent-based spring embedder of Chernobelskiy et al. (GD 2011):
attraction (d - k)/d along edges and repulsion k^2/d^3 between all
pairs place the nodes, while a tangential force turns each edge's
chord so that the angles both ends want for it agree, and each
node's fan of edge tangents turns to fit; edges then get the arc
that matches (stored in `arc`, as by lombardiEdges). Returns
lombardiness() of the straight-line drawing it starts from and of
the result. Best for small and medium graphs (up to a few hundred
nodes).

### `lombardiness()`

lombardiness() scores how close the drawing is to a Lombardi drawing,
0-100: 100 when every node's edges leave it at equal angles (as
measured by their tangents, so arcs count; see lombardiEdges). Nodes
with one edge are always perfect (Chernobelskiy et al., GD 2011).

### `lowest(field, count=10, seq=None)`

lowest(degree, 5): the 5 with the smallest degree, smallest first
(see highest).

### `makeBlockModel(sizes, p_in, p_out=None, seed=0, layout=True)`

makeBlockModel([30, 30, 40], 0.3, 0.02) makes a stochastic block model:
nodes in groups of the given sizes, each pair inside a group joined with
probability p_in and each pair in different groups with p_out, so the
network has community structure (Newman, Networks, section 12.11.6).
p_in can instead be a matrix of probabilities between groups. The node
field `block` gives each node's group (0, 1, ...).

### `makeConfigurationModel(degrees, simple=False, seed=0, layout=True)`

makeConfigurationModel([3, 2, 2, 1, ...]) replaces the graph with a
random network with exactly those degrees: each node gets that many
"stubs" (half-edges) and the stubs are paired up uniformly at random
(Newman, Networks, section 12.1). Some pairs make self-loops or join
nodes already joined; simple=true deletes those afterwards (so some
degrees come out lower). degrees can be a node field of the current
graph, e.g. makeConfigurationModel(degree), which randomises a network
keeping its degrees. The node field `stubs` keeps each node's intended
degree. The degrees must add up to an even number. Returns the counts of
self-loops and repeated edges. layout=false skips the force-directed
layout (for when you lay it out yourself). (GUESS's degree field counts a self-loop
once; in the book's convention it adds 2 to the degree, which is what
`stubs` holds.)

### `makeExpectedDegree(weights, seed=0, layout=True)`

makeExpectedDegree([5.5, 3, 1.2, ...]) replaces the graph with a random
network in which each pair i, j is joined independently with
probability w_i w_j / sum(w) (at most 1), so node i's expected degree is
about w_i: the Chung-Lu model, the configuration model's cousin with
independent edges (Newman, Networks, section 12.1.2). weights can be a
node field of the current graph. No self-loops or repeated edges. The
node field `expected` keeps w. layout=false skips the layout.

### `makeFromCalls(target)`

makeFromCalls("package.module") builds a call graph of a module (a
module name or a .py file): a node per function and method, an edge
from each to the functions it calls. Calls are matched by name
(f(), self.f(), cls.f(), Class.f()), so it's an approximation: calls
through variables, other modules or dynamic dispatch are missed.
Nodes get `function` (Class.name or name), `cls`, `lines`, `params`
and `public` (no leading underscore); edges get `weight`, the number
of call sites.

### `makeFromCSV(filename, nodes=None, directed=False, source=None, target=None, interaction=None, weight=None, header=True)`

makeFromCSV("edges.csv") replaces the graph with a spreadsheet table as
Gephi reads it: an edge table (Source, Target[, Type, Weight, Label, ...]),
an adjacency matrix or an adjacency list. makeFromCSV("edges.csv",
"nodes.csv") also reads a node table (Id[, Label, ...]). Opening just a node
table adds its columns to the current graph's nodes (matched by Id).
Other columns become fields; directed=true makes edges without a Type
directed.

As in Cytoscape, any columns can hold the edges: source= and target=
name them (by header, or number from 0), interaction= the type of
interaction (stored in the edge field `interaction`) and weight= the
weight: makeFromCSV("ppi.tsv", source="gene_a", target="gene_b",
interaction="type"). header=false reads a table without a header row
(columns col1, col2, …; source=0, target=1 pick them).

### `makeFromDL(filename)`

Replace the current graph with a UCINET DL file (fullmatrix, edgelist1, nodelist1).

### `makeFromDOT(filename)`

Replace the current graph with a Graphviz DOT file (.dot, .gv): node
and edge statements, subgraphs (cluster_* members get a `cluster` field),
default attributes; pos, color/fillcolor, label, width/height, shape,
penwidth and weight map to GUESS, other attributes become fields.

### `makeFromGDF(filename)`

Replace the current graph with the contents of a GDF file.

### `makeFromGEXF(filename)`

Replace the current graph with a GEXF file (Gephi's format): attributes,
colours, positions, sizes, edge weights and thickness.

### `makeFromGloBI(taxa, interaction='eats', limit=500, server='https://api.globalbioticinteractions.org')`

makeFromGloBI(["Vulpes vulpes", "Lynx lynx"]) opens observed species
interactions from the Global Biotic Interactions database (GloBI):
for each taxon, what it `interaction`s (eats, preysOn, pollinates,
parasiteOf, visitsFlowersOf, ...), up to `limit` records each.
Feeding links run from food to eater, other kinds from the taxon to
its partner. Edges get `weight` (records) and `interaction`; nodes
`taxon` (the full name) and `query` (true for the taxa you asked
for). GloBI aggregates many studies with their own licences: cite
GloBI and the sources you use.

### `makeFromGML(filename)`

Replace the current graph with a GML file (Graph Modelling Language, as
written by networkx, igraph, yEd and Cytoscape: labels, graphics x/y,
fill colour, size and shape, and every other attribute as a field). For
compatibility with GUESS 2006, a GraphML (XML) file works too.

### `makeFromGraphML(filename)`

Replace the current graph with a GraphML file.

### `makeFromImports(target, external=False, tests=False, level=None)`

makeFromImports("networkx") builds the import graph of a Python
package (an installed package's name, or a folder or file of
source): a node per module, an edge from each module to each module
of the package it imports (importer -> imported). Nodes get `module`
(the dotted name), `package` (its parent package), `depth`, `lines`,
`functions` and `classes`; edges get `weight` (import statements) and
`toplevel` (false when every import between the two happens inside a
function: a deferred import, often used to dodge an import cycle).
external=true also adds the outside packages imported (`external`
true). level=k merges modules below depth k into their parent (e.g.
level=2 gives one node per subpackage). Test modules are skipped
unless tests=true. The code is parsed, never run.

### `makeFromMap(region='usa')`

makeFromMap("usa") makes the network of the lower 48 US states, an
edge wherever two share a border (touching at a single point, like
the Four Corners, doesn't count); makeFromMap("world") does the same
for countries.
Nodes get `abbrev`, `latitude`, `longitude` (and `continent` for
countries) and are placed on a map. Such networks are planar (when
each region is one piece of land), which is why four colours always
suffice to colour a map. Data: Natural Earth 1:50m, public domain.

### `makeFromPajek(filename)`

Replace the current graph with a Pajek .net file (nodes are named pajek<id>).

### `makeFromSimilarity(filename, k=5, threshold=None, method='cosine', id=None, columns=None, features=None, values=None, mutual=False)`

makeFromSimilarity("profiles.csv") links each row of a feature table
to the k rows most similar to it (k=5), or, with threshold=t, every
pair at least t similar. The table is wide (an id column, here the
first or id=..., then numeric columns; columns=[...] picks them, and
text columns become node fields) or long, one row per (id, feature,
value): features="keyword", values="score" (values default to 1).
method: "cosine" (default; profiles pointing the same way),
"correlation" (same ups and downs), "jaccard" (shared nonzero
features) or "euclidean" (close values; 1/(1+distance)). mutual=true
keeps only pairs that are in each other's top k. Edges get `weight`
= similarity. Typical uses: co-expression networks, documents by
term profile, people by votes or answers.

### `makeFromText(filename, terms=None, by='paragraph', window=None, minCount=3, maxTerms=60, caseSensitive=False, stopwords=None)`

makeFromText("story.txt", terms) builds a co-occurrence network: one
node per term, linked when two terms occur in the same paragraph
(by="sentence" or "line" for smaller units; window=k for within k
words of each other, in the same paragraph). terms is a list of names, or a dict from each
node's name to its aliases, e.g. {"Holmes": ["Holmes", "Sherlock"],
"Adler": ["Irene Adler", "Miss Adler", "the woman"]} (matching ignores
case unless caseSensitive=true). Without terms, the maxTerms most
frequent words (at least minCount times, minus common words and
stopwords=[...]) are used. Nodes get `count` (occurrences), `units`
(paragraphs etc. containing them) and `first` (the first unit, for
story order); edges get `weight`, the number of shared units (or
windows).

### `makeFromTwoMode(filename, a=None, b=None, weight=None)`

makeFromTwoMode("paper-authors.csv", "paper", "author") reads a table
with one row per pair (a paper and one of its authors, a gene and one
of its terms, a person and an event) as a two-mode network: a node
for every value of each column, an edge for every row, and `kind` set
to the column's name, ready for bipartiteLayout(kind) or
project(kind, "author"). a= and b= name the columns (default: the
first two); weight= names a numeric column to use as edge weight.
Repeated rows add to the weight.

### `makeNicheModel(species=30, connectance=0.15, seed=0)`

makeNicheModel(species, connectance) builds a food web with the niche
model (Williams and Martinez 2000), which reproduces the structure of
real food webs well: each species has a niche value (0..1) and eats
every species whose niche falls in a range below its own. connectance
(links / species^2) is typically 0.05-0.3. Edges run from food to
eater; nodes get `niche` and `range`. Species left without any link
are dropped. seed= gives a different web.

### `makePriceModel(n, c=3, a=1.0, seed=0, layout=True)`

makePriceModel(n, c, a) grows a citation network by Price's model
(Newman, Networks, section 13.1): papers arrive one at a time, and each
cites c earlier papers (on average, when c isn't a whole number),
chosen with probability proportional to in-degree + a, so the
much-cited get cited more (cumulative advantage). The in-degrees end up
with a power-law tail of exponent 2 + a/c. Uses Newman's fast method:
with probability c/(c + a) copy a citation made by a random earlier
paper, otherwise pick a paper uniformly. Edges point from citing to
cited. The field `born` gives each node's and edge's arrival step (paper
k arrives at step k), so revealUpTo(step) replays the growth.

### `mergeNodes(*nodes, name=None)`

mergeNodes(a, b, ...) merges nodes that are the same entity into
the first (or name=...): every edge of the others moves to it
(parallel edges are combined, adding their weights; edges between the
merged nodes disappear), empty fields of the kept node are filled
from the others, `aliases` records the other names and labels, and
`merged` counts the nodes it stands for. One undo step. Also takes a
set or a list of pairs from findDuplicates (each pair merged).

### `minCostFlow(source, target, amount, capacity='capacity', cost='weight')`

minCostFlow(a, b, 100) finds the cheapest way to send `amount` units
from a to b: each edge can carry up to its `capacity` field (missing
or empty = unlimited) at its `cost` field per unit (default: weight;
missing = 1). Direction is followed for directed edges; an undirected
edge can carry flow either way. Stores each edge's flow in `flow` and
returns the total cost (an error if the amount can't get through).

### `nestedness(field, rows=None)`

nestedness(kind) measures how nested a two-mode network is (NODF,
Almeida-Neto et al. 2008; 0 = not at all, 100 = perfectly): in a
nested plant-pollinator network, the specialists interact with
subsets of the species the generalists interact with. kind is the
field saying which side each node is on; rows= names one side
(default: the first value). Returns (NODF, NODF of the rows, NODF of
the columns). Compare with a randomised network (rewire()) to judge
whether a value is high.

### `ninverse(seq)`

All nodes not in seq.

### `nodeData(*args)`

nodeData(field, ...) or nodeData(nodes, field, ...): one row per node
for an Altair chart, with `name`, the fields given (all data fields when
none are) and `_node`, the node's id, which links each mark to its node.
alt.Chart(nodeData("degree", "dept")).mark_point().encode(x="degree", y="dept")

### `offspring(cases=None, show=True)`

offspring() reads a transmission tree (directed edges from infector
to infected) and counts how many each case infected (its outdegree).
Returns them with R (the mean), the dispersion k of a negative
binomial fitted to them (small k, below 1: a few superspreaders cause
most transmission), the share who infected no one, and the share of
transmissions caused by the top 20% of cases. offspring(cases) uses
only those cases, e.g. offspring(onset < 28); their infections count
wherever they lead. Stores the count in the field `offspring`.

### `outbreaks(runs=200, seeds=1, model='SIR', beta=0.3, gamma=0.1, threshold=0.5, immune=None, weight=None, steps=1000, large=0.1, seed=0, name='risk', show=True)`

outbreaks(runs) repeats spread() many times, because one simulated
outbreak is an anecdote. Each run starts from `seeds` random nodes (a
number) or from the given nodes. immune=nodes (vaccinated, isolated)
can't be infected or start an outbreak; weight=field makes long
contacts riskier (see spread). Stores each node's share of runs it was
reached in `risk` (name=...), charts the final sizes (hover a bar to see
where those outbreaks started), and returns them
(.mean, .median, .large = share of runs reaching more than `large` of
the nodes).

### `plotSpectrum(matrix='laplacian')`

plotSpectrum() charts the eigenvalues of the Laplacian (or
"adjacency", "normalized") in order, one dot each: count the zeros
to count components; a small second eigenvalue means the network
nearly splits in two.

### `readSets(filename, item=None, set=None, where=None)`

readSets("go.csv") reads a table with one row per (item, set) pair,
e.g. gene,term, into {set: {items}} for enrichment(). item= and set=
name the columns (default: the first two); where={"aspect": "process"}
keeps only matching rows. A row's set may list several, separated by
";" or "|".

### `remove(seq)`

Remove nodes and/or edges (a node takes its edges). Undo with add(...).
As in the original, a removed node's name still refers to it, so
add(name) or addNode(name) puts it back.

### `removeComplete(seq)`

Remove nodes and/or edges permanently (they cannot be re-added).

### `removeDisconnected()`

Remove (and return) nodes with no edges other than self loops.

### `removeEdge(e)`

Remove one edge.

### `removeLeaves()`

Repeatedly remove nodes of total degree <= 1. Returns what was removed.

### `removeMap()`

removeMap() removes the map drawn by geoLayout (the positions stay).

### `removeNode(node)`

Remove one node and its edges (undo with add(g.deleted) or undo()).
Its name still refers to it, so addNode(n) puts it back.

### `removeSelfLoops()`

Remove (and return) all edges whose endpoints are the same node.

### `report(filename=None, top=5)`

report() writes a one-page summary of the graph: size, density,
components, degree distribution, path lengths, clustering,
assortativity, the `top` nodes by degree, betweenness and PageRank,
and the communities if any have been found (louvain_class,
leiden_class, infomap_class). report("summary.html") saves it as a web
page (offered as a download in the browser) and report("summary.md")
as Markdown; with no name it's printed. Returns the Markdown.

### `resizeLinear(field, smallest, largest)`

Size nodes (or edge widths) by rank of field value, from smallest to largest.

### `resizeRandom(field, smallest, largest)`

Give each distinct value of field a random size (or edge width) between smallest and largest.

### `richClub(normalized=True, trials=5, seed=0, show=True)`

richClub() asks whether the well-connected nodes are densely linked
to each other: for each degree k, the rich-club coefficient is the
density of the links among nodes with degree > k. normalized=True
divides it by the same coefficient in degree-preserving random
networks (averaged over `trials`): above 1 = a rich club (hubs prefer
each other, as in airline or scientific elites), below 1 = hubs avoid
each other. Prints a table and returns {k: value}.

### `shortcutNodes()`

Repeatedly replace degree-2 nodes by an edge between their neighbours.
Returns [removed, added].

### `showChart(chart, title=None)`

showChart(chart, title=None) shows an Altair chart in the dock (a cell
whose value is a chart does this by itself). Hovering a mark highlights
its nodes, clicking selects them, right-click opens the element menu;
interval selections (brushes) select what they cover.

### `sizeBy(field, smallest, largest, scale='linear')`

sizeBy(field, smallest, largest) sizes nodes (or edge widths, for an edge field) in
proportion to a numeric field's value, from smallest to largest. scale may be
"linear", "log", "sqrt" or "rank" (as in Gephi's ranking). Compare
resizeLinear, which spaces distinct values evenly.

### `skitter(field)`

Nodes around a circle ordered by field; radius shrinks with outdegree.

### `sortBy(*d, descending=False)`

sortBy(field) or sortBy(seq, field), smallest first;
descending=true for largest first.

### `spectrum(matrix='laplacian')`

spectrum() returns the eigenvalues of the graph Laplacian L = D - A,
smallest first; spectrum("adjacency") those of A (largest first),
spectrum("normalized") of the normalised Laplacian I - D^-1/2 A D^-1/2.
Direction and weights are ignored (edges count once each way). The
Laplacian has as many zero eigenvalues as the network has
components; the second smallest is the algebraic connectivity.

### `spread(seeds, model='SIR', beta=0.3, gamma=0.1, threshold=0.5, steps=100, seed=0, show=True, immune=None, weight=None)`

spread([v1, v2], model="SIR") simulates something spreading from
the seed nodes, one step at a time:
  "SI"         each step, every infected node infects each susceptible
               neighbour with probability beta
  "SIR"        the same, and each infected node recovers (and can't be
               infected again) with probability gamma
  "cascade"    independent cascade: a newly active node gets one chance
               (probability beta) to activate each neighbour
  "threshold"  a node becomes active when at least `threshold` of its
               neighbours are (complex contagion: ideas, adoption)
Directed edges are followed in their direction. immune=nodes can't be
infected (vaccinated, say: state V). weight=field makes long contacts
riskier: beta is then the chance per unit of weight, so an edge of
weight w transmits with chance 1 - (1 - beta)**w per step. Stores
`infected_at` (the step a node was reached; -1 = never) and `state`
(S, I, R or V at the end), plots how many are in each state at each
step, and returns those counts. Replay it with showTime(t,
infected_at); outbreaks() repeats it many times.

### `straightenEdges()`

straightenEdges() makes every edge straight again (arc = 0).

### `structuralBalance(sign='sign', name='camp')`

structuralBalance(sign) tests a signed network (an edge field of +1/-1,
or "+"/"-") for structural balance: every cycle has an even number of
negative edges, so no triangle has exactly one or three. Harary's
theorem says a balanced network splits into (at most) two camps with
positive edges inside and negative edges between; the node field `camp`
(0 or 1) gets that split, or for an unbalanced network one that follows
a spanning tree. Returns {"balanced": ..., "unbalanced": [(a, b, c), ...]
(triangles with an odd number of negative edges), "frustrated": [edges
that disagree with the camps]}. Direction is ignored.

### `travelingSalesman(stops=None, weight='weight', cycle=True)`

travelingSalesman(stops) finds a short route that visits every node
in `stops` (default: all) and returns to the start (cycle=False: an
open path), travelling along the graph's edges with `weight` as the
length (missing = 1); a stop can be passed through more than once.
It's an approximation (Christofides' algorithm on undirected graphs,
a greedy method otherwise), fine for planning, not a proof of
optimality. Returns the route's nodes and edges in order; .length
holds its total length.

### `trophicLevels()`

trophicLevels() computes each species' prey-averaged trophic level
(`trophic`: 1 for species that eat nothing in the web, otherwise 1 + the
mean level of what it eats), `omnivory` (the spread of its food's
levels: 0 = eats on one level) and `role` (basal: eats nothing here;
top: nothing eats it; else intermediate). Prints a summary.

### `wordCloud(field, top=80, stopwords=None, minLength=3)`

wordCloud(field) shows the most frequent words in a text field as a
word cloud in the dock (as Gephi's Word Cloud plugin), sized by how
many times each occurs. Hovering a word lights up the nodes (or edges)
whose text contains it; clicking selects them. Common English words
are left out; stopwords=[...] adds more, top= sets how many words,
minLength= the shortest word kept.

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
path length, clustering, transitivity, degree assortativity, reciprocity
(directed edges) and (if computed) modularity.

### `groupsOfSize(field, smallest, largest=None)`

groupsOfSize(field, min[, max]): the nodes (or edges) whose value of
field is shared by at least min (and at most max) elements — e.g. drop
tiny communities with showOnly(groupsOfSize(louvain_class, 5)).

### `heatMap(center, near='#d7191c', far='#2c7bb6', unreachable='#bdbdbd', middle='#8e5fbf', spread=True)`

heatMap(node) colours every node by its distance (hops, ignoring
direction) from node: red at the node, through violet, to blue for the
farthest, grey if unreachable; the distance is stored in the hops field
(-1 if unreachable). spread=True (default) spaces the colours by how
many nodes are at each distance, so every band is visible;
spread=False spaces them by distance alone. near, middle, far and
unreachable change the colours (middle=None: a straight blend). Gephi's
heat map tool.

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
community in the louvain_class field (0 = largest) and returns the
communities. Try colorize(louvain_class). resolution > 1 gives more,
smaller communities; seed=None varies the result between runs.

### `modularity(field)`

modularity(field): the modularity Q of the partition given by a node
field (e.g. modularity(dept), modularity(louvain_class)).

### `mutualEdges()`

Directed edges whose reverse edge also exists.

### `paint(center, color, depth=0)`

paint(node, color, depth=0) colours a node, and with depth=k everything
within k hops of it (Gephi's brush).

### `radius()`

The smallest eccentricity among nodes with at least one neighbour.

### `recompute(*fields)`

Computed fields (betweenness, pagerank, component, ...) recalculate
themselves when read after the graph has changed, so this is rarely
needed: recompute(pagerank, ...) forces it now (e.g. for a field you
had overwritten, which then follows the graph again); recompute() redoes
every computed field that has been used so far.

### `revealUpTo(step, field='born')`

revealUpTo(step) plays back a network's growth: nodes whose `born`
field (or field=) is at most step are shown and the rest hidden, and an
edge is shown once both its ends are (and, if edges have the field too,
once its own value is at most step). The way to animate a growing
network: build the final network first, give every node (and edge) the
step it arrives at, lay it out once, center(g.nodes) to fit the final
picture, then call revealUpTo(0), revealUpTo(1), ... from a timer, so
nodes appear where they will stay. Returns the nodes and edges that
arrive at exactly this step (to highlight them).

### `shortestPath(source, target, weighted=False)`

shortestPath(a, b): the nodes and edges of a shortest path from a to b
(following edge direction), or an empty set if there is none.
weighted=true uses edge weights as lengths. E.g. shortestPath(a, b).color = red

### `showAll()`

Make every node and edge visible again.

### `showOnly(seq, induced=False)`

showOnly(seq) hides every node and edge not in seq: a set of nodes
keeps the edges among them; a set with edges keeps just those edges
and their endpoints, plus any nodes listed (showOnly(shortestPath(a, b))
shows the path and nothing else). induced=true keeps every edge among
the shown nodes instead. Undo with showAll(). As subgraph does.

## Clustering and generators

### `biComponentClusters()`

Biconnected components (ignoring edge direction).

### `edgeBetweennessClusters(count)`

Split the graph into `count` communities with Girvan-Newman.

### `makeBarabasiAlbertRandom(*args)`

makeBarabasiAlbertRandom(vert, edges, evolve): preferential attachment; starts from `vert` nodes and adds `evolve` nodes with `edges` edges each. The field `born` records the step each node and edge arrived (0 for the seeds), so revealUpTo(step) can replay the growth.

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

## More measures: Katz, prestige, bridging, cliques, MDS, k-brace; field tools and generators

### `castField(field, type)`

castField(field, INTEGER) changes a field's type (INTEGER, DOUBLE,
BOOLEAN or VARCHAR) and converts its values: "12" becomes 12, 3.7
becomes 3, "yes" becomes true. Values that can't be converted are
counted and left empty. One undo step.

### `cliques(minSize=3, limit=1000)`

cliques(minSize=3) finds every maximal clique (a group where everyone
is linked to everyone, that no other node could join) with at least
minSize nodes, ignoring edge direction; largest first, up to `limit`.
largestCliques() gives just the biggest ones.

### `copyColors(fromGraph, field='name')`

copyColors("other") gives each node the colour of the node with the
same name (or the same value of field=...) in another graph of this
session, so the same people look the same in both (Gephi's Node Color
Manager). Nodes with no match keep their colour. One undo step.

### `evaluateLinks(method='adamic_adar', hide=0.1, seed=0, show=True)`

evaluateLinks() tests how well predictLinks would have done: it hides
a share of the edges (hide=0.1), scores the unlinked pairs from what's
left, and reports precision (of the top-scored pairs, as many as were
hidden, how many are hidden edges) and AUC (how often a hidden edge
outscores a pair that was never linked; 0.5 is chance). The graph
isn't changed. method as in predictLinks, or "all" to compare them.

### `geoVectors(edges=None, lat=None, lon=None)`

geoVectors() stores each edge's compass bearing (degrees from north,
from node1 to node2) in `bearing` and its great-circle length in `km`,
and summarises the edges (all, or the given ones): their mean length and
its standard deviation, and the resultant vector (the edges added up
as arrows, as east and north kilometres) with its size and bearing.
Latitude and longitude fields are found as geoLayout finds them, or
named: geoVectors(lat=y, lon=x). Returns the summary as a dict.

### `kBrace(k=2)`

kBrace(k) is the k-brace: what's left after repeatedly removing every
edge whose two ends have fewer than k neighbours in common (an edge's
embeddedness), ignoring direction. Weakly embedded ties go; the dense
core stays. showOnly(kBrace(2)) shows it. (It equals the (k+2)-truss:
each remaining edge lies in at least k triangles.) Returns the edges.

### `makeBarabasiAlbertAging(n, m, aging=1.0, seed=0)`

makeBarabasiAlbertAging(n, m, aging=1) grows a preferential-attachment
network in which old nodes lose their appeal: each new node links to m
existing ones, chosen with probability proportional to degree x
age^-aging (age in steps since the node arrived). aging=0 is plain
Barabási-Albert; larger values favour recent nodes (Dorogovtsev and
Mendes' model). The field `born` records the step each node and edge
arrived (0 for the starting clique), for revealUpTo.

### `makeGeometricRandom(n, radius, seed=0)`

makeGeometricRandom(n, radius) scatters n nodes in the unit square
and links every two closer than radius (a random geometric graph:
sensor and contact networks). Nodes are drawn where they fell.

### `makePowerlawCluster(n, m, p, seed=0)`

makePowerlawCluster(n, m, p) grows a scale-free network with
clustering (Holme and Kim): preferential attachment with m edges per
new node, each followed with probability p by a triangle-closing edge.

### `makeWattsStrogatz(n, k, p, seed=0)`

makeWattsStrogatz(n, k, p) replaces the graph with a Watts-Strogatz
small world: n nodes on a ring, each linked to its k nearest
neighbours, then each edge rewired with probability p (0 keeps the
ring lattice; 1 is close to random). Nodes are drawn on the ring.

### `mds(dims=2, weight=None, name='mds')`

mds(dims=2) places the nodes in `dims` dimensions by classical
multidimensional scaling of their shortest-path distances (hops; with
weight=... an edge field read as a distance), storing the coordinates
in fields mds1, mds2, ... (or name=...). Unreachable pairs count as one
more than the longest distance. scatterLayout(mds1, mds2) draws them;
mdsLayout() does both in one go.

### `readNames(filename, field='name')`

readNames("keep.txt") is the nodes whose name (or field=...) appears
in a text file: one per line, or separated by commas, semicolons, tabs
or spaces. showOnly(readNames("keep.txt")) keeps just them (Gephi's
FilterFromFile). Says how many listed names matched no node.

### `weightedBridging(weight='weight', name='wbridging')`

weightedBridging() is bridging centrality for weighted networks: a
strong tie (big weight) counts as a short one (distance 1/weight), so
shortest paths prefer strong ties. Stores the weighted betweenness in
`wbetweenness` and weighted betweenness x bridging_coef in `wbridging`
(or name=...). Edges with weight 0 or less are left out.

## More clustering: Chinese Whispers, MCL, DBSCAN, MCODE, overlapping communities

### `chineseWhispersClusters(iterations=20, weighted=True, seed=0)`

chineseWhispersClusters() finds communities by Chinese Whispers
(Biemann 2006): every node starts in its own class and repeatedly takes
the class with the most (weighted) ties among its neighbours. Fast and
parameter-free; the number of communities isn't chosen in advance.
Stores cw_class (0 = largest) and returns the communities.
weighted=False ignores edge weights; seed=None varies the result.

### `cliquePercolationClusters(k=3)`

cliquePercolationClusters(k=3) finds overlapping communities by
clique percolation (Palla et al. 2005): a community is a chain of
k-cliques that share k-1 nodes, so a node can be in several (and many
nodes are in none). Stores cpm_classes (e.g. "0;2"; "" for none) and
cpm_count; returns the communities, largest first. showOverlaps(...)
draws them.

### `dbscanClusters(fields=('x', 'y'), eps=None, minPts=4)`

dbscanClusters() groups nodes that lie close together on screen with
DBSCAN (Ester et al. 1996): a cluster is a dense region (at least
minPts nodes within eps of each other), and nodes in sparse areas are
noise (dbscan_class -1). fields: numeric node fields to measure
distance in, by default the positions (x, y); e.g.
dbscanClusters((degree, pagerank)). Fields aren't rescaled, so give
them comparable ranges. eps=None picks it from the knee of the sorted
k-distance curve and prints it.

### `linkCommunities(threshold=None, minEdges=2)`

linkCommunities() finds overlapping communities by clustering edges
(Ahn, Bagrow & Lehmann 2010): two edges sharing a node are similar when
their other ends have similar neighbourhoods; edges are merged by
single linkage and the dendrogram is cut where partition density is
highest (or at similarity `threshold`, 0-1). Each edge gets link_class;
a node belongs to the communities of its edges (link_classes "0;3",
link_count). Communities of fewer than minEdges edges are dropped
(link_class -1). Returns node communities, largest first.

### `mclClusters(inflation=2.0, expansion=2, loops=True, iterations=100)`

mclClusters() finds clusters by the Markov Cluster algorithm (MCL,
van Dongen 2000): random walks are expanded and then "inflated" until
flow stays inside clusters. inflation (1.2-5, default 2) sets the
granularity: higher gives more, smaller clusters. Uses edge weights;
loops=True adds self loops (recommended). Stores mcl_class.
Works on connected pieces of up to 3000 nodes.

### `mcodeClusters(degreeCutoff=2, scoreCutoff=0.2, haircut=True, fluff=False, fluffDensity=0.1, kCore=2, maxDepth=100)`

mcodeClusters() finds densely connected regions with MCODE (Bader &
Hogue 2003), made for protein complexes in interaction networks. Each
node is weighted by the density of the highest k-core of its
neighbourhood; complexes grow from the heaviest seeds through
neighbours weighing at least (1 - scoreCutoff) of the seed's. Defaults
are the paper's: degreeCutoff 2, scoreCutoff 0.2, haircut (keep only
the 2-core) on, fluff (add dense neighbours, fluffDensity) off, kCore 2,
maxDepth 100. Stores mcode_class (0 = best scoring, -1 = in none) and
mcode_score (the node weight); returns the complexes, best first, and
prints their scores (density x size).

### `showOverlaps(communities, hulls=False, none='lightgray')`

showOverlaps(communities) shows overlapping communities: each gets
its own colour, a node in one takes that colour, a node in several is
drawn as a pie with a slice per community, and nodes in none are
lightgray (none=...). communities: the result of
cliquePercolationClusters()/linkCommunities(), any set of sets, or a
field listing them (cpm_classes, link_classes, or a class field).
hulls=True also shades each community. removePies() goes back to
plain nodes.

## Structure: bridges, cut nodes, backbones, directed graphs, mixing, comparing partitions

### `ancestors(node)`

ancestors(node): every node with a directed path to node (upstream: what it
depends on or cites, transitively). Undirected edges count both ways.

### `assortativity(field=None, categorical=None)`

assortativity() is the degree assortativity of the graph: positive when
hubs link to hubs, negative when hubs link to small nodes.
assortativity(dept) measures homophily by a field: near 1 = ties stay
within the same value, 0 = random mixing, negative = ties cross values.
Numeric fields use the correlation of values across edges;
categorical=true treats a numeric field (a grade, a class number) as
categories instead, and categorical=false treats a text field's values
as numbers.

### `blockmodel(count=4, show=True)`

blockmodel(count) groups the nodes into count positions of structurally
equivalent nodes: nodes tied to the same others (in the same
directions), whether or not they're tied to each other, which is a
role (teacher, broker, follower), not a community. Profiles are
compared by correlation and merged by average-linkage clustering.
Stores each node's position in `position` (0 = largest), prints the
image matrix (the density of ties from each position to each other;
a dense diagonal means cohesive positions, dense off-diagonals mean
roles that serve each other) and returns the positions. Try
colorize(position), then collapseBy(position) for the reduced graph.
Fine up to a couple of thousand nodes.

### `bridges()`

bridges(): the edges whose removal would split a connected part of the
graph in two (direction ignored; a pair joined by parallel edges is never
a bridge). bridges().color = red shows the weak ties.

### `compareClusters(field1, field2, method='nmi')`

compareClusters(louvain_class, dept) says how well two partitions of
the nodes agree, over the nodes that have both values: method "nmi"
(normalized mutual information, 0..1), "ari" (adjusted Rand: 0 = chance,
1 = identical), "rand" or "vi" (variation of information: 0 = identical).
Works for edge fields too.

### `cutNodes()`

cutNodes(): the nodes whose removal would split a connected part of the
graph (articulation points; direction ignored).

### `descendants(node)`

descendants(node): every node reachable from node along directed edges
(downstream: what depends on it, or what it leads to).

### `feedbackEdges()`

feedbackEdges(): directed edges that close cycles (back edges of a
depth-first search, plus self-loops); removing or reversing them leaves
the directed part acyclic. A small set, not necessarily the smallest.

### `mainPath()`

mainPath() finds the main path of a citation (or other flow)
network: the chain of directed edges that the most source-to-sink
paths run through (Hummon and Doreian's main path analysis, key-route
variant). Each directed edge gets `spc`, its search path count as a
share of all source-to-sink paths (0..1). The path starts at the edge
with the highest spc and extends both ways, always along the
highest-spc edge, to a source and a sink. Edges closing cycles
(feedbackEdges()) are ignored. Returns the path's nodes and edges.
In a citation network with edges citing -> cited, it runs from recent
work back to the field's foundations.

### `mixingMatrix(field, show=True)`

mixingMatrix(dept) counts the edges between each pair of values of a
node field (dept1-dept1, dept1-dept2, ...), printed as a table and
returned as {value: {value: count}}. Direction is ignored. With many
values only the 20 most common are printed.

### `reciprocity()`

reciprocity(): the share of directed edges whose reverse edge also
exists (1 = every tie returned). Undirected edges are left out.

### `robustness(orders=('random', 'degree'), trials=5, seed=0, show=True)`

robustness() asks how the network falls apart as nodes fail: for
each way of removing nodes it gives the share of nodes still in the
largest connected piece after removing each share of them, and plots
the curves. orders: "random" (failures; averaged over `trials`
random orders), "degree" or "betweenness" (attacks on the biggest
hubs or bridges first, ranked once at the start), "adaptive" (the
current highest-degree node each time), or a node field (highest
first). The graph isn't changed. Returns {order: [(removed share,
largest-piece share), ...]} and prints the share removed at which the
largest piece drops below half. Many real networks shrug off random
failures but break quickly under attack.

### `spanningTree(maximum=False, weighted=True)`

spanningTree() returns the edges of a minimum spanning tree (a forest if
the graph is in pieces) by edge weight: the cheapest backbone that keeps
everything connected. spanningTree(maximum=True) keeps the strongest ties
instead, a good backbone when weight means strength:
showOnly(spanningTree(maximum=True)). weighted=False ignores weights.

### `transitiveReduction()`

transitiveReduction(): in a directed acyclic graph, the edges implied
by longer paths (a -> c when a -> b -> c exists, and repeated edges). They
are marked in the edge field `redundant` and returned, so
transitiveReduction().visible = false shows the backbone of a citation or
dependency graph. Only directed edges count; cycles are an error (see
feedbackEdges).

### `transitivity()`

transitivity(): the share of connected triples that close into
triangles (global clustering coefficient; direction ignored).

### `triadCensus(show=True)`

triadCensus() counts the 16 kinds of directed triads (Holland and
Leinhardt): how often three nodes form a cycle, a transitive triple, a
star and so on. Undirected edges count as mutual. Prints the types that
occur and returns {type: count}.

## networkx bridge and sample graphs

### `fromNetworkX(G, name=None)`

fromNetworkX(G) replaces the graph with networkx graph G: its node and
edge attributes become fields (types from the values), `pos` or x/y give
positions (otherwise a spring layout), and direction is kept. String keys
become node names; other keys become n0, n1, ... with the original in
`nxkey`. fromNetworkX(G, "name") opens it in a new tab instead and
switches to it (use("main") goes back).

### `makeSample(name=None)`

makeSample("karate") loads a classic network: karate, lesmis,
florentine, davis, petersen, kite, tutte, dodecahedron, caveman.
makeSample() lists them. They come with their attributes (karate's
`club`, lesmis' `weight`, davis' `bipartite`) and a spring layout.

### `setField(values, name, kind=None)`

setField(values, "name") stores a result as a field: a dict from nodes
(or node names) to values, as networkx centralities return; a dict from
node pairs (a, b) to values gives an edge field; a list of node sets (as
community algorithms return) gives each node its set's index, largest
first. The type is taken from the values. Returns the field.
    setField(nx.core_number(toNetworkX()), "core")
    setField(nx.community.greedy_modularity_communities(toNetworkX()), "greedy")

### `toNetworkX(directed=None, visibleOnly=False)`

toNetworkX() returns the graph as a networkx graph, to use any networkx
algorithm: node keys are node names, and every field (dept, color, x, y,
pagerank once used, ...) is an attribute; positions are also `pos`.
directed=True/False forces the type (a mixed graph becomes directed, with
undirected edges both ways); visibleOnly=True leaves out hidden elements.
Bring results back with setField:
    import networkx as nx
    setField(nx.katz_centrality(toNetworkX()), "katz")

## igraph: communities, large-graph layouts, similarity, patterns, cuts and flows

### `bipartiteLayout(field, hgap=1, vgap=1)`

bipartiteLayout(field) draws a two-mode network in two rows (by a field
with two values, e.g. bipartite in makeSample("davis")), ordering each
row to reduce edge crossings. Without igraph (still loading, or
turned off) the rows are ordered by the barycenter heuristic instead.

### `cohesiveBlocks()`

cohesiveBlocks() finds nested groups that stay connected after removing
any k-1 nodes (Moody and White's cohesive blocking): a structural view
that k-cores miss. Each node's highest cohesion is stored in `cohesion`;
the blocks are returned, most cohesive last. Slow beyond a few thousand
nodes.

### `cutDendrogram(count)`

cutDendrogram(n) re-cuts the hierarchy of the last walktrapClusters or
fastGreedyClusters into n communities (same field), e.g. driven by a
Slider to explore coarser and finer groupings.

### `dhLayout(seed=0)`

dhLayout() is the Davidson-Harel layout: simulated annealing that
spreads nodes evenly and avoids edge crossings and nodes on edges. Slow
but tidy: for figures of up to a few hundred nodes.

### `dominatorTree(root)`

dominatorTree(root) follows directed edges from root and finds, for
every node it reaches, its immediate dominator: the last node every path
from root must pass through (who controls access to whom). Stored in
`idom` (a node name); returns the nodes root reaches.

### `drlLayout(preset='default', seed=0)`

drlLayout() is a force-directed layout for large graphs (DrL /
OpenOrd): tens of thousands of nodes in seconds, with clusters pulled
well apart. preset: "default", "coarsen" (more separated clusters),
"coarsest", "refine" (polish an existing layout) or "final".

### `eigenvectorClusters(count=None)`

eigenvectorClusters() splits the graph by the leading eigenvector of
the modularity matrix (Newman), repeatedly; count limits the number of
communities. Stored in eigen_class.

### `fastGreedyClusters(count=None)`

fastGreedyClusters() merges communities greedily by modularity
(Clauset-Newman-Moore), building a hierarchy; count as in
walktrapClusters. Stored in fastgreedy_class; cutDendrogram(n) re-cuts.

### `findPattern(pattern, induced=False, limit=100)`

findPattern(pattern) finds every place where a small pattern occurs in
the graph (subgraph isomorphism, LAD algorithm). The pattern is a list of
pairs, e.g. findPattern([("a","b"), ("b","c"), ("c","a")]) for
triangles, or a networkx graph (nx.cycle_graph(4), nx.star_graph(3)).
induced=True requires no extra edges among the matched nodes. Returns
up to `limit` matches, each a set of nodes; the same nodes matched in
another order count once.

### `fluidClusters(count, seed=0)`

fluidClusters(count) splits a connected graph into exactly count communities
(fluid communities). On a graph in pieces run it on one part, e.g. in
subgraph(giantComponent()). Stored in fluid_class.

### `infomapClusters(trials=10, seed=0)`

infomapClusters() finds communities by Infomap (how a random walker's
flow stays inside groups), following edge direction and weights; a good
choice for directed networks such as citations or web links. Stored in
infomap_class.

### `labelPropagationClusters(field=None, seed=0)`

labelPropagationClusters() finds communities very fast (linear time) by
letting each node adopt its neighbours' most common label; good for very
large graphs, rougher than Leiden. labelPropagationClusters(field)
starts from the values of a field and keeps those nodes fixed, filling in
the rest (semi-supervised). Stored in lpa_class.

### `largestCliques()`

largestCliques() returns the largest cliques (groups where everyone is
linked to everyone), each a set of nodes. Exponential in the worst
case, fast on sparse graphs.

### `leidenClusters(resolution=1.0, objective='modularity', iterations=-1, seed=0)`

leidenClusters() finds communities with the Leiden algorithm (better
than Louvain: every community is internally connected) and stores them
in leiden_class (0 = largest). resolution > 1 gives more, smaller
communities. objective="CPM" (constant Potts model) avoids modularity's
resolution limit; its resolution is a density, typically 0.001-0.1.
iterations=-1 runs until stable; seed=None varies the result.

### `lglLayout(root=None, seed=0)`

lglLayout() is the Large Graph Layout: grows the drawing outward from
a root node (default: a random one, or lglLayout(v1)), suited to big,
tree-like networks.

### `maxFlow(a, b, capacity='weight')`

maxFlow(a, b) computes the maximum flow from a to b with edge weights
as capacities (capacity=None: 1 per edge), following edge direction when
the graph has directed edges. Each edge's flow is stored in the edge
field `flow`; returns the total.

### `maxMatching(field=None)`

maxMatching() returns a largest set of edges with no node in two of
them (pairs everyone it can); maxMatching(field) matches across the two
values of a field in a two-mode network, using weights.

### `minCut(a, b, capacity=None)`

minCut(a, b) returns the fewest edges whose removal separates a from b
(direction ignored); minCut(a, b, weight) the cut of least total
weight. Prints the cut's size.

### `optimalClusters()`

optimalClusters() finds the partition with the highest possible
modularity (exact, by integer programming): only for small graphs (up
to about 100 nodes), as a baseline for the other methods. Stored in
optimal_class.

### `personalizedPagerank(seq, damping=0.85)`

personalizedPagerank(seq) ranks every node by how easily a random walk
restarting at the given nodes reaches it: relevance to a chosen set
(e.g. personalizedPagerank(sel) or personalizedPagerank(v1)). Stored in
the field `ppr`.

### `predictLinks(top=20, method='adamic_adar', show=True, add=False)`

predictLinks() lists likely missing edges: pairs of nodes that aren't
linked but share neighbours, scored by "adamic_adar" (shared neighbours,
rare ones counting more), "jaccard", "common" (count of shared
neighbours) or "resource" (resource allocation). Returns the `top`
pairs as (node, node, score), best first. add=true also adds them as
edges, marked with the method's name in the edge field `predicted`
(showOnly(predicted != None) shows them; undo() takes them away).
evaluateLinks() tests how well a method would have predicted.

### `rewire(times=None, name=None, seed=0, keep=None)`

rewire() makes a randomised copy of the graph in a new tab keeping
every node's degree (repeated swaps of edge ends, 10 x edges by
default): the null model for "is this structure more than chance?".
Compare e.g. transitivity() or modularity here and there. Edge weights
travel with the swapped ends. keep=field only swaps ends that share
that field's value, so the edges between each pair of values stay
the same in number: rewire(keep=kind) keeps a two-mode network
two-mode (plants still only link to pollinators).

### `similarTo(node, method='jaccard', top=10, alpha=0.9)`

similarTo(v1) scores every node by how much its neighbourhood overlaps
v1's, stores the score in the field `similarity` and returns the `top`
most similar nodes. method: "jaccard" (shared neighbours / all
neighbours of either), "dice" (2 x shared / sum of degrees), or
"adamic_adar" (shared neighbours, rare ones counting more), or
"regular": regular equivalence (Leicht, Holme and Newman), where nodes
are similar if their neighbours are similar, so nodes with the same
role score high even with no neighbours in common; alpha (below 1)
weighs longer paths. Direction is ignored.

### `simplify(combine='sum', loops=True)`

simplify() merges parallel edges between the same two nodes (and the
same direction) into one, whose weight combines theirs: combine="sum"
(default), "max", "min", "mean" or "first"; loops=True also removes
self-loops. One undo step.

### `spinglassClusters(spins=25, gamma=1.0, seed=0)`

spinglassClusters() finds communities by simulated annealing of a spin
model (Reichardt-Bornholdt); handles negative edge weights (signed
networks). Slow: for graphs up to about 2,000 nodes. spins is the most
communities allowed, gamma > 1 favours smaller ones. Stored in
spinglass_class. Needs a connected graph.

### `umapLayout(minDist=0.01, epochs=500, seed=0)`

umapLayout() places nodes by UMAP on the graph's connections: tight,
well-separated islands for clusters. Edge weights count as similarity.
minDist (0..1) is how tightly points may pack; more epochs, more
polish.

### `useIgraph(on=True)`

useIgraph(false) makes the statistics use networkx / numpy instead of
igraph (to compare results or work around a problem); useIgraph() turns
igraph back on. Prints which engine is active.

### `voronoiClusters()`

voronoiClusters() picks central "generator" nodes automatically and
gives every other node to its nearest one (by weighted distance); the
communities are stored in voronoi_class and the generators returned.

### `walktrapClusters(count=None, steps=4)`

walktrapClusters() groups nodes that short random walks (steps long)
tend to stay among, building a hierarchy; count=None cuts it where
modularity is highest, walktrapClusters(8) gives 8 communities.
Stored in walktrap_class; cutDendrogram(n) re-cuts it.

## Graphviz layouts: dot, neato, sfdp, fdp, circo, twopi, osage; overlap removal

### `circoLayout()`

circoLayout() puts the biconnected parts of the graph on circles,
chained together: shows rings and cycles (pathways, loops).

### `dotLayout(rankdir='TB', clusters=None, nodesep=0.25, ranksep=0.5, route=True)`

dotLayout() draws the graph in layers with Graphviz's dot: edges point
down (rankdir="LR": left to right; "BT", "RL"), crossings are minimised
and long edges are routed around nodes as smooth bends (route=False:
straight edges). clusters=dept keeps each value's nodes together in a
box. nodesep and ranksep are spacings in inches. Best for hierarchies,
dependency and citation graphs.

### `fdpLayout(clusters=None, overlap='prism')`

fdpLayout() is a force layout that can keep clusters together:
fdpLayout(clusters=louvain_class) gives each community its own box.

### `graphvizLayout(engine='dot', **attrs)`

graphvizLayout("neato") lays the graph out with any Graphviz engine:
dot, neato, fdp, sfdp, circo, twopi, osage or patchwork. Keyword
arguments become Graphviz graph attributes, e.g.
graphvizLayout("neato", mode="sgd", overlap="prism") or
graphvizLayout("dot", rankdir="LR", ranksep=1). Pinned (fixed) nodes stay
put in neato and fdp.

### `neatoLayout(mode='major', model='shortpath', field=None, overlap='prism')`

neatoLayout() places nodes so their distances on screen follow their
distances in the graph (stress majorization: the best-quality layout up
to a few thousand nodes). mode: "major" (default), "sgd" (faster),
"KK" (Kamada-Kawai); model="circuit" uses resistance distance;
field=weight makes an edge field the preferred edge length;
overlap="prism" (default) then removes node overlaps (overlap="true"
leaves them).

### `osageLayout(clusters)`

osageLayout(dept) packs each value's nodes into a rectangle and packs
the rectangles together: a compact overview of the groups.

### `removeOverlap(method='prism', sep=4)`

removeOverlap() moves nodes apart until none overlap, keeping the shape
of the current layout (Graphviz's PRISM). Works after any layout. method:
"prism" (default), "voronoi", "scale" (spread evenly), "compress";
sep is the extra margin in points.

### `sfdpLayout(overlap='prism', K=None)`

sfdpLayout() is Graphviz's multilevel force layout: fast on large graphs
(thousands to tens of thousands of nodes) with good global structure.
K is the ideal edge length in inches; overlap="prism" removes overlaps.

### `twopiLayout(root=None)`

twopiLayout(v1) places nodes on rings by their distance from a root
(Graphviz's twopi; default root: chosen by Graphviz).

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

circleLayout(field) makes one circle per value of a node field (bigger
groups get bigger circles, the biggest first), packed in rows.

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

### `forceAtlas2Layout(iterations=None, scaling=None, gravity=1.0, strongGravity=False, linLog=False, dissuadeHubs=False, preventOverlap=False, edgeWeightInfluence=1.0, gravitySources=None)`

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
  gravitySources       nodes that act as extra centres of gravity: every
                       node is pulled toward the nearest of them (in
                       hops) instead of the centre, so the graph forms
                       a cluster around each (MultiGravity ForceAtlas2)
E.g. forceAtlas2Layout(linLog=true, preventOverlap=true)

### `frLayout(width=None, height=None)`

frLayout() runs Fruchterman-Rheingold (as in Pajek) starting from the
current positions and fits the result into a 1000 x 1000 grid with cells
the size of the largest node; frLayout(width, height) uses that area.

### `gemLayout(seed=None)`

gemLayout() runs the GEM force-directed layout (Frick et al.);
gemLayout(seed) seeds the random generator for a repeatable layout.

### `hiveLayout(axis=None, position=None, scale='rank', axes=None, inner=60, length=440, curved=True)`

hiveLayout(axis, position) draws a hive plot (Krzywinski et al.): one
radial axis per value of the node field `axis` (the most common values,
at most `axes` of them, the rest merged into "other"), each node placed
along its axis by the numeric field `position` (default totaldegree),
and edges drawn as curves between axes. scale is "rank" (default; evenly
spread), "linear" or "log". Without `axis`: for directed graphs the
classic source / hub / sink axes (only outgoing, both, only incoming
edges), otherwise leaves / connectors / hubs by degree. The axes are drawn
with their labels; any later layout removes them.
E.g. hiveLayout(dept, pagerank) or hiveLayout(louvain_class, axes=5)

### `isomLayout(iterations=None)`

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

### `jSpringLayout(iterations=None)`

jSpringLayout() runs the JUNG spring layout from random positions until
it settles or for 500 iterations (fewer on graphs over 1000 nodes);
jSpringLayout(n) runs exactly n iterations.

### `kkLayout(width=None, height=None)`

kkLayout() runs Kamada-Kawai on each connected component, starting from
a circle, then fits the result into 1000 x 1000; kkLayout(width, height)
uses that area instead.

### `labelAdjustLayout(margin=2)`

labelAdjustLayout() moves nodes just enough that nodes and their
visible labels stop overlapping (Gephi's Label Adjust).

### `mdsLayout()`

mdsLayout() places nodes by classical multidimensional scaling of the
edge weights (an edge's weight is the distance between its endpoints,
every other pair is at distance 1). Nodes without edges are not moved.

### `mirrorLayout(horizontal=True)`

mirrorLayout() flips the layout left-right; mirrorLayout(false) flips it
upside down.

### `moveLayout(x, y)`

moveLayout(x, y) moves the layout so its top-left corner is at (x, y).

### `noverlapLayout(margin=5, ratio=1.2)`

noverlapLayout() nudges nodes apart until none overlap (Gephi's Noverlap):
each node is treated as a disc of ratio x its size plus margin.

### `physicsLayout(iterations=None)`

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
layout into a width x height box at the origin. rescaleLayout(nodes,
percent) or rescaleLayout(nodes, xpercent, ypercent) spreads out (or
draws together) just those nodes about their centre, leaving the rest
where they are (Gephi's Scale layout).

### `ringMove(node, index)`

ringMove(node, k) moves a node to position k around the circle made by
circleLayout() and re-spaces the ring (what dragging a node around the
circle does).

### `rotateLayout(degrees=90)`

rotateLayout(degrees) turns the layout clockwise about its centre.

### `scatterLayout(x, y, width=1000, height=1000)`

scatterLayout(x, y) places nodes by two numeric fields (x to the
right, y upwards) in a width x height area. Dragging a node then edits
those two values.

### `springLayout(iterations=None)`

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

### `translateLayout(dx, dy)`

translateLayout(dx, dy) moves every node by (dx, dy).

### `treeLayout(root=None, horizontal=False, spacing=None)`

treeLayout() draws each connected component as a tidy tree (a
breadth-first spanning tree from its best-connected node, or from root),
parents centred over their children; horizontal=true grows it left to
right; spacing sets the distance between neighbouring leaves.

### `weightedKKLayout()`

weightedKKLayout() runs the JUNG Kamada-Kawai layout using shortest
paths where each edge's `weight` is its length.

### `weightedSpringLayout(minLength, maxLength, iterations=None)`

weightedSpringLayout(minLength, maxLength[, iterations]) is springLayout
with each edge's natural length mapped linearly from its `weight`
(lowest weight -> minLength, highest -> maxLength). Iterations as for
springLayout.

## Structure-aware layout (motifLayout, after LUMINA)

### `motifLayout(spacing=None, minStar=3, minCycle=3, maxCycle=40, minChain=2, minParallel=2, leavesAround=True, gap=2.0, iterations=300, outline=False, seed=0)`

motifLayout() is a structure-aware layout (a port of LUMINA, the
IntAct team's layout for protein networks). It finds four shapes and
gives each its own arrangement: cycles become circles, chains (paths
ending in a leaf) hang off their anchor as small rings, a node with
leaves becomes a star with the leaves in rings around it, and nodes
sharing exactly the same neighbours (parallel) line up in a grid
between them. Each shape is treated as one big node while the whole
is laid out by stress majorization, so the drawing keeps graph
distances; components are turned to fit and packed. Each node's shape
is stored in the field `motif` ("star 3", "cycle 1", …), so
colorize(motif) or groupBy(motif) work.

spacing= the distance between neighbouring nodes in a shape (default:
from node sizes); gap= the room between shapes, in spacings;
minStar= the leaves a node needs to be a star (leavesAround=false
leaves smaller groups of leaves to the layout); minCycle/maxCycle and
minChain set the sizes of rings and chains; outline=true draws an
ellipse or box around each shape (removeConvexHulls() clears them).
Fixed nodes keep their positions.

## More layouts: multipartite, concentric, ordered, circle packing, isometric layers

### `circlePackLayout(*fields, padding=4, outlines=True)`

circlePackLayout(field) packs the nodes as circles inside one circle
per value of a field; circlePackLayout(field1, field2, ...) nests them
(each value of field2 a circle inside its field1 circle, and so on). Each
node keeps its size, so nothing overlaps; padding is the gap between
circles. The group circles are drawn and labelled (outlines=false
leaves them out); any later layout removes them. Without a field all
nodes are packed into one circle. (Bostock's d3 circle packing.)

### `concentricLayout(field, rings=None)`

concentricLayout(field) puts the nodes on rings by their value of a
field, the highest value in the centre (degree, a score, a level). A
numeric field with many values is cut into `rings` equal ranges
(default 8); a text field gets one ring per value. Each ring is ordered
so neighbours of the ring inside sit near them, and spaced to fit the
nodes' sizes. Compare twopiLayout(root), rings by distance from one node.

### `dualCircleLayout(count=None, field='degree')`

dualCircleLayout(count) puts the `count` nodes with the highest value
of field (default degree) on an inner circle and everyone else on an
outer circle, each outer node near the inner nodes it links to (Gephi's
Dual Circle Layout). count defaults to the square root of the number of
nodes.

### `hairballLayout(neighbors=True, logX=False, logY=False, width=1000, height=1000)`

hairballLayout() draws a Hairball Buster plot (node-neighbour
centrality, Matties et al., JHU/APL): nodes sorted by degree, the
busiest on the left, each at x = its rank and y = its degree (upwards),
with a short tick, level with each node, under the rank of every one of
its neighbours, so each row of ticks shows who a node is tied to. Hubs
tied mostly to hubs, to leaves, or to a clique stand out at a glance,
and two graphs can be compared plot to plot. Edges are left as they are:
g.edges.visible = false shows the plot alone. neighbors=false leaves
out the ticks (drawn for up to 5000 edges); logX/logY use log scales.
Any later layout removes the axes and ticks.

### `isometricLayout(field, layers=None, angle=30, gap=None)`

isometricLayout(field) stacks the graph in layers by a node field and
shows them at an angle, as planes one above the other: each layer keeps
the current layout's shape, squashed into a diamond, the lowest value at
the bottom (Gephi's Isometric Layout and Network Splitter 3D). Edges
between layers run between the planes. A text field gives one layer per
value; a numeric field with many values is cut into `layers` equal
ranges (default 5). angle tilts the planes (30 = isometric; smaller is
flatter); gap is the distance between layers. The layer number goes in
the zlayer field, and the planes are outlined; run it again to change
the field or angle without compounding. Any other layout removes the
outlines.

### `multipartiteLayout(field, gap=None, vertical=False)`

multipartiteLayout(field) puts the nodes in one column per value of a
node field (in value order: kind, year, level, ...), ordering each column
to reduce edge crossings; vertical=true makes rows instead. gap is the
distance between columns (default: they fill 1000 units). The
multipartite version of bipartiteLayout.

### `orderedLayout(field, axis='x', iterations=None, inverted=False, length=1000, gravity=1.0)`

orderedLayout(field) fixes each node's position on one axis by a
numeric field (a year, a step, an order) and runs a ForceAtlas2 force
on the other axis only, so connected nodes come together without
breaking the order (Gephi's Ordered Layout and EventGraphLayout).
axis="y" orders from top to bottom; inverted=true reverses; length is
the span of the ordered axis. Nodes without a value go in the middle.

## Display: hulls, legends, background, edges, labels, selection, export

### `clearDrawings()`

Remove every drawing made with drawLine, drawText, drawRect and drawCircle.

### `constantLabelSize(on=True, size=None)`

constantLabelSize() keeps labels the same size on screen as you zoom
(they grow with the graph otherwise); each label appears once there is
room for it and stays as you zoom further in, so zooming in reveals more
labels. size= sets that size in pixels (default 10; a node's labelsize
still scales its own label). Labels inside nodes keep fitting their
nodes. constantLabelSize(false) turns it off.

### `createConvexHull(seq, color='200,200,255,90', shape='hull', rotate=False, padding=6)`

createConvexHull(seq) shades the convex hull around the nodes in seq
(edges contribute their endpoints). shape="box" or "ellipse" draws a
box or an ellipse around them instead; rotate=true turns the box or
ellipse to fit the group (the smallest box at any angle) rather than
keeping it upright; padding= is the room left around the nodes.
encircle(seq) is the same with an ellipse.

### `curvedEdges(on=True)`

curvedEdges() draws every edge as a circular arc running clockwise from
source to target, as in Gephi's preview, so a->b and b->a separate and
direction reads without arrows. curvedEdges(false) goes back to straight
lines; curvedEdges(k) sets the curvature: the arc radius is edge length / k
(default 1.2, as in Gephi; 2 gives semicircles).

### `directedEdges(style='taper')`

directedEdges(style) sets how directed edges show which way they go.
"taper" (the default): wide at the source, narrowing to a point at the
target, with no arrowhead. "fade": dark at the source, light at the
target. "arrow": a line with an arrowhead at the target. Holten and van
Wijk's user study (CHI 2009) found tapered edges were read fastest and most
accurately, dark-to-light next, and standard arrows among the worst, and
that adding a second cue did not help, so the default uses the taper
alone. An edge's own arrowhead or linestyle still applies: dashed, dotted
and similar styles keep an arrowhead, since they cannot show direction.

### `drawCircle(x, y, r, color=None, fill=None, lineWidth=1.5, style='solid')`

drawCircle(x, y, r) draws a circle centred at (x, y) with radius r
(graph coordinates), under the graph. fill=, lineWidth= and style= as
for drawRect.

### `drawLine(x1, y1, x2, y2, color=None, width=1.5, style='solid', arrow=False)`

drawLine(x1, y1, x2, y2) draws a line on the display, under the
graph, in graph coordinates (the same as node x and y; a node's
centre is n.x + n.width/2, n.y + n.height/2). color= (default: the
theme's text colour), width=, style="dashed" or "dotted", arrow=true
puts an arrowhead at (x2, y2). Returns the drawing (.remove()).

### `drawRect(x, y, w, h, color=None, fill=None, lineWidth=1.5, style='solid')`

drawRect(x, y, w, h) draws a box with its top-left corner at (x, y)
(graph coordinates), under the graph. fill= a colour fills it
(e.g. "255,200,0,60" for a translucent one); color= is the outline
(default: the theme's text colour) and lineWidth=0 leaves it out.

### `drawText(x, y, text, color=None, size=14, anchor='middle')`

drawText(x, y, "text") writes text on the display at (x, y) in graph
coordinates, above the graph. size= is in graph units (it zooms with
the graph); anchor= "start", "middle" or "end" (horizontal).

### `edgeLabelsAlong(on=True)`

edgeLabelsAlong() turns edge labels to run along their edges (kept
upright, so they read left to right); edgeLabelsAlong(false) keeps them
horizontal (the default).

### `encircle(seq, shape='ellipse', color=None, rotate=True, padding=10)`

encircle(seq) draws a shaded ellipse around a group of nodes, turned
to fit it; encircle(seq, "box") a box, encircle(seq, "hull") the
convex hull. rotate=false keeps the shape upright. Without a color,
each group gets its own (light) colour. Returns the shape: .color,
.shape, .rotate and .padding change it; removeConvexHull removes it.

### `encircleBy(field, shape='ellipse', rotate=True, padding=10, smallest=2)`

encircleBy(field) draws one shape around each group of nodes that
share a value of a node field (with at least `smallest` members), each
in its own colour: encircleBy(louvain_class), encircleBy(dept, "box").
Returns the shapes.

### `excentricLens(on=True, radius=None, autoSize=None, maxLabels=None)`

excentricLens() turns on the lens tool (the toolbar's Lens): a circle
that follows the pointer and lists the labels of the nodes under it
beside it, each joined to its node by a line (excentric labelling).
The wheel resizes it, Shift+wheel scrolls long lists; a click pins it,
and then clicking a label selects its node (Shift: add or remove),
"Select" takes everything under the lens, and the colour bars filter
the list. radius in pixels; autoSize=true sizes the lens to the
density under it; maxLabels per side. excentricLens(false) turns it
off.

### `exportEPS(filename='guess.eps')`

Save the display as EPS (downloaded by the browser): an image of the current view inside the file. For vector output use exportSVG.

### `exportGIF(filename='guess.gif')`

Save the display as GIF (downloaded by the browser): an image of the current view inside the file. For vector output use exportSVG.

### `exportJPG(filename='guess.jpg')`

Save the display as JPG (downloaded by the browser, or added to the zip after startImages()).

### `exportPDF(filename='guess.pdf')`

Save the display as PDF (downloaded by the browser): an image of the current view inside the file. For vector output use exportSVG.

### `exportPNG(filename='guess.png')`

Save the display as PNG (downloaded by the browser, or added to the zip after startImages()).

### `exportPS(filename='guess.ps')`

Save the display as PS (downloaded by the browser): an image of the current view inside the file. For vector output use exportSVG.

### `exportSVG(filename='guess.svg')`

Save the display as SVG (downloaded by the browser, or added to the zip after startImages()). Vector: the whole graph, not just the visible area.

### `getConvexHulls()`

All hulls currently shown.

### `getDisplayBackground()`

The display background color, or None when it follows the light/dark theme.

### `getDrawings()`

The drawings on the display.

### `GradientLegend(start, end, lo=0, hi=1, ticks=None)`

A color ramp legend: GradientLegend(startColor, endColor, min, max[, tickEvery])
shows the ramp from min to max, with a tick mark every tickEvery units.

### `hideOverlappingLabels(on=True)`

hideOverlappingLabels() hides labels that would overlap a label of a
bigger node, rechecked as you zoom; hideOverlappingLabels(false) shows all.

### `hoverFields(*fields, nodes=None, edges=None)`

hoverFields(dept, degree) sets the fields the tooltip shows as soon as
the pointer is on a node or edge; by default it shows only the label.
Waiting a moment shows every field. Node fields go to nodes' tooltips
and edge fields to edges'; a kind you don't mention keeps its fields.
hoverFields(nodes=["dept"], edges=["weight"]) names them by kind (for a
field both have, such as color); hoverFields() goes back to labels
only. View → Hover fields… picks them from a list.

### `labelOutlines(on=True)`

labelOutlines() draws a halo in the background colour around labels so
they stay readable over edges; labelOutlines(false) turns it off.

### `labelPlacement(method='candidates')`

labelPlacement("candidates") or labelPlacement("particles") chooses how
labels with labelpos "outside" (and edge labels, which slide along their
edge) find room. "candidates" (default) tries 16 positions around each
node, biggest nodes first, then re-places labels that still collide;
"particles" also searches further out, ring by ring, and draws a leader
line to labels it places away from their node. Both avoid other labels,
nodes and edges.

### `Legend()`

A legend box on the display. ``l = Legend(); l.add(bob, "managers")``.

Entries snapshot the look of the node, edge or hull at the time they are added.

### `optimizeLabels(seconds=2)`

optimizeLabels() improves the positions of labels placed "outside"
(and of edge labels) by simulated annealing for a few seconds, trading
overlaps with labels, nodes and edges against the preferred positions;
the result stays until the graph is replaced, labelPlacement changes or
you run it again. Good before exporting a figure.

### `overrideArrowLength(length)`

Fix the arrowhead length (graph units) for all directed edges; None resets.

### `overrideArrowWidth(width)`

Fix the arrowhead width (graph units) for all directed edges; None resets.

### `raiseChanged(on=True)`

raiseChanged() (the default) draws a node or edge on top of the others
once its appearance changes (colour, size, shape, label, visibility),
so what you just changed isn't hidden under its neighbours; edges stay
under nodes. raiseChanged(false) keeps the drawing order fixed.

### `removeBackgroundImage()`

Remove the background image set with setBackgroundImage.

### `removeConvexHull(hull)`

Remove one hull.

### `removeConvexHulls(seq=None)`

Remove the given hulls, or all hulls.

### `removeDrawing(d)`

Remove one drawing (from drawLine, drawText, drawRect or drawCircle).

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

### `startImages(filename='images.zip')`

Collect the images that exportPNG() and the other exports save into one
zip file, downloaded by stopImages(), instead of downloading each:
    startImages('frames.zip')
    for t in range(1990, 2001):
        showTime(t, 'year', 1)
        exportPNG('year_%d.png' % t)
    stopImages()
Each export shows the display as it is at that point in the script.
Repeated names get -2, -3, ... added.

### `startMovie(fps=30, filename='guess.webm')`

Record the display (graph canvas) as a WebM video until stopMovie().
Everything shown — layouts, morphs, edits, panning — is captured.

### `stopImages()`

Stop collecting images (see startImages) and download the zip.

### `stopMovie()`

Stop recording and download the video.

## Styles and visual mappings

### `applyStyle(name)`

applyStyle(name) runs a style's commands (one undo step).

### `arrowheadBy(field)`

arrowheadBy(field) gives each value of an edge field its own
arrowhead (triangle, swept, open, diamond, circle, tee, then
repeating), the most common value first; heads show on directed edges.
One edge: e.arrowhead = "swept"; "none" leaves the head off.

### `defineStyle(name, commands)`

defineStyle(name, [command, ...]) saves a named style: Gython lines that
set colours, sizes, labels, legends or display settings. Styles are saved
with the session; the style panel builds them for you.

### `getStyles()`

The saved styles: {name: [commands]}.

### `labelBy(field, show=True)`

labelBy(field) sets each node's (or edge's) label to its value of field
and shows the labels; labelBy(field, false) sets them without showing.

### `legendFor(field, title=None)`

legendFor(field) adds a legend explaining the current colours by field:
one entry per value (for categories, as after colorize), or a gradient
from the lowest to the highest value (for numbers, as after colorBy).
The legend follows the colours: run colorize or colorBy again and it
updates (until you add or remove entries yourself).

### `lineStyleBy(field)`

lineStyleBy(field) gives each value of an edge field its own line
style (solid, dashed, dotted, double, wave, taper, fuzzy, then
repeating), the most common value first. One edge: e.linestyle = "dashed";
the styles are solid, dashed, dotted, taper (narrows towards the
target), wave, double, fuzzy, gradient (source colour to target colour)
and flow (dashes moving towards the target).

### `polygon(sides)`

polygon(sides) is the node style for a regular polygon with that many
sides (3 to 64), a corner at the top: (dept == 'dept1').style = polygon(5).
polygonBy(field) sets one per node from a field.

### `polygonBy(field, smallest=3, largest=12)`

polygonBy(field) draws each node as a regular polygon whose number of
sides comes from a node field (as Gephi's Polygon Shaped Nodes): a whole
number field gives the sides directly (kept within smallest..largest);
any other field gives each value its own polygon, 3, 4, 5, … sides, the
most common value first.

### `removeLegend(legend)`

removeLegend(lg) or removeLegend(2) removes one legend (the number is the
one shown as <legend 2: …>; the × on a legend runs this).

### `removeLegends()`

removeLegends() removes every legend.

### `removeStyle(name)`

removeStyle(name) deletes a saved style.

### `shapeBy(field)`

shapeBy(field) gives each value of a node field its own shape (circle,
square, rounded square, triangle, diamond, hexagon, octagon, then
repeating), the most common value first.

### `table(seq=None)`

table() opens the data table of all nodes; table(seq) shows just those
nodes or edges (e.g. table(sel), table(freq > 10), table(g.edges)).

## Pie nodes, borders and edge bundling

### `borderBy(field, width=2.5)`

borderBy(field) gives node borders a distinct colour per value of a
field (as colorize does for fills) and widens them.

### `bundleEdges(field=None, strength=0.85, method=None, neighbors=10, angleStrength=1.2, stiffness=0.1, compatibility=0.6, cycles=6)`

bundleEdges() bundles edges that run alike, so the main flows stand
out of a hairball. Three methods:
  bundleEdges()                 MINGLE (multilevel, saves "ink"): fast,
                                tree-like bundles; good for large graphs
  bundleEdges(method="fdeb")    force-directed edge bundling: smooth,
                                organic curves; up to a few thousand edges
  bundleEdges(louvain_class) through the centres of the groups of a
                                node field
strength 0..1 blends toward straight lines (0 = straight). MINGLE:
neighbors (edges compared with each), angleStrength (higher allows
sharper turns). FDEB: stiffness (of each edge), compatibility (0..1, how
alike edges must be to attract), cycles. Layouts and removeBundles()
straighten them again.

### `pieChart(fields, palette=None, labels=None)`

pieChart([f1, f2, ...]) draws each node as a pie whose slices are the
node's values of those numeric fields. pieChart(f) with one text field
reads each node's own list of values from it: v1.f = [12, 21, 12] gives
v1 three slices (slice k has the same colour on every node).
palette=[colors] sets slice colours; labels=[...] names the slices in the legend.

### `pieNeighbors(field)`

pieNeighbors(field) draws each node as a pie of its neighbours' values of
a categorical field (the most common values; the rest as "other").

### `removeBundles()`

Draw edges straight again after bundleEdges.

### `removePies()`

Draw nodes normally again (after pieChart / pieNeighbors).

## Grouping: collapse and expand

### `collapse(seq, name=None)`

collapse(seq) replaces those nodes with one meta-node (see module help);
collapse(seq, "name") names it. Returns the meta-node.

### `collapseBy(field, smallest=2)`

collapseBy(field) collapses each group of nodes sharing a value of field
(with at least `smallest` members) into a meta-node named after the value.

### `expand(meta)`

expand(metaNode) brings back the nodes a meta-node stands for (also:
double-click it). Returns them.

### `expandAll()`

Expand every collapsed group (repeatedly, for nested groups).

### `isGroup(node)`

True if node is a collapsed group (meta-node).

## Several graphs: subgraphs and tabs

### `closeGraph(name)`

closeGraph(name) discards a graph that isn't the current one.

### `graphNames()`

The graphs in this session; the current one first.

### `newGraph(name='untitled')`

newGraph(name) starts an empty graph and switches to it.

### `project(field, keep, method='count', name=None)`

project(kind, "woman") turns a two-mode network (people and the
events, groups or papers they belong to) into a one-mode network of
just the nodes whose `kind` is "woman": two are linked when they share
a neighbour of the other kind. It opens as a new graph (the two-mode
one stays; use() goes back), keeping fields and positions. Each edge
gets `shared` (how many neighbours in common) and `weight`, by method:
  "count"    the number shared (default)
  "jaccard"  shared / neighbours of either (0..1; removes the size
             effect of very active nodes)
  "newman"   each shared neighbour adds 1/(its degree - 1), so a
             small event counts more than a crowded one
Each kept node also gets `affiliations`: its number of other-kind
neighbours. E.g. project(kind, "event") gives the event network.

### `renameGraph(name)`

renameGraph(name) renames the current graph.

### `subgraph(seq=None, name=None, induced=False)`

subgraph(seq) makes a new graph of exactly what seq selects, keeping
fields, positions and look, and switches to it: a set of nodes gives
those nodes and the edges among them (subgraph(dept == "dept3")); a
set with edges gives just those edges and their endpoints, plus any
nodes listed (subgraph(freq > 100) is the heavy-tie network;
subgraph(shortestPath(a, b)) is the path). induced=true keeps every
edge among the selected nodes instead. subgraph(seq, "name") names
the new graph; use(name) goes back. As showOnly does for the display.

### `use(name)`

use(name) switches to another graph of this session (see graphNames()).

## Time: ranges, years and the timeline

### `showTime(t, field=None, window=None)`

showTime(t) shows only the nodes and edges whose ranges contain time t
(elements without ranges stay visible); showTime(t, field) shows those
whose numeric field is <= t (window=w: only within the last w).
Edges are shown only when both ends are.

## Presentations (slides)

### `addSlide(note='', camera=None, at=None)`

addSlide(note) saves the current graph (as a state) and view as a slide;
camera=[x, y, zoom] is filled in by the page; at=k inserts it at k.

### `moveSlide(index, to)`

moveSlide(k, j) moves slide k to position j.

### `noteSlide(index, note)`

noteSlide(k, text) changes slide k's note.

### `removeSlide(index)`

removeSlide(k) deletes slide k.

### `showSlide(index, duration=1200)`

showSlide(k) morphs the graph to slide k's state and moves the camera.

### `slides()`

The slides' notes, in order.

## Data from the web: URLs, SPARQL, NDEx, Neo4j, packages

### `installPackage(name)`

installPackage("name") installs a Python package into this session
(pure-Python wheels from PyPI, or Pyodide's own packages such as scipy),
in the background; a note appears when it's ready to import.

### `makeFromCypher(query, url='http://localhost:7474', user=None, password=None, database='neo4j')`

makeFromCypher(query, url, user, password) runs a Cypher query on a
Neo4j server's HTTP API and builds the graph from the nodes and
relationships it returns (properties become fields).

### `makeFromFile(filename)`

makeFromFile(filename) opens a graph file in any format GUESS reads,
choosing the reader from the file's extension or, when the extension
doesn't say (.xml, .txt, .json, …), from its content: GraphML, XGMML,
SBML, PSI-MI, KGML or GPML in .xml; PSI-MI TAB, SIF or CSV in .txt;
Cytoscape.js JSON or CX in .json. Opening a file in the page (File →
Open, or dropping it) does this.

### `makeFromNDEx(uuid, server='https://www.ndexbio.org')`

makeFromNDEx(uuid) opens a public network from the NDEx repository
(Cytoscape's network commons), with its attributes and layout.

### `makeFromOpenAlex(search, limit=200, mode='citations')`

makeFromOpenAlex("graph drawing") searches OpenAlex (the open
catalogue of scholarly works, CC0) for works with those words in the
title, takes the `limit` most cited, and opens their citation network
(citing -> cited) with `title`, `year`, `cites` (citations from
anywhere), `venue` and `firstauthor`. mode="authors" opens a two-mode
paper-author network instead (kind = paper or author), ready for
project(kind, "author"). Ready for mainPath(), leidenClusters() and
the Text cookbook's recipes.

### `makeFromSPARQL(query, endpoint='https://query.wikidata.org/sparql', directed=True)`

makeFromSPARQL(query) builds a graph from a SPARQL query whose rows bind
?source and ?target (optionally ?sourceLabel / ?targetLabel, used as
labels; any other variables become edge fields). E.g. a Wikidata query
for "influenced by" links.

### `makeFromSTRING(genes, species=9606, score=0.7, add=0, server='https://string-db.org')`

makeFromSTRING(["TP53", "MDM2", "ATM"]) opens the protein interactions
among those genes from the STRING database (string-db.org): species is
an NCBI taxon (9606 human, 10090 mouse, 4932 yeast, 7227 fly, 6239
worm, 3702 Arabidopsis, 511145 E. coli), score the minimum combined
confidence (0.4 medium, 0.7 high, 0.9 highest), add=n also brings in
the n proteins that interact most with the query. Genes may be a list
or one string separated by spaces/commas. Nodes get `description`,
`stringId` and `query` (true for the genes you asked for); edges get
`score` (also `weight`) and the evidence behind it: `experiments`,
`databases`, `textmining`, `coexpression`, `neighborhood`, `fusion`,
`cooccurrence` (each 0..1). STRING data are CC BY 4.0: cite it.

### `makeFromURL(url, format=None)`

makeFromURL(url) downloads a graph (GDF, GEXF, GraphML, GML, DOT, Pajek, DL, CSV,
RDF (Turtle, N-Triples, RDF/XML), Cytoscape's SIF, NNF, Cytoscape.js JSON, CX/CX2 and XGMML, PSI-MI TAB or XML, SBML, BioPAX, KEGG KGML, WikiPathways GPML, a .guess
session or a .py script) and opens it; format=".gexf" etc. when the URL doesn't end in the extension (the
biological formats are also recognised by their content).

### `makeFromWikipedia(title, limit=150, lang='en')`

makeFromWikipedia("Graph drawing") opens a page's link network: the
page, up to `limit` articles it links to, and every link among them
(directed: linking page -> linked page). Node `hop` is 0 for the start
page and 1 for the others; `indegree` then shows which linked
articles the neighbourhood itself points to most (identifier pages
such as "Doi (identifier)", linked by citation templates, are left
out). lang= picks the
language edition ("de", "fr", ...). Wikipedia text is CC BY-SA; the
link structure is what's loaded here.

### `sparql(query, endpoint='https://query.wikidata.org/sparql')`

sparql(query[, endpoint]) runs a SPARQL query (Wikidata by default) and
returns the rows as a list of {variable: value} dicts.

## Standalone web pages (exportHTML)

### `exportHTML(filename='graph.html', title=None, hidden=False, fields=True)`

exportHTML("graph.html") writes the graph as one self-contained web
page: open it in any browser, from disk or a web server, with nothing
else to install. It shows the graph as drawn here (colours, sizes,
shapes, labels, legends, images) and lets the reader pan and zoom,
search by name, hover for a node's fields and click to see its
neighbours. hidden=true includes hidden nodes and edges; fields=false
leaves the data fields out (a smaller, more private page).

## Live graph streams (Gephi streaming protocol)

### `stopStream()`

stopStream() stops every stream started with streamFrom.

### `streamFrom(url)`

streamFrom(url) follows a live graph stream in the Gephi streaming
format (Gephi's Graph Streaming plugin): an HTTP URL that sends one
JSON event per line, such as Gephi's own
"http://localhost:8080/workspace1?operation=getGraph", or a ws:// or
wss:// WebSocket sending one event per message. Nodes and edges are
added, changed and removed as events arrive (between commands, so a
long command delays them); new nodes appear next to a neighbour.
Streamed changes are not undo steps. stopStream() stops it. The
server must allow cross-origin requests (CORS) from this page.

## AI assistants (MCP bridge)

### `connectAssistant(port=7777)`

connectAssistant() connects this page to an AI assistant through the
GUESS MCP bridge (mcp/guess-mcp.mjs, which the assistant starts; see
the manual). The assistant can then run Gython here, read a summary
of the graph and the command help, and see the view. Everything it
runs appears in the console marked "assistant" and can be undone.
disconnectAssistant() ends it. port= must match GUESS_MCP_PORT.

### `disconnectAssistant()`

disconnectAssistant() disconnects the AI assistant (see connectAssistant).

## Cytoscape formats: SIF, NNF, Cytoscape.js JSON, CX/CX2, XGMML, .cys sessions

### `exportCYJS(filename='graph.cyjs')`

exportCYJS("graph.cyjs") writes the graph as Cytoscape.js JSON, which
Cytoscape (File → Import → Network from File) and Cytoscape.js read:
every field as data, positions, and each node's colour, size and
shape as data (color, width, height, shape) for a style to map.

### `makeFromCX(filename, directed=True)`

makeFromCX("network.cx2") replaces the graph with a network in CX2
or CX (version 1), the formats of NDEx and Cytoscape's exchange
format: attributes (typed as declared), node positions, and the
default and per-node colours, sizes and shapes. Nodes are named by
their `name` (a name two nodes share gets the id added). CX edges have
a direction, as in Cytoscape; directed=false loads them undirected.

### `makeFromCYJS(filename)`

makeFromCYJS("network.cyjs") replaces the graph with Cytoscape.js
JSON, as Cytoscape exports for the web (File → Export → Network to
File → Cytoscape.js JSON) and as Cytoscape.js uses: each node's and
edge's data become fields, positions are kept, and compound (group)
nodes become the field `parent` of their members. Nodes are named by
their `name` (or label); a name two nodes share gets the node's id
added. exportCYJS writes the format.

### `makeFromCYS(filename, network=None)`

makeFromCYS("session.cys") opens a network from a Cytoscape session
file: its attributes, and positions, colours, sizes and shapes from
its view. A session can hold several networks: the first opens and
the others are listed; makeFromCYS(file, "name") or
makeFromCYS(file, 2) opens another, and makeFromCYS(file, "all") opens
each as a graph of its own (tabs above the graph; use(name) switches).
Styles (Cytoscape's visual mappings) aren't read.

### `makeFromNNF(filename)`

makeFromNNF("nested.nnf") replaces the graph with a Cytoscape nested
network file: lines `network node` (a node in a network) and `network
source type target` (an edge), # comments. Every network's nodes and
edges are loaded together: `network` says which network(s) each node
and edge is in, and a node named after a network (one that stands for
it, nested inside another) has that name in `nested`. So
showOnly(network == 'M1') shows one network, and
collapse(network == 'M1') folds a nested network into a node.

### `makeFromSIF(filename, directed=False)`

makeFromSIF("network.sif") replaces the graph with a Cytoscape SIF
file (simple interaction format): each line is `source type target
[target …]`, or a lone node name. If the file has tabs, fields are
tab-separated and names may contain spaces; otherwise names are
separated by spaces. The type goes in the edge field `interaction`
(colorize(interaction) shows it). directed=true makes every edge run
from source to target.

### `makeFromXGMML(filename)`

makeFromXGMML("network.xgmml") replaces the graph with an XGMML file,
Cytoscape's XML format: node and edge attributes (typed: string,
integer, real, boolean; lists joined with '; '), and each node's
graphics: position, size, fill and outline colour and shape. Files
with bare '&' characters (a common fault) are repaired as they are
read.

## Biology formats: PSI-MI (MITAB, XML), SBML, BioPAX, KEGG KGML, WikiPathways GPML

### `makeFromBioPAX(filename, mode='sif')`

makeFromBioPAX("pathway.owl") opens a BioPAX level 3 pathway (as
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
edges.

### `makeFromGPML(filename)`

makeFromGPML("WP707.gpml") opens a WikiPathways pathway (GPML 2013a
or 2021), drawn as on WikiPathways: data nodes at their positions,
with their colours, shapes and database references (`xref_db`,
`xref_id`). Interactions become edges with their `arrow`
(mim-conversion, mim-catalysis, mim-inhibition, Arrow, TBar, …). An
interaction that ends on another one (a catalysis on a conversion)
meets it at a small anchor node; groups that interactions point at
become nodes, and members have the group in `group`.

### `makeFromKGML(filename)`

makeFromKGML("hsa04115.xml") opens a KEGG pathway map (KGML), drawn
as on KEGG: genes, compounds and linked maps at their positions, in
their colours and shapes, labelled with the first name. Relations
become directed edges with `kind` (PPrel, GErel, ECrel, PCrel) and
`subtype` (activation, inhibition, phosphorylation, …); reactions
become edges from substrates to products with the `enzyme`. Entries
in a group (a complex) have the group in `group`.

### `makeFromMITAB(filename, merge=True)`

makeFromMITAB("interactions.txt") opens molecular interactions in
PSI-MI TAB (MITAB 2.5, 2.6 or 2.7), as IntAct, BioGRID, MINT and the
IMEx databases export them. Each interactor becomes a node named by
its gene name when the file gives one (else its short label or
identifier), with `ident`, `taxid`, `species`, `kind` and `aliases`.
Each pair becomes an edge with the detection `method`, `kind`
(interaction type), `pubmed`, `author`, `sourcedb`, `interaction` ids
and IntAct's `miscore`; repeated evidence for a pair is merged into
one edge with an `evidence` count (merge=false keeps one edge per
line). An interactor paired with itself is a self-loop.

### `makeFromPDB(source, cutoff=8.0, chain=None)`

makeFromPDB("1ubq") or makeFromPDB("protein.pdb") turns a protein
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
folded protein seen from its widest side.

### `makeFromPSIMI(filename, merge=True)`

makeFromPSIMI("interactions.xml") opens molecular interactions in
PSI-MI XML (2.5 or 3.0), with the same nodes and fields as
makeFromMITAB. An interaction with more than two participants is
expanded into pairs: from the bait to each prey when a bait is named
(spoke expansion), otherwise between every pair (matrix expansion);
the edge field `expansion` says which.

### `makeFromSBML(filename, reactions='nodes')`

makeFromSBML("model.xml") opens a systems biology model (SBML level
2 or 3). Species become nodes (`compartment`, `initial` amount or
concentration, `sbo`); each reaction becomes a small grey node, with
directed edges from its reactants and modifiers and to its products
(`role`, `stoichiometry`). reactions="edges" draws each reaction as
edges from reactants (and modifiers) to products instead. A species
name used in two compartments gets the compartment added, as
"ATP [cytosol]". Positions from the SBML layout package are kept.

## Import and export: Excel, RDF, Bluesky, JSON, KML, shapefiles, standalone HTML

### `exportJSON(filename='graph.json', format='graphology')`

exportJSON("graph.json") writes the graph for sigma.js and graphology
(graph.import(data)): nodes with label, x, y, size, colour and every data
field, edges with weight, size, colour and fields; hidden elements are
marked hidden. format="sigma" writes the older sigma.js JSON ({nodes:
[{id, label, x, y, size, color, attributes}], edges: [...]}) that
Gephi's JSON Exporter makes. Offered as a download.

### `exportKML(filename='graph.kml', lat=None, lon=None)`

exportKML("graph.kml") writes the graph for Google Earth and other
maps: each node with coordinates a placemark (its colour, label and
fields), each edge between two placed nodes a line (its colour and
width). Coordinates come from the latitude/lat and longitude/lon/lng
fields, or name them: exportKML("x.kml", lat="y", lon="x"). Offered as
a download.

### `exportSHP(filename='graph.zip', lat=None, lon=None)`

exportSHP("graph.zip") writes shapefiles for GIS (QGIS, ArcGIS) in a
zip: nodes.shp (points, with name, label, colour and the node fields)
and edges.shp (lines between placed nodes, with source, target,
weight, colour and the edge fields), in WGS 84 longitude/latitude.
Coordinates come from latitude/lat and longitude/lon/lng fields, or
name them with lat= and lon=. Field names are cut to 10 characters,
as the format requires. Offered as a download.

### `makeFromBluesky(handle, depth=1, limit=100, mode='follows', maxNodes=500)`

makeFromBluesky("alice.bsky.social") opens a Bluesky account's
network from the public API: the account and up to `limit` accounts it
follows, with directed "follows" edges. mode="followers" fetches who
follows it instead, "both" both. depth=2 also fetches the same for
each account found, adding the ties among them and new accounts, up
to maxNodes accounts in all. Nodes get handle, did, followers,
follows, posts and description; labels are display names.

### `makeFromCooccurrence(filename, column=None, separator=';', sheet=None, keep=True)`

makeFromCooccurrence("papers.csv", "authors") builds a network of the
values that share a cell: each row's list (split at separator, ";" by
default; also "," or "|") links every pair in it, as co-authors on a
paper or keywords on an article. Nodes get `count` (rows they appear
in); edges `weight` (rows they share). Works on .csv, .tsv and .xlsx
(sheet= picks a sheet); column= is a header name or a number (0 =
first; default: the first column whose cells hold lists). keep=true
also adds a node for a value that never shares a row.

### `makeFromExcel(filename, sheet=None, nodes=None, directed=False, source=None, target=None, interaction=None, weight=None, header=True)`

makeFromExcel("data.xlsx") replaces the graph with an Excel workbook
read as makeFromCSV reads tables: an edge sheet (Source, Target[, Type,
Weight, Label, ...]), an adjacency matrix or list; with a node sheet
(Id[, Label, ...]) too when the workbook has one. sheet= picks the edge
sheet by name or number (0 = first); nodes= names the node sheet, or
another file (.xlsx or .csv). Other columns become fields; directed=true
makes edges without a Type directed. makeFromCSV("data.xlsx") does the same.
source=, target=, interaction=, weight= and header= choose the edge
sheet's columns as in makeFromCSV.

### `makeFromRDF(filename, format=None, types=True)`

makeFromRDF("data.ttl") replaces the graph with RDF data (Turtle,
N-Triples or RDF/XML, by extension or content; format="turtle", "nt"
or "xml" to say). Each resource becomes a node (labelled by rdfs:label,
foaf:name, skos:prefLabel or its local name; its IRI in `uri`), each
property linking two resources an edge (its name in `predicate`), and
each literal property a node field (numbers and booleans typed).
types=false keeps rdf:type as a `type` field instead of edges to class
nodes. For SPARQL endpoints use makeFromSPARQL.

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

### `scratch()`

with scratch(): runs the block, then puts the graph back as it was
(which nodes and edges exist, and every value): for trying things out,
such as removing nodes and measuring the result. Fields made inside the
block are removed too; print or keep in variables what you want to keep.

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

### `liveCharts(on=True)`

liveCharts() makes every chart live, now and from now on: each is
recomputed after any command that changes the graph or the display.
liveCharts(False) turns that off. (The Live button on a chart does it
for one chart.)

### `plotDistrib(field, sortField=None, log=False)`

Each element's value of field, in rank order (or ordered by sortField).
log=true draws the values on a log axis.

### `plotFrequency(field, log=False, cumulative=False, fit=False, kmin=None, shift=0)`

plotFrequency(degree) plots, for each value of a numeric field, the
fraction of nodes (or edges) with that value: the degree distribution
p(k). log=true draws both axes on log scales (a power law is then a
straight line; zeros are left out). cumulative=true plots the fraction
with that value or more (the complementary cumulative distribution,
smoother for heavy tails). Pointing at the chart highlights the
elements with that value. fit=true adds a power law fitted by maximum
likelihood (fitPowerLaw; kmin= fixes where it starts, shift= fits k + shift)
as a dashed line.

### `plotHistogram(field, bins=10, log=False)`

Histogram of a numeric field's values in `bins` equal-width bins.
log=true uses bins of equal width on a log scale (for heavy-tailed
values such as degree; values <= 0 are left out) and a log count axis.

### `plotLine(data, title='Chart', xlabel='x', ylabel='y', log=False, logX=None, logY=None, dots=False, xrange=None, yrange=None, dashed=None, highlight=None)`

plotLine(points) draws a line chart of [(x, y), ...] pairs;
plotLine({"infected": pts1, "recovered": pts2}) draws one line per
series. log=true makes both axes logarithmic (or logX=/logY= one of
them; points <= 0 are left out). dots=true marks each point. A chart
with the same title replaces the last one, so calling it in a loop
updates it. yrange=(lo, hi) fixes the y axis (e.g. (0.8, 1) for values
near 1), xrange= the x axis. dashed=["fit", ...] draws those series
dashed and without dots (for theory curves and fits), and
highlight=["this network"] draws those series' points large, so a single
point stands out among simulated ones.

### `plotScatter(x, y=None, log=False, logX=None, logY=None, ends=False, title=None, xlabel=None, ylabel=None, line=None, xrange=None, yrange=None)`

plotScatter(degree, betweenness) plots one dot per node (or edge) at
(x, y), in its own colour; pointing at a dot highlights its element and
clicking selects it. plotScatter(age, ends=true) plots, for every edge,
the value of a node field at one end against the other (both ways round
for undirected edges), which shows assortative mixing. Data works too:
plotScatter([(x, y), ...]) or plotScatter({"name": points, ...}).
log=true uses log scales on both axes (logX=/logY= for one; values <= 0
are left out). line=[(x0, y0), (x1, y1), ...] adds a reference line,
e.g. y = x. xrange=/yrange=(lo, hi) fix the axes. A chart with the same
title replaces the last one.

### `plotSizes(field)`

Bar chart of how many elements share each value of field (largest first).

### `plotSizesPie(field)`

Pie chart of how many elements share each value of field.

### `showMatrix(order=None, weight=None, nodes=None, title=None, numbers=False, rows=None, cols=None)`

showMatrix() draws the adjacency matrix: a row and a column per
node, and a dark cell where an edge joins them (darker for a bigger
`weight` field value, when given). order=field sorts the rows and
columns by that field (a community, a group, a degree), with lines
between groups, so blocks and nested patterns show; nodes= limits it
to some nodes. Rows run from the sending node to the receiving one
for directed edges. Parallel edges add up; an undirected self-edge
counts 2 on the diagonal (1 if directed), as in the usual definition.
numbers=true writes each cell's value, zeros included (for small
matrices). rows= and cols= give two sets of nodes for a rectangular
matrix, e.g. the incidence matrix of a two-mode network:
showMatrix(rows=(kind == 'group'), cols=(kind == 'person'), numbers=true).
Hovering a cell highlights its edge and two nodes; clicking selects
them. Up to 600 rows and columns.

## Interface building (panels, widgets, timers, events)

### `Action(name, label=None)`

Action(name): one of GUESS's own commands for a menu or toolbar: "open",
"save", "png", "svg", "sample", "share-link", "share-viewer", "table",
"style", "filter", "variables", "help", "history", "search", "stop",
"tour", "manual", "fit", the tools "tool:select", "tool:lens",
"tool:path", "tool:heat", "tool:paint", "tool:cluster", "tools"
(the whole tool strip, for a toolbar) and "source" (an app's code).

### `after(seconds, fn)`

Call fn() once after `seconds` seconds; returns a timer with .stop().

### `Button(*a, **k)`

Button(text, onClick=fn): calls fn() when clicked; .enabled turns it on/off.

### `Chart(*a, **k)`

Chart(lambda: plotHistogram(degree)) puts a chart inside a panel
instead of the dock: the function makes the chart (any plot command, or
an Altair chart) and runs again after every command, so the chart
follows the graph. .refresh() redraws it now.

### `Checkbox(*a, **k)`

Checkbox(text, checked=False, onChange=fn): calls fn(checked) when toggled.

### `Column(*a, **k)`

Column(*widgets): widgets one under another.

### `Dropdown(*a, **k)`

Dropdown(options, value=None, label="", onChange=fn): a choice list; calls
fn(value) when the selection changes.

### `every(seconds, fn)`

Call fn() every `seconds` seconds; returns a timer with .stop().

### `everyPaced(fn, steps=None, slow=0.9, fast=0.15, ramp=3)`

everyPaced(step) calls step() again and again, slow-fast-slow, so a
process can be followed on screen: `slow` seconds apart for the first
`ramp` calls, speeding up to `fast`, and slowing down again over the
last `ramp` calls. Give steps= when the number of calls is known, or
let step() return how many calls are left (an int); returning False
stops. Returns a timer with .stop().

### `Group(*a, **k)`

Group(title, *widgets, collapsed=False): a titled box that can be folded.

### `Label(*a, **k)`

Label(text): a line of text in a panel; set .text to change it.
Label(lambda: f"{len(sel)} selected") is live: the function runs again
after every command and the label follows.

### `linkTo(element, text=None)`

linkTo(node) is Markdown for a small chip naming a node (or edge):
in a Markdown panel, pointing at the chip highlights the element in the
graph and clicking selects it. Good for listing a queue, a path or
search results beside the graph:
    Markdown(lambda: "Queue: " + " ".join(linkTo(n) for n in queue))
text= replaces the shown name (e.g. "v3 (d=2)").

### `Markdown(*a, **k)`

Markdown(text): a block of formatted text in a panel (headings, **bold**,
*italics*, `code`, lists and links). Set .text to change it; a function
makes it live, like Label.

### `Menu(title, *items)`

Menu(title, *items): a menu for ui.menubar; items are MenuItem, Action,
Separator (or "-").

### `MenuItem(*a, **k)`

MenuItem(label, run="code" or onClick=fn, shortcut=""): an item for
Menu(...) or a menu bar. run= runs Gython as a command (one undo step).

### `openURL(url)`

Open a web page in a new browser tab.

### `Panel(*a, **k)`

Panel(title, *widgets, position="bottom", vertical=False). Show with
ui.dock(p), or place it with ui.layout(left=p, …). position is "bottom",
"right" or "left".

### `Row(*a, **k)`

Row(*widgets): widgets side by side.

### `Separator()`

Separator(): a line between menu or toolbar items.

### `Slider(*a, **k)`

Slider(min, max, value=None, step=1, label="", onChange=None, onSlide=None).
onChange fires on release, onSlide while dragging.

### `stopTimers()`

Stop all timers.

### `Tab(*a, **k)`

Tab(title, *widgets): one page of a Tabs.

### `Tabs(*a, **k)`

Tabs(Tab("Network", …), Tab("Style", View("style")), …): tabbed pages
in a panel; .selected is the title of the tab showing.

### `TextField(*a, **k)`

TextField(value="", placeholder="", onEnter=None): onEnter(text) on Return.

### `View(*a, **k)`

View(name) puts one of GUESS's own views inside a panel or tab: "table"
(the data table), "style", "filter", "variables", "help", "timeline" or
"console".

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

### `distinctColors(count, seed=1)`

distinctColors(count): count clearly different colours (as "r,g,b" strings), the
most different first — the categorical palette colorize(field) uses.

### `generateColors(*args)`

generateColors(start, end, n) or generateColors(start, middle, end, n).

### `randomColor(alpha=None)`

A random color "r,g,b"; randomColor(alpha) adds an alpha (0..255).

## Examples

The same examples are searchable in the app's Help panel and command palette (Cmd/Ctrl+K).

### Basics

**Colour nodes by a query**

```python
(freq > 100).color = red
```

**Nodes with a field value**

```python
dept == 'dept3'
```

**Pattern match names**

```python
name like 'v1%'
```

**Combine queries**

```python
(dept == 'dept1') & (totaldegree > 3)
```

**Loop over a set**

```python
for n in (dept == 'dept3'):
    n.labelvisible = true
```

**Edges between two groups**

```python
(dept == 'dept1') <-> (dept == 'dept3')
```

**Directed edges**

```python
v1 -> g.nodes
```

**Any edges touching a node**

```python
v1 ? g.nodes
```

**Neighbours of a node**

```python
v1.getNeighbors()
```

**Add nodes and edges**

```python
addNode('zed', color=red)
addEdge(zed, v1)
```

**Remove and restore**

```python
remove(totaldegree == 0)
add(g.deleted)
```

**Undo the last command**

```python
undo()
```

### Appearance

**A colour per category**

```python
colorize(dept)
```

**Gradient by value**

```python
colorBy(freq, yellow, red, 'log')
```

**Size by importance**

```python
sizeBy(pagerank, 5, 40, 'sqrt')
```

**Size by rank of a field**

```python
resizeLinear(totaldegree, 5, 30)
```

**Labels from a field**

```python
labelBy(dept)
```

**Shapes per category**

```python
shapeBy(dept)
```

**Legend for a mapping**

```python
colorize(dept)
legendFor(dept)
```

**Edge width by weight**

```python
sizeBy(freq, 1, 8)
```

**Curved, mixed-colour edges**

```python
curvedEdges()
setEdgeColorMode('mixed')
```

**Line styles and arrowheads**

```python
lineStyleBy(directed)
g.edges.arrowhead = 'swept'
```

**Tapered or arrowed directed edges**

```python
directedEdges('taper')
directedEdges('arrow')
```

**Readable labels**

```python
labelOutlines()
hideOverlappingLabels()
```

**Shade a group**

```python
createConvexHull(dept == 'dept1', '200,200,255,90')
```

**Ellipse or box around a group**

```python
encircle(dept == 'dept1')
encircle(dept == 'dept2', 'box')
```

**A shape around every group**

```python
encircleBy(dept)
```

**Dark background**

```python
setDisplayBackground(black)
```

**Save a named style**

```python
defineStyle('by dept', ['colorize(dept)', 'legendFor(dept)'])
applyStyle('by dept')
```

**Polygon nodes**

```python
(dept == 'dept1').style = polygon(5)
polygonBy(dept, 3, 8)
```

**Word cloud of a text field**

```python
wordCloud(dept)
```

### Layouts

**ForceAtlas2**

```python
forceAtlas2Layout()
```

**ForceAtlas2, tighter clusters**

```python
forceAtlas2Layout(linLog=true, preventOverlap=true)
```

**GEM layout**

```python
gemLayout()
```

**Kamada-Kawai**

```python
kkLayout()
```

**Hierarchy**

```python
sugiyamaLayout()
```

**Hive plot**

```python
hiveLayout(dept, pagerank, axes=5)
```

**Radial around a node**

```python
radialLayout(v1)
```

**Remove overlaps**

```python
noverlapLayout()
```

**Pack components**

```python
binPackLayout()
```

**Rotate / mirror**

```python
rotateLayout(90)
mirrorLayout()
```

**One column per group**

```python
multipartiteLayout(dept)
```

**Rings by importance**

```python
concentricLayout(degree)
```

**Hubs inside, the rest outside**

```python
dualCircleLayout(10)
```

**Order by a field, untangle the rest**

```python
orderedLayout(degree)
```

**Hairball Buster plot**

```python
hairballLayout()
g.edges.visible = false
```

**Nested circles by group**

```python
circlePackLayout(dept)
```

**Layers in 3D-style planes**

```python
isometricLayout(dept)
```

**Two centres of gravity**

```python
forceAtlas2Layout(gravitySources=[v1, v73])
```

**Spread out part of a layout**

```python
rescaleLayout(dept == 'dept1', 1.5)
```

**Stars, rings and grids (structure-aware)**

```python
motifLayout(outline=true)
```

### Analysis

**Summary statistics**

```python
graphStats()
```

**Communities**

```python
louvainClusters()
colorize(louvain_class)
```

**Most central nodes**

```python
sortBy(pagerank)[-10:]
```

**Label the hubs**

```python
(betweenness > 1000).labelvisible = true
```

**Shortest path**

```python
shortestPath(v1, v14).color = red
```

**Distance heat map**

```python
heatMap(v1)
```

**Groups as charts**

```python
plotSizesPie(dept)
```

**Distribution chart**

```python
plotHistogram(pagerank)
```

**SQL over fields**

```python
sql('select dept, count(*) from nodes group by dept')
```

**Weak points**

```python
bridges().color = red
cutNodes().size = 30
```

**Backbone**

```python
showOnly(spanningTree(maximum=True))
```

**Brokers**

```python
sortBy(constraint)[:5]
```

**Homophily**

```python
assortativity(dept)
mixingMatrix(dept)
```

**Compare partitions**

```python
louvainClusters()
compareClusters(louvain_class, dept)
```

**Any networkx algorithm**

```python
import networkx as nx
setField(nx.community.greedy_modularity_communities(toNetworkX()), 'greedy')
colorize(greedy)
```

**Classic networks**

```python
makeSample('karate')
colorize(club)
```

**Leiden communities**

```python
leidenClusters()
colorize(leiden_class)
```

**Communities in directed graphs**

```python
infomapClusters()
colorize(infomap_class)
```

**Similar nodes**

```python
similarTo(v1).color = red
```

**Likely missing links**

```python
predictLinks(10)
```

**Find a pattern**

```python
findPattern([('a','b'), ('b','c'), ('c','a')])
```

**Large-graph layout**

```python
drlLayout()
```

**Layered drawing (Graphviz)**

```python
dotLayout(rankdir='LR')
```

**Stress layout (Graphviz)**

```python
neatoLayout()
```

**Remove overlaps, keep shape**

```python
removeOverlap()
```

**Labels inside nodes**

```python
g.nodes.labelvisible = true
fitNodesToLabels()
```

**Labels where there's room**

```python
g.nodes.labelvisible = true
g.nodes.labelpos = 'outside'
```

**Labels off the edges**

```python
g.nodes.labelpos = 'outside'
labelPlacement('particles')
```

**Polish label positions**

```python
optimizeLabels(2)
```

**Labels that stay readable when zooming**

```python
constantLabelSize()
```

**Excentric labelling lens**

```python
excentricLens(radius=80)
```

**Label size by a field**

```python
labelSizeBy(pagerank, 0.8, 2)
```

**Edge labels**

```python
labelBy(freq)
edgeLabelsAlong()
```

**Katz and prestige**

```python
highest(katz, 5)
highest(domain_prestige, 5)
```

**Bridging centrality**

```python
colorBy(bridging, yellow, red)
highest(bridging, 5)
```

**Weighted bridging**

```python
weightedBridging()
highest(wbridging, 5)
```

**Maximal cliques**

```python
cliques(4)
```

**Test link prediction**

```python
evaluateLinks('all')
```

**Coordinates from MDS**

```python
mds(2)
scatterLayout(mds1, mds2)
```

**Chinese Whispers communities**

```python
chineseWhispersClusters()
colorize(cw_class)
```

**Markov clustering (MCL)**

```python
mclClusters(inflation=2)
colorize(mcl_class)
```

**Clusters of nearby nodes**

```python
dbscanClusters()
colorize(dbscan_class)
```

**Dense complexes (MCODE)**

```python
mcodeClusters()
(mcode_class == 0).color = red
```

**Overlapping communities**

```python
cs = cliquePercolationClusters(3)
showOverlaps(cs)
```

**Communities of edges**

```python
linkCommunities()
showOverlaps(link_classes)
```

**Bundle edges**

```python
bundleEdges()
```

**Force-directed edge bundling**

```python
bundleEdges(method='fdeb')
```

### Filtering and selection

**Show only a core**

```python
showOnly(kCore(3))
```

**Ego network**

```python
showOnly(egoNetwork(v1, 2))
```

**Largest component**

```python
showOnly(giantComponent())
```

**Edges inside communities**

```python
showOnly(intraEdges(louvain_class))
```

**Show everything again**

```python
showAll()
```

**The k-brace core**

```python
showOnly(kBrace(2))
```

**Keep nodes listed in a file**

```python
showOnly(readNames('keep.txt'))
```

**Select from code**

```python
select(dept == 'dept2')
```

**Act on the selection**

```python
sel.color = orange
center(sel)
```

**Table of a set**

```python
table(dept == 'dept3')
```

### Files and sessions

**Load Gephi's format**

```python
makeFromGEXF('graph.gexf')
```

**Load spreadsheets**

```python
makeFromCSV('edges.csv', 'nodes.csv')
```

**Export for Gephi**

```python
exportGEXF('graph.gexf')
```

**Save a session**

```python
saveSession('work.guess')
```

**Save what you ran**

```python
saveHistory('work.py')
```

**Snapshot and morph**

```python
ss('before')
circleLayout()
morph('before', 2000)
```

**Random graph**

```python
makeBarabasiAlbertRandom(5, 2, 300)
```

**Small-world graph**

```python
makeWattsStrogatz(100, 4, 0.1)
```

**Open an Excel workbook**

```python
makeFromExcel('network.xlsx')
```

**Open any network file**

```python
makeFromFile('network.xml')
```

**Choose the edge columns**

```python
makeFromCSV('ppi.tsv', source='gene_a', target='gene_b', interaction='type')
```

**Open a Cytoscape SIF file**

```python
makeFromSIF('network.sif')
colorize(interaction)
```

**Open Cytoscape.js JSON**

```python
makeFromCYJS('network.cyjs')
```

**Export for Cytoscape**

```python
exportCYJS('graph.cyjs')
```

**Open a CX or CX2 network**

```python
makeFromCX('network.cx2')
```

**Open XGMML**

```python
makeFromXGMML('network.xgmml')
```

**Networks from a Cytoscape session**

```python
makeFromCYS('analysis.cys', 'all')
```

**Interactions from IntAct (MITAB)**

```python
makeFromMITAB('intact.txt')
```

**PSI-MI XML interactions**

```python
makeFromPSIMI('interactions.xml')
```

**A systems biology model (SBML)**

```python
makeFromSBML('model.xml')
```

**A Reactome pathway (BioPAX)**

```python
makeFromBioPAX('pathway.owl')
```

**A KEGG map**

```python
makeFromKGML('hsa04115.xml')
```

**A WikiPathways pathway**

```python
makeFromGPML('WP707.gpml')
```

**Co-authors from a list column**

```python
makeFromCooccurrence('papers.csv', 'authors', ';')
```

**Open RDF / Turtle**

```python
makeFromRDF('foaf.ttl')
```

**A Bluesky follow network**

```python
makeFromBluesky('bsky.app', limit=50)
```

**Change a field's type**

```python
castField(year, INTEGER)
```

**An interactive web page**

```python
exportHTML('graph.html')
```

**Export for sigma.js**

```python
exportJSON('graph.json')
```

**Export to Google Earth**

```python
exportKML('graph.kml')
```

**Export shapefiles for GIS**

```python
exportSHP('graph.zip')
```

**Follow a live stream**

```python
streamFrom('http://localhost:8080/workspace1?operation=getGraph')
```

**Let an AI assistant help**

```python
connectAssistant()
```

### Interface building

**A slider that filters**

```python
s = Slider(freq.min, freq.max, label='min freq')
def update(v):
    (freq < v).visible = false
    (freq >= v).visible = true
s.onChange = update
ui.dock(Panel('Filter', s))
```

**React to clicks**

```python
graphevents.clickNode = lambda n: center([n] + n.getNeighbors())
```

**Record a movie**

```python
startMovie(30, 'run.webm')
gemLayout()
stopMovie()
```

**Save an image per step, as one zip**

```python
startImages('steps.zip')
for k in [1, 2, 3]:
    (degree >= k).color = red
    exportPNG('step_%d.png' % k)
stopImages()
```

**Arrange the window like an app**

```python
ui.layout(left=Tabs(Tab('About', Markdown('### My app')), Tab('Style', View('style'))), bottom=View('table'))
```

**A live label**

```python
ui.statusbar(Label(lambda: f'{len(sel)} selected'))
```

**Your own menu**

```python
ui.menubar(Menu('Tools', MenuItem('Communities', run='louvainClusters()'), Action('table')), keep=['Help'])
```

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
| `strokewidth` | DOUBLE | 0.0 |
| `labelcolor` | VARCHAR | None |
| `fixed` | BOOLEAN | False |
| `style` | INTEGER | 2 |
| `width` | DOUBLE | 10.0 |
| `height` | DOUBLE | 10.0 |
| `label` | VARCHAR | None |
| `image` | VARCHAR | None |
| `labelvisible` | BOOLEAN | False |
| `labelpos` | VARCHAR | 'right' |
| `labelsize` | DOUBLE | 1.0 |
| `indegree` | INTEGER | 0 (read-only) |
| `outdegree` | INTEGER | 0 (read-only) |
| `totaldegree` | INTEGER | 0 (read-only) |
| `degree` | INTEGER | 0 (read-only) |

Built-in edge fields:

| field | type | default |
|---|---|---|
| `node1` | VARCHAR | None (read-only) |
| `node2` | VARCHAR | None (read-only) |
| `directed` | BOOLEAN | False (read-only) |
| `source` | VARCHAR | None (read-only) |
| `destination` | VARCHAR | None (read-only) |
| `color` | VARCHAR | 'dandelion' |
| `labelcolor` | VARCHAR | None |
| `visible` | BOOLEAN | True |
| `width` | DOUBLE | 2.0 |
| `weight` | DOUBLE | 1.0 |
| `label` | VARCHAR | None |
| `labelvisible` | BOOLEAN | False |
| `labelsize` | DOUBLE | 1.0 |
| `linestyle` | VARCHAR | 'solid' |
| `arrowhead` | VARCHAR | 'triangle' |
| `arc` | DOUBLE | 0.0 |

Computed node fields (calculated the first time they are used, by name or
as `n.<field>`; `recompute()` after editing the graph): `pagerank`, `hub`, `authority`, `eigenvector`, `closeness`, `harmonic`, `eccentricity`, `clustering`, `triangles`, `coreness`, `strength`, `component`, `strongcomponent`, `betweenness`, `degrank`, `hits`, `rwbetweenness`, `knn`; edge field `betweenness`.

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
