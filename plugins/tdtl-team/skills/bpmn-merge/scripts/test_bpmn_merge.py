"""Проверки сборщика версий на маленьких искусственных схемах.
Запуск из корня репозитория team-plugin:
  python3 -I plugins/tdtl-team/skills/bpmn-merge/scripts/test_bpmn_merge.py
Печатает «все проверки прошли» или список упавших проверок (код выхода 1).
Все файлы — во временной папке, она удаляется после прогона.
"""
import contextlib
import io
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpmn_merge as bm  # noqa: E402

HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Defs" targetNamespace="http://bpmn.io/schema/bpmn">')
BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def schema(dx=0, b_name="Б", extra_proc="", extra_di="", lane_extra="", b_out="", f1_name="", drop_a=False,
           lane_name="Дорожка", b_x=400, f1_source="A", f1_target="B", b_in_lane=True, lanes_extra="",
           extra_collab="", extra_defs=""):
    a_out = '<bpmn:outgoing>F1</bpmn:outgoing>' if f1_source == "A" else ''
    a_task = '' if drop_a else '<bpmn:task id="A" name="А">%s</bpmn:task>' % a_out
    a_di = '' if drop_a else '<bpmndi:BPMNShape id="A_di" bpmnElement="A"><dc:Bounds x="%d" y="100" width="100" height="80"/></bpmndi:BPMNShape>' % (200 + dx)
    f1 = '' if drop_a else '<bpmn:sequenceFlow id="F1" sourceRef="%s" targetRef="%s"%s/>' % (
        f1_source, f1_target, ' name="%s"' % f1_name if f1_name else "")
    f1_di = '' if drop_a else ('<bpmndi:BPMNEdge id="F1_di" bpmnElement="F1"><di:waypoint x="%d" y="140"/><di:waypoint x="%d" y="140"/></bpmndi:BPMNEdge>'
                               % (300 + dx, 400 + dx))
    b_in = '<bpmn:incoming>F1</bpmn:incoming>' if not drop_a and f1_target == "B" else ''
    return (HEAD +
            '<bpmn:collaboration id="C1"><bpmn:participant id="Pool" name="Пул" processRef="P"/>' + extra_collab + '</bpmn:collaboration>'
            '<bpmn:process id="P"><bpmn:laneSet id="LS"><bpmn:lane id="L" name="%s">' % lane_name
            + ('' if drop_a else '<bpmn:flowNodeRef>A</bpmn:flowNodeRef>')
            + ('<bpmn:flowNodeRef>B</bpmn:flowNodeRef>' if b_in_lane else '') + lane_extra +
            '</bpmn:lane>' + lanes_extra + '</bpmn:laneSet>' + a_task +
            '<bpmn:task id="B" name="%s">' % b_name + b_in + b_out + '</bpmn:task>'
            + f1 + extra_proc + '</bpmn:process>' + extra_defs +
            '<bpmndi:BPMNDiagram id="D"><bpmndi:BPMNPlane id="PL" bpmnElement="C1">'
            '<bpmndi:BPMNShape id="Pool_di" bpmnElement="Pool" isHorizontal="true"><dc:Bounds x="%d" y="50" width="900" height="300"/></bpmndi:BPMNShape>' % (100 + dx) +
            '<bpmndi:BPMNShape id="L_di" bpmnElement="L" isHorizontal="true"><dc:Bounds x="%d" y="50" width="870" height="300"/></bpmndi:BPMNShape>' % (130 + dx) +
            a_di +
            '<bpmndi:BPMNShape id="B_di" bpmnElement="B"><dc:Bounds x="%d" y="100" width="100" height="80"/></bpmndi:BPMNShape>' % (b_x + dx) +
            f1_di + extra_di + '</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>')


def write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def sub(d, name):
    p = os.path.join(d, name)
    os.makedirs(p)
    return p


def snapshot(d):
    """Все файлы папки (без подпапок) с содержимым — чтобы увидеть любую запись."""
    out = {}
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                out[n] = f.read()
    return out


def run_main(argv):
    """Запуск bm.main() как из командной строки. -> (код выхода, весь вывод)."""
    buf = io.StringIO()
    old = sys.argv
    sys.argv = ["bpmn_merge.py"] + list(argv)
    code = 0
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                bm.main()
            except SystemExit as e:
                if e.code is None or isinstance(e.code, int):
                    code = e.code or 0
                else:  # sys.exit("текст") — текст тоже вывод
                    code = 1
                    buf.write(str(e.code))
    finally:
        sys.argv = old
    return code, buf.getvalue()


def refs(el, tag):
    return [(c.text or "").strip() for c in el if bm.local(c.tag) == tag]


def lane_of(doc, node):
    return [lid for lid, el in doc.by_id.items() if bm.local(el.tag) == "lane" and node in refs(el, "flowNodeRef")]


NOTE = ('<bpmn:textAnnotation id="N1"><bpmn:text>Вопрос АВ: зачем А?</bpmn:text></bpmn:textAnnotation>',
        '<bpmndi:BPMNShape id="N1_di" bpmnElement="N1"><dc:Bounds x="200" y="250" width="150" height="40"/></bpmndi:BPMNShape>')
ADD_C = dict(  # новый блок В в дорожке L и стрелка Б -> В
    b_out='<bpmn:outgoing>F2</bpmn:outgoing>',
    lane_extra='<bpmn:flowNodeRef>C</bpmn:flowNodeRef>',
    extra_proc='<bpmn:task id="C" name="В"><bpmn:incoming>F2</bpmn:incoming></bpmn:task>'
               '<bpmn:sequenceFlow id="F2" sourceRef="B" targetRef="C"/>',
    extra_di='<bpmndi:BPMNShape id="C_di" bpmnElement="C"><dc:Bounds x="600" y="100" width="100" height="80"/></bpmndi:BPMNShape>'
             '<bpmndi:BPMNEdge id="F2_di" bpmnElement="F2"><di:waypoint x="500" y="140"/><di:waypoint x="600" y="140"/></bpmndi:BPMNEdge>')


# ---------------------------------------------------------------- прежние проверки (T-0142)

def old_checks(d):
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

    ok(r["shifts"]["Даниил"] == (100, 0), "сдвиг холста у Даниила не найден: %s" % (r["shifts"],))
    for i in ("N1", "AS1", "C", "F2", "N1_di", "AS1_di", "C_di", "F2_di"):
        ok(i in m.by_id, "не добавлен %s" % i)
    cx = float(m.by_id["C_di"].find("{*}Bounds").get("x"))
    ok(cx == 600, "блок В не сдвинут обратно на 100: x=%s" % cx)
    ok(m.by_id["B"].get("name") == "Б", "изменение Б применилось без решения")
    ok(any(c[0] == "B" for c in r["conflicts"]), "нет конфликта по Б (Андрей и Даниил по-разному)")
    outs = [c.text for c in m.by_id["B"] if c.tag.endswith("outgoing")]
    ok(outs == ["F2"], "у Б нет ссылки на новую стрелку F2: %s" % outs)
    refs_l = [c.text for c in m.by_id["L"] if c.tag.endswith("flowNodeRef")]
    ok("C" in refs_l, "блок В не попал в дорожку")
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


# ---------------------------------------------------------------- T-0196

def ac1(d):
    """-o и --report не совпадают с исходной, с версиями и друг с другом."""
    cases = [
        ("-o = исходная", lambda w: ["-o", w["base"], "--report", w["rep"]], "base.bpmn"),
        ("-o = версия", lambda w: ["-o", w["v1"], "--report", w["rep"]], "v1.bpmn"),
        ("--report = исходная", lambda w: ["-o", w["out"], "--report", w["base"]], "base.bpmn"),
        ("--report = вторая версия", lambda w: ["-o", w["out"], "--report", w["v2"]], "v2.bpmn"),
        ("-o = --report", lambda w: ["-o", w["same"], "--report", w["same"]], "same.md"),
        ("-o = исходная, записанная по-другому", lambda w: ["-o", os.path.join(w["d"], "x", "..", "base.bpmn"),
                                                            "--report", w["rep"]], "base.bpmn"),
    ]
    for n, (title, argv, name) in enumerate(cases):
        c = sub(d, "c%d" % n)
        os.makedirs(os.path.join(c, "x"))
        w = {"d": c, "base": write(c, "base.bpmn", schema()),
             "v1": write(c, "v1.bpmn", schema(b_name="Б1", extra_proc=NOTE[0], extra_di=NOTE[1])),
             "v2": write(c, "v2.bpmn", schema(f1_name="да")),
             "out": os.path.join(c, "out.bpmn"), "rep": os.path.join(c, "rep.md"), "same": os.path.join(c, "same.md")}
        before = snapshot(c)
        code, out = run_main([w["base"], w["v1"], w["v2"]] + argv(w))
        after = snapshot(c)
        ok(code != 0, "T-0196 AC-1: %s — сборка не остановилась (код выхода 0)" % title)
        ok(after == before, "T-0196 AC-1: %s — файлы в папке записаны или изменены: было %s, стало %s"
           % (title, sorted(before), sorted(after)))
        ok(name in out, "T-0196 AC-1: %s — в тексте остановки не назван файл %s: %r" % (title, name, out[-300:]))
    # обычный запуск по-прежнему пишет оба файла
    c = sub(d, "ok")
    base, v1 = write(c, "base.bpmn", schema()), write(c, "v1.bpmn", schema(extra_proc=NOTE[0], extra_di=NOTE[1]))
    code, out = run_main([base, v1, "-o", os.path.join(c, "out.bpmn"), "--report", os.path.join(c, "rep.md")])
    ok(code == 0 and os.path.exists(os.path.join(c, "out.bpmn")) and os.path.exists(os.path.join(c, "rep.md")),
       "T-0196 AC-1: обычный запуск не записал собранную и отчёт: код %s, %r" % (code, out[-300:]))


def ac2(d):
    """Запись — только после проверки и построения отчёта; ошибка отчёта не оставляет полузаписанного."""
    c = sub(d, "boom")
    base = write(c, "base.bpmn", schema())
    v1 = write(c, "v1.bpmn", schema(b_name="Б1", extra_proc=NOTE[0], extra_di=NOTE[1]))
    write(c, "out.bpmn", "OLD-OUT")
    write(c, "rep.md", "OLD-REP")

    def boom(*a, **k):
        raise RuntimeError("сбой при построении отчёта")

    for title, out_name, rep_name in (("файлы уже были", "out.bpmn", "rep.md"),
                                      ("файлов не было", "new.bpmn", "new.md")):
        before = snapshot(c)
        orig = bm.report
        bm.report = boom
        raised, code = False, None
        try:
            code, _ = run_main([base, v1, "-o", os.path.join(c, out_name), "--report", os.path.join(c, rep_name)])
        except Exception:
            raised = True
        finally:
            bm.report = orig
        after = snapshot(c)
        ok(raised or code != 0, "T-0196 AC-2: %s — ошибка в отчёте проглочена, код выхода 0" % title)
        ok(after == before, "T-0196 AC-2: %s — при ошибке в отчёте на диске что-то записано: было %s, стало %s%s"
           % (title, sorted(before), sorted(after),
              "" if after.get("out.bpmn") == before.get("out.bpmn") else " (out.bpmn перезаписан)"))
    # проблемы целостности: как раньше — код выхода 1, файлы записаны, отчёт говорит «не цельный»
    c = sub(d, "broken")
    ghost = '<bpmn:flowNodeRef>GHOST</bpmn:flowNodeRef>'
    base = write(c, "base.bpmn", schema(lane_extra=ghost))
    v1 = write(c, "v1.bpmn", schema(lane_extra=ghost, extra_proc=NOTE[0], extra_di=NOTE[1]))
    out, rep = os.path.join(c, "out.bpmn"), os.path.join(c, "rep.md")
    code, txt = run_main([base, v1, "-o", out, "--report", rep])
    ok(code == 1, "T-0196 AC-2: при проблемах целостности код выхода не 1: %s" % code)
    ok(os.path.exists(out) and os.path.exists(rep), "T-0196 AC-2: при проблемах целостности файлы не записаны")
    with open(rep, encoding="utf-8") as f:
        ok("не цельный" in f.read(), "T-0196 AC-2: в отчёте нет «Собранный файл не цельный»")


def ac3(d):
    """--accept правки не стирает incoming/outgoing/flowNodeRef, добавленные другим автором или сборкой."""
    base = write(d, "base.bpmn", schema())
    v_add = write(d, "v_add.bpmn", schema(**ADD_C))  # Андрей: стрелка Б -> В, блок В в дорожке
    v_ren = write(d, "v_ren.bpmn", schema(b_name="Б2"))  # Даниил: переименовал Б
    r = bm.merge(base, [v_add, v_ren], ["Андрей", "Даниил"], accept=["B"])
    b = r["merged"].by_id["B"]
    ok(b.get("name") == "Б2", "T-0196 AC-3: принятое переименование Б не применилось")
    ok(refs(b, "outgoing") == ["F2"], "T-0196 AC-3: --accept B стёр у Б ссылку на стрелку F2 другого автора: outgoing=%s"
       % refs(b, "outgoing"))
    ok(refs(b, "incoming") == ["F1"], "T-0196 AC-3: у Б потерялся incoming F1: %s" % refs(b, "incoming"))
    ok(not r["problems"], "T-0196 AC-3: файл не цельный: %s" % r["problems"])

    v_lane = write(d, "v_lane.bpmn", schema(lane_name="Дорожка Даниила"))  # Даниил: переименовал дорожку
    r = bm.merge(base, [v_add, v_lane], ["Андрей", "Даниил"], accept=["L"])
    lane = r["merged"].by_id["L"]
    ok(lane.get("name") == "Дорожка Даниила", "T-0196 AC-3: принятое переименование дорожки не применилось")
    ok(sorted(refs(lane, "flowNodeRef")) == ["A", "B", "C"],
       "T-0196 AC-3: --accept L выкинул из дорожки блок другого автора: flowNodeRef=%s" % refs(lane, "flowNodeRef"))
    ok(not r["problems"], "T-0196 AC-3: файл не цельный: %s" % r["problems"])


def ac4(d):
    """--accept Task принимает только Task, чертёж — только по явному Task_di; неизвестный id — в «Не получилось»."""
    base = write(d, "base.bpmn", schema())
    v = write(d, "v.bpmn", schema(b_name="Б2", b_x=450))  # переименовал Б и передвинул его
    r = bm.merge(base, [v], ["Андрей"], accept=["B"])
    bx = float(r["merged"].by_id["B_di"].find("{*}Bounds").get("x"))
    ok(r["merged"].by_id["B"].get("name") == "Б2", "T-0196 AC-4: --accept B не применил переименование")
    ok(bx == 400, "T-0196 AC-4: --accept B заодно передвинул чертёж B_di (x=%s), его не называли" % bx)
    r = bm.merge(base, [v], ["Андрей"], accept=["B", "B_di"])
    bx = float(r["merged"].by_id["B_di"].find("{*}Bounds").get("x"))
    ok(bx == 450, "T-0196 AC-4: --accept B,B_di не передвинул чертёж (x=%s)" % bx)

    r = bm.merge(base, [v], ["Андрей"], accept=["A"])  # А есть в схеме, но его никто не менял
    ok("A" in {f[1] for f in r["failed"]}, "T-0196 AC-4: --accept A без правки и удаления у А — молча, не в «Не получилось»")
    rep = os.path.join(d, "rep.md")
    code, out = run_main([base, v, "-o", os.path.join(d, "out.bpmn"), "--report", rep, "--accept", "NOPE_404"])
    with open(rep, encoding="utf-8") as f:
        text = f.read()
    tail = text.split("## Не получилось", 1)[1] if "## Не получилось" in text else ""
    ok("NOPE_404" in tail, "T-0196 AC-4: неизвестный id NOPE_404 из --accept не попал в «Не получилось» отчёта")
    ok("NOPE_404" in out, "T-0196 AC-4: неизвестный id NOPE_404 из --accept не назван в выводе: %r" % out[-300:])


def ac5(d):
    """--accept удаления не удаляет элемент, на который ссылаются, или с вложенными; причина в отчёте."""
    X = '<bpmn:task id="X" name="Х"/>'
    cases = [
        ("attachedToRef", "X", dict(extra_proc=X + '<bpmn:boundaryEvent id="BE" attachedToRef="X"/>'), dict()),
        ("default", "FG", dict(extra_proc='<bpmn:exclusiveGateway id="G" default="FG"/>'
                                          '<bpmn:sequenceFlow id="FG" sourceRef="G" targetRef="B"/>'),
         dict(extra_proc='<bpmn:exclusiveGateway id="G"/>')),
        ("processRef", "P2", dict(extra_collab='<bpmn:participant id="Pool2" name="Пул 2" processRef="P2"/>',
                                  extra_defs='<bpmn:process id="P2"/>'),
         dict(extra_collab='<bpmn:participant id="Pool2" name="Пул 2" processRef="P2"/>')),
        ("подпроцесс с вложенным блоком", "SP",
         dict(extra_proc='<bpmn:subProcess id="SP"><bpmn:task id="ST" name="Внутри"/></bpmn:subProcess>'), dict()),
        ("дорожка с блоком (flowNodeRef)", "L2",
         dict(extra_proc=X, lanes_extra='<bpmn:lane id="L2" name="Дорожка 2"><bpmn:flowNodeRef>X</bpmn:flowNodeRef></bpmn:lane>'),
         dict(extra_proc=X, lane_extra='<bpmn:flowNodeRef>X</bpmn:flowNodeRef>')),
        ("дорожка с поддорожкой (childLaneSet)", "L3",
         dict(lanes_extra='<bpmn:lane id="L3" name="Дорожка 3"><bpmn:childLaneSet id="CLS">'
                          '<bpmn:lane id="L4" name="Поддорожка"/></bpmn:childLaneSet></bpmn:lane>'), dict()),
    ]
    for n, (title, iid, b_kw, v_kw) in enumerate(cases):
        c = sub(d, "c%d" % n)
        base = write(c, "base.bpmn", schema(**b_kw))
        v = write(c, "v.bpmn", schema(**v_kw))
        r = bm.merge(base, [v], ["Сергей"], accept=[iid])
        ok(iid in r["deletions"], "T-0196 AC-5: %s — удаление %s не найдено (сломан сам сценарий)" % (title, iid))
        ok(iid in r["merged"].by_id, "T-0196 AC-5: %s — %s удалён по --accept, хотя на него ссылаются или в нём есть элементы"
           % (title, iid))
        why = [f for f in r["failed"] if f[1] == iid]
        ok(why and all(str(f[2]).strip() for f in why), "T-0196 AC-5: %s — отказ удалить %s без причины в «Не получилось»"
           % (title, iid))
        ok(not r["problems"], "T-0196 AC-5: %s — файл не цельный: %s" % (title, r["problems"]))
    # вложенное удалено первым — тогда пустой подпроцесс удаляется как раньше
    c = sub(d, "nested_ok")
    base = write(c, "base.bpmn", schema(**cases[3][2]))
    v = write(c, "v.bpmn", schema())
    r = bm.merge(base, [v], ["Сергей"], accept=["ST", "SP"])
    ok("ST" not in r["merged"].by_id and "SP" not in r["merged"].by_id,
       "T-0196 AC-5: --accept ST,SP — подпроцесс с принятым удалением вложенного не удалён")
    ok(not r["problems"], "T-0196 AC-5: файл не цельный: %s" % r["problems"])


def ac6(d):
    """Принятая правка конца стрелки обновляет incoming/outgoing; перенос между дорожками — изменение в отчёте."""
    base = write(d, "base.bpmn", schema(extra_proc='<bpmn:task id="X" name="Х"/>'))
    # куда: F1 теперь ведёт в Х, а не в Б
    v_t = write(d, "v_t.bpmn", schema(f1_target="X", extra_proc='<bpmn:task id="X" name="Х"><bpmn:incoming>F1</bpmn:incoming></bpmn:task>'))
    r = bm.merge(base, [v_t], ["Андрей"], accept=["F1"])
    m = r["merged"]
    ok(m.by_id["F1"].get("targetRef") == "X", "T-0196 AC-6: принятая правка targetRef F1 не применилась")
    ok("F1" not in refs(m.by_id["B"], "incoming"), "T-0196 AC-6: у Б остался incoming F1 после переноса стрелки в Х")
    ok(refs(m.by_id["X"], "incoming") == ["F1"], "T-0196 AC-6: у Х нет incoming F1: %s" % refs(m.by_id["X"], "incoming"))
    # откуда: F1 теперь идёт из Х, а не из А
    v_s = write(d, "v_s.bpmn", schema(f1_source="X", extra_proc='<bpmn:task id="X" name="Х"><bpmn:outgoing>F1</bpmn:outgoing></bpmn:task>'))
    r = bm.merge(base, [v_s], ["Андрей"], accept=["F1"])
    m = r["merged"]
    ok(m.by_id["F1"].get("sourceRef") == "X", "T-0196 AC-6: принятая правка sourceRef F1 не применилась")
    ok("F1" not in refs(m.by_id["A"], "outgoing"), "T-0196 AC-6: у А остался outgoing F1 после переноса стрелки на Х")
    ok(refs(m.by_id["X"], "outgoing") == ["F1"], "T-0196 AC-6: у Х нет outgoing F1: %s" % refs(m.by_id["X"], "outgoing"))

    # Андрей перенёс Б из «Дорожка» в «Дорожка 2»; Даниил добавил в «Дорожка 2» новый блок В — это не конфликт
    lane2 = '<bpmn:lane id="L2" name="Дорожка 2">%s</bpmn:lane>'
    base = write(d, "base_l.bpmn", schema(lanes_extra=lane2 % ""))
    v_move = write(d, "v_move.bpmn", schema(b_in_lane=False, lanes_extra=lane2 % '<bpmn:flowNodeRef>B</bpmn:flowNodeRef>'))
    v_add = write(d, "v_add_l.bpmn", schema(
        lanes_extra=lane2 % '<bpmn:flowNodeRef>C</bpmn:flowNodeRef>', extra_proc='<bpmn:task id="C" name="В"/>',
        extra_di='<bpmndi:BPMNShape id="C_di" bpmnElement="C"><dc:Bounds x="600" y="250" width="100" height="80"/></bpmndi:BPMNShape>'))
    r = bm.merge(base, [v_move, v_add], ["Андрей", "Даниил"], accept=[])
    moved = [i for i in ("B", "L", "L2") if i in r["changes"]]
    ok(moved, "T-0196 AC-6: перенос Б в другую дорожку не попал в изменения")
    ok(not r["conflicts"], "T-0196 AC-6: перенос Б и новый блок в той же дорожке дали конфликт: %s" % r["conflicts"])
    ok(lane_of(r["merged"], "B") == ["L"], "T-0196 AC-6: перенос Б применился без решения: %s" % lane_of(r["merged"], "B"))
    rep = os.path.join(d, "rep_l.md")
    run_main([base, v_move, v_add, "--authors", "Андрей,Даниил", "-o", os.path.join(d, "out_l.bpmn"), "--report", rep])
    with open(rep, encoding="utf-8") as f:
        text = f.read()
    sec = text.split("## Изменения", 1)[1].split("\n## ", 1)[0] if "## Изменения" in text else ""
    ok("Дорожка 2" in sec, "T-0196 AC-6: в разделе «Изменения» отчёта не видно переноса в «Дорожка 2»")
    r = bm.merge(base, [v_move, v_add], ["Андрей", "Даниил"], accept=moved)
    m = r["merged"]
    ok(lane_of(m, "B") == ["L2"], "T-0196 AC-6: принятый перенос Б (--accept %s) не применился: Б в %s"
       % (",".join(moved), lane_of(m, "B")))
    ok(lane_of(m, "C") == ["L2"] and lane_of(m, "A") == ["L"], "T-0196 AC-6: после переноса Б другие блоки выпали из дорожек")
    ok(not r["problems"], "T-0196 AC-6: файл не цельный: %s" % r["problems"])


def ns_prefixed(text):
    """Та же схема, но с префиксами ns0…ns3, как пишет ElementTree."""
    for old, new in (("bpmndi", "ns1"), ("bpmn", "ns0"), ("dc", "ns2"), ("di", "ns3")):
        text = text.replace("xmlns:%s=" % old, "xmlns:%s=" % new)
        text = text.replace("<%s:" % old, "<%s:" % new).replace("</%s:" % old, "</%s:" % new)
    return text


def ac7(d):
    """Файлы с префиксами ns0, ns1 не роняют сборку."""
    for n, (title, base_text) in enumerate((("обе с ns0", ns_prefixed(schema())),
                                            ("исходная с bpmn:, версия с ns0", schema()))):
        c = sub(d, "c%d" % n)
        base = write(c, "base.bpmn", base_text)
        v = write(c, "v.bpmn", ns_prefixed(schema(extra_proc=NOTE[0], extra_di=NOTE[1])))
        with open(v, encoding="utf-8") as f:
            ok("<ns0:task" in f.read(), "T-0196 AC-7: сценарий сломан — в версии нет префикса ns0")
        out, rep = os.path.join(c, "out.bpmn"), os.path.join(c, "rep.md")
        try:
            code, txt = run_main([base, v, "-o", out, "--report", rep])
        except Exception as e:
            raise AssertionError("T-0196 AC-7: %s — сборка упала: %s: %s" % (title, type(e).__name__, e))
        ok(code == 0, "T-0196 AC-7: %s — код выхода %s: %r" % (title, code, txt[-300:]))
        root = ET.parse(out).getroot()
        ok(any(el.get("id") == "N1" for el in root.iter(BPMN + "textAnnotation")),
           "T-0196 AC-7: %s — новая заметка N1 не попала в собранную" % title)
        r = bm.merge(out, [out], ["тот же"], accept=[])
        ok(not r["problems"] and not r["changes"], "T-0196 AC-7: %s — собранный файл не читается как исходная" % title)


CHECKS = [("прежние проверки", old_checks), ("T-0196 AC-1", ac1), ("T-0196 AC-2", ac2), ("T-0196 AC-3", ac3),
          ("T-0196 AC-4", ac4), ("T-0196 AC-5", ac5), ("T-0196 AC-6", ac6), ("T-0196 AC-7", ac7)]


def main():
    fails = []
    with tempfile.TemporaryDirectory(prefix="bpmn_merge_test_") as d:
        for name, fn in CHECKS:
            try:
                fn(sub(d, fn.__name__))
            except AssertionError as e:
                fails.append("%s — %s" % (name, e))
            except Exception as e:  # падение сборщика — тоже красная проверка, остальные идут дальше
                fails.append("%s — упало: %s: %s" % (name, type(e).__name__, e))
    if fails:
        print("НЕ ПРОШЛИ (%d из %d):" % (len(fails), len(CHECKS)))
        for f in fails:
            print("- " + f)
        sys.exit(1)
    print("все проверки прошли")


if __name__ == "__main__":
    main()
