const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

(async () => {
  const appRoot = path.resolve(__dirname, "..");
  const outputDir = path.join(appRoot, "qa", "subpath");
  const pageUrl = process.env.GEOAI_SUBPATH_QA_URL || "http://127.0.0.1:8804/smt/#explore";
  const expectedPrefix = new URL(pageUrl).pathname.replace(/[^/]*$/, "");
  const origin = new URL(pageUrl).origin;
  const chromePath = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
  fs.mkdirSync(outputDir, { recursive: true });

  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const consoleErrors = [];
  const requestFailures = [];
  const escapedRequests = [];
  const firstPartyRequests = [];

  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", error => consoleErrors.push(String(error)));
  page.on("request", request => {
    const parsed = new URL(request.url());
    if (parsed.origin !== origin) return;
    firstPartyRequests.push(parsed.pathname);
    if (!parsed.pathname.startsWith(expectedPrefix)) escapedRequests.push(`${request.method()} ${parsed.pathname}`);
  });
  page.on("requestfailed", request => {
    const reason = request.failure()?.errorText || "failed";
    if (request.url().startsWith(origin) && reason !== "net::ERR_ABORTED") requestFailures.push(`${request.method()} ${request.url()}: ${reason}`);
  });

  await page.goto(pageUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.locator("#productQuery").waitFor({ state: "visible", timeout: 30000 });
  await page.locator("#map.leaflet-container").waitFor({ state: "visible", timeout: 30000 });
  await page.waitForTimeout(1500);
  const appBase = await page.evaluate(() => window.GeoAIApp?.basePath);
  const loaded = await page.evaluate(() => ({
    styles: [...document.styleSheets].filter(sheet => sheet.href && new URL(sheet.href).origin === location.origin).map(sheet => new URL(sheet.href).pathname),
    scripts: [...document.scripts].filter(script => script.src && new URL(script.src).origin === location.origin).map(script => new URL(script.src).pathname),
    images: [...document.images].filter(image => image.currentSrc && new URL(image.currentSrc).origin === location.origin).map(image => new URL(image.currentSrc).pathname),
  }));
  const runtime = await page.evaluate(async () => {
    const [health, status, model] = await Promise.all([
      fetch(window.GeoAIApp.url("api/health")).then(response => response.json()),
      fetch(window.GeoAIApp.url("api/system/integration-status")).then(response => response.json()),
      fetch(window.GeoAIApp.url("api/system/model-info")).then(response => response.json()),
    ]);
    return { health, status, model };
  });

  await page.fill("#productQuery", "พื้นที่เกษตรใกล้แหล่งน้ำ 300 เมตร");
  const [agentResponse] = await Promise.all([
    page.waitForResponse(response => response.url().includes(`${expectedPrefix}api/agent/query`) && response.request().method() === "POST", { timeout: 120000 }),
    page.click("#productAskBtn"),
  ]);
  await page.waitForFunction(() => !document.querySelector("#productAskBtn")?.disabled, null, { timeout: 30000 });
  await page.waitForTimeout(750);

  const screenshot = path.join(outputDir, "smt_desktop_1440x900.png");
  await page.screenshot({ path: screenshot, fullPage: false });
  await browser.close();

  const checks = {
    base_path_matches_expected: appBase === expectedPrefix,
    local_styles_use_prefix: loaded.styles.length > 0 && loaded.styles.every(item => item.startsWith(expectedPrefix)),
    local_scripts_use_prefix: loaded.scripts.length > 0 && loaded.scripts.every(item => item.startsWith(expectedPrefix)),
    local_images_use_prefix: loaded.images.length > 0 && loaded.images.every(item => item.startsWith(expectedPrefix)),
    api_health_ok: runtime.health?.ok === true,
    operational_model_a7t: runtime.model?.operational_model === "A7-T",
    taxonomy_revised7: runtime.model?.taxonomy === "Revised 7-class",
    polygon_count_155199: runtime.status?.database?.polygon_count === 155199,
    postgis_read_only: runtime.status?.sql_policy === "read_only_parameterized_allowlist",
    search_api_ok: agentResponse.ok(),
    no_root_escaped_requests: escapedRequests.length === 0,
    no_first_party_request_failures: requestFailures.length === 0,
    no_console_errors: consoleErrors.length === 0,
  };
  const report = { generated_at: new Date().toISOString(), page_url: pageUrl, expected_prefix: expectedPrefix, app_base: appBase, checks, passed: Object.values(checks).every(Boolean), first_party_request_count: firstPartyRequests.length, escaped_requests: escapedRequests, request_failures: requestFailures, console_errors: consoleErrors, loaded, screenshot };
  fs.writeFileSync(path.join(outputDir, "subpath_browser_qa.json"), JSON.stringify(report, null, 2), "utf8");
  process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  if (!report.passed) process.exitCode = 2;
})().catch(error => { console.error(error); process.exitCode = 1; });
