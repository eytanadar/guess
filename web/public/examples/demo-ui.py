# Demo app: an edge-frequency threshold slider, department picker and
# click-to-focus, in the spirit of the paper's political-blog applet.
threshold = Label("")

def show_edges(val):
    (freq < val).visible = false
    (freq >= val).visible = true
    threshold.text = "%d of %d edges" % (len(Edge.visible == true), len(g.edges))

slider = Slider(freq.min, freq.max + 1, label="Min. frequency", onChange=show_edges)

def pick(dept_name):
    if dept_name == "(all)":
        g.nodes.labelvisible = false
        center()
    else:
        g.nodes.labelvisible = false
        members = dept == dept_name
        members.labelvisible = true
        center(members)

depts = Dropdown(["(all)"] + sorted(set(dept.values())), label="Department", onChange=pick)
ui.dock(Panel("Explore", slider, threshold, depts))

graphevents.clickNode = lambda n: center([n] + n.getNeighbors())
StatusBar.setStatus("Click a node to focus on its neighbourhood")
show_edges(freq.min)
