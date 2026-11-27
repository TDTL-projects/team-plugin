// node --test plugins/tdtl-team/skills/dedal-dev/scripts/test_*.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { check, main } from "./check-text.mjs";

function run(argv) {
  const out = [];
  const log = console.log;
  console.log = (s) => out.push(String(s));
  try { return { code: main(argv), out: out.join("\n") }; } finally { console.log = log; }
}

test("обычный текст — можно", () => {
  for (const t of ["Дедал: запуск начат — повод queue, режим быстрый", "PR #162, коммит 65f8ab, T-0776", "версия 12, 6 знаков: abc123",
    "в среду 27.11.2026 в 12:04", "1 234 567 — с пробелами", "семь знаков хеша: abc1234", "слово decade и facade — не хеш"]) {
    assert.equal(check(t).ok, true, t);
  }
});

test("7 и больше цифр подряд — нельзя", () => {
  const r = check("запуск CI 19712345678 упал");
  assert.equal(r.ok, false);
  assert.deepEqual(r.found.map((f) => f.piece), ["19712345678"]);
  assert.equal(check("номер 1234567").ok, false);
  assert.equal(check("номер 123456").ok, true);
});

test("хеш длиннее 7 знаков — нельзя, и полный хеш тоже", () => {
  assert.equal(check("коммит 65f8ab3c").ok, false);
  assert.equal(check("коммит 65F8AB3C").ok, false);
  assert.equal(check("коммит c9a70959c64c2a299a08749afb1844537abe962c").ok, false);
  assert.equal(check("ссылка https://github.com/o/r/commit/c9a70959c64c2a299a08749afb1844537abe962c").ok, false);
});

test("кусок внутри слова не считается", () => {
  assert.equal(check("ключ run_key=abc1234567x").ok, true); // буква сразу после — не отдельное число
  assert.equal(check("T-0776").ok, true);
});

test("код выхода и подсказка", () => {
  const bad = run(["запуск", "19712345678"]);
  assert.equal(bad.code, 1);
  assert.match(bad.out, /19712345678 — 7 и больше цифр подряд/);
  assert.match(bad.out, /только в ссылки/);
  const ok = run(["Дедал:", "запуск", "закончен"]);
  assert.equal(ok.code, 0);
  assert.match(ok.out, /можно писать/);
});
