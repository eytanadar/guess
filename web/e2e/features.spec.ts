import { existsSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { boot, clickNode, lastError, menu, run } from "./helpers";

test("layouts run without errors", async ({ page }) => {
  await boot(page);
  for (const cmd of ["circleLayout", "frLayout", "kkLayout", "gemLayout", "isomLayout", "radialLayout(v1)",
                     "mdsLayout", "sugiyamaLayout", "binPackLayout", "rescaleLayout(0.5)"]) {
    await run(page, cmd);
    expect(await lastError(page), cmd).toBeNull();
  }
});

test("states, morph and ranges", async ({ page }) => {
  await boot(page);
  await run(page, "ss(1); circleLayout(); remove(dept == 'dept1'); ss(2); ls(1)");
  await run(page, "morph(2, 500)");
  await run(page, "addRange(v1, '1-5'); print(Node rcontains 3)");
  await expect(page.locator(".console-out")).toContainText("[v1]");
  expect(await lastError(page)).toBeNull();
});

test("a docked slider drives Python code", async ({ page }) => {
  await boot(page);
  await run(page, [
    "lab = Label('')",
    "def hideshow(val):",
    "    (freq < val).visible = false",
    "    lab.text = '%d visible' % len(Edge.visible == true)",
    "s = Slider(freq.min, freq.max, onChange=hideshow)",
    "ui.dock(Panel('Threshold', s, lab))",
  ].join("\n"));
  const slider = page.locator(".w-slider input");
  await slider.evaluate((el: HTMLInputElement) => {
    el.value = "120";
    el.dispatchEvent(new Event("change"));
  });
  await expect(page.locator(".w-label")).toHaveText(/^\d+ visible$/);
  expect(await page.locator(".w-label").textContent()).not.toBe("725 visible");
});

test("charts link to the graph", async ({ page }) => {
  await boot(page);
  await run(page, "plotSizesPie(dept)");
  await page.locator(".chart path.mark").first().hover();
  await expect(page.locator("#tip")).toContainText("number of nodes");
});

test("exports download files", async ({ page }) => {
  await boot(page);
  for (const [cmd, name] of [["exportSVG('g.svg')", "g.svg"], ["exportPNG('g.png')", "g.png"],
                             ["saveSession('s.guess')", "s.guess"], ["exportGDF('g.gdf')", "g.gdf"]]) {
    const download = page.waitForEvent("download");
    await run(page, cmd);
    expect((await download).suggestedFilename()).toBe(name);
  }
});

test("work is autosaved and restored on reload", async ({ page }) => {
  await boot(page);
  await run(page, "v1.color = red; ss('x'); remove(v2)");
  await page.waitForTimeout(3000); // autosave debounce
  await page.reload();
  await expect(page.locator(".console-out")).toContainText("Restored your previous session", { timeout: 90_000 });
  await run(page, "print(v1.color, getStates(), 'v2' in dir())");
  await expect(page.locator(".console-out .stdout").last()).toHaveText("red ['x'] False\n");
});

test("app mode runs the bundled demo", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/?load=examples/demo.guess&app=1");
  await expect(page.locator(".panel .w-slider")).toBeVisible({ timeout: 90_000 });
  await expect(page.locator("#console")).toBeHidden();
  await page.locator(".w-select select").selectOption("dept2");
  await expect(page.locator("#status")).toContainText("Click a node");
  expect(errors).toEqual([]);
});

test("curved edges and edge colour modes", async ({ page }) => {
  await boot(page);
  await run(page, 'setEdgeColorMode("mixed")');
  await menu(page, "View", "#curved");
  await expect(page.locator("#curved")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".cell").last()).toContainText("curvedEdges(true)");
  await run(page, "curvedEdges(0.5)");
  expect(await lastError(page)).toBeNull();
  await menu(page, "View", "#curved");
  await expect(page.locator("#curved")).toHaveAttribute("aria-pressed", "false");
});

test("gephi statistics, layouts, label options and click tools", async ({ page }) => {
  const errors = await boot(page);
  await run(page, "cl = louvainClusters()\ncolorize(modularity_class)\nforceAtlas2Layout(iterations=80)");
  expect(await lastError(page)).toBeNull();
  await expect(page.locator(".cell").last()).toContainText(/modularity 0\.\d+: \d+ communities/);
  await run(page, "graphStats()");
  await expect(page.locator(".cell").last()).toContainText("diameter");
  await run(page, "labelOutlines(); hideOverlappingLabels(); g.nodes.labelvisible = true; sizeBy(pagerank, 6, 30, 'sqrt')");
  expect(await lastError(page)).toBeNull();

  // shortest path tool: two clicks write the command
  await page.click("[data-tool=path]");
  await run(page, "center(v1)");
  await clickNode(page, "v1");
  await expect(page.locator("#status")).toContainText("Path from v1");
  await run(page, "center(v14)");
  const cells = page.locator(".cell");
  const before = await cells.count();
  await clickNode(page, "v14");
  await expect(cells).toHaveCount(before + 1);
  await expect(cells.last()).toContainText("shortestPath(v1, v14).color");
  // heat map tool
  await page.click("[data-tool=heat]");
  await clickNode(page, "v14");
  await expect(cells.last()).toContainText("heatMap(v14)");
  await expect(cells.last()).not.toHaveClass(/running/);
  expect(await lastError(page)).toBeNull();
  await page.click("[data-tool=select]");
  await expect(page.locator("#status")).toHaveText("");
  // selecting a node focuses it (no console command)
  const n = await cells.count();
  await clickNode(page, "v14");
  await page.waitForTimeout(200);
  expect(await cells.count()).toBe(n);
  expect(errors).toEqual([]);
});

test("open GEXF and CSV files", async ({ page }) => {
  await boot(page);
  const gexf = `<?xml version="1.0" encoding="UTF-8"?>
<gexf xmlns="http://gexf.net/1.3" xmlns:viz="http://gexf.net/1.3/viz" version="1.3"><graph defaultedgetype="undirected">
<nodes><node id="a" label="A"><viz:position x="0" y="0"/></node><node id="b" label="B"><viz:position x="100" y="50"/></node></nodes>
<edges><edge source="a" target="b" weight="3"/></edges></graph></gexf>`;
  await page.locator("#file").setInputFiles({ name: "tiny.gexf", mimeType: "application/xml", buffer: Buffer.from(gexf) });
  await expect(page.locator(".cell").last()).toContainText("loaded 2 nodes, 1 edges from tiny.gexf (GEXF)");
  await page.locator("#file").setInputFiles({ name: "e.csv", mimeType: "text/csv", buffer: Buffer.from("Source,Target,Weight\nnp,nq,2\nnq,nr,1\n") });
  await expect(page.locator(".cell").last()).toContainText("(CSV edge table)");
  await run(page, "print(len(g.nodes), (np-nq).weight)");
  await expect(page.locator(".cell").last()).toContainText("3 2.0");
});

test("box and lasso selection, group drag, select()", async ({ page }) => {
  const errors = await boot(page);
  await run(page, "center()");
  await page.waitForTimeout(700);
  const box = (await page.locator("#graph canvas").boundingBox())!;
  const at = (fx: number, fy: number) => [box.x + box.width * fx, box.y + box.height * fy] as const;
  const status = page.locator("#status");
  // shift-drag a box over the whole view selects every node
  await page.keyboard.down("Shift");
  await page.mouse.move(...at(0.005, 0.005));
  await page.mouse.down();
  await page.mouse.move(...at(0.5, 0.5), { steps: 4 });
  await page.mouse.move(...at(0.995, 0.995), { steps: 4 });
  await page.mouse.up();
  await page.keyboard.up("Shift");
  await expect(status).toContainText("402 selected");
  await run(page, "print(len(sel))");
  await expect(page.locator(".cell").last()).toContainText("402");
  // Esc clears
  await page.locator(".toolbar .brand").click();
  await page.keyboard.press("Escape");
  await expect(status).not.toContainText("selected");
  // alt-drag lasso around the left half
  await page.keyboard.down("Alt");
  await page.mouse.move(...at(0.005, 0.005));
  await page.mouse.down();
  for (const [fx, fy] of [[0.5, 0.005], [0.5, 0.995], [0.005, 0.995], [0.005, 0.01]]) await page.mouse.move(...at(fx, fy), { steps: 3 });
  await page.mouse.up();
  await page.keyboard.up("Alt");
  await expect(status).toContainText(/\d+ selected/);
  const lassoed = Number((await status.textContent())!.match(/(\d+) selected/)![1]);
  expect(lassoed).toBeGreaterThan(20);
  expect(lassoed).toBeLessThan(402);
  // select() from code, then dragging one selected node moves both
  await run(page, "select([v1, v2]); v1.x = 100; v1.y = 100; v2.x = 300; v2.y = 100; center([v1, v2])");
  await expect(status).toContainText("2 selected");
  await page.waitForTimeout(700);
  const r = await page.evaluate(() => 0);
  void r;
  await run(page, "center(v1)");
  await page.waitForTimeout(700);
  await page.mouse.move(...at(0.5, 0.5));
  await page.mouse.down();
  await page.mouse.move(...at(0.5, 0.6), { steps: 5 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  await run(page, "print(v1.y > 100, v2.y > 100, v1.y == v2.y)");
  await expect(page.locator(".cell").last()).toContainText("True True True");
  expect(errors).toEqual([]);
});

test("undo / redo, clickable printed nodes, theme toggle", async ({ page }) => {
  const errors = await boot(page);
  await run(page, "v1.color = red");
  await menu(page, "Edit", "#undo");
  await expect(page.locator(".cell").last()).toContainText("undid: v1.color = red");
  const target = page.locator(".cell", { has: page.locator(".cell-code", { hasText: /^v1\.color = red$/ }) });
  await expect(target).toHaveClass(/undone/);
  await run(page, "print(v1.color)");
  await expect(page.locator(".cell").last()).toContainText("cornflowerblue");
  // Ctrl/Cmd+Shift+Z outside the editor redoes
  await page.locator("#graph canvas").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("ControlOrMeta+Shift+z");
  await expect(page.locator(".cell").last()).toContainText("redid: v1.color = red");
  await expect(target).not.toHaveClass(/undone/);
  // printed nodes are linked: clicking one selects it
  await run(page, "for n in [v1, v2]:\n    print('node', n)");
  await page.locator(".cell").last().locator(".obj.node", { hasText: "v2" }).click();
  await expect(page.locator("#status")).toContainText("1 selected");
  await run(page, "print(sel)");
  await expect(page.locator(".cell").last()).toContainText("[v2]");
  // "Run again" adds a new cell at the bottom; history() lists every run
  const n = await page.locator(".cell").count();
  await page.locator(".cell").nth(n - 2).hover();
  await page.locator(".cell").nth(n - 2).locator(".cell-rerun").click();
  await expect(page.locator(".cell")).toHaveCount(n + 1);
  await expect(page.locator(".cell").last().locator(".cell-code")).toContainText("print('node', n)");
  await run(page, "history()");
  await expect(page.locator(".cell").last()).toContainText("print('node', n)");
  // theme: Auto -> Light -> Dark
  await menu(page, "View", "[data-theme-choice=dark]");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(24, 24, 26)");
  await menu(page, "View", "[data-theme-choice=auto]");
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", /./);
  expect(errors).toEqual([]);
});

test("help, palette, data table, style and filter panels, parameter hints", async ({ page }) => {
  const errors = await boot(page);
  const cells = page.locator(".cell");
  // help: search and insert an example
  await page.keyboard.press("F1");
  await expect(page.locator("#side-help")).toBeVisible();
  await page.locator(".help-search").fill("louvain");
  await page.locator(".help-example", { hasText: "Communities" }).getByRole("button", { name: "Insert" }).click();
  await expect(page.locator(".console-in .cm-content")).toContainText("louvainClusters()");
  await run(page, "help(sizeBy)");
  await expect(page.locator(".help-doc")).toContainText("proportion");
  // parameter hints
  await page.locator(".console-in .cm-content").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("sizeBy(freq, 1, ");
  await expect(page.locator(".cm-sig-param.active")).toHaveText("largest");
  // errors: summary, suggestion, line
  await run(page, "a1 = 1\ncolorize(dpet)");
  await expect(cells.last().locator(".error-summary")).toContainText("did you mean 'dept'");
  await expect(cells.last().locator(".code-line.err-line")).toHaveText("colorize(dpet)");
  // palette: search a value and select it
  await page.locator(".toolbar .brand").click();
  await page.keyboard.press("ControlOrMeta+k");
  await page.keyboard.type("dept == dept3");
  await expect(page.locator(".palette-item.active")).toContainText("dept == dept3");
  await page.keyboard.press("Enter");
  await expect(cells.last()).toContainText('select(dept == "dept3")');
  await expect(page.locator("#status")).toContainText(/selected/);
  // table: opens, filters, edits
  await menu(page, "View", "#btn-table");
  await expect(page.locator(".dtable-count")).toContainText("402 of 402 nodes");
  await page.locator(".dtable-bar input[type=search]").fill("dept3");
  await expect(page.locator(".dtable-count")).not.toContainText("402 of");
  await page.locator(".dtable-bar input[type=search]").fill("");
  const firstJob = page.locator(".dtable-rows .dtable-row").first().locator(".dtable-cell.editable").nth(1);
  await firstJob.dblclick();
  await page.locator(".dtable-edit").fill("boss");
  await page.keyboard.press("Enter");
  await expect(cells.last().locator(".cell-code")).toContainText('= "boss"');
  await expect(cells.last()).not.toHaveClass(/failed/);
  // style panel: map dept to colour
  await menu(page, "View", "#btn-style");
  await page.locator("#side-style select").nth(2).selectOption("dept");
  await page.locator("#side-style .pf-apply").click();
  await expect(cells.last()).toContainText("legendFor(dept)");
  await expect(page.locator("#side-style .pf-rule")).toHaveCount(2);
  // filter panel: k-core
  await menu(page, "View", "#btn-filter");
  await page.locator("#side-filter select").first().selectOption("s:kcore");
  await page.locator("#side-filter button", { hasText: "Add" }).click();
  await expect(cells.last()).toContainText("showOnly(kCore(2))");
  await page.locator("#side-filter button", { hasText: "Show all" }).click();
  await expect(cells.last()).toContainText("showAll()");
  expect(errors).toEqual([]);
});

test("graph tabs, groups, watched cells, timeline, slides, find, exports, variables", async ({ page }) => {
  const errors = await boot(page);
  const cells = page.locator(".cell");
  // several graphs: a subgraph opens a tab
  await run(page, "subgraph(dept == 'dept3', 'three')");
  await expect(page.locator(".graph-tab")).toHaveCount(2);
  await page.locator(".graph-tab button", { hasText: "main" }).click();
  await expect(cells.last()).toContainText('use("main")');
  await expect(page.locator(".graph-tab.current")).toContainText("main");
  // collapse a group; double-click expands it
  await run(page, "m = collapse(dept == 'dept1', 'one')\ncenter(m)");
  await page.waitForTimeout(700);
  const box = (await page.locator("#graph canvas").boundingBox())!;
  await page.mouse.dblclick(box.x + box.width / 2, box.y + box.height / 2);
  await expect(cells.last()).toContainText("expand(one)");
  await expect(cells.last()).not.toHaveClass(/failed/);
  // a watched cell re-runs after other commands
  await run(page, "print(len(g.nodes))");
  const watched = cells.nth((await cells.count()) - 1);
  await watched.hover();
  await watched.locator(".cell-watch").click();
  await expect(watched).toHaveClass(/watched/);
  await run(page, "addNode('extra1')");
  await expect(watched.locator(".cell-out")).toContainText("403");
  await watched.hover();
  await watched.locator(".cell-watch").click();
  // variables panel
  await run(page, "hubs = (totaldegree > 10)");
  await menu(page, "View", "#btn-vars");
  await expect(page.locator(".ws-row", { hasText: "hubs" })).toContainText("nodes");
  // timeline over a numeric field
  await run(page, "addNodeField('year', INT, 0)\nfor n in g.nodes:\n    n.year = 1990 + (n.totaldegree % 10)");
  await menu(page, "View", "#btn-timeline");
  await page.locator(".timeline select").first().selectOption("year");
  await expect(page.locator(".tl-time")).toHaveText("1999");
  await page.locator(".tl-slider").fill("2");
  await expect(page.locator(".tl-time")).toHaveText("1992");
  await page.waitForTimeout(500);
  await run(page, "print(len([n for n in g.nodes if n.visible]) < 403)");
  await expect(cells.last()).toContainText("True");
  await page.locator(".timeline button", { hasText: "Show all" }).click();
  // presentation: add two slides and step back
  await menu(page, "View", "#btn-present");
  await page.locator("#slide-new-note").fill("everything");
  await page.click("#slide-add");
  await expect(page.locator("#slide-pos")).toHaveText("1 / 1");
  await run(page, "colorize(dept)");
  await page.locator("#slide-new-note").fill("by department");
  await page.click("#slide-add");
  await expect(page.locator("#slide-pos")).toHaveText("2 / 2");
  await page.click("#slide-prev");
  await expect(page.locator("#slide-note")).toHaveText("everything");
  // find in output
  await page.keyboard.press("ControlOrMeta+Shift+f");
  await page.locator(".console-find input").fill("subgraph");
  await expect(page.locator(".console-find-count")).toHaveText("1 match");
  await page.keyboard.press("Escape");
  // notebook export
  const dl = page.waitForEvent("download");
  await menu(page, "File", "#export-notebook");
  expect((await dl).suggestedFilename()).toBe("guess.ipynb");
  expect(errors).toEqual([]);
});

test("dragging: hidden moves, ring, edges, scatter", async ({ page }) => {
  const errors = await boot(page);
  const cells = page.locator(".cell");
  const screen = (name: string) => page.evaluate((name) => {
    const r = (window as any).__guess.renderer;
    const n = [...r.nodes.values()].find((m: any) => m.name === name);
    const c = r.app.canvas.getBoundingClientRect();
    const v = r.getView();
    const s = v[2];
    return [c.left + c.width / 2 + (n.x + n.w / 2 - v[0]) * s, c.top + c.height / 2 + (n.y + n.h / 2 - v[1]) * s];
  }, name);
  const drag = async (from: number[], to: number[], alt = false) => {
    await page.mouse.move(from[0], from[1]);
    if (alt) await page.keyboard.down("Alt");
    await page.mouse.down();
    for (let k = 1; k <= 8; k++) await page.mouse.move(from[0] + ((to[0] - from[0]) * k) / 8, from[1] + ((to[1] - from[1]) * k) / 8);
    await page.mouse.up();
    if (alt) await page.keyboard.up("Alt");
  };
  // 1. a plain drag runs a hidden cell (undoable, in history()); View shows it
  await run(page, "makeSimpleRandom(3, 0)\nnd0.x, nd0.y = 0, 0\nnd1.x, nd1.y = 400, 0\nnd2.x, nd2.y = 420, 30\ncolorize(name)\ncenter()");
  await page.waitForTimeout(700);
  const before = await cells.count();
  const p0a = await screen("nd0"), q1 = await screen("nd1");
  await drag(p0a, [(p0a[0] + q1[0]) / 2, p0a[1] + 60]);
  await expect(cells).toHaveCount(before + 1);
  const moved = cells.nth(before);
  await expect(moved).toHaveClass(/hidden-move/);
  await expect(moved).toBeHidden();
  await expect(moved).toContainText("nd0.x = ");
  await expect(moved).not.toContainText("name =");     // no group reassignment
  await run(page, "print(nd0.y > 1)\nhistory()");
  await expect(cells.last()).toContainText("True");
  await expect(cells.last()).toContainText("nd0.x = ");
  await menu(page, "View", "#show-moves");
  await expect(moved).toBeVisible();
  await menu(page, "View", "#show-moves");
  await expect(moved).toBeHidden();
  // 2. alt-drag from a node to another: a new edge
  await drag(await screen("nd1"), await screen("nd2"), true);
  await expect(cells.last()).toContainText("addEdge(nd1, nd2)");
  // 3. circle layout: slide around the ring
  await run(page, "makeSimpleRandom(8, 0)\ncircleLayout()\ncenter()");
  await page.waitForTimeout(700);
  await drag(await screen("nd0"), await screen("nd4"));
  await expect(cells.last()).toContainText("ringMove(nd0,");
  await expect(cells.last()).not.toHaveClass(/failed/);
  // 4. scatter layout: dragging edits the two fields
  await run(page, "makeSimpleRandom(3, 0)\naddNodeField('a', DOUBLE, 0)\naddNodeField('b', DOUBLE, 0)\nnd1.a, nd1.b = 10, 10\nnd2.a, nd2.b = 5, 2\nscatterLayout(a, b)\ncenter()");
  await page.waitForTimeout(700);
  const p0 = await screen("nd0"), p1 = await screen("nd1");
  await drag(p0, [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2]);
  await expect(cells.last()).toContainText("nd0.a = ");
  await run(page, "print(4 < nd0.a < 6, 4 < nd0.b < 6)");
  await expect(cells.last()).toContainText("True True");
  expect(errors).toEqual([]);
});

test("gestures guide, one-time tips and modal dialogs", async ({ page }) => {
  const errors = await boot(page);
  // the first-visit tip links to the guide
  await expect(page.locator("#tipcard")).toBeVisible({ timeout: 8000 });
  await page.locator(".tipcard-show").click();
  await expect(page.locator("#gesture-box")).toHaveClass(/flash/);
  await expect(page.locator(".help-tabs [data-tab=gestures]")).toHaveAttribute("aria-selected", "true");
  await page.locator(".help-search").fill("circle");
  await expect(page.locator(".gesture")).toHaveCount(1);
  await expect(page.locator(".gesture-img").first()).toHaveJSProperty("complete", true);
  await page.locator(".help-tabs [data-tab=commands]").click();
  await expect(page.locator(".help-guide-link")).toBeVisible();
  // a tip appears once when a drag gesture becomes available
  await run(page, "circleLayout()");
  await expect(page.locator(".tipcard-text")).toContainText("around the circle");
  // modal dialog instead of prompt()
  await run(page, "center(v1)");
  await page.waitForTimeout(700);
  const box = (await page.locator("#graph canvas").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, { button: "right" });
  await page.locator("#menu button", { hasText: "Assign to variable" }).click();
  await expect(page.locator("dialog.ask-dialog")).toBeVisible();
  await page.locator("dialog.ask-dialog input").fill("mine");
  await page.keyboard.press("Enter");
  await expect(page.locator(".console-out .note").last()).toContainText("mine = 1 item");
  expect(errors).toEqual([]);
});

test("2006 manual compatibility: custom menu items and old export formats", async ({ page }) => {
  const errors = await boot(page);
  // NodeEditorPopup.addItem (manual §15.5.2)
  await run(page, [
    "def paintIt(n):",
    "    n.color = red",
    "    print('painted ' + n.name)",
    "item = NodeEditorPopup.addItem('Paint red')",
    "item.menuEvent = paintIt",
    "center(v1)",
  ].join("\n"));
  await page.waitForTimeout(700);
  const box = (await page.locator("#graph canvas").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, { button: "right" });
  await page.locator("#menu button", { hasText: "Paint red" }).click();
  await expect(page.locator(".console-out")).toContainText("painted v1");
  // exportPDF/PS/EPS/GIF (manual §9)
  for (const [cmd, name, magic] of [["exportPDF('g.pdf')", "g.pdf", "%PDF-1.4"], ["exportPS('g.ps')", "g.ps", "%!PS-Adobe"],
                                    ["exportEPS('g.eps')", "g.eps", "%!PS-Adobe-3.0 EPSF"], ["exportGIF('g.gif')", "g.gif", "GIF89a"]]) {
    const download = page.waitForEvent("download");
    await run(page, cmd);
    const d = await download;
    expect(d.suggestedFilename()).toBe(name);
    const fs = await import("node:fs");
    const head = fs.readFileSync((await d.path())!).subarray(0, magic.length).toString("latin1");
    expect(head, cmd).toBe(magic);
    if (process.env.GUESS_KEEP) fs.copyFileSync((await d.path())!, `${process.env.GUESS_KEEP}/${name}`);
  }
  expect(errors).toEqual([]);
});

test("Help menu: Manual and GitHub open in a new tab", async ({ page, context }) => {
  const errors = await boot(page);
  const [manual] = await Promise.all([context.waitForEvent("page"), menu(page, "Help", "#btn-manual")]);
  expect(new URL(manual.url()).pathname).toBe("/manuals/");
  // the dev server serves docs/manual/build when the manual has been built
  if (existsSync(new URL("../../docs/manual/build/index.html", import.meta.url))) {
    await expect(manual).toHaveTitle("GUESS manual");
    await expect(manual.locator("a", { hasText: "PDF" })).toHaveAttribute("href", "GUESS-manual.pdf");
  }
  await manual.close();
  const [gh] = await Promise.all([context.waitForEvent("page"), menu(page, "Help", "#btn-github")]);
  expect(gh.url()).toContain("github.com/eytanadar/guess");
  await gh.close();
  expect(errors).toEqual([]);
});

test("legendFor: one live legend per field; rows highlight and have a menu", async ({ page }) => {
  const errors = await boot(page);
  await run(page, "colorize(dept)\nlegendFor(dept)");
  await run(page, "colorize(dept)\nlegendFor(dept)");               // replaces, doesn't stack
  await expect(page.locator("#legends .legend")).toHaveCount(1);
  const row = page.locator("#legends .legend-row.live", { hasText: /^dept4$/ });
  await row.hover();
  const hl = await page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size);
  await run(page, "print(len(dept == 'dept4'))");
  await expect(page.locator(".cell").last()).toContainText(String(hl));
  expect(hl).toBeGreaterThan(0);
  await row.click({ button: "right" });
  await expect(page.locator("#menu .menu-head")).toContainText(`dept4 (${hl} nodes)`);
  await page.locator("#menu button", { hasText: "Hide labels" }).click();
  await expect(page.locator(".cell").last()).toContainText("(dept == 'dept4').labelvisible = false");
  // the legend follows colorize
  const before = await page.locator("#legends .sw").first().evaluate((e) => getComputedStyle(e).backgroundColor);
  await run(page, "colorize(dept, yellow, blue)");
  await expect.poll(() => page.locator("#legends .sw").first().evaluate((e) => getComputedStyle(e).backgroundColor)).not.toBe(before);
  // a long legend: 12 rows and "… N more"; Show all lists every group and scrolls
  await run(page, "louvainClusters()\ncolorize(modularity_class)\nlegendFor(modularity_class)");
  const big = page.locator("#legends .legend").last();
  await expect(big.locator(".legend-row")).toHaveCount(13);
  await big.locator(".legend-more").click();
  await run(page, "print(len(groupBy(modularity_class)))");
  const total = Number((await page.locator(".cell").last().locator(".cell-out").innerText()).trim());
  await expect(big.locator(".legend-row")).toHaveCount(total + 1);
  await expect(big.locator(".legend-row").last()).toContainText(`all ${total} shown`);
  await expect.poll(() => big.evaluate((b) => b.scrollHeight > b.clientHeight)).toBe(true);
  await big.locator(".legend-more").click();
  await expect(big.locator(".legend-row")).toHaveCount(13);
  await run(page, "removeLegend(" + await big.getAttribute("data-i") + ")");
  // × closes a legend with a command (undoable)
  await page.locator("#legends .legend-close").click();
  await expect(page.locator(".cell").last()).toContainText("removeLegend(");
  await expect(page.locator("#legends .legend")).toHaveCount(0);
  await run(page, "undo()");
  await expect(page.locator("#legends .legend")).toHaveCount(1);
  expect(errors).toEqual([]);
});

test("open GML and DOT files; delete selected nodes (key, menu, right-click)", async ({ page }) => {
  const errors = await boot(page);
  const gml = 'graph [ node [ id 1 label "a" ] node [ id 2 label "b" ] node [ id 3 label "c" ] edge [ source 1 target 2 ] edge [ source 2 target 3 ] ]';
  await page.locator("#file").setInputFiles({ name: "t.gml", mimeType: "text/plain", buffer: Buffer.from(gml) });
  await expect(page.locator(".cell").last()).toContainText('makeFromGML("t.gml")');
  await expect(page.locator(".cell").last()).toContainText("loaded 3 nodes, 2 edges from t.gml (GML)");
  const dot = "digraph { p -> q -> r; r -> w; w [color=red] }";
  await page.locator("#file").setInputFiles({ name: "t.dot", mimeType: "text/plain", buffer: Buffer.from(dot) });
  await expect(page.locator(".cell").last()).toContainText("loaded 4 nodes, 3 edges from t.dot (DOT)");
  // Delete key removes the selection (one undoable command)
  await run(page, "select(p)");
  await page.locator("body").focus();
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("Delete");
  await expect(page.locator(".cell").last()).toContainText("remove(sel)");
  await run(page, "print(len(g.nodes), len(g.edges))");
  await expect(page.locator(".cell").last()).toContainText("3 2");
  // Edit → Delete selected nodes
  await run(page, "select(q)");
  await menu(page, "Edit", "#delete-sel");
  await run(page, "print(len(g.nodes))");
  await expect(page.locator(".cell").last()).toContainText("2");
  // right-click → Delete
  await run(page, "center(w)");
  await page.waitForTimeout(900);                         // camera tween
  const at = await page.evaluate(() => {
    const r = (window as any).__guess.renderer;
    const n = [...r.nodes.values()].find((m: any) => m.name === "w");
    const c = r.app.canvas.getBoundingClientRect(), v = r.getView();
    return [c.left + c.width / 2 + (n.x + n.w / 2 - v[0]) * v[2], c.top + c.height / 2 + (n.y + n.h / 2 - v[1]) * v[2]];
  });
  await page.mouse.click(at[0], at[1], { button: "right" });
  await page.locator("#menu button", { hasText: /^Delete$/ }).click();
  await expect(page.locator(".cell").last()).toContainText("remove(w)");
  await run(page, "print(sorted(n.name for n in g.nodes))");
  await expect(page.locator(".cell").last()).toContainText("['r']");
  await run(page, "undo()");
  await run(page, "print(len(g.nodes))");
  await expect(page.locator(".cell").last()).toContainText("2");
  expect(errors).toEqual([]);
});

test("networkx bridge, samples and structure commands run in the browser", async ({ page }) => {
  const errors = await boot(page);
  await run(page, "makeSample('karate')\nprint(len(g.nodes), n0.club)");
  await expect(page.locator(".cell").last()).toContainText("34 Mr. Hi");
  await run(page, "import networkx as nx\nG = toNetworkX()\nsetField(nx.community.label_propagation_communities(G), 'lpa')\nprint(type(G).__name__, lpa.max >= 1)");
  await expect(page.locator(".cell").last()).toContainText("Graph True");
  await run(page, "print(len(bridges()), len(cutNodes()), len(spanningTree()), round(assortativity(club), 2) > 0.5)");
  await expect(page.locator(".cell").last()).toContainText("1 1 33 True");
  await run(page, "louvainClusters()\nprint(compareClusters(modularity_class, club) > 0.3, sortBy(constraint)[0].name)");
  await expect(page.locator(".cell").last()).toContainText("True");
  await run(page, "fromNetworkX(nx.florentine_families_graph(), 'florence')\nprint(graphNames()[0], len(g.nodes))");
  await expect(page.locator(".cell").last()).toContainText("florence 15");
  await run(page, "exportDOT('f.dot')\nmakeFromDOT('f.dot')\nprint(len(g.edges))");
  await expect(page.locator(".cell").last()).toContainText("20");
  expect(await lastError(page)).toBeNull();
  expect(errors).toEqual([]);
});

test("igraph loads in the background and powers statistics, communities and layouts", async ({ page }) => {
  const errors = await boot(page);
  // wait for the background load (a few seconds at most)
  await expect.poll(async () => {
    await run(page, "try:\n    import igraph\n    print('igraph', igraph.__version__)\nexcept ImportError:\n    print('still loading')");
    return page.locator(".cell").last().innerText();
  }, { timeout: 60000, intervals: [1000] }).toContain("igraph 1.");
  await run(page, "useIgraph()");
  await expect(page.locator(".cell").last()).toContainText("engine: igraph");
  await run(page, "leidenClusters()\ncolorize(leiden_class)");
  await expect(page.locator(".cell").last()).toContainText(/modularity 0\.\d+: \d+ communities in leiden_class/);
  await run(page, "print(round(sortBy(betweenness)[-1].betweenness), len(findPattern([('a','b'),('b','c'),('c','a')])) > 0)");
  await expect(page.locator(".cell").last()).toContainText("True");
  await run(page, "drlLayout()\nprint(len(similarTo(v1)), len(predictLinks(3, show=False)))");
  await expect(page.locator(".cell").last()).toContainText("3");
  expect(await lastError(page)).toBeNull();
  expect(errors).toEqual([]);
});

test("Graphviz loads in the background and lays out graphs", async ({ page }) => {
  const errors = await boot(page);
  await expect.poll(async () => {
    await run(page, "from guess import gv\nprint('graphviz', gv.runner() is not None)");
    return page.locator(".cell").last().innerText();
  }, { timeout: 60000, intervals: [1000] }).toContain("graphviz True");
  await run(page, "makeSimpleDirectedRandom(20, 30)\nremove(feedbackEdges())\ndotLayout()\n"
    + "print(all(e.node1.y + e.node1.height / 2 < e.node2.y + e.node2.height / 2 for e in g.edges))");
  await expect(page.locator(".cell").last()).toContainText("True");
  const bent = await page.evaluate(() => [...(window as any).__guess.renderer.edges.values()].filter((e: any) => e.b && e.b.length).length);
  expect(bent).toBeGreaterThan(0);
  await run(page, "makeSample('karate')\nneatoLayout()\nfor n in g.nodes: n.x = n.x / 5; n.y = n.y / 5\nremoveOverlap()\nprint('ok')");
  await expect(page.locator(".cell").last()).toContainText("ok");
  await menu(page, "Layout", "Large graph (sfdp)");
  await expect(page.locator(".cell").last()).toContainText("sfdpLayout()");
  await expect(page.locator(".cell").last()).not.toHaveClass(/failed/);
  expect(await lastError(page)).toBeNull();
  expect(errors).toEqual([]);
});

test("labels inside nodes, positions, sizes, new shapes and edge labels", async ({ page }) => {
  const errors = await boot(page);
  await run(page, `makeSample('florentine')
g.nodes.labelvisible = true
g.nodes.labelpos = 'inside'
for n in g.nodes: n.width = 40; n.height = 30
Medici.color = '#222244'
Pazzi.color = '#f5f0c8'
Acciaiuoli.label = 'Acciaiuoli family of bankers'
Acciaiuoli.height = 60
Strozzi.style = 13
Strozzi.labelpos = 'below'
Albizzi.style = 12
Albizzi.labelsize = 1.6
Albizzi.labelpos = 'right'
for e in g.edges: e.label = 'marriage'
g.edges.labelvisible = true
center()`);
  await page.waitForTimeout(600);
  const pl = () => page.evaluate(() => {
    const r = (window as any).__guess.renderer;
    const nodes = new Map([...r.nodes.values()].map((n: any) => [n.name, n]));
    return r.placements.map((p: any) => ({ ...p, node: p.key.startsWith("n") ? [...nodes.values()].find((n: any) => `n${n.i}` === p.key) : null }));
  });
  let P = await pl();
  const byName = (name: string) => P.find((p: any) => p.node?.name === name);
  // inside: fits the node, contrasting colour, wrapped when long
  for (const p of P.filter((q: any) => q.node && q.node.name !== "Strozzi" && q.node.name !== "Albizzi")) {
    expect(p.w).toBeLessThanOrEqual(p.node.w + 0.01);
  }
  expect(byName("Medici").color).toBe(0xffffff);
  expect(byName("Pazzi").color).toBe(0x1a1a1a);
  expect(byName("Acciaiuoli").text).toContain("\n");
  // below / right with a bigger size
  const st = byName("Strozzi");
  expect(st.ay).toBe(0);
  expect(st.y).toBeGreaterThan(st.node.y + st.node.h);
  expect(byName("Albizzi").scale).toBeCloseTo(0.25 * 1.6);
  // edge labels on pills; turned along their edges on request
  const edgeLabels = P.filter((p: any) => p.key.startsWith("e"));
  expect(edgeLabels.length).toBe(20);
  expect(edgeLabels.every((p: any) => p.pill && p.rot === 0)).toBe(true);
  await run(page, "edgeLabelsAlong()");
  await page.waitForTimeout(300);
  P = await pl();
  expect(P.filter((p: any) => p.key.startsWith("e") && p.rot !== 0).length).toBeGreaterThan(10);
  expect(P.filter((p: any) => p.key.startsWith("e")).every((p: any) => Math.abs(p.rot) <= Math.PI / 2 + 1e-9)).toBe(true);
  // the SVG export draws the same: polygons for the new shapes, wrapped lines, pills
  const svg: string = await page.evaluate(() => (window as any).__guess.renderer.exportSVG());
  expect(svg).toContain("<polygon");
  expect((svg.match(/<tspan/g) ?? []).length).toBeGreaterThan(20);
  expect(svg).toContain('fill-opacity="0.85"');
  expect(svg).toContain("rotate(");
  expect(await lastError(page)).toBeNull();
  expect(errors).toEqual([]);
});

test("label placement: candidates, particles, annealing and constant-size labels", async ({ page }) => {
  const errors = await boot(page);
  const stats = () => page.evaluate(() => {
    const r = (window as any).__guess.renderer;
    const P = r.placements.filter((p: any) => p.key.startsWith("n"));
    const B = P.map((p: any) => [p.x - p.ax * p.w, p.y - p.ay * p.h, p.x + (1 - p.ax) * p.w, p.y + (1 - p.ay) * p.h]);
    let ll = 0;
    for (let i = 0; i < B.length; i++) for (let j = i + 1; j < B.length; j++)
      if (Math.min(B[i][2], B[j][2]) > Math.max(B[i][0], B[j][0]) && Math.min(B[i][3], B[j][3]) > Math.max(B[i][1], B[j][1])) ll++;
    return { overlaps: ll, leaders: P.filter((p: any) => p.leader).length, n: P.length };
  });
  await run(page, "g.nodes.labelvisible = true");
  await page.waitForTimeout(400);
  const fixed = await stats();
  await run(page, "g.nodes.labelpos = 'outside'");
  await page.waitForTimeout(400);
  const cand = await stats();
  expect(cand.n).toBe(402);
  expect(cand.overlaps).toBeLessThan(fixed.overlaps * 0.6);
  await run(page, "labelPlacement('particles')");
  await page.waitForTimeout(400);
  const part = await stats();
  expect(part.leaders).toBeGreaterThan(0);
  expect(part.overlaps).toBeLessThan(fixed.overlaps * 0.6);
  await run(page, "labelPlacement('candidates')\noptimizeLabels(1)");
  await expect(page.locator("#status")).toContainText(/optimizeLabels: 402 labels, overlap cost [\d.]+ → [\d.]+/, { timeout: 10000 });
  const [before, after] = (await page.locator("#status").innerText()).match(/[\d.]+ → [\d.]+/)![0].split(" → ").map(Number);
  expect(after).toBeLessThanOrEqual(before);
  // constant-size labels: zooming in reveals more of them
  await run(page, "constantLabelSize()\ncenter()");
  await page.waitForTimeout(800);
  const shown = () => page.evaluate(() => [...(window as any).__guess.renderer.labelPool.values()].filter((t: any) => t.visible).length);
  const out = await shown();
  await run(page, "center(egoNetwork(v128, 1))");
  await page.waitForTimeout(1200);
  const inside = await page.evaluate(() => {
    const r = (window as any).__guess.renderer;
    const [x0, y0, x1, y1] = (() => { const v = r.getView(); const c = r.app.canvas.getBoundingClientRect(); return [v[0] - c.width / 2 / v[2], v[1] - c.height / 2 / v[2], v[0] + c.width / 2 / v[2], v[1] + c.height / 2 / v[2]]; })();
    const inView = r.placements.filter((p: any) => p.key.startsWith("n") && p.x > x0 && p.x < x1 && p.y > y0 && p.y < y1);
    return { inView: inView.length, visible: inView.filter((p: any) => r.labelPool.get(p.key)?.visible).length };
  });
  expect(out).toBeLessThan(402);
  expect(inside.visible).toBeGreaterThan(inside.inView * 0.8);
  expect(await lastError(page)).toBeNull();
  expect(errors).toEqual([]);
});
