// Narrated demo video of GUESS, rebuilt from demo/script.json.
//
//   cd web && npm run demo                 # → demo/out/guess-demo.mp4 (+ .srt captions)
//   npm run demo -- --script demo/script.json --out demo/out --voice <elevenlabs voice id>
//   npm run demo -- --dry-run              # no audio: estimates timing from word counts
//
// Pipeline: (1) narration for each scene from ElevenLabs (cached by text+voice
// in demo/.cache), (2) a Playwright session drives the real app while the
// browser records video, each scene's actions paced to its narration,
// (3) ffmpeg lays the clips at the scene start times and muxes an MP4.
// Needs ELEVENLABS_API (or ELEVENLABS_API_KEY) in the repo's .env, and ffmpeg.
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const root = resolve(web, "..");
const args = process.argv.slice(2);
const opt = (name, dflt) => {
  const k = args.indexOf(`--${name}`);
  return k >= 0 ? args[k + 1] : dflt;
};
const dryRun = args.includes("--dry-run");
const scriptPath = resolve(web, opt("script", "demo/script.json"));
const outDir = resolve(web, opt("out", "demo/out"));
const cacheDir = join(here, ".cache");
const PORT = Number(opt("port", "5321"));
const W = 1600, H = 900;
const MAX_SECONDS = Number(opt("max-seconds", "300"));

// ---- environment ----------------------------------------------------------------
function loadEnv() {
  const p = join(root, ".env");
  if (!existsSync(p)) return;
  for (const line of readFileSync(p, "utf8").split("\n")) {
    const m = /^\s*([A-Za-z_][\w]*)\s*=\s*(.*)\s*$/.exec(line);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}
loadEnv();
const script = JSON.parse(readFileSync(scriptPath, "utf8"));
const voice = opt("voice", process.env.ELEVENLABS_VOICE || script.voice || "JBFqnCBsd6RMkjVDRZzb");
const ttsModel = script.ttsModel || "eleven_multilingual_v2";
mkdirSync(outDir, { recursive: true });
mkdirSync(cacheDir, { recursive: true });

// ---- 1. narration ---------------------------------------------------------------------
const seconds = (file) => Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file]).toString().trim());

// spoken spellings for words the voice gets wrong ("pronounce" in script.json);
// captions keep the written form
const spoken = (text) => Object.entries(script.pronounce ?? {})
  .reduce((t, [word, say]) => t.replace(new RegExp(`\\b${word}\\b`, "g"), say), text);

async function narrate(written) {
  const text = spoken(written);
  if (dryRun) return { file: null, dur: Math.max(1.5, text.split(/\s+/).length / 2.6) };
  const key = process.env.ELEVENLABS_API || process.env.ELEVENLABS_API_KEY;
  if (!key) throw new Error("ELEVENLABS_API is not set (repo .env)");
  const hash = createHash("sha256").update(`${voice}|${ttsModel}|${text}`).digest("hex").slice(0, 16);
  const file = join(cacheDir, `${hash}.mp3`);
  if (!existsSync(file)) {
    const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${voice}?output_format=mp3_44100_128`, {
      method: "POST",
      headers: { "xi-api-key": key, "Content-Type": "application/json", Accept: "audio/mpeg" },
      body: JSON.stringify({ text, model_id: ttsModel, voice_settings: { stability: 0.45, similarity_boost: 0.8, style: 0.15 } }),
    });
    if (!res.ok) throw new Error(`ElevenLabs ${res.status}: ${await res.text()}`);
    writeFileSync(file, Buffer.from(await res.arrayBuffer()));
    console.log(`  narrated: ${text.slice(0, 60)}…`);
  }
  return { file, dur: seconds(file) };
}

// ---- 2. the app ----------------------------------------------------------------------
async function startServer() {
  const proc = spawn("npx", ["vite", "--port", String(PORT), "--strictPort"], { cwd: web, stdio: "ignore" });
  for (let i = 0; i < 120; i++) {
    try {
      if ((await fetch(`http://localhost:${PORT}/`)).ok) return proc;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  proc.kill();
  throw new Error("dev server did not start");
}

// a visible cursor (headless recordings have none) and a caption strip
const OVERLAY = `
(() => {
  const add = () => {
    const c = document.createElement("div");
    c.id = "demo-cursor";
    c.style.cssText = "position:fixed;z-index:99999;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(255,31,107,.25);border:2px solid #ff1f6b;pointer-events:none;transition:transform .12s;left:-50px;top:-50px";
    document.body.append(c);
    addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", () => (c.style.transform = "scale(.7)"), true);
    addEventListener("mouseup", () => (c.style.transform = ""), true);
    const cap = document.createElement("div");
    cap.id = "demo-caption";
    cap.style.cssText = "position:fixed;z-index:99998;left:50%;bottom:28px;transform:translateX(-50%);max-width:70%;padding:8px 16px;border-radius:8px;background:rgba(20,20,22,.82);color:#fff;font:600 18px system-ui,sans-serif;opacity:0;transition:opacity .3s;pointer-events:none;text-align:center";
    document.body.append(cap);
    const title = document.createElement("div");
    title.id = "demo-title";
    title.style.cssText = "position:fixed;inset:0;z-index:99997;display:flex;flex-direction:column;align-items:center;justify-content:center;background:rgba(250,250,248,.94);color:#1f1f1d;font:700 54px system-ui,sans-serif;letter-spacing:.04em;opacity:0;transition:opacity .6s;pointer-events:none";
    document.body.append(title);
  };
  if (document.body) add(); else addEventListener("DOMContentLoaded", add);
})();`;

let page;
let mouse = [W / 2, H / 2];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function moveTo(x, y, ms = 450) {
  const steps = Math.max(8, Math.round(ms / 16));
  const [x0, y0] = mouse;
  for (let k = 1; k <= steps; k++) {
    const t = k / steps, e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
    await page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e);
    await sleep(ms / steps);
  }
  mouse = [x, y];
}

async function moveToEl(locator) {
  const b = await locator.boundingBox();
  if (!b) throw new Error("element not visible");
  await moveTo(b.x + b.width / 2, b.y + b.height / 2);
}

async function clickEl(locator) {
  await moveToEl(locator);
  await locator.click();
}

/** Screen position of a node's centre (dev build exposes window.__guess). */
const nodeXY = (name) => page.evaluate((name) => {
  const r = window.__guess.renderer;
  const n = [...r.nodes.values()].find((m) => m.name === name);
  if (!n) throw new Error(`no node ${name}`);
  const c = r.app.canvas.getBoundingClientRect(), v = r.getView();
  return [c.left + c.width / 2 + (n.x + n.w / 2 - v[0]) * v[2], c.top + c.height / 2 + (n.y + n.h / 2 - v[1]) * v[2]];
}, name);

/** Screen centre of the biggest group of nodes coloured differently from `name`. */
const otherGroupXY = (name) => page.evaluate((name) => {
  const r = window.__guess.renderer;
  const nodes = [...r.nodes.values()].filter((m) => m.v);
  const me = nodes.find((m) => m.name === name);
  const by = new Map();
  for (const m of nodes) if (m.c !== me.c) (by.get(m.c) ?? by.set(m.c, []).get(m.c)).push(m);
  const grp = [...by.values()].sort((a, b) => b.length - a.length)[0];
  const cx = grp.reduce((s, m) => s + m.x + m.w / 2, 0) / grp.length, cy = grp.reduce((s, m) => s + m.y + m.h / 2, 0) / grp.length;
  const c = r.app.canvas.getBoundingClientRect(), v = r.getView();
  return [c.left + c.width / 2 + (cx - v[0]) * v[2], c.top + c.height / 2 + (cy - v[1]) * v[2]];
}, name);

async function runCode(code, visible = true) {
  const cells = page.locator(".cell");
  const before = await cells.count();
  const editor = page.locator(".console-in .cm-content");
  await clickEl(editor);
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Backspace");
  if (visible && !code.includes("\n") && code.length < 90) await page.keyboard.type(code, { delay: 28 });
  else await editor.fill(code);
  await sleep(250);
  await page.keyboard.press("Shift+Enter");
  await cells.nth(before).waitFor();
  await page.waitForFunction((n) => !document.querySelectorAll(".cell")[n]?.classList.contains("running"), before, { timeout: 120000 });
}

async function drag(from, to, { alt = false, ms = 1100 } = {}) {
  await moveTo(from[0], from[1]);
  if (alt) await page.keyboard.down("Alt");
  await page.mouse.down();
  await moveTo(to[0], to[1], ms);
  await sleep(300);
  await page.mouse.up();
  if (alt) await page.keyboard.up("Alt");
}

/** The action vocabulary script.json uses (see demo/README.md). */
async function act(a) {
  if (a.run !== undefined) return runCode(a.run, a.visible !== false);
  if (a.wait !== undefined) return sleep(a.wait);
  if (a.caption !== undefined) return page.evaluate((t) => {
    const c = document.getElementById("demo-caption");
    c.textContent = t;
    c.style.opacity = t ? "1" : "0";
  }, a.caption);
  if (a.title !== undefined) return page.evaluate(([t, sub]) => {
    const el = document.getElementById("demo-title");
    el.innerHTML = t ? `<div>${t}</div>${sub ? `<div style="font:400 24px system-ui;margin-top:14px;color:#6d6c66">${sub}</div>` : ""}` : "";
    el.style.opacity = t ? "1" : "0";
  }, [a.title, a.subtitle ?? ""]);
  if (a.menu) {
    const titleEl = page.locator(".menu-title", { hasText: a.menu[0] });
    if ((await titleEl.getAttribute("aria-expanded")) !== "true") await clickEl(titleEl);
    else await moveToEl(titleEl);
    await sleep(500);
    if ((await titleEl.getAttribute("aria-expanded")) !== "true") {
      await titleEl.click();   // the click closed a menu that was still open: open it again
      await sleep(300);
    }
    const pop = page.locator(".menu-root", { has: page.locator(".menu-title", { hasText: a.menu[0] }) }).locator(".menu-pop");
    const item = a.menu[1].startsWith("#") || a.menu[1].startsWith("[") ? pop.locator(a.menu[1]) : pop.getByRole("menuitem", { name: a.menu[1] });
    // go straight down into the menu first: crossing other titles would switch menus
    const ib = await item.boundingBox();
    if (ib) await moveTo(mouse[0], ib.y + ib.height / 2, 250);
    if (a.close) {
      await moveToEl(item);
      await sleep(600);
      await page.keyboard.press("Escape");
      return;
    }
    return clickEl(item);
  }
  if (a.click) return clickEl(page.locator(a.click).first());
  if (a.select) return page.locator(a.select[0]).first().selectOption(a.select[1]);
  if (a.fill) {
    await clickEl(page.locator(a.fill[0]).first());
    return page.locator(a.fill[0]).first().pressSequentially(a.fill[1], { delay: 40 });
  }
  if (a.key) return page.keyboard.press(a.key);
  if (a.typeKeys) return page.keyboard.type(a.typeKeys, { delay: 70 });
  if (a.hoverNode) {
    const [x, y] = await nodeXY(a.hoverNode);
    return moveTo(x, y, 600);
  }
  if (a.hoverOutput) return moveToEl(page.locator(".cell .obj, .cell .grp", { hasText: a.hoverOutput }).last());
  if (a.hoverText) return moveToEl(page.locator(a.hoverText[0], { hasText: a.hoverText[1] }).last());
  if (a.dragNode) return drag(await nodeXY(a.dragNode[0]), await nodeXY(a.dragNode[1]), { alt: !!a.alt });
  if (a.dragIntoGroup) return drag(await nodeXY(a.dragIntoGroup), await otherGroupXY(a.dragIntoGroup), { ms: 1600 });
  if (a.zoom) {
    const b = await page.locator("#graph canvas").boundingBox();
    await moveTo(b.x + b.width / 2, b.y + b.height / 2);
    for (let i = 0; i < 12; i++) {
      await page.mouse.wheel(0, a.zoom > 0 ? -60 : 60);
      await sleep(40);
    }
    return;
  }
  throw new Error(`unknown action ${JSON.stringify(a)}`);
}

// ---- 3. record ---------------------------------------------------------------------------
async function record(scenes) {
  const server = await startServer();
  const tmp = join(outDir, "raw");
  rmSync(tmp, { recursive: true, force: true });
  const browser = await chromium.launch({ channel: process.env.CI ? undefined : "chrome" });
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, recordVideo: { dir: tmp, size: { width: W, height: H } }, colorScheme: script.theme === "dark" ? "dark" : "light" });
  await ctx.addInitScript(OVERLAY);
  page = await ctx.newPage();
  const t0 = Date.now();
  // warm up first: Vite may reload the page once after pre-bundling dependencies
  await page.goto(`http://localhost:${PORT}/`);
  await page.locator(".console-out").getByText(/loaded 402/).first().waitFor({ timeout: 120000 });
  await sleep(1500);
  await page.reload();
  await page.locator(".console-out").getByText(/loaded 402/).first().waitFor({ timeout: 120000 });
  for (const a of script.setup ?? []) await act(a);
  await sleep(800);
  const times = [];
  for (const sc of scenes) {
    const start = (Date.now() - t0) / 1000;
    const minEnd = Date.now() + sc.audio.dur * 1000 + (sc.pause ?? 600);
    console.log(`  scene ${sc.id} (${sc.audio.dur.toFixed(1)}s)`);
    for (const a of sc.actions ?? []) {
      try {
        await act(a);
      } catch (e) {
        const shot = join(outDir, `failed-${sc.id}.png`);
        await page.screenshot({ path: shot });
        throw new Error(`scene ${sc.id}, action ${JSON.stringify(a)}: ${String(e).split("\n")[0]} (screenshot: ${shot})`);
      }
    }
    const left = minEnd - Date.now();
    if (left > 0) await sleep(left);
    times.push({ id: sc.id, start, end: (Date.now() - t0) / 1000 });
  }
  await sleep(1200);
  const video = page.video();
  await ctx.close();
  await browser.close();
  server.kill();
  const raw = await video.path();
  const firstStart = times[0].start;
  return { raw, times, trim: Math.max(0, firstStart - 0.4) };
}

// ---- 4. mix and mux ---------------------------------------------------------------------
function srtTime(s) {
  const ms = Math.round(s * 1000);
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`;
}

// Captions: each scene's narration in short cues (at most two lines of ~42
// characters, broken at sentences, then clauses, then words). A cue's time is
// its share of the scene's characters, snapped to the nearest pause that
// ffmpeg hears in the narration, so cues change where the voice breathes.
const LINE = 42, CUE = 2 * LINE;

function splitCues(text) {
  const sentences = text.match(/[^.!?]+[.!?]+["')]*\s*|[^.!?]+$/g) ?? [text];
  const cues = [];
  // a clause too long for one cue: split it in two at the best break, repeatedly
  const pushWords = (part) => {
    if (fits(part)) { cues.push(part); return; }
    const [x, y] = bestBreak(part, Infinity);
    pushWords(x);
    pushWords(y);
  };
  for (const sen of sentences.map((x) => x.trim()).filter(Boolean)) {
    if (fits(sen)) { cues.push(sen); continue; }
    // clauses: after , ; : — keeping the punctuation; merge small ones back up to CUE
    const clauses = sen.split(/(?<=[,;:—])\s+/);
    let cur = "";
    for (const c of clauses) {
      if (cur && !fits(cur + " " + c)) { cues.push(cur); cur = ""; }
      if (!fits(c)) { pushWords(c); continue; }
      cur = cur ? cur + " " + c : c;
    }
    if (cur) cues.push(cur);
  }
  // fold a dangling short cue into its neighbour when they fit together
  for (let i = cues.length - 1; i > 0; i--) {
    if (cues[i].length < 16 && fits(cues[i - 1] + " " + cues[i])) cues.splice(i - 1, 2, cues[i - 1] + " " + cues[i]);
  }
  return cues.map(twoLines);
}

// words a line or cue should not end on ("… with a / frequency")
const WEAK = new Set("a an the of to in on at by for with and or but so that which who over one two its their our we".split(" "));

/** Split text in two at the best word boundary: balanced, after punctuation if
 *  possible, never after a weak word; each half at most `max` long if it can be. */
function bestBreak(text, max) {
  const words = text.split(" ");
  let best = [text, ""], score = Infinity;
  for (let k = 1; k < words.length; k++) {
    const a = words.slice(0, k).join(" "), b = words.slice(k).join(" ");
    const last = words[k - 1].toLowerCase().replace(/[^a-z]/g, "");
    let sc = Math.abs(a.length - b.length);
    if (/[,;:—.]$/.test(a)) sc -= 12;
    if (WEAK.has(last)) sc += 25;
    if (Math.max(a.length, b.length) > max) sc += 100;
    if (sc < score) { score = sc; best = [a, b]; }
  }
  return best;
}

/** Does the text make a good cue: one line, or two lines of at most LINE
 *  characters that don't break after a weak word? */
function fits(text) {
  if (text.length <= LINE) return true;
  if (text.length > CUE) return false;
  const [a, b] = bestBreak(text, LINE);
  return a.length <= LINE && b.length <= LINE && !WEAK.has(a.split(" ").pop().toLowerCase().replace(/[^a-z]/g, ""));
}

/** Break a cue into at most two balanced lines. */
function twoLines(cue) {
  if (cue.length <= LINE) return cue;
  return bestBreak(cue, LINE).join("\n");
}

/** Midpoints of the pauses in an audio file (seconds). */
function pauses(file) {
  if (!file) return [];
  const r = spawnSync("ffmpeg", ["-hide_banner", "-i", file, "-af", "silencedetect=noise=-32dB:d=0.12", "-f", "null", "-"], { encoding: "utf8" });
  const out = [];
  let start = null;
  for (const line of (r.stderr || "").split("\n")) {
    const a = /silence_start: ([\d.]+)/.exec(line), b = /silence_end: ([\d.]+)/.exec(line);
    if (a) start = Number(a[1]);
    if (b && start !== null) { out.push((start + Number(b[1])) / 2); start = null; }
  }
  return out;
}

function sceneCues(sc) {
  const cues = splitCues(sc.narration);
  const dur = sc.audio.dur;
  const total = cues.reduce((s, c) => s + c.length, 0);
  const gaps = pauses(sc.audio.file);
  const bounds = [0];
  let acc = 0;
  for (let i = 0; i < cues.length - 1; i++) {
    acc += cues[i].length;
    let t = (acc / total) * dur;
    const near = gaps.filter((g) => Math.abs(g - t) < 0.9 && g > bounds[bounds.length - 1] + 0.6);
    if (near.length) t = near.reduce((a, b) => (Math.abs(b - t) < Math.abs(a - t) ? b : a));
    bounds.push(Math.max(t, bounds[bounds.length - 1] + 0.6));
  }
  bounds.push(dur);
  return cues.map((text, i) => ({ start: bounds[i], end: bounds[i + 1], text }));
}

function writeCaptions(out, times, scenes, trim) {
  const cues = [];
  scenes.forEach((sc, i) => {
    const t0 = times[i].start - trim;
    const last = Math.min(times[i].end, times[i].start + sc.audio.dur + 0.3) - trim;
    const sc_ = sceneCues(sc);
    sc_.forEach((c, k) => cues.push({ start: t0 + c.start, end: k === sc_.length - 1 ? last : t0 + c.end, text: c.text }));
  });
  const srt = cues.map((c, k) => `${k + 1}\n${srtTime(c.start)} --> ${srtTime(c.end)}\n${c.text}\n`).join("\n");
  writeFileSync(out.replace(/\.mp4$/, ".srt"), srt);
}

function mux(raw, times, scenes, trim) {
  const out = join(outDir, script.output || "guess-demo.mp4");
  const inputs = [], filters = [];
  scenes.forEach((sc, i) => {
    if (!sc.audio.file) return;
    inputs.push("-i", sc.audio.file);
    const ms = Math.max(0, Math.round((times[i].start - trim) * 1000));
    filters.push(`[${inputs.length / 2}:a]adelay=${ms}|${ms}[a${i}]`);
  });
  const labels = filters.map((f) => f.slice(f.lastIndexOf("[")));
  const args = ["-y", "-ss", String(trim), "-i", raw, ...inputs];
  if (labels.length) {
    args.push("-filter_complex", `${filters.join(";")};${labels.join("")}amix=inputs=${labels.length}:normalize=0:dropout_transition=0[aout]`,
      "-map", "0:v", "-map", "[aout]", "-c:a", "aac", "-b:a", "160k");
  } else {
    args.push("-map", "0:v");
  }
  args.push("-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out);
  execFileSync("ffmpeg", args, { stdio: ["ignore", "ignore", "inherit"] });
  writeCaptions(out, times, scenes, trim);
  return out;
}

// ---- main -----------------------------------------------------------------------------
console.log(`script: ${scriptPath} (${script.scenes.length} scenes), voice ${voice}`);
const scenes = [];
for (const sc of script.scenes) scenes.push({ ...sc, audio: await narrate(sc.narration) });
const talk = scenes.reduce((s, sc) => s + sc.audio.dur + (sc.pause ?? 600) / 1000, 0);
console.log(`narration ≈ ${Math.round(talk)} s`);
if (talk > MAX_SECONDS && !args.includes("--force")) {
  throw new Error(`narration is ${Math.round(talk)} s, over the ${MAX_SECONDS} s limit: shorten the script (or --force)`);
}
if (args.includes("--captions")) {
  // rewrite the .srt for the existing video from timing.json (no recording)
  const { times, trim } = JSON.parse(readFileSync(join(outDir, "timing.json"), "utf8"));
  if (times.length !== scenes.length || times.some((t, i) => t.id !== scenes[i].id)) {
    throw new Error("script.json's scenes differ from the last recording (timing.json): run npm run demo");
  }
  const out = join(outDir, script.output || "guess-demo.mp4");
  writeCaptions(out, times, scenes, trim);
  console.log(`wrote ${out.replace(/\.mp4$/, ".srt")}`);
  process.exit(0);
}
const { raw, times, trim } = await record(scenes);
const total = times[times.length - 1].end - trim;
const out = mux(raw, times, scenes, trim);
writeFileSync(join(outDir, "timing.json"), JSON.stringify({ trim, times, total }, null, 1));
console.log(`\nwrote ${out} (${Math.round(total)} s) and captions ${out.replace(/\.mp4$/, ".srt")}`);
if (total > MAX_SECONDS) console.warn(`warning: the video is ${Math.round(total)} s, over ${MAX_SECONDS} s`);
