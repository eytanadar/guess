import { test } from "@playwright/test";
import { readFileSync } from "node:fs";
test.use({ deviceScaleFactor: 2 });
test("svg", async ({ page }) => {
  await page.setContent('<body style="margin:0;background:#222">' + readFileSync("/private/tmp/claude-503/-Users-eadar-Documents-GitHub-guess-web/8a5cf0a4-a09f-45c1-a19f-da4afdadc839/scratchpad/styles.svg", "utf8") + "</body>");
  await page.locator("svg").first().screenshot({ path: "/private/tmp/claude-503/-Users-eadar-Documents-GitHub-guess-web/8a5cf0a4-a09f-45c1-a19f-da4afdadc839/scratchpad/styles-svg.png" });
});
