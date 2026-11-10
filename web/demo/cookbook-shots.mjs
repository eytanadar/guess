// Figures for the cookbooks. A recipe's figure is written in its Markdown as
// ![caption](img/NAME.png); this runs the recipe's python blocks that come
// before the image in the real app (fresh browser; the datasets are built in)
// and saves the graph area as cookbooks/<volume>/img/NAME.png (app-NAME: the
// whole window, for capstone apps with their panels).
//
//   cd web && npm run cookbook-shots                 # every volume
//   npm run cookbook-shots -- sna                    # one volume
//   npm run cookbook-shots -- sna:karate-split       # one figure
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, readFileSync, readdirSync, rmSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const books = resolve(web, "..", "cookbooks");
const tmp = join(here, "out", "cookbook-shots");
mkdirSync(tmp, { recursive: true });
const PORT = 5324, W = 1280, H = 800;
const only = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** [{vol, name, code}] for every figure in every cookbook. */
function figures() {
  const out = [];
  for (const vol of readdirSync(books)) {
    const md = join(books, vol, "cookbook.md");
    if (!existsSync(md)) continue;
    for (const recipe of readFileSync(md, "utf8").split(/^## /m)) {
      const re = /^```python\n([\s\S]*?)^```|!\[[^\]]*\]\(img\/([\w-]+)\.png\)/gm;
      const code = [];
      for (const m of recipe.matchAll(re)) {
        if (m[1] !== undefined) code.push(m[1]);
        else out.push({ vol, name: m[2], code: code.join("\n") });
      }
    }
  }
  return out.filter((f) => !only.length || only.includes(f.vol) || only.includes(`${f.vol}:${f.name}`));
}

let page;
async function run(code, settle = 1200) {
  const cells = page.locator(".cell");
  const n = await cells.count();
  await page.locator(".console-in .cm-content").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator(".console-in .cm-content").fill(code);
  await page.keyboard.press("Shift+Enter");
  await cells.nth(n).waitFor();
  await page.waitForFunction((n) => !document.querySelectorAll(".cell")[n]?.classList.contains("running"), n, { timeout: 180000 });
  const err = await cells.nth(n).locator(".error").count();
  await sleep(settle);
  return err === 0;
}

async function startServer() {
  const proc = spawn("npx", ["vite", "--port", String(PORT), "--strictPort"], { cwd: web, stdio: "ignore", detached: true });
  const stop = () => { try { process.kill(-proc.pid); } catch { /* gone */ } };
  process.on("exit", stop);
  for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => process.exit(130));
  for (let i = 0; i < 120; i++) {
    try { if ((await fetch(`http://localhost:${PORT}/`)).ok) return proc; } catch { /* starting */ }
    await sleep(500);
  }
  throw new Error("dev server did not start");
}

const todo = figures();
const server = await startServer();
const browser = await chromium.launch({ channel: process.env.CI ? undefined : "chrome" });
let failed = 0;
try {
  for (const f of todo) {
    const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2, colorScheme: "light" });
    page = await ctx.newPage();
    await page.goto(`http://localhost:${PORT}/`);
    await page.locator(".console-out").getByText(/loaded 402/).first().waitFor({ timeout: 180000 });
    await page.addStyleTag({ content: "#tip, #tipcard { display: none !important; }" });
    // the datasets are already in the app's file space (fetched on first use)
    // igraph and Graphviz load in the background after start-up: wait for both
    for (let i = 0; i < 60; i++) {
      await run("from guess import igr as __i, gv as __g\nprint('READY' if __i.module() is not None and __g.runner() is not None else 'WAIT')", 100);
      if ((await page.locator(".cell").last().innerText()).includes("READY")) break;
      await sleep(1000);
    }
    await page.keyboard.press("Control+l");    // clear the console, so figures start clean
    await sleep(200);
    try {
      if (!(await run(f.code))) console.error(`  ${f.vol}:${f.name}: the recipe reported an error`);
      // app-* figures (capstones) show the whole window, panels and all
      const png = join(tmp, `${f.name}.png`);
      if (f.name.startsWith("app-")) await page.screenshot({ path: png });
      else await page.screenshot({ path: png, clip: await page.locator("#graph").boundingBox() });
      const dir = join(books, f.vol, "img");
      mkdirSync(dir, { recursive: true });
      execFileSync("ffmpeg", ["-v", "error", "-y", "-i", png, "-vf", "scale='min(1400,iw)':-1", join(dir, `${f.name}.png`)]);
      console.log(`  ${f.vol}/img/${f.name}.png`);
    } catch (e) {
      failed++;
      console.error(`  ${f.vol}:${f.name} failed: ${String(e).split("\n")[0]}`);
    }
    await ctx.close();
  }
} finally {
  await browser.close();
  server.kill();
  rmSync(tmp, { recursive: true, force: true });
}
process.exit(failed ? 1 : 0);
