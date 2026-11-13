import { expect, test } from "@playwright/test";
const ready = (page: any) => page.waitForFunction(() => (window as any).__guess?.renderer?.nodes?.size > 0, null, { timeout: 120000 });
test("twin", async ({ page }) => {
  const errors: string[] = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/?app=explainers/networks/ch11-path-lengths/manifest.json"); await ready(page);
  await page.getByRole("tab", { name: "What's missing" }).click();
  await page.waitForTimeout(4000);
  await page.locator("#dock-right select").nth(1).selectOption({ label: "Its random twin" });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: "/private/tmp/claude-503/-Users-eadar-Documents-GitHub-guess-web/8a5cf0a4-a09f-45c1-a19f-da4afdadc839/scratchpad/ch11b/pl-twin.png" });
  await page.locator("#dock-right select").nth(0).selectOption({ label: "Political blogs (600-blog sample)" });
  await page.waitForTimeout(12000);
  await page.screenshot({ path: "/private/tmp/claude-503/-Users-eadar-Documents-GitHub-guess-web/8a5cf0a4-a09f-45c1-a19f-da4afdadc839/scratchpad/ch11b/pl-twin-blogs.png" });
  for (const t of await page.locator(".console-out .error").allInnerTexts()) console.log("ERRTEXT", t);
  await expect(page.locator(".console-out .error")).toHaveCount(0);
  expect(errors).toEqual([]);
});
