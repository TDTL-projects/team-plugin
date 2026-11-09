"""Проверки сборщика версий на маленьких искусственных схемах.
Запуск: python3 -I tools/test_bpmn_merge.py  (печатает «все проверки прошли» или падает)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpmn_merge as bm  # noqa: E402

HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Defs" targetNamespace="http://bpmn.io/schema/bpmn">')


def schema(dx=0, b_name="Б", extra_proc="", extra_di="", lane_extra="", b_out="", f1_name="", drop_a=False):
    a_task = '' if drop_a else '<bpmn:task id="A" name="А"><bpmn:outgoing>F1</bpmn:outgoing></bpmn:task>'
    a_di = '' if drop_a else '<bpmndi:BPMNShape id="A_di" bpmnElement="A"><dc:Bounds x="%d" y="100" width="100" height="80"/></bpmndi:BPMNShape>' % (200 + dx)
    f1 = '' if drop_a else '<bpmn:sequenceFlow id="F1" sourceRef="A" targetRef="B"%s/>' % (' name="%s"' % f1_name if f1_name else "")
    f1_di = '' if drop_a else ('<bpmndi:BPMNEdge id="F1_di" bpmnElement="F1"><di:waypoint x="%d" y="140"/><di:waypoint x="%d" y="140"/></bpmndi:BPMNEdge>'
                               % (300 + dx, 400 + dx))
    return (HEAD +
            '<bpmn:collaboration id="C1"><bpmn:participant id="Pool" name="Пул" processRef="P"/></bpmn:collaboration>'
            '<bpmn:process id="P"><bpmn:laneSet id="LS"><bpmn:lane id="L" name="Дорожка">'
            + ('' if drop_a else '<bpmn:flowNodeRef>A</bpmn:flowNodeRef>') + '<bpmn:flowNodeRef>B</bpmn:flowNodeRef>' + lane_extra +
            '</bpmn:lane></bpmn:laneSet>' + a_task +
            '<bpmn:task id="B" name="%s">' % b_name + ('' if drop_a else '<bpmn:incoming>F1</bpmn:incoming>') + b_out + '</bpmn:task>'
            + f1 + extra_proc + '</bpmn:process>'
            '<bpmndi:BPMNDiagram id="D"><bpmndi:BPMNPlane id="PL" bpmnElement="C1">'
            '<bpmndi:BPMNShape id="Pool_di" bpmnElement="Pool" isHorizontal="true"><dc:Bounds x="%d" y="50" width="900" height="300"/></bpmndi:BPMNShape>' % (100 + dx) +
            '<bpmndi:BPMNShape id="L_di" bpmnElement="L" isHorizontal="true"><dc:Bounds x="%d" y="50" width="870" height="300"/></bpmndi:BPMNShape>' % (130 + dx) +
            a_di +
            '<bpmndi:BPMNShape id="B_di" bpmnElement="B"><dc:Bounds x="%d" y="100" width="100" height="80"/></bpmndi:BPMNShape>' % (400 + dx) +
            f1_di + extra_di + '</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>')


def write(d, name, text):
    p = os.path.join(d, name)
    open(p, "w", encoding="utf-8").write(text)
    return p


def main():
    d = tempfile.mkdtemp()
    base = write(d, "base.bpmn", schema())
    # Андрей: заметка к А и переименовал Б
    v1 = write(d, "v1.bpmn", schema(
        b_name="Б от Андрея",
        extra_proc='<bpmn:textAnnotation id="N1"><bpmn:text>Вопрос АВ: зачем А?</bpmn:text></bpmn:textAnnotation>'
                   '<bpmn:association id="AS1" associationDirection="None" sourceRef="A" targetRef="N1"/>',
        extra_di='<bpmndi:BPMNShape id="N1_di" bpmnElement="N1"><dc:Bounds x="200" y="250" width="150" height="40"/></bpmndi:BPMNShape>'
                 '<bpmndi:BPMNEdge id="AS1_di" bpmnElement="AS1"><di:waypoint x="250" y="180"/><di:waypoint x="250" y="250"/></bpmndi:BPMNEdge>'))
    # Даниил: сдвинул весь холст на 100, переименовал Б по-другому, добавил блок В и стрелку Б -> В, подписал F1
    v2 = write(d, "v2.bpmn", schema(
        dx=100, b_name="Б от Даниила", f1_name="да",
        b_out='<bpmn:outgoing>F2</bpmn:outgoing>',
        lane_extra='<bpmn:flowNodeRef>C</bpmn:flowNodeRef>',
        extra_proc='<bpmn:task id="C" name="В"><bpmn:incoming>F2</bpmn:incoming></bpmn:task>'
                   '<bpmn:sequenceFlow id="F2" sourceRef="B" targetRef="C"/>',
        extra_di='<bpmndi:BPMNShape id="C_di" bpmnElement="C"><dc:Bounds x="700" y="100" width="100" height="80"/></bpmndi:BPMNShape>'
                 '<bpmndi:BPMNEdge id="F2_di" bpmnElement="F2"><di:waypoint x="600" y="140"/><di:waypoint x="700" y="140"/></bpmndi:BPMNEdge>'))
    # Сергей: удалил А (и стрелку F1)
    v3 = write(d, "v3.bpmn", schema(drop_a=True))

    r = bm.merge(base, [v1, v2, v3], ["Андрей", "Даниил", "Сергей"], accept=[])
    m = r["merged"]
    ok = lambda cond, msg: (_ for _ in ()).throw(AssertionError(msg)) if not cond else None

    ok(r["shifts"]["Даниил"] == (100, 0), "сдвиг холста у Даниила не найден: %s" % (r["shifts"],))
    for i in ("N1", "AS1", "C", "F2", "N1_di", "AS1_di", "C_di", "F2_di"):
        ok(i in m.by_id, "не добавлен %s" % i)
    cx = float(m.by_id["C_di"].find("{*}Bounds").get("x"))
    ok(cx == 600, "блок В не сдвинут обратно на 100: x=%s" % cx)
    ok(m.by_id["B"].get("name") == "Б", "изменение Б применилось без решения")
    ok(any(c[0] == "B" for c in r["conflicts"]), "нет конфликта по Б (Андрей и Даниил по-разному)")
    outs = [c.text for c in m.by_id["B"] if c.tag.endswith("outgoing")]
    ok(outs == ["F2"], "у Б нет ссылки на новую стрелку F2: %s" % outs)
    refs = [c.text for c in m.by_id["L"] if c.tag.endswith("flowNodeRef")]
    ok("C" in refs, "блок В не попал в дорожку")
    ok("A" in r["deletions"] and "A" in m.by_id, "удаление А не в отчёте или применилось без решения")
    ok(any(c[0] == "A" for c in r["conflicts"]) is False, "лишний конфликт по А")
    ok(any(c[0] == "F1" for c in r["conflicts"]), "нет конфликта по F1: Даниил подписал, Сергей удалил")
    ok(not r["problems"], "собранный файл не цельный: %s" % r["problems"])
    ok("B_di" not in r["changes"], "сдвиг холста посчитан правкой положения")

    # принять: подпись F1 нельзя (конфликт), удаление А нельзя (на него ссылается F1)
    r2 = bm.merge(base, [v1, v2, v3], ["Андрей", "Даниил", "Сергей"], accept=["F1", "A"])
    failed = {f[1] for f in r2["failed"]}
    ok("F1" in failed, "конфликтную правку F1 приняли")
    ok("A" in failed and "A" in r2["merged"].by_id, "удалили А, на который ссылается стрелка")

    # принять без конфликта: только Даниил, подпись F1
    r3 = bm.merge(base, [v2], ["Даниил"], accept=["F1"])
    ok(r3["merged"].by_id["F1"].get("name") == "да", "принятая подпись F1 не применилась")
    ok(not r3["problems"], "после принятия файл не цельный: %s" % r3["problems"])

    # принять удаление без ссылок: Сергей удаляет только заметку из базы с заметкой
    base_n = write(d, "base_n.bpmn", schema(
        extra_proc='<bpmn:textAnnotation id="N0"><bpmn:text>Старая заметка</bpmn:text></bpmn:textAnnotation>',
        extra_di='<bpmndi:BPMNShape id="N0_di" bpmnElement="N0"><dc:Bounds x="500" y="250" width="150" height="40"/></bpmndi:BPMNShape>'))
    v_del = write(d, "v_del.bpmn", schema())
    r4 = bm.merge(base_n, [v_del], ["Сергей"], accept=["N0"])
    ok("N0" not in r4["merged"].by_id and "N0_di" not in r4["merged"].by_id, "принятое удаление заметки не применилось")
    ok(not r4["problems"], "после удаления файл не цельный: %s" % r4["problems"])

    print("все проверки прошли (%s)" % d)


if __name__ == "__main__":
    main()
