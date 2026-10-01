/**
 * «ربات تانل» (docs/specs/2026-10-01-bots-and-tunnel-mesh.md): a Telegram bot
 * of its own for tunnels and servers, apart from the sales bot and the
 * management bot. In 2.1.0 this was an optional second token folded inside the
 * management bot's card; the owner never found it and asked for it twice.
 */
import React, { useEffect, useState } from "react";
import { Activity, Check, Loader2, MessageCircle, Network, Server, Stethoscope } from "lucide-react";
import { API_URL } from "../../lib/constants";
import { errMsg, okJson } from "../../lib/format";
import { Field, Msg, SectionHead } from "../../ui/index";

export function TunnelBotSection({ password }) {
  const [d, setD] = useState(null);
  const [tok, setTok] = useState("");
  const [ids, setIds] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState(null);
  const H = { "X-Admin-Password": password, "Content-Type": "application/json" };

  const fill = (j) => {
    setD(j);
    setTok(j.monitorToken || "");
    setIds((j.admins && j.admins.length ? j.admins : (j.suggestAdmin ? [j.suggestAdmin] : [])).join(", "));
  };
  useEffect(() => {
    fetch(`${API_URL}/api/admin/adminbot`, { headers: H })
      .then((r) => okJson(r, "تنظیمِ ربات تانل خوانده نشد")).then(fill)
      .catch((e) => setMsg({ t: "err", m: errMsg(e) }));
  }, [password]);

  const save = async () => {
    setBusy("save"); setMsg(null);
    try {
      const r = await fetch(`${API_URL}/api/admin/adminbot`, {
        method: "PUT", headers: H,
        body: JSON.stringify({ monitorToken: tok, admins: ids.split(/[\s,،]+/).filter(Boolean) }),
      });
      const j = await okJson(r, "ذخیره نشد");
      fill(j);
      const u = j.usernames && j.usernames.monitorToken;
      setMsg({ t: "ok", m: u ? `ذخیره شد: @${u}. در تلگرام این ربات را باز کنید و Start بزنید، بعد «آزمایش».`
        : "ذخیره شد" });
    } catch (e) { setMsg({ t: "err", m: errMsg(e) }); }
    finally { setBusy(""); }
  };

  const test = async () => {
    setBusy("test"); setMsg(null);
    try {
      const r = await fetch(`${API_URL}/api/admin/adminbot/test`, { method: "POST", headers: H });
      const j = await okJson(r, "آزمایش انجام نشد");
      const mine = (j.results || []).filter((x) => x.bot === "تانل");
      const bad = mine.filter((x) => !x.ok);
      setMsg(!mine.length ? { t: "err", m: "اول توکنِ ربات تانل را ذخیره کنید." }
        : bad.length ? { t: "err", m: bad.map((x) => `${x.to}: ${x.why}`).join(" · ") }
          : { t: "ok", m: "رسید. منوی ربات تانل را در تلگرام ببینید." });
    } catch (e) { setMsg({ t: "err", m: errMsg(e) }); }
    finally { setBusy(""); }
  };

  return (
    <div className="fx-anim">
      <SectionHead title="ربات تانل"
        desc="یک ربات تلگرامِ جدا فقط برای تانل‌ها و سرورها؛ نه رباتِ فروش، نه رباتِ مدیریت." />
      <Msg msg={msg} />

      <div className="fx-split">
        <div className="fx-card p-5">
          <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
            <Network size={15} style={{ color: "var(--accent-2)" }} /> اتصال
            {d && d.hasMonitorToken && <span className="text-[11.5px] font-normal px-2 py-0.5 rounded-full"
              style={{ background: "var(--ok-soft)", color: "var(--ok)" }}>وصل</span>}
          </div>
          <p className="text-[12.5px] mb-3" style={{ color: "var(--muted)" }}>
            در BotFather یک رباتِ تازه بسازید و توکنش را این‌جا بگذارید. فقط شناسه‌های زیر جواب می‌گیرند.
          </p>
          <Field label="توکنِ ربات تانل">
            <input className="fx-input w-full" dir="ltr" value={tok} placeholder="123456:ABC…"
              onChange={(e) => setTok(e.target.value)} />
          </Field>
          <Field label="شناسه‌ی عددیِ تلگرامِ مدیر (همان مدیرهای ربات مدیریت)">
            <input className="fx-input w-full" dir="ltr" value={ids} placeholder="123456789"
              onChange={(e) => setIds(e.target.value)} />
          </Field>
          <div className="flex items-center gap-2">
            <button onClick={save} disabled={!!busy || !d} className="fx-btn px-4 py-2 text-[13px] flex items-center gap-1.5">
              {busy === "save" ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} ذخیره
            </button>
            <button onClick={test} disabled={!!busy || !(d && d.hasMonitorToken)}
              className="fx-btn-g px-4 py-2 text-[13px] flex items-center gap-1.5">
              {busy === "test" ? <Loader2 size={13} className="animate-spin" /> : <MessageCircle size={13} />} آزمایش
            </button>
          </div>
        </div>

        <div className="fx-card p-5">
          <div className="text-[14px] font-semibold text-white mb-1 flex items-center gap-2">
            <Activity size={15} style={{ color: "var(--accent-2)" }} /> چه کاری می‌کند
          </div>
          <div className="fx-rowlist text-[13px]" style={{ color: "var(--dim)" }}>
            <div className="flex items-start gap-2"><Network size={14} className="shrink-0 mt-1" style={{ color: "var(--accent-2)" }} />
              <span><b>📡 تانل‌ها</b>: هر تانل، موتورش، روشن یا خاموش، و اینکه سرورش آنلاین است.</span></div>
            <div className="flex items-start gap-2"><Stethoscope size={14} className="shrink-0 mt-1" style={{ color: "var(--accent-2)" }} />
              <span><b>🩺 عیب‌یابی</b>: نتیجه‌ی آخرین بررسیِ هر سرور، و «چه کنم».</span></div>
            <div className="flex items-start gap-2"><Server size={14} className="shrink-0 mt-1" style={{ color: "var(--accent-2)" }} />
              <span><b>🖥 سرورها</b>: آنلاین یا آفلاین، و آخرین تماس.</span></div>
            <div className="flex items-start gap-2"><Activity size={14} className="shrink-0 mt-1" style={{ color: "var(--warn)" }} />
              <span><b>هشدار</b>: وقتی ارتباطِ یک سرور خراب شود و وقتی درست شود، خودش پیام می‌دهد. هشدارهای سلامتِ سرور هم این‌جا می‌آیند، نه در رباتِ فروش.</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}
