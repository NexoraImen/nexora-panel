/**
 * ربات: انتخاب اینباند.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect } from "react";
import {
  AlertTriangle, Check, CheckCircle2, Circle, Layers, Loader2, Network, RefreshCw, Save, Star,
} from "lucide-react";
import { API_URL } from "../../lib/constants";
import { errMsg, errText, faNum, okJson } from "../../lib/format";
import { EmptyState, InfoBox, Msg, PageSkeleton, SectionHead, StatTile, StatusChip } from "../../ui/index";

// سه حالت انتخاب اینباند. متن‌ها عمداً توضیحی‌اند تا مدیر
// بدون خواندن مستندات بفهمد هرکدام چه اثری روی کانفیگ مشتری دارد.
export const INBOUND_MODES = [
  {
    key: "all",
    title: "همه‌ی اینباندهای فعال",
    desc: "کانفیگ روی هر اینباند فعال ساخته می‌شود. اگر یکی از سرورها بیفتد، بقیه کار می‌کنند.",
    tag: "پیشنهادی",
  },
  {
    key: "default",
    title: "فقط اینباند پیش‌فرض",
    desc: "همان اینباندی که در «اتصال و تنظیمات» به‌عنوان پیش‌فرض ثبت شده.",
  },
  {
    key: "custom",
    title: "انتخاب دستی",
    desc: "خودت مشخص کن کانفیگ روی کدام اینباندها ساخته شود.",
  },
];

export function InboundRow({ inb, checked, onToggle }) {
  return (
    <label className="flex items-center gap-3 p-3 rounded-xl mb-2 cursor-pointer transition-all"
      style={{
        background: checked ? "var(--accent-soft)" : "var(--surface-3)",
        border: `1px solid ${checked ? "var(--accent-2)" : "var(--border)"}`,
      }}>
      <input type="checkbox" checked={checked} onChange={() => onToggle(inb.id)}
        style={{ accentColor: "var(--accent)", flexShrink: 0 }} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[14px] font-semibold text-white truncate">{inb.remark}</span>
          {!inb.enable && (
            <span className="text-[11px] px-1.5 py-0.5 rounded"
              style={{ background: "var(--danger-soft)", color: "var(--danger)" }}>
              غیرفعال
            </span>
          )}
        </div>
        <div className="text-[12px] mt-1 flex items-center gap-2" style={{ color: "var(--muted)" }}>
          <span dir="ltr" style={{ fontFamily: "var(--mono)" }}>
            {inb.protocol || "—"}:{inb.port ?? "—"}
          </span>
          <span style={{ opacity: 0.4 }}>•</span>
          <span>شناسه {faNum(inb.id)}</span>
        </div>
      </div>
    </label>
  );
}

/**
 * تنظیم اینباند — برای خودِ مالک، یا برای یک نماینده.
 *
 * `tenant` که داده شود یعنی «اینباندِ همین نماینده». بدون آن، همان
 * رفتار قبلی: مستاجر ریشه.
 *
 * فهرستِ اینباندها در هر دو حالت از پنل x-ui مالک خوانده می‌شود —
 * نماینده پنل جدا ندارد. چیزی که فرق می‌کند فقط *انتخاب* است.
 */
export function BotInboundsSection({ password, tenant = null }) {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [mode, setMode] = useState("all");
  const [sel, setSel] = useState([]);

  const load = async () => {
    setLoading(true);
    try {
      const q = tenant ? `?tenant=${encodeURIComponent(tenant)}` : "";
      const r = await fetch(`${API_URL}/api/admin/bot/inbounds` + q, {
        headers: { "X-Admin-Password": password },
      }).then((x) => okJson(x));
      setD(r);
      setMode(r.mode || "all");
      setSel(Array.isArray(r.selected) ? r.selected : []);
    } catch (e) {
      setD({ ready: false, error: errMsg(e), inbounds: [] });
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [password, tenant]);
  useEffect(() => { if (msg) { const x = setTimeout(() => setMsg(null), 4000); return () => clearTimeout(x); } }, [msg]);

  const inbounds = d?.inbounds || [];
  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const same = (a, b) =>
    JSON.stringify([...(a || [])].sort((x, y) => x - y)) ===
    JSON.stringify([...(b || [])].sort((x, y) => x - y));
  const dirty = !!d?.ready && (mode !== (d.mode || "all") || !same(sel, d.selected));
  // بک‌اند در حالت custom با لیست خالی ۴۰۰ می‌دهد؛ جلوترش را همین‌جا می‌گیریم.
  const blocked = mode === "custom" && sel.length === 0;

  const defInb = inbounds.find((i) => String(i.id) === String(d?.default));
  const active = inbounds.filter((i) => i.enable);

  const save = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/bot/inbounds`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify(tenant ? { mode, ids: sel, tenant }
                                    : { mode, ids: sel }),
      });
      const j = await res.json().catch(() => ({}));
      if (res.ok) {
        setD({ ...d, mode: j.mode ?? mode, selected: j.ids ?? sel });
        setSel(j.ids ?? sel);
        setMsg({ t: "ok", m: "تنظیم اینباندها ذخیره شد" });
      } else {
        setMsg({ t: "err", m: errText(j.detail, "ذخیره ناموفق بود") });
      }
    } catch {
      setMsg({ t: "err", m: "اتصال برقرار نشد" });
    } finally { setSaving(false); }
  };

  if (loading) {
    return <PageSkeleton />;
  }

  return (
    <div className="fx-anim">
      <SectionHead title="اینباندها"
        desc="مشخص کن کانفیگ هر مشتری روی کدام اینباندهای پنل ساخته شود — با نام، نه با شماره."
        action={
          <div className="flex items-center gap-2">
            {dirty && <StatusChip dirty />}
            <button onClick={load} disabled={saving}
              className="fx-btn-g px-3 py-2.5 text-[13px] flex items-center gap-1.5">
              <RefreshCw size={13} /> بازخوانی
            </button>
            <button onClick={save} disabled={saving || !d?.ready || blocked || !dirty}
              className="fx-btn px-4 py-2.5 text-[14px] flex items-center gap-1.5">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} ذخیره
            </button>
          </div>
        } />

      <Msg msg={msg} />

      {/* وضعیت اینباندها در یک نگاه — «اینباند تعریف نشده» یکی از
          پرتکرارترین شکایت‌ها بود و جوابش همین سه عدد است */}
      {d?.ready && inbounds.length > 0 && (
        <div className="fx-g3 grid grid-cols-3 gap-3">
          <StatTile label="اینباند فعال" icon={Layers}
            tone={active.length ? "var(--ok)" : "var(--danger)"}
            value={faNum(active.length)}
            color={active.length ? "var(--ok)" : "var(--danger)"}
            hint={inbounds.length - active.length > 0
                  ? `${faNum(inbounds.length - active.length)} اینباند خاموش`
                  : "همه‌ی اینباندها روشن‌اند"} />
          <StatTile label="انتخاب‌شده برای ربات" icon={Check} tone="var(--accent-2)"
            value={mode === "all" ? faNum(active.length) : faNum(sel.length)}
            hint={mode === "all" ? "همه‌ی اینباندهای فعال" : "فقط انتخاب‌شده‌ها"} />
          <StatTile label="پیش‌فرض" icon={Star}
            tone={defInb ? "var(--accent-2)" : "var(--warn)"}
            value={defInb ? (defInb.remark || `#${defInb.id}`) : "تعیین نشده"}
            color={defInb ? "var(--text)" : "var(--warn)"}
            hint={defInb ? "کانفیگ‌های تازه این‌جا ساخته می‌شوند"
                         : "بدون آن، ساخت کانفیگ می‌خوابد"} />
        </div>
      )}

      {!d?.ready ? (
        <div className="fx-card p-5">
          <div className="text-[14px] font-semibold text-white mb-2 flex items-center gap-2">
            <AlertTriangle size={15} style={{ color: "var(--warn)" }} /> اینباندها خوانده نشد
          </div>
          <p className="text-[13px] leading-relaxed" style={{ color: "var(--dim)" }}>
            {d?.error || "اتصال پنل تنظیم نشده است."}
          </p>
          <InfoBox tone="warn">
            برای خواندن اینباندها، اول باید آدرس و رمز پنل در بخش <b>«اتصال و تنظیمات»</b> ثبت
            و تست شده باشد. بعد از آن این صفحه را دوباره باز کن.
          </InfoBox>
        </div>
      ) : (
        <>
          <div className="fx-card p-5 mb-4">
            <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
              <Network size={15} style={{ color: "var(--accent-2)" }} /> کانفیگ روی کدام اینباندها ساخته شود؟
            </div>
            <p className="text-[13px] mb-4" style={{ color: "var(--muted)" }}>
              پنل الان <b style={{ color: "var(--dim)" }}>{faNum(inbounds.length)}</b> اینباند دارد که{" "}
              <b style={{ color: "var(--dim)" }}>{faNum(active.length)}</b> تای آن فعال است.
            </p>

            <div className="fx-g3 grid grid-cols-3 gap-2.5">
              {INBOUND_MODES.map((m) => {
                const on = mode === m.key;
                return (
                  <button key={m.key} onClick={() => setMode(m.key)}
                    className="p-3.5 rounded-xl text-right transition-all"
                    style={{
                      background: on ? "var(--accent-soft)" : "var(--surface-3)",
                      border: `1px solid ${on ? "var(--accent-2)" : "var(--border)"}`,
                    }}>
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <span className="shrink-0 flex items-center justify-center"
                        style={{
                          width: 15, height: 15, borderRadius: "50%",
                          border: `1.5px solid ${on ? "var(--accent-2)" : "var(--border-2)"}`,
                        }}>
                        {on && <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent-2)" }} />}
                      </span>
                      <span className="text-[13px] font-bold" style={{ color: on ? "var(--accent-2)" : "var(--dim)" }}>
                        {m.title}
                      </span>
                      {m.tag && (
                        <span className="text-[11px] px-1.5 py-0.5 rounded"
                          style={{ background: "var(--ok-soft)", color: "var(--ok)" }}>
                          {m.tag}
                        </span>
                      )}
                    </div>
                    <div className="text-[12px] leading-relaxed" style={{ color: "var(--muted)" }}>
                      {m.desc}
                    </div>
                  </button>
                );
              })}
            </div>

            {mode === "default" && (
              <InfoBox>
                {defInb ? (
                  <>اینباند پیش‌فرض الان <b>{defInb.remark}</b> است (
                    <span dir="ltr" style={{ fontFamily: "var(--mono)" }}>
                      {defInb.protocol}:{defInb.port}
                    </span>). تغییرش در «اتصال و تنظیمات» انجام می‌شود.</>
                ) : (
                  <>هنوز اینباند پیش‌فرضی ثبت نشده. تا وقتی ثبت نشود ربات به اولین اینباند فعال وصل می‌شود —
                    بهتر است در «اتصال و تنظیمات» یکی را مشخص کنی.</>
                )}
              </InfoBox>
            )}
          </div>

          {mode === "custom" ? (
            <div className="fx-card p-5">
              <div className="flex items-center justify-between gap-3 mb-1 flex-wrap">
                <div className="text-[14px] font-semibold text-white flex items-center gap-2">
                  <Layers size={15} style={{ color: "var(--accent-2)" }} /> اینباندهای انتخاب‌شده
                  <span className="text-[13px] font-normal" style={{ color: "var(--muted)" }}>
                    ({faNum(sel.length)} از {faNum(inbounds.length)})
                  </span>
                </div>
                <button
                  onClick={() => setSel(sel.length === active.length ? [] : active.map((i) => i.id))}
                  className="fx-btn-g px-3 py-2 text-[13px]">
                  {sel.length === active.length ? "هیچ‌کدام" : "همه‌ی فعال‌ها"}
                </button>
              </div>
              <p className="text-[13px] mb-4" style={{ color: "var(--muted)" }}>
                اینباند غیرفعال هم قابل انتخاب است، ولی تا وقتی در پنل روشن نشود کانفیگی رویش ساخته نمی‌شود.
              </p>

              {inbounds.length === 0 ? (
                <EmptyState icon={Network} text="پنل هیچ اینباندی ندارد"
                  hint="تا وقتی در 3x-ui حداقل یک اینباند نسازید، ربات نمی‌تواند کانفیگ بسازد." />
              ) : (
                inbounds.map((i) => (
                  <InboundRow key={i.id} inb={i} checked={sel.includes(i.id)} onToggle={toggle} />
                ))
              )}

              {blocked && (
                <InfoBox tone="warn">
                  در حالت انتخاب دستی باید <b>حداقل یک اینباند</b> تیک بخورد، وگرنه ربات نمی‌تواند کانفیگ بسازد.
                </InfoBox>
              )}
            </div>
          ) : inbounds.length > 0 ? (
            <div className="fx-card p-5">
              <div className="text-[14px] font-semibold text-white mb-3 flex items-center gap-2">
                <Layers size={15} style={{ color: "var(--muted)" }} /> اینباندهای پنل
              </div>
              {/* دو ستون روی دسکتاپ: هر ردیف فقط نام و پروتکل دارد و در
                  تمام‌عرض، دو سومِ نوار خالی می‌ماند */}
              <div className="grid gap-2 sm:grid-cols-2">
              {inbounds.map((i) => {
                const used = mode === "all" ? i.enable : String(i.id) === String(d?.default);
                return (
                  <div key={i.id} className="flex items-center gap-3 p-3 rounded-xl min-w-0"
                    style={{ background: "var(--surface-3)", border: "1px solid var(--border)", opacity: used ? 1 : 0.45 }}>
                    {used
                      ? <CheckCircle2 size={15} style={{ color: "var(--ok)", flexShrink: 0 }} />
                      : <Circle size={15} style={{ color: "var(--muted)", flexShrink: 0 }} />}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[14px] font-semibold text-white truncate">{i.remark}</span>
                        {!i.enable && (
                          <span className="text-[11px] px-1.5 py-0.5 rounded"
                            style={{ background: "var(--danger-soft)", color: "var(--danger)" }}>
                            غیرفعال
                          </span>
                        )}
                      </div>
                      <div className="text-[12px] mt-1 flex items-center gap-2" style={{ color: "var(--muted)" }}>
                        <span dir="ltr" style={{ fontFamily: "var(--mono)" }}>
                          {i.protocol || "—"}:{i.port ?? "—"}
                        </span>
                        <span style={{ opacity: 0.4 }}>•</span>
                        <span>شناسه {faNum(i.id)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
              </div>
            </div>
          ) : (
            <EmptyState icon={Network} text="پنل هیچ اینباندی ندارد"
                  hint="تا وقتی در 3x-ui حداقل یک اینباند نسازید، ربات نمی‌تواند کانفیگ بسازد." />
          )}
        </>
      )}
    </div>
  );
}
