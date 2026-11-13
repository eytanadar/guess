import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "e2e-tmp52", timeout: 240_000, expect: { timeout: 60_000 }, workers: 1, reporter: "list",
  use: { baseURL: "http://localhost:5352/", viewport: { width: 1280, height: 860 }, channel: "chrome" },
  webServer: { command: "npx vite --port 5352 --strictPort", url: "http://localhost:5352/", reuseExistingServer: false },
});
