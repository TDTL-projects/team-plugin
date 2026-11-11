// Проверка обновления схемы в FigJam на имитации Figma (без доски и без коннектора). Нужен Node.js.
// Запуск: node test_bpmn_to_figjam.js база.js база_повтор.js новая_версия.js [другой_масштаб.js]
//   база.js и новая_версия.js — выход bpmn_to_figjam.py с одним и тем же --title и --page "Наиль";
//   другой_масштаб.js — та же схема с тем же --title и другим --scale (без --force): должна остановиться.
// Проверки T-0220 (метка gone на весь документ) делят новую_версию.js на две части по ширине схемы — в ней нужны
// хотя бы два блока-задачи в левой половине; каждый файл из аргументов — не длиннее 49 000 знаков.
const fs = require('fs');
let nid = 0;
class N {
  constructor(type) { Object.assign(this, {type, id: 'n' + (++nid), name: '', x: 0, y: 0, width: 100, height: 14, rotation: 0, children: [], parent: null, spd: {}}); }
  getSharedPluginData(ns, k) { return this.spd[ns + '/' + k] || ''; }
  setSharedPluginData(ns, k, v) { this.spd[ns + '/' + k] = v; }
  resize(w, h) { this.width = w; this.height = h; }
  resizeWithoutConstraints(w, h) { this.resize(w, h); }
  appendChild(c) { if (c.parent) c.parent.children.splice(c.parent.children.indexOf(c), 1); c.parent = this; this.children.push(c); }
  remove() { this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null; }
  findChild(f) { return this.children.find(f) || null; }
}
// Две страницы, как на доске «Процессы»: первая — «Общий», черновики — на странице автора (D-0026).
// Документ — со своими метками (getSharedPluginData на весь файл, T-0220); страницы грузятся сразу, loadAsync ничего не делает.
const pages = ['Общий', 'Наиль'].map(name => Object.assign(new N('PAGE'), {name, loadAsync: async () => {}}));
const [common, author] = pages;
const root = Object.assign(new N('DOCUMENT'), {id: '0:0', name: 'Процессы', children: pages});
for (const p of pages) p.parent = root;
const all = (n) => [n, ...n.children.flatMap(all)];
const make = (type, extra) => { const n = new N(type); Object.assign(n, extra || {}); figma.currentPage.appendChild(n); return n; };
const figma = {
  mixed: Symbol('mixed'), currentPage: common, root,
  setCurrentPageAsync: async (p) => { figma.currentPage = p; }, loadAllPagesAsync: async () => {},
  loadFontAsync: async () => {},
  getNodeByIdAsync: async (id) => pages.flatMap(all).find(n => n.id === id) || null,
  createSection: () => make('SECTION'), createText: () => make('TEXT'), createRectangle: () => make('RECTANGLE'),
  createShapeWithText: () => make('SHAPE_WITH_TEXT', {text: {fontName: {family: 'Inter', style: 'Medium'}}}),
  createConnector: () => make('CONNECTOR', {text: {fontName: {family: 'Inter', style: 'Medium'}}}),
};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
// patch — правка данных скрипта, как другие флаги bpmn_to_figjam.py: объект (undefined убирает поле) или функция
const run = (file, patch) => {
  let code = fs.readFileSync(file, 'utf8');
  if (patch) {
    const m = code.match(/^const D = (.*);$/m);
    const d = JSON.parse(m[1]);
    if (typeof patch === 'function') patch(d); else Object.assign(d, patch);
    for (const k of Object.keys(d)) if (d[k] === undefined) delete d[k];
    code = code.replace(m[0], () => 'const D = ' + JSON.stringify(d) + ';');
  }
  figma.currentPage = common;   // коннектор начинает каждый вызов с первой страницы
  return new AsyncFunction('figma', code)(figma);
};
const ok = (c, msg) => { if (!c) { console.error('ОШИБКА: ' + msg); process.exit(1); } };
const board = () => JSON.stringify([root.spd, ...pages.flatMap(all).map(n => [n.id, n.name, n.x, n.y, n.fills, n.parent && n.parent.id, n.spd])]);
const fails = async (file, patch, re, msg) => {
  const snap = board();
  let err = null; try { await run(file, patch); } catch (e) { err = e.message; }
  ok(err && re.test(err), msg + ': ' + err);
  ok(snap === board(), msg + ': доска изменилась');
};
let mine = [];   // узлы, которые добавили люди (в том числе копия нашего блока с той же меткой)
const extra = [];   // ещё узлы людей с нашей меткой, добавленные позже (в позиции блоков схемы не входят)
const pos = (sec) => Object.fromEntries(sec.children.filter(n => !mine.includes(n) && !extra.includes(n) && n.getSharedPluginData('tdtl_bpmn', 'key').endsWith('|main'))
  .map(n => [n.getSharedPluginData('tdtl_bpmn', 'key').replace(/^.*?_/, ''), [Math.round(n.x), Math.round(n.y)]]));
const human = (sec, type, name) => { const n = new N(type); n.name = name; sec.appendChild(n); return n; };

(async () => {
  const [base, again, next, other] = process.argv.slice(2);
  const title = JSON.parse(fs.readFileSync(base, 'utf8').match(/^const D = (.*);$/m)[1]).title;
  // T-0220 AC-6: код влезает в предел коннектора с запасом (bpmn_to_figjam.py, LIMIT) — считаем знаки, как Python
  for (const f of process.argv.slice(2)) { const len = Array.from(fs.readFileSync(f, 'utf8')).length;
    ok(len <= 49000, 'T-0220 AC-6: код ' + f + ' длиннее 49 000 знаков: ' + len); }

  // страница не указана или не найдена — стоп до любых изменений
  await fails(base, {page: undefined, sectionId: undefined}, /--page/, 'без --page и --section не остановил');
  await fails(base, {page: 'Нет такой'}, /Нет страницы/, 'неизвестная страница не остановила');
  await fails(base, {sectionId: 'n999999'}, /не найдена/, 'несуществующая --section не остановила');

  const r1 = await run(base);
  ok(r1.fresh && r1.created > 0 && r1.removed.length === 0, 'первый перенос: ' + JSON.stringify(r1));
  ok(!common.children.length, 'секция легла на первую страницу, а не на страницу автора');
  const sec = author.children.find(n => n.type === 'SECTION');
  ok(sec, 'секции нет на странице автора');
  const total = sec.children.length;
  const orig = sec.children.find(n => n.type === 'SHAPE_WITH_TEXT' && n.getSharedPluginData('tdtl_bpmn', 'key'));
  const short = orig.getSharedPluginData('tdtl_bpmn', 'key').split('|')[0].replace(/^.*?_/, '');   // B03 из BRK-TOBE_B03
  // люди добавили своё: листочки (в том числе латиницей «слово · …» и с id блока из схемы), фигуру и текст с id из схемы,
  // текст «заголовок», копию нашего блока (Ctrl+D, те же метки) и блок, вставленный из другой секции (с её метками)
  mine = [['STICKY', 'Sticky'], ['SHAPE_WITH_TEXT', 'Мой блок'], ['TEXT', 'Заметка · важно'],
    ['STICKY', 'TODO · уточнить'], ['TEXT', 'Step2 · проверить'], ['STICKY', short + ' · уточнить у Андрея'],
    ['SHAPE_WITH_TEXT', orig.name], ['TEXT', short + ' · подпись'], ['TEXT', 'заголовок']].map(([t, n]) => human(sec, t, n));
  for (const n of mine) { n.x = -500; n.y = -500; n.text = {characters: 'своё', fontName: {family: 'Inter', style: 'Medium'}}; }
  // копия стоит в секции раньше оригинала (человек поднял оригинал наверх или вынул его и вернул) — порядок ей не помогает
  const copy = human(sec, orig.type, orig.name); copy.spd = {...orig.spd}; copy.x = orig.x + 30; copy.y = orig.y + 30;
  copy.text = {characters: 'Вариант Б', fontName: {family: 'Inter', style: 'Medium'}};
  sec.children.splice(sec.children.indexOf(copy), 1); sec.children.unshift(copy);
  // блок вставлен из другой секции, где лежит его оригинал
  const elsewhere = Object.assign(new N('SECTION'), {name: 'Другая схема · как есть'}); author.appendChild(elsewhere);
  const src = human(elsewhere, 'SHAPE_WITH_TEXT', 'BRK-ASIS_X99 · Блок из «как есть»');
  src.spd = {'tdtl_bpmn/key': 'BRK-ASIS_X99|main', 'tdtl_bpmn/node': src.id};
  const pasted = human(sec, 'SHAPE_WITH_TEXT', src.name); pasted.x = -800; pasted.y = -800; pasted.spd = {...src.spd};
  pasted.text = {characters: 'из другой секции', fontName: {family: 'Inter', style: 'Medium'}};
  mine.push(copy, pasted);
  // узел людей на месте и не тронут: та же секция, место, текст, метки
  const look = (n) => JSON.stringify([n.parent && n.parent.id, n.x, n.y, n.text && n.text.characters, n.spd]);
  const was = new Map(mine.map(n => [n, look(n)]));
  const alive = () => mine.every(n => look(n) === was.get(n));

  const r2 = await run(again);
  ok(!r2.fresh && r2.created === 0 && r2.removed.length === 0 && r2.moved.length === 0, 'повтор без изменений: ' + JSON.stringify(r2));
  ok(alive() && sec.children.length === total + mine.length, 'свои узлы людей пропали');
  ok(r2.dups.length === 0, 'копия или вставка названы нашими: ' + JSON.stringify(r2.dups));
  ok(orig.parent === sec && orig.text.characters !== 'Вариант Б', 'оригинал блока потерян');

  // секция прежней версии скрипта (метки node ещё нет) и вставленный туда до обновления блок из другой секции:
  // ключа нет в этой схеме — не удаляем, называем в unknown; свои узлы при этом получают метку node
  for (const n of [sec, ...sec.children]) if (!mine.includes(n)) delete n.spd['tdtl_bpmn/node'];
  const legacyPaste = human(sec, 'SHAPE_WITH_TEXT', 'BRK-ASIS_Y01 · Блок из «как есть»'); legacyPaste.x = -900; legacyPaste.y = -900;
  legacyPaste.spd = {'tdtl_bpmn/key': 'BRK-ASIS_Y01|main'}; legacyPaste.text = {characters: 'старая вставка', fontName: {family: 'Inter', style: 'Medium'}};
  const lp = look(legacyPaste);
  // и копия блока, сделанная людьми на секции прежней версии (Ctrl+D, сразу после оригинала, тоже без node)
  const lsrc = sec.children.find(n => n.type === 'SHAPE_WITH_TEXT' && n !== orig && !mine.includes(n) && n.spd['tdtl_bpmn/key']);
  const legacyCopy = Object.assign(new N(lsrc.type), {name: lsrc.name, x: lsrc.x + 50, y: lsrc.y, spd: {...lsrc.spd},
    text: {characters: 'копия прежней версии', fontName: {family: 'Inter', style: 'Medium'}}});
  sec.children.splice(sec.children.indexOf(lsrc) + 1, 0, legacyCopy); legacyCopy.parent = sec;
  const lcId = lsrc.spd['tdtl_bpmn/key'].split('|')[0], lc = look(legacyCopy); extra.push(legacyCopy);
  const lsrcX = lsrc.x;
  const r3 = await run(again);
  ok(r3.created === 0 && r3.removed.length === 0 && look(legacyPaste) === lp, 'на секции прежней версии вставка удалена или тронута: ' + JSON.stringify(r3));
  ok(look(legacyCopy) === lc && r3.dups.includes(lcId), 'копия на секции прежней версии тронута или не названа в dups: ' + JSON.stringify(r3.dups));
  ok(JSON.stringify(r3.unknown) === '["BRK-ASIS_Y01"]', 'вставка без метки node не названа в unknown: ' + JSON.stringify(r3.unknown));
  ok(sec.children.every(n => n === legacyPaste || n === legacyCopy || mine.includes(n) || n.spd['tdtl_bpmn/node'] === n.id), 'свои узлы прежней версии не получили метку node');
  ok(alive(), 'на секции прежней версии тронуты узлы людей');

  const before = pos(sec);

  // человек растянул секцию и положил листочек за край схемы
  sec.resize(sec.width + 3000, sec.height + 2000);
  const big = [sec.width, sec.height];
  sec.fills = [{type: 'SOLID', color: {r: 0.9, g: 0.95, b: 1}}];
  const fill = JSON.stringify(sec.fills);
  // цвет из .bpmn не в виде #rrggbb не роняет обновление посередине
  const r4 = await run(next, d => { const t = d.items.find(i => i.t !== 'lane'); t.fill = 'red'; t.stroke = '#fff'; });
  const after = pos(sec);
  const shifted = Object.keys(before).filter(k => k in after && (before[k][0] !== after[k][0] || before[k][1] !== after[k][1]));
  ok(shifted.length === r4.moved.length, 'список сдвинутых не совпадает с доской: ' + shifted.length + ' / ' + r4.moved.length);
  ok(alive(), 'листочек или копия блока удалены при обновлении');
  // второй запуск: оригинал уже со своей меткой node, копия прежней версии — нет; её всё равно не удаляем
  ok(look(legacyCopy) === lc && r4.dups.includes(lcId) && !r4.removed.includes(lcId), 'копия прежней версии удалена на втором запуске: ' + JSON.stringify([r4.dups, r4.removed]));
  ok(JSON.stringify(sec.fills) === fill, 'фон секции перекрашен при обновлении');
  ok(sec.width >= big[0] && sec.height >= big[1], 'растянутую секцию ужали: ' + [sec.width, sec.height] + ' < ' + big);

  // человек скопировал блок и написал в копии свой вариант; блок убрали из схемы (скрипт удалил оригинал), потом вернули.
  // Копия не должна стать «вырезанным и вставленным» блоком: её не трогаем, блок рисуется заново.
  const kNode = sec.children.find(n => n.type === 'SHAPE_WITH_TEXT' && n !== orig && n !== lsrc && !mine.includes(n) && !extra.includes(n) && n.spd['tdtl_bpmn/node'] === n.id);
  const kId = kNode.spd['tdtl_bpmn/key'].split('|')[0];
  const kCopy = Object.assign(new N(kNode.type), {name: kNode.name, x: kNode.x + 60, y: kNode.y, spd: {...kNode.spd},
    text: {characters: 'Вариант В', fontName: {family: 'Inter', style: 'Medium'}}});
  sec.appendChild(kCopy); extra.push(kCopy); const kc = look(kCopy);
  const r4a = await run(next, d => { d.items = d.items.filter(i => i.id !== kId); d.edges = d.edges.filter(e => e.s !== kId && e.t !== kId); });
  ok(r4a.removed.includes(kId) && !kNode.parent && look(kCopy) === kc, 'блок не удалён или тронута его копия: ' + JSON.stringify(r4a.removed));
  const r4b = await run(next);
  ok(r4b.created > 0 && look(kCopy) === kc && !r4b.moved.includes(kId), 'копию затёрли, когда блок вернули в схему: ' + JSON.stringify([kCopy.x, kCopy.text.characters, r4b.moved]));

  // другой масштаб: стоп без изменений
  sec.setSharedPluginData('tdtl_bpmn', 'scale', '1');
  await fails(next, null, /Масштаб/, 'другой масштаб не остановил');

  // код, собранный с другим --scale, на секции с прежним масштабом: стоп без изменений
  sec.setSharedPluginData('tdtl_bpmn', 'scale', fs.readFileSync(next, 'utf8').match(/"S":([\d.]+)/)[1]);
  if (other) await fails(other, null, /Масштаб/, '--scale не остановил');
  // дальше масштаб совпадает: каждая остановка ниже срабатывает по своей причине, а не по масштабу

  // часть 2 запущена с заголовком части 1 (скопировали команду): стоп, часть 1 цела. Как в настоящем --groups,
  // дорожки у частей общие (те же id), блоков в маленькой части меньше, чем дорожек.
  const part = title + ' · малая часть';
  const rp = await run(base, d => { d.title = part; const keep = new Set(d.items.filter(i => i.t !== 'lane').slice(0, 4).map(i => i.id));
    d.items = d.items.filter(i => i.t === 'lane' || keep.has(i.id)); d.edges = d.edges.filter(e => keep.has(e.s) && keep.has(e.t)); });
  ok(rp.fresh, 'малая часть не легла новой секцией: ' + JSON.stringify(rp));
  await fails(next, d => { d.title = part; for (const i of d.items) if (i.t !== 'lane') i.id = 'P2_' + i.id;
    for (const e of d.edges) Object.assign(e, {id: 'P2_' + e.id, s: 'P2_' + e.s, t: 'P2_' + e.t}); },
    /другая схема/, 'часть 2 с тем же --title стёрла бы часть 1');

  // --section лежит на одной странице, --page — другая: стоп
  await fails(next, {sectionId: sec.id, page: 'Общий'}, /страниц/, '--section не на странице --page');

  // копия нашей секции (Ctrl+D, те же метки) на другой странице — не наша: стоп
  const secCopy = Object.assign(new N('SECTION'), {name: title, spd: {...sec.spd}}); common.appendChild(secCopy);
  await fails(base, {page: 'Общий'}, /не этот скрипт/, 'копия секции принята за свою');
  secCopy.remove();

  // чужая секция с тем же заголовком (нарисована руками, метки нет): стоп, ничего не тронуто
  const foreign = Object.assign(new N('SECTION'), {name: title}); common.appendChild(foreign);
  const theirs = [human(foreign, 'STICKY', 'TODO · уточнить'), human(foreign, 'SHAPE_WITH_TEXT', 'Шаг 1')];
  await fails(base, {page: 'Общий'}, /не этот скрипт/, 'чужая секция с тем же заголовком принята за свою');
  // --section на секции людей (нет метки) — тоже стоп: её скрипт не трогает никогда
  await fails(base, {page: undefined, sectionId: foreign.id}, /не этот скрипт/, '--section на чужой секции не остановил');
  ok(theirs.every(n => n.parent === foreign), 'в чужой секции тронуты узлы людей');

  // схема перенесена частями, у каждой своя секция: --section от другой части — стоп, а не перерисовка чужой части
  await fails(next, d => { d.sectionId = sec.id; delete d.page; d.title = title + ' · этап 06'; }, /называется/, '--section от другой части не остановил');

  // вырезали и вставили (Ctrl+X → Ctrl+V): у блока и у секции новые id, метки прежние, оригиналов больше нет.
  // Так схему переносят на «Общий» — секция должна обновляться как своя, без второй копии и без стопа.
  const blk = sec.children.find(n => n.type === 'SHAPE_WITH_TEXT' && n !== orig && !mine.includes(n) && n.spd['tdtl_bpmn/node'] === n.id);
  const blk2 = Object.assign(new N(blk.type), {name: blk.name, x: blk.x, y: blk.y, text: blk.text, spd: {...blk.spd}});
  blk.remove(); sec.appendChild(blk2);
  // а этот блок вырезан вместе с копией: у двух узлов метки одного пропавшего блока, различить их нельзя
  const blk3 = sec.children.find(n => n.type === 'SHAPE_WITH_TEXT' && n !== orig && n !== blk2 && !mine.includes(n) && n.spd['tdtl_bpmn/node'] === n.id);
  const twins = [0, 1].map(d => Object.assign(new N(blk3.type), {name: blk3.name, x: blk3.x + d * 40, y: blk3.y, text: blk3.text, spd: {...blk3.spd}}));
  const blk3Id = blk3.spd['tdtl_bpmn/key'].split('|')[0];
  blk3.remove(); for (const n of twins) sec.appendChild(n);
  const moved = Object.assign(new N('SECTION'), {name: sec.name, spd: {...sec.spd}, width: sec.width, height: sec.height, fills: sec.fills});
  for (const n of [...sec.children]) moved.appendChild(n);
  sec.remove(); common.appendChild(moved);
  // блок вставлен из другого файла: оригинала в этом файле нет, ключа в схеме нет — не удаляем, называем в unknown
  const foreignFile = human(moved, 'SHAPE_WITH_TEXT', 'OTHER_Z1 · Блок из другого файла');
  foreignFile.spd = {'tdtl_bpmn/key': 'OTHER_Z1|main', 'tdtl_bpmn/node': 'n888888'};
  // блок вставлен из другого файла, и такой ключ в схеме есть: оригинала в этом файле нет, свой блок на месте — не удаляем, в dups
  const twinSrc = moved.children.find(n => n.type === 'SHAPE_WITH_TEXT' && n !== orig && n !== blk2 && !twins.includes(n) && n !== lsrc && !mine.includes(n) && n.spd['tdtl_bpmn/node'] === n.id);
  const fromFile = Object.assign(new N(twinSrc.type), {name: twinSrc.name, x: -1200, y: -1200, spd: {...twinSrc.spd, 'tdtl_bpmn/node': 'n999999'},
    text: {characters: 'из другого файла', fontName: {family: 'Inter', style: 'Medium'}}}); moved.appendChild(fromFile);
  const ffId = twinSrc.spd['tdtl_bpmn/key'].split('|')[0];
  const count = moved.children.length;
  const r6 = await run(next, {page: undefined, sectionId: moved.id});
  ok(r6.created === 0 && r6.removed.length === 0, 'вырезанная и вставленная секция не обновилась на месте: ' + JSON.stringify(r6));
  ok(moved.children.length === count && blk2.parent === moved && blk2.spd['tdtl_bpmn/node'] === blk2.id && moved.spd['tdtl_bpmn/node'] === moved.id,
    'вырезанный блок или секция не стали своими');
  ok(mine.every(n => n.parent === moved) && pasted.text.characters === 'из другой секции', 'при переносе тронуты узлы людей');
  ok(foreignFile.parent === moved && r6.unknown.includes('OTHER_Z1'), 'вставка из другого файла удалена или не названа в unknown: ' + JSON.stringify(r6.unknown));
  ok(fromFile.parent === moved && fromFile.x === -1200 && fromFile.text.characters === 'из другого файла' && r6.dups.includes(ffId),
    'вставка из другого файла с ключом из схемы удалена, тронута или не названа в dups: ' + JSON.stringify(r6.dups));
  ok(legacyCopy.parent === moved && legacyCopy.x === lsrcX + 50 && legacyCopy.text.characters === 'копия прежней версии' && r6.dups.includes(lcId),
    'копию прежней версии обновили вместо вырезанного оригинала: ' + JSON.stringify([legacyCopy.x, legacyCopy.text.characters, r6.dups]));
  ok(r6.dups.includes(blk3Id) && twins.every(n => n.parent === moved), 'копия, вырезанная вместе с оригиналом, не названа в dups или удалена: ' + JSON.stringify(r6.dups));

  // T-0220. Схема разложена на две секции (две части с разными --title, как «· этапы 01–02» и «· этапы 03–05»).
  // Андрей скопировал (Ctrl+D) блок из первой секции во вторую и вписал свой вариант. Блок убрали из схемы — скрипт
  // удалил оригинал в первой секции. Потом блок вернули в схему второй части: обновление второй секции не должна
  // принять копию за вырезанный блок. Второй блок удалила из первой секции прежняя версия скрипта (до выкатки новой):
  // его id лежит только в метке gone первой секции (через запятую), а следующей новая версия обновляет вторую секцию.
  const NS = 'tdtl_bpmn';
  const DN = JSON.parse(fs.readFileSync(next, 'utf8').match(/^const D = (.*);$/m)[1]);
  const cx = (i) => i.x + i.w / 2, body = DN.items.filter(i => i.t !== 'lane');
  const mid = (Math.min(...body.map(cx)) + Math.max(...body.map(cx))) / 2;
  const ids1 = new Set(body.filter(i => cx(i) < mid).map(i => i.id)), ids2 = new Set(body.filter(i => cx(i) >= mid).map(i => i.id));
  const [b0, b1] = body.filter(i => ids1.has(i.id) && /Task$|^task$|^callActivity$/.test(i.k)).map(i => i.id);
  ok(b0 && b1 && ids2.size, 'T-0220: в новой версии схемы нет двух блоков-задач в левой половине — сценарий не собрать');
  const T1 = title + ' · часть 1', T2 = title + ' · часть 2';
  const slice = (t, ids) => (d) => { d.title = t; d.items = d.items.filter(i => i.t === 'lane' || ids.has(i.id));
    d.edges = d.edges.filter(e => ids.has(e.s) && ids.has(e.t)); };
  ok((await run(next, slice(T1, ids1))).fresh && (await run(next, slice(T2, ids2))).fresh, 'T-0220: части схемы не легли новыми секциями');
  const sec1 = author.children.find(n => n.type === 'SECTION' && n.name === T1), sec2 = author.children.find(n => n.type === 'SECTION' && n.name === T2);
  const own = (s, id) => s.children.find(n => n.spd[NS + '/key'] === id + '|main' && n.spd[NS + '/node'] === n.id);
  const o0 = own(sec1, b0), o1 = own(sec1, b1);
  // копия: новый узел с метками оригинала (и с его id в node), в другой секции, на другом месте, со своим текстом
  const dupe = (o, text, x, y) => { const c = Object.assign(new N(o.type), {name: o.name, x, y, spd: {...o.spd},
    text: {characters: text, fontName: {family: 'Inter', style: 'Medium'}}}); sec2.appendChild(c); return c; };
  const c0 = dupe(o0, 'Вариант Андрея', 111, 222), c1 = dupe(o1, 'Вариант Андрея 2', 333, 444);
  const c0was = look(c0), c1was = look(c1);
  // первый блок убрали из первой части: обновление первой секции удаляет его оригинал
  const q1 = await run(next, slice(T1, new Set([...ids1].filter(id => id !== b0))));
  ok(q1.removed.includes(b0) && !o0.parent && look(c0) === c0was && look(c1) === c1was,
    'T-0220: обновление первой секции не удалило оригинал или тронуло копии: ' + JSON.stringify(q1.removed));
  // второй блок убрала из схемы и удалила из первой секции прежняя версия скрипта: id — только в метке gone секции
  const lg = sec1.getSharedPluginData(NS, 'gone'); o1.remove(); sec1.setSharedPluginData(NS, 'gone', (lg ? lg + ',' : '') + o1.id);
  const token = (s, id) => new RegExp('(^|[^\\w:])' + id.replace(/[^\w]/g, '\\$&') + '($|[^\\w:])').test(s);
  ok(token(root.getSharedPluginData(NS, 'gone'), o0.id),
    'T-0220 AC-1: id удалённого скриптом узла ' + o0.id + ' нет в метке gone документа: «' + root.getSharedPluginData(NS, 'gone') + '»');
  // блоки вернули в схему — во вторую часть
  const q2 = await run(next, slice(T2, new Set([...ids2, b0, b1])));
  const named = [...q2.dups, ...q2.unknown];
  ok(look(c0) === c0was && named.includes(b0), 'T-0220 AC-2: копию в другой секции затёрли или не назвали в dups/unknown, когда блок вернули в схему: ' +
    JSON.stringify([c0.parent && c0.parent.name, c0.x, c0.y, c0.text.characters, q2.dups, q2.unknown]));
  ok(own(sec2, b0) && own(sec2, b0) !== c0, 'T-0220 AC-2: вернувшийся блок не нарисован во второй секции заново');
  ok(look(c1) === c1was && named.includes(b1), 'T-0220 AC-1: метка gone, записанная в первой секции прежней версией, не учтена — копию затёрли или не назвали: ' +
    JSON.stringify([c1.parent && c1.parent.name, c1.x, c1.y, c1.text.characters, q2.dups, q2.unknown]));

  // T-0220 AC-3: gone загружен до check(sec). Скрипт сам секций не удаляет — состояние искусственное: id исходной секции
  // лежит в её метке gone, секцию скопировали (Ctrl+D, метки те же), исходную удалили. Если gone загружен до проверки
  // секции, копия — не наша (её оригинал удалил «скрипт»): стоп. Если позже — копия сочтена вырезанной и обновлена.
  const T3 = title + ' · копия секции', small = new Set([...ids2].slice(0, 4));
  ok((await run(next, slice(T3, small))).fresh, 'T-0220: секция для проверки AC-3 не легла новой');
  const sA = author.children.find(n => n.type === 'SECTION' && n.name === T3);
  const sB = Object.assign(new N('SECTION'), {name: T3, x: sA.x, y: sA.y + sA.height + 200, width: sA.width, height: sA.height, fills: sA.fills,
    spd: {...sA.spd, [NS + '/gone']: (sA.spd[NS + '/gone'] ? sA.spd[NS + '/gone'] + ',' : '') + sA.id}});
  for (const n of sA.children) sB.appendChild(Object.assign(new N(n.type), {name: n.name, x: n.x, y: n.y, text: n.text && {...n.text}, spd: {...n.spd}}));
  sA.remove(); author.appendChild(sB);
  await fails(next, d => { slice(T3, small)(d); d.sectionId = sB.id; delete d.page; }, /не этот скрипт/,
    'T-0220 AC-3: метка gone загружена после проверки секции — копия секции, чей оригинал в gone, принята за свою');

  console.log('все проверки прошли | первый перенос: ' + r1.created + ' узлов | новая версия: создано ' + r4.created +
    ', удалено ' + r4.removed.length + ', сдвиг холста погашен ' + JSON.stringify(r4.shift) + ', сдвинуто блоков ' + r4.moved.length +
    (r4.moved.length ? ' (' + r4.moved.join(', ') + ')' : ''));
})().catch(e => { console.error('ОШИБКА: ' + e.stack); process.exit(1); });
