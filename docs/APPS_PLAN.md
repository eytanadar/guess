# Plan: GUESS apps

## Status (November 2026)

Decisions: no Cytoscape or Gephi presets or close copies; example apps for
cookbook domains instead. Delivery starts with `?app=<manifest>` and is kept
simple. Whether users may open the console is the author's choice. GUESS
keeps its own look, with no property-table style editor.

**Built:**
- the manifest and `?app=` loading, with a trust prompt for other sites, and the console opening when the script fails;
- console modes (`hidden`, `toggle` with Ctrl+`, `shown`) and the theme;
- `ui.layout` (left, right and bottom regions, with draggable edges and sizes);
- `Tabs`/`Tab`, `Group`, `Row`, `Column`, `Markdown`, `View`, and live `Label`/`Markdown` given a function;
- `ui.menubar` (`Menu`, `MenuItem`, `Action`, `keep=`), `ui.toolbar`, `ui.statusbar`, `ui.title` and `ui.console`;
- three example apps in `web/public/apps/` (Interactome Explorer, Airport Disruption, Outbreak Explorer), under *Help → Example apps*;
- the manual's *Apps* section, plus notes in the three cookbooks' capstones.

**Not built (from the plan below):**
- presets (dropped);
- workspaces and `ui.saveLayout()`;
- the overview mini-map and the align/distribute tools;
- `Table`, `List` and `Tree` widgets (a `View("table")` covers the data table);
- folder bundles with `--app`, and an `exportApp` that writes a manifest.

An app is GUESS with its own interface. It's Gython code, and optionally data,
that runs when GUESS loads, with the console hidden and the window arranged
for one job: a Cytoscape-style workbench, a Gephi-style studio, or a small
tool for one question.

## What exists today

| piece | what it does | limit |
|---|---|---|
| `exportApp("x.guess", script)` and `?app=1` | saves the graph with a script that runs on load; hides the console | the layout is fixed (graph, plus panels docked below or to the right) |
| `Panel`, `Label`, `Button`, `Slider`, `Checkbox`, `Dropdown`, `TextField` | small panels in the dock | no tabs, tables, lists or trees; only bottom and right |
| `graphevents`, `NodeEditorPopup.addItem` | click handlers, right-click menu items | no menu bar or toolbar control |
| the data table, style, filter, variables and history panels | built-in views | not placeable by code |
| share and viewer links, `exportHTML` | sharing | `exportHTML` has no Python |

## What an app needs (from the Cytoscape screenshot)

- **A window divided into regions.** A Control Panel on the left (tabs:
  Network, Style, Select), a Tool Panel under it, the graph in the centre,
  a Table Panel below (tabs: Node, Edge and Network Table), and an overview
  in a corner.
- **Its own menu bar and an icon toolbar.**
- **Built-in views placed anywhere:** the graph, tables, style editor,
  filters, legend, overview.
- **Custom panels mixed in:** Node Layout Tools (scale, align, distribute,
  rotate).
- **A status line.**
- **No console**, but developers can bring it back.

## Design

### 1. The app package

The app is a manifest plus a script, plus any data files:

```json
{
  "guess-app": 1,
  "name": "PPI Workbench",
  "icon": "logo.svg",
  "theme": {"mode": "light", "accent": "#2f6fde"},
  "console": "hidden",
  "script": "main.gy",
  "data": ["brca1-intact.gdf"],
  "open": "brca1-intact.gdf"
}
```

- **What `console` means:**
  - `"hidden"` takes the console away;
  - `"toggle"` lets anyone open it with Ctrl+`;
  - `"dev"` lets it open only with `?dev=1`.
- **Ways to deliver an app:**
  1. **A hosted GUESS plus a link:** `index.html?app=https://…/manifest.json`. The data is fetched into the Python file space when the app first reads it, as the cookbook data is now.
  2. **A static folder:** `npm run bundle -- --app myapp/` builds a site with the app preloaded and no `?app=` needed. `--offline` includes the Python runtime, as the existing bundle option does.
  3. **A single `.guess` file:** what `exportApp` makes today, extended with the manifest fields. It suits sharing by email.
- **Trust:** an app from another site runs code, but only inside the page's Python sandbox. GUESS asks once ("Run app X from site Y?") unless the app comes from the page's own site.

### 2. Layout: regions, splitters and tabs

A Python API, so the same code works in a script or the console:

```python
ui.layout(
    left=Stack(
        Tabs(Tab("Network", NetworkList()), Tab("Style", StylePanel()), Tab("Select", FilterPanel())),
        Panel("Tool Panel", ScaleTools(), AlignTools(), RotateTools()),
        sizes=[3, 2]),
    center=GraphView(overview="bottom-right"),
    bottom=Tabs(Tab("Node Table", Table("nodes")), Tab("Edge Table", Table("edges"))),
    sizes={"left": 300, "bottom": 230},
)
```

- **Regions:** `top`, `left`, `center`, `right` and `bottom`. Each takes a view, a `Tabs`, a `Stack` (split vertically) or a `Row`, with draggable splitters. Sizes are remembered for each viewer.
- **Built-in views** that can be placed anywhere:
  - `GraphView` (optionally with an overview mini-map);
  - `Table(kind)` and `StylePanel()`;
  - `FilterPanel()`, `Legend()`, `HistoryPanel()` and `Console()`;
  - `Help()`, `Search()`, `Timeline()`, `NetworkList()` (the session's graphs) and `Charts()` (where charts dock).
- **Today's panels and charts** still work: `ui.dock(Panel(...))` goes to the region named by `position=`, which can now also be `"left"` or `"top"`.
- **Workspaces** (as in Gephi's Overview / Data Laboratory / Preview) switch between whole layouts:

  ```python
  ui.workspaces(Overview=layout1, Data=layout2, Preview=layout3)
  ```

- **Capturing a layout:** `ui.saveLayout()` writes out the code for the current arrangement, after you've dragged things into place, so designing a layout doesn't mean writing it by hand.

### 3. Menus, toolbar and status bar

```python
ui.menubar(
    Menu("File", Action("open"), Action("save"), Separator(), Item("Export PNG", run="exportPNG()")),
    Menu("Layout", Item("Stars and rings", run="motifLayout()"), Item("ForceAtlas2", run="forceAtlas2Layout()")),
    Menu("Help", Action("manual")),
)                                          # replaces the built-in menus
ui.toolbar(Action("open"), Action("save"), "|", Action("zoom-in"), Action("zoom-out"), Action("fit"),
           "|", Action("tool:select"), Action("tool:lens"), "|", Search(), spacer=True)
ui.statusbar(Label(lambda: f"{len(sel)} selected"), Memory())
```

- **Built-in actions by name:**
  - `open`, `save`, `undo`, `redo`;
  - `zoom-in`, `zoom-out`, `fit`;
  - `tool:select`, `tool:path`, …;
  - `layout:fa2`, …;
  - `export:png`, …;
  - `table`, `manual`, `tour`.

  Each comes with a label, an icon and a shortcut.
- **Your own items** run Gython (`run=`) or call a function (`onClick=`).
- **Changing the built-in menus:** `ui.menubar(keep=["File", "Help"], add=[...])` keeps some of them and adds yours.
- **Icons:** a small built-in SVG set from an MIT- or ISC-licensed icon library, plus an app's own SVGs by file name.
- **The right-click menu** keeps `NodeEditorPopup.addItem`, and gains `ui.contextMenu(kind, items)` to replace or reorder it.

### 4. More widgets

- **Containers:** `Tabs`, `Stack`, `Row` and `Group` (titled and collapsible, like Cytoscape's panels).
- **Data views:**
  - `Table(seq_or_kind, columns=…)`, live and linked like today's data table;
  - `List` and `Tree` (`NetworkList` is a ready-made `Tree`);
  - `Markdown`, `Image` and `Chart`, which embeds a chart command or an Altair chart in a panel.
- **Inputs:**
  - `NumberField`, `ColorPicker`, `Toggle`, `RadioGroup` and `RangeSlider`;
  - `FieldPicker`, a list of node or edge fields;
  - `ValuePicker`, the values of a field.
- **Dialogs:** `ui.ask(...)`, `ui.choose(...)` and `ui.form(...)` for small wizards, using the existing modal dialogs.
- **Binding:** `label.bind(lambda: …)` and `table.bind(query)`. They refresh after every command, as live charts do now, so panels stay current without handler code.

### 5. Features the two examples need that GUESS lacks

| feature | for | effort |
|---|---|---|
| overview mini-map in a corner of the graph | Cytoscape, Gephi | S |
| align / distribute / stack selected nodes; scale and rotate the selection | Cytoscape's Node Layout Tools | S |
| network list (graphs and subgraphs) as a tree | Cytoscape's Network tab | S |
| style editor laid out as properties with default / mapping / bypass | Cytoscape's Style tab | M (extends the style panel) |
| layout workspaces | Gephi's Overview / Data Laboratory / Preview | M |
| preview settings (edge thickness, label fonts, curved edges, rendered as for export) | Gephi's Preview | M |

### 6. Presets and examples

- `ui.preset("cytoscape")` and `ui.preset("gephi")`: ready-made arrangements in pure Gython. They are also the reference examples for app authors.
- **Example apps:**
  - a PPI Workbench in Cytoscape style (IntAct import, `motifLayout`, node table);
  - a Gephi-style studio (Appearance, Layout, Statistics and Filters, with the timeline below);
  - the existing cookbook capstones, rewritten as packaged apps.

### 7. Developer workflow

- **Writing an app:**
  - `appPreview()` turns the current session into the app view;
  - Ctrl+` brings the console back;
  - `ui.reset()` returns to the standard window.
- **Packaging it:** `exportApp("myapp/", script="main.gy", data=[...])` writes the manifest folder; `exportApp("myapp.guess")` writes the single file.
- **Tests:** a Playwright helper loads an app by URL and checks its regions, menus and actions.

## Phases

| phase | contents | effort |
|---|---|---|
| 1. Foundation | manifest and loading (`?app=`, folder bundle, `.guess`); console modes; regions, splitters and tabs; built-in views placeable; `ui.layout`, `ui.menubar`, `ui.toolbar`, `ui.statusbar` with built-in actions; theme and branding | 3–4 days |
| 2. Widgets | containers, Table, List and Tree, inputs, dialogs, binding; overview mini-map; align, distribute and rotate tools | 3 days |
| 3. Presets and examples | `ui.preset("cytoscape" \| "gephi")`, network list, workspaces, `ui.saveLayout()`, two example apps, a cookbook chapter on building apps | 3 days |
| 4. Deployment | `exportApp` folder and zip, `npm run bundle -- --app`, offline apps, trust prompt, manual section | 2 days |

Each phase ships on its own and keeps today's apps (`exportApp`, `?app=1`)
working.

## Decisions for you

1. **Which delivery comes first:** a hosted GUESS with `?app=` links, or self-contained folders and zips?
2. **Whether an app's users may open the console:** never, with a key, or at the author's choice (the plan's default is the author's choice).
3. **Whether to copy Cytoscape and Gephi** closely (panel names, icons) or loosely, keeping GUESS's look with the same arrangement. The plan assumes loosely, which also avoids imitating their branding.
4. **The style editor:** whether a Cytoscape-style property table (default / mapping / bypass) is worth building, or the current style panel placed in a tab is enough.
