"""
Selling Nexora Pro licenses from the owner's own bot (Phase 4 of 2.0).

Spec: docs/specs/2026-09-30-sell-pro.md

A `pro_license` plan is bought through the normal purchase cores
(`wallet_purchase`, `card_order` → `approve_order`); only delivery differs.
`handlers._provision` calls `deliver_license` instead of 3x-ui, and it returns
`(ok, result)` like the config path, so everything around it is unchanged:
approved only after the license exists, refund or unclaim on failure, the
payout hook, the events.

The issuer runs on the owner's server next to the panel (`/opt/nexora-issuer`)
and is reached on loopback with the owner token, which the issuer's
`cli.py owner-token` writes. Without that token this server cannot sell
licenses: `available()` is False, the bot hides such plans and the panel does
not offer the kind. That is the normal state of every Community install.
"""
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import core
import fmt as F
from tg import esc

log = logging.getLogger(__name__)

ISSUER_URL = os.getenv("NEXORA_ISSUER_OWNER_URL", "http://127.0.0.1:8790").rstrip("/")
TIMEOUT = 15
_LICENSE_ID = re.compile(r"^NX-[0-9A-HJKMNP-TV-Z]{8}$")
_KEY = re.compile(r"^NXP-[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){3}$")

# No proxy: the issuer is on loopback. urllib would otherwise honour an
# HTTP_PROXY left in the environment and send the owner token to it.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _token():
    tok = os.getenv("NEXORA_ISSUER_OWNER_TOKEN", "").strip()
    if tok:
        return tok
    d = Path(os.getenv("NEXORA_ISSUER_DIR") or "/var/lib/nexora-issuer")
    try:
        tok = (d / "owner-token").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return tok if len(tok) >= 32 else ""


def available():
    """Can this server sell licenses? Only where the issuer's owner token is
    readable: the owner's own server."""
    return bool(_token())


def _post(path, body):
    """(True, answer) or (False, a Persian reason for the admin group)."""
    tok = _token()
    if not tok:
        return False, ("این سرور ناشرِ مجوز ندارد (توکنِ مالک پیدا نشد)؛ "
                       "مجوز فروخته نمی‌شود")
    req = urllib.request.Request(
        ISSUER_URL + path, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-Owner-Token": tok})
    try:
        with _opener.open(req, timeout=TIMEOUT) as r:
            return True, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail") or ""
        except (ValueError, AttributeError, OSError):
            detail = ""
        return False, f"سرور مجوز نپذیرفت ({e.code}): {detail}"[:300]
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"سرور مجوز در دسترس نیست: {e}"[:300]


def deliver_license(ctx, order, plan):
    """
    Issue (new order) or extend (renewal order) the license for a paid order.
    Returns (ok, result); result is {"license": {...}, "plan_name": …}.

    The order reference is "<tenant>:<order_id>", and the issuer is
    idempotent on it: a retried approval gets the same license back (with a
    new key, since the issuer keeps only hashes), a repeated renewal extends
    once.
    """
    if ctx.tenant.get("parent_id"):
        # core.sellable already hides these rows from a reseller's shop; this
        # is the last door, for a row written by hand or a forged callback.
        return False, "مجوز Pro را فقط فروشگاهِ مالک می‌فروشد"
    lplan = core.clean_license_plan(plan.get("license_plan"))
    periods = core.clean_periods(plan.get("periods"))
    ref = f"{ctx.tid}:{order['id']}"
    target = order.get("renew_license")

    if target:
        own = ctx.db.user_license(order["user_id"], target)
        if not own:
            return False, "مجوزی که باید تمدید شود مالِ این خریدار نیست"
        if own["plan"] != lplan:
            # The issuer extends by the license's own unit: a yearly plan on a
            # monthly license would buy months while charging for years.
            return False, "پلنِ تمدید با نوعِ این مجوز (ماهانه/سالانه) جور نیست"
        ok, r = _post("/v1/owner/extend",
                      {"order_ref": ref, "license_id": target, "periods": periods})
        if not ok:
            return False, r
        lid, key = r.get("license_id"), None
    else:
        buyer = ctx.db.get_user_by_id(order["user_id"]) or {}
        ok, r = _post("/v1/owner/issue",
                      {"order_ref": ref, "plan": lplan, "periods": periods,
                       "note": f"tg {buyer.get('tg_id') or '?'}"})
        if not ok:
            return False, r
        lid, key = r.get("license_id"), r.get("key")
        if not (isinstance(key, str) and _KEY.match(key)):
            return False, "پاسخِ سرور مجوز کلیدِ معتبری نداشت"
    if not (isinstance(lid, str) and _LICENSE_ID.match(lid)):
        return False, "پاسخِ سرور مجوز شناسه‌ی معتبری نداشت"
    expires = r.get("expires") if isinstance(r.get("expires"), int) else None

    # The delivered marker (db.UNDELIVERED) before success is reported: it is
    # what refuses a second approval, a reject and a revert of this order.
    ctx.db.exec("UPDATE orders SET license_id=? WHERE tenant_id=? AND id=?",
                (lid, ctx.tid, order["id"]))
    ctx.db.save_license(order["user_id"], order["id"], lid, lplan, expires,
                        key[-4:] if key else None)
    if r.get("repeat"):
        log.warning("order %s: the issuer already had it (%s); %s", ref, lid,
                    "new key sent" if key else "not extended twice")
    return True, {"license": {"id": lid, "key": key, "expires": expires, "plan": lplan,
                              "periods": periods, "renewed": bool(target)},
                  "plan_name": plan.get("name") or ""}


def _date(ts):
    if not ts:
        return "—"
    return core.fa_date(time.strftime("%Y-%m-%d", time.localtime(ts)))


def delivery_text(lic):
    """The buyer's message. The key is in it exactly once: the issuer cannot
    show it again (only its hash is kept)."""
    if lic.get("renewed"):
        return "\n".join([
            F.header("مجوز Pro تمدید شد", "✅"),
            "",
            f"🔑 شناسه  {F.code(lic['id'])}",
            F.row("اعتبارِ تازه", f"تا {_date(lic.get('expires'))}", "⏳"),
            "",
            F.quote("کلید عوض نشده است. سرورتان تمدید را در به‌روزرسانیِ بعدیِ "
                    "مجوز می‌بیند: هفته‌ای یک‌بار خودکار، یا همین حالا با دکمه‌ی "
                    "تازه‌کردن در کارتِ مجوزِ پنل."),
        ])
    return "\n".join([
        F.header("مجوز نکسورا Pro شما آماده است", "🔑"),
        "",
        f"🏷 شناسه  {F.code(lic['id'])}",
        F.row("اعتبار", f"تا {_date(lic.get('expires'))}", "⏳"),
        "",
        F.section("کلیدِ مجوز", "🔐"),
        F.code(lic["key"]),
        "",
        F.quote_more(
            F.b("فعال‌سازی"),
            "",
            "۱. پنل نکسورا را باز کنید و به «به‌روزرسانی» بروید.",
            "۲. کلید را در کارتِ مجوز بچسبانید و «فعال‌سازی» را بزنید.",
            "۳. بعد «نصبِ بسته‌ی Pro» را بزنید.",
        ),
        "",
        "⚠️ " + F.b("این کلید فقط همین یک‌بار فرستاده می‌شود") +
        "؛ جای امنی نگهش دارید. هر مجوز روی یک سرور فعال می‌شود.",
    ])


def license_line(row):
    """One license in "my subscriptions"."""
    exp = row.get("expires")
    over = exp is not None and exp < time.time()
    plan = dict(core.LICENSE_PLANS).get(row.get("plan"), "")
    return (f"{'🔴' if over else '🔑'} {F.b('نکسورا Pro')} {esc(plan)} · "
            f"{F.code(row['license_id'])}\n"
            + (f"⛔ {F.b('اعتبار تمام شده')} (تا {_date(exp)} بود)" if over
               else f"⏳ تا {_date(exp)}")
            + (f" · کلید …{esc(row['key_hint'])}" if row.get("key_hint") else ""))
