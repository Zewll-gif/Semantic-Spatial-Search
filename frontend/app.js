/*
CLEAN PROJECT HEADER
ไฟล์: app.js
หน้าที่: ส่วนแสดงผลและ interaction ของ GeoAI Explorer
Input: ข้อมูลจาก API และ static assets
Output: หน้าเว็บหรือพฤติกรรม UI
Dependency สำคัญ: backend API และ class schema
สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
*/
let map, tiles=[], fullTiles=[], testTiles=[], layers=new Map(), fullGridGroup, testGroup, searchGroup, selectedGroup, splitGroups={}, fullAoiBounds, scope='FULL_AOI';
let selectionShape=null, drawBoxButton=null, stopActiveDrawing=null;
const $=s=>document.querySelector(s);
const appUrl=value=>window.GeoAIApp.url(value);
const esc=s=>String(s).replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
function bounds(t){return [[t.bbox[1],t.bbox[0]],[t.bbox[3],t.bbox[2]]]}
function dominantCode(t){const r=t.class_percentages||{};const codes=['R1','R2','R3','R4','R5','R6','R7'];return codes.reduce((best,code)=>Number(r[code]||0)>Number(r[best]||0)?code:best,'R1')}
function dominantName(t){const code=dominantCode(t);return `${code} ${window.GeoAIClasses.name(code)}`}
function color(t){return window.GeoAIClasses.color(dominantCode(t))}
function initMap(aoi,splitData){
  if(!window.L){$('#map').innerHTML='<div style="padding:24px;color:#657b86">Leaflet ไม่พร้อมใช้งาน แต่ผลลัพธ์และพิกัดยังเปิดดูได้</div>';return}
  fullAoiBounds=aoi.bounds.leaflet_bounds;
  map=L.map('map',{zoomControl:true,preferCanvas:true,zoomSnap:0.1,zoomDelta:0.5}).setView(L.latLngBounds(fullAoiBounds).getCenter(),11);
  map.createPane('aoiImagery');map.getPane('aoiImagery').style.zIndex='350';
  map.createPane('aoiThematic');map.getPane('aoiThematic').style.zIndex='360';
  const basemaps={
    street:L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}),
    imagery:L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'Sources: Esri and contributors',maxZoom:19}),
    terrain:L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',{attribution:'Map data © OpenStreetMap contributors · style © OpenTopoMap',maxZoom:17})
  };
  let activeBasemap=basemaps.imagery.addTo(map), activeBasemapKey='imagery';
  // Display-only soft edges; source imagery and canonical A7-T pixels remain unchanged.
  const fullRgb=L.imageOverlay(appUrl('aoi/full_aoi_rgb_soft_edge.png?v=map-integration-2'),fullAoiBounds,{opacity:0.94,interactive:false,pane:'aoiImagery'}).addTo(map);
  // Categorical XYZ tiles are rendered on demand from the frozen 3 m GeoTIFF.
  const tileOptions={pane:'aoiThematic',opacity:1,interactive:false,noWrap:true,bounds:fullAoiBounds,maxNativeZoom:18,maxZoom:19,keepBuffer:2,className:'a7t-categorical-tile'};
  const tileUrl=(classes='')=>appUrl(`api/map/a7t/{z}/{x}/{y}.png?v=${window.GeoAIClasses.version()}${classes?`&classes=${encodeURIComponent(classes)}`:''}`);
  const fullPrediction=L.tileLayer(tileUrl(),tileOptions);
  let filteredPrediction=null,activeMapMode='rgb';
  const ndvi=L.imageOverlay(appUrl('analysis-assets/NDVI_FULL_AOI_PREVIEW.png'),fullAoiBounds,{opacity:.76,interactive:false,pane:'aoiThematic'});
  const ndwi=L.imageOverlay(appUrl('analysis-assets/NDWI_FULL_AOI_PREVIEW.png'),fullAoiBounds,{opacity:.76,interactive:false,pane:'aoiThematic'});
  fullGridGroup=L.layerGroup();testGroup=L.layerGroup();searchGroup=L.layerGroup().addTo(map);selectedGroup=L.layerGroup().addTo(map);
  splitGroups={TRAIN14:L.layerGroup(),VAL4:L.layerGroup()};drawGrid();drawTestTiles();drawSplits(splitData.records||[]);
  L.control.layers({}, {'ผลค้นหา':searchGroup,'ขอบเขต Tile':fullGridGroup,'TRAIN14':splitGroups.TRAIN14,'VAL4':splitGroups.VAL4,'TEST40':testGroup,'พื้นที่ที่เลือก':selectedGroup},{collapsed:true,position:'bottomright'}).addTo(map);
  const modes={rgb:{label:'RGB',note:'PlanetScope RGB ของโครงการ'},prediction:{label:'A7‑T',note:'ผลจำแนก A7‑T · ไม่ใช่ Ground Truth'},ndvi:{label:'NDVI',note:'ดัชนีพืชพรรณ · ข้อมูลประกอบ'},ndwi:{label:'NDWI',note:'ดัชนีน้ำ · ข้อมูลประกอบ'}};
  const modeLayers={rgb:[fullRgb],ndvi:[fullRgb,ndvi],ndwi:[fullRgb,ndwi]};
  const panel=document.createElement('div');panel.className='map-view-panel';panel.setAttribute('aria-label','เลือกรูปแบบแผนที่');
  const head=document.createElement('div');head.className='map-view-head';head.innerHTML='<span>ชั้นข้อมูล</span><span aria-hidden="true">◫</span>';panel.appendChild(head);
  const choices=document.createElement('div');choices.className='map-view-choices';choices.setAttribute('role','group');choices.setAttribute('aria-label','เลือกรูปแบบแผนที่');panel.appendChild(choices);
  const note=document.createElement('p');note.className='map-view-note';panel.appendChild(note);
  const baseLabel=document.createElement('div');baseLabel.className='map-base-label';baseLabel.textContent='พื้นหลังแผนที่';panel.appendChild(baseLabel);
  const baseChoices=document.createElement('div');baseChoices.className='map-base-choices';baseChoices.setAttribute('role','group');baseChoices.setAttribute('aria-label','เลือกพื้นหลังแผนที่');panel.appendChild(baseChoices);
  const buttons={};
  Object.entries(modes).forEach(([key,mode])=>{const button=document.createElement('button');button.type='button';button.textContent=mode.label;button.dataset.mapMode=key;button.setAttribute('aria-label',`แสดง ${mode.label}: ${mode.note}`);button.setAttribute('aria-pressed','false');button.addEventListener('click',()=>setMode(key));choices.appendChild(button);buttons[key]=button});
  const setMode=key=>{[fullRgb,fullPrediction,filteredPrediction,ndvi,ndwi].filter(Boolean).forEach(layer=>{if(map.hasLayer(layer))map.removeLayer(layer)});(key==='prediction'?[fullRgb,filteredPrediction||fullPrediction]:modeLayers[key]).forEach(layer=>layer.addTo(map));Object.entries(buttons).forEach(([id,button])=>button.setAttribute('aria-pressed',String(id===key)));note.textContent=modes[key].note;panel.dataset.mode=key;activeMapMode=key};
  window.setFullMapMode=setMode;
  window.getFullMapMode=()=>activeMapMode;
  window.showFullClassification=()=>{if(filteredPrediction&&map.hasLayer(filteredPrediction))map.removeLayer(filteredPrediction);filteredPrediction=null;setMode('prediction')};
  window.showClassFilteredClassification=classIds=>{
    const codes=[...new Set(classIds.map(code=>String(code).toUpperCase()))].sort();
    codes.forEach(code=>window.GeoAIClasses.color(code));
    if(filteredPrediction&&map.hasLayer(filteredPrediction))map.removeLayer(filteredPrediction);
    filteredPrediction=L.tileLayer(tileUrl(codes.join(',')),tileOptions);
    setMode('prediction');
  };
  window.clearClassFilteredClassification=()=>{if(filteredPrediction&&map.hasLayer(filteredPrediction))map.removeLayer(filteredPrediction);filteredPrediction=null;setMode(activeMapMode)};
  const baseButtons={};
  const baseMeta={street:'ถนน',imagery:'ดาวเทียม',terrain:'ภูมิประเทศ'};
  const setBasemap=key=>{if(!basemaps[key])return;if(activeBasemap&&map.hasLayer(activeBasemap))map.removeLayer(activeBasemap);activeBasemap=basemaps[key];activeBasemapKey=key;activeBasemap.addTo(map);Object.entries(baseButtons).forEach(([id,button])=>button.setAttribute('aria-pressed',String(id===key)));};
  window.setMapBasemap=setBasemap;
  window.getMapBasemap=()=>activeBasemapKey;
  Object.entries(baseMeta).forEach(([key,label])=>{const button=document.createElement('button');button.type='button';button.textContent=label;button.setAttribute('aria-pressed','false');button.addEventListener('click',()=>setBasemap(key));baseChoices.appendChild(button);baseButtons[key]=button});
  $('#map').parentElement.appendChild(panel);L.DomEvent.disableClickPropagation(panel);L.DomEvent.disableScrollPropagation(panel);setMode('rgb');setBasemap('imagery');
  fitFullAoi();$('#fullAoiBtn').addEventListener('click',fitFullAoi);
}
function fitFullAoi(){
  if(!map||!fullAoiBounds)return;
  const compact=map.getSize().x<760;
  // Leave room for functional controls while using fractional zoom to avoid a tiny AOI.
  map.fitBounds(fullAoiBounds,{paddingTopLeft:compact?[12,90]:[30,105],paddingBottomRight:compact?[12,76]:[30,72],animate:false});
}
window.fitFullAoi=fitFullAoi;
function drawGrid(){if(!map)return;fullTiles.forEach(t=>{const l=L.rectangle(bounds(t),{color:'#6d8794',weight:.5,fill:false,opacity:.45});l.bindTooltip(`${t.tile_id} · ${t.dataset_role||'UNLABELED_DEPLOYMENT'}`);l.addTo(fullGridGroup)})}
function drawTestTiles(){if(!map)return;testTiles.forEach(t=>{const l=L.rectangle(bounds(t),{color:color(t),weight:1,fillOpacity:.18});l.bindTooltip(t.tile_id);l.bindPopup(`<strong>${esc(t.tile_id)}</strong><br>${esc(dominantName(t))}`);l.on('click',()=>showTile(t.tile_id));l.addTo(testGroup);layers.set(t.tile_id,l)})}
function drawSplits(records){records.filter(r=>r.split!=='TEST40').forEach(r=>{const g=splitGroups[r.split];if(!g)return;const l=L.rectangle([[r.bbox[1],r.bbox[0]],[r.bbox[3],r.bbox[2]]],{color:r.split==='TRAIN14'?'#547b91':'#a76f3e',weight:1,dashArray:'4 5',fillOpacity:.05});l.bindTooltip(`${r.tile_id} · ${r.split}`);l.addTo(g)})}
function renderResults(payload){$('#resultCount').textContent=payload.results.length;$('#queryMeta').textContent=`${payload.scope} · intent: ${payload.intent} · matched: ${payload.matched_tokens.join(', ')||'default'} · weights: ${Object.entries(payload.feature_weights).map(([k,v])=>`${k} ${v}`).join(' · ')}`;const host=$('#results');host.innerHTML='';if(searchGroup)searchGroup.clearLayers();payload.results.forEach(item=>{const t=document.getElementById('resultTemplate').content.cloneNode(true);const card=t.querySelector('.result');card.dataset.tileId=item.tile_id;card.setAttribute('aria-label',`ผลลัพธ์ ${item.rank} ${item.tile_id}`);t.querySelector('.rank').textContent=`#${item.rank}`;t.querySelector('.tile').textContent=item.tile_id;t.querySelector('.score').textContent=`คะแนน ${item.score.toFixed(2)} / 100`;t.querySelector('.result-meta').textContent=`${item.dataset_role||'UNLABELED_DEPLOYMENT'} · ${dominantName(item)}`;const d=t.querySelector('.distribution');Object.entries(item.class_percentages).filter(([,v])=>v>.02).sort((a,b)=>b[1]-a[1]).slice(0,3).forEach(([k,v])=>{const p=document.createElement('span');p.className='pill';p.textContent=`${k} ${v.toFixed(1)}%`;d.appendChild(p)});const rgb=t.querySelector('.rgb');rgb.src=appUrl(`assets/${item.tile_id}/rgb`);const over=t.querySelector('.overlay');over.src=appUrl(`assets/${item.tile_id}/overlay?v=${window.GeoAIClasses.version()}`);t.querySelector('.media input').addEventListener('input',e=>over.style.opacity=e.target.value);t.querySelector('.explanation').textContent=item.explanation;t.querySelector('.zoom').setAttribute('aria-label',`ซูมไปยัง ${item.tile_id}`);t.querySelector('.zoom').addEventListener('click',()=>showTile(item.tile_id));t.querySelector('.why-result').addEventListener('click',()=>showTile(item.tile_id));host.appendChild(t);const testLayer=layers.get(item.tile_id);if(testLayer){testLayer.setStyle({weight:3,color:'#e36f42',fillOpacity:.28});testLayer.bindPopup(`<strong>#${item.rank} · ${esc(item.tile_id)}</strong><br>Score ${item.score.toFixed(2)}<br>${esc(dominantName(item))}`)}if(searchGroup){const l=L.rectangle(bounds(item),{color:'#e36f42',weight:3,fill:false});l.bindPopup(`<strong>#${item.rank} · ${esc(item.tile_id)}</strong><br>Score ${item.score.toFixed(2)}`);l.addTo(searchGroup)}})}
function showTile(id){const t=fullTiles.find(x=>x.tile_id===id)||testTiles.find(x=>x.tile_id===id);if(!t)return;if(map){map.fitBounds(bounds(t),{maxZoom:13});if(selectedGroup){selectedGroup.clearLayers();L.imageOverlay(appUrl(`assets/${id}/overlay?v=${window.GeoAIClasses.version()}`),bounds(t),{opacity:.58,interactive:false}).addTo(selectedGroup)}}document.querySelectorAll('.result.is-selected').forEach(x=>x.classList.remove('is-selected'));const el=[...document.querySelectorAll('.result')].find(x=>x.dataset.tileId===id);if(el){el.classList.add('is-selected');el.scrollIntoView({behavior:'smooth',block:'center'})}window.dispatchEvent(new CustomEvent('tile-selected',{detail:t}))}
function resetTestStyles(){testTiles.forEach(t=>{const layer=layers.get(t.tile_id);if(layer)layer.setStyle({color:color(t),weight:1,fillOpacity:.18})})}
function clearSelection(){
  if(stopActiveDrawing)stopActiveDrawing();
  window.clearRoiPreview?.();
  window.selectedBbox=null;window.selectedGeometry=null;selectionShape=null;
  if(selectedGroup)selectedGroup.clearLayers();
  if(drawBoxButton){drawBoxButton.textContent='▧';drawBoxButton.classList.remove('is-active')}
  window.dispatchEvent(new CustomEvent('map-selection-changed',{detail:{active:false}}));
}
window.clearMapWorkspace=()=>{
  clearSelection();
  if(searchGroup)searchGroup.clearLayers();
  resetTestStyles();
  fitFullAoi();
  window.dispatchEvent(new CustomEvent('map-clear-search'));
  window.dispatchEvent(new CustomEvent('map-workspace-cleared'));
};
async function runSearch(q){const res=await fetch(appUrl(`api/search?q=${encodeURIComponent(q)}&top_n=10&scope=${scope}`));renderResults(await res.json())}
async function boot(){const [full,test,aoi,splitData]=await Promise.all([fetch(appUrl('api/tiles?scope=FULL_AOI')).then(r=>r.json()),fetch(appUrl('api/tiles?scope=TEST40_ONLY')).then(r=>r.json()),fetch(appUrl('api/aoi')).then(r=>r.json()),fetch(appUrl('api/splits')).then(r=>r.json())]);fullTiles=full.tiles;testTiles=test.tiles;tiles=fullTiles;$('#tileCount').textContent=`${full.count} AOI tiles · 40 TEST40`;$('#aoiSize').textContent=`${aoi.metadata.source_size.width}×${aoi.metadata.source_size.height}`;$('#aoiCrs').textContent=aoi.metadata.crs;initMap(aoi,splitData);$('#scopeSelect').addEventListener('change',e=>{scope=e.target.value;runSearch($('#query').value);document.querySelector('.results-section').hidden=false;document.querySelector('.right-panel').classList.add('is-open')});$('#searchBtn').addEventListener('click',()=>{runSearch($('#query').value);document.querySelector('.results-section').hidden=false;document.querySelector('.right-panel').classList.add('is-open')});$('#query').addEventListener('keydown',e=>{if(e.key==='Enter')runSearch($('#query').value)});document.querySelectorAll('.chips button').forEach(b=>b.addEventListener('click',()=>{$('#query').value=b.dataset.q;runSearch(b.dataset.q)}))}
window.GeoAIClasses.ready.then(boot).catch(err=>{$('#queryMeta').textContent=String(err)});
function installSimpleDrawing(){
  if(!map||!window.L||document.getElementById('drawBoxBtn'))return;
  const ctl=L.control({position:'topleft'});
  ctl.onAdd=()=>{
    const d=L.DomUtil.create('div','leaflet-bar'),b=L.DomUtil.create('a','',d);drawBoxButton=b;
    b.id='drawBoxBtn';b.href='#';b.title='วาดกรอบ: คลิกมุมแรก แล้วคลิกมุมตรงข้าม';b.textContent='▧';
    L.DomEvent.on(b,'click',L.DomEvent.stop).on(b,'click',()=>{
      clearSelection();
      let start=null;
      map.getContainer().style.cursor='crosshair';b.textContent='1';b.classList.add('is-active');
      const move=e=>{if(selectionShape&&start)selectionShape.setBounds(L.latLngBounds(start,e.latlng))};
      const stop=()=>{map.off('mousemove',move);map.off('click',once);map.getContainer().style.cursor='';stopActiveDrawing=null};
      stopActiveDrawing=stop;
      const once=e=>{
        if(!start){start=e.latlng;selectionShape=L.rectangle([start,start],{color:'#f8fbf9',weight:3,opacity:.95,fillColor:'#163f34',fillOpacity:.05,dashArray:'8 5'}).addTo(selectedGroup);map.on('mousemove',move);b.textContent='2';return}
        // Commit the second click itself as the final corner. This also works
        // when a user clicks twice without a mousemove between the two clicks.
        selectionShape.setBounds(L.latLngBounds(start,e.latlng));
        const bb=selectionShape.getBounds();stop();window.selectedBbox=[bb.getWest(),bb.getSouth(),bb.getEast(),bb.getNorth()];
        window.selectedGeometry=selectionShape.toGeoJSON().geometry;b.textContent='✓';b.classList.remove('is-active');
        window.clearRoiPreview?.();window.dispatchEvent(new CustomEvent('map-selection-changed',{detail:{active:true,bbox:window.selectedBbox,geometry:window.selectedGeometry,mode:'rectangle'}}));
      };
      map.on('click',once);
    });
    return d;
  };
  ctl.addTo(map);
}
setTimeout(installSimpleDrawing,5000);
