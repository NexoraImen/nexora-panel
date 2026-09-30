/*
 * Pro license card (System page).
 * Spec: docs/specs/2026-09-29-license-core.md
 *
 * Every state the backend can report has its own tone and sentence here;
 * the sentence itself comes from the backend (`message`), so the panel and
 * the 403 of a locked route always say the same thing.
 */
import React, { useState, useEffect } from "react";
import { KeyRound, RefreshCw } from "lucide-react";
import { errMsg, okJson } from "../lib/format";
import { API_URL } from "../lib/constants";
import { ConfirmModal, Msg } from "../ui/index";
import { isoToJalaliStamp } from "../ui/jalali";
import { setLicense } from "../ui/pro";

const TONE = {
  active: "ok", grace: "warn", none: "accent",
  expired: "danger", invalid: "danger", wrong_machine: "danger", clock: "danger",
};
const TITLE = {
  active: "Pro فعال است", grace: "Pro در مهلت", none: "نسخه‌ی Community",
  expired: "Pro قفل است", invalid: "مجوز نامعتبر", wrong_machine: "مجوز برای سرور دیگری است",
  clock: "ساعت سرور عقب رفته",
};
const PLAN = { monthly: "ماهانه", yearly: "سالانه", owner: "دائمی مالک" };

// Literal paths, not `license/${what}`: tests/test-seams.py matches every
// panel call to a real route and cannot see through a template.
const URLS = {
  activate: `${API_URL}/api/admin/license/activate`,
  refresh: `${API_URL}/api/admin/license/refresh`,
  deactivate: `${API_URL}/api/admin/license/deactivate`,
  proInstall: `${API_URL}/api/admin/license/pro-install`,
  updateLog: `${API_URL}/api/admin/update-log`,
};

const stamp = (ts) => (ts ? isoToJalaliStamp(new Date(ts * 1000).toISOString()) : "");

export function LicenseCard({ password }) {
  const [lic, setLic] = useState(null);
  const [err, setErr] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState(null);
  const [confirmOff, setConfirmOff] = useState(false);
  // The Pro package install runs `nexora pro` on the server (fetch, rebuild,
  // restart). Its log is the update log; the last line is shown until it ends.
  const [install, setInstall] = useState(null);
  const H = { "X-Admin-Password": password };

  useEffect(() => {
    if (!install || install.done) return undefined;
    const id = setInterval(async () => {
      try {
        const r = await fetch(URLS.updateLog, { headers: H });
        const j = await okJson(r, "خواندنِ گزارشِ نصب ناموفق بود");
        const last = (j.lines || []).filter((l) => l.trim()).slice(-1)[0] || "";
        setInstall({ line: last, done: !!j.finished, failed: !!j.failed });
      } catch {
        // The panel restarts during the install: a failed read here is expected
        // for a few seconds, and the next tick tries again.
      }
    }, 3000);
    return () => clearInterval(id);
  }, [install && install.done, password]);

  const proInstall = async () => {
    setBusy("pro"); setMsg(null);
    try {
      const res = await fetch(URLS.proInstall, { method: "POST", headers: H });
      const v = await okJson(res, "شروعِ نصبِ بسته‌ی Pro ناموفق بود");
      setInstall({ line: v.message, done: false, failed: false });
    } catch (e) {
      setMsg({ t: "err", m: errMsg(e) });
    } finally { setBusy(""); }
  };

  const load = async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/license`, { headers: H });
      const v = await okJson(res, "خواندن وضعیت مجوز ناموفق بود");
      setLic(v); setLicense(v);
      setErr("");
    } catch (e) { setErr(errMsg(e)); }
  };
  useEffect(() => { load(); }, [password]);

  const act = async (what, body, okText) => {
    setBusy(what); setMsg(null);
    try {
      const res = await fetch(URLS[what], {
        method: "POST",
        headers: { ...H, "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const v = await okJson(res, "درخواست مجوز ناموفق بود");
      // Shared: the nav marks and the locked sections follow at once.
      setLic(v); setLicense(v);
      setMsg({ t: "ok", m: okText });
      if (what === "activate") setKey("");
    } catch (e) {
      setMsg({ t: "err", m: errMsg(e) });
    } finally { setBusy(""); }
  };

  if (err) return <div className="mb-4"><Msg msg={{ t: "err", m: err }} /></div>;
  if (!lic) return null;

  const tone = TONE[lic.state] || "danger";
  const has = !!lic.license_id;
  const refresh = lic.refresh || {};

  return (
    <div className="fx-card p-4 mb-4"
      style={{ background: `var(--${tone}-wash)`, borderColor: `var(--${tone}-line)` }}>
      {/* flex-wrap + min width: measured at 375px the two buttons squeezed
          the text to a 90px column, 455px tall. Now they drop to their own row. */}
      <div className="flex items-start gap-3 flex-wrap">
        <div className="fx-ico" style={{ background: `var(--${tone}-soft)` }}>
          <KeyRound size={16} style={{ color: `var(--${tone})` }} />
        </div>
        <div className="flex-1" style={{ minWidth: 220 }}>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[15px] font-semibold text-white">{TITLE[lic.state] || lic.state}</span>
            {lic.plan && (
              <span className="text-[12px] px-2 py-0.5 rounded-md"
                style={{ background: "var(--hair-2)", color: "var(--dim)" }}>{PLAN[lic.plan] || lic.plan}</span>
            )}
          </div>
          <div className="text-[13px] mt-1 leading-relaxed" style={{ color: "var(--dim)" }}>{lic.message}</div>
          {refresh.tried_at && refresh.ok === false && (
            <div className="text-[12px] mt-1" style={{ color: "var(--warn)" }}>
              آخرین تلاش برای تازه‌کردن ({stamp(refresh.tried_at)}) ناموفق بود: {refresh.error}
            </div>
          )}
        </div>
        {has && (
          <div className="flex gap-2 shrink-0">
            <button onClick={() => act("refresh", null, "مجوز تازه شد")} disabled={!!busy}
              className="fx-btn-g px-3 py-2 text-[13px] flex items-center gap-1.5">
              <RefreshCw size={13} className={busy === "refresh" ? "animate-spin" : ""} /> تازه‌کردن
            </button>
            <button onClick={() => setConfirmOff(true)} disabled={!!busy}
              className="fx-btn-g px-3 py-2 text-[13px]" style={{ color: "var(--danger)" }}>
              غیرفعال
            </button>
          </div>
        )}
      </div>

      {(!has || lic.state === "invalid" || lic.state === "wrong_machine") && (
        <div className="flex gap-2 mt-3">
          <input className="fx-input flex-1" dir="ltr" value={key} placeholder="NXP-XXXX-XXXX-XXXX-XXXX"
            onChange={(e) => setKey(e.target.value)} />
          <button onClick={() => act("activate", { key }, "مجوز فعال شد")}
            disabled={!!busy || key.trim().length < 8}
            className="fx-btn px-4 py-2.5 text-[14px] shrink-0">
            {busy === "activate" ? "…" : "فعال‌سازی"}
          </button>
          {!has && (
            <a href={lic.sales_url} target="_blank" rel="noreferrer"
              className="fx-btn-g px-3.5 py-2.5 text-[13px] shrink-0">خرید Pro</a>
          )}
        </div>
      )}
      {lic.pro && !lic.pro_loaded && !lic.pro_error && (
        <div className="flex items-center gap-2 flex-wrap mt-3">
          <span className="text-[13px] flex-1" style={{ color: "var(--warn)", minWidth: 200 }}>
            مجوز فعال است ولی بسته‌ی Pro روی این سرور نصب نیست.
          </span>
          <button onClick={proInstall} disabled={!!busy || (install && !install.done)}
            className="fx-btn px-4 py-2 text-[13px] shrink-0">
            {busy === "pro" ? "…" : "نصبِ بسته‌ی Pro"}
          </button>
        </div>
      )}
      {install && (
        <div className="text-[12px] mt-2 leading-relaxed"
          style={{ color: install.failed ? "var(--danger)" : install.done ? "var(--ok)" : "var(--dim)" }}>
          {install.done
            ? (install.failed ? "نصب کامل نشد: " : "بسته‌ی Pro نصب شد؛ صفحه را تازه کنید. ")
            : "در حال نصب… "}
          <span dir="ltr">{install.line}</span>
        </div>
      )}
      {lic.pro_error && (
        <div className="text-[12px] mt-2" style={{ color: "var(--danger)" }}>
          کدِ Pro روی این سرور بار نشد: <span dir="ltr">{lic.pro_error}</span>
        </div>
      )}
      {!lic.issuer_configured && (
        <div className="text-[12px] mt-2" style={{ color: "var(--warn)" }}>
          نشانی سرور مجوز روی این نصب تنظیم نشده؛ فعال‌سازی و تازه‌کردن کار نمی‌کنند.
        </div>
      )}

      <div className="text-[12px] mt-3 flex items-center gap-1.5 min-w-0" style={{ color: "var(--muted)" }}>
        <span className="shrink-0">شناسه‌ی سرور:</span>
        <code dir="ltr" className="truncate" style={{ fontFamily: "var(--mono)" }}>{lic.fingerprint}</code>
      </div>
      {msg && <div className="mt-2"><Msg msg={msg} /></div>}

      {confirmOff && (
        <ConfirmModal
          title="غیرفعال‌کردن مجوز روی این سرور؟"
          desc="بخش‌های Pro همین‌جا قفل می‌شوند و مجوز برای فعال‌سازی روی سرور دیگری آزاد می‌شود. مشتری‌ها قطع نمی‌شوند."
          confirmLabel="غیرفعال کن"
          onConfirm={() => { setConfirmOff(false); act("deactivate", null, "مجوز غیرفعال شد"); }}
          onCancel={() => setConfirmOff(false)} />
      )}
    </div>
  );
}
