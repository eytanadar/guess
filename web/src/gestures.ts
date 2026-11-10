// The "Mouse and gestures" guide: every direct-manipulation element, with a
// screenshot (public/help/*.png, made by demo/gesture-shots.mjs).

export interface Gesture {
  id: string;
  title: string;
  /** what you do (keys and mouse) */
  how: string;
  /** what happens, and the Gython it writes, if any */
  what: string;
  /** screenshot in public/help/ (without extension) */
  img?: string;
  /** when the gesture is available, if not always */
  when?: string;
}

export const GESTURE_SECTIONS: { title: string; items: Gesture[] }[] = [
  {
    title: "Moving around",
    items: [
      { id: "pan", title: "Pan and zoom", how: "Drag the background · scroll or pinch · double-click the background",
        what: "Moves the view, zooms around the pointer, and fits the whole graph (View → Fit graph does too). Double-clicking a node zooms to it." },
      { id: "hover", title: "Hover for details", how: "Point at a node or edge",
        what: "Shows its fields in a tooltip and highlights it in the console output, the data table and any charts. An edge also rings its two endpoints.", img: "hover-edge" },
    ],
  },
  {
    title: "Selecting",
    items: [
      { id: "focus", title: "Focus on a neighbourhood", how: "Click a node (Select tool) · click it again or press Esc to clear",
        what: "Keeps the node and its neighbours bright, labels them, and dims everything else.", img: "focus" },
      { id: "box", title: "Box selection", how: "Shift-drag on the background · add Cmd/Ctrl to add to the selection",
        what: "Selects the nodes inside the box. The selection is the variable sel in the console (sel.color = red, showOnly(sel)).", img: "box" },
      { id: "lasso", title: "Lasso selection", how: "Alt/Option-drag on the background",
        what: "Selects the nodes inside a freehand outline.", img: "lasso" },
      { id: "toggle", title: "Add or remove one node", how: "Shift-click a node",
        what: "Adds it to the selection, or takes it out. Esc or a click on the background clears the selection." },
      { id: "output", title: "Select from the console", how: "Hover, click or right-click linked output in the console",
        what: "Hovering highlights the nodes and edges a result refers to; clicking selects them and zooms to them; right-click opens a menu (colour, size, labels, hide, assign to a variable).", img: "output" },
    ],
  },
  {
    title: "Dragging with meaning",
    items: [
      { id: "move", title: "Move nodes", how: "Drag a node · drag any node of a selection to move them all",
        what: "Moves it (or the whole selection). Each drag is one undo step, recorded as a command (v12.x = …; v12.y = …) that history() and saved logs include; View → Show node moves in the console shows them." },
      { id: "ring", title: "Reorder a circle", when: "after circleLayout()",
        how: "Drag a node around the circle",
        what: "The node stays on the ring and the others make room; dropping it runs ringMove(node, position).", img: "ring" },
      { id: "edge", title: "Draw an edge", how: "Alt/Option-drag from one node to another",
        what: "A rubber band snaps to the nearest node; releasing adds the edge with addEdge(a, b).", img: "edge" },
      { id: "scatter", title: "Edit values by position", when: "after scatterLayout(xfield, yfield)",
        how: "Drag a node in the scatter plot",
        what: "The status bar shows the values under the pointer; dropping sets both fields (when they are editable).", img: "scatter" },
      { id: "expand", title: "Expand a group", when: "after collapse(…) or collapseBy(field)",
        how: "Double-click a collapsed group (drawn with a thick border)",
        what: "Brings its members back where they were, as expand(group).", img: "expand" },
    ],
  },
  {
    title: "Click tools (toolbar)",
    items: [
      { id: "path", title: "Shortest path", how: "Choose Path, then click two nodes",
        what: "Colours a shortest path between them, with the colour beside the tools: shortestPath(a, b).color = …", img: "path" },
      { id: "heat", title: "Heat map", how: "Choose Heat, then click a node",
        what: "Colours every node by its distance from that node, red (near) through violet to blue (far), grey if unreachable (heatMap(node)); the distance is stored in the hops field.", img: "heat" },
      { id: "paint", title: "Paint", how: "Choose Paint, then click nodes · shift-click paints the neighbours too",
        what: "paint(node, colour) or paint(node, colour, 1)." },
      { id: "lens", title: "Excentric lens", how: "Choose ◎ Lens (or press L), then point at nodes · wheel resizes · Shift+wheel scrolls · click pins it",
        what: "Lists the labels of the nodes under the lens beside it, joined by lines, with a bar chart by colour. Pinned, click a label to select its node (Shift: add), click bars to filter, and Select N takes them all. Esc releases it." },
    ],
  },
  {
    title: "Panels",
    items: [
      { id: "table", title: "Data table", how: "View → Data table · click a row · double-click a cell",
        what: "Rows follow the selection both ways; double-clicking a name zooms to it; editing a cell runs v.field = value.", img: "table" },
      { id: "filter", title: "Filters", how: "View → Filter panel · drag the range handles, tick values",
        what: "Hides what doesn't match by running showOnly(…); Show all brings everything back.", img: "filter" },
      { id: "timeline", title: "Timeline", how: "View → Timeline · drag the slider or press ▶",
        what: "Shows the graph at a moment, from ranges or a numeric field such as year; Keep records the moment as showTime(…).", img: "timeline" },
      { id: "slides", title: "Presentation", how: "View → Presentation · ← → step through slides",
        what: "Add slide saves the graph and the view with a note; stepping morphs between them." },
    ],
  },
  {
    title: "Keyboard",
    items: [
      { id: "keys", title: "Shortcuts", how: "Shift+Enter run · Cmd/Ctrl+K search · F1 help · Cmd/Ctrl+Z undo (outside the code cell) · Shift+Cmd/Ctrl+Z redo · Esc interrupt or clear · Shift+Cmd/Ctrl+F find in output · Shift+↑↓ history",
        what: "Every gesture above writes Gython into the console, so it can be read, undone and run again." },
    ],
  },
];

export const GESTURES: Gesture[] = GESTURE_SECTIONS.flatMap((s) => s.items);
