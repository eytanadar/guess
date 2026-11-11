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

Started 2026-11-10, with the four items below. Each is marked done when it
lands, with its tests.

1. **Wrong-answer bugs:** chained comparisons, `and`/`or`/`not` on sets,
   `field in (...)`, the `&` precedence hint and `_suggest`.
2. **Linked output:** dicts, sets and f-strings.
3. **Two-way highlighting,** clickable chart bars, and ids on the
   `outbreaks` histogram.
4. **Aggregates and `top()`:** `s.degree.avg` and friends, iterable fields,
   `top(field, k)`.

Waiting for a decision: argument renames (O), the meaning of `-` (D), and
loosening reserved names (J).
