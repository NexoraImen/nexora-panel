/**
 * کوچک‌کردنِ عکس پیش از فرستادن.
 *
 * چرا لازم است: عکسی که مشتری از صفحه‌ی گوشی‌اش می‌گیرد معمولاً
 * بین ۳ تا ۸ مگابایت است. فرستادنِ خامش سه مشکل دارد — روی
 * اینترنتِ موبایل چند ده ثانیه طول می‌کشد، base64 حجم را یک‌سوم
 * دیگر هم زیاد می‌کند، و سرور با ۴۱۳ ردش می‌کند بی‌آنکه کاربر
 * بفهمد چه کاری می‌توانست بکند.
 *
 * ۱۶۰۰ پیکسل برای چیزی که در پشتیبانی فرستاده می‌شود کافی است:
 * عکسِ خطای اپلیکیشن، رسید، یا صفحه‌ای که کار نمی‌کند — همه در
 * این اندازه خوانا می‌مانند.
 *
 * و اگر مرورگر canvas نداشت یا عکس باز نشد، خودِ فایلِ اصلی
 * برمی‌گردد: کوچک‌نشدن از نفرستادن بهتر است. سرور حدِ خودش را
 * دارد و اگر بزرگ بود، همان‌جا با پیامِ روشن رد می‌کند.
 */

export const IMG_MAX_SIDE = 1600;
export const IMG_QUALITY = 0.82;

/** فایل → dataURL، بدون دست‌زدن به محتوا. */
export function fileToDataUrl(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result || ""));
    r.onerror = () => rej(new Error("فایل خوانده نشد"));
    r.readAsDataURL(file);
  });
}

/**
 * فایلِ تصویر → dataURL کوچک‌شده.
 *
 * برمی‌گرداند `{ data, width, height, bytes }`.
 */
export async function shrinkImage(file, maxSide = IMG_MAX_SIDE,
                                  quality = IMG_QUALITY) {
  const orig = await fileToDataUrl(file);
  const fallback = { data: orig, width: 0, height: 0, bytes: file.size };

  // PNGِ شفاف را به JPEG تبدیل نمی‌کنیم مگر بزرگ باشد: زمینه‌ی
  // شفاف در JPEG سیاه می‌شود و عکسِ برش‌خورده‌ی کاربر خراب درمی‌آید.
  const keepPng = file.type === "image/png" && file.size <= 900 * 1024;
  if (keepPng) return fallback;

  try {
    const img = await new Promise((res, rej) => {
      const i = new Image();
      i.onload = () => res(i);
      i.onerror = () => rej(new Error("عکس باز نشد"));
      i.src = orig;
    });
    const w = img.naturalWidth || img.width;
    const h = img.naturalHeight || img.height;
    if (!w || !h) return fallback;

    const scale = Math.min(1, maxSide / Math.max(w, h));
    // عکسِ کوچکِ کم‌حجم را دوباره فشرده نمی‌کنیم — فقط کیفیت را
    // بی‌دلیل پایین می‌آورد
    if (scale === 1 && file.size <= 700 * 1024) return fallback;

    const cw = Math.max(1, Math.round(w * scale));
    const ch = Math.max(1, Math.round(h * scale));
    const cv = document.createElement("canvas");
    cv.width = cw; cv.height = ch;
    const cx = cv.getContext("2d");
    if (!cx) return fallback;
    cx.drawImage(img, 0, 0, cw, ch);
    const data = cv.toDataURL("image/jpeg", quality);
    if (!data || data.length < 32) return fallback;

    // اگر «کوچک‌شده» از اصل بزرگ‌تر درآمد، اصل را بفرست
    const bytes = Math.round((data.length - (data.indexOf(",") + 1)) * 0.75);
    if (bytes >= file.size) return fallback;
    return { data, width: cw, height: ch, bytes };
  } catch {
    return fallback;
  }
}
