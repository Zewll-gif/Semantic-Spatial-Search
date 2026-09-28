/*
CLEAN PROJECT HEADER
ไฟล์: evidence.js
หน้าที่: ส่วนแสดงผลและ interaction ของ GeoAI Explorer
Input: ข้อมูลจาก API และ static assets
Output: หน้าเว็บหรือพฤติกรรม UI
Dependency สำคัญ: backend API และ class schema
สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
*/
(() => {
  let current = null;
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const emptyState = () => {
    const body = $('#evidenceBody'), details = $('#evidenceDetails');
    if (body) { body.hidden = false; body.className = 'evidence-empty'; }
    if (details) details.hidden = true;
    const cross = $('#crosscheckSection'); if (cross) cross.hidden = true;
    const why = $('#whyBtn'); if (why) { why.disabled = true; why.dataset.tile = ''; }
  };
  const statusText = s => String(s || 'UNAVAILABLE').replaceAll('_', ' ');
  function strength(spectral, external) {
    if (spectral === 'CONSISTENT' && external === 'SUPPORTIVE') return ['HIGH', 'supportive'];
    if (spectral === 'CONSISTENT' || external === 'SUPPORTIVE') return ['MODERATE', 'supportive'];
    return ['LIMITED', 'limited'];
  }
  async function render(t) {
    current = t;
    const title = $('#evidenceTitle'), body = $('#evidenceBody'), details = $('#evidenceDetails');
    if (!title || !body || !details) return;
    title.textContent = t.dominant_class_name || `Tile ${t.tile_id}`;
    body.hidden = true; details.hidden = false;
    const crossNode = $('#crosscheckSection');
    if (crossNode && crossNode.parentElement !== details) details.appendChild(crossNode);
    let lulc = $('#lulcCrosscheck');
    if (!lulc) { lulc = document.createElement('section'); lulc.id='lulcCrosscheck'; lulc.className='evidence-group crosscheck-section'; details.appendChild(lulc); }
    lulc.innerHTML = '<h3>EXTERNAL LULC REFERENCES</h3><div class="crosscheck-grid"><div><span class="crosscheck-label">Dynamic World</span><strong id="dwStatus">Loading…</strong></div><div><span class="crosscheck-label">ESA WorldCover 2021</span><strong id="wcStatus">Loading…</strong></div><div><span class="crosscheck-label">GISTDA Land Use</span><strong id="gistdaStatus">Loading…</strong></div><div><span class="crosscheck-label">Mapped overlap</span><strong id="lulcAgreement">—</strong></div></div><p id="lulcSummary" class="crosscheck-summary">External consistency context only; not accuracy.</p><details><summary>Reference provenance</summary><div id="lulcProvenance" class="crosscheck-details"></div></details>';
    $('#segEvidence').innerHTML = `<b>${esc(t.dominant_class_name || 'Model prediction')}</b><br>R1 ${Number(t.R1_percent || 0).toFixed(1)}% · R2 ${Number(t.R2_percent || 0).toFixed(1)}% · R3 ${Number(t.R3_percent || 0).toFixed(1)}%<br>Entropy ${Number(t.entropy || 0).toFixed(3)}`;
    $('#spatialEvidence').innerHTML = `Valid pixels ${Number(t.valid_pixel_count || 0).toLocaleString()}<br>Centroid ${Number(t.centroid_lat || 0).toFixed(5)}, ${Number(t.centroid_lon || 0).toFixed(5)}`;
    $('#spectralEvidence').textContent = 'Running prediction-conditioned NDVI/NDWI consistency check…';
    const geom = {type:'bbox', coordinates:t.bbox};
    const cls = Number(t.dominant_class || 0);
    try {
      const makeReq = () => ({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({geometry:geom, predicted_class:cls})});
      const [sr, er, lr] = await Promise.all([fetch(window.GeoAIApp.url('api/tools/spectral-consistency'), makeReq()), fetch(window.GeoAIApp.url('api/tools/external-reference'), makeReq()), fetch(window.GeoAIApp.url('api/evidence/lulc-comparison'), makeReq())]);
      const spectral = await sr.json(), external = await er.json(), lulcData = await lr.json();
      const spectralStatus = spectral.overall_spectral_status || 'UNAVAILABLE';
      const externalStatus = external.status || 'UNAVAILABLE';
      $('#spectralEvidence').innerHTML = `NDVI ${statusText(spectral.ndvi?.status)} · NDWI ${statusText(spectral.ndwi?.status)}<br>Selected predicted pixels: ${Number(spectral.pixel_count || 0).toLocaleString()}<br><small>${esc(spectral.rule || '')}</small>`;
      $('#externalEvidence').innerHTML = `External evidence <span>${esc(statusText(externalStatus))}${external.feature_count ? ` · ${external.feature_count} OSM features` : ''}</span>`;
      const cross = $('#crosscheckSection'); if (cross) cross.hidden = false;
      $('#crosscheckSpectral').textContent = statusText(spectralStatus);
      $('#crosscheckExternal').textContent = statusText(externalStatus);
      const [label, clsName] = strength(spectralStatus, externalStatus);
      $('#evidenceStrength').textContent = label; $('#evidenceStrength').className = `evidence-status ${clsName}`;
      $('#crosscheckSummary').textContent = `${label} evidence · contextual consistency only; this is not model accuracy.`;
      $('#crosscheckDetails').innerHTML = `<details><summary>Method details</summary><p>Class-relative IQR and p10–p90 rules on frozen full-AOI predictions. OSM status is contextual only (R1/R2/R4).</p><p>${esc(external.message || '')}</p></details>`;
      $('#dwStatus').textContent = statusText(lulcData.dynamic_world?.status);
      $('#wcStatus').textContent = `${statusText(lulcData.worldcover?.status)} · 2021`;
      $('#gistdaStatus').textContent = statusText(lulcData.gistda?.status);
      $('#lulcAgreement').textContent = lulcData.agreement_percent == null ? '—' : `${Number(lulcData.agreement_percent).toFixed(1)}%`;
      $('#lulcSummary').textContent = `GISTDA mapped overlap ${Number(lulcData.mapped_overlap_pixels || 0).toLocaleString()} pixels; external products are reference datasets, not ground truth.`;
      $('#lulcProvenance').innerHTML = `Dynamic World: 10 m, temporal window ${esc((lulcData.temporal_metadata?.dynamic_world?.window || []).join(' to '))}.<br>ESA WorldCover: 10 m, reference year 2021.<br>GISTDA: 1:50,000, older reference period B.E. 2560–2561.`;
      const explain = $('#whyContent');
      if (explain) explain.innerHTML = `<p><b>${esc(t.tile_id)}</b> was selected from semantic ranking or the map.</p><p>Operational A7-T (A7_RGBN_REVISED7_TVERSKY) proportions are predictions, not ground truth.</p><p>Spectral consistency: <b>${statusText(spectralStatus)}</b>; external context: <b>${statusText(externalStatus)}</b>. Evidence consistency ≠ model accuracy.</p>`;
    } catch (err) {
      $('#spectralEvidence').textContent = 'Evidence cross-check unavailable.';
      $('#evidenceStrength').textContent = 'LIMITED'; $('#evidenceStrength').className = 'evidence-status limited';
    }
    const why = $('#whyBtn'); if (why) { why.disabled = false; why.dataset.tile = t.tile_id; }
  }
  emptyState();
  window.addEventListener('tile-selected', e => render(e.detail));
  document.addEventListener('click', async e => {
    const b = e.target.closest('.why-result'); if (!b) return;
    const id = b.closest('.result')?.querySelector('.tile')?.textContent; if (!id) return;
    try { render(await fetch(window.GeoAIApp.url(`api/tiles/${encodeURIComponent(id)}`)).then(r => r.json())); } catch (_) { emptyState(); }
  });
  $('#whyBtn')?.addEventListener('click', () => { const detail = $('#whyDetail'); if (detail) { detail.hidden = false; detail.open = true; detail.scrollIntoView({behavior:'smooth', block:'nearest'}); } });
})();
