# Explainers for Newman, *Networks* (2nd ed.): plan

One small GUESS app per section, each one a `<id>/manifest.json` + `<id>/main.gy`
in this folder, opened as `index.html?app=explainers/networks/<id>/manifest.json`.
`index.html` here lists them all. Explainers explain in their own words and use
their own or bundled data; they don't reproduce the book's text or figures.

Page numbers are the book's (PDF page = book page + 13).

Status: **planned** → **built** → **checked**.

---

## Batch 1: book pages 1–50 (Chapters 1–3)

Chapter 4 begins on p. 47. Section 4.1 is planned with the rest of Chapter 4 in batch 2.

### Ch. 1 Introduction (pp. 1–12)

**`ch01-zoo`: What is a network?** · built
- *Idea:* nodes and edges, and the book's four kinds of network.
- *Reader:*
  - starts with an 8-node, 10-edge toy network and hovers to see "node" and "edge";
  - then uses a drop-down to switch between four real examples: technological (`us-airports.gdf`, map layout), information (`vis-papers.gdf` citations, with arrows), social (`makeSample('karate')`) and biological (a food web from `makeNicheModel`, with `trophicLevels()` as height);
  - each example has a two-line caption and its node/edge counts, and notes whether it is directed.
- *GUESS:* `Dropdown`, `makeSample`, `makeFromFile`, `geoLayout`, `makeNicheModel`, `trophicLevels`, `orderedLayout`.

**`ch01-properties`: Three things to measure** · built
- *Idea:* degree and hubs, the small-world effect, and communities, as a first look.
- *Reader:* works with the karate club in three tabs:
  - **Degree:** each node's number is its degree, and size follows degree. A directed toggle switches to a small web graph with separate in- and out-degree.
  - **Small world:** click two members to see the shortest path and its length; a counter shows the mean distance.
  - **Communities:** a button runs Louvain and colours the groups. A checkbox compares them with the real split (`club`).
- *GUESS:* `labelBy`, `sizeBy`, `shortestPath`, `averagePathLength`, `louvainClusters`, `compareClusters`, `Tabs`.

### Ch. 2 Technological networks (pp. 14–31)

**`ch02-internet-tiers`: The shape of the Internet (§2.1)** · built
- *As built:* also has the router / class C subnet / domain / AS drop-down (`collapseBy`).
- *Idea:* a backbone, regional and local ISPs, then end users. Most studies keep only the routers.
- *Data:* a generated four-tier network of about 300 nodes, with a `tier` field.
- *Reader:*
  - sees the tiers as rings (`concentricLayout(tier)`);
  - "Router level" hides the end users and shows how few nodes and edges are left;
  - clicking an end user shows its route to another user: up through the tiers and back down.
- *GUESS:* `concentricLayout`, `showOnly`, `shortestPath`, `flow` edge style for the route.

**`ch02-traceroute`: Mapping the Internet with traceroute and BGP (§§2.1.1–2.1.2)** · built
- *As built:* uses real data, 300 ASes snowball-sampled from Newman's 2006 AS-level snapshot (`internet-as-sample.gdf`). The coarse-graining drop-down moved to `ch02-internet-tiers`, since an AS-level map can't be coarse-grained further. Coverage is reported by link kind (hub–hub, hub–small, small–small).
- *Idea:*
  - Raising the TTL one step at a time reveals a route hop by hop.
  - The union of the routes from a few sources is the measured map, and it misses edges.
  - Coarse-graining by subnet, domain or AS.
- *Data:* a generated router network (preferential attachment, about 250 routers). Each router gets a made-up IP address, a domain and an AS.
- *Reader:*
  - **TTL step:** pick a source and a destination, then press "TTL + 1". The packet dies one hop further along each time and the router that "reports back" lights up.
  - **Map from sources:**
    - Click to add sources (1–10) and the edges each source discovers are drawn bold.
    - A status line shows the share of real edges found and of nodes found.
    - "Clustered sources" against "spread-out sources" shows the overlap bias.
  - **Coarse-grain:** a drop-down picks router / class C subnet / domain / AS and runs `collapseBy` on that field. The AS level is the BGP view of §2.1.2.
- *GUESS:* BFS paths (`toNetworkX` + networkx), `collapseBy`/`expandAll`, `every` for the step animation, `Slider`.

**`ch02-telephone`: Circuit switching in the telephone network (§2.2)** · built
- *Idea:* there are three tiers (subscribers, local exchanges, long-distance offices). Local calls never use a trunk, and trunk capacity limits how many calls connect.
- *Data:* a generated three-tier network laid out by region.
- *Reader:*
  - "Place 20 calls" picks random pairs, and a "local share" slider controls how many are local;
  - each connected call holds its circuit (the edges glow while it lasts), and a call that finds a full trunk is blocked (red flash);
  - counters show calls connected, calls blocked and trunk load;
  - a "trunk capacity" slider shows blocking rise as capacity falls.
- *GUESS:* `every` timer, edge `width` and `color` for load, `flow` style for active circuits, `Slider`.

**`ch02-power-cascade`: Cascading failures in a power grid (§2.3)** · built
- *As built:* uses real data, 400 stations of the Western US grid (Watts–Strogatz, via Newman; `power-grid-region.gdf`). The outage chart is a log–log CCDF in a `Chart` widget.
- *Idea:*
  - When a line or station fails, its load moves elsewhere and can cause more failures.
  - Outage sizes are heavy-tailed.
  - The book cautions that topology alone predicts little; the explainer says so.
- *Data:* a generated grid-like network (geometric random graph, ~300 nodes). Its load is betweenness, and capacity = (1+α)·initial load (the Motter–Lai model).
- *Reader:*
  - clicks a station to fail it and watches the cascade round by round;
  - the α slider sets the tolerance;
  - "Run 200 random failures" plots outage sizes on log–log axes.
- *GUESS:* `recompute('betweenness')`, `remove`/`add(g.deleted)`, `after` for the rounds, an Altair log–log chart (see the gaps below).

**`ch02-rail-spaces`: Which network is the rail network? (§2.4)** · built
- *As built:* the three views morph between saved states; `project()` isn't used, because it opens a new graph tab.
- *Idea:* Sen et al.'s point: a traveller counts trains, not stops. There are three representations:
  - stops linked in sequence;
  - stations linked when one train serves both (P-space);
  - stations–routes bipartite, with its projection.
- *Data:* a generated set of 6–8 train lines over ~40 stations, on map-like coordinates.
- *Reader:*
  - morphs between the three views (`ss`/`morph`);
  - clicks two stations to see "stops" against "trains needed" in each view;
  - in the bipartite view, "Project onto stations" builds P-space live with `project()`.
- *GUESS:* states and `morph`, `project`, `bipartiteLayout`, `shortestPath`.

**`ch02-river-trees`: Rivers are trees (§2.5)** · built
- *As built:* the toy gas network was left out. The Buffon lines use the new `drawLine`/`drawCircle`.
- *Idea:*
  - distribution and collection networks;
  - a river has no loops, so water drains by exactly one path;
  - pipe and river sizes come from the area they drain.
- *Data:*
  - a river network grown on a lattice (a random spanning tree drained towards an outlet), with edge width set by the area drained;
  - a small toy gas network with pipe sizes.
- *Reader:*
  - clicks any point to trace its single path to the outlet;
  - "Add a loop" adds an edge and shows that water now has two routes;
  - a "Buffon's lines" button overlays a grid of parallel lines, counts crossings and estimates total river length against the true length.
- *GUESS:* `spanningTree`, `treeLayout`/positions, `sizeBy` on edges, `ancestors`/`descendants`. The overlay lines are drawn as hidden-node edges (see the gaps below).

### Ch. 3 Networks of information (pp. 32–46)

**`ch03-web-crawler`: How a crawler finds the Web (§3.1)** · built
- *Idea:*
  - the Web is directed;
  - a crawler does a breadth-first search from a start page, using a store of URLs it has seen;
  - pages nobody links to are never found, so the crawl only reaches what the start page can reach.
- *Data:* a generated directed web of ~150 pages in a few "sites", with some orphan pages.
- *Reader:*
  - clicks a start page, then steps or plays the crawl;
  - colours mark unseen, queued and downloaded pages;
  - a side panel lists the store, oldest first;
  - at the end, the unreached pages stay grey and a line reports "found 61%";
  - trying other start pages shows how much (or how little) the start matters.
- *GUESS:* `descendants`, `every`, `Markdown` panel, `arrowhead`.

**`ch03-citations`: Citation networks point back in time (§3.2, §3.2.1)** · built
- *Idea:*
  - citations are acyclic, so a path never returns to where it started;
  - most papers are cited rarely;
  - cocitation (cited together) and bibliographic coupling (citing the same papers) give weighted undirected networks.
  - Patent and legal citations have the same structure.
- *Data:* `vis-papers.gdf` (bundled).
- *Reader:*
  - lays the papers out by year (`orderedLayout(year)`), so every arrow points left;
  - `findCycles()` finds none;
  - a chart shows the share of papers with 0, 1, 2, … citations;
  - selecting a paper highlights the papers cocited with it and those coupled to it, with the shared references;
  - buttons build the weighted cocitation or coupling network in a new tab, coloured by community;
  - `mainPath()` shows the backbone.
- *GUESS:* `orderedLayout`, `findCycles`, `plotHistogram`, `newGraph`/`use`, `mainPath`, `louvainClusters`. Cocitation is computed in the script.

**`ch03-p2p-search`: Searching a peer-to-peer network (§3.3.1)** · built
- *Idea:* flooding search with a hop limit works on small networks but floods the network with messages. Supernodes fix that.
- *Data:* a generated network of 200 peers. A file is copied onto a few random peers.
- *Reader:*
  - clicks a peer and searches;
  - the query spreads in rings, hop by hop, until it is found or the TTL runs out;
  - counters show the messages sent;
  - a TTL slider controls the hop limit;
  - "Use supernodes" switches to the two-tier design and compares the message counts.
- *GUESS:* BFS by rings, `every`, `heatMap` or colour by hop, `concentricLayout(tier)` for the two-tier view.

**`ch03-recommender`: Recommendations from a bipartite network (§3.3.2)** · built
- *Idea:*
  - people and items form a bipartite network, with like/dislike weights;
  - recommend what similar people liked.
- *Data:* generated people and films with ratings drawn from a few taste groups.
- *Reader:*
  - sees people on one side and films on the other (`bipartiteLayout`), with edges coloured from dislike to like;
  - clicks a person to see their most similar people (shared likes) and the recommended films, with a reason ("liked by 3 people like you");
  - a "Hide one rating and predict it" button shows a hit or a miss.
- *GUESS:* `bipartiteLayout`, `similarTo`, `project`, `colorBy` on edge weight.

**`ch03-keyword-index`: A book index is a network (§3.3.3)** · built
- *Idea:*
  - a keyword index is a words–pages bipartite network;
  - documents that share words are similar;
  - LSA (an SVD of the incidence matrix) finds similarity even without shared words.
- *Data:* `scandal-in-bohemia.txt`. The "pages" are paragraphs and the words are the top terms.
- *Reader:*
  - sees the words–paragraphs bipartite network and clicks a word to see its paragraphs;
  - clicks a paragraph to see its nearest paragraphs by shared words, then by LSA;
  - a "Place by LSA" button lays the paragraphs out on the first two singular vectors.
- *GUESS:* building the incidence matrix in the script (numpy), `scatterLayout`, `makeFromText` for the terms, `similarTo`.

### Gaps found in batch 1, and what was done

| need | done |
|---|---|
| A chart inside an app panel | **added** `Chart(fn)`: a widget that runs a plot command (or returns an Altair chart) and redraws after every command |
| Log–log axes for distributions | **added** `log=` on `plotHistogram`/`plotDistrib`. New: `plotFrequency(field, log, cumulative)`, which plots p(k) or its CCDF, and `plotLine(points or {series: points}, log/logX/logY, dots)` |
| Lines and text over the graph | **added** `drawLine`, `drawText`, `drawRect`, `drawCircle`, `removeDrawing`, `clearDrawings`, `getDrawings`. Drawings are saved with sessions, undoable, and included in exports |
| Markdown emphasis across line breaks | **fixed**: `**bold**` and `*italics*` may now wrap within a paragraph or list item in `Markdown` panels |
| Real infrastructure data | **added** `power-grid-region.gdf` and `internet-as-sample.gdf` from Mark Newman's network data page (`cookbooks/data/make_newman.py`). Neither file states a licence; both carry the authors' citations |
| Patent and legal citation data | not added. The citations explainer says the structure is the same |

Tests: `py/tests/test_explainers.py` runs every script and drives its controls; `web/e2e/explainers.spec.ts` opens each one in the browser.

---

## Batch 2: book pages 47–101 (Chapters 4–5)

This batch runs five pages past 96 so that it ends at the end of Chapter 5.

### Ch. 4 Social networks (pp. 47–69)

**`ch04-sociograms`: Sociograms and what an edge means (§4.1)** · built
- *Idea:* Moreno's sociograms make simple patterns obvious (friendships rarely cross the boys/girls line). What counts as a tie depends on the question.
- *Data:* a generated class of 30 children with a `gender` field and three kinds of ties (friend, sits near, plays with).
- *Reader:*
  - boys are triangles and girls circles;
  - a counter shows the ties within and between groups;
  - a drop-down switches the kind of tie, and the picture and the count change;
  - "Stack the three" shows the same people as a multiplex network (`isometricLayout`).
- *GUESS:* `shapeBy`, `mixingMatrix`, `assortativity`, edge `kind` + visibility, `isometricLayout`.

**`ch04-name-generator`: Asking people who their friends are (§4.2)** · built
- *Idea:*
  - a name generator gives a **directed** network, and nominations aren't always returned;
  - a fixed-choice limit caps out-degree but not in-degree, so popular people still stand out, while the true hubs among the nominators are hidden.
- *Data:* a generated "true" school friendship network with a few very sociable and a few very popular students.
- *Reader:*
  - the "name up to k friends" slider (1–10, or no limit) redraws the surveyed network;
  - charts of in- and out-degree (`Chart` + `plotFrequency`) show the cap;
  - a reciprocity readout shows how many nominations are returned;
  - a toggle adds the doctors' three questions (advice / discussion / social) as layers.
- *GUESS:* `addDirectedEdge`, `reciprocity`, `Chart`, `plotFrequency`, `isometricLayout`.

**`ch04-ego-networks`: Ego-centred surveys and how many people you know (§4.2.1)** · built
- *Idea:*
  - surveying random egos and their alters gives local facts (degree, clustering) without the whole network;
  - Bernard's scale-up method estimates how many people someone knows from a list of names.
- *Data:* a generated town of ~600 people with clustered friendships and surnames drawn from a frequency list.
- *Reader:*
  - **Ego tab:** "Interview 10 random people" highlights the egos, their alters and the alter–alter ties, and estimates mean degree and clustering, with error bars against the truth as more egos are added.
  - **Scale-up tab:** pick a person and a name list covering p% of the town; the count of people known on the list, divided by p, estimates the person's acquaintances, shown against the true number.
- *GUESS:* `egoNetwork`, `averageClustering`, custom sampling, `plotLine`.

**`ch04-observing-dolphins`: Building a network by watching (§4.3)** · built
- *Idea:* direct observation records interactions, and a tie is declared when a pair is seen together often enough. The network you get depends on the threshold and on how long you watch.
- *Data:* Lusseau's bottlenose dolphins of Doubtful Sound (from Newman's network data page; to be added with `make_newman.py`) as the hidden "true" associations, with generated sighting rates.
- *Reader:*
  - "Watch for 10 days" accumulates sightings;
  - a threshold slider ("seen together at least n times") redraws the network;
  - readouts show the true links found, the false links and the communities;
  - the observed network converges as days are added.
- *GUESS:* edge `weight` from counts, visibility filters, `louvainClusters`, `compareClusters`.

**`ch04-florentine-and-email`: Networks from records (§4.4)** · built
- *Idea:*
  - archival records rebuild networks from the past, such as the Medici's central place in Florence's marriage network;
  - modern records (email, calls) are **time-resolved**.
- *Data:* `florentine.gdf` (bundled); a generated email log with timestamps.
- *Reader:*
  - **Florence tab:** families sized by betweenness; "Remove the Medici" shows how much falls apart.
  - **Email tab:** a timeline slider (`showTime`) plays a month of email; who talks to whom changes by week, and the "all month" view hides that.
- *GUESS:* `betweenness`, `remove`/`add`, `showTime`/timeline, edge `time` ranges.

**`ch04-affiliation`: Affiliation networks and their projections (§4.5)** · built
- *Idea:* actors linked through groups form a bipartite network. Projecting it onto actors or groups loses information: big groups become cliques, and you can't tell one big meeting from many small ones.
- *Data:* `southern-women.gdf` (bundled), and authors and papers from `vis-paper-authors.csv` (bundled; OpenAlex) as a coauthorship example.
- *Reader:*
  - switch datasets;
  - see the bipartite network (`bipartiteLayout`);
  - project onto people or onto groups (`project`, with count, Jaccard or Newman weights);
  - find the two Southern Women groups (communities);
  - click a pair to see what the projection hides (which events they shared).
- *GUESS:* `bipartiteLayout`, `project`, `louvainClusters`, `use()` between tabs.

**`ch04-milgram`: The small-world experiment (§4.6)** · built
- *Idea:*
  - letters forwarded only to first-name acquaintances, each towards a target, arrive in about six steps;
  - chains get lost, and lost chains bias the result towards short ones;
  - funnelling: most arrive through a few of the target's friends;
  - people can *find* short paths using geography and occupation (Kleinberg).
- *Data:* a generated society on a grid map (`makeKleinbergRandom`-style long-range links), each person with a town and an occupation.
- *Reader:*
  - "Send 96 letters" from one town to a target far away; each holder forwards greedily by distance and occupation, and drops out with probability *p*;
  - completed chains are drawn as paths;
  - readouts show the share completed, the mean length of completed chains against the true mean shortest path, and which of the target's friends delivered them;
  - a drop-out slider shows the length bias.
- *GUESS:* `makeKleinbergRandom` or custom generation, `shortestPath`, `drawLine` for chains, `Chart`.

**`ch04-snowball`: Sampling hidden populations (§4.7)** · built
- *Idea:*
  - snowball sampling over-samples well-connected people (roughly in proportion to eigenvector centrality);
  - random-walk sampling samples in proportion to degree, which can be corrected for, giving unbiased estimates;
  - respondent-driven sampling (tickets) works like a random walk.
- *Data:* a generated network with a hidden attribute that correlates with degree.
- *Reader:*
  - run snowball waves (by colour) or a random walk from a seed;
  - compare the sample's mean degree and attribute prevalence with the truth;
  - see the raw and degree-reweighted random-walk estimates converge;
  - a chart of the estimate against sample size.
- *GUESS:* `eigenvector`, custom sampling, `plotLine`, `Chart`.

### Ch. 5 Biological networks (pp. 70–101)

**`ch05-metabolism`: Five ways to draw a metabolic network (§5.1.1)** · built
- *Idea:*
  - the full picture is a directed bipartite network of metabolites and reactions (tripartite with enzymes);
  - the usual pictures are projections that lose information;
  - currency metabolites (ATP, NAD⁺, water) become false hubs.
- *Data:* glycolysis written out by hand from standard textbook reactions (10 reactions, their enzymes, substrates and products).
- *Reader:* a drop-down morphs between:
  - bipartite;
  - tripartite (+ enzymes);
  - metabolite projection (undirected);
  - substrate→product (directed);
  - with or without currency metabolites.
  A readout counts edges and the top hubs in each.
- *GUESS:* states and `morph`, `shapeBy`, `arrowhead`, `project`-like construction in the script.

**`ch05-ppi-errors`: Protein interactions and noisy experiments (§5.1.2)** · built
- *Idea:*
  - two-hybrid screens test pairs (bait × prey) and have high false-positive and false-negative rates;
  - affinity purification pulls down whole complexes, recorded as "spoke" or "matrix" edges.
- *Data:* `yeast-modules.gdf` (bundled, STRING).
- *Reader:*
  - false-positive and false-negative sliders redraw a "measured" network, with readouts for the modules recovered (NMI against `module`) and the hubs kept;
  - for one complex, spoke against matrix shows how the same pull-down gives very different networks.
- *GUESS:* sampling in the script, `louvainClusters`, `compareClusters`, edge colours for false/true.

**`ch05-gene-regulation`: Switching genes on and off (§5.1.3)** · built
- *Idea:* transcription factors promote or inhibit other genes, giving a directed, signed network. Its loops produce memory and oscillation.
- *Data:* `pheromone-pathway.csv` (bundled, signed), plus three textbook circuits: a toggle switch, a repressilator and a feed-forward loop.
- *Reader:*
  - promoting edges are arrows and inhibiting edges tees (`arrowhead = 'tee'`);
  - a Boolean simulation steps every second (`every`), with nodes lit when on;
  - click a gene to force it on or off and watch the effect spread;
  - the repressilator oscillates and the toggle remembers.
- *GUESS:* `arrowheadBy`, `every`, `Chart` (on/off over time with `plotLine`).

**`ch05-drugs-diseases`: Drug, target and disease networks (§5.1.4)** · built
- *Idea:*
  - drug–target and disease–gene bipartite networks;
  - projecting gives drug–drug or disease–disease networks, and related diseases cluster;
  - a protein's folded chain is a network of contacts.
- *Data:* **needed**. A small illustrative drug–target set can be written by hand; the human diseasome (Goh et al. 2007) and protein contact maps (PDB) are not bundled. See the gaps below.
- *Reader:*
  - project the bipartite network either way;
  - clusters appear;
  - for the protein, a contact network from 3D coordinates at a distance threshold slider.
- *GUESS:* `project`, `bipartiteLayout`, `makeFromSimilarity`/threshold.

**`ch05-worm-brain`: The wiring of *C. elegans* (§5.2.1)** · built
- *Idea:* neurons as nodes and synapses as directed edges; signals pass when enough inputs fire.
- *Data:* the *C. elegans* neural network (White et al., via Newman's network data page; to be added with `make_newman.py`).
- *Reader:*
  - stimulate a few neurons and watch a threshold model of firing spread step by step;
  - a threshold slider sets how many inputs a neuron needs;
  - hubs and in/out-degree charts.
- *GUESS:* `every`, `colorBy`, `Chart`.

**`ch05-functional-brain`: Brain networks from correlations (§5.2.2)** · built
- *Idea:* fMRI doesn't see wires. Edges are inferred where regions' activity correlates, so the network depends on the threshold.
- *Data:* generated activity time series for ~40 regions in 4 systems.
- *Reader:*
  - a threshold slider on the correlation redraws the network;
  - modules appear, then merge into a hairball;
  - one region's time series is shown against a neighbour's (`plotLine`).
- *GUESS:* numpy correlation, `Chart`/`plotLine`, `louvainClusters`.

**`ch05-food-webs`: Who eats whom (§5.3.1)** · built
- *Idea:*
  - edges run from prey to predator (energy flow), nearly acyclic;
  - trophic level, with mixed levels for omnivores;
  - source and sink webs;
  - trophic species (lumping species with the same predators and prey).
- *Data:* `makeNicheModel` webs, or a real web from GloBI (`makeFromGloBI`, online).
- *Reader:*
  - drawn by trophic level;
  - click a species for its source web (`descendants`) or sink web (`ancestors`);
  - "Find loops" shows the few cycles;
  - "Lump trophic species" merges identical roles (`mergeNodes`).
- *GUESS:* `trophicLevels`, `orderedLayout`, `ancestors`/`descendants`, `findCycles`, `mergeNodes`.

**`ch05-mutualism`: Pollinators, parasites and nestedness (§5.3.2)** · built
- *Idea:*
  - mutualistic networks are undirected and bipartite, and often **nested**: specialists use subsets of what generalists use;
  - parasites have parasites of their own.
- *Data:* a generated plant–pollinator matrix with a nestedness slider (or GloBI online).
- *Reader:*
  - the matrix view and bipartite view;
  - NODF (`nestedness`) as the slider changes;
  - "remove the generalists" shows how much collapses.
- *GUESS:* `nestedness`, `bipartiteLayout`, `remove`.

### Gaps found in batch 2

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| Dolphin and *C. elegans* datasets | observing-dolphins, worm-brain | not bundled; both on Newman's page | add to `make_newman.py` (dolphins: Lusseau et al. 2003; C. elegans: White et al. 1986 / Watts–Strogatz 1998) |
| Human diseasome / drug–target data | drugs-diseases | not bundled; licences vary (DrugBank is restrictive) | small hand-written illustrative set, clearly marked; or fetch an open set at run time |
| Protein structure → contact network | drugs-diseases | no PDB/mmCIF reader | `makeFromPDB(file or id, cutoff=8)`: residues as nodes, contacts within the cutoff as edges (RCSB serves files with CORS) |
| Brain connectome data | functional-brain | not bundled | generated data for now; an open connectome (e.g., a macaque or human parcellation) could be added |
| Mutualistic network data (Interaction Web Database) | mutualism | not bundled; GloBI connector is online-only | generated, or GloBI online |
| A matrix (adjacency heat map) view | mutualism, functional-brain, later Ch. 6 | none; charts are bar/line/pie or Altair | `showMatrix(order=field)`: an adjacency matrix in the dock, rows sorted by a field, linked to the graph like other charts (could be built on Altair `mark_rect`) |

---

## Batch 3: book pages 102–157 (Chapter 6, the start of Part II)

This batch runs past 151 so that it ends at the end of Chapter 6, *Mathematics of networks*. From here on the explainers pair each picture with the matrix or the numbers behind it.

**`ch06-adjacency-matrix`: The adjacency matrix (§§6.1–6.3)** · planned
- *Idea:*
  - a network and its adjacency matrix are the same thing;
  - multiedges put 2s, 3s, … off the diagonal, and a self-edge puts a **2** on the diagonal;
  - weighted networks hold weights in the cells.
- *Reader:*
  - a 6-node network beside its matrix (numbers shown);
  - click two nodes to add or remove an edge and watch the matrix change;
  - buttons add a double edge or a self-edge;
  - a weight slider on the selected edge;
  - the readout shows symmetric/not, Σ of a row = degree, and Σ of all cells = 2m.
- *GUESS:* `showMatrix` (needs numbers in cells and self-edges counted twice; see gaps), `Chart`, `graphevents`.

**`ch06-acyclic`: Directed and acyclic networks (§6.4)** · planned
- *Idea:*
  - directed adjacency matrices aren't symmetric;
  - a network is acyclic exactly when you can repeatedly remove a node with no outgoing edges;
  - numbering the nodes in that order makes the matrix strictly triangular.
- *Reader:*
  - step through the removal algorithm (each removed node gets its number and drops to its row in the drawing);
  - the matrix, ordered by the numbers, fills in as an upper triangle;
  - "Add an edge that closes a loop", then run again: the algorithm gets stuck, and the stuck nodes are a cycle (red).
- *GUESS:* `findCycles`, `showMatrix(order=)`, positions by order, `every`.

**`ch06-hypergraphs`: Hypergraphs, bipartite networks and projections (§§6.5–6.6)** · planned
- *Idea:*
  - groups (families, papers, films) as hyperedges, the same information as a bipartite network;
  - the incidence matrix B;
  - the projection P = BᵀB, whose diagonal counts each node's groups and off-diagonal shared groups;
  - projections are unions of cliques.
- *Reader:*
  - morph between three views: hyperedges drawn as shaded loops (`encircle`), bipartite, and weighted projection (edge labels = shared groups);
  - B and P shown as matrices;
  - "Add a group of 5" shows a 5-clique appear.
- *GUESS:* `encircle`, states and `morph`, `project`, `showMatrix` (rectangular B; see gaps).

**`ch06-multilayer`: Multilayer, multiplex and temporal networks (§6.7)** · planned
- *Idea:*
  - layers of different node types with interlayer edges (a bus, train and air journey);
  - **multiplex** layers on the same people (friends, work, family);
  - **temporal** networks as ordered layers whose interlayer edges only go forward in time (infection can't go back in time).
- *Reader:*
  - the transport tab plans a journey that changes layers (`isometricLayout`), and the shortest trip is counted in transfers or in minutes;
  - the multiplex tab toggles layers on and off;
  - the temporal tab spreads an infection forward through daily contact layers; the same contacts with time ignored would infect more people.
- *GUESS:* `isometricLayout`, `shortestPath(weighted=true)`, node copies per layer (see gaps).

**`ch06-trees-planar`: Trees and planar networks (§§6.8–6.9)** · planned
- *Idea:*
  - a tree has n − 1 edges and exactly one path between any two nodes, and any node can be the root;
  - a planar network can be drawn with no crossings;
  - K₅ and K₃,₃ can't;
  - maps make planar networks, and four colours always suffice.
- *Reader:*
  - **Tree tab:** click a node to re-root (`treeLayout`), add an edge to see the loop.
  - **Planar tab:** drag nodes to remove crossings, with a live crossing counter; try K₅ and K₃,₃ (never 0).
  - **Map tab:** regions of a generated map (or US states) and their adjacency network, coloured with four colours step by step.
- *GUESS:* `treeLayout`, `addEdge`, crossing count and colouring (see gaps), node-drag refresh.

**`ch06-degree-sparsity`: Degree, density and sparsity (§6.10)** · planned
- *Idea:*
  - 2m = Σ degrees;
  - mean degree c = 2m/n;
  - density ρ = c/(n−1);
  - real networks are sparse;
  - if each person keeps about the same number of friends as the population grows, density falls like 1/n;
  - in directed networks, mean in-degree = mean out-degree.
- *Reader:*
  - grow a network node by node under two rules ("a fixed number of friends" against "a fixed share of everyone") and chart density against n;
  - on any bundled dataset, read off m, c and ρ, and check 2m = Σk.
- *GUESS:* `addNode`/`addEdge` in a timer, `density`, `Chart`, `plotLine`.

**`ch06-walks-paths`: Walks, paths and powers of A (§6.11)** · planned
- *Idea:*
  - the number of walks of length r from j to i is [Aʳ]ᵢⱼ;
  - loops of length r total Tr Aʳ;
  - the shortest path is the smallest r with [Aʳ]ᵢⱼ > 0;
  - shortest paths need not be unique;
  - the diameter.
- *Reader:*
  - click two nodes and step r = 1, 2, 3 …: the count of walks, the nodes reachable in exactly r steps lit up ring by ring, and the moment the target is first reached (= distance);
  - all shortest paths are drawn together;
  - a table of Tr Aʳ.
- *GUESS:* numpy matrix powers, `shortestPath`, networkx `all_shortest_paths`, `diameter`.

**`ch06-components`: Components, weak and strong (§6.12)** · planned
- *Idea:*
  - components;
  - block-diagonal matrices when ordered by component;
  - in directed networks: weakly and strongly connected components, and a node's in- and out-components, whose intersection is its strongly connected component.
- *Reader:*
  - an undirected tab colours the components, with the matrix ordered by component (blocks);
  - a directed tab shows weak against strong components;
  - clicking a node shades its in-component, its out-component and their overlap.
- *GUESS:* `component`, `strongcomponent`, `ancestors`/`descendants`, `encircle`, `showMatrix(order=component)`.

**`ch06-cuts-flows`: Independent paths, cut sets and maximum flow (§6.13)** · planned
- *Idea:*
  - edge- and node-independent paths;
  - Menger's theorem: their number equals the size of the minimum cut set;
  - max-flow/min-cut on weighted networks.
- *Reader:*
  - click A and B;
  - the edge-independent paths are drawn in distinct colours, the node-independent ones in another view, and the minimum cut set is crossed out, with the counts equal;
  - the weighted tab sets edge capacities (widths) and shows the maximum flow (`flow` style) beside the minimum cut, equal.
- *GUESS:* `maxFlow`, `minCut`, networkx `edge_disjoint_paths`/`node_disjoint_paths`, `flow` line style.

**`ch06-laplacian`: The graph Laplacian (§6.14)** · planned
- *Idea:* L = D − A, and four uses:
  - **partitioning:** the cut size is ¼ sᵀLs, and the Fiedler vector's signs give a good split;
  - **drawing:** the sum of squared edge lengths is xᵀLx, minimised by the Laplacian's eigenvectors;
  - **random walks:** a walker is found at node i with probability kᵢ/2m;
  - **resistor networks:** LV = RI.
  - Also: eigenvalues ≥ 0, the number of zero eigenvalues = the number of components, and the algebraic connectivity.
- *Reader:* five tabs:
  - **Spectrum:** an eigenvalue chart; cut edges until it splits and watch a second zero appear.
  - **Partition:** colour by the Fiedler vector, with the cut size.
  - **Drawing:** a random layout against a spectral layout, with xᵀLx for each.
  - **Random walk:** a walker runs, and a chart of visit share against degree is a straight line.
  - **Resistors:** click s and t, nodes coloured by voltage, current along edges (`flow`), and the effective resistance.
- *GUESS:* numpy `eigh`, `Chart`/`plotLine`, `every`, edge `flow` style.

### Gaps found in batch 3

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| Matrix cells with their numbers; self-edges counted 2 on the diagonal (1 if directed); rectangular matrices (incidence B: groups × items) | adjacency-matrix, hypergraphs, acyclic | `showMatrix` shades cells but prints no numbers, and is always square | `showMatrix(numbers=true, rows=…, cols=…)` |
| Copies of each node per layer (multiplex/temporal), with interlayer edges, for `isometricLayout` | multilayer | `isometricLayout` stacks by a node field, so a node can be in only one layer | `expandLayers(edgeField)`: one copy of each node per value of an edge field, interlayer edges between copies (direction optional, for time) |
| Counting edge crossings in the current drawing | trees-planar (and layout comparisons generally) | none | `edgeCrossings()`: the number of crossings (and optionally the crossing pairs) |
| Graph colouring (no two neighbours alike) | trees-planar | none | `colorGraph(strategy="DSATUR")`: a colour class per node in `color_class` (networkx greedy colouring) |
| Region adjacency from a map (US states, countries) | trees-planar | the map outlines exist (geoLayout) but no adjacency network | `makeFromMap("usa")`: one node per state or country, edges for shared borders |
| A spectrum chart (eigenvalues of A, L or the normalised Laplacian) | laplacian, later Ch. 7/14/17 | numpy can compute it in a script; no command | `plotSpectrum(matrix="laplacian")` (and `spectrum()` returning the values) |

---

## To do (requests not yet done)

- **Lombardi-style layout and edge rounding**, as described in `lombardi.pdf` (repo root): circular-arc edges with evenly spaced angles around each node. Planned as a layout command plus an edge-drawing mode.
- Batch 3 (Chapter 6): fill the gaps listed above, then build its 10 explainers.
