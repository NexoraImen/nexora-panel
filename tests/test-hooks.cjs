/**
 * قاعده‌ی هوک‌های React: همیشه همه، همیشه به یک ترتیب.
 *
 * چرا این تست وجود دارد:
 *     یک کامپوننت که اول «اگر داده نیامده، اسپینر نشان بده» برمی‌گردد
 *     و *بعد* یک هوک صدا می‌زند، در رندر اول آن هوک را اجرا نمی‌کند و
 *     در رندر دوم می‌کند. React این را با خطای #310 می‌گیرد و کل
 *     صفحه سیاه می‌شود — نه یک پیام خطا، نه یک بخش خراب: هیچ.
 *
 *     تست رندر کامپوننت‌ها این را نمی‌گیرد، چون هر کامپوننت را یک‌بار
 *     با داده سوار می‌کند و گذارِ «خالی ← پر» اصلاً اتفاق نمی‌افتد.
 *
 *     این بررسی ساده است و به مرورگر نیاز ندارد: هر هوکی که در بدنه‌ی
 *     کامپوننت بعد از یک return شرطی بیاید، خطاست.
 *
 * اجرا:  node tests/test-hooks.cjs
 */
const fs = require("fs");
const path = require("path");

const G = "\x1b[38;5;42m", R = "\x1b[38;5;203m", D = "\x1b[38;5;245m", X = "\x1b[0m";
let ok = 0, fail = 0;

function check(name, cond, detail) {
  if (cond) { ok++; console.log(`  ${G}✓${X} ${name}` + (detail ? ` ${D}— ${detail}${X}` : "")); }
  else { fail++; console.log(`  ${R}✗${X} ${name}` + (detail ? ` ${D}— ${detail}${X}` : "")); }
}

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name.endsWith(".jsx")) out.push(p);
  }
  return out;
}

const ROOT = path.join(__dirname, "..", "frontend", "src");
const files = walk(ROOT);

//: هوک در بدنه‌ی کامپوننت دقیقاً دو فاصله تورفتگی دارد. صدازدن‌های
//: تودرتو (داخل یک callback) بیشتر تورفته‌اند و قاعده شاملشان نیست.
const HOOK = /^ {2}[^/*].*\buse[A-Z]\w*\s*\(/;
const COMPONENT = /^(?:export\s+)?function\s+[A-Z]\w*\s*\(/;

const problems = [];

for (const file of files) {
  const lines = fs.readFileSync(file, "utf8").split("\n");
  let inComp = null;

  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];

    if (COMPONENT.test(l)) { inComp = { name: l.trim(), start: i, guard: 0 }; continue; }
    if (!inComp) continue;
    if (l === "}") { inComp = null; continue; }

    // نگهبانِ زودهنگام: «if (...) {» در سطح بدنه که داخلش return دارد
    if (/^ {2}if\s*\(/.test(l)) {
      for (let j = i + 1; j < lines.length; j++) {
        if (lines[j] === "  }" || /^ {2}\}/.test(lines[j])) {
          if (lines.slice(i, j).some((x) => /^ {4}return\b/.test(x))) {
            inComp.guard = j;
          }
          break;
        }
      }
      continue;
    }

    if (inComp.guard && i > inComp.guard && HOOK.test(l)) {
      problems.push({
        file: path.relative(ROOT, file),
        line: i + 1,
        comp: inComp.name.replace(/^export\s+/, "").split("(")[0],
        code: l.trim().slice(0, 60),
      });
    }
  }
}

console.log(`\n${D}── هوک بعد از return شرطی ──${X}`);
check(`${files.length} فایل بررسی شد`, files.length > 0, `${files.length} فایل jsx`);
check("هیچ هوکی بعد از return شرطی صدا زده نمی‌شود",
  problems.length === 0,
  problems.map((p) => `${p.file}:${p.line} در ${p.comp} → ${p.code}`).join(" | "));

console.log(`\n${D}${"─".repeat(50)}${X}`);
console.log(`  ${fail ? R : G}${ok} پاس${X}` + (fail ? ` · ${R}${fail} ناموفق${X}` : ""));
if (!fail) console.log(`  ${D}صفحه‌ای با خطای #310 سیاه نمی‌شود${X}`);
console.log();
process.exit(fail ? 1 : 0);
