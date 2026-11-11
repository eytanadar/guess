import { expect, test } from "@playwright/test";
import { boot, run } from "./helpers";
const SP = "/private/tmp/claude-503/-Users-eadar-Documents-GitHub-guess-web/8a5cf0a4-a09f-45c1-a19f-da4afdadc839/scratchpad/";
test("shots", async ({ page }) => {
  await boot(page);
  await run(page, "g.nodes.size = 30\npolygonBy(dept, 3, 9)\ncolorize(dept)\ncenter(dept == 'dept1')");
  await page.waitForTimeout(800);
  await page.screenshot({ path: SP + "poly.png" });
  await run(page, "addNodeField('bio', VARCHAR, '')\nwords = ['network graph analysis', 'graph drawing layout', 'social network theory', 'centrality broker network', 'community detection graph']\nfor i, n in enumerate(g.nodes): n.bio = words[i % 5] + ' ' + n.dept\nwordCloud(bio)");
  await expect(page.locator(".vega-embed text").first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(800);
  await page.locator(".vega-embed text", { hasText: /^graph$/ }).first().hover();
  await page.waitForTimeout(400);
  await page.screenshot({ path: SP + "cloud.png" });
  const hl = await page.evaluate(() => (window as any).__guess.renderer.hl.nodes.size);
  console.log("HL", hl);
  expect(await page.locator(".error").count()).toBe(0);
});
