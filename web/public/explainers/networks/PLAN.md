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

**`ch01-zoo`: What is a network?** · planned
- *Idea:* nodes and edges, and the book's four kinds of network.
- *Reader:*
  - starts with an 8-node, 10-edge toy network and hovers to see "node" and "edge";
  - then uses a drop-down to switch between four real examples: technological (`us-airports.gdf`, map layout), information (`vis-papers.gdf` citations, with arrows), social (`makeSample('karate')`) and biological (a food web from `makeNicheModel`, with `trophicLevels()` as height);
  - each example has a two-line caption and its node/edge counts, and notes whether it is directed.
- *GUESS:* `Dropdown`, `makeSample`, `makeFromFile`, `geoLayout`, `makeNicheModel`, `trophicLevels`, `orderedLayout`.

**`ch01-properties`: Three things to measure** · planned
- *Idea:* degree and hubs, the small-world effect, and communities, as a first look.
- *Reader:* works with the karate club in three tabs:
  - **Degree:** each node's number is its degree, and size follows degree. A directed toggle switches to a small web graph with separate in- and out-degree.
  - **Small world:** click two members to see the shortest path and its length; a counter shows the mean distance.
  - **Communities:** a button runs Louvain and colours the groups. A checkbox compares them with the real split (`club`).
- *GUESS:* `labelBy`, `sizeBy`, `shortestPath`, `averagePathLength`, `louvainClusters`, `compareClusters`, `Tabs`.

### Ch. 2 Technological networks (pp. 14–31)

**`ch02-internet-tiers`: The shape of the Internet (§2.1)** · planned
- *Idea:* a backbone, regional and local ISPs, then end users. Most studies keep only the routers.
- *Data:* a generated four-tier network of about 300 nodes, with a `tier` field.
- *Reader:*
  - sees the tiers as rings (`concentricLayout(tier)`);
  - "Router level" hides the end users and shows how few nodes and edges are left;
  - clicking an end user shows its route to another user: up through the tiers and back down.
- *GUESS:* `concentricLayout`, `showOnly`, `shortestPath`, `flow` edge style for the route.

**`ch02-traceroute`: Mapping the Internet with traceroute and BGP (§§2.1.1–2.1.2)** · planned
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

**`ch02-telephone`: Circuit switching in the telephone network (§2.2)** · planned
- *Idea:* there are three tiers (subscribers, local exchanges, long-distance offices). Local calls never use a trunk, and trunk capacity limits how many calls connect.
- *Data:* a generated three-tier network laid out by region.
- *Reader:*
  - "Place 20 calls" picks random pairs, and a "local share" slider controls how many are local;
  - each connected call holds its circuit (the edges glow while it lasts), and a call that finds a full trunk is blocked (red flash);
  - counters show calls connected, calls blocked and trunk load;
  - a "trunk capacity" slider shows blocking rise as capacity falls.
- *GUESS:* `every` timer, edge `width` and `color` for load, `flow` style for active circuits, `Slider`.

**`ch02-power-cascade`: Cascading failures in a power grid (§2.3)** · planned
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

**`ch02-rail-spaces`: Which network is the rail network? (§2.4)** · planned
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

**`ch02-river-trees`: Rivers are trees (§2.5)** · planned
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

**`ch03-web-crawler`: How a crawler finds the Web (§3.1)** · planned
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

**`ch03-citations`: Citation networks point back in time (§3.2, §3.2.1)** · planned
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

**`ch03-p2p-search`: Searching a peer-to-peer network (§3.3.1)** · planned
- *Idea:* flooding search with a hop limit works on small networks but floods the network with messages. Supernodes fix that.
- *Data:* a generated network of 200 peers. A file is copied onto a few random peers.
- *Reader:*
  - clicks a peer and searches;
  - the query spreads in rings, hop by hop, until it is found or the TTL runs out;
  - counters show the messages sent;
  - a TTL slider controls the hop limit;
  - "Use supernodes" switches to the two-tier design and compares the message counts.
- *GUESS:* BFS by rings, `every`, `heatMap` or colour by hop, `concentricLayout(tier)` for the two-tier view.

**`ch03-recommender`: Recommendations from a bipartite network (§3.3.2)** · planned
- *Idea:*
  - people and items form a bipartite network, with like/dislike weights;
  - recommend what similar people liked.
- *Data:* generated people and films with ratings drawn from a few taste groups.
- *Reader:*
  - sees people on one side and films on the other (`bipartiteLayout`), with edges coloured from dislike to like;
  - clicks a person to see their most similar people (shared likes) and the recommended films, with a reason ("liked by 3 people like you");
  - a "Hide one rating and predict it" button shows a hit or a miss.
- *GUESS:* `bipartiteLayout`, `similarTo`, `project`, `colorBy` on edge weight.

**`ch03-keyword-index`: A book index is a network (§3.3.3)** · planned
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

### Gaps found in batch 1

| need | used by | status in GUESS | proposal |
|---|---|---|---|
| A chart inside an app panel | power-cascade, citations (and most of Ch. 10–16 later) | charts open in the dock. `View` can embed only table, style, filter, variables, help, timeline and console | add a `Chart(...)` widget, or `View("chart")` showing the last chart |
| Log–log axes for distributions | power-cascade, later Ch. 10 | possible through Altair (`showChart`), but `plotHistogram`/`plotDistrib` have no log option | add `log=True` to `plotHistogram`/`plotDistrib` |
| Drawing plain lines or shapes over the graph (annotations) | river-trees (Buffon lines), later diagrams | no annotation API. Hulls and legends only | workaround: hidden end nodes plus edges; a small `drawLine`/`drawText` overlay would be cleaner |
| Real infrastructure data (router/AS-level Internet, power grid, gas pipelines) | traceroute, power-cascade | not bundled | use generated data for now; optionally bundle an AS-level snapshot (CAIDA/Routeviews; check licence) and the Western US grid used by Watts and Strogatz |
| Patent and legal citation data | citations §3.2.1 | not bundled | explain with `vis-papers.gdf`; mention that the structure is the same |

Everything else in batch 1 uses existing commands.
