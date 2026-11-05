# Declarative dragging: what it is and what GUESS could take from it (2026-11-05)

Sources: <https://declarative-dragging.github.io/>, the
[dragology](https://github.com/declarative-dragging/dragology) repository, and
the paper (Horowitz, Blinn and Heer, "Declarative Dragging", UIST 2026).

## The idea

Today, dragging in most tools means "move this thing to where the pointer is".
In declarative dragging, the view is a pure function from model state to
picture. For each draggable element, the author declares **which model states
dragging it can lead to**. The engine renders those candidate states, finds
where the dragged element would be in each, and builds the interaction from
that: it follows the pointer, previews, snaps and animates the drop.

Dragology (MIT, TypeScript, React + SVG; npm 0.1.x) provides combinators:

- `between(states)`: interpolate the whole picture between discrete states,
  using where the dragged element sits in each.
- `closest(specs)`: follow whichever option puts the element nearest the pointer.
- `vary(state, params, {constraint})`: change numeric parameters continuously.
  An optimiser (COBYLA) picks the values that put the element under the pointer.
- Drop targets, fixed elements, "float near targets, snap to islands",
  `switchToStateAndFollow` (e.g. start dragging a new edge), and drop/branch
  transitions.

The authors note these limits:
- Drag-start cost grows with the square of the number of candidate states.
- Drop targets must not overlap.
- It handles one pointer at a time.
- SVG's transform model is the natural target; Canvas/WebGL is not.

## Fit with GUESS

Use the idea, not the library. GUESS draws with PixiJS, and its model lives in
Python, which can't be re-run at drag speed. Every GUESS drag can still be made
"declarative" by working out its candidate states at drag start (in JS, from
data Python already sent). The drag then follows the pointer through those
states, and on drop runs **one Gython command**, which keeps it visible,
undoable and scriptable. The small reusable parts (closest, between and a 1–2
parameter optimiser) are easy to write; the MIT code in `src/math` could be
borrowed.

## Ideas, ranked by value for effort

1. **Drop a node on a group to change its field.** Dragging a node near a
   convex hull, a legend entry or a coloured cluster snaps it in. On drop,
   `v12.dept = "dept3"` runs, and colour and hull follow. This is direct
   manipulation for Gython's most common operation: categorical editing.
   (`closest(hull states)` + `whenFar(free move)`.)
2. **Slide along the layout's geometry.** In circle and radial layouts a
   dragged node stays on its ring and slots into a new position in the order.
   In Sugiyama it moves within its layer, and a live crossing count shows
   whether the reorder helps. On drop the layout is re-run with that order
   pinned. (`vary(angle)` / `closest(orderings)`.)
3. **Scrub between saved states.** Grabbing a node while holding a modifier
   blends the whole graph between saved states (`ss`), following that node's
   positions in each. This reuses the morph interpolation; releasing runs
   `ls(state)` or leaves a blend. (`between(states)`.)
4. **Drag from node to node to create an edge (Alt-drag).** A rubber-band edge
   snaps to the nearest candidate target and, on drop, runs
   `addEdge(v1, v7)`. (`switchToStateAndFollow` + `closest(nearest k)`.)
5. **Attribute axes.** When a layout maps a field to x or y (a scatter of two
   fields), dragging a node edits those field values within their range,
   becoming a direct-manipulation data editor. (`vary(field)` with bounds.)
6. **Drag to set layout parameters.** Dragging any node outward in a radial
   layout changes the ring spacing; dragging a pinned anchor in a force layout
   changes edge length or gravity. This needs a closed-form JS position
   function, so only for analytic layouts. (`vary(param)`.)
7. **Filter handles on the graph.** Histogram range handles (already in the
   Filter panel) could preview what they would hide while dragging. This is
   modest extra value over plain sliders.

Pitfalls to design around:
- Limit candidates to the nearest few targets, since the cost grows
  quadratically.
- Disambiguate targets that overlap on screen in dense regions.
- Turn off ordinary drag-to-move while a semantic drag is active.
- Never call Python during a drag, only on drop.

## Recommendation

Prototype idea 1 (drop on a group) and idea 2 (slide on circle/radial rings).
They need only a candidate-state picker in `renderer.ts` and a drop-time
Gython command, and they give GUESS something no other graph tool has:
editing data and layout by dragging, recorded as reproducible code.

## Implemented (2026-11-05)

Each drag works out its candidate states when it starts (in `main.ts`
`dragBehaviour`, from the `drag` context Python sends with the overlay). It
follows the pointer through them, with snapping, a preview of other nodes and a
highlight ring. On drop it runs **one** Gython command, so the change shows in
the console, can be undone and can be re-run. The renderer's `DragBehaviour`
interface (`move(world x, y) → frame`, `drop(frame)`) is the reusable core.

| gesture | when | on drop |
|---|---|---|
| drag a node into another group | after `colorize(field)` or `legendFor(field)` on a node field | `v.field = value; v.color = …; v.x = …; v.y = …` |
| drag a node around the circle | after `circleLayout()` (others make room as you drag) | `ringMove(v, k)` |
| Alt-drag from a node to another | always | `addEdge(a, b)` |
| drag a node in a scatter plot | after `scatterLayout(xfield, yfield)` (editable fields only) | `v.x_field = …; v.y_field = …` |

Dragging a node that belongs to a multi-node selection still moves the whole
selection, and any other drag is a plain move. Not built: scrubbing between
states by dragging (the Timeline and Presentation panels cover this), Sugiyama
layer reordering, and dragging to set layout parameters.
