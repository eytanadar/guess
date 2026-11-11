import { expect, test } from "@playwright/test";
import { boot, lastError, run } from "./helpers";

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
