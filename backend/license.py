"""
Pro license verification for the free core. Standard library only.

Spec: docs/specs/2026-09-29-license-core.md

This module only *verifies*. Signing lives on the issuer (Phase 3), and the
private key never touches a customer server. The check is public code and can
be patched out; that gains nothing, because Pro code is not in the free core and
only arrives from the issuer against a valid license. What this module must get
right is the honest answer: which state we are in, why, and when Pro locks.

The bot imports this same file by path. There is deliberately no second copy:
a rule written in two places drifts (the repo's most frequent bug class).
"""
import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

# ── Public keys ───────────────────────────────────────────────────────────
# kid -> 32-byte Ed25519 public key. A map, not one key, so a leaked or rotated
# key is replaced by shipping a new map; the issuer re-signs on the next refresh.
# k1: the production key, made by `issuer.cli keygen` on the owner's issuer
# (2026-09-30). Only the public half is here; the private half never leaves the
# issuer's data dir. An empty map makes every license "invalid", and
# scripts/export-public.py refuses to publish one.
KEYS: dict = {"k1": bytes.fromhex("a53f87583c77bba0e7511e928ff4b53ffa0e46cee28da3bb76253b4567b28893")}

FEATURES = (
    "mini_app", "loyalty", "affiliates", "resellers", "accounting",
    "diagnostics", "insights", "channel", "monitoring_multi", "subpage_templates",
)
# Persian names for the messages the panel shows.
FEATURE_FA = {
    "mini_app": "مینی‌اپ تلگرام",
    "loyalty": "سکه، دعوت و بازگرداندن مشتری",
    "affiliates": "همکاری در فروش",
    "resellers": "پنل نمایندگی",
    "accounting": "حسابداری واسطه‌ها",
    "diagnostics": "عیب‌یابی اتصال و امنیت",
    "insights": "قیف فروش و نظرسنجی",
    "channel": "ارسال به کانال",
    "monitoring_multi": "مانیتورینگ چند سرور",
    "subpage_templates": "قالب‌های صفحه اشتراک",
}
#: Which API paths belong to which Pro feature, by prefix (the longest match
#: wins). Public on purpose: it names paths, not code. The loader gates Pro code
#: that runs in the app namespace with it, and the tests use it to tell "a Pro
#: route that is absent in the Community tree" from "a panel call to nowhere".
#: Spec: docs/specs/2026-09-29-pro-split.md
PRO_PATHS = {
    "/api/admin/channel": "channel",
    "/api/admin/bot/funnel": "insights",
    "/api/admin/bot/trial-journey": "insights",
    "/api/admin/bot/preview-flows": "insights",
    "/api/portal/funnel": "insights",
    "/api/portal/trial-journey": "insights",
    "/api/portal/bot-preview": "insights",
    "/api/admin/firewall": "diagnostics",
    "/api/admin/link/": "diagnostics",
    "/api/admin/inbounds/": "diagnostics",
    "/api/admin/tunnel": "monitoring_multi",
    "/api/admin/health/all": "monitoring_multi",
    "/api/admin/health/check/": "monitoring_multi",
    "/api/admin/traffic": "monitoring_multi",
    "/api/agent/": "monitoring_multi",
    "/api/mini/": "mini_app",
    "/api/admin/bot/mini-theme": "mini_app",
    "/api/admin/billing": "accounting",
    # card receipts approved by the bank SMS (docs/specs/2026-10-07-sms-auto-approve.md)
    "/api/admin/bot/smspay": "accounting",
    "/api/sms/": "accounting",
    "/api/portal/summary": "accounting",
    "/api/portal/": "resellers",
    "/api/admin/tenant": "resellers",
    "/api/admin/reseller-": "resellers",
    "/api/admin/portal-addon": "resellers",
    "/api/admin/store-addon": "resellers",
    "/api/admin/bot/discounts": "loyalty",
    "/api/mini/rewards": "loyalty",
    "/api/admin/bot/affiliate": "affiliates",
    "/api/aff/": "affiliates",
    # None marks a core path under a Pro prefix. These hold the owner's data
    # and the x-ui path the whole panel reads, so a lapsed license must never
    # stop a backup or a restore.
    "/api/admin/billing/backup": None,
    "/api/admin/billing/restore": None,
    "/api/admin/billing/xui-path": None,
}


def pro_feature_of(path):
    """The Pro feature `path` belongs to, or None for a core path."""
    best = None
    for prefix, feature in PRO_PATHS.items():
        if path.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, feature)
    return best[1] if best else None


PLANS = ("monthly", "yearly", "owner")
SALES_URL = "https://t.me/crm_nexoravpn"

# Clock moved back by more than this -> "clock". A day, so NTP corrections
# and a server that was off for a while never trip it.
CLOCK_SLACK = 24 * 3600
# last_seen is rewritten at most this often, so status() on every request
# does not write to disk on every request.
LAST_SEEN_EVERY = 300

DATA_DIR = Path(os.getenv("NEXORA_LICENSE_DIR",
                          str(Path(__file__).resolve().parent.parent / "data")))
MACHINE_ID_FILES = ["/etc/machine-id", "/var/lib/dbus/machine-id"]


def _p(name):
    return DATA_DIR / name


# ── Ed25519 verify (RFC 8032 §5.1.7) ──────────────────────────────────────
# Pure Python: the free core only verifies, a few milliseconds do not matter,
# and a crypto dependency would mean a pip install on every server during
# `nexora update`. Checked against the RFC 8032 test vectors in
# tests/test-license.py.
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _add(a, b):
    # Extended twisted Edwards coordinates (X, Y, Z, T).
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _equal(a, b):
    return ((a[0] * b[2] - b[0] * a[2]) % _P == 0
            and (a[1] * b[2] - b[1] * a[2]) % _P == 0)


def _recover_x(y, sign):
    if y >= _P:
        return None             # non-canonical encoding
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None             # not on the curve
    if (x & 1) != sign:
        x = _P - x
    return x


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _compress(pt):
    zi = pow(pt[2], _P - 2, _P)
    x, y = pt[0] * zi % _P, pt[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _h(data):
    return int.from_bytes(hashlib.sha512(data).digest(), "little") % _L


def verify(public: bytes, msg: bytes, sig: bytes) -> bool:
    if len(public) != 32 or len(sig) != 64:
        return False
    A = _decompress(public)
    R = _decompress(sig[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False            # malleable S: RFC 8032 requires rejecting it
    k = _h(sig[:32] + public + msg)
    return _equal(_mul(s, _G), _add(R, _mul(k, A)))


# ── Files ─────────────────────────────────────────────────────────────────
def _read_json(name):
    try:
        return json.loads(_p(name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _write(name, text):
    # Atomic: a half-written license.json would read as "invalid" and lock Pro.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _p(name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, _p(name))


def install_id():
    f = _p("install_id")
    try:
        v = f.read_text(encoding="utf-8").strip()
        if len(v) == 32:
            return v
    except FileNotFoundError:
        pass
    v = secrets.token_hex(16)
    _write("install_id", v)
    return v


def machine_id():
    for f in MACHINE_ID_FILES:
        try:
            v = Path(f).read_text(encoding="utf-8").strip()
            if v:
                return v
        except OSError:
            continue
    return ""


def fingerprint():
    """sha256 of machine-id + install_id. Copying data/ to another server
    changes the machine-id; cloning a whole image is caught by the issuer."""
    raw = f"nexora-v1|{machine_id()}|{install_id()}".encode()
    return hashlib.sha256(raw).hexdigest()


# ── Parsing ───────────────────────────────────────────────────────────────
def _b64u(s):
    if not isinstance(s, str):
        raise ValueError("not a string")
    return base64.b64decode(s + "=" * (-len(s) % 4), altchars=b"-_", validate=True)


def _int_or_none(v):
    return v is None or (isinstance(v, int) and not isinstance(v, bool))


def parse(doc):
    """Return (payload, None) or (None, reason). Checks the signature and the
    payload shape; says nothing yet about time or machine."""
    if not isinstance(doc, dict):
        return None, "malformed"
    kid = doc.get("kid")
    if kid not in KEYS:
        return None, "unknown_key"
    try:
        body, sig = _b64u(doc.get("payload")), _b64u(doc.get("sig"))
    except (ValueError, TypeError):
        return None, "malformed"
    if not verify(KEYS[kid], body, sig):
        return None, "bad_signature"
    try:
        pl = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "malformed"
    ok = (isinstance(pl, dict)
          and isinstance(pl.get("license_id"), str) and pl["license_id"]
          and pl.get("plan") in PLANS
          and isinstance(pl.get("entitlements"), list)
          and all(isinstance(e, str) for e in pl["entitlements"])
          and isinstance(pl.get("machine"), str)
          and isinstance(pl.get("issued"), int)
          and _int_or_none(pl.get("expires"))
          and _int_or_none(pl.get("valid_until"))
          and isinstance(pl.get("grace_days"), int) and 0 <= pl["grace_days"] <= 60)
    if not ok:
        return None, "malformed"
    return pl, None


_cache = {"raw": None, "result": None}


def _load():
    """(payload, reason) for data/license.json; (None, None) when absent.
    Verification is cached on the file's bytes: requires() runs per request."""
    try:
        raw = _p("license.json").read_bytes()
    except FileNotFoundError:
        return None, None
    if raw != _cache["raw"]:
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            doc = None
        _cache["raw"], _cache["result"] = raw, parse(doc)
    return _cache["result"]


# ── State ─────────────────────────────────────────────────────────────────
def _last_seen(now, write=True):
    st = _read_json("license_state.json") or {}
    seen = st.get("last_seen") if isinstance(st.get("last_seen"), int) else 0
    if write and now - seen >= LAST_SEEN_EVERY:
        _write("license_state.json", json.dumps({"last_seen": now}))
    return seen


def reset_clock(now=None):
    """After a successful online refresh: the issuer vouched for the time."""
    _write("license_state.json", json.dumps({"last_seen": int(now or time.time())}))


def _fa_date(ts):
    if ts is None:
        return ""
    try:
        import jdatetime
        v = jdatetime.datetime.fromtimestamp(ts).strftime("%Y/%m/%d %H:%M")
    except Exception:
        v = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    # Persian digits: the panel shows this sentence as is, beside Persian dates.
    return v.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


_REASON_FA = {
    "unknown_key": "کلید امضای این مجوز شناخته نیست",
    "bad_signature": "امضای مجوز درست نیست؛ فایل دست خورده یا ناقص است",
    "malformed": "فایل مجوز خراب است",
}


def status(now=None):
    """The one answer every caller uses. `pro` is True only in active/grace."""
    now = int(now if now is not None else time.time())
    fp = fingerprint()
    out = {"state": "none", "pro": False, "reason": None, "plan": None,
           "license_id": None, "expires": None, "valid_until": None,
           "lock_at": None, "entitlements": [], "fingerprint": fp,
           "sales_url": SALES_URL, "message": ""}
    pl, why = _load()
    if pl is None and why is None:
        out["message"] = "نسخه‌ی Community. برای بخش‌های Pro مجوز لازم است."
        _last_seen(now)
        return out
    if pl is None:
        out.update(state="invalid", reason=why,
                   message=f"مجوز پذیرفته نشد: {_REASON_FA[why]}. دوباره فعالش کنید.")
        return out
    out.update(plan=pl["plan"], license_id=pl["license_id"],
               expires=pl["expires"], valid_until=pl["valid_until"],
               entitlements=[e for e in pl["entitlements"] if e in FEATURES])
    if pl["machine"] != fp:
        out.update(state="wrong_machine", reason="wrong_machine",
                   message="این مجوز برای سرور دیگری است. اول آن‌جا غیرفعالش کنید، "
                           "بعد این‌جا فعال کنید.")
        return out
    seen = _last_seen(now, write=False)
    if seen and now < seen - CLOCK_SLACK:
        out.update(state="clock", reason="clock",
                   message=f"ساعت سرور به عقب رفته است ({_fa_date(now)}، در حالی که "
                           f"قبلاً {_fa_date(seen)} دیده شده بود). ساعت را درست کنید "
                           "و مجوز را تازه کنید.")
        return out
    _last_seen(now)
    ends = [t for t in (pl["expires"], pl["valid_until"]) if t is not None]
    if not ends:                                        # owner license
        out.update(state="active", pro=True, message="مجوز دائمی مالک.")
        return out
    end = min(ends)
    # Which one lapsed decides what the owner must do: pay, or get online.
    reason = ("payment" if pl["expires"] is not None
              and (pl["valid_until"] is None or pl["expires"] <= pl["valid_until"])
              else "refresh")
    lock_at = end + pl["grace_days"] * 86400
    out["lock_at"] = lock_at
    what = ("اشتراک Pro تمام شده" if reason == "payment"
            else "مجوز مدتی است با سرور مجوز تازه نشده")
    todo = "تمدید کنید" if reason == "payment" else "اینترنت سرور را بررسی و مجوز را تازه کنید"
    if now < end:
        out.update(state="active", pro=True,
                   message=f"Pro فعال است تا {_fa_date(end)}.")
    elif now < lock_at:
        out.update(state="grace", pro=True, reason=reason,
                   message=f"{what}. بخش‌های Pro در {_fa_date(lock_at)} قفل می‌شوند؛ "
                           f"{todo}. مشتری‌ها قطع نمی‌شوند.")
    else:
        out.update(state="expired", reason=reason,
                   message=f"{what} و بخش‌های Pro از {_fa_date(lock_at)} قفل‌اند؛ "
                           f"{todo}. مشتری‌ها قطع نشده‌اند.")
    return out


def allowed(feature, st=None):
    st = st or status()
    return bool(st["pro"]) and feature in st["entitlements"]


def denial(feature, st):
    """Why `feature` is locked, in one Persian sentence."""
    name = FEATURE_FA.get(feature, feature)
    if st["pro"]:
        return f"«{name}» در این مجوز نیست."
    if st["state"] == "none":
        return f"«{name}» بخشی از نسخه‌ی Pro است."
    return f"«{name}» قفل است: {st['message']}"


def requires(feature):
    """FastAPI dependency for a Pro route. List it *after* check_auth so an
    anonymous caller gets the auth error, not the license state."""
    if feature not in FEATURES:
        raise ValueError(f"unknown Pro feature: {feature}")

    def _dep():
        st = status()
        if allowed(feature, st):
            return st
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail=denial(feature, st),
                            headers={"X-Nexora-Pro": feature})
    return _dep


def install(doc, now=None):
    """Store a license the issuer returned, but only if it would be usable
    here. Returns (status, None) or (None, reason): a bad file must never
    replace a good one."""
    pl, why = parse(doc)
    if pl is None:
        return None, why
    if pl["machine"] != fingerprint():
        return None, "wrong_machine"
    _write("license.json", json.dumps(doc))
    reset_clock(now)
    return status(now), None


def remove():
    try:
        _p("license.json").unlink()
    except FileNotFoundError:
        pass


# ── Refresh bookkeeping ───────────────────────────────────────────────────
REFRESH_EVERY = 7 * 86400


def note_refresh(ok, error="", now=None):
    """Record the last attempt; `ok_at` only moves on success, so a week of
    failures shows as a week-old refresh, not as a fresh one."""
    now = int(now or time.time())
    prev = _read_json("license_refresh.json") or {}
    rec = {"ok_at": now if ok else prev.get("ok_at"), "tried_at": now,
           "ok": bool(ok), "error": "" if ok else str(error)[:300]}
    _write("license_refresh.json", json.dumps(rec, ensure_ascii=False))
    return rec


def refresh_info():
    return _read_json("license_refresh.json") or {"ok_at": None, "tried_at": None,
                                                  "ok": None, "error": ""}


def refresh_due(now=None):
    now = int(now or time.time())
    st = status(now)
    if st["state"] in ("none", "invalid", "wrong_machine") or st["plan"] == "owner":
        return False
    ok_at = refresh_info().get("ok_at") or 0
    # "clock" is due at once: only the issuer can vouch for the time.
    return st["state"] == "clock" or now - ok_at >= REFRESH_EVERY


# ── The issuer, over HTTP ─────────────────────────────────────────────────
#: The owner's issuer hostnames, tried in order: one host blocked in Iran must
#: not lock every server out. Names, not addresses: moving the issuer to
#: another server is a DNS change, and no panel needs an update for it.
#: NEXORA_LICENSE_URLS overrides it.
DEFAULT_LICENSE_URLS: list = [
    "https://lic1.imennet-n.ir",
    "https://lic2.imennet-n.ir",
]


def license_urls():
    env = [u.strip().rstrip("/") for u in os.getenv("NEXORA_LICENSE_URLS", "").split(",")
           if u.strip()]
    return env or [u.rstrip("/") for u in DEFAULT_LICENSE_URLS]


def issuer_post(path, payload, urls=None, timeout=15):
    """POST JSON to the first issuer that answers. (json, None), or (None,
    reason naming every URL tried and why). One client for the panel and for
    scripts/pro-fetch.py, so the two can never disagree on which issuer to ask
    or what a refusal means."""
    import urllib.error
    import urllib.request
    urls = license_urls() if urls is None else urls
    if not urls:
        return None, "نشانی سرور مجوز تنظیم نشده است (NEXORA_LICENSE_URLS)"
    body = json.dumps(payload).encode()
    errors = []
    for base in urls:
        try:
            req = urllib.request.Request(f"{base}{path}", data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            # The issuer answered and said no: a reason, not an outage, so the
            # next URL would say the same thing.
            try:
                msg = json.loads(e.read().decode("utf-8")).get("detail") or ""
            except Exception:
                msg = ""
            return None, f"سرور مجوز نپذیرفت ({e.code}): {msg or e.reason}"
        except Exception as e:
            errors.append(f"{base}: {type(e).__name__}: {e}")
    return None, "به سرور مجوز نرسیدیم — " + " | ".join(errors)


# ── Pro bundles ───────────────────────────────────────────────────────────
#: Signed bytes of a bundle manifest start with this, so a license signature
#: can never pass as a manifest, nor a manifest as a license.
BUNDLE_PREFIX = b"nexora-bundle-v1|"


def verify_bundle(manifest, blob, license_id, version):
    """(payload, None) when `blob` is the Pro bundle the issuer signed for this
    license and this panel version; else (None, reason). Nothing may be
    unpacked before this passes: the bundle is code the panel will run."""
    if not isinstance(manifest, dict) or not isinstance(blob, (bytes, bytearray)):
        return None, "malformed"
    kid = manifest.get("kid")
    if kid not in KEYS:
        return None, "unknown_key"
    try:
        body, sig = _b64u(manifest.get("payload")), _b64u(manifest.get("sig"))
    except (ValueError, TypeError):
        return None, "malformed"
    if not verify(KEYS[kid], BUNDLE_PREFIX + body, sig):
        return None, "bad_signature"
    try:
        pl = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "malformed"
    if not (isinstance(pl, dict) and pl.get("kind") == "pro-bundle"
            and isinstance(pl.get("sha256"), str) and isinstance(pl.get("size"), int)):
        return None, "malformed"
    if pl.get("license_id") != license_id:
        return None, "other_license"
    if pl.get("version") != version:
        return None, "other_version"
    if len(blob) != pl["size"] or hashlib.sha256(bytes(blob)).hexdigest() != pl["sha256"]:
        return None, "bad_hash"
    return pl, None
