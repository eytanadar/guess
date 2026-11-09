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
}

export interface EdgeRec {
  i: number; s: number; t: number; d: boolean;
  c: number; a: number; w: number; v: boolean;
  l: string; lv: boolean; lc: number;
  /** bend points [x0, y0, x1, y1, ...] (centre coordinates), if routed */
  b?: number[] | null;
}

/** Interpreter output: text, node, edge, or a (possibly annotated) group. */
export type Seg =
  | string
  | { n: number; t: string }
  | { e: number; t: string }
  | { g: Seg[]; a?: string };

export interface HullRec { i: number; nodes: number[]; c: number; a: number }

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
  ramp?: { from: number; to: number; min: number; max: number; ticks?: number };
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
  /** labelled lines under the graph (hive plot axes) */
  guides?: { x1: number; y1: number; x2: number; y2: number; label: string }[];
  guidesNote?: string;
  /** context for semantic dragging (see main.ts dragBehaviour) */
  drag?: DragContext;
  labels?: { outline: boolean; cull: boolean };
  hulls: HullRec[];
  legends: LegendRec[];
}

export interface Morph {
  duration: number;
  nodeAppearAfter: number; nodeDisappearBy: number;
  edgeAppearAfter: number; edgeDisappearBy: number;
}

export interface WidgetRec { id: string; kind: string; props: Record<string, unknown> }
export interface PanelRec extends WidgetRec { children: WidgetRec[] }

export interface ChartMsg {
  type: "chart"; id: string; kind: "bar" | "pie" | "distrib";
  title: string; xlabel: string; ylabel: string;
  items: { label: string; value: number; color: number; ids: ["n" | "e", number][] }[];
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
  | { type: "ui"; op: "open"; url: string };

export interface Info { title: string; rows: [string, string][] }

export type FromWorker =
  | { type: "status"; text: string }
  | { type: "ready"; interruptible: boolean }
  | { type: "scene"; nodes: NodeRec[]; edges: EdgeRec[] }
  | { type: "patch"; nodes: NodeRec[]; edges: EdgeRec[]; removedNodes: number[]; removedEdges: number[]; morph?: Morph; pos?: number[] }
  | { type: "out"; segs: Seg[] }
  | { type: "text"; text: string }
  /** summary: one line (with a "did you mean" hint); line: the cell line it happened on */
  | { type: "error"; text: string; summary?: string; line?: number }
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
  | UiMsg
  | { type: "image"; key: string; url: string }
  | { type: "download"; name: string; text: string }
  | { type: "select"; nodes: number[] }
  /** undo()/redo() reversed or re-applied the command run in console cell `cell` */
  | { type: "undone"; cell: number; undone: boolean }
  | { type: "export"; format: "png" | "jpg" | "svg" | "gif" | "pdf" | "ps" | "eps"; name: string }
  | { type: "done"; id: number; ok: boolean }
  | { type: "reply"; id: number; value: unknown };

export type ToWorker =
  | { type: "init"; files: Record<string, string>; data: Record<string, string>; interrupt?: SharedArrayBuffer }
  /** quiet: a watched cell refreshing (not added to history or undo) */
  | { type: "run"; id: number; code: string; echo?: boolean; cell?: number; quiet?: boolean }
  | { type: "complete"; id: number; code: string }
  | { type: "completions"; id: number; text: string }
  | { type: "docs"; id: number }
  | { type: "snapshot"; id: number; since: number }
  | { type: "event"; id: number; target: string; name: string; value: string }
  | { type: "describe"; id: number; kind: "n" | "e"; ident: number }
  | { type: "assign"; id: number; name: string; items: ["n" | "e", number][] }
  /** nodes dragged on the display, as [id, x, y, id, x, y, ...] (one undo step) */
  | { type: "select"; nodes: number[] }
  | { type: "install"; name: string }
  /** the last click on the graph, in graph coordinates */
  | { type: "click"; x: number; y: number }
  | { type: "writeFile"; id: number; name: string; data: Uint8Array }
  /** help index, field summaries (filters/style panel) or data-table rows */
  | { type: "query"; id: number; what: "help" | "fields" | "table" | "workspace" | "timeline"; kind?: string; ids?: number[] | null };

export interface DragContext {
  /** circleLayout(): nodes slide around the ring and reorder */
  ring?: { cx: number; cy: number; r: number; ids: number[] };
  /** scatterLayout(x, y): dragging edits the two fields */
  axes?: { x: string; y: string; x0: number; sx: number; y0: number; sy: number; h: number;
           xint: boolean; yint: boolean; xedit: boolean; yedit: boolean };
}
