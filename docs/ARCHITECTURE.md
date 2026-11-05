# Architecture

GUESS for the web is a static site. Everything runs in the browser: the graph
model and the Gython language run in Python (CPython 3.14 compiled to
WebAssembly by [Pyodide](https://pyodide.org)) inside a Web Worker; the page
draws the graph with [PixiJS](https://pixijs.com) (WebGL) and hosts the code
console ([CodeMirror 6](https://codemirror.net)). There is no server-side code.

```
┌──────────────────────── page (main thread) ────────────────────────┐
│ main.ts      wiring: toolbar, tools, menus, tooltips, autosave,     │
│              theme, file open/drop, movie recording                 │
│ renderer.ts  PixiJS scene: nodes, edges, labels, hulls, selection,  │
│              focus, camera, hit testing, PNG/SVG export             │
│ console.ts   working cell (CodeMirror) + executed-cell stack        │
│ dock.ts      Python-defined panels/widgets and linked SVG charts     │
│ store.ts     IndexedDB autosave                                     │
└───────────────▲──────────────────────────────┬──────────────────────┘
                │ FromWorker messages           │ ToWorker messages
                │ (scene, patch, out, overlay…) │ (run, move, select…)
┌───────────────┴──────────── worker.ts ────────▼──────────────────────┐
│ Pyodide + numpy + networkx, the `guess` package in /guess_py,        │
│ user files in /data (the working directory)                          │
│                                                                      │
│  Session (session.py) ── namespace, run(), undo, output, patches    │
│   ├─ compiler.py   Gython → Python 3 AST                             │
│   ├─ runtime.py    helpers compiled code calls (__gop__, __gsub__ …) │
│   ├─ model.py      Graph, Node, Edge, Field, GSet, Journal           │
│   └─ commands, analysis, algorithms, layouts, visuals, states,       │
│      ranges, charts, gui, persist, formats, gdf, gexf, sqlquery      │
└──────────────────────────────────────────────────────────────────────┘
```

## The Python side (`py/guess/`)

| module | role |
|---|---|
| `session.py` | One interactive session: the Gython namespace, `run()`, protected system names, completions, docs, render records/patches, undo/redo stacks, `print` with linked output, selection (`sel`). Talks to the page only through `emit(dict)`. |
| `compiler.py` | Gython → Python. Stage 1 rewrites the infix graph operators (`->`, `<-`, `<->`, `?`, `like`, …) at the token level into marker comparisons so Python's parser gives them comparison precedence; stage 2 is an AST transformer (operators → `__gop__`, attribute access/assignment broadcasting over sets, `-` → `__gsub__`, bare command names auto-called at statement level, protected-name checks). |
| `runtime.py` | The functions compiled code calls. |
| `model.py` | `Graph` (nodes by name and id, edges by id, schemas, change tracking, `remove`/`add` with `g.deleted`, journaled for undo), `Node`/`Edge` (field values in a dict), `Field` (typed column; comparisons build queries), `GSet` (list of elements whose attribute access/assignment broadcasts), `Journal` and `Graph.revert` (undo). |
| `commands.py` | The global commands of the original `Main.py`: loading/saving formats, structure edits, grouping, colour/size mappings (`colorize`, `sizeBy`, `colorBy`, …), `center`, `help`. |
| `analysis.py` | Gephi-style statistics as lazily computed node fields, Louvain communities, structural filters, `shortestPath`, `heatMap`, `paint`, `showOnly`. |
| `algorithms.py` | networkx bridge (`to_networkx`), betweenness, Girvan–Newman/components clusters, random-graph generators. |
| `layouts.py` | All layouts on a numpy snapshot (`_Snapshot`); iterative layouts are generators driven by `_Layouts.run`, which publishes positions ~30×/s and stops cleanly on interrupt. Includes ForceAtlas2, Noverlap and the sampled-stress Kamada–Kawai fast path. |
| `visuals.py` | The `View`: hulls, legends, background, background image, arrow sizes, curved edges, edge colour mode, label options, selection command; sent as one `overlay` message. |
| `states.py`, `ranges.py` | Saved states (`ss`/`ls`/`morph`, `field[state]`) and existence-interval queries. |
| `charts.py`, `gui.py` | Linked charts and Python-built panels/widgets/timers/graph events (rendered by `dock.ts`). |
| `persist.py` | `.guess` session files (JSON) and apps; also used for autosave. |
| `formats.py`, `gdf.py`, `gexf.py`, `sqlquery.py` | Pajek/GraphML/DL, GDF, GEXF/CSV, `sql()` over SQLite. |

### Execution of one console cell

1. `console.ts` sends `{type: "run", code, cell}`; `worker.ts` sets
   `session.current_cell` and calls `session.run(code)`.
2. `run` starts an undo **journal** on the graph, compiles the Gython,
   computes any lazy statistic the code names (`_prepare_fields`), and
   `exec`s it in the namespace with stdout redirected to `text` messages.
   Expression statements go through `__display__` → an `out` message whose
   segments link to node/edge ids.
3. Model writes go through `Field.set` / `Graph.add*`/`remove*`, which mark
   elements dirty and record previous values/operations in the journal.
4. Long-running code (layouts) calls `session.tick()`, which flushes patches
   about 30 times a second so the display animates. The Stop button writes
   SIGINT into a `SharedArrayBuffer` Pyodide polls (`setInterruptBuffer`),
   raising `KeyboardInterrupt`.
5. Afterwards `flush()` turns the dirty sets into one `patch` (changed node
   and edge records, removals, packed positions for move-only changes,
   optional morph timing) plus an `overlay` if the view changed, and the
   journal becomes an undo entry if anything changed.

### Undo

Every top-level `run` (and every node drag) records a `Journal`: structural
operations in order (`add`/`rem` of elements, `field`/`unfield` of schema
columns), the *first* previous value of each `(element, field)` written, and
copies of `g.deleted`/`g.bends` if touched. The session also snapshots the
view (hulls, legends, display settings), saved states and ranges, and keeps
them only if they changed. `Graph.revert(journal)` replays it backwards
(structure first, then values, then the deleted/bends dictionaries) **while
journaling**, so the reversal is itself a journal: undo pushes it on the redo
stack and redo reverts it again. The stack holds 50 steps and about 3 million
recorded values. Not undoable: Python variables, files written to `/data`,
downloads. Lazy statistic fields are not journaled (recomputing is harmless).

### Rendering protocol

`protocol.ts` is the single definition of the messages. Python → page:

| message | meaning |
|---|---|
| `scene` | full node and edge records (after loading a graph) |
| `patch` | changed records, removed ids, packed `pos` for move-only nodes, optional `morph` |
| `overlay` | view state: background (null = theme), image, arrows, curvature, edge colour mode, label options, hulls, legends |
| `out` / `text` / `error` | console output (segments link to elements) |
| `center`, `export`, `download`, `image`, `movie` | camera, file output and media |
| `chart`, `ui` | dock charts, panels, widget updates, timers, graph events, status |
| `select` | selection set from Python (`select(...)`) |
| `undone` | undo/redo affected console cell N (strike-through) |
| `ready`, `status`, `done`, `reply` | lifecycle and request/response |

Page → Python: `init`, `run`, `completions`, `docs`, `describe` (tooltip),
`assign` (context menu → variable), `event` (widget/graph/timer callbacks),
`move` (dragged nodes, one undo step), `select` (box/lasso → `sel`),
`snapshot` (autosave), `writeFile` (opened files).

Node records are compact: `{i, name, x, y, w, h, c, a, s, sc, l, lv, lc, v, img}`
(colours as 0xRRGGBB plus alpha); edges `{i, s, t, d, c, a, w, v, l, lv, lc, b}`.

### The renderer

`renderer.ts` keeps only visual state (maps of node/edge records). It redraws
nodes and edges into PixiJS `Graphics` when something is dirty, labels as
pooled `BitmapText` (rendered at 4× and scaled), and an overlay layer for
hover highlights, the selection outline and the marquee. Edges are straight,
quadratic curves for parallel edges, polylines for routed (Sugiyama) edges, or
Gephi-style circular arcs (`curvedEdges`). Focus mode dims everything outside a
node's neighbourhood; label culling hides overlapping labels by priority on
zoom. Hit testing is geometric (nodes, then nearest edge polyline).

### Front-end state that is not in Python

Camera, hover, focus, tool mode, theme (`localStorage guess.theme`), console
width (`guess.consoleWidth`) and command history (`guess.history`). The graph
itself is autosaved to IndexedDB two seconds after changes (a `.guess`
session JSON) and restored on reload.

## Why these choices

- **Pyodide in a worker** keeps the UI responsive during layouts and lets the
  Stop button interrupt Python; the model stays in Python so Gython semantics
  are exactly Python's.
- **numpy** for layouts and statistics; **networkx** (pure Python, loaded
  without its matplotlib dependency chain) for algorithms that don't need
  scipy. PageRank/HITS/eigenvector are numpy reimplementations because
  networkx's versions require scipy.
- **Patches, not polling**: Python tracks dirty elements and sends deltas, so
  large graphs stay cheap to update.
- **Static hosting**: no backend to run or secure; `coi-serviceworker.js`
  provides cross-origin isolation where the server can't send headers.
