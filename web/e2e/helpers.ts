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

/** Choose a menu item: menu(page, "View", "#curved") or menu(page, "Edit", "Undo"). */
export async function menu(page: Page, title: string, item: string) {
  await page.locator(".menu-title", { hasText: title }).click();
  const pop = page.locator(".menu-root", { has: page.locator(".menu-title", { hasText: title }) }).locator(".menu-pop").first();
  const target = (item.startsWith("#") || item.startsWith("[") ? pop.locator(item) : pop.getByRole("menuitem", { name: item, includeHidden: true })).first();
  // an item in a submenu: open the submenu first (hover its title)
  const subTitle = await target.evaluate((el) => el.closest(".menu-sub")?.querySelector(".menu-sub-title")?.textContent ?? null);
  if (subTitle) await pop.locator(".menu-sub-title", { hasText: subTitle }).first().hover();
  await target.click();
}

/** Click a node by name: waits for the camera to settle, then clicks a point
 *  inside the node that the renderer's own hit test gives to that node (so a
 *  bigger neighbour drawn on top can't steal the click). */
export async function clickNode(page: Page, name: string) {
  const [x, y] = await nodePoint(page, name);
  await page.mouse.click(x, y);
}

/** A point on the page inside a node that the renderer's hit test gives to it. */
export async function nodePoint(page: Page, name: string): Promise<number[]> {
  const at = await page.waitForFunction((name) => {
    const g = (window as any).__guess;
    const r = g.renderer;
    if (r.tween) return null;                       // still moving
    const n = [...r.nodes.values()].find((m: any) => m.name === name && m.v);
    if (!n) return null;
    const c = r.app.canvas.getBoundingClientRect();
    const v = r.getView();
    const s = v[2];
    for (const fy of [0.5, 0.35, 0.65, 0.2, 0.8]) {
      for (const fx of [0.5, 0.35, 0.65, 0.2, 0.8]) {
        const sx = c.width / 2 + (n.x + n.w * fx - v[0]) * s, sy = c.height / 2 + (n.y + n.h * fy - v[1]) * s;
        const hit = r.hitTest(sx, sy);
        if (hit?.kind === "n" && hit.id === n.i && sx > 0 && sy > 0 && sx < c.width && sy < c.height) return [c.left + sx, c.top + sy];
      }
    }
    return null;
  }, name, { timeout: 15000 });
  return (await at.jsonValue()) as number[];
}
