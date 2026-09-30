/**
 * لوگوی فروشگاه — یک جا، برای سربرگِ مینی‌اپ، صفحه‌ی ورود و پرتال.
 *
 * برگه: docs/specs/2026-09-23-mini-theme-studio.md
 *
 * چرا یک کامپوننت: لوگو سه جا دیده می‌شود و اگر هر کدام قاب و زمینه‌ی
 * خودش را داشت، نماینده در پیش‌نمایش یک شکل می‌دید و مشتری در اسپلش
 * شکلِ دیگر.
 *
 * وقتی لوگو نیست — یا عکس باز نشد — **نشانِ خودکار** از حرفِ اولِ نامِ
 * فروشگاه با رنگِ پالت ساخته می‌شود. تا امروز جایش یک مربعِ خنثی بود:
 * نامِ نکسورا را لو نمی‌داد، ولی نامِ فروشگاه را هم نمی‌گفت.
 */
import React from "react";

export const LOGO_SHAPES = [
  { id: "rounded", fa: "گوشه‌گرد" },
  { id: "circle", fa: "دایره" },
  { id: "square", fa: "مربع" },
];
export const LOGO_BGS = [
  { id: "none", fa: "بی‌زمینه" },
  { id: "light", fa: "روشن" },
  { id: "accent", fa: "رنگِ پالت" },
];

/** سبکِ معتبر — هر چه نامعتبر است، پیش‌فرض می‌شود. همان قاعده‌ی بکند. */
export function cleanLogoStyle(s) {
  const x = s && typeof s === "object" ? s : {};
  const pad = Math.round(Number(x.pad));
  return {
    shape: LOGO_SHAPES.some((o) => o.id === x.shape) ? x.shape : "rounded",
    bg: LOGO_BGS.some((o) => o.id === x.bg) ? x.bg : "none",
    pad: Number.isFinite(pad) ? Math.min(24, Math.max(0, pad)) : 0,
  };
}

/**
 * حرفِ نشان — «حسین VPN» → «ح»، «Nova Net» → «NN».
 *
 * دو حرف فقط وقتی هر دو لاتین‌اند. حرفِ فارسی کنارِ لاتین «Vح» می‌شد
 * (جهتِ متن قاطی می‌شود)، و دو حرفِ فارسیِ جدا هم نشانِ آشنایی نیست.
 */
export function initials(name) {
  const words = String(name || "").trim().split(/[\s‌\-_.]+/).filter(Boolean);
  const first = (w) => Array.from(w)[0] || "";
  const latin = (c) => /^[A-Za-z0-9]$/.test(c);
  const a = first(words[0] || ""), b = first(words[1] || "");
  return (latin(a) && latin(b) ? a + b : a).toUpperCase();
}

export function ShopLogo({ src = "", name = "", style, size = 38, className = "" }) {
  const st = cleanLogoStyle(style);
  const [failed, setFailed] = React.useState(false);
  React.useEffect(() => { setFailed(false); }, [src]);
  const showImg = !!src && !failed;
  const pad = showImg ? Math.round((size * st.pad) / 100) : 0;

  return (
    <span className={`nx-shoplogo shape-${st.shape} bg-${showImg ? st.bg : "mono"} ${className}`}
      style={{ width: size, height: size, padding: pad }}
      role="img" aria-label={name || "لوگو"}>
      {showImg ? (
        <img src={src} alt="" onError={() => setFailed(true)} draggable={false} />
      ) : (
        <b style={{ fontSize: Math.round(size * (initials(name).length > 1 ? 0.36 : 0.44)) }}>
          {initials(name) || "•"}
        </b>
      )}
    </span>
  );
}
