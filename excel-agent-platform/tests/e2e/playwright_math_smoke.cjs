const path = require("path");

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
const SCREENSHOT_DIR = path.join(
  ROOT,
  "excel-agent-platform",
  "data",
  "reports",
  "screenshots",
);

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
  await page.setInputFiles('input[type="file"]', "/tmp/math.xlsx");
  await page.fill(
    'textarea[aria-label="Task description"]',
    "calculate the values of columns A and B according to the operation from column Operation and save the result in column Value",
  );
  await page.click('button:has-text("Run")');
  await page.waitForSelector("text=Run completed", { timeout: 60_000 });
  await page.waitForSelector('td:text("1377")', { timeout: 20_000 });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "04_frontend_math_result.png"),
    fullPage: true,
  });

  const downloadPromise = page.waitForEvent("download");
  await page.locator('a[title="Download workbook"]').click();
  const download = await downloadPromise;
  await download.saveAs(path.join(SCREENSHOT_DIR, "ui_download_math.xlsx"));

  await browser.close();
  console.log(`math_screenshot_saved=${SCREENSHOT_DIR}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
