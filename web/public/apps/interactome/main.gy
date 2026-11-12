# Interactome Explorer: an example GUESS app (biology).
# BRCA1's interaction neighbourhood from IntAct (CC BY 4.0), laid out by structure.

makeFromFile("brca1-intact.gdf")
g.nodes.size = 9
motifLayout()
center()

def selected_info():
    if not len(sel):
        return "*Click a protein, or drag a box, to see it here.*"
    if len(sel) > 1:
        return f"**{len(sel)} proteins** selected; their partners: {len(set(m for n in sel for m in n.getNeighbors()) - set(sel))}"
    n = sel[0]
    parts = sorted(m.name for m in n.getNeighbors())
    shown = ", ".join(parts[:12]) + (f" and {len(parts) - 12} more" if len(parts) > 12 else "")
    return (f"### {n.name}\n{n.description or ''}\n\n"
            f"- UniProt: `{n.uniprot}`\n- species: {n.species}\n- {n.degree} partners: {shown}")

def min_score(v):
    showAll()
    (miscore < v).visible = false
    (degree == 0).visible = false

def stars():
    motifLayout(outline=outlines.checked)

def forces():
    removeConvexHulls()
    forceAtlas2Layout(preventOverlap=true)

def complexes():
    mcodeClusters()
    colorize(mcode_class)

def communities():
    louvainClusters()
    colorize(louvain_class)

outlines = Checkbox("outline each shape", checked=False, onChange=lambda on: stars())
about = Markdown("""### Interactome Explorer
The proteins that interact with **BRCA1**, from IntAct. Each hub's partners
sit in rings around it; proteins sharing the same partners line up in grids.
Hover a protein to read about it; click to select it.""")

ui.title("Interactome Explorer", "BRCA1 · IntAct")
ui.layout(
    left=Tabs(
        Tab("Explore",
            about,
            Group("Selected", Markdown(selected_info)),
            Group("Layout", Row(Button("Stars and rings", onClick=stars), Button("Forces", onClick=forces)), outlines),
            Group("Confidence", Slider(0, 1, 0, 0.05, label="minimum MI score", onChange=min_score))),
        Tab("Colour", Row(Button("Complexes (MCODE)", onClick=complexes), Button("Communities", onClick=communities)),
            View("style")),
        Tab("Filter", View("filter"))),
    bottom=View("table"),
    sizes={"left": 330, "bottom": 210},
)
ui.menubar(
    Menu("File", Action("open"), Action("save"), "-", Action("png"), Action("svg"),
         MenuItem("Interactive web page", run='exportHTML("brca1.html", title="BRCA1 interactions")')),
    Menu("Analysis",
         MenuItem("Complexes (MCODE)", onClick=complexes),
         MenuItem("Communities (Louvain)", onClick=communities),
         MenuItem("Hubs", run="highest(degree, 10).labelvisible = true"),
         "-", MenuItem("Summary", run="graphStats()"), "-", Action("source", "How this app is built")),
    keep=["Help"])
ui.toolbar(Action("tools"), "|", Action("fit"), Action("search"))
ui.statusbar(Label(lambda: f"{len([n for n in g.nodes if n.visible])} proteins shown · {len(g.edges)} interactions"),
             "|", Label(lambda: f"{len(sel)} selected"))
