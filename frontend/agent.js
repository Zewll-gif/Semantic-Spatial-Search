/*
CLEAN PROJECT HEADER
ไฟล์: agent.js
หน้าที่: ส่วนแสดงผลและ interaction ของ GeoAI Explorer
Input: ข้อมูลจาก API และ static assets
Output: หน้าเว็บหรือพฤติกรรม UI
Dependency สำคัญ: backend API และ class schema
สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
*/
(() => {
  const q = document.getElementById('agentQuery'), unit = document.getElementById('agentUnit');
  const ask = document.getElementById('agentAskBtn'), answer = document.getElementById('agentAnswer'), status = document.getElementById('agentStatus');
  const providerControl = document.getElementById('llmProviderControl'), providerSelect = document.getElementById('llmProviderSelect');
  fetch(window.GeoAIApp.url('api/system/integration-status')).then(r => r.json()).then(data => {
    const llm=data.llm||{};
    if(providerSelect&&['openai','deepseek'].includes(llm.provider))providerSelect.value=llm.provider;
    if(providerControl&&llm.debug_selector)providerControl.hidden=false;
  }).catch(()=>{});
  if (!q || !ask) return;
  fetch(window.GeoAIApp.url('api/health')).then(r => r.json()).then(h => { status.textContent = h.agent_enabled ? (h.agent_fallback_available ? 'พร้อมใช้งาน · fallback ปลอดภัย' : 'พร้อมใช้งาน') : 'AI Agent unavailable — semantic search still available'; }).catch(() => { status.textContent = 'AI Agent ไม่พร้อมใช้งานชั่วคราว แต่ยังสามารถค้นหาพื้นที่ด้วย semantic search ได้'; });
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  ask.addEventListener('click', async () => {
    const question = q.value.trim(); if (!question) return;
    ask.disabled = true; ask.textContent = 'กำลังวิเคราะห์…'; answer.hidden = false; answer.textContent = 'กำลังเรียกใช้เครื่องมือเชิงพื้นที่และหลักฐานโครงการ…';
    try {
      const r = await fetch(window.GeoAIApp.url('api/agent'), {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({question, unit:unit.value, bbox:window.selectedBbox || null, scope:document.getElementById('scopeSelect')?.value || 'FULL_AOI'})});
      const data = await r.json(); if (!r.ok) throw new Error(data.detail || 'agent request failed');
      const tools = (data.tool_calls_used || []).join(', ') || 'ไม่มี';
      const evidence = (data.evidence?.model || []).slice(0,3).map(x => `<li>${esc(x.document_name)}</li>`).join('');
      const resultList = (data.results || []).slice(0,5).map(x => `<li><b>${esc(x.tile_id)}</b> · ${Number(x.score || 0).toFixed(2)} คะแนน</li>`).join('');
      answer.innerHTML = `<div><b>${esc(data.answer)}</b></div><div class="agent-meta">Scope: ${esc(data.scope_status)} · Evidence strength: ${esc(data.evidence_strength)} · Tools: ${esc(tools)} · ${esc(data.latency_ms)} ms</div>${resultList ? `<details open><summary>ผลลัพธ์พื้นที่</summary><ol>${resultList}</ol></details>` : ''}${evidence ? `<details><summary>Evidence sources</summary><ul>${evidence}</ul></details>` : ''}${(data.limitations||[]).length ? `<details><summary>ข้อจำกัด</summary><ul>${data.limitations.map(esc).map(x=>`<li>${x}</li>`).join('')}</ul></details>` : ''}`;
    } catch (e) { answer.textContent = `AI Agent ไม่พร้อมใช้งานชั่วคราว แต่ยังสามารถค้นหาพื้นที่ด้วย semantic search ได้ (${e.message})`; }
    finally { ask.disabled = false; ask.textContent = 'ถาม Agent'; }
  });
})();
