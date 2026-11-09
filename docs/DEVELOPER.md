# Developer guide

## Setup

Requirements: Node 24+, Python 3.14 (Pyodide's CPython version) and
[uv](https://docs.astral.sh/uv/) or pip, Chrome (for the Playwright tests).

```sh
# Python package (runs in Pyodide in the browser; tested under CPython)
cd py
uv venv -p 3.14 .venv && uv pip install -p .venv -r requirements-dev.txt

# front end
cd ../web
npm install
npm run dev            # http://localhost:5173 — reloads on TS/CSS and Python changes
```

The dev server sends the COOP/COEP headers that make the page cross-origin
isolated (needed for interrupting Python). The Python files are imported into
the bundle with `import.meta.glob("../../py/guess/*.py", {query: "?raw"})`, so
editing them reloads the page; there is no separate Python build.

## Tests

```sh
cd py && .venv/bin/python -m pytest -q        # ~160 tests, about a minute
cd web && npm run typecheck && npm run test:e2e
```

Use `python -m pytest` (not the `pytest` script) so `tests/` imports resolve.
Playwright starts its own Vite server on port 5318 and uses your installed
Chrome locally (Playwright's Chromium in CI).

| suite | covers |
|---|---|
| `py/tests/test_gython.py` | the paper's examples, compiler, operators, completions |
| `test_phase1.py`, `test_states.py`, `test_visuals.py`, `test_gui.py`, `test_sql.py`, `test_bends.py` | model, commands, states/ranges, hulls/legends, widgets, SQL, routed edges |
| `test_layouts.py` | every layout (determinism, fixed nodes, quality, the KK fast path) |
| `test_persist.py` | session files and display settings round trips |
| `test_gephi.py` | statistics, Louvain, filters, paths, palettes, GEXF/CSV, ForceAtlas2, selection |
| `test_undo.py` | undo/redo, drags, history, linked `print` |
| `web/e2e/*.spec.ts` | the real app in Chrome: console, tools, files, selection, undo, theme |

Python output goes through `session.emit`; tests use the `Recorder` fixture in
`test_gython.py` and the `ev(session, expr)` helper. Note that `ev` clears the
recorder, so read `s.rec` before calling it.

## Code map

```
py/guess/          the Python package (see ARCHITECTURE.md for each module)
py/tests/          pytest suites
py/tools/          gen_api_docs.py (writes docs/API.md)
web/index.html     page shell and toolbar
web/src/           main.ts, renderer.ts, console.ts, dock.ts, worker.ts, protocol.ts, store.ts, style.css
web/e2e/           Playwright tests (helpers.ts: boot, type, run, lastError)
web/public/        coi-serviceworker.js, examples/
web/deploy/        server config templates copied into bundles
web/scripts/       bundle.mjs (npm run bundle)
docs/              this documentation
gdfs/              sample.gdf (the built-in sample graph) and other GDF files
guess-orig/        the original Java/Jython GUESS (reference only; not in git)
```

## Common tasks

### Add a Gython command

Define a function inside the relevant module's `install(session)` and register
it; the docstring becomes `help()`, the hover tooltip and `docs/API.md`.

```python
def install(session):
    g = session.graph

    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    @cmd
    def degreeHistogram(field=None):
        """degreeHistogram() prints how many nodes have each total degree."""
        ...
```

Guidelines:
- Change the graph through attributes (`n.color = c`), `g.addNode`,
  `g.addEdge`, `g.remove`; these mark elements for the next patch **and**
  record undo information. Writing `elem._vals` directly bypasses both.
- Raise `GuessError("...")` for user mistakes; the console shows the message
  without a traceback through the internals.
- Return a `GSet` (with an annotation) for sets of elements so the output is
  linked and works with the set operators.
- For display-level state, extend `View` in `visuals.py` (and `capture` /
  `restore` for undo, `record` for the overlay message, `persist.py` for
  session files).
- Regenerate the reference: `cd py && .venv/bin/python tools/gen_api_docs.py`
  (a test fails if `docs/API.md` is stale).

### Add a computed statistic

Add a function `graph -> {node: value}` (or `({node: value}, INT)`) to
`analysis.LAZY`. It becomes a node field computed the first time it is used.

### Add a layout

Write a generator `_my_gen(snap, ...)` in `layouts.py` that yields `(n, 2)`
position arrays (top-left corners, as node `x`/`y`), and a command that calls
`lay.run(lay.snap(), _my_gen(...))` (or `lay.apply(snap, positions)` for a
one-shot layout). Respect `snap.fixed`. `_repulsion(P, power, cutoff, mass=)`
gives O(n log n)-ish pairwise repulsion for large graphs.

### Change the protocol

Edit `web/src/protocol.ts` (the single source of truth), then the emitter in
Python (`session.emit({...})`) and the handler in `main.ts` (`worker.onmessage`)
or `worker.ts` (`handle`). Keep messages JSON-serialisable: the Python test
recorder enforces it.

### Front-end conventions

- No framework; plain DOM + CSS variables (`style.css` tokens; dark theme via
  `prefers-color-scheme` and `html[data-theme]`).
- The renderer never talks to the worker; `main.ts` wires events.
- Anything the user does that changes the model goes through Python as Gython
  (`term.submit("...")`) so it appears in the console, the history and undo.

## Debugging tips

- `to_python("a->b")` (in `guess.compiler`) shows the Python a Gython snippet compiles to.
- In the browser console, worker errors appear as `error` messages in the GUESS console.
- `?load=<url>` opens a graph or session at startup; `&app=1` hides the console.
- Clear autosave: DevTools → Application → IndexedDB → `guess`.

## Gestures guide screenshots

The in-app "Mouse and gestures" guide (`web/src/gestures.ts`) uses screenshots
in `web/public/help/`. Regenerate them after UI changes with
`npm run help-shots` (all) or `npm run help-shots -- ring edge` (some).

## Demo video

`web/demo/` rebuilds the narrated demo after changes (see its README):
`npm run demo:script` (Claude rewrites the script), `npm run demo -- --dry-run`,
then `npm run demo`. When UI selectors change, update the action table in
`web/demo/PROMPT.md`.

## Releasing

1. Bump `version` in `web/package.json`.
2. Run both test suites.
3. `npm run bundle` (and/or `npm run bundle -- --offline`), see [DEPLOY.md](DEPLOY.md).
