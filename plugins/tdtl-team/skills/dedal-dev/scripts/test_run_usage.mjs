// node --test plugins/tdtl-team/skills/dedal-dev/scripts/test_*.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, utimesSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { projectDir, latestJsonl, latestAnyJsonl, summarize, main } from "./run-usage.mjs";

const rec = (o) => JSON.stringify(o);
const usage = (i, o, cr = 0, cc = 0) => ({ input_tokens: i, output_tokens: o, cache_read_input_tokens: cr, cache_creation_input_tokens: cc });

test("папка проекта: «/» и «.» — в «-»", () => {
  assert.equal(projectDir("/home/user/tl-pm-demo", "/b"), join("/b", "projects", "-home-user-tl-pm-demo"));
  assert.equal(projectDir("/home/u/my.app", "/b"), join("/b", "projects", "-home-u-my-app"));
});

test("сумма: usage один раз на message.id, вызовы инструментов, время, модель", () => {
  const text = [
    rec({ type: "user", timestamp: "2026-11-27T10:00:00.000Z", message: { role: "user", content: "привет" } }),
    // один ответ модели — две записи с тем же id и той же usage
    rec({ type: "assistant", timestamp: "2026-11-27T10:00:05.000Z", message: { id: "m1", model: "claude-opus-5-5", usage: usage(2, 300, 1000, 500), content: [{ type: "text", text: "…" }] } }),
    rec({ type: "assistant", timestamp: "2026-11-27T10:00:06.000Z", message: { id: "m1", model: "claude-opus-5-5", usage: usage(2, 300, 1000, 500), content: [{ type: "tool_use", id: "t1", name: "Bash" }] } }),
    rec({ type: "assistant", timestamp: "2026-11-27T10:01:00.000Z", message: { id: "m2", model: "claude-opus-5-5", usage: usage(1, 100), content: [{ type: "tool_use", id: "t2" }, { type: "tool_use", id: "t3" }] } }),
    // субагент в том же файле — не считаем
    rec({ type: "assistant", isSidechain: true, timestamp: "2026-11-27T11:00:00.000Z", message: { id: "s1", model: "claude-sonnet-5-5", usage: usage(9, 9999), content: [{ type: "tool_use", id: "t9" }] } }),
    "не json",
    "",
    rec({ type: "system", timestamp: "2026-11-27T10:05:00.000Z" }),
  ].join("\n");
  assert.deepEqual(summarize(text), {
    tokens_in: 2 + 1000 + 500 + 1, tokens_out: 400, tokens_total: 1503 + 400, tool_calls: 3,
    started_at: "2026-11-27T10:00:00.000Z", ended_at: "2026-11-27T10:05:00.000Z", model: "claude-opus-5-5",
  });
});

test("пустая расшифровка — {}", () => {
  assert.deepEqual(summarize(""), {});
  assert.deepEqual(summarize("мусор\n{}\n"), {});
});

test("самый свежий .jsonl; нет папки — null", () => {
  const dir = mkdtempSync(join(tmpdir(), "run-usage-"));
  writeFileSync(join(dir, "old.jsonl"), "");
  writeFileSync(join(dir, "new.jsonl"), "");
  writeFileSync(join(dir, "notes.txt"), "");
  utimesSync(join(dir, "old.jsonl"), new Date("2026-01-01"), new Date("2026-01-01"));
  utimesSync(join(dir, "new.jsonl"), new Date("2026-11-27"), new Date("2026-11-27"));
  assert.equal(latestJsonl(dir), join(dir, "new.jsonl"));
  assert.equal(latestJsonl(join(dir, "нет")), null);
});

test("нет файла — печатает {} и код 0", () => {
  const out = [];
  const log = console.log;
  console.log = (s) => out.push(String(s));
  try { assert.equal(main([join(tmpdir(), "нет-такой-расшифровки.jsonl")]), 0); } finally { console.log = log; }
  assert.deepEqual(out, ["{}"]);
});

test("T-0814: latestAnyJsonl — самый свежий во всех папках проектов, без subagents", () => {
  const base = mkdtempSync(join(tmpdir(), "ru-any-"));
  const a = join(base, "projects", "-home-user"), b = join(base, "projects", "-home-user-app");
  mkdirSync(join(a, "s1", "subagents"), { recursive: true });
  mkdirSync(b, { recursive: true });
  writeFileSync(join(a, "s1.jsonl"), "{}\n");
  writeFileSync(join(b, "old.jsonl"), "{}\n");
  writeFileSync(join(a, "s1", "subagents", "agent-x.jsonl"), "{}\n");
  const now = Date.now() / 1000;
  utimesSync(join(b, "old.jsonl"), now - 100, now - 100);
  utimesSync(join(a, "s1.jsonl"), now - 10, now - 10);
  utimesSync(join(a, "s1", "subagents", "agent-x.jsonl"), now, now);
  assert.equal(latestAnyJsonl(base), join(a, "s1.jsonl"));
  assert.equal(latestAnyJsonl(join(base, "нет")), null);
});
