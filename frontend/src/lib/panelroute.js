/**
 * نشانیِ صفحه‌های پنل.
 *
 * چرا لازم شد: پنل هیچ نشانی‌ای نداشت. رفرش یعنی برگشت به
 * داشبورد، دکمه‌ی «عقب» مرورگر یعنی بیرون‌رفتن از پنل، و هیچ صفحه‌ای
 * را نمی‌شد برای کسی فرستاد.
 *
 * چرا هش و نه مسیر: یک باندل سه اپ را سرو می‌کند و کدامش بالا
 * بیاید از `location.pathname` تصمیم گرفته می‌شود (`/`، `/r/<slug>`،
 * `/app`). اگر صفحه‌های پنل هم مسیر بگیرند، با آن انتخاب قاطی
 * می‌شوند و به سرور هم دست باید زد. هش هیچ‌کدام را لازم ندارد و
 * «عقب/جلو» را همان‌قدر درست می‌دهد.
 */

/** فضای کاریِ یک صفحه — از روی خودِ فهرست، نه یک نگاشتِ دستیِ دوم. */
export function workspaceOf(WORKSPACES, key) {
  if (!key) return null;
  return Object.keys(WORKSPACES).find((w) =>
    WORKSPACES[w].groups.some((g) => g.items.some((i) => i.key === key))) || null;
}

/** کلیدِ داخل نشانی. خالی یعنی نشانی چیزی نمی‌گوید. */
export function readKey() {
  try {
    return String(window.location.hash || "").replace(/^#\/?/, "").trim();
  } catch { return ""; }
}

/**
 * نشانی را به این صفحه ببر.
 *
 * `push` تازه‌ای در تاریخچه می‌سازد (کلیکِ کاربر)، و بدونش فقط
 * نشانی را هم‌تراز می‌کند (هم‌گام‌سازی) — وگرنه هر رندر یک ورودیِ
 * تاریخچه می‌سازد و «عقب» بی‌فایده می‌شود.
 */
export function writeKey(key, push) {
  if (!key) return;
  try {
    const want = "#/" + key;
    if (window.location.hash === want) return;
    const url = window.location.pathname + window.location.search + want;
    if (push) window.history.pushState({ key }, "", url);
    else window.history.replaceState({ key }, "", url);
  } catch { /* مرورگرِ عجیب — نشانی نداشتن از کرش بهتر است */ }
}
