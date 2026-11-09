"""BPMN 2.0 (.bpmn) -> SVG, который перетаскивают в Figma Design как редактируемые слои.

Зачем: перенос без коннектора Figma и без платных плагинов. Координаты берутся
из файла (DI), поэтому один .bpmn всегда даёт одну и ту же картинку.
Заметки (вопросы/ответы) — полным текстом, «Вопрос …:» / «Ответ …:» жирным;
группы — пунктирной рамкой без заливки; слова в подписях не рвутся.

Каждый элемент — группа <g id="id из BPMN">: в Figma слой называется так же,
по этому id потом сравниваем и собираем версии.

Запуск:
  python3 -I bpmn_to_svg.py вход.bpmn выход.svg --title "BRK-TOBE Процессы ХРВ · как будет"

Шрифт — Noto Sans (есть в Figma). Ширина букв берётся из таблицы
noto_sans_widths.json рядом со скриптом, поэтому ничего ставить не нужно:
работает на macOS, Windows и Linux с обычным Python 3.
"""
import argparse
import json
import math
import os
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bpmn_model import check_out, parse  # noqa: E402

FONT = "Noto Sans"
with open(os.path.join(HERE, "noto_sans_widths.json"), encoding="utf-8") as _f:
    _W = json.load(_f)
WIDTHS = {False: _W["regular"], True: _W["bold"]}
UNKNOWN = {False: _W["regular"]["о"], True: _W["bold"]["о"]}  # незнакомый знак — как «о»
INK, LINE, MUTED, WHITE = "#1f2933", "#52606d", "#7b8794", "#ffffff"
NOTE_FILL = {"q": "#fff3bf", "a": "#d3f9d8", "c": "#dbe4ff"}
TASKS = {"task", "userTask", "serviceTask", "manualTask", "scriptTask", "businessRuleTask",
         "sendTask", "receiveTask", "callActivity", "subProcess", "transaction"}
LH = 1.3  # межстрочный интервал

def width(s, size, bold=False):
    table, unknown = WIDTHS[bold], UNKNOWN[bold]
    return sum(table.get(ch, unknown) for ch in s) * size / 1000


def wrap(s, w, size, bold=False):
    """Перенос по словам. Слово длиннее строки не рвём — строка станет шире."""
    lines = []
    for para in s.split("\n"):
        cur = ""
        for word in para.split():
            test = word if not cur else cur + " " + word
            if cur and width(test, size, bold) > w:
                lines.append(cur)
                cur = word
            else:
                cur = test
        lines.append(cur)
    return lines


def text_block(lines, x, y, size, anchor="middle", bold=False, color=INK, bold_prefix=0):
    """Многострочный текст: x — центр (или левый край при anchor=start), y — верх блока."""
    out = ['<text font-family="%s" font-size="%s"%s fill="%s" text-anchor="%s">'
           % (FONT, size, ' font-weight="700"' if bold else "", color, anchor)]
    for i, line in enumerate(lines):
        base = y + size * 1.02 + i * size * LH
        if i == 0 and bold_prefix:
            # Figma теряет координаты у вложенных tspan — только соседние, у каждого свои x и y
            head, rest = line[:bold_prefix], line[bold_prefix:]
            out.append('<tspan x="%.1f" y="%.1f" font-weight="700">%s</tspan>' % (x, base, escape(head)))
            if rest:
                out.append('<tspan x="%.1f" y="%.1f">%s</tspan>'
                           % (x + width(head, size, True), base, escape(rest)))
        else:
            out.append('<tspan x="%.1f" y="%.1f">%s</tspan>' % (x, base, escape(line) or " "))
    out.append("</text>")
    return "".join(out)


def block_height(n, size):
    return n * size * LH


def fitted(name, w, h):
    """Подпись внутри блока: уменьшаем шрифт, пока не влезет."""
    for size in (12, 11, 10, 9, 8):
        lines = wrap(name, w, size)
        if max(width(l, size) for l in lines) <= w + 0.5 and block_height(len(lines), size) <= h:
            break
    return lines, size


def arrow_head(p0, p1, length=10, half=4):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    d = math.hypot(dx, dy) or 1
    ux, uy = dx / d, dy / d
    bx, by = p1[0] - ux * length, p1[1] - uy * length
    return "%.1f,%.1f %.1f,%.1f %.1f,%.1f" % (p1[0], p1[1], bx - uy * half, by + ux * half,
                                              bx + uy * half, by - ux * half)


ICONS = {
    "user": '<circle cx="8" cy="5" r="3" fill="none" stroke="%s" stroke-width="1.3"/>'
            '<path d="M2.5 15c0-3.2 2.4-5.2 5.5-5.2s5.5 2 5.5 5.2" fill="none" stroke="%s" stroke-width="1.3"/>' % (INK, INK),
    "service": '<circle cx="8" cy="8" r="2.4" fill="none" stroke="%s" stroke-width="1.3"/>'
               '<circle cx="8" cy="8" r="4.6" fill="none" stroke="%s" stroke-width="1.3"/>'
               '<path d="M8 1.5v2.3M8 12.2v2.3M1.5 8h2.3M12.2 8h2.3M3.4 3.4l1.6 1.6M11 11l1.6 1.6M3.4 12.6L5 11M11 5l1.6-1.6" '
               'stroke="%s" stroke-width="1.3"/>' % (INK, INK, INK),
    "timer": '<circle cx="8" cy="8" r="6.5" fill="#fff" stroke="%s" stroke-width="1.2"/>'
             '<path d="M8 3.5V8l3 2" fill="none" stroke="%s" stroke-width="1.2"/>' % (INK, INK),
    "message": '<rect x="1.5" y="3.5" width="13" height="9" fill="#fff" stroke="%s" stroke-width="1.2"/>'
               '<path d="M1.5 3.5L8 8.5l6.5-5" fill="none" stroke="%s" stroke-width="1.2"/>' % (INK, INK),
    "signal": '<path d="M8 2l6.5 11.5h-13z" fill="none" stroke="%s" stroke-width="1.2"/>' % INK,
    "error": '<path d="M2 14l3-10 4 6 5-7-3 11-4-6z" fill="none" stroke="%s" stroke-width="1.2"/>' % INK,
}


def icon(name, x, y, size):
    s = size / 16
    return '<g transform="translate(%.1f %.1f) scale(%.3f)">%s</g>' % (x, y, s, ICONS[name])


class Svg:
    def __init__(self, model, top=0):
        # top — место под заголовок: схема сдвигается вниз, координаты без минусов
        self.ox, self.oy = model["origin"][0], model["origin"][1] - top

    def X(self, v):
        return v - self.ox

    def Y(self, v):
        return v - self.oy

    def label(self, it, cx, cy, below, size=11):
        if not it.get("n"):
            return ""
        if it.get("lb"):
            lx, ly, lw, _ = it["lb"]
            lines = wrap(it["n"], lw, size)
            return text_block(lines, self.X(lx) + lw / 2, self.Y(ly), size)
        lines = wrap(it["n"], 120, size)
        top = cy + 4 if below else cy - block_height(len(lines), size) - 4
        return text_block(lines, cx, top, size)

    def edge(self, it):
        pts = [(self.X(x), self.Y(y)) for x, y in it["p"]]
        k = it["k"]
        color = it.get("stroke") or (LINE if k == "sequenceFlow" else MUTED)
        dash = ""
        if k == "association" or k.startswith("data"):
            dash = ' stroke-dasharray="2 4"'
        if k == "messageFlow":
            dash = ' stroke-dasharray="8 5"'
        sw = 1.5 if k == "sequenceFlow" else 1.2
        out = ['<polyline points="%s" fill="none" stroke="%s" stroke-width="%s" stroke-linejoin="round"%s/>'
               % (" ".join("%.1f,%.1f" % p for p in pts), color, sw, dash)]
        if k in ("sequenceFlow", "messageFlow") or k.startswith("data") or it.get("dir") in ("One", "Both"):
            out.append('<polygon points="%s" fill="%s"/>' % (arrow_head(pts[-2], pts[-1]), color))
        if it.get("dir") == "Both":
            out.append('<polygon points="%s" fill="%s"/>' % (arrow_head(pts[1], pts[0]), color))
        if k == "messageFlow":
            out.append('<circle cx="%.1f" cy="%.1f" r="3.5" fill="#fff" stroke="%s"/>' % (pts[0][0], pts[0][1], color))
        if it.get("n"):
            if it.get("lb"):
                lx, ly, lw, _ = it["lb"]
                out.append(text_block(wrap(it["n"], lw, 10), self.X(lx) + lw / 2, self.Y(ly), 10))
            else:
                best, mx, my = 0, pts[0][0], pts[0][1]
                for a, b in zip(pts, pts[1:]):
                    ln = math.hypot(b[0] - a[0], b[1] - a[1])
                    if ln > best:
                        best, mx, my = ln, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                lines = wrap(it["n"], 120, 10)
                out.append(text_block(lines, mx, my - block_height(len(lines), 10) - 3, 10))
        return "".join(out)

    def shape(self, it):
        bx, by, w, h = it["b"]
        x, y = self.X(bx), self.Y(by)
        k, name = it["k"], it.get("n", "")
        stroke = it.get("stroke") or INK
        fill = it.get("fill")
        o = []
        if k in ("participant", "lane"):
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="%s" stroke-width="%s"/>'
                     % (x, y, w, h, fill or "none", stroke, 2 if k == "participant" else 1))
            if name:
                o.append('<rect x="%.1f" y="%.1f" width="30" height="%.1f" fill="%s" stroke="%s"/>'
                         % (x, y, h, "#e4e7eb" if k == "participant" else "#f5f7fa", stroke))
                lines = wrap(name, max(h - 10, 20), 11, True)
                cx, cy = x + 15, y + h / 2
                th = block_height(len(lines), 11)
                if th <= 29:   # до 2 строк влезает в полосу 30 px: вертикально, как в BPMN
                    o.append('<g transform="rotate(-90 %.1f %.1f)">%s</g>'
                             % (cx, cy, text_block(lines, cx, cy - th / 2, 11, bold=True)))
                elif k == "participant":   # узкий пул (легенда): подпись горизонтально над пулом (правка Даниила)
                    hl = wrap(name, max(w - 10, 60), 11, True)
                    o.append(text_block(hl, x + 2, y - block_height(len(hl), 11) - 3, 11, anchor="start", bold=True))
                else:   # узкая дорожка: горизонтально в левом верхнем углу, справа от полосы
                    hl = wrap(name, max(w - 44, 60), 10, True)
                    o.append(text_block(hl, x + 34, y + 3, 10, anchor="start", bold=True, color=MUTED))
        elif k == "group":
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="10" fill="none" stroke="%s" '
                     'stroke-width="1.5" stroke-dasharray="8 4"/>' % (x, y, w, h, it.get("stroke") or MUTED))
            if name:
                lb = it.get("lb")
                lw = lb[2] if lb else min(w - 16, 420)
                lx, ly = (self.X(lb[0]), self.Y(lb[1])) if lb else (x + 8, y + 6)
                o.append(text_block(wrap(name, lw, 12, True), lx, ly, 12, anchor="start", bold=True,
                                    color=it.get("stroke") or "#3e4c59"))
        elif k == "subProcessExpanded":
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="10" fill="%s" fill-opacity="0.35" '
                     'stroke="%s" stroke-width="1.5"/>' % (x, y, w, h, fill or "none", stroke))
            if name:
                o.append(text_block(wrap(name, min(w - 20, 500), 12, True), x + 10, y + 8, 12,
                                    anchor="start", bold=True))
        elif k in TASKS:
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="10" fill="%s" stroke="%s" stroke-width="%s"/>'
                     % (x, y, w, h, fill or WHITE, stroke, 3.5 if k == "callActivity" else 1.5))
            has_icon = k in ("userTask", "serviceTask")
            if has_icon:
                o.append(icon("user" if k == "userTask" else "service", x + 6, y + 5, 14))
            plus = k in ("callActivity", "subProcess")
            if plus:
                px, py = x + w / 2 - 7, y + h - 17
                o.append('<rect x="%.1f" y="%.1f" width="14" height="14" fill="none" stroke="%s"/>'
                         '<path d="M%.1f %.1fh8M%.1f %.1fv8" stroke="%s"/>'
                         % (px, py, INK, px + 3, py + 7, px + 7, py + 3, INK))
            if name:
                top, bottom = (16 if has_icon else 4), (18 if plus else 4)
                lines, size = fitted(name, w - 12, h - top - bottom)
                th = block_height(len(lines), size)
                o.append(text_block(lines, x + w / 2, y + top + (h - top - bottom - th) / 2, size))
        elif k.endswith("Event"):
            d = min(w, h)
            cx, cy, rr = x + w / 2, y + h / 2, d / 2
            dash = ' stroke-dasharray="4 3"' if it.get("nonInterrupting") else ""
            if k == "endEvent":
                o.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="%s" stroke-width="4"/>'
                         % (cx, cy, rr - 1.5, fill or WHITE, stroke))
            elif k == "startEvent":
                o.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="%s" stroke-width="1.5"%s/>'
                         % (cx, cy, rr, fill or WHITE, stroke, dash))
            else:
                o.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="%s" stroke-width="1.2"%s/>'
                         '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" stroke-width="1.2"%s/>'
                         % (cx, cy, rr, fill or WHITE, stroke, dash, cx, cy, rr - 3, stroke, dash))
            if it.get("ev") in ICONS:
                o.append(icon(it["ev"], cx - 9, cy - 9, 18))
            o.append(self.label(it, cx, y + h, True))
        elif k.endswith("Gateway"):
            o.append('<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="%s" stroke="%s" stroke-width="1.5"/>'
                     % (x + w / 2, y, x + w, y + h / 2, x + w / 2, y + h, x, y + h / 2, fill or WHITE, stroke))
            cx, cy, s = x + w / 2, y + h / 2, min(w, h) * 0.22
            if k == "exclusiveGateway":
                o.append('<path d="M%.1f %.1fL%.1f %.1fM%.1f %.1fL%.1f %.1f" stroke="%s" stroke-width="3"/>'
                         % (cx - s, cy - s, cx + s, cy + s, cx + s, cy - s, cx - s, cy + s, INK))
            elif k == "parallelGateway":
                o.append('<path d="M%.1f %.1fV%.1fM%.1f %.1fH%.1f" stroke="%s" stroke-width="3"/>'
                         % (cx, cy - s, cy + s, cx - s, cy, cx + s, INK))
            elif k == "inclusiveGateway":
                o.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" stroke-width="2.5"/>'
                         % (cx, cy, s, INK))
            elif k == "eventBasedGateway":
                p = s * 0.75
                o.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s"/>'
                         '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s"/>'
                         '<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="none" stroke="%s" stroke-width="1.2"/>'
                         % (cx, cy, s * 1.25, INK, cx, cy, s * 1.05, INK,
                            cx, cy - p, cx + p, cy - p * 0.25, cx + p * 0.6, cy + p, cx - p * 0.6, cy + p,
                            cx - p, cy - p * 0.25, INK))
            o.append(self.label(it, cx, y, False))
        elif k == "textAnnotation":
            lines = wrap(name or " ", max(w - 14, 40), 11)
            hh = max(h, block_height(len(lines), 11) + 10)
            nfill = fill or NOTE_FILL.get(it.get("nc", ""))
            if nfill:
                o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (x, y, w, hh, nfill))
            o.append('<path d="M%.1f %.1fH%.1fV%.1fH%.1f" fill="none" stroke="%s" stroke-width="1.5"/>'
                     % (x + 15, y, x, y + hh, x + 15, it.get("stroke") or LINE))
            colon = (name or "").find(":")
            prefix = colon + 1 if it.get("nc") and 0 < colon < 40 and colon < len(lines[0]) else 0
            o.append(text_block(lines, x + 7, y + 5, 11, anchor="start", bold_prefix=prefix))
        else:
            # данные, хранилища и всё незнакомое — рамкой с подписью, чтобы ничего не пропало
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="%s" stroke="%s"%s/>'
                     % (x, y, w, h, fill or WHITE, stroke, ' stroke-dasharray="4 3"' if k == "unknown" else ""))
            o.append(self.label(it, x + w / 2, y + h, True))
        return "".join(o)


NESTING = ("participant", "lane", "subProcessExpanded")
# порядок внутри родителя: рамки групп -> дорожки -> блоки -> стрелки -> заметки
ORDER = {"group": 0, "lane": 1, "subProcessExpanded": 2, "edge": 4, "textAnnotation": 5}


def area(s):
    return s["b"][2] * s["b"][3]


def has_point(s, x, y):
    bx, by, bw, bh = s["b"]
    return bx - 1 <= x <= bx + bw + 1 and by - 1 <= y <= by + bh + 1


def center(s):
    bx, by, bw, bh = s["b"]
    return bx + bw / 2, by + bh / 2


def tree(model):
    """Кто чей родитель: пул -> дорожки -> блоки. Дорожку блока берём из файла
    (flowNodeRef), если там пусто — по положению. Стрелки — в общий пул обоих концов."""
    shapes = model["shapes"]
    pools = [s for s in shapes if s["k"] == "participant"]
    lanes = [s for s in shapes if s["k"] == "lane"]
    subs = [s for s in shapes if s["k"] == "subProcessExpanded"]
    parent = {}

    def smallest(cands):
        return min(cands, key=area)["id"] if cands else None

    def pool_of(x, y):
        return smallest([p for p in pools if has_point(p, x, y)])

    for l in lanes:
        bx, by, bw, bh = l["b"]
        parent[l["id"]] = smallest([o for o in lanes + pools if o is not l and area(o) > area(l)
                                    and has_point(o, bx, by) and has_point(o, bx + bw, by + bh)])
    for s in shapes:
        if s["k"] in ("participant", "lane"):
            continue
        cx, cy = center(s)
        if s["k"] in ("group", "textAnnotation"):
            parent[s["id"]] = pool_of(cx, cy)
            continue
        sub = smallest([p for p in subs if p is not s and area(p) > area(s) and has_point(p, cx, cy)])
        by_ref = [l for l in lanes if s["id"] in l.get("refs", [])]
        by_pos = [l for l in lanes if has_point(l, cx, cy)]
        parent[s["id"]] = sub or smallest(by_ref) or smallest(by_pos) or pool_of(cx, cy)
    for e in model["edges"]:
        a, b = pool_of(*e["p"][0]), pool_of(*e["p"][-1])
        parent[e["id"]] = a if a == b else None
    return parent


def layer_name(it):
    name = " ".join((it.get("n") or "").split())
    if len(name) > 40:
        name = name[:39] + "…"
    return it["id"] + (" · " + name if name else "")


def render(model, title):
    title_h = 60
    s = Svg(model, title_h)
    W, H = model["size"]
    H += title_h
    q = lambda v: escape(v, {'"': "&quot;"})
    parent = tree(model)
    items = {it["id"]: it for it in model["shapes"]}
    items.update({e["id"]: dict(e, edge=True) for e in model["edges"]})
    children = {}
    for iid, it in items.items():
        children.setdefault(parent.get(iid), []).append(it)

    def key(it):
        k = "edge" if it.get("edge") else it["k"]
        return (ORDER.get(k, 3), -area(it) if "b" in it else 0)

    def draw(it):
        body = s.edge(it) if it.get("edge") else s.shape(it)
        kids = sorted(children.get(it["id"], []), key=key)
        if it.get("k") in NESTING and not it.get("edge"):
            inner = '<g id="%s">%s</g>' % (q(it["id"] + " · рамка"), body)
            inner += "".join(draw(c) for c in kids)
            return '<g id="%s">%s</g>' % (q(layer_name(it)), inner)
        return '<g id="%s">%s</g>' % (q(layer_name(it)), body) if body else ""

    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H),
             '<rect id="фон" x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H),
             '<g id="заголовок">%s</g>' % text_block([title], 40, 14, 24, anchor="start", bold=True),
             ]
    top = sorted(children.get(None, []), key=lambda it: (0 if it.get("k") == "participant" else 1,) + key(it))
    parts += [draw(it) for it in top]
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--title", required=True,
                    help="заголовок схемы: «КОД Название · как есть / как будет» (D-0026)")
    a = ap.parse_args()
    check_out(a.src, a.dst, ".svg")
    model = parse(a.src)
    svg = render(model, a.title)
    with open(a.dst, "w", encoding="utf-8") as f:
        f.write(svg)
    notes = [x for x in model["shapes"] if x["k"] == "textAnnotation"]
    print("Готово:", a.dst, "| блоков:", len(model["shapes"]), "| стрелок:", len(model["edges"]),
          "| заметок:", len(notes), "| размер:", model["size"])


if __name__ == "__main__":
    main()
