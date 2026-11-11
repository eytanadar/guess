# Gephi plugins and GUESS

This compares each plugin in the Gephi plugin store with what GUESS can do
today, and what each missing one would take.

The list comes from `plugins/plugins.json` on the `gephi-plugins`
repository's `gh-pages` branch: 101 published entries. Duplicates and
version splits are merged here (Twitter v1 and v2, two Girvan–Newman
plugins, two Clique Percolation plugins, the BoundingDiameters suite and
UI), as are support modules that aren't features (JettyWrapper,
StreamingAPI/Impl/Server). Where a plugin's source is on `master-forge`,
its README was read. GUESS's side comes from `docs/API.md` (343 commands)
and the code.

**Status**

| mark | meaning |
|---|---|
| ✅ | GUESS has an equivalent |
| ◐ | partial: close, or one line of Gython away |
| ✗ | missing |
| n/a | can't apply to a browser app, or the service is gone |

**Effort** for missing pieces:

| size | means |
|---|---|
| S | under a day, usually a wrapper around networkx or igraph (both load in Pyodide) |
| M | a few days |
| L | a week or more |

## Status: implemented (November 2026)

The plan at the end of this document has been carried out. Every row below
marked ◐ or ✗ now has a GUESS command, except true 3D (an isometric
projection stands in for it), and the rows marked n/a or ?.

| area | new in GUESS |
|---|---|
| measures | computed fields `katz`, `domain_prestige`, `proximity_prestige`, `rank_prestige`, `bridging_coef`, `bridging`, `wclustering`; `weightedBridging`, `cliques`, `mds`, `geoVectors`, `kBrace`, `evaluateLinks`, `predictLinks(add=true)` |
| clustering | `chineseWhispersClusters`, `mclClusters`, `dbscanClusters`, `mcodeClusters`, `cliquePercolationClusters`, `linkCommunities`, and `showOverlaps` for overlapping communities (pies and hulls) |
| layouts | `multipartiteLayout`, `concentricLayout`, `dualCircleLayout`, `orderedLayout`, `hairballLayout`, `circlePackLayout`, `isometricLayout`; `rescaleLayout(nodes, …)`, `forceAtlas2Layout(gravitySources=…)` |
| generators | `makeWattsStrogatz`, `makeBarabasiAlbertAging`, `makeGeometricRandom`, `makePowerlawCluster` |
| import | `makeFromExcel` (and `.xlsx` in `makeFromCSV`), `makeFromCooccurrence`, `makeFromRDF` (Turtle, N-Triples, RDF/XML), `makeFromBluesky`, `streamFrom` / `stopStream` (Gephi streaming protocol over HTTP or WebSocket) |
| export | `exportHTML` (standalone interactive page), `exportJSON` (graphology / sigma), `exportKML`, `exportSHP` |
| display and tools | `polygon(n)` and `polygonBy(field)` (regular polygons), `wordCloud(field)`, `castField`, `readNames`, `copyColors` |
| AI assistants | `mcp/guess-mcp.mjs` (MCP server, no dependencies) with `connectAssistant()` / `disconnectAssistant()` |

The manual and the cookbooks cover these, with new recipes in the biology,
SNA, text, infrastructure and core books.

## Summary (before implementation)

| status | count | plugins |
|---|---|---|
| ✅ equivalent | 34 | most layouts, metrics, community detection, generators, importers, display |
| ◐ partial | 22 | a thin wrapper or one option short (Katz, prestige, multipartite, scale part of a layout, Excel, …) |
| ✗ missing | 21 | 3D layouts, MCL/MCODE/link communities, KML/SHP/JSON export, streaming, word cloud, AI control |
| n/a | 6 | Oracle, AgensGraph, Twitter, Polinode, Linkfluence, HttpGraph (needs a proxy) |
| ? | 2 | GC-Viz, Architectural GraphML: no source or description |

Counts are table rows. A row can cover several plugins that do the same
thing (for example Sigma, Loxa, OpenSeadragon and web publishing).

Most gaps are small: an algorithm networkx, igraph or a pure-Python package
already has, plus a GUESS command with a docstring and a test. Four are
larger:

1. **3D.** GUESS draws in 2D. Isometric or z-layer projection fits within
   2D; true 3D does not.
2. **Live streaming.** GUESS can already apply patches. What's missing is a
   client for Gephi's streaming protocol, or a WebSocket feed.
3. **Standalone web export.** `exportApp` needs a running GUESS. A
   self-contained HTML viewer would cover Sigma, Loxa, OpenSeadragon and
   web publishing at once.
4. **AI control (MCP).** This needs a bridge between an MCP server and the
   page.

## Layouts

| plugin | GUESS today | | what it would take |
|---|---|---|---|
| GeoLayout | `geoLayout()` (Mercator, Albers, …) | ✅ | |
| Map of Countries | `geoLayout(map="world"\|"usa")` draws outlines | ✅ | other maps would need Natural Earth admin-1 data in `mapdata.py` (S) |
| Graphviz Layout | `dotLayout`, `neatoLayout`, `sfdpLayout`, `fdpLayout`, `circoLayout`, `twopiLayout`, `osageLayout` | ✅ | |
| Noverlap | `noverlapLayout()`; also `removeOverlap()` | ✅ | |
| OpenOrd | `drlLayout()` (DrL is OpenOrd's predecessor) | ✅ | |
| Layered Layout | `sugiyamaLayout()`, `dotLayout()` | ✅ | |
| Hiveplot Layout | `hiveLayout()` | ✅ | |
| MdsLayout (positions from two columns) | `scatterLayout(x, y)` | ✅ | |
| Position Ranking (map a field to x or y) | `scatterLayout(x, y)` with any numeric fields | ✅ | |
| Community Clusters | `fdpLayout(clusters=dept)`, `osageLayout(dept)` | ✅ | a force layout with one attractor per group would match Gephi's look more closely (S) |
| Circular Layout | circle: `circleLayout()`; radial axes: `hiveLayout()` | ◐ | the dual-circle layout (hubs inside, the rest outside) needs `dualCircleLayout(count)` (S) |
| Alphabetical Sorter | `circleLayout()` puts nodes on a circle; `sortBy` orders them | ◐ | an `order=` field for `circleLayout` and a grid sorter (S) |
| Concentric Layout | `twopiLayout(root)` puts nodes on rings by distance from a root | ◐ | rings by a field's value, as in `concentricLayout(degree)` (S) |
| Multipartite Layout | `bipartiteLayout(field)` does two rows | ◐ | k columns, one per field value; networkx `multipartite_layout` (S) |
| Scale layout (expand or contract part of the graph) | `rescaleLayout()` scales the whole graph | ◐ | an optional set argument, scaling about the set's centre (S) |
| Ordered Layout / EventGraphLayout (one axis fixed by a field, force on the other) | `scatterLayout`, `dagLayout`, `sugiyamaLayout` | ◐ | a `fixedAxis="x"` option for `forceAtlas2Layout` that holds x at a field and moves only y (S–M) |
| Hairball Buster (node-neighbour centrality) | the `knn` field (average neighbour degree); `scatterLayout(degree, knn)` | ◐ | the HB plot itself: each node at its degree, its neighbours spread above it (S) |
| MultiGravity ForceAtlas 2 | `forceAtlas2Layout(gravity=…)` with one centre | ✗ | gravity towards several nodes (`gravitySources=[v1, v2]`) in GUESS's own FA2 code (S–M) |
| Circle Pack | `osageLayout` packs rectangles | ✗ | hierarchical circle packing by one or more fields: port d3-hierarchy's `pack`, or use the pure-Python `circlify` (M) |
| Force Atlas 3D, Random 3D | 2D only | ✗ | a `z` field plus a WebGL 3D view with orbit and pick (L); a cheap first step is a `z` field and a projected `isometricLayout` |
| Isometric Layout, Network Splitter 3D (z layers from a field) | — | ✗ | 2D isometric projection of layers by a field: x' = x + z·cos30°, y' = y − z·sin30°, with optional layer hulls (S). Fits the current renderer |
| GC-Viz | — | ? | no source or description in the store; can't assess |

## Metrics and statistics

| plugin | GUESS today | | what it would take |
|---|---|---|---|
| Edge Betweenness Metric | edge field `betweenness` | ✅ | |
| Clustering Coefficient | `clustering` field, `averageClustering()`, `transitivity()` | ✅ | |
| BoundingDiameters (fast diameter and radius) | `diameter()`, `radius()`, the `eccentricity` field | ✅ | the BoundingDiameters algorithm only matters past about 10⁵ nodes |
| Weakly connected components (disjoint set) | `component` field, `weakComponentClusters()` | ✅ | |
| Spanning Tree / Minimum Spanning Tree | `spanningTree(maximum=False)` | ✅ | |
| Lineage (ancestors and descendants of a node) | `ancestors(node)`, `descendants(node)` | ✅ | a field holding signed distance from the origin, as Lineage writes, is one loop of Gython |
| Social Network Analysis (general measures) | pagerank, closeness, harmonic, eigenvector, hits, coreness, `graphStats()`, `report()` … | ✅ | |
| Clique Detector | `largestCliques()` | ◐ | all maximal cliques via networkx `find_cliques` as `cliques(minSize)` (S) |
| Katz Centrality | `setField(nx.katz_centrality(toNetworkX()), "katz")` | ◐ | a computed `katz` field next to `pagerank` (S) |
| Prestige (indegree, domain, proximity, rank) | `indegree`; `ancestors()` gives domain | ◐ | four computed fields from `ancestors` and BFS distances (S) |
| Weighted Cluster Coefficient | `clustering` ignores weights | ◐ | `clustering(weight="weight")` with networkx or igraph `transitivity_local_undirected(weights=)` (S) |
| MdsMetric (MDS to k dimensions as fields) | `mdsLayout()` (2D positions), `embed(dims)` (node2vec) | ◐ | `mds(dims=k)` storing `mds1..k` fields: classical MDS is a few numpy lines (S) |
| Bridging Centrality / Weighted Bridging Centrality | `betweenness` | ✗ | bridging coefficient × betweenness, weighted with distance 1/w (S) |
| VectorStatistics (mean edge length and direction from lat/lon) | `geoDistance()` stores edge lengths | ✗ | edge bearings and the resultant vector, as `geoVectors()` (S) |
| Link Prediction | `predictLinks(method=…)` lists likely edges | ◐ | `add=True` to add them marked by method, and an evaluation against a held-out graph (S) |

## Communities and clustering

| plugin | GUESS today | | what it would take |
|---|---|---|---|
| Leiden Algorithm | `leidenClusters()` | ✅ | |
| Label Propagation | `labelPropagationClusters()` | ✅ | |
| Girvan–Newman / Newman–Girvan | `edgeBetweennessClusters(count)` | ✅ | |
| Groups By Partition (one node per group) | `collapseBy(field)`; `blockmodel()` | ✅ | |
| Chinese Whispers | — | ✗ | close to weighted label propagation, about 20 lines (S) |
| Markov Cluster (MCL) | — | ✗ | numpy: expansion and inflation of the column-stochastic matrix; or the `markov_clustering` package (S) |
| Clique Percolation | — | ✗ | networkx `k_clique_communities` (S). Communities overlap, so the result needs a multi-valued field (node → list) shown with `pieChart` or hulls (M with display) |
| Link Communities (Ahn et al.) | — | ✗ | Jaccard edge similarity and single-linkage clustering with scipy, cut at maximum partition density. Communities overlap too (M) |
| MCODE | — | ✗ | vertex weighting by k-core density and seed growth; no maintained Python package (M) |
| DBSCAN (on positions or fields) | — | ✗ | scikit-learn's DBSCAN, which Pyodide provides; `dbscanClusters(fields=(x, y), eps, minPts)` (S) |

## Filters

| plugin | GUESS today | | what it would take |
|---|---|---|---|
| Top Weight Edge Filter | `showOnly(highest(weight, 100))` | ✅ | |
| FilterFromFile (keep nodes listed in a file) | `showOnly([n for n in g.nodes if n.name in open("keep.txt").read().split()])` | ◐ | a `readNames(file)` helper to make it one call (S) |
| KBrace Filter | — | ✗ | the k-brace (edges in at least k triangles or k-embedded): iterative removal; networkx `k_truss` is close (S) |

## Generators

| plugin | GUESS today | | what it would take |
|---|---|---|---|
| Erdős–Rényi | `makeErdosRenyiRandom(n, p)` (G(n,p)), `makeSimpleRandom(n, m)` (G(n,m)) | ✅ | |
| Kleinberg | `makeKleinbergRandom(size, clust)` | ✅ | |
| Complex Generators (Watts–Strogatz, …) | `fromNetworkX(nx.watts_strogatz_graph(100, 4, 0.1))` | ◐ | named commands for the common models (S) |
| Barabási–Albert with ageing | `makeBarabasiAlbertRandom` without ageing | ◐ | an attachment probability that decays with node age (S) |
| Random Waypoint / Lévy Walk mobility generators | — | ✗ | agents moving in a plane, an edge while within range, written as ranges for the timeline (M) |
| Architectural GraphML | — | ? | no source; it seems to build a graph from building floor plans. Can't assess |
| HttpGraph (the web as you browse) | — | n/a | needs a local HTTP proxy. The nearest in-browser equivalents are `makeFromWikipedia`, `makeFromOpenAlex` and `makeFromURL` |

## Import and data sources

| plugin | GUESS today | | what it would take |
|---|---|---|---|
| Similarity Computer | `makeFromSimilarity()` | ✅ | |
| Multimode Networks Transformation | `project(field, keep)` | ✅ | |
| Neo4j | `makeFromCypher()` over the HTTP API | ✅ | Bolt itself would need `neo4j-driver` over WebSockets (M); HTTP covers the use |
| Virtuoso Importer | `makeFromSPARQL(query, endpoint=…)` | ✅ | |
| Excel and CSV to networks | `makeFromCSV`, `makeFromTwoMode` | ◐ | `.xlsx` via openpyxl (pure Python, installable in Pyodide), feeding the CSV path; also a co-occurrence mode for one cell holding several values (S) |
| SemanticWebImport (RDF and RDFS files) | SPARQL endpoints only | ◐ | local RDF/Turtle/N-Triples files via rdflib (pure Python): triples become edges, literals become fields (S–M) |
| Graph Streaming (Gephi streaming protocol) | — | ✗ | a `streamFrom(url)` client reading Gephi's JSON events (`an`, `ae`, `cn`, `dn` …) with `fetch` streaming or WebSocket, each applied as a patch. Only cross-origin servers that allow it (CORS) will work. A desktop bridge could be the server side (M) |
| Bluesky / AT Protocol | — | ✗ | the public AppView (`public.api.bsky.app`, CORS-open): `app.bsky.graph.getFollows` and `getFollowers` for a follow network from a handle (S–M) |
| Twitter Streaming Importer (v1, v2) | — | n/a | the API is closed or paid |
| Oracle Driver | `sql()` on in-memory tables | n/a | a browser can't open database connections |
| AgensGraph | — | n/a | PostgreSQL protocol, as above, unless it offers an HTTP endpoint |

## Export and publishing

| plugin | GUESS today | | what it would take |
|---|---|---|---|
| Image Preview (images in nodes) | the `image` field | ✅ | |
| Publish your network to the web / Loxa / SigmaExporter / OpenSeadragon | `exportApp()` (a `.guess` file opened by GUESS with `?app=1`); `exportSVG()` | ◐ | a self-contained `exportHTML()` with the data inlined and a light read-only viewer (pan, zoom, hover, search) (M). A zoomable deep-zoom image is less useful given SVG |
| JSON Exporter (sigma.js / graphology JSON) | GEXF, GraphML, GML, DOT, GDF, CSV | ✗ | `exportJSON()` in graphology's format: `{nodes:[{key, attributes}], edges:[…]}` with x, y, size and color (S) |
| ExportToEarth / Google Maps exporter (KML) | — | ✗ | `exportKML()` from lat/lon: placemarks for nodes, LineStrings for edges, colours as KML `aabbggrr` (S) |
| SHPExporter (shapefiles) | — | ✗ | pyshp (pure Python) writing point and line layers, zipped (S) |
| PolinodeExporter | — | n/a | upload to a commercial service |

## Display and appearance

| plugin | GUESS today | | what it would take |
|---|---|---|---|
| Shape by Partition | `shapeBy(field)` | ✅ | |
| Multi Colour Renderer | `pieChart([...])`, `pieNeighbors(field)` | ✅ | |
| Give Colors To Nodes / Edges (colour from a hex or RGB column) | `g.nodes.color = hexcolor` (colours take names, `#hex` or `"r,g,b"`) | ✅ | |
| Node Color Manager (share colours between graphs) | several graphs (`use`); `defineStyle` / `applyStyle` | ◐ | `copyColors(fromGraph)` matching nodes by name (S) |
| Polygon Shaped Nodes | circle, rect, round rect, triangle, diamond, hexagon (`style`) | ◐ | regular n-gons with a sides field: generalise `polyPoints` in `renderer.ts` and the SVG export (S) |

## Tools

| plugin | GUESS today | | what it would take |
|---|---|---|---|
| Scripting Plugin (Python console) | GUESS is built around one (Gython) | ✅ | |
| Inspector | hover tooltips (`hoverFields`), the data table, provenance | ✅ | |
| Column Calculator | `g.nodes.score = …` and `for n in g.nodes: n.f = …` | ✅ | |
| Recast column (change a field's type) | `addNodeField` plus a loop | ◐ | `castField(field, INTEGER)` (S) |
| Word Cloud (frequent words in a text field) | `makeFromText` builds term networks | ✗ | `wordCloud(field)`: counts with stop words, drawn with Vega's `wordcloud` transform. GUESS embeds Vega, so `showChart` could take a raw Vega spec, linked so a word highlights the nodes containing it (S–M) |
| Gephi AI (control Gephi from Claude and other assistants over MCP) | — | ✗ | an MCP server exposing GUESS commands, with a bridge into the open page so tools run as console cells, keeping undo and history. Alternatively an in-app assistant, which needs a server-side proxy to keep the API key out of the browser (L) |
| Linkfluence Plugin | — | n/a | private tooling for one company |

## Suggested order

If the aim is to cover what Gephi users reach for:

1. **Small wrappers (one or two days in all):**
   - computed fields `katz` and the four prestige measures;
   - bridging centrality, weighted clustering, `cliques()`;
   - `chineseWhispersClusters`, `mclClusters`, `dbscanClusters`;
   - `exportJSON`, `exportKML`;
   - `.xlsx` in `makeFromCSV`;
   - multipartite and concentric layouts;
   - `rescaleLayout(seq, …)`, `castField`.
2. **Overlapping communities:** clique percolation and link communities.
   These need a multi-valued membership field and a way to show it (pies or
   hulls).
3. **`exportHTML()`:** a standalone viewer, which replaces four publishing
   plugins.
4. **Streaming:** `streamFrom(url)` for Gephi's streaming protocol, and
   Bluesky import.
5. **Isometric z-layers in 2D.** Full 3D only if people ask for it.
6. **MCP control:** largest effort, and a design decision about where the
   key and server live.
