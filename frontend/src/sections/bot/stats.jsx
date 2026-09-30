/**
 * ربات: گزارش فروش. (Funnel and trial stats are Pro: src/pro/insights.jsx.)
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useCallback, useState, useEffect } from "react";
import {
  FileText, Download, RefreshCw, TrendingUp, Users,
} from "lucide-react";
import { API_URL } from "../../lib/constants";
import { errMsg, errText, esc0, faNum, okJson } from "../../lib/format";
import { AreaChart, Avatar, CountUp, EmptyState, LoadError, PageSkeleton, SectionHead, Segmented, StatTile } from "../../ui/index";
import { isoToJalaliLabel } from "../../ui/jalali";

export const REPORT_RANGES = [[7, "۷ روز"], [30, "۳۰ روز"], [90, "۹۰ روز"], [365, "یک سال"]];

/**
 * گزارش فروش ربات.
 *
 * حسابداری می‌گوید از هر واسطه چقدر طلب دارید؛ این می‌گوید فروش
 * مستقیم ربات در یک دوره چه شکلی بوده — چند نفر آمدند، چند درصدشان
 * خریدند، و چه کسانی بیشترین سهم را داشتند.
 */
export function BotReportSection({ password }) {
  const [days, setDays] = useState(30);
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch(`${API_URL}/api/admin/bot/users/report?days=${days}`, {
      headers: { "X-Admin-Password": password },
    }).then((r) => okJson(r))
      .then((j) => { if (alive) { setD(j); setLoading(false); } })
      .catch((e) => { if (alive) { setD({ ready: false, error: errMsg(e) }); setLoading(false); } });
    return () => { alive = false; };
  }, [password, days]);

  const [busy, setBusy] = useState(false);

  /**
   * دانلود فایل از یک مسیر محافظت‌شده.
   *
   * نسخه‌ی قبلی آدرس را مستقیم در <a href> می‌گذاشت. مرورگر در آن
   * حالت هیچ هدری نمی‌فرستد، پس سرور ۴۰۱ می‌داد و کاربر یک فایل
   * خطا دانلود می‌کرد بدون اینکه بفهمد چرا. پس fetch می‌کنیم و
   * blob را دانلود می‌دهیم.
   */
  const grab = async (path, filename) => {
    setBusy(true);
    try {
      const res = await fetch(`${API_URL}${path}`, {
        headers: { "X-Admin-Password": password },
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        alert(errText(j.detail, "ساخت فایل ناموفق بود"));
        return;
      }
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      setTimeout((h) => URL.revokeObjectURL(h), 2000, a.href);
    } catch {
      alert("اتصال به سرور برقرار نشد");
    } finally { setBusy(false); }
  };

  const today = new Date().toISOString().slice(0, 10);
  const download = () => grab("/api/admin/bot/users/export",
                              `nexora-users-${today}.csv`);
  const downloadPdf = () => grab(
    `/api/admin/bot/users/report/pdf?days=${days}`,
    `nexora-bot-report-${days}d-${today}.pdf`);

  if (loading) return <PageSkeleton />;

  if (!d?.ready) {
    return (
      <div className="fx-anim">
        <SectionHead title="گزارش فروش" desc="خلاصه‌ی عملکرد ربات در یک بازه." />
        <div className="fx-card p-5">
          <p className="text-[13px]" style={{ color: "var(--dim)" }}>
            {d?.error || "دیتابیس ربات در دسترس نیست."}
          </p>
        </div>
      </div>
    );
  }

  const o = d.orders || {};
  const u = d.users || {};
  const s = d.subs || {};
  const maxDay = Math.max(...(d.daily || []).map((x) => x.sum), 1);
  // میانگین بدون روزهای صفر: روزهای بی‌فروش میانگین را مصنوعی
  // پایین می‌آورند و خط مرجع بی‌معنا می‌شود.
  const sold = (d.daily || []).filter((x) => x.sum > 0);
  const avgDay = sold.length
    ? sold.reduce((a, b) => a + b.sum, 0) / sold.length : 0;

  return (
    <div className="fx-anim">
      <SectionHead title="گزارش فروش"
        desc="عملکرد ربات در بازه‌ی انتخابی — چند نفر آمدند، چند نفر خریدند، چقدر فروش رفت."
        action={
          <div className="flex items-center gap-2 flex-wrap">
            <Segmented value={days} onChange={setDays}
              items={REPORT_RANGES.map(([v, l]) => [v, l])} />
            <button onClick={downloadPdf} disabled={busy}
              className="fx-btn px-3 py-2.5 text-[13px] flex items-center gap-1.5">
              <FileText size={13} /> گزارش PDF
            </button>
            <button onClick={download} disabled={busy}
              className="fx-btn-g px-3 py-2.5 text-[13px] flex items-center gap-1.5">
              <Download size={13} /> خروجی اکسل
            </button>
          </div>
        } />

      <div className="fx-g4 grid grid-cols-4 gap-3 mb-4">
        <StatTile label="فروش دوره" value={faNum(o.revenue || 0)} unit="تومان"
          color="var(--ok)"
          hint={o.approved ? `${faNum(o.approved)} سفارش · میانگین ${faNum(o.avg)}` : "سفارشی نبوده"} />
        <StatTile label="کاربر جدید" value={faNum(u.newUsers || 0)} unit="نفر"
          hint={`از ${faNum(u.users || 0)} کاربر کل`} />
        <StatTile label="خریدار" value={faNum(d.buyerCount || 0)} unit="نفر"
          color="var(--accent-2)"
          hint={d.conversion !== null && d.conversion !== undefined
            ? `نرخ تبدیل ${faNum(d.conversion)}٪ از کاربران جدید`
            : "کاربر جدیدی نبوده"} />
        <StatTile label="اشتراک فعال" value={faNum(s.active || 0)}
          color={s.expiringSoon ? "var(--warn)" : "var(--text)"}
          hint={s.expiringSoon
            ? `${faNum(s.expiringSoon)} تا کمتر از ۳ روز اعتبار دارد`
            : `از ${faNum(s.total || 0)} اشتراک کل`} />
      </div>

      {(o.pending > 0 || o.rejected > 0) && (
        <div className="fx-card p-5 mb-4">
          <div className="flex gap-4 flex-wrap text-[13px]">
            {o.pending > 0 && (
              <span style={{ color: "var(--warn)" }}>
                ⏳ <b>{faNum(o.pending)}</b> رسید منتظر بررسی شماست
              </span>
            )}
            {o.rejected > 0 && (
              <span style={{ color: "var(--muted)" }}>
                {faNum(o.rejected)} سفارش در این دوره رد شده
              </span>
            )}
          </div>
        </div>
      )}

      {(d.daily || []).length > 1 && (
        <div className="fx-card p-5 mb-4">
          <div className="text-[14px] font-semibold text-white mb-3 flex items-center gap-2">
            <TrendingUp size={15} style={{ color: "var(--accent-2)" }} /> فروش روزانه
          </div>
          <AreaChart
            data={d.daily.map((x) => x.sum)}
            color="var(--accent-2)"
            height={110}
            label={`${isoToJalaliLabel(d.daily[0].day)} تا ${isoToJalaliLabel(d.daily[d.daily.length - 1].day)}`}
            format={(v) => `${faNum(v)} تومان`} labels={d.daily.map((x) => x.day)} />
        </div>
      )}

      <div className="fx-card p-5">
        <div className="flex items-center justify-between gap-3 mb-1 flex-wrap">
          <div className="text-[14px] font-semibold text-white flex items-center gap-2">
            <Users size={15} style={{ color: "var(--accent-2)" }} /> بهترین خریداران
          </div>
          <span className="text-[13px]" style={{ color: "var(--muted)" }}>
            {faNum(u.withPhone || 0)} کاربر شماره تماس داده‌اند
          </span>
        </div>
        <p className="text-[13px] mb-3" style={{ color: "var(--muted)" }}>
          مرتب بر اساس مجموع خرید در همین دوره.
        </p>

        {!(d.buyers || []).length ? (
          <EmptyState icon={Users} text="در این بازه خریدی ثبت نشده" />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="fx-table">
              <thead>
                <tr><th>کاربر</th><th>شماره تماس</th><th>سفارش</th>
                  <th>مجموع خرید</th><th>آخرین خرید</th></tr>
              </thead>
              <tbody>
                {(d.buyers || []).map((b) => (
                  <tr key={b.tg_id}>
                    <td>
                      <span className="inline-flex items-center gap-2 align-middle">
                        <Avatar name={b.first_name || b.username} id={b.tg_id} size={24} />
                        <span>{esc0(b.first_name) || "—"}</span>
                      </span>
                      {b.username && (
                        <span dir="ltr" className="mr-2" style={{ color: "var(--muted)", fontFamily: "var(--mono)" }}>
                          @{b.username}
                        </span>
                      )}
                    </td>
                    <td dir="ltr" style={{ fontFamily: "var(--mono)", color: b.phone ? "var(--dim)" : "var(--muted)" }}>
                      {b.phone || "—"}
                    </td>
                    <td style={{ fontFamily: "var(--mono)" }}>{faNum(b.orders)}</td>
                    <td style={{ fontFamily: "var(--mono)", color: "var(--ok)" }}>
                      {faNum(b.spent)}
                    </td>
                    <td style={{ color: "var(--muted)" }}>{isoToJalaliLabel(b.lastBuy)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
