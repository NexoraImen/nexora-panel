#!/usr/bin/env python3
"""
The core half of selling Pro licenses (Phase 4): the rules every edition
carries, checked without an issuer. The sale itself, against a real issuer,
is tests/pro/test-sell-pro.py.

Spec: docs/specs/2026-09-30-sell-pro.md

- "delivered" is one condition (`db.UNDELIVERED`): a license order has no
  sub_id, so a bare `sub_id IS NULL` anywhere would let a sold license be
  rejected, reverted or approved and paid out again;
- `core.sellable`: licenses only from the root tenant, only with an issuer;
- a Community install (no owner token) cannot sell and says why;
- the rules shared with the private issuer have the same values (parity).

Run:  python3 tests/test-sell-pro-core.py
"""
import ast
import os
import re
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="sellcore_")
os.environ["NEXORA_ISSUER_DIR"] = os.path.join(TMP, "no-issuer")
os.environ["BOT_DB_PATH"] = os.path.join(TMP, "bot.db")
os.environ.pop("NEXORA_ISSUER_OWNER_TOKEN", None)
# A proxy in the environment: a default urllib opener would pick it up (and
# send the owner token through it). license_sale's must not.
os.environ["http_proxy"] = os.environ["HTTP_PROXY"] = "http://127.0.0.1:1"
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "bot")]

G, R, D, X = "\033[38;5;42m", "\033[38;5;203m", "\033[38;5;245m", "\033[0m"
_ok = _fail = 0


def check(name, cond, detail=""):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  {G}✓{X} {name}" + (f" {D}— {detail}{X}" if detail else ""))
    else:
        _fail += 1
        print(f"  {R}✗{X} {name}" + (f" {D}— {detail}{X}" if detail else ""))


def head(t):
    print(f"\n{D}── {t} ──{X}")


import core                                                # noqa: E402
import db                                                  # noqa: E402
import license_sale as LS                                  # noqa: E402

# ═══════════════════════════════════════════════════════════
head("One meaning of 'delivered'")
# ═══════════════════════════════════════════════════════════
check("UNDELIVERED names both markers", "sub_id IS NULL" in db.UNDELIVERED
      and "license_id IS NULL" in db.UNDELIVERED)
bare = []
for base in ("bot", "backend"):
    for p in sorted((ROOT / base).rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if re.search(r"sub_id\s+IS\s+NULL", line, re.I) and "UNDELIVERED =" not in line:
                bare.append(f"{p.relative_to(ROOT)}:{i}")
check("no bare `sub_id IS NULL` left (each would miss license orders)", not bare, ", ".join(bare[:5]))
check("order_delivered: config", core.order_delivered({"sub_id": 3}))
check("order_delivered: license", core.order_delivered({"license_id": "NX-ABCDEFGH"}))
check("order_delivered: neither", not core.order_delivered({"sub_id": None, "license_id": None}))
src = (ROOT / "bot" / "handlers.py").read_text(encoding="utf-8")
check("approve_order's guard uses order_delivered, not sub_id alone",
      'order["status"] == "approved" and core.order_delivered(order)' in src)

# ═══════════════════════════════════════════════════════════
head("Who may sell a license")
# ═══════════════════════════════════════════════════════════
lic, vpn = {"kind": "pro_license"}, {"kind": "volume"}
check("root with an issuer: yes", core.sellable(lic, True, True))
check("root without an issuer: no", not core.sellable(lic, True, False))
check("reseller, even with an issuer: no", not core.sellable(lic, False, True))
check("VPN plans: always", core.sellable(vpn, False, False) and core.sellable({}, False, False))
# A Pro store is one whose plans on sale are all licenses; any VPN plan, or
# nothing on sale, keeps the VPN wording.
check("Pro store: only licenses on sale", core.license_only([lic, lic]))
check("not a Pro store: a VPN plan beside the license", not core.license_only([lic, vpn]))
check("not a Pro store: nothing on sale", not core.license_only([]) and not core.license_only(None))
check("not a Pro store: VPN only", not core.license_only([vpn, {}]))
check("licenses are bot-only", "pro_license" in core.BOT_ONLY_KINDS)
check("license plans are monthly and yearly", [k for k, _ in core.LICENSE_PLANS] == ["monthly", "yearly"])
check("an unknown license plan is monthly", core.clean_license_plan("lifetime") == "monthly")
check("periods are clamped 1..36", (core.clean_periods(0), core.clean_periods("x"),
                                    core.clean_periods(99), core.clean_periods(3)) == (1, 1, 36, 3))
check("the plan line of a license names it, not gigabytes",
      "Pro" in core.plan_spec({"kind": "pro_license", "license_plan": "yearly", "periods": 2})
      and "گیگ" not in core.plan_spec({"kind": "pro_license"}))
check("the plan line of a VPN plan is unchanged", core.plan_spec({"gb": 50, "days": 30})
      == f"{core.fmt_gb(50)} · {core.fmt_days(30)}")

# ═══════════════════════════════════════════════════════════
head("Without an issuer (every Community install)")
# ═══════════════════════════════════════════════════════════
check("cannot sell", LS.available() is False)
ok, why = LS._post("/v1/owner/issue", {})
check("a sale attempt fails and says why, without a network call", ok is False and "ناشر" in why, why)
Path(os.environ["NEXORA_ISSUER_DIR"]).mkdir(parents=True, exist_ok=True)
(Path(os.environ["NEXORA_ISSUER_DIR"]) / "owner-token").write_text("short\n")
check("a truncated token file does not count", LS.available() is False)
os.environ["NEXORA_ISSUER_OWNER_TOKEN"] = "t" * 40
check("the environment variable counts", LS.available() is True)
os.environ.pop("NEXORA_ISSUER_OWNER_TOKEN")
check("the client never uses a proxy (it carries the owner token)",
      not any(getattr(h, "proxies", None) for h in LS._opener.handlers))

# ═══════════════════════════════════════════════════════════
head("Parity with the issuer (private tree only)")
# ═══════════════════════════════════════════════════════════
if (ROOT / "issuer" / "store.py").exists():
    sys.path.insert(0, str(ROOT / "backend"))
    from issuer import store as ST                           # noqa: E402
    check("license plans the bot sells = plans the issuer sells",
          [k for k, _ in core.LICENSE_PLANS] == list(ST.SALE_PLANS))
    check("license id pattern is the issuer's", LS._LICENSE_ID.pattern == ST._LICENSE_ID.pattern)
    check("periods the bot allows fit the issuer's 1..120", core.clean_periods(10**6) <= 120)
    tree = ast.parse((ROOT / "bot" / "license_sale.py").read_text(encoding="utf-8"))
    refs = [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)
            and "ctx.tid" in ast.unparse(n) and "order['id']" in ast.unparse(n)]
    check("the order reference is '<tenant>:<order_id>', the issuer's format",
          bool(refs) and ST._ORDER_REF.match("12:345"))
else:
    print(f"  {D}(Community tree: no issuer to compare with){X}")

print(f"\n{_ok} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
