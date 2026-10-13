(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const message = $('#message');

  const NAV = ['Dashboard', 'Products', 'Content', 'Images', 'Pinterest', 'Review Center', 'Analytics'];
  const CATEGORIES = [
    'Business & Investment',
    'Dating, Relationships & Romance',
    'Education',
    'Health & Fitness',
    'Family & Children',
    'Hobby & Craft',
    'All Categories'
  ];

  function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function setMessage(text) {
    if (message) message.textContent = text;
  }

  async function api(url, options = {}) {
    const r = await fetch(url, options);
    let data = {};
    try { data = await r.json(); } catch (_) {}
    if (!r.ok || data.ok === false) throw new Error(data.error || `Request failed (${r.status})`);
    return data;
  }

  function modal(title, body, footer = '') {
    document.querySelector('#dfModal')?.remove();
    const el = document.createElement('div');
    el.id = 'dfModal';
    el.innerHTML = `
      <div class="df-backdrop"></div>
      <section class="df-modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <header><div><div class="eyebrow">DIGIFLOW WORKSPACE</div><h2>${esc(title)}</h2></div><button class="df-close" aria-label="Close">×</button></header>
        <div class="df-body">${body}</div>
        ${footer ? `<footer>${footer}</footer>` : ''}
      </section>`;
    document.body.appendChild(el);
    el.querySelector('.df-close').onclick = () => el.remove();
    el.querySelector('.df-backdrop').onclick = () => el.remove();
    return el;
  }

  function injectModalStyles() {
    if ($('#dfModalStyles')) return;
    const style = document.createElement('style');
    style.id = 'dfModalStyles';
    style.textContent = `
      #dfModal{position:fixed;inset:0;z-index:9999;display:grid;place-items:center}
      #dfModal .df-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.68);backdrop-filter:blur(7px)}
      #dfModal .df-modal{position:relative;width:min(900px,calc(100vw - 40px));max-height:82vh;display:flex;flex-direction:column;background:linear-gradient(145deg,rgba(17,23,34,.98),rgba(8,12,20,.98));border:1px solid #1d3342;border-radius:16px;box-shadow:0 25px 90px rgba(0,0,0,.55)}
      #dfModal header,#dfModal footer{padding:16px 18px;border-bottom:1px solid #1d2635;display:flex;justify-content:space-between;align-items:center}
      #dfModal footer{border-top:1px solid #1d2635;border-bottom:0;justify-content:flex-end;gap:8px}
      #dfModal header h2{margin:5px 0 0;font-size:18px}
      #dfModal .df-body{padding:16px;overflow:auto}
      #dfModal .df-close{width:34px;height:34px;border:1px solid #26364b;border-radius:9px;background:#101722;color:#fff;font-size:22px;cursor:pointer}
      #dfModal .df-row{display:grid;grid-template-columns:1fr auto;gap:14px;padding:13px;border:1px solid #1b2635;border-radius:11px;background:#0b1018;margin-bottom:9px}
      #dfModal .df-row b{display:block;font-size:12px;margin-bottom:5px}
      #dfModal .df-row small{color:#7f8da3;word-break:break-word}
      #dfModal .df-actions{display:flex;gap:7px;align-items:center}
      #dfModal button.df-action{border:1px solid #245266;background:#0b2028;color:#6deaff;border-radius:8px;padding:8px 10px;font-size:10px;font-weight:700;cursor:pointer}
      #dfModal button.df-action.warn{border-color:#684b27;color:#ffd58a;background:#21180b}
      #dfModal button.df-action.good{border-color:#20533f;color:#82fbc7;background:#0c2019}
      #dfModal .df-empty{padding:35px;text-align:center;color:#7f8da3;border:1px dashed #27364b;border-radius:11px}
      #dfModal .df-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
      #dfModal .df-card{padding:14px;border:1px solid #1b2635;border-radius:11px;background:#0b1018}
      #dfModal .df-card strong{display:block;font-size:22px;margin-top:6px}
      @media(max-width:700px){#dfModal .df-grid{grid-template-columns:1fr 1fr}#dfModal .df-row{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  async function refreshStatus() {
    try {
      const data = await api('/api/status');
      const s = data.storage;
      const stat = $$('.stat');
      if (stat[0]) { $('strong', stat[0]).textContent = s.products; $('small', stat[0]).textContent = '60 target'; }
      if (stat[1]) { $('strong', stat[1]).textContent = s.verified; $('small', stat[1]).textContent = 'verified / approved'; }
      if (stat[2]) { $('strong', stat[2]).textContent = s.images; $('small', stat[2]).textContent = 'Adobe stage'; }
      if (stat[3]) { $('strong', stat[3]).textContent = s.review; $('small', stat[3]).textContent = 'approved'; }
      const run = $('.bottom.active span'); if (run) run.textContent = s.running_tasks;
      const bottoms = $$('.bottom'); if (bottoms[1]) $('span', bottoms[1])?.replaceChildren(document.createTextNode(String(s.completed_tasks)));
      setMessage(data.browser.browser ? 'Persistent browser is running. Site tabs can be reused.' : 'Persistent browser is ready; open a service to launch it.');
      return data;
    } catch (e) {
      setMessage('Backend connection error: ' + e.message);
    }
  }

  async function openSite(site) {
    try {
      setMessage('Opening ' + site + '…');
      const data = await api('/api/open/' + encodeURIComponent(site), {method:'POST'});
      setMessage(site.toUpperCase() + ' opened in the persistent browser. Login manually the first time.');
      await refreshStatus();
      return data;
    } catch (e) {
      setMessage('Could not open ' + site + ': ' + e.message);
    }
  }

  async function showProducts(category = 'All Categories') {
    try {
      const data = await api('/api/products?category=' + encodeURIComponent(category));
      const rows = data.products.map(p => `
        <div class="df-row">
          <div><b>${esc(p.name)}</b><small>${esc(p.category)} · ${esc(p.amount)}${p.currency ? ' ' + esc(p.currency) : ''}<br>${esc(p.url)}</small></div>
          <div class="df-actions"><button class="df-action" data-open-url="${esc(p.url)}">Open URL</button><span class="statusPill">${esc(p.status)}</span></div>
        </div>`).join('');
      const el = modal('Products — ' + category, rows || '<div class="df-empty">No products are stored yet.</div>', `<button class="df-action" id="dfQueue">Queue ${category === 'All Categories' ? '60' : '10'} products</button>`);
      $$('[data-open-url]', el).forEach(b => b.onclick = () => window.open(b.dataset.openUrl, '_blank', 'noopener'));
      $('#dfQueue', el).onclick = async () => {
        try {
          await api('/api/runs', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category, target_count: category === 'All Categories' ? 60 : 10})});
          setMessage('Collection run queued. The run is stored and can be resumed by the task engine.');
          el.remove(); await refreshStatus();
        } catch(e) { setMessage(e.message); }
      };
    } catch (e) { setMessage(e.message); }
  }

  async function showReview() {
    try {
      const data = await api('/api/review');
      const rows = data.products.map(p => `
        <div class="df-row"><div><b>${esc(p.name)}</b><small>${esc(p.category)} · ${esc(p.amount)}<br>${esc(p.url)}</small></div>
        <div class="df-actions"><button class="df-action good" data-approve="${p.id}">Approve</button><button class="df-action warn" data-reject="${p.id}">Reject</button></div></div>`).join('');
      const el = modal('Review Center', rows || '<div class="df-empty">Nothing is waiting for review.</div>');
      $$('[data-approve]', el).forEach(b => b.onclick = async () => { await api('/api/review/'+b.dataset.approve+'/approve',{method:'POST'}); el.remove(); showReview(); refreshStatus(); });
      $$('[data-reject]', el).forEach(b => b.onclick = async () => { await api('/api/review/'+b.dataset.reject+'/reject',{method:'POST'}); el.remove(); showReview(); refreshStatus(); });
    } catch(e) { setMessage(e.message); }
  }

  async function showTasks(completedOnly = false) {
    try {
      const data = await api('/api/tasks');
      const list = data.tasks.filter(t => completedOnly ? t.status === 'completed' : t.status !== 'completed');
      const rows = list.map(t => `<div class="df-row"><div><b>${esc(t.kind)}</b><small>Task #${t.id} · ${esc(t.created_at)}</small></div><span class="statusPill">${esc(t.status)} · ${t.progress}%</span></div>`).join('');
      modal(completedOnly ? 'Completed Tasks' : 'Running / Queued Tasks', rows || '<div class="df-empty">No tasks in this list.</div>');
    } catch(e) { setMessage(e.message); }
  }

  async function showAnalytics() {
    try {
      const data = await api('/api/status');
      const s = data.storage;
      modal('Analytics', `<div class="df-grid">
        <div class="df-card">Products<strong>${s.products}</strong></div>
        <div class="df-card">Verified<strong>${s.verified}</strong></div>
        <div class="df-card">Images<strong>${s.images}</strong></div>
        <div class="df-card">Approved<strong>${s.review}</strong></div>
        <div class="df-card">Running<strong>${s.running_tasks}</strong></div>
        <div class="df-card">Completed<strong>${s.completed_tasks}</strong></div>
      </div>`);
    } catch(e) { setMessage(e.message); }
  }

  function bind() {
    injectModalStyles();
    const navs = $$('.nav');
    navs.forEach((b, i) => b.onclick = () => {
      navs.forEach(x => x.classList.remove('active')); b.classList.add('active');
      if (i === 0) document.querySelector('#dfModal')?.remove();
      else if (i === 1) showProducts();
      else if (i === 2) showProducts();
      else if (i === 3) showProducts();
      else if (i === 4) openSite('pinterest');
      else if (i === 5) showReview();
      else if (i === 6) showAnalytics();
    });

    $$('.cat').forEach((b, i) => b.onclick = () => {
      $$('.cat').forEach(x => x.classList.remove('active')); b.classList.add('active');
      showProducts(CATEGORIES[i]);
    });

    const bottoms = $$('.bottom');
    if (bottoms[0]) bottoms[0].onclick = () => showTasks(false);
    if (bottoms[1]) bottoms[1].onclick = () => showTasks(true);
    if (bottoms[2]) bottoms[2].onclick = () => openSite('pinterest');
    if (bottoms[3]) bottoms[3].onclick = () => showReview();
  }

  window.openSite = openSite;
  window.refreshStatus = refreshStatus;
  bind();
  refreshStatus();
  setInterval(refreshStatus, 5000);
})();
