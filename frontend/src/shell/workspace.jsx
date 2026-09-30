/**
 * پوسته‌ی پنل و سوییچ فضای کاری.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState } from "react";
import {
  Bot, Check, ChevronDown, Circle,
} from "lucide-react";
import { WORKSPACES, WS_COLOR } from "../lib/constants";
import { NavAlert, NavIndicator, SectionHead } from "../ui/index";
import { ProMark } from "../ui/pro";

export function ComingSoon({ title, desc, features }) {
  return (
    <div className="fx-anim">
      <SectionHead title={title} desc={desc} />
      <div className="fx-card fx-empty">
        <div className="fx-ico mx-auto mb-4" style={{ width: 52, height: 52, background: "var(--warn-soft)" }}>
          <Bot size={24} style={{ color: "var(--warn)" }} />
        </div>
        <div className="text-[16px] font-bold text-white mb-2">در حال توسعه</div>
        <p className="text-[13px] mb-6 max-w-md mx-auto leading-relaxed" style={{ color: "var(--muted)" }}>
          این بخش هنوز فعال نیست. تنظیماتی که در بخش «اتصال و تنظیمات» ذخیره می‌کنید،
          به‌محض آماده شدن ربات خودکار استفاده می‌شوند.
        </p>
        {features && (
          <div className="max-w-sm mx-auto text-right">
            <div className="text-[13px] mb-2.5" style={{ color: "var(--dim)" }}>قابلیت‌های برنامه‌ریزی‌شده:</div>
            {features.map((f, i) => (
              <div key={i} className="flex items-center gap-2 py-1.5">
                <Circle size={5} fill="var(--muted)" strokeWidth={0} />
                <span className="text-[13px]" style={{ color: "var(--muted)" }}>{f}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * مودال ساده — از React Portal روی body.
 *
 * داخل main که overflow دارد کار نمی‌کند و بریده می‌شود؛ این را
 * قبلاً یک‌بار یاد گرفتیم.
 */
/** مینیاتور کوچک هر حالت — تا بدون امتحان کردن بفهمید چه شکلی است. */
export function WsModePreview({ mode, active }) {
  const line = (w, on) => (
    <div style={{
      height: 4, width: w, borderRadius: 2,
      background: on ? "var(--accent)" : "var(--hair-3)",
    }} />
  );

  return (
    <div className="rounded-xl p-2.5 flex gap-1.5"
      style={{
        height: 58,
        background: active ? "var(--scrim-1)" : "var(--scrim-1)",
        boxShadow: "0 2px 8px var(--scrim-2) inset",
      }}>
      {mode === "rail" && (
        <div className="flex flex-col gap-1 shrink-0">
          {[0, 1, 2].map((i) => (
            <div key={i} style={{
              width: 8, height: 8, borderRadius: 3,
              background: i === 1 ? "var(--accent)" : "var(--hair-3)",
            }} />
          ))}
        </div>
      )}

      <div className="flex-1 flex flex-col gap-1.5 min-w-0">
        {mode === "dropdown" && (
          <>
            <div className="rounded-md flex items-center px-1.5"
              style={{ height: 13, background: "var(--hair-2)" }}>
              {line(18, true)}
            </div>
            <div className="flex flex-col gap-1 pr-1">
              {line(26, false)}{line(20, false)}{line(23, false)}
            </div>
          </>
        )}

        {mode === "accordion" && (
          <>
            {line(24, true)}
            <div className="flex flex-col gap-1 pr-2"
              style={{ borderRight: "1px solid var(--accent-line)" }}>
              {line(18, false)}{line(15, false)}
            </div>
            {line(22, false)}
          </>
        )}

        {mode === "rail" && (
          <div className="flex flex-col gap-1.5 pt-0.5">
            {line(26, false)}{line(20, false)}{line(23, false)}
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════ سوییچ فضای کاری ═══════════════════ */

/**
 * جابه‌جایی بین فضاهای کاری.
 *
 * سه حالت دارد چون سلیقه‌ها فرق می‌کند و این پنل قرار است فروخته شود.
 * حالت از تنظیمات می‌آید و در localStorage می‌ماند.
 */
export function WorkspaceSwitch({ mode, workspace, onSwitch, active, setActive,
                                 alerts = {} }) {
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState(null);
  const spaces = Object.values(WORKSPACES);
  const cur = WORKSPACES[workspace];

  /* ── تاشو ── */
  if (mode === "accordion") {
    return (
      <div className="mb-2">
        {spaces.map((w) => {
          const on = workspace === w.key;
          const col = WS_COLOR[w.key] || "var(--accent-2)";
          return (
            <div key={w.key} className="mb-1">
              <button title="باز کردن این بخش" data-navhead={w.key}
                onClick={() => onSwitch(w.key)}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-right transition-all"
                style={{
                  background: on ? `color-mix(in srgb, ${col} 10%, transparent)` : "transparent",
                  border: `1px solid ${on ? `color-mix(in srgb, ${col} 22%, transparent)` : "transparent"}`,
                }}>
                <w.icon size={15} style={{ color: on ? col : "var(--muted)", flexShrink: 0 }} />
                <span className="flex-1 text-[13px] truncate"
                  style={{ color: on ? "var(--text)" : "var(--dim)", fontWeight: on ? 700 : 500 }}>
                  {w.label}
                </span>
                <ChevronDown size={12} style={{
                  color: "var(--muted)", flexShrink: 0,
                  transform: on ? "rotate(180deg)" : "none",
                  transition: "transform .25s cubic-bezier(.22,1,.36,1)",
                }} />
              </button>

              {on && (
                <div className="mt-1 pr-2.5 mr-4 relative"
                  style={{ borderRight: `1px solid color-mix(in srgb, ${col} 22%, transparent)` }}>
                  <NavIndicator activeKey={active} />
                  {/* برچسبِ گروه فقط وقتی بیش از یک گروه هست. تا ۱.۱۲۲ گروه‌ها
                      این‌جا با flatMap یکی می‌شدند و «ربات» ۱۷ موردِ پشتِ هم
                      بی‌هیچ دسته‌ای بود — چشم باید همه را می‌خواند. */}
                  {w.groups.flatMap((g, gi) => [
                    w.groups.length > 1 && (
                      <div key={`g${gi}`} className="fx-nav-group">{g.title}</div>
                    ),
                    ...g.items.map((it) => ({ ...it, _g: gi })),
                  ]).map((it) => {
                    // برچسبِ گروه خودش عنصرِ React است (و `.key` دارد) — مستقیم برمی‌گردد
                    if (!it || React.isValidElement(it)) return it || null;
                    const sel = active === it.key;
                    return (
                      <button key={it.key} data-navkey={it.key} onClick={() => setActive(it.key)}
                        aria-current={sel ? "page" : undefined}
                        className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg mb-0.5 text-right transition-colors relative"
                        style={{
                          background: "transparent",
                          color: sel ? "var(--text)" : "var(--muted)",
                          fontWeight: sel ? 600 : 400,
                        }}>
                        <it.icon size={12} style={{ flexShrink: 0 }} />
                        <span className="flex-1 text-[13px] truncate">{it.label}</span>
                        <ProMark feature={it.pro} />
                        {it.badge && (
                          <span className="text-[10.5px] px-1.5 py-0.5 rounded-full shrink-0"
                            style={{ background: "var(--hair-2)", color: "var(--muted)" }}>
                            {it.badge}
                          </span>
                        )}
                        {/* همان نشانِ `App.jsx` — از یک کامپوننت، نه دو
                            تکه‌ی جدا. حالتِ تاشو پیش‌فرض است، پس اگر
                            فقط آن‌جا اضافه شود، نشان هیچ‌وقت دیده
                            نمی‌شود. */}
                        {!it.badge && it.alert && <NavAlert count={alerts[it.alert]} />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  /* ── نوار آیکون ── */
  if (mode === "rail") {
    return (
      <div className="flex gap-1.5 mb-4 px-1">
        {spaces.map((w) => {
          const on = workspace === w.key;
          const col = WS_COLOR[w.key] || "var(--accent-2)";
          return (
            <div key={w.key} className="relative flex-1"
              onMouseEnter={() => setHover(w.key)} onMouseLeave={() => setHover(null)}>
              <button data-navhead={w.key} onClick={() => onSwitch(w.key)}
                className="w-full flex items-center justify-center rounded-xl transition-all"
                style={{
                  height: 42,
                  background: on ? `color-mix(in srgb, ${col} 14%, transparent)` : "transparent",
                  border: `1px solid ${on ? `color-mix(in srgb, ${col} 28%, transparent)` : "var(--border)"}`,
                  boxShadow: on
                    ? `0 1px 0 var(--hair-2) inset, 0 6px 14px -6px color-mix(in srgb, ${col} 55%, transparent)`
                    : "none",
                }}>
                <w.icon size={17} style={{ color: on ? col : "var(--muted)" }} />
              </button>

              {hover === w.key && (
                <div className="absolute z-30 whitespace-nowrap rounded-xl px-3 py-2 fx-fade"
                  style={{
                    top: "calc(100% + 7px)", right: 0,
                    background: "var(--surface-2)", border: "1px solid var(--border-2)",
                    boxShadow: "0 12px 28px -8px var(--scrim-3)",
                  }}>
                  <div className="text-[13px] font-bold text-white">{w.label}</div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  /* ── کشویی (پیش‌فرض) ── */
  const col = WS_COLOR[workspace] || "var(--accent-2)";
  return (
    <div className="relative mb-4">
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-right"
        style={{
          background: "var(--surface-2)", border: "1px solid var(--border-2)",
          boxShadow: "0 1px 0 var(--hair-2) inset",
        }}>
        <div className="rounded-[10px] flex items-center justify-center shrink-0"
          style={{
            width: 30, height: 30,
            background: `color-mix(in srgb, ${col} 14%, transparent)`,
            boxShadow: "0 1px 0 var(--hair-3) inset",
          }}>
          <cur.icon size={15} style={{ color: col }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-bold text-white truncate">{cur.label}</div>
          <div className="text-[11px] mt-0.5" style={{ color: "var(--muted)" }}>فضای کاری</div>
        </div>
        <ChevronDown size={14} style={{
          color: "var(--muted)", flexShrink: 0,
          transform: open ? "rotate(180deg)" : "none", transition: "transform .22s",
        }} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute z-20 left-0 right-0 rounded-2xl p-1.5 fx-scale"
            style={{
              top: "calc(100% + 6px)",
              background: "var(--surface)", border: "1px solid var(--border-2)",
              boxShadow: "0 18px 40px -12px var(--scrim-4)",
            }}>
            {spaces.map((w) => {
              const on = workspace === w.key;
              const c2 = WS_COLOR[w.key] || "var(--accent-2)";
              return (
                <button title="رفتن به این بخش" key={w.key} data-navhead={w.key}
                  onClick={() => { onSwitch(w.key); setOpen(false); }}
                  className="w-full flex items-center gap-2.5 px-2.5 py-2.5 rounded-xl text-right transition-colors"
                  style={{ background: on ? `color-mix(in srgb, ${c2} 12%, transparent)` : "transparent" }}>
                  <w.icon size={14} style={{ color: on ? c2 : "var(--muted)", flexShrink: 0 }} />
                  <span className="flex-1 text-[13px] truncate"
                    style={{ color: on ? "var(--text)" : "var(--dim)", fontWeight: on ? 700 : 500 }}>
                    {w.label}
                  </span>
                  {on && <Check size={12} style={{ color: c2, flexShrink: 0 }} />}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
