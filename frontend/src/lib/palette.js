/**
 * پالتِ کامل از **یک** رنگ — رنگی که نماینده برای فروشگاهش انتخاب کرده.
 *
 * چرا وجود دارد:
 *   مالک گفت «رنگ اعمال نمی‌شود». اعمال می‌شد — فقط به نصفِ صفحه.
 *   مینی‌اپ دو رنگِ برند دارد: `--accent` (آبی) و `--cy` (فیروزه‌ای)،
 *   و دکمه‌های اصلی — «خرید»، قیمت، زبانه‌ی فعال، پرداخت، ارسالِ
 *   پیام — همه `--cy` بودند. نسخه‌ی قبلی فقط `--accent` را عوض می‌کرد،
 *   پس پرتکرارترین رنگِ صفحه فیروزه‌ای می‌ماند، هر رنگی که نماینده
 *   می‌گذاشت. چند رنگِ ثابت هم در CSS بود (کارتِ موجودی، واژه‌ی اسپلش).
 *
 * نماینده یک رنگ می‌دهد؛ بقیه از همان ساخته می‌شوند تا با هم بخوانند:
 *
 *   accent    خودِ رنگ، با روشنایی‌ای که روی زمینه خوانا بماند
 *   accent-2  همان فام، روشن‌تر (تیره) یا تیره‌تر (روشن) — برای متن
 *   accent-2s سرِ روشنِ شیب‌های سطحی (حبابِ پیام، کارتِ تمدید)
 *   accent-deep / cy-2  تهِ تیره‌ترِ شیب‌ها
 *   cy        همسایه‌ی نزدیک (۱۶ درجه آن‌طرف‌تر روی چرخه‌ی رنگ)،
 *             برای دکمه‌ها و شیب‌ها. نسخه‌ی اول ۳۰ درجه بود و دکمه‌ی
 *             فروشگاهِ بنفش سرخابی، زمرد آبی و رز قرمز می‌شد — دو
 *             برند، نه یکی. ۱۶ درجه همان خانواده است با کمی جان.
 *   on-*      رنگِ متنِ روی همان دکمه — سیاه یا سفید، از روی روشنایی
 *   پله‌ها   wash/soft/fill/line/edge — همان پنج پله‌ی توکن‌های مخزن
 *
 * یک تابع، سه مصرف‌کننده: خودِ مینی‌اپ، صفحه‌ی ورودِ آن (پیش از آمدنِ
 * داده، از کش)، و پیش‌نمایشِ پرتال. اگر پیش‌نمایش حسابِ خودش را داشت،
 * نماینده چیزی می‌دید که مشتری‌اش نمی‌دید.
 *
 * رنگِ نامعتبر → null، و صداکننده هیچ‌چیز را عوض نمی‌کند (رنگِ پیش‌فرضِ
 * CSS می‌ماند).
 */

const HEX = /^#[0-9a-fA-F]{6}$/;

function hexToHsl(hex) {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  const l = (mx + mn) / 2;
  if (mx === mn) return [0, 0, l];
  const d = mx - mn;
  const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  let h;
  if (mx === r) h = (g - b) / d + (g < b ? 6 : 0);
  else if (mx === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return [h * 60, s, l];
}

function hslToRgb(h, s, l) {
  h = ((h % 360) + 360) % 360;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return [r, g, b].map((v) => Math.round((v + m) * 255));
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** فامِ h با اشباعِ s، و آن Lی که روشناییِ نسبی‌اش به `target` برسد. */
function toLum(h, s, target) {
  let lo = 0.04, hi = 0.96;
  for (let i = 0; i < 26; i++) {
    const mid = (lo + hi) / 2;
    if (luminance(hslToRgb(h, s, mid)) < target) lo = mid; else hi = mid;
  }
  return hslToRgb(h, s, (lo + hi) / 2);
}
const hex = (rgb) => "#" + rgb.map((v) => v.toString(16).padStart(2, "0")).join("");

/** روشناییِ نسبی (WCAG) — برای انتخابِ متنِ سیاه یا سفید روی رنگ. */
export function luminance(rgb) {
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** نسبتِ کنتراستِ دو رنگ (۱ تا ۲۱). */
export function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const DARK_TEXT = [6, 9, 15];      // همان #06090F که روی دکمه‌های روشن می‌نشیند
const WHITE = [255, 255, 255];

/**
 * متنِ روی یک سطح — که ممکن است شیبی از چند رنگ باشد.
 *
 * طراحیِ موجود دو عادت دارد: دکمه‌ها متنِ تیره دارند، کارت‌های بزرگ
 * متنِ سفید. `prefer` همان عادت را نگه می‌دارد و فقط وقتی کنتراست
 * کم باشد برعکسش می‌کند — پس رنگِ پیش‌فرض دقیقاً همان می‌ماند که بود،
 * و رنگی مثلِ زردِ روشن یا بنفشِ تیره هم خوانا می‌شود.
 *
 * برای شیب، بدترین سرِ شیب ملاک است: متن روی همه‌ی طولِ دکمه است.
 */
function ink(surfaces, prefer) {
  const worst = (t) => Math.min(...surfaces.map((c) => contrast(c, t)));
  if (prefer === "dark") {
    if (worst(DARK_TEXT) >= 4.5) return "#06090F";
    return worst(WHITE) >= worst(DARK_TEXT) ? "#FFFFFF" : "#06090F";
  }
  if (worst(WHITE) >= 3) return "#FFFFFF";
  return worst(DARK_TEXT) >= worst(WHITE) ? "#06090F" : "#FFFFFF";
}

function steps(prefix, rgb) {
  const c = rgb.join(", ");
  return {
    [`--${prefix}-rgb`]: c,
    [`--${prefix}-wash`]: `rgba(${c}, .07)`,
    [`--${prefix}-soft`]: `rgba(${c}, .12)`,
    [`--${prefix}-fill`]: `rgba(${c}, .20)`,
    [`--${prefix}-line`]: `rgba(${c}, .30)`,
    [`--${prefix}-edge`]: `rgba(${c}, .45)`,
  };
}

/**
 * @param {string} color  رنگِ انتخابی، `#RRGGBB`
 * @param {"dark"|"light"} scheme  پوسته‌ی تلگرام
 * @param {number} shift  رنگِ دوم چند درجه آن‌طرف‌تر — پالتِ آماده می‌تواند
 *                        جهتش را خودش بگوید (اقیانوس: آبی → فیروزه‌ای)
 * @returns {Object<string,string>|null}  نگاشتِ متغیرهای CSS
 */
export function accentPalette(color, scheme = "dark", shift = 16) {
  if (!HEX.test(String(color || ""))) return null;
  const [h, s0, l0] = hexToHsl(color);
  const light = scheme === "light";

  // رنگِ خیلی کم‌رنگ یا خیلی تیره روی هیچ زمینه‌ای دکمه نمی‌شود.
  // فام همان است که نماینده خواسته؛ فقط روشنایی و اشباع به بازه‌ی
  // خوانا برده می‌شوند.
  const s = clamp(s0, 0.38, 0.92);
  const l = clamp(l0, 0.34, 0.70);

  let accent = hslToRgb(h, s, l);

  // درست روی مرز (روشناییِ ۰٫۱۷ تا ۰٫۲) نه متنِ تیره ۴٫۵ می‌گیرد نه
  // سفید — اندازه‌گیری‌شده ۴٫۴۶ روی #bf40bf. کمترین جابه‌جایی ممکن:
  // تا ۰٫۲ روشن‌تر، همان فام و اشباع.
  if (luminance(accent) > 0.17 && luminance(accent) < 0.2) accent = toLum(h, s, 0.2);

  /*
   * `accent-2` دو کار دارد و دو رنگ لازم است:
   *   · **متن** روی زمینه‌ی پوسته (۱۱ قاعده) — در روشن تیره، در تیره
   *     روشن، از روی روشنایی و نه عددِ L (زردِ کم‌رنگ روی زمینه‌ی
   *     روشن ۱٫۲۶ کنتراست داشت).
   *   · **سطح** — سرِ روشنِ شیبِ حبابِ پیام و کارتِ تمدید (`accent-2s`).
   *     این یکی باید همان سمتِ مرزِ `accent` بماند، وگرنه متنِ رویش
   *     از یک سر خوانده می‌شود و از سرِ دیگر نه.
   */
  const accent2 = toLum(h, s, light ? Math.min(luminance(accent), 0.2)
                                    : Math.max(luminance(accent), 0.3));

  /*
   * همسایه‌ها با **روشناییِ هم‌اندازه**، نه با عددِ L یکسان.
   *
   * نسخه‌ی اول cy را با همان L می‌ساخت. ولی L در HSL روشنایی نیست:
   * سبزِ L=0.4 چند برابرِ آبیِ L=0.4 روشن است. شیبِ دکمه از سبزِ روشن
   * به آبیِ تیره می‌رفت و هیچ رنگِ متنی رویش خوانده نمی‌شد —
   * اندازه‌گیری‌شده: کنتراستِ ۲٫۶۷ روی #00b894 در پوسته‌ی روشن.
   *
   * پس اول تصمیم می‌گیریم متنِ دکمه تیره است یا سفید — از روی خودِ
   * رنگِ نماینده — و بعد همسایه‌ها را **همان سمتِ مرز** می‌سازیم.
   * مرز حدودِ روشناییِ ۰٫۱۸۵ است: بالاترش متنِ تیره ۴٫۵ کنتراست
   * می‌گیرد، پایین‌ترش متنِ سفید.
   */
  const la = luminance(accent);
  const darkInk = la >= 0.185;
  const sc = clamp(s + 0.04, 0.4, 0.95);
  const cy = toLum(h + shift, sc, darkInk ? Math.max(la, 0.2) : Math.min(la, 0.17));
  const cy2 = toLum(h + shift, sc, darkInk ? Math.max(la * 0.8, 0.19) : Math.min(la * 0.8, 0.15));

  // سرِ روشنِ شیب‌های سطحی — همان سمتِ مرز
  const accent2s = toLum(h, s, darkInk ? Math.max(la * 1.35, 0.3) : Math.min(la * 1.4, 0.17));

  // تهِ تیره‌ترِ شیب‌ها — جای دو رنگِ ثابتی که در CSS بود
  // (#1F6FBF زیرِ کارتِ موجودی، #14B8A6 زیرِ دکمه‌ی خرید)
  const deep = toLum(h, s, darkInk ? Math.max(la * 0.75, 0.19) : la * 0.7);

  return {
    "--accent": hex(accent),
    "--accent-2": hex(accent2),
    "--accent-2s": hex(accent2s),
    "--accent-deep": hex(deep),
    ...steps("accent", accent),
    "--cy": hex(cy),
    "--cy-2": hex(cy2),
    ...steps("cy", cy),
    // دکمه‌ها و حبابِ پیام: متنِ تیره اگر بشود
    "--on-accent": ink([accent, accent2s], "dark"),
    // کارت‌های بزرگِ رنگی: متنِ سفید اگر بشود. cy حساب نمی‌شود: در
    // کارتِ موجودی در ۱۴۰٪ نشسته، یعنی بیرون از خودِ کارت.
    "--on-accent-hi": ink([accent, deep, accent2s], "white"),
    // دکمه‌های شیبِ accent → cy
    "--on-cy": ink([accent, cy, cy2], "dark"),
  };
}

/** نوشتنِ پالت روی ریشه — و پاک‌کردنِ همان کلیدها وقتی رنگی نیست. */
const KEYS = Object.keys(accentPalette("#2b7fd6"));

export function applyPalette(color, scheme, el = document.documentElement) {
  const pal = accentPalette(color, scheme);
  for (const k of KEYS) {
    if (pal) el.style.setProperty(k, pal[k]);
    else el.style.removeProperty(k);
  }
  return !!pal;
}
