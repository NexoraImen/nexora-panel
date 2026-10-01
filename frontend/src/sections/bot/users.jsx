/**
 * ربات: کاربران و پرونده‌ی مشتری.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect, useMemo, useRef } from "react";
import { useDebouncedChange } from "../../lib/hooks";
import { createPortal } from "react-dom";
import {
  AlertTriangle, Ban, ChevronLeft, Loader2, Package, RefreshCw, Send, Trash2, Users, X,
} from "lucide-react";
import { adminSrc } from "../../lib/botsrc";
import { isoToJalaliLabel } from "../../ui/jalali";
import { daysLeft, faNum, fmtBytes, fmtDate } from "../../lib/format";
import { Avatar, ConfirmModal, EmptyState, FilterBar, InfoBox, Modal, Msg, PageSkeleton, Pager, SectionHead, StatStrip, StatusPill } from "../../ui/index";

// فیلترهای بخش کاربران — کلیدها باید عیناً با _USER_FILTERS در
// backend/app.py بخوانند.
export const USER_FILTERS = [
  { key: "all", label: "همه" },
  { key: "active", label: "اشتراک فعال" },
  { key: "expired", label: "منقضی‌شده" },
  { key: "never", label: "بدون خرید" },
  { key: "buyers", label: "خریدار" },
  { key: "withPhone", label: "شماره دارد" },
  { key: "noPhone", label: "بدون شماره" },
  { key: "withBalance", label: "کیف پول دار" },
  { key: "withCoins", label: "سکه دار" },
  { key: "referred", label: "با دعوت" },
  { key: "blocked", label: "مسدود" },
];

export const USER_SORTS = [
  { key: "new", label: "تازه‌ترین" },
  { key: "old", label: "قدیمی‌ترین" },
  { key: "spent", label: "بیشترین خرید" },
  { key: "balance", label: "بیشترین موجودی" },
  { key: "coins", label: "بیشترین سکه" },
  { key: "lastSeen", label: "آخرین فعالیت" },
];

export const PAGE = 40;

/* `src` خالی یعنی پنلِ مالک؛ پرتالِ نماینده `portalSrc` می‌دهد و همین
   فهرست با مشتری‌های خودِ او پر می‌شود (مرز در بکند است). */
export function BotUsersSection({ password, src }) {
  const S = useMemo(() => src || adminSrc(password), [src, password]);
  const [d, setD] = useState({ users: [], total: 0, counts: {} });
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("new");
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState(null);
  const [msgTo, setMsgTo] = useState(null);
  const [loading, setLoading] = useState(true);
  // «در حال جستجو» با «هنوز چیزی نیامده» یکی نیست. اولی نباید
  // فهرست را پاک کند؛ اسکلت فقط برای دومی است.
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const seq = useRef(0);
  // ban / remove (docs/specs/2026-10-01-admin-bot-backup-ui.md): the owner
  // asked for both, for himself and for resellers, for security cases
  const [ask, setAsk] = useState(null);       // {u, kind: "block"|"unblock"|"delete"}
  const [note, setNote] = useState(null);
  const [sweeping, setSweeping] = useState(false);

  const load = async (opts = {}) => {
    const query = opts.q !== undefined ? opts.q : q;
    const f = opts.filter || filter;
    const s = opts.sort || sort;
    const off = opts.offset !== undefined ? opts.offset : offset;

    // شماره‌ی درخواست: تایپِ سریع یعنی چند درخواستِ هم‌زمان، و
    // پاسخ‌ها لزوماً به ترتیب نمی‌آیند. بدون این، پاسخِ کوتاه‌ترِ
    // یک عبارتِ قدیمی‌تر روی نتیجه‌ی تازه می‌نشست و فهرست با چیزی
    // که در فیلد نوشته شده جور درنمی‌آمد.
    const mine = ++seq.current;
    setBusy(true);
    try {
      const p = new URLSearchParams({
        q: query, filter: f, sort: s, offset: off, limit: PAGE,
      });
      // شمارشِ فیلترها به عبارتِ جستجو ربطی ندارد — همان عددها را
      // برمی‌گرداند. ولی یازده کوئریِ `EXISTS` است و روی ۲۵ هزار
      // کاربر ۳۶ میلی‌ثانیه از هر ضربه‌ی کیبورد را می‌خورد. پس
      // موقع تایپ نمی‌خواهیمش و عددهای قبلی را نگه می‌داریم.
      if (query) p.set("counts", "0");
      const r = await S.users(p.toString());
      if (mine !== seq.current) return;
      setD((prev) => ({
        users: r.users || [], total: r.total || 0,
        counts: r.counts || prev.counts || {},
      }));
      setErr(null);
    } catch (e) {
      // پیش‌تر «بی‌صدا» بود: خطای شبکه یا رمز همان «در این دسته کاربری
      // نیست» را نشان می‌داد — فهرستِ خالی و فهرستِ خوانده‌نشده یکی بودند
      if (mine === seq.current) setErr((e && e.message) || "خواندنِ کاربران ناموفق بود");
    }
    finally {
      if (mine === seq.current) { setBusy(false); setLoading(false); }
    }
  };
  useEffect(() => { load({ offset: 0 }); }, [S]);

  // جستجوی زنده — بدون این، ادمین باید هر بار Enter بزند.
  // بارِ اول اجرا نمی‌شود، وگرنه بازکردنِ صفحه دو درخواستِ یکسان
  // می‌زد و فهرست بعد از آمدن دوباره به اسکلت برمی‌گشت.
  useDebouncedChange(q, 250, () => { setOffset(0); load({ q, offset: 0 }); });

  const pick = (key) => { setFilter(key); setOffset(0); load({ filter: key, offset: 0 }); };
  const pickSort = (key) => { setSort(key); setOffset(0); load({ sort: key, offset: 0 }); };
  const go = (off) => { setOffset(off); load({ offset: off }); };

  const users = d.users;
  const pages = Math.ceil(d.total / PAGE) || 1;

  const act = async () => {
    const { u, kind } = ask;
    setAsk(null);
    try {
      if (kind === "delete") {
        const r = await S.removeUser(u.tg_id);
        setNote({ t: "ok", m: `«${u.first_name || u.tg_id}» حذف شد${r.configs ? ` و ${faNum(r.configs)} کانفیگش از 3x-ui پاک شد` : ""}.` });
      } else {
        await S.block(u.tg_id, kind === "block");
        setNote({ t: "ok", m: kind === "block"
          ? `«${u.first_name || u.tg_id}» مسدود شد: ربات و مینی‌اپ دیگر جوابش را نمی‌دهند.`
          : `مسدودیِ «${u.first_name || u.tg_id}» برداشته شد.` });
      }
      load();
    } catch (e) { setNote({ t: "err", m: e.message }); }
  };

  /* Configs deleted in 3x-ui: remove them from the bot now, and say why
     for any that stay (the owner saw them linger with no reason given). */
  const sweep = async () => {
    setSweeping(true); setNote(null);
    try {
      const r = await S.sweep();
      if (!r.ok) { setNote({ t: "err", m: `3x-ui خوانده نشد: ${r.why}` }); return; }
      const gone = r.shops.reduce((a, x) => a + (x.gone || 0), 0);
      const stuck = r.shops.filter((x) => x.skipped || x.error);
      setNote(stuck.length
        ? { t: "err", m: `${faNum(gone)} کانفیگِ پاک‌شده برداشته شد. در ${faNum(stuck.length)} فروشگاه کاری نشد: `
            + stuck.map((x) => x.error || x.why).join(" · ") }
        : { t: "ok", m: gone ? `${faNum(gone)} کانفیگ که در 3x-ui پاک شده بود از ربات و مینی‌اپ برداشته شد.`
            : `همه‌ی کانفیگ‌های ربات در 3x-ui هستند (${faNum(r.xuiClients)} کانفیگ در پنل).` });
      load();
    } catch (e) { setNote({ t: "err", m: e.message }); }
    finally { setSweeping(false); }
  };

  // خلاصه‌ی همین صفحه — بدون درخواست تازه
  const rows = d.users || [];
  const walletSum = rows.reduce((a, u) => a + (Number(u.balance) || 0), 0);
  const withPhone = rows.filter((u) => u.phone).length;
  const blocked = rows.filter((u) => u.is_blocked).length;
  const page = Math.floor(offset / PAGE) + 1;

  return (
    <div className="fx-anim">
      <SectionHead title="کاربران ربات"
        desc="هر کسی که با ربات تعامل داشته — با سابقه‌ی خرید، شماره تماس و امکان پیام مستقیم."
        action={
          <div className="flex items-center gap-2">
            {S.sweep && (
              <button onClick={sweep} disabled={sweeping}
                title="کانفیگ‌هایی را که در 3x-ui پاک شده‌اند از ربات و مینی‌اپ بردار"
                className="fx-btn-g px-3 py-2.5 text-[13px] flex items-center gap-1.5">
                {sweeping ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} همگام‌سازی با 3x-ui
              </button>
            )}
            <button onClick={() => load()} disabled={loading}
              className="fx-btn-g px-3 py-2.5 text-[13px] flex items-center gap-1.5">
              <RefreshCw size={13} /> بازخوانی
            </button>
          </div>
        } />
      <Msg msg={note} />

      {/* شمارِ کلِ دسته‌ها، از `counts` بکند — نه جمعِ همین صفحه. کاشیِ
          قبلی «کیف پول این صفحه» فقط چهل ردیفِ جاری را جمع می‌زد و با
          رفتن به صفحه‌ی بعد عوض می‌شد؛ عددی که معنای ثابتی نداشت. */}
      {err && <Msg msg={{ t: "err", m: err }} />}
      {!loading && d.counts && d.counts.all > 0 && (
        <StatStrip items={[
          { label: "کاربران", value: faNum(d.counts.all),
            hint: d.counts.referred ? `${faNum(d.counts.referred)} با دعوت` : "" },
          { label: "خریدار", value: faNum(d.counts.buyers || 0), color: "var(--ok)",
            hint: `${faNum(Math.round(((d.counts.buyers || 0) * 100) / d.counts.all))}٪` },
          { label: "اشتراکِ فعال", value: faNum(d.counts.active || 0),
            hint: d.counts.expired ? `${faNum(d.counts.expired)} منقضی` : "" },
          { label: "مسدود", value: faNum(d.counts.blocked || 0),
            color: d.counts.blocked ? "var(--danger)" : "var(--text)",
            hint: d.counts.withBalance ? `${faNum(d.counts.withBalance)} با موجودی` : "" },
        ]} />
      )}

      {/* جستجو، فیلتر، مرتب‌سازی — سه کنترل، نه هفده دکمه.
          اندازه‌گیری و دلیلش بالای `Menu` در `ui/index.jsx`.

          فیلترِ بی‌نتیجه هنوز حذف می‌شود، ولی حالا از *فهرستِ منو*
          — همان قاعده، جای کم‌هزینه‌تر. فیلترِ انتخاب‌شده همیشه
          می‌ماند، وگرنه با صفرشدنِ نتیجه از زیرِ دستِ کاربر ناپدید
          می‌شود و راهِ برگشتی نمی‌ماند. */}
      <FilterBar
        q={q} onQ={setQ} busy={busy && !loading}
        placeholder="نام، یوزرنیم، آیدی عددی یا شماره تماس..."
        filters={USER_FILTERS.filter(
          (f) => filter === f.key || d.counts[f.key] !== 0)}
        filter={filter} onFilter={pick} counts={d.counts}
        sorts={USER_SORTS} sort={sort} onSort={pickSort} />

      {loading ? (
        <PageSkeleton />
      ) : users.length === 0 ? (
        <EmptyState icon={Users} text={q ? `چیزی برای «${q}» پیدا نشد` : "در این دسته کاربری نیست"} />
      ) : (
        <>
          {/* جدول، نه ردیفِ دوخطی: هر کاربر ۷۴ پیکسل بود و ستون نداشت، پس
              «چه کسی بیشتر خرید کرده» را باید خط‌به‌خط خواند. حالا ستون‌ها
              زیرِ هم‌اند و ردیف ~۴۸ پیکسل. روی گوشی همان ردیف دوخطی می‌شود. */}
          <div className="fx-card usr-table mb-3" role="table" aria-label="کاربران ربات">
            <div className="usr-row usr-head" role="row">
              <span role="columnheader">کاربر</span>
              <span role="columnheader">شناسه و شماره</span>
              <span role="columnheader">خرید</span>
              <span role="columnheader">سکه</span>
              <span role="columnheader">کیف پول</span>
              <span role="columnheader" className="usr-trial">پیش از تست</span>
              <span role="columnheader" aria-label="کارها" />
            </div>
            {users.map((u) => (
              <div key={u.id} className="usr-row fx-rowhover" role="row">
                <button role="cell" onClick={() => setDetail(u.tg_id)} className="usr-who"
                  title="پرونده‌ی کاربر">
                  <Avatar name={u.first_name || u.username} id={u.tg_id} size={28} />
                  <span className="usr-name">{u.first_name || "بدون نام"}</span>
                  {u.username && <span className="usr-un" dir="ltr">@{u.username}</span>}
                  {u.activeSubs > 0 && (
                    <span className="fx-pill" style={{ background: "var(--ok-soft)", color: "var(--ok)" }}>فعال</span>
                  )}
                  {u.is_blocked === 1 && (
                    <span className="fx-pill" style={{ background: "var(--danger-soft)", color: "var(--danger)" }}>مسدود</span>
                  )}
                </button>
                {/* شناسه و شماره همان چیزی‌اند که مالک موقعِ پشتیبانی کپی
                    می‌کند؛ `fx-idnum` ستون را هم‌تراز نگه می‌دارد */}
                <span role="cell" className="usr-ids" dir="ltr">
                  <span className="fx-idnum" title="شناسه تلگرام">{u.tg_id}</span>
                  {u.phone && <span className="fx-idnum" title="شماره تماس">{u.phone}</span>}
                </span>
                <span role="cell" className="usr-num" data-label="خرید">
                  {u.ordersCount > 0
                    ? <>{faNum(u.ordersCount)} · <b>{faNum(u.spent)}</b></>
                    : <span className="usr-nil">—</span>}
                </span>
                <span role="cell" className="usr-num" data-label="سکه" style={{ color: u.coins ? "var(--warn)" : undefined }}>
                  {u.coins ? faNum(u.coins) : <span className="usr-nil">—</span>}
                </span>
                <span role="cell" className="usr-num" data-label="کیف پول" style={{ color: u.balance ? "var(--ok)" : undefined }}>
                  {u.balance ? faNum(u.balance) : <span className="usr-nil">—</span>}
                </span>
                <span role="cell" className="usr-trial" title="پاسخ‌های پیش از تست">
                  {u.trialInfo || <span className="usr-nil">—</span>}
                </span>
                <span role="cell" className="usr-act">
                  <button onClick={() => setMsgTo(u)} className="fx-ico-btn"
                    title="پیام به این کاربر" aria-label={`پیام به ${u.first_name || u.tg_id}`}>
                    <Send size={13} />
                  </button>
                  <button onClick={() => setAsk({ u, kind: u.is_blocked === 1 ? "unblock" : "block" })}
                    className="fx-ico-btn" style={u.is_blocked === 1 ? { color: "var(--danger)" } : undefined}
                    title={u.is_blocked === 1 ? "برداشتنِ مسدودی" : "مسدود کردن"}
                    aria-label={`${u.is_blocked === 1 ? "برداشتنِ مسدودیِ" : "مسدود کردنِ"} ${u.first_name || u.tg_id}`}>
                    <Ban size={13} />
                  </button>
                  <button onClick={() => setAsk({ u, kind: "delete" })} className="fx-ico-btn"
                    title="حذفِ کاربر و کانفیگ‌هایش" aria-label={`حذفِ ${u.first_name || u.tg_id}`}>
                    <Trash2 size={13} />
                  </button>
                  <button onClick={() => setDetail(u.tg_id)} className="fx-ico-btn"
                    title="پرونده‌ی کاربر" aria-label={`پرونده‌ی ${u.first_name || u.tg_id}`}>
                    <ChevronLeft size={14} />
                  </button>
                </span>
              </div>
            ))}
          </div>

          {/* شماره‌دار، نه «قبلی/بعدی» — با ۲۵ هزار کاربر، رسیدن به صفحه‌ی
              دهم ده کلیک بود (قاعده‌ی مخزن: صفحه‌بندیِ شماره‌دار) */}
          <Pager page={page} pages={pages} total={d.total} perPage={PAGE}
            onPage={(n) => go((n - 1) * PAGE)} />
        </>
      )}

      {ask && (
        <ConfirmModal
          title={ask.kind === "delete" ? "حذفِ کاربر" : ask.kind === "block" ? "مسدود کردنِ کاربر" : "برداشتنِ مسدودی"}
          desc={ask.kind === "delete"
            ? `«${ask.u.first_name || ask.u.tg_id}» مسدود می‌شود، همه‌ی کانفیگ‌هایش از 3x-ui پاک می‌شود و از فهرست می‌رود. سفارش‌ها و پرداخت‌هایش در حساب‌ها می‌ماند. برگشت ندارد.`
            : ask.kind === "block"
              ? `ربات و مینی‌اپ دیگر به «${ask.u.first_name || ask.u.tg_id}» جواب نمی‌دهند. کانفیگ‌هایش کار می‌کنند، مگر حذفش کنید.`
              : `«${ask.u.first_name || ask.u.tg_id}» دوباره می‌تواند از ربات استفاده کند.`}
          confirmLabel={ask.kind === "delete" ? "حذف کن" : ask.kind === "block" ? "مسدود کن" : "بردار"}
          onConfirm={act} onCancel={() => setAsk(null)} />
      )}

      {detail && (
        <SubscriberModal tgId={detail} src={S} onClose={() => setDetail(null)}
          onMessage={(u) => { setDetail(null); setMsgTo(u); }} />
      )}
      {msgTo && (
        <MessageUserModal user={msgTo} src={S} onClose={() => setMsgTo(null)} />
      )}
    </div>
  );
}

export function MessageUserModal({ user, password, src, onClose }) {
  const S = useMemo(() => src || adminSrc(password), [src, password]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const name = user.first_name || user.tg_id;

  const send = async () => {
    if (!text.trim()) return;
    setBusy(true); setMsg(null);
    try {
      await S.message(user.tg_id, text);
      setMsg({ t: "ok", m: "پیام فرستاده شد" });
      setText("");
      setTimeout(onClose, 1200);
    } catch (e) {
      setMsg({ t: "err", m: e.message || "ارسال ناموفق بود" });
    } finally { setBusy(false); }
  };

  return (
    <Modal title={`پیام به ${name}`} onClose={onClose} width="480px"
      footer={
        <div className="flex items-center justify-between gap-3 w-full">
          <span className="text-[12px]" style={{ color: "var(--muted)" }}>
            از طرف ربات، با عنوان «پیام از پشتیبانی» فرستاده می‌شود
          </span>
          <button onClick={send} disabled={busy || !text.trim()}
            className="fx-btn px-4 py-2.5 text-[14px] flex items-center gap-1.5 shrink-0">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} ارسال
          </button>
        </div>
      }>
      <Msg msg={msg} />
      <textarea className="fx-input" rows={6} value={text} autoFocus
        onChange={(e) => setText(e.target.value)}
        placeholder="سلام! درباره‌ی سفارشتان تماس می‌گیرم…"
        style={{ resize: "vertical", lineHeight: 1.8 }} />
      <div className="text-[12px] mt-2 flex items-center justify-between"
        style={{ color: "var(--muted)" }}>
        <span>{faNum(text.length)} از ۳۵۰۰ کاراکتر</span>
        {user.username && <span dir="ltr">@{user.username}</span>}
      </div>
      <InfoBox>
        اگر کاربر ربات را بلاک کرده باشد، پیام نمی‌رسد و همین‌جا به شما گفته می‌شود.
      </InfoBox>
    </Modal>
  );
}

export function SubscriberModal({ tgId, password, src, onClose, onMessage }) {
  const S = useMemo(() => src || adminSrc(password), [src, password]);
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setD(await S.subscriber(tgId));
      } catch (e) { setErr(e.message || "دریافت اطلاعات ناموفق بود"); }
      finally { setLoading(false); }
    })();
  }, [tgId, S]);

  const u = d?.user || {};
  const subs = d?.subscriptions || [];
  const live = d?.live || {};

  return createPortal(
    <div className="nx-modal-wrap fx-fade"
      style={{ background: "var(--veil)", backdropFilter: "blur(6px)" }}
      onClick={onClose}>
      <div className="w-full max-w-2xl rounded-2xl fx-scale nx-modal flex flex-col"
        onClick={(e) => e.stopPropagation()}
        style={{ background: "var(--surface)", border: "1px solid var(--accent-halo)" }}>

        <div className="p-5 shrink-0 flex items-start justify-between gap-3"
          style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[16px] font-bold text-white">
                {u.first_name || "بدون نام"}
              </span>
              {u.username && (
                <span className="text-[13px]" dir="ltr" style={{ color: "var(--muted)" }}>
                  @{u.username}
                </span>
              )}
              {u.is_blocked === 1 && (
                <span className="fx-pill" style={{ background: "var(--danger-soft)", color: "var(--danger)" }}>
                  مسدود
                </span>
              )}
            </div>
            {/* همان قاعده‌ی فهرست: شناسه و شماره باید خوانده شوند،
                چون مالک با همین‌ها آدم را می‌شناسد و کپی می‌کند. */}
            <div className="text-[12.5px] mt-1.5 flex items-center gap-2" dir="ltr">
              <span className="fx-idnum" title="شناسه تلگرام">{u.tg_id}</span>
              {u.phone && (
                <>
                  <span style={{ color: "var(--muted)", opacity: 0.4 }}>·</span>
                  <span className="fx-idnum" title="شماره تماس">{u.phone}</span>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {onMessage && u.tg_id && (
              <button onClick={() => onMessage(u)}
                className="fx-btn-g px-3 py-2 text-[13px] flex items-center gap-1.5">
                <Send size={13} /> پیام
              </button>
            )}
            <button title="بستن" onClick={onClose} className="fx-ico-btn"><X size={16} /></button>
          </div>
        </div>

        <div className="p-5 overflow-y-auto flex-1" style={{ minHeight: 0 }}>
          {loading && (
            <PageSkeleton />
          )}

          {err && (
            <div className="rounded-xl p-3 flex items-center gap-2 text-[13px]"
              style={{ background: "var(--danger-soft)", border: "1px solid var(--danger-line)", color: "var(--danger)" }}>
              <AlertTriangle size={14} /> {err}
            </div>
          )}

          {d && (
            <>
              {/* خلاصه */}
              <div className="fx-g3 grid grid-cols-3 gap-3 mb-5">
                {[
                  ["سکه", u.coins || 0, "var(--warn)"],
                  ["کیف پول", Number(u.balance || 0).toLocaleString("fa-IR"), "var(--ok)"],
                  ["خرید موفق", (d.orders || []).filter((o) => o.status === "approved").length, "var(--accent-2)"],
                ].map(([l, v, c2], i) => (
                  <div key={i} className="rounded-xl p-3 text-center"
                    style={{ background: "var(--surface-3)", border: "1px solid var(--border)" }}>
                    <div className="text-[18px] font-bold" style={{ color: c2, fontFamily: "var(--mono)" }}>{v}</div>
                    <div className="text-[12px] mt-1" style={{ color: "var(--muted)" }}>{l}</div>
                  </div>
                ))}
              </div>

              {/* اشتراک‌ها */}
              <div className="text-[14px] font-semibold text-white mb-3">
                اشتراک‌ها
                {!d.liveAvailable && subs.length > 0 && (
                  <span className="text-[12px] font-normal mr-2" style={{ color: "var(--warn)" }}>
                    · داده زنده در دسترس نیست
                  </span>
                )}
              </div>

              {subs.length === 0 && (
                <div className="text-center py-6 text-[13px]" style={{ color: "var(--muted)" }}>
                  اشتراکی ندارد
                </div>
              )}

              {subs.map((s) => {
                const lv = live[s.client_email];
                const used = lv ? (lv.up || 0) + (lv.down || 0) : 0;
                const total = lv?.total || 0;
                const pct = total > 0 ? Math.min(100, Math.round(used * 100 / total)) : 0;
                const dl = lv?.expiryTime ? daysLeft(lv.expiryTime) : null;
                const near = dl !== null && dl <= 3;

                return (
                  <div key={s.id} className="fx-card p-4 mb-3" style={{ background: "var(--surface-3)" }}>
                    <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
                      <div className="flex items-center gap-2">
                        <Package size={14} style={{ color: "var(--accent-2)" }} />
                        <span className="text-[14px] font-semibold text-white">
                          {s.plan_name || "اشتراک"}
                        </span>
                      </div>
                      <span className="fx-pill" style={{
                        background: s.is_active ? "var(--ok-soft)" : "var(--hair-2)",
                        color: s.is_active ? "var(--ok)" : "var(--muted)",
                      }}>
                        {s.is_active ? "فعال" : "غیرفعال"}
                      </span>
                    </div>

                    <div className="text-[12px] mb-3" dir="ltr"
                      style={{ color: "var(--muted)", fontFamily: "var(--mono)" }}>
                      {s.client_email}
                    </div>

                    {lv ? (
                      <>
                        <div className="flex justify-between mb-2">
                          <span className="text-[13px]" style={{ color: "var(--dim)" }}>مصرف حجم</span>
                          <span className="text-[13px] font-bold"
                            style={{ color: "var(--accent-2)", fontFamily: "var(--mono)" }}>
                            {fmtBytes(used)} {total > 0
                              ? `/ ${fmtBytes(total)}`
                              : <span className="fx-fa-sub">· نامحدود</span>}
                          </span>
                        </div>

                        {total > 0 && (
                          <div className="h-[8px] rounded-full overflow-hidden mb-3"
                            style={{ background: "var(--accent-soft)" }}>
                            <div style={{
                              width: `${pct}%`, height: "100%", borderRadius: 99,
                              background: pct >= 85
                                ? "linear-gradient(90deg,var(--danger),#FCA5A5)"
                                : "linear-gradient(90deg,var(--accent),var(--accent-2))",
                            }} />
                          </div>
                        )}

                        <div className="grid grid-cols-3 gap-2 mb-3">
                          {[
                            ["دانلود", fmtBytes(lv.down), "var(--ok)"],
                            ["آپلود", fmtBytes(lv.up), "var(--warn)"],
                            ["باقی", total > 0 ? fmtBytes(Math.max(0, total - used)) : "∞", "var(--accent-2)"],
                          ].map(([l, v, c2], i) => (
                            <div key={i} className="text-center">
                              <div className="text-[11.5px]" style={{ color: "var(--muted)" }}>{l}</div>
                              <div className="text-[13px] font-bold mt-0.5"
                                style={{ color: c2, fontFamily: "var(--mono)" }}>{v}</div>
                            </div>
                          ))}
                        </div>

                        <div className="flex justify-between text-[13px] pt-2"
                          style={{ borderTop: "1px solid var(--border)" }}>
                          <span style={{ color: "var(--muted)" }}>انقضا</span>
                          <span style={{ color: near ? "var(--warn)" : "var(--dim)" }}>
                            {fmtDate(lv.expiryTime)}
                            {dl !== null && (dl > 0 ? ` · ${dl} روز مانده` : " · منقضی شده")}
                          </span>
                        </div>
                      </>
                    ) : (
                      <div className="text-[13px] py-2" style={{ color: "var(--muted)" }}>
                        داده‌ی زنده از 3x-ui دریافت نشد — اتصال پنل را بررسی کنید
                      </div>
                    )}
                  </div>
                );
              })}

              {/* آخرین سفارش‌ها */}
              {(d.orders || []).length > 0 && (
                <>
                  <div className="text-[14px] font-semibold text-white mt-5 mb-3">آخرین سفارش‌ها</div>
                  {(d.orders || []).slice(0, 6).map((o) => (
                    <div key={o.id} className="flex items-center justify-between gap-2 py-2.5"
                      style={{ borderBottom: "1px solid var(--border)" }}>
                      <div className="min-w-0">
                        <div className="text-[13px]" style={{ color: "var(--dim)" }}>
                          {o.plan_name || "—"}
                        </div>
                        <div className="text-[12px] mt-0.5"
                          style={{ color: "var(--muted)", fontFamily: "var(--mono)" }}>
                          {/* این مسیر تاریخ را خام و میلادی می‌دهد
                              (ردیفِ دیتابیس است، نه خروجیِ ساخته‌شده)،
                              پس تبدیل این‌جا انجام می‌شود — وگرنه وسطِ
                              یک پرونده‌ی کاملاً فارسی یک تاریخِ میلادی
                              می‌نشیند. شناسه‌ی سفارش عمداً لاتین
                              می‌ماند؛ آن را کپی می‌کنند. */}
                          #{o.id} · {isoToJalaliLabel(o.created_at) || "—"}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-[13px]" style={{ color: "var(--dim)" }}>
                          {Number(o.amount || 0).toLocaleString("fa-IR")}
                        </span>
                        <StatusPill s={o.status} />
                      </div>
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
