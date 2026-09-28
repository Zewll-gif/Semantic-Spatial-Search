/*
CLEAN PROJECT HEADER
ไฟล์: hero-reveal.js
หน้าที่: ส่วนแสดงผลและ interaction ของ GeoAI Explorer
Input: ข้อมูลจาก API และ static assets
Output: หน้าเว็บหรือพฤติกรรม UI
Dependency สำคัญ: backend API และ class schema
สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
*/
(() => {
  const hero = document.querySelector('.experience-hero');
  const semantic = document.querySelector('.hero-semantic');
  if (!hero || !semantic) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let current = {x: .7, y: .5};
  let target = {...current};
  let frame = 0;
  let dragging = false;
  const paint = () => {
    current.x += (target.x - current.x) * (reduced.matches ? 1 : .15);
    current.y += (target.y - current.y) * (reduced.matches ? 1 : .15);
    semantic.style.setProperty('--reveal-x', `${(current.x * 100).toFixed(2)}%`);
    semantic.style.setProperty('--reveal-y', `${(current.y * 100).toFixed(2)}%`);
    if (Math.abs(target.x-current.x) + Math.abs(target.y-current.y) > .001) frame = requestAnimationFrame(paint);
    else frame = 0;
  };
  const move = event => {
    const rect = hero.getBoundingClientRect();
    target = {x: Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),y: Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))};
    hero.classList.add('is-revealing');
    if (!frame) frame = requestAnimationFrame(paint);
  };
  hero.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch' && !dragging) return;
    move(event);
  }, {passive:true});
  hero.addEventListener('pointerdown', event => {
    if (event.pointerType === 'touch') dragging = true;
    move(event);
  }, {passive:true});
  hero.addEventListener('pointerup', () => {dragging = false;}, {passive:true});
  hero.addEventListener('pointerleave', () => {
    if (!matchMedia('(pointer:coarse)').matches) hero.classList.remove('is-revealing');
    dragging = false;
  });
  if (matchMedia('(pointer:coarse)').matches) hero.classList.add('is-revealing');
})();
