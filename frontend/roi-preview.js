/* Exact A7-T categorical raster ROI preview. It never alters the prediction raster. */
(() => {
  let group, preview, dimmer, controller, control, mode = 'blend', opacity = .62;
  const fmt = value => Number(value || 0).toLocaleString('th-TH', {maximumFractionDigits: 2});
  const classLabel = item => `${item.class_id} ${item.class_name_th || item.class_name}`;
  const bounds = bbox => [[bbox[1], bbox[0]], [bbox[3], bbox[2]]];

  function refreshPreview() {
    if (!preview) return;
    preview.setOpacity(mode === 'rgb' ? 0 : mode === 'a7t' ? 1 : opacity);
    control?.getContainer()?.querySelectorAll('[data-roi-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.roiMode === mode)));
    const slider = control?.getContainer()?.querySelector('input[type="range"]');
    if (slider) { slider.value = String(Math.round(opacity * 100)); slider.disabled = mode !== 'blend'; }
  }

  function clear() {
    controller?.abort(); controller = null;
    if (group) group.clearLayers();
    preview = null; dimmer = null;
    if (control) control.getContainer().classList.remove('is-visible');
  }

  function renderInsight(data) {
    const host = control?.getContainer()?.querySelector('[data-roi-insight]');
    if (!host) return;
    const dominant = data.dominant_class || {};
    const active = (data.classes || []).filter(item => item.pixels > 0).sort((a, b) => b.pixels - a.pixels);
    host.replaceChildren();
    const title = document.createElement('p'); title.className = 'roi-summary';
    title.textContent = `ROI · ${fmt(data.total_area_rai)} ไร่ · เด่น: ${classLabel(dominant)}`;
    host.append(title);
    const list = document.createElement('div'); list.className = 'roi-class-list';
    active.forEach(item => {
      const row = document.createElement('div'); row.className = 'roi-class-row';
      const swatch = document.createElement('i'); swatch.style.background = window.GeoAIClasses.color(item.class_id);
      const label = document.createElement('span'); label.textContent = classLabel(item);
      const value = document.createElement('strong'); value.textContent = `${fmt(item.percent)}% · ${fmt(item.area_rai)} ไร่`;
      row.append(swatch, label, value); list.append(row);
    });
    host.append(list);
  }

  function installControl() {
    if (!window.map || !window.L || control) return;
    control = L.control({position: 'topright'});
    control.onAdd = () => {
      const root = L.DomUtil.create('section', 'roi-preview-control');
      root.setAttribute('aria-label', 'ตัวอย่างการจำแนกในกรอบที่เลือก');
      root.innerHTML = `<div class="roi-preview-head"><strong>กรอบที่เลือก</strong><button type="button" data-roi-close aria-label="ปิดตัวอย่าง ROI">×</button></div>
        <div class="roi-segmented" role="group" aria-label="รูปแบบแสดงผลในกรอบ"><button type="button" data-roi-mode="rgb">RGB</button><button type="button" data-roi-mode="a7t">A7-T</button><button type="button" data-roi-mode="blend">Blend</button></div>
        <label class="roi-opacity">ความโปร่งใส <input type="range" min="20" max="100" value="62" aria-label="ความโปร่งใสของ A7-T ในกรอบ"/></label>
        <div data-roi-insight class="roi-insight">กำลังอ่าน A7-T Full AOI…</div>`;
      L.DomEvent.disableClickPropagation(root); L.DomEvent.disableScrollPropagation(root);
      root.querySelectorAll('[data-roi-mode]').forEach(button => button.addEventListener('click', () => { mode = button.dataset.roiMode; refreshPreview(); }));
      root.querySelector('input[type="range"]').addEventListener('input', event => { opacity = Number(event.target.value) / 100; mode = 'blend'; refreshPreview(); });
      root.querySelector('[data-roi-close]').addEventListener('click', () => window.clearRoiPreview());
      return root;
    };
    control.addTo(map);
  }

  function addDimmer(bbox) {
    if (!window.fullAoiBounds) return;
    const outer = [
      fullAoiBounds[0], [fullAoiBounds[0][0], fullAoiBounds[1][1]], fullAoiBounds[1], [fullAoiBounds[1][0], fullAoiBounds[0][1]],
    ];
    const inner = [[bbox[1], bbox[0]], [bbox[1], bbox[2]], [bbox[3], bbox[2]], [bbox[3], bbox[0]]];
    dimmer = L.polygon([outer, inner], {pane: 'roiMask', stroke: false, fillColor: '#13251d', fillOpacity: .15, interactive: false, fillRule: 'evenodd'}).addTo(group);
  }

  async function show(bbox) {
    if (!Array.isArray(bbox) || bbox.length !== 4 || !window.map || !window.L) return;
    installControl(); clear(); installControl();
    mode = 'blend';
    // RGB remains outside the rectangle; the categorical PNG is attached only to ROI bounds.
    window.setFullMapMode?.('rgb');
    if (!map.getPane('roiPreview')) { map.createPane('roiPreview'); map.getPane('roiPreview').style.zIndex = '365'; }
    if (!map.getPane('roiMask')) { map.createPane('roiMask'); map.getPane('roiMask').style.zIndex = '370'; }
    group = L.layerGroup().addTo(map);
    const params = new URLSearchParams({west: bbox[0], south: bbox[1], east: bbox[2], north: bbox[3], v: window.GeoAIClasses.version()});
    preview = L.imageOverlay(`/api/roi/preview?${params}`, bounds(bbox), {opacity, pane: 'roiPreview', interactive: false, className: 'roi-categorical-preview'}).addTo(group);
    addDimmer(bbox); refreshPreview();
    const root = control?.getContainer(); root?.classList.add('is-visible');
    controller = new AbortController();
    try {
      const response = await fetch('/api/roi/insight', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({bbox}), signal: controller.signal});
      if (!response.ok) throw new Error('ROI insight unavailable');
      renderInsight(await response.json());
    } catch (error) {
      if (error.name !== 'AbortError') {
        const host = root?.querySelector('[data-roi-insight]'); if (host) host.textContent = 'ไม่สามารถสรุปผลในกรอบนี้ได้';
      }
    }
  }

  window.showRoiPreview = show;
  window.clearRoiPreview = clear;
})();
