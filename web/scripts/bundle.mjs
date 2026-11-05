// Build a deployable copy of GUESS: `npm run bundle [-- --offline] [-- --out DIR]`.
//
//   bundle/guess-web-<version>/        the site: upload its contents to any static web server
//   bundle/guess-web-<version>.zip     the same, zipped (and .tar.gz)
//
// --offline also copies Pyodide (the Python runtime, numpy and networkx, ~25 MB)
// into the site, so it needs no CDN at run time (intranets, air-gapped machines).
// Downloads are cached in web/.pyodide-cache.
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const offline = args.includes("--offline");
const outIdx = args.indexOf("--out");
const outRoot = resolve(web, outIdx >= 0 ? args[outIdx + 1] : "bundle");
const { version } = JSON.parse(readFileSync(join(web, "package.json"), "utf8"));
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const name = `guess-web-${version}${offline ? "-offline" : ""}`;
const site = join(outRoot, name);

const run = (cmd, argv, env = {}) => execFileSync(cmd, argv, { cwd: web, stdio: "inherit", env: { ...process.env, ...env } });

console.log(`building ${name}${offline ? " (self-hosted Pyodide)" : ""}…`);
run("npx", ["vite", "build", "--outDir", site, "--emptyOutDir"], offline ? { VITE_PYODIDE_URL: "../pyodide/" } : {});

for (const [src, dst] of [["htaccess", ".htaccess"], ["_headers", "_headers"], ["nginx.conf.example", "nginx.conf.example"], ["Caddyfile.example", "Caddyfile.example"]]) {
  cpSync(join(web, "deploy", src), join(site, dst));
}

if (offline) {
  const cache = join(web, ".pyodide-cache");
  mkdirSync(cache, { recursive: true });
  const fetchTo = async (file) => {
    const cached = join(cache, file);
    if (!existsSync(cached)) {
      const res = await fetch(PYODIDE + file);
      if (!res.ok) throw new Error(`${file}: ${res.status} ${res.statusText}`);
      writeFileSync(cached, Buffer.from(await res.arrayBuffer()));
      console.log(`  downloaded ${file}`);
    }
    mkdirSync(join(site, "pyodide"), { recursive: true });
    cpSync(cached, join(site, "pyodide", file));
  };
  await fetchTo("pyodide-lock.json");
  const lock = JSON.parse(readFileSync(join(cache, "pyodide-lock.json"), "utf8"));
  const files = new Set(["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip"]);
  // numpy with its dependencies; networkx alone (the worker skips its matplotlib chain)
  const want = ["numpy"];
  const seen = new Set();
  while (want.length) {
    const p = want.pop();
    if (seen.has(p)) continue;
    seen.add(p);
    const info = lock.packages[p];
    if (!info) throw new Error(`package ${p} is not in pyodide-lock.json`);
    files.add(info.file_name);
    want.push(...(info.depends ?? []));
  }
  files.add(lock.packages.networkx.file_name);
  for (const f of files) await fetchTo(f);
}

writeFileSync(join(site, "VERSION.txt"), `GUESS for the web ${version}\nbuilt ${new Date().toISOString()}\n${offline ? "Pyodide: self-hosted in pyodide/\n" : `Pyodide: ${PYODIDE}\n`}`);

// archives
for (const ext of [".zip", ".tar.gz"]) rmSync(join(outRoot, name + ext), { force: true });
try {
  execFileSync("tar", ["-czf", `${name}.tar.gz`, name], { cwd: outRoot, stdio: "inherit" });
} catch {
  console.warn("tar not available; skipped .tar.gz");
}
try {
  execFileSync("zip", ["-qr", `${name}.zip`, name], { cwd: outRoot, stdio: "inherit" });
} catch {
  console.warn("zip not available; skipped .zip (the .tar.gz and the folder are there)");
}
console.log(`\ndone: ${site}\n      ${join(outRoot, name)}.{zip,tar.gz}\nUpload the folder's contents to your web server (see docs/DEPLOY.md).`);
