/**
 * تشخیصِ اینکه کدام اپ باید بالا بیاید — و بس.
 *
 * چرا جدا از خودِ اپ‌ها: `main.jsx` باید *پیش از* بارگذاریِ هیچ‌کدام
 * تصمیم بگیرد. تا امروز این دو تابع از داخل `portal/index.jsx` و
 * `mini/index.jsx` می‌آمدند، یعنی برای پرسیدنِ «کدام اپ؟» هر سه اپ
 * دانلود می‌شدند — و مشتری‌ای که مینی‌اپ را روی موبایل باز می‌کرد،
 * کلِ پنل مدیر را هم می‌گرفت.
 *
 * حالا این فایل هیچ وابستگی‌ای ندارد، پس سه اپ می‌توانند با
 * `React.lazy` بارگذاری شوند و فقط همان یکی که لازم است برسد.
 */

/** پنل نماینده: /r/<نشانی> */
export function portalSlug() {
  const m = /^\/r\/([A-Za-z0-9_-]+)/.exec(window.location.pathname || "");
  return m ? m[1] : "";
}

/** مینی‌اپ مشتری: /app */
export function isMini() {
  return /^\/app(\/|$)/.test(window.location.pathname || "");
}

/** پنل همکار فروش: /aff */
export function isAff() {
  return /^\/aff(\/|$)/.test(window.location.pathname || "");
}
