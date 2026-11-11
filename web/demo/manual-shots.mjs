// Figures for the manual (docs/manual/MANUAL.md). Each figure is taken in a
// fresh browser on the sample graph and saved as docs/manual/img/<name>.png.
// Re-run after UI changes:
//
//   cd web && npm run manual-shots            # all
//   npm run manual-shots -- interface hive    # just these
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const outDir = resolve(web, "..", "docs", "manual", "img");
const tmp = join(here, "out", "manual-shots");
mkdirSync(outDir, { recursive: true });
mkdirSync(tmp, { recursive: true });
const PORT = 5323, W = 1280, H = 800;
const only = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let page;

async function run(code, settle = 900) {
  const cells = page.locator(".cell");
  const n = await cells.count();
  await page.locator(".console-in .cm-content").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator(".console-in .cm-content").fill(code);
  await page.keyboard.press("Shift+Enter");
  await cells.nth(n).waitFor();
  await page.waitForFunction((n) => !document.querySelectorAll(".cell")[n]?.classList.contains("running"), n, { timeout: 120000 });
  await sleep(settle); // camera tweens, animations
}

function save(png, name, width) {
  execFileSync("ffmpeg", ["-v", "error", "-y", "-i", png, "-vf", `scale='min(${width},iw)':-1`, join(outDir, `${name}.png`)]);
  console.log(`  ${name}.png`);
}

/** The whole window. */
async function shotWindow(name) {
  const png = join(tmp, `${name}.png`);
  await page.screenshot({ path: png });
  save(png, name, 1600);
}

/** The graph area only. */
async function shotGraph(name) {
  const b = await page.locator("#graph").boundingBox();
  const png = join(tmp, `${name}.png`);
  await page.screenshot({ path: png, clip: b });
  save(png, name, 1200);
}

/** One element (with a little padding). */
async function shotEl(name, selector, pad = 6) {
  const b = await page.locator(selector).first().boundingBox();
  const png = join(tmp, `${name}.png`);
  await page.screenshot({ path: png, clip: { x: Math.max(0, b.x - pad), y: Math.max(0, b.y - pad), width: Math.min(W, b.width + 2 * pad), height: Math.min(H, b.height + 2 * pad) } });
  save(png, name, 1200);
}

const click = (sel) => page.evaluate((sel) => document.querySelector(sel).click(), sel);

const SHOTS = {
  interface: async () => {
    await run("v1", 400);
    await shotWindow("interface");
  },
  "tutorial-depts": async () => {
    await run([
      "g.nodes.visible = 0",
      "dept4 = (dept == 'dept4')",
      "dept9 = (dept == 'dept9')",
      "(dept4, dept9).visible = 1",
      "(dept4 - dept9).color = red",
      "(dept9 - dept9).color = blue",
      "center()",
    ].join("\n"), 1200);
    await shotWindow("tutorial-depts");
  },
  "tutorial-legend": async () => {
    await run([
      "colorize(dept)",
      "deptg = groupBy(dept)",
      "xy = Legend()",
      "for d in deptg: xy.add(d[0], d[0].dept)",
    ].join("\n"), 1200);
    await shotWindow("tutorial-legend");
  },
  menus: async () => {
    await page.locator(".menu-title", { hasText: "Layout" }).click();
    await sleep(300);
    const b = await page.locator(".menu-root", { has: page.locator(".menu-title", { hasText: "Layout" }) }).locator(".menu-pop").boundingBox();
    const png = join(tmp, "menus.png");
    await page.screenshot({ path: png, clip: { x: 0, y: 0, width: Math.min(W, b.x + b.width + 40), height: Math.min(H, b.y + b.height + 12) } });
    save(png, "menus", 1000);
  },
  queries: async () => {
    await run("(freq > 100).color = red\n(freq > 100).width = 5\n(freq > 100).nodes.labelvisible = true\ncenter((freq > 100).nodes)", 1200);
    await shotGraph("queries");
  },
  table: async () => {
    await run("table(dept == 'dept3')", 800);
    await shotWindow("table");
  },
  fa2: async () => {
    await run("louvainClusters()\ncolorize(louvain_class)\nsizeBy(pagerank, 6, 40)\nforceAtlas2Layout(linLog=true, preventOverlap=true)\ncenter()", 1500);
    await shotGraph("fa2");
  },
  hive: async () => {
    await run("hiveLayout(dept, totaldegree)\ncolorize(dept)\ncenter()", 1500);
    await shotGraph("hive");
  },
  "color-by": async () => {
    await run("colorBy(betweenness, yellow, red)\nsizeBy(betweenness, 5, 40, 'log')\nGradientLegend(yellow, red, betweenness.min, betweenness.max)\ncenter()", 1200);
    await shotGraph("color-by");
  },
  hulls: async () => {
    await run([
      "colorize(dept)",
      "for d in ('dept4', 'dept6', 'dept9'):",
      "    grp = dept == d",
      "    createConvexHull(grp, averageColor(grp[0].color, white))",
      "center()",
    ].join("\n"), 1200);
    await shotGraph("hulls");
  },
  chart: async () => {
    await run("colorize(dept)\nplotSizesPie(dept)", 1200);
    await shotWindow("chart");
  },
  slider: async () => {
    await run([
      "lab = Label('')",
      "def hideshow(val):",
      "    g.edges.visible = true",
      "    (freq < val).visible = false",
      "    lab.text = '%d edges visible' % len(Edge.visible == true)",
      "s = Slider(freq.min, freq.max, value=100, label='Minimum frequency', onChange=hideshow)",
      "ui.dock(Panel('Threshold', s, lab))",
      "hideshow(100)",
    ].join("\n"), 1000);
    await shotWindow("slider");
  },
  help: async () => {
    await click("#btn-help");
    await sleep(500);
    await page.locator(".help-search").fill("color");
    await sleep(500);
    await shotWindow("help");
  },
  palette: async () => {
    await click("#btn-palette");
    await sleep(400);
    await page.keyboard.type("lay");
    await sleep(600);
    await shotWindow("palette");
  },
  style: async () => {
    await click("#btn-style");
    await sleep(700);
    await shotWindow("style");
  },
  filter: async () => {
    await click("#btn-filter");
    await sleep(700);
    await shotWindow("filter");
  },
  timeline: async () => {
    await run("addNodeField('year', INTEGER, 0)\nfor n in g.nodes: n.year = 1990 + int(n.name[1:]) % 20\nshowTime(1995, 'year', 5)", 1000);
    await shotWindow("timeline");
  },
  dark: async () => {
    await page.evaluate(() => document.querySelector('[data-theme-choice="dark"]').click());
    await run("colorize(dept)\nlabelBy(name)\nhideOverlappingLabels()", 1000);
    await shotWindow("dark");
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
  {
    // warm up (Vite may reload once after pre-bundling)
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.goto(`http://localhost:${PORT}/`);
    await p.locator(".console-out").getByText(/loaded 402/).first().waitFor({ timeout: 120000 });
    await ctx.close();
  }
  for (const [name, fn] of Object.entries(SHOTS)) {
    if (only.length && !only.includes(name)) continue;
    const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2, colorScheme: "light" });
    page = await ctx.newPage();
    await page.goto(`http://localhost:${PORT}/`);
    await page.locator(".console-out").getByText(/loaded 402/).first().waitFor({ timeout: 120000 });
    await page.addStyleTag({ content: "#tip, #tipcard { display: none !important; }" });
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
