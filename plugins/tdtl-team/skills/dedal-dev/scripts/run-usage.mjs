#!/usr/bin/env node
// Навык dedal-dev (T-0776, учёт расхода T-0772): сумма токенов текущей сессии Claude Code для строки «сессия» в dev_run.
//   node run-usage.mjs [путь к расшифровке .jsonl]
// Без аргумента — самый свежий *.jsonl в ~/.claude/projects/<папка текущего каталога>/, нет — самый свежий во всех папках (T-0814) (имя папки — путь cwd,
// где «/» и «.» заменены на «-»; корень настроек можно сменить переменной CLAUDE_CONFIG_DIR).
// Печатает JSON {tokens_in, tokens_out, tokens_total, tool_calls, started_at, ended_at, model}.
// Нет файла — печатает {} и код 0: честно, среда не отдала.
//
// ВНИМАНИЕ: формат расшифровки и полей message.usage в документации Claude Code не описан. Здесь — то, что видно в файлах
// на 27.11.2026; проверит проба T-0782. Что заметили:
//  - один ответ модели пишется несколькими записями type=assistant (по одной на блок content) с тем же message.id
//    и той же usage — usage берём один раз на message.id (последнюю), иначе сумма раздувается в 2–7 раз;
//  - tokens_in = input_tokens + cache_read_input_tokens + cache_creation_input_tokens; tokens_out = output_tokens;
//  - записи субагентов (isSidechain) не считаем: их пишут строками ролей из ответа вызова субагента;
//  - вызовы инструментов — блоки content с type=tool_use; длительность — от первой до последней отметки timestamp.
// Без сети, без внешних команд, файлы не пишет.
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

/** Папка расшифровок для каталога cwd. */
export function projectDir(cwd, base = process.env.CLAUDE_CONFIG_DIR || join(homedir(), ".claude")) {
  return join(base, "projects", cwd.replace(/[/.]/g, "-"));
}

/** Самый свежий *.jsonl в папке (по времени изменения) или null. */
export function latestJsonl(dir) {
  if (!existsSync(dir)) return null;
  let best = null;
  let names;
  try { names = readdirSync(dir); } catch { return null; }   // не папка (.DS_Store и т.п.)
  for (const name of names) {
    if (!name.endsWith(".jsonl")) continue;
    const p = join(dir, name);
    let st;
    try { st = statSync(p); } catch { continue; }
    if (!st.isFile()) continue;
    if (!best || st.mtimeMs > best.t) best = { p, t: st.mtimeMs };
  }
  return best ? best.p : null;
}

const n = (v) => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/** Сумма по строкам расшифровки. Пустой результат — {}. */
export function summarize(text) {
  const usage = new Map(); // message.id → {usage, model}
  let anon = 0;
  const tools = new Set();
  let toolsNoId = 0;
  let first = null, last = null;
  for (const line of String(text).split("\n")) {
    if (!line.trim()) continue;
    let o;
    try { o = JSON.parse(line); } catch { continue; }
    if (!o || typeof o !== "object") continue;
    if (o.isSidechain === true) continue;
    if (typeof o.timestamp === "string" && !Number.isNaN(Date.parse(o.timestamp))) {
      if (!first || Date.parse(o.timestamp) < Date.parse(first)) first = o.timestamp;
      if (!last || Date.parse(o.timestamp) > Date.parse(last)) last = o.timestamp;
    }
    if (o.type !== "assistant" || !o.message || typeof o.message !== "object") continue;
    const m = o.message;
    if (m.usage && typeof m.usage === "object") usage.set(m.id ? `id:${m.id}` : `anon:${anon++}`, { u: m.usage, model: m.model });
    if (Array.isArray(m.content)) {
      for (const c of m.content) {
        if (c && c.type === "tool_use") c.id ? tools.add(c.id) : toolsNoId++;
      }
    }
  }
  if (!usage.size && !first) return {};
  let tin = 0, tout = 0;
  const models = new Map();
  for (const { u, model } of usage.values()) {
    tin += n(u.input_tokens) + n(u.cache_read_input_tokens) + n(u.cache_creation_input_tokens);
    tout += n(u.output_tokens);
    if (typeof model === "string" && model && !model.startsWith("<")) models.set(model, (models.get(model) ?? 0) + 1);
  }
  const model = [...models.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? null;
  return { tokens_in: tin, tokens_out: tout, tokens_total: tin + tout, tool_calls: tools.size + toolsNoId,
    started_at: first, ended_at: last, model };
}

/** Самый свежий *.jsonl ведущей сессии во всех папках проектов (T-0814): расшифровка лежит в папке каталога, где сессия
 *  началась (в облаке — /home/user), а Дедал к концу запуска стоит в рабочей копии — поиск по cwd давал {}.
 *  Субагенты пишут в <папка>/<сессия>/subagents/ — туда не заходим. */
export function latestAnyJsonl(base = process.env.CLAUDE_CONFIG_DIR || join(homedir(), ".claude")) {
  const root = join(base, "projects");
  if (!existsSync(root)) return null;
  let best = null;
  for (const name of readdirSync(root)) {
    const p = latestJsonl(join(root, name));
    if (!p) continue;
    let t;
    try { t = statSync(p).mtimeMs; } catch { continue; }
    if (!best || t > best.t) best = { p, t };
  }
  return best ? best.p : null;
}

export function main(argv) {
  // самый свежий из папки каталога и из всех папок: в папке рабочей копии может лежать старая расшифровка
  const here = latestJsonl(projectDir(process.cwd())), any = latestAnyJsonl();
  const mt = (p) => { try { return p ? statSync(p).mtimeMs : -1; } catch { return -1; } };
  const file = argv[0] || (mt(any) > mt(here) ? any : here);
  let text;
  try { text = file ? readFileSync(file, "utf8") : null; } catch { text = null; }
  console.log(JSON.stringify(text === null ? {} : summarize(text)));
  return 0;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) process.exit(main(process.argv.slice(2)));
