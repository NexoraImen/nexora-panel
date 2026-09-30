/**
 * تبدیل تاریخ شمسی ↔ میلادی.
 *
 * چرا تست دارد:
 *     تقویم جای حدس‌زدن نیست. یک روز خطا در تبدیل یعنی تاریخ شروع
 *     همکاری یک روز جابه‌جا ثبت می‌شود، و آن مستقیم روی تعداد ماه و
 *     مبلغ صورت‌حساب می‌نشیند.
 *
 *     تاریخ‌های مرجع پایین از تبدیل‌های شناخته‌شده‌اند: آغاز سال،
 *     پایان سال کبیسه، و روزهایی که ماه میلادی و شمسی هم‌زمان عوض
 *     می‌شوند — همان‌جاهایی که الگوریتم‌های نادرست می‌شکنند.
 *
 * اجرا:  node tests/test-jalali.cjs
 */
const path = require("path");
const fs = require("fs");

const ROOT = path.dirname(__dirname);
const G = "\x1b[38;5;42m", R = "\x1b[38;5;203m",
      D = "\x1b[38;5;245m", X = "\x1b[0m";
let ok = 0, fail = 0;

function check(name, cond, detail) {
  if (cond) {
    ok++;
    console.log(`  ${G}✓${X} ${name}` + (detail ? ` ${D}— ${detail}${X}` : ""));
  } else {
    fail++;
    console.log(`  ${R}✗${X} ${name}` + (detail ? ` ${D}— ${detail}${X}` : ""));
  }
}
function head(t) { console.log(`\n${D}── ${t} ──${X}`); }

let esbuild;
try { esbuild = require("esbuild"); } catch {
  console.log("esbuild پیدا نشد"); process.exit(1);
}

const OUT = path.join(ROOT, "frontend", ".test-build-jalali");
fs.rmSync(OUT, { recursive: true, force: true });
esbuild.buildSync({
  entryPoints: [path.join(ROOT, "frontend", "src", "ui", "jalali.jsx")],
  bundle: true, format: "cjs", platform: "node",
  outfile: path.join(OUT, "jalali.cjs"), jsx: "automatic",
  external: ["react", "lucide-react"], logLevel: "silent",
});
const J = require(path.join(OUT, "jalali.cjs"));

// ═══════════ تاریخ‌های مرجع ═══════════
// [سال, ماه, روز میلادی] ↔ [سال, ماه, روز شمسی]
const PAIRS = [
  [[2024, 3, 20], [1403, 1, 1]],    // آغاز سال ۱۴۰۳
  [[2025, 3, 21], [1404, 1, 1]],    // آغاز سال ۱۴۰۴
  [[2026, 3, 21], [1405, 1, 1]],    // آغاز سال ۱۴۰۵
  [[2024, 9, 22], [1403, 7, 1]],    // اول مهر
  [[2024, 12, 21], [1403, 10, 1]],  // اول دی
  [[2025, 3, 20], [1403, 12, 30]],  // آخرین روز ۱۴۰۳ — سال کبیسه
  [[2023, 3, 21], [1402, 1, 1]],
  [[2022, 6, 22], [1401, 4, 1]],    // اول تیر
  [[2026, 9, 12], [1405, 6, 21]],   // امروز
];

head("میلادی → شمسی");
for (const [[gy, gm, gd], [jy, jm, jd]] of PAIRS) {
  const r = J.toJalali(gy, gm, gd);
  check(`${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`
        + ` → ${jy}/${jm}/${jd}`,
        r.jy === jy && r.jm === jm && r.jd === jd,
        `${r.jy}/${r.jm}/${r.jd}`);
}

head("شمسی → میلادی");
for (const [[gy, gm, gd], [jy, jm, jd]] of PAIRS) {
  const d = J.toGregorian(jy, jm, jd);
  const got = [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()];
  check(`${jy}/${jm}/${jd} → ${gy}-${gm}-${gd}`,
        got[0] === gy && got[1] === gm && got[2] === gd,
        got.join("-"));
}

head("رفت و برگشت روی هزار روز پشت سر هم");
let bad = 0, firstBad = "";
let d = Date.UTC(2020, 0, 1);
for (let i = 0; i < 1000; i++) {
  const cur = new Date(d + i * 86400000);
  const gy = cur.getUTCFullYear(), gm = cur.getUTCMonth() + 1,
        gd = cur.getUTCDate();
  const j = J.toJalali(gy, gm, gd);
  const back = J.toGregorian(j.jy, j.jm, j.jd);
  if (back.getUTCFullYear() !== gy || back.getUTCMonth() + 1 !== gm
      || back.getUTCDate() !== gd) {
    bad++;
    if (!firstBad) {
      firstBad = `${gy}-${gm}-${gd} → ${j.jy}/${j.jm}/${j.jd} → `
        + `${back.getUTCFullYear()}-${back.getUTCMonth() + 1}-${back.getUTCDate()}`;
    }
  }
}
check("هر تاریخ به خودش برمی‌گردد", bad === 0,
      bad ? `${bad} خطا — اولی: ${firstBad}` : "۱۰۰۰ روز");

head("سال کبیسه");
// ۱۴۰۳ کبیسه است (اسفند ۳۰ روز)، ۱۴۰۴ نیست
const leap1403 = J.toJalali(2025, 3, 20);
check("۳۰ اسفند ۱۴۰۳ وجود دارد",
      leap1403.jy === 1403 && leap1403.jm === 12 && leap1403.jd === 30,
      `${leap1403.jy}/${leap1403.jm}/${leap1403.jd}`);
const after = J.toJalali(2026, 3, 20);
check("۱۴۰۴ کبیسه نیست — اسفندش ۲۹ روز است",
      after.jm === 12 && after.jd === 29,
      `${after.jy}/${after.jm}/${after.jd}`);

head("برچسب فارسی");
check("برچسب درست ساخته می‌شود",
      J.isoToJalaliLabel("2024-09-22") === "۱ مهر ۱۴۰۳",
      J.isoToJalaliLabel("2024-09-22"));
check("ارقام فارسی‌اند",
      /^[۰-۹]/.test(J.isoToJalaliLabel("2024-12-21")),
      J.isoToJalaliLabel("2024-12-21"));
check("ورودی خالی خطا نمی‌دهد", J.isoToJalaliLabel("") === "");
check("ورودی خراب همان‌طور برمی‌گردد",
      J.isoToJalaliLabel("چیز") === "چیز");
check("ورودی null خطا نمی‌دهد", J.isoToJalaliLabel(null) === "");
// رشته‌ی از قبل شمسی دوباره تبدیل نمی‌شود — «۲۵ دی ۷۸۳» از همین می‌آمد
check("تاریخِ شمسی دوباره تبدیل نمی‌شود",
      J.isoToJalaliLabel("1405-01-15") === "۱۵ فروردین ۱۴۰۵",
      J.isoToJalaliLabel("1405-01-15"));

fs.rmSync(OUT, { recursive: true, force: true });

console.log(`\n${D}${"─".repeat(50)}${X}`);
console.log(`  ${fail ? R : G}${ok} پاس${X}` + (fail ? ` · ${R}${fail} ناموفق${X}` : ""));
console.log();
process.exit(fail ? 1 : 0);
