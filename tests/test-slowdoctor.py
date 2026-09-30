#!/usr/bin/env python3
"""
سلامت scripts/slow-doctor.sh.

چرا وجود دارد:
    اسکریپت تابعی به نام head تعریف کرده بود. در شل، تابع همنامِ یک
    دستور استاندارد آن را سایه می‌اندازد — پس هر `| head -8` در واقع
    همان تابع را با «-8» به‌عنوان عنوان صدا می‌زد و به‌جای هشت خط
    اول، یک خط جداکننده چاپ می‌کرد.

    نتیجه این بود که در گزارش سرور مشتری، فهرست پردازه‌ها، پرمصرف‌ترین
    آی‌پی‌ها و بخش Xray همگی خط تزئینی و عدد «-8» نشان می‌دادند. هیچ
    خطایی هم داده نمی‌شد؛ فقط خروجی بی‌معنا بود.

اجرا:  python3 tests/test-slowdoctor.py
"""
import io
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(ROOT, "scripts/slow-doctor.sh")
SRC = io.open(SH, encoding="utf-8").read()

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


# ═══════════════════════════════════════════════════════════
head("هیچ تابعی دستور استاندارد را سایه نیندازد")

#: دستورهایی که اسکریپت واقعاً در لوله استفاده می‌کند
COREUTILS = {"head", "tail", "sort", "uniq", "grep", "awk", "sed", "cut",
             "wc", "tr", "cat", "printf", "echo", "date", "test", "ls",
             "find", "read", "seq", "df", "free", "ps", "kill", "time"}

funcs = set(re.findall(r"^([a-zA-Z_][\w-]*)\(\)\s*\{", SRC, re.M))
clash = funcs & COREUTILS
check("هیچ نام تابعی با دستور استاندارد یکی نیست", not clash,
      f"تداخل: {sorted(clash)}" if clash else f"{len(funcs)} تابع")

check("تابع تیتر اسمش section است", "section()" in SRC)
check("همه‌ی تیترها از section استفاده می‌کنند",
      len(re.findall(r"^section \"", SRC, re.M)) >= 8,
      f"{len(re.findall(chr(94) + 'section ' + chr(34), SRC, re.M))} تیتر")
check("هیچ صدازدن head به‌عنوان تیتر نمانده",
      not re.search(r'^head "', SRC, re.M))
check("لوله‌های head دست‌نخورده‌اند", SRC.count("| head -") >= 6,
      f"{SRC.count('| head -')} مورد")

head("نحو")

bash = shutil.which("bash")
if bash:
    p = subprocess.run([bash, "-n", SH], capture_output=True, text=True)
    check("bash -n بدون خطا", p.returncode == 0,
          (p.stderr or "").strip()[:70])
else:
    check("bash در دسترس است", False, "رد شد")

head("مقایسه با پنل x-ui")

check("دیتابیس x-ui را در چند مسیر می‌گردد",
      SRC.count("x-ui.db") >= 3)
check("تعداد کلاینت‌های x-ui را می‌شمارد",
      "client_traffics" in SRC)
check("کلاینت‌های فعال را جدا می‌شمارد", "WHERE enable=1" in SRC)
check("کلاینت‌های بدون کانال را گزارش می‌دهد",
      "not accounted for by any channel" in SRC,
      "نه هر کلاینتی که ربات نفروخته — واسطه هم می‌فروشد")
check("سنگین‌ترین کلاینت‌ها را نشان می‌دهد",
      "ORDER BY (up+down) DESC" in SRC)
check("نبود دیتابیس x-ui خطا نمی‌دهد",
      "x-ui database not found" in SRC)
check("نبود sqlite3 هم بی‌خطر است",
      "command -v sqlite3" in SRC)

head("خروجی انگلیسی می‌ماند")

# متن فارسی داخل printf با جهت‌دهی ترمینال تداخل می‌کند و آدرس‌ها را
# به‌هم می‌ریزد — همان چیزی که یک بار اتفاق افتاد.
persian_in_output = re.findall(r'^\s*(?:echo|printf|ok|warn|bad|info)\s+.*'
                               r'[؀-ۿ]', SRC, re.M)
check("هیچ متن فارسی در خروجی نیست", not persian_in_output,
      f"{len(persian_in_output)} خط" if persian_in_output else "")

head("تحلیل اتصال‌ها")

check("از $NF استفاده می‌کند نه ستون ثابت", "$NF" in SRC,
      "جای ستون بین نسخه‌های ss فرق می‌کند")
# آدرس داخل الگوی grep است، پس نقطه‌هایش escape شده‌اند: 127\.0\.0\.1
check("لوپ‌بک کنار گذاشته می‌شود",
      re.search(r"127\\\.0\\\.0\\\.1", SRC) is not None,
      "در همان grep -vE که آدرس‌های بی‌معنا را می‌اندازد")
check("اتصال به ازای هر کلاینت را حساب می‌کند",
      "connections per active client" in SRC)
check("تقسیم بر صفر محافظت شده",
      re.search(r'\[ "\$\{ACTIVE:-0\}" -gt 0 \]', SRC) is not None)

head("واسطه‌ها هم یک کانال فروش‌اند")

# ربات تنها کانال نیست. تقسیم ۲۲۵۰ اتصال بر ۶ اشتراکِ ربات عددی
# ترسناک می‌ساخت که هیچ معنایی نداشت، چون کلاینت واسطه‌ها شمرده نمی‌شد.
check("مخرج همه‌ی کلاینت‌های فعال است، نه فقط ربات",
      "FROM client_traffics WHERE enable=1" in SRC
      and "clients across all channels" in SRC)
check("اگر x-ui خوانده نشد، صریح می‌گوید مبنا چیست",
      "bot subscriptions only" in SRC)
check("تفکیک بر اساس گروه واسطه دارد",
      "Clients per reseller group" in SRC)
check("کلاینت گروه‌دار را «ناشناخته» حساب نمی‌کند",
      "belong to a reseller group" in SRC)
check("فقط بدون‌گروه‌ها را هشدار می‌دهد",
      "no reseller group and were not sold by the bot" in SRC)
check("نسخه‌ی بدون ستون گروه بی‌خطر است",
      "has no group column" in SRC)
check("ترافیک پخش‌شده را از کانفیگ اشتراکی جدا می‌کند",
      "spread evenly means simply many real users" in SRC)

print(f"\n{D}{'─' * 46}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
