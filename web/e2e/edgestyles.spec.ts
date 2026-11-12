import { expect, test } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { boot, run } from "./helpers";

const GRID = [
  "remove(g.nodes)",
  "styles = ['solid','dashed','dotted','taper','wave','double','fuzzy','gradient','flow']",
  "heads = ['triangle','swept','open','diamond','circle','tee','none']",
  "for i, st in enumerate(styles):",
  "    a = addNode('L' + st); b = addNode('R' + st)",
  "    a.x, a.y, b.x, b.y = 0, i * 40, 260, i * 40",
  "    a.color = 'green'; b.color = 'orange'",
  "    e = addDirectedEdge(a, b); e.linestyle = st; e.width = 3",
  "for i, h in enumerate(heads):",
  "    a = addNode('A' + h); b = addNode('B' + h)",
  "    a.x, a.y, b.x, b.y = 420, i * 50, 640, i * 50",
  "    e = addDirectedEdge(a, b); e.arrowhead = h; e.width = 2.5",
  "center()",
].join("\n");

test("edges have line styles and arrowheads, on screen and in SVG", async ({ page }) => {
  await boot(page);
  await run(page, GRID);
  await expect(page.locator(".cell").last()).not.toHaveClass(/failed/);
  const svg: string = await page.evaluate(() => (window as any).__guess.renderer.exportSVG());
  expect(svg).toContain("stroke-dasharray");                // dashed, dotted, flow
  expect(svg).toContain("<linearGradient");                 // gradient
  expect(svg).toContain('attributeName="stroke-dashoffset"'); // flow moves
  expect(svg).toContain("<circle");                         // the circle head
  if (process.env.SVG_OUT) writeFileSync(process.env.SVG_OUT, svg);
  // flow edges keep redrawing: two frames a moment apart differ
  const canvas = page.locator("canvas").first();
  const one = await canvas.screenshot();
  await page.waitForTimeout(250);
  expect(Buffer.compare(one, await canvas.screenshot())).not.toBe(0);
  // a mistyped style says what the choices are
  await run(page, "g.edges[0].linestyle = 'zigzag'");
  await expect(page.locator(".cell").last()).toContainText("linestyle should be one of solid, dashed");
});
