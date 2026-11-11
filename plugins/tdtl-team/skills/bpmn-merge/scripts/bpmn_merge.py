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
import io
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


STD_PREFIXES = (("bpmn", BPMN_NS), ("bpmndi", DI_NS), ("dc", "http://www.omg.org/spec/DD/20100524/DC"),
                ("di", "http://www.omg.org/spec/DD/20100524/DI"))


def register_namespaces(paths):
    for p in paths:
        with open(p, encoding="utf-8") as f:
            raw = f.read()
        for prefix, uri in re.findall(r'xmlns:([\w-]+)="([^"]+)"', raw):
            if re.fullmatch(r"ns\d+", prefix):
                continue  # так пишет сам ElementTree; register_namespace такие префиксы не принимает
            ET.register_namespace(prefix, uri)
    for prefix, uri in STD_PREFIXES:  # привычные префиксы BPMN — последними, чтобы победили
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
        # в какой дорожке блок: самая вложенная (поддорожки идут в документе после своей дорожки)
        self.lane_of, self.lane_name = {}, {}
        for el in self.root.iter(B + "lane"):
            self.lane_name[el.get("id")] = el.get("name") or el.get("id")
            for c in el:
                if local(c.tag) == "flowNodeRef" and (c.text or "").strip():
                    self.lane_of[c.text.strip()] = el.get("id")

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


LANE = "__lane"  # дорожка блока — в подписи блока: перенос между дорожками — правка блока, а не дорожек


def signature(el, dx=0, dy=0, lane=None):
    """Значимое содержимое элемента без его детей-с-id и без шума инструментов."""
    attrs = []
    for k, v in sorted(el.attrib.items()):
        if local(k) in NOISE_ATTRS:
            continue
        attrs.append((local(k), v))
    if lane:
        attrs.append((LANE, lane))
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


def explain(old, new, lane_names=None):
    """Что именно поменялось — короткими словами для отчёта. lane_names: id дорожки -> название."""
    _, oa, ot, ok = old
    _, na, nt, nk = new
    out = []
    oa, na = dict(oa), dict(na)
    names = {"name": "название", "value": "название", "fill": "цвет заливки", "stroke": "цвет линии",
             "background-color": None, "border-color": None, "sourceRef": "откуда", "targetRef": "куда",
             "isExpanded": "развёрнут", "isHorizontal": "горизонтальный"}
    if oa.get(LANE) != na.get(LANE):
        ln = lane_names or {}
        out.append("дорожка: «%s» → «%s»" % (ln.get(oa.get(LANE), oa.get(LANE)) or "(нет)",
                                             ln.get(na.get(LANE), na.get(LANE)) or "(нет)"))
    for k in sorted(set(oa) | set(na)):
        if k == LANE or oa.get(k) == na.get(k) or names.get(k, k) is None:
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


HEAD_TAGS = {"documentation", "extensionElements", "auditing", "monitoring", "text"}
BLOCK_ATTRS = REF_ATTRS - {"bpmnElement", "calledElement_ignore"}
# части элемента — не «вложенные элементы»: удаляются вместе с ним
PART_TAGS = {"ioSpecification", "property", "dataInput", "dataOutput", "inputSet", "outputSet", "conditionExpression",
             "documentation", "extensionElements", "resourceRole", "performer", "humanPerformer", "potentialOwner"}


def is_part(tag):
    return tag in PART_TAGS or tag.endswith("EventDefinition") or tag.endswith("LoopCharacteristics")


def lanes_with(doc, t):
    return {el.get("id") for el in doc.root.iter(B + "lane")
            if any(local(c.tag) == "flowNodeRef" and (c.text or "").strip() == t for c in el)}


def accept_change(merged, t, v, sh, conflict_ids=()):
    """Принять правку элемента t из версии автора v. Пусто — принята; иначе причина, и ничего не изменено.
    Ссылки-дети (incoming, outgoing, flowNodeRef) остаются из собранной: их могли добавить другой автор или сама сборка.
    Принятый конец стрелки перевешивает incoming/outgoing; дорожки блока становятся такими, как у автора
    (ссылка снимается со всех дорожек собранной, где блока нет у автора, в том числе с дорожки, которую он удалил).
    Дорожка, куда перенесён блок, должна быть дорожкой в собранной и не под конфликтом — иначе правка не применяется."""
    src, dst = v.by_id[t], merged.by_id[t]
    want, have = lanes_with(v, t), lanes_with(merged, t)
    missing = [ln for ln in sorted(want - have)
               if ln not in merged.by_id or local(merged.by_id[ln].tag) != "lane" or ln in conflict_ids]
    if missing:
        return "дорожки %s, куда перенесён блок, нет в собранной версии" % ", ".join(missing)
    ns = dst.tag[:dst.tag.index("}") + 1] if "}" in dst.tag else ""
    old_ends = {a: dst.get(a) for a in ("sourceRef", "targetRef")}
    dst.attrib.clear()
    dst.attrib.update(src.attrib)
    dst.text = src.text
    refs = [c for c in dst if not c.get("id") and local(c.tag) in REF_CHILDREN]
    kids = [c for c in dst if c.get("id")]
    plain = []
    for c in src:
        if not c.get("id") and local(c.tag) not in REF_CHILDREN:
            cc = copy.deepcopy(c)
            shift(cc, -sh[0], -sh[1])
            plain.append(cc)
    n = 0
    while n < len(plain) and local(plain[n].tag) in HEAD_TAGS:
        n += 1
    for c in list(dst):
        dst.remove(c)
    for c in plain[:n] + refs + plain[n:] + kids:
        dst.append(c)
    if not len(dst) and not (dst.text or "").strip():
        dst.text = None   # детей не осталось — отступ перед ними не нужен
    if local(dst.tag) == "sequenceFlow":
        for attr, ref in (("sourceRef", "outgoing"), ("targetRef", "incoming")):
            old, new = old_ends[attr], dst.get(attr)
            if old == new:
                continue
            if old in merged.by_id:
                for c in list(merged.by_id[old]):
                    if local(c.tag) == ref and (c.text or "").strip() == t:
                        merged.by_id[old].remove(c)
            if new in merged.by_id and t not in [(c.text or "").strip() for c in merged.by_id[new] if local(c.tag) == ref]:
                add_ref(merged.by_id[new], ns + ref, t)
    for ln in have - want:
        for c in list(merged.by_id[ln]):
            if local(c.tag) == "flowNodeRef" and (c.text or "").strip() == t:
                merged.by_id[ln].remove(c)
    for ln in sorted(want - have):
        add_ref(merged.by_id[ln], ns + "flowNodeRef", t)
    return ""


def delete_blockers(merged, t):
    """Почему элемент t нельзя удалить: на него ссылаются, на нём держится чертёж или внутри него есть элементы.
    Пусто — можно."""
    el = merged.by_id.get(t)
    if el is None:
        return ""
    inside = {id(x) for x in el.iter()}
    users = ["%s (%s)" % (x.get("id") or local(x.tag), local(k)) for x in merged.root.iter() if id(x) not in inside
             for k, v in x.attrib.items() if local(k) in BLOCK_ATTRS and v == t]
    planes = [d.get("id") or local(d.tag) for d in merged.di_of.get(t, []) if local(d.tag) in ("BPMNPlane", "BPMNDiagram")]
    nested = []

    def walk(n):
        for c in n:
            if is_part(local(c.tag)):
                continue
            if c.get("id"):
                nested.append(c.get("id"))
            walk(c)
    walk(el)
    lane_refs = [(c.text or "").strip() for c in el if local(c.tag) == "flowNodeRef"] if local(el.tag) == "lane" else []
    why = []
    if users:
        why.append("на него ссылаются " + ", ".join(users))
    if planes:
        why.append("на нём держится чертёж " + ", ".join(planes))
    if nested:
        why.append("внутри есть элементы " + ", ".join(nested))
    if lane_refs:
        why.append("в дорожке блоки " + ", ".join(lane_refs))
    return "; ".join(why)


def merge(base_path, version_paths, authors, accept):
    accept = list(dict.fromkeys(accept))   # повтор id в --accept — один раз
    register_namespaces([base_path] + version_paths)
    base = Doc(base_path)
    merged = Doc(base_path)
    versions = [Doc(p) for p in version_paths]
    base_sig = {i: signature(el, lane=base.lane_of.get(i)) for i, el in base.by_id.items()}

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
            # новая дорожка приходит без ссылок на блоки, которые были в исходной (их перенос — правка блока, на решение)
            # и которые уже добавил другой автор (блок остаётся в дорожке того, кто добавил первым)
            for ln in new.iter(B + "lane"):
                for c in list(ln):
                    ref = (c.text or "").strip()
                    if local(c.tag) == "flowNodeRef" and (ref in base.by_id or added_from.get(ref, author) != author):
                        ln.remove(c)
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
            vsig = signature(v.by_id[iid], dx, dy, lane=v.lane_of.get(iid))
            if vsig != bsig:
                changes.setdefault(iid, []).append((author, vsig, explain(bsig, vsig, {**base.lane_name, **v.lane_name}), v))

    # конфликты: один элемент по-разному у разных авторов, или удалён у одного и изменён у другого
    for iid, lst in changes.items():
        if len({x[1] for x in lst}) > 1:
            conflicts.append((iid, "по-разному изменили: " + ", ".join(x[0] for x in lst), base.describe(iid)))
        if iid in deletions:
            conflicts.append((iid, "%s удалил(а), %s изменил(а)" % (", ".join(deletions[iid]),
                                                                      ", ".join(x[0] for x in lst)),
                              base.describe(iid)))
    conflict_ids = {c[0] for c in conflicts}

    # принятые правки: сначала все изменения, потом удаления в порядке --accept (вложенное — раньше того, во что вложено).
    # Только названные id: чертёж Task_di принимается, только если назван сам (положение — отдельная строка отчёта).
    applied = []
    todo_del = []
    for t in accept:
        if t in conflict_ids:
            failed.append(("—", t, "конфликт — сначала решите, чью версию брать"))
        elif t in changes:
            author, vsig, _, v = changes[t][0]
            why = accept_change(merged, t, v, shifts[author], conflict_ids)
            if why:
                failed.append(("—", t, "правка не применена: " + why))
                continue
            applied.append((t, "изменение от " + author))
            merged.reindex()
        elif t in deletions:
            todo_del.append(t)
        else:
            failed.append(("—", t, "у этого id нет правки или удаления на решение — проверьте id"))
    for t in todo_del:
        why = delete_blockers(merged, t)
        if why:
            failed.append(("—", t, "не удалён: " + why))
            continue
        el = merged.by_id.get(t)
        if el is None:
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

    # -o и --report — только новые файлы: перепутанные аргументы не должны затереть исходную или версию автора
    # Всё — до сборки, чтобы сбой не случился посередине записи (схема записана, отчёт нет).
    def same(x, y):
        return os.path.realpath(x) == os.path.realpath(y) or (
            os.path.exists(x) and os.path.exists(y) and os.path.samefile(x, y))   # жёсткая ссылка, регистр букв

    for flag, path in (("-o", a.out), ("--report", a.report)):
        if path.endswith(os.sep) or (os.altsep and path.endswith(os.altsep)):
            ap.error("%s указывает на папку %s, а нужен файл. Ничего не записано." % (flag, path))
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            ap.error("%s: папки %s нет. Ничего не записано." % (flag, folder))
        if os.path.isdir(path):
            ap.error("%s указывает на папку %s, а нужен файл. Ничего не записано." % (flag, path))
        for p in [a.base] + a.versions:
            if same(path, p):
                ap.error("%s указывает на входной файл %s — он был бы перезаписан. Ничего не записано." % (flag, p))
    if same(a.out, a.report):
        ap.error("-o и --report указывают на один файл %s. Ничего не записано." % a.out)

    r = merge(a.base, a.versions, authors, accept)
    text = report(r, a.base, a.versions, authors, a.out)   # отчёт строится до записи: сбой в нём ничего не пишет
    write_both(r["merged"].tree, a.out, text, a.report)
    n_sem = len([x for x in r["added"] if not r["merged"].by_id[x[1]].get("bpmnElement")])
    print("Добавлено: %d (и %d положений на схеме) | изменений: %d | удалений: %d | конфликтов: %d | принято: %d | проблем целостности: %d"
          % (n_sem, len(r["added"]) - n_sem, len(r["changes"]), len(r["deletions"]), len(r["conflicts"]),
             len(r["applied"]), len(r["problems"])))
    for who, iid, why in r["failed"]:
        print("Не получилось: %s — %s" % (iid, why))
    if r["problems"]:
        sys.exit(1)


def write_both(tree, out, text, rep):
    """Оба файла сначала целиком в памяти, запись на диск — последним шагом: сбой при сборке или отчёте
    ничего не пишет. Временных файлов и удалений нет."""
    buf = io.BytesIO()
    tree.write(buf, encoding="UTF-8", xml_declaration=True)
    data, rep_data = buf.getvalue(), text.encode("utf-8")
    with open(out, "wb") as f:
        f.write(data)
    with open(rep, "wb") as f:
        f.write(rep_data)


if __name__ == "__main__":
    main()
