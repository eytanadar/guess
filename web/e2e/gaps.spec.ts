import { expect, test } from "@playwright/test";
import { boot, run } from "./helpers";

test("a Chart widget draws inside its panel and follows the graph; log-log charts", async ({ page }) => {
  const errors = await boot(page);
  await run(page, [
    "c = Chart(lambda: plotFrequency(degree, log=true))",
    "ui.dock(Panel('Degrees', c, position='right'))",
  ].join("\n"));
  const w = page.locator(".w-chart");
  await expect(w.locator("svg.chart circle")).not.toHaveCount(0);
  await expect(w).toContainText("log–log");
  await expect(w.locator(".w-chart-title")).toHaveText("Distribution of degree");
  const before = await w.locator("svg.chart circle").count();
  await run(page, "remove([n for n in g.nodes if n.degree > 5])");
  await expect.poll(() => w.locator("svg.chart circle").count()).toBeLessThan(before);
  await run(page, "plotHistogram(degree, 6, log=true)");
  await expect(page.locator(".panel .chart-body svg.chart").last()).toContainText("log scale");
  if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT + "/chart.png" });
  expect(errors).toEqual([]);
});

test("drawings show on the display and in SVG export", async ({ page }) => {
  const errors = await boot(page);
  await run(page, [
    "clearDrawings()",
    "drawRect(-50, -50, 200, 120, fill='255,200,0,60', style='dashed')",
    "drawCircle(50, 10, 80, color=red)",
    "drawLine(-50, 120, 150, 120, width=3, arrow=true)",
    "drawText(50, -70, 'a drawn title', size=24)",
    "center()",
  ].join("\n"));
  const svg = await page.evaluate(() => (window as any).__guess?.renderer?.exportSVG?.() ?? null);
  if (svg) {
    expect(svg).toContain("a drawn title");
    expect(svg).toContain("stroke-dasharray");
  }
  if (process.env.SHOT) { await page.waitForTimeout(1500); await page.screenshot({ path: process.env.SHOT + "/drawings.png" }); }
  expect(errors).toEqual([]);
});

test("menus have submenus that open by hover, click and keyboard", async ({ page }) => {
  const errors = await boot(page);
  await page.locator(".menu-title", { hasText: "View" }).click();
  const sub = page.locator(".menu-sub", { has: page.locator(".menu-sub-title", { hasText: "Edges" }) });
  await expect(sub.locator(".menu-sub-pop")).toBeHidden();
  await sub.locator(".menu-sub-title").hover();
  await expect(sub.locator(".menu-sub-pop")).toBeVisible();
  await page.locator("#curved").click();
  await expect(page.locator("#curved")).toHaveAttribute("aria-pressed", "true");
  await expect(sub.locator(".menu-sub-pop")).toBeHidden();               // the menu closed
  // keyboard: down to a submenu title, right opens it, left closes it
  await page.locator(".menu-title", { hasText: "File" }).focus();
  await page.keyboard.press("ArrowDown");
  const exportData = page.locator(".menu-sub-title", { hasText: "Export data" });
  await exportData.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator(".menu-sub", { has: exportData }).locator(".menu-sub-pop")).toBeVisible();
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator(".menu-sub", { has: exportData }).locator(".menu-sub-pop")).toBeHidden();
  await expect(exportData).toBeFocused();
  await page.keyboard.press("Escape");
  // an insert item puts code in the cell instead of running it
  await page.locator(".menu-title", { hasText: "File" }).click();
  await page.locator(".menu-sub-title", { hasText: "Open from the web" }).hover();
  await page.getByRole("menuitem", { name: "Protein structure (PDB)…" }).click();
  await expect(page.locator(".console-in .cm-content")).toContainText('makeFromPDB("1ubq")');
  expect(errors).toEqual([]);
});

test("linkTo chips in a Markdown panel highlight and select their node", async ({ page }) => {
  await boot(page);
  await run(page, "ui.layout(right=Markdown(lambda: 'Queue: ' + ' '.join(linkTo(n) for n in [v1, v2])))");
  const chip = page.locator(".w-markdown .md-el", { hasText: "v2" });
  await expect(chip).toBeVisible();
  await chip.hover();
  await chip.click();
  await run(page, "print(sorted(n.name for n in sel))");
  await expect(page.locator(".console-out").last()).toContainText("['v2']");
});

test("showDendrogram draws a linked tree and colours a cut", async ({ page }) => {
  const errors = await boot(page);
  await run(page, "newGraph('d')\nfor v in 'abcdef':\n    addNode(v)\nshowDendrogram([(0, 1), (2, 3), (6, 7), (4, 5), (8, 9)], cut=2, field='hc')");
  const svg = page.locator("svg.dendrogram").last();
  await expect(svg).toBeVisible();
  await expect(svg.locator("path:not(.axis)")).toHaveCount(5);
  await expect(svg).toContainText("2 groups");
  // the top merge holds all six; clicking a branch selects its nodes
  await svg.locator("rect.mark").first().click({ force: true });
  await run(page, "print(len(sel), sorted(set(n.hc for n in g.nodes)))");
  await expect(page.locator(".cell").last()).toContainText("[0, 1]");
  expect(errors).toEqual([]);
});

test("Markdown links to another app on the site", async ({ page }) => {
  await boot(page);
  await run(page, "ui.layout(right=Markdown('See [Milgram](?app=explainers/networks/ch04-milgram/manifest.json).'))");
  const a = page.locator(".w-markdown a", { hasText: "Milgram" });
  await expect(a).toHaveAttribute("href", "?app=explainers/networks/ch04-milgram/manifest.json");
  await a.click();
  await page.waitForFunction(() => (window as any).__guess?.renderer?.nodes?.size > 0, null, { timeout: 90000 });
  await expect(page).toHaveURL(/ch04-milgram/);
});
