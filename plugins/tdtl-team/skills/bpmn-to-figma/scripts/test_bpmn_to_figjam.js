// Проверка обновления схемы в FigJam на имитации Figma (без доски и без коннектора). Нужен Node.js.
// Запуск: node test_bpmn_to_figjam.js база.js база_повтор.js новая_версия.js [другой_масштаб.js]
//   база.js и новая_версия.js — выход bpmn_to_figjam.py с одним и тем же --title и --page "Наиль";
//   другой_масштаб.js — та же схема с тем же --title и другим --scale (без --force): должна остановиться.
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
const pages = ['Общий', 'Наиль'].map(name => Object.assign(new N('PAGE'), {name}));
const [common, author] = pages;
const all = (n) => [n, ...n.children.flatMap(all)];
const make = (type, extra) => { const n = new N(type); Object.assign(n, extra || {}); figma.currentPage.appendChild(n); return n; };
const figma = {
  mixed: Symbol('mixed'), currentPage: common, root: {children: pages},
  setCurrentPageAsync: async (p) => { figma.currentPage = p; },
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
const board = () => JSON.stringify(pages.flatMap(all).map(n => [n.id, n.name, n.x, n.y, n.fills, n.parent && n.parent.id, n.spd]));
const fails = async (file, patch, re, msg) => {
  const snap = board();
  let err = null; try { await run(file, patch); } catch (e) { err = e.message; }
  ok(err && re.test(err), msg + ': ' + err);
  ok(snap === board(), msg + ': доска изменилась');
};
let mine = [];   // узлы, которые добавили люди (в том числе копия нашего блока с той же меткой)
const pos = (sec) => Object.fromEntries(sec.children.filter(n => !mine.includes(n) && n.getSharedPluginData('tdtl_bpmn', 'key').endsWith('|main'))
  .map(n => [n.getSharedPluginData('tdtl_bpmn', 'key').replace(/^.*?_/, ''), [Math.round(n.x), Math.round(n.y)]]));
const human = (sec, type, name) => { const n = new N(type); n.name = name; sec.appendChild(n); return n; };

(async () => {
  const [base, again, next, other] = process.argv.slice(2);
  const title = JSON.parse(fs.readFileSync(base, 'utf8').match(/^const D = (.*);$/m)[1]).title;

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
  // текст «заголовок», копию нашего блока (Ctrl+D, та же метка)
  mine = [['STICKY', 'Sticky'], ['SHAPE_WITH_TEXT', 'Мой блок'], ['TEXT', 'Заметка · важно'],
    ['STICKY', 'TODO · уточнить'], ['TEXT', 'Step2 · проверить'], ['STICKY', short + ' · уточнить у Андрея'],
    ['SHAPE_WITH_TEXT', orig.name], ['TEXT', short + ' · подпись'], ['TEXT', 'заголовок']].map(([t, n]) => human(sec, t, n));
  for (const n of mine) { n.x = -500; n.y = -500; n.text = {characters: 'своё', fontName: {family: 'Inter', style: 'Medium'}}; }
  const copy = human(sec, orig.type, orig.name); copy.spd = {...orig.spd}; copy.x = orig.x + 30; copy.y = orig.y + 30;
  mine.push(copy);
  // узел людей на месте и не тронут: та же секция, место, текст, без нашей метки
  const alive = () => mine.every(n => n.parent === sec && (n === copy || (n.x === -500 && n.y === -500 && n.text.characters === 'своё' && !n.spd['tdtl_bpmn/key'])));
  const origId = orig.getSharedPluginData('tdtl_bpmn', 'key').split('|')[0];

  const r2 = await run(again);
  ok(!r2.fresh && r2.created === 0 && r2.removed.length === 0 && r2.moved.length === 0, 'повтор без изменений: ' + JSON.stringify(r2));
  ok(alive() && sec.children.length === total + mine.length, 'свои узлы людей пропали');
  ok(JSON.stringify(r2.dups) === JSON.stringify([origId]), 'в dups не только копия блока: ' + JSON.stringify(r2.dups));
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
  ok(JSON.stringify(sec.fills) === fill, 'фон секции перекрашен при обновлении');
  ok(sec.width >= big[0] && sec.height >= big[1], 'растянутую секцию ужали: ' + [sec.width, sec.height] + ' < ' + big);

  // другой масштаб: стоп без изменений
  sec.setSharedPluginData('tdtl_bpmn', 'scale', '1');
  await fails(next, null, /Масштаб/, 'другой масштаб не остановил');

  // код, собранный с другим --scale, на секции с прежним масштабом: стоп без изменений
  sec.setSharedPluginData('tdtl_bpmn', 'scale', fs.readFileSync(next, 'utf8').match(/"S":([\d.]+)/)[1]);
  if (other) await fails(other, null, /Масштаб/, '--scale не остановил');
  // дальше масштаб совпадает: каждая остановка ниже срабатывает по своей причине, а не по масштабу

  // --section лежит на одной странице, --page — другая: стоп
  await fails(next, {sectionId: sec.id, page: 'Общий'}, /страниц/, '--section не на странице --page');

  // чужая секция с тем же заголовком (нарисована руками, метки нет): стоп, ничего не тронуто
  const foreign = Object.assign(new N('SECTION'), {name: title}); common.appendChild(foreign);
  const theirs = [human(foreign, 'STICKY', 'TODO · уточнить'), human(foreign, 'SHAPE_WITH_TEXT', 'Шаг 1')];
  await fails(base, {page: 'Общий'}, /не этот скрипт/, 'чужая секция с тем же заголовком принята за свою');
  // --section на секции людей (нет метки) — тоже стоп: её скрипт не трогает никогда
  await fails(base, {page: undefined, sectionId: foreign.id}, /не этот скрипт/, '--section на чужой секции не остановил');
  ok(theirs.every(n => n.parent === foreign), 'в чужой секции тронуты узлы людей');

  // схема перенесена частями, у каждой своя секция: --section от другой части — стоп, а не перерисовка чужой части
  await fails(next, d => { d.sectionId = sec.id; delete d.page; d.title = title + ' · этап 06'; }, /называется/, '--section от другой части не остановил');

  console.log('все проверки прошли | первый перенос: ' + r1.created + ' узлов | новая версия: создано ' + r4.created +
    ', удалено ' + r4.removed.length + ', сдвиг холста погашен ' + JSON.stringify(r4.shift) + ', сдвинуто блоков ' + r4.moved.length +
    (r4.moved.length ? ' (' + r4.moved.join(', ') + ')' : ''));
})().catch(e => { console.error('ОШИБКА: ' + e.stack); process.exit(1); });
