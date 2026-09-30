#!/usr/bin/env python3
"""
تست ابزار پرداختِ پاداش‌های معرفِ جامانده.

چرا وجود دارد:
    این ابزار سکه می‌دهد، و سکه تخفیف است — یعنی پول. یک شرطِ کمی
    گشاد یعنی کسی که استحقاقش را ندارد پاداش بگیرد، و یک شرطِ کمی
    تنگ یعنی طلبِ واقعی پرداخت نشود.

    پس دیتابیسی ساخته می‌شود با هر پنج حالتی که ممکن است پیش بیاید:
    یکی که واقعاً طلبکار است، و چهار تا که به دلایل مختلف نیستند.

اجرا:  python3 tests/test-repair-referrals.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = str(ROOT / "scripts" / "repair-referrals.py")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bot"))

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


tmpdir = tempfile.mkdtemp()
DBP = os.path.join(tmpdir, "bot.db")
os.environ["BOT_DB_PATH"] = DBP

import db as botdb                                     # noqa: E402

botdb.DB_PATH = Path(DBP)
botdb.init_db()
TID = botdb.create_tenant("نکسورا", bot_token="1:T", owner_tg_id=999)
botdb.save_tenant_settings(TID, {"coins": {"per_referral": 10}})
D_ = botdb.TenantDB(TID)

D_.exec("""INSERT INTO plans (id,tenant_id,name,price,gb,days,is_trial)
           VALUES (501,?,'۳۰ گیگ',200000,30,30,0)""", (TID,))
D_.exec("""INSERT INTO plans (id,tenant_id,name,price,gb,days,is_trial)
           VALUES (502,?,'تست رایگان',0,1,1,1)""", (TID,))

INV = D_.create_user(100, None, "معرف")
UA = D_.create_user(101, None, "الف")   # با کیف پول خرید، معرفش نگرفت
UB = D_.create_user(102, None, "ب")     # فقط تست گرفت
UC = D_.create_user(103, None, "ج")     # خرید و پاداشش قبلا داده شده
UD = D_.create_user(104, None, "د")     # اصلا معرفی ندارد
UE = D_.create_user(105, None, "ه")     # سفارشش رد شده
for u in (UA, UB, UC, UE):
    D_.exec("UPDATE users SET referred_by=? WHERE id=?", (INV["id"], u["id"]))


def order(uid, plan_id, status="approved"):
    return D_.exec("INSERT INTO orders (tenant_id,user_id,plan_id,amount,"
                   "base_amount,status) VALUES (?,?,?,0,0,?)",
                   (TID, uid, plan_id, status))


OA = order(UA["id"], 501)
order(UB["id"], 502)                     # فقط تست
OC = order(UC["id"], 501)
order(UD["id"], 501)
order(UE["id"], 501, "rejected")
D_.reward_referral(INV["id"], UC["id"], 10, "قبلا پرداخت شده", order_id=OC)

ENV = dict(os.environ, BOT_DB_PATH=DBP, PYTHONIOENCODING="utf-8")


def run(*args):
    r = subprocess.run([sys.executable, TOOL, *args], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def coins():
    return D_.get_user(100)["coins"]


# ═══════════════════════════════════════════════════════════
head("بدون --apply هیچ سکه‌ای جابه‌جا نمی‌شود")

check("پاداشِ ج از قبل پرداخت شده", coins() == 10, f"{coins()} سکه")
rc, out = run()
check("اجرا بدون خطا", rc == 0, f"rc={rc}")
check("هیچ سکه‌ای اضافه نشد", coins() == 10, f"{coins()} سکه")
check("و می‌گوید چیزی ننوشته", "Nothing written" in out)
check("و هشدار می‌دهد که سکه ارزش واقعی است",
      "gives away real value" in out,
      "این تصمیم باید با صاحب سیستم باشد")
check("فقط یک نفر طلبکار است", "would pay: 1 person" in out,
      "فقط الف — بقیه هرکدام دلیلی دارند")
check("و آن یک نفر الف است", "الف" in out)

# ═══════════════════════════════════════════════════════════
head("با --apply فقط طلبِ واقعی پرداخت می‌شود")

rc, out = run("--apply")
check("اجرا بدون خطا", rc == 0, f"rc={rc}")
check("معرف ۱۰ سکه‌ی تازه گرفت", coins() == 20, f"{coins()} سکه")
check("و گزارش هم همین را می‌گوید", "paid: 1 person, 10 coins" in out, out[-200:])

_txs = D_.q("SELECT * FROM coin_tx WHERE tenant_id=? AND kind='referral' "
            "ORDER BY id", (TID,))
check("دو تراکنش پاداش هست، نه بیشتر", len(_txs) == 2, str(len(_txs)))
_for = {t["ref_user_id"] for t in _txs}
check("یکی برای ج و یکی برای الف", _for == {UA["id"], UC["id"]}, str(_for))
check("پاداشِ الف به سفارشش گره خورده",
      any(t["ref_user_id"] == UA["id"] and t["order_id"] == OA for t in _txs),
      "بدون order_id در دفتر پیدا نمی‌شود")

check("کسی که فقط تست گرفت پاداشی نساخت", UB["id"] not in _for,
      "تست رایگان خرید نیست")
check("کسی که معرفی نداشت هم نه", UD["id"] not in _for)
check("و سفارشِ ردشده هم پاداش ندارد", UE["id"] not in _for)

# ═══════════════════════════════════════════════════════════
head("اجرای دوباره بی‌اثر است")

rc, out = run("--apply")
check("اجرا بدون خطا", rc == 0, f"rc={rc}")
check("سکه‌ها دست نخوردند", coins() == 20, f"{coins()} سکه")
check("و می‌گوید کسی طلبکار نیست", "Nobody is owed" in out)

# ═══════════════════════════════════════════════════════════
head("نرخ صفر یعنی چیزی پرداخت نمی‌شود")

UF = D_.create_user(106, None, "و")
D_.exec("UPDATE users SET referred_by=? WHERE id=?", (INV["id"], UF["id"]))
order(UF["id"], 501)
botdb.save_tenant_settings(TID, {"coins": {"per_referral": 0}})
rc, out = run("--apply")
check("اجرا بدون خطا", rc == 0, f"rc={rc}")
check("سکه‌ای داده نشد", coins() == 20, f"{coins()} سکه")
check("و دلیلش گفته می‌شود", "referral rate is 0" in out,
      "سکوت این‌جا یعنی مدیر فکر کند پرداخت شده")
botdb.save_tenant_settings(TID, {"coins": {"per_referral": 10}})

# ═══════════════════════════════════════════════════════════
head("دستور در nexora-cli.sh درست وصل شده")

import io                                              # noqa: E402

CLI = io.open(str(ROOT / "nexora-cli.sh"), encoding="utf-8").read()
_blk = CLI[CLI.index("  repair-referrals)"):]
_blk = _blk[:_blk.index("\n    ;;")]
_code = "\n".join(l for l in _blk.split("\n")
                  if not l.strip().startswith("#"))

check("شاخه‌ی repair-referrals وجود دارد", "repair-referrals)" in CLI)
check("shift دارد", "shift" in _code,
      "بدون آن، نامِ خودِ دستور به argparse می‌رسد و رد می‌شود")
check("مسیر دیتابیس ربات را می‌دهد", "BOT_DB_PATH=" in _code)
check("آرگومان‌ها را رد می‌کند", '"$@"' in _code,
      "وگرنه --apply هیچ‌وقت نمی‌رسد")
check("در فهرست راهنما آمده", "nexora repair-referrals" in CLI)

shutil.rmtree(tmpdir, ignore_errors=True)

print(f"\n{D}{'─' * 46}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}  |  {D}{_fail} ناموفق{X}")
print()
sys.exit(1 if _fail else 0)
