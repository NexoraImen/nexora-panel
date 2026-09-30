/**
 * پیش‌نمایشِ ربات — از روی **کدِ واقعی**، با تنظیمات و پلن‌ها و متن‌های همین
 * فروشگاه (مالک یا نماینده).
 *
 * پیش‌تر متن‌های دست‌نوشته‌ی همین فایل بود و از ربات عقب افتاده بود: سؤال‌های
 * پیش از تست، پیگیری و نوع و تبِ پلن را نداشت. مالک: «خیلی از چیزها را
 * نمی‌شود تست گرفت؛ می‌خواهم قبلش خودم ببینم چه کار می‌کند». حالا بکند
 * `bot/preview_flows.py` را اجرا می‌کند — همان `handlers` که مشتری با آن حرف
 * می‌زند — و این‌جا فقط کشیده می‌شود.
 */

/**
 * HTML تلگرام → HTML امن. فقط همان چند تگی که تلگرام می‌فهمد و **بی هیچ
 * ویژگی‌ای** (حتی href) برمی‌گردد؛ متنِ بینشان دوباره escape می‌شود. پس متنِ
 * دلخواهِ فروشگاه (قالب‌های «متن‌ها») هیچ‌وقت HTML اجرایی نمی‌سازد.
 */
const TAGS = { b: "b", strong: "b", i: "i", em: "i", u: "u", ins: "u", s: "s", del: "s",
               code: "code", pre: "pre", blockquote: "blockquote", a: "u", "tg-spoiler": "s" };
export function tgHtml(src) {
  const dec = (x) => x.replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\"").replace(/&amp;/g, "&");
  const enc = (x) => x.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const re = /<(\/?)([a-zA-Z-]+)(?:\s[^>]*)?>/g;
  let out = "", last = 0, m;
  const s = String(src || "");
  while ((m = re.exec(s))) {
    out += enc(dec(s.slice(last, m.index)));
    const t = TAGS[m[2].toLowerCase()];
    if (t) out += `<${m[1]}${t}>`;
    last = re.lastIndex;
  }
  return out + enc(dec(s.slice(last)));
}
