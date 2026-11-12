import { expect, test } from "@playwright/test";
import { readdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const DIR = join(process.cwd(), "public", "explainers", "networks");
const NAMES = readdirSync(DIR).filter((d) => existsSync(join(DIR, d, "main.gy"))).sort();

for (const name of NAMES) {
  test(`explainer ${name} opens without errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`/?app=explainers/networks/${name}/manifest.json`);
    await page.waitForFunction(() => (window as any).__guess?.renderer?.nodes?.size > 0, null, { timeout: 90000 });
    await expect(page.locator("#dock-right .w-markdown").first()).toBeVisible({ timeout: 30000 });
    await page.waitForTimeout(1500);
    await expect(page.locator(".console-out .error")).toHaveCount(0);
    if (process.env.SHOT) await page.screenshot({ path: `${process.env.SHOT}/${name}.png` });
    expect(errors).toEqual([]);
  });
}

test("the explainers index links every built explainer", async ({ page }) => {
  await page.goto("/explainers/networks/index.html");
  const links = page.locator("a", { hasText: "Open" });
  await expect(links).toHaveCount(NAMES.length);
  const href = await links.first().getAttribute("href");
  expect(href).toContain("?app=explainers/networks/");
});
