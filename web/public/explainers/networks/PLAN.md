# Explainers for Newman, *Networks* (2nd ed.): plan

One small GUESS app per section, each one a `<id>/manifest.json` + `<id>/main.gy`
in this folder, opened as `index.html?app=explainers/networks/<id>/manifest.json`.
`index.html` here lists them all. Explainers explain in their own words and use
their own or bundled data; they don't reproduce the book's text or figures.

Page numbers are the book's (PDF page = book page + 13).

Status: **planned** → **built** → **checked**.

Conventions for every explainer (from review feedback):
- Labels are readable: `constantLabelSize(size=14)`.
- State changes are visible: bigger nodes and outlines (`strokewidth`), not just a colour change; bright fills with dark outlines read on both themes, while black fills look hollow on the dark one.
- Evolving processes (transmission, flow, mutation, search) highlight the edges involved.
- Simulations run slow-fast-slow (`everyPaced`) so they can be watched.
- Show data as it is collected (live `Chart(fn)`), and give "Simulate" buttons that sweep parameters.
- **Several components:** lay out, then `binPackLayout()` to pack the components side by side, then `noverlapLayout()` so no nodes overlap; use `binPackLayout(false)` when rescaling would stretch small pieces, and a bigger `margin=` when labels are shown. This doesn't apply where positions mean something (maps, anatomy, time axes).
- **Growing networks:** build the final network first and lay it out once. Give each node and edge the step at which it arrives (`born`), fit the view to the final picture (`center(g.nodes)`), then reveal it with `revealUpTo(step)`. Nodes appear where they will stay; nothing moves as it grows.

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

**`ch06-adjacency-matrix`: The adjacency matrix (§§6.1–6.3)** · built
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

**`ch06-acyclic`: Directed and acyclic networks (§6.4)** · built
- *Idea:*
  - directed adjacency matrices aren't symmetric;
  - a network is acyclic exactly when you can repeatedly remove a node with no outgoing edges;
  - numbering the nodes in that order makes the matrix strictly triangular.
- *Reader:*
  - step through the removal algorithm (each removed node gets its number and drops to its row in the drawing);
  - the matrix, ordered by the numbers, fills in as an upper triangle;
  - "Add an edge that closes a loop", then run again: the algorithm gets stuck, and the stuck nodes are a cycle (red).
- *GUESS:* `findCycles`, `showMatrix(order=)`, positions by order, `every`.

**`ch06-hypergraphs`: Hypergraphs, bipartite networks and projections (§§6.5–6.6)** · built
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

**`ch06-multilayer`: Multilayer, multiplex and temporal networks (§6.7)** · built
- *Idea:*
  - layers of different node types with interlayer edges (a bus, train and air journey);
  - **multiplex** layers on the same people (friends, work, family);
  - **temporal** networks as ordered layers whose interlayer edges only go forward in time (infection can't go back in time).
- *Reader:*
  - the transport tab plans a journey that changes layers (`isometricLayout`), and the shortest trip is counted in transfers or in minutes;
  - the multiplex tab toggles layers on and off;
  - the temporal tab spreads an infection forward through daily contact layers; the same contacts with time ignored would infect more people.
- *GUESS:* `isometricLayout`, `shortestPath(weighted=true)`, node copies per layer (see gaps).

**`ch06-trees-planar`: Trees and planar networks (§§6.8–6.9)** · built
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

**`ch06-degree-sparsity`: Degree, density and sparsity (§6.10)** · built
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

**`ch06-walks-paths`: Walks, paths and powers of A (§6.11)** · built
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

**`ch06-components`: Components, weak and strong (§6.12)** · built
- *Idea:*
  - components;
  - block-diagonal matrices when ordered by component;
  - in directed networks: weakly and strongly connected components, and a node's in- and out-components, whose intersection is its strongly connected component.
- *Reader:*
  - an undirected tab colours the components, with the matrix ordered by component (blocks);
  - a directed tab shows weak against strong components;
  - clicking a node shades its in-component, its out-component and their overlap.
- *GUESS:* `component`, `strongcomponent`, `ancestors`/`descendants`, `encircle`, `showMatrix(order=component)`.

**`ch06-cuts-flows`: Independent paths, cut sets and maximum flow (§6.13)** · built
- *Idea:*
  - edge- and node-independent paths;
  - Menger's theorem: their number equals the size of the minimum cut set;
  - max-flow/min-cut on weighted networks.
- *Reader:*
  - click A and B;
  - the edge-independent paths are drawn in distinct colours, the node-independent ones in another view, and the minimum cut set is crossed out, with the counts equal;
  - the weighted tab sets edge capacities (widths) and shows the maximum flow (`flow` style) beside the minimum cut, equal.
- *GUESS:* `maxFlow`, `minCut`, networkx `edge_disjoint_paths`/`node_disjoint_paths`, `flow` line style.

**`ch06-laplacian`: The graph Laplacian (§6.14)** · built
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

### Gaps found in batch 3 (all added: `showMatrix(numbers=, rows=, cols=)`, `expandLayers`, `edgeCrossings`, `colorGraph`, `makeFromMap`, `spectrum`/`plotSpectrum`; also Markdown tables in panels)

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| Matrix cells with their numbers; self-edges counted 2 on the diagonal (1 if directed); rectangular matrices (incidence B: groups × items) | adjacency-matrix, hypergraphs, acyclic | `showMatrix` shades cells but prints no numbers, and is always square | `showMatrix(numbers=true, rows=…, cols=…)` |
| Copies of each node per layer (multiplex/temporal), with interlayer edges, for `isometricLayout` | multilayer | `isometricLayout` stacks by a node field, so a node can be in only one layer | `expandLayers(edgeField)`: one copy of each node per value of an edge field, interlayer edges between copies (direction optional, for time) |
| Counting edge crossings in the current drawing | trees-planar (and layout comparisons generally) | none | `edgeCrossings()`: the number of crossings (and optionally the crossing pairs) |
| Graph colouring (no two neighbours alike) | trees-planar | none | `colorGraph(strategy="DSATUR")`: a colour class per node in `color_class` (networkx greedy colouring) |
| Region adjacency from a map (US states, countries) | trees-planar | the map outlines exist (geoLayout) but no adjacency network | `makeFromMap("usa")`: one node per state or country, edges for shared borders |
| A spectrum chart (eigenvalues of A, L or the normalised Laplacian) | laplacian, later Ch. 7/14/17 | numpy can compute it in a script; no command | `plotSpectrum(matrix="laplacian")` (and `spectrum()` returning the values) |

---

## Batch 4: book pages 158–217 (Chapter 7, *Measures and metrics*)

This batch runs past 207 so that it ends at the end of the chapter.

**`ch07-eigenvector-katz`: Eigenvector and Katz centrality (§§7.1.1–7.1.3)** · built
- *Idea:*
  - degree counts neighbours; eigenvector centrality counts *important* neighbours, the fixed point of x ← A x;
  - in directed networks, nodes no one points to get zero, and so do the nodes they point to;
  - Katz centrality adds a free amount β to every node, with α trading off between degree-like and eigenvector-like.
- *Reader:*
  - step the power iteration (paced): sizes settle onto the eigenvector, and a chart shows the change per step;
  - on a directed graph, watch zeros spread;
  - an α slider (up to 1/κ₁, which is shown) morphs sizes from degree to eigenvector;
  - a rank table across the measures.
- *GUESS:* numpy, `everyPaced`, `Chart`/`plotLine`, `sizeBy`.

**`ch07-pagerank-hits`: PageRank, hubs and authorities (§§7.1.4–7.1.5)** · built
- *Idea:*
  - PageRank divides each node's vote among its out-links, plus a random jump (damping);
  - it is where a random surfer spends its time;
  - HITS gives hubs (point to good authorities) and authorities (pointed to by good hubs).
- *Data:* the invented web from `ch03-web-crawler`, or `vis-papers.gdf`.
- *Reader:*
  - a random surfer animation (paced, edges highlighted as it moves, with jumps shown);
  - a visit-share chart converging to the PageRank values;
  - a damping slider;
  - dangling nodes;
  - a hubs/authorities toggle (`hub`, `authority` fields).
- *GUESS:* `pagerank`, `hub`/`authority`, `everyPaced`, `Chart`.

**`ch07-closeness-betweenness`: Closeness and betweenness (§§7.1.6–7.1.7)** · built
- *Idea:*
  - closeness is the inverse mean distance, a narrow range of values; harmonic closeness handles components;
  - betweenness is the share of shortest paths through a node; brokers score high with low degree.
- *Reader:*
  - click a node to see distance rings (`heatMap`) and its closeness and harmonic closeness;
  - pick two nodes to see all their shortest paths, each node's share of them, and how betweenness adds them up over all pairs (paced, pair by pair);
  - a degree-against-betweenness scatter (brokers stand out).
- *Data:* Les Misérables (bundled) or the US airports.
- *GUESS:* `heatMap`, `betweenness`, `closeness`, `harmonic`, scatter chart (see gaps).

**`ch07-groups`: Cliques, k-cores and k-components (§7.2)** · built
- *Idea:*
  - cliques;
  - k-cores, found by peeling away nodes of degree < k;
  - k-components need k independent paths, and are not the same as k-cores (Fig. 7.6's network has one 2-core but two 2-components).
- *Reader:*
  - peel the k-cores step by step (paced), each removal highlighting the node and its edges;
  - largest cliques as hulls;
  - bicomponents and tricomponents (`biComponentClusters`, networkx `k_components`);
  - a small example where the 2-core ≠ the 2-components.
- *GUESS:* `kCore`, `coreness`, `largestCliques`, `biComponentClusters`, `encircle`.

**`ch07-clustering`: Transitivity and clustering (§7.3)** · built
- *Idea:*
  - "a friend of a friend is a friend": global clustering = 3 × triangles / connected triples;
  - local clustering, often lower for high-degree nodes;
  - real networks have far more triangles than random ones with the same degrees.
- *Reader:*
  - click a node to see its triangles and open triples (closed in green, open dashed) and its local C;
  - a chart of C against degree;
  - "Rewire, keeping degrees" (`rewire`), paced, with C falling live.
- *GUESS:* `clustering`, `triangles`, `transitivity`, `rewire`, scatter chart.

**`ch07-reciprocity-balance`: Reciprocity and structural balance (§§7.4–7.5)** · built
- *Idea:*
  - reciprocity is the share of directed edges returned;
  - in signed networks, triangles with an odd number of negative edges are unbalanced;
  - a balanced network splits into two camps (Harary).
- *Reader:*
  - **Reciprocity tab:** mutual edges highlighted, with the value against what chance would give.
  - **Balance tab:** a signed network (green +, red −) with unbalanced triangles flashing; click an edge to flip its sign; or run the triad dynamics, which fix an unbalanced triangle at a time (paced) until it splits into two camps, coloured by Harary's division.
- *GUESS:* `reciprocity`, `mutualEdges`, `graphevents.clickEdge`, `everyPaced`, a balance check (see gaps).

**`ch07-similarity`: Structural and regular equivalence (§7.6)** · built
- *Idea:*
  - structural equivalence: sharing neighbours (cosine, Jaccard, Pearson);
  - regular equivalence: having *similar* neighbours (σ = αAσA + I, Leicht–Holme–Newman), which finds similar roles even far apart.
- *Reader:*
  - click a node and every node is coloured by similarity to it, with a drop-down of measures;
  - two roles in an invented organisation (managers in different departments share no neighbours but are regularly equivalent).
- *GUESS:* `similarTo`, numpy for the regular-equivalence fixed point.

**`ch07-assortativity`: Homophily and assortative mixing (§7.7)** · built
- *Idea:*
  - mixing by category (modularity Q, the mixing matrix);
  - by an ordered value (the correlation r across edges, e.g. age);
  - by degree (hubs with hubs, as in social networks, or hubs with small nodes, as in the Internet).
- *Reader:*
  - choose a dataset and attribute;
  - see the mixing matrix (`mixingMatrix` / `showMatrix(order=)`), Q and r;
  - see a scatter of the values at either end of each edge;
  - "Shuffle the edges, keeping degrees" (`rewire`) sends r to ≈ 0 live;
  - compare r for degree across the bundled networks (social vs technological).
- *GUESS:* `modularity`, `assortativity`, `mixingMatrix`, `rewire`, scatter chart.

### Gaps found in batch 4 (all added: `plotScatter`, `katzCentrality`, `structuralBalance`, `similarTo(method="regular")`, `kComponents`; also `assortativity(categorical=)`, scatter axes fitted to the data)

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| A scatter plot of two fields (points only, linked to the graph) | closeness-betweenness, clustering, assortativity (edge-end scatter) | `plotLine(dots=true)` joins the dots; Altair can scatter but is heavy | `plotScatter(x, y, log=False)` for nodes, and for edges with `ends=true` (value at one end against the other) |
| Signed networks: balance test, the two camps, unbalanced triangles | reciprocity-balance | none | `structuralBalance(sign)`: returns balanced?, sets `camp` on nodes, and the list of unbalanced triangles |
| Katz centrality with a chosen α (and β) | eigenvector-katz | `katz` is computed with a fixed α | `katzCentrality(alpha, beta=1)` |
| Regular-equivalence similarity | similarity | none (`similarTo` is structural) | `similarTo(node, method="regular", alpha=0.9)` |
| k-components | groups | `biComponentClusters` (k = 2) and igraph's `cohesiveBlocks` | `kComponents(k)` via networkx |

---

Also found while building batch 4 (not changed):
- Node names become Gython globals, so a node named `D` overwrites a variable `D`. `clash.py` checks names against commands and fields, not node names.
- `nx.k_components` takes about 4 s in Pyodide on 62 nodes, so `ch07-groups` computes the tricomponents in the background (`after(3, ...)`).
- `Button(onClick=f)` passes an argument to `f`, so a handler with a default parameter gets `None`. Use a lambda.
- There is no `isNeighbor` helper for nodes.

## Batch 5: book pages 218–274 (Chapter 8, *Computer algorithms*)

Chapter 8 is about how network calculations are done, so these explainers
animate algorithms step by step. Each shows the data structures (queue,
distances, counts) beside the graph, counts the operations, and has a
"Run at full speed" or "Simulate" button that times the algorithm on growing
networks and charts the running time.

**`ch08-complexity`: Software and running time (§§8.1–8.2)** · built
- *Idea:*
  - running time is measured by how it grows with n and m (big-O), not by seconds;
  - O(m + n) beats O(n²) beats O(n³) once networks get big, whatever the constants.
- *Reader:*
  - "Simulate": time three real calculations (degree count O(m), all-pairs distances by BFS O(n(m + n)), a naive O(n³) matrix product) on random networks of growing size;
  - a log–log chart of time against n, with guide lines of slope 1, 2 and 3, so the exponent is the slope;
  - a slider to extrapolate: "how long for a million nodes?".
- *GUESS:* `plotLine(log=true)`, random generators, Python timing.

**`ch08-storing`: Adjacency matrix, adjacency list and others (§8.3)** · built
- *Idea:*
  - the matrix uses n² memory, finds an edge in O(1) but lists neighbours in O(n);
  - the list uses O(m) memory, lists neighbours in O(k) but finds an edge in O(k);
  - hybrids, trees and hash tables trade memory for speed (Table 8.2).
- *Reader:*
  - side by side: the graph, its matrix (`showMatrix`) and its adjacency list (a live Markdown table);
  - click a node: its row lights up in the matrix and its list in the table, with the cells each structure touches counted;
  - click two nodes: "is there an edge?", with the cost in each structure;
  - add and remove edges by clicking, with the costs;
  - a memory chart against n for a sparse network (matrix n², list 2m, hash table ≈ 4m).
- *GUESS:* `showMatrix(numbers=true)`, Markdown tables, `graphevents`.

**`ch08-degrees-clustering`: Degrees and clustering, computed (§8.4)** · built
- *Idea:*
  - a degree is a list length (O(1));
  - local clustering checks every pair of a node's neighbours, k(k − 1)/2 checks, so the total cost is set by Σk², large when there are hubs.
- *Reader:*
  - step through one node's neighbour pairs (paced): each pair's edge is checked, closed pairs turn green and open ones are dashed;
  - the triangle count and C build up as you go;
  - "All nodes" runs the whole network with a live operations counter;
  - a chart comparing operations for a hub-heavy network and a uniform one with the same m.
- *GUESS:* `everyPaced`, edge highlighting, `Chart`.

**`ch08-bfs`: Breadth-first search (§§8.5.1–8.5.5)** · built
- *Idea:*
  - BFS finds distances from one node by layers: everything at distance d is found before d + 1;
  - the naive version rescans all nodes each round (O(n²) in the worst case); a first-in-first-out queue makes it O(m + n);
  - recording predecessors gives the shortest-path tree, and recording several gives every shortest path.
- *Reader:*
  - choose a source and step BFS (paced slow-fast-slow): the queue is shown as a row of chips, the current node is outlined, the edges examined are highlighted, and each node gets its distance as a label and its layer colour;
  - a naive/queue toggle with an operations counter;
  - "Show the shortest-path tree" (predecessor edges, tapered toward the source);
  - "all shortest paths" (multiple predecessors, path counts on the nodes).
- *GUESS:* `everyPaced`, labels, `heatMap`-like colouring, tapered directed edges for the tree.

**`ch08-betweenness-algorithm`: Computing betweenness (§8.5.6)** · built
- *Idea:*
  - the fast (Brandes / Newman) algorithm: one BFS per source counts shortest paths σ (adding counts from predecessors);
  - a backward pass sends each node's dependency to its predecessors in proportion to σ;
  - the sum over sources is betweenness, in O(n(m + n)) rather than O(n³).
- *Reader:*
  - pick a source:
    - forward pass, paced: σ appears on each node as the BFS reaches it;
    - backward pass, paced: dependencies flow down the tree, with edge widths showing the amount;
  - "Next source" adds to a running betweenness, shown as node size;
  - the final sizes equal `betweenness`, and a bar chart shows the running total for every node.
- *GUESS:* `everyPaced`, labels, edge widths, `betweenness` to check against.

**`ch08-dijkstra`: Shortest paths with edge lengths (§8.6)** · built
- *Idea:*
  - with lengths, layers no longer work;
  - Dijkstra's algorithm keeps tentative distances, always settles the closest unsettled node, and relaxes its edges;
  - a priority queue (a binary heap) makes it O((m + n) log n).
- *Reader:*
  - a road-like network with lengths drawn as edge labels and widths;
  - step Dijkstra (paced): settled nodes are filled, tentative ones outlined with their distance, and a relaxation that shortens a distance flashes its edge;
  - the priority queue is listed in order;
  - comparing BFS hop counts with Dijkstra distances shows a path with more hops that is shorter;
  - a path drawn on request.
- *GUESS:* `everyPaced`, edge labels, `constantLabelSize`.

**`ch08-maxflow`: Maximum flow by augmenting paths (§8.7)** · built
- *Idea:*
  - repeatedly find a path from source to target in the *residual* network and push flow along it;
  - flow pushed one way frees capacity the other way, so later paths can undo earlier choices;
  - when no path remains, the nodes still reachable from the source give a minimum cut (max-flow/min-cut);
  - node-independent paths come from splitting each node into an in-node and an out-node joined by a unit edge.
- *Reader:*
  - step the algorithm (paced): the augmenting path is found by BFS (highlighted), flow is pushed, and the residual edges (tapered, both directions where both exist) are redrawn;
  - a "bad first path" scenario where a later path cancels flow on an edge;
  - the final cut shown as hulls around the two sides;
  - a "Split nodes" tab that redraws a network with each node as an in/out pair and runs the same algorithm to count node-independent paths.
- *GUESS:* `everyPaced`, `arc` edges (to separate a→b from b→a), tapered directed edges, `encircle`.

### Gaps found in batch 5 (added: `linkTo(element)`, Markdown chips that highlight and select their node or edge; the others needed nothing new: node labels can carry two numbers, Python timing works in Pyodide, and residual edges use `arc` plus tapered edges)

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| Showing a data structure (a queue, a heap, a list) beside the graph, with entries linked to their nodes | bfs, dijkstra, storing | Markdown text can list it, but entries aren't linked to nodes | a small `ListView(fn)` widget (or Markdown node links) whose items highlight and select their nodes |
| Two numbers on a node (distance and path count) that stay readable | bfs, betweenness-algorithm | one label per node | either a second label (`sublabel`) or keep using "d=2 · σ=3" labels; check how they read |
| Timing calculations in the browser | complexity | Python `time` works in Pyodide, but slowly and noisily | none; use medians of repeats and say so |
| Residual networks with an edge each way | maxflow | `arc` and tapered edges | probably none; check how it looks |

Also found and fixed while building batch 5:
- A hidden edge no longer bends its visible twin into a curve.
- New node field `strokewidth` (per-node border width) for showing state with outlines.
- The line-chart key now sits above the plot, not over the lines.
- Scatter axes end on round numbers, and a one-point chart gets a proper axis.
- `showMatrix` sorts n2 before n10 and labels rows by node label.
- `center()` leaves room for labels to the right of the rightmost nodes.

Noted, not changed:
- Labels inside nodes fit the node rather than following `constantLabelSize`, so they are small in 30 px nodes.
- In tests, `App.press` matches the first button with that label across tabs, so give buttons distinct labels.

## Batch 6: book pages 275–339 (Chapters 9–10)

Chapter 9 is about how wrong network data can be and what to do about it;
Chapter 10 surveys the structure of real networks, using the measures of
Chapters 6–7 across many datasets. The Chapter 10 explainers compare the
bundled networks side by side.

**`ch09-measurement-error`: Types and sources of error (§§9.1–9.2)** · built
- *Idea:*
  - measured networks have missing edges (false negatives), spurious edges (false positives), missing or merged nodes, and wrong attributes;
  - some measures are robust to this and some are not.
- *Reader:*
  - a true network (left) and its measured version: sliders for the false-negative and false-positive rates;
  - each measurement draws the missed edges as faint dashed lines and the spurious ones in red;
  - a live table compares the true and measured values: mean degree, clustering, mean distance, the size of the largest component and the top hubs;
  - "Simulate" sweeps the error rate and charts how far each measure drifts, showing which are robust.
- *GUESS:* numpy and networkx, `Chart`, dashed and highlighted edges.

**`ch09-em`: Estimating errors from repeated measurements (§9.3)** · built
- *Idea:*
  - measure a network N times; each pair is seen E out of N times;
  - with a true-positive rate α, false-positive rate β and density ρ, the EM algorithm alternates between the probability Q that each edge is real and the best α, β and ρ.
- *Reader:*
  - an invented "who was near whom" study: a hidden true network, N noisy observations (a slider for N), and edge widths showing E;
  - "Run EM" (paced): each iteration recolours edges by Q (red near 0, green near 1) and updates α, β and ρ, with a live chart of the three converging;
  - a confusion table against the truth (real edges kept, spurious edges dropped);
  - "Simulate" sweeps N and charts the reconstruction error;
  - a Q histogram shows the bimodal split.
- *GUESS:* numpy, `everyPaced`, `Chart`, `plotHistogram`.

**`ch09-correcting`: Link prediction and node disambiguation (§9.4)** · built
- *Idea:*
  - missing edges can be guessed from structure (shared neighbours and similar scores), and tested by hiding edges and seeing whether they come back;
  - nodes can be wrongly merged (two "J. Smith"s become one hub) or wrongly split, and a node's neighbourhood helps tell them apart.
- *Reader:*
  - **Link prediction tab:**
    - "Hide 10% of edges", then predict with a method dropdown (`predictLinks`);
    - true predictions are green and false ones red, the hidden edges that were missed are dashed;
    - precision and AUC (`evaluateLinks`) with a chart across methods.
  - **Disambiguation tab:**
    - an invented coauthorship network where several authors share a name, merged as the raw data would have them;
    - the merged nodes are big false hubs and create shortcuts (the mean distance shrinks);
    - "Split by neighbourhood" clusters each name's papers by shared coauthors and splits the node, and the statistics recover.
- *GUESS:* `predictLinks`, `evaluateLinks`, `similarTo`, `linkTo` chips for candidates.

**`ch10-components`: Components and the bow tie (§10.1)** · built
- *Idea:*
  - most networks have one large component and many small ones;
  - in directed networks the large weak component splits into a strongly connected core with an in-component and an out-component (the "bow tie"), plus tendrils and tubes.
- *Reader:*
  - a table across the bundled networks: n, the share in the largest component, the number of components;
  - pick one to see it packed by component (`binPackLayout` + `noverlapLayout`);
  - a directed tab draws the bow tie as three columns (in, core, out) with tendrils, sized by count;
  - click a node to see its own in- and out-components.
- *Data:* the bundled networks, plus a directed web-like network (political blogs, from the public network data page, if added).
- *GUESS:* components, `strongcomponent`, `ancestors`/`descendants`, a bow-tie decomposition (see gaps).

**`ch10-small-world`: Shortest paths and the small-world effect (§10.2)** · built
- *Idea:*
  - mean distances are small (often under 10, even for millions of nodes) and grow like log n;
  - the diameter is larger but still small.
- *Reader:*
  - pick a network and a node: distance rings from it (`heatMap`), and a live chart of how many nodes are at each distance;
  - "Simulate": the distance distribution averaged over many sources;
  - a scatter of mean distance against log n across the bundled networks and growing random networks, with ln n / ln c as a guide line;
  - a "six degrees" game: click two nodes and guess their distance before it is shown.
- *GUESS:* `heatMap`, BFS, `plotScatter`, `plotLine`.

**`ch10-degree-distributions`: Degree distributions and power laws (§§10.3–10.4.1)** · built
- *Idea:*
  - degree distributions are right-skewed with hubs;
  - a power law p(k) ∝ k^−α is a straight line on log–log axes;
  - plain histograms are noisy in the tail, so use logarithmic bins or the cumulative distribution;
  - estimate α by maximum likelihood, not by fitting a line.
- *Reader:*
  - choose a network and a view: linear histogram, log–log histogram, log bins, or cumulative (`plotFrequency(cumulative=true)`);
  - a k_min slider fits α by maximum likelihood and draws the fitted line on the cumulative plot, with α ± σ;
  - the hubs are highlighted in the graph when you point at the tail;
  - the Internet and the power grid side by side (heavy tail against none).
- *GUESS:* `plotFrequency`, `plotHistogram(log=true)`, a power-law fit (see gaps).

**`ch10-power-law-properties`: Properties of power laws (§10.4.2)** · built
- *Idea:*
  - for α ≤ 3 the second moment ⟨k²⟩ diverges, so in practice it is dominated by the largest values and keeps growing with sample size;
  - power laws are top-heavy: a small share of nodes holds a large share of the edges (the "80/20 rule").
- *Reader:*
  - an α slider and "Draw a sample" (paced, growing sample sizes): live charts of the sample mean and of ⟨k²⟩ against sample size, one settling and one not for α < 3;
  - a top-heavy chart, W (share of edge ends held) against P (share of nodes, largest first), for real networks and for samples;
  - in the graph, the top P% of nodes are highlighted as you drag a slider, with their share of edges.
- *GUESS:* `plotLine`, random sampling in Python, `Chart`.

**`ch10-centrality-clustering-mixing`: Centralities, clustering and mixing across networks (§§10.5–10.7)** · built
- *Idea:*
  - eigenvector and betweenness centrality are right-skewed too;
  - real networks have much more clustering than chance would give for social networks, about as much for technological ones;
  - local clustering falls with degree;
  - social networks are assortative by degree, and technological and biological ones are disassortative.
- *Reader:*
  - a comparison table across the bundled networks: C, the configuration-model expectation (⟨k²⟩ − ⟨k⟩)² / n⟨k⟩³, and r;
  - pick one to see the cumulative distributions of eigenvector centrality and betweenness, and C(k) against k (`plotScatter`);
  - a scatter of r across networks by kind.
  - This links back to the Chapter 7 explainers for the definitions.
- *GUESS:* `plotScatter`, `plotFrequency`, `assortativity`, `clustering`.

### Gaps in batch 6 (added before building: `bowTie()`, `fitPowerLaw(field or list, kmin=)` with the Kolmogorov–Smirnov choice of k_min, `plotFrequency(fit=true)`, dashed chart series; data: `polblogs-sample.gdf` (600 blogs, seed 1, bow tie intact) and `degree-sequences.csv` (network,degree,count for the whole Internet AS graph, US power grid and political blogs))

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| Bow-tie decomposition of a directed network | ch10-components | `strongcomponent` and `ancestors`/`descendants` give the pieces by hand | `bowTie()`: a node field `bowtie` = core / in / out / tendril / tube / other, and the sizes |
| Power-law fit with k_min and its uncertainty | ch10-degree-distributions, power-law-properties | none | `fitPowerLaw(field, kmin=None)`: α by maximum likelihood (with the discrete ½ correction), σ, and k_min chosen by the Kolmogorov–Smirnov method when not given; a `fit=` line on `plotFrequency(cumulative=true)` |
| A directed web-like network with a real bow tie | ch10-components | the bundled directed networks are a worm brain (one big SCC) and a citation DAG (no core) | add political blogs (Adamic and Glance) from the public network data page |
| A function on a cumulative plot (fitted line) | ch10-degree-distributions | `plotLine` can draw it as a second series | probably none |

Found and fixed while building batch 6:
- `constantLabelSize` and `directedEdges` are now session-wide; switching graphs with `use()` used to reset them.
- Chart changes:
  - `plotLine(yrange=, xrange=, dashed=[...])` and `plotScatter(xrange=, yrange=)`, with points outside a fixed range clipped;
  - a y-axis label on every line chart;
  - round numbers at the top of line-chart y axes;
  - a key for multi-series scatter plots.

Noted, not changed:
- `fitPowerLaw` picks k_min by the KS distance alone, which can't tell a power-law tail from an exponential one. `ch10-degree-distributions` adds a likelihood-ratio comparison of its own, which could move into the command.
- `predictLinks` and `evaluateLinks` need igraph, so `ch09-correcting` scores the pairs in plain Python.
- networkx's `eigenvector_centrality_numpy` needs scipy, which isn't installed, so use numpy's `eigh`.
- Highlighted nodes on the dark theme should use bright fills with dark outlines; a black fill reads as a hollow ring.

## Batch 7: book pages 340–400 (Part III, *Network models*: Chapter 11 and Chapter 12.1–12.9)

Models of networks: random graphs with Poisson degrees, then the
configuration model with any degrees. The generating-function sections
(§12.10 on) are batch 8. Each explainer sets theory and simulation side by
side: the formula's curve with a "Simulate" button that adds measured points.

**`ch11-random-graph`: G(n, p) and G(n, m) (§§11.1–11.4)** · built
- *Idea:*
  - every pair is joined independently with probability p;
  - the mean degree is c = (n − 1)p and the degree distribution is Poisson for large n;
  - clustering is C = c/(n − 1), which vanishes for large networks, unlike real ones.
- *Reader:*
  - "Add edges one at a time": the n nodes are placed once (the final layout), and edges appear in random order, paced, each new one highlighted;
  - a c slider; a live chart of the degree distribution against the Poisson and binomial formulas;
  - a table of C measured against c/(n − 1) next to a real network of the same n and m;
  - "Simulate" averages over many graphs.
- *GUESS:* `makeErdosRenyiRandom` or networkx, `revealUpTo` (edges given a `born` step), `plotLine`.

**`ch11-giant-component`: The giant component (§11.5)** · built
- *Idea:*
  - below c = 1 all components are small; above it a giant component of size S = 1 − e^{−cS} appears;
  - S is found by solving that equation (graphically: where the curve meets the line).
- *Reader:*
  - drag c through 1 and watch the largest component (hull, coloured) appear;
  - a live chart of S against c: theory curve, simulated points ("Simulate" sweeps c at two sizes of n, so the transition sharpens);
  - a cobweb plot of the fixed-point iteration S ← 1 − e^{−cS}, stepped (paced);
  - why there can't be two giant components (join them with probability ~1).
- *GUESS:* networkx, `encircle`, `plotLine`, `everyPaced`.

**`ch11-small-components`: Small components (§11.6)** · built
- *Idea:*
  - the small components are trees (almost surely);
  - their size distribution π_s is known exactly;
  - the mean size of the component a node belongs to is ⟨s⟩ = 1/(1 − c + cS), which diverges at c = 1.
- *Reader:*
  - the small components packed beside the giant one (`binPackLayout` + `noverlapLayout`), with trees confirmed (cycles would be flagged red);
  - a chart of π_s from simulation against the formula;
  - ⟨s⟩ against c with its spike at 1;
  - click a small component to see its size and that it has s − 1 edges.
- *GUESS:* networkx components, `binPackLayout`, `noverlapLayout`, `plotLine`.

**`ch11-path-lengths`: Path lengths, and what random graphs get wrong (§§11.7–11.8)** · built
- *Idea:*
  - the number of nodes s steps away grows like c^s, so the diameter is about ln n / ln c (small world);
  - but random graphs lack the clustering, skewed degrees and community structure of real networks.
- *Reader:*
  - click a node to see the rings at distance 1, 2, 3, … with counts against c^s (paced ball growth);
  - "Simulate" plots the mean distance against n (log axis), with the ln n / ln c line;
  - a side-by-side table: a real network and G(n, p) with the same n and m (C, degree spread, r, mean distance), and their degree distributions overlaid.
- *GUESS:* BFS, `heatMap`, `plotLine`, `plotScatter`.

**`ch12-configuration-model`: The configuration model (§12.1)** · built
- *Idea:*
  - give each node k_i "stubs" (half-edges) and pair stubs uniformly at random;
  - every matching is equally likely; there are some self-loops and multi-edges, but few in large sparse networks;
  - the chance of an edge between i and j is about k_i k_j / 2m;
  - the "expected degree" (Chung–Lu) variant joins pairs independently with that probability.
- *Reader:*
  - stubs drawn as short spokes on each node, paired up one pair at a time (paced), each new edge highlighted, self-loops and multi-edges flagged in red;
  - choose the degree sequence from a real network or a slider;
  - a chart of measured edge frequency between pairs against k_i k_j / 2m over many runs ("Simulate");
  - self-loop and multi-edge counts against their expected values as n grows.
- *GUESS:* stubs as `drawLine` spokes, `everyPaced`, a configuration-model generator (see gaps).

**`ch12-excess-degree`: Excess degree and the friendship paradox (§§12.2–12.5)** · built
- *Idea:*
  - following an edge, you reach a node with probability proportional to its degree, so your friends have more friends than you do on average;
  - the excess degree distribution is q_k = (k + 1)p_{k+1}/⟨k⟩;
  - the clustering is (⟨k²⟩ − ⟨k⟩)² / n⟨k⟩³;
  - the network is locally tree-like, and the mean number of second neighbours is ⟨k²⟩ − ⟨k⟩.
- *Reader:*
  - "Pick a random edge end" (paced): the node reached is outlined, and a live chart builds the degree distribution of reached nodes against p_k and the formula;
  - a "friendship paradox" table for real networks (the share of nodes with fewer friends than their friends' average);
  - second neighbours counted in the graph against the formula.
- *GUESS:* `plotLine`, `linkTo`, `everyPaced`.

**`ch12-giant-component`: The giant component in the configuration model (§§12.6–12.9)** · built
- *Idea:*
  - there is a giant component when ⟨k²⟩ − 2⟨k⟩ > 0 (Molloy–Reed);
  - its size comes from u = g₁(u) and S = 1 − g₀(u);
  - with power-law degrees and α < 3 there is always a giant component;
  - the diameter is still about ln n.
- *Reader:*
  - the worked example: nodes of degree 1 and 3, with a slider for the share of degree-3 nodes; the giant component appears when it passes the threshold;
  - a theory curve against simulation;
  - the u = g₁(u) cobweb (paced);
  - a power-law tab: lower α and see the giant component stay;
  - a diameter chart against n.
- *GUESS:* the configuration-model generator, `plotLine`, `encircle`.

### Gaps in batch 7 (added before building: `makeConfigurationModel(degrees or field, simple=, seed=)` with its own stub matching, a `stubs` field and self-loop and repeated-edge counts; `makeExpectedDegree(weights)`; GUESS `degree` counts a self-loop once, while the book counts it twice)

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| Configuration model from a degree sequence, keeping self-loops and multi-edges (or not) | ch12-configuration-model, ch12-giant-component, ch11-path-lengths | none (networkx `configuration_model` works from code) | `makeConfigurationModel(degrees, simple=False, seed=0)` (degrees: a list, or a field to copy from the current graph); the field `stubs` on nodes |
| Expected-degree (Chung–Lu) random graphs | ch12-configuration-model | none | `makeExpectedDegree(weights, seed=0)` |
| Self-loops and multi-edges drawn visibly | ch12-configuration-model | self-loops are drawn; multi-edges curve apart | check how it looks with many |
| Edge-by-edge growth on fixed nodes | ch11-random-graph | `revealUpTo` reveals nodes; edges with a `born` field are revealed too | none |

Notes from building batch 7:
- **Book check:** the expected number of pairs of parallel edges in the configuration model is ¼[(⟨k²⟩ − ⟨k⟩)/⟨k⟩]² for large n, half of eq. (12.3), whose sum counts each pair in both orders. Simulation agrees with the exact sum Σ_{i<j} k_i(k_i−1)k_j(k_j−1) / 2(2m−1)(2m−3). `ch12-configuration-model` explains the difference.
- **Fixed in GUESS:**
  - live Markdown and Labels in tabs that aren't showing are no longer recomputed after every command; they refresh when their tab is selected;
  - `makeConfigurationModel` and `makeExpectedDegree` take `layout=False`;
  - `fromNetworkX` without positions falls back to GUESS's `frLayout` when networkx's spring layout fails (it needs scipy for more than 500 nodes, and the browser has no scipy), instead of leaving random positions.
- **Browser-only pitfalls:**
  - `np.repeat` with 64-bit counts fails in Pyodide (cast to `np.intp`);
  - `frLayout` differs between the browser and native runs, so screenshots aren't reproducible.
- **Also fixed:** `plotLine(highlight=[names])` draws those series with large markers, so a one-point "this network" series stands out among simulated points.

## Batch 8: book pages 401–458 (Chapter 12.10–12.11 and Chapter 13.1–13.3)

The mathematics behind the configuration model (generating functions),
other random-graph models, and the first models of how networks grow:
Price's model of citations and the Barabási–Albert model. The growth models
follow the "growing networks" convention: build the final network, lay it out
once, then reveal it in arrival order.

**`ch12-generating-functions`: Generating functions (§§12.10.1–12.10.7)** · built
- *Idea:*
  - a degree distribution can be packed into a function g₀(z) = Σ p_k z^k;
  - moments come from its derivatives at z = 1;
  - adding independent quantities multiplies their generating functions;
  - g₁(z) = g₀′(z)/g₀′(1) is the excess-degree distribution;
  - second neighbours come from g₀(g₁(z)).
- *Reader:*
  - choose a distribution (Poisson, exponential, power law, or a real network's);
  - see p_k as bars and g₀(z) and g₁(z) as curves on [0, 1], with the slope at 1 marked as ⟨k⟩;
  - "Add two" convolves p_k with itself, shown against the product g₀(z)²;
  - a sampling check: draw a node's neighbours' excess degrees in a real network and compare with g₁.
- *GUESS:* numpy, `plotLine(dashed=)`, `Chart`.

**`ch12-small-component-sizes`: Small components from generating functions (§§12.10.8–12.10.9)** · built
- *Idea:*
  - the size of the small component reached along an edge satisfies h₁(z) = z g₁(h₁(z)), and h₀(z) = z g₀(h₁(z));
  - iterating gives the whole size distribution π_s;
  - the mean size is 1 + g₀′(1)/(1 − g₁′(1)), which diverges at the transition.
- *Reader:*
  - the iteration h₁ ← z g₁(h₁) stepped (paced), with the curve converging;
  - the predicted π_s as a dashed line against simulated small components (packed beside the giant one);
  - a slider for the mean degree, showing the divergence near the transition.
- *GUESS:* numpy, `makeConfigurationModel`, `binPackLayout` + `noverlapLayout`, `plotLine`.

**`ch12-other-models`: Directed, bipartite and community random graphs (§§12.11.1–12.11.6)** · built
- *Idea:*
  - the configuration model generalises:
    - directed: in- and out-stubs paired;
    - bipartite: stubs of two kinds;
    - acyclic: edges point down a fixed order;
    - degree-correlated;
    - clustered: triangle "stubs";
    - with communities: the stochastic block model.
- *Reader:* one tab per variant, each with its generator, a picture and the property it adds.
  - **Directed:** the bow tie appears.
  - **Bipartite:** its projection is full of cliques.
  - **Clustered:** C stays high as n grows.
  - **Communities:** sliders for p_in and p_out, with the block structure visible in `showMatrix(order=block)` and found again by `louvainClusters`.
- *GUESS:* networkx generators, `showMatrix`, `bowTie`, a stochastic block model generator (see gaps).

**`ch12-small-world-model`: The small-world model (§§12.11.7–12.11.8)** · built
- *Idea:*
  - a ring lattice has high clustering and long paths;
  - rewiring a small fraction p of edges as random shortcuts collapses the path lengths while the clustering stays high;
  - so real networks can have both.
- *Reader:*
  - a p slider (on a log scale) redraws the ring with shortcuts highlighted;
  - "Rewire one by one" (paced): each shortcut flashes and the mean distance drops live;
  - "Simulate": the classic C(p)/C(0) and L(p)/L(0) curves on a log p axis;
  - a note on dynamic networks (§12.11.7).
- *GUESS:* `makeWattsStrogatz`, `everyPaced`, `plotLine(logX=)`.

**`ch13-price-model`: Price's model of citations (§13.1)** · built
- *Idea:*
  - new papers cite c earlier papers, chosen in proportion to (in-degree + a);
  - the in-degree distribution becomes a power law with α = 2 + a/c;
  - the simulation trick: with probability c/(c + a) copy a citation from a random paper, otherwise pick uniformly.
- *Reader:*
  - the network is built first and revealed paper by paper (paced), each new paper's citations highlighted;
  - nodes are sized by in-degree and coloured by arrival time;
  - sliders for c and a with a live cumulative in-degree chart and its fitted α against 2 + a/c (`fitPowerLaw`);
  - "Simulate" sweeps a.
- *GUESS:* `revealUpTo`, `fitPowerLaw`, `plotFrequency(fit=true)`, a Price-model generator that records the step each node arrives (see gaps).

**`ch13-barabasi-albert`: The Barabási–Albert model (§13.2)** · built
- *Idea:*
  - undirected growth with each new node attaching to m existing nodes in proportion to degree: α = 3;
  - without the preference (uniform attachment) the distribution is exponential.
- *Reader:*
  - growth revealed node by node, with the new node's links flowing;
  - side by side: preferential against uniform attachment, with their degree distributions charted live (log–log and log-linear);
  - the fitted α.
- *GUESS:* `makeBarabasiAlbertRandom` (with a `born` field), `revealUpTo`, `fitPowerLaw`.

**`ch13-first-mover`: Time evolution and the first-mover advantage (§13.3)** · built
- *Idea:*
  - in these models the oldest nodes end up with the highest degrees: the expected degree falls with arrival time, and a node's degree grows like a power of time;
  - early arrival matters more than anything else.
- *Reader:*
  - colour by arrival time and size by degree;
  - a scatter of degree against arrival time with the theoretical curve;
  - pick any node to follow its degree over time (paced re-growth, with the node highlighted);
  - real data: citations by year in `vis-papers.gdf` against the model.
- *GUESS:* `plotScatter(line=)`, `revealUpTo`.

### Gaps in batch 8 (added before building: `makePriceModel(n, c, a)` with Newman's copying method; a `born` field (arrival step on nodes and edges) from `makePriceModel`, `makeBarabasiAlbertRandom` and `makeBarabasiAlbertAging`; `makeBlockModel(sizes, p_in, p_out or matrix)` with a `block` field)

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| Growth generators that record when each node arrived | ch13-price-model, ch13-barabasi-albert, ch13-first-mover | `makeBarabasiAlbertRandom` doesn't record arrival order; there is no Price model | `makePriceModel(n, c, a=1, seed=0)` (directed) and a `born` field from `makeBarabasiAlbertRandom` (and the aging variant) |
| Stochastic block model | ch12-other-models | none (networkx `stochastic_block_model` works from code) | `makeBlockModel(sizes, p_in, p_out, seed=0)` with a node field `block` |
| Clustered random graphs (triangle stubs) | ch12-other-models | none | build it in the explainer (or `makeClusteredRandom`) |

Notes from building batch 8:
- **Price's model is a power law in k + a, not k:** fitting k directly reads low (2.19 against 2.33 at a = 1). Added `fitPowerLaw(shift=a)` and `plotFrequency(fit=true, shift=a)`.
- **Barabási–Albert fits:** fits from the smallest k_min come out under 3, because the exact m(m+1)/k(k+1) form bends at small k. `ch13-barabasi-albert` explains this.
- **First-mover data:** `vis-papers.gdf`'s global `cites` count shows no first-mover pattern (the set is chosen by citations within each search phrase). Citations from inside the set do show it, and `ch13-first-mover` uses them.
- **Community detection:** Louvain loses planted groups somewhat above the theoretical detectability limit, which is what belief propagation reaches. `ch12-other-models` says so.
- **Fixed in GUESS:**
  - slider readouts round to the slider's step;
  - test helper `App.tab(title)`.
- **Tooling:** temporary Playwright configs can live in the scratchpad if `web/node_modules` is symlinked beside them.

## Batch 9: book pages 459–514 (Chapter 13.4–13.6 and Part IV, Chapter 14.1–14.2)

The end of Part III (variations on growth models, and networks designed by
optimisation), then Part IV, *Applications*, opening with community
detection by modularity. The growth models replay their growth in place
(`born` + `revealUpTo`).

**`ch13-growth-variations`: Extra edges and edge removal (§§13.4.1–13.4.2)** · built
- *Idea:*
  - real networks also gain edges between old nodes and lose edges;
  - adding edges between existing nodes (also chosen by degree) and removing random edges changes the exponent, but the tail stays a power law while growth dominates.
- *Reader:*
  - sliders for the extra edges per step and the edge-removal rate;
  - the growth is replayed node by node; new edges between old nodes flash blue, and removed edges fade red and vanish;
  - a live cumulative degree chart with its fitted α against the formula;
  - "Simulate" sweeps the removal rate.
- *GUESS:* a general growth generator (see gaps), `revealUpTo`, `fitPowerLaw`.

**`ch13-nonlinear-attachment`: Non-linear preferential attachment (§13.4.3)** · built
- *Idea:*
  - attachment ∝ k^γ;
  - γ < 1 gives a stretched exponential: no power law;
  - γ = 1 gives the power law;
  - γ > 1 gives condensation: one node ends up attached to nearly everything.
- *Reader:*
  - a γ slider (0.5 to 1.5);
  - the growth is replayed with the biggest hub outlined;
  - the share of edges held by the largest node is charted against n;
  - degree distributions for three γ values side by side.
- *GUESS:* the general growth generator, `revealUpTo`, `plotFrequency`.

**`ch13-node-copying`: Node copying models (§13.5)** · built
- *Idea:*
  - a new node copies the links of a random existing node (each with some probability), plus a few links of its own;
  - this gives a power law without any explicit preference;
  - it is a plausible model for gene duplication in protein networks and for copying links on the web.
- *Reader:*
  - each step picks a node to copy, outlines it, and draws the copied links (purple) and the new random ones (orange), replayed in place;
  - sliders for the copy probability;
  - degree distribution with its fit;
  - a comparison with Price's model at a matching exponent.
- *GUESS:* a copying-model generator (see gaps), `revealUpTo`, `fitPowerLaw`.

**`ch13-optimization-models`: Networks designed for a purpose (§13.6)** · built
- *Idea:*
  - a transport network trades the cost of building edges against travel time;
  - cheap networks are trees, fast ones are meshes, and in between hub-and-spoke designs appear (as in airline networks).
- *Reader:*
  - towns scattered on a map;
  - a slider for the weight on travel time against length;
  - "Optimise" runs simulated annealing (paced): proposed edge additions and removals flash, and accepted ones stay;
  - the cost and travel time are charted live;
  - presets show the tree, hub-and-spoke and mesh regimes.
- *GUESS:* `everyPaced`, `drawLine`, `plotLine`, Dijkstra from networkx.

**`ch14-modularity`: Dividing networks and modularity (§§14.1–14.2.2)** · built
- *Idea:*
  - graph partitioning fixes the number and size of groups; community detection doesn't;
  - modularity Q measures how many more edges fall within groups than chance would give;
  - a simple algorithm moves single nodes between two groups to raise Q (Kernighan–Lin style), keeping the best state.
- *Reader:*
  - the karate club and a planted-partition network;
  - click nodes to move them between groups and watch Q change;
  - "Optimise" moves one node per step (paced), highlighting the moved node and its edges, with Q charted live;
  - the edges between groups are dashed, and the result is compared with the known split.
- *GUESS:* `modularity`, `makeBlockModel`, `everyPaced`, `graphevents.clickNode`.

**`ch14-spectral-modularity`: Spectral modularity maximisation (§§14.2.3–14.2.4)** · built
- *Idea:*
  - modularity is a quadratic form in the modularity matrix B = A − kkᵀ/2m;
  - the signs of its leading eigenvector give a good split;
  - repeating the split on each group gives more groups, while each split raises Q.
- *Reader:*
  - nodes coloured by their value in the leading eigenvector (a diverging scale), and a sorted bar chart of the entries;
  - "Split" divides by sign and "Split again" recurses (paced), stopping when no split raises Q;
  - `showMatrix(order=group)` shows the block structure.
- *GUESS:* numpy, `showMatrix`, `plotLine`.

**`ch14-louvain-resolution`: The Louvain algorithm and the resolution limit (§§14.2.5–14.2.6)** · built
- *Idea:*
  - Louvain moves nodes locally and then merges each community into a single node, repeating; it is fast and good;
  - but modularity has a resolution limit: in a ring of small cliques, maximising Q can merge neighbouring cliques even though each is clearly a community.
- *Reader:*
  - **Louvain tab:** step through it (paced). Phase 1 moves nodes, highlighted with their community colour; phase 2 collapses communities into super-nodes, shown in a second graph. Q is charted at each level.
  - **Resolution tab:**
    - a ring of n cliques (slider) shows what Louvain finds and Q for the "one clique per community" partition against the merged one;
    - a resolution slider (`louvainClusters(resolution=)`) shows communities split as it rises.
- *GUESS:* `louvainClusters(resolution=)`, `modularity`, networkx's Louvain levels (`louvain_partitions`), `subgraph`/`use()` for the collapsed graph.

### Gaps in batch 9 (added before building: `makeGrowingNetwork(n, m, gamma, a, extra=, remove=)` with `born` and `died` (removed edges stay hidden, and `revealUpTo` replays removals); `makeCopyingModel(n, c, copy)` (the book's version; in-degree exponent 1 + 1/copy) with a `copied` field; `modularity(field, resolution=)`)

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| A general growth generator: m edges per new node, attachment ∝ (k + a)^γ, extra edges between old nodes, edge removal | ch13-growth-variations, ch13-nonlinear-attachment | `makeBarabasiAlbertRandom` (γ = 1, no extras), `makePriceModel` | `makeGrowingNetwork(n, m=2, gamma=1, a=1, extra=0, remove=0, seed=0)` with `born` on nodes and edges and a `died` step on removed edges (kept hidden, so the replay can show removals) |
| Node copying model | ch13-node-copying | none | `makeCopyingModel(n, copy=0.5, links=2, seed=0)` with `born` and a `copied` field (the node copied from) |
| `modularity(field, resolution=)` to match Louvain's | ch14-louvain-resolution | `modularity(field)` only | add `resolution=` |

Notes from building batch 9:
- **Book check (worth confirming against the errata):** eq. (13.85), the exponent with extra edges (w per step) and removals (v per step), is printed as α = 2 + (v − w)/(c + 2w − 2v). That gives 2 for plain Barabási–Albert and contradicts eq. (13.70).
  - Solving the master equation (13.77) gives α = 2 + c/(c + 2w − 2v). That is 3 with no extras, reduces to (13.70), and diverges at v = c/2 + w as the text says.
  - An exact numerical solution of (13.77) to k = 200,000 agrees to three decimals. `ch13-growth-variations` uses the corrected form and says why.
- **Fixed in GUESS:**
  - layouts are seeded by default, so `frLayout` and the others give the same result every run, in the browser and natively;
  - `center()` includes self-loops;
  - `makeGrowingNetwork`'s extra edges join only existing nodes.
- **Explainers:** they should still use their own seeded layout where groups must be visibly apart.

## Batch 10: book pages 515–567 (the rest of Chapter 14, *Community structure*)

Community detection beyond modularity: description length, statistical
inference, edge betweenness and hierarchical clustering. Then how to test
the algorithms, and structures other than communities.

**`ch14-infomap`: Communities as codes for random walks (§14.3)** · built
- *Idea:*
  - a random walker stays inside communities for long stretches;
  - naming communities and then nodes within them describes the walk in fewer bits;
  - the map equation's description length is minimised by Infomap.
- *Reader:*
  - a walker moves (paced), its path coloured by community;
  - a live "code" strip writes each step's codeword, with a community-change codeword when it leaves a group;
  - a bar chart compares description lengths for one community, the planted groups, and Infomap's answer;
  - drag nodes between groups to see the code length change.
- *GUESS:* `infomapClusters`, `everyPaced`, a map-equation calculation in Python.

**`ch14-sbm-inference`: Community detection by statistical inference (§14.4)** · built
- *Idea:*
  - fit a stochastic block model by maximum likelihood;
  - the plain SBM tends to split networks into hubs and periphery (the karate club!), so the degree-corrected SBM is needed;
  - the likelihood says how well each partition explains the edges.
- *Reader:*
  - a karate-club tab with "Fit plain SBM" and "Fit degree-corrected SBM", each by paced Monte Carlo node moves (the moved node is highlighted);
  - a live log-likelihood chart;
  - the resulting groups against the real split, with NMI;
  - block-model matrices for each fit.
- *GUESS:* an SBM fitter (see gaps), `showMatrix(order=)`, `compareClusters`.

**`ch14-girvan-newman`: Betweenness-based division (§14.5.1)** · built
- *Idea:*
  - edges between communities carry many shortest paths;
  - removing the highest-betweenness edge repeatedly (and recomputing) breaks the network into its communities;
  - the order of the splits is a dendrogram.
- *Reader:*
  - "Remove the busiest edge" (paced), with each edge's width its betweenness and the removed edge flashing red;
  - new components outlined as they appear;
  - modularity at each level charted live, its peak marked;
  - the dendrogram building up beside it.
- *GUESS:* `edgeBetweennessClusters`, edge `betweenness`, a dendrogram chart (see gaps).

**`ch14-hierarchical-clustering`: Hierarchical clustering (§14.5.2)** · built
- *Idea:*
  - measure how similar each pair of nodes is (e.g. cosine similarity), then merge the most similar groups step by step;
  - single, complete and average linkage give different trees;
  - cutting the tree at a level gives communities.
- *Reader:*
  - a linkage dropdown;
  - merges replayed (paced), with the merged groups' hulls joining;
  - the dendrogram with a draggable cut height, and the graph coloured by the cut;
  - single linkage's "chaining" shown on a network where it fails.
- *GUESS:* `cutDendrogram`, `encircle`, numpy and SciPy-free linkage in Python, a dendrogram chart (see gaps).

**`ch14-measuring-performance`: Testing community detection (§14.6)** · built
- *Idea:*
  - test on real networks with known groups (the karate club), but mostly on artificial benchmarks with planted communities (planted partition, LFR);
  - compare found and planted groups with normalized mutual information;
  - every method fails when the groups are mixed enough.
- *Reader:*
  - a benchmark generator with a mixing slider μ; the planted groups are shown by colour and the found ones by hull;
  - NMI and the method's name live;
  - "Simulate" sweeps μ for Louvain, Infomap, label propagation and walktrap, with NMI curves on one chart (the classic benchmark plot);
  - a table for the karate club.
- *GUESS:* `makeBlockModel`, an LFR generator (see gaps), the clustering commands, `compareClusters`.

**`ch14-other-structure`: Overlapping, hierarchical, core–periphery and ranked structure (§14.7)** · built
- *Idea:* communities aren't the only large-scale structure:
  - groups overlap (link communities);
  - groups nest (hierarchy);
  - a dense core and a sparse periphery;
  - nodes ranked so that edges mostly point one way (stratified networks), or placed in a latent space.
- *Reader:* one tab per kind.
  - **Overlapping:** `linkCommunities` shown with `showOverlaps`.
  - **Hierarchical:** a nested block model, with zoomable hulls.
  - **Core–periphery:** a core–periphery fit, with the block matrix and core nodes in the centre.
  - **Ranking:** nodes placed by an inferred rank (SpringRank-style), with edges coloured by whether they point up or down; and a latent-space layout.
- *GUESS:* `linkCommunities`, `showOverlaps`, `showMatrix`, `orderedLayout`, a core–periphery fit and a ranking (see gaps).

### Gaps in batch 10 (added before building: `showDendrogram(merges, nodes=, heights=, cut=, field=)`, a linked dendrogram chart (it shows the last walktrap or fast-greedy tree with no arguments); `fitBlockModel(k, degreeCorrected=)` (Karrer–Newman likelihood, Kernighan–Lin moves; on karate the plain model groups the hubs together, and the degree-corrected optimum (−739.4) scores above the true club split (−743.2)); `makeLFR(n, tau1, tau2, mu)` (retries seeds); `corePeriphery()` (Borgatti–Everett); `rankNodes()` (SpringRank))

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| A dendrogram chart, linked to the graph | ch14-girvan-newman, ch14-hierarchical-clustering | `cutDendrogram` re-cuts walktrap and fast-greedy trees, but nothing draws them | `showDendrogram()` for the last hierarchical clustering (and from a merge list), with leaves linked to nodes, subtrees highlighting their members, and a click or drag to cut |
| Fitting a stochastic block model (plain and degree-corrected) | ch14-sbm-inference, ch14-other-structure | `blockmodel` finds structural-equivalence positions, which is not SBM inference | `fitBlockModel(k, degreeCorrected=True, sweeps=, seed=)`: Monte Carlo maximum likelihood, field `sbm_class`, returning the log-likelihood |
| LFR benchmark networks | ch14-measuring-performance | `makeBlockModel` (planted partition) only | `makeLFR(n, tau1, tau2, mu, ...)` via networkx, with a `community` field |
| Core–periphery and ranking | ch14-other-structure | none | `corePeriphery()` (a two-block fit with a `core` field) and `rankNodes()` (SpringRank-style, field `rank`) |

Notes from building batch 10:
- **`showDendrogram`:**
  - `paint=true` colours the nodes to match the tree's groups;
  - groups of one node are grey in both chart and graph;
  - tied group sizes are ordered by smallest node index, so colours are predictable;
  - the "N groups" label sits at the left.
- **networkx's random generators** (e.g. `planted_partition_graph`) give different graphs for the same seed in the browser and natively (different networkx versions). GUESS's own generators (`makeBlockModel`, `makeConfigurationModel`, `makeLFR`'s seed handling aside) are reproducible, so prefer them.
- **`labelPropagationClusters`, `infomapClusters` and `walktrapClusters` need igraph,** which loads in the background in the browser. Explainers skip them with a note until it's ready, or use networkx equivalents.
- **On the karate club,** the degree-corrected block-model optimum (−739.4) beats the true split (−743.2) and misplaces nodes 8 and 9. The explainers say so.

## Batch 11: book pages 568–624 (Chapter 15, *Percolation and network resilience*, and Chapter 16.1–16.2)

What happens when nodes fail or are attacked (percolation), then the
standard models of epidemics, first fully mixed and then on networks. The
spreading processes highlight the edges that carry each transmission, run
slow-fast-slow, and chart the epidemic curve live.

**`ch15-random-failure`: Percolation and random failure (§§15.1–15.2)** · built
- *Idea:*
  - keep each node with occupation probability φ;
  - the giant component survives above a threshold φ_c = 1/(g₁′(1)) and vanishes below it;
  - in the configuration model S(φ) follows from u = 1 − φ + φ g₁(u);
  - networks with heavy-tailed degrees have φ_c → 0: they are very robust to random failure.
- *Reader:*
  - a φ slider removes nodes from a fixed drawing (removed ones fade, kept ones keep their place), with the giant component outlined;
  - "Fail nodes one by one" (paced), each failure flashing red;
  - theory S(φ) dashed against simulated points ("Simulate");
  - Poisson against power-law networks.
- *GUESS:* `makeConfigurationModel`, `robustness`, `plotLine(dashed=)`.

**`ch15-targeted-attack`: Removing the hubs (§15.3)** · built
- *Idea:*
  - remove the highest-degree nodes first and the giant component collapses after a few per cent: robust yet fragile;
  - the threshold comes from the same equations with a cut-off degree;
  - acquaintance immunisation (vaccinate a random neighbour of a random person) finds hubs without knowing the network.
- *Reader:*
  - an attack replayed hub by hub (paced), the removed hub and its edges flashing;
  - random failure and attack curves on one chart, for a power-law network, the Internet sample and the power grid;
  - an acquaintance-immunisation tab where random people point to a friend and that friend is immunised, with the degree of those chosen against random choice.
- *GUESS:* `robustness(orders=)`, `plotLine`, `everyPaced`.

**`ch15-percolation-algorithms`: Percolation on real networks, computed fast (§§15.4–15.5)** · built
- *Idea:*
  - the Newman–Ziff algorithm adds nodes back one at a time in random order, merging clusters with union-find, so one pass gives the whole curve S(φ) for every φ;
  - this gives curves for real networks without equations.
- *Reader:*
  - nodes are restored one at a time (paced; nodes stay in place, and the merged clusters' hulls join), with the union-find "pointer to root" drawn for the newest node;
  - a live chart of the largest cluster against the number of nodes added;
  - bond percolation (edges instead of nodes) as a toggle;
  - "Real networks" runs the algorithm on the bundled networks for random and degree-ordered removal and compares the curves.
- *GUESS:* a Newman–Ziff command (see gaps), `revealUpTo` (each node's `born` = its turn), `encircle`.

**`ch16-si-sir`: The SI and SIR models (§§16.1.1–16.1.4)** · built
- *Idea:*
  - in a fully mixed population, SI grows logistically;
  - SIR adds recovery;
  - the basic reproduction number R₀ = β/γ decides whether an outbreak takes off;
  - the final size solves S = 1 − e^{−R₀S}.
- *Reader:*
  - a population drawn as dots in a grid; each step a few random contacts flash as lines between the people they join, and infections spread along them (paced);
  - live S, I and R curves against the solved equations (dashed);
  - sliders for β and γ, with R₀ shown;
  - "Simulate" sweeps R₀ and charts the final size against the theory.
- *GUESS:* numpy ODE stepping, `everyPaced`, `drawLine` for contacts, `plotLine(dashed=)`.

**`ch16-sis-sirs`: SIS, SIRS and other models (§§16.1.5–16.1.7)** · built
- *Idea:*
  - without lasting immunity (SIS) the infection settles at an endemic level 1 − 1/R₀;
  - with waning immunity (SIRS) it can oscillate;
  - other models add a latent stage (SEIR) and more.
- *Reader:*
  - a model dropdown (SIS, SIRS, SEIR) on the same dots-and-contacts picture;
  - live curves with their steady states dashed;
  - an R₀ slider showing the threshold;
  - a phase-plane chart (S against I) for SIRS spiralling in.
- *GUESS:* `plotLine`, `everyPaced`.

**`ch16-complex-contagion`: Two diseases, and complex contagion (§§16.1.8–16.1.9)** · built
- *Idea:*
  - two diseases can help each other (co-infection), giving explosive outbreaks;
  - ideas and behaviours often need several contacts before they are adopted (complex contagion);
  - clustered networks then spread them better than random ones, the reverse of simple contagion.
- *Reader:*
  - a cooperative-diseases tab with two colours, co-infected nodes outlined, and the sudden jump in outbreak size as transmission rises;
  - a complex-contagion tab on a clustered lattice against the same lattice rewired, with a threshold slider: adoption spreads (paced, the adopting node's infected neighbours' edges highlighted) on the lattice and stalls on the rewired network.
- *GUESS:* `spread(model="threshold")`, `makeWattsStrogatz`, `everyPaced`.

**`ch16-epidemics-on-networks`: Epidemic models on networks (§16.2)** · built
- *Idea:*
  - on a network, infection travels only along edges;
  - hubs get infected early and spread widely;
  - the outbreak depends on the network's structure as well as β and γ.
- *Reader:*
  - SIR on a contact network (paced), with each transmission's edge flashing, infected nodes enlarged and outlined, and recovered ones greyed;
  - live S, I and R curves against the fully mixed prediction with the same mean degree;
  - a degree-of-the-infected-over-time chart showing hubs first;
  - networks: random, power-law, the school contacts.
- *GUESS:* `spread(model="SIR")` (with its timeline), or the explainer's own step function, and `everyPaced`.

### Gaps in batch 11 (added before building: `percolation(order, bond=, trials=)`, Newman–Ziff with union-find (site or bond; random, degree or field order; matches S = φs with s = 1 − e^{−cφs}); `spread` and `outbreaks` with SIS, SIRS (`waning=`) and SEIR (`sigma=`; its counts carry `.exposed`))

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| Newman–Ziff percolation: the whole S(φ) curve in one pass, for site or bond percolation, random or ordered | ch15-percolation-algorithms, ch15-random-failure | `robustness` recomputes components at each removal share | `percolation(order="random", bond=False, trials=1, show=True)` → [(φ, S)], with union-find; `robustness` could use it |
| SIS, SIRS and SEIR on networks | ch16-sis-sirs, ch16-epidemics-on-networks | `spread` has SI, SIR, cascade and threshold | add `model="SIS"`, `"SIRS"` (`waning=`) and `"SEIR"` (`sigma=`) to `spread` |
| Fully mixed compartmental curves | ch16-si-sir, ch16-sis-sirs | none (numpy is enough) | probably none; the explainers integrate the equations |

Notes from building batch 11:
- **Fixed a bug from batch 7's hidden-tab change:** widgets on hidden tabs stopped getting plain updates (a button's text, a slider's value), so they came back stale. Now plain updates are always sent, and only live text and charts wait for their tab.
- **Everything random is reproducible now:**
  - the older generators (`makeErdosRenyiRandom`, `makeSimpleRandom`, `makeBarabasiAlbertRandom`, …) take `seed=` (default 0; `seed=None` for a new graph each time);
  - nodes without positions start at a spot fixed by their name (`scatter_position`) instead of a random one, so file loads and generators lay out the same way in the browser and natively.
- **`plotLine(colors=)`:** give a theory curve its data's colour (used in `ch16-si-sir` and `ch16-sis-sirs`).
- **Simulation detail:** with one contact per step, a fully mixed SIS run sits about 10% below 1 − 1/R₀, because several infected people hit the same person. `ch16-sis-sirs` uses five sub-steps per step to match the differential equations.

## Batch 12: book pages 625–674 (the rest of Chapter 16, *Epidemics on networks*)

How big an outbreak gets (it maps onto percolation), what happens with two
diseases, and how epidemics unfold in time on networks, compared with the
pair and degree-based approximations. Every simulation shows its
transmissions on the edges, runs slow-fast-slow, and charts the theory dashed.

**`ch16-outbreak-percolation`: Outbreak sizes and percolation (§§16.3.1–16.3.2)** · built
- *Idea:*
  - in the SIR model each edge transmits at most once, with probability T (the transmissibility), so the final outbreak is a cluster of bond percolation with occupation probability T;
  - large outbreaks happen only above T_c = ⟨k⟩/(⟨k²⟩ − ⟨k⟩), and their size is the giant cluster's;
  - below T_c, outbreaks are small, and above it they are either small or large (bimodal).
- *Reader:*
  - "Flip every edge's coin first": the occupied edges are drawn and the cluster around the first case lights up, which is exactly where the outbreak goes;
  - then run the same outbreak (paced) to show it matches;
  - a T slider;
  - "Simulate": the outbreak-size histogram at a few T values (bimodal above T_c), and the large-outbreak size and probability against T with the configuration-model theory dashed;
  - Poisson against heavy-tailed degrees (T_c near 0).
- *GUESS:* `percolation(bond=true)`, `outbreaks`, `makeConfigurationModel`, a fixed infectious period (see gaps).

**`ch16-two-diseases`: Coexisting diseases and coinfection (§§16.3.3–16.3.5)** · built
- *Idea:*
  - with cross-immunity, a second disease can spread only on the network the first one left (the residual network), so it may fail even with a high T;
  - with coinfection (one disease helps the other) the transition becomes discontinuous;
  - complex contagion's analysis via the same percolation picture.
- *Reader:*
  - **Cross-immunity tab:** disease 1 runs, its survivors stay highlighted, then disease 2 runs on the residual network (paced). A chart of disease 2's size against T₂, with and without disease 1.
  - **Coinfection tab:** a sweep shows the jump.
  - Builds on `ch16-complex-contagion` from batch 11, without repeating it.
- *GUESS:* `spread` with `immune=`, `outbreaks`, `plotLine(dashed=)`.

**`ch16-si-in-time`: The SI model in time (§§16.4–16.5)** · built
- *Idea:*
  - on a network the SI epidemic grows at first like e^{βκ₁t}, set by the leading eigenvalue of A, not like e^{β⟨k⟩t};
  - the order in which nodes are infected follows eigenvector centrality;
  - the pair approximation and the degree-based approximation predict the curve, the latter much better on heterogeneous networks.
- *Reader:*
  - SI from one seed (paced), with each infection's edge flashing and infected nodes sized by infection time;
  - live charts: the infected fraction against the fully mixed, pair and degree-based predictions (dashed);
  - a scatter of infection time against eigenvector centrality (`plotScatter`);
  - networks: random, power-law and the political blogs.
- *GUESS:* `spread(model="SI")`, numpy ODEs, eigenvector centrality.

**`ch16-sir-sis-in-time`: SIR and SIS in time (§§16.6–16.7)** · built
- *Idea:*
  - the degree-based approximation for SIR gives the epidemic curve and the threshold;
  - for SIS it gives an endemic state where each degree class has its own prevalence (hubs are almost always infected), and on heavy-tailed networks the threshold vanishes.
- *Reader:*
  - a model toggle;
  - a live simulation with nodes coloured by state and edges flashing;
  - curves against the degree-based solution (dashed);
  - for SIS, a chart of endemic prevalence against degree (scatter of time spent infected against degree, against the formula);
  - "Simulate" sweeps β to show the threshold for Poisson against power-law degrees.
- *GUESS:* `spread(model="SIR"|"SIS")`, numpy ODEs, `plotScatter`, `plotLine(dashed=)`.

### Gaps in batch 12 (added before building: `spread`/`outbreaks(duration=k)`, a fixed infectious period (SIR is then exactly bond percolation with T = 1 − (1 − β)^k); the node field `infected_steps`; the degree-based ODEs are left to the explainers)

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| A fixed infectious period, so SIR maps exactly onto bond percolation | ch16-outbreak-percolation | `spread` recovers with probability gamma per step (a geometric infectious period) | `spread(..., duration=k)`: infected for exactly k steps; T = 1 − (1 − β)^k |
| Time spent infected per node (for SIS prevalence by degree) | ch16-sir-sis-in-time | `spread` stores the first infection step and the final state | an `infected_steps` field (steps spent infected) |
| Degree-based ODE solutions | ch16-si-in-time, ch16-sir-sis-in-time | none | the explainers integrate them with numpy; probably no command |

Notes from building batch 12:
- **Nothing new needed in GUESS:** `spread`/`outbreaks(duration=)` and `infected_steps` were enough. `plotLine(colors=)` keeps theory and simulation in matching colours.
- **SIR degree-based approximation:** count k − 1 of an infected neighbour's edges, as the book's SIR version does; the plain form over-predicts (83% against 68% simulated).
- **SI in time:** starting from one case, random take-off delays make every theory run ahead. With c first cases (x₀ = c/n, as the book starts) the pair approximation is within 0.01.
- **Simulation method:** continuous-time SI is computed exactly as one Dijkstra search per outbreak (exponential waits per edge), which makes averaging cheap in the browser.

## Batch 13: book pages 675–731 (Chapter 17, *Dynamical systems on networks*, and Chapter 18, *Network search*) — the last batch

The book's final two chapters: how processes on nodes settle, grow or
synchronise (and how the network's spectrum decides which), then how to
find things in networks, from web search to Kleinberg's navigable
small worlds.

**`ch17-fixed-points`: Dynamical systems, fixed points and stability (§17.1)** · planned
- *Idea:*
  - a system dx/dt = f(x) heads for fixed points;
  - a fixed point is stable if small perturbations shrink, which linearisation decides from the sign of f′(x*) (one variable) or the eigenvalues of the Jacobian (two).
- *Reader:*
  - one variable: f(x) plotted with its fixed points marked (filled when stable, hollow when not); click a start, and a dot slides along (paced) as its trajectory x(t) is charted;
  - two variables: a phase plane with a few trajectories from clicked starts and the eigenvalues at each fixed point shown (sink, source, saddle, spiral);
  - presets: logistic growth and a predator–prey model.
- *GUESS:* `plotLine`, `plotScatter`, numpy, `everyPaced`. (No network here: the drawing is a phase portrait, built from nodes and edges as markers.)

**`ch17-network-stability`: Dynamics on networks and linear stability (§§17.2–17.3)** · planned
- *Idea:*
  - with dx_i/dt = f(x_i) + Σ_j A_ij g(x_i, x_j), a symmetric fixed point is stable when every eigenvalue of the linearised system is negative;
  - in special cases that becomes a condition on the largest eigenvalue κ₁ of A, or the Laplacian's spectrum, so the network's structure decides stability;
  - the book's worked example, and more than one variable per node.
- *Reader:*
  - nodes coloured and sized by their deviation x_i − x* (a diverging scale) after a small kick;
  - "Kick" perturbs a node and the deviations spread along edges (paced, edges flowing where the coupling acts), dying away or growing;
  - a coupling slider crosses the threshold set by κ₁;
  - a live chart of the deviation's size, with the predicted growth rate dashed;
  - a table of κ₁ for several networks and their thresholds.
- *GUESS:* numpy, `everyPaced`, `spectrum`.

**`ch17-spectra`: Spectra of networks (§17.4)** · planned
- *Idea:*
  - the eigenvalues of A and L summarise a network;
  - random graphs have Wigner's semicircle (with κ₁ ≈ ⟨k⟩ sitting outside it);
  - heavy-tailed networks have large eigenvalues set by their hubs (≈ √k_max);
  - the Laplacian's spectrum gives components (zero eigenvalues) and the spectral gap.
- *Reader:*
  - choose a network and a matrix (A, L, normalised L);
  - a histogram of eigenvalues with the semicircle dashed where it applies;
  - the leading eigenvector shown on the nodes;
  - "Grow n" shows the bulk converging to the semicircle and κ₁ separating;
  - power-law networks with κ₁ against √k_max.
- *GUESS:* `spectrum`, `plotSpectrum`, a histogram of a list of numbers (see gaps).

**`ch17-synchronization`: Synchronization (§17.5)** · planned
- *Idea:*
  - coupled oscillators on a network (the Kuramoto model) lock into step once the coupling passes a threshold;
  - the order parameter r measures it;
  - the master stability function says whether the synchronised state survives, from the Laplacian's eigenvalues.
- *Reader:*
  - every node an oscillator, coloured by its phase on a colour wheel, so synchrony shows as a single colour spreading;
  - edges flow where neighbours pull each other;
  - a coupling slider;
  - a live chart of r(t);
  - "Simulate" sweeps the coupling for a random network and a ring, showing the transition.
- *GUESS:* numpy, `everyPaced`, node colours by hue, `plotLine`.

**`ch18-web-search`: Web search (§18.1)** · planned
- *Idea:*
  - a search engine finds pages that match the words, then ranks them by importance in the link network (PageRank) as well as relevance;
  - ranking by links alone or by text alone each fails in its own way.
- *Reader:*
  - a small invented web of pages with words;
  - type a query to see matching pages outlined, ranked by text score, by PageRank and by a blend (slider);
  - the top results as `linkTo` chips;
  - a link-farm page shows why links alone can be gamed.
- *GUESS:* `pagerank`, `Textfield`, `linkTo`. (Builds on `ch03-web-crawler` and `ch07-pagerank-hits`.)

**`ch18-distributed-search`: Searching distributed databases (§18.2)** · planned
- *Idea:*
  - in peer-to-peer networks a query must find the item without a central index;
  - flooding is fast but costly;
  - random walks are cheap but slow;
  - walks biased towards high-degree nodes find things in about √n steps on heavy-tailed networks, and copying each item's index to its neighbours helps more.
- *Reader:*
  - choose a strategy, then "Search" (paced), with the query's path flowing along edges and the visited nodes ringed;
  - a live chart of messages against steps;
  - "Simulate" plots steps to success against n for each strategy, on log–log axes.
  - Builds on `ch03-p2p-search` with the analysis.
- *GUESS:* `everyPaced`, `makeConfigurationModel`, `plotLine(logX=, logY=)`.

**`ch18-kleinberg`: Navigable small worlds (§18.3.1)** · planned
- *Idea:*
  - in Kleinberg's model each person on a grid has one long-range contact chosen with probability ∝ r^{−α};
  - greedy routing (always pass the message to the contact closest to the target) is fast only at α = 2 (the grid's dimension), where shortcuts are spread across every scale.
- *Reader:*
  - an α slider rebuilds the grid's long-range links (drawn faintly);
  - "Send a message" from a random person to a random target (paced), each hop flowing along an edge, the current holder ringed, and the distance to the target shown;
  - "Simulate": mean delivery time against α for two grid sizes, with the minimum at α = 2 sharpening as n grows.
- *GUESS:* `makeKleinbergRandom` or the explainer's own generator, `everyPaced`, `plotLine`.

**`ch18-hierarchical-search`: A hierarchical model for messages (§18.3.2)** · planned
- *Idea:*
  - people belong to groups nested in a hierarchy (and to several hierarchies: where they live, what they do);
  - links are likelier between people close in the hierarchies;
  - greedy routing by closeness in *any* hierarchy finds short chains, explaining the success of Milgram's experiment.
- *Reader:*
  - a tree of groups drawn beside the network;
  - a homophily slider and a number of hierarchies;
  - "Send a message" (paced), each hop choosing the contact closest to the target in some hierarchy, the hop and the hierarchy used highlighted;
  - "Simulate": success rate and chain length against homophily.
  - Links back to `ch04-milgram`.
- *GUESS:* `everyPaced`, a hierarchical model generator in the explainer.

### Gaps in batch 13 (added before building: `plotHistogram(list or array, bins, title=)`; `colorByPhase(field, period=)`, a colour wheel; `makeKleinbergRandom` now stores grid coordinates `gx`/`gy` (on a plain grid, not a torus; each long-range link is undirected); all random generators are seeded)

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| A histogram of a list of numbers (eigenvalues, delivery times) | ch17-spectra, ch18-kleinberg | `plotHistogram` takes a field | `plotHistogram([values], bins)`: lists too |
| Colouring nodes by a cyclic value (an oscillator's phase) | ch17-synchronization | `colorBy` ramps between two colours | `colorBy(field, cyclic=true)` (a colour wheel), or set colours in the explainer |
| Kleinberg grids with node coordinates and α | ch18-kleinberg | `makeKleinbergRandom(size, clust)` (on a torus) | check it records grid coordinates; otherwise give it `gx`/`gy` fields |

## To do (requests not yet done)

- (done) Lombardi-style layout and edge rounding: `lombardiLayout()`, `lombardiEdges()`, `lombardiness()`, `straightenEdges()`, edge field `arc`.
- (done) Directed edges follow Holten & van Wijk (CHI 2009): tapered by default, no arrowheads; `directedEdges("taper"|"fade"|"arrow")`, line style `fade`.
- (done) Command output links to the graph: nodes and edges a command prints can be hovered and clicked in the console, like returned values.
  - `predictLinks` links the names in its pairs, and "added N predicted edges" links to those edges.
  - The same holds for `shortestPath` ("no path from a to b"), bridging centrality's top node, `minCostFlow`'s ends, the route command's stops and steps, `minCut`'s edges, the counts of cliques, matches and cycles, motifs and collapsed motifs, `findDuplicates` pairs, `mergeNodes`, the group-statistics table (group name and hub), enrichment set names, and the new nodes from node-table imports.
  - Commands print through `session.say(...)` / `linked(...)`, which keep column widths.
