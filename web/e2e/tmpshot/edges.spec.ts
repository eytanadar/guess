import { test } from "@playwright/test";
import { boot, run } from "../helpers";
test.use({ deviceScaleFactor: 3 });
const code = [
  "remove(g.nodes)",
  "styles = ['solid','dashed','dotted','taper','wave','double','fuzzy','gradient','flow']",
  "heads = ['triangle','swept','open','diamond','circle','tee','none']",
  "for i, st in enumerate(styles):",
  "    a = addNode('L' + st); b = addNode('R' + st)",
  "    a.x, a.y, b.x, b.y = 0, i * 40, 260, i * 40",
  "    a.color = 'green'; b.color = 'orange'; a.label = st; a.labelvisible = true; a.labelpos = 'left'",
  "    e = addDirectedEdge(a, b); e.linestyle = st; e.width = 3; e.color = 'blue'",
  "for i, h in enumerate(heads):",
  "    a = addNode('A' + h); b = addNode('B' + h)",
  "    a.x, a.y, b.x, b.y = 420, i * 50, 640, i * 50",
  "    b.label = h; b.labelvisible = true",
  "    e = addDirectedEdge(a, b); e.arrowhead = h; e.width = 2.5; e.color = 'gray'",
  "center()",
].join("\n");
for (const scheme of ["light", "dark"] as const) test("edges " + scheme, async ({ page }) => {
  await boot(page);
  await page.evaluate((s) => { document.documentElement.dataset.theme = s; }, scheme);
  await run(page, code);
  console.log(await page.locator(".cell").last().innerText());
  await page.waitForTimeout(800);
  const box = (await page.locator("canvas").first().boundingBox())!;
  await page.screenshot({ path: "/private/tmp/claude-503/-Users-eadar-Documents-GitHub-guess-web/8a5cf0a4-a09f-45c1-a19f-da4afdadc839/scratchpad/edges-" + scheme + ".png", clip: { x: box.x + 230, y: box.y + 230, width: 90, height: 360 } });
  await page.screenshot({ path: "/private/tmp/claude-503/-Users-eadar-Documents-GitHub-guess-web/8a5cf0a4-a09f-45c1-a19f-da4afdadc839/scratchpad/heads-" + scheme + ".png", clip: { x: box.x + 640, y: box.y + 235, width: 70, height: 330 } });
});
