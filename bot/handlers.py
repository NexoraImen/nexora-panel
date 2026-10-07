"""
جریان‌های کاربری ربات.

هر handler یک تابع ساده است که (ctx, update) می‌گیرد.
ctx شامل bot، db، tenant و settings است.
"""

import json
import os
import time
import logging
from pathlib import Path
from datetime import datetime

from tg import (kb, esc, TelegramError, Bot, contact_kb, remove_kb,
                valid_button_url)
import core
import db as DB
import fmt as F          # واژگان قالب‌بندی تلگرام — F.b، F.code، F.quote و…
import events as EV   # نگاشتِ نوعِ رویداد → برچسب و هشدار
import license_sale as LS   # Pro licenses sold by the owner's bot (Phase 4)
from xui import XUI, XUIError
import qr

log = logging.getLogger("nexora.bot")


# ── Pro areas ── docs/specs/2026-09-29-pro-split.md ───────────────────────
# bot/pro/<area>.py, loaded by path. Never `import pro`: backend/ has a `pro`
# folder too, and which one a bare import found would depend on sys.path
# order, which differs between the bot, the panel and each test.
PRO_DIR = Path(os.getenv("NEXORA_PRO_BOT_DIR",
                         str(Path(__file__).resolve().parent / "pro")))
_PRO = {}


def pro(area):
    """The Pro module for `area`, or None in the Community edition (no file).
    A file that is present but fails to import raises: Pro code that is there
    but silently not running is the worst of both editions."""
    if area in _PRO:
        return _PRO[area]
    f = PRO_DIR / f"{area}.py"
    if not f.is_file():
        _PRO[area] = None
        return None
    import importlib.util
    import sys
    name = f"nexora_pro_bot_{area}"
    spec = importlib.util.spec_from_file_location(name, f)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    _PRO[area] = mod
    return mod


def _license():
    # The same backend/license.py the panel runs; one copy, so the bot and the
    # panel can never disagree about the license.
    import sys
    if "license" in sys.modules:
        return sys.modules["license"]
    import importlib.util
    f = Path(__file__).resolve().parent.parent / "backend" / "license.py"
    spec = importlib.util.spec_from_file_location("license", f)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["license"] = mod
    spec.loader.exec_module(mod)
    return mod


def pro_allowed(feature):
    """True when the Pro code for `feature` may run now. A broken license
    module locks Pro (logged), never the core."""
    try:
        return _license().allowed(feature)
    except Exception:
        log.exception("license check failed; Pro stays locked")
        return False


# ═══════════════════════════════════════════════════════════
#  Context — هر مستاجر یک نمونه دارد
# ═══════════════════════════════════════════════════════════

class Ctx:
    """
    زمینه‌ی یک درخواست.

    نکته‌ی مهم درباره‌ی بازخوانی زنده: تنظیمات و اطلاعات مستاجر هر بار
    تازه خوانده می‌شوند، پس تغییرات پنل بدون ری‌استارت ربات اعمال می‌شوند.
    فقط اتصال 3x-ui کش می‌شود (چون لاگین هزینه دارد) و آن هم وقتی
    اطلاعات اتصال عوض شود، خودکار دور ریخته می‌شود.
    """

    #: چند ثانیه تنظیمات را کش کنیم.
    #
    # صفر یعنی رفتار قبلی: هر دسترسی یک اتصال SQLite جدید، یک کوئری
    # و یک json.loads. و `ctx.s` در handlers حدود ۳۱ جا صدا زده
    # می‌شود — یعنی یک پیام ساده‌ی کاربر ده‌ها بار دیسک را می‌خورد.
    # اندازه‌گیری‌شده: ۲ms هر بار روی SSD، ۶۲ms برای یک پیام؛ روی
    # دیسک اشتراکی سرور مجازی چند برابر.
    #
    # دو ثانیه به‌اندازه‌ی کافی کوتاه است که تغییر تنظیمات در پنل
    # عملاً فوری دیده شود، و به‌اندازه‌ی کافی بلند که در طول پردازش
    # یک پیام فقط یک بار خوانده شود.
    CACHE_TTL = float(os.getenv("BOT_CTX_CACHE", "2"))

    def __init__(self, bot, tenant):
        self.bot = bot
        self._tenant0 = tenant
        self.tid = tenant["id"]
        self.db = DB.TenantDB(tenant["id"])
        self._xui = None
        self._xui_sig = None
        self._t_cache = None
        self._t_at = 0.0
        self._s_cache = None
        self._s_at = 0.0
        self._in_cache = None
        self._in_at = 0.0

    def invalidate(self):
        """دور ریختن کش — بعد از هر تغییری که خودمان در تنظیمات دادیم."""
        self._t_cache = self._s_cache = None
        self._t_at = self._s_at = 0.0

    @property
    def tenant(self):
        """اطلاعات مستاجر، با کش کوتاه."""
        now = time.time()
        if self._t_cache is None or now - self._t_at > self.CACHE_TTL:
            self._t_cache = DB.get_tenant(self.tid) or self._tenant0
            self._t_at = now
        return self._t_cache

    @property
    def s(self):
        """تنظیمات مستاجر، با کش کوتاه."""
        now = time.time()
        if self._s_cache is None or now - self._s_at > self.CACHE_TTL:
            self._s_cache = DB.tenant_settings(self.tid)
            self._s_at = now
        return self._s_cache

    @property
    def xui(self):
        # نماینده پنلِ جدا ندارد — به پنلِ مالک وصل می‌شود و کانفیگ‌هایش
        # با گروهِ خودش جدا می‌شوند. دلیلِ کامل در `DB.panel_source`.
        t = DB.panel_source(self.tenant) or self.tenant
        # امضای اتصال — اگر عوض شود یعنی ادمین تنظیمات پنل را تغییر داده
        sig = (t.get("panel_url"), t.get("panel_user"),
               t.get("panel_pass"), t.get("panel_token"))
        if self._xui is None or self._xui_sig != sig:
            self._xui = XUI(*sig)
            self._xui_sig = sig
        return self._xui

    def brand(self):
        return self.s.get("brand") or self.tenant.get("name") or "VPN"

    #: نام اینباندها با کش بلندتر — روی پنل تقریباً هرگز عوض نمی‌شوند
    INBOUND_TTL = 300.0

    def inbound_names(self):
        """
        {شناسه‌ی اینباند: نام قابل‌خواندن} از پنل ۳x-ui.

        بدون این، مشتری‌ای که سه اشتراک روی سه سرور دارد سه بار
        «یک‌ماهه پرسرعت» می‌بیند و نمی‌فهمد کدام کدام است. نام اینباند
        (remark) همان چیزی است که خودِ مدیر روی سرور گذاشته — «آلمان»،
        «فنلاند» — و دقیقاً همان است که مشتری باید ببیند.

        اگر پنل در دسترس نباشد دیکشنری خالی برمی‌گردد؛ نام سرور یک
        زینت است و نبودش نباید پیام را از کار بیندازد.
        """
        now = time.time()
        if self._in_cache is not None and now - self._in_at <= self.INBOUND_TTL:
            return self._in_cache
        names = {}
        try:
            for ib in (self.xui.inbounds() or []):
                if not isinstance(ib, dict):
                    continue
                iid = ib.get("id")
                remark = (ib.get("remark") or "").strip()
                if iid is not None and remark:
                    names[int(iid)] = remark
        except Exception:
            log.debug("نام اینباندها خوانده نشد", exc_info=True)
        self._in_cache, self._in_at = names, now
        return names

    def sub_label(self, sub, with_plan=True, plan_name=None):
        """
        نام یکتا و خوانای یک اشتراک.

        ترتیب: نام پلنی که مشتری خریده، بعد شماره‌ی خودِ کانفیگ
        (nexora_555_2 → «کانفیگ ۲»).

        نام اینباند فقط وقتی می‌آید که تنها یک اینباند در کار نباشد.
        قبلاً برعکس بود — نام اینباند *به‌جای* شماره‌ی کانفیگ می‌نشست:

            یک‌ماهه · پنل جدید
            یک‌ماهه · پنل جدید
            یک‌ماهه · پنل جدید

        چون همه‌ی کانفیگ‌ها روی یک اینباند مشترک‌اند، هر سه اشتراکِ
        مشتری دقیقاً یک اسم می‌گرفتند و صفحه‌ی تمدید نمی‌گفت کدام را
        دارد تمدید می‌کند. آن اسم هم مال پنل بود، نه چیزی که مشتری
        خریده باشد.

        plan_name را وقتی می‌دهیم که ردیف اشتراک از یک SELECT خام آمده
        باشد و ستون plan_name نداشته باشد — وگرنه «اشتراک» می‌نویسد.
        """
        parts = []
        if with_plan:
            # نام ثبت‌شده‌ی خود اشتراک اول می‌آید — همان چیزی که
            # مشتری خریده. اگر پلن بعداً حذف شود، این می‌ماند.
            parts.append(str(sub.get("plan_name") or plan_name or "اشتراک"))

        # شناسه‌ی خودِ کانفیگ — این چیزی است که دو اشتراک را از هم
        # جدا می‌کند، چون روی یک اینباند هم یکتاست.
        email = str(sub.get("client_email") or "")
        tail = email.rsplit("_", 1)[-1] if "_" in email else ""
        if tail.isdigit():
            parts.append(f"کانفیگ {core.fa(tail)}")

        # نام سرور فقط وقتی اطلاعات اضافه می‌کند که بیش از یک اینباند
        # داشته باشیم؛ با یک اینباند، برای همه یکی است و فقط طولش
        # می‌کند.
        iid = sub.get("inbound_id")
        if iid is not None:
            try:
                names = self.inbound_names()
                if len(names) > 1 and names.get(int(iid)):
                    parts.append(names[int(iid)])
            except (TypeError, ValueError) as _exc:
                log.debug("sub_label step: %s", _exc)

        return " · ".join(parts) if parts else "اشتراک"

    def is_admin(self, tg_id):
        """
        تشخیص ادمین.

        نکته: owner_tg_id از فرم پنل می‌آید و ممکن است رشته باشد،
        در حالی که تلگرام همیشه عدد می‌فرستد. پس هر دو را به عدد
        تبدیل می‌کنیم تا مقایسه درست انجام شود — این باگی بود که
        باعث می‌شد ادمین اصلاً شناخته نشود.
        """
        def as_int(v):
            try:
                return int(str(v).strip())
            except (TypeError, ValueError):
                return None

        me = as_int(tg_id)
        if me is None:
            return False

        t = DB.get_tenant(self.tid)
        if as_int(t.get("owner_tg_id")) == me:
            return True

        for a in (self.s.get("admins") or []):
            if as_int(a) == me:
                return True
        return False

    #: اعلان‌هایی که اگر گروه نباشد به پیویِ صاحبِ ربات می‌روند.
    #
    # فقط آن‌هایی که کسی منتظرِ جوابشان است: رسید (مشتری پول داده)،
    # هشدار (پولِ مشتری معلق مانده)، و پیامِ پشتیبانی. عضوِ تازه و
    # آمار نه — اینها در گروه خوب‌اند، در پیوی سیل.
    DM_TOPICS = ("receipts", "alerts", "tickets")

    def staff_chat(self, topic=None):
        """
        (chat_id, topic_id) برای اعلانِ مدیریتی.

        اول گروهِ مدیریت. اگر نیست و اعلان از آن‌هایی است که کسی
        منتظرش است، پیویِ صاحبِ ربات — که نماینده با یک دکمه در پرتال
        خودش را به آن وصل می‌کند (`own_` در `/start`).

        هر دو مسیر از همین‌جا رد می‌شوند؛ نسخه‌ی دومی از «کجا بفرستم»
        یعنی روزی یکی‌شان پیوی را فراموش می‌کند.
        """
        t = DB.get_tenant(self.tid) or {}
        gid = t.get("admin_group_id")
        if gid:
            try:
                topics = json.loads(t.get("topics") or "{}")
            except json.JSONDecodeError:
                topics = {}
            return gid, topics.get(topic)
        if topic in self.DM_TOPICS and t.get("owner_tg_id"):
            return t["owner_tg_id"], None
        return None, None

    def notify_group(self, text, keyboard=None, topic=None, photo=None):
        """
        ارسال به گروه مدیریت در تاپیک مشخص — یا پیویِ صاحبِ ربات.

        `photo` بایت‌های تصویر است و متن به زیرنویسش می‌رود. چرا
        این‌جا و نه یک تابع دوم: پیداکردنِ گروه و تاپیک همین‌جاست و
        نسخه‌ی دومی از آن یعنی روزی یکی‌شان تاپیک را فراموش می‌کند.
        """
        gid, tpid = self.staff_chat(topic)
        if not gid:
            return None
        try:
            if photo:
                return self.bot.send_photo_bytes(
                    gid, photo, filename="photo.jpg",
                    # زیرنویسِ تلگرام ۱۰۲۴ کاراکتر است، نه ۴۰۹۶.
                    # بلندتر که باشد، کلِ ارسال رد می‌شود — نه اینکه
                    # کوتاه شود.
                    caption=text[:1000], keyboard=keyboard,
                    topic_id=tpid)
            return self.bot.send(gid, text, keyboard=keyboard,
                                 topic_id=tpid)
        except TelegramError as e:
            log.warning("ارسال به گروه ناموفق: %s", e)
            return None


# ═══════════════════════════════════════════════════════════
#  رویدادها — یک درِ ورودی، نه دو
# ═══════════════════════════════════════════════════════════

def record(ctx, kind, user_id=None, data=None, who=None):
    """
    ثبتِ رویداد، و اگر پولِ مشتری معلق مانده، خبرکردنِ گروه.

    چرا یک تابع و نه دو خط در هر جای شکست:
        اگر «ثبت کن» و «گروه را خبر کن» جدا نوشته شوند، جای
        هفدهم یکی‌شان را فراموش می‌کند — و آن یکی همیشه همانی
        است که مالک لازمش دارد. این‌جا `EV.is_alert` تصمیم
        می‌گیرد، نه صداکننده.

    هیچ‌وقت خطا بالا نمی‌برد: از داخلِ `except` صدا زده می‌شود و
    یک خطای فرعی نباید جای خطای اصلی را بگیرد.
    """
    try:
        ctx.db.log(kind, user_id, data)
    except Exception:
        log.debug("ثبت رویداد ناموفق (%s)", kind, exc_info=True)

    if not EV.is_alert(kind):
        return
    try:
        ctx.notify_group(EV.alert_text(kind, data, who=esc(who) if who else None))
    except Exception:
        # گروه خبردار نشد؛ ولی ردیفِ جدول سرِ جایش است. دو مسیرِ
        # جدا، تا شکستِ یکی دیگری را نبرد.
        log.debug("هشدار گروه ناموفق (%s)", kind, exc_info=True)


# ═══════════════════════════════════════════════════════════
#  منوها
# ═══════════════════════════════════════════════════════════

def miniapp_url(ctx):
    """
    آدرس مینی‌اپ. برمی‌گرداند: رشته‌ی https یا "" .

    مقدارش را **خودِ پنل** می‌نویسد: اولین باری که مدیر پنل را روی
    https باز می‌کند، بک‌اند دامنه‌ی خودش را از هدر Host می‌بیند و
    `https://<همان دامنه>/app` را این‌جا ثبت می‌کند. مینی‌اپ از همان
    `frontend/dist` سرو می‌شود که پنل، و nginx هم `try_files` دارد،
    پس `/app` بدون هیچ تنظیم تازه‌ای بالا می‌آید.

    چرا خودکار: تنظیمی که باید آدم پرش کند، پر نمی‌شود — و آن‌وقت
    قابلیتی داریم که ساخته شده و هیچ‌کس نمی‌بیندش. همان چیزی که سر
    پنل نمایندگی افتاد (ساخته شد و هیچ دکمه‌ای به آن نمی‌رسید) و سر
    اینباند پیش‌فرض (تنظیم نبود و کلِ ساخت کانفیگ می‌خوابید).

    چرا از `sub_base_url` ساخته نمی‌شود: آن آدرسِ سرویسِ اشتراکِ
    x-ui است و معمولاً روی پورت دیگری می‌نشیند. حدس‌زدن از رویش
    آدرسی می‌سازد که صفحه‌ی سفید می‌دهد — بدتر از نبودنِ دکمه.

    تلگرام فقط https را می‌پذیرد و با http خودِ *پیام* را رد می‌کند —
    نه فقط دکمه را. پس هر چیزی که https نباشد این‌جا دور ریخته
    می‌شود، نه این‌که به تلگرام برسد و کل منو را از کار بیندازد.
    """
    url = str(ctx.s.get("miniapp_url") or "").strip()
    if not url.lower().startswith("https://"):
        return ""
    # The mini app is Pro (`mini_app`). Locked, every button that would open
    # it disappears; the bot menu does everything the mini app does.
    if not pro_allowed("mini_app"):
        return ""
    url = url.rstrip("/")
    # شناسه‌ی فروشگاه در آدرس — فقط کلیدِ کشِ ظاهر، نه احراز هویت (آن
    # از امضای initData است). همه‌ی فروشگاه‌ها یک /app دارند؛ بی این،
    # مینی‌اپ پیش از رسیدنِ پاسخ نمی‌دانست مالِ کیست: بارِ اول با رنگِ
    # پیش‌فرضِ نکسورا بالا می‌آمد و بعد به پوسته‌ی فروشگاه می‌پرید، و
    # مشتری‌ای که از دو ربات می‌خرید اسپلشِ فروشگاهِ دیگر را می‌دید.
    tid = getattr(ctx, "tid", None)
    if tid is not None and "shop=" not in url:
        url += ("&" if "?" in url else "?") + f"shop={int(tid)}"
    return url


# برچسبِ دکمه‌ی تست — پیش‌نمایش و تست‌ها هم همین را می‌خوانند
TRIAL_BUTTON = "🎁 دریافت تست رایگان"


def trial_offer(ctx, user):
    """
    آیا به این کاربر تستِ رایگان پیشنهاد می‌شود؟ — یک قاعده برای دکمه‌ی منو
    و خطِ پررنگِ پیامِ خوش‌آمد، تا یکی بی دیگری نیاید.

    فقط وقتی پلنِ تستی هست: «روشن» بدونِ پلن، دکمه‌ای می‌ساخت که جوابش «فعلاً
    فعال نیست» بود. و هر کاربر یک‌بار — چه از ربات گرفته باشد چه از مینی‌اپ،
    چون هر دو از `trial_core` و همان پرچمِ `trial_used` می‌گذرند.
    """
    # An admin always sees it and can take it again: the owner had used his
    # own trial while testing, so the button he had just switched on never
    # appeared for him and he had no way to see what a new customer sees.
    return bool(ctx.s.get("trial_enabled")
                and (not user.get("trial_used") or ctx.is_admin(user["tg_id"]))
                and ctx.db.trial_plan())


def main_menu(ctx, user):
    # ترتیب بر اساس کاری که کاربر بیشتر می‌آید انجام دهد:
    # خرید، بعد دیدن وضعیت، بعد بقیه
    # A Pro store (`core.license_only`) says licenses where a VPN shop says
    # subscriptions, and has no install guide: its guide is about VPN apps.
    lic = _license_store(ctx)
    rows = [
        [("🛒 خرید نکسورا Pro" if lic else "🛒 خرید اشتراک", "buy")],
        [("🔑 مجوزهای من" if lic else "📊 اشتراک‌های من", "mysubs"),
         ("👛 کیف پول", "wallet")],
        [("🧾 سفارش‌های من", "myorders")],
    ]
    # Inviting friends earns coins: Pro (`loyalty`). Without it the coins
    # button stays for anyone who still has coins to spend.
    if loyalty_on():
        rows.insert(2, [("🎁 دعوت دوستان", "ref"), ("🪙 سکه‌های من", "coins")])
    elif (user.get("coins") or 0) > 0:
        rows.insert(2, [("🪙 سکه‌های من", "coins")])
    # پنل همکار فقط به کسی نشان داده می‌شود که واقعاً همکار است — and only
    # while the partner program (Pro, `affiliates`) is on
    try:
        if affiliates_on() and DB.affiliate_by_tg(ctx.tid, user["tg_id"]):
            rows.append([("💼 پنل همکاری در فروش", "affiliate")])
    except Exception as _exc:
        log.debug("main_menu step: %s", _exc)

    # مینی‌اپ.
    #
    # *اضافه* بر منو، نه جایگزینِ چیزی. مینی‌اپ از دامنه‌ی ما بارگذاری
    # می‌شود و مشتری‌های ما همان کسانی‌اند که اینترنتشان محدود است.
    # اگر آن صفحه بالا نیاید، تلگرام چیزی نمی‌گوید و کاربر صفحه‌ی سفید
    # می‌بیند — پس هر کاری که از مینی‌اپ می‌شود کرد، باید از همین منو
    # هم بشود.
    app_url = miniapp_url(ctx)
    if app_url:
        rows.insert(0, [("📱 اپلیکیشن", app_url, "web_app", "primary")])

    # تستِ رایگان بالای همه — اولین چیزی که کسی که هنوز چیزی نخریده
    # می‌بیند — و سبز (مالک: «وقتی ربات باز می‌شود دکمه‌ی اشتراک رایگان
    # باشد و توجه را بگیرد»). دکمه پررنگ نمی‌شود؛ رنگ و جای اول کارِ پررنگی
    # را می‌کنند و خطِ پررنگِ پیامِ خوش‌آمد به آن اشاره می‌کند.
    if trial_offer(ctx, user):
        rows.insert(0, [(TRIAL_BUTTON, "trial", None, "success")])
    rows.append(([] if lic else [("📚 آموزش نصب", "help")]) + [("💬 پشتیبانی", "support")])
    if ctx.is_admin(user["tg_id"]):
        rows.append([("⚙️ پنل مدیریت", "admin")])
    return kb(rows)


def back_kb(to="menu"):
    return kb([[("‹ بازگشت", to)]])


def welcome_text(ctx, user):
    """
    پیام خوش‌آمد با وضعیت زنده.

    به‌جای یک متن ثابت، وضعیت واقعی کاربر را نشان می‌دهد: اشتراک فعال،
    روزهای باقی‌مانده، سکه و کیف پول. این‌طور کاربر با یک نگاه می‌فهمد
    کجاست و چه کاری باید بکند.
    """
    name = esc(user.get("first_name") or "دوست عزیز")
    brand = esc(ctx.brand())

    # خطِ پررنگِ تست — متنِ دکمه نمی‌تواند پررنگ باشد، متنِ پیام می‌تواند
    offer = (F.b("🎁 تست رایگان داریم!") + " هر نفر یک‌بار و بدون پرداخت. "
             "از دکمه‌ی سبزِ بالا بگیرید.") if trial_offer(ctx, user) else ""
    # The mini app, suggested to everyone who has one (task 6): the owner
    # wants buyers there, and a button alone was easy to miss.
    if miniapp_url(ctx):
        app_line = ("📱 کار با " + F.b("اپلیکیشن") + " راحت‌تر است: خرید، تمدید، "
                    "اشتراک‌ها و گفتگو با پشتیبانی همه آن‌جاست.")
        offer = f"{offer}\n\n{app_line}" if offer else app_line

    custom = ctx.s.get("welcome_text")
    if custom:
        text = custom.replace("{name}", name).replace("{brand}", brand)
        return f"{text}\n\n{offer}" if offer else text

    subs = ctx.db.user_subs(user["id"], active_only=True)
    coins = user.get("coins", 0)
    balance = user.get("balance", 0)

    lines = [f"سلام {name} 👋", f"به {brand} خوش آمدید.", ""]
    if offer:
        lines += [offer, ""]

    if subs:
        # چند اشتراک یعنی چند سرور. اگر فقط «۱۲ روز باقی مانده» بنویسیم،
        # مشتری نمی‌داند حرف از کدام است — پس همه را با نامشان می‌آوریم.
        shown = subs[:3]
        for s in shown:
            left = core.days_left(s.get("expires_at"))
            if left is None:
                status = core.pending_text(s) or "بدون محدودیت زمانی"
            elif left <= 0:
                status = f"{F.b('اعتبارش تمام شده')} و باید تمدید شود"
            elif left == 1:
                status = f"فقط {F.b('امروز')} اعتبار دارد"
            elif left <= 3:
                status = f"فقط {F.b(f'{core.fa(left)} روز')} باقی مانده"
            else:
                status = f"{F.b(f'{core.fa(left)} روز')} باقی مانده"

            dot = "🔴" if (left is not None and left <= 0) else (
                  "🟡" if (left is not None and left <= 3) else "🟢")
            lines.append(f"{dot} {F.b(ctx.sub_label(s))}")
            lines.append(f"⏳ {status}")
            lines.append("")

        if len(subs) > len(shown):
            lines.append(F.i(f"و {core.fa(len(subs) - len(shown))} اشتراک دیگر "
                             "در «اشتراک‌های من»"))
    elif _license_store(ctx):
        lics = ctx.db.user_licenses(user["id"])
        if lics:
            lines.append("\n\n".join(LS.license_line(r) for r in lics[:3]))
        else:
            lines += [
                "هنوز مجوزی ندارید.",
                "با <b>خرید نکسورا Pro</b> شروع کنید. کلید همان لحظه‌ی پرداخت می‌رسد.",
            ]
    else:
        lines += [
            "هنوز اشتراکی ندارید.",
            "با <b>خرید اشتراک</b> شروع کنید. کمتر از یک دقیقه طول می‌کشد.",
        ]

    wallet_line = []
    if balance:
        wallet_line.append(f"👛 کیف پول <b>{core.toman(balance)}</b> تومان")
    if coins:
        tier = core.tier_for(coins, ctx.s)
        if tier:
            wallet_line.append(
                f"🪙 <b>{core.fa(coins)}</b> سکه <i>({core.fa(tier['percent'])}٪ تخفیف آماده)</i>")
        else:
            wallet_line.append(f"🪙 <b>{core.fa(coins)}</b> سکه")
    if wallet_line:
        lines += ["", "  ·  ".join(wallet_line)]

    return "\n".join(lines).rstrip()


# ═══════════════════════════════════════════════════════════
#  /start و ثبت‌نام + رفرال
# ═══════════════════════════════════════════════════════════

#: پیلودهایی که مینی‌اپ در `?start=` می‌فرستد.
#
#  اینها «کد معرف» نیستند و نباید به‌عنوان کد معرف خوانده شوند.
#  کد معرف شش حرفِ بزرگ از همان الفباست، پس `WALLET` می‌تواند
#  روزی کدِ واقعیِ کسی باشد — و آن‌وقت هر کسی که از مینی‌اپ روی
#  «شارژ» بزند، بی‌صدا زیرمجموعه‌ی آن نفر می‌شود.
DEEP_WORDS = ("wallet", "buy", "subs", "support")


def _deep_link(ctx, user, chat_id, arg):
    """
    مقصدِ مستقیم از مینی‌اپ. True یعنی خودش جواب داد.

    چرا لازم شد: مینی‌اپ دکمه‌هایی داشت که به `?start=wallet`
    می‌رفتند، ولی `/start` این مقدار را فقط به‌عنوان کد معرف
    می‌خواند و چون کد معتبری نبود بی‌صدا دورش می‌ریخت. نتیجه این
    بود که دکمه «کار می‌کرد» — ربات باز می‌شد — ولی کاربر در منوی
    اصلی رها می‌شد و باید خودش دنبال کیف پول می‌گشت.
    """
    arg = (arg or "").strip()
    if not arg:
        return False
    if arg == "wallet":
        show_wallet(ctx, user, chat_id, None)
        return True
    if arg == "buy":
        show_plans(ctx, user, chat_id)
        return True
    if arg == "subs":
        show_subs(ctx, user, chat_id, None)
        return True
    if arg.startswith("renew_"):
        try:
            sid = int(arg[6:])
        except ValueError:
            return False
        # مالکیت را خودِ show_renew می‌سنجد (WHERE user_id=?)، پس
        # شناسه‌ی دست‌کاری‌شده به «این اشتراک پیدا نشد» می‌رسد
        show_renew(ctx, user, chat_id, None, sid)
        return True
    return False


#: لینکِ وصل‌شدن چقدر معتبر است
OWNER_CLAIM_MINUTES = 30


def claim_owner(ctx, msg, code):
    """
    صاحبِ فروشگاه خودش را به رباتش وصل می‌کند.

    چرا لازم شد: رسیدها و هشدارها به گروهِ مدیریت می‌رفتند و
    نماینده نه گروه داشت نه راهی برای تعریفش. `owner_tg_id` هم که
    راهِ دوم است از هیچ فرمی پر نمی‌شد. پس مشتریِ نماینده رسید
    می‌فرستاد و **هیچ‌کس** خبردار نمی‌شد.

    چرا لینک و نه «آیدیِ عددی‌تان را وارد کنید»: کسی آیدیِ عددیِ
    خودش را نمی‌داند، و عددِ اشتباه یعنی رسیدها به غریبه برسد.
    این‌جا خودِ تلگرام می‌گوید چه کسی دکمه را زده.

    کد یک‌بارمصرف و کوتاه‌عمر است — هرکس این لینک را داشته باشد
    می‌تواند سفارش‌های این فروشگاه را تایید کند.
    """
    import hmac as _hmac

    frm = msg.get("from") or {}
    chat_id = (msg.get("chat") or {}).get("id") or frm.get("id")

    # متنِ خامِ تنظیمات را نگه می‌داریم: ادعای پایین روی همین متن شرط
    # می‌گذارد.
    raw = (DB.get_tenant(ctx.tid) or {}).get("settings") or "{}"
    try:
        st = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        st = {}
    if not isinstance(st, dict):
        st = {}
    want = st.get("owner_claim") if isinstance(st.get("owner_claim"), dict) else {}
    good = bool(code) and bool(want.get("code")) and \
        _hmac.compare_digest(str(code), str(want.get("code")))

    fresh = False
    try:
        fresh = datetime.fromisoformat(str(want.get("until"))[:19]) > datetime.now()
    except (TypeError, ValueError):
        fresh = False

    if not (good and fresh):
        return ctx.bot.send(
            chat_id,
            "⚠️ این لینک دیگر معتبر نیست.\n\n"
            "از پنلِ خودتان دوباره «وصلِ من به ربات» را بزنید. لینک "
            f"فقط {core.fa(OWNER_CLAIM_MINUTES)} دقیقه و یک‌بار کار می‌کند.")

    # سوزاندنِ کد و وصل‌کردن **یک** نوشتنِ شرطی است، نه دو تا.
    #
    # نسخه‌ی اول اول کد را می‌سوزاند و بعد جدا وصل می‌کرد. دو Start
    # هم‌زمان هر دو کدِ زنده را خوانده بودند و هر دو رد می‌شدند — آخری
    # برنده، بی‌آنکه کسی بفهمد. حالا شرط روی همان متنی است که خواندیم:
    # فقط یکی می‌تواند آن را عوض کند.
    st.pop("owner_claim", None)
    with DB.conn() as c:
        cur = c.execute(
            "UPDATE tenants SET settings=?, owner_tg_id=? "
            "WHERE id=? AND settings=?",
            (json.dumps(st, ensure_ascii=False), int(frm["id"]), ctx.tid, raw))
        won = cur.rowcount == 1
    if not won:
        return ctx.bot.send(
            chat_id, "⚠️ این لینک همین حالا استفاده شد. اگر شما نبودید، از "
                     "پنلِ خودتان جدا شوید و لینکِ تازه بسازید.")
    ctx.invalidate()
    ctx.db.log("owner_linked", None, {"tg": frm.get("id")})
    log.info("صاحبِ فروشگاه %s به ربات وصل شد: %s", ctx.tid, frm.get("id"))

    return ctx.bot.send(
        chat_id,
        "✅ <b>وصل شدید</b>\n\n"
        "از این به بعد رسیدِ هر خرید با دکمه‌های تایید و رد همین‌جا "
        "می‌آید، و اگر ساختِ کانفیگی گیر کند همین‌جا خبردار می‌شوید.")


def cmd_start(ctx, msg, args=None):
    """
    نمایش منوی اصلی.

    ساختِ کاربر و کارهای ثبت‌نام (پاداش خوش‌آمد، اطلاع به معرف، خبر
    به گروه) این‌جا نیست — در _get_or_create است، چون کاربر همان‌جا
    ساخته می‌شود. یک نسخه‌ی تکراری از آن منطق قبلاً این‌جا بود که
    هیچ‌وقت اجرا نمی‌شد و فقط توهم کارکردن می‌داد.
    """
    tg = msg["from"]
    user = _get_or_create(ctx, tg, args)

    ctx.db.clear_state(tg["id"])

    # اگر از مینی‌اپ آمده و مقصد مشخصی خواسته، همان‌جا ببرش
    try:
        if _deep_link(ctx, user, tg["id"], args):
            return
    except Exception:
        # مقصد خراب بود؛ منوی اصلی بهتر از هیچ است — ولی بی‌صدا نه
        log.warning("دیپ‌لینک %r کار نکرد", args, exc_info=True)

    ctx.bot.send(tg["id"], welcome_text(ctx, user), keyboard=main_menu(ctx, user))


# ═══════════════════════════════════════════════════════════
#  خرید
# ═══════════════════════════════════════════════════════════

_KIND_ICON = {"volume": "📦", "limited": "👥", "pro_license": "🔑"}


def _sellable(ctx, plan):
    """`core.sellable` for this shop: root tenant, and the issuer reachable."""
    return core.sellable(plan, not ctx.tenant.get("parent_id"),
                         (plan or {}).get("kind") == "pro_license" and LS.available())


def _license_store(ctx):
    """`core.license_only` for this shop. Never raises: the menu must render."""
    try:
        return core.license_only([p for p in ctx.db.plans() if _sellable(ctx, p)])
    except Exception as exc:
        log.debug("license_store: %s", exc)
        return False


def buy_word(ctx, store=None):
    """The buy button's words. A Pro store sells licenses, not subscriptions."""
    lic = _license_store(ctx) if store is None else store
    return "خرید نکسورا Pro" if lic else "خرید اشتراک"


def show_plans(ctx, user, chat_id, message_id=None, kind=None, tab=None):
    # فروشگاهِ بسته همین‌جا می‌گوید — نه بعد از انتخابِ پلن و روشِ پرداخت
    closed = store_gate(ctx)
    if closed:
        return _reply(ctx, chat_id, message_id, closed, back_kb())
    # عضویت اجباری کانال — قبل از دیدن پلن‌ها
    if require_membership(ctx, chat_id, message_id, user):
        return

    plans = [p for p in ctx.db.plans() if _sellable(ctx, p)]
    if not plans:
        text = ("فعلاً پلنی برای فروش فعال نیست.\n\n"
                "به‌زودی برمی‌گردند. اگر عجله دارید، به پشتیبانی پیام بدهید.")
        return _reply(ctx, chat_id, message_id, text, back_kb())

    # «رضایت» پیش از خرید — از نظرِ مشتری‌های خودِ همین فروشگاه
    # (`TenantDB.satisfaction`)؛ زیرِ ۱۰ نظر هیچ. فقط روی **اولین** صفحه‌ی
    # خرید، هر کدام که باشد (نوع، مدت یا پلن‌ها): تا ۱.۱۲۱ فقط روی فهرستِ
    # پلن‌ها بود، یعنی مشتریِ فروشگاهی با دو نوع آن را بعد از دو انتخاب می‌دید.
    # Showing it is Pro (`insights`); the answers it is made of are kept either way.
    sat = ""
    if ctx.s.get("show_satisfaction", True) and pro_allowed("insights"):
        line = core.satisfaction_line(ctx.db.satisfaction(core.SATISFACTION_MIN))
        if line:
            sat = f"\n\n{line}"

    # نوع ← تب ← پلن؛ هر مرحله‌ای که فقط یک گزینه دارد پریده می‌شود
    groups = core.plan_groups(plans)
    kinds = [k for k, _ in groups]
    if kind is None and len(kinds) > 1:
        rows = [[(f"{_KIND_ICON.get(k, '📦')} {dict(core.PLAN_KINDS)[k]}", f"pk:{k}")]
                for k in kinds]
        rows.append([("‹ بازگشت", "menu")])
        return _reply(ctx, chat_id, message_id,
                      "🛒 <b>خرید اشتراک</b>" + sat + "\n\nچه نوع اشتراکی می‌خواهید؟", kb(rows))
    if len(kinds) > 1:
        sat = ""
    kind = kind if kind in kinds else kinds[0]
    tabs = dict(groups)[kind]
    back_to = "buy" if len(kinds) > 1 else "menu"
    if tab is None and len(tabs) > 1:
        rows = [[(t or "بقیه", f"pt:{kind}:{i}")] for i, (t, _p) in enumerate(tabs)]
        rows.append([("‹ بازگشت", back_to)])
        return _reply(ctx, chat_id, message_id,
                      f"🛒 <b>{dict(core.PLAN_KINDS)[kind]}</b>{sat}\n\nمدت را انتخاب کنید:", kb(rows))
    if len(tabs) > 1:
        sat = ""
    idx = tab if isinstance(tab, int) and 0 <= tab < len(tabs) else 0
    plans = tabs[idx][1]
    rows = [[(core.plan_line(p), f"plan:{p['id']}")] for p in plans]
    rows.append([("‹ بازگشت", f"pk:{kind}" if len(tabs) > 1 else back_to)])

    prog = core.coin_progress(user["coins"], ctx.s.get("coins"))
    hint = ""
    if prog["current_percent"]:
        hint = (f"\n\n🪙 <b>{core.fa(prog['coins'])}</b> سکه دارید. "
                f"<b>{core.fa(prog['current_percent'])}٪ تخفیف</b> روی همین خرید اعمال می‌شود.")
    elif prog["next"]:
        hint = (f"\n\n🪙 با <b>{core.fa(prog['next']['need'])}</b> سکه‌ی دیگر، "
                f"{core.fa(prog['next']['percent'])}٪ تخفیف باز می‌شود.")

    _reply(ctx, chat_id, message_id,
           f"🛒 <b>{buy_word(ctx, core.license_only(plans))}</b>" + sat + "\n\n"
           "پلن مناسبتان را انتخاب کنید. جزئیات و مبلغ را "
           f"در صفحه‌ی بعد می‌بینید.{hint}", kb(rows))


def show_plan_detail(ctx, user, chat_id, message_id, plan_id):
    p = ctx.db.get_plan(plan_id)
    if not p:
        return _reply(ctx, chat_id, message_id,
                      "این پلن دیگر در دسترس نیست.\n\n"
                      "از لیست، یکی از پلن‌های فعال را انتخاب کنید.",
                      back_kb("buy"))

    cs = ctx.s.get("coins")

    # کدِ در دست، هر بار از نو سنجیده می‌شود.
    #
    # ظرفیت ممکن است بین دیدنِ این صفحه و زدنِ دکمه تمام شده باشد؛
    # قیمتی که نشان می‌دهیم باید همان باشد که گرفته می‌شود.
    dcode = ctx.db.held_discount(user["tg_id"])
    dpct, dwhy, dbad = 0, None, ""
    if dcode:
        dwhy, dpct, _ = find_discount(ctx, dcode, plan_id)
        if not dpct:
            # بی‌صدا دور انداختنش یعنی قیمت بی‌توضیح به حالتِ اول
            # برمی‌گردد و مشتری فکر می‌کند کد را اشتباه زده.
            dbad, dcode = dcode, ""
            ctx.db.set_held_discount(user["tg_id"], None)

    pr = core.price_order(p["price"], coins=user["coins"], coin_cfg=cs,
                          use_coins=True, discount_percent=dpct)
    has_coin_discount = pr["coin_discount"] > 0

    # قیمتِ «بدون سکه ولی با کد» — پایه‌ی دکمه‌ی خریدِ ساده و سنجشِ
    # کفایتِ کیف پول. بدونش مشتری‌ای که کد زده هنوز قیمتِ کامل را
    # روی دکمه می‌بیند و کیف پولش «کافی نیست» اعلام می‌شود.
    plain = core.price_order(p["price"], discount_percent=dpct)

    ips = p["ip_limit"]
    days = p["days"]
    # هر سطر یک ایموجیِ نشانه دارد تا چشم بتواند اسکن کند. بدون
    # آن‌ها، سطرها در موبایل یک بلوک متن یکنواخت می‌شوند.
    # نام و توضیحِ فروشگاه همان‌طور که نوشته شده، بالا؛ مشخصات یک خطِ کوچک
    # زیرش (مالک: «نوشته‌ها مطابق نوشته‌های خودم»)
    lic = p.get("kind") == "pro_license"
    if not _sellable(ctx, p):
        return _reply(ctx, chat_id, message_id,
                      "این پلن دیگر در دسترس نیست.\n\n"
                      "از لیست، یکی از پلن‌های فعال را انتخاب کنید.",
                      back_kb("buy"))
    lines = [F.title(p["name"], "🔑" if lic else "📦")]
    if p.get("description"):
        lines += ["", esc(p["description"])]
    lines += ["", F.i(core.plan_spec(p) if lic else " · ".join([
        f"{core.fmt_gb(p['gb'])}",
        (f"{core.fa(days)} روز" if days else "بی‌انقضا"),
        (f"{core.fa(ips)} کاربر" if ips else "کاربرِ نامحدود")]))]

    if dwhy:
        lines += ["", F.quote(f"🎟 کدِ <code>{esc(dbad)}</code> اعمال نشد: "
                              f"{esc(dwhy)}")]

    rows = []
    if dpct:
        lines += ["", f"🎟 کد <code>{esc(dcode)}</code>: "
                      f"{core.fa(dpct)}٪ تخفیف"]
    if has_coin_discount:
        # قیمت قبلی خط‌خورده کنار قیمت جدید: مشتری خودش مقدار
        # صرفه‌جویی را می‌بیند، که از نوشتن «۲۰٪ تخفیف» قوی‌تر است.
        lines += ["", "💰 " + F.price(core.toman(pr["final"]),
                                     old=core.toman(p["price"]))]
        lines.append(F.i(f"🪙 {core.fa(pr['coins_used'])} سکه‌ی شما خرج می‌شود "
                         f"({core.fa(pr['coin_percent'])}٪ تخفیف)"))
        rows.append([(f"🪙 خرید با تخفیف · {core.toman(pr['final'])} تومان",
                      f"chk:{plan_id}:1")])
    else:
        lines += ["", "💰 " + F.price(
            core.toman(plain["final"]),
            old=(core.toman(p["price"]) if dpct else None))]

    rows.append([(f"💳 خرید · {core.toman(plain['final'])} تومان",
                  f"chk:{plan_id}:0")])

    # دکمه‌ی کد: یا برای واردکردنش، یا برای برداشتنش. هر دو حالت
    # دیده می‌شود — کدی که روی قیمت اثر دارد و یادِ کسی نیست، همان
    # مسیرِ خرابِ بی‌صداست.
    rows.append([("✖️ برداشتن کد تخفیف", f"dscx:{plan_id}")] if dcode
                else [("🎟 کد تخفیف دارم", f"dsc:{plan_id}")])

    if user["balance"] >= plain["final"]:
        lines.append("")
        lines.append(F.quote(
            "👛 موجودی کیف پولتان برای این خرید کافی است. با پرداخت از "
            "کیف پول، " + ("مجوز" if lic else "اشتراک") + " "
            + F.b("بدون معطلی") + " تحویل می‌شود."))
        rows.append([("👛 پرداخت آنی از کیف پول", f"wpay:{plan_id}")])

    rows.append([("‹ بازگشت", "buy")])
    _reply(ctx, chat_id, message_id, "\n".join(lines), kb(rows))


def ask_discount(ctx, user, chat_id, message_id, plan_id):
    """پرسیدنِ کد. پاسخش در `handle_discount` می‌آید."""
    p = ctx.db.get_plan(plan_id)
    if not p:
        return _reply(ctx, chat_id, message_id,
                      "این پلن دیگر در دسترس نیست.\n\n"
                      "از لیست، یکی از پلن‌های فعال را انتخاب کنید.",
                      back_kb("buy"))
    ctx.db.set_state(user["tg_id"], "await_discount", {"plan": int(plan_id)})
    return _reply(ctx, chat_id, message_id,
                  "🎟 <b>کد تخفیف</b>\n\n"
                  "کدتان را همین‌جا بفرستید.\n\n"
                  "<blockquote>اگر کدی ندارید، برگردید و بدون آن "
                  "خرید کنید.</blockquote>",
                  kb([[("‹ بازگشت", f"plan:{plan_id}")]]))


def drop_discount(ctx, user, chat_id, message_id, plan_id):
    """برداشتنِ کد — و برگشت به همان صفحه با قیمتِ بی‌تخفیف."""
    ctx.db.set_held_discount(user["tg_id"], None)
    return show_plan_detail(ctx, user, chat_id, message_id, int(plan_id))


def handle_discount(ctx, msg, user, sdata):
    """
    کدی که مشتری فرستاده.

    سنجش همان‌جایی است که مینی‌اپ هم از آن رد می‌شود
    (`find_discount` → `core.validate_discount`) — نه نسخه‌ی دومی
    که روزی از اولی دور بیفتد.
    """
    chat_id = (msg.get("chat") or {}).get("id")
    code = (msg.get("text") or "").strip()
    pid = int(sdata.get("plan") or 0)

    if not code:
        return ctx.bot.send(chat_id, "کد را به‌صورت متن بفرستید.",
                            keyboard=kb([[("‹ بازگشت", f"plan:{pid}")]]))

    err, pct, _row = find_discount(ctx, code, pid or None)
    if not pct:
        # «ظرفیت تمام شده» و «منقضی شده» دو چیزِ متفاوتند و مشتری
        # باید بداند کدام — وگرنه کدِ درست را هم دوباره می‌زند.
        return ctx.bot.send(
            chat_id,
            f"❌ {esc(err or 'کد تخفیف معتبر نیست')}\n\n"
            "اگر کد دیگری دارید بفرستید، یا برگردید.",
            keyboard=kb([[("‹ بازگشت", f"plan:{pid}")]]))

    ctx.db.set_held_discount(user["tg_id"], code)
    ctx.db.clear_state(user["tg_id"])
    fresh = ctx.db.get_user(user["tg_id"]) or user
    ctx.bot.send(chat_id, f"✅ کد پذیرفته شد: <b>{core.fa(pct)}٪</b> تخفیف")
    return show_plan_detail(ctx, fresh, chat_id, None, pid)


def find_discount(ctx, code, plan_id=None):
    """
    کدِ تخفیفِ همین مستاجر. برمی‌گرداند (خطا, درصد, ردیف).

    **جست‌وجو همیشه با `tenant_id`.** بدونش مشتریِ یک نماینده کدِ
    نماینده‌ی دیگر را استفاده می‌کند و تخفیفش از جیبِ اشتباه می‌رود.

    خودِ سنجش در `core.validate_discount` است تا ربات و مینی‌اپ و
    پنل یک قاعده داشته باشند — نه سه نسخه که روزی از هم دور بیفتند.
    """
    if not str(code or "").strip():
        return "کد وارد نشده", 0, None
    row = ctx.db.get_discount(code)
    err, pct = core.validate_discount(dict(row) if row else None, plan_id)
    return err, pct, (dict(row) if row else None)


def store_gate(ctx):
    """
    آیا این فروشگاه اجازه‌ی فروش دارد؟ None یعنی بله؛ وگرنه متنی برای مشتری.

    نماینده برای فروش از ربات و مینی‌اپ اشتراکِ ماهانه می‌خرد
    (docs/specs/2026-09-26-reseller-store-subscription.md). قاعده در
    `core.addon_open` است — همان که بکند برای پرتال صدا می‌زند.

    هر پنج هسته‌ای که پول می‌گیرند یا کانفیگ می‌دهند این را صدا می‌زنند:
    `card_order`، `wallet_purchase`، `topup_order`، `give_trial`،
    `auto_renew_subscription`. `test_flow` با ast همین را می‌سنجد — و اینکه
    `receipt_submit` صدایش **نزند**: رسیدِ سفارشی که وقتِ باز بودن ساخته
    شده پولی است که در راه است.
    """
    t = ctx.tenant
    if not t.get("parent_id"):
        return None
    try:
        rs = json.loads((DB.root_tenant() or {}).get("settings") or "{}")
    except (json.JSONDecodeError, TypeError):
        log.warning("store gate: root settings unreadable — using defaults")
        rs = {}
    cfg = core.addon_config(rs if isinstance(rs, dict) else {}, "store")
    if core.addon_open(ctx.s, t.get("parent_id"), cfg["price"], "store"):
        return None
    return core.STORE_CLOSED


def card_order(ctx, user, plan_id, use_coins=False, renew_sub_id=None,
               discount_code=None, renew_license=None):
    """
    ساختِ سفارشِ کارتی: قیمت، رزروِ سکه، و انتخابِ کارت.

    برمی‌گرداند (ok, data). وقتی ok است:
        {"order":…, "plan":…, "card":…, "price":…, "ttl":…}
    وقتی نیست، `data` یکی از:
        no_plan | no_card | {"why": "coins", "left":…, "need":…}

    چرا جدا از `checkout`: مینی‌اپ هم سفارشِ کارتی می‌سازد. نسخه‌ی
    اولِ مینی‌اپ همین را دوباره نوشته بود و **دو چیز را جا انداخت**:
    تخفیفِ سکه (`core.price_order`) و مهلتِ قابل‌تنظیم
    (`order_ttl_minutes`). یعنی مشتری‌ای که سکه داشت، از مینی‌اپ
    قیمتِ کامل می‌داد. تستِ «مینی‌اپ خودش پول جابه‌جا نمی‌کند» همین
    را گرفت.
    """
    if store_gate(ctx):
        return False, {"why": "store_closed"}
    p = ctx.db.get_plan(plan_id)
    if not p or not _sellable(ctx, p):
        return False, "no_plan"

    cs = ctx.s.get("coins")
    # کدِ تخفیف پیش از سکه اعمال می‌شود — ترتیبش در
    # `core.price_order` است و عوض نمی‌شود، وگرنه قیمت‌های امروز و
    # دیروز قابلِ مقایسه نیستند.
    derr, dpct, _drow = find_discount(ctx, discount_code, plan_id) \
        if discount_code else (None, 0, None)
    if derr:
        return False, {"why": "discount", "detail": derr}
    pr = core.price_order(p["price"], coins=user["coins"], coin_cfg=cs,
                          use_coins=bool(use_coins),
                          discount_percent=dpct)

    card = core.pick_card(ctx.s.get("cards"))
    if not card:
        return False, "no_card"

    ttl = int(ctx.s.get("order_ttl_minutes") or 30)
    order = ctx.db.create_order(
        user["id"], plan_id, p["price"], pr["final"],
        coins_used=pr["coins_used"], ttl_minutes=ttl,
        # کد روی خودِ سفارش می‌نشیند، نه با ارجاع: ماه‌ها بعد باید
        # بشود گفت این مبلغ چرا این بوده، حتی اگر کد حذف شده باشد
        discount_pct=dpct, discount_code=(discount_code or None) if dpct else None,
        # اگر تمدید است، مقصد از همین‌جا ثبت می‌شود — وگرنه provision
        # نمی‌داند کدام اشتراک را باید تمدید کند و کانفیگ تازه می‌سازد
        kind=("renew" if renew_sub_id or renew_license else "new"),
        renew_sub_id=renew_sub_id, renew_license=renew_license,
    )

    # سکه همین حالا رزرو می‌شود، نه موقع تایید.
    #
    # اگر تا تایید صبر کنیم، مشتری می‌تواند چند سفارش با همان سکه‌ها
    # بسازد — چون هنوز کم نشده‌اند — و همه را تایید بگیرد.
    if pr["coins_used"]:
        took, left = ctx.db.spend_coins(
            user["id"], pr["coins_used"], "hold",
            f"رزرو برای سفارش #{order['id']}", order_id=order["id"])
        if not took:
            ctx.db.exec(
                "UPDATE orders SET status='expired' WHERE tenant_id=? AND id=?",
                (ctx.tid, order["id"]))
            return False, {"why": "coins", "left": left,
                           "need": pr["coins_used"]}

    ctx.db.exec(
        "UPDATE orders SET card_used=?, status='pending' WHERE tenant_id=? AND id=?",
        (card.get("number"), ctx.tid, order["id"]))

    return True, {"order": ctx.db.get_order(order["id"]), "plan": p,
                  "card": card, "price": pr, "ttl": ttl}


def checkout(ctx, user, chat_id, message_id, plan_id, use_coins,
             renew_sub_id=None, renew_license=None):
    """ساخت سفارش و نمایش اطلاعات کارت — پوسته‌ی `card_order`."""
    # پوسته فقط کد را می‌برد؛ قیمت همان‌جایی حساب می‌شود که برای
    # مینی‌اپ هم حساب می‌شود.
    held = ctx.db.held_discount(user["tg_id"])
    ok, r = card_order(ctx, user, plan_id, use_coins=use_coins,
                       renew_sub_id=renew_sub_id, discount_code=held or None,
                       renew_license=renew_license)
    if not ok:
        if isinstance(r, dict) and r.get("why") == "store_closed":
            return _reply(ctx, chat_id, message_id, core.STORE_CLOSED, back_kb())
        if r == "no_plan":
            return _reply(ctx, chat_id, message_id,
                          "این پلن دیگر در دسترس نیست.\n\n"
                          "از لیست، یکی از پلن‌های فعال را انتخاب کنید.",
                          back_kb("buy"))
        if r == "no_card":
            return _reply(ctx, chat_id, message_id,
                          "راه پرداخت هنوز فعال نشده است.\n\n"
                          "یک پیام به پشتیبانی بدهید تا دستی برایتان انجام دهیم.",
                          back_kb())
        return _reply(ctx, chat_id, message_id,
                      "سکه‌های شما برای این تخفیف کافی نیست.\n\n"
                      f"موجودی: <b>{core.fa(r['left'])}</b> سکه\n"
                      f"لازم: <b>{core.fa(r['need'])}</b> سکه\n\n"
                      "<blockquote>اگر همین الان سفارش دیگری ثبت "
                      "کرده‌اید، سکه‌هایتان آن‌جا رزرو شده‌اند."
                      "</blockquote>",
                      back_kb("buy"))

    order, p, card, pr, ttl = (r["order"], r["plan"], r["card"],
                               r["price"], r["ttl"])
    # کد داخلِ سفارش ثبت شد؛ ماندنش روی کاربر یعنی خریدِ بعدی هم
    # بی‌آنکه مشتری بخواهد تخفیف می‌گیرد.
    if held:
        ctx.db.set_held_discount(user["tg_id"], None)
    ctx.db.set_state(user["tg_id"], "await_receipt", {"order_id": order["id"]})

    holder = esc(card.get("holder") or "—")
    if card.get("bank"):
        holder += f" · {esc(card['bank'])}"

    lines = [
        "🧾 <b>سفارش شما</b>",
        "",
        f"📦 {esc(p['name'])}",
        f"<i>{esc(core.plan_spec(p))}</i>",
        "",
    ]
    if pr["code_discount"] or pr["coin_discount"]:
        lines.append(f"قیمت: <s>{core.toman(p['price'])}</s> تومان")
    if pr["code_discount"]:
        lines.append(f"🎟 کد تخفیف: {core.fa(pr['code_percent'])}٪ "
                     f"({core.toman(pr['code_discount'])} تومان)")
    if pr["coin_discount"]:
        lines.append(f"🪙 تخفیف سکه: {core.fa(pr['coin_percent'])}٪ "
                     f"({core.fa(pr['coins_used'])} سکه)")
    lines += [
        f"💰 قابل پرداخت: <b>{core.toman(pr['final'])} تومان</b>",
        "",
        "💳 <b>مبلغ را دقیقاً به همین کارت واریز کنید</b>",
        f"<code>{core.fmt_card(card['number'])}</code>",
        f"👤 {holder}",
        "",
        f"⏳ مهلت پرداخت: <b>{core.fa(ttl)} دقیقه</b>",
        "",
        "📸 بعد از واریز، <b>عکس رسید</b> یا <b>متن پیامک بانک</b> را "
        "همین‌جا بفرستید تا بررسی شود.",
        "",
        f"<i>کد پیگیری:</i> <code>#{order['id']}</code>",
    ]

    # شماره‌ی کارت بدون خط تیره کپی می‌شود — اپ بانک با خط تیره
    # معمولاً قبول نمی‌کند و مشتری باید دستی پاکشان کند
    digits = "".join(ch for ch in str(card["number"]) if ch.isdigit())
    _reply(ctx, chat_id, message_id, "\n".join(lines),
           kb([[("📋 کپی شماره کارت", digits, "copy")],
               [("📋 کپی مبلغ", str(pr["final"]), "copy")],
               [("✖️ لغو سفارش", f"cancel:{order['id']}")]]))


def wallet_purchase(ctx, user, plan_id, renew_sub_id=None,
                    discount_code=None, renew_license=None):
    """
    خریدِ اشتراک از کیف پول — بدونِ هیچ پوسته‌ی تلگرامی.

    برمی‌گرداند یک دیکشنری با کلیدِ `ok`. وقتی `ok` است:
        {"ok": True, "order": <ردیف سفارش>, "plan": <پلن>,
         "user": <کاربرِ تازه>, "sub": <نتیجه‌ی provision>,
         "spent": <مبلغ>, "left": <موجودی بعد>}
    وقتی نیست:
        {"ok": False, "why": "<کلید>", "plan":…, "short":…, "left":…,
         "detail": "<متن خطای ساخت>"}

    چرا جدا از `wallet_pay`:
        مینی‌اپ هم باید دقیقاً همین را انجام بدهد. اگر آن‌جا دوباره
        نوشته شود، می‌شود مسیر چهارمِ پول در این مخزن — و سه مسیر
        قبلی (کارت، کیف پول، تمدید خودکار) هر کدام یک‌بار یک قاعده
        را فراموش کردند و سه بار جدا پیدا شدند: یکی `approved` را
        پیش از ساخت می‌نوشت، یکی بعدش هیچ‌وقت نمی‌نوشت، و یکی پاداشِ
        معرف را نمی‌داد.

        پس این‌جا یک نسخه هست و هر دو مسیر صدایش می‌زنند. تستِ
        `test_flow` با ast می‌سنجد که همین تابع هر دو پرداخت را
        بدهد.
    """
    if store_gate(ctx):
        return {"ok": False, "why": "store_closed"}
    p = ctx.db.get_plan(plan_id)
    if not p or not _sellable(ctx, p):
        return {"ok": False, "why": "no_plan"}

    # کدِ تخفیف — همان اعتبارسنجِ مسیرِ کارت، تا دو مسیر یک قاعده
    # داشته باشند. بدونِ این، کدی که در ربات کار می‌کرد از کیف پول
    # رد می‌شد و مشتری قیمتِ کامل می‌داد.
    dpct = 0
    if discount_code:
        derr, dpct, _drow = find_discount(ctx, discount_code, plan_id)
        if derr:
            return {"ok": False, "why": "discount", "detail": derr, "plan": p}
    pr = core.price_order(p["price"], discount_percent=dpct)
    price = pr["final"]

    fresh = ctx.db.get_user(user["tg_id"])
    if fresh["balance"] < price:
        return {"ok": False, "why": "low_balance", "plan": p,
                "short": price - fresh["balance"],
                "left": fresh["balance"]}

    # کسر اول، سفارش بعد. اگر ترتیب برعکس باشد و کسر نگیرد، یک
    # سفارش بی‌پرداخت می‌ماند که هیچ‌کس بعداً نمی‌فهمد چه بوده.
    # `base_amount` قیمتِ پلن می‌ماند و `amount` قیمتِ پرداختی —
    # تفاوتشان همان تخفیفی است که داده شده، و گزارش‌ها از رویش
    # حساب می‌کنند.
    order = ctx.db.create_order(fresh["id"], plan_id, p["price"], price,
                                paid_from="wallet",
                                kind=("renew" if renew_sub_id or renew_license else "new"),
                                renew_sub_id=renew_sub_id, renew_license=renew_license,
                                discount_pct=dpct,
                                discount_code=(discount_code or None) if dpct else None)
    paid, left = ctx.db.spend_balance(fresh["id"], price, "spend",
                                      f"خرید {p['name']}", order["id"])
    if not paid:
        # بین خواندن موجودی و این لحظه، پول جای دیگری خرج شده —
        # مثلاً تمدید خودکار همین کاربر که در نخ دیگری می‌دود.
        ctx.db.close_order(order["id"], "rejected", "موجودی کیف پول کافی نبود")
        return {"ok": False, "why": "race", "plan": p, "left": left}

    ok, result = provision(ctx, order["id"])
    if not ok:
        # بستن و برگرداندن پول، با هم و یک بار.
        ctx.db.close_order(order["id"], "rejected", "خطا در ساخت کانفیگ")
        return {"ok": False, "why": "provision", "plan": p,
                "detail": str(result)}

    # حالا که کانفیگ ساخته شد، این یک فروشِ تمام‌شده است.
    #
    # بدون این خط سفارش pending می‌ماند و جاروکشِ سفارش‌های منقضی
    # نیم‌ساعت بعد «منقضی»‌اش می‌کرد — فروشی که انجام شده و در هیچ
    # آماری نیست.
    ctx.db.close_order(order["id"], "approved")

    # A wallet sale is a sale: the partner's commission and the referrer's
    # coins, like every other path. The referral reward once came only from
    # the card path, although the bot had promised it for any purchase.
    after_paid_order(ctx, fresh, order["id"])

    # گروه مدیریت باید این فروش را ببیند. هر رویدادِ پولیِ دیگر خودش
    # را اعلام می‌کند؛ فقط خریدِ کیف‌پولی بی‌صدا بود.
    ctx.notify_group(
        f"👛 <b>خرید با کیف پول</b>\n"
        f"کاربر: {esc(fresh.get('first_name') or fresh['tg_id'])} "
        f"(<code>{fresh['tg_id']}</code>)\n"
        f"پلن: {esc(p['name'])}"
        + ("\nنوع: تمدید" if renew_sub_id or renew_license else "")
        + f"\nمبلغ: {core.toman(price)} تومان"
        + (f" (کد تخفیف {core.fa(dpct)}٪ از {core.toman(p['price'])})" if dpct else ""))

    # `price`, not the plan's list price: with a discount code the buyer, the
    # mini app and the group were all told the undiscounted amount, while the
    # wallet had been charged the discounted one.
    return {"ok": True, "order": order, "plan": p, "user": fresh,
            "sub": result, "spent": price, "left": left}


def wallet_pay(ctx, user, chat_id, message_id, plan_id,
               renew_sub_id=None, renew_license=None):
    """
    پرداخت مستقیم از کیف پول — پوسته‌ی تلگرامیِ `wallet_purchase`.

    این‌جا فقط پیام ساخته می‌شود؛ هیچ پولی این‌جا جابه‌جا نمی‌شود.
    """
    held = ctx.db.held_discount(user["tg_id"])
    r = wallet_purchase(ctx, user, plan_id, renew_sub_id=renew_sub_id,
                        discount_code=held or None, renew_license=renew_license)

    if r["ok"]:
        # خرج شد — دیگر روی کاربر نمی‌ماند.
        if held:
            ctx.db.set_held_discount(user["tg_id"], None)
        _reply(ctx, chat_id, message_id,
               f"✅ <b>{core.toman(r['spent'])}</b> تومان از کیف پولتان کم شد.\n\n"
               + ("مجوز" if (r.get("sub") or {}).get("license") else "اشتراک")
               + " آماده است. همین پایین برایتان فرستادیم.", None)
        return deliver(ctx, r["user"], r["sub"])

    why = r["why"]
    if why == "store_closed":
        return _reply(ctx, chat_id, message_id, core.STORE_CLOSED, back_kb())
    if why == "no_plan":
        return _reply(ctx, chat_id, message_id,
                      "این پلن دیگر در دسترس نیست.", back_kb("buy"))

    if why == "discount":
        # کد بین دیدنِ صفحه و زدنِ دکمه از کار افتاد. برش می‌داریم و
        # می‌گوییم چه شد — نه اینکه خرید بی‌توضیح نشود.
        ctx.db.set_held_discount(user["tg_id"], None)
        return _reply(ctx, chat_id, message_id,
                      f"🎟 {esc(r.get('detail') or 'کد تخفیف معتبر نیست')}\n\n"
                      "کد برداشته شد. دوباره امتحان کنید.",
                      kb([[("‹ بازگشت", f"plan:{plan_id}")]]))

    if why == "low_balance":
        return _reply(ctx, chat_id, message_id,
                      "موجودی کیف پولتان برای این پلن کافی نیست.\n\n"
                      f"موجودی: <b>{core.toman(r['left'])}</b> تومان\n"
                      f"کسری: <b>{core.toman(r['short'])}</b> تومان\n\n"
                      "می‌توانید کیف پول را شارژ کنید یا کارت‌به‌کارت بپردازید.",
                      back_kb("buy"))

    if why == "race":
        return _reply(ctx, chat_id, message_id,
                      "موجودی کیف پولتان کافی نیست.\n\n"
                      f"موجودی: <b>{core.toman(r['left'])}</b> تومان\n"
                      f"لازم: <b>{core.toman(r['plan']['price'])}</b> تومان\n\n"
                      "<blockquote>اگر همین الان خرید دیگری انجام داده‌اید یا "
                      "تمدید خودکارتان اجرا شده، ممکن است موجودی تغییر کرده "
                      "باشد.</blockquote>",
                      back_kb("buy"))

    return _reply(ctx, chat_id, message_id,
                  "ساخت اشتراک به مشکل خورد و <b>مبلغ کامل به کیف پولتان برگشت</b>.\n\n"
                  f"<i>{esc(r.get('detail') or '')}</i>\n\n"
                  "<blockquote>چند دقیقه دیگر دوباره امتحان کنید. اگر باز هم "
                  "نشد، پشتیبانی همین را می‌بیند و پیگیری می‌کند."
                  "</blockquote>",
                  back_kb())


def receipt_submit(ctx, user, order_id, rtype, rfile=None, rtext=None,
                   photo_bytes=None):
    """
    ثبتِ رسیدِ یک سفارشِ کارتی، و خبردادن به گروه مدیریت.

    برمی‌گرداند (ok, why). `why` یکی از:
        closed   سفارش دیگر باز نیست
        expired  مهلتش تمام شده
        race     درست همین لحظه منقضی شد

    چرا جدا از `handle_receipt`: مینی‌اپ هم باید دقیقاً همین را
    انجام بدهد — همان قاعده‌ی مهلت، همان ادعای اتمی، همان اعلان با
    دکمه‌های تایید و رد. اگر آن‌جا دوباره نوشته شود، دو مسیرِ رسید
    می‌شود و روزی یکی‌شان اعلان را جا می‌اندازد؛ آن‌وقت مشتری پول
    داده و هیچ‌کس خبر ندارد.

    `photo_bytes` برای جایی است که عکس از تلگرام نیامده (مینی‌اپ):
    همان‌جا به گروه آپلود می‌شود و `file_id`ش برمی‌گردد — پس پنل و
    پنل نماینده بدون هیچ تغییری همان رسید را نشان می‌دهند.
    """
    order = ctx.db.get_order(order_id)
    if not order or order["status"] != "pending":
        return False, "closed"

    if order.get("expires_at"):
        try:
            if datetime.fromisoformat(order["expires_at"]) < datetime.now():
                ctx.db.exec(
                    "UPDATE orders SET status='expired' WHERE tenant_id=? AND id=?",
                    (ctx.tid, order_id))
                _release_coins(ctx, order_id)
                return False, "expired"
        except ValueError:
            # مهلتِ ناخوانا یعنی قاعده‌ی مهلت اجرا نشد؛ رسید پذیرفته می‌شود،
            # ولی بی‌صدا نه
            log.warning("order %s has unreadable expires_at %r — deadline not enforced",
                        order_id, order.get("expires_at"))

    t = DB.get_tenant(ctx.tid)
    # گروه، یا پیویِ صاحبِ ربات — همان قاعده‌ی `notify_group`.
    gid, receipts_topic = ctx.staff_chat("receipts")

    # عکسی که از تلگرام نیامده باید اول آپلود شود تا `file_id` بگیرد.
    #
    # همین آپلود، خودش اعلانِ گروه هم هست — دو کار با یک درخواست. و
    # مهم‌تر: بعدش رسیدِ مینی‌اپ دقیقاً مثل رسیدِ ربات ذخیره می‌شود،
    # پس هیچ‌جای پایین‌دست لازم نیست بداند از کجا آمده.
    uploaded = None
    if photo_bytes and gid:
        try:
            r = ctx.bot.send_photo_bytes(
                gid, photo_bytes, filename=f"receipt-{order_id}.jpg",
                caption=_receipt_caption(ctx, user, order, rtext),
                topic_id=receipts_topic)
            ph = ((r or {}).get("result") or {}).get("photo") or []
            if ph:
                uploaded = ph[-1].get("file_id")
        except (TelegramError, KeyError, TypeError) as e:
            log.warning("آپلود رسید مینی‌اپ ناموفق: %s", e)

    # `rfile` اگر از قبل آمده، منبعِ اصلی است و جایش را نمی‌دهد.
    #
    # مینی‌اپ عکس را روی دیسکِ خودمان می‌گذارد و ارجاعِ `local:` را
    # می‌فرستد. اگر این‌جا با `file_id` تلگرام جایگزین شود، همان
    # وابستگی برمی‌گردد که باعث گم‌شدنِ رسید شده بود. `uploaded`
    # فقط برای پیامِ گروه است.
    if uploaded and not rfile:
        rfile = uploaded

    # شرطی، نه بی‌قید: بین بررسی مهلت بالا و همین لحظه، جاروکشِ
    # زمان‌بند می‌تواند سفارش را منقضی کرده و سکه‌ها را پس داده باشد.
    if not ctx.db.attach_receipt(order_id, rtype, rfile, rtext):
        return False, "race"

    # اگر عکس همین حالا آپلود شد، گروه خبردار شده — فقط دکمه‌ها را
    # جدا می‌فرستیم. وگرنه اعلانِ کامل.
    buttons = kb([[("✅ تایید", f"ap:{order_id}"), ("❌ رد", f"rj:{order_id}")]])
    info = _receipt_caption(ctx, user, order, rtext)

    if uploaded:
        ctx.notify_group(f"سفارش #{order_id}: تصمیم شما؟",
                         keyboard=buttons, topic="receipts")
    elif gid and rtype == "photo" and rfile and not str(rfile).startswith("local:"):
        try:
            ctx.bot.send_photo(gid, rfile, caption=info, keyboard=buttons,
                               topic_id=receipts_topic)
        except TelegramError as e:
            log.warning("ارسال عکس رسید ناموفق: %s", e)
            ctx.notify_group(info, keyboard=buttons, topic="receipts")
    else:
        ctx.notify_group(info, keyboard=buttons, topic="receipts")

    # The bank's SMS may already be here (docs/specs/2026-10-07-sms-auto-approve.md).
    # Off the customer's path: building the config takes seconds, and the
    # "receipt received" reply should not wait for it.
    sp = pro("smspay")
    if sp and sp.enabled(ctx):
        _spawn(sp.match, ctx, order_id)
    return True, None


def _spawn(fn, *args):
    """A daemon thread that logs instead of dying silently. Tests run it inline."""
    import threading

    def run():
        try:
            fn(*args)
        except Exception:
            log.exception("background %s failed", getattr(fn, "__name__", fn))
    threading.Thread(target=run, daemon=True).start()


def _receipt_caption(ctx, user, order, rtext):
    """متنِ اعلانِ رسید — یک شکل، از هر مسیری که آمده باشد."""
    plan = ctx.db.get_plan(order["plan_id"])
    who = esc(user.get("first_name") or "بدون نام")
    if user.get("username"):
        who += f" · @{esc(user['username'])}"
    info = (
        f"🧾 <b>رسید جدید: سفارش #{order['id']}</b>\n\n"
        f"{who}\n"
        f"<code>{user['tg_id']}</code>\n\n"
        f"{esc(plan['name']) if plan else '—'}\n"
        f"<b>{core.toman(order['amount'])}</b> تومان"
    )
    if order["coins_used"]:
        info += (f"\nبا {core.fa(order['coins_used'])} سکه · "
                 f"{core.fa(order['discount_pct'])}٪ تخفیف")
    if rtext:
        info += f"\n\n<i>{esc(rtext[:400])}</i>"
    return info


def handle_receipt(ctx, msg, user, state_data):
    """
    رسیدی که مشتری در گفتگوی ربات فرستاده.

    پوسته‌ی تلگرامیِ `receipt_submit` — این‌جا فقط پیام ساخته می‌شود.
    """
    order_id = state_data.get("order_id")

    rtype = rfile = rtext = None
    if msg.get("photo"):
        rtype = "photo"
        rfile = msg["photo"][-1]["file_id"]
        rtext = msg.get("caption")
    elif msg.get("text"):
        rtype = "text"
        rtext = msg["text"]
    else:
        return ctx.bot.send(user["tg_id"],
                            "برای ثبت پرداخت، <b>عکس رسید</b> یا "
                            "<b>متن پیامک بانک</b> را بفرستید.")

    ok, why = receipt_submit(ctx, user, order_id, rtype, rfile, rtext)
    ctx.db.clear_state(user["tg_id"])

    if ok:
        return ctx.bot.send(user["tg_id"], _waiting_text(ctx, order_id),
                            keyboard=_waiting_kb(ctx, order_id))

    if why == "closed":
        return ctx.bot.send(user["tg_id"],
                            "این سفارش دیگر باز نیست. شاید قبلاً بررسی "
                            "یا لغو شده باشد.\n\n"
                            "وضعیتش را از «سفارش‌های من» ببینید.",
                            keyboard=main_menu(ctx, user))

    if why == "expired":
        return ctx.bot.send(user["tg_id"],
                            "⌛️ مهلت این سفارش تمام شد.\n\n"
                            "اگر واریز کرده‌اید، "
                            "به پشتیبانی پیام بدهید تا دستی ثبت شود.\n"
                            f"وگرنه از «{buy_word(ctx)}» یک سفارش تازه بسازید.",
                            keyboard=main_menu(ctx, user))

    return ctx.bot.send(
        user["tg_id"],
        "⌛️ درست همین لحظه مهلت این سفارش تمام شد.\n\n"
        "اگر واریز کرده‌اید، رسیدتان را برای پشتیبانی "
        "بفرستید تا دستی ثبت شود.\n"
        f"وگرنه از «{buy_word(ctx)}» یک سفارش تازه بسازید.",
        keyboard=main_menu(ctx, user))


def _waiting_text(ctx, order_id):
    """
    پیام انتظار تایید.

    به‌جای برگرداندن کاربر به منوی اصلی (که گیج‌کننده است و انگار
    چیزی نشده)، وضعیت را روشن می‌گوییم و راه ارتباط می‌دهیم.
    """
    tpl = ctx.s.get("waiting_text")
    support = ctx.s.get("support_username") or ""
    if tpl:
        return (tpl.replace("{order_id}", str(order_id))
                   .replace("{support}", support))

    txt = (
        "✅ <b>رسیدتان رسید</b>\n\n"
        "⏳ الان در صف بررسی است، معمولاً کمتر از <b>۱۵ دقیقه</b>.\n"
        "📩 به‌محض تأیید، اشتراک همین‌جا برایتان می‌آید.\n\n"
        "<blockquote>لازم نیست منتظر بمانید؛ می‌توانید تلگرام را ببندید.</blockquote>\n\n"
        f"<i>کد پیگیری:</i> <code>#{order_id}</code>"
    )
    if support:
        txt += ("\n\n<i>اگر بیشتر از یک ساعت طول کشید، همین کد را "
                "برای پشتیبانی بفرستید.</i>")
    return txt


def _waiting_kb(ctx, order_id):
    support = ctx.s.get("support_username") or ""
    rows = [[("📊 وضعیت سفارش", f"ost:{order_id}")]]
    if support:
        rows.append([("🎧 پشتیبانی", f"https://t.me/{support.lstrip('@')}", "url")])
    rows.append([("‹ منوی اصلی", "menu")])
    return kb(rows)


def show_order_status(ctx, user, chat_id, message_id, order_id):
    """وضعیت لحظه‌ای یک سفارش برای مشتری."""
    o = ctx.db.get_order(order_id)
    if not o or o["user_id"] != user["id"]:
        return _reply(ctx, chat_id, message_id, "سفارش پیدا نشد.", back_kb())

    labels = {
        "awaiting": ("⏳", "در انتظار بررسی"),
        "review": ("🔍", "در حال بررسی"),
        "panel_approve": ("⚙️", "تایید شد، در حال ساخت کانفیگ"),
        "approved": ("✅", "تایید شد"),
        "rejected": ("❌", "تایید نشد"),
        "expired": ("⌛️", "منقضی شد"),
    }
    icon, label = labels.get(o["status"], ("•", o["status"]))
    p = ctx.db.get_plan(o["plan_id"]) if o.get("plan_id") else None

    txt = (
        f"{icon} <b>وضعیت سفارش: {label}</b>\n\n"
        f"{esc(p['name']) if p else '—'}\n"
        f"<b>{core.toman(o['amount'])}</b> تومان\n"
        f"ثبت شده در {core.fa_datetime(o.get('created_at'))}\n\n"
        f"<i>کد پیگیری:</i> <code>#{order_id}</code>"
    )
    if o["status"] == "rejected" and o.get("admin_note"):
        txt += f"\n\n<b>دلیل رد شدن:</b>\n{esc(o['admin_note'])}"

    return _reply(ctx, chat_id, message_id, txt, _waiting_kb(ctx, order_id))




def _free_email(ctx, user, prefix, limit=30):
    """
    شناسه‌ی کانفیگ تازه — `پیشوند_شماره`، تضمین‌شده آزاد.

    `user` دیگر در نام نیست (تا ۱.۱۱۷ آیدیِ عددیِ تلگرام بود)؛ پارامتر
    می‌ماند تا صداکننده‌ها عوض نشوند.
    """
    # شماره از شمارنده‌ی اتمیِ فروشگاه (`shop_200`)، نه از آیدیِ تلگرام.
    # پنل هنوز پرسیده می‌شود: نامی که دستی در x-ui ساخته شده، یا دیتابیسی
    # که از بک‌آپِ قدیمی برگشته، نباید روی کانفیگِ زنده‌ی کسِ دیگری بنشیند.
    seq = ctx.db.next_name_seq(prefix)
    for _ in range(limit):
        email = core.make_email(prefix, seq)
        try:
            taken = ctx.xui.find_client(None, email=email)
        except Exception:
            # پنل جواب نداد — شماره‌ی شمارنده بهترین چیزی است که داریم.
            # متوقف‌کردن خرید به‌خاطر یک بررسی، بدتر است.
            return email
        if not taken:
            return email
        log.warning("شناسه‌ی %s در پنل گرفته است — شماره‌ی بعدی", email)
        seq = ctx.db.next_name_seq(prefix)

    return core.make_email(prefix, seq)


#: پاسخ approve_order وقتی نخِ دیگری همین سفارش را برداشته.
#: صداکننده باید این را از «ساخت کانفیگ شکست خورد» تشخیص بدهد،
#: چون پاسخِ درست به این یکی صبر است نه تلاش دوباره.
ORDER_BUSY = "این سفارش همین حالا در حال پردازش است"


def loyalty_on():
    """The loyalty module when it may run now (Pro present and licensed), else
    None. Earning coins, the invite screen and the trial follow-up need it;
    spending coins a customer already has and redeeming a code they hold do
    not: those were promised to a customer, and customers are never cut off."""
    try:
        mod = pro("loyalty")
    except Exception:
        log.exception("Pro loyalty module failed to load; loyalty stays off")
        return None
    return mod if mod is not None and pro_allowed("loyalty") else None


#: The payouts a paid order may owe: (Pro area, license feature, the user field
#: that says there is someone to pay). Each lives in its own Pro module.
PAYOUTS = (("affiliates", "affiliates", "affiliate_id"),
           ("loyalty", "loyalty", "referred_by"))


def after_paid_order(ctx, user, order_id):
    """
    The payouts of a paid, delivered order: the partner's commission and the
    referrer's coins.

    The only payout call in the three purchase cores (`wallet_purchase`,
    `approve_order`, `auto_renew_subscription`), right after
    `close_order(..., "approved")`. `tests/bot/test_flow.py` checks that with
    ast, because each core once paid one of the two and forgot the other.

    - Community edition (no Pro file): nothing to pay.
    - Pro locked: skipped out loud, one `payout_skipped` event per order and
      feature when there is someone to pay, and never paid later.
    - A payout that fails is logged as `payout_failed` and never breaks the
      delivery: the customer's config is already made and the order closed.
    """
    for area, feature, field in PAYOUTS:
        try:
            mod = pro(area)
        except Exception:
            log.exception("Pro %s module failed to load; payout not made", area)
            ctx.db.log("payout_failed", user.get("id"),
                       {"order": order_id, "feature": feature, "why": "load"})
            continue
        if mod is None:
            continue
        if not pro_allowed(feature):
            if user.get(field):
                ctx.db.log("payout_skipped", user.get("id"),
                           {"order": order_id, "feature": feature})
            continue
        try:
            mod.after_paid_order(ctx, user, order_id)
        except Exception as e:
            log.exception("%s payout for order %s failed", feature, order_id)
            ctx.db.log("payout_failed", user.get("id"),
                       {"order": order_id, "feature": feature,
                        "why": f"{type(e).__name__}: {e}"[:200]})


def approve_order(ctx, order_id, admin_tg_id):
    order = ctx.db.get_order(order_id)
    if not order:
        return False, "سفارش پیدا نشد"
    # سفارشی که تایید شده *و* کانفیگش ساخته شده، دوباره تایید نمی‌شود.
    #
    # ولی سفارشی که در نسخه‌های قبل approved شد و ساخت کانفیگش شکست
    # خورد، بدون sub_id مانده است. اگر آن را هم رد کنیم، برای همیشه
    # گیر می‌کند و مشتری پول داده و چیزی نگرفته. این‌ها باید بتوانند
    # دوباره تلاش کنند.
    if order["status"] == "approved" and core.order_delivered(order):
        return False, "این سفارش قبلاً تایید شده و تحویل شده"

    # ادعای اتمی، *قبل* از هر کاری.
    #
    # فقط یک نخ می‌تواند برنده شود؛ بقیه همین‌جا برمی‌گردند. بدون این،
    # دو تایید هم‌زمان هر دو نگهبان بالا را رد می‌کردند و مشتری با یک
    # پرداخت دو کانفیگ می‌گرفت.
    if not ctx.db.claim_order(order_id, admin_tg_id):
        return False, ORDER_BUSY

    def _unclaim(note):
        """ادعا را پس می‌دهیم تا تلاش دوباره ممکن بماند."""
        ctx.db.exec(
            "UPDATE orders SET status='awaiting', admin_note=? "
            "WHERE tenant_id=? AND id=? AND " + DB.UNDELIVERED,
            (note[:180], ctx.tid, order_id))

    # شارژ کیف پول کانفیگ ندارد — فقط موجودی اضافه می‌شود
    if order.get("kind") == "topup":
        u = ctx.db.get_user_by_id(order["user_id"])
        ctx.db.add_balance(u["id"], order["amount"], "topup",
                           "شارژ کیف پول", order_id)
        fresh = ctx.db.get_user_by_id(u["id"])
        ctx.bot.send(
            u["tg_id"],
            "✅ <b>کیف پولتان شارژ شد</b>\n\n"
            f"واریزی: {core.toman(order['amount'])} تومان\n"
            f"موجودی جدید: <b>{core.toman(fresh['balance'])}</b> تومان\n\n"
            "حالا می‌توانید بدون انتظارِ تأیید رسید خرید کنید.")
        ctx.notify_group(
            f"💳 <b>شارژ کیف پول</b>\n"
            f"کاربر: {esc(u.get('first_name') or u['tg_id'])}\n"
            f"مبلغ: {core.toman(order['amount'])} تومان")
        return True, "شارژ انجام شد"

    # ساخت کانفیگ *قبل* از تایید نهایی.
    #
    # قبلاً سفارش اول approved می‌شد و بعد کانفیگ ساخته می‌شد. اگر
    # ساخت شکست می‌خورد، سفارش برای همیشه در حالت «تایید شده ولی
    # بدون کانفیگ» گیر می‌کرد و تلاش دوباره هم با پیام «قبلاً تایید
    # شده» رد می‌شد. حالا تا کانفیگ ساخته نشود، سفارش در صف بررسی
    # می‌ماند و ادمین می‌تواند دوباره تایید بزند.
    # ساخت کانفیگ چند ثانیه طول می‌کشد؛ تا آن موقع کاربر «در حال
    # تایپ» می‌بیند و فکر نمی‌کند ربات قطع شده
    try:
        buyer = ctx.db.get_user_by_id(order["user_id"])
        if buyer:
            ctx.bot.action(buyer["tg_id"], "typing")
    except Exception as _exc:
        log.warning("buyer lookup on approve: %s", _exc)

    # ساخت کانفیگ چند ثانیه طول می‌کشد؛ بدون این، مشتری سکوت می‌بیند
    try:
        u0 = ctx.db.get_user_by_id(order["user_id"])
        if u0:
            ctx.bot.action(u0["tg_id"], "typing")
    except Exception as _exc:
        log.warning("buyer lookup on approve: %s", _exc)

    ok, result = provision(ctx, order_id)
    if not ok:
        # ادعا را پس می‌دهیم، وگرنه سفارشی که ساختش شکست خورده
        # approved می‌ماند و هیچ‌کس نمی‌تواند دوباره تلاش کند.
        _unclaim(f"خطای ساخت: {result}")
        return False, result

    user = ctx.db.get_user_by_id(order["user_id"])

    # Payouts (partner commission, referrer coins) only after the config was
    # made: until it is delivered, no sale has happened.
    after_paid_order(ctx, user, order_id)

    # سکه هنگام ثبت سفارش رزرو شده — این‌جا فقط نوعش را ثبت می‌کنیم
    # که در تاریخچه «خرج‌شده» دیده شود، نه «رزرو».
    #
    # کم‌کردن دوباره‌ی آن، همان باگی بود که با دو سفارش هم‌زمان
    # موجودی را منفی می‌کرد.
    if order["coins_used"]:
        ctx.db.exec(
            "UPDATE coin_tx SET kind='spend', note=? "
            "WHERE tenant_id=? AND order_id=? AND kind='hold'",
            (f"تخفیف سفارش #{order_id}", ctx.tid, order_id))

    # تحویل نباید بتواند جریان تایید را بشکند.
    #
    # قبلاً اگر ارسال پیام به مشتری خطا می‌داد، همان استثنا تا بالا
    # می‌رفت: پیام تایید به ادمین هم نمی‌رسید و دکمه‌های رسید سر جایشان
    # می‌ماندند، انگار تایید اصلاً ثبت نشده. کانفیگ ساخته شده بود ولی
    # هیچ‌کس خبر نداشت.
    # خبرِ تایید در صندوقِ مینی‌اپ — پیش از تحویل، چون تحویل ممکن
    # است شکست بخورد و آن‌وقت مشتری حتی نمی‌فهمد تایید شده.
    try:
        ctx.db.chat_add(order["user_id"], "system",
                        f"رسید سفارش #{order_id} تایید شد و "
                        + ("مجوزتان در ربات فرستاده شد." if result.get("license")
                           else "اشتراکتان ساخته شد."),
                        order_id=order_id)
    except Exception:
        log.warning("ثبت خبرِ تایید در صندوق ناموفق", exc_info=True)

    try:
        deliver(ctx, user, result)
    except Exception as e:
        log.exception("ارسال کانفیگ به مشتری ناموفق")
        # فقط ثبت: پیامِ گروه همین پایین دست‌ساز است و راهنمای
        # عمل دارد، پس `record` نباید پیامِ دومی روی آن بفرستد.
        try:
            ctx.db.log("deliver_failed", order["user_id"],
                       {"order": order_id, "error": str(e)})
        except Exception:
            log.debug("ثبت رویداد ناموفق", exc_info=True)
        lic = result.get("license")
        ctx.notify_group(
            (f"⚠️ <b>مجوز صادر شد ولی به مشتری نرسید</b>\n\n" if lic else
             f"⚠️ <b>کانفیگ ساخته شد ولی به مشتری نرسید</b>\n\n")
            + f"سفارش <code>#{order_id}</code> · "
            f"{esc(user.get('first_name') or user['tg_id'])}\n"
            f"<code>{esc(str(e)[:200])}</code>\n\n"
            + (f"کلید فقط یک‌بار نمایش داده می‌شود: روی سرورِ ناشر "
               f"<code>python -m issuer.cli rekey {esc(lic['id'])}</code> "
               "بزنید و کلیدِ تازه را دستی بفرستید." if lic else
               "اشتراک در پنل سالم است. لینک را دستی بفرستید."))
        return True, result

    return True, result





def _release_coins(ctx, order_id):
    """
    سکه‌های رزروشده‌ی یک سفارش را برمی‌گرداند.

    رزرو فقط وقتی معنا دارد که راه برگشتی هم داشته باشد. بدون این،
    سفارشی که منقضی یا لغو شود سکه‌ها را برای همیشه نگه می‌دارد و
    مشتری بدون اینکه چیزی گرفته باشد، آن‌ها را از دست می‌دهد.

    دو بار برگرداندن ممکن نیست: تراکنش رزرو بعد از بازگشت به
    «released» تغییر نام می‌دهد، پس دفعه‌ی بعد پیدا نمی‌شود.
    """
    return ctx.db.release_coins(order_id)


def provision(ctx, order_id):
    """
    ساخت یا تمدید کانفیگ در 3x-ui — و ثبتِ شکست، هر شکلی که باشد.

    چرا یک پوسته و نه `record()` کنارِ هر `return False`:
        بدنه پنج راهِ شکست دارد (پلنِ پیدانشده، اینباندِ نبود،
        تمدیدِ هم‌زمان، خطای پنل، خطای غیرمنتظره) و راهِ ششم روزی
        اضافه می‌شود. اولین نسخه فقط دو `except` را ثبت می‌کرد و
        probe نشان داد پنلِ خاموش از راهِ «اینباند پیدا نشد» بیرون
        می‌رود — یعنی سفارش شکست می‌خورد و هیچ رویدادی ثبت نمی‌شد.

        این‌جا نقطه‌ی خروج یکی است، پس راهِ ششم هم خودبه‌خود ثبت
        می‌شود.
    """
    ok, res = _provision(ctx, order_id)
    if not ok:
        try:
            order = ctx.db.get_order(order_id) or {}
            user = (ctx.db.get_user_by_id(order["user_id"])
                    if order.get("user_id") else None) or {}
        except Exception:
            order, user = {}, {}
        record(ctx, "provision_failed", order.get("user_id"),
               {"order": order_id, "error": res},
               who=user.get("first_name") or user.get("tg_id"))
    return ok, res


def _provision(ctx, order_id):
    """بدنه — هیچ‌کس جز پوسته‌ی بالا صدایش نمی‌زند."""
    order = ctx.db.get_order(order_id)
    plan = ctx.db.get_plan(order["plan_id"]) if order.get("plan_id") else None
    if not plan:
        return False, "پلن این سفارش پیدا نشد"

    # A Pro license (Phase 4): the issuer delivers it. First, before any of
    # the reseller or 3x-ui logic below, and returning the same (ok, result)
    # so close_order, refunds, payouts and events stay the callers' job.
    if plan.get("kind") == "pro_license":
        return LS.deliver_license(ctx, order, plan)

    user = ctx.db.get_user_by_id(order["user_id"])
    t = DB.get_tenant(ctx.tid)

    # ── فروشگاهِ نماینده ───────────────────────────────────────────
    #
    # سه چیز برای نماینده فرق می‌کند، و هر سه تا امروز جا مانده بودند:
    #
    #   گروه    تنها چیزی که می‌گوید این کانفیگ مالِ کیست. بدونش کانفیگ
    #           در پنلِ مالک ساخته می‌شد و در صورتحسابِ هیچ‌کس نمی‌آمد
    #           — مالک کانفیگ را داده و پولش را از کسی نمی‌گیرد.
    #   پیشوند  نامِ ردیفِ نماینده فارسی است («حسین») و `isalnum`
    #           حرفِ فارسی را نگه می‌دارد؛ یعنی شناسه‌ی کانفیگ و لینکِ
    #           اشتراک فارسی می‌شد. پرتال از اول `portal_slug` را
    #           می‌گذاشت و صفحه‌ی اشتراک برند را از همان تشخیص می‌دهد.
    #   اعتبار  نماینده‌ی پیش‌پرداخت نباید بیشتر از آنچه داده بفروشد.
    #
    # شکستِ هر کدام **پیش از** ساختِ کانفیگ است، نه بعدش.
    reseller = bool(t.get("parent_id"))
    trial = bool(plan.get("is_trial"))
    group = None
    if reseller and trial:
        # تستِ نماینده رایگان است و هزینه‌اش با مالک (تصمیمِ مالک):
        # بی‌گروه ساخته می‌شود تا در صورتحسابِ نماینده نیاید.
        #
        # حجم و مدت و کاربر را **مالک** تعیین می‌کند و همین‌جا جایگزین
        # می‌شوند، نه فقط موقعِ ذخیره: اگر مالک بعداً تست را کوچک کرد، ردیفِ
        # قدیمیِ نماینده هم با عددِ تازه ساخته می‌شود.
        spec = DB.trial_cap()
        if not spec:
            return False, ("تستِ این فروشگاه ساخته نشد: مدیر تستِ رایگانِ "
                           "نماینده‌ها را خاموش کرده")
        plan = dict(plan, gb=spec["gb"], days=spec["days"],
                    ip_limit=spec["ip_limit"])
    elif reseller:
        group = str(t.get("portal_group") or "").strip()
        if not group:
            return False, ("این فروشگاه هنوز گروهِ x-ui ندارد. کانفیگِ "
                           "بی‌گروه در صورتحسابِ کسی شمرده نمی‌شود، پس "
                           "ساخته نشد. مالک باید گروه را تعیین کند")

    if reseller and not trial and not int(plan.get("gb") or 0):
        # نامحدودِ فروشگاهِ حجمی با سقفِ مالک (`core.unlimited_cap`)
        capped = core.unlimited_cap(plan.get("gb"), ctx.s)
        if capped:
            plan = dict(plan, gb=capped)

    inbound = plan.get("inbound_id") or t.get("default_inbound")
    if not inbound and reseller:
        # همان ترتیبِ `_portal_inbound` در پرتال: انتخابِ خودش، بعد
        # پیش‌فرضِ مالک. بدونِ این، کانفیگی که نماینده از ربات می‌فروشد
        # روی اینباندی می‌نشست که از پرتالش نمی‌نشست.
        try:
            own = json.loads(t.get("inbound_ids") or "[]") \
                if (t.get("inbound_mode") or "all") == "custom" else []
        except (json.JSONDecodeError, TypeError):
            own = []
        if own:
            inbound = own[0]
        else:
            inbound = (DB.root_tenant() or {}).get("default_inbound")
    if not inbound:
        # اینباند پیش‌فرض تنظیم نشده.
        #
        # شکست کامل اینجا از دید مشتری یعنی «پول دادم و کانفیگ
        # نگرفتم» — آن هم فقط به‌خاطر یک تنظیم که مدیر جا انداخته.
        # به‌جایش اولین اینباند فعال پنل را برمی‌داریم؛ در حالت
        # پیش‌فرض (all) کلاینت به‌هرحال به همه‌ی اینباندهای فعال
        # وصل می‌شود، پس این انتخاب فقط نقطه‌ی شروع است.
        try:
            active = [i for i in (ctx.xui.inbounds() or [])
                      if i.get("enable", True)]
        except Exception as e:
            log.warning("خواندن اینباندها برای انتخاب خودکار ناموفق: %s", e)
            active = []

        if not active:
            return False, ("اینباند پیش‌فرض تنظیم نشده و هیچ اینباند فعالی "
                           "هم در پنل پیدا نشد")

        inbound = active[0].get("id")
        log.warning("اینباند پیش‌فرض تنظیم نشده — به‌طور خودکار از #%s "
                    "استفاده شد", inbound)

    if reseller:
        prefix = t.get("portal_slug") or "nx"
    else:
        prefix = ctx.s.get("email_prefix") or (t.get("name") or "nx")
    sub_base = ctx.s.get("sub_base_url")
    if not sub_base and reseller:
        # همان ترتیبِ `_sub_base` در پرتال: خودش، بعد مالک، بعد خودِ پنل
        # (که `create_subscription` وقتی خالی باشد می‌پرسد).
        try:
            sub_base = (json.loads((DB.root_tenant() or {}).get("settings")
                                   or "{}") or {}).get("sub_base_url")
        except (json.JSONDecodeError, TypeError):
            sub_base = None

    # کفِ این پلن برای نماینده‌ی پیش‌پرداخت. بکند موقعِ ذخیره‌ی پلن
    # حسابش کرده (`plans.cost`)؛ این‌جا فقط خوانده می‌شود.
    charge = 0
    if reseller and not trial and DB.is_prepaid(t):
        charge = max(0, int(plan.get("cost") or 0))
        if not charge:
            # کف معلوم نیست — فروش را نمی‌ایستانیم چون مشتری پول داده؛
            # صورتحسابِ گروه به‌هرحال این کانفیگ را می‌شمارد. ولی
            # بی‌صدا هم نه.
            log.warning("پلن %s نماینده %s کف ندارد — از اعتبار چیزی کم "
                        "نشد، صورتحسابِ گروه می‌شماردش", plan.get("id"), ctx.tid)

    try:
        # تمدید اشتراک موجود یا ساخت جدید
        if order["kind"] == "renew":
            # مقصد را از خود سفارش می‌خوانیم.
            #
            # قبلاً subs[0] گرفته می‌شد — تازه‌ترین اشتراک، نه آن‌که
            # مشتری برای تمدیدش پول داده بود. کسی که سه اشتراک داشت،
            # اشتباهی یکی دیگر را تمدیدشده می‌دید و همان که می‌خواست
            # منقضی می‌شد.
            sub = None
            target = order.get("renew_sub_id")
            if target:
                sub = ctx.db.q(
                    "SELECT * FROM subscriptions WHERE tenant_id=? AND id=? "
                    "AND user_id=?", (ctx.tid, int(target), user["id"]), one=True)
            if not sub:
                subs = ctx.db.user_subs(user["id"])
                sub = subs[0] if subs else None
            if sub:
                # قفل کوتاه روی همین اشتراک.
                #
                # تاریخ تازه از تاریخ فعلی ساخته می‌شود، پس دو تمدید
                # هم‌زمان هر دو یک مبدأ می‌خوانند و هر دو همان یک ماه
                # را می‌نویسند — دو پرداخت، یک ماه. صداکننده با خطای
                # ما پول را برمی‌گرداند.
                if not ctx.db.claim_renewal(sub["id"]):
                    return False, "این اشتراک همین حالا در حال تمدید است"
                if charge:
                    okc, have = DB.charge_credit(
                        ctx.tid, charge, f"تمدید {sub.get('client_email')}")
                    if not okc:
                        ctx.db.release_renewal(sub["id"])
                        return False, (f"اعتبارِ فروشگاه کافی نیست: لازم "
                                       f"{core.toman(charge)}، موجودی {core.toman(have)} تومان")
                try:
                    # ایمیل را هم می‌دهیم: در 3x-ui نسخه‌ی ۳ شناسه‌ی
                    # اصلی کلاینت ایمیل است و جست‌وجو با آن مطمئن‌تر
                    # از uuid است
                    try:
                        ext = ctx.xui.extend_subscription(
                            sub["inbound_id"], sub["client_uuid"],
                            plan["days"], plan["gb"],
                            email=sub.get("client_email"))
                    except Exception:
                        if charge:
                            DB.refund_credit(
                                ctx.tid, charge,
                                "بازگشت: تمدید روی پنل انجام نشد")
                        raise
                    new_exp = _add_days_iso(sub["expires_at"], plan["days"])
                    # Not started yet (start after first use): 3x-ui added the
                    # days to the pending duration, so the bot does the same
                    # and keeps no date until the first connection.
                    pend = None
                    xexp = ext.get("expiry_ms") if isinstance(ext, dict) else None
                    if xexp is not None and int(xexp) < 0:
                        new_exp, pend = None, -int(xexp) // 86400000
                    elif not sub.get("expires_at") and sub.get("pending_days"):
                        new_exp, pend = None, int(sub["pending_days"]) + int(plan["days"] or 0)

                    # حجم را از همان چیزی می‌گیریم که روی پنل نشست.
                    #
                    # تمدید حجم را جمع می‌کند و شمارنده‌ی مصرف را صفر
                    # نمی‌کند. ربات ولی همان اندازه‌ی پلن را نگه
                    # می‌داشت، پس بعد از اولین تمدید مصرفِ تجمعی با
                    # سقفِ یک دوره سنجیده می‌شد: مشتری که ۴۵ از ۱۰۰
                    # گیگ خرج کرده بود «۹۰٪» می‌دید و هشدار اتمام حجم
                    # می‌گرفت، همان روز اولِ دوره‌ی تازه.
                    new_gb = sub.get("gb") or 0
                    if isinstance(ext, dict) and ext.get("total_bytes") is not None:
                        new_gb = int(round(ext["total_bytes"] / (1024 ** 3)))
                    ctx.db.exec(
                        """UPDATE subscriptions SET expires_at=?, gb=?,
                           is_active=1, pending_days=?,
                           notified_7d=0, notified_3d=0, notified_1d=0,
                           notified_80p=0, ended_at=NULL, notified_del=0
                           WHERE tenant_id=? AND id=?""",
                        (new_exp, new_gb, pend, ctx.tid, sub["id"])
                    )
                    ctx.db.exec(
                        "UPDATE orders SET sub_id=? WHERE tenant_id=? AND id=?",
                        (sub["id"], ctx.tid, order_id))
                finally:
                    ctx.db.release_renewal(sub["id"])
                return True, {**sub, "expires_at": new_exp, "gb": new_gb,
                              "pending_days": pend, "renewed": True}

        email = _free_email(ctx, user, prefix)

        # اینباندهایی که کانفیگ روی آن‌ها ساخته می‌شود.
        #
        # اولویت: تنظیم پلن، بعد تنظیم سراسری. حالت all یعنی همه‌ی
        # اینباندهای فعال، که تصمیمش با خود کلاینت xui است.
        pl_inbounds = None
        t = ctx.tenant
        mode = t.get("inbound_mode") or "all"

        raw = plan.get("inbound_ids")
        if not raw and mode == "custom":
            raw = t.get("inbound_ids")
        elif not raw and mode == "default":
            raw = json.dumps([inbound]) if inbound else None

        if raw:
            try:
                pl_inbounds = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                pl_inbounds = [x.strip() for x in str(raw).split(",") if x.strip()]

        # یادداشت شناسه‌ی کانفیگ را دارد: `_portal_charge_for` موقعِ
        # حذف، برگشتی را از روی همین متن پیدا می‌کند.
        if charge:
            okc, have = DB.charge_credit(ctx.tid, charge, f"ساخت {email}")
            if not okc:
                return False, (f"اعتبارِ فروشگاه کافی نیست: لازم "
                               f"{core.toman(charge)}، موجودی {core.toman(have)} تومان")
        # گروه فقط برای نماینده فرستاده می‌شود؛ مسیرِ مالک همان است که بود.
        extra = {"group": group} if group else {}
        # Start after first use (task 9): the days begin on the first
        # connection, for purchases and trials alike. A shop can turn it off.
        on_use = core.start_on_use(ctx.s) and bool(plan["days"])
        try:
            res = ctx.xui.create_subscription(
                inbound, email, plan["gb"], plan["days"],
                ip_limit=plan["ip_limit"], tg_id=user["tg_id"],
                sub_base_url=sub_base, inbound_ids=pl_inbounds,
                start_on_use=on_use, **extra,
            )
        except Exception:
            if charge:
                DB.refund_credit(ctx.tid, charge,
                                 "بازگشت: کار روی پنل انجام نشد")
            raise

        exp_iso, pending = None, None
        if res["expiry_ms"] and res["expiry_ms"] > 0:
            exp_iso = datetime.fromtimestamp(res["expiry_ms"] / 1000).isoformat(timespec="seconds")
        elif res["expiry_ms"] and res["expiry_ms"] < 0:
            # Counts from the first connection; the sweep writes the date then.
            pending = int(plan["days"] or 0) or None

        sid = ctx.db.exec(
            """INSERT INTO subscriptions (tenant_id, user_id, order_id, plan_id,
                                          plan_name, client_email, client_uuid,
                                          sub_url, inbound_id, gb, expires_at,
                                          pending_days)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            # نام پلن همین‌جا ثبت می‌شود، نه فقط شناسه‌اش. اگر مدیر
            # بعداً پلن را حذف یا عوض کند، مشتری همچنان نام چیزی را
            # می‌بیند که واقعاً خریده.
            (ctx.tid, user["id"], order_id, plan["id"], plan["name"], email,
             res["uuid"], res["sub_url"], inbound, plan["gb"], exp_iso, pending)
        )
        ctx.db.exec("UPDATE orders SET sub_id=? WHERE tenant_id=? AND id=?",
                    (sid, ctx.tid, order_id))
        ctx.db.log("provision", user["id"], {"order": order_id, "sub": sid})

        return True, {"id": sid, "client_email": email, "sub_url": res["sub_url"],
                      "expires_at": exp_iso, "gb": plan["gb"],
                      "pending_days": pending,
                      "plan_name": plan["name"], "renewed": False,
                      # اگر لینک اشتراک ساخته نشد، دست‌کم خود کانفیگ‌ها
                      # را داریم تا مشتری دست‌خالی نماند
                      "configs": res.get("configs") or []}

    except XUIError as e:
        log.error("خطای ساخت کانفیگ: %s", e)
        return False, f"خطای پنل: {e}"
    except Exception as e:
        log.exception("خطای غیرمنتظره در provision")
        return False, f"خطای غیرمنتظره: {e}"


def _add_days_iso(iso, days):
    from datetime import timedelta
    base = datetime.now()
    if iso:
        try:
            cur = datetime.fromisoformat(iso)
            if cur > base:
                base = cur
        except ValueError as _exc:
            log.debug("_add_days_iso step: %s", _exc)
    return (base + timedelta(days=days)).isoformat(timespec="seconds")


def _deliver_kb(ctx, url):
    """
    دکمه‌های پیام تحویل.

    دکمه‌ی «افزودن یک‌کلیک» با اسکیم اپلیکیشن (happ:// و امثالش)
    این‌جا ساخته نمی‌شود: تلگرام آن را نمی‌پذیرد و کل پیام را رد
    می‌کند. یک‌کلیک از روی صفحه‌ی اشتراک انجام می‌شود که با https
    باز می‌شود؛ اگر آدرس اشتراک http(s) باشد، همان را دکمه می‌کنیم.
    """
    rows = []
    if url:
        # دکمه‌ی کپی تلگرام — کاربر لازم نیست متن را دستی انتخاب کند
        rows.append([("📋 کپی لینک اشتراک", url, "copy")])
    if valid_button_url(url):
        rows.append([("📄 صفحه‌ی اشتراک من", url, "url")])
    rows.append([("📚 آموزش نصب", "help"), ("📊 اشتراک‌های من", "mysubs")])
    rows.append([("‹ منوی اصلی", "menu")])
    return kb(rows)


def deliver(ctx, user, sub):
    """
    ارسالِ کانفیگ به مشتری — با قالبِ همان فروشگاه، و QR.

    قالب: `delivered_text` فروشگاه، وگرنه `core.DELIVERED_DEFAULT` (به سبکِ
    متنی که مالک نوشت: نامِ کاربری، لینک، کانال، تشکر). متنِ قدیمیِ چندبخشی
    فقط وقتی لینک ساخته نشده به کار می‌رود — آن‌جا باید توضیح بدهد چه کند.
    """
    if sub.get("license"):
        # The key goes to the buyer's chat only: not into the mini-app inbox,
        # which keeps its messages in the database.
        return ctx.bot.send(user["tg_id"], LS.delivery_text(sub["license"]),
                            keyboard=kb([[("📊 اشتراک‌های من", "mysubs")]]))

    url = sub.get("sub_url")
    if url:
        d0 = core.days_left(sub.get("expires_at"))
        text = core.delivered_message(
            ctx.s.get("delivered_text"),
            title="تمدید شد" if sub.get("renewed") else "ساخته شد",
            name=user.get("first_name") or "",
            username=sub.get("client_email") or "",
            link=url, brand=ctx.brand(),
            channel=public_channel(ctx),
            plan=str(sub.get("plan_name") or ""), gb=core.fmt_gb(sub.get("gb")),
            expires=(f"{core.fa(d0)} روز" if d0 is not None
                     else core.pending_text(sub) or "—"), esc=esc)
        _chat_copy(ctx, user, text, sub)
        sent = _send_delivery(ctx, user, text, url)
        _trial_converted(ctx, user, sub)
        return sent

    title = "تمدید شد" if sub.get("renewed") else "آماده است"
    d = core.days_left(sub.get("expires_at"))

    lines = [
        # نام ثبت‌شده‌ی اشتراک زیر عنوان می‌آید: اگر مشتری چند اشتراک
        # داشته باشد باید همین‌جا بفهمد این کدام است.
        F.header(f"اشتراک شما {title}", "✅", F.b(ctx.sub_label(sub))),
        "",
        F.section("مشخصات", "📊"),
        F.row("حجم", core.fmt_gb(sub.get("gb")), "💾"),
    ]
    if d is not None:
        val = f"{core.fa(d)} روز"
        if sub.get("expires_at"):
            val += f" (تا {core.fa_date(sub['expires_at'])})"
        lines.append(F.row("اعتبار", val, "⏳"))
    elif core.pending_text(sub):
        lines.append(F.row("اعتبار", core.pending_text(sub), "⏳"))
    if sub.get("client_email"):
        lines += ["", F.section("شناسه‌ی کانفیگ", "🏷"),
                  F.code(sub["client_email"])]

    if url:
        lines += [
            "",
            F.section("لینک اشتراک شما", "🔑"),
            F.code(url),
            "",
            F.quote_more(
                F.b("چطور وصل شوم؟"),
                "",
                "۱. دکمه‌ی «کپی لینک» پایین را بزنید.",
                "۲. برنامه‌ی VPN را باز کنید.",
                "۳. گزینه‌ی افزودن از کلیپ‌بورد را بزنید.",
                "۴. سرور را انتخاب کنید و وصل شوید.",
                "",
                "اگر برنامه ندارید، «آموزش نصب» لینک دانلود همه را دارد.",
            ),
        ]
    elif sub.get("configs"):
        # لینک اشتراک نداریم ولی خود کانفیگ‌ها را داریم — همان‌ها را
        # می‌دهیم تا مشتری دست‌خالی نماند و لازم نباشد پشتیبانی
        # را برای چیزی که در دسترس است درگیر کند.
        lines += ["", "🔗 <b>کانفیگ‌های شما</b>"]
        for cfg in sub["configs"][:5]:
            lines.append(f"<code>{esc(cfg)}</code>")
        lines.append("")
        lines.append("<i>هر کدام را که خواستید کپی کنید و در برنامه‌تان "
                     "وارد کنید. همه به یک حساب وصل‌اند.</i>")
    else:
        # بدون لینک، کاربر نمی‌داند چه کند — پس صریح می‌گوییم
        lines += [
            "",
            "⚠️ لینک اشتراک ساخته نشد، ولی <b>خریدتان ثبت شده است</b>.\n"
            "به پشتیبانی پیام بدهید تا همین حالا دستی برایتان بفرستیم.",
        ]

    lines += ["", "<blockquote>هر وقت خواستید، از «اشتراک‌های من» مصرف و "
              "روزهای باقی‌مانده را ببینید.</blockquote>"]

    text = "\n".join(lines)
    _chat_copy(ctx, user, text, sub)
    _send_delivery(ctx, user, text, url)


def _trial_converted(ctx, user, sub):
    """
    اولین خریدِ پولیِ کسی که تست گرفته بود → پیامِ «خریدت موفق بود» (یک‌بار)،
    و پایانِ پیگیری. ادعا با UPDATE شرطی: دو تحویلِ هم‌زمان یک پیام.
    """
    try:
        if sub.get("is_trial") or not ctx.s.get("trial_journey", True):
            return
        u = ctx.db.get_user(user["tg_id"]) or user
        if not u.get("trial_at") or u.get("trial_bought_at"):
            return
        with DB.conn() as c:
            won = c.execute("UPDATE users SET trial_bought_at=CURRENT_TIMESTAMP, trial_step=3 "
                            "WHERE tenant_id=? AND id=? AND trial_bought_at IS NULL",
                            (ctx.tid, u["id"])).rowcount == 1
        if not won:
            return
        ctx.bot.send(u["tg_id"], core.trial_msg(ctx.s, "trial_msg_bought", _journey_name(u),
                                                ctx.brand(), esc=esc))
    except Exception as e:
        # تحویل رفته؛ این فقط پیامِ اضافه است — ولی بی‌صدا نه
        log.warning("پیامِ «خرید موفق» پیگیری نرفت: %s", e)


def _chat_copy(ctx, user, html, sub):
    """
    همان پیامِ تحویل، در صندوقِ مینی‌اپ.

    چرا کپیِ همان متن و نه متنی جدا:
        دو متنِ جدا یعنی روزی یکی‌شان اصلاح می‌شود و دیگری نه — و
        آن‌که فراموش می‌شود همانی است که مشتری می‌خواند. متنِ
        تلگرام از `F.*` ساخته شده، پس فقط تگ‌هایش برداشته می‌شود.

    چرا اصلاً لازم است:
        مشتری بعد از خرید مینی‌اپ را باز می‌کند، نه چتِ ربات را. و
        مشتری‌ای که ربات را بلاک کرده یا نوتیفیکیشن را بسته، پیامِ
        تلگرام را اصلاً نمی‌بیند — ولی پولش را داده.

    **هرگز تحویل را نمی‌شکند.** از داخلِ مسیرِ پول صدا زده می‌شود و
    یک خطای فرعی نباید جای کانفیگِ ساخته‌شده را بگیرد.
    """
    try:
        body = F.plain(html).strip()
        if not body:
            return
        ctx.db.chat_add(user["id"], "system", body,
                        order_id=(sub or {}).get("order_id"))
    except Exception:
        log.debug("کپیِ تحویل در صندوق ناموفق", exc_info=True)


def support_reply(ctx, u, body, photo=None, ticket_id=None, stored=False):
    """
    The one way a support message reaches a buyer: the panel's inbox, the
    reseller portal's inbox, the bot's admin "message" and a ticket reply
    (docs/specs/2026-09-30-vpn-fixes.md, task 4).

    With a mini app the message lives in its chat, and the bot gets one
    short notice with a button that opens it. The notice is not repeated
    while a support message is still unread: five replies in a row are one
    notice, not five full texts cluttering the bot. Without a mini app
    (Community, or no https domain) the bot is the only place to read it,
    so the text is sent in full.

    `stored`: the caller already put it in the chat (the panel's inbox).
    Returns what the bot sent, or None when a notice was already waiting.
    """
    if not stored:
        ctx.db.chat_add(u["id"], "admin", str(body or "")[:2000], photo=photo)
    app_url = miniapp_url(ctx)
    if not app_url:
        txt = "💬 <b>پاسخ پشتیبانی</b>\n\n" + esc(str(body or "📷 عکس"))
        if ticket_id:
            txt += (f"\n\n<blockquote>درباره‌ی پیامی که فرستاده بودید، "
                    f"شماره پیگیری <code>#{ticket_id}</code></blockquote>")
        return ctx.bot.send(u["tg_id"], txt,
                            keyboard=kb([[("💬 پاسخ دوباره", "support")],
                                         [("‹ منوی اصلی", "menu")]]))
    if ctx.db.chat_unread_from_support(u["id"]) > 1:
        return None                      # an earlier notice is still unread
    chat_url = app_url + ("&" if "?" in app_url else "?") + "tab=chat"
    return ctx.bot.send(u["tg_id"], "💬 پیام تازه‌ای از پشتیبانی دارید.",
                        keyboard=kb([[("💬 باز کردن گفتگو", chat_url, "web_app")]]))


def _chat_notice(ctx, srow, html):
    """
    یادآوری‌ها در صندوقِ مینی‌اپ.

    چرا: مشتری‌ای که ربات را بلاک کرده یا نوتیفیکیشن را بسته، هیچ
    یادآوری‌ای نمی‌بیند و اولین خبری که می‌گیرد قطع‌شدنِ اتصال است.
    صندوق همیشه هست.

    **همان متنِ تلگرام**، فقط بدونِ تگ — دو متنِ جدا یعنی روزی
    یکی‌شان اصلاح می‌شود و دیگری نه.

    `user_id` روی ردیفِ اشتراک هست؛ اگر نبود بی‌صدا رد می‌شویم، چون
    پیامِ بی‌صاحب در صندوقِ کسِ دیگری می‌نشیند.
    """
    try:
        uid = (srow or {}).get("user_id")
        if not uid:
            return
        body = F.plain(html).strip()
        if body:
            ctx.db.chat_add(uid, "system", body)
    except Exception:
        log.debug("یادآوری در صندوق ثبت نشد", exc_info=True)


def _send_delivery(ctx, user, text, url):
    """
    ارسال پیام تحویل با تضمین رسیدن.

    اگر تلگرام صفحه‌کلید را رد کند (مثلاً یک دکمه‌ی url نامعتبر)،
    کل پیام رد می‌شود و مشتری کانفیگش را نمی‌گیرد — در حالی که پول
    داده و کانفیگ در پنل ساخته شده. پس اگر ارسال با دکمه شکست خورد،
    بدون دکمه دوباره می‌فرستیم. متن مهم است، دکمه تزئین.
    """
    try:
        sent = ctx.bot.send(user["tg_id"], text,
                            keyboard=_deliver_kb(ctx, url))
    except TelegramError as e:
        log.warning("ارسال تحویل با صفحه‌کلید ناموفق (%s) — بدون دکمه "
                    "دوباره تلاش می‌شود", e)
        sent = ctx.bot.send(user["tg_id"], text)

    # کیوآر لینک — روی گوشی خیلی راحت‌تر از کپی‌کردن یک لینک بلند است،
    # مخصوصاً وقتی مشتری روی همان گوشی هم تلگرام دارد هم اپ VPN.
    # اگر ساخته نشد، تحویل که رسیده است؛ این فقط اضافه است.
    if url:
        try:
            png = qr.make(url)
            if png:
                ctx.bot.send_photo_bytes(
                    user["tg_id"], png, filename="nexora-sub.png",
                    caption="📷 <b>کیوآر همین لینک</b>\n\n"
                            "<blockquote>در اپ VPN گزینه‌ی افزودن با اسکن را "
                            "بزنید و این را نشان دوربین بدهید. نیازی به کپی "
                            "کردن لینک نیست.</blockquote>")
        except Exception as e:
            log.warning("ارسال کیوآر ناموفق: %s", e)

    return sent


# ═══════════════════════════════════════════════════════════
#  بخش‌های منو
# ═══════════════════════════════════════════════════════════

def show_subs(ctx, user, chat_id, message_id):
    subs = ctx.db.user_subs(user["id"])
    lics = ctx.db.user_licenses(user["id"])
    if lics and not subs:
        return show_licenses(ctx, user, chat_id, message_id, lics)
    if not subs and _license_store(ctx):
        return _reply(ctx, chat_id, message_id,
                      "🔑 <b>مجوزهای شما</b>\n\n"
                      "هنوز مجوزی اینجا نیست.\n\n"
                      "هر مجوزی که بخرید با تاریخ اعتبارش همین‌جا می‌آید "
                      "و تمدیدش هم از همین‌جاست.",
                      kb([[("🛒 خرید نکسورا Pro", "buy")], [("‹ بازگشت", "menu")]]))
    if not subs:
        return _reply(ctx, chat_id, message_id,
                      "📊 <b>اشتراک‌های شما</b>\n\n"
                      "هنوز اشتراکی اینجا نیست.\n\n"
                      "اولین اشتراکتان کمتر از یک دقیقه طول می‌کشد: "
                      "پلن را انتخاب می‌کنید، رسید می‌فرستید و تحویل می‌گیرید.",
                      kb([[("🛒 خرید اشتراک", "buy")], [("‹ بازگشت", "menu")]]))

    lines = ["📊 <b>اشتراک‌های شما</b>", ""]
    rows = []

    # مصرف واقعی از پنل — بدون این، کاربر نمی‌داند چقدر مانده و
    # وقتی حجمش تمام شود فکر می‌کند سرویس خراب است
    client = None
    try:
        client = ctx.xui
    except Exception as _exc:
        log.debug("show_subs step: %s", _exc)

    for s in subs:
        d = core.days_left(s.get("expires_at"))
        expired = d is not None and d <= 0

        used_gb = None
        if client and s.get("client_email"):
            try:
                t = client.client_traffic(s["client_email"])
                if t:
                    up = int(t.get("up") or 0)
                    down = int(t.get("down") or 0)
                    used_gb = round((up + down) / (1024 ** 3), 1)
            except Exception as _exc:
                log.debug("show_subs step: %s", _exc)

        total_gb = s.get("gb") or 0
        pct = None
        if total_gb and used_gb is not None:
            pct = min(100, round(used_gb * 100 / total_gb))

        if expired:
            status = "🔴"
        elif pct is not None and pct >= 90:
            status = "🟠"
        elif d is not None and d <= 3:
            status = "🟡"
        else:
            status = "🟢"

        # نام اشتراک = پلن + سرور. بدون نام سرور، سه اشتراک هم‌پلن
        # سه خط کاملاً یکسان می‌شوند و مشتری گم می‌شود.
        lines.append(f"{status} {F.b(ctx.sub_label(s))}")

        # نوار مصرف — سریع‌ترین راه فهمیدن وضعیت
        if pct is not None:
            filled = round(pct / 10)
            bar = "█" * filled + "░" * (10 - filled)
            left_gb = max(0, round(total_gb - used_gb, 1))
            lines.append(f"{F.code(bar)} {core.fa(pct)}٪")
            lines.append(f"💾 {F.b(f'{core.fa(left_gb)} گیگ')} باقی مانده "
                         f"{F.i(f'({core.fa(used_gb)} از {core.fmt_gb(total_gb)} مصرف شده)')}")
        elif used_gb is not None:
            lines.append(f"💾 {F.b(f'{core.fa(used_gb)} گیگ')} مصرف شده (حجم نامحدود)")
        else:
            lines.append(f"💾 {core.fmt_gb(total_gb)} ترافیک")

        if d is None:
            lines.append(f"⏳ {core.pending_text(s) or 'بدون محدودیت زمانی'}")
        elif expired:
            gone = core.days_past(s.get("expires_at"))
            lines.append(
                f"⛔ {F.b('امروز')} منقضی شد" if gone < 1 else
                f"⛔ {F.b(f'{core.fa(gone)} روز پیش')} منقضی شده")
        else:
            line = f"⏳ {F.b(f'{core.fa(d)} روز')} اعتبار"
            if s.get("expires_at"):
                line += f" (تا {core.fa_date(s['expires_at'])})"
            lines.append(line)

        if s.get("client_email"):
            lines.append(f"🏷 {F.code(s['client_email'])}")

        if s.get("sub_url"):
            lines.append(f"🔗 {F.code(s['sub_url'])}")

        lines.append("")

        # هر اشتراک یک دکمه به صفحه‌ی خودش — با QR و لینک در بالا (مالک:
        # «وارد اشتراکم می‌شوم باید کیوآرکد و لینکم با اطلاعات بیاید بالا»).
        # تمدید در همان صفحه است.
        icon = "📄" if not expired else "⚡"
        rows.append([(f"{icon} {ctx.sub_label(s)}", f"sub:{s['id']}")])

    for lrow in lics:
        lines += [LS.license_line(lrow), ""]
        rows.append([(f"🔑 {lrow['license_id']}", f"lic:{lrow['license_id']}")])

    lines.append(F.quote(
        "لینک را بزنید تا کپی شود، بعد در برنامه‌تان وارد کنید.",
        "اگر بلد نیستید، «آموزش نصب» را بزنید."))
    rows.append([("📚 آموزش نصب", "help")])

    rows.append([("‹ بازگشت", "menu")])
    _reply(ctx, chat_id, message_id, "\n".join(lines), kb(rows))


def show_licenses(ctx, user, chat_id, message_id, lics):
    """"My subscriptions" for a buyer who has only Pro licenses."""
    lines = ["🔑 <b>مجوزهای شما</b>", ""]
    rows = []
    for lrow in lics:
        lines += [LS.license_line(lrow), ""]
        rows.append([(f"🔑 {lrow['license_id']}", f"lic:{lrow['license_id']}")])
    rows.append([("‹ بازگشت", "menu")])
    return _reply(ctx, chat_id, message_id, "\n".join(lines), kb(rows))


def _renew_plans(ctx, lrow):
    """License plans that can renew this license: same unit (the issuer
    extends by the license's own unit), and sellable here."""
    return [p for p in ctx.db.plans()
            if p.get("kind") == "pro_license" and _sellable(ctx, p)
            and core.clean_license_plan(p.get("license_plan")) == lrow["plan"]]


def show_license(ctx, user, chat_id, message_id, license_id):
    """One license: id, paid until, key hint, and how to renew it."""
    lrow = ctx.db.user_license(user["id"], license_id)
    if not lrow:
        return _reply(ctx, chat_id, message_id, "این مجوز پیدا نشد.", back_kb("mysubs"))
    lines = [LS.license_line(lrow), ""]
    rows = []
    plans = _renew_plans(ctx, lrow)
    if plans:
        lines.append(F.quote("تمدید همین مجوز را جلو می‌برد؛ کلید عوض نمی‌شود و "
                             "لازم نیست روی سرور کاری بکنید."))
        for p in plans:
            if user["balance"] >= p["price"]:
                rows.append([(f"👛 تمدید از کیف پول · {core.plan_line(p)}",
                              f"lwp:{p['id']}:{lrow['license_id']}")])
            rows.append([(f"💳 تمدید · {core.plan_line(p)}",
                          f"lck:{p['id']}:{lrow['license_id']}")])
    else:
        lines.append(F.quote("فعلاً پلنی برای تمدیدِ این مجوز در فروش نیست؛ "
                             "به پشتیبانی پیام بدهید."))
        rows.append([("💬 پشتیبانی", "support")])
    rows.append([("‹ اشتراک‌های من", "mysubs")])
    return _reply(ctx, chat_id, message_id, "\n".join(lines), kb(rows))


def _license_renew_args(ctx, user, arg):
    """(plan_id, license_id) from "<plan>:<license>", only when the license is
    this user's and the plan can renew it. None otherwise: a forged callback
    must not create an order at all."""
    pid, _, lid = arg.partition(":")
    if not pid.isdigit():
        return None
    lrow = ctx.db.user_license(user["id"], lid)
    if not lrow or int(pid) not in {p["id"] for p in _renew_plans(ctx, lrow)}:
        return None
    return int(pid), lid


def show_sub(ctx, user, chat_id, message_id, sub_id):
    """
    صفحه‌ی یک اشتراک: **QR بالا**، زیرش لینک و مشخصات، و دکمه‌ها.

    یک پیامِ عکس‌دار، نه دو پیام: کیوآر و لینک و مصرف با هم دیده می‌شوند.
    مالکیت با `user_id` سنجیده می‌شود — شناسه‌ی دست‌کاری‌شده به «پیدا نشد»
    می‌رسد.
    """
    s = ctx.db.q("SELECT s.*, p.name AS plan_name FROM subscriptions s "
                 "LEFT JOIN plans p ON p.id=s.plan_id "
                 "WHERE s.tenant_id=? AND s.id=? AND s.user_id=?",
                 (ctx.tid, int(sub_id), user["id"]), one=True)
    if not s:
        return _reply(ctx, chat_id, message_id, "این اشتراک پیدا نشد.", back_kb("mysubs"))

    d = core.days_left(s.get("expires_at"))
    expired = d is not None and d <= 0
    used_gb = None
    try:
        t = ctx.xui.client_traffic(s["client_email"]) if s.get("client_email") else None
        if t:
            used_gb = round((int(t.get("up") or 0) + int(t.get("down") or 0)) / (1024 ** 3), 1)
    except Exception as _exc:
        log.debug("show_sub usage: %s", _exc)
    total = s.get("gb") or 0

    lines = [f"{'🔴' if expired else '🟢'} {F.b(ctx.sub_label(s))}", ""]
    if s.get("client_email"):
        lines.append(f"👤 {F.code(s['client_email'])}")
    if used_gb is not None and total:
        left = max(0, round(total - used_gb, 1))
        lines.append(f"💾 {F.b(f'{core.fa(left)} گیگ')} مانده "
                     f"{F.i(f'({core.fa(used_gb)} از {core.fmt_gb(total)})')}")
    elif used_gb is not None:
        lines.append(f"💾 {F.b(f'{core.fa(used_gb)} گیگ')} مصرف شده (حجم نامحدود)")
    else:
        lines.append(f"💾 {core.fmt_gb(total)}")
    if d is None:
        lines.append(f"⏳ {core.pending_text(s) or 'بدون محدودیت زمانی'}")
    elif expired:
        lines.append(f"⛔ {F.b('منقضی شده')}")
    else:
        lines.append(f"⏳ {F.b(f'{core.fa(d)} روز')} (تا {core.fa_date(s['expires_at'])})")
    url = s.get("sub_url") or ""
    if url:
        lines += ["", "🔗 لینک اشتراک:", F.code(url)]

    rows = []
    if url:
        rows.append([("📋 کپی لینک", url, "copy")])
    rows.append([("⚡ تمدید" if expired else "🔄 تمدید", f"renew:{s['id']}")])
    rows.append([("📚 آموزش نصب", "help"), ("‹ اشتراک‌های من", "mysubs")])
    caption = "\n".join(lines)

    png = None
    if url:
        try:
            png = qr.make(url)
        except Exception as e:
            log.warning("کیوآرِ صفحه‌ی اشتراک ساخته نشد: %s", e)
    if png:
        try:
            return ctx.bot.send_photo_bytes(chat_id, png, filename="sub.png",
                                            caption=caption, keyboard=kb(rows))
        except TelegramError as e:
            # عکس نرفت (مثلاً کپشنِ بلند) — متن مهم‌تر است
            log.warning("صفحه‌ی اشتراک با کیوآر نرفت (%s) — بی‌عکس", e)
    return _reply(ctx, chat_id, message_id, caption, kb(rows))


def show_renew(ctx, user, chat_id, message_id, sub_id):
    """
    تمدید یک اشتراک مشخص.

    نام پلن همه‌جا می‌آید: کسی که سه اشتراک دارد باید بداند دارد
    کدامش را تمدید می‌کند، وگرنه پول می‌دهد و اشتباه تمدید می‌شود.
    """
    sub = ctx.db.q(
        "SELECT * FROM subscriptions WHERE tenant_id=? AND id=? AND user_id=?",
        (ctx.tid, sub_id, user["id"]), one=True
    )
    if not sub:
        return _reply(ctx, chat_id, message_id,
                      "این اشتراک پیدا نشد.", back_kb("mysubs"))

    plan = ctx.db.get_plan(sub["plan_id"]) if sub.get("plan_id") else None
    left = core.days_left(sub.get("expires_at"))

    # تیتر خودش می‌گوید کدام اشتراک — نه «تمدید اشتراک» خشک و خالی.
    # نام پلن را صریح می‌دهیم چون این ردیف از SELECT خام آمده.
    label = ctx.sub_label(sub, plan_name=(plan or {}).get("name")
                          if plan else sub.get("plan_name"))
    lines = [F.header("تمدید اشتراک", "🔄", F.b(label)), ""]
    lines.append(F.section("وضعیت فعلی", "📊"))

    if plan:
        lines.append(F.row("پلن", core.fmt_gb(plan["gb"]) + " · "
                           + core.fmt_days(plan["days"]), "📦"))

    if left is None:
        lines.append(F.row("اعتبار", core.pending_text(sub) or "بدون محدودیت زمانی", "⏳"))
    elif left <= 0:
        lines.append(F.row("اعتبار", "تمام شده", "⛔"))
    else:
        lines.append(F.row("باقی‌مانده", f"{core.fa(left)} روز", "⏳"))

    if sub.get("client_email"):
        lines += ["", F.section("شناسه‌ی کانفیگ", "🏷"),
                  F.code(sub["client_email"])]

    rows = []
    if plan:
        lines += ["", F.hr(),
                  F.row("مبلغ تمدید",
                        core.toman(plan["price"]) + " تومان", "💰"), ""]
        lines.append(F.quote(
            "بعد از تمدید، همین کانفیگ ادامه پیدا می‌کند. لازم نیست "
            "چیزی را در برنامه‌تان عوض کنید."))
        if user["balance"] >= plan["price"]:
            rows.append([("👛 تمدید آنی از کیف پول",
                          f"wpay:{plan['id']}:{sub['id']}")])
        rows.append([(f"💳 تمدید · {core.toman(plan['price'])} تومان",
                      f"chk:{plan['id']}:0:{sub['id']}")])
    else:
        lines += ["", "پلن این اشتراک دیگر موجود نیست. از فهرست پلن‌ها "
                  "یکی انتخاب کنید."]
        rows.append([("🛒 دیدن پلن‌ها", "buy")])

    rows.append([("‹ اشتراک‌های من", "mysubs")])
    return _reply(ctx, chat_id, message_id, "\n".join(lines), kb(rows))


def show_wallet(ctx, user, chat_id, message_id):
    u = ctx.db.get_user(user["tg_id"])
    txs = ctx.db.q(
        "SELECT * FROM wallet_tx WHERE tenant_id=? AND user_id=? ORDER BY id DESC LIMIT 5",
        (ctx.tid, u["id"])
    )
    lines = [
        "👛 <b>کیف پول</b>",
        "",
        f"💰 موجودی: <b>{core.toman(u['balance'])}</b> تومان",
    ]
    if txs:
        lines += ["", "📄 <b>آخرین تراکنش‌ها</b>"]
        for t in txs:
            sign = "+" if t["amount"] > 0 else "−"
            lines.append(f"{sign} {core.toman(abs(t['amount']))} · "
                         f"{esc(t.get('note') or t['kind'])}")

    lines += ["", "<i>با کیف پول شارژشده، خرید بعدی‌تان بدون انتظارِ تأیید "
              "رسید انجام می‌شود و تمدید خودکار هم فعال می‌ماند.</i>"]

    return _reply(ctx, chat_id, message_id, "\n".join(lines),
                  kb([[("💳 شارژ کیف پول", "topup")],
                      [("‹ منو", "menu")]]))


def wallet_topup(ctx, user, chat_id, message_id):
    """
    انتخاب مبلغ شارژ.

    همان جریان کارت‌به‌کارت خرید است — مبلغ انتخاب می‌شود، رسید
    می‌آید، شما تایید می‌کنید و موجودی اضافه می‌شود.
    """
    # کارت‌ها در تنظیمات مستاجر ذخیره می‌شوند، نه در جدول.
    #
    # این‌جا از جدولی به نام cards می‌خواند که هیچ‌وقت ساخته نشده —
    # پس هر بار که مشتری «شارژ کیف پول» را می‌زد، یک
    # OperationalError بالا می‌رفت و هیچ پاسخی نمی‌گرفت. مسیر خرید
    # از همان اول درست بود (core.pick_card روی ctx.s) و فقط شارژ
    # کیف پول جا مانده بود.
    cards = [c for c in (ctx.s.get("cards") or [])
             if isinstance(c, dict) and c.get("number")
             and c.get("active", True)]
    if not cards:
        return _reply(ctx, chat_id, message_id,
                      "شارژ کیف پول فعلاً در دسترس نیست.", back_kb("wallet"))

    amounts = [100000, 200000, 500000, 1000000]
    rows = [[(f"{core.toman(a)} تومان", f"topup:{a}")] for a in amounts]
    rows.append([("‹ بازگشت", "wallet")])

    return _reply(ctx, chat_id, message_id,
                  "💳 <b>شارژ کیف پول</b>\n\n"
                  "مبلغ را انتخاب کنید. بعد از واریز و فرستادن رسید، "
                  "موجودی‌تان اضافه می‌شود و خریدهای بعدی <b>بدون انتظار</b> "
                  "انجام می‌شوند.",
                  kb(rows))


#: کمینه و بیشینه‌ی شارژ — یک جا، چون هم ربات می‌سنجدش هم مینی‌اپ
TOPUP_MIN = 10_000
TOPUP_MAX = 50_000_000


def topup_order(ctx, user, amount):
    """
    هسته‌ی شارژ کیف پول: سفارشِ `topup` بساز و کارت را برگردان.

    چرا هسته شد: مینی‌اپ هم باید همین کار را بکند، و اگر آن‌جا
    دوباره نوشته شود می‌شود مسیرِ دومی که یک روز یکی از قاعده‌ها را
    فراموش می‌کند — دقیقاً همان چیزی که سه مسیرِ خرید سرش اتفاق
    افتاد.

    برمی‌گرداند `(order, card)`؛ روی ورودیِ بد `ValueError` با متنی
    که مستقیم قابل نشان‌دادن است.
    """
    closed = store_gate(ctx)
    if closed:
        raise ValueError(closed)
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise ValueError("این مبلغ خوانده نشد")

    if not (TOPUP_MIN <= amount <= TOPUP_MAX):
        raise ValueError("مبلغ باید بین ۱۰ هزار تا ۵۰ میلیون تومان باشد")

    u = ctx.db.get_user(user["tg_id"]) if user.get("tg_id") else user
    card = core.pick_card(ctx.s.get("cards"))
    if not card:
        raise ValueError("هنوز شماره کارتی ثبت نشده")

    # plan_id خالی یعنی این سفارش شارژ است نه خرید پلن
    order = ctx.db.create_order(u["id"], None, amount, amount, kind="topup")
    ctx.db.set_state(u["id"], "await_receipt", {"order_id": order["id"]})
    return order, card


def wallet_topup_amount(ctx, user, chat_id, message_id, amount):
    """پوسته‌ی تلگرامیِ `topup_order` — منطقش این‌جا نیست."""
    try:
        order, card = topup_order(ctx, user, amount)
    except ValueError as e:
        msg = str(e)
        if "کارتی" in msg:
            msg += ("\n\n<blockquote>از پنل، بخش «اتصال و تنظیمات»، کارت را "
                    "اضافه کنید.</blockquote>")
        return _reply(ctx, chat_id, message_id, msg, back_kb("wallet"))

    amount = int(order["amount"])

    return _reply(ctx, chat_id, message_id,
                  f"💳 <b>شارژ کیف پول</b>\n\n"
                  f"مبلغ: <b>{core.toman(amount)}</b> تومان\n\n"
                  f"این مبلغ را به کارت زیر واریز کنید:\n"
                  f"<code>{core.fmt_card(card['number'])}</code>\n"
                  f"به نام <b>{esc(card['holder'])}</b>\n\n"
                  f"بعد <b>عکس رسید</b> یا <b>متن پیامک بانک</b> را همین‌جا "
                  f"بفرستید تا موجودی‌تان اضافه شود.",
                  kb([[("📋 کپی شماره کارت",
                        "".join(c for c in str(card["number"]) if c.isdigit()),
                        "copy")],
                      [("📋 کپی مبلغ", str(amount), "copy")],
                      [("‹ انصراف", "wallet")]]))


def show_coins(ctx, user, chat_id, message_id):
    u = ctx.db.get_user(user["tg_id"])
    cs = core.coin_settings(ctx.s.get("coins"))
    prog = core.coin_progress(u["coins"], ctx.s.get("coins"))

    lines = [
        "🪙 <b>سکه‌های شما</b>",
        "",
        f"موجودی: <b>{core.fa(prog['coins'])} سکه</b>",
    ]
    if prog["current_percent"]:
        lines.append(f"همین حالا <b>{core.fa(prog['current_percent'])}٪ تخفیف</b> "
                     f"دارید <i>(با خرج {core.fa(prog['current_cost'])} سکه)</i>")
    if prog["next"]:
        lines.append(f"با <b>{core.fa(prog['next']['need'])} سکه</b> دیگر، "
                     f"تخفیف {core.fa(prog['next']['percent'])}٪ باز می‌شود")

    lines += ["", "<b>پله‌های تخفیف</b>"]
    for t in cs["tiers"]:
        mark = "✅" if u["coins"] >= t["coins"] else "▫️"
        lines.append(f"{mark} {core.fa(t['coins'])} سکه: "
                     f"{core.fa(t['percent'])}٪ تخفیف")

    earn = loyalty_on()
    lines += [
        "",
        (f"هر دوستی که با لینک شما بیاید و <b>خرید کند</b>، "
         f"<b>{core.fa(cs['per_referral'])} سکه</b> به شما می‌رسد.") if earn else "",
        "",
        "<i>سکه‌ها تاریخ انقضا ندارند. می‌توانید جمعشان کنید تا "
        "به پله‌ی بالاتر برسید.</i>"
        if not cs.get("expire_days") else "",
    ]

    # فاصله‌های خالی عمدی‌اند (گروه‌بندی بصری) — فقط خط آخر که ممکن
    # است شرطی خالی بماند حذف می‌شود، نه همه‌ی خالی‌ها
    while lines and lines[-1] == "":
        lines.pop()

    _reply(ctx, chat_id, message_id, "\n".join(lines),
           kb(([[("🎁 دعوت دوستان", "ref")]] if earn else []) + [[("‹ بازگشت", "menu")]]))


def show_referral(ctx, user, chat_id, message_id):
    """The invite screen (Pro, `loyalty`). Locked or absent, an invite button
    left in an older message still answers, and says so: a shown button must
    work."""
    mod = loyalty_on()
    if not mod:
        _reply(ctx, chat_id, message_id,
               "🎁 دعوتِ دوستان فعلاً فعال نیست.", kb([[("‹ بازگشت", "menu")]]))
        return
    text, rows = mod.referral_screen(ctx, user)
    _reply(ctx, chat_id, message_id, text, kb(rows))


def show_help(ctx, user, chat_id, message_id):
    # جزئیاتِ هر قدم داخل نقل‌قول جمع‌شونده می‌رود: کسی که بلد است سه
    # خط می‌بیند و رد می‌شود، کسی که نیست بازش می‌کند و کامل می‌خواند.
    txt = ctx.s.get("help_text") or F.join(
        F.title("آموزش نصب", "📚"),
        F.lines(
            "سه قدم، کمتر از دو دقیقه:",
            "",
            f"{F.b('۱.')} برنامه‌ی مناسب دستگاهتان را از دکمه‌های پایین نصب کنید",
            f"{F.b('۲.')} به «اشتراک‌های من» بروید و لینک اشتراک را کپی کنید",
            f"{F.b('۳.')} در برنامه، گزینه‌ی افزودن از لینک را بزنید و بچسبانید",
        ),
        F.quote_more(
            F.b("جزئیات هر قدم"),
            "",
            F.b("اندروید") + ": برنامه‌ی v2rayNG یا Happ را نصب کنید. بالا "
            "سمت راست علامت + را بزنید و «Import from clipboard» را انتخاب کنید.",
            "",
            F.b("آیفون") + ": برنامه‌ی Streisand یا Happ. روی + بزنید و "
            "«افزودن از کلیپ‌بورد» را انتخاب کنید.",
            "",
            F.b("ویندوز") + ": برنامه‌ی v2rayN. از منوی Servers گزینه‌ی "
            "«Import from clipboard» را بزنید.",
            "",
            "بعد از افزودن، سرور را انتخاب و دکمه‌ی اتصال را بزنید. اگر "
            "وصل نشد، یک سرور دیگر از همان لیست را امتحان کنید.",
        ),
        F.quote("اگر جایی گیر کردید، از پشتیبانی بپرسید."),
    )
    rows = []
    apps = ctx.s.get("apps") or []
    for a in apps[:6]:
        if a.get("url"):
            rows.append([(f"📥 {a.get('name')}", a["url"], "url")])
    rows.append([("‹ بازگشت", "menu")])
    _reply(ctx, chat_id, message_id, txt, kb(rows))


def start_support(ctx, user, chat_id, message_id):
    ctx.db.set_state(user["tg_id"], "await_ticket", {})
    _reply(ctx, chat_id, message_id,
           "💬 <b>پشتیبانی</b>\n\n"
           "مشکل یا سوالتان را در یک پیام بنویسید. هرچه دقیق‌تر باشد، "
           "سریع‌تر حل می‌شود.\n\n"
           "<i>اگر درباره‌ی سفارش است، کد پیگیری‌اش را هم بنویسید.</i>",
           kb([[("✖️ انصراف", "menu")]]))


def handle_ticket(ctx, msg, user):
    text = msg.get("text") or msg.get("caption") or ""
    if not text.strip():
        return ctx.bot.send(user["tg_id"],
                            "پیامتان را به‌صورت متن بنویسید تا ثبت شود.")

    tid = ctx.db.exec(
        "INSERT INTO tickets (tenant_id, user_id, message) VALUES (?,?,?)",
        (ctx.tid, user["id"], text[:2000])
    )
    ctx.db.clear_state(user["tg_id"])
    ctx.bot.send(user["tg_id"],
                 "✅ <b>پیامتان ثبت شد</b>\n\n"
                 "پاسخ را همین‌جا در تلگرام می‌گیرید و لازم نیست منتظر بمانید.\n\n"
                 f"<i>شماره پیگیری:</i> <code>#{tid}</code>",
                 keyboard=main_menu(ctx, user))

    ctx.notify_group(
        f"🎫 <b>تیکت #{tid}</b>\n\n"
        f"👤 {esc(user.get('first_name'))} (<code>{user['tg_id']}</code>)\n\n"
        f"{esc(text[:800])}",
        keyboard=kb([[("✍️ پاسخ", f"tk:{tid}")]]),
        topic="tickets"
    )


def check_membership(ctx, u, force=False, again="menu"):
    """
    بررسی عضویت اجباری کانال.

    برمی‌گرداند: (مجاز, کیبورد_دعوت)
    اگر کانالی تنظیم نشده، همیشه مجاز است. اگر تلگرام خطا داد
    (مثلاً ربات در کانال ادمین نیست)، سخت‌گیری نمی‌کنیم — قفل‌شدن
    کل فروش بدتر از رد نشدن یک نفر است.

    `force`: برای تستِ رایگان، حتی وقتی قفلِ عمومیِ کانال خاموش است
    (`trial_channel`) — مالک: «تایید عضویت در کانال قبلِ گرفتنِ لینکِ تست».
    `again`: دکمه‌ی «عضو شدم» به کجا برگردد.
    """
    if not ctx.s.get("force_channel_on") and not force:
        return True, None
    ch = ctx.s.get("force_channel")
    if not ch:
        return True, None
    try:
        st = ctx.bot.member_status(ch, u["tg_id"])
    except Exception:
        return True, None
    if st in ("member", "administrator", "creator"):
        return True, None

    link = ch if str(ch).startswith("http") else f"https://t.me/{str(ch).lstrip('@')}"
    return False, kb([
        [("📢 عضویت در کانال", link, "url")],
        [("✅ عضو شدم، بررسی کن", again)],
    ])


def trial_needs_channel(ctx):
    """تست پیش از لینک عضویت را می‌سنجد؟ (پیش‌فرض بله، اگر کانالی هست)"""
    return bool(ctx.s.get("force_channel")) and bool(ctx.s.get("trial_channel", True))


def require_membership(ctx, chat_id, message_id, u, force=False, again="menu"):
    """اگر عضو نبود پیام می‌دهد و True برمی‌گرداند (یعنی ادامه نده)."""
    allowed, invite = check_membership(ctx, u, force=force, again=again)
    if allowed:
        return False
    _reply(ctx, chat_id, message_id,
           "📢 <b>یک قدم مانده</b>\n\n"
           "برای ادامه، اول در کانال ما عضو شوید. اطلاع‌رسانی قطعی‌ها و "
           "تخفیف‌ها همان‌جا منتشر می‌شود.\n\n"
           "بعد از عضویت، دکمه‌ی «عضو شدم» را بزنید.", invite)
    return True


def affiliates_on():
    """The affiliates module when it may run now (Pro present and licensed)."""
    try:
        mod = pro("affiliates")
    except Exception:
        log.exception("Pro affiliates module failed to load; the partner panel stays off")
        return None
    return mod if mod is not None and pro_allowed("affiliates") else None


def affiliate_panel(ctx, user, chat_id, message_id):
    """The partner's panel (Pro, `affiliates`). Locked, a panel button left in
    an older message still answers, and says so."""
    mod = affiliates_on()
    if not mod:
        return _reply(ctx, chat_id, message_id,
                      "💼 پنل همکاری فعلاً در دسترس نیست.", back_kb())
    text, rows = mod.panel_screen(ctx, user)
    return _reply(ctx, chat_id, message_id, text, kb(rows) if rows else back_kb())


def affiliate_list(ctx, user, chat_id, message_id):
    """The partner's sales list (Pro, `affiliates`)."""
    mod = affiliates_on()
    if not mod:
        return _reply(ctx, chat_id, message_id,
                      "💼 پنل همکاری فعلاً در دسترس نیست.", back_kb())
    text, rows = mod.list_screen(ctx, user)
    return _reply(ctx, chat_id, message_id, text, kb(rows) if rows else back_kb())


def my_orders(ctx, user, chat_id, message_id):
    """
    تاریخچه‌ی سفارش‌های کاربر.

    هر سفارش با وضعیتش می‌آید — تا کاربر بداند رسیدش دیده شده یا
    نه، و اگر رد شده چرا. بدون این، تنها راهش پرسیدن از پشتیبانی است.
    """
    rows = ctx.db.q(
        """SELECT o.*, p.name AS plan_name, p.gb, p.days
           FROM orders o LEFT JOIN plans p ON p.id = o.plan_id
           WHERE o.tenant_id=? AND o.user_id=?
           ORDER BY o.id DESC LIMIT 15""",
        (ctx.tid, user["id"]))

    if not rows:
        return _reply(ctx, chat_id, message_id,
                      "🧾 <b>سفارش‌های من</b>\n\n"
                      "هنوز سفارشی اینجا نیست.\n\n"
                      "هر خریدی که بکنید، با وضعیتش همین‌جا ثبت می‌شود.",
                      kb([[(f"🛒 {buy_word(ctx)}", "buy")], [("‹ منو", "menu")]]))

    label = {
        "pending": "⏳ در انتظار رسید",
        "awaiting": "⏳ در حال بررسی",
        "approved": "✅ تایید شده",
        "rejected": "❌ رد شده",
        "cancelled": "🚫 لغو شده",
        "expired": "⌛️ مهلتش تمام شد",
    }

    lines = ["🧾 <b>سفارش‌های من</b>", ""]
    for o in rows:
        st = label.get(o["status"], o["status"])
        when = core.fa_datetime(o.get("created_at"))
        name = o.get("plan_name") or "—"

        lines.append(f"{st} · {name}")

        # مبلغ نهایی در amount است، نه final_price/price که وجود ندارند
        price = o.get("amount") or 0
        if price:
            lines.append(f"<b>{core.toman(price)}</b> تومان · {when}")
        else:
            lines.append(f"رایگان · {when}")
        if o.get("coins_used"):
            lines.append(f"با {core.fa(o['coins_used'])} سکه")

        # دلیل رد — مهم‌ترین چیزی که کاربر می‌خواهد بداند
        if o["status"] == "rejected" and o.get("admin_note"):
            lines.append(f"<i>دلیل: {esc(o['admin_note'][:90])}</i>")

        lines.append(f"<i>کد پیگیری:</i> <code>#{o['id']}</code>")
        lines.append("")

    buttons = []
    pending = [o for o in rows if o["status"] in ("pending", "awaiting")]
    if pending:
        lines.append(f"<i>{core.fa(len(pending))} سفارش هنوز در جریان است.</i>")
    if any(o["status"] == "rejected" for o in rows):
        buttons.append([("🔄 خرید مجدد", "buy")])
    buttons.append([("‹ منو", "menu")])

    return _reply(ctx, chat_id, message_id, "\n".join(lines), kb(buttons))


def trial_core(ctx, u):
    """
    ساختِ تستِ رایگان — **تنها** هسته‌اش. ربات (`give_trial`) و مینی‌اپ
    (`/api/mini/trial`) هر دو همین را صدا می‌زنند.

    برمی‌گرداند (ok, data): ok → data اشتراکِ ساخته‌شده (برای `deliver`)؛
    وگرنه data یکی از «store_closed»، «used»، «no_plan»، یا متنِ خطای ساخت.
    اطلاعاتِ پیش از تست و کانال را صداکننده پیش از این سنجیده.

    تا ۱.۱۱۷ مینی‌اپ اصلاً مسیرِ تست نداشت: پلنِ تست میانِ پلن‌ها بود و
    «خرید»ش خطای «از خودِ ربات بگیرید» می‌داد.
    """
    if store_gate(ctx):
        return False, "store_closed"
    # An admin may take the trial again, to test the flow (see `trial_offer`).
    again = bool(u.get("trial_used")) and ctx.is_admin(u["tg_id"])
    if u.get("trial_used") and not again:
        return False, "used"
    plan = ctx.db.trial_plan()
    if not plan:
        return False, "no_plan"

    # حقِ تست را *قبل* از ساخت می‌گیریم.
    #
    # بررسی بالا فقط یک خواندن است؛ بین آن و نوشتن پرچم، ساخت کانفیگ
    # چند ثانیه طول می‌کشد. دو بار زدنِ دکمه یعنی هر دو نخ پرچم را
    # صفر می‌دیدند و هر دو کانفیگ رایگان می‌ساختند.
    if not again and not ctx.db.claim_trial(u["id"]):
        return False, "used"

    order = ctx.db.create_order(u["id"], plan["id"], 0, 0, kind="new")

    # سفارش این‌جا approved *نمی‌شود* — همان قاعده‌ی مسیر کارت و کیف
    # پول: تا کانفیگ ساخته نشود، فروشی اتفاق نیفتاده. قبلاً اول
    # approved می‌شد و اگر ساخت شکست می‌خورد، سفارشِ approved می‌ماند:
    # کاربری که هیچ‌وقت چیزی نگرفت، در قیف «خرید موفق» شمرده می‌شد.
    ok, result = provision(ctx, order["id"])
    if not ok:
        # پیامِ صداکننده می‌گوید تست محفوظ است — پس واقعاً پسش می‌دهیم
        if not again:
            ctx.db.release_trial(u["id"])
        ctx.db.close_order(order["id"], "rejected", "ساخت اشتراک تست ناموفق")
        return False, str(result)

    ctx.db.close_order(order["id"], "approved")
    # شروعِ پیگیری (۰/۸/۱۶/۲۴ ساعت) — `run.send_trial_journey`
    ctx.db.exec("UPDATE users SET trial_at=CURRENT_TIMESTAMP, trial_step=0 "
                "WHERE tenant_id=? AND id=?", (ctx.tid, u["id"]))
    # تحویلِ تست «خریدِ پولی» نیست — `_trial_converted` از همین می‌فهمد
    result = dict(result, is_trial=True)
    op = dict(core.TRIAL_OPERATORS).get(u.get("operator") or "", "")
    osn = dict(core.TRIAL_OS).get(u.get("device_os") or "", "")
    info = " · ".join(x for x in (esc(u.get("real_name") or ""), op, osn) if x)
    ctx.notify_group(
        f"🎉 اشتراک تست\n👤 {esc(u.get('first_name'))} (<code>{u['tg_id']}</code>)"
        + (f"\n📝 {info}" if info else ""),
        topic="users"
    )
    return True, result


TRIAL_USED_TEXT = ("اشتراک تست رایگان را قبلاً گرفته‌اید. هر حساب فقط یک‌بار "
                   "می‌تواند.\n\nبرای ادامه، یکی از پلن‌ها را انتخاب کنید.")


def _trial_ask(ctx, user, chat_id, message_id, step):
    """یک قدم از اطلاعاتِ پیش از تست — دکمه برای اپراتور و سیستم‌عامل، متن برای نام."""
    if step == "operator":
        rows = [[(lbl, f"tinfo:op:{k}") for k, lbl in core.TRIAL_OPERATORS[:2]],
                [(lbl, f"tinfo:op:{k}") for k, lbl in core.TRIAL_OPERATORS[2:]],
                [("‹ بازگشت", "menu")]]
        return _reply(ctx, chat_id, message_id,
                      "🎁 <b>تستِ رایگان</b>: سه سؤالِ کوتاه\n\n"
                      "۱ از ۳ · اینترنتت کدام اپراتور است؟", kb(rows))
    if step == "device_os":
        rows = [[(lbl, f"tinfo:os:{k}") for k, lbl in core.TRIAL_OS[:2]],
                [(lbl, f"tinfo:os:{k}") for k, lbl in core.TRIAL_OS[2:]],
                [("‹ بازگشت", "menu")]]
        return _reply(ctx, chat_id, message_id,
                      "🎁 <b>تستِ رایگان</b>\n\n۲ از ۳ · با چه دستگاهی وصل می‌شوی؟", kb(rows))
    ctx.db.set_state(user["tg_id"], "await_trial_name", {})
    return _reply(ctx, chat_id, message_id,
                  "🎁 <b>تستِ رایگان</b>\n\n۳ از ۳ · اسمت را بنویس تا با اسم صدایت کنیم 🌷",
                  back_kb())


def trial_info_save(ctx, user, field, value):
    """ذخیره‌ی یک پاسخ — فقط کلیدهای فهرستِ `core`. برمی‌گرداند: ذخیره شد؟"""
    allowed = {"operator": dict(core.TRIAL_OPERATORS), "device_os": dict(core.TRIAL_OS)}
    if field in allowed:
        if value not in allowed[field]:
            return False
    elif field == "real_name":
        value = core.clean_real_name(value)
        if not value:
            return False
    else:
        return False
    # سه جمله‌ی صریح، نه نامِ ستون در f-string: دروازه‌ی «محدود به مستاجر»
    # شرطِ tenant_id را از متنِ خودِ SQL می‌خواند
    sql = {
        "operator": "UPDATE users SET operator=? WHERE tenant_id=? AND tg_id=?",
        "device_os": "UPDATE users SET device_os=? WHERE tenant_id=? AND tg_id=?",
        "real_name": "UPDATE users SET real_name=? WHERE tenant_id=? AND tg_id=?",
    }[field]
    ctx.db.exec(sql, (value, ctx.tid, user["tg_id"]))
    return True


def give_trial(ctx, user, chat_id, message_id):
    """پوسته‌ی تلگرامیِ `trial_core`: اطلاعات، کانال، بعد ساخت و تحویل."""
    closed = store_gate(ctx)
    if closed:
        return _reply(ctx, chat_id, message_id, closed, back_kb())
    u = ctx.db.get_user(user["tg_id"])
    if u.get("trial_used") and not ctx.is_admin(u["tg_id"]):
        return _reply(ctx, chat_id, message_id, TRIAL_USED_TEXT,
                      kb([[("🛒 دیدن پلن‌ها", "buy")], [("‹ بازگشت", "menu")]]))
    if not ctx.db.trial_plan():
        return _reply(ctx, chat_id, message_id,
                      "اشتراک تست فعلاً فعال نیست.", back_kb())

    # ترتیبِ مالک: اطلاعات ← کانال ← لینک
    missing = core.trial_info_missing(u, ctx.s)
    if missing:
        return _trial_ask(ctx, u, chat_id, message_id, missing[0])
    if require_membership(ctx, chat_id, message_id, u,
                          force=trial_needs_channel(ctx), again="trial"):
        return

    ok, result = trial_core(ctx, u)
    if not ok:
        if result == "used":
            return _reply(ctx, chat_id, message_id, TRIAL_USED_TEXT,
                          kb([[("🛒 دیدن پلن‌ها", "buy")], [("‹ بازگشت", "menu")]]))
        if result == "store_closed":
            return _reply(ctx, chat_id, message_id, core.STORE_CLOSED, back_kb())
        if result == "no_plan":
            return _reply(ctx, chat_id, message_id, "اشتراک تست فعلاً فعال نیست.", back_kb())
        return _reply(ctx, chat_id, message_id,
                      "ساخت اشتراک تست به مشکل خورد.\n\n"
                      f"<i>{esc(result)}</i>\n\n"
                      "چند دقیقه دیگر دوباره امتحان کنید. "
                      "تست رایگانتان هنوز محفوظ است.", back_kb())

    deliver(ctx, u, result)
    send_trial_welcome(ctx, u)


def _journey_name(u):
    return (u or {}).get("real_name") or (u or {}).get("first_name") or ""


def send_trial_welcome(ctx, u):
    """
    پیامِ «بلافاصله بعد از تست» (قدمِ ۰). ربات و مینی‌اپ هر دو بعد از
    `deliver` صدایش می‌زنند. شکستش تحویل را نمی‌شکند.
    """
    if not ctx.s.get("trial_journey", True):
        return
    try:
        ctx.bot.send(u["tg_id"], core.trial_msg(ctx.s, "trial_msg_0", _journey_name(u),
                                                ctx.brand(), esc=esc))
    except Exception as e:
        log.warning("پیامِ آغازِ تست نرفت (کاربر %s): %s", u.get("id"), e)


def feedback_poll_kb(kind, ref):
    """چهار دکمه‌ی کیفیت برای نظرسنجیِ بعد از خرید/تمدید — `fb:<نوع>:<سفارش>:<پاسخ>`."""
    o = core.TRIAL_POLL_8
    return kb([[(o[0][1], f"fb:{kind}:{ref}:{o[0][0]}"), (o[1][1], f"fb:{kind}:{ref}:{o[1][0]}")],
               [(o[2][1], f"fb:{kind}:{ref}:{o[2][0]}"), (o[3][1], f"fb:{kind}:{ref}:{o[3][0]}")]])


def order_feedback(ctx, user, chat_id, message_id, kind, ref, answer):
    """پاسخِ نظرسنجیِ بعد از خرید/تمدید. سفارش باید مالِ همین مشتری باشد."""
    if kind not in core.FEEDBACK_KINDS or answer not in dict(core.TRIAL_POLL_8):
        return None
    if not str(ref).isdigit() or not ctx.db.q(
            "SELECT 1 FROM orders WHERE tenant_id=? AND id=? AND user_id=?",
            (ctx.tid, int(ref), user["id"]), one=True):
        return None
    ctx.db.feedback_set(user["id"], kind, answer, str(ref))
    if answer == "bad":
        ctx.db.set_state(user["tg_id"], "await_trial_problem", {"kind": kind, "ref": str(ref)})
        return _reply(ctx, chat_id, message_id,
                      core.trial_msg(ctx.s, "trial_msg_8_bad", _journey_name(user),
                                     ctx.brand(), esc=esc), None)
    return _reply(ctx, chat_id, message_id,
                  f"ممنون از نظرت 🌷 «{esc(dict(core.TRIAL_POLL_8)[answer])}» ثبت شد.", None)


def trial_poll_kb(question):
    opts = core.TRIAL_POLL_8 if question == "8" else core.TRIAL_POLL_16
    return kb([[(opts[0][1], f"tfb:{question}:{opts[0][0]}"),
                (opts[1][1], f"tfb:{question}:{opts[1][0]}")],
               [(opts[2][1], f"tfb:{question}:{opts[2][0]}"),
                (opts[3][1], f"tfb:{question}:{opts[3][0]}")]])


def trial_feedback(ctx, user, chat_id, message_id, question, answer):
    """پاسخِ دکمه‌های پیگیری. «مشکل داشتم» توضیح می‌خواهد و به صندوق می‌رود."""
    opts = dict(core.TRIAL_POLL_8 if question == "8" else core.TRIAL_POLL_16)
    if question not in ("8", "16") or answer not in opts:
        return None
    ctx.db.trial_feedback_set(user["id"], question, answer)
    if question == "8" and answer == "bad":
        ctx.db.set_state(user["tg_id"], "await_trial_problem", {"kind": "trial8", "ref": ""})
        return _reply(ctx, chat_id, message_id,
                      core.trial_msg(ctx.s, "trial_msg_8_bad", _journey_name(user),
                                     ctx.brand(), esc=esc), None)
    return _reply(ctx, chat_id, message_id,
                  f"ممنون از نظرت 🌷 «{esc(opts[answer])}» ثبت شد.", None)


FEEDBACK_WHERE = {"trial8": "در تست", "buy": "بعد از خرید", "renew": "بعد از تمدید"}


def handle_trial_problem(ctx, msg, user, sdata=None):
    """
    توضیحِ «مشکل داشتم» — از هر نظرسنجی (تست، بعد از خرید، بعد از تمدید) →
    همان ردیفِ نظر، صندوقِ پیام‌ها (مثلِ پیامِ پشتیبانی)، و گروهِ مدیریت.
    """
    text = (msg.get("text") or "").strip()
    chat_id = msg["chat"]["id"]
    if not text:
        return ctx.bot.send(chat_id, "لطفاً مشکل را با متن بنویس 🙏")
    sd = sdata if isinstance(sdata, dict) else {}
    kind = sd.get("kind") if sd.get("kind") in FEEDBACK_WHERE else "trial8"
    ref = str(sd.get("ref") or "")
    where = FEEDBACK_WHERE[kind]
    ctx.db.clear_state(user["tg_id"])
    ctx.db.feedback_set(user["id"], kind, "bad", ref, text[:1000])
    try:
        ctx.db.chat_add(user["id"], "user", f"🔴 مشکل {where}:\n{text[:1000]}",
                        order_id=int(ref) if ref.isdigit() else None)
    except Exception:
        log.warning("مشکلِ %s در صندوق ثبت نشد (کاربر %s)", kind, user.get("id"), exc_info=True)
    ctx.notify_group(f"🔴 مشکل {where}\n👤 {esc(_journey_name(user))} "
                     f"(<code>{user['tg_id']}</code>)"
                     + (f" · سفارش <code>#{ref}</code>" if ref else "")
                     + f"\n\n{esc(text[:600])}", topic="support")
    return ctx.bot.send(chat_id, "ممنون که گفتی 🤝 پشتیبانی بررسی می‌کند و همین‌جا جوابت را می‌دهد.",
                        keyboard=back_kb())


# ═══════════════════════════════════════════════════════════
#  کمکی
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
#  پنل مدیریت داخل ربات — فقط برای ادمین‌ها
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
#  دریافت شماره تلفن — اختیاری
#  اجباری نیست: کاربری که نمی‌خواهد شماره بدهد نباید از خرید
#  محروم شود. فقط یک‌بار پرسیده می‌شود.
# ═══════════════════════════════════════════════════════════

SKIP_PHONE = "فعلاً نه"


def ask_phone(ctx, user, chat_id):
    """اگر شماره نداریم و قبلاً نپرسیده‌ایم، یک‌بار می‌پرسیم."""
    if user.get("phone"):
        return False
    if not ctx.s.get("ask_phone", True):
        return False

    # اگر قبلاً پرسیده‌ایم، دوباره مزاحم نمی‌شویم
    if user.get("phone_asked"):
        return False

    ctx.db.exec("UPDATE users SET phone_asked=1 WHERE tenant_id=? AND tg_id=?",
                (ctx.tid, user["tg_id"]))
    ctx.db.set_state(user["tg_id"], "await_phone", {})
    txt = ctx.s.get("phone_prompt") or (
        "📱 <b>شماره تماس</b>\n\n"
        "اگر شماره‌تان را ثبت کنید، وقتی مشکلی پیش بیاید سریع‌تر پیدایتان "
        "می‌کنیم و اشتراکتان قابل بازیابی می‌ماند.\n\n"
        "<i>اختیاری است و بدون آن هم می‌توانید خرید کنید.</i>"
    )
    ctx.bot.send(chat_id, txt,
                 keyboard=contact_kb("📱 ارسال شماره من", SKIP_PHONE))
    return True


def handle_phone(ctx, msg, user):
    """پردازش شماره — از دکمه‌ی تلگرام یا تایپ دستی."""
    chat_id = msg["chat"]["id"]
    contact = msg.get("contact")
    text = (msg.get("text") or "").strip()

    # کاربر رد کرد
    if text == SKIP_PHONE or text in ("رد", "بعدا", "بعداً"):
        ctx.db.clear_state(user["tg_id"])
        ctx.bot.send(chat_id, "باشه، بدون شماره ادامه می‌دهیم 👍",
                     keyboard=remove_kb())
        return cmd_start(ctx, msg)

    phone = None
    if contact:
        # فقط شماره‌ی خود کاربر را می‌پذیریم، نه مخاطب دیگری
        if contact.get("user_id") and int(contact["user_id"]) != int(user["tg_id"]):
            ctx.bot.send(chat_id,
                         "این شماره متعلق به شما نیست. لطفاً شماره‌ی خودتان را بفرستید.",
                         keyboard=contact_kb("📱 ارسال شماره من", SKIP_PHONE))
            return
        phone = contact.get("phone_number")
    elif text:
        digits = "".join(ch for ch in text if ch.isdigit() or ch == "+")
        if len(digits) >= 10:
            phone = digits

    if not phone:
        ctx.bot.send(chat_id,
                     "این شماره درست به نظر نمی‌رسد.\n\n"
                     "ساده‌ترین راه دکمه‌ی پایین است. یا شماره را به شکل "
                     "<code>09121234567</code> بنویسید.",
                     keyboard=contact_kb("📱 ارسال شماره من", SKIP_PHONE))
        return

    phone = core.normalize_phone(phone)
    ctx.db.exec("UPDATE users SET phone=? WHERE tenant_id=? AND tg_id=?",
                (phone, ctx.tid, user["tg_id"]))
    ctx.db.clear_state(user["tg_id"])

    ctx.bot.send(chat_id,
                 f"✅ شماره‌ی <code>{esc(core.pretty_phone(phone))}</code> ثبت شد.",
                 keyboard=remove_kb())
    user = ctx.db.get_user(user["tg_id"])
    return cmd_start(ctx, msg)


def show_admin(ctx, user, chat_id, message_id=None):
    """صفحه‌ی اصلی پنل مدیریت با آمار زنده."""
    if not ctx.is_admin(user["tg_id"]):
        return _reply(ctx, chat_id, message_id, "دسترسی ندارید.", back_kb())

    st = ctx.db.stats()
    pending = st.get("pending", 0)

    txt = (
        f"⚙️ <b>پنل مدیریت</b> · {esc(ctx.brand())}\n\n"
        f"👥 کاربران   <b>{core.fa(st.get('users', 0))}</b>\n"
        f"📦 اشتراک فعال   <b>{core.fa(st.get('active_subs', 0))}</b>\n"
        f"💳 رسید در انتظار   <b>{core.fa(pending)}</b>\n"
        f"🎫 تیکت باز   <b>{core.fa(st.get('open_tickets', 0))}</b>\n\n"
        f"💰 فروش کل   <b>{core.toman(st.get('revenue_total', 0))}</b> تومان"
    )
    if pending:
        txt += f"\n\n⏳ <b>{core.fa(pending)}</b> رسید منتظر بررسی شماست."

    rows = []
    rows.append([(f"💳 رسیدها ({pending})" if pending else "💳 رسیدها", "adm:orders")])
    rows += [
        [("👥 کاربران", "adm:users"), ("📦 پلن‌ها", "adm:plans")],
        [("📊 آمار", "adm:stats"), ("📢 پیام همگانی", "adm:bc")],
        [("‹ بازگشت", "menu")],
    ]
    return _reply(ctx, chat_id, message_id, txt, kb(rows))


def admin_orders(ctx, user, chat_id, message_id=None):
    """صف رسیدهای در انتظار."""
    if not ctx.is_admin(user["tg_id"]):
        return

    orders = ctx.db.pending_orders()
    if not orders:
        return _reply(ctx, chat_id, message_id,
                      "✅ صف رسیدها خالی است. همه بررسی شده‌اند.",
                      back_kb("admin"))

    rows = []
    for o in orders[:10]:
        nm = (o.get("first_name") or "بدون نام")[:15]
        rows.append([(f"#{o['id']} · {nm} · {core.toman(o['amount'])}", f"adm:o:{o['id']}")])
    rows.append([("‹ بازگشت", "admin")])

    return _reply(ctx, chat_id, message_id,
                  f"💳 <b>رسیدهای در انتظار</b> · {core.fa(len(orders))}\n\n"
                  "روی هرکدام بزنید تا جزئیات و رسیدش را ببینید.", kb(rows))


def admin_order_detail(ctx, user, chat_id, message_id, order_id):
    """جزئیات سفارش با دکمه تایید/رد."""
    if not ctx.is_admin(user["tg_id"]):
        return

    o = ctx.db.get_order(order_id)
    if not o:
        return _reply(ctx, chat_id, message_id, "سفارش پیدا نشد.", back_kb("adm:orders"))

    u = ctx.db.get_user_by_id(o["user_id"]) or {}
    p = ctx.db.get_plan(o["plan_id"]) if o.get("plan_id") else None

    txt = (
        f"🧾 <b>سفارش #{o['id']}</b>\n\n"
        f"{esc(u.get('first_name') or 'بدون نام')}"
        + (f" · @{esc(u['username'])}" if u.get("username") else "") + "\n"
        f"<code>{u.get('tg_id', '?')}</code>\n\n"
        f"{esc(p['name']) if p else 'نامشخص'}\n"
        f"<b>{core.toman(o['amount'])}</b> تومان\n"
    )
    if o.get("coins_used"):
        txt += (f"با {core.fa(o['coins_used'])} سکه · "
                f"{core.fa(o.get('discount_pct', 0))}٪ تخفیف\n")
    txt += f"{core.fa_datetime(o.get('created_at'))}"

    if o.get("receipt_text"):
        txt += f"\n\n📝 <i>{esc(str(o['receipt_text'])[:180])}</i>"

    rows = []
    if o["status"] in ("awaiting", "review"):
        rows = [
            [("✅ تایید و ساخت کانفیگ", f"ap:{o['id']}")],
            [("❌ رد", f"rj:{o['id']}"), ("💬 سوال از مشتری", f"adm:ask:{o['id']}")],
        ]
    else:
        txt += f"\n\nوضعیت: <b>{o['status']}</b>"
    rows.append([("‹ بازگشت", "adm:orders")])

    if o.get("receipt_type") == "photo" and o.get("receipt_file"):
        try:
            ctx.bot.send_photo(chat_id, o["receipt_file"], caption=txt, keyboard=kb(rows))
            return
        except TelegramError as _exc:
            log.debug("admin_order_detail step: %s", _exc)

    return _reply(ctx, chat_id, message_id, txt, kb(rows))


def admin_users(ctx, user, chat_id, message_id=None):
    """آخرین کاربران."""
    if not ctx.is_admin(user["tg_id"]):
        return

    rows_db = ctx.db.q(
        "SELECT * FROM users WHERE tenant_id=? ORDER BY created_at DESC LIMIT 10",
        (ctx.tid,))
    if not rows_db:
        return _reply(ctx, chat_id, message_id,
                      "هنوز کاربری ثبت نشده است.", back_kb("admin"))

    lines = ["👥 <b>آخرین کاربران</b>", ""]
    rows = []
    for u in rows_db:
        nm = esc((u.get("first_name") or "بدون نام")[:16])
        un = f" @{esc(u['username'])}" if u.get("username") else ""
        lines.append(f"{nm}{un}: {core.fa(u.get('coins', 0))} سکه · "
                     f"{core.toman(u.get('balance', 0))} تومان")
        rows.append([(f"{nm} · {u['tg_id']}", f"adm:u:{u['tg_id']}")])

    rows.append([("🔎 جستجو", "adm:find")])
    rows.append([("‹ بازگشت", "admin")])
    return _reply(ctx, chat_id, message_id, "\n".join(lines), kb(rows))


def admin_user_detail(ctx, user, chat_id, message_id, target_id):
    """جزئیات و مدیریت یک کاربر."""
    if not ctx.is_admin(user["tg_id"]):
        return

    u = ctx.db.get_user(int(target_id))
    if not u:
        return _reply(ctx, chat_id, message_id, "کاربر پیدا نشد.", back_kb("adm:users"))

    subs = ctx.db.user_subs(u["id"], active_only=False)
    active = [s for s in subs if s.get("is_active")]

    txt = (
        f"👤 <b>{esc(u.get('first_name') or 'بدون نام')}</b>"
        + (f" · @{esc(u['username'])}" if u.get("username") else "") + "\n"
        f"<code>{u['tg_id']}</code>\n\n"
        f"🪙 سکه   <b>{core.fa(u.get('coins', 0))}</b>\n"
        f"👛 کیف پول   <b>{core.toman(u.get('balance', 0))}</b> تومان\n"
        f"📦 اشتراک فعال   <b>{core.fa(len(active))}</b>\n"
        f"📅 عضویت   {core.fa_date(u.get('created_at'))}\n\n"
        f"🔗 کد دعوت   <code>{u.get('ref_code', '—')}</code>"
    )
    if u.get("is_blocked"):
        txt += "\n\n🚫 <b>این کاربر مسدود است</b>"

    rows = [
        [("💎 سکه", f"adm:coin:{u['tg_id']}"), ("👛 کیف پول", f"adm:bal:{u['tg_id']}")],
        [("💬 ارسال پیام", f"adm:msg:{u['tg_id']}")],
        [("✅ رفع مسدودی" if u.get("is_blocked") else "🚫 مسدودسازی", f"adm:blk:{u['tg_id']}")],
        [("‹ بازگشت", "adm:users")],
    ]
    return _reply(ctx, chat_id, message_id, txt, kb(rows))


def admin_stats(ctx, user, chat_id, message_id=None):
    """آمار کامل."""
    if not ctx.is_admin(user["tg_id"]):
        return

    st = ctx.db.stats()
    txt = (
        f"📊 <b>آمار</b>\n\n"
        f"👥 کاربران   <b>{core.fa(st.get('users', 0))}</b>\n"
        f"📦 اشتراک فعال   <b>{core.fa(st.get('active_subs', 0))}</b>\n"
        f"💳 رسید در انتظار   <b>{core.fa(st.get('pending', 0))}</b>\n"
        f"🎫 تیکت باز   <b>{core.fa(st.get('open_tickets', 0))}</b>\n\n"
        f"💰 فروش کل   <b>{core.toman(st.get('revenue_total', 0))}</b> تومان"
    )
    return _reply(ctx, chat_id, message_id, txt,
                  kb([[("🔄 تازه‌سازی", "adm:stats")], [("‹ بازگشت", "admin")]]))


def admin_plans(ctx, user, chat_id, message_id=None):
    """لیست پلن‌ها."""
    if not ctx.is_admin(user["tg_id"]):
        return

    plans = ctx.db.plans(active_only=False, include_trial=True)
    if not plans:
        return _reply(ctx, chat_id, message_id,
                      "هنوز پلنی ساخته نشده.\n\n"
                      "<i>ساخت و ویرایش پلن‌ها از پنل وب انجام می‌شود.</i>",
                      back_kb("admin"))

    lines = ["📦 <b>پلن‌ها</b>", ""]
    for p in plans:
        mark = "🟢" if p.get("is_active") else "⚪️"
        trial = " 🎁" if p.get("is_trial") else ""
        lines.append(f"{mark} {esc(p['name'])}{trial} · {core.toman(p['price'])} · "
                     f"{core.fmt_gb(p.get('gb'))} · {core.fmt_days(p.get('days'))}")

    lines.append("\n<i>ویرایش پلن‌ها از پنل وب انجام می‌شود.</i>")
    return _reply(ctx, chat_id, message_id, "\n".join(lines), back_kb("admin"))


def admin_ask_input(ctx, user, chat_id, message_id, kind, target=None):
    """شروع ورودی چندمرحله‌ای ادمین."""
    if not ctx.is_admin(user["tg_id"]):
        return

    prompts = {
        "bc": "📢 <b>پیام همگانی</b>\n\n"
              "متن را بفرستید تا برای <b>همه‌ی کاربران</b> ارسال شود.\n\n"
              "<i>قبل از ارسال دوباره بخوانیدش. برگشتی ندارد.</i>",
        "coin": "🪙 <b>تغییر سکه</b>\n\n"
                "چند سکه اضافه شود؟\n\n"
                "<i>برای کسر، عدد را با منها بنویسید، مثلاً</i> <code>-10</code>",
        "bal": "👛 <b>تغییر موجودی</b>\n\n"
               "چه مبلغی (تومان) اضافه شود؟\n\n"
               "<i>برای کسر، عدد را با منها بنویسید، مثلاً</i> <code>-50000</code>",
        "msg": "💬 <b>پیام به کاربر</b>\n\n"
               "متن پیام را بفرستید تا مستقیم برایش ارسال شود.",
        "ask": "💬 سوالتان از این مشتری را بفرستید.",
        "find": "🔎 نام، یوزرنیم یا آیدی عددی کاربر را بفرستید.",
        "tkreply": "✍️ <b>پاسخ به تیکت</b>\n\n"
                   "متن پاسخ را بفرستید تا مستقیم برای مشتری ارسال شود.\n\n"
                   "<blockquote>مشتری فقط همین متن را می‌بیند. نام شما و "
                   "گروه مدیریت به او نشان داده نمی‌شود.</blockquote>",
    }
    ctx.db.set_state(user["tg_id"], f"adm_{kind}", {"t": target})
    return _reply(ctx, chat_id, message_id,
                  prompts.get(kind, "مقدار را بفرستید:"),
                  kb([[("انصراف", "admin")]]))


def admin_input(ctx, user, chat_id, text, state, data):
    """پردازش ورودی ادمین."""
    if not ctx.is_admin(user["tg_id"]):
        return

    kind = state.replace("adm_", "")
    target = (data or {}).get("t")
    ctx.db.clear_state(user["tg_id"])
    txt = (text or "").strip()

    if kind == "bc":
        ids = [r["tg_id"] for r in ctx.db.q(
            "SELECT tg_id FROM users WHERE tenant_id=? AND is_blocked=0", (ctx.tid,))]

        if not ids:
            return _reply(ctx, chat_id, None, "کاربری برای ارسال نیست.",
                          back_kb("admin"))

        # پیام پیشرفت، چون ارسال به صدها نفر طول می‌کشد و بدون آن
        # کاربر فکر می‌کند چیزی کار نمی‌کند
        progress = ctx.bot.send(
            chat_id, f"📢 در حال ارسال به {core.fa(len(ids))} کاربر…")
        pid = (progress or {}).get("message_id") if isinstance(progress, dict) else None

        sent = failed = blocked = 0
        for i, uid in enumerate(ids, 1):
            try:
                ctx.bot.send(uid, txt)
                sent += 1
            except TelegramError as e:
                msg = str(e).lower()
                if "blocked" in msg or "deactivated" in msg or "chat not found" in msg:
                    blocked += 1
                    # They blocked the bot: `left_at`, not a ban. Setting
                    # `is_blocked` here made the bot ignore them for good,
                    # even after they unblocked it and pressed /start.
                    try:
                        ctx.db.exec(
                            "UPDATE users SET left_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND tg_id=?",
                            (ctx.tid, uid))
                    except Exception as e:
                        log.warning("marking user %s blocked failed: %s", uid, e)
                else:
                    failed += 1
            except Exception:
                failed += 1

            # تلگرام حدود ۳۰ پیام در ثانیه اجازه می‌دهد
            if i % 25 == 0:
                time.sleep(1.2)
                if pid:
                    try:
                        ctx.bot.edit(chat_id, pid,
                                     f"📢 ارسال… {core.fa(i)} از {core.fa(len(ids))}")
                    except Exception as _exc:
                        log.warning("admin action side effect: %s", _exc)

        report = [
            "📢 <b>پیام همگانی ارسال شد</b>", "",
            f"رسید به   <b>{core.fa(sent)}</b> نفر",
        ]
        if blocked:
            report.append(f"ربات را بلاک کرده‌اند   {core.fa(blocked)}")
            report.append("<i>این‌ها خودکار غیرفعال شدند تا دفعه‌ی بعد "
                          "وقت تلف نشود.</i>")
        if failed:
            report.append(f"ناموفق   {core.fa(failed)}")

        if pid:
            try:
                ctx.bot.edit(chat_id, pid, "\n".join(report),
                             keyboard=back_kb("admin"))
                return
            except Exception as _exc:
                log.warning("admin action side effect: %s", _exc)
        return _reply(ctx, chat_id, None, "\n".join(report), back_kb("admin"))

    if kind == "find":
        like = f"%{txt}%"
        found = ctx.db.q(
            "SELECT * FROM users WHERE tenant_id=? AND (first_name LIKE ? OR username LIKE ? "
            "OR CAST(tg_id AS TEXT) LIKE ?) LIMIT 8", (ctx.tid, like, like, like))
        if not found:
            return _reply(ctx, chat_id, None,
                          "کسی با این مشخصات یافت نشد.\n\n"
                          "<i>با آیدی عددی مطمئن‌تر است.</i>",
                          back_kb("adm:users"))
        rows = [[(f"{(u.get('first_name') or '?')[:18]} · {u['tg_id']}", f"adm:u:{u['tg_id']}")]
                for u in found]
        rows.append([("‹ بازگشت", "adm:users")])
        return _reply(ctx, chat_id, None,
                      f"🔎 <b>{core.fa(len(found))}</b> نتیجه", kb(rows))

    if kind in ("coin", "bal") and target:
        try:
            amt = int(txt.replace(",", "").replace("،", ""))
        except ValueError:
            return _reply(ctx, chat_id, None,
                          "عدد معتبر نبود. فقط رقم بنویسید، "
                          "مثلاً <code>50</code> یا <code>-10</code>",
                          back_kb("admin"))

        u = ctx.db.get_user(int(target))
        if not u:
            return _reply(ctx, chat_id, None,
                          "این کاربر پیدا نشد.", back_kb("adm:users"))

        if kind == "coin":
            ctx.db.add_coins(u["id"], amt, "admin", "تنظیم دستی ادمین")
            fresh = ctx.db.get_user(u["tg_id"])
            note = (f"🪙 {core.fa(abs(amt))} سکه "
                    f"{'اضافه' if amt > 0 else 'کسر'} شد.")
            user_msg = (
                f"🪙 <b>{core.fa(abs(amt))} سکه</b> به حسابتان "
                f"{'اضافه شد' if amt > 0 else 'کم شد'}.\n\n"
                f"موجودی فعلی: <b>{core.fa(fresh.get('coins', 0))}</b> سکه")
        else:
            ctx.db.add_balance(u["id"], amt, "admin", "تنظیم دستی ادمین")
            fresh = ctx.db.get_user(u["tg_id"])
            note = (f"👛 {core.toman(abs(amt))} تومان "
                    f"{'اضافه' if amt > 0 else 'کسر'} شد.")
            user_msg = (
                f"👛 کیف پولتان <b>{core.toman(abs(amt))}</b> تومان "
                f"{'شارژ شد' if amt > 0 else 'کم شد'}.\n\n"
                f"موجودی فعلی: <b>{core.toman(fresh.get('balance', 0))}</b> تومان")

        try:
            ctx.bot.send(u["tg_id"], user_msg)
        except TelegramError as _exc:
            log.warning("admin action side effect: %s", _exc)
        return _reply(ctx, chat_id, None, f"✅ {note}",
                      kb([[("‹ بازگشت", f"adm:u:{target}")]]))

    if kind == "msg" and target:
        u = ctx.db.get_user(int(target))
        if u:
            try:
                support_reply(ctx, u, txt)
                return _reply(ctx, chat_id, None, "✅ پیام رسید.",
                              kb([[("‹ بازگشت", f"adm:u:{target}")]]))
            except TelegramError:
                return _reply(ctx, chat_id, None,
                              "❌ نرسید. احتمالاً کاربر ربات را بلاک کرده.",
                              back_kb("adm:users"))

    if kind == "tkreply" and target:
        t = ctx.db.q("SELECT * FROM tickets WHERE tenant_id=? AND id=?",
                     (ctx.tid, int(target)), one=True)
        if not t:
            return _reply(ctx, chat_id, None, "این تیکت پیدا نشد.", back_kb())

        u = ctx.db.get_user_by_id(t["user_id"])
        if not u:
            return _reply(ctx, chat_id, None, "کاربر این تیکت پیدا نشد.", back_kb())

        try:
            support_reply(ctx, u, txt, ticket_id=t["id"])
        except TelegramError:
            return _reply(ctx, chat_id, None,
                          "❌ نرسید. احتمالاً کاربر ربات را بلاک کرده.",
                          back_kb())

        # تیکت بسته می‌شود تا در فهرست «باز» نماند و دو بار جواب نگیرد
        try:
            ctx.db.exec(
                "UPDATE tickets SET status='answered', answer=?, "
                "answered_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND id=?",
                (txt[:2000], ctx.tid, int(target)))
        except Exception as e:
            # پاسخ رفته، ولی تیکت «باز» می‌ماند و ممکن است دوباره جواب بگیرد
            log.warning("closing ticket %s after reply failed: %s", target, e)

        return _reply(ctx, chat_id, None,
                      f"✅ پاسخ تیکت <code>#{target}</code> برای مشتری رفت.",
                      kb([[("‹ منوی مدیریت", "admin")]]))

    if kind == "reject" and target:
        if not do_reject(ctx, int(target), user["tg_id"],
                         txt or "رسید تأیید نشد."):
            # رد حالا شرطی است: سفارشی که کانفیگ گرفته یا قبلاً رد
            # شده، رد نمی‌شود. گفتن «رد شد» در آن حالت دروغ است.
            return _reply(ctx, chat_id, None,
                          f"سفارش <code>#{target}</code> رد نشد: یا کانفیگش "
                          "ساخته شده، یا قبلاً رد شده بود.\n\n"
                          "وضعیتش را از فهرست سفارش‌ها ببینید.",
                          back_kb("adm:orders"))
        return _reply(ctx, chat_id, None,
                      f"❌ سفارش #{target} رد شد و دلیلش به مشتری رسید.",
                      back_kb("adm:orders"))

    if kind == "ask" and target:
        o = ctx.db.get_order(int(target))
        if o:
            u = ctx.db.get_user_by_id(o["user_id"])
            if u:
                try:
                    ctx.bot.send(u["tg_id"],
                                     f"💬 <b>درباره سفارش #{o['id']}</b>\n\n{esc(txt)}")
                    return _reply(ctx, chat_id, None, "✅ پیام رسید.",
                                  kb([[("‹ بازگشت", f"adm:o:{target}")]]))
                except TelegramError as _exc:
                    log.warning("admin action side effect: %s", _exc)
        return _reply(ctx, chat_id, None,
                      "❌ نرسید. احتمالاً کاربر ربات را بلاک کرده.",
                      back_kb("adm:orders"))

    return _reply(ctx, chat_id, None,
                  "این ورودی شناخته نشد. از منو دوباره شروع کنید.",
                  back_kb("admin"))


def _back_from_left(ctx, user):
    """
    Someone writing to the bot has unblocked it: clear `left_at`. And a ban
    with no `blocked_by` is from before 2.1.2, when a failed broadcast set
    the same flag as a ban; those were nearly all customers who had blocked
    the bot, and the bot ignored them for good once they came back. They are
    let back in, and it is on record. A ban set since then names who set it
    and stays.
    """
    if user.get("left_at") or (user.get("is_blocked") and not user.get("blocked_by")):
        ctx.db.exec("UPDATE users SET left_at=NULL, is_blocked=CASE WHEN blocked_by IS NULL "
                    "THEN 0 ELSE is_blocked END WHERE tenant_id=? AND id=?",
                    (ctx.tid, user["id"]))
        if user.get("is_blocked") and not user.get("blocked_by"):
            ctx.db.log("user_back", user["id"], {"why": "old flag from a broadcast"})
        return ctx.db.get_user(user["tg_id"]) or user
    return user


def admin_toggle_block(ctx, user, chat_id, message_id, target_id):
    """مسدود/رفع مسدودی کاربر."""
    if not ctx.is_admin(user["tg_id"]):
        return
    u = ctx.db.get_user(int(target_id))
    if not u:
        return
    new = 0 if u.get("is_blocked") else 1
    ctx.db.exec("UPDATE users SET is_blocked=?, blocked_by=? WHERE tenant_id=? AND tg_id=?",
                (new, "admin" if new else None, ctx.tid, int(target_id)))
    return admin_user_detail(ctx, user, chat_id, message_id, target_id)


def _reply(ctx, chat_id, message_id, text, keyboard):
    """اگر message_id باشد ویرایش می‌کند، وگرنه پیام جدید می‌فرستد."""
    if message_id:
        try:
            return ctx.bot.edit(chat_id, message_id, text, keyboard)
        except TelegramError as _exc:
            log.debug("_reply step: %s", _exc)
    return ctx.bot.send(chat_id, text, keyboard=keyboard)


# ═══════════════════════════════════════════════════════════
#  مسیریاب — نقطه‌ی ورود همه‌ی آپدیت‌های تلگرام
# ═══════════════════════════════════════════════════════════

def dispatch(tenant, bot, update):
    """
    یک آپدیت تلگرام را به هندلر مناسب می‌رساند.

    این تنها نقطه‌ای است که run.py صدا می‌زند؛ بقیه‌ی توابع از این‌جا
    فراخوانی می‌شوند. خطاها این‌جا گرفته می‌شوند تا یک آپدیت خراب
    کل حلقه‌ی مستاجر را متوقف نکند.
    """
    ctx = Ctx(bot, tenant)

    # داکstring بالا این را وعده می‌داد ولی try واقعی وجود نداشت؛ هر
    # خطای یک آپدیت تا حلقه‌ی اصلی بالا می‌رفت.
    try:
        if "callback_query" in update:
            return _on_callback(ctx, update["callback_query"])
        if "message" in update:
            return _on_message(ctx, update["message"])
    except Exception as e:
        log.exception("خطای پردازش آپدیت %s", update.get("update_id"))
        try:
            ctx.notify_group(_error_alert(update, e), topic="alerts")
        except Exception as _exc:
            log.warning("error alert to admin group: %s", _exc)
    return None


def _error_alert(update, exc):
    """
    متن هشدار خطا برای گروه مدیریت.

    قبلاً فقط update_id و «جزئیات در لاگ سرور است» فرستاده می‌شد، که
    یعنی مدیر باید SSH بزند تا بفهمد کدام دکمه شکسته. حالا نوع خطا و
    دکمه‌ای که زده شده هم می‌آید — هیچ‌کدام حساس نیستند و معمولاً همان
    دو خط برای فهمیدن ماجرا کافی است.

    عمداً هیچ متن پیام کاربر این‌جا نمی‌آید؛ گروه مدیریت جای محتوای
    خصوصی مشتری نیست.
    """
    cb = (update.get("callback_query") or {})
    msg = update.get("message") or {}
    who = (cb.get("from") or msg.get("from") or {})

    lines = ["⚠️ <b>خطا در پردازش یک پیام</b>", ""]

    if cb.get("data"):
        lines.append(f"دکمه: <code>{esc(str(cb['data'])[:64])}</code>")
    elif msg.get("text", "").startswith("/"):
        lines.append(f"دستور: <code>{esc(msg['text'].split()[0][:32])}</code>")
    else:
        lines.append("رویداد: پیام معمولی")

    if who.get("id"):
        lines.append(f"کاربر: <code>{esc(str(who['id']))}</code>")

    lines += ["", f"<code>{esc(type(exc).__name__)}: "
                  f"{esc(str(exc)[:160])}</code>", ""]
    lines.append("<i>ردپای کامل در لاگ سرور: "
                 "<code>journalctl -u nexora-bot -n 50</code></i>")
    return "\n".join(lines)


def _get_or_create(ctx, tg_user, ref=None):
    u = ctx.db.get_user(tg_user["id"])
    if u:
        ctx.db.touch_user(tg_user["id"])
        return u

    # کاربر این‌جا ساخته می‌شود، پس همین‌جا هم باید تصمیم بگیریم
    # لینک از کدام نوع بوده. قبلاً پیشوند aff_ فقط در cmd_start
    # دیده می‌شد — که هیچ‌وقت به آن نمی‌رسید، چون تا آن لحظه کاربر
    # ساخته شده بود و شرط «کاربر جدید» رد می‌شد. نتیجه: هیچ لینک
    # همکاری هرگز به همکارش وصل نمی‌شد.
    referred_by = None
    affiliate = None
    arg = (ref or "").strip()
    if arg.startswith("aff_"):
        affiliate = DB.affiliate_by_code(ctx.tid, arg[4:])
        # همکار نمی‌تواند خودش را معرفی کند.
        #
        # مسیر «دعوت دوست» همین شرط را داشت و این یکی نداشت. همکاری
        # که هنوز با ربات کار نکرده، با بازکردن لینک خودش مشتریِ خودش
        # می‌شد و از هر خریدِ خودش پورسانت می‌گرفت — یعنی تخفیفی که
        # قرار نبود وجود داشته باشد.
        if affiliate and affiliate.get("tg_id") == tg_user["id"]:
            affiliate = None
    elif arg and arg not in DEEP_WORDS and not arg.startswith("renew_"):
        inviter = ctx.db.get_user_by_ref(arg)
        # کاربر نمی‌تواند خودش را دعوت کند
        if inviter and inviter["tg_id"] != tg_user["id"]:
            referred_by = inviter["id"]

    u = ctx.db.create_user(
        tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
        referred_by=referred_by,
    )
    if affiliate:
        ctx.db.exec("UPDATE users SET affiliate_id=? WHERE tenant_id=? AND id=?",
                    (affiliate["id"], ctx.tid, u["id"]))
        u["affiliate_id"] = affiliate["id"]

    # ── همه‌ی کارهای «کاربر تازه آمد» این‌جا انجام می‌شوند ──
    #
    # قبلاً در cmd_start بودند، و همان‌جا هم نمی‌رسیدند: تا وقتی
    # cmd_start صدا زده شود، کاربر توسط همین تابع ساخته شده بود و
    # شرط «کاربر جدید» رد می‌شد. اگر گیت شماره هم فعال باشد،
    # cmd_start اصلاً در اولین تماس اجرا نمی‌شود.
    #
    # نتیجه‌اش این بود: معرف هیچ خبری نمی‌گرفت، پاداش خوش‌آمد داده
    # نمی‌شد، و گروه مدیریت کاربر جدید را نمی‌دید.
    ctx.db.log("signup", u["id"], {"ref": bool(referred_by)})


    uname = tg_user.get("username")
    ctx.notify_group(
        f"👤 <b>کاربر جدید</b>\n"
        f"نام: {esc(tg_user.get('first_name'))}\n"
        f"آیدی: <code>{tg_user['id']}</code>\n"
        f"یوزرنیم: @{esc(uname) if uname else '—'}"
        + ("\n📎 با لینک دعوت" if referred_by else ""),
        topic="users"
    )

    # The welcome bonus and the word to the friend are Pro (`loyalty`). The
    # relation (`referred_by`) is recorded above either way: data, so a
    # renewed license finds it. A bonus that a locked license skips is logged.
    if referred_by:
        mod = loyalty_on()
        if mod:
            try:
                mod.on_invited_signup(ctx, u, referred_by, tg_user)
            except Exception:
                log.exception("invited signup of user %s", u["id"])
        elif pro("loyalty") is not None and core.coin_settings(
                ctx.s.get("coins")).get("welcome_bonus"):
            ctx.db.log("payout_skipped", u["id"], {"feature": "loyalty", "why": "welcome bonus"})

    return u


def _on_message(ctx, msg):
    frm = msg.get("from") or {}
    if frm.get("is_bot"):
        return None

    chat = msg.get("chat") or {}
    # پیام‌های گروه مدیریت جدا رسیدگی می‌شوند
    if chat.get("type") in ("group", "supergroup"):
        return None

    text = (msg.get("text") or "").strip()

    # /start با پارامتر کد معرف
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        ref = parts[1].strip() if len(parts) > 1 else None
        # وصل‌شدنِ صاحبِ فروشگاه — پیش از هر کارِ دیگر، چون این کد
        # کدِ معرف نیست و نباید به‌جای آن ثبت شود.
        if ref and ref.startswith("own_"):
            return claim_owner(ctx, msg, ref[4:])
        user = _back_from_left(ctx, _get_or_create(ctx, frm, ref))
        if user.get("is_blocked"):
            return None
        if ask_phone(ctx, user, msg["chat"]["id"]):
            return None
        return cmd_start(ctx, msg, ref)

    user = ctx.db.get_user(frm["id"])
    if not user:
        user = _get_or_create(ctx, frm)
    user = _back_from_left(ctx, user)
    if user.get("is_blocked"):
        return None

    # ادامه‌ی گفتگوی چندمرحله‌ای
    state = user.get("state")
    try:
        sdata = json.loads(user.get("state_data") or "{}")
    except (json.JSONDecodeError, TypeError):
        sdata = {}

    if state == "await_phone" or msg.get("contact"):
        return handle_phone(ctx, msg, user)

    # ورودی‌های پنل مدیریت
    if state and state.startswith("adm_"):
        return admin_input(ctx, user, chat.get("id"), text, state, sdata)

    if state == "await_receipt":
        return handle_receipt(ctx, msg, user, sdata)
    if state == "await_ticket":
        return handle_ticket(ctx, msg, user)
    if state == "await_discount":
        return handle_discount(ctx, msg, user, sdata)
    if state == "await_trial_problem":
        return handle_trial_problem(ctx, msg, user, sdata)
    if state == "await_trial_name":
        if not trial_info_save(ctx, user, "real_name", text):
            return ctx.bot.send(chat["id"], "این اسم خوانده نشد. فقط اسمت را بنویس "
                                            "(۲ تا ۴۰ حرف، بی لینک).", keyboard=back_kb())
        ctx.db.clear_state(user["tg_id"])
        return give_trial(ctx, ctx.db.get_user(user["tg_id"]), chat["id"], None)

    if text == "/menu":
        return ctx.bot.send(chat["id"], welcome_text(ctx, user),
                            keyboard=main_menu(ctx, user))

    # پیام آزاد → منو
    return ctx.bot.send(chat["id"], welcome_text(ctx, user),
                        keyboard=main_menu(ctx, user))


# نگاشت callback ساده → تابع
_SIMPLE = {
    "menu":    lambda ctx, u, c, m: _reply(ctx, c, m, welcome_text(ctx, u), main_menu(ctx, u)),
    "buy":     lambda ctx, u, c, m: show_plans(ctx, u, c, m),
    "mysubs":  lambda ctx, u, c, m: show_subs(ctx, u, c, m),
    "myorders": lambda ctx, u, c, m: my_orders(ctx, u, c, m),
    "affiliate": lambda ctx, u, c, m: affiliate_panel(ctx, u, c, m),
    "aff_list": lambda ctx, u, c, m: affiliate_list(ctx, u, c, m),
    "wallet":  lambda ctx, u, c, m: show_wallet(ctx, u, c, m),
    "topup":   lambda ctx, u, c, m: wallet_topup(ctx, u, c, m),
    "coins":   lambda ctx, u, c, m: show_coins(ctx, u, c, m),
    "ref":     lambda ctx, u, c, m: show_referral(ctx, u, c, m),
    "help":    lambda ctx, u, c, m: show_help(ctx, u, c, m),
    "support": lambda ctx, u, c, m: start_support(ctx, u, c, m),
    "trial":   lambda ctx, u, c, m: give_trial(ctx, u, c, m),
    "admin":   lambda ctx, u, c, m: show_admin(ctx, u, c, m),
}


def _on_callback(ctx, cq):
    frm = cq.get("from") or {}
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    mid = msg.get("message_id")

    user = _back_from_left(ctx, ctx.db.get_user(frm["id"]) or _get_or_create(ctx, frm))
    if user.get("is_blocked"):
        return ctx.bot.answer_cb(cq["id"], "دسترسی شما مسدود است", alert=True)

    try:
        ctx.bot.answer_cb(cq["id"])
    except TelegramError as _exc:
        log.debug("_on_callback step: %s", _exc)

    if data in _SIMPLE:
        return _SIMPLE[data](ctx, user, chat_id, mid)

    if ":" not in data:
        return None
    action, _, arg = data.partition(":")

    try:
        if action == "plan":
            return show_plan_detail(ctx, user, chat_id, mid, int(arg))
        if action == "sub":
            return show_sub(ctx, user, chat_id, mid, int(arg))
        if action == "pk":
            return show_plans(ctx, user, chat_id, mid, kind=arg)
        if action == "pt":
            k, _, i = arg.partition(":")
            return show_plans(ctx, user, chat_id, mid, kind=k,
                              tab=int(i) if i.isdigit() else 0)
        if action == "fb":
            kind, _, rest = arg.partition(":")
            ref, _, ans = rest.partition(":")
            return order_feedback(ctx, user, chat_id, mid, kind, ref, ans)
        if action == "tfb":
            q, _, a = arg.partition(":")
            return trial_feedback(ctx, user, chat_id, mid, q, a)
        if action == "tinfo":
            # tinfo:op:<کلید> یا tinfo:os:<کلید> — بعد قدمِ بعدیِ همان تست
            kind, _, val = arg.partition(":")
            field = {"op": "operator", "os": "device_os"}.get(kind)
            if field:
                trial_info_save(ctx, user, field, val)
            return give_trial(ctx, ctx.db.get_user(user["tg_id"]), chat_id, mid)
        if action == "chk":
            # chk:<plan>:<coins>[:<sub>] — بخش سوم فقط در تمدید می‌آید
            parts = arg.split(":")
            pid = int(parts[0])
            use_coins = len(parts) > 1 and parts[1] == "1"
            rid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
            return checkout(ctx, user, chat_id, mid, pid, use_coins,
                            renew_sub_id=rid)
        if action == "dsc":
            return ask_discount(ctx, user, chat_id, mid, int(arg))
        if action == "dscx":
            return drop_discount(ctx, user, chat_id, mid, int(arg))
        if action == "wpay":
            parts = arg.split(":")
            rid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            return wallet_pay(ctx, user, chat_id, mid, int(parts[0]),
                              renew_sub_id=rid)
        if action == "lic":
            return show_license(ctx, user, chat_id, mid, arg)
        if action in ("lwp", "lck"):
            # lwp/lck:<plan>:<license> — renewing a Pro license, wallet or card
            got = _license_renew_args(ctx, user, arg)
            if not got:
                return _reply(ctx, chat_id, mid, "این تمدید دیگر در دسترس نیست.",
                              back_kb("mysubs"))
            if action == "lwp":
                return wallet_pay(ctx, user, chat_id, mid, got[0], renew_license=got[1])
            return checkout(ctx, user, chat_id, mid, got[0], False, renew_license=got[1])
        if action == "topup":
            return wallet_topup_amount(ctx, user, chat_id, mid, int(arg))
        if action == "cancel":
            ctx.db.exec("UPDATE orders SET status='expired' WHERE tenant_id=? AND id=?",
                        (ctx.tid, int(arg)))
            _release_coins(ctx, int(arg))
            ctx.db.clear_state(user["tg_id"])
            return _reply(ctx, chat_id, mid,
                          "سفارش لغو شد. هر وقت خواستید دوباره اقدام کنید 👍",
                          main_menu(ctx, user))

        # دکمه‌ی «پاسخ» روی تیکت در گروه مدیریت.
        #
        # این هم مثل دکمه‌ی تمدید هندلر نداشت: ادمین روی «پاسخ»
        # می‌زد و هیچ اتفاقی نمی‌افتاد، پس عملاً هیچ تیکتی از داخل
        # تلگرام جواب داده نمی‌شد.
        if action == "tk":
            if not ctx.is_admin(frm["id"]):
                return ctx.bot.answer_cb(cq["id"], "دسترسی ندارید", alert=True)
            return admin_ask_input(ctx, user, chat_id, mid, "tkreply", arg)

        # دکمه‌ی «تمدید» در اشتراک‌های من.
        #
        # این شاخه وجود نداشت: دکمه ساخته می‌شد، کاربر می‌زد و هیچ
        # اتفاقی نمی‌افتاد. هیچ خطایی هم در لاگ نبود چون callback
        # بی‌صدا به انتهای تابع می‌رسید و None برمی‌گرداند.
        if action == "renew":
            return show_renew(ctx, user, chat_id, mid, int(arg))

        if action == "ost":
            return show_order_status(ctx, user, chat_id, mid, int(arg))

        # ارسال مجدد رسید بعد از رد
        if action == "retry":
            o = ctx.db.get_order(int(arg))
            if not o or o["user_id"] != user["id"]:
                return ctx.bot.answer_cb(cq["id"], "سفارش پیدا نشد", alert=True)
            ctx.db.set_state(user["tg_id"], "await_receipt", {"order": int(arg)})
            return _reply(ctx, chat_id, mid,
                          "📤 رسید جدید را بفرستید (عکس یا متن پیامک بانک).",
                          kb([[("انصراف", "menu")]]))

        # ── پنل مدیریت داخل ربات ──
        if action == "adm":
            if not ctx.is_admin(frm["id"]):
                return ctx.bot.answer_cb(cq["id"], "دسترسی ندارید", alert=True)

            sub, _, param = arg.partition(":")
            routes = {
                "orders": lambda: admin_orders(ctx, user, chat_id, mid),
                "users":  lambda: admin_users(ctx, user, chat_id, mid),
                "stats":  lambda: admin_stats(ctx, user, chat_id, mid),
                "plans":  lambda: admin_plans(ctx, user, chat_id, mid),
            }
            if sub in routes:
                return routes[sub]()

            if sub == "o":
                return admin_order_detail(ctx, user, chat_id, mid, int(param))
            if sub == "u":
                return admin_user_detail(ctx, user, chat_id, mid, param)
            if sub == "blk":
                return admin_toggle_block(ctx, user, chat_id, mid, param)
            if sub in ("bc", "find"):
                return admin_ask_input(ctx, user, chat_id, mid, sub)
            if sub in ("coin", "bal", "msg", "ask"):
                return admin_ask_input(ctx, user, chat_id, mid, sub, param)
            return None

        # دکمه‌های ادمین در گروه مدیریت
        if action in ("ap", "rj"):
            if not ctx.is_admin(frm["id"]):
                return ctx.bot.answer_cb(cq["id"], "دسترسی ندارید", alert=True)
            if action == "ap":
                # نتیجه‌ی approve_order قبلاً دور ریخته می‌شد: نه
                # answer_cb زده می‌شد نه پیام گروه عوض می‌شد. یعنی
                # ادمین دکمه را می‌زد، هیچ اتفاقی نمی‌دید و همان رسید
                # با همان دکمه‌ها سر جایش می‌ماند — انگار تایید اصلاً
                # ثبت نشده. خطای واقعی پنل هم هیچ‌وقت دیده نمی‌شد.
                okp, res = approve_order(ctx, int(arg), frm["id"])
                # answer_cb بالای تابع یک‌بار مصرف شده، پس بازخورد را
                # با پیام واقعی می‌دهیم نه با پاسخ کال‌بک
                if okp:
                    try:
                        ctx.bot.edit_markup(chat_id, mid, keyboard=kb(
                            [[(f"✅ سفارش #{arg} تایید شد", f"adm:o:{arg}")]]))
                    except TelegramError as _exc:
                        log.debug("_on_callback step: %s", _exc)
                    ctx.bot.send(chat_id,
                                 f"✅ <b>سفارش #{arg} تایید شد</b>\n"
                                 "کانفیگ ساخته و برای مشتری ارسال شد.")
                elif res == ORDER_BUSY:
                    # نخ دیگری همین سفارش را برداشته. گفتن «ساخت
                    # ناموفق بود» ادمین را به تلاش دوباره تشویق
                    # می‌کند، درست وقتی که نباید.
                    ctx.bot.send(
                        chat_id,
                        f"⏳ سفارش #{arg} همین حالا از مسیر دیگری در حال "
                        "پردازش است. چند لحظه صبر کنید و وضعیتش را ببینید.")
                else:
                    ctx.bot.send(
                        chat_id,
                        f"❌ <b>ساخت کانفیگ سفارش #{arg} ناموفق بود</b>\n\n"
                        f"{esc(str(res))}\n\n"
                        "سفارش هنوز در صف بررسی است. بعد از رفع مشکل "
                        "دوباره تایید بزنید.")
                return None
            # از ادمین دلیل می‌پرسیم — رد بدون توضیح، مشتری را سردرگم
            # و عصبانی می‌کند و بار پشتیبانی را بالا می‌برد.
            ctx.db.set_state(frm["id"], "adm_reject", {"t": str(arg)})
            ctx.bot.send(
                chat_id,
                f"❌ <b>رد سفارش #{arg}</b>\n\n"
                "دلیل رد را بنویسید تا برای مشتری فرستاده شود.\n\n"
                "<i>یا یکی از دلیل‌های آماده را انتخاب کنید:</i>",
                keyboard=kb([
                    [("مبلغ نادرست", f"rjr:{arg}:amount")],
                    [("رسید ناخوانا", f"rjr:{arg}:unclear")],
                    [("رسید تکراری", f"rjr:{arg}:dup")],
                    [("رسید نامعتبر", f"rjr:{arg}:invalid")],
                    [("انصراف", f"adm:o:{arg}")],
                ]))
            return ctx.bot.answer_cb(cq["id"], "دلیل را انتخاب یا بنویسید")

        # دلیل آماده‌ی رد
        if action == "rjr":
            if not ctx.is_admin(frm["id"]):
                return ctx.bot.answer_cb(cq["id"], "دسترسی ندارید", alert=True)
            oid, _, code = arg.partition(":")
            reasons = {
                "amount": "مبلغ واریزی با مبلغ سفارش یکی نبود. "
                          "لطفاً دقیقاً همان مبلغ را واریز کنید.",
                "unclear": "تصویر رسید خوانا نبود. "
                           "یک عکس واضح‌تر یا متن پیامک بانک بفرستید.",
                "dup": "این رسید قبلاً برای سفارش دیگری استفاده شده است.",
                "invalid": "این رسید تأیید نشد. "
                           "اگر مطمئنید واریز کرده‌اید، به پشتیبانی پیام بدهید.",
            }
            ctx.db.clear_state(frm["id"])
            done = do_reject(ctx, int(oid), frm["id"],
                             reasons.get(code, "رسید تأیید نشد."))
            if not done:
                # دکمه‌ها را برمی‌داریم ولی ادمین باید بداند چرا
                # چیزی به مشتری نرفت
                ctx.bot.answer_cb(
                    cq["id"],
                    "رد نشد: یا کانفیگش ساخته شده یا قبلاً رد شده بود.",
                    alert=True)
            return ctx.bot.edit_markup(chat_id, mid, None)

    except (ValueError, TypeError):
        log.warning("callback نامعتبر: %s", data)
    return None


def do_reject(ctx, order_id, admin_tg_id, reason):
    """
    رد سفارش با دلیل مشخص و اطلاع‌رسانی به مشتری.

    مشتری باید بداند چرا رد شده و چه کاری بکند — وگرنه یا پیگیری
    نمی‌کند (فروش از دست می‌رود) یا با عصبانیت به پشتیبانی می‌زند.
    """
    # شرطی: سفارشی که کانفیگش ساخته شده رد نمی‌شود، و رد دوباره هم
    # پیام دوم به مشتری نمی‌فرستد.
    if not ctx.db.mark_rejected(order_id, admin_tg_id, reason):
        return False

    o = ctx.db.get_order(order_id)
    if not o:
        return False

    # سکه‌های رزروشده برمی‌گردند.
    #
    # قبلاً این‌جا بی‌قید add_coins صدا زده می‌شد، در حالی که سکه‌ای
    # کم نشده بود — یعنی هر سفارشی که رد می‌شد، به مشتری سکه‌ی
    # رایگان می‌داد. حالا فقط چیزی که واقعاً رزرو شده آزاد می‌شود.
    _release_coins(ctx, order_id)

    u = ctx.db.get_user_by_id(o["user_id"])
    if not u:
        return False

    support = ctx.s.get("support_username") or ""
    tpl = ctx.s.get("reject_text")
    if tpl:
        txt = (tpl.replace("{order_id}", str(order_id))
                  .replace("{reason}", reason)
                  .replace("{support}", support))
    else:
        txt = (
            "❌ <b>رسیدتان تأیید نشد</b>\n\n"
            f"<b>دلیل:</b>\n{esc(reason)}\n\n"
        )
        if o.get("coins_used"):
            txt += (f"🪙 <b>{core.fa(o['coins_used'])}</b> سکه‌ای که خرج شده بود "
                    "به حسابتان برگشت.\n\n")
        txt += ("رسید درست را دوباره بفرستید تا سریع بررسی شود.\n\n"
                f"<i>کد پیگیری:</i> <code>#{order_id}</code>")

    rows = [[("🔄 ارسال مجدد رسید", f"retry:{order_id}")]]
    if support:
        rows.append([("🎧 پشتیبانی", f"https://t.me/{support.lstrip('@')}", "url")])
    rows.append([("‹ منوی اصلی", "menu")])

    try:
        ctx.bot.send(u["tg_id"], txt, keyboard=kb(rows))
    except TelegramError as _exc:
        log.warning("rejection notice to customer: %s", _exc)

    # و همان خبر در صندوقِ مینی‌اپ.
    #
    # مشتری که از مینی‌اپ خریده، ممکن است گفتگوی ربات را باز نکند.
    # بدون این، رسیدش رد می‌شود و *دلیلش را هیچ‌وقت نمی‌بیند* — و
    # بعد از پشتیبانی می‌پرسد چرا. متن همان متنی است که مالک نوشته.
    try:
        ctx.db.chat_add(
            o["user_id"], "system",
            f"رسید سفارش #{order_id} تایید نشد.\n\nدلیل: {reason}",
            order_id=order_id)
    except Exception:
        log.warning("ثبت خبرِ رد در صندوق ناموفق", exc_info=True)

    return True


# ═══════════════════════════════════════════════════════════
#  توابع زمان‌بند
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
#  Channel: only the name customers are shown stays in the core.
#  Posting is Pro: bot/pro/channel.py (docs/specs/2026-09-29-pro-split.md).
# ═══════════════════════════════════════════════════════════

def public_channel(ctx):
    """
    کانالی که به مشتری معرفی می‌شود (پیامِ تحویل): کانالِ عضویت، وگرنه کانالِ
    پست‌ها — فقط اگر یوزرنیم دارد. کانالِ خصوصی (شناسه‌ی عددی) به کارِ مشتری
    نمی‌آید.
    """
    for k in ("force_channel", "channel_id"):
        ch = str(ctx.s.get(k) or "").strip()
        if ch and not ch.lstrip("-").isdigit():
            return ch if ch.startswith("@") or "t.me/" in ch else "@" + ch.lstrip("@")
    return ""


def send_expiry_notice(tenant, bot, sub, days_left):
    """یادآوری نزدیک‌شدن انقضا با دکمه‌ی تمدید."""
    ctx = Ctx(bot, tenant)
    if days_left <= 0:
        head = "⛔️ <b>اشتراکتان امروز تمام می‌شود</b>"
    elif days_left == 1:
        head = "⏰ <b>فقط یک روز تا پایان اشتراک</b>"
    else:
        head = f"⏰ <b>{core.fa(days_left)} روز تا پایان اشتراک</b>"

    # sub گاهی sqlite3.Row است و .get ندارد — با یک dict ساده کار
    # می‌کنیم تا sub_label بتواند مثل بقیه‌جا رفتارش را انجام دهد
    srow = {k: sub[k] for k in sub.keys()} if hasattr(sub, "keys") else dict(sub)
    label = ctx.sub_label(srow)

    # دکمه مستقیم همین اشتراک را تمدید می‌کند، نه «خرید» کلی —
    # وگرنه کاربر دوباره باید حدس بزند کدام را انتخاب کند.
    #
    # این یک خط قبلاً فقط در مسیرِ پیش‌فرض بود و مسیرِ متنِ سفارشی
    # `"buy"` می‌داد. یعنی هر مالکی که متن را عوض می‌کرد، بی‌آنکه
    # بداند دکمه‌ی هدفمند را هم از دست می‌داد.
    renew_cb = f"renew:{srow['id']}" if srow.get("id") else "mysubs"
    renew_kb = kb([[(f"🔄 تمدید · {label}", renew_cb)],
                   [("‹ منوی اصلی", "menu")]])

    tpl = ctx.s.get("expiry_text")
    if tpl:
        txt = (tpl.replace("{days}", str(max(days_left, 0)))
                  .replace("{plan}", esc(str(srow.get("plan_name") or "")))
                  .replace("{label}", esc(label)))
        _chat_notice(ctx, srow, txt)
        return ctx.bot.send(srow.get("tg_id"), txt, keyboard=renew_kb)

    txt = F.join(
        head,
        f"📦 {F.b(label)}",
        F.lines(
            "اگر تمدید نکنید، اتصالتان قطع می‌شود.",
            "تمدید یک دکمه است و کانفیگ فعلی‌تان " + F.b("همان می‌ماند") +
            " و لازم نیست چیزی را دوباره اضافه کنید.",
        ),
    )
    _chat_notice(ctx, srow, txt)
    try:
        bot.send(sub["tg_id"], txt, keyboard=renew_kb)
    except TelegramError as e:
        log.warning("یادآوری ارسال نشد (%s): %s", sub["tg_id"], e)


def send_delete_notice(tenant, bot, sub):
    """
    The day before the sweep deletes a config that ended and was not renewed
    (docs/specs/2026-09-30-vpn-fixes.md, task 9). The renew button keeps the
    same config, so the buyer adds nothing again.
    """
    ctx = Ctx(bot, tenant)
    srow = {k: sub[k] for k in sub.keys()} if hasattr(sub, "keys") else dict(sub)
    label = ctx.sub_label(srow)
    txt = F.join(
        F.title("فردا این اشتراک پاک می‌شود", "🗑"),
        f"📦 {F.b(label)}",
        F.lines(
            "اعتبارش تمام شده و هنوز تمدید نشده.",
            "اگر تا فردا تمدید کنید همین کانفیگ می‌ماند و لازم نیست چیزی را دوباره اضافه کنید.",
        ),
    )
    _chat_notice(ctx, srow, txt)
    return bot.send(srow.get("tg_id"), txt,
                    keyboard=kb([[(f"🔄 تمدید · {label}", f"renew:{srow['id']}")],
                                 [("‹ منوی اصلی", "menu")]]))


def send_traffic_notice(tenant, bot, sub, used_gb, total_gb):
    """
    هشدار «حجمت دارد تمام می‌شود».

    ستون notified_80p از ابتدا در جدول بود و دو جای کد صفرش می‌کردند،
    ولی هیچ‌جا پُرش نمی‌کرد — یعنی این هشدار هیچ‌وقت فرستاده نمی‌شد.
    مشتری حجمش تمام می‌شد، اتصالش می‌خوابید، و اولین خبری که می‌گرفت
    قطع‌شدن بود.

    برخلاف انقضا، حجم تاریخ ندارد: کسی ممکن است در یک شب تمامش کند.
    پس این هشدار روی درصد مصرف کار می‌کند، نه روی روز.
    """
    ctx = Ctx(bot, tenant)
    pct = min(100, int(used_gb * 100 / total_gb)) if total_gb else 0
    left_gb = max(0, round(total_gb - used_gb, 1))

    srow = {k: sub[k] for k in sub.keys()} if hasattr(sub, "keys") else dict(sub)
    label = ctx.sub_label(srow)

    # مثل `expiry_text` — همان سازوکار، تا مالک مجبور نشود یکی را
    # بتواند عوض کند و دیگری را نه.
    tpl = (ctx.s.get("reminders") or {}).get("traffic_text")
    if tpl:
        txt = (tpl.replace("{used}", core.fa(used_gb))
                  .replace("{total}", core.fmt_gb(total_gb))
                  .replace("{left}", core.fa(left_gb))
                  .replace("{pct}", core.fa(pct))
                  .replace("{plan}", esc(str(srow.get("plan_name") or "")))
                  .replace("{label}", esc(label)))
        renew_cb = f"renew:{srow['id']}" if srow.get("id") else "mysubs"
        _chat_notice(ctx, srow, txt)
        return bot.send(srow.get("tg_id"), txt,
                        keyboard=kb([[(f"🔄 تمدید · {label}", renew_cb)],
                                     [("‹ منوی اصلی", "menu")]]))

    txt = F.join(
        F.title(f"{core.fa(pct)}٪ از حجمتان مصرف شده", "📊"),
        f"📦 {F.b(label)}",
        F.lines(
            F.row("مصرف‌شده", f"{core.fa(used_gb)} از {core.fmt_gb(total_gb)}", "💾"),
            F.row("باقی‌مانده", f"{core.fa(left_gb)} گیگ", "🟢"),
        ),
        F.quote("وقتی حجم تمام شود اتصال قطع می‌شود، حتی اگر تاریخ "
                "اشتراکتان هنوز باقی باشد."),
    )
    renew_cb = f"renew:{srow['id']}" if srow.get("id") else "mysubs"
    _chat_notice(ctx, srow, txt)
    try:
        bot.send(sub["tg_id"], txt,
                 keyboard=kb([[(f"🔄 تمدید · {label}", renew_cb)],
                              [("‹ منوی اصلی", "menu")]]))
    except TelegramError as e:
        log.warning("هشدار حجم ارسال نشد (%s): %s", sub["tg_id"], e)


def _renew_gave_up(ctx, sub, why):
    """
    تمدید خودکاری که اصلاً نمی‌تواند اجرا شود.

    یک بار به مشتری و گروه گفته می‌شود، نه هر ساعت.
    """
    n = ctx.db.renew_failed(sub["id"], max_hours=24)
    if n != 1:
        return
    user = ctx.db.get_user_by_id(sub["user_id"])
    if not user:
        return
    try:
        ctx.bot.send(
            user["tg_id"],
            F.join(
                F.title("تمدید خودکار انجام نشد", "⚠️"),
                why + ".",
                F.quote("برای اینکه اشتراکتان قطع نشود، دستی تمدید کنید "
                        "یا به پشتیبانی پیام بدهید."),
            ),
            keyboard=kb([[("📊 اشتراک‌های من", "mysubs")]]))
    except TelegramError as _exc:
        log.warning("renewal-failed notice to customer: %s", _exc)
    ctx.notify_group(
        f"⚠️ تمدید خودکار ممکن نیست\n👤 <code>{user['tg_id']}</code>\n"
        f"{esc(why)}", topic="alerts")


def _tell_renew_stuck(ctx, user, sub, plan):
    """بعد از چند شکست پیاپی، مشتری باید خودش دست به کار شود."""
    try:
        srow = {k: sub[k] for k in sub.keys()} if hasattr(sub, "keys") else dict(sub)
        ctx.bot.send(
            user["tg_id"],
            F.join(
                F.title("تمدید خودکار چند بار ناموفق بود", "⚠️"),
                F.lines(f"📦 {F.b(ctx.sub_label(srow, plan_name=plan['name']))}"),
                "پولی از کیف پولتان کم نشده.",
                F.quote("برای اینکه اشتراکتان قطع نشود، دستی تمدید کنید "
                        "یا به پشتیبانی پیام بدهید."),
            ),
            keyboard=kb([[("🔁 تمدید دستی", f"renew:{sub['id']}")],
                         [("📊 اشتراک‌های من", "mysubs")]]))
    except TelegramError as _exc:
        log.debug("_tell_renew_stuck step: %s", _exc)


def auto_renew_subscription(tenant, bot, sub):
    """
    تمدید خودکار از کیف پول.

    اگر موجودی کافی نباشد، فقط اطلاع می‌دهیم — تمدید خودکار خاموش
    نمی‌شود تا اگر کاربر شارژ کرد، دفعه‌ی بعد انجام شود.
    """
    ctx = Ctx(bot, tenant)
    if store_gate(ctx):
        # پیامی به مشتری نمی‌رود: زمان‌بند هر دور دوباره این‌جا می‌رسد و
        # هر بار یک پیام می‌شد. لاگ هست تا بی‌صدا نباشد.
        log.warning("auto-renew skipped: store %s has no active subscription "
                    "(sub %s)", ctx.tid, sub["id"])
        return
    plan = ctx.db.get_plan(sub["plan_id"]) if sub["plan_id"] else None
    if not plan:
        # پلن حذف شده. قبلاً این‌جا بی‌صدا برمی‌گشت: تمدید خودکار
        # روشن می‌ماند، هیچ‌وقت اجرا نمی‌شد، و مشتری تا لحظه‌ی قطع‌شدن
        # فکر می‌کرد پوشش دارد.
        _renew_gave_up(ctx, sub, "پلن این اشتراک دیگر موجود نیست")
        return

    user = ctx.db.get_user_by_id(sub["user_id"])
    if not user:
        return

    if user["balance"] < plan["price"]:
        try:
            short = plan["price"] - user["balance"]
            # نام پلن باید بیاید: کاربری که چند اشتراک دارد وگرنه
            # نمی‌داند کدامشان تمدید نشده و دنبال کدام باید بگردد
            srow = {k: sub[k] for k in sub.keys()} if hasattr(sub, "keys") else dict(sub)
            bot.send(user["tg_id"],
                     F.join(
                         F.title("تمدید خودکار انجام نشد", "⚠️"),
                         F.lines(
                             f"📦 {F.b(ctx.sub_label(srow, plan_name=plan['name']))}",
                             F.i(f"{core.fmt_gb(plan['gb'])} · "
                                 f"{core.fmt_days(plan['days'])}"),
                         ),
                         "موجودی کیف پولتان کافی نبود.",
                         F.lines(
                             F.row("لازم", core.toman(plan["price"]) + " تومان", "💰"),
                             F.row("موجودی", core.toman(user["balance"]) + " تومان", "👛"),
                             F.row("کسری", core.toman(short) + " تومان", "➖"),
                         ),
                         F.quote("کیف پول را شارژ کنید تا دفعه‌ی بعد خودکار "
                                 "انجام شود. تمدید خودکارتان هنوز روشن است."),
                     ),
                     keyboard=kb([[("👛 شارژ کیف پول", "wallet")],
                                  [("📊 اشتراک‌های من", "mysubs")]]))
        except TelegramError as _exc:
            log.debug("auto_renew_subscription step: %s", _exc)
        return

    order = ctx.db.create_order(user["id"], plan["id"], plan["price"], plan["price"],
                                kind="renew", paid_from="wallet")

    # اتمی: زمان‌بند تمدید خودکار در نخ جداگانه‌ای می‌دود و قفل هر چت
    # آن را پوشش نمی‌دهد. یعنی می‌تواند دقیقاً هم‌زمان با خریدِ خود
    # کاربر اجرا شود و دو بار از یک موجودی بردارد.
    paid, left = ctx.db.spend_balance(
        user["id"], plan["price"], "renew",
        f"تمدید خودکار اشتراک #{sub['id']}", order["id"])
    if not paid:
        ctx.db.close_order(order["id"], "rejected", "موجودی کیف پول کافی نبود")
        log.info("تمدید خودکار اشتراک %s: موجودی کافی نبود (%s تومان)",
                 sub["id"], left)
        return

    # سفارش این‌جا approved *نمی‌شود*.
    #
    # قبلاً می‌شد، و اگر ساخت شکست می‌خورد پول برمی‌گشت ولی سفارش
    # approved می‌ماند — یعنی پولِ برگشته در آمار «فروش» شمرده
    # می‌شد. و تمدیدِ ناموفق رها نمی‌شود؛ با فاصله دوباره تلاش
    # می‌کند. پس یک اشتراکِ گیرکرده هر روز چند فروشِ خیالی به آمار
    # اضافه می‌کرد.
    ok, result = provision(ctx, order["id"])
    if ok:
        ctx.db.close_order(order["id"], "approved")
        ctx.db.renew_succeeded(sub["id"])

        # An automatic renewal is a sale too. Once only the card path paid
        # commission, so a partner earned nothing from the renewals of a
        # customer they brought. The referral reward is "one per friend", so
        # here it only pays a friend who was never rewarded before (say, their
        # first purchase was from the wallet when that path forgot it).
        after_paid_order(ctx, user, order["id"])

        # پرچم‌های یادآوری برای دوره‌ی جدید صفر می‌شوند
        ctx.db.exec(
            """UPDATE subscriptions
               SET notified_7d=0, notified_3d=0, notified_1d=0, notified_80p=0
               WHERE tenant_id=? AND id=?""",
            (ctx.tid, sub["id"])
        )
        try:
            srow2 = {k: sub[k] for k in sub.keys()} if hasattr(sub, "keys") else dict(sub)
            bot.send(user["tg_id"],
                     F.join(
                         F.title("اشتراکتان خودکار تمدید شد", "✅"),
                         F.lines(
                             f"📦 {F.b(ctx.sub_label(srow2, plan_name=plan['name']))}",
                             F.i(f"{core.fmt_gb(plan['gb'])} · "
                                 f"{core.fmt_days(plan['days'])}"),
                         ),
                         f"💰 {F.b(core.toman(plan['price']) + ' تومان')} "
                         "از کیف پول کم شد.",
                         F.quote("کاری لازم نیست بکنید. کانفیگ فعلی‌تان "
                                 "همان است و وصل می‌ماند."),
                     ),
                     keyboard=kb([[("📊 اشتراک‌های من", "mysubs")]]))
        except TelegramError as _exc:
            log.debug("auto_renew_subscription step: %s", _exc)
        ctx.notify_group(f"🔁 تمدید خودکار\n👤 <code>{user['tg_id']}</code>\n"
                         f"💰 {core.toman(plan['price'])} تومان", topic="renewals")
    else:
        # پول برمی‌گردد و سفارش بسته می‌شود — با هم، وگرنه یکی از آن
        # دو جا می‌ماند. برگشت هم به سفارش گره می‌خورد؛ قبلاً
        # order_id نمی‌گرفت و در دفتر پیدا نمی‌شد.
        ctx.db.close_order(order["id"], "rejected",
                           "بازگشت وجه: تمدید خودکار ناموفق")

        # همان خطا هر ساعت تکرار می‌شود. بدون شمردن، گروه مدیریت
        # شبانه‌روز یک پیام را می‌گیرد و هشدارِ واقعیِ بعدی گم می‌شود.
        n = ctx.db.renew_failed(sub["id"])
        if n == 1 or n % 6 == 0:
            ctx.notify_group(
                f"⚠️ تمدید خودکار ناموفق (بار {core.fa(n)})\n"
                f"👤 <code>{user['tg_id']}</code>\n"
                f"خطا: {esc(str(result))}", topic="alerts")
        else:
            log.warning("تمدید خودکار اشتراک %s بار %s ناموفق: %s",
                        sub["id"], n, result)
        if n == 3:
            _tell_renew_stuck(ctx, user, sub, plan)


def send_daily_report(tenant):
    """گزارش روزانه در تاپیک آمار."""
    bot = Bot(tenant["bot_token"])
    ctx = Ctx(bot, tenant)
    s = ctx.db.stats()

    today = ctx.db.q(
        """SELECT COUNT(*) c, COALESCE(SUM(amount),0) sum FROM orders
           WHERE tenant_id=? AND status='approved' AND date(created_at)=date('now')""",
        (ctx.tid,), one=True
    )
    new_users = ctx.db.q(
        "SELECT COUNT(*) c FROM users WHERE tenant_id=? AND date(created_at)=date('now')",
        (ctx.tid,), one=True
    )

    txt = (f"📊 <b>گزارش امروز</b>\n\n"
           f"فروش   <b>{core.fa(today['c'])}</b> سفارش\n"
           f"درآمد   <b>{core.toman(today['sum'])}</b> تومان\n"
           f"کاربر جدید   <b>{core.fa(new_users['c'])}</b>\n\n"
           f"<b>در مجموع</b>\n"
           f"کاربران   {core.fa(s.get('users', 0))}\n"
           f"اشتراک فعال   {core.fa(s.get('active_subs', 0))}")
    ctx.notify_group(txt, topic="stats")
