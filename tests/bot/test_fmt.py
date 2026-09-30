#!/usr/bin/env python3
"""
واژگان قالب‌بندی و سلامت HTML همه‌ی پیام‌های ربات.

چرا وجود دارد:
    تلگرام پیامی را که HTML خرابی داشته باشد رد می‌کند — کاربر هیچ
    چیزی نمی‌بیند و در لاگ فقط یک ۴۰۰ می‌ماند. یک <b> بسته‌نشده کافی
    است تا صفحه‌ای کامل از کار بیفتد.

    این تست دو کار می‌کند: خود توابع fmt را می‌سنجد، و بعد همه‌ی
    صحنه‌هایی که preview_texts می‌سازد را از اعتبارسنج رد می‌کند.

اجرا:  python3 tests/bot/test_fmt.py
"""
import io
import os
# repo root and bot/ — these tests moved from bot/ to tests/bot/ (2.0 layout)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOT_DIR = os.path.join(_ROOT_DIR, "bot")

import re
import sys

sys.path.insert(0, _BOT_DIR)

import fmt as F  # noqa: E402

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
head("امن‌سازی")

check("< و > امن می‌شوند", F.esc("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;")
check("& امن می‌شود", F.esc("a & b") == "a &amp; b")
check("None خالی می‌شود", F.esc(None) == "")
check("عدد هم قبول است", F.esc(42) == "42")
check("امن‌سازی دوباره نمی‌شکند",
      F.esc(F.esc("&")) == "&amp;amp;", "esc دوبار = دوبار کدگذاری")

head("تگ‌های پایه")

check("پررنگ", F.b("سلام") == "<b>سلام</b>")
check("خط‌خورده", F.s("۱۰۰") == "<s>۱۰۰</s>")
check("تک‌فاصله", F.code("nexora_1") == "<code>nexora_1</code>")
check("اسپویلر", F.spoiler("۱۰٪") == "<tg-spoiler>۱۰٪</tg-spoiler>")
check("ورودی خطرناک داخل تگ امن می‌شود",
      F.b("<script>") == "<b>&lt;script&gt;</b>")
check("pre با زبان",
      'class="language-bash"' in F.pre("ls", lang="bash"))

head("لینک")

check("لینک سالم", F.link("اینجا", "https://x.ir")
      == '<a href="https://x.ir">اینجا</a>')
check("لینک tg:// قبول می‌شود", 'href="tg://' in F.user_link("x", 5))
check("آدرس نامعتبر فقط متن می‌شود",
      F.link("متن", "javascript:alert(1)") == "متن",
      "نباید تگ بسازد")
check("آدرس خالی فقط متن می‌شود", F.link("متن", None) == "متن")
check("آدرس با نویسه‌ی خطرناک امن می‌شود",
      "&amp;" in F.link("x", "https://a.ir/?a=1&b=2"))

head("نقل‌قول")

check("نقل‌قول ساده", F.quote("خط") == "<blockquote>خط</blockquote>")
check("نقل‌قول چندخطی", "\n" in F.quote("یک", "دو"))
check("نقل‌قول جمع‌شونده", F.quote_more("متن")
      == "<blockquote expandable>متن</blockquote>")
check("قالب‌بندی داخل نقل‌قول می‌ماند",
      "<b>" in F.quote(F.b("مهم")), "نقل‌قول ورودی آماده را دست نمی‌زند")
check("None داخل نقل‌قول انداخته می‌شود",
      F.quote("یک", None, "دو") == "<blockquote>یک\nدو</blockquote>")

head("قیمت")

check("قیمت بدون تخفیف", F.price("۱۹۰") == "<b>۱۹۰ تومان</b>")
check("قیمت با تخفیف خط‌خورده دارد", "<s>" in F.price("۱۹۰", old="۲۵۰"))
check("قیمت با تخفیف جدید را پررنگ می‌کند",
      "<b>۱۹۰ تومان</b>" in F.price("۱۹۰", old="۲۵۰"))
check("قیمت یکسان خط‌خورده نمی‌گیرد",
      "<s>" not in F.price("۱۹۰", old="۱۹۰"))

head("چیدمان")

check("join خالی‌ها را می‌اندازد",
      F.join("یک", "", None, "دو") == "یک\n\nدو")
check("lines بدون سطر خالی", F.lines("یک", "دو") == "یک\nدو")
check("title پررنگ است", F.title("سلام", "👋") == "👋 <b>سلام</b>")
check("title بدون اموجی فاصله‌ی اضافه ندارد",
      F.title("سلام") == "<b>سلام</b>")
check("field مقدار را کپی‌کردنی می‌کند", "<code>" in F.field("کد", "AB12"))

head("اعتبارسنج")

check("متن سالم ایراد ندارد", F.check(F.b("x") + F.code("y")) == [])
check("تگ بسته‌نشده گرفته می‌شود",
      any("بسته نشده" in p for p in F.check("<b>سلام")))
check("تگ ناشناخته گرفته می‌شود",
      any("ناشناخته" in p for p in F.check("<marquee>x</marquee>")))
check("ترتیب غلط گرفته می‌شود",
      F.check("<b><i>x</b></i>") != [])
check("تگ داخل code گرفته می‌شود",
      any("بی‌اثر" in p for p in F.check("<code><b>x</b></code>")))
check("a بدون href گرفته می‌شود",
      any("href" in p for p in F.check("<a>x</a>")))
check("& تنها گرفته می‌شود",
      any("امن‌سازی‌نشده" in p for p in F.check("a & b")))
check("&amp; مشکلی ندارد", F.check("a &amp; b") == [])
check("بستن بدون باز شدن گرفته می‌شود",
      any("بدون باز شدن" in p for p in F.check("</b>")))
check("blockquote expandable معتبر است",
      F.check(F.quote_more("x")) == [])

check("plain تگ‌ها را برمی‌دارد", F.plain("<b>سلام</b>") == "سلام")
check("سقف طول شناسایی می‌شود", F.too_long("x" * 4097))
check("پیام معمولی بلند نیست", not F.too_long("x" * 100))


# ═══════════════════════════════════════════════════════════
head("همه‌ی صحنه‌های ربات")

# preview_texts هر صفحه‌ی ربات را می‌سازد. اگر HTML هر کدام خراب باشد،
# این‌جا لو می‌رود — نه در دست مشتری.
import subprocess  # noqa: E402

env = dict(os.environ, PYTHONIOENCODING="utf-8", NEXORA_PREVIEW_RAW="1")
root = _ROOT_DIR
proc = subprocess.run([sys.executable, os.path.join("bot", "preview_texts.py")],
                      cwd=root, env=env, capture_output=True, text=True,
                      encoding="utf-8", errors="replace", timeout=300)

check("پیش‌نمایش بدون خطا اجرا شد",
      proc.returncode == 0 and "Traceback" not in (proc.stdout + proc.stderr),
      (proc.stderr or "").strip().splitlines()[-1][:60] if proc.returncode else "")

raw = os.path.join(root, "bot", ".preview-raw.txt")
if os.path.exists(raw):
    blocks = io.open(raw, encoding="utf-8").read().split("\x00")
    blocks = [b for b in blocks if b.strip()]
    check("صحنه‌ها استخراج شدند", len(blocks) > 30, f"{len(blocks)} پیام")

    bad = []
    for blk in blocks:
        name, _, body = blk.partition("\x01")
        for p in F.check(body):
            bad.append(f"{name.strip()}: {p}")
    check("HTML همه‌ی پیام‌ها سالم است", not bad,
          f"{len(bad)} ایراد" if bad else f"{len(blocks)} پیام بررسی شد")
    for line in bad[:10]:
        print(f"      {R}▸{X} {line}")

    long_ = [b.partition("\x01")[0].strip() for b in blocks
             if F.too_long(b.partition("\x01")[2])]
    check("هیچ پیامی از سقف تلگرام رد نشده", not long_, ", ".join(long_[:3]))

    os.remove(raw)
else:
    check("فایل خام پیش‌نمایش ساخته شد", False, ".preview-raw.txt نبود")




# ═══════════════════════════════════════════════════════════
head("سربرگ و جداکننده")

check("خط اصلی تعریف شده", hasattr(F, "RULE"))
check("خط نازک تعریف شده", hasattr(F, "THIN"))
check("خط اصلی روی موبایل نمی‌شکند", len(F.RULE) <= 24,
      f"{len(F.RULE)} کاراکتر — بلندتر از این می‌شکند")
check("خط نازک کوتاه‌تر است", len(F.THIN) < len(F.RULE),
      f"{len(F.THIN)} در برابر {len(F.RULE)}")
check("هر دو یک‌کاراکتری تکرارشده‌اند",
      len(set(F.RULE)) == 1 and len(set(F.THIN)) == 1)

h = F.header("پنل کاربری", "👑", "خوش آمدید")
check("سربرگ عنوان پررنگ دارد", "<b>پنل کاربری</b>" in h)
check("سربرگ اموجی دارد", h.startswith("👑"))
check("سربرگ خط جداکننده دارد", F.RULE in h)
check("زیرعنوان بعد از خط می‌آید",
      h.index(F.RULE) < h.index("خوش آمدید"))
check("بدون زیرعنوان هم کار می‌کند",
      F.header("تنها", "📦").count("\n") == 1)

sec = F.section("مشخصات", "📊")
check("عنوان بخش پررنگ است", "<b>مشخصات</b>" in sec)
check("زیرش خط نازک دارد", sec.endswith(F.THIN))

check("hr خط اصلی می‌دهد", F.hr() == F.RULE)
check("hr(thin) خط نازک می‌دهد", F.hr(thin=True) == F.THIN)

head("چیدمان کامل هنوز HTML معتبر است")

full = F.lines(
    F.header("پنل کاربری نکسورا", "👑", "سلام " + F.b("علی")),
    "",
    F.section("وضعیت", "📊"),
    F.row("اعتبار", "۲۴ روز", "⏳"),
    F.row("حجم", "۴۲.۸ گیگ", "📉"),
    "",
    F.section("لینک", "🔑"),
    F.code("vless://abc@host:443"),
    F.i("برای کپی لمس کنید"),
    F.hr(),
    F.link("پشتیبانی", "https://t.me/nexora"),
)
problems = F.check(full)
check("کل پیام از اعتبارسنجی رد می‌شود", not problems,
      "؛ ".join(problems[:2]))
check("زیر سقف طول تلگرام است", not F.too_long(full),
      f"{len(full)} کاراکتر")
check("متن ساده‌اش خوانا می‌ماند", "پنل کاربری نکسورا" in F.plain(full))


# ═══════════════════════════════════════════════════════════
head("نام اشتراک، اسم کانفیگ مشتری است نه اسم اینباند")

os.environ.setdefault("BOT_DB_PATH", __import__("tempfile").mktemp(suffix=".db"))
sys.path.insert(0, _ROOT_DIR)
from bot import handlers  # noqa: E402
SRC = io.open(os.path.join(_BOT_DIR,
                           "handlers.py"), encoding="utf-8").read()

# روی سرور واقعی همه‌ی کانفیگ‌ها روی یک اینباند مشترک‌اند («پنل
# جدید»). sub_label نام اینباند را *به‌جای* شماره‌ی کانفیگ می‌گذاشت،
# پس هر سه اشتراکِ یک مشتری دقیقاً یک اسم می‌گرفتند و صفحه‌ی تمدید
# نمی‌گفت کدام را دارد تمدید می‌کند.

class LabelCtx(handlers.Ctx):
    """Ctx بدون پنل — فقط نام اینباندها را دستی می‌دهیم."""

    def __init__(self, names):
        self._names = names

    def inbound_names(self):
        return self._names


ONE = LabelCtx({1: "پنل جدید"})
MANY = LabelCtx({1: "آلمان", 2: "فنلاند"})

S1 = {"plan_name": "یک‌ماهه", "client_email": "nexora_555_1", "inbound_id": 1}
S2 = {"plan_name": "یک‌ماهه", "client_email": "nexora_555_2", "inbound_id": 1}
S3 = {"plan_name": "یک‌ماهه", "client_email": "nexora_555_3", "inbound_id": 1}

labels = [ONE.sub_label(s) for s in (S1, S2, S3)]
check("سه اشتراک، سه اسم متفاوت", len(set(labels)) == 3,
      " / ".join(labels))
check("شماره‌ی کانفیگ در اسم هست", "کانفیگ ۲" in labels[1], labels[1])
check("نام اینباند مشترک نمی‌آید", "پنل جدید" not in labels[0],
      "اسم پنل است، نه چیزی که مشتری خریده")
check("نام پلن اول می‌آید", labels[0].startswith("یک‌ماهه"), labels[0])

head("وقتی چند سرور دارید، نام سرور می‌آید")

a = MANY.sub_label({"plan_name": "سه‌ماهه", "client_email": "nexora_9_1",
                    "inbound_id": 1})
b = MANY.sub_label({"plan_name": "سه‌ماهه", "client_email": "nexora_9_1",
                    "inbound_id": 2})
check("سرور اول نامش می‌آید", "آلمان" in a, a)
check("سرور دوم هم همین‌طور", "فنلاند" in b, b)
check("و دو اشتراک روی دو سرور از هم جدا می‌شوند", a != b)

head("حالت‌های ناقص")

check("بدون شناسه‌ی عددی، اسم پلن می‌ماند",
      ONE.sub_label({"plan_name": "یک‌ماهه", "client_email": "custom"})
      == "یک‌ماهه")
check("پلن حذف‌شده با plan_name دستی کار می‌کند",
      "طلایی" in ONE.sub_label({"client_email": "nexora_1_2"},
                               plan_name="طلایی"))
check("هیچ‌چیز نبود، اسم خالی نمی‌ماند",
      ONE.sub_label({}) == "اشتراک",
      "دکمه‌ی بدون متن در تلگرام خطا می‌دهد")

check("صفحه‌ی تمدید همین اسم را نشان می‌دهد",
      "ctx.sub_label(sub, plan_name=" in SRC,
      "همان چیزی که مشتری در فهرست اشتراک‌ها دیده")



print(f"\n{D}{'─' * 46}{X}")
color = G if not _fail else R
# ═══════════════════════════════════════════════════════════
head("نگهبان HTML باید همان چیزی را بگیرد که تلگرام رد می‌کند")

# send وقتی check ایرادی ببیند پیام را *بدون قالب* می‌فرستد. پس هر
# ایراد کاذب یعنی یک پیام تخت‌شده، و هر ایرادِ ازدست‌رفته یعنی پیامی
# که تلگرام پس می‌زند و مشتری هیچ‌وقت نمی‌بیند.

check("بلوک کد با زبان سالم است", F.check(F.pre("ls -la", "bash")) == [],
      "شکل مستندِ خود تلگرام — قبلاً «بی‌اثر» علامت می‌خورد و تخت می‌شد")
check("ولی تگ داخل code هنوز ایراد است",
      any("بی‌اثر" in p for p in F.check("<code><b>x</b></code>")))
check("و تگ داخل خودِ code در pre هم",
      any("بی‌اثر" in p for p in F.check("<pre><code><b>x</b></code></pre>")))

check("«<»ی که تگ نساخته گرفته می‌شود",
      any("«<»" in p for p in F.check("کاربر a<b عزیز")),
      "نامی با < و یک esc جاافتاده — تلگرام کل پیام را رد می‌کند")
check("تگ نیمه‌تمام هم", any("«<»" in p for p in F.check("نام: <script")))
check("«>» تنها ایراد نیست", F.check("۵ > ۳") == [],
      "تلگرام این یکی را قبول می‌کند")
check("متن امن‌شده هنوز سالم است", F.check(F.b("a<b>c")) == [])

check("صفت نامعتبر روی <a> گرفته می‌شود",
      any("صفت نامعتبر" in p
          for p in F.check('<a href="https://x/"چیزی">t</a>')),
      "قبلاً فقط «href هست یا نه» سنجیده می‌شد")
check("لینک سالم رد نمی‌شود",
      F.check(F.link("متن", "https://nexora.ir/sub/abc?x=1&y=2")) == [])
check("لینک تودرتو گرفته می‌شود",
      any("تودرتو" in p for p in
          F.check('<a href="https://a">x<a href="https://b">y</a></a>')))
check("صفت روی تگی که صفت نمی‌گیرد",
      any("صفت نامعتبر" in p for p in F.check('<b class="x">t</b>')))
check("blockquote expandable مجاز است",
      F.check(F.quote_more("یک", "دو")) == [])
check("اسپویلر مجاز است", F.check(F.spoiler("x")) == [])
check("موجودیت شانزده‌شانزدهی ایراد نیست", F.check("a &#x27; b") == [],
      "قبلاً فقط ده‌دهی شناخته می‌شد")


print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
