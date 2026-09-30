/**
 * ربات: رویدادها.
 *
 * برگه‌اش: docs/specs/2026-09-22-bot-events.md
 *
 * جدولِ `events` از قبل در `bot/db.py` بود، دو جا نوشته می‌شد
 * (`provision` و `signup`) و **هیچ‌جا خوانده نمی‌شد** — نه کوئری،
 * نه مسیر API، نه صفحه. تانل‌ها صفحه‌ی «رویدادها» داشتند و ربات
 * نداشت، پس هفده جای شکستِ ربات فقط به `journalctl` می‌رفتند.
 *
 * نگاشتِ «نوع → برچسب و شدت» این‌جا دوباره نوشته نمی‌شود: با
 * `kinds` از بک‌اند می‌آید، که خودش از `bot/events.py` می‌خواند —
 * همان فایلی که پیامِ گروهِ مدیریت هم از آن ساخته می‌شود. دو
 * نسخه‌ی این نگاشت یعنی روزی چیپِ این صفحه یک چیز بگوید و پیامِ
 * تلگرام چیزِ دیگری.
 *
 * صفحه‌بندی شماره‌دار است، نه «نمایش بیشتر» — قاعده‌ی مخزن، و
 * `test-ui-safety.py` اجرایش می‌کند.
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  AlertTriangle, Bell, CheckCircle2, Clock, Info, RefreshCw, User,
} from "lucide-react";

import { adminSrc } from "../../lib/botsrc";
import { faNum } from "../../lib/format";
import { isoToJalaliStamp } from "../../ui/jalali";
import {
  EmptyState, InfoBox, Msg, Pager, PageSkeleton, SectionHead, Toggle,
} from "../../ui/index";

const PER = 30;

//: شدت → توکنِ رنگ. پنج پله‌ی مخزن؛ هیچ `rgba()` خامی این‌جا
//: نوشته نمی‌شود و `test-ui-safety` هم رد می‌کند و هم توکنِ
//: تعریف‌نشده را می‌گیرد — که بی‌صدا شفاف می‌شود.
const TONE = {
  error: {
    fg: "var(--danger)", bg: "var(--danger-soft)",
    line: "var(--danger-line)", wash: "var(--danger-wash)",
    Icon: AlertTriangle,
  },
  warn: {
    fg: "var(--warn)", bg: "var(--warn-soft)",
    line: "var(--warn-line)", wash: "var(--warn-wash)",
    Icon: AlertTriangle,
  },
  ok: {
    fg: "var(--ok)", bg: "var(--ok-soft)",
    line: "var(--ok-line)", wash: "transparent",
    Icon: CheckCircle2,
  },
  info: {
    fg: "var(--muted)", bg: "var(--hair-2)",
    line: "var(--hair-3)", wash: "transparent",
    Icon: Info,
  },
};

const tone = (level) => TONE[level] || TONE.info;

/* `src` خالی یعنی پنلِ مالک؛ پرتالِ نماینده `portalSrc` می‌دهد. */
export function BotEventsSection({ password, src }) {
  const S = useMemo(() => src || adminSrc(password), [src, password]);
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(true);
  const [msg, setMsg] = useState(null);
  const [page, setPage] = useState(1);
  const [onlyErrors, setOnlyErrors] = useState(false);

  const load = useCallback(async () => {
    setBusy(true); setMsg(null);
    try {
      // پرس‌وجو بیرونِ قالبِ مسیر می‌چسبد، وگرنه تستِ درز یک
      // قطعه‌ی جعلی می‌بیند و مسیر را ناموجود می‌خواند
      const q = `page=${page}&per=${PER}&errors=${onlyErrors ? 1 : 0}`;
      setD(await S.events(q));
    } catch (e) {
      setMsg({ t: "err", m: e.message });
    } finally {
      setBusy(false);
    }
  }, [S, page, onlyErrors]);

  useEffect(() => { load(); }, [load]);

  if (busy && !d) return <PageSkeleton cards={2} rows={8} />;

  const rows = d?.events || [];
  const kinds = d?.kinds || {};
  const total = d?.total || 0;
  const pages = Math.max(1, Math.ceil(total / PER));

  // چند نوع اصلاً گروه را خبر می‌کنند — مالک باید بداند کدام‌ها،
  // وگرنه سکوتِ تلگرام را «پس مشکلی نبوده» می‌خواند
  const alerting = Object.values(kinds).filter((k) => k.alert).length;

  return (
    <div>
      <SectionHead
        title="رویدادهای ربات"
        desc="چه چیزی شکست، کِی، و برای چه کسی — بدون نیاز به لاگِ سرور"
        action={
          <button
            className="fx-btn-g px-3 py-1.5 text-[13px] flex items-center gap-1.5"
            onClick={load} disabled={busy}>
            <RefreshCw size={14} className={busy ? "animate-spin" : ""} />
            تازه‌سازی
          </button>
        }
      />

      <Msg msg={msg} />

      {d && d.ready === false ? (
        <InfoBox tone="warn">
          {d.message || "ربات هنوز راه‌اندازی نشده است"}
        </InfoBox>
      ) : (
        <>
          <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
            {/* `Toggle` برچسب را فقط `aria-label` می‌کند و چیزی
                نشان نمی‌دهد، و `onChange` رویداد را پاس می‌دهد نه
                مقدار را. نسخه‌ی اولِ این صفحه `(v) => setOnlyErrors(v)`
                داشت — یعنی کلیدی که روشن می‌شد و **هرگز خاموش نه**،
                چون شیء رویداد همیشه truthy است. با کلیک دوم در
                مرورگر همین دیده شد. */}
            <label className="flex items-center gap-2 cursor-pointer text-[13px]"
              style={{ color: "var(--dim)" }}>
              <Toggle
                label="فقط خطاها"
                checked={onlyErrors}
                onChange={() => { setOnlyErrors(!onlyErrors); setPage(1); }}
              />
              فقط خطاها
            </label>
            {alerting > 0 ? (
              <span className="text-[12px] flex items-center gap-1.5"
                style={{ color: "var(--muted)" }}>
                <Bell size={13} />
                {faNum(alerting)} نوع از اینها همان لحظه در گروهِ مدیریت هم
                خبر می‌دهند
              </span>
            ) : null}
          </div>

          {!rows.length ? (
            <EmptyState
              icon={Clock}
              text={onlyErrors ? "هیچ خطایی ثبت نشده" : "هنوز رویدادی ثبت نشده"}
              hint={onlyErrors
                ? "یعنی هیچ‌کدام از کارهای ربات شکست نخورده — یا هنوز چیزی ثبت نشده است."
                : "هر بار ربات کانفیگ بسازد، تمدید کند، یا کاری از دستش برنیاید، این‌جا یک ردیف می‌نشیند."}
            />
          ) : (
            <>
              <div className="fx-card overflow-hidden">
                {rows.map((e, i) => {
                  const t = tone(e.level);
                  const Icon = t.Icon;
                  return (
                    <div key={e.id}
                      className="flex items-start gap-3 px-3 py-2.5"
                      style={{
                        background: t.wash,
                        borderBottom: i < rows.length - 1
                          ? "1px solid var(--hair-1)" : "none",
                      }}>
                      <span
                        className="shrink-0 mt-0.5 flex items-center justify-center"
                        style={{
                          width: 26, height: 26, borderRadius: 8,
                          background: t.bg, color: t.fg,
                          border: `1px solid ${t.line}`,
                        }}>
                        <Icon size={14} />
                      </span>

                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] leading-6"
                          style={{ color: "var(--dim)" }}>
                          {e.text}
                        </div>
                        <div
                          className="flex items-center gap-3 flex-wrap text-[11px] mt-0.5"
                          style={{ color: "var(--muted)" }}>
                          <span>{e.at ? isoToJalaliStamp(e.at) : "—"}</span>
                          {e.name || e.tgId ? (
                            <span className="flex items-center gap-1">
                              <User size={11} />
                              {e.name || "بی‌نام"}
                              {/* شناسه عدد نیست: با faNum جداکننده‌ی
                                  هزارگان می‌گرفت — «۱۸۴٬۹۲۳٬۷۷۱» —
                                  و کپی‌کردنش هم بی‌فایده می‌شد */}
                              {e.tgId ? (
                                <span dir="ltr" className="fx-idnum"
                                  title="شناسه تلگرام">{e.tgId}</span>
                              ) : null}
                            </span>
                          ) : null}
                          {kinds[e.kind]?.alert ? (
                            <span className="flex items-center gap-1"
                              style={{ color: "var(--warn)" }}>
                              <Bell size={11} />
                              در گروه هم خبر داده شد
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <Pager page={page} pages={pages} total={total} perPage={PER}
                onPage={setPage} />
            </>
          )}
        </>
      )}
    </div>
  );
}
