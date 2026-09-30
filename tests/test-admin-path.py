#!/usr/bin/env python3
"""
نشانیِ مخفیِ پنلِ مدیر — روی خودِ اپ، از راهِ ASGI.

برگه: docs/specs/2026-09-28-admin-path-and-aff-payouts.md

چرا ASGI و نه صدا زدنِ تابع: نگهبان یک middleware است و فقط وقتی اجرا
می‌شود که درخواست واقعاً از اپ رد شود. تست‌های دیگر تابع‌ها را مستقیم
صدا می‌زنند و این در را هرگز نمی‌بینند. `TestClient` هم این‌جا نیست
(httpx نصب نیست)، پس اپ را خودمان با یک scopeِ ساده صدا می‌زنیم.

اجرا:  python3 tests/test-admin-path.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="adminpath_")
os.environ.update(
    BOT_DB_PATH=os.path.join(TMP, "bot.db"),
    BILLING_DB_PATH=os.path.join(TMP, "billing.db"), NEXORA_ADMIN_PASSWORD="testpw",
    CONFIG_PATH=os.path.join(TMP, "config.json"),
    ADMIN_PATH_FILE=os.path.join(TMP, "admin_path.json"))
os.environ.pop("NEXORA_ADMIN_PATH", None)
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "bot"), str(ROOT / "backend")]

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


import app as AP                                          # noqa: E402


def call(path, headers=None, method="GET", body=b""):
    """یک درخواستِ واقعی از میانِ همه‌ی middlewareها — بی شبکه."""
    scope = {"type": "http", "http_version": "1.1", "method": method, "path": path,
             "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "scheme": "https", "server": ("panel.test", 443), "client": ("203.0.113.9", 5555),
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
    out = {"body": b""}
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(m):
        if m["type"] == "http.response.start":
            out["status"] = m["status"]
        elif m["type"] == "http.response.body":
            out["body"] += m.get("body", b"")

    asyncio.run(AP.app(scope, receive, send))
    return out["status"], out["body"].decode("utf-8", "replace")


# ═══════════════════════════════════════════════════════════
head("نشانی ساخته می‌شود و می‌ماند")
# ═══════════════════════════════════════════════════════════
P = AP.admin_path()
check("۲۰ نویسه از الفبای بی‌ابهام", len(P) == 20 and set(P) <= set(AP._ADMIN_PATH_ABC), P)
check("در فایل نوشته شد", json.loads(Path(os.environ["ADMIN_PATH_FILE"]).read_text())["path"] == P)
check("«تازه» علامت خورد تا ربات برای مالک بفرستد", AP._ADMIN_PATH["fresh"] is True)
AP._ADMIN_PATH.update(v=None, fresh=False)
check("خواندنِ دوباره همان نشانی است، نه تازه", AP.admin_path() == P and not AP._ADMIN_PATH["fresh"])

# ═══════════════════════════════════════════════════════════
head("در: بی نشانی، پنلِ مدیر وجود ندارد")
# ═══════════════════════════════════════════════════════════
PW = {"X-Admin-Password": AP._INTERNAL_PW}
st, b = call("/api/admin/ping")
check("بی هدر: ۴۰۴ِ «پیدا نشد» — مثلِ مسیرِ ناموجود", st == 404 and "Not Found" in b, f"{st} {b[:40]}")
st, _ = call("/api/admin/ping", {"X-Admin-Path": "wrongwrongwrongwrong"})
check("نشانیِ غلط: ۴۰۴", st == 404)
st, _ = call("/api/admin/panel-path", PW)
check("رمزِ درست بی نشانی هم ۴۰۴ — رمز به‌تنهایی در را باز نمی‌کند", st == 404)
st, _ = call("/api/login", {"Content-Type": "application/json"}, "POST", json.dumps({"password": AP._INTERNAL_PW}).encode())
check("ورود هم پشتِ همان در است", st == 404)
st, _ = call("/api/admin/ping", {"X-Admin-Path": P})
check("نشانیِ درست: ping عبور می‌کند", st == 200)
st, _ = call("/api/admin/ping", {"X-Admin-Path": "/" + P.upper() + "/"})
check("با اسلش و حروفِ بزرگ هم همان نشانی است", st == 200)
st, b = call("/api/admin/panel-path", {"X-Admin-Path": P})
check("نشانی + بی رمز: هنوز رمز لازم است (۴۲۲/۴۰۱)", st in (401, 422), str(st))
st, b = call("/api/admin/panel-path", {"X-Admin-Path": P, **PW})
check("نشانی + رمز: می‌رسد و نشانی را می‌گوید", st == 200 and json.loads(b)["path"] == P, b[:80])
st, _ = call("/api/login", {"X-Admin-Path": P, "Content-Type": "application/json"}, "POST",
             json.dumps({"password": AP._INTERNAL_PW}).encode())
check("ورود با نشانی: ۲۰۰", st == 200, str(st))

# ═══════════════════════════════════════════════════════════
head("بقیه‌ی دامنه دست نمی‌خورد")
# ═══════════════════════════════════════════════════════════
# /api/mini/*, /api/portal/* and /api/aff/* are Pro (mini app, reseller portal, partner app):
# only in the tree that has them.
for path in ("/api/health", "/api/public/config",
             *(("/api/mini/me", "/api/portal/me", "/api/aff/summary")
               if getattr(AP, "PRO_LOADED", False) else ())):
    st, _ = call(path)
    check(f"{path} بی هدرِ نشانی به خودِ مسیرش می‌رسد (نه ۴۰۴ِ در)", st != 404, str(st))

# ═══════════════════════════════════════════════════════════
head("نشانیِ تازه")
# ═══════════════════════════════════════════════════════════
st, b = call("/api/admin/panel-path/rotate", {"X-Admin-Path": P, **PW}, "POST")
P2 = json.loads(b)["path"] if st == 200 else ""
check("نشانیِ تازه ساخته شد", st == 200 and P2 and P2 != P, b[:80])
st, _ = call("/api/admin/ping", {"X-Admin-Path": P})
check("نشانیِ قبلی همین لحظه ۴۰۴ است", st == 404)
st, _ = call("/api/admin/ping", {"X-Admin-Path": P2})
check("و تازه کار می‌کند", st == 200)

color = G if not _fail else R
print(f"\n  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
