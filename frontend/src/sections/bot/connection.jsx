/**
 * ربات: اتصال، وضعیت و تنظیمات پایه.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect } from "react";
import {
  AlertTriangle, Bot, CheckCircle2, Circle, CreditCard, Eye, HelpCircle, Key, Loader2, Plus as PlusIcon, Power, Radio, RefreshCw, Save, Server, ShieldCheck, Trash2, Users, XCircle, Zap,
} from "lucide-react";
import { errMsg, errText, faNum, okJson } from "../../lib/format";
import { API_URL } from "../../lib/constants";
import { ConfirmModal, Field, InfoBox, Msg, PageSkeleton, SectionHead, Toggle } from "../../ui/index";

export function BotStatusBar({ status, password, onChange, dirty, onApplied }) {
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const [applied, setApplied] = useState(false);
  const [askStop, setAskStop] = useState(false);
  useEffect(() => { if (applied) { const t = setTimeout(() => setApplied(false), 3000); return () => clearTimeout(t); } }, [applied]);
  if (!status) return null;

  const ready = status.dbReady;
  const running = !!status.running;

  const act = async (action) => {
    setBusy(action); setErr("");
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/service/${action}`, {
        method: "POST", headers: { "X-Admin-Password": password },
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) setErr(errText(d.detail, "اجرای دستور ناموفق بود"));
      onChange?.();
    } catch { setErr("اتصال به سرور برقرار نشد"); }
    finally { setBusy(null); }
  };

  const applyNow = async () => {
    setBusy("apply"); setErr("");
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/reload`, {
        method: "POST", headers: { "X-Admin-Password": password },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { setApplied(true); onApplied?.(); }
      else setErr(errText(d.detail, "اعمال ناموفق بود"));
    } catch { setErr("اتصال به سرور برقرار نشد"); }
    finally { setBusy(null); }
  };

  const tone = running ? "var(--ok)" : ready ? "var(--warn)" : "var(--muted)";

  return (
    <div className="fx-card p-4 mb-4" style={{ borderColor: `${running ? "var(--ok-line)" : "var(--warn-line)"}` }}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="fx-ico" style={{ background: running ? "var(--ok-soft)" : "var(--warn-soft)" }}>
            <Bot size={16} style={{ color: tone }} />
          </div>
          <div>
            <div className="text-[14px] font-semibold text-white flex items-center gap-2">
              {running ? "ربات در حال اجراست" : ready ? "ربات متوقف است" : "ربات راه‌اندازی نشده"}
              <Circle size={7} fill={tone} strokeWidth={0} />
            </div>
            <div className="text-[13px] mt-0.5" style={{ color: "var(--muted)" }}>
              {ready
                ? `${faNum(status.stats?.users ?? 0)} کاربر · ${faNum(status.stats?.plans ?? 0)} پلن فعال · ${faNum(status.stats?.pendingOrders ?? 0)} رسید در انتظار`
                : (status.message || "توکن را وارد و ذخیره کنید")}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* عددِ بی‌برچسب را خواننده «درآمد» می‌خواند. فروش شامل
              خریدِ از کیف پول هم هست، که پول تازه‌ای نیست. */}
          {ready && status.totalSales > 0 && (
            <span className="fx-pill" style={{ background: "var(--ok-soft)", color: "var(--ok)" }}>
              فروش {Number(status.totalSales).toLocaleString("fa-IR")} تومان
            </span>
          )}
          {ready && status.totalReceived > 0
            && status.totalReceived !== status.totalSales && (
            <span className="fx-pill" style={{ background: "var(--accent-soft)", color: "var(--accent-2)" }}
              title="فقط پرداخت‌های کارتی — خرید از کیف پول پول تازه نیست">
              دریافتی {Number(status.totalReceived).toLocaleString("fa-IR")} تومان
            </span>
          )}
          {running ? (
            <>
              <button onClick={() => act("restart")} disabled={!!busy}
                className="fx-btn-g px-3 py-2.5 text-[13px] flex items-center gap-1.5">
                {busy === "restart" ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                ری‌استارت
              </button>
              {/* خاموش‌کردن فروش را کامل می‌خواباند — با یک کلیکِ اشتباه نه */}
              <button onClick={() => setAskStop(true)} disabled={!!busy}
                className="px-3.5 py-2.5 rounded-[10px] text-[13px] font-semibold flex items-center gap-1.5"
                style={{ background: "var(--danger-soft)", border: "1px solid var(--danger-line)", color: "var(--danger)" }}>
                {busy === "stop" ? <Loader2 size={13} className="animate-spin" /> : <Power size={13} />}
                خاموش
              </button>
            </>
          ) : (
            <button onClick={() => act("start")} disabled={!!busy}
              className="fx-btn px-4 py-2.5 text-[13px] flex items-center gap-1.5">
              {busy === "start" ? <Loader2 size={13} className="animate-spin" /> : <Power size={13} />}
              روشن کردن ربات
            </button>
          )}
        </div>
      </div>

      {running && dirty && (
        <div className="mt-3 rounded-xl p-3 flex items-center justify-between gap-3 flex-wrap"
          style={{ background: "var(--warn-wash)", border: "1px solid var(--warn-line)" }}>
          <div className="flex items-start gap-2.5">
            <RefreshCw size={15} style={{ color: "var(--warn)", flexShrink: 0, marginTop: 1 }} />
            <div>
              <div className="text-[13px] font-semibold" style={{ color: "var(--text)" }}>
                تغییرات ذخیره‌نشده دارید
              </div>
              <div className="text-[12px] mt-1 leading-relaxed" style={{ color: "var(--muted)" }}>
                قیمت‌ها و متن‌ها به‌محض ذخیره اعمال می‌شوند. اگر توکن یا اتصال پنل را
                عوض کرده‌اید، این دکمه را بزنید.
              </div>
            </div>
          </div>
          <button onClick={applyNow} disabled={!!busy}
            className="fx-btn px-4 py-2.5 text-[13px] flex items-center gap-1.5 shrink-0">
            {busy === "apply" ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            اعمال در ربات
          </button>
        </div>
      )}

      {applied && (
        <div className="mt-3 rounded-xl p-2.5 text-[13px] flex items-center gap-2"
          style={{ background: "var(--ok-soft)", border: "1px solid var(--ok-fill)", color: "var(--ok)" }}>
          <CheckCircle2 size={13} /> اعمال شد — ربات ظرف ۳۰ ثانیه همگام می‌شود
        </div>
      )}

      {err && (
        <div className="mt-3 rounded-xl p-2.5 text-[13px] flex items-center gap-2"
          style={{ background: "var(--danger-soft)", border: "1px solid var(--danger-fill)", color: "var(--danger)" }}>
          <AlertTriangle size={13} /> {err}
        </div>
      )}
      {askStop && (
        <ConfirmModal title="خاموش‌کردنِ ربات"
          desc="تا وقتی دوباره روشنش نکنید، هیچ مشتری‌ای نمی‌تواند بخرد، تمدید کند یا کانفیگش را بگیرد؛ یادآوری‌ها و تمدیدِ خودکار هم متوقف می‌شوند."
          confirmLabel="خاموش کن" onCancel={() => setAskStop(false)}
          onConfirm={() => { setAskStop(false); act("stop"); }} />
      )}
    </div>
  );
}

export function ConnectionTest({ password, tenant }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const runTrace = async () => {
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/xui-trace`, {
        method: "POST",
        headers: { "X-Admin-Password": password },
      });
      const d = await res.json();
      setResult(d);
    } catch {
      setResult({ ok: false, steps: [
        { title: "اتصال به سرور", ok: false, detail: "برقرار نشد" }] });
    } finally { setBusy(false); }
  };

  const run = async () => {
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/test-connection`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify({
          panel_url: tenant.panel_url,
          panel_user: tenant.panel_user,
          panel_pass: tenant.panel_pass,
          panel_token: tenant.panel_token,
          default_inbound: tenant.default_inbound,
        }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) {
        setResult({ ok: false, steps: [{ key: "e", title: "تست انجام نشد",
                    ok: false, detail: errText(d.detail, "خطای سرور"), hint: "" }] });
      } else {
        setResult(d);
      }
    } catch {
      setResult({ ok: false, steps: [{ key: "e", title: "اتصال به سرور برقرار نشد",
                  ok: false, detail: "", hint: "پنل در حال اجراست؟" }] });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fx-card p-5 mb-4">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-1">
        <div>
          <div className="text-[14px] font-semibold text-white flex items-center gap-2">
            <ShieldCheck size={15} style={{ color: "var(--accent-2)" }} /> تست اتصال
          </div>
          <p className="text-[13px] mt-1.5 leading-relaxed max-w-md" style={{ color: "var(--muted)" }}>
            یک کانفیگ آزمایشی می‌سازد و بلافاصله پاک می‌کند — تا مطمئن شوید
            ربات واقعاً می‌تواند برای مشتری کانفیگ بسازد، نه فقط وصل شود.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button title="تست اتصال" onClick={run} disabled={busy || !tenant.panel_url}
            className="fx-btn px-4 py-2.5 text-[14px] flex items-center gap-1.5"
            style={!tenant.panel_url ? { opacity: 0.45, cursor: "not-allowed" } : {}}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            {busy ? "در حال بررسی..." : "اجرای تست"}
          </button>
          <button onClick={runTrace} disabled={busy || !tenant.panel_url}
            className="fx-btn-g px-3 py-2.5 text-[13px] flex items-center gap-1.5"
            style={!tenant.panel_url ? { opacity: 0.45, cursor: "not-allowed" } : {}}>
            <HelpCircle size={13} /> تشخیص عمیق
          </button>
        </div>
      </div>

      {!tenant.panel_url && (
        <p className="text-[13px] mt-3" style={{ color: "var(--warn)" }}>
          ابتدا آدرس پنل را وارد و ذخیره کنید.
        </p>
      )}

      {result && (
        <div className="mt-4">
          <div className="rounded-xl p-3 mb-3 flex items-center gap-2.5 text-[14px] font-semibold"
            style={{
              background: result.ok ? "var(--ok-soft)" : "var(--danger-soft)",
              border: `1px solid ${result.ok ? "var(--ok-line)" : "var(--danger-line)"}`,
              color: result.ok ? "var(--ok)" : "var(--danger)",
            }}>
            {result.ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            {result.ok ? "همه‌چیز آماده است — ربات می‌تواند کانفیگ بسازد"
                       : "یک مرحله ناموفق بود"}
          </div>

          {(result.steps || []).map((s, i) => (
            <div key={i} className="flex gap-3 py-2.5"
              style={{ borderBottom: i < result.steps.length - 1 ? "1px solid var(--border)" : "none" }}>
              <div className="shrink-0 mt-0.5">
                {s.ok ? <CheckCircle2 size={15} style={{ color: "var(--ok)" }} />
                      : <XCircle size={15} style={{ color: "var(--danger)" }} />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold"
                  style={{ color: s.ok ? "var(--text)" : "var(--danger)" }}>{s.title}</div>
                {errText(s.detail) && (
                  <div className="text-[13px] mt-1 leading-relaxed break-words" style={{ color: "var(--muted)" }}>
                    {errText(s.detail)}
                  </div>
                )}
                {s.hint && (
                  <div className="text-[13px] mt-1.5 leading-relaxed" style={{ color: "var(--warn)" }}>
                    {s.hint}
                  </div>
                )}
              </div>
            </div>
          ))}

          {result.inbounds?.length > 0 && (
            <div className="mt-4">
              <div className="text-[13px] mb-2" style={{ color: "var(--muted)" }}>
                inboundهای موجود — شماره‌ی مورد نظر را در تنظیمات بگذارید:
              </div>
              <div className="flex flex-wrap gap-2">
                {result.inbounds.map((ib) => (
                  <span key={ib.id} className="fx-pill"
                    style={{ background: "var(--surface-3)", color: "var(--dim)",
                             border: "1px solid var(--border-2)" }}>
                    <b style={{ fontFamily: "var(--mono)" }}>#{ib.id}</b>
                    {" "}{ib.remark || ib.protocol}
                    {ib.port ? ` · ${ib.port}` : ""}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function BotSection({ password, dirty }) {
  const [t, setT] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [showTok, setShowTok] = useState(false);
  const [authMode, setAuthMode] = useState("token");
  // خطای خواندن جدا از msg نگه داشته می‌شود: msg چند ثانیه بعد پاک می‌شد
  // و شاخه‌ی «خوانده نشد» به «ماژول ربات ممکن است نصب نشده باشد» برمی‌گشت
  const [loadErr, setLoadErr] = useState("");

  const load = async () => {
    try {
      const [s, st] = await Promise.all([
        fetch(`${API_URL}/api/admin/bot/settings`, { headers: { "X-Admin-Password": password } })
          .then((r) => okJson(r, "خواندنِ تنظیماتِ ربات ناموفق بود")),
        // وضعیت فرعی است؛ شکستش صفحه را نمی‌اندازد ولی گفته می‌شود
        fetch(`${API_URL}/api/admin/bot/status`, { headers: { "X-Admin-Password": password } })
          .then((r) => okJson(r, "خواندنِ وضعیتِ ربات ناموفق بود"))
          .catch((e) => ({ _err: errMsg(e) })),
      ]);
      setLoadErr("");
      if (st && st._err) {
        setStatus(null);
        setMsg({ t: "err", m: st._err });
      } else setStatus(st);
      // بک‌اند ممکن است tenant را null بدهد یا فیلدهایش ناقص باشند.
      // اینجا یک شکل کامل می‌سازیم تا هیچ‌جای رابط روی null نخورد.
      // اگر ماژول ربات در دسترس نیست، حالت خطا نشان می‌دهیم
      if (!s.ready && !s.tenant) {
        setT(null);
        if (s.error) setLoadErr(s.error);
        return;
      }

      const raw = s.tenant || {};
      const tn = {
        name: "Nexora",
        bot_username: "", owner_tg_id: "", panel_url: "", panel_user: "",
        default_inbound: "", admin_group_id: "",
        ...raw,
        settings: (raw.settings && typeof raw.settings === "object" && !Array.isArray(raw.settings))
          ? raw.settings : {},
        topics: (raw.topics && typeof raw.topics === "object" && !Array.isArray(raw.topics))
          ? raw.topics : {},
      };
      setT(tn);
      // اگر قبلاً با یوزر/رمز تنظیم شده بود، همان حالت را نشان بده
      if (tn.panel_user && !tn.panel_token_set) setAuthMode("login");
      if (s.error) setMsg({ t: "err", m: s.error });
    } catch (e) { setLoadErr(errMsg(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [password]);
  useEffect(() => { if (msg) { const x = setTimeout(() => setMsg(null), 4000); return () => clearTimeout(x); } }, [msg]);

  const up = (patch) => setT({ ...t, ...patch });
  const upS = (patch) => setT({ ...t, settings: { ...(t.settings || {}), ...patch } });

  const save = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify(t),
      });
      const d = await res.json();
      if (res.ok) { setMsg({ t: "ok", m: "تنظیمات ربات ذخیره شد" }); load(); }
      else setMsg({ t: "err", m: errText(d.detail, "ذخیره ناموفق بود") });
    } catch { setMsg({ t: "err", m: "اتصال برقرار نشد" }); }
    finally { setSaving(false); }
  };

  if (loading) return <PageSkeleton />;

  // اگر به هر دلیلی tenant ساخته نشد، به‌جای صفحه‌ی سفید یک پیام
  // با راه‌حل نشان می‌دهیم.
  if (!t) {
    return (
      <div className="fx-anim">
        <SectionHead title="اتصال و تنظیمات ربات" desc="" />
        <div className="fx-card fx-empty">
          <AlertTriangle size={24} style={{ color: "var(--warn)" }} className="mx-auto mb-3" />
          <div className="text-[14px] font-semibold text-white mb-2">
            تنظیمات ربات خوانده نشد
          </div>
          <p className="text-[13px] mb-5 max-w-sm mx-auto leading-relaxed" style={{ color: "var(--muted)" }}>
            {loadErr || msg?.m || "ماژول ربات ممکن است نصب نشده باشد."}
          </p>
          <button onClick={() => { setLoading(true); load(); }}
            className="fx-btn px-5 py-2.5 text-[14px] inline-flex items-center gap-2">
            <RefreshCw size={14} /> تلاش دوباره
          </button>
          <div className="text-[13px] mt-5 pt-4" style={{ color: "var(--muted)", borderTop: "1px solid var(--border)" }}>
            اگر ادامه داشت، روی سرور اجرا کنید:{" "}
            <code dir="ltr" className="px-2 py-1 rounded-md"
              style={{ background: "var(--surface-3)", color: "var(--accent-2)", fontFamily: "var(--mono)" }}>
              nexora doctor
            </code>
          </div>
        </div>
      </div>
    );
  }

  const s = (t.settings && typeof t.settings === "object" && !Array.isArray(t.settings))
    ? t.settings : {};
  const cards = Array.isArray(s.cards) ? s.cards : [];

  return (
    <div className="fx-anim">
      <SectionHead title="اتصال و تنظیمات ربات"
        desc="توکن ربات، اتصال به پنل 3x-ui، گروه مدیریت و شماره کارت‌ها."
        action={
          <button onClick={save} disabled={saving} className="fx-btn px-4 py-2.5 text-[14px] flex items-center gap-1.5">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} ذخیره
          </button>
        } />

      <BotStatusBar status={status} password={password} onChange={load} dirty={dirty} />
      <Msg msg={msg} />

      {/* دو ستون روی صفحه‌ی پهن: فیلدهای کوتاه (یوزرنیم، آیدی گروه) در یک
          ستونِ ۹۹۰ پیکسلی کش می‌آمدند و صفحه ۲۳۰۰ پیکسل پیمایش داشت */}
      <div className="fx-cols2">
      {/* توکن ربات */}
      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
          <Bot size={15} style={{ color: "var(--accent-2)" }} /> ربات تلگرام
        </div>
        <p className="text-[13px] mb-4" style={{ color: "var(--muted)" }}>
          توکن را از <span dir="ltr">@BotFather</span> بگیرید.
        </p>

        <div className="fx-g3 grid grid-cols-2 gap-3">
          <Field label="نام کسب‌وکار">
            <input className="fx-input" value={t.name || ""} onChange={(e) => up({ name: e.target.value })} placeholder="Nexora" />
          </Field>
          <Field label="یوزرنیم ربات" hint="بدون @">
            <input className="fx-input" dir="ltr" value={t.bot_username || ""} onChange={(e) => up({ bot_username: e.target.value })} placeholder="NexoraVpnBot" />
          </Field>
        </div>

        <Field label="توکن ربات" hint={t.bot_token_set ? "توکن ذخیره شده — برای تغییر، مقدار جدید وارد کنید" : "الزامی"}>
          <div className="flex gap-2">
            <input className="fx-input" dir="ltr" type={showTok ? "text" : "password"}
              value={t.bot_token || ""} onChange={(e) => up({ bot_token: e.target.value })}
              placeholder="123456:AAE..." style={{ fontFamily: "var(--mono)" }} />
            <button title="نمایش یا پنهان‌کردن توکن" onClick={() => setShowTok(!showTok)} className="fx-btn-g px-3 shrink-0">
              <Eye size={14} />
            </button>
          </div>
        </Field>

        <Field label="آیدی عددی ادمین اصلی" hint="از @userinfobot بگیرید">
          <input className="fx-input" dir="ltr" value={t.owner_tg_id || ""}
            onChange={(e) => up({ owner_tg_id: e.target.value })} placeholder="123456789"
            style={{ fontFamily: "var(--mono)" }} />
        </Field>
      </div>

      {/* اتصال به پنل */}
      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
          <Server size={15} style={{ color: "var(--accent-2)" }} /> اتصال به پنل 3x-ui
        </div>
        <p className="text-[13px] mb-4" style={{ color: "var(--muted)" }}>
          ربات از این اتصال برای ساخت خودکار کانفیگ استفاده می‌کند.
        </p>

        <Field label="آدرس پنل" hint="با پورت و مسیر، مثلاً https://panel.site.com:2053/abc">
          <input className="fx-input" dir="ltr" value={t.panel_url || ""}
            onChange={(e) => up({ panel_url: e.target.value })} placeholder="https://panel.example.com:2053/path" />
        </Field>

        <div className="flex gap-2 mb-4">
          {[["token", "توکن API", ShieldCheck, "امن‌تر"], ["login", "نام کاربری و رمز", Key, ""]].map(([k, l, Ico, tag]) => (
            <button key={k} onClick={() => setAuthMode(k)}
              className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl text-[13px] font-semibold transition-all"
              style={authMode === k
                ? { background: "linear-gradient(135deg,var(--accent),var(--accent-2))", color: "#06090F" }
                : { background: "var(--surface-3)", border: "1px solid var(--border-2)", color: "var(--muted)" }}>
              <Ico size={14} /> {l}
              {tag && authMode === k && (
                <span className="text-[11px] px-1.5 py-0.5 rounded-full"
                  style={{ background: "var(--scrim-1)" }}>{tag}</span>
              )}
            </button>
          ))}
        </div>

        {authMode === "token" ? (
          <>
            <Field label="توکن API پنل" hint={t.panel_token_set ? "ذخیره شده — برای تغییر مقدار جدید وارد کنید" : "از پنل: Settings → Security → API Token"}>
              <input className="fx-input" dir="ltr" type="password" value={t.panel_token || ""}
                onChange={(e) => up({ panel_token: e.target.value })}
                placeholder="xxxxxxxx-xxxx-xxxx"
                style={{ fontFamily: "var(--mono)" }} />
            </Field>
            <InfoBox>
              <b>چرا توکن بهتر است؟</b> رمز پنل دسترسی کامل می‌دهد و اگر لو برود
              باید کل رمز را عوض کنید. توکن را می‌توانید هر لحظه از پنل باطل کنید
              بدون این‌که چیز دیگری تغییر کند.
            </InfoBox>
          </>
        ) : (
          <div className="fx-g3 grid grid-cols-2 gap-3">
            <Field label="نام کاربری پنل">
              <input className="fx-input" dir="ltr" value={t.panel_user || ""} onChange={(e) => up({ panel_user: e.target.value })} />
            </Field>
            <Field label="رمز پنل" hint={t.panel_pass_set ? "ذخیره شده" : ""}>
              <input className="fx-input" dir="ltr" type="password" value={t.panel_pass || ""}
                onChange={(e) => up({ panel_pass: e.target.value })} />
            </Field>
          </div>
        )}

        <Field label="شناسه inbound پیش‌فرض" hint="عدد inbound که کانفیگ‌ها در آن ساخته شوند">
          <input className="fx-input" dir="ltr" value={t.default_inbound || ""}
            onChange={(e) => up({ default_inbound: e.target.value })} placeholder="1"
            style={{ fontFamily: "var(--mono)" }} />
        </Field>
      </div>

      <ConnectionTest password={password} tenant={t} />

      {/* گروه مدیریت */}
      <div className="fx-card p-5 mb-4">
        <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
          <Users size={15} style={{ color: "var(--accent-2)" }} /> گروه مدیریت
        </div>
        <p className="text-[13px] mb-4 leading-relaxed" style={{ color: "var(--muted)" }}>
          یک سوپرگروه خصوصی بسازید، تاپیک‌ها را فعال کنید، ربات را ادمین کنید و آیدی گروه را اینجا بگذارید.
          ربات خودش تاپیک‌های لازم را می‌سازد.
        </p>
        <Field label="آیدی گروه" hint="معمولاً با -100 شروع می‌شود">
          <input className="fx-input" dir="ltr" value={t.admin_group_id || ""}
            onChange={(e) => up({ admin_group_id: e.target.value })} placeholder="-1001234567890"
            style={{ fontFamily: "var(--mono)" }} />
        </Field>
      </div>

      {/* کارت‌های بانکی */}
      <div className="fx-card p-5 mb-4">
        <div className="flex items-center justify-between gap-3 mb-1">
          <div className="text-[14px] font-semibold text-white flex items-center gap-2">
            <CreditCard size={15} style={{ color: "var(--accent-2)" }} /> شماره کارت‌ها
          </div>
          <button onClick={() => upS({ cards: [...cards, { number: "", holder: "", bank: "", active: true }] })}
            className="fx-btn-g px-3 py-2 text-[13px] flex items-center gap-1.5">
            <PlusIcon size={13} /> افزودن کارت
          </button>
        </div>
        <p className="text-[13px] mb-4" style={{ color: "var(--muted)" }}>
          اگر چند کارت فعال باشد، ربات به‌صورت چرخشی از آن‌ها استفاده می‌کند.
        </p>

        {cards.length === 0 && (
          <div className="text-center py-6 text-[13px]" style={{ color: "var(--muted)" }}>
            هنوز کارتی اضافه نشده — بدون کارت، پرداخت کار نمی‌کند
          </div>
        )}

        {cards.map((cd, i) => (
          <div key={i} className="fx-card p-4 mb-3" style={{ background: "var(--surface-3)" }}>
            <div className="flex items-center justify-between gap-2 mb-3">
              <Toggle checked={cd.active !== false}
                onChange={() => { const l = [...cards]; l[i] = { ...cd, active: !(cd.active !== false) }; upS({ cards: l }); }}
                label="فعال" />
              <button title="حذف این کارت" onClick={() => upS({ cards: cards.filter((_, x) => x !== i) })}
                className="fx-ico-btn" style={{ width: 28, height: 28 }}><Trash2 size={13} /></button>
            </div>
            <Field label="شماره کارت">
              <input className="fx-input" dir="ltr" value={cd.number || ""}
                onChange={(e) => { const l = [...cards]; l[i] = { ...cd, number: e.target.value }; upS({ cards: l }); }}
                placeholder="6037997512345678" style={{ fontFamily: "var(--mono)" }} />
            </Field>
            <div className="fx-g3 grid grid-cols-2 gap-3">
              <Field label="به نام">
                <input className="fx-input" value={cd.holder || ""}
                  onChange={(e) => { const l = [...cards]; l[i] = { ...cd, holder: e.target.value }; upS({ cards: l }); }}
                  placeholder="علی محمدی" />
              </Field>
              <Field label="بانک">
                <input className="fx-input" value={cd.bank || ""}
                  onChange={(e) => { const l = [...cards]; l[i] = { ...cd, bank: e.target.value }; upS({ cards: l }); }}
                  placeholder="ملی" />
              </Field>
            </div>
          </div>
        ))}
      </div>

      {/* عضویت اجباری کانال */}
      <div className="fx-card p-5 mb-4">
        <div className="flex items-center justify-between gap-3 mb-1">
          <div className="text-[14px] font-semibold text-white flex items-center gap-2">
            <Radio size={15} style={{ color: "var(--accent-2)" }} /> عضویت اجباری کانال
          </div>
          <Toggle checked={!!s.force_channel_on}
            onChange={() => upS({ force_channel_on: !s.force_channel_on })} label="فعال" />
        </div>
        <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--muted)" }}>
          اگر فعال باشد، کاربر تا در کانال عضو نشود نمی‌تواند پلن‌ها را ببیند یا تست رایگان بگیرد.
        </p>

        {/* Off: the fields fold away instead of sitting greyed out (the
            owner's screenshot: a greyed field and a three-line warning
            under a switch that was off). */}
        {s.force_channel_on && <div className="mt-3">
          <Field label="یوزرنیم یا لینک کانال" hint="مثلاً @your_channel یا https://t.me/your_channel">
            <input className="fx-input" dir="ltr" value={s.force_channel || ""}
              onChange={(e) => upS({ force_channel: e.target.value })} placeholder="@your_channel" />
          </Field>

          <InfoBox tone="warn">
            ربات باید در کانال <b>ادمین</b> باشد؛ وگرنه عضویت بررسی نمی‌شود و همه می‌توانند بخرند.
          </InfoBox>
        </div>}
      </div>

      </div>

      {/* راه‌اندازی */}
      <p className="text-[12.5px] px-1" style={{ color: "var(--muted)" }}>
        بعد از ذخیره، روی سرور بزنید:{" "}
        <code dir="ltr" className="px-2 py-0.5 rounded-md text-[12.5px]"
          style={{ background: "var(--surface-3)", color: "var(--accent-2)", fontFamily: "var(--mono)" }}>
          nexora bot enable
        </code>
      </p>
    </div>
  );
}
