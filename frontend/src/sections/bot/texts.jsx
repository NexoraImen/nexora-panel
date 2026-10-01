/**
 * ربات: متن پیام‌ها و رفتار.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  BellRing, Loader2, RotateCcw, Save,
} from "lucide-react";
import { adminSrc } from "../../lib/botsrc";
import {
  Field, InfoBox, Msg, NumberInput, NumberStepper, PageSkeleton, SectionHead,
  Tabs, Toggle,
} from "../../ui/index";
import { tgHtml } from "./preview";
import { faNum } from "../../lib/format";

export const BOT_TEXTS = [
  { k: "welcome_text", label: "پیام خوش‌آمد",
    hint: "اگر خالی بماند، وضعیت زنده‌ی کاربر نمایش داده می‌شود",
    vars: ["{name}", "{brand}"],
    sample: "سلام {name} 👋\n\nبه {brand} خوش آمدید." },
  { k: "phone_prompt", label: "درخواست شماره",
    hint: "اختیاری بودن آن را حتماً بگویید", vars: [],
    sample: "📱 اگر شماره‌تان را ثبت کنید، سریع‌تر می‌توانیم کمکتان کنیم." },
  { k: "waiting_text", label: "بعد از ارسال رسید",
    hint: "", vars: ["{order_id}", "{support}"],
    sample: "✅ رسید شما دریافت شد\nکد پیگیری: {order_id}" },
  { k: "reject_text", label: "رد رسید",
    hint: "دلیل رد خودکار جایگزین می‌شود", vars: ["{order_id}", "{reason}", "{support}"],
    sample: "❌ رسید شما تایید نشد\n\nدلیل: {reason}" },
  // پیش‌فرض همان `core.DELIVERED_DEFAULT` است — خالی بماند، همان می‌رود
  { k: "delivered_text", label: "تحویل کانفیگ",
    hint: "خالی بماند، همین نمونه فرستاده می‌شود. QR همیشه جدا می‌آید",
    vars: ["{name}", "{username}", "{link}", "{brand}", "{channel}", "{plan}", "{gb}", "{expires}"],
    sample: "🔑 اشتراک شما با موفقیت ساخته شد.\n\n👤 نام کاربری شما:\n{username}\n\n🔗 لینک اشتراک شما:\n{link}\n\n📌 لطفاً لینک بالا رو کپی کنید و داخل برنامه مورد استفاده‌تون وارد کنید.\n\n📢 کانال {brand}:\n☁️ {channel}\n\n💙 ممنون که {brand} رو انتخاب کردید." },
  { k: "expiry_text", label: "یادآوری انقضا",
    hint: "", vars: ["{days}", "{plan}"],
    sample: "⏰ {days} روز تا پایان اشتراک شما باقی مانده." },
  // پیگیریِ تست — پیش‌فرض‌ها همان `core.TRIAL_MSG_DEFAULTS` (docs/specs/2026-09-27-shop-funnel.md)
  { k: "trial_msg_0", label: "پیگیریِ تست · بلافاصله",
    hint: "همان لحظه‌ی گرفتنِ تست، بعد از لینک", vars: ["{name}", "{brand}"],
    sample: "🎁 {name}، تست {brand} برات فعال شد 💙\n\nیه مقدار باهاش کار کن و سرعت و پایداریش رو خودت امتحان کن.\nهر مشکلی هم داشتی، همین‌جا بهمون بگو 🤝☁️" },
  { k: "trial_msg_8", label: "پیگیریِ تست · ۸ ساعت بعد",
    hint: "با چهار دکمه: عالی، خوب، معمولی، مشکل داشتم", vars: ["{name}", "{brand}"],
    sample: "سلام {name} 🌷\nتا اینجا فرصت کردی تست {brand} رو امتحان کنی؟ 😊\n\nسرعت و اتصالش چطور بوده؟" },
  { k: "trial_msg_8_bad", label: "پیگیریِ تست · «مشکل داشتم»",
    hint: "توضیحِ مشتری به «پیام‌ها» می‌رود", vars: ["{name}", "{brand}"],
    sample: "متأسفیم که تجربه خوبی نداشتی {name} 🙏\nبگو دقیقاً چه مشکلی داشتی تا بررسیش کنیم 🤝💙" },
  { k: "trial_msg_16", label: "پیگیریِ تست · ۱۶ ساعت بعد",
    hint: "با چهار دکمه: سرعت، پایداری، اتصال، رضایت", vars: ["{name}", "{brand}"],
    sample: "یه سؤال کوچیک ازت داریم {name} 🌷\n\nاگه بخوای {brand} رو با یه کلمه توصیف کنی، نظرت چیه؟ 😄" },
  { k: "trial_msg_24", label: "پیگیریِ تست · پایانِ تست",
    hint: "۲۴ ساعت بعد یا وقتی حجمِ تست تمام شد؛ کدِ برگشت (اگر روشن است) خودکار زیرش می‌آید", vars: ["{name}", "{brand}"],
    sample: "{name}، تستت به پایان رسید\nاگر از تست راضی بودی و دوست داشتی ادامه بدی 💙\n\nمی‌تونی سرویس موردنظرت رو مستقیم از مینی‌اپ {brand} انتخاب و خرید کنی 👇\n\n🛒 خرید سریع و آنلاین\n☁️ بدون نیاز به پیام دادن به پشتیبانی" },
  { k: "trial_msg_bought", label: "پیگیریِ تست · بعد از خرید",
    hint: "یک‌بار، همان لحظه‌ی اولین خریدِ کسی که تست گرفته بود", vars: ["{name}", "{brand}"],
    sample: "💙 {name}، خریدت با موفقیت انجام شد!\n\nاشتراکت آماده‌ست و اطلاعات اتصال داخل مینی‌اپ برات قرار گرفته. ✅\n\nاگر برای اتصال مشکلی داشتی، پشتیبانی کنارت هست 🤝☁️" },
  // نظرسنجیِ چند روز بعد از خرید و تمدید — پیش‌فرض‌ها همان `core.TRIAL_MSG_DEFAULTS`
  { k: "fb_msg_buy", label: "نظرسنجی · چند روز بعد از خرید",
    hint: "با چهار دکمه‌ی کیفیت؛ «مشکل داشتم» به «پیام‌ها» می‌رود", vars: ["{name}", "{brand}"],
    sample: "سلام {name} 🌷\nچند روزه که اشتراک {brand} رو داری — راضی هستی؟ 😊\n\nسرعت و اتصالش چطور بوده؟" },
  { k: "fb_msg_renew", label: "نظرسنجی · چند روز بعد از تمدید",
    hint: "همان چهار دکمه", vars: ["{name}", "{brand}"],
    sample: "{name}، ممنون که دوباره {brand} رو انتخاب کردی 💙\n\nاین دوره سرعت و اتصالش چطور بوده؟" },
  { k: "help_text", label: "آموزش نصب",
    hint: "خالی بماند، متن سه‌قدمی پیش‌فرض نمایش داده می‌شود", vars: ["{brand}"],
    sample: "📚 آموزش نصب\n\nسه قدم، کمتر از دو دقیقه:" },
];

/**
 * تنظیم‌هایی که ربات می‌خواند ولی تا امروز هیچ فیلدی در پنل نداشتند.
 *
 * تست درزها (tests/test-seams.py) اینها را پیدا کرد: هر هشت کلید در
 * handlers.py خوانده می‌شد و چون پنل راهی برای نوشتنشان نداشت، همیشه
 * روی مقدار پیش‌فرض قفل بودند. بدترینش trial_enabled بود — «تست رایگان»
 * را به‌هیچ‌وجه نمی‌شد روشن کرد.
 */
export const BOT_BEHAVIOUR = [
  { k: "trial_enabled", type: "bool", def: false, label: "اشتراک تست رایگان",
    hint: "هر کاربر یک بار می‌تواند بگیرد" },
  // پیش از لینکِ تست (docs/specs/2026-09-27-shop-funnel.md) — پیش‌فرض روشن
  { k: "start_on_first_use", type: "bool", def: true, label: "شروع از اولین اتصال",
    hint: "روزهای کانفیگ از وقتی شمرده می‌شود که مشتری اولین بار وصل شود، نه از لحظه‌ی خرید" },
  { k: "delete_expired_days", type: "num", def: 5, min: 0, max: 90,
    label: "پاک‌کردن کانفیگِ تمدیدنشده", unit: "روز",
    hint: "چند روز بعد از تمام‌شدن، کانفیگی که ربات ساخته پاک شود. یک روز قبلش به مشتری خبر می‌دهیم. ۰ یعنی هرگز" },
  { k: "trial_ask_info", type: "bool", def: true, label: "سه سؤال پیش از تست",
    hint: "اپراتور و دستگاه با دکمه، و اسم — در ربات و مینی‌اپ. جواب‌ها در «کاربران» دیده می‌شوند" },
  { k: "trial_journey", type: "bool", def: true, label: "پیگیریِ تست (۸، ۱۶ و ۲۴ ساعت)",
    hint: "نظرسنجی و پیامِ پایانِ تست؛ متن‌هایش در «متن‌ها» است و آمارش در «آمار و قیف»" },
  { k: "feedback_polls", type: "bool", def: true, label: "نظرسنجیِ بعد از خرید و تمدید",
    hint: "چهار دکمه‌ی کیفیت. نتیجه‌اش در «آمار و قیف»" },
  { k: "feedback_after_days", type: "num", def: 3, min: 1, max: 14,
    label: "نظرسنجی چند روز بعد از خرید", unit: "روز",
    hint: "آن‌قدر بعد که مشتری سرویس را امتحان کرده باشد؛ پیش‌فرض ۳ روز" },
  { k: "show_satisfaction", type: "bool", def: true, label: "نشان‌دادنِ رضایتِ مشتری‌ها پیش از خرید",
    hint: "«⭐ ۹۲٪ از مشتری‌ها راضی‌اند — ۱۲۰ نظر» بالای پلن‌ها در ربات و مینی‌اپ؛ از ۱۰ نظر به بالا" },
  { k: "trial_channel", type: "bool", def: true, label: "عضویتِ کانال پیش از تست",
    hint: "فقط اگر کانالِ عضویت را تنظیم کرده باشید؛ حتی وقتی قفلِ کانال برای خرید خاموش است" },
  { k: "ask_phone", type: "bool", def: true, label: "درخواست شماره تماس",
    hint: "همیشه اختیاری است؛ این فقط نمایش دکمه را کنترل می‌کند" },
  { k: "support_username", type: "text", label: "یوزرنیم پشتیبانی",
    ph: "@nexora_support",
    hint: "در پیام‌های خطا و رد رسید به مشتری نشان داده می‌شود" },
  { k: "order_ttl_minutes", type: "num", def: 30, min: 5, max: 1440,
    label: "مهلت پرداخت", unit: "دقیقه",
    hint: "بعد از این مدت سفارش پرداخت‌نشده منقضی می‌شود" },
  { k: "email_prefix", type: "text", label: "پیشوند شناسه کانفیگ",
    ph: "nexora",
    hint: "شناسه‌ی کلاینت در پنل این شکلی ساخته می‌شود: prefix_200 (یک شماره‌ی ترتیبی برای هر اشتراک)" },
  { k: "sub_base_url", type: "text", label: "دامنه‌ی لینک اشتراک",
    ph: "https://sub.nexora.ir",
    hint: "خالی بماند، از تنظیمات خود پنل 3x-ui خوانده می‌شود" },
  // راهنمای قبلی می‌گفت «خودش از دامنه‌ی لینک اشتراک ساخته
  // می‌شود» — که غلط بود و کد صریحاً این کار را نمی‌کند. مالک
  // خالی گذاشت، آدرس هیچ‌وقت نوشته نشد، و مینی‌اپ بی‌صدا نیامد.
  { k: "miniapp_url", type: "miniapp", label: "آدرس مینی‌اپ",
    ph: "https://panel.example.com/app",
    hint: "دامنه‌ی همین پنل + ‎/app‎. معمولاً اولین باری که پنل را "
        + "روی https باز می‌کنید خودش پر می‌شود؛ اگر خالی مانده "
        + "یعنی آن تشخیص کار نکرده و باید دستی بگذاریدش. "
        + "حتماً https — تلگرام با http کلِ پیام را رد می‌کند، نه "
        + "فقط دکمه را. بدون این، دکمه‌ی مینی‌اپ در هیچ رباتی "
        + "(نه شما، نه نماینده‌ها) ظاهر نمی‌شود." },
];

/**
 * آدرسِ مینی‌اپ — با دکمه‌ی «آدرسِ همین پنل».
 *
 * چرا دکمه: این مقدار قرار بود خودکار پر شود، ولی فقط وقتی پنل
 * روی https باز شود **و** هدرش به بک‌اند برسد. روی نصب‌هایی با
 * بلوکِ nginx قدیمی هیچ‌وقت نمی‌رسد و آدرس خالی می‌ماند — بی‌صدا،
 * و مینی‌اپ در هیچ رباتی ظاهر نمی‌شود.
 *
 * مرورگر دامنه را می‌داند. یک دکمه، و تمام.
 */
function MiniappField({ value, ph, onChange }) {
  const here = typeof window !== "undefined" ? window.location : null;
  const secure = !!here && here.protocol === "https:";
  const guess = secure ? `${here.origin}/app` : "";
  const empty = !String(value || "").trim();
  const bad = !empty && !/^https:\/\//i.test(String(value).trim());

  return (
    <div>
      <input className="fx-input" value={value} placeholder={ph}
        onChange={(e) => onChange(e.target.value)}
        style={{ fontFamily: "var(--mono)", direction: "ltr",
                 textAlign: "left" }} />

      {guess && guess !== value && (
        <button onClick={() => onChange(guess)}
          className="fx-btn-g w-full mt-2 py-1.5 text-[12px]"
          title={guess}>
          آدرسِ همین پنل را بگذار
        </button>
      )}

      {/* خالی‌بودن باید *دیده* شود. تا امروز فقط یک فیلدِ خالی بود
          و هیچ‌جا نمی‌گفت نتیجه‌اش چیست. */}
      {empty && (
        <p className="text-[11.5px] mt-2 leading-relaxed"
          style={{ color: "var(--warn)" }}>
          خالی است — دکمه‌ی مینی‌اپ در هیچ رباتی ظاهر نمی‌شود.
          {!secure && " این صفحه روی https نیست، پس آدرس را دستی بگذارید."}
        </p>
      )}
      {bad && (
        <p className="text-[11.5px] mt-2" style={{ color: "var(--danger)" }}>
          باید با ‎https://‎ شروع شود — تلگرام با http کلِ پیام را رد می‌کند.
        </p>
      )}
    </div>
  );
}


/**
 * یادآوری‌ها: روشن/خاموش، آستانه‌ها، و متنِ هشدارِ حجم.
 *
 * چرا این‌جا و نه یک صفحه‌ی جدا: فهرستِ کناریِ بخشِ ربات چهارده قلم
 * دارد و یکی بیشتر یعنی شلوغ‌تر. متنِ یادآوری هم از قبل همین‌جاست —
 * زمان‌بندی کنارِ متنی می‌نشیند که فرمانش را می‌دهد.
 *
 * چرا سه اسلاتِ ثابت: پرچمِ «فرستاده شد» سه ستونِ مشخص است
 * (notified_7d/3d/1d). فهرستِ آزاد یعنی ستونِ notified_14d هم لازم
 * است. سه اسلات که مالک عددشان را عوض می‌کند همان کار را بدونِ
 * مهاجرت می‌کند. صفر یعنی همان اسلات خاموش.
 */
function Reminders({ s, upS }) {
  const r = { enabled: true, days: [7, 3, 1], traffic_pct: 80,
              traffic_text: "", ...(s.reminders || {}) };
  const days = Array.isArray(r.days) ? r.days : [7, 3, 1];
  const up = (patch) => upS({ reminders: { ...r, days, ...patch } });
  const setDay = (i, v) => {
    const next = [days[0] ?? 0, days[1] ?? 0, days[2] ?? 0];
    next[i] = Number(v) || 0;
    up({ days: next });
  };

  const off = !r.enabled;

  return (
    <div className="fx-card p-4">
      <div className="flex items-start justify-between gap-4 pb-3"
        style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold text-white flex items-center gap-2">
            <BellRing size={15} style={{ color: "var(--accent-2)" }} />
            یادآوری‌ها روشن باشند
          </div>
          <div className="text-[12px] mt-1 leading-relaxed"
            style={{ color: "var(--muted)" }}>
            هم یادآوری نزدیک‌شدن انقضا، هم هشدار پرشدن حجم. خاموش‌کردن
            یعنی مشتری اولین خبری که می‌گیرد قطع‌شدن است.
          </div>
        </div>
        <div className="shrink-0">
          <Toggle label="یادآوری‌ها" checked={!!r.enabled}
            onChange={() => up({ enabled: !r.enabled })} />
        </div>
      </div>

      <div style={{ opacity: off ? 0.45 : 1, pointerEvents: off ? "none" : "auto" }}>
        <div className="pt-3">
          <Field label="چند روز مانده یادآوری برود"
            hint="سه نوبت. صفر یعنی آن نوبت فرستاده نشود.">
            <div className="fx-g3 grid grid-cols-3 gap-3">
              {[0, 1, 2].map((i) => (
                <NumberStepper key={i} value={Number(days[i]) || 0}
                  onChange={(v) => setDay(i, v)} min={0} max={90} unit="روز" />
              ))}
            </div>
          </Field>
        </div>

        <Field label="هشدار حجم از چند درصد"
          hint="وقتی مصرف از این درصد رد شود، یک‌بار خبر می‌رود. صفر یعنی این هشدار خاموش.">
          <NumberStepper value={Number(r.traffic_pct) || 0}
            onChange={(v) => up({ traffic_pct: v })} min={0} max={100} unit="٪" />
        </Field>

        <Field label="متن هشدار حجم"
          hint="خالی بماند، متن پیش‌فرض می‌رود. جای‌گذارها: {used} {total} {left} {pct} {plan} {label}">
          <textarea className="fx-input" rows={3} value={r.traffic_text || ""}
            onChange={(e) => up({ traffic_text: e.target.value })}
            placeholder={"📊 {pct}٪ از حجم {label} مصرف شده.\nباقی‌مانده: {left} گیگ"}
            style={{ resize: "vertical", lineHeight: 1.9 }} />
        </Field>

        <InfoBox>
          عوض‌کردنِ عددِ یک نوبت، کسی را که <b>قبلاً همان نوبت را
          گرفته</b> دوباره خبر نمی‌کند. سرِ تمدید پرچم‌ها صفر می‌شوند و
          از آن به بعد عددِ تازه کار می‌کند.
        </InfoBox>
      </div>
    </div>
  );
}

/* دسته‌بندیِ متن‌ها به ترتیبِ سفرِ مشتری. کلیدی که این‌جا نیست (متنِ تازه‌ای
   که به `BOT_TEXTS` اضافه شود و این فهرست فراموش شود) در «دیگر» می‌آید —
   بی‌صدا ناپدید نمی‌شود. */
const TEXT_GROUPS = [
  { t: "شروع", keys: ["welcome_text", "phone_prompt", "help_text"] },
  { t: "خرید و تحویل", keys: ["waiting_text", "reject_text", "delivered_text", "expiry_text"] },
  { t: "پیگیریِ تست", keys: ["trial_msg_0", "trial_msg_8", "trial_msg_8_bad", "trial_msg_16",
                             "trial_msg_24", "trial_msg_bought"] },
  { t: "نظرسنجی", keys: ["fb_msg_buy", "fb_msg_renew"] },
];

// مقدارِ نمونه برای پیش‌نمایش — فقط نمایش؛ ربات مقدارِ واقعی را می‌گذارد
const SAMPLE_VARS = {
  "{name}": "سارا", "{brand}": "فروشگاه شما", "{order_id}": "۴۰۹۸", "{support}": "@support",
  "{reason}": "مبلغ واریزی کمتر است", "{username}": "shop_200",
  "{link}": "https://sub.example.com/sub/shop_200", "{channel}": "@your_channel",
  "{plan}": "۳۰ گیگ یک‌ماهه", "{gb}": "۳۰", "{expires}": "۱۴۰۵/۰۸/۱۲", "{days}": "۳",
};
const fill = (txt) => Object.entries(SAMPLE_VARS)
  .reduce((acc, [k, v]) => acc.split(k).join(v), String(txt || ""));

function groupsOf(texts) {
  const known = new Set(TEXT_GROUPS.flatMap((g) => g.keys));
  const byKey = Object.fromEntries(texts.map((f) => [f.k, f]));
  const out = TEXT_GROUPS.map((g) => ({ t: g.t, items: g.keys.map((k) => byKey[k]).filter(Boolean) }));
  const rest = texts.filter((f) => !known.has(f.k));
  if (rest.length) out.push({ t: "دیگر", items: rest });
  return out.filter((g) => g.items.length);
}

/**
 * ویرایشگرِ یک متن: کادرِ بزرگ، جای‌گذارهای کلیک‌شدنی، و پیش‌نمایشِ زنده.
 *
 * چرا پیش‌نمایش کنارِ کادر: تا ۱.۱۲۳ هر متن یک کادرِ سه‌خطی بود و مالک
 * نمی‌دید «{name}» و «<b>» در تلگرام چه شکلی می‌شوند مگر اینکه ذخیره کند و
 * از ربات امتحان کند. `tgHtml` همان تبدیلِ امنِ پیش‌نمایشِ ربات است.
 */
function TextEditor({ f, value, onChange }) {
  const box = useRef(null);
  const custom = !!String(value || "").trim();
  const insert = (v) => {
    const el = box.current;
    const cur = String(value || "");
    if (!el) { onChange(cur + v); return; }
    const a = el.selectionStart ?? cur.length, b = el.selectionEnd ?? cur.length;
    onChange(cur.slice(0, a) + v + cur.slice(b));
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(a + v.length, a + v.length); });
  };
  return (
    <div className="tx-edit">
      <div className="tx-edit-head">
        <div className="min-w-0">
          <b>{f.label}</b>
          {f.hint && <p>{f.hint}</p>}
        </div>
        {custom && (
          <button onClick={() => onChange("")} className="fx-btn-g px-3 py-1.5 text-[12px] flex items-center gap-1.5 shrink-0"
            title="متنِ خودتان پاک می‌شود و ربات پیش‌فرض را می‌فرستد">
            <RotateCcw size={12} /> پیش‌فرض
          </button>
        )}
      </div>
      {f.vars.length > 0 && (
        <div className="tx-vars" aria-label="جای‌گذارها — با کلیک در جای مکان‌نما گذاشته می‌شود">
          {f.vars.map((v) => (
            <button key={v} onClick={() => insert(v)} title={`گذاشتنِ ${v} — نمونه: ${SAMPLE_VARS[v] || ""}`}>{v}</button>
          ))}
        </div>
      )}
      <div className="tx-panes">
        <textarea ref={box} className="fx-input tx-area" value={value || ""}
          onChange={(e) => onChange(e.target.value)} placeholder={f.sample}
          aria-label={f.label} />
        <div className="tx-phone" aria-label={`پیش‌نمایشِ ${f.label}`}>
          <span className="tx-phone-tag">{custom ? "پیش‌نمایش" : "پیش‌نمایش · متنِ پیش‌فرض"}</span>
          <div className="tx-bubble"
            // امن: `tgHtml` فقط تگ‌های بی‌ویژگی را برمی‌گرداند
            dangerouslySetInnerHTML={{ __html: tgHtml(fill(custom ? value : f.sample)) }} />
        </div>
      </div>
    </div>
  );
}

/* `src` خالی یعنی پنلِ مالک. پرتالِ نماینده `portalSrc` می‌دهد، همراهِ
   `behaviour` کوتاه‌تر (بدونِ پیشوندِ شناسه، آدرسِ مینی‌اپ و پایه‌ی
   لینک — آن‌ها مالِ مالک‌اند) و بدونِ فهرستِ مدیرها، چون نماینده با
   دکمه‌ی «وصلِ من به ربات» مدیرِ رباتش می‌شود. مرزِ واقعی بکند است. */
export function BotTextsSection({ password, src, behaviour = BOT_BEHAVIOUR,
                                  showAdmins = true }) {
  const S = useMemo(() => src || adminSrc(password), [src, password]);
  const [t, setT] = useState(null);
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  // سه زبانه به‌جای یک صفحه‌ی ۳۲۰۰ پیکسلی: ۱۷ کادرِ متن، بعد یادآوری‌ها،
  // بعد رفتارِ ربات — هرکدام کاری جدا، و مالک برای رسیدن به یک کلید باید
  // از روی همه رد می‌شد. ذخیره هر سه را با هم می‌فرستد، پس عوض‌کردنِ
  // زبانه چیزی را گم نمی‌کند.
  const [tab, setTab] = useState("texts");
  const [cur, setCur] = useState(BOT_TEXTS[0].k);

  const load = async () => {
    try {
      const st = await S.settings();
      setT({ settings: st });
      setSaved(JSON.stringify(st));
    } catch (e) { setMsg({ t: "err", m: e.message || "اتصال برقرار نشد" }); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [S]);
  useEffect(() => { if (msg) { const x = setTimeout(() => setMsg(null), 4000); return () => clearTimeout(x); } }, [msg]);

  const s = t?.settings || {};
  const upS = (patch) => setT({ ...t, settings: { ...s, ...patch } });
  const dirty = !!t && JSON.stringify(t.settings) !== saved;

  const save = async () => {
    setSaving(true);
    try {
      await S.saveSettings(t.settings);
      setSaved(JSON.stringify(t.settings));
      setMsg({ t: "ok", m: "ذخیره شد — ربات فوری اعمال می‌کند" });
    } catch (e) {
      // دلیلِ واقعی، نه «ناموفق» — بکندِ پرتال می‌گوید کدام عدد بیرون از بازه بود
      setMsg({ t: "err", m: e.message || "ذخیره ناموفق" });
    } finally { setSaving(false); }
  };

  if (loading) return <PageSkeleton />;

  const groups = groupsOf(BOT_TEXTS);
  const f = BOT_TEXTS.find((x) => x.k === cur) || BOT_TEXTS[0];
  const edited = BOT_TEXTS.filter((x) => String(s[x.k] || "").trim()).length;

  return (
    <div className="fx-anim">
      <SectionHead title="متن‌ها و رفتارِ ربات"
        desc="هر پیامی که ربات می‌فرستد، یادآوری‌ها و رفتارش. تغییرات بدون ری‌استارت اعمال می‌شوند."
        action={
          <div className="flex items-center gap-2">
            {dirty && <span className="text-[12px]" style={{ color: "var(--warn)" }}>تغییرِ ذخیره‌نشده</span>}
            <button onClick={save} disabled={saving || !dirty} className="fx-btn px-4 py-2 text-[13.5px] flex items-center gap-1.5">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} ذخیره
            </button>
          </div>
        } />

      <Msg msg={msg} />

      <Tabs active={tab} onChange={setTab} items={[
        { key: "texts", label: edited ? `متن‌ها · ${faNum(edited)} ویرایش‌شده` : "متن‌ها" },
        { key: "reminders", label: "یادآوری‌ها" },
        { key: "behaviour", label: "رفتارِ ربات" },
      ]} />

      {tab === "texts" && (
        <div className="fx-card tx-split">
          <nav className="tx-list" aria-label="متن‌ها">
            {groups.map((g) => (
              <div key={g.t} className="tx-group">
                <div className="tx-group-t">{g.t}</div>
                {g.items.map((x) => {
                  const on = x.k === f.k;
                  const mine = !!String(s[x.k] || "").trim();
                  return (
                    <button key={x.k} onClick={() => setCur(x.k)} aria-current={on ? "true" : undefined}
                      className={`tx-item ${on ? "on" : ""}`}>
                      <span className="truncate">{x.label.replace(/^پیگیریِ تست · |^نظرسنجی · /, "")}</span>
                      <i className={mine ? "mine" : ""} title={mine ? "متنِ خودتان" : "متنِ پیش‌فرض"} />
                    </button>
                  );
                })}
              </div>
            ))}
          </nav>
          <TextEditor key={f.k} f={f} value={s[f.k] || ""} onChange={(v) => upS({ [f.k]: v })} />
        </div>
      )}

      {tab === "reminders" && <Reminders s={s} upS={upS} />}

      {tab === "behaviour" && (
      <div className="fx-card p-4">
        {behaviour.map((f) => {
          // نشانی‌ها زیرِ برچسب می‌نشینند، نه در ستونِ ۲۰۰ پیکسلی کنارش.
          // آنجا «https://panel.example.com/app» بریده می‌شد و هشدارِ
          // خالی‌بودنِ مینی‌اپ در چهار خطِ باریک زیرِ ورودی می‌پیچید.
          const wide = f.type === "miniapp" || f.k === "sub_base_url";
          return (
          <div key={f.k}
            className={wide ? "py-2" : "flex items-center justify-between gap-4 py-2"}
            style={{ borderBottom: "1px solid var(--border)" }}>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-semibold text-white">{f.label}</div>
              <div className="text-[11.5px] leading-relaxed"
                style={{ color: "var(--muted)" }}>{f.hint}</div>
            </div>
            <div className={wide ? "mt-2.5 w-full max-w-[520px]" : "shrink-0"}
              style={wide ? undefined : { width: f.type === "bool" ? "auto" : 170 }}>
              {f.type === "bool" && (
                <Toggle label={f.label}
                  checked={s[f.k] === undefined ? f.def : !!s[f.k]}
                  onChange={() => upS({ [f.k]: !(s[f.k] === undefined ? f.def : !!s[f.k]) })} />
              )}
              {f.type === "num" && (
                <div className="flex items-center gap-2">
                  <NumberInput className="fx-input" min={f.min} max={f.max}
                    value={s[f.k] ?? f.def}
                    onChange={(e) => upS({ [f.k]: Number(e.target.value) || f.def })}
                    style={{ textAlign: "center" }}  />
                  <span className="text-[12px] shrink-0"
                    style={{ color: "var(--muted)" }}>{f.unit}</span>
                </div>
              )}
              {f.type === "text" && (
                <input className="fx-input" value={s[f.k] || ""} placeholder={f.ph}
                  onChange={(e) => upS({ [f.k]: e.target.value })}
                  style={{ fontFamily: "var(--mono)", direction: "ltr", textAlign: "left" }} />
              )}
              {/* آدرسِ مینی‌اپ: مرورگر دامنه‌ی پنل را می‌داند، پس
                  لازم نیست کسی تایپش کند یا ssh بزند. */}
              {f.type === "miniapp" && (
                <MiniappField value={s[f.k] || ""} ph={f.ph}
                  onChange={(v) => upS({ [f.k]: v })} />
              )}
            </div>
          </div>
          );
        })}

        {/* مدیرها آیدی عددی‌اند، پس هر خط یک عدد — نه CSV که با فاصله خراب شود */}
        {showAdmins && <div className="pt-3">
          <Field label="مدیرهای ربات"
            hint="هر خط یک آیدی عددی تلگرام. اینها دسترسی پنل مدیریت داخل ربات را دارند.">
            <textarea className="fx-input" rows={3}
              value={(s.admins || []).join("\n")}
              onChange={(e) => upS({
                admins: e.target.value.split("\n")
                  .map((x) => parseInt(x.trim(), 10))
                  .filter((x) => Number.isFinite(x)),
              })}
              placeholder={"123456789\n987654321"}
              style={{ fontFamily: "var(--mono)", direction: "ltr",
                       textAlign: "left", resize: "vertical" }} />
          </Field>
        </div>}
      </div>
      )}
    </div>
  );
}

// پیش‌نمایشِ ربات به `sections/bot/preview.jsx` رفت و حالا از خودِ ربات ساخته
// می‌شود؛ متن‌های دست‌نوشته‌ی این‌جا از ربات عقب افتاده بودند.
