/*
CLEAN PROJECT HEADER
ไฟล์: product.js
หน้าที่: ส่วนแสดงผลและ interaction ของ GeoAI Explorer
Input: ข้อมูลจาก API และ static assets
Output: หน้าเว็บหรือพฤติกรรม UI
Dependency สำคัญ: backend API และ class schema
สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
*/
/* Canonical Agent V2 UI: no synthetic spatial results, no client-side GIS math. */
(() => {
  const byId = id => document.getElementById(id);
  const form = byId('productSearch');
  if (!form) return;
  const query = byId('productQuery'), panel = document.querySelector('.right-panel');
  const progress = byId('productProgress'), error = byId('productError');
  const cards = byId('productResultCards'), evidence = byId('productEvidence');
  const modeLabel = {spatial:'Spatial Query', knowledge:'Knowledge Query', mixed:'Mixed Analysis'};
  const queryClassIds = ['R1','R2','R3','R4','R5','R6','R7'];
  let activeRequest = null, requestNumber = 0, polygonLayer = null, selectedLayer = null, selectedPopup = null, lastQuestion = '', preSearchMapMode = null, preSearchBasemap = null, activeSearchClass = null, identifyRequest = null;
  let conversationHistory=[];
  let labelGroup=null, leaderGroup=null, distanceBufferGroup=null, referenceGroup=null, distanceLineGroup=null, distanceLabelGroup=null, distanceKeyControl=null;
  let resultFeatures=[], resultLayers=new Map(), bufferLayers=new Map(), referenceLayers=new Map(), distanceVisuals=new Map(), currentDistanceContext=null, relayoutTimer=null;
  const resultStyle=feature=>({color:window.GeoAIClasses.color(feature.properties?.class_id),weight:.8,opacity:.12,fillColor:window.GeoAIClasses.color(feature.properties?.class_id),fillOpacity:.025,className:'product-result-polygon'});
  const hoverStyle=feature=>({...resultStyle(feature),weight:2,opacity:.58,fillOpacity:.12});
  const selectedStyle=feature=>({...resultStyle(feature),color:'#ffffff',weight:3,opacity:1,fillOpacity:.78});
  let touchStart = null;
  const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const setText = (node, value) => { node.textContent = String(value ?? ''); return node; };
  const make = (tag, className, text) => { const n=document.createElement(tag); if(className)n.className=className; if(text!==undefined)setText(n,text); return n; };
  const show = () => { panel.classList.add('is-open','has-query-results'); document.body.classList.add('results-open'); };
  const hide = () => { panel.classList.remove('is-open'); document.body.classList.remove('results-open'); };
  const clearMap = () => {
    if(relayoutTimer)clearTimeout(relayoutTimer);
    if (polygonLayer && typeof searchGroup !== 'undefined' && searchGroup) searchGroup.removeLayer(polygonLayer);
    else if (polygonLayer && typeof map !== 'undefined' && map) map.removeLayer(polygonLayer);
    labelGroup?.clearLayers();leaderGroup?.clearLayers();
    distanceBufferGroup?.clearLayers();referenceGroup?.clearLayers();distanceLineGroup?.clearLayers();distanceLabelGroup?.clearLayers();
    if(distanceKeyControl&&map){map.removeControl(distanceKeyControl);distanceKeyControl=null}
    if(selectedPopup&&map){map.closePopup(selectedPopup);selectedPopup=null}
    polygonLayer=null;selectedLayer=null;resultFeatures=[];resultLayers.clear();bufferLayers.clear();referenceLayers.clear();distanceVisuals.clear();currentDistanceContext=null;activeSearchClass=null;
    if(identifyRequest)identifyRequest.abort();
    window.dispatchEvent(new CustomEvent('map-search-results',{detail:{active:false}}));
  };
  const restoreMapMode = () => { window.clearClassFilteredClassification?.(); if(preSearchMapMode!==null)window.setFullMapMode?.(preSearchMapMode); if(preSearchBasemap!==null)window.setMapBasemap?.(preSearchBasemap);preSearchMapMode=null;preSearchBasemap=null; };
  function status(message) { progress.hidden=false; progress.textContent=message; }
  function addEvidence(title, text) { const box=make('section','product-evidence-block'); box.append(make('h3','',title),make('p','',text)); evidence.append(box); return box; }
  function technical(data) {
    const box=make('section','product-evidence-block'); const details=make('details');
    details.append(make('summary','','View technical details'));
    const tools=(data.tool_trace||[]).map(x=>`${x.tool}: ${x.status}`).join(' · ') || 'ไม่มี';
    details.append(make('p','',`Tools: ${tools}`));
    if(data.llm) details.append(make('p','',`Agent: ${data.llm.used ? `${data.llm.provider} ${data.llm.mode||'tool loop'}` : 'deterministic fallback'} · Model: ${data.llm.model||'n/a'} · Spatial backend: ${data.llm.gis_backend || 'local GIS'}`));
    const params=(data.tool_trace||[]).filter(x=>x.parameters).map(x=>`${x.tool} ${JSON.stringify(x.parameters)}`).join(' | ');
    if(params) details.append(make('p','',`Parameters: ${params}`));
    const sources=(data.evidence||[]).map(x=>x.title||x.id).filter(Boolean).join(' · ');
    if(sources) details.append(make('p','',`Knowledge sources: ${sources}`));
    box.append(details); evidence.append(box);
  }
  function reliability(data) {
    const rel=data.reliability; if(!rel) return;
    const box=addEvidence('MODEL CONTEXT · A7‑T','ผลลัพธ์นี้มาจากการทำนายของแบบจำลอง A7-T · ค่าประเมินอ้างอิงจาก Fixed VAL4 · พื้นที่ที่แสดงไม่ได้ผ่าน independent Ground Truth validation');
    const m=rel.class_metric_context;
    if(m) box.append(make('p','',m.validation_iou==null ? `${m.class_id}: ไม่มี support ใน Fixed VAL4` : `${m.class_id} validation reference — IoU ${Number(m.validation_iou).toFixed(3)} · F1 ${Number(m.validation_f1).toFixed(3)} (class-level validation metric, NOT polygon-level confidence)`));
  }
  function selectFeature(feature, layer, card, revealPanel=true) {
    if(selectedLayer && selectedLayer!==layer && selectedLayer.setStyle) selectedLayer.setStyle(resultStyle(selectedLayer.feature));
    selectedLayer=layer;
    if(layer?.setStyle) { layer.setStyle(selectedStyle(feature)); layer.bringToFront(); }
    document.querySelectorAll('.product-result-card.is-selected').forEach(n=>n.classList.remove('is-selected'));
    document.querySelectorAll('.result-number.is-selected').forEach(n=>n.classList.remove('is-selected'));
    document.querySelector(`.result-number[data-feature-id="${feature.properties?.feature_id??feature.id}"]`)?.classList.add('is-selected');
    highlightDistanceForFeature(featureId(feature));
    if(card) { card.classList.add('is-selected'); if(revealPanel) card.scrollIntoView({behavior:reduced()?'auto':'smooth',block:'nearest'}); }
    const p=feature.properties||{}, id=p.feature_id??feature.id;
    const existing=byId('productFeatureDetail'); if(existing) existing.remove();
    const box=make('section','product-evidence-block'); box.id='productFeatureDetail';
    box.append(make('span','feature-id',`FEATURE ${id} · A7‑T PREDICTION`));
    box.append(make('h3','feature-class-title',`${p.class_id} ${window.GeoAIClasses.name(p.class_id)}`));
    box.append(make('p','feature-thai-name',window.GeoAIClasses.thai(p.class_id)));
    const metrics=make('div','feature-metrics');
    const entries=[['Area',`${Number(p.area_rai||0).toLocaleString('th-TH',{maximumFractionDigits:2})} ไร่`]];
    if(p.nearest_distance_m!=null) entries.push(['ระยะถึงพื้นที่อ้างอิง',distanceDescription(p)]);
    if(p.ndvi_mean!=null) entries.push(['NDVI mean',Number(p.ndvi_mean).toFixed(2)]);
    if(p.ndwi_mean!=null) entries.push(['NDWI mean',Number(p.ndwi_mean).toFixed(2)]);
    entries.push(['Model',p.source_model||'A7-T']);
    entries.forEach(([label,value])=>{const metric=make('div','feature-metric');metric.append(make('span','',label),make('strong','',value));metrics.append(metric)});
    box.append(metrics,make('p','feature-source-note','ผลจาก model prediction · ไม่ใช่ polygon-level confidence'));
    evidence.prepend(box);
    if(layer?.getBounds && typeof map!=='undefined' && map) {
      if(selectedPopup)map.closePopup(selectedPopup);
      const popupNode=make('div','selected-result-popup');
      popupNode.append(make('span','selected-result-index',`ผลลัพธ์ ${Math.max(1,resultFeatures.findIndex(item=>featureId(item)===featureId(feature))+1)}`));
      popupNode.append(make('strong','',`${p.class_id} ${window.GeoAIClasses.name(p.class_id)}`));
      popupNode.append(make('span','',window.GeoAIClasses.thai(p.class_id)));
      popupNode.append(make('b','',areaText(feature)));
      if(p.nearest_distance_m!=null) popupNode.append(make('span','selected-result-distance',`↔ ${distanceDescription(p)}`));
      selectedPopup=L.popup({className:'selected-result-leaflet-popup',closeButton:true,autoPan:false,offset:[0,-13]})
        .setLatLng(layer.getBounds().getCenter()).setContent(popupNode).openOn(map);
    }
    if(layer?.getBounds && typeof map!=='undefined' && map) {
      const mobile=map.getSize().x<760;
      const right=mobile?18:(revealPanel?Math.min(410,Math.round(panel.getBoundingClientRect().width||0)+34):70);
      const distanceBounds=distanceVisuals.get(featureId(feature))?.line?.getBounds?.();
      if(distanceBounds?.isValid?.()) map.flyTo(distanceBounds.getCenter(),mobile?15:16,{duration:reduced()?0:.7});
      else map.flyToBounds(layer.getBounds(),{paddingTopLeft:[mobile?18:70,mobile?155:145],paddingBottomRight:[right,mobile?105:85],maxZoom:16,duration:reduced()?0:.7});
    }
    if(revealPanel) show();
  }
  const featureId=feature=>String(feature.properties?.feature_id??feature.id);
  const areaText=feature=>`${Number(feature.properties?.area_rai||0).toLocaleString('th-TH',{minimumFractionDigits:2,maximumFractionDigits:2})} ไร่`;
  const formatDistance=value=>Number(value)<.5?'0 เมตร (ขอบพื้นที่ติดกัน)':`${Number(value).toLocaleString('th-TH',{maximumFractionDigits:0})} เมตร`;
  const compactDistance=value=>Number(value)<.5?'0 ม. · ติดกัน':`${Number(value).toLocaleString('th-TH',{maximumFractionDigits:0})} ม.`;
  const referenceClassId=properties=>properties?.nearest_reference_class_id||currentDistanceContext?.target_class_id||'';
  const distanceDescription=properties=>{
    const classId=referenceClassId(properties),name=classId?window.GeoAIClasses.thai(classId):'พื้นที่อ้างอิง';
    return `${formatDistance(properties?.nearest_distance_m)} จาก ${classId?`${classId} `:''}${name}`;
  };
  function highlightDistanceForFeature(sourceId) {
    const selectedVisual=distanceVisuals.get(String(sourceId));
    const selectedReferenceId=String(selectedVisual?.referenceId??'');
    for(const [id,layer] of bufferLayers.entries()) {
      const selected=String(id)===selectedReferenceId;
      layer.setStyle?.({weight:selected?3:2,opacity:selected?1:.95,fillOpacity:selected?.42:.28});
      if(selected)layer.bringToFront?.();
    }
    for(const [id,visual] of distanceVisuals.entries()) {
      const selected=String(id)===String(sourceId);
      visual.halo?.setStyle({weight:selected?7:5,opacity:selected ? .52 : .26});
      visual.line?.setStyle({weight:selected?3.5:2,dashArray:selected?'11 6':'7 7',opacity:selected?1:.88});
      visual.marker?.setZIndexOffset(selected?800:0);
      visual.marker?.getElement()?.querySelector('.distance-line-label')?.classList.toggle('is-selected',selected);
    }
    for(const [id,layer] of referenceLayers.entries()) {
      const active=[...distanceVisuals.values()].some(item=>String(item.referenceId)===String(id)&&String(item.sourceId)===String(sourceId));
      layer.setStyle?.({color:active?'#e9fbff':'#62cfff',weight:active?5:3.5,opacity:1,fillOpacity:active?.94:.78});
      if(active){layer.bringToFront?.();layer.openTooltip?.()}else layer.closeTooltip?.();
    }
    selectedLayer?.bringToFront?.();
  }
  function labelLayout() {
    if(!polygonLayer||!map||!labelGroup||!leaderGroup)return;
    labelGroup.clearLayers();leaderGroup.clearLayers();
    for(const [index,feature] of resultFeatures.entries()){
      const layer=resultLayers.get(featureId(feature));if(!layer?.getBounds)continue;
      const anchor=layer.getBounds().getCenter();if(!map.getBounds().contains(anchor))continue;
      const id=featureId(feature),color=window.GeoAIClasses.color(feature.properties?.class_id);
      const node=make('button','result-number',String(index+1));node.type='button';node.dataset.featureId=id;node.style.setProperty('--result-color',color);node.setAttribute('aria-label',`ผลลัพธ์ ${index+1} ${feature.properties?.class_id||''} ${areaText(feature)}`);
      const icon=L.divIcon({className:'result-number-marker',html:node.outerHTML,iconSize:[30,30],iconAnchor:[15,15]});
      const marker=L.marker(anchor,{icon,pane:'searchResultLabels',keyboard:true});
      marker.on('click',e=>{L.DomEvent.stopPropagation(e.originalEvent);selectFeature(feature,layer,document.querySelector(`.product-result-card[data-feature-id="${id}"]`))});
      marker.addTo(labelGroup);
    }
  }
  function scheduleLabels(){if(relayoutTimer)clearTimeout(relayoutTimer);relayoutTimer=setTimeout(labelLayout,70)}
  function drawDistanceContext(context) {
    if(!context||!map||!window.L)return;
    const buffers=context.buffers?.features||[],references=context.references?.features||[],lines=context.lines?.features||[];
    if(!buffers.length&&!references.length&&!lines.length)return;
    currentDistanceContext=context;
    distanceBufferGroup=distanceBufferGroup||L.layerGroup();referenceGroup=referenceGroup||L.layerGroup();distanceLineGroup=distanceLineGroup||L.layerGroup();distanceLabelGroup=distanceLabelGroup||L.layerGroup();
    for(const group of [distanceBufferGroup,referenceGroup,distanceLineGroup,distanceLabelGroup]){
      if(searchGroup){if(!searchGroup.hasLayer(group))searchGroup.addLayer(group)}else if(!map.hasLayer(group))group.addTo(map);
    }
    const target=context.target_class_id||'';
    L.geoJSON({type:'FeatureCollection',features:buffers},{pane:'searchDistanceBuffer',interactive:false,style:{color:'#fff',weight:2,opacity:.95,dashArray:'6 5',fillColor:target?window.GeoAIClasses.color(target):'#fff',fillOpacity:.28,className:'distance-buffer-zone'},onEachFeature:(feature,layer)=>{
      const id=String(feature.properties?.reference_feature_id??feature.id);bufferLayers.set(id,layer);layer.on('add',()=>layer.getElement?.()?.classList.add('distance-buffer-zone'));
    }}).addTo(distanceBufferGroup);
    L.geoJSON({type:'FeatureCollection',features:references},{pane:'searchDistanceReference',style:{color:'#62cfff',weight:3.5,opacity:1,fillColor:target?window.GeoAIClasses.color(target):'#fff',fillOpacity:.78,className:'distance-reference-polygon'},onEachFeature:(feature,layer)=>{
      const id=String(feature.properties?.feature_id??feature.id);referenceLayers.set(id,layer);layer.on('add',()=>layer.getElement?.()?.classList.add('distance-reference-polygon'));
      layer.bindTooltip(`${feature.properties?.class_id||target} ${window.GeoAIClasses.thai(feature.properties?.class_id||target)} อ้างอิง`,{sticky:false,direction:'top',offset:[0,-16],opacity:1,className:'distance-reference-tooltip'});
    }}).addTo(referenceGroup);
    lines.forEach((feature,index)=>{
      const p=feature.properties||{},sourceId=String(p.source_feature_id),referenceId=String(p.reference_feature_id??'');
      const halo=L.geoJSON(feature,{pane:'searchDistanceLines',interactive:false,style:{color:'#071b14',weight:5,opacity:.26,lineCap:'round'}}).addTo(distanceLineGroup);
      const line=L.geoJSON(feature,{pane:'searchDistanceLines',style:{color:'#fff',weight:2,opacity:.88,dashArray:'7 7',lineCap:'round',className:'distance-connector-line'}}).addTo(distanceLineGroup);
      line.eachLayer(path=>path.getElement?.()?.classList.add('distance-connector-line'));
      line.on('click',()=>{const source=resultFeatures.find(item=>featureId(item)===sourceId),layer=resultLayers.get(sourceId);if(source&&layer)selectFeature(source,layer,document.querySelector(`.product-result-card[data-feature-id="${sourceId}"]`))});
      let marker=null;
      if(index<10&&line.getBounds?.().isValid()){
        const label=compactDistance(p.distance_m);
        const icon=L.divIcon({className:'distance-line-label-icon',html:`<span class="distance-line-label">${label}</span>`,iconSize:[82,24],iconAnchor:[41,12]});
        marker=L.marker(line.getBounds().getCenter(),{icon,pane:'searchResultLabels',interactive:false}).addTo(distanceLabelGroup);
      }
      distanceVisuals.set(sourceId,{sourceId,referenceId,halo,line,marker});
    });
    distanceKeyControl=L.control({position:'bottomleft'});
    distanceKeyControl.onAdd=()=>{
      const node=L.DomUtil.create('div','distance-map-key');
      if(references.length){const referenceRow=L.DomUtil.create('div','distance-map-key-row',node);const reference=L.DomUtil.create('i','distance-map-key-reference',referenceRow);reference.style.setProperty('--distance-reference-color',target?window.GeoAIClasses.color(target):'#fff');reference.setAttribute('aria-hidden','true');const referenceText=L.DomUtil.create('span','',referenceRow);referenceText.textContent=`polygon ${target} ${window.GeoAIClasses.thai(target)} อ้างอิง`;}
      if(buffers.length){const zoneRow=L.DomUtil.create('div','distance-map-key-row',node);const zone=L.DomUtil.create('i','distance-map-key-zone',zoneRow);zone.style.setProperty('--distance-zone-color',target?window.GeoAIClasses.color(target):'#fff');zone.setAttribute('aria-hidden','true');const zoneText=L.DomUtil.create('span','',zoneRow);zoneText.textContent=`เขตไม่เกิน ${Number(context.max_distance_m||0).toLocaleString('th-TH')} ม. รอบ ${target} ${window.GeoAIClasses.thai(target)}`;}
      const lineRow=L.DomUtil.create('div','distance-map-key-row',node);const line=L.DomUtil.create('i','distance-map-key-line',lineRow);line.setAttribute('aria-hidden','true');
      const text=L.DomUtil.create('span','',lineRow);text.textContent='เส้นระยะจริงจากขอบถึงขอบ';
      L.DomEvent.disableClickPropagation(node);return node;
    };
    distanceKeyControl.addTo(map);
  }
  function addResultFeatures(features) {
    if(!features.length||!map)return;
    const collection={type:'FeatureCollection',features};
    const layer=L.geoJSON(collection,{pane:'searchResultPolygons',style:feature=>resultStyle(feature),onEachFeature:(feature,part)=>{
      const id=featureId(feature);resultLayers.set(id,part);
      part.on('mouseover',()=>{if(part!==selectedLayer)part.setStyle(hoverStyle(feature));document.querySelector(`.product-result-card[data-feature-id="${id}"]`)?.classList.add('is-hovered');document.querySelector(`.result-number[data-feature-id="${id}"]`)?.classList.add('is-hovered')});
      part.on('mouseout',()=>{if(part!==selectedLayer)part.setStyle(resultStyle(feature));document.querySelector(`.product-result-card[data-feature-id="${id}"]`)?.classList.remove('is-hovered');document.querySelector(`.result-number[data-feature-id="${id}"]`)?.classList.remove('is-hovered')});
      part.on('click',event=>{L.DomEvent.stopPropagation(event.originalEvent);selectFeature(feature,part,document.querySelector(`.product-result-card[data-feature-id="${id}"]`))});
    }});
    layer.addTo(polygonLayer);resultFeatures.push(...features);scheduleLabels();
  }
  function drawPolygons(data) {
    const distanceContext=data.results?.distance_context||null;
    clearMap();
    currentDistanceContext=distanceContext;
    const features=data.results?.geojson?.features||[];const count=features.length;
    if(!count||!map||!window.L)return;
    if(preSearchMapMode===null)preSearchMapMode=window.getFullMapMode?.()||'rgb';
    if(preSearchBasemap===null)preSearchBasemap=window.getMapBasemap?.()||'imagery';
    window.setFullMapMode?.('rgb');window.setMapBasemap?.('imagery');
    for(const [name,z] of [['searchDistanceBuffer',418],['searchResultPolygons',430],['searchResultLeaders',435],['searchDistanceReference',440],['searchDistanceLines',450],['searchResultLabels',650]]){
      if(!map.getPane(name))map.createPane(name);map.getPane(name).style.zIndex=String(z);
    }
    if(searchGroup&&!map.hasLayer(searchGroup))searchGroup.addTo(map);
    polygonLayer=L.featureGroup().addTo(searchGroup||map);
    labelGroup=labelGroup||L.layerGroup();leaderGroup=leaderGroup||L.layerGroup();
    if(searchGroup){if(!searchGroup.hasLayer(labelGroup))searchGroup.addLayer(labelGroup);if(!searchGroup.hasLayer(leaderGroup))searchGroup.addLayer(leaderGroup)}
    else {labelGroup.addTo(map);leaderGroup.addTo(map)}
    addResultFeatures(features);
    drawDistanceContext(distanceContext);
    const compact=map.getSize().x<760;
    map.fitBounds(polygonLayer.getBounds(),{paddingTopLeft:compact?[18,150]:[70,150],paddingBottomRight:compact?[18,105]:[Math.min(410,(panel.offsetWidth||360)+34),95],maxZoom:15,animate:!reduced()});
    scheduleLabels();
    window.dispatchEvent(new CustomEvent('map-search-results',{detail:{active:count>0,count}}));
  }
  function highlightFeature(feature,card,revealPanel=true) {
    if(!feature||!window.L||typeof map==='undefined'||!map)return;
    const layer=resultLayers.get(featureId(feature));if(layer)selectFeature(feature,layer,card,revealPanel);
  }
  function appendResultCard(feature,index) {
    const p=feature.properties||{}, id=p.feature_id??feature.id;
    const card=make('button','product-result-card'); card.type='button'; card.dataset.featureId=String(id);
    const dot=make('i','class-dot'); dot.style.background=window.GeoAIClasses.color(p.class_id);
    const number=make('span','result-card-number',String(index+1));number.style.setProperty('--result-color',window.GeoAIClasses.color(p.class_id));
    const title=make('strong'); title.append(dot,document.createTextNode(`Feature ${id} · ${p.class_id} ${window.GeoAIClasses.name(p.class_id)}`));
    card.append(number,title,make('span','',`${Number(p.area_rai||0).toLocaleString('th-TH',{maximumFractionDigits:2})} ไร่${p.nearest_distance_m!=null?` · ${distanceDescription(p)}`:''}`));
    card.addEventListener('click',()=>highlightFeature(feature,card));
    cards.append(card);
  }
  function resultCards(data) {
    const features=data.results?.geojson?.features||[];
    const count=data.results?.count??features.length;
    const total=data.results?.total_matches;
    const spatial=data.intent?.spatial_intent||{};
    currentDistanceContext=data.results?.distance_context||null;
    const classOnly=Boolean(spatial.source_class_id&&!spatial.relation&&!spatial.area_min&&!spatial.area_max&&!window.selectedBbox);
    panel.dataset.totalMatches=total==null?'':String(total);
    panel.dataset.highlighted=String(count);
    panel.dataset.fullClassCoverage=classOnly?'true':'false';
    panel.dataset.resultClass=classOnly?spatial.source_class_id:'';
    setText(byId('productTitle'),total==null?`แสดง ${count.toLocaleString('th-TH')} พื้นที่`:`พบ ${Number(total).toLocaleString('th-TH')} พื้นที่`);
    if(spatial.relation==='near'&&currentDistanceContext) {
      const hasBuffer=Boolean(currentDistanceContext.buffers?.features?.length);
      cards.append(make('p','product-result-scope distance-result-scope',`polygon สี${hasBuffer?'ทึบ':'คลาส'}คือ ${currentDistanceContext.target_class_id} ${window.GeoAIClasses.thai(currentDistanceContext.target_class_id)} อ้างอิง${hasBuffer?' · พื้นที่สีโปร่งคือเขตระยะจริง':''} · เส้นประสีขาวคือระยะสั้นที่สุดจากขอบถึงขอบ · เกณฑ์ไม่เกิน ${Number(currentDistanceContext.max_distance_m).toLocaleString('th-TH')} เมตร`));
    } else if(classOnly&&total!=null) {
      cards.append(make('p','product-result-scope',`แผนที่แสดง ${spatial.source_class_id} ครบทุกตำแหน่งทั่ว Full AOI · รายการและป้ายแสดง ${count.toLocaleString('th-TH')} จาก ${Number(total).toLocaleString('th-TH')} polygon`));
    } else if(total!=null && total>count) {
      cards.append(make('p','product-result-scope',`แสดง polygon ผลค้นหา ${count.toLocaleString('th-TH')} พื้นที่จากทั้งหมด ${Number(total).toLocaleString('th-TH')} พื้นที่ · สีตรงตามคลาส A7‑T`));
    } else {
      cards.append(make('p','product-result-scope',`แสดงเฉพาะ polygon ${count.toLocaleString('th-TH')} พื้นที่ที่ตรงเงื่อนไข · สีตรงตามคลาส A7‑T`));
    }
    features.slice(0,20).forEach((feature,index)=>appendResultCard(feature,index));
    drawPolygons(data);
    if(classOnly){
      activeSearchClass=spatial.source_class_id;
      window.showClassFilteredClassification?.([activeSearchClass]);
      setTimeout(()=>window.fitFullAoi?.(),80);
    }
    if(total!=null && total>count && spatial.source_class_id && !spatial.relation && !spatial.area_min) {
      let shown=count;
      const more=make('button','product-load-more',`แสดงเพิ่มอีก 20 พื้นที่ (${shown.toLocaleString('th-TH')}/${Number(total).toLocaleString('th-TH')})`);
      more.type='button'; cards.append(more);
      const currentRequest=requestNumber;
      more.addEventListener('click',async()=>{
        more.disabled=true; setText(more,'กำลังโหลดพื้นที่เพิ่มเติม…');
        try {
          const response=await fetch('/api/spatial/search',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({class_id:spatial.source_class_id,bbox:window.selectedBbox||null,limit:20,offset:shown})});
          if(!response.ok) throw new Error(`HTTP ${response.status}`);
          const page=await response.json(); if(currentRequest!==requestNumber)return;
          const next=page.geojson?.features||[];
          more.remove(); next.forEach((feature,index)=>appendResultCard(feature,shown+index));addResultFeatures(next);shown+=next.length;
          panel.dataset.highlighted=String(shown);
          window.dispatchEvent(new CustomEvent('map-search-results',{detail:{active:true,count:shown}}));
          if(shown<total && next.length) {cards.append(more);setText(more,`แสดงเพิ่มอีก 20 พื้นที่ (${shown.toLocaleString('th-TH')}/${Number(total).toLocaleString('th-TH')})`);}
          const scope=cards.querySelector('.product-result-scope');
          if(scope)setText(scope,classOnly?`แผนที่แสดง ${spatial.source_class_id} ครบทุกตำแหน่งทั่ว Full AOI · โหลดข้อมูลรายละเอียด ${shown.toLocaleString('th-TH')} จาก ${Number(total).toLocaleString('th-TH')} polygon`:`แสดง polygon ผลค้นหา ${shown.toLocaleString('th-TH')} พื้นที่จากทั้งหมด ${Number(total).toLocaleString('th-TH')} พื้นที่`);
        } catch(e) {setText(more,`โหลดเพิ่มไม่สำเร็จ — ลองอีกครั้ง`);cards.append(more)}
        finally {more.disabled=false}
      });
    }
    // No automatic selection: the first map view keeps every returned polygon visible.
  }
  function withoutDistance(text) {
    return String(text||'').replace(/(?:\s*ไม่เกิน\s*\d+(?:\.\d+)?\s*(?:เมตร|m|กิโลเมตร|km))+/gi,' ').replace(/\s+/g,' ').trim();
  }
  function runOption(container, nextQuestion) {
    container.querySelectorAll('button,input').forEach(node=>node.disabled=true);
    submit(nextQuestion);
  }
  function options(data) {
    const opts=make('div','quick-options');
    if(data.fallback_type==='unsupported_class') {
      const b=make('button','','ค้นหา R2 แทน'); b.type='button'; b.addEventListener('click',()=>runOption(opts,'ค้นหาพื้นที่เกษตรกรรม')); opts.append(b);
    } else {
      const spatial=data.intent?.spatial_intent||{};
      const base=withoutDistance(lastQuestion);
      const missingTarget=spatial.relation==='near'&&!spatial.target_class_id;
      const missingDistance=spatial.relation==='near'&&!spatial.distance_m;
      if(missingTarget) {
        const prompt=make('p','quick-options-label','เลือกประเภทพื้นที่เป้าหมาย'); opts.append(prompt);
        const cleanBase=base.replace(/\s*ใกล้(?:กับ)?\s*$/,'').trim();
        queryClassIds.filter(id=>id!==spatial.source_class_id).forEach(id=>{
          const name=window.GeoAIClasses.thai(id);
          const b=make('button','',`${id} ${name}`); b.type='button';
          b.addEventListener('click',()=>runOption(opts,`${cleanBase} ใกล้${name}`)); opts.append(b);
        });
      } else if(missingDistance) {
        const prompt=make('p','quick-options-label','เลือกระยะสูงสุด'); opts.append(prompt);
        for(const [label,meters] of [['100 m',100],['300 m',300],['500 m',500],['1 km',1000]]) {
          const b=make('button','',label); b.type='button'; b.addEventListener('click',()=>runOption(opts,`${base} ไม่เกิน ${meters} เมตร`)); opts.append(b);
        }
        const custom=make('input'); custom.type='number'; custom.min='1'; custom.placeholder='ระยะกำหนดเอง (เมตร)'; custom.setAttribute('aria-label','ระยะทางกำหนดเองเป็นเมตร');
        custom.addEventListener('keydown',e=>{if(e.key==='Enter'&&Number(custom.value)>0)runOption(opts,`${base} ไม่เกิน ${Number(custom.value)} เมตร`)}); opts.append(custom);
      } else {
        const edit=make('button','','แก้ไขคำถาม'); edit.type='button'; edit.addEventListener('click',()=>{query.focus();hide()}); opts.append(edit);
      }
    }
    evidence.append(opts);
  }
  function render(data) {
    cards.replaceChildren(); evidence.replaceChildren();
    byId('productResults').hidden=false; panel.classList.add('has-query-results');
    setText(byId('productMode'),modeLabel[data.mode]||'Query');
    setText(byId('productSummary'),data.answer||'');
    if(data.status==='clarification_required') { show(); clearMap(); restoreMapMode(); setText(byId('productTitle'),data.fallback_type==='unsupported_class'?'ข้อจำกัดของประเภทข้อมูล':'ขอข้อมูลอีกเล็กน้อย'); options(data); return; }
    if(data.status==='no_result') { show(); clearMap(); restoreMapMode(); setText(byId('productTitle'),'ไม่พบพื้นที่ที่ตรงกับเงื่อนไข'); const opts=make('div','quick-options'); const retry=make('button','','ปรับระยะ'); retry.type='button'; retry.onclick=()=>{query.focus();hide()}; const clear=make('button','','ล้างตัวกรอง'); clear.type='button'; clear.onclick=()=>{query.value='';clearMap();restoreMapMode();hide()}; opts.append(retry,clear); evidence.append(opts); technical(data); return; }
    if(data.status!=='success') { show(); clearMap(); restoreMapMode(); setText(byId('productTitle'),'ยังประมวลผลไม่ได้'); technical(data); return; }
    if(data.mode==='knowledge') { show(); clearMap(); restoreMapMode(); setText(byId('productTitle'),'คำตอบจากฐานความรู้'); const docs=(data.evidence||[]); if(docs.length) addEvidence('Knowledge Evidence',docs.map(x=>x.title||x.id).join(' · ')); technical(data); return; }
    resultCards(data); reliability(data);
    if(data.mode==='mixed' && data.evidence?.length) addEvidence('Knowledge Evidence',data.evidence.map(x=>x.title||x.id).join(' · '));
    technical(data);
    document.body.classList.add('search-has-results');
    show();
  }
  async function submit(raw) {
    const text=String(raw??query.value).trim(); if(!text)return;
    query.value=text; lastQuestion=text;
    if(byId('scopeSelect')?.value!=='FULL_AOI') { error.hidden=false; error.textContent='Agent V2 ค้นหาใน Full AOI เท่านั้น กรุณาเลือก “พื้นที่ทั้งหมด” (TEST40 ใช้กับ semantic search แบบเดิม)'; return; }
    if(activeRequest)activeRequest.abort(); activeRequest=new AbortController(); const own=++requestNumber;
    error.hidden=true; byId('productAskBtn').disabled=true; document.body.classList.remove('search-has-results');
    const stages=['กำลังทำความเข้าใจคำถาม...','กำลังเลือกเครื่องมือเชิงพื้นที่...','กำลังค้นหาข้อมูล GIS...','กำลังเตรียมหลักฐาน...'];
    let stage=0; status(stages[0]); const tick=setInterval(()=>{stage=Math.min(stage+1,stages.length-1);status(stages[stage])},420);
    let keepSuccessNotice=false;
    try {
      await window.GeoAIClasses.ready;
      const providerControl=byId('llmProviderControl'),providerSelect=byId('llmProviderSelect');
      const payload={query:text,bbox:window.selectedBbox||null,geometry:window.selectedGeometry||null,limit:20,history:conversationHistory.slice(-6)};
      if(providerControl&&!providerControl.hidden&&providerSelect)payload.provider=providerSelect.value;
      const response=await fetch('/api/agent/query',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload),signal:activeRequest.signal});
      const data=await response.json(); if(!response.ok)throw new Error(data.detail?.message||'ระบบยังไม่พร้อมตอบคำถามนี้');
      if(own!==requestNumber)return;
      render(data);
      if(data.answer){conversationHistory.push({role:'user',content:text},{role:'assistant',content:String(data.answer)});conversationHistory=conversationHistory.slice(-6)}
      if(data.status==='success'&&data.mode!=='knowledge'&&data.results?.count){keepSuccessNotice=true;const full=panel.dataset.fullClassCoverage==='true';status(full?`แสดง ${panel.dataset.resultClass} ครบทุกตำแหน่งทั่ว Full AOI`:`แสดง polygon ผลค้นหา ${data.results.count} พื้นที่บนภาพดาวเทียม`);setTimeout(()=>{if(own===requestNumber)progress.hidden=true},3200)}
    } catch(e) {
      if(e.name==='AbortError')return;
      error.hidden=false;error.textContent=`ค้นหาไม่สำเร็จ: ${e.message||'โปรดลองอีกครั้ง'}`;
      console.error('GeoAI query failed',e);
    } finally { clearInterval(tick); if(own===requestNumber){if(!keepSuccessNotice)progress.hidden=true;byId('productAskBtn').disabled=false;} }
  }
  form.addEventListener('submit',e=>{e.preventDefault();submit()});
  query.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submit()}});
  document.querySelectorAll('[data-product-query]').forEach(b=>b.addEventListener('click',()=>submit(b.dataset.productQuery)));
  byId('closeResults')?.addEventListener('click',hide);
  window.clearProductSearch=()=>{if(activeRequest)activeRequest.abort();requestNumber++;conversationHistory=[];query.value='';cards.replaceChildren();evidence.replaceChildren();byId('productResults').hidden=true;error.hidden=true;progress.hidden=true;clearMap();restoreMapMode();hide();document.body.classList.remove('search-has-results');panel.classList.remove('has-query-results');delete panel.dataset.totalMatches;delete panel.dataset.highlighted;delete panel.dataset.fullClassCoverage;delete panel.dataset.resultClass};
  window.addEventListener('map-clear-search',()=>window.clearProductSearch());
  let identifyAttempts=0;
  const installMapIdentify=()=>{
    if(typeof map==='undefined'||!map){if(++identifyAttempts<30)setTimeout(installMapIdentify,250);return;}
    map.on('moveend zoomend resize',scheduleLabels);
    map.on('click',async event=>{
      if(polygonLayer||panel.dataset.totalMatches===undefined||drawBoxButton?.classList.contains('is-active'))return;
      if(identifyRequest)identifyRequest.abort();identifyRequest=new AbortController();
      try{
        const params=new URLSearchParams({lon:String(event.latlng.lng),lat:String(event.latlng.lat)});
        if(activeSearchClass)params.set('class_id',activeSearchClass);
        const response=await fetch(`/api/map/identify?${params}`,{signal:identifyRequest.signal});
        if(!response.ok)return;
        const data=await response.json();if(!data.feature)return;
        const id=data.feature.properties?.feature_id??data.feature.id;
        highlightFeature(data.feature,document.querySelector(`.product-result-card[data-feature-id="${id}"]`),false);
        show();
      }catch(error){if(error.name!=='AbortError')console.warn('Map identify unavailable',error)}
    });
  };
  installMapIdentify();
  panel.addEventListener('touchstart',e=>{touchStart=e.touches[0]?.clientY??null},{passive:true});
  panel.addEventListener('touchend',e=>{if(touchStart==null)return;const dy=(e.changedTouches[0]?.clientY??touchStart)-touchStart;if(dy>100)hide();else if(dy< -75)show();touchStart=null},{passive:true});
  window.addEventListener('tile-selected',show);
  window.addEventListener('keydown',e=>{if(e.key==='Escape')hide()});
  window.productQuery=submit;
})();
