#!/usr/bin/env python3
"""
سه باگی که کاربر دید و دیگر نباید برگردند.

۱. صفحه‌ی سیاه هنگام بستن آی‌پی
   FastAPI برای خطای اعتبارسنجی، detail را آرایه‌ای از آبجکت
   برمی‌گرداند. رندر مستقیم آن در JSX یعنی خطای React و از دست
   رفتن کل صفحه. هیچ detail خامی نباید به JSX برسد.

۲. «ناعدد» در حسابداری
   Number("متن").toLocaleString("fa-IR") در جاوااسکریپت رشته‌ی
   «ناعدد» می‌دهد. این کلمه هیچ معنایی برای کاربر ندارد.

۳. باکس‌های چسبیده
   فاصله فقط با کلاس دستی mb-4 می‌آمد و هرجا جا می‌افتاد،
   دو کارت به هم می‌چسبیدند.

اجرا:  python3 tests/test-ui-safety.py
"""
import io
import os
import re
import re as _re        # also bound inside the Pro-only mini section
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "frontend", "src")

G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")
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


def sources():
    for dirpath, _d, files in os.walk(SRC):
        for f in sorted(files):
            if f.endswith((".jsx", ".js")):
                p = os.path.join(dirpath, f)
                key = os.path.relpath(p, SRC).replace(os.sep, "/")
                yield key, io.open(p, encoding="utf-8").read()


ALL = dict(sources())
# Pro screens live in frontend/src/pro/ (docs/specs/2026-09-29-pro-split.md).
# In the full tree a missing one is an error, not an empty string: an empty
# string passed "no text-white in the mini app" for a file that had moved.
# The Community tree has none; its Pro checks are counted as skipped.
HAS_PRO_SRC = any(k.startswith("pro/") for k in ALL)
_PRO_SKIPPED = []


def pro_src(rel):
    if HAS_PRO_SRC:
        return ALL[rel]          # KeyError: the file moved; fix the test, not the check
    return None


def pro_check(name, rel, test, detail=""):
    src = pro_src(rel)
    if src is None:
        _PRO_SKIPPED.append(name)
    else:
        check(name, test(src), detail)
FMT = ALL.get("lib/format.js", "")
UI = ALL.get("ui/index.jsx", "")
APP = ALL.get("App.jsx", "")
CSS = io.open(os.path.join(SRC, "index.css"), encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════
head("۱ · صفحه‌ی سیاه هنگام خطای سرور")

check("errText تعریف شده", "export function errText" in FMT)
check("آرایه‌ی خطای FastAPI را مدیریت می‌کند", "Array.isArray(detail)" in FMT)
check("آبجکت تنها را هم مدیریت می‌کند", 'detail.msg || detail.message' in FMT)
check("loc را به نام فیلد تبدیل می‌کند", "d.loc" in FMT)

raw = []
for name, src in ALL.items():
    if name == "lib/format.js":
        continue
    for m in re.finditer(r'\b([a-z]\w*)\.detail\b', src):
        start = max(0, m.start() - 9)
        if "errText(" in src[start:m.start()]:
            continue
        # فیلدهای داده‌ای خودمان، نه پاسخ خطا
        line = src[src.rfind("\n", 0, m.start()) + 1:
                   src.find("\n", m.end())]
        if re.search(r'\bs\.detail\b', line) and "errText" not in line:
            continue
        raw.append(f"{name}: {line.strip()[:70]}")

check("هیچ detail خامی به JSX نمی‌رسد", not raw,
      f"{len(raw)} مورد" if raw else f"{len(ALL)} فایل بررسی شد")
for r in raw[:8]:
    print(f"      {Y}▸{X} {r}")

check("مرز خطا وجود دارد", "class ErrorBoundary" in UI)
check("getDerivedStateFromError دارد", "getDerivedStateFromError" in UI)
check("محتوای صفحه در مرز خطا پیچیده شده", "<ErrorBoundary" in APP)
check("با عوض‌شدن صفحه بازنشانی می‌شود", "ErrorBoundary key={active}" in APP,
      "وگرنه یک خطا تا رفرش روی همه‌ی صفحات می‌ماند")
check("مرز خطا راه بازگشت می‌دهد", "دوباره تلاش" in UI)
check("مرز خطا می‌گوید بقیه سالم است", "بقیه‌ی پنل سالم است" in UI)


head("۲ · «ناعدد»")

check("faNum مقدار خالی را خط تیره می‌کند",
      'n === null || n === undefined || n === ""' in FMT)
check("عدد نامتناهی هم خط تیره می‌شود", "Number.isFinite(n)" in FMT)
check("متن غیرعددی فقط رقم‌هایش فارسی می‌شود", "toFaDigits(s)" in FMT)
check("هیچ مسیری به toLocaleString روی NaN نمی‌رسد",
      "Number(n || 0).toLocaleString" not in FMT,
      "شکل قبلی که «ناعدد» می‌ساخت")

# کلمه نباید به‌عنوان متنِ نمایشی جایی بیاید. داخل توضیحِ کد
# اشکالی ندارد — همان‌جا دلیل وجود این تست نوشته شده.
def strip_comments(src):
    src = re.sub(r"/\*[\s\S]*?\*/", " ", src)
    return re.sub(r"^\s*//.*$", " ", src, flags=re.M)

hard = [n for n, s in ALL.items() if "ناعدد" in strip_comments(s)]
check("کلمه‌ی «ناعدد» به کاربر نشان داده نمی‌شود", not hard, str(hard))


head("۳ · فاصله‌ی باکس‌ها")

check("قاعده‌ی فاصله‌ی عمومی هست", ".fx-anim > * + *" in CSS,
      "هر دو عنصر هم‌سطح، نه فقط چند ترکیب مشخص")
check("از توکن فاصله استفاده می‌کند", "var(--space-4)" in CSS)
check("مقیاس فاصله تعریف شده",
      all(f"--space-{n}:" in CSS for n in (2, 3, 4, 6, 8)))
check("فقط فرزند مستقیم را می‌گیرد", ".fx-anim >" in CSS,
      "تا خانه‌های گرید که gap دارند دست‌نخورده بمانند")
check("دلیلش نوشته شده", "collapse" in CSS)


head("سلامت کلی رابط")

# هر فایلی که از یک کامپوننت استفاده می‌کند باید import کرده باشد
missing = []
for name, src in ALL.items():
    if not name.endswith(".jsx"):
        continue
    used = set(re.findall(r"<([A-Z]\w+)[\s/>]", src))
    declared = set(re.findall(r"(?:function|const|class)\s+([A-Z]\w+)", src))
    # <Icon /> که از پراپ یا destructure می‌آید: const { icon: Icon } = m
    declared |= set(re.findall(r"[:{]\s*([A-Z]\w+)\s*[,}=]", src))
    declared |= set(re.findall(r"const\s+([A-Z]\w+)\s*=", src))
    # destructure آرایه‌ای در map:  .map(([k, l, Ico, tag]) => ...)
    for m in re.finditer(r"\(\s*\[([^\]]*)\]\s*\)\s*=>", src):
        declared |= {x.strip() for x in m.group(1).split(",")
                     if re.fullmatch(r"[A-Z]\w*", x.strip())}
    imported = set()
    for m in re.finditer(r"import\s+\{([^}]*)\}\s+from", src):
        imported |= {x.strip().split(" as ")[-1] for x in m.group(1).split(",")}
    for m in re.finditer(r"import\s+(\w+)\s+from", src):
        imported.add(m.group(1))
    # React.Fragment و تگ‌های داخلی
    gap = used - declared - imported - {"React"}
    if gap:
        missing.append(f"{name}: {sorted(gap)}")

check("هر کامپوننتی که استفاده می‌شود import شده", not missing,
      f"{len(missing)} فایل" if missing else f"{len(ALL)} فایل")
for m in missing[:6]:
    print(f"      {Y}▸{X} {m}")

# هیچ فایلی نباید چیزی export کند که تعریف نکرده
broken = []
for name, src in ALL.items():
    for m in re.finditer(r"import\s+\{([^}]*)\}\s+from\s+[\"'](\.[^\"']+)[\"']",
                         src):
        names = [x.strip().split(" as ")[0] for x in m.group(1).split(",")
                 if x.strip()]
        target = os.path.normpath(os.path.join(
            os.path.dirname(name), m.group(2)))
        # خودِ مسیر هم یک گزینه است: وقتی import پسوند را صریح
        # نوشته باشد (`./lib/route.js`)، چسباندنِ پسوند دوباره
        # دنبال `route.js.js` می‌گشت و ماژولِ سالم را «پیدا نشد»
        # گزارش می‌کرد — یعنی یک هشدار دروغ که هشدارهای واقعی را
        # بی‌ارزش می‌کند.
        cand = [target, target + ".jsx", target + ".js",
                os.path.join(target, "index.jsx")]
        tsrc = next((ALL[c.replace(os.sep, "/")] for c in cand
                     if c.replace(os.sep, "/") in ALL), None)
        if tsrc is None:
            broken.append(f"{name}: ماژول {m.group(2)} پیدا نشد")
            continue
        for n2 in names:
            # `async` هم بینشان می‌نشیند: `export async function f()`
            # جاوااسکریپتِ درست است و بدون این، هر تابعِ async که
            # export شود «export نشده» گزارش می‌شد — یعنی یک هشدار
            # دروغ که هشدارهای واقعی را بی‌ارزش می‌کند.
            if not re.search(r"export\s+(?:async\s+)?"
                             r"(?:function|const|class|let|var)\s+"
                             + re.escape(n2) + r"\b", tsrc):
                broken.append(f"{name}: {n2} در {m.group(2)} export نشده")

check("هر import به یک export واقعی می‌رسد", not broken,
      f"{len(broken)} مورد" if broken else "")
for b in broken[:8]:
    print(f"      {Y}▸{X} {b}")



# ═══════════════════════════════════════════════════════════
head("CSS · دو قاعده نباید بی‌صدا همدیگر را پاک کنند")

# `.fx-card` و `.fx-kpi` روی یک عنصر با هم می‌آیند. اگر هر دو
# `::before` بسازند، هرکدام دیرتر در فایل بیاید دیگری را پاک
# می‌کند — بدون هیچ خطایی، فقط یک افکت که ناپدید می‌شود.
_PAIRS = [("fx-card", "fx-kpi"), ("fx-card", "fx-sk")]
_clash = []
for _a, _b in _PAIRS:
    for _pseudo in ("::before", "::after"):
        _ra = re.search(r"^\.%s%s\s*\{" % (_a, _pseudo), CSS, re.M)
        _rb = re.search(r"^\.%s%s\s*\{" % (_b, _pseudo), CSS, re.M)
        if _ra and _rb:
            _clash.append("%s + %s هر دو %s" % (_a, _b, _pseudo))
check("کلاس‌هایی که با هم می‌آیند، یک شبه‌عنصر را دو بار نمی‌سازند",
      not _clash, "، ".join(_clash) if _clash
      else "کارت از ::before، شاخص از ::after")

# و هر عنصری که شبه‌عنصرِ مطلق دارد باید خودش جایگاه داشته باشد،
# وگرنه آن شبه‌عنصر روی نزدیک‌ترین والدِ جایگاه‌دار می‌نشیند و کلِ
# صفحه را می‌گیرد
for _cls in ("fx-card", "fx-kpi"):
    _blk = re.search(r"^\.%s\s*\{([^}]*)\}" % _cls, CSS, re.M)
    _all = "".join(m.group(1) for m in
                   re.finditer(r"^\.%s\s*\{([^}]*)\}" % _cls, CSS, re.M))
    check("%s جایگاه دارد" % _cls,
          "position: relative" in _all or "position:relative" in _all,
          "شبه‌عنصرِ absolute بدون آن، از کارت بیرون می‌زند")



# ═══════════════════════════════════════════════════════════
head("حالت خالی · یک قاعده، یک جا")

# بیست جا همان شکل را دستی ساخته بودند — کارتِ نقطه‌چین، آیکونِ
# کم‌رنگ، یک جمله. یعنی بهترکردنِ کامپوننت مشترک هیچ‌کدامشان را عوض
# نمی‌کرد. همان باگی که این مخزن هشت بار دیده: یک قاعده، چند جا.
_hand = []
for _n, _s in ALL.items():
    if _n.endswith("ui/index.jsx"):
        continue
    for _m in re.finditer(r'className="fx-card p-\d+ text-center"[^>]*'
                          r'borderStyle: "dashed"', _s):
        _hand.append(f"{_n}:{_s[:_m.start()].count(chr(10)) + 1}")

check("هیچ حالت خالیِ دست‌سازی نمانده", not _hand,
      "، ".join(_hand[:4]) if _hand else "همه از EmptyState یا کلاس مشترک")

check("کامپوننت حالت خالی وجود دارد", "export function EmptyState" in UI)
check("و آیکونش داخل یک مربع می‌نشیند", "fx-empty-ico" in UI and ".fx-empty-ico" in CSS,
      "آیکونِ تنهای کم‌رنگ شبیه «چیزی بارگذاری نشد» بود")
check("و نبودنِ آیکون چیزی را نمی‌شکند", "Icon ? <Icon" in UI,
      "وگرنه «Element type is invalid» و سقوط همان بخش")

_users = [n for n, s in ALL.items() if "<EmptyState" in s]
# 14 files in the full tree; the Community tree has no Pro screens, and 12 of
# its own files use it (area 8).
check("و واقعاً همه‌جا استفاده می‌شود", len(_users) >= (14 if HAS_PRO_SRC else 10), f"{len(_users)} فایل")


head("چیدمان · کارتِ کوتاه تمام‌عرض نمی‌شود")

# سه صفحه یک ستون از کارت‌های ۹۷۰ پیکسلی بودند که هرکدام یک کادر
# سه‌خطی داشتند. اندازه‌گیری‌شده: متن‌های ربات ۲۳۲۴ پیکسل بلند.
check("گریدِ دوستونیِ مساوی تعریف شده", ".fx-g2-even" in CSS)
check("و روی موبایل یک‌ستونه می‌شود",
      re.search(r"@media \(max-width: 900px\)[^}]*\{[^}]*\.fx-g2-even", CSS, re.S) is not None
      or ".fx-g2-even { grid-template-columns: 1fr; }" in CSS)
# از ۱.۱۲۴ متن‌ها فهرست + ویرایشگرند، نه ۱۷ کادرِ کنارِ هم (برگه‌ی تراکم)
check("متن‌های ربات: فهرست و ویرایشگر با پیش‌نمایش",
      "tx-split" in ALL.get("sections/bot/texts.jsx", "")
      and "tgHtml" in ALL.get("sections/bot/texts.jsx", ""))
check("سوالات متداول هم", "fx-g2-even" in ALL.get("sections/subpage.jsx", ""))
# Side by side, 300 px cards. Since 2.0.1 wrapping rows whose last row
# stretches, so a lone last card no longer leaves half the row empty.
pro_check("و سرورهای تانل گرید گرفته‌اند", "pro/tunnel.jsx",
          lambda src: "fx-wrap-cards" in src
          and ".fx-wrap-cards > * { flex: 1 1 300px" in CSS)


# ═══════════════════════════════════════════════════════════
#  صفحه‌ی اشتراک — نوشتن روی عنصرِ ناموجود، کلِ تابع را می‌کشد
# ═══════════════════════════════════════════════════════════
#
# چرا دروازه شد: سلولِ «حجم کلی» به کارتِ بالا منتقل شد و
# `document.getElementById("title-limit").innerText = …` باقی ماند.
# نتیجه یک TypeError بود که **تمامِ خط‌های بعدِ خودش در همان تابع**
# را اجرا نکرد: هیچ برچسبی ترجمه نشد، هیچ عددی پر نشد، و صفحه در
# حالتِ صفر ماند — بدونِ هیچ پیامی به کاربر.
#
# خودِ همان فایل `setText()` را دارد و کامنتش می‌گوید «اگر عنصری
# نبود، به‌جای کرش بی‌سروصدا رد می‌شود». این دروازه فقط می‌سنجد که
# دسترسیِ مستقیم به عنصری که وجود ندارد نمانده باشد.

# ═══════════════════════════════════════════════════════════
#  برچسبِ سفید — مشتریِ نماینده نباید نامِ ما را ببیند
# ═══════════════════════════════════════════════════════════
#
# مالک: «نباید کاربر بفهمد از نکسورا دارد خریداری می‌کند».
#
# صفحه‌ی ورودِ مینی‌اپ دو چیز لو می‌داد: نشانِ نکسورا (چون
# `main.jsx` هیچ‌وقت لوگوی فروشگاه را پاس نمی‌داد) و کلمه‌ی
# «NEXORA» که مستقیم در `Splash` نوشته شده بود.

head("برچسبِ سفید · مینی‌اپِ نماینده")

_MAIN = io.open(os.path.join(ROOT, "frontend", "src", "main.jsx"),
                encoding="utf-8").read()
_MARK = io.open(os.path.join(ROOT, "frontend", "src", "lib", "mark.jsx"),
                encoding="utf-8").read()

check("اسپلشِ مینی‌اپ حالتِ خنثی دارد",
      'neutral={WHICH === "mini"}' in _MAIN,
      "وگرنه نشانِ ما را به مشتریِ نماینده نشان می‌دهد")

check("و لوگوی فروشگاه را پاس می‌دهد",
      "logo={(SHOP && SHOP.logo)" in _MAIN,
      "`NexoraMark` از قبل src می‌گرفت؛ کسی استفاده نمی‌کرد")

# کلمه‌ی NEXORA باید پشتِ شرط باشد، نه بی‌قید
_word = _MARK.split('className="nx-word"')[0][-260:] if 'nx-word' in _MARK else ""
check("کلمه‌ی NEXORA بی‌قید چاپ نمی‌شود",
      "!neutral" in _word,
      "روی مینی‌اپِ نماینده یا نامِ اوست یا هیچ")

check("نشانِ خنثی وجود دارد",
      "if (neutral) {" in _MARK,
      "«نمی‌دانم کیست» دلیلِ نشان‌دادنِ برندِ خودمان نیست")

# عنوانِ پنجره هم همین است — تلگرام بالای مینی‌اپ نشانش می‌دهد
check("عنوانِ پنجره برای مینی‌اپ نامِ ما نیست",
      'document.title = (SHOP && SHOP.brand) || "اشتراک من"' in _MAIN,
      "`index.html` یک عنوانِ مشترک برای هر چهار اپ دارد")

pro_check("و مینی‌اپ برند را برای دفعه‌ی بعد نگه می‌دارد", "pro/mini.jsx",
          lambda _MINIJS: "writeShop(" in _MINIJS and "localStorage.setItem" in ALL.get("lib/shopcache.js", ""),
          "بدونش هر بار اول یک صفحه‌ی بی‌نام دیده می‌شود")


# ═══════════════════════════════════════════════════════════
#  رنگِ فروشگاه به همه‌ی مینی‌اپ می‌رسد
# ═══════════════════════════════════════════════════════════
#
# مالک: «پوسته و رنگ اعمال نمی‌شود». اعمال می‌شد — به نصفِ صفحه.
# دکمه‌های اصلیِ مینی‌اپ `--cy` بودند و فقط `--accent` عوض می‌شد، چند
# رنگ هم ثابت در CSS نوشته شده بود، و متغیرها روی `.mn-app` می‌نشستند
# که پنجره‌های پورتال‌شده بیرونِ آن‌اند. خوانایی را `test-palette.cjs`
# روی کلِ چرخه‌ی رنگ می‌سنجد؛ این‌جا اینکه رنگ اصلاً برسد.

head("رنگِ فروشگاه · به همه‌ی مینی‌اپ می‌رسد")

_CSS_ALL = io.open(os.path.join(ROOT, "frontend", "src", "index.css"),
                   encoding="utf-8").read()
_MAIN_SRC = io.open(os.path.join(ROOT, "frontend", "src", "main.jsx"),
                    encoding="utf-8").read()
# استودیوی پوسته از ۱.۱۱۰ در portal/studio.jsx است (پنلِ مالک هم از آن
# استفاده می‌کند)؛ سنجش‌های «پرتال» هر دو فایل را می‌بینند.
# The portal is Pro since 2.0 (src/pro/portal/); None in the Community tree.
_PORTAL_SRC = ("".join(pro_src(f"pro/portal/{f}") for f in ("index.jsx", "studio.jsx"))
               if HAS_PRO_SRC else None)

# رنگ‌های ثابتِ برند در قاعده‌های مینی‌اپ و اسپلش
_FIXED = re.compile(r"#1F6FBF|#14B8A6|#2DD4BF|#5AA9E6|#04221E"
                    r"|rgba\(\s*45,\s*212,\s*191|rgba\(\s*90,\s*169,\s*230"
                    r"|rgba\(\s*43,\s*127,\s*214", re.I)
_stuck = []
for _m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _CSS_ALL):
    _sel = _m.group(1).strip().split("\n")[-1]
    if not re.search(r"\.mn-|\.nx-word|\.nx-retry", _sel):
        continue
    if _FIXED.search(_m.group(2)):
        _stuck.append(_sel[:50])
check("هیچ رنگِ ثابتِ برندی در مینی‌اپ و اسپلش نمانده",
      not _stuck, f"{len(_stuck)} قاعده" if _stuck else "همه از توکن")
if _stuck:
    for _x in _stuck[:8]:
        print(f"      ▸ {_x}")

# متنِ روی دکمه‌ی رنگی از پالت می‌آید، نه سیاهِ ثابت
_ink = []
for _m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _CSS_ALL):
    _sel, _body = _m.group(1).strip().split("\n")[-1], _m.group(2)
    if ".mn-" not in _sel and ".nx-retry" not in _sel:
        continue
    if re.search(r"background[^;]*var\(--(accent|cy)", _body) and \
            re.search(r"(?<![-a-z])color:\s*#(06090F|fff\b|FFFFFF)", _body):
        _ink.append(_sel[:50])
check("متنِ روی سطحِ رنگی از پالت می‌آید (on-accent/on-cy)",
      not _ink, f"{len(_ink)} قاعده" if _ink else "")
if _ink:
    for _x in _ink[:8]:
        print(f"      ▸ {_x}")

pro_check("مینی‌اپ پوسته را روی ریشه می‌گذارد، نه روی .mn-app", "pro/mini.jsx",
          lambda _MINI_SRC: "applyTheme(" in _MINI_SRC and "style={accentVars" not in _MINI_SRC,
          "پنجره‌های پورتال‌شده بیرونِ .mn-app‌اند")
pro_check("اسپلش هم پوسته‌ی کش‌شده را می‌گیرد (قالب و رنگ)", "pro/mini.jsx",
          lambda _MINI_SRC: "applyTheme(SHOP_THEME" in _MAIN_SRC and "theme: me?.theme" in _MINI_SRC)
# پیش‌نمایش **خودِ مینی‌اپ** است در قاب، نه ماکت. مالک: «فقط یک
# پیش‌نمایشِ خیلی عادی نمایش می‌دهد» — ماکتِ دست‌ساز فقط رنگِ دکمه را
# عوض می‌کرد. قاب با postMessage پوسته را می‌گیرد.
pro_check("پیش‌نمایشِ پرتال خودِ مینی‌اپ است، نه ماکت", "pro/portal/studio.jsx",
          lambda _s: 'src="/app?preview=1"' in _PORTAL_SRC and '"nx-preview"' in _PORTAL_SRC
          and "function ThemePreview" not in _PORTAL_SRC,
          "وگرنه نماینده چیزی می‌بیند که مشتری نمی‌بیند")
pro_check("و مینی‌اپ در پیش‌نمایش به سرور نمی‌زند", "pro/mini.jsx",
          lambda _MINI_SRC: "if (PREVIEW) return demoApi(" in _MINI_SRC)

# هر قالبِ غیرپیش‌فرض باید ساختار را عوض کند — نه فقط یک رنگ. اگر
# قالبی برای یکی از این‌ها چیزی نگوید، در همان بخش شبیهِ «شفق» است و
# نماینده فکر می‌کند قالب کامل عوض نشده.
_THEMES_JS = io.open(os.path.join(ROOT, "frontend", "src", "lib", "mini-themes.js"),
                     encoding="utf-8").read()
_tpl_ids = re.findall(r'\{ id: "([a-z]+)", fa:',
                      _THEMES_JS.split("export const MINI_PALETTES")[0])
_KEY_PARTS = (".mn-top", ".mn-tabs", ".mn-tab.on", ".mn-card-bal", ".mn-plan-btn", ".nx-")
_thin = []
for _t in _tpl_ids:
    if _t == "aurora":
        continue
    _rules = "\n".join(m.group(1) for m in re.finditer(
        r'html\[data-mn-tpl="' + _t + r'"\]\s*([^{]*)\{', _CSS_ALL))
    for _k in _KEY_PARTS:
        if _k not in _rules:
            _thin.append(f"{_t}: {_k}")
check("هر قالب نوار، زبانه، کارت، دکمه و صفحه‌ی ورود را عوض می‌کند",
      _tpl_ids and not _thin, ", ".join(_thin[:6]) if _thin else f"{len(_tpl_ids)} قالب")

_MARK = io.open(os.path.join(ROOT, "frontend", "src", "lib", "mark.jsx"), encoding="utf-8").read()
_shop_sp = _MARK[_MARK.index("function ShopSplash("):_MARK.index("export function Splash(")] \
    if "function ShopSplash(" in _MARK and "export function Splash(" in _MARK else ""
check("صفحه‌ی ورود لوگوی فروشگاه را با همان قاب نشان می‌دهد",
      "<ShopLogo src={logo} name={name} style={logoStyle}" in _shop_sp)
# مینی‌اپ اسپلشِ خودش را دارد و نه اسپلشِ نکسورا با لوگوی عوض‌شده:
# مدارِ دوّار و نوارِ سیاهِ پایینِ قالبِ bold از آن‌جا می‌آمد.
check("اسپلشِ مینی‌اپ اسپلشِ فروشگاه است، نه اسپلشِ پنل",
      re.search(r"if \(neutral\)\s*\{?\s*return\s*<ShopSplash", _MARK) is not None)

# فاصله‌ی حروف روی متنِ فارسی پیوندِ حروف را می‌شکند — «ف ر و ش گ ا ه».
# نامِ فروشگاه اغلب فارسی است، پس هیچ قاعده‌ی .nx-shop-name نباید بدهدش.
_shop_rules = [m.group(1) for m in re.finditer(
    r"\.nx-shop-name[^{]*\{([^}]*)\}", _CSS_ALL)]
check("نامِ فروشگاه در اسپلش letter-spacing ندارد (فارسی را از هم می‌پاشد)",
      _shop_rules and not any(re.search(r"letter-spacing\s*:(?!\s*0\s*(;|$))", r) for r in _shop_rules),
      f"{len(_shop_rules)} قاعده")

# پرتالِ نماینده: مالک گفت «نمودارِ خطی نگذار». خطِ روندِ کوچک
# (spark) در کارت‌ها همان بود.
if HAS_PRO_SRC:                 # the reseller portal is Pro (src/pro/portal/)
    _PORT = pro_src("pro/portal/index.jsx")
    _DASH = pro_src("pro/portal/dash.jsx")
    check("پرتالِ نماینده نمودارِ خطی ندارد",
          "spark" not in _PORT and "spark" not in _DASH and "<polyline" not in _DASH)
    check("خانه‌ی پرتال داشبوردِ تازه است",
          "<HomeDash " in _PORT and "function HomeDash(" in _DASH)
else:
    _PRO_SKIPPED.append('portal: no line chart, the new home dashboard')
# صفحه‌ی درون‌خطی کارتِ باریکِ وسطِ صفحه نیست — نصفِ صفحه خالی می‌ماند
if HAS_PRO_SRC:                 # the reseller portal is Pro (src/pro/portal/)
    _STUDIO = pro_src("pro/portal/studio.jsx")
    _frame = _STUDIO[_STUDIO.index("export function Frame("):_STUDIO.index("const ACCENTS")] \
        if "export function Frame(" in _STUDIO and "const ACCENTS" in _STUDIO else ""
else:
    _frame = ""
# روشن/تیره پیش از اولین رندر — وگرنه صفحه‌ی ورودِ مشتریِ پوسته‌ی
# روشن سیاه است و بعد ناگهان سفید می‌شود. و یک قاعده، نه دو: هر جا
# colorScheme خوانده شود جز tgScheme، دو پاسخِ متفاوت ممکن می‌شود.
_MAIN = ALL.get("main.jsx", "")
_boot = _MAIN[:_MAIN.index("function Booting(")] if "function Booting(" in _MAIN else ""
check("پوسته‌ی روشن/تیره پیش از صفحه‌ی ورود روی ریشه است", "markScheme(" in _boot)
pro_check("… و مینی‌اپ هم همان را صدا می‌زند", "pro/mini.jsx", lambda src: "markScheme(" in src)
_cs = [f for f, src in ALL.items() if "colorScheme" in src and f != "lib/mini-themes.js"]
check("colorScheme فقط در tgScheme خوانده می‌شود", not _cs, ", ".join(_cs))

# تاریخِ ISO که مستقیم رندر شود، میلادی است و در RTL وارونه هم خوانده
# می‌شود: «فعال تا 22-10-2026» در استودیوی پوسته همین بود. تاریخ برای
# کاربر از isoToJalaliLabel می‌گذرد؛ slice(0, 10) فقط برای API و نامِ فایل.
_isoraw = []
for _f, _src in ALL.items():
    if not _f.endswith(".jsx"):
        continue
    # هر شکلی از بریدنِ یک ستونِ تاریخ — `{x.slice(0, 10)}`، `?.slice(0, 16)`،
    # `.replace("T", " ").slice(0, 16)`، و داخلِ faNum(String(...)). نسخه‌ی
    # اولِ این دروازه فقط اولی را می‌شناخت و پنج جای دیگر از زیرش رد شدند.
    for _m in re.finditer(r"\{\s*(String\([^)]*\)|[\w.?]+)\.slice\(0,\s*10\)\s*\}"
                          r"|(_at|At|until|[dD]ate|newest)\b\s*\|?\|?[^;{}]{0,12}?\)?"
                          r"(\.replace\([^)]*\))?\??\.slice\(0,\s*(10|16|19)\)", _src):
        _line = _src[_src.rfind(chr(10), 0, _m.start()) + 1:_src.find(chr(10), _m.end())]
        if "isoToJalali" in _line or "toISOString" in _line or "dayKey" in _line:
            continue
        _isoraw.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
    # و خودِ ستونِ تاریخ، بی‌بریدن: `{v.at}`، `{snap.at}`، `{r.created_at}`.
    # نسخه‌ی دومِ این دروازه فقط بریدن را می‌شناخت و چهار جا از زیرش رد شد.
    for _m in re.finditer(r"\{\s*[\w]+\??\.(at|created_at|updated_at|createdAt|updatedAt|paid_at"
                          r"|expires_at|expiresAt|sent_at|last_seen|spent_at|spentAt|done_at|taken_at)\s*\}", _src):
        _ln = _src[_src.rfind(chr(10), 0, _m.start()) + 1:_src.find(chr(10), _m.end())]
        if "JalaliDate" in _ln or "value={" in _ln:
            continue      # مقدارِ انتخابگرِ تاریخ است، نه متنِ نمایش‌داده‌شده
        _isoraw.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
    # و داخلِ رشته‌ی قالبی: `همه‌ی اعداد از ${d.since} تا امروز` — دفترِ کل
    # «از 06-08-2026» نشان می‌داد، وارونه و میلادی
    for _m in re.finditer(r"\$\{\s*[\w]+\??\.(since|at|created_at|spent_at|paid_at|expires_at|until"
                          r"|periodStart|settledUntil|last_seen)\s*\}", _src):
        _isoraw.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
    # و ستونی که فقط `T`ش عوض شود: `{m.nextRun.replace("T", " ساعت ")}` —
    # بی‌بریدن و با نامی که در فهرستِ بالا نبود، از هر دو شکل رد شد و
    # «اجرای بعدی: 26-09-2026» را در مانیتورینگ نشان می‌داد.
    for _m in re.finditer(r"\{\s*[\w.?]+\.replace\(\s*[\"'/]T[\"'/]", _src):
        _isoraw.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
    # و با جایگزین: `{e.at || "—"}` — شکلی که `{e.at}` نبود و از هر دو رد شد؛
    # رویدادهای ربات روی سرور تاریخِ میلادیِ خام نشان می‌دادند چون داده‌ی
    # ساختگیِ هارنس از قبل شمسی نوشته شده بود.
    for _m in re.finditer(r"\{\s*[\w]+\??\.(at|created_at|updated_at|createdAt|updatedAt|paid_at|expires_at"
                          r"|expiresAt|sent_at|scheduled_at|last_seen)\s*(\|\||\?\?)", _src):
        _ln = _src[_src.rfind(chr(10), 0, _m.start()) + 1:_src.find(chr(10), _m.end())]
        if "JalaliDate" in _ln or "value={" in _ln:
            continue      # مقدارِ انتخابگرِ تاریخ است، نه متنِ نمایش‌داده‌شده
        _isoraw.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
check("هیچ تاریخِ میلادیِ خامی رندر نمی‌شود", not _isoraw, ", ".join(_isoraw[:5]))

# کلاسِ `fx-*` که در CSS تعریف نشده بی‌صدا هیچ اثری ندارد. `fx-btn-ghost`
# در سه صفحه (شش دکمه) بود و هرگز تعریف نشد: «فایروال» در مانیتورینگِ
# نودها، «تازه‌سازی» و «بستن» در تلاش برای نفوذ — همه متنِ بی‌ظاهر.
_CSS_ALL = "".join(io.open(os.path.join(dp, f), encoding="utf-8").read()
                   for dp, _d, fs in os.walk(SRC) for f in fs if f.endswith(".css"))
_fx_def = set(re.findall(r"\.(fx-[A-Za-z0-9_-]+)", _CSS_ALL))
_fx_miss = []
for _f, _src in ALL.items():
    for _m in re.finditer(r"""className=(?:"([^"]*)"|\{`([^`]*)`\})""", _src):
        _txt = re.sub(r"\$\{[^}]*\}", " ", _m.group(1) or _m.group(2) or "")
        for _c in re.findall(r"(?<![\w-])(fx-[A-Za-z0-9_-]+)", _txt):
            if _c not in _fx_def:
                _fx_miss.append(f"{_c} ({_f}:{_src[:_m.start()].count(chr(10)) + 1})")
check("هر کلاسِ fx-* که در JSX هست در CSS تعریف شده", not _fx_miss, ", ".join(_fx_miss[:5]))

# رمز در آدرس — `<img src=".../receipt/12?pw=${password}">` رمزِ مدیر را در
# لاگِ nginx، تاریخچه‌ی مرورگر و Referer می‌گذاشت. هر راز باید در هدر برود.
_urlsecret = []
# تنها استثنا: دستورِ نصبِ ایجنت. متنی است که مدیر یک‌بار روی خودِ نود
# اجرا می‌کند (curl … | bash) و مسیرِ نصب توکن را فقط از پارامتر می‌گیرد؛
# هیچ درخواستی از مرورگر با آن زده نمی‌شود.
_URL_OK = {("pro/tunnel.jsx", "/api/agent/install.sh?token=")}
for _f, _src in ALL.items():
    for _m in re.finditer(r"[?&](pw|pass|password|token|secret|key)=\$\{", _src):
        _ln = _src[_src.rfind(chr(10), 0, _m.start()) + 1:_src.find(chr(10), _m.end())]
        if any(_f == a and b in _ln for a, b in _URL_OK):
            continue
        _urlsecret.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
check("هیچ رازی در پارامترِ آدرس نیست (هدر، نه ?pw=)", not _urlsecret, ", ".join(_urlsecret[:5]))

# ستون‌های پرچمِ دیتابیس ۰/۱‌اند، نه true/false. `p.is_active !== false` برای ۰
# «روشن» می‌داد و پلنِ خاموش در پنل روشن دیده می‌شد.
_intflag = []
for _f, _src in ALL.items():
    for _m in re.finditer(r"\b(is_active|is_trial|is_blocked|is_active_sub)\s*!==\s*false", _src):
        _intflag.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
check("پرچمِ ۰/۱ دیتابیس با «!== false» سنجیده نمی‌شود", not _intflag, ", ".join(_intflag[:5]))

# لغوِ blob بلافاصله بعد از click دانلود را در فایرفاکس پیش از شروع می‌بُرد —
# پنج جا همین شکل را داشتند (بکاپ، صورتحساب، گزارش، خروجیِ آی‌پی‌ها)
_revoke = []
for _f, _src in ALL.items():
    for _m in re.finditer(r"\.click\(\);\s*\n\s*URL\.revokeObjectURL\(", _src):
        _revoke.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
check("blob بلافاصله بعد از click لغو نمی‌شود", not _revoke, ", ".join(_revoke[:5]))

# نوشتنی که پاسخش خوانده نمی‌شود — `await fetch(url, {method: "POST"})` بی‌آنکه
# نتیجه در متغیری بنشیند. پرداختِ واسطه، پرداختِ همکار و نرخِ گروه همین‌طور
# بودند: شکست پنجره را می‌بست و «ذخیره شد» به نظر می‌رسید.
# تنها استثنا: به‌روزرسانی — سرویس وسطِ درخواست ری‌استارت می‌شود.
_WRITE_OK = ("/api/admin/run-update",)
_unread = []
for _f, _src in ALL.items():
    if not _f.endswith(".jsx"):
        continue
    for _m in re.finditer(r'method:\s*"(POST|PUT|DELETE|PATCH)"', _src):
        _st = _src.rfind("fetch(", 0, _m.start())
        if _st < 0 or _m.start() - _st > 400:
            continue
        _pre = _src[max(0, _st - 40):_st]
        if not re.search(r"await\s*$", _pre) or re.search(r"=\s*await\s*$", _pre):
            continue
        if any(x in _src[_st:_m.start()] for x in _WRITE_OK):
            continue
        _unread.append(f"{_f}:{_src[:_st].count(chr(10)) + 1}")
check("پاسخِ هر نوشتن (POST/PUT/DELETE) خوانده می‌شود", not _unread, ", ".join(_unread[:5]))

# خواندنی که خطایش بلعیده می‌شود. کارتِ بازگردانی وقتی فهرستِ نسخه‌ها
# خوانده نمی‌شد می‌گفت «هنوز نسخه‌ای نیست»؛ قیف «هنوز داده‌ای نیست»؛ بررسیِ
# نسخه دستورِ نصب نشان می‌داد. دو شکل:
#   ۱) `catch { /* بی‌صدا */ }` یا catchِ خالی پشتِ یک fetch
#   ۲) `if (res.ok) setX(await res.json());` بدونِ else
# catchی که دلیلش را در کامنت می‌گوید («شبکه قطع بود — دفعه‌ی بعد»)
# تصمیم است، نه بلعیدن، و رد نمی‌شود.
_swallow = []
for _f, _src in ALL.items():
    if not _f.endswith(".jsx"):
        continue
    for _m in re.finditer(r"\bcatch\s*(?:\(\s*\w*\s*\))?\s*\{(\s*(?:/\*(.*?)\*/)?\s*)\}", _src):
        _why = (_m.group(2) or "").strip()
        if _why and _why not in ("بی‌صدا", ""):
            continue
        _try = _src.rfind("try", 0, _m.start())
        if _try < 0 or _m.start() - _try > 900 or "fetch(" not in _src[_try:_m.start()]:
            continue
        _swallow.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
    for _m in re.finditer(r"if\s*\((\w+)\.ok\)\s*set\w+\(await \1\.json\(\)\);(?!\s*else)", _src):
        _swallow.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1} (if ok بی‌else)")
    # ۳) `.then((r) => r.json())` — وضعیت را نمی‌سنجد، پس `{detail}`ِ خطا
    #    مثلِ داده در state می‌نشست. بیست‌وشش جا بود؛ جایش okJson است.
    #    هر دو شکل: `(r) => r.json()` و `r => r.json()`. دومی از زیرِ نسخه‌ی
    #    اولِ این دروازه رد شده بود (تنظیماتِ حسابداری، اتصالِ ربات).
    for _m in re.finditer(r"\.then\(\(?(\w+)\)?\s*=>\s*\1\.json\(\)\)", _src):
        _swallow.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1} (r.json بی‌سنجش — okJson)")
check("خطای خواندن بلعیده نمی‌شود (catchِ بی‌صدا، if-okِ بی‌else)",
      not _swallow, ", ".join(_swallow[:6]))

# نویسه‌ی کنترلیِ نامرئی در کدِ تست — `\b` که در heredocِ گیت‌بش به
# backspace تبدیل شد، همین دروازه‌ی بالا را بی‌صدا کور کرده بود: سبز
# می‌ماند در حالی که چهار تاریخِ میلادی از زیرش رد می‌شد.
_ctl = []
for _d in ("tools", os.path.join("frontend", "src")):
    for _dp, _dn, _fn in os.walk(os.path.join(ROOT, _d)):
        for _n in _fn:
            if _n.endswith((".py", ".js", ".cjs", ".jsx", ".css")):
                _t = io.open(os.path.join(_dp, _n), encoding="utf-8", errors="replace").read()
                if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", _t):
                    _ctl.append(_n)
check("هیچ نویسه‌ی کنترلیِ نامرئی در کد و تست نیست", not _ctl, ", ".join(_ctl[:5]))

# ستونِ «1fr» یعنی minmax(auto, 1fr): از کوچک‌ترین پهنای محتوایش تنگ‌تر
# نمی‌شود، پس یک فیلدِ بلند یا نامِ nowrap کلِ شبکه را از صفحه بیرون می‌داد
# — ممیزیِ خودکار روی ۳۲۰ تا ۳۶۰ پیکسل: سکه، کد تخفیف، پاپ‌آپ، متن‌ها،
# استودیو، و خانه‌ی مینی‌اپ (۵۷ پیکسل اسکرولِ افقی). هر مسیرِ fr در
# عمقِ صفر یا مستقیم داخلِ repeat() باید minmax(0, …) باشد.
def _bare_fr(val):
    i, stack, hits = 0, [], []
    while i < len(val):
        m = re.match(r"([a-z-]+)\(", val[i:])
        if m:
            stack.append(m.group(1)); i += len(m.group(0)); continue
        if val[i] == ")":
            stack and stack.pop(); i += 1; continue
        m = re.match(r"(\d*\.?\d+)fr\b", val[i:])
        prev = val[i - 1] if i else " "
        if m and not (prev.isalnum() or prev in ".-") and all(f == "repeat" for f in stack):
            hits.append(m.group(0))
        i += len(m.group(0)) if m else 1
    return hits
_frs = []
_CSSFR = io.open(os.path.join(ROOT, "frontend", "src", "index.css"), encoding="utf-8").read()
for _m in re.finditer(r"grid-template-columns:\s*([^;{}]+)", _CSSFR):
    if _bare_fr(_m.group(1)):
        _frs.append(f"index.css:{_CSSFR[:_m.start()].count(chr(10)) + 1} {_m.group(1).strip()[:40]}")
check("هیچ ستونِ شبکه‌ای «1fr» خام نیست (minmax(0, 1fr))", not _frs, ", ".join(_frs[:4]))

# ظاهرِ فروشگاه از اولین فریم — مالک: «اول صفحه‌ی خودِ نکسورا می‌آید،
# بعد شخصی‌سازی». سه دلیل داشت و هر سه این‌جا سنجیده می‌شوند:
#   ۱. اپ پیش از رسیدنِ /api/mini/me با رنگِ پیش‌فرض بالا می‌آمد؛
#   ۲. applyTheme(null) در همان فاصله پوسته‌ی کش‌شده را پاک می‌کرد؛
#   ۳. کلیدِ کش برای همه‌ی فروشگاه‌ها یکی بود.
pro_check("مینی‌اپ تا رسیدنِ فروشگاه پشتِ اسپلشِ خودش می‌ماند", "pro/mini.jsx",
          lambda _MINI: "if (!PREVIEW && !me && !err)" in _MINI
          and re.search(r"useLayoutEffect\(\(\) => \{\s*(//[^\n]*\n\s*)*if \(!PREVIEW && !me\) return", _MINI) is not None)
_rawkey = [f for f, src in ALL.items() if f != "lib/shopcache.js" and '"nx_shop' in src]
check("کشِ ظاهرِ فروشگاه یک کلید دارد و برای هر فروشگاه جداست",
      not _rawkey, ", ".join(_rawkey) or "شناسه‌ی آدرس را test-admin-api با صدا زدنِ miniapp_url می‌سنجد")
check("صفحه‌ی اشتراک تا نشستنِ ظاهرِ فروشگاه محتوا را نشان نمی‌دهد",
      all(x in io.open(os.path.join(ROOT, "sub-page-index.html"), encoding="utf-8").read()
          for x in ("classList.add('nx-boot')", "bootDone()", "nx_subcfg:")))

# پلِ تلگرام فقط برای مینی‌اپ — telegram.org بدونِ VPN فیلتر است و
# <script src> هم‌زمان در <head> پنلِ مدیر و نماینده را تا timeout سفید
# نگه می‌داشت.
_IDX = io.open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
check("اسکریپتِ تلگرام هم‌زمان برای همه‌ی اپ‌ها بار نمی‌شود",
      re.search(r'^\s*<script\s+src="https://telegram\.org', _IDX, re.M) is None
      and "onApp" in _IDX and "preview=1" in _IDX)
# و پیش‌نمایشِ استودیو، که حالا بی‌SDK بار می‌شود، نباید به دیوارِ «باید
# از داخل تلگرام باز شود» بخورد — نسخه‌ی اولِ همین اصلاح قابِ پیش‌نمایش را
# دقیقاً همین‌طور خالی کرد.
pro_check("پیش‌نمایشِ مینی‌اپ بی‌تلگرام هم بالا می‌آید", "pro/mini.jsx",
          lambda src: re.search(r"if \(!tg\(\) && !PREVIEW\)", src) is not None)

# آلفای هگز که به یک متغیر چسبانده شود (`${c}99`) فقط روی رنگِ هگزِ خام
# درست است. رنگ‌های پنل از توکن‌اند، پس `var(--ok)99` می‌شود — نامعتبر،
# و مرورگر بی‌صدا کلِ background را دور می‌ریزد. نوارهای قیفِ «آمار و
# قیف» به همین دلیل روی سرورِ واقعی خالی بودند. فقط انتخاب‌گرهای رنگ،
# که مقدارشان هگزِ خودِ داده است، مستثنا‌اند.
_hexa = []
for _f, _src in ALL.items():
    if not _f.endswith(".jsx") or _f.endswith(("sections/bot/themes.jsx", "sections/subpage.jsx")):
        continue
    for _m in re.finditer(r"\$\{[\w.]+\}[0-9A-Fa-f]{2}(?![0-9A-Za-z])", _src):
        _hexa.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
check("هیچ آلفای هگزی به رنگِ متغیر چسبانده نمی‌شود", not _hexa, ", ".join(_hexa[:5]))

# ستون‌های صفر/یکِ SQLite (is_trial، is_active) عدد می‌رسند نه بولی، و
# `{r.is_trial && …}` در React خودِ «0» را چاپ می‌کند. کنارِ نامِ هر
# پلنِ پولیِ نماینده یک صفرِ تنها نشسته بود و هیچ‌کس نپرسید چیست.
_zero = []
for _f, _src in ALL.items():
    for _m in re.finditer(r"\{\s*[\w.?]*\b(is_trial|is_active)\s*&&", _src):
        _zero.append(f"{_f}:{_src[:_m.start()].count(chr(10)) + 1}")
check("ستونِ صفر/یک مستقیم با && رندر نمی‌شود (صفر چاپ می‌شود)", not _zero,
      ", ".join(_zero[:5]))

if HAS_PRO_SRC:                 # the reseller portal is Pro (src/pro/portal/)
    check("صفحه‌های پرتال تمام‌عرض‌اند، نه کارتِ شناورِ باریک",
          'className="nx-page"' in _frame and "width + 220" not in _frame)
else:
    _PRO_SKIPPED.append('portal: full-width pages')

# هر توکنِ پالت در :root پیش‌فرض دارد — وگرنه بدونِ رنگِ نماینده شفاف می‌شود
_ROOT_TOK = set(re.findall(r"^\s*(--[a-z0-9-]+)\s*:", _CSS_ALL.split(":root")[1].split("}")[0], re.M))
_PAL_KEYS = ["--accent-2s", "--accent-deep", "--cy-2", "--cy-rgb", "--on-accent",
             "--on-accent-hi", "--on-cy", "--accent-rgb", "--cy-edge"]
_miss = [k for k in _PAL_KEYS if k not in _ROOT_TOK]
check("هر توکنِ پالت پیش‌فرض دارد", not _miss, ", ".join(_miss))


head("صفحه‌ی اشتراک · دسترسیِ مستقیم به عنصر")

_SUBHTML = io.open(os.path.join(ROOT, "sub-page-index.html"),
                   encoding="utf-8").read()
_sub_ids = set(re.findall(r'id="([^"]+)"', _SUBHTML))
_direct = re.findall(r'getElementById\(\s*"([^"]+)"\s*\)\s*\.\s*\w+\s*=',
                     _SUBHTML)
_ghost = sorted({i for i in _direct if i not in _sub_ids})

check("هر نوشتنِ مستقیم، عنصرِ واقعی دارد", not _ghost,
      "، ".join(_ghost) if _ghost
      else f"{len(_direct)} دسترسی روی {len(_sub_ids)} شناسه")

# و شبکه‌ی آمار باید با ستون‌هایش جور باشد، وگرنه ردیفِ آخر
# سلولِ خالی می‌گیرد — همان حفره‌ای که مالک در اسکرین‌شات نشان داد
_cells = _SUBHTML.count('class="stat-cell"')
_m = re.search(r"\.stats-card \{[^}]*grid-template-columns: repeat\((\d+)",
               _SUBHTML, re.S)
_cols = int(_m.group(1)) if _m else 0
check("شبکه‌ی آمار جای خالی نمی‌گذارد",
      _cols > 0 and _cells % _cols == 0,
      f"{_cells} سلول در {_cols} ستون")

print(f"\n{D}{'─' * 46}{X}")
# ═══════════════════════════════════════════════════════════
head("فهرست بلند باید صفحه‌بندی شود، نه اینکه همه‌اش ریخته شود")

# سرور ایران نزدیک هشتصد سوکت باز دارد. کارت «پورت‌های باز» دو راه
# داشت که هر دو کل فهرست را یک‌جا می‌ریختند: با فیلتر فعال هیچ سقفی
# نبود، و دکمه‌ی «نمایش همه‌ی N پورت» هم همه را باز می‌کرد. نتیجه یک
# جدول هشتصد ردیفی در یک کارت بود.
#
# LongList صفحه‌بندی عددی دارد — همان چیزی که لازم است — ولی این
# کارت از آن استفاده نمی‌کرد.

MON = io.open(os.path.join(ROOT, "frontend", "src", "sections",
                           "monitoring.jsx"), encoding="utf-8").read()
_ports = MON[MON.index("export function PortsCard"):]
_ports = _ports[:_ports.index("\nexport function")]

check("کارت پورت‌ها صفحه‌بندی دارد", "<LongList" in _ports,
      "همان کامپوننتی که بقیه‌ی فهرست‌های بلند استفاده می‌کنند")
# دنبال خودِ دکمه می‌گردیم، نه متن — وگرنه توضیحِ همین اصلاح هم
# به‌عنوان دکمه شمرده می‌شود
check("و دکمه‌ی «نمایش همه» ندارد",
      "faNum(ports.length)} پورت" not in _ports,
      "«نمایش بیشتر» فهرست را بلندتر می‌کند — دقیقاً همان مشکل")
check("کارت مشتری‌ها هم صفحه‌بندی شد",
      "نمایش همه‌ی ${faNum(d.clients.length)} مشتری" not in MON
      and "items={list} initial={6}" in MON,
      "فهرست مشتری‌ها با رشد کسب‌وکار بلندتر می‌شد")
check("و حالتِ all جایی نمانده", "const [all, setAll]" not in MON,
      "وضعیتی که دیگر خوانده نمی‌شود فقط گمراه‌کننده است")
check("و حالتِ بی‌سقف هم ندارد",
      "setAll" not in _ports and "const [all," not in _ports)
check("پرخطرها هنوز اول می‌آیند",
      "[...risky, ...low]" in _ports,
      "صفحه‌ی اول باید همان چیزی باشد که باید به آن رسیدگی شود")

UI = io.open(os.path.join(ROOT, "frontend", "src", "ui", "index.jsx"),
             encoding="utf-8").read()
check("LongList می‌تواند ظرف دلخواه بگیرد", "container" in UI,
      "ردیف جدول باید داخل tbody بنشیند، نه داخل div")
check("و صفحه‌بندی‌اش عددی است", "Pager page={cur}" in UI)

# هر فهرستی که از داده‌ی سرور می‌آید و مستقیم map می‌شود، بالقوه
# بی‌سقف است. این‌ها را می‌شماریم تا کارت تازه‌ای همان اشتباه را
# تکرار نکند.
_unbounded = []
for _name in ("sec.processes", "sec.services", "conn.byIp"):
    if f"{_name}.map(" in MON:
        _unbounded.append(_name)
pro_check("جدول قاعده‌های فایروال هم صفحه‌بندی شد", "pro/firewall.jsx",
          lambda FW: "items={rules} initial={12}" in FW and "rules.map(" not in FW,
          "روی سروری با ده‌ها قاعده، جدول تا ته صفحه می‌رفت")
pro_check("جدول تلاش‌های نفوذ صفحه‌بندی دارد", "pro/intrusion.jsx",
          lambda INT: "usePager(shown, 15)" in INT)

check("فهرست‌های بلندِ دیگر هم مستقیم map نمی‌شوند", not _unbounded,
      "، ".join(_unbounded) if _unbounded else "همه از LongList رد می‌شوند")

# پنل نماینده اپلیکیشن جداست و از این اسکن بیرون می‌ماند — و دقیقاً
# به همین دلیل، جدول کانفیگ‌هایش تا امروز همه‌ی ردیف‌ها را یک‌جا
# می‌ریخت. نماینده‌ای با صدها کانفیگ صفحه‌ای می‌دید که ته نداشت.
if HAS_PRO_SRC:                 # the reseller portal is Pro (src/pro/portal/)
    PORTAL = pro_src("pro/portal/index.jsx")
    check("پنل نماینده هم خوانده شد", len(PORTAL) > 1000, f"{len(PORTAL)} نویسه")
    # ادعا روی همان جدول، نه روی هر map در فایل: فهرست پلن‌های ربات
    # کوتاه و کران‌دار است و صفحه‌بندی‌اش بی‌معنی.
    _dash = PORTAL[PORTAL.index("function Dashboard("):] if "function Dashboard(" in PORTAL else ""
    check("جدول کانفیگ‌های نماینده صفحه‌بندی دارد",
          "usePager(rows, 15)" in _dash and "{pageRows.map(" in _dash
          and "{rows.map(" not in _dash,
          "باید برشِ صفحه را map کند، نه کل فهرست را")
    check("و کنترل صفحه‌بندی هم رندر می‌شود", "{pager}" in PORTAL)
    check("فهرست سفارش‌های نماینده هم صفحه‌بندی دارد",
          "usePager(rows || [], 12)" in PORTAL and "{ordersPager}" in PORTAL,
          "سفارش‌ها با گذر زمان بی‌سقف می‌شوند")
    check("و بریده‌شدنِ فهرست بی‌صدا نمی‌ماند", "truncated" in PORTAL,
          "نماینده نباید فکر کند همین‌ها همه‌ی سفارش‌هایش است")
    check("فیلتر وضعیت هم دارد", "const FILTERS" in PORTAL and "passes(c)" in PORTAL,
          "جست‌وجوی نام به‌تنهایی «کدام‌ها رو به اتمام‌اند» را جواب نمی‌دهد")
else:
    _PRO_SKIPPED.append('portal: tables are paged and filtered')


# ═══════════════════════════════════════════════════════════
head("جعبه‌ی راهنما نباید به چیزِ زیرش بچسبد")

# InfoBox فقط mt-4 داشت و هیچ فاصله‌ای از پایین. اندازه‌گیری روی
# صفحه‌ی زنده: صفر پیکسل تا عنصر بعدی. و این کامپوننت بیش از صد بار
# در نوزده صفحه به کار رفته، پس همه‌جا همین‌طور بود.
#
# last:mb-0 برای وقتی است که آخرین عنصرِ یک کارت باشد — آن‌جا فاصله‌ی
# پایین فقط فضای خالیِ اضافه می‌سازد، که خودش ایراد دیگری است.
_ib = UI[UI.index("export function InfoBox("):]
_ib = _ib[:_ib.index("export function", 10)]
check("InfoBox از بالا و پایین فاصله دارد", "my-4" in _ib,
      "با mt-4 تنها، هر چیزی که زیرش بیاید چسبیده است")
check("و وقتی آخرین عنصر است فاصله‌ی اضافه نمی‌گذارد",
      "last:mb-0" in _ib, "وگرنه ته کارت فضای خالی می‌ماند")


# ═══════════════════════════════════════════════════════════
head("فرمِ باز‌شونده نباید داخل ردیفِ دکمه‌ها بنشیند")

# فرمِ «نماینده‌ی جدید» داخل یک ردیفِ flex justify-between رندر
# می‌شد که برای دکمه‌هاست. نتیجه: فرم فقط یک ستون از عرض را
# می‌گرفت و کنارش یک ستونِ خالیِ بزرگ می‌ماند.
def _btn_row_of(_pa2):
    _row = _pa2[_pa2.index('className="flex justify-between items-center gap-2 mb-3 flex-wrap"'):]
    return _row[:_row.index("</div>")]


pro_check("فرم داخل ردیفِ دکمه‌ها نیست", "pro/portal-admin.jsx",
          lambda _pa2: "<NewReseller" not in _btn_row_of(_pa2),
          "ردیفِ flex عرض را می‌شکند و کنارش خالی می‌ماند")
pro_check("و بیرون از آن، تمام‌عرض رندر می‌شود", "pro/portal-admin.jsx",
          lambda _pa2: "{adding && (" in _pa2 and "<NewReseller" in _pa2)


# ═══════════════════════════════════════════════════════════
head("مقدارِ ثبت‌شده نباید از منوی انتخاب غیب شود")

# فهرست گروه‌ها از x-ui می‌آید. اگر گروهِ ثبت‌شده‌ی یک نماینده در آن
# فهرست نباشد — پنل در دسترس نباشد، یا گروه در x-ui عوض شده باشد —
# select مقدارِ بی‌گزینه را نشان نمی‌دهد و روی «انتخاب کنید»
# می‌افتد. یعنی نماینده‌ای که گروه دارد «بدون گروه» دیده می‌شود، و
# کافی است پنل یک لحظه قطع باشد تا همه‌ی نماینده‌ها همین‌طور شوند.
pro_check("صفحه‌ی نمایندگی خوانده شد", "pro/portal-admin.jsx",
          lambda PADM: len(PADM) > 1000)
pro_check("گروهِ ثبت‌شده حتی بیرون از فهرست هم گزینه می‌شود", "pro/portal-admin.jsx",
          lambda PADM: "!(groups || []).includes(group)" in PADM
          and "<option value={group}>" in PADM,
          "وگرنه select روی «انتخاب کنید» می‌افتد و صفحه دروغ می‌گوید")


# ═══════════════════════════════════════════════════════════
head("یک بخش نباید دو بار رندر شود")

# اسکریپتِ وصله روی ("App.jsx", "app.jsx") حلقه زد. ویندوز به بزرگی
# و کوچکی حروف حساس نیست، پس هر دو یک فایل بودند و خطِ مسیر دو بار
# اضافه شد — صفحه‌ی اینباند نماینده‌ها دو بار پشت سر هم رندر می‌شد.
_routes = re.findall(r'\{active === "([a-z0-9-]+)" &&', APP)
_dupe = sorted({k for k in _routes if _routes.count(k) > 1})
check("هیچ مسیری دو بار وصل نشده", not _dupe,
      "، ".join(_dupe) if _dupe else f"{len(_routes)} مسیر، همه یکتا")


# ═══════════════════════════════════════════════════════════
head("متن فارسی داخل فیلدِ چپ‌به‌راست دیده نمی‌شود")

# روی input، جهت از *مقدار* گرفته می‌شود نه placeholder — پس فیلدی
# که dir="ltr" دارد، placeholder فارسی‌اش را چپ‌به‌راست می‌چیند. و
# فونت mono هم حرف فارسی ندارد.
#
# قاعده‌ی خودِ مخزن در بیشتر جاها رعایت شده: فارسی در label و hint،
# و placeholder یک نمونه‌ی خنثی.
_FA = re.compile(r"[\u0600-\u06ff]")
_bad_ph = []
for _name, _src in ALL.items():
    if not _name.endswith((".jsx", ".js")):
        continue
    for _m in re.finditer(r'placeholder="([^"]*)"', _src):
        _txt = _m.group(1)
        # فقط حروف فارسی مهم است؛ رقم فارسی جهت‌پذیر نیست
        if not re.search(r"[\u0620-\u064a\u067e\u0686\u0698\u06af\u06cc]",
                         _txt):
            continue
        # از نزدیک‌ترین «<» عقب‌تر تا خودِ placeholder — داخلِ یک تگ
        # می‌ماند، چون تگ نمی‌تواند «<» داشته باشد
        _open = _src.rfind("<", 0, _m.start())
        _tag = _src[_open:_m.start()]
        if 'dir="ltr"' in _tag or "var(--mono)" in _tag:
            _bad_ph.append(f"{_name}:{_src[:_m.start()].count(chr(10)) + 1}")

check("placeholder فارسی روی فیلد چپ‌به‌راست نمانده", not _bad_ph,
      "، ".join(_bad_ph) if _bad_ph
      else "فارسی در label می‌نشیند، نه در placeholder")


# ═══════════════════════════════════════════════════════════
head("جهت و قلم · فارسی داخل ظرفِ چپ‌به‌راست یا مونو")

# سه چیز اندازه‌گیری‌شده، نه حدس:
#
#   • dir="ltr" جای عدد و واحدش را عوض می‌کند. «۸۳ روز» روی صفحه
#     «روز ۸۳» خوانده می‌شود.
#   • JetBrains Mono هیچ گلیف فارسی ندارد، پس حرف‌های فارسی به مونوی
#     سیستم می‌افتند: «اعتبار» ۷۱٪ پهن‌تر از قلمِ خودِ پنل، «تومان»
#     ۳۱٪ — درست وسط یک عدد.
#   • و ارقام فارسی باید در مونو بمانند، چون ستون‌های جدول با آن
#     هم‌تراز می‌شوند (در مونو همه ۲۴٫۰۱ پیکسل، در قلم اصلی ۱۴٫۵ تا
#     ۲۷٫۱). پس راه‌حل «فارسی را به زنجیره‌ی مونو اضافه کن» رد شد.
#
# این باگ در دو صفحه‌ی جدا پیدا شد — داشبورد حسابداری و «واسطه‌ها و
# نرخ» — با یک متنِ تقریباً یکسان. همان الگویی که این مخزن هفت بار
# دیده: یک قاعده، دو جا، اصلاح در یکی.
#
# راه فرار: کلاس fx-fa-sub (جهت و قلم را برمی‌گرداند) یا <bdi>.
#
# چیزی که این تست *نمی‌تواند* بگیرد: فارسیِ داده‌ای. `{g.name}` وقتی
# نامِ گروه «بدون گروه» باشد همان مشکل را دارد، ولی در فایل هیچ حرف
# فارسی‌ای دیده نمی‌شود. برای آن‌ها قرارداد این است که هر شناسه‌ای که
# کاربر می‌نویسد (نام گروه، ایمیل کانفیگ) داخل <bdi> و با monoIf()
# بنشیند — و همین تست، اگر کسی <bdi> را بردارد و کنارش متن فارسی
# باشد، قرمز می‌شود.

_FA_LETTER = re.compile(r"[\u0620-\u064A\u066E-\u06D3\u06EE\u06EF"
                        r"\u06FA-\u06FF]")
#: راه‌های اعلامِ «این‌جا حواسم بود»
#  fx-fa-sub  → جهت و قلم را برمی‌گرداند
#  <bdi       → متنِ دوجهته را جدا نگه می‌دارد
#  monoIf(    → مونو را فقط به شناسه‌ی لاتین می‌دهد
#  fx-ltr-ok  → چپ‌به‌راست عمدی است (نمودار جریان)
_ESCAPE = ("fx-fa-sub", "<bdi", "monoIf(")
_TAG_ESCAPE = ("fx-ltr-ok",)

def _walk_jsx(src):
    """
    پشته‌ی تگ‌ها را می‌پیماید و هر متنِ فارسی را با ظرفش گزارش می‌کند.

    چرا پشته و نه regex روی بدنه: دو <span> تودرتو هم‌نام‌اند، پس
    «تا اولین </span>» بدنه را وسط می‌برد. و وقتی راه فرار را
    «هرجای بدنه» گرفتم، شکستنِ عمدی نشان داد یک <bdi> در گوشه‌ی
    بدنه، فارسیِ بیرونِ خودش را هم معاف می‌کند.

    برمی‌گرداند: (شماره‌ی خط, توضیح ظرف) برای هر تخلف.
    """
    out, stack, i, n = [], [], 0, len(src)
    while i < n:
        lt = src.find("<", i)
        if lt < 0:
            lt = n
        text = src[i:lt]
        if text and _FA_LETTER.search(text):
            # عمیق‌ترین ظرفی که جهت یا قلم را تحمیل می‌کند
            hard = max((k for k, f in enumerate(stack) if f["hard"]),
                       default=None)
            safe = max((k for k, f in enumerate(stack) if f["safe"]),
                       default=None)
            if hard is not None and (safe is None or safe < hard):
                out.append((src[:i].count(chr(10)) + 1, stack[hard]["desc"]))
        i = lt
        if i >= n:
            break
        if src.startswith("</", i):
            gt = src.find(">", i)
            if gt < 0:
                break
            if stack:
                stack.pop()
            i = gt + 1
            continue
        m = re.match(r"<([A-Za-z][\w.]*)", src[i:])
        if not m:
            i += 1
            continue
        # تا بستنِ تگِ باز، با شمردن آکولاد — صفت‌ها {{…}} دارند
        j, depth = i + m.end(), 0
        while j < n:
            c = src[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == ">" and depth == 0:
                break
            j += 1
        attrs = src[i + m.end():j]
        self_close = attrs.rstrip().endswith("/")
        tag = m.group(1)
        hard = ('dir="ltr"' in attrs or "var(--mono)" in attrs) \
            and not any(e in attrs for e in _TAG_ESCAPE)
        safe = (tag == "bdi" or "fx-fa-sub" in attrs or "monoIf(" in attrs)
        if not self_close:
            stack.append({
                "hard": hard, "safe": safe,
                "desc": "<%s%s>" % (tag, re.sub(r"\s+", " ", attrs)[:44]),
            })
        i = j + 1
    return out


_bidi = []
for _name, _src in ALL.items():
    if not _name.endswith(".jsx"):
        continue
    # کامنت‌ها با تعداد خطِ برابر جایگزین می‌شوند، وگرنه شماره‌ی خطی
    # که گزارش می‌شود با فایل نمی‌خواند و آدم را به جای اشتباه می‌برد
    _flat = re.sub(r"\{/\*.*?\*/\}",
                   lambda m: "\n" * m.group(0).count("\n"), _src, flags=re.S)
    for _line, _desc in _walk_jsx(_flat):
        _bidi.append("%s:%d %s" % (_name, _line, _desc))

check("حرف فارسی داخل dir=ltr یا مونو نمانده", not _bidi,
      "، ".join(_bidi[:6]) if _bidi
      else "هر کدام یا fx-fa-sub دارند یا داخل bdi نشسته‌اند")

# و خودِ راه فرار باید وجود داشته باشد، وگرنه تست بالا با حذف کلاس
# هم سبز می‌ماند
_css = ALL.get("index.css") or io.open(
    os.path.join(SRC, "index.css"), encoding="utf-8").read()
check("کلاس fx-fa-sub تعریف شده", ".fx-fa-sub" in _css
      and "--sans" in _css, "جهت rtl و قلم اصلی را برمی‌گرداند")


# ═══════════════════════════════════════════════════════════
head("دکمه‌ی آیکونی · هر دکمه‌ای باید بگوید چه می‌کند")

# دکمه‌ی بی‌متن و بی‌tooltip کاربر را به حدس‌زدن وامی‌دارد، و ۱۲ تا از
# اینها دکمه‌ی «حذف» بودند. پنل ۳۳ دکمه را از قبل همین‌طور برچسب زده
# بود؛ بقیه جا مانده بودند.

_ICON = re.compile(r"<([A-Z][A-Za-z0-9]*)\s+size=")
_nolabel = []
for _name, _src in ALL.items():
    if not _name.endswith(".jsx"):
        continue
    for _m in re.finditer(r"<button\b", _src):
        _i, _depth = _m.end(), 0
        while _i < len(_src):
            _ch = _src[_i]
            if _ch == "{":
                _depth += 1
            elif _ch == "}":
                _depth -= 1
            elif _ch == ">" and _depth == 0:
                break
            _i += 1
        _open_tag = _src[_m.start():_i + 1]
        _close = _src.find("</button>", _i)
        _body = _src[_i + 1:_close] if _close > 0 else ""
        _inner = re.sub(r"<[^>]*>", "", _body)
        # متنِ ثابت
        _txt = re.sub(r"\{[^{}]*\}", "", _inner).strip()
        # و متنِ پویا: `{copied ? "کپی شد" : "کپی لینک"}` یا `{label}`
        # هم برچسب‌اند و کاربر می‌بیندشان. بدون این، هر دکمه‌ای که
        # متنش شرطی باشد «فقط‌آیکون» شمرده می‌شد — دو مورد در مینی‌اپ
        # همین‌طور بی‌دلیل قرمز شدند.
        if not _txt:
            for _e in re.findall(r"\{([^{}]*)\}", _inner):
                if re.search(r'"[^"]*[^\W\d_][^"]*"', _e) or \
                        re.fullmatch(r"\s*[a-z]\w*\s*", _e):
                    _txt = "(پویا)"
                    break
        if _txt or not _ICON.search(_body):
            continue
        if "title=" in _open_tag or "aria-label" in _open_tag:
            continue
        _nolabel.append("%s:%d" % (_name, _src[:_m.start()].count(chr(10)) + 1))

check("هر دکمه‌ی فقط‌آیکون برچسب دارد", not _nolabel,
      "، ".join(_nolabel[:6]) if _nolabel
      else "title یا aria-label روی همه هست")


# ═══════════════════════════════════════════════════════════
head("زبان · واحدِ انگلیسی در رابطی که فارسی است")

# دو خط در دو صفحه‌ی جدا این شکلی بودند:
#
#     {g.name} · {g.configs} config · {g.months} months
#
# در حالی که سرستونِ همان جدول «ماه» می‌نوشت و جای دیگرِ همان فایل
# «{faNum(it.months)} ماه». یعنی واژه‌ها فارسیِ خودشان را داشتند و
# فقط این دو خط جا مانده بودند.
#
# فقط متنِ رندرشده شمرده می‌شود، نه کد: «config» ۱۲۶ بار در مخزن هست
# و تقریباً همه‌اش نام متغیر یا مسیر API است.

#: واژه‌هایی که معادل فارسی‌شان همین حالا جای دیگرِ پنل به کار می‌رود
_EN_UNITS = re.compile(r"\b(configs?|months?|days?|used|renewals?)\b", re.I)

_en = []
for _name, _src in ALL.items():
    if not _name.endswith(".jsx"):
        continue
    _flat = re.sub(r"\{/\*.*?\*/\}",
                   lambda m: "\n" * m.group(0).count("\n"), _src, flags=re.S)
    # متنِ بینِ تگ‌ها، بدونِ عبارت‌های {…}
    for _m in re.finditer(r">([^<>]{1,200})<", _flat):
        _txt = _m.group(1)
        # آکولادهای تودرتو را لایه‌لایه برمی‌داریم؛ یک regex ساده
        # `\{[^{}]*\}` از پسِ {a && (b ? c : d)} برنمی‌آید و تکه‌ای از
        # کد را به‌عنوان «متن» تحویل می‌دهد
        for _ in range(6):
            _new = re.sub(r"\{[^{}]*\}", "", _txt)
            if _new == _txt:
                break
            _txt = _new
        # اگر هنوز نشانه‌ی کد دارد، این «متنِ نمایشی» نبوده
        if re.search(r"[{}();=]|&&|=>", _txt):
            continue
        if not _EN_UNITS.search(_txt):
            continue
        _en.append("%s:%d — %s" % (
            _name, _flat[:_m.start()].count(chr(10)) + 1,
            re.sub(r"\s+", " ", _txt).strip()[:44]))

check("واحدِ انگلیسی در متنِ نمایشی نمانده", not _en,
      "، ".join(_en[:5]) if _en
      else "«کانفیگ» و «ماه» و «مصرف» همه‌جا فارسی‌اند")


# ═══════════════════════════════════════════════════════════
head("اندازه‌ی قلم · کلاسی که نوشته می‌شود باید اثر کند")

# `.fx-stat-num` در index.css اندازه و وزن را می‌گذاشت و دیرتر از
# کلاس‌های تیلویند می‌آمد، پس با ویژگیِ برابر برنده می‌شد. نتیجه: سه
# جا `fx-stat-num text-[21px] font-extrabold` نوشته شده بود و هیچ‌کدام
# کار نمی‌کرد — ۳۲ پیکسل (و در موبایل ۲۸) رندر می‌شد و عددِ میلیونی از
# کارت بیرون می‌زد. با :where ویژگی صفر می‌شود و هر اندازه‌ی صریحی در
# JSX برنده است.
check("اندازه‌ی fx-stat-num با :where قابل بازنویسی است",
      ":where(.fx-stat-num)" in _css,
      "وگرنه text-[..] کنارش بی‌اثر می‌شود")

# قاعده‌ی واقعی: هیچ‌جا `.fx-stat-num` بدونِ :where نباید font-size
# بگذارد — نه در قاعده‌ی اصلی، نه داخل مدیاکوئری. شمردنِ همه‌شان از
# خواندنِ یک مدیاکوئریِ مشخص مطمئن‌تر است، چون فردا مدیاکوئریِ دیگری
# اضافه می‌شود و تستِ نقطه‌ای آن را نمی‌بیند.
_bare_size = []
for _m in re.finditer(r"(:where\()?\.fx-stat-num\)?\s*\{([^}]*)\}", _css):
    if "font-size" in _m.group(2) and not _m.group(1):
        _bare_size.append(re.sub(r"\s+", " ", _m.group(2)).strip()[:40])
check("هیچ قاعده‌ی fx-stat-num بدون :where اندازه نمی‌گذارد",
      not _bare_size, "، ".join(_bare_size) if _bare_size
      else "پیش‌فرض‌ها صفر-ویژگی‌اند و text-[..] بر آن‌ها غلبه می‌کند")



# ═══════════════════════════════════════════════════════════
head("فیلد عددی · کاربر فارسی باید بتواند رقم بزند")

# `<input type="number">` هر چیزی جز رقمِ لاتین را **بی‌صدا دور
# می‌ریزد**. در مرورگر اندازه گرفته شد:
#
#     تایپ «۱۲۳»    →  value === ""
#     تایپ «۱۲٬۳۴۵» →  value === ""
#     تایپ «1,234»  →  value === ""
#
# یعنی کاربر فارسی رقم می‌زند و هیچ چیزی در فیلد ظاهر نمی‌شود؛ نه
# خطایی، نه پیامی. و فلش‌های بالا/پایینش هم در چیدمان راست‌به‌چپ سر
# جای درستی نمی‌نشستند.
#
# جایگزین NumberInput است: type=text با inputMode عددی، و
# نرمال‌سازی در همان مرز. چیزی که به onChange و بعد به بکند می‌رسد
# همان رشته‌ی لاتینِ قبلی است — قرارداد عوض نشده، فقط دیگر خالی
# نمی‌ماند.

_num_inputs = []
for _name, _src in ALL.items():
    if not _name.endswith(".jsx"):
        continue
    for _m in re.finditer(r"<input\b", _src):
        _i, _d = _m.end(), 0
        while _i < len(_src):
            _c = _src[_i]
            if _c == "{":
                _d += 1
            elif _c == "}":
                _d -= 1
            elif _c == ">" and _d == 0:
                break
            _i += 1
        if 'type="number"' in _src[_m.start():_i + 1]:
            _num_inputs.append("%s:%d"
                               % (_name, _src[:_m.start()].count(chr(10)) + 1))

check("هیچ <input type=\"number\"> نمانده", not _num_inputs,
      "، ".join(_num_inputs[:6]) if _num_inputs
      else "همه NumberInput شده‌اند")

_ui = ALL.get("ui/index.jsx", "")
check("NumberInput وجود دارد و type=text است",
      "export function NumberInput" in _ui and 'type="text"' in _ui,
      "با inputMode عددی، تا صفحه‌کلید موبایل هم عددی بماند")
check("و ورودی را پیش از onChange نرمال می‌کند",
      "normalizeNumeric(e.target.value" in _ui,
      "وگرنه رقم فارسی دست‌نخورده به بکند می‌رسد")
check("نرمال‌ساز ارقام فارسی و عربی را می‌شناسد",
      "\u06F0" in _ui or "۰-۹" in _ui,
      "هر دو مجموعه‌ی رقم در یونیکد جدا هستند")


# ═══════════════════════════════════════════════════════════
head("جدول پرتال · روی گوشی نباید پهلو بکشد")

# جدولِ کانفیگ‌ها هفت ستون دارد. روی ۳۷۵ پیکسل یعنی اسکرول افقی، و
# اسکرول افقی یعنی نماینده برای رسیدن به دکمه‌ی تمدید باید جدول را
# بکشد. زیر ۷۲۰ پیکسل هر ردیف یک کارت می‌شود و عنوانِ هر خانه از
# data-label می‌آید — پس یک نشانه‌گذاری می‌ماند، نه دو نسخه‌ی جدا که
# روزی از هم دور بیفتند.
if HAS_PRO_SRC:                 # the reseller portal is Pro (src/pro/portal/)
    _PI = pro_src("pro/portal/index.jsx")

    check("جدول کانفیگ‌ها کلاسِ کارت‌شونده دارد",
          "fx-table-cards" in _PI and ".fx-table-cards" in _css,
          "بدون کلاس، قاعده‌ی موبایل به هیچ جدولی نمی‌خورد")

    _labelled = re.findall(r'<td data-label="([^"]+)"', _PI)
    check("خانه‌های داده عنوان دارند", len(_labelled) >= 5,
          "، ".join(_labelled) if _labelled else "هیچ‌کدام")

    check("و قاعده‌ی موبایل عنوان را نشان می‌دهد",
          "td[data-label]::before" in _css and "attr(data-label)" in _css,
          "وگرنه روی گوشی ستون‌ها بی‌نام می‌شوند")

    # نوار مصرف: عدد تنها خوانده نمی‌شود، نوار فقط دیده می‌شود
    # خودِ قاعده، نه هر رشته‌ای که نامش را دارد: `.fx-usebar > i` هم
    # همین زیررشته را دارد، پس شکستنِ عمدی نشان داد حذفِ قاعده‌ی اصلی
    # گرفته نمی‌شود
    check("نوار مصرف تعریف شده",
          re.search(r"^\.fx-usebar\s*\{", _css, re.M) is not None
          and re.search(r"^\.fx-usebar\s*>\s*i\s*\{", _css, re.M) is not None
          and "fx-usebar" in _PI,
          "هم خودِ نوار و هم پُرشدگی‌اش")
    check("و رنگش از روی درصد می‌آید",
          "usagePct >= 90" in _PI and "usagePct >= 75" in _PI,
          "قرمز بالای ۹۰، زرد بالای ۷۵ — تا نگاه سریع کافی باشد")
else:
    _PRO_SKIPPED.append('portal: tables become cards on phones, usage bars')

TW = io.open(os.path.join(ROOT, "frontend", "tailwind.config.js"),
             encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════
head("بارگذاری · اسکلتون، نه چرخنده‌ی وسطِ صفحه")

# چرخنده فقط می‌گوید «صبر کن» و وقتی داده رسید کل چیدمان می‌پرد.
# اسکلتون جای محتوا را از قبل نگه می‌دارد.
#
# چرخنده‌ی داخلِ دکمه درست است و باید بماند: آن‌جا واقعاً یعنی
# «این دکمه مشغول است» و جای چیزی را نگرفته.
_page_spin = []
for _n, _s in ALL.items():
    for _m in re.finditer(
            r'<div className="flex (?:justify-center|items-center justify-center)'
            r'[^"]*"[^>]*>\\s*<Loader2[^/]*/>\\s*</div>', _s):
        _page_spin.append(f"{_n}:{_s[:_m.start()].count(chr(10)) + 1}")

check("هیچ چرخنده‌ی تمام‌صفحه‌ای نمانده", not _page_spin,
      "، ".join(_page_spin[:4]) if _page_spin else "همه اسکلتون شده‌اند")

check("اسکلتونِ صفحه وجود دارد", "export function PageSkeleton" in UI)
check("و به صفحه‌خوان هم می‌گوید مشغول است", 'aria-busy="true"' in UI,
      "وگرنه کسی که صفحه را نمی‌بیند نمی‌فهمد چیزی در راه است")

_sk_users = [n for n, s in ALL.items()
             if "<PageSkeleton" in s or "<Skeleton" in s or "<SkeletonTable" in s]
# 18 in the full tree; the Community tree has no Pro screens (17 at area 9).
check("و واقعاً در صفحه‌ها استفاده شده", len(_sk_users) >= (18 if HAS_PRO_SRC else 12),
      f"{len(_sk_users)} فایل")


# ═══════════════════════════════════════════════════════════
head("مودال · نباید تله‌ی کیبورد باشد")

# با Tab می‌شد از داخل مودال به صفحه‌ی زیرش رفت و روی دکمه‌ای زد که
# اصلاً دیده نمی‌شود. برای کسی که با کیبورد کار می‌کند، مودال عملاً
# یک تله بود.
check("حبس تمرکز نوشته شده", "export function useFocusTrap" in UI)
check("و تمرکز را سر جای اولش برمی‌گرداند", "prev.focus" in UI,
      "بعد از بستن، کاربر باید همان‌جا باشد که بود")
check("و با Escape بسته می‌شود", 'e.key === "Escape"' in UI)

for _name in ("Modal", "ConfirmModal"):
    _fn = UI[UI.find(f"export function {_name}("):]
    _fn = _fn[:_fn.find(chr(10) + "export ", 10)]
    check(f"{_name} از حبس تمرکز استفاده می‌کند", "useFocusTrap(box" in _fn)
    check(f"{_name} به صفحه‌خوان می‌گوید مودال است",
          'role="dialog"' in _fn and 'aria-modal="true"' in _fn)

_toast = UI[UI.find("export function Toast("):]
_toast = _toast[:_toast.find(chr(10) + "export ", 10)]
check("توست اعلام می‌شود", 'role="status"' in _toast and 'aria-live' in _toast,
      "بدون این، «ذخیره شد» برای صفحه‌خوان اتفاق نیفتاده است")


# ═══════════════════════════════════════════════════════════
head("موشن · یک زبان، نه سلیقه‌ی هر کامپوننت")

_css_all = CSS
for _tok in ("--m-fast", "--m-base", "--m-slow",
             "--sp-snappy", "--sp-soft", "--sp-inout"):
    check(f"توکن {_tok} تعریف شده", _tok + ":" in _css_all)

check("تیلویند توکن‌ها را می‌شناسد",
      "theme: { extend: {} }" not in TW
      and 'accent: "var(--accent)"' in TW
      and "transitionTimingFunction" in TW,
      "وگرنه هر کامپوننت باید style درون‌خطی بنویسد")
check("و رنگ‌ها را از همان متغیرهای CSS می‌خواند",
      TW.count("var(--") >= 14, f"{TW.count('var(--')} ارجاع")

# انیمیشن روی width/height/top/left یعنی مرورگر باید چیدمان را
# دوباره حساب کند — روی موبایل همان‌جا می‌لنگد
_bad_anim = []
for _m in re.finditer(r"transition:\\s*([^;]+);", _css_all):
    _t = _m.group(1)
    for _prop in ("width", "height", "top", "left", "right", "bottom", "margin"):
        # «width» داخل «stroke-width» و «max-width» نباید شمرده شود
        if re.search(r"(?:^|[\\s,])" + _prop + r"(?:\\s|,|$)", _t):
            _bad_anim.append(_t.strip()[:60])
check("هیچ transition روی خصوصیت‌های چیدمانی نیست", not _bad_anim,
      "، ".join(sorted(set(_bad_anim))[:3]) if _bad_anim
      else "فقط transform و opacity و رنگ — یعنی روی GPU")

check("حرکت را می‌شود کم کرد", "body.fx-calm" in _css_all)
check("و تنظیمِ خودِ سیستم هم محترم است",
      "prefers-reduced-motion" in _css_all)


# ═══════════════════════════════════════════════════════════
head("پالت فرمان · ۴۵ صفحه با یک تایپ")

_APPJ = ALL.get("App.jsx", "")
check("پالت فرمان وجود دارد", "export function CommandPalette" in UI)
check("و با Ctrl+K باز می‌شود",
      'e.key.toLowerCase() === "k"' in _APPJ and "ctrlKey" in _APPJ)
check("همه‌ی فضاهای کاری را می‌گردد، نه فقط یکی",
      "workspaces={WORKSPACES}" in _APPJ,
      "جستجوی سایدبار فقط همان فضای کاری را فیلتر می‌کرد")
check("و انتخاب، فضای کاری را هم عوض می‌کند",
      "setWorkspace(ws)" in _APPJ,
      "وگرنه به صفحه‌ای می‌رفت که در فهرست جاری نیست و پرت می‌شد")
check("صفحه‌های نیامده در پالت نمی‌آیند", "if (it.badge) return;" in UI,
      "دکمه‌ی بی‌جواب از نبودِ دکمه بدتر است")
check("با کیبورد کامل کار می‌کند",
      '"ArrowDown"' in UI and '"ArrowUp"' in UI and '"Enter"' in UI)


# ═══════════════════════════════════════════════════════════
head("سه اپ نباید در یک فایل باشند")

# مشتریِ مینی‌اپ کلِ پنل مدیر را هم دانلود می‌کرد — و همان مشتری،
# همان کسی است که اینترنتش محدود است.
_MAIN = ALL.get("main.jsx", "")
# سه import پویا و *یک* lazy: تکه‌ها جدا می‌مانند و فقط یکی دانلود
# می‌شود. شکلِ قبلی سه تا `lazy(() => import(...))` بود؛ حالا دانلود
# پیش از رندر شروع می‌شود تا کفِ زمانیِ صفحه‌ی ورود با آن هم‌زمان
# بدود، نه پشت سرش.
check("اپ‌ها با import پویا جدا می‌مانند",
      _MAIN.count("() => import(") >= 3, "پنل مدیر، پنل نماینده، مینی‌اپ")
# کامنت‌ها اول برداشته می‌شوند — این‌جا هم `lazy(` در توضیحِ خودِ
# کد پیدا می‌شد و شمارش را دو برابر می‌کرد. سومین بار در این مخزن.
_main_code = "\n".join(l for l in _MAIN.split("\n")
                       if not l.strip().startswith("//"))
check("و فقط یکی از آن‌ها بار می‌شود",
      "PICK[WHICH]()" in _main_code and _main_code.count("lazy(") == 1,
      "اگر هر سه صدا زده شوند، مشتریِ مینی‌اپ کلِ پنل مدیر را هم می‌گیرد")
check("و شرطِ مسیر از ماژولِ بی‌وابستگی می‌آید",
      'from "./lib/route.js"' in _MAIN,
      "وگرنه خودِ تصمیم، هر سه اپ را بار می‌کند")
_ROUTE = ALL.get("lib/route.js", "")
check("و آن ماژول واقعاً هیچ وابستگی‌ای ندارد",
      "import " not in _ROUTE, "یک import کافی است تا همه‌چیز دوباره به هم بچسبد")
check("تا رسیدنِ تکه، صفحه سفید نمی‌ماند", "Suspense" in _MAIN and "fallback" in _MAIN)


# ═══════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════
head("دارایی‌ها · هیچ‌چیز از CDN بیرونی نیاید")

# چرا این دروازه: آیکون‌ها از `cdnjs`، قلم‌ها از `fonts.googleapis`
# و `jsdelivr`، و پرچم‌ها از `flagcdn` می‌آمدند. هیچ‌کدام در ایران
# بالا نمی‌آیند — و چون روی مرورگرِ خودمان (با VPN) درست دیده
# می‌شدند، خرابی هیچ‌وقت پیدا نمی‌شد. مشتری ۴۸ آیکونِ نامرئی
# می‌دید و ما یک صفحه‌ی سالم.
#
# لینکِ قابل کلیک (دانلود برنامه، تلگرام) استثناست: آن را کاربر
# باز می‌کند، مرورگر موقع رندر نمی‌خواهدش.
_CDN = ("fonts.googleapis.com", "fonts.gstatic.com", "cdnjs.cloudflare.com",
        "cdn.jsdelivr.net", "flagcdn.com", "unpkg.com", "use.fontawesome.com")

import re as _re_cdn                                    # noqa: E402

def _asset_hits(text):
    """فقط جایی که مرورگر خودش چیزی را *می‌کشد*، نه لینکِ کلیک‌کردنی."""
    out = []
    for pat in (r'<link[^>]+href="([^"]+)"',
                r'<script[^>]+src="([^"]+)"',
                r'@import\s+url\([\'"]?([^\'")]+)',
                r'url\(\s*[\'"]?(https?://[^\'")]+)'):
        for m in _re_cdn.finditer(pat, text, _re_cdn.I):
            u = m.group(1)
            if any(d in u for d in _CDN):
                out.append(u[:60])
    return out

for _name, _txt in (("پنل", io.open("frontend/index.html", encoding="utf-8").read()),
                    ("صفحه اشتراک", io.open("sub-page-index.html", encoding="utf-8").read())):
    _h = _asset_hits(_txt)
    check(f"{_name} دارایی‌اش را از بیرون نمی‌گیرد", not _h,
          "؛ ".join(_h[:3]) or "در ایران بالا نمی‌آید و بی‌صدا خالی می‌ماند")

# آیکون‌های صفحه‌ی اشتراک باید واقعاً جاسازی شده باشند — نه فقط
# لینکِ CDN برداشته شده باشد، که یعنی هیچ آیکونی
_SUB = io.open("sub-page-index.html", encoding="utf-8").read()
check("آیکون‌های صفحه اشتراک جاسازی‌اند",
      'id="nexora-icons"' in _SUB and "mask-image:url(\"data:image/svg+xml" in _SUB,
      "برداشتنِ لینک بدون جاسازی یعنی هیچ آیکونی")

# و هر آیکونی که در صفحه به کار رفته باید قاعده‌ی خودش را داشته باشد،
# وگرنه همان یکی نامرئی می‌ماند و بقیه سالم‌اند — که سخت‌تر هم دیده
# می‌شود
_used = set(_re_cdn.findall(r"fa-(?:solid|brands|regular) (fa-[a-z0-9-]+)", _SUB))
_styled = set(_re_cdn.findall(r"\.(fa-[a-z0-9-]+)\{-webkit-mask-image", _SUB))
_miss = sorted(_used - _styled)
check("و هر آیکونی که به کار رفته تصویر دارد", not _miss,
      "بی‌تصویر: " + "، ".join(_miss[:5]) if _miss else "")


head("رفتن به یک صفحه · یک در، نه چهار تا")

# پرتکرارترین باگِ این مخزن: یک قاعده در چند جا، اصلاح در یکی.
# این‌جا چهار جا «برو به این صفحه» را جدا نوشته بودند — دسترسی
# سریع، زنگ اعلان، پالت فرمان، و تعویض فضای کاری — و یکی‌شان
# فضای کاری را عوض نمی‌کرد. نتیجه: دکمه‌های دسترسی سریع هیچ کاری
# نمی‌کردند، چون افکتِ نگهبان فوراً برشان می‌گرداند.
_APP = ALL.get("App.jsx", "")

# `setActive` فقط دو جا مجاز است: خودِ goTo، و افکتِ نگهبان که
# صفحه‌ی بی‌جا را برمی‌گرداند.
_sets = _APP.count("setActive(")
check("setActive فقط در دو جای مجاز است", _sets <= 2,
      f"{_sets} بار — هر بارِ اضافه یعنی درِ پنجمی که فضای کاری را فراموش می‌کند")

check("درِ واحد وجود دارد", "const goTo = useCallback(" in _APP)
check("و فضای کاری را از خودِ کلید درمی‌آورد",
      "workspaceOf(WORKSPACES, k)" in _APP,
      "نگاشتِ دستیِ دوم، همان‌جایی است که از هم جدا می‌شوند")

for _who, _pat in (("زنگ اعلان", "onGo={goTo}"),
                   ("پالت فرمان", "onPick={(ws, key) => goTo(key)}"),
                   ("دسترسی سریع", "const navigate = goTo;")):
    check(f"{_who} از همان در می‌رود", _pat in _APP)

# ── نشانی ──
#
# بدون این، رفرش یعنی برگشت به داشبورد و دکمه‌ی «عقب» یعنی
# بیرون‌رفتن از پنل.
check("صفحه‌ی اولیه از نشانی خوانده می‌شود", "readKey()" in _APP,
      "وگرنه رفرش همیشه به صفحه‌ی اول برمی‌گردد")
check("و فضای کاری هم از همان نشانی",
      "workspaceOf(WORKSPACES, readKey())" in _APP,
      "اگر فقط صفحه از نشانی بیاید، نگهبان فوراً پرتش می‌کند بیرون")
check("عقب و جلوی مرورگر شنیده می‌شود",
      '"popstate"' in _APP and '"hashchange"' in _APP)
check("کلیکِ کاربر ورودیِ تاریخچه می‌سازد", "writeKey(k, true)" in _APP,
      "با replace، دکمه‌ی عقب هیچ‌جا نمی‌رود")
check("و هم‌گام‌سازی نمی‌سازد", "writeKey(active, false)" in _APP,
      "هر رندر یک ورودیِ تاریخچه یعنی دکمه‌ی عقب بی‌فایده")

_RT = ALL.get("lib/panelroute.js", "")
check("ماژول نشانی جداست", bool(_RT), "lib/panelroute.js")
check("و هش استفاده می‌کند نه مسیر", "location.hash" in _RT,
      "مسیر با انتخابِ سه‌اپ از روی pathname قاطی می‌شود")


# ═══════════════════════════════════════════════════════════
head("قلمِ عدد · رقمِ فارسی نباید مونو بگیرد")

# پشتیبانِ فارسیِ خودِ مونو — ده‌ها faNum داخلِ var(--mono) است و
# بدونِ این، رقمِ فارسی از قلمِ سیستم (تاهوما) می‌آمد.
_monodef = re.search(r"--mono:([^;]+);", io.open(os.path.join(ROOT, "frontend", "src", "index.css"), encoding="utf-8").read())
check("قلمِ مونو پشتیبانِ فارسی دارد (IRANSansX پیش از monospace)",
      bool(_monodef) and "IRANSansX" in _monodef.group(1)
      and _monodef.group(1).index("IRANSansX") < _monodef.group(1).rindex("monospace"))

# چرا: `--mono` گلیفِ فارسی ندارد. «۳۲» بی‌صدا به قلمِ پشتیبان
# می‌افتاد و کنارِ واحدش («گیگابایت») دو قلمِ متفاوت می‌نشست —
# همان چیزی که مالک «به‌هم‌ریختگی فونت» می‌دید. اندازه‌گیری روی
# مینی‌اپ: ۱۱ جا.
check("توکنِ قلمِ عدد تعریف شده", "--num:" in CSS,
      "ایران‌سنس با tabular-nums، نه مونو")
check("و ایران‌سنس اول زنجیره است",
      CSS.split("--num:")[1].split(";")[0].strip().startswith('"IRANSansX"'))

# قاعده‌هایی که عددِ فارسی نشان می‌دهند نباید مونو بگیرند
_NUMRULES = (".mn-cell-value", ".mn-bal-amount b", ".mn-msg-at",
             ".mn-plan-price", ".fx-stat-num")
for _sel in _NUMRULES:
    _sel = _sel.strip()
    _i = CSS.find(_sel + " {")
    if _i < 0:
        _i = CSS.find(_sel + "{")
    if _i < 0:
        check(f"قاعده‌ی {_sel} هست", False, "پیدا نشد")
        continue
    _blk = CSS[_i:CSS.find("}", _i)]
    check(f"{_sel} مونو نمی‌گیرد", "var(--mono)" not in _blk,
          "رقمِ فارسی در مونو به قلمِ دیگری می‌افتد")


# ═══════════════════════════════════════════════════════════
if pro_src("pro/mini.jsx") is None:
    _PRO_SKIPPED.append("mini app: looks like Telegram (whole section)")
else:
    head("مینی‌اپ · باید شبیه خودِ تلگرام باشد")

    _MINI = pro_src("pro/mini.jsx")
    check("رنگ‌ها را از تلگرام می‌گیرد", "themeParams" in _MINI,
          "وگرنه روی تلگرامِ روشن، یک جعبه‌ی تیره‌ی غریبه است")
    check("و وقتی کاربر پوسته را عوض کند، دنبالش می‌رود",
          '"themeChanged"' in _MINI)
    check("نوار بالای تلگرام هم هم‌رنگ می‌شود", "setHeaderColor" in _MINI)
    check("هیچ متنِ سفیدِ ثابتی نمانده", "text-white" not in _MINI,
          "روی پوسته‌ی روشن، سفید روی سفید نامرئی است")
    check("لرزشِ بازخورد دارد", "HapticFeedback" in _MINI)

    # ساعتِ پیام با رقمِ لاتین چاپ می‌شد — تنها عددِ لاتینِ
    # گفتگو، کنارِ متنِ فارسی، مثل یک وصله. (شناسه‌ی سفارش و
    # لینک و شماره‌ی کارت عمداً لاتین می‌مانند — آن‌ها را کاربر
    # کپی می‌کند، ساعت را فقط می‌خواند.)
    # به *قاعده* بسته شده، نه به شکلِ دقیقِ نشانه‌گذاری: یک‌بار با
    # اضافه‌شدنِ برچسبِ «در حال رفتن» همین تست شکست در حالی که رفتار
    # درست بود.
    _clock_line = next((ln for ln in _MINI.splitlines() if "mn-msg-at" in ln), "")
    _clock_blk = _MINI[_MINI.find("mn-msg-at"):][:200]
    check("ساعتِ پیام رقمِ فارسی دارد",
          "faDigits(String(m.at)" in _clock_blk,
          "رقمِ لاتین کنارِ حبابِ فارسی وصله به نظر می‌رسد")

    # ── ناحیه‌ی امن ──
    #
    # `env(safe-area-inset-*)` را مرورگر از سیستم‌عامل می‌گیرد، ولی داخل
    # WebViewِ تلگرام معمولاً صفر برمی‌گردد و اصلاً چیزی از نوارِ خودِ
    # تلگرام نمی‌داند. پس عددها باید از خودِ تلگرام بیایند.
    check("ناحیه‌ی امن را از تلگرام می‌خواند",
          "safeAreaInset" in _MINI and "contentSafeAreaInset" in _MINI,
          "env() داخل تلگرام صفر است و نوار خودش را هم نمی‌شناسد")
    # دنبالِ *اشتراک* بگرد، نه نامِ رویداد: همان رشته در خطِ لغوِ
    # اشتراک (`offEvent`) هم هست، پس با شرطِ ساده، برداشتنِ خودِ
    # `onEvent` سبز می‌ماند.
    check("و وقتی عوض شود دنبالش می‌رود",
          'onEvent?.("safeAreaChanged"' in _MINI
          and 'onEvent?.("contentSafeAreaChanged"' in _MINI,
          "چرخاندن گوشی و بازشدن صفحه‌کلید عوضش می‌کنند")
    # برگه‌ی پرداخت نباید بلندتر از فضای موجود شود.
    #
    # روی گوشیِ ۸۱۲ پیکسلی جا می‌شد و مشکلی دیده نمی‌شد؛ داخل تلگرام که
    # ارتفاعِ قابل‌استفاده کمتر است، برگه ۵۳۴ پیکسل می‌شد در ۴۸۰ و
    # دستگیره و عنوانش می‌رفتند بالای لبه — و اسکرول هم نداشت.
    _sheet = CSS.split(".mn-sheet {")[1].split("}")[0] if ".mn-sheet {" in CSS else ""
    check("برگه‌ی پرداخت سقف ارتفاع دارد", "max-height:" in _sheet,
          "بدون سقف، بالای برگه بیرون از صفحه می‌رود")
    check("و وقتی بلند شد اسکرول می‌خورد", "overflow-y: auto" in _sheet,
          "برگه‌ی بریده‌ی بی‌اسکرول یعنی دکمه‌ای که کاربر به آن نمی‌رسد")
    check("و اسکرولش به صفحه‌ی پشت سرایت نمی‌کند",
          "overscroll-behavior: contain" in _sheet)

    check("نوارهای بالا و پایین از همان متغیر استفاده می‌کنند",
          "var(--mn-sa-top)" in CSS and "var(--mn-sa-bottom)" in CSS)

    # `* 0` یک‌بار واقعاً در این فایل بود: خطی که شبیه رعایتِ ناحیه‌ی امن
    # است ولی حاصلش همیشه صفر — بدترین نوعِ مسیر خرابِ بی‌صدا، چون
    # *به نظر می‌رسد* کار شده.
    check("هیچ حسابِ ناحیه‌ی امنی در صفر ضرب نشده",
          "safe-area-inset-top, 0px) * 0" not in CSS,
          "خطی که شبیه رعایتِ ناحیه‌ی امن است ولی همیشه صفر می‌دهد")
    check("ولی نبودنش چیزی را نمی‌شکند",
          "catch { /* بی‌صدا — لرزش اختیاری است */ }" in _MINI)
    check("و هنوز هیچ پولی این‌جا حساب نمی‌شود",
          "price *" not in _MINI and "* months" not in _MINI,
          "خرید در خودِ ربات می‌ماند — قرار خودِ مالک")

    import re as _re

# ═══════════════════════════════════════════════════════════
head("نشانِ منو · یک قاعده، دو رندرکننده")

# پنل **دو** رندرکننده‌ی منو دارد: یکی در App.jsx و یکی در
# shell/workspace.jsx برای حالتِ تاشو — که حالتِ پیش‌فرض است.
#
# نسخه‌ی اول نشان را فقط به اولی اضافه کرد و هیچ‌وقت دیده نشد.
# همان باگِ همیشگیِ این مخزن، این بار در کارِ خودم.
_WS = ALL.get("shell/workspace.jsx", "")
_APP = ALL.get("App.jsx", "")

check("کامپوننتِ نشان یک جا تعریف شده",
      "export function NavAlert(" in ALL.get("ui/index.jsx", ""),
      "دو تکه JSX جدا یعنی روزی یکی‌شان عوض می‌شود و دیگری نه")
check("و هر دو رندرکننده از همان استفاده می‌کنند",
      "<NavAlert " in _APP and "<NavAlert " in _WS,
      "حالتِ تاشو پیش‌فرض است؛ اگر نداشته باشدش، نشان دیده نمی‌شود")
check("و هر دو شمارنده را می‌گیرند",
      "alerts[n.alert]" in _APP and "alerts[it.alert]" in _WS)


# ═══════════════════════════════════════════════════════════
head("رنگ · یک نام، یک مقدار")

# چهار وضعیت پنل در ۳۲۸ جای JSX دستی نوشته شده بودند — رنگ هشدار
# به‌تنهایی ۶۳ بار با ۱۷ آلفای متفاوت. `.05` و `.06` و `.07` و `.08`
# را هیچ طراحی عمداً انتخاب نمی‌کند؛ ردِ پای کپی‌کردن‌اند. نتیجه این
# بود که هیچ دو چیپِ «هشدار» دقیقاً یک رنگ نبودند.
_RGBA = _re.compile(r"rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,")

# این دو صفحه انتخابگرِ رنگ‌اند: آن‌جا مقدارِ واقعی *خودِ داده* است،
# نه استایل. عمداً بیرون‌اند.
_PICKERS = ("sections/bot/themes.jsx", "sections/subpage.jsx")

_raw = []
for _name, _src in ALL.items():
    if _name.endswith(_PICKERS) or not _name.endswith(".jsx"):
        continue
    _n = len(_RGBA.findall(_src))
    if _n:
        _raw.append(f"{_name}:{_n}")

check("هیچ rgba خامی در JSX نمانده", not _raw,
      ", ".join(_raw[:4]) if _raw else "همه از توکن می‌آیند")

# و خودِ توکن‌ها باید واقعاً تعریف شده باشند — var(--nope) بی‌صدا
# شفاف می‌شود، که همان مسیر خرابِ بی‌صداست
_CSS = io.open(os.path.join(ROOT, "frontend", "src", "index.css"),
               encoding="utf-8").read()
_defined = set(_re.findall(r"^\s*(--[a-z0-9-]+)\s*:", _CSS, _re.M))
_used = set()
for _name, _src in ALL.items():
    if _name.endswith(".jsx"):
        _used |= set(_re.findall(r"var\(\s*(--[a-z0-9-]+)\s*\)", _src))
# توکن‌هایی که خودِ کامپوننت در لحظه می‌سازد (مثل --ring روی Avatar)
_runtime = {"--ring", "--pct", "--w"}
_ghost = sorted(_used - _defined - _runtime)
check("هر var() که JSX می‌نویسد تعریف شده", not _ghost,
      ", ".join(_ghost[:5]) if _ghost else f"{len(_used)} توکن")

check("پله‌های معنایی کامل‌اند",
      all(f"--{c}-{t}:" in _CSS
          for c in ("ok", "warn", "danger")
          for t in ("wash", "soft", "fill", "line", "edge")),
      "wash · soft · fill · line · edge")


# ═══════════════════════════════════════════════════════════
head("چهره‌ی کاربر · یک قاعده، دو جا")

# `AVATAR_HUES` در پنل (React) و `NEXORA_AVATAR_HUES` در صفحه‌ی
# اشتراک (HTML تک‌فایلی) عمداً تکراری‌اند: صفحه‌ی اشتراک را سرورِ
# 3x-ui سرو می‌کند و به باندلِ ما دسترسی ندارد. پس طبق قاعده‌ی
# مخزن، تستِ برابری می‌خواهد — وگرنه دقیقاً وقتی از هم جدا می‌شوند
# که کسی یکی را عوض کند و همان مشتری در دو جا دو رنگ بگیرد.

_UI = ALL.get("ui/index.jsx", "")
_SUBP = io.open(os.path.join(ROOT, "sub-page-index.html"),
                encoding="utf-8").read()


def _hues(text, name):
    m = _re.search(name + r"\s*=\s*\[(.*?)\];", text, _re.S)
    return _re.findall(r"#[0-9A-Fa-f]{6}", m.group(1)) if m else []


_a = _hues(_UI, "AVATAR_HUES")
_b = _hues(_SUBP, "NEXORA_AVATAR_HUES")
check("پنل رنگ‌های چهره را دارد", len(_a) == 16, f"{len(_a)} رنگ")
check("صفحه‌ی اشتراک هم همان‌ها را دارد", len(_b) == 16, f"{len(_b)} رنگ")
check("و دو فهرست دقیقاً یکی‌اند", _a == _b,
      "یک مشتری نباید در پنل بنفش باشد و در صفحه‌ی اشتراک سبز")

# هشِ رنگ هم باید یکی باشد، نه فقط فهرست
check("هشِ هر دو یک فرمول است",
      "h = (h * 31 + key.charCodeAt(i)) >>> 0" in _UI
      and "h = (h * 31 + label.charCodeAt(i)) >>> 0" in _SUBP,
      "رنگ باید از نام بیاید، همیشه همان")

# دنبالِ *صداشدن* بگرد، نه تعریفِ تابع: با `paintAvatar(` تنها،
# برداشتنِ خطِ صدازدن هم سبز می‌ماند — یعنی دروازه‌ای که به اتاقِ
# خالی نگاه می‌کند.
# چهره باید دایره بماند، نه بیضی. قابِ ۴۶ پیکسلی داخل یک ستونِ
# فلکسِ ۵۴ پیکسلی بود و کنارش خطِ «آفلاین» هم می‌نشست، پس از ۴۶ به
# ۳۸ فشرده می‌شد — و `border-radius: 50%` روی ۴۶×۳۸ یعنی بیضی.
# jsdom چیدمان ندارد، پس این را از روی خودِ قاعده می‌سنجیم.
check("قابِ چهره در صفحه‌ی اشتراک فشرده نمی‌شود",
      "flex: none;" in _SUBP.split(".profile-img {")[1].split("}")[0]
      if ".profile-img {" in _SUBP else False,
      "بدون flex:none، ستونِ فلکس ارتفاعش را می‌خورد و دایره بیضی می‌شود")

# صفحه‌ی اشتراک باید همان زبانِ طراحیِ پنل را داشته باشد، نه فقط
# همان رنگِ اکسنت. سه چیزِ مشترک: سریِ دومِ فیروزه‌ای، خطِ مو روی
# لبه‌ی بالای کارت‌ها، و نورِ محیطی.
# دو کارت که یک چیز را دو بار می‌گفتند، یکی شدند. برگشتشان یعنی
# دوباره ۲۶۲ پیکسل برای شش قلم داده.
check("آمار صفحه‌ی اشتراک دو بار تکرار نمی‌شود",
      'id="sec-details"' not in _SUBP and "stat-cell" in _SUBP,
      "«مصرف کل» و «باقی‌مانده» هر کدام در دو کارت جدا بودند")

# `getElementById(x).innerText` بدون نگهبان یعنی هر جابه‌جاییِ چیدمان
# صفحه را سفید می‌کند.
check("نوشتن روی شناسه نگهبان دارد", "function setText(id, v)" in _SUBP,
      "یک عنصرِ جابه‌جاشده نباید کل رندر را بیندازد")

check("صفحه‌ی اشتراک سری دوم برند را دارد", "--cy:" in _SUBP,
      "پنل دو رنگ دارد؛ این صفحه فقط آبی داشت")
check("و خطِ مو روی لبه‌ی کارت‌ها", "--hair-3" in _SUBP and "::after" in _SUBP,
      "بدون آن، کارت یک مستطیلِ تخت است")
check("و نورِ محیطی زیر همه چیز", "nx-amb" in _SUBP)
# `::after` عمداً است نه `::before`: چند کلاس از قبل `::before`
# دارند (سه‌نقطه‌ی قالب کنسول) و گرفتنش یعنی خراب‌کردنشان.
check("خط مو از ::after می‌آید، نه ::before",
      ".stats-card::after" in _SUBP and ".stats-card::before" not in _SUBP,
      "همان برخوردی که یک‌بار روی کارت KPI پنل رخ داد")

check("صفحه‌ی اشتراک شبحِ خاکستری را کنار می‌گذارد",
      "profile-initial" in _SUBP and "paintAvatar(username)" in _SUBP,
      "آیکونِ یکسان برای همه، هیچ نمی‌گوید")


# ═══════════════════════════════════════════════════════════
head("کانال به عرضِ خودش واکنش می‌دهد، نه به عرضِ پنجره")

# منوی کناری حدود سیصد پیکسل از صحنه می‌برد، پس `min-width` روی
# پنجره چیزی را می‌سنجد که این بخش هیچ‌وقت ندارد. اندازه‌گیری‌شده،
# با منوی باز:
#
#     پنجره ۱۱۰۰ → صحنه ۸۴۰ → کادرِ نوشتن ۴۳۴، پیش‌نمایش ۳۲۶
#
# یعنی گرید دوستونه می‌شد در حالی که جا نداشت. با `@container`
# همان پنجره یک‌ستونه می‌ماند و کادر ۸۰۶ می‌شود — و اگر مالک منو
# را جمع کند، همان پنجره دوستونه می‌شود، چون صحنه واقعاً پهن‌تر
# شده. مدیاکوئری این را نمی‌بیند.
check("گریدِ کانال ظرفِ سنجش دارد",
      ".ch-wrap { container-type: inline-size; }" in CSS,
      "بدونِ ظرف، @container به کلِ صفحه برمی‌گردد")
check("و دوستونه‌شدنش با @container است نه @media",
      re.search(r"@container \([^)]*min-width[^)]*\)\s*\{\s*\.ch-grid", CSS)
      is not None,
      "عرضِ پنجره چیزی را می‌سنجد که این بخش ندارد")
check("هیچ مدیاکوئریِ پنجره‌ای روی گریدِ کانال نمانده",
      re.search(r"@media[^{]*\{\s*\.ch-grid", CSS) is None,
      "دو قاعده برای یک چیز، یعنی روزی یکی اصلاح می‌شود و دیگری نه")
check("ورودیِ آدرسِ کانال عرضِ ثابت ندارد",
      "flex: 1 1 180px" in CSS.split(".ch-addr-in {")[1].split("}")[0],
      "عرضِ ثابت در فضای تنگ سرریز می‌کند")


# ═══════════════════════════════════════════════════════════
head("پاسخ‌های آماده در صندوق")

_INBOX = ALL.get("sections/bot/inbox.jsx", "")

_defs = re.search(r"export const QUICK_DEFAULTS = \[(.*?)\n\];", _INBOX, re.S)
check("پاسخ‌های پیش‌فرض وجود دارند", bool(_defs),
      "ردیفِ خالی یعنی مالک نمی‌فهمد این‌جا قرار بوده چه باشد")

_body = _defs.group(1) if _defs else ""
_titles = re.findall(r'title:\s*"([^"]+)"', _body)
check("هر پاسخ هم عنوان دارد هم متن",
      len(_titles) >= 4 and len(_titles) == _body.count("body:"),
      f"{len(_titles)} عنوان · {_body.count('body:')} متن")

# دکمه باید *درج* کند، نه بفرستد: جوابِ آماده تقریباً همیشه یک جمله
# کم دارد، و پیامی که ناقص رفته برنمی‌گردد.
_uq = re.search(r"const useQuick = \(body\) => \{(.*?)\n  \};", _INBOX, re.S)
check("کلیک، متن را در کادر می‌گذارد و نمی‌فرستد",
      bool(_uq) and "send(" not in _uq.group(1),
      "دکمه‌ای که خودش بفرستد، آن یک جمله را برای همیشه حذف می‌کند")
check("و چیپ‌ها روی همین تابع سوارند",
      "onClick={() => useQuick(r.body)}" in _INBOX)

# جای‌گذاری که پرکننده ندارد، وسطِ جمله سوراخ می‌گذارد
_fq = re.search(r"const fillQuick = \(body\) => \{(.*?)\n  \};", _INBOX, re.S)
_filled = set(re.findall(r"\\\{([a-z_]+)\\\}", _fq.group(1))) if _fq else set()
_offered = set(re.findall(r"\{([a-z_]+)\}", _body))
check("هر جای‌گذاری که در متن‌ها آمده، پر هم می‌شود",
      _offered <= _filled,
      f"بی‌پرکننده: {sorted(_offered - _filled)}" if _offered - _filled
      else f"{len(_filled)} جای‌گذار")


# ═══════════════════════════════════════════════════════════
head("پنجره‌ها · فوکوس با تایپ نمی‌پرد")
# ═══════════════════════════════════════════════════════════
# `useFocusTrap` با `onClose` در وابستگی‌ها، با هر رندر دوباره اجرا می‌شد —
# و `onClose` تقریباً همه‌جا تابعِ درون‌خطی است. هر حرفِ تایپ‌شده فوکوس را
# به ✕ می‌برد؛ در «افزودن سرور» فقط یک حرف نوشته می‌شد.
_ft = re.search(r"export function useFocusTrap\(ref, onClose\) \{(.*?)\n\}", ALL.get("ui/index.jsx", ""), re.S)
_ftb = _ft.group(1) if _ft else ""
check("اثرِ تله‌ی فوکوس فقط به ref وابسته است، نه به onClose",
      bool(_ft) and "}, [ref]);" in _ftb and "onClose]" not in _ftb,
      "onClose‌ِ درون‌خطی با هر رندر عوض می‌شود و فوکوس را از فیلد می‌دزدد")
check("و Escape آخرین onClose را از ref صدا می‌زند", "closeRef.current" in _ftb)

# ═══════════════════════════════════════════════════════════
head("اسپلشِ مینی‌اپ · روی گوشیِ اندروید")
# ═══════════════════════════════════════════════════════════
# عکسِ مالک: مربعِ خاکستری پشتِ لوگو، مستطیل پشتِ نام، و دستگیره‌ی کج در
# گوشه — هایلایتِ انتخابِ متنِ اندروید (انگشت روی اسپلش ماند). و تاری روی
# WebViewِ گوشیِ ارزان گران است. هیچ‌کدام در کروم و هارنس دیده نمی‌شد.
check("اسپلش و دکمه‌های مینی‌اپ انتخاب نمی‌شوند (user-select و touch-callout)",
      bool(re.search(r"\.nx-splash, \.nx-splash \*[^{]*\{[^}]*user-select: none;[^}]*-webkit-touch-callout: none",
                     io.open(os.path.join(ROOT, "frontend", "src", "index.css"), encoding="utf-8").read())))
_CSSX = io.open(os.path.join(ROOT, "frontend", "src", "index.css"), encoding="utf-8").read()
_spl = []
for _m in re.finditer(r"([^{}]*)\{([^{}]*)\}", _CSSX):
    _sel, _body = _m.group(1).strip().split("\n")[-1], _m.group(2)
    if re.search(r"\.nx-splash|\.nx-shop|\.nx-shoplogo|^from|^to|^\d+%", _sel) and "blur(" in _body \
            and "backdrop" not in _body:
        _spl.append(_sel[:60])
_kf = re.search(r"@keyframes nx-reveal \{(.*?)\n\}", _CSSX, re.S)
check("هیچ filter: blur روی اسپلش و لوگوی فروشگاه نیست", not _spl, "، ".join(_spl[:4]))
check("و انیمیشنِ ورودِ لوگو (nx-reveal) هم بی تاری است",
      bool(_kf) and "blur(" not in _kf.group(1))
_sl = re.search(r"\n\.nx-shop-logo \{([^}]*)\}", _CSSX)
check("لوگوی اسپلش سایه‌ی تار ندارد — هاله گرادیانِ ::before است",
      bool(_sl) and "box-shadow" not in _sl.group(1) and ".nx-shop-mark::before" in _CSSX)

if _PRO_SKIPPED:
    print(f"\n  {D}Community tree: {len(_PRO_SKIPPED)} Pro checks skipped (no frontend/src/pro/){X}")
# The UI knows the version it was built from and says when the server runs
# another (an update whose build step did not finish; task 10).
_VITE = io.open(os.path.join(SRC, "..", "vite.config.js"), encoding="utf-8").read()
_APPB = io.open(os.path.join(SRC, "..", "..", "backend", "app.py"), encoding="utf-8").read()
check("the build carries its version and the panel compares it with the server's",
      "__NX_BUILD__" in _VITE and "<StaleBuildBanner" in ALL.get("App.jsx", "")
      and "__NX_BUILD__" in ALL.get("ui/pro.jsx", "")
      and '"version": _panel_version()' in _APPB)

head("Toggle gives its callers a value, not the click event")
# Four callers wrote `(v) => up({ enabled: v })` while Toggle passed the click
# event: the trial follow-up stored a DOM node and its save died with
# "Converting circular structure to JSON".
_tg = UI.split("export function Toggle(")[1].split("\nexport ")[0]
check("Toggle calls onChange(!checked)", "onChange(!checked)" in _tg
      and "onClick={onChange}" not in _tg, _tg[:160])

color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
