/**
 * زنگِ اعلان — «چه کسی منتظرِ من است، و از کِی».
 *
 * چرا ساخته شد: نشانِ کنارِ منو می‌گفت «۲ رسید»، ولی نمی‌گفت کی
 * فرستاده و چقدر معطل مانده. مالک باید صفحه‌ی سفارش‌ها را باز
 * می‌کرد تا بفهمد کدامش دو ساعت است که جواب نگرفته — و همان دو
 * ساعت، همان چیزی است که مشتری از آن ناراضی می‌شود.
 *
 * ترتیب از قدیمی‌ترین است، نه تازه‌ترین: چیزی که بیشتر منتظر
 * مانده بالاتر می‌آید، چون همان دارد دیر می‌شود.
 */
import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bell, CreditCard, MessageCircle, Image } from "lucide-react";

import { faNum, toFaDigits } from "../lib/format";

/** «۲ ساعت و ۵ دقیقه» — نه «۱۲۵ دقیقه»، که باید حسابش کرد. */
export function waited(min) {
  const m = Math.max(0, Math.round(Number(min) || 0));
  if (m < 1) return "همین حالا";
  if (m < 60) return `${faNum(m)} دقیقه`;
  const h = Math.floor(m / 60);
  if (h < 24) {
    const r = m % 60;
    return r ? `${faNum(h)} ساعت و ${faNum(r)} دقیقه` : `${faNum(h)} ساعت`;
  }
  const d = Math.floor(h / 24);
  const rh = h % 24;
  return rh ? `${faNum(d)} روز و ${faNum(rh)} ساعت` : `${faNum(d)} روز`;
}

/** از چه ساعتی دیر است. یک ساعت معطلی هنوز عادی است؛ سه ساعت نه. */
const tone = (min) => (min >= 180 ? "bad" : min >= 60 ? "warn" : "");

export function AlertBell({ data, onGo }) {
  const [open, setOpen] = useState(false);
  const [box, setBox] = useState(null);
  const btnRef = useRef(null);

  const items = data?.items || [];
  const total = (data?.receipts || 0) + (data?.messages || 0);
  const oldest = data?.oldestMin || 0;

  // موقعیت را موقعِ بازشدن می‌گیریم: پنل روی body می‌نشیند (پرتال)،
  // چون هر چیزی با position: fixed داخل .fx-anim در آن حبس می‌شود
  useEffect(() => {
    if (!open) return undefined;
    const place = () => {
      const r = btnRef.current?.getBoundingClientRect();
      if (!r) return;
      // لبه‌ی راستِ پنل به لبه‌ی راستِ دکمه می‌چسبد — ولی چون در
      // چیدمانِ راست‌به‌چپ این دکمه سمتِ چپِ صفحه است، پنلِ ۳۶۰
      // پیکسلی از لبه بیرون می‌زد (چپش روی ‎−۷ می‌نشست). پس داخلِ
      // صفحه نگهش می‌داریم.
      const w = Math.min(360, window.innerWidth - 24);
      const want = window.innerWidth - r.right;
      const max = window.innerWidth - w - 12;
      setBox({ top: r.bottom + 8, right: Math.max(12, Math.min(want, max)) });
    };
    place();
    const close = (e) => {
      if (!btnRef.current?.contains(e.target)
          && !e.target.closest?.(".fx-bell-pop")) setOpen(false);
    };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const go = (it) => {
    setOpen(false);
    onGo?.(it.kind === "receipt" ? "bot-orders" : "bot-inbox", it);
  };

  return (
    <>
      <button ref={btnRef} className={`fx-bell ${total ? "on" : ""} ${tone(oldest)}`}
        onClick={() => setOpen((v) => !v)}
        title={total ? `${faNum(total)} مورد منتظر پاسخ` : "چیزی منتظر نیست"}
        aria-label="اعلان‌ها" aria-expanded={open}>
        <Bell size={16} />
        {total > 0 && (
          <span className="fx-bell-dot">{total > 99 ? "۹۹+" : faNum(total)}</span>
        )}
      </button>

      {open && box && createPortal(
        <div className="fx-bell-pop" style={{ top: box.top, right: box.right }}>
          <div className="fx-bell-head">
            <b>منتظرِ شما</b>
            {total > 0 && (
              <span className={tone(oldest)}>
                قدیمی‌ترین: {waited(oldest)}
              </span>
            )}
          </div>

          {!items.length ? (
            <div className="fx-bell-empty">
              <Bell size={22} />
              <p>چیزی منتظر پاسخ نیست</p>
              <span>رسید تازه و پیام خوانده‌نشده همین‌جا می‌آید.</span>
            </div>
          ) : (
            <div className="fx-bell-rows">
              {items.map((it) => (
                <button key={`${it.kind}-${it.id}`} className="fx-bell-row"
                  onClick={() => go(it)}>
                  <span className={`fx-bell-ic ${it.kind}`}>
                    {it.kind === "receipt" ? <CreditCard size={14} />
                                           : <MessageCircle size={14} />}
                  </span>
                  <span className="fx-bell-body">
                    <span className="fx-bell-top">
                      <b>{it.name}</b>
                      <i className={tone(it.waitedMin)}>{waited(it.waitedMin)}</i>
                    </span>
                    <span className="fx-bell-sub">
                      {it.kind === "receipt" ? (
                        <>
                          رسید سفارش <span dir="ltr">#{toFaDigits(it.id)}</span>
                          {it.amount ? ` · ${faNum(it.amount)} تومان` : ""}
                          {it.hasPhoto && <Image size={11} className="inline mr-1" />}
                        </>
                      ) : (
                        <>
                          {it.count > 1 && `${faNum(it.count)} پیام · `}
                          {it.body || "پیام تازه"}
                        </>
                      )}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>, document.body)}
    </>
  );
}

export default AlertBell;
