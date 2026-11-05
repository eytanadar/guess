import { defineConfig } from "@playwright/test";

// Locally we use the installed Chrome; CI installs Playwright's Chromium.
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:5318/",
    viewport: { width: 1280, height: 860 },
    channel: process.env.CI ? undefined : "chrome",
    acceptDownloads: true,
  },
  webServer: {
    command: "npx vite --port 5318 --strictPort",
    url: "http://localhost:5318/",
    reuseExistingServer: !process.env.CI,
  },
});
