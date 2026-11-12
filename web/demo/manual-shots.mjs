// Figures for the manual (docs/manual/MANUAL.md). Each figure is taken in a
// fresh browser on the sample graph and saved as docs/manual/img/<name>.png.
// Re-run after UI changes:
//
//   cd web && npm run manual-shots            # all
//   npm run manual-shots -- interface hive    # just these
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
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

/** The graph canvas cropped to what's drawn (plus a margin), as a PNG data URL. */
async function tight(pad = 40) {
  await page.mouse.move(5, 5);  // no hover highlight
  await sleep(300);
  const png = (await page.locator("#graph canvas").first().screenshot()).toString("base64");
  return page.evaluate(async ({ png, pad }) => {
    const img = new Image();
    img.src = "data:image/png;base64," + png;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = img.width; c.height = img.height;
    const g = c.getContext("2d");
    g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height).data;
    const bg = [d[0], d[1], d[2]];
    let x0 = c.width, y0 = c.height, x1 = 0, y1 = 0;
    for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
      const i = (y * c.width + x) * 4;
      if (Math.abs(d[i] - bg[0]) + Math.abs(d[i + 1] - bg[1]) + Math.abs(d[i + 2] - bg[2]) > 30) {
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
    x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad);
    x1 = Math.min(c.width, x1 + pad); y1 = Math.min(c.height, y1 + pad);
    const o = document.createElement("canvas");
    o.width = x1 - x0; o.height = y1 - y0;
    o.getContext("2d").drawImage(c, x0, y0, o.width, o.height, 0, 0, o.width, o.height);
    return o.toDataURL("image/png");
  }, { png, pad });
}

function saveData(dataUrl, name, width) {
  const png = join(tmp, `${name}.png`);
  writeFileSync(png, Buffer.from(dataUrl.split(",")[1], "base64"));
  save(png, name, width);
}

/** Several tight shots in a grid, each with a caption underneath. */
async function grid(parts, cols) {
  return page.evaluate(async ({ parts, cols }) => {
    const imgs = await Promise.all(parts.map(async ([, u]) => { const i = new Image(); i.src = u; await i.decode(); return i; }));
    const cap = 56, gap = 40;
    const cw = Math.max(...imgs.map((i) => i.width)), ch = Math.max(...imgs.map((i) => i.height)) + cap;
    const rows = Math.ceil(imgs.length / cols);
    const W = cols * cw + gap * (cols - 1), H = rows * ch + gap * (rows - 1);
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const g = c.getContext("2d");
    const probe = document.createElement("canvas").getContext("2d");
    probe.drawImage(imgs[0], 0, 0);
    const p = probe.getImageData(1, 1, 1, 1).data;
    g.fillStyle = `rgb(${p[0]},${p[1]},${p[2]})`;
    g.fillRect(0, 0, W, H);
    g.font = "28px ui-monospace, Menlo, monospace";
    g.fillStyle = getComputedStyle(document.body).color;
    g.textAlign = "center";
    imgs.forEach((i, k) => {
      const x = (k % cols) * (cw + gap), y = Math.floor(k / cols) * (ch + gap);
      g.drawImage(i, x + (cw - i.width) / 2, y);
      g.fillText(parts[k][0], x + cw / 2, y + ch - 16);
    });
    return c.toDataURL("image/png");
  }, { parts, cols });
}

/** Zoom out a step, so labels past the outermost nodes stay on the canvas. */
async function zoomOut(dy = 40) {
  const b = await page.locator("#graph").boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  await page.mouse.wheel(0, dy);
  await sleep(500);
}

const CLEAR = "remove(g.nodes)";
const GIANT = "gc = giantComponent()\nremove([n for n in g.nodes if n not in gc])";

/** Wait until the graph stops changing (layouts keep moving after their command returns). */
async function settle(maxMs = 60000) {
  const canvas = page.locator("#graph canvas").first();
  await sleep(1500);                     // animated layouts start a moment after their command
  let prev = await canvas.screenshot(), same = 0;
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs && same < 2) {
    await sleep(700);
    const cur = await canvas.screenshot();
    same = Buffer.compare(prev, cur) === 0 ? same + 1 : 0;
    prev = cur;
  }
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
  // option figures: every value of a field, side by side
  nodeshapes: async () => {
    await run([CLEAR,
      "items = [(1,'1 rectangle'),(2,'2 ellipse'),(3,'3 rounded rectangle'),(11,'11 triangle'),(12,'12 diamond'),",
      "         (13,'13 hexagon'),(14,'14 octagon'),(polygon(5),'polygon(5)'),(polygon(7),'polygon(7)'),(polygon(9),'polygon(9)')]",
      "for i, (st, txt) in enumerate(items):",
      "    n = addNode('s%d' % i, x=(i % 5) * 140, y=(i // 5) * 110, width=44, height=44, style=st)",
      "    n.label = txt; n.labelpos = 'below'; n.labelvisible = true",
      "for i, st in enumerate([4, 5, 6]):",
      "    n = addNode('in%d' % i, x=i * 210 + 70, y=240, width=150, height=46, style=st)",
      "    n.label = 'style %d: label inside' % st; n.labelvisible = true",
      "center()"].join("\n"), 1000);
    saveData(await tight(), "nodeshapes", 1400);
  },
  labelpos: async () => {
    await run([CLEAR,
      "for i, p in enumerate(['right', 'left', 'above', 'below', 'inside', 'outside']):",
      "    n = addNode('p' + p, x=(i % 3) * 200, y=(i // 3) * 120, width=22, height=22)",
      "    if p == 'inside': n.width = 80; n.height = 34",
      "    n.label = p; n.labelpos = p; n.labelvisible = true",
      "center()"].join("\n"), 1000);
    await zoomOut(150);
    saveData(await tight(), "labelpos", 900);
  },
  edgestyles: async () => {
    await run([CLEAR,
      "styles = ['solid','dashed','dotted','taper','wave','double','fuzzy','gradient','flow']",
      "heads = ['triangle','swept','open','diamond','circle','tee','none']",
      "for i, st in enumerate(styles):",
      "    a = addNode('L' + st, x=0, y=i * 40, color='green', label=st, labelpos='left', labelvisible=true)",
      "    b = addNode('R' + st, x=260, y=i * 40, color='orange')",
      "    e = addDirectedEdge(a, b, width=3, color='blue'); e.linestyle = st",
      "for i, h in enumerate(heads):",
      "    a = addNode('A' + h, x=420, y=i * 50)",
      "    b = addNode('B' + h, x=640, y=i * 50, label=h, labelvisible=true)",
      "    e = addDirectedEdge(a, b, width=2.5, color='gray'); e.arrowhead = h",
      "center()"].join("\n"), 1000);
    await zoomOut();
    saveData(await tight(), "edgestyles", 1400);
  },
  edgecolormodes: async () => {
    await run([CLEAR,
      "a = addNode('a', x=0, y=0, color='red', width=18, height=18)",
      "b = addNode('b', x=220, y=0, color='blue', width=18, height=18)",
      "c = addNode('c', x=110, y=90, color='green', width=18, height=18)",
      "for u, v in [(a, b), (b, c), (c, a)]:",
      "    addDirectedEdge(u, v, width=4, color='gray')",
      "center()"].join("\n"), 1000);
    const parts = [];
    for (const m of ["original", "source", "target", "mixed"]) {
      await run(`setEdgeColorMode('${m}')`, 600);
      parts.push([`setEdgeColorMode("${m}")`, await tight(30)]);
    }
    saveData(await grid(parts, 2), "edgecolormodes", 1200);
  },
  enclosures: async () => {
    await run([CLEAR,
      "import random",
      "random.seed(4)",
      "for k, kind in enumerate(['hull', 'box', 'ellipse']):",
      "    ns = [addNode('%s%d' % (kind, i), x=k * 260 + random.uniform(0, 140), y=random.uniform(0, 110), width=14, height=14) for i in range(6)]",
      "    createConvexHull(ns, shape=kind)",
      "    ns[0].label = 'shape=\"%s\"' % kind; ns[0].labelpos = 'outside'; ns[0].labelvisible = true",
      "center()"].join("\n"), 1000);
    await zoomOut(150);
    saveData(await tight(), "enclosures", 1200);
  },
  layouts: async () => {
    await run(`${GIANT}\ncolorize(dept)\ng.edges.width = 0.6\ng.nodes.width = 9\ng.nodes.height = 9`, 500);
    const parts = [];
    for (const cmd of ["forceAtlas2Layout()", "gemLayout()", "kkLayout()",
                       "mdsLayout()", "circleLayout(dept)", "radialLayout(v1)",
                       "concentricLayout(totaldegree)", "multipartiteLayout(dept)", "dualCircleLayout(20)"]) {
      await run(cmd, 500);
      await settle();
      await run("center()", 900);
      await settle();
      parts.push([cmd, await tight(20)]);
    }
    saveData(await grid(parts, 3), "layouts", 1400);
  },
  bundling: async () => {
    await run(`${GIANT}\ncolorize(dept)\nsetEdgeColorMode('source')\ng.edges.width = 0.8`, 500);
    await settle();
    await run("center()", 900);
    const parts = [["no bundling", await tight(20)]];
    for (const cmd of ["bundleEdges()", 'bundleEdges(method="fdeb")', "bundleEdges(dept)"]) {
      await run(`removeBundles()\n${cmd}`, 500);
      await settle();
      parts.push([cmd, await tight(20)]);
    }
    saveData(await grid(parts, 2), "bundling", 1200);
  },
  colorscales: async () => {
    // nodes in a grid, ordered by pagerank: how much of the range each scale colours
    await run([GIANT, "g.edges.visible = false",
      "ns = sorted(g.nodes, key=lambda n: n.pagerank)",
      "for i, n in enumerate(ns):",
      "    n.x = (i % 23) * 20; n.y = (i // 23) * 20; n.width = 15; n.height = 15",
      "center()"].join("\n"), 1200);
    const parts = [];
    for (const sc of ["linear", "log", "sqrt", "rank"]) {
      const cmd = `colorBy(pagerank, yellow, red, '${sc}')`;
      await run(cmd, 800);
      parts.push([cmd, await tight(20)]);
    }
    saveData(await grid(parts, 2), "colorscales", 1200);
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
    await ctx.addInitScript(() => { try { localStorage.setItem("guess.theme", "auto"); } catch {} });
    const p = await ctx.newPage();
    await p.goto(`http://localhost:${PORT}/`);
    await p.locator(".console-out").getByText(/loaded 402/).first().waitFor({ timeout: 120000 });
    await ctx.close();
  }
  for (const [name, fn] of Object.entries(SHOTS)) {
    if (only.length && !only.includes(name)) continue;
    const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2, colorScheme: "light" });
    await ctx.addInitScript(() => { try { localStorage.setItem("guess.theme", "auto"); } catch {} });
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
