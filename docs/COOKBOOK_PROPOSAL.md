# Proposal: the "GUESS for X" cookbooks (2026-11-10)

**Status (2026-11-10):** the series is set up in `cookbooks/` (build,
recipe checker, screenshot script, datasets). Written: the Kitchen (core),
*Social Network Analysis*, *Biology*, and *Text, Knowledge and Citation
Networks*. Features added for them: `project`, `blockmodel`, a `degree`
field, `makeFromSTRING`, `readSets` and `enrichment`, `colorBy(center=)`
(with legends that show the real gradient), `makeFromText`,
`makeFromTwoMode`, `makeFromSimilarity`, `mainPath`, and for
*Infrastructure and Transportation* (also written) `geoLayout` with a
vector map layer, `geoDistance` and `robustness`. `subgraph` and
`showOnly` now keep exactly the edges selected. *Software and
Systems*, *Investigations*, *Ecology* and *Epidemiology* are written too,
and every book ends with a capstone app. Decided 2026-11-10: no Social Media book; the
Digital Humanities material (history and geography of a field) is folded
into the Text book. See `cookbooks/README.md`.

A series of domain cookbooks, each a set of short, runnable recipes for one
field (social network analysis, biology, …), built from a shared core. This
proposal comes from reading the structure of seven books about other network
tools (listed at the end) and checking which of their analyses GUESS can do
today. Features GUESS lacks, and that the cookbooks would need, are in
[Feature gaps](#feature-gaps).

## 1. What the reference books do

| book | tool | organisation | domains in its examples |
|---|---|---|---|
| Gephi Cookbook (Khokhar, 2015) | Gephi | ~90 recipes in 10 chapters, ordered by tool feature (basics, layouts, partition/ranking, metrics and filters, data lab, preview, dynamic graphs, datasets, plugins) | web/internet, social (karate, Twitter), biology (C. elegans, yeast), airlines |
| Network Graph Analysis and Visualization with Gephi (Cherven, 2013) | Gephi | a linear tutorial: install, first graph, layouts, building a dataset, plugins, filters and statistics, publishing | general / school data |
| Instant Cytoscape How-to (Su, 2013) | Cytoscape | about 10 recipes tagged Easy/Intermediate/Advanced: load, style, views, search, apps, clusters, remote data, export | molecular biology |
| Analyzing Social Media Networks with NodeXL (Hansen, Shneiderman, Smith, 2011) | NodeXL | three parts: concepts, a tool tutorial (layout and labels, metrics, filtering, clustering), then one chapter per data source (email, threads, Twitter, Facebook, web, Flickr, YouTube, wikis) | social media |
| Connect to Networks with NodeXL (2023) | NodeXL Pro | a reference manual: import, data preparation, groups (by attribute, component, cluster, motif), metrics, appearance, then one end-to-end tutorial | social media, text |
| Complex Network Analysis in Python (Zinoviev, 2017) | NetworkX, Gephi | five parts by *kind of network* (explicit relations, co-occurrence, similarity/bipartite, directed), each ending in a case study | Wikipedia, Panama Papers, semantic/product networks, cultural domain analysis, psychological trauma |
| Network Science: Analysis and Optimization Algorithms (Pinheiro, 2023) | SAS | algorithm chapters (subgraphs, centrality, optimisation), then business case studies | logistics/routing, COVID-19, urban mobility, insurance and telecom fraud, churn |

Patterns worth borrowing:

- **A fixed recipe template**, as in the Packt books (*Getting ready → How to
  do it → How it works → There's more → See also*). It is what makes them
  skimmable.
- **Difficulty tags** (Cytoscape: Easy/Intermediate/Advanced).
- **A tool part, then a domain part**, as in the NodeXL book. The tool part
  is shared, and the domain chapters are where readers find themselves.
- **Organise by the shape of the data, not the tool's menus** (Zinoviev:
  explicit, co-occurrence, similarity, directed). Readers know what their data
  looks like before they know what algorithm they want.
- **End-to-end case studies** that end with an interpretation, not just a
  picture (NodeXL, Zinoviev and Pinheiro all do this).
- **Practitioner's summary / researcher's agenda** boxes (NodeXL): one says
  what to do on Monday, the other what's still open.

What the books do badly, and GUESS can do better: their steps are
click-paths and screenshots that go stale. GUESS recipes are text, so every
step can be **run and checked by the build**, as the manual already is with
`check_examples.py`, and the pictures can be **regenerated** from the recipe.

## 2. Series structure

```
cookbooks/
  core/            "GUESS Kitchen": the shared recipes every volume links to
  sna/             GUESS for Social Network Analysis
  social-media/    GUESS for Social Media and Online Communities
  biology/         GUESS for Biology
  text/            GUESS for Text, Knowledge and Citation Networks
  infrastructure/  GUESS for Infrastructure and Transportation
  investigations/  GUESS for Fraud, Finance and Investigations
  software/        GUESS for Software and Systems
  humanities/      GUESS for Digital Humanities
  data/            the datasets, each with a licence/source note
  tools/           build, example checker, screenshot generator
```

Each volume is short (about 25–40 recipes) and assumes the core, linking to
it rather than repeating it. A volume has:

1. **Why networks here**: two pages on what nodes and edges mean in this
   field, and the standard questions.
2. **Getting the data in**: the field's file formats and sources.
3. **Recipes**, grouped by question (see each volume below).
4. **Two or three case studies**, each worked end to end, ending in an
   interpretation.
5. **Pitfalls**: the field's classic mistakes (for example a hairball
   from a PPI dump, or treating retweets as friendship).

### Recipe template

```markdown
### 3.4 Find the brokers between departments  ·  Intermediate

**You have** an organisational network with a department field.
**You want** the people who connect departments that otherwise don't talk.

**Ingredients:** `sample.gdf` · `betweenness` · `interEdges` · `cutNodes`

**Steps**
​```python
makeFromGDF("sample.gdf")
brokers = sortBy(betweenness)[-10:]
brokers.color = red
(interEdges(dept)).color = orange
​```
<!-- screenshot: generated from the steps -->

**How it works:** two or three paragraphs: what the measure means here.
**Variations:** weighted, directed, ego-only, over time (`ss` / `morph`).
**Pitfalls:** where this misleads you.
**See also:** core 2.3 (centrality), SNA 5.1 (structural holes).
```

Every code block runs in the build. A recipe that breaks fails the build.
Screenshots come from the same code via a headless GUESS. The format is
the manual's Markdown, so the existing pandoc pipeline produces HTML, PDF and
EPUB for each volume with no new tooling. "Open in GUESS" links can load a
recipe's steps straight into the console.

### Core volume: "GUESS Kitchen"

Shared by every domain volume, organised by task:

1. **Getting data in**: GDF/GraphML/GEXF/GML/DOT/Pajek/CSV (edge table,
   adjacency matrix, node table merged onto a graph); URL, SPARQL, Cypher,
   NDEx; from networkx/igraph.
2. **Cleaning**: duplicates to weights (`simplify`), self-loops, isolates,
   giant component, renaming fields, sampling big graphs.
3. **Asking questions**: field queries, `find`, `like`, set algebra, edge
   operators, `groupBy`, the data table.
4. **Measuring**: degree and strength, centralities, clustering,
   paths and diameter, assortativity, reciprocity, `graphStats`.
5. **Finding structure**: components, cores, cliques, communities (Louvain,
   Leiden, Infomap, …), comparing partitions, groups and collapsing.
6. **Laying out**: choosing a layout (force, hierarchical, radial, Graphviz),
   overlap removal, fixing nodes, comparing layouts.
7. **Encoding**: colour, size and shape by field; legends; heat maps;
   pie glyphs; hulls; edge bundling; labels and label placement; the lens.
8. **Change over time**: states and morphing, ranges, `showTime`, movies.
9. **Sharing**: images (SVG/PDF/PNG), slides, `exportApp`, sessions,
   scripts and history.

### Domain volumes

Each heading lists the recipe groups. Recipes marked ⚠ need a feature in
[Feature gaps](#feature-gaps).

**GUESS for Social Network Analysis** (first: the shortest path from what
GUESS already does well)
- Ego networks: ego and alters, density, brokerage, ego-network comparison
- Centrality and power: who is central under which definition, and why they
  disagree
- Structural holes and brokerage: betweenness, cut nodes, bridges, inter-group
  edges, constraint ⚠
- Cohesion: cliques, k-cores, communities, cohesive blocks
- Roles and positions: structural equivalence, blockmodels ⚠
- Homophily and mixing: assortativity, mixing matrices, `interEdges`/`intraEdges`
- Directed ties: reciprocity, triad census, hierarchy
- Two-mode data: people × events, projection ⚠
- Case studies: Zachary's karate club (the split), Florentine families,
  an organisational chart vs. the informal network (`sample.gdf`)

**GUESS for Social Media and Online Communities**
- Data: hashtag/mention/reply networks from exports and APIs ⚠ (importers)
- Thread and reply structure; conversation trees
- Influencers vs. bridges; retweet cascades over time (states / `showTime`)
- Polarisation: two-community structure, cross-cutting edges
- Wikis and hyperlink networks; Reddit/Mastodon/Bluesky-style data ⚠
- Content and network together: word pairs per group ⚠ (text tools)
- Case studies: a polarised hashtag, a wiki's edit network, a mailing list

**GUESS for Biology**
- Data: PPI and gene networks from NDEx, SIF/GML/GraphML, expression tables
  merged onto nodes
- Hubs and essentiality; degree distributions (`plotDistrib`)
- Modules and complexes: clustering, cliques, cores
- Pathways and regulation: directed paths, `descendants`/`ancestors`,
  feedback loops (`feedbackEdges`), motifs (`findPattern`)
- Expression overlays: heat colours, pie glyphs per condition, comparing
  conditions with states and morphing
- Enrichment of a module ⚠
- Neural connectomes: C. elegans, directed and weighted
- Case studies: yeast PPI modules, a signalling pathway, C. elegans

**GUESS for Text, Knowledge and Citation Networks**
- Co-occurrence networks from text ⚠ (window/sentence builder)
- Semantic and term networks; slicing by weight
- Bipartite word–document networks and projections ⚠
- Similarity networks from feature tables (`similarTo`, thresholds) ⚠
  (similarity builder)
- Citation networks: DAGs, main paths, topological order ⚠
- Knowledge graphs: SPARQL import, typed edges, label placement
- Case studies: characters in a play, a citation field's history, cultural
  domain analysis

**GUESS for Infrastructure and Transportation**
- Airports and routes: geographic layout ⚠, edge bundling, hubs
- Robustness: removing hubs vs. random failure, cut nodes, bridges,
  `minCut`, `maxFlow`
- Shortest and alternative routes; spanning trees
- Optimisation: min-cost flow, assignment, travelling salesman ⚠
- Mobility flows: origin–destination matrices, flow maps ⚠ (geo)
- Case studies: the US airline network, a power grid, a city's bike trips

**GUESS for Fraud, Finance and Investigations**
- Entity resolution: merging duplicate nodes ⚠ (merge nodes)
- Bipartite person–company networks and projections ⚠
- Suspicious structures: rings (cycles), stars, dense cores, motifs
- Link prediction (`predictLinks`) and similarity
- Community-based anomaly scoring ⚠ (group metrics)
- Timelines of transactions (ranges, `showTime`)
- Case studies: an offshore-leaks-style network, an insurance-claims ring,
  a telecom call network

**GUESS for Software and Systems**
- Dependency graphs from DOT, package manifests; call graphs
- Cycles, layers and topological order (`dagLayout`, `feedbackEdges`,
  `transitiveReduction`) ⚠ (toposort)
- Dominators and critical modules (`dominatorTree`, cut nodes)
- Graphviz layouts and DOT round-trips
- Case studies: a Python package's imports, a microservice graph

**GUESS for Digital Humanities**
- Character networks from scripts and novels ⚠ (co-occurrence)
- Correspondence networks over time (states, `showTime`)
- Prosopography: people × institutions ⚠ (bipartite)
- Maps of letters and travel ⚠ (geo)
- Case studies: *Les Misérables*, a letters archive

Suggested order: **Core → SNA → Biology → Text → Infrastructure**, then the
rest. SNA needs almost nothing new. Biology and Text unlock the most
missing features (bipartite projection, co-occurrence, enrichment), and
those features also serve later volumes.

## 3. Datasets

Each volume needs small, openly licensed datasets in `cookbooks/data`, each
with a source and licence note. Candidates: Zachary karate club, Florentine
families, *Les Misérables* co-appearance, dolphins, C. elegans neural network,
yeast PPI (from NDEx or a public-domain release), US airports, a power grid,
the Enron email graph (subset), a citation network (e.g. from OpenAlex), a
Python package dependency graph (generated), `sample.gdf` and
`adamic-glance.gdf`. Check each licence before bundling. Where redistribution
isn't allowed, recipes load the data by URL.

## 4. Feature gaps

Things the books do that GUESS can't yet, ranked by how many volumes need them.

| priority | feature | needed by | notes |
|---|---|---|---|
| ✅ done | **Bipartite projection**: `project(kind, value, method)` with count, Jaccard and Newman weights; opens in a new graph | SNA, Text, Biology, Investigations, Humanities | added for the SNA book |
| ✅ done | **Geographic layout**: `geoLayout(lat, lon, projection=, map=)` (Mercator, Albers, equirectangular) with Natural Earth outlines drawn as a vector layer (exported in SVG/PDF); `geoDistance()` for great-circle edge lengths | Infrastructure, Humanities, epidemiology | added for the Infrastructure book |
| ✅ done | **Co-occurrence builder**: `makeFromText(file, terms, by=, window=)`, with alias lists | Text, Social media, Humanities | added for the Text book |
| ✅ done | **Similarity network builder**: `makeFromSimilarity(table, k= or threshold=, method=)`, wide or long tables | Text, Biology, Investigations | added for the Text book |
| ✅ done | **Group metrics table**: `groupStats(field)` | SNA, Investigations, Social media | added for the Investigations book |
| ✅ done | **Motif groups**: `findMotifs(kind)` and `collapseMotifs(kind)` (fan, connector, clique) | Social media, Biology | Kitchen recipe |
| ✅ done | **Blockmodeling / structural equivalence**: `blockmodel(k)` stores `position` and prints the image matrix | SNA | added for the SNA book |
| ✅ done | **Spreading simulations**: `spread(seeds, model)` (SI, SIR, cascade, threshold), with `infected_at` for replay | epidemiology, Social media, marketing | SNA "Diffusion" chapter |
| ✅ done | **Merge nodes**: `mergeNodes` and `findDuplicates` | Investigations, Text, all data cleaning | added for the Investigations book |
| ✅ done | **Web importers**: `makeFromWikipedia(title)` and `makeFromOpenAlex(search)` (Mastodon/Bluesky/Reddit not pursued) | Text | Text "Live sources" chapter |
| ✅ done | **Enrichment**: `readSets(table)` and `enrichment(nodes, sets)` (hypergeometric, BH q-values) | Biology, Text | added for the Biology book; also names citation fronts by keyword |
| — | ~~Topological sort~~ | Software, Text | already there: the `generation` node field |
| — | ~~Burt's constraint / effective size~~ | SNA | already there: the `constraint` and `effsize` node fields |
| ✅ done | **Rich-club coefficient**: `richClub()` (normalised against degree-preserving rewiring); k-shells are the existing `coreness` | SNA, Infrastructure | Infrastructure recipe |
| ✅ done | **Optimisation**: `minCostFlow(a, b, amount)` and `travelingSalesman(stops)` (VRP out of scope) | Infrastructure, logistics | Infrastructure recipes |
| ✅ done | **STRING connector**: `makeFromSTRING(genes, species, score, add)` | Biology | the API allows browser requests |
| ✅ done | **Two-mode tables**: `makeFromTwoMode(table, a, b)` | Text, SNA, Biology | paper–author, gene–term, person–event |
| ✅ done | **Main path analysis**: `mainPath()` with `spc` edge weights | Text (citations) | Hummon and Doreian, key-route variant |
| ✅ done | **Code graphs**: `makeFromImports(package)` (module imports, deferred imports flagged, `level=` for subpackages) and `makeFromCalls(module)` (approximate call graphs) | Software | added for the Software book; parses, never runs, the code |
| ✅ done | **Investigation tools**: `findDuplicates`, `mergeNodes` (entity resolution, undoable), `groupStats` (per-group profile), `findCycles` (bounded directed cycles) | Investigations, SNA | added for the Investigations book |
| ✅ done | **Ecology tools**: `makeNicheModel`, `trophicLevels`, `extinctions` (cascades, R50), `nestedness` (NODF), `makeFromGloBI`; `rewire(keep=field)` for constrained null models | Ecology | added for the Ecology book |
| ✅ done | **Epidemiology tools**: `outbreaks` (many simulated outbreaks: size distribution, per-node `risk`), `spread(immune=, weight=)`, `offspring` (R, dispersion k, superspreading in a transmission tree), `effectiveDistance` (Brockmann–Helbing) | Epidemiology | added for the Epidemiology book |
| ✅ done | **Robustness simulation**: `robustness(orders)` (random, degree, betweenness, adaptive, any field) with a line chart | Infrastructure | added for the Infrastructure book |
| ✅ done | **Automatic report**: `report()` / `report("file.html")` | all | Kitchen recipe |
| ✅ done | **Node embeddings**: `embed(dims)` (node2vec walks + PPMI factorisation, numpy only) | Investigations, ML | Kitchen recipe |

## TODO after the cookbooks

All done 2026-11-10 except where noted: computed fields refresh themselves; the cookbooks deploy with the manuals (Help → Cookbooks); help images re-rendered; the Stop test hardened; and every item in the gap table. GitHub Pages deployment: not pursued (2026-11-10).

- **Deploy the cookbooks with the manuals (asked 2026-11-10).** The deploy
  scripts (`web/scripts/copy-manuals.mjs`, used by `npm run bundle` and the
  Pages workflow) copy `docs/manual/build/` to `manuals/` on the site. They
  should also copy `cookbooks/build/` (each book's HTML, PDF and EPUB, plus
  its index page) to `manuals/cookbooks/`, and the manuals' `index.html`
  (written by `docs/manual/build.py`) should link to the cookbooks' index
  and list each book. Also consider a Help → Cookbooks menu item beside
  Help → Manual, and a README link.
- **Computed fields refresh themselves (agreed 2026-11-10).** Today
  `betweenness`, `component`, `pagerank` and the other computed fields are
  calculated on first use and kept, so after `remove()`/`addEdge()` they're
  stale until `recompute()`. The SNA book hit this (`recompute()` in the
  Medici case study). Plan: structural changes set a dirty bit on the graph
  (cheap, no recalculation). Reading a structure-dependent ("fragile")
  field checks the bit and recomputes that field once, then clears its
  flag. A run of edits costs nothing until a measure is read, and nobody
  has to call `recompute()` (it stays, as a way to force it). Keep
  user-set fields out of it, and record per-field which kind of change
  invalidates it (structure vs. weights). Then drop the `recompute()` notes
  from the recipes (SNA Medici, Infrastructure hub closure, Investigations).
  Also: a projection or subgraph copies computed fields from the source
  graph, where they may describe the old structure (seen in the
  Investigations book), so a copied computed field should start dirty.
- ~~**Decide: should `subgraph(edges)` keep only those edges?**~~ Done 2026-11-10: `subgraph` and `showOnly` keep exactly the selected edges (`induced=true` for the old behaviour).
- (was) **Decide: should `subgraph(edges)` keep only those edges?** Today,
  given edges, it keeps their endpoints and *every* edge among them (as
  documented), so `subgraph(freq > 100)` doesn't give the heavy-tie network.
  Two recipes in this series got this wrong at first. Both now use
  `subgraph(g.nodes, name)` then `remove(…)`. networkx distinguishes
  `subgraph` (node-induced) from `edge_subgraph`. GUESS could do the same
  with an `edgeSubgraph(edges)` command, or switch `subgraph` to
  edge-induced when given only edges (a behaviour change). Needs a
  decision.

## 5. Build plan

1. Set up `cookbooks/` with the recipe template, the core volume's outline,
   and the build: reuse `docs/manual/build.py` and `check_examples.py`, with
   one output folder per volume, an index page, and Help-menu links.
2. Add a headless screenshot step (Playwright + the app) that renders each
   recipe's final state.
3. Write the core volume and the SNA volume. They need no new features
   except bipartite projection (one recipe).
4. Build the high-priority gaps (projection, geo layout, co-occurrence,
   similarity builder), then write Biology and Text.
5. Then the rest, in the order above.

## Sources consulted

Read for structure and topics only (no text reused): the seven books listed
in §1. They are in the local `books/` folder, which isn't part of the
repository and shouldn't be committed.
