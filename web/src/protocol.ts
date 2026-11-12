// Messages exchanged between the UI thread and the Python worker.

export interface NodeRec {
  i: number; name: string;
  x: number; y: number; w: number; h: number;
  c: number; a: number; s: number; sc: number;
  l: string; lv: boolean; lc: number; v: boolean;
  img: string | null;
  /** 1 if this node is a collapsed group (meta-node) */
  m?: number;
  /** pie slice sizes (see Overlay.pie) */
  p?: number[];
  /** label position when not "right": left, above, below, inside, outside (GUESS picks a free side) */
  lp?: string;
  /** label size as a scale (absent: 1) */
  ls?: number;
  /** line style (absent: solid) and arrowhead (absent: triangle); see edgestyles.ts */
  st?: string;
  ah?: string;
}

export interface EdgeRec {
  i: number; s: number; t: number; d: boolean;
  c: number; a: number; w: number; v: boolean;
  l: string; lv: boolean; lc: number;
  /** bend points [x0, y0, x1, y1, ...] (centre coordinates), if routed */
  b?: number[] | null;
  /** label size as a scale (absent: 1) */
  ls?: number;
  /** line style (absent: solid) and arrowhead (absent: triangle); see edgestyles.ts */
  st?: string;
  ah?: string;
}

/** Interpreter output: text, node, edge, or a (possibly annotated) group. */
export type Seg =
  | string
  | { n: number; t: string }
  /** ends: [id, name] of each end when t is "a-b" / "a->b" (each end links to its node) */
  | { e: number; t: string; ends?: [[number, string], [number, string]] }
  | { g: Seg[]; a?: string; x?: ["n" | "e", number][]; q?: string };   // q: a query naming the members   // x: more members, linked but not shown

/** sh: the shape around the group (absent: convex hull); rot: turned to fit; pad: room around the nodes */
export interface HullRec { i: number; nodes: number[]; c: number; a: number; sh?: "box" | "ellipse"; rot?: boolean; pad?: number }

/** k: node, edge or hull swatch; "x" a text-only line ("… 32 more") */
export interface LegendEntry {
  k: "n" | "e" | "h" | "x"; c: number; a: number; s?: number; w?: number; t: string;
  /** legendFor rows: the elements the row stands for (ik: "n" nodes, "e" edges)
   *  and a Gython expression for them (the right-click menu acts on it) */
  ids?: number[]; ik?: "n" | "e"; q?: string;
  /** hid: shown only when the legend is expanded; more: the "… N more" row that expands it */
  hid?: boolean; more?: boolean;
}

export interface LegendRec {
  i: number;
  entries: LegendEntry[];
  ramp?: { from: number; to: number; min: number; max: number; ticks?: number; stops?: [number, number][] };
}

export interface Overlay {
  type: "overlay";
  /** null: follow the light/dark theme */
  background: number | null;
  image: { url: string; x: number; y: number } | null;
  arrow: { length: number | null; width: number | null };
  /** 0 = straight edges; > 0 = every edge curves clockwise (Gephi preview style) */
  curvature: number;
  edgeColor?: "original" | "source" | "target" | "mixed";
  /** names of saved styles (defineStyle) */
  styles?: string[];
  /** pie-chart node slice colours (node records then carry `p`, the slice sizes) */
  pie?: number[] | null;
  borderWidth?: number;
  /** draw a node or edge on top once its appearance changes (raiseChanged()) */
  raiseChanged?: boolean;
  /** hoverFields(): the fields the tooltip shows at once, by kind (the rest after a moment) */
  hoverFields?: { n: string[]; e: string[] };
  /** labelled lines under the graph (hive plot axes) */
  guides?: { x1: number; y1: number; x2: number; y2: number; label: string }[];
  /** a map drawn under the graph (geoLayout): outlines as flat [x0, y0, x1, y1, …]
   * rings in graph coordinates; fill/stroke null = follow the theme */
  map?: { rings: number[][]; fill: number | null; stroke: number | null } | null;
  guidesNote?: string;
  /** context for semantic dragging (see main.ts dragBehaviour) */
  drag?: DragContext;
  labels?: { outline: boolean; cull: boolean; along?: boolean; placement?: string; screen?: boolean };
  hulls: HullRec[];
  legends: LegendRec[];
}

export interface Morph {
  duration: number;
  nodeAppearAfter: number; nodeDisappearBy: number;
  edgeAppearAfter: number; edgeDisappearBy: number;
}

/** children: containers (tabs, tab, group, row, column) */
export interface WidgetRec { id: string; kind: string; props: Record<string, unknown>; children?: WidgetRec[] }
/** a menu, toolbar or status bar entry: a widget, a built-in action or a separator */
export type BarItem = WidgetRec | { kind: "action"; name: string; text?: string } | { kind: "sep" };
export interface PanelRec extends WidgetRec { children: WidgetRec[] }

export interface ChartMsg {
  type: "chart"; id: string; kind: "bar" | "pie" | "distrib" | "line";
  /** live: recomputed after every change; canLive: it knows how it was made */
  live?: boolean; canLive?: boolean;
  title: string; xlabel: string; ylabel: string;
  items: { label: string; value: number; color: number; ids: ["n" | "e", number][]; q?: string }[];
  /** line charts: a query for the elements at a point, with {x} for its x value
   *  (spread: "(infected_at >= 0) & (infected_at <= {x})") */
  xq?: string;
  /** line charts: one polyline per series, x and y in data units */
  series?: { name: string; color: number; points: [number, number][] }[];
}

export type UiMsg =
  | { type: "ui"; op: "dock"; panel: PanelRec }
  | { type: "ui"; op: "update"; id: string; props: Record<string, unknown> }
  | { type: "ui"; op: "close"; id: string }
  | { type: "ui"; op: "events"; enabled: string[]; defaults: { highlight: boolean; zoom: boolean; edgeHighlight?: boolean; edgeZoom?: boolean } }
  /** context-menu items added from Python (NodeEditorPopup.addItem); scope n, e or ne */
  | { type: "ui"; op: "menu"; items: { id: string; label: string; scope: "n" | "e" | "ne" }[] }
  | { type: "ui"; op: "timer"; id: string; ms: number; repeat: boolean }
  | { type: "ui"; op: "cancelTimer"; id: string }
  | { type: "ui"; op: "status"; text: string }
  | { type: "ui"; op: "open"; url: string }
  /** apps: the window's regions, menu bar, toolbar, status bar, title and console */
  | { type: "ui"; op: "regions"; sizes: Record<string, number> }
  | { type: "ui"; op: "menubar"; menus: { title: string; items: BarItem[] }[]; keep: string[] }
  | { type: "ui"; op: "toolbar"; items: BarItem[] }
  | { type: "ui"; op: "statusbar"; items: BarItem[] }
  | { type: "ui"; op: "title"; text: string; subtitle: string | null }
  | { type: "ui"; op: "console"; mode: "hidden" | "toggle" | "shown" };

/** What a hovered name or query in executed code means now. */
export interface PeekInfo {
  title: string;
  lines: string[];
  items: ["n" | "e", number][];
  /** colouring by a hovered field, shown while hovering: [id, 0xRRGGBB] */
  colors?: { n?: [number, number][]; e?: [number, number][] };
}

export interface Info {
  title: string;
  rows: [string, string][];
  /** which console cells last changed it: [aspect, cell, code] (newest first) */
  prov?: [string, number, string][];
}

export type FromWorker =
  | { type: "status"; text: string }
  | { type: "ready"; interruptible: boolean }
  | { type: "scene"; nodes: NodeRec[]; edges: EdgeRec[]; gid?: number; gname?: string }
  | { type: "patch"; nodes: NodeRec[]; edges: EdgeRec[]; removedNodes: number[]; removedEdges: number[]; morph?: Morph; pos?: number[] }
  | { type: "out"; segs: Seg[]; gid?: number }
  | { type: "text"; text: string }
  /** summary: one line (with a "did you mean" hint); line: the cell line it happened on */
  /** an Altair (Vega-Lite) chart for the dock; cell: the console cell that made it */
  | { type: "vega"; id: string; title: string; spec: any; cell: number | null; fields: { n: string[]; e: string[] };
      live?: boolean; canLive?: boolean }
  /** a chart stopped (or started) being live */
  | { type: "liveState"; id: string; live: boolean }
  /** demo(): the guided tour's steps, starting at `at` */
  | { type: "demo"; steps: { level: string; title: string; text: string; code: string; notice: string }[]; at: number }
  | { type: "error"; text: string; summary?: string; line?: number;
      /** the summary with the nodes and edges it names linked; gid: the graph they belong to */
      segs?: Seg[]; gid?: number }
  | { type: "help"; topic: string | null }
  | { type: "slides"; slides: { note: string }[]; index: number | null }
  /** move the camera: [centre x, centre y, zoom] in graph coordinates */
  | { type: "camera"; camera: number[]; ms: number }
  /** installPackage(): the page asks the worker to pip-install it */
  | { type: "install"; name: string }
  /** the session's graphs (tabs above the graph when there are several) */
  | { type: "graphs"; names: string[]; current: string }
  | { type: "table"; kind: "n" | "e"; ids: number[] | null }
  | { type: "center"; nodes: number[]; edges: number[] }
  | Overlay
  | ChartMsg
  | { type: "movie"; op: "start"; fps: number; name: string }
  | { type: "movie"; op: "stop" }
  /** startImages()/stopImages(): script exports go into one zip instead of separate downloads */
  | { type: "images"; op: "start"; name: string }
  | { type: "images"; op: "stop" }
  | UiMsg
  | { type: "image"; key: string; url: string }
  /** b64: binary content (exportSHP's zip), base64; text is then empty */
  | { type: "download"; name: string; text: string; b64?: string }
  /** connectAssistant(): open (or close) the MCP bridge's WebSocket */
  | { type: "assistant"; op: "connect" | "disconnect"; url?: string }
  /** optimizeLabels(): simulated annealing over label positions in the renderer */
  | { type: "labels"; op: "optimize"; ms: number }
  /** excentricLens(): the lens tool on or off, and its options */
  | { type: "lens"; on: boolean; radius?: number; auto?: boolean; max?: number }
  | { type: "select"; nodes: number[] }
  /** undo()/redo() reversed or re-applied the command run in console cell `cell` */
  | { type: "undone"; cell: number; undone: boolean }
  | { type: "export"; format: "png" | "jpg" | "svg" | "gif" | "pdf" | "ps" | "eps"; name: string }
  | { type: "done"; id: number; ok: boolean }
  | { type: "reply"; id: number; value: unknown };

export type ToWorker =
  | { type: "init"; files: Record<string, string>; data: Record<string, string>;
      /** datasets fetched on first read (name -> absolute URL): the cookbooks' data */
      lazy?: Record<string, string>; interrupt?: SharedArrayBuffer }
  /** quiet: a watched cell refreshing (not added to history or undo) */
  | { type: "run"; id: number; code: string; echo?: boolean; cell?: number; quiet?: boolean }
  | { type: "complete"; id: number; code: string }
  | { type: "completions"; id: number; text: string }
  | { type: "docs"; id: number }
  | { type: "snapshot"; id: number; since: number }
  | { type: "event"; id: number; target: string; name: string; value: string }
  | { type: "describe"; id: number; kind: "n" | "e"; ident: number }
  | { type: "cellChanges"; id: number; cell: number }
  | { type: "peek"; id: number; expr: string }
  /** the history scrubber: list the undo steps, a step's elements, move to a position */
  | { type: "historySteps"; id: number }
  | { type: "historyItems"; id: number; step: number }
  | { type: "historyGoto"; id: number; at: number }
  /** filter the data table with a Gython expression (full: run calls too, isolated) */
  | { type: "tableQuery"; id: number; expr: string; kind: "n" | "e"; full: boolean }
  /** the Cluster tool: which nodes are labelled in a field */
  | { type: "clusterInfo"; id: number; field: string }
  /** make a chart live (recomputed after every change) or not */
  | { type: "live"; id: number; chart: string; on: boolean }
  | { type: "assign"; id: number; name: string; items: ["n" | "e", number][] }
  /** nodes dragged on the display, as [id, x, y, id, x, y, ...] (one undo step) */
  | { type: "select"; nodes: number[] }
  | { type: "install"; name: string }
  /** the last click on the graph, in graph coordinates */
  | { type: "click"; x: number; y: number }
  | { type: "writeFile"; id: number; name: string; data: Uint8Array }
  /** help index, field summaries (filters/style panel) or data-table rows */
  | { type: "query"; id: number; what: "help" | "fields" | "table" | "workspace" | "timeline" | "suggest" | "summary"; kind?: string; ids?: number[] | null };

export interface DragContext {
  /** circleLayout(): nodes slide around the ring and reorder */
  ring?: { cx: number; cy: number; r: number; ids: number[] };
  /** scatterLayout(x, y): dragging edits the two fields */
  axes?: { x: string; y: string; x0: number; sx: number; y0: number; sy: number; h: number;
           xint: boolean; yint: boolean; xedit: boolean; yedit: boolean };
}
