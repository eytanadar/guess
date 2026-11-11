"""demo(): a guided tour of GUESS for newcomers, from selecting nodes to a
what-if analysis, a contagion model and a small app. Each step explains an
idea, shows the code and runs it as an ordinary console cell (so it can be
edited, undone and run again). The steps use the sample organisation
(sample.gdf: 402 people, their departments and who works with whom).
"""
from .model import GuessError

LEVELS = ("Basic", "Intermediate", "Advanced")

STEPS = [
    # ---- Basic ------------------------------------------------------------------
    dict(level="Basic", title="Meet the graph",
         text="This network is an organisation: each dot is a person, each line a working tie. "
              "GUESS is driven by code: type Gython (Python with graph shortcuts) in the console "
              "and press Shift+Enter, or press *Run it* below to run each step for you.",
         code='makeFromGDF("sample.gdf")\ncenter()\nlen(g.nodes), len(g.edges)',
         notice="`g` is the graph; `g.nodes` and `g.edges` are sets you can count, loop over and change. "
                "The wheel zooms, dragging pans, and clicking a person highlights their contacts."),
    dict(level="Basic", title="Every node is a variable",
         text="Each person is a variable named after them, and their data are fields: `v1.dept`, "
              "`v1.degree` (how many ties). Setting a field changes the picture.",
         code="v1.dept, v1.degree\nv1.color = red\nv1.size = 40\ncenter(v1)",
         notice="Fields you set are the same fields you read: `v1.color` is now red. Hover `v1` in the "
                "code above to find it in the graph."),
    dict(level="Basic", title="Select by asking a question",
         text="A comparison on a field is a question about every node at once, and its answer is a "
              "set. Setting a field on the set changes all of its members.",
         code="degree > 10\n(degree > 10).color = orange\n(degree > 10).size = 30\ncenter()",
         notice="The first line printed the people with more than 10 ties: point at the list to see "
                "them in the graph. `(degree > 10)` works anywhere a set does."),
    dict(level="Basic", title="Combine questions",
         text="Combine questions with `and`, `or` and `not` (or `&`, `|`, `-`). `in` tests membership, "
              "and comparisons chain as in maths.",
         code="busy = (dept == 'dept3') and (degree > 6)\nbusy.color = blue\nlen(busy), len(3 < degree < 6)",
         notice="`busy` is an ordinary variable holding a set: hover it in the code to light it up. "
                "`3 < degree < 6` is a range in one go."),
    dict(level="Basic", title="Colour and size by data",
         text="Rather than colour sets one by one, map a field to colour or size. A legend explains "
              "the colours.",
         code="colorize(dept)\nresizeLinear(degree, 5, 30)\ncenter()",
         notice="Hover a legend entry to light up its department. Hover `dept` in the code to preview "
                "colouring by it without changing anything."),
    dict(level="Basic", title="Output is linked to the graph",
         text="Anything printed that refers to nodes or edges is linked: hover it to highlight, click to "
              "select, Alt-click to put it in your code.",
         code="highest(degree, 5)\nv1.getNeighbors()",
         notice="Click a name in the output, then look for `sel` in the status line: `sel` is always the "
                "current selection. Right-click a name for a menu of things to do with it."),
    dict(level="Basic", title="Mistakes are cheap",
         text="Every command is one undo step. Remove a whole department, then take it back.",
         code="remove(dept == 'dept4')\nlen(g.nodes)",
         notice="Now press Cmd/Ctrl+Z (with the cursor outside the code cell), or run `undo()`. The undone "
                "cell is struck through. *Edit → History…* lets you scrub back and forth through every step."),
    # ---- Intermediate ---------------------------------------------------------------
    dict(level="Intermediate", title="Lay it out",
         text="A layout places the nodes. Force-directed layouts pull connected nodes together, so "
              "groups that work together end up near each other.",
         code="gemLayout()\ncenter()",
         notice="Try `circleLayout(dept)` or *Layout* in the menu. You can also drag nodes; each drag "
                "is an undoable command too."),
    dict(level="Intermediate", title="Charts that talk to the graph",
         text="Charts appear beside the graph and are linked to it: each bar knows its nodes.",
         code="plotSizes(dept)\nplotHistogram(degree, 8)",
         notice="Hover a bar to light up its people; click to select them; drag across bars to select "
                "a range. *● Live* keeps a chart up to date as you change the graph."),
    dict(level="Intermediate", title="Who is central?",
         text="Centrality measures are fields that compute themselves when you first use them: "
              "`betweenness` counts how many shortest paths run through a person.",
         code="brokers = highest(betweenness, 5)\nbrokers.labelvisible = true\nbrokers.size = 45\n"
              "brokers.color = red\ncenter(brokers)",
         notice="These five sit between groups. Compare with `highest(degree, 5)`: the best connected "
                "are not always the best placed."),
    dict(level="Intermediate", title="Communities versus departments",
         text="Community detection finds groups that are densely tied inside, from the ties alone. "
              "Do they match the formal departments?",
         code="louvainClusters();\ncolorize(louvain_class)\n"
              "print(len(interEdges(dept)), 'ties cross departments')\n"
              "print(len(interEdges(louvain_class)), 'ties cross communities')",
         notice="Fewer ties cross communities than departments: the informal groups follow the "
                "work more closely than the org chart does. The `;` after `louvainClusters()` hides its "
                "long printout; `groupBy(louvain_class)` lists the communities."),
    dict(level="Intermediate", title="Paths",
         text="How far apart are two people, and through whom?",
         code="path = shortestPath(v1, v300)\npath.color = red\npath.width = 5\nlen(path)",
         notice="`shortestPath` gives the ties along the way, so its length is the number of steps. "
                "Try the *Path* tool in the toolbar: click two people and it writes this code for you."),
    # ---- Advanced ------------------------------------------------------------------
    dict(level="Advanced", title="What if the brokers left?",
         text="`with scratch():` runs a block on a copy of the graph and then puts everything back: "
              "a safe place for what-if questions.",
         code="with scratch():\n"
              "    remove(highest(betweenness, 10))\n"
              "    print('without the top 10 brokers:', len(weakComponentClusters()), 'pieces')\n"
              "print('with them:', len(weakComponentClusters()), 'pieces')",
         notice="The graph is untouched afterwards. `robustness()` runs this kind of experiment "
                "systematically and charts the result."),
    dict(level="Advanced", title="Your own chart, with Altair",
         text="For charts GUESS has no command for, use Altair. `nodeData` gives one row per node, "
              "and the chart stays linked: each point is a person.",
         code="brush = alt.selection_interval()\n"
              "alt.Chart(nodeData('degree', 'betweenness', 'dept')).mark_point().encode(\n"
              "    x='degree', y='betweenness', color='dept', tooltip='name').add_params(brush)",
         notice="Drag a box over the chart: the people inside are selected in the graph. Hover a point "
                "to find that person. (The first Altair chart takes a few seconds to load.)"),
    dict(level="Advanced", title="Simulate a contagion",
         text="`spread` runs an epidemic (or rumour) model over the ties and records when each person "
              "was reached.",
         code='spread([v73], "SIR", beta=0.2, gamma=0.1, seed=3)\n'
              "colorBy(infected_at, yellow, red)\n(infected_at < 0).color = lightgray",
         notice="Yellow was reached early, red late, grey never. Point at the chart to see who had been "
                "reached by each step; click to select them."),
    dict(level="Advanced", title="Build a small tool",
         text="Panels, sliders and buttons turn an analysis into a tool for others. Here, a slider "
              "hides everyone with fewer ties than its value.",
         code="def at_least(k):\n"
              "    showAll()\n"
              "    (degree < k).visible = false\n\n"
              'ui.dock(Panel("Busy people", Slider(1, 15, 1, label="minimum ties", onChange=at_least),\n'
              '                Button("Show all", onClick=showAll)))',
         notice="Drag the slider. `exportApp(\"busy.guess\")` packages a tool like this with its data, "
                "and `saveHistory()` downloads everything you ran as a script."),
    dict(level="Advanced", title="Where next",
         text="That's the tour. The help panel lists every command with examples you can run; the "
              "manual and the cookbooks (biology, epidemiology, social networks and more) go further.",
         code="help()",
         notice="`demo()` starts this tour again, and `demo(9)` or `demo('advanced')` jumps ahead."),
]


def install(session):
    def demo(step=1):
        """demo() starts a guided tour of GUESS for newcomers, from selecting
        nodes to communities, what-if analysis, Altair charts, a contagion model
        and a small app. Each step explains an idea and runs its code as a
        normal console cell. demo(9) starts at step 9; demo("advanced") at the
        first step of that level (basic, intermediate, advanced)."""
        if isinstance(step, str):
            want = step.strip().capitalize()
            if want not in LEVELS:
                raise GuessError(f"demo() levels are {', '.join(l.lower() for l in LEVELS)}")
            at = next(i for i, s in enumerate(STEPS) if s["level"] == want)
        else:
            at = int(step) - 1
            if not 0 <= at < len(STEPS):
                raise GuessError(f"the tour has steps 1 to {len(STEPS)}")
        session.emit({"type": "demo", "steps": STEPS, "at": at})
        print(f"Tour: step {at + 1} of {len(STEPS)}, in the panel below the graph")

    session.register_command("demo", demo)


__all__ = ["install", "STEPS", "LEVELS"]
