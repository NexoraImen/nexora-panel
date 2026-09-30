/*
 * Pro areas in the panel.
 * Spec: docs/specs/2026-09-29-pro-split.md
 *
 * A Pro screen renders only when its module is in this build *and* the
 * license allows its feature. Everything else is <ProLock>: the feature's
 * name, the backend's own reason, and the way to buy. The backend checks the
 * license on every Pro route too; this screen is honesty, not protection.
 */
import React, { Suspense, lazy, useEffect, useState } from "react";
import { AlertTriangle, Lock } from "lucide-react";
import { API_URL } from "../lib/constants";
import { errMsg, okJson } from "../lib/format";
import { Msg } from "./index";

// Every Pro screen in this build. The Community build has no src/pro/, so this
// is {} and every Pro area shows its lock.
const MODS = import.meta.glob("../pro/*.jsx");
const LAZY = {};

export const proPresent = (area) => !!MODS[`../pro/${area}.jsx`];

// One license answer shared by the nav, the banner and every Pro section, so
// activating on the System page unlocks the rest without a reload.
let current = null;
let inflight = null;
const subs = new Set();

export function setLicense(v) {
  current = v;
  subs.forEach((f) => f(v));
}

export function loadLicense(password) {
  if (!inflight) {
    inflight = fetch(`${API_URL}/api/admin/license`, { headers: { "X-Admin-Password": password } })
      .then((res) => okJson(res, "خواندن وضعیت مجوز ناموفق بود"))
      .then((v) => { setLicense(v); return v; })
      .catch((e) => { setLicense({ error: errMsg(e) }); })
      .finally(() => { inflight = null; });
  }
  return inflight;
}

export function useLicense(password) {
  const [lic, setLic] = useState(current);
  useEffect(() => {
    subs.add(setLic);
    if (!current && password) loadLicense(password);
    return () => { subs.delete(setLic); };
  }, [password]);
  return lic;
}

export const allowed = (lic, feature) =>
  !!(lic && lic.pro && (lic.entitlements || []).includes(feature));

// The nav mark of a locked Pro area. One component for both nav modes: the
// accordion is the default, so a mark added to one only would never be seen.
export function ProMark({ feature, className = "" }) {
  const lic = useLicense();
  if (!feature || !lic || lic.error || allowed(lic, feature)) return null;
  return (
    <span className={`text-[10.5px] px-1.5 py-0.5 rounded-full shrink-0 ${className}`}
      style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>Pro</span>
  );
}

export function ProLock({ feature, lic, present }) {
  const name = (lic?.features || {})[feature] || feature;
  // Licensed but the screen is not in this build: a broken install, not an upsell.
  const reason = allowed(lic, feature) && !present
    ? "این بخش در بسته‌ی Pro این سرور نیست؛ بسته‌ی Pro را دوباره نصب کنید."
    : (lic?.denials || {})[feature] || `«${name}» بخشی از نسخه‌ی Pro است.`;
  const buy = lic && !lic.pro && lic.sales_url;
  return (
    <div className="fx-card p-5 flex items-start gap-3 flex-wrap"
      style={{ background: "var(--accent-wash)", borderColor: "var(--accent-line)" }}>
      <div className="fx-ico" style={{ background: "var(--accent-soft)" }}>
        <Lock size={16} style={{ color: "var(--accent)" }} />
      </div>
      <div className="flex-1" style={{ minWidth: 220 }}>
        <div className="text-[15px] font-semibold text-white">{name} · Pro</div>
        <div className="text-[13px] mt-1 leading-relaxed" style={{ color: "var(--dim)" }}>{reason}</div>
        <div className="text-[12px] mt-1" style={{ color: "var(--muted)" }}>
          کلید مجوز را در «سیستم» وارد کنید. داده‌های این بخش سر جایشان می‌مانند.
        </div>
      </div>
      {buy && (
        <a href={lic.sales_url} target="_blank" rel="noreferrer"
          className="fx-btn px-4 py-2.5 text-[14px] shrink-0">خرید Pro</a>
      )}
    </div>
  );
}

export function ProSection({ area, name = "default", feature, password, ...props }) {
  const lic = useLicense(password);
  const present = proPresent(area);
  if (!lic) return null;
  if (lic.error) return <Msg msg={{ t: "err", m: lic.error }} />;
  if (!present || !allowed(lic, feature)) return <ProLock feature={feature} lic={lic} present={present} />;
  const Screen = lazyPro(area, name);
  return (
    <Suspense fallback={null}>
      <Screen password={password} {...props} />
    </Suspense>
  );
}

function lazyPro(area, name) {
  const key = `${area}:${name}`;
  if (!LAZY[key]) {
    LAZY[key] = lazy(() => MODS[`../pro/${area}.jsx`]().then((m) => ({ default: m[name] })));
  }
  return LAZY[key];
}

// A Pro piece inside a core screen (the reseller portal). No license check
// here: the portal has no admin session, and the backend answers every Pro
// route with 403 and its reason. Not in this build: `fallback`.
export function ProModule({ area, name = "default", fallback = null, ...props }) {
  if (!proPresent(area)) return fallback;
  const Piece = lazyPro(area, name);
  return (
    <Suspense fallback={null}>
      <Piece {...props} />
    </Suspense>
  );
}

export function ProUnavailable() {
  return (
    <section className="pd-card" style={{ color: "var(--dim)", fontSize: 13 }}>
      این بخش در نسخه‌ی Pro است.
    </section>
  );
}

// grace / clock / wrong_machine: Pro still works or just stopped, and the owner
// must act. One line, above every section, until it is fixed.
const BANNER = { grace: "warn", clock: "danger", wrong_machine: "danger" };

export function LicenseBanner({ password }) {
  const lic = useLicense(password);
  const tone = lic && BANNER[lic.state];
  if (!tone) return null;
  return (
    <div className="fx-card px-4 py-2.5 mb-4 flex items-center gap-2 text-[13px]"
      style={{ background: `var(--${tone}-wash)`, borderColor: `var(--${tone}-line)`, color: `var(--${tone})` }}>
      <AlertTriangle size={14} className="shrink-0" />
      <span className="flex-1 min-w-0">{lic.message}</span>
    </div>
  );
}
