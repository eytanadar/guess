import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";
import { defineConfig, type Plugin } from "vite";

// The dev server serves the built manual (docs/manual/build) at /manuals/ and
// the cookbooks (cookbooks/build) at /manuals/cookbooks/, as the deployed site
// does (scripts/copy-manuals.mjs), so Help → Manual and Help → Cookbooks work.
const MANUAL_DIR = join(import.meta.dirname, "..", "docs", "manual", "build");
const COOKBOOK_DIR = join(import.meta.dirname, "..", "cookbooks", "build");
const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8", ".pdf": "application/pdf", ".epub": "application/epub+zip",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};
const manuals = (): Plugin => ({
  name: "guess-manuals",
  configureServer(server) {
    server.middlewares.use("/manuals", (req, res, next) => {
      let path = decodeURIComponent((req.url ?? "/").split("?")[0]);
      let dir = MANUAL_DIR;
      if (path.startsWith("/cookbooks/data/")) {
        const name = path.slice("/cookbooks/data/".length);
        const found = [join(COOKBOOK_DIR, "..", "data"), join(MANUAL_DIR, "..", "..", "..", "gdfs")]
          .map((d) => join(d, name)).find((f) => !name.includes("/") && existsSync(f));
        if (!found) return next();
        res.setHeader("Content-Type", name.endsWith(".md") ? "text/markdown; charset=utf-8" : "text/plain; charset=utf-8");
        createReadStream(found).pipe(res);
        return;
      }
      if (path === "/cookbooks" || path.startsWith("/cookbooks/")) {
        dir = COOKBOOK_DIR;
        path = path.slice("/cookbooks".length) || "/";
      }
      const rel = normalize(path === "/" ? "/index.html" : path).replace(/^([/\\]|\.\.)+/, "");
      const file = join(dir, rel);
      if (!file.startsWith(dir) || !existsSync(file) || !statSync(file).isFile()) return next();
      res.setHeader("Content-Type", TYPES[extname(file)] ?? "application/octet-stream");
      createReadStream(file).pipe(res);
    });
  },
});

// Cross-origin isolation enables SharedArrayBuffer, which Pyodide uses to
// interrupt long-running Python (the "stop" button / Ctrl-C).
const isolation = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

export default defineConfig({
  // relative asset paths so the build works from any sub-path (e.g. GitHub Pages)
  base: "./",
  server: { headers: isolation, fs: { allow: [".."] } },
  preview: { headers: isolation },
  worker: { format: "es" },
  plugins: [manuals()],
});
