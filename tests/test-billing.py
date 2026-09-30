#!/usr/bin/env python3
"""
تست ریاضیات حسابداری.

چرا وجود دارد:
    گزارش شد «با اینکه نرخ تعیین کرده‌ام، بعضی ردیف‌ها بدون نرخ
    می‌آیند». علتش این بود که وقتی حجم کانفیگ از همه‌ی نرخ‌های
    تعریف‌شده بزرگ‌تر بود، هیچ نرخی انتخاب نمی‌شد و آن ردیف *صفر*
    حساب می‌شد — یعنی پول از دست رفته، بی‌سروصدا.

اجرا:  python3 tests/test-billing.py
"""
import io
import os
import re
import sys

G, R, D, X = "\033[38;5;42m", "\033[38;5;203m", "\033[38;5;245m", "\033[0m"
_ok = _fail = 0

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(ROOT, "backend", "app.py"), encoding="utf-8").read()

# فقط همین دو تابع را برمی‌داریم تا کل app.py با وابستگی‌هایش لازم
# نشود. _price_for حالا کارش را به _price_with_reason می‌سپارد، پس
# هر دو باید بیایند — وگرنه تست با NameError می‌افتد و دلیلش هیچ
# ربطی به قیمت‌گذاری ندارد.
# The pricing core by name (ast), not by a regex up to the next route: the
# routes that followed it moved to backend/pro/accounting.py, and a regex
# would then swallow whatever comes next.
import ast as _ast
_T = _ast.parse(SRC)
_ns = {}
_want = ("_match_rate", "_device_rate", "_line_amount", "_price_with_reason", "_price_for")
for _n in _T.body:
    if isinstance(_n, _ast.FunctionDef) and _n.name in _want:
        exec(_ast.get_source_segment(SRC, _n), _ns)
_missing = [w for w in _want if w not in _ns]
if _missing:
    print(f"{R}not found in backend/app.py: {', '.join(_missing)}{X}")
    sys.exit(1)
price_for = _ns["_price_for"]
price_with_reason = _ns["_price_with_reason"]
line_amount = _ns.get("_line_amount")


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


RATES = [{"gb": 30, "price": 90_000},
         {"gb": 50, "price": 120_000},
         {"gb": 100, "price": 190_000}]

head("انتخاب نرخ")
check("تطابق دقیق حجم", price_for(50, RATES) == 120_000,
      str(price_for(50, RATES)))
check("حجم بین دو نرخ، بالاتر را می‌گیرد", price_for(40, RATES) == 120_000,
      str(price_for(40, RATES)))
check("حجم کمتر از همه، کوچک‌ترین نرخ", price_for(10, RATES) == 90_000,
      str(price_for(10, RATES)))

# باگ اصلی: قبلاً None برمی‌گشت و ردیف صفر حساب می‌شد
check("حجم بزرگ‌تر از همه‌ی نرخ‌ها، بالاترین نرخ را می‌گیرد",
      price_for(200, RATES) == 190_000, str(price_for(200, RATES)))
check("حجم خیلی بزرگ هم صفر نمی‌شود",
      price_for(5000, RATES) is not None, str(price_for(5000, RATES)))

head("نامحدود")
# قاعده عوض شد. قبلاً نامحدودِ بدون نرخِ نامحدود صفر حساب می‌شد، و
# روی سرور واقعی این یعنی ۱۰۰ کانفیگ از ۲۵۷ تا بی‌قیمت می‌ماندند.
# وقتی مدیر برای یک گروه نرخ گذاشته، منظورش این است که این گروه قیمت
# دارد؛ «چون دقیقاً جور در نمی‌آید پس صفر» جوابِ غلطی است.
check("نامحدود با فقط نرخ حجمی، گران‌ترین پله را می‌گیرد",
      price_for(0, RATES) == 190_000, str(price_for(0, RATES)))
check("و دیگر صفر نمی‌شود", price_for(0, RATES) is not None,
      "همان قاعده‌ای که برای کانفیگِ بزرگ‌تر از همه‌ی پله‌ها به کار می‌رود")

UNL = RATES + [{"gb": 0, "price": 250_000}]
check("نامحدود با نرخ نامحدود", price_for(0, UNL) == 250_000,
      str(price_for(0, UNL)))
check("وجود نرخ نامحدود، انتخاب حجمی را خراب نمی‌کند",
      price_for(50, UNL) == 120_000, str(price_for(50, UNL)))

head("ورودی خراب")
check("لیست خالی", price_for(50, []) is None)
check("None", price_for(50, None) is None)
check("نرخ با مقدار غیرعددی نادیده گرفته می‌شود",
      price_for(50, [{"gb": "خراب", "price": "x"}, {"gb": 50, "price": 120_000}])
      == 120_000)
check("همه‌ی نرخ‌ها خراب", price_for(50, [{"gb": "x", "price": "y"}]) is None)

print(f"\n{D}{'─' * 46}{X}")
# ═══════════════════════════════════════════════════════════
head("«بدون نرخ» باید بگوید چرا")

# پنج علت مختلف به «بدون نرخ» ختم می‌شوند و هیچ‌کدام از خودِ عبارت
# پیدا نیست. مدیری که نرخ تعریف کرده و باز هم «بدون نرخ» می‌بیند،
# هیچ راهی ندارد بفهمد کدام‌یک است — و همین چند بار به‌عنوان
# «حسابداری کار نمی‌کند» برگشته.

_p, _w = price_with_reason(0, [])
check("گروه بدون نرخ", _p is None and "هیچ نرخی تعریف نشده" in _w, _w)

_p, _w = price_with_reason(0, [{"gb": 50, "price": 120_000}])
check("کانفیگ نامحدود، نرخ حجمی را می‌گیرد", _p == 120_000 and _w is None,
      "نامحدود دست‌کم به اندازه‌ی بزرگ‌ترین پله است")

_p, _w = price_with_reason(50, [{"gb": 0, "price": 190_000}])
check("کانفیگ حجمی، نرخِ تنهای گروه را می‌گیرد",
      _p == 190_000 and _w is None,
      "گروه «unlimited» با ۸۸ کانفیگِ ۲۰۰ گیگی — همین حالت بود")

_p, _w = price_with_reason(200, [{"gb": 0, "price": 190_000}])
check("و حجم بزرگ هم همین‌طور", _p == 190_000 and _w is None)

_p, _w = price_with_reason(0, [{"gb": 0, "price": 190_000}])
check("نامحدود با نرخ نامحدود قیمت می‌گیرد", _p == 190_000 and _w is None)

_p, _w = price_with_reason(50, [{"gb": 50, "price": 120_000}])
check("تطابق دقیق هنوز کار می‌کند", _p == 120_000 and _w is None)

_p, _w = price_with_reason(40, [{"gb": 30, "price": 90_000},
                                {"gb": 50, "price": 120_000}])
check("نزدیک‌ترین بالاتر هنوز کار می‌کند", _p == 120_000 and _w is None)

_p, _w = price_with_reason(200, [{"gb": 30, "price": 90_000},
                                 {"gb": 50, "price": 120_000}])
check("بزرگ‌تر از همه، بالاترین نرخ را می‌گیرد", _p == 120_000 and _w is None,
      "صفر گرفتن از یک کانفیگ واقعی بدتر از تقریب است")

_p, _w = price_with_reason(50, [{"gb": None, "price": None}])
check("ردیف خراب، دلیلِ روشن می‌دهد",
      _p is None and "خوانده نشدند" in _w, _w)

# ═══════════════════════════════════════════════════════════
head("نرخ هر کاربر اضافه")

# کانفیگ چهارکاربره همان نرخ کانفیگ تک‌کاربره را می‌گرفت، در حالی که
# سه کاربر بیشتر روی سرور می‌نشیند. هر پله‌ی نرخ حالا نرخ کاربر خودش
# را دارد.

if not line_amount:
    check("_line_amount از app.py برداشته شد", False, "regex نخورد")
else:
    R1 = [{"gb": 0, "price": 190_000, "perDevice": 50_000}]

    amt, base, per, extra = line_amount(0, R1, 1, 4)
    check("کانفیگ چهارکاربره سه کاربر اضافه دارد", extra == 3, str(extra))
    check("و مبلغش پایه + سه برابر نرخ کاربر است", amt == 340_000, str(amt))
    check("نرخ پایه جدا گزارش می‌شود", base == 190_000 and per == 50_000)

    amt, _b, _p, extra = line_amount(0, R1, 1, 1)
    check("کانفیگ تک‌کاربره فقط نرخ پایه می‌گیرد", amt == 190_000, str(amt))
    check("و کاربر اضافه ندارد", extra == 0)

    amt, _b, _p, _e = line_amount(0, R1, 3, 4)
    check("سه ماه، سه برابر می‌شود", amt == 1_020_000, str(amt))

    amt, _b, _p, extra = line_amount(0, R1, 1, 0)
    check("دستگاه نامحدود فقط نرخ پایه می‌گیرد", amt == 190_000,
          "شمردنی نیست، پس چیزی اضافه نمی‌شود")
    check("و کاربر اضافه‌اش صفر است", extra == 0)

    # بدون نرخ کاربر، هیچ چیز عوض نمی‌شود
    R0 = [{"gb": 0, "price": 190_000}]
    amt, _b, per, _e = line_amount(0, R0, 2, 4)
    check("نرخ کاربر که تعریف نشده باشد، فاکتور عوض نمی‌شود",
          amt == 380_000 and per == 0,
          "فاکتورهای قبلی باید دقیقاً همان بمانند")

    # هر پله نرخ کاربر خودش را دارد
    R2 = [{"gb": 30, "price": 180_000, "perDevice": 20_000},
          {"gb": 50, "price": 230_000, "perDevice": 60_000}]
    amt30, _b, p30, _e = line_amount(30, R2, 1, 3)
    amt50, _b, p50, _e = line_amount(50, R2, 1, 3)
    check("پله‌ی ۳۰ گیگ نرخ کاربر خودش را دارد",
          p30 == 20_000 and amt30 == 220_000, f"{amt30}")
    check("و پله‌ی ۵۰ گیگ نرخ دیگری", p50 == 60_000 and amt50 == 350_000,
          f"{amt50}")

    # کانفیگ بی‌نرخ همچنان صفر
    amt, base, _p, _e = line_amount(50, [], 1, 4)
    check("کانفیگ بدون نرخ هنوز صفر است", amt == 0 and base is None)

JD = io.open(os.path.join(ROOT, "frontend", "src", "ui", "jalali.jsx"),
             encoding="utf-8").read()
check("تقویم از راه portal روی body می‌نشیند",
      "createPortal(" in JD and "document.body)" in JD,
      "هر والدی که transform داشته باشد، position:fixed را در خودش "
      "حبس می‌کند — و .fx-anim دقیقاً همین را دارد")
check("و کلیک روی خودِ تقویم نمی‌بنددش",
      "panel.current.contains(e.target)" in JD,
      "با portal دیگر فرزندِ box نیست")
check("تقویم از کادر والد بیرون می‌زند", 'position: "fixed"' in JD,
      "قبلاً نصفش زیر لبه‌ی کارت می‌رفت و دست‌نیافتنی بود")
check("و اگر پایین جا نباشد رو به بالا باز می‌شود", "const up =" in JD)


head("Pricing-core rules that stay in the core")

APP = io.open(os.path.join(ROOT, "backend", "app.py"), encoding="utf-8").read()
check("مبدأ صورتحساب یک قاعده‌ی مشترک دارد", "def _bill_since(" in APP,
      "تسویه‌شده تا، بعد شروع همکاری — نه هر جا یک تصمیم جدا")
check("شمارش تمدید و تاریخ‌گذاری‌اش یک مبدأ دارند",
      "def _start_ms(" in APP and "created, source = _start_ms(" in APP)
check("تعداد تمدیدها از _months_for می‌آید",
      "def _renewal_dates(cl, logged_rows, months=None" in APP,
      "قبلاً هر کدام مستقل می‌شمردند و دو عدد می‌دادند")
check("تمدید چندماهه چند ماه حساب می‌شود",
      'real.extend([(d, "قطعی")] * n)' in APP,
      "تمدید سه‌ماهه سه ماه صورتحساب است، نه یکی")



if __name__ == "__main__":
    color = G if not _fail else R
    print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
    print()
    sys.exit(1 if _fail else 0)
