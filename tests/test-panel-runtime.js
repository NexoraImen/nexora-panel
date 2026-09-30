#!/usr/bin/env node
// repo root — these tests moved from the root into tests/ (2.0 layout)
const ROOT_DIR = require("path").dirname(__dirname);
/**
 * تست اجرای واقعی پنل ساخته‌شده.
 *
 * چرا لازم است: `npm run build` می‌تواند موفق شود ولی باندل در مرورگر
 * کرش کند — مثلاً وقتی یک import حذف شده باشد. آن‌وقت پنل صفحه‌ی سفید
 * می‌شود بدون اینکه چیزی در لاگ بیلد باشد.
 *
 * اجرا (بعد از npm run build):
 *     node tests/test-panel-runtime.js [مسیر dist]
 */

const fs = require("fs");
const path = require("path");


/*
 * پیش‌فرض: بیلدِ تک‌فایلیِ مخصوصِ همین تست.
 *
 * `dist` واقعی تکه‌تکه است تا مشتریِ مینی‌اپ کلِ پنل مدیر را دانلود
 * نکند، و تکه‌ها با `import` به هم وصل‌اند — چیزی که jsdom اجرا
 * نمی‌کند. پس `dist-test` ساخته می‌شود که همان کد است در یک فایل.
 *
 * اگر نبود، خودش می‌سازدش: تستی که بگوید «اول یک دستور دیگر بزن»،
 * روزی زده نمی‌شود.
 */
const SINGLE = path.join(ROOT_DIR, "frontend", "dist-test");
let DIST = process.argv[2];
if (!DIST) {
  if (!fs.existsSync(path.join(SINGLE, "index.html"))) {
    console.log("  ساختِ نسخه‌ی تک‌فایلی برای تست…");
    const { spawnSync } = require("child_process");
    const r = spawnSync("npx", ["vite", "build"], {
      cwd: path.join(ROOT_DIR, "frontend"),
      env: { ...process.env, NEXORA_SINGLE_BUNDLE: "1" },
      shell: true, encoding: "utf8",
    });
    if (r.status !== 0) {
      console.error("❌ ساختِ نسخه‌ی تست ناموفق بود");
      console.error((r.stderr || r.stdout || "").slice(-400));
      process.exit(1);
    }
  }
  DIST = SINGLE;
}

function jsdomPath() {
  const candidates = [
    "jsdom",
    "/tmp/jstest/node_modules/jsdom",
    path.join(ROOT_DIR, "node_modules", "jsdom"),
  ];
  for (const c of candidates) {
    try { return require(c); } catch { /* بعدی */ }
  }
  console.error("jsdom پیدا نشد.  npm i jsdom  را اجرا کنید");
  process.exit(2);
}

const { JSDOM } = jsdomPath();

if (!fs.existsSync(path.join(DIST, "index.html"))) {
  console.error(`❌ فایل ساخته‌شده پیدا نشد: ${DIST}/index.html`);
  console.error("   ابتدا npm run build را اجرا کنید");
  process.exit(1);
}

const html = fs.readFileSync(path.join(DIST, "index.html"), "utf8");
const assets = path.join(DIST, "assets");
const jsFile = fs.existsSync(assets)
  ? fs.readdirSync(assets).find((f) => f.endsWith(".js"))
  : null;

if (!jsFile) {
  console.error("❌ فایل جاوااسکریپت در dist/assets پیدا نشد");
  process.exit(1);
}

const jsPath = path.join(assets, jsFile);
const size = fs.statSync(jsPath).size;
const js = fs.readFileSync(jsPath, "utf8");

console.log("\n" + "═".repeat(52));
console.log("  تست اجرای پنل");
console.log("═".repeat(52) + "\n");
console.log(`  فایل:  ${jsFile}`);
console.log(`  حجم:   ${(size / 1024).toFixed(0)} KB`);

if (size < 50000) {
  console.error("\n❌ باندل بیش از حد کوچک است — بیلد ناقص بوده");
  process.exit(1);
}

const errors = [];
const dom = new JSDOM(html, {
  runScripts: "outside-only",
  url: "https://panel.test/",
  pretendToBeVisual: true,
});

const w = dom.window;
w.fetch = () => Promise.resolve({
  ok: false, status: 401, json: () => Promise.resolve({}),
});
w.matchMedia = () => ({
  matches: false,
  addListener() {}, removeListener() {},
  addEventListener() {}, removeEventListener() {},
});
w.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
w.onerror = (m) => errors.push(String(m));

const origError = console.error;
console.error = (...a) => {
  const s = a.join(" ");
  if (/Error|is not defined|undefined is not/.test(s)) errors.push(s);
};

try {
  w.eval(js);
} catch (e) {
  errors.push(e.message);
}

setTimeout(() => {
  console.error = origError;
  const root = w.document.getElementById("root");
  const len = root ? root.innerHTML.trim().length : 0;
  const rendered = len > 50;

  console.log(`  رندر:  ${rendered ? "✅ محتوا تولید شد" : "❌ چیزی رندر نشد"} (${len} کاراکتر)`);

  if (errors.length) {
    console.log("\n  خطاهای زمان اجرا:");
    errors.slice(0, 5).forEach((e) => console.log("    • " + e.slice(0, 180)));
  }

  const pass = rendered && errors.length === 0;
  console.log("\n" + "═".repeat(52));
  console.log(pass ? "  ✅ پنل سالم اجرا می‌شود" : "  ❌ پنل در مرورگر کار نمی‌کند");
  console.log("═".repeat(52) + "\n");
  process.exit(pass ? 0 : 1);
}, 2500);
