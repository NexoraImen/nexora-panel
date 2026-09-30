/**
 * تست رندر واقعی پنل.
 *
 *   cd frontend && npm run build
 *   node ../tests/test-render.cjs
 *
 * چرا لازم است: `npm run build` وقتی موفق تمام می‌شود که فایل‌ها
 * ساخته شوند — حتی اگر CSS تقریباً خالی باشد. دو بار همین اتفاق
 * افتاد: یک‌بار دستورهای @tailwind حذف شدند و یک‌بار بلوک :root،
 * و هر دو بار build سبز بود ولی پنل بدون ظاهر بالا می‌آمد.
 *
 * این اسکریپت CSS ساخته‌شده را در یک مرورگر شبیه‌سازی‌شده اجرا
 * می‌کند و مقدار واقعی computed style را می‌خواند.
 */

const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..");
const DIST = path.join(ROOT, "frontend", "dist");

let pass = 0;
let fail = 0;

const G = "\x1b[38;5;42m";
const R = "\x1b[38;5;203m";
const D = "\x1b[38;5;245m";
const X = "\x1b[0m";

function chk(name, ok, extra = "") {
  ok ? pass++ : fail++;
  const mark = ok ? `${G}✓${X}` : `${R}✗${X}`;
  console.log(`  ${mark} ${name}${extra ? ` ${D}— ${extra}${X}` : ""}`);
}

function head(t) {
  console.log(`\n${D}── ${t} ──${X}`);
}

// ── پیدا کردن فایل‌های خروجی ──
if (!fs.existsSync(DIST)) {
  console.error(`\n${R}پوشه dist نیست. اول اجرا کنید: cd frontend && npm run build${X}\n`);
  process.exit(1);
}

const assetsDir = path.join(DIST, "assets");
const cssFiles = fs.readdirSync(assetsDir).filter((f) => f.endsWith(".css"));

if (!cssFiles.length) {
  console.error(`\n${R}هیچ فایل CSS در خروجی نیست${X}\n`);
  process.exit(1);
}

const css = fs.readFileSync(path.join(assetsDir, cssFiles[0]), "utf8");
const html = fs.readFileSync(path.join(DIST, "index.html"), "utf8");

console.log(`\n${D}بررسی ${cssFiles[0]} — ${(css.length / 1024).toFixed(1)} KB${X}`);

// CSS را داخل صفحه تزریق می‌کنیم؛ jsdom فایل خارجی را لود نمی‌کند
const dom = new JSDOM(html.replace("</head>", `<style>${css}</style></head>`),
                      { pretendToBeVisual: true });
const { document: d, window: w } = dom.window;

// ── ۱. حجم ──
head("حجم خروجی");
chk("CSS خالی نیست", css.length > 10000,
    `${(css.length / 1024).toFixed(1)} KB`);

// ── ۲. کلاس‌های Tailwind ──
head("کلاس‌های Tailwind");
const utils = [
  ["flex", "display", "flex"],
  ["grid", "display", "grid"],
  ["hidden", "display", "none"],
  ["items-center", "alignItems", "center"],
  ["justify-between", "justifyContent", "space-between"],
  ["text-center", "textAlign", "center"],
  ["absolute", "position", "absolute"],
  ["relative", "position", "relative"],
  ["w-full", "width", "100%"],
  ["rounded-xl", "borderRadius", "0.75rem"],
  ["truncate", "overflow", "hidden"],
];
// «0.75rem» و «.75rem» یک مقدارند — Tailwind در خروجی minify صفر
// ابتدایی را حذف می‌کند. مقایسه‌ی رشته‌ای خام اینجا الکی قرمز می‌شد.
const sameCss = (a, b) => {
  if (a === b) return true;
  const n = (v) => String(v).trim().replace(/(^|[\s(,])(\.\d)/g, "$10$2");
  return n(a) === n(b);
};
for (const [cls, prop, want] of utils) {
  const el = d.createElement("div");
  el.className = cls;
  d.body.appendChild(el);
  const got = w.getComputedStyle(el)[prop];
  chk(`.${cls}`, sameCss(got, want), got || "خالی");
}

// ── ۳. متغیرهای رنگ ──
head("متغیرهای رنگ");
const root = w.getComputedStyle(d.documentElement);
const vars = ["--bg", "--surface", "--surface-2", "--surface-3",
              "--border", "--border-2", "--accent", "--accent-2",
              "--accent-soft", "--text", "--dim", "--muted",
              "--ok", "--warn", "--danger", "--purple"];
for (const v of vars) {
  const val = root.getPropertyValue(v).trim();
  chk(v, !!val, val || "تعریف نشده");
}

// ── ۴. فونت ──
head("فونت");
// body حالا از متغیر می‌خواند، چون برگرداندنِ قلم از داخل سلول‌های
// مونو به یک نامِ یک‌جا تعریف‌شده نیاز داشت. jsdom متغیر را باز
// نمی‌کند، پس اگر مقدار var(--…) بود، خودِ متغیر را دنبال می‌کنیم —
// وگرنه تست به «نامِ قلم عوض نشده باشد» تبدیل می‌شد، نه «قلم اعمال
// شده باشد».
let bodyFont = w.getComputedStyle(d.body).fontFamily;
const varRef = /^var\((--[\w-]+)\)$/.exec(bodyFont.trim());
if (varRef) bodyFont = root.getPropertyValue(varRef[1]).trim();
chk("روی body اعمال شده", bodyFont.includes("IRANSansX"),
    bodyFont.slice(0, 52));
chk("اعلان @font-face", (css.match(/@font-face/g) || []).length >= 2,
    `${(css.match(/@font-face/g) || []).length} اعلان`);
chk("فایل فونت در خروجی",
    fs.readdirSync(assetsDir).some((f) => /woff2?$/.test(f)));

// ── ۵. کلاس‌های سفارشی ──
head("کلاس‌های سفارشی");
const app = fs.readFileSync(
  path.join(ROOT, "frontend", "src", "App.jsx"), "utf8");
const usedClasses = new Set();
for (const m of app.matchAll(/className="([^"]+)"/g)) {
  for (const c of m[1].split(/\s+/)) {
    if (/^(fx|nx)-/.test(c)) usedClasses.add(c);
  }
}
const missing = [...usedClasses].filter((c) => !css.includes("." + c));
chk(`${usedClasses.size} کلاس استفاده‌شده تعریف دارند`,
    missing.length === 0,
    missing.length ? missing.slice(0, 6).join("، ") : "");

// ── نتیجه ──
console.log(`\n${D}${"─".repeat(46)}${X}`);
if (fail) {
  console.log(`  ${R}${pass} پاس · ${fail} ناموفق${X}\n`);
  process.exit(1);
}
console.log(`  ${G}${pass} پاس — ظاهر پنل سالم است${X}\n`);
