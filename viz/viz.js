/* hyenovel viz — 互動邏輯。資料由 viz.py 注入(window.HYENOVEL_DATA / HYENOVEL_SRC)。 */
const D = window.HYENOVEL_DATA;
const SRC = window.HYENOVEL_SRC;
const FB = D.feedback;
document.getElementById('ttl').textContent = D.title + ' · ' + D.slug;
const byId = {}; D.nodes.forEach(n => byId[n.id] = n);
const esc = s => (s || '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

/* feedback 點:strengths + key_points 合一,建 node→points 索引 */
const POINTS = [];
if (FB) {
  (FB.strengths || []).forEach(p => POINTS.push({ ...p, kind: 'str' }));
  (FB.key_points || []).forEach(p => POINTS.push({ ...p, kind: 'key' }));
}
const ptsByNode = {};
POINTS.forEach((p, i) => (p.refs || []).forEach(r => (ptsByNode[r] = ptsByNode[r] || []).push(i)));
const hasFb = new Set(Object.keys(ptsByNode));

/* ---------- tabs ---------- */
const gotoTab = v => document.querySelector(`.tab[data-v=${v}]`).click();
document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.view').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('v-' + t.dataset.v).classList.add('active');
  if (t.dataset.v === 'axis') drawAxis();
  if (t.dataset.v === 'chain') cy.resize();
});

/* ---------- legend + diagnostics ---------- */
const leg = document.getElementById('legend');
for (const [k, c] of Object.entries(D.colors)) {
  const s = document.createElement('span');
  s.innerHTML = `<i class="dot" style="background:${c}"></i>${D.cn[k]}`;
  leg.appendChild(s);
}
const diagNames = {
  orphan: ['孤兒技法', '不服務任何效果/主題=可能是裝飾'],
  overloaded: ['過載主題', '被太多東西餵=可能用力過猛'],
  hollow: ['空心主題', '沒有技法餵它=意圖可能落空'],
};
const diagEl = document.getElementById('diag'); let anyDiag = false;
for (const [nid, cls] of Object.entries(D.diag)) {
  cls.forEach(c => {
    anyDiag = true;
    const d = document.createElement('div');
    d.innerHTML = `<span class="diag-tag ${c}">${diagNames[c][0]}</span>` +
      `<b>${esc(byId[nid] ? byId[nid].label : nid)}</b> — <span style="color:var(--dim)">${diagNames[c][1]}</span>`;
    diagEl.appendChild(d);
  });
}
if (!anyDiag) diagEl.innerHTML = '<span style="color:var(--dim)">意圖鏈無明顯孤兒/過載/空心。</span>';

/* ---------- 意圖鏈:分欄佈局 ---------- */
const CHAIN_TYPES = ['motif', 'technique', 'effect', 'theme'];
const COL = { motif: 0, technique: 1, effect: 2, theme: 3 };
const chainNodes = D.nodes.filter(n => CHAIN_TYPES.includes(n.type));
const chainIds = new Set(chainNodes.map(n => n.id));
const SPX = 300, SPY = 78;
const colCount = {}; chainNodes.forEach(n => colCount[n.type] = (colCount[n.type] || 0) + 1);
const colIdx = {};
const positioned = chainNodes.map(n => {
  const i = (colIdx[n.type] = (colIdx[n.type] || 0)); colIdx[n.type]++;
  const total = colCount[n.type];
  return {
    data: { id: n.id, label: n.label + (hasFb.has(n.id) ? '  💬' : ''), ntype: n.type },
    position: { x: COL[n.type] * SPX + 80, y: (i - (total - 1) / 2) * SPY + 340 },
    classes: (D.diag[n.id] || []).join(' '),
  };
});
const chainEdges = D.edges.filter(e => chainIds.has(e.from) && chainIds.has(e.to))
  .map((e, i) => ({ data: { id: 'ce' + i, source: e.from, target: e.to, label: e.type } }));

const cy = cytoscape({
  container: document.getElementById('cy'),
  elements: [...positioned, ...chainEdges],
  layout: { name: 'preset', fit: true, padding: 40 },
  style: [
    { selector: 'node', style: {
        'background-color': ele => D.colors[ele.data('ntype')] || '#888',
        'label': 'data(label)', 'color': '#e8e6e0', 'font-size': '11px',
        'text-wrap': 'wrap', 'text-max-width': '120px',
        'text-valign': 'center', 'text-halign': 'right', 'text-margin-x': 4,
        'width': 24, 'height': 24 } },
    { selector: 'node.orphan', style: { 'border-width': 3, 'border-color': '#ffce93' } },
    { selector: 'node.overloaded', style: { 'border-width': 3, 'border-color': '#ff9b9b' } },
    { selector: 'node.hollow', style: { 'border-width': 3, 'border-color': '#9bccff', 'border-style': 'dashed' } },
    { selector: 'node.sel', style: { 'width': 34, 'height': 34, 'border-width': 3, 'border-color': '#fff', 'font-size': '13px', 'z-index': 99 } },
    { selector: 'edge', style: {
        'width': 1.4, 'line-color': '#3f3f4a', 'target-arrow-color': '#3f3f4a',
        'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'arrow-scale': 0.8 } },
    { selector: 'edge[label="produces"]', style: { 'line-color': '#2980b9', 'target-arrow-color': '#2980b9' } },
    { selector: 'edge[label="serves"]', style: { 'line-color': '#c0392b', 'target-arrow-color': '#c0392b' } },
    { selector: 'edge.hl', style: { 'width': 2.4, 'label': 'data(label)', 'font-size': '9px',
        'color': '#cfcfd6', 'text-rotation': 'autorotate', 'text-background-color': '#1a1a1e',
        'text-background-opacity': 0.85, 'text-background-padding': 2, 'z-index': 90 } },
    { selector: '.faded', style: { 'opacity': 0.12 } },
  ],
});
cy.on('tap', 'node', ev => selectNode(ev.target.id()));
cy.on('tap', ev => { if (ev.target === cy) clearSelection(); });

/* ---------- 選取 / 連動 ---------- */
let axisHi = new Set();
function highlightChain(id) {
  cy.elements().removeClass('faded sel hl');
  const n = cy.$('#' + id);
  if (!n.length) return; // 該 node 不在意圖鏈圖上(如 beat/character)
  cy.elements().addClass('faded');
  n.removeClass('faded').addClass('sel');
  n.connectedEdges().removeClass('faded').addClass('hl');
  n.neighborhood('node').removeClass('faded');
}
function selectNode(id) {
  highlightChain(id);
  const n = byId[id];
  axisHi = n && n.type === 'theme' ? new Set([id, ...feeders(id)]) : new Set([id]);
  renderDockNode(id);
  if (document.getElementById('v-axis').classList.contains('active')) drawAxis();
}
function clearSelection() {
  cy.elements().removeClass('faded sel hl');
  axisHi = new Set();
  renderDockIdle();
  if (document.getElementById('v-axis').classList.contains('active')) drawAxis();
}
function feeders(themeId) {
  const res = new Set();
  D.edges.forEach(e => {
    if ((e.type === 'serves' || e.type === 'manifests') && e.to === themeId) {
      res.add(e.from);
      D.edges.forEach(e2 => { if (e2.type === 'produces' && e2.to === e.from) res.add(e2.from); });
    }
  });
  return [...res];
}

/* ---------- 常駐 dock ---------- */
const dock = document.getElementById('dock-dyn');
const qSpan = (ev) => `<span class="q" data-s="${ev.start}" data-e="${ev.end}">${esc(ev.quote)}</span>`;
function pointHTML(p) {
  let h = `<div class="fbpoint ${p.kind}"><div class="t">${esc(p.title)}</div>`;
  if (p.quotes && p.quotes.length)
    h += '<div>' + p.quotes.map(q => '「' + qSpan(q) + '」').join(' ') + '</div>';
  if (p.body) h += `<div class="b">${esc(p.body)}</div>`;
  if (p.experiment) h += `<div class="exp"><b>實驗:</b>${esc(p.experiment)}</div>`;
  if (p.question) h += `<div class="qline" data-q="1">${esc(p.question)}</div>`;
  return h + '</div>';
}
function renderDockIdle() {
  if (!FB) { dock.innerHTML = '<p class="hint">尚無回饋。跑 /story-critique 產生 feedback,或點圖上節點看分析。</p>'; return; }
  let h = `<div class="read">${esc(FB.read)}</div>`;
  if (FB.key_points && FB.key_points.length) {
    h += '<h3>編輯最想聊的事</h3>';
    FB.key_points.forEach(p => {
      const first = (p.refs || [])[0] || '';
      h += `<div class="fbpoint key opener" data-id="${first}"><div class="t">${esc(p.title)}</div>` +
        (p.question ? `<div class="qline">${esc(p.question)}</div>` : '') +
        refchips(p.refs) + '</div>';
    });
  }
  if (FB.one_line) h += `<div class="oneline">一句話:${esc(FB.one_line)}</div>`;
  dock.innerHTML = h;
}
function renderDockNode(id) {
  const n = byId[id]; if (!n) return;
  let h = `<div style="font-size:13px"><b style="color:${D.colors[n.type]}">${D.cn[n.type]}</b> ${esc(n.label)}`;
  if (n.intensity != null) h += ` <span style="color:var(--dim)">強度 ${n.intensity}</span>`;
  h += '</div>';
  if (n.note) h += `<div class="b" style="font-size:13px;line-height:1.7;margin:6px 0">${esc(n.note)}</div>`;
  if (n.evidence && n.evidence.length) {
    h += '<h3>原文證據</h3>';
    n.evidence.forEach(ev => {
      h += `<div style="font-size:13px;line-height:1.7">「${qSpan(ev)}」` +
        (ev.note ? ` <span style="color:var(--dim)">— ${esc(ev.note)}</span>` : '') + '</div>';
    });
  }
  const pis = ptsByNode[id] || [];
  if (pis.length) {
    h += '<h3>編輯對這點的話</h3>';
    pis.forEach(i => h += pointHTML(POINTS[i]));
    h += '<p class="hint">想聊?在終端 <b>/story-discuss ' + esc(D.slug) + '</b> 接這題(網頁版即時討論為 Phase 2)。</p>';
  } else if (FB) {
    h += '<p class="hint">編輯沒特別點這顆。看「編輯最想聊的事」?<span class="q" data-idle="1">回總覽</span></p>';
  }
  dock.innerHTML = h;
}
function refchips(refs) {
  return (refs || []).filter(r => byId[r]).map(r =>
    `<span class="refchip" data-id="${r}">${esc(byId[r].label)}</span>`).join('');
}
/* dock 事件委派 */
dock.addEventListener('click', e => {
  const idle = e.target.closest('[data-idle]'); if (idle) { clearSelection(); return; }
  const q = e.target.closest('.q'); if (q && q.dataset.s != null) { gotoTab('axis'); setTimeout(() => highlightRange(+q.dataset.s, +q.dataset.e), 60); return; }
  const chip = e.target.closest('.refchip'); if (chip) { gotoTab('chain'); selectNode(chip.dataset.id); return; }
  const op = e.target.closest('.opener'); if (op && op.dataset.id) { selectNode(op.dataset.id); }
});

/* ---------- 文本軸 SVG ---------- */
const NS = 'http://www.w3.org/2000/svg';
const mk = (t, a) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); return e; };
function drawAxis() {
  const svg = document.getElementById('axis');
  const W = svg.clientWidth || 900, H = 300;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.innerHTML = '';
  const ml = 44, mr = 24, mb = 44, w = W - ml - mr;
  const baseY = H - mb, topY = 22, curveH = baseY - topY - 64;
  const X = p => ml + w * p, Y = v => baseY - 64 - curveH * v;

  svg.appendChild(mk('line', { x1: ml, y1: baseY, x2: W - mr, y2: baseY, stroke: '#4a4a55' }));
  ['開頭', '中段', '結尾'].forEach((t, i) => {
    const tx = mk('text', { x: X(i / 2), y: H - 14, fill: '#9a978f', 'font-size': 11, 'text-anchor': 'middle' });
    tx.textContent = t; svg.appendChild(tx);
  });
  const tl = mk('text', { x: ml, y: topY - 4, fill: '#9a978f', 'font-size': 10 }); tl.textContent = '張力'; svg.appendChild(tl);

  const beats = D.nodes.filter(n => n.type === 'beat' && n.intensity != null && n.evidence.some(e => e.pos != null))
    .map(n => ({ x: X(n.evidence.find(e => e.pos != null).pos), inten: n.intensity, n }))
    .sort((a, b) => a.x - b.x);
  if (beats.length) {
    let dl = `M ${beats[0].x} ${Y(beats[0].inten)}`;
    beats.slice(1).forEach(b => dl += ` L ${b.x} ${Y(b.inten)}`);
    svg.appendChild(mk('path', { d: `${dl} L ${beats[beats.length - 1].x} ${baseY} L ${beats[0].x} ${baseY} Z`, fill: '#7f8c8d', 'fill-opacity': 0.12 }));
    svg.appendChild(mk('path', { d: dl, fill: 'none', stroke: '#aeb6ba', 'stroke-width': 2 }));
    beats.forEach(b => {
      const hot = axisHi.has(b.n.id);
      const c = mk('circle', { cx: b.x, cy: Y(b.inten), r: hot ? 6 : 4, fill: '#aeb6ba', class: 'marker' });
      if (hot) { c.setAttribute('stroke', '#fff'); c.setAttribute('stroke-width', 1.5); }
      c.onclick = () => selectAndJump(b.n);
      c.appendChild(Object.assign(mk('title'), { textContent: `${b.n.label} (${b.inten})` }));
      svg.appendChild(c);
    });
    const peak = beats.reduce((a, b) => b.inten > a.inten ? b : a, beats[0]);
    const pl = mk('text', { x: peak.x, y: Y(peak.inten) - 9, fill: '#ffd479', 'font-size': 10, 'text-anchor': 'middle' });
    pl.textContent = '峰值 · ' + peak.n.label; svg.appendChild(pl);
  }
  // 意象復現虛線
  D.nodes.filter(n => n.type === 'motif').forEach(n => {
    const pts = n.evidence.filter(e => e.pos != null).map(e => X(e.pos)).sort((a, b) => a - b);
    if (pts.length > 1) svg.appendChild(mk('line', { x1: pts[0], y1: baseY - 38, x2: pts[pts.length - 1], y2: baseY - 38,
      stroke: D.colors.motif, 'stroke-opacity': 0.35, 'stroke-width': 1, 'stroke-dasharray': '2 3' }));
  });
  const lanes = { motif: { y: baseY - 38, sh: 'circle' }, technique: { y: baseY - 22, sh: 'tri' }, effect: { y: baseY - 6, sh: 'rect' } };
  for (const [type, L] of Object.entries(lanes)) {
    const lab = mk('text', { x: ml - 8, y: L.y + 3, fill: '#9a978f', 'font-size': 10, 'text-anchor': 'end' });
    lab.textContent = D.cn[type]; svg.appendChild(lab);
    D.nodes.filter(n => n.type === type).forEach(n => {
      const fb = hasFb.has(n.id), hot = axisHi.has(n.id);
      n.evidence.filter(e => e.pos != null).forEach(e => {
        const x = X(e.pos), col = D.colors[type];
        let s;
        if (L.sh === 'circle') s = mk('circle', { cx: x, cy: L.y, r: hot ? 6 : 4, fill: col, class: 'marker' });
        else if (L.sh === 'tri') s = mk('polygon', { points: `${x},${L.y - 5} ${x - 4},${L.y + 4} ${x + 4},${L.y + 4}`, fill: col, class: 'marker' });
        else s = mk('rect', { x: x - 4, y: L.y - 4, width: 8, height: 8, fill: col, class: 'marker' });
        if (hot) { s.setAttribute('stroke', '#fff'); s.setAttribute('stroke-width', 1.5); }
        else if (fb) { s.setAttribute('stroke', '#ffd479'); s.setAttribute('stroke-width', 1.5); }
        s.onclick = () => selectAndJump(n, e);
        s.appendChild(Object.assign(mk('title'), { textContent: `${n.label}「${e.quote}」` }));
        svg.appendChild(s);
      });
    });
  }
}
function selectAndJump(n, e) {
  selectNode(n.id);
  const ev = e || (n.evidence && n.evidence.find(x => x.start >= 0));
  if (ev && ev.start >= 0) highlightRange(ev.start, ev.end);
}

/* ---------- 原文高亮 ---------- */
function highlightRange(s, e) {
  const box = document.getElementById('src');
  box.innerHTML = esc(SRC.slice(0, s)) + '<mark>' + esc(SRC.slice(s, e)) + '</mark>' + esc(SRC.slice(e));
  const m = box.querySelector('mark'); if (m) m.scrollIntoView({ block: 'center', behavior: 'smooth' });
}
document.getElementById('src').textContent = SRC;
renderDockIdle();
