"""Разбор BPMN 2.0 (.bpmn): смысловые элементы + чертёж (DI) -> простая модель
для рисования. Общий для bpmn_to_svg.py. Только стандартная библиотека Python 3.
"""
import math
import os
import sys
import xml.etree.ElementTree as ET

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}
BPMN = "{%s}" % NS["bpmn"]
# цвета, которые сохраняют bpmn.io и Camunda Modeler
COLOR_ATTRS = {
    "fill": ["{http://bpmn.io/schema/bpmn/biocolor/1.0}fill",
             "{http://www.omg.org/spec/BPMN/non-normative/color/1.0}background-color"],
    "stroke": ["{http://bpmn.io/schema/bpmn/biocolor/1.0}stroke",
               "{http://www.omg.org/spec/BPMN/non-normative/color/1.0}border-color"],
}

CONTAINERS = ("participant", "lane", "group", "subProcessExpanded")
EDGE_KINDS = {"sequenceFlow", "messageFlow", "association",
              "dataInputAssociation", "dataOutputAssociation"}
NOTE_KINDS = (("Вопрос", "q"), ("Ответ", "a"), ("Комментарий", "c"))


def r(v):
    return round(float(v), 1)


def bounds(el):
    b = el.find("dc:Bounds", NS)
    if b is None:
        return None
    return [r(b.get("x")), r(b.get("y")), r(b.get("width")), r(b.get("height"))]


def color(el, which):
    for attr in COLOR_ATTRS[which]:
        if el.get(attr):
            return el.get(attr)
    return None


def note_class(text):
    head = text.lstrip()[:40]
    for word, cls in NOTE_KINDS:
        if head.startswith(word):
            return cls
    return ""


def parse(path):
    root = ET.parse(path).getroot()

    # 1. Смысловые элементы: id -> сведения
    sem = {}
    category_values = {}
    for el in root.iter():
        if not el.tag.startswith(BPMN) or not el.get("id"):
            continue
        kind = el.tag[len(BPMN):]
        if kind == "categoryValue":
            category_values[el.get("id")] = el.get("value") or ""
            continue
        info = {"kind": kind, "name": (el.get("name") or "").strip()}
        if kind == "textAnnotation":
            info["name"] = (el.findtext("bpmn:text", "", NS) or "").strip()
        if kind.endswith("Event"):
            defs = [c.tag[len(BPMN):].replace("EventDefinition", "")
                    for c in el if c.tag.endswith("EventDefinition")]
            if defs:
                info["ev"] = defs[0]
            if el.get("cancelActivity") == "false":
                info["nonInterrupting"] = True
        if kind == "group":
            info["cv"] = el.get("categoryValueRef")
        if kind == "lane":
            info["refs"] = [x.text.strip() for x in el.findall("bpmn:flowNodeRef", NS) if x.text]
        if kind == "association":
            info["dir"] = el.get("associationDirection") or "None"
        doc = el.findtext("bpmn:documentation", "", NS)
        if doc:
            info["doc"] = doc.strip()
        sem[el.get("id")] = info
    for info in sem.values():
        if info["kind"] == "group" and not info["name"]:
            info["name"] = category_values.get(info.pop("cv", None), "")
        info.pop("cv", None)

    # 2. Чертёж (DI): одна схема — первая плоскость
    plane = root.find(".//bpmndi:BPMNPlane", NS)
    if plane is None:
        sys.exit("В файле нет чертежа (BPMNDiagram/BPMNPlane) — рисовать не по чему")

    shapes, edges = [], []
    for el in plane:
        tag = el.tag.split("}")[1]
        ref = el.get("bpmnElement")
        info = sem.get(ref, {"kind": "unknown", "name": ""})
        if tag == "BPMNShape":
            item = {"id": ref, "k": info["kind"], "n": info["name"], "b": bounds(el)}
            if item["b"] is None:
                continue
            if info["kind"] == "subProcess" and el.get("isExpanded") == "true":
                item["k"] = "subProcessExpanded"
            lab = el.find("bpmndi:BPMNLabel", NS)
            if lab is not None and bounds(lab):
                item["lb"] = bounds(lab)
            for key in ("ev", "nonInterrupting", "doc", "refs"):
                if key in info:
                    item[key] = info[key]
            if info["kind"] == "textAnnotation":
                item["nc"] = note_class(info["name"])
            for which in ("fill", "stroke"):
                c = color(el, which)
                if c:
                    item[which] = c
            shapes.append(item)
        elif tag == "BPMNEdge":
            pts = [[r(w.get("x")), r(w.get("y"))] for w in el.findall("di:waypoint", NS)]
            if len(pts) < 2:
                continue
            item = {"id": ref, "k": info["kind"], "n": info["name"], "p": pts}
            if info.get("dir") and info["dir"] != "None":
                item["dir"] = info["dir"]
            lab = el.find("bpmndi:BPMNLabel", NS)
            if lab is not None and bounds(lab):
                item["lb"] = bounds(lab)
            c = color(el, "stroke")
            if c:
                item["stroke"] = c
            edges.append(item)

    # 3. Общие границы
    xs, ys = [], []
    for s in shapes:
        x, y, w, h = s["b"]
        xs += [x, x + w]
        ys += [y, y + h]
    for e in edges:
        for x, y in e["p"]:
            xs.append(x)
            ys.append(y)
    pad = 40
    origin = [min(xs) - pad, min(ys) - pad]
    size = [math.ceil(max(xs) - min(xs) + 2 * pad), math.ceil(max(ys) - min(ys) + 2 * pad)]
    return {"source": os.path.basename(path), "origin": origin, "size": size,
            "shapes": shapes, "edges": edges}
