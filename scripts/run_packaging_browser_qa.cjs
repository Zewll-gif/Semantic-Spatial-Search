const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

(async () => {
const appRoot = path.resolve(__dirname, "..");
const outputDir = path.join(appRoot, "qa", "self_contained");
const baseUrl = process.env.GEOAI_QA_BASE_URL || "http://127.0.0.1:8803";
const chromePath = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
fs.mkdirSync(outputDir, { recursive: true });

const browser = await chromium.launch({ headless: true, executablePath: chromePath });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const consoleErrors = [];
const localRequestFailures = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => consoleErrors.push(String(error)));
page.on("requestfailed", (request) => {
  if (request.url().startsWith(baseUrl) && request.failure()?.errorText !== "net::ERR_ABORTED") {
    localRequestFailures.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText || "failed"}`);
  }
});

async function layoutSnapshot() {
  return page.evaluate(() => {
    const selectors = ["#scopeSelect", "#productSearch", ".map-toolbar", "#legendToggle", ".leaflet-control-layers"];
    const elements = Object.fromEntries(selectors.map((selector) => {
      const element = document.querySelector(selector);
      if (!element) return [selector, null];
      const rect = element.getBoundingClientRect();
      return [selector, { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height, visible: rect.width > 0 && rect.height > 0 }];
    }));
    return {
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      clientHeight: document.documentElement.clientHeight,
      elements,
    };
  });
}

await page.goto(`${baseUrl}/#explore`, { waitUntil: "domcontentloaded", timeout: 30000 });
await page.locator("#productQuery").waitFor({ state: "visible", timeout: 30000 });
await page.locator("#map.leaflet-container").waitFor({ state: "visible", timeout: 30000 });
await page.waitForTimeout(1500);

const runtime = await page.evaluate(async () => {
  const [health, integration, model] = await Promise.all([
    fetch("/api/health").then((response) => response.json()),
    fetch("/api/system/integration-status").then((response) => response.json()),
    fetch("/api/system/model-info").then((response) => response.json()),
  ]);
  return { health, integration, model };
});

await page.fill("#productQuery", "พื้นที่เกษตรใกล้แหล่งน้ำ 300 เมตร");
const [agentResponse] = await Promise.all([
  page.waitForResponse((response) => response.url().includes("/api/agent/query") && response.request().method() === "POST", { timeout: 120000 }),
  page.click("#productAskBtn"),
]);
const agentPayload = await agentResponse.json();
await page.waitForFunction(() => !document.querySelector("#productAskBtn")?.disabled, null, { timeout: 30000 });
await page.waitForTimeout(1000);

const desktop = await layoutSnapshot();
const desktopResultCards = await page.locator("#productResultCards > *").count();
const desktopOverlayCount = await page.locator(".leaflet-overlay-pane svg path, .result-numbered-marker, .result-number-marker").count();
const desktopError = ((await page.locator("#productError").textContent().catch(() => "")) || "").trim();
const desktopScreenshot = path.join(outputDir, "desktop_1440x900.png");
await page.screenshot({ path: desktopScreenshot, fullPage: false });

await page.setViewportSize({ width: 390, height: 844 });
await page.goto(`${baseUrl}/#explore`, { waitUntil: "domcontentloaded", timeout: 30000 });
await page.locator("#productQuery").waitFor({ state: "visible", timeout: 30000 });
await page.locator("#map.leaflet-container").waitFor({ state: "visible", timeout: 30000 });
await page.waitForTimeout(1200);
const mobile = await layoutSnapshot();
const mobileScreenshot = path.join(outputDir, "mobile_390x844.png");
await page.screenshot({ path: mobileScreenshot, fullPage: false });

await browser.close();

function withinViewport(box, viewportWidth) {
  return box == null || !box.visible || (box.left >= -1 && box.right <= viewportWidth + 1);
}

const checks = {
  health_ok: runtime.health?.ok === true,
  operational_model_a7t: runtime.model?.operational_model === "A7-T",
  taxonomy_revised7: runtime.model?.taxonomy === "Revised 7-class",
  polygon_count_155199: runtime.integration?.database?.polygon_count === 155199,
  postgis_read_only: runtime.integration?.sql_policy === "read_only_parameterized_allowlist",
  deterministic_browser_qa: runtime.integration?.llm?.enabled === false,
  agent_http_ok: agentResponse.ok(),
  agent_has_results: desktopResultCards > 0,
  desktop_result_cards: desktopResultCards > 0,
  desktop_map_overlays: desktopOverlayCount > 0,
  desktop_no_error_banner: desktopError.length === 0,
  desktop_no_horizontal_overflow: desktop.scrollWidth <= desktop.clientWidth,
  mobile_no_horizontal_overflow: mobile.scrollWidth <= mobile.clientWidth,
  mobile_controls_in_viewport: Object.values(mobile.elements).every((box) => withinViewport(box, mobile.clientWidth)),
  no_console_errors: consoleErrors.length === 0,
  no_local_request_failures: localRequestFailures.length === 0,
};

const report = {
  generated_at: new Date().toISOString(),
  url: `${baseUrl}/#explore`,
  desktop_viewport: "1440x900",
  mobile_viewport: "390x844",
  checks,
  passed: Object.values(checks).every(Boolean),
  desktop: { ...desktop, result_cards: desktopResultCards, overlay_count: desktopOverlayCount, screenshot: desktopScreenshot },
  mobile: { ...mobile, screenshot: mobileScreenshot },
  console_errors: consoleErrors,
  local_request_failures: localRequestFailures,
  agent: { status: agentPayload?.status || null, mode: agentPayload?.mode || null, count: agentPayload?.count || agentPayload?.matching_source_features?.length || agentPayload?.results?.length || 0 },
};
fs.writeFileSync(path.join(outputDir, "browser_qa.json"), JSON.stringify(report, null, 2), "utf8");
process.stdout.write(JSON.stringify(report, null, 2) + "\n");
if (!report.passed) process.exitCode = 2;
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
