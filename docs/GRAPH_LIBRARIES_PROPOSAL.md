# Features from networkx, igraph and Graphviz (proposal, 2026-11-09)

GUESS should add a public networkx bridge and a set of cheap analysis
commands first. Next, it should move heavy computations to igraph's C core,
then add Graphviz layouts through a WebAssembly build.

This proposal comes from three surveys of the library sources (`networkx/`,
`python-igraph/`, `graphviz/`, reference checkouts ignored by git), each
checked against GUESS's 247 commands in [API.md](API.md). The surveys read
code and docs and ran nothing; speeds and sizes below are estimates.

## How the three libraries divide the work

| Library | Role for GUESS | In the browser today |
|---|---|---|
| **networkx** 3.6.1 | A catalogue: dozens of algorithms, each a few lines to wrap. The biggest win is a public bridge that opens all of it from the console. | Loaded at startup (pure Python, without its matplotlib dependency). Already used for Louvain, modularity, Girvan–Newman, components, betweenness, clustering, triangles, coreness, shortest path and random generators (`py/guess/algorithms.py`, `analysis.py`). |
| **igraph** 1.0.0 | The speed engine. Its C core lifts the ~10k–100k node ceiling on betweenness, closeness, paths and communities, and adds Leiden, Infomap, large-graph layouts and pattern search. | Ships with Pyodide (with scipy); not used yet. |
| **Graphviz** | The layout gap: true layered layout with clusters, stress layout, overlap removal and edge routing. | Not in Pyodide. It would run as WebAssembly in the page (`@hpcc-js/wasm-graphviz` or `@viz-js/viz`, roughly 1 MB gzipped, loaded on first use), with positions sent back to Python. Graphviz is EPL-2.0: shipping the unmodified WebAssembly build is fine without relicensing GUESS. |

GUESS's own numpy code already computes PageRank, HITS, eigenvector,
closeness, harmonic, eccentricity and distance statistics.

## Tier 1: cheap, high value (hours each)

| # | Feature | From | What you get |
|---|---|---|---|
| 1 | `toNetworkX()`, `fromNetworkX(G)`, `setField(dict, name)` | networkx | Every networkx algorithm is one console line away, e.g. `setField(nx.katz_centrality(toNetworkX()), 'katz')`. Fields, positions, direction and multi-edges carry across. |
| 2 | `exportDOT()` + DOT reader fixes | Graphviz | Round trip with Graphviz. The reader fixes cover `fontcolor` (currently read and dropped), `style=invis`/dashed, `dir`, `tooltip`/`URL`, `xlabel`, pinned `pos!` and cluster labels. The writer is also the input for every Graphviz layout. |
| 3 | `makeSample('karate'\|'lesmis'\|'florentine'\|'davis'\|'petersen'…)` | networkx, igraph | Classic datasets with attributes, offline, for tutorials and the manual. |
| 4 | `assortativity(field)`, `mixingMatrix(field)`; `reciprocity`, `transitivity` and a triad census in `graphStats` | both | Homophily and directed-network profiles in one call. |
| 5 | `bridges()`, `cutNodes()`, `spanningTree()`, `constraint` field (structural holes) | networkx | Visual results: colour the weak points, the backbone, the brokers. |
| 6 | `ancestors(n)`, `descendants(n)`, `transitiveReduction()`, `feedbackEdges()`, `generation` field | networkx, Graphviz tools | Operations for citation and dependency graphs that GUESS lacks. |
| 7 | `compareClusters(f1, f2, method='nmi')` | igraph | "How well do the communities match `dept`?" as one number. |

## Tier 2: igraph as the engine (about 2–3 days)

**Bridge.** A cached `toIgraph(visibleOnly=True, weights='weight')` builds
`igraph.Graph(n, edges, directed)` from GUESS node indices. It costs O(n+m),
is cached per graph and cleared on change, like `recompute`.

**Switch these commands to igraph and keep their names:**
- betweenness for nodes and edges (add `cutoff` for approximate values);
- closeness, harmonic, eccentricity, `diameter`/`radius`/`averagePathLength` (removes the O(n²) memory limit);
- clustering, triangles and `averageClustering`; coreness and `kCore`; components and biconnected components;
- `shortestPath`, `edgeBetweennessClusters`;
- `louvainClusters` via `community_multilevel`, adding `levels=True` for the hierarchy.

**Keep as they are:** GUESS's PageRank, HITS and eigenvector code (already
fast; switching risks small numeric changes in saved sessions), and ForceAtlas2
(interactive). Switch `kkLayout`/`weightedKKLayout` and `frLayout` to igraph's
C versions only above ~1k nodes.

**New community commands**
- `leidenClusters(resolution=1, objective='modularity'|'CPM')`: always internally connected; the fastest option.
- `infomapClusters(trials=10)`: flow-based, best for directed graphs.
- `walktrapClusters(count)`, `fastGreedyClusters(count)` and `cutDendrogram(n)`, which could drive a Slider.
- `labelPropagation(seedField=None)`: linear time; can spread seed labels from a field.
- `eigenvectorClusters(count)`, `fluidClusters(k)`, `voronoiClusters()`.
- For small graphs only: `spinglassClusters()` (signed networks), `optimalClusters()` (exact, about 100 nodes or fewer).
- `cohesiveBlocks()`: nested k-connected blocks, writing a `cohesion` field (under ~5k nodes).

**New layouts:** `drlLayout()` (the first credible 100k-node layout),
`umapLayout()`, `lglLayout(root)`, `mdsLayout(distances='paths')`, `dhLayout()`
(small graphs, few crossings), `bipartiteLayout(typeField)`,
`sugiyamaLayout(layers=field)`, `treeLayout(circular=True)`.

**New analysis**
- `similarTo(node, method='jaccard')` and `predictLinks(top=50)`, scoring only 2-hop candidate pairs.
- `findPattern(pattern)`: subgraph search with the LAD algorithm, igraph's standout feature.
- `minCut(a, b)`, `maxFlow(a, b, capacity='weight')`, `separators()`.
- `personalizedPagerank(seq)`, `dominatorTree(root)`.
- `triadCensus()`, `motifs(size=3)`, and a `knn` field (average neighbour degree).
- `largestCliques()`, `cliques(min=3)`, `maxMatching()`, `simplify(combine='sum')`.
- `rewire()` for degree-preserving null models.

**Caveats**
- igraph uses integer vertex ids, so the bridge needs a name mapping.
- Edge weights mean similarity in community detection but length in paths and betweenness; each command must document which.
- Some methods are undirected-only or reject multigraphs, so simplify the copy first.
- A long C call cannot be stopped with Stop. Warn before spinglass, optimal modularity or cohesive blocks on large graphs.
- Seed igraph's random generator from `seed=`.
- Compare outputs against today's networkx results on small graphs before switching.

## Tier 3: Graphviz layouts (1–2 days for the pipeline, then small per engine)

**Pipeline**
1. Python writes DOT (the `exportDOT` code).
2. The worker passes it to the page, which runs the WebAssembly build with `json0` output.
3. Node positions come back, along with edge spline points and label positions.
4. Python sets `x, y = pos.x, -pos.y`.

The layout runs in the page, not in Python; load it lazily so startup cost is unchanged.

**Commands**
- `dotLayout(rankdir='TB', nodesep, ranksep, clusters='cluster', sameRank=None, splines='spline', unflatten=None)`: layered layout that keeps clusters together. This is the biggest layout gap; today's `sugiyamaLayout`/`dagLayout` don't handle clusters or rank constraints.
- `neatoLayout(mode='major'|'sgd'|'KK', model='shortpath'|'circuit', lenField=None)`: stress layout, the best quality up to a few thousand nodes.
- `sfdpLayout()`: multilevel force layout for 10k–100k nodes.
- `fdpLayout(clusters=…)`, `osageLayout(field)`: cluster-aware layouts.
- `circoLayout()`, `treemapLayout(field)` (patchwork).
- `removeOverlap(method='prism', sep=4)`: removes overlaps after any layout while keeping its shape better than `noverlapLayout`.
- Later: `routeEdges(splines='ortho'|'spline'|'polyline')`. It needs the renderer to draw per-edge curves stored in a hidden `_spline` field, which also makes imported Graphviz drawings render exactly.

## Tier 4: worthwhile but niche

- **Two-mode and cross-tab:** `projectBipartite(sideField, value)`, `quotientGraph(field)`, `lineGraph()`, `complementGraph()`, `composeGraphs`/`diffGraphs` between tabs, `condenseSCC()` (a documented recipe over `collapseBy(strongcomponent)`).
- **Generators:** `makeSBM`, `makeLFR`, `makeWattsStrogatz`, `makePowerLaw`, `makeForestFire`, `makeGeometric`, `makeFamous(name)`.
- **Formats:**
  - node-link and Cytoscape JSON (`makeFromJSON`/`exportJSON`);
  - plain edge lists and NCOL (`makeFromEdgeList`, `makeFromNCOL`);
  - LGL, DIMACS, Matrix Market;
  - `exportPajek`.
- **Layouts:** `spectralLayout()`, `shellLayout(field)`, `multipartiteLayout(field)`.
- **Analysis:**
  - `kTruss(k)`, `colorGraph()`, `voteRank(k)`, `katz` and `trophic` fields;
  - `inferLabels(field)`, `localCommunity(node)`, `partitionQuality(field)`;
  - `kShortestPaths(a, b, k)`, `voronoi(seeds)`, `conductance(seq)`, `richClub()`, `smallWorld()` (expensive).
- **Visual tools:**
  - `clusterMap(field)`: communities drawn as country regions, as Graphviz's gvmap does;
  - `edgepaint()`: distinct colours for edges that cross at small angles.

  Both would be reimplemented in Python or JS; the WebAssembly builds don't include them.

## Recommended order

1. **Bridges and Tier 1.** The cheapest gains. `exportDOT` and the networkx bridge are also foundations for later tiers.
2. **The igraph engine swap.** The biggest gain at real-world sizes. It changes existing commands, so it needs side-by-side checks.
3. **The Graphviz pipeline**, starting with `dotLayout`, `neatoLayout` and `removeOverlap`.

**Verify before building**
- networkx 3.6 `leiden_communities` may need an extra backend. This is not confirmed; igraph's Leiden avoids the question.
- Newer igraph methods (`community_voronoi`, `layout_umap`) must be checked against Pyodide's igraph 1.0.0.
- The WebAssembly package sizes are estimates; measure them before deciding.

---

## Survey details: networkx

Scaling assumes 1k–50k nodes in single-threaded Pyodide, roughly 3–10× slower
than CPython. O(N·M) algorithms get painful above about 10k nodes.

**Centrality.** Commands below write node fields.
- `katz_centrality_numpy`: `katz` field; a cheap sparse solve.
- `current_flow_closeness`: `information` field; O(N³), up to ~3k nodes.
- `laplacian_centrality`, `subgraph_centrality`: small graphs only.
- `voterank(G, k)`: `voteRank(k)`, k spreaders that don't overlap.
- `trophic_levels`: `trophic` field for directed graphs.
- `dispersion(u)`: expensive.
- `prominent_group`: exponential; small graphs only.
- `local/global_reaching_centrality`: O(N·M).
- Not worth adding: load and percolation centrality (close to betweenness), second-order centrality.

**Communities**
- `leiden_communities`, `asyn_lpa`/`fast_label_propagation` (O(M)).
- `greedy_modularity_communities`, with `best_n` to ask for exactly k groups.
- `asyn_fluidc(G, k)`: needs a connected graph; use `giantComponent()`.
- `k_clique_communities`: overlapping groups, which could be drawn as hulls.
- `infomap` (pure Python, new in 3.6).
- `kernighan_lin_bisection`: `bisect()`.
- `partition_quality`, coverage, performance: `partitionQuality(field)`.
- `greedy_source_expansion`: `localCommunity(node)`.

**Structure and cohesion**
- `k_truss`, `k_shell`, `k_crust`, `k_corona`, `onion_layers`.
- `bridges`, and `local_bridges(with_span=True)` for a `span` edge field.
- `articulation_points`: `cutNodes()`.
- `minimum_edge_cut`/`node_cut`, `stoer_wagner`, `edge_disjoint_paths`: `disjointPaths(a, b)`.
- `maximum_flow`: `maxFlow`.
- `constraint`, `effective_size`: Burt's structural holes, O(N·d²).
- `rich_club_coefficient`.
- `find_cliques`, `node_clique_number`: `maxClique()` and a `cliquenumber` field.
- `densest_subgraph`, `dominating_set`, `maximal_independent_set`, `max_weight_matching` (O(N³)).
- `greedy_color`: `colorGraph()` writes `colorclass`.
- `transitivity`, `square_clustering`, `global_efficiency` (O(N·M)).
- `sigma`/`omega` small-world coefficients: very expensive, about 1k nodes or fewer.

**Assortativity and mixing**
- `degree_assortativity_coefficient`, `attribute_assortativity_coefficient`, `numeric_assortativity_coefficient`.
- `attribute_mixing_matrix`.
- `average_neighbor_degree`.

All are O(M).

**Link prediction and similarity**
- `jaccard_coefficient`, `adamic_adar_index`, `resource_allocation_index`, `preferential_attachment`, `common_neighbor_centrality`.
- Restrict candidates to one node or to 2-hop pairs.
- SimRank works only on small graphs; Panther is approximate and scales better; graph edit distance is exponential, so skip it.

**Paths, DAGs, trees, cycles**
- `minimum_spanning_tree` / `maximum_spanning_tree`.
- `shortest_simple_paths`: `kShortestPaths`.
- `steiner_tree`: `connectNodes(seq)`.
- `ancestors`, `descendants`, `topological_generations`, `dag_longest_path`, `transitive_reduction`.
- `find_cycle`, `simple_cycles` (length-bounded), `girth`.
- `periphery`, `center`, `barycenter`, `resistance_distance`.
- `voronoi_cells`: a `cell` field.
- `conductance`, `node_boundary`.
- Niche: dominance, Euler, TSP.

**Directed and social**
- `triadic_census`, `reciprocity`, `flow_hierarchy`.
- `attracting_components`: an `attracting` field.

**Bipartite**
- `weighted_projected_graph`, `overlap_weighted_projected_graph`: `projectBipartite` into a new tab. Cost is O(Σ deg²) of the other side.
- `is_bipartite`, bipartite sets, bipartite clustering, BiRank.

**Classification and summarisation**
- `harmonic_function`, `local_and_global_consistency`: `inferLabels(field)`; dense, up to ~5k nodes.
- `snap_aggregation`.
- `weisfeiler_lehman_subgraph_hashes`: a `role` field for structurally equivalent nodes.

**Isomorphism.** `vf2pp` / `GraphMatcher.subgraph_isomorphisms_iter`
(exponential; needs a cap).

**Generators**
- Social datasets: karate club, Les Misérables, Florentine families, Davis Southern Women.
- Named small graphs: Petersen, Krackhardt kite, Tutte, Heawood…
- Community benchmarks: `stochastic_block_model`, `planted_partition_graph`, `LFR_benchmark_graph` (slow, can fail to converge), `relaxed_caveman`, `ring_of_cliques`.
- Random models: Watts–Strogatz, Holme–Kim powerlaw-cluster, random geometric (sets positions), configuration model, scale-free directed, random trees.
- `double_edge_swap`: rewiring.

**Layouts missing from GUESS**
- `spectral_layout`, `shell_layout`, `bipartite_layout`/`multipartite_layout`.
- `planar_layout`: O(N), but raises on non-planar graphs.
- Low value: `spiral_layout`, `arf_layout`. `bfs_layout` is close to `radialLayout`.

**Formats missing from GUESS:** node-link JSON, Cytoscape JSON, edge list,
adjacency list, graph6/sparse6.

**Operators**
- `quotient_graph`, `line_graph`, `complement` (the graph complement; GUESS's `complement(seq)` is a set complement).
- `compose`, `union`, `difference`.
- `contracted_nodes`: a permanent `merge(seq)`, unlike `collapse`.

**Bridge design (`toNetworkX` / `fromNetworkX`)**
- Today's private `to_networkx` turns a mixed graph into a DiGraph by duplicating undirected edges. Keep that, add `directed=None|True|False`, and record `G.graph['mixed']`.
- Use MultiGraph/MultiDiGraph, keyed by GUESS edge id, when parallel edges exist.
- **Fields:** copy every user field, and computed fields only if already evaluated (never trigger computation).
- **Positions:** write `pos` as an (x, y) tuple and also `x`/`y`.
- **Node keys:** the GUESS name is the node key; drop the internal `edge=` back-reference.
- **Import types:** infer field types from values.
- **Import names:** stringify non-string node keys and keep the original in a field.
- **Import positions:** read `pos` or `x`/`y`, or run a layout.
- **Import weights and metadata:** map `weight`, keep `G.graph`.
- **Import target:** `name=` loads into a new tab; the import is one undo step.
- `setField(dict_or_sets, name)` turns any networkx result into a field in one line.

## Survey details: igraph

Checked against `src/_igraph/graphobject.c` (every C method named here is
exposed) and the Python wrappers in `community.py`, `clustering.py`,
`layout.py` and `io/files.py`.

**Communities.** The table gives scale notes and the suggested GUESS command.

| igraph | Notes | Command |
|---|---|---|
| `community_leiden(objective_function, resolution, beta, n_iterations, initial_membership)` | Near-linear; seconds at 100k | `leidenClusters` |
| `community_infomap(edge_weights, vertex_weights, trials)` | Seconds to tens of seconds at 100k | `infomapClusters` |
| `community_walktrap(steps=4)` → dendrogram | To ~50k | `walktrapClusters` |
| `community_fastgreedy()` → dendrogram | Undirected, simple graphs only | `fastGreedyClusters` |
| `community_label_propagation(initial, fixed)` | Linear | `labelPropagation` |
| `community_leading_eigenvector(clusters)` | To ~20k | `eigenvectorClusters` |
| `community_spinglass(spins, gamma, implementation="neg")` | Under ~2k nodes; handles negative weights | `spinglassClusters` |
| `community_optimal_modularity()` | GLPK, under ~100 nodes | `optimalClusters` |
| `community_voronoi(lengths, weights, radius)` | Moderate | `voronoiClusters` |
| `community_fluid_communities(k)` | Fast | `fluidClusters` |
| `community_edge_betweenness` | 50–100× faster than networkx | engine for `edgeBetweennessClusters` |
| `community_multilevel(return_levels=True)` | 10–50× faster | engine for `louvainClusters` |

**Working with results**
- `compare_communities(method="vi"|"nmi"|"rand"|"adjusted_rand"|"split-join")`.
- `VertexDendrogram.as_clustering(n)` / `.optimal_count`: `cutDendrogram(n)`.
- `cohesive_blocks()`: `cohesiveBlocks()`.
- `cluster_graph()` and `crossing()` are already covered by GUESS's `collapseBy` and `interEdges`.

**Layouts**
- `layout_drl` (presets default/coarsen/refine), `layout_lgl`, `layout_umap`.
- `layout_mds(dist=…)`.
- `layout_kamada_kawai`, `layout_fruchterman_reingold(grid="auto")`.
- `layout_davidson_harel`.
- `layout_reingold_tilford(_circular)`, `layout_sugiyama(layers=…)`, `layout_bipartite`.
- `layout_grid`, `layout_star`.
- 3D layouts are skipped; GUESS has no 3D view.

**Speed.** Expected gains of the C core over networkx or numpy:
- **Betweenness:** 20–50× faster than networkx. At 50k nodes it takes minutes instead of hours. `cutoff` gives approximate values.
- **Closeness, harmonic, eccentricity, distances, radius, diameter, average path length:** per-source BFS in C with O(n) memory, instead of all-pairs O(n²) memory.
- **`transitivity_local_undirected`, `list_triangles`, `coreness`, components, biconnected components, `bridges`, `articulation_points`:** 10–30× faster than networkx.
- **PageRank (PRPACK), hub/authority, eigenvector:** competitive with GUESS's numpy code.
- **New path queries:** `personalized_pagerank(reset_vertices=…)`, `get_all_shortest_paths`, `get_k_shortest_paths`.

**Analysis**
- `constraint`, `assortativity_degree` / `assortativity` / `assortativity_nominal`, `knn`.
- `similarity_jaccard` / `_dice` / `_inverse_log_weighted`, `cocitation`, `bibcoupling`.
- `triad_census`, `dyad_census`, `motifs_randesu(size=3|4)`, `reciprocity`.
- `largest_cliques`, `maximal_cliques(min,max)`, `clique_number`, `largest_independent_vertex_sets`.
- `vertex_connectivity` / `edge_connectivity`, `minimum_size_separators`, `mincut`, `st_mincut`, `maxflow`, `all_st_mincuts`, `gomory_hu_tree`.
- `dominator`.
- `rewire`, `Degree_Sequence(method="vl")`.
- `subisomorphic_lad` / `get_subisomorphisms_lad`, `count_isomorphisms_vf2`, `automorphism_group`.
- `maximum_matching`, `maximum_bipartite_matching`, `spanning_tree`.
- `unfold_tree`, `contract_vertices`, `simplify(combine_edges=…)`.
- `feedback_arc_set`, `topological_sorting`, `girth`, `minimum_cycle_basis`, `vertex_coloring_greedy`.

**Generators**
- Random models: `Static_Power_Law`, `Degree_Sequence`, `SBM`, `Forest_Fire`, `Watts_Strogatz`, `Barabasi`, `Erdos_Renyi`, `Chung_Lu`, `K_Regular`, `Nearest_Neighbor_Graph`.
- Named and catalogue graphs: `Famous` (Zachary, Petersen, Coxeter… about 30), `Atlas`, `LCF`.
- Regular structures: `Kautz`, `De_Bruijn`, `Hypercube`, `Tree`, triangular and hexagonal lattices.

**Formats**
- Read: NCOL, LGL, DIMACS, GraphDB, plain edge list, gzipped GraphML.
- Write: NCOL, LGL, LEDA, DIMACS, Pajek.

## Survey details: Graphviz

Sources: `graphviz/LICENSE` (EPL-2.0), `lib/{dotgen, neatogen, fdpgen,
sfdpgen, circogen, twopigen, osage, patchwork, ortho, vpsc, edgepaint,
mingle}`, `cmd/tools/*.1`, `cmd/gvmap`, `cmd/edgepaint`, `cmd/mingle`, and
`plugin/core/gvrender_core_json.c`, which provides the `json`, `json0`,
`dot_json` and `xdot_json` outputs.

**Engines**

| Engine | Strengths | GUESS today |
|---|---|---|
| **dot** | Network-simplex ranking, crossing minimisation, `rankdir`, `rank=same/min/max/source/sink`, clusters as boxes, `ordering=out`, `nodesep`/`ranksep`, `newrank`, `group`, ports | `sugiyamaLayout`, `sugiyamaLayout2`, `dagLayout`, `treeLayout`: no clusters, rank constraints or spline routing |
| **neato** | Stress majorization (default), KK, SGD, hier, ipsep; models shortpath, circuit, subset, mds; edge `len` | `kkLayout`, `jkkLayout1`/`2`, `weightedKKLayout`, `mdsLayout`; no stress majorization or SGD. A numpy SGD stress layout would be about 150 lines. |
| **sfdp** | Multilevel spring-electrical with a quadtree (`K`, `repulsiveforce`, `smoothing`, `beautify`) | Nothing multilevel; ForceAtlas2 is the closest |
| **fdp** | Force-directed, with clusters as nested boxes | Not covered |
| **circo** | Biconnected components on chained circles | `circleLayout` uses one ring only |
| **twopi** | Radial layout by BFS level | `radialLayout(center)` |
| **osage** | Clusters packed as rectangles | `binPackLayout` packs components, not clusters |
| **patchwork** | Squarified treemap | Not covered |
| **overlap removal** | prism, voronoi, vpsc, ipsep, scalexy, compress, ortho; `sep` | `noverlapLayout`, `labelAdjustLayout` |
| **pack / gvpack** | Component packing | `binPackLayout` |

**Edge routing**
- `splines=spline|polyline|ortho|curved|line`, routing around obstacles. Running `neato -n2` with fixed positions works after any GUESS layout.
- Label placement via `lp`/`xlp`, `headlabel`/`taillabel`.
- **Already covered:** mingle bundling (GUESS has `bundleEdges`).
- **Not covered:** edgepaint, which colours crossing edges apart.

**Tools**
- **tred** → `transitiveReduction()` (~40 lines).
- **acyclic** → `feedbackEdges()`.
- **sccmap** → `condenseSCC()`.
- **ccomps / bcomps**: covered.
- **unflatten** → a `dotLayout(unflatten=…)` option.
- **dijkstra**: covered by `heatMap`.
- **gvgen** → `makeGenerated(kind, n)`.
- **gc** (counts) and **gvpr** (graph scripting): covered by `graphStats`, Gython and `sql`.
- **cluster / gvmap** → `clusterMap(field)`.
- **mm2gv** → `makeFromMTX`.

**DOT reader: attributes to map**
- **Fixes**
  - Apply `fontcolor` as the label colour, on nodes and edges.
  - Node `color` becomes the outline (`strokecolor`) when `fillcolor` or `style=filled` is present.
- **New mappings**
  - Node `penwidth` → a `strokewidth` field; `peripheries` → a field.
  - `xlabel` → label when there's no `label`; `tooltip` and `URL`/`href` → fields.
  - `style=invis` → hidden; edge dashed/dotted/bold → a field.
  - `dir=back|both|none`, `arrowhead`/`arrowtail` → fields. `dir=back` swaps the endpoints; `dir=none` gives an undirected edge.
  - `len` → an edge field; `fixedsize`, `fontsize` → fields.
  - `pos` ending in `!` → `fixed`.
  - Edge `pos` splines → a hidden `_spline` field.
  - Graph `bb` → normalise coordinates; remember `rankdir` and `layout`.
- **Clusters and labels**
  - `rank=same` → a group field.
  - Cluster labels → kept; nested clusters → the innermost, plus a `clusterpath` field.
  - Record and HTML labels → stripped to plain text.

**exportDOT writer (`exportDOT(filename, layout=True, fields=True)`)**
- **Header:** `digraph` if any edge is directed, with undirected edges written as `dir=none`. Never `strict`. Keep the stored `rankdir`.
- **Nodes**
  - Quoted name and `label`.
  - Position `pos="x,-y!"`, with `!` when the node is fixed.
  - Size: `width`/`height` = GUESS size × 3/72 inches.
  - Shape from `style`: 1→box, 2→ellipse, 3→Mrecord, 5→triangle, 9→diamond.
  - Colours: `style=filled` with `fillcolor` `#rrggbb[aa]`; `color` = `strokecolor`; `fontcolor` = `labelcolor`.
  - `style=invis` when hidden; `image`.
  - User fields as attributes, prefixed `guess_` only when their names clash with Graphviz attributes.
- **Clusters:** `subgraph cluster_<v> { label="<v>"; … }` from the `cluster` field, or another field via `clusters=`.
- **Edges**
  - `color`, `penwidth` = width.
  - `weight`: integer for dot, or `len` for neato.
  - `label`, `fontcolor`, `dir=none`, user fields.
- **Collapsed groups:** export the meta-nodes, or expand them first.
- **Test:** `makeFromDOT(exportDOT(...))` should reproduce the mapped fields.

**WebAssembly**
- **@hpcc-js/wasm-graphviz** (Apache-2.0 wrapper, WebAssembly inlined in one ES module):
  - about 1.5–2 MB minified, 0.6–0.9 MB gzipped (estimate);
  - includes every engine (dot, neato, fdp, sfdp, circo, twopi, osage, patchwork, nop);
  - outputs `dot`, `json`/`json0` and `svg`;
  - call `graphviz.layout(dot, "json", "neato")`.
- **@viz-js/viz** (MIT wrapper): similar size and API.
- Neither includes gvmap, edgepaint or mingle.
- **Loading:** lazily, in the main thread or a second worker.
- **Licence:** EPL-2.0 is weak, file-level copyleft. Keep the notice and say where the source is available. Modified Graphviz files would have to stay EPL. Loading the unmodified package from npm keeps compliance trivial.
