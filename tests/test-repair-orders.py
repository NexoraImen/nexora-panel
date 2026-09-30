#!/usr/bin/env python3
"""
تست ابزار اصلاح وضعیت سفارش‌های کیف پول.

چرا وجود دارد:
    این ابزار روی دیتابیسِ واقعیِ فروش می‌نویسد و همان ستونی را عوض
    می‌کند که همه‌ی آمارهای فروش از رویش شمرده می‌شوند. یک شرطِ کمی
    گشاد یعنی سفارشی که واقعاً منقضی شده «فروش» شود، و یک شرطِ کمی
    تنگ یعنی فروشِ واقعی همچنان دیده نشود.

    پس اینجا یک دیتابیسِ ساختگی با یازده حالت ساخته می‌شود — چهار
    تا که باید عوض شوند و هفت تا که به هیچ وجه نباید — و بعد از
    اجرا تک‌تکشان سنجیده می‌شوند.

اجرا:  python3 tests/test-repair-orders.py
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = str(ROOT / "scripts" / "repair-orders.py")

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


# ═══ دیتابیس ساختگی ═══
tmpdir = tempfile.mkdtemp()
DBP = os.path.join(tmpdir, "bot.db")

con = sqlite3.connect(DBP)
con.executescript("""
CREATE TABLE orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, user_id INTEGER,
  plan_id INTEGER, kind TEXT, amount INTEGER, base_amount INTEGER,
  paid_from TEXT, status TEXT, admin_note TEXT, sub_id INTEGER,
  created_at TEXT, expires_at TEXT);
CREATE TABLE wallet_tx (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, user_id INTEGER,
  amount INTEGER, kind TEXT, note TEXT, order_id INTEGER, created_at TEXT);
""")


def order(oid, kind, status, amount, sub_id, paid_from="wallet"):
    con.execute("INSERT INTO orders (id,tenant_id,user_id,kind,amount,"
                "base_amount,paid_from,status,sub_id,created_at) "
                "VALUES (?,1,7,?,?,?,?,?,?,'2026-09-01')",
                (oid, kind, amount, amount, paid_from, status, sub_id))


def tx(oid, amount, kind):
    con.execute("INSERT INTO wallet_tx (tenant_id,user_id,amount,kind,"
                "order_id,created_at) VALUES (1,7,?,?,?,'2026-09-01')",
                (amount, kind, oid))


#: هر ردیف: (شناسه, توضیح, وضعیتی که باید بعدش داشته باشد)
CASES = [
    (1, "خرید کیف پول که تحویل شد و جاروکش «منقضی»‌اش کرد", "approved"),
    (2, "خرید کیف پول که تحویل شد و pending ماند", "approved"),
    (3, "تمدید ناموفق که پولش برگشت ولی approved ماند", "rejected"),
    (4, "همان، با برگشتِ قدیمیِ بدون order_id", "rejected"),
    (5, "تمدید واقعاً موفق", "approved"),
    (6, "فروش کارتی", "approved"),
    (7, "سفارشی که واقعاً بی‌پرداخت منقضی شد", "expired"),
    (8, "خریدی که خطا خورد و پولش برگشت", "rejected"),
    (9, "پول رفت، کانفیگی ساخته نشد، برگشتی هم نبود", "expired"),
    (10, "کانفیگ ساخته شد ولی بعداً پولش برگشت", "expired"),
    (11, "خریدِ approved بدون کانفیگ — از قاعده‌ی تمدید بیرون است",
     "approved"),
]

# ۱ و ۲: پول رفت، برنگشت، کانفیگ ساخته شد → فروشِ واقعی
order(1, "new", "expired", 200_000, 55)
tx(1, -200_000, "spend")
order(2, "new", "pending", 300_000, 56)
tx(2, -300_000, "spend")
# ۳ و ۴: کانفیگی ساخته نشد → فروش نبوده
order(3, "renew", "approved", 200_000, None)
tx(3, -200_000, "renew")
tx(3, 200_000, "refund")
order(4, "renew", "approved", 200_000, None)
tx(4, -200_000, "renew")
con.execute("INSERT INTO wallet_tx (tenant_id,user_id,amount,kind,order_id,"
            "created_at) VALUES (1,7,200000,'refund',NULL,'2026-09-01')")
# ۵ تا ۸: هیچ‌کدام نباید دست بخورند
order(5, "renew", "approved", 200_000, 57)
tx(5, -200_000, "renew")
order(6, "new", "approved", 200_000, 58, paid_from="card")
order(7, "new", "expired", 200_000, None)
order(8, "new", "rejected", 200_000, None)
tx(8, -200_000, "spend")
tx(8, 200_000, "refund")

# ۹ تا ۱۱ مرزها را نگه می‌دارند. بدون اینها شرط‌های ابزار می‌توانستند
# گشاد شوند و تست همچنان سبز بماند — که یک بار واقعاً شد.
#
# ۹: پول کم شده، کانفیگی نیست، برگشتی هم نیست. یعنی ربات وسطِ کار
#    ایستاده. «فروش» نیست و ابزار نباید خودش تصمیم بگیرد — فقط
#    گزارشش می‌کند.
order(9, "new", "expired", 200_000, None)
tx(9, -200_000, "spend")
# ۱۰: کانفیگ ساخته شد ولی پول برگشته. پس فروش نبوده.
order(10, "new", "expired", 200_000, 59)
tx(10, -200_000, "spend")
tx(10, 200_000, "refund")
# ۱۱: سفارشِ «جدید» که approved است و کانفیگ ندارد. قاعده‌ی این
#     ابزار درباره‌ی تمدیدهاست؛ این یکی را باید به حال خود بگذارد.
order(11, "new", "approved", 200_000, None)
con.commit()
con.close()

ENV = dict(os.environ, BOT_DB_PATH=DBP, PYTHONIOENCODING="utf-8")


def run(*args):
    r = subprocess.run([sys.executable, TOOL, *args], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def statuses():
    c = sqlite3.connect(DBP)
    try:
        return {r[0]: r[1] for r in c.execute("SELECT id,status FROM orders")}
    finally:
        c.close()


# ═══════════════════════════════════════════════════════════
head("بدون --apply چیزی نباید نوشته شود")

before = statuses()
rc, out = run()
check("اجرا بدون خطا", rc == 0, f"rc={rc}")
check("هیچ ردیفی عوض نشد", statuses() == before,
      "پیش‌نمایش باید بی‌خطر باشد")
check("و می‌گوید که چیزی ننوشته", "Nothing written" in out)
check("تغییرِ آمار را گزارش می‌کند", "reported sales change: +100,000" in out,
      "۵۰۰٬۰۰۰ اضافه، ۴۰۰٬۰۰۰ کم")
check("سفارشِ نیازمندِ بررسی دستی را جدا می‌کند",
      "Check by hand" in out and "#4" in out,
      "برگشتِ قدیمی به سفارش گره نخورده بود")
check("سفارشِ پول‌گرفته و تحویل‌نشده را جدا گزارش می‌کند",
      "never refunded" in out and "LEFT ALONE" in out,
      "مشتری پولش رفته و چیزی نگرفته — تصمیمش با صاحب سیستم است")

# ═══════════════════════════════════════════════════════════
head("با --apply هر یازده حالت درست می‌شود")

rc, out = run("--apply")
check("اجرا بدون خطا", rc == 0, f"rc={rc}")
now = statuses()
for oid, what, want in CASES:
    check(f"#{oid} {what}", now.get(oid) == want,
          f"{now.get(oid)} ← باید {want} باشد")

# ═══════════════════════════════════════════════════════════
head("اجرای دوباره نباید چیزی پیدا کند")

rc, out = run("--apply")
again = statuses()
check("اجرا بدون خطا", rc == 0, f"rc={rc}")
check("چیزی برای اصلاح نمانده", "Nothing to repair" in out)
check("و هیچ ردیفی دوباره عوض نشد", again == now,
      "اجرای دوباره باید بی‌اثر باشد")

# ═══════════════════════════════════════════════════════════
head("دیتابیسِ بی‌ربط نباید ابزار را بترکاند")

empty = os.path.join(tmpdir, "empty.db")
sqlite3.connect(empty).close()
r = subprocess.run([sys.executable, TOOL, "--apply"], cwd=str(ROOT),
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace",
                   env=dict(os.environ, BOT_DB_PATH=empty,
                            PYTHONIOENCODING="utf-8"))
check("بدون جدولِ سفارش، تمیز بیرون می‌آید", r.returncode == 0,
      f"rc={r.returncode}")
check("و می‌گوید چیزی برای اصلاح نیست",
      "nothing to repair" in (r.stdout or "").lower())

# ═══════════════════════════════════════════════════════════
head("دستور در nexora-cli.sh درست وصل شده")

# نکته: کامنت‌ها اول برداشته می‌شوند. سه بار پیش آمده که تست با
# وجود باگ سبز مانده، چون رشته‌ای که دنبالش بودم در توضیحِ خودم
# پیدا می‌شد نه در کد.
import io                                              # noqa: E402

CLI = io.open(str(ROOT / "nexora-cli.sh"), encoding="utf-8").read()
_blk = CLI[CLI.index("  repair-orders)"):]
_blk = _blk[:_blk.index("\n    ;;")]
_code = "\n".join(l for l in _blk.split("\n")
                  if not l.strip().startswith("#"))

check("شاخه‌ی repair-orders وجود دارد", "repair-orders)" in CLI)
check("shift دارد", "shift" in _code,
      "بدون آن، نامِ خودِ دستور به argparse می‌رسد و رد می‌شود")
check("مسیر دیتابیس ربات را می‌دهد", "BOT_DB_PATH=" in _code)
check("آرگومان‌ها را رد می‌کند", '"$@"' in _code,
      "وگرنه --apply هیچ‌وقت نمی‌رسد")
check("در فهرست راهنما آمده", "nexora repair-orders" in CLI)

shutil.rmtree(tmpdir, ignore_errors=True)

print(f"\n{D}{'─' * 46}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}  |  {D}{_fail} ناموفق{X}")
print()
sys.exit(1 if _fail else 0)
