/*
CLEAN PROJECT HEADER
ไฟล์: cinematic.js
หน้าที่: ส่วนแสดงผลและ interaction ของ GeoAI Explorer
Input: ข้อมูลจาก API และ static assets
Output: หน้าเว็บหรือพฤติกรรม UI
Dependency สำคัญ: backend API และ class schema
สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
*/
(() => {
  const ready = fn => document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', fn, {once:true})
    : fn();

  ready(() => {
    const workspace = document.getElementById('explore');
    const topbar = document.querySelector('.workspace-topbar');
    const scope = document.querySelector('.scope-strip');
    if (workspace && topbar && topbar.parentElement !== workspace) workspace.prepend(topbar);
    if (workspace && scope && scope.parentElement !== workspace) topbar.after(scope);

    const query = document.getElementById('productQuery');
    const toolbar = document.querySelector('.map-toolbar');
    const toolsToggle = document.createElement('button');
    toolsToggle.type = 'button';
    toolsToggle.className = 'cinematic-tools-toggle';
    toolsToggle.textContent = 'เครื่องมือ +';
    toolsToggle.setAttribute('aria-expanded','false');
    toolsToggle.addEventListener('click', () => {
      const open = toolbar?.classList.toggle('is-open');
      toolsToggle.setAttribute('aria-expanded',String(Boolean(open)));
      toolsToggle.textContent = open ? 'ปิดเครื่องมือ −' : 'เครื่องมือ +';
    });
    if (toolbar) toolbar.prepend(toolsToggle);
    window.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (!workspace) return;
        workspace.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
        setTimeout(() => query?.focus(), 420);
      }
    });

    const setLayerPanelBehavior = () => {
      const panel = document.querySelector('.map-view-panel');
      const head = panel?.querySelector('.map-view-head');
      if (!panel || !head || head.dataset.cinematicBound) return;
      head.dataset.cinematicBound = 'true';
      head.tabIndex = 0;
      head.setAttribute('role','button');
      head.setAttribute('aria-label','เปิดหรือปิดตัวเลือกชั้นข้อมูลและพื้นหลังแผนที่');
      const toggle = () => panel.classList.toggle('is-expanded');
      head.addEventListener('click', toggle);
      head.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
      document.addEventListener('click', e => { if (!panel.contains(e.target)) panel.classList.remove('is-expanded'); });
    };
    setLayerPanelBehavior();
    const panelObserver = new MutationObserver(setLayerPanelBehavior);
    panelObserver.observe(document.body, {childList:true, subtree:true});

    const rightPanel = document.querySelector('.right-panel');
    const resultTitle = document.getElementById('productTitle');
    const ribbon = document.createElement('button');
    ribbon.type = 'button';
    ribbon.className = 'cinematic-result-ribbon';
    ribbon.hidden = true;
    ribbon.innerHTML = '<b>0</b><span>ดูผลลัพธ์บนแผนที่</span><span aria-hidden="true">↗</span>';
    ribbon.addEventListener('click', () => {
      rightPanel?.classList.add('is-open');
      document.body.classList.add('results-open');
    });
    workspace?.append(ribbon);

    const syncRibbon = () => {
      const cards = document.querySelectorAll('.product-result-card').length;
      const total=Number(rightPanel?.dataset.totalMatches||0);
      const highlighted=Number(rightPanel?.dataset.highlighted||cards);
      const fullClassCoverage=rightPanel?.dataset.fullClassCoverage==='true';
      const resultClass=rightPanel?.dataset.resultClass||'';
      const hasResults = Boolean(rightPanel?.classList.contains('has-query-results'));
      ribbon.hidden = !hasResults;
      ribbon.querySelector('b').textContent = total?total.toLocaleString('th-TH'):String(cards || (hasResults ? '•' : '0'));
      ribbon.querySelector('span').textContent = cards ? (fullClassCoverage?`${resultClass} ครบทั่ว AOI · ${total.toLocaleString('th-TH')} polygon`:(total>highlighted?`แสดง ${highlighted.toLocaleString('th-TH')} จาก ${total.toLocaleString('th-TH')} พื้นที่ · ดูรายการ`:`${highlighted.toLocaleString('th-TH')} พื้นที่ · ดูรายการ`)) : (resultTitle?.textContent || 'ดูผลลัพธ์');
    };
    if (rightPanel) new MutationObserver(syncRibbon).observe(rightPanel, {subtree:true, childList:true, attributes:true, characterData:true});

    const reveal = new IntersectionObserver(entries => {
      entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('is-visible'); });
    }, {threshold:.12, rootMargin:'0px 0px -8%'});
    document.querySelectorAll('.data-passage .reveal-item').forEach(node => reveal.observe(node));

    const hero = document.querySelector('.experience-hero');
    const heroImage = document.querySelector('.hero-imagery');
    const heroSemantic = document.querySelector('.hero-semantic');
    let ticking = false;
    const parallax = () => {
      if (!hero || !heroImage || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      if (hero.getBoundingClientRect().bottom < 0) return;
      const y = Math.min(window.scrollY * .09, 70);
      heroImage.style.transform = `scale(1.035) translate3d(0,${y}px,0)`;
      if (heroSemantic) heroSemantic.style.transform = heroImage.style.transform;
    };
    window.addEventListener('scroll', () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => { parallax(); ticking = false; });
    }, {passive:true});

    if (location.hash) requestAnimationFrame(() => setTimeout(() => {
      document.querySelector(location.hash)?.scrollIntoView({block:'start'});
      if (location.hash === '#explore' && typeof map !== 'undefined' && map) setTimeout(() => map.invalidateSize(), 120);
    }, 80));
  });
})();
