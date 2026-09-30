#!/usr/bin/env python3
"""
تشخیص قطعی مشکل حسابداری.

روی سرور اجرا کنید:

    cd /opt/nexora-panel
    python3 scripts/billing-trace.py

این اسکریپت دقیقاً همان کدی را اجرا می‌کند که پنل اجرا می‌کند،
ولی به‌جای بلعیدن خطا، کل traceback را چاپ می‌کند. خروجی‌اش
دقیقاً می‌گوید کدام خط شکست خورده.
"""

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("CONFIG_PATH", str(ROOT / "data" / "config.json"))

G = "\033[38;5;42m"
R = "\033[38;5;203m"
Y = "\033[38;5;220m"
D = "\033[38;5;245m"
B = "\033[38;5;39m"
X = "\033[0m"


def ok(m):
    print(f"  {G}✓{X} {m}")


def bad(m):
    print(f"  {R}✗{X} {m}")


def warn(m):
    print(f"  {Y}!{X} {m}")


def dim(m):
    print(f"  {D}{m}{X}")


def head(m):
    print(f"\n{B}── {m} ──{X}")


print(f"\n{B}تشخیص قطعی حسابداری نکسورا{X}")

# ═══════════════════════════════════════════════
head("۱. بارگذاری کد پنل")

try:
    import app as A
    ok(f"app.py بارگذاری شد — نسخه {(ROOT / 'VERSION').read_text().strip() if (ROOT / 'VERSION').exists() else '?'}")
except Exception:
    bad("بارگذاری app.py شکست خورد:")
    traceback.print_exc()
    sys.exit(1)

# Since 2.0 accounting is Pro (backend/pro/accounting.py). Without the Pro
# package the check below would blame an old version and send the owner to
# `nexora update`, which changes nothing; say what is really missing.
if not getattr(A, "PRO_LOADED", True):
    bad("Accounting is part of Nexora Pro, and this server has no Pro package loaded.")
    if getattr(A, "PRO_ERROR", ""):
        dim(f"Pro failed to load: {A.PRO_ERROR}")
    sys.exit(2)

# آیا این نسخه محافظ دارد؟
has_guard = hasattr(A, "_billing_overview_impl")
if has_guard:
    ok("این نسخه محافظ خطا دارد (۱.۰.۳ به بالا)")
else:
    warn("این نسخه محافظ خطا ندارد — احتمالاً ۱.۰.۲ یا قدیمی‌تر")
    dim("بعد از این تشخیص، nexora update را بزنید")

# ═══════════════════════════════════════════════
head("۲. مسیر دیتابیس x-ui")

try:
    path = A._xui_db_path()
    ok(f"مسیر: {path}")
    dim(f"وجود دارد: {path.exists()}  ·  خواندنی: {os.access(path, os.R_OK) if path.exists() else '—'}")
except Exception:
    bad("تعیین مسیر شکست خورد:")
    traceback.print_exc()
    sys.exit(1)

# ═══════════════════════════════════════════════
head("۳. باز کردن دیتابیس x-ui")

try:
    res = A._xui_conn()
    con, err = res if isinstance(res, tuple) else (res, None)
    if con:
        ok("باز شد")
        try:
            n = con.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            ok(f"{n} کانفیگ")
        except Exception as e:
            warn(f"شمارش کلاینت: {e}")
        con.close()
    else:
        bad(f"باز نشد: {err}")
        sys.exit(1)
except Exception:
    bad("خطای غیرمنتظره:")
    traceback.print_exc()
    sys.exit(1)

# ═══════════════════════════════════════════════
head("۴. خواندن کامل کلاینت‌ها")

try:
    out = A._read_xui_clients()
    if len(out) == 3:
        clients, groups, rerr = out
    else:
        clients, rerr = out
        groups = []
    if clients is None:
        bad(f"ناموفق: {rerr}")
        sys.exit(1)
    ok(f"{len(clients)} کانفیگ، {len(groups or [])} گروه")
    if groups:
        dim("گروه‌ها: " + "، ".join(groups[:10]))
except Exception:
    bad("کرش:")
    traceback.print_exc()
    sys.exit(1)

# ═══════════════════════════════════════════════
head("۵. دیتابیس حسابداری نکسورا")

bpath = getattr(A, "BILLING_DB", None)
if bpath:
    dim(f"مسیر: {bpath}")
    if Path(bpath).exists():
        st = Path(bpath).stat()
        dim(f"حجم: {st.st_size:,} بایت  ·  مجوز: {oct(st.st_mode)[-3:]}")
    else:
        dim("هنوز ساخته نشده — با اولین استفاده ساخته می‌شود")

try:
    bcon = A._billing_conn()
    ok("باز شد")
    tables = [r[0] for r in bcon.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    dim("جدول‌ها: " + "، ".join(tables))
    for t in ("group_config", "payments", "renewals"):
        try:
            n = bcon.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            dim(f"  {t}: {n} ردیف")
        except Exception as e:
            warn(f"  {t}: {str(e)[:60]}")
    bcon.close()
except Exception:
    bad("کرش — این احتمالاً مشکل شماست:")
    traceback.print_exc()
    print()
    print(f"  {Y}رفع:{X} فایل حسابداری را کنار بگذارید و از نو ساخته شود:")
    print(f"    mv {bpath} {bpath}.broken")
    print(f"    systemctl restart nexora-panel")
    sys.exit(1)

# ═══════════════════════════════════════════════
head("۶. محاسبه‌ی کامل — همان چیزی که پنل صدا می‌زند")

PW = os.getenv("NEXORA_PW", "")
if not PW:
    auth = ROOT / "data" / "auth.json"
    if auth.exists():
        dim("رمز از auth.json خوانده نمی‌شود (هش است) — با متغیر بدهید:")
        dim("  NEXORA_PW='رمز-پنل' python3 scripts/billing-trace.py")
        dim("فعلاً منطق را بدون احراز هویت اجرا می‌کنم:")

try:
    impl = getattr(A, "_billing_overview_impl", None)
    if impl:
        result = impl()
    else:
        # نسخه‌ی قدیمی — بدنه‌ی تابع را مستقیم صدا می‌زنیم
        import inspect
        src = inspect.getsource(A.billing_overview)
        dim("نسخه‌ی قدیمی — با احراز هویت اجرا می‌شود")
        result = A.billing_overview(x_admin_password=PW) if PW else None
        if result is None:
            warn("برای این نسخه رمز لازم است. دوباره با NEXORA_PW اجرا کنید.")
            sys.exit(0)

    if result.get("ready"):
        ok(f"موفق — {len(result.get('groups', []))} گروه")
        print()
        for g in result.get("groups", []):
            mark = f"{G}●{X}" if g.get("billable") else f"{D}○{X}"
            print(f"    {mark} {g['key']:<20} {g['configs']:>4} کانفیگ  "
                  f"{g.get('usedGB', 0):>8} GB")
    else:
        bad(f"ناموفق: {result.get('error')}")
except Exception:
    bad("کرش — traceback کامل:")
    print()
    traceback.print_exc()
    print()
    print(f"  {Y}این خروجی را بفرستید تا دقیقاً رفع شود.{X}")
    sys.exit(1)

# ═══════════════════════════════════════════════
head("نتیجه")
print()
ok("همه‌چیز از داخل کد کار می‌کند")
dim("اگر پنل هنوز خطا می‌دهد، مشکل در ارتباط مرورگر با سرور است:")
dim("  systemctl restart nexora-panel")
dim("  و بعد صفحه را با Ctrl+Shift+R تازه کنید")
print()
