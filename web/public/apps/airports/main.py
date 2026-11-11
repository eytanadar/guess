# Airport Disruption: an example GUESS app (infrastructure).
# US airports and routes; click an airport, close it, and see who is cut off.

makeFromFile("us-airports.gdf")
geoLayout()
sizeBy(degree, 3, 22)
g.edges.visible = false
closed = []

def pieces():
    return weakComponentClusters()

def status():
    parts = pieces()
    big = len(parts[0]) if len(parts) else 0
    lost = len(g.nodes) - big
    return (f"**{len(closed)}** closed · the largest connected part has **{big}** airports"
            + (f"; **{lost}** are cut off from it" if lost else ""))

def picked():
    return sel[0] if len(sel) == 1 else None

def info():
    a = picked()
    if a is None:
        return "*Click an airport.*"
    return f"### {a.name} · {a.airport}\n{a.city}, {a.country}\n\n- {a.degree} routes"

def close_it():
    a = picked()
    if a is None:
        StatusBar.setStatus("Click an airport first")
        return
    closed.append(a.name)
    remove(a)
    select([])
    mark_cut_off()

def mark_cut_off():
    parts = pieces()
    g.nodes.color = "cornflowerblue"
    for p in parts[1:]:
        p.color = "red"

def reopen():
    global closed
    add(g.deleted)
    closed = []
    g.nodes.color = "cornflowerblue"

def busiest():
    for n in highest(betweenness, 5):
        if n.name not in closed:
            select([n])
            return

def show_routes(on):
    g.edges.visible = on

routes = Checkbox("show routes", checked=False, onChange=show_routes)

ui.title("Airport Disruption")
ui.layout(
    right=Column(
        Markdown("""### What if an airport closes?
Click an airport on the map, then **Close it**. Airports cut off from the
main network turn red."""),
        Group("Airport", Markdown(info), Row(Button("Close it", onClick=close_it), Button("Pick a busy one", onClick=busiest))),
        Group("Network", Markdown(status), Button("Reopen everything", onClick=reopen), routes)),
    sizes={"right": 300},
)
ui.menubar()
ui.toolbar(Action("tool:select"), Action("tool:lens"), "|", Action("fit"), Action("png"), "|", Action("source", "How this app is built"))
ui.statusbar(Label(lambda: f"{len(g.nodes)} airports open"))
