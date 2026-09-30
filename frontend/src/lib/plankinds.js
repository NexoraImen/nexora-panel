/**
 * نوعِ پلن — «حجمی» و «کاربر محدود».
 *
 * همین فهرست در `bot/core.py` (`PLAN_KINDS`) است و ربات دکمه‌هایش را از آن
 * می‌سازد؛ `tests/test-shop-funnel.py` برابریِ این دو را می‌سنجد. کلیدِ ناشناس
 * در بکند «حجمی» می‌شود.
 */
export const PLAN_KINDS = [
  { id: "volume", fa: "حجمی" },
  { id: "limited", fa: "کاربر محدود" },
  { id: "pro_license", fa: "نکسورا Pro" },
];

/**
 * VPN kinds only: what a reseller may sell. A Pro license is sold by the owner
 * alone, and only on the server that runs the license issuer
 * (docs/specs/2026-09-30-sell-pro.md); the backend refuses it for a reseller.
 */
export const VPN_KINDS = PLAN_KINDS.filter((k) => k.id !== "pro_license");

/** A `pro_license` plan's license: same list as `core.LICENSE_PLANS` (parity test). */
export const LICENSE_PLANS = [
  { id: "monthly", fa: "ماهانه" },
  { id: "yearly", fa: "سالانه" },
];

export const kindFa = (k) => (PLAN_KINDS.find((x) => x.id === k) || PLAN_KINDS[0]).fa;

/** تب‌هایی که همین حالا در پلن‌ها هست — برای پیشنهاد در ویرایشگر */
export const tabsOf = (plans) => [...new Set((plans || [])
  .map((p) => String(p.tab || "").trim()).filter(Boolean))];

/**
 * گزینه‌های پیش از تست — برای پیش‌نمایشِ مینی‌اپ (`mini/demo.js`). مینی‌اپِ واقعی
 * همین را از `/api/mini/me` می‌گیرد؛ منبع `core.TRIAL_OPERATORS` / `TRIAL_OS`
 * است و `tests/test-shop-funnel.py` برابری را می‌سنجد.
 */
export const TRIAL_OPERATORS = [
  { id: "mci", fa: "همراه اول" }, { id: "irancell", fa: "ایرانسل" },
  { id: "rightel", fa: "رایتل" }, { id: "other", fa: "سایر" },
];
export const TRIAL_OS = [
  { id: "android", fa: "اندروید" }, { id: "ios", fa: "آیفون" },
  { id: "windows", fa: "ویندوز" }, { id: "mac", fa: "مک" },
];
