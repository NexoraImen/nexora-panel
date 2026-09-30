#!/usr/bin/env python3
"""
هر دکمه‌ی ربات باید هندلر داشته باشد.

چرا وجود دارد:
    دکمه‌ی «تمدید» ساخته می‌شد، کاربر می‌زد، و هیچ اتفاقی نمی‌افتاد.
    نه پیامی، نه خطایی در لاگ — callback بی‌صدا به انتهای dispatch
    می‌رسید و None برمی‌گرداند. تصادفی پیدا شد.

    این تست همان را سیستماتیک می‌کند: هر callback_data که ربات تولید
    می‌کند باید یا در _SIMPLE باشد، یا شاخه‌ی action داشته باشد. اگر
    دکمه‌ی جدیدی بدون هندلر اضافه شود، این‌جا قرمز می‌شود — نه در
    دست مشتری.

اجرا:  python3 tests/test-bot-buttons.py
"""
import ast
import io
import os
import re
import sys

G, R, D, X = "\033[38;5;42m", "\033[38;5;203m", "\033[38;5;245m", "\033[0m"
_ok = _fail = 0

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(ROOT, "bot", "handlers.py"), encoding="utf-8").read()
TREE = ast.parse(SRC)


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


# ═══════════ استخراج دکمه‌ها از AST ═══════════
#
# دکمه‌ها به kb() می‌رسند به شکل [[(متن، داده)], ...] یا
# [[(متن، داده، "url"|"copy")], ...]. فقط تاپل‌های دوتایی و آن‌هایی
# که نوعشان url/copy نیست، callback هستند.

def _const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # f-string: فقط بخش ثابت ابتدایی مهم است ("renew:{id}" → "renew")
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                break
        return "".join(parts) if parts else None
    return None


# فقط تاپل‌هایی که واقعاً به kb() می‌رسند.
#
# هر تاپل دوتایی از رشته شبیه دکمه است — از جمله
# ("group", "supergroup") در یک مقایسه یا مقدار یک dict. شمردن آن‌ها
# گزارش را پر از هشدار دروغ می‌کرد، و گزارشی که دروغ می‌گوید بدتر
# از نبودنش است. پس دامنه را به آرگومان‌های kb محدود می‌کنیم.
def _kb_tuples(tree):
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if name != "kb":
            continue
        for arg in node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Tuple):
                    out.append(sub)
    return out


buttons = set()
for node in _kb_tuples(TREE):
    if not (2 <= len(node.elts) <= 3):
        continue
    if len(node.elts) == 3:
        kind = _const(node.elts[2])
        if kind in ("url", "copy"):
            continue
    data = _const(node.elts[1])
    if not data:
        continue
    m = re.match(r"^([a-z][a-z_]*)(:|$)", data)
    if m:
        buttons.add(m.group(1))

# rows.append([...]) هم رایج است و از kb() بیرون می‌ماند؛ آن‌ها را
# از روی الگوی خودشان برمی‌داریم
for m in re.finditer(r'rows\.append\(\s*\[(.*?)\]\s*\)', SRC, re.S):
    for d in re.findall(r',\s*f?"([a-z][a-z_]*)(?::[^"]*)?"\s*\)', m.group(1)):
        # url و copy نوع دکمه‌اند، نه callback_data
        if d not in ("url", "copy"):
            buttons.add(d)

# ═══════════ استخراج هندلرها ═══════════

handled = set(re.findall(r'action == "([a-z_]+)"', SRC))
for grp in re.findall(r'action in \(([^)]*)\)', SRC):
    handled |= set(re.findall(r'"([a-z_]+)"', grp))

# _SIMPLE: نگاشت داده‌ی ساده به تابع
simple = set()
m = re.search(r"_SIMPLE\s*=\s*\{(.*?)\n\}", SRC, re.S)
if m:
    simple = set(re.findall(r'"([a-z_]+)"\s*:', m.group(1)))

known = handled | simple

head("پوشش دکمه‌ها")
print(f"  {D}دکمه‌های callback : {len(buttons)}{X}")
print(f"  {D}شاخه‌ی action     : {len(handled)}{X}")
print(f"  {D}در _SIMPLE        : {len(simple)}{X}")
print()

orphans = sorted(b for b in buttons if b not in known)
check("هر دکمه هندلر دارد", not orphans,
      ("بدون هندلر: " + ", ".join(orphans)) if orphans else
      f"{len(buttons)} دکمه بررسی شد")

if orphans:
    print()
    for o in orphans:
        # کجا ساخته شده
        for i, line in enumerate(SRC.splitlines(), 1):
            if re.search(rf'"{o}(:|")', line):
                print(f"      {R}{o}{X}  ← خط {i}: {line.strip()[:66]}")
                break

head("دکمه‌های حیاتی")

for b, label in [("buy", "خرید اشتراک"), ("mysubs", "اشتراک‌های من"),
                 ("renew", "تمدید"), ("wallet", "کیف پول"),
                 ("ref", "دعوت دوستان"), ("coins", "سکه‌ها"),
                 ("help", "آموزش نصب"), ("support", "پشتیبانی"),
                 ("menu", "منوی اصلی"), ("plan", "جزئیات پلن"),
                 ("chk", "تسویه"), ("ap", "تایید رسید"),
                 ("rj", "رد رسید"), ("topup", "شارژ کیف پول")]:
    check(f"«{label}» هندلر دارد", b in known, b)

head("سلامت ساختار")

check("_SIMPLE خالی نیست", len(simple) > 5, f"{len(simple)} ورودی")
# هر دو شکل — `except Exception:` و `except Exception as e:`. نسخه‌ی قبلی
# فقط اولی را می‌دید و در واقع روی catchِ *درونیِ* ارسالِ هشدار سبز می‌شد،
# نه روی catchِ بیرونی که همین بررسی قرار بود بسنجد.
check("dispatch استثنا را می‌گیرد",
      re.search(r"except Exception( as \w+)?:", SRC.split("def dispatch")[1][:900]) is not None)
check("callback نامعتبر لاگ می‌شود", "callback نامعتبر" in SRC)

# هر تابعی که به عنوان هندلر ثبت شده، باید واقعاً وجود داشته باشد
defined = {n.name for n in TREE.body if isinstance(n, ast.FunctionDef)}
refs = set(re.findall(r'return ([a-z_]+)\(ctx, user, chat_id', SRC))
missing_fn = sorted(f for f in refs if f not in defined)
check("همه‌ی توابع هندلر تعریف شده‌اند", not missing_fn, str(missing_fn))

print(f"\n{D}{'─' * 46}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
