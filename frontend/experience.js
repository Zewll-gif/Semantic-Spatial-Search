/*
CLEAN PROJECT HEADER
ไฟล์: experience.js
หน้าที่: ส่วนแสดงผลและ interaction ของ GeoAI Explorer
Input: ข้อมูลจาก API และ static assets
Output: หน้าเว็บหรือพฤติกรรม UI
Dependency สำคัญ: backend API และ class schema
สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
*/
/* Presentation-only interactions; never changes GIS, model, or API responses. */
(() => {
  const comparisons=[...document.querySelectorAll('.tile-card .compare-stage')];
  const workspace=document.getElementById('explore');
  const heroImagery=document.querySelector('.hero-imagery');
  const heroSemantic=document.querySelector('.hero-semantic');
  if(!workspace)return;

  comparisons.forEach(stage=>{
    const range=stage.querySelector('.compare-range');
    if(!range)return;
    const updateCompare=()=>stage.style.setProperty('--split',`${range.value}%`);
    range.addEventListener('input',updateCompare,{passive:true});
    updateCompare();
  });

  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const atlas=document.querySelector('.tile-atlas');
  document.querySelectorAll('[data-atlas-direction]').forEach(button=>button.addEventListener('click',()=>{
    if(!atlas)return;
    const card=atlas.querySelector('.tile-card');
    if(!card)return;
    atlas.scrollBy({left:Number(button.dataset.atlasDirection)*(card.getBoundingClientRect().width+11),behavior:reduced?'auto':'smooth'});
  }));
  if(reduced){document.querySelectorAll('.reveal-item').forEach(el=>el.classList.add('is-visible'))}
  else {
    const reveal=new IntersectionObserver(entries=>{
      entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('is-visible');reveal.unobserve(entry.target)}});
    },{threshold:.12,rootMargin:'0px 0px -30px 0px'});
    document.querySelectorAll('.reveal-item').forEach(el=>reveal.observe(el));
  }

  let scheduled=false, wasActive=false;
  const updateSection=()=>{
    scheduled=false;
    const scrollable=document.documentElement.scrollHeight-window.innerHeight;
    document.documentElement.style.setProperty('--read-progress',`${scrollable>0?Math.min(window.scrollY/scrollable,1)*100:0}%`);
    if(!reduced&&heroImagery){
      const shift=Math.min(window.scrollY*.055,34);
      heroImagery.style.transform=`translate3d(0,${shift}px,0) scale(1.04)`;
      if(heroSemantic)heroSemantic.style.transform=heroImagery.style.transform;
    }
    const active=workspace.getBoundingClientRect().top < window.innerHeight*.55;
    document.body.classList.toggle('explore-active',active);
    if(active&&!wasActive&&typeof map!=='undefined'&&map){
      window.setTimeout(()=>{
        map.invalidateSize({pan:false});
        if(typeof fitFullAoi==='function')fitFullAoi();
      },80);
    }
    wasActive=active;
  };
  const onScroll=()=>{if(!scheduled){scheduled=true;requestAnimationFrame(updateSection)}};
  window.addEventListener('scroll',onScroll,{passive:true});
  window.addEventListener('resize',onScroll,{passive:true});
  const alignHash=()=>{
    const target=location.hash&&document.querySelector(location.hash);
    if(target)window.setTimeout(()=>target.scrollIntoView({block:'start',behavior:'auto'}),120);
  };
  window.addEventListener('hashchange',()=>{onScroll();alignHash()});
  window.addEventListener('load',alignHash,{once:true});
  updateSection();
})();
