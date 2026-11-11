import { expect, test } from "@playwright/test";
import { boot, input, lastError, menu, run, type } from "./helpers";

test("loads the sample graph and runs paper examples", async ({ page }) => {
  const errors = await boot(page);
  await expect(page.locator(".console-out")).toContainText("loaded 402 nodes, 725 edges");
  for (const cmd of ["(freq > 100).color = red", "colorize(dept)", "resizeLinear(totaldegree, 5, 25)",
                     "name like 'v1%'", "(v1, v2) & (jobfun == 'employee')", "center(dept == 'dept3')"]) {
    await run(page, cmd);
  }
  expect(await lastError(page)).toBeNull();
  expect(errors).toEqual([]);
});

test("hovering grouped output highlights the group and shows its annotation", async ({ page }) => {
  await boot(page);
  await run(page, "groupBy(dept)");
  await page.locator(".result .grp .grp").nth(2).hover();
  await expect(page.locator("#tip")).toContainText("dept == 'dept2'");
  await expect(page.locator("#tip")).toContainText("37 nodes");
});

test("system names are protected", async ({ page }) => {
  await boot(page);
  await run(page, "g = 5");
  expect(await lastError(page)).toContain("is the graph");
});

test("blocks, completion and doc hovers", async ({ page }) => {
  await boot(page);
  await run(page, "for n in (dept == 'dept3'):\n    n.labelvisible = true");
  expect(await lastError(page)).toBeNull();
  await type(page, "v1.jo");
  await page.keyboard.press("Tab");
  await expect(page.locator(input)).toHaveText("v1.jobfun");
  await run(page, "colorize(dept)");
  await page.locator(".cell-code .fn", { hasText: "colorize" }).last().hover();
  await expect(page.locator("#tip")).toContainText("colorize(field");
});

test("cells: Enter adds a line, Shift+Enter runs, Edit and Run again reuse a cell", async ({ page }) => {
  await boot(page);
  await type(page, "k = 2");
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await page.keyboard.type("print(k * 21)");
  await expect(page.locator(".console-in .cm-line")).toHaveCount(2);
  const cells = page.locator(".cell");
  const before = await cells.count();
  await page.keyboard.press("Shift+Enter");
  await expect(cells).toHaveCount(before + 1);
  await expect(cells.last().locator(".cell-out")).toHaveText("42");
  await expect(page.locator(".console-in .cm-placeholder")).toBeVisible(); // cell emptied
  // pull it back, change it, run again
  await cells.last().hover();
  await cells.last().locator(".cell-edit").click();
  await expect(page.locator(".console-in .cm-line")).toHaveText(["k = 2", "print(k * 21)"]);
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("print(k * 50)");
  await page.keyboard.press("Shift+Enter");
  await expect(cells).toHaveCount(before + 2);
  await expect(cells.last().locator(".cell-out")).toHaveText("100");
  await cells.last().hover();
  await cells.last().locator(".cell-rerun").click();
  await expect(cells).toHaveCount(before + 3);
  await expect(cells.last().locator(".cell-out")).toHaveText("100");
  // history: ↑ on the first line goes back, ↓ on the last line forward, and the
  // unsaved cell (and edits to recalled commands) survive the round trip
  const lines = page.locator(".console-in .cm-line");
  await page.locator(input).click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("a = 1");
  await page.keyboard.press("Enter");
  await page.keyboard.type("b = 2");
  await page.keyboard.press("ArrowDown"); // last line of the present cell: nothing
  await expect(lines).toHaveText(["a = 1", "b = 2"]);
  await page.keyboard.press("ArrowUp"); // moves to line 1 within the cell
  await expect(lines).toHaveText(["a = 1", "b = 2"]);
  await page.keyboard.press("ArrowUp"); // first line: the last command
  await expect(lines).toHaveText(["print(k * 50)"]);
  await page.keyboard.press("ArrowUp");
  await expect(lines).toHaveText(["k = 2", "print(k * 21)"]);
  await page.keyboard.press("End");
  await page.keyboard.type("  # edited");
  await page.keyboard.press("ArrowDown"); // first line -> second line, still this command
  await expect(lines).toHaveText(["k = 2  # edited", "print(k * 21)"]);
  await page.keyboard.press("ArrowDown"); // last line: forward
  await expect(lines).toHaveText(["print(k * 50)"]);
  await page.keyboard.press("ArrowUp"); // back again: the edit was kept
  await expect(lines).toHaveText(["k = 2  # edited", "print(k * 21)"]);
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown"); // ... and back to the unsaved cell, intact
  await expect(lines).toHaveText(["a = 1", "b = 2"]);
  await page.keyboard.press("ArrowDown");
  await expect(lines).toHaveText(["a = 1", "b = 2"]);
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Backspace");
  // an error marks the cell
  await run(page, "nosuchname");
  await expect(cells.last()).toHaveClass(/failed/);
});

test("Stop interrupts a runaway command", async ({ page }) => {
  await boot(page);
  await expect(page.locator("#stop")).toBeEnabled();
  await type(page, "while True: pass");
  await page.keyboard.press("Shift+Enter");
  // wait until the command is actually running (starting a run resets the interrupt flag)
  await expect(page.locator(".cell.running")).toHaveCount(1);
  // under load the first click can land before Python checks the flag: press
  // Stop until the run reports the interrupt (each press is idempotent)
  await expect(async () => {
    await page.click("#stop");
    await expect(page.locator(".console-out .error").last()).toHaveText("Interrupted", { timeout: 2000 });
  }).toPass({ timeout: 30000 });
  await expect(page.locator(".cell.running")).toHaveCount(0);
});

test("the cookbooks' datasets are there by name, fetched on first use", async ({ page }) => {
  await boot(page);
  const cells = page.locator(".cell");
  for (const [code, expected] of [
    ['makeFromGDF("karate.gdf")', "loaded 34 nodes, 78 edges"],          // a cookbook dataset
    ['makeFromCSV("friends.csv")', "loaded 8 nodes"],                       // a tiny one
    ['makeFromGDF("adamic-glance.gdf")', "loaded 40 nodes"],                // from gdfs/
    ['print(len(open("scandal-in-bohemia.txt").read()) > 10000)', "True"],   // any file type
  ]) {
    const n = await cells.count();
    await type(page, code);
    await page.keyboard.press("Shift+Enter");
    await expect(cells.nth(n)).toContainText(expected, { timeout: 30000 });
  }
});

test("File → Start fresh forgets the autosave, history and settings", async ({ page }) => {
  await boot(page);
  const cells = page.locator(".cell");
  const n = await cells.count();
  await type(page, "addNode('only_here')");
  await page.keyboard.press("Shift+Enter");
  await expect(cells).toHaveCount(n + 1);
  await page.evaluate(() => localStorage.setItem("guess.theme", "light"));
  await page.waitForTimeout(2600);                            // the autosave runs 2 s after a change
  await page.reload();
  await expect(page.locator(".console-out")).toContainText("Restored your previous session", { timeout: 60000 });
  page.once("dialog", (d) => void d.accept());
  await menu(page, "File", "#fresh-start");
  await page.waitForURL((u) => !u.search && !u.hash);
  await expect(page.locator(".console-out").getByText(/loaded 402/).first()).toBeVisible({ timeout: 60000 });
  await expect(page.locator(".console-out")).not.toContainText("Restored your previous session");
  expect(await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("guess.")))).toEqual(
    expect.not.arrayContaining(["guess.theme", "guess.history"]));
  expect(await page.evaluate(() => localStorage.getItem("guess.theme"))).toBeNull();
});

test("the code box suggests demo() on a first visit, then commands that fit the graph", async ({ page }) => {
  await boot(page);
  const hint = page.locator(".console-in .cm-placeholder");
  await expect(hint).toHaveText("Gython — new here? try demo()");
  // a later visit: commands for this graph, in turn
  await page.reload();
  await expect(page.locator(".console-out")).toContainText(/loaded/, { timeout: 90_000 });
  await expect(hint).toHaveText(/^Gython — e\.g\. /);
  const seen = new Set<string>();
  for (let i = 0; i < 6; i++) {
    seen.add(await hint.innerText());
    await run(page, "1");
  }
  expect(seen.size).toBeGreaterThan(3);
  // another graph: suggestions use its fields (karate has club, not dept)
  await run(page, 'makeFromGDF("karate.gdf")');
  const karate: string[] = [];
  for (let i = 0; i < 12; i++) {
    karate.push(await hint.innerText());
    await run(page, "1");
  }
  expect(karate.join(" ")).not.toContain("dept");
});
