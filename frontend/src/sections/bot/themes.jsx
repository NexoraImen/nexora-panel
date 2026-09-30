/**
 * ربات: قالب‌ها و پالت رنگ.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle, Check, Loader2, Palette as PaletteIcon, Plus as PlusIcon, Trash2, X,
} from "lucide-react";
import { errText, okJson } from "../../lib/format";
import { API_URL } from "../../lib/constants";
import { ConfirmModal, Field, InfoBox, LoadError, Msg, PageSkeleton, SectionHead } from "../../ui/index";

// نمایش کوچک ساختار هر Template
export function TemplateThumb({ id, vars, active }) {
  const v = vars || {};
  const A = active ? (v.accent || "#2B7FD6") : "#3A4453";
  const A2 = active ? (v.accent2 || "#5AA9E6") : "#2A3444";
  const bg = active ? (v.bg || "#06090F") : "#0A0E17";
  const card = active ? `${A}12` : "#141A25";
  const bar = (w, h = 3, c = "#2A3444") => ({ width: w, height: h, borderRadius: 2, background: c });

  return (
    <div style={{ background: bg, borderRadius: 10, padding: 9, height: 68, overflow: "hidden" }}>
      {id === "classic" && (
        <>
          <div style={{ background: card, borderRadius: 6, padding: 6, marginBottom: 5, display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 20, height: 20, borderRadius: "50%", border: `2.5px solid ${A}`, borderRightColor: "transparent", flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ ...bar("72%"), marginBottom: 3 }} />
              <div style={bar("46%")} />
            </div>
          </div>
          <div style={{ display: "flex", gap: 3.5 }}>
            {[0, 1, 2].map((i) => <div key={i} style={{ flex: 1, height: 9, borderRadius: 3, background: i === 0 ? A : "#1E2531" }} />)}
          </div>
        </>
      )}
      {id === "analytics" && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 3.5, marginBottom: 4 }}>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} style={{ background: card, borderRadius: 4, padding: 3.5 }}>
                <div style={{ ...bar(9, 3, i < 2 ? A : A2), marginBottom: 2.5 }} />
                <div style={bar("62%", 2.5)} />
              </div>
            ))}
          </div>
          <div style={{ background: card, borderRadius: 4, padding: 4, display: "flex", alignItems: "flex-end", gap: 2, height: 20 }}>
            {[6, 11, 8, 14, 10, 6, 12].map((h, i) => (
              <div key={i} style={{ flex: 1, height: h, borderRadius: 1, background: i === 6 ? A : `${A}55` }} />
            ))}
          </div>
        </>
      )}
      {id === "wallet" && (
        <>
          <div style={{ height: 30, borderRadius: 8, marginBottom: 6, padding: 7, background: `linear-gradient(135deg,${A},${A2})`, position: "relative", overflow: "hidden" }}>
            <div style={{ position: "absolute", top: -10, left: -10, width: 34, height: 34, borderRadius: "50%", background: "rgba(255,255,255,.16)" }} />
            <div style={{ ...bar(26, 6, bg), opacity: .82, marginBottom: 4 }} />
            <div style={{ ...bar(16, 3, bg), opacity: .5 }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-around" }}>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} style={{ width: 12, height: 12, borderRadius: "50%", background: i === 0 ? A : "#1E2531" }} />
            ))}
          </div>
        </>
      )}
      {id === "console" && (
        <>
          <div style={{ background: card, borderRadius: 4, padding: 6, marginBottom: 5 }}>
            <div style={{ display: "flex", gap: 2.5, marginBottom: 5 }}>
              {["#FF5F57", "#FEBC2E", "#28C840"].map((cc, i) => (
                <div key={i} style={{ width: 4, height: 4, borderRadius: "50%", background: cc, opacity: active ? .85 : .35 }} />
              ))}
            </div>
            {[0, 1].map((i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <div style={bar(20, 2.5)} />
                <div style={bar(12, 2.5, i === 1 ? A : "#2A3444")} />
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 1.5 }}>
            {Array.from({ length: 16 }).map((_, i) => (
              <div key={i} style={{ flex: 1, height: 7, borderRadius: 1, background: i < 9 ? A : `${A}2E` }} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * سربرگ یک گام.
 *
 * بیرون از کامپوننت تعریف شده — اگر داخل بدنه باشد، در هر رندر
 * دوباره ساخته می‌شود و React کل زیردرختش را دور می‌ریزد. نتیجه:
 * پرش بصری و از بین رفتن انیمیشن ورود.
 */
export function ThemeStep({ n, title, desc, accent, bg }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div className="w-7 h-7 rounded-full flex items-center justify-center text-[13px] font-bold shrink-0"
        style={{
          background: accent || "var(--accent)",
          color: bg || "#06090F",
          boxShadow: `0 1px 0 rgba(255,255,255,.3) inset, 0 4px 10px -3px ${accent || "var(--accent)"}`,
        }}>{n}</div>
      <div>
        <div className="text-[14px] font-bold text-white leading-tight">{title}</div>
        {desc && <div className="text-[13px] mt-1" style={{ color: "var(--muted)" }}>{desc}</div>}
      </div>
    </div>
  );
}

export function ThemesSection({ config, setConfig, password }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [msg, setMsg] = useState(null);
  const [confirmDel, setConfirmDel] = useState(null);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/themes`, { headers: { "X-Admin-Password": password } });
      setData(await okJson(res, "خواندنِ قالب‌ها ناموفق بود"));
      setErr("");
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [password]);
  useEffect(() => { if (msg) { const t = setTimeout(() => setMsg(null), 4000); return () => clearTimeout(t); } }, [msg]);

  if (loading) return <PageSkeleton />;
  // بی‌این، خطا «۰ ساختار × ۰ پالت» و دو گامِ خالی نشان می‌داد
  if (err && !data) {
    return (
      <div className="fx-anim">
        <SectionHead title="قالب صفحه اشتراک" />
        <LoadError what="قالب‌ها و پالت‌ها" err={err} onRetry={load} />
      </div>
    );
  }

  const templates = data?.templates || [];
  const palettes = [...(data?.palettes || []), ...(data?.customPalettes || [])];
  const curTpl = config.template || "classic";
  const curPal = config.palette || "ocean";
  const activePal = palettes.find((p) => p.id === curPal) || palettes[0];
  const V = activePal?.vars || {};

  const removePalette = async (id) => {
    setConfirmDel(null);
    try {
      const res = await fetch(`${API_URL}/api/admin/palettes/${id}`, {
        method: "DELETE", headers: { "X-Admin-Password": password },
      });
      if (res.ok) { setMsg({ t: "ok", m: "پالت حذف شد" }); load(); }
      else {
        const j = await res.json().catch(() => ({}));
        setMsg({ t: "err", m: errText(j.detail, "حذف ناموفق بود") });
      }
    } catch { setMsg({ t: "err", m: "اتصال برقرار نشد" }); }
  };

  return (
    <div className="fx-anim">
      <SectionHead title="قالب صفحه اشتراک"
        desc={`ساختار و رنگ جدا هستند — ${templates.length} ساختار × ${palettes.length} پالت = ${templates.length * palettes.length} ترکیب`}
        action={
          <button onClick={() => setAddOpen(true)} className="fx-btn px-4 py-2.5 text-[14px] flex items-center gap-2">
            <PlusIcon size={14} /> پالت سفارشی
          </button>
        } />

      <Msg msg={msg} />

      {/* گام ۱ — ساختار */}
      <ThemeStep n="۱" title="ساختار قالب" desc="سبک بصری کارت‌ها و اجزای صفحه" accent={V.accent} bg={V.bg} />
      <div className="grid gap-3 mb-8" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(190px,1fr))" }}>
        {templates.map((t) => {
          const on = curTpl === t.id;
          return (
            <button key={t.id} onClick={() => setConfig({ ...config, template: t.id })}
              className="fx-card p-4 text-right"
              style={{
                transition: "transform .28s cubic-bezier(.22,1,.36,1), box-shadow .28s ease, border-color .2s ease, background .2s ease",
                ...(on ? {
                  borderColor: `${V.accent}88`,
                  background: `${V.accent}0D`,
                  transform: "translateY(-3px)",
                  boxShadow: `0 1px 0 rgba(255,255,255,.1) inset, 0 0 0 1px ${V.accent}44, 0 18px 36px -14px ${V.accent}55`,
                } : {}),
              }}>
              <div className="mb-4"><TemplateThumb id={t.id} vars={V} active={on} /></div>
              <div className="flex items-center gap-2 mb-2">
                {on && (
                  <div style={{
                    width: 16, height: 16, borderRadius: "50%", flexShrink: 0,
                    background: V.accent, display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <Check size={10} style={{ color: V.bg || "#06090F" }} />
                  </div>
                )}
                <span className="text-[14px] font-bold text-white" style={{ fontFamily: "var(--mono)" }}>{t.name}</span>
                <span className="text-[12px]" style={{ color: "var(--muted)" }}>· {t.fa}</span>
              </div>
              <div className="text-[12px] mt-1 leading-relaxed" style={{ color: "var(--muted)" }}>{t.desc}</div>
            </button>
          );
        })}
      </div>

      {/* گام ۲ — پالت */}
      <ThemeStep n="۲" title="طیف رنگی" desc="رنگ‌بندی که روی ساختار انتخابی اعمال می‌شود" accent={V.accent} bg={V.bg} />
      <div className="grid gap-3 mb-8" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(120px,1fr))" }}>
        {palettes.map((p) => {
          const on = curPal === p.id;
          const pv = p.vars || {};
          return (
            <div key={p.id} className="fx-card p-3 relative"
              style={{
                transition: "transform .28s cubic-bezier(.22,1,.36,1), box-shadow .28s ease, border-color .2s ease",
                ...(on ? {
                  borderColor: `${pv.accent}99`,
                  transform: "translateY(-2px)",
                  boxShadow: `0 1px 0 rgba(255,255,255,.1) inset, 0 0 0 1px ${pv.accent}44, 0 16px 32px -14px ${pv.accent}66`,
                } : {}),
              }}>
              <button title="انتخاب این قالب" onClick={() => setConfig({ ...config, palette: p.id })} className="w-full text-right">
                <div className="rounded-xl mb-3 relative overflow-hidden" style={{
                  height: 44,
                  background: `linear-gradient(135deg,${pv.accent},${pv.accent2})`,
                  boxShadow: `0 1px 0 rgba(255,255,255,.25) inset, 0 4px 10px -3px ${pv.accent}77`,
                }}>
                  <div style={{ position: "absolute", inset: 0, background: `linear-gradient(90deg, transparent 48%, ${pv.bg}E6)` }} />
                  {on && (
                    <div style={{
                      position: "absolute", top: 7, right: 7,
                      width: 20, height: 20, borderRadius: "50%",
                      background: pv.bg, display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                      <Check size={12} style={{ color: pv.accent }} />
                    </div>
                  )}
                </div>
                <div className="text-[13px] font-bold text-white" style={{ fontFamily: "var(--mono)" }}>{p.name}</div>
                <div className="text-[11.5px] mt-0.5" style={{ color: "var(--muted)" }}>{p.fa}</div>
              </button>
              {p.builtin === false && (
                <button title="حذف این قالب" onClick={() => setConfirmDel(p)} className="fx-ico-btn absolute" style={{ width: 24, height: 24, top: 6, left: 6 }}>
                  <Trash2 size={11} />
                </button>
              )}
            </div>
          );
        })}
      </div>

      <InfoBox>
        ترکیب فعلی: <b>{templates.find((t) => t.id === curTpl)?.name}</b> × <b>{activePal?.name}</b>
        <br />
        بعد از انتخاب، دکمه‌ی <b>«ذخیره تغییرات»</b> را بزنید، سپس در بخش
        <b> «پیش‌نمایش زنده»</b> نتیجه را ببینید. برای هر واسطه هم می‌توانید ترکیب جداگانه تعیین کنید.
      </InfoBox>

      {addOpen && <AddPaletteModal password={password} onClose={() => setAddOpen(false)}
        onAdded={(m) => { setMsg(m); load(); setAddOpen(false); }} />}

      {confirmDel && (
        <ConfirmModal title="حذف پالت؟"
          desc={`پالت «${confirmDel.name}» حذف می‌شود. اگر جایی استفاده شده باشد، به پالت پیش‌فرض برمی‌گردد.`}
          onConfirm={() => removePalette(confirmDel.id)} onCancel={() => setConfirmDel(null)} />
      )}
    </div>
  );
}

export function AddPaletteModal({ password, onClose, onAdded }) {
  const [name, setName] = useState("");
  const [fa, setFa] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [vars, setVars] = useState({
    accent: "#2B7FD6", accent2: "#5AA9E6", bg: "#06090F",
    surface: "#0D1420", surfaceAlt: "#0A0E17",
    border: "rgba(255,255,255,0.06)", text: "#E8EEF7", textMuted: "#5A6880",
  });
  const [preview, setPreview] = useState("classic");

  const setVar = (k, v) => setVars({ ...vars, [k]: v });

  const submit = async () => {
    setErr("");
    if (!name.trim()) { setErr("نام پالت را وارد کنید"); return; }
    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/palettes`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify({ name, fa: fa || name, vars }),
      });
      const d = await res.json();
      if (res.ok) onAdded({ t: "ok", m: `پالت «${name}» اضافه شد` });
      else setErr(errText(d.detail, "افزودن ناموفق بود"));
    } catch { setErr("اتصال به سرور برقرار نشد"); }
    finally { setBusy(false); }
  };

  const COLORS = [
    ["accent", "رنگ اصلی"], ["accent2", "رنگ ثانویه"],
    ["bg", "پس‌زمینه"], ["surface", "کارت‌ها"], ["text", "متن"],
  ];

  return createPortal(
    <div className="nx-modal-wrap fx-fade"
      style={{ background: "rgba(3,6,12,.82)", backdropFilter: "blur(6px)" }} onClick={onClose}>
      <div className="max-w-2xl rounded-2xl fx-scale nx-modal" onClick={(e) => e.stopPropagation()}
        style={{ background: "var(--surface)", border: "1px solid rgba(90,169,230,.3)" }}>

        <div className="nx-modal-head p-5" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <PaletteIcon size={17} style={{ color: "var(--accent-2)" }} />
              <span className="text-[16px] font-bold text-white">پالت رنگی سفارشی</span>
            </div>
            <button title="بستن" onClick={onClose} className="fx-ico-btn"><X size={16} /></button>
          </div>
        </div>

        <div className="nx-modal-body p-5">
          <div className="fx-g3 grid grid-cols-2 gap-3">
            <Field label="نام پالت (انگلیسی)">
              <input className="fx-input" dir="ltr" value={name} onChange={(e) => setName(e.target.value)} placeholder="Sunset" />
            </Field>
            <Field label="نام فارسی">
              <input className="fx-input" value={fa} onChange={(e) => setFa(e.target.value)} placeholder="غروب" />
            </Field>
          </div>

          <div className="text-[13px] font-semibold text-white mt-4 mb-2.5">رنگ‌ها</div>
          <div className="fx-g3 grid grid-cols-2 gap-3">
            {COLORS.map(([k, l]) => (
              <Field key={k} label={l}>
                <div className="flex items-center gap-2">
                  <input type="color" value={vars[k]} onChange={(e) => setVar(k, e.target.value)}
                    className="w-10 h-10 rounded-lg cursor-pointer shrink-0"
                    style={{ background: "transparent", border: "1px solid var(--border-2)" }} />
                  <input className="fx-input" dir="ltr" value={vars[k]} onChange={(e) => setVar(k, e.target.value)} />
                </div>
              </Field>
            ))}
          </div>

          <div className="text-[13px] font-semibold text-white mt-4 mb-2.5">پیش‌نمایش روی ساختارها</div>
          <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(120px,1fr))" }}>
            {["classic", "analytics", "wallet", "console"].map((id) => (
              <button key={id} onClick={() => setPreview(id)} className="text-right p-2 rounded-xl transition-all"
                style={preview === id
                  ? { background: `${vars.accent}16`, border: `1px solid ${vars.accent}77` }
                  : { background: "var(--surface-3)", border: "1px solid var(--border-2)" }}>
                <TemplateThumb id={id} vars={vars} active={preview === id} />
                <div className="text-[12px] mt-1.5 font-semibold" style={{ color: preview === id ? vars.accent2 : "var(--muted)", fontFamily: "var(--mono)" }}>
                  {id}
                </div>
              </button>
            ))}
          </div>

          {err && (
            <div className="rounded-xl p-3 mt-4 flex items-center gap-2 text-[13px]"
              style={{ background: "rgba(248,113,113,.1)", border: "1px solid rgba(248,113,113,.3)", color: "var(--danger)" }}>
              <AlertTriangle size={14} /> {err}
            </div>
          )}
        </div>

        <div className="nx-modal-foot p-5 flex gap-2" style={{ borderTop: "1px solid var(--border)" }}>
          <button onClick={onClose} className="fx-btn-g flex-1 py-3 text-[14px]">انصراف</button>
          <button onClick={submit} disabled={busy} className="fx-btn flex-1 py-3 text-[14px] flex items-center justify-center gap-2">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <PlusIcon size={14} />} افزودن پالت
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
