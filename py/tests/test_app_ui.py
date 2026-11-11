"""App interfaces: containers, live labels, regions, menus, toolbar, status bar."""
from tests.test_gython import s  # noqa: F401  (fixture)


def ui_msgs(s, op):
    return [m for m in s.rec.of("ui") if m["op"] == op]


def test_layout_regions_and_containers(s):
    code = """
t = Tabs(Tab("Info", Label("hello"), Markdown("**bold**")), Tab("Style", View("style")))
ui.layout(left=t, bottom=[View("table")], right=Panel("Tools", Button("Go")), sizes={"left": 320})
"""
    assert s.run(code), s.rec.of("error")
    docks = ui_msgs(s, "dock")
    where = sorted(d["panel"]["props"]["position"] for d in docks)
    assert where == ["bottom", "left", "right"]
    left = next(d["panel"] for d in docks if d["panel"]["props"]["position"] == "left")
    assert left["props"]["bare"] is True and left["children"][0]["kind"] == "tabs"
    assert [c["props"]["title"] for c in left["children"][0]["children"]] == ["Info", "Style"]
    assert ui_msgs(s, "regions")[-1]["sizes"] == {"left": 320.0}
    # a second layout replaces the first
    s.rec.clear()
    assert s.run('ui.layout(right=Label("only"))')
    closed = ui_msgs(s, "close")
    assert len(closed) == 3
    assert not s.run('View("nope")')


def test_live_labels_follow_commands(s):
    assert s.run('lab = Label(lambda: f"{len(g.nodes)} nodes")\nui.statusbar(lab, "|", Action("fit"))')
    n = len(s.graph._nodes)
    bar = ui_msgs(s, "statusbar")[-1]["items"]
    assert bar[0]["props"]["text"] == f"{n} nodes" and bar[1] == {"kind": "sep"} and bar[2]["name"] == "fit"
    s.rec.clear()
    assert s.run("addNode('zed')")
    assert ui_msgs(s, "update")[-1]["props"] == {"text": f"{n + 1} nodes"}
    assert s.run('bad = Label(lambda: 1 / 0)\nbad.text')


def test_menubar_toolbar_title_console(s):
    code = """
def hello(): print("hi")
ui.menubar(Menu("App", Action("open"), "-", MenuItem("Hello", onClick=hello), MenuItem("Stats", run="graphStats()")), keep=["Help"])
ui.toolbar(Action("open"), "|", Button("Run"), "search", Action("tools"))
ui.title("Test App")
ui.console("toggle")
"""
    assert s.run(code), s.rec.of("error")
    mb = ui_msgs(s, "menubar")[-1]
    items = mb["menus"][0]["items"]
    assert [i["kind"] for i in items] == ["action", "sep", "menuitem", "menuitem"] and mb["keep"] == ["Help"]
    assert items[3]["props"]["run"] == "graphStats()"
    tb = ui_msgs(s, "toolbar")[-1]["items"]
    assert [i["kind"] for i in tb] == ["action", "sep", "button", "action", "action"]
    assert ui_msgs(s, "title")[-1]["text"] == "Test App" and ui_msgs(s, "console")[-1]["mode"] == "toggle"
    # a menu item's handler runs through dispatch
    hid = items[2]["id"]
    s.rec.clear()
    assert s.dispatch(hid, "click", None)
    assert "hi" in "".join(m["text"] for m in s.rec.of("text"))
    assert not s.run('Action("fly")') and not s.run('ui.console("loud")')
