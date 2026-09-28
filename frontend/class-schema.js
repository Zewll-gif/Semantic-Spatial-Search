/* A7-T class display contract. Values come only from the frozen project palette API. */
window.GeoAIClasses = (() => {
  let schema;
  const requireClass = code => {
    const value = schema?.classes?.[code];
    if (!value) throw new Error(`Unknown A7-T class: ${code}`);
    return value;
  };
  const install = payload => {
    if (payload.model !== 'A7_RGBN_REVISED7_TVERSKY' || payload.schema !== 'A7_REVISED7_V1') {
      throw new Error('A7-T class schema mismatch');
    }
    for (let n = 1; n <= 7; n++) {
      const code = `R${n}`;
      if (!/^#[0-9A-Fa-f]{6}$/.test(payload.classes?.[code]?.color || '')) throw new Error(`Missing canonical color ${code}`);
      document.documentElement.style.setProperty(`--r${n}`, payload.classes[code].color);
    }
    schema = payload;
    const renderLegend = (selector, heading) => {
      const host = document.querySelector(selector);
      if (!host) return;
      host.replaceChildren();
      if (heading) { const title = document.createElement('span'); title.className='legend-heading'; title.textContent=heading; host.append(title); }
      for (let n=1; n<=7; n++) {
        const code=`R${n}`, item=document.createElement('span'), swatch=document.createElement('i');
        swatch.className=`swatch c${n}`; swatch.setAttribute('aria-hidden','true');
        item.append(swatch, document.createTextNode(`${code} ${payload.classes[code].name_en}`));
        host.append(item);
      }
    };
    renderLegend('#legendBody');
    renderLegend('.atlas-legend', 'สีคลาสผลทำนาย A7-T');
    const select=document.getElementById('analysisClass');
    if (select) {
      const previous=select.value;
      select.replaceChildren();
      for (let n=1; n<=7; n++) {
        const code=`R${n}`, option=document.createElement('option');
        option.value=String(n); option.textContent=`${code} ${payload.classes[code].name_en}`; select.append(option);
      }
      select.value=previous;
    }
    const version=`${payload.prediction_sha256.slice(0,12)}-${payload.palette_sha256.slice(0,12)}`;
    document.querySelectorAll('.compare-prediction').forEach(img => {
      img.src = `${img.getAttribute('src').split('?')[0]}?v=${version}`;
    });
  };
  const ready = fetch(window.GeoAIApp.url('api/class-schema'), {cache:'no-store'})
    .then(response => { if (!response.ok) throw new Error(`Class schema HTTP ${response.status}`); return response.json(); })
    .then(install);
  return {
    ready,
    color: code => requireClass(code).color,
    name: code => requireClass(code).name_en,
    thai: code => requireClass(code).name_th,
    version: () => `${schema.prediction_sha256.slice(0,12)}-${schema.palette_sha256.slice(0,12)}`,
  };
})();
