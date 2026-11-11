import { expect, test } from "@playwright/test";
import { boot, clickNode, input, lastError, run } from "./helpers";

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
  await page.locator(".result .grp").last().click({ button: "right" });
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
