/**
 * هوک‌های مشترک.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useEffect, useRef } from "react";

/**
 * پولینگ که وقتی تب دیده نمی‌شود متوقف می‌شود.
 *
 * قبلاً صفحه‌ی مانیتورینگ هر ۵ ثانیه سرور را صدا می‌زد — حتی وقتی
 * پنل ساعت‌ها در یک تب پس‌زمینه باز مانده بود. هر فراخوانی روی سرور
 * چند subprocess اجرا می‌کند (ss، systemctl، ps)، پس این یعنی بار
 * دائمی روی همان سروری که قرار است سبک بماند.
 *
 * ms=0 یعنی پولینگ خاموش.
 */
export function usePolling(fn, ms, deps = []) {
  const saved = useRef(fn);
  useEffect(() => { saved.current = fn; });

  useEffect(() => {
    if (!ms) return undefined;
    let timer = null;

    const tick = () => { if (!document.hidden) saved.current(); };
    const start = () => { if (!timer) timer = setInterval(tick, ms); };
    const stop = () => { if (timer) { clearInterval(timer); timer = null; } };

    const onVis = () => {
      if (document.hidden) { stop(); return; }
      // برگشت به تب: یک‌بار فوری تازه کن، بعد دوباره زمان‌بندی
      saved.current();
      start();
    };

    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVis);
    return () => { stop(); document.removeEventListener("visibilitychange", onVis); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);
}

/**
 * جست‌وجوی باتأخیر — که بارِ اول اجرا نمی‌شود.
 *
 * چرا این قلّاب لازم شد: الگوی معمولِ «دیبونس» این شکل بود
 *
 *     useEffect(() => { load(); }, [password]);          // بارِ اول
 *     useEffect(() => {                                   // و دوباره!
 *       const t = setTimeout(() => load(), 350);
 *       return () => clearTimeout(t);
 *     }, [q]);
 *
 * و افکتِ دوم **هنگام سوارشدن هم اجرا می‌شود**، چون `q` از خالی
 * شروع می‌شود. اندازه‌گیری روی «کاربران ربات»: دو درخواستِ کاملاً
 * یکسان، یکی در ۱۰ میلی‌ثانیه و یکی در ۳۷۲ — و دومی دوباره
 * `loading` را روشن می‌کرد، پس فهرست می‌آمد و بلافاصله به اسکلت
 * برمی‌گشت. از بیرون «لگ» و «چند بار رندر» دیده می‌شد.
 *
 * تابع در ref نگه داشته می‌شود تا همیشه تازه‌ترین نسخه‌اش صدا زده
 * شود، بدون اینکه عوض‌شدنِ خودش تایمر را از نو بیندازد.
 */
export function useDebouncedChange(value, ms, fn) {
  const first = useRef(true);
  const latest = useRef(fn);
  latest.current = fn;

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return undefined;
    }
    const t = setTimeout(() => latest.current?.(), ms);
    return () => clearTimeout(t);
    // فقط به خودِ مقدار وابسته است؛ تابع در ref است
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, ms]);
}
