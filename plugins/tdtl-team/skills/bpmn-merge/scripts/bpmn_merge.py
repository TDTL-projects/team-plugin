"""Сборка версий .bpmn от разных авторов в одну по id элементов.

Как работает (трёхсторонняя сборка):
  исходная версия (общий предок) + версии авторов -> собранная версия + отчёт.
  - Новые элементы из версий (блоки, стрелки, заметки, группы) добавляются сами.
  - Изменения и удаления существующих элементов НЕ применяются, а попадают
    в отчёт — решает владелец схемы. Принять их: --accept id1,id2 ...
  - Если два автора по-разному поменяли один элемент — это конфликт, в отчёте.
  - Шум, который bpmn.io и Camunda дописывают сами (отметки групп categoryValueRef,
    пустые подписи BPMNLabel, exporter), правкой не считается.

Запуск:
  python3 -I bpmn_merge.py исходная.bpmn версия1.bpmn [версия2.bpmn ...] \\
      -o собранная.bpmn --report отчёт.md [--authors "Андрей,Даниил"] [--accept id,id]
"""
import argparse
import copy
import os
import re
import sys
import xml.etree.ElementTree as ET

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
DI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
B = "{%s}" % BPMN_NS

NOISE_CHILDREN = {"categoryValueRef", "incoming", "outgoing", "flowNodeRef"}
NOISE_ATTRS = {"exporter", "exporterVersion"}
REF_ATTRS = {"sourceRef", "targetRef", "bpmnElement", "processRef", "attachedToRef",
             "default", "categoryValueRef", "calledElement_ignore"}
REF_CHILDREN = {"incoming", "outgoing", "flowNodeRef", "categoryValueRef"}

KIND_RU = {
    "task": "Блок", "userTask": "Блок (человек)", "serviceTask": "Блок (система)",
    "manualTask": "Блок", "scriptTask": "Блок", "businessRuleTask": "Блок", "sendTask": "Блок",
    "receiveTask": "Блок", "callActivity": "Вызов процесса", "subProcess": "Подпроцесс",
    "sequenceFlow": "Стрелка", "messageFlow": "Стрелка сообщения", "association": "Связь заметки",
    "textAnnotation": "Заметка", "group": "Группа", "lane": "Дорожка", "participant": "Пул",
    "exclusiveGateway": "Развилка", "parallelGateway": "Развилка (параллельная)",
    "inclusiveGateway": "Развилка", "eventBasedGateway": "Развилка по событию",
    "startEvent": "Начало", "endEvent": "Конец", "intermediateCatchEvent": "Событие",
    "intermediateThrowEvent": "Событие", "boundaryEvent": "Событие на границе",
    "category": "Категория групп", "categoryValue": "Название группы",
    "BPMNShape": "Положение", "BPMNEdge": "Линия",
}


def local(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def short(s, n=70):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def register_namespaces(paths):
    for p in paths:
        raw = open(p, encoding="utf-8").read()
        for prefix, uri in re.findall(r'xmlns:([\w-]+)="([^"]+)"', raw):
            ET.register_namespace(prefix, uri)


class Doc:
    def __init__(self, path):
        self.path = path
        self.tree = ET.parse(path)
        self.root = self.tree.getroot()
        self.reindex()

    def reindex(self):
        self.by_id, self.parent = {}, {}
        for p in self.root.iter():
            for c in p:
                self.parent[c] = p
        for el in self.root.iter():
            if el.get("id"):
                self.by_id[el.get("id")] = el
        self.di_of = {}
        for el in self.root.iter():
            if el.get("bpmnElement"):
                self.di_of.setdefault(el.get("bpmnElement"), []).append(el)

    def id_parent(self, el):
        p = self.parent.get(el)
        while p is not None and not p.get("id"):
            p = self.parent.get(p)
        return p

    def ordered_ids(self):
        return [el.get("id") for el in self.root.iter() if el.get("id")]

    def describe(self, iid):
        """«Заметка «Ответ АВ: …»» — по-человечески, с именем из смыслового элемента."""
        el = self.by_id.get(iid)
        if el is None:
            return iid
        kind = local(el.tag)
        sem = el
        if el.get("bpmnElement") and el.get("bpmnElement") in self.by_id:
            sem = self.by_id[el.get("bpmnElement")]
        name = sem.get("name") or sem.get("value") or ""
        if not name:
            t = sem.find(B + "text")
            name = t.text if t is not None and t.text else ""
        what = KIND_RU.get(local(sem.tag), local(sem.tag))
        tail = " на схеме" if sem is not el else ""
        sid = sem.get("id") or iid
        return "%s «%s»%s" % (what, short(name), tail) if name else "%s %s%s" % (what, sid, tail)


GEO = {"Bounds": ("x", "y"), "waypoint": ("x", "y")}


def find_shift(base, v):
    """Общий сдвиг всей схемы (когда холст передвинули целиком): самый частый
    сдвиг одинаковых блоков, если он у большинства."""
    deltas = {}
    n = 0
    for iid, el in v.by_id.items():
        if local(el.tag) != "BPMNShape" or iid not in base.by_id:
            continue
        a, b = base.by_id[iid].find("{*}Bounds"), el.find("{*}Bounds")
        if a is None or b is None:
            continue
        n += 1
        d = (round(float(b.get("x")) - float(a.get("x"))), round(float(b.get("y")) - float(a.get("y"))))
        deltas[d] = deltas.get(d, 0) + 1
    if not deltas:
        return (0, 0)
    d, cnt = max(deltas.items(), key=lambda kv: kv[1])
    return d if cnt * 2 > n else (0, 0)


def shift(el, dx, dy):
    """Сдвинуть координаты элемента DI и всех его частей."""
    if not (dx or dy):
        return
    for x in el.iter():
        if local(x.tag) in GEO:
            x.set("x", fmt(float(x.get("x")) + dx))
            x.set("y", fmt(float(x.get("y")) + dy))


def fmt(v):
    return str(int(v)) if float(v).is_integer() else str(round(v, 2))


def signature(el, dx=0, dy=0):
    """Значимое содержимое элемента без его детей-с-id и без шума инструментов."""
    attrs = []
    for k, v in sorted(el.attrib.items()):
        if local(k) in NOISE_ATTRS:
            continue
        attrs.append((local(k), v))
    kids = []
    for c in el:
        if c.get("id") or local(c.tag) in NOISE_CHILDREN:
            continue
        if local(c.tag) == "BPMNLabel":
            continue  # положение подписи bpmn.io и Camunda пересчитывают сами — не правка
        kids.append(child_sig(c, dx, dy))
    return (local(el.tag), tuple(attrs), " ".join((el.text or "").split()), tuple(kids))


def child_sig(c, dx=0, dy=0):
    """dx, dy — общий сдвиг версии: вычитаем, чтобы сдвиг холста не считался правкой."""
    attrs = []
    for k, v in sorted(c.attrib.items()):
        if local(c.tag) in GEO and local(k) in ("x", "y", "width", "height"):
            v = float(v) - (dx if local(k) == "x" else dy if local(k) == "y" else 0)
            v = str(round(v))
        attrs.append((local(k), v))
    kids = tuple(child_sig(x, dx, dy) for x in c if not x.get("id"))
    return (local(c.tag), tuple(attrs), " ".join((c.text or "").split()), kids)


def explain(old, new):
    """Что именно поменялось — короткими словами для отчёта."""
    _, oa, ot, ok = old
    _, na, nt, nk = new
    out = []
    oa, na = dict(oa), dict(na)
    names = {"name": "название", "value": "название", "fill": "цвет заливки", "stroke": "цвет линии",
             "background-color": None, "border-color": None, "sourceRef": "откуда", "targetRef": "куда",
             "isExpanded": "развёрнут", "isHorizontal": "горизонтальный"}
    for k in sorted(set(oa) | set(na)):
        if oa.get(k) == na.get(k) or names.get(k, k) is None:
            continue
        out.append('%s: «%s» → «%s»' % (names.get(k, k), short(oa.get(k, ""), 50) or "(пусто)",
                                        short(na.get(k, ""), 50) or "(пусто)"))
    if ot != nt:
        out.append("текст: «%s» → «%s»" % (short(ot, 50) or "(пусто)", short(nt, 50) or "(пусто)"))
    if ok != nk:
        okd = {k[0]: k for k in ok}
        nkd = {k[0]: k for k in nk}
        geo = {"Bounds", "waypoint"}
        if any(k[0] in geo for k in ok + nk) and [k for k in ok if k[0] in geo] != [k for k in nk if k[0] in geo]:
            out.append("линия проложена по-другому" if any(k[0] == "waypoint" for k in ok + nk)
                       else "перемещён или изменён размер")
        for tag in sorted((set(okd) | set(nkd)) - geo):
            if okd.get(tag) != nkd.get(tag):
                if tag in ("text", "documentation", "conditionExpression"):
                    out.append("%s: «%s» → «%s»" % ({"text": "текст", "documentation": "описание",
                                                     "conditionExpression": "условие"}[tag],
                                                    short(okd[tag][2] if tag in okd else "", 50) or "(пусто)",
                                                    short(nkd[tag][2] if tag in nkd else "", 50) or "(пусто)"))
                elif tag != "BPMNLabel":
                    out.append("изменено: %s" % tag)
    return "; ".join(out) or "изменено"


def insert_like(merged, src_doc, el, new):
    """Вставить new в объединённый документ туда же, где el лежит в версии автора."""
    p = src_doc.id_parent(el)
    if p is None or p.get("id") not in merged.by_id:
        return False
    target = merged.by_id[p.get("id")]
    # вставляем после ближайшего предыдущего соседа с id, который есть в собранной версии
    sibs = list(src_doc.parent[el]) if el in src_doc.parent else []
    pos = None
    if src_doc.parent.get(el) is p:
        before = sibs[:sibs.index(el)]
        for s in reversed(before):
            if s.get("id") and s.get("id") in merged.by_id and merged.by_id[s.get("id")] in list(target):
                pos = list(target).index(merged.by_id[s.get("id")]) + 1
                break
    if pos is None:
        pos = len(target)
    target.insert(pos, new)
    return True


def add_ref(el, tag_ns, ref):
    """Добавить ссылку-ребёнка (incoming/outgoing/flowNodeRef) в правильное место."""
    tag = local(tag_ns)
    kids = list(el)
    same = [i for i, c in enumerate(kids) if c.tag == tag_ns]
    new = ET.Element(tag_ns)
    new.text = ref
    if same:
        el.insert(same[-1] + 1, new)
    elif tag == "incoming":
        outs = [i for i, c in enumerate(kids) if local(c.tag) == "outgoing"]
        el.insert(outs[0] if outs else len(kids), new)
    elif tag == "flowNodeRef":
        cls = [i for i, c in enumerate(kids) if local(c.tag) == "childLaneSet"]
        el.insert(cls[0] if cls else len(kids), new)
    else:
        el.append(new)


def check(doc):
    """Проверка целостности: id без повторов, все ссылки ведут на существующие элементы."""
    problems = []
    seen = {}
    for el in doc.root.iter():
        i = el.get("id")
        if i:
            if i in seen:
                problems.append("повтор id %s" % i)
            seen[i] = el
    for el in doc.root.iter():
        for k, v in el.attrib.items():
            if local(k) in REF_ATTRS and v and v not in seen and local(k) != "categoryValueRef":
                problems.append("%s у %s ссылается на несуществующий %s" % (local(k), el.get("id") or local(el.tag), v))
        if local(el.tag) in REF_CHILDREN and el.text and el.text.strip() not in seen:
            problems.append("%s ссылается на несуществующий %s" % (local(el.tag), el.text.strip()))
    return problems


def merge(base_path, version_paths, authors, accept):
    register_namespaces([base_path] + version_paths)
    base = Doc(base_path)
    merged = Doc(base_path)
    versions = [Doc(p) for p in version_paths]
    base_sig = {i: signature(el) for i, el in base.by_id.items()}

    added, changes, deletions, conflicts, failed = [], {}, {}, [], []
    added_from = {}  # id -> автор

    shifts = {}
    dropped_cvr = 0
    for v, author in zip(versions, authors):
        dropped_cvr += sum(1 for el in v.root.iter() if local(el.tag) == "categoryValueRef") - \
            sum(1 for el in base.root.iter() if local(el.tag) == "categoryValueRef")
        dx, dy = find_shift(base, v)
        shifts[author] = (dx, dy)
        new_ids = []
        for iid in v.ordered_ids():
            if iid in base.by_id:
                continue
            el = v.by_id[iid]
            if iid in merged.by_id:
                if iid in added_from and signature(merged.by_id[iid]) != signature(el, dx, dy):
                    conflicts.append((iid, "%s и %s добавили разный элемент с одним id"
                                      % (added_from[iid], author), v.describe(iid)))
                continue
            new = copy.deepcopy(el)
            # шум bpmn.io (отметки групп) в новые элементы не тащим
            for c in list(new):
                if local(c.tag) == "categoryValueRef":
                    new.remove(c)
            shift(new, -dx, -dy)
            if insert_like(merged, v, el, new):
                merged.reindex()
                for x in new.iter():
                    if x.get("id"):
                        added_from[x.get("id")] = author
                        new_ids.append(x.get("id"))
                added.append((author, iid, v.describe(iid)))
            else:
                failed.append((author, iid, v.describe(iid)))
        # ссылки существующих элементов на новые (incoming/outgoing стрелок, flowNodeRef дорожек)
        new_set = set(new_ids)
        for iid, el in v.by_id.items():
            if iid in new_set or iid not in merged.by_id:
                continue
            m = merged.by_id[iid]
            have = {(c.tag, (c.text or "").strip()) for c in m}
            for c in el:
                if local(c.tag) in ("incoming", "outgoing", "flowNodeRef") and (c.text or "").strip() in new_set:
                    if (c.tag, c.text.strip()) not in have:
                        add_ref(m, c.tag, c.text.strip())
        # изменения и удаления
        for iid, bsig in base_sig.items():
            if iid not in v.by_id:
                deletions.setdefault(iid, []).append(author)
                continue
            vsig = signature(v.by_id[iid], dx, dy)
            if vsig != bsig:
                changes.setdefault(iid, []).append((author, vsig, explain(bsig, vsig), v))

    # конфликты: один элемент по-разному у разных авторов, или удалён у одного и изменён у другого
    for iid, lst in changes.items():
        if len({x[1] for x in lst}) > 1:
            conflicts.append((iid, "по-разному изменили: " + ", ".join(x[0] for x in lst), base.describe(iid)))
        if iid in deletions:
            conflicts.append((iid, "%s удалил(а), %s изменил(а)" % (", ".join(deletions[iid]),
                                                                      ", ".join(x[0] for x in lst)),
                              base.describe(iid)))
    conflict_ids = {c[0] for c in conflicts}

    # принятые правки
    applied = []
    for iid in accept:
        targets = [iid] + [d.get("id") for d in base.di_of.get(iid, []) if d.get("id")]
        for t in targets:
            if t in conflict_ids:
                failed.append(("—", t, "конфликт — сначала решите, чью версию брать"))
                continue
            if t in changes:
                author, _, _, v = changes[t][0]
                src, dst = v.by_id[t], merged.by_id[t]
                dst.attrib.clear()
                dst.attrib.update(src.attrib)
                dst.text = src.text
                keep = [c for c in dst if c.get("id")]
                for c in list(dst):
                    dst.remove(c)
                sdx, sdy = shifts[author]
                for c in src:
                    if not c.get("id"):
                        cc = copy.deepcopy(c)
                        shift(cc, -sdx, -sdy)
                        dst.append(cc)
                for c in keep:
                    dst.append(c)
                applied.append((t, "изменение от " + author))
            elif t in deletions:
                el = merged.by_id.get(t)
                if el is None:
                    continue
                users = [x for x in merged.root.iter()
                         if any(v == t for k, v in x.attrib.items() if local(k) in ("sourceRef", "targetRef"))]
                if users:
                    failed.append(("—", t, "не удалён: на него ссылаются %s" % ", ".join(u.get("id") for u in users)))
                    continue
                for di in merged.di_of.get(t, []):
                    merged.parent[di].remove(di)
                for x in list(merged.root.iter()):
                    for c in list(x):
                        if local(c.tag) in REF_CHILDREN and (c.text or "").strip() == t:
                            x.remove(c)
                merged.parent[el].remove(el)
                applied.append((t, "удаление от " + ", ".join(deletions[t])))
            merged.reindex()

    return {"base": base, "merged": merged, "added": added, "shifts": shifts, "dropped_cvr": max(dropped_cvr, 0), "changes": changes,
            "deletions": deletions, "conflicts": conflicts, "failed": failed,
            "applied": applied, "problems": check(merged)}


def report(r, base_path, version_paths, authors, out_path):
    base = r["base"]
    L = ["# Сборка версий BPMN", "",
         "- Исходная: `%s`" % os.path.basename(base_path)]
    for p, a in zip(version_paths, authors):
        L.append("- Версия «%s»: `%s`" % (a, os.path.basename(p)))
    L.append("- Собранная: `%s`" % os.path.basename(out_path))
    n_sem = len([x for x in r["added"] if not r["merged"].by_id[x[1]].get("bpmnElement")])
    L += ["", "**Итог:** добавлено %d, изменений на решение %d, удалений на решение %d, конфликтов %d, принято %d."
          % (n_sem, len(r["changes"]), len(r["deletions"]), len(r["conflicts"]), len(r["applied"]))]
    sem_base = [i for i, el in base.by_id.items() if not el.get("bpmnElement") and local(el.tag) not in
                ("definitions", "BPMNDiagram", "BPMNPlane")]
    for a in {x for lst in r["deletions"].values() for x in lst}:
        gone = [i for i in sem_base if a in r["deletions"].get(i, [])]
        if len(gone) * 2 > len(sem_base):
            L += ["", "## ⚠ У «%s» пропала большая часть элементов (%d из %d)" % (a, len(gone), len(sem_base)), "",
                  "Похоже, схему перерисовали с новыми id. Сборка по id тут не работает: результат не выкладывать,"
                  " попросить автора править исходный файл, не меняя id существующих блоков."]
    if r.get("dropped_cvr"):
        L += ["", "Служебные отметки «блок лежит в группе» (categoryValueRef), которые bpmn.io ставит сам, в собранную "
              "версию не переносятся (%d шт.): на схеме их не видно, группы и блоки на месте." % r["dropped_cvr"]]
    for a, (dx, dy) in r["shifts"].items():
        if dx or dy:
            L += ["", "У «%s» вся схема сдвинута на (%d, %d) — сдвиг учтён, правкой не считается." % (a, dx, dy)]
    if r["problems"]:
        L += ["", "## ⚠ Собранный файл не цельный", ""] + ["- " + p for p in r["problems"]]
    if r["conflicts"]:
        L += ["", "## Конфликты — решить, чью версию брать", ""]
        L += ["- `%s` %s — %s" % (i, d, why) for i, why, d in r["conflicts"]]

    # изменения: сначала смысловые, потом положение на схеме
    sem, geo = [], []
    for iid, lst in r["changes"].items():
        for author, _, why, v in lst:
            row = "- `%s` %s — %s (%s)" % (iid, base.describe(iid), why, author)
            (geo if base.by_id[iid].get("bpmnElement") else sem).append(row)
    if sem:
        L += ["", "## Изменения — решить (в собранную версию не внесены)", ""] + sem
    if geo:
        L += ["", "## Положение и цвет на схеме — решить", ""] + geo
    # чертёж удалённого элемента отдельной строкой не показываем
    dels = {i: a for i, a in r["deletions"].items()
            if not (base.by_id[i].get("bpmnElement") in r["deletions"])}
    if dels:
        L += ["", "## Удалено у автора — решить (в собранной версии осталось)", ""]
        L += ["- `%s` %s (%s)" % (i, base.describe(i), ", ".join(a)) for i, a in dels.items()]
    if r["applied"]:
        L += ["", "## Принято по --accept", ""] + ["- `%s` — %s" % a for a in r["applied"]]
    if r["failed"]:
        L += ["", "## Не получилось", ""] + ["- `%s` %s (%s)" % (i, d, a) for a, i, d in r["failed"]]
    sem_added = [x for x in r["added"] if not r["merged"].by_id[x[1]].get("bpmnElement")]
    if sem_added:
        L += ["", "## Добавлено автоматически", ""]
        for author, iid, d in sem_added:
            L.append("- `%s` %s (%s)" % (iid, d, author))
        L.append("")
        L.append("Вместе с ними — их положение на схеме (%d)." % (len(r["added"]) - len(sem_added)))
    if r["changes"] or r["deletions"]:
        L += ["", "Принять правку или удаление: запустить сборку ещё раз с `--accept id1,id2`."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("base", help="исходная версия — общий предок")
    ap.add_argument("versions", nargs="+", help="версии авторов")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--authors", default="", help="имена авторов через запятую, по порядку версий")
    ap.add_argument("--accept", default="", help="id элементов, чьи изменения или удаления принять")
    a = ap.parse_args()
    authors = [x.strip() for x in a.authors.split(",") if x.strip()]
    authors += [os.path.basename(p) for p in a.versions[len(authors):]]
    accept = [x.strip() for x in a.accept.split(",") if x.strip()]

    r = merge(a.base, a.versions, authors, accept)
    r["merged"].tree.write(a.out, encoding="UTF-8", xml_declaration=True)
    with open(a.report, "w", encoding="utf-8") as f:
        f.write(report(r, a.base, a.versions, authors, a.out))
    n_sem = len([x for x in r["added"] if not r["merged"].by_id[x[1]].get("bpmnElement")])
    print("Добавлено: %d (и %d положений на схеме) | изменений: %d | удалений: %d | конфликтов: %d | принято: %d | проблем целостности: %d"
          % (n_sem, len(r["added"]) - n_sem, len(r["changes"]), len(r["deletions"]), len(r["conflicts"]),
             len(r["applied"]), len(r["problems"])))
    if r["problems"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
