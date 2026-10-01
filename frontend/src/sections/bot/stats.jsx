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
import { AreaChart, Avatar, CountUp, EmptyState, LoadError, PageSkeleton, SectionHead, Segmented, StatStrip } from "../../ui/index";
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
  // Every day of the range, not only the days that sold: three sale days
  // drew three walls labelled "19 to 29 Shahrivar", and the empty days in
  // between, the ones worth seeing, were not on the chart at all.
  const byDay = Object.fromEntries((d.daily || []).map((x) => [x.day, x.sum]));
  const series = [];
  if ((d.daily || []).length) {
    const end = new Date();
    const span = Math.min(Number(days) || 30, 366);
    for (let i = span - 1; i >= 0; i--) {
      const t = new Date(end.getFullYear(), end.getMonth(), end.getDate() - i);
      const k = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
      series.push({ day: k, sum: byDay[k] || 0 });
    }
  }
  const maxDay = Math.max(...series.map((x) => x.sum), 1);
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

      {/* one strip, not four 148 px cards: the report is the chart and
          the buyers below, these four numbers only frame it */}
      <StatStrip items={[
        { label: "فروش دوره", value: `${faNum(o.revenue || 0)} تومان`, color: "var(--ok)",
          hint: o.approved ? `${faNum(o.approved)} سفارش · میانگین ${faNum(o.avg)}` : "سفارشی نبوده" },
        { label: "کاربر جدید", value: faNum(u.newUsers || 0), hint: `از ${faNum(u.users || 0)}` },
        { label: "خریدار", value: faNum(d.buyerCount || 0), color: "var(--accent-2)",
          hint: d.conversion !== null && d.conversion !== undefined ? `تبدیل ${faNum(d.conversion)}٪` : "" },
        { label: "اشتراک فعال", value: faNum(s.active || 0),
          color: s.expiringSoon ? "var(--warn)" : "var(--text)",
          hint: s.expiringSoon ? `${faNum(s.expiringSoon)} تا زیرِ ۳ روز` : `از ${faNum(s.total || 0)}` },
      ]} />

      {/* one line under the tiles, not a full-width card for one sentence */}
      {(o.pending > 0 || o.rejected > 0) && (
        <div className="mb-4 -mt-1 px-1">
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

      {series.length > 1 && (
        <div className="fx-card p-5 mb-4">
          <div className="text-[14px] font-semibold text-white mb-3 flex items-center gap-2">
            <TrendingUp size={15} style={{ color: "var(--accent-2)" }} /> فروش روزانه
          </div>
          <AreaChart
            data={series.map((x) => x.sum)}
            color="var(--accent-2)"
            height={110}
            label={`${isoToJalaliLabel(series[0].day)} تا ${isoToJalaliLabel(series[series.length - 1].day)}`}
            format={(v) => `${faNum(v)} تومان`} labels={series.map((x) => x.day)} />
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
