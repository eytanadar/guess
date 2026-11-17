import { expect, test } from "@playwright/test";
import { boot, clickNode, input, lastError, menu, run } from "./helpers";

test("dicts, sets and f-strings in output link to the graph", async ({ page }) => {
  await boot(page);
  await run(page, 'print(f"the hub is {highest(degree, 1)[0]}")');
  const hub = page.locator(".result .obj.node").last();
  await expect(hub).toHaveText("v73");
  await hub.hover();
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size)).toBe(1);
  await run(page, "{n: n.degree for n in highest(degree, 3)}");
  await expect(page.locator(".result").last().locator(".obj.node")).toHaveCount(3);
  expect(await lastError(page)).toBeNull();
});

test("hovering a chart bar marks the console output it covers; clicking selects", async ({ page }) => {
  await boot(page);
  await run(page, "dept == 'dept1'");
  await run(page, "plotSizes(dept)");
  // the dept1 bar: find it by its tooltip label
  const n = await page.locator(".chart rect.mark").count();
  let found = -1;
  for (let i = 0; i < n && found < 0; i++) {
    await page.locator(".chart rect.mark").nth(i).hover();
    if ((await page.locator("#tip").innerText()).startsWith("dept1")) found = i;
  }
  expect(found).toBeGreaterThanOrEqual(0);
  await expect(page.locator(".result .obj.node.linked").first()).toBeVisible();
  await page.locator(".chart rect.mark").nth(found).click();
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.selection.size)).toBe(43);
});

test("right-clicking a histogram bin acts on its query", async ({ page }) => {
  await boot(page);
  await run(page, "plotHistogram(degree, 4)");
  await page.locator(".chart rect.mark").first().click({ button: "right" });
  await expect(page.locator("#menu .menu-head")).toBeVisible();
  // its actions act on the bin's query
  await page.locator("#menu button", { hasText: "Show labels" }).click();
  await expect(page.locator(".cell-code").last()).toContainText("degree >= 0");
});

const hlCount = (page: import("@playwright/test").Page) =>
  page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size as number);

test("output about an earlier graph stops linking", async ({ page }) => {
  await boot(page);
  await run(page, "v1");
  const old = page.locator(".result").last();
  await expect(old).not.toHaveClass(/stale/);
  await run(page, 'makeFromGDF("karate.gdf")');
  await expect(old).toHaveClass(/stale/);
  await old.locator(".obj").hover();
  expect(await hlCount(page)).toBe(0);
});

test("alt-click and the menu insert elements as code", async ({ page }) => {
  await boot(page);
  await run(page, "highest(degree, 3)");
  await page.locator(".result .obj.node").first().click({ modifiers: ["Alt"] });
  await expect(page.locator(input)).toHaveText("v73");
  await page.locator(input).press("End");
  await page.keyboard.type(".color = ");
  const grp = page.locator(".result .grp").last();
  const box = (await grp.boundingBox())!;
  await grp.click({ button: "right", position: { x: box.width - 3, y: box.height / 2 } });   // on the "]"
  await page.locator("#menu button", { hasText: "Insert as code" }).click();
  await expect(page.locator(input)).toHaveText("v73.color = (v73, v335, v171)");
});

test("the tooltip and cell numbers say which code changed an element", async ({ page }) => {
  await boot(page);
  await run(page, "colorize(dept)");
  await run(page, "v1.size = 30");
  await run(page, "v1");
  await page.locator(".result .obj.node").last().hover();
  await expect(page.locator("#tip")).toContainText("size ← [");
  await expect(page.locator("#tip")).toContainText("colorize(dept)");
  await page.locator(".cell-num").nth(-3).hover();
  await expect.poll(() => hlCount(page)).toBe(402);
});

test("hovering names, queries and fields in executed code", async ({ page }) => {
  await boot(page);
  await run(page, "hubs = highest(degree, 5)\nshowOnly(3 < degree < 6)\nsizeBy(freq, 1, 3)");
  const code = page.locator(".cell-code").last();
  await code.locator("span", { hasText: /^hubs$/ }).hover();
  await expect(page.locator("#tip")).toContainText("hubs — 5 nodes now");
  await expect.poll(() => hlCount(page)).toBe(5);
  await code.locator("span", { hasText: /^degree$/ }).nth(1).hover();
  await expect(page.locator("#tip")).toContainText("3 < degree < 6 — 49 nodes now");
  await code.locator("span", { hasText: /^freq$/ }).hover();
  await expect(page.locator("#tip")).toContainText("edge field");
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.preview?.e.size ?? 0)).toBe(725);
  await page.mouse.move(5, 5);
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.preview)).toBeNull();
});

test("distinct values link to their members", async ({ page }) => {
  await boot(page);
  await run(page, "dept.distinct");
  await page.locator(".result .grp .grp", { hasText: "'dept1'" }).hover();
  await expect(page.locator("#tip")).toContainText("dept == 'dept1'");
  await expect.poll(() => hlCount(page)).toBe(43);
});

test("alt-clicking a node in the graph inserts its name", async ({ page }) => {
  await boot(page);
  await page.keyboard.down("Alt");
  await clickNode(page, "v73");
  await page.keyboard.up("Alt");
  await expect(page.locator(input)).toHaveText("v73");
});

test("pointing at a spread chart shows the step and who was reached by then", async ({ page }) => {
  await boot(page);
  await run(page, "spread([v73], 'SI', beta=0.5, seed=1)");
  const hit = page.locator(".chart rect.line-hit");
  const box = (await hit.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height / 2);
  await expect(page.locator("#tip")).toContainText("step");
  await expect(page.locator("#tip")).toContainText("infected:");
  await expect.poll(() => hlCount(page)).toBeGreaterThan(0);
  await page.mouse.click(box.x + box.width * 0.3, box.y + box.height / 2);
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.selection.size)).toBeGreaterThan(0);
});

test("charts mark each other's bars", async ({ page }) => {
  await boot(page);
  await run(page, "plotSizes(dept)");
  await run(page, "plotHistogram(degree, 4)");
  await page.locator(".chart").first().locator("rect.mark").first().hover();
  await expect(page.locator(".chart").nth(1).locator("rect.mark.linked").first()).toBeVisible();
});

test("the edge table marks edges between selected nodes", async ({ page }) => {
  await boot(page);
  await run(page, "table(g.edges)");
  await run(page, "select(dept == 'dept1')");
  await expect(page.locator(".dtable-row.selected").first()).toBeVisible();
});

const selCount = (page: import("@playwright/test").Page) =>
  page.evaluate(() => (window as any).__guess.renderer.selection.size as number);

test("dragging across histogram bars selects every bar in the range", async ({ page }) => {
  await boot(page);
  await run(page, "plotHistogram(degree, 4)");
  const bars = page.locator(".chart rect.mark");
  const a = (await bars.nth(0).boundingBox())!, b = (await bars.nth(1).boundingBox())!;
  const y = a.y + a.height - 2;
  await page.mouse.move(a.x + 2, y);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width / 2, y, { steps: 5 });
  await expect(page.locator(".chart .brush")).toBeVisible();
  await expect.poll(() => hlCount(page)).toBeGreaterThan(0);
  await page.mouse.up();
  // the two lowest bins: every node with degree below the third bin's start
  await run(page, "len(sel)");
  const n = Number(await page.locator(".result").last().innerText());
  expect(await selCount(page)).toBe(n);
  expect(n).toBeGreaterThan(0);
  expect(await lastError(page)).toBeNull();
});

test("hovering a node elsewhere scrolls the data table to its row", async ({ page }) => {
  await boot(page);
  await run(page, "table()");
  await expect(page.locator(".dtable-row").first()).toBeVisible();
  await run(page, "g.nodes[-1]");
  await page.locator(".result .obj.node").last().hover();
  const last = await page.locator(".result .obj.node").last().innerText();
  await expect(page.locator(".dtable-row.linked .dtable-name", { hasText: new RegExp(`^${last}$`) })).toBeVisible();
});

test("errors link the nodes they name", async ({ page }) => {
  await boot(page);
  await run(page, "v1.nosuchfield");
  const link = page.locator(".error .obj.node").last();
  await expect(link).toHaveText("v1");
  await link.hover();
  await expect.poll(() => hlCount(page)).toBe(1);
});

test("a pinned watched cell shows live output in a side panel and follows the selection", async ({ page }) => {
  await boot(page);
  await run(page, "print(len(sel), 'selected')");
  const cell = page.locator(".cell").last();
  await cell.hover();
  await cell.locator(".cell-watch").click();
  await cell.locator(".cell-pin").click();
  const pane = page.locator(".panel-body.watch-body");
  await expect(pane).toContainText("0 selected");
  await expect(cell.locator(".cell-out")).toContainText("Pinned");
  // a selection made on the display (not a command) re-runs it
  await clickNode(page, "v73");
  await page.keyboard.down("Shift");
  await clickNode(page, "v1");
  await page.keyboard.up("Shift");
  await expect(pane).toContainText(/[12] selected/);
  // closing the panel brings the output back to the cell
  await page.locator(".panel", { has: pane }).locator(".panel-close").click();
  await expect(cell.locator(".cell-out")).toContainText("selected");
  await expect(cell.locator(".cell-out")).not.toContainText("Pinned");
});

test("the history panel steps back and forward and shows what each step changed", async ({ page }) => {
  await boot(page);
  await run(page, "v1.size = 60");
  await run(page, "addNode('fresh')");
  await menu(page, "Edit", "#btn-history");
  const steps = page.locator(".history-step");
  await expect(steps.last()).toContainText("addNode('fresh')");
  await expect(page.locator(".history-where")).toContainText("addNode('fresh')");
  // hovering a step highlights what it touched
  await steps.filter({ hasText: "v1.size = 60" }).hover();
  await expect.poll(() => hlCount(page)).toBe(1);
  // clicking the start undoes everything; the cells are struck through
  await steps.filter({ hasText: "v1.size = 60" }).click();
  await expect(steps.last()).toHaveClass(/undone/);
  await expect(page.locator(".cell.undone")).toHaveCount(1);
  await run(page, "print('fresh' in [n.name for n in g.nodes], v1.size)");
  // (v1.size printed is linked output, so it isn't plain stdout)
  await expect(page.locator(".cell").last().locator(".result, .stdout").last()).toHaveText("False 60.0");
  // the slider goes forward again
  const slider = page.locator(".history-slider");
  await slider.focus();
  await page.keyboard.press("End");
  await expect(page.locator(".cell.undone")).toHaveCount(0);
  await expect(steps.last()).not.toHaveClass(/undone/);
  expect(await lastError(page)).toBeNull();
});

test("the table filters with Gython and its rows have the element menu", async ({ page }) => {
  await boot(page);
  await run(page, "table()");
  const search = page.locator(".dtable-bar input[type=search]");
  await search.fill("dept == 'dept1' and degree > 3");
  await expect(search).toHaveClass(/query/);
  await run(page, "len((dept == 'dept1') & (degree > 3))");
  const want = await page.locator(".result").last().innerText();
  await expect(page.locator(".dtable-count")).toContainText(`${want} of 402 nodes`);
  // plain text still searches
  await search.fill("dept7");
  await expect(search).not.toHaveClass(/query/);
  // Enter runs calls (on a scratch copy)
  await search.fill("highest(degree, 5)");
  await search.press("Enter");
  await expect(page.locator(".dtable-count")).toContainText("5 of 402 nodes");
  // right-click a row: the element menu; "Add to selection" fills sel
  await page.locator(".dtable-rows .dtable-row").first().click({ button: "right" });
  await expect(page.locator("#menu .menu-head")).toBeVisible();
  await page.locator("#menu button", { hasText: "Add to selection (sel)" }).click();
  await expect.poll(() => selCount(page)).toBe(1);
  // Actions with nothing else selected but one row: acts on the selected row; clear and act on all 5 shown
  await run(page, "select()");
  await page.locator(".dtable-actions").click();
  await expect(page.locator("#menu .menu-head")).toContainText("5 nodes shown");
  await page.locator("#menu button", { hasText: "Select these" }).click();
  await expect.poll(() => selCount(page)).toBe(5);
  expect(await lastError(page)).toBeNull();
});

test("the Cluster tool labels one lasso per cluster and shows what's left", async ({ page }) => {
  await boot(page);
  await page.locator("[data-tool=cluster]").click();
  await expect(page.locator(".ask-dialog input")).toHaveValue("cluster");
  await page.locator(".ask-dialog button.primary").click();
  const bar = page.locator(".cluster-bar");
  await expect(bar).toBeVisible();
  await expect(bar.locator(".cluster-next")).toHaveValue("1");
  await expect(bar.locator(".cluster-left")).toContainText("402 left");
  const c = (await page.locator("#graph canvas").boundingBox())!;
  // a plain drag draws a lasso: the nodes inside become cluster 1
  const lasso = async (x0: number, x1: number) => {
    // (starting below the tool's bar, which sits over the top of the graph)
    await page.mouse.move(c.x + c.width * x0, c.y + c.height * 0.3);
    await page.mouse.down();
    for (const [fx, fy] of [[x0, 0.02], [x1, 0.02], [x1, 0.98], [x0, 0.98], [x0, 0.32]]) {
      await page.mouse.move(c.x + c.width * fx, c.y + c.height * fy, { steps: 4 });
    }
    await page.mouse.up();
  };
  await lasso(0.02, 0.5);
  await expect(bar.locator(".cluster-next")).toHaveValue("2");
  await expect(bar.locator(".cluster-counts")).toContainText("1 cluster ·");
  await expect(bar.locator(".cluster-bar input[type=checkbox], input[type=checkbox]").first()).toBeChecked();
  // the second, overlapping one takes over the nodes it catches (relabel is on)
  await lasso(0.3, 0.98);
  await expect(bar.locator(".cluster-next")).toHaveValue("3");
  await expect(bar.locator(".cluster-counts")).toContainText("2 clusters");
  await run(page, "print(len(cluster == 1) + len(cluster == 2), len(g.nodes) - len(cluster == None))");
  const [a, b] = (await page.locator(".stdout").last().innerText()).split(" ").map(Number);
  expect(a).toBe(b);
  expect(a).toBeGreaterThan(300);
  await expect(bar.locator(".cluster-counts")).toContainText(`${a} labelled`);
  // overriding the id: text ids count up too
  await bar.locator(".cluster-next").fill("10");
  await run(page, "undo()");
  await expect(bar.locator(".cluster-counts")).toContainText("1 cluster ·");
  await page.keyboard.press("Escape");
  await page.locator("#graph canvas").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Escape");
  await expect(bar).toBeHidden();
  // again: "cluster" is taken, so it suggests cluster1
  await page.locator("[data-tool=cluster]").click();
  await expect(page.locator(".ask-dialog input")).toHaveValue("cluster1");
  // choosing the existing field asks whether to clear it
  await page.locator(".ask-dialog input").fill("cluster");
  await page.locator(".ask-dialog button.primary").click();
  await expect(page.locator(".ask-dialog")).toContainText("cluster already has values");
  await page.locator(".ask-dialog button", { hasText: "Clear cluster" }).click();
  await expect(bar).toBeVisible();
  await expect(bar.locator(".cluster-next")).toHaveValue("1");
  await expect(bar.locator(".cluster-left")).toContainText("402 left");
  expect(await lastError(page)).toBeNull();
});

test("Altair charts show in the dock and link to the graph", async ({ page }) => {
  test.setTimeout(180_000);
  await boot(page);
  // alt is imported on first use (Pyodide loads altair the first time)
  await run(page, "alt.Chart(nodeData('degree', 'dept')).mark_point().encode(x='degree', y='dept', color='dept')");
  const marks = page.locator(".vega-body svg path.mark-symbol, .vega-body svg .mark-symbol path");
  await expect(marks.first()).toBeVisible({ timeout: 90_000 });
  expect(await lastError(page)).toBeNull();
  // one mark per node: hovering it highlights that node
  await marks.first().hover({ force: true });
  await expect.poll(() => hlCount(page)).toBe(1);
  // a summary chart: a bar of count() by dept links through a query
  await run(page, "alt.Chart(nodeData('dept')).mark_bar().encode(x='dept', y='count()').properties(title='by dept')");
  await expect(page.locator(".panel header", { hasText: "by dept" })).toBeVisible();
  const bars = page.locator(".panel", { has: page.locator("header", { hasText: "by dept" }) }).locator("svg .mark-rect path");
  await expect(bars.first()).toBeVisible();
  await bars.first().hover({ force: true });
  await expect.poll(() => hlCount(page)).toBeGreaterThan(1);
  await bars.first().click({ force: true });
  await run(page, "print(len(sel), len(dept == 'dept0'))");
  const [a, b] = (await page.locator(".stdout").last().innerText()).split(" ").map(Number);
  expect(a).toBe(b);
  // the graph's hover fades the other points of the scatter plot
  await run(page, "nodeData('pagerank')");
  expect(await lastError(page)).toBeNull();
});

test("a live chart recomputes after changes", async ({ page }) => {
  await boot(page);
  await run(page, "plotSizes(dept)");
  const panel = page.locator(".panel", { has: page.locator("header", { hasText: "dept group sizes" }) });
  const live = panel.locator(".panel-live");
  await expect(live).toHaveAttribute("aria-pressed", "false");
  const bars = panel.locator("rect.mark");
  const before = await bars.count();
  await live.click();
  await expect(live).toHaveAttribute("aria-pressed", "true");
  await run(page, "remove(dept == 'dept1')");
  await expect(bars).toHaveCount(before - 1);
  await run(page, "undo()");
  await expect(bars).toHaveCount(before);
  await live.click();
  await expect(live).toHaveAttribute("aria-pressed", "false");
  await run(page, "remove(dept == 'dept2')");
  await expect(bars).toHaveCount(before);
  expect(await lastError(page)).toBeNull();
});

test("an edge in the output links its ends to their nodes and its connector to the edge", async ({ page }) => {
  await boot(page);
  await run(page, "list(g.edges)[0]");
  const edge = page.locator(".result").last().locator(".obj.edge");
  const ends = edge.locator(".obj.node.end");
  await expect(ends).toHaveCount(2);
  await expect(edge).toHaveText(/^\w+\u2013\w+$/);   // an en dash, not "-"
  const hl = () => page.evaluate(() => {
    const h = (window as any).__guess.renderer.hl;
    return [h.nodes.size, h.edges.size];
  });
  await ends.first().hover();
  await expect.poll(hl).toEqual([1, 0]);
  // the connector: the edge span's own text, between the two ends
  await edge.locator(".conn").hover();
  await expect.poll(hl).toEqual([0, 1]);
  // a set of edges still counts edges only
  await run(page, "list(g.edges)[:3]");
  await page.locator(".result").last().locator(".grp").first().hover();
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size)).toBe(0);
});

test("hovering hidden nodes and edges elsewhere draws ghosts of them in the graph", async ({ page }) => {
  await boot(page);
  const drawn = () => page.evaluate(() => (window as any).__guess.renderer.overlay.getLocalBounds().width);
  await run(page, "(dept == 'dept1').visible = false\ndept == 'dept1'");
  expect(await drawn()).toBe(0);
  await page.locator(".result").last().locator(".grp, .obj").first().hover();
  await expect.poll(drawn).toBeGreaterThan(0);
  await page.mouse.move(5, 5);
  await expect.poll(drawn).toBe(0);
  await run(page, "showAll()\nedg = [k for k in g.edges if v73 in (k.node1, k.node2)][:2]\nfor k in edg: k.visible = false\nedg");
  await page.locator(".result").last().locator(".obj.edge .conn").first().hover();
  await expect.poll(drawn).toBeGreaterThan(0);
});

test("commands print linked nodes and edges: predictLinks(add=true)", async ({ page }) => {
  await boot(page);
  await expect.poll(async () => {        // predictLinks needs igraph, which loads in the background
    await run(page, "try:\n    import igraph\n    print('igraph ready')\nexcept ImportError:\n    print('still loading')");
    return page.locator(".cell").last().textContent();
  }, { timeout: 60000, intervals: [1000] }).toContain("igraph ready");
  await run(page, "r = predictLinks(3, add=true)");
  const cell = page.locator(".cell", { hasText: "predictLinks(3, add=true)" }).last();
  await expect(cell.locator(".obj.node")).toHaveCount(6, { timeout: 60_000 });   // three pairs, both ends
  const added = cell.locator(".grp", { hasText: "3 predicted edges" });
  await expect(added).toHaveCount(1);
  await added.hover();
  await cell.locator(".obj.node").first().hover();
  expect(await lastError(page)).toBeNull();
});

test("a printed field value links every element with that value", async ({ page }) => {
  await boot(page);
  await run(page, "v4.dept");
  const val = page.locator(".result").nth((await page.locator(".result").count()) - 1).locator(".grp");
  await val.hover();
  const n = await page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size as number);
  await run(page, "len(dept == v4.dept)");
  await expect(page.locator(".result").last()).toHaveText(String(n));
  expect(n).toBeGreaterThan(1);
  await val.click({ button: "right" });
  await expect(page.locator("#menu .menu-head")).toContainText("dept ==");
});

test("deleted nodes are struck through in the output; undo restores them", async ({ page }) => {
  await boot(page);
  await run(page, "v4");
  const v4 = page.locator(".result").nth((await page.locator(".result").count()) - 1).locator(".obj.node");
  await run(page, "removeNode(v4)");
  await expect(v4).toHaveClass(/gone/);
  await run(page, "undo()");
  await expect(v4).not.toHaveClass(/gone/);
});

test("right-clicking selected output acts on just the selected nodes, whole names", async ({ page }) => {
  await boot(page);
  await run(page, "dept == 'dept4'");
  const objs = page.locator(".result").last().locator(".obj.node");
  const names = await objs.evaluateAll((els) => els.slice(0, 3).map((e) => e.textContent));
  // select from the middle of the first name to the middle of the third
  await objs.first().evaluate((first) => {
    const third = first.parentElement!.querySelectorAll(".obj.node")[2];
    const r = document.createRange();
    r.setStart(first.firstChild!, 1);
    r.setEnd(third.firstChild!, 1);
    const s = window.getSelection()!;
    s.removeAllRanges();
    s.addRange(r);
  });
  await objs.nth(1).click({ button: "right" });
  await expect(page.locator("#menu .menu-head")).toContainText("3 nodes");
  expect(await page.evaluate(() => window.getSelection()!.toString())).toBe(names.join(", "));
  const cells = await page.locator(".cell").count();
  await page.locator("#menu button", { hasText: "Show labels" }).click();
  await expect(page.locator(".cell")).toHaveCount(cells + 1);
  // the cell spells out the nodes, so it means the same when run again or saved
  await expect(page.locator(".cell-code").last()).toHaveText(`(${names.join(", ")}).labelvisible = true`);
});

test("menu actions on many elements spell them out, folded in the console", async ({ page }) => {
  await boot(page);
  await run(page, "highest(degree, 8)");
  const objs = page.locator(".result").last().locator(".obj.node");
  const names = await objs.evaluateAll((els) => els.map((e) => e.textContent));
  // select them all in the output, then right-click the selection
  await objs.first().evaluate((first) => {
    const all = first.parentElement!.querySelectorAll(".obj.node");
    const r = document.createRange();
    r.setStartBefore(first);
    r.setEndAfter(all[all.length - 1]);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(r);
  });
  await objs.nth(2).click({ button: "right" });
  await expect(page.locator("#menu .menu-head")).toContainText("8 nodes");
  await page.locator("#menu .swatches button[title=red]").click();
  const code = page.locator(".cell-code").last();
  await expect(code).toHaveAttribute("data-code", `(${names.join(", ")}).color = red`);
  // shown folded after the first node; the toggle opens it
  const shown = () => code.evaluate((e) => (e as HTMLElement).innerText.replace(/\s+$/, ""));
  await expect.poll(shown).toBe(`(${names[0]}, … +7 more).color = red`);
  // hovering the count, or the brackets, highlights the whole set
  const hl = () => page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size);
  await code.locator(".code-fold").hover();
  await expect.poll(hl).toBe(8);
  await page.mouse.move(5, 5);
  await expect.poll(hl).toBe(0);
  await code.locator("[data-from='0']:not(.code-fold)").hover();
  await expect.poll(hl).toBe(8);
  await code.locator(".code-fold").click();
  await expect.poll(shown).toBe(`(${names.join(", ")} ▴).color = red`);
  // the cell runs the same again: every one of them is red
  await run(page, `all(n.color == red for n in (${names.join(", ")}))`);
  await expect(page.locator(".result").last()).toHaveText("True");
  expect(await lastError(page)).toBeNull();
});

test("printed lists fold to their first item; one-item lists don't fold", async ({ page }) => {
  await boot(page);
  await run(page, "highest(degree, 5)");
  const list = page.locator(".result").last().locator(".grp.foldable").first();
  const arrow = list.locator(":scope > .list-toggle");
  await expect(arrow).toHaveText("▾");
  await arrow.click();
  await expect(arrow).toHaveText("▸");
  await expect(list).toContainText("… +4 more");
  await expect(list.locator(".list-body")).toBeHidden();
  // hovering the folded list still highlights all five
  await list.hover({ position: { x: 3, y: 3 } });
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size)).toBe(5);
  await arrow.click();
  await expect(list.locator(".list-body")).toBeVisible();
  await run(page, "highest(degree, 1)");
  await expect(page.locator(".result").last().locator(".list-toggle")).toHaveCount(0);
});

test("many groups print as a list of folded groups", async ({ page }) => {
  await boot(page);
  await run(page, "groupBy(dept)");
  const out = page.locator(".result").last();
  const groups = out.locator(".grp.foldable.collapsed");
  expect(await groups.count()).toBeGreaterThan(8);
  expect(await groups.first().innerText()).toMatch(/^▸\[dept\d+: v\d+, … \+\d+ more\]$/);    // [dept0: v1, … +27 more]
  await expect(groups.first().locator(".grp-label")).toHaveText(/^dept\d+: $/);
  const first = out.locator(".grp.foldable").nth(1);              // (0 is the outer list)
  await first.locator(":scope > .list-toggle").click();
  await expect(first.locator(":scope > .list-body")).toBeVisible();
  await expect(first.locator(":scope > .grp-label")).toBeVisible();          // the label stays when open
});

test("legends and chart panels fold", async ({ page }) => {
  await boot(page);
  await run(page, "colorBy(degree, yellow, red); GradientLegend(degree)");
  const lg = page.locator("#legends .legend").last();
  await expect(lg.locator(".ramp-title")).toHaveText("degree");
  await lg.locator(".legend-fold").click();
  await expect(page.locator("#legends .legend-folded")).toHaveText("Legend: degree");
  await expect(page.locator("#legends .ramp")).toHaveCount(0);
  await page.locator("#legends .legend-folded").click();
  await expect(page.locator("#legends .ramp")).toHaveCount(1);
  await run(page, "plotHistogram(degree, 4)");
  const panel = page.locator(".panel").last();
  await panel.locator(".panel-fold").click();
  await expect(panel.locator(".panel-body")).toBeHidden();
  await panel.locator(".panel-fold").click();
  await expect(panel.locator(".panel-body")).toBeVisible();
});

test("output formats: x >> table prints a linked, sortable, foldable table", async ({ page }) => {
  await boot(page);
  await run(page, "dept == 'dept1' >> table(degree)");
  const t = page.locator(".result .out-table").last();
  await expect(t.locator("th")).toHaveText(["node", "degree"]);
  await expect(t.locator("tbody tr")).toHaveCount(43);
  // sort by degree, descending on the second click
  await t.locator("th").nth(1).click();
  await t.locator("th").nth(1).click();
  const first = Number(await t.locator("tbody tr").first().locator("td").nth(1).innerText());
  const last = Number(await t.locator("tbody tr").last().locator("td").nth(1).innerText());
  expect(first).toBeGreaterThanOrEqual(last);
  // a node in a cell is linked
  await t.locator(".obj.node").first().hover();
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size)).toBe(1);
  // groups: label, size, members (folded); the table folds to one line
  await run(page, "groupBy(dept) >> table(sort='size')");
  const gt = page.locator(".result .out-table").last();
  await expect(gt.locator("th")).toHaveText(["label", "size", "members"]);
  await expect(gt.locator("tbody tr").first().locator(".grp.collapsed")).toHaveCount(1);
  await gt.locator(":scope > .list-toggle").click();
  await expect(gt.locator(".tbl-short")).toHaveText("table: label, size, members (21 rows)");
  // settings: every set as a count from now on
  await run(page, "setFormat('set', count)");
  await run(page, "dept == 'dept1'");
  await expect(page.locator(".result").last()).toHaveText("43");
  expect(await lastError(page)).toBeNull();
});

test("colours print as swatches whose tooltip gives the rgb value and name", async ({ page }) => {
  await boot(page);
  await run(page, "[red, '10,20,30', v4.color]");
  const sw = page.locator(".result").last().locator(".swatch");
  await expect(sw).toHaveCount(3);
  await expect(sw.nth(0)).toHaveAttribute("title", "red — rgb(255, 0, 0)");
  await expect(sw.nth(1)).toHaveAttribute("title", "10,20,30 — rgb(10, 20, 30)");
  expect(await sw.nth(0).evaluate((e) => getComputedStyle(e).backgroundImage)).toContain("rgb(255, 0, 0)");
  // colours in code get a swatch too: names (2006 and CSS) and colour strings
  await run(page, "v1.color = blue; v2.color = dandelion; v3.color = '#ff8800'; v5.color = 'navy'; x9 = 5");
  const code = page.locator(".cell-code").last();
  await expect(code.locator(".code-swatch")).toHaveCount(4);
  await expect(code.locator(".code-swatch").first()).toHaveAttribute("title", /^blue: #/);
  await expect(code).toHaveAttribute("data-code", "v1.color = blue; v2.color = dandelion; v3.color = '#ff8800'; v5.color = 'navy'; x9 = 5");
  // a field's colour stays linked to the nodes with it
  await run(page, "v4.color");
  await page.locator(".result").last().locator(".grp").hover();
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size)).toBeGreaterThan(1);
  expect(await lastError(page)).toBeNull();
});

test("field values printed in a loop link to the elements with that value", async ({ page }) => {
  await boot(page);
  await run(page, "colorize(dept)");
  await run(page, "for c in groupBy(dept)[:3]: print(c[0].dept, c[0].color)");
  const out = page.locator(".cell").last();
  await expect(out.locator(".swatch")).toHaveCount(3);
  await out.locator(".grp", { hasText: "dept1" }).first().hover();
  await expect.poll(() => page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size)).toBe(43);
  expect(await lastError(page)).toBeNull();
});
