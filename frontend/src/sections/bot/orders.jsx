/**
 * ربات: سفارش‌ها و بررسی رسید.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle, CheckCircle2, CreditCard, Loader2, RefreshCw, Search, X,
} from "lucide-react";
import { errText, faNum } from "../../lib/format";
import { API_URL } from "../../lib/constants";
import { Avatar, EmptyState, Field, Msg, PageSkeleton, SectionHead, StatusPill, Tabs } from "../../ui/index";
import { isoToJalaliLabel, isoToJalaliStamp } from "../../ui/jalali";

export const REJECT_REASONS = [
  "مبلغ واریزی با مبلغ سفارش مطابقت ندارد.",
  "تصویر رسید خوانا نبود.",
  "این رسید قبلاً استفاده شده است.",
  "رسید معتبر تشخیص داده نشد.",
];

/* رسید با هدر، نه با رمز در آدرس.
   پیش‌تر `<img src=".../receipt/12?pw=رمز">` بود: رمزِ مدیر در لاگِ
   nginx، تاریخچه‌ی مرورگر و Referer می‌نشست — برای هر رسیدِ صفحه. حالا
   تصویر با fetch و هدر گرفته و از blob نشان داده می‌شود؛ بکند دیگر
   `?pw=` را نمی‌پذیرد. شکست هم دیده می‌شود، نه اینکه تصویر بی‌صدا
   پنهان شود. */
export function ReceiptImg({ id, password, style, alt = "رسید" }) {
  const [src, setSrc] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let url = null;
    let alive = true;
    setSrc(null); setErr(null);
    fetch(`${API_URL}/api/admin/bot/receipt/${id}`, { headers: { "X-Admin-Password": password } })
      .then(async (r) => {
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          throw new Error(errText(j.detail, "رسید باز نشد"));
        }
        return r.blob();
      })
      .then((b) => { if (!alive) return; url = URL.createObjectURL(b); setSrc(url); })
      .catch((e) => { if (alive) setErr(e.message || "رسید باز نشد"); });
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [id, password]);
  if (err) {
    return (
      <span className="grid place-items-center text-center text-[10.5px] p-1.5 leading-snug"
        style={{ ...style, color: "var(--danger)" }} title={err}>
        <AlertTriangle size={14} />{err}
      </span>
    );
  }
  if (!src) return <span className="fx-sk block" style={style} />;
  return <img src={src} alt={alt} style={style} />;
}

const KIND_LABEL = { new: "خرید", renew: "تمدید", topup: "شارژ کیف پول" };

export function BotOrdersSection({ password }) {
  const [rejecting, setRejecting] = useState(null);
  const [reason, setReason] = useState("");
  const [orders, setOrders] = useState([]);
  const [filter, setFilter] = useState("awaiting");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(null);
  const [zoom, setZoom] = useState(null);

  const load = async (f = filter) => {
    setLoading(true);
    try {
      const r = await fetch(`${API_URL}/api/admin/bot/orders?status=${f}`, { headers: { "X-Admin-Password": password } });
      const d = await r.json().catch(() => ({}));
      // خطا پیش‌تر به «رسیدی در انتظار تایید نیست» ختم می‌شد — صفِ
      // خالی و صفِ خوانده‌نشده یک شکل بودند
      if (!r.ok) { setMsg({ t: "err", m: errText(d.detail, "خواندنِ سفارش‌ها ناموفق بود") }); return; }
      if (d.error) setMsg({ t: "err", m: `خواندنِ سفارش‌ها ناقص ماند: ${d.error}` });
      else if (d.dbReady === false) setMsg({ t: "err", m: "دیتابیسِ ربات پیدا نشد — ربات نصب و اجرا شده؟" });
      setOrders(d.orders || []);
    } catch { setMsg({ t: "err", m: "اتصال برقرار نشد" }); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(filter); }, [password, filter]);
  useEffect(() => { if (msg) { const x = setTimeout(() => setMsg(null), 4000); return () => clearTimeout(x); } }, [msg]);

  const doReject = async () => {
    if (!reason.trim()) return;
    const id = rejecting.id;
    setRejecting(null);
    setBusy(id);
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/orders/${id}/reject-with-reason`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify({ reason }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        setMsg({ t: "ok", m: "سفارش رد شد — دلیل برای مشتری فرستاده می‌شود" });
        load(filter);
      } else setMsg({ t: "err", m: errText(d.detail, "عملیات ناموفق") });
    } catch { setMsg({ t: "err", m: "اتصال برقرار نشد" }); }
    finally { setBusy(null); }
  };

  const act = async (id, action) => {
    setBusy(id);
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/orders/${id}/${action}`, {
        method: "POST", headers: { "X-Admin-Password": password },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        setMsg({ t: "ok", m: action === "approve" ? "تایید شد — ربات کانفیگ را می‌سازد" : "سفارش رد شد" });
        load(filter);
      } else setMsg({ t: "err", m: errText(d.detail, "عملیات ناموفق") });
    } catch { setMsg({ t: "err", m: "اتصال برقرار نشد" }); }
    finally { setBusy(null); }
  };

  const FILTERS = [
    { k: "awaiting", l: "در انتظار تایید" },
    { k: "approved", l: "تاییدشده" },
    { k: "rejected", l: "ردشده" },
    { k: "all", l: "همه" },
  ];

  // از همان آرایه‌ای که در دست است — نه یک درخواست تازه
  const sumAmount = orders.reduce((a, o) => a + (Number(o.amount) || 0), 0);
  const waiting = orders.filter((o) => (o.status || "") === "pending"
                                    || (o.status || "") === "awaiting").length;
  const newest = orders.reduce((m, o) =>
    (o.created_at && (!m || o.created_at > m)) ? o.created_at : m, "");

  return (
    <div className="fx-anim">
      <SectionHead title="سفارش‌ها و رسیدها"
        desc="رسیدهای پرداخت کارت‌به‌کارت. تایید هم از اینجا و هم از گروه تلگرام ممکن است."
        action={
          <button onClick={() => load(filter)} className="fx-btn-g px-3 py-2.5 text-[13px] flex items-center gap-1.5">
            <RefreshCw size={13} /> تازه‌سازی
          </button>
        } />

      <Msg msg={msg} />

      {/* فیلتر و خلاصه در یک ردیف.
          تا ۱.۱۲۲ خلاصه سه کارتِ شاخصِ ۱۴۲ پیکسلی بود و زبانه‌ها ردیفِ
          جدای خودشان را داشتند؛ اولین رسید در y≈۳۲۰ شروع می‌شد. همان سه
          عدد حالا کنارِ زبانه‌هاست — از همان آرایه، بی‌درخواستِ تازه. */}
      <div className="ord-bar">
        <Tabs items={FILTERS.map(f => ({ key: f.k, label: f.l }))} active={filter} onChange={setFilter} />
        {!loading && orders.length > 0 && (
          <div className="ord-sum" aria-live="polite">
            <span><b>{faNum(orders.length)}</b> سفارش</span>
            <span><b style={{ color: "var(--ok)" }}>{faNum(sumAmount)}</b> تومان</span>
            {newest && <span>تازه‌ترین: {isoToJalaliLabel(newest)}</span>}
            {waiting > 0 && filter !== "awaiting" && (
              <span style={{ color: "var(--warn)" }}>{faNum(waiting)} در انتظار</span>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <PageSkeleton />
      ) : orders.length === 0 ? (
        <EmptyState icon={CreditCard}
          text={filter === "awaiting" ? "رسیدی در انتظار تایید نیست" : "موردی یافت نشد"}
          hint={filter === "awaiting"
            ? "هر رسیدی که مشتری بفرستد همین‌جا می‌آید — و از گروه تلگرام هم می‌شود تاییدش کرد."
            : "فیلتر بالا را عوض کنید تا سفارش‌های دیگر را ببینید."} />
      ) : (
        /* صف، نه شبکه‌ی کارت: هر سفارش یک ردیفِ ~۷۶ پیکسلی — رسید، کیست،
           چه خریده، چقدر، و دو دکمه کنارِ همان ردیف. کارت‌های قبلی
           ۲۱۰ تا ۳۰۰ پیکسل بودند و دکمه‌ی تایید تمامِ عرضِ کارت را
           می‌گرفت؛ در یک صفحه فقط چهار رسید دیده می‌شد. */
        <div className="fx-card ord-list">{orders.map((o) => (
        <div key={o.id} className={`ord-row st-${o.status || "none"}`}>
          {o.receipt_type === "photo" ? (
            <button onClick={() => setZoom(o.id)} className="ord-thumb"
              title="بزرگ‌نماییِ رسید" aria-label={`بزرگ‌نماییِ رسیدِ سفارش ${o.id}`}>
              <ReceiptImg id={o.id} password={password}
                style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              <span className="ord-zoom"><Search size={11} /></span>
            </button>
          ) : (
            <span className="ord-thumb ord-thumb-none" aria-hidden="true">
              <Avatar name={o.first_name || o.username} id={o.tg_id} size={30} />
            </span>
          )}

          <div className="ord-main">
            <div className="ord-l1">
              <span className="ord-name">{o.first_name || "بدون نام"}</span>
              {o.username && <span className="ord-user" dir="ltr">@{o.username}</span>}
              <StatusPill s={o.status} />
              <span className="fx-pill" style={{ background: "var(--accent-soft)", color: "var(--accent-2)" }}>
                {KIND_LABEL[o.kind] || "سفارش"}
              </span>
              {o.plan_name && <span className="ord-plan">{o.plan_name}</span>}
              {o.paid_from === "wallet" && (
                <span className="fx-pill" style={{ background: "var(--hair-2)", color: "var(--muted)" }}>از کیف پول</span>
              )}
            </div>
            <div className="ord-l2">
              <span><b>{faNum(Number(o.amount || 0))}</b> تومان</span>
              {o.coins_used > 0 && <span>{faNum(o.coins_used)} سکه · {faNum(o.discount_pct || 0)}٪ تخفیف</span>}
              <span>#{faNum(o.id)}</span>
              <span>{isoToJalaliStamp(o.created_at)}</span>
            </div>
            {o.receipt_type === "text" && o.receipt_text && (
              /* متنِ رسید دو خط، و با کلیک کامل — نه یک جعبه‌ی ۱۳۰ پیکسلی
                 که قدِ هر ردیف را سه برابر می‌کرد */
              <button className="ord-text" dir="auto" title="نمایشِ کاملِ متنِ رسید"
                onClick={(e) => e.currentTarget.classList.toggle("open")}>
                {o.receipt_text}
              </button>
            )}
          </div>

          {(o.status === "awaiting" || o.status === "review") && (
            <div className="ord-act">
              <button onClick={() => act(o.id, "approve")} disabled={busy === o.id}
                className="ord-ok" aria-label={`تاییدِ سفارشِ ${o.id}`}>
                {busy === o.id ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} تایید
              </button>
              <button onClick={() => { setRejecting(o); setReason(""); }} disabled={busy === o.id}
                className="fx-btn-g ord-no" aria-label={`ردِ سفارشِ ${o.id}`}>
                رد با دلیل
              </button>
            </div>
          )}
        </div>
        ))}</div>
      )}

      {zoom && createPortal(
        <div onClick={() => setZoom(null)}
          className="fixed inset-0 z-[110] flex items-center justify-center p-6"
          style={{ background: "var(--veil)", cursor: "zoom-out" }}>
          <span onClick={(e) => e.stopPropagation()}>
            <ReceiptImg id={zoom} password={password}
              style={{ maxWidth: "92vw", maxHeight: "88vh", minWidth: 120, minHeight: 120, borderRadius: 14, objectFit: "contain" }} />
          </span>
          <button title="بستن" onClick={() => setZoom(null)}
            className="absolute top-5 left-5 fx-ico-btn" style={{ width: 38, height: 38 }}>
            <X size={18} />
          </button>
        </div>, document.body)}

      {rejecting && createPortal(
        <div className="nx-modal-wrap fx-fade"
          style={{ background: "var(--veil)", backdropFilter: "blur(6px)" }}
          onClick={() => setRejecting(null)}>
          <div className="w-full max-w-md rounded-2xl fx-scale nx-modal flex flex-col"
            onClick={(e) => e.stopPropagation()}
            style={{ background: "var(--surface)", border: "1px solid var(--danger-line)" }}>

            <div className="p-5 shrink-0" style={{ borderBottom: "1px solid var(--border)" }}>
              <div className="flex items-center gap-2">
                <AlertTriangle size={16} style={{ color: "var(--danger)" }} />
                <span className="text-[16px] font-bold text-white">رد سفارش #{rejecting.id}</span>
              </div>
              <p className="text-[13px] mt-2 leading-relaxed" style={{ color: "var(--muted)" }}>
                دلیل برای مشتری فرستاده می‌شود و سکه‌های خرج‌شده خودکار برمی‌گردند.
              </p>
            </div>

            <div className="p-5 overflow-y-auto flex-1" style={{ minHeight: 0 }}>
              <div className="text-[13px] mb-2" style={{ color: "var(--dim)" }}>دلیل‌های آماده:</div>
              <div className="flex flex-col gap-2 mb-4">
                {REJECT_REASONS.map((r, ri) => (
                  <button key={ri} onClick={() => setReason(r)}
                    className="text-right p-2.5 rounded-xl text-[13px] transition-all"
                    style={reason === r
                      ? { background: "var(--danger-soft)", border: "1px solid var(--danger-line)", color: "var(--text)" }
                      : { background: "var(--surface-3)", border: "1px solid var(--border)", color: "var(--dim)" }}>
                    {r}
                  </button>
                ))}
              </div>

              <Field label="یا دلیل خودتان را بنویسید">
                <textarea className="fx-input" rows={3} value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="مثلاً: مبلغ واریزی ۵۰ هزار تومان کمتر است" />
              </Field>
            </div>

            <div className="p-5 shrink-0 flex gap-2" style={{ borderTop: "1px solid var(--border)" }}>
              <button onClick={() => setRejecting(null)} className="fx-btn-g flex-1 py-3 text-[14px]">
                انصراف
              </button>
              <button onClick={doReject} disabled={!reason.trim()}
                className="flex-1 py-3 rounded-[11px] text-[14px] font-bold"
                style={{ background: reason.trim() ? "var(--danger)" : "var(--surface-2)",
                         color: reason.trim() ? "#fff" : "var(--muted)" }}>
                رد کن و اطلاع بده
              </button>
            </div>
          </div>
        </div>, document.body)}
    </div>
  );
}
