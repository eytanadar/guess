# Competitive analysis and suggestions (2026-11-05)

How GUESS for the web compares with graph-visualisation systems and with
modern coding environments, and what to add. Based on general knowledge of
these products as of 2026, not a hands-on audit of current releases.

## Where GUESS stands

GUESS's distinctive position is **a graph tool driven by a language**: queries
like `(freq > 100).color = red` and `v1 ? g.nodes` are shorter than any GUI
path, every action is reproducible text, and it now runs entirely in the
browser with Gephi-grade layouts and statistics. Most competitors are either
GUI-first tools with weak or no scripting (Gephi, Cytoscape, Kumu, yEd), or
code-first environments with no graph-native interaction (Jupyter + networkx,
Observable + d3). The gap to close is in both directions: GUI affordances that
emit Gython, and IDE-grade help for writing Gython.

## Graph visualisation systems

| system | strengths worth learning from | GUESS today |
|---|---|---|
| **Cytoscape** (desktop) / **Cytoscape.js** | Style panel with continuous/discrete/passthrough mappings and saved styles; linked node/edge **tables** with sort, filter, inline edit; select panel and filter chains; **network collections** (subnetworks from a selection, many views); groups/meta-nodes collapse and expand; an app store; NDEx/public data import; image-on-node charts (enhancedGraphics) | mappings via commands only; no tables; one graph |
| **Gephi / Gephi Lite** | Data Laboratory (tables, column operations, merges); composable filter tree with live sliders; statistics with reports; timeline for dynamic graphs; Preview with presets; Gephi Lite runs in the browser and shares via URL/gist | statistics, layouts, curved edges and filters as commands; no filter UI, timeline or table |
| **Graphistry** | GPU layouts and rendering for millions of edges; histograms that filter and colour the graph; point-and-click "filter by this value"; investigation workflows; embeddable sessions | WebGL rendering; CPU layouts (fine to ~10⁴ nodes) |
| **Kumu** | Storytelling: presentations stepping through views, perspectives (saved style + filter sets), shareable read-only maps, a decorations/selector language | states + morph, apps via `exportApp` |
| **Neo4j Bloom / Linkurious** | Natural-language-ish search phrases, expand/collapse neighbourhoods on demand, scene saving, rule-based styling | text queries; no incremental expand |
| **yEd / yFiles** | High-quality orthogonal, hierarchical, tree and organic layouts; edge routing; grouping/folding; label placement | Sugiyama/DAG, radial, KK, FA2; Noverlap; basic labels |
| **NodeXL** | Spreadsheet-native workflow and import from social media and other sources; automatic report of metrics | CSV import, `graphStats()` |
| **sigma.js / graphology**, **Retina** | Fast WebGL rendering; publish a static, searchable explorer for readers | apps via `?app=1` |

## Modern coding environments

| environment | strengths worth learning from | GUESS today |
|---|---|---|
| **Jupyter / JupyterLab** | Rich outputs (tables, plots, widgets); a variable inspector; `.ipynb` as the exchange format; extensions | cells with linked output; no tables or variable view |
| **marimo, Observable, Pluto.jl** | Reactive cells (change one, dependents re-run); UI elements bound to variables; stored as plain scripts; publish as apps | REPL-style cell stack; panels via `ui.dock` |
| **VS Code / Cursor / Zed** | Command palette; signature help while typing; inline diagnostics with quick fixes; go-to-definition; AI chat, inline completion and "explain this error" | Tab completion and hover docs; errors as tracebacks |
| **Hex, Deepnote** | SQL + Python cells side by side; parameter inputs; scheduled/shared apps; comments and collaboration | `sql()` command; single user |
| **RStudio / Spyder** | Environment pane (variables with type and size), history pane, plot pane | `history()` |
| **Google Colab** | Zero setup, share by link, forms on cells | zero setup (static site); no link sharing |

## Recommendations

Effort: S = a day or less, M = a few days, L = a week or more. Every GUI
feature should *write Gython into the console* (as the tools already do), so
work stays reproducible, undoable and learnable.

### Highest value

1. **Linked data table panel (M).** Cytoscape and Gephi users live in this
   view. A dockable Nodes / Edges table showing all fields, with sortable
   columns, a per-column filter box, sync with the graph selection in both
   directions, and inline editing (which emits `v12.dept = "x"`). Show
   `sel`, a GSet or a query result in it with `table(seq)`.
2. **Style and mapping panel (M).** Pick a field, then a visual property
   (colour, size, label, shape, width), then a mapping (categorical
   palette, gradient with linear/log/rank, passthrough), with a live legend.
   It emits `colorize`/`colorBy`/`sizeBy`. Saved "styles" (Kumu perspectives,
   Cytoscape styles) are a named bundle of these commands plus display
   settings, applied with one click.
3. **Command palette and search (S).** Cmd/Ctrl+K: fuzzy-search commands
   (with their docs), node names and field values ("dept = dept3" → select
   them), toolbar actions and recent commands. This is the single
   biggest discoverability win for 180 commands.
4. **Signature help and better errors (S/M).** Show the parameter hint while
   typing inside `forceAtlas2Layout(`; underline the failing line in the cell;
   replace tracebacks with one-line messages plus "did you mean `dept`?"
   (names, fields and node names are all known); a "show details" toggle
   keeps the traceback.
5. **Natural language → Gython assistant (M).** A "describe what you want"
   box that turns "colour the five most central nodes in each department red"
   into Gython and puts it in the working cell for review, plus "explain this
   error". The API reference and docstrings make good grounding. This is now
   the expected affordance in Hex, Cursor and Colab, and it complements
   GUESS's language-first design instead of replacing it. Needs an API key or
   proxy, so make it optional.
6. **Filter panel with live sliders (M).** Gephi's most loved feature: a
   stack of conditions (field range sliders with histograms, k-core, degree,
   community size, ego network) that hide or show without deleting. Each
   change rewrites one `showOnly(...)` line. This also covers Graphistry's
   "histogram that filters" pattern.

### Strong next steps

7. **Variable / workspace pane (S).** User variables with type, size (`sel` —
   12 nodes), hover-highlighting for sets, and click to show in the table.
   Also list saved states, hulls and legends.
8. **Share by link and publish (M).** Encode a session (or a script plus data
   URL) into a shareable URL or gist, like Gephi Lite and Observable;
   "Publish" builds a read-only explorer bundle (search box, hover info,
   legends) from the current view with the existing bundle script.
9. **Subnetworks and multiple views (L).** "New graph from selection" and a
   tab strip of graphs (Cytoscape collections), with `use("name")` in Gython.
   This also enables side-by-side comparison of states.
10. **Group, collapse and expand (M).** Meta-nodes from a group or community
    (`collapse(groupBy(modularity_class))`), double-click to expand (Cytoscape
    groups, yEd folding, Bloom expansion). Pairs well with large graphs.
11. **Reactive "watch" cells and live charts (M).** Pin a cell so it re-runs
    when the graph changes (marimo/Observable style but opt-in), useful for
    `graphStats()`, charts and legends. This also covers the "live charts" item
    already in the plan.
12. **Notebook and report export (S/M).** Export the cell stack as `.ipynb`
    (with a small `guess` shim), as Markdown or HTML with PNG snapshots, or as
    a plain `.py` script (`saveHistory` already exists).

### Worth considering

13. **Timeline for dynamic graphs (L).** Use ranges/states as time: a slider
    with play, a sparkline of node and edge counts, and morphs between steps
    (Gephi timeline, Kumu presentations).
14. **Presentations / guided tours (M).** A sequence of saved views (state +
    camera + annotation) to step through or record. This builds on states,
    morph and the movie recorder.
15. **Scale (L).** GPU layouts (WebGL/WebGPU ForceAtlas2, as in Graphistry and
    graphology) and level-of-detail rendering (aggregate far-away nodes, draw
    labels only for important ones) for 10⁵–10⁶ edges.
16. **More layout quality (M).** Orthogonal and tree layouts with edge
    routing, and label-aware placement (yEd); Gephi's Label Adjust.
17. **Richer node glyphs (M).** Pie or donut nodes for categorical fields,
    icons, borders by field, and edge bundling for dense graphs.
18. **Data connectors (M).** Paste a table, fetch from a URL, Wikidata or
    SPARQL queries, Neo4j/Cypher over HTTP, NDEx (Cytoscape's network
    repository), and `micropip.install` for extra Python packages.
19. **Editor niceties (S).** Optional Vim keys, multi-cursor, a snippets
    gallery (the welcome examples, expanded by task), and a Find feature in
    the output.
20. **Collaboration (L).** Live multiplayer sessions or comment threads on
    views. It is high cost, so only worth doing if GUESS is used for team
    analysis.

### Suggested order

Start with 3 (palette and search), 4 (signature help and errors) and 1 (data
table), which together make the tool much easier for newcomers. Follow with 2
(style panel) and 6 (filters), so the most common Gephi and Cytoscape
workflows have GUI paths that teach Gython. Then 5 (assistant) and 8
(sharing).
