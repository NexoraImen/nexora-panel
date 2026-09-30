/**
 * آیکون‌های صفحه‌ی اشتراک — از فونت‌آسام به ماسکِ SVG جاسازی‌شده.
 *
 * چرا: صفحه‌ی اشتراک آیکون‌هایش را از `cdnjs.cloudflare.com` می‌گرفت،
 * که در ایران بالا نمی‌آید. یعنی مشتری ۴۸ جای خالی می‌دید — و چون
 * فونت‌آسام وقتی نرسد هیچ چیزی نشان نمی‌دهد (نه حتی مربع)، این خرابی
 * کاملاً بی‌صدا بود. روی مرورگرِ خودِ ما با VPN درست دیده می‌شد.
 *
 * چرا ماسک و نه `<svg>`: آیکون‌ها فقط در HTML نیستند — در جدولِ
 * ترجمه‌ی چهار زبان، در نگاشتِ پلتفرم، و در `className =` هم
 * ساخته می‌شوند. با ماسک، همان `<i class="fa-solid fa-copy">` سرِ
 * جایش می‌ماند و هیچ‌کدام از آن مسیرها دست نمی‌خورد.
 *
 * و چون رنگ از `background-color: currentColor` می‌آید، همان
 * `style="color: var(--accent)"`هایی که روی آیکون‌ها هست هنوز کار
 * می‌کند.
 *
 * آیکون‌ها از lucide می‌آیند — همان مجموعه‌ای که پنل استفاده می‌کند،
 * پس صفحه‌ی مشتری و پنلِ مالک یک زبانِ تصویری دارند.
 */
const fs = require("fs");
const path = require("path");

const ICON_DIR = path.join(__dirname, "..", "frontend", "node_modules",
                           "lucide-react", "dist", "esm", "icons");

/** fa → lucide. برندها معادلِ لوگو ندارند، پس نزدیک‌ترین معنا. */
const MAP = {
  "fa-android": "smartphone",
  "fa-apple": "smartphone",
  "fa-arrow-down": "arrow-down",
  "fa-arrow-up": "arrow-up",
  "fa-arrow-up-left": "arrow-up-left",
  "fa-battery-three-quarters": "battery-medium",
  "fa-bolt": "zap",
  "fa-box-open": "package-open",
  "fa-chart-pie": "pie-chart",
  "fa-check": "check",
  "fa-chevron-down": "chevron-down",
  "fa-chevron-left": "chevron-left",
  "fa-circle-play": "circle-play",
  "fa-clock": "clock",
  "fa-cloud-arrow-down": "cloud-download",
  "fa-copy": "copy",
  "fa-database": "database",
  "fa-desktop": "monitor",
  "fa-download": "download",
  "fa-gauge-high": "gauge",
  "fa-gift": "gift",
  "fa-globe": "globe",
  "fa-hourglass-half": "hourglass",
  "fa-house": "home",
  "fa-link": "link",
  "fa-mobile-screen": "smartphone",
  "fa-moon": "moon",
  "fa-paper-plane": "send",
  "fa-qrcode": "qr-code",
  "fa-rotate": "rotate-cw",
  "fa-shield-halved": "shield",
  "fa-star": "star",
  "fa-sun": "sun",
  "fa-telegram": "send",
  "fa-triangle-exclamation": "triangle-alert",
  "fa-xmark": "x",
};

/** آرایه‌ی عناصرِ یک آیکون lucide را از ماژولش بیرون بکش. */
function elements(name) {
  const file = path.join(ICON_DIR, name + ".js");
  const src = fs.readFileSync(file, "utf8");
  const open = src.indexOf("[", src.indexOf("createLucideIcon("));
  if (open < 0) throw new Error(`آرایه‌ی ${name} پیدا نشد`);
  // تا براکتِ متناظر — شمردن، چون داخلش آرایه‌های تودرتو هست
  let depth = 0, end = -1;
  for (let i = open; i < src.length; i++) {
    if (src[i] === "[") depth++;
    else if (src[i] === "]") { depth--; if (!depth) { end = i + 1; break; } }
  }
  if (end < 0) throw new Error(`آرایه‌ی ${name} بسته نشد`);
  // شکلِ ماژول ثابت است و ورودی از node_modules می‌آید، نه از کاربر
  // eslint-disable-next-line no-eval
  return eval(src.slice(open, end));
}

const ATTR = (o) => Object.entries(o)
  .filter(([k]) => k !== "key")
  .map(([k, v]) => `${k}="${v}"`).join(" ");

function svg(name) {
  const body = elements(name).map(([tag, at]) => `<${tag} ${ATTR(at)}/>`).join("");
  // ماسک از آلفا می‌خواند، پس رنگ اهمیتی ندارد؛ ولی stroke باید باشد
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" `
       + `stroke="#000" stroke-width="2" stroke-linecap="round" `
       + `stroke-linejoin="round">${body}</svg>`;
}

/** برای data: URI داخل CSS — نقل‌قول و # و < باید فرار بگیرند. */
const enc = (s) => s
  .replace(/</g, "%3C").replace(/>/g, "%3E")
  .replace(/#/g, "%23").replace(/"/g, "'")
  .replace(/\s+/g, " ");

function build() {
  const rules = [];
  for (const [fa, lu] of Object.entries(MAP)) {
    rules.push(`.${fa}{-webkit-mask-image:url("data:image/svg+xml,${enc(svg(lu))}");`
             + `mask-image:url("data:image/svg+xml,${enc(svg(lu))}")}`);
  }
  return `<style id="nexora-icons">
/* آیکون‌ها — محلی، بدون CDN. ساخته‌ی scripts/make-subpage-icons.js
   دست‌کاری نکن؛ اسکریپت را دوباره اجرا کن. */
.fa-solid,.fa-brands,.fa-regular,[class*="fa-"]{
  display:inline-block;width:1em;height:1em;vertical-align:-.125em;
  background-color:currentColor;
  -webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;
  -webkit-mask-position:center;mask-position:center;
  -webkit-mask-size:contain;mask-size:contain;
  font-style:normal;line-height:1;flex-shrink:0;
}
${rules.join("\n")}
</style>`;
}

if (require.main === module) {
  const out = build();
  const P = path.join(__dirname, "..", "sub-page-index.html");
  let html = fs.readFileSync(P, "utf8");

  // ۱) بلوکِ قبلی را (اگر هست) با تازه عوض کن، وگرنه قبل از
  //    </head> بگذار
  const re = /<style id="nexora-icons">[\s\S]*?<\/style>/;
  if (re.test(html)) {
    html = html.replace(re, out);
  } else {
    html = html.replace("</head>", out + "\n</head>");
  }

  // ۲) لینکِ فونت‌آسام از cdnjs — در ایران بالا نمی‌آید
  html = html.replace(
    /\s*<link rel="stylesheet" href="https:\/\/cdnjs\.cloudflare\.com[^>]*>/g, "");

  fs.writeFileSync(P, html);
  const n = Object.keys(MAP).length;
  console.log(`✅ ${n} آیکون جاسازی شد، لینک cdnjs برداشته شد`);
}

module.exports = { build, MAP };
