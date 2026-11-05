import { defineConfig } from "vite";

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
});
