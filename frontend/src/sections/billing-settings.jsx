/**
 * Accounting settings that stay in the free core: where the x-ui database is,
 * and the backup and restore of the billing database. They hold the owner's
 * data, so a lapsed Pro license must never stop a backup or a restore.
 * The accounting screens themselves are Pro (frontend/src/pro/billing.jsx).
 *
 * Spec: docs/specs/2026-09-29-pro-split.md ("Accounting").
 */
import React, { useState, useEffect } from "react";
import { AlertTriangle, CheckCircle2, Database, Download, Loader2, Save, Upload } from "lucide-react";
import { API_URL } from "../lib/constants";
import { errMsg, faNum, okJson } from "../lib/format";
import { Field, InfoBox, LoadError, Msg, PageSkeleton, SectionHead } from "../ui/index";

export function BillingSettings({ password }) {
  const [info, setInfo] = useState(null);
  const [loadErr, setLoadErr] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const fileRef = React.useRef(null);

  // This used to read the whole config, change one key and send it all back.
  // If that read got a 500, `{detail}` was saved as the config; and with no
  // version, any concurrent change made elsewhere was silently wiped. Now
  // only this one path is read and written.
  const load = async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/billing/xui-path`,
        { headers: { "X-Admin-Password": password } });
      const i = await okJson(res, "خواندنِ مسیرِ x-ui ناموفق بود");
      setInfo(i);
      setPath(i.manual || "");
      setLoadErr("");
    } catch (e) { setLoadErr(errMsg(e)); }
  };
  useEffect(() => { load(); }, [password]);
  useEffect(() => { if (msg) { const t = setTimeout(() => setMsg(null), 4500); return () => clearTimeout(t); } }, [msg]);

  const savePath = async (p) => {
    setBusy("path");
    try {
      const res = await fetch(`${API_URL}/api/admin/billing/xui-path`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify({ path: p }),
      });
      await okJson(res, "ذخیره‌ی مسیر ناموفق بود");
      setMsg({ t: "ok", m: "مسیر ذخیره شد" });
      load();
    } catch (e) { setMsg({ t: "err", m: errMsg(e) }); }
    finally { setBusy(null); }
  };

  const backup = async () => {
    setBusy("backup");
    try {
      // This used to be an unchecked `r.json()`: an error answer was
      // downloaded as "the backup" with "downloaded: 0 payments, 0 groups".
      // The owner believed they had a backup.
      const d = await fetch(`${API_URL}/api/admin/billing/backup`, {
        headers: { "X-Admin-Password": password },
      }).then((r) => okJson(r, "گرفتنِ پشتیبان ناموفق بود"));
      const blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `nexora-billing-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      // Revoking at once cuts the download off before it starts in some browsers
      setTimeout((h) => URL.revokeObjectURL(h), 2000, a.href);
      setMsg({ t: "ok", m: `دانلود شد — ${d.counts?.payments || 0} پرداخت، ${d.counts?.group_config || 0} گروه` });
    } catch (e) { setMsg({ t: "err", m: `بک‌آپ ناموفق: ${errMsg(e)}` }); }
    finally { setBusy(null); }
  };

  const restore = async (file) => {
    setBusy("restore");
    // "Not a valid file" is for the file only; a network failure used to say it too
    let parsed;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      setMsg({ t: "err", m: "فایل معتبر نبود — JSONِ خوانا نیست" });
      setBusy(null); if (fileRef.current) fileRef.current.value = "";
      return;
    }
    try {
      const res = await fetch(`${API_URL}/api/admin/billing/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify({ data: parsed.data || parsed }),
      });
      const d = await okJson(res, "بازیابی ناموفق");
      // The backend says when the safety copy before the restore could not be
      // taken (there is no way back); this message used to stop short of the UI
      const safety = d.safetyWarning ? ` — ${d.safetyWarning}` : "";
      if (d.warning) {
        setMsg({ t: "err", m: `بازیابی ناقص بود — ${d.warning}${safety}` });
      } else {
        const n = Object.values(d.restored || {}).reduce((x, y) => x + y, 0);
        setMsg({ t: safety ? "err" : "ok", m: `بازیابی شد — ${faNum(n)} ردیف${safety}` });
      }
    } catch (e) { setMsg({ t: "err", m: errMsg(e) }); }
    finally { setBusy(null); if (fileRef.current) fileRef.current.value = ""; }
  };

  // A read error used to leave a skeleton forever (its message went away
  // after 4.5 seconds). Now only the path card gives way to the error; the
  // backup, which is needed exactly when something is broken, stays usable.
  if (!info && !loadErr) return <PageSkeleton />;

  return (
    <div className="fx-anim">
      <SectionHead title="تنظیمات و بک‌آپ"
        desc="مسیر دیتابیس ۳x-ui و پشتیبان‌گیری از نرخ‌ها و پرداخت‌ها." />

      {/* The whole-panel backup and its bot live on one page; this page's
          file holds accounting only (the owner looked for the full one here). */}
      <a href="#/bot-backup" className="fx-card p-4 flex items-center justify-between gap-3"
        style={{ textDecoration: "none" }}>
        <span className="text-[13px]" style={{ color: "var(--dim)" }}>
          <b className="text-white">پشتیبانِ کاملِ پنل و ربات مدیریت</b>
          {" "}· یک فایل برای همه‌چیز، و ارسالِ خودکار به تلگرام
        </span>
        <span className="text-[12.5px] shrink-0" style={{ color: "var(--accent-2)" }}>باز کن ›</span>
      </a>

      {msg && <Msg msg={msg} />}

      {!info ? (
        <div className="mb-4">
          <LoadError what="مسیرِ دیتابیسِ x-ui" err={loadErr} onRetry={load} />
        </div>
      ) : (
      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
          <Database size={15} style={{ color: "var(--accent-2)" }} /> مسیر دیتابیس ۳x-ui
        </div>
        <p className="text-[13px] mb-4 leading-relaxed" style={{ color: "var(--muted)" }}>
          حسابداری گروه‌ها و مصرف را از این فایل می‌خواند — فقط‌خواندنی، بدون هیچ تغییری در آن.
        </p>

        <div className="rounded-xl p-3 mb-4 flex items-start gap-2.5"
          style={{
            background: info.readable ? "var(--ok-wash)" : "var(--warn-wash)",
            border: `1px solid ${info.readable ? "var(--ok-fill)" : "var(--warn-fill)"}`,
          }}>
          {info.readable
            ? <CheckCircle2 size={15} style={{ color: "var(--ok)", flexShrink: 0, marginTop: 1 }} />
            : <AlertTriangle size={15} style={{ color: "var(--warn)", flexShrink: 0, marginTop: 1 }} />}
          <div className="min-w-0">
            <div className="text-[13px] font-semibold" style={{ color: info.readable ? "var(--ok)" : "var(--warn)" }}>
              {info.readable ? "خوانده می‌شود" : info.exists ? "پیدا شد ولی دسترسی خواندن نیست" : "پیدا نشد"}
            </div>
            <div className="text-[12px] mt-1 break-all" dir="ltr"
              style={{ color: "var(--muted)", fontFamily: "var(--mono)" }}>
              {info.current}
            </div>
            {info.exists && !info.readable && (
              <div className="text-[12px] mt-2" style={{ color: "var(--warn)" }}>
                روی سرور اجرا کنید: <code dir="ltr" className="px-1.5 py-0.5 rounded"
                  style={{ background: "var(--surface-3)" }}>chmod +r {info.current}</code>
              </div>
            )}
          </div>
        </div>

        {info.found?.length > 0 && (
          <div className="mb-4">
            <div className="text-[13px] mb-2" style={{ color: "var(--muted)" }}>
              مسیرهای پیداشده روی این سرور:
            </div>
            {info.found.map((f) => (
              <button key={f.path} onClick={() => { setPath(f.path); savePath(f.path); }}
                className="w-full flex items-center justify-between gap-2 p-2.5 rounded-xl mb-1.5 text-right"
                style={{
                  background: f.path === info.current ? "var(--accent-soft)" : "var(--surface-3)",
                  border: `1px solid ${f.path === info.current ? "var(--accent-edge)" : "var(--border)"}`,
                }}>
                <span className="text-[13px] truncate" dir="ltr"
                  style={{ color: "var(--dim)", fontFamily: "var(--mono)" }}>{f.path}</span>
                <span className="text-[11.5px] shrink-0" style={{ color: "var(--muted)" }}>
                  {(f.size / 1024 / 1024).toFixed(1)} MB
                </span>
              </button>
            ))}
          </div>
        )}

        <Field label="مسیر دستی" hint="اگر ۳x-ui جای دیگری نصب است">
          <div className="flex gap-2">
            <input className="fx-input" dir="ltr" value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/etc/x-ui/x-ui.db"
              style={{ fontFamily: "var(--mono)" }} />
            <button onClick={() => savePath(path)} disabled={busy === "path"}
              className="fx-btn px-4 py-2.5 text-[13px] shrink-0 flex items-center gap-1.5">
              {busy === "path" ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
              ذخیره
            </button>
          </div>
        </Field>
      </div>
      )}

      <div className="fx-card p-5">
        <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
          <Database size={15} style={{ color: "var(--accent-2)" }} /> بک‌آپ حسابداری
        </div>
        <p className="text-[13px] mb-4 leading-relaxed" style={{ color: "var(--muted)" }}>
          نرخ‌ها، پرداخت‌ها و لاگ تمدید. داده‌ی ۳x-ui در بک‌آپ نیست — آن از خودش خوانده می‌شود.
        </p>

        <div className="fx-g3 grid grid-cols-2 gap-3">
          <button onClick={backup} disabled={busy === "backup"}
            className="fx-btn py-3 text-[14px] flex items-center justify-center gap-2">
            {busy === "backup" ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            دریافت بک‌آپ
          </button>
          <button onClick={() => fileRef.current?.click()} disabled={busy === "restore"}
            className="fx-btn-g py-3 text-[14px] flex items-center justify-center gap-2">
            {busy === "restore" ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            بازیابی از فایل
          </button>
        </div>
        <input ref={fileRef} type="file" accept=".json" className="hidden"
          onChange={(e) => e.target.files?.[0] && restore(e.target.files[0])} />

        <InfoBox>
          قبل از بازیابی، یک نسخه‌ی امن از وضعیت فعلی گرفته می‌شود — اگر فایل اشتباه
          بود، داده‌ی فعلی از دست نرفته است.
        </InfoBox>
      </div>
    </div>
  );
}
