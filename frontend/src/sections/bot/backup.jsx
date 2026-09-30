/**
 * ربات: پشتیبان‌گیری.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect } from "react";
import {
  Download, Loader2, Upload,
} from "lucide-react";
import { errMsg, errText, faNum, okJson } from "../../lib/format";
import { API_URL } from "../../lib/constants";
import { ConfirmModal, InfoBox, Msg, SectionHead } from "../../ui/index";

export function BotBackupSection({ password }) {
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const [confirm, setConfirm] = useState(null);
  useEffect(() => { if (msg) { const t = setTimeout(() => setMsg(null), 5000); return () => clearTimeout(t); } }, [msg]);

  const download = async () => {
    setBusy("dl");
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/backup`, {
        headers: { "X-Admin-Password": password } });
      const d = await res.json();
      if (!res.ok) { setMsg({ t: "err", m: errText(d.detail, "دریافت ناموفق") }); return; }

      const blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `nexora-bot-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      // لغوِ فوری، دانلود را در بعضی مرورگرها (فایرفاکس) پیش از شروع می‌بُرد
      const href = a.href;
      setTimeout(() => URL.revokeObjectURL(href), 2000);
      const total = Object.values(d.counts || {}).reduce((x, y) => x + y, 0);
      setMsg({ t: "ok", m: `بک‌آپ دانلود شد — ${total} رکورد` });
    } catch { setMsg({ t: "err", m: "اتصال برقرار نشد" }); }
    finally { setBusy(null); }
  };

  const pickFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => {
      try {
        const parsed = JSON.parse(r.result);
        if (!parsed.data) { setMsg({ t: "err", m: "این فایل بک‌آپ ربات نیست" }); return; }
        setConfirm(parsed);
      } catch { setMsg({ t: "err", m: "فایل خراب است" }); }
    };
    r.readAsText(f);
    e.target.value = "";
  };

  const restore = async () => {
    const payload = confirm;
    setConfirm(null); setBusy("up");
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify({ data: payload.data }),
      });
      const d = await okJson(res, "بازیابی ناموفق");
      const total = faNum(Object.values(d.restored || {}).reduce((x, y) => x + y, 0));
      const safety = d.safetyWarning ? ` — ${d.safetyWarning}` : "";
      // بازگردانیِ نصفه نباید مثل بازگردانیِ سالم به نظر برسد
      if (d.warning) setMsg({ t: "err", m: `${total} رکورد بازیابی شد، ولی ${d.warning}${safety}` });
      else setMsg({ t: safety ? "err" : "ok", m: `${total} رکورد بازیابی شد${safety}` });
    } catch (e) { setMsg({ t: "err", m: errMsg(e) }); }
    finally { setBusy(null); }
  };

  return (
    <div className="fx-anim">
      <SectionHead title="بک‌آپ و بازیابی ربات"
        desc="کاربران، سفارش‌ها، اشتراک‌ها، سکه‌ها و تنظیمات ربات." />
      <Msg msg={msg} />

      <div className="fx-g2 grid grid-cols-2 gap-4 mb-4">
        <button onClick={download} disabled={!!busy} className="fx-card p-6 text-center">
          <div className="fx-ico mx-auto mb-3" style={{ width: 44, height: 44, background: "var(--accent-soft)" }}>
            {busy === "dl" ? <Loader2 size={20} className="animate-spin" style={{ color: "var(--accent-2)" }} />
                           : <Download size={20} style={{ color: "var(--accent-2)" }} />}
          </div>
          <div className="text-[14px] font-semibold text-white mb-1">دریافت بک‌آپ</div>
          <div className="text-[13px]" style={{ color: "var(--muted)" }}>یک فایل JSON دانلود می‌شود</div>
        </button>

        <label className="fx-card p-6 text-center cursor-pointer">
          <div className="fx-ico mx-auto mb-3" style={{ width: 44, height: 44, background: "var(--warn-soft)" }}>
            {busy === "up" ? <Loader2 size={20} className="animate-spin" style={{ color: "var(--warn)" }} />
                           : <Upload size={20} style={{ color: "var(--warn)" }} />}
          </div>
          <div className="text-[14px] font-semibold text-white mb-1">بازیابی از فایل</div>
          <div className="text-[13px]" style={{ color: "var(--muted)" }}>فایل بک‌آپ را انتخاب کنید</div>
          <input type="file" accept=".json" onChange={pickFile} className="hidden" disabled={!!busy} />
        </label>
      </div>

      <InfoBox tone="warn">
        بازیابی، <b>همه‌ی داده‌های فعلی ربات را جایگزین می‌کند</b>.
        قبل از آن یک نسخه‌ی امن از وضعیت فعلی کنار دیتابیس ذخیره می‌شود،
        پس اگر اشتباه شد چیزی از دست نمی‌رود.
      </InfoBox>

      {confirm && (
        <ConfirmModal
          title="بازیابی بک‌آپ؟"
          desc={`این فایل شامل ${Object.entries(confirm.counts || {}).map(([k, v]) => `${v} ${k}`).join(" · ")} است. همه‌ی داده‌های فعلی ربات جایگزین می‌شوند.`}
          confirmLabel="بازیابی کن"
          onConfirm={restore}
          onCancel={() => setConfirm(null)} />
      )}
    </div>
  );
}
