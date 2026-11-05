import { expect, test } from "@playwright/test";
import { boot, lastError, run } from "./helpers";

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
  await page.click("#curved");
  await expect(page.locator("#curved")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".cell").last()).toContainText("curvedEdges(true)");
  await run(page, "curvedEdges(0.5)");
  expect(await lastError(page)).toBeNull();
  await page.click("#curved");
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

  const canvas = page.locator("#graph canvas");
  const box = (await canvas.boundingBox())!;
  const clickCentre = async () => {
    await page.waitForTimeout(700); // camera tween
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  };
  // shortest path tool: two clicks write the command
  await page.click("[data-tool=path]");
  await run(page, "center(v1)");
  await clickCentre();
  await expect(page.locator("#status")).toContainText("Path from v1");
  await run(page, "center(v14)");
  const cells = page.locator(".cell");
  const before = await cells.count();
  await clickCentre();
  await expect(cells).toHaveCount(before + 1);
  await expect(cells.last()).toContainText("shortestPath(v1, v14).color");
  // heat map tool
  await page.click("[data-tool=heat]");
  await clickCentre();
  await expect(cells.last()).toContainText("heatMap(v14)");
  await expect(cells.last()).not.toHaveClass(/running/);
  expect(await lastError(page)).toBeNull();
  await page.click("[data-tool=select]");
  await expect(page.locator("#status")).toHaveText("");
  // selecting a node focuses it (no console command)
  const n = await cells.count();
  await clickCentre();
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
  await page.click("#undo");
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
  await page.click("#theme");
  await page.click("#theme");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(24, 24, 26)");
  await page.click("#theme");
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
  await page.click("#btn-table");
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
  await page.click("#btn-style");
  await page.locator("#side-style select").nth(2).selectOption("dept");
  await page.locator("#side-style .pf-apply").click();
  await expect(cells.last()).toContainText("legendFor(dept)");
  await expect(page.locator("#side-style .pf-rule")).toHaveCount(2);
  // filter panel: k-core
  await page.click("#btn-filter");
  await page.locator("#side-filter select").first().selectOption("s:kcore");
  await page.locator("#side-filter button", { hasText: "Add" }).click();
  await expect(cells.last()).toContainText("showOnly(kCore(2))");
  await page.locator("#side-filter button", { hasText: "Show all" }).click();
  await expect(cells.last()).toContainText("showAll()");
  expect(errors).toEqual([]);
});
