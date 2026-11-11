# Review: the Gython DSL, and linking code with the visualization (2026-11-10)

Two read-only reviews, made after the cookbooks were written. Claims marked
(verified) were run through `Session` on `gdfs/sample.gdf`.

Plan agreed 2026-11-10: start with the wrong-answer bugs, linked dicts, sets and
f-strings in output, two-way highlighting and clickable chart bars, then
`.avg`-style aggregates and `top()`. Renames and the meaning of `-` need a
decision first. See [Status](#status) at the end.

---

# Part 1: the Gython DSL

## Strengths

- **A small core.** Gython is a token pre-pass plus an AST transform
  (`compiler.py`, about 350 lines) with runtime helpers (`runtime.py`). There
  is no custom parser, and Python tooling still works.
- **Queries read well.** Queries are sets: `(freq > 100).nodes.labelvisible =
  true` and `v1 ? g.nodes` read naturally, and sets carry their label in
  output ("dept == 'dept1'").
- **Fields are first-class.** Computed fields are lazy, so
  `sizeBy(pagerank, …)` just works. Field aggregates (`freq.max`,
  `dept.distinct`), states (`field[state]`) and undo work across every
  command.
- **Good errors in places,** e.g. `v1.Dept` suggests `dept`.

## Wrong answers with no error (verified)

| you write | you get | should be |
|---|---|---|
| `3 < degree < 6` | 313 nodes | 49, `(degree > 3) & (degree < 6)` |
| `(dept == "dept1") and (degree > 3)` | 138 nodes (just `degree > 3`) | the overlap of both |
| `not someSet` | a bool | the complement |
| `degree in [1, 2]` | always `True` | the matching nodes |

Python turns a chained comparison into `and`. `and`, `or` and `not` test
whether a set is empty instead of combining sets. `Field.__eq__` returns a
non-empty set, so `in` is always true.

## Other traps

- **Precedence.** `dept == "dept1" & degree > 3` raises a raw traceback from
  `runtime.py` ("unsupported operand … 'str' and 'Field'") with no hint to add
  parentheses. This is probably why recipes fall back to list comprehensions.
- **`-` between node sets means edges.** `g.nodes - (dept == "dept1")`
  returns the edges between them (classic GUESS), but `s -= t` is a TypeError
  while `s &= t` works. Recipes then reach for `.difference()`.
- **Fields aren't iterable.** `max(degree)` fails with "no saved state 0",
  because `__getitem__` (states) is used as the iteration protocol.
- **Mismatched queries return empty sets with no warning:** `dept == 3`,
  `freq > "abc"`.
- **Builtins can be shadowed.** A node named `len` or a field named `type`
  replaces the builtin for the whole session. `len([1, 2])` then fails with
  "'Node' object is not callable".
- **A broken hint.** `_suggest` (`session.py`) can suggest the misspelt name
  itself ("did you mean 'color'?").

## Inconsistencies

- **About 860 reserved names:** commands, colours, fields and node names,
  including `x`, `name`, `log`, `density`, `report`, `tan` and `plum`.
  - `from math import log` is a compile error.
  - The error always says "(graph, node, field or color)", even for a
    command.
  - A loop variable `n` fails at the top level when there's a node named
    `n`, but works inside a function or comprehension.
  - The core cookbook says `size` is reserved, but `size = 3` works.
  - `addNode("center")` makes a node that can't be reached by name, with no
    warning.
  - A field named `class` can only be read with `getattr(n, 'class')`.
- **Field parameters have six names:** `field`, `fld`, `kindField`,
  `typeField`, `seedField`, `lenField`. `add*Field` takes `fieldName`,
  `sqlType` and `defaultValue`.
- **Strings aren't accepted as fields.** `sizeBy("degree", …)` fails, and
  four separate helpers turn an argument into a field (`commands.py`,
  `layouts.py`, `gv.py`, `charts.py`).
- **Ranges are named differently:** `colorBy(field, start, end)`,
  `sizeBy(field, smallest, largest)` (its docstring says min/max),
  `resizeLinear(field, start, end)`.
- **Overlapping pairs:**
  - `colorize(f, a, b)` vs `colorBy(f, a, b, scale='rank')`;
  - `resizeLinear` vs `sizeBy(scale='rank')`;
  - `moveLayout` vs `translateLayout`;
  - `biComponentCluster` vs `biComponentClusters`;
  - `degree` vs `totaldegree`;
  - `node1`/`node2` vs `source`/`destination`.
- **Toggles are switched off in four ways:** `pieOff()`, `unbundleEdges()`,
  `curvedEdges(False)`, `removeConvexHulls()`.
- **`name=` has three meanings:** an output field (`embed`,
  `effectiveDistance`), a graph (`subgraph`), or a node (`mergeNodes`).
- **Colours don't round-trip.** They're stored as "r,g,b" strings, so
  `n.color == red` doesn't work, and there's no alpha or lighten helper.
- **`sortBy` has no `descending=`,** although `GSet.sortBy` does; hence
  `sortBy(degree)[-k:]`.
- **Vestiges:** `*args` signatures (`sortBy`, `groupBy`, `center`,
  `make*Random`) and Java-era stubs (`exportSWF`, `getAppletContext`).
- **Clustering output:** Louvain writes `modularity_class`, every other
  method writes `X_class`. Labels say "47 communitys".
- **Docs vs code:** the manual says `groupAndSortBy` puts the largest group
  first, but it sorts by value.
- **Two error styles.** A `GuessError` is a clean line; Python errors dump
  internal frames. Reading an unknown field suggests a name, writing one
  (`n.colour = red`) doesn't.

## Missing

- **Aggregates over a set's values:** `(dept == "x").degree` is a plain list,
  so recipes write `statistics.mean(n.degree for n in g.nodes)`.
- **Membership and ranges:** nothing like `dept in ("a", "b")`.
- **A set filter:** no `set.where(lambda …)` that returns a set.
  `interEdges(room)` exists but no recipe uses it.
- **Inline field creation:** `Node.score = 0` is an error; `addNodeField`
  must come first.
- **A scoped what-if:** the `ss(...)` … `ls(...)` pattern recurs.
- **Echo control:** every top-level expression echoes, and the only way to
  hide it is `_ =`.
- **Attributes on result objects** need `object.__setattr__`, because
  `GSet.__setattr__` broadcasts.
- **`top(field, k)`.**
- **Fast membership:** `n in someSet` scans a list, so a loop over it is
  O(n²) (from reading the code; not timed).

## Proposed tweaks

| # | before → after | cost | breaks? |
|---|---|---|---|
| A | `3 < degree < 6` → compiled to `(degree > 3) & (degree < 6)` | small (compiler) | only fixes wrong results |
| B | `a and b`, `a or b`, `not a` on query sets → `&`, `\|`, complement | medium | code that tests a set's truthiness must keep working |
| C | `dept in ("a", "b")` → a membership query | small | no |
| D | `-` between node sets: at least make `-=` match `-`, and warn | small | changing `-` itself would |
| E | `statistics.mean(n.degree for n in s)` → `s.degree.avg` (`.sum .min .max .median .distinct`); `max(degree)` works | small | no |
| F | `addNodeField("score", INTEGER, 0)` → `Node.score = 0` | small | no |
| G | `sizeBy("degree", …)` accepted everywhere, through one helper | small | no |
| H | `sortBy(degree)[-k:]` → `top(degree, k)` | trivial | no |
| I | `_ = louvainClusters()` → a trailing `;` hides the echo; sets of sets print compactly | small | no |
| J | stop node and field names shadowing builtins; allow imports and loop variables to shadow commands; name the real kind in the error | small–medium | loosens a protection |
| K | `getattr(n, 'class')` → `n.class_` | trivial | no |
| L | `ss(...)` … `ls(...)` → `with scratch(): …` | small | no |
| M | `[e for e in g.edges if …]` → `g.edges.where(...)` | trivial | no |
| N | `"130,130,130,35"` → `gray.alpha(35)` | small | no |
| O | argument names unified (`field`, `smallest`/`largest`, `on=False` toggles), old names kept as aliases; hide Java-era stubs | medium | no, if aliased |
| P | a clear error for the `&` precedence trap | trivial | no |

---

# Part 2: linking code with the visualization

## What's linked today

- **One hub.** Every link goes through `highlightItems` (`web/src/main.ts`),
  which highlights the graph and marks the matching chart bars. Items are
  `["n" | "e", id]`.
- **Console output → graph.** `segment()` (`py/guess/session.py`) turns
  nodes, edges and lists, tuples or sets of them (up to 500) into linked
  spans. Hover highlights them, with a tooltip of field values (one element)
  or a group summary. Click selects and centres. Right-click opens the menu.
- **Code → docs only.** Command names in code show their documentation, but
  nothing in code links to the graph.
- **Graph → elsewhere.**
  - Hover highlights chart bars and shows a tooltip.
  - The selection is kept in the variable `sel` and in the table.
  - The path, heat and paint tools, the context menu and table edits all
    write code.
- **Charts → graph.** Hovering a bar or pie slice highlights its elements.
  Line charts have no ids.
- **Tables, legends and the Variables panel → graph,** on hover. Legend rows
  carry a query, so the right-click menu acts on it.
- **Undo** strikes through the matching cell. The history records which cell
  changed which element and field, but nothing displays it.
- **Watched cells** re-run after each command.

## Gaps

1. **Dicts, sets and f-strings print as plain text.** `{n: n.degree …}`,
   `set(...)`, `print(f"… {node}")` and every command summary written as an
   f-string are unlinked. So is `offspring()`, which returns a dict.
2. **`outbreaks()` has nothing to link.** Its histogram bars carry no ids.
   The spread, extinction and robustness line charts carry none either.
3. **Groups over 500 items** link only the first 500.
4. **Old output may point at the wrong elements** after a new graph is
   loaded, because spans store only an id (from reading the code).
5. **Error messages link nothing,** and `_suggest` can repeat the misspelt
   name.
6. **Linking is one-way.** Hovering the graph, a table row or a legend never
   marks console output, legend rows or table rows.
7. **Chart bars only respond to hover:** no click to select, no brushing, no
   menu, and no linking between charts.
8. **Code is inert.** Variables, fields, node names and queries in code
   don't highlight anything.
9. **No quick way to get a node or the selection into code.**
10. **Edge tables don't show the selection,** and the table doesn't scroll
    to a hovered element.
11. **Provenance is unused.**

## Proposed improvements, by value for effort

1. **Link dicts, sets and Counters in output** (small): extend `segment()`.
2. **Insert as code** (small): alt-click a node, row or legend entry to
   insert its expression; an "Insert as code" menu item.
3. **Two-way highlighting** (small–medium): graph hover marks console
   output, table rows and legend rows.
4. **Click and brush on charts** (small–medium): click a bar to select its
   elements, right-click for the menu; histogram bins carry their query,
   e.g. `(degree >= 4) & (degree < 6)`.
5. **Linked f-strings and reports** (medium): nodes inside printed text
   become links, so command summaries and errors link for free. Give the
   `outbreaks` histogram the ids of the nodes in each bin.
6. **Hover-linking in executed code** (medium): a variable highlights its
   members, a field gives a temporary colour-by, and `degree > 5`
   highlights its matches.
7. **Provenance** (medium): the hover tooltip says "color ← cell [12]:
   `colorize(dept)`", and hovering a cell highlights what it changed.
8. **Preview a command's effect** (medium–large): run it, show the change as
   a ghost overlay, roll it back.
9. **Stale links and truncation** (small): tag output with its graph; link
   all members of large groups; fix `_suggest`.
10. **Live watched results** (small–medium): pin a watched cell as a docked
    live view, or re-run it when the selection changes.

Also: selection in edge tables; linking help examples to a preview; a
history scrubber that highlights what each undo step touches.

---

# Status

Started 2026-11-10; the first four items were done 2026-11-11, with tests
(`py/tests/test_queries_v2.py`, `py/tests/test_linked_output.py`,
`web/e2e/linking.spec.ts`).

1. ✅ **Wrong-answer bugs.**
   - `3 < degree < 6` is the intersection of its parts.
   - `and`, `or` and `not` combine sets when used as values. In the test of
     an `if`, `while`, conditional expression, `assert` or comprehension
     filter they stay plain Python.
   - `field in (...)` / `not in` is a membership query (`Field.isin`).
   - `dept == "x" & degree > 3` gives a "put each comparison in
     parentheses" error.
   - `_suggest` no longer suggests the misspelt name itself, or anything
     when the object is missing (None).
   - Found on the way and fixed: a number compared with an integer field
     was rounded first (`degree < 4.75` meant `degree < 4`).
2. ✅ **Linked output.**
   - Dicts, sets and frozensets of elements link, entry by entry.
   - f-strings compile to `LinkedStr`: an ordinary `str`, with the nodes,
     edges and sets in it linked when printed.
   - Groups longer than 500 link every member (shown or not).
   - Objects with their own summary (e.g. `offspring()`) keep it, and link
     every element they hold.
3. ✅ **Two-way highlighting.**
   - Hovering the graph, a chart mark, a table row or a legend row marks the
     console output, table rows, legend rows and chart marks that mention
     the same elements. This works even when graph highlighting is off.
   - Chart bars select on click (shift adds). Right-click opens the element
     menu, which acts on the bar's query: histogram bins and `plotSizes`
     bars carry one.
   - The `outbreaks()` histogram links each bar to the people its runs
     started from.
4. ✅ **Aggregates and `highest`/`lowest`.**
   - Reading a field from a set gives `Values`, with `.avg`, `.mean`,
     `.sum`, `.min`, `.max`, `.median`, `.count` and `.distinct`.
   - Fields are iterable (`max(degree)`) and have `.median` and `.count`.
   - `highest(field, k)` and `lowest(field, k)`; `sortBy(..., descending=true)`.
   - Named `highest`/`lowest`, not `top`, because `top` is a common variable
     name in the recipes.
   - The Epidemiology book uses them.

Decided 2026-11-11 and done:

- **Renames (O), outright, old scripts may break.**
  - One shared helper (`model.as_field`) turns an argument into a field. It
    accepts a field or its name, computes a not-yet-used computed field
    (`"pagerank"`), and suggests close names. Commands, charts, glyphs,
    igraph, Graphviz, layouts and styles all use it.
  - Arguments follow the conventions now in Appendix B of the manual:
    `field`; `x`/`y`; `smallest`/`largest` for sizes; `start`/`end` for
    colours; `count`; `node`; `iterations`; `addNodeField(name, type,
    default)`.
  - `pieOff` is now `removePies` and `unbundleEdges` is `removeBundles`;
    `biComponentCluster` is removed.
  - Manual Appendix C lists every rename. Two workarounds in the core
    cookbook are simplified.
- **`-` (D): kept as the 2006 edge operator.** `-=` now does the same, and
  the result's label points to `a.difference(b)`.
- **Reserved names (J), points 1–4.**
  1. Nodes and fields named after Python builtins don't hide them.
  2. Errors say what kind of name it is.
  3. An explicit import replaces a command for the session, with a note;
     `del` brings the command back. The graph `g` can never be replaced.
  4. `for` loop variables may reuse node names for the cell.
  - Plain assignments to commands and colours are still errors (point 5,
    not done).

Done 2026-11-11 (linking list items 2, 6, 7 and part of 9), with tests in
`py/tests/test_linked_output.py` and `web/e2e/linking.spec.ts`:

- **Stale output.** Output is tagged with the graph it was made from (a
  counter bumped on every load or switch). Output from an earlier graph is
  greyed out and unlinked.
- **Insert as code.** Alt-click a node in the graph, a table row, a legend
  row, a chart bar or anything in the output, or use the menu's *Insert as
  code*. You get a name, a query, `sel` or a short tuple; larger sets are
  bound to `picked1`, `picked2`, ….
- **Provenance.**
  - Each recorded cell notes which elements and aspects (color, size,
    position, label, …) it changed.
  - The node and edge tooltip lists them (`color ← [12] colorize(dept)`).
  - Hovering a cell number highlights everything that cell changed.
  - The menu's *Show the code that changed it* scrolls to and flashes the
    cell.
  - Undo forgets what the undone cell did.
- **Hovering executed code.**
  - Names and queries in executed code are evaluated now, side-effect free
    (no calls; the worker's `peek` checks the syntax tree).
  - A variable or query highlights its members; a comparison chain is taken
    whole.
  - A field shows its values and previews colouring by it: temporary
    renderer colours, nothing changed.
  - A plain value shows its value.
- **Distinct values** (suggested by the user). `dept.distinct` (and
  `set.field.distinct`) prints values that link to the elements having
  them. Right-click or alt-click acts on `dept == value` for the whole
  field.

Done 2026-11-11, the small and medium items (tests in
`py/tests/test_small_batch.py` and `web/e2e/linking.spec.ts`):

- **Small.**
  - `;` at the end of a line hides the echo.
  - A set of many groups prints compactly, still linked
    (`21 groups: [dept0: 28] …`).
  - `Node.score = 0` makes a field, typed by its default.
  - `set.where(fn)` filters to a set.
  - Colours compare by meaning (`n.color == red`) and vary
    (`.alpha() .lighter() .darker()`); colour fields read back as colours.
  - A note when a query can't match because of its type (once per field).
  - Writing an unknown field suggests a close name.
  - Tracebacks leave out the runtime helper frames.
  - "communities", not "communitys".
  - The `groupAndSortBy` docs are corrected.
  - Louvain writes `louvain_class` (was `modularity_class`).
  - `n.class_` reaches a field named after a Python keyword.
- **Medium.**
  - `with scratch():` (used in the Epidemiology and Ecology books).
  - Line charts give a readout at the pointer; on the `spread` chart,
    pointing highlights who was reached by then and a click selects them
    (chart field `xq`).
  - The edge table marks the edges between selected nodes.
  - Charts mark each other's bars.
  - `n in set` is a cached hash lookup.

Done 2026-11-11 (the rest of the list, except previews):

- **Live watched results (10).** *Pin* moves a watched cell's live output
  into a side panel; watched cells that use `sel` re-run when the display
  selection changes.
- **History scrubber.** *Edit → History…*: a slider and list over the undo
  history; moving undoes or redoes to that point and highlights each step
  crossed; hovering a step highlights what it changed.
- **Brushing.** Dragging across bars selects all of them (the query is the
  bars' queries joined with `|`).
- **The data table** scrolls to an element hovered elsewhere.
- **Errors** link the nodes and edges they name.
- **Java-era names removed:** `Types`, `Integer` and the other Java type
  names, `Morpher`, `InfoWindow`/`infowindow`, `getAppletContext`, the
  display object `v` (`lastClick()` replaces `v.getLastClickedPosition()`),
  `readjustEdges`, `setSynchronous`, and the `exportSWF/JAVA/CGM/EMF` stubs.
  `NodeEditorPopup` and friends stay: they are the API for adding menu items.

Also added (requests on 2026-11-11):

- **Gython in the data table's filter box.** Queries filter as you type;
  expressions with calls run on Enter, isolated (their changes are reverted).
- **The element menu on table rows** (right-click; several selected rows at
  once), an *Actions ▾* button for the selected or shown rows, and *Select* /
  *Add to selection (sel)* in every element menu.
- **The Cluster tool**: one lasso per cluster into a field (default
  `cluster`, else `cluster1`, …; an existing field can be cleared first),
  relabelling by default, ids counting up (or typed), labelled/left shown as preview
  colours and counts; each lasso is an undoable `labelCluster(...)`.

- **Altair charts** (`nodeData`, `edgeData`, `showChart`; a cell whose
  value is a chart shows it in the dock). Marks link to their element, or
  through the query they're grouped by; brushes select; the graph's hover
  fades unrelated points. Recipes in the Core, SNA and Epidemiology books.
- **Live charts**: *● Live* on a chart (or `liveCharts()`) recomputes it,
  isolated, after every change, undo and history move.

- **demo()**: a 17-step guided tour (Basic → Intermediate → Advanced) in a
  panel below the graph; each step runs as a console cell. The code box's
  hint suggests `demo()` on a first visit, then rotates commands that suit
  the graph showing (its own fields and node names).

Still open: previews of a command's effect (8), and linking help examples to
a preview.
