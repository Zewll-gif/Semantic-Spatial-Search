/* Map-first presentation for user-drawn AOI analysis and review corrections. */
(() => {
  const legacyRunButton = document.getElementById('runAnalysisBtn');
  if (!legacyRunButton) return;
  let current = null, analysisGroup = null, previewUrl = null;
  let externalLayer = 'rgb', externalOpacity = .84;
  let correctionPoint = null, correctionFeature = null, correctionRecord = null;
  const history = [];
  const fmt = (value, digits = 2) => Number(value).toLocaleString('th-TH', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  const panel = () => document.querySelector('.right-panel');
  const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const geometry = () => window.selectedGeometry || (window.selectedBbox ? { type: 'Polygon', coordinates: [[[window.selectedBbox[0], window.selectedBbox[1]], [window.selectedBbox[2], window.selectedBbox[1]], [window.selectedBbox[2], window.selectedBbox[3]], [window.selectedBbox[0], window.selectedBbox[3]], [window.selectedBbox[0], window.selectedBbox[1]]]] } : null);

  function ensureHost() {
    let host = document.getElementById('drawnAoiResults');
    if (host) return host;
    host = el('section', 'panel-section drawn-aoi-results');
    host.id = 'drawnAoiResults'; host.hidden = true;
    panel().insertBefore(host, panel().querySelector('.evidence-panel'));
    return host;
  }
  function showPanel() {
    const right = panel();
    right.classList.add('is-open', 'has-aoi-results'); right.classList.remove('has-query-results');
    document.body.classList.add('results-open');
    right.scrollTo({ top: 0, behavior: reduceMotion() ? 'auto' : 'smooth' });
  }
  function hideOtherSections(on) {
    panel().querySelectorAll(':scope > .product-results,:scope > .results-section,:scope > .evidence-panel,:scope > .workspace-layers,:scope > .limitations').forEach(node => { node.hidden = on; });
  }
  function clearOverlay() {
    if (analysisGroup) analysisGroup.clearLayers();
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
  }
  function toast(message, tone = 'success') {
    let node = document.querySelector('.aoi-toast');
    if (!node) { node = el('div', 'aoi-toast'); node.setAttribute('role', 'status'); node.setAttribute('aria-live', 'polite'); document.getElementById('explore').append(node); }
    node.className = `aoi-toast is-visible ${tone}`; node.textContent = message;
    clearTimeout(toast.timer); toast.timer = setTimeout(() => node.classList.remove('is-visible'), 3200);
  }
  function metric(label, value, note) {
    const card = el('div', 'aoi-metric');
    card.append(el('span', '', label), el('strong', '', value));
    if (note) card.append(el('small', '', note));
    return card;
  }
  function humanError(error) {
    const text = String(error?.message || '');
    if (/credentials_invalid|credentials_forbidden|ไม่ถูกต้อง|หมดอายุ|ไม่มีสิทธิ์/i.test(text)) return 'CDSE S3 credentials ไม่ถูกต้อง หมดอายุ หรือไม่มีสิทธิ์อ่านข้อมูล กรุณาอัปเดตคีย์ที่ backend';
    if (/credentials_missing|CDSE S3|ตั้งค่าการเข้าถึง/i.test(text)) return 'ยังไม่ได้ตั้งค่าการเข้าถึงข้อมูล Sentinel-2 ที่ backend';
    if (/no_scene|ไม่พบภาพ Sentinel-2/i.test(text)) return 'ไม่พบภาพ Sentinel-2 ที่เหมาะสมสำหรับพื้นที่และช่วงเวลานี้';
    if (/no_usable_pixels|ไม่มีพิกเซลที่ใช้/i.test(text)) return 'ภาพ Sentinel-2 วันที่เลือกไม่มีพิกเซลที่ใช้วิเคราะห์ได้ กรุณาเลือกวันที่อื่นหรือวาดพื้นที่ใหม่';
    if (/stac_unavailable|เชื่อมต่อแหล่งข้อมูล/i.test(text)) return 'ไม่สามารถเชื่อมต่อแหล่งข้อมูลดาวเทียมภายนอกได้ในขณะนี้';
    if (/outside|no_data|ขอบเขต/i.test(text)) return 'พื้นที่ที่เลือกอยู่นอกขอบเขตข้อมูลที่รองรับ';
    if (/geometry|polygon|vertex/i.test(text)) return 'รูปทรงพื้นที่ไม่สมบูรณ์ กรุณาวาดพื้นที่ใหม่';
    return 'ไม่สามารถวิเคราะห์พื้นที่ได้ในขณะนี้ กรุณาลองอีกครั้ง';
  }
  function insight(data) {
    const active = data.classes.filter(item => item.pixels > 0).sort((a, b) => b.percentage - a.percentage);
    const first = active[0], second = active[1];
    const sentences = [`พื้นที่นี้มี${first.class_name_th}เป็นองค์ประกอบหลัก ${fmt(first.percentage, 1)}%${second ? ` รองลงมาคือ${second.class_name_th} ${fmt(second.percentage, 1)}%` : ''}`];
    const vegetation = data.classes.filter(item => ['R3', 'R5'].includes(item.class_id)).reduce((sum, item) => sum + item.percentage, 0);
    const water = data.classes.find(item => item.class_id === 'R4')?.percentage || 0;
    if (data.ndvi.available) sentences.push(`ค่า NDVI เฉลี่ย ${fmt(data.ndvi.mean, 2)}${vegetation >= 20 ? ' สอดคล้องกับการมีพืชพรรณในพื้นที่' : ''}`);
    if (water >= 5 || (data.ndwi.available && data.ndwi.mean > 0)) sentences.push(`ตรวจพบองค์ประกอบแหล่งน้ำ ${fmt(water, 1)}% และค่า NDWI เฉลี่ย ${fmt(data.ndwi.mean, 2)}`);
    return sentences.slice(0, 3).join(' ');
  }
  function metricDetails(data) {
    const details = el('details', 'aoi-metric-details');
    details.append(el('summary', '', 'ดูค่าสถิติเพิ่มเติม'));
    const grid = el('div', 'aoi-stat-grid');
    [['NDVI', data.ndvi, 2], ['NDWI', data.ndwi, 2], ['ระดับความสูง', data.elevation, 1]].forEach(([name, item, digits]) => {
      const block = el('div', 'aoi-stat-block'); block.append(el('strong', '', name));
      if (!item.available) block.append(el('span', '', `ไม่มีข้อมูล ${name} สำหรับบางส่วนของพื้นที่นี้`));
      else block.append(el('span', '', `ต่ำสุด ${fmt(item.min, digits)}`), el('span', '', `เฉลี่ย ${fmt(item.mean, digits)}`), el('span', '', `มัธยฐาน ${fmt(item.median, digits)}`), el('span', '', `สูงสุด ${fmt(item.max, digits)}`));
      grid.append(block);
    });
    details.append(grid); return details;
  }
  const traceLabels = {
    calculate_aoi_area: 'คำนวณพื้นที่ AOI', get_class_distribution: 'วิเคราะห์สิ่งปกคลุมดิน',
    get_ndvi_zonal_stats: 'วิเคราะห์ค่า NDVI', get_ndwi_zonal_stats: 'วิเคราะห์ค่า NDWI', get_dem_zonal_stats: 'วิเคราะห์ระดับความสูง',
    check_project_coverage: 'ตรวจสอบขอบเขตข้อมูลโครงการ', search_sentinel2: 'ค้นหาภาพดาวเทียมภายนอก',
    select_best_scene: 'เลือกภาพที่เหมาะสม', calculate_external_ndvi: 'คำนวณ NDVI จาก Sentinel-2',
    calculate_external_ndwi: 'คำนวณ NDWI จาก Sentinel-2', calculate_external_zonal_stats: 'คำนวณค่าสถิติภายใน AOI',
  };
  function renderTrace(data) {
    const trace = el('details', 'aoi-trace'); trace.append(el('summary', '', 'ดูวิธีที่ระบบวิเคราะห์'));
    const body = el('div', 'aoi-trace-body');
    data.execution_trace.forEach(step => {
      const row = el('div', 'aoi-trace-step');
      row.append(el('b', '', '✓'), el('strong', '', traceLabels[step.tool] || step.tool));
      const meta = el('div', 'aoi-trace-meta');
      meta.append(el('code', '', `${step.tool}()`), el('span', '', step.source), el('span', '', step.status === 'success' ? 'สำเร็จ' : step.status));
      row.append(meta); body.append(row);
    });
    const foot = data.analysis_type === 'external_satellite' ? `Sentinel-2 L2A · 10 m · ${data.geometry_vertices} vertices` : `CRS: EPSG:4326 → EPSG:32647 · ${data.geometry_vertices} vertices`;
    body.append(el('p', 'aoi-trace-foot', foot)); trace.append(body); return trace;
  }
  function renderReliability(data) {
    const details = el('details', 'aoi-reliability'); details.append(el('summary', '', 'ความน่าเชื่อถือของผล'));
    const body = el('div', 'aoi-reliability-body');
    body.append(el('p', '', 'ผลสิ่งปกคลุมดินมาจากการทำนายของ A7-T และค่าประเมินอ้างอิงจาก Fixed VAL4'));
    body.append(el('p', 'aoi-info-note', 'ค่าด้านล่างเป็นผลประเมินระดับคลาส ไม่ใช่ความมั่นใจของ AOI หรือ polygon นี้ และพื้นที่นี้ไม่ได้ผ่าน independent Ground Truth validation'));
    const metrics = el('div', 'aoi-reliability-grid');
    Object.entries(data.reliability.class_metrics || {}).forEach(([code, value]) => metrics.append(el('span', '', `${code} · IoU ${value.validation_iou == null ? '—' : fmt(value.validation_iou, 3)} · F1 ${value.validation_f1 == null ? '—' : fmt(value.validation_f1, 3)}`)));
    body.append(metrics); details.append(body); return details;
  }
  function correctionDrawer() {
    const drawer = el('section', 'aoi-correction-drawer'); drawer.hidden = true; drawer.setAttribute('role', 'dialog'); drawer.setAttribute('aria-modal', 'true'); drawer.setAttribute('aria-labelledby', 'aoiCorrectionTitle');
    drawer.innerHTML = `<div class="aoi-drawer-head"><div><span>ตรวจสอบโดยผู้ใช้</span><h3 id="aoiCorrectionTitle">แก้ไขการจำแนก</h3></div><button type="button" data-correction-close aria-label="ปิดหน้าต่างแก้ไข">×</button></div>
      <div class="aoi-model-prediction"><span>ผลทำนายของโมเดล</span><strong data-correction-source></strong></div>
      <label>แก้เป็น<select data-corrected-class aria-label="เลือกคลาสที่ถูกต้อง"></select></label>
      <label>หมายเหตุ <small>ไม่บังคับ</small><textarea data-correction-note rows="3" maxlength="1000" placeholder="อธิบายเหตุผลสั้น ๆ"></textarea></label>
      <p class="aoi-correction-caveat">การแก้ไขนี้จะถูกเก็บเพื่อการตรวจสอบ และจะไม่เปลี่ยนผลทำนายของโมเดลทันที</p>
      <div class="aoi-drawer-actions"><button type="button" class="secondary-btn" data-correction-cancel>ยกเลิก</button><button type="button" class="primary-btn" data-save-correction>บันทึกการแก้ไข</button></div>`;
    const select = drawer.querySelector('[data-corrected-class]');
    for (let i = 1; i <= 7; i++) { const code = `R${i}`, option = el('option', '', `${code} ${window.GeoAIClasses.thai(code)}`); option.value = code; select.append(option); }
    drawer.querySelectorAll('[data-correction-close],[data-correction-cancel]').forEach(button => button.addEventListener('click', () => { drawer.hidden = true; }));
    drawer.querySelector('[data-save-correction]').addEventListener('click', () => saveCorrection(drawer)); return drawer;
  }
  function featureDetail() {
    const section = el('section', 'aoi-feature-detail'); section.dataset.featureDetail = '';
    section.innerHTML = `<div class="aoi-feature-intro"><div><h3>ตรวจสอบการจำแนก</h3><p>เลือกจุดภายใน AOI เพื่อดูคลาสที่โมเดลทำนาย</p></div><button type="button" class="secondary-btn" data-identify-feature>เลือกจุดบนแผนที่</button></div><div data-feature-content hidden></div>`;
    section.querySelector('[data-identify-feature]').addEventListener('click', () => beginIdentify(section)); return section;
  }
  function renderFeature(section, data) {
    const p = data.feature.properties, content = section.querySelector('[data-feature-content]');
    content.hidden = false; content.replaceChildren();
    const prediction = el('div', 'aoi-feature-row'); prediction.append(el('span', '', 'ผลทำนายของโมเดล'), el('strong', '', `${p.class_id} ${window.GeoAIClasses.thai(p.class_id)}`)); content.append(prediction);
    if (correctionRecord) {
      const corrected = el('div', 'aoi-feature-row is-corrected'); corrected.append(el('span', '', 'การแก้ไขของผู้ใช้'), el('strong', '', `${correctionRecord.corrected_class} ${window.GeoAIClasses.thai(correctionRecord.corrected_class)}`));
      const status = el('div', 'aoi-feature-row'); status.append(el('span', '', 'สถานะ'), el('strong', 'aoi-pending-status', 'รอตรวจสอบ')); content.append(corrected, status);
    }
    const button = el('button', 'aoi-correction-entry', 'การจำแนกนี้ไม่ถูกต้อง'); button.type = 'button'; button.addEventListener('click', openCorrection); content.append(button);
  }
  function coverageBar(label, value, tone) {
    const row = el('div', 'aoi-coverage-row');
    const head = el('div', 'aoi-coverage-label'); head.append(el('span', '', label), el('strong', '', `${fmt(value, 1)}%`));
    const track = el('div', 'aoi-coverage-track'), bar = el('span'); bar.style.width = `${Math.max(0, Math.min(100, value))}%`; bar.dataset.tone = tone; track.append(bar); row.append(head, track); return row;
  }
  function renderCoverageChoice(host, data, geom) {
    host.replaceChildren(); host.hidden = false;
    const card = el('section', 'aoi-source-choice');
    card.append(el('span', 'aoi-source-badge neutral', data.status === 'partial_coverage' ? 'Mixed data coverage' : 'Outside project footprint'));
    card.append(el('h2', '', data.status === 'partial_coverage' ? 'เลือกแหล่งข้อมูลสำหรับวิเคราะห์' : 'พื้นที่อยู่นอกข้อมูลโครงการ'));
    card.append(el('p', '', data.message));
    const coverage = el('div', 'aoi-coverage');
    coverage.append(coverageBar('Project coverage', data.project_coverage_percentage, 'project'), coverageBar('External coverage', data.external_coverage_percentage, 'external'));
    card.append(coverage);
    const actions = el('div', 'aoi-source-actions');
    if (data.status === 'partial_coverage') {
      const project = el('button', 'secondary-btn', 'วิเคราะห์เฉพาะพื้นที่ที่มีข้อมูลโครงการ'); project.type = 'button'; project.addEventListener('click', () => analyzeProjectOnly(geom)); actions.append(project);
    }
    const external = el('button', 'primary-btn', 'วิเคราะห์ทั้งหมดด้วย Sentinel-2'); external.type = 'button'; external.addEventListener('click', () => analyzeExternal(geom)); actions.append(external); card.append(actions);
    card.append(el('small', '', 'Sentinel-2 เป็นข้อมูลคนละ sensor และจะไม่ถูกเรียกว่า A7-T หรือแปลงเป็นคลาส R1–R7'));
    host.append(card);
  }
  function externalStatDetails(data) {
    const details = el('details', 'aoi-metric-details'); details.append(el('summary', '', 'ดูค่าสถิติเพิ่มเติม'));
    const grid = el('div', 'aoi-stat-grid');
    [['NDVI', data.ndvi], ['NDWI', data.ndwi]].forEach(([name, item]) => {
      const block = el('div', 'aoi-stat-block'); block.append(el('strong', '', name));
      if (!item.available) block.append(el('span', '', 'ไม่มีพิกเซลที่ใช้ได้'));
      else block.append(el('span', '', `ต่ำสุด ${fmt(item.min, 3)}`), el('span', '', `เฉลี่ย ${fmt(item.mean, 3)}`), el('span', '', `มัธยฐาน ${fmt(item.median, 3)}`), el('span', '', `สูงสุด ${fmt(item.max, 3)}`));
      grid.append(block);
    });
    const quality = el('div', 'aoi-stat-block'); quality.append(el('strong', '', 'คุณภาพข้อมูล'), el('span', '', `Valid ${fmt(data.valid_pixel_percentage, 1)}%`), el('span', '', `Cloud ${fmt(data.cloud_pixel_percentage, 1)}%`), el('span', '', `No-data ${fmt(data.nodata_pixel_percentage, 1)}%`)); grid.append(quality);
    details.append(grid); return details;
  }
  function externalPreviewControl(data, geom) {
    const control = el('section', 'aoi-external-preview');
    const title = el('div', 'aoi-preview-head'); title.append(el('strong', '', 'ภาพภายใน AOI'), el('span', '', 'RGB / ดัชนีจาก Sentinel-2'));
    const segmented = el('div', 'aoi-preview-segmented');
    [['rgb', 'RGB'], ['ndvi', 'NDVI'], ['ndwi', 'NDWI']].forEach(([mode, label]) => {
      const button = el('button', '', label); button.type = 'button'; button.dataset.layer = mode; button.setAttribute('aria-pressed', String(mode === externalLayer));
      button.addEventListener('click', async () => { externalLayer = mode; segmented.querySelectorAll('button').forEach(node => node.setAttribute('aria-pressed', String(node === button))); await showExternalPreview(geom, mode); }); segmented.append(button);
    });
    const opacity = el('label', 'aoi-external-opacity'); opacity.append(el('span', '', 'ความทึบ'));
    const range = document.createElement('input'); range.type = 'range'; range.min = '.2'; range.max = '1'; range.step = '.05'; range.value = String(externalOpacity); range.addEventListener('input', () => { externalOpacity = Number(range.value); analysisGroup?.eachLayer(layer => { if (layer instanceof L.ImageOverlay) layer.setOpacity(externalOpacity); }); }); opacity.append(range);
    control.append(title, segmented, opacity); return control;
  }
  function renderExternalStats(host, data, geom) {
    host.replaceChildren(); host.hidden = false;
    const head = el('div', 'aoi-result-head'), title = el('div'); title.append(el('span', 'aoi-source-badge external', 'External satellite analysis'), el('h2', '', `${fmt(data.area_rai)} ไร่`), el('small', '', 'ไม่ใช่ A7-T classification'));
    head.append(title); host.append(head);
    const provenance = el('section', 'aoi-provenance');
    provenance.append(el('h3', '', 'Sentinel-2 Level-2A'));
    [['วันที่ภาพ', data.scene.acquisition_date], ['Cloud cover', `${fmt(data.scene.cloud_cover_percentage, 1)}%`], ['ความละเอียด', `${data.scene.spatial_resolution_m} m`], ['Product ID', data.scene.item_id]].forEach(([label, value]) => { const row = el('div', 'aoi-provenance-row'); row.append(el('span', '', label), el('strong', '', value)); provenance.append(row); }); host.append(provenance);
    if (data.cloud_warning) host.append(el('p', 'aoi-warning', 'ภาพที่เลือกมีเมฆปกคลุมสูงหรือ valid coverage ต่ำ ผลวิเคราะห์อาจมีข้อมูลที่ใช้ได้จำกัด'));
    const metrics = el('div', 'aoi-metrics'); metrics.append(metric('ค่า NDVI', data.ndvi.available ? fmt(data.ndvi.mean, 2) : 'ไม่มีข้อมูล', 'B08 / B04'), metric('ค่า NDWI', data.ndwi.available ? fmt(data.ndwi.mean, 2) : 'ไม่มีข้อมูล', 'B03 / B08'), metric('Valid coverage', `${fmt(data.valid_pixel_percentage, 1)}%`, 'SCL mask')); host.append(metrics, externalStatDetails(data));
    host.append(externalPreviewControl(data, geom));
    const summary = el('section', 'aoi-agent-summary'); summary.append(el('h3', '', 'สรุปจากข้อมูลดาวเทียม'), el('p', '', data.summary)); host.append(summary, renderTrace(data));
    const caveat = el('section', 'aoi-external-caveat'); caveat.append(el('strong', '', 'ขอบเขตการตีความ'), el('p', '', 'ระบบคำนวณเฉพาะ RGB, NDVI และ NDWI จาก Sentinel-2 L2A โดยไม่อนุมานคลาส R1–R7 และไม่แสดง A7-T Reliability Context')); host.append(caveat);
  }
  function renderStats(host, data) {
    host.replaceChildren(); host.hidden = false;
    const head = el('div', 'aoi-result-head'), title = el('div');
    title.append(el('span', 'aoi-source-badge project', 'Project analysis · A7-T / PlanetScope'), el('h2', '', `${fmt(data.area_rai)} ไร่`), el('small', '', `${fmt(data.area_m2, 0)} m² · EPSG:32647`));
    const historySelect = el('select', 'aoi-history'); historySelect.setAttribute('aria-label', 'ประวัติพื้นที่ที่วิเคราะห์');
    history.forEach((item, index) => { const option = el('option', '', `พื้นที่ที่ ${history.length - index} · ${fmt(item.area_rai)} ไร่`); option.value = item.aoi_id; historySelect.append(option); });
    historySelect.addEventListener('change', () => { const item = history.find(row => row.aoi_id === historySelect.value); if (item) { current = item; correctionRecord = null; renderStats(host, item); } });
    head.append(title, historySelect); host.append(head);
    if (data.message) host.append(el('p', 'aoi-info-note', data.message));
    const dominant = el('section', 'aoi-dominant'); dominant.style.setProperty('--class-color', data.dominant_class.color); dominant.append(el('span', '', 'ประเภทเด่น'), el('strong', '', `${data.dominant_class.class_id} ${data.dominant_class.class_name_th}`), el('b', '', `${fmt(data.dominant_class.percentage, 1)}%`)); host.append(dominant);
    const metrics = el('div', 'aoi-metrics');
    metrics.append(metric('ค่า NDVI', data.ndvi.available ? fmt(data.ndvi.mean, 2) : 'ไม่มีข้อมูล', 'ค่าเฉลี่ย'), metric('ค่า NDWI', data.ndwi.available ? fmt(data.ndwi.mean, 2) : 'ไม่มีข้อมูล', 'ค่าเฉลี่ย'), metric('ระดับความสูง', data.elevation.available ? `${fmt(data.elevation.min, 0)}–${fmt(data.elevation.max, 0)} m` : 'ไม่มีข้อมูล', 'COP30 DSM'));
    host.append(metrics, metricDetails(data));
    const composition = el('section', 'aoi-composition'); composition.append(el('h3', '', 'สัดส่วนสิ่งปกคลุมดิน'));
    data.classes.forEach(item => {
      const row = el('div', 'aoi-class-row'), label = el('div', 'aoi-class-label'), swatch = el('i'); swatch.style.background = item.color;
      label.append(swatch, el('span', '', `${item.class_id} ${item.class_name_th}`), el('strong', '', `${fmt(item.percentage, 1)}%`));
      const track = el('div', 'aoi-class-track'), bar = el('span'); bar.style.width = `${Math.max(0, Math.min(100, item.percentage))}%`; bar.style.background = item.color; track.append(bar);
      row.append(label, track, el('small', '', `${fmt(item.area_rai)} ไร่`)); composition.append(row);
    }); host.append(composition);
    const summary = el('section', 'aoi-agent-summary'); summary.append(el('h3', '', 'ข้อสังเกตจากพื้นที่'), el('p', '', insight(data)));
    host.append(summary, renderTrace(data), renderReliability(data), featureDetail());
    document.querySelector('#explore > .aoi-correction-drawer')?.remove();
    document.getElementById('explore').append(correctionDrawer());
  }
  function loading(host, mode = 'project') {
    host.hidden = false; host.replaceChildren();
    const box = el('div', 'aoi-loading'); box.append(el('span', 'aoi-loading-spinner'));
    const content = el('div'); content.append(el('strong', '', mode === 'external' ? 'กำลังวิเคราะห์ด้วย Sentinel-2…' : 'กำลังวิเคราะห์พื้นที่…'));
    const steps = mode === 'external' ? ['ตรวจสอบ project coverage', 'ค้นหาและเลือก Sentinel-2 scene', 'อ่าน RGB / NIR / SCL', 'คำนวณ NDVI / NDWI'] : ['คำนวณขนาดพื้นที่', 'วิเคราะห์ A7-T', 'คำนวณ NDVI / NDWI', 'วิเคราะห์ระดับความสูง'];
    const list = el('div', 'aoi-loading-steps'); steps.forEach((text, index) => { const row = el('span', index === 0 ? 'is-active' : '', text); row.prepend(el('i', '', index === 0 ? '•' : '○')); list.append(row); });
    content.append(list); box.append(content); host.append(box);
  }
  async function showPreview(geom) {
    const response = await fetch('/api/aoi/preview', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ geometry: geom }) });
    if (!response.ok) throw Error('preview unavailable');
    const bbox = response.headers.get('X-GeoAI-Rendered-Bbox').split(',').map(Number);
    previewUrl = URL.createObjectURL(await response.blob()); analysisGroup = analysisGroup || L.layerGroup().addTo(map); analysisGroup.clearLayers();
    L.imageOverlay(previewUrl, [[bbox[1], bbox[0]], [bbox[3], bbox[2]]], { opacity: .86, interactive: false, pane: 'aoiThematic', className: 'aoi-analysis-preview' }).addTo(analysisGroup);
    L.geoJSON(geom, { style: { color: '#fff', weight: 3, dashArray: '7 5', fill: false }, interactive: false }).addTo(analysisGroup);
  }
  async function showExternalPreview(geom, layer = 'rgb') {
    const response = await fetch('/api/aoi/external/preview', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ geometry: geom, layer }) });
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw Error(data.detail?.message || 'external preview unavailable'); }
    const bbox = response.headers.get('X-GeoAI-Rendered-Bbox').split(',').map(Number);
    if (previewUrl) URL.revokeObjectURL(previewUrl); previewUrl = URL.createObjectURL(await response.blob()); analysisGroup = analysisGroup || L.layerGroup().addTo(map); analysisGroup.clearLayers();
    L.imageOverlay(previewUrl, [[bbox[1], bbox[0]], [bbox[3], bbox[2]]], { opacity: externalOpacity, interactive: false, pane: 'aoiThematic', className: `aoi-external-preview-layer is-${layer}` }).addTo(analysisGroup);
    L.geoJSON(geom, { style: { color: '#fff', weight: 3, dashArray: '7 5', fill: false }, interactive: false }).addTo(analysisGroup);
  }
  function focusExternalAoi(geom) {
    const bounds = L.geoJSON(geom).getBounds();
    if (!bounds.isValid()) return;
    const compact = map.getSize().x < 760;
    map.fitBounds(bounds, {
      animate: !reduceMotion(),
      duration: reduceMotion() ? 0 : .55,
      maxZoom: 14,
      paddingTopLeft: compact ? [18, 120] : [48, 115],
      paddingBottomRight: compact ? [18, 390] : [410, 80],
    });
  }
  async function analyzeProjectOnly(geom) {
    const host = ensureHost(); loading(host); legacyRunButton.disabled = true; window.GeoAIDrawUI?.setAnalyzing(true);
    try {
      const response = await fetch('/api/aoi/analyze', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ geometry: geom, analysis_mode: 'project_only' }) });
      const data = await response.json(); if (!response.ok) throw Error(data.detail?.message || 'analysis failed');
      await showPreview(data.geometry); current = data; history.unshift(data); if (history.length > 5) history.pop(); renderStats(host, data); window.GeoAIDrawUI?.setAnalyzed(true);
    } catch (error) { renderFailure(host, error, () => analyzeProjectOnly(geom)); }
    finally { legacyRunButton.disabled = false; }
  }
  async function analyzeExternal(geom) {
    const host = ensureHost(); loading(host, 'external'); legacyRunButton.disabled = true; window.GeoAIDrawUI?.setAnalyzing(true); clearOverlay();
    try {
      const response = await fetch('/api/aoi/external/analyze', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ geometry: geom }) });
      const data = await response.json(); if (!response.ok) throw Error(`${data.detail?.code || ''} ${data.detail?.message || 'external analysis failed'}`);
      current = data; externalLayer = 'rgb'; renderExternalStats(host, data, geom); await showExternalPreview(geom, externalLayer); focusExternalAoi(geom); window.GeoAIDrawUI?.setAnalyzed(true);
    } catch (error) { renderFailure(host, error, () => analyzeExternal(geom)); }
    finally { legacyRunButton.disabled = false; }
  }
  function renderFailure(host, error, retry) {
    host.innerHTML = '<div class="aoi-error"><strong>วิเคราะห์พื้นที่ไม่สำเร็จ</strong><p></p><button type="button" class="secondary-btn">ลองอีกครั้ง</button></div>';
    host.querySelector('p').textContent = humanError(error); host.querySelector('button').addEventListener('click', retry); window.GeoAIDrawUI?.setAnalyzing(false);
  }
  async function analyze() {
    const geom = geometry(), host = ensureHost();
    if (!geom) { host.hidden = false; host.innerHTML = '<div class="aoi-empty"><strong>ยังไม่ได้เลือกพื้นที่</strong><p>วาดพื้นที่บนแผนที่เพื่อเริ่มวิเคราะห์</p></div>'; showPanel(); return; }
    hideOtherSections(true); showPanel(); loading(host); legacyRunButton.disabled = true; window.GeoAIDrawUI?.setAnalyzing(true);
    const started = performance.now();
    try {
      window.clearRoiPreview?.(); clearOverlay(); correctionRecord = null; correctionFeature = null;
      const response = await fetch('/api/aoi/analyze', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ geometry: geom }) });
      const data = await response.json(); if (!response.ok) throw Error(data.detail?.message || data.detail || 'analysis failed');
      const remaining = Math.max(0, 520 - (performance.now() - started)); if (remaining) await wait(remaining);
      if (data.status === 'external_option' || data.status === 'partial_coverage') { renderCoverageChoice(host, data, geom); window.GeoAIDrawUI?.setAnalyzing(false); return; }
      if (data.status === 'no_data') throw Error('no_data');
      await showPreview(data.geometry || geom);
      current = data; history.unshift(data); if (history.length > 5) history.pop(); renderStats(host, data); window.GeoAIDrawUI?.setAnalyzed(true);
    } catch (error) {
      renderFailure(host, error, analyze);
    } finally { legacyRunButton.disabled = false; }
  }
  const contains = (geom, latlng) => {
    const point = [latlng.lng, latlng.lat], ringContains = ring => { let inside = false; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const a = ring[i], b = ring[j]; if (((a[1] > point[1]) !== (b[1] > point[1])) && (point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0])) inside = !inside; } return inside; };
    return geom.type === 'Polygon' ? ringContains(geom.coordinates[0]) : geom.coordinates.some(poly => ringContains(poly[0]));
  };
  function beginIdentify(section) {
    const button = section.querySelector('[data-identify-feature]'); button.textContent = 'คลิกจุดภายใน AOI…'; button.classList.add('is-active'); map.getContainer().classList.add('is-correction-pick');
    map.once('click', async event => {
      map.getContainer().classList.remove('is-correction-pick'); button.textContent = 'เลือกจุดบนแผนที่'; button.classList.remove('is-active');
      if (!current || !contains(current.geometry, event.latlng)) { toast('ตำแหน่งนี้อยู่นอกพื้นที่ที่วิเคราะห์', 'info'); return; }
      try {
        const response = await fetch(`/api/map/identify?lon=${event.latlng.lng}&lat=${event.latlng.lat}`), data = await response.json(); if (!response.ok || !data.feature) throw Error('identify unavailable');
        correctionPoint = event.latlng; correctionFeature = data.feature; correctionRecord = null; renderFeature(section, data);
      } catch (_) { toast('ไม่พบข้อมูลจำแนก ณ ตำแหน่งนี้', 'info'); }
    });
  }
  function openCorrection() {
    if (!correctionFeature) return;
    const drawer = document.querySelector('#explore > .aoi-correction-drawer'), p = correctionFeature.properties;
    drawer.querySelector('[data-correction-source]').textContent = `${p.class_id} ${window.GeoAIClasses.thai(p.class_id)}`;
    drawer.querySelector('[data-corrected-class]').value = p.class_id === 'R1' ? 'R2' : 'R1'; drawer.querySelector('[data-correction-note]').value = ''; drawer.hidden = false;
    drawer.querySelector('[data-corrected-class]').focus();
  }
  async function saveCorrection(drawer) {
    if (!correctionFeature || !correctionPoint) return;
    const p = correctionFeature.properties, button = drawer.querySelector('[data-save-correction]'); button.disabled = true; button.textContent = 'กำลังบันทึก…';
    const payload = { geometry: { type: 'Point', coordinates: [correctionPoint.lng, correctionPoint.lat] }, feature_id: p.feature_id, original_class: p.class_id, corrected_class: drawer.querySelector('[data-corrected-class]').value, user_note: drawer.querySelector('[data-correction-note]').value, source_aoi_id: current.aoi_id };
    try {
      const response = await fetch('/api/aoi/corrections', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) }), data = await response.json(); if (!response.ok) throw Error('save failed');
      correctionRecord = data; drawer.hidden = true; renderFeature(ensureHost().querySelector('[data-feature-detail]'), { feature: correctionFeature }); toast('บันทึกการแก้ไขแล้ว');
      const color = window.GeoAIClasses.color(data.corrected_class);
      const icon = L.divIcon({ className: 'aoi-correction-marker', html: `<span style="--correction-color:${color}" aria-hidden="true">✎</span>`, iconSize: [24, 24], iconAnchor: [12, 12] });
      L.marker(correctionPoint, { icon, pane: 'markerPane', keyboard: true, title: `แก้ไข ${data.original_class} เป็น ${data.corrected_class}` }).bindTooltip(`ผลทำนาย ${data.original_class} → ผู้ใช้แก้เป็น ${data.corrected_class} · รอตรวจสอบ`).addTo(analysisGroup);
    } catch (_) { toast('บันทึกการแก้ไขไม่สำเร็จ กรุณาลองอีกครั้ง', 'error'); }
    finally { button.disabled = false; button.textContent = 'บันทึกการแก้ไข'; }
  }
  legacyRunButton.addEventListener('click', analyze);
  window.GeoAIAoiAnalysis = { analyze };
  window.addEventListener('map-workspace-cleared', () => { clearOverlay(); current = null; correctionFeature = null; correctionRecord = null; document.querySelector('#explore > .aoi-correction-drawer')?.remove(); const host = ensureHost(); host.hidden = true; panel().classList.remove('has-aoi-results'); hideOtherSections(false); });
})();
