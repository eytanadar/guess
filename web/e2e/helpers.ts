import { expect, type Page } from "@playwright/test";

export const input = ".console-in .cm-content";

/** Open the app and wait for the sample graph (or ?load target) to finish loading. */
export async function boot(page: Page, path = "/") {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(path);
  await expect(page.locator(".console-out")).toContainText(/loaded/, { timeout: 90_000 });
  return errors;
}

/** Put code in the working cell. */
export async function type(page: Page, code: string) {
  await page.locator(input).click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator(input).fill(code);
}

/** Run code as a cell (Shift+Enter) and wait for it to finish. */
export async function run(page: Page, code: string) {
  const cells = page.locator(".cell");
  const before = await cells.count();
  await type(page, code);
  await page.keyboard.press("Shift+Enter");
  await expect(cells).toHaveCount(before + 1);
  await expect(cells.last()).not.toHaveClass(/running/);
}

export async function lastError(page: Page) {
  const errs = page.locator(".console-out .error");
  return (await errs.count()) ? errs.last().textContent() : null;
}
