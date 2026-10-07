#!/usr/bin/env python3
"""
درزها را می‌آزماید — جاهایی که دو نیمه‌ی کد باید با هم بخوانند.

چرا وجود دارد:
    هر باگی که در این پروژه به دست مشتری رسید، باگ منطق نبود؛ باگ
    اتصال بود. یک طرف چیزی را اعلام کرده بود و طرف دیگر خبر نداشت:

      · دکمه‌ی «تمدید» ساخته می‌شد، dispatch شاخه نداشت
      · «شارژ کیف پول» از جدول cards می‌خواند، جدولی وجود نداشت
      · firewall/suggest در بک‌اند بود، هیچ‌جای پنل صدایش نمی‌زد
      · tg.py متد action را دو بار تعریف کرده بود

    هیچ‌کدام را تست‌های معمولی نگرفتند، چون تست یک *تابع* را می‌آزماید
    و درز تابع نیست. این فایل به‌جای آزمودن رفتار، دو سمت هر درز را
    می‌شمارد و تفاضل می‌گیرد.

اجرا:  python3 tests/test-seams.py
"""
import ast
import glob
import io
import os
import re
import sys

G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")
_ok = _fail = 0

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# The Pro modules live in backend/pro/ since 2.0 (docs/specs/2026-09-29-pro-split.md).
# Checks name them by their old place; resolve() maps it, and in the Community
# tree, where they do not exist, the checks skip them instead of failing.
_MOVED = {f"backend/{m}.py": f"backend/pro/{m}.py"
          for m in ("firewall", "tunnels", "intrusion", "inbounddoc", "linkcheck")}
_MOVED["agent/nexora-agent.py"] = "backend/pro/agent/nexora-agent.py"
_MOVED["backend/fx.py"] = "backend/pro/fx.py"
_MOVED.update({f"frontend/src/sections/{m}.jsx": f"frontend/src/pro/{m}.jsx"
               for m in ("billing", "expenses", "portal-admin")})
_MOVED.update({f"frontend/src/sections/bot/{m}.jsx": f"frontend/src/pro/{m}.jsx"
               for m in ("coins", "discounts")})
_MOVED.update({f"frontend/src/portal/{f}": f"frontend/src/pro/portal/{f}"
               for f in ("index.jsx", "dash.jsx", "store.jsx", "studio.jsx", "api.js")})


def resolve(rel):
    return _MOVED.get(rel, rel)


def exists(rel):
    return os.path.exists(os.path.join(ROOT, *resolve(rel).split("/")))


def rd(*parts):
    rel = resolve("/".join(parts))
    return io.open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8").read()


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


def bullets(items, limit=12):
    """فهرست خطاها را زیر تست چاپ می‌کند تا لازم نباشد کسی بگردد."""
    for x in sorted(items)[:limit]:
        print(f"      {Y}▸{X} {x}")
    if len(items) > limit:
        print(f"      {D}… و {len(items) - limit} مورد دیگر{X}")


APP_PY = rd("backend", "app.py")
# Pro files moved verbatim out of app.py run inside its namespace
# (NAMESPACE in backend/pro/__init__.py). For every scan of "the app's routes"
# they are part of it; left out, an ungated or unauthenticated route there
# would be invisible to the very checks that exist to catch it.
_PRO_INIT = os.path.join(ROOT, "backend", "pro", "__init__.py")
_NS = (re.search(r"^NAMESPACE = \(([^)]*)\)", io.open(_PRO_INIT, encoding="utf-8").read(), re.M)
       if os.path.exists(_PRO_INIT) else None)
NS_FILES = sorted(re.findall(r'"(\w+\.py)"', _NS.group(1))) if _NS else []
# license.PRO_PATHS: which paths are Pro. In the Community tree those routes
# are absent on purpose, and a core panel call to one is not "to nowhere".
import importlib.util as _ilu_lic                              # noqa: E402
_lspec = _ilu_lic.spec_from_file_location("license_for_seams", os.path.join(ROOT, "backend", "license.py"))
LICM = _ilu_lic.module_from_spec(_lspec)
_lspec.loader.exec_module(LICM)
HAS_PRO_API = os.path.isdir(os.path.join(ROOT, "backend", "pro"))
APP_NS = APP_PY + "".join("\n" + rd("backend", "pro", f) for f in NS_FILES)
HANDLERS = rd("bot", "handlers.py")
DB_PY = rd("bot", "db.py")


def _frontend_src():
    """
    همه‌ی سورس فرانت‌اند، به هم چسبیده.

    تا وقتی پنل یک فایل ۱۱۴۰۰ خطی بود، خواندن App.jsx کافی بود. حالا
    که به ماژول شکسته شده، باید کل درخت را بخوانیم وگرنه این تست فکر
    می‌کند نصف پنل ناپدید شده.
    """
    base = os.path.join(ROOT, "frontend", "src")
    parts = []
    for dirpath, _dirs, files in os.walk(base):
        for f in sorted(files):
            if f.endswith((".jsx", ".js")):
                parts.append(io.open(os.path.join(dirpath, f),
                                     encoding="utf-8").read())
    return "\n".join(parts)


APP_JSX = _frontend_src()

print(f"\n{D}{'═' * 54}{X}")
print("  تست درزها — دو سمت هر اتصال باید با هم بخوانند")
print(f"{D}{'═' * 54}{X}")


# ═══════════════════════════════════════════════════════════
#  درز ۱ — مسیرهای بک‌اند ↔ صداکننده‌های فرانت‌اند
# ═══════════════════════════════════════════════════════════
head("درز ۱ · بک‌اند ↔ فرانت‌اند")


def _collapse(p):
    """
    ${...} را حذف می‌کند — با شمردن آکولاد، چون درون‌شان خودشان
    آکولاد و پرانتز دارند: ${encodeURIComponent(sel.name)}
    """
    out, i = [], 0
    while i < len(p):
        if p.startswith("${", i):
            depth, i = 1, i + 2
            while i < len(p) and depth:
                depth += (p[i] == "{") - (p[i] == "}")
                i += 1
            out.append(":p")
        else:
            out.append(p[i])
            i += 1
    return "".join(out)


def normalize(p):
    """
    /api/x/{id} و /api/x/${n} را به یک شکل درمی‌آورد تا قابل مقایسه شوند،
    و رشته‌ی پرس‌وجو را دور می‌ریزد چون بخشی از مسیر نیست.
    """
    p = _collapse(p).split("?")[0].rstrip("/")
    p = re.sub(r"\{[^}]*\}", ":p", p)       # {palette_id} → :p
    p = re.sub(r"(?::p){2,}", ":p", p)      # `${id}${q}` یک پارامتر است، نه دو
    return p


sys.path.insert(0, os.path.join(ROOT, "scripts"))
from route_decls import route_decls          # noqa: E402  (one reader for core and Pro routes)

routes = {normalize(path) for _m, path, _f in route_decls(ROOT)}

# فرانت‌اند از دو شکل استفاده می‌کند: تمپلیت مستقیم، و helper به نام call.
# کل بک‌تیک را برمی‌داریم، نه تا اولین پرانتز — چون ${encodeURIComponent(x)}
# داخل خودش پرانتز دارد و برش زودهنگام مسیر را ناقص می‌کند.
called = set()
for lit in re.findall(r'`([^`]*)`', APP_JSX):
    m = re.search(r'\$\{API_URL\}(/api[^\s]*)', lit)
    if m:
        called.add(normalize(m.group(1)))

# هر رشته‌ای که با /api/ شروع شود یک صدازدن است — فرقی نمی‌کند
# مستقیم در fetch باشد یا به یک helper مثل call() یا useJson() برود.
# الگوی قبلی فقط call() را می‌شناخت و وقتی useJson اضافه شد، مسیرهای
# تازه بی‌صداکننده به نظر رسیدند.
for m in re.finditer(r'[`"\'](/api/[^`"\'\s]*)', APP_JSX):
    called.add(normalize(m.group(1)))

check("مسیرهای بک‌اند استخراج شدند", len(routes) > 50, f"{len(routes)} مسیر")
check("صداکننده‌های فرانت‌اند استخراج شدند", len(called) > 40,
      f"{len(called)} صدازدن")

# فرانت‌اند مسیری را صدا بزند که وجود ندارد = ۴۰۴ در دست مشتری
ghost = called - routes - {"/api"}
if not HAS_PRO_API:
    ghost = {g for g in ghost if LICM.pro_feature_of(g) is None}
check("هر صدازدن فرانت‌اند مسیر واقعی دارد", not ghost,
      f"{len(ghost)} مسیر ناموجود" if ghost else "")
if ghost:
    bullets(ghost)

# مسیری که هیچ‌کس صدا نمی‌زند = کد مرده (باگ «پیشنهاد قواعد فایروال»)
# مسیرهای عمومی و مسیرهای ایجنت را مستثنا می‌کنیم: صداکننده‌شان مرورگر،
# صفحه‌ی اشتراک، یا اسکریپت ایجنت روی سرور دیگر است — نه App.jsx.
PUBLIC = ("/api/public", "/api/sub", "/api/health", "/api/docs",
          "/api/openapi", "/api/agent", "/api/sms")

#: مسیرهایی که می‌دانیم صداکننده ندارند و دلیلش را نوشته‌ایم.
#: این فهرست عمداً کوتاه است — هر ورودی یک بدهی است، نه یک استثنا.
#: مسیر تازه‌ای که این‌جا نباشد، تست را قرمز می‌کند.
KNOWN_ORPHANS = {
    "/api/admin/reset-defaults":
        "کل تنظیمات را بدون تأیید به پیش‌فرض برمی‌گرداند — بهتر است حذف شود",
    "/api/admin/billing/payments/:p":
        "پنل پرداخت ثبت می‌کند ولی دکمه‌ی حذف ندارد",
    "/api/admin/health/local":
        "سلامت سرور خود پنل — پنل فقط سرورهای دیگر را نشان می‌دهد",
}

#: Core routes whose only screen is Pro, so in the Community tree nothing calls
#: them. Each is a gap in the free panel, written down rather than hidden.
COMMUNITY_ORPHANS = {
    "/api/admin/bot/brand":
        "the shop's brand is set from the theme studio (Pro: pro/portal/studio.jsx)",
    "/api/admin/bot/logo":
        "the shop's logo, same studio",
}

orphan = {r for r in routes - called if not r.startswith(PUBLIC)}
new_orphans = orphan - set(KNOWN_ORPHANS)
if not HAS_PRO_API:
    new_orphans -= set(COMMUNITY_ORPHANS)
check("مسیر بی‌صداکننده‌ی تازه‌ای اضافه نشده", not new_orphans,
      f"{len(new_orphans)} مسیر تازه" if new_orphans
      else f"{len(orphan)} بدهی شناخته‌شده")
if new_orphans:
    bullets(new_orphans)

# بدهی‌های شناخته‌شده هشدارند، نه شکست — ولی دیده می‌شوند
still = orphan & set(KNOWN_ORPHANS)
if still:
    print(f"    {D}بدهی‌های باز:{X}")
    for r in sorted(still):
        print(f"      {Y}▸{X} {r} {D}— {KNOWN_ORPHANS[r]}{X}")

# اگر بدهی‌ای وصل شد، باید از فهرست پاک شود وگرنه فهرست بی‌معنا می‌شود
stale = set(KNOWN_ORPHANS) - orphan
# A known orphan on a Pro path is absent from the Community tree, not "fixed".
if not HAS_PRO_API:
    stale = {r for r in stale if not LICM.pro_feature_of(r)}
check("فهرست بدهی‌ها به‌روز است", not stale,
      f"{len(stale)} مورد دیگر بدهی نیست" if stale else "")
if stale:
    bullets(stale)


# ═══════════════════════════════════════════════════════════
#  درز ۲ — جدول‌هایی که ربات کوئری می‌زند ↔ اسکیمای واقعی
# ═══════════════════════════════════════════════════════════
head("درز ۲ · کوئری‌های ربات ↔ اسکیمای دیتابیس")

BOT_DIR = os.path.join(ROOT, "bot")
bot_sources = {f: rd("bot", f) for f in sorted(os.listdir(BOT_DIR))
               if f.endswith(".py") and not f.startswith("test_")}

# پنل هم در دیتابیس ربات جدول می‌سازد (مثلاً bot_flags برای فرمان reload)،
# پس اسکیمای واقعی مجموع هر دو فایل است، نه فقط db.py
_CREATE = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["\']?(\w+)'
schema = {m.lower() for m in re.findall(_CREATE, DB_PY, re.I)}
schema |= {m.lower() for m in re.findall(_CREATE, APP_PY, re.I)}
check("اسکیما خوانده شد", len(schema) > 3, f"{len(schema)} جدول")

# فقط داخل رشته‌هایی که واقعاً SQL هستند می‌گردیم. اگر مستقیم روی
# متن فایل regex بزنیم، «from datetime import ...» هم جدول حساب می‌شود.
# الگو باید *شکل* SQL را ببیند، نه فقط یک کلمه‌ی کلیدی. یک داک‌استرینگ
# فارسی که در توضیحش می‌نویسد «UPDATE هیچ شرطی نداشت» وگرنه SQL حساب
# می‌شد و «هیچ» را به‌عنوان نام جدول گزارش می‌کرد.
SQL_START = re.compile(
    r'\bSELECT\b[\s\S]*\bFROM\b'
    r'|\bINSERT\s+(?:OR\s+\w+\s+)?INTO\b'
    r'|\bUPDATE\s+\w+\s+SET\b'
    r'|\bDELETE\s+FROM\b'
    r'|\bREPLACE\s+INTO\b', re.I)
queried = {}
for fname, src in bot_sources.items():
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        sql = node.value
        if not SQL_START.search(sql):
            continue
        for m in re.finditer(r'\b(?:FROM|JOIN|INTO|UPDATE)\s+["\']?(\w+)',
                             sql, re.I):
            t = m.group(1).lower()
            if t in ("select", "set", "where", "values"):
                continue
            queried.setdefault(t, set()).add(fname)

# جدول‌های موقتی/سیستمی SQLite را نادیده می‌گیریم
SYSTEM = {"sqlite_master", "sqlite_sequence", "pragma"}
missing = {t: f for t, f in queried.items()
           if t not in schema and t not in SYSTEM}

check("هر جدولی که ربات کوئری می‌زند در اسکیما هست", not missing,
      f"{len(missing)} جدول ناموجود" if missing else
      f"{len(queried)} جدول بررسی شد")
if missing:
    bullets([f"{t}  ({', '.join(sorted(f))})" for t, f in missing.items()])


# ═══════════════════════════════════════════════════════════
#  درز ۳ — کلیدهای تنظیمات: ربات می‌خواند ↔ پنل می‌نویسد
# ═══════════════════════════════════════════════════════════
head("درز ۳ · تنظیمات ربات ↔ فرم پنل")

# فقط ctx.s و self.s — نه هر s.get دیگری، چون s نام رایج ردیف اشتراک هم هست
read_keys = set()
for src in bot_sources.values():
    read_keys |= set(re.findall(r'(?:ctx|self)\.s\.get\(\s*"([a-z_]+)"', src))
    read_keys |= set(re.findall(r'(?:ctx|self)\.s\[\s*"([a-z_]+)"\s*\]', src))

check("کلیدهای تنظیمات استخراج شدند", len(read_keys) > 10,
      f"{len(read_keys)} کلید")

# کلیدی که ربات می‌خواند ولی هیچ‌جای پنل نیست، یعنی مدیر هرگز
# نمی‌تواند مقدارش را بدهد — همیشه خالی می‌ماند و بی‌صدا از کار می‌افتد.
unreachable = {k for k in read_keys if f'"{k}"' not in APP_JSX
               and f"'{k}'" not in APP_JSX and f".{k}" not in APP_JSX}
check("هر تنظیمی که ربات می‌خواند در پنل قابل تنظیم است", not unreachable,
      f"{len(unreachable)} کلید بی‌راه" if unreachable else "")
if unreachable:
    bullets(unreachable)


# ═══════════════════════════════════════════════════════════
#  درز ۴ — تعریف تکراری: دو متد هم‌نام، یکی بی‌صدا برنده
# ═══════════════════════════════════════════════════════════
head("درز ۴ · تعریف تکراری")

dupes = []
for fname, src in bot_sources.items():
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    # سطح ماژول و سطح کلاس، جدا از هم
    scopes = [("", tree.body)]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            scopes.append((node.name + ".", node.body))
    for prefix, body in scopes:
        seen = {}
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in seen:
                    dupes.append(f"{fname}: {prefix}{node.name}() "
                                 f"خط {seen[node.name]} و {node.lineno}")
                seen[node.name] = node.lineno

check("هیچ تابعی دو بار تعریف نشده", not dupes,
      f"{len(dupes)} تعریف تکراری" if dupes else
      f"{len(bot_sources)} فایل بررسی شد")
if dupes:
    bullets(dupes)


# ═══════════════════════════════════════════════════════════
#  درز ۵ — هر هندلری که ثبت شده باید وجود داشته باشد
# ═══════════════════════════════════════════════════════════
head("درز ۵ · ارجاع به توابع ناموجود")

tree = ast.parse(HANDLERS)
defined = {n.name for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
imported = set(re.findall(r'^(?:from|import)\s+(\w+)', HANDLERS, re.M))

referenced = set(re.findall(r'\breturn\s+(show_\w+|admin_\w+|cmd_\w+)\(',
                            HANDLERS))
dangling = sorted(f for f in referenced if f not in defined)
check("هر تابعی که صدا زده می‌شود تعریف شده", not dangling, str(dangling))

check("ماژول‌های لازم import شده‌اند",
      {"core", "db"} <= imported | defined,
      f"{sorted(imported)[:4]}")


# ═══════════════════════════════════════════════════════════
#  درز ۶ — آیکون استفاده‌شده ولی import‌نشده
# ═══════════════════════════════════════════════════════════
head("درز ۶ · آیکون بدون import")

# این دو بار اتفاق افتاد و هر دو بار فقط موقع اجرای واقعی پیدا شد:
# «Activity is not defined» و بعد «Power is not defined». باندل بدون
# خطا ساخته می‌شود چون esbuild نام آزاد را خطا نمی‌گیرد؛ فقط مرورگر
# موقع اجرا می‌افتد — و کل پنل سفید می‌شود.
FRONT = os.path.join(ROOT, "frontend", "src")
icon_problems = []

for dirpath, _dirs, files in os.walk(FRONT):
    for fname in files:
        if not fname.endswith((".jsx", ".js")):
            continue
        path = os.path.join(dirpath, fname)
        src = io.open(path, encoding="utf-8").read()

        imported = set()
        # `import React, { Suspense } from "react"` هم باید دیده شود:
        # الگوی قبلی فقط `import {…}` را می‌گرفت و شکلِ ترکیبی را
        # «import نشده» گزارش می‌کرد — یک هشدار دروغ.
        for im in re.finditer(r'import (?:\w+,\s*)?\{([^}]*)\} from', src):
            for chunk in im.group(1).split(","):
                chunk = chunk.strip()
                if chunk:
                    imported.add(chunk.split()[-1])
        imported |= set(re.findall(r'^import (\w+)', src, re.M))

        # هر چیزی که در همین فایل تعریف شده
        local = set(re.findall(
            r'^(?:export\s+)?(?:default\s+)?'
            r'(?:function|const|let|var|class)\s+(\w+)', src, re.M))
        # کامپوننت‌های تعریف‌شده داخل بدنه‌ی یک کامپوننت دیگر
        local |= set(re.findall(r'\bconst\s+([A-Z]\w*)\s*=', src))

        # نام‌هایی که از destructuring پارامتر می‌آیند: ({ icon: Icon })
        # اینها متغیر محلی‌اند، نه نام آزاد. بدون این، هر کامپوننتی که
        # آیکون را به‌عنوان prop می‌گیرد اشتباهاً «import‌نشده» اعلام
        # می‌شد — و تست به‌خاطر خودش قرمز می‌ماند.
        for params in re.findall(r'(?:function\s+\w+|=>|\()\s*\(?\{([^}]*)\}',
                                 src):
            local |= set(re.findall(r'\w+\s*:\s*([A-Z]\w*)', params))

        # و از destructuring آرایه‌ای: .map(([k, l, Ico, tag]) => …)
        for params in re.findall(r'\(\s*\[([^\]]*)\]\s*\)\s*=>', src):
            local |= set(re.findall(r'\b([A-Z]\w*)\b', params))

        used = set(re.findall(r'<([A-Z][A-Za-z0-9]+)[\s/>]', src))
        used |= set(re.findall(r'icon:\s*([A-Z][A-Za-z0-9]+)', src))

        for name in sorted(used):
            if name in imported or name in local:
                continue
            if name in ("React", "Fragment"):
                continue
            icon_problems.append(f"{os.path.relpath(path, ROOT)}: {name}")

check("هر آیکون/کامپوننت استفاده‌شده import شده", not icon_problems,
      f"{len(icon_problems)} مورد" if icon_problems
      else "همان باگی که دو بار پنل را سفید کرد")
if icon_problems:
    bullets(icon_problems, limit=15)


# ═══════════════════════════════════════════════════════════
#  درز ۷ — ماژولی که استفاده شده ولی import نشده (پایتون)
# ═══════════════════════════════════════════════════════════
head("درز ۷ · نام ناموجود در پایتون")

# app.py ماژول re را با نام _re وارد می‌کند. دو تابع تازه `re.match`
# نوشتند — کامپایل بی‌صدا رد می‌شود، چون پایتون نام آزاد را فقط موقع
# اجرا حل می‌کند. NameError وقتی رخ می‌داد که کاربر دکمه را می‌زد.
py_problems = []
STDLIB = ("re", "os", "sys", "json", "time", "math", "random", "socket",
          "sqlite3", "shutil", "subprocess", "hashlib", "hmac", "base64",
          "ipaddress", "tempfile", "logging", "secrets", "string", "uuid")

for rel in ("backend/app.py", "backend/monitor.py", "backend/firewall.py",
            "backend/netid.py", "backend/tunnels.py", "bot/handlers.py",
            "bot/db.py", "bot/core.py", "bot/xui.py", "bot/tg.py",
            "bot/run.py", "agent/nexora-agent.py",
            *sorted(os.path.relpath(f, ROOT).replace(os.sep, "/") for d in ("backend/pro", "bot/pro")
                    for f in glob.glob(os.path.join(ROOT, d, "*.py")))):
    path = os.path.join(ROOT, *resolve(rel).split("/"))
    if not os.path.exists(path):
        continue
    src = io.open(path, encoding="utf-8").read()
    rel = resolve(rel)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue

    bound = set()
    # A namespace file sees every name app.py imports.
    walk_trees = [tree] + ([ast.parse(APP_PY)] if rel in {f"backend/pro/{f}" for f in NS_FILES} else [])
    for node in (x for t_ in walk_trees for x in ast.walk(t_)):
        if isinstance(node, ast.Import):
            for a in node.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                bound.add(a.asname or a.name)

    for mod in STDLIB:
        if mod in bound:
            continue
        hit = re.search(r"(?<![\w.])" + mod + r"\.[a-z_]+\(", src)
        if not hit:
            continue
        # ممکن است داخل خود تابع import شده باشد
        if re.search(r"^\s+import " + mod + r"\b",
                     src + (APP_PY if rel in {f"backend/pro/{f}" for f in NS_FILES} else ""), re.M):
            continue
        line = src[:hit.start()].count("\n") + 1
        py_problems.append(f"{rel}:{line} — {mod}. بدون import")

check("هر ماژولی که استفاده می‌شود import شده", not py_problems,
      f"{len(py_problems)} مورد" if py_problems
      else "همان NameError که فقط موقع کلیک کاربر رخ می‌داد")
if py_problems:
    bullets(py_problems)


# ═══════════════════════════════════════════════════════════
#  درز — هر مسیر مدیریتی باید احراز هویت کند
# ═══════════════════════════════════════════════════════════
head("درز · احراز هویت مسیرها")

# یک نقطه‌ی پایانی مدیریتی که check_auth را جا انداخته باشد، درِ باز
# است — و از بیرون هیچ تفاوتی با بقیه ندارد. با ۱۱۴ مسیر، چشم‌چرانی
# جواب نمی‌دهد؛ این بررسی درخت نحوی را می‌خواند.

import ast as _ast

_tree = _ast.parse(APP_NS)
_routes = []
for _n in _tree.body:
    if not isinstance(_n, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
        continue
    for _d in _n.decorator_list:
        if (isinstance(_d, _ast.Call) and _d.args
                and isinstance(_d.args[0], _ast.Constant)
                and re.fullmatch(r"app\.(get|post|put|delete|patch)",
                                 _ast.unparse(_d.func))):
            _routes.append((_d.args[0].value, _n))

# A floor that says the parser saw the app at all; the Community tree has
# fewer routes (96 at area 8), the full tree over 250.
check("مسیرها از درخت نحوی خوانده شدند", len(_routes) > (100 if HAS_PRO_API else 60),
      f"{len(_routes)} مسیر")

_admin = [(p, n) for p, n in _routes if p.startswith("/api/admin")]
# بی رمز، عمداً: فقط می‌گوید «نشانیِ مخفی درست است» — و خودِ این سنجش در
# `_admin_path_gate` پیش از رسیدن به تابع انجام شده (بی آن هدر ۴۰۴).
_NO_AUTH_OK = {"/api/admin/ping"}
_naked = [(p, n.name, n.lineno) for p, n in _admin
          if "check_auth" not in _ast.unparse(n) and p not in _NO_AUTH_OK]
check("هر مسیر مدیریتی احراز هویت می‌کند", not _naked,
      ("، ".join(f"{p} (خط {ln})" for p, _f, ln in _naked)
       if _naked else f"{len(_admin)} مسیر"))
if _naked:
    bullets([f"{p} — {f}() خط {ln}" for p, f, ln in _naked])

# مسیرهای ایجنت با رمز مدیریت کار نمی‌کنند؛ با توکن و امضای نود.
_agent = [(p, n) for p, n in _routes if p.startswith("/api/agent")]
#: مسیرهایی که عمداً توکن نمی‌خواهند، و دلیلش.
#
#  این پنج‌تا فقط *کد* می‌دهند — منطق مانیتورینگ و فایروال و خودِ
#  ایجنت — نه داده و نه اعتبارنامه. بستنشان ممکن است، ولی download
#  در ایجنت توکن نمی‌فرستد، پس هر ایجنتی که همین حالا روی سرورها
#  نصب است دیگر نمی‌تواند خودش را به‌روز کند و برای همیشه عقب
#  می‌ماند. راهش این است که اول ایجنت توکن بفرستد و بعد این‌جا
#  اجباری شود — نه برعکس.
OPEN_AGENT_ROUTES = {
    "/api/agent/agent.py", "/api/agent/monitor.py",
    "/api/agent/firewall.py", "/api/agent/health.py",
    "/api/agent/netid.py",
    # عیب‌یابیِ ارتباط (۱.۱۱۱) — همان دلیل: فقط کد، و ایجنت بی‌توکن می‌گیردش
    "/api/agent/linkcheck.py",
}

_unsigned = [(p, n.name) for p, n in _agent
             if p not in OPEN_AGENT_ROUTES
             and "_agent_node" not in _ast.unparse(n)
             and "token" not in _ast.unparse(n.args).lower()]
check("هر مسیر ایجنتِ داده‌ای توکن می‌خواهد", not _unsigned,
      ("، ".join(p for p, _f in _unsigned) if _unsigned
       else f"{len(_agent) - len(OPEN_AGENT_ROUTES)} مسیر"))

# The agent routes are Pro (monitoring_multi): none in the Community tree.
_gone = [p for p in OPEN_AGENT_ROUTES
         if _agent and p not in {x for x, _n in _agent}]
check("فهرست استثناها کهنه نشده", not _gone,
      "، ".join(_gone) if _gone else "هر پنج‌تا هنوز هستند")

# و مسیرهای عمومی عمداً بازند — ولی باید کم و شناخته‌شده باشند
_public = sorted(p for p, _n in _routes
                 if not p.startswith(("/api/admin", "/api/agent")))
KNOWN_PUBLIC = {
    "/api/public/config", "/api/preview", "/api/health", "/api/sub/{sub_id}",
    "/", "/api", "/api/docs", "/api/openapi.json",
    # ورود خودش نمی‌تواند رمز بخواهد
    "/api/login",
    # ── پنل نماینده ──
    #
    # این‌ها check_auth ندارند چون رمز مدیر را نمی‌گیرند — از
    # portal_tenant رد می‌شوند که نشست نماینده را می‌سنجد و ردیف
    # مستاجر خودش را برمی‌گرداند. عمداً یک سطح جداست: مسیرهای مدیر
    # همه فرض می‌کنند «تو صاحب سیستمی» و هیچ‌کدامشان نباید دست
    # نماینده بیفتد.
    "/api/portal/{slug}/login",     # ورود، مثل /api/login رمز نمی‌خواهد
    "/api/portal/logout",           # فقط نشست خودش را پاک می‌کند

    # لوگوی برند. عمومی بودنش عمدی است: مینی‌اپ و صفحه‌ی اشتراک
    # بدون احراز هویت بازش می‌کنند. چیزی جز بایت‌های تصویر در پاسخ
    # نیست، و *نوشتن* روی همین منبع از دو مسیرِ محافظت‌شده می‌گذرد
    # (مدیر و portal_tenant).
    "/api/public/logo/{tid}",

    # عکسِ پروفایلِ مشتری. عمومی است چون تگِ <img> نمی‌تواند هدرِ
    # احراز هویت بفرستد — ولی **نامِ فایل تصادفی است**، پس خودش
    # کلیدِ دسترسی است و با شمردنِ شناسه‌ها پیدا نمی‌شود.
    # *نوشتن* رویش از `mini_user` می‌گذرد.
    "/api/public/avatar/{name}",

    # عکسِ داخلِ گفتگو. همان قاعده‌ی آواتار و به همان دلیل: تگِ
    # <img> هدر نمی‌فرستد. نامِ فایل ۱۲ بایت تصادفی دارد، پس
    # «آدرس، خودش کلید است» و شمردنِ شناسه‌ها به جایی نمی‌رسد.
    # *نوشتن* رویش از `mini_user` (مشتری) یا `check_auth` (مالک)
    # می‌گذرد.
    "/api/public/chat-photo/{name}",

    # The bank SMS from the shop's own phone (docs/specs/2026-10-07-sms-auto-approve.md).
    # The forwarder app cannot send the admin password; the address carries
    # 32 random bytes per shop, a wrong one is a 404, and all it can do is
    # store a deposit that still needs a matching receipt.
    "/api/sms/{token}",
}

# بقیه‌ی مسیرهای نماینده یک دسته‌اند و تستِ اختصاصیِ پایین تضمین
# می‌کند همه‌شان از portal_tenant رد می‌شوند — که سختگیرانه‌تر از
# فهرست‌کردن تک‌تکشان این‌جاست.
KNOWN_PUBLIC |= {p for p, _n in _routes if p.startswith("/api/portal/")}

# مینی‌اپ هم همین‌طور: احراز هویتش هدر است نه پارامتر، پس اسکنرِ
# بالا آن را «عمومی» می‌بیند. تستِ اختصاصیِ پایین سختگیرانه‌تر است.
KNOWN_PUBLIC |= {p for p, _n in _routes if p.startswith("/api/mini/")}

# ── پنل همکار فروش ──
#
# مثل نماینده، یک سطحِ جدا: رمزِ مدیر را نمی‌گیرند و از
# `aff_session` رد می‌شوند. ورود و خروج طبیعتاً نشست ندارند —
# ورود که نمی‌تواند نشست بخواهد، و خروج فقط توکنِ خودش را پاک
# می‌کند.
KNOWN_PUBLIC |= {p for p, _n in _routes if p.startswith("/api/aff/")}

# ── هر مسیر نماینده باید به مستاجر خودش محدود باشد ──
#
# همان کاری که بالاتر برای check_auth روی مسیرهای مدیر انجام شد.
# مسیر نماینده‌ای که portal_tenant نداشته باشد یعنی یا احراز هویت
# ندارد یا — بدتر — احراز هویت دارد و محدود نیست، که دقیقاً همان
# باگی است که در مسیرهای ایجنت پیدا شد.
_portal = [(p, n) for p, n in _routes if p.startswith("/api/portal")]
_unguarded = [p for p, n in _portal
              if not p.endswith(("/login", "/logout"))
              and "portal_tenant" not in _ast.unparse(n)]
check("هر مسیر نماینده به مستاجر خودش محدود است", not _unguarded,
      "، ".join(_unguarded) if _unguarded
      else f"{len(_portal)} مسیر، همه پشت portal_tenant")
# ── هر مسیر مینی‌اپ باید امضای تلگرام را بسنجد ──
#
# همان قاعده‌ی مسیرهای نماینده. initData تنها چیزی است که بین
# مشتری‌ها دیوار می‌کشد: بدون سنجیدنش، فرستادن شناسه‌ی دیگری کافی
# است تا کسی اشتراک‌های دیگری را ببیند.
_mini = [(p, n) for p, n in _routes if p.startswith("/api/mini")]
# فهرستِ مجاز، با دلیل. `/api/mini/brand` پیش از ورود صدا زده می‌شود —
# برای اولین فریمِ اسپلش، وقتی initData هنوز سنجیده نشده — و فقط همان
# نام و لوگو و پوسته‌ای را می‌دهد که هر کسی با بازکردنِ ربات می‌بیند.
_MINI_PUBLIC = {"/api/mini/brand"}
_mini_open = [p for p, n in _mini
              if "mini_user" not in _ast.unparse(n) and p not in _MINI_PUBLIC]
check("هر مسیر مینی‌اپ امضای تلگرام را می‌سنجد", not _mini_open,
      "، ".join(_mini_open) if _mini_open
      else f"{len(_mini)} مسیر، همه پشت mini_user")
# و مسیرِ عمومی فقط برند می‌دهد: اگر کسی فردا موجودی یا اشتراک به آن
# اضافه کند، این‌جا می‌ایستد — نه روزی که کسی شناسه‌ها را بشمارد.
_brand_fn = next((n for p, n in _mini if p == "/api/mini/brand"), None)
_brand_src = _ast.unparse(_brand_fn) if _brand_fn else ""
if HAS_PRO_API:                           # the mini app is Pro (backend/pro/mini.py)
  check("مسیرِ عمومیِ مینی‌اپ فقط ظاهرِ فروشگاه را می‌دهد",
      _brand_fn is not None and "return _shop_brand(" in _brand_src
      and _brand_src.count("return ") == 1,
      "هر چیزِ بیشتری پشتِ امضای تلگرام است")

# هر مسیر `/api/aff/*` جز ورود و خروج باید از `aff_session` رد شود.
# بدون این، فردا مسیری اضافه می‌شود که دادهٔ همکارِ دیگر را می‌دهد و
# چون «عمومی» است هیچ دروازه‌ای هم نمی‌گیردش.
_aff = [(p, n) for p, n in _routes if p.startswith("/api/aff")]
_aff_open = [p for p, n in _aff
             if "aff_session" not in _ast.unparse(n)
             and not p.endswith("/login") and not p.endswith("/logout")]
check("هر مسیر همکار از aff_session رد می‌شود", not _aff_open,
      "، ".join(_aff_open) or f"{len(_aff)} مسیر بررسی شد")

# ── درز · تنظیماتِ سکه ──
#
# این درز یک‌بار شکسته بود و **بی‌صدا**: صفحه‌ی «سکه و دعوت» پنل
# `settings.coins_per_referral` می‌نوشت و ربات
# `settings.coins.per_referral` می‌خواند. یعنی مالک عدد می‌گذاشت،
# «ذخیره شد» می‌دید، و ربات همان پیش‌فرض را می‌داد.
#
# اندازه‌گیری‌شده: مالک «۲۵ سکه به معرف» گذاشت، ربات ۱۰ داد. و
# پله‌ها `{coins, pct}` نوشته می‌شدند در حالی که `core.tier_for`
# `percent` می‌خواهد — با `pct` اصلاً KeyError می‌داد.
#
# هیچ تستی نگرفتش چون هر دو طرف جدا درست بودند؛ فقط به هم وصل
# نبودند. این‌جا دقیقاً همان اتصال سنجیده می‌شود.
print(f"\n{D}── درز · سکه: پنل ↔ ربات ──{X}")

def _nocomment(src):
    """
    کامنت‌ها را برمی‌دارد.

    لازم شد چون خودِ همین باگ بالای فایل توضیح داده شده — با نامِ
    کلیدهای غلطش. بدون این، دروازه به کامنتی که می‌گوید «این غلط
    بود» گیر می‌داد و مجبور می‌شدیم توضیح را پاک کنیم تا تست سبز
    شود؛ یعنی دقیقاً همان دانشی را دور بیندازیم که نگهش داشتیم.

    فقط برای JS/JSX. روی پایتون نزنش: `backend/app.py` داخلِ رشته‌ها
    `/*` دارد (قطعه‌های shell و CSS)، و این تابع از اولین `/*` تا
    آخرین `*/` را یک‌جا می‌خورد — یک‌بار همین‌جا ۲۵۶ هزار کاراکتر،
    یعنی نصفِ فایل، بی‌صدا حذف شد و دروازه‌ی تازه روی ناحیه‌ی
    حذف‌شده سبز ماند. برای پایتون `_py_nocomment` هست.
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _py_nocomment(src):
    """
    کامنت‌های پایتون را برمی‌دارد، بدون دست‌زدن به رشته‌ها.

    با tokenize، نه regex: `"#"` داخلِ یک رشته کامنت نیست و regex
    فرقشان را نمی‌فهمد.
    """
    import tokenize as _tk
    out = []
    try:
        for tok in _tk.generate_tokens(io.StringIO(src).readline):
            if tok.type == _tk.COMMENT:
                continue
            out.append(tok)
        return _tk.untokenize(out)
    except Exception:
        # **متنِ خام برنمی‌گردانیم.**
        #
        # `tokenize` روی یک قطعه‌ی تورفته‌ی وسطِ فایل (نه کلِ فایل)
        # در بعضی نسخه‌های پایتون خطا می‌دهد. نسخه‌ی قبلی این‌جا
        # `src` را پس می‌داد، یعنی کامنت‌ها می‌ماندند و صداکننده
        # بی‌خبر بود — یک دروازه روی CI قرمز شد و محلی سبز، چون
        # ۳.۱۰ و ۳.۱۴ این‌جا مثل هم رفتار نمی‌کنند.
        #
        # حذفِ خط‌به‌خط کامل نیست (`#` داخلِ رشته را هم می‌برد) ولی
        # دست‌کم در همان جهتِ درست خطا می‌کند.
        return "\n".join(
            "" if ln.strip().startswith("#") else ln.split("  #")[0]
            for ln in src.splitlines())


# The coins screen is Pro (loyalty, frontend/src/pro/coins.jsx) since 2.0.
if exists("frontend/src/sections/bot/coins.jsx"):
    _coins_jsx = _nocomment(rd("frontend", "src", "sections", "bot", "coins.jsx"))
    _core_py = rd("bot", "core.py")

    # کلیدهای واقعیِ ربات، از خودِ `DEFAULT_COIN_SETTINGS`
    _m = re.search(r"DEFAULT_COIN_SETTINGS\s*=\s*\{(.*?)\n\}", _core_py, re.S)
    _bot_keys = set(re.findall(r'"(\w+)"\s*:', _m.group(1))) if _m else set()
    check("کلیدهای سکه‌ی ربات خوانده شدند", len(_bot_keys) >= 5,
          "، ".join(sorted(_bot_keys)) if _bot_keys else "DEFAULT_COIN_SETTINGS پیدا نشد")

    # پنل باید زیر `coins` بنویسد، نه کنارش
    check("پنل تنظیمات سکه را زیر کلید coins می‌گذارد",
          "coins: {" in _coins_jsx or "coins: c" in _coins_jsx,
          "ربات `ctx.s.get(\"coins\")` می‌خواند؛ کلیدِ مسطح را هیچ‌وقت نمی‌بیند")

    # هیچ کلیدِ مسطحِ قدیمی نماند
    _flat = [k for k in ("coins_per_referral", "coins_for_invitee",
                         "min_purchase_for_coin", "coin_tiers")
             if k in _coins_jsx]
    check("کلیدهای مسطحِ قدیمی برنگشته‌اند", not _flat,
          "، ".join(_flat) if _flat else "هیچ‌کدام به ربات نمی‌رسیدند")

    # هر کلیدی که پنل داخلِ شیءِ سکه می‌نویسد باید ربات بشناسدش
    _obj = re.search(r"const DEFAULTS = \{(.*?)\n\};", _coins_jsx, re.S)
    _panel_keys = set(re.findall(r"^\s*(\w+):", _obj.group(1), re.M)) if _obj else set()
    _unknown = sorted(_panel_keys - _bot_keys)
    check("هر کلیدی که پنل می‌نویسد ربات می‌شناسد", not _unknown,
          "، ".join(_unknown) if _unknown
          else f"{len(_panel_keys)} کلید، همه در DEFAULT_COIN_SETTINGS")

    # و هیچ کلیدی از قلم نیفتاده باشد: چیزی که پنل تنظیمش نمی‌کند،
    # مالک هم نمی‌تواند عوضش کند
    _missing = sorted(_bot_keys - _panel_keys - {"tiers"})
    check("و هر کلیدی که ربات دارد در پنل قابل تنظیم است", not _missing,
          "، ".join(_missing) if _missing else f"{len(_bot_keys)} کلید")

    # نامِ فیلدِ پله — `percent`، نه `pct`
    check("پله‌ها percent می‌نویسند، نه pct",
          "pct" not in _coins_jsx and "percent:" in _coins_jsx,
          "`core.tier_for` روی `reached[\"percent\"]` می‌ایستد و با pct KeyError می‌دهد")

# مینی‌اپ نردبان را خودش نسازد — همان قاعده‌ی «پول یک هسته دارد»
# The mini app is Pro (frontend/src/pro/mini.jsx); absent in the Community tree.
if os.path.exists(os.path.join(ROOT, "frontend", "src", "pro", "mini.jsx")):
    _mini_rw = _nocomment(rd("frontend", "src", "pro", "mini.jsx"))
    check("مینی‌اپ نردبانِ تخفیف را دوباره حساب نمی‌کند",
          "/api/mini/rewards" in _mini_rw
          and not re.search(r"coins\s*>=\s*\d+\s*\?", _mini_rw),
          "درصد از `core.coin_progress` می‌آید — همان که لحظه‌ی خرید قیمت را کم می‌کند")

# The rewards route is the mini app's (Pro): in APP_NS when the tree has it.
if HAS_PRO_API:
    check("و مسیرِ پاداش هم از خودِ core می‌پرسد",
          "core.coin_progress(" in APP_NS,
          "دو نسخه یعنی روزی مینی‌اپ ۳۰٪ نشان دهد و صندوق ۲۰٪ کم کند")

    check("مسیرِ پاداش همان کلیدی را می‌خواند که ربات",
          'st.get("coins")' in APP_NS,
          "هر دسترسیِ دیگری یعنی دو نردبانِ متفاوت")


_new_public = [p for p in _public if p not in KNOWN_PUBLIC]
check("مسیر عمومی تازه‌ای بی‌خبر اضافه نشده", not _new_public,
      ("، ".join(_new_public) if _new_public
       else f"{len(_public)} مسیر عمومی شناخته‌شده"))
if _new_public:
    bullets(_new_public)



# ═══════════════════════════════════════════════════════════
#  درز — هر کوئری باید به مستاجر محدود باشد
# ═══════════════════════════════════════════════════════════
head("درز · محدودشدن به مستاجر")

# ربات چندمستاجری است: هر فروشگاه جدول‌های مشترک دارد و فقط ستون
# tenant_id آن‌ها را از هم جدا می‌کند. یک کوئری که آن شرط را جا
# بیندازد، داده‌ی یک فروشگاه را در ربات دیگری نشان می‌دهد — و هیچ
# خطایی هم نمی‌دهد، چون نتیجه «معتبر» به نظر می‌رسد.

TENANT_TABLES = {
    "users", "plans", "orders", "subscriptions", "coin_tx", "wallet_tx",
    "discounts", "tickets", "affiliates", "affiliate_commissions",
    "affiliate_payouts", "events",
}

#: کوئری‌هایی که عمداً به مستاجر محدود نیستند، و دلیلشان.
#: هر ورودی یک تصمیم است، نه یک استثنا.
TENANT_FREE = {
    "UPDATE subscriptions SET plan_name":
        "مهاجرت یک‌باره — عمداً روی همه‌ی مستاجرها، و روی plan_id که "
        "سراسری یکتاست",
    "UPDATE orders SET status='awaiting' WHERE status='review'":
        "مهاجرت یک‌باره — نامِ وضعیتِ قدیمیِ در انتظار، برای همه‌ی "
        "مستاجرها؛ هیچ ردیفی از مستاجری به مستاجرِ دیگر نمی‌رود",
}


def _sql_literals(tree):
    """رشته‌های SQL، با چسباندن رشته‌های مجاور."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            parts = [v.value for v in node.values
                     if isinstance(v, ast.Constant) and isinstance(v.value, str)]
            out.append((node.lineno, " ".join(parts)))
    return out


_leaks, _checked = [], 0
for _path, _src in (("bot/db.py", DB_PY), ("bot/handlers.py", HANDLERS)):
    for _ln, _q in _sql_literals(ast.parse(_src)):
        if not re.search(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM)\b",
                         _q, re.I):
            continue
        _tables = {t.lower() for t in re.findall(
            r"(?:FROM|INTO|UPDATE|JOIN)\s+([a-z_]+)", _q, re.I)}
        if not (_tables & TENANT_TABLES):
            continue
        _checked += 1
        if "tenant_id" in _q:
            continue
        _flat = " ".join(_q.split())
        if any(_flat.startswith(k) for k in TENANT_FREE):
            continue
        _leaks.append(f"{_path}:{_ln} — {_flat[:70]}")

check("کوئری‌های مستاجری پیدا شدند", _checked > 60, f"{_checked} کوئری")
check("همه به مستاجر محدودند", not _leaks,
      f"{len(_leaks)} بدون شرط" if _leaks else f"{_checked} کوئری")
if _leaks:
    bullets(_leaks)



# ═══════════════════════════════════════════════════════════
#  درز — SQL ساخته‌شده با درج رشته
# ═══════════════════════════════════════════════════════════
head("درز · درجِ رشته در SQL")

# مقدارها همیشه با ? پارامتر می‌شوند، ولی *نام* جدول و ستون را
# نمی‌شود پارامتر کرد — پس چند جا با f-string ساخته می‌شوند.
#
# تا وقتی آن نام‌ها از خود کد بیایند (فهرست ثابت، فهرست سفید، یا
# اسکیمای دیتابیس) هیچ مشکلی نیست. خطر جایی است که چیزی از بدنه‌ی
# درخواست مستقیم داخل کوئری بنشیند.

#: نام‌هایی که یعنی «این از بیرون آمده».
REQUEST_ISH = ("payload", "request", "body", "form", "params",
               "user_input", "raw_input")

SQL_KW = re.compile(
    r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM|ALTER TABLE|PRAGMA)\b", re.I)

_interp, _risky = 0, []
for _path in ("backend/app.py", "bot/db.py", "bot/handlers.py",
              "backend/tunnels.py"):
    if not exists(_path):
        continue
    _src = rd(_path)
    for _n in ast.walk(ast.parse(_src)):
        if not isinstance(_n, ast.JoinedStr):
            continue
        _lit = " ".join(v.value for v in _n.values
                        if isinstance(v, ast.Constant)
                        and isinstance(v.value, str))
        if not SQL_KW.search(_lit):
            continue
        _interp += 1
        for _v in _n.values:
            if not isinstance(_v, ast.FormattedValue):
                continue
            _expr = ast.unparse(_v.value)
            if any(r in _expr.lower() for r in REQUEST_ISH):
                _risky.append(f"{_path}:{_n.lineno} — {{{_expr}}}")

check("کوئری‌های درج‌شده پیدا شدند", _interp > 15, f"{_interp} کوئری")
check("هیچ‌کدام مقدارِ درخواست را داخل SQL نمی‌گذارند", not _risky,
      f"{len(_risky)} مورد" if _risky else f"{_interp} کوئری بررسی شد")
if _risky:
    bullets(_risky)



# ═══════════════════════════════════════════════════════════
#  درز — مسیر فایل‌ها در نصب، کد، و CLI
# ═══════════════════════════════════════════════════════════
head("درز · مسیر داده‌ها")

# سه جا باید درباره‌ی محل فایل‌ها یک حرف بزنند: install.sh که متغیرها
# را در سرویس systemd می‌نویسد، کدی که پیش‌فرض‌ها را دارد، و
# nexora-cli که موقع نسخه‌برداری همان‌جا را می‌گردد.
#
# اگر از هم فاصله بگیرند، پنل جایی می‌نویسد که نسخه‌بردار نگاه
# نمی‌کند — و روزی که به پشتیبان نیاز باشد، خالی است.

INSTALL_SH = rd("install.sh")
CLI_SH = rd("nexora-cli.sh")

# متغیرهایی که کد می‌خواند
_read_env = set(re.findall(r'getenv\("([A-Z_]+)"', APP_PY + rd("bot/db.py")
                           + (rd("backend/tunnels.py") if exists("backend/tunnels.py") else "")))
check("متغیرهای محیطی کد پیدا شدند", len(_read_env) > 8,
      f"{len(_read_env)} متغیر")

# آن‌هایی که *باید* در نصب تنظیم شوند، چون پیش‌فرضشان نسبی است
MUST_SET = {"CONFIG_PATH", "AUTH_PATH", "SUBPAGE_HTML_PATH",
            "TUNNEL_DB_PATH", "BOT_DB_PATH"}
_unset = [v for v in MUST_SET if f'{v}=' not in INSTALL_SH]
check("نصب همه‌ی مسیرهای لازم را تنظیم می‌کند", not _unset,
      "، ".join(_unset) if _unset else f"{len(MUST_SET)} متغیر")

# دیتابیس‌ها باید کنار هم در data/ باشند — همان‌جا که CLI می‌گردد
for _db in ("bot.db", "billing.db", "tunnels.db"):
    check(f"«{_db}» در نسخه‌برداری هست", f"{_db}" in CLI_SH,
          "وگرنه پشتیبان بدون آن ساخته می‌شود")

check("نصب، داده را در data/ کنار نصب می‌گذارد",
      "CONFIG_PATH=$INSTALL_DIR/data/config.json" in INSTALL_SH,
      "پیش‌فرض billing.db و bot.db از کنار همین ساخته می‌شود")
check("و CLI هم همان‌جا را می‌گردد",
      '"$INSTALL_DIR/data/$db"' in CLI_SH
      or '$INSTALL_DIR/data/bot.db' in CLI_SH,
      "سه جا باید یک حرف بزنند")



# ═══════════════════════════════════════════════════════════
#  درز — متغیری که هیچ‌جا مقدار نگرفته
# ═══════════════════════════════════════════════════════════
head("درز · متغیر بی‌مقدار در تابع")

# همان خانواده‌ی بالا، ولی یک پله نزدیک‌تر: نه ماژول جاافتاده، بلکه
# متغیری که *در تابعِ دیگری* مقدار می‌گیرد و این‌جا بی‌مقدار خوانده
# می‌شود. پایتون تا لحظه‌ی اجرا چیزی نمی‌گوید، و چون این خط معمولاً
# پشت یک شرط است — «اگر ادمین رد کرد»، «اگر پورت حیاتی بود» — تست‌های
# معمولی هم از کنارش رد می‌شوند.
#
# سه بار همین اتفاق افتاد: یک‌بار در مسیر تایید سفارش از گروه ادمین،
# دوبار وقتی یک مقدار مشترک را به چند تابع بردم و در یکی‌شان تعریفش
# را جا انداختم. هر سه فقط وقتی خودشان را نشان می‌دادند که کاربر
# دقیقاً همان دکمه را می‌زد.

PYFILES = [
    "backend/app.py", "backend/monitor.py", "backend/firewall.py",
    "backend/netid.py", "backend/tunnels.py", "backend/health.py",
    "backend/intrusion.py", "backend/fx.py", "bot/handlers.py",
    "bot/db.py", "bot/core.py", "bot/xui.py", "bot/tg.py", "bot/run.py",
    "bot/fmt.py", "bot/qr.py", "agent/nexora-agent.py",
]

import builtins as _bi
_BUILTIN = set(dir(_bi)) | {"__file__", "__name__", "__doc__", "__spec__"}


def _bound_in(node):
    """هر نامی که در این زیردرخت مقدار می‌گیرد — سخاوتمندانه."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                out.add(a.asname or a.name)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                            ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
        elif isinstance(n, (ast.arg,)):
            out.add(n.arg)
    return out


unbound = []
for rel in PYFILES:
    path = os.path.join(ROOT, *resolve(rel).split("/"))
    if not os.path.exists(path):
        continue
    try:
        tree = ast.parse(io.open(path, encoding="utf-8").read())
    except SyntaxError:
        continue

    # نام‌های سطح ماژول: هر چیزی که بیرون توابع مقدار می‌گیرد
    modscope = set(_BUILTIN)
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            modscope.add(n.name)
        else:
            modscope |= _bound_in(n)

    # فقط توابع سطح بالا و متدها — تابع تودرتو داخل همین زیردرخت است
    funcs = [n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        funcs += [n for n in cls.body
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    for fn in funcs:
        bound = modscope | _bound_in(fn)
        for stmt in fn.body:
            for n in ast.walk(stmt):
                if (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                        and n.id not in bound):
                    unbound.append(f"{rel}:{n.lineno} — {n.id} در {fn.name}()")

check("هر متغیری که خوانده می‌شود جایی مقدار گرفته", not unbound,
      f"{len(unbound)} مورد" if unbound
      else f"{len(PYFILES)} فایل — NameError پشت شرط پنهان نمانده")
if unbound:
    bullets(unbound)


# ═══════════════════════════════════════════════════════════
head("درز · CLI ↔ ابزارها")

# `case "$1" in` آرگومان‌ها را جابه‌جا نمی‌کند: بدون shift، نامِ خودِ
# دستور هم داخل "$@" می‌ماند و به اسکریپت می‌رسد.
#
#     $ nexora import-topups --apply
#     error: unrecognized arguments: import-topups
#
# دستور کاملاً سالم به نظر می‌رسد و فقط موقع اجرای واقعی می‌شکند —
# یعنی دست کاربر، نه این‌جا.

CLI = io.open(os.path.join(ROOT, "nexora-cli.sh"), encoding="utf-8").read()

#: هر شاخه‌ی case، از برچسبش تا ;;
_branches = re.findall(r'\n  ([a-z][a-z|_-]*\))\n(.*?)\n    ;;',
                       CLI, re.S)
check("شاخه‌های CLI استخراج شدند", len(_branches) > 10,
      f"{len(_branches)} شاخه")

def _code_only(body):
    """
    بدنه بدون کامنت‌ها.

    اولین نسخه‌ی این تست کامنت‌ها را هم می‌خواند و برای همین وقتی
    shift را عمداً برداشتم، همچنان سبز ماند: کامنتِ بالای همان خط
    کلمه‌ی «shift» را داشت. تستی که با توضیحِ کنارِ کد فریب بخورد،
    چیزی را محافظت نمی‌کند.
    """
    out = []
    for ln in body.split("\n"):
        cut = ln.find("#")
        out.append(ln if cut < 0 else ln[:cut])
    return "\n".join(out)


_noshift = []
for _label, _body in _branches:
    _code = _code_only(_body)
    if '"$@"' not in _code:
        continue
    _name = _label.rstrip(")")
    # دو راه درست وجود دارد و هر دو قبول است:
    #   ۱. shift پیش از اولین استفاده از "$@"
    #   ۲. خودِ نام صریح دور انداخته شود — کاری که rollback می‌کند،
    #      چون روی "$@" حلقه می‌زند و `rollback) ;;` را نادیده
    #      می‌گیرد
    _at = _code.index('"$@"')
    if "shift" in _code[:_at]:
        continue
    if any(f"{alt})" in _code for alt in _name.split("|")):
        continue
    _noshift.append(_name)

check("نام خودِ دستور به ابزار نمی‌رسد", not _noshift,
      "، ".join(_noshift) if _noshift
      else "یا shift می‌کنند یا نامشان را صریح دور می‌اندازند")
if _noshift:
    bullets(_noshift)

# هر ابزاری که CLI صدا می‌زند باید واقعاً وجود داشته باشد
_called = set(re.findall(r'scripts/([a-z0-9-]+\.py)', CLI))
_missing = [t for t in sorted(_called)
            if not os.path.exists(os.path.join(ROOT, "scripts", t))]
check("هر ابزاری که CLI صدا می‌زند وجود دارد", not _missing,
      "، ".join(_missing) if _missing else f"{len(_called)} ابزار")
if _missing:
    bullets(_missing)

# و در راهنما دیده شود، وگرنه کسی پیدایش نمی‌کند.
#
# فهرست **استخراج می‌شود**، نه دستی نوشته. نسخه‌ی قبلی چهار نام را
# ثابت داشت، یعنی دستورِ تازه‌ای که به CLI اضافه شود از دیدِ دروازه
# پنهان می‌ماند — همان الگویی که یک‌بار سرِ صفحه‌ی «کانال» افتاد و
# با `data-navhead` حل شد.
_cmds = set()
for _m in re.finditer(r"^  ([a-z0-9][a-z0-9|-]*)\)\s*$", CLI, re.M):
    _label = _m.group(1)
    _body = CLI[_m.end():]
    _body = _body[:_body.find(";;")] if ";;" in _body else _body
    if "scripts/" in _body:
        # نامِ اصلی، نه نام‌های مستعار
        _cmds.add(_label.split("|")[0])

check("شاخه‌های ابزاری استخراج شدند", len(_cmds) >= 4,
      "، ".join(sorted(_cmds)))

_unlisted = [c for c in sorted(_cmds) if f"nexora {c}" not in CLI]
check("دستورهای ابزاری در راهنما فهرست شده‌اند", not _unlisted,
      "، ".join(_unlisted) if _unlisted else "، ".join(sorted(_cmds)))
if _unlisted:
    bullets([f"{c} — شاخه دارد، در راهنما نیست" for c in _unlisted])


# ═══════════════════════════════════════════════════════════
head("درز · «کدام مستاجر» باید صریح باشد")

# همین یک اشتباه امروز پنج بار پیدا شد:
#
#     SELECT ... FROM tenants LIMIT 1
#
# بدون شرط و بدون ترتیب. به مالک می‌رسد فقط چون معمولاً کوچک‌ترین
# شناسه مال اوست — و همین که ردیف مالک یک‌بار پاک و دوباره ساخته
# شود (اجرای دوباره‌ی نصب)، شناسه‌اش از نماینده بزرگ‌تر می‌شود.
#
# آن‌وقت: درآمد ربات صفر می‌شود، هشدار سرور به گروه نماینده می‌رود،
# همکار فروش زیر مستاجر اشتباه ساخته می‌شود و پورسانتش از دفتر کل
# بیرون می‌ماند، و اعتبارنامه‌ی پنل از ردیف خالی خوانده می‌شود.
#
# هیچ‌کدام خطا نمی‌دهند. همه‌شان بی‌صدا جواب اشتباه می‌دهند.

_PYSQL = []
for _rel in ("backend/app.py", "bot/db.py", "backend/tunnels.py"):
    _p = os.path.join(ROOT, *resolve(_rel).split("/"))
    if os.path.exists(_p):
        _PYSQL.append((_rel, io.open(_p, encoding="utf-8").read()))

check("فایل‌های حاوی SQL پیدا شدند", len(_PYSQL) >= 2,
      "، ".join(r for r, _ in _PYSQL))

#: راه‌های درستِ مشخص‌کردن مستاجر
_OK_MARKS = ("parent_id IS NULL", "WHERE id=?", "WHERE id = ?",
             "bot_token=?", "bot_token = ?", "portal_slug=?",
             "portal_slug = ?", "tenant_id=?", "tenant_id = ?")

_loose = []
for _rel, _src in _PYSQL:
    # رشته‌های چسبیده به هم را یکی می‌کنیم، وگرنه شرط و LIMIT در دو
    # رشته‌ی جدا می‌افتند و اسکنر هیچ‌کدام را کامل نمی‌بیند.
    _flat = re.sub(r'"\s*\n\s*"', "", _src)
    _flat = re.sub(r"'\s*\n\s*'", "", _flat)
    for _m in re.finditer(r"FROM tenants[^\"']{0,240}", _flat):
        _sql = _m.group(0)
        if not re.search(r"LIMIT\s+1", _sql, re.I):
            continue
        if any(k in _sql for k in _OK_MARKS):
            continue
        _line = _flat[:_m.start()].count("\n") + 1
        _loose.append(f"{_rel}:~{_line} — {_sql[:70].strip()}")

check("هیچ «FROM tenants … LIMIT 1» بی‌شرطی نمانده", not _loose,
      f"{len(_loose)} مورد" if _loose
      else "هر کدام یا مستاجر ریشه را می‌خواهند یا شناسه‌ی مشخص")
if _loose:
    bullets(_loose)

# و هر جا ریشه خواسته می‌شود، ترتیب هم باید باشد: دو ردیف ریشه
# ممکن است وجود داشته باشد و بدون ORDER BY انتخاب دلخواه است.
_noorder = []
for _rel, _src in _PYSQL:
    _flat = re.sub(r'"\s*\n\s*"', "", _src)
    for _m in re.finditer(r"FROM tenants[^\"']{0,240}", _flat):
        _sql = _m.group(0)
        if "parent_id IS NULL" not in _sql:
            continue
        if not re.search(r"LIMIT\s+1", _sql, re.I):
            continue
        if "ORDER BY" in _sql.upper():
            continue
        _line = _flat[:_m.start()].count("\n") + 1
        _noorder.append(f"{_rel}:~{_line} — {_sql[:70].strip()}")

check("انتخاب مستاجر ریشه ترتیب مشخص دارد", not _noorder,
      f"{len(_noorder)} مورد" if _noorder
      else "بدون ORDER BY، «اولین ریشه» تعریف‌شده نیست")
if _noorder:
    bullets(_noorder)


# ═══════════════════════════════════════════════════════════
#  تنظیماتِ مستاجر: هر دو جهت
#
#  برگه‌اش: docs/specs/2026-09-19-reminders-and-settings-seam.md
#
#  این همان درزی است که باگِ سکه از آن آمد: پنل
#  `settings.coins_per_referral` می‌نوشت و ربات
#  `settings.coins.per_referral` می‌خواند. هیچ خطایی نداد — عدد
#  فقط هیچ‌وقت نرسید.
#
#  یک‌بار دستی مرورش کردیم و هشت کلید پیدا شد (`BOT_BEHAVIOUR` در
#  texts.jsx از همان‌جا آمد). ولی آن مرور فقط handlers.py را دید،
#  و `reminders` که در run.py خوانده می‌شود جا ماند — تا نسخه‌ی
#  ۱.۷۱.۰ هیچ راهی برای خاموش‌کردنِ یادآوری‌ها نبود.
#
#  پس این‌بار به‌جای مرورِ دستی، دروازه.
# ═══════════════════════════════════════════════════════════
head("تنظیمات مستاجر: پنل می‌نویسد، ربات می‌خواند")

_RUN_PY = rd("bot", "run.py")

# جهتِ اول: ربات می‌خواند، کسی باید بنویسد.
#
# `ctx.s.get(...)` در handlers و `cfg.get(...)` در run — دو شکلِ
# رسیدن به همان دیکشنری.
_reads = set(re.findall(r'ctx\.s\.get\(\s*"([a-z_0-9]+)"', HANDLERS))
_reads |= set(re.findall(r'cfg\.get\(\s*"([a-z_0-9]+)"', _RUN_PY))

# کلیدهایی که نصب‌کننده یا خودِ بک‌اند می‌گذارند و پنل فیلد ندارد
_SETTINGS_OK = {"brand", "apps", "configs", "clients", "topics"}

# هر صفحه‌ای که تنظیماتِ ربات را می‌خواند یا می‌نویسد، خودش پیدا
# می‌شود. فهرستِ دستی یعنی صفحه‌ی تازه از دیدِ دروازه پنهان است —
# و دقیقاً همین یک‌بار اتفاق افتاد: صفحه‌ی «کانال» ساخته شد و
# `channel_id` در هیچ‌کدام از پنج فایلِ فهرست نبود.
#
# از ۱.۸۷ صفحه‌های ربات تنظیمات را از راهِ `lib/botsrc.js` می‌خوانند
# (`S.settings()` / `S.saveSettings(...)`) تا همان صفحه برای نماینده
# هم کار کند. پس «صفحه‌ی تنظیمات» یعنی یکی از این دو در آن هست؛
# بدونِ این، با آن جابه‌جایی متن‌ها و سکه از دیدِ دروازه پنهان شدند و
# ۱۶ کلید «بی‌فیلد» خوانده شدند.
_SETTINGS_DOOR = re.compile(r'/api/admin/bot/settings|\b(?:S|src)\.(?:saveSettings|settings)\(')
_front_files = []
for _dir in (("sections",), ("pro",)):          # Pro screens (and the portal) since 2.0
    for _b, _d, _f in os.walk(os.path.join(ROOT, "frontend", "src", *_dir)):
        for _n in _f:
            if not _n.endswith(".jsx"):
                continue
            _src = io.open(os.path.join(_b, _n), encoding="utf-8").read()
            if _SETTINGS_DOOR.search(_src):
                _front_files.append(_src)
_FRONT = "\n".join(_front_files)

_unwritten = sorted(
    k for k in _reads
    if k not in _SETTINGS_OK
    and not re.search(rf'["\']{k}["\']', _FRONT)
    and not re.search(rf'\b{k}\s*:', _FRONT))

#: Keys the bot reads whose only screen is Pro. In the Community tree nothing
#: writes them, and that is the edition, not a bug: written down, not hidden.
COMMUNITY_UNWRITTEN = {
    "coins": "coin tiers are set on the Pro coins screen; Community spends coins "
             "a customer already has at the saved (or default) tiers",
}
if not HAS_PRO_API:
    _unwritten = [k for k in _unwritten if k not in COMMUNITY_UNWRITTEN]
check("هر کلیدی که ربات می‌خواند، پنل راهی برای نوشتنش دارد",
      not _unwritten,
      f"{len(_unwritten)} کلید بی‌فیلد" if _unwritten
      else f"{len(_reads)} کلید سنجیده شد")
if _unwritten:
    bullets([f"{k} — ربات می‌خواند، هیچ صفحه‌ای نمی‌نویسد" for k in _unwritten])

# جهتِ دوم — خطرناک‌تر: پنل می‌نویسد و هیچ‌کس نمی‌خواند.
#
# این سمت بی‌صداست: مالک عدد می‌گذارد، «ذخیره شد» می‌بیند، و هیچ
# اتفاقی نمی‌افتد.
_BOT_ALL = HANDLERS + _RUN_PY + rd("bot", "core.py") + rd("bot", "db.py")

_writes = set()
for _m in re.finditer(r'upS\(\s*\{\s*([a-z_][a-z_0-9]*)\s*:', _FRONT):
    _writes.add(_m.group(1))
for _m in re.finditer(r'\bsettings:\s*\{\s*\.\.\.[a-z.]+,\s*([a-z_][a-z_0-9]*)\s*:',
                      _FRONT):
    _writes.add(_m.group(1))
# همان نوشتن از راهِ درِ تازه: saveSettings({ ...x, key: … }) و
# saveSettings({ key: …, key2: … })
for _m in re.finditer(r'saveSettings\(\s*\{([^}]*)', _FRONT):
    for _k in re.findall(r'(?:^|,)\s*([a-z_][a-z_0-9]*)\s*:', _m.group(1)):
        _writes.add(_k)

#: تنظیم‌هایی که فقط خودِ پنل مصرفشان می‌کند — ربات نمی‌بیندشان و
#: نباید هم ببیند. هر قلم دلیلش را همراه دارد.
_PANEL_ONLY = {
    "quick_replies": "پاسخ‌های آماده‌ی صندوق — پنل می‌نویسد و پنل می‌خواند",
}

_unread = sorted(k for k in _writes
                 if k not in _PANEL_ONLY
                 and not re.search(rf'"{k}"', _BOT_ALL)
                 and not re.search(rf'"{k}"', APP_PY))

check("هر کلیدی که پنل می‌نویسد، جایی خوانده می‌شود",
      not _unread,
      f"{len(_unread)} کلیدِ مرده" if _unread
      else f"{len(_writes)} کلید سنجیده شد")
if _unread:
    bullets([f"{k} — پنل می‌نویسد، هیچ‌کس نمی‌خواند" for k in _unread])

# کارتی که تعریف شده ولی سوار نیست، «فیلد» نیست.
#
# دروازه‌ی بالا فقط می‌بیند که کلید در فایل هست. اگر کسی
# `<Reminders />` را از JSX بردارد و خودِ تابع را جا بگذارد، کلید
# هنوز در فایل دیده می‌شود ولی مالک هیچ‌وقت آن فیلد را نمی‌بیند.
#
# جاروی شکستن دقیقاً همین را نشان داد: برداشتنِ سوارشدنِ کارت،
# هیچ دروازه‌ای را قرمز نکرد.
_orphans = []
for _rel in ["frontend/src/sections/bot/texts.jsx",
             "frontend/src/sections/bot/coins.jsx",
             "frontend/src/sections/bot/discounts.jsx",
             "frontend/src/sections/bot/connection.jsx"]:
    if not exists(_rel):
        continue                      # a Pro screen; none in the Community tree
    _src = _nocomment(rd(*_rel.split("/")))
    for _m in re.finditer(r"^(export\s+)?function\s+([A-Z][A-Za-z0-9_]*)\s*\(",
                          _src, re.M):
        _exported, _name = _m.group(1), _m.group(2)
        if _exported:
            continue          # از بیرون سوار می‌شود (App.jsx)
        if re.search(rf"<{_name}[\s/>]", _src):
            continue
        _orphans.append(f"{_rel.split('/')[-1]}:{_name}")

# نامِ سطح‌ماژولیِ تکراری در app.py — دومی بی‌صدا جای اولی را می‌گیرد.
# `_FA_DIGITS` سه بار تعریف شده بود، یکی‌شان برعکسِ بقیه (لاتین ← فارسی)، و
# چون پایین‌تر بود، همه‌ی «فارسی ← لاتین»ها در عمل برعکس کار می‌کردند.
import ast as _ast                                        # noqa: E402
_seen_top = {}
_dups_top = []
for _n in _ast.parse(rd("backend", "app.py")).body:
    _names = ([_t.id for _t in _n.targets if isinstance(_t, _ast.Name)]
              if isinstance(_n, _ast.Assign)
              else [_n.name] if isinstance(_n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef))
              else [])
    for _nm in _names:
        if _nm in _seen_top:
            _dups_top.append(f"{_nm} (خطِ {_seen_top[_nm]} و {_n.lineno})")
        _seen_top.setdefault(_nm, _n.lineno)
check("هیچ نامِ سطح‌ماژولی در app.py دو بار تعریف نشده", not _dups_top, "، ".join(_dups_top[:4]))

check("هر کارتی که ساخته شده، جایی سوار هم هست", not _orphans,
      f"{len(_orphans)} کارتِ یتیم" if _orphans
      else "کارتِ تعریف‌شده‌ی بی‌مصرف نداریم")
if _orphans:
    bullets([f"{x} — تعریف شده، هیچ‌جا سوار نشده" for x in _orphans])

# ═══════════════════════════════════════════════════════════
#  درز — «این کاربر خرید؟» یک قاعده است، نه چند تا
# ═══════════════════════════════════════════════════════════
#
# گرفتنِ تستِ رایگان خودش یک سفارشِ `approved` با مبلغ صفر می‌سازد.
# پس هر کوئری‌ای که به یک *کاربر* نگاه می‌کند و می‌پرسد «خرید کرده؟»
# باید پلنِ تست را کنار بگذارد، وگرنه هر کسی که دکمه‌ی تست را زده
# خریدار شمرده می‌شود.
#
# چرا دروازه شد: قیف این قاعده را داشت و صفحه‌ی کاربران نداشت. روی
# همان داده، قیف «۱ خرید موفق» می‌گفت و چیپِ «خریدار» «۲» — و لیست
# کنارِ نامِ کسی که فقط تست گرفته بود می‌نوشت «۱ خرید · ۰ تومان».
# همان الگوی همیشگی: یک قاعده، دو جا، اصلاح در یکی.
#
# مبلغ برای تشخیص کافی نیست: تستِ صفر تومانی و سفارشِ صددرصد
# تخفیف‌خورده هر دو صفرند، ولی یکی تبدیل است و دیگری نه.

# ثابت‌ها را باز می‌کنیم، وگرنه کوئریِ درست (که {SQL_REAL_BUY}
# می‌نویسد) شکلِ approved ندارد و دروازه بی‌صدا از رویش رد می‌شود —
# یعنی همان سبزماندنی که این دروازه قرار بود جلویش را بگیرد.
_APP_NC = _py_nocomment(APP_PY)
for _k in ("SQL_PLAN_JOIN", "SQL_REAL_BUY"):
    _v = re.search(rf'{_k} = "([^"]+)"', APP_PY)
    if _v:
        _APP_NC = _APP_NC.replace("{" + _k + "}", _v.group(1))

# هر عبارتِ SQL که هم به `u.id` گره خورده و هم approved را می‌سنجد
_per_user = []
for _m in re.finditer(r"SELECT[^;]{0,400}?o\.user_id\s*=\s*u\.id[^;]{0,200}",
                      _APP_NC):
    _frag = _m.group(0)
    if "status='approved'" not in _frag:
        continue
    if "is_trial" in _frag:
        continue
    _line = _APP_NC[:_m.start()].count("\n") + 1
    _per_user.append(f"app.py:~{_line} — {' '.join(_frag.split())[:90]}")

check("هر کوئریِ «این کاربر خرید؟» تستِ رایگان را کنار می‌گذارد",
      not _per_user,
      f"{len(_per_user)} کوئری بدونِ فیلترِ تست" if _per_user
      else "همه از قاعده‌ی قیف رد می‌شوند")
if _per_user:
    bullets(_per_user)

# و خودِ قاعده یک تعریف داشته باشد، نه چند نسخه‌ی دستی
check("قاعده‌ی «خریدِ واقعی» یک‌جا تعریف شده",
      APP_PY.count('SQL_REAL_BUY = "') == 1
      and APP_PY.count("SQL_REAL_BUY") >= 5,
      f"{APP_PY.count('SQL_REAL_BUY')} مصرف‌کننده")


# ═══════════════════════════════════════════════════════════
#  درز — کفِ قیمتِ نماینده ↔ خودِ صورتحساب
# ═══════════════════════════════════════════════════════════
#
# برگه: docs/specs/2026-09-22-reseller-and-ui.md
#
# چرا دروازه شد: پرتال کف را خودش حساب می‌کرد — `cost[gb]`، یعنی
# **فقط حجم**. صورتحساب از `_line_amount` می‌آید که
# `(نرخ پایه + نرخ کاربر اضافه) × ماه` است.
#
# اندازه‌گیری‌شده با نرخ‌های نمونه:
#
#     ۳۰ گیگ /  ۹۰ روز / ۲ کاربر   ۶۰٬۰۰۰ نشان داده می‌شد،  ۲۲۵٬۰۰۰ بود
#     نامحدود / ۳۶۵ روز / ۱ کاربر  ۲۰۰٬۰۰۰ نشان داده می‌شد، ۲٬۴۰۰٬۰۰۰ بود
#
# یعنی نماینده «بالای کف» می‌فروخت و دوازده برابر ضرر می‌کرد، و فقط
# آخرِ ماه می‌فهمید.

if HAS_PRO_API:                       # the reseller portal is Pro (backend/pro/resellers.py)
    _PORTAL_JSX = rd("frontend", "src", "portal", "index.jsx")

    check("مسیرِ کفِ قیمت وجود دارد",
          '"/api/portal/plan-cost"' in APP_NS
          and "/api/portal/plan-cost" in _PORTAL_JSX,
          "دو سمتِ درز")

    # کف باید از همان تابعی بیاید که فاکتور را می‌سازد، نه ضربِ تازه.
    #
    # از ۱.۸۶ محاسبه در `_plan_floor` است — چون ذخیره‌ی پلن هم همان عدد
    # را لازم دارد (`plans.cost`) و دو محاسبه یعنی نماینده یک کف ببیند و
    # از اعتبارش کفِ دیگری کم شود. پس سه چیز سنجیده می‌شود: پیش‌نمایش
    # `_plan_floor` را صدا می‌زند، ذخیره هم، و خودِ `_plan_floor` از
    # توابعِ صورتحساب می‌خواند.
    def _fn(name):
        if f"def {name}(" not in APP_NS:
            return ""
        body = APP_NS.split(f"def {name}(")[1]
        m = re.search(r"\n(?:def |@app\.)", body)
        return body[:m.start()] if m else body


    _cost_fn = _fn("portal_plan_cost")
    _floor_fn = _fn("_plan_floor")
    _save_fn = _fn("portal_bot_plans_save")
    check("کف از _line_amount می‌آید، نه ضربِ تازه",
          "_plan_floor(" in _cost_fn
          and "_line_amount(" in _floor_fn and "_months_from_days(" in _floor_fn
          and "_price_with_reason(" in _floor_fn,
          "همان تابعی که صورتحساب از آن می‌خواند")
    check("پیش‌نمایش و ذخیره یک کف دارند",
          "_plan_floor(" in _save_fn and "_line_amount(" not in _save_fn,
          "کفی که نماینده می‌بیند همان است که از اعتبارش کم می‌شود")

    # و «نمی‌دانم» صفر برنگردد — صفر یعنی رایگان
    # جاروی شکستن: با برداشتنِ همین یک شاخه، دروازه‌ی قبلی سبز ماند
    # چون رشته‌ی `"ready": False` جای دیگری از همان تابع هم بود. حالا
    # خودِ شاخه سنجیده می‌شود، نه وجودِ یک رشته.
    _no_rate = ""
    if "    base, why = _price_with_reason(gb, rates)" in _floor_fn:
        _no_rate = _floor_fn.split(
            "    base, why = _price_with_reason(gb, rates)")[1].split(
            "\n    months =")[0]
    check("نبودِ نرخ صفر برنمی‌گرداند",
          "if base is None:" in _no_rate
          and '"ready": False' in _no_rate and '"why": why' in _no_rate
          and '"cost": 0' not in _floor_fn,
          "صفر یعنی «رایگان»، نه «نرخ ندارد»")

    # پرتال دیگر خودش ضرب نکند
    _bad = []
    for _m in re.finditer(r"policy\.(?:perGb|cost)\b[^\n]{0,60}", _PORTAL_JSX):
        _frag = _m.group(0)
        if "*" in _frag or "+" in _frag:
            _bad.append(" ".join(_frag.split())[:70])
    check("پرتال کفِ قیمت را خودش حساب نمی‌کند", not _bad,
          f"{len(_bad)} ضرب در JSX" if _bad else "از بکند می‌گیرد")
    if _bad:
        bullets(_bad)


# ═══════════════════════════════════════════════════════════
#  درز — فیلدِ مبلغ جداکننده دارد، فیلدِ غیرمبلغ ندارد
# ═══════════════════════════════════════════════════════════
#
# `MoneyInput` مقدارِ خام را به `onChange` می‌دهد، نه رشته‌ی
# جداکننده‌دار — وگرنه `Number(e.target.value)` در همه‌ی صداکننده‌ها
# `NaN` می‌شود.
_UI_JSX = rd("frontend", "src", "ui", "index.jsx")
_money_fn = _UI_JSX.split("export function MoneyInput(")[1] \
                   .split("\nexport function ")[0]
check("MoneyInput مقدارِ خام به صداکننده می‌دهد",
      "e.target.value = normalizeNumeric(" in _money_fn,
      "رشته‌ی جداکننده‌دار یعنی NaN در هر صداکننده")

#: فیلدهایی که عمداً جداکننده نمی‌گیرند — عدد نیستند یا بزرگ نمی‌شوند.
#: شماره‌ی کارت و شناسه‌ی تلگرام هر کدام یک‌بار همین اشتباه را
#: خورده‌اند.
_NOT_MONEY = re.compile(
    r"درصد|percent|pct|روز|days|گیگ|GB|حجم|کاربر|ip_limit|سکه|coin|"
    r"شماره|کارت|card|شناسه|tg_id|پورت|port|دقیقه|ساعت|ماه")
_MONEY_LBL = re.compile(r"قیمت|مبلغ|تومان|نرخ|اعتبار|شارژ")

_plain = []
for _rel in ("frontend/src/sections/billing.jsx",
             "frontend/src/sections/bot/plans.jsx",
             "frontend/src/sections/expenses.jsx",
             "frontend/src/sections/portal-admin.jsx",
             "frontend/src/portal/index.jsx"):
    if not exists(_rel):
        continue                        # a Pro screen; none in the Community tree
    _src = rd(*_rel.split("/"))
    _lines = _src.splitlines()
    for _i, _ln in enumerate(_lines):
        if "<NumberInput" not in _ln:
            continue
        _ctx = "\n".join(_lines[max(0, _i - 7):_i + 3])
        if _MONEY_LBL.search(_ctx) and not _NOT_MONEY.search(_ctx):
            _plain.append(f"{_rel.split('/')[-1]}:{_i + 1}")

check("هر فیلدِ مبلغ جداکننده دارد", not _plain,
      f"{len(_plain)} فیلدِ مبلغِ بی‌جداکننده" if _plain
      else "MoneyInput روی همه سوار است")
if _plain:
    bullets(_plain)


# ═══════════════════════════════════════════════════════════
#  درز — قفلِ پوسته‌ی نماینده
# ═══════════════════════════════════════════════════════════
#
# قاعده‌ی مخزن: اعتبارسنجی **در بکند**، نه فقط در رابط. رابط فقط
# راحتی است و کسی می‌تواند درخواست را مستقیم بفرستد — همان چیزی
# که برای حجم‌های مجازِ نماینده هم رعایت شد.

if HAS_PRO_API:                       # the reseller portal is Pro (backend/pro/resellers.py)
    # The lock lives in `_theme_save` (core: the owner's studio saves through
    # it too); the portal route must go through it. This check used to slice
    # portal_theme_set up to the next route, which only passed because
    # _theme_save happened to be defined right below it.
    _theme_set = APP_NS.split("def portal_theme_set(")[1].split("\n@app.")[0] \
        if "def portal_theme_set(" in APP_NS else ""
    _theme_sv = APP_NS.split("def _theme_save(")[1].split("\ndef ")[0] \
        if "def _theme_save(" in APP_NS else ""
    check("ذخیره‌ی پوسته در بکند قفل را می‌سنجد",
          "_theme_save(t, payload)" in _theme_set
          and "_addon_open(t)" in _theme_sv and "402" in _theme_sv,
          "رابط فقط راحتی است")

    # خریدِ هر افزونه (پوسته، اشتراکِ فروشگاه) از یک هسته رد می‌شود
    _buy = APP_NS.split("def _addon_buy(")[1].split("\ndef ")[0] \
        if "def _addon_buy(" in APP_NS else ""
    for _route in ("portal_theme_buy", "portal_store_buy"):
        _rb = APP_NS.split(f"def {_route}(")[1].split("\n@app.")[0] \
            if f"def {_route}(" in APP_NS else ""
        check(f"{_route} از هسته‌ی خرید رد می‌شود", "_addon_buy(" in _rb,
              "نسخه‌ی دومِ «کسر و تمدید» روزی یکی از دو قاعده را جا می‌اندازد")
    check("اول کسر، بعد تمدید",
          _buy.find("_portal_charge(") < _buy.find("_addon_extend(")
          and _buy.find("_portal_charge(") > 0,
          "برعکسش یعنی قابلیتی که پولش نرسیده باز می‌ماند")
    check("و اگر تمدید شکست خورد پول برمی‌گردد",
          "_portal_refund(" in _buy,
          "همان قاعده‌ی close_order در ربات")

# رنگ باید اعتبارسنجی شود — رنگِ خراب یعنی متنِ نامرئی، همان چیزی
# که یک‌بار در قالبِ «کیف پول» صفحه‌ی اشتراک افتاد
check("رنگ فقط #RRGGBB پذیرفته می‌شود",
      "_HEX_RE" in APP_PY and "def _clean_accent(" in APP_PY,
      "رنگِ نامعتبر یعنی متنِ نامرئی")

# قفل موقعِ *خواندن* هم سنجیده شود، نه فقط موقعِ نوشتن: اشتراکِ
# تمام‌شده باید رنگ را خاموش کند بی‌آنکه پاکش کند
# رنگ و پوسته از `_shop_brand` می‌آیند (مشترکِ `mini_me` و `mini_brand`)
if HAS_PRO_API:                       # the mini app is Pro (backend/pro/mini.py)
    _me = APP_NS.split("def mini_me(")[1].split("\n@app.")[0] \
        if "def mini_me(" in APP_NS else ""
    _sb = APP_NS.split("def _shop_brand(")[1].split("\n@app.")[0] \
        if "def _shop_brand(" in APP_NS else ""
    check("مینی‌اپ رنگ را فقط وقتی قفل باز است می‌گیرد",
          "_shop_brand(" in _me and "_addon_open(t)" in _sb,
          "اشتراکِ تمام‌شده رنگ را خاموش می‌کند، نه پاک")


# ═══════════════════════════════════════════════════════════
#  درز — یادآوری‌ها: یک متن، دو مقصد
# ═══════════════════════════════════════════════════════════
#
# مشتری‌ای که ربات را بلاک کرده یا نوتیفیکیشن را بسته، هیچ
# یادآوری‌ای نمی‌بیند و اولین خبرش قطع‌شدنِ اتصال است. صندوق همیشه
# هست.
#
# دو متنِ جدا یعنی روزی یکی‌شان اصلاح می‌شود و دیگری نه — و آن‌که
# فراموش می‌شود همانی است که مشتری می‌خواند.

check("تحویل و یادآوری‌ها در صندوق هم می‌نشینند",
      "_chat_copy(" in HANDLERS and "_chat_notice(" in HANDLERS,
      "بلاک‌کردنِ ربات نباید یعنی بی‌خبری")

for _fn, _hook in (("def deliver(", "_chat_copy("),
                   ("def send_expiry_notice(", "_chat_notice("),
                   ("def send_traffic_notice(", "_chat_notice(")):
    _body = HANDLERS.split(_fn)[1].split("\ndef ")[0] if _fn in HANDLERS else ""
    check(f"«{_fn[4:-1]}» هر دو مسیرش صندوق را پر می‌کند",
          _body.count(_hook) >= 2,
          f"{_body.count(_hook)} جا — متنِ سفارشی و متنِ پیش‌فرض")

# و متنِ صندوق از همان متنِ تلگرام ساخته شود، نه نسخه‌ی دوم
_copy = HANDLERS.split("def _chat_copy(")[1].split("\ndef ")[0] \
    if "def _chat_copy(" in HANDLERS else ""
check("متنِ صندوق از همان متنِ تلگرام می‌آید",
      "F.plain(" in _copy,
      "نسخه‌ی دوم یعنی روزی از هم دور می‌افتند")
check("و ثبتش تحویل را نمی‌شکند",
      "except Exception" in _copy,
      "از مسیرِ پول صدا زده می‌شود")


# ═══════════════════════════════════════════════════════════
#  درز — داده‌ی هارنس ↔ شکلِ واقعیِ پاسخِ بکند
# ═══════════════════════════════════════════════════════════
#
# چرا دروازه شد: ردیف‌های ساختگیِ سفارشِ پرتال `name` و `plan`
# می‌فرستادند، ولی بکند `customer` و `planName` می‌دهد. نتیجه:
# هر ردیف در هارنس «#۷۰۰ · » خالی نشان می‌داد و فیلترِ برگه‌ها هم
# اعمال نمی‌شد، پس سفارشِ تاییدشده در برگه‌ی «در انتظار» می‌نشست و
# چون دکمه‌ای ندارد **شبیهِ باگ** به نظر می‌رسید.
#
# یعنی داده‌ی ساختگیِ بدشکل دو کار می‌کند، هر دو بد: باگِ تقلبی
# می‌سازد، و باگِ واقعی را می‌پوشاند. `CLAUDE.md` درباره‌ی
# «واقع‌نما نگهش دار» هشدار داده بود؛ این‌جا اجرایش می‌کنیم.

_BOOT = rd("tests", "harness", "harness-boot.js")


def _return_keys(fn_name):
    """کلیدهای دیکشنریِ `return {...}`ِ یک مسیرِ بکند."""
    if f"def {fn_name}(" not in APP_PY:
        return set()
    body = APP_PY.split(f"def {fn_name}(")[1].split("\n@app.")[0]
    # آخرین `return {` که یک دیکشنریِ چندخطی است
    i = body.rfind("return {")
    if i < 0:
        return set()
    return set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)":', body[i:]))


def _mock_keys(var_name):
    """کلیدهای شیءِ ساختگی در harness-boot."""
    m = re.search(rf"{var_name}\s*=\s*\{{(.*?)\n\s*\}}", _BOOT, re.S)
    if not m:
        m = re.search(rf"{var_name}\s*=.*?return \{{(.*?)\n\s*\}};", _BOOT, re.S)
    if not m:
        return set()
    return set(re.findall(r"(?:^|[{,\s])([A-Za-z_][A-Za-z0-9_]*)\s*:", m.group(1)))


#: مسیرهایی که ردیفِ ساختگی دارند. فهرست کوتاه و عمدی است — هر
#: قلم یک جفتِ «تابعِ بکند ↔ متغیرِ هارنس» است که رابط ردیف‌به‌ردیف
#: می‌خواندش، پس نامِ کلیدها باید یکی باشد.
_SHAPES = [
    ("portal_orders", "P_ORDER_ROWS", {"id", "customer", "planName", "amount",
                                       "status", "kind", "paidFrom"}),
]

for _fn, _var, _must in _SHAPES:
    _mock = _mock_keys(_var)
    _missing = sorted(_must - _mock)
    check(f"ردیفِ ساختگیِ «{_var}» شکلِ بکند را دارد", not _missing,
          "، ".join(_missing) if _missing else f"{len(_mock)} کلید")
    if _missing:
        bullets([f"{k} — بکند می‌دهد، هارنس نه" for k in _missing])

# و فیلترِ برگه‌ها در هارنس واقعاً اعمال شود
check("هارنس فیلترِ وضعیتِ سفارش را اعمال می‌کند",
      "function portalOrders(" in _BOOT and "status=" in _BOOT,
      "وگرنه سفارشِ تاییدشده در برگه‌ی «در انتظار» بی‌دکمه می‌نشیند")

# داده‌ی خالی یعنی شاخه‌ی «هنوز چیزی نیست» و صفحه‌ی سالمِ دروغین
for _var, _why in (("M_ORDERS", "کارتِ سفارشِ در انتظارِ مینی‌اپ"),
                   ("EVENTS", "فهرستِ رویدادها")):
    _m = re.search(rf"var {_var}\s*=\s*(.{{0,40}})", _BOOT, re.S)
    _txt = _m.group(1) if _m else ""
    check(f"داده‌ی ساختگیِ «{_var}» خالی نیست",
          "[]" not in _txt.replace(" ", "")[:14],
          _why)

# بخشی از هارنس از خروجیِ واقعیِ بکند روی فیکسچرِ موقت ساخته می‌شود؛
# مسیرِ فایلِ موقت (C:\Users\<نام>\AppData\...، /tmp/...) همراهش می‌آمد
# و در صفحه‌ی تنظیماتِ حسابداری نشسته بود. مخزن عمومی است.
_leak = sorted(set(re.findall(r"[A-Za-z]:\\\\+Users\\\\+[^\\\"]+|/tmp/[\w.-]+|/home/[\w.-]+", _BOOT)))
check("هارنس مسیرِ دستگاهِ سازنده را ندارد", not _leak,
      "، ".join(_leak[:3]) if _leak else "")

# آی‌پیِ عمومیِ واقعی در کدِ محصول — فقط بازه‌های مستند (RFC 5737).
#
# نمونه‌ی `placeholder` در صفحه‌ی آی‌پی‌های بسته‌شده «91.99.12.4» بود و
# یک خطِ «خروجیِ واقعیِ ss» در تست، آدرسِ یک سرورِ واقعی را داشت. مخزن
# عمومی است. تست‌های شناساییِ شبکه (netid، intrusion) عمداً بیرون‌اند:
# برای سنجیدنِ «آی‌پیِ ایران» به بازه‌ی واقعیِ ایران نیاز دارند.
import glob as _glob
import ipaddress as _ipa
_DOC = [_ipa.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
_IP_OK = {"1.2.3.4", "1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9"}
_IP_RE = re.compile(r"(?<![\w.])((?:\d{1,3}\.){3}\d{1,3})(?![\w.])")
_J = lambda *a: os.path.join(ROOT, *a)
_prod = (_glob.glob(_J("frontend", "src", "**", "*.js*"), recursive=True)
         + _glob.glob(_J("backend", "*.py"))
         + [f for f in _glob.glob(_J("bot", "*.py"))
            if not os.path.basename(f).startswith("test_")]
         + _glob.glob(_J("*.sh"))
         + [_J("sub-page-index.html"), _J("tests", "harness", "harness-boot.js")])
_pub = []
for _f in _prod:
    try:
        _src = open(_f, encoding="utf-8").read()
    except OSError:
        continue
    for _m in _IP_RE.finditer(_src):
        try:
            _a = _ipa.ip_address(_m.group(1))
        except ValueError:
            continue
        if _a.is_global and _m.group(1) not in _IP_OK and not any(_a in _n for _n in _DOC):
            _pub.append(f"{os.path.relpath(_f, ROOT)}: {_m.group(1)}")
# ستون‌های tenants که بکند می‌خواند — در اسکیمای *واقعی*.
#
# هشدارِ سلامتِ سرور `SELECT bot_token, admin_id, group_id FROM tenants` بود؛
# آن دو ستون هرگز وجود نداشتند (`owner_tg_id`، `admin_group_id`). کوئری
# همیشه خطا می‌داد، `except: pass` می‌بلعید، و هیچ هشداری هرگز نرفت —
# سال‌ها بی‌نشانه. اسکیما از خودِ `init_db()` ساخته می‌شود، با همه‌ی
# مهاجرت‌ها، نه با خواندنِ متنِ CREATE.
import tempfile as _tf
import importlib as _il
import sqlite3 as _sq
_tmpdb = os.path.join(_tf.mkdtemp(prefix="nx-seams-"), "bot.db")
os.environ["BOT_DB_PATH"] = _tmpdb
sys.path.insert(0, ROOT)
from bot import db as _botdb  # noqa: E402
_il.reload(_botdb)
_botdb.init_db()
_c = _sq.connect(_tmpdb)
_tables = {r[0]: {x[1] for x in _c.execute(f"PRAGMA table_info({r[0]})")}
           for r in _c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
_c.close()
_tcols = _tables.get("tenants", set())

# همه‌ی جدول‌های ربات، در بکند و خودِ ربات. فقط کوئریِ تک‌جدولی (بی JOIN)
# سنجیده می‌شود — ستونِ با نامِ مستعار نیاز به تجزیه‌ی واقعیِ SQL دارد.
_bad_cols = []
for _label, _src in (("app.py", APP_PY), ("handlers.py", HANDLERS),
                     ("run.py", rd("bot", "run.py")), ("db.py", DB_PY)):
    for _node in ast.walk(ast.parse(_src)):
        _txt = None
        if isinstance(_node, ast.Constant) and isinstance(_node.value, str):
            _txt = _node.value
        elif isinstance(_node, ast.JoinedStr):
            _txt = "".join(v.value for v in _node.values
                           if isinstance(v, ast.Constant) and isinstance(v.value, str))
        if not _txt:
            continue
        _flat = " ".join(_txt.split())
        if re.search(r"\bJOIN\b", _flat, re.I):
            continue
        for _m in re.finditer(r"SELECT\s+(.+?)\s+FROM\s+(\w+)\b", _flat, re.I):
            _cols = _tables.get(_m.group(2))
            if _cols is None:
                continue
            for _col in _m.group(1).split(","):
                _w = _col.strip().split()[0] if _col.strip() else ""
                if re.fullmatch(r"[a-z_]+", _w) and _w != "distinct" and _w not in _cols:
                    _bad_cols.append(f"{_label}:{_node.lineno} {_m.group(2)}.{_w}")
        for _m in re.finditer(r"UPDATE\s+(\w+)\s+SET\s+([a-z_]+)\s*=", _flat, re.I):
            _cols = _tables.get(_m.group(1))
            if _cols is not None and _m.group(2) not in _cols:
                _bad_cols.append(f"{_label}:{_node.lineno} {_m.group(1)}.{_m.group(2)}")
check("هر ستونی که کوئری می‌خواند در اسکیمای واقعیِ ربات هست",
      len(_tcols) > 10 and len(_tables) > 10 and not _bad_cols,
      "، ".join(sorted(set(_bad_cols))[:5]) if _bad_cols else f"{len(_tables)} جدول")


# `except …: pass` در کدِ محصول — مسیرِ خرابِ بی‌صدا.
#
# هشدارِ سلامتِ سرور سال‌ها فرستاده نشد چون کوئری‌اش ستونِ ناموجود
# می‌خواند و `except Exception: pass` خطا را می‌بلعید. هیچ‌کس نفهمید.
# هر بلعیدن حالا یا لاگ می‌کند یا در این فهرست با دلیل آمده است.
# استثنای خودکار: بدنه‌ای که فقط import است، یا close/rollback داخلِ پاک‌سازی.
_SILENT_OK = {
    ("app.py", "_client_ip"): "آدرسِ نامعتبر در هدر یعنی نادیده‌گرفتنِ آن هدر",
    ("app.py", "_auth_failed"): "دیکشنریِ خالی — چیزی برای حذف نیست",
    ("core.py", "validate_discount"): "تاریخِ انقضای ناخوانا یعنی بی‌انقضا (قابلیتِ وصل‌نشده)",
    ("firewall.py", "tunnel_ports_in_use"): "خطی از خروجی که پورت ندارد",
    ("firewall.py", "block_refusal"): "آی‌پیِ محافظتِ نامعتبر — مقایسه معنا ندارد",
    ("monitor.py", "cpu"): "os.getloadavg روی ویندوز نیست",
    ("monitor.py", "_net_counters"): "خطِ سربرگ یا ناقصِ /proc/net/dev",
    ("health.py", "check_services"): "شمارِ ری‌استارتِ ناخوانا یعنی صفر",
    ("health.py", "check_ipv6"): "شکستِ اتصال *همان* نتیجه‌ی آزمونِ IPv6 است",
}
_silent = []
for _rel in ("backend/app.py", "backend/tunnels.py", "backend/firewall.py",
             "backend/intrusion.py", "backend/monitor.py", "backend/netid.py",
             "backend/fx.py", "backend/health.py",
             "bot/handlers.py", "bot/run.py", "bot/db.py", "bot/xui.py", "bot/core.py",
             "bot/tg.py"):
    _p = os.path.join(ROOT, *resolve(_rel).split("/"))
    if not os.path.exists(_p):
        continue
    _base = os.path.basename(_p)

    def _walk(node, fn):
        for _ch in ast.iter_child_nodes(node):
            _f = _ch.name if isinstance(_ch, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            if isinstance(_ch, ast.Try):
                for _h in _ch.handlers:
                    if len(_h.body) == 1 and isinstance(_h.body[0], ast.Pass):
                        _b0 = _ch.body[0]
                        if isinstance(_b0, (ast.Import, ast.ImportFrom)):
                            continue
                        if ast.unparse(_b0).endswith((".close()", ".rollback()")):
                            continue
                        if (_base, fn) in _SILENT_OK:
                            continue
                        _silent.append(f"{_rel}:{_h.lineno} ({fn})")
            _walk(_ch, _f)
    _walk(ast.parse(open(_p, encoding="utf-8").read()), "-")
check("هیچ `except: pass`ِ بی‌دلیلی در کدِ محصول نیست", not _silent,
      "، ".join(_silent[:5]) if _silent else f"{len(_SILENT_OK)} استثنای دلیل‌دار")


# لینکِ دعوتِ همکار دو جا ساخته می‌شود: منوی همکار در ربات، و بکند (پنلِ
# همکار و صفحه‌ی مالک). اگر یکی عوض شود، همکار دو لینکِ متفاوت می‌بیند و
# یکی‌شان مشتری را به نامِ او ثبت نمی‌کند.
def _aff_tpls(src):
    return {re.sub(r"\{[^}]*\}", "{}", m)
            for m in re.findall(r'f"(https://t\.me/\{[^}]+\}\?start=aff_\{[^}]+\})"', src)}
# Both builders are Pro since 2.0 (bot/pro/affiliates.py, backend/pro/affiliates.py).
if HAS_PRO_API:
    _bot_aff = _aff_tpls(rd("bot", "pro", "affiliates.py"))
    _be_aff = _aff_tpls(APP_NS)
    check("لینکِ همکار در ربات و بکند یک شکل دارد",
          len(_bot_aff) == 1 and _bot_aff == _be_aff,
          f"ربات {sorted(_bot_aff)} · بکند {sorted(_be_aff)}")


def _latin_money(src, label):
    """f-stringِ فارسی با `{x:,}` — مبلغِ لاتین وسطِ جمله‌ی فارسی."""
    _fa = re.compile(r"[؀-ۿ]")
    out = []
    for _fn in ast.walk(ast.parse(src)):
        if not isinstance(_fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        _body = ast.unparse(_fn)
        # PDF قاعده‌ی خودش را دارد (reportlab، `_fa`)؛ آن‌جا دست نمی‌زنیم
        if "pdf" in _fn.name.lower() or "drawString" in _body or "_fa(" in _body:
            continue
        for _n in ast.walk(_fn):
            if not isinstance(_n, ast.JoinedStr):
                continue
            _lit = "".join(v.value for v in _n.values
                           if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if not _fa.search(_lit):
                continue
            for _v in _n.values:
                if (isinstance(_v, ast.FormattedValue) and _v.format_spec is not None
                        and "," in ast.unparse(_v.format_spec)):
                    out.append(f"{label}:{_n.lineno}")
    return sorted(set(out))


# مبلغِ لاتین در پیامِ فارسی — «لازم 280,000 تومان». بکند `_fnum`، ربات
# `core.toman`. هر دو شکل پیش‌تر بی‌قاعده کنارِ هم بودند.
_lm = _latin_money(APP_PY, "backend/app.py") + _latin_money(HANDLERS, "bot/handlers.py")
check("مبلغ در پیامِ فارسی رقمِ فارسی دارد (_fnum / core.toman)", not _lm,
      "، ".join(_lm[:5]) if _lm else "")

check("کدِ محصول آی‌پیِ عمومیِ واقعی ندارد", not _pub,
      "، ".join(_pub[:3]) if _pub else f"{len(_prod)} فایل")


# ═══════════════════════════════════════════════════════════
#  درز — پلنِ رباتِ نماینده ↔ گروهِ x-ui
# ═══════════════════════════════════════════════════════════
#
# چرا دروازه شد: `_portal_gb_policy` → `_portal_rates` →
# `_portal_group`، و آن آخری وقتی گروه تعیین نشده ۴۰۹ می‌دهد. پس
# نماینده‌ای که مالک هنوز گروهش را نگذاشته بود **اصلاً نمی‌توانست
# پلن تعریف کند** — نه ویرایشگر باز می‌شد، نه ذخیره می‌شد — و
# پیامش «با پشتیبانی تماس بگیرید» بود.
#
# ولی پلنِ ربات یک ردیف در جدولِ `plans`ِ خودِ نماینده برای رباتِ
# خودش است. گروه فقط برای *کفِ قیمت* لازم است.
#
# و پنلِ خودِ مالک کارتی دارد که «بدون گروه» را می‌شمارد — یعنی این
# حالت عادی است، نه استثنا.

_RAISING = "_portal_group(t)"      # آن‌که ۴۰۹ می‌دهد
_SAFE = "_portal_group_opt(t)"     # آن‌که رشته‌ی خالی می‌دهد

check("کمکیِ «گروه، اگر بود» وجود دارد",
      "def _portal_group_opt(" in APP_PY,
      "بدونِ آن، هر مسیری که نرخ می‌خواند به گروه گره می‌خورد")

# نرخ‌ها نباید خودشان بمیرند
_rates_fn = APP_PY.split("def _portal_rates(")[1].split("\ndef ")[0]
check("خواندنِ نرخ بدونِ گروه خطا نمی‌دهد",
      _SAFE in _rates_fn and _RAISING not in _rates_fn,
      "فهرستِ خالی، نه ۴۰۹")

# و مسیرهای پلن نباید به آن برسند
for _fn in ("portal_bot_plans", "portal_bot_plans_save", "portal_plan_cost"):
    # A missing function is a failure here, not an empty body: the check
    # below is negative and would pass on nothing. (Pro: resellers.py.)
    if not HAS_PRO_API:
        continue
    if f"def {_fn}(" not in APP_NS:
        check(f"«{_fn}» exists", False, "renamed or moved: update this list")
        continue
    _body = APP_NS.split(f"def {_fn}(")[1].split("\n@app.")[0]
    check(f"«{_fn}» به گروه گره نخورده",
          _RAISING not in _body,
          "پلنِ ربات کانفیگ نیست")

# ولی قاعده‌ی امنیتی شل نشده باشد: کانفیگ‌ها همچنان گروه می‌خواهند
for _fn in ("portal_configs", "portal_summary"):
    # both Pro: resellers.py and accounting.py
    if not HAS_PRO_API:
        continue
    _body = (APP_NS.split(f"def {_fn}(")[1].split("\n@app.")[0]
             if f"def {_fn}(" in APP_NS else "")
    check(f"«{_fn}» همچنان گروه می‌خواهد",
          _RAISING in _body,
          "نماینده‌ی نیمه‌ساخته نباید کلِ مشتری‌ها را ببیند")

# و کفِ نامعلوم باید *دلیل* بدهد، نه صفر و نه انفجار
if HAS_PRO_API:                       # the reseller portal is Pro (backend/pro/resellers.py)
    _cost_body = (APP_NS.split("def portal_plan_cost(")[1].split("\n@app.")[0]
                  if "def portal_plan_cost(" in APP_NS else "")
    check("کفِ بی‌گروه دلیل می‌گوید",
          "گروه شما هنوز تعیین نشده" in _cost_body,
          "سکوت یعنی نماینده نمی‌داند چرا عددی نمی‌بیند")


# ═══════════════════════════════════════════════════════════
#  درز — انتخابِ قالب از داخلِ پیش‌نمایش
# ═══════════════════════════════════════════════════════════
#
# تا امروز حلقه این بود: قالب را عوض کن → ذخیره کن → برو
# پیش‌نمایش → ببین → برگرد. برای مقایسه‌ی چهار قالب یعنی چهار بار
# ذخیره روی تنظیماتِ واقعیِ مشتری‌ها.

_SYS = rd("frontend", "src", "sections", "system.jsx")

check("پیش‌نمایش قالب را به مسیر پاس می‌دهد",
      "template=${encodeURIComponent" in _SYS
      and "def preview_subpage(template" in APP_PY,
      "دو سمتِ درز")

# بازنویسی باید **فقط پیش‌نمایشی** باشد و از فهرستِ مجاز رد شود:
# مقدارش مستقیم داخلِ صفحه تزریق می‌شود
_prev = (APP_PY.split("def render_preview_html(")[1].split("\n@app.")[0]
         if "def render_preview_html(" in APP_PY else "")
check("قالبِ پیش‌نمایش از فهرستِ مجاز رد می‌شود",
      "PREVIEW_TEMPLATES" in _prev and "in PREVIEW_TEMPLATES" in _prev,
      "مقدار مستقیم در صفحه تزریق می‌شود")
check("و پالت هم الگو دارد",
      "fullmatch" in _prev,
      "هر رشته‌ای یعنی تزریقِ اسکریپت")

# پالت را همان تابعی حل کند که مسیرِ واقعی صدا می‌زند
check("پوسته‌ی پیش‌نمایش از resolve_theme می‌آید",
      "resolve_theme(" in _prev,
      "نگاشتِ دومِ «نام پالت → رنگ» یعنی روزی از هم دور می‌افتند")

# انتخابِ نهایی نباید کلِ تنظیمات را جایگزین کند
_pick = (APP_PY.split("def pick_theme(")[1].split("\n@app.")[0]
         if "def pick_theme(" in APP_PY else "")
check("انتخابِ قالب فقط دو کلید را عوض می‌کند",
      'cfg["template"]' in _pick and 'cfg["palette"]' in _pick
      and "load_config()" in _pick,
      "dictِ ناقص یعنی هر چه در آن نیست پاک می‌شود")
check("و شناسه‌ی ناشناس را رد می‌کند",
      "TEMPLATES" in _pick and "PALETTES" in _pick and "400" in _pick,
      "کلاسِ tpl-<ناشناس> یعنی چیدمانِ شکسته، بی‌صدا")

# صفحه‌ی مشتری باید بازنویسی را بشناسد، وگرنه انتخابگر بی‌اثر است
check("صفحه‌ی اشتراک بازنویسیِ پیش‌نمایش را می‌خواند",
      "NEXORA_FORCE_THEME" in rd("sub-page-index.html"),
      "بدونِ آن، نوار عوض می‌شود و صفحه نه")


# ═══════════════════════════════════════════════════════════
#  درز — نماینده هم مینی‌اپ دارد
# ═══════════════════════════════════════════════════════════
#
# دو چیز جلویش را گرفته بود و هر دو یک شکل داشتند: کوئری‌ای که
# `parent_id IS NULL` می‌گذاشت.
#
#   ۱. `_learn_panel_origin` آدرس را فقط روی ریشه می‌نوشت، پس
#      `miniapp_url(ctx)` برای نماینده خالی بود و دکمه‌ی مینی‌اپ در
#      رباتش **اصلاً ظاهر نمی‌شد**.
#   ۲. `_mini_tenants()` هم فقط ریشه را برمی‌گرداند، پس امضای
#      initData با توکنِ رباتِ نماینده سنجیده نمی‌شد و ۴۰۱ می‌گرفت.
#
# یعنی پوسته‌ی شخصیِ نماینده داشت مینی‌اپی را رنگ می‌کرد که برای او
# وجود نداشت.

def _root_only(body):
    """
    آیا این تابع خودش را به مستاجرِ ریشه محدود کرده؟

    فقط **فیلتر** مهم است. `ORDER BY parent_id IS NULL DESC` ترتیب
    است و کامنتی که باگِ قدیمی را توضیح می‌دهد هم فیلتر نیست —
    دروازه‌ای که به توضیح گیر کند، مجبورمان می‌کند توضیح را پاک
    کنیم.
    """
    # خط‌به‌خط، بدونِ `tokenize`.
    #
    # `_py_nocomment` روی یک قطعه‌ی تورفته‌ی وسطِ فایل در پایتون
    # ۳.۱۰ خطا می‌دهد و بی‌صدا متنِ خام را برمی‌گرداند — یعنی
    # کامنت‌ها می‌مانند و دروازه روی CI قرمز می‌شود و محلی سبز.
    for line in body.splitlines():
        bare = line.strip()
        if bare.startswith("#"):
            continue                      # توضیح، نه کد
        if "parent_id IS NULL" not in line:
            continue
        head = line[:line.index("parent_id IS NULL")].upper()
        if "ORDER BY" in head:
            continue                      # ترتیب، نه فیلتر
        return True
    return False


if HAS_PRO_API:                       # the mini app is Pro (backend/pro/mini.py)
    _mt = (APP_NS.split("def _mini_tenants(")[1].split("\ndef ")[0]
           if "def _mini_tenants(" in APP_NS else "")
    check("مینی‌اپ ربات نماینده را هم می‌شناسد",
          not _root_only(_mt) and "bot_token" in _mt,
          "وگرنه مشتریِ نماینده ۴۰۱ می‌گیرد")

_lp = (APP_PY.split("def _learn_panel_origin(")[1].split("\ndef ")[0]
       if "def _learn_panel_origin(" in APP_PY else "")
# شرط این است که **فقط ریشه** نباشد و روی ردیف‌ها حلقه بزند —
# نه اینکه `bot_token` را نام ببرد. آدرس بدونِ ربات هم نوشته
# می‌شود، تا لحظه‌ای که ربات وصل شد دکمه همان‌جا باشد.
check("آدرس مینی‌اپ برای همه‌ی مستاجرها نوشته می‌شود",
      not _root_only(_lp) and "for row in rows" in _lp,
      "وگرنه دکمه در رباتِ نماینده ظاهر نمی‌شود")

if HAS_PRO_API:                       # the reseller portal is Pro (backend/pro/resellers.py)
    _pb = (APP_NS.split("def portal_bot_set(")[1].split("\n@app.")[0]
           if "def portal_bot_set(" in APP_NS else "")
    # خودِ **انتساب** سنجیده می‌شود، نه وجودِ رشته: جاروی شکستن نشان
    # داد با برداشتنِ همین یک خط، «miniapp_url» هنوز در کامنت و در
    # شرطِ بالایش هست و دروازه سبز می‌ماند.
    check("نماینده‌ای که همین حالا ربات وصل می‌کند هم آدرس می‌گیرد",
          re.search(r'mine\[\s*"miniapp_url"\s*\]\s*=', _pb) is not None,
          "وگرنه منتظرِ بازشدنِ دوباره‌ی پنلِ مالک می‌ماند")

# و مینی‌اپ باید نامِ فروشگاهِ خودش را نشان بدهد
if os.path.exists(os.path.join(ROOT, "frontend", "src", "pro", "mini.jsx")):
    _MINI = rd("frontend", "src", "pro", "mini.jsx")
    check("عنوانِ مینی‌اپ نامِ همان فروشگاه است",
          "document.title = b" in _MINI,
          "«اشتراک من» یعنی مشتری نامِ فروشگاه را هیچ‌جا نمی‌بیند")


# ═══════════════════════════════════════════════════════════
#  درز — حالتِ خالی نباید بن‌بست باشد
# ═══════════════════════════════════════════════════════════
#
# ویرایشگرِ پلن وقتی هیچ پلنی نبود، `<>`ای را که دکمه‌های «پلن
# تازه» و «ذخیره» در آن بودند اصلاً رندر نمی‌کرد. یعنی **هر
# نماینده‌ی تازه** بن‌بست می‌خورد — دقیقاً همان «نماینده نمی‌تواند
# پلن تعریف کند».
#
# قاعده‌ی مخزن: «هر دکمه‌ای که نشان داده می‌شود باید کار کند» — و
# بدترین شکلش این است که دکمه اصلاً نشان داده نشود.

if HAS_PRO_API:                       # the reseller portal is Pro (backend/pro/resellers.py)
    _PORTAL = rd("frontend", "src", "portal", "index.jsx")
    _no_way = []
    for _m in re.finditer(r"<EmptyState\b[^>]*?/>", _PORTAL, re.S):
        _tag = _m.group(0)
        # فهرست‌هایی که کاربر می‌تواند پرشان کند باید راهِ جلو داشته باشند
        if "هنوز" in _tag and "action=" not in _tag:
            _line = _PORTAL[:_m.start()].count("\n") + 1
            _no_way.append(f"portal:{_line} — {' '.join(_tag.split())[:64]}")

    check("حالتِ خالیِ ویرایشگرها راهِ جلو دارد", not _no_way,
          f"{len(_no_way)} بن‌بست" if _no_way else "همه دکمه دارند")
    if _no_way:
        bullets(_no_way)


# ═══════════════════════════════════════════════════════════
#  درز — مسیرِ پول بی‌صدا رد نمی‌شود
# ═══════════════════════════════════════════════════════════
#
# قاعده‌ی اولِ `CLAUDE.md`: «مسیرِ خرابِ بی‌صدا ممنوع». تا امروز
# دروازه‌ای نداشت.
#
# پیدا شد در ممیزیِ خودِ همین جلسه: دو مسیرِ تمدید، اگر تاریخِ
# ذخیره‌شده خراب بود، بی‌سروصدا از «الان» شروع می‌کردند — یعنی
# نماینده‌ای که بیست روز اعتبار داشت پول می‌داد و همان بیست روز را
# از دست می‌داد، بدونِ هیچ ردی در هیچ لاگی.
#
# `except: pass` همه‌جا بد نیست؛ در مسیری که پول جابه‌جا می‌کند
# هست. پس دامنه محدود است به تابع‌هایی که خودشان پول کم یا زیاد
# می‌کنند.

# «پول» فقط کسر و واریز نیست: تاریخِ اشتراکی که بابتش پول داده شده
# هم همان است. جاروی شکستن نشان داد مسیرِ `grant` — که خودش پولی
# جابه‌جا نمی‌کند ولی روزهای پرداخت‌شده را عوض می‌کند — از دیدِ
# فهرستِ اول بیرون می‌ماند.
_MONEY_CALLS = ("_portal_charge(", "_portal_refund(",
                "spend_balance(", "close_order(", "credit = credit",
                "theme_until")

_silent = []
for _m in re.finditer(r"\ndef (\w+)\(", APP_PY):
    _fn = _m.group(1)
    _body = APP_PY[_m.end():]
    _nxt = re.search(r"\ndef \w+\(", _body)
    if _nxt:
        _body = _body[:_nxt.start()]
    if not any(c in _body for c in _MONEY_CALLS):
        continue
    # `except …: pass` بدونِ هیچ لاگی
    for _e in re.finditer(r"except [^\n]*:\n(?:[ \t]*#[^\n]*\n)*[ \t]*pass\b",
                          _body):
        _line = APP_PY[:_m.end() + _e.start()].count("\n") + 1
        _silent.append(f"{_fn} (app.py:~{_line})")

check("هیچ مسیرِ پولی بی‌صدا رد نمی‌شود", not _silent,
      f"{len(_silent)} جا" if _silent
      else "except بدونِ لاگ، در تابعی که پول جابه‌جا می‌کند")
if _silent:
    bullets(_silent)


# و آستانه‌ها واقعاً از تنظیمات بیایند، نه از ثابتِ ماژول
check("آستانه‌های یادآوری از تنظیمات خوانده می‌شوند",
      "def expiry_steps(" in _RUN_PY and "def traffic_pct(" in _RUN_PY
      and "for day, flag in steps" in _RUN_PY,
      "ثابتِ ماژول یعنی مالک نمی‌تواند عوضش کند")


# ═══════════════════════════════════════════════════════════
print(f"\n{D}{'─' * 54}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
if not _fail:
    print(f"  {D}هر دو سمت همه‌ی درزها با هم می‌خوانند{X}")
print()
sys.exit(1 if _fail else 0)
