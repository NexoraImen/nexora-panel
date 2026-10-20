import React, { useEffect, useState } from "react";
import { API_URL } from "../lib/constants";
import { errMsg, okJson } from "../lib/format";
import { ConfirmModal, Field, InfoBox, Msg, SectionHead } from "../ui/index";

// Keep this display threshold aligned with remote_xui.FRESH_SECONDS; the backend authorizes selection.
const FRESH_SECONDS = 90;

function snapshotState(node) {
  if (node.revoked) return "اتصال لغو شده است.";
  if (!node.snapshot_at) return "اطلاعات موجود نیست؛ سرور هنوز آماده انتخاب نیست.";
  const seconds = (Date.now() - dateOf(node.snapshot_at).getTime()) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) return "زمان اطلاعات نامعتبر است؛ ساعت سرور را بررسی کنید.";
  return seconds > FRESH_SECONDS ? "اطلاعات قدیمی است؛ دریافت اطلاعات تازه از ایجنت لازم است." : "اطلاعات تازه است؛ تأیید نهایی هنگام ذخیره انجام می‌شود.";
}

function dateOf(value) {
  return new Date(typeof value === "number" || /^\d+(\.\d+)?$/.test(value) ? Number(value) * 1000 : value);
}

function stamp(value) {
  if (!value) return "ثبت نشده";
  const date = dateOf(value);
  return Number.isNaN(date.getTime()) ? "زمان نامعتبر" : date.toLocaleString("fa-IR", { timeZone: "Asia/Tehran" });
}

function age(value) {
  const seconds = (Date.now() - dateOf(value).getTime()) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) return "سن نامشخص؛ ساعت سرور را بررسی کنید";
  if (seconds < 60) return "کمتر از یک دقیقه پیش";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes.toLocaleString("fa-IR")} دقیقه پیش`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours.toLocaleString("fa-IR")} ساعت پیش` : `${Math.floor(hours / 24).toLocaleString("fa-IR")} روز پیش`;
}

export function RemoteXuiSection({ password }) {
  const [data, setData] = useState(null);
  const [mode, setMode] = useState("local");
  const [region, setRegion] = useState("foreign");
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [nodeRegion, setNodeRegion] = useState("foreign");
  const [pair, setPair] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [revoke, setRevoke] = useState(null);
  const [review, setReview] = useState(null);
  const [reconnect, setReconnect] = useState(null);
  const request = (url = `${API_URL}/api/admin/remote-xui`, options = {}) => fetch(url, {
    ...options, headers: { "X-Admin-Password": password, "Content-Type": "application/json" },
  });
  const load = async () => {
    const next = await okJson(await request());
    setData(next); setMode(next.mode); setRegion(next.region); setSelected(next.selected == null ? "" : String(next.selected));
    setNodeRegion(next.nodes.find((n) => String(n.id) === String(next.selected))?.region || next.region);
  };
  const run = async (action) => {
    setBusy(true); setMsg(null);
    try { await action(); }
    catch (e) { setMsg({ t: "err", m: errMsg(e) }); }
    finally { setBusy(false); }
  };
  useEffect(() => { run(load); }, [password]);
  const save = () => run(async () => {
    const node = data.nodes.find((n) => String(n.id) === selected);
    await okJson(await request(`${API_URL}/api/admin/remote-xui`, { method: "PUT", body: JSON.stringify({ mode, region, node_id: mode === "remote" ? node.id : null }) }));
    await load(); setMsg({ t: "ok", m: "منبع اتصال ذخیره شد." });
  });
  const createPair = () => run(async () => {
    setPair(null);
    const result = await okJson(await request(`${API_URL}/api/admin/remote-xui/pair`, { method: "POST", body: JSON.stringify({ name: name.trim(), region: nodeRegion }) }));
    setPair(result);
  });
  const copy = (value) => run(async () => {
    if (!navigator.clipboard) throw new Error("کپی خودکار در دسترس نیست؛ متن را دستی کپی کنید.");
    await navigator.clipboard.writeText(value); setMsg({ t: "ok", m: "کپی شد." });
  });
  return <>
    <SectionHead title="اتصال سرور 3x-ui" desc="انتخاب 3x-ui همین سرور یا اتصال پنل مرکزی به سرور دیگر"
      action={<button className="fx-btn-g px-4 py-2" disabled={busy} onClick={() => run(load)}>{busy ? "در حال پردازش…" : "تازه‌سازی"}</button>} />
    <Msg msg={msg} />
    {reconnect && <ConfirmModal title="اتصال دوباره سرور؟" confirmLabel="اتصال دوباره" desc={`«${reconnect.name}» باید همان سرور 3x-ui و همان منبع حسابداری قبلی باشد. توکن قبلی بلافاصله باطل می‌شود؛ شناسه و تاریخچه حذف نمی‌شوند. اطلاعات قبلی پاک می‌شود و دریافت اطلاعات تازه لازم است.`} onCancel={() => setReconnect(null)} onConfirm={() => { const node = reconnect; setReconnect(null); run(async () => {
      setPair(null);
      const result = await okJson(await request(`${API_URL}/api/admin/remote-xui/node/${encodeURIComponent(node.id)}/pair`, { method: "POST" }));
      setPair(result); await load();
      setMsg({ t: "ok", m: "کد اتصال دوباره ساخته شد؛ دستور نصب را روی همان سرور اجرا کنید و سپس اطلاعات را تازه‌سازی کنید." });
    }); }} />}
    {data && <>
      {(data.orders || []).length > 0 && <div className="fx-card p-4 mb-4">
        {data.orders.map((order) => <div key={`${order.tenant_id}:${order.order_id}`} className="flex items-center justify-between gap-3 flex-wrap py-3 text-[13px]" style={{ borderBottom: "1px solid var(--border)" }}>
          <div>سفارش #{order.order_id} در انتظار تطبیق تحویل و پرداخت است؛ تلاش مجدد و برگشت خودکار متوقف است.<span style={{ color: "var(--muted)" }}> فروشگاه {order.tenant_id}</span></div>
          <a className="fx-btn-g px-3 py-2" href="#/bot-orders">بررسی سفارش‌ها</a>
        </div>)}
      </div>}
      {(data.uncertain || []).length > 0 && <div className="fx-card p-4 mb-4">
        <InfoBox tone="warn">نتیجهٔ این فرمان‌ها نامشخص است. پیش از ادامه، نتیجه را روی سرور و سفارش و پرداخت را بررسی کنید. تأیید بررسی، فرمان را دوباره اجرا نمی‌کند.</InfoBox>
        {data.uncertain.map((command) => <div key={command.id} className="flex items-center justify-between gap-3 flex-wrap py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="min-w-0 text-[13px] break-words">
            <div>فرمان {command.id} · سرور {data.nodes.find((n) => n.id === command.node_id)?.name || command.node_id}</div>
            <div dir="ltr">{command.method} {command.path}</div>
            <div>{stamp(command.created)}</div>
          </div>
          <button className="fx-btn-g px-3 py-2" disabled={busy} onClick={() => setReview(command)}>تأیید بررسی نتیجه</button>
        </div>)}
      </div>}
      <div className="fx-card p-4 space-y-3">
        <div className="fx-g3 grid grid-cols-2 gap-3">
        <Field label="3x-ui روی همین سرور نصب است؟"><select aria-label="حالت اتصال" className="fx-input" value={mode} disabled={busy} onChange={(e) => setMode(e.target.value)}>
          <option value="local">محلی — 3x-ui همین سرور</option><option value="remote">مرکزی — 3x-ui سرور دیگر</option>
        </select></Field>
        <Field label={mode === 'local' ? '3x-ui همین سرور در ایران است یا خارج؟' : 'موقعیت پنل مرکزی / سرور فعلی'}><select aria-label="موقعیت پنل" className="fx-input" value={region} disabled={busy} onChange={(e) => setRegion(e.target.value)}>
          <option value="iran">ایران</option><option value="foreign">خارج از ایران</option>
        </select></Field>
        {mode === "remote" && <Field label="سرور 3x-ui"><select aria-label="سرور 3x-ui" className="fx-input" value={selected} disabled={busy} onChange={(e) => setSelected(e.target.value)}>
          <option value="">انتخاب سرور</option>{data.nodes.map((node) => <option key={node.id} value={String(node.id)} disabled={!!node.revoked}>{node.name}{node.revoked ? " — لغوشده" : ""}</option>)}
        </select></Field>}
        </div>
        {mode === 'remote'
          ? <InfoBox>انتخاب سرور راه دور فقط پس از تأیید اطلاعات تازه توسط سرور مرکزی ذخیره می‌شود. برای دریافت وضعیت جدید، «تازه‌سازی» را بزنید.</InfoBox>
          : <InfoBox>3x-ui همین سرور با موقعیت انتخاب‌شده استفاده می‌شود؛ نیازی به اتصال ایجنت نیست.</InfoBox>}
        <button className="fx-btn px-4 py-2" disabled={busy || (mode === "remote" && !data.nodes.some((n) => String(n.id) === selected && !n.revoked))} onClick={save}>ذخیره اتصال</button>
      </div>
      <div className="fx-card p-4 mt-4">
        <h3 className="font-semibold mb-3">سرورهای متصل</h3>
        {!data.nodes.length && <p>هنوز سروری متصل نشده است.</p>}
        {data.nodes.map((node) => <div key={node.id} className="flex items-center justify-between gap-3 flex-wrap py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="min-w-0 text-[13px] space-y-1">
            <div className="font-semibold break-words">{node.name} · {node.region === "iran" ? "ایران" : "خارج از ایران"}{String(data.selected) === String(node.id) ? data.mode === "remote" ? " · منبع فعلی" : " · منبع راه دور قبلی" : ""}</div>
            <div style={{ color: node.online && !node.revoked ? "var(--ok)" : "var(--warn)" }}>{node.revoked ? "لغوشده" : node.online ? "آنلاین" : "آفلاین / ارتباط قدیمی"}</div>
            <div>آخرین ارتباط: {stamp(node.last_seen)}</div>
            <div>آخرین اطلاعات: {stamp(node.snapshot_at)}{node.snapshot_at ? ` · دریافت اطلاعات: ${age(node.snapshot_at)}` : ""}</div>
            <div style={{ color: "var(--muted)" }}>{snapshotState(node)}</div>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button className="fx-btn-g px-3 py-2" disabled={busy} onClick={() => setReconnect(node)}>اتصال دوباره</button>
            <button className="fx-btn-g px-3 py-2" disabled={busy || !!node.revoked} onClick={() => setRevoke(node)}>لغو اتصال</button>
          </div>
        </div>)}
      </div>
      <div className="fx-card p-4 mt-4 space-y-4">
        <h3 className="font-semibold">اتصال سرور جدید</h3>
        <Field label="نام سرور"><input aria-label="نام سرور" className="fx-input" value={name} maxLength={60} disabled={busy} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="موقعیت سرور جدید"><select aria-label="موقعیت سرور جدید" className="fx-input" value={nodeRegion} disabled={busy} onChange={(e) => setNodeRegion(e.target.value)}><option value="iran">ایران</option><option value="foreign">خارج از ایران</option></select></Field>
        <button className="fx-btn px-4 py-2" disabled={busy || !name.trim()} onClick={createPair}>ساخت کد یک‌بارمصرف</button>
        {pair && <>
          <InfoBox tone="warn">کد اتصال محرمانه و یک‌بارمصرف است؛ با خروج از صفحه پاک می‌شود. انقضا: {stamp(pair.expires)}</InfoBox>
          <Field label="کد اتصال"><input aria-label="کد اتصال" className="fx-input" dir="ltr" readOnly value={pair.code} /></Field>
          <button className="fx-btn-g px-3 py-2" disabled={busy} onClick={() => copy(pair.code)}>کپی کد</button>
          <Field label="نشانی نصب‌کننده"><input aria-label="نشانی نصب‌کننده" className="fx-input" dir="ltr" readOnly value={pair.installer_url || ""} /></Field>
          {pair.command_hint ? <>
            <Field label="دستور نصب روی سرور 3x-ui" hint="نصب‌کننده ابتدا با curl -f در فایل دانلود می‌شود، سپس با کد اتصال اجرا می‌شود؛ آن را مستقیم به shell پایپ نکنید."><textarea aria-label="دستور نصب" className="fx-input w-full" dir="ltr" rows={4} readOnly value={pair.command_hint} /></Field>
            <button className="fx-btn-g px-3 py-2" disabled={busy} onClick={() => copy(pair.command_hint)}>کپی دستور نصب</button>
          </> : <InfoBox tone="warn">دستور نصب از سرور دریافت نشد؛ رابط نصب را حدس نزنید. پس از تکمیل نصب‌کننده، کد جدید بسازید.</InfoBox>}
          <button className="fx-btn-g px-3 py-2" onClick={() => setPair(null)}>پنهان‌کردن کد و دستور</button>
        </>}
      </div>
    </>}
    {revoke && <ConfirmModal title="لغو اتصال سرور؟" confirmLabel="لغو اتصال" desc={`دسترسی «${revoke.name}» لغو می‌شود؛ اگر منبع فعلی است، فروش تا برقراری اتصال معتبر متوقف می‌شود.`} onCancel={() => setRevoke(null)} onConfirm={() => { const node = revoke; setRevoke(null); run(async () => {
      const response = await request(`${API_URL}/api/admin/remote-xui/node/${encodeURIComponent(node.id)}`, { method: "DELETE" });
      if (response.status !== 204) await okJson(response);
      setPair(null); await load(); setMsg({ t: "ok", m: "اتصال سرور لغو شد." });
    }); }} />}
    {review && <ConfirmModal title="تأیید بررسی فرمان نامشخص" confirmLabel="نتیجه را روی سرور بررسی و سفارش و پرداخت را تطبیق داده‌ام" desc={`فرمان ${review.id} فقط به‌عنوان بررسی‌شده ثبت می‌شود و دوباره اجرا نمی‌شود. تأیید فقط پس از بررسی واقعی نتیجه و تطبیق مالی مجاز است؛ اطلاعات تازه لازم است.`} onCancel={() => setReview(null)} onConfirm={() => { const command = review; setReview(null); run(async () => {
      await okJson(await request(`${API_URL}/api/admin/remote-xui/command/${encodeURIComponent(command.id)}/resolve`, { method: "POST", body: JSON.stringify({ reviewed: true }) }));
      await load(); setMsg({ t: "ok", m: "بررسی نتیجه ثبت شد؛ فرمان دوباره اجرا نشد." });
    }); }} />}
  </>;
}
