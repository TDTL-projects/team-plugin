#!/usr/bin/env node
// Навык dedal-dev (T-0776): проверка текста записи в трекер до отправки.
// Сторож трекера прячет записи с длинными номерами: вместо текста видно «запись на проверке», метка пропадает.
// Код 1 и подсказка, если в тексте 7+ цифр подряд или шестнадцатеричный хеш длиннее 7 знаков; иначе код 0.
//   node check-text.mjs "текст записи"     (без аргумента — текст из stdin)
// Без сети, без внешних команд, файлы не пишет.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// 7+ цифр подряд, не внутри слова из латиницы и цифр
const LONG_NUMBER = /(?<![0-9A-Za-z])\d{7,}(?![0-9A-Za-z])/g;
// хеш: 8+ знаков 0-9a-f, хотя бы одна цифра и одна буква (чистые цифры ловит правило выше, слова из a-f без цифр — не хеш)
const HASH = /(?<![0-9A-Za-z])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{8,}(?![0-9A-Za-z])/gi;

/** @param {string} text @returns {{ ok: boolean, found: { piece: string, why: string }[] }} */
export function check(text) {
  const found = [];
  for (const m of String(text).matchAll(LONG_NUMBER)) found.push({ piece: m[0], why: "7 и больше цифр подряд" });
  for (const m of String(text).matchAll(HASH)) found.push({ piece: m[0], why: "хеш длиннее 7 знаков" });
  return { ok: found.length === 0, found };
}

export function main(argv) {
  let text = argv.join(" ");
  if (!argv.length) {
    if (process.stdin.isTTY) {
      console.error('как вызвать: node check-text.mjs "текст записи"');
      return 2;
    }
    text = readFileSync(0, "utf8");
  }
  const r = check(text);
  if (r.ok) {
    console.log("можно писать");
    return 0;
  }
  console.log(["сторож трекера спрячет запись:", ...r.found.map((f) => `- ${f.piece} — ${f.why}`),
    "как исправить: номер запуска, полный хеш и длинные числа — только в ссылки (поле links); в тексте — коротко: «коммит abc123» (6 знаков), «PR #N»."].join("\n"));
  return 1;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) process.exit(main(process.argv.slice(2)));
