"""BPMN 2.0 (.bpmn) -> код для коннектора Figma (use_figma), который строит схему в FigJam
или обновляет уже перенесённую на месте, по id элементов. Основа — скрипт Даниила (T-0142, 05.11.2026).

Запуск (ставить ничего не нужно):
  python3 bpmn_to_figjam.py схема.bpmn out.js --title "XP Название · как будет" (--page "Наиль" | --section ID) [--groups ID1,ID2 | --x0 N --x1 N] [--scale 1.5] [--force]
  python3 bpmn_to_figjam.py схема.bpmn --list-groups      # этапы (группы) схемы, чтобы переносить частями

Код из out.js передают в use_figma без правок. Он:
- рисует фигуры по координатам файла (x1.5), стрелки — коннекторами FigJam, они тянутся за блоками;
- кладёт схему на страницу --page (коннектор иначе начинает с первой — «Общий»), находит секцию по --section
  или по заголовку на этой странице и обновляет её (секцию с тем же заголовком, нарисованную не скриптом, не трогает): есть в .bpmn — правит узел на месте,
  нет на доске — создаёт, пропал из .bpmn — удаляет; листочки и фигуры, которые люди добавили сами, не трогает;
- сдвиг всей схемы на холсте (как у bpmn.io) гасит, чтобы блоки и комментарии рядом с ними остались на местах;
- возвращает, какие блоки сдвинулись и какие удалены: комментарии FigJam привязаны к точке холста, не к блоку.
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bpmn_model import parse  # noqa: E402

S, P, T, ST = 1.5, 40, 160, 45   # масштаб по умолчанию, отступ слева, место под заголовок, ширина полосы подписей дорожек
LIMIT = 49000                    # предел длины кода для use_figma (50 000 символов) с запасом


def prune(d):
    return {k: v for k, v in d.items() if v not in (None, "")}


def groups_of(m):
    return [s for s in m["shapes"] if s["k"] == "group"]


def build(src, title, x0=None, x1=None, groups=None, section=None, force=False, scale=S, page=None):
    if not page and not section:
        raise SystemExit("Укажите, куда класть схему: --page \"название страницы\" (черновик — на странице автора, D-0026) "
                         "или --section <id> из прошлого ответа")
    if not scale > 0:
        raise SystemExit("--scale должен быть больше нуля")
    S = scale
    m = parse(src)
    by_id = {s["id"]: s for s in m["shapes"]}
    if groups:
        miss = [g for g in groups if g not in by_id or by_id[g]["k"] != "group"]
        if miss:
            raise SystemExit("Нет таких групп: %s. Список: --list-groups" % ", ".join(miss))
        x0 = min(by_id[g]["b"][0] for g in groups)
        x1 = max(by_id[g]["b"][0] + by_id[g]["b"][2] for g in groups)
    body = [s for s in m["shapes"] if s["k"] not in ("participant", "lane")] or m["shapes"]
    if x0 is None:
        x0 = min(s["b"][0] for s in body)
    if x1 is None:
        x1 = max(s["b"][0] + s["b"][2] for s in body)
    pools = [s for s in m["shapes"] if s["k"] == "participant"] or m["shapes"]
    y0 = min(s["b"][1] for s in pools)

    def xy(x, y):
        return round((x - x0) * S + P + ST), round((y - y0) * S + T)   # целые px: на доске разница < 1 px, а код короче

    def z(v):
        return round(v * S)

    refs = {}
    for el in ET.parse(src).getroot().iter():
        if el.get("sourceRef") and el.get("targetRef") and el.get("id"):
            refs[el.get("id")] = (el.get("sourceRef"), el.get("targetRef"))

    items, B = [], {}
    for s in m["shapes"]:
        x, y, w, h = s["b"]
        B[s["id"]] = s["b"]
        if s["k"] == "participant":
            continue
        if s["k"] == "lane":
            items.append(prune(dict(t="lane", id=s["id"], n=s["n"], x=P, y=xy(x0, y)[1], w=ST + z(x1 - x0), h=z(h))))
            continue
        if not (x0 <= x + w / 2 <= x1):
            continue
        nx, ny = xy(x, y)
        it = dict(id=s["id"], n=s["n"], k=s["k"], x=nx, y=ny, w=z(w), h=z(h),
                  fill=s.get("fill"), stroke=s.get("stroke"), ev=s.get("ev"))
        if s.get("lb"):
            it["lx"], it["ly"] = xy(s["lb"][0], s["lb"][1])
            it["lw"] = z(s["lb"][2])
        items.append(prune(it))
    if not any(i.get("t") != "lane" for i in items):
        raise SystemExit("В выбранном окне схемы нет ни одного блока — переносить нечего (проверьте --groups или --x0/--x1)")

    def side(pt, b):
        x, y, w, h = b
        d = {"LEFT": abs(pt[0] - x), "RIGHT": abs(pt[0] - x - w), "TOP": abs(pt[1] - y), "BOTTOM": abs(pt[1] - y - h)}
        k = min(d, key=d.get)
        return k if d[k] <= 12 else "AUTO"

    ids = {i["id"] for i in items}
    edges = []
    for e in m["edges"]:
        st = refs.get(e["id"])
        if st and st[0] in ids and st[1] in ids:
            edges.append(prune(dict(id=e["id"], n=e["n"], k=e["k"], s=st[0], t=st[1],
                                    ms=side(e["p"][0], B[st[0]]), me=side(e["p"][-1], B[st[1]]))))
    ids_all = [i["id"] for i in items]
    pfx = os.path.commonprefix(ids_all)
    pfx = pfx[:pfx.rfind("_") + 1]   # общий префикс id (BRK-TOBE_): узлы старой выкладки без него тоже узнаются
    data = prune(dict(title=title, page=page, sectionId=section, S=S, pfx=pfx, ST=ST, force=force or None,
                      W=round(z(x1 - x0) + ST + 2 * P), H=round(max(i["y"] + i["h"] for i in items) + P),
                      items=items, edges=edges))
    with open(os.path.join(HERE, "figjam_tpl.js"), encoding="utf-8") as f:
        tpl = f.read()
    # строки-комментарии и отступы коннектору не нужны, а место в пределе длины занимают
    tpl = "\n".join(l.strip() for l in tpl.splitlines() if l.strip() and not l.strip().startswith("//"))
    js = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    shapes = sum(1 for i in items if i.get("t") != "lane")
    return js, shapes, sum(1 for i in items if i.get("t") == "lane"), len(edges)


def main():
    ap = argparse.ArgumentParser(description="BPMN -> код use_figma для FigJam")
    ap.add_argument("src")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--title")
    ap.add_argument("--groups", help="id групп-этапов через запятую: перенести только их")
    ap.add_argument("--x0", type=float)
    ap.add_argument("--x1", type=float)
    ap.add_argument("--page", help="страница доски (название или id), куда класть схему; черновик — на странице автора")
    ap.add_argument("--section", help="id секции на доске (без него ищется по заголовку на странице --page)")
    ap.add_argument("--scale", type=float, default=S,
                    help="масштаб схемы (по умолчанию %s); другой масштаб на уже перенесённой секции — стоп без --force" % S)
    ap.add_argument("--force", action="store_true", help="разрешить другой масштаб, чем в прошлый раз")
    ap.add_argument("--list-groups", action="store_true")
    a = ap.parse_args()
    if a.list_groups:
        for g in sorted(groups_of(parse(a.src)), key=lambda s: s["b"][0]):
            print("%s | x %d–%d | %s" % (g["id"], g["b"][0], g["b"][0] + g["b"][2], (g["n"] or "").replace("\n", " ")))
        return
    if not a.out or not a.title:
        ap.error("нужны out.js и --title")
    js, shapes, lanes, edges = build(a.src, a.title, a.x0, a.x1,
                                     a.groups.split(",") if a.groups else None, a.section, a.force, a.scale, a.page)
    if len(js) > LIMIT:
        print("Код длиннее, чем принимает коннектор: %d из %d символов. Переносите по частям — по этапам:\n"
              "  --groups ID1,ID2 (список: --list-groups), у каждой части свой --title." % (len(js), LIMIT))
        sys.exit(2)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(js)
    print("Готово: %s | блоков: %d | дорожек: %d | стрелок: %d | длина кода: %d" % (a.out, shapes, lanes, edges, len(js)))


if __name__ == "__main__":
    main()
