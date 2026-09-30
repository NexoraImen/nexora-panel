#!/usr/bin/env node
/**
 * پالتِ فروشگاه — هر رنگی که نماینده بدهد، متن رویش خوانده شود.
 *
 * چرا با جاروی کلِ چرخه‌ی رنگ و نه چند نمونه:
 *   نسخه‌ی اولِ پالت روی بنفش و صورتی درست بود و روی سبز در پوسته‌ی
 *   روشن کنتراستِ ۲٫۶۷ می‌داد — یعنی متنِ دکمه‌ی «خرید» عملاً دیده
 *   نمی‌شد. با سه رنگِ نمونه این هرگز پیدا نمی‌شد. نماینده هر رنگی
 *   می‌تواند بدهد، پس هر رنگی سنجیده می‌شود: ۳۶ فام × ۴ اشباع ×
 *   ۷ روشنایی × دو پوسته.
 *
 * آستانه‌ها از WCAG: ۴٫۵ برای متنِ معمولی روی دکمه، ۳ برای عددِ درشتِ
 * کارت و متنِ برجسته روی زمینه.
 *
 * اجرا:  node tests/test-palette.cjs
 */
const path = require("path");
const { pathToFileURL } = require("url");

const G = "\x1b[38;5;42m", R = "\x1b[38;5;203m", D = "\x1b[38;5;245m", X = "\x1b[0m";

function hslHex(h, s, l) {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return "#" + [r, g, b].map((v) => Math.round((v + m) * 255).toString(16).padStart(2, "0")).join("");
}
const rgb = (hx) => [1, 3, 5].map((i) => parseInt(hx.slice(i, i + 2), 16));

(async () => {
  const P = await import(pathToFileURL(path.join(__dirname, "..", "frontend", "src", "lib", "palette.js")).href);
  const { accentPalette, contrast } = P;
  const T = await import(pathToFileURL(path.join(__dirname, "..", "frontend", "src", "lib", "mini-themes.js")).href);
  let ok = 0, fail = 0;
  const check = (name, cond, detail = "") => {
    if (cond) { ok++; console.log(`  ${G}✓${X} ${name}${detail ? ` ${D}— ${detail}${X}` : ""}`); }
    else { fail++; console.log(`  ${R}✗${X} ${name}${detail ? ` ${D}— ${detail}${X}` : ""}`); }
  };

  check("رنگِ نامعتبر پالت نمی‌سازد (پوسته‌ی پیش‌فرض می‌ماند)",
        accentPalette("") === null && accentPalette("red") === null
        && accentPalette("#12345") === null);

  // کمترین کنتراستِ هر جفت، روی کلِ جارو
  const worst = {};
  const note = (key, v, color, scheme) => {
    if (!worst[key] || v < worst[key].v) worst[key] = { v, color, scheme };
  };
  const BG = { dark: rgb("#070A12"), light: rgb("#EEF3FA") };

  // هر جهتی که یک پالتِ آماده برای رنگِ دومش می‌گیرد
  const SHIFTS = [...new Set([16, 30, ...T.MINI_PALETTES.map((x) => x.shift ?? 30)])];
  for (const scheme of ["dark", "light"]) {
    for (let h = 0; h < 360; h += 10) {
      for (const s of [0.1, 0.5, 0.9, 1]) {
        for (const l of [0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95]) {
         for (const shift of SHIFTS) {
          const color = hslHex(h, s, l);
          const p = accentPalette(color, scheme, shift);
          const min = (ink, surfaces) => Math.min(...surfaces.map((x) => contrast(rgb(ink), rgb(x))));
          // دکمه‌های شیبِ accent → cy (خرید، پرداخت، ارسالِ پیام)
          note("on-cy", min(p["--on-cy"], [p["--accent"], p["--cy"], p["--cy-2"]]), color, scheme);
          // حبابِ پیامِ خودِ مشتری و دکمه‌های تک‌رنگ
          note("on-accent", min(p["--on-accent"], [p["--accent"], p["--accent-2s"]]), color, scheme);
          // کارتِ موجودی و کارتِ تمدید — عددِ درشت
          note("on-accent-hi", min(p["--on-accent-hi"],
                                   [p["--accent"], p["--accent-deep"], p["--accent-2s"]]), color, scheme);
          // متنِ برجسته روی زمینه‌ی خودِ پوسته
          note("accent-2 on bg", contrast(rgb(p["--accent-2"]), BG[scheme]), color, scheme);
         }
        }
      }
    }
  }

  // ── طیف‌ها: متنِ معمولی روی زمینه و سطح‌های خودِ هر پالت ──
  //
  // پالت‌ها حالا زمینه را هم عوض می‌کنند (رنگِ دلخواه زمینه‌ای از فامِ
  // خودش می‌گیرد). متنِ اصلی و متنِ کم‌رنگِ پوسته ثابت‌اند، پس روی هر
  // زمینه‌ی تازه باید سنجیده شوند.
  const TEXT = rgb("#EDF2F9"), MUTED = rgb("#94A3B8");
  const surfaces = (v) => ["--bg", "--surface-3", "--surface", "--surface-2"].map((k) => rgb(v[k]));
  const presets = T.MINI_PALETTES.map((x) => ({ id: x.id, v: T.themeVars({ palette: x.id }, "dark") }));
  for (let h = 0; h < 360; h += 15) {
    presets.push({ id: "custom " + hslHex(h, 0.9, 0.5), v: T.themeVars({ palette: "custom", accent: hslHex(h, 0.9, 0.5) }, "dark") });
  }
  let wText = { v: 99 }, wMuted = { v: 99 };
  for (const { id, v } of presets) {
    for (const sf of surfaces(v)) {
      const a = contrast(TEXT, sf), b = contrast(MUTED, sf);
      if (a < wText.v) wText = { v: a, id };
      if (b < wMuted.v) wMuted = { v: b, id };
    }
  }
  check("متنِ اصلی روی هر زمینه و سطحِ هر پالت ≥ ۷", wText.v >= 7, `بدترین ${wText.v.toFixed(2)} (${wText.id})`);
  check("متنِ کم‌رنگ روی هر زمینه و سطحِ هر پالت ≥ ۴٫۵", wMuted.v >= 4.5, `بدترین ${wMuted.v.toFixed(2)} (${wMuted.id})`);
  check("هر پالتِ آماده زمینه‌ی تیره دارد (در پوسته‌ی تیره)",
        presets.every(({ v }) => v["--bg"] && contrast(rgb(v["--bg"]), [0, 0, 0]) < 1.3));
  check("در پوسته‌ی روشن زمینه دست نمی‌خورد",
        T.MINI_PALETTES.every((x) => !("--bg" in T.themeVars({ palette: x.id }, "light"))),
        "متغیرِ درون‌خطی روی ریشه قاعده‌ی پوسته‌ی روشن را می‌پوشاند");
  check("اقیانوس همان آبی و فیروزه‌ایِ آشنا است",
        (() => { const v = T.themeVars({ palette: "ocean" }, "dark");
                 const [r, g, b] = rgb(v["--cy"]); return g > r && g > b * 0.8; })(),
        T.themeVars({ palette: "ocean" }, "dark")["--cy"]);

  const fmt = (w) => `بدترین ${w.v.toFixed(2)} (${w.color}، ${w.scheme === "dark" ? "تیره" : "روشن"})`;
  check("متنِ دکمه‌ی شیب‌دار (خرید، پرداخت) ≥ ۴٫۵ روی هر رنگ", worst["on-cy"].v >= 4.5, fmt(worst["on-cy"]));
  check("متنِ دکمه‌ی تک‌رنگ ≥ ۴٫۵", worst["on-accent"].v >= 4.5, fmt(worst["on-accent"]));
  check("عددِ درشتِ کارت ≥ ۳", worst["on-accent-hi"].v >= 3, fmt(worst["on-accent-hi"]));
  check("متنِ برجسته روی زمینه ≥ ۳", worst["accent-2 on bg"].v >= 3, fmt(worst["accent-2 on bg"]));

  // فامِ نماینده باید بماند — پالتی که رنگ را عوض کند، رنگِ او نیست
  const pal = accentPalette("#e84393");
  check("رنگِ نماینده همان است که داده (وقتی در بازه‌ی خوانا است)", pal["--accent"] === "#e84393",
        pal["--accent"]);

  console.log(`\n  ${fail ? R : G}${ok} پاس${X}${fail ? ` · ${R}${fail} ناموفق${X}` : ""}\n`);
  process.exit(fail ? 1 : 0);
})();
