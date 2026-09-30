/**
 * سیستم، به‌روزرسانی و گیت‌هاب.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect, useRef } from "react";
import {
  AlertTriangle, Check, CheckCircle2, Download, ExternalLink, Github, HardDrive, History, Loader2, Minus, Monitor, Plus, RefreshCw, Save, Server, Smartphone, Terminal, Users,
} from "lucide-react";
import { errText, faNum, okJson } from "../lib/format";
import { API_URL } from "../lib/constants";
import { Collapse, ConfirmModal, Field, InfoBox, MiniMarkdown, Msg, PageSkeleton, SectionHead } from "../ui/index";
import { isoToJalaliLabel, isoToJalaliStamp } from "../ui/jalali";
import { LicenseCard } from "./license";

export function RollbackCard({ password }) {
  const [snaps, setSnaps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState(null);
  const [keepSettings, setKeepSettings] = useState(true);
  const [msg, setMsg] = useState(null);
  const [loadErr, setLoadErr] = useState("");

  const load = async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/snapshots`, {
        headers: { "X-Admin-Password": password } });
      const d = await okJson(res, "خواندنِ نسخه‌های ذخیره‌شده ناموفق بود");
      setSnaps(d.snapshots || []);
      setLoadErr("");
    } catch (e) { setLoadErr(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [password]);
  useEffect(() => { if (msg) { const t = setTimeout(() => setMsg(null), 5000); return () => clearTimeout(t); } }, [msg]);

  const run = async () => {
    const id = confirm.id;
    setConfirm(null);
    try {
      const res = await fetch(`${API_URL}/api/admin/rollback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify({ id, keepSettings }),
      });
      const d = await res.json();
      if (res.ok) {
        setMsg({ t: "ok", m: "بازگشت شروع شد — صفحه تا لحظاتی دیگر بارگذاری می‌شود" });
        setTimeout(() => window.location.reload(), 45000);
      } else setMsg({ t: "err", m: errText(d.detail, "بازگشت ناموفق") });
    } catch { setMsg({ t: "err", m: "اتصال برقرار نشد" }); }
  };

  if (loading) return null;

  return (
    <div className="fx-card p-5 mb-4">
      <div className="flex items-center gap-2 mb-1">
        <History size={15} style={{ color: "var(--warn)" }} />
        <span className="text-[14px] font-semibold text-white">بازگشت به نسخه قبلی</span>
      </div>
      <p className="text-[13px] mb-4 leading-relaxed" style={{ color: "var(--muted)" }}>
        قبل از هر به‌روزرسانی یک نسخه‌ی کامل ذخیره می‌شود و پنج نسخه‌ی آخر نگه داشته می‌شوند.
        وضعیت فعلی هم قبل از بازگشت ذخیره می‌شود، پس همیشه می‌توانید دوباره جلو بروید.
      </p>

      <Msg msg={msg} />

      {/* خطای خواندن «هنوز نسخه‌ای نیست» نیست. درست وقتی کسی بعد از یک
          به‌روزرسانیِ خراب دنبالِ راهِ برگشت است، این دروغ یعنی فکر کند
          راهی نیست. */}
      {loadErr ? (
        <Msg msg={{ t: "err", m: `فهرستِ نسخه‌ها خوانده نشد: ${loadErr}` }} />
      ) : snaps.length === 0 ? (
        <div className="text-center py-6 text-[13px]" style={{ color: "var(--muted)" }}>
          هنوز نسخه‌ی ذخیره‌شده‌ای نیست — با اولین به‌روزرسانی ساخته می‌شود
        </div>
      ) : (
        <>
          <label className="flex items-center gap-2 text-[13px] mb-3 cursor-pointer" style={{ color: "var(--dim)" }}>
            <input type="checkbox" checked={keepSettings} onChange={(e) => setKeepSettings(e.target.checked)}
              style={{ accentColor: "var(--accent)" }} />
            تنظیمات فعلی حفظ شود (توصیه می‌شود)
          </label>

          <div className="mt-4">
          {snaps.map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-3 p-3.5 rounded-xl mb-3 flex-wrap"
              style={{ background: "var(--surface-3)", border: "1px solid var(--border)" }}>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[14px] font-semibold text-white">نسخه {s.version}</span>
                  {s.hasBot && <span className="fx-pill" style={{ background: "var(--accent-soft)", color: "var(--accent-2)" }}>شامل ربات</span>}
                </div>
                <div className="text-[12px] mt-1" style={{ color: "var(--muted)", fontFamily: "var(--mono)" }}>
                  {isoToJalaliStamp(s.createdAt)} · {s.sizeMb} MB
                </div>
              </div>
              <button onClick={() => setConfirm(s)}
                className="fx-btn-g px-3.5 py-2.5 text-[13px] shrink-0" style={{ color: "var(--warn)" }}>
                بازگشت به این نسخه
              </button>
            </div>
          ))}
          </div>
        </>
      )}

      {confirm && (
        <ConfirmModal
          title={`بازگشت به نسخه ${confirm.version}؟`}
          desc={`پنل به وضعیت ${isoToJalaliLabel(confirm.createdAt)} برمی‌گردد و حدود یک دقیقه در دسترس نخواهد بود.${keepSettings ? " تنظیمات فعلی حفظ می‌شود." : " تنظیمات هم به همان نسخه برمی‌گردد."}`}
          confirmLabel="بله، برگرد"
          onConfirm={run}
          onCancel={() => setConfirm(null)} />
      )}
    </div>
  );
}

export function GithubCard({ password }) {
  const [repo, setRepo] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const load = async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/github`, {
        headers: { "X-Admin-Password": password },
      });
      const d = await okJson(res, "خواندنِ مخزن ناموفق بود");
      setRepo(d.repo || "");
      setSaved(d.repo || "");
    } catch (e) {
      // خالی ماندنِ فیلد یعنی «تنظیم نشده»؛ خطا باید جدا گفته شود
      setMsg({ t: "err", m: e.message });
    }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [password]);
  useEffect(() => { if (msg) { const t = setTimeout(() => setMsg(null), 5000); return () => clearTimeout(t); } }, [msg]);

  const save = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/github`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Admin-Password": password },
        body: JSON.stringify({ repo }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        setSaved(d.repo || "");
        setRepo(d.repo || "");
        setMsg({ t: "ok", m: d.latestTag
          ? `متصل شد — آخرین نسخه: ${d.latestTag}`
          : "ذخیره شد" });
      } else {
        setMsg({ t: "err", m: errText(d.detail, "ذخیره ناموفق بود") });
      }
    } catch { setMsg({ t: "err", m: "اتصال به سرور برقرار نشد" }); }
    finally { setBusy(false); }
  };

  if (loading) return null;

  const dirty = repo.trim() !== saved;

  return (
    <div className="fx-card p-5 mb-4">
      <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
        <Github size={15} style={{ color: "var(--accent-2)" }} /> مخزن به‌روزرسانی
      </div>
      <p className="text-[13px] mb-4 leading-relaxed" style={{ color: "var(--muted)" }}>
        وقتی مخزن را وصل کنید، پنل نسخه‌های جدید را از Releases گیت‌هاب می‌گیرد
        و به‌روزرسانی از همین‌جا انجام می‌شود.
      </p>

      <Field label="آدرس مخزن" hint="مثلاً username/nexora — یا لینک کامل گیت‌هاب">
        <div className="flex gap-2">
          <input className="fx-input" dir="ltr" value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="username/nexora"
            onKeyDown={(e) => e.key === "Enter" && dirty && save()}
            style={{ fontFamily: "var(--mono)" }} />
          <button title="ذخیره" onClick={save} disabled={busy || !dirty}
            className="fx-btn px-4 py-2.5 text-[14px] shrink-0 flex items-center gap-1.5"
            style={!dirty ? { opacity: 0.45, cursor: "not-allowed" } : {}}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            {busy ? "بررسی..." : "اتصال"}
          </button>
        </div>
      </Field>

      {msg && (
        <div className="rounded-xl p-3 mb-3 flex items-start gap-2 text-[13px] leading-relaxed"
          style={{
            background: msg.t === "err" ? "var(--danger-soft)" : "var(--ok-soft)",
            border: `1px solid ${msg.t === "err" ? "var(--danger-line)" : "var(--ok-line)"}`,
            color: msg.t === "err" ? "var(--danger)" : "var(--ok)",
          }}>
          {msg.t === "err" ? <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                           : <CheckCircle2 size={14} className="shrink-0 mt-0.5" />}
          <span>{msg.m}</span>
        </div>
      )}

      {saved ? (
        <div className="flex items-center gap-2 text-[13px]" style={{ color: "var(--ok)" }}>
          <CheckCircle2 size={13} />
          متصل به{" "}
          <a href={`https://github.com/${saved}`} target="_blank" rel="noreferrer"
            dir="ltr" className="underline"
            style={{ color: "var(--accent-2)", fontFamily: "var(--mono)" }}>
            {saved}
          </a>
        </div>
      ) : (
        <InfoBox>
          <b>قبل از اتصال:</b> مخزن باید عمومی باشد و حداقل یک Release داشته باشد.
          پنل هنگام اتصال این را بررسی می‌کند.
        </InfoBox>
      )}
    </div>
  );
}

export function UpdateCard({ password }) {
  const [info, setInfo] = useState(null);
  const [checking, setChecking] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [stuck, setStuck] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const finishRef = React.useRef(null);
  const [log, setLog] = useState([]);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const [checkErr, setCheckErr] = useState("");
  const check = async () => {
    setChecking(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/check-update`, { headers: { "X-Admin-Password": password } });
      setInfo(await okJson(res, "بررسیِ نسخه ناموفق بود"));
      setCheckErr("");
    } catch (e) { setCheckErr(e.message); }
    finally { setChecking(false); }
  };

  useEffect(() => { check(); }, [password]);

  // در حین به‌روزرسانی، لاگ را دنبال می‌کنیم.
  // نکته‌ی مهم: سرویس وسط کار ری‌استارت می‌شود، پس درخواست‌ها موقتاً شکست
  // می‌خورند. برای همین چند محافظ لازم است تا صفحه گیر نکند:
  //   ۱. سقف زمانی کلی (۶ دقیقه) — بعد از آن به‌هرحال رفرش می‌کنیم
  //   ۲. تشخیص بازگشت سرویس: اگر بعد از قطعی دوباره سالم شد، یعنی تمام شده
  //   ۳. رفرش خودکار در هر حالت پایان
  useEffect(() => {
    if (!updating) return;

    let elapsed = 0;
    let sawDowntime = false;
    let quiet = 0;          // چند بار پشت سر هم لاگ بدون تغییر ماند
    let lastLen = 0;
    let done = false;

    const finish = (delay = 2200) => {
      if (done) return;
      done = true;
      clearInterval(timer);
      setUpdating(false);
      setTimeout(() => window.location.reload(), delay);
    };
    finishRef.current = finish;

    const timer = setInterval(async () => {
      elapsed += 2000;
      setElapsedSec(Math.floor(elapsed / 1000));

      // سقف کلی — ۴ دقیقه کافی است؛ بیشتر یعنی چیزی خراب شده
      if (elapsed > 240000) {
        setLog((l) => [...l, "— زمان انتظار تمام شد —"]);
        setStuck(true);
        clearInterval(timer);
        return;
      }

      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 4000);
        const res = await fetch(`${API_URL}/api/admin/update-log?_t=${Date.now()}`, {
          headers: { "X-Admin-Password": password },
          cache: "no-store",
          signal: ctrl.signal,
        });
        clearTimeout(to);

        if (res.ok) {
          const d = await res.json();
          const lines = d.lines || [];
          if (lines.length) setLog(lines);

          if (d.finished || d.failed) { finish(); return; }

          // سرویس برگشته بعد از قطعی → کار تمام است
          if (sawDowntime) {
            setLog((l) => [...l, "— سرویس بازگشت —"]);
            finish(1500);
            return;
          }

          // لاگ بی‌حرکت: اگر ۳۰ ثانیه هیچ خط تازه‌ای نیامد و سرویس هم
          // سالم است، یعنی یا تمام شده یا گیر کرده. به کاربر اختیار می‌دهیم
          // به‌جای اینکه بی‌صدا منتظر بماند.
          if (lines.length === lastLen) {
            quiet += 1;
            if (quiet >= 15) {
              setStuck(true);
              clearInterval(timer);
              return;
            }
          } else {
            quiet = 0;
            lastLen = lines.length;
          }
        }
      } catch {
        // سرویس در حال ری‌استارت — طبیعی است
        sawDowntime = true;
        quiet = 0;
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [updating, password]);

  const startUpdate = async () => {
    setConfirmOpen(false);
    setStuck(false);
    setElapsedSec(0);
    setUpdating(true);
    setLog(["در حال شروع به‌روزرسانی..."]);
    try {
      await fetch(`${API_URL}/api/admin/run-update`, {
        method: "POST",
        headers: { "X-Admin-Password": password },
      });
    } catch { /* سرویس ری‌استارت می‌شود، خطا طبیعی است */ }
  };

  const hasUpdate = info?.updateAvailable;

  return (
    <>
      <div className="fx-card p-5 mb-4" style={hasUpdate ? { borderColor: "var(--ok-edge)", boxShadow: "0 0 24px var(--ok-wash)" } : {}}>
        <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="fx-ico" style={{ background: hasUpdate ? "var(--ok-soft)" : "var(--accent-soft)" }}>
              <RefreshCw size={16} className={checking ? "animate-spin" : ""}
                style={{ color: hasUpdate ? "var(--ok)" : "var(--accent-2)" }} />
            </div>
            <div className="min-w-0">
              <div className="text-[14px] font-semibold text-white">به‌روزرسانی</div>
              <div className="text-[13px] mt-0.5" style={{ color: "var(--muted)" }}>
                {checking ? "در حال بررسی..." :
                 checkErr ? "بررسیِ نسخه ناموفق بود" :
                 !info?.configured ? "به‌روزرسانی خودکار تنظیم نشده" :
                 info?.error ? "ارتباط با گیت‌هاب برقرار نشد" :
                 hasUpdate ? `نسخه ${info.latestVersion} در دسترس است` :
                 "شما آخرین نسخه را دارید"}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="fx-pill" style={{ background: "var(--hair-2)", color: "var(--muted)" }}>
              نسخه فعلی: {info?.currentVersion || "?"}
            </span>
            {!updating && (
              <button onClick={check} className="fx-btn-g px-3 py-2 text-[13px] flex items-center gap-1.5">
                <RefreshCw size={12} /> بررسی مجدد
              </button>
            )}
          </div>
        </div>

        {/* در حال به‌روزرسانی */}
        {updating && (
          <div className="rounded-xl p-4"
            style={{ background: "var(--surface-3)", border: `1px solid ${stuck ? "var(--warn-line)" : "var(--accent-halo)"}` }}>
            <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
              <div className="flex items-center gap-2">
                {stuck
                  ? <AlertTriangle size={14} style={{ color: "var(--warn)" }} />
                  : <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent-2)" }} />}
                <span className="text-[13px] font-semibold"
                  style={{ color: stuck ? "var(--warn)" : "var(--accent-2)" }}>
                  {stuck ? "پاسخی از سرور نمی‌آید" : "در حال به‌روزرسانی — صفحه را نبندید"}
                </span>
              </div>
              <span className="text-[13px]" style={{ color: "var(--muted)", fontFamily: "var(--mono)" }}>
                {Math.floor(elapsedSec / 60)}:{String(elapsedSec % 60).padStart(2, "0")}
              </span>
            </div>

            {stuck && (
              <div className="rounded-xl p-3 mb-3 text-[13px] leading-relaxed"
                style={{ background: "var(--warn-wash)", border: "1px solid var(--warn-fill)", color: "var(--dim)" }}>
                لاگی دریافت نمی‌شود. معمولاً یعنی به‌روزرسانی تمام شده و سرویس ری‌استارت شده،
                ولی گاهی هم یعنی چیزی خطا داده. یکی از گزینه‌های زیر را انتخاب کنید.
              </div>
            )}

            {stuck && (
              <div className="flex gap-2 mb-3 flex-wrap">
                <button onClick={() => window.location.reload()}
                  className="fx-btn px-4 py-2.5 text-[13px] flex items-center gap-1.5">
                  <RefreshCw size={13} /> بارگذاری مجدد پنل
                </button>
                <button onClick={() => { setStuck(false); setUpdating(false); }}
                  className="fx-btn-g px-4 py-2.5 text-[13px]">
                  بستن و ادامه کار
                </button>
              </div>
            )}
            <div className="rounded-lg p-3 max-h-52 overflow-y-auto" dir="ltr"
              style={{ background: "#05070C", border: "1px solid var(--border)" }}>
              {log.length === 0 ? (
                <div className="text-[13px]" style={{ color: "var(--muted)", fontFamily: "var(--mono)" }}>
                  waiting for output...
                </div>
              ) : log.map((l, i) => (
                <div key={i} className="text-[13px] leading-relaxed"
                  style={{ color: l.includes("✓") ? "var(--ok)" : l.includes("✗") ? "var(--danger)" : "var(--dim)",
                           fontFamily: "var(--mono)" }}>
                  {l}
                </div>
              ))}
            </div>
            <p className="text-[12px] mt-3" style={{ color: "var(--muted)" }}>
              بعد از اتمام، صفحه خودکار بارگذاری مجدد می‌شود.
            </p>
          </div>
        )}

        {/* نسخه جدید موجود است */}
        {!updating && hasUpdate && (
          <>
            <div className="rounded-xl p-4 mb-3" style={{ background: "var(--ok-wash)", border: "1px solid var(--ok-fill)" }}>
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 size={14} style={{ color: "var(--ok)" }} />
                <span className="text-[14px] font-semibold" style={{ color: "var(--ok)" }}>
                  نسخه {info.latestVersion} منتشر شده
                </span>
              </div>
              {info.releaseNotes && (
                <div className="text-[13px] leading-relaxed max-h-40 overflow-y-auto mt-2"
                  style={{ color: "var(--dim)" }}>
                  <MiniMarkdown text={info.releaseNotes} />
                </div>
              )}
            </div>

            <button onClick={() => setConfirmOpen(true)}
              className="fx-btn w-full py-3 text-[14px] flex items-center justify-center gap-2">
              <Download size={15} /> به‌روزرسانی به نسخه {info.latestVersion}
            </button>

            <p className="text-[12px] mt-2.5 text-center" style={{ color: "var(--muted)" }}>
              تنظیمات، رمز عبور و واسطه‌های شما حفظ می‌شوند
            </p>
          </>
        )}

        {/* آخرین نسخه */}
        {!updating && !hasUpdate && info?.configured && !info?.error && (
          <div className="rounded-xl p-4 flex items-center gap-2.5" style={{ background: "var(--ok-wash)", border: "1px solid var(--ok-fill)" }}>
            <CheckCircle2 size={15} style={{ color: "var(--ok)" }} />
            <span className="text-[13px]" style={{ color: "var(--dim)" }}>
              شما آخرین نسخه ({info.currentVersion}) را دارید
            </span>
          </div>
        )}

        {/* خطای خودِ پنل — پیش‌تر به شاخه‌ی «تنظیم نشده» می‌افتاد و
            دستورِ نصب نشان می‌داد، در حالی که تنظیم بود و فقط بررسی شکست */}
        {!updating && checkErr && !checking && (
          <Msg msg={{ t: "err", m: checkErr }} />
        )}

        {/* تنظیم نشده */}
        {!updating && !checkErr && !info?.configured && !checking && (
          <div className="rounded-xl p-4" style={{ background: "var(--surface-3)", border: "1px solid var(--border)" }}>
            <p className="text-[13px] mb-2.5" style={{ color: "var(--dim)" }}>
              برای فعال‌سازی به‌روزرسانی خودکار، این دستور را روی سرور اجرا کنید:
            </p>
            <code dir="ltr" className="block px-3 py-2.5 rounded-lg text-[13px]"
              style={{ background: "#05070C", border: "1px solid var(--border-2)", color: "var(--accent-2)",
                       fontFamily: "var(--mono)", wordBreak: "break-all" }}>
              echo 'GITHUB_REPO="NexoraImen/nexora-panel"' &gt; /opt/nexora-panel/.github
            </code>
            <p className="text-[12px] mt-2" style={{ color: "var(--muted)" }}>
              سپس <span dir="ltr" style={{ fontFamily: "var(--mono)" }}>nexora restart</span> را بزنید.
            </p>
          </div>
        )}

        {/* خطای اتصال */}
        {!updating && info?.error && (
          <div className="rounded-xl p-4" style={{ background: "var(--warn-wash)", border: "1px solid var(--warn-fill)" }}>
            <div className="flex items-start gap-2.5">
              <AlertTriangle size={15} className="shrink-0 mt-0.5" style={{ color: "var(--warn)" }} />
              <div>
                <div className="text-[13px] mb-1" style={{ color: "var(--warn)" }}>ارتباط با گیت‌هاب برقرار نشد</div>
                <div className="text-[12px]" style={{ color: "var(--muted)" }}>
                  ممکن است سرور به گیت‌هاب دسترسی نداشته باشد. می‌توانید از ترمینال به‌روزرسانی کنید:
                  <span dir="ltr" style={{ fontFamily: "var(--mono)" }}> nexora update</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {confirmOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 fx-fade"
          style={{ background: "var(--veil)", backdropFilter: "blur(6px)" }} onClick={() => setConfirmOpen(false)}>
          <div className="w-full max-w-sm rounded-2xl p-5 fx-scale" onClick={(e) => e.stopPropagation()}
            style={{ background: "var(--surface)", border: "1px solid var(--accent-line)" }}>
            <div className="flex items-center gap-2 mb-2.5" style={{ color: "var(--accent-2)" }}>
              <Download size={18} />
              <span className="text-[16px] font-semibold">به‌روزرسانی به {info?.latestVersion}؟</span>
            </div>
            <p className="text-[13px] mb-3 leading-relaxed" style={{ color: "var(--muted)" }}>
              سرویس برای چند دقیقه ری‌استارت می‌شود. صفحه‌ی اشتراک مشتریان در این مدت
              با تنظیمات فعلی به کار خود ادامه می‌دهد.
            </p>
            <div className="rounded-lg p-3 mb-4" style={{ background: "var(--ok-wash)", border: "1px solid var(--ok-fill)" }}>
              <div className="text-[13px] leading-relaxed" style={{ color: "var(--dim)" }}>
                قبل از شروع، یک بک‌آپ خودکار از تنظیمات گرفته می‌شود.
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setConfirmOpen(false)} className="fx-btn-g flex-1 py-2.5 text-[14px]">انصراف</button>
              <button onClick={startUpdate} className="fx-btn flex-1 py-2.5 text-[14px]">شروع به‌روزرسانی</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function SystemSection({ password }) {
  const [sys, setSys] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sysErr, setSysErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/admin/system`, { headers: { "X-Admin-Password": password } });
        setSys(await okJson(res, "خواندنِ وضعیتِ سیستم ناموفق بود"));
      } catch (e) { setSysErr(e.message); }
      finally { setLoading(false); }
    })();
  }, [password]);

  const CMD = ({ children }) => (
    <code dir="ltr" className="block px-3 py-2.5 rounded-lg text-[13px] my-1.5"
      style={{ background: "var(--surface-3)", border: "1px solid var(--border-2)",
               color: "var(--accent-2)", fontFamily: "var(--mono)" }}>
      {children}
    </code>
  );

  if (loading) {
    return <PageSkeleton />;
  }

  return (
    <div className="fx-anim">
      <SectionHead title="سیستم و به‌روزرسانی" desc="وضعیت نصب، نسخه‌ی فعلی و راهنمای به‌روزرسانی." />
      {/* بی‌این، هر چهار کاشی «?» می‌گفتند و دلیلش هیچ‌جا نبود */}
      {sysErr && <Msg msg={{ t: "err", m: sysErr }} />}

      <LicenseCard password={password} />

      {/* وضعیت */}
      <div className="fx-g4 grid grid-cols-4 gap-3 mb-4">
        <div className="fx-card p-4">
          <div className="fx-ico mb-3" style={{ background: "var(--accent-soft)" }}>
            <Server size={16} style={{ color: "var(--accent-2)" }} />
          </div>
          <div className="text-[18px] font-bold text-white" style={{ fontFamily: "var(--mono)" }}>
            {sys?.version || "?"}
          </div>
          <div className="text-[13px] mt-1" style={{ color: "var(--dim)" }}>نسخه فعلی</div>
        </div>

        <div className="fx-card p-4">
          <div className="fx-ico mb-3" style={{ background: sys?.template?.exists ? "var(--ok-soft)" : "var(--danger-soft)" }}>
            <HardDrive size={16} style={{ color: sys?.template?.exists ? "var(--ok)" : "var(--danger)" }} />
          </div>
          <div className="text-[16px] font-bold" style={{ color: sys?.template?.exists ? "var(--ok)" : "var(--danger)" }}>
            {sys?.template?.exists ? "نصب شده" : "پیدا نشد"}
          </div>
          <div className="text-[13px] mt-1" style={{ color: "var(--dim)" }}>قالب صفحه اشتراک</div>
          {sys?.template?.size > 0 && (
            <div className="text-[12px] mt-0.5" style={{ color: "var(--muted)" }}>
              {(sys.template.size / 1024).toFixed(0)} KB
            </div>
          )}
        </div>

        <div className="fx-card p-4">
          <div className="fx-ico mb-3" style={{ background: "var(--purple-soft)" }}>
            <Smartphone size={16} style={{ color: "var(--purple)" }} />
          </div>
          <div className="text-[18px] font-bold text-white" style={{ fontFamily: "var(--mono)" }}>
            {faNum(sys?.counts?.apps ?? 0)}
          </div>
          <div className="text-[13px] mt-1" style={{ color: "var(--dim)" }}>اپلیکیشن</div>
        </div>

        <div className="fx-card p-4">
          <div className="fx-ico mb-3" style={{ background: "var(--warn-soft)" }}>
            <Users size={16} style={{ color: "var(--warn)" }} />
          </div>
          <div className="text-[18px] font-bold text-white" style={{ fontFamily: "var(--mono)" }}>
            {faNum(sys?.counts?.resellers ?? 0)}
          </div>
          <div className="text-[13px] mt-1" style={{ color: "var(--dim)" }}>واسطه</div>
        </div>
      </div>

      {/* هشدار آدرس API */}
      {sys?.template?.apiUrl?.includes("localhost") && (
        <div className="mb-4">
          <InfoBox tone="warn">
            <b>هشدار:</b> آدرس API داخل قالب روی <span dir="ltr">localhost</span> است.
            مرورگر مشتری نمی‌تواند به آن وصل شود و تنظیمات پنل اعمال نخواهد شد.
            <br />با دستور <span dir="ltr" style={{ fontFamily: "var(--mono)" }}>nexora update</span> یا اجرای مجدد نصب، آن را به دامنه‌ی واقعی تغییر دهید.
          </InfoBox>
        </div>
      )}

      {/* به‌روزرسانی */}
      {sys?.build?.stale && (
        <div className="fx-card p-4 mb-4 flex items-start gap-3"
          style={{ background: "var(--warn-wash)", borderColor: "var(--warn-line)" }}>
          <AlertTriangle size={17} style={{ color: "var(--warn)", flexShrink: 0, marginTop: 2 }} />
          <div className="flex-1">
            <div className="text-[14px] font-semibold text-white mb-1">
              پنل با کد فعلی ساخته نشده
            </div>
            <div className="text-[13px] leading-relaxed" style={{ color: "var(--dim)" }}>
              کد به‌روز است ولی صفحه‌ای که می‌بینید از بیلد قبلی است — به همین دلیل
              قابلیت‌های جدید ظاهر نمی‌شوند. معمولاً یعنی بیلد در آخرین به‌روزرسانی
              شکست خورده است.
              <br />
              <code dir="ltr" className="inline-block mt-2 px-3 py-1.5 rounded-lg text-[13px]"
                style={{ background: "var(--surface-3)", color: "var(--warn)", fontFamily: "var(--mono)" }}>
                nexora rebuild
              </code>
            </div>
          </div>
        </div>
      )}

      {/* کار اول، مرجع آخر: به‌روزرسانی و بازگشت کارهایی‌اند که برایشان به
          این صفحه می‌آیند؛ اتصالِ مخزن یک‌بار انجام می‌شود. */}
      <UpdateCard password={password} />
      <RollbackCard password={password} />
      <GithubCard password={password} />

      {/* جزئیاتِ فنی — مرجع، نه کار. قبلاً دو کارتِ همیشه‌باز بودند، یکی
          بالای صفحه، و صفحه را دو برابرِ لازم بلند می‌کردند. */}
      <Collapse title="جزئیاتِ فنی" icon={Terminal}
        hint="مسیرهای نصب و دستورهای مدیریتیِ سرور">
        <div className="text-[12.5px] font-semibold mb-2 flex items-center gap-2" style={{ color: "var(--dim)" }}>
          <HardDrive size={13} /> مسیرهای نصب
        </div>
        <div className="flex flex-col gap-2.5">
          {[
            { l: "قالب صفحه اشتراک", v: sys?.template?.path },
            { l: "فایل تنظیمات", v: sys?.configPath },
            { l: "آدرس API در قالب", v: sys?.template?.apiUrl },
          ].map((row, i) => (
            <div key={i} className="flex items-center justify-between gap-3 py-2" style={{ borderBottom: i < 2 ? "1px solid var(--border)" : "none" }}>
              <span className="text-[13px] shrink-0" style={{ color: "var(--dim)" }}>{row.l}</span>
              <span dir="ltr" className="text-[13px] truncate" style={{ color: "var(--muted)", fontFamily: "var(--mono)" }}>
                {row.v || "—"}
              </span>
            </div>
          ))}
        </div>
        <div className="text-[12.5px] font-semibold mt-5 mb-2 flex items-center gap-2" style={{ color: "var(--dim)" }}>
          <Terminal size={13} /> دستورهای مدیریتی
        </div>
        {[
          { c: "nexora status", d: "وضعیت کامل سرویس‌ها" },
          { c: "nexora logs", d: "لاگ زنده (خروج با Ctrl+C)" },
          { c: "nexora restart", d: "ری‌استارت بک‌اند" },
          { c: "nexora rebuild", d: "ساخت مجدد پنل (رفع مشکل ظاهری)" },
          { c: "nexora backup", d: "بک‌آپ فوری از تنظیمات" },
          { c: "nexora snapshots", d: "لیست نسخه‌های ذخیره‌شده" },
          { c: "nexora rollback", d: "بازگشت به نسخه قبل" },
          { c: "nexora diagnose", d: "عیب‌یابی نمایش قالب" },
        ].map((x, i, arr) => (
          <div key={i} className="flex items-center justify-between gap-3 py-2" style={{ borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none" }}>
            <code dir="ltr" className="text-[13px]" style={{ color: "var(--accent-2)", fontFamily: "var(--mono)" }}>{x.c}</code>
            <span className="text-[13px]" style={{ color: "var(--muted)" }}>{x.d}</span>
          </div>
        ))}
      </Collapse>

      <InfoBox>
        قبل از هر به‌روزرسانی، یک بک‌آپ دستی هم بگیرید: <b>تنظیمات → پشتیبان‌گیری → دریافت پشتیبان</b>
      </InfoBox>
    </div>
  );
}

export function LivePreview({ dirty, onSave, saving, password }) {
  const [key, setKey] = useState(0);
  const [device, setDevice] = useState("mobile");
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(100);
  // پهنای واقعیِ جایی که قاب در آن می‌نشیند. روی گوشی قابِ ۳۹۰ پیکسلی
  // در کارتِ ۳۵۸ پیکسلی جا نمی‌شد و سمتِ چپِ صفحه‌ی اشتراک بریده می‌شد؛
  // «۱۰۰٪» یعنی «تا جایی که جا دارد»، نه «بیرون بزن».
  const boxRef = useRef(null);
  const [boxW, setBoxW] = useState(0);
  useEffect(() => {
    const el = boxRef.current;
    if (!el || typeof ResizeObserver !== "function") return undefined;
    const ro = new ResizeObserver(([e]) => setBoxW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  /*
   * امتحانِ قالب‌ها بدونِ ذخیره.
   *
   * تا امروز حلقه این بود: قالب را عوض کن → ذخیره کن → بیا
   * پیش‌نمایش → ببین → برگرد. برای مقایسه‌ی چهار قالب یعنی چهار بار
   * ذخیره روی تنظیماتِ واقعیِ مشتری‌ها.
   *
   * `try` همان چیزی است که در نوار انتخاب می‌شود و فقط به نشانیِ
   * iframe می‌رود؛ `saved` آن چیزی است که واقعاً ذخیره شده. تا وقتی
   * دکمه‌ی «همین را انتخاب کن» زده نشود، هیچ‌چیز عوض نمی‌شود.
   */
  const [opts, setOpts] = useState({ templates: [], palettes: [] });
  const [saved, setSaved] = useState({ template: "", palette: "" });
  const [tryTpl, setTryTpl] = useState("");
  const [tryPal, setTryPal] = useState("");
  const [picking, setPicking] = useState(false);
  const [pickMsg, setPickMsg] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await fetch(`${API_URL}/api/admin/themes`,
                              { headers: { "X-Admin-Password": password || "" } });
        const j = await r.json().catch(() => ({}));
        if (!alive || !r.ok) return;
        // نام‌های واقعیِ پاسخ: `currentTemplate` / `currentPalette`،
        // و پالت‌های سفارشی جدا می‌آیند
        setOpts({
          templates: j.templates || [],
          // Only classic is free (subpage_templates); the reason is the backend's.
          locked: !!j.templatesLocked, why: j.templatesWhy || "",
          palettes: [...(j.palettes || []), ...(j.customPalettes || [])],
        });
        setSaved({ template: j.currentTemplate || "",
                   palette: j.currentPalette || "" });
      } catch { /* نبودِ فهرست نباید پیش‌نمایش را بیندازد */ }
    })();
    return () => { alive = false; };
  }, [password]);

  const curTpl = tryTpl || saved.template;
  const curPal = tryPal || saved.palette;
  const changed = (tryTpl && tryTpl !== saved.template)
               || (tryPal && tryPal !== saved.palette);

  const pick = async () => {
    setPicking(true); setPickMsg(null);
    try {
      const r = await fetch(`${API_URL}/api/admin/themes`, {
        method: "POST",
        headers: { "Content-Type": "application/json",
                   "X-Admin-Password": password || "" },
        body: JSON.stringify({ template: curTpl, palette: curPal }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(errText(j.detail, "ذخیره نشد"));
      setSaved({ template: curTpl, palette: curPal });
      setTryTpl(""); setTryPal("");
      setPickMsg({ t: "ok", m: "انتخاب شد — مشتری‌ها از این به بعد همین را می‌بینند" });
    } catch (e) {
      setPickMsg({ t: "err", m: e.message });
    } finally { setPicking(false); }
  };

  const DEVICES = {
    mobile: { w: 390, label: "موبایل", icon: Smartphone, sub: "iPhone 14 Pro" },
    tablet: { w: 768, label: "تبلت", icon: Monitor, sub: "iPad" },
    desktop: { w: 1200, label: "دسکتاپ", icon: Monitor, sub: "لپ‌تاپ" },
  };
  const d = DEVICES[device];
  const H = 760;
  // حاشیه‌ی ۲۴ پیکسلی از هر طرف (p-6)
  const fit = boxW ? Math.max(0.3, (boxW - 48) / d.w) : 1;
  const scale = Math.min(zoom / 100, fit);
  const fitted = scale < zoom / 100;

  const refresh = () => { setLoading(true); setKey((k) => k + 1); };

  return (
    <div className="fx-anim">
      <SectionHead
        title="پیش‌نمایش زنده"
        desc="دقیقاً همان چیزی که مشتری می‌بیند — با تنظیمات ذخیره‌شده‌ی شما و داده‌ی نمونه."
      />

      {dirty && (
        <div className="mb-4">
          <div className="rounded-2xl p-4 flex items-start gap-3 flex-wrap" style={{ background: "var(--warn-wash)", border: "1px solid var(--warn-line)" }}>
            <AlertTriangle size={16} className="shrink-0 mt-0.5" style={{ color: "var(--warn)" }} />
            <div className="flex-1 min-w-[200px]">
              <div className="text-[14px] font-semibold mb-1" style={{ color: "var(--warn)" }}>تغییرات ذخیره‌نشده دارید</div>
              <p className="text-[13px] leading-relaxed" style={{ color: "var(--dim)" }}>
                پیش‌نمایش، آخرین نسخه‌ی <b>ذخیره‌شده</b> را نشان می‌دهد. برای دیدن تغییرات جدید، اول ذخیره کنید.
              </p>
            </div>
            <button onClick={async () => { await onSave(); setTimeout(refresh, 300); }} disabled={saving}
              className="fx-btn px-3.5 py-2 text-[13px] flex items-center gap-1.5 shrink-0">
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
              ذخیره و به‌روزرسانی
            </button>
          </div>
        </div>
      )}

      {/* نوار ابزار */}
      <div className="fx-card p-3 mb-4 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1 p-1 rounded-[11px]" style={{ background: "var(--surface-3)", border: "1px solid var(--border-2)" }}>
            {Object.entries(DEVICES).map(([k, v]) => (
              <button key={k} onClick={() => setDevice(k)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-[9px] text-[13px] font-medium transition-all"
                style={device === k ? { background: "var(--accent-2)", color: "#06090F" } : { color: "var(--muted)" }}>
                <v.icon size={12} /> {v.label}
              </button>
            ))}
          </div>
          <span className="text-[12px] px-2.5 py-1.5 rounded-lg" style={{ background: "var(--surface-3)", color: "var(--muted)", fontFamily: "var(--mono)" }}>
            {d.w}px · {d.sub}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1 px-1 py-1 rounded-[11px]" style={{ background: "var(--surface-3)", border: "1px solid var(--border-2)" }}>
            <button onClick={() => setZoom((z) => Math.max(50, Math.min(z, Math.round(scale * 100)) - 10))} className="fx-ico-btn" style={{ width: 28, height: 28 }} aria-label="کوچک‌نمایی"><Minus size={13} /></button>
            {/* عددِ واقعی — وقتی قاب برای جاشدن کوچک شده، همان را بگو */}
            <span className="text-[13px] w-11 text-center" style={{ color: fitted ? "var(--accent-2)" : "var(--dim)", fontFamily: "var(--mono)" }}
              title={fitted ? "برای جاشدن در صفحه کوچک شده" : undefined}>{Math.round(scale * 100)}%</span>
            <button onClick={() => setZoom((z) => Math.min(150, z + 10))} className="fx-ico-btn" style={{ width: 28, height: 28 }} aria-label="بزرگ‌نمایی"><Plus size={13} /></button>
          </div>
          <a href={`${API_URL}/api/preview`} target="_blank" rel="noreferrer" className="fx-btn-g px-3 py-2 text-[13px] flex items-center gap-1.5">
            <ExternalLink size={13} /> <span className="fx-hide-m">تب جدید</span>
          </a>
          <button onClick={refresh} className="fx-btn px-3.5 py-2 text-[13px] flex items-center gap-1.5">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> به‌روزرسانی
          </button>
        </div>
      </div>

      {/* ناحیه پیش‌نمایش با اسکرول */}
      <div className="fx-card overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-3)" }}>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: "#FF5F57" }} />
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: "#FEBC2E" }} />
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: "#28C840" }} />
          </div>
          <div className="text-[12px] px-3 py-1 rounded-md flex-1 mx-3 text-center truncate" dir="ltr"
            style={{ background: "var(--surface)", color: "var(--muted)", fontFamily: "var(--mono)" }}>
            {API_URL}/api/preview
          </div>
          <div className="w-14 fx-hide-m" />
        </div>

        {/* انتخابگر — بالای خودِ نما، نه در صفحه‌ای دیگر. مقایسه
            وقتی معنی دارد که هر دو چیز هم‌زمان جلوی چشم باشند. */}
        {opts.templates.length > 0 && (
          <div className="px-3 py-2.5"
            style={{ borderBottom: "1px solid var(--border-2)",
                     background: "var(--surface-2)" }}>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[12px] shrink-0"
                style={{ color: "var(--muted)" }}>چیدمان</span>
              {opts.templates.map((t) => (
                <button key={t.id}
                  onClick={() => {
                    if (opts.locked && t.id !== "classic") { setPickMsg({ t: "err", m: opts.why }); return; }
                    setTryTpl(t.id); setLoading(true);
                  }}
                  title={opts.locked && t.id !== "classic" ? opts.why : undefined}
                  className="px-2.5 py-1 rounded-lg text-[12px] transition-all"
                  style={curTpl === t.id
                    ? { background: "var(--accent-fill)",
                        border: "1px solid var(--accent-edge)",
                        color: "var(--accent-2)" }
                    : { background: "transparent",
                        border: "1px solid var(--border-2)",
                        color: "var(--muted)" }}>
                  {t.name || t.id}{opts.locked && t.id !== "classic" ? " · Pro" : ""}
                </button>
              ))}
            </div>

            {opts.palettes.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap mt-2">
                <span className="text-[12px] shrink-0"
                  style={{ color: "var(--muted)" }}>رنگ</span>
                {opts.palettes.map((p) => (
                  <button key={p.id} title={p.name || p.id}
                    onClick={() => { setTryPal(p.id); setLoading(true); }}
                    aria-label={p.name || p.id}
                    style={{
                      width: 24, height: 24, borderRadius: 8, flex: "none",
                      // مقدارِ رنگ این‌جا خودِ داده است — یکی از دو
                      // استثنای قاعده‌ی توکن
                      background: (p.vars && p.vars.accent) || "var(--accent)",
                      border: curPal === p.id
                        ? "2px solid var(--text)" : "1px solid var(--hair-3)",
                    }} />
                ))}
              </div>
            )}

            {changed && (
              <div className="flex items-center gap-2 flex-wrap mt-2.5">
                <span className="text-[12px]" style={{ color: "var(--warn)" }}>
                  فقط دارید نگاه می‌کنید — هنوز ذخیره نشده
                </span>
                <button onClick={pick} disabled={picking}
                  className="fx-btn px-3 py-1.5 text-[12.5px] flex items-center gap-1.5">
                  {picking ? <Loader2 size={12} className="animate-spin" />
                    : <Save size={12} />}
                  همین را انتخاب کن
                </button>
                <button onClick={() => { setTryTpl(""); setTryPal(""); setLoading(true); }}
                  className="fx-btn-g px-3 py-1.5 text-[12.5px]">
                  برگرد به ذخیره‌شده
                </button>
              </div>
            )}

            <Msg msg={pickMsg} onClose={() => setPickMsg(null)} />
          </div>
        )}

        <div className="nx-preview-scroll" ref={boxRef} style={{ background: "var(--bg)" }}>
          <div className="flex justify-center p-6">
            {/* جعبه دقیقاً اندازه‌ی قابِ بزرگ‌نمایی‌شده است و قاب از گوشه‌ی
                بالا-چپ بزرگ می‌شود. پیش‌تر پهنای جعبه کوچک می‌شد ولی قاب با
                پهنای اصلی از وسطِ خودش کوچک می‌شد — در ۵۰٪ قاب نیم‌پهنا به
                راست می‌لغزید، و ارتفاعِ ۷۶۰ هم هرگز کم نمی‌شد. */}
            <div className="relative shrink-0" style={{ width: d.w * scale, height: H * scale,
              transition: "width .25s ease, height .25s ease" }}>
              {loading && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-[18px] z-10" style={{ background: "var(--surface-3)" }}>
                  <Loader2 size={22} className="animate-spin" style={{ color: "var(--accent-2)" }} />
                  <span className="text-[13px]" style={{ color: "var(--muted)" }}>در حال بارگذاری...</span>
                </div>
              )}
              <iframe
                key={key}
                // NX_PREVIEW_URL فقط در هارنس — آن‌جا بکندی نیست که این مسیر را
                // بدهد و این صفحه همیشه یک قابِ خاکستری بود. مسیرِ واقعی در
                // قالبِ جدای خودش می‌ماند: test-seams صدازدن‌ها را از متنِ
                // قالب پیدا می‌کند و قالبِ تو‌در‌تو را نمی‌بیند.
                src={(window.NX_PREVIEW_URL || `${API_URL}/api/preview`) + `?t=${key}`
                     + `&template=${encodeURIComponent(curTpl || "")}`
                     + `&palette=${encodeURIComponent(curPal || "")}`}
                onLoad={() => setLoading(false)}
                title="پیش‌نمایش صفحه اشتراک"
                style={{
                  position: "absolute", top: 0, left: 0,
                  width: d.w,
                  height: H,
                  border: "1px solid var(--border-2)",
                  borderRadius: 18,
                  background: "var(--bg)",
                  display: "block",
                  transform: `scale(${scale})`,
                  transformOrigin: "0 0",
                  transition: "transform .25s ease",
                }}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4">
        <InfoBox>
          داده‌های نمایش‌داده‌شده (حجم، تاریخ انقضا، کانفیگ‌ها) <b>نمونه</b> هستند و در سرور واقعی با اطلاعات هر مشتری جایگزین می‌شوند — ولی تمام تنظیماتی که در این پنل ذخیره کرده‌اید (اپ‌ها، رنگ‌ها، بنرها، متن‌ها) دقیقاً همان‌طور که اینجا می‌بینید اعمال می‌شوند.
        </InfoBox>
      </div>
    </div>
  );
}
