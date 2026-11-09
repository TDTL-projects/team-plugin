// Проверка обновления схемы в FigJam на имитации Figma (без доски и без коннектора). Нужен Node.js.
// Запуск: node test_bpmn_to_figjam.js база.js база_повтор.js новая_версия.js [другой_масштаб.js]
//   база.js и новая_версия.js — выход bpmn_to_figjam.py с одним и тем же --title;
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
const page = new N('PAGE');
const all = (n) => [n, ...n.children.flatMap(all)];
const make = (type, extra) => { const n = new N(type); Object.assign(n, extra || {}); page.appendChild(n); return n; };
const figma = {
  mixed: Symbol('mixed'), currentPage: page,
  loadFontAsync: async () => {},
  getNodeByIdAsync: async (id) => all(page).find(n => n.id === id) || null,
  createSection: () => make('SECTION'), createText: () => make('TEXT'), createRectangle: () => make('RECTANGLE'),
  createShapeWithText: () => make('SHAPE_WITH_TEXT', {text: {fontName: {family: 'Inter', style: 'Medium'}}}),
  createConnector: () => make('CONNECTOR', {text: {fontName: {family: 'Inter', style: 'Medium'}}}),
};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const run = (file) => new AsyncFunction('figma', fs.readFileSync(file, 'utf8'))(figma);
const ok = (c, msg) => { if (!c) { console.error('ОШИБКА: ' + msg); process.exit(1); } };
const pos = (sec) => Object.fromEntries(sec.children.filter(n => n.getSharedPluginData('tdtl_bpmn', 'key').endsWith('|main'))
  .map(n => [n.getSharedPluginData('tdtl_bpmn', 'key').replace(/^.*?_/, ''), [Math.round(n.x), Math.round(n.y)]]));

(async () => {
  const [base, again, next, other] = process.argv.slice(2);
  const r1 = await run(base);
  ok(r1.fresh && r1.created > 0 && r1.removed.length === 0, 'первый перенос: ' + JSON.stringify(r1));
  const sec = page.children.find(n => n.type === 'SECTION');
  const total = sec.children.length;
  // люди добавили своё: листочек, фигуру, текст с « · »
  for (const [t, name] of [['STICKY', 'Sticky'], ['SHAPE_WITH_TEXT', 'Мой блок'], ['TEXT', 'Заметка · важно']]) { const n = new N(t); n.name = name; sec.appendChild(n); }

  const r2 = await run(again);
  ok(!r2.fresh && r2.created === 0 && r2.removed.length === 0 && r2.moved.length === 0, 'повтор без изменений: ' + JSON.stringify(r2));
  ok(sec.children.length === total + 3, 'свои узлы людей пропали');

  // старая выкладка без меток (как у Даниила до правки): узнаётся по именам слоёв
  const before = pos(sec);
  for (const n of sec.children) n.spd = {};
  sec.setSharedPluginData('tdtl_bpmn', 'scale', '1.5');
  const r3 = await run(again);
  ok(r3.created === 0 && r3.removed.length === 0, 'старая выкладка не узнана: ' + JSON.stringify(r3));

  const r4 = await run(next);
  const after = pos(sec);
  const shifted = Object.keys(before).filter(k => k in after && (before[k][0] !== after[k][0] || before[k][1] !== after[k][1]));
  ok(shifted.length === r4.moved.length, 'список сдвинутых не совпадает с доской: ' + shifted.length + ' / ' + r4.moved.length);
  ok(sec.children.some(n => n.type === 'STICKY'), 'листочек удалён при обновлении');

  // другой масштаб: стоп без изменений
  sec.setSharedPluginData('tdtl_bpmn', 'scale', '1');
  const snap = JSON.stringify(pos(sec)), cnt = sec.children.length;
  let err = null; try { await run(next); } catch (e) { err = e.message; }
  ok(err && /Масштаб/.test(err) && cnt === sec.children.length && snap === JSON.stringify(pos(sec)), 'другой масштаб не остановил: ' + err);

  // код, собранный с другим --scale, на секции с прежним масштабом: стоп без изменений
  if (other) {
    sec.setSharedPluginData('tdtl_bpmn', 'scale', fs.readFileSync(next, 'utf8').match(/"S":([\d.]+)/)[1]);
    const snap2 = JSON.stringify(pos(sec)), cnt2 = sec.children.length;
    let err2 = null; try { await run(other); } catch (e) { err2 = e.message; }
    ok(err2 && /Масштаб/.test(err2) && cnt2 === sec.children.length && snap2 === JSON.stringify(pos(sec)), '--scale не остановил: ' + err2);
  }

  console.log('все проверки прошли | первый перенос: ' + r1.created + ' узлов | новая версия: создано ' + r4.created +
    ', удалено ' + r4.removed.length + ', сдвиг холста погашен ' + JSON.stringify(r4.shift) + ', сдвинуто блоков ' + r4.moved.length +
    (r4.moved.length ? ' (' + r4.moved.join(', ') + ')' : ''));
})().catch(e => { console.error('ОШИБКА: ' + e.stack); process.exit(1); });
