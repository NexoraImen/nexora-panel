/**
 * صندوق پیام — سمتِ مالک، به شکلِ یک پیام‌رسان.
 *
 * چرا این شکل و نه یک فهرستِ ساده: این صفحه جایی است که مالک با
 * مشتریِ عصبانی حرف می‌زند. هر چیزی که در تلگرام عادت دارد و این‌جا
 * نباشد، یک لحظه مکث می‌سازد — و مکثِ آن لحظه یعنی جوابِ دیرتر.
 *
 * پس: دو ستونِ تمام‌قد، جست‌وجو در گفتگوها، جداکننده‌ی تاریخ،
 * گروه‌شدنِ پیام‌های پشت‌سرهم، ساعت روی هر پیام، و نشانِ خوانده‌شدن.
 *
 * خبرهای خودکار (تایید/ردِ رسید) با `sender='system'` در همین
 * گفتگو می‌نشینند، پس مالک دقیقاً همان چیزی را می‌بیند که مشتری
 * دیده — نه یک روایتِ جدا.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowDown, Check, CheckCheck, ImagePlus, Loader2,
  MessageCircle, Pencil, Plus, RefreshCw, Search, Send, Shield, Trash2, X, Zap,
} from "lucide-react";

import { adminSrc } from "../../lib/botsrc";
import { faNum, toFaDigits } from "../../lib/format";
import {
  Avatar, EmptyState, Field, Lightbox, Modal, PageSkeleton, SectionHead,
} from "../../ui/index";
import { shrinkImage } from "../../lib/image.js";

/* ── پاسخ‌های آماده ──

   همان ده جوابی که هر روز تایپ می‌شوند. مالک عوضشان می‌کند؛ اینها
   فقط نقطه‌ی شروع‌اند تا صندوق از روزِ اول خالی نباشد.

   کلیک می‌کند و متن **داخلِ کادر می‌نشیند**، نه اینکه مستقیم برود.
   جوابِ آماده تقریباً همیشه یک جمله کم دارد — و دکمه‌ای که خودش
   بفرستد یعنی آن جمله هیچ‌وقت اضافه نمی‌شود. */

export const QUICK_DEFAULTS = [
  { title: "لینک را کپی کنید",
    body: "سلام {name} 🙂\nلینکِ اشتراکتان را از بخش «اشتراک‌های من» "
        + "کپی کنید و در برنامه از گزینه‌ی افزودن از کلیپ‌بورد واردش کنید." },
  { title: "نصب برنامه",
    body: "برای نصب، از بخش «آموزش نصب» در ربات برنامه‌ی مخصوصِ "
        + "دستگاهتان را بگیرید. سه قدم است و کمتر از دو دقیقه." },
  { title: "رسید تایید شد",
    body: "رسیدتان تایید شد ✅\nاشتراکتان همین حالا فعال شد — "
        + "لینکش را برایتان فرستادیم." },
  { title: "رسید نامشخص",
    body: "تصویرِ رسید واضح نیست. لطفاً یک عکسِ روشن‌تر یا متنِ "
        + "پیامکِ بانک را بفرستید تا سریع بررسی کنیم." },
  { title: "قطعی موقت",
    body: "قطعیِ موقتِ شبکه است و در حالِ رفعش هستیم. چند دقیقه "
        + "دیگر دوباره وصل شوید 🙏" },
  { title: "سرعت کم",
    body: "لطفاً یک‌بار سرورِ دیگری را از داخلِ برنامه امتحان کنید. "
        + "اگر باز هم کند بود، ساعتِ دقیق و نامِ سرور را بگویید." },
];


/* ── زمان ──
   ساعت روی پیام، و روزِ آن بالای گروه. تاریخِ کامل روی هر پیام،
   ستونِ باریکی می‌سازد که چشم مجبور است از رویش رد شود. */

const clock = (at) => {
  const s = String(at || "");
  const hm = s.slice(11, 16);
  return hm ? toFaDigits(hm) : "";
};

const dayKey = (at) => String(at || "").slice(0, 10);

function dayLabel(key) {
  if (!key) return "";
  const today = new Date().toISOString().slice(0, 10);
  const y = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  if (key === today) return "امروز";
  if (key === y) return "دیروز";
  try {
    return new Date(key + "T00:00:00").toLocaleDateString("fa-IR");
  } catch { return toFaDigits(key); }
}

/* `src`: منبعِ داده. خالی یعنی پنلِ مالک؛ پرتالِ نماینده
   `portalSrc(token)` می‌دهد و **همین صفحه** با داده‌ی او کار می‌کند
   (lib/botsrc.js — چرا یک صفحه و نه کپی). */
export function BotInboxSection({ password, src, note }) {
  const S = useMemo(() => src || adminSrc(password), [src, password]);
  const [threads, setThreads] = useState(null);
  const [open, setOpen] = useState(null);
  const [msgs, setMsgs] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [atEnd, setAtEnd] = useState(true);
  // عکسِ انتخاب‌شده ولی هنوز نفرستاده، و عکسی که تمام‌صفحه باز است
  const [photo, setPhoto] = useState("");
  const [shrinking, setShrinking] = useState(false);
  const [zoom, setZoom] = useState("");
  // پاسخ‌های آماده و ویرایشگرشان
  const [quick, setQuick] = useState(null);
  // null یعنی «خوانده نشده» — نه «تنظیماتِ خالی». ذخیره‌ی پاسخ‌های آماده
  // کلِ تنظیمات را پس می‌فرستد، پس بی‌این، شکستِ خواندن همه‌چیز را پاک می‌کرد.
  const [brand, setBrand] = useState(null);
  const [editQ, setEditQ] = useState(null);

  const logRef = useRef(null);
  const endRef = useRef(null);
  const boxRef = useRef(null);
  const photoRef = useRef(null);

  const loadThreads = useCallback(async () => {
    setErr("");
    try {
      const j = await S.inbox();
      setThreads(j.threads || []);
    } catch (e) { setErr(e.message); setThreads([]); }
  }, [S]);

  const loadThread = useCallback(async (uid) => {
    if (!uid) return;
    try {
      const j = await S.inbox(uid);
      setMsgs(j.messages || []);
    } catch (e) { setErr(e.message); }
  }, [S]);

  // پاسخ‌های آماده از تنظیمات می‌آیند. اگر چیزی ذخیره نشده باشد،
  // پیش‌فرض‌ها نشان داده می‌شوند — نه یک ردیفِ خالی که مالک نفهمد
  // این‌جا قرار بوده چه باشد.
  const loadQuick = useCallback(async () => {
    try {
      const st = await S.settings();
      setBrand(st);
      const q0 = Array.isArray(st.quick_replies) ? st.quick_replies : null;
      setQuick(q0 && q0.length ? q0 : QUICK_DEFAULTS);
    } catch (e) {
      setQuick(QUICK_DEFAULTS);
      setErr(`تنظیماتِ ربات خوانده نشد؛ پاسخ‌های آماده ذخیره نمی‌شوند: ${e.message}`);
    }
  }, [S]);

  useEffect(() => { loadQuick(); }, [loadQuick]);
  useEffect(() => { loadThreads(); }, [loadThreads]);
  useEffect(() => { if (open) { setMsgs(null); loadThread(open); } }, [open, loadThread]);

  /* پایین‌ماندن — ولی فقط وقتی کاربر خودش پایین است.
     اگر وسطِ تاریخچه باشد و پیام تازه بیاید، پرتاب‌شدن به انتها
     آزاردهنده است؛ به‌جایش دکمه‌ی «برو پایین» می‌آید. */
  useEffect(() => {
    if (atEnd) endRef.current?.scrollIntoView({ block: "end" });
  }, [msgs, atEnd]);

  const onScroll = () => {
    const el = logRef.current;
    if (!el) return;
    setAtEnd(el.scrollHeight - el.scrollTop - el.clientHeight < 60);
  };

  /* گفتگوی باز زنده می‌ماند — مشتری ممکن است همین حالا بنویسد.
   *
   * پانزده ثانیه برای یک گفتگو خیلی زیاد بود: مشتری می‌نوشت و
   * مالک تا ربع دقیقه بعد نمی‌دید. حالا سه ثانیه — ولی فقط تا دو
   * دقیقه بعد از آخرین حرکت. گفتگویی که رها شده نباید تا ابد هر
   * سه ثانیه به سرور بزند.
   */
  const lastMove = useRef(Date.now());
  useEffect(() => { lastMove.current = Date.now(); }, [open, msgs]);

  useEffect(() => {
    if (!open) return undefined;
    const id = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      const idle = Date.now() - lastMove.current > 120000;
      // وقتی گفتگو سرد شده، هر پنجمین تیک کافی است
      if (idle && Math.floor(Date.now() / 3000) % 5 !== 0) return;
      loadThread(open);
      loadThreads();
    }, 3000);
    return () => clearInterval(id);
  }, [open, loadThread, loadThreads]);

  // برگشت به تب باید فوری تازه کند، نه اینکه تا تیکِ بعدی صبر کند
  useEffect(() => {
    if (!open) return undefined;
    const wake = () => {
      if (document.visibilityState !== "visible") return;
      lastMove.current = Date.now();
      loadThread(open);
      loadThreads();
    };
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("focus", wake);
    return () => {
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("focus", wake);
    };
  }, [open, loadThread, loadThreads]);

  /**
   * فرستادن — با حبابِ فوری.
   *
   * قبلاً متن تا وقتی *دو* رفت‌وبرگشت تمام نمی‌شد (POST، بعد
   * خواندنِ دوباره‌ی گفتگو) روی صفحه نمی‌آمد. روی اینترنتِ کند یعنی
   * یکی دو ثانیه که انگار هیچ اتفاقی نیفتاده — و مالک دوباره
   * می‌زد.
   *
   * حالا حباب همان لحظه می‌نشیند با نشانِ «در حال رفتن»، و اگر
   * نرسید همان‌جا قرمز می‌شود. جعبه هم فوری خالی می‌شود.
   */
  /* عکسِ انتخاب‌شده، پیش از فرستادن.
     همان هسته‌ی کوچک‌کردنِ مینی‌اپ (`lib/image.js`) — نه نسخه‌ی
     دومی که یک روز حدِ حجم یا چرخشِ عکس را فراموش کند. */
  const pickPhoto = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setErr("");
    if (!/^image\//.test(f.type || "")) { setErr("فقط عکس فرستاده می‌شود"); return; }
    setShrinking(true);
    try {
      const out = await shrinkImage(f);
      if (out.bytes > 3 * 1024 * 1024) {
        setErr("حجم عکس بیشتر از ۳ مگابایت است"); return;
      }
      setPhoto(out.data);
      boxRef.current?.focus();
    } catch (e2) { setErr(e2.message || "عکس خوانده نشد"); }
    finally { setShrinking(false); }
  };

  /**
   * متنِ پاسخِ آماده، با جای‌گذارهای پرشده.
   *
   * فقط سه جای‌گذار، و هر سه از داده‌ای می‌آیند که این صفحه واقعاً
   * دارد. جای‌گذاری که داده‌اش نیست، خالی چاپ می‌شود — و جمله‌ای
   * که وسطش سوراخ دارد از نبودش بدتر است.
   */
  const fillQuick = (body) => {
    const th = (threads || []).find((t) => t.userId === open);
    return String(body || "")
      .replace(/\{name\}/g, (th?.name || "").trim() || "دوست عزیز")
      .replace(/\{brand\}/g, (brand && brand.brand) || "")
      .replace(/\{support\}/g, (brand && brand.support_username) || "");
  };

  /** درج در کادر، نه ارسال. تقریباً همیشه یک جمله باید اضافه شود. */
  const useQuick = (body) => {
    const t = fillQuick(body);
    setText((prev) => (prev.trim() ? `${prev.replace(/\s+$/, "")}\n${t}` : t));
    boxRef.current?.focus();
  };

  const saveQuick = async (rows) => {
    if (!brand) {
      setErr("تنظیماتِ ربات هنوز خوانده نشده — صفحه را تازه کنید، بعد ذخیره کنید");
      return;
    }
    setQuick(rows);
    try {
      await S.saveSettings({ ...brand, quick_replies: rows });
      setBrand((b) => ({ ...b, quick_replies: rows }));
    } catch (e) { setErr(e.message); }
  };

  const send = async () => {
    const body = text.trim();
    if ((!body && !photo) || busy || !open) return;
    const temp = `tmp-${Date.now()}`;
    const pic = photo;
    setBusy(true); setErr("");
    setText(""); setPhoto("");
    setAtEnd(true);
    setMsgs((prev) => [...(prev || []), {
      id: temp, from: "admin", body, photo: pic,
      at: new Date().toISOString().slice(0, 19).replace("T", " "),
      pending: true,
    }]);
    boxRef.current?.focus();
    try {
      await S.inboxSend({ userId: open, body, ...(pic ? { photo: pic } : {}) });
      lastMove.current = Date.now();
      await loadThread(open);
      loadThreads();
    } catch (e) {
      setErr(e.message);
      // حبابِ ناموفق نباید شبیه پیامِ رفته بماند
      setMsgs((prev) => (prev || []).map(
        (m) => (m.id === temp ? { ...m, pending: false, failed: true } : m)));
    } finally { setBusy(false); }
  };

  const cur = (threads || []).find((t) => t.userId === open);

  const shown = useMemo(() => {
    const needle = q.trim();
    if (!needle) return threads || [];
    return (threads || []).filter((t) =>
      `${t.name} ${t.username} ${t.tgId} ${t.lastBody}`.includes(needle));
  }, [threads, q]);

  /* پیام‌های پشت‌سرهمِ یک نفر یک گروه می‌شوند: فقط اولی چهره و
     نامش را می‌گیرد. بدون این، ده پیامِ پشت‌سرهم ده تا آواتار
     می‌شوند و صفحه شلوغ می‌شود. */
  const grouped = useMemo(() => {
    const out = [];
    let lastDay = null;
    let lastFrom = null;
    (msgs || []).forEach((m) => {
      const d = dayKey(m.at);
      if (d && d !== lastDay) {
        out.push({ kind: "day", key: `d${d}`, label: dayLabel(d) });
        lastDay = d;
        lastFrom = null;
      }
      out.push({ kind: "msg", key: m.id, m, head: m.from !== lastFrom });
      lastFrom = m.from;
    });
    return out;
  }, [msgs]);

  return (
    <>
      <SectionHead icon={MessageCircle} title="پیام‌ها"
        desc="گفتگو با مشتری‌ها. خبرهای خودکار — مثل تایید یا رد رسید — هم در همین گفتگو ثبت می‌شوند، پس دقیقاً همان چیزی را می‌بینید که مشتری دیده."
        action={
          <button onClick={() => { loadThreads(); if (open) loadThread(open); }}
            className="fx-btn-g px-3 py-2 text-[13px] flex items-center gap-1.5">
            <RefreshCw size={13} /> تازه‌سازی
          </button>
        } />

      {err && (
        <p className="text-[13px] mb-3 flex items-start gap-1.5"
          style={{ color: "var(--danger)" }}>
          <AlertTriangle size={13} className="shrink-0 mt-0.5" />{err}
        </p>
      )}

      {!threads ? (
        <PageSkeleton />
      ) : !threads.length ? (
        <EmptyState icon={MessageCircle} text="هنوز پیامی نیامده"
          hint="هر پیامی که مشتری از مینی‌اپ بفرستد همین‌جا می‌آید — و خبر تایید و رد رسیدها هم." />
      ) : (
        <div className="fx-chat">
          {/* ── ستونِ گفتگوها ── */}
          <aside className="fx-chat-list">
            <div className="fx-chat-search">
              <Search size={13} />
              <input value={q} onChange={(e) => setQ(e.target.value)}
                placeholder="جست‌وجوی نام یا شناسه" />
            </div>

            <div className="fx-chat-rows">
              {!shown.length ? (
                <p className="text-[12.5px] text-center py-6" style={{ color: "var(--muted)" }}>
                  چیزی پیدا نشد
                </p>
              ) : shown.map((t) => (
                <button key={t.userId} onClick={() => setOpen(t.userId)}
                  className={`fx-chat-row ${open === t.userId ? "on" : ""}`}>
                  <Avatar name={t.name || t.username} id={t.tgId} size={38}
                    src={t.avatar} />
                  <span className="fx-chat-row-body">
                    <span className="fx-chat-row-top">
                      <b>{t.name || "بدون نام"}</b>
                      <i>{clock(t.lastAt) || toFaDigits(String(t.lastAt || "").slice(5, 10))}</i>
                    </span>
                    <span className="fx-chat-row-bot">
                      <span>{t.lastBody || "—"}</span>
                      {t.unread > 0 && <em>{faNum(t.unread)}</em>}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </aside>

          {/* ── گفتگو ── */}
          <section className="fx-chat-pane">
            {!open ? (
              <div className="fx-chat-blank">
                <EmptyState icon={MessageCircle} text="یک گفتگو را باز کنید"
                  hint="از فهرست، مشتری‌ای را انتخاب کنید." />
              </div>
            ) : (
              <>
                <header className="fx-chat-head">
                  <Avatar name={cur?.name || cur?.username} id={cur?.tgId} size={34}
                    src={cur?.avatar} />
                  <div className="min-w-0">
                    <b>{cur?.name || "بدون نام"}</b>
                    <span dir="ltr">
                      {cur?.username ? `@${cur.username} · ` : ""}
                      {cur?.tgId ? toFaDigits(cur.tgId) : ""}
                    </span>
                  </div>
                </header>

                <div className="fx-chat-log" ref={logRef} onScroll={onScroll}>
                  {!msgs ? (
                    <div className="p-4"><PageSkeleton /></div>
                  ) : !msgs.length ? (
                    <p className="text-[12.5px] text-center py-8"
                      style={{ color: "var(--muted)" }}>
                      هنوز پیامی رد و بدل نشده
                    </p>
                  ) : grouped.map((g) => (
                    g.kind === "day" ? (
                      <div key={g.key} className="fx-chat-day"><span>{g.label}</span></div>
                    ) : (
                      <div key={g.key}
                        className={`fx-bub ${g.m.from} ${g.head ? "head" : ""}`
                          + `${g.m.pending ? " pending" : ""}${g.m.failed ? " failed" : ""}`
                          + `${g.m.photo ? " pic" : ""}`}>
                        {g.m.from === "system" && <Shield size={12} className="fx-bub-ico" />}
                        {g.m.photo && (
                          <button className="fx-bub-photo" onClick={() => setZoom(g.m.photo)}
                            aria-label="بزرگ‌کردن عکس">
                            <img src={g.m.photo} alt="" loading="lazy" />
                          </button>
                        )}
                        {g.m.body && <span className="fx-bub-text">{g.m.body}</span>}
                        <span className="fx-bub-meta">
                          {clock(g.m.at)}
                          {/* حبابِ خوش‌بینانه باید بگوید هنوز نرفته —
                              وگرنه پیامی که نرسیده شبیه پیامِ رفته است */}
                          {g.m.from === "admin" && (
                            g.m.failed ? <AlertTriangle size={12} />
                              : g.m.pending ? <Loader2 size={12} className="animate-spin" />
                                : g.m.read ? <CheckCheck size={12} /> : <Check size={12} />
                          )}
                        </span>
                      </div>
                    )
                  ))}
                  <div ref={endRef} />
                </div>

                {!atEnd && (
                  <button className="fx-chat-down" title="برو به آخرین پیام"
                    onClick={() => { setAtEnd(true); endRef.current?.scrollIntoView({ block: "end" }); }}>
                    <ArrowDown size={15} />
                  </button>
                )}

                {/* عکسِ آماده‌ی ارسال، با راهِ برداشتنش */}
                {photo && (
                  <div className="fx-chat-att">
                    <img src={photo} alt="عکس انتخاب‌شده" />
                    <button onClick={() => setPhoto("")} aria-label="برداشتن عکس">
                      <X size={13} />
                    </button>
                  </div>
                )}

                {/* پاسخ‌های آماده.
                    بالای کادر و نه داخلِ منو: چیزی که هر روز ده بار
                    استفاده می‌شود نباید یک کلیکِ اضافه داشته باشد. */}
                <div className="fx-quick">
                  <Zap size={13} className="fx-quick-i" aria-hidden="true" />
                  <div className="fx-quick-row">
                    {(quick || []).map((r, i) => (
                      <button key={`${r.title}-${i}`} type="button"
                        className="fx-quick-chip" disabled={busy}
                        title={fillQuick(r.body)}
                        onClick={() => useQuick(r.body)}>
                        {r.title}
                      </button>
                    ))}
                  </div>
                  <button type="button" className="fx-quick-edit"
                    onClick={() => setEditQ((quick || []).map((x) => ({ ...x })))}
                    title="ویرایش پاسخ‌های آماده"
                    aria-label="ویرایش پاسخ‌های آماده">
                    <Pencil size={12} />
                  </button>
                </div>

                <footer className="fx-chat-bar">
                  <button className="fx-clip" onClick={() => photoRef.current?.click()}
                    disabled={busy || shrinking} aria-label="فرستادن عکس"
                    title="فرستادن عکس">
                    {shrinking ? <Loader2 size={16} className="animate-spin" />
                               : <ImagePlus size={16} />}
                  </button>
                  <input ref={photoRef} type="file" accept="image/*" className="hidden"
                    onChange={pickPhoto} />
                  <textarea ref={boxRef} rows={1} dir="auto" value={text}
                    onChange={(e) => setText(e.target.value)}
                    onPaste={(e) => {
                      /* چسباندنِ عکس از کلیپ‌بورد: مالک معمولاً
                         اسکرین‌شات می‌گیرد و Ctrl+V می‌زند. بدون
                         این، باید اول ذخیره‌اش کند. */
                      const it = [...(e.clipboardData?.items || [])]
                        .find((x) => x.type?.startsWith("image/"));
                      const f = it?.getAsFile?.();
                      if (!f) return;
                      e.preventDefault();
                      pickPhoto({ target: { files: [f], value: "" } });
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                    }}
                    placeholder={photo
                      ? "توضیحی برای عکس… (اختیاری)"
                      : "پیام بنویسید…  (Enter می‌فرستد، Shift+Enter خط تازه)"} />
                  <button onClick={send} disabled={busy || (!text.trim() && !photo)}
                    aria-label="فرستادن" title="فرستادن">
                    {busy ? <Loader2 size={16} className="animate-spin" />
                          : <Send size={16} />}
                  </button>
                </footer>
                <p className="fx-chat-note">
                  {note || "پاسخ شما هم در مینی‌اپ و هم در خودِ ربات به مشتری می‌رسد."}
                </p>
              </>
            )}
          </section>
        </div>
      )}

      {editQ && (
        <Modal title="پاسخ‌های آماده" onClose={() => setEditQ(null)} width="560px">
          <p className="text-[12.5px] mb-3" style={{ color: "var(--muted)" }}>
            جای‌گذارها: <code>{"{name}"}</code> نامِ مشتری ·{" "}
            <code>{"{brand}"}</code> نامِ برند · <code>{"{support}"}</code>{" "}
            یوزرنیمِ پشتیبانی
          </p>

          {editQ.map((r, i) => (
            <div key={i} className="fx-card p-3 mb-2">
              <div className="flex items-center gap-2 mb-2">
                <input className="fx-input" value={r.title}
                  placeholder="عنوانِ دکمه"
                  onChange={(e) => setEditQ(editQ.map(
                    (x, j) => (j === i ? { ...x, title: e.target.value } : x)))} />
                <button type="button" className="fx-ico-btn shrink-0"
                  onClick={() => setEditQ(editQ.filter((_x, j) => j !== i))}
                  title="حذف" aria-label="حذف این پاسخ">
                  <Trash2 size={14} />
                </button>
              </div>
              <textarea className="fx-input" rows={2} value={r.body}
                placeholder="متنِ پاسخ"
                onChange={(e) => setEditQ(editQ.map(
                  (x, j) => (j === i ? { ...x, body: e.target.value } : x)))}
                style={{ resize: "vertical", lineHeight: 1.9 }} />
            </div>
          ))}

          <div className="flex items-center justify-between gap-2 mt-3">
            <button type="button" className="fx-btn-g px-3 py-2 text-[13px] flex items-center gap-1.5"
              onClick={() => setEditQ([...editQ, { title: "", body: "" }])}>
              <Plus size={13} /> پاسخ تازه
            </button>
            <div className="flex items-center gap-2">
              <button type="button" className="fx-btn-g px-3 py-2 text-[13px]"
                onClick={() => setEditQ(QUICK_DEFAULTS.map((x) => ({ ...x })))}>
                بازگرداندن پیش‌فرض‌ها
              </button>
              <button type="button" className="fx-btn px-4 py-2 text-[13px]"
                onClick={() => {
                  /* ردیفِ بی‌عنوان یا بی‌متن، چیپی می‌سازد که یا
                     دیده نمی‌شود یا هیچ درج نمی‌کند. */
                  const rows = editQ
                    .map((x) => ({ title: (x.title || "").trim(),
                                   body: (x.body || "").trim() }))
                    .filter((x) => x.title && x.body);
                  saveQuick(rows.length ? rows : QUICK_DEFAULTS);
                  setEditQ(null);
                }}>
                ذخیره
              </button>
            </div>
          </div>
        </Modal>
      )}

      <Lightbox src={zoom} onClose={() => setZoom("")} />
    </>
  );
}
