"""
منطق کسب‌وکار ربات: سیستم سکه، تخفیف، سفارش و رفرال.

این ماژول عمداً از تلگرام و دیتابیس مستقل نگه داشته شده تا
بشود مستقیم و بدون شبیه‌سازی تستش کرد.
"""

import json
import os
import random
from pathlib import Path
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════
#  سیستم سکه
# ═══════════════════════════════════════════════════════════

# پله‌های پیش‌فرض طبق ایده‌ی کاربر: هر ۲۰ سکه = ۱۰٪ تخفیف
DEFAULT_COIN_TIERS = [
    {"coins": 20,  "percent": 10},
    {"coins": 40,  "percent": 20},
    {"coins": 60,  "percent": 30},
    {"coins": 80,  "percent": 40},
    {"coins": 100, "percent": 50},
]

DEFAULT_COIN_SETTINGS = {
    "enabled": True,
    "tiers": DEFAULT_COIN_TIERS,
    "per_referral": 10,        # سکه به معرف، بعد از اولین خرید زیرمجموعه
    "welcome_bonus": 0,        # سکه به کاربر جدیدی که با لینک آمده
    "max_percent": 50,         # سقف تخفیف
    "expire_days": 0,          # 0 = بدون انقضا
}


def coin_settings(raw):
    """ادغام تنظیمات ذخیره‌شده با پیش‌فرض‌ها."""
    s = dict(DEFAULT_COIN_SETTINGS)
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in s and v is not None:
                s[k] = v
    tiers = s.get("tiers") or DEFAULT_COIN_TIERS
    # مرتب‌سازی صعودی تا محاسبه‌ی پله درست باشد
    s["tiers"] = sorted(
        [t for t in tiers if isinstance(t, dict) and t.get("coins") is not None],
        key=lambda t: int(t["coins"])
    )
    return s


def tier_for(coins, settings):
    """
    بالاترین پله‌ای که کاربر با این تعداد سکه به آن رسیده.
    اگر به هیچ پله‌ای نرسیده، None برمی‌گرداند.
    """
    s = coin_settings(settings)
    if not s["enabled"]:
        return None
    reached = None
    for t in s["tiers"]:
        if coins >= int(t["coins"]):
            reached = t
        else:
            break
    if not reached:
        return None
    pct = min(int(reached["percent"]), int(s["max_percent"]))
    return {"coins": int(reached["coins"]), "percent": pct}


def next_tier(coins, settings):
    """پله‌ی بعدی و تعداد سکه‌ی لازم تا رسیدن به آن."""
    s = coin_settings(settings)
    for t in s["tiers"]:
        if coins < int(t["coins"]):
            return {"coins": int(t["coins"]),
                    "percent": int(t["percent"]),
                    "need": int(t["coins"]) - coins}
    return None


def coin_progress(coins, settings):
    """خلاصه‌ی وضعیت سکه برای نمایش به کاربر."""
    cur = tier_for(coins, settings)
    nxt = next_tier(coins, settings)
    return {
        "coins": coins,
        "current_percent": cur["percent"] if cur else 0,
        "current_cost": cur["coins"] if cur else 0,
        "next": nxt,
    }


def apply_coins(price, coins, settings):
    """
    اعمال تخفیف سکه روی قیمت.

    منطق: کاربر بالاترین پله‌ی ممکن را استفاده می‌کند و فقط سکه‌های
    همان پله مصرف می‌شود — نه همه‌ی موجودی. این‌طور اگر ۱۲۰ سکه دارد،
    ۱۰۰ تا خرج می‌کند و ۲۰ تا برایش می‌ماند.
    """
    t = tier_for(coins, settings)
    if not t or price <= 0:
        return {"price": price, "discount": 0, "percent": 0, "coins_used": 0}

    discount = price * t["percent"] // 100
    return {
        "price": max(price - discount, 0),
        "discount": discount,
        "percent": t["percent"],
        "coins_used": t["coins"],
    }


# ═══════════════════════════════════════════════════════════
#  قیمت‌گذاری سفارش
# ═══════════════════════════════════════════════════════════

def price_order(plan_price, *, coins=0, coin_cfg=None, use_coins=False,
                discount_percent=0, reseller_discount=0):
    """
    محاسبه‌ی قیمت نهایی با همه‌ی تخفیف‌ها.

    ترتیب اعمال: اول کد تخفیف، بعد سکه، بعد تخفیف عمده‌ی واسطه.
    این ترتیب عمدی است تا تخفیف‌ها روی هم ضرب نشوند و قیمت منفی نشود.
    """
    base = int(plan_price)
    price = base
    # `code_percent` کنارِ مبلغش می‌آید تا صداکننده مجبور نشود از
    # روی دو عدد دوباره درصد را حساب کند — همان‌جا که گرد‌کردن
    # عددی می‌سازد که با آنچه به مشتری گفته‌ایم یکی نیست.
    breakdown = {"base": base, "code_discount": 0, "code_percent": 0,
                 "coin_discount": 0, "reseller_discount": 0,
                 "coins_used": 0, "coin_percent": 0}

    if discount_percent > 0:
        d = price * int(discount_percent) // 100
        breakdown["code_discount"] = d
        breakdown["code_percent"] = int(discount_percent)
        price -= d

    if use_coins and coins > 0:
        res = apply_coins(price, coins, coin_cfg)
        breakdown["coin_discount"] = res["discount"]
        breakdown["coins_used"] = res["coins_used"]
        breakdown["coin_percent"] = res["percent"]
        price = res["price"]

    if reseller_discount > 0:
        d = price * int(reseller_discount) // 100
        breakdown["reseller_discount"] = d
        price -= d

    breakdown["final"] = max(price, 0)
    return breakdown


# ═══════════════════════════════════════════════════════════
#  کد تخفیف
# ═══════════════════════════════════════════════════════════

def validate_discount(row, plan_id=None):
    """بررسی اعتبار کد تخفیف. (پیام خطا, درصد)"""
    if not row:
        return "کد تخفیف پیدا نشد", 0
    if not row.get("is_active"):
        return "این کد غیرفعال است", 0
    if row.get("max_uses") and row["used_count"] >= row["max_uses"]:
        return "ظرفیت این کد تمام شده", 0
    exp = row.get("expires_at")
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now():
                return "این کد منقضی شده", 0
        except ValueError:
            pass
    if row.get("plan_id") and plan_id and row["plan_id"] != plan_id:
        return "این کد برای این پلن نیست", 0
    return None, int(row["percent"])


# ═══════════════════════════════════════════════════════════
#  کارت بانکی
# ═══════════════════════════════════════════════════════════

def pick_card(cards):
    """
    انتخاب کارت برای پرداخت. اگر چند کارت باشد تصادفی انتخاب می‌شود
    تا تراکنش‌ها روی یک حساب متمرکز نشوند.
    """
    active = [c for c in (cards or []) if c.get("number") and c.get("active", True)]
    if not active:
        return None
    return random.choice(active)


def fmt_card(number):
    """نمایش شماره کارت به‌صورت چهار رقم چهار رقم."""
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    return "-".join(digits[i:i + 4] for i in range(0, len(digits), 4)) or number


# ═══════════════════════════════════════════════════════════
#  کمکی‌های نمایش
# ═══════════════════════════════════════════════════════════

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(v):
    """
    فارسی‌کردن ارقام یک متن.

    فقط برای چیزهایی که کاربر *می‌خواند* — نه چیزهایی که کپی می‌کند.
    شماره‌ی کارت، لینک اشتراک، کد دعوت و شناسه‌ی سفارش عمداً لاتین
    می‌مانند، چون با رقم فارسی نه در تلگرام قابل جست‌وجو می‌شوند و نه
    در اپ‌ها و درگاه‌ها درست پیست می‌شوند.
    """
    return str(v).translate(_FA_DIGITS)


#: نام ماه‌های شمسی
_FA_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
              "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")


def fa_date(value, with_month_name=True):
    """
    تاریخ شمسی برای مشتری فارسی‌زبان.

    تا قبل از این، ربات تاریخ انقضا را میلادی نشان می‌داد — مشتری
    ایرانی «۲۰۲۷-۰۱-۱۵» را نمی‌خواند و نمی‌فهمد چند روز دیگر است.

    اگر jdatetime نصب نباشد یا ورودی خراب باشد، همان میلادیِ قبلی
    برمی‌گردد؛ نمایش تاریخ نباید بتواند پیام را از کار بیندازد.
    """
    if not value:
        return ""
    raw = str(value)[:10]
    try:
        y, m, d = (int(x) for x in raw.split("-"))
    except (ValueError, TypeError):
        return fa(raw)

    try:
        import jdatetime
        from datetime import date as _date
        j = jdatetime.date.fromgregorian(date=_date(y, m, d))
        if with_month_name:
            return f"{fa(j.day)} {_FA_MONTHS[j.month - 1]} {fa(j.year)}"
        return fa(f"{j.year}/{j.month:02d}/{j.day:02d}")
    except Exception:
        return fa(raw)


def fa_datetime(value):
    """
    تاریخ شمسی به‌همراه ساعت — برای سفارش‌ها و رویدادها.

    ساعت همان‌طور می‌ماند؛ فقط بخش تاریخ شمسی می‌شود.
    """
    if not value:
        return ""
    raw = str(value).replace("T", " ")
    date_part = raw[:10]
    time_part = raw[11:16].strip()
    d = fa_date(date_part, with_month_name=False)
    return f"{d} — {fa(time_part)}" if time_part else d


def toman(n):
    """قالب‌بندی مبلغ با جداکننده‌ی هزارگان."""
    try:
        return fa(f"{int(n):,}".replace(",", "،"))
    except (TypeError, ValueError):
        return str(n)


def fmt_gb(gb):
    return "نامحدود" if not gb else f"{fa(gb)} گیگابایت"


def fmt_days(days):
    if not days:
        return "بدون محدودیت زمانی"
    if days % 30 == 0:
        return f"{fa(days // 30)} ماهه"
    return f"{fa(days)} روزه"


def plan_line(p):
    """
    دکمه‌ی پلن: **نامِ خودِ فروشگاه** + قیمت.

    مالک: «نوشته‌های پلن مطابق نوشته‌های خودم نشان داده شود». تا ۱.۱۱۸
    دکمه «نام — ۳۰ گیگ · ۳۰ روز — قیمت» بود و نامی که فروشگاه با دقت
    نوشته بود («۲۰۰ گیگ کاربر محدود ۲ ماهه») زیرِ مشخصاتِ تکراری گم می‌شد.
    مشخصات در صفحه‌ی پلن است.
    """
    return f"{p['name']} — {toman(p['price'])} تومان"


#: نوعِ پلن — همین فهرست در `frontend/src/lib/plankinds.js` (تستِ برابری)
PLAN_KINDS = (("volume", "حجمی"), ("limited", "کاربر محدود"),
              ("pro_license", "نکسورا Pro"))

#: Kinds sold from the bot only: the mini-app neither lists nor sells them.
#: A license key is shown once, in a Telegram message the buyer keeps; the
#: mini-app has no screen for it (docs/specs/2026-09-30-sell-pro.md).
BOT_ONLY_KINDS = ("pro_license",)

#: A `pro_license` plan's license: the issuer's plan names (issuer/store.py
#: SALE_PLANS) and how the buyer reads them. Parity with plankinds.js.
LICENSE_PLANS = (("monthly", "ماهانه"), ("yearly", "سالانه"))


def clean_plan_kind(v):
    return v if v in dict(PLAN_KINDS) else "volume"


def clean_license_plan(v):
    return v if v in dict(LICENSE_PLANS) else "monthly"


def clean_periods(v):
    """Periods of a license plan: months for monthly, years for yearly.
    The issuer accepts 1..120; a shop never sells more than a few."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 1
    return min(max(n, 1), 36)


def sellable(plan, root, can_sell_licenses):
    """
    May this shop offer this plan? The one rule for the bot's plan list and
    for both purchase cores (`card_order`, `wallet_purchase`).

    A Pro license is sold only by the root tenant (the owner) and only where
    the license issuer is reachable (`license_sale.available()`). A reseller's
    row of that kind, written by hand, is never offered: a button that cannot
    deliver is worse than no button.
    """
    if (plan or {}).get("kind") != "pro_license":
        return True
    return bool(root and can_sell_licenses)


def license_only(plans):
    """
    Is this a Pro store: every plan on sale is a license? Takes the plans
    already filtered by `sellable`.

    The owner sells Pro from a bot of its own, next to the issuer, not from
    the VPN bot: Pro buyers are VPN sellers, and a VPN customer should never
    meet a license button. That bot is an ordinary install whose plans are all
    licenses, so the VPN wording ("buy a subscription", install guide) is
    switched off by what is on sale rather than by a setting: a setting has
    to be found and turned on, and until then the Pro store would show a VPN
    install guide to its buyers.
    """
    kinds = {clean_plan_kind((p or {}).get("kind")) for p in plans or []}
    return kinds == {"pro_license"}


def order_delivered(order):
    """The Python side of `db.UNDELIVERED`: a config or a license exists."""
    return bool((order or {}).get("sub_id") or (order or {}).get("license_id"))


def plan_spec(p):
    """The one-line spec under a plan's name (plan page, order summary)."""
    if (p or {}).get("kind") == "pro_license":
        unit = dict(LICENSE_PLANS).get(p.get("license_plan"), "ماهانه")
        n = clean_periods(p.get("periods"))
        span = (f"{fa(n)} ماه" if p.get("license_plan") != "yearly" else f"{fa(n)} سال")
        return f"مجوز Pro برای یک سرور · {unit} · {span}"
    return f"{fmt_gb(p['gb'])} · {fmt_days(p['days'])}"


def clean_plan_tab(v):
    """تبِ مدت («۱ ماهه»، «۲ ماهه»…): یک خط، حداکثر ۲۴ نویسه."""
    return " ".join(str(v or "").split())[:24]


def plan_groups(plans):
    """
    مسیرِ خرید: نوع ← تب ← پلن. برمی‌گرداند
    [(kind, [(tab, [plans…]), …]), …] به ترتیبِ اولین پلنِ هر گروه
    (`sort_order` فروشگاه). تبِ خالی «بقیه» است.
    """
    out = []
    for p in plans or []:
        k = clean_plan_kind(p.get("kind"))
        t = clean_plan_tab(p.get("tab"))
        kg = next((g for g in out if g[0] == k), None)
        if kg is None:
            kg = (k, [])
            out.append(kg)
        tg = next((g for g in kg[1] if g[0] == t), None)
        if tg is None:
            tg = (t, [])
            kg[1].append(tg)
        tg[1].append(p)
    return out


def mins_since(when):
    """چند دقیقه از یک زمانِ محلی گذشته. نامعتبر → None."""
    if not when:
        return None
    try:
        t = datetime.fromisoformat(str(when).replace("T", " ").strip())
    except (ValueError, TypeError):
        return None
    return max(0, int((datetime.now() - t).total_seconds() // 60))


def channel_photo_dir():
    """
    پوشه‌ی عکسِ پست‌های کانال.

    **یک تعریف، دو مصرف‌کننده:** بک‌اند این‌جا می‌نویسد و زمان‌بندِ
    ربات از همین‌جا می‌خواند. اگر هر کدام پیش‌فرضِ خودش را داشت،
    اولین باری که مسیرها از هم جدا می‌شدند عکس بی‌صدا حذف می‌شد و
    پست بدونِ عکس در کانال می‌نشست — و کسی هم خطایی نمی‌دید.

    کنارِ دیتابیسِ ربات می‌نشیند، چون آن تنها مسیری است که هر دو
    پردازه قطعاً بر سرش توافق دارند.
    """
    d = os.getenv("CHANNEL_DIR")
    if d:
        return Path(d)
    db = os.getenv("BOT_DB_PATH") or os.getenv("BOT_DB")
    base = Path(db).parent if db else Path(__file__).resolve().parent.parent / "data"
    return base / "channel"


def days_left(expires_at):
    if not expires_at:
        return None
    try:
        exp = datetime.fromisoformat(expires_at)
    except (ValueError, TypeError):
        return None
    delta = exp - datetime.now()
    return max(int(delta.total_seconds() // 86400), 0) if delta.total_seconds() > 0 else 0


def days_past(expires_at):
    """
    چند روز از انقضا گذشته. اگر هنوز منقضی نشده یا تاریخ ندارد: صفر.

    days_left عمداً هیچ‌وقت منفی نمی‌دهد — ده‌ها جا روی «صفر یعنی
    تمام شده» حساب باز کرده‌اند. ولی همین یعنی با آن نمی‌شود گفت
    *چند وقت* پیش تمام شده: صفحه‌ی «اشتراک‌های من» برای هر اشتراک
    منقضی می‌نوشت «۰ روز پیش منقضی شده»، چه دیروز تمام شده بود چه
    سه ماه پیش.
    """
    if not expires_at:
        return 0
    try:
        exp = datetime.fromisoformat(expires_at)
    except (ValueError, TypeError):
        return 0
    gone = (datetime.now() - exp).total_seconds()
    return int(gone // 86400) if gone > 0 else 0


# ═══════════════════════════════════════════════════════════
#  پیش از تستِ رایگان — اپراتور، سیستم‌عامل، نام
# ═══════════════════════════════════════════════════════════
#
# برگه: docs/specs/2026-09-27-shop-funnel.md. همین فهرست‌ها را ربات
# (دکمه‌ها) و مینی‌اپ (از `/api/mini/me`) نشان می‌دهند؛ کلیدِ ناشناس رد می‌شود.

TRIAL_OPERATORS = (("mci", "همراه اول"), ("irancell", "ایرانسل"),
                   ("rightel", "رایتل"), ("other", "سایر"))
TRIAL_OS = (("android", "اندروید"), ("ios", "آیفون"),
            ("windows", "ویندوز"), ("mac", "مک"))


def trial_info_missing(user, settings):
    """
    کدام اطلاعاتِ پیش از تست هنوز نیست: زیرمجموعه‌ی
    («operator»، «device_os»، «real_name»)، به همین ترتیب. فروشگاهی که
    `trial_ask_info` را خاموش کرده چیزی نمی‌پرسد.
    """
    if not (settings or {}).get("trial_ask_info", True):
        return []
    u = user or {}
    return [k for k in ("operator", "device_os", "real_name") if not u.get(k)]


def clean_real_name(raw):
    """نامِ تایپی: ۲ تا ۴۰ نویسه، بی لینک و بی @ — یا None."""
    t = " ".join(str(raw or "").split())
    if not 2 <= len(t) <= 40:
        return None
    low = t.lower()
    if "http" in low or "t.me" in low or "@" in t or "/" in t:
        return None
    return t


# ═══════════════════════════════════════════════════════════
#  پیگیریِ تست — ۰، ۸، ۱۶ و ۲۴ ساعت، و «خرید موفق»
# ═══════════════════════════════════════════════════════════
#
# متن‌ها از پیامِ خودِ مالک آمده‌اند (docs/specs/2026-09-27-shop-funnel.md)؛
# هر فروشگاه `trial_msg_*` خودش را می‌گذارد. `{name}` اسمی است که مشتری پیش
# از تست نوشت (وگرنه نامِ تلگرامش)، `{brand}` نامِ فروشگاه.

TRIAL_POLL_8 = (("great", "😍 عالی"), ("good", "👍 خوب"),
                ("ok", "😐 معمولی"), ("bad", "🔴 مشکل داشتم"))
TRIAL_POLL_16 = (("speed", "⚡ سرعت"), ("stable", "🛡️ پایداری"),
                 ("connect", "🌐 اتصال"), ("happy", "💙 رضایت"))

#: ساعت‌های پیگیری بعد از گرفتنِ تست → شماره‌ی قدم
TRIAL_STEPS = ((8, 1), (16, 2), (24, 3))

TRIAL_MSG_DEFAULTS = {
    "trial_msg_0": ("🎁 {name}، تست {brand} برات فعال شد 💙\n\n"
                    "یه مقدار باهاش کار کن و سرعت و پایداریش رو خودت امتحان کن.\n"
                    "هر مشکلی هم داشتی، همین‌جا بهمون بگو 🤝☁️"),
    "trial_msg_8": ("سلام {name} 🌷\n"
                    "تا اینجا فرصت کردی تست {brand} رو امتحان کنی؟ 😊\n\n"
                    "سرعت و اتصالش چطور بوده؟"),
    "trial_msg_8_bad": ("متأسفیم که تجربه خوبی نداشتی {name} 🙏\n"
                        "بگو دقیقاً چه مشکلی داشتی تا بررسیش کنیم 🤝💙"),
    "trial_msg_16": ("یه سؤال کوچیک ازت داریم {name} 🌷\n\n"
                     "اگه بخوای {brand} رو با یه کلمه توصیف کنی، نظرت چیه؟ 😄"),
    "trial_msg_24": ("{name}، تستت به پایان رسید\n"
                     "اگر از تست راضی بودی و دوست داشتی ادامه بدی 💙\n\n"
                     "می‌تونی سرویس موردنظرت رو مستقیم از مینی‌اپ {brand} انتخاب و خرید کنی 👇\n\n"
                     "🛒 خرید سریع و آنلاین\n"
                     "☁️ بدون نیاز به پیام دادن به پشتیبانی"),
    # نظرسنجیِ چند روز بعد از خرید و تمدید (فاز ۳) — همان چهار دکمه‌ی کیفیت
    "fb_msg_buy": ("سلام {name} 🌷\n"
                   "چند روزه که اشتراک {brand} رو داری — راضی هستی؟ 😊\n\n"
                   "سرعت و اتصالش چطور بوده؟"),
    "fb_msg_renew": ("{name}، ممنون که دوباره {brand} رو انتخاب کردی 💙\n\n"
                     "این دوره سرعت و اتصالش چطور بوده؟"),
    "trial_msg_bought": ("💙 {name}، خریدت با موفقیت انجام شد!\n\n"
                         "اشتراکت آماده‌ست و اطلاعات اتصال داخل مینی‌اپ برات قرار گرفته. ✅\n\n"
                         "اگر برای اتصال مشکلی داشتی، پشتیبانی کنارت هست 🤝☁️"),
}


#: نظرسنجی‌های بعد از خرید و تمدید — و چند روز بعد
FEEDBACK_KINDS = ("buy", "renew")
FEEDBACK_AFTER_DAYS = 3

#: «رضایت» از چند نظر به بالا به مشتری نشان داده می‌شود
SATISFACTION_MIN = 10


def satisfaction_line(sat):
    """خطِ «رضایت» برای بالای پلن‌ها — یا خالی اگر هنوز نظرِ کافی نیست."""
    if not sat:
        return ""
    return f"⭐ {fa(sat['pct'])}٪ از مشتری‌ها راضی‌اند — {fa(sat['n'])} نظر"


def trial_msg(settings, key, name="", brand="", esc=lambda x: x):
    """متنِ یک قدمِ پیگیری از قالبِ فروشگاه — با اسمِ خودِ مشتری."""
    tpl = str((settings or {}).get(key) or "").strip() or TRIAL_MSG_DEFAULTS[key]
    return tpl.replace("{name}", esc(name or "دوست عزیز")).replace("{brand}", esc(brand))


def trial_due_step(hours_since, sent_step):
    """
    قدمی که الان باید فرستاده شود، یا 0. اگر ربات مدتی پایین بوده و چند قدم
    عقب افتاده، فقط **آخرین** قدمِ رسیده فرستاده می‌شود — نه سه پیام پشتِ هم.
    """
    due = 0
    for h, step in TRIAL_STEPS:
        if hours_since >= h:
            due = step
    return due if due > int(sent_step or 0) else 0


#: پیامِ تحویلِ پیش‌فرض — به سبکِ متنی که مالک خودش نوشت. هر فروشگاه
#: `delivered_text` خودش را می‌گذارد؛ جای‌گذارها در `delivered_message`.
DELIVERED_DEFAULT = (
    "🔑 اشتراک شما با موفقیت {title}.\n\n"
    "👤 نام کاربری شما:\n{username}\n\n"
    "🔗 لینک اشتراک شما:\n{link}\n\n"
    "📌 لطفاً لینک بالا رو کپی کنید و داخل برنامه مورد استفاده‌تون وارد کنید.\n\n"
    "{channel_block}"
    "💙 ممنون که {brand} رو انتخاب کردید."
)


def delivered_message(template, *, title, name, username, link, brand,
                      channel="", plan="", gb="", expires="", esc=lambda x: x):
    """
    متنِ تحویل از قالبِ فروشگاه. همه‌ی مقدارها پیش از جای‌گذاری escape
    می‌شوند (HTML تلگرام)؛ نام و لینک در `<code>` تا با یک لمس کپی شوند.

    `{channel_block}` وقتی فروشگاه کانال ندارد خالی است — نه یک «📢 کانال:»
    بی‌نشانی.
    """
    ch = str(channel or "").strip()
    if ch and not ch.startswith("@") and "t.me/" not in ch:
        ch = "@" + ch
    block = f"📢 کانال {esc(brand)}:\n☁️ {esc(ch)}\n\n" if ch else ""
    vals = {
        "{title}": esc(title), "{name}": esc(name),
        "{username}": f"<code>{esc(username)}</code>" if username else "—",
        "{link}": f"<code>{esc(link)}</code>" if link else "—",
        "{sub_url}": f"<code>{esc(link)}</code>" if link else "—",
        "{brand}": esc(brand), "{channel}": esc(ch), "{channel_block}": block,
        "{plan}": esc(plan), "{gb}": esc(gb), "{expires}": esc(expires),
    }
    out = str(template or DELIVERED_DEFAULT)
    for k, v in vals.items():
        out = out.replace(k, v)
    return out


def make_email(tenant_prefix, seq):
    """
    ساخت شناسه‌ی کلاینت در 3x-ui: `پیشوند_شماره` — مثلاً `shop_200`.

    پیشوند می‌ماند چون صفحه‌ی اشتراک برندِ فروشگاه را از تکه‌ی پیش از
    اولین `_` تشخیص می‌دهد. شماره یک شمارنده‌ی ترتیبیِ همان فروشگاه است
    (`TenantDB.next_name_seq`).

    تا ۱.۱۱۷ `prefix_<آیدیِ عددیِ تلگرام>_<n>` بود — مالک: «این کلی شماره
    نوشته»؛ `shop_26041224_1` برای مشتری و پشتیبانی خواندنی نبود.
    """
    prefix = "".join(ch for ch in (tenant_prefix or "nx") if ch.isalnum()).lower()[:12]
    return f"{prefix or 'nx'}_{int(seq)}"


def normalize_phone(raw):
    """
    یکسان‌سازی شماره‌ی ایرانی به شکل 98XXXXXXXXXX.

    تلگرام گاهی با +، گاهی بدون، و گاهی با 0 ابتدایی می‌دهد.
    بدون یکسان‌سازی، یک نفر می‌تواند با چند شکل ثبت شود.
    """
    d = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if d.startswith("0098"):
        d = d[2:]
    elif d.startswith("098"):
        d = d[1:]
    elif d.startswith("09"):
        d = "98" + d[1:]
    elif d.startswith("9") and len(d) == 10:
        d = "98" + d
    return d


def pretty_phone(p):
    """نمایش خوانا: 98912... → 0912 123 4567"""
    d = normalize_phone(p)
    if d.startswith("98") and len(d) == 12:
        n = "0" + d[2:]
        return f"{n[:4]} {n[4:7]} {n[7:]}"
    return d or "—"


# ═══════════════════════════════════════════════════════════
#  افزونه‌های پولیِ نماینده — پوسته، و اشتراکِ فروشگاه
# ═══════════════════════════════════════════════════════════
#
# برگه: docs/specs/2026-09-26-reseller-store-subscription.md
#
# این قاعده **فقط این‌جا** نوشته شده. بکند (پرتال، مینی‌اپ) و ربات هر دو
# همین را صدا می‌زنند؛ پیش‌تر پوسته قاعده‌ی خودش را در app.py داشت و
# نسخه‌ی دوم برای ربات یعنی همان باگی که این مخزن هفت بار خورده.

#: نوع → (کلیدِ قیمت در تنظیماتِ ریشه، کلیدِ تاریخ در تنظیماتِ نماینده)
ADDONS = {
    "theme": ("portal_addon", "theme_until"),
    "store": ("store_addon", "store_until"),
}

#: همان جمله در ربات و مینی‌اپ — مشتری نباید دو توضیح ببیند
STORE_CLOSED = ("فروشِ این فروشگاه موقتاً متوقف است. "
                "لطفاً کمی بعد دوباره سر بزنید یا به پشتیبانی پیام بدهید.")


#: «نامحدود» فروشگاه‌های حجمی چند گیگ است، اگر مالک عددی نگذاشته
UNLIMITED_GB_DEFAULT = 200


def unlimited_gb(root_settings):
    """نامحدود = چند گیگ، از تنظیمِ مالک (`unlimited_gb`). بکند هم همین را صدا می‌زند."""
    try:
        v = int((root_settings or {}).get("unlimited_gb") or 0)
    except (TypeError, ValueError, AttributeError):
        v = 0
    return v if v > 0 else UNLIMITED_GB_DEFAULT


def unlimited_cap(plan_gb, tenant_settings):
    """
    حجمی که کانفیگِ یک پلن واقعاً با آن ساخته می‌شود.

    فروشگاهِ نماینده‌ای که نرخش حجمی است، «نامحدود» را با سقفِ منصفانه
    می‌سازد (مالک: «نامحدودی که ما تعریف می‌کنیم ۲۰۰ گیگ است»). بکند
    `unlimited_cap_gb` را در تنظیماتِ همان فروشگاه می‌نویسد؛ فروشگاهِ
    پله‌ای آن را ندارد و نامحدودش بی‌سقف می‌ماند — آن‌جا سقف قیمتِ
    صورتحساب را از پله‌ی «نامحدود» به پله‌ی ۲۰۰ گیگ می‌برد.
    """
    try:
        gb = int(plan_gb or 0)
        cap = int((tenant_settings or {}).get("unlimited_cap_gb") or 0)
    except (TypeError, ValueError, AttributeError):
        return int(plan_gb or 0) if str(plan_gb or "").isdigit() else 0
    return cap if gb <= 0 and cap > 0 else gb


def addon_config(root_settings, kind):
    """
    قیمت و مدتِ یک افزونه از تنظیماتِ مالک: {"price": تومان, "days": روز}.

    قیمتِ صفر یعنی **رایگان برای همه**، نه «تعریف‌نشده» — و پیش‌فرض همین
    است، تا به‌روزرسانی فروشِ هیچ نماینده‌ای را بی‌خبر قطع نکند.
    """
    key = ADDONS[kind][0]
    st = (root_settings or {}).get(key) if isinstance(root_settings, dict) else None
    st = st if isinstance(st, dict) else {}
    try:
        price = max(0, int(st.get("price") or 0))
        days = max(1, int(st.get("days") or 30))
    except (TypeError, ValueError):
        price, days = 0, 30
    return {"price": price, "days": days}


def addon_blocked_key(kind):
    """کلیدِ «مالک دستی بسته» در تنظیماتِ نماینده — مثلاً `store_off`."""
    return f"{kind}_off"


def addon_open(tenant_settings, parent_id, price, kind, now=None):
    """
    آیا این مستاجر الان این افزونه را دارد؟

    فروشگاهِ خودِ مالک (بی‌والد) هرگز قفل نیست. قفلِ دستیِ مالک بر همه‌چیز
    مقدم است. قیمتِ صفر یعنی برای همه باز. وگرنه تاریخ؛ تاریخِ نخواندنی یعنی
    **بسته** — بازِ بی‌صدا یعنی فروشِ رایگان، و این‌جا اشتباه به ضررِ مالک
    است نه نماینده.

    چرا قفلِ دستی: تا ۱.۱۱۴ «ببند» فقط تاریخ را پاک می‌کرد. با قیمتِ صفر
    تاریخ اصلاً خوانده نمی‌شد، پس «ببند» و «باز کن» هیچ اثری نداشتند —
    مالک: «دکمه‌های باز و بسته‌اش اصلاً کار نمی‌کند».
    """
    if not parent_id:
        return True
    if (tenant_settings or {}).get(addon_blocked_key(kind)):
        return False
    if int(price or 0) <= 0:
        return True
    until = str((tenant_settings or {}).get(ADDONS[kind][1]) or "")
    if not until:
        return False
    try:
        return datetime.fromisoformat(until[:19]) > (now or datetime.now())
    except (TypeError, ValueError):
        return False
