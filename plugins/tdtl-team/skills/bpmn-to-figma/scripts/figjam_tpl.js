// Строит или обновляет схему BPMN в FigJam. Данные подставляет bpmn_to_figjam.py; код не править.
const D = __DATA__;
const NS = 'tdtl_bpmn';
// Цвет — только #rrggbb или #rgb, иначе цвет по умолчанию: битое значение не роняет обновление посередине.
const h = (c) => { let x = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(c||'') ? c.slice(1) : 'ffffff';
  if (x.length === 3) x = x.replace(/./g, '$&$&');
  return {r:parseInt(x.slice(0,2),16)/255,g:parseInt(x.slice(2,4),16)/255,b:parseInt(x.slice(4,6),16)/255}; };
const R = {family:'Inter',style:'Regular'}, B = {family:'Inter',style:'Bold'}, M = {family:'Inter',style:'Medium'};
const stop = (m) => { throw new Error(m + ' Ничего не изменено.'); };
// Наш узел или секция — с меткой, которую поставил скрипт, и со своим же id в метке node. Копия (Ctrl+D) или вставка
// из другой секции несёт метки оригинала, но id у неё новый — она уже не наша. Без node — узлы прежней версии скрипта.
const ours = (n, k) => { if (!n.getSharedPluginData(NS, k)) return false; const id = n.getSharedPluginData(NS, 'node'); return !id || id === n.id; };
const stamp = (n) => n.setSharedPluginData(NS, 'node', n.id);

// 1. Страница и секция. Всё, что может остановить скрипт, — до первого изменения на доске.
//    Коннектор начинает каждый вызов с первой страницы («Общий»), поэтому страницу называют явно (D-0026).
let page = null;
if (D.page) {
  const ps = figma.root.children.filter(p => p.id === D.page);
  const byName = ps.length ? ps : figma.root.children.filter(p => p.name === D.page);
  if (byName.length !== 1) stop((byName.length ? 'Страниц с названием «' + D.page + '» несколько — укажите id страницы.' : 'Нет страницы «' + D.page + '».') +
    ' Страницы: ' + figma.root.children.map(p => '«' + p.name + '» (' + p.id + ')').join(', ') + '.');
  page = byName[0];
}
let sec = null;
if (D.sectionId) {
  sec = await figma.getNodeByIdAsync(D.sectionId);
  if (!sec) stop('Секция ' + D.sectionId + ' не найдена.');
  if (sec.type !== 'SECTION') stop('Узел ' + D.sectionId + ' — не секция.');
  let p = sec.parent; while (p && p.type !== 'PAGE') p = p.parent;
  if (page && p !== page) stop('Секция ' + D.sectionId + ' лежит на странице «' + (p && p.name) + '», а не на «' + page.name + '».');
  if (!ours(sec, 'scale')) stop('Секцию ' + D.sectionId + ' «' + sec.name + '» сделал не этот скрипт — её не трогаю.');
  if (sec.name !== D.title) stop('Секция ' + D.sectionId + ' называется «' + sec.name + '», а --title «' + D.title + '»: это другая схема или другая её часть. ' +
    'Проверьте --section (у каждой части схемы своя секция) или --title.');
  page = p;
}
if (!page) stop('Не указано, куда класть схему: --page «название страницы» (черновик — на странице автора, D-0026) или --section <id> из прошлого ответа.');
if (figma.currentPage !== page) await figma.setCurrentPageAsync(page);
if (!sec) {
  const same = page.children.filter(n => n.type === 'SECTION' && n.name === D.title);
  if (same.length > 1) stop('На странице «' + page.name + '» несколько секций «' + D.title + '»: укажите нужную через --section <id> (' + same.map(n => n.id).join(', ') + ').');
  sec = same[0] || null;
  // Секция с тем же заголовком, но без нашей метки, — чужая (D-0026: заголовки у всех одинаковые по форме).
  if (sec && !ours(sec, 'scale'))
    stop('На странице «' + page.name + '» уже есть секция «' + D.title + '» (' + sec.id + '), но её сделал не этот скрипт — её не трогаю. ' +
      'Возьмите другой --title или пусть автор той секции её переименует.');
}
const fresh = !sec;
if (!fresh) {
  const prev = sec.getSharedPluginData(NS, 'scale');
  if (prev && Number(prev) !== D.S && !D.force)
    stop('Масштаб схемы в секции ' + prev + ', а сейчас ' + D.S + ': все блоки сдвинутся, комментарии останутся на старых местах.');
}

// 2. Узлы прошлой выкладки — только с нашей меткой tdtl_bpmn/key. По имени слоя не узнаём: листочек «B03 · уточнить»
//    выглядит как наш блок. Листочки, фигуры и тексты людей не трогаем; копию нашего блока (Ctrl+D, та же метка) — тоже.
const keyOf = (n) => ours(n, 'key') ? n.getSharedPluginData(NS, 'key') : null;
const old = {}, dup = new Set();
for (const n of (sec ? sec.children : [])) { const k = keyOf(n); if (!k) continue; if (old[k]) dup.add(k); else old[k] = n; }
// Совпала меньше половины своих блоков — в секции другая схема или другая часть с тем же --title: перерисовка стёрла бы её.
const want = new Set([...D.items.map(i => i.id + '|main'), ...D.edges.map(e => e.id + '|main')]);
const mainOld = Object.keys(old).filter(k => k.endsWith('|main')), hit = mainOld.filter(k => want.has(k)).length;
if (mainOld.length && hit * 2 < mainOld.length)
  stop('В секции «' + sec.name + '» другая схема или другая её часть: из ' + mainOld.length + ' блоков и стрелок на доске в этой схеме ' + hit + '. ' +
    'У каждой части схемы — свой --title.');
// Шрифты — до первого изменения: человек мог поставить нашему блоку шрифт, которого нет, и скрипт упал бы посередине.
const fonts = [R, B, M];
for (const n of Object.values(old)) { const t = n.type === 'TEXT' ? n : n.text; if (t && t.fontName && t.fontName !== figma.mixed) fonts.push(t.fontName); }
try { await Promise.all(fonts.map(f => figma.loadFontAsync(f))); }
catch (e) { stop('Не загружается шрифт на блоках схемы (' + e.message + '): верните блокам шрифт Inter.'); }

if (fresh) { sec = figma.createSection(); sec.x = 0; sec.y = page.children.reduce((m,n)=>n===sec?m:Math.max(m,n.y+n.height),-200) + 200;
  sec.fills = [{type:'SOLID', color:h('#ffffff')}]; }   // фон — только у новой: человек мог перекрасить свою
sec.name = D.title; sec.setSharedPluginData(NS, 'scale', String(D.S)); stamp(sec);

// 3. Сдвиг всей схемы (bpmn.io двигает холст, другое окно --x0) гасим: блоки остаются там, где были.
const cnt = {}; let matched = 0;
for (const i of D.items) { if (i.t === 'lane') continue; const n = old[i.id+'|main']; if (!n) continue;
  matched++; const k = Math.round(n.x - i.x) + ',' + Math.round(n.y - i.y); cnt[k] = (cnt[k]||0) + 1; }
let dx = 0, dy = 0; const best = Object.entries(cnt).sort((a,b) => b[1]-a[1])[0];
if (best && best[1]*2 > matched && best[0] !== '0,0') [dx, dy] = best[0].split(',').map(Number);
for (const i of D.items) { if (i.t !== 'lane') { i.x += dx; if (i.lx != null) i.lx += dx; } i.y += dy; if (i.ly != null) i.ly += dy; }
// Секцию не ужимаем: человек мог растянуть её и положить листочки за краем схемы.
const W = Math.max(D.W, fresh ? 0 : sec.width, ...D.items.map(i => i.x + i.w + 40)), H = Math.max(D.H, fresh ? 0 : sec.height, ...D.items.map(i => i.y + i.h + 40));
sec.resizeWithoutConstraints(W, H);

const used = new Set(); let created = 0, updated = 0; const moved = [];
function get(key, make, type) {
  const n = old[key]; let node;
  if (n && n.type === type && !used.has(n.id)) { node = n; updated++; }
  else { node = make(); sec.appendChild(node); created++; }
  used.add(node.id); node.setSharedPluginData(NS, 'key', key); stamp(node); return node;
}
const S1 = (c) => [{type:'SOLID', color:h(c)}];
function txt(key, s, x, y, w, size, font, align) {
  const t = get(key, () => figma.createText(), 'TEXT'); t.rotation = 0;
  t.fontName = font||R; t.fontSize = size||11; t.characters = s||''; t.textAlignHorizontal = align||'CENTER';
  if (w) { t.textAutoResize = 'HEIGHT'; t.resize(Math.max(w,20), t.height); } else t.textAutoResize = 'WIDTH_AND_HEIGHT';
  t.x = x; t.y = y; return t;
}
const place = (n, i) => { const was = old[i.id+'|main'] === n ? [n.x, n.y] : null;
  n.x = i.x; n.y = i.y; if (was && (Math.abs(was[0]-n.x) > 2 || Math.abs(was[1]-n.y) > 2)) moved.push(i.id); };

const title = txt('title', D.title, 40, 30, 0, 48, B, 'LEFT'); title.name = 'заголовок';
const map = {}; const TASK = ['task','userTask','serviceTask','manualTask','scriptTask','businessRuleTask','sendTask','receiveTask','callActivity','subProcess'];
const EVI = {message:'✉', timer:'⏱', signal:'△', conditional:'≡', escalation:'↑', error:'ϟ'};
const GWI = {exclusiveGateway:'✕', parallelGateway:'+', inclusiveGateway:'○', eventBasedGateway:'⬠', complexGateway:'✱'};
for (const i of D.items) {
  const nm = i.id + ' · ' + (i.n||'').replace(/\n/g,' ');
  if (i.t === 'lane' || i.k === 'group') {
    const lane = i.t === 'lane';
    const r = get(i.id+'|main', () => figma.createRectangle(), 'RECTANGLE'); r.resize(i.w, i.h); r.fills = [];
    if (lane) { r.x = i.x; r.y = i.y; } else place(r, i);
    r.strokes = S1(lane?'#9aa5b1':'#7b8794'); r.strokeWeight = lane?1:1.5; r.dashPattern = lane ? [] : [8,6]; r.name = nm; r.locked = true;
    if (lane) {
      const st = get(i.id+'|полоса', () => figma.createRectangle(), 'RECTANGLE'); st.resize(D.ST, i.h); st.x = i.x; st.y = i.y;
      st.fills = S1('#eef1f5'); st.strokes = S1('#9aa5b1'); st.strokeWeight = 1; st.name = i.id + ' · полоса'; st.locked = true;
      const l = txt(i.id+'|подпись', i.n, 0, 0, Math.max(i.h-16, 40), 14, B, 'CENTER');
      l.rotation = 90; l.x = i.x + (D.ST - l.height)/2; l.y = i.y + i.h - 8;   // снизу вверх, как в BPMN
      l.name = nm + ' · подпись'; l.locked = true;
    } else {
      const l = txt(i.id+'|подпись', i.n, i.x + 8, i.y + 6, i.w - 16, 14, B, 'LEFT'); l.name = nm + ' · подпись'; l.locked = true;
    }
    continue;
  }
  const s = get(i.id+'|main', () => figma.createShapeWithText(), 'SHAPE_WITH_TEXT');
  if (s.text.fontName !== figma.mixed) await figma.loadFontAsync(s.text.fontName);
  const gw = /Gateway$/.test(i.k);
  if (i.k === 'textAnnotation') {
    s.shapeType = 'SQUARE'; s.resize(i.w, i.h);
    s.fills = S1(/^\s*Ответ/.test(i.n||'')?'#d3f9d8':(/^\s*Вопрос/.test(i.n||'')?'#fff3bf':'#f5f7fa')); s.strokes = S1('#b3b3b3'); s.strokeWeight = 1;
    s.text.fontName = R; s.text.fontSize = 11; s.text.characters = i.n||''; s.text.textAlignHorizontal = 'LEFT';
  } else if (TASK.includes(i.k)) {
    s.shapeType = 'ROUNDED_RECTANGLE'; s.resize(i.w, i.h);
    s.fills = S1(i.fill||'#ffffff'); s.strokes = S1(i.stroke||'#1e1e1e'); s.strokeWeight = i.k==='callActivity' ? 3 : 1;
    s.text.fontName = R; s.text.fontSize = 11; s.text.textAlignHorizontal = 'CENTER';
    s.text.characters = (i.k==='userTask'?'👤 ':i.k==='serviceTask'?'⚙ ':i.k==='callActivity'?'⊞ ':'') + (i.n||'');
  } else {
    s.shapeType = gw ? 'DIAMOND' : 'ELLIPSE'; s.resize(i.w, i.h);
    s.fills = S1(i.fill||'#ffffff'); s.strokes = S1(i.stroke||'#1e1e1e'); s.strokeWeight = i.k==='endEvent' ? 4 : 1.5;
    s.text.fontName = M; s.text.fontSize = gw?20:14; s.text.textAlignHorizontal = 'CENTER'; s.text.characters = gw ? (GWI[i.k]||'') : (EVI[i.ev]||'');
    if (i.n) { const l = txt(i.id+'|подпись', i.n, (i.lx!=null?i.lx:i.x-45), (i.ly!=null?i.ly:i.y+i.h+4), i.lw||i.w+90, 11, R); l.name = i.id + ' · подпись'; }
  }
  place(s, i); s.name = nm; map[i.id] = s;
}
let nc = 0;
for (const e of D.edges) {
  const a = map[e.s], b = map[e.t]; if (!a || !b) continue;
  const c = get(e.id+'|main', () => figma.createConnector(), 'CONNECTOR');
  c.connectorStart = {endpointNodeId:a.id, magnet:e.ms}; c.connectorEnd = {endpointNodeId:b.id, magnet:e.me};
  c.connectorLineType = 'ELBOWED'; c.connectorStartStrokeCap = 'NONE';
  c.connectorEndStrokeCap = e.k==='association' ? 'NONE' : 'ARROW_EQUILATERAL';
  c.strokes = S1(e.k==='association'?'#9aa5b1':'#52606d'); c.strokeWeight = 1.5;
  c.dashPattern = !e.k ? [] : (e.k==='association' ? [2,4] : [8,5]);
  if (c.text.fontName !== figma.mixed) await figma.loadFontAsync(c.text.fontName);
  c.text.fontName = R; c.text.fontSize = 11; c.text.characters = e.n||'';
  c.name = e.id + ' · ' + (e.n||''); nc++;
}
// 4. Удаляем только свои узлы, которых больше нет в .bpmn. Копии и вставки — не наши (ours), их не трогаем.
//    Повтор метки бывает только у копий, сделанных до этой версии скрипта: не трогаем, называем в dups.
const removed = [], dups = new Set();
for (const n of [...sec.children]) { if (used.has(n.id)) continue; const k = keyOf(n); if (!k) continue;
  if (dup.has(k)) { dups.add(k.split('|')[0]); continue; }
  if (k.endsWith('|main')) removed.push(k.split('|')[0]); n.remove(); }
return {page: page.name, section: sec.id, fresh, shift: [dx, dy], shapes: Object.keys(map).length, connectors: nc, created, updated, removed, moved, dups: [...dups]};
