#!/usr/bin/env python3
"""
پشتیبان‌گیری و بازگردانی — چیزی که فقط یک بار لازم می‌شود، و همان بار
باید کار کند.

چرا وجود دارد:
    فهرست جدول‌هایی که پشتیبان می‌گیرد، دستی نوشته شده بود. هر بار که
    قابلیت تازه‌ای جدول تازه‌ای اضافه کرد، آن فهرست به‌روز نشد — و
    هیچ‌جا هم خطایی نداد. پشتیبان با «ok» دانلود می‌شد و جدول‌های
    جامانده در آن نبودند.

    برای همکاری در فروش یعنی خودِ همکارها، پورسانت‌هایشان و پرداخت‌های
    انجام‌شده؛ برای حسابداری یعنی کل بخش هزینه‌ها. پولی که به آدم‌های
    واقعی بدهکارید.

    و بازگردانی هر ردیفی را که درج نشود بی‌صدا رد می‌کرد، بعد
    «ok: true» برمی‌گرداند.

اجرا:  python3 tests/test-backup.py
"""
import importlib.util
import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


TMP = tempfile.mkdtemp()
BOT = os.path.join(TMP, "bot.db")
os.environ["BOT_DB_PATH"] = BOT
os.environ["NEXORA_DATA_DIR"] = TMP

# ── دیتابیس ربات را با همان اسکیمای واقعی می‌سازیم ──
sys.path.insert(0, ROOT)
os.environ.setdefault("BOT_DB_PATH", BOT)
from bot import db as BDB  # noqa: E402

BDB.init_db()
tid = BDB.create_tenant("فروشگاه", bot_token="1:T", owner_tg_id=7)
d = BDB.TenantDB(tid)

uid = d.exec("INSERT INTO users (tenant_id, tg_id, first_name, balance, coins)"
             " VALUES (?,?,?,?,?)", (tid, 111, "مشتری", 50000, 9))
pid = d.exec("INSERT INTO plans (tenant_id, name, gb, days, price)"
             " VALUES (?,?,?,?,?)", (tid, "یک‌ماهه", 50, 30, 190000))
aid = d.exec("INSERT INTO affiliates (tenant_id, name, code, percent, active)"
             " VALUES (?,?,?,?,1)", (tid, "همکار اول", "AFF1", 15))
d.exec("UPDATE users SET affiliate_id=? WHERE tenant_id=? AND id=?",
       (aid, tid, uid))
o = d.create_order(uid, pid, 190000, 190000)
BDB.record_commission(tid, uid, o["id"], 190000)
d.exec("INSERT INTO affiliate_payouts (tenant_id, affiliate_id, amount, note)"
       " VALUES (?,?,?,?)", (tid, aid, 28500, "تسویه‌ی مهر"))

spec = importlib.util.spec_from_file_location(
    "nxapp", os.path.join(ROOT, "backend", "app.py"))
APP = importlib.util.module_from_spec(spec)
sys.modules["nxapp"] = APP
spec.loader.exec_module(APP)
APP.BOT_DB = Path(BOT)
APP.BILLING_DB = Path(TMP) / "billing.db"
APP.check_auth = lambda pw: True


def rows_in(table, db=BOT):
    c = sqlite3.connect(db)
    try:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return -1
    finally:
        c.close()


# ═══════════════════════════════════════════════════════════
head("پشتیبان ربات باید همه‌ی جدول‌ها را داشته باشد")

bak = APP.bot_backup(x_admin_password="x")
have = set(bak["data"])

c = sqlite3.connect(BOT)
real = {r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")} - {"sqlite_sequence"}
c.close()

missing = sorted(real - have)
check("هیچ جدولی از قلم نیفتاده", not missing,
      "جامانده: " + "، ".join(missing) if missing else "")

for t in ("affiliates", "affiliate_commissions", "affiliate_payouts"):
    check(f"«{t}» در پشتیبان هست", t in have,
          "پول همکار فروش" if t != "affiliates" else "خودِ همکارها")

check("و ردیف‌هایشان واقعاً پر است",
      len(bak["data"].get("affiliates") or []) == 1
      and len(bak["data"].get("affiliate_commissions") or []) == 1
      and len(bak["data"].get("affiliate_payouts") or []) == 1,
      "فهرست خالی یعنی پشتیبانِ بی‌فایده")

check("شمارش‌ها با داده جور است",
      all(bak["counts"][k] == len(v) for k, v in bak["data"].items()))


head("بازگردانی همان چیزی را برمی‌گرداند که برداشته")

before = {t: rows_in(t) for t in sorted(real)}
for t in ("affiliate_payouts", "affiliate_commissions", "affiliates",
          "subscriptions", "orders", "users"):
    cx = sqlite3.connect(BOT)
    cx.execute(f"DELETE FROM {t}")
    cx.commit()
    cx.close()

res = APP.bot_restore({"data": bak["data"]}, x_admin_password="x")
check("بازگردانی موفق اعلام می‌شود", res.get("ok") is True)

after = {t: rows_in(t) for t in sorted(real)}
lost = {t: (before[t], after[t]) for t in before if before[t] != after[t]}
check("هیچ ردیفی گم نشده", not lost,
      "، ".join(f"{t}: {a}→{b}" for t, (a, b) in lost.items()) or "")

check("همکار فروش برگشت", rows_in("affiliates") == 1,
      str(rows_in("affiliates")))
check("پورسانتش هم برگشت", rows_in("affiliate_commissions") == 1,
      str(rows_in("affiliate_commissions")))
check("و پرداختی که به او شده", rows_in("affiliate_payouts") == 1,
      str(rows_in("affiliate_payouts")))


head("بازگردانیِ ناقص باید داد بزند، نه «ok»")

bad = {k: list(v) for k, v in bak["data"].items()}
# ردیفی بدون tg_id — ستونی که NOT NULL است، پس درج واقعاً شکست می‌خورد
bad["users"] = bad["users"] + [{"id": 999, "tenant_id": tid}]
res2 = APP.bot_restore({"data": bad}, x_admin_password="x")
check("ردیفی که درج نشد گزارش می‌شود", bool(res2.get("skipped")),
      f"restored={res2.get('restored', {}).get('users')} از {len(bad['users'])}")
check("و پیام قابل‌خواندن دارد", "users" in (res2.get("warning") or ""),
      res2.get("warning") or "بدون پیام")
check("بازگردانی سالم هیچ هشداری ندارد",
      not APP.bot_restore({"data": bak["data"]},
                          x_admin_password="x").get("skipped"),
      "وگرنه هشدارِ همیشگی یعنی هشدارِ نادیده‌گرفته‌شده")
check("و دلیلِ ردیفِ جامانده را هم می‌گوید، نه فقط تعداد",
      "NOT NULL" in (res2.get("skippedWhy") or {}).get("users", "")
      and "NOT NULL" in (res2.get("warning") or ""),
      (res2.get("skippedWhy") or {}).get("users", "بدون دلیل"))

head("خالی‌نشدنِ جدول، بازگردانی را متوقف می‌کند")

# پیش‌تر DELETEِ ناموفق با pass بلعیده می‌شد و INSERT OR REPLACE ردیف‌های
# پشتیبان را روی ردیف‌های قدیمی می‌ریخت — مخلوطی که هیچ‌جا ثبت نبود.
import sqlite3 as _sq
_c = _sq.connect(":memory:")
_c.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
_c.execute("INSERT INTO t VALUES (1, 'old'), (2, 'old')")
_c.execute("CREATE TRIGGER no_del BEFORE DELETE ON t BEGIN SELECT RAISE(ABORT, 'locked'); END")
try:
    APP._restore_tables(_c, ["t"], {"t": [{"id": 3, "v": "new"}]})
    _stopped = False
except RuntimeError as e:
    _stopped = "locked" in str(e)
check("DELETEِ ناموفق خطا می‌دهد، نه ادامه", _stopped)
check("و ردیفِ تازه روی قدیمی‌ها ریخته نشده",
      [r[0] for r in _c.execute("SELECT id FROM t ORDER BY id")] == [1, 2])
_c.close()

head("نسخه‌ی امنِ ناموفق گفته می‌شود")
# بی نسخه‌ی امن راهِ برگشت نیست؛ حسابداری این را می‌گفت و ربات نه
_orig_copy = APP._sqlite_copy
APP._sqlite_copy = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
try:
    _rs = APP.bot_restore({"data": bak["data"]}, x_admin_password="x")
finally:
    APP._sqlite_copy = _orig_copy
check("بازگردانیِ ربات بی نسخه‌ی امن هشدار می‌دهد",
      _rs.get("safetyWarning") and _rs.get("safetyCopy") is None, str(_rs.get("safetyWarning")))

head("یک حلقه‌ی بازگردانی، نه دو")

import ast as _ast
_tree = _ast.parse(open(os.path.join(ROOT, "backend", "app.py"), encoding="utf-8").read())
_fns = {n.name: n for n in _ast.walk(_tree) if isinstance(n, _ast.FunctionDef)}
for _name in ("bot_restore", "billing_restore"):
    _calls = {getattr(c.func, "id", "") for c in _ast.walk(_fns[_name]) if isinstance(c, _ast.Call)}
    _own = any(isinstance(n, _ast.Constant) and isinstance(n.value, str)
               and n.value.startswith("DELETE FROM") for n in _ast.walk(_fns[_name]))
    check(f"{_name} از _restore_tables می‌گذرد و حلقه‌ی خودش را ندارد",
          "_restore_tables" in _calls and not _own,
          "دو نسخه‌ی این حلقه در دو جهت از هم دور افتاده بودند")

head("پشتیبانِ نسخه‌ی قدیمی هم بازمی‌گردد")

old_style = {k: v for k, v in bak["data"].items()
             if not k.startswith("affiliate")}
res3 = APP.bot_restore({"data": old_style}, x_admin_password="x")
check("پشتیبانی که جدول‌های تازه را ندارد قبول می‌شود",
      res3.get("ok") is True)
check("و جدولی که در آن نبوده خالی نمی‌شود",
      rows_in("affiliates") == 1,
      f"{rows_in('affiliates')} همکار — نبودنِ جدول در فایل یعنی «نمی‌دانم»، نه «حذف کن»")


head("پشتیبان حسابداری")

bcon = APP._billing_conn()
bcon.execute("INSERT INTO group_config (group_key,label,billable) "
             "VALUES ('ali','ali',1)")
bcon.execute("INSERT INTO expenses (kind, label, amount, amount_irt, spent_at) "
             "VALUES ('server_abroad','سرور خارج',30,1800000,'2026-09-01')")
bcon.commit()
bcon.close()

bb = APP.billing_backup(x_admin_password="x")
bcon = APP._billing_conn()
btables = {r[0] for r in bcon.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")} - {
    "sqlite_sequence", "bot_flags"}
bcon.close()

bmissing = sorted(btables - set(bb["data"]))
check("هیچ جدول حسابداری از قلم نیفتاده", not bmissing,
      "جامانده: " + "، ".join(bmissing) if bmissing else "")
check("«expenses» در پشتیبان هست", "expenses" in bb["data"],
      "بخش هزینه‌ها — سرور خارج، سرور ایران، خرید ترافیک")
check("و ردیفش پر است", len(bb["data"].get("expenses") or []) == 1)

head("بازگردانی حسابداری")

def brows(t):
    c = APP._billing_conn()
    try:
        return c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    finally:
        c.close()

c2 = APP._billing_conn()
c2.execute("DELETE FROM expenses")
c2.execute("DELETE FROM group_config")
c2.commit()
c2.close()

r = APP.billing_restore({"data": bb["data"]}, x_admin_password="x")
check("بازگردانی حسابداری موفق است", r.get("ok") is True)
check("هزینه‌ها برمی‌گردند", brows("expenses") == 1, str(brows("expenses")))
check("نرخ گروه‌ها هم", brows("group_config") == 1, str(brows("group_config")))
check("و هیچ هشداری نیست", not r.get("skipped"))

head("پشتیبان قدیمیِ حسابداری، هزینه‌ها را پاک نمی‌کند")

legacy = {k: v for k, v in bb["data"].items()
          if k in ("group_config", "payments", "renewals")}
APP.billing_restore({"data": legacy}, x_admin_password="x")
check("جدولی که در فایل نبود دست‌نخورده می‌ماند",
      brows("expenses") == 1,
      f"{brows('expenses')} هزینه — قبلاً بی‌قید خالی می‌شد")



print(f"\n{D}{'─' * 50}{X}")
color = G if not _fail else R
# ═══════════════════════════════════════════════════════════
head("کپی گرفتن از دیتابیسی که WAL دارد")

# bot.db با WAL کار می‌کند. هر چیزی که هنوز به فایل اصلی منتقل نشده
# در «-wal» می‌نشیند، نه در خود فایل. پس cp ساده می‌تواند ساعت‌ها
# سفارش و پرداخت را جا بگذارد — و این دقیقاً همان نسخه‌ای است که
# «قبل از بازگردانی» گرفته می‌شد و rollback به آن برمی‌گردد.

import shutil as _sh   # noqa: E402

_wd = tempfile.mkdtemp()
_src = os.path.join(_wd, "wal.db")
_c = sqlite3.connect(_src)
_c.execute("PRAGMA journal_mode=WAL")
_c.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER)")
_c.commit()
# ردیف‌هایی که در WAL می‌مانند: چک‌پوینت نمی‌زنیم
_c.executemany("INSERT INTO orders (amount) VALUES (?)",
               [(i * 1000,) for i in range(1, 51)])
_c.commit()

check("‎-wal واقعاً محتوا دارد",
      os.path.exists(_src + "-wal") and os.path.getsize(_src + "-wal") > 0,
      "بدون این، تست چیزی را نمی‌سنجد")

# ── کپی ساده‌ی فایل: همان کاری که قبلاً می‌شد ──
_plain = os.path.join(_wd, "plain.db")
_sh.copy2(_src, _plain)
_p = sqlite3.connect(_plain)
try:
    _plain_n = _p.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
except Exception:
    _plain_n = -1
_p.close()

# ── کپی سازگار ──
_good = os.path.join(_wd, "good.db")
APP._sqlite_copy(_src, _good)
_g = sqlite3.connect(_good)
_good_n = _g.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
_g.close()
_c.close()

check("کپی سازگار همه‌ی ردیف‌ها را دارد", _good_n == 50, f"{_good_n} از ۵۰")
check("و کپی ساده کمتر داشت", _plain_n < 50,
      f"cp ساده {_plain_n} ردیف"
      + (" — فایل اصلاً خوانده نشد" if _plain_n < 0 else "")
      + "؛ همین‌ها بودند که گم می‌شدند")
check("کپی سازگار فایل جانبی جا نمی‌گذارد",
      not os.path.exists(_good + "-wal"),
      "یک فایل تنها که هر جا بگذاریدش درست خوانده می‌شود")

SRC = io.open(os.path.join(ROOT, "backend", "app.py"), encoding="utf-8").read()
check("نسخه‌ی امنِ پیش از بازگردانی از همین راه گرفته می‌شود",
      "_sqlite_copy(BOT_DB, safety)" in SRC,
      "وگرنه توری که برای نجات پهن شده خودش سوراخ است")
check("و اگر گرفته نشد، لاگ می‌شود",
      "نسخه‌ی امنِ پیش از بازگردانی گرفته نشد" in SRC,
      "قبلاً بی‌صدا None می‌شد و بازگردانی جلو می‌رفت")
check("بازگردانی یکجا انجام می‌شود",
      "BEGIN IMMEDIATE" in SRC and "con.rollback()" in SRC,
      "خالی‌کردن همه‌ی جدول‌ها و بعد شکستن، بدترین حالت است")

CLI = io.open(os.path.join(ROOT, "nexora-cli.sh"), encoding="utf-8").read()
check("اسنپ‌شات هم از .backup استفاده می‌کند",
      ".backup '$SNAP_DEST/$db'" in CLI)
check("و اگر sqlite3 نبود، ‎-wal را همراه می‌برد",
      '"$SRC-wal"' in CLI)
check("بازگردانی ‎-wal کهنه‌ی مقصد را برمی‌دارد",
      'rm -f "$INSTALL_DIR/data/$RDB-wal"' in CLI,
      "گذاشتن فایل تازه کنار WAL قدیمی می‌تواند خرابش کند")
check("و tunnels.db هم برمی‌گردد", "restore_db tunnels.db" in CLI,
      "در اسنپ‌شات بود ولی در بازگردانی نبود")


# ═══════════════════════════════════════════════════════════
head("سرویس باید پیش از جابه‌جایی فایلش بایستد")

# ربات درست متوقف می‌شد، پنل نه — در حالی که billing.db و tunnels.db
# را همان پنل باز نگه داشته است.
#
# کپی‌کردن روی دیتابیسی که یک پروسه‌ی زنده بازش دارد، با WALش و
# صفحه‌های کش‌شده‌اش، همان کاری است که SQLite صریح می‌گوید نکنید. و
# پنجره‌اش کوتاه نبود: بازسازی فرانت‌اند بین بازگردانی و ری‌استارت
# چند دقیقه طول می‌کشد.

_roll = CLI[CLI.index("\n  rollback)"):]
_roll = _roll[:_roll.index("\n  snapshots)")]

_first_restore = _roll.find("restore_db bot.db")
if _first_restore < 0:
    _first_restore = _roll.find("restore_db billing.db")
_before = _roll[:_first_restore] if _first_restore > 0 else ""

check("بخش rollback پیدا شد", _first_restore > 0, f"{len(_roll)} کاراکتر")
check("ربات پیش از بازگردانی متوقف می‌شود",
      "systemctl stop nexora-bot" in _before)
check("پنل هم پیش از بازگردانی متوقف می‌شود",
      "systemctl stop $SERVICE" in _before,
      "billing.db و tunnels.db را پنل باز نگه داشته")

# و باید در هر مسیر خروجی دوباره بالا بیاید
check("مسیر بازگرداندن سرویس‌ها تعریف شده",
      "roll_bring_up()" in _roll and "trap roll_bring_up EXIT" in _roll,
      "بین بازگردانی و ری‌استارت دو مسیر exit هست")
check("و بعد از ری‌استارت موفق غیرفعال می‌شود",
      'ROLL_DOWN=""' in _roll,
      "وگرنه trap دوباره سرویسی را استارت می‌کند که تازه ری‌استارت شده")

# ترتیب: توقف، بعد بازگردانی، بعد ری‌استارت
_stop = _roll.find("systemctl stop $SERVICE")
_restart = _roll.find("systemctl restart $SERVICE")
check("ترتیب درست است — توقف، بازگردانی، ری‌استارت",
      0 < _stop < _first_restore < _restart,
      f"stop@{_stop} restore@{_first_restore} restart@{_restart}")

head("بازگردانی داخل پنل قفل می‌گیرد، فایل را جابه‌جا نمی‌کند")

# فرق دارد با rollback: این یکی داخلِ همان پروسه اجرا می‌شود و ربات
# ممکن است هم‌زمان بنویسد. BEGIN IMMEDIATE قفل نوشتن می‌گیرد، پس
# بدترین حالت SQLITE_BUSY است نه خرابیِ فایل.
check("بازگردانی ربات تراکنش صریح دارد",
      'con.execute("BEGIN IMMEDIATE")' in SRC,
      "بدون آن، نیمی از داده رفته و نیمی برنگشته")
check("و پیش از آن نسخه‌ی امن می‌گیرد",
      "bot-before-restore-" in SRC)
check("بازگردانی حسابداری هم نسخه‌ی امن می‌گیرد",
      "billing-before-restore-" in SRC)
check("ردیفی که درج نشد گزارش می‌شود",
      '"skipped"' in SRC and '"warning"' in SRC,
      "«ok: true» با نیمی از ردیف‌ها، بدترین جواب ممکن است")


print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
