import { expect, test } from "@playwright/test";
import { boot, run } from "../helpers";
test.use({ deviceScaleFactor: 2 });
test("flows", async ({ page }) => {
  await boot(page);
  await run(page, [
    "remove(g.nodes)",
    "import random",
    "random.seed(3)",
    "L = [addNode('l%d' % i) for i in range(4)]; R = [addNode('r%d' % i) for i in range(4)]",
    "for i, n in enumerate(L): n.x, n.y, n.color = 0, i * 150, 'red'",
    "for i, n in enumerate(R): n.x, n.y, n.color = 360, i * 150, 'green'",
    "for a in L + R:",
    "    for b in L + R:",
    "        if a != b and random.random() < 0.45:",
    "            e = addDirectedEdge(a, b); e.weight = random.random() ** 2 * 10",
    "g.edges.arrowhead = 'swept'",
    "sizeBy(weight, 0.5, 7)",
    "colorBy(weight, lightgray, '50,70,90')",
    "curvedEdges()",
    "center()",
  ].join("\n"));
  console.log((await page.locator(".cell").last().locator(".cell-out").innerText()).slice(-300));
  await page.waitForTimeout(800);
  await page.locator("canvas").first().screenshot({ path: "/private/tmp/claude-503/-Users-eadar-Documents-GitHub-guess-web/8a5cf0a4-a09f-45c1-a19f-da4afdadc839/scratchpad/flows.png" });
  const svg = await page.evaluate(() => (window as any).guessRenderer?.exportSVG?.() ?? "");
  console.log("svg", svg.length, (svg.match(/<polygon/g) || []).length);
});
