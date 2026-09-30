/**
 * انتخابگر تاریخ شمسی.
 *
 * چرا نوشته شد:
 *     `<input type="date">` تقویم میلادی نشان می‌دهد. کسی که تاریخ
 *     شروع همکاری با یک واسطه را از حافظه می‌گوید، آن را شمسی به یاد
 *     دارد — «اول مهر ۱۴۰۳»، نه «۲۰۲۴-۰۹-۲۲». تبدیل ذهنی یعنی خطا،
 *     و خطا این‌جا مستقیم روی صورت‌حساب می‌نشیند.
 *
 *     پس ورودی شمسی است و خروجی میلادی: بک‌اند همان ISO را می‌گیرد
 *     که همیشه می‌گرفت و چیزی در آن سمت عوض نمی‌شود.
 *
 * تبدیل بدون کتابخانه انجام می‌شود. jdatetime سمت پایتون هست، ولی
 * آوردن یک کتابخانه‌ی تاریخ به باندل مرورگر برای همین یک فیلد،
 * چند ده کیلوبایت هزینه دارد. الگوریتم پایین همان الگوریتم
 * استاندارد است و در تست با تاریخ‌های واقعی سنجیده می‌شود.
 */
import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Calendar, ChevronLeft, ChevronRight, X } from "lucide-react";

const MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
const WEEK = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

const fa = (n) => String(n).replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);

/**
 * آیا این سال شمسی کبیسه است.
 *
 * چرخه‌ی ۳۳ ساله: در هر چرخه هشت سال کبیسه‌اند و جایشان ثابت است.
 * این قاعده برای سال‌های کاری ما (۱۳۰۰ تا ۱۵۰۰) دقیق است.
 *
 * فرمول ۱۲۸ساله‌ای که اول نوشتم برای ۱۴۰۳ جواب اشتباه می‌داد — و
 * ۱۴۰۳ کبیسه است. تست با تاریخ‌های واقعی همان اول لوش داد.
 */
const LEAP_IN_CYCLE = new Set([1, 5, 9, 13, 17, 22, 26, 30]);

function isLeap(jy) {
  return LEAP_IN_CYCLE.has(((jy % 33) + 33) % 33);
}

/** شمار روزهای هر ماه شمسی. */
function monthLen(jy, jm) {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return isLeap(jy) ? 30 : 29;
}

//: مبدأ: اول فروردین ۱۴۰۰ برابر است با ۲۱ مارس ۲۰۲۱.
//
// از یک نقطه‌ی نزدیک می‌شماریم، نه از سال ۱. شمردن از سال ۱ یعنی
// هر خطای کوچک در قاعده‌ی کبیسه، روی ۱۴۰۰ سال انباشته می‌شود و
// نتیجه چند روز جابه‌جا درمی‌آید.
const ANCHOR_JY = 1400;
const ANCHOR_DAY = Math.floor(Date.UTC(2021, 2, 21) / 86400000);

/** شمار روزهای یک سال شمسی. */
const yearLen = (jy) => (isLeap(jy) ? 366 : 365);

/** روزِ مطلق اول فروردین یک سال شمسی. */
function nowruzDay(jy) {
  let d = ANCHOR_DAY;
  if (jy >= ANCHOR_JY) {
    for (let y = ANCHOR_JY; y < jy; y++) d += yearLen(y);
  } else {
    for (let y = jy; y < ANCHOR_JY; y++) d -= yearLen(y);
  }
  return d;
}

/** میلادی → شمسی. ورودی: سال، ماه (۱ تا ۱۲)، روز. */
export function toJalali(gy, gm, gd) {
  const abs = Math.floor(Date.UTC(gy, gm - 1, gd) / 86400000);

  // سال را با تخمین شروع می‌کنیم و بعد تصحیح — دو حلقه‌ی کوتاه،
  // نه هزار بار تکرار
  let jy = gy - 621;
  while (nowruzDay(jy) > abs) jy--;
  while (nowruzDay(jy + 1) <= abs) jy++;

  let n = abs - nowruzDay(jy);
  let jm = 1;
  while (jm <= 12) {
    const len = monthLen(jy, jm);
    if (n < len) break;
    n -= len;
    jm++;
  }
  return { jy, jm, jd: n + 1 };
}

/** شمسی → میلادی، به شکل Date. */
export function toGregorian(jy, jm, jd) {
  let n = nowruzDay(jy);
  for (let m = 1; m < jm; m++) n += monthLen(jy, m);
  n += jd - 1;
  return new Date(n * 86400000);
}

/** «۲۰۲۴-۰۹-۲۲» → «۱ مهر ۱۴۰۳» */
export function isoToJalaliLabel(iso) {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
  if (!m) return String(iso);
  // سالِ زیرِ ۱۷۰۰ یعنی رشته خودش شمسی است. دوباره تبدیل‌کردنش «۲۵ دی ۷۸۳»
  // می‌ساخت — همان چیزی که داده‌ی ساختگیِ کدهای تخفیف نشان داد. تاریخِ
  // شمسی همان‌طور که هست نشان داده می‌شود، نه اینکه خرابش کنیم.
  if (+m[1] < 1700) return `${fa(+m[3])} ${MONTHS[+m[2] - 1] || ""} ${fa(+m[1])}`;
  const { jy, jm, jd } = toJalali(+m[1], +m[2], +m[3]);
  return `${fa(jd)} ${MONTHS[jm - 1]} ${fa(jy)}`;
}

/**
 * «2026-09-22 12:30» یا «2026-09-22T12:30:05» → «۳۱ شهریور ۱۴۰۵، ۱۲:۳۰»
 *
 * فقط تقویم عوض می‌شود، نه منطقه‌ی زمانی — ساعت همان است که رشته
 * می‌گوید، دقیقاً مثلِ قبل که خامِ `slice(0, 16)` نشان داده می‌شد.
 * بی‌ساعت، همان isoToJalaliLabel.
 */
export function isoToJalaliStamp(iso) {
  if (!iso) return "";
  // رشته‌ای که ISO نیست (مثلاً خطِ لاگِ sshd) همان‌طور می‌ماند —
  // وگرنه ساعتش دو بار چسبانده می‌شد
  if (!/^\d{4}-\d{2}-\d{2}/.test(String(iso))) return String(iso);
  const day = isoToJalaliLabel(iso);
  const t = /[T ](\d{2}):(\d{2})/.exec(String(iso));
  return t ? `${day}، ${fa(t[1])}:${fa(t[2])}` : day;
}

function isoOf(d) {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`
       + `-${String(d.getUTCDate()).padStart(2, "0")}`;
}

/**
 * فیلد تاریخ شمسی.
 *
 * value و onChange هر دو با رشته‌ی میلادی ISO کار می‌کنند — دقیقاً
 * همان چیزی که بک‌اند می‌خواهد. فقط آنچه کاربر می‌بیند شمسی است.
 */
export function JalaliDate({ value, onChange, placeholder = "انتخاب تاریخ" }) {
  const today = new Date();
  const tj = toJalali(today.getFullYear(), today.getMonth() + 1, today.getDate());

  const [open, setOpen] = useState(false);
  const [view, setView] = useState({ y: tj.jy, m: tj.jm });
  const box = useRef(null);
  const btn = useRef(null);
  const panel = useRef(null);
  const [pos, setPos] = useState(null);

  // تقویم با position:fixed و از راه portal روی body می‌نشیند.
  //
  // اول absolute بود و رو به پایین باز می‌شد؛ وقتی فیلد پایین یک
  // کارت بود نصفش زیر لبه می‌رفت. با fixed آن حل شد — ولی یک مشکل
  // بدتر جایش آمد:
  //
  // .fx-anim که کل صفحه را در بر می‌گیرد انیمیشنی با transform دارد
  // و fill-mode آن both است، یعنی transform بعد از تمام‌شدن هم روی
  // عنصر می‌ماند. هر transformِ غیر none یک containing block برای
  // فرزندانِ fixed می‌سازد. پس تقویم نسبت به *آن* جا می‌گرفت، در
  // حالی که مختصاتش از getBoundingClientRect می‌آمد که نسبت به
  // صفحه است. نتیجه: تقویم جایی بیرون از دید می‌افتاد و کاربر فکر
  // می‌کرد اصلاً باز نمی‌شود.
  //
  // portal آن را مستقیم زیر body می‌گذارد، بیرون از هر والدِ
  // transform‌دار. این تنها راهی است که در هر صفحه‌ای کار می‌کند،
  // چون نمی‌شود تضمین کرد هیچ والدی transform ندارد.
  const place = () => {
    const el = btn.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const W = 280;
    const H = 330;                      // تقریبِ ارتفاع تقویم
    const gap = 6;
    const below = window.innerHeight - r.bottom;
    const up = below < H && r.top > below;
    // راست‌چین: لبه‌ی راست تقویم روی لبه‌ی راست فیلد
    let left = r.right - W;
    left = Math.max(8, Math.min(left, window.innerWidth - W - 8));
    const top = up ? Math.max(8, r.top - gap - H) : r.bottom + gap;
    setPos({ left, top, maxHeight: up ? r.top - gap - 8 : below - gap - 8 });
  };

  useEffect(() => {
    if (!open) return undefined;
    place();
    const again = () => place();
    window.addEventListener("resize", again);
    // scroll در حالت capture: هر والدِ اسکرول‌شونده هم شنیده می‌شود
    window.addEventListener("scroll", again, true);
    return () => {
      window.removeEventListener("resize", again);
      window.removeEventListener("scroll", again, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // وقتی مقدار بیرونی عوض شد، تقویم روی همان ماه باز شود
  useEffect(() => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ""));
    if (m) {
      const j = toJalali(+m[1], +m[2], +m[3]);
      setView({ y: j.jy, m: j.jm });
    }
  }, [value]);

  // کلیک بیرون و Escape می‌بندند — بدون این، تقویم روی صفحه گیر می‌کند
  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      // پنل با portal بیرون از box رندر می‌شود، پس دیگر فرزندِ آن
      // نیست و contains تنهایی کافی نیست — بدون این، هر کلیکی روی
      // خود تقویم می‌بستش.
      const inBox = box.current && box.current.contains(e.target);
      const inPanel = panel.current && panel.current.contains(e.target);
      if (!inBox && !inPanel) setOpen(false);
    };
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const sel = (() => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ""));
    return m ? toJalali(+m[1], +m[2], +m[3]) : null;
  })();

  const step = (delta) => {
    let { y, m } = view;
    m += delta;
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1; y += 1; }
    setView({ y, m });
  };

  const pick = (d) => {
    onChange(isoOf(toGregorian(view.y, view.m, d)));
    setOpen(false);
  };

  // شنبه اول هفته است؛ getUTCDay شنبه را ۶ می‌دهد
  const first = toGregorian(view.y, view.m, 1);
  const lead = (first.getUTCDay() + 1) % 7;
  const len = monthLen(view.y, view.m);

  return (
    <div ref={box} style={{ position: "relative" }}>
      <button ref={btn} type="button" onClick={() => setOpen(!open)}
        className="fx-input flex items-center justify-between gap-2"
        style={{ width: "100%", textAlign: "right", cursor: "pointer" }}>
        <span style={{ color: value ? "var(--text)" : "var(--muted)" }}>
          {value ? isoToJalaliLabel(value) : placeholder}
        </span>
        <span className="flex items-center gap-1.5">
          {value && (
            <X size={14} style={{ color: "var(--muted)" }}
              onClick={(e) => { e.stopPropagation(); onChange(""); }} />
          )}
          <Calendar size={15} style={{ color: "var(--muted)" }} />
        </span>
      </button>

      {open && pos && createPortal(
        <div ref={panel} className="fx-card p-3" style={{
          position: "fixed", left: pos.left, top: pos.top,
          zIndex: 3000, width: 280,
          maxHeight: Math.max(220, pos.maxHeight),
          overflowY: "auto",
          boxShadow: "0 18px 44px -14px var(--scrim-3)",
        }}>
          <div className="flex items-center justify-between mb-2">
            <button type="button" onClick={() => step(-1)}
              className="fx-ico-btn" style={{ width: 28, height: 28 }}
              aria-label="ماه قبل"><ChevronRight size={15} /></button>
            <span className="text-[14px] font-semibold text-white">
              {MONTHS[view.m - 1]} {fa(view.y)}
            </span>
            <button type="button" onClick={() => step(1)}
              className="fx-ico-btn" style={{ width: 28, height: 28 }}
              aria-label="ماه بعد"><ChevronLeft size={15} /></button>
          </div>

          <div className="grid grid-cols-7 gap-1 mb-1">
            {WEEK.map((w, i) => (
              <div key={i} className="text-center text-[11px] py-1"
                style={{ color: "var(--muted)" }}>{w}</div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-1">
            {Array.from({ length: lead }).map((_, i) => <div key={`e${i}`} />)}
            {Array.from({ length: len }).map((_, i) => {
              const d = i + 1;
              const on = sel && sel.jy === view.y && sel.jm === view.m
                         && sel.jd === d;
              const now = tj.jy === view.y && tj.jm === view.m && tj.jd === d;
              return (
                <button key={d} type="button" onClick={() => pick(d)}
                  className="rounded-lg text-[13px] py-1.5 transition-all"
                  style={{
                    background: on ? "var(--accent)" : "transparent",
                    color: on ? "#fff" : now ? "var(--accent-2)" : "var(--dim)",
                    border: now && !on ? "1px solid var(--accent-2)"
                                       : "1px solid transparent",
                  }}>{fa(d)}</button>
              );
            })}
          </div>

          <div className="flex gap-2 mt-3">
            <button type="button" className="fx-btn-g flex-1 py-2 text-[12px]"
              onClick={() => { setView({ y: tj.jy, m: tj.jm }); pick(tj.jd); }}>
              امروز
            </button>
            <button type="button" className="fx-btn-g flex-1 py-2 text-[12px]"
              onClick={() => setOpen(false)}>بستن</button>
          </div>
        </div>,
        document.body)}
    </div>
  );
}
