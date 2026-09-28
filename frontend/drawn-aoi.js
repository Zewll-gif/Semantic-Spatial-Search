/* Rectangle, polygon and freehand AOI drawing. Geometry is GeoJSON EPSG:4326. */
(() => {
  let menu, context, hint, activeStop = null, lastMode = 'rectangle';
  const style = { color: '#f8fbf9', weight: 3, opacity: .95, fillColor: '#163f34', fillOpacity: .05, dashArray: '8 5' };
  const mapElement = () => map?.getContainer();
  const stop = () => { activeStop?.(); activeStop = null; mapElement()?.classList.remove('is-drawing-aoi'); hideHint(); };
  const bboxFromLayer = layer => { const b = layer.getBounds(); return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]; };
  const showHint = text => { if (!hint) return; hint.textContent = text; hint.classList.add('is-visible'); };
  const hideHint = () => hint?.classList.remove('is-visible');
  const setContext = state => {
    if (!context) return;
    context.hidden = state === 'hidden'; context.dataset.state = state;
    const analyze = context.querySelector('[data-aoi-analyze]');
    analyze.disabled = state === 'loading'; analyze.textContent = state === 'loading' ? 'กำลังวิเคราะห์…' : state === 'analyzed' ? 'วิเคราะห์อีกครั้ง' : 'วิเคราะห์พื้นที่นี้';
  };
  const commit = (layer, mode) => {
    stop(); window.clearRoiPreview?.();
    selectedGroup.clearLayers(); selectionShape = layer.addTo(selectedGroup);
    window.selectedGeometry = layer.toGeoJSON().geometry; window.selectedBbox = bboxFromLayer(layer); lastMode = mode;
    window.dispatchEvent(new CustomEvent('map-selection-changed', { detail: { active: true, geometry: window.selectedGeometry, bbox: window.selectedBbox, mode } }));
    setContext('ready'); menu?.closest('.map-toolbar')?.classList.remove('is-open');
  };
  const beginPolygon = () => {
    window.clearMapWorkspace?.(); stop(); showHint('คลิกเพื่อวางจุด และดับเบิลคลิกเพื่อปิดรูป');
    const points = []; let draft = L.polyline([], { ...style, fill: false }).addTo(selectedGroup);
    mapElement().classList.add('is-drawing-aoi');
    const click = event => { points.push(event.latlng); draft.setLatLngs(points); };
    const finish = event => { L.DomEvent.preventDefault(event.originalEvent); if (points.length < 3) return; commit(L.polygon(points, style), 'polygon'); };
    map.on('click', click); map.on('dblclick', finish); map.doubleClickZoom.disable();
    activeStop = () => { map.off('click', click); map.off('dblclick', finish); map.doubleClickZoom.enable(); if (draft && !window.selectedGeometry) selectedGroup.removeLayer(draft); };
  };
  const beginFreehand = () => {
    window.clearMapWorkspace?.(); stop(); showHint('กดค้างแล้วลากบนแผนที่เพื่อกำหนดพื้นที่');
    const container = mapElement(), points = []; let drawing = false, draft = L.polyline([], { ...style, fill: false }).addTo(selectedGroup);
    map.dragging.disable(); container.classList.add('is-drawing-aoi');
    const point = event => map.mouseEventToLatLng(event);
    const down = event => { if (event.button !== 0) return; drawing = true; points.push(point(event)); event.preventDefault(); };
    const move = event => { if (!drawing) return; const p = point(event), last = points[points.length - 1]; if (!last || map.distance(last, p) > 5) { points.push(p); draft.setLatLngs(points); } };
    const up = () => { if (!drawing) return; drawing = false; if (points.length >= 3) commit(L.polygon(points, style), 'freehand'); else stop(); };
    container.addEventListener('pointerdown', down); container.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
    activeStop = () => { container.removeEventListener('pointerdown', down); container.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); map.dragging.enable(); if (draft && !window.selectedGeometry) selectedGroup.removeLayer(draft); };
  };
  const beginRectangle = () => {
    window.clearMapWorkspace?.(); stop(); showHint('คลิกมุมแรก แล้วคลิกมุมตรงข้าม');
    let start = null, draft = null;
    mapElement().classList.add('is-drawing-aoi');
    const move = event => { if (draft && start) draft.setBounds(L.latLngBounds(start, event.latlng)); };
    const click = event => {
      if (!start) { start = event.latlng; draft = L.rectangle([start, start], style).addTo(selectedGroup); map.on('mousemove', move); return; }
      draft.setBounds(L.latLngBounds(start, event.latlng)); commit(draft, 'rectangle');
    };
    map.on('click', click);
    activeStop = () => { map.off('click', click); map.off('mousemove', move); if (draft && !window.selectedGeometry) selectedGroup.removeLayer(draft); };
  };
  const redraw = () => {
    window.clearMapWorkspace?.();
    const toolbar = menu?.closest('.map-toolbar'); toolbar?.classList.add('is-open');
    toolbar?.querySelector('.cinematic-tools-toggle')?.setAttribute('aria-expanded', 'true');
    setContext('hidden'); showHint('เลือก Rectangle, Polygon หรือ Freehand');
  };
  function install() {
    if (!window.map || !window.L || menu) return false;
    const toolbar = document.querySelector('#explore .map-toolbar'), card = document.querySelector('#explore .map-card'); if (!toolbar || !card) return false;
    menu = document.createElement('div'); menu.className = 'aoi-draw-menu'; menu.setAttribute('aria-label', 'เครื่องมือวาดพื้นที่วิเคราะห์');
    menu.innerHTML = `<button type="button" data-mode="rectangle" title="วาดสี่เหลี่ยม"><span aria-hidden="true">▭</span><b>Rectangle</b></button>
      <button type="button" data-mode="polygon" title="วาด Polygon"><span aria-hidden="true">⬡</span><b>Polygon</b></button>
      <button type="button" data-mode="freehand" title="วาดแบบอิสระ"><span aria-hidden="true">✎</span><b>Freehand</b></button>
      <button type="button" data-mode="clear" title="ล้างพื้นที่ที่วาด"><span aria-hidden="true">×</span><b>ล้าง</b></button>`;
    toolbar.append(menu);
    hint = document.createElement('div'); hint.className = 'aoi-draw-hint'; hint.setAttribute('role', 'status'); card.append(hint);
    context = document.createElement('div'); context.className = 'aoi-context-actions'; context.hidden = true;
    context.innerHTML = '<span>พื้นที่พร้อมวิเคราะห์</span><button type="button" class="secondary-btn" data-aoi-redraw>วาดใหม่</button><button type="button" class="primary-btn" data-aoi-analyze>วิเคราะห์พื้นที่นี้</button>';
    card.append(context);
    menu.querySelector('[data-mode="rectangle"]').addEventListener('click', beginRectangle);
    menu.querySelector('[data-mode="polygon"]').addEventListener('click', beginPolygon);
    menu.querySelector('[data-mode="freehand"]').addEventListener('click', beginFreehand);
    menu.querySelector('[data-mode="clear"]').addEventListener('click', () => window.clearMapWorkspace?.());
    context.querySelector('[data-aoi-redraw]').addEventListener('click', redraw);
    context.querySelector('[data-aoi-analyze]').addEventListener('click', () => window.GeoAIAoiAnalysis?.analyze?.());
    window.addEventListener('aoi-draw-menu', () => toolbar.classList.add('is-open'));
    window.addEventListener('map-selection-changed', event => { if (event.detail?.active) setContext('ready'); else setContext('hidden'); });
    window.addEventListener('map-workspace-cleared', () => { stop(); setContext('hidden'); });
    window.GeoAIDrawUI = { setAnalyzing: on => setContext(on ? 'loading' : 'ready'), setAnalyzed: on => setContext(on ? 'analyzed' : 'ready'), redraw: () => lastMode === 'polygon' ? beginPolygon() : lastMode === 'freehand' ? beginFreehand() : beginRectangle() };
    return true;
  }
  const timer = setInterval(() => { if (install()) clearInterval(timer); }, 300);
})();
