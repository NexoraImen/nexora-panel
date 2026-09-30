/**
 * پوسته‌ی مینی‌اپ — قالب × پالت.
 *
 * برگه: docs/specs/2026-09-23-mini-theme-studio.md
 *
 * **قالب** ساختار است: نوارِ بالا، نوارِ زبانه‌ها، شکلِ کارت و دکمه،
 * گوشه‌ها، سایه، و صفحه‌ی ورود. خودِ قاعده‌ها در `index.css` زیرِ
 * `html[data-mn-tpl="…"]` نوشته شده‌اند — رنگ و شکل جای CSS است؛ این‌جا
 * فقط صفت روی ریشه می‌نشیند.
 *
 * **پالت** طیف است: رنگِ اصلی به‌اضافه‌ی زمینه و سطح‌های هم‌خانواده‌اش.
 * نسخه‌ی قبلی فقط رنگِ دکمه‌ها را عوض می‌کرد و زمینه آبیِ نکسورا
 * می‌ماند — «فقط یک سری جزئیات عوض می‌شود» دقیقاً همین بود.
 *
 * یک تابع (`applyTheme`)، سه مصرف‌کننده: خودِ مینی‌اپ، صفحه‌ی ورودش
 * (از کش، پیش از آمدنِ داده)، و پیش‌نمایشِ پرتال — که خودِ مینی‌اپ است
 * در قاب، پس چیزی جز همین را نمی‌تواند نشان بدهد.
 *
 * شناسه‌ها باید با `MINI_TEMPLATES` / `MINI_PALETTES` در بکند یکی
 * باشند؛ `test-ui-safety` برابری‌شان را می‌سنجد.
 */
import { accentPalette } from "./palette.js";

export const MINI_TEMPLATES = [
  { id: "aurora", fa: "شفق", desc: "ظاهرِ پیش‌فرض — شیب‌های نرم و کارتِ موجودیِ رنگی" },
  { id: "mono", fa: "مینیمال", desc: "تخت و آرام — خطِ مو، بی‌شیب، زبانه با خطِ زیرین" },
  { id: "bold", fa: "پررنگ", desc: "نوارِ بالای رنگی، زبانه‌های شناور، دکمه‌های قرصی" },
  { id: "neon", fa: "نئون", desc: "گوشه‌های تیز، درخششِ رنگ روی لبه‌ها، عددِ تک‌فاصله" },
];

/*
 * پالت‌های آماده. `shift` جهتِ رنگِ دوم است (پیش‌فرض ۱۶ درجه) — اقیانوس
 * به فیروزه‌ای می‌رود تا همان ظاهرِ آشنای آبی و فیروزه‌ای بماند.
 * `bg` زمینه‌ی حالتِ تیره است؛ سطح‌ها از همان فام و
 * اشباع با روشنایی‌های ثابت ساخته می‌شوند — همان فاصله‌هایی که
 * پوسته‌ی پیش‌فرض دارد (#070A12 → #101827 → #17223A).
 */
export const MINI_PALETTES = [
  { id: "ocean", fa: "اقیانوس", accent: "#2B7FD6", bg: "#070A12", shift: -40 },
  { id: "violet", fa: "بنفش", accent: "#7C5CFF", bg: "#0A0714" },
  { id: "emerald", fa: "زمرد", accent: "#10B981", bg: "#04100C" },
  { id: "sunset", fa: "غروب", accent: "#F97316", bg: "#120904" },
  { id: "rose", fa: "رز", accent: "#E84393", bg: "#12060D" },
  { id: "gold", fa: "طلایی", accent: "#D4A017", bg: "#0F0C04", shift: -20 },
  { id: "crimson", fa: "یاقوت", accent: "#E11D48", bg: "#110407" },
  { id: "slate", fa: "سنگی", accent: "#94A3B8", bg: "#0A0C10" },
];

export const DEFAULT_TEMPLATE = "aurora";

/*
 * سبکِ صفحه‌ی ورود — جدا از قالب.
 *
 * قالب هنوز رنگ و زمینه‌ی اسپلش را می‌دهد (پررنگ تمام‌رنگ است، مینیمال
 * بی‌نور)؛ این فقط «چه چیزی حرکت می‌کند» است. پیش‌تر هر فروشگاه یک
 * اسپلش داشت: لوگو، نام، نوارِ باریک.
 *
 * شناسه‌ها با `MINI_SPLASHES` در بکند یکی‌اند — test-portal-dashboard
 * برابری‌شان را می‌سنجد؛ شناسه‌ای که بکند نشناسد بی‌صدا «نوار» می‌شد.
 */
export const MINI_SPLASHES = [
  { id: "bar", fa: "نوار", desc: "لوگو، نام و نوارِ پیشرفتِ باریک — پیش‌فرض" },
  { id: "ring", fa: "حلقه", desc: "کمانی از رنگِ اصلی دورِ لوگو می‌چرخد" },
  { id: "pulse", fa: "موج", desc: "موج‌های نرم از لوگو بیرون می‌روند" },
  { id: "dots", fa: "نقطه‌ها", desc: "سه نقطه زیرِ نام — جمع‌وجور و آرام" },
  { id: "logo", fa: "فقط لوگو", desc: "لوگوی بزرگ که نفس می‌کشد؛ بی‌نام، بی‌نوار" },
];
export const DEFAULT_SPLASH = "bar";
export const cleanSplash = (v) => (MINI_SPLASHES.some((x) => x.id === v) ? v : DEFAULT_SPLASH);
const HEX = /^#[0-9a-fA-F]{6}$/;

function hexHsl(hex) {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  if (mx === mn) return [0, 0, l];
  const d = mx - mn;
  const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  const h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, s, l];
}

function hsl(h, s, l) {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return "#" + [r, g, b].map((v) => Math.round((v + m) * 255).toString(16).padStart(2, "0")).join("");
}

/** سطح‌های حالتِ تیره از یک زمینه — همان فام، روشنایی‌های ثابت. */
function surfacesFrom(bg) {
  const [h, s0] = hexHsl(bg);
  const s = Math.min(s0, 0.45);
  return {
    "--bg": hsl(h, s, 0.045),
    "--surface-3": hsl(h, s, 0.07),
    "--surface": hsl(h, s, 0.11),
    "--surface-2": hsl(h, s, 0.16),
  };
}

/**
 * پالتِ نهایی: `{accent, bg}` از پالتِ آماده، یا از رنگِ دلخواه.
 * رنگِ دلخواه زمینه‌ای از فامِ خودش می‌گیرد — طیف، نه فقط دکمه.
 */
export function resolvePalette(paletteId, customAccent) {
  if (paletteId === "custom" && HEX.test(String(customAccent || ""))) {
    const [h] = hexHsl(customAccent);
    return { accent: customAccent, bg: hsl(h, 0.35, 0.045), shift: 16 };
  }
  const p = MINI_PALETTES.find((x) => x.id === paletteId);
  if (p) return { accent: p.accent, bg: p.bg, shift: p.shift ?? 16 };
  // سازگاری: پیش از قالب‌ها فقط `mini_accent` بود
  if (HEX.test(String(customAccent || ""))) return resolvePalette("custom", customAccent);
  return null;
}

/** همه‌ی متغیرهای یک پوسته — برای ریشه، یا برای یک عنصرِ پیش‌نمایش. */
export function themeVars({ palette, accent }, scheme = "dark") {
  const pal = resolvePalette(palette, accent);
  if (!pal) return null;
  const vars = { ...accentPalette(pal.accent, scheme, pal.shift) };
  // زمینه و سطح‌ها فقط در تیره. در روشنِ تلگرام زمینه روشن می‌ماند —
  // متغیرِ درون‌خطی روی ریشه قاعده‌ی پوسته‌ی روشن را می‌پوشاند و
  // سطحِ تیره را وسطِ پوسته‌ی روشن می‌گذاشت.
  if (scheme !== "light") Object.assign(vars, surfacesFrom(pal.bg));
  return vars;
}

const ALL_KEYS = Object.keys({
  ...accentPalette("#2b7fd6"), ...surfacesFrom("#070A12"),
});

/**
 * روشن یا تیره — از خودِ تلگرام، یک قاعده برای دو جا.
 *
 * صفحه‌ی ورود (main.jsx) و خودِ مینی‌اپ (syncTheme) هر دو می‌پرسند.
 * تا امروز فقط مینی‌اپ می‌پرسید، آن هم بعد از بارشدنِ تکه‌اش؛ پس
 * صفحه‌ی ورود برای مشتریِ پوسته‌ی روشن همیشه سیاه بود و بعد ناگهان
 * سفید می‌شد. یک تابع، تا دو پاسخِ متفاوت ممکن نباشد.
 */
export function tgScheme(w) {
  return (w && w.colorScheme) === "light" ? "light" : "dark";
}

/** صفتِ پوسته روی ریشه — همان که قاعده‌های روشنِ index.css می‌خوانند */
export function markScheme(w, el = document.documentElement) {
  const s = tgScheme(w);
  el.dataset.mnScheme = s;
  return s;
}

/**
 * پوسته را روی ریشه بگذار — و هر چه قبلاً گذاشته شده بود، اگر این
 * پوسته ندارد، بردار. `theme` خالی یعنی پیش‌فرض.
 */
export function applyTheme(theme, scheme = "dark", el = document.documentElement) {
  const t = theme || {};
  const tpl = MINI_TEMPLATES.some((x) => x.id === t.tpl) ? t.tpl : DEFAULT_TEMPLATE;
  el.dataset.mnTpl = tpl;
  const vars = themeVars(t, scheme) || {};
  for (const k of ALL_KEYS) {
    if (vars[k] !== undefined) el.style.setProperty(k, vars[k]);
    else el.style.removeProperty(k);
  }
  return tpl;
}

/** پالتِ آماده، برای نمونه‌رنگ‌های انتخاب‌گر. */
export function paletteSwatch(id, accent) {
  const p = resolvePalette(id, accent);
  if (!p) return null;
  const v = themeVars({ palette: id, accent }, "dark");
  return { accent: v["--accent"], cy: v["--cy"], bg: v["--bg"], surface: v["--surface"] };
}
