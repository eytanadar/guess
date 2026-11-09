import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";
import { defineConfig, type Plugin } from "vite";

// The dev server serves the built manual (docs/manual/build) at /manuals/, as
// the deployed site does (scripts/copy-manuals.mjs), so Help → Manual works.
const MANUAL_DIR = join(import.meta.dirname, "..", "docs", "manual", "build");
const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8", ".pdf": "application/pdf", ".epub": "application/epub+zip",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};
const manuals = (): Plugin => ({
  name: "guess-manuals",
  configureServer(server) {
    server.middlewares.use("/manuals", (req, res, next) => {
      const path = decodeURIComponent((req.url ?? "/").split("?")[0]);
      const rel = normalize(path === "/" ? "/index.html" : path).replace(/^([/\\]|\.\.)+/, "");
      const file = join(MANUAL_DIR, rel);
      if (!file.startsWith(MANUAL_DIR) || !existsSync(file) || !statSync(file).isFile()) return next();
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
