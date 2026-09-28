import * as maplibregl from './vendor/maplibre/maplibre-gl.mjs?v=tour-mime-20260919';

const section = document.getElementById('guidedTour');
const mapNode = document.getElementById('tourMap');
const bridge = document.getElementById('tourBridge');
const title = document.getElementById('tourTitle');
const description = document.getElementById('tourDescription');
const classCode = document.getElementById('tourClass');
const hotspot = document.getElementById('tourHotspot');
const hotspotText = document.getElementById('tourHotspotText');
const progressBar = document.getElementById('tourProgress');
const cta = document.getElementById('tourCta');
const discover = document.getElementById('discover');
const explorer = document.getElementById('explore');
const hero = document.getElementById('storyTop');
const journeyScene = document.getElementById('journeyScene');

// Keep the narrative order explicit: introduction, terrain context,
// visual comparison, then the live explorer. This prevents the search map
// from interrupting the onboarding story before users see the data context.
if (discover && explorer) explorer.before(discover);

const AOI = { west: 98.89023907363709, south: 18.66529982248273, east: 99.12675969138141, north: 18.91771645786411 };
const overview = { center: [(AOI.west + AOI.east) / 2, (AOI.south + AOI.north) / 2], zoom: 12.15, pitch: 0, bearing: 0 };
// กล้องปลาย Hero คือกล้องต้น Tour เดียวกัน จึงไม่มีการรีเซ็ตตำแหน่งระหว่างส่วน
const entry = { center: [99.028, 18.835], zoom: 12.9, pitch: 30, bearing: -7 };
const classCopy = {
  R1: 'สังเกตกลุ่มอาคารและพื้นผิวทึบน้ำที่ต่อเนื่องในเขตเมือง',
  R2: 'สังเกตลวดลายแปลงเกษตรบนพื้นที่ราบ',
  R3: 'สังเกตไม้ยืนต้นสีเข้มบนแนวภูเขาด้านตะวันตกและความต่างระดับของสันเขา',
  R4: 'สังเกตแนวลำน้ำและแหล่งน้ำที่คดเคี้ยวผ่านพื้นที่ศึกษา',
  R5: 'สังเกตพื้นที่เปิดโล่งที่ปกคลุมด้วยหญ้าและพืชล้มลุก',
  R6: 'สังเกตพื้นดินเปิดเผยซึ่งต่างจากพืชพรรณโดยรอบ',
};
let map;
let mapReady = false;
let activeCode = '';
let activeIndex = -1;
let currentProgress = 0;
let locations = [];
let cameras = [];
let exemplarManifest;
let trigger;
let heroProgress = 0;
let cameraPose = { lon: overview.center[0], lat: overview.center[1], zoom: overview.zoom, pitch: overview.pitch, bearing: overview.bearing };
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
const mobile = window.matchMedia('(max-width: 640px)');

cta.addEventListener('click', event => {
  event.preventDefault();
  if (location.hash !== '#explore') location.hash = 'explore';
  explorer?.scrollIntoView({ block: 'start', behavior: reduced.matches ? 'instant' : 'smooth' });
});
hero?.querySelectorAll('a[href="#guidedTour"]').forEach(link => link.addEventListener('click', event => {
  if (!trigger) return;
  event.preventDefault();
  history.replaceState(null, '', '#guidedTour');
  window.scrollTo({ top: trigger.start + (trigger.end - trigger.start) * 0.075, behavior: reduced.matches ? 'instant' : 'smooth' });
}));

const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
const mix = (a, b, t) => a + (b - a) * t;
const smooth = t => t * t * (3 - 2 * t);

function between(a, b, t) {
  return { center: [mix(a.center[0], b.center[0], t), mix(a.center[1], b.center[1], t)], zoom: mix(a.zoom, b.zoom, t), pitch: mix(a.pitch, b.pitch, t), bearing: mix(a.bearing, b.bearing, t) };
}

function moveCamera(pose, immediate = false) {
  if (!mapReady) return;
  const target = { lon: pose.center[0], lat: pose.center[1], zoom: pose.zoom, pitch: pose.pitch, bearing: pose.bearing };
  if (immediate || reduced.matches) {
    window.gsap?.killTweensOf(cameraPose);
    cameraPose = target;
    map.jumpTo({ center: [cameraPose.lon, cameraPose.lat], zoom: cameraPose.zoom, pitch: cameraPose.pitch, bearing: cameraPose.bearing });
    return;
  }
  // Tween ค่ากล้องบน MapLibre ผืนเดียว แทนการ fade ภาพนิ่งข้ามหน้า
  window.gsap.to(cameraPose, { duration: 0.42, ease: 'power2.out', overwrite: true,
    ...target,
    onUpdate: () => map.jumpTo({ center: [cameraPose.lon, cameraPose.lat], zoom: cameraPose.zoom, pitch: cameraPose.pitch, bearing: cameraPose.bearing }),
  });
}

function renderHero(p) {
  heroProgress = clamp(p);
  hero.style.setProperty('--hero-content-opacity', (1 - smooth(clamp((heroProgress - 0.35) / 0.43))).toFixed(4));
  if (!trigger || window.scrollY <= trigger.start + 1) moveCamera(between(overview, entry, smooth(heroProgress)));
}

function classAt(index) {
  if (index <= 0 || index >= 7) return null;
  return locations[index - 1];
}

function showCopy(index) {
  if (index === activeIndex) return;
  activeIndex = index;
  const item = classAt(index);
  section.dataset.scene = item?.class_id || (index === 7 ? 'finish' : 'overview');
  classCode.textContent = item?.class_id || '';
  title.textContent = item ? window.GeoAIClasses.name(item.class_id) : index === 7 ? 'พร้อมสำรวจพื้นที่ด้วยคำถามของคุณ' : 'รู้จักภูมิทัศน์ก่อนเริ่มค้นหา';
  description.textContent = item ? `${window.GeoAIClasses.thai(item.class_id)} — ${classCopy[item.class_id]}` : index === 7 ? 'R7 ไม่ปรากฏในผล Full AOI ชุดนี้ จึงไม่สร้างตำแหน่งตัวอย่างที่ไม่มีจริง' : 'เลื่อนเพื่อสำรวจพื้นที่เมือง เกษตร ไม้ยืนต้น แหล่งน้ำ หญ้า และดินเปลือยจากภาพ PlanetScope บนภูมิประเทศจริง';
  cta.hidden = index !== 7;
  hotspotText.textContent = item ? window.GeoAIClasses.thai(item.class_id) : '';
  hotspot.style.display = item ? 'flex' : 'none';
}

function setHighlight(code, opacity) {
  if (!mapReady) return;
  if (code !== activeCode) {
    activeCode = code;
    for (const item of locations) if (item.class_id !== code) {
      map.setPaintProperty(`tour-mask-${item.class_id}`, 'raster-opacity', 0);
      if (item.class_id === 'R6') map.setPaintProperty('tour-halo-R6', 'raster-opacity', 0);
    }
  }
  if (code) map.setPaintProperty(`tour-mask-${code}`, 'raster-opacity', opacity);
  if (code === 'R6') map.setPaintProperty('tour-halo-R6', 'raster-opacity', opacity);
  // ลดความเด่นของ RGB เฉพาะช่วงชูคลาส โดยคงสีคลาสจาก palette เดิมทุกค่า
  map.setPaintProperty('tour-rgb', 'raster-brightness-max', 1 - opacity * 0.23);
  map.setPaintProperty('tour-rgb', 'raster-saturation', -opacity * 0.12);
}

function placeHotspot() {
  const item = classAt(activeIndex);
  if (!mapReady || !item || mobile.matches) return;
  const point = map.project(item.center_lonlat);
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return;
  hotspot.style.left = `${clamp(point.x, 20, mapNode.clientWidth - 170)}px`;
  hotspot.style.top = `${clamp(point.y, 60, mapNode.clientHeight - 72)}px`;
}

function render(p) {
  currentProgress = clamp(p);
  section.style.setProperty('--tour-reveal-opacity', smooth(clamp(currentProgress / 0.045)).toFixed(4));
  progressBar.style.transform = `scaleX(${currentProgress})`;
  const segment = currentProgress * (cameras.length - 1);
  const from = Math.min(cameras.length - 2, Math.floor(segment));
  const t = smooth(clamp(segment - from));
  const a = cameras[from], b = cameras[from + 1];
  const index = Math.min(7, Math.round(segment));
  showCopy(index);
  bridge.style.opacity = mapReady ? '0' : '1';
  const item = classAt(index);
  const emphasis = item ? smooth(clamp(1 - Math.abs(segment - index) / 0.75)) : 0;
  hotspot.style.opacity = String(emphasis);
  setHighlight(item?.class_id || '', emphasis);
  if (!mapReady) return;
  moveCamera(between(a, b, t));
  placeHotspot();
}

function createMap(maskManifest) {
  const sourceBounds = [AOI.west, AOI.south, AOI.east, AOI.north];
  map = new maplibregl.Map({
    container: mapNode,
    style: {
      version: 8,
      sources: {
        rgb: { type: 'raster', tiles: [window.GeoAIApp.url('terrain/tiles/rgb/{z}/{x}/{y}.png')], tileSize: 256, minzoom: 10, maxzoom: 15, bounds: sourceBounds },
        dem: { type: 'raster-dem', tiles: [window.GeoAIApp.url('terrain/tiles/dem/{z}/{x}/{y}.png')], tileSize: 256, minzoom: 10, maxzoom: 14, bounds: sourceBounds, encoding: 'terrarium' },
      },
      layers: [{ id: 'tour-rgb', type: 'raster', source: 'rgb', paint: { 'raster-fade-duration': 0 } }],
    },
    center: overview.center, zoom: overview.zoom, pitch: 0, bearing: 0,
    antialias: !mobile.matches,
    attributionControl: false,
    dragRotate: false, scrollZoom: false, dragPan: false, doubleClickZoom: false, keyboard: false, touchZoomRotate: false,
    maxPitch: 70,
  });
  map.on('load', () => {
    for (const item of locations) {
      const code = item.class_id;
      const exemplar = maskManifest.scenes[code];
      if (!exemplar || exemplar.color.toUpperCase() !== window.GeoAIClasses.color(code).toUpperCase()) throw new Error(`Tour mask palette mismatch: ${code}`);
      map.addSource(`tour-mask-${code}`, { type: 'image', url: window.GeoAIApp.url(`${exemplar.file}?v=${exemplar.sha256.slice(0, 12)}`), coordinates: exemplar.coordinates_maplibre });
      if (code === 'R6' && exemplar.halo_file) {
        map.addSource('tour-halo-R6', { type: 'image', url: window.GeoAIApp.url(`${exemplar.halo_file}?v=${exemplar.halo_sha256.slice(0, 12)}`), coordinates: exemplar.coordinates_maplibre });
        map.addLayer({ id: 'tour-halo-R6', type: 'raster', source: 'tour-halo-R6', paint: { 'raster-opacity': 0, 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } });
      }
      map.addLayer({ id: `tour-mask-${code}`, type: 'raster', source: `tour-mask-${code}`, paint: { 'raster-opacity': 0, 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } });
    }
    map.setTerrain({ source: 'dem', exaggeration: mobile.matches ? 1.1 : 1.25 });
    mapReady = true;
    document.body.classList.add('journey-ready');
    section.classList.add('tour-ready');
    map.resize();
    if (window.scrollY < (trigger?.start || hero.offsetHeight)) renderHero(heroProgress);
    else render(currentProgress);
  });
  map.on('move', placeHotspot);
  map.on('error', event => console.warn('Terrain tour map:', event.error?.message || event));
  window.__terrainTour = { map, get progress() { return currentProgress; }, get activeClass() { return activeCode; }, get camera() { return map.getCenter().toArray(); }, goToScene: index => { trigger?.scroll(trigger.start + (trigger.end - trigger.start) * index / 7); render(index / 7); } };
}

function setupScroll() {
  if (!window.gsap || !window.ScrollTrigger) throw new Error('GSAP ScrollTrigger is unavailable');
  window.gsap.registerPlugin(window.ScrollTrigger);
  const updateHeroFlight = () => {
    const progress = clamp(window.scrollY / Math.max(hero.offsetHeight - window.innerHeight * 0.12, 1));
    renderHero(progress);
  };
  window.addEventListener('scroll', updateHeroFlight, { passive: true });
  updateHeroFlight();
  trigger = window.ScrollTrigger.create({
    trigger: section, start: 'top top',
    end: () => `+=${Math.round(window.innerHeight * (reduced.matches ? 2.6 : mobile.matches ? 4.2 : 5.8))}`,
    pin: true, anticipatePin: 1, scrub: reduced.matches ? 0.12 : 0.7,
    invalidateOnRefresh: true,
    onUpdate: self => render(self.progress),
  });
  if (window.scrollY >= trigger.start) render(trigger.progress);
}

async function init() {
  try {
    await window.GeoAIClasses.ready;
    const [locationsResponse, manifestResponse] = await Promise.all([
      fetch(window.GeoAIApp.url('terrain/class_tour_locations.json')), fetch(window.GeoAIApp.url('terrain/exemplars/manifest.json')),
    ]);
    if (!locationsResponse.ok || !manifestResponse.ok) throw new Error('Tour source artifacts are unavailable');
    locations = await locationsResponse.json();
    exemplarManifest = await manifestResponse.json();
    if (locations.length !== 6 || Object.keys(exemplarManifest.scenes || {}).length !== 6) throw new Error('Tour source has incomplete R1–R6 locations');
    cameras = [entry, ...locations.map(item => ({
      center: item.center_lonlat,
      zoom: item.camera.zoom - (mobile.matches ? 0.45 : 0),
      pitch: reduced.matches ? Math.min(item.camera.pitch, 20) : mobile.matches ? Math.min(item.camera.pitch, 52) : item.camera.pitch,
      bearing: item.camera.bearing * (reduced.matches ? 0.2 : mobile.matches ? 0.45 : 1),
    })), { ...overview, pitch: reduced.matches ? 0 : 28, bearing: reduced.matches ? 0 : -5, zoom: 12.0 }];
    createMap(exemplarManifest);
    setupScroll();
  } catch (error) {
    console.error('Terrain tour fallback:', error);
    section.classList.add('tour-fallback');
    description.textContent = 'ไม่สามารถโหลดมุมมองสามมิติได้ในขณะนี้ แผนที่ค้นหาด้านล่างยังใช้งานได้';
    cta.hidden = false;
  }
}

init();
