"""Приёмочные проверки T-0221 для сборщика версий BPMN, на маленьких искусственных схемах.
Запуск из корня репозитория team-plugin:
  python3 -I plugins/tdtl-team/skills/bpmn-merge/scripts/test_bpmn_merge_t0221.py
Печатает «все проверки прошли» или список упавших проверок (код выхода 1).
Все файлы — во временной папке, она удаляется после прогона. Сети нет.
Помощники (schema, write, ok, run_main, …) — из проверок T-0196 (test_bpmn_merge.py).
"""
import builtins
import errno
import io
import os
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpmn_merge as bm  # noqa: E402
import test_bpmn_merge as t96  # noqa: E402

ok, write, sub, snapshot, tree, run_main = t96.ok, t96.write, t96.sub, t96.snapshot, t96.tree, t96.run_main
schema, refs, lanes_with, dup_refs, fr, NOTE = t96.schema, t96.refs, t96.lanes_with, t96.dup_refs, t96.fr, t96.NOTE


# ---------------------------------------------------------------- AC-1: все дорожки блока в отчёте и в --accept

def lanes_doc(b_lanes, b_name="Б"):
    """Дорожка «Брокер» (L) с поддорожкой «Исполнитель» (L1). А — в обеих, Б — в b_lanes (множество из L, L1)."""
    return (t96.HEAD + '<bpmn:process id="P"><bpmn:laneSet id="LS">'
            '<bpmn:lane id="L" name="Брокер">' + fr("A", *(["B"] if "L" in b_lanes else [])) +
            '<bpmn:childLaneSet id="CLS"><bpmn:lane id="L1" name="Исполнитель">' +
            fr("A", *(["B"] if "L1" in b_lanes else [])) +
            '</bpmn:lane></bpmn:childLaneSet></bpmn:lane></bpmn:laneSet>'
            '<bpmn:task id="A" name="А"/><bpmn:task id="B" name="%s"/>' % b_name +
            '</bpmn:process></bpmn:definitions>')


def lanes_part(text, iid):
    """Кусок строки отчёта про дорожки блока iid: (до «→», после «→»). Нет строки или куска — (None, None)."""
    sec = text.split("## Изменения", 1)[1].split("\n## ", 1)[0] if "## Изменения" in text else ""
    for line in sec.splitlines():
        if line.startswith("- `%s`" % iid) and "дорожк" in line:
            seg = line[line.index("дорожк"):].split(";", 1)[0]
            if "→" in seg:
                left, right = seg.split("→", 1)
                return left, right
    return None, None


def ac1_lane_sets(d):
    """T-0221 AC-1: отчёт показывает весь набор дорожек блока до и после; --accept ставит ровно его;
    одинаковое переименование с разными наборами дорожек у двух авторов — конфликт."""
    base = write(d, "base.bpmn", lanes_doc({"L", "L1"}))
    errs = []
    for n, (title, v_text) in enumerate((("только убрал из «Брокер»", lanes_doc({"L1"})),
                                         ("переименовал и убрал из «Брокер»", lanes_doc({"L1"}, b_name="Б2")))):
        v = write(d, "v_%d.bpmn" % n, v_text)
        r = bm.merge(base, [v], ["Андрей"], accept=[])
        if "B" not in r["changes"]:
            errs.append("%s: Б ушёл из «Брокер» (остался в «Исполнитель») — этого нет в изменениях" % title)
        elif lanes_with(r["merged"], "B") != {"L", "L1"}:
            errs.append("%s: без --accept Б в %s, ждали как в исходной {L, L1}" % (title, sorted(lanes_with(r["merged"], "B"))))
        text = bm.report(r, base, [v], ["Андрей"], os.path.join(d, "out.bpmn"))
        left, right = lanes_part(text, "B")
        if left is None:
            errs.append("%s: в «## Изменения» нет строки про дорожки Б вида «дорожки: «Брокер», «Исполнитель» → «Исполнитель»»"
                        % title)
        elif not ("Брокер" in left and "Исполнитель" in left and "Исполнитель" in right and "Брокер" not in right):
            errs.append("%s: дорожки Б показаны не полностью: было «%s», стало «%s»; ждали «Брокер», «Исполнитель» → "
                        "«Исполнитель»" % (title, left.strip(), right.strip()))
        r = bm.merge(base, [v], ["Андрей"], accept=["B"])
        m = r["merged"]
        if lanes_with(m, "B") != {"L1"} or "B" not in {a[0] for a in r["applied"]}:
            errs.append("%s, --accept B: Б в %s, ждали ровно показанное {L1}; «Не получилось» %s"
                        % (title, sorted(lanes_with(m, "B")), [f for f in r["failed"] if f[1] == "B"]))
        if lanes_with(m, "A") != {"L", "L1"} or dup_refs(m) or r["problems"]:
            errs.append("%s, --accept B: А в %s, повторы %s, проблемы %s"
                        % (title, sorted(lanes_with(m, "A")), dup_refs(m), r["problems"]))

    # два автора одинаково переименовали Б, но один ещё убрал его из «Брокер» — конфликт, не набор первого
    vx = write(d, "vx.bpmn", lanes_doc({"L1"}, b_name="Б2"))
    vy = write(d, "vy.bpmn", lanes_doc({"L", "L1"}, b_name="Б2"))
    for title, files, authors in (("убравший первым", [vx, vy], ["X", "Y"]), ("убравший вторым", [vy, vx], ["Y", "X"])):
        r = bm.merge(base, files, authors, accept=["B"])
        m = r["merged"]
        if not any(c[0] == "B" for c in r["conflicts"]):
            errs.append("%s: одинаковое имя Б2, разные дорожки — нет конфликта по Б" % title)
        if m.by_id["B"].get("name") != "Б" or lanes_with(m, "B") != {"L", "L1"}:
            errs.append("%s, --accept B: правка Б применена при конфликте: имя «%s», дорожки %s"
                        % (title, m.by_id["B"].get("name"), sorted(lanes_with(m, "B"))))
        if "B" not in {f[1] for f in r["failed"]} or "B" in {a[0] for a in r["applied"]}:
            errs.append("%s, --accept B: Б не в «Не получилось» или стоит в «Принято»" % title)
    # сторож: одинаковое имя и одинаковые дорожки у обоих — не конфликт
    vz = write(d, "vz.bpmn", lanes_doc({"L1"}, b_name="Б2"))
    r = bm.merge(base, [vx, vz], ["X", "Z"], accept=["B"])
    if any(c[0] == "B" for c in r["conflicts"]) or lanes_with(r["merged"], "B") != {"L1"} \
            or r["merged"].by_id["B"].get("name") != "Б2":
        errs.append("одинаковая правка у двух авторов: конфликт %s, Б в %s, имя «%s» — ждали без конфликта, {L1}, «Б2»"
                    % ([c for c in r["conflicts"] if c[0] == "B"], sorted(lanes_with(r["merged"], "B")),
                       r["merged"].by_id["B"].get("name")))
    ok(not errs, "T-0221 AC-1: " + "; ".join(errs))


# ---------------------------------------------------------------- AC-2: отчёт пишется первым; папка без права записи

class FailingOpen:
    """На время проверки: открыть на запись путь path нельзя (как переполненный диск). Остальное — как обычно."""

    def __init__(self, path):
        self.target = os.path.realpath(path)

    def _hit(self, file):
        try:
            return os.path.realpath(os.fsdecode(file)) == self.target
        except TypeError:
            return False   # открывают по номеру дескриптора

    def __enter__(self):
        self.real_open, self.real_io_open, self.real_os_open = builtins.open, io.open, os.open
        real_open, real_os_open = self.real_open, self.real_os_open

        def fake_open(file, mode="r", *a, **k):
            if any(ch in mode for ch in "wax+") and self._hit(file):
                raise OSError(errno.ENOSPC, "Нет места на диске (подмена в проверке)", os.fsdecode(file))
            return real_open(file, mode, *a, **k)

        def fake_os_open(path, flags, *a, **k):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT) and self._hit(path):
                raise OSError(errno.ENOSPC, "Нет места на диске (подмена в проверке)", os.fsdecode(path))
            return real_os_open(path, flags, *a, **k)

        builtins.open, io.open, os.open = fake_open, fake_open, fake_os_open
        return self

    def __exit__(self, *exc):
        builtins.open, io.open, os.open = self.real_open, self.real_io_open, self.real_os_open
        return False


def ac2_write_order(d):
    """T-0221 AC-2: запись схемы не удалась — отчёт уже записан, выход с ошибкой и «не выкладывать»;
    запись отчёта не удалась — схема не записана."""
    errs = []
    c = sub(d, "out_fails")
    base = write(c, "base.bpmn", schema())
    v1 = write(c, "v1.bpmn", schema(b_name="Б1", extra_proc=NOTE[0], extra_di=NOTE[1]))
    out, rep = os.path.join(c, "out.bpmn"), os.path.join(c, "rep.md")
    try:
        with FailingOpen(out):
            code, txt = run_main([base, v1, "-o", out, "--report", rep])
    except Exception as e:
        code, txt = None, ""
        errs.append("схема не записалась: упало %s: %s вместо выхода с ошибкой и понятного текста" % (type(e).__name__, e))
    if code == 0:
        errs.append("схема не записалась, а код выхода 0")
    rep_text = ""
    if os.path.exists(rep):
        with open(rep, encoding="utf-8") as f:
            rep_text = f.read()
    if "Итог" not in rep_text:
        errs.append("схема не записалась — и отчёта нет (или он неполный): отчёт должен быть записан первым")
    if code not in (None, 0) and "не выкладывать" not in txt:
        errs.append("схема не записалась — в выводе нет «отчёт записан, схема — нет, не выкладывать»: %r" % txt[-300:])

    c = sub(d, "rep_fails")
    base = write(c, "base.bpmn", schema())
    v1 = write(c, "v1.bpmn", schema(b_name="Б1", extra_proc=NOTE[0], extra_di=NOTE[1]))
    out, rep = os.path.join(c, "out.bpmn"), os.path.join(c, "rep.md")
    raised, code = False, None
    try:
        with FailingOpen(rep):
            code, txt = run_main([base, v1, "-o", out, "--report", rep])
    except Exception:
        raised = True
    if not raised and code == 0:
        errs.append("отчёт не записался, а код выхода 0")
    if os.path.exists(out):
        errs.append("отчёт не записался, а схема записана — схема без отчёта")
    ok(not errs, "T-0221 AC-2: " + "; ".join(errs))


def ac2_readonly_dir(d):
    """T-0221 AC-2: папка для -o или --report без права записи — отказ до сборки, оба файла не созданы."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("ПРОПУЩЕНО: T-0221 AC-2 (папка без права записи) — запуск от root, права папок не действуют")
        return
    errs = []
    for n, (title, flag) in enumerate((("-o в папке без права записи", "-o"),
                                       ("--report в папке без права записи", "--report"))):
        c = sub(d, "c%d" % n)
        ro, rw = sub(c, "locked_dir"), sub(c, "rw")
        base = write(c, "base.bpmn", schema())
        v1 = write(c, "v1.bpmn", schema(extra_proc=NOTE[0], extra_di=NOTE[1]))
        out = os.path.join(ro if flag == "-o" else rw, "out.bpmn")
        rep = os.path.join(rw if flag == "-o" else ro, "rep.md")
        os.chmod(ro, stat.S_IRUSR | stat.S_IXUSR)
        calls = []
        orig = bm.merge

        def spy(*a, **k):
            calls.append(1)
            return orig(*a, **k)

        try:
            probe = os.path.join(ro, "probe")
            try:
                with open(probe, "w"):
                    pass
            except OSError:
                pass
            else:
                os.remove(probe)
                print("ПРОПУЩЕНО: T-0221 AC-2 (папка без права записи) — в этой системе chmod не запрещает запись")
                return
            before = tree(c)
            bm.merge = spy
            try:
                code, txt = run_main([base, v1, "-o", out, "--report", rep])
            except Exception as e:
                code, txt = None, ""
                errs.append("%s: упало %s: %s вместо отказа с понятным текстом" % (title, type(e).__name__, e))
            finally:
                bm.merge = orig
            after = tree(c)
        finally:
            os.chmod(ro, stat.S_IRWXU)
        if code == 0:
            errs.append("%s: код выхода 0" % title)
        if after != before:
            errs.append("%s: на диске что-то записано: %s" % (title, sorted(set(after) ^ set(before)) or
                                                              [k for k in after if after[k] != before.get(k)]))
        if calls:
            errs.append("%s: сборка запущена — отказ должен быть до сборки" % title)
        if code not in (None, 0) and "locked_dir" not in txt:
            errs.append("%s: в тексте отказа не названа папка locked_dir: %r" % (title, txt[-200:]))
    ok(not errs, "T-0221 AC-2: " + "; ".join(errs))


# ---------------------------------------------------------------- AC-3: существующий -o или --report не перезаписывается

def ac3_no_overwrite(d):
    """T-0221 AC-3: -o или --report указывает на существующий файл, которого нет среди входных, — отказ,
    файл не изменён, второй файл не создан."""
    errs = []
    for n, (title, out_name, rep_name, existing) in enumerate((
            ("-o уже есть", "old.bpmn", "new.md", "old.bpmn"),
            ("--report уже есть", "new.bpmn", "old.md", "old.md"))):
        c = sub(d, "c%d" % n)
        base = write(c, "base.bpmn", schema())
        v1 = write(c, "v1.bpmn", schema(b_name="Б1", extra_proc=NOTE[0], extra_di=NOTE[1]))
        write(c, "old.bpmn", "OLD-OUT")
        write(c, "old.md", "OLD-REP")
        before = snapshot(c)
        try:
            code, txt = run_main([base, v1, "-o", os.path.join(c, out_name), "--report", os.path.join(c, rep_name)])
        except Exception as e:
            code, txt = None, ""
            errs.append("%s: упало %s: %s вместо отказа" % (title, type(e).__name__, e))
        after = snapshot(c)
        if code == 0:
            errs.append("%s: код выхода 0" % title)
        if after.get(existing) != before.get(existing):
            errs.append("%s: существующий %s перезаписан" % (title, existing))
        if set(after) != set(before):
            errs.append("%s: создан файл %s" % (title, sorted(set(after) - set(before))))
        if code not in (None, 0) and existing not in txt:
            errs.append("%s: в тексте отказа не назван %s: %r" % (title, existing, txt[-200:]))
    ok(not errs, "T-0221 AC-3: " + "; ".join(errs))


# ---------------------------------------------------------------- AC-4: ссылки данных, событий и чертежа

EV = '<bpmn:endEvent id="%s"><bpmn:%sEventDefinition id="%s_def"%s/></bpmn:endEvent>'


def ev(iid, kind, attr="", ref=""):
    return EV % (iid, kind, iid, ' %s="%s"' % (attr, ref) if attr else "")


TASK_X_IN = ('<bpmn:task id="X" name="Х"><bpmn:property id="X_p" name="__targetRef_placeholder"/>%s</bpmn:task>')
DIA = '<bpmn:dataInputAssociation id="DIA"><bpmn:sourceRef>DOR</bpmn:sourceRef><bpmn:targetRef>X_p</bpmn:targetRef></bpmn:dataInputAssociation>'
DOA = '<bpmn:dataOutputAssociation id="DOA"><bpmn:targetRef>DOR</bpmn:targetRef></bpmn:dataOutputAssociation>'
DO = '<bpmn:dataObject id="DO"/>'
DOR = '<bpmn:dataObjectReference id="DOR" name="Документ" dataObjectRef="DO"/>'
DOR_DI = '<bpmndi:BPMNShape id="DOR_di" bpmnElement="DOR"><dc:Bounds x="700" y="250" width="36" height="50"/></bpmndi:BPMNShape>'
X_TASK = '<bpmn:task id="X" name="Х"/>'
X_DI = '<bpmndi:BPMNShape id="X_di" bpmnElement="X"><dc:Bounds x="700" y="100" width="100" height="80"/></bpmndi:BPMNShape>'
FX = '<bpmn:sequenceFlow id="FX" sourceRef="A" targetRef="B"/>'


def fx_di(attrs):
    return ('<bpmndi:BPMNEdge id="FX_di" bpmnElement="FX" %s><di:waypoint x="300" y="160"/><di:waypoint x="400" y="160"/>'
            '</bpmndi:BPMNEdge>' % attrs)


def ac4_delete_refs(d):
    """T-0221 AC-4: удаление по --accept отказывает, если на элемент или его чертёж ссылаются
    sourceRef/targetRef-дети ассоциаций данных, messageRef, dataObjectRef, dataStoreRef, signalRef, errorRef,
    escalationRef, eventDefinitionRef, sourceElement/targetElement у BPMNEdge. Причина — в «Не получилось»."""
    cases = [  # (что ссылается, id на удаление, исходная, версия автора без этого id)
        ("sourceRef-ребёнок dataInputAssociation", "DOR",
         dict(extra_proc=DO + DOR + TASK_X_IN % DIA, extra_di=DOR_DI), dict(extra_proc=DO + TASK_X_IN % "")),
        ("targetRef-ребёнок dataOutputAssociation", "DOR",
         dict(extra_proc=DO + DOR + '<bpmn:task id="X" name="Х">%s</bpmn:task>' % DOA, extra_di=DOR_DI),
         dict(extra_proc=DO + X_TASK)),
        ("dataObjectRef", "DO", dict(extra_proc=DO + DOR, extra_di=DOR_DI), dict(extra_proc=DOR, extra_di=DOR_DI)),
        ("dataStoreRef", "DS",
         dict(extra_defs='<bpmn:dataStore id="DS" name="Хранилище"/>',
              extra_proc='<bpmn:dataStoreReference id="DSR" dataStoreRef="DS"/>'),
         dict(extra_proc='<bpmn:dataStoreReference id="DSR" dataStoreRef="DS"/>')),
        ("messageRef", "Msg", dict(extra_defs='<bpmn:message id="Msg" name="Письмо"/>',
                                   extra_proc=ev("E", "message", "messageRef", "Msg")),
         dict(extra_proc=ev("E", "message"))),
        ("signalRef", "Sig", dict(extra_defs='<bpmn:signal id="Sig" name="Сигнал"/>',
                                  extra_proc=ev("E", "signal", "signalRef", "Sig")),
         dict(extra_proc=ev("E", "signal"))),
        ("errorRef", "Err", dict(extra_defs='<bpmn:error id="Err" name="Ошибка"/>',
                                 extra_proc=ev("E", "error", "errorRef", "Err")),
         dict(extra_proc=ev("E", "error"))),
        ("escalationRef", "Esc", dict(extra_defs='<bpmn:escalation id="Esc" name="Эскалация"/>',
                                      extra_proc=ev("E", "escalation", "escalationRef", "Esc")),
         dict(extra_proc=ev("E", "escalation"))),
        ("eventDefinitionRef", "ED", dict(extra_defs='<bpmn:messageEventDefinition id="ED"/>',
                                          extra_proc='<bpmn:endEvent id="E"><bpmn:eventDefinitionRef>ED</bpmn:eventDefinitionRef>'
                                                     '</bpmn:endEvent>'),
         dict(extra_proc='<bpmn:endEvent id="E"/>')),
        ("sourceElement у BPMNEdge — на чертёж удаляемого", "X",
         dict(extra_proc=X_TASK + FX, extra_di=X_DI + fx_di('sourceElement="X_di"')),
         dict(extra_proc=FX, extra_di=fx_di('sourceElement="X_di"'))),
        ("targetElement у BPMNEdge — на чертёж удаляемого", "X",
         dict(extra_proc=X_TASK + FX, extra_di=X_DI + fx_di('targetElement="X_di"')),
         dict(extra_proc=FX, extra_di=fx_di('targetElement="X_di"'))),
    ]
    errs = []
    for n, (title, iid, b_kw, v_kw) in enumerate(cases):
        c = sub(d, "c%d" % n)
        base = write(c, "base.bpmn", schema(**b_kw))
        v = write(c, "v.bpmn", schema(**v_kw))
        r = bm.merge(base, [v], ["Сергей"], accept=[iid])
        m = r["merged"]
        if iid not in r["deletions"]:
            errs.append("%s: сломан сценарий — удаление %s не найдено" % (title, iid))
            continue
        if iid not in m.by_id:
            errs.append("%s: %s удалён по --accept, хотя на него ссылаются" % (title, iid))
        why = [f for f in r["failed"] if f[1] == iid]
        if not (why and all(str(f[2]).strip() for f in why)):
            errs.append("%s: отказ удалить %s без причины в «Не получилось»" % (title, iid))
        if r["problems"]:
            errs.append("%s: файл не цельный: %s" % (title, r["problems"]))
    # сторожа: сначала то, что ссылается, потом то, на что ссылаются, — удаляются оба, как в T-0196
    for title, b_kw, v_kw, acc in (
            ("--accept DIA,DOR", cases[0][2], dict(extra_proc=DO + '<bpmn:task id="X" name="Х"><bpmn:property id="X_p" '
                                                                 'name="__targetRef_placeholder"/></bpmn:task>'), ["DIA", "DOR"]),
            ("--accept FX,X", cases[9][2], dict(), ["FX", "X"])):
        c = sub(d, "ok_%s" % acc[0])
        base = write(c, "base.bpmn", schema(**b_kw))
        v = write(c, "v.bpmn", schema(**v_kw))
        r = bm.merge(base, [v], ["Сергей"], accept=acc)
        left = [i for i in acc + [i + "_di" for i in acc] if i in r["merged"].by_id]
        if left or r["problems"]:
            errs.append("%s: не удалено %s, «Не получилось» %s, проблемы %s" % (title, left, r["failed"], r["problems"]))
    ok(not errs, "T-0221 AC-4: " + "; ".join(errs))


def ref_doc(valid):
    """Схема со всеми видами ссылок из AC-4. valid=False — цели ссылок не определены (висячие)."""
    targets_defs = ('<bpmn:dataObject id="R_DO"/><bpmn:dataStore id="R_DS"/><bpmn:message id="R_MSG"/>'
                    '<bpmn:signal id="R_SIG"/><bpmn:error id="R_ERR"/><bpmn:escalation id="R_ESC"/>'
                    '<bpmn:messageEventDefinition id="R_EDR"/>')
    targets_proc = ('<bpmn:dataObjectReference id="R_SRC" dataObjectRef="R_DO"/>'
                    '<bpmn:dataObjectReference id="R_TGT" dataObjectRef="R_DO"/>')
    targets_di = ('<bpmndi:BPMNShape id="R_SE" bpmnElement="B"><dc:Bounds x="0" y="0" width="1" height="1"/></bpmndi:BPMNShape>'
                  '<bpmndi:BPMNShape id="R_TE" bpmnElement="B"><dc:Bounds x="0" y="0" width="1" height="1"/></bpmndi:BPMNShape>')
    proc = ('<bpmn:task id="X" name="Х"><bpmn:property id="X_p" name="p"/>'
            '<bpmn:dataInputAssociation id="DIA1"><bpmn:sourceRef>R_SRC</bpmn:sourceRef><bpmn:targetRef>X_p</bpmn:targetRef>'
            '</bpmn:dataInputAssociation>'
            '<bpmn:dataOutputAssociation id="DOA1"><bpmn:targetRef>R_TGT</bpmn:targetRef></bpmn:dataOutputAssociation></bpmn:task>'
            '<bpmn:dataObjectReference id="DOR1" dataObjectRef="R_DO"/>'
            '<bpmn:dataStoreReference id="DSR1" dataStoreRef="R_DS"/>'
            + ev("E1", "message", "messageRef", "R_MSG") + ev("E2", "signal", "signalRef", "R_SIG")
            + ev("E3", "error", "errorRef", "R_ERR") + ev("E4", "escalation", "escalationRef", "R_ESC")
            + '<bpmn:endEvent id="E5"><bpmn:eventDefinitionRef>R_EDR</bpmn:eventDefinitionRef></bpmn:endEvent>'
            + FX)
    di = fx_di('sourceElement="R_SE" targetElement="R_TE"')
    return schema(extra_proc=proc + (targets_proc if valid else ""), extra_di=di + (targets_di if valid else ""),
                  extra_defs=targets_defs if valid else "")


def ac4_check(d):
    """T-0221 AC-4: проверка целостности (check) называет висячие ссылки этих видов; цельный файл — без проблем."""
    ghosts = ["R_SRC", "R_TGT", "R_DO", "R_DS", "R_MSG", "R_SIG", "R_ERR", "R_ESC", "R_EDR", "R_SE", "R_TE"]
    good = bm.check(bm.Doc(write(d, "good.bpmn", ref_doc(valid=True))))
    bad = bm.check(bm.Doc(write(d, "bad.bpmn", ref_doc(valid=False))))
    missed = [g for g in ghosts if not any(g in p for p in bad)]
    errs = []
    if missed:
        errs.append("висячие ссылки не найдены: %s (найдено: %s)" % (missed, bad))
    if good:
        errs.append("в цельном файле найдены проблемы: %s" % good)
    ok(not errs, "T-0221 AC-4: check — " + "; ".join(errs))


# ---------------------------------------------------------------- AC-5: причина, почему элемент не добавлен

def ac5_failed_reason(d):
    """T-0221 AC-5: в «Не получилось» у недобавленного элемента — причина: куда он вложен у автора
    (id родителя) и что этого места в собранной нет; не только описание элемента."""
    base = write(d, "base.bpmn", schema())
    v_text = schema(extra_defs='<bpmn:message id="Msg1" name="Письмо"/>'
                               '<bpmn:process id="P2"><bpmn:task id="T9" name="Новый"/></bpmn:process>')
    v = write(d, "v.bpmn", v_text.replace('id="Defs"', 'id="Defs_V"', 1))   # у автора другой id корня
    r = bm.merge(base, [v], ["Андрей"], accept=[])
    errs = []
    for iid, parent in (("Msg1", "Defs_V"), ("T9", "P2")):
        if iid in r["merged"].by_id:
            errs.append("сломан сценарий — %s добавлен" % iid)
            continue
        why = [f for f in r["failed"] if f[1] == iid]
        if not why:
            errs.append("%s не добавлен и не в «Не получилось»" % iid)
        elif not any(parent in str(f[2]) for f in why):
            errs.append("у %s в причине не назван родитель %s, в который он вложен у автора: %s" % (iid, parent, why))
    text = bm.report(r, base, [v], ["Андрей"], os.path.join(d, "out.bpmn"))
    sec = text.split("## Не получилось", 1)[1].split("\n## ", 1)[0] if "## Не получилось" in text else ""
    line = [x for x in sec.splitlines() if x.startswith("- `Msg1`")]
    if not (line and "Defs_V" in line[0]):
        errs.append("в отчёте в «## Не получилось» у Msg1 не видно, куда он вложен у автора: %s" % line)
    ok(not errs, "T-0221 AC-5: " + "; ".join(errs))


CHECKS = [("T-0221 AC-1 все дорожки блока", ac1_lane_sets), ("T-0221 AC-2 порядок записи", ac2_write_order),
          ("T-0221 AC-2 папка без права записи", ac2_readonly_dir), ("T-0221 AC-3 без перезаписи", ac3_no_overwrite),
          ("T-0221 AC-4 удаление и ссылки", ac4_delete_refs), ("T-0221 AC-4 check", ac4_check),
          ("T-0221 AC-5 причина «Не получилось»", ac5_failed_reason)]


def main():
    fails = []
    with tempfile.TemporaryDirectory(prefix="bpmn_merge_t0221_") as d:
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
