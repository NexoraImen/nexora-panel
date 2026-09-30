/**
 * ظاهرِ فروشگاه از دفعه‌ی قبل — برای اولین فریمِ مینی‌اپ.
 *
 * موقعِ اسپلش هنوز `/api/mini/me` نیامده. دفعه‌ی قبل می‌دانستیم مشتریِ
 * کدام فروشگاه است و ظاهرش را نگه داشتیم.
 *
 * کلید **برای هر فروشگاه جداست** (`?shop=` که ربات در آدرس می‌گذارد).
 * همه‌ی فروشگاه‌ها یک /app دارند؛ با یک کلیدِ مشترک، مشتری‌ای که از
 * ربات‌ِ مالک و یک نماینده هر دو می‌خرید اسپلشِ فروشگاهِ دیگر را می‌دید.
 * این شناسه فقط کلیدِ کش است — هویت از امضای initData می‌آید.
 *
 * نوشتن و خواندن یک‌جا تا دو نسخه‌ی کلید از هم جدا نشوند (main.jsx
 * می‌خواند، مینی‌اپ می‌نویسد). `localStorage` ممکن است نباشد؛ هر
 * دسترسی داخلِ try است و نبودنش فقط یعنی اسپلشِ خنثی.
 */
export function shopKey(search = typeof window !== "undefined" ? window.location.search : "") {
  let id = "";
  try { id = new URLSearchParams(search).get("shop") || ""; } catch { /* */ }
  return /^\d{1,9}$/.test(id) ? `nx_shop:${id}` : "nx_shop";
}

export function readShop() {
  try {
    const raw = window.localStorage.getItem(shopKey());
    const v = raw ? JSON.parse(raw) : null;
    return v && typeof v === "object" ? v : null;
  } catch { return null; }
}

export function writeShop(v) {
  try { window.localStorage.setItem(shopKey(), JSON.stringify(v)); } catch { /* */ }
}
