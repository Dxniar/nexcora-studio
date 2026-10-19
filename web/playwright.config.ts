import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
const python =
  process.env.PYTHON ||
  (process.platform === "win32" && existsSync("../.venv/Scripts/python.exe")
    ? "..\\.venv\\Scripts\\python.exe"
    : "python");
// A fresh headless browser context, never the user's running browser/profile.
const channel =
  process.platform === "win32" &&
  existsSync(
    `${process.env["ProgramFiles(x86)"]}/Microsoft/Edge/Application/msedge.exe`,
  )
    ? "msedge"
    : undefined;
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 8000 },
  reporter: "list",
  outputDir: "./artifacts/test-results",
  use: {
    channel,
    baseURL: "http://127.0.0.1:8765",
    headless: true,
    locale: "ru-RU",
    viewport: { width: 390, height: 844 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: `"${python}" e2e/server.py`,
    url: "http://127.0.0.1:8765/health/live",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
