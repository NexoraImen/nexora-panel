"""
واژگان قالب‌بندی پیام‌های تلگرام.

چرا وجود دارد:
    تا امروز هر پیام ربات تگ‌های HTML را دستی داخل f-string می‌نوشت.
    نتیجه‌اش این بود که یک جا <b> بسته نمی‌شد، یک جا متن کاربر بدون
    امن‌سازی وسط تگ می‌نشست، و تلگرام کل پیام را با خطای «can't parse
    entities» رد می‌کرد — بدون اینکه کسی بفهمد کدام پیام بوده.

    این ماژول همان تگ‌ها را به توابع تبدیل می‌کند: ورودی همیشه
    امن‌سازی می‌شود، تگ همیشه بسته می‌شود، و check() قبل از ارسال
    ساختار را می‌سنجد.

تگ‌هایی که تلگرام در parse_mode=HTML می‌پذیرد:
    <b> <i> <u> <s> <code> <pre> <a href> <tg-spoiler>
    <blockquote> <blockquote expandable>

قاعده‌ی مهم: داخل <code> و <pre> هیچ قالب‌بندی دیگری کار نمی‌کند؛
محتوا عیناً همان‌طور که هست نمایش داده می‌شود. به همین دلیل bold()
و بقیه هرگز داخل code() صدا زده نمی‌شوند.
"""

import re

# ═══════════════════════════════════════════════════════════
#  امن‌سازی
# ═══════════════════════════════════════════════════════════

def esc(s):
    """
    متن خام را برای HTML امن می‌کند.

    هر چیزی که از کاربر یا پنل می‌آید باید از این رد شود. یک نام
    کاربری با < در آن، بدون این کار کل پیام را از کار می‌اندازد.
    """
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;"))


# ═══════════════════════════════════════════════════════════
#  تگ‌های ساده
# ═══════════════════════════════════════════════════════════

def b(s):
    """پررنگ — برای چیزی که چشم باید اول ببیند."""
    return f"<b>{esc(s)}</b>"


def i(s):
    """مورب — برای توضیح کناری، نه محتوای اصلی."""
    return f"<i>{esc(s)}</i>"


def u(s):
    return f"<u>{esc(s)}</u>"


def s(text):
    """خط‌خورده — برای قیمت قبل از تخفیف."""
    return f"<s>{esc(text)}</s>"


def code(s):
    """
    تک‌فاصله — برای هر چیزی که کاربر باید کپی کند.

    در تلگرام با یک ضربه کپی می‌شود، و چون فونتش عرض‌ثابت است
    رقم‌ها زیر هم می‌افتند و خواندن شماره‌ی کارت آسان می‌شود.
    """
    return f"<code>{esc(s)}</code>"


def pre(s, lang=None):
    """بلوک چندخطی تک‌فاصله — برای خروجی دستور یا لاگ."""
    if lang:
        return f'<pre><code class="language-{esc(lang)}">{esc(s)}</code></pre>'
    return f"<pre>{esc(s)}</pre>"


def spoiler(s):
    """پنهان تا وقتی کاربر بزند — برای چیزی که لو دادنش مزه را می‌برد."""
    return f"<tg-spoiler>{esc(s)}</tg-spoiler>"


def link(text, url):
    """
    لینک با متن خوانا.

    آدرس‌های بلند پیام را زشت می‌کنند؛ این‌طور فقط عنوان دیده می‌شود.
    اگر آدرس معتبر نباشد، فقط متن برمی‌گردد — یک لینک خراب نباید
    کل پیام را از کار بیندازد.
    """
    u_ = str(url or "").strip()
    if not re.match(r"^(https?|tg)://", u_):
        return esc(text)
    return f'<a href="{esc(u_)}">{esc(text)}</a>'


def user_link(text, tg_id):
    """اشاره به یک کاربر تلگرام بدون نیاز به یوزرنیم."""
    return f'<a href="tg://user?id={esc(tg_id)}">{esc(text)}</a>'


# ═══════════════════════════════════════════════════════════
#  نقل‌قول
# ═══════════════════════════════════════════════════════════

def quote(*lines):
    """
    نقل‌قول — برای نکته‌ای که باید از متن اصلی جدا دیده شود.

    ورودی از قبل قالب‌بندی‌شده پذیرفته می‌شود (یعنی خروجی b()، code()
    و مانند آن)، چون داخل نقل‌قول قالب‌بندی کار می‌کند.
    """
    body = "\n".join(str(x) for x in lines if x is not None)
    return f"<blockquote>{body}</blockquote>"


def quote_more(*lines):
    """
    نقل‌قول جمع‌شونده — راهنمای بلند بدون اینکه صفحه را پر کند.

    تلگرام فقط چند خط اول را نشان می‌دهد و بقیه با زدن روی آن باز
    می‌شود. برای آموزش نصب و متن‌های طولانی دقیقاً همین لازم است:
    کسی که بلد است رد می‌شود، کسی که نیست بازش می‌کند.
    """
    body = "\n".join(str(x) for x in lines if x is not None)
    return f"<blockquote expandable>{body}</blockquote>"


# ═══════════════════════════════════════════════════════════
#  الگوهای پرتکرار
# ═══════════════════════════════════════════════════════════

def price(new, old=None, unit="تومان"):
    """
    قیمت، و اگر تخفیفی هست قیمت قبلی خط‌خورده کنارش.

    دیدنِ «۲۵۰٬۰۰۰ ← ۱۹۰٬۰۰۰» خیلی قوی‌تر از نوشتن «۲۴٪ تخفیف» است،
    چون مشتری خودش مقدار صرفه‌جویی را می‌بیند.
    """
    if old and str(old) != str(new):
        return f"{s(f'{old} {unit}')} {b(f'{new} {unit}')}"
    return b(f"{new} {unit}")


def row(label, value, emoji=""):
    """
    یک سطر «برچسب: مقدار» با لنگر بصری در ابتدا.

    اموجی ابتدای خط کار نشانه را می‌کند: چشم موقع اسکرول روی آن
    می‌نشیند و لازم نیست کل خط خوانده شود.
    """
    head = f"{emoji} " if emoji else ""
    return f"{head}{esc(label)}  {b(value)}"


def field(label, value, emoji=""):
    """سطری که مقدارش کپی‌کردنی است — مثل شناسه یا کد پیگیری."""
    head = f"{emoji} " if emoji else ""
    return f"{head}{esc(label)}\n{code(value)}"


def bullet(text, emoji="▫️"):
    return f"{emoji} {esc(text)}"


def title(text, emoji=""):
    """تیتر پیام — همیشه اولین خط، همیشه پررنگ."""
    return f"{emoji} {b(text)}".strip()


#: جداکننده‌ی اصلی — بین بخش‌های بزرگ پیام
#:
#: طولش عمداً ۲۰ کاراکتر است. خط‌های بلندتر روی موبایل می‌شکنند و
#: پیام را به‌هم می‌ریزند؛ بیست کاراکتر در باریک‌ترین صفحه هم در یک
#: سطر جا می‌شود.
RULE = "━" * 20

#: جداکننده‌ی فرعی — زیر عنوان هر بخش، نازک‌تر از خط اصلی
THIN = "─" * 16


def hr(thin=False):
    """
    جداکننده‌ی بین بخش‌ها.

    خط اصلی بخش‌های بزرگ را از هم جدا می‌کند، خط نازک زیربخش‌ها را.
    طولشان ثابت و کوتاه است تا در هیچ صفحه‌ای نشکنند.
    """
    return THIN if thin else RULE


def header(text, emoji="", subtitle=None):
    """
    سربرگ پیام: عنوان پررنگ، خط جداکننده، و اگر بود یک زیرعنوان.

    این همان الگویی است که چشم را سر جای درست می‌نشاند — عنوان،
    مرز، بعد محتوا.
    """
    out = [f"{emoji} {b(text)}".strip(), RULE]
    if subtitle:
        out.append(subtitle)
    return "\n".join(out)


def section(text, emoji=""):
    """عنوان یک زیربخش، با خط نازک زیرش."""
    return f"{emoji} {b(text)}".strip() + "\n" + THIN


def join(*parts):
    """
    بخش‌ها را با یک سطر خالی به هم می‌چسباند و خالی‌ها را می‌اندازد.

    این‌طور می‌شود بخشی را شرطی ساخت بدون اینکه سطر خالی اضافه جا بماند.
    """
    return "\n\n".join(p for p in (str(x) for x in parts if x) if p.strip())


def lines(*parts):
    """مثل join ولی بدون سطر خالی بین‌شان."""
    return "\n".join(p for p in (str(x) for x in parts if x) if p.strip())


# ═══════════════════════════════════════════════════════════
#  اعتبارسنجی
# ═══════════════════════════════════════════════════════════

#: تگ‌هایی که تلگرام می‌شناسد. هرچه بیرون این باشد خطای parse می‌دهد.
ALLOWED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
           "code", "pre", "a", "tg-spoiler", "blockquote", "span"}

#: داخل اینها قالب‌بندی کار نمی‌کند، پس تگ تودرتو یعنی اشتباه منطقی
LITERAL = {"code", "pre"}

#: تگ‌هایی که هیچ صفتی نمی‌گیرند
_BARE = None   # در _ATTRS مقداردهی می‌شود

_TAG = re.compile(r"<(/?)([a-zA-Z-]+)([^>]*)>")

#: تنها صفت‌هایی که تلگرام برای هر تگ می‌پذیرد.
#:
#: بدون این، «href=" هست یا نه» تنها چیزی بود که سنجیده می‌شد — پس
#: <a href="https://x/"چیزی"> از نگهبان رد می‌شد و تلگرام پیام را
#: پس می‌زد.
_ATTRS = {
    "a": re.compile(r'^\s*href="[^"<>]*"\s*$'),
    "code": re.compile(r'^\s*(class="language-[\w.+#-]+")?\s*$'),
    "blockquote": re.compile(r"^\s*(expandable)?\s*$"),
    "span": re.compile(r'^\s*class="tg-spoiler"\s*$'),
}

_BARE = re.compile(r"^\s*$")


def check(text):
    """
    ساختار HTML یک پیام را می‌سنجد و فهرست ایرادها را برمی‌گرداند.

    تلگرام پیام با تگ خراب را رد می‌کند و کاربر هیچ چیزی نمی‌بیند.
    بهتر است این‌جا و در تست بفهمیم تا در دست مشتری.

    فهرست خالی یعنی سالم.
    """
    problems = []
    stack = []
    spans = []
    for m in _TAG.finditer(text):
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        spans.append((m.start(), m.end()))

        if name not in ALLOWED:
            problems.append(f"تگ ناشناخته: <{name}>")
            continue

        if closing:
            if not stack:
                problems.append(f"</{name}> بدون باز شدن")
            elif stack[-1] != name:
                problems.append(f"</{name}> در حالی که <{stack[-1]}> باز است")
                stack.pop()
            else:
                stack.pop()
            continue

        # داخل code/pre هیچ تگی نباید باشد — جز <code> بلافاصله داخل
        # <pre>، که شکل مستندِ خودِ تلگرام برای بلوک کد با زبان است.
        # قبلاً همین شکل «بی‌اثر» علامت می‌خورد، و چون send وقتی
        # ایرادی ببیند پیام را بدون قالب می‌فرستد، اولین بلوک کدِ
        # زبان‌دار بی‌صدا تخت می‌شد.
        if stack and stack[-1] in LITERAL and not (stack[-1] == "pre"
                                                   and name == "code"):
            problems.append(f"<{name}> داخل <{stack[-1]}> بی‌اثر است")

        if name == "a" and "a" in stack:
            problems.append("<a> داخل <a> — تلگرام لینک تودرتو را رد می‌کند")

        if name == "a" and 'href="' not in attrs:
            problems.append("<a> بدون href")
        elif not _ATTRS.get(name, _BARE).match(attrs):
            problems.append(f"<{name}> با صفت نامعتبر: {attrs.strip()[:40]}")

        stack.append(name)

    for name in stack:
        problems.append(f"<{name}> بسته نشده")

    # «<»ی که تگ کامل نساخته — همان چیزی که این نگهبان برای آن هست
    #
    # قبلاً فقط تگ‌های *کامل* دیده می‌شدند، پس نامی مثل «a<b» از
    # نگهبان رد می‌شد و تلگرام پیام را پس می‌زد: مشتری هیچ چیزی
    # نمی‌دید و هیچ‌جا هم ثبت نمی‌شد که چرا.
    covered = set()
    for a, z in spans:
        covered.update(range(a, z))
    for idx, ch in enumerate(text):
        if ch == "<" and idx not in covered:
            problems.append(f"«<» امن‌سازی‌نشده در نویسه‌ی {idx}")
            break

    # & تنهایی هم پیام را می‌شکند
    for m in re.finditer(r"&(?!(amp|lt|gt|quot|#x?[0-9a-fA-F]+);)", text):
        problems.append(f"& امن‌سازی‌نشده در نویسه‌ی {m.start()}")
        break

    return problems


def plain(text):
    """متن بدون تگ — برای شمردن طول واقعی و برای تست."""
    return re.sub(r"<[^>]+>", "", text)


#: سقف طول پیام در تلگرام
MAX_LEN = 4096


def too_long(text):
    """آیا پیام از سقف تلگرام رد شده؟ تگ‌ها هم حساب می‌شوند."""
    return len(text) > MAX_LEN
