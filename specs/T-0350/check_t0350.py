#!/usr/bin/env python3
"""T-0350: проверка текстов плагина по спеке specs/T-0350/spec.md.

Только читает файлы репозитория: без сети, внешних команд и удаления.
Запуск из любой папки: python3 -I specs/T-0350/check_t0350.py
Код 0 — все проверки прошли, 1 — есть FAIL.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "tdtl-team"
SKILLS = PLUGIN / "skills"
AGENTS = PLUGIN / "agents"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(path):
    return path.read_text(encoding="utf-8")


def norm(s):
    return re.sub(r"\s+", " ", s.replace("*", "")).strip()


def frontmatter(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fields = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def description(path):
    fm = frontmatter(read(path)) or {}
    return fm.get("description", "")


def table_rows(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            rows.append([norm(c) for c in line.strip().strip("|").split("|")])
    return rows


take = read(SKILLS / "take-task" / "SKILL.md")
ast = read(SKILLS / "asterion" / "SKILL.md")
dedal = read(SKILLS / "dedal" / "SKILL.md")
wave = read(SKILLS / "wave" / "SKILL.md")
pm = read(SKILLS / "pm" / "SKILL.md")
hww = read(SKILLS / "how-we-work" / "SKILL.md")
reviewer = read(AGENTS / "reviewer.md")
spec_tests = read(AGENTS / "spec-tests.md")
readme = read(ROOT / "README.md")

# --- Заголовки name/description у всех SKILL.md и агентов (сторож) ---
for path in sorted(SKILLS.glob("*/SKILL.md")) + sorted(AGENTS.glob("*.md")):
    fm = frontmatter(read(path))
    expected = path.parent.name if path.name == "SKILL.md" else path.stem
    ok = fm is not None and fm.get("name") == expected and len(fm.get("description", "")) > 20
    check(f"заголовок {path.relative_to(ROOT)}", ok, "нет name/description или name не совпадает с папкой")

# --- AC-1: таблица линий и строка «вне линий» в take-task ---
HEADER = ["Линия", "Проекты", "Репозитории", "Техлид / конвейер / проверяющий", "Владелец линии",
          "«Да» на волну", "Секреты и боевая база", "Аккаунт GitHub", "Уведомления проверяющего"]
ROW_TL = ["TradeLab", "все проекты без своего конвейера (T-0349)",
          "все репозитории TDTL-projects, кроме репозиториев других линий и вне линий "
          "(сейчас это tradelab-app, tl-pm-demo, team-plugin)",
          "Дедал / Конвейер / Астерион", "Ерлан", "Ерлан", "Ерлан", "Ерлана",
          "push Ерлану (`PushNotification`)"]
ROW_TD = ["ТД+XP", "P-08", "DocsSystem", "Хугин / Паровоз / Мунин", "Наиль", "Наиль", "Наиль", "Наиля",
          "сообщение Наилю (`send_message`, без `weekend`)"]
OUT_LINE = ("Вне линий: module_dt_check (SP-24), владелец Наиль — задачи с этим репозиторием в «К разработке» "
            "не ставят и ни один конвейер их не ведёт, PR не берёт ни один проверяющий; слияние и выкладка — "
            "по команде владельца.")

rows = table_rows(take)
check("AC-1 заголовок таблицы линий", HEADER in rows)
check("AC-1 строка TradeLab", ROW_TL in rows)
check("AC-1 строка ТД+XP", ROW_TD in rows)
check("AC-1 строка «вне линий»", any(norm(l) == OUT_LINE for l in take.splitlines()))
h_pos = take.find("| Линия | Проекты |")
m_pos = take.find("## Метки в журнале")
check("AC-1 таблица линий перед «Метки в журнале»", 0 <= h_pos < m_pos)
others = [p for p in list(SKILLS.glob("*/SKILL.md")) + list(AGENTS.glob("*.md")) + [ROOT / "README.md"]
          if p != SKILLS / "take-task" / "SKILL.md"]
check("AC-1 таблица линий только в take-task", all("| Линия | Проекты |" not in read(p) for p in others))
check("AC-1 module_dt_check назван только в take-task",
      all("module_dt_check" not in read(p) for p in others))

# --- AC-2: метки, вердикты, «да», причины остановки ---
for label in ["«Паровоз: запуск начат»", "«Мунин: проверка не ослаблена — PR #N»"]:
    check(f"AC-2 пример метки {label} в take-task", label in take)
check("AC-2 вердикт: участник «Мунин»", "участник «Мунин»" in take)
check("AC-2 вердикт: участник «Наиль»", "участник «Наиль»" in take)
check("AC-2 записи другой линии не засчитываются",
      "записи участников другой линии не засчитываются" in take.lower())
for name, text in [("take-task", take), ("asterion", ast)]:
    check(f"AC-2 «да» Наиля по участнику в {name}", "участника «Наиль»" in text)
    for reason in ["«вердикт Мунина по зерну»", "«вердикт Мунина по PR #N»", "«да Наиля на слияние»",
                   "«вердикт Астериона по зерну»", "«вердикт Астериона по PR #N»", "«да Ерлана на слияние»"]:
        check(f"AC-2 причина {reason} в {name}", reason in text)
    check(f"AC-2 рабочие базы DocsSystem ссылкой на её CLAUDE.md в {name}",
          any("DocsSystem" in l and "CLAUDE.md" in l for l in text.splitlines()))
check("AC-2 возврат «вне линий»: запись в журнал",
      "запуск закончен: репозиторий вне линий — вернул владельцу" in take)
check("AC-2 возврат «вне линий»: причина передачи", "репозиторий вне линий — ведёт владелец" in take)
check("AC-2 в take-task нет «(обычно Ерлан)»", "(обычно Ерлан)" not in take)
check("AC-2 в take-task нет «ответ Ерлану готовит Астерион»", "ответ Ерлану готовит Астерион" not in take)
check("AC-2 в asterion нет «с аккаунта Ерлана»", "с аккаунта Ерлана" not in ast)
check("AC-2 в asterion нет «Что ждёт Ерлана»", "Что ждёт Ерлана" not in ast)
check("AC-2 метка «Мунин: Наилю отправлено — …» в asterion", "«Мунин: Наилю отправлено — …»" in ast)
check("AC-2 asterion: send_message", "send_message" in ast)
# прежние тексты TradeLab на месте
for s in ["«Конвейер: запуск начат»", "участник «Астерион»", "«да»"]:
    check(f"AC-2 TradeLab: {s} в take-task", s in take)
for s in ["«Астерион: Ерлану отправлено — …»", "PushNotification"]:
    check(f"AC-2 TradeLab: {s} в asterion", s in ast)

# --- AC-3: обращения в description ---
check("AC-3 take-task: «Паровоз, возьми T-…»", "Паровоз, возьми T-…" in description(SKILLS / "take-task" / "SKILL.md"))
check("AC-3 asterion: «Мунин, проверь …»", "Мунин, проверь" in description(SKILLS / "asterion" / "SKILL.md"))
check("AC-3 dedal: «Хугин, …»", "Хугин, …" in description(SKILLS / "dedal" / "SKILL.md"))
check("AC-3 прежние обращения целы",
      "Астерион, …" in description(SKILLS / "asterion" / "SKILL.md")
      and "Дедал, …" in description(SKILLS / "dedal" / "SKILL.md")
      and "возьми T-…" in description(SKILLS / "take-task" / "SKILL.md"))

# --- AC-4: wave, dedal, разделы «Для разработки» ---
check("AC-4 в wave нет «Ерлан»", "Ерлан" not in wave)
check("AC-4 wave ссылается на таблицу линий", "владел" in wave and "take-task" in wave)
check("AC-4 dedal: раздел «Для разработки (Хугин)»", "## Для разработки (Хугин)" in dedal)
check("AC-4 dedal: DocsSystem в строке «Репозиторий»",
      any(l.startswith("- Репозиторий:") and "DocsSystem" in l for l in dedal.splitlines()))
for name, text in [("take-task", take), ("asterion", ast)]:
    check(f"AC-4 {name}: оба заголовка «Для разработки»",
          "Для разработки (Дедал)" in text and "Для разработки (Хугин)" in text)
check("AC-4 pm: «Мунин, проверь зерно T-…»", "Мунин, проверь зерно T-…" in pm)
check("AC-4 pm: «Хугин, допиши для разработки T-…»", "Хугин, допиши для разработки T-…" in pm)

# --- AC-5: каждый бот видит только свою линию ---
check("AC-5 asterion: `project: P-08`", "project: P-08" in ast)
check("AC-5 asterion: `project: -P-08`", "project: -P-08" in ast)
check("AC-5 take-task: нет «ответственный «Конвейер»»", "ответственный «Конвейер»" not in take)
check("AC-5 asterion: нет «ответственный «Конвейер»»", "ответственный «Конвейер»" not in ast)
check("AC-5 asterion: «вне линий» не смотрит никто", "вне линий" in ast)

# --- AC-6: версия, README, how-we-work; служебное ---
version = json.loads(read(PLUGIN / ".claude-plugin" / "plugin.json")).get("version")
check("AC-6 версия 0.17.0", version == "0.17.0", f"сейчас {version}")
check("AC-6 README: Хугин, Паровоз, Мунин", all(n in readme for n in ["Хугин", "Паровоз", "Мунин"]))
check("AC-6 how-we-work: одна строка о ТД+XP",
      sum(1 for l in hww.splitlines() if "ТД+XP" in l) == 1)
check("reviewer: «да» владельца линии", "владельца линии" in reviewer)
check("spec-tests: проверяющий линии", "проверяющ" in spec_tests)
all_text = [read(p) for p in list(SKILLS.glob("*/SKILL.md")) + list(AGENTS.glob("*.md"))]
check("нет «сервер СЭД» в навыках", all("сервер СЭД" not in t for t in all_text))

failed = 0
for name, ok, detail in results:
    print(("OK   " if ok else "FAIL ") + name + ("" if ok or not detail else f" — {detail}"))
    failed += 0 if ok else 1
print(f"\nИтог: {len(results) - failed} OK, {failed} FAIL")
sys.exit(1 if failed else 0)
