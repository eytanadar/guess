// Copy the built manual (docs/manual/build: index.html and the PDF, HTML, EPUB
// and Word files) into <site>/manuals/, which Help → Manual opens, and the
// cookbooks (cookbooks/build: index.html and each book's HTML, PDF and EPUB)
// into <site>/manuals/cookbooks/, which Help → Cookbooks opens.
//
//   node scripts/copy-manuals.mjs dist          # after vite build (npm run build does this)
//   node scripts/copy-manuals.mjs dist --build  # build the manual and cookbooks first if missing
//
// The manual is built by docs/manual/build.py (pandoc + XeLaTeX). Without it the
// site still works; the Manual menu item then shows a 404, so we warn.
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(web, "..");
export const manualBuild = join(root, "docs", "manual", "build");
export const cookbookBuild = join(root, "cookbooks", "build");
const KEEP = /^(index\.html|GUESS-manual\.(pdf|html|epub|docx))$/;
const KEEP_COOKBOOK = /^(index\.html|GUESS-for-[\w-]+\.(pdf|html|epub))$/;

function python() {
  const venv = join(root, "py", ".venv", "bin", "python");
  return existsSync(venv) ? venv : "python3";
}

function buildManual() {
  execFileSync(python(), [join(root, "docs", "manual", "build.py")], { stdio: "inherit" });
}

function buildCookbooks() {
  execFileSync(python(), [join(root, "cookbooks", "tools", "build.py")], { stdio: "inherit" });
}

/** Copy the cookbooks into site/manuals/cookbooks; returns the number of files copied. */
export function copyCookbooks(site, { build = false } = {}) {
  if (!existsSync(join(cookbookBuild, "index.html")) && build) {
    try {
      buildCookbooks();
    } catch (e) {
      console.warn(`could not build the cookbooks: ${String(e).split("\n")[0]}`);
    }
  }
  if (!existsSync(join(cookbookBuild, "index.html"))) {
    console.warn("warning: no built cookbooks (cookbooks/tools/build.py); Help → Cookbooks will be missing");
    return 0;
  }
  const dest = join(site, "manuals", "cookbooks");
  mkdirSync(dest, { recursive: true });
  let n = 0;
  for (const f of readdirSync(cookbookBuild)) {
    if (!KEEP_COOKBOOK.test(f)) continue;
    copyFileSync(join(cookbookBuild, f), join(dest, f));
    n++;
  }
  // the data files, under their own names, for the index pages' download links
  const data = join(dest, "data");
  mkdirSync(data, { recursive: true });
  let d = 0;
  for (const dir of [join(root, "cookbooks", "data"), join(root, "gdfs")]) {
    for (const f of readdirSync(dir)) {
      if (!/\.(gdf|csv|txt)$/.test(f) && f !== "README.md") continue;
      if (dir.endsWith("gdfs") && existsSync(join(data, f))) continue;
      copyFileSync(join(dir, f), join(data, f));
      d++;
    }
  }
  console.log(`cookbooks: ${n} files and ${d} data files → ${dest}`);
  return n;
}

/** Copy the manual into site/manuals; returns the number of files copied. */
export function copyManuals(site, { build = false } = {}) {
  if (!existsSync(join(manualBuild, "index.html"))) {
    if (build) {
      try {
        buildManual();
      } catch (e) {
        console.warn(`could not build the manual: ${String(e).split("\n")[0]}`);
      }
    }
    if (!existsSync(join(manualBuild, "index.html"))) {
      console.warn("warning: no built manual (python3 docs/manual/build.py); the site's manuals/ link will be missing");
      return 0;
    }
  }
  const dest = join(site, "manuals");
  mkdirSync(dest, { recursive: true });
  let n = 0;
  for (const f of readdirSync(manualBuild)) {
    if (!KEEP.test(f)) continue;
    copyFileSync(join(manualBuild, f), join(dest, f));
    n++;
  }
  console.log(`manuals: ${n} files → ${dest}`);
  copyCookbooks(site, { build });
  return n;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const site = resolve(web, args.find((a) => !a.startsWith("--")) ?? "dist");
  copyManuals(site, { build: args.includes("--build") });
}
