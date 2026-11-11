import { expect, test } from "@playwright/test";
import { run } from "./helpers";

const ready = (page: import("@playwright/test").Page) =>
  page.waitForFunction(() => (window as any).__guess?.renderer?.nodes?.size > 0, null, { timeout: 90000 });

test("an app from ?app= arranges the window and its controls work", async ({ page }) => {
  await page.goto("/?app=apps/interactome/manifest.json");
  await ready(page);
  await expect(page).toHaveTitle("Interactome Explorer");
  await expect(page.locator(".brand")).toContainText("Interactome Explorer");
  await expect(page.locator("#console")).toBeHidden();
  // regions: tabs on the left, the data table below, toolbar and status bar
  const tabs = page.locator("#dock-left .w-tabbar button");
  await expect(tabs).toHaveText(["Explore", "Colour", "Filter"]);
  await expect(page.locator("#dock-bottom #table-body")).toBeVisible();
  await expect(page.locator("#app-toolbar .toolgroup")).toBeVisible();
  await expect(page.locator("header.toolbar #search")).toBeHidden();
  await tabs.nth(1).click();
  await expect(page.locator("#dock-left .w-tab").nth(1)).toBeVisible();
  await expect(page.locator("#dock-left .w-tab").nth(0)).toBeHidden();
  await tabs.nth(0).click();
  // live labels follow the selection
  await expect(page.locator("#app-statusbar")).toContainText("0 selected");
  // a menu item runs its command
  await page.locator(".menubar .menu-title", { hasText: "Analysis" }).click();
  await page.locator(".menubar .menu-pop button", { hasText: "Hubs" }).click();
  await expect.poll(() => page.evaluate(() =>
    [...(window as any).__guess.renderer.nodes.values()].filter((n: any) => n.lv).length)).toBe(10);
  // the console comes back with Ctrl+` (this app allows it)
  await page.keyboard.press("Control+`");
  await expect(page.locator("#console")).toBeVisible();
  await expect(page.locator("#console")).toContainText("highest(degree, 10).labelvisible = true");
  await run(page, "select(BRCA1_P38398)");
  await expect(page.locator("#app-statusbar")).toContainText("1 selected");
  await expect(page.locator("#dock-left .w-markdown").nth(1)).toContainText("Breast cancer type 1 susceptibility protein");
});

test("an app's script error shows the console", async ({ page }) => {
  await page.route("**/apps/broken/manifest.json", (r) => r.fulfill({ json: { name: "Broken", code: "makeFromGDF('karate.gdf')\nui.title('Broken')\nnosuch()" } }));
  await page.goto("/?app=apps/broken/manifest.json");
  await ready(page);
  await expect(page.locator("#console")).toBeVisible();
  await expect(page.locator("#console .error").last()).toContainText("nosuch");
});
