"""Help content shared by the in-app help browser, the command palette and the
generated API reference: command groups and curated, searchable examples."""

# module that defines a command -> help group title
GROUPS = [
    ("commands", "Graph structure, loading and saving, mapping, view"),
    ("session", "Undo, redo, history and logging"),
    ("analysis", "Statistics, communities, filters and paths"),
    ("algorithms", "Clustering and generators"),
    ("structure", "Structure: bridges, cut nodes, backbones, directed graphs, mixing, comparing partitions"),
    ("interop", "networkx bridge and sample graphs"),
    ("igr", "igraph: communities, large-graph layouts, similarity, patterns, cuts and flows"),
    ("gv", "Graphviz layouts: dot, neato, sfdp, fdp, circo, twopi, osage; overlap removal"),
    ("layouts", "Layouts"),
    ("visuals", "Display: hulls, legends, background, edges, labels, selection, export"),
    ("styles", "Styles and visual mappings"),
    ("glyphs", "Pie nodes, borders and edge bundling"),
    ("groups", "Grouping: collapse and expand"),
    ("workspaces", "Several graphs: subgraphs and tabs"),
    ("timeline", "Time: ranges, years and the timeline"),
    ("slides", "Presentations (slides)"),
    ("connectors", "Data from the web: URLs, SPARQL, NDEx, Neo4j, packages"),
    ("states", "States and morphing"),
    ("ranges", "Ranges (existence intervals)"),
    ("charts", "Charts"),
    ("gui", "Interface building (panels, widgets, timers, events)"),
    ("persist", "Sessions and apps"),
    ("sqlquery", "SQL"),
    ("colors", "Colors"),
]


def group_of(name, fn):
    """The GROUPS key for a command function."""
    if getattr(fn, "__qualname__", "").startswith("Session.__init__"):
        return "session"
    mod = getattr(fn, "__module__", "") or ""
    key = mod.rsplit(".", 1)[-1] if mod.startswith("guess") else "commands"
    return key if key in dict(GROUPS) else "commands"


# title, code, tags (extra search words). Grouped by topic for the help browser.
EXAMPLES = [
    ("Basics", [
        ("Colour nodes by a query", "(freq > 100).color = red", "select filter set attribute"),
        ("Nodes with a field value", "dept == 'dept3'", "query equals"),
        ("Pattern match names", "name like 'v1%'", "sql like wildcard"),
        ("Combine queries", "(dept == 'dept1') & (totaldegree > 3)", "and intersection"),
        ("Loop over a set", "for n in (dept == 'dept3'):\n    n.labelvisible = true", "for iterate labels"),
        ("Edges between two groups", "(dept == 'dept1') <-> (dept == 'dept3')", "undirected edges between"),
        ("Directed edges", "v1 -> g.nodes", "out edges arrow"),
        ("Any edges touching a node", "v1 ? g.nodes", "incident neighbours"),
        ("Neighbours of a node", "v1.getNeighbors()", "adjacent"),
        ("Add nodes and edges", "addNode('zed', color=red)\naddEdge(zed, v1)", "create new"),
        ("Remove and restore", "remove(totaldegree == 0)\nadd(g.deleted)", "delete undo"),
        ("Undo the last command", "undo()", "revert redo"),
    ]),
    ("Appearance", [
        ("A colour per category", "colorize(dept)", "categorical palette distinct"),
        ("Gradient by value", "colorBy(freq, yellow, red, 'log')", "continuous ranking heat"),
        ("Size by importance", "sizeBy(pagerank, 5, 40, 'sqrt')", "ranking scale centrality"),
        ("Size by rank of a field", "resizeLinear(totaldegree, 5, 30)", "degree"),
        ("Labels from a field", "labelBy(dept)", "text names"),
        ("Shapes per category", "shapeBy(dept)", "style square circle"),
        ("Legend for a mapping", "colorize(dept)\nlegendFor(dept)", "key"),
        ("Edge width by weight", "sizeBy(freq, 1, 8)", "thickness edges"),
        ("Curved, mixed-colour edges", "curvedEdges()\nsetEdgeColorMode('mixed')", "gephi arcs"),
        ("Readable labels", "labelOutlines()\nhideOverlappingLabels()", "halo cull overlap"),
        ("Shade a group", "createConvexHull(dept == 'dept1', '200,200,255,90')", "hull region"),
        ("Dark background", "setDisplayBackground(black)", "theme"),
        ("Save a named style", "defineStyle('by dept', ['colorize(dept)', 'legendFor(dept)'])\napplyStyle('by dept')", "preset perspective"),
    ]),
    ("Layouts", [
        ("ForceAtlas2", "forceAtlas2Layout()", "gephi force directed"),
        ("ForceAtlas2, tighter clusters", "forceAtlas2Layout(linLog=true, preventOverlap=true)", "linlog"),
        ("GEM layout", "gemLayout()", "force directed"),
        ("Kamada-Kawai", "kkLayout()", "spring stress"),
        ("Hierarchy", "sugiyamaLayout()", "tree dag layered"),
        ("Hive plot", "hiveLayout(dept, pagerank, axes=5)", "hive radial axes krzywinski"),
        ("Radial around a node", "radialLayout(v1)", "tree centre"),
        ("Remove overlaps", "noverlapLayout()", "spread"),
        ("Pack components", "binPackLayout()", "disconnected"),
        ("Rotate / mirror", "rotateLayout(90)\nmirrorLayout()", "flip turn"),
    ]),
    ("Analysis", [
        ("Summary statistics", "graphStats()", "diameter density components clustering"),
        ("Communities", "louvainClusters()\ncolorize(modularity_class)", "modularity clusters louvain"),
        ("Most central nodes", "sortBy(pagerank)[-10:]", "top important pagerank"),
        ("Label the hubs", "(betweenness > 1000).labelvisible = true", "centrality bridges"),
        ("Shortest path", "shortestPath(v1, v14).color = red", "route distance"),
        ("Distance heat map", "heatMap(v1)", "hops"),
        ("Groups as charts", "plotSizesPie(dept)", "pie chart"),
        ("Distribution chart", "plotHistogram(pagerank)", "histogram"),
        ("SQL over fields", "sql('select dept, count(*) from nodes group by dept')", "query table"),
        ("Weak points", "bridges().color = red\ncutNodes().size = 30", "articulation cut vertex bridge"),
        ("Backbone", "showOnly(spanningTree(maximum=True))", "spanning tree skeleton"),
        ("Brokers", "sortBy(constraint)[:5]", "structural holes burt effective size"),
        ("Homophily", "assortativity(dept)\nmixingMatrix(dept)", "assortativity mixing"),
        ("Compare partitions", "louvainClusters()\ncompareClusters(modularity_class, dept)", "nmi ari rand"),
        ("Any networkx algorithm", "import networkx as nx\nsetField(nx.community.greedy_modularity_communities(toNetworkX()), 'greedy')\ncolorize(greedy)", "networkx nx bridge communities"),
        ("Classic networks", "makeSample('karate')\ncolorize(club)", "zachary les miserables florentine sample"),
        ("Leiden communities", "leidenClusters()\ncolorize(leiden_class)", "igraph communities leiden"),
        ("Communities in directed graphs", "infomapClusters()\ncolorize(infomap_class)", "igraph infomap flow"),
        ("Similar nodes", "similarTo(v1).color = red", "jaccard neighbours similarity"),
        ("Likely missing links", "predictLinks(10)", "link prediction adamic adar"),
        ("Find a pattern", "findPattern([('a','b'), ('b','c'), ('c','a')])", "subgraph isomorphism motif triangle"),
        ("Large-graph layout", "drlLayout()", "igraph drl openord big"),
        ("Layered drawing (Graphviz)", "dotLayout(rankdir='LR')", "dot hierarchy dag graphviz sugiyama"),
        ("Stress layout (Graphviz)", "neatoLayout()", "neato stress majorization graphviz"),
        ("Remove overlaps, keep shape", "removeOverlap()", "prism overlap graphviz"),
        ("Labels inside nodes", "g.nodes.labelvisible = true\nfitNodesToLabels()", "label inside fit flowchart"),
        ("Labels where there's room", "g.nodes.labelvisible = true\ng.nodes.labelpos = 'outside'", "label position placement"),
        ("Labels off the edges", "g.nodes.labelpos = 'outside'\nlabelPlacement('particles')", "label placement particles leader"),
        ("Polish label positions", "optimizeLabels(2)", "label placement annealing optimize"),
        ("Labels that stay readable when zooming", "constantLabelSize()", "label zoom screen size"),
        ("Label size by a field", "labelSizeBy(pagerank, 0.8, 2)", "label size font"),
        ("Edge labels", "labelBy(freq)\nedgeLabelsAlong()", "edge label along"),
        ("Bundle edges", "bundleEdges()", "mingle edge bundling hairball"),
        ("Force-directed edge bundling", "bundleEdges(method='fdeb')", "fdeb holten edge bundling"),
    ]),
    ("Filtering and selection", [
        ("Show only a core", "showOnly(kCore(3))", "filter hide"),
        ("Ego network", "showOnly(egoNetwork(v1, 2))", "neighbourhood"),
        ("Largest component", "showOnly(giantComponent())", "connected"),
        ("Edges inside communities", "showOnly(intraEdges(modularity_class))", "within"),
        ("Show everything again", "showAll()", "reset unhide"),
        ("Select from code", "select(dept == 'dept2')", "highlight sel"),
        ("Act on the selection", "sel.color = orange\ncenter(sel)", "selected"),
        ("Table of a set", "table(dept == 'dept3')", "data rows"),
    ]),
    ("Files and sessions", [
        ("Load Gephi's format", "makeFromGEXF('graph.gexf')", "open import"),
        ("Load spreadsheets", "makeFromCSV('edges.csv', 'nodes.csv')", "csv import table"),
        ("Export for Gephi", "exportGEXF('graph.gexf')", "save"),
        ("Save a session", "saveSession('work.guess')", "download"),
        ("Save what you ran", "saveHistory('work.py')", "script history"),
        ("Snapshot and morph", "ss('before')\ncircleLayout()\nmorph('before', 2000)", "state animate"),
        ("Random graph", "makeBarabasiAlbertRandom(5, 2, 300)", "generate scale free"),
    ]),
    ("Interface building", [
        ("A slider that filters", "s = Slider(freq.min, freq.max, label='min freq')\ndef update(v):\n    (freq < v).visible = false\n    (freq >= v).visible = true\ns.onChange = update\nui.dock(Panel('Filter', s))", "widget panel"),
        ("React to clicks", "graphevents.clickNode = lambda n: center([n] + n.getNeighbors())", "events"),
        ("Record a movie", "startMovie(30, 'run.webm')\ngemLayout()\nstopMovie()", "video"),
    ]),
]


def examples():
    """Flat list of {group, title, code, tags}."""
    return [{"group": g, "title": t, "code": c, "tags": tags} for g, items in EXAMPLES for t, c, tags in items]
