/*
CLEAN PROJECT HEADER
ไฟล์: workspace.js
หน้าที่: ส่วนแสดงผลและ interaction ของ GeoAI Explorer
Input: ข้อมูลจาก API และ static assets
Output: หน้าเว็บหรือพฤติกรรม UI
Dependency สำคัญ: backend API และ class schema
สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
*/
(() => {
  const $ = s => document.querySelector(s);
  const thesis = $('#thesisToggle'), panel = $('#thesisPanel');
  function setThesis(on) {
    if (panel) panel.hidden = !on;
    document.querySelectorAll('.scoring-details').forEach(d => { d.hidden = !on; if (!on) d.open = false; });
  }
  thesis?.addEventListener('change', () => setThesis(thesis.checked));
  document.querySelectorAll('.suggestion-grid button,.suggestion-extra button').forEach(b => b.addEventListener('click', () => { const q = $('#agentQuery'); q.value = b.dataset.q; $('#agentAskBtn')?.click(); }));
  $('#moreSuggestions')?.addEventListener('click', () => {
    const extra = $('#suggestionExtra'), btn = $('#moreSuggestions');
    const open = extra.hidden;
    extra.hidden = !open;
    btn.textContent = open ? 'ซ่อนคำแนะนำ' : 'ดูเพิ่มเติม';
    btn.setAttribute('aria-expanded', String(open));
  });
  $('#drawHintBtn')?.addEventListener('click', () => window.dispatchEvent(new CustomEvent('aoi-draw-menu')));
  function showAnalysis() {
    const details = document.querySelector('.workspace-layers');
    if (details) details.open = true;
    const right=document.querySelector('.right-panel');
    right?.classList.add('is-open');right?.classList.remove('has-query-results');
    // Keep the document anchored on the map. Scroll only the floating results panel.
    if (right) right.scrollTo({top:0,behavior:'smooth'});
  }
  $('#analysisHintBtn')?.addEventListener('click', showAnalysis);
  let hasSearchResults=false;
  function selection() {
    const active = Boolean(window.selectedGeometry||window.selectedBbox), status = $('#selectionStatus');
    if (status) status.textContent = active ? 'เลือกพื้นที่แล้ว' : hasSearchResults ? 'กำลังแสดงผลค้นหา' : 'แผนที่พร้อมใช้งาน';
    ['selectionAnalyze','selectionArea','selectionExport'].forEach(id => { const b = $('#' + id); if (b) b.disabled = !active; });
    if($('#selectionClear'))$('#selectionClear').disabled=!(active||hasSearchResults);
    document.querySelector('.toolbar-action-group')?.classList.toggle('has-selection',active);
  }
  setInterval(selection, 400);
  $('#selectionClear')?.addEventListener('click', () => { window.clearMapWorkspace?.(); hasSearchResults=false; selection(); });
  $('#selectionAnalyze')?.addEventListener('click', () => { if (window.GeoAIAoiAnalysis?.analyze) window.GeoAIAoiAnalysis.analyze(); else { showAnalysis(); $('#runAnalysisBtn')?.click(); } });
  $('#selectionArea')?.addEventListener('click', () => { const q = $('#agentQuery'); q.value = 'คำนวณพื้นที่ที่ฉันเลือกเป็นไร่'; $('#agentAskBtn')?.click(); });
  $('#selectionExport')?.addEventListener('click', () => { showAnalysis(); $('#runAnalysisBtn')?.click(); });
  $('#legendToggle')?.addEventListener('click', () => { const body = $('#legendBody'), btn = $('#legendToggle'); const open = body.hidden; body.hidden = !open; btn.textContent = open ? 'Legend ▴' : 'Legend'; btn.setAttribute('aria-expanded', String(open)); });
  window.addEventListener('map-selection-changed',selection);
  window.addEventListener('map-search-results',e=>{hasSearchResults=Boolean(e.detail?.active);selection()});
  window.addEventListener('map-workspace-cleared',()=>{hasSearchResults=false;selection()});
  setThesis(Boolean(thesis?.checked));
  selection();
})();
