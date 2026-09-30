#!/usr/bin/env node
/**
 * صفحه‌ی اشتراکِ مشتری را بدون سرورِ 3x-ui قابلِ دیدن می‌کند.
 *
 * این صفحه را تا امروز هیچ‌کس ندیده بود مگر روی سرور واقعی با یک
 * اشتراکِ واقعی — یعنی عملاً هیچ‌وقت. و هر چیزی که دیده نشود، خراب
 * می‌ماند: همان درسی که برای خودِ پنل گرفتیم.
 *
 * تمام قالب‌های Go در یک بلوکِ جاوااسکریپت‌اند (۲۳ تا)، پس جای‌گذاری
 * ساده است — نه موتورِ قالب لازم است نه Go.
 *
 *   node tests/harness/make-subpage-harness.js
 *   frontend/dist-test/sub.html
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const SRC = path.join(ROOT, "sub-page-index.html");
const OUT = path.join(ROOT, "frontend", "dist-test", "sub.html");

const now = Math.floor(Date.now() / 1000);
const GB = 1024 ** 3;

// داده‌ی واقع‌نما — نه صفر، نه گرد. اشتراکی که نصفِ حجمش رفته و
// هجده روز مانده، همان حالتی است که مشتری بیشتر وقت‌ها می‌بیند.
const VALS = {
  ".sId": "a1b2c3d4e5",
  ".enabled": "true",
  ".expire": String(now + 18 * 86400),
  ".downloadByte": String(Math.round(23.4 * GB)),
  ".uploadByte": String(Math.round(1.7 * GB)),
  ".totalByte": String(50 * GB),
  ".subUrl": "https://sub.example.com/sub/a1b2c3d4e5",
  ".subJsonUrl": "https://sub.example.com/json/a1b2c3d4e5",
  ".subClashUrl": "https://sub.example.com/clash/a1b2c3d4e5",
  ".subTitle": "اشتراک نکسورا",
  ".subSupportUrl": "https://t.me/demo_support",
  ".datepicker": "jalali",
  // میلی‌ثانیه، نه ثانیه — مثل `expiryTime` در خودِ 3x-ui.
  // با ثانیه، `new Date()` می‌رفت به ۱۹۷۰ و صفحه «۱۳۴۸/۱۱/۱»
  // نشان می‌داد. داده‌ی ساختگیِ غلط، باگی می‌سازد که وجود ندارد.
  ".lastOnline": String((now - 420) * 1000),
};

const EMAILS = ["رضا مرادی", "nexora_8814_1"];
const LINKS = [
  "vless://11111111-2222-3333-4444-555555555555@de1.example.com:443"
    + "?type=ws&security=tls&path=%2Fws&host=de1.example.com#Germany-1",
  "vless://11111111-2222-3333-4444-555555555555@nl2.example.com:443"
    + "?type=grpc&security=tls&serviceName=grpc#Netherlands-2",
];

let html = fs.readFileSync(SRC, "utf8");

// دو حلقه‌ی range را مستقیم با آرایه‌ی آماده جایگزین کن — بازنویسیِ
// معناشناسیِ Go لازم نیست، فقط همین دو خط range دارند.
html = html.replace(
  /\[\{\{ range \$i, \$e := \.emails \}\}[\s\S]*?\{\{ end \}\}\]/,
  JSON.stringify(EMAILS));
html = html.replace(
  /\[\{\{ range \$i, \$l := \.links \}\}[\s\S]*?\{\{ end \}\}\]/,
  JSON.stringify(LINKS));

for (const [k, v] of Object.entries(VALS)) {
  html = html.split("{{ " + k + " }}").join(v);
}

const left = html.match(/\{\{[^}]*\}\}/g);
if (left) {
  console.error("❌ قالب جا مانده:", [...new Set(left)].join(", "));
  process.exit(1);
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, html, "utf8");
console.log("✅ frontend/dist-test/sub.html ساخته شد");
