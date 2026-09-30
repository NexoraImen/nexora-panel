/**
 * کمکی‌های نمایش: رقم فارسی، حجم، تاریخ.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
export const fmtBytes = (n) => {
  const b = Number(n || 0);
  if (b <= 0) return "۰";
  const gb = b / 1073741824;
  // حجمِ ماهانه‌ی یک سرور به ترابایت می‌رسد؛ «۲۴۵۰٫۳ GB» خوانا نیست
  if (gb >= 1024) return `${(gb / 1024).toFixed(2)} TB`;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  return `${(b / 1048576).toFixed(0)} MB`;
};

export const fmtDate = (ms) => {
  if (!ms) return "بدون انقضا";
  try {
    return new Date(Number(ms)).toLocaleDateString("fa-IR");
  } catch { return "—"; }
};

export const daysLeft = (ms) => {
  if (!ms) return null;
  const d = Math.ceil((Number(ms) - Date.now()) / 86400000);
  return d;
};

// faNum یک عدد می‌خواهد؛ برای رشته‌هایی مثل «13:45:22» یا نسخه‌ی
// کرنل باید رقم‌به‌رقم تبدیل کرد، وگرنه NaN می‌شود.
export const toFaDigits = (s) =>
  String(s ?? "").replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);

export function fmtUptime(s) {
  if (!s) return "—";
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
  if (d) return `${faNum(d)} روز و ${faNum(h)} ساعت`;
  const m = Math.floor((s % 3600) / 60);
  return h ? `${faNum(h)} ساعت و ${faNum(m)} دقیقه` : `${faNum(m)} دقیقه`;
}

export function fmtSize(n) {
  if (n === null || n === undefined) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = Number(n);
  while (Math.abs(v) >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${faNum(v.toFixed(i ? 1 : 0))} ${u[i]}`;
}

/** نام کاربر ممکن است HTML داشته باشد — React خودش امن می‌کند، این فقط تمیزکاری است. */
export const esc0 = (s) => (s == null ? "" : String(s));

/**
 * عدد با رقم فارسی و جداکننده‌ی هزارگان.
 *
 * نسخه‌ی قبلی `Number(n||0).toLocaleString("fa-IR")` بود. مشکل این
 * است که `Number("۱۲ مهر")` برابر NaN می‌شود و `NaN.toLocaleString`
 * با محلی فارسی رشته‌ی **«ناعدد»** برمی‌گرداند — که در صفحه‌ی
 * حسابداری به‌جای مبلغ چاپ می‌شد و هیچ معنایی برای کاربر نداشت.
 *
 * حالا سه حالت جدا می‌شوند:
 *   · خالی یا تعریف‌نشده  →  خط تیره؛ یعنی «مقداری ثبت نشده»
 *   · عدد واقعی           →  قالب‌بندی فارسی
 *   · متنِ غیرعددی        →  فقط رقم‌هایش فارسی می‌شود
 *
 * هیچ مسیری به «ناعدد» نمی‌رسد.
 */
export const faNum = (n, empty = "—") => {
  if (n === null || n === undefined || n === "") return empty;
  if (typeof n === "number") {
    return Number.isFinite(n) ? n.toLocaleString("fa-IR") : empty;
  }
  if (typeof n === "boolean") return n ? "بله" : "خیر";

  const s = String(n).trim();
  if (!s) return empty;

  // رشته‌ای که کاملاً یک عدد است (با یا بدون جداکننده) عدد حساب می‌شود
  const bare = s.replace(/[,،\s]/g, "");
  if (/^-?\d+(\.\d+)?$/.test(bare)) {
    const v = Number(bare);
    if (Number.isFinite(v)) return v.toLocaleString("fa-IR");
  }

  // وگرنه متن است — «۱۳:۴۵:۲۲»، «۶.۸.۰-۱۰۰۲»، هرچه — فقط رقم‌ها
  return toFaDigits(s);
};

/**
 * پیام خطای سرور را به یک رشته‌ی قابل نمایش تبدیل می‌کند.
 *
 * FastAPI برای خطای اعتبارسنجی، detail را به‌شکل آرایه‌ای از آبجکت
 * برمی‌گرداند. اگر همان را مستقیم در JSX بگذاریم، React خطای
 * «Objects are not valid as a React child» می‌دهد و **کل صفحه سیاه
 * می‌شود** — دقیقاً همان چیزی که موقع بستن آی‌پی اتفاق می‌افتاد.
 *
 * پس هیچ‌جا detail خام رندر نمی‌شود؛ همه از این رد می‌شوند.
 */
/**
 * پاسخِ خواندن را باز می‌کند، یا با دلیلِ خودِ بکند می‌ایستد.
 *
 * الگوی `if (res.ok) setX(await res.json())` بدون else، و
 * `fetch(...).then(r => r.json())` بدون سنجیدنِ status، هر دو خطای
 * سرور را به «فهرستِ خالی» تبدیل می‌کردند: کارتِ بازگردانی
 * می‌گفت «نسخه‌ای نیست» وقتی خواندنش شکسته بود. این یک تابع جای
 * هر دو است. پاسخِ غیرِJSON (صفحه‌ی خطای nginx) هم پیامِ خوانا
 * می‌دهد، نه SyntaxError.
 */
/**
 * پیامِ خوانا از یک خطای fetch.
 *
 * `fetch` روی شبکه‌ی قطع TypeError می‌دهد با متنِ انگلیسیِ مرورگر
 * («Failed to fetch»)؛ آن را فارسی می‌کنیم. هر خطای دیگر — که از
 * `okJson` با دلیلِ خودِ بکند می‌آید — همان‌طور می‌ماند. پیش‌تر هر
 * catch فقط «اتصال برقرار نشد» می‌گفت، حتی وقتی سرور گفته بود چرا.
 */
export function errMsg(e, net = "اتصال به سرور برقرار نشد") {
  if (!e || e instanceof TypeError || !e.message) return net;
  return e.message;
}

export async function okJson(res, fallback = "خواندن از سرور ناموفق بود") {
  let j = null;
  try { j = await res.json(); } catch { j = null; }
  if (!res.ok) {
    throw new Error(errText(j && typeof j === "object" ? j.detail : null,
                            `${fallback} (${res.status})`));
  }
  if (j === null) throw new Error(`${fallback} — پاسخ JSON نبود`);
  return j;
}

export function errText(detail, fallback = "عملیات ناموفق بود") {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d === "string") return d;
        if (d && typeof d === "object") {
          const where = Array.isArray(d.loc) ? d.loc.filter(
            (x) => x !== "body" && typeof x === "string").join(".") : "";
          return where ? `${where}: ${d.msg || ""}` : (d.msg || "");
        }
        return "";
      })
      .filter(Boolean);
    return parts.length ? parts.join(" · ") : fallback;
  }
  if (typeof detail === "object") {
    return detail.msg || detail.message || detail.detail || fallback;
  }
  return String(detail);
}

/**
 * حرفِ فارسی — نه رقمِ فارسی.
 *
 * ارقام فارسی (۰-۹) در محدوده‌ی U+06F0..U+06F9 نشسته‌اند و عمداً
 * بیرون گذاشته شده‌اند: عدد در فونت مونو درست و خواناست، مشکل فقط
 * حرف است.
 */
export const hasFaLetter = (s) =>
  /[ؠ-يٮ-ۓۮۯۺ-ۿ]/.test(String(s ?? ""));

/**
 * فونت مونو فقط برای شناسه‌های لاتین.
 *
 * زنجیره‌ی --mono با JetBrains Mono شروع می‌شود و آن فونت **هیچ
 * گلیف فارسی ندارد**. نامی که فارسی باشد و در این فونت بیفتد، به
 * مونوی جایگزینِ سیستم می‌افتد و بسیار پهن‌تر از متنِ دور و برش
 * رندر می‌شود. اندازه گرفته شد: «اعتبار» در مونو ۱۰۸ پیکسل، در فونت
 * اصلی ۶۳ پیکسل — یعنی ۷۱٪ پهن‌تر، درست وسط یک خط.
 *
 * پس مونو را فقط جایی می‌گذاریم که ارزشش را دارد: شناسه‌ی لاتین،
 * که در آن تفاوتِ l و 1 و O و 0 مهم است.
 */
export const monoIf = (s) => (hasFaLetter(s) ? undefined : "var(--mono)");

/**
 * تاریخِ شمسی برای *خواندن*.
 *
 * چرا یک تابع جدا و نه فقط toFaDigits: بک‌اند تاریخ را با رقمِ
 * لاتین می‌دهد (`1405/07/18`) چون همان مقدار به CSV و PDF هم
 * می‌رود، جایی که لاتین درست است. ولی روی صفحه، کنارِ «انقضا» و
 * «۲۳ روز مانده»، تنها عددِ لاتینِ کادر می‌شود و مثل وصله دیده
 * می‌شود — مالک هم دقیقاً همین را گفت.
 *
 * جداکننده هم عوض می‌شود: در متنِ راست‌به‌چپ، `/` مرزِ جهت می‌سازد
 * و ترتیبِ اجزا را به‌هم می‌ریزد؛ `‎/‎` نه.
 */
export const faDate = (v, empty = "—") => {
  const s = String(v == null ? "" : v).trim();
  if (!s) return empty;
  return toFaDigits(s);
};
