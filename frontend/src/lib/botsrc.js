/**
 * منبعِ داده‌ی بخش‌های ربات — مالک یا نماینده، با یک شکل.
 *
 * چرا وجود دارد:
 *   مالک خواست «تمامی موارد ربات خودم باید دقیقا برای نماینده اعمال
 *   بشه». راهِ آسان کپیِ صفحه‌های کاربران، چت، متن‌ها و سکه در پرتال
 *   بود — و این مخزن می‌داند آخرش چه می‌شود: یک قاعده، دو جا، اصلاح
 *   در یکی. پس همان صفحه‌های پنلِ مالک سوار می‌شوند و فقط **از کجا
 *   می‌خوانند** عوض می‌شود.
 *
 *   مرز در بکند است، نه این‌جا: هر مسیرِ پرتال از
 *   `portal_tenant` رد می‌شود و هر کوئری مستاجرِ خودِ نماینده را دارد.
 *   این فایل فقط آدرس را انتخاب می‌کند.
 *
 * هر مسیر در قالبِ تمیز نوشته شده و پرس‌وجو *بیرون* از قالب چسبیده —
 * تستِ درز مسیرها را از روی همین رشته‌ها با بکند تطبیق می‌دهد.
 */
import { API_URL } from "./constants";
import { errText } from "./format";

async function req(path, headers, { method = "GET", body } = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errText(j.detail, "درخواست ناموفق بود"));
  return j;
}

/** تنظیماتِ خوانده‌شده همیشه یک دیکشنری است، هر چه برگشته باشد. */
function asDict(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}

export function adminSrc(password) {
  const H = { "X-Admin-Password": password || "" };
  return {
    kind: "admin",
    async settings() {
      const d = await req("/api/admin/bot/settings", H);
      return asDict(d.tenant?.settings);
    },
    // مالک کلِ دیکشنری را می‌فرستد — همان رفتارِ قبلی
    saveSettings: (st) => req("/api/admin/bot/settings", H,
                              { method: "PUT", body: { settings: st } }),
    users: (qs) => req("/api/admin/bot/users" + "?" + qs, H),
    subscriber: (tgId) => req(`/api/admin/bot/subscriber/${tgId}`, H),
    message: (tgId, text) => req(`/api/admin/bot/message/${tgId}`, H,
                                 { method: "POST", body: { text } }),
    inbox: (uid) => req("/api/admin/bot/inbox" + (uid ? `?user_id=${uid}` : ""), H),
    inboxSend: (body) => req("/api/admin/bot/inbox/send", H, { method: "POST", body }),
    events: (qs) => req("/api/admin/bot/events" + "?" + qs, H),
    trialJourney: () => req("/api/admin/bot/trial-journey", H),
    previewFlows: () => req("/api/admin/bot/preview-flows", H),
  };
}

export function portalSrc(token) {
  const H = { "X-Portal-Token": token || "" };
  return {
    kind: "portal",
    async settings() {
      const d = await req("/api/portal/bot-settings", H);
      return asDict(d.settings);
    },
    // بکند فقط کلیدهای مجاز را برمی‌دارد و روی بقیه ادغام می‌کند
    saveSettings: (st) => req("/api/portal/bot-settings", H,
                              { method: "PUT", body: { settings: st } }),
    users: (qs) => req("/api/portal/users" + "?" + qs, H),
    subscriber: (tgId) => req(`/api/portal/subscriber/${tgId}`, H),
    message: (tgId, text) => req(`/api/portal/message/${tgId}`, H,
                                 { method: "POST", body: { text } }),
    inbox: (uid) => req("/api/portal/inbox" + (uid ? `?user_id=${uid}` : ""), H),
    inboxSend: (body) => req("/api/portal/inbox/send", H, { method: "POST", body }),
    events: (qs) => req("/api/portal/events" + "?" + qs, H),
    funnel: () => req("/api/portal/funnel", H),
    trialJourney: () => req("/api/portal/trial-journey", H),
    previewFlows: () => req("/api/portal/bot-preview", H),
  };
}
