/*
CLEAN PROJECT HEADER
ไฟล์: landscape-tour.js
หน้าที่: ส่วนแสดงผลและ interaction ของ GeoAI Explorer
Input: ข้อมูลจาก API และ static assets
Output: หน้าเว็บหรือพฤติกรรม UI
Dependency สำคัญ: backend API และ class schema
สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
*/
/* Guided Landscape Tour: camera positions are derived from real AOI bounds and
   full-AOI tile centroids; this RGB preview is not a DEM or Ground Truth. */
(() => {
  const tour = document.getElementById('guidedTour');
  const world = document.getElementById('tourWorld');
  if (!tour || !world) return;

  const bounds = {west:98.89023907363709, south:18.66529982248273,
    east:99.12675969138141, north:18.9176840206757};
  const points = {
    urban:{lon:98.98506289550053,lat:18.799718041102942},
    agriculture:{lon:98.9996392355989,lat:18.86912930210497},
    water:{lon:98.970481564701,lat:18.827480629504134},
    woody:{lon:98.91218049127173,lat:18.79969798287687}
  };
  const normalized = point => ({x:(point.lon-bounds.west)/(bounds.east-bounds.west),
    y:(bounds.north-point.lat)/(bounds.north-bounds.south)});
  const focus = [
    {x:.5,y:.5,zoom:1.02},
    {...normalized(points.urban),zoom:3.25},
    {...normalized(points.agriculture),zoom:3.3},
    {...normalized(points.water),zoom:3.45},
    {...normalized(points.woody),zoom:3.15},
    {x:.5,y:.5,zoom:1.02}
  ];
  const copy = [
    {label:'01 / OVERVIEW',title:'รู้จักภูมิทัศน์<br/><em>ก่อนเริ่มค้นหา</em>',description:'เริ่มจากภาพ PlanetScope ของพื้นที่ศึกษาทั้งหมด แล้วเลื่อนเพื่อสำรวจตัวอย่างเมือง เกษตร แหล่งน้ำ และไม้ยืนต้นในบริบทจริง',note:'ภาพ AOI จริง · ภาพประกอบ ไม่ใช่ Ground Truth'},
    {label:'02 / R1 · BUILT-UP',title:'ร่องรอยเมือง<br/><em>บนผืนดิน</em>',description:'R1 ครอบคลุมสิ่งปลูกสร้างและพื้นผิวแข็ง ตัวอย่างนี้อยู่ในบริเวณที่ผล A7‑T ระบุคลาส R1 เด่นชัด',note:'tile_r08_c06 · A7‑T R1 92.88% ของพิกเซลที่ใช้ได้'},
    {label:'03 / R2 · AGRICULTURE',title:'รูปแบบของ<br/><em>พื้นที่เกษตร</em>',description:'R2 รวม Agricultural Land / Cropland มองเห็นลวดลายแปลงที่แตกต่างจากเขตเมืองและไม้ยืนต้น',note:'tile_r03_c07 · A7‑T R2 60.32% ของพิกเซลที่ใช้ได้'},
    {label:'04 / R4 · WATER',title:'เส้นทางของน้ำ<br/><em>ในภูมิทัศน์</em>',description:'R4 คือแหล่งน้ำใน taxonomy ที่ใช้งาน จุดนี้มีน้ำร่วมกับพื้นที่เมืองและพืชพรรณ จึงเหมาะดูบริบทของพื้นที่ผสม',note:'tile_r06_c05 · A7‑T R4 20.14% ของพิกเซลที่ใช้ได้'},
    {label:'05 / R3 · WOODY COVER',title:'แนวไม้ยืนต้น<br/><em>และพื้นที่ป่า</em>',description:'R3 คือ Tree / Woody Cover พื้นที่ตัวอย่างทางตะวันตกมีผลจำแนกไม้ยืนต้นเด่นชัด',note:'tile_r08_c01 · A7‑T R3 98.62% ของพิกเซลที่ใช้ได้'},
    {label:'06 / ENTER THE EXPLORER',title:'จากการมองเห็น<br/><em>สู่การตั้งคำถาม</em>',description:'เมื่อรู้จักลักษณะพื้นที่แล้ว ลองค้นหาคลาส ความสัมพันธ์เชิงพื้นที่ และหลักฐานประกอบบนแผนที่จริง',note:'ผลจำแนก A7‑T เป็น model prediction · ไม่ใช่ Ground Truth'}
  ];
  const title = document.getElementById('tourTitle');
  const label = document.getElementById('tourStepLabel');
  const description = document.getElementById('tourDescription');
  const note = document.getElementById('tourTileNote');
  const progressBar = document.getElementById('tourProgress');
  const buttons = [...tour.querySelectorAll('[data-tour-step]')];
  const hotspots = [...tour.querySelectorAll('.tour-hotspot')];
  const detailImage = document.getElementById('tourDetailImage');
  const detailCaption = document.getElementById('tourDetailCaption');
  const tileIds = [null,'tile_r08_c06','tile_r03_c07','tile_r06_c05','tile_r08_c01',null];
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let current = -1, frame = 0;

  const clamp = value => Math.min(1,Math.max(0,value));
  const lerp = (a,b,t) => a+(b-a)*t;
  const ease = t => t*t*(3-2*t);
  function showStep(index) {
    if (index === current) return;
    current = index;
    tour.dataset.step = String(index);
    const content = copy[index];
    label.textContent = content.label;
    title.innerHTML = content.title;
    description.textContent = content.description;
    note.textContent = content.note;
    if (tileIds[index]) {
      detailImage.src = `/assets/${tileIds[index]}/rgb`;
      detailImage.alt = `PlanetScope RGB ของ ${tileIds[index]}`;
      detailCaption.textContent = tileIds[index];
    }
    buttons.forEach((button,i) => {
      if (i===index) button.setAttribute('aria-current','step');
      else button.removeAttribute('aria-current');
    });
    hotspots.forEach(hotspot => hotspot.classList.toggle('is-active',Number(hotspot.dataset.hotspot)===index));
  }
  function update() {
    frame = 0;
    const rect = tour.getBoundingClientRect();
    const viewportH = window.innerHeight;
    const travel = Math.max(1,rect.height-viewportH);
    const progress = clamp(-rect.top/travel);
    const stage = progress*5;
    const from = Math.min(4,Math.floor(stage));
    const to = from+1;
    const transition = ease(clamp(stage-from));
    const selected = Math.min(5,Math.round(stage));
    showStep(selected);
    progressBar.style.width = `${progress*100}%`;

    const first=focus[from], second=focus[to];
    const x=lerp(first.x,second.x,transition);
    const y=lerp(first.y,second.y,transition);
    const detailScale=lerp(first.zoom,second.zoom,transition);
    const imageW=world.offsetWidth, imageH=world.offsetHeight;
    const fit=Math.max(window.innerWidth/imageW,viewportH/imageH);
    const scale=fit*detailScale;
    const targetX=selected===0||selected===5 ? .5 : (window.innerWidth<640 ? .58 : .65);
    const targetY=window.innerWidth<640 ? .40 : .5;
    const tx=window.innerWidth*targetX - x*imageW*scale;
    const ty=viewportH*targetY - y*imageH*scale;
    world.style.transform=`translate3d(${tx.toFixed(1)}px,${ty.toFixed(1)}px,0) scale(${scale.toFixed(4)})`;
    hotspots.forEach(hotspot => {
      const point=[null,points.urban,points.agriculture,points.water,points.woody][Number(hotspot.dataset.hotspot)];
      const position=normalized(point);
      hotspot.style.left=`${(tx+position.x*imageW*scale).toFixed(1)}px`;
      hotspot.style.top=`${(ty+position.y*imageH*scale).toFixed(1)}px`;
    });
  }
  const requestUpdate=()=>{if(!frame) frame=requestAnimationFrame(update)};
  buttons.forEach(button=>button.addEventListener('click',()=>{
    const index=Number(button.dataset.tourStep);
    const top=window.scrollY+tour.getBoundingClientRect().top;
    const travel=Math.max(1,tour.offsetHeight-window.innerHeight);
    window.scrollTo({top:top+travel*(index/5),behavior:reduceMotion.matches?'instant':'smooth'});
  }));
  window.addEventListener('scroll',requestUpdate,{passive:true});
  window.addEventListener('resize',requestUpdate);
  reduceMotion.addEventListener?.('change',requestUpdate);
  requestUpdate();
})();
