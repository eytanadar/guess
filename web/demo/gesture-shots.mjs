// Screenshots for the in-app "Mouse and gestures" guide (src/gestures.ts).
// Each one is taken in a fresh browser mid-gesture, cropped around the action
// and saved as public/help/<name>.png. Re-run after UI changes:
//
//   cd web && npm run help-shots            # all
//   npm run help-shots -- ring edge         # just these
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const outDir = join(web, "public", "help");
const tmp = join(here, "out", "shots");
mkdirSync(outDir, { recursive: true });
mkdirSync(tmp, { recursive: true });
const PORT = 5322, W = 1280, H = 780;
const only = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let page;
const nodeXY = (name) => page.evaluate((name) => {
  const r = window.__guess.renderer;
  const n = [...r.nodes.values()].find((m) => m.name === name);
  const c = r.app.canvas.getBoundingClientRect(), v = r.getView();
  return [c.left + c.width / 2 + (n.x + n.w / 2 - v[0]) * v[2], c.top + c.height / 2 + (n.y + n.h / 2 - v[1]) * v[2]];
}, name);

async function run(code) {
  const cells = page.locator(".cell");
  const n = await cells.count();
  await page.locator(".console-in .cm-content").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator(".console-in .cm-content").fill(code);
  await page.keyboard.press("Shift+Enter");
  await cells.nth(n).waitFor();
  await page.waitForFunction((n) => !document.querySelectorAll(".cell")[n]?.classList.contains("running"), n, { timeout: 60000 });
  await sleep(700);   // camera tweens
}

/** Press, move in steps (the gesture is now in progress), then call `during`. */
async function midDrag(from, to, during, { alt = false, shift = false } = {}) {
  await page.mouse.move(from[0], from[1]);
  if (alt) await page.keyboard.down("Alt");
  if (shift) await page.keyboard.down("Shift");
  await page.mouse.down();
  for (let k = 1; k <= 14; k++) {
    await page.mouse.move(from[0] + ((to[0] - from[0]) * k) / 14, from[1] + ((to[1] - from[1]) * k) / 14);
    await sleep(25);
  }
  await sleep(250);
  await during();
  await page.mouse.up();
  if (alt) await page.keyboard.up("Alt");
  if (shift) await page.keyboard.up("Shift");
}

/** Crop around a point (clamped to the window) and save as png. */
async function shot(name, [cx, cy], w = 560, h = 360) {
  // stay inside the graph area (not the toolbar or console)
  const gb = await page.locator("#graph").boundingBox();
  w = Math.min(w, gb.width);
  h = Math.min(h, gb.height);
  const x = Math.max(gb.x, Math.min(gb.x + gb.width - w, cx - w / 2)), y = Math.max(gb.y, Math.min(gb.y + gb.height - h, cy - h / 2));
  const png = join(tmp, `${name}.png`);
  await page.screenshot({ path: png, clip: { x, y, width: w, height: h } });
  execFileSync("ffmpeg", ["-v", "error", "-y", "-i", png, "-vf", `scale=${Math.min(w, 560)}:-1`, join(outDir, `${name}.png`)]);
  console.log(`  ${name}.png`);
}

async function shotEl(name, selector, pad = 6) {
  const b = await page.locator(selector).first().boundingBox();
  const png = join(tmp, `${name}.png`);
  await page.screenshot({ path: png, clip: { x: Math.max(0, b.x - pad), y: Math.max(0, b.y - pad), width: Math.min(W, b.width + 2 * pad), height: Math.min(H, b.height + 2 * pad) } });
  execFileSync("ffmpeg", ["-v", "error", "-y", "-i", png, "-vf", "scale='min(560,iw)':-1", join(outDir, `${name}.png`)]);
  console.log(`  ${name}.png`);
}

/** The whole graph area (for small demo graphs). */
async function shotGraph(name) {
  const gb = await page.locator("#graph").boundingBox();
  await shot(name, [gb.x + gb.width / 2, gb.y + gb.height / 2], gb.width, gb.height);
}

const graphCentre = async () => {
  const b = await page.locator("#graph canvas").boundingBox();
  return [b.x + b.width / 2, b.y + b.height / 2];
};

const SHOTS = {
  "hover-edge": async () => {
    await run("center(v128-v14)");
    const [a, b] = [await nodeXY("v128"), await nodeXY("v14")];
    const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    await page.mouse.move(mid[0], mid[1]);
    await sleep(600);
    await shot("hover-edge", mid, 560, 400);
  },
  focus: async () => {
    await run("center(egoNetwork(v128, 1))");
    const p = await nodeXY("v128");
    await page.mouse.click(p[0], p[1]);
    await page.mouse.move(p[0] + 200, p[1] + 200);
    await sleep(400);
    await shot("focus", p, 560, 380);
  },
  box: async () => {
    const [cx, cy] = await graphCentre();
    await midDrag([cx - 160, cy - 110], [cx + 120, cy + 90], () => shot("box", [cx - 20, cy - 10], 560, 380), { shift: true });
  },
  lasso: async () => {
    const [cx, cy] = await graphCentre();
    const from = [cx - 150, cy - 40];
    await page.mouse.move(from[0], from[1]);
    await page.keyboard.down("Alt");
    await page.mouse.down();
    for (let k = 0; k <= 40; k++) {
      const t = (k / 40) * Math.PI * 1.8;
      await page.mouse.move(cx + Math.cos(t + Math.PI) * 150 * (1 + 0.25 * Math.sin(3 * t)), cy + Math.sin(t + Math.PI) * 110);
      await sleep(15);
    }
    await sleep(200);
    await shot("lasso", [cx, cy], 560, 380);
    await page.mouse.up();
    await page.keyboard.up("Alt");
  },
  output: async () => {
    await run("dept == 'dept3'");
    const o = page.locator(".cell .obj", { hasText: "v128" }).last();
    const b = await o.boundingBox();
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
    await sleep(600);
    const png = join(tmp, "output.png");
    await page.screenshot({ path: png, clip: { x: 360, y: 120, width: W - 360, height: 420 } });
    execFileSync("ffmpeg", ["-v", "error", "-y", "-i", png, "-vf", "scale=560:-1", join(outDir, "output.png")]);
    console.log("  output.png");
  },
  ring: async () => {
    await run("makeSimpleRandom(14, 18)\ncircleLayout()\ncolorize(totaldegree)\ng.nodes.size = 64\ng.nodes.labelvisible = true\ncenter()");
    const from = await nodeXY("nd0"), to = await nodeXY("nd5");
    await midDrag(from, [to[0] + 10, to[1] + 10], () => shotGraph("ring"));
  },
  edge: async () => {
    await run("makeSimpleRandom(10, 8)\ncircleLayout()\ng.nodes.size = 64\ng.nodes.labelvisible = true\ncenter()");
    const from = await nodeXY("nd1"), to = await nodeXY("nd6");
    await midDrag(from, [to[0] + 4, to[1] + 4], () => shotGraph("edge"), { alt: true });
  },
  scatter: async () => {
    await run("makeSimpleRandom(12, 6)\naddNodeField('cost', DOUBLE, 0)\naddNodeField('value', DOUBLE, 0)\nfor n in g.nodes:\n    n.cost = (int(n.name[2:]) * 37) % 100\n    n.value = (int(n.name[2:]) * 23) % 50\nscatterLayout(cost, value)\ng.nodes.size = 44\ng.nodes.labelvisible = true\ncenter()");
    const from = await nodeXY("nd3");
    const [cx, cy] = await graphCentre();
    await midDrag(from, [cx + 40, cy - 30], () => shotGraph("scatter"));
  },
  expand: async () => {
    await run("colorize(dept)\nm = collapse(dept == 'dept1', 'dept1')\ncenter(egoNetwork(m, 1))");
    await shot("expand", await nodeXY("dept1"), 560, 380);
  },
  path: async () => {
    await page.click("[data-tool=path]");
    await run("center(v1)");
    let p = await nodeXY("v1");
    await page.mouse.click(p[0], p[1]);
    await run("center(v14)");
    p = await nodeXY("v14");
    await page.mouse.click(p[0], p[1]);
    await page.waitForTimeout(1500);
    await run("center(shortestPath(v1, v14))");
    await page.mouse.move(5, 300);
    await shot("path", await graphCentre(), 600, 420);
  },
  heat: async () => {
    await run("heatMap(v128)\ncenter()");
    await shot("heat", await graphCentre(), 600, 440);
  },
  table: async () => {
    await run("colorize(dept)\nselect(dept == 'dept3')");
    await page.locator(".menu-title", { hasText: "View" }).click();
    await page.locator("#btn-table").click();
    await sleep(800);
    await shotEl("table", "#table-pane");
  },
  filter: async () => {
    await page.locator(".menu-title", { hasText: "View" }).click();
    await page.locator("#btn-filter").click();
    await sleep(500);
    await page.locator("#side-filter select").first().selectOption("e:freq");
    await page.locator("#side-filter .pf-form button").click();
    await sleep(400);
    const r = page.locator("#side-filter .pf-ranges input").first();
    await r.fill("60");
    await r.dispatchEvent("change");
    await sleep(1500);
    await shotEl("filter", "#side-filter", 0);
  },
  timeline: async () => {
    await run("addNodeField('year', INT, 0)\nfor n in g.nodes:\n    n.year = 1995 + n.totaldegree % 12");
    await page.locator(".menu-title", { hasText: "View" }).click();
    await page.locator("#btn-timeline").click();
    await sleep(500);
    await page.locator(".timeline select").first().selectOption("year");
    await sleep(500);
    await page.locator(".tl-slider").fill("5");
    await sleep(1200);
    await shotEl("timeline", "#timeline", 0);
  },
};

async function startServer() {
  // own process group, so the whole server (npx and vite) goes when we exit, even on an error
  const proc = spawn("npx", ["vite", "--port", String(PORT), "--strictPort"], { cwd: web, stdio: "ignore", detached: true });
  const stop = () => { try { process.kill(-proc.pid); } catch { /* already gone */ } };
  process.on("exit", stop);
  for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => process.exit(130));
  for (let i = 0; i < 120; i++) {
    try {
      if ((await fetch(`http://localhost:${PORT}/`)).ok) return proc;
    } catch { /* starting */ }
    await sleep(500);
  }
  throw new Error("dev server did not start");
}

const server = await startServer();
const browser = await chromium.launch({ channel: process.env.CI ? undefined : "chrome" });
try {
  // warm up (Vite may reload once after pre-bundling)
  {
    const ctx = await browser.newContext();
    await ctx.addInitScript(() => { try { localStorage.setItem("guess.theme", "auto"); } catch {} });
    const p = await ctx.newPage();
    await p.goto(`http://localhost:${PORT}/`);
    await p.locator(".console-out").getByText(/loaded 402/).first().waitFor({ timeout: 120000 });
    await ctx.close();
  }
  for (const [name, fn] of Object.entries(SHOTS)) {
    if (only.length && !only.includes(name)) continue;
    const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
    await ctx.addInitScript(() => { try { localStorage.setItem("guess.theme", "auto"); } catch {} });
    page = await ctx.newPage();
    await page.goto(`http://localhost:${PORT}/`);
    await page.locator(".console-out").getByText(/loaded 402/).first().waitFor({ timeout: 120000 });
    // tooltips only where they are the point of the picture
    if (!["hover-edge", "output"].includes(name)) await page.addStyleTag({ content: "#tip { display: none !important; }" });
    await sleep(500);
    try {
      await fn();
    } catch (e) {
      console.error(`  ${name} failed: ${String(e).split("\n")[0]}`);
    }
    await ctx.close();
  }
} finally {
  await browser.close();
  server.kill();
  rmSync(tmp, { recursive: true, force: true });
}
