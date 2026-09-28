import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const outputDir = "D:/499_2/499_Thesis_Final_PUBLISH/FINAL_A7T_LOCK/07_POSTGIS_LLM_FINAL/05_BROWSER_QA";
fs.mkdirSync(outputDir, { recursive: true });
const cases = [
  ["01", "ค้นหาพื้นที่สิ่งปลูกสร้าง", "search_landcover"],
  ["02", "หาพื้นที่เกษตรมากกว่า 5 ไร่", "filter_by_area"],
  ["03", "หาพื้นที่เกษตรใกล้น้ำไม่เกิน 300 เมตร", "find_nearby"],
  ["04", "ขอรายละเอียด feature 155177", "get_feature_details"],
  ["05", "แสดงหลักฐานของ feature 155177", "get_evidence"],
];

const browser = await chromium.launch({
  headless: true,
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const consoleErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => consoleErrors.push(String(error)));

const rows = [];
for (const provider of ["openai", "deepseek"]) {
  for (const [index, query, expectedTool] of cases) {
    await page.goto("http://127.0.0.1:8795/#explore", { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.locator("#productQuery").waitFor({ state: "visible", timeout: 30000 });
    await page.waitForTimeout(1200);
    await page.selectOption("#llmProviderSelect", provider);
    await page.fill("#productQuery", query);
    const [agentResponse] = await Promise.all([
      page.waitForResponse((response) => response.url().includes("/api/agent/query") && response.request().method() === "POST", { timeout: 240000 }),
      page.click("#productAskBtn"),
    ]);
    const agentData = await agentResponse.json().catch(() => ({}));
    await page.waitForFunction(() => !document.querySelector("#productAskBtn")?.disabled, null, { timeout: 30000 });
    await page.waitForTimeout(750);
    const errorText = (await page.locator("#productError").textContent().catch(() => "")) || "";
    const details = page.locator("#productEvidence details").last();
    if (await details.count()) {
      await details.locator("summary").click();
    }
    const detailText = (await page.locator("#productEvidence").textContent()) || "";
    const providerActual = String(agentData?.llm?.provider || agentData?.provider || "").toLowerCase();
    const trace = agentData?.tool_trace || agentData?.tool_calls || agentData?.tool_calls_used || [];
    const actualTools = trace.map((item) => typeof item === "string" ? item : (item?.tool || item?.name)).filter(Boolean);
    const providerShown = providerActual === provider;
    const toolShown = actualTools.includes(expectedTool);
    const resultText = (await page.locator("#productTitle").textContent()) || "";
    const overlayCount = await page.locator(".leaflet-overlay-pane svg path, .result-numbered-marker, .result-number-marker").count();
    const screenshot = path.join(outputDir, `${provider.toUpperCase()}_LIVE_${index}.png`);
    await page.screenshot({ path: screenshot, fullPage: false });
    rows.push({
      provider,
      case_id: index,
      query,
      expected_tool: expectedTool,
      provider_shown: providerShown,
      tool_shown: toolShown,
      provider_actual: providerActual,
      actual_tools: actualTools.join("|"),
      api_status: agentData?.status || "",
      result_title: resultText.trim(),
      overlay_element_count: overlayCount,
      ui_error: errorText.trim(),
      screenshot,
      pass: agentResponse.ok() && providerShown && toolShown && !errorText.trim(),
    });
    process.stdout.write(`${provider} ${index} ${rows.at(-1).pass ? "PASS" : "FAIL"}\n`);
  }
}

await page.setViewportSize({ width: 390, height: 844 });
await page.goto("http://127.0.0.1:8795/#explore", { waitUntil: "domcontentloaded", timeout: 30000 });
await page.locator("#productQuery").waitFor({ state: "visible", timeout: 30000 });
await page.waitForTimeout(1200);
await page.selectOption("#llmProviderSelect", "deepseek");
await page.fill("#productQuery", "ค้นหาพื้นที่น้ำ");
await Promise.all([
  page.waitForResponse((response) => response.url().includes("/api/agent/query") && response.request().method() === "POST", { timeout: 240000 }),
  page.click("#productAskBtn"),
]);
await page.waitForFunction(() => !document.querySelector("#productAskBtn")?.disabled, null, { timeout: 30000 });
await page.waitForTimeout(750);
const bodyWidth = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
const mobileShot = path.join(outputDir, "MOBILE_390x844_LIVE.png");
await page.screenshot({ path: mobileShot, fullPage: false });

await browser.close();

const headers = Object.keys(rows[0]);
const csv = [
  headers.join(","),
  ...rows.map((row) => headers.map((header) => JSON.stringify(row[header] ?? "")).join(",")),
].join("\n");
fs.writeFileSync(path.join(outputDir, "BROWSER_LIVE_QA.csv"), "\uFEFF" + csv + "\n", "utf8");
fs.writeFileSync(path.join(outputDir, "BROWSER_LIVE_QA.json"), JSON.stringify({
  url: "http://127.0.0.1:8795/#explore",
  desktop_viewport: "1440x900",
  mobile_viewport: "390x844",
  cases: rows,
  console_errors: consoleErrors,
  mobile_horizontal_overflow: bodyWidth.scrollWidth > bodyWidth.clientWidth,
  mobile_screenshot: mobileShot,
}, null, 2), "utf8");

if (!rows.every((row) => row.pass) || consoleErrors.length || bodyWidth.scrollWidth > bodyWidth.clientWidth) {
  process.exitCode = 2;
}
