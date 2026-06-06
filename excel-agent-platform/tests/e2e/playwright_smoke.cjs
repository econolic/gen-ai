const path = require("path");
const fs = require("fs");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch (localError) {
    try {
      return require("/tmp/eap-playwright/node_modules/playwright");
    } catch (tmpError) {
      throw new Error(
        "Playwright is not installed. Install it locally or run this script from a Playwright Docker image. " +
          `Local error: ${localError.message}; /tmp fallback error: ${tmpError.message}`,
      );
    }
  }
}

const { chromium } = loadPlaywright();

const ROOT = "/mnt/d/Git/gen-ai";
const FRONTEND_URL = process.env.FRONTEND_URL || "http://localhost:5173";
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const MOUNTAINS_FILE =
  process.env.MOUNTAINS_FILE ||
  path.join(ROOT, "excel-agent-platform", "tests", "fixtures", "mountains_final_project.xlsx");
const SCREENSHOT_DIR = path.join(
  ROOT,
  "excel-agent-platform",
  "data",
  "reports",
  "screenshots",
);

async function main() {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  page.on("console", (msg) => {
    if (["error", "warning"].includes(msg.type())) {
      console.log(`browser:${msg.type()}:${msg.text()}`);
    }
  });
  page.on("pageerror", (err) => console.log(`browser-page-error:${err.message}`));

  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "01_frontend_initial.png"),
    fullPage: true,
  });

  await page.setInputFiles('input[type="file"]', MOUNTAINS_FILE);
  await page.fill(
    'textarea[aria-label="Task description"]',
    "add the height of the mountains in meters to the column height",
  );
  await page.click('button:has-text("Run")');
  await page.waitForSelector("text=/Plan Approval|Run completed|Run failed|Clarification/", {
    timeout: 60_000,
  });
  if (await page.getByRole("heading", { name: "Plan Approval" }).isVisible()) {
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "02_frontend_plan_approval.png"),
      fullPage: true,
    });
    await page.click('button:has-text("Approve")');
  }
  await page.waitForSelector("text=Run completed", { timeout: 60_000 });
  await page.getByText(/wikidata/i).first().waitFor({ timeout: 20_000 });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "03_frontend_mountains_result.png"),
    fullPage: true,
  });

  const downloadPromise = page.waitForEvent("download");
  await page.locator('a[title="Download workbook"]').click();
  const download = await downloadPromise;
  await download.saveAs(path.join(SCREENSHOT_DIR, "ui_download_mountains.xlsx"));

  const docs = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await docs.goto(`${BACKEND_URL}/docs`, { waitUntil: "networkidle" });
  await docs.screenshot({
    path: path.join(SCREENSHOT_DIR, "04_swagger_docs.png"),
    fullPage: true,
  });

  await browser.close();
  console.log(`screenshots_saved=${SCREENSHOT_DIR}`);
}

main().catch(async (error) => {
  console.error(error);
  process.exit(1);
});
