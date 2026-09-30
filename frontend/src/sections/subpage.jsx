/**
 * صفحه‌ی اشتراک مشتری.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect } from "react";
import {
  Activity, AlertTriangle, ShoppingCart, TrendingUp, Wallet, Bell, Check, CheckCircle2, ChevronLeft, Clock, Copy, Download, ExternalLink, Eye, Gift, Globe, HelpCircle, Key, Layers, LayoutGrid, Loader2, MessageCircle, MessageSquare, Package, Palette, PlayCircle, Plus, Search, ShieldCheck, Sliders, Smartphone, Star, Trash2, Type, Upload, UserPlus, Users, Video,
} from "lucide-react";
import { errMsg, errText, faNum, okJson } from "../lib/format";
import { NexoraMark } from "../lib/mark.jsx";
import { ProMark, allowed, proPresent, useLicense } from "../ui/pro";
import { API_URL, LANG_TABS, OS_TABS, SCHEME_ICON, SCHEME_OPTIONS, WS_MODES } from "../lib/constants";
import { WsModePreview } from "../shell/workspace";
import { AreaChart, BarList, ConfirmModal, Donut, EmptyState, Field, InfoBox, Msg, NumberStepper,
  SectionHead, Segmented, Skeleton, SkeletonCards, Sparkline, StatTile,
  Tabs, Toggle } from "../ui/index";
import { TemplateThumb } from "./bot/themes";
import { isoToJalaliStamp } from "../ui/jalali";

/**
 * داشبورد — اولین چیزی که مالک بعد از ورود می‌بیند.
 *
 * چه چیزی عوض شد و چرا:
 *
 * نسخه‌ی قبل چهار شمارنده‌ی محتوا داشت (چند اپ، چند سوال، چند
 * ویدیو) با اسپارک‌لاین‌هایی که **عدد ساختگی** بودند — `[2,3,3,4,5,5]`
 * در خودِ کد نوشته شده بود. یعنی نموداری که چیزی را نشان نمی‌داد و
 * فقط شبیه نمودار بود.
 *
 * حالا همان جا کارِ واقعیِ کسب‌وکار را نشان می‌دهد: کاربر تازه،
 * سفارش، درآمد، نرخ تبدیل — همه از `/api/admin/bot/users/report` که
 * از قبل وجود داشت و هیچ صفحه‌ای جز گزارشِ فروش از آن نمی‌خواند.
 * اسپارک‌لاین‌ها هم از سریِ `daily` همان پاسخ می‌آیند، نه از عددِ
 * دستی.
 *
 * شمارنده‌های محتوا نرفتند؛ یک ردیفِ کوچک‌تر پایین‌تر شدند. آن‌ها
 * وضعیتِ صفحه‌اند، نه شاخصِ کسب‌وکار، و نباید با هم رقابت کنند.
 */
/**
 * صورتحساب نماینده‌ها — خلاصه‌ی داشبورد.
 *
 * چرا این‌جا: ستونِ کناری از کارتِ محتوا بلندتر بود و زیرش ۲۱۱
 * پیکسل حفره می‌ماند. کش‌دادنِ کارتِ محتوا فقط همان حفره را به
 * داخلِ کارت می‌برد؛ چیزی که جایش می‌نشیند باید *حرفی برای گفتن*
 * داشته باشد.
 *
 * و `billing/overview` از قبل بود و هیچ صفحه‌ای صدایش نمی‌زد — در
 * فهرستِ بدهی‌های تستِ درز هم ثبت شده بود.
 *
 * عنوان «بدهی» است نه «فروش»: این عدد چیزی است که نماینده باید
 * بدهد، نه چیزی که فروخته. در این مخزن این دو را یک‌بار قاطی
 * کرده‌ایم و عددی ساختند که درست به نظر می‌رسید.
 */
function BillingMini({ data, onGo }) {
  if (data && data.ready === false) return null;
  const groups = (data?.groups || [])
    .filter((g) => g.billed !== false && (g.due || 0) > 0)
    .sort((a, b) => (b.due || 0) - (a.due || 0))
    .slice(0, 5);
  const max = groups.reduce((m, g) => Math.max(m, g.due || 0), 0) || 1;

  return (
    /* کارتِ شبکه تا قدِ ردیف کش می‌آید؛ بدونِ `flex-col` محتوایش
       بالا جمع می‌شود و زیرش حفره می‌ماند */
    <div className="fx-card p-5 flex flex-col">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div>
          <h3 className="text-[14px] font-bold text-white">بدهی نماینده‌ها</h3>
          <p className="text-[12px] mt-1" style={{ color: "var(--muted)" }}>
            این دوره · تومان
          </p>
        </div>
        <button onClick={onGo}
          className="fx-btn-g px-3 py-1.5 text-[12.5px] flex items-center gap-1.5">
          صورتحساب <ChevronLeft size={12} />
        </button>
      </div>

      {!data ? (
        <Skeleton h={120} />
      ) : data.error ? (
        <p className="text-[13px]" style={{ color: "var(--danger)" }}>{data.error}</p>
      ) : data.locked ? (
        <p className="text-[13px] leading-relaxed" style={{ color: "var(--muted)" }}>
          <ProMark feature="accounting" className="ml-1.5" />{data.locked}
        </p>
      ) : !groups.length ? (
        <EmptyState icon={Layers} text="بدهی بازی نیست"
          hint="هر نماینده‌ای که این دوره کانفیگ ساخته باشد، این‌جا با مبلغش می‌آید." />
      ) : (
        /* ردیف‌ها کنارِ هم، نه پخش در قدِ کارت: `justify-between` هر چه
           کارت بلندتر بود فاصله را بیشتر می‌کرد و بینِ دو ردیف ۶۰ پیکسل
           خالی می‌ماند */
        <div className="fx-rowlist">
          {groups.map((g) => (
            <div key={g.name} className="flex items-center gap-3">
              <span className="text-[13px] shrink-0" style={{ color: "var(--dim)", minWidth: 62 }}>
                {g.label || g.name}
              </span>
              <span className="flex-1 h-2 rounded-full overflow-hidden"
                style={{ background: "var(--hair-2)" }}>
                <span className="block h-full rounded-full"
                  style={{ width: `${Math.max(6, Math.round((g.due / max) * 100))}%`,
                           background: "linear-gradient(90deg,var(--accent),var(--accent-2))" }} />
              </span>
              <b className="text-[12.5px] shrink-0 fx-stat-num"
                style={{ color: "var(--text)" }}>{faNum(g.due)}</b>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function OverviewSection({ config, stats, navigate, dirty, password }) {
  const [rep, setRep] = useState(null);
  /* صورتحسابِ نماینده‌ها.
     این مسیر از قبل بود و هیچ صفحه‌ای صدایش نمی‌زد — در فهرستِ
     «بدهی»های تستِ درز هم ثبت شده بود. حالا ستونِ خالیِ داشبورد را
     با عددِ واقعی پر می‌کند، نه با بزرگ‌کردنِ یک کارتِ تمام‌شده. */
  const [bill, setBill] = useState(null);
  const [days, setDays] = useState(30);
  const [err, setErr] = useState("");
  // Accounting is Pro. Locked or not in this build, the card says so in one
  // line instead of asking a route that answers 403 (or does not exist) and
  // showing that as a failure.
  const lic = useLicense(password);
  const billOpen = !!lic && !lic.error && proPresent("billing") && allowed(lic, "accounting");
  const billShown = !lic ? null
    : lic.error ? { error: lic.error }
    : billOpen ? bill
    : { locked: allowed(lic, "accounting")
        ? "این بخش در بسته‌ی Pro این سرور نیست؛ بسته‌ی Pro را دوباره نصب کنید."
        : (lic.denials || {}).accounting || "حسابداری بخشی از نسخه‌ی Pro است." };

  useEffect(() => {
    if (!billOpen) return undefined;
    let alive = true;
    fetch(`${API_URL}/api/admin/billing/overview`,
      { headers: { "X-Admin-Password": password } })
      // پیش‌تر خطای HTTP `null` می‌شد (اسکلتِ همیشگی) و خطای شبکه
      // `ready: false` (کارت پنهان، انگار حسابداری تنظیم نشده)
      .then((r) => okJson(r, "خواندنِ بدهی‌ها ناموفق بود"))
      .then((j) => { if (alive) setBill(j); })
      .catch((e) => { if (alive) setBill({ error: errMsg(e) }); });
    return () => { alive = false; };
  }, [password, billOpen]);

  useEffect(() => {
    let alive = true;
    setRep(null);
    setErr("");
    fetch(`${API_URL}/api/admin/bot/users/report?days=${days}`,
      { headers: { "X-Admin-Password": password } })
      .then((r) => okJson(r))
      .then((j) => {
        if (!alive) return;
        // ربات ممکن است اصلاً وصل نباشد — آن حالت باید *گفته* شود،
        // نه اینکه صفحه خالی بماند و مالک فکر کند خراب است
        if (j && j.ready === false) setErr(errText(j.error, "دیتابیس ربات در دسترس نیست"));
        setRep(j || {});
      })
      .catch((e) => alive && setErr(errMsg(e)));
    return () => { alive = false; };
  }, [days, password]);

  const daily = (rep?.daily || []);
  const orderSeries = daily.map((d) => Number(d.n) || 0);
  const moneySeries = daily.map((d) => Number(d.sum) || 0);
  const o = rep?.orders || {};
  const u = rep?.users || {};
  const s = rep?.subs || {};

  const appsCount = stats?.appsCount ?? OS_TABS.reduce((a, t) => a + (config.downloadApps?.[t.key]?.length || 0), 0);
  const faqCount = stats?.faqCount ?? LANG_TABS.reduce((a, t) => a + (config.faq?.[t.key]?.length || 0), 0);
  const videosCount = stats?.videosCount ?? (config.videos?.length || 0);
  const resellerCount = (config.resellers || []).filter((r) => r.enabled !== false).length;

  const content = [
    { key: "apps", label: "اپلیکیشن‌ها", value: appsCount, icon: Smartphone, sub: "روی ۳ پلتفرم" },
    { key: "faq", label: "سوالات متداول", value: faqCount, icon: HelpCircle, sub: "در ۴ زبان" },
    { key: "videos", label: "ویدیوهای آموزشی", value: videosCount, icon: Video, sub: videosCount ? "قابل نمایش" : "هنوز اضافه نشده" },
    { key: "resellers", label: "واسطه‌های فعال", value: resellerCount, icon: Users, sub: "برند اختصاصی" },
  ];

  const features = [
    { l: "بنرهای هشدار", on: config.banners?.enabled, k: "banners" },
    { l: "کارت رفرال", on: config.referral?.enabled, k: "referral" },
    { l: "سوالات متداول", on: config.advanced?.showFaqSection !== false, k: "settings" },
    { l: "پاپ‌آپ راهنما", on: config.advanced?.showNotificationPopup !== false, k: "settings" },
  ];

  const busy = !rep && !err;

  return (
    <div className="fx-anim">

      {/* ── ردیف شاخص‌ها ── */}
      {busy ? <SkeletonCards n={4} /> : (
        <div className="fx-g4 grid grid-cols-4 gap-3">
          <StatTile
            label="کاربران تازه" icon={UserPlus} tone="var(--accent-2)"
            value={faNum(u.newUsers ?? 0)}
            unit={`از ${faNum(u.users ?? 0)} کل`}
            hint={`${faNum(u.blocked ?? 0)} نفر بلاک شده`}
            color="var(--text)" />
          <StatTile
            label="سفارش موفق" icon={ShoppingCart} tone="var(--ok)"
            value={faNum(o.approved ?? 0)}
            hint={`${faNum(o.pending ?? 0)} در انتظار تأیید`}
            spark={orderSeries} sparkColor="var(--ok)" color="var(--text)" />
          <StatTile
            label="درآمد دوره" icon={Wallet} tone="var(--accent-2)"
            value={faNum(o.revenue ?? 0)} unit="تومان"
            hint={`میانگین ${faNum(o.avg ?? 0)} تومان`}
            spark={moneySeries} sparkColor="var(--accent-2)" color="var(--text)" />
          <StatTile
            label="نرخ تبدیل" icon={TrendingUp} tone="var(--purple)"
            value={faNum(rep?.conversion ?? 0)} unit="درصد"
            hint={`${faNum(rep?.buyerCount ?? 0)} خریدار از ${faNum(u.newUsers ?? 0)} نفر`}
            color="var(--text)" />
        </div>
      )}

      {err && (
        <div className="fx-card p-4" style={{ borderColor: "var(--warn-line)", background: "var(--warn-soft)" }}>
          <div className="text-[13px] font-semibold" style={{ color: "var(--warn)" }}>{err}</div>
          <div className="text-[12px] mt-1" style={{ color: "var(--muted)" }}>
            شاخص‌های فروش از دیتابیس ربات می‌آیند. بقیه‌ی صفحه سالم است.
          </div>
        </div>
      )}

      {/* ── نمودار اصلی و ترکیب اشتراک‌ها ── */}
      {/* ستونِ کناری بلندتر از نمودار بود و زیرِ نمودار ۱۴۱ پیکسل
          فضای مرده می‌ماند. `fx-fill` یعنی این کارت تا قدِ ردیف کش
          بیاید — و چون محتوایش نمودار است، آن فضا به خودِ نمودار
          می‌رسد، نه به یک حفره. */}
      <div className="fx-g2 grid gap-3">
        <div className="fx-card fx-fill p-5">
          <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
            <div>
              <h2 className="text-[15px] font-bold text-white">روند فروش</h2>
              <p className="text-[12px] mt-1" style={{ color: "var(--muted)" }}>
{faNum(days)} روز گذشته · {faNum(o.approved ?? 0)} سفارش
              </p>
            </div>
            <Segmented value={days} onChange={setDays}
              items={[{ v: 7, l: "۷ روز" }, { v: 30, l: "۳۰ روز" }, { v: 90, l: "۹۰ روز" }]} />
          </div>

          {busy ? <Skeleton h={150} /> : orderSeries.length < 2 ? (
            <EmptyState icon={TrendingUp} text="هنوز فروشی در این بازه ثبت نشده"
              hint="با اولین سفارش موفق، روند این‌جا کشیده می‌شود." />
          ) : (
            /* هر دو سری روی یک محور — نه دو نمودار زیر هم. کارت
               نصف ارتفاع می‌گیرد و «فروش بالا رفت ولی تعداد سفارش
               نه» در یک نگاه دیده می‌شود. */
            <AreaChart
              data={moneySeries} color="var(--accent-2)" height={168}
              label="درآمد روزانه" format={(v) => `${faNum(v)} تومان`}
              data2={orderSeries} color2="var(--cy)" label2="تعداد سفارش"
              format2={(v) => `${faNum(v)} سفارش`} labels={daily.map((d) => d.day)} />
          )}
        </div>

        <div className="flex flex-col gap-3">
          <div className="fx-card p-5">
            <h3 className="text-[14px] font-bold text-white mb-1">وضعیت اشتراک‌ها</h3>
            <p className="text-[12px] mb-4" style={{ color: "var(--muted)" }}>
              {faNum(s.total ?? 0)} اشتراک در کل
            </p>
            {busy ? <Skeleton h={120} /> : (s.total ? (
              <Donut center="فعال" items={[
                { n: "فعال", v: s.active || 0, c: "var(--ok)" },
                { n: "نزدیک انقضا", v: s.expiringSoon || 0, c: "var(--warn)" },
                { n: "منقضی", v: Math.max(0, (s.total || 0) - (s.active || 0)), c: "#3E4C63" },
              ]} />
            ) : (
              <p className="text-[12px] py-6 text-center" style={{ color: "var(--muted)" }}>
                هنوز اشتراکی ساخته نشده
              </p>
            ))}
          </div>

          <div className="fx-card p-5">
            <div className="flex items-center justify-between gap-2 mb-4">
              <h3 className="text-[14px] font-bold text-white">بیشترین خرید</h3>
              <button onClick={() => navigate("bot-users")}
                className="fx-btn-g px-2.5 py-1.5 text-[12px] flex items-center gap-1">
                همه <ChevronLeft size={12} />
              </button>
            </div>
            {busy ? <Skeleton h={100} /> : (rep?.buyers || []).length ? (
              <BarList color="linear-gradient(to left,var(--accent-2),var(--accent))"
                format={(v) => faNum(v)}
                items={(rep.buyers || []).slice(0, 5).map((b) => ({
                  n: b.first_name || b.username || `#${b.tg_id}`,
                  v: Number(b.spent) || 0,
                }))} />
            ) : (
              <p className="text-[12px] py-5 text-center" style={{ color: "var(--muted)" }}>
                در این بازه کسی خرید نکرده
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ── ردیفِ پایین: بدهیِ نماینده‌ها و خودِ صفحه‌ی اشتراک ──

          تا ۱.۱۲۳ این‌جا چهار کارت بود (~۷۸۰ پیکسل):
          - «محتوای صفحه» با چهار کاشیِ عدد؛
          - «قابلیت‌های روشن» با چهار ردیف؛
          - «بدهیِ نماینده‌ها»؛
          - «دسترسی سریع»: چهار پیوند که سایدبار و Ctrl K همان‌ها را دارند.
          محتوا و قابلیت‌ها هر دو «صفحه‌ی مشتری چه دارد» را جواب می‌دادند و
          حالا یک فهرستِ هشت‌ردیفی‌اند. دسترسیِ سریع برداشته شد، چون تکرار بود. */}
      {/* هم‌قد نمی‌شوند (نه `fx-g2-rows`): فهرستِ هشت‌ردیفی بلندتر است و کشیدنِ
          کارتِ بدهی تا قدِ آن، زیرِ چهار ردیفش یک حفره می‌ساخت */}
      {/* ستونِ پهن فهرست است (دو زیرستونِ چهارتایی) و ستونِ کناری بدهی‌ها.
          برعکسش — بدهیِ سه‌ردیفی در ستونِ پهن کنارِ فهرستِ هشت‌ردیفی — زیرِ
          کارتِ بدهی ~۲۵۰ پیکسل جای خالی می‌گذاشت (عکسِ مالک، ۱.۱۲۷). */}
      <div className="fx-g2 grid gap-3 items-start">
        <div className="fx-card p-5 min-w-0">
          <h3 className="text-[14px] font-bold text-white">صفحه‌ی اشتراکِ مشتری</h3>
          <p className="text-[12px] mt-1 mb-2" style={{ color: "var(--muted)" }}>
            چیزی که مشتری روی صفحه‌اش می‌بیند
          </p>
          <div className="ov-list ov-2col">
            {content.map((c) => (
              <button key={c.key} onClick={() => navigate(c.key)} className="ov-row" title="رفتن به این بخش">
                <c.icon size={14} aria-hidden="true" />
                <span className="ov-l">{c.label}</span>
                <span className="ov-sub">{c.sub}</span>
                <b>{faNum(c.value)}</b>
                <ChevronLeft size={13} className="ov-go" aria-hidden="true" />
              </button>
            ))}
            {features.map((x) => (
              <button key={x.l} onClick={() => navigate(x.k)} className="ov-row" title="رفتن به این بخش">
                <Activity size={14} aria-hidden="true" />
                <span className="ov-l">{x.l}</span>
                <span className="ov-sub" />
                <span className="fx-pill" style={{
                  background: x.on ? "var(--ok-soft)" : "var(--hair-1)",
                  color: x.on ? "var(--ok)" : "var(--muted)" }}>
                  {x.on ? "فعال" : "خاموش"}
                </span>
                <ChevronLeft size={13} className="ov-go" aria-hidden="true" />
              </button>
            ))}
          </div>
        </div>
        <BillingMini data={billShown} onGo={() => navigate("bill-dash")} />
      </div>
    </div>
  );
}

export function PhonePreview({ config, os }) {
  const list = config.downloadApps?.[os] || [];
  const rec = list.find((a) => a.recommended);
  const others = list.filter((a) => !a.recommended);
  const osLabel = OS_TABS.find((t) => t.key === os)?.label;

  return (
    <div className="fx-hide-m">
      <div className="sticky top-24">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--muted)" }}><Eye size={13} /> پیش‌نمایش زنده</div>
          <span className="text-[12px] px-2 py-0.5 rounded-full" style={{ background: "rgba(43,127,214,.12)", color: "var(--accent-2)" }}>{osLabel}</span>
        </div>
        <div className="mx-auto rounded-[2.2rem] p-2.5" style={{ width: 250, background: "linear-gradient(160deg,#1a2130,#0a0e17)", border: "1px solid rgba(255,255,255,.12)", boxShadow: "0 24px 70px rgba(0,0,0,.55)" }}>
          <div className="flex items-center justify-center mb-1.5"><div className="w-14 h-1 rounded-full" style={{ background: "rgba(255,255,255,.15)" }} /></div>
          <div className="rounded-[1.7rem] overflow-hidden" style={{ background: "var(--bg)", minHeight: 380 }}>
            <div className="flex items-center justify-between px-4 pt-3 pb-1 text-[10px]" style={{ color: "var(--muted)" }}>
              <span style={{ fontFamily: "var(--mono)" }}>۱۰:۳۰</span>
              <div className="flex items-center gap-1"><span className="w-1 h-1 rounded-full" style={{ background: "var(--ok)" }} /><span>Nexora</span></div>
            </div>
            <div className="px-3.5 pb-4">
              <div className="text-[12px] font-bold text-white text-center my-3">دانلود برنامه‌ها</div>
              <div className="rounded-lg px-2.5 py-2 mb-3 flex items-start gap-1.5" style={{ background: "rgba(43,127,214,.1)", border: "1px solid rgba(43,127,214,.3)" }}>
                <Star size={9} className="shrink-0 mt-0.5" style={{ color: "var(--accent-2)" }} fill="var(--accent-2)" />
                <div className="text-[10.5px] leading-relaxed" style={{ color: "var(--accent-2)" }}>پیشنهاد ما: <b>{rec?.name || "—"}</b></div>
              </div>
              {[rec, ...others].filter(Boolean).map((app, i) => {
                const Icon = SCHEME_ICON[app.scheme] || Package;
                return (
                  <div key={i} className="rounded-xl p-3 mb-2 relative" style={{ background: "var(--surface)", border: app.recommended ? "1px solid rgba(90,169,230,.45)" : "1px solid var(--border)" }}>
                    {app.recommended && <div className="absolute -top-2 right-3 text-[9px] px-2 py-0.5 rounded-full" style={{ background: "linear-gradient(135deg,#2B7FD6,#5AA9E6)", color: "#06090F", fontWeight: 700 }}>پیشنهادی</div>}
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="min-w-0">
                        <div className="text-[12px] font-bold text-white truncate">{app.name}</div>
                        <div className="text-[10px]" style={{ color: "var(--muted)" }}>کلاینت رسمی</div>
                      </div>
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: app.recommended ? "linear-gradient(135deg,#2B7FD6,#8FC1EE)" : "rgba(255,255,255,.05)" }}>
                        <Icon size={14} color={app.recommended ? "#06090F" : "#5A6880"} />
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      {app.scheme !== "none" && <div className="text-[10px] text-center py-1.5 rounded-lg font-bold" style={{ background: "linear-gradient(135deg,#2B7FD6,#5AA9E6)", color: "#06090F" }}>افزودن با یک کلیک</div>}
                      <div className="text-[9.5px] text-center py-1 rounded-lg" style={{ border: "1px solid var(--border-2)", color: "var(--muted)" }}>دانلود اپ</div>
                    </div>
                  </div>
                );
              })}
              {list.length === 0 && <div className="text-[11px] text-center py-12" style={{ color: "#2A3444" }}>هیچ اپی اضافه نشده</div>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AppsSection({ config, setConfig, requestDelete }) {
  const [osTab, setOsTab] = useState("android");
  const list = config.downloadApps?.[osTab] || [];
  const counts = Object.fromEntries(OS_TABS.map((t) => [t.key, config.downloadApps?.[t.key]?.length || 0]));

  const updateApp = (i, patch) => {
    const l = [...list]; l[i] = { ...l[i], ...patch };
    setConfig({ ...config, downloadApps: { ...(config.downloadApps || {}), [osTab]: l } });
  };
  const setRec = (i) => {
    const l = list.map((a, j) => ({ ...a, recommended: j === i }));
    setConfig({ ...config, downloadApps: { ...(config.downloadApps || {}), [osTab]: l } });
  };
  const addApp = () => setConfig({ ...config, downloadApps: { ...(config.downloadApps || {}), [osTab]: [...list, { id: `app-${Date.now()}`, name: "اپ جدید", url: "", recommended: list.length === 0, scheme: "none" }] } });

  return (
    <div className="fx-g2 grid gap-6 fx-anim" style={{ gridTemplateColumns: "1fr 280px" }}>
      <div className="min-w-0">
        <SectionHead title="اپلیکیشن‌های دانلود" desc="برای هر پلتفرم، اپ‌های قابل‌دانلود و اپ پیشنهادی را مدیریت کنید." />
        <Tabs items={OS_TABS} active={osTab} onChange={setOsTab} counts={counts} />
        <div className="flex flex-col gap-3">
          {list.length === 0 && <EmptyState icon={Smartphone} text="هنوز اپی برای این پلتفرم اضافه نشده"
            hint="مشتری در صفحه‌ی اشتراک هیچ دکمه‌ی نصبی نمی‌بیند تا اینجا حداقل یک اپ اضافه کنید." />}
          {list.map((app, i) => {
            const Icon = SCHEME_ICON[app.scheme] || Package;
            return (
              <div key={app.id || i} className={`fx-card p-4 ${app.recommended ? "fx-card-hl" : ""}`}>
                <div className="flex items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="fx-ico" style={{ background: app.recommended ? "linear-gradient(135deg,#2B7FD6,#8FC1EE)" : "rgba(255,255,255,.05)" }}>
                      <Icon size={16} color={app.recommended ? "#06090F" : "#5A6880"} />
                    </div>
                    <button title="پیشنهادی کن" onClick={() => setRec(i)} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-[10px] text-[13px] font-semibold transition-all"
                      style={app.recommended ? { color: "#06090F", background: "linear-gradient(135deg,#2B7FD6,#5AA9E6)" } : { color: "var(--muted)", background: "rgba(255,255,255,.05)" }}>
                      <Star size={11} fill={app.recommended ? "#06090F" : "none"} /> {app.recommended ? "پیشنهادی" : "انتخاب به‌عنوان پیشنهادی"}
                    </button>
                  </div>
                  <button title="حذف این اپلیکیشن" onClick={() => requestDelete({ type: "app", os: osTab, idx: i, name: app.name })} className="fx-ico-btn shrink-0"><Trash2 size={15} /></button>
                </div>
                <div className="fx-g3 grid grid-cols-2 gap-3">
                  <Field label="نام اپ"><input className="fx-input" value={app.name} onChange={(e) => updateApp(i, { name: e.target.value })} /></Field>
                  <Field label="نوع افزودن یک‌کلیک">
                    <select className="fx-input" value={app.scheme} onChange={(e) => updateApp(i, { scheme: e.target.value })}>
                      {SCHEME_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                    </select>
                  </Field>
                </div>
                <Field label="لینک دانلود"><input className="fx-input" dir="ltr" value={app.url} onChange={(e) => updateApp(i, { url: e.target.value })} placeholder="https://..." /></Field>
              </div>
            );
          })}
          <button onClick={addApp} className="fx-btn-dash flex items-center justify-center gap-2 py-3.5 text-[14px]">
            <Plus size={15} /> افزودن اپ جدید به {OS_TABS.find((t) => t.key === osTab)?.label}
          </button>
        </div>
      </div>
      <PhonePreview config={config} os={osTab} />
    </div>
  );
}

export function VideosSection({ config, setConfig, requestDelete }) {
  const videos = config.videos || [];
  const update = (i, patch) => { const l = [...videos]; l[i] = { ...l[i], ...patch }; setConfig({ ...config, videos: l }); };
  const add = () => setConfig({ ...config, videos: [...videos, { id: `vid-${Date.now()}`, title: "آموزش جدید", telegramUrl: "", platform: "all" }] });

  const incomplete = videos.filter((v) => !v.telegramUrl || !v.telegramUrl.trim()).length;

  return (
    <div className="fx-anim">
      <SectionHead title="ویدیوهای آموزشی" desc="ویدیوها را در کانال تلگرام خود آپلود کنید و فقط لینک پیام را اینجا بگذارید — هیچ حجمی از سرور مصرف نمی‌شود." />

      {incomplete > 0 && (
        <div className="mb-4">
          <InfoBox tone="warn">
            <b>{incomplete} ویدیو بدون لینک است</b> و در صفحه‌ی مشتری نمایش داده نمی‌شود.
            برای هر ویدیو حتماً لینک تلگرام را وارد کنید.
          </InfoBox>
        </div>
      )}

      <div className="mb-4">
        <InfoBox>
          <b>چطور لینک بگیرم؟</b> ویدیو را در کانال تلگرام‌تان بفرستید، روی پیام لمس طولانی کنید و «Copy Link» را بزنید. لینکی شبیه <span dir="ltr" style={{ fontFamily: "var(--mono)" }}>t.me/your_channel/42</span> می‌گیرید.
          <br /><span style={{ color: "var(--warn)" }}>توجه:</span> لینک Saved Messages شخصی برای مشتری‌ها باز نمی‌شود — حتماً از کانال عمومی استفاده کنید.
        </InfoBox>
      </div>
      <div className="flex flex-col gap-3">
        {videos.length === 0 && <EmptyState icon={Video} text="هنوز ویدیویی اضافه نشده"
          hint="ویدیوی آموزش نصب، بیشترین سؤال پشتیبانی را کم می‌کند." />}
        {videos.map((v, i) => (
          <div key={v.id || i} className="fx-card p-4">
            <div className="flex items-center justify-between gap-2 mb-3">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="fx-ico" style={{ background: "rgba(43,127,214,.12)" }}><PlayCircle size={16} style={{ color: "var(--accent-2)" }} /></div>
                <span className="text-[14px] font-semibold text-white truncate">{v.title || "بدون عنوان"}</span>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {v.telegramUrl && <a href={v.telegramUrl} target="_blank" rel="noreferrer" className="fx-ico-btn" style={{ color: "var(--accent-2)" }}><ExternalLink size={14} /></a>}
                <button title="حذف این ویدیو" onClick={() => requestDelete({ type: "video", idx: i, name: v.title })} className="fx-ico-btn"><Trash2 size={15} /></button>
              </div>
            </div>
            <div className="fx-g3 grid grid-cols-2 gap-3">
              <Field label="عنوان ویدیو"><input className="fx-input" value={v.title} onChange={(e) => update(i, { title: e.target.value })} placeholder="آموزش نصب Happ در اندروید" /></Field>
              <Field label="مربوط به پلتفرم">
                <select className="fx-input" value={v.platform} onChange={(e) => update(i, { platform: e.target.value })}>
                  <option value="all">همه پلتفرم‌ها</option>
                  {OS_TABS.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
              </Field>
            </div>
            <Field label="لینک پیام تلگرام" hint="مثال: https://t.me/your_channel/42">
              <input className="fx-input" dir="ltr" value={v.telegramUrl} onChange={(e) => update(i, { telegramUrl: e.target.value })} placeholder="https://t.me/..." />
            </Field>
          </div>
        ))}
        <button onClick={add} className="fx-btn-dash flex items-center justify-center gap-2 py-3.5 text-[14px]"><Plus size={15} /> افزودن ویدیوی آموزشی</button>
      </div>
    </div>
  );
}

export function FaqSection({ config, setConfig, requestDelete }) {
  const [lang, setLang] = useState("fa");
  const list = config.faq?.[lang] || [];
  const counts = Object.fromEntries(LANG_TABS.map((t) => [t.key, config.faq?.[t.key]?.length || 0]));
  const update = (i, patch) => { const l = [...list]; l[i] = { ...l[i], ...patch }; setConfig({ ...config, faq: { ...(config.faq || {}), [lang]: l } }); };
  const add = () => setConfig({ ...config, faq: { ...(config.faq || {}), [lang]: [...list, { q: "", a: "" }] } });

  return (
    <div className="fx-anim">
      <SectionHead title="سوالات متداول" desc="این سوال‌ها به‌صورت آکاردئون در پایین صفحه‌ی اشتراک نمایش داده می‌شوند." />
      <Tabs items={LANG_TABS} active={lang} onChange={setLang} counts={counts} />
      {list.length === 0 && <EmptyState icon={HelpCircle} text="هنوز سوالی برای این زبان اضافه نشده"
        hint="سوال‌های متداول در همان صفحه جواب می‌دهند و بار پشتیبانی را کم می‌کنند." />}
      {/* دو ستون: هر سوال یک کادر کوتاه است و تمام‌عرض‌بودنش فقط
          فضای خالی می‌ساخت — سه سوال، ۸۱۰ پیکسل ارتفاع. */}
      <div className="fx-g2-even grid gap-3">
        {list.map((item, i) => (
          <div key={i} className="fx-card p-4">
            <div className="flex items-start justify-between mb-2.5">
              <span className="fx-pill" style={{ background: "rgba(255,255,255,.04)", color: "var(--muted)" }}>سوال {i + 1}</span>
              <button title="حذف این سوال" onClick={() => requestDelete({ type: "faq", lang, idx: i, name: item.q || "این سوال" })} className="fx-ico-btn"><Trash2 size={14} /></button>
            </div>
            <Field label="متن سوال"><input className="fx-input" value={item.q} onChange={(e) => update(i, { q: e.target.value })} /></Field>
            <Field label="متن پاسخ"><textarea className="fx-input" value={item.a} onChange={(e) => update(i, { a: e.target.value })} rows={2} /></Field>
          </div>
        ))}
      </div>
      <button onClick={add} className="fx-btn-dash w-full flex items-center justify-center gap-2 py-3.5 text-[14px]"><Plus size={15} /> افزودن سوال جدید</button>
    </div>
  );
}

export function BannersSection({ config, setConfig }) {
  const b = config.banners || {};
  const update = (patch) => setConfig({ ...config, banners: { ...b, ...patch } });
  const [tab, setTab] = useState("thresholds");

  const TABS_B = [
    { key: "thresholds", label: "آستانه‌ها", icon: Sliders },
    { key: "disabled", label: "متن بنر قطعی", icon: AlertTriangle },
    { key: "lowquota", label: "متن بنر اتمام", icon: Clock },
  ];

  return (
    <div className="fx-anim">
      <SectionHead title="بنرهای هشدار" desc="بنرهایی که بالای داشبورد صفحه‌ی اشتراک، بسته به شرایط، خودکار ظاهر می‌شوند." />

      <div className="fx-card p-5 mb-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="fx-ico" style={{ background: "rgba(43,127,214,.12)" }}><Bell size={16} style={{ color: "var(--accent-2)" }} /></div>
            <div className="min-w-0">
              <div className="text-[14px] font-semibold text-white">فعال‌سازی کلی بنرها</div>
              <div className="text-[13px] mt-0.5" style={{ color: "var(--muted)" }}>اگر خاموش کنید، هیچ بنری نمایش داده نمی‌شود</div>
            </div>
          </div>
          <Toggle checked={b.enabled !== false} onChange={() => update({ enabled: !(b.enabled !== false) })} label="بنرها" />
        </div>
      </div>

      <div style={{ opacity: b.enabled !== false ? 1 : 0.45, pointerEvents: b.enabled !== false ? "auto" : "none" }}>
        <Tabs items={TABS_B} active={tab} onChange={setTab} />

        {tab === "thresholds" && (
          <div className="fx-g3 grid grid-cols-2 gap-4 fx-fade">
            <div className="fx-card p-5">
              <div className="flex items-center gap-2 mb-4"><Clock size={14} style={{ color: "var(--warn)" }} /><span className="text-[14px] font-semibold text-white">هشدار پایان زمان</span></div>
              <NumberStepper value={b.lowQuotaDaysThreshold ?? 3} onChange={(v) => update({ lowQuotaDaysThreshold: v })} min={1} max={30} unit="روز" />
              <p className="text-[12px] mt-3 leading-relaxed" style={{ color: "#475569" }}>
                از <b style={{ color: "var(--warn)" }}>{faNum(b.lowQuotaDaysThreshold ?? 3)} روز</b> مانده به انقضا، بنر نمایش داده می‌شود.
              </p>
            </div>
            <div className="fx-card p-5">
              <div className="flex items-center gap-2 mb-4"><Package size={14} style={{ color: "var(--warn)" }} /><span className="text-[14px] font-semibold text-white">هشدار پایان حجم</span></div>
              <NumberStepper value={b.lowQuotaPercentThreshold ?? 15} onChange={(v) => update({ lowQuotaPercentThreshold: v })} min={1} max={50} unit="درصد" />
              <p className="text-[12px] mt-3 leading-relaxed" style={{ color: "#475569" }}>
                وقتی کمتر از <b style={{ color: "var(--warn)" }}>{faNum(b.lowQuotaPercentThreshold ?? 15)}٪</b> حجم باقی باشد، بنر ظاهر می‌شود.
              </p>
            </div>
          </div>
        )}

        {tab === "disabled" && (
          <div className="fx-g2 grid gap-5 fx-fade" style={{ gridTemplateColumns: "1fr 280px" }}>
            <div className="fx-card p-5">
              <div className="text-[14px] font-semibold text-white mb-1">بنر «کانفیگ غیرفعال است»</div>
              <p className="text-[13px] mb-4 leading-relaxed" style={{ color: "var(--muted)" }}>
                وقتی کانفیگ مشتری غیرفعال شده باشد (مثلاً به‌خاطر تخطی از محدودیت IP) این بنر نمایش داده می‌شود.
              </p>
              <Field label="عنوان" hint="خالی بگذارید تا متن پیش‌فرض استفاده شود">
                <input className="fx-input" value={b.disabledTitle || ""} onChange={(e) => update({ disabledTitle: e.target.value })} placeholder="این کانفیگ غیرفعال است" />
              </Field>
              <Field label="متن توضیحات">
                <textarea className="fx-input" rows={3} value={b.disabledDesc || ""} onChange={(e) => update({ disabledDesc: e.target.value })}
                  placeholder="این اتفاق معمولاً به‌خاطر استفاده‌ی هم‌زمان از چند دستگاه می‌افتد..." />
              </Field>
              <Field label="متن دکمه">
                <input className="fx-input" value={b.disabledButtonText || ""} onChange={(e) => update({ disabledButtonText: e.target.value })} placeholder="تماس با پشتیبانی" />
              </Field>
            </div>
            <div className="fx-hide-m">
              <div className="sticky top-24">
                <div className="flex items-center gap-1.5 text-[13px] mb-3" style={{ color: "var(--muted)" }}><Eye size={13} /> پیش‌نمایش</div>
                <div className="rounded-2xl p-4" style={{ background: "rgba(248,113,113,.08)", border: "1px solid rgba(248,113,113,.3)" }}>
                  <div className="flex items-start gap-2.5">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: "rgba(248,113,113,.18)" }}>
                      <AlertTriangle size={14} style={{ color: "var(--danger)" }} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-[13px] font-bold text-white mb-1">{b.disabledTitle || "این کانفیگ غیرفعال است"}</div>
                      <div className="text-[12px] leading-relaxed mb-2.5" style={{ color: "var(--dim)" }}>
                        {b.disabledDesc || "این اتفاق معمولاً به‌خاطر استفاده‌ی هم‌زمان از چند دستگاه می‌افتد."}
                      </div>
                      <div className="inline-block text-[12px] font-bold px-2.5 py-1.5 rounded-lg" style={{ background: "var(--danger)", color: "#1a0505" }}>
                        {b.disabledButtonText || "تماس با پشتیبانی"}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {tab === "lowquota" && (
          <div className="fx-g2 grid gap-5 fx-fade" style={{ gridTemplateColumns: "1fr 280px" }}>
            <div className="fx-card p-5">
              <div className="text-[14px] font-semibold text-white mb-1">بنر «اشتراک رو به اتمام»</div>
              <p className="text-[13px] mb-4 leading-relaxed" style={{ color: "var(--muted)" }}>
                وقتی حجم یا زمان اشتراک مشتری به آستانه‌ی تعیین‌شده برسد، این بنر نمایش داده می‌شود.
              </p>
              <Field label="عنوان">
                <input className="fx-input" value={b.lowQuotaTitle || ""} onChange={(e) => update({ lowQuotaTitle: e.target.value })} placeholder="اشتراک شما رو به اتمام است" />
              </Field>
              <Field label="متن هشدار پایان زمان" hint="از {days} برای نمایش تعداد روز باقی‌مانده استفاده کنید">
                <textarea className="fx-input" rows={2} value={b.lowQuotaDescDays || ""} onChange={(e) => update({ lowQuotaDescDays: e.target.value })}
                  placeholder="فقط {days} روز از اشتراک شما باقی مانده. همین حالا تمدید کنید." />
              </Field>
              <Field label="متن هشدار پایان حجم">
                <textarea className="fx-input" rows={2} value={b.lowQuotaDescVolume || ""} onChange={(e) => update({ lowQuotaDescVolume: e.target.value })}
                  placeholder="حجم اشتراک شما رو به اتمام است. همین حالا تمدید کنید." />
              </Field>
              <Field label="عنوان بنر منقضی‌شده">
                <input className="fx-input" value={b.expiredTitle || ""} onChange={(e) => update({ expiredTitle: e.target.value })} placeholder="اشتراک شما منقضی شده" />
              </Field>
              <Field label="متن بنر منقضی‌شده" hint="وقتی زمان اشتراک تمام شده — نه رو به اتمام">
                <textarea className="fx-input" rows={2} value={b.lowQuotaDescExpired || ""} onChange={(e) => update({ lowQuotaDescExpired: e.target.value })}
                  placeholder="اشتراک شما به پایان رسیده و اتصال شما قطع است. برای وصل‌شدن دوباره، تمدید کنید." />
              </Field>
              <div className="fx-g3 grid grid-cols-2 gap-3">
                <Field label="متن دکمه">
                  <input className="fx-input" value={b.lowQuotaButtonText || ""} onChange={(e) => update({ lowQuotaButtonText: e.target.value })} placeholder="تمدید اشتراک" />
                </Field>
                <Field label="لینک دکمه" hint="خالی = لینک پشتیبانی">
                  <input className="fx-input" dir="ltr" value={b.lowQuotaButtonUrl || ""} onChange={(e) => update({ lowQuotaButtonUrl: e.target.value })} placeholder="https://t.me/..." />
                </Field>
              </div>
            </div>
            <div className="fx-hide-m">
              <div className="sticky top-24">
                <div className="flex items-center gap-1.5 text-[13px] mb-3" style={{ color: "var(--muted)" }}><Eye size={13} /> پیش‌نمایش</div>
                <div className="rounded-2xl p-4" style={{ background: "rgba(251,191,36,.08)", border: "1px solid rgba(251,191,36,.3)" }}>
                  <div className="flex items-start gap-2.5">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: "rgba(251,191,36,.18)" }}>
                      <Clock size={14} style={{ color: "var(--warn)" }} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-[13px] font-bold text-white mb-1">{b.lowQuotaTitle || "اشتراک شما رو به اتمام است"}</div>
                      <div className="text-[12px] leading-relaxed mb-2.5" style={{ color: "var(--dim)" }}>
                        {(b.lowQuotaDescDays || "فقط {days} روز از اشتراک شما باقی مانده.").replace("{days}", String(b.lowQuotaDaysThreshold ?? 3))}
                      </div>
                      <div className="inline-block text-[12px] font-bold px-2.5 py-1.5 rounded-lg" style={{ background: "var(--warn)", color: "#2a1c02" }}>
                        {b.lowQuotaButtonText || "تمدید اشتراک"}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function ReferralSection({ config, setConfig }) {
  const r = config.referral || { enabled: true };
  return (
    <div className="fx-anim">
      <SectionHead title="سیستم رفرال" desc="کارت معرفی به دوستان که در داشبورد صفحه‌ی اشتراک نمایش داده می‌شود." />
      <div className="fx-card p-5 mb-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="fx-ico" style={{ background: "var(--accent-soft)" }}><Gift size={16} style={{ color: "var(--accent-2)" }} /></div>
            <div className="min-w-0">
              <div className="text-[14px] font-semibold text-white">نمایش کارت رفرال</div>
              <div className="text-[13px] mt-0.5" style={{ color: "var(--muted)" }}>اگر خاموش کنید، کارت معرفی نمایش داده نمی‌شود</div>
            </div>
          </div>
          <Toggle checked={r.enabled} onChange={() => setConfig({ ...config, referral: { ...r, enabled: !r.enabled } })} label="رفرال" />
        </div>
      </div>
      {/* متنِ قبلی می‌گفت پاداشِ خودکار «باید در ربات پیاده‌سازی شود» —
          در حالی که ربات از خیلی قبل «سکه و دعوت» را داشت. مدیر را به
          ساختنِ چیزی می‌فرستاد که وجود داشت، و نمی‌گفت این کارت چه می‌کند. */}
      <InfoBox tone="warn">
        این کارت دوستِ مشتری را با پیامِ آماده‌ی «فلانی معرفیم کرده» (با نامِ کاربریِ معرف) به <b>پشتیبانی</b> می‌فرستد؛
        پس پاداشِ معرفی‌هایی که از این‌جا می‌آیند را <b>دستی</b> می‌دهید. پاداشِ خودکارِ دعوت در خودِ ربات است —
        بخشِ <b>ربات تلگرام ← سکه و دعوت</b>.
      </InfoBox>
    </div>
  );
}

export function LinksSection({ config, setConfig }) {
  const l = config.links;
  const update = (patch) => setConfig({ ...config, links: { ...l, ...patch } });
  return (
    <div className="fx-anim">
      <SectionHead title="لینک‌های ارتباطی" desc="آدرس‌های پشتیبانی و کانال که در سراسر صفحه‌ی اشتراک استفاده می‌شوند." />
      <div className="fx-card p-5">
        <div className="text-[14px] font-semibold text-white mb-4 flex items-center gap-2"><MessageCircle size={15} style={{ color: "var(--accent-2)" }} /> پشتیبانی و کانال</div>
        <div className="fx-g3 grid grid-cols-2 gap-4">
          <Field label="یوزرنیم تلگرام پشتیبانی" hint="بدون @ وارد کنید">
            <input className="fx-input" dir="ltr" value={l.supportUsername} onChange={(e) => update({ supportUsername: e.target.value })} placeholder="your_support" />
          </Field>
          <Field label="یوزرنیم کانال" hint="بدون @ وارد کنید">
            <input className="fx-input" dir="ltr" value={l.channelUsername} onChange={(e) => update({ channelUsername: e.target.value })} placeholder="your_channel" />
          </Field>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <a href={`https://t.me/${l.supportUsername}`} target="_blank" rel="noreferrer" className="text-[13px] px-3 py-1.5 rounded-lg flex items-center gap-1.5" style={{ background: "rgba(43,127,214,.1)", color: "var(--accent-2)" }}>
            <ExternalLink size={11} /> تست لینک پشتیبانی
          </a>
          <a href={`https://t.me/${l.channelUsername}`} target="_blank" rel="noreferrer" className="text-[13px] px-3 py-1.5 rounded-lg flex items-center gap-1.5" style={{ background: "rgba(43,127,214,.1)", color: "var(--accent-2)" }}>
            <ExternalLink size={11} /> تست لینک کانال
          </a>
        </div>
      </div>
    </div>
  );
}


/**
 * لوگوی برندِ خودِ مالک.
 *
 * چرا این‌جا و نه کنار نماینده‌ها: فهرستِ نماینده‌ها
 * `WHERE parent_id IS NOT NULL` است، پس خودِ مالک هیچ‌وقت در آن
 * نیست. قابلیت ساخته شده بود ولی صاحبِ پنل به آن نمی‌رسید — یعنی
 * عملاً وجود نداشت.
 *
 * همین لوگو در نوار کناری پنل، در مینی‌اپ، و در صفحه‌ی اشتراک
 * می‌نشیند.
 */
function BrandLogo({ password }) {
  const ref = React.useRef(null);
  const [info, setInfo] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");

  const load = React.useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/api/admin/brand/logo`,
        { headers: { "X-Admin-Password": password } });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errText(j.detail, "خوانده نشد"));
      setInfo(j);
    } catch (e) { setErr(e.message); }
  }, [password]);

  React.useEffect(() => { load(); }, [load]);

  const send = async (body, method) => {
    if (!info?.id) return;
    setBusy(true); setErr("");
    try {
      const r = await fetch(`${API_URL}/api/admin/tenant/${info.id}/logo`, {
        method,
        headers: { "Content-Type": "application/json",
                   "X-Admin-Password": password },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errText(j.detail, "آپلود نشد"));
      await load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  const pick = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > 512 * 1024) { setErr("حجم فایل بیشتر از ۵۱۲ کیلوبایت است"); return; }
    const data = await new Promise((res, rej) => {
      const rd = new FileReader();
      rd.onload = () => res(String(rd.result || ""));
      rd.onerror = () => rej(new Error("فایل خوانده نشد"));
      rd.readAsDataURL(f);
    }).catch((e2) => { setErr(e2.message); return null; });
    if (data) send({ data }, "POST");
  };

  return (
    <div className="flex items-center gap-4 flex-wrap">
      <div className="shrink-0">
        {info?.logo
          ? <img src={info.logo} alt="لوگو" className="nx-logo"
              style={{ width: 64, height: 64, border: "1px solid var(--border)" }} />
          : <NexoraMark size={64} />}
      </div>
      <div className="min-w-0 flex-1" style={{ minWidth: 200 }}>
        <div className="text-[13px] mb-1.5" style={{ color: "var(--dim)" }}>
          لوگوی برند شما
        </div>
        <div className="text-[12px] mb-2.5 leading-relaxed"
          style={{ color: "var(--muted)" }}>
          در نوار کناری پنل، مینی‌اپ تلگرام و صفحه‌ی اشتراک مشتری
          نشان داده می‌شود. PNG، JPEG یا WebP — حداکثر ۵۱۲ کیلوبایت.
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => ref.current?.click()} disabled={busy || !info}
            className="fx-btn px-3 py-2 text-[13px] flex items-center gap-1.5">
            {busy ? <Loader2 size={13} className="animate-spin" />
                  : <Upload size={13} />}
            {info?.logo ? "تغییر لوگو" : "آپلود لوگو"}
          </button>
          {info?.logo && (
            <button onClick={() => send(null, "DELETE")} disabled={busy}
              className="fx-btn-g px-3 py-2 text-[13px] flex items-center gap-1.5">
              <Trash2 size={13} /> برداشتن
            </button>
          )}
        </div>
        {err && (
          <p className="text-[12px] mt-2 flex items-start gap-1.5"
            style={{ color: "var(--danger)" }}>
            <AlertTriangle size={12} className="shrink-0 mt-0.5" />{err}
          </p>
        )}
      </div>
      <input ref={ref} type="file" accept="image/png,image/jpeg,image/webp"
        onChange={pick} className="hidden" />
    </div>
  );
}

/**
 * تاریخچه‌ی تنظیمات و برگشت به عقب.
 *
 * چرا هست: تا امروز تنظیمات در یک فایل JSON بود که با هر ذخیره
 * بازنویسی می‌شد. یک تغییرِ اشتباه — یا فایلی که نصفه نوشته شده
 * بود — یعنی راهِ برگشتی وجود نداشت.
 *
 * حالا هر ذخیره نسخه‌ی قبلی را نگه می‌دارد و از همین‌جا برمی‌گردد.
 */
function ConfigHistory({ password, onRestored }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(0);

  const load = async () => {
    setErr("");
    try {
      const r = await fetch(`${API_URL}/api/admin/config/history`,
        { headers: { "X-Admin-Password": password } });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errText(j.detail, "تاریخچه خوانده نشد"));
      setData(j);
    } catch (e) { setErr(e.message); setData({ versions: [] }); }
  };

  useEffect(() => { load(); }, [password]);   // eslint-disable-line

  const back = async (v) => {
    setBusy(v); setErr("");
    try {
      const r = await fetch(`${API_URL}/api/admin/config/rollback/${v}`,
        { method: "POST", headers: { "X-Admin-Password": password } });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errText(j.detail, "برگرداندن ناموفق بود"));
      onRestored?.(j.config, j.version);
      await load();
    } catch (e) { setErr(e.message); } finally { setBusy(0); }
  };

  const rows = data?.versions || [];

  return (
    <div className="fx-card p-5 mt-5">
      <SectionHead icon={Clock} title="تاریخچه تنظیمات"
        desc="هر ذخیره، نسخه‌ی قبلی را نگه می‌دارد. اگر چیزی را اشتباه عوض کردید، از همین‌جا برگردید."
        action={
          <button onClick={load}
            className="fx-btn-g px-3 py-2 text-[13px] flex items-center gap-1.5">
            <Activity size={13} /> تازه‌سازی
          </button>
        } />

      {err && (
        <p className="text-[13px] mb-3 flex items-start gap-1.5"
          style={{ color: "var(--danger)" }}>
          <AlertTriangle size={13} className="shrink-0 mt-0.5" />{err}
        </p>
      )}

      {!data ? (
        <Skeleton h={90} />
      ) : !rows.length ? (
        <EmptyState icon={Clock} text="هنوز نسخه‌ی قبلی‌ای نیست"
          hint="بعد از اولین ذخیره، نسخه‌ی پیشین این‌جا می‌ماند." />
      ) : (
        <div className="fx-rows">
          {rows.map((v) => (
            <div key={v.version} className="fx-row-kv">
              <span className="flex items-center gap-2 min-w-0">
                <b style={{ fontFamily: "var(--mono)" }} dir="ltr">#{faNum(v.version)}</b>
                <i className="not-italic text-[12px] truncate"
                  style={{ color: "var(--muted)" }}>{isoToJalaliStamp(v.at)}</i>
              </span>
              <button className="fx-btn-g px-3 py-1.5 text-[12.5px] flex items-center gap-1.5"
                disabled={busy === v.version} onClick={() => back(v.version)}>
                {busy === v.version
                  ? <Loader2 size={12} className="animate-spin" />
                  : <ChevronLeft size={12} />}
                بازگرداندن
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


export function SettingsSection({ config, setConfig, password, onPasswordChanged, onRestored, wsMode, setWsMode }) {
  const a = config.advanced || {};
  const update = (patch) => setConfig({ ...config, advanced: { ...a, ...patch } });
  // دو زبانه، نه دو گروهِ زیرِ هم در یک صفحه‌ی ۲۳۶۸ پیکسلی: «ظاهرِ صفحه‌ی
  // مشتری» و «پنلِ خودتان» دو مخاطبِ متفاوت دارند و هیچ‌وقت با هم ویرایش
  // نمی‌شوند. تغییرها در `config` می‌مانند، پس زبانه چیزی را گم نمی‌کند.
  const [tab, setTab] = useState("page");
  const vis = [
    { key: "showBrandStrip", label: "نوار برند بالای صفحه", desc: "لوگو و نام برند" },
    { key: "showReferralCard", label: "کارت رفرال", desc: "معرفی به دوستان در داشبورد" },
    { key: "showFaqSection", label: "بخش سوالات متداول", desc: "آکاردئون سوالات در پایین صفحه" },
    { key: "showNotificationPopup", label: "پاپ‌آپ راهنما", desc: "تنظیمات کامل در بخش «پاپ‌آپ راهنما»" },
    { key: "allowThemeToggle", label: "دکمه تغییر تم", desc: "اجازه‌ی سوییچ بین حالت تیره و روشن" },
    { key: "allowLanguageToggle", label: "دکمه تغییر زبان", desc: "اجازه‌ی انتخاب زبان توسط مشتری" },
  ];

  return (
    <div className="fx-anim">
      <SectionHead title="تنظیمات پیشرفته" desc="کنترل کامل روی ظاهر، رفتار و جزئیات صفحه‌ی اشتراک." />

      {/* دو گروه، هر کدام شبکه‌ی دوستونی.
          قبلاً ده کارت در یک ستونِ ۳۳۶۰ پیکسلی بود و «ظاهرِ صفحه‌ی
          مشتری» با «رمزِ پنل» و «بک‌آپ» قاطی بود — مالک: «هر چیزی که فضا را
          شلوغ کرده». ستون‌های CSS (نه grid): کارت‌های ناهم‌قد بی‌حفره
          کنارِ هم می‌نشینند. */}
      <Tabs active={tab} onChange={setTab} items={[
        { key: "page", label: "ظاهرِ صفحه‌ی اشتراک" },
        { key: "panel", label: "پنل، رمز و پشتیبان" },
      ]} />

      {tab === "page" && <>
      <div className="fx-set-group">
        <span>روی صفحه‌ی همه‌ی مشتری‌ها اثر می‌گذارد — بعد از ذخیره، یک‌بار خودتان بازش کنید</span>
      </div>
      <div className="fx-set-cols">
      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-4 flex items-center gap-2"><Type size={15} style={{ color: "var(--accent-2)" }} /> هویت برند</div>

        <div className="rounded-xl p-4 mb-4"
          style={{ background: "var(--surface-3)", border: "1px solid var(--border)" }}>
          <BrandLogo password={password} />
        </div>

        <div className="fx-g3 grid grid-cols-2 gap-4">
          <Field label="نام برند"><input className="fx-input" value={a.brandName || ""} onChange={(e) => update({ brandName: e.target.value })} placeholder="NEXORA" /></Field>
          <Field label="عنوان صفحه (تب مرورگر)"><input className="fx-input" value={a.pageTitle || ""} onChange={(e) => update({ pageTitle: e.target.value })} /></Field>
        </div>
      </div>

      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-4 flex items-center gap-2"><Palette size={15} style={{ color: "var(--accent-2)" }} /> رنگ‌بندی</div>
        <div className="fx-g3 grid grid-cols-2 gap-4">
          <Field label="رنگ اصلی برند">
            <div className="flex items-center gap-2">
              <input type="color" value={a.accentColor || "#2B7FD6"} onChange={(e) => update({ accentColor: e.target.value })}
                className="w-11 h-11 rounded-xl cursor-pointer shrink-0" style={{ background: "transparent", border: "1px solid var(--border-2)" }} />
              <input className="fx-input" dir="ltr" value={a.accentColor || ""} onChange={(e) => update({ accentColor: e.target.value })} />
            </div>
          </Field>
          <Field label="رنگ ثانویه (گرادینت)">
            <div className="flex items-center gap-2">
              <input type="color" value={a.accentColor2 || "#5AA9E6"} onChange={(e) => update({ accentColor2: e.target.value })}
                className="w-11 h-11 rounded-xl cursor-pointer shrink-0" style={{ background: "transparent", border: "1px solid var(--border-2)" }} />
              <input className="fx-input" dir="ltr" value={a.accentColor2 || ""} onChange={(e) => update({ accentColor2: e.target.value })} />
            </div>
          </Field>
        </div>
        <div className="mt-2 rounded-xl p-3 text-center" style={{ background: `linear-gradient(135deg, ${a.accentColor || "#2B7FD6"}, ${a.accentColor2 || "#5AA9E6"})` }}>
          <span className="text-[13px] font-bold" style={{ color: "#06090F" }}>پیش‌نمایش گرادینت برند</span>
        </div>
      </div>

      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2"><Eye size={15} style={{ color: "var(--accent-2)" }} /> نمایش بخش‌ها</div>
        <p className="text-[13px] mb-4" style={{ color: "var(--muted)" }}>هر بخشی را که نمی‌خواهید در صفحه‌ی مشتری دیده شود، خاموش کنید.</p>
        <div className="flex flex-col">
          {vis.map((v, i) => (
            <div key={v.key} className="flex items-center justify-between gap-3 py-3" style={{ borderBottom: i < vis.length - 1 ? "1px solid var(--border)" : "none" }}>
              <div className="min-w-0">
                <div className="text-[14px] text-white">{v.label}</div>
                <div className="text-[12px] mt-0.5" style={{ color: "var(--muted)" }}>{v.desc}</div>
              </div>
              <Toggle checked={a[v.key] !== false} onChange={() => update({ [v.key]: !(a[v.key] !== false) })} label={v.label} />
            </div>
          ))}
        </div>
      </div>

      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-4 flex items-center gap-2"><Globe size={15} style={{ color: "var(--accent-2)" }} /> پیش‌فرض‌های صفحه</div>
        <div className="fx-g3 grid grid-cols-2 gap-4">
          <Field label="زبان پیش‌فرض">
            <select className="fx-input" value={a.defaultLanguage || "fa"} onChange={(e) => update({ defaultLanguage: e.target.value })}>
              {LANG_TABS.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
            </select>
          </Field>
          <Field label="تم پیش‌فرض">
            <select className="fx-input" value={a.defaultTheme || "dark"} onChange={(e) => update({ defaultTheme: e.target.value })}>
              <option value="dark">تیره</option><option value="light">روشن</option>
            </select>
          </Field>
        </div>
        <Field label="تاخیر نمایش پاپ‌آپ راهنما">
          <NumberStepper value={a.notificationDelaySeconds ?? 10} onChange={(v) => update({ notificationDelaySeconds: v })} min={0} max={60} unit="ثانیه" />
        </Field>
      </div>

      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2"><ShieldCheck size={15} style={{ color: "var(--accent-2)" }} /> امنیت و حریم خصوصی</div>
        <p className="text-[13px] mb-4" style={{ color: "var(--muted)" }}>کنترل چیزی که مشتری می‌تواند ببیند یا کپی کند.</p>
        <div className="flex items-center justify-between gap-3 py-3">
          <div className="min-w-0">
            <div className="text-[14px] text-white">مخفی‌کردن لیست کانفیگ‌ها</div>
            <div className="text-[12px] mt-0.5 leading-relaxed" style={{ color: "var(--muted)" }}>
              دکمه‌ی «کپی کانفیگ» حذف می‌شود تا مشتری نتواند کانفیگ خام را کپی و با دیگران به اشتراک بگذارد. لینک اشتراک همچنان کار می‌کند.
            </div>
          </div>
          <Toggle checked={a.hideConfigsList === true} onChange={() => update({ hideConfigsList: !a.hideConfigsList })} label="مخفی‌کردن کانفیگ‌ها" />
        </div>
      </div>

      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-4 flex items-center gap-2"><Sliders size={15} style={{ color: "var(--accent-2)" }} /> سفارشی‌سازی پیشرفته</div>
        <Field label="متن پاورقی سفارشی" hint="اگر خالی بگذارید، چیزی نمایش داده نمی‌شود.">
          <input className="fx-input" value={a.customFooterText || ""} onChange={(e) => update({ customFooterText: e.target.value })} placeholder="پشتیبانی ۲۴ ساعته" />
        </Field>
        <Field label="CSS سفارشی" hint="برای کاربران حرفه‌ای — مستقیم به صفحه‌ی اشتراک تزریق می‌شود.">
          <textarea className="fx-input" dir="ltr" rows={4} value={a.customCss || ""} onChange={(e) => update({ customCss: e.target.value })}
            placeholder=".my-class { color: red; }" style={{ fontFamily: "var(--mono)", fontSize: 11.5 }} />
        </Field>
      </div>

      </div>

      </>}

      {tab === "panel" && <>
      <div className="fx-set-group">
        <span>فقط برای شما — مشتری هیچ‌کدام را نمی‌بیند</span>
      </div>
      <PanelPathCard password={password} />
      {/* حالت سوییچ فضای کاری — سلیقه‌ای، فقط روی همین مرورگر */}
      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
          <LayoutGrid size={15} style={{ color: "var(--accent-2)" }} /> نمایش فضاهای کاری
        </div>
        <p className="text-[13px] mb-4 leading-relaxed" style={{ color: "var(--muted)" }}>
          چطور بین صفحه اشتراک، حسابداری و ربات جابه‌جا شوید. فقط روی همین مرورگر ذخیره می‌شود.
        </p>

        <div className="fx-g3 grid grid-cols-3 gap-3">
          {Object.entries(WS_MODES).map(([k, m]) => {
            const on = wsMode === k;
            return (
              <button title="انتخاب این حالت" key={k} onClick={() => setWsMode(k)}
                className="p-3.5 rounded-2xl text-right"
                style={{
                  background: on ? "var(--accent-soft)" : "var(--surface-3)",
                  border: `1px solid ${on ? "rgba(43,127,214,.45)" : "var(--border)"}`,
                  transition: "transform .28s cubic-bezier(.22,1,.36,1), box-shadow .28s, background .2s, border-color .2s",
                  transform: on ? "translateY(-2px)" : "none",
                  boxShadow: on
                    ? "0 1px 0 rgba(255,255,255,.1) inset, 0 14px 30px -14px rgba(43,127,214,.55)"
                    : "0 1px 0 rgba(255,255,255,.04) inset",
                }}>
                <WsModePreview mode={k} active={on} />
                <div className="flex items-center gap-1.5 mt-3">
                  {on && <Check size={12} style={{ color: "var(--accent-2)", flexShrink: 0 }} />}
                  <span className="text-[13px] font-bold"
                    style={{ color: on ? "var(--text)" : "var(--dim)" }}>{m.label}</span>
                </div>
                <div className="text-[12px] mt-1.5 leading-relaxed" style={{ color: "var(--muted)" }}>
                  {m.desc}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="fx-set-cols">
      <BackupCard password={password} onRestored={onRestored} />

      <ChangePasswordCard password={password} onPasswordChanged={onPasswordChanged} />

      </div>
      <ConfigHistory password={password} onRestored={onRestored} />
      </>}
    </div>
  );
}

export function ResellersSection({ config, setConfig, requestDelete, password }) {
  const resellers = config.resellers || [];
  const [expanded, setExpanded] = useState(null);
  const [tplOptions, setTplOptions] = useState([]);
  const [palOptions, setPalOptions] = useState([]);
  const [optErr, setOptErr] = useState("");

  // ساختارها و پالت‌ها برای انتخاب قالب اختصاصی هر واسطه
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/admin/themes`, { headers: { "X-Admin-Password": password } });
        const d = await okJson(res, "خواندنِ قالب‌ها ناموفق بود");
        setTplOptions(d.templates || []);
        setPalOptions([...(d.palettes || []), ...(d.customPalettes || [])]);
        setOptErr("");
      } catch (e) {
        // بی‌این، دو منوی «ساختار» و «طیف رنگی» فقط گزینه‌ی «همان
        // اصلی» را داشتند و کسی نمی‌فهمید چرا
        setOptErr(e.message);
      }
    })();
  }, [password]);

  const update = (i, patch) => {
    const l = [...resellers]; l[i] = { ...l[i], ...patch };
    setConfig({ ...config, resellers: l });
  };
  const updateOverride = (i, path, value) => {
    const l = [...resellers];
    const ov = { ...(l[i].overrides || {}) };
    ov[path[0]] = { ...(ov[path[0]] || {}), [path[1]]: value };
    l[i] = { ...l[i], overrides: ov };
    setConfig({ ...config, resellers: l });
  };
  const add = () => {
    const id = `reseller-${Date.now()}`;
    setConfig({
      ...config,
      resellers: [...resellers, {
        id, name: "واسطه جدید", enabled: true, emailPrefix: "", domains: [],
        overrides: {
          links: { supportUsername: "", channelUsername: "" },
          advanced: { brandName: "", pageTitle: "", accentColor: "#2B7FD6", accentColor2: "#5AA9E6" },
        },
      }],
    });
    setExpanded(resellers.length);
  };

  return (
    <div className="fx-anim">
      <SectionHead
        title="واسطه‌ها (فروش با برند اختصاصی)"
        desc="برای هر واسطه، برند و لینک‌های اختصاصی تعریف کنید — روی همین سرور، بدون نیاز به سرور یا پنل جدید."
      />

      <div className="mb-4">
        <InfoBox>
          <b>چطور کار می‌کند؟</b> صفحه‌ی اشتراک تشخیص می‌دهد مشتری متعلق به کدام واسطه است و برند همان واسطه را نمایش می‌دهد.
          هر چیزی که برای واسطه تعریف نکنید (مثل اپ‌های دانلود، سوالات متداول، بنرها) خودکار از تنظیمات اصلی شما به ارث می‌رسد.
          <br /><br />
          <b>دو روش تشخیص:</b>
          <br />
          ۱. <b>پیشوند ایمیل</b> — کافی است در پنل 3x-ui، ایمیل مشتریان آن واسطه را با پیشوند بسازید (مثلاً <span dir="ltr" style={{ fontFamily: "var(--mono)" }}>macan_ali@nexora</span>)
          <br />
          ۲. <b>دامنه اختصاصی</b> — واسطه یک دامنه می‌خرد و به IP همین سرور اشاره می‌دهد (کاملاً white-label)
        </InfoBox>
      </div>

      <div className="flex flex-col gap-3">
        {resellers.length === 0 && <EmptyState icon={Users} text="هنوز واسطه‌ای اضافه نشده"
          hint="واسطه یعنی کسی که با برند خودش می‌فروشد و شما فقط صورتحسابش را می‌گیرید." />}

        {resellers.map((r, i) => {
          const isOpen = expanded === i;
          const ov = r.overrides || {};
          const advOv = ov.advanced || {};
          const linksOv = ov.links || {};
          return (
            <div key={r.id || i} className={`fx-card ${r.enabled === false ? "" : ""}`} style={{ opacity: r.enabled === false ? 0.6 : 1 }}>
              {/* سربرگ */}
              <div className="flex items-center justify-between gap-2 p-4">
                <button onClick={() => setExpanded(isOpen ? null : i)} className="flex items-center gap-3 min-w-0 flex-1 text-right">
                  <div className="fx-ico" style={{ background: `linear-gradient(135deg, ${advOv.accentColor || "#2B7FD6"}, ${advOv.accentColor2 || "#5AA9E6"})` }}>
                    <span className="font-bold text-[16px]" style={{ color: "#06090F" }}>
                      {(advOv.brandName || r.name || "?").trim().charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <div className="text-[14px] font-semibold text-white truncate">{r.name || "بدون نام"}</div>
                    {/* پیچیدن، نه بریدن: پیشوند و دامنه همان چیزی است که مدیر
                        برای تشخیصِ واسطه لازم دارد و روی گوشی نصفش می‌رفت */}
                    <div className="text-[12px] mt-0.5 break-words" style={{ color: "var(--muted)" }}>
                      {r.emailPrefix ? `پیشوند: ${r.emailPrefix}_` : ""}
                      {r.emailPrefix && r.domains?.length ? " · " : ""}
                      {r.domains?.length ? r.domains.join(", ") : ""}
                      {!r.emailPrefix && !r.domains?.length ? "هنوز تنظیم نشده" : ""}
                    </div>
                  </div>
                </button>
                <div className="flex items-center gap-2 shrink-0">
                  <Toggle checked={r.enabled !== false} onChange={() => update(i, { enabled: !(r.enabled !== false) })} label="فعال" />
                  <button title="حذف این واسطه" onClick={() => requestDelete({ type: "reseller", idx: i, name: r.name })} className="fx-ico-btn"><Trash2 size={15} /></button>
                </div>
              </div>

              {/* بدنه */}
              {isOpen && (
                <div className="px-4 pb-4 fx-fade" style={{ borderTop: "1px solid var(--border)" }}>
                  <div className="pt-4">
                    <Field label="نام واسطه (فقط برای خودتان، به مشتری نمایش داده نمی‌شود)">
                      <input className="fx-input" value={r.name} onChange={(e) => update(i, { name: e.target.value })} placeholder="مثلاً: ماکان" />
                    </Field>

                    <div className="text-[13px] font-semibold text-white mt-4 mb-2.5 flex items-center gap-2">
                      <Search size={13} style={{ color: "var(--accent-2)" }} /> روش تشخیص مشتریان این واسطه
                    </div>

                    <div className="fx-g3 grid grid-cols-2 gap-3">
                      <Field label="پیشوند ایمیل" hint={r.emailPrefix ? `ایمیل مشتریان باید این‌طور باشد: ${r.emailPrefix}_نام@دامنه` : "مثلاً: macan"}>
                        <input className="fx-input" dir="ltr" value={r.emailPrefix || ""} onChange={(e) => update(i, { emailPrefix: e.target.value.trim() })} placeholder="macan" />
                      </Field>
                      <Field label="دامنه‌های اختصاصی" hint="با کاما جدا کنید. باید به IP همین سرور اشاره کنند.">
                        <input className="fx-input" dir="ltr" value={(r.domains || []).join(", ")}
                          onChange={(e) => update(i, { domains: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                          placeholder="macanvpn.ir" />
                      </Field>
                    </div>

                    <div className="text-[13px] font-semibold text-white mt-4 mb-2.5 flex items-center gap-2">
                      <Palette size={13} style={{ color: "var(--accent-2)" }} /> برند اختصاصی واسطه
                    </div>

                    <div className="fx-g3 grid grid-cols-2 gap-3">
                      <Field label="نام برند"><input className="fx-input" value={advOv.brandName || ""} onChange={(e) => updateOverride(i, ["advanced", "brandName"], e.target.value)} placeholder="MACAN" /></Field>
                      <Field label="عنوان صفحه"><input className="fx-input" value={advOv.pageTitle || ""} onChange={(e) => updateOverride(i, ["advanced", "pageTitle"], e.target.value)} placeholder="ماکان | اشتراک" /></Field>
                    </div>

                    <div className="fx-g3 grid grid-cols-2 gap-3">
                      <Field label="یوزرنیم پشتیبانی واسطه" hint="بدون @">
                        <input className="fx-input" dir="ltr" value={linksOv.supportUsername || ""} onChange={(e) => updateOverride(i, ["links", "supportUsername"], e.target.value)} placeholder="macan_support" />
                      </Field>
                      <Field label="یوزرنیم کانال واسطه" hint="بدون @">
                        <input className="fx-input" dir="ltr" value={linksOv.channelUsername || ""} onChange={(e) => updateOverride(i, ["links", "channelUsername"], e.target.value)} placeholder="macanvpn" />
                      </Field>
                    </div>

                    <div className="fx-g3 grid grid-cols-2 gap-3">
                      <Field label="رنگ اصلی">
                        <div className="flex items-center gap-2">
                          <input type="color" value={advOv.accentColor || "#2B7FD6"} onChange={(e) => updateOverride(i, ["advanced", "accentColor"], e.target.value)}
                            className="w-11 h-11 rounded-xl cursor-pointer shrink-0" style={{ background: "transparent", border: "1px solid var(--border-2)" }} />
                          <input className="fx-input" dir="ltr" value={advOv.accentColor || ""} onChange={(e) => updateOverride(i, ["advanced", "accentColor"], e.target.value)} />
                        </div>
                      </Field>
                      <Field label="رنگ ثانویه">
                        <div className="flex items-center gap-2">
                          <input type="color" value={advOv.accentColor2 || "#5AA9E6"} onChange={(e) => updateOverride(i, ["advanced", "accentColor2"], e.target.value)}
                            className="w-11 h-11 rounded-xl cursor-pointer shrink-0" style={{ background: "transparent", border: "1px solid var(--border-2)" }} />
                          <input className="fx-input" dir="ltr" value={advOv.accentColor2 || ""} onChange={(e) => updateOverride(i, ["advanced", "accentColor2"], e.target.value)} />
                        </div>
                      </Field>
                    </div>

                    <Field label="متن پاورقی اختصاصی (اختیاری)">
                      <input className="fx-input" value={advOv.customFooterText || ""} onChange={(e) => updateOverride(i, ["advanced", "customFooterText"], e.target.value)} placeholder="پشتیبانی ۲۴ ساعته ماکان" />
                    </Field>

                    <div className="text-[13px] font-semibold text-white mt-4 mb-2.5 flex items-center gap-2">
                      <Layers size={13} style={{ color: "var(--accent-2)" }} /> قالب اختصاصی
                    </div>
                    {optErr && <Msg msg={{ t: "err", m: `فهرستِ قالب‌ها خوانده نشد: ${optErr}` }} />}
                    <div className="fx-g3 grid grid-cols-2 gap-3">
                      <Field label="ساختار" hint="خالی = ساختار اصلی شما">
                        <select className="fx-input" value={r.overrides?.template || ""}
                          onChange={(e) => {
                            const l = [...resellers];
                            const ov = { ...(l[i].overrides || {}) };
                            if (e.target.value) ov.template = e.target.value; else delete ov.template;
                            l[i] = { ...l[i], overrides: ov };
                            setConfig({ ...config, resellers: l });
                          }}>
                          <option value="">— همان ساختار اصلی —</option>
                          {tplOptions.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.fa}</option>)}
                        </select>
                      </Field>

                      <Field label="طیف رنگی" hint="خالی = پالت اصلی شما">
                        <select className="fx-input" value={r.overrides?.palette || ""}
                          onChange={(e) => {
                            const l = [...resellers];
                            const ov = { ...(l[i].overrides || {}) };
                            if (e.target.value) ov.palette = e.target.value; else delete ov.palette;
                            l[i] = { ...l[i], overrides: ov };
                            setConfig({ ...config, resellers: l });
                          }}>
                          <option value="">— همان پالت اصلی —</option>
                          {palOptions.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.fa}</option>)}
                        </select>
                      </Field>
                    </div>

                    {(r.overrides?.template || r.overrides?.palette) && (() => {
                      const pv = palOptions.find((p) => p.id === (r.overrides?.palette))?.vars;
                      const tid = r.overrides?.template || config.template || "classic";
                      return (
                        <div className="flex items-center gap-3 rounded-xl p-3 mt-1"
                          style={{ background: "var(--surface-3)", border: "1px solid var(--border)" }}>
                          <div style={{ width: 96, flexShrink: 0 }}>
                            <TemplateThumb id={tid} vars={pv || {}} active />
                          </div>
                          <div className="text-[13px] leading-relaxed" style={{ color: "var(--muted)" }}>
                            ترکیب این واسطه:{" "}
                            <b style={{ color: "var(--text)" }}>
                              {tplOptions.find((t) => t.id === tid)?.name || tid}
                            </b>
                            {" × "}
                            <b style={{ color: pv?.accent2 || "var(--accent-2)" }}>
                              {palOptions.find((p) => p.id === r.overrides?.palette)?.name || "پالت اصلی"}
                            </b>
                          </div>
                        </div>
                      );
                    })()}

                    {/* تست زنده */}
                    {(r.emailPrefix || r.domains?.length > 0) && (
                      <div className="mt-3 rounded-xl p-3" style={{ background: "var(--surface-3)", border: "1px solid var(--border)" }}>
                        <div className="text-[13px] mb-2" style={{ color: "var(--muted)" }}>تست تشخیص این واسطه:</div>
                        <div className="flex flex-wrap gap-2">
                          {r.emailPrefix && (
                            <a href={`${API_URL}/api/public/config?email=${r.emailPrefix}_test@nexora`} target="_blank" rel="noreferrer"
                              className="text-[12px] px-2.5 py-1.5 rounded-lg flex items-center gap-1.5" style={{ background: "rgba(43,127,214,.1)", color: "var(--accent-2)" }}>
                              <ExternalLink size={10} /> تست با ایمیل
                            </a>
                          )}
                          {r.domains?.[0] && (
                            <a href={`${API_URL}/api/public/config?host=${r.domains[0]}`} target="_blank" rel="noreferrer"
                              className="text-[12px] px-2.5 py-1.5 rounded-lg flex items-center gap-1.5" style={{ background: "rgba(43,127,214,.1)", color: "var(--accent-2)" }}>
                              <ExternalLink size={10} /> تست با دامنه
                            </a>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        <button onClick={add} className="fx-btn-dash flex items-center justify-center gap-2 py-3.5 text-[14px]">
          <UserPlus size={15} /> افزودن واسطه جدید
        </button>
      </div>

      <div className="mt-4">
        <InfoBox tone="warn">
          <b>نکته‌ی مهم امنیتی:</b> لیست واسطه‌ها هرگز در پاسخ عمومی API فرستاده نمی‌شود — مشتری هیچ راهی برای دیدن این‌که چند واسطه دارید یا مشخصاتشان چیست ندارد.
        </InfoBox>
      </div>
    </div>
  );
}

export function BackupCard({ password, onRestored }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const exportConfig = async () => {
    setBusy(true); setMsg(null);
    try {
      const res = await fetch(`${API_URL}/api/admin/export`, { headers: { "X-Admin-Password": password } });
      if (!res.ok) throw new Error();
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `nexora-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      setMsg({ type: "ok", text: "فایل پشتیبان دانلود شد" });
    } catch {
      setMsg({ type: "error", text: "دریافت پشتیبان ناموفق بود" });
    } finally { setBusy(false); }
  };

  const importConfig = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!confirm("تنظیمات فعلی با محتوای این فایل جایگزین می‌شود. مطمئن هستید؟")) {
      e.target.value = ""; return;
    }
    setBusy(true); setMsg(null);
    // «فایل معتبر نیست» فقط برای فایل؛ پیش‌تر قطعیِ شبکه هم همین را می‌گفت
    let parsed;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      setMsg({ type: "error", text: "فایل معتبر نیست — JSONِ خوانا نبود" });
      setBusy(false); e.target.value = ""; return;
    }
    try {
      const res = await fetch(`${API_URL}/api/admin/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify(parsed),
      });
      const data = await okJson(res, "بازیابی ناموفق بود");
      // پیامِ بکند می‌گوید کدام بخش‌های تازه‌تر دست نخوردند
      setMsg({ type: "ok", text: data.message || "تنظیمات بازیابی شد" });
      onRestored();
    } catch (err) {
      setMsg({ type: "error", text: errMsg(err) });
    } finally { setBusy(false); e.target.value = ""; }
  };

  return (
    <div className="fx-card p-5 mb-4">
      <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
        <Download size={15} style={{ color: "var(--accent-2)" }} /> پشتیبان‌گیری و بازیابی
      </div>
      <p className="text-[13px] mb-4 leading-relaxed" style={{ color: "var(--muted)" }}>
        قبل از هر تغییر بزرگ، یک نسخه پشتیبان بگیرید. هنگام بازیابی، از نسخه‌ی فعلی خودکار یک کپی روی سرور نگه داشته می‌شود.
      </p>

      {msg && (
        <div className="rounded-xl p-3 mb-3 flex items-center gap-2 text-[13px]"
          style={{
            background: msg.type === "error" ? "rgba(248,113,113,.1)" : "rgba(52,211,153,.1)",
            border: `1px solid ${msg.type === "error" ? "rgba(248,113,113,.3)" : "rgba(52,211,153,.3)"}`,
            color: msg.type === "error" ? "var(--danger)" : "var(--ok)",
          }}>
          {msg.type === "error" ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />} {msg.text}
        </div>
      )}

      <div className="fx-g3 grid grid-cols-2 gap-3">
        <button onClick={exportConfig} disabled={busy} className="fx-btn-g flex items-center justify-center gap-2 py-3 text-[13px]">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} دریافت پشتیبان
        </button>
        <label className="fx-btn-g flex items-center justify-center gap-2 py-3 text-[13px] cursor-pointer">
          <Upload size={14} /> بازیابی از فایل
          <input type="file" accept="application/json" onChange={importConfig} className="hidden" disabled={busy} />
        </label>
      </div>
    </div>
  );
}

/**
 * نشانیِ مخفیِ پنل — دیدن، کپی و ساختنِ نشانیِ تازه.
 *
 * برگه: docs/specs/2026-09-28-admin-path-and-aff-payouts.md. نشانیِ تازه
 * نشانیِ قبلی را همان لحظه می‌بندد، پس بعد از ساخت خودمان به آن می‌رویم —
 * وگرنه صفحه‌ی باز با درخواستِ بعدی «پیدا نشد» می‌گرفت.
 */
export function PanelPathCard({ password }) {
  const [d, setD] = useState(null);
  const [msg, setMsg] = useState(null);
  const [ask, setAsk] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    fetch(`${API_URL}/api/admin/panel-path`, { headers: { "X-Admin-Password": password } })
      .then((r) => okJson(r, "نشانیِ پنل خوانده نشد")).then(setD)
      .catch((e) => setMsg({ t: "err", m: errMsg(e) }));
  }, [password]);
  const url = d ? (d.url || `${window.location.origin}/${d.path}/`) : "";
  const copy = () => {
    try { navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1600); }
    catch { setMsg({ t: "err", m: "کپی نشد — نشانی را دستی انتخاب کنید" }); }
  };
  const rotate = async () => {
    setAsk(false);
    try {
      const r = await fetch(`${API_URL}/api/admin/panel-path/rotate`,
        { method: "POST", headers: { "X-Admin-Password": password } });
      const j = await okJson(r, "نشانیِ تازه ساخته نشد");
      window.location.href = `/${j.path}/${window.location.hash || ""}`;
    } catch (e) { setMsg({ t: "err", m: errMsg(e) }); }
  };
  return (
    <div className="fx-card p-5 mb-4">
      <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
        <Key size={15} style={{ color: "var(--accent-2)" }} /> نشانیِ پنل
      </div>
      <p className="text-[12.5px] mb-3 leading-relaxed" style={{ color: "var(--muted)" }}>
        پنل فقط از این نشانی باز می‌شود؛ هر نشانیِ دیگری روی این دامنه «پیدا نشد» است. این را به
        نماینده‌ها و همکارها ندهید — آن‌ها نشانیِ خودشان را دارند. روی سرور هم با
        <code className="mx-1" dir="ltr">nexora url</code> دیده می‌شود.
      </p>
      <Msg msg={msg} />
      {d && (
        <div className="flex items-center gap-2 flex-wrap">
          <code className="fx-input flex-1 text-[12.5px] truncate" dir="ltr"
            style={{ fontFamily: "var(--mono)", minWidth: 220, userSelect: "all" }}>{url}</code>
          <button onClick={copy} className="fx-btn-g px-3 py-2 text-[12.5px] flex items-center gap-1.5">
            {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "کپی شد" : "کپی"}
          </button>
          <button onClick={() => setAsk(true)} className="fx-btn-g px-3 py-2 text-[12.5px]"
            style={{ color: "var(--warn)" }}>نشانیِ تازه</button>
        </div>
      )}
      {ask && (
        <ConfirmModal title="نشانیِ تازه برای پنل؟" confirmLabel="بساز و برو"
          desc="نشانیِ فعلی همین لحظه بسته می‌شود — نشانک‌ها و تب‌های باز روی نشانیِ قبلی «پیدا نشد» می‌گیرند. این صفحه خودش به نشانیِ تازه می‌رود."
          onCancel={() => setAsk(false)} onConfirm={rotate} />
      )}
    </div>
  );
}

export function ChangePasswordCard({ password, onPasswordChanged }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const strength = (() => {
    if (!next) return { level: 0, label: "", color: "var(--muted)" };
    let s = 0;
    if (next.length >= 8) s++;
    if (next.length >= 12) s++;
    if (/[A-Z]/.test(next) && /[a-z]/.test(next)) s++;
    if (/\d/.test(next)) s++;
    if (/[^A-Za-z0-9]/.test(next)) s++;
    const map = [
      { label: "خیلی ضعیف", color: "var(--danger)" },
      { label: "ضعیف", color: "var(--danger)" },
      { label: "متوسط", color: "var(--warn)" },
      { label: "خوب", color: "#84CC16" },
      { label: "قوی", color: "var(--ok)" },
      { label: "خیلی قوی", color: "var(--ok)" },
    ];
    return { level: s, ...map[s] };
  })();

  const submit = async () => {
    setMsg(null);
    if (next !== confirm) { setMsg({ type: "error", text: "رمز جدید و تکرار آن یکسان نیستند" }); return; }
    if (next.length < 8) { setMsg({ type: "error", text: "رمز جدید باید حداقل ۸ کاراکتر باشد" }); return; }

    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify({ currentPassword: current, newPassword: next }),
      });
      const data = await res.json();
      if (res.ok) {
        setMsg({ type: "ok", text: "رمز عبور با موفقیت تغییر کرد" });
        setCurrent(""); setNext(""); setConfirm("");
        onPasswordChanged(next);
      } else {
        setMsg({ type: "error", text: errText(data.detail, "تغییر رمز ناموفق بود") });
      }
    } catch {
      setMsg({ type: "error", text: "اتصال به سرور برقرار نشد" });
    } finally { setBusy(false); }
  };

  return (
    <div className="fx-card p-5 mb-4">
      <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
        <Key size={15} style={{ color: "var(--accent-2)" }} /> تغییر رمز عبور
      </div>
      <p className="text-[13px] mb-4" style={{ color: "var(--muted)" }}>
        رمز جدید بلافاصله فعال می‌شود و در فایل امن روی سرور ذخیره می‌گردد.
      </p>

      <Field label="رمز عبور فعلی">
        <input className="fx-input" type={show ? "text" : "password"} value={current}
          onChange={(e) => setCurrent(e.target.value)} dir="ltr"
          style={{ fontFamily: "var(--mono)" }} />
      </Field>

      <Field label="رمز عبور جدید" hint="حداقل ۸ کاراکتر — ترکیب حروف بزرگ/کوچک، عدد و علامت امن‌تر است">
        <input className="fx-input" type={show ? "text" : "password"} value={next}
          onChange={(e) => setNext(e.target.value)} dir="ltr"
          style={{ fontFamily: "var(--mono)" }} />
      </Field>

      {next && (
        <div className="mb-3 -mt-1">
          <div className="flex items-center gap-1.5 mb-1.5">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="h-1 flex-1 rounded-full transition-all"
                style={{ background: i < strength.level ? strength.color : "rgba(255,255,255,.07)" }} />
            ))}
          </div>
          <span className="text-[12px]" style={{ color: strength.color }}>قدرت رمز: {strength.label}</span>
        </div>
      )}

      <Field label="تکرار رمز جدید">
        <input className="fx-input" type={show ? "text" : "password"} value={confirm}
          onChange={(e) => setConfirm(e.target.value)} dir="ltr"
          style={{ fontFamily: "var(--mono)",
                   borderColor: confirm && next !== confirm ? "var(--danger)" : undefined }} />
      </Field>

      <label className="flex items-center gap-2 text-[13px] mb-4 cursor-pointer" style={{ color: "var(--dim)" }}>
        <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)}
          style={{ accentColor: "var(--accent)" }} />
        نمایش رمزها
      </label>

      {msg && (
        <div className="rounded-xl p-3 mb-3 flex items-center gap-2 text-[13px]"
          style={{
            background: msg.type === "error" ? "rgba(248,113,113,.1)" : "rgba(52,211,153,.1)",
            border: `1px solid ${msg.type === "error" ? "rgba(248,113,113,.3)" : "rgba(52,211,153,.3)"}`,
            color: msg.type === "error" ? "var(--danger)" : "var(--ok)",
          }}>
          {msg.type === "error" ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />} {msg.text}
        </div>
      )}

      <button title="ثبت رمز" onClick={submit} disabled={busy || !current || !next || !confirm}
        className="fx-btn w-full py-3 text-[14px] flex items-center justify-center gap-2">
        {busy ? <Loader2 size={15} className="animate-spin" /> : <Key size={15} />}
        {busy ? "در حال تغییر..." : "تغییر رمز عبور"}
      </button>
    </div>
  );
}

export function PopupSection({ config, setConfig }) {
  const p = config.popup || {};
  const update = (patch) => setConfig({ ...config, popup: { ...p, ...patch } });
  const EMOJIS = ["🔔", "💡", "⚠️", "🚀", "❓", "📱", "🎁", "⚡"];

  return (
    <div className="fx-g2 grid gap-6 fx-anim" style={{ gridTemplateColumns: "1fr 300px" }}>
      <div className="min-w-0">
        <SectionHead title="پاپ‌آپ راهنما" desc="پیامی که چند ثانیه بعد از باز شدن صفحه‌ی اشتراک به مشتری نمایش داده می‌شود." />

        <div className="fx-card p-5 mb-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="fx-ico" style={{ background: "rgba(43,127,214,.12)" }}><MessageSquare size={16} style={{ color: "var(--accent-2)" }} /></div>
              <div className="min-w-0">
                <div className="text-[14px] font-semibold text-white">نمایش پاپ‌آپ</div>
                <div className="text-[13px] mt-0.5" style={{ color: "var(--muted)" }}>اگر خاموش کنید، هیچ پاپ‌آپی نمایش داده نمی‌شود</div>
              </div>
            </div>
            <Toggle checked={p.enabled !== false} onChange={() => update({ enabled: !(p.enabled !== false) })} label="پاپ‌آپ" />
          </div>
        </div>

        <div style={{ opacity: p.enabled !== false ? 1 : 0.45, pointerEvents: p.enabled !== false ? "auto" : "none" }}>
          <div className="fx-card p-5 mb-4">
            <div className="text-[14px] font-semibold text-white mb-4">محتوای پیام</div>

            <Field label="آیکون">
              <div className="flex items-center gap-2 flex-wrap">
                {EMOJIS.map((e) => (
                  <button key={e} onClick={() => update({ icon: e })}
                    className="w-11 h-11 rounded-xl text-[21px] transition-all"
                    style={p.icon === e
                      ? { background: "var(--accent-soft)", border: "1px solid var(--accent)" }
                      : { background: "var(--surface-3)", border: "1px solid var(--border-2)" }}>
                    {e}
                  </button>
                ))}
                {/* ورودیِ ایموجیِ دلخواه — همان مقدارِ فعلی را نشان می‌دهد، پس
                    بی‌نشانه شبیهِ یک دکمه‌ی تکراری کنارِ فهرست بود */}
                <input className="fx-input" style={{ width: 88, textAlign: "center", fontSize: 17, borderStyle: "dashed" }}
                  value={p.icon || ""} onChange={(e) => update({ icon: e.target.value })} maxLength={4}
                  placeholder="دلخواه" title="یا یک ایموجیِ دلخواه بنویسید" aria-label="ایموجیِ دلخواه" />
              </div>
            </Field>

            <Field label="عنوان پیام">
              <input className="fx-input" value={p.title || ""} onChange={(e) => update({ title: e.target.value })}
                placeholder="آیا مشکلی در اتصال کانفیگ دارید؟" />
            </Field>

            <Field label="متن توضیحات">
              <textarea className="fx-input" rows={2} value={p.description || ""} onChange={(e) => update({ description: e.target.value })}
                placeholder="پیشنهاد می‌کنیم از برنامه‌ی Happ استفاده کنید..." />
            </Field>
          </div>

          <div className="fx-card p-5 mb-4">
            <div className="text-[14px] font-semibold text-white mb-4">دکمه‌ها</div>
            <div className="fx-g3 grid grid-cols-2 gap-3">
              <Field label="متن دکمه‌ی اصلی">
                <input className="fx-input" value={p.primaryButtonText || ""} onChange={(e) => update({ primaryButtonText: e.target.value })} placeholder="پشتیبانی" />
              </Field>
              <Field label="متن دکمه‌ی رد کردن">
                <input className="fx-input" value={p.dismissButtonText || ""} onChange={(e) => update({ dismissButtonText: e.target.value })} placeholder="خیر" />
              </Field>
            </div>
            <Field label="لینک دکمه‌ی اصلی" hint="اگر خالی بگذارید، خودکار به لینک پشتیبانی شما (یا واسطه) وصل می‌شود.">
              <input className="fx-input" dir="ltr" value={p.primaryButtonUrl || ""} onChange={(e) => update({ primaryButtonUrl: e.target.value })} placeholder="https://t.me/..." />
            </Field>
          </div>

          <div className="fx-card p-5">
            <div className="text-[14px] font-semibold text-white mb-4">زمان‌بندی</div>
            <div className="fx-g3 grid grid-cols-2 gap-4">
              <Field label="تاخیر تا نمایش" hint="چند ثانیه بعد از باز شدن صفحه ظاهر شود">
                <NumberStepper value={p.delaySeconds ?? 10} onChange={(v) => update({ delaySeconds: v })} min={0} max={60} unit="ثانیه" />
              </Field>
              <Field label="بسته شدن خودکار" hint="بعد از چند ثانیه خودش بسته شود">
                <NumberStepper value={p.autoCloseSeconds ?? 15} onChange={(v) => update({ autoCloseSeconds: v })} min={3} max={60} unit="ثانیه" />
              </Field>
            </div>
          </div>
        </div>
      </div>

      {/* پیش‌نمایش زنده پاپ‌آپ */}
      <div className="fx-hide-m">
        <div className="sticky top-24">
          <div className="flex items-center gap-1.5 text-[13px] mb-3" style={{ color: "var(--muted)" }}>
            <Eye size={13} /> پیش‌نمایش
          </div>
          <div className="rounded-2xl p-5" style={{ background: "var(--surface-3)", border: "1px solid var(--border-2)" }}>
            <div className="rounded-2xl p-5 text-center" style={{ background: "var(--surface)", border: "1px solid rgba(90,169,230,.3)", boxShadow: "0 8px 32px rgba(0,0,0,.4)" }}>
              <div className="text-[32px] mb-2">{p.icon || "🔔"}</div>
              <div className="text-[14px] font-bold text-white mb-2 leading-relaxed">{p.title || "آیا مشکلی در اتصال دارید؟"}</div>
              <div className="text-[13px] leading-relaxed mb-3" style={{ color: "var(--dim)" }}>{p.description || "متن توضیحات اینجا نمایش داده می‌شود"}</div>
              <div className="h-1 rounded-full mb-4 overflow-hidden" style={{ background: "rgba(255,255,255,.06)" }}>
                <div className="h-full rounded-full" style={{ width: "65%", background: "var(--accent-2)" }} />
              </div>
              <div className="flex gap-2">
                <div className="flex-1 py-2 rounded-lg text-[13px]" style={{ border: "1px solid var(--border-2)", color: "var(--muted)" }}>
                  {p.dismissButtonText || "خیر"}
                </div>
                <div className="flex-1 py-2 rounded-lg text-[13px] font-bold" style={{ background: "linear-gradient(135deg,var(--accent),var(--accent-2))", color: "#06090F" }}>
                  {p.primaryButtonText || "پشتیبانی"}
                </div>
              </div>
            </div>
          </div>
          <p className="text-[12px] mt-3 text-center leading-relaxed" style={{ color: "var(--muted)" }}>
            بعد از {faNum(p.delaySeconds ?? 10)} ثانیه ظاهر و بعد از {faNum(p.autoCloseSeconds ?? 15)} ثانیه بسته می‌شود
          </p>
        </div>
      </div>
    </div>
  );
}
