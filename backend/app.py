"""بک‌اند پنل مدیریت صفحه‌ی اشتراک Nexora"""

import os
import json
import re as _re
import secrets
import threading as _threading
import time
import logging
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import (FastAPI, HTTPException, Header, Request, Response,
                     Depends)
from fastapi.middleware.cors import CORSMiddleware
import contextvars as _contextvars
import hmac as _hmac
import secrets as _secrets
import ipaddress as _ipaddress
import time as _time
from fastapi.responses import HTMLResponse, JSONResponse

log = logging.getLogger("nexora.panel")

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "../data/config.json"))
AUTH_PATH = Path(os.getenv("AUTH_PATH", str(CONFIG_PATH.parent / "auth.json")))
ADMIN_PASSWORD = os.getenv("NEXORA_SUBPAGE_ADMIN_PASSWORD", "change-me")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")


#: رمز به‌شکل هَش ذخیره می‌شود، نه متنِ ساده.
#
#  چرا: تا امروز `auth.json` خودِ رمز را داشت. هر کسی که آن فایل را
#  می‌خواند — پشتیبانِ لو رفته، اسنپ‌شاتِ جابه‌جاشده، یک خطای مسیر —
#  مستقیم به پنل، رمز x-ui، توکن ربات و داده‌ی همه‌ی مشتری‌ها
#  می‌رسید. هَش این را به یک حدس‌زدنِ گران تبدیل می‌کند.
#
#  چرا PBKDF2 و نه یک هَشِ ساده: SHA سریع است و سرعت دقیقاً همان
#  چیزی است که حدس‌زننده می‌خواهد.
PW_SCHEME = "pbkdf2_sha256"
PW_ITERS = 200_000


def _pw_hash(pw: str, salt: bytes = None, iters: int = PW_ITERS) -> str:
    import hashlib
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", str(pw).encode("utf-8"), salt, iters)
    return f"{PW_SCHEME}${iters}${salt.hex()}${dk.hex()}"


def _pw_is_hash(v: str) -> bool:
    return isinstance(v, str) and v.startswith(PW_SCHEME + "$")


def _pw_check(given: str, stored: str) -> bool:
    """
    مقایسه‌ی زمان‌ثابت — چه ذخیره‌شده هَش باشد چه متنِ ساده.

    متنِ ساده هنوز پذیرفته می‌شود چون نصب‌های قبلی همان را دارند و
    ردکردنش یعنی قفل‌شدنِ مالک پشتِ پنلِ خودش. اولین ورودِ موفق
    خودش ارتقا می‌دهد.
    """
    import hashlib
    g = str(given or "")
    st = str(stored or "")
    if not st:
        return False
    if _pw_is_hash(st):
        try:
            _, it, salt_hex, want = st.split("$", 3)
            dk = hashlib.pbkdf2_hmac("sha256", g.encode("utf-8"),
                                     bytes.fromhex(salt_hex), int(it))
        except (ValueError, TypeError):
            log.error("قالبِ رمزِ ذخیره‌شده خوانده نشد")
            return False
        return _hmac.compare_digest(dk.hex(), want)
    # بایت مقایسه می‌شود، نه رشته: compare_digest روی رشته‌ی غیراسکی
    # TypeError می‌دهد — یک رمز فارسی کل پنل را با ۵۰۰ می‌بست.
    return _hmac.compare_digest(g.encode("utf-8"), st.encode("utf-8"))


def _stored_password():
    """مقدارِ خام (هَش یا متن) — فقط برای سنجیدن، نه برای پاس‌دادن."""
    if AUTH_PATH.exists():
        try:
            with open(AUTH_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                pw = data.get("password")
                if pw:
                    return pw
        except (json.JSONDecodeError, OSError):
            log.warning("auth.json خوانده نشد؛ از متغیر محیطی", exc_info=True)
    return ADMIN_PASSWORD


def verify_password(given: str) -> bool:
    """
    آیا این رمز درست است؟

    و اگر ذخیره‌شده هنوز متنِ ساده بود، همین‌جا ارتقا می‌دهد — تا
    مهاجرت بدون اینکه کسی کاری کند انجام شود.
    """
    stored = _stored_password()
    if not _pw_check(given, stored):
        return False
    if not _pw_is_hash(stored):
        try:
            save_password(given)
            log.info("رمز پنل به شکل هَش ذخیره شد")
        except Exception:
            # ارتقا نشد؛ ولی ورود درست بود و نباید بشکند
            log.warning("ارتقای رمز به هَش ناموفق", exc_info=True)
    return True


#: نشانه‌ی فراخوانِ درونی.
#
#  یک مسیرِ نماینده، تابعِ صورتحسابِ مدیر را مستقیم صدا می‌زند و آن
#  تابع `check_auth` دارد. تا امروز رمزِ ذخیره‌شده را پاس می‌داد —
#  که با هَش‌شدن دیگر جواب نمی‌دهد. مقدارِ تصادفیِ هر اجرا یعنی
#  حدس‌زدنی هم نیست، و چون از بیرون هیچ‌وقت برابرش نمی‌شود، راهِ
#  دور زدن باز نمی‌کند.
_INTERNAL_PW = "internal:" + secrets.token_urlsafe(32)


def load_password():
    """
    مقدارِ ذخیره‌شده.

    **برای مقایسه از `verify_password` استفاده کن، نه از این.** این
    ممکن است هَش برگرداند و مقایسه‌ی مستقیم با آن همیشه غلط است.
    """
    return _stored_password()


def save_password(new_password: str):
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTH_PATH, "w", encoding="utf-8") as f:
        json.dump({"password": _pw_hash(new_password)}, f,
                  ensure_ascii=False, indent=2)
    # محدود کردن دسترسی فایل به مالک (فقط روی سیستم‌های یونیکسی)
    try:
        os.chmod(AUTH_PATH, 0o600)
    except OSError as e:
        # روی ویندوز معنا ندارد؛ روی لینوکس یعنی هشِ رمز برای بقیه‌ی
        # کاربرانِ سرور خواناست — بی‌صدا نباید بماند
        log.warning("could not restrict %s to 0600: %s", AUTH_PATH, e)

DEFAULT_CONFIG = {
    "downloadApps": {
        "android": [
            {"id": "happ", "name": "Happ", "url": "https://github.com/Happ-proxy/happ-android/releases/download/3.26.3/Happ.apk", "recommended": True, "icon": "bolt", "scheme": "happ"},
            {"id": "v2rayng", "name": "v2rayNG", "url": "https://github.com/2dust/v2rayNG/releases/download/2.2.6/v2rayNG_2.2.6_arm64-v8a.apk", "recommended": False, "icon": "paper-plane", "scheme": "v2rayng"}
        ],
        "ios": [
            {"id": "happ", "name": "Happ", "url": "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215", "recommended": True, "icon": "bolt", "scheme": "happ"},
            {"id": "v2box", "name": "V2Box", "url": "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690", "recommended": False, "icon": "shield-halved", "scheme": "v2box"}
        ],
        "desktop": [
            {"id": "happ", "name": "Happ (Windows)", "url": "https://github.com/Happ-proxy/happ-desktop/releases/download/3.3.6/setup-Happ.x64.exe", "recommended": True, "icon": "bolt", "scheme": "happ"},
            {"id": "v2rayn", "name": "v2rayN (Windows)", "url": "https://github.com/2dust/v2rayN/releases/download/7.24.1/v2rayN-windows-arm64.zip", "recommended": False, "icon": "box-open", "scheme": "none"}
        ]
    },
    "faq": {
        "fa": [
            {"q": "چرا نمی‌توانم وصل شوم؟", "a": "اول مطمئن شوید آخرین نسخه‌ی اپ پیشنهادی (Happ) را نصب کرده‌اید و کانفیگ را درست وارد کرده‌اید."},
            {"q": "چطور اشتراکم را تمدید کنم؟", "a": "روی دکمه‌ی «تمدید ساب» در داشبورد بزنید یا مستقیم به پشتیبانی پیام دهید."}
        ],
        "en": [{"q": "Why can't I connect?", "a": "Make sure you've installed the latest version of our recommended app (Happ)."}],
        "tr": [], "ar": []
    },
    "banners": {
        "enabled": True,
        "lowQuotaDaysThreshold": 3,
        "lowQuotaPercentThreshold": 15,
        "disabledTitle": "",
        "disabledDesc": "",
        "disabledButtonText": "",
        "lowQuotaTitle": "",
        "lowQuotaDescDays": "",
        "lowQuotaDescVolume": "",
        "lowQuotaButtonText": "",
        "lowQuotaButtonUrl": ""
    },
    "referral": {"enabled": True},
    "links": {"supportUsername": "", "channelUsername": ""},
    "videoTutorialUrl": None,
    "videos": [],
    "advanced": {
        "brandName": "NEXORA",
        "pageTitle": "Nexora | مدیریت اشتراک",
        "accentColor": "#2B7FD6",
        "accentColor2": "#5AA9E6",
        "defaultLanguage": "fa",
        "defaultTheme": "dark",
        "showNotificationPopup": True,
        "notificationDelaySeconds": 10,
        "showBrandStrip": True,
        "showReferralCard": True,
        "showFaqSection": True,
        "customCss": "",
        "customFooterText": "",
        "allowThemeToggle": True,
        "allowLanguageToggle": True,
        "hideConfigsList": False
    },
    "popup": {
        "enabled": True,
        "delaySeconds": 10,
        "icon": "🔔",
        "title": "آیا مشکلی در اتصال کانفیگ دارید؟",
        "description": "پیشنهاد می‌کنیم از برنامه‌ی Happ استفاده کنید؛ در غیر این صورت به پشتیبانی پیام بدهید",
        "primaryButtonText": "پشتیبانی",
        "primaryButtonUrl": "",
        "dismissButtonText": "خیر",
        "autoCloseSeconds": 15
    },
    "bot": {
        "enabled": False,
        "token": "",
        "adminChatId": "",
        "welcomeMessage": "سلام! به ربات Nexora خوش آمدید 👋",
        "notifyOnPurchase": True,
        "notifyOnExpiry": True,
        "expiryReminderDays": 3
    },
    "resellers": [],
    "template": "classic",
    "palette": "ocean",
    "customPalettes": []
}


# ---------------------------------------------------------------
# قالب‌های داخلی صفحه‌ی اشتراک
# ---------------------------------------------------------------
# هر قالب فقط ظاهر را عوض می‌کند؛ داده و منطق یکسان می‌ماند.
# layout مشخص می‌کند کدام چیدمان استفاده شود:
#   standard = حلقه پیشرفت + کارت‌ها
#   compact  = نوار افقی فشرده
#   glass    = کارت‌های شیشه‌ای با عدد درشت
# ═══════════════════════════════════════════════════════════
#  سیستم قالب: ساختار (template) × طیف رنگی (palette)
#  جدا نگه داشتن این دو یعنی با ۴ ساختار و ۸ پالت،
#  ۳۲ ترکیب در اختیار کاربر است — و افزودن یک پالت جدید
#  خودکار ۴ ترکیب تازه می‌سازد.
# ═══════════════════════════════════════════════════════════

TEMPLATES = [
    {"id": "classic", "name": "Classic", "fa": "کلاسیک",
     "desc": "ظاهر پیش‌فرض — ساده و آشنا"},
    {"id": "analytics", "name": "Analytics", "fa": "تحلیلی",
     "desc": "کارت‌های آماری برجسته با حاشیه‌های رنگی"},
    {"id": "wallet", "name": "Wallet", "fa": "کیف پول",
     "desc": "کارت اصلی گرادینتی + دکمه‌های گرد"},
    {"id": "console", "name": "Console", "fa": "کنسول",
     "desc": "حس ترمینال — مونواسپیس و گوشه‌های تیز"},
]

PALETTES = [
    {"id": "ocean", "name": "Ocean", "fa": "اقیانوس", "builtin": True, "vars": {
        "accent": "#2B7FD6", "accent2": "#5AA9E6", "bg": "#06090F",
        "surface": "#0D1420", "surfaceAlt": "#0A0E17",
        "border": "rgba(255,255,255,0.06)", "text": "#E8EEF7", "textMuted": "#5A6880"}},
    {"id": "violet", "name": "Violet", "fa": "بنفش", "builtin": True, "vars": {
        "accent": "#8B5CF6", "accent2": "#C084FC", "bg": "#0A0713",
        "surface": "#150F26", "surfaceAlt": "#0F0A1C",
        "border": "rgba(255,255,255,0.07)", "text": "#EDE9F7", "textMuted": "#6B6188"}},
    {"id": "ember", "name": "Ember", "fa": "آتشین", "builtin": True, "vars": {
        "accent": "#F97316", "accent2": "#FB923C", "bg": "#0C0906",
        "surface": "#181109", "surfaceAlt": "#120C07",
        "border": "rgba(255,255,255,0.07)", "text": "#FBEDE6", "textMuted": "#8F7365"}},
    {"id": "forest", "name": "Forest", "fa": "جنگل", "builtin": True, "vars": {
        "accent": "#10B981", "accent2": "#34D399", "bg": "#04100C",
        "surface": "#0A1D16", "surfaceAlt": "#071711",
        "border": "rgba(255,255,255,0.06)", "text": "#E4F7EF", "textMuted": "#5A806F"}},
    {"id": "rose", "name": "Rose", "fa": "رز", "builtin": True, "vars": {
        "accent": "#EC4899", "accent2": "#F472B6", "bg": "#0E060B",
        "surface": "#1B0D16", "surfaceAlt": "#150A11",
        "border": "rgba(255,255,255,0.07)", "text": "#FDF2FA", "textMuted": "#8B6F80"}},
    {"id": "gold", "name": "Gold", "fa": "طلایی", "builtin": True, "vars": {
        "accent": "#D4AF37", "accent2": "#E8C766", "bg": "#0C0A07",
        "surface": "#171310", "surfaceAlt": "#110E0B",
        "border": "rgba(212,175,55,0.16)", "text": "#F5EFE2", "textMuted": "#8F8371"}},
    {"id": "cyan", "name": "Cyan", "fa": "فیروزه‌ای", "builtin": True, "vars": {
        "accent": "#06B6D4", "accent2": "#22D3EE", "bg": "#04121A",
        "surface": "#0A2029", "surfaceAlt": "#071821",
        "border": "rgba(255,255,255,0.07)", "text": "#E0F5FA", "textMuted": "#6E96A3"}},
    {"id": "slate", "name": "Slate", "fa": "خاکستری", "builtin": True, "vars": {
        "accent": "#94A3B8", "accent2": "#CBD5E1", "bg": "#0B0C0F",
        "surface": "#14161B", "surfaceAlt": "#101216",
        "border": "rgba(255,255,255,0.09)", "text": "#F1F5F9", "textMuted": "#6B7480"}},
]


def get_template(tpl_id=None):
    for t in TEMPLATES:
        if t["id"] == tpl_id:
            return t
    return TEMPLATES[0]


def get_palette(cfg, pal_id=None):
    for p in PALETTES:
        if p["id"] == pal_id:
            return p
    for p in cfg.get("customPalettes", []):
        if p.get("id") == pal_id:
            return p
    return PALETTES[0]


#: Assets the Pro package hands to the core (backend/pro/subpage.py).
_PRO_ASSETS = {}


def _pro_templates_ok():
    """Templates other than classic are Pro (`subpage_templates`)."""
    try:
        return bool(_PRO_ASSETS.get("subpage_css")) and LIC.allowed("subpage_templates")
    except Exception:
        log.warning("template license check failed; showing classic", exc_info=True)
        return False


def resolve_theme(cfg, template_id=None, palette_id=None):
    """ترکیب ساختار و رنگ — چیزی که صفحه‌ی اشتراک برای رندر لازم دارد."""
    tpl = get_template(template_id or cfg.get("template"))
    # A Pro template without the license (or without the Pro package) shows
    # classic: the customer's page keeps working and the owner's choice is
    # kept for when the license comes back.
    if tpl["id"] != "classic" and not _pro_templates_ok():
        tpl = get_template("classic")
    pal = get_palette(cfg, palette_id or cfg.get("palette"))
    out = {
        "template": tpl["id"], "templateName": tpl["name"],
        "palette": pal["id"], "paletteName": pal["name"],
        "vars": pal.get("vars", {}),
    }
    if tpl["id"] != "classic":
        out["css"] = _PRO_ASSETS["subpage_css"]
    return out


def deep_merge(base: dict, override: dict) -> dict:
    """ادغام عمیق: مقادیر override روی base می‌نشینند، بقیه دست‌نخورده می‌مانند."""
    result = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def find_reseller(cfg: dict, email: str = None, host: str = None):
    """
    واسطه‌ی مربوطه را پیدا می‌کند. اولویت با دامنه است (دقیق‌تر)،
    بعد پیشوند ایمیل. اگر هیچ‌کدام نخورد، None برمی‌گرداند
    (یعنی برند اصلی خودتان نمایش داده می‌شود).
    """
    resellers = [r for r in cfg.get("resellers", []) if r.get("enabled", True)]

    # ۱. تطبیق دامنه (دقیق‌تر، اولویت بالاتر)
    if host:
        clean_host = host.split(":")[0].lower().strip()
        # حذف www. برای تطبیق راحت‌تر
        if clean_host.startswith("www."):
            clean_host = clean_host[4:]
        for r in resellers:
            for d in (r.get("domains") or []):
                d_clean = d.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]
                if d_clean.startswith("www."):
                    d_clean = d_clean[4:]
                if d_clean and (clean_host == d_clean or clean_host.endswith("." + d_clean)):
                    return r

    # ۲. تطبیق پیشوند ایمیل
    if email:
        e = email.lower().strip()
        for r in resellers:
            # جداکننده‌ی تهِ پیشوند برداشته می‌شود: پنل «macan» می‌خواهد و
            # خودش «_» را می‌گذارد، ولی مالکی که «macan_» تایپ کند (یعنی همان
            # چیزی که در ایمیل‌ها می‌بیند) پیشوندِ «macan__» می‌ساخت که با
            # هیچ ایمیلی نمی‌خورد — و مشتریِ واسطه بی‌صدا برندِ مالک را می‌دید.
            prefix = (r.get("emailPrefix") or "").lower().strip().rstrip("_-.")
            if prefix and (e.startswith(prefix + "_") or e.startswith(prefix + "-") or e.startswith(prefix + ".")):
                return r

    return None

app = FastAPI(title="Nexora Sub Page Config API")
# `expose_headers` لازم است: هدرِ سفارشی در حالت cross-origin
# برای جاوااسکریپت نامرئی است مگر این‌جا نامش بیاید — و پنل
# روی همان مبدأ صفحه‌ی اشتراک نیست. بدون این، نسخه‌ی تنظیمات
# همیشه null می‌شد و محافظِ «دو تبِ باز» بی‌صدا از کار می‌افتاد.
app.add_middleware(CORSMiddleware, allow_origins=[ALLOWED_ORIGIN],
                   allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["X-Config-Version"])


#: تنظیماتِ پنل روی دیتابیس می‌نشیند، نه فایل JSON.
#
#  چرا عوض شد — سه چیز، هر سه واقعی:
#
#  ۱. نوشتن اتمی نبود. `open(w)` اول فایل را خالی می‌کرد بعد
#     می‌نوشت؛ برق برود یا دیسک پر شود، فایل نصفه می‌ماند.
#  ۲. و خرابی بی‌صدا بود: JSONِ خراب یعنی برگشت به `DEFAULT_CONFIG`،
#     یعنی برند و پالت و لینک‌ها و فهرست نماینده‌ها پاک می‌شدند و
#     هیچ‌جا نمی‌گفت چرا. مالک فکر می‌کرد خودش خرابش کرده.
#  ۳. آخرین ذخیره همه‌چیز را می‌برد. دو تبِ باز یعنی یکی بی‌صدا
#     کارِ دیگری را پاک می‌کند.
#
#  چرا داخل `bot.db` و نه فایلِ سوم: یک فایل برای پشتیبان‌گرفتن و
#  برگرداندن، همان چیزی که مالک خواست.
CONFIG_HISTORY_KEEP = 50

#: جدول‌ها یک‌بار ساخته می‌شوند، نه در هر اتصال
_CFG_READY = False
_CFG_LOCAL = _threading.local()


def _cfg_con():
    """
    اتصال به دیتابیسِ تنظیمات، با ساختِ جدول‌ها اگر نبودند.

    `CHECK (id = 1)` عمدی است: یک ردیف، ساختاری تضمین‌شده. این همان
    دامِ «FROM … LIMIT 1 بدون شرط» است که در این مخزن پنج بار پیدا
    شد — این‌جا از اول ممکنش نمی‌کنیم.
    """
    import sqlite3
    # اتصال به‌ازای هر نخ نگه داشته می‌شود و بسته نمی‌شود.
    #
    # اندازه‌گیری: با بازکردنِ اتصالِ تازه در هر خواندن، هر
    # `load_config()` حدود یک میلی‌ثانیه طول می‌کشید — کندتر از
    # خواندنِ همان فایل JSON. هزینه‌اش خودِ باز کردن بود، نه کوئری.
    #
    # اتصالِ SQLite فقط در نخِ خودش امن است، و FastAPI مسیرهای
    # همگام را در یک استخرِ نخ اجرا می‌کند که نخ‌هایش بازاستفاده
    # می‌شوند — پس تعدادِ اتصال‌ها کران‌دار است.
    have = getattr(_CFG_LOCAL, "con", None)
    if have is not None:
        return have
    BOT_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(BOT_DB), timeout=15)
    con.row_factory = sqlite3.Row
    # پیش‌فرضِ پایتون تراکنشِ deferred است؛ برای ادعا کردن پیش از
    # نوشتن، خودمان BEGIN IMMEDIATE می‌زنیم
    con.isolation_level = None
    # ساختِ جدول فقط یک‌بار در عمرِ پردازه.
    #
    # اندازه‌گیری: با اجرای این دو دستور در هر اتصال، خواندنِ
    # تنظیمات ۱٫۱۷ میلی‌ثانیه شد — کندتر از خواندنِ همان فایل JSON،
    # یعنی دقیقاً برعکسِ چیزی که می‌خواستیم.
    if not _CFG_READY:
        con.execute("""CREATE TABLE IF NOT EXISTS panel_config (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            body       TEXT NOT NULL,
            version    INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS panel_config_history (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            body    TEXT NOT NULL,
            note    TEXT,
            at      TEXT DEFAULT CURRENT_TIMESTAMP)""")
        globals()["_CFG_READY"] = True
    _CFG_LOCAL.con = con
    return con


#: کَشِ درون‌پردازه‌ای. نرمال‌سازی (ادغام با پیش‌فرض و اصلاح نوع‌ها)
#  گران‌ترین بخشِ خواندن است و در هر درخواست تکرار می‌شد.
_CFG_CACHE = {"version": None, "json": None}


def _cfg_migrate(con):
    """
    یک‌بار، از `config.json` به جدول.

    فایل **پاک نمی‌شود** — به‌عنوان پشتیبان می‌ماند. اگر جدول پر
    باشد، فایل اصلاً خوانده نمی‌شود.
    """
    stored = None
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
        except (json.JSONDecodeError, OSError):
            log.warning("config.json خوانده نشد؛ از پیش‌فرض شروع می‌کنیم",
                        exc_info=True)
    if not isinstance(stored, dict):
        stored = json.loads(json.dumps(DEFAULT_CONFIG))
    con.execute("INSERT OR REPLACE INTO panel_config (id, body, version) "
                "VALUES (1, ?, 1)",
                (json.dumps(stored, ensure_ascii=False),))
    log.info("تنظیمات از config.json به دیتابیس منتقل شد")
    return stored


def _cfg_raw():
    """بدنه‌ی خام و نسخه‌اش — بدون نرمال‌سازی."""
    con = _cfg_con()
    try:
        row = con.execute(
            "SELECT body, version FROM panel_config WHERE id = 1").fetchone()
        if row is None:
            con.execute("BEGIN IMMEDIATE")
            try:
                # ممکن است بین SELECT و این‌جا کسِ دیگری ساخته باشد
                again = con.execute(
                    "SELECT body, version FROM panel_config WHERE id = 1").fetchone()
                if again is not None:
                    con.execute("COMMIT")
                    return again["body"], int(again["version"])
                stored = _cfg_migrate(con)
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            return json.dumps(stored, ensure_ascii=False), 1

        body, ver = row["body"], int(row["version"])
        try:
            json.loads(body)
        except json.JSONDecodeError:
            # خرابی — ولی این‌بار بی‌صدا به پیش‌فرض برنمی‌گردیم.
            # تاریخچه دقیقاً برای همین هست: آخرین نسخه‌ی سالم.
            log.error("بدنه‌ی تنظیمات (نسخه %s) خراب است — "
                      "برمی‌گردیم به آخرین نسخه‌ی سالم", ver)
            for h in con.execute(
                    "SELECT body, version FROM panel_config_history "
                    "ORDER BY id DESC LIMIT 20"):
                try:
                    json.loads(h["body"])
                except json.JSONDecodeError:
                    continue
                log.error("نسخه‌ی %s از تاریخچه استفاده شد", h["version"])
                return h["body"], ver
            log.error("هیچ نسخه‌ی سالمی در تاریخچه نبود — پیش‌فرض")
            return json.dumps(DEFAULT_CONFIG, ensure_ascii=False), ver
        return body, ver
    finally:
        pass


def config_version():
    """نسخه‌ی فعلی — پنل همین را موقع ذخیره پس می‌فرستد."""
    con = _cfg_con()
    row = con.execute(
        "SELECT version FROM panel_config WHERE id = 1").fetchone()
    return int(row["version"]) if row else 0


def _normalize_config(stored):
    """
    ساختارِ کامل از روی چیزی که ذخیره شده.

    اگر فایلِ ذخیره‌شده از نسخه‌ی قدیمی‌تر باشد و فیلدهای جدید را
    نداشته باشد، از پیش‌فرض پر می‌شوند — بدون این، پنل هنگام
    دسترسی به فیلدِ ناموجود کرش می‌کند.
    """
    if not isinstance(stored, dict):
        stored = {}
    # ادغام: مقادیر ذخیره‌شده روی پیش‌فرض می‌نشینند،
    # ولی هر فیلدی که در ذخیره‌شده نباشد از پیش‌فرض می‌آید
    merged = deep_merge(json.loads(json.dumps(DEFAULT_CONFIG)), stored)

    # تضمین اینکه کلیدهای زبان FAQ همیشه وجود دارند
    faq = merged.setdefault("faq", {})
    # اگر faq خودش دیکشنری نباشد (فایل دستی خراب شده)، بازش می‌سازیم.
    # setdefault فقط وقتی کلید نباشد کمک می‌کند — نه وقتی مقدارش نوع اشتباه دارد.
    if not isinstance(faq, dict):
        faq = merged["faq"] = {}
    for lang in ("fa", "en", "tr", "ar"):
        if not isinstance(faq.get(lang), list):
            faq[lang] = []

    # تضمین اینکه کلیدهای پلتفرم اپ‌ها همیشه وجود دارند
    apps = merged.setdefault("downloadApps", {})
    if not isinstance(apps, dict):
        apps = merged["downloadApps"] = {}
    for os_key in ("android", "ios", "desktop"):
        if not isinstance(apps.get(os_key), list):
            apps[os_key] = []

    for key in ("videos", "resellers", "customPalettes"):
        if not isinstance(merged.get(key), list):
            merged[key] = []

    # دیکشنری‌های تودرتو — اگر نوعشان خراب باشد، فرانت‌اند روی
    # خواندن فیلدهایشان کرش می‌کند
    for key in ("advanced", "links", "banners", "popup", "referral", "bot"):
        if not isinstance(merged.get(key), dict):
            merged[key] = dict(DEFAULT_CONFIG.get(key) or {})

    # مهاجرت از سیستم قدیمی (theme واحد) به سیستم ترکیبی.
    # نکته: چون DEFAULT_CONFIG خودش template دارد، باید بررسی کنیم که
    # کاربر در فایل ذخیره‌شده‌اش template نداشته — نه در نسخه‌ی ادغام‌شده.
    if stored.get("theme") and not stored.get("template"):
        old_map = {
            "aurora": ("classic", "ocean"), "midnight": ("classic", "violet"),
            "emerald": ("classic", "forest"), "sunset": ("wallet", "ember"),
            "carbon": ("console", "slate"), "neon": ("console", "rose"),
            "ocean": ("analytics", "cyan"), "royal": ("wallet", "gold"),
            "minimal": ("classic", "slate"),
        }
        tpl, pal = old_map.get(stored.get("theme"), ("classic", "ocean"))
        merged["template"] = tpl
        merged["palette"] = pal
    merged.setdefault("template", "classic")
    merged.setdefault("palette", "ocean")
    return merged


def load_config():
    """تنظیمات، همیشه با ساختارِ کامل."""
    # اول فقط نسخه را بپرس. بدنه ممکن است چند کیلوبایت باشد و
    # کشیدن و پارس‌کردنش وقتی چیزی عوض نشده، دور ریختنِ کار است.
    ver = config_version()
    if ver and _CFG_CACHE["version"] == ver and _CFG_CACHE["json"] is not None:
        # کپیِ تازه می‌دهیم: فراخوان‌ها مقدار را دست‌کاری می‌کنند و
        # بعد ذخیره — اگر همان شیء برگردد، کشِ مشترک آلوده می‌شود
        return json.loads(_CFG_CACHE["json"])
    body, ver = _cfg_raw()
    merged = _normalize_config(json.loads(body))
    _CFG_CACHE["version"] = ver
    _CFG_CACHE["json"] = json.dumps(merged, ensure_ascii=False)
    return merged


def save_config(data, expected_version=None):
    """
    ذخیره‌ی اتمی، با تاریخچه.

    `expected_version` اگر داده شود و با نسخه‌ی فعلی نخواند، ذخیره
    رد می‌شود — این همان چیزی است که جلوی «دو تبِ باز، یکی کارِ
    دیگری را پاک می‌کند» را می‌گیرد. فراخوان‌های داخلی ندهند؛
    آن‌ها خودشان همین حالا خوانده‌اند.

    `BEGIN IMMEDIATE` عمدی است: نسخه را باید *پیش از* نوشتن ادعا
    کرد، وگرنه دو نویسنده هر دو نسخه‌ی N را می‌خوانند و هر دو
    N+1 می‌نویسند.
    """
    body = json.dumps(data, ensure_ascii=False)
    con = _cfg_con()
    con.execute("BEGIN IMMEDIATE")
    try:
        row = con.execute(
            "SELECT body, version FROM panel_config WHERE id = 1").fetchone()
        cur_ver = int(row["version"]) if row else 0
        if expected_version is not None and int(expected_version) != cur_ver:
            raise HTTPException(
                status_code=409,
                detail="این تنظیمات را جای دیگری عوض کرده‌اید — "
                       "صفحه را تازه کنید تا تغییراتِ آن‌جا از بین نرود")
        new_ver = cur_ver + 1
        if row is not None:
            # نسخه‌ی *قبلی* در تاریخچه می‌نشیند، چون برگشت یعنی
            # برگشت به همان
            con.execute(
                "INSERT INTO panel_config_history (version, body) VALUES (?,?)",
                (cur_ver, row["body"]))
            con.execute(
                "DELETE FROM panel_config_history WHERE id NOT IN "
                "(SELECT id FROM panel_config_history ORDER BY id DESC LIMIT ?)",
                (CONFIG_HISTORY_KEEP,))
        con.execute(
            "INSERT INTO panel_config (id, body, version, updated_at) "
            "VALUES (1, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(id) DO UPDATE SET body=excluded.body, "
            "version=excluded.version, updated_at=CURRENT_TIMESTAMP",
            (body, new_ver))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    _CFG_CACHE["version"] = None      # دفعه‌ی بعد دوباره بخوان
    return new_ver


def config_history(limit=20):
    """نسخه‌های قبلی — برای دیدن و برگشتن."""
    con = _cfg_con()
    rows = con.execute(
        "SELECT version, at, LENGTH(body) n FROM panel_config_history "
        "ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [{"version": int(r["version"]), "at": r["at"], "size": int(r["n"])}
            for r in rows]


def config_rollback(version):
    """
    برگشت به یک نسخه‌ی قبلی.

    خودِ برگشت هم یک ذخیره‌ی تازه است، نه پاک‌کردنِ تاریخچه — پس
    اگر اشتباه بود، از همان راه برمی‌گردد.
    """
    con = _cfg_con()
    row = con.execute(
        "SELECT body FROM panel_config_history WHERE version = ? "
        "ORDER BY id DESC LIMIT 1", (int(version),)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="این نسخه در تاریخچه نیست")
    try:
        data = json.loads(row["body"])
    except json.JSONDecodeError:
        raise HTTPException(status_code=422,
                            detail="این نسخه خوانا نیست و برگرداندنی نیست")
    save_config(data)
    return _normalize_config(data)


# ═══════════════════════════════════════════════════════════
#  سدّ حدس‌زدن رمز
#
#  کل این سامانه پشت یک رمز است: پنل، اطلاعات مشتری‌ها، رمز x-ui،
#  توکن ربات. تا امروز هیچ چیزی جلوی حدس‌زدنِ پشت‌سرهم را نمی‌گرفت —
#  نه در /api/login و نه در هیچ‌کدام از مسیرهای مدیریتی، که همان رمز
#  را در هدر می‌گیرند و به همان اندازه برای حدس‌زدن در دسترس‌اند.
#
#  ماژول intrusion حمله‌ی SSH را می‌بیند و گزارش می‌دهد؛ درِ خودِ پنل
#  هیچ نگهبانی نداشت.
# ═══════════════════════════════════════════════════════════

#: چند تلاش ناموفق، در چه بازه‌ای، و چقدر قفل
AUTH_MAX_FAILS = 10
AUTH_WINDOW = 300        # ثانیه
AUTH_LOCK = 900          # ثانیه
#: سقف آی‌پی‌های زیر نظر — تا کسی با آی‌پی جعلی حافظه را پر نکند
AUTH_TRACK_MAX = 2048

_auth_fails = {}
_auth_ip = _contextvars.ContextVar("nexora_client_ip", default="?")


def _client_ip(request):
    """
    آی‌پی واقعی درخواست‌دهنده.

    پشت nginx همه‌ی درخواست‌ها از 127.0.0.1 می‌آیند، پس بدون
    X-Forwarded-For همه در یک سطل می‌افتند و یک مهاجم می‌تواند مدیر
    را بیرون بیندازد. ولی این هدر را فقط وقتی باور می‌کنیم که خودِ
    همسایه لوپ‌بک یا شبکه‌ی خصوصی باشد — یعنی nginx خودمان. از
    اینترنت هر کسی می‌تواند هر چیزی در آن بنویسد.
    """
    peer = ""
    try:
        peer = (request.client.host or "") if request.client else ""
    except Exception:
        peer = ""

    trusted = False
    try:
        ip = _ipaddress.ip_address(peer)
        trusted = ip.is_loopback or ip.is_private
    except ValueError:
        trusted = False

    if trusted:
        # nginx نصب فقط X-Real-IP می‌فرستد (install.sh). تا ۱.۱۱۱ فقط
        # X-Forwarded-For خوانده می‌شد، پس پشتِ nginx آی‌پیِ همه
        # 127.0.0.1 بود: قفلِ ورودِ همه در یک سطل، و آی‌پیِ نودها هرگز
        # ثبت نمی‌شد.
        for h in ("x-forwarded-for", "x-real-ip"):
            first = (request.headers.get(h) or "").split(",")[0].strip()
            if first:
                try:
                    _ipaddress.ip_address(first)
                    return first
                except ValueError:
                    pass
    return peer or "?"


@app.middleware("http")
async def _remember_client_ip(request: Request, call_next):
    """
    آی‌پی را برای همین درخواست کنار می‌گذارد.

    check_auth از ۱۱۴ جا با همان یک آرگومان صدا زده می‌شود؛ عوض‌کردن
    امضایش یعنی دست‌زدن به همه‌ی آن‌ها. این‌طور نگهبان بدون تغییر
    هیچ صداکننده‌ای به آی‌پی می‌رسد.
    """
    token = _auth_ip.set(_client_ip(request))
    try:
        return await call_next(request)
    finally:
        _auth_ip.reset(token)


# ═══════════════════════════════════════════════════════════
#  نشانیِ مخفیِ پنلِ مدیر
#
#  برگه: docs/specs/2026-09-28-admin-path-and-aff-payouts.md
#
#  پنلِ مدیر روی همان دامنه‌ای است که مینی‌اپ (/app)، پنلِ نماینده (/r/…) و
#  همکار (/aff) رویش‌اند، و هر مسیرِ دیگری — از جمله «/» — صفحه‌ی ورودِ
#  مدیر را باز می‌کرد. هر نماینده و همکاری که نشانیِ خودش را داشت، با
#  پاک‌کردنِ مسیر به درِ پنلِ مالک می‌رسید (مالک: «این باعث خطر می‌شود»).
#
#  حالا هر `/api/admin/*` و `/api/login` بدونِ هدرِ `X-Admin-Path`ِ درست
#  همان 404 ای را می‌گیرد که یک مسیرِ ناموجود. **استثنای محلی ندارد**:
#  تشخیصِ «درخواستِ محلی» به هدرهای nginx تکیه می‌کرد و nginxِ نصب‌های
#  قدیمی همه‌شان را نمی‌فرستد — یعنی درست همان‌جا که لازم است، باز می‌ماند.
#  هیچ ابزارِ محلی هم /api/admin را از راهِ HTTP صدا نمی‌زند (تست‌ها تابع
#  را مستقیم صدا می‌زنند). رمز و قفلِ ورود سرِ جایشان‌اند؛ این لایه‌ی اضافه است.
# ═══════════════════════════════════════════════════════════
ADMIN_PATH_FILE = Path(os.getenv("ADMIN_PATH_FILE", str(CONFIG_PATH.parent / "admin_path.json")))
_ADMIN_PATH_RE = _re.compile(r"^[a-z0-9_-]{8,64}$")
#: الفبای بی‌ابهام — نشانی را گاهی از روی گوشی تایپ می‌کنند (بی l/1 و o/0)
_ADMIN_PATH_ABC = "abcdefghijkmnpqrstuvwxyz23456789"
_ADMIN_PATH = {"v": None, "fresh": False}
_ADMIN_PATH_LOCK = _threading.Lock()


def _new_admin_path():
    return "".join(_secrets.choice(_ADMIN_PATH_ABC) for _ in range(20))


def _write_admin_path(v):
    ADMIN_PATH_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ADMIN_PATH_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"path": v}), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError as e:
        log.debug("chmod admin_path: %s", e)      # ویندوز؛ روی سرور همیشه موفق است
    os.replace(tmp, ADMIN_PATH_FILE)


def admin_path():
    """
    نشانیِ مخفی — از `NEXORA_ADMIN_PATH` یا `data/admin_path.json`، و اگر
    نیست همین حالا ساخته می‌شود. ساختنِ بارِ اول `fresh` را روشن می‌کند تا
    ربات آن را برای مالک بفرستد (`_announce_admin_path`).
    """
    env = (os.getenv("NEXORA_ADMIN_PATH") or "").strip().strip("/").lower()
    if env and _ADMIN_PATH_RE.match(env):
        return env
    if _ADMIN_PATH["v"]:
        return _ADMIN_PATH["v"]
    with _ADMIN_PATH_LOCK:
        if _ADMIN_PATH["v"]:
            return _ADMIN_PATH["v"]
        v = ""
        try:
            if ADMIN_PATH_FILE.exists():
                v = str(json.loads(ADMIN_PATH_FILE.read_text(encoding="utf-8")).get("path") or "")
        except (OSError, ValueError):
            # فایلِ خراب نباید پنل را برای همیشه ببندد — ولی بی‌صدا هم نه
            log.warning("admin_path.json خوانده نشد؛ نشانیِ تازه ساخته می‌شود", exc_info=True)
        if not _ADMIN_PATH_RE.match(v):
            v = _new_admin_path()
            _write_admin_path(v)
            _ADMIN_PATH["fresh"] = True
            log.warning("نشانیِ تازه‌ی پنلِ مدیر ساخته شد — «nexora url» روی سرور نشانش می‌دهد")
        _ADMIN_PATH["v"] = v
        return v


def rotate_admin_path():
    v = _new_admin_path()
    with _ADMIN_PATH_LOCK:
        _write_admin_path(v)
        _ADMIN_PATH["v"] = v
    return v


def _panel_origin():
    """«https://دامنه» از همان فایلی که بیلد می‌خواند (install.sh)؛ وگرنه ""."""
    try:
        env = Path(__file__).resolve().parent.parent / "frontend" / ".env"
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("VITE_API_URL="):
                v = line.split("=", 1)[1].strip().rstrip("/")
                return v if v.startswith("https://") else ""
    except OSError as e:
        log.debug("frontend/.env خوانده نشد: %s", e)
    return ""


def admin_url():
    o = _panel_origin()
    return f"{o}/{admin_path()}/" if o else ""


def _admin_path_ok(got: str) -> bool:
    got = (got or "").strip().strip("/").lower()
    want = admin_path()
    return bool(got) and _hmac.compare_digest(got.encode("utf-8"), want.encode("utf-8"))


def _is_admin_api(path: str) -> bool:
    return path == "/api/login" or path == "/api/admin" or path.startswith("/api/admin/")


@app.middleware("http")
async def _admin_path_gate(request: Request, call_next):
    if _is_admin_api(request.url.path) and request.method != "OPTIONS":
        if not _admin_path_ok(request.headers.get("x-admin-path")):
            # همان پاسخِ مسیرِ ناموجود — نه 401، که بگوید «این‌جا چیزی هست»
            return JSONResponse({"detail": "Not Found"}, status_code=404)
    return await call_next(request)


def _auth_locked(ip):
    """اگر قفل است، چند ثانیه‌ی دیگر باز می‌شود؛ وگرنه صفر."""
    rec = _auth_fails.get(ip)
    if not rec:
        return 0
    if rec.get("until", 0) > _time.time():
        return int(rec["until"] - _time.time()) + 1
    return 0


def _auth_failed(ip):
    now = _time.time()
    rec = _auth_fails.get(ip)
    if not rec or now - rec.get("first", now) > AUTH_WINDOW:
        rec = {"first": now, "n": 0, "until": 0}
    rec["n"] += 1
    if rec["n"] >= AUTH_MAX_FAILS:
        rec["until"] = now + AUTH_LOCK
    if len(_auth_fails) >= AUTH_TRACK_MAX and ip not in _auth_fails:
        # قدیمی‌ترین را بیرون می‌اندازیم تا فهرست بی‌مرز رشد نکند
        try:
            oldest = min(_auth_fails, key=lambda k: _auth_fails[k].get("first", 0))
            _auth_fails.pop(oldest, None)
        except ValueError:
            pass
    _auth_fails[ip] = rec
    return rec


def _auth_ok(ip):
    """ورود درست یعنی پرونده بسته می‌شود."""
    _auth_fails.pop(ip, None)


def check_auth(x_admin_password: str = Header(...)):
    ip = _auth_ip.get()

    wait = _auth_locked(ip)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"تلاش‌های ناموفق زیاد بود. {wait // 60 + 1} دقیقه‌ی دیگر "
                   "دوباره امتحان کنید.",
            headers={"Retry-After": str(wait)})

    # مقایسه‌ی زمان‌ثابت: مقایسه‌ی معمولی روی اولین بایتِ متفاوت
    # برمی‌گردد و همان اختلاف، هرچند کوچک، رمز را بایت‌به‌بایت لو
    # می‌دهد.
    # بایت مقایسه می‌کنیم، نه رشته: compare_digest روی رشته‌ی غیر
    # اسکی TypeError می‌دهد — یعنی یک رمز فارسی کل پنل را با خطای
    # ۵۰۰ می‌بست، نه فقط ورود را.
    if x_admin_password == _INTERNAL_PW:
        return True
    if not verify_password(x_admin_password):
        rec = _auth_failed(ip)
        left = AUTH_MAX_FAILS - rec["n"]
        detail = "رمز عبور نادرست است"
        if 0 < left <= 3:
            detail += f" — {left} تلاش دیگر تا قفل‌شدن موقت"
        raise HTTPException(status_code=401, detail=detail)

    _auth_ok(ip)


#: کلیدهایی که به مرورگر مشتری فرستاده می‌شوند.
#
#  این عمداً فهرستِ «مجاز» است، نه فهرستِ «حذف کن».
#
#  قبلاً برعکس بود: هر چیزی جز resellers و bot عمومی می‌شد. یعنی هر
#  کلیدِ تازه‌ای که به تنظیمات اضافه می‌شد، خودبه‌خود روی صفحه‌ی
#  عمومی می‌نشست — maintenance (ساعت ری‌استارت سرور، آستانه‌ی شلوغی،
#  آخرین خطا) دقیقاً همین‌طور بیرون می‌رفت.
#
#  با فهرست مجاز، جهتِ اشتباه بی‌خطر است: فراموش‌کردن یک کلید یعنی
#  قابلیتی نمایش داده نمی‌شود، نه اینکه چیزی درز کند. اگر قابلیت
#  تازه‌ای لازم دارد روی صفحه دیده شود، همین‌جا اضافه‌اش کنید.
PUBLIC_CONFIG_KEYS = {
    "downloadApps", "faq", "banners", "referral", "links",
    "videoTutorialUrl", "videos", "advanced", "popup",
    "template", "palette", "customPalettes",
}


@app.get("/api/public/config")
def get_public_config(request: Request, response: Response, email: str = None, host: str = None):
    """
    تنظیمات را برمی‌گرداند. اگر مشتری متعلق به یک واسطه باشد،
    تنظیمات همان واسطه (ادغام‌شده روی تنظیمات پایه) برگردانده می‌شود.

    تشخیص واسطه:
      - پارامتر host یا هدر Origin/Referer (تطبیق دامنه)
      - پارامتر email (تطبیق پیشوند ایمیل کلاینت)
    """
    # جلوگیری از کش شدن توسط مرورگر، کلودفلر یا هر CDN دیگری.
    # بدون این، مشتری ممکن است ساعت‌ها تنظیمات قدیمی را ببیند.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    cfg = load_config()

    # اگر host به‌صراحت داده نشده، از Origin یا Referer استخراج می‌کنیم
    if not host:
        origin = request.headers.get("origin") or request.headers.get("referer") or ""
        if origin:
            host = origin.replace("https://", "").replace("http://", "").split("/")[0]

    reseller = find_reseller(cfg, email=email, host=host)

    # فقط چیزهایی که صفحه‌ی اشتراک واقعاً لازم دارد.
    public_cfg = {k: v for k, v in cfg.items() if k in PUBLIC_CONFIG_KEYS}

    if reseller:
        # overrides هم از همان صافی رد می‌شود. این‌ها را مدیر می‌نویسد
        # نه مهاجم، ولی یک کلیدِ اشتباهی در overrides نباید بتواند
        # چیزی را که بالا حذف شده دوباره برگرداند.
        merged = deep_merge(public_cfg, reseller.get("overrides", {}))
        public_cfg = {k: v for k, v in merged.items()
                      if k in PUBLIC_CONFIG_KEYS}
        public_cfg["_resellerId"] = reseller.get("id")

    # قالب فعال را به‌صورت کامل ضمیمه می‌کنیم تا صفحه‌ی اشتراک
    # بتواند مستقیم متغیرهای رنگ و چیدمان را اعمال کند.
    # واسطه می‌تواند قالب متفاوتی داشته باشد (theme در overrides).
    # ترکیب ساختار و رنگ — واسطه می‌تواند هر دو را متفاوت داشته باشد
    public_cfg["_theme"] = resolve_theme(
        cfg, public_cfg.get("template"), public_cfg.get("palette")
    )

    return public_cfg


@app.get("/api/admin/themes")
def list_themes(x_admin_password: str = Header(...)):
    """ساختارها و پالت‌ها برای انتخاب در پنل."""
    check_auth(x_admin_password)
    cfg = load_config()
    return {
        "currentTemplate": cfg.get("template", "classic"),
        "currentPalette": cfg.get("palette", "ocean"),
        # Only classic is free; the picker marks the rest and says why.
        "templatesLocked": not _pro_templates_ok(),
        "templatesWhy": "" if _pro_templates_ok() else LIC.denial("subpage_templates", LIC.status()),
        "templates": TEMPLATES,
        "palettes": PALETTES,
        "customPalettes": cfg.get("customPalettes", []),
    }


@app.post("/api/admin/themes")
def pick_theme(payload: dict, x_admin_password: str = Header(...)):
    """
    انتخابِ چیدمان و پالت — از داخلِ پیش‌نمایش.

    فقط همین دو کلید. بقیه‌ی تنظیمات دست‌نخورده می‌مانند، چون این
    مسیر آن‌ها را نمی‌خواند و نمی‌نویسد.

    هر دو از فهرستِ مجاز رد می‌شوند: شناسه‌ی ناشناس یعنی صفحه‌ی
    مشتری کلاسِ `tpl-<چیزی>` بگیرد که هیچ CSSای ندارد — یعنی
    چیدمانِ شکسته، بی‌صدا.
    """
    check_auth(x_admin_password)
    p = payload or {}
    cfg = load_config()

    tpl = str(p.get("template") or "").strip()
    pal = str(p.get("palette") or "").strip()

    if tpl:
        if not any(t["id"] == tpl for t in TEMPLATES):
            raise HTTPException(status_code=400,
                                detail=f"چیدمان «{tpl}» شناخته نشد")
        if tpl != "classic" and not _pro_templates_ok():
            raise HTTPException(status_code=403,
                                detail=LIC.denial("subpage_templates", LIC.status()),
                                headers={"X-Nexora-Pro": "subpage_templates"})
        cfg["template"] = tpl

    if pal:
        known = ({p2["id"] for p2 in PALETTES}
                 | {c.get("id") for c in cfg.get("customPalettes", [])})
        if pal not in known:
            raise HTTPException(status_code=400,
                                detail=f"پالت «{pal}» شناخته نشد")
        cfg["palette"] = pal

    if not tpl and not pal:
        raise HTTPException(status_code=400, detail="چیزی برای تغییر نیست")

    save_config(cfg)
    return {"ok": True, "template": cfg.get("template"),
            "palette": cfg.get("palette")}


@app.post("/api/admin/palettes")
def add_custom_palette(payload: dict, x_admin_password: str = Header(...)):
    """افزودن پالت رنگی سفارشی."""
    check_auth(x_admin_password)
    cfg = load_config()

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="نام پالت الزامی است")

    customs = cfg.setdefault("customPalettes", [])
    if len(customs) >= 20:
        raise HTTPException(status_code=400, detail="حداکثر ۲۰ پالت سفارشی مجاز است")

    pal_id = payload.get("id") or f"pal-{int(datetime.now().timestamp())}"
    if any(p.get("id") == pal_id for p in customs) or any(p["id"] == pal_id for p in PALETTES):
        raise HTTPException(status_code=400, detail="پالتی با این شناسه وجود دارد")

    allowed = {"accent", "accent2", "bg", "surface", "surfaceAlt", "border", "text", "textMuted"}
    raw = payload.get("vars") or {}
    pal = {
        "id": pal_id,
        "name": name,
        "fa": (payload.get("fa") or name).strip(),
        "builtin": False,
        "vars": {k: str(v)[:60] for k, v in raw.items() if k in allowed},
    }

    customs.append(pal)
    save_config(cfg)
    return {"ok": True, "palette": pal}


@app.delete("/api/admin/palettes/{palette_id}")
def delete_custom_palette(palette_id: str, x_admin_password: str = Header(...)):
    """حذف پالت سفارشی. پالت‌های داخلی حذف نمی‌شوند."""
    check_auth(x_admin_password)
    cfg = load_config()

    customs = cfg.get("customPalettes", [])
    if not any(p.get("id") == palette_id for p in customs):
        raise HTTPException(status_code=404, detail="پالت پیدا نشد")

    cfg["customPalettes"] = [p for p in customs if p.get("id") != palette_id]

    if cfg.get("palette") == palette_id:
        cfg["palette"] = "ocean"
    for r in cfg.get("resellers", []):
        if r.get("overrides", {}).get("palette") == palette_id:
            r["overrides"].pop("palette", None)

    save_config(cfg)
    return {"ok": True}


@app.get("/api/admin/ping")
def admin_ping():
    """
    «این نشانی درست است؟» — بی رمز. خودِ پاسخ یعنی هدرِ نشانی درست بود
    (وگرنه `_admin_path_gate` پیش از این‌جا 404 داده). رابط از این می‌فهمد
    صفحه‌ی ورود را نشان بدهد یا «پیدا نشد» را.

    `version`: the UI compares it with the version it was built from and
    says so when an update left the old UI in place (task 10). Only callers
    that already know the secret admin path get here.
    """
    return {"ok": True, "version": _panel_version()}


@app.get("/api/admin/panel-path")
def admin_panel_path(x_admin_password: str = Header(...)):
    check_auth(x_admin_password)
    return {"path": admin_path(), "url": admin_url()}


@app.post("/api/admin/panel-path/rotate")
def admin_panel_path_rotate(x_admin_password: str = Header(...)):
    """
    نشانیِ تازه — مثلاً وقتی قبلی لو رفته. نشانیِ قبلی همین لحظه 404 می‌شود؛
    رابط بعد از این به نشانیِ تازه می‌رود.
    """
    check_auth(x_admin_password)
    v = rotate_admin_path()
    log.warning("نشانیِ پنلِ مدیر عوض شد")
    return {"path": v, "url": admin_url()}


@app.post("/api/login")
def login(payload: dict):
    # همان نگهبان — وگرنه بستن یک در و باز گذاشتن آن یکی.
    check_auth((payload or {}).get("password") or "")
    return {"ok": True}


def _panel_host(request):
    """
    دامنه‌ی پنل، فقط وقتی مطمئن باشیم روی https باز شده. وگرنه "" .

    چرا دو منبع و نه فقط هدر `X-Forwarded-Proto`:

    نسخه‌ی اول فقط آن هدر را می‌خواند، و روی نصب‌های واقعی **هیچ‌وقت
    درست نشد** — چون بلوک nginx خودمان آن را جلو نمی‌فرستاد. TLS روی
    nginx تمام می‌شد و درخواست به uvicorn به شکل http می‌رسید، پس
    شرط همیشه رد می‌شد و آدرس مینی‌اپ هرگز ثبت نمی‌شد. یعنی قابلیتی
    که «بدون تنظیم کار می‌کند» اعلام شده بود، روی سرور کار نمی‌کرد و
    هیچ‌جا هم نمی‌گفت چرا. (بلوک nginx هم در همین نسخه اصلاح شد، ولی
    نصب‌های موجود فایل قدیمی را دارند.)

    `Referer` را خودِ مرورگر می‌گذارد و نوار آدرسِ همان پنل است — یعنی
    دقیقاً همان چیزی که می‌خواهیم بدانیم، بدون وابستگی به تنظیم nginx.
    این مسیر رمز مدیر می‌خواهد، پس فقط مرورگرِ خودِ مالک به این‌جا
    می‌رسد و سطح اعتماد همان قبلی است.
    """
    def _clean(h):
        h = (h or "").split(",")[0].strip()
        return "" if (not h or any(c in h for c in " /\\?#@")) else h

    # ۱) نوار آدرسِ خودِ مرورگر
    for key in ("referer", "origin"):
        raw = (request.headers.get(key) or "").strip()
        if not raw.lower().startswith("https://"):
            continue
        host = _clean(raw[len("https://"):].split("/")[0])
        if host:
            return host

    # ۲) هدر پروکسی — برای نصب‌هایی که تنظیمش دارند
    if (request.headers.get("x-forwarded-proto") or "").strip().lower() == "https":
        return _clean(request.headers.get("host"))

    # بدون https آدرسی نمی‌سازیم: تلگرام خودش ردش می‌کند و
    # ثبت‌کردنش فقط یک مقدارِ مرده به جا می‌گذارد
    return ""


def _learn_panel_origin(request):
    """
    دامنه‌ی خودِ پنل را یک‌بار یاد می‌گیرد و آدرس مینی‌اپ را می‌سازد.

    چرا این‌جا: مینی‌اپ از همان `frontend/dist` سرو می‌شود که پنل، و
    nginx هم `try_files` دارد — پس `https://<دامنه‌ی پنل>/app` بدون
    هیچ تنظیم تازه‌ای بالا می‌آید. تنها چیزی که کم بود، خودِ دامنه
    بود؛ و این‌جا در هدر Host نشسته است.

    چرا از مسیر مدیر و نه مسیر عمومی: هدر Host را فرستنده تعیین
    می‌کند. روی یک مسیر عمومی، هر کسی می‌توانست دامنه‌ی دلخواهش را
    ثبت کند و مینی‌اپِ مشتری‌ها را به صفحه‌ی خودش ببرد. این مسیر رمز
    مدیر می‌خواهد، پس فقط مرورگرِ خودِ مالک به این‌جا می‌رسد.

    یک‌بار نوشته می‌شود و بعد دست نمی‌خورد — تا اگر مالک آدرس دیگری
    گذاشت، بازکردنِ دوباره‌ی پنل رویش ننویسد.
    """
    try:
        host = _panel_host(request)
        if not host:
            return

        con = _bot_rw()
        try:
            # **همه‌ی** مستاجرها، نه فقط ریشه.
            #
            # تا امروز `WHERE parent_id IS NULL … LIMIT 1` بود، پس
            # نماینده هیچ‌وقت آدرس نمی‌گرفت و دکمه‌ی مینی‌اپ در
            # رباتش ظاهر نمی‌شد. یعنی نماینده اصلاً مینی‌اپ نداشت.
            #
            # آدرس برای همه یکی است (`/app` روی همین دامنه) و
            # مستاجر از روی **امضای توکنِ ربات** تشخیص داده می‌شود،
            # نه از روی آدرس — پس مشتریِ هر نماینده فروشگاهِ خودِ او
            # را می‌بیند.
            # همه‌ی مستاجرها، حتی آن‌که هنوز ربات ندارد: آدرس
            # بدونِ ربات بی‌ضرر است، و لحظه‌ای که ربات وصل شود دکمه
            # همان‌جا هست بدونِ بازکردنِ دوباره‌ی پنل.
            rows = con.execute("SELECT id, settings FROM tenants").fetchall()
            wrote = 0
            for row in rows:
                try:
                    st = json.loads(row["settings"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    st = None
                if not isinstance(st, dict):
                    # ناخوانا: نوشتنِ {miniapp_url} رویش داده‌ی قابلِ‌نجات را پاک می‌کرد
                    log.warning("tenant %s settings unreadable — miniapp_url not set", row["id"])
                    continue
                if str(st.get("miniapp_url") or "").strip():
                    continue            # خودش گذاشته — دست نمی‌زنیم
                st["miniapp_url"] = f"https://{host}/app"
                con.execute("UPDATE tenants SET settings=? WHERE id=?",
                            (json.dumps(st, ensure_ascii=False), row["id"]))
                wrote += 1
            if wrote:
                con.commit()
                log.info("آدرس مینی‌اپ برای %s مستاجر ثبت شد: https://%s/app",
                         wrote, host)
        finally:
            con.close()
    except Exception:
        # یادگرفتنِ دامنه راحتی است، نه شرطِ بازشدنِ پنل
        log.debug("ثبت خودکار آدرس مینی‌اپ ناموفق", exc_info=True)


@app.get("/api/admin/config")
def get_admin_config(request: Request, response: Response,
                     x_admin_password: str = Header(...)):
    """
    تنظیمات، به‌علاوه‌ی نسخه‌اش در هدر.

    چرا در هدر و نه داخل خودِ سند: پنل همین سند را می‌گیرد، دست‌کاری
    می‌کند و عیناً پس می‌فرستد. هر کلیدی که این‌جا اضافه شود، آن‌جا
    ذخیره می‌شود و برای همیشه در تنظیمات می‌ماند.
    """
    check_auth(x_admin_password)
    _learn_panel_origin(request)
    cfg = load_config()
    response.headers["X-Config-Version"] = str(config_version())
    return cfg


@app.put("/api/admin/config")
def update_config(payload: dict, x_admin_password: str = Header(...),
                  x_config_version: str = Header(None)):
    """
    ذخیره — و اگر جای دیگری عوض شده باشد، رد.

    بدون این، دو تبِ باز یعنی هر کدام که دیرتر ذخیره کند کارِ
    دیگری را بی‌صدا پاک می‌کند. پنل نسخه‌ای را که گرفته پس
    می‌فرستد؛ اگر نخواند، خطای روشن می‌گیرد نه پاک‌شدنِ خاموش.
    """
    check_auth(x_admin_password)
    # کلِ تنظیمات جایگزین می‌شود، پس چیزی که شبیهِ تنظیمات نیست رد می‌شود.
    # صفحه‌ی «تنظیماتِ حسابداری» تنظیمات را با `r.json()` بی‌سنجش می‌خواند؛
    # اگر آن خواندن ۵۰۰ می‌گرفت، `{detail: …}` با یک مسیر به‌جای کلِ
    # تنظیمات ذخیره می‌شد. نیمی از کلیدهای سطحِ اول کف است.
    _known = set(payload or {}) & set(DEFAULT_CONFIG)
    if len(_known) < len(DEFAULT_CONFIG) // 2:
        raise HTTPException(
            status_code=400,
            detail=f"تنظیماتِ ناقص — فقط {_fnum(len(_known))} از {_fnum(len(DEFAULT_CONFIG))} بخش آمده؛ ذخیره نشد")
    want = None
    if x_config_version not in (None, ""):
        try:
            want = int(x_config_version)
        except ValueError:
            want = None
    ver = save_config(payload, expected_version=want)
    return {"ok": True, "version": ver}


@app.get("/api/admin/config/history")
def get_config_history(x_admin_password: str = Header(...)):
    """نسخه‌های قبلیِ تنظیمات."""
    check_auth(x_admin_password)
    return {"current": config_version(), "versions": config_history()}


@app.post("/api/admin/config/rollback/{version}")
def post_config_rollback(version: int, x_admin_password: str = Header(...)):
    """برگشت به یک نسخه‌ی قبلی."""
    check_auth(x_admin_password)
    cfg = config_rollback(version)
    return {"ok": True, "version": config_version(), "config": cfg}


@app.post("/api/admin/reset-defaults")
def reset_defaults(x_admin_password: str = Header(...)):
    check_auth(x_admin_password)
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG


@app.get("/api/admin/stats")
def get_stats(x_admin_password: str = Header(...)):
    """آمار خلاصه برای نمایش در داشبورد."""
    check_auth(x_admin_password)
    cfg = load_config()

    apps = cfg.get("downloadApps", {})
    faq = cfg.get("faq", {})
    videos = cfg.get("videos", [])
    advanced = cfg.get("advanced", {})

    apps_count = sum(len(v or []) for v in apps.values())
    faq_count = sum(len(v or []) for v in faq.values())

    # شمارش اپ‌های پیشنهادی تعیین‌شده
    recommended = {}
    for os_key, lst in apps.items():
        rec = next((a for a in (lst or []) if a.get("recommended")), None)
        recommended[os_key] = rec.get("name") if rec else None

    active_features = {
        "banners": cfg.get("banners", {}).get("enabled", False),
        "referral": cfg.get("referral", {}).get("enabled", False),
        "faqSection": advanced.get("showFaqSection", True),
        "notificationPopup": advanced.get("showNotificationPopup", True),
        "brandStrip": advanced.get("showBrandStrip", True),
    }

    return {
        "appsCount": apps_count,
        "faqCount": faq_count,
        "videosCount": len(videos),
        "appsPerPlatform": {k: len(v or []) for k, v in apps.items()},
        "faqPerLanguage": {k: len(v or []) for k, v in faq.items()},
        "recommendedApps": recommended,
        "activeFeatures": active_features,
        "activeFeaturesCount": sum(1 for v in active_features.values() if v),
    }


#: قالب‌هایی که صفحه‌ی اشتراک می‌شناسد. فهرستِ مجاز است، نه ممنوع:
#: مقدار مستقیم داخلِ صفحه تزریق می‌شود.
PREVIEW_TEMPLATES = ("classic", "analytics", "wallet", "console")


def render_preview_html(raw: str, template: str = "",
                        palette: str = "") -> str:
    """
    فایل قالب را برای پیش‌نمایش آماده می‌کند.

    چون فایل یک قالب Go template است (که فقط پنل 3x-ui می‌تواند رندرش کند)،
    برای نمایش در پنل مدیریت، متغیرهای {{ .xxx }} را با داده‌ی نمونه
    جایگزین می‌کنیم — دقیقاً همان کاری که پنل واقعی با داده‌ی واقعی می‌کند.
    """

    now = int(datetime.now().timestamp())
    sample = {
        "sId": "preview-sample-id",
        "enabled": "true",
        "expire": str(now + 15 * 86400),
        "downloadByte": "3221225472",
        "uploadByte": "536870912",
        "totalByte": "32212254720",
        "subUrl": "https://example.com/sub/preview-sample",
        "subJsonUrl": "https://example.com/json/preview-sample",
        "subClashUrl": "https://example.com/clash/preview-sample",
        "subTitle": "NexoraVpn",
        "subSupportUrl": "",
        "datepicker": "gregorian",
        "lastOnline": str((now - 300) * 1000),
        "download": "3.0 GB",
        "upload": "512 MB",
        "total": "30 GB",
        "used": "3.5 GB",
        "remained": "26.5 GB",
    }

    out = raw

    # ۱. حلقه‌ی emails
    # نکته: از lambda استفاده می‌کنیم چون رشته‌ی جایگزین ممکن است شامل
    # کاراکترهایی مثل \u باشد که re.sub آن‌ها را به‌عنوان escape تفسیر می‌کند.
    out = _re.sub(
        r"\[\s*\{\{\s*range\s+\$i,\s*\$e\s*:=\s*\.emails\s*\}\}.*?\{\{\s*end\s*\}\}\s*\]",
        lambda m: '["preview@nexora"]',
        out, flags=_re.DOTALL,
    )

    # ۲. حلقه‌ی links
    sample_links = (
        '["vless://11111111-2222-3333-4444-555555555555@example.com:443'
        '?type=ws&security=tls&path=%2Fpreview#FR-Nexora-Sample-1",'
        '"vless://11111111-2222-3333-4444-555555555555@example.com:2053'
        '?type=ws&security=tls&path=%2Fpreview#TR-Nexora-Sample-2"]'
    )
    out = _re.sub(
        r"\[\s*\{\{\s*range\s+\$i,\s*\$l\s*:=\s*\.links\s*\}\}.*?\{\{\s*end\s*\}\}\s*\]",
        lambda m: sample_links,
        out, flags=_re.DOTALL,
    )

    # ۳. متغیرهای ساده
    for key, val in sample.items():
        out = _re.sub(r"\{\{\s*\." + key + r"\s*\}\}", lambda m, v=val: v, out)

    # ۴. هر متغیر باقی‌مانده‌ی ناشناخته → رشته‌ی خالی (تا JS نشکند)
    out = _re.sub(r"\{\{[^}]*\}\}", lambda m: "", out)

    # ۵. بازنویسیِ قالب/پالت — فقط برای همین نما.
    #
    #  فهرستِ مجاز، نه هر رشته‌ای: این مقدار مستقیم داخلِ صفحه
    #  تزریق می‌شود و ورودیِ کنترل‌نشده یعنی تزریقِ اسکریپت. قاعده‌ی
    #  خودِ مخزن: فهرستِ مجاز، نه فهرستِ ممنوع.
    tpl = template if template in PREVIEW_TEMPLATES else ""
    pal = palette if _re.fullmatch(r"[a-z0-9_-]{1,32}", palette or "") else ""
    if tpl or pal:
        # `resolve_theme` همان تابعی است که مسیرِ واقعی صدا می‌زند،
        # پس پیش‌نمایش و صفحه‌ی مشتری هیچ‌وقت از هم دور نمی‌افتند.
        # نگاشتِ دومِ «نامِ پالت → رنگ‌ها» دقیقاً همان الگویی است که
        # این مخزن بارها بابتش باگ خورده.
        try:
            _cfg = load_config()
            _th = resolve_theme(_cfg, tpl or None, pal or None)
            forced = {"template": _th.get("template") or tpl,
                      "vars": _th.get("vars") or {}}
        except Exception:
            log.debug("حلِ پوسته‌ی پیش‌نمایش ناموفق", exc_info=True)
            forced = {"template": tpl} if tpl else {}
        inject = ("<script>window.NEXORA_FORCE_THEME = "
                  + json.dumps(forced, ensure_ascii=False) + ";</script>")
        # پیش از هر اسکریپتِ دیگری، وگرنه قالب یک‌بار با مقدارِ
        # ذخیره‌شده اعمال می‌شود و پرش دیده می‌شود
        if "</head>" in out:
            out = out.replace("</head>", inject + "</head>", 1)
        else:
            out = inject + out

    return out


@app.get("/api/preview", response_class=HTMLResponse)
def preview_subpage(template: str = "", palette: str = ""):
    """
    صفحه‌ی اشتراک را با داده‌ی نمونه برای مشاهده در پنل مدیریت سرو
    می‌کند.

    `template` و `palette` **فقط همین نما** را عوض می‌کنند و هیچ‌چیز
    ذخیره نمی‌شود. بدونِ این، مقایسه‌ی چهار قالب یعنی چهار بار
    ذخیره روی تنظیماتِ واقعیِ مشتری‌ها و چهار بار رفت‌وبرگشت.
    """
    html_path = Path(os.getenv("SUBPAGE_HTML_PATH", "../sub-page-index.html"))
    if not html_path.exists():
        return HTMLResponse(
            "<div style='font-family:sans-serif;padding:40px;text-align:center;"
            "color:#888;background:#06090f;height:100vh'>فایل قالب پیدا نشد.<br>"
            f"مسیر مورد انتظار: {html_path.resolve()}</div>",
            status_code=404,
        )

    raw = html_path.read_text(encoding="utf-8")
    return HTMLResponse(render_preview_html(raw, template=template,
                                            palette=palette))


@app.post("/api/admin/change-password")
def change_password(payload: dict, x_admin_password: str = Header(...)):
    """
    تغییر رمز عبور مدیریت.
    نیازمند رمز فعلی است تا اگر کسی به مرورگر باز شما دسترسی پیدا کرد،
    نتواند بدون دانستن رمز فعلی آن را عوض کند.
    """
    check_auth(x_admin_password)

    current = payload.get("currentPassword", "")
    new = payload.get("newPassword", "")

    # `!=` روی مقدارِ ذخیره‌شده کار نمی‌کند وقتی هَش است
    if not _pw_check(current, _stored_password()):
        raise HTTPException(status_code=400, detail="رمز عبور فعلی نادرست است")

    if len(new) < 8:
        raise HTTPException(status_code=400, detail="رمز جدید باید حداقل ۸ کاراکتر باشد")

    if new == current:
        raise HTTPException(status_code=400, detail="رمز جدید نباید با رمز فعلی یکسان باشد")

    save_password(new)
    return {"ok": True, "message": "رمز عبور با موفقیت تغییر کرد"}


@app.get("/api/admin/export")
def export_config(x_admin_password: str = Header(...)):
    """خروجی کامل تنظیمات برای پشتیبان‌گیری (بدون رمز عبور)."""
    check_auth(x_admin_password)
    cfg = load_config()
    return {
        "_exportedAt": datetime.now().isoformat(),
        "_version": "1.0",
        "config": cfg,
    }


@app.post("/api/admin/import")
def import_config(payload: dict, x_admin_password: str = Header(...)):
    """بازیابی تنظیمات از فایل پشتیبان."""
    check_auth(x_admin_password)

    cfg = payload.get("config") or payload
    if not isinstance(cfg, dict) or "downloadApps" not in cfg:
        raise HTTPException(status_code=400, detail="فایل پشتیبان معتبر نیست")

    # پشتیبان از نسخه‌ی فعلی قبل از بازنویسی (برای بازگشت در صورت اشتباه).
    # save_config خودش نسخه‌ی قبلی را در تاریخچه می‌گذارد؛ این فایل اضافه
    # است، پس شکستش کار را نمی‌ایستاند — ولی گفته می‌شود.
    try:
        backup_path = CONFIG_PATH.parent / f"config.backup.{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as src, open(backup_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
    except OSError as e:
        log.warning("config file backup before import failed: %s", e)

    # بخشی که در پشتیبان نیست یعنی «آن موقع وجود نداشت»، نه «حذفش کن» —
    # همان قاعده‌ی بازگردانیِ ربات. پیش‌تر پشتیبانِ قدیمی (بی `resellers`،
    # `bot`، `popup`، …) آن بخش‌ها را بی‌صدا پاک می‌کرد.
    current = load_config()
    kept = sorted(k for k in current if k not in cfg)
    save_config({**current, **cfg})
    out = {"ok": True, "message": "تنظیمات با موفقیت بازیابی شد"}
    if kept:
        out["kept"] = kept
        out["message"] += f" — {_fnum(len(kept))} بخشِ تازه‌تر که در فایل نبود دست نخورد"
    return out


def _frontend_build_info():
    """
    وضعیت بیلد فرانت‌اند.

    اگر بیلد قدیمی‌تر از کد باشد، یعنی آخرین به‌روزرسانی بیلد نشده و
    کاربر دارد نسخه‌ی قبلی پنل را می‌بیند — دقیقاً همان حالتی که
    گیج‌کننده است چون VERSION جدید نشان می‌دهد.
    """
    root = _root_dir()
    dist = root / "frontend" / "dist" / "index.html"
    src = root / "frontend" / "src" / "App.jsx"

    if not dist.exists():
        return {"built": False, "stale": True,
                "note": "پنل هنوز ساخته نشده — nexora rebuild را اجرا کنید"}

    try:
        d_time = dist.stat().st_mtime
        s_time = src.stat().st_mtime if src.exists() else 0
        stale = s_time > d_time + 5
        return {
            "built": True,
            "stale": stale,
            "builtAt": datetime.fromtimestamp(d_time).isoformat(timespec="seconds"),
            "note": ("کد جدیدتر از بیلد است — nexora rebuild را اجرا کنید"
                     if stale else None),
        }
    except OSError:
        return {"built": True, "stale": False}


@app.get("/api/admin/system")
def system_info(x_admin_password: str = Header(...)):
    """اطلاعات نسخه و وضعیت سیستم برای نمایش در پنل."""
    check_auth(x_admin_password)

    version = "unknown"
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    if version_file.exists():
        try:
            version = version_file.read_text(encoding="utf-8").strip()
        except OSError as _exc:
            log.debug("system_info read: %s", _exc)

    html_path = Path(os.getenv("SUBPAGE_HTML_PATH", "../sub-page-index.html"))
    template_ok = html_path.exists()
    template_size = html_path.stat().st_size if template_ok else 0

    # آدرس API تنظیم‌شده داخل قالب
    api_url = None
    if template_ok:
        try:
            content = html_path.read_text(encoding="utf-8")
            m = _re.search(r'const SUBPAGE_CONFIG_API = "([^"]*)"', content)
            if m:
                api_url = m.group(1)
        except OSError as _exc:
            log.debug("system_info read: %s", _exc)

    cfg = load_config()
    return {
        "build": _frontend_build_info(),
        "version": version,
        "template": {
            "path": str(html_path),
            "exists": template_ok,
            "size": template_size,
            "apiUrl": api_url,
        },
        "counts": {
            "apps": sum(len(v or []) for v in cfg.get("downloadApps", {}).values()),
            "faq": sum(len(v or []) for v in cfg.get("faq", {}).values()),
            "videos": len(cfg.get("videos", [])),
            "resellers": len(cfg.get("resellers", [])),
        },
        "configPath": str(CONFIG_PATH),
        "configExists": CONFIG_PATH.exists(),
    }


@app.get("/api/admin/check-update")
def check_update(x_admin_password: str = Header(...)):
    """
    بررسی وجود نسخه‌ی جدید در گیت‌هاب.
    فقط چک می‌کند — چیزی نصب نمی‌کند.
    """
    check_auth(x_admin_password)

    root = Path(__file__).resolve().parent.parent
    current = "unknown"
    vf = root / "VERSION"
    if vf.exists():
        try:
            current = vf.read_text(encoding="utf-8").strip()
        except OSError as _exc:
            log.warning("check_update read: %s", _exc)

    # خواندن مخزن از فایل .github (اگر نصب‌کننده آن را ساخته باشد)
    repo, token = None, None
    gh = root / ".github"
    if gh.exists():
        try:
            for line in gh.read_text(encoding="utf-8").splitlines():
                if line.startswith("GITHUB_REPO="):
                    repo = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("GITHUB_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError as _exc:
            log.warning("check_update read: %s", _exc)

    if not repo:
        return {
            "currentVersion": current,
            "latestVersion": None,
            "updateAvailable": False,
            "configured": False,
            "message": "به‌روزرسانی خودکار تنظیم نشده است",
        }

    try:
        import urllib.request

        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "nexora-panel"},
        )
        if token:
            req.add_header("Authorization", f"token {token}")

        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.load(resp)

        latest = (data.get("tag_name") or "").lstrip("v")
        notes = data.get("body") or ""
        published = data.get("published_at")

        def parse(v):
            try:
                return tuple(int(x) for x in v.split("."))
            except (ValueError, AttributeError):
                return (0,)

        available = bool(latest) and parse(latest) > parse(current)

        return {
            "currentVersion": current,
            "latestVersion": latest,
            "updateAvailable": available,
            "configured": True,
            "releaseNotes": notes[:2000],
            "publishedAt": published,
            "repo": repo,
        }
    except Exception as e:
        return {
            "currentVersion": current,
            "latestVersion": None,
            "updateAvailable": False,
            "configured": True,
            "error": str(e)[:200],
            "message": "ارتباط با گیت‌هاب برقرار نشد",
        }


@app.post("/api/admin/run-update")
def run_update(x_admin_password: str = Header(...)):
    """
    اجرای به‌روزرسانی در پس‌زمینه.

    نکته: این عملیات سرویس را ری‌استارت می‌کند، پس نمی‌توانیم منتظر
    نتیجه‌اش بمانیم. اسکریپت جدا (detached) اجرا می‌شود تا بعد از
    قطع شدن این پروسه هم ادامه پیدا کند.
    """
    check_auth(x_admin_password)

    root = Path(__file__).resolve().parent.parent
    if not (root / ".github").exists():
        raise HTTPException(status_code=400, detail="به‌روزرسانی خودکار تنظیم نشده است")
    _run_cli_detached("update")
    return {
        "ok": True,
        "message": "به‌روزرسانی شروع شد. حدود ۲ تا ۵ دقیقه طول می‌کشد.",
        "logPath": UPDATE_LOG,
    }


def _run_cli_detached(command):
    """Run `nexora <command>` detached, its output in UPDATE_LOG (the file
    /api/admin/update-log reads). Detached because it restarts this service:
    nothing here can wait for it. One helper for the update button and the Pro
    install button, so the two never write to different logs (the update
    button once wrote a hard-coded path while the reader followed the env)."""
    root = Path(__file__).resolve().parent.parent
    cli = Path("/usr/local/bin/nexora")
    if not cli.exists():
        cli = root / "nexora-cli.sh"
    if not cli.exists():
        raise HTTPException(status_code=400, detail="اسکریپت nexora پیدا نشد")
    try:
        import subprocess
        subprocess.Popen(f"nohup bash {cli} {command} > {UPDATE_LOG} 2>&1 &",
                         shell=True, start_new_session=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"اجرای دستور ناموفق بود: {e}")


@app.get("/api/admin/update-log")
def update_log(x_admin_password: str = Header(...)):
    """خواندن لاگ آخرین به‌روزرسانی."""
    check_auth(x_admin_password)
    # The same file rollback writes to (UPDATE_LOG, overridable by env). A
    # hard-coded copy of the path here meant NEXORA_UPDATE_LOG moved the writer
    # but not the reader.
    p = Path(UPDATE_LOG)
    if not p.exists():
        return {"exists": False, "lines": []}
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        # حذف کدهای رنگ ترمینال برای نمایش تمیز در مرورگر
        clean = [_re.sub(r"\x1b\[[0-9;]*m", "", ln) for ln in lines[-60:]]
        # نشانه‌های پایان کار — چند حالت مختلف را پوشش می‌دهیم چون
        # اسکریپت ممکن است با پیام‌های متفاوتی تمام شود
        end_markers = ("UPDATE COMPLETE", "Already on the latest",
                       "Version did not change", "ROLLBACK COMPLETE",
                       "PRO INSTALL COMPLETE", "Pro package not installed")
        done = any(any(m in ln for m in end_markers) for ln in clean)
        failed = any(ln.strip().startswith("✗") for ln in clean)
        return {"exists": True, "lines": clean, "finished": done, "failed": failed}
    except OSError as e:
        return {"exists": False, "lines": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  مدیریت ربات — ماژول جدا (bot/)
#  پنل فقط به دیتابیس ربات نگاه می‌کند؛ اگر ربات نصب نباشد،
#  این endpointها پاسخ خالی می‌دهند و پنل مثل قبل کار می‌کند.
# ═══════════════════════════════════════════════════════════

BOT_DB = Path(os.getenv("BOT_DB_PATH", str(CONFIG_PATH.parent / "bot.db")))


def _row_get(row, key, default=None):
    """
    یک ستون از ردیف، وقتی ممکن است اصلاً نباشد.

    `sqlite3.Row` برای کلیدِ ناموجود IndexError می‌دهد، نه None. و
    ترتیبِ به‌روزرسانی روی سرور همیشه مرتب نیست: پنل تازه می‌شود و
    ربات هنوز ری‌استارت نشده، پس ستونی که مهاجرتِ ربات می‌سازد
    هنوز وجود ندارد. بدون این، کلِ صندوق ۵۰۳ می‌شد به‌جای اینکه
    فقط یک عکس نیاید.
    """
    try:
        v = row[key]
    except (IndexError, KeyError, TypeError):
        return default
    return default if v is None else v


def _bot_conn():
    """اتصال فقط‌خواندنی به دیتابیس ربات. اگر نبود، None."""
    if not BOT_DB.exists():
        return None
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{BOT_DB}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        return con
    except Exception:
        return None


#: جدول‌هایی که مالِ یک مستاجرند.
_TENANT_TABLES = ("users", "orders", "subscriptions", "plans", "coin_tx",
                  "wallet_tx", "tickets", "chat_messages", "events")


def _tenant_conn(tid):
    """
    اتصالِ فقط‌خواندنی که **فقط داده‌ی یک مستاجر** را می‌بیند.

    چرا این شکل و نه `WHERE tenant_id=?` در هر کوئری:
        تا وقتی فقط یک ربات بود، هیچ کوئریِ پنل شرطِ مستاجر نداشت و
        لازم هم نبود. با آمدنِ رباتِ نماینده‌ها، کاربران، سفارش‌ها،
        قیف و گزارشِ پنلِ مالک همه‌ی مستاجرها را با هم می‌شمردند —
        فروشِ نماینده در عددِ «فروش»ِ مالک می‌آمد، و پیام به کاربری که
        مالِ رباتِ دیگری بود از رباتِ مالک می‌رفت.

        گزارش به‌تنهایی دوازده کوئری دارد. اضافه‌کردنِ شرط به تک‌تکشان
        یعنی روزی یکی جا بماند — همان باگِ همیشگیِ این مخزن.

    SQLite نامِ بی‌پیشوند را اول در `temp` می‌گردد، بعد در `main`. پس
    یک نمای موقت به همان نام، هر کوئریِ موجود را بدونِ دست‌زدن محدود
    می‌کند — از جمله زیرکوئری‌ها. روی اتصالِ فقط‌خواندنی هم کار می‌کند،
    چون `temp` همیشه نوشتنی است.

    `tid=None` یعنی بدونِ محدودیت (هنوز مستاجری نیست).
    """
    con = _bot_conn()
    if con is None or tid is None:
        return con
    try:
        have = {r[0] for r in con.execute(
            "SELECT name FROM main.sqlite_master WHERE type='table'")}
        for tbl in _TENANT_TABLES:
            if tbl not in have:
                continue
            cols = {r[1] for r in con.execute(f"PRAGMA main.table_info({tbl})")}
            if "tenant_id" in cols:
                # int(): تعریفِ نما پارامتر نمی‌گیرد، پس عدد مستقیم می‌نشیند
                con.execute(f"CREATE TEMP VIEW {tbl} AS SELECT * FROM "
                            f"main.{tbl} WHERE tenant_id={int(tid)}")
    except Exception:
        con.close()
        raise
    return con


def _root_tid():
    """شناسه‌ی مستاجرِ ریشه، یا None اگر هنوز نیست."""
    con = _bot_conn()
    if not con:
        return None
    try:
        r = con.execute("SELECT id FROM tenants WHERE parent_id IS NULL "
                        "ORDER BY id LIMIT 1").fetchone()
        return int(r["id"]) if r else None
    except Exception:
        return None
    finally:
        con.close()


#: «خرید واقعی» — یک تعریف، برای هر جایی که می‌پرسد چند نفر خریدند.
#
#  گرفتن تست رایگان خودش یک سفارشِ `approved` با مبلغ صفر می‌سازد. هر
#  شمارشی که این را کنار نگذارد، کسانی را که فقط دکمه‌ی تست را زده‌اند
#  «خریدار» حساب می‌کند.
#
#  قیف تبدیل در ۱.۳۷.۰ درست شد ولی گزارش فروش تعریف خودش را داشت، پس
#  پنل دو نرخ تبدیل نشان می‌داد: ۸۰٪ و ۲۰٪ روی همان داده. حالا هر سه
#  جا — قیف، گزارش فروش، و آمار پنل نماینده — از همین می‌خوانند.
SQL_PLAN_JOIN = "LEFT JOIN plans p ON p.id = o.plan_id"
SQL_REAL_BUY = "o.status='approved' AND COALESCE(p.is_trial,0)=0"


@app.get("/api/admin/bot/inbounds")
def bot_inbounds(tenant: int = None, x_admin_password: str = Header(...)):
    """
    اینباندهای پنل با نام و مشخصات.

    تا مدیر با نام انتخاب کند نه با شماره — کسی شماره‌ی اینباند
    را حفظ نیست، ولی نامش را می‌شناسد.
    """
    check_auth(x_admin_password)
    ok, err = _ensure_bot_db()
    if not ok:
        return {"ready": False, "error": err, "inbounds": []}

    con = _bot_conn()
    if not con:
        return {"ready": False, "error": "دیتابیس ربات در دسترس نیست",
                "inbounds": []}
    try:
        # اعتبارنامه‌ی پنل x-ui همیشه مالِ مالک است — ردیف نماینده
        # معمولاً خالی است و صفحه بدون هیچ توضیحی «اینباندی نیست»
        # نشان می‌داد.
        root = con.execute(
            "SELECT panel_url, panel_user, panel_pass, panel_token, "
            "default_inbound, inbound_mode, inbound_ids "
            "FROM tenants WHERE parent_id IS NULL "
            "ORDER BY id LIMIT 1").fetchone()
        t = dict(root) if root else {}

        # ولی *انتخابِ* اینباند مالِ همان مستاجری است که پرسیده شده.
        # قبلاً همیشه ریشه خوانده می‌شد، پس تنظیم هر نماینده نه دیده
        # می‌شد و نه قابل تغییر بود.
        if tenant:
            own = con.execute(
                "SELECT default_inbound, inbound_mode, inbound_ids "
                "FROM tenants WHERE id=?", (int(tenant),)).fetchone()
            if not own:
                return {"ready": False, "error": "نماینده پیدا نشد",
                        "inbounds": []}
            t.update({k: own[k] for k in
                      ("default_inbound", "inbound_mode", "inbound_ids")})
    except Exception as e:
        return {"ready": False, "error": str(e)[:150], "inbounds": []}
    finally:
        con.close()

    if not t.get("panel_url"):
        return {"ready": False, "error": "اتصال پنل تنظیم نشده", "inbounds": []}

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_nx_xui", _bot_dir() / "xui.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        cl = m.XUI(t["panel_url"], t.get("panel_user"),
                   t.get("panel_pass"), t.get("panel_token"))
        raw = cl.inbounds()
    except Exception as e:
        return {"ready": False, "error": f"خواندن اینباندها ناموفق: {str(e)[:120]}",
                "inbounds": []}

    out = []
    for i in raw:
        out.append({
            "id": i.get("id"),
            "remark": i.get("remark") or f"اینباند {i.get('id')}",
            "protocol": i.get("protocol") or "",
            "port": i.get("port"),
            "enable": bool(i.get("enable", True)),
        })

    try:
        selected = json.loads(t.get("inbound_ids") or "[]")
    except (json.JSONDecodeError, TypeError):
        selected = []

    return {
        "ready": True,
        "inbounds": out,
        "mode": t.get("inbound_mode") or "all",
        "selected": selected,
        "default": t.get("default_inbound"),
        "tenant": int(tenant) if tenant else None,
    }


@app.put("/api/admin/bot/inbounds")
def bot_inbounds_set(payload: dict, x_admin_password: str = Header(...)):
    """
    تعیین اینباندهایی که کانفیگ روی آن‌ها ساخته شود.

    mode:
      all     → همه‌ی اینباندهای فعال
      default → فقط اینباند پیش‌فرض
      custom  → همان‌هایی که انتخاب شده

    `tenant` در بدنه یعنی «برای همین نماینده». بدون آن، مستاجر ریشه —
    یعنی خودِ مالک.

    قبلاً این دستور `WHERE` نداشت و روی *همه‌ی* مستاجرها می‌نوشت. یعنی
    هر بار که مالک اینباندهای خودش را تنظیم می‌کرد، همان تنظیم بی‌صدا
    روی تک‌تک نماینده‌ها هم می‌نشست و انتخابِ خودشان را پاک می‌کرد.
    """
    check_auth(x_admin_password)
    mode = (payload or {}).get("mode") or "all"
    if mode not in ("all", "default", "custom"):
        raise HTTPException(status_code=400, detail="حالت نامعتبر")

    ids = payload.get("ids") or []
    clean = []
    for x in ids:
        try:
            clean.append(int(x))
        except (TypeError, ValueError):
            continue

    if mode == "custom" and not clean:
        raise HTTPException(status_code=400,
                            detail="در حالت انتخابی، حداقل یک اینباند لازم است")

    con = _bot_rw()
    try:
        tid = (payload or {}).get("tenant")
        if tid:
            row = con.execute("SELECT id FROM tenants WHERE id=?",
                              (int(tid),)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="نماینده پیدا نشد")
            target = int(tid)
        else:
            row = con.execute("SELECT id FROM tenants WHERE parent_id IS NULL "
                              "ORDER BY id LIMIT 1").fetchone()
            if not row:
                raise HTTPException(status_code=400,
                                    detail="مستاجر ریشه پیدا نشد")
            target = int(row["id"])

        cur = con.execute(
            "UPDATE tenants SET inbound_mode=?, inbound_ids=? WHERE id=?",
            (mode, json.dumps(clean), target))
        con.commit()
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail="چیزی تغییر نکرد")
        return {"ok": True, "mode": mode, "ids": clean, "tenant": target}
    finally:
        con.close()


#: رقمِ فارسی و عربی ← لاتین (برای خواندنِ ورودی). تنها تعریف در این فایل —
#  برعکسش `_TO_FA_DIGITS` است.
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@app.post("/api/admin/bot/xui-trace")
def bot_xui_trace(x_admin_password: str = Header(...)):
    """
    تشخیص کامل ساخت کانفیگ — همان چیزی که scripts/xui-trace.py می‌کند،
    ولی از داخل پنل تا نیازی به SSH نباشد.

    هر مرحله جدا گزارش می‌شود، و اگر جایی شکست بخورد پیام خام
    پنل ۳x-ui بدون تفسیر نمایش داده می‌شود — چون همان پیام است
    که می‌گوید چه چیزی کم است.
    """
    check_auth(x_admin_password)
    steps = []

    def step(title, ok, detail="", hint=""):
        steps.append({"title": title, "ok": ok, "detail": detail, "hint": hint})
        return ok

    con = _bot_conn()
    if not con:
        step("خواندن تنظیمات", False, "دیتابیس ربات در دسترس نیست")
        return {"ok": False, "steps": steps}

    try:
        # همان قاعده‌ی بالا: صفحه‌ی عیب‌یابی هم باید تنظیمات مالک را
        # بخواند، وگرنه «پنل تنظیم نشده» گزارش می‌کند در حالی که شده.
        r = con.execute(
            "SELECT panel_url, panel_user, panel_pass, panel_token, "
            "default_inbound FROM tenants WHERE parent_id IS NULL "
            "ORDER BY id LIMIT 1").fetchone()
        t = dict(r) if r else {}
    finally:
        con.close()

    if not t.get("panel_url"):
        step("آدرس پنل", False, "تنظیم نشده",
             "بخش اتصال و تنظیمات را پر کنید")
        return {"ok": False, "steps": steps}

    step("آدرس پنل", True, t["panel_url"])
    step("روش احراز هویت", True,
         "توکن API" if t.get("panel_token") else f"نام کاربری ({t.get('panel_user')})")

    # app.py ماژول sys را با نام _sys وارد می‌کند؛ «sys» خالی این‌جا
    # یعنی NameError درست وقتی ادمین دکمه‌ی ردیابی را می‌زند.
    import sys as _sys
    _sys.path.insert(0, str(_bot_dir()))
    try:
        from xui import XUI, XUIError
    except Exception as e:
        step("بارگذاری کلاینت", False, str(e)[:120])
        return {"ok": False, "steps": steps}

    client = XUI(t["panel_url"], t.get("panel_user"),
                 t.get("panel_pass"), t.get("panel_token"))

    try:
        client.login()
        step("ورود به پنل", True, "موفق")
    except Exception as e:
        step("ورود به پنل", False, str(e)[:160],
             "رمز یا توکن را بررسی کنید")
        return {"ok": False, "steps": steps}

    try:
        inbounds = client.inbounds()
        step("خواندن inboundها", True,
             " · ".join(f"#{i.get('id')} {i.get('remark','')}"
                        for i in inbounds[:5]))
    except Exception as e:
        step("خواندن inboundها", False, str(e)[:160])
        return {"ok": False, "steps": steps}

    if not inbounds:
        step("inbound موجود", False, "هیچ inboundی نیست",
             "در ۳x-ui حداقل یک inbound بسازید")
        return {"ok": False, "steps": steps}

    try:
        routes = client.discover()
    except Exception:
        routes = {}

    if routes:
        client_routes = [p for p in routes if "client" in p.lower()]
        step("مسیرهای API", True,
             f"{len(routes)} مسیر · " +
             (", ".join(sorted(client_routes)[:3]) if client_routes
              else "بدون مسیر کلاینت"))
    else:
        step("مسیرهای API", True, "پنل مشخصات OpenAPI ندارد",
             "مسیرها با آزمون‌وخطا پیدا می‌شوند")

    schema = None
    try:
        schema = client.request_schema("/panel/api/clients", "post")
    except Exception as _exc:
        log.debug("x-ui request schema: %s", _exc)

    if schema:
        props = list((schema.get("properties") or {}).keys())
        req = schema.get("required") or []
        step("فیلدهایی که پنل می‌خواهد", True,
             f"{', '.join(props[:10])}" +
             (f" · اجباری: {', '.join(req)}" if req else ""))
    else:
        step("فیلدهایی که پنل می‌خواهد", True,
             "اعلام نشده — شکل‌های شناخته‌شده امتحان می‌شوند")

    target = t.get("default_inbound") or inbounds[0].get("id")
    email = f"nexora_test_{secrets.token_hex(3)}"

    created = None
    try:
        created = client.add_client(int(target), email, gb=1, days=1)
        step("ساخت کانفیگ آزمایشی", True, f"{email} روی inbound #{target}")
    except Exception as e:
        step("ساخت کانفیگ آزمایشی", False, str(e)[:300],
             "پیام بالا مستقیم از پنل ۳x-ui است. اگر نام فیلدی را "
             "می‌گوید، همان فیلد در این نسخه جای دیگری است.")
        return {"ok": False, "steps": steps}

    try:
        found = client.find_client(int(target), email=email)
        step("بازخوانی از پنل", bool(found),
             "پیدا شد" if found else "ساخته شد ولی پیدا نشد",
             "" if found else "احتمالاً به inbound وصل نشده — "
             "کلاینت هست ولی هیچ‌جا فعال نیست")
    except Exception as e:
        step("بازخوانی از پنل", False, str(e)[:160])

    try:
        if created and created.get("id"):
            client.delete_client(int(target), created["id"], email=email)
            step("پاکسازی", True, "کانفیگ آزمایشی حذف شد")
    except Exception as e:
        step("پاکسازی", False, f"{str(e)[:120]} — {email} را دستی حذف کنید")

    return {"ok": all(s["ok"] for s in steps), "steps": steps}


@app.get("/api/admin/bot/status")
def bot_status(x_admin_password: str = Header(...)):
    """وضعیت کلی ربات — نصب شده؟ فعال است؟ چند کاربر؟"""
    check_auth(x_admin_password)

    module_exists = (_bot_dir() / "run.py").exists()
    okdb, err = _ensure_bot_db()
    # فقط مستاجرِ ریشه — فروشِ رباتِ نماینده درآمدِ نماینده است
    con = _tenant_conn(_root_tid())
    if not con:
        return {
            "installed": module_exists,
            "dbReady": False,
            "running": _svc_active(),
            "message": err or ("ربات هنوز راه‌اندازی نشده است" if module_exists
                               else "ماژول ربات روی سرور نیست — nexora update را اجرا کنید"),
            "botDir": str(_bot_dir()),
            "dbPath": str(BOT_DB),
        }

    try:
        stats = {}
        for key, sql in [
            ("users", "SELECT COUNT(*) c FROM users"),
            ("plans", "SELECT COUNT(*) c FROM plans WHERE is_active=1"),
            ("pendingOrders", "SELECT COUNT(*) c FROM orders WHERE status IN ('awaiting','review')"),
            ("activeSubs", "SELECT COUNT(*) c FROM subscriptions WHERE is_active=1"),
            ("openTickets", "SELECT COUNT(*) c FROM tickets WHERE status='open'"),
            ("tenants", "SELECT COUNT(*) c FROM tenants"),
        ]:
            try:
                stats[key] = con.execute(sql).fetchone()["c"]
            except Exception:
                stats[key] = 0

        # «فروش» و «درآمد» یکی نیستند: سفارشی که از کیف پول پرداخت
        # شده فروش هست ولی پول تازه‌ای با آن نرسیده. این عدد بی‌برچسب
        # بالای صفحه می‌نشست و خواننده آن را درآمد می‌خواند.
        try:
            sales = con.execute(
                "SELECT COALESCE(SUM(amount),0) s FROM orders "
                "WHERE status='approved'").fetchone()["s"]
        except Exception:
            sales = 0

        return {
            "installed": True,
            "dbReady": True,
            "running": _svc_active(),
            "stats": stats,
            "totalSales": sales,
            "totalReceived": _bot_money_in(),
            # نام قدیمی، تا اگر جایی هنوز می‌خواندش خالی نماند
            "totalRevenue": sales,
        }
    finally:
        con.close()


@app.get("/api/admin/bot/orders")
def bot_orders(status: str = "awaiting", limit: int = 50,
               x_admin_password: str = Header(...)):
    """صف سفارش‌ها — برای تایید رسید از داخل پنل."""
    check_auth(x_admin_password)
    # سفارشِ رباتِ نماینده این‌جا دکمه‌ی تایید می‌گرفت ولی با زمینه‌ی
    # رباتِ مالک پیدا نمی‌شد. مالِ هر کس، در پنلِ خودش.
    con = _tenant_conn(_root_tid())
    if not con:
        return {"orders": [], "dbReady": False}

    try:
        allowed = {"awaiting", "review", "approved", "rejected", "all"}
        if status not in allowed:
            status = "awaiting"

        # نامِ پلن هم — کارتِ سفارش تا امروز نمی‌گفت مشتری *چه* خریده؛
        # مدیر رسیدِ ۲۸۰ هزار تومانی را بی‌آنکه بداند سه‌ماهه است یا
        # شارژِ کیف پول تایید می‌کرد
        _sel = ("SELECT o.*, u.first_name, u.username, u.tg_id, "
                "p.name AS plan_name, COALESCE(p.is_trial,0) AS plan_is_trial "
                "FROM orders o LEFT JOIN users u ON u.id=o.user_id "
                "LEFT JOIN plans p ON p.id=o.plan_id ")
        if status == "all":
            rows = con.execute(_sel + "ORDER BY o.created_at DESC LIMIT ?",
                               (min(limit, 200),)).fetchall()
        elif status == "awaiting":
            # «review» وضعیتِ قدیمی است که تایید و رد هنوز می‌پذیرندش ولی هیچ
            # زبانه‌ای نشانش نمی‌داد — رسیدی که فقط در «همه» پیدا می‌شد
            rows = con.execute(_sel + "WHERE o.status IN ('awaiting','review') "
                               "ORDER BY o.created_at DESC LIMIT ?", (min(limit, 200),)).fetchall()
        else:
            rows = con.execute(_sel + "WHERE o.status=? ORDER BY o.created_at DESC LIMIT ?",
                               (status, min(limit, 200))).fetchall()

        return {"orders": [dict(r) for r in rows], "dbReady": True}
    except Exception as e:
        return {"orders": [], "dbReady": True, "error": str(e)[:200]}
    finally:
        con.close()


#: فیلترهای بخش کاربران — شرط SQL هرکدام.
#
# فهرست ساده‌ی «۵۰ کاربر آخر» وقتی چند صد کاربر دارید بی‌فایده است؛
# ادمین معمولاً دنبال یک دسته‌ی مشخص می‌گردد: چه کسی خرید کرده، چه
# کسی شماره داده، چه کسی اشتراکش تمام شده.
_USER_FILTERS = {
    "all": "1=1",
    "active": "EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=u.id "
              "AND s.is_active=1 AND (s.expires_at IS NULL "
              "OR s.expires_at > CURRENT_TIMESTAMP))",
    "expired": "EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=u.id) "
               "AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=u.id "
               "AND s.is_active=1 AND (s.expires_at IS NULL "
               "OR s.expires_at > CURRENT_TIMESTAMP))",
    "never": "NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=u.id)",
    # «خریدار» یعنی همان چیزی که قیف می‌گوید، نه هر سفارشِ approved.
    #
    #  گرفتنِ تست رایگان خودش یک سفارشِ approved با مبلغ صفر می‌سازد،
    #  پس با شرطِ خامِ status='approved' هر کسی که دکمه‌ی تست را زده
    #  «خریدار» شمرده می‌شد — چیپِ بالای صفحه عددِ بزرگ‌تری از قیف
    #  نشان می‌داد و لیست، آدمی را خریدار می‌خواند که یک تومان هم
    #  نداده بود. همان قاعده، دو جا، دو جواب.
    "buyers": f"EXISTS (SELECT 1 FROM orders o {SQL_PLAN_JOIN} "
              f"WHERE o.user_id=u.id AND {SQL_REAL_BUY})",
    "blocked": "u.is_blocked=1",
    "withPhone": "u.phone IS NOT NULL AND u.phone<>''",
    "noPhone": "(u.phone IS NULL OR u.phone='')",
    "withBalance": "COALESCE(u.balance,0) > 0",
    "withCoins": "COALESCE(u.coins,0) > 0",
    "referred": "u.referred_by IS NOT NULL",
    # Removed users: off every other list, and here to be brought back (the
    # owner, 2026-10-02: a removed user could never come back, even when the
    # removal was a mistake).
    "removed": "u.deleted_at IS NOT NULL",
}

_USER_SORTS = {
    "new": "u.created_at DESC",
    "old": "u.created_at ASC",
    "spent": "spent DESC",
    "balance": "COALESCE(u.balance,0) DESC",
    "coins": "COALESCE(u.coins,0) DESC",
    "lastSeen": "COALESCE(u.last_seen, u.created_at) DESC",
}


@app.get("/api/admin/bot/users")
def bot_users(q: str = "", limit: int = 50, offset: int = 0,
              filter: str = "all", sort: str = "new", counts: int = 1,
              x_admin_password: str = Header(...)):
    """
    کاربران ربات با فیلتر، مرتب‌سازی و آمار هر کاربر.

    برای هر کاربر تعداد سفارش موفق، مجموع خرید و وضعیت اشتراک هم
    برمی‌گردد — بدون این‌ها ادمین باید روی تک‌تک کاربران کلیک می‌کرد
    تا بفهمد کدام مشتری واقعی است.
    """
    check_auth(x_admin_password)
    return _users_page(_root_tid(), q=q, limit=limit, offset=offset,
                       filter=filter, sort=sort, counts=counts)


def _user_block(t, tg_id, block, by):
    """
    Ban or unban one bot user of shop `t`, for the owner and for a reseller
    (one core, two thin routes). A banned user gets no answer from the bot
    and a 403 from the mini app; their configs keep working until deleted.
    """
    h = _bot_handlers()
    d = h.DB.TenantDB(t["id"])
    u = d.get_user(int(tg_id))
    if not u or u.get("deleted_at"):
        raise HTTPException(404, detail="این کاربر در این ربات نیست")
    d.exec("UPDATE users SET is_blocked=?, blocked_by=? WHERE tenant_id=? AND id=?",
           (1 if block else 0, by if block else None, t["id"], u["id"]))
    d.log("user_blocked" if block else "user_unblocked", u["id"], {"by": by})
    return {"ok": True, "blocked": bool(block)}


def _user_delete(t, tg_id, by):
    """
    Remove one bot user: ban, delete every config of theirs from 3x-ui, take
    them off the list. Orders and payments stay, so the accounts still add
    up. A reseller's configs go through the billing core (`_portal_delete_core`),
    the same as the portal's delete button, so usage and the period's share
    stay on that reseller's bill. Any config that could not be deleted is
    named; the user stays listed until it is.
    """
    h = _bot_handlers()
    d = h.DB.TenantDB(t["id"])
    u = d.get_user(int(tg_id))
    if not u or u.get("deleted_at"):
        raise HTTPException(404, detail="این کاربر در این ربات نیست")
    subs = d.q("SELECT * FROM subscriptions WHERE tenant_id=? AND user_id=? "
               "AND deleted_at IS NULL", (t["id"], u["id"]))
    now = datetime.now().isoformat(timespec="seconds")
    failed = []
    for s in subs:
        try:
            if t.get("parent_id"):
                core_del = globals().get("_portal_delete_core")
                if core_del is None:
                    raise RuntimeError("billing core (Pro) not loaded")
                core_del(t, s["client_email"], by_whom=f"user removed by {by}")
            else:
                h.Ctx(h.Bot(t["bot_token"]), t).xui.delete_client(
                    s["inbound_id"], s["client_uuid"], email=s["client_email"])
            d.exec("UPDATE subscriptions SET is_active=0, deleted_at=?, deleted_why='user_deleted' "
                   "WHERE tenant_id=? AND id=?", (now, t["id"], s["id"]))
        except Exception as e:
            log.warning("deleting config %s of user %s failed: %s", s["client_email"], tg_id, e)
            failed.append(f"{s['client_email']}: {str(e)[:100]}")
    d.exec("UPDATE users SET is_blocked=1, blocked_by=? WHERE tenant_id=? AND id=?",
           (by, t["id"], u["id"]))
    if failed:
        raise HTTPException(502, detail="کاربر مسدود شد ولی این کانفیگ‌ها از 3x-ui پاک نشدند: "
                                        + "، ".join(failed))
    d.exec("UPDATE users SET deleted_at=? WHERE tenant_id=? AND id=?", (now, t["id"], u["id"]))
    d.log("user_deleted", u["id"], {"by": by, "configs": len(subs)})
    return {"ok": True, "configs": len(subs)}


def _user_restore(t, tg_id, by):
    """
    Bring a removed (or banned) user back: the bot and the mini app answer
    them again and they are on the list. Their deleted configs stay deleted:
    those were taken out of 3x-ui (and off a reseller's bill), so a returning
    user buys again.
    """
    h = _bot_handlers()
    d = h.DB.TenantDB(t["id"])
    u = d.get_user(int(tg_id))
    if not u:
        raise HTTPException(404, detail="این کاربر در این ربات نیست")
    d.exec("UPDATE users SET deleted_at=NULL, is_blocked=0, blocked_by=NULL "
           "WHERE tenant_id=? AND id=?", (t["id"], u["id"]))
    d.log("user_restored", u["id"], {"by": by})
    return {"ok": True}


@app.post("/api/admin/bot/users/{tg_id}/restore")
def bot_user_restore(tg_id: int, x_admin_password: str = Header(...)):
    check_auth(x_admin_password)
    return _user_restore(_root_tenant_row(), tg_id, "owner")


@app.post("/api/admin/bot/users/{tg_id}/block")
def bot_user_block(tg_id: int, body: dict, x_admin_password: str = Header(...)):
    check_auth(x_admin_password)
    return _user_block(_root_tenant_row(), tg_id, bool((body or {}).get("block")), "owner")


@app.delete("/api/admin/bot/users/{tg_id}")
def bot_user_delete(tg_id: int, x_admin_password: str = Header(...)):
    check_auth(x_admin_password)
    return _user_delete(_root_tenant_row(), tg_id, "owner")


def _users_page(tid, q="", limit=50, offset=0, filter="all", sort="new",
                counts=1):
    """
    فهرستِ کاربرانِ یک مستاجر — همان برای مالک و نماینده.

    یک پیاده‌سازی: فیلترها، مرتب‌سازی و قاعده‌ی «خریدار» یک جا هستند.
    """
    con = _tenant_conn(tid)
    if not con:
        return {"users": [], "dbReady": False}

    # removed users are off the list (but for their own filter); their
    # orders stay for the accounts
    where = [_USER_FILTERS.get(filter, "1=1")]
    if filter != "removed":
        where.append("u.deleted_at IS NULL")
    params = []
    if q:
        like = f"%{q}%"
        where.append("(u.first_name LIKE ? OR u.username LIKE ? "
                     "OR CAST(u.tg_id AS TEXT) LIKE ? OR u.phone LIKE ?)")
        params += [like, like, like, like]

    where_sql = " AND ".join(f"({w})" for w in where)
    order_sql = _USER_SORTS.get(sort, _USER_SORTS["new"])
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    base = f"""
        SELECT u.*,
          -- «۱ خرید · ۰ تومان» کنارِ کسی که فقط تست گرفته بود، چون
          -- تستِ رایگان هم یک سفارشِ approved است. همان قاعده‌ی قیف.
          (SELECT COUNT(*) FROM orders o {SQL_PLAN_JOIN}
            WHERE o.user_id=u.id AND {SQL_REAL_BUY}) AS ordersCount,
          (SELECT COALESCE(SUM(o.amount),0) FROM orders o {SQL_PLAN_JOIN}
            WHERE o.user_id=u.id AND {SQL_REAL_BUY}) AS spent,
          (SELECT COUNT(*) FROM subscriptions s WHERE s.user_id=u.id
            AND s.deleted_at IS NULL) AS subsCount,
          (SELECT COUNT(*) FROM subscriptions s WHERE s.user_id=u.id
            AND s.deleted_at IS NULL
            AND s.is_active=1 AND (s.expires_at IS NULL
            OR s.expires_at > CURRENT_TIMESTAMP)) AS activeSubs
        FROM users u
        WHERE {where_sql}
    """

    try:
        total = con.execute(
            f"SELECT COUNT(*) AS n FROM users u WHERE {where_sql}",
            params).fetchone()["n"]
        rows = con.execute(f"{base} ORDER BY {order_sql} LIMIT ? OFFSET ?",
                           params + [limit, offset]).fetchall()

        # شمارش هر فیلتر، تا ادمین بدون کلیک‌کردن بداند هرکدام چندتاست.
        #
        # یک اسکن، نه یازده‌تا — ولی شرط‌ها از همان `_USER_FILTERS`
        # ساخته می‌شوند، نه یک نسخه‌ی دوم. اگر این‌جا دستی نوشته
        # می‌شد، همان باگِ همیشگیِ این مخزن بود: یک قاعده، دو جا،
        # اصلاح در یکی.
        #
        # اندازه‌گیری روی ۲۵ هزار کاربر: ۶۱ میلی‌ثانیه → ۳۵.
        n_counts = {}
        if counts:
            try:
                sel = ", ".join(
                    f'SUM(CASE WHEN ({cond})'
                    + ('' if key == "removed" else ' AND u.deleted_at IS NULL')
                    + f' THEN 1 ELSE 0 END) AS "{key}"'
                    for key, cond in _USER_FILTERS.items())
                row = con.execute(f"SELECT {sel} FROM users u").fetchone()
                n_counts = {k: int(row[k] or 0) for k in _USER_FILTERS}
            except Exception:
                log.debug("شمارش فیلترها ناموفق", exc_info=True)
                n_counts = {}

        out = {"users": [_with_trial_info(dict(r)) for r in rows], "dbReady": True,
               "total": total, "offset": offset, "limit": limit}
        # وقتی خواسته نشده، کلید اصلاً نمی‌آید — فرانت عددهای قبلی
        # را نگه می‌دارد. `{}` می‌فرستادیم، همه‌ی چیپ‌ها صفر می‌شدند.
        if counts:
            out["counts"] = n_counts
        return out
    except Exception as e:
        return {"users": [], "dbReady": True, "error": str(e)[:200]}
    finally:
        con.close()


def _with_trial_info(u):
    """
    پاسخ‌های پیش از تست (نام · اپراتور · دستگاه) به شکلِ خوانا — برچسب‌ها از
    همان `core.TRIAL_*` که ربات و مینی‌اپ نشان می‌دهند، نه نسخه‌ی دومی در رابط.
    """
    core = _bot_core()
    parts = [u.get("real_name") or "",
             dict(core.TRIAL_OPERATORS).get(u.get("operator") or "", ""),
             dict(core.TRIAL_OS).get(u.get("device_os") or "", "")]
    u["trialInfo"] = " · ".join(x for x in parts if x)
    return u


@app.get("/api/admin/bot/users/report")
def bot_users_report(days: int = 30, x_admin_password: str = Header(...)):
    """
    گزارش دوره‌ای کاربران ربات — معادل صورتحساب حسابداری، ولی برای
    سمت فروش.

    حسابداری می‌گوید از هر واسطه چقدر طلب دارید. این می‌گوید در این
    دوره چند نفر آمدند، چند نفر خریدند، چقدر فروش رفت و چه کسانی
    بیشترین سهم را داشتند — چیزی که تا حالا فقط با نگاه‌کردن به
    فهرست کاربران قابل حدس‌زدن بود.
    """
    check_auth(x_admin_password)
    con = _tenant_conn(_root_tid())
    if not con:
        return {"ready": False, "error": "دیتابیس ربات در دسترس نیست"}

    days = max(1, min(int(days or 30), 365))
    since = f"-{days} days"

    def one(sql, args=()):
        try:
            r = con.execute(sql, args).fetchone()
            return dict(r) if r else {}
        except Exception:
            return {}

    def many(sql, args=()):
        try:
            return [dict(r) for r in con.execute(sql, args)]
        except Exception:
            return []

    try:
        totals = one("""
            SELECT
              (SELECT COUNT(*) FROM users) AS users,
              (SELECT COUNT(*) FROM users
                WHERE created_at >= datetime('now', ?)) AS newUsers,
              (SELECT COUNT(*) FROM users WHERE is_blocked=1) AS blocked,
              (SELECT COUNT(*) FROM users WHERE phone IS NOT NULL
                AND phone != '') AS withPhone
        """, (since,))

        # تست رایگان سفارش هست ولی خرید نیست — بدون این، هم تعداد
        # باد می‌کند و هم «میانگین سفارش» با سفارش‌های صفرتومانی
        # پایین کشیده می‌شود.
        orders = one(f"""
            SELECT COUNT(*) AS n, COALESCE(SUM(o.amount),0) AS sum
            FROM orders o {SQL_PLAN_JOIN}
            WHERE {SQL_REAL_BUY} AND o.created_at >= datetime('now', ?)
        """, (since,))

        rejected = one("""
            SELECT COUNT(*) AS n FROM orders
            WHERE status='rejected' AND created_at >= datetime('now', ?)
        """, (since,))

        pending = one("SELECT COUNT(*) AS n FROM orders WHERE status='awaiting'")

        subs = one("""
            SELECT
              (SELECT COUNT(*) FROM subscriptions) AS total,
              (SELECT COUNT(*) FROM subscriptions WHERE is_active=1
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP))
                AS active,
              (SELECT COUNT(*) FROM subscriptions
                WHERE expires_at IS NOT NULL
                AND expires_at <= datetime('now', '+3 days')
                AND expires_at > CURRENT_TIMESTAMP) AS expiringSoon
        """)

        # خریدارها — همان چیزی که تصمیم فروش رویش گرفته می‌شود
        buyers = many(f"""
            SELECT u.tg_id, u.first_name, u.username, u.phone,
                   COUNT(o.id) AS orders,
                   COALESCE(SUM(o.amount),0) AS spent,
                   MAX(o.created_at) AS lastBuy
            FROM users u JOIN orders o ON o.user_id = u.id {SQL_PLAN_JOIN}
            WHERE {SQL_REAL_BUY} AND o.created_at >= datetime('now', ?)
            GROUP BY u.id
            ORDER BY spent DESC
            LIMIT 20
        """, (since,))

        # فروش روزانه، برای دیدن روند
        daily = many(f"""
            SELECT date(o.created_at) AS day, COUNT(*) AS n,
                   COALESCE(SUM(o.amount),0) AS sum
            FROM orders o {SQL_PLAN_JOIN}
            WHERE {SQL_REAL_BUY} AND o.created_at >= datetime('now', ?)
            GROUP BY date(o.created_at)
            ORDER BY day
        """, (since,))

        n_orders = int(orders.get("n") or 0)
        n_new = int(totals.get("newUsers") or 0)
        n_buyers = len(many(f"""
            SELECT DISTINCT o.user_id FROM orders o {SQL_PLAN_JOIN}
            WHERE {SQL_REAL_BUY} AND o.created_at >= datetime('now', ?)
        """, (since,)))

        return {
            "ready": True,
            "days": days,
            "users": totals,
            "orders": {
                "approved": n_orders,
                "rejected": int(rejected.get("n") or 0),
                "pending": int(pending.get("n") or 0),
                "revenue": int(orders.get("sum") or 0),
                "avg": int((orders.get("sum") or 0) / n_orders) if n_orders else 0,
            },
            "subs": subs,
            "buyers": buyers,
            "buyerCount": n_buyers,
            # نرخ تبدیل: از کسانی که این دوره آمدند، چند درصد خریدند
            "conversion": (round(n_buyers * 100.0 / n_new, 1)
                           if n_new else None),
            "daily": daily,
        }
    finally:
        con.close()


@app.get("/api/admin/bot/users/export")
def bot_users_export(q: str = "", filter: str = "all", sort: str = "new",
                     x_admin_password: str = Header(...)):
    """
    خروجی CSV کاربران ربات — با همان فیلتری که در صفحه اعمال شده.

    شماره تماس هم می‌آید، چون همان چیزی است که برای پیگیری فروش
    بیرون از تلگرام لازم می‌شود.
    """
    check_auth(x_admin_password)

    data = bot_users(q=q, filter=filter, sort=sort, limit=100000, offset=0,
                     x_admin_password=x_admin_password)
    if not data.get("dbReady"):
        raise HTTPException(status_code=400, detail="دیتابیس ربات در دسترس نیست")

    import csv
    import io as _io
    buf = _io.StringIO()
    buf.write("﻿")   # BOM تا اکسل فارسی را درست بخواند
    w = csv.writer(buf)
    w.writerow(["شناسه تلگرام", "نام", "یوزرنیم", "شماره تماس",
                "سفارش موفق", "مجموع خرید (تومان)", "اشتراک", "اشتراک فعال",
                "سکه", "کیف پول", "کد دعوت", "مسدود", "تاریخ عضویت"])

    for u in data.get("users") or []:
        w.writerow([
            u.get("tg_id", ""), u.get("first_name") or "",
            u.get("username") or "", u.get("phone") or "",
            u.get("ordersCount", 0), u.get("spent", 0),
            u.get("subsCount", 0), u.get("activeSubs", 0),
            u.get("coins", 0), u.get("balance", 0),
            u.get("ref_code") or "",
            "بله" if u.get("is_blocked") else "خیر",
            str(u.get("created_at") or "")[:19],
        ])

    from fastapi.responses import Response as _Resp
    return _Resp(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 'attachment; filename="nexora-bot-users.csv"'})


def _sqlite_copy(src, dest):
    """
    کپی سازگار از یک دیتابیس SQLite.

    کپی ساده‌ی فایل برای دیتابیسی که WAL دارد کافی نیست: هر چیزی که
    هنوز به فایل اصلی منتقل نشده در «‎-wal» نشسته و در کپی نمی‌آید.
    یعنی نسخه‌ای که «قبل از بازگردانی» گرفته می‌شد می‌توانست ساعت‌ها
    سفارش و پرداخت کم داشته باشد — دقیقاً همان چیزی که قرار بود از
    آن محافظت کند.

    بدتر از کم‌داشتن: اگر همان فایلِ تنها بعداً کنار یک ‎-wal دیگر
    گذاشته شود، SQLite ممکن است آن WAL را رویش اعمال کند.

    backup() خودِ SQLite همه‌ی این‌ها را یک‌جا و سازگار می‌نویسد.
    """
    import sqlite3
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=15)
    try:
        d = sqlite3.connect(str(dest), timeout=15)
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def _bot_rw():
    """اتصال نوشتنی به دیتابیس ربات (برای تنظیمات از پنل)."""
    import sqlite3
    BOT_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(BOT_DB), timeout=10)
    con.row_factory = sqlite3.Row
    return con


#: لوگوی برند — مالک و هر نماینده یکی دارد.
#
#  چرا روی دیسک و نه در دیتابیس: این فایل را مرورگرِ مشتری مستقیم
#  می‌خواهد (مینی‌اپ و صفحه‌ی اشتراک)، و ریختنِ چند صد کیلوبایت باینری
#  در هر `SELECT * FROM tenants` یعنی کند‌کردنِ هر چیزی که مستاجر
#  می‌خواند.
LOGO_DIR = Path(os.getenv("LOGO_DIR", str(CONFIG_PATH.parent / "logos")))

#: سقفِ حجم. بدون Pillow نمی‌شود تصویر را کوچک کرد، پس همین سقف تنها
#  چیزی است که جلوی یک فایلِ ۲۰ مگابایتی را می‌گیرد.
LOGO_MAX_BYTES = 512 * 1024

#: رسید از دوربینِ گوشی می‌آید و بزرگ‌تر است؛ ولی بی‌سقف هم نه.
RECEIPT_MAX_BYTES = 3 * 1024 * 1024

#: فرمت‌های مجاز، با **بایت‌های اولِ فایل** — نه پسوند و نه
#  `Content-Type`، که هر دو را فرستنده می‌نویسد.
#
#  SVG عمداً نیست: می‌تواند `<script>` داشته باشد و این فایل از
#  دامنه‌ی خودِ ما سرو می‌شود، یعنی XSS روی پنل.
def _logo_kind(blob: bytes):
    """پسوند و نوعِ محتوا، یا (None, None) اگر تصویرِ مجاز نباشد."""
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if blob[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None, None


def _logo_path(tid: int):
    """فایلِ لوگوی این مستاجر، اگر باشد."""
    for ext in ("png", "jpg", "webp"):
        p = LOGO_DIR / f"{int(tid)}.{ext}"
        if p.exists():
            return p
    return None


def _logo_url(tid) -> str:
    """نشانیِ عمومیِ لوگو، یا رشته‌ی خالی. رابط از همین تصمیم می‌گیرد."""
    try:
        return f"/api/public/logo/{int(tid)}" if _logo_path(tid) else ""
    except (TypeError, ValueError):
        return ""


def _logo_save(tid: int, payload: dict):
    """
    ذخیره‌ی لوگو از بدنه‌ی JSON با base64.

    چرا base64 و نه multipart: `python-multipart` نصب نیست و افزودنِ
    وابستگی به سروری که با `nexora-cli` به‌روز می‌شود ریسکِ بی‌دلیل
    دارد. برای نیم‌مگابایت، base64 کاملاً بس است.
    """
    import base64
    raw = str((payload or {}).get("data") or "")
    if "," in raw[:80] and raw.lstrip().startswith("data:"):
        raw = raw.split(",", 1)[1]          # data:image/png;base64,....
    raw = raw.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="فایلی فرستاده نشد")

    # سقف را *قبل* از دیکد بسنج: رشته‌ی base64 حدود ۴/۳ برابرِ خودِ
    # فایل است، پس بدونِ این شرط یک رشته‌ی چند مگابایتی دیکد می‌شود و
    # تازه بعدش رد می‌شود.
    if len(raw) > (LOGO_MAX_BYTES * 4) // 3 + 1024:
        raise HTTPException(status_code=413,
                            detail="حجم فایل بیشتر از ۵۱۲ کیلوبایت است")
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="فایل خوانده نشد")

    if len(blob) > LOGO_MAX_BYTES:
        raise HTTPException(status_code=413,
                            detail="حجم فایل بیشتر از ۵۱۲ کیلوبایت است")

    ext, _ctype = _logo_kind(blob)
    if not ext:
        raise HTTPException(status_code=400,
                            detail="فقط PNG، JPEG یا WebP — و فایل باید سالم باشد")

    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    # پسوندِ قبلی ممکن است فرق کند، پس همه را پاک کن وگرنه دو فایل
    # می‌مانند و `_logo_path` قدیمی را برمی‌دارد
    _logo_clear(tid)
    (LOGO_DIR / f"{int(tid)}.{ext}").write_bytes(blob)
    return {"ok": True, "url": _logo_url(tid), "bytes": len(blob)}


def _logo_clear(tid: int):
    for ext in ("png", "jpg", "webp"):
        p = LOGO_DIR / f"{int(tid)}.{ext}"
        if p.exists():
            try:
                p.unlink()
            except OSError:
                log.debug("پاک‌کردن لوگو ناموفق", exc_info=True)


def _root_tenant_row():
    """
    مستاجرِ ریشه — همان مالک.

    **هیچ‌وقت `LIMIT 1` بدون شرط.** اگر ردیفِ مالک یک‌بار پاک و
    دوباره ساخته شود (نصبِ دوباره)، شناسه‌اش از نماینده بزرگ‌تر
    می‌شود و بی‌صدا به ردیفِ اشتباه می‌رسیم. قاعده‌ی مخزن است و تستِ
    درز اجرایش می‌کند.
    """
    con = _bot_conn()
    if not con:
        raise HTTPException(status_code=503, detail="دیتابیس ربات در دسترس نیست")
    try:
        r = con.execute(
            "SELECT * FROM tenants WHERE parent_id IS NULL "
            "ORDER BY id LIMIT 1").fetchone()
    finally:
        con.close()
    if not r:
        raise HTTPException(status_code=404, detail="مستاجر ریشه پیدا نشد")
    return dict(r)


def _bot_db_rw(t):
    """
    `TenantDB` نوشتنی برای این مستاجر.

    `_bot_conn` فقط‌خواندنی است و صندوق پیام باید بنویسد. از همان
    کلاسِ ربات استفاده می‌کنیم، نه SQL دستی — وگرنه قاعده‌ی
    خوانده‌نشده دو جا نوشته می‌شود و روزی از هم دور می‌افتند.
    """
    h = _bot_handlers()
    return h.DB.TenantDB(t["id"])


def _tenant_settings(t):
    """تنظیماتِ یک مستاجر، همیشه dict."""
    try:
        st = json.loads((t or {}).get("settings") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return st if isinstance(st, dict) else {}


def _save_tenant_settings(tid, st):
    """
    نوشتنِ کلِ تنظیمات.

    صداکننده باید dictِ کامل را بدهد — همان که از
    `_tenant_settings` گرفته و دستکاری کرده. نوشتنِ dictِ ناقص
    یعنی هر چه در آن نیست پاک می‌شود.
    """
    con = _bot_rw()
    try:
        con.execute("UPDATE tenants SET settings=? WHERE id=?",
                    (json.dumps(st or {}, ensure_ascii=False), int(tid)))
        con.commit()
    finally:
        con.close()


@app.get("/api/admin/bot/inbox")
def admin_inbox(user_id: int = None, x_admin_password: str = Header(...)):
    """
    گفتگوها برای مالک — فهرست، یا یک گفتگوی مشخص.
    """
    check_auth(x_admin_password)
    return _inbox_read(_root_tenant_row(), user_id)


def _inbox_read(t, user_id=None):
    """صندوقِ یک مستاجر — همان برای مالک و نماینده."""
    try:
        db = _bot_db_rw(t)
        if user_id:
            rows = db.chat_list(int(user_id))
            return {"messages": [{
                "id": r["id"], "from": r["sender"], "body": r["body"],
                "photo": _row_get(r, "photo") or "",
                "orderId": r["order_id"], "at": r["created_at"],
                "read": bool(r["read_at"]),
            } for r in rows]}
        threads = db.chat_threads()
        return {"threads": [{
            "userId": r["user_id"], "tgId": r["tg_id"],
            "name": r["first_name"] or "", "username": r["username"] or "",
            "avatar": _avatar_url(t["id"], r["user_id"]),
            "unread": int(r["unread"] or 0),
            # پیامی که فقط عکس است متنِ خالی دارد؛ بدون این، ردیفِ
            # گفتگو در فهرست خالی می‌ماند و به نظر می‌رسد چیزی نیامده
            "lastBody": ((r["last_body"] or "")[:120]
                         or ("📷 عکس" if _row_get(r, "last_photo") else "")),
            "lastAt": r["last_at"] or "",
        } for r in threads],
            "unread": db.chat_unread_for_admin()}
    except Exception as e:
        log.exception("خواندن صندوق پنل ناموفق")
        raise HTTPException(status_code=503, detail=f"صندوق خوانده نشد: {str(e)[:120]}")


@app.post("/api/admin/bot/inbox/send")
def admin_inbox_send(payload: dict, x_admin_password: str = Header(...)):
    """پاسخ مالک به یک مشتری — هم در صندوق، هم در خودِ ربات."""
    check_auth(x_admin_password)
    return _inbox_send(_root_tenant_row(), payload)


def _inbox_send(t, payload):
    """
    پاسخ به یک مشتری از صندوقِ همین مستاجر.

    `db.chat_add` روی `TenantDB(t["id"])` است، پس گفتگوی مستاجرِ دیگر
    دست‌نیافتنی است — ولی شناسه‌ی مشتری هم باید مالِ همین مستاجر
    باشد، وگرنه پیامی ثبت می‌شد که هیچ‌کس نمی‌دیدش.
    """
    p = payload or {}
    try:
        uid = int(p.get("userId"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="مشتری مشخص نشده")
    body = str(p.get("body") or "").strip()
    raw = p.get("photo")
    if not body and not raw:
        raise HTTPException(status_code=400, detail="پیام خالی است")

    try:
        if not _bot_db_rw(t).get_user_by_id(uid):
            raise HTTPException(status_code=404, detail="این مشتری پیدا نشد")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"صندوق در دسترس نیست: {str(e)[:100]}")
    # عکس *قبل* از ثبتِ پیام ذخیره می‌شود: اگر فایل ننشیند، پیامی
    # هم ثبت نشده. برعکسش یعنی ردیفی در گفتگو که به عکسی اشاره
    # می‌کند که وجود ندارد — و آن، قابِ شکسته‌ی همیشگی است.
    photo = _chat_photo_save(t["id"], uid, raw) if raw else None
    try:
        db = _bot_db_rw(t)
        db.chat_add(uid, "admin", body[:2000], photo=photo)
        db.chat_mark_read(uid, "admin")
        u = db.get_user_by_id(uid)
    except Exception as e:
        log.exception("ثبت پاسخ ناموفق")
        raise HTTPException(status_code=502, detail=f"فرستاده نشد: {str(e)[:120]}")

    # ── خبردادن در تلگرام، بدونِ شلوغ‌کردنِ ربات ──
    #
    # تا امروز **متنِ کاملِ پاسخ** در گفتگوی ربات هم نوشته می‌شد.
    # نتیجه‌اش این بود که هر مکالمه دو بار وجود داشت — یک‌بار در
    # مینی‌اپ و یک‌بار در ربات — و ربات پر می‌شد از چیزی که مشتری
    # همان‌جا در مینی‌اپ داشت.
    #
    # ولی حذفِ کامل هم درست نیست: مشتری‌ای که مینی‌اپ را باز نکند
    # هیچ‌وقت نمی‌فهمد جواب آمده.
    #
    # پس: یک خطِ کوتاه با دکمه‌ی بازکردنِ مینی‌اپ، و **فقط وقتی
    # خبرِ خوانده‌نشده‌ای از قبل نمانده باشد**. اگر پشتیبانی پنج
    # پیامِ پشت‌سرهم بدهد، مشتری یک خبر می‌گیرد نه پنج‌تا؛ و تا
    # نخواندشان، خبرِ تازه‌ای نمی‌آید.
    # The rule (one notice while unread; full text only without a mini app)
    # lives in the bot's `support_reply`: the bot's own admin paths use it
    # too. This copy used to count unread *system* notes as well, so a buyer
    # who never opened the mini app got no notice again, ever.
    if u:
        try:
            h, ctx = _mini_ctx(t)
            h.support_reply(ctx, u, body, photo=photo, stored=True)
        except Exception:
            log.warning("support notice to %s failed", uid, exc_info=True)

    return {"ok": True, "photo": photo or ""}


# ═══════════════════════════════════════════════════════════
#  رویدادهای ربات
#
#  برگه: docs/specs/2026-09-22-bot-events.md
#
#  جدولِ `events` از قبل بود و دو جا نوشته می‌شد و **هیچ‌جا خوانده
#  نمی‌شد**. این‌جا فقط خوانده می‌شود.
#
#  نگاشتِ «نوع → برچسبِ فارسی و شدت» این‌جا دوباره نوشته نمی‌شود:
#  از `bot/events.py` می‌آید، همان چیزی که خودِ ربات هم می‌خواند.
#  دو نسخه‌ی این نگاشت یعنی روزی چیپِ پنل یک چیز بگوید و پیامِ
#  گروه چیزِ دیگری.
#
#  **هیچ آماری از این جدول شمرده نمی‌شود.** فروش از `orders` می‌آید
#  و بس؛ دو منبعِ حقیقت برای یک عدد، همان باگی است که این مخزن
#  هفت بار دیده.
# ═══════════════════════════════════════════════════════════

def _bot_events_mod():
    """ماژولِ `events` ربات — خالص، بدونِ دیتابیس و FastAPI."""
    if "events" in _BOT_MODS:
        return _BOT_MODS["events"]
    import sys as _sys
    bot_dir = str(Path(__file__).resolve().parent.parent / "bot")
    if bot_dir not in _sys.path:
        _sys.path.insert(0, bot_dir)
    try:
        import events as _ev          # noqa: E402
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"فهرستِ رویدادها بارگذاری نشد: {type(e).__name__}")
    _BOT_MODS["events"] = _ev
    return _ev


@app.get("/api/admin/bot/events")
def bot_events(page: int = 1, per: int = 30, errors: int = 0,
               x_admin_password: str = Header(...)):
    """
    رویدادهای ربات — چه چیزی شکست، کِی، و برای چه کسی.

    صفحه‌بندیِ شماره‌دار، نه «نمایش بیشتر» — قاعده‌ی مخزن و
    `test-ui-safety` اجرایش می‌کند.
    """
    check_auth(x_admin_password)
    con = _bot_conn()
    if not con:
        return {"ready": False, "events": [], "total": 0,
                "message": "ربات هنوز راه‌اندازی نشده است"}
    con.close()
    return _events_page(_root_tenant_row(), page, per, errors)


def _events_page(t, page=1, per=30, errors=0):
    """رویدادهای یک مستاجر — همان برای مالک و نماینده."""
    ev = _bot_events_mod()

    per = max(5, min(int(per or 30), 100))
    page = max(1, int(page or 1))

    try:
        res = _bot_db_rw(t).events(
            limit=per, offset=(page - 1) * per,
            only_errors=bool(errors),
            kinds=[k for k in ev.KINDS if ev.is_error(k)])
    except Exception as e:
        log.debug("خواندن رویدادها ناموفق", exc_info=True)
        raise HTTPException(status_code=503,
                            detail=f"خواندن رویدادها ناموفق: {type(e).__name__}")

    out = []
    for r in res["rows"]:
        try:
            data = json.loads(r.get("data") or "{}")
        except Exception:
            data = {}
        out.append({
            "id": r["id"],
            "kind": r["kind"],
            "level": ev.level(r["kind"]),
            "text": ev.describe(r["kind"], data),
            "at": r["created_at"],
            "userId": r.get("user_id"),
            "name": r.get("first_name") or "",
            "username": r.get("username") or "",
            "tgId": r.get("tg_id"),
        })

    return {
        "ready": True,
        "events": out,
        "total": res["total"],
        "page": page,
        "per": per,
        # فهرستِ نوع‌ها هم می‌رود تا پنل بتواند بدونِ نسخه‌ی دومِ
        # نگاشت، چیپ و راهنما بسازد
        "kinds": {k: {"label": v["label"], "level": v["level"],
                      "alert": bool(v.get("alert"))}
                  for k, v in ev.KINDS.items()},
    }


@app.get("/api/admin/bot/alerts")
def admin_alerts(x_admin_password: str = Header(...)):
    """
    چیزهایی که همین حالا کارِ مالک را می‌خواهند — با نام و ساعت.

    چرا فقط شمار کافی نبود: «۲ رسید» می‌گفت چند تا، ولی نمی‌گفت
    *کی* فرستاده و *چقدر* منتظر مانده. مالک باید صفحه‌ی سفارش‌ها را
    باز می‌کرد تا بفهمد کدامش دو ساعت است که معطل است. و همان دو
    ساعت، همان چیزی است که مشتری از آن ناراضی می‌شود.

    ترتیب از قدیمی‌ترین است، نه تازه‌ترین: چیزی که بیشتر منتظر
    مانده بالاتر می‌آید، چون همان است که دارد دیر می‌شود.

    و فیلترِ مستاجر: تا امروز نبود، پس رسیدِ مشتریِ *نماینده* هم به
    مالک هشدار می‌داد — کاری که اصلاً مالِ او نیست و نماینده خودش
    باید جوابش را بدهد.
    """
    check_auth(x_admin_password)
    con = _bot_conn()
    empty = {"receipts": 0, "messages": 0, "items": [], "oldestMin": 0,
             "ready": False}
    if not con:
        return empty
    try:
        root = _root_tenant_row()
        tid = root["id"] if root else None
        if tid is None:
            return empty

        # «چند دقیقه منتظر» را خودِ اسکیوال حساب کند — تبدیلِ رشته‌ی
        # زمان در پایتون یعنی یک جای دیگر که منطقه‌ی زمانی را اشتباه
        # بفهمد
        rc = con.execute(
            "SELECT o.id, o.amount, o.created_at, o.receipt_type, "
            "       u.id uid, u.first_name, u.username, u.tg_id, "
            "       p.name plan, "
            "       CAST((julianday('now') - julianday(o.created_at)) * 1440 AS INTEGER) mins "
            "  FROM orders o "
            "  JOIN users u ON u.id = o.user_id "
            "  LEFT JOIN plans p ON p.id = o.plan_id "
            " WHERE o.tenant_id = ? AND o.status = 'awaiting' "
            " ORDER BY o.created_at ASC LIMIT 30", (tid,)).fetchall()

        ms = con.execute(
            "SELECT m.user_id uid, u.first_name, u.username, u.tg_id, "
            "       MIN(m.created_at) at, COUNT(*) n, "
            "       CAST((julianday('now') - julianday(MIN(m.created_at))) * 1440 AS INTEGER) mins "
            "  FROM chat_messages m "
            "  JOIN users u ON u.id = m.user_id "
            " WHERE m.tenant_id = ? AND m.sender = 'user' AND m.read_at IS NULL "
            " GROUP BY m.user_id ORDER BY at ASC LIMIT 30", (tid,)).fetchall()

        # درخواست‌های تسویه‌ی همکارهای خودِ مالک — نشانِ «همکاری در فروش»
        try:
            aff_req = con.execute(
                "SELECT COUNT(*) FROM affiliate_requests r JOIN affiliates a ON a.id=r.affiliate_id "
                "WHERE r.status='pending' AND a.tenant_id=?", (tid,)).fetchone()[0]
        except Exception:
            aff_req = 0          # جدول هنوز نیست — یعنی درخواستی هم نیست

        # آخرین متنِ هر گفتگو، تا مالک بدون بازکردن بداند موضوع چیست
        last = {}
        for r in ms:
            row = con.execute(
                "SELECT body FROM chat_messages WHERE tenant_id=? AND user_id=? "
                "AND sender='user' ORDER BY id DESC LIMIT 1",
                (tid, r["uid"])).fetchone()
            last[r["uid"]] = (row["body"] if row else "") or ""
    except Exception:
        log.debug("خواندن هشدارها ناموفق", exc_info=True)
        return empty
    finally:
        con.close()

    def who(r):
        return (r["first_name"] or "").strip() or \
               ("@" + r["username"] if r["username"] else "") or \
               f"#{r['tg_id']}"

    items = []
    for r in rc:
        items.append({
            "kind": "receipt", "id": int(r["id"]), "userId": int(r["uid"]),
            "name": who(r), "amount": int(r["amount"] or 0),
            "plan": r["plan"] or "", "at": r["created_at"],
            "waitedMin": max(0, int(r["mins"] or 0)),
            "hasPhoto": (r["receipt_type"] or "") == "photo",
        })
    for r in ms:
        items.append({
            "kind": "message", "id": int(r["uid"]), "userId": int(r["uid"]),
            "name": who(r), "count": int(r["n"] or 0),
            "body": (last.get(r["uid"], "") or "")[:90],
            "at": r["at"], "waitedMin": max(0, int(r["mins"] or 0)),
        })

    items.sort(key=lambda x: -x["waitedMin"])
    return {
        "receipts": len(rc), "messages": sum(int(r["n"] or 0) for r in ms),
        "affRequests": int(aff_req or 0),
        "items": items,
        "oldestMin": items[0]["waitedMin"] if items else 0,
        "ready": True,
    }


@app.get("/api/admin/brand/logo")
def brand_logo_get(x_admin_password: str = Header(...)):
    """
    لوگوی خودِ مالک — شناسه‌اش و اینکه هست یا نه.

    چرا مسیرِ جدا: فهرستِ نماینده‌ها `WHERE parent_id IS NOT NULL`
    است، یعنی خودِ مالک هیچ‌وقت در آن نیست. پس تا امروز هیچ جایی
    برای آپلودِ لوگوی خودش وجود نداشت — قابلیتی که ساخته شده بود ولی
    صاحبِ پنل به آن نمی‌رسید.
    """
    check_auth(x_admin_password)
    con = _bot_conn()
    if not con:
        raise HTTPException(status_code=503, detail="دیتابیس ربات در دسترس نیست")
    try:
        # هیچ‌وقت `LIMIT 1` بدون شرط: ردیفِ مالک اگر یک‌بار پاک و
        # دوباره ساخته شود، شناسه‌اش از نماینده بزرگ‌تر می‌شود.
        r = con.execute(
            "SELECT id, name FROM tenants "
            "WHERE parent_id IS NULL ORDER BY id LIMIT 1").fetchone()
    finally:
        con.close()
    if not r:
        raise HTTPException(status_code=404, detail="مستاجر ریشه پیدا نشد")
    return {"id": r["id"], "name": r["name"] or "",
            "logo": _logo_url(r["id"])}


#: رسیدِ تصویری روی دیسکِ خودمان.
#
#  چرا: نسخه‌ی اول عکس را فقط به گروه مدیریت تلگرام آپلود می‌کرد و
#  `file_id`ش را نگه می‌داشت. اگر گروه تنظیم نشده بود — یا آپلود
#  شکست می‌خورد — `receipt_file` خالی می‌ماند در حالی که
#  `receipt_type` هنوز "photo" بود. نتیجه: پنل ۴۰۴ می‌داد و
#  **عکسِ رسید برای همیشه گم می‌شد**. مشتری پول داده و مدرکش نیست.
#
#  حالا دیسک منبعِ اصلی است و تلگرام فقط راهِ *دیدنِ سریع* در گروه.
RECEIPT_DIR = Path(os.getenv("RECEIPT_DIR", str(CONFIG_PATH.parent / "receipts")))

#: پیشوندی که می‌گوید این رسید روی دیسکِ ماست، نه در تلگرام.
LOCAL_RECEIPT = "local:"


def _image_b64(raw):
    """
    تصویرِ رسید از بدنه‌ی JSON (base64، با یا بی `data:`) — یا None اگر خالی.

    یک‌جا برای رسیدِ مینی‌اپ و رسیدِ پرداختِ همکار: سقف *پیش از* دیکد
    سنجیده می‌شود (base64 حدود ۴/۳ خودِ فایل است) و نوع از بایت‌های اولِ
    فایل، نه از پسوند — SVG عمداً راه ندارد (`_logo_kind`).
    """
    raw = str(raw or "")
    if not raw:
        return None
    import base64
    if raw.lstrip().startswith("data:") and "," in raw[:80]:
        raw = raw.split(",", 1)[1]
    raw = raw.strip()
    if len(raw) > (RECEIPT_MAX_BYTES * 4) // 3 + 1024:
        raise HTTPException(status_code=413, detail="حجم تصویر بیشتر از ۳ مگابایت است")
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="تصویر خوانده نشد")
    if len(blob) > RECEIPT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="حجم تصویر بیشتر از ۳ مگابایت است")
    if not _logo_kind(blob)[0]:
        raise HTTPException(status_code=400, detail="فقط تصویر PNG، JPEG یا WebP")
    return blob


def _receipt_save(order_id: int, blob: bytes):
    """بایت‌های رسید را ذخیره کن و مقدارِ `receipt_file` را برگردان."""
    ext, _ctype = _logo_kind(blob)
    if not ext:
        return None
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{int(order_id)}.{ext}"
    (RECEIPT_DIR / name).write_bytes(blob)
    return LOCAL_RECEIPT + name


def _receipt_local(ref):
    """اگر این ارجاع محلی است، فایلش را بده — وگرنه None."""
    ref = str(ref or "")
    if not ref.startswith(LOCAL_RECEIPT):
        return None
    name = ref[len(LOCAL_RECEIPT):]
    # هیچ‌وقت مسیرِ آمده از بیرون را مستقیم به هم نچسبان
    if "/" in name or "\\" in name or ".." in name:
        return None
    p = RECEIPT_DIR / name
    return p if p.exists() else None


#: عکسِ پروفایلِ مشتری.
#
#  نامِ فایل تصادفی است، نه `<مستاجر>_<کاربر>.png`. چرا: این مسیر
#  عمومی است (تگِ <img> نمی‌تواند هدرِ احراز هویت بفرستد)، و نامِ
#  قابل‌حدس یعنی هر کسی می‌تواند عکسِ هر مشتری را با شمردنِ شناسه‌ها
#  بردارد. نامِ تصادفی همان «آدرس، خودش کلید است».
AVATAR_DIR = Path(os.getenv("AVATAR_DIR", str(CONFIG_PATH.parent / "avatars")))
AVATAR_MAX_BYTES = 512 * 1024


def _avatar_find(tid, uid):
    """فایلِ عکسِ این کاربر، اگر باشد."""
    if not AVATAR_DIR.exists():
        return None
    for p in AVATAR_DIR.glob(f"{int(tid)}_{int(uid)}_*"):
        if p.is_file():
            return p
    return None


def _avatar_url(tid, uid):
    p = _avatar_find(tid, uid)
    return f"/api/public/avatar/{p.name}" if p else ""


def _avatar_clear(tid, uid):
    while True:
        p = _avatar_find(tid, uid)
        if not p:
            return
        try:
            p.unlink()
        except OSError:
            return


def _avatar_save(tid, uid, raw):
    """base64 → فایل. برمی‌گرداند نشانی، یا خطا می‌دهد."""
    import base64
    import secrets as _s
    raw = str(raw or "")
    if raw.lstrip().startswith("data:") and "," in raw[:80]:
        raw = raw.split(",", 1)[1]
    raw = raw.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="عکسی فرستاده نشد")
    if len(raw) > (AVATAR_MAX_BYTES * 4) // 3 + 1024:
        raise HTTPException(status_code=413, detail="حجم عکس بیشتر از ۵۱۲ کیلوبایت است")
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="عکس خوانده نشد")
    if len(blob) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="حجم عکس بیشتر از ۵۱۲ کیلوبایت است")
    ext, _c = _logo_kind(blob)
    if not ext:
        raise HTTPException(status_code=400, detail="فقط PNG، JPEG یا WebP")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    _avatar_clear(tid, uid)
    name = f"{int(tid)}_{int(uid)}_{_s.token_hex(8)}.{ext}"
    (AVATAR_DIR / name).write_bytes(blob)
    return f"/api/public/avatar/{name}"


@app.get("/api/public/avatar/{name}")
def public_avatar(name: str):
    """
    عکسِ پروفایل. نامِ فایل تصادفی است، پس خودش کلیدِ دسترسی است.
    """
    # نامِ آمده از بیرون هرگز مستقیم به مسیر نمی‌چسبد
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=404, detail="پیدا نشد")
    p = AVATAR_DIR / name
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="پیدا نشد")
    blob = p.read_bytes()
    _e, ctype = _logo_kind(blob)
    if not ctype:
        raise HTTPException(status_code=404, detail="پیدا نشد")
    return Response(content=blob, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=600"})


#: عکسِ داخل گفتگو.
#
#  همان قاعده‌ی عکسِ پروفایل: نامِ فایل تصادفی است و خودش کلیدِ
#  دسترسی، چون تگِ <img> نمی‌تواند هدرِ احراز هویت بفرستد. نامِ
#  قابل‌حدس یعنی هر کسی با شمردنِ شناسه‌ها عکس‌های پشتیبانیِ بقیه را
#  برمی‌دارد.
#
#  و حدِ حجم بالاتر از پروفایل است: عکسِ صفحه‌ی گوشی معمولاً از یک
#  آواتار بزرگ‌تر است و ۵۱۲ کیلوبایت بیشترشان را رد می‌کرد.
CHAT_DIR = Path(os.getenv("CHAT_DIR", str(CONFIG_PATH.parent / "chat")))
CHAT_MAX_BYTES = 3 * 1024 * 1024


def _chat_photo_save(tid, uid, raw):
    """base64 → فایل. برمی‌گرداند نشانی، یا خطا می‌دهد."""
    import base64
    import secrets as _s
    raw = str(raw or "")
    if raw.lstrip().startswith("data:") and "," in raw[:80]:
        raw = raw.split(",", 1)[1]
    raw = raw.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="عکسی فرستاده نشد")
    if len(raw) > (CHAT_MAX_BYTES * 4) // 3 + 1024:
        raise HTTPException(status_code=413, detail="حجم عکس بیشتر از ۳ مگابایت است")
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="عکس خوانده نشد")
    if len(blob) > CHAT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="حجم عکس بیشتر از ۳ مگابایت است")
    ext, _c = _logo_kind(blob)
    if not ext:
        raise HTTPException(status_code=400, detail="فقط PNG، JPEG یا WebP")

    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{int(tid)}_{int(uid)}_{_s.token_hex(12)}.{ext}"
    (CHAT_DIR / name).write_bytes(blob)
    return f"/api/public/chat-photo/{name}"


def _chat_photo_bytes(url):
    """بایت‌های عکسِ یک پیام، برای فرستادنش در تلگرام."""
    name = str(url or "").rsplit("/", 1)[-1]
    if not name or "\\" in name or ".." in name:
        return None
    p = CHAT_DIR / name
    try:
        return p.read_bytes() if p.is_file() else None
    except OSError:
        return None


@app.get("/api/public/chat-photo/{name}")
def public_chat_photo(name: str):
    """عکسِ گفتگو. نامِ فایل تصادفی است، پس خودش کلیدِ دسترسی است."""
    # نامِ آمده از بیرون هرگز مستقیم به مسیر نمی‌چسبد
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=404, detail="پیدا نشد")
    p = CHAT_DIR / name
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="پیدا نشد")
    blob = p.read_bytes()
    _e, ctype = _logo_kind(blob)
    if not ctype:
        raise HTTPException(status_code=404, detail="پیدا نشد")
    return Response(content=blob, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/public/logo/{tid}")
def public_logo(tid: int):
    """
    لوگوی یک مستاجر — عمومی، چون مینی‌اپ و صفحه‌ی اشتراک بدون احراز
    هویت بازش می‌کنند. چیزی جز بایت‌های تصویر در پاسخ نیست.
    """
    p = _logo_path(tid)
    if not p:
        raise HTTPException(status_code=404, detail="لوگویی ثبت نشده")
    blob = p.read_bytes()
    _ext, ctype = _logo_kind(blob)
    if not ctype:
        # فایلِ روی دیسک دیگر تصویر نیست — سرو نکن
        raise HTTPException(status_code=404, detail="لوگویی ثبت نشده")
    return Response(content=blob, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=300"})


def _bot_dir():
    return Path(__file__).resolve().parent.parent / "bot"


def _ensure_bot_db():
    """
    اگر دیتابیس ربات نبود، می‌سازدش.

    برمی‌گرداند: (موفق, پیام خطا)
    پیام خطا دقیق است تا کاربر بداند چه کاری کند — نه یک «نصب نشده» مبهم.
    """
    # وجود فایل کافی نیست — ممکن است ساخته شده ولی جدول‌ها نباشند
    # (نصب نیمه‌کاره، یا فایلی که دستی کپی شده). این حالت خطای
    # «no such table» می‌دهد که برای کاربر بی‌معناست.
    if BOT_DB.exists():
        try:
            import sqlite3
            con = sqlite3.connect(f"file:{BOT_DB}?mode=ro", uri=True, timeout=5)
            has = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'"
            ).fetchone()
            con.close()
            if has:
                return True, None
        except Exception:
            pass
        # فایل هست ولی ناقص — از نو می‌سازیم

    bd = _bot_dir()
    if not (bd / "db.py").exists():
        return False, (
            f"پوشه‌ی ربات پیدا نشد ({bd}). "
            "احتمالاً به‌روزرسانی ناقص بوده — روی سرور اجرا کنید: nexora update"
        )

    # اول تلاش مستقیم (سریع‌تر و خطای واضح‌تر می‌دهد)
    try:
        import importlib.util
        BOT_DB.parent.mkdir(parents=True, exist_ok=True)
        os.environ["BOT_DB_PATH"] = str(BOT_DB)

        spec = importlib.util.spec_from_file_location("_nexora_botdb", bd / "db.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.init_db()

        if BOT_DB.exists():
            return True, None
    except Exception as e:
        direct_err = str(e)[:200]
    else:
        direct_err = "ساخته نشد"

    # تلاش دوم: پروسه‌ی جدا
    try:
        import subprocess
        import sys as _sys
        code = (
            "import os, sys\n"
            f"os.environ['BOT_DB_PATH'] = r'{BOT_DB}'\n"
            f"sys.path.insert(0, r'{bd}')\n"
            "import db\n"
            "db.init_db()\n"
        )
        p = subprocess.run([_sys.executable, "-c", code],
                           timeout=30, capture_output=True, text=True)
        if BOT_DB.exists():
            return True, None
        err = (p.stderr or "").strip()[-250:] or direct_err
        return False, f"ساخت دیتابیس ربات ناموفق بود: {err}"
    except Exception as e:
        return False, f"ساخت دیتابیس ربات ناموفق بود: {str(e)[:200]}"


@app.get("/api/admin/bot/settings")
def bot_settings_get(x_admin_password: str = Header(...)):
    """
    تنظیمات ربات اصلی — توکن، پنل، گروه، کارت‌ها، سکه.

    این endpoint هرگز نباید ۵۰۰ بدهد: اگر داده‌ی دیتابیس خراب باشد،
    یک پاسخ خالی برمی‌گرداند تا پنل باز شود و کاربر بتواند از نو
    تنظیم کند — نه اینکه با صفحه‌ی سفید روبه‌رو شود.
    """
    check_auth(x_admin_password)
    okdb, err = _ensure_bot_db()

    con = _bot_conn()
    if not con:
        return {"ready": False, "tenant": None, "error": err,
                "botDir": str(_bot_dir()), "dbPath": str(BOT_DB)}
    try:
        try:
            row = con.execute(
                "SELECT * FROM tenants WHERE parent_id IS NULL ORDER BY id LIMIT 1"
            ).fetchone()
        except Exception as e:
            # جدول ناقص یا اسکیمای قدیمی — پنل باید باز شود
            return {"ready": False, "tenant": None,
                    "error": f"خواندن تنظیمات ناموفق: {str(e)[:150]}"}
        if not row:
            return {"ready": True, "tenant": None}

        t = dict(row)
        # توکن‌ها را ماسک می‌کنیم — در پاسخ کامل نمی‌فرستیم
        for k in ("bot_token", "panel_pass", "panel_token"):
            if t.get(k):
                t[k + "_set"] = True
                t[k] = t[k][:6] + "…" if len(str(t[k])) > 8 else "…"
            else:
                t[k + "_set"] = False
        # کلیدِ هوش مصنوعی داخلِ settings است، پس از حلقه‌ی رازهای
        # بالا رد نمی‌شود. جدا ماسکش می‌کنیم.
        try:
            _ai = (t.get("settings") or {})
            if isinstance(_ai, str):
                _ai = json.loads(_ai or "{}")
            if isinstance(_ai, dict) and isinstance(_ai.get("ai"), dict):
                _k = str(_ai["ai"].get("api_key") or "")
                if _k:
                    _ai["ai"] = {**_ai["ai"],
                                 "api_key": (_k[:6] + "…" if len(_k) > 8 else "…")}
                    t["settings"] = _ai
        except Exception:
            log.debug("ماسک‌کردن کلید هوش مصنوعی ناموفق", exc_info=True)

        # settings و topics باید همیشه دیکشنری باشند.
        # اگر مقدارشان "null" یا "[]" باشد، json.loads چیزی برمی‌گرداند
        # که دیکشنری نیست و فرانت‌اند روی آن کرش می‌کند.
        for k in ("topics", "settings"):
            try:
                parsed = json.loads(t.get(k) or "{}")
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {}
            t[k] = parsed if isinstance(parsed, dict) else {}

        # فیلدهای متنی نباید None باشند — فرانت‌اند روی input می‌گذاردشان
        for k in ("name", "bot_username", "panel_url", "panel_user",
                  "owner_tg_id", "admin_group_id", "default_inbound"):
            if t.get(k) is None:
                t[k] = ""

        return {"ready": True, "tenant": t}
    except Exception as e:
        return {"ready": False, "tenant": None,
                "error": f"خطای غیرمنتظره: {str(e)[:150]}"}
    finally:
        con.close()


@app.put("/api/admin/bot/settings")
def bot_settings_put(payload: dict, x_admin_password: str = Header(...)):
    """ذخیره تنظیمات ربات اصلی."""
    check_auth(x_admin_password)
    okdb, err = _ensure_bot_db()
    if not okdb:
        raise HTTPException(status_code=400, detail=err or "ماژول ربات در دسترس نیست")

    con = _bot_rw()
    try:
        row = con.execute(
            "SELECT id FROM tenants WHERE parent_id IS NULL ORDER BY id LIMIT 1"
        ).fetchone()

        name = (payload.get("name") or "Nexora").strip()
        if not row:
            cur = con.execute(
                "INSERT INTO tenants (name, is_active, credit) VALUES (?,1,-1)", (name,)
            )
            tid = cur.lastrowid
        else:
            tid = row["id"]

        # `settings` کلِ دیکشنری را *جایگزین* می‌کند. سه صفحه (پیگیریِ تست،
        # پاسخ‌های آماده، آدرسِ کانال) اگر خواندنِ تنظیمات شکست می‌خورد، با
        # دیکشنریِ خالی ادامه می‌دادند و ذخیره‌شان فقط یک کلید را پس
        # می‌فرستاد — یعنی همه‌ی متن‌ها، سکه، کارت‌ها و بقیه پاک می‌شد.
        # رابط اصلاح شد؛ این نگهبان برای صفحه‌ی بعدی است که همین را تکرار
        # کند. پیش از هر نوشتنی، تا ردِ آن هیچ اثرِ نیمه‌کاره‌ای نگذارد.
        _incoming = payload.get("settings")
        if row and isinstance(_incoming, dict):
            try:
                _cur = json.loads(con.execute(
                    "SELECT settings FROM tenants WHERE id=?",
                    (tid,)).fetchone()["settings"] or "{}")
            except Exception:
                _cur = {}
            if isinstance(_cur, dict) and len(_cur) >= 4:
                _lost = set(_cur) - set(_incoming)
                if len(_lost) * 2 > len(_cur):
                    raise HTTPException(
                        status_code=400,
                        detail=(f"تنظیماتِ ناقص — {_fnum(len(_lost))} از {_fnum(len(_cur))} بخشِ "
                                "تنظیماتِ ربات پاک می‌شد؛ ذخیره نشد. صفحه را تازه کنید."))

        # فیلدهای ساده — فقط اگر مقدار داده شده باشد به‌روز می‌شوند
        simple = ["name", "bot_username", "owner_tg_id", "panel_url", "panel_user",
                  "default_inbound", "admin_group_id", "is_active"]
        for k in simple:
            if k in payload:
                con.execute(f"UPDATE tenants SET {k}=? WHERE id=?", (payload[k], tid))

        # فیلدهای حساس — فقط وقتی مقدار جدید و غیرخالی بیاید
        for k in ("bot_token", "panel_pass", "panel_token"):
            v = payload.get(k)
            if v and not str(v).endswith("…"):
                con.execute(f"UPDATE tenants SET {k}=? WHERE id=?", (v, tid))

        # کلیدِ ماسک‌شده نباید ذخیره شود.
        #
        # صفحه تنظیمات را می‌خواند (با کلیدِ بریده)، چیزِ دیگری را
        # عوض می‌کند و همان را پس می‌فرستد. بدونِ این نگهبان، همان
        # ذخیره کلیدِ واقعی را با «sk-ab…» جایگزین می‌کرد و سرویس
        # بی‌صدا از کار می‌افتاد.
        _newst = payload.get("settings")
        if isinstance(_newst, dict) and isinstance(_newst.get("ai"), dict):
            _nk = str(_newst["ai"].get("api_key") or "")
            if _nk.endswith("…"):
                try:
                    _old = json.loads(con.execute(
                        "SELECT settings FROM tenants WHERE id=?",
                        (tid,)).fetchone()["settings"] or "{}")
                except Exception:
                    _old = {}
                _newst["ai"] = {**_newst["ai"],
                                "api_key": ((_old.get("ai") or {}).get("api_key")
                                            or "")}

        for k in ("topics", "settings"):
            if k in payload and isinstance(payload[k], (dict, list)):
                con.execute(f"UPDATE tenants SET {k}=? WHERE id=?",
                            (json.dumps(payload[k], ensure_ascii=False), tid))

        con.commit()
        return {"ok": True, "tenantId": tid}
    finally:
        con.close()


@app.get("/api/admin/bot/plans")
def bot_plans_get(x_admin_password: str = Header(...)):
    """لیست پلن‌های فروش."""
    check_auth(x_admin_password)
    con = _bot_conn()
    if not con:
        return {"plans": [], "ready": False}
    try:
        # به مستاجر اصلی محدود، مثل مسیر ذخیره.
        #
        # قبلاً بی‌قید بود. تا وقتی فقط یک ربات وجود داشت فرقی
        # نمی‌کرد، ولی از وقتی نماینده می‌تواند ربات خودش را داشته
        # باشد، پلن‌های او در فهرست پلن‌های مالک ظاهر می‌شدند — و
        # چون *ذخیره* به مستاجر اصلی محدود است، حذفشان از آن فهرست
        # پاسخ «ok» می‌داد و هیچ کاری نمی‌کرد.
        root = con.execute(
            "SELECT id FROM tenants WHERE parent_id IS NULL "
            "ORDER BY id LIMIT 1").fetchone()
        if root:
            rows = con.execute(
                "SELECT * FROM plans WHERE tenant_id=? ORDER BY sort_order, id",
                (root["id"],)).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM plans ORDER BY sort_order, id").fetchall()
        return {"plans": [dict(r) for r in rows], "ready": True,
                "canSellLicenses": _can_sell_licenses()}
    except Exception:
        return {"plans": [], "ready": True, "canSellLicenses": False}
    finally:
        con.close()


def _plan_cols(con):
    """
    ستون‌های نوع و تبِ پلن. مهاجرتِ ربات هم می‌سازدشان، ولی پنل ممکن است
    چند ثانیه زودتر از ربات بالا بیاید — همان دلیلِ `cost`.
    """
    have = {r[1] for r in con.execute("PRAGMA table_info(plans)")}
    if "kind" not in have:
        con.execute("ALTER TABLE plans ADD COLUMN kind TEXT DEFAULT 'volume'")
    if "tab" not in have:
        con.execute("ALTER TABLE plans ADD COLUMN tab TEXT DEFAULT ''")
    # Phase 4 (selling Pro): the license a `pro_license` plan sells
    if "license_plan" not in have:
        con.execute("ALTER TABLE plans ADD COLUMN license_plan TEXT DEFAULT ''")
    if "periods" not in have:
        con.execute("ALTER TABLE plans ADD COLUMN periods INTEGER DEFAULT 1")


def _can_sell_licenses():
    """Only the owner's own server, where the license issuer's owner token is
    readable (bot/license_sale.py). The plan editor offers the kind only then."""
    try:
        return bool(_bot_handlers().LS.available())
    except Exception:
        log.warning("license sale availability unknown", exc_info=True)
        return False


@app.put("/api/admin/bot/plans")
def bot_plans_put(payload: dict, x_admin_password: str = Header(...)):
    """ذخیره کامل لیست پلن‌ها (جایگزینی)."""
    check_auth(x_admin_password)
    okdb, err = _ensure_bot_db()
    if not okdb:
        raise HTTPException(status_code=400, detail=err or "ماژول ربات در دسترس نیست")

    plans = payload.get("plans")
    if not isinstance(plans, list):
        raise HTTPException(status_code=400, detail="فهرست پلن‌ها نامعتبر است")

    con = _bot_rw()
    try:
        row = con.execute(
            "SELECT id FROM tenants WHERE parent_id IS NULL ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="ابتدا تنظیمات ربات را ذخیره کنید")
        tid = row["id"]

        keep = [p.get("id") for p in plans if p.get("id")]
        if keep:
            ph = ",".join("?" * len(keep))
            con.execute(
                f"DELETE FROM plans WHERE tenant_id=? AND id NOT IN ({ph})",
                [tid] + keep)
        else:
            con.execute("DELETE FROM plans WHERE tenant_id=?", (tid,))

        _plan_cols(con)
        core = _bot_core()
        sell_ok = None
        for i, p in enumerate(plans):
            kind = core.clean_plan_kind(p.get("kind"))
            lic = kind == "pro_license"
            if lic:
                if sell_ok is None:
                    sell_ok = _can_sell_licenses()
                if not sell_ok:
                    # Refused, not saved and hidden: a plan the bot can never
                    # deliver would sit in the list as if it were for sale.
                    raise HTTPException(
                        status_code=400,
                        detail=f"«{p.get('name') or 'پلن'}» مجوز Pro است، ولی این سرور ناشرِ "
                               "مجوز ندارد؛ فقط روی سروری که ناشر رویش نصب است فروخته می‌شود")
                if int(p.get("price") or 0) <= 0:
                    raise HTTPException(status_code=400,
                                        detail=f"«{p.get('name') or 'پلن'}»: مجوز Pro قیمت می‌خواهد")
            vals = (
                p.get("name", "پلن"), p.get("description", ""),
                # A license has no volume, days, users or inbound; zero them so
                # no report ever reads a leftover number from the editor.
                0 if lic else int(p.get("gb") or 0), 0 if lic else int(p.get("days") or 0),
                0 if lic else int(p.get("ip_limit") or 0), int(p.get("price") or 0),
                None if lic else p.get("inbound_id"), 1 if p.get("is_active", True) else 0,
                0 if lic else (1 if p.get("is_trial") else 0), i,
                kind, core.clean_plan_tab(p.get("tab")),
                core.clean_license_plan(p.get("license_plan")) if lic else "",
                core.clean_periods(p.get("periods")) if lic else 1,
            )
            if p.get("id"):
                con.execute(
                    "UPDATE plans SET name=?,description=?,gb=?,days=?,ip_limit=?,"
                    "price=?,inbound_id=?,is_active=?,is_trial=?,sort_order=?,"
                    "kind=?,tab=?,license_plan=?,periods=? WHERE id=? AND tenant_id=?",
                    vals + (p["id"], tid))
            else:
                con.execute(
                    "INSERT INTO plans (name,description,gb,days,ip_limit,price,"
                    "inbound_id,is_active,is_trial,sort_order,kind,tab,license_plan,"
                    "periods,tenant_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    vals + (tid,))

        con.commit()
        return {"ok": True, "count": len(plans)}
    finally:
        con.close()


@app.post("/api/admin/bot/orders/{order_id}/reject-with-reason")
def bot_reject_reason(order_id: int, payload: dict,
                      x_admin_password: str = Header(...)):
    """
    رد سفارش با دلیل مشخص.

    دلیل در admin_note ذخیره می‌شود و ربات آن را برای مشتری می‌فرستد
    و سکه‌های خرج‌شده را برمی‌گرداند.
    """
    check_auth(x_admin_password)
    reason = (payload or {}).get("reason", "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="دلیل رد را بنویسید")

    if not BOT_DB.exists():
        raise HTTPException(status_code=400, detail="دیتابیس ربات موجود نیست")

    con = _bot_rw()
    try:
        row = con.execute("SELECT status FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="سفارش پیدا نشد")
        if row["status"] not in ("awaiting", "review"):
            raise HTTPException(status_code=400, detail="این سفارش قبلاً بررسی شده است")

        # ربات این وضعیت را می‌بیند، به مشتری خبر می‌دهد و سکه را برمی‌گرداند
        con.execute(
            "UPDATE orders SET status='panel_reject', admin_note=?, "
            "reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (reason[:400], order_id))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@app.post("/api/admin/bot/orders/{order_id}/{action}")
def bot_order_action(order_id: int, action: str, x_admin_password: str = Header(...)):
    """
    تایید یا رد سفارش از داخل پنل.

    نکته: ساخت کانفیگ و اطلاع به مشتری کار ربات است. پنل فقط وضعیت را
    علامت‌گذاری می‌کند و ربات در چرخه‌ی بعدی‌اش آن را می‌بیند و انجام می‌دهد.
    """
    check_auth(x_admin_password)
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="عملیات نامعتبر")
    if not BOT_DB.exists():
        raise HTTPException(status_code=400, detail="دیتابیس ربات موجود نیست")

    con = _bot_rw()
    try:
        row = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="سفارش پیدا نشد")
        if row["status"] not in ("awaiting", "review"):
            raise HTTPException(status_code=400, detail="این سفارش قبلاً بررسی شده است")

        new_status = "panel_approve" if action == "approve" else "rejected"
        con.execute(
            "UPDATE orders SET status=?, reviewed_at=CURRENT_TIMESTAMP, admin_note=? "
            "WHERE id=?",
            (new_status, "از پنل مدیریت", order_id))
        con.commit()
        return {"ok": True, "status": new_status}
    finally:
        con.close()


# ═══════════════════════════════════════════════════════════
#  خودترمیمی هنگام راه‌اندازی
#
#  بک‌اند تنها جزئی است که بعد از هر به‌روزرسانی حتماً ری‌استارت
#  می‌شود. پس هر کاری که ممکن است در به‌روزرسانی جا بماند را
#  اینجا انجام می‌دهیم — تا کاربر هیچ‌وقت مجبور به کار دستی نشود.
# ═══════════════════════════════════════════════════════════

def _root_dir():
    return Path(__file__).resolve().parent.parent


def _selfheal_cli():
    """دستور nexora را با نسخه‌ی نصب‌شده همگام می‌کند."""
    src = _root_dir() / "nexora-cli.sh"
    dst = Path("/usr/local/bin/nexora")
    if not src.exists() or not dst.parent.exists():
        return None

    data = src.read_bytes()
    if dst.exists() and dst.read_bytes() == data:
        return None

    tmp = dst.with_suffix(".new")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o755)
    os.replace(tmp, dst)   # اتمی — اگر همان لحظه اجرا شود، نصفه نمی‌ماند
    return "CLI به‌روز شد"


def _selfheal_scripts():
    """دسترسی اجرایی اسکریپت‌ها را برمی‌گرداند."""
    fixed = 0
    for p in _root_dir().glob("*.sh"):
        try:
            if not os.access(p, os.X_OK):
                os.chmod(p, 0o755)
                fixed += 1
        except OSError as _exc:
            log.warning("selfheal: script permission check: %s", _exc)
    return f"{fixed} اسکریپت اجرایی شد" if fixed else None


def _selfheal_bot_deps():
    """وابستگی‌های ربات را در صورت نبود نصب می‌کند."""
    root = _root_dir()
    req = root / "bot" / "requirements.txt"
    if not req.exists():
        return None

    try:
        import importlib
        importlib.import_module("requests")
        return None          # قبلاً هست
    except ImportError:
        pass

    pip = root / "backend" / "venv" / "bin" / "pip"
    if not pip.exists():
        return None

    try:
        import subprocess
        subprocess.run([str(pip), "install", "-r", str(req), "-q"],
                       timeout=180, capture_output=True)
        return "وابستگی‌های ربات نصب شد"
    except Exception:
        return None


def _selfheal_bot_service():
    """اگر ماژول ربات هست ولی سرویسش نیست، می‌سازدش."""
    root = _root_dir()
    if not (root / "bot" / "run.py").exists():
        return None

    svc = Path("/etc/systemd/system/nexora-bot.service")
    if svc.exists() or not svc.parent.exists():
        return None

    python = root / "backend" / "venv" / "bin" / "python"
    if not python.exists():
        return None

    try:
        svc.write_text(f"""[Unit]
Description=Nexora Telegram Bot
After=network.target nexora-panel.service

[Service]
Type=simple
WorkingDirectory={root}/bot
Environment="BOT_DB_PATH={root}/data/bot.db"
Environment="PANEL_CONFIG={root}/data/config.json"
ExecStart={python} run.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
""", encoding="utf-8")
        os.chmod(svc, 0o600)

        import subprocess
        subprocess.run(["systemctl", "daemon-reload"], timeout=20, capture_output=True)
        return "سرویس ربات ساخته شد"
    except Exception:
        return None


def _selfheal_backup_cron():
    """بک‌آپ روزانه را در صورت نبود تنظیم می‌کند."""
    root = _root_dir()
    cfg = root / "data" / "config.json"
    if not cfg.exists():
        return None

    try:
        import subprocess
        cur = subprocess.run(["crontab", "-l"], capture_output=True,
                             text=True, timeout=15).stdout or ""
        if "nexora" in cur and "config.json" in cur:
            return None

        line = (f"0 3 * * * cp {cfg} /root/backups/config-$(date +\\%Y\\%m\\%d).json 2>/dev/null")
        Path("/root/backups").mkdir(parents=True, exist_ok=True)
        new_tab = (cur.rstrip("\n") + "\n" + line + "\n").lstrip("\n")
        subprocess.run(["crontab", "-"], input=new_tab, text=True,
                       timeout=15, capture_output=True)
        return "بک‌آپ روزانه تنظیم شد"
    except Exception:
        return None


HISTORY_PATH = Path(os.getenv("HISTORY_PATH",
                              str(CONFIG_PATH.parent / "usage-history.json")))

#: چند نمونه نگه داریم. هر ۵ دقیقه یک نمونه یعنی ۵۷۶ نمونه = دو روز.
#: بیشتر از این، فایل بزرگ می‌شود بدون اینکه به تصمیم کمکی کند.
HISTORY_MAX = 576


def _history_load():
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _history_sample():
    """
    یک نمونه از وضعیت سرور.

    بدون تاریخچه، «پیک سرور کی است؟» جواب ندارد و زمان‌بندی نگهداری
    فقط حدس است. نمونه‌ها همراه همان حلقه‌ی پنج‌دقیقه‌ای گرفته می‌شوند
    تا بار اضافه‌ای به سرور تحمیل نشود.
    """
    if not MONITOR:
        return
    try:
        snap = MONITOR.snapshot(include=["cpu", "memory", "connections"])
    except Exception:
        return

    def _val(key):
        for m in snap.get("metrics") or []:
            if m.get("key") == key and isinstance(m.get("value"), (int, float)):
                return round(float(m["value"]), 1)
        return None

    conn = (snap.get("sections") or {}).get("connections") or {}
    row = {
        "t": datetime.now().isoformat(timespec="minutes"),
        "cpu": _val("cpu"),
        "mem": _val("memory"),
        "conn": int(conn.get("total") or 0),
        "ips": int(conn.get("uniqueIps") or 0),
    }

    rows = _history_load()
    rows.append(row)
    rows = rows[-HISTORY_MAX:]
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
    except Exception as _exc:
        log.warning("usage history dir: %s", _exc)


@app.get("/api/admin/usage-history")
def usage_history(hours: int = 24, x_admin_password: str = Header(...)):
    """تاریخچه‌ی مصرف سرور و ساعت پیک."""
    check_auth(x_admin_password)
    from datetime import timedelta

    rows = _history_load()
    if hours and hours > 0:
        cut = (datetime.now() - timedelta(hours=int(hours))).isoformat(
            timespec="minutes")
        rows = [r for r in rows if str(r.get("t") or "") >= cut]

    # میانگین هر ساعت شبانه‌روز — همان چیزی که ساعت کم‌مصرف را نشان
    # می‌دهد و زمان‌بندی نگهداری باید رویش بنشیند
    buckets = {}
    for r in _history_load():
        try:
            h = int(str(r["t"])[11:13])
        except (ValueError, KeyError, IndexError):
            continue
        b = buckets.setdefault(h, {"conn": 0, "cpu": 0.0, "n": 0})
        b["conn"] += int(r.get("conn") or 0)
        b["cpu"] += float(r.get("cpu") or 0)
        b["n"] += 1

    hourly = [{"hour": h,
               "conn": round(b["conn"] / b["n"], 1),
               "cpu": round(b["cpu"] / b["n"], 1)}
              for h, b in sorted(buckets.items()) if b["n"]]

    quietest = min(hourly, key=lambda x: x["conn"])["hour"] if hourly else None
    busiest = max(hourly, key=lambda x: x["conn"])["hour"] if hourly else None

    return {"samples": rows, "hourly": hourly, "count": len(rows),
            "quietestHour": quietest, "busiestHour": busiest,
            "maxSamples": HISTORY_MAX}


@app.get("/api/admin/top-clients")
def top_clients(limit: int = 10, x_admin_password: str = Header(...)):
    """
    پرمصرف‌ترین مشتری‌ها بر اساس ترافیک واقعی پنل.

    شمارش اتصال فقط IP می‌دهد؛ این می‌گوید کدام *مشتری* — با نام
    کانفیگ، حجم مصرفی و سهمش از کل — بیشترین بار را می‌برد.
    """
    check_auth(x_admin_password)

    clients, _groups, err = _read_xui_clients()
    if clients is None:
        return {"ready": False, "error": err or "دیتابیس پنل در دسترس نیست",
                "clients": []}

    out = []
    for c in clients:
        email = c.get("email")
        if not email:
            continue
        used = int(c.get("used") or 0)
        quota = int(c.get("totalGB") or 0)
        out.append({
            "email": email,
            "group": c.get("group") or "بدون گروه",
            "usedBytes": used,
            "usedGB": round(used / (1024 ** 3), 2),
            "quotaGB": round(quota / (1024 ** 3), 1) if quota else 0,
            "pctOfQuota": (round(used * 100.0 / quota, 1) if quota else None),
            "enable": bool(c.get("enable", True)),
            "expiryTime": c.get("expiry_time") or c.get("expiryTime") or 0,
        })

    total = sum(x["usedBytes"] for x in out) or 1
    for x in out:
        x["pctOfAll"] = round(x["usedBytes"] * 100.0 / total, 1)

    out.sort(key=lambda x: x["usedBytes"], reverse=True)
    return {"ready": True, "clients": out[:max(1, min(limit, 100))],
            "totalClients": len(out),
            "totalUsedGB": round(total / (1024 ** 3), 1)}



#: پیش‌فرض زمان‌بندی نگهداری.
#
# ۰۵:۰۰ به وقت سرور انتخاب شده چون کم‌ترین مصرف VPN ایرانی همان‌جاست:
# شب‌روها خوابیده‌اند و صبح‌کارها هنوز بیدار نشده‌اند. عمل پیش‌فرض هم
# ری‌استارت Xray است نه ریبوت سرور — یکی حدود یک ثانیه قطعی دارد،
# دیگری یک تا دو دقیقه.
MAINT_DEFAULT = {
    "enabled": False,
    "action": "xray",          # xray | reboot
    "hour": 5,
    "minute": 0,
    "days": [],                # خالی یعنی هر روز
    "skipIfBusy": True,
    "busyThreshold": 20,
    "confirmedReboot": False,  # ریبوت تا تایید صریح مدیر اجرا نمی‌شود
    "lastRun": None,
    "lastResult": None,
}


def _maint_conf():
    cfg = load_config()
    m = dict(MAINT_DEFAULT)
    got = cfg.get("maintenance")
    if isinstance(got, dict):
        m.update({k: v for k, v in got.items() if k in MAINT_DEFAULT})
    return m


def _maint_save(m):
    cfg = load_config()
    cfg["maintenance"] = m
    save_config(cfg)


def _maint_busy():
    """آیا سرور الان شلوغ است؟ برای اینکه وسط پیک ری‌استارت نکنیم."""
    if not MONITOR:
        return False, 0
    try:
        c = MONITOR.connections() or {}
        n = int(c.get("total") or 0)
        return n, n
    except Exception:
        return 0, 0


def _maint_run(action):
    """اجرای واقعی نگهداری. خروجی: (موفق، توضیح)"""
    import subprocess
    if action == "reboot":
        try:
            subprocess.Popen(["shutdown", "-r", "+1"],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True, "ریبوت سرور تا یک دقیقه‌ی دیگر"
        except Exception as e:
            return False, f"ریبوت ناموفق: {e}"

    for svc in ("x-ui", "xray"):
        try:
            r = subprocess.run(["systemctl", "restart", svc],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                return True, f"سرویس {svc} ری‌استارت شد"
        except Exception:
            continue
    return False, "هیچ‌کدام از سرویس‌های x-ui/xray ری‌استارت نشدند"


def _maint_tick():
    """
    یک‌بار بررسی پنجره‌ی نگهداری. از حلقه‌ی سلامت (هر ۵ دقیقه) صدا زده
    می‌شود، پس پنجره را ۵ دقیقه‌ای می‌گیریم تا جا نیفتد.
    """
    m = _maint_conf()
    if not m.get("enabled"):
        return
    if m.get("action") == "reboot" and not m.get("confirmedReboot"):
        return

    now = datetime.now()
    if m.get("days") and now.weekday() not in [int(d) for d in m["days"]]:
        return

    target = now.replace(hour=int(m.get("hour", 5)),
                         minute=int(m.get("minute", 0)),
                         second=0, microsecond=0)
    delta = (now - target).total_seconds()
    if not (0 <= delta < 300):
        return

    today = now.strftime("%Y-%m-%d")
    if str(m.get("lastRun") or "")[:10] == today:
        return

    if m.get("skipIfBusy"):
        busy, n = _maint_busy()
        if busy and n >= int(m.get("busyThreshold") or 20):
            m["lastRun"] = now.isoformat(timespec="seconds")
            m["lastResult"] = f"رد شد — {_fnum(n)} اتصال فعال بود"
            _maint_save(m)
            return

    ok, note = _maint_run(m.get("action") or "xray")
    m["lastRun"] = now.isoformat(timespec="seconds")
    m["lastResult"] = ("انجام شد — " if ok else "ناموفق — ") + note
    _maint_save(m)


@app.get("/api/admin/maintenance")
def maintenance_get(x_admin_password: str = Header(...)):
    """زمان‌بندی نگهداری خودکار."""
    check_auth(x_admin_password)
    m = _maint_conf()

    from datetime import timedelta

    nxt = None
    if m.get("enabled"):
        now = datetime.now()
        cand = now.replace(hour=int(m["hour"]), minute=int(m["minute"]),
                           second=0, microsecond=0)
        if cand <= now:
            cand += timedelta(days=1)
        for _ in range(8):
            if not m.get("days") or cand.weekday() in [int(d) for d in m["days"]]:
                break
            cand += timedelta(days=1)
        nxt = cand.isoformat(timespec="minutes")

    busy, n = _maint_busy()
    m["nextRun"] = nxt
    m["activeConnections"] = n
    # اگر زمان‌بند خودش شکسته، «اجرای بعدی: …» دروغ است — همین را بگو
    m["tickError"] = _LOOP_ERR.get("maint")
    return m


@app.put("/api/admin/maintenance")
def maintenance_set(payload: dict, x_admin_password: str = Header(...)):
    """
    تنظیم زمان‌بندی.

    ریبوت سرور عمداً سخت‌تر از ری‌استارت سرویس است: تا وقتی
    confirmedReboot صریحاً true نشود، اجرا نمی‌شود. یک تیک اشتباهی
    نباید بتواند سرور فروش را وسط شب بخواباند.
    """
    check_auth(x_admin_password)
    m = _maint_conf()

    action = (payload or {}).get("action") or m["action"]
    if action not in ("xray", "reboot"):
        raise HTTPException(status_code=400, detail="عمل نامعتبر")

    try:
        hour = int(payload.get("hour", m["hour"]))
        minute = int(payload.get("minute", m["minute"]))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ساعت نامعتبر")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise HTTPException(status_code=400, detail="ساعت باید بین ۰ تا ۲۳ باشد")

    days = payload.get("days", m["days"]) or []
    days = [int(d) for d in days if str(d).isdigit() and 0 <= int(d) <= 6]

    confirmed = bool(payload.get("confirmedReboot", m["confirmedReboot"]))
    enabled = bool(payload.get("enabled", m["enabled"]))
    if enabled and action == "reboot" and not confirmed:
        raise HTTPException(
            status_code=400,
            detail="ریبوت خودکار سرور نیاز به تایید صریح دارد")

    m.update({
        "enabled": enabled,
        "action": action,
        "hour": hour,
        "minute": minute,
        "days": days,
        "skipIfBusy": bool(payload.get("skipIfBusy", m["skipIfBusy"])),
        "busyThreshold": max(1, int(payload.get("busyThreshold",
                                                m["busyThreshold"]) or 20)),
        "confirmedReboot": confirmed,
    })
    _maint_save(m)
    return {"ok": True, **m}


@app.post("/api/admin/maintenance/run-now")
def maintenance_run_now(payload: dict = None, x_admin_password: str = Header(...)):
    """اجرای دستی — برای وقتی مدیر همین حالا می‌خواهد."""
    check_auth(x_admin_password)
    action = ((payload or {}).get("action") or "xray")
    if action not in ("xray", "reboot"):
        raise HTTPException(status_code=400, detail="عمل نامعتبر")
    if action == "reboot" and not (payload or {}).get("confirm"):
        raise HTTPException(status_code=400,
                            detail="برای ریبوت باید confirm بفرستید")

    ok, note = _maint_run(action)
    m = _maint_conf()
    m["lastRun"] = datetime.now().isoformat(timespec="seconds")
    m["lastResult"] = ("دستی — " if ok else "دستی، ناموفق — ") + note
    _maint_save(m)
    return {"ok": ok, "note": note}


#: آخرین خطای هر کارِ پس‌زمینه — {کار: {"error": متن, "at": زمان}}
#
# این حلقه هر پنج دقیقه نمونه‌ی مصرف می‌گیرد و نگهداریِ خودکار را اجرا
# می‌کند. هر سه شکستش با `pass` بلعیده می‌شد: اگر نگهداری از کار
# می‌افتاد، هیچ‌جا — نه لاگ، نه پنل — چیزی گفته نمی‌شد و مدیر فکر
# می‌کرد هر شب اجرا می‌شود.
_LOOP_ERR = {}


def _loop_fail(key, exc):
    """شکستِ یک کارِ پس‌زمینه را ثبت کن؛ لاگ فقط وقتی متن عوض شود، نه هر پنج دقیقه."""
    msg = f"{type(exc).__name__}: {str(exc)[:160]}"
    prev = _LOOP_ERR.get(key)
    if not prev or prev.get("error") != msg:
        log.warning("background task %s failed: %s", key, msg, exc_info=True)
    _LOOP_ERR[key] = {"error": msg, "at": datetime.now().isoformat(timespec="minutes")}


def _loop_ok(key):
    if _LOOP_ERR.pop(key, None):
        log.info("background task %s recovered", key)


#: Called every health round after this server's own check. Pro code for other
#: servers (backend/pro/servers.py) adds itself; the core loop knows nothing of
#: nodes or tunnels.
_HEALTH_HOOKS = []


# ── Config lifecycle (docs/specs/2026-09-30-vpn-fixes.md, task 9) ─────────
#: The sweep runs from the health loop (every 5 minutes) and works every 15
#: minutes: one read of the x-ui database, then only rows that changed.
SUB_SWEEP_EVERY = 900
_SUB_SWEEP = {"at": 0.0}


def _sub_ended(cl, now):
    """Has this 3x-ui client ended: date passed, or volume used up? 3x-ui is
    the truth here, not the bot's copy: the owner edits dates in 3x-ui too.
    A negative expiry has not started yet; zero never expires."""
    exp = int(cl.get("expiry") or 0)
    if exp > 0 and exp / 1000 <= now.timestamp():
        return True
    total = int(cl.get("totalGB") or 0)
    return bool(total and int(cl.get("used") or 0) >= total)


def _sub_delete(h, t, d, s, now):
    """Delete one ended config and mark it; False when it was not deleted.
    Holds the renewal lock so a renewal cannot land on a deleted config."""
    if not d.claim_renewal(s["id"]):
        return False                      # being renewed right now
    try:
        fresh = d.q("SELECT * FROM subscriptions WHERE tenant_id=? AND id=?",
                    (t["id"], s["id"]), one=True)
        if not fresh or fresh.get("deleted_at") or not fresh.get("ended_at"):
            return False                  # renewed or gone meanwhile
        if t.get("parent_id"):
            # A reseller's config carries a bill. Only the billing core may
            # delete it; without Pro there is none, so it stays (and says so).
            core_del = globals().get("_portal_delete_core")
            if core_del is None:
                log.warning("sub sweep: reseller %s config %s not deleted: "
                            "billing core (Pro) not loaded", t["id"], s["client_email"])
                return False
            core_del(t, s["client_email"], by_whom="auto: expired, not renewed",
                     refund=False)
        else:
            ctx = h.Ctx(h.Bot(t["bot_token"]), t)
            ctx.xui.delete_client(s["inbound_id"], s["client_uuid"],
                                  email=s["client_email"])
        d.exec("UPDATE subscriptions SET is_active=0, deleted_at=?, "
               "deleted_why='expired' WHERE tenant_id=? AND id=?",
               (now.isoformat(timespec="seconds"), t["id"], s["id"]))
        d.log("sub_deleted", s["user_id"], {"sub": s["id"], "email": s["client_email"]})
        return True
    except Exception as e:
        log.warning("sub sweep: deleting %s failed: %s", s["client_email"], e)
        d.log("sub_delete_failed", s["user_id"],
              {"sub": s["id"], "error": str(e)[:200]})
        return False
    finally:
        d.release_renewal(s["id"])


def _sub_api_client(c):
    """A client as 3x-ui's API returns it, in `_read_xui_clients` shape:
    the sweep reads only these three fields."""
    up, down = int(c.get("up") or 0), int(c.get("down") or 0)
    return {"email": c.get("email"),
            "expiry": int(c.get("expiryTime") or 0),
            "totalGB": int(c.get("totalGB") or c.get("total") or 0),
            "used": up + down or int(c.get("usedTraffic") or 0)}


def _sub_confirm_missing(h, t, missing):
    """
    Ask the shop's own 3x-ui about configs the database read did not find.
    Returns {email: client} for the ones it still has (the rest are gone), or
    None when the panel cannot be asked, before or after: `find_client` says
    None both for "not there" and for "panel down", so a panel that stops
    answering mid-way must not turn into "everything was deleted".
    """
    try:
        x = h.Ctx(h.Bot(t["bot_token"]), t).xui
        if not x.inbounds():
            _SUB_WHY[t["id"]] = "the shop's 3x-ui API listed no inbounds"
            return None
        found = {}
        for s in missing:
            c = x.find_client(s["inbound_id"], email=s["client_email"])
            # Some 3x-ui versions answer an unknown email with an empty
            # "success" object; only an answer that names this config counts.
            if isinstance(c, dict) and str(c.get("email") or "").lower() == s["client_email"].lower():
                found[s["client_email"]] = _sub_api_client(c)
        if not x.inbounds():
            _SUB_WHY[t["id"]] = "the shop's 3x-ui API stopped answering mid-check"
            return None
        _SUB_WHY[t["id"]] = f"asked the shop's 3x-ui API: {len(found)} of {len(missing)} still there"
        return found
    except Exception as e:
        log.warning("sub sweep: shop %s: 3x-ui API not reachable: %s", t["id"], e)
        _SUB_WHY[t["id"]] = f"the shop's 3x-ui API is not reachable: {type(e).__name__}: {str(e)[:120]}"
        return None


#: Why the last pass of each shop decided what it did, for the report below.
_SUB_WHY = {}


def _sub_lifecycle_shop(h, t, index, now):
    """One shop's pass. Returns counts, for the log and the tests."""
    d = h.DB.TenantDB(t["id"])
    days = h.core.delete_after_days(h.DB.tenant_settings(t["id"]))
    out = {"gone": 0, "started": 0, "ended": 0, "warned": 0, "deleted": 0,
           "skipped": "", "missing": [], "checked": 0, "why": ""}
    _SUB_WHY.pop(t["id"], None)
    # Every config the bot or the mini app still lists, switched off ones
    # too: the mini app shows `deleted_at IS NULL`, and a config the bot had
    # switched off but 3x-ui had deleted was in neither this pass nor gone.
    subs = d.q("SELECT s.*, u.tg_id FROM subscriptions s JOIN users u ON u.id=s.user_id "
               "WHERE s.tenant_id=? AND s.deleted_at IS NULL",
               (t["id"],))
    out["checked"] = len(subs)
    back = d.q("SELECT id, user_id, client_email FROM subscriptions WHERE tenant_id=? "
               "AND deleted_why='missing_in_panel'", (t["id"],))
    for b in back:
        if b["client_email"] in index:
            d.exec("UPDATE subscriptions SET is_active=1, deleted_at=NULL, deleted_why=NULL "
                   "WHERE tenant_id=? AND id=?", (t["id"], b["id"]))
            d.log("sub_back", b["user_id"], {"sub": b["id"], "email": b["client_email"]})
            out["back"] = out.get("back", 0) + 1
    if out.get("back"):
        subs = d.q("SELECT s.*, u.tg_id FROM subscriptions s JOIN users u ON u.id=s.user_id "
                   "WHERE s.tenant_id=? AND s.deleted_at IS NULL", (t["id"],))
        out["checked"] = len(subs)
    missing = [s for s in subs if s["client_email"] not in index]
    out["missing"] = [s["client_email"] for s in missing][:30]
    # Half the shop gone at once can be a wrong panel or a bad read. It can
    # also be an owner with eight configs who deleted five test ones by hand,
    # and the first version of this guard could not tell the two apart: it
    # skipped that shop every hour and the deleted configs stayed in the bot.
    # So the shop's own 3x-ui (the one the bot creates on) is asked about each
    # one; only when it cannot be asked is nothing marked.
    # A wrong panel or a bad read finds none of this shop's configs. Until
    # 2.1.3 the guard was "half or more missing", and an owner who deleted his
    # test configs by hand tripped it every hour; when his 3x-ui API did not
    # answer either, the deleted configs stayed in the bot and the mini app for
    # good (the owner's screenshots, 2026-10-01). If the read finds even one
    # of the shop's configs it read the right panel, and the rest are gone. A
    # "gone" mark is undone below the moment a config is seen again.
    found_n = len(subs) - len(missing)
    guard = len(missing) >= 5 and found_n == 0
    if guard:
        found = _sub_confirm_missing(h, t, missing)
        if found is None:
            out["skipped"] = f"{len(missing)} of {len(subs)} configs missing from 3x-ui"
            log.warning("sub sweep: shop %s: %s; nothing marked", t["id"], out["skipped"])
            d.log("sub_sweep_skipped", None, {"missing": len(missing), "of": len(subs)})
        else:
            index = {**index, **found}
            guard = False
    stamp = now.isoformat(timespec="seconds")
    for s in subs:
        cl = index.get(s["client_email"])
        if cl is None:
            if not guard:
                d.exec("UPDATE subscriptions SET is_active=0, deleted_at=?, "
                       "deleted_why='missing_in_panel' WHERE tenant_id=? AND id=?",
                       (stamp, t["id"], s["id"]))
                d.log("sub_gone", s["user_id"], {"sub": s["id"], "email": s["client_email"]})
                out["gone"] += 1
            continue
        if not s.get("is_active"):
            continue                      # switched off: only the "gone" rule applies
        exp = int(cl.get("expiry") or 0)
        if not s.get("expires_at") and s.get("pending_days") and exp > 0:
            # First connection happened: 3x-ui turned the duration into a date.
            iso = datetime.fromtimestamp(exp / 1000).isoformat(timespec="seconds")
            d.exec("UPDATE subscriptions SET expires_at=?, pending_days=NULL "
                   "WHERE tenant_id=? AND id=?", (iso, t["id"], s["id"]))
            out["started"] += 1
        if not _sub_ended(cl, now):
            if s.get("ended_at"):         # renewed by hand in 3x-ui
                d.exec("UPDATE subscriptions SET ended_at=NULL, notified_del=0 "
                       "WHERE tenant_id=? AND id=?", (t["id"], s["id"]))
            continue
        ended_at = s.get("ended_at")
        if not ended_at:
            # The first time the sweep sees it, not the expiry date: on the
            # first run after an update, months-old expired configs would
            # otherwise be deleted at once, with no warning.
            ended_at = stamp
            d.exec("UPDATE subscriptions SET ended_at=? WHERE tenant_id=? AND id=?",
                   (stamp, t["id"], s["id"]))
            out["ended"] += 1
        if days <= 0:
            continue
        since = now - datetime.fromisoformat(str(ended_at)[:19])
        if since >= timedelta(days=days):
            if _sub_delete(h, t, d, {**s, "ended_at": ended_at}, now):
                out["deleted"] += 1
        elif since >= timedelta(days=days - 1) and not s.get("notified_del"):
            try:
                h.send_delete_notice(t, h.Bot(t["bot_token"]), s)
            except Exception as e:
                # A buyer who blocked the bot must not block the deletion.
                log.warning("sub sweep: delete notice to %s failed: %s", s.get("tg_id"), e)
            d.exec("UPDATE subscriptions SET notified_del=1 WHERE tenant_id=? AND id=?",
                   (t["id"], s["id"]))
            out["warned"] += 1
    out["why"] = _SUB_WHY.get(t["id"]) or (
        f"{len(missing)} of {len(subs)} not in the x-ui database; marked gone"
        if missing else f"all {len(subs)} found in the x-ui database")
    return out


def sub_sweep_report():
    """
    Run the sweep for every shop now and say, shop by shop, what it saw and
    why it did what it did. Behind the bot-users page's «همگام‌سازی با
    3x-ui» button and `nexora sweep`: when configs deleted in 3x-ui stayed
    in the mini app on the owner's server, nothing in the panel could say
    why, and guessing from here twice did not find it.
    """
    clients, _k, err = _read_xui_clients()
    path = str(_xui_db_path())
    if clients is None:
        return {"ok": False, "xuiPath": path, "why": f"x-ui database unreadable: {err}"}
    index = {c.get("email"): c for c in clients if c.get("email")}
    h = _bot_handlers()
    now = datetime.now()
    shops = []
    for t in h.DB.all_tenants(active_only=True):
        if not t.get("bot_token"):
            continue
        try:
            r = _sub_lifecycle_shop(h, t, index, now)
        except Exception as e:
            r = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
        shops.append({"id": t["id"], "name": t.get("name") or "", "reseller": bool(t.get("parent_id")), **r})
    _SUB_SWEEP["at"] = time.time()
    return {"ok": True, "xuiPath": path, "xuiClients": len(index), "shops": shops}


@app.post("/api/admin/subs/sweep")
def subs_sweep(x_admin_password: str = Header(...)):
    check_auth(x_admin_password)
    return sub_sweep_report()


_SUB_SHOP_AT = {}


def sub_sweep_shop_now(t, clients=None, min_gap=60, now=None):
    """
    The sweep for one shop, now (at most once a minute per shop). The mini
    app calls it before listing a buyer's configs: with only the hourly pass,
    a config the owner had just deleted in 3x-ui was still on the buyer's
    home screen for up to an hour, as an "active, 0 MB" card. Same function
    as the hourly pass, so the same guard and the same rule.
    """
    if time.time() - _SUB_SHOP_AT.get(t["id"], 0) < min_gap:
        return None
    _SUB_SHOP_AT[t["id"]] = time.time()
    if clients is None:
        clients, _k, _err = _read_xui_clients()
    if not clients:
        return None
    try:
        index = {c.get("email"): c for c in clients if c.get("email")}
        # `now` for tests with a fixed clock: the mini app's own call used the
        # real one, and five days after the test's date it deleted configs
        # the test had not yet aged (CI red from 2026-10-06 12:00)
        return _sub_lifecycle_shop(_bot_handlers(), t, index, now or datetime.now())
    except Exception as e:
        log.warning("sub sweep (shop %s, on demand) failed: %s", t.get("id"), e)
        return None


def _sub_lifecycle_tick(now=None, force=False):
    """
    Hourly: configs the bot made, against 3x-ui. Marks the start of configs
    that count from the first connection, hides configs deleted by hand in
    3x-ui, warns the day before and deletes configs that ended and were not
    renewed for `delete_expired_days`. Runs in the panel, which reads the x-ui
    database once for every shop and holds the billing core. Returns
    {shop id: counts}, or None when it is not due yet.
    """
    if not force and time.time() - _SUB_SWEEP["at"] < SUB_SWEEP_EVERY:
        return None
    _SUB_SWEEP["at"] = time.time()
    now = now or datetime.now()
    clients, _keys, err = _read_xui_clients()
    if clients is None:
        raise RuntimeError(f"x-ui database unreadable: {err}")
    index = {c.get("email"): c for c in clients if c.get("email")}
    h = _bot_handlers()
    report = {}
    for t in h.DB.all_tenants(active_only=True):
        if t.get("bot_token"):
            report[t["id"]] = _sub_lifecycle_shop(h, t, index, now)
    return report


def _start_health_loop():
    """
    بررسی خودکار سلامت هر ۵ دقیقه.

    نخ پس‌زمینه، نه cron — چون باید همراه سرویس بالا و پایین برود
    و اگر پنل خاموش شد، بررسی هم متوقف شود.
    """
    import threading

    def loop():
        time.sleep(60)          # فرصت بالا آمدن کامل سرویس
        while True:
            try:
                if HEALTH:
                    data = HEALTH.run_all(ports=_health_ports(),
                                          domain=_health_domain())
                    _health_alert("سرور پنل", data, key="local")

                # Other servers (Pro, `monitoring_multi`) plug in here.
                for _hook in _HEALTH_HOOKS:
                    try:
                        _hook()
                    except Exception as e:
                        _loop_fail("health-jobs", e)
            except Exception as e:
                _loop_fail("health-jobs", e)

            # پنجره‌ی نگهداری هم همین‌جا بررسی می‌شود — نخ جدا لازم
            # ندارد و هر دو با سرویس بالا و پایین می‌روند
            try:
                _history_sample()
                _loop_ok("history")
            except Exception as e:
                _loop_fail("history", e)


            try:
                _maint_tick()
                _loop_ok("maint")
            except Exception as e:
                _loop_fail("maint", e)

            try:
                if _sub_lifecycle_tick() is not None:
                    _loop_ok("sub-lifecycle")
            except Exception as e:
                _loop_fail("sub-lifecycle", e)

            try:
                _tunnel_alert_tick()
                _loop_ok("tunnel-alerts")
            except Exception as e:
                _loop_fail("tunnel-alerts", e)

            time.sleep(300)

    try:
        threading.Thread(target=loop, daemon=True).start()
    except Exception as _exc:
        log.error("health/maintenance loop thread did not start: %s", _exc, exc_info=True)


def _selfheal_plan_costs():
    """
    پلن‌هایی که پیش از ۱.۸۶ ذخیره شده‌اند کفِ ذخیره‌شده ندارند.

    حلقه‌ی `_selfheal` خطا را بی‌صدا می‌بلعد؛ این یکی پول است، پس
    خودش می‌گوید.
    """
    if not BOT_DB.exists():
        return None
    try:
        n = _refresh_plan_costs()
    except Exception:
        log.warning("همگام‌سازیِ کفِ پلن‌ها موقعِ بالاآمدن ناموفق", exc_info=True)
        return None
    return f"کفِ {_fnum(n)} پلن" if n else None


def _announce_admin_path():
    """
    بارِ اولی که نشانی ساخته شد، ربات آن را در پیوی مالک و مدیرهای ربات
    می‌فرستد — وگرنه مالکی که پنل را با «/» باز می‌کرد، بعد از به‌روزرسانی
    پشتِ «پیدا نشد» می‌ماند. فقط پیوی، نه گروه: گروه ممکن است آدم‌های دیگر
    هم داشته باشد. نبودِ ربات یا شکستِ ارسال لاگ می‌شود؛ `nexora url` همیشه
    هست.
    """
    admin_path()
    if not _ADMIN_PATH.get("fresh"):
        return
    con = _bot_conn()
    if not con:
        log.warning("نشانیِ پنل ساخته شد ولی ربات نیست — با «nexora url» روی سرور ببینید")
        return
    try:
        t = con.execute("SELECT bot_token, owner_tg_id, settings FROM tenants "
                        "WHERE parent_id IS NULL ORDER BY id LIMIT 1").fetchone()
    except Exception:
        log.warning("نشانیِ پنل: مستاجرِ ریشه خوانده نشد", exc_info=True)
        return
    finally:
        con.close()
    if not t or not t["bot_token"]:
        return
    ids = set()
    raw_ids = [t["owner_tg_id"]]
    try:
        raw_ids += list(json.loads(t["settings"] or "{}").get("admins") or [])
    except ValueError as e:
        log.warning("نشانیِ پنل: تنظیماتِ ربات خوانده نشد: %s", e)
    for x in raw_ids:
        s = str(x or "").strip()
        if s.lstrip("-").isdigit():
            ids.add(int(s))
    url = admin_url() or f"/{admin_path()}/"
    text = ("🔐 <b>نشانیِ پنلِ مدیریت عوض شد</b>\n\n"
            f"<code>{url}</code>\n\n"
            "از این به بعد پنل فقط از همین نشانی باز می‌شود — نشانیِ قبلی «پیدا نشد» "
            "نشان می‌دهد. این نشانی را به نماینده‌ها و همکارها ندهید.\n"
            "روی سرور هم با دستورِ <code>nexora url</code> دیده می‌شود.")
    for cid in ids:
        try:
            body = json.dumps({"chat_id": cid, "text": text, "parse_mode": "HTML",
                               "link_preview_options": {"is_disabled": True}}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{t['bot_token']}/sendMessage",
                data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                r.read()
        except Exception as e:
            log.warning("نشانیِ پنل به %s نرسید: %s", cid, e)


@app.on_event("startup")
def _admin_path_boot():
    # در پس‌زمینه: تلگرام از ایران کُند است و راه‌اندازیِ پنل نباید منتظرش بماند
    _threading.Thread(target=_announce_admin_path, daemon=True).start()


# ── Pro license ── docs/specs/2026-09-29-license-core.md ─────────────────
try:
    import license as LIC                                  # noqa: E402
except ImportError:
    # Many tests load app.py by path without backend/ on sys.path (as fx.py
    # does below). Registered under the plain name so a later `import license`
    # gets this same object: two copies would each keep their own KEYS.
    import importlib.util as _ilic
    import sys as _sys
    _ls = _ilic.spec_from_file_location("license", Path(__file__).resolve().parent / "license.py")
    LIC = _ilic.module_from_spec(_ls)
    _sys.modules["license"] = LIC
    _ls.loader.exec_module(LIC)

# A list, tried in order: one issuer host blocked in Iran must not lock every
# server out of refreshing. license.license_urls(): the env, else the owner's
# defaults (license.DEFAULT_LICENSE_URLS). Tests replace this list.
LICENSE_URLS = LIC.license_urls()

_LIC_WHY_FA = {
    "wrong_machine": "مجوزی که سرور مجوز داد برای این سرور نیست",
    "unknown_key": "کلید امضای مجوز شناخته نیست؛ پنل را به‌روز کنید",
    "bad_signature": "امضای مجوز درست نبود",
    "malformed": "پاسخ سرور مجوز خراب بود",
}


def pro_required(feature):
    """Dependency for a Pro route. It depends on check_auth itself: listed side
    by side, FastAPI still runs the license check after a failed auth, and an
    anonymous caller learned the license state (tests/test-license.py)."""
    gate = LIC.requires(feature)

    def _dep(_auth=Depends(check_auth)):
        return gate()
    return _dep


def _panel_version():
    try:
        return (_root_dir() / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "?"


def _issuer(action, payload):
    """POST to the first issuer that answers (license.issuer_post, the one
    client the panel and scripts/pro-fetch.py share)."""
    return LIC.issuer_post(f"/v1/license/{action}",
                           {**payload, "version": _panel_version(), "domain": _panel_origin()},
                           urls=LICENSE_URLS)


def _license_view():
    # PRO_* are set by _load_pro() at the end of this module. `denials` is the
    # backend's own sentence per feature, so the panel's lock screen and a
    # locked route's 403 never say different things.
    st = LIC.status()
    return {**st, "refresh": LIC.refresh_info(),
            "features": LIC.FEATURE_FA,
            "denials": {f: LIC.denial(f, st) for f in LIC.FEATURES},
            "issuer_configured": bool(LICENSE_URLS),
            "pro_loaded": globals().get("PRO_LOADED", False),
            "pro_error": globals().get("PRO_ERROR", "")}


def _license_install(resp):
    doc = resp.get("license") if isinstance(resp, dict) else None
    st, why = LIC.install(doc)
    if why:
        raise HTTPException(502, detail=f"مجوز نصب نشد: {_LIC_WHY_FA.get(why, why)}")
    LIC.note_refresh(True)
    return _license_view()


@app.get("/api/admin/license")
def license_get(_=Depends(check_auth)):
    return _license_view()


@app.post("/api/admin/license/activate")
def license_activate(body: dict, _=Depends(check_auth)):
    key = str((body or {}).get("key") or "").strip()
    if not (8 <= len(key) <= 200):
        raise HTTPException(400, detail="کلید مجوز را کامل وارد کنید.")
    resp, err = _issuer("activate", {"key": key, "machine": LIC.fingerprint()})
    if err:
        raise HTTPException(502, detail=err)
    return _license_install(resp)


def _pro_watermark():
    """Whose license the installed Pro code was cut for (backend/pro/WATERMARK,
    written by the issuer into every bundle). Sent on refresh: a bundle cut for
    another license is how a leak shows up on the issuer."""
    try:
        return (Path(__file__).resolve().parent / "pro" / "WATERMARK").read_text(
            encoding="utf-8").strip()[:16]
    except OSError:
        return ""


def _license_refresh():
    st = LIC.status()
    if not st["license_id"]:
        return None, "مجوزی نصب نیست که تازه شود."
    resp, err = _issuer("refresh", {"license_id": st["license_id"],
                                    "machine": LIC.fingerprint(),
                                    "watermark": _pro_watermark()})
    if err:
        LIC.note_refresh(False, err)
        return None, err
    try:
        return _license_install(resp), None
    except HTTPException as e:
        LIC.note_refresh(False, e.detail)
        return None, e.detail


@app.post("/api/admin/license/refresh")
def license_refresh(_=Depends(check_auth)):
    view, err = _license_refresh()
    if err:
        raise HTTPException(502, detail=err)
    return view


@app.post("/api/admin/license/pro-install")
def license_pro_install(_=Depends(check_auth)):
    """Fetch and install the Pro package for this license and version
    (`nexora pro`: scripts/pro-fetch.py, then rebuild and restart). Offered on
    the System page when the license is active but no Pro code is loaded."""
    st = LIC.status()
    if not st["pro"]:
        raise HTTPException(400, detail="بسته‌ی Pro فقط برای مجوزِ فعال داده می‌شود؛ اول مجوز را فعال کنید.")
    _run_cli_detached("pro")
    return {"ok": True, "logPath": UPDATE_LOG,
            "message": "نصب بسته‌ی Pro شروع شد؛ حدود ۲ تا ۵ دقیقه طول می‌کشد و پنل یک‌بار راه‌اندازیِ دوباره می‌شود."}


@app.post("/api/admin/license/deactivate")
def license_deactivate(_=Depends(check_auth)):
    st = LIC.status()
    if not st["license_id"]:
        raise HTTPException(400, detail="مجوزی نصب نیست.")
    # The issuer must free the slot first. Removing the file while it still
    # counts this server would leave the owner with a license bound nowhere.
    _, err = _issuer("deactivate", {"license_id": st["license_id"],
                                    "machine": LIC.fingerprint()})
    if err:
        raise HTTPException(502, detail=f"غیرفعال نشد، مجوز همین‌جا ماند: {err}")
    LIC.remove()
    return _license_view()


def _license_loop():
    while True:
        try:
            if LIC.refresh_due():
                _, err = _license_refresh()
                if err:
                    log.warning("license refresh failed: %s", err)
        except Exception:
            log.exception("license refresh loop")
        time.sleep(6 * 3600)


@app.on_event("startup")
def _license_boot():
    _threading.Thread(target=_license_loop, daemon=True).start()


@app.on_event("startup")
def _selfheal():
    """
    همه‌ی ترمیم‌ها را اجرا می‌کند.

    هر مرحله جدا محافظت شده: اگر یکی شکست بخورد، بقیه ادامه می‌دهند
    و سرویس در هر حالت بالا می‌آید. اینها بهبودند، نه ضرورت.
    """
    _start_health_loop()

    steps = [
        ("cli", _selfheal_cli),
        ("scripts", _selfheal_scripts),
        ("bot-deps", _selfheal_bot_deps),
        ("bot-service", _selfheal_bot_service),
        ("cron", _selfheal_backup_cron),
        ("plan-costs", _selfheal_plan_costs),
    ]
    done = []
    for name, fn in steps:
        try:
            r = fn()
            if r:
                done.append(r)
        except Exception as _exc:
            log.warning("selfheal step failed: %s", _exc)

    if done:
        try:
            import logging
            logging.getLogger("uvicorn").info(
                "خودترمیمی: %s", " · ".join(done))
        except Exception:
            pass


def _svc(action, unit="nexora-bot"):
    """اجرای امن systemctl. برمی‌گرداند (موفق, پیام)."""
    import subprocess
    try:
        r = subprocess.run(["systemctl", action, unit],
                           capture_output=True, text=True, timeout=25)
        if r.returncode == 0:
            return True, ""
        return False, (r.stderr or r.stdout or "").strip()[:200]
    except FileNotFoundError:
        return False, "systemctl در دسترس نیست"
    except Exception as e:
        return False, str(e)[:200]


def _svc_active(unit="nexora-bot"):
    import subprocess
    try:
        r = subprocess.run(["systemctl", "is-active", "--quiet", unit],
                           timeout=10)
        return r.returncode == 0
    except Exception:
        return False


@app.post("/api/admin/bot/service/{action}")
def bot_service(action: str, x_admin_password: str = Header(...)):
    """کنترل سرویس ربات از پنل — بدون نیاز به ورود به سرور."""
    check_auth(x_admin_password)
    if action not in ("start", "stop", "restart"):
        raise HTTPException(status_code=400, detail="عملیات نامعتبر")

    if action in ("start", "restart"):
        if not (_bot_dir() / "run.py").exists():
            raise HTTPException(status_code=400,
                                detail="ماژول ربات روی سرور نیست — nexora update را اجرا کنید")
        # اگر سرویس نبود، بساز
        if not Path("/etc/systemd/system/nexora-bot.service").exists():
            try:
                _selfheal_bot_service()
            except Exception as _exc:
                log.warning("bot service selfheal: %s", _exc)

    ok, err = _svc(action)
    if not ok:
        raise HTTPException(status_code=500, detail=err or "اجرای دستور ناموفق بود")

    if action in ("start", "restart"):
        _svc("enable")

    import time
    time.sleep(2.5)
    return {"ok": True, "running": _svc_active()}


#: جدول‌هایی که پشتیبان نمی‌خواهند.
#
#  sqlite_sequence را خودِ SQLite نگه می‌دارد، و bot_flags یک پرچم
#  لحظه‌ای بین پنل و ربات است نه داده‌ی کاربر.
_BACKUP_SKIP = {"sqlite_sequence", "bot_flags"}

#: ترتیب دلخواه — والدها اول. جدول‌های کشف‌شده‌ای که این‌جا نیستند
#: بعد از این‌ها می‌آیند، پس فراموش‌شدنشان ممکن نیست.
_BOT_TABLE_ORDER = [
    "tenants", "users", "plans", "orders", "subscriptions",
    "affiliates", "affiliate_commissions", "affiliate_payouts",
    "coin_tx", "wallet_tx", "discounts", "tickets", "events",
]


def _tables_of(con, order=()):
    """
    فهرست جدول‌های واقعیِ یک دیتابیس، به ترتیب دلخواه.

    چرا از اسکیما خوانده می‌شود و دستی نوشته نمی‌شود: فهرست دستی با
    هر قابلیت تازه عقب می‌ماند و هیچ خطایی هم نمی‌دهد. پشتیبان با
    «ok» دانلود می‌شد و جدول‌های تازه اصلاً در آن نبودند — همکاران
    فروش، پورسانتشان، و کل بخش هزینه‌ها همین‌طور جا افتاده بودند.
    """
    try:
        found = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    except Exception:
        return list(order)
    found -= _BACKUP_SKIP
    known = [t for t in order if t in found]
    return known + sorted(found - set(known))


def _restore_tables(con, order, data):
    """
    جدول‌های `order` را خالی و از `data` پر می‌کند؛ همان برای ربات و حسابداری.

    این حلقه پیش‌تر دو بار نوشته شده بود — یک‌بار در بازگردانیِ ربات و
    یک‌بار در حسابداری — و هر دو دو چیز را بی‌صدا رد می‌کردند:

      - `DELETE` ناموفق با `pass` بلعیده می‌شد. بعد `INSERT OR REPLACE`
        ردیف‌های پشتیبان را روی ردیف‌های قدیمی می‌ریخت: نه داده‌ی قبلی،
        نه داده‌ی پشتیبان، بلکه مخلوطی که هیچ‌جا ثبت نشده بود. حالا
        همان‌جا می‌ایستد و فراخوان rollback می‌کند.
      - ردیفِ درج‌نشده شمرده می‌شد ولی *چرا*یش نه. حالا اولین خطای هر
        جدول هم برمی‌گردد.

    برمی‌گرداند: (restored, skipped, why) — why = {جدول: اولین خطا}
    """
    restored, skipped, why = {}, {}, {}
    # خالی‌کردن به ترتیبِ وارونه (فرزند پیش از والد)، پر کردن به ترتیبِ راست
    for t in reversed(order):
        try:
            con.execute(f"DELETE FROM {t}")
        except Exception as e:
            raise RuntimeError(f"خالی‌کردنِ جدولِ {t} ناموفق بود: {str(e)[:120]}")
    for t in order:
        rows = data.get(t) or []
        if not rows:
            restored[t] = 0
            continue
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        usable = [c for c in cols if any(isinstance(r, dict) and c in r for r in rows)]
        if not usable:
            restored[t] = 0
            continue
        ph = ",".join("?" * len(usable))
        sql = f"INSERT OR REPLACE INTO {t} ({','.join(usable)}) VALUES ({ph})"
        n = 0
        for r in rows:
            try:
                con.execute(sql, [r.get(c) for c in usable])
                n += 1
            except Exception as e:
                why.setdefault(t, f"{type(e).__name__}: {str(e)[:100]}")
        restored[t] = n
        if n < len(rows):
            skipped[t] = len(rows) - n
    return restored, skipped, why


def _restore_warning(skipped, why):
    """«بعضی ردیف‌ها بازنگشتند» با دلیلِ هر جدول — یک متن برای هر دو بازگردانی."""
    return ("بعضی ردیف‌ها بازنگشتند: "
            + "، ".join(f"{k} ({v}" + (f" — {why[k]}" if why.get(k) else "") + ")"
                       for k, v in skipped.items()))


@app.get("/api/admin/bot/backup")
def bot_backup(x_admin_password: str = Header(...)):
    """دانلود بک‌آپ کامل ربات (JSON)."""
    check_auth(x_admin_password)
    con = _bot_conn()
    if not con:
        raise HTTPException(status_code=400, detail="دیتابیس ربات موجود نیست")

    try:
        tables = _tables_of(con, _BOT_TABLE_ORDER)
        dump = {}
        for t in tables:
            try:
                dump[t] = [dict(r) for r in con.execute(f"SELECT * FROM {t}")]
            except Exception:
                dump[t] = []

        return {
            "version": 1,
            "createdAt": datetime.now().isoformat(timespec="seconds"),
            "panelVersion": (Path(__file__).resolve().parent.parent / "VERSION")
                            .read_text().strip() if (Path(__file__).resolve().parent.parent / "VERSION").exists() else "?",
            "counts": {k: len(v) for k, v in dump.items()},
            "data": dump,
        }
    finally:
        con.close()


@app.post("/api/admin/bot/restore")
def bot_restore(payload: dict, x_admin_password: str = Header(...)):
    """
    بازیابی بک‌آپ ربات.

    قبل از هر کاری از وضعیت فعلی یک نسخه‌ی امن می‌گیریم — اگر بازیابی
    اشتباه بود، داده‌ی فعلی از دست نرفته باشد.
    """
    check_auth(x_admin_password)
    data = (payload or {}).get("data")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="فایل بک‌آپ نامعتبر است")

    okdb, err = _ensure_bot_db()
    if not okdb:
        raise HTTPException(status_code=400, detail=err or "دیتابیس ربات در دسترس نیست")

    # نسخه‌ی امن قبل از بازیابی
    try:
        safety = BOT_DB.with_name(
            f"bot-before-restore-{datetime.now():%Y%m%d-%H%M%S}.db")
        _sqlite_copy(BOT_DB, safety)
    except Exception:
        log.warning("نسخه‌ی امنِ پیش از بازگردانی گرفته نشد", exc_info=True)
        safety = None

    con = _bot_rw()
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        # همه‌ی جدول‌ها اول خالی می‌شوند و بعد پر. اگر وسط کار چیزی
        # بشکند، بدون تراکنشِ صریح نیمی از داده رفته است و نیمی
        # برنگشته — و آن نسخه‌ی امن هم تازه همان‌جا لازم می‌شود.
        con.execute("BEGIN IMMEDIATE")
        # فقط جدول‌هایی که هم در پشتیبان‌اند و هم در این دیتابیس
        # وجود دارند. این‌طور پشتیبانِ نسخه‌ی قدیمی‌تر هم بازمی‌گردد،
        # بدون اینکه جدولی که در آن نبوده خالی شود.
        present = _tables_of(con, _BOT_TABLE_ORDER)
        order = [t for t in present if t in data]
        # ردیفی که درج نشد باید دیده شود. قبلاً بی‌صدا رد می‌شد و
        # جوابْ «ok» بود — یعنی بازگردانیِ نصفه، بدون هیچ نشانه‌ای.
        restored, skipped, why = _restore_tables(con, order, data)

        missing = sorted(set(data) - set(order))
        con.commit()
        out = {"ok": True, "restored": restored,
               "safetyCopy": str(safety) if safety else None}
        if skipped:
            out["skipped"] = skipped
            out["skippedWhy"] = why
            out["warning"] = _restore_warning(skipped, why)
        # هم‌تراز با حسابداری: بی‌نسخه‌ی امن، راهِ برگشت نیست — گفته شود
        if safety is None:
            out["safetyWarning"] = "نسخه‌ی امنِ پیش از بازگردانی گرفته نشد"
        if missing:
            out["unknownTables"] = missing
        return out
    except Exception as e:
        try:
            con.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"بازیابی ناموفق: {str(e)[:200]}")
    finally:
        con.close()


SNAP_DIR = Path("/root/nexora-snapshots")


@app.get("/api/admin/snapshots")
def list_snapshots(x_admin_password: str = Header(...)):
    """نسخه‌های ذخیره‌شده برای بازگشت — بدون نیاز به ترمینال."""
    check_auth(x_admin_password)
    if not SNAP_DIR.exists():
        return {"snapshots": []}

    out = []
    for d in sorted(SNAP_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        ver = "?"
        vf = d / "VERSION"
        if vf.exists():
            try:
                ver = vf.read_text().strip()
            except OSError as _exc:
                log.debug("snapshot metadata: %s", _exc)

        size = 0
        try:
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        except OSError as _exc:
            log.debug("snapshot metadata: %s", _exc)

        out.append({
            "id": d.name,
            "version": ver,
            "createdAt": datetime.fromtimestamp(d.stat().st_mtime).isoformat(timespec="seconds"),
            "sizeMb": round(size / 1048576, 1),
            "hasSettings": (d / "config.json").exists(),
            "hasBot": (d / "bot").exists() or (d / "bot.db").exists(),
        })
    return {"snapshots": out[:20]}


#: لاگ مشترک به‌روزرسانی و بازگردانی — رابط کاربری همین را دنبال می‌کند.
UPDATE_LOG = os.getenv("NEXORA_UPDATE_LOG", "/tmp/nexora-update.log")


@app.post("/api/admin/rollback")
def run_rollback(payload: dict, x_admin_password: str = Header(...)):
    """
    بازگشت به یک نسخه‌ی قبلی از داخل پنل.

    مثل به‌روزرسانی، در پس‌زمینه اجرا می‌شود و لاگش در همان فایل
    نوشته می‌شود تا رابط کاربری بتواند دنبالش کند.
    """
    check_auth(x_admin_password)
    # قالبِ مجاز، نه فهرستِ کاراکترهای ممنوع.
    #
    # نام نسخه‌ها را خودِ اسکریپت با «date +%Y%m%d-%H%M%S» می‌سازد، پس
    # همیشه همین شکل است. فهرستِ ممنوع (قبلاً فقط / و ..) هر چیزی را
    # که در آن فکر نکرده بودیم عبور می‌داد — از جمله کاراکترهای شل.
    snap = str((payload or {}).get("id", "") or "").strip()
    if not _re.fullmatch(r"\d{8}-\d{6}", snap):
        raise HTTPException(status_code=400, detail="شناسه نسخه نامعتبر است")

    target = SNAP_DIR / snap
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="این نسخه پیدا نشد")

    keep = "yes" if (payload or {}).get("keepSettings", True) else "no"

    # مسیر کامل دستور — نه فقط نام.
    #
    # سرویس systemd متغیر PATH محدودی دارد و ممکن است
    # /usr/local/bin در آن نباشد، پس «nexora» پیدا نمی‌شود و
    # دستور بی‌صدا شکست می‌خورد.
    import shutil
    exe = shutil.which("nexora") or "/usr/local/bin/nexora"
    if Path(exe).exists():
        cli_argv = [exe]
    else:
        local = _root_dir() / "nexora-cli.sh"
        if local.exists():
            cli_argv = ["bash", str(local)]
        else:
            raise HTTPException(
                status_code=500,
                detail="دستور nexora پیدا نشد. روی سرور اجرا کنید: nexora doctor")

    log = UPDATE_LOG
    try:
        import subprocess
        # لاگ را پاک می‌کنیم تا رابط کاربری فقط این اجرا را ببیند
        try:
            Path(log).write_text(
                f"[{datetime.now():%H:%M:%S}] بازگشت به نسخه {snap} آغاز شد\n",
                encoding="utf-8")
        except Exception as _exc:
            # `log` این‌جا مسیرِ فایل است، نه لاگر
            logging.getLogger("nexora.panel").warning("rollback log write: %s", _exc)

        # بدون شل. آرگومان‌ها فهرست‌اند، پس هیچ مقداری تفسیر نمی‌شود.
        # start_new_session همان کاری را می‌کند که setsid می‌کرد:
        # بستن پنل وسط کار، بازگردانی را نمی‌کشد.
        argv = cli_argv + ["rollback", snap, "--yes", f"--settings={keep}"]

        # نبودِ فایل لاگ نباید جلوی بازگردانی را بگیرد. لاگ برای دیدن
        # است؛ بازگردانی کاری است که باید انجام شود.
        try:
            logf = open(log, "ab")
        except OSError:
            logf = None
        try:
            subprocess.Popen(argv,
                             start_new_session=True,
                             stdin=subprocess.DEVNULL,
                             stdout=logf or subprocess.DEVNULL,
                             stderr=subprocess.STDOUT)
        finally:
            if logf:
                try:
                    logf.close()
                except OSError:
                    pass
        return {"ok": True, "started": snap, "log": log}
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"اجرای بازگشت ناموفق: {str(e)[:200]}")


@app.get("/api/admin/bot/receipt/{order_id}")
def bot_receipt(order_id: int, x_admin_password: str = Header(None)):
    """
    تصویر رسید — فقط با هدر.

    پیش‌تر رمزِ مدیر در پارامترِ `?pw=` هم پذیرفته می‌شد، چون تگِ <img>
    هدر نمی‌فرستد. یعنی رمز در لاگِ دسترسیِ nginx، تاریخچه‌ی مرورگر و
    هدرِ Referer می‌نشست — برای هر رسیدی که صفحه نشان می‌داد. رابط حالا
    تصویر را با هدر می‌گیرد و از blob نشان می‌دهد.
    """
    """
    تصویر رسید یک سفارش.

    تلگرام فایل‌ها را با file_id نگه می‌دارد. اینجا آن را به لینک
    موقت تبدیل می‌کنیم، محتوا را می‌گیریم و به‌صورت تصویر برمی‌گردانیم
    تا پنل بتواند نمایش و بزرگ‌نمایی کند.
    """
    check_auth(x_admin_password)
    con = _bot_conn()
    if not con:
        raise HTTPException(status_code=404, detail="دیتابیس ربات موجود نیست")

    try:
        row = con.execute(
            "SELECT o.receipt_type, o.receipt_file, o.receipt_text, o.tenant_id "
            "FROM orders o WHERE o.id=?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="سفارش پیدا نشد")

        if row["receipt_type"] != "photo" or not row["receipt_file"]:
            raise HTTPException(status_code=404, detail="این سفارش رسید تصویری ندارد")

        # رسیدی که خودمان نگه داشته‌ایم — بدون رفتن به تلگرام.
        # یک قاعده‌ی نمایش، دو منبع: دیسک برای رسیدهای مینی‌اپ،
        # تلگرام برای رسیدهایی که در خودِ گفتگو آمده‌اند.
        _lp = _receipt_local(row["receipt_file"])
        if _lp:
            _blob = _lp.read_bytes()
            _e, _ct = _logo_kind(_blob)
            if _ct:
                return Response(content=_blob, media_type=_ct,
                                headers={"Cache-Control": "private, max-age=60"})
            raise HTTPException(status_code=404, detail="فایل رسید سالم نیست")

        t = con.execute("SELECT bot_token FROM tenants WHERE id=?",
                        (row["tenant_id"],)).fetchone()
        token = t["bot_token"] if t else None
        if not token:
            raise HTTPException(status_code=400, detail="توکن ربات تنظیم نشده است")
    finally:
        con.close()

    try:
        import requests
        from fastapi.responses import Response as FastResponse

        r = requests.get(f"https://api.telegram.org/bot{token}/getFile",
                         params={"file_id": row["receipt_file"]}, timeout=15)
        d = r.json()
        if not d.get("ok"):
            raise HTTPException(status_code=502,
                                detail="تلگرام فایل را برنگرداند")

        path = d["result"]["file_path"]
        img = requests.get(f"https://api.telegram.org/file/bot{token}/{path}",
                           timeout=25)
        if img.status_code != 200:
            raise HTTPException(status_code=502, detail="دریافت تصویر ناموفق بود")

        ext = path.rsplit(".", 1)[-1].lower() if "." in path else "jpg"
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")

        return FastResponse(content=img.content, media_type=mime,
                            headers={"Cache-Control": "private, max-age=600"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"خطا در دریافت رسید: {str(e)[:150]}")


@app.get("/api/admin/bot/subscriber/{tg_id}")
def bot_subscriber_detail(tg_id: int, x_admin_password: str = Header(...)):
    """
    پرونده‌ی کامل یک مشتری: اطلاعات ربات + مصرف زنده از 3x-ui.

    ترافیک از خود پنل خوانده می‌شود نه از کش، چون عددی که به ادمین
    نشان می‌دهیم باید همان چیزی باشد که مشتری می‌بیند.
    """
    check_auth(x_admin_password)
    return _subscriber(_root_tid(), tg_id)


def _subscriber(tid, tg_id):
    """
    پرونده‌ی یک مشتری در **یک** مستاجر.

    تا امروز کاربر فقط با `tg_id` پیدا می‌شد. یک نفر می‌تواند هم از
    رباتِ مالک بخرد هم از رباتِ نماینده — دو ردیف با یک `tg_id` — و
    `fetchone()` هر کدام را که پیش می‌آمد برمی‌داشت.
    """
    # this shop's sweep first, as the mini app does: a config deleted in
    # 3x-ui leaves this list now, not at the next pass
    _t = _tenant_row(tid)
    if _t:
        sub_sweep_shop_now(_t)
    con = _tenant_conn(tid)
    if not con:
        raise HTTPException(status_code=404, detail="دیتابیس ربات موجود نیست")

    try:
        u = con.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
        user = dict(u)

        # deleted configs (by the sweep, by hand in 3x-ui, with the user)
        # are gone here too, as in the bot and the mini app
        subs = [dict(r) for r in con.execute(
            "SELECT s.*, p.name AS plan_name FROM subscriptions s "
            "LEFT JOIN plans p ON p.id = s.plan_id "
            "WHERE s.user_id = ? AND s.deleted_at IS NULL "
            "ORDER BY s.created_at DESC", (user["id"],))]

        orders = [dict(r) for r in con.execute(
            "SELECT o.*, p.name AS plan_name FROM orders o "
            "LEFT JOIN plans p ON p.id = o.plan_id "
            "WHERE o.user_id = ? ORDER BY o.created_at DESC LIMIT 20", (user["id"],))]

        coins = [dict(r) for r in con.execute(
            "SELECT * FROM coin_tx WHERE user_id=? ORDER BY created_at DESC LIMIT 15",
            (user["id"],))]

        _trow = con.execute("SELECT * FROM tenants WHERE id=?",
                            (user["tenant_id"],)).fetchone()
    finally:
        con.close()

    # نماینده پنلِ جدا ندارد؛ مصرفِ زنده از پنلِ مالک می‌آید — همان
    # قاعده‌ی `_panel_row` که ساخت و تمدید هم از آن می‌گذرند.
    tenant = _panel_row(dict(_trow)) if _trow else None

    # Live usage from the x-ui database, the same read the sweep, the mini
    # app and accounting use. It used to ask the API config by config; when
    # that API did not answer, every config said "no live data" and nothing
    # could tell a deleted config from a live one.
    live = {}
    clients, _k, _e = _read_xui_clients()
    if clients:
        idx = {c.get("email"): c for c in clients if c.get("email")}
        for s in subs:
            c = idx.get(s.get("client_email"))
            if c:
                live[s["client_email"]] = {
                    "up": 0, "down": int(c.get("used") or 0),
                    "total": int(c.get("totalGB") or 0),
                    "expiryTime": int(c.get("expiry") or 0),
                    "enable": bool(c.get("enable", True)), "inboundId": None}
    if not live and tenant and tenant["panel_url"]:
        try:
            import sys as _sys
            bd = str(_bot_dir())
            if bd not in _sys.path:
                _sys.path.insert(0, bd)
            from xui import XUI  # noqa: E402

            client = XUI(tenant["panel_url"], tenant["panel_user"],
                         tenant["panel_pass"], tenant["panel_token"])
            for s in subs:
                email = s.get("client_email")
                if not email:
                    continue
                try:
                    t = client.client_traffic(email)
                    if t:
                        if isinstance(t, list):
                            t = t[0] if t else None
                        if t:
                            live[email] = {
                                "up": t.get("up", 0),
                                "down": t.get("down", 0),
                                "total": t.get("total", 0),
                                "expiryTime": t.get("expiryTime", 0),
                                "enable": t.get("enable", True),
                                "inboundId": t.get("inboundId"),
                            }
                except Exception as _exc:
                    log.debug("subscriber traffic: %s", _exc)
        except Exception:
            pass

    return {
        "user": user,
        "subscriptions": subs,
        "orders": orders,
        "coinHistory": coins,
        "live": live,
        "liveAvailable": bool(live),
    }


@app.post("/api/admin/bot/message/{tg_id}")
def bot_message_user(tg_id: int, payload: dict,
                     x_admin_password: str = Header(...)):
    """
    پیام مستقیم ادمین به یک کاربر، از طریق ربات.

    بدون این، ادمین برای هر تماسی باید از پنل بیرون می‌رفت و در تلگرام
    دنبال کاربر می‌گشت — و اگر کاربر یوزرنیم نداشت، اصلاً راهی نبود.
    """
    check_auth(x_admin_password)
    return _message_user(_root_tid(), tg_id, payload)


def _message_user(tid, tg_id, payload):
    """
    پیام از رباتِ **همین** مستاجر به مشتریِ **همین** مستاجر.

    قبلاً کاربر با `tg_id` از هر مستاجری پیدا می‌شد و توکنِ رباتِ
    همان ردیف برداشته می‌شد — یعنی پیامِ مالک می‌توانست از رباتِ
    نماینده برود.
    """
    text = (payload or {}).get("text") or ""
    text = str(text).strip()
    if not text:
        raise HTTPException(status_code=400, detail="متن پیام خالی است")
    if len(text) > 3500:
        raise HTTPException(status_code=400,
                            detail="متن پیام از ۳۵۰۰ کاراکتر بیشتر است")

    con = _tenant_conn(tid)
    if not con:
        raise HTTPException(status_code=404, detail="دیتابیس ربات موجود نیست")
    try:
        u = con.execute("SELECT id, tenant_id, first_name, is_blocked "
                        "FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
        t = con.execute("SELECT bot_token FROM tenants WHERE id=?",
                        (u["tenant_id"],)).fetchone()
    finally:
        con.close()

    token = t["bot_token"] if t else None
    if not token:
        raise HTTPException(status_code=400, detail="توکن ربات تنظیم نشده است")

    # امضای «پیام از پشتیبانی» تا کاربر نداند این پیام خودکار است یا انسان
    body = json.dumps({
        "chat_id": tg_id,
        "text": f"💬 <b>پیام از پشتیبانی</b>\n\n{text}",
        "parse_mode": "HTML",
    }).encode()

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8")).get("description", "")
        except Exception:
            err = str(e)
        # پرتکرارترین حالت: کاربر ربات را بلاک کرده — این خطای ما نیست
        if "blocked" in err.lower() or "deactivated" in err.lower():
            raise HTTPException(status_code=409,
                                detail="کاربر ربات را بلاک کرده یا حسابش حذف شده")
        raise HTTPException(status_code=400, detail=f"تلگرام: {err[:200]}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ارسال ناموفق: {str(e)[:160]}")

    if not res.get("ok"):
        raise HTTPException(status_code=400,
                            detail=res.get("description") or "ارسال ناموفق")

    return {"ok": True, "sentTo": tg_id}


@app.post("/api/admin/bot/reload")
def bot_reload(x_admin_password: str = Header(...)):
    """
    اعلام به ربات که تنظیمات عوض شده.

    ربات تنظیمات را در هر درخواست تازه می‌خواند، پس تغییرات معمولاً
    فوری اعمال می‌شوند. این endpoint برای مواردی است که ربات چیزی را
    در حافظه نگه داشته — مثل نخِ یک مستاجر که توکنش عوض شده.

    یک فلگ در دیتابیس می‌گذاریم؛ ربات در چرخه‌ی بعدی می‌بیندش و
    خودش را همگام می‌کند. بدون قطعی سرویس.
    """
    check_auth(x_admin_password)
    if not BOT_DB.exists():
        raise HTTPException(status_code=400, detail="دیتابیس ربات موجود نیست")

    con = _bot_rw()
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS bot_flags ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT,"
            "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        con.execute(
            "INSERT INTO bot_flags (key, value, updated_at) VALUES ('reload', ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (str(int(datetime.now().timestamp())),))
        con.commit()
        return {"ok": True, "running": _svc_active()}
    finally:
        con.close()


@app.post("/api/admin/bot/test-connection")
def bot_test_connection(payload: dict, x_admin_password: str = Header(...)):
    """
    تست کامل اتصال به 3x-ui — مرحله به مرحله.

    فقط «وصل شد» کافی نیست. کاربر باید مطمئن شود که ربات واقعاً
    می‌تواند کانفیگ بسازد. پس یک کلاینت آزمایشی می‌سازیم، بررسی
    می‌کنیم، و بلافاصله پاکش می‌کنیم.
    """
    check_auth(x_admin_password)

    bot_dir = _bot_dir()
    if not (bot_dir / "xui.py").exists():
        raise HTTPException(status_code=400, detail="ماژول ربات روی سرور نیست")

    # اطلاعات از payload یا از تنظیمات ذخیره‌شده
    url = (payload or {}).get("panel_url")
    user = (payload or {}).get("panel_user")
    pw = (payload or {}).get("panel_pass")
    token = (payload or {}).get("panel_token")
    inbound = (payload or {}).get("default_inbound")

    if not url or (token and str(token).endswith("…")) or (pw and str(pw).endswith("…")):
        con = _bot_conn()
        if con:
            try:
                row = con.execute(
                    "SELECT * FROM tenants WHERE parent_id IS NULL ORDER BY id LIMIT 1"
                ).fetchone()
                if row:
                    r = dict(row)
                    url = url or r.get("panel_url")
                    user = user or r.get("panel_user")
                    if not pw or str(pw).endswith("…"):
                        pw = r.get("panel_pass")
                    if not token or str(token).endswith("…"):
                        token = r.get("panel_token")
                    inbound = inbound or r.get("default_inbound")
            finally:
                con.close()

    if not url:
        raise HTTPException(status_code=400, detail="آدرس پنل وارد نشده است")

    steps = []

    def step(key, title, ok, detail="", hint=""):
        steps.append({"key": key, "title": title, "ok": ok,
                      "detail": detail, "hint": hint})
        return ok

    import sys as _sys
    if str(bot_dir) not in _sys.path:
        _sys.path.insert(0, str(bot_dir))

    try:
        import importlib
        xmod = importlib.import_module("xui")
        importlib.reload(xmod)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"بارگذاری ماژول ناموفق: {str(e)[:150]}")

    client = xmod.XUI(url, user, pw, token)

    # ۱ — احراز هویت
    try:
        client.login()
        method = "توکن API" if token else "نام کاربری و رمز"
        step("auth", "احراز هویت", True, f"با {method} وارد شد")
    except Exception as e:
        step("auth", "احراز هویت", False, str(e)[:180],
             "آدرس پنل، توکن یا نام کاربری و رمز را بررسی کنید. "
             "آدرس باید شامل پورت و مسیر باشد.")
        return {"ok": False, "steps": steps}

    # ۲ — خواندن inboundها
    inbounds = []
    try:
        inbounds = client.inbounds() or []
        names = [f"#{i.get('id')} {i.get('remark') or i.get('protocol','')}"
                 for i in inbounds[:6]]
        step("inbounds", "خواندن inboundها", bool(inbounds),
             f"{len(inbounds)} inbound: " + " · ".join(names) if inbounds
             else "هیچ inbound فعالی پیدا نشد",
             "" if inbounds else "ابتدا در پنل 3x-ui یک inbound بسازید.")
        if not inbounds:
            return {"ok": False, "steps": steps}
    except Exception as e:
        step("inbounds", "خواندن inboundها", False, str(e)[:180],
             "کاربر پنل باید دسترسی خواندن داشته باشد.")
        return {"ok": False, "steps": steps}

    # ۳ — معماری پنل
    #
    # از نسخه‌ی ۳ به بعد پنل مشخصات OpenAPI خودش را سرو می‌کند.
    # اگر بتوانیم بخوانیمش، دیگر حدس نمی‌زنیم کدام مسیر را صدا بزنیم.
    try:
        routes = client.discover()
    except Exception:
        routes = {}

    if routes:
        modern = any(p.startswith("/panel/api/clients") for p in routes)
        step("api", "مسیرهای API", True,
             f"{len(routes)} مسیر از خود پنل خوانده شد — "
             + ("معماری کلاینت مستقل" if modern else "معماری کلاسیک"))
    else:
        try:
            mode = client.detect_api()
            step("api", "تشخیص نسخه پنل", True,
                 "معماری جدید (۳.۴ به بعد)" if mode == "modern" else "معماری کلاسیک",
                 "مشخصات OpenAPI خوانده نشد — مسیرها با آزمون‌وخطا پیدا می‌شوند")
        except Exception:
            step("api", "تشخیص نسخه پنل", True, "کلاسیک (پیش‌فرض)")

    # ۴ — inbound انتخاب‌شده
    target = None
    if inbound:
        try:
            target = int(inbound)
        except (TypeError, ValueError):
            target = None
    if target is None:
        target = inbounds[0].get("id")
        step("inbound", "inbound پیش‌فرض", True,
             f"#{target} (اولین inbound — در تنظیمات مشخص نشده بود)",
             "بهتر است inbound دلخواهتان را در تنظیمات مشخص کنید.")
    else:
        found = any(int(i.get("id", -1)) == target for i in inbounds)
        if not step("inbound", "inbound پیش‌فرض", found,
                    f"#{target}" if found else f"#{target} در پنل وجود ندارد",
                    "" if found else "شماره‌ی درست را از لیست بالا انتخاب کنید."):
            return {"ok": False, "steps": steps}

    # ۵ — ساخت کلاینت آزمایشی
    import uuid as _uuid
    probe = f"nexora_test_{_uuid.uuid4().hex[:8]}"
    created = False
    try:
        client.add_client(target, probe, gb=1, days=1, ip_limit=1)
        created = True
        step("create", "ساخت کانفیگ آزمایشی", True, f"کلاینت {probe} ساخته شد")
    except Exception as e:
        step("create", "ساخت کانفیگ آزمایشی", False, str(e)[:180],
             "کاربر پنل باید دسترسی نوشتن داشته باشد. "
             "اگر از توکن استفاده می‌کنید، مطمئن شوید توکن محدود نشده باشد.")
        return {"ok": False, "steps": steps}

    # ۶ — خواندن کلاینت ساخته‌شده
    try:
        # آرگومان اول inbound است نه ایمیل — قبلاً ایمیل به‌جای
        # inbound می‌رفت و این مرحله همیشه «خوانده نشد» می‌داد،
        # حتی وقتی کلاینت درست ساخته شده بود.
        found = client.find_client(target, email=probe)
        step("verify", "بازخوانی کانفیگ", bool(found),
             "کلاینت در پنل پیدا شد" if found else "ساخته شد ولی خوانده نشد",
             "" if found else "ممکن است پنل هنوز همگام نشده باشد.")
    except Exception as e:
        step("verify", "بازخوانی کانفیگ", False, str(e)[:180])

    # ۷ — پاکسازی (مهم: نباید کلاینت آشغال بماند)
    if created:
        try:
            # در نسخه‌ی ۳ حذف با ایمیل انجام می‌شود؛ اگر ایمیل را
            # به‌جای uuid بفرستیم مسیرهای درست اصلاً امتحان نمی‌شوند
            # و کلاینت آزمایشی در پنل باقی می‌ماند.
            client.delete_client(target, None, email=probe)
            step("cleanup", "پاکسازی", True, "کلاینت آزمایشی حذف شد")
        except Exception as e:
            step("cleanup", "پاکسازی", False, str(e)[:180],
                 f"کلاینت «{probe}» را دستی از پنل حذف کنید.")

    all_ok = all(s["ok"] for s in steps)
    return {
        "ok": all_ok,
        "steps": steps,
        "inbounds": [{"id": i.get("id"),
                      "remark": i.get("remark") or "",
                      "protocol": i.get("protocol") or "",
                      "port": i.get("port")}
                     for i in inbounds],
    }


@app.get("/api/admin/github")
def github_get(x_admin_password: str = Header(...)):
    """تنظیمات مخزن گیت‌هاب برای به‌روزرسانی."""
    check_auth(x_admin_password)
    f = _root_dir() / ".github"
    repo = ""
    if f.exists():
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("GITHUB_REPO="):
                    repo = line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception as _exc:
            log.warning("reading github repo file: %s", _exc)
    return {"repo": repo, "configured": bool(repo)}


@app.put("/api/admin/github")
def github_put(payload: dict, x_admin_password: str = Header(...)):
    """
    ذخیره‌ی مخزن گیت‌هاب.

    قبل از ذخیره، وجود مخزن و داشتن Release بررسی می‌شود — تا کاربر
    یک آدرس اشتباه ذخیره نکند و بعد در به‌روزرسانی گیر کند.
    """
    check_auth(x_admin_password)
    repo = (payload or {}).get("repo", "").strip()

    # نرمال‌سازی: از URL کامل هم قبول می‌کنیم
    repo = repo.replace("https://github.com/", "").replace("http://github.com/", "")
    repo = repo.rstrip("/").removesuffix(".git")

    if not repo:
        f = _root_dir() / ".github"
        try:
            f.unlink(missing_ok=True)
        except Exception as _exc:
            log.warning("github token file cleanup: %s", _exc)
        return {"ok": True, "repo": "", "configured": False}

    if repo.count("/") != 1 or not all(repo.split("/")):
        raise HTTPException(status_code=400,
                            detail="قالب درست: username/repository")

    # بررسی واقعی
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "nexora-panel"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
        tag = data.get("tag_name", "")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(
                status_code=400,
                detail=f"مخزن «{repo}» پیدا نشد یا هیچ Release ندارد. "
                       "مطمئن شوید عمومی است و حداقل یک Release ساخته‌اید.")
        raise HTTPException(status_code=400, detail=f"گیت‌هاب پاسخ نداد: {e.code}")
    except Exception as e:
        raise HTTPException(status_code=400,
                            detail=f"بررسی مخزن ناموفق: {str(e)[:120]}")

    f = _root_dir() / ".github"
    f.write_text(f'GITHUB_REPO="{repo}"\n', encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except Exception as e:
        # توکنِ گیت‌هاب در این فایل است
        log.warning("could not restrict %s to 0600: %s", f, e)

    return {"ok": True, "repo": repo, "configured": True, "latestTag": tag}


# ═══════════════════════════════════════════════════════════
#  حسابداری واسطه‌ها
#
#  گروه‌ها و مصرف واقعی از x-ui.db خوانده می‌شوند (فقط‌خواندنی).
#  نرخ‌ها، پرداخت‌ها و لاگ تمدید در دیتابیس خودمان ذخیره می‌شوند.
# ═══════════════════════════════════════════════════════════

# مسیر دیتابیس x-ui.
#
# اولویت: تنظیمات پنل ← متغیر محیطی ← مسیرهای رایج.
# اگر فقط به متغیر محیطی تکیه کنیم، نصب‌های قدیمی که آن را ندارند
# حسابداری‌شان کار نمی‌کند و کاربر هم راهی برای اصلاحش ندارد.
XUI_CANDIDATES = [
    "/etc/x-ui/x-ui.db",
    "/usr/local/x-ui/x-ui.db",
    "/opt/x-ui/x-ui.db",
    "/etc/x-ui/db/x-ui.db",
]


def _xui_db_path():
    """مسیر فعلی دیتابیس x-ui را برمی‌گرداند."""
    # ۱. تنظیم دستی در پنل.
    #
    # اگر مسیر دستی وجود نداشته باشد (غلط تایپی، فاصله‌ی اضافه،
    # جابه‌جایی فایل) نباید همان‌جا شکست بخوریم — بقیه‌ی راه‌ها را
    # امتحان می‌کنیم. وگرنه یک اشتباه کوچک، حسابداری را برای همیشه
    # از کار می‌اندازد.
    try:
        cfg = load_config()
        manual = ((cfg.get("advanced") or {}).get("xuiDbPath") or "").strip()
        # کاراکترهای نامرئی که هنگام کپی‌پیست می‌آیند
        manual = manual.strip("\u200c\u200e\u200f\ufeff'\" ")
        if manual and Path(manual).exists():
            return Path(manual)
    except Exception:
        manual = ""

    # ۲. متغیر محیطی
    env = os.getenv("XUI_DB_PATH", "").strip()
    if env and Path(env).exists():
        return Path(env)

    # ۳. مسیرهای رایج — تازه‌ترین، نه اولینِ فهرست.
    #
    # چرا این‌طور شد: نصب‌های واقعی بیش از یک `x-ui.db` دارند. نصبِ
    # دوباره، مهاجرت از یک مسیر به مسیر دیگر، یا بک‌آپی که کنارش
    # مانده — و فهرستِ بالا اولینِ موجود را برمی‌داشت.
    #
    # نتیجه‌اش بی‌صدا بود و از بیرون شبیهِ خرابیِ حسابداری: پنل عددِ
    # یک فایلِ مرده را می‌خواند که هیچ‌وقت عوض نمی‌شد، و مالک
    # می‌دید مصرف «آپدیت نمی‌شود» و با پنلِ خودِ x-ui هم نمی‌خواند.
    #
    # x-ui هر چند ثانیه روی فایلِ زنده می‌نویسد، پس تازه‌ترین
    # `mtime` همان فایلِ زنده است. این حدس نیست؛ قابلِ سنجش است.
    found = []
    for p in XUI_CANDIDATES:
        pp = Path(p)
        try:
            if pp.exists():
                found.append((pp.stat().st_mtime, pp))
        except OSError:
            continue
    if found:
        found.sort(key=lambda x: x[0], reverse=True)
        return found[0][1]

    # هیچ‌کدام پیدا نشد — مسیری که کاربر انتظار دارد را برمی‌گردانیم
    # تا پیام خطا به همان اشاره کند، نه به یک مسیر پیش‌فرض گیج‌کننده.
    if manual:
        return Path(manual)
    if env:
        return Path(env)
    return Path(XUI_CANDIDATES[0])
def _xui_db_candidates():
    """
    همه‌ی فایل‌های `x-ui.db` که پیدا می‌شوند، با زمانِ آخرین نوشتن.

    برای تشخیص هم هست و هم برای هشدار: وقتی بیش از یکی هست، یعنی
    ممکن است پنل به فایلِ اشتباه نگاه کند — و آن خرابی بی‌صداست.
    """
    out = []
    seen = set()
    for p in XUI_CANDIDATES:
        pp = Path(p)
        try:
            if not pp.exists():
                continue
            key = str(pp.resolve())
            if key in seen:
                continue
            seen.add(key)
            st = pp.stat()
            out.append({"path": str(pp), "mtime": st.st_mtime,
                        "size": st.st_size})
        except OSError:
            continue
    out.sort(key=lambda d: d["mtime"], reverse=True)
    return out


BILLING_DB = Path(os.getenv("BILLING_DB_PATH", str(CONFIG_PATH.parent / "billing.db")))


def _xui_conn():
    """
    اتصال فقط‌خواندنی به دیتابیس x-ui.

    برمی‌گرداند: (اتصال, پیام‌خطا)
    خطای واقعی برگردانده می‌شود نه None خالی — چون «پیدا نشد» و
    «مجوز ندارد» و «قفل است» سه مشکل کاملاً متفاوت‌اند و کاربر باید
    بداند کدام است تا بتواند رفعش کند.
    """
    xdb = _xui_db_path()

    if not xdb.exists():
        parent = xdb.parent
        if not parent.exists():
            return None, (f"پوشه‌ی {parent} وجود ندارد. "
                          "مطمئن شوید ۳x-ui روی همین سرور نصب است.")
        return None, f"فایل {xdb.name} در {parent} پیدا نشد"

    if not os.access(xdb, os.R_OK):
        try:
            st = xdb.stat()
            perm = oct(st.st_mode)[-3:]
        except Exception:
            perm = "?"
        return None, (f"فایل هست ولی پنل اجازه‌ی خواندنش را ندارد "
                      f"(مجوز فعلی: {perm}). روی سرور اجرا کنید: "
                      f"chmod +r {xdb}")

    import sqlite3

    def _try_open(uri):
        con = sqlite3.connect(uri, uri=True, timeout=8)
        con.row_factory = sqlite3.Row
        # SQLite تنبل است: تا به جدول‌ها دست نزنی، فایل خراب را هم
        # بی‌صدا قبول می‌کند. پس فهرست جدول‌ها را می‌خوانیم.
        con.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return con

    # فایل‌های جانبی WAL هم باید خواندنی باشند، وگرنه SQLite کل
    # دیتابیس را باز نمی‌کند. این را قبل از تلاش بررسی می‌کنیم چون
    # پیام خطای خودش گمراه‌کننده است.
    for suffix in ("-wal", "-shm"):
        side = xdb.with_name(xdb.name + suffix)
        if side.exists() and not os.access(side, os.R_OK):
            return None, (f"فایل {side.name} خواندنی نیست. ۳x-ui در حالت WAL است و "
                          f"این فایل هم لازم است. اجرا کنید: "
                          f"chmod +r {xdb.parent}/{xdb.name}*")

    try:
        # حالت اول: فقط‌خواندنی معمولی
        return _try_open(f"file:{xdb}?mode=ro"), None
    except sqlite3.OperationalError as first:
        # اگر دیتابیس در حالت WAL باشد، mode=ro به فایل‌های جانبی
        # (-wal و -shm) هم نیاز دارد و اگر آن‌ها خواندنی نباشند
        # شکست می‌خورد. immutable=1 این وابستگی را دور می‌زند.
        #
        # امن است چون x-ui در حال نوشتن است ولی ما فقط می‌خوانیم؛
        # بدترین حالت این است که چند ثانیه داده‌ی قدیمی‌تر ببینیم.
        # immutable فقط وقتی درست است که فایل -wal وجود نداشته باشد،
        # وگرنه داده‌های اخیر دیده نمی‌شوند و جدول‌ها خالی به نظر می‌رسند.
        if not xdb.with_name(xdb.name + "-wal").exists():
            try:
                return _try_open(f"file:{xdb}?immutable=1"), None
            except Exception as _exc:
                log.debug("x-ui immutable open: %s", _exc)

        msg = str(first)
        low = msg.lower()
        if "locked" in low:
            return None, "دیتابیس ۳x-ui قفل است. چند لحظه بعد دوباره امتحان کنید."
        if "unable to open" in low:
            wal = xdb.with_name(xdb.name + "-wal")
            hint = ""
            if wal.exists() and not os.access(wal, os.R_OK):
                hint = f" فایل {wal.name} هم باید خواندنی باشد: chmod +r {wal}"
            return None, (f"باز کردن دیتابیس ممکن نشد. معمولاً یعنی پنل به پوشه‌ی "
                          f"{xdb.parent} دسترسی ندارد: chmod o+x {xdb.parent}" + hint)
        if "not a database" in low:
            return None, f"فایل {xdb.name} یک دیتابیس SQLite معتبر نیست"
        return None, f"باز کردن دیتابیس ناموفق: {msg[:120]}"
    except sqlite3.OperationalError as e:
        msg = str(e)
        if "locked" in msg.lower():
            return None, "دیتابیس ۳x-ui قفل است. چند لحظه بعد دوباره امتحان کنید."
        if "not a database" in msg.lower():
            return None, f"فایل {xdb} یک دیتابیس SQLite معتبر نیست"
        return None, f"باز کردن دیتابیس ناموفق: {msg[:120]}"
    except sqlite3.DatabaseError as e:
        if "not a database" in str(e).lower():
            return None, f"فایل {xdb.name} یک دیتابیس SQLite معتبر نیست"
        return None, f"خواندن دیتابیس ناموفق: {str(e)[:110]}"
    except Exception as e:
        return None, f"خطای غیرمنتظره: {type(e).__name__}: {str(e)[:110]}"


def _billing_conn():
    """
    دیتابیس حسابداری — جدا از x-ui تا هرگز به آن دست نزنیم.

    اگر فایل خراب باشد (قطع برق وسط نوشتن، کپی ناقص) کنارش
    می‌گذاریم و از نو می‌سازیم. از دست رفتن نرخ‌ها بد است، ولی
    از کار افتادن کل بخش حسابداری بدتر.
    """
    import sqlite3
    BILLING_DB.parent.mkdir(parents=True, exist_ok=True)

    def _open():
        con = sqlite3.connect(str(BILLING_DB), timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return con

    try:
        con = _open()
    except sqlite3.DatabaseError:
        # فایل سالم نیست — کنار می‌گذاریم تا قابل بازیابی دستی بماند
        try:
            broken = BILLING_DB.with_name(
                f"{BILLING_DB.stem}-corrupt-{datetime.now():%Y%m%d-%H%M%S}.db")
            BILLING_DB.replace(broken)
        except Exception:
            try:
                BILLING_DB.unlink(missing_ok=True)
            except Exception as _exc:
                log.warning("billing db setup: %s", _exc)
        con = _open()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS group_config (
            group_key   TEXT PRIMARY KEY,
            label       TEXT,
            billable    INTEGER DEFAULT 0,
            rates         TEXT DEFAULT '[]',
            per_gb        INTEGER DEFAULT 0,
            period_days   INTEGER DEFAULT 30,
            period_start  TEXT,
            settled_until TEXT,
            note          TEXT,
            updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            group_key   TEXT NOT NULL,
            amount      INTEGER NOT NULL,
            paid_at     TEXT NOT NULL,
            note        TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        -- اولین باری که پنل هر کلاینت را دید.
        --
        -- نسخه‌های قدیمی x-ui تاریخ ساخت کلاینت را نگه نمی‌دارند، و آن
        -- اطلاعات جای دیگری هم وجود ندارد — پس هر کانفیگ «یک ماهه»
        -- حساب می‌شد و واسطه‌ای که دو سال کار کرده، یک ماه صورت‌حساب
        -- می‌گرفت.
        --
        -- گذشته را نمی‌شود ساخت، ولی از امروز به بعد می‌شود ثبت کرد.
        -- این کف مطمئنی می‌دهد: «دست‌کم از این تاریخ می‌شناسیمش».
        CREATE TABLE IF NOT EXISTS client_seen (
            email      TEXT PRIMARY KEY,
            group_key  TEXT,
            first_seen TEXT NOT NULL,
            last_seen  TEXT,
            -- آخرین انقضایی که از این کلاینت دیدیم.
            --
            -- بدون این، تمدید اصلاً قابل تشخیص نیست: پنل دست واسطه
            -- است، او مستقیم در x-ui تمدید می‌کند، و x-ui هیچ
            -- تاریخچه‌ای نگه نمی‌دارد. تنها راه فهمیدنش این است که
            -- خودمان انقضا را به خاطر بسپاریم و دفعه‌ی بعد مقایسه
            -- کنیم — اگر جلو رفته باشد، تمدید شده.
            last_expiry INTEGER,

            -- مصرف، و همان قاعده برای ترافیک.
            --
            -- x-ui با ریست‌شدنِ ترافیک `up` و `down` را صفر می‌کند و
            -- عددِ قبلی برای همیشه می‌رود. اندازه‌گیری‌شده: کانفیگِ
            -- ۵۰۰ گیگی که ۵۰۰ مصرف کرد، ریست خورد، و ۴۵۰ دیگر مصرف
            -- کرد — پنل ۴۵۰ نشان می‌داد و ۵۰۰ گیگ بی‌صدا گم شده بود.
            --
            -- روی صورتحساب یعنی واسطه‌ای که با ریست‌زدن دو برابر حجم
            -- فروخته، یک‌بار پول می‌دهد.
            --
            -- `used_before` جمعِ دوره‌های ریست‌شده است و `last_used`
            -- مبنای مقایسه. افتادنِ عدد یعنی ریست.
            last_used   INTEGER,
            used_before INTEGER DEFAULT 0
        );

        -- لاگ تمدید: x-ui تاریخچه ندارد، پس از امروز خودمان ثبت می‌کنیم
        CREATE TABLE IF NOT EXISTS renewals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT NOT NULL,
            group_key   TEXT,
            months      INTEGER DEFAULT 1,
            gb          INTEGER,
            source      TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        -- هزینه‌ها: سرور خارج، سرور ایران، خرید حجم، دامنه و بقیه.
        -- بدون این، «درآمد» عدد بی‌معنایی است؛ سود آن چیزی است که
        -- بعد از کم‌کردن اینها می‌ماند.
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kind        TEXT NOT NULL,      -- server_abroad | server_iran | traffic | domain | other
            label       TEXT NOT NULL,
            amount      REAL NOT NULL,      -- به واحد currency
            currency    TEXT DEFAULT 'IRT', -- IRT | EUR | USD
            -- مبلغ تومانیِ *لحظه‌ی خرید*. عمداً ذخیره می‌شود و دوباره
            -- محاسبه نمی‌شود: اگر هر بار با نرخ روز حساب کنیم، هزینه‌ی
            -- ماه پیش با تکان‌خوردن بازار عوض می‌شود.
            amount_irt  INTEGER,
            fx_rate     INTEGER,
            fx_source   TEXT,
            gb          INTEGER,            -- برای خرید حجم
            recurring   TEXT DEFAULT 'once',-- once | monthly | yearly
            spent_at    TEXT NOT NULL,
            note        TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        -- کانفیگ‌هایی که پاک شدند در حالی که بدهی داشتند.
        --
        -- صورتحساب از فهرستِ *زنده‌ی* x-ui خوانده می‌شود، پس ردیفی که
        -- پاک شود کاملاً از فاکتور غیب می‌شود — چه نماینده پاکش کند
        -- چه خودِ مالک. این یعنی «حذف» می‌تواند راه فرار از پرداخت
        -- باشد، درست همان چیزی که مالک درباره‌ی انقضا هشدار داد.
        --
        -- ردیف‌های این جدول عدد را عوض نمی‌کنند؛ فقط می‌گویند چه چیزی
        -- و با چه مبلغی از فاکتور بیرون رفت، تا تصمیمش با مالک باشد
        -- نه با سکوت.
        CREATE TABLE IF NOT EXISTS deleted_clients (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT NOT NULL,
            group_key   TEXT,
            deleted_at  TEXT NOT NULL,
            months      REAL DEFAULT 0,
            amount      INTEGER DEFAULT 0,
            gb          INTEGER,
            used        INTEGER,
            by_whom     TEXT,
            note        TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_delcl_group
            ON deleted_clients(group_key, deleted_at);

        CREATE INDEX IF NOT EXISTS idx_pay_group ON payments(group_key);
        CREATE INDEX IF NOT EXISTS idx_ren_email ON renewals(email);
        CREATE INDEX IF NOT EXISTS idx_exp_date ON expenses(spent_at);
        CREATE INDEX IF NOT EXISTS idx_exp_kind ON expenses(kind);
    """)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(group_config)")}
        for col, decl in (("per_gb", "INTEGER DEFAULT 0"),
                          ("period_days", "INTEGER DEFAULT 30"),
                          ("period_start", "TEXT"),
                          ("settled_until", "TEXT"),
                          # مصرفِ کلِ گروهِ حجمی در لحظه‌ی تسویه (بایت) —
                          # دوره‌ی بعد فقط از این‌جا به بعد را می‌شمرد
                          ("settled_used", "INTEGER")):
            if col not in cols:
                con.execute(f"ALTER TABLE group_config ADD COLUMN {col} {decl}")
        dcols = {r[1] for r in con.execute("PRAGMA table_info(deleted_clients)")}
        if "used_live" not in dcols:
            # مصرفِ «جاریِ» کلاینت در لحظه‌ی حذف. بانکِ ریستِ x-ui در سطحِ گروه
            # می‌ماند، پس وقتی آن هست، فقط همین بخش با حذف گم می‌شد.
            con.execute("ALTER TABLE deleted_clients ADD COLUMN used_live INTEGER")
        pcols = {r[1] for r in con.execute("PRAGMA table_info(payments)")}
        if "settles" not in pcols:
            # پرداختی که با «تسویه» ثبت شد مالِ دوره‌ی بسته است. تاریخش همان
            # روزِ تسویه است و دوره‌ی تازه از همان روز پرداخت‌ها را می‌شمرد —
            # پس بی این علامت، پولِ دوره‌ی بسته دوباره اعتبارِ دوره‌ی تازه
            # می‌شد و نماینده بستانکار دیده می‌شد.
            con.execute("ALTER TABLE payments ADD COLUMN settles INTEGER DEFAULT 0")
            # یک‌بار: تسویه‌های پیشین — همان روزِ «تسویه‌شده تا» و یادداشتِ
            # «تسویه…». بیشتر از این حدس نمی‌زنیم.
            # یک‌بار: تاریخ‌های شمسیِ متنی که فرمِ قدیمی خام ذخیره می‌کرد
            _fixed = 0
            for _r in con.execute("SELECT id, paid_at FROM payments").fetchall():
                _iso = _iso_day(_r[1])
                if _iso and _iso != str(_r[1] or "")[:10]:
                    con.execute("UPDATE payments SET paid_at=? WHERE id=?", (_iso, _r[0]))
                    _fixed += 1
            if _fixed:
                log.warning("billing: %s payment date(s) were Jalali text — converted to ISO", _fixed)
            con.execute(
                "UPDATE payments SET settles=1 WHERE COALESCE(note,'') LIKE 'تسویه%' "
                "AND substr(COALESCE(paid_at,''),1,10) = (SELECT substr(COALESCE("
                "g.settled_until,''),1,10) FROM group_config g "
                "WHERE g.group_key = payments.group_key)")
    except Exception as _exc:
        log.warning("billing db setup: %s", _exc)

    con.commit()
    return con


def _jalali_to_gregorian(jy, jm, jd):
    """تبدیلِ شمسی به میلادی — الگوریتمِ استاندارد (jdf)، بی وابستگی."""
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    days += (jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    months = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 12 and gd > months[gm]:
        gd -= months[gm]
        gm += 1
    return gy, gm + 1, gd


def _iso_day(raw):
    """
    تاریخِ پرداخت به شکلِ YYYY-MM-DD، یا None اگر خواندنی نیست.

    چرا: فرمِ «ثبت پرداخت» تاریخ را متنی می‌گرفت («۱۴۰۵/۰۶/۲۵») و بکند
    همان را خام ذخیره می‌کرد. همه‌ی برش‌های دوره مقایسه‌ی رشته‌اند، و
    «۱۴۰۵…» با رقمِ فارسی از هر تاریخِ میلادی «بزرگ‌تر» است — یعنی آن
    پرداخت در هر دوره‌ای شمرده می‌شد، حتی بعد از تسویه. شمسی (سالِ کمتر از
    ۱۷۰۰) به میلادی برگردانده می‌شود.
    """
    from datetime import date as _d
    t = str(raw or "").strip().translate(_FA_DIGITS).replace("/", "-")[:10]
    parts = t.split("-")
    if len(parts) != 3 or not all(x.isdigit() for x in parts):
        return None
    y, m, dd = (int(x) for x in parts)
    try:
        if y < 1700:
            if not (1 <= m <= 12 and 1 <= dd <= 31):
                return None
            y, m, dd = _jalali_to_gregorian(y, m, dd)
        return _d(y, m, dd).isoformat()
    except ValueError:
        return None


def _period_payment(paid_at, settles, cut):
    """
    آیا این پرداخت مالِ دوره‌ای است که از `cut` شروع می‌شود؟

    یک‌جا، چون سه صفحه (داشبورد، صورتحساب، صفحه‌ی دوره) می‌پرسند. پرداختِ
    تسویه (`settles`) با تاریخِ خودِ روزِ تسویه ثبت می‌شود و مالِ دوره‌ی
    **بسته** است — نه دوره‌ای که از همان روز شروع می‌شود.
    """
    d = str(paid_at or "")[:10]
    if not cut:
        return True
    if d < cut:
        return False
    return not (settles and d <= cut)


def _deleted_usage(bcon, xui_bank, mixed=()):
    """
    {گروه: بایت} مصرفِ کانفیگ‌های حذف‌شده — برای بدهیِ حجمی.

    با بانکِ x-ui فقط مصرفِ جاریِ لحظه‌ی حذف گم شده (`used_live`)؛ بانکِ
    ریست‌های قبلی‌اش در گروه مانده. بی بانکِ x-ui، کلِ عمرش (`used`) —
    چون بانکِ خودمان از روی کلاینت‌های زنده ساخته می‌شود.

    A mixed group (`_volume_mixed`) counts only deleted configs that had a
    volume cap, over their whole life: its unlimited configs are billed at a
    rate, and its bank is the panel's per-config record, not x-ui's.
    """
    out = {}
    try:
        for r in bcon.execute(
                "SELECT group_key, COALESCE(SUM(used),0) u, "
                "COALESCE(SUM(COALESCE(used_live, used)),0) l, "
                "COALESCE(SUM(CASE WHEN COALESCE(gb,0) > 0 THEN used ELSE 0 END),0) c "
                "FROM deleted_clients GROUP BY group_key"):
            if r["group_key"] in mixed:
                out[r["group_key"]] = int(r["c"])
            else:
                out[r["group_key"]] = int(r["l"] if xui_bank else r["u"])
    except Exception as e:
        # بی‌صدا صفر نمی‌شود: بدهیِ حجمی کمتر از واقعیت یعنی پولِ ازدست‌رفته
        log.warning("deleted usage unreadable: %s", e)
    return out


def _volume_bill(conf, live_bytes, bank_bytes, deleted_bytes):
    """
    بدهیِ گروهِ **حجمی** — تنها جایی که ساخته می‌شود.

    مالک: «اگر ۱۰۰ گیگ تعریف کرد ولی کاربر ۳۰ گیگ مصرف کرد، پولِ همان ۳۰
    را می‌گیریم.» پس بدهی از مصرف است، نه از سقف یا تعدادِ ماه:

        کلِ عمر = مصرفِ زنده + بانکِ ریست + مصرفِ کانفیگ‌های حذف‌شده
        این دوره = کلِ عمر − مصرفِ لحظه‌ی تسویه (`settled_used`)

    تا ۱.۱۱۶ سه صفحه سه فرمول داشتند: داشبورد کلِ عمر را در برابرِ پرداخت‌های
    پس از تسویه می‌گذاشت، صورتحساب و پرتالِ نماینده نرخِ حجمی را اصلاً
    نمی‌دیدند (صفر)، و حذفِ کانفیگ مصرفش را از حساب برمی‌داشت.

    `basis`:
      period   تسویه با مصرفِ ثبت‌شده: فقط از آن به بعد، در برابرِ پرداخت‌های
               پس از تسویه
      running  هنوز چنین تسویه‌ای نیست: کلِ عمر در برابرِ **همه‌ی**
               پرداخت‌ها — حسابِ جاری. تسویه‌های حجمیِ پیش از این نسخه
               مصرفِ لحظه‌شان را نداشتند و همین‌جا می‌افتند.
    """
    per_gb = _price_per_gb(conf or {}) or 0
    life = max(0, int(live_bytes or 0) + int(bank_bytes or 0) + int(deleted_bytes or 0))
    snap = (conf or {}).get("settled_used")
    has_snap = snap is not None and str(snap) != ""
    base = int(snap or 0) if has_snap else 0
    billed = max(0, life - base)
    gib = 1024 ** 3
    return {
        "perGb": per_gb,
        "basis": "period" if has_snap else "running",
        "lifeBytes": life, "settledBytes": base, "billedBytes": billed,
        "deletedBytes": int(deleted_bytes or 0), "bankBytes": int(bank_bytes or 0),
        "billedGB": round(billed / gib, 2), "lifeGB": round(life / gib, 2),
        "amount": round(billed / gib * per_gb),
        "amountAll": round(life / gib * per_gb),
    }


def _xui_group_banks():
    """
    ترافیکی که x-ui خودش برای هر گروه بانک کرده — بایت.

    ── چرا این وجود دارد ──

    3x-ui وقتی ترافیکِ یک گروه را ریست می‌کند، مقدارِ پیش از ریست را
    در `client_groups.reset_up` و `reset_down` نگه می‌دارد، و
    **منفی** ذخیره‌اش می‌کند. صفحه‌ی گروه‌های خودِ x-ui این را نشان
    می‌دهد:

        نمایش = SUM(up + down)  −  (reset_up + reset_down)

    چون آن دو منفی‌اند، تفریق یعنی جمعِ مصرفِ دوره‌های قبل.

    ── چرا لازم شد ──

    اندازه‌گیری روی دیتابیسِ واقعیِ یک سرور، کنارِ اسکرین‌شاتِ خودِ
    پنلِ x-ui: هر یازده گروه با این فرمول تا کمتر از یک درصد
    می‌خواندند، و بدونش هفت‌تایشان نمی‌خواندند. «Hossein naji»
    ۵۷۸ گیگِ جاری داشت و ۴۶۲ گیگِ بانک‌شده — پنلِ x-ui ۱.۰۱ ترابایت
    می‌گفت و پنلِ ما ۵۷۸ گیگ.

    یعنی تاریخچه‌ای که فکر می‌کردیم x-ui ندارد، دارد — فقط در سطحِ
    گروه، نه کلاینت.
    """
    con, _err = _xui_conn()
    if not con:
        return {}
    out = {}
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(client_groups)")}
        if not {"reset_up", "reset_down"} <= cols:
            return {}
        for r in con.execute(
                "SELECT name, reset_up, reset_down FROM client_groups"):
            # منفی ذخیره می‌شوند، پس منفی‌شان می‌کنیم تا مثبت شود.
            # `max(0, …)` نگهبان است: اگر روزی x-ui علامت را عوض کند،
            # نتیجه نباید از مصرفِ واقعی کم کند.
            bank = -(int(r["reset_up"] or 0) + int(r["reset_down"] or 0))
            out[(r["name"] or "").strip()] = max(0, bank)
    except Exception:
        log.debug("خواندن ترافیک بانک‌شده‌ی گروه ناموفق", exc_info=True)
        return {}
    finally:
        con.close()
    return out


def _read_xui_clients():
    """
    همه‌ی کانفیگ‌ها با گروه و مصرف واقعی.

    نسخه‌ی ۳.۵ ساختار تمیزی دارد:
      clients.group_name  ← نام گروه، مستقیم روی خود کلاینت
      client_groups       ← فهرست گروه‌ها (برای نمایش گروه‌های خالی)
      client_traffics     ← مصرف واقعی

    نسخه‌های قدیمی‌تر گروه ندارند و کلاینت داخل JSON اینباند است؛
    آن حالت هم پشتیبانی می‌شود تا پنل روی هر نسخه‌ای کار کند.
    """
    con, cerr = _xui_conn()
    if not con:
        return None, None, cerr or f"دیتابیس x-ui در {_xui_db_path()} در دسترس نیست"

    try:
        tables = {r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}

        # مصرف واقعی — تنها جایی که عدد درست دارد.
        #
        # **جمع، نه جایگزینی.** `client_traffics` یک ردیف به ازای هر
        # (اینباند، ایمیل) دارد، نه یک ردیف به ازای هر کاربر. کاربری
        # که هم روی XHTTP است و هم روی TCP+Vision — یعنی همان
        # چیدمانی که خودِ این پروژه پیشنهاد می‌دهد — دو ردیف دارد.
        #
        # کدِ قبلی `traffic[email] = dict(r)` می‌نوشت، پس فقط
        # *آخرین* ردیف می‌ماند و بقیه دور ریخته می‌شد.
        #
        # اندازه‌گیری روی دادهٔ واقعیِ یک سرور: گروه‌هایی که
        # کاربرانشان یک اینباند داشتند دقیق می‌خواندند (dastani،
        # Pelleaval، sajjad)، و بقیه به نسبتِ تعدادِ اینباند کم
        # می‌آمدند — «yaser» ۴۳۵ گیگ مصرف داشت و پنل ۱۱۱ نشان
        # می‌داد.
        #
        # روی صورتحساب یعنی همه‌ی مصرف‌ها کمتر از واقعیت.
        traffic = {}
        if "client_traffics" in tables:
            try:
                for r in con.execute(
                    "SELECT email, up, down, expiry_time, enable FROM client_traffics"
                ):
                    em = r["email"]
                    up = int(r["up"] or 0)
                    down = int(r["down"] or 0)
                    exp = int(r["expiry_time"] or 0)
                    cur = traffic.get(em)
                    if cur is None:
                        traffic[em] = {"up": up, "down": down,
                                       "expiry_time": exp,
                                       "enable": bool(r["enable"])}
                    else:
                        cur["up"] += up
                        cur["down"] += down
                        # دورترین انقضا، و «فعال» اگر حتی یکی فعال باشد:
                        # کاربر تا وقتی یک اینباندش باز است وصل می‌شود
                        cur["expiry_time"] = max(cur["expiry_time"], exp)
                        cur["enable"] = cur["enable"] or bool(r["enable"])
            except Exception as e:
                return None, None, f"خواندن client_traffics ناموفق: {str(e)[:110]}"

        # فهرست گروه‌ها — حتی آن‌هایی که هنوز کاربری ندارند
        known_groups = []
        if "client_groups" in tables:
            try:
                known_groups = [r["name"] for r in con.execute(
                    "SELECT name FROM client_groups ORDER BY id")]
            except Exception as e:
                # گروه‌های بی‌کاربر از فهرست می‌افتند؛ بی‌صدا نه
                log.warning("reading x-ui client_groups failed: %s", e)

        rows = []

        # ── نسخه‌ی ۳.۵: جدول مستقل clients ──
        if "clients" in tables:
            cols = {r[1] for r in con.execute("PRAGMA table_info(clients)")}
            sel = ["email", "total_gb", "expiry_time", "enable", "created_at"]
            for extra in ("limit_ip", "sub_id", "tg_id", "updated_at", "reset"):
                if extra in cols:
                    sel.append(extra)
            if "group_name" in cols:
                sel.append("group_name")
            if "comment" in cols:
                sel.append("comment")
            try:
                for r in con.execute(f"SELECT {','.join(sel)} FROM clients"):
                    d = dict(r)
                    rows.append({
                        "email": d.get("email"),
                        "group": (d.get("group_name") or "").strip() or "بدون گروه",
                        "totalGB": int(d.get("total_gb") or 0),
                        "expiry": int(d.get("expiry_time") or 0),
                        "enable": bool(d.get("enable")),
                        "createdAt": d.get("created_at"),
                        "limitIp": int(d.get("limit_ip") or 0),
                        "subId": d.get("sub_id") or "",
                        "tgId": d.get("tg_id") or 0,
                        "updatedAt": d.get("updated_at"),
                        "resetCount": int(d.get("reset") or 0),
                        "comment": d.get("comment") or "",
                    })
            except Exception as e:
                return None, None, f"خواندن clients ناموفق: {str(e)[:110]}"

        # ── نسخه‌ی کلاسیک: کلاینت داخل JSON اینباند ──
        elif "inbounds" in tables:
            try:
                for r in con.execute("SELECT id, remark, settings FROM inbounds"):
                    try:
                        st = json.loads(r["settings"] or "{}")
                    except (json.JSONDecodeError, TypeError):
                        continue
                    for cl in st.get("clients", []):
                        rows.append({
                            "email": cl.get("email"),
                            "group": (r["remark"] or "").strip() or "بدون گروه",
                            "totalGB": int(cl.get("totalGB") or 0),
                            "expiry": int(cl.get("expiryTime") or 0),
                            "enable": bool(cl.get("enable", True)),
                            "createdAt": None,
                            "limitIp": int(cl.get("limitIp") or 0),
                            "comment": "",
                        })
            except Exception as e:
                return None, None, f"خواندن اینباندها ناموفق: {str(e)[:110]}"
        else:
            return None, None, "جدول کلاینت‌ها پیدا نشد — نسخه‌ی x-ui پشتیبانی نمی‌شود"

        # مصرف را می‌چسبانیم
        out = []
        for r in rows:
            em = r.get("email")
            if not em:
                continue
            t = traffic.get(em, {})
            r["used"] = int((t.get("up") or 0) + (t.get("down") or 0))
            # مصرفِ جمع‌شده‌ی همه‌ی دوره‌ها. این‌جا فقط پایه‌اش گذاشته
            # می‌شود (برابرِ دوره‌ی جاری)؛ `_attach_total_usage` مقدارِ
            # دوره‌های ریست‌شده را رویش می‌گذارد.
            #
            # چرا همیشه ست می‌شود: تا هیچ صداکننده‌ای مجبور نباشد
            # `.get()` بنویسد و هیچ‌کدام بی‌صدا به `used` برنگردند.
            r["usedTotal"] = r["used"]
            if not r.get("expiry"):
                r["expiry"] = int(t.get("expiry_time") or 0)
            out.append(r)

        return out, known_groups, None
    finally:
        con.close()


# ═══════════════════════════════════════════════════════════
#  محاسبات حسابداری
#
#  هر عددی که اینجا حساب می‌شود روی فاکتور واسطه می‌رود، پس
#  گرد کردن و حالت‌های لبه باید صریح و قابل توضیح باشند.
# ═══════════════════════════════════════════════════════════

TEHRAN_OFFSET = 3.5 * 3600      # UTC+3:30


def _tehran_today():
    """
    Today's date in Tehran, the same clock `_to_jalali` puts config dates on.
    The billing pages compared Tehran-dated configs with the server's own
    `date.today()`; on a UTC server, between 20:30 and midnight UTC a config
    made that evening was already "tomorrow" and fell out of the current
    period (found by CI running at 21:19 UTC, 2026-10-01).
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    return (_dt.now(_tz.utc) + _td(seconds=TEHRAN_OFFSET)).date()


def _epoch_ms(v):
    """
    هر شکلی از تاریخ را به میلی‌ثانیه‌ی epoch تبدیل می‌کند، یا None.

    لازم است چون x-ui در نسخه‌های مختلف created_at را جور دیگری
    نگه می‌دارد: گاهی عدد ثانیه، گاهی عدد میلی‌ثانیه، و گاهی متنِ
    «۲۰۲۴-۰۳-۱۱ ۰۹:۲۲:۰۰». هر کد که فرض کند فقط یکی از این‌هاست،
    روی نصف نصب‌ها می‌شکند.
    """
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        if f <= 0:
            return None
        # زیر ۱e11 یعنی ثانیه است، نه میلی‌ثانیه
        return f * (1000 if f < 1e11 else 1)
    try:
        txt = str(v).strip().replace("Z", "+00:00")
        if txt.isdigit():
            return _epoch_ms(int(txt))
        from datetime import datetime as _dt
        return _dt.fromisoformat(txt[:19]).timestamp() * 1000
    except (ValueError, TypeError):
        return None


def _months_from_days(days):
    """
    تعداد ماه‌های صورتحساب از تعداد روز. نیم‌ماه به بالا.

    چرا round() ساده کافی نبود:

        round(9.5)  == 10
        round(10.5) == 10      ← همین
        round(11.5) == 12

    پایتون «گرد کردن بانکی» می‌کند و نیم را به نزدیک‌ترین عدد زوج
    می‌برد. یعنی دو کانفیگ که هر دو دقیقاً نیم‌ماه اضافه دارند،
    بسته به اینکه عدد ماهشان زوج است یا فرد، دو جور حساب می‌شوند.
    برای صورتحساب این قابل دفاع نیست.

    اپسیلون هم لازم است: مرزِ دقیق نیم‌ماه با اختلاف کسری از ثانیه
    این‌ور و آن‌ور می‌شود (۲۸۵ روز = دقیقاً ۹.۵ ماه)، و بدون آن یک
    ثانیه فرقِ بی‌اهمیت در تاریخ ساخت، یک ماه کم یا زیاد می‌کرد.
    """
    import math
    if days is None:
        return 1
    try:
        return max(1, int(math.floor(float(days) / 30.0 + 0.5 + 1e-6)))
    except (TypeError, ValueError):
        return 1


def _date_ms(d):
    """
    نیمه‌شبِ یک تاریخ به میلی‌ثانیه — بدون وابستگی به منطقه‌ی زمانی ماشین.

    جایگزین strftime("%s") که افزونه‌ی glibc است: روی ویندوز و
    هر libc دیگری ValueError می‌دهد و تست‌ها هم آن را نمی‌گرفتند،
    چون تا پیش از این هیچ‌وقت به آن خط نمی‌رسیدیم.
    """
    from datetime import datetime as _dt, timezone as _tz
    return int(_dt(d.year, d.month, d.day, tzinfo=_tz.utc).timestamp() * 1000)


#: رقمِ لاتین ← فارسی (برای پیام). نامش عمداً با `_FA_DIGITS` (فارسی ← لاتین)
#  فرق دارد: تا ۱.۱۲۸ هر دو `_FA_DIGITS` بودند و چون این یکی پایین‌تر تعریف
#  می‌شد، «فارسی ← لاتین»ِ `_iso_day` در عمل برعکس کار می‌کرد — فقط چون
#  `int()`ِ پایتون رقمِ فارسی را هم می‌خواند، دیده نشد. test-seams حالا
#  هر نامِ سطح‌ماژولیِ تکراری در app.py را رد می‌کند.
_TO_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fnum(n):
    """
    عدد برای پیامِ فارسی که رابط نشان می‌دهد — همان شکلِ `faNum`ِ رابط.

    پیام‌های خطا و گزارش با f-stringِ خام رقمِ لاتین وسطِ جمله‌ی فارسی
    می‌گذاشتند («2 بخشِ تازه‌تر»، «لازم 280,000 تومان»). عمداً فقط برای
    *شمار و مبلغ* است: مسیر، آی‌پی، پورت و نسخه باید لاتین بمانند، پس
    تبدیلِ کلِ پیام در رابط غلط بود. PDF قاعده‌ی خودش را دارد.
    """
    try:
        s = f"{int(n):,}".replace(",", "٬")
    except (TypeError, ValueError):
        return str(n)
    return s.translate(_TO_FA_DIGITS)


def _to_jalali(epoch_ms):
    """
    تاریخ به شمسی، به وقت تهران.

    ورودی می‌تواند عدد یا متن باشد — قبلاً فقط عدد را می‌پذیرفت و
    با متن TypeError می‌داد. صفحه‌ی «صورتحساب دوره» دقیقاً همین
    مقدار را خام می‌فرستاد، پس روی هر x-ui که created_at را متنی
    ذخیره می‌کند، آن صفحه با خطای ۵۰۰ می‌افتاد.

    برمی‌گرداند: (شمسی, میلادی) یا (None, None) اگر مقدار معنادار نباشد.
    """
    epoch_ms = _epoch_ms(epoch_ms)
    if not epoch_ms or epoch_ms <= 0:
        return None, None
    try:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        d = _dt.fromtimestamp(epoch_ms / 1000, _tz.utc) + _td(seconds=TEHRAN_OFFSET)
        try:
            import jdatetime
            j = jdatetime.date.fromgregorian(date=d.date())
            return f"{j.year:04d}/{j.month:02d}/{j.day:02d}", d.strftime("%Y-%m-%d")
        except ImportError:
            return None, d.strftime("%Y-%m-%d")
    except Exception:
        return None, None


def _duration_days(created, expiry):
    """
    مدت اشتراک به روز.

    اگر یکی از دو تاریخ نباشد، None برمی‌گردد — نه صفر، چون صفر
    یعنی «مدت صفر» و این با «نمی‌دانیم» فرق دارد.

    هر دو ورودی از _epoch_ms رد می‌شوند: created در x-ui معمولاً متن
    است و float("2024-09-12 10:00:00") خطا می‌داد، پس این تابع برای
    *همه‌ی* کلاینت‌ها None برمی‌گرداند و ستون «مدت» در صورتحساب
    گروه همیشه خالی بود.
    """
    c0 = _epoch_ms(created)
    e0 = _epoch_ms(expiry)
    if not c0 or not e0:
        return None
    days = (e0 - c0) / 86400000.0
    return round(days, 1) if days > 0 else None


def _usage_percent(used_bytes, quota_raw):
    """
    درصد مصرف. برای پلن نامحدود None برمی‌گردد چون درصدی از
    بی‌نهایت معنا ندارد.

    `quota_raw` همان چیزی است که x-ui می‌دهد — و x-ui گاهی بایت
    می‌دهد و گاهی خودِ عددِ گیگ. پس از `_gb_of` رد می‌شود، همان
    هسته‌ای که بقیه‌ی حسابداری هم از آن می‌گذرد.

    چرا این‌جا و نه در صداکننده‌ها: هر چهار صداکننده مقدارِ خامِ
    x-ui را می‌دادند انگار بایت است. روی نصبی که `total_gb` عددِ
    گیگ نگه می‌دارد، نتیجه‌اش این بود:

        used=450GB، quota=500  →  ۹۶٬۶۳۶٬۷۶۴٬۱۶۰٪

    و در مینی‌اپ، `gb` و `usagePct` دو خط فاصله داشتند و همان یک
    مقدار در یکی از `_gb_of` رد می‌شد و در دیگری نه.
    """
    gb = _gb_of(quota_raw)
    if gb <= 0:
        return None
    return round(used_bytes * 100.0 / (gb * (1024 ** 3)))


def _start_ms(cl, since=None, first_seen=None):
    """
    مبدأ زمانی یک کانفیگ، و اینکه از کجا آمده.

    شمارش ماه و تاریخ‌گذاری تمدیدها باید از *یک* مبدأ حساب کنند.
    وقتی هر کدام مبدأ خودش را داشت، صورتحساب کلی و صورتحساب دوره‌ای
    دو عدد متفاوت می‌دادند و معلوم نبود کدام درست است.

    برمی‌گرداند: (میلی‌ثانیه یا None, نام منبع)
    """
    ms = _epoch_ms(cl.get("createdAt"))
    if ms is not None:
        return ms, "ساخت"
    ms = _epoch_ms(since)
    if ms is not None:
        return ms, "شروع گروه"
    ms = _epoch_ms(first_seen)
    if ms is not None:
        return ms, "اولین‌دید"
    return None, "پیش‌فرض"


def _renewal_dates(cl, logged_rows, months=None, since=None, first_seen=None):
    """
    تاریخِ هر تمدید — دقیقاً به تعدادی که _months_for شمرده است.

    دو منبع داریم و هیچ‌کدام تنهایی کافی نیست:

      ثبت‌شده  تمدیدهایی که خودِ نکسورا دیده. تاریخ واقعی دارند،
               ولی فقط از روزی که نصب شده به بعد.
      تخمینی   بقیه — از فاصله‌ی ساخت تا انقضا. فرض این است که هر
               تمدید سر ماه انجام شده: ایجاد + ۳۰ روز، + ۶۰ روز، …

    چرا شمارش دیگر این‌جا انجام نمی‌شود:
        این تابع اگر حتی *یک* تمدیدِ ثبت‌شده می‌دید، بقیه را دور
        می‌ریخت و فقط همان را برمی‌گرداند. کانفیگی با دو سال سابقه و
        یک تمدید ثبت‌شده، در صورتحساب کلی ۲۵ ماه بود و در صورتحساب
        دوره‌ای یک تمدید — دو عدد از یک واقعیت.

        حالا تعداد از _months_for می‌آید و این‌جا فقط *تاریخ* گذاشته
        می‌شود. ماه‌هایی که ردی از آن‌ها نداریم مالِ گذشته‌اند: ثبت از
        روز نصب شروع شده، پس ثبت‌شده‌ها تازه‌ترین‌ها هستند و تخمین‌ها
        جای ماه‌های اول را می‌گیرند.

    و چرا هر ردیفِ ثبت‌شده به اندازه‌ی months خودش باز می‌شود:
        تمدید سه‌ماهه سه ماه صورتحساب است، نه یکی. قبلاً هر ردیف یک
        تمدید حساب می‌شد.
    """
    email = cl.get("email")
    real = []
    for r in (logged_rows or []):
        if r.get("email") != email:
            continue
        d = (r.get("created_at") or "")[:10]
        if not d:
            continue
        try:
            n = max(1, int(r.get("months") or 1))
        except (TypeError, ValueError):
            n = 1
        real.extend([(d, "قطعی")] * n)
    real.sort()

    # created ممکن است متن باشد. قبلاً float(created) بود و با متن
    # ValueError می‌داد، پس این تابع خالی برمی‌گشت — یعنی کانفیگی که
    # دو سال تمدید شده، در صورتحساب *صفر* تمدید داشت و تقریباً کل
    # مبلغ از قلم می‌افتاد.
    c0, _src = _start_ms(cl, since, first_seen)
    e0 = _epoch_ms(cl.get("expiry") or 0)

    if months is None:
        if c0 is None or not e0 or e0 <= 0:
            return real
        months = max(1 + len(real),
                     _months_from_days((e0 - c0) / 86400000.0))

    need = max(0, int(months) - 1)
    if len(real) >= need:
        return real[len(real) - need:]
    if c0 is None:
        return real

    out = []
    for i in range(1, need - len(real) + 1):
        _j, g = _to_jalali(int(c0 + i * 30 * 86400000))
        if g:
            out.append((g, "تخمینی"))
    return out + real


def _rows_by_email(logged_rows):
    """
    ردیف‌های تمدید، گروه‌شده بر اساس ایمیل.

    بدون این، هر کلاینت کل جدول تمدیدها را می‌پیمود — روی ۲۵۷ کانفیگ
    یعنی ۲۵۷ پیمایش کامل، در تابعی که هر بار باز کردن صفحه صدا زده
    می‌شود.
    """
    out = {}
    for r in (logged_rows or []):
        out.setdefault(r.get("email"), []).append(r)
    return out


def _period_share(cl, logged, rows, since, group_start=None, first_seen=None):
    """
    از عمر این کانفیگ، چند ماهش روی صورتحسابِ *این دوره* می‌آید.

    برمی‌گرداند:
        (ماهِ این دوره, ماهِ کل, تمدیدِ این دوره, در دوره ساخته شده؟,
         منبع, انحراف)

    چرا یک تابع مشترک:
        صورتحساب و نمای کلی هر کدام جدا حساب می‌کردند. وقتی صورتحساب
        «تسویه‌شده تا» را رعایت کرد و نمای کلی نکرد، داشبورد زیر تیتر
        «کل بدهی دوره» عدد کلِ عمر را نشان می‌داد و فاکتور عدد دوره را
        — دو رقم برای یک واقعیت، و آن‌که برچسبِ «دوره» داشت غلط بود.

        هر جای تازه‌ای هم که بدهی حساب می‌کند باید از همین‌جا بگیرد.
    """
    months, kind, drift = _months_for(cl, logged, since=group_start,
                                      first_seen=first_seen)
    if not since:
        return months, months, months - 1, True, kind, drift

    today = datetime.now().strftime("%Y-%m-%d")
    _cj, created_g = _to_jalali(cl.get("createdAt"))
    base_g = created_g or (first_seen or "")[:10]
    is_new = bool(base_g) and since <= base_g <= today

    dates = _renewal_dates(cl, rows, months,
                           since=group_start, first_seen=first_seen)

    # هر ماه یک‌بار، در همان دوره‌ای که **سپری شده**.
    #
    # شرط قبلاً فقط `d >= since` بود، بدون سقف. `_renewal_dates` برای
    # کانفیگی که تا ۱۴۰۶ اعتبار دارد، مرزهای ماهانه را تا همان‌جا جلو
    # می‌برد — و آن تاریخ‌ها همیشه از «تسویه‌شده تا» جلوترند. پس هر
    # دوره دوباره شمرده می‌شدند.
    #
    # اندازه‌گیری‌شده روی یک گروه واقعی: ۵۸ ماه در دوره‌ی اول، ۴۱ ماه
    # در دوره‌ی دوم که **هر ۴۱ تایش قبلاً هم شمرده شده بود**، و ۳۰ ماه
    # که در هر سه دوره آمدند. مالک بر اساس همین فاکتورها دو بار پول
    # گرفت.
    #
    # چرا «سپری‌شده» و نه «فروخته‌شده»:
    #     مدل «کلِ دوره را موقع فروش حساب کن» هم درست است، ولی برای
    #     تکرارنشدن باید به خاطر بسپارد کدام ماه‌های آینده قبلاً روی
    #     فاکتور رفته‌اند — و «تسویه‌شده تا» که یک تاریخ است نمی‌تواند
    #     این را نگه دارد. با شمردنِ ماهِ سپری‌شده، جمعِ کلِ عمرِ
    #     کانفیگ همان عدد است، فقط درست پخش می‌شود و هیچ ماهی دو بار
    #     نمی‌آید.
    ren_in = sum(1 for d, _k in dates if since <= d <= today)
    return (1 if is_new else 0) + ren_in, months, ren_in, is_new, kind, drift


def _period_bounds(conf, ref=None):
    """
    ابتدا و انتهای دوره‌ی جاری یک واسطه.

    دوره از تاریخ شروعی که مدیر تعیین کرده جلو می‌رود، به طول
    period_days. اگر شروعی تعریف نشده باشد، از اول ماه میلادی
    جاری حساب می‌شود.
    """
    from datetime import date, timedelta

    today = ref or _tehran_today()
    length = max(1, int(conf.get("period_days") or 30))

    start_str = (conf.get("period_start") or "").strip()
    if start_str:
        try:
            anchor = date.fromisoformat(start_str[:10])
        except ValueError:
            anchor = None
    else:
        anchor = None

    if anchor is None:
        # بدون لنگر، دوره باید شامل امروز باشد و به عقب برسد —
        # نه از اول ماه میلادی. وگرنه در روزهای اول ماه، کانفیگ‌های
        # چند روز پیش بیرون می‌مانند و صورتحساب خالی درمی‌آید.
        anchor = today - timedelta(days=length - 1)

    if anchor > today:
        return anchor, anchor + timedelta(days=length)

    # چند دوره از لنگر گذشته؟
    elapsed = (today - anchor).days
    n = elapsed // length
    start = anchor + timedelta(days=n * length)
    return start, start + timedelta(days=length)


def _months_for(cl, logged, since=None, first_seen=None):
    """
    یک کانفیگ چند ماه صورت‌حساب دارد، و این عدد از کجا آمده.

    برمی‌گرداند: (تعداد ماه, منبع, خطای تخمین به روز)

    منبع‌ها به ترتیب اعتبار:

      ثبت‌شده   تمدیدهایی که خودِ نکسورا ثبت کرده — قطعی
      ساخت      تاریخ ساخت کلاینت در x-ui — قطعی، ولی نسخه‌های
                قدیمی این ستون را ندارند
      شروع گروه مدیر تاریخ شروع همکاری با واسطه را گفته
      اولین‌دید  پنل از این تاریخ کلاینت را می‌شناسد — کف مطمئن،
                نه تاریخ واقعی شروع
      پیش‌فرض   هیچ‌کدام نبود؛ یک ماه

    چرا منبع برمی‌گردد: قبلاً همه‌ی این حالت‌ها یک عدد خشک می‌دادند و
    مدیر نمی‌فهمید چرا واسطه‌ای که دو سال کار کرده «یک ماه» صورت‌حساب
    گرفته. حالا پنل می‌تواند دقیقاً بگوید عدد از کجا آمده و چه چیزی
    لازم است تا درست شود.
    """
    from datetime import datetime as _dt

    # تمدیدهای ثبت‌شده یک *کف* هستند، نه جایگزین تخمین.
    #
    # قبلاً همین‌جا return می‌شد. ولی ثبت از روزی شروع می‌شود که
    # نکسورا نصب شده؛ کانفیگی که دو سال سابقه دارد و یک تمدیدِ
    # ثبت‌شده، «۲ ماه» می‌شد به‌جای ۲۵ ماه — یعنی ثبت‌کردن تمدیدها
    # صورتحساب را *بدتر* می‌کرد.
    #
    # پایین هر دو حساب می‌شوند و بزرگ‌ترشان برمی‌گردد.
    floor = 1 + logged.get(cl["email"], 0) if cl["email"] in logged else 0

    exp = cl.get("expiry")

    _ms = _epoch_ms

    created, source = _start_ms(cl, since, first_seen)

    if not exp or exp <= 0 or created is None:
        return (floor, "ثبت‌شده", 0) if floor > 1 else (1, "پیش‌فرض", 0)

    exp_ms = _ms(exp)
    if exp_ms is None:
        return (floor, "ثبت‌شده", 0) if floor > 1 else (1, "پیش‌فرض", 0)

    days = (exp_ms - created) / 86400000.0
    if days <= 0:
        # منقضی شده: از شروع تا امروز حساب می‌کنیم، نه تا انقضا —
        # وگرنه کانفیگی که سه سال کار کرده و دیروز تمام شده،
        # «یک ماه» حساب می‌شد.
        days = (_dt.now().timestamp() * 1000 - created) / 86400000.0
        if days <= 0:
            return (floor, "ثبت‌شده", 0) if floor > 1 else (1, "منقضی", 0)
        months = _months_from_days(days)
        if floor > months:
            return floor, "ثبت‌شده", 0
        return months, source + " (منقضی)", 0

    months = _months_from_days(days)

    # تمدیدی که دیده‌ایم از تخمین بیشتر است — یعنی انقضا یک جایی عقب
    # کشیده شده (تمدید با «تاریخ تازه» به‌جای «افزودن روز»). آن‌وقت
    # فاصله‌ی ساخت تا انقضا کوتاه‌تر از واقعیت است و تخمین کم می‌آورد.
    if floor > months:
        return floor, "ثبت‌شده", 0

    drift = abs(days - months * 30)
    if source == "ساخت" and drift <= 2:
        return months, "قطعی", 0
    return months, source, round(drift)


def _bill_since(conf, explicit=""):
    """
    صورتحساب از چه تاریخی به بعد حساب شود، و چرا.

    ترتیب:
      ۱. تاریخی که مدیر همین حالا انتخاب کرده
      ۲. «تسویه‌شده تا» — هرچه پیش از آن بوده، پولش گرفته شده
      ۳. «شروع همکاری» — پیش از آن اصلاً همکاری‌ای نبوده
      ۴. هیچ‌کدام — از ابتدای عمر هر کانفیگ

    چرا لازم شد:
        صورتحساب *همه‌ی* عمر هر کانفیگ را حساب می‌کرد و هیچ تاریخی
        را نمی‌دید. واسطه‌ای که ماه پیش تسویه کرده بود، این ماه
        دوباره همان تمدیدها را روی فاکتورش می‌دید.

        «تسویه‌شده تا» از قبل در پایگاه داده بود و صفحه‌ی دوره‌ای هم
        رعایتش می‌کرد — ولی صورتحساب و PDF، یعنی همان چیزی که دست
        واسطه می‌رسد، اصلاً نگاهش نمی‌کردند.

    برمی‌گرداند: (YYYY-MM-DD یا "", برچسب منبع)
    """
    from datetime import date as _date

    def ok(v):
        v = (v or "").strip()[:10]
        if not v:
            return ""
        try:
            _date.fromisoformat(v)
        except ValueError:
            return ""
        return v

    # تاریخِ خرابی که از قبل ذخیره شده، بی‌صدا رد نمی‌شود: اگر «تسویه‌شده
    # تا» نامعتبر است و به پله‌ی بعد می‌رسیم، برچسبِ منبع همین را می‌گوید —
    # سربرگِ صورتحساب آن را نشان می‌دهد، پس مدیر می‌بیند چرا ماه‌های
    # تسویه‌شده دوباره آمده‌اند.
    bad = []
    for value, why in ((explicit, "تاریخ انتخابی"),
                       ((conf or {}).get("settled_until"), "تسویه‌شده تا"),
                       ((conf or {}).get("period_start"), "شروع همکاری")):
        v = ok(value)
        if v:
            if bad:
                why = f"{why} — «{'، '.join(bad)}» نامعتبر بود"
            return v, why
        if (value or "").strip():
            bad.append(why)
    if bad:
        return "", f"«{'، '.join(bad)}» نامعتبر بود"
    return "", ""


def _price_per_gb(conf):
    """
    نرخ حجمی — وقتی با واسطه به‌جای پلن، روی هر گیگابایت توافق شده.

    برمی‌گرداند: عدد تومان بر گیگابایت، یا None اگر تعریف نشده.
    """
    try:
        v = int(conf.get("per_gb") or 0)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _volume_mixed(conf):
    """
    A volume group (per-GB price) that also prices truly unlimited configs:
    its rates carry a gb=0 row with a price. docs/specs/2026-09-30-vpn-fixes.md,
    task 5. The owner: volume configs by usage, unlimited ones at a rate.

    Without such a row a volume group stays exactly what it was: every config,
    unlimited or not, billed by usage.
    """
    if not _price_per_gb(conf or {}):
        return False
    try:
        rates = json.loads((conf or {}).get("rates") or "[]")
    except (json.JSONDecodeError, TypeError):
        return False
    for r in rates if isinstance(rates, list) else []:
        try:
            if int(r.get("gb", -1)) == 0 and int(r.get("price", 0)) > 0:
                return True
        except (TypeError, ValueError, AttributeError):
            continue
    return False


def _by_usage(conf, cl, mixed=None):
    """
    Is this config billed by its usage? The one rule every billing surface
    reads (dashboard, invoice, period page, settlement, portal): in a volume
    group, yes, except a config with no volume cap when the group prices
    unlimited configs (`_volume_mixed`). Those are billed like any rated
    config: the rate times the months of the period.
    """
    if not _price_per_gb(conf or {}):
        return False
    if mixed is None:
        mixed = _volume_mixed(conf)
    return not (mixed and int(cl.get("totalGB") or 0) == 0)


def _price_for(gb, rates):
    """
    قیمت یک کانفیگ. نرخ نامحدود با gb=0 مشخص می‌شود.

    ترتیب انتخاب:
      ۱. نرخ دقیقاً همان حجم
      ۲. نزدیک‌ترین نرخ بالاتر
      ۳. بالاترین نرخ تعریف‌شده — وقتی حجم کانفیگ از همه‌ی نرخ‌ها
         بزرگ‌تر است

    مرحله‌ی سوم قبلاً نبود: اگر واسطه‌ای نرخ ۳۰ و ۵۰ و ۱۰۰ گیگ تعریف
    کرده بود و مشتری کانفیگ ۲۰۰ گیگی داشت، هیچ نرخی پیدا نمی‌شد و آن
    ردیف *صفر* حساب می‌شد — با اینکه نرخ تعریف شده بود. صفر گرفتن از
    یک کانفیگ واقعی بدتر از تقریب زدن است.

    نرخی که مدیر تعریف کرده باید استفاده شود — حتی اگر دقیقاً روی این
    کانفیگ ننشیند.

    قبلاً این‌طور نبود و دو حالت بی‌صدا صفر می‌شدند:

      • گروهی که فقط نرخ نامحدود داشت، ولی کانفیگ‌هایش حجم داشتند.
        روی سرور واقعی این یعنی ۱۰۰ کانفیگ از ۲۵۷ تا هیچ قیمتی
        نمی‌گرفتند — گروهی به اسم «unlimited» با یک نرخ ۱۹۰٬۰۰۰ و
        ۸۸ کانفیگِ ۲۰۰ گیگی داخلش.

      • گروهی که فقط نرخ حجمی داشت، ولی کانفیگی نامحدود در آن بود.

    وقتی مدیر برای یک گروه نرخ گذاشته، منظورش این است که این گروه
    قیمت دارد. «چون دقیقاً جور در نمی‌آید پس صفر» جوابِ غلطی است به
    سوالی که اصلاً پرسیده نشده بود.
    """
    price, _ = _price_with_reason(gb, rates)
    return price


def _device_rate(gb, rates):
    """
    نرخ هر کاربرِ اضافه برای همین حجم — یا صفر اگر تعریف نشده.

    از همان ردیفی خوانده می‌شود که قیمت پایه از آن آمده، پس هر پله
    می‌تواند نرخ کاربر خودش را داشته باشد.
    """
    chosen = _match_rate(gb, rates)
    if not chosen:
        return 0
    try:
        return max(0, int(chosen.get("perDevice", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _line_amount(gb, rates, months, limit_ip):
    """
    مبلغ یک ردیف فاکتور: (نرخ پایه + کاربرهای اضافه) × ماه.

    کانفیگ چهارکاربره همان نرخ کانفیگ تک‌کاربره را می‌گرفت، در حالی
    که سه کاربر بیشتر روی سرور می‌نشیند. حالا هر ردیف نرخ، نرخ کاربر
    خودش را دارد.

    «کاربرِ اضافه» یعنی از دومی به بعد — نرخ پایه شامل کاربر اول است،
    پس کانفیگ تک‌کاربره و فاکتورهای قبلی دست‌نخورده می‌مانند.

    محدودیت نامحدود (صفر) قابل شمردن نیست، پس فقط نرخ پایه می‌گیرد و
    ردیف علامت می‌خورد تا در فهرست «نیاز به بررسی» دیده شود.

    برمی‌گرداند: (مبلغ, نرخ پایه, نرخ هر کاربر, تعداد کاربر اضافه)
    """
    base, _why = _price_with_reason(gb, rates)
    if base is None:
        return 0, None, 0, 0
    per = _device_rate(gb, rates)
    try:
        ips = int(limit_ip or 0)
    except (TypeError, ValueError):
        ips = 0
    extra = max(0, ips - 1) if ips > 0 else 0
    return (base + per * extra) * months, base, per, extra


def _match_rate(gb, rates):
    """همان ردیفی که _price_with_reason قیمتش را برمی‌دارد."""
    valid = []
    for r in rates or []:
        try:
            valid.append((int(r.get("gb", -1)), r))
        except (TypeError, ValueError, AttributeError):
            continue
    if not valid:
        return None
    for g, r in valid:
        if g == gb:
            return r
    if gb > 0:
        higher = sorted((v for v in valid if v[0] > gb), key=lambda v: v[0])
        if higher:
            return higher[0][1]
        vol = [v for v in valid if v[0] > 0]
        if vol:
            return max(vol, key=lambda v: v[0])[1]
        flat = [v for v in valid if v[0] == 0]
        if flat:
            return flat[0][1]
        return None
    vol = [v for v in valid if v[0] > 0]
    return max(vol, key=lambda v: v[0])[1] if vol else None


def _price_with_reason(gb, rates):
    """
    قیمت، به‌همراه دلیلِ نبودنش. برمی‌گرداند: (قیمت یا None, دلیل یا None)

    چرا دلیل لازم است: «بدون نرخ» پنج علت مختلف دارد و هیچ‌کدامشان
    از خودِ عبارت پیدا نیست. مدیری که نرخ تعریف کرده و باز هم «بدون
    نرخ» می‌بیند، هیچ راهی ندارد بفهمد کدام‌یک است — و همین چند بار
    به‌عنوان «حسابداری کار نمی‌کند» برگشته.
    """
    if not rates:
        return None, "برای این گروه هیچ نرخی تعریف نشده"

    valid, broken = [], 0
    for r in rates:
        try:
            valid.append((int(r.get("gb", -1)), int(r.get("price", 0))))
        except (TypeError, ValueError):
            broken += 1
            continue
    if not valid:
        return None, "نرخ‌های این گروه خوانده نشدند — دوباره ثبتشان کنید"

    for g, price in valid:
        if g == gb:
            return price, None

    if gb > 0:
        higher = sorted((v for v in valid if v[0] > gb), key=lambda v: v[0])
        if higher:
            return higher[0][1], None
        # از همه‌ی نرخ‌ها بزرگ‌تر است — بالاترین نرخ حجمی را می‌گیرد
        volume_rates = [v for v in valid if v[0] > 0]
        if volume_rates:
            return max(volume_rates, key=lambda v: v[0])[1], None
        # هیچ نرخ حجمی نیست، ولی نرخ نامحدود هست: همان تنها نرخِ
        # گروه است، پس نرخِ ثابتِ گروه حساب می‌شود.
        flat = [v for v in valid if v[0] == 0]
        if flat:
            return flat[0][1], None
        return None, (f"این کانفیگ {gb} گیگ است و هیچ نرخی برای این "
                      "گروه جور در نمی‌آید")

    # gb == 0 یعنی نامحدود. نرخ نامحدود در حلقه‌ی تطابق دقیق بالا
    # گرفته می‌شد؛ اگر به این‌جا رسیدیم یعنی فقط نرخ حجمی هست.
    #
    # گران‌ترین پله را می‌گیرد: نامحدود دست‌کم به اندازه‌ی بزرگ‌ترین
    # حجمی است که برایش نرخ گذاشته‌اید — همان قاعده‌ای که برای کانفیگِ
    # بزرگ‌تر از همه‌ی پله‌ها هم به کار می‌رود.
    vol = [v for v in valid if v[0] > 0]
    if vol:
        return max(vol, key=lambda v: v[0])[1], None

    return None, "برای این گروه هیچ نرخ قابل‌استفاده‌ای نیست"



def _gb_of(total):
    """
    حجمِ کانفیگ به گیگابایت.

    ۳x-ui گاهی بایت می‌دهد و گاهی خودِ عدد گیگ — پس شرطِ «بزرگ‌تر از
    ۱۰۲۴» تصمیم می‌گیرد کدام است. صفر یعنی نامحدود.

    این یک خط تا امروز شش بار درون‌خطی تکرار شده بود و یک‌بار هم در
    `scripts/billing-why.py`. هفت کپی از یک قاعده‌ی پول، که هر کدامشان
    جای تازه‌ای برای جدا افتادن بود.
    """
    try:
        total = int(total or 0)
    except (TypeError, ValueError):
        return 0
    return total // (1024 ** 3) if total > 1024 else total


def _attach_total_usage(bcon, clients):
    """
    مصرفِ دوره‌های ریست‌شده را روی کلاینت‌ها می‌گذارد.

    x-ui با ریستِ ترافیک عدد را صفر می‌کند و تاریخچه‌ای ندارد، پس
    `client_seen.used_before` تنها جایی است که آن مصرف باقی مانده.

    **این تنها راهِ رسیدن به مصرفِ واقعی است.** نسخه‌ی قبل این جمع را
    فقط در `billing_clients` حساب می‌کرد و بقیه‌ی صفحه‌های حسابداری —
    از جمله بدهیِ نرخِ حجمی — همان عددِ پس‌از‌ریست را برمی‌داشتند.
    یعنی همان «یک قاعده، دو جا، اصلاح در یکی».
    """
    if not clients:
        return
    before = {}
    try:
        before = {r["email"]: int(r["used_before"] or 0) for r in bcon.execute(
            "SELECT email, used_before FROM client_seen")}
    except Exception:
        # ستون هنوز ساخته نشده (نصبِ تازه، پیش از اولین ثبت).
        # این‌جا *برنمی‌گردیم*: قرارِ این تابع این است که بعد از
        # اجرایش هر کلاینت `usedTotal` داشته باشد. برگشتنِ زودهنگام
        # یعنی صداکننده روی کلیدِ نبوده KeyError می‌گیرد — و آن،
        # یک صفحه‌ی خالی است به‌جای یک عددِ بدونِ جمع.
        log.debug("خواندن مصرف پیشین ناموفق", exc_info=True)
    for cl in clients:
        cl["usedTotal"] = int(cl.get("used") or 0) + before.get(cl.get("email"), 0)


def _with_total_usage(clients):
    """
    `_attach_total_usage`، ولی خودش اتصالِ حسابداری را باز و بسته
    می‌کند.

    برای مسیرهایی که اتصالِ باز ندارند (پنلِ نماینده). شکستِ باز‌کردن
    بی‌صداست: `usedTotal` از پیش برابرِ `used` است، پس بدترین حالت
    همان رفتارِ قبلی است، نه کرش.
    """
    if not clients:
        return clients
    try:
        bcon = _billing_conn()
    except Exception:
        log.debug("اتصال حسابداری برای جمعِ مصرف باز نشد", exc_info=True)
        return clients
    try:
        _attach_total_usage(bcon, clients)
    finally:
        bcon.close()
    return clients


def _billable_config(cl):
    """
    آیا این کانفیگ باید نرخ بگیرد؟ برمی‌گرداند: (بله/خیر, دلیل)

    قاعده‌ای که مالک خواست: فقط کانفیگ‌های در استفاده حساب شوند — ولی
    «منقضی شد» نباید راه فرار از پرداخت باشد.

    این دو با هم می‌خوانند، چون منقضی‌شدن یعنی کانفیگ *دوره‌اش را کار
    کرده*. مشتری آن ماه را استفاده کرده و واسطه باید بابتش بدهد. آنچه
    نباید حساب شود، کانفیگی است که ساخته شده و اصلاً به کار نیفتاده:
    غیرفعال، بدون یک بایت ترافیک.

    ۳x-ui کانفیگ منقضی را خودش غیرفعال می‌کند، پس اگر فقط به enable
    نگاه می‌کردیم، هر کانفیگی با تمام‌شدن دوره‌اش از صورت‌حساب بیرون
    می‌افتاد — دقیقاً همان چیزی که مالک هشدار داد.
    """
    # جمعِ همه‌ی دوره‌ها، نه دوره‌ی جاری.
    #
    # وگرنه کانفیگی که مصرف داشته و بعد ریست خورده، «ساخته شده ولی
    # هرگز به کار نیفتاده» شمرده می‌شد و کاملاً از صورتحساب بیرون
    # می‌افتاد. یعنی ریست‌زدن راهِ نپرداختن می‌شد — و ریست دستِ خودِ
    # نماینده است.
    used = int(cl.get("usedTotal") or cl.get("used") or 0)
    enabled = bool(cl.get("enable"))

    if enabled:
        return True, "فعال"
    if used > 0:
        return True, "غیرفعال ولی مصرف داشته"

    exp = cl.get("expiry")
    try:
        expired = bool(exp) and int(exp) > 0 and int(exp) < _now_ms()
    except (TypeError, ValueError):
        expired = False
    if expired:
        return True, "دوره‌اش تمام شده — کار کرده و باید حساب شود"

    return False, "ساخته شده ولی هرگز به کار نیفتاده"


def _now_ms():
    return int(datetime.now().timestamp() * 1000)


def _bot_money_in():
    """
    پولی که از راه ربات واقعاً به دست مالک رسیده.

    دو تله این‌جا هست و هر دو در جهت *بیشتر نشان‌دادن* خطا می‌کنند:

      • سفارشی که از کیف پول پرداخت شده پول تازه نیست. همان پول
        یک‌بار موقع شارژ کیف رسیده و یک‌بار موقع خرید شمرده می‌شود.
        مشتری‌ای که ۵۰۰٬۰۰۰ شارژ کند و همان را خرج کند، ۱٬۰۰۰٬۰۰۰
        درآمد نشان می‌دهد.

      • سفارش‌های رباتِ *نماینده* درآمد نماینده است، نه مالک. بدون
        فیلتر مستاجر، فروش آن‌ها در سود مالک می‌نشیند.

    پس فقط سفارش‌های تاییدشده‌ی مستاجر اصلی که با کارت پرداخت
    شده‌اند — شارژ کیف پول با کارت هم همین‌جاست، چون آن لحظه‌ی
    رسیدن پول است.
    """
    con = _bot_conn()
    if not con:
        return 0
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(orders)")}
        # نصب‌های قدیمی ستون paid_from ندارند؛ آن‌جا همه‌ی سفارش‌ها
        # کارتی بوده‌اند چون کیف پول هنوز نبوده.
        card = (" AND COALESCE(paid_from,'card')='card'"
                if "paid_from" in cols else "")
        # «مستاجرِ ریشه» یعنی هرکسی که نماینده‌ی کس دیگری نیست. با
        # ORDER BY id LIMIT 1 یک ردیف دلخواه انتخاب می‌شد و اگر
        # مستاجر دیگری زودتر ساخته شده بود، درآمد واقعی صفر
        # گزارش می‌شد — بی‌صدا.
        r = con.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM orders "
            "WHERE status='approved'" + card +
            " AND tenant_id IN (SELECT id FROM tenants WHERE parent_id IS NULL)"
        ).fetchone()
        return int((r["s"] if r else 0) or 0)
    except Exception:
        log.debug("خواندن درآمد ربات ناموفق", exc_info=True)
        return 0
    finally:
        con.close()


# ── One-file backup (docs/specs/2026-10-01-admin-bot-backup-ui.md, part A) ──
try:
    import backup as BACKUP                 # noqa: E402
except ImportError:
    # Loaded by path without backend/ on sys.path (many tests, like `license`
    # above): the same object under the plain name.
    import importlib.util as _ibak
    import sys as _sys
    _bs = _ibak.spec_from_file_location("backup", Path(__file__).resolve().parent / "backup.py")
    BACKUP = _ibak.module_from_spec(_bs)
    _sys.modules["backup"] = BACKUP
    _bs.loader.exec_module(BACKUP)


def _backup_dbs():
    """Where each database really is: the bot and billing paths come from
    environment variables and are not always under data/."""
    return {"bot.db": BOT_DB, "billing.db": BILLING_DB,
            "tunnels.db": Path(os.getenv("TUNNEL_DB_PATH",
                                         str(CONFIG_PATH.parent / "tunnels.db")))}


def _backup_dir():
    d = CONFIG_PATH.parent / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_host():
    import socket
    return _re.sub(r"[^A-Za-z0-9.-]", "", socket.gethostname())[:40] or "panel"


def full_backup_file():
    """Build the whole-panel zip in data/backups/ and return its path. Used by
    the download below, by `nexora backup` and by the management bot."""
    name = f"nexora-backup-{_backup_host()}-{datetime.now():%Y%m%d-%H%M%S}.zip"
    out = _backup_dir() / name
    BACKUP.build(CONFIG_PATH.parent, _backup_dbs(), _panel_version(), out,
                 host=_backup_host())
    # Keep the ten newest: one a day for a week and a half, not a full disk.
    olds = sorted(_backup_dir().glob("nexora-backup-*.zip"))[:-10]
    for p in olds:
        try:
            p.unlink()
        except OSError as e:
            log.warning("old backup %s not removed: %s", p.name, e)
    return out


@app.get("/api/admin/backup/full")
def backup_full(x_admin_password: str = Header(...)):
    """The whole panel in one zip: databases, settings, receipts, logos."""
    check_auth(x_admin_password)
    try:
        p = full_backup_file()
    except Exception as e:
        log.warning("full backup failed", exc_info=True)
        raise HTTPException(status_code=500,
                            detail=f"ساختِ پشتیبان ناموفق بود: {type(e).__name__}: {str(e)[:160]}")
    return Response(content=p.read_bytes(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{p.name}"'})


@app.post("/api/admin/backup/full/restore")
async def backup_full_restore(request: Request, x_admin_password: str = Header(...)):
    """
    Restore the whole panel from one zip (raw body, no multipart: one less
    dependency on every server). The current state is saved first as a
    backup of its own; without that copy nothing is touched.
    """
    check_auth(x_admin_password)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="فایلی فرستاده نشد")
    up = _backup_dir() / f"upload-{datetime.now():%Y%m%d-%H%M%S}.zip"
    up.write_bytes(body)
    safety = _backup_dir() / f"before-restore-{datetime.now():%Y%m%d-%H%M%S}.zip"
    try:
        out = BACKUP.restore(up, CONFIG_PATH.parent, _backup_dbs(), _panel_version(),
                             safety, host=_backup_host())
    except BACKUP.BackupError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            up.unlink()
        except OSError as e:
            # a stray upload is disk, not data: said, not raised
            log.warning("uploaded backup %s not removed: %s", up.name, e)
    # The settings cache and the bot's connections read the old state until
    # they reopen; restarting the bot is the reliable way. The panel reads
    # its config from the database on every call.
    ok, why = _svc("restart")
    out["botRestarted"] = ok
    if not ok:
        out["botWarning"] = f"ربات دوباره راه‌اندازی نشد ({why}); یک‌بار از صفحه‌ی ربات روشنش کنید."
    log.info("full restore: %d files from %s", len(out["restored"]), out.get("from"))
    return out


@app.get("/api/admin/billing/backup")
def billing_backup(x_admin_password: str = Header(...)):
    """بک‌آپ کامل حسابداری — نرخ‌ها، پرداخت‌ها و لاگ تمدید."""
    check_auth(x_admin_password)
    try:
        con = _billing_conn()
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"دیتابیس حسابداری باز نشد: {str(e)[:120]}")
    try:
        dump = {}
        for t in _tables_of(con, ("group_config", "payments", "renewals",
                                  "expenses", "client_seen")):
            try:
                dump[t] = [dict(r) for r in con.execute(f"SELECT * FROM {t}")]
            except Exception:
                dump[t] = []
        return {
            "version": 1,
            "createdAt": datetime.now().isoformat(timespec="seconds"),
            "counts": {k: len(v) for k, v in dump.items()},
            "data": dump,
        }
    finally:
        con.close()


@app.post("/api/admin/billing/restore")
def billing_restore(payload: dict, x_admin_password: str = Header(...)):
    """
    بازیابی بک‌آپ حسابداری.

    قبل از هر کاری یک نسخه‌ی امن از وضعیت فعلی گرفته می‌شود، چون
    نرخ‌ها و پرداخت‌ها داده‌ی مالی‌اند و از دست رفتنشان گران است.
    """
    check_auth(x_admin_password)
    data = (payload or {}).get("data")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="فایل بک‌آپ نامعتبر است")

    safety = None
    try:
        import shutil
        if BILLING_DB.exists():
            safety = BILLING_DB.with_name(
                f"billing-before-restore-{datetime.now():%Y%m%d-%H%M%S}.db")
            shutil.copy2(BILLING_DB, safety)
    except Exception:
        # مثلِ ربات: بی‌نسخه‌ی امن هم ادامه می‌دهیم، ولی گفته می‌شود
        log.warning("نسخه‌ی امنِ حسابداری پیش از بازگردانی گرفته نشد", exc_info=True)
        safety = None

    con = _billing_conn()
    try:
        # فقط جدول‌هایی که هم در فایل‌اند و هم در این دیتابیس. قبلاً
        # سه جدولِ ثابت بی‌قید خالی می‌شدند — یعنی بازگردانیِ یک
        # پشتیبانِ قدیمی، داده‌ی جدول‌هایی را که در آن نبود پاک می‌کرد.
        order = [x for x in _tables_of(con, ("group_config", "payments",
                                             "renewals", "expenses",
                                             "client_seen"))
                 if x in data]
        try:
            restored, skipped, why = _restore_tables(con, order, data)
        except Exception as e:
            con.rollback()
            raise HTTPException(status_code=500, detail=f"بازیابی ناموفق: {str(e)[:200]}")
        con.commit()
        out = {"ok": True, "restored": restored,
               "safetyCopy": str(safety) if safety else None}
        if skipped:
            out["skipped"] = skipped
            out["skippedWhy"] = why
            out["warning"] = _restore_warning(skipped, why)
        if safety is None and BILLING_DB.exists():
            out["safetyWarning"] = "نسخه‌ی امنِ پیش از بازگردانی گرفته نشد"
        return out
    finally:
        con.close()


@app.put("/api/admin/billing/xui-path")
def billing_xui_path_set(payload: dict, x_admin_password: str = Header(...)):
    """
    فقط مسیرِ دستیِ دیتابیسِ x-ui — نه کلِ تنظیمات.

    پیش‌تر صفحه کلِ تنظیمات را می‌خواند، یک کلید را عوض می‌کرد و کل را
    پس می‌فرستاد، بی‌آنکه نسخه‌اش را بفرستد: هر تغییری که در این فاصله
    جای دیگری ذخیره شده بود بی‌صدا پاک می‌شد، و اگر خواندن شکست خورده
    بود، پاسخِ خطا به‌جای تنظیمات ذخیره می‌شد. این‌جا خواندن و نوشتن هر
    دو سمتِ سرور است.
    """
    check_auth(x_admin_password)
    path = (payload or {}).get("path")
    if path is None or not isinstance(path, str):
        raise HTTPException(status_code=400, detail="مسیر باید متن باشد")
    path = path.strip()
    if len(path) > 500:
        raise HTTPException(status_code=400, detail="مسیر بیش از حد بلند است")
    cfg = load_config()
    cfg.setdefault("advanced", {})
    cfg["advanced"]["xuiDbPath"] = path
    ver = save_config(cfg)
    return {"ok": True, "path": path, "version": ver}


@app.get("/api/admin/billing/xui-path")
def billing_xui_path(x_admin_password: str = Header(...)):
    """
    وضعیت مسیر دیتابیس x-ui — برای بخش تنظیمات.

    مسیرهای رایج را هم بررسی می‌کند تا اگر جای دیگری نصب شده،
    کاربر مجبور نباشد حدس بزند.
    """
    check_auth(x_admin_password)
    cur = _xui_db_path()

    found = []
    for p in XUI_CANDIDATES:
        pp = Path(p)
        if pp.exists():
            found.append({"path": p, "readable": os.access(pp, os.R_OK),
                          "size": pp.stat().st_size})

    # تست واقعی اتصال — نه فقط بررسی وجود فایل
    con, err = _xui_conn()
    tables = []
    if con:
        try:
            tables = [r["name"] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        except Exception as _exc:
            log.debug("x-ui table list: %s", _exc)
        finally:
            con.close()

    return {
        "current": str(cur),
        "exists": cur.exists(),
        "readable": cur.exists() and os.access(cur, os.R_OK),
        "connected": con is not None or err is None,
        "error": err,
        "tables": tables[:30],
        "hasClients": "clients" in tables or "client_traffics" in tables,
        "hasGroups": "client_groups" in tables,
        "found": found,
        # مسیرِ دستیِ ذخیره‌شده — تا صفحه برای نشان‌دادنش کلِ تنظیمات را نخواند
        "manual": ((load_config().get("advanced") or {}).get("xuiDbPath") or ""),
        "envVar": os.getenv("XUI_DB_PATH", ""),
    }


def _fa(text):
    """
    آماده‌سازی متن فارسی برای PDF.

    reportlab حروف را نمی‌چسباند و راست‌به‌چپ نمی‌کند، پس قبلش
    خودمان شکل‌دهی و ترتیب را درست می‌کنیم. اگر کتابخانه‌ها نبودند،
    متن خام برمی‌گردد تا حداقل چیزی چاپ شود.
    """
    s = str(text or "")
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def _pdf_font(bold=False):
    """
    فونت فارسی برای PDF.

    اول ایران‌سنس همراه پروژه، بعد فونت‌های سیستم. هر فونت با یک
    نمونه‌ی واقعی آزمایش می‌شود چون خیلی‌ها حروف پایه را دارند ولی
    گلیف‌های اتصالی را نه، و نتیجه مربع خالی می‌شود.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    key = "NexoraFA-Bold" if bold else "NexoraFA"
    if key in pdfmetrics.getRegisteredFontNames():
        return key

    try:
        import arabic_reshaper
        probe = arabic_reshaper.reshape("صورتحساب مبلغ باقی‌مانده")
    except Exception:
        probe = "\ufebb\ufeee\ufead\ufe97\ufea4\ufeb4"

    def covers(path):
        try:
            from fontTools.ttLib import TTFont as FT
            ft = FT(path, fontNumber=0, lazy=True)
            cmap = set(ft.getBestCmap().keys())
            ft.close()
            return {ord(ch) for ch in probe if ch.strip()}.issubset(cmap)
        except Exception:
            return False

    import glob
    fonts_dir = _root_dir() / "assets" / "fonts"
    want = "Bold" if bold else "Regular"

    candidates = []
    # فونت همراه پروژه، با وزن درست
    candidates += sorted(glob.glob(str(fonts_dir / f"*{want}*.ttf")))
    candidates += sorted(glob.glob(str(fonts_dir / "*.ttf")))
    candidates += sorted(glob.glob(str(_root_dir() / "assets" / "*.ttf")))

    system = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
    prefer = ("iransans", "vazir", "sahel", "shabnam", "naskh", "arabic")
    candidates += [f for f in system
                   if any(p in f.lower() for p in prefer)
                   and (want.lower() in f.lower() or not bold)]
    candidates += [f for f in system
                   if "bold" not in f.lower() and "italic" not in f.lower()]

    for path in candidates:
        if covers(path):
            try:
                pdfmetrics.registerFont(TTFont(key, path))
                return key
            except Exception:
                continue

    return "Helvetica-Bold" if bold else "Helvetica"


@app.get("/api/admin/bot/users/report/pdf")
def bot_users_report_pdf(days: int = 30, x_admin_password: str = Header(...)):
    """
    گزارش فروش ربات به‌صورت PDF — با همان قالب و رنگ صورتحساب واسطه.

    چیزی که فقط روی صفحه است را نمی‌شود بایگانی کرد یا برای شریک
    فرستاد؛ به همین دلیل نسخه‌ی چاپی لازم است. و چون کنار صورتحساب
    حسابداری بایگانی می‌شود، باید همان شکل را داشته باشد نه یک جدول
    ساده‌ی بی‌قواره.
    """
    check_auth(x_admin_password)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.pdfgen import canvas as pdfcanvas
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="reportlab نصب نیست: pip install reportlab arabic-reshaper python-bidi")

    rep = bot_users_report(days=days, x_admin_password=x_admin_password)
    if not rep.get("ready"):
        raise HTTPException(status_code=400,
                            detail=rep.get("error") or "گزارش در دسترس نیست")

    F = _pdf_font()
    FB = _pdf_font(bold=True)

    import io as _io
    buf = _io.BytesIO()
    W, H = A4
    c = pdfcanvas.Canvas(buf, pagesize=A4)

    # همان پالت صورتحساب — روشن و چاپ‌پذیر
    NAVY = colors.HexColor("#1F3864")
    INK = colors.HexColor("#1A1A1A")
    GREY = colors.HexColor("#555555")
    MUTE = colors.HexColor("#8A92A0")
    LINE = colors.HexColor("#CFD6E4")
    SOFT = colors.HexColor("#F6F8FC")
    CARD = colors.HexColor("#FAFBFD")
    HEAD = colors.HexColor("#E8EDF6")
    GOOD = colors.HexColor("#14683C")

    def money(n):
        return f"{int(n or 0):,}"

    stamp = datetime.now()
    doc_no = f"NX-R-{stamp:%Y%m%d}-{days}"

    ML, MR = 14 * mm, 14 * mm
    CW = W - ML - MR
    page = [0]

    def footer():
        c.setFont(F, 7)
        c.setFillColor(MUTE)
        c.drawCentredString(W / 2, 8 * mm,
                            _fa(f"گزارش نکسورا — صفحه {page[0]}"))

    def header():
        c.setFillColor(colors.white)
        c.rect(0, 0, W, H, fill=1, stroke=0)

        y0 = H - 14 * mm
        c.setFont(FB, 19)
        c.setFillColor(NAVY)
        c.drawString(ML, y0 - 4 * mm, "NEXORA")
        c.setFont(F, 8)
        c.setFillColor(GREY)
        c.drawString(ML, y0 - 9.5 * mm, _fa("گزارش فروش ربات تلگرام"))

        c.setFont(F, 8)
        meta = [
            (_fa("شماره گزارش") + ": ", doc_no),
            (_fa("تاریخ صدور") + ": ", stamp.strftime("%Y-%m-%d")),
            (_fa("بازه") + ": ", _fa(f"{days} روز گذشته")),
        ]
        yy = y0 - 3 * mm
        for label, val in meta:
            c.setFillColor(GREY)
            tw = c.stringWidth(val, F, 8)
            c.drawRightString(W - MR, yy, val)
            c.setFillColor(MUTE)
            c.drawRightString(W - MR - tw - 1 * mm, yy, label)
            yy -= 4.5 * mm

        c.setStrokeColor(NAVY)
        c.setLineWidth(1.8)
        c.line(ML, H - 28 * mm, W - MR, H - 28 * mm)
        footer()
        return H - 38 * mm

    y = header()

    o = rep.get("orders") or {}
    u = rep.get("users") or {}
    subs = rep.get("subs") or {}

    # ── کارت‌های خلاصه ──
    cards = [
        ("کاربر جدید", f"{int(u.get('newUsers') or 0):,}", NAVY),
        ("خریدار", f"{int(rep.get('buyerCount') or 0):,}", NAVY),
        ("سفارش موفق", f"{int(o.get('approved') or 0):,}", GOOD),
        # «فروش»، نه «درآمد»: سفارشی که از کیف پول پرداخت شده در این
        # عدد هست، ولی پول تازه‌ای با آن نرسیده.
        ("فروش (تومان)", money(o.get("revenue")), GOOD),
    ]
    cw = CW / len(cards)
    for idx, (label, val, col) in enumerate(cards):
        x = ML + idx * cw
        c.setFillColor(CARD)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.roundRect(x + 1.2 * mm, y - 17 * mm, cw - 2.4 * mm, 17 * mm,
                    2 * mm, fill=1, stroke=1)
        c.setFont(F, 7.5)
        c.setFillColor(MUTE)
        c.drawCentredString(x + cw / 2, y - 5.5 * mm, _fa(label))
        c.setFont(FB, 13)
        c.setFillColor(col)
        c.drawCentredString(x + cw / 2, y - 13 * mm, val)
    y -= 26 * mm

    # ── خلاصه‌ی دوره ──
    detail = [
        ("نرخ تبدیل بازدید به خرید", f"{rep.get('conversion') or 0}%"),
        ("میانگین هر سفارش", money(o.get("avg")) + " " + _fa("تومان")),
        ("سفارش رد شده", f"{int(o.get('rejected') or 0):,}"),
        ("سفارش در انتظار", f"{int(o.get('pending') or 0):,}"),
        ("اشتراک فعال", f"{int(subs.get('active') or 0):,}"),
    ]
    c.setFont(FB, 9.5)
    c.setFillColor(NAVY)
    c.drawRightString(W - MR, y, _fa("خلاصه‌ی دوره"))
    y -= 6 * mm

    for idx, (label, val) in enumerate(detail):
        if idx % 2 == 0:
            c.setFillColor(SOFT)
            c.rect(ML, y - 2.2 * mm, CW, 6.8 * mm, fill=1, stroke=0)
        c.setFont(F, 8.5)
        c.setFillColor(MUTE)
        c.drawRightString(W - MR - 2 * mm, y, _fa(label))
        c.setFillColor(INK)
        c.drawString(ML + 2 * mm, y, val)
        y -= 6.8 * mm

    y -= 8 * mm

    # ── بیشترین خریداران ──
    c.setFont(FB, 9.5)
    c.setFillColor(NAVY)
    c.drawRightString(W - MR, y, _fa("بیشترین خریداران"))
    y -= 7 * mm

    COL_AMOUNT = ML + 2 * mm
    COL_ORDERS = ML + 42 * mm

    def table_head(yy):
        c.setFillColor(HEAD)
        c.rect(ML, yy - 2.4 * mm, CW, 7.5 * mm, fill=1, stroke=0)
        c.setFont(FB, 8)
        c.setFillColor(NAVY)
        c.drawString(COL_AMOUNT, yy, _fa("مبلغ (تومان)"))
        c.drawString(COL_ORDERS, yy, _fa("سفارش"))
        c.drawRightString(W - MR - 2 * mm, yy, _fa("مشتری"))
        return yy - 8.5 * mm

    y = table_head(y)

    buyers = rep.get("buyers") or []
    if not buyers:
        c.setFont(F, 8.5)
        c.setFillColor(MUTE)
        c.drawCentredString(W / 2, y, _fa("در این بازه خریدی ثبت نشده است"))
        y -= 8 * mm
    else:
        for idx, b in enumerate(buyers[:30]):
            if y < 28 * mm:
                c.showPage()
                y = table_head(header())
            if idx % 2 == 0:
                c.setFillColor(SOFT)
                c.rect(ML, y - 2.2 * mm, CW, 6.8 * mm, fill=1, stroke=0)
            name = (b.get("first_name") or b.get("username")
                    or str(b.get("tg_id") or ""))
            c.setFont(F, 8.5)
            c.setFillColor(INK)
            c.drawString(COL_AMOUNT, y, money(b.get("spent")))
            c.setFillColor(GREY)
            c.drawString(COL_ORDERS, y, f"{int(b.get('orders') or 0):,}")
            c.setFillColor(INK)
            c.drawRightString(W - MR - 2 * mm, y, _fa(str(name)[:38]))
            y -= 6.8 * mm

        total = sum(int(b.get("spent") or 0) for b in buyers)
        c.setStrokeColor(NAVY)
        c.setLineWidth(0.9)
        c.line(ML, y - 0.5 * mm, W - MR, y - 0.5 * mm)
        y -= 6.5 * mm
        c.setFont(FB, 9)
        c.setFillColor(NAVY)
        c.drawString(COL_AMOUNT, y, money(total))
        c.drawRightString(W - MR - 2 * mm, y, _fa("جمع کل"))
        y -= 9 * mm

    # ── روند روزانه ──
    #
    # نمودار میله‌ای ساده و بدون کتابخانه: روند فروش را در یک نگاه
    # نشان می‌دهد، که از یک ستون عدد خیلی گویاتر است.
    daily = rep.get("daily") or []
    if daily and y > 55 * mm:
        c.setFont(FB, 9.5)
        c.setFillColor(NAVY)
        c.drawRightString(W - MR, y, _fa("روند فروش روزانه"))
        y -= 8 * mm

        peak = max([int(x.get("sum") or 0) for x in daily] + [1])
        bar_h = 22 * mm
        n = min(len(daily), 30)
        shown = daily[-n:]
        bw = CW / n
        base = y - bar_h

        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(ML, base, W - MR, base)

        for idx, x in enumerate(shown):
            v = int(x.get("sum") or 0)
            h = (v / peak) * bar_h if peak else 0
            bx = ML + idx * bw
            c.setFillColor(NAVY if v else LINE)
            c.rect(bx + bw * 0.22, base, bw * 0.56, max(h, 0.4),
                   fill=1, stroke=0)

        c.setFont(F, 6.5)
        c.setFillColor(MUTE)
        c.drawString(ML, base - 4 * mm, _fa(str(shown[0].get("d") or "")))
        c.drawRightString(W - MR, base - 4 * mm,
                          _fa(str(shown[-1].get("d") or "")))
        c.drawCentredString(W / 2, base - 4 * mm,
                            _fa("بیشترین روز: ") + money(peak))

    c.showPage()
    c.save()
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/pdf",
        headers={"Content-Disposition":
                 "attachment; filename=nexora-bot-report-" + str(days) + "d.pdf"})



# ═══════════════════════════════════════════════════════════
#  سلامت سیستم
# ═══════════════════════════════════════════════════════════

try:
    import health as HEALTH
except Exception:
    HEALTH = None

# آخرین وضعیت هر سرور، تا فقط وقتی چیزی عوض شد هشدار بدهیم
_health_state = {}


def _health_ports():
    """پورت‌هایی که باید شنونده داشته باشند — از inboundهای ۳x-ui."""
    ports = set()
    try:
        con, _ = _xui_conn()
        if con:
            try:
                for r in con.execute("SELECT port FROM inbounds WHERE enable=1"):
                    if r[0]:
                        ports.add(int(r[0]))
            except Exception as _exc:
                log.warning("health: reading x-ui ports: %s", _exc)
            con.close()
    except Exception as _exc:
        log.warning("health: reading x-ui ports: %s", _exc)
    return sorted(ports)[:12]


def _health_domain():
    try:
        cfg = load_config()
        return ((cfg.get("advanced") or {}).get("panelDomain") or "").strip() or None
    except Exception:
        return None



def _health_alert(server, data, key):
    """
    هشدار تلگرام — وقتی وضعیت عوض شود، و اولین باری که خراب است.

    اگر هر بار پیام بدهیم، بعد از چند ساعت کسی نگاهشان نمی‌کند. پس
    تکرارِ همان سطح خبر نمی‌شود.

    ولی «اولین مشاهده» را هم ساکت گذاشتن یک سوراخ واقعی می‌ساخت:
    وضعیت در حافظه‌ی همین پردازه نگه داشته می‌شود، پس هر ری‌استارت
    پنل آن را پاک می‌کند — و `nexora update` هر بار ری‌استارت می‌کند.

    اگر سروری با دیسک پر بالا می‌آمد، اجرای اول فقط ثبت می‌کرد و
    ساکت می‌ماند؛ اجراهای بعدی هم چون سطح عوض نشده بود ساکت
    می‌ماندند. دیسک تا ابد پر و هیچ پیامی. برای سامانه‌ای که تنها
    کارش خبردادن است، بدترین حالت ممکن.

    حالا اولین مشاهده هم خبر می‌شود، ولی فقط وقتی «ok» نباشد — پس
    ری‌استارتِ سرورِ سالم هیچ پیامی نمی‌سازد.
    """
    level = data.get("level", "ok")
    prev = _health_state.get(key)
    _health_state[key] = level

    if prev == level:
        return
    if prev is None and level == "ok":
        return

    crit = [c for c in data.get("checks", []) if c.get("level") == "crit"]
    warn = [c for c in data.get("checks", []) if c.get("level") == "warn"]

    if level == "ok":
        text = f"✅ <b>{server}</b>\n\nمشکلات برطرف شد."
    else:
        icon = "🔴" if level == "crit" else "🟡"
        lines = [f"{icon} <b>{server}</b>", "", data.get("summary", ""), ""]
        for c in (crit + warn)[:6]:
            mark = "❌" if c["level"] == "crit" else "⚠️"
            lines.append(f"{mark} <b>{c['title']}</b> — {c['detail']}")
            if c.get("hint"):
                lines.append(f"   <i>{c['hint'][:110]}</i>")
        text = "\n".join(lines)

    # Server and tunnel alerts belong to the owner's management bot, not the
    # bot his customers buy from (docs/specs/2026-10-01-admin-bot-backup-ui.md).
    # Not delivered there (no bot set, or Telegram refused) → the sales bot's
    # group as before: an alert that goes nowhere is the one failure this
    # function exists to prevent.
    if _adminbot_alert(text):
        return
    try:
        import sqlite3 as sq
        con = sq.connect(f"file:{BOT_DB}?mode=ro", uri=True, timeout=5)
        con.row_factory = sq.Row
        # مستاجر ریشه، نه هر ردیفی که اول بیاید.
        #
        # بدون این شرط، اگر ردیف مالک یک‌بار پاک و دوباره ساخته شود —
        # که با اجرای دوباره‌ی نصب اتفاق می‌افتد — شناسه‌اش بزرگ‌تر از
        # شناسه‌ی نماینده می‌شود و LIMIT 1 نماینده را برمی‌دارد.
        #
        # آن‌وقت هشدارِ سرورِ مالک با رباتِ نماینده و به گروهِ نماینده
        # فرستاده می‌شود: دیسک پر، سرویس خاموش، انقضای گواهی و نام
        # میزبان‌ها می‌رود دست شخص سوم، و مالک هیچ خبری نمی‌گیرد.
        # ستون‌ها `admin_id` و `group_id` خوانده می‌شدند که در جدولِ tenants
        # هرگز نبوده‌اند (نامشان `owner_tg_id` و `admin_group_id` است). پس
        # این کوئری همیشه خطا می‌داد، `except: pass` می‌بلعیدش، و **هیچ
        # هشدارِ سروری — دیسکِ پر، سرویسِ خاموش، گواهیِ رو به انقضا — هرگز
        # فرستاده نشد.** مسیریابی حالا همان `staff_chat`ِ ربات است: گروهِ
        # مدیریت با تاپیکِ alerts، وگرنه پیویِ صاحبِ ربات.
        r = con.execute(
            "SELECT bot_token, owner_tg_id, admin_group_id, topics FROM tenants "
            "WHERE parent_id IS NULL ORDER BY id LIMIT 1").fetchone()
        con.close()
        if not r or not r["bot_token"]:
            log.info("health alert not sent: bot has no token")
            return
        thread = None
        if r["admin_group_id"]:
            target = r["admin_group_id"]
            try:
                thread = (json.loads(r["topics"] or "{}") or {}).get("alerts")
            except (json.JSONDecodeError, TypeError, AttributeError):
                thread = None
        else:
            target = r["owner_tg_id"]
        if not target:
            log.info("health alert not sent: no admin group and no owner chat")
            return
        import urllib.request
        msg = {"chat_id": target, "text": text, "parse_mode": "HTML"}
        if thread:
            msg["message_thread_id"] = thread
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{r['bot_token']}/sendMessage",
            data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=12)
    except Exception as e:
        # توکن در آدرس است؛ فقط نوع و متنِ کوتاهِ خطا، نه URL
        log.warning("health alert not sent: %s: %s", type(e).__name__, str(e)[:160])


# ── Management bot (docs/specs/2026-10-01-admin-bot-backup-ui.md, part B) ──
try:
    import adminbot as ADMINBOT             # noqa: E402
except ImportError:
    import importlib.util as _iadb
    import sys as _sys
    _as = _iadb.spec_from_file_location("adminbot", Path(__file__).resolve().parent / "adminbot.py")
    ADMINBOT = _iadb.module_from_spec(_as)
    _sys.modules["adminbot"] = ADMINBOT
    _as.loader.exec_module(ADMINBOT)


def _tg_bot(token):
    """The bot's own Telegram client (retries, safe HTML), not a third copy."""
    _bot_handlers()                         # puts bot/ on sys.path
    import tg as _TG
    return _TG.Bot(token)


def _adminbot_alert(text):
    """Send an alert to the management bot's admins. True if anyone got it."""
    s = ADMINBOT.settings(ADMINBOT.load(CONFIG_PATH.parent))
    tok = s["monitorToken"] or s["token"]
    if not tok or not s["admins"]:
        return False
    sent = False
    bot = _tg_bot(tok)
    for cid in s["admins"]:
        try:
            bot.send(cid, text)
            sent = True
        except Exception as e:
            log.warning("management bot alert to %s not sent: %s", cid, str(e)[:160])
    return sent


_LIC_STATE_FA = {"active": "فعال", "grace": "در مهلت", "expired": "منقضی",
                 "none": "ندارد", "invalid": "نامعتبر"}


class _AdminBotApi:
    """What each button of the management bot does: the panel's own functions."""

    def status(self):
        lines = [f"📊 <b>وضعیت</b> · نسخه‌ی {_panel_version()}", ""]
        if HEALTH:
            try:
                h = HEALTH.run_all(ports=_health_ports(), domain=_health_domain())
                icon = {"ok": "🟢", "warn": "🟡", "crit": "🔴"}.get(h.get("level"), "⚪")
                lines.append(f"{icon} سرور: {h.get('summary', '')}")
                for c in [c for c in h.get("checks", []) if c.get("level") != "ok"][:5]:
                    lines.append(f"   {'❌' if c['level'] == 'crit' else '⚠️'} {c['title']}: {c['detail']}")
            except Exception as e:
                lines.append(f"⚪ بررسیِ سرور ناموفق: {type(e).__name__}")
        lines.append(("🟢" if _svc_active("nexora-bot") else "🔴") + " ربات فروش")
        try:
            st = LIC.status()
            lines.append(f"🔑 مجوز Pro: {_LIC_STATE_FA.get(st.get('state'), st.get('state') or '؟')}")
        except Exception as e:
            lines.append(f"🔑 مجوز: خوانده نشد ({type(e).__name__})")
        return "\n".join(lines)

    def backup(self):
        return full_backup_file()

    def sales(self):
        t = _root_tenant_row()
        if not t:
            return "ربات فروش هنوز تنظیم نشده."
        st = _bot_db_rw(t).stats()
        h = _bot_handlers()
        fa, toman = h.core.fa, h.core.toman
        out = (f"💰 <b>امروز</b>\n\n"
               f"فروش: <b>{toman(st.get('revenue_today', 0))}</b> تومان\n"
               f"کاربرِ تازه: <b>{fa(st.get('users_today', 0))}</b>\n"
               f"اشتراکِ فعال: <b>{fa(st.get('active_subs', 0))}</b>\n"
               f"رسیدِ در انتظار: <b>{fa(st.get('pending', 0))}</b>")
        if st.get("open_tickets"):
            out += f"\nتیکتِ باز: <b>{fa(st['open_tickets'])}</b>"
        return out

    def search(self, q):
        clients, _k, err = _read_xui_clients()
        if clients is None:
            return f"❌ دیتابیسِ 3x-ui خوانده نشد: {err}"
        ql = q.strip().lower()
        hits = [c for c in clients if ql in (c.get("email") or "").lower()
                or ql in (c.get("comment") or "").lower()][:6]
        if not hits:
            return f"کانفیگی با «{q[:40]}» پیدا نشد."
        fa_date = _bot_handlers().core.fa_date
        gb = 1024 ** 3
        rows = []
        for c in hits:
            used = c.get("used", 0) / gb
            tot = c.get("totalGB", 0) / gb
            exp = int(c.get("expiry") or 0)
            if exp < 0:
                when = f"از اولین اتصال، {-exp // 86400000} روز"
            elif exp == 0:
                when = "بی‌تاریخ"
            else:
                when = fa_date(datetime.fromtimestamp(exp / 1000).isoformat())
            rows.append(f"{'🟢' if c.get('enable') else '⚫️'} <code>{c.get('email')}</code> · {c.get('group')}\n"
                        f"   {used:.1f} از {('%.0f' % tot + ' گیگ') if tot else 'نامحدود'} · {when}")
        more = f"\n\n(فقط {len(hits)} مورد اول)" if len(hits) == 6 else ""
        return "🔎 <b>نتیجه</b>\n\n" + "\n\n".join(rows) + more

    def restart(self, what):
        return _svc("restart", "nexora-bot" if what == "bot" else "nexora-panel")

    def admin_url(self):
        return admin_url()

    def set_backup_every(self, h):
        ADMINBOT.update(CONFIG_PATH.parent, backupEvery=int(h))


_ROLE_FA = {"iran": "ایران", "foreign": "خارج"}
_TUN_OFF = "بخشِ تانل (Pro) روی این پنل فعال نیست."


class _TunnelBotApi:
    """
    What the tunnel bot's buttons show: the tunnel section's own data (Pro:
    `TUN`, `_link_diag_data`, `_linkcheck_tick`, loaded into this namespace).
    Without Pro each answer says so instead of failing.
    """

    @staticmethod
    def _tun():
        return globals().get("TUN") if globals().get("TUNNELS_OK") else None

    def tunnels(self):
        T = self._tun()
        if not T:
            return _TUN_OFF
        rows = T.list_tunnels()
        if not rows:
            return "📡 هنوز تانلی ساخته نشده."
        lines = [f"📡 <b>تانل‌ها</b> · {len(rows)}", ""]
        for t in rows[:25]:
            on = t.get("status") == "running"
            node = "" if t.get("nodeOnline", True) else " · سرورش آفلاین"
            lines.append(f"{'🟢' if on else '🔴'} <b>{t.get('name') or '#' + str(t.get('id'))}</b>"
                         f" · {t.get('engineName') or t.get('engine') or ''}"
                         f" · {'روشن' if on else 'خاموش'}{node}")
        return "\n".join(lines)

    def servers(self):
        T = self._tun()
        if not T:
            return _TUN_OFF
        rows = T.list_nodes()
        if not rows:
            return "🖥 هنوز سروری اضافه نشده."
        lines = [f"🖥 <b>سرورها</b> · {len(rows)}", ""]
        for n in rows[:25]:
            lines.append(f"{'🟢' if n.get('online') else '🔴'} <b>{n.get('name')}</b>"
                         f" · {_ROLE_FA.get(n.get('role'), n.get('role') or '')}"
                         f" · {n.get('running_count', 0)}/{n.get('tunnel_count', 0)} تانل"
                         + ("" if n.get("online") else f" · آخرین تماس {str(n.get('last_seen') or '؟')[:16]}"))
        return "\n".join(lines)

    def diagnosis(self):
        f = globals().get("_link_diag_data")
        if not (self._tun() and f):
            return _TUN_OFF
        nodes = (f() or {}).get("nodes") or []
        if not nodes:
            return "🩺 هنوز نتیجه‌ای نیست؛ «بررسیِ دوباره» را بزنید."
        icon = {"ok": "🟢", "warn": "🟡", "bad": "🔴"}
        lines = ["🩺 <b>عیب‌یابی</b>", ""]
        for n in nodes[:15]:
            v = n.get("verdict") or {}
            lines.append(f"{icon.get(v.get('level'), '⚪')} <b>{n.get('name')}</b>: "
                         f"{v.get('title') or 'در انتظارِ نتیجه'}")
            if v.get("level") in ("warn", "bad") and v.get("fix"):
                lines.append(f"   چه کنم: {str(v['fix'])[:160]}")
        return "\n".join(lines)

    def recheck(self):
        f = globals().get("_linkcheck_tick")
        if not (self._tun() and f):
            return _TUN_OFF
        try:
            f(force=True)
        except Exception as e:
            return f"❌ بررسی شروع نشد: {type(e).__name__}"
        return ("🔄 بررسی شروع شد. نتیجه‌ی سرورها تا یکی دو دقیقه‌ی دیگر می‌رسد؛ "
                "بعد «🩺 عیب‌یابی» را بزنید.")


#: Last diagnosis level per server, for "a tunnel broke / recovered" alerts.
_TUN_LEVELS = {}


def _tunnel_alert_tick():
    """
    Compare each server's diagnosis with the last look and tell the owner what
    changed (`adminbot.level_changes`). Until now a broken tunnel showed only on
    the diagnosis page: nothing told the owner. Runs from the health loop.
    """
    f = globals().get("_link_diag_data")
    if not (globals().get("TUNNELS_OK") and f):
        return 0
    nodes = (f() or {}).get("nodes") or []
    now = {str(n.get("id")): (n.get("verdict") or {}).get("level") or "unknown" for n in nodes}
    by_id = {str(n.get("id")): n for n in nodes}
    changes = ADMINBOT.level_changes(_TUN_LEVELS, now)
    _TUN_LEVELS.update(now)
    for nid, _old, new in changes:
        n = by_id[nid]
        v = n.get("verdict") or {}
        if new == "ok":
            text = f"✅ <b>{n.get('name')}</b>\nارتباط دوباره سالم است."
        else:
            text = (f"{'🔴' if new == 'bad' else '🟡'} <b>{n.get('name')}</b>\n{v.get('title') or ''}"
                    + (f"\n\n{str(v.get('reason'))[:300]}" if v.get("reason") else "")
                    + (f"\n\nچه کنم: {str(v.get('fix'))[:200]}" if v.get("fix") else ""))
        if not _adminbot_alert(text):
            log.info("tunnel alert not sent (no tunnel or management bot): %s", n.get("name"))
    return len(changes)


_ADMINBOT_STOP = _threading.Event()


@app.on_event("startup")
def _adminbot_boot():
    if os.getenv("NEXORA_NO_ADMIN_BOT"):
        return
    _threading.Thread(target=ADMINBOT.loop, name="admin-bot", daemon=True,
                      args=(_tg_bot, _AdminBotApi(), CONFIG_PATH.parent,
                            _ADMINBOT_STOP)).start()
    _threading.Thread(target=ADMINBOT.loop_tunnel, name="tunnel-bot", daemon=True,
                      args=(_tg_bot, _TunnelBotApi(), CONFIG_PATH.parent,
                            _ADMINBOT_STOP)).start()


def _mask_token(tok):
    return (tok[:6] + "…" + tok[-4:]) if tok and len(tok) > 12 else ("…" if tok else "")


@app.get("/api/admin/adminbot")
def adminbot_get(x_admin_password: str = Header(...)):
    """The management bot's settings. Tokens are never sent back whole."""
    check_auth(x_admin_password)
    raw = ADMINBOT.load(CONFIG_PATH.parent)
    s = ADMINBOT.settings(raw)
    root = _root_tenant_row() or {}
    return {"token": _mask_token(s["token"]), "hasToken": bool(s["token"]),
            "monitorToken": _mask_token(s["monitorToken"]), "hasMonitorToken": bool(s["monitorToken"]),
            "admins": s["admins"], "backupEvery": s["backupEvery"],
            "everyChoices": list(ADMINBOT.BACKUP_EVERY_CHOICES),
            "suggestAdmin": root.get("owner_tg_id") or None,
            "lastBackup": raw.get("lastBackup")}


@app.put("/api/admin/adminbot")
def adminbot_put(body: dict, x_admin_password: str = Header(...)):
    """
    Save the management bot. A token is checked with getMe before it is kept,
    and refused when it is a sales bot's token: two pollers on one token take
    turns getting "409 Conflict" and both bots go half-deaf.
    """
    check_auth(x_admin_password)
    cur = ADMINBOT.load(CONFIG_PATH.parent)
    names = {}
    for key in ("token", "monitorToken"):
        if key not in body:
            continue
        tok = str(body.get(key) or "").strip()
        if tok and "…" in tok:
            continue                       # the masked value came back unchanged
        if tok:
            con = _bot_conn()
            try:
                used = con and con.execute("SELECT 1 FROM tenants WHERE bot_token=?", (tok,)).fetchone()
            finally:
                if con:
                    con.close()
            if used:
                raise HTTPException(400, detail="این توکنِ رباتِ فروش است. برای ربات مدیریت یک ربات تازه در BotFather بسازید.")
            if tok == (cur.get("token") if key == "monitorToken" else cur.get("monitorToken")):
                raise HTTPException(400, detail="ربات مدیریت و ربات مانیتورینگ باید دو ربات جدا باشند (یا مانیتورینگ را خالی بگذارید).")
            try:
                me = _tg_bot(tok).me() or {}
            except Exception as e:
                raise HTTPException(400, detail=f"تلگرام این توکن را نپذیرفت: {str(e)[:120]}")
            names[key] = me.get("username") or ""
        cur[key] = tok
    if "admins" in body:
        ids = []
        for x in body.get("admins") or []:
            sx = str(x).strip()
            if not sx.lstrip("-").isdigit():
                raise HTTPException(400, detail=f"شناسه‌ی عددیِ تلگرام نیست: {sx[:20]}")
            ids.append(int(sx))
        cur["admins"] = ids
    if "backupEvery" in body:
        h = int(body.get("backupEvery") or 0)
        if h not in ADMINBOT.BACKUP_EVERY_CHOICES:
            raise HTTPException(400, detail="بازه‌ی پشتیبانِ خودکار نامعتبر است")
        cur["backupEvery"] = h
    ADMINBOT.update(CONFIG_PATH.parent, **cur)
    return {**adminbot_get(x_admin_password), "usernames": names}


@app.post("/api/admin/adminbot/test")
def adminbot_test(x_admin_password: str = Header(...)):
    """Send a hello to every admin, so the owner sees it works (and has pressed
    Start: a bot cannot message someone who never started it)."""
    check_auth(x_admin_password)
    s = ADMINBOT.settings(ADMINBOT.load(CONFIG_PATH.parent))
    if not (s["token"] or s["monitorToken"]) or not s["admins"]:
        raise HTTPException(400, detail="اول توکن و شناسه‌ی مدیر را ذخیره کنید")
    out = []
    for tok, label in ((s["token"], "مدیریت"), (s["monitorToken"], "تانل")):
        if not tok:
            continue
        bot = _tg_bot(tok)
        for cid in s["admins"]:
            try:
                if label == "مدیریت":
                    bot.send(cid, ADMINBOT.MENU_TEXT, ADMINBOT.menu_kb())
                else:
                    bot.send(cid, ADMINBOT.TUNNEL_MENU_TEXT, ADMINBOT.tunnel_menu_kb())
                out.append({"bot": label, "to": cid, "ok": True})
            except Exception as e:
                why = str(e)[:140]
                if "chat not found" in why.lower() or "forbidden" in why.lower():
                    why = "این شناسه هنوز ربات را Start نکرده"
                out.append({"bot": label, "to": cid, "ok": False, "why": why})
    return {"results": out}


try:
    import monitor as MONITOR
except Exception:
    try:
        import importlib.util as _ilu
        _ms = _ilu.spec_from_file_location(
            "monitor", Path(__file__).resolve().parent / "monitor.py")
        MONITOR = _ilu.module_from_spec(_ms)
        _ms.loader.exec_module(MONITOR)
    except Exception:
        MONITOR = None


@app.get("/api/admin/monitor")
def monitor_snapshot(sections: str = "", x_admin_password: str = Header(...)):
    """
    وضعیت زنده‌ی سرور.

    sections: فهرست کاما-جدا برای گرفتن فقط بخشی از داده‌ها — صفحه‌ای
    که هر ۵ ثانیه تازه می‌شود نباید هر بار apt را هم صدا بزند.
    """
    check_auth(x_admin_password)
    if not MONITOR:
        raise HTTPException(status_code=500, detail="ماژول مانیتورینگ بارگذاری نشد")

    want = [s.strip() for s in sections.split(",") if s.strip()] or None
    t0 = time.time()
    snap = MONITOR.snapshot(include=want)
    snap["took"] = round(time.time() - t0, 2)
    return snap


@app.get("/api/admin/health/local")
def health_local(x_admin_password: str = Header(...)):
    """سلامت همین سرور — جایی که پنل نصب است."""
    check_auth(x_admin_password)
    if not HEALTH:
        raise HTTPException(status_code=500, detail="ماژول سلامت بارگذاری نشد")

    res = HEALTH.run_all(ports=_health_ports(), domain=_health_domain())
    res["server"] = "سرور پنل"
    return res



# ═══════════════════════════════════════════════════════════
#  پنل نماینده
#
#  چرا یک سطح API جداگانه، و نه استفاده از مسیرهای مدیریتی:
#
#  پنل مدیر ۱۱۴ مسیر دارد و همه‌شان فرض می‌کنند «تو صاحب سیستمی».
#  دادنشان به نماینده یعنی هر کدام باید جداگانه به مستاجر خودش
#  محدود شود — و کافی است یکی جا بیفتد تا نماینده داده‌ی بقیه را
#  ببیند. همین کلاس اشتباه امروز در مسیرهای ایجنت پیدا شد: نودی که
#  احراز هویت شده بود ولی محدود نشده بود، می‌توانست کار نود دیگر را
#  ببندد.
#
#  پس فهرست مجاز، نه فهرست ممنوع: هر چیزی که این‌جا نوشته نشده،
#  برای نماینده اصلاً وجود ندارد. اضافه‌کردن یک قابلیت تازه یک
#  تصمیم آگاهانه است، نه چیزی که خودبه‌خود ارث برسد.
# ═══════════════════════════════════════════════════════════

def _tenant_row(tid):
    """یک مستاجر از دیتابیس ربات — فقط خواندن."""
    con = _bot_conn()
    if not con:
        return None
    try:
        r = con.execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()
        return dict(r) if r else None
    except Exception:
        return None
    finally:
        con.close()


#: نشست‌های باز نماینده — توکن به (شناسه‌ی مستاجر، زمان انقضا)
def _portal_open(value):
    """
    آیا پورتالِ این نماینده باز است؟

    فهرست مجاز، نه فهرست ممنوع. سه جا این پرچم را می‌خواندند و هر
    کدام جور دیگری:

      ورود         CAST(... AS INTEGER)=1   — فقط عددِ یک
      بررسی نشست   not in ("0","","None")   — هرچه ناشناخته، باز
      فهرست مدیر   همان فهرست ممنوع

    روی ۰ و ۱ هر سه یک جواب می‌دهند، ولی روی هر مقدار دیگری — ۲،
    "true"، "yes" — ورود می‌بست و نشست باز می‌ماند. یعنی دقیقاً
    برعکسِ چیزی که بالای همان کد نوشته شده بود: «دسترسی همان لحظه
    بسته می‌شود».

    ستون یک‌بار به‌اشتباه TEXT ساخته شده بود و همان یک‌بار کافی بود
    تا هیچ نماینده‌ای نتواند وارد شود. پرچمی که سه جور خوانده شود،
    دیر یا زود همان اتفاق را دوباره می‌سازد.
    """
    if value is None or isinstance(value, bool):
        return value is True
    if isinstance(value, (int, float)):
        return int(value) == 1
    try:
        return int(str(value).strip() or "0") == 1
    except (TypeError, ValueError):
        return False


_PORTAL_SESSIONS = {}


def portal_tenant(x_portal_token: str = Header(None)):
    """
    مستاجرِ نشستِ جاری. هر مسیر نماینده از این رد می‌شود.

    برمی‌گرداند: ردیف کامل مستاجر — تا صداکننده مجبور نباشد شناسه را
    از جای دیگری بگیرد و اشتباهی مستاجر دیگری را بخواند.
    """
    rec = _PORTAL_SESSIONS.get(str(x_portal_token or ""))
    if not rec or rec[1] < _time.time():
        _PORTAL_SESSIONS.pop(str(x_portal_token or ""), None)
        raise HTTPException(status_code=401, detail="نشست منقضی شده — دوباره وارد شوید")

    t = _tenant_row(rec[0])
    if not t or not t.get("is_active") or not _portal_open(
            t.get("portal_enabled")):
        # دسترسی همان لحظه بسته می‌شود، نه سر انقضای نشست.
        _PORTAL_SESSIONS.pop(str(x_portal_token or ""), None)
        raise HTTPException(status_code=403, detail="دسترسی این نماینده بسته شده")
    return t


#: What a reseller reads when this panel's Pro is locked. The owner's license
#: state (grace, clock, payment) is the owner's business, not the reseller's;
#: the reseller's bot keeps selling either way.
RESELLER_LOCKED = "این بخش از پنل نمایندگی فعلاً در دسترس نیست؛ با مدیر فروشگاه تماس بگیرید."


def _reseller_locked(feature):
    if not LIC.allowed(feature):
        raise HTTPException(status_code=403, detail=RESELLER_LOCKED,
                            headers={"X-Nexora-Pro": feature})


def portal_pro_required(feature):
    """portal_tenant, then the license: the reseller-portal twin of
    pro_required. The license check nests inside, so a caller without a
    session gets the portal's own 401 and never learns the license state."""
    LIC.requires(feature)                       # an unknown key fails at startup

    def _dep(t: dict = Depends(portal_tenant)):
        _reseller_locked(feature)
        return t
    return _dep


def portal_login_pro_required(feature):
    """The portal's login has no session yet, so the license alone decides,
    in the reseller's words (portal_pro_required cannot: it needs a session)."""
    LIC.requires(feature)

    def _dep():
        _reseller_locked(feature)
    return _dep


#: What a sales partner reads when this panel's Pro is locked: like the
#: reseller, not the owner's license state. The partner's earned balance is
#: kept; only the app is closed.
PARTNER_LOCKED = "پنل همکاری فعلاً در دسترس نیست؛ با مدیر فروشگاه تماس بگیرید."


def _partner_pro_gate(feature):
    """For the partner app (/api/aff/*). It authenticates with its own session
    inside the endpoint (aff_session), so only the license is added here."""
    LIC.requires(feature)

    def _dep():
        if not LIC.allowed(feature):
            raise HTTPException(status_code=403, detail=PARTNER_LOCKED,
                                headers={"X-Nexora-Pro": feature})
    return _dep



def _bot_username(t):
    """
    نام کاربری ربات — و اگر نبود، یک‌بار از تلگرام بپرس و نگه دار.

    چرا لازم شد: همه‌ی دکمه‌های «برو به ربات» در مینی‌اپ (شارژ کیف
    پول، تمدید، پشتیبانی) لینکِ `t.me/<username>` می‌سازند. این ستون
    فقط وقتی پر می‌شود که توکن از خودِ پنل ثبت شده باشد؛ اگر با
    نصب‌کننده یا CLI تنظیم شده باشد خالی می‌ماند و همه‌ی آن دکمه‌ها
    بی‌صدا بن‌بست می‌شوند — کاربر می‌زند و هیچ اتفاقی نمی‌افتد.

    یک‌بار می‌پرسیم و در همان ستون می‌نشیند، پس دفعه‌ی بعد رایگان
    است.
    """
    u = (t.get("bot_username") or "").strip().lstrip("@")
    if u:
        return u
    tok = t.get("bot_token")
    if not tok:
        return ""
    try:
        ok, who = _tg_get_me(tok)
    except Exception:
        log.warning("getMe برای پرکردن bot_username نشد", exc_info=True)
        return ""
    if not ok or not who:
        return ""
    who = str(who).lstrip("@")
    try:
        con = _bot_rw()
        try:
            con.execute("UPDATE tenants SET bot_username=? WHERE id=?", (who, t["id"]))
            con.commit()
        finally:
            con.close()
    except Exception:
        # نتوانستیم نگه داریم؛ ولی همین حالا جواب را داریم
        log.warning("ذخیره‌ی bot_username نشد", exc_info=True)
    return who


def _ref_count(tid, uid):
    """چند نفر با کدِ این کاربر وارد شده‌اند."""
    con = _bot_conn()
    if not con:
        return 0
    try:
        row = con.execute(
            "SELECT COUNT(*) n FROM users WHERE tenant_id=? AND referred_by=?",
            (tid, uid)).fetchone()
        return int(row["n"] or 0) if row else 0
    except Exception:
        log.debug("شمارشِ دعوت‌ها ناموفق", exc_info=True)
        return 0
    finally:
        con.close()


def _mini_ctx(t):
    """
    زمینه‌ی ربات این مستاجر — برای خرید از داخل مینی‌اپ.

    همان چیزی که `_portal_bot_ctx` برای نماینده می‌سازد. بدون توکن
    ربات نمی‌شود کانفیگ ساخت و به مشتری داد.
    """
    h = _bot_handlers()
    row = _tenant_row(t["id"]) or t
    if not row.get("bot_token"):
        raise HTTPException(status_code=409,
                            detail="ربات این فروشگاه تنظیم نشده")
    return h, h.Ctx(h.Bot(row["bot_token"]), row)


def _portal_group_opt(t):
    """
    گروهِ x-ui این نماینده — یا رشته‌ی خالی.

    چرا جدا از `_portal_group`: آن یکی عمداً خطا می‌دهد، چون
    مسیرهایی که کانفیگ نشان می‌دهند بدونِ گروه نباید هیچ‌چیز نشان
    بدهند (نماینده‌ی نیمه‌ساخته نباید کلِ مشتری‌ها را ببیند).

    ولی **پلنِ رباتِ نماینده کانفیگ نیست.** یک ردیف در جدولِ
    `plans`ِ خودش، برای رباتِ خودش. گره‌زدنش به گروه یعنی نماینده‌ای
    که مالک هنوز گروهش را نگذاشته اصلاً نتواند پلن تعریف کند — و
    پیامی بگیرد که می‌گوید «با پشتیبانی تماس بگیرید».

    گروه فقط برای **کفِ قیمت** لازم است، و نبودنش باید *گفته* شود،
    نه اینکه کلِ صفحه را بیندازد.
    """
    return (t.get("portal_group") or "").strip()


def _portal_group(t):
    """
    گروه x-ui این نماینده. اگر تعریف نشده باشد، هیچ چیزی نشان نمی‌دهیم.

    برگرداندن «همه» وقتی گروه تنظیم نشده، بدترین حالت ممکن است: یک
    نماینده‌ی نیمه‌ساخته کل مشتری‌های سیستم را می‌دید.
    """
    g = (t.get("portal_group") or "").strip()
    if not g:
        raise HTTPException(
            status_code=409,
            detail="گروه این نماینده هنوز تعیین نشده — با پشتیبانی تماس بگیرید")
    return g



# ═══════════════════════════════════════════════════════════
#  پنل نماینده — نوشتن
#
#  تا این‌جا نماینده فقط می‌خواند. از این‌جا به بعد در x-ui می‌نویسد،
#  و x-ui همان جایی است که کانفیگ مشتری‌های واقعی زندگی می‌کند. پس
#  سه قاعده که هیچ‌کدام قابل مذاکره نیست:
#
#    ۱. گروه هرگز از درخواست خوانده نمی‌شود. همیشه از ردیف مستاجر.
#    ۲. هر کانفیگی که قرار است تغییر کند، اول از پنل خوانده می‌شود و
#       گروهش سنجیده می‌شود. اینکه نماینده ایمیلش را فرستاده هیچ
#       چیزی را ثابت نمی‌کند.
#    ۳. کسر اعتبار اتمی است و *قبل* از کار انجام می‌شود؛ اگر کار
#       شکست خورد برمی‌گردد.
# ═══════════════════════════════════════════════════════════

def _panel_row(t):
    """
    ردیفی که اتصالِ x-ui این مستاجر از آن خوانده می‌شود: خودش اگر پنل
    دارد، وگرنه ریشه.

    همین قاعده در ربات هم هست (`bot/db.py: panel_source`) چون دو پردازه‌ی
    جدایند. تا ۱.۸۵ فقط این‌جا بود و رباتِ نماینده به هیچ‌جا وصل
    می‌شد. `test-admin-api` برابریِ این دو را می‌سنجد.
    """
    if t.get("panel_url"):
        return t
    con = _bot_conn()
    try:
        r = con.execute(
            "SELECT * FROM tenants WHERE parent_id IS NULL "
            "ORDER BY id LIMIT 1").fetchone() if con else None
        return dict(r) if r else None
    finally:
        if con:
            con.close()


def _portal_rates(t):
    """
    نرخ‌های گروه این نماینده، از تنظیمات حسابداری.

    بدونِ گروه، فهرستِ خالی — نه خطا. صداکننده خودش تصمیم می‌گیرد
    که این برایش مرگبار است یا فقط یعنی «کف معلوم نیست».
    """
    group = _portal_group_opt(t)
    if not group:
        return {}, []
    con = _billing_conn()
    try:
        r = con.execute("SELECT * FROM group_config WHERE group_key=?",
                        (group,)).fetchone()
        conf = dict(r) if r else {}
    finally:
        con.close()
    try:
        rates = json.loads(conf.get("rates") or "[]")
    except (json.JSONDecodeError, TypeError):
        rates = []
    return conf, (rates if isinstance(rates, list) else [])



# ═══════════════════════════════════════════════════════════
#  ربات شخصی نماینده
#
#  زیرساختش از قبل هست: run.py برای هر مستاجرِ فعال که توکن دارد یک
#  نخ polling جدا می‌سازد، با برند و پنل و مشتری‌های خودش. هر سی
#  ثانیه هم sync_workers نگاه می‌کند چه چیزی تازه اضافه شده.
#
#  پس تنها کاری که این‌جا می‌ماند ثبت توکن است — و مهم‌ترین بخشش
#  این است که توکنِ غلط قبل از ذخیره‌شدن رد شود. توکنی که تایپش
#  اشتباه باشد، رباتی می‌سازد که بالا می‌آید و هیچ‌وقت جواب نمی‌دهد،
#  و نماینده هیچ راهی ندارد بفهمد چرا.
# ═══════════════════════════════════════════════════════════

#: کلیدهایی که نماینده می‌تواند از برندش عوض کند.
#
#  فهرست مجاز، نه ممنوع: settings کلیدهای حساس هم دارد (اتصال پنل،
#  شناسه‌ی گروه مدیریت) و باز گذاشتنش یعنی نماینده می‌تواند چیزهایی
#  را عوض کند که مال او نیست.
PORTAL_BRAND_KEYS = {"brand", "support_username", "channel_username"}


def _tg_get_me(token, timeout=10):
    """
    توکن را از خودِ تلگرام می‌پرسد. برمی‌گرداند: (درست؟, نام کاربری یا پیام)
    """
    import urllib.request
    import urllib.error
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "تلگرام این توکن را نمی‌شناسد"
        return False, f"تلگرام پاسخ نداد (HTTP {e.code})"
    except Exception as e:
        return False, f"تلگرام در دسترس نبود: {type(e).__name__}"
    if not data.get("ok"):
        return False, "تلگرام این توکن را نپذیرفت"
    return True, (data.get("result") or {}).get("username") or ""


def _bot_trial_cap():
    """تستِ فعالِ مالک — سقفِ تستِ نماینده. همان `db.trial_cap` ربات."""
    try:
        return _bot_handlers().DB.trial_cap()
    except Exception:
        log.warning("خواندنِ سقفِ تست ناموفق", exc_info=True)
        return None


# ═══════════════════════════════════════════════════════════
#  پوسته‌ی شخصیِ نماینده — و قفلش
#
#  برگه: docs/specs/2026-09-22-reseller-and-ui.md
#
#  برند و لوگو از قبل بودند؛ تازه: **رنگ**، **پیش‌نمایش**، و
#  اینکه مالک بتواند این قابلیت را پولی کند.
#
#  مبلغ و مدت را **مالک** تعریف می‌کند؛ این‌جا هیچ عددی حدس زده
#  نمی‌شود. صفر یعنی رایگان برای همه.
#
#  پرداخت از همان `tenants.credit` کم می‌شود که از قبل هست — راهِ
#  پرداختِ دومی ساختن یعنی دو جای حسابداری، و این مخزن می‌داند
#  آخرش چه می‌شود.
# ═══════════════════════════════════════════════════════════

#: رنگِ معتبر: فقط `#RRGGBB`. هر چیز دیگری رد می‌شود و پوسته‌ی
#: پیش‌فرض می‌ماند — رنگِ خراب یعنی متنِ نامرئی روی زمینه‌ی هم‌رنگ،
#: همان چیزی که یک‌بار در قالبِ «کیف پول» صفحه‌ی اشتراک افتاد.
_HEX_RE = _re.compile(r"^#[0-9a-fA-F]{6}$")


def _clean_accent(raw):
    """رنگ، یا رشته‌ی خالی. هیچ‌وقت چیزِ نامعتبر برنمی‌گرداند."""
    v = str(raw or "").strip()
    return v.lower() if _HEX_RE.match(v) else ""


# ── پوسته‌ی مینی‌اپ: قالب × پالت × سبکِ لوگو ──
#
# برگه: docs/specs/2026-09-23-mini-theme-studio.md
#
# فهرستِ مجاز، نه دلخواه: شناسه‌ای که رابط نمی‌شناسد، مینی‌اپ را روی
# پیش‌فرض می‌برد و نماینده فکر می‌کند ذخیره نشده. ظاهرِ هر کدام در
# `frontend/src/lib/mini-themes.js` است؛ `test-ui-safety` برابریِ دو
# فهرست را می‌سنجد.
MINI_TEMPLATES = ("aurora", "mono", "bold", "neon")
MINI_PALETTES = ("ocean", "violet", "emerald", "sunset", "rose", "gold",
                 "crimson", "slate", "custom")
# سبکِ صفحه‌ی ورود — همان `MINI_SPLASHES` رابط (test-portal-dashboard)
MINI_SPLASHES = ("bar", "ring", "pulse", "dots", "logo")
LOGO_SHAPES = ("rounded", "circle", "square")
LOGO_BGS = ("none", "light", "accent")


def _clean_logo_style(v):
    """سبکِ لوگو — هر چه نامعتبر است پیش‌فرض می‌شود (همان `cleanLogoStyle` رابط)."""
    v = v if isinstance(v, dict) else {}
    try:
        pad = max(0, min(24, int(round(float(v.get("pad") or 0)))))
    except (TypeError, ValueError):
        pad = 0
    return {"shape": v.get("shape") if v.get("shape") in LOGO_SHAPES else "rounded",
            "bg": v.get("bg") if v.get("bg") in LOGO_BGS else "none",
            "pad": pad}


def _mini_theme(t, st=None):
    """
    پوسته‌ای که مینی‌اپِ این مستاجر واقعاً نشان می‌دهد.

    قفل همین‌جا سنجیده می‌شود: اشتراک که تمام شود پوسته بی‌آنکه پاک
    شود از کار می‌افتد — تا اگر دوباره تهیه کرد، همان برگردد. لوگو
    خودش از این قفل بیرون است (آپلودش از قبل رایگان بود)؛ فقط
    **سبکش** پشتِ قفل است.
    """
    st = st if st is not None else _tenant_settings(t)
    if not _addon_open(t):
        return {"tpl": "aurora", "palette": "", "accent": "",
                "logoStyle": _clean_logo_style({}), "splash": "bar"}
    accent = _clean_accent(st.get("mini_accent"))
    palette = st.get("mini_palette") if st.get("mini_palette") in MINI_PALETTES else ""
    # پیش از قالب‌ها فقط رنگ بود — همان رنگ، پالتِ دلخواه است
    if not palette and accent:
        palette = "custom"
    return {"tpl": st.get("mini_tpl") if st.get("mini_tpl") in MINI_TEMPLATES else "aurora",
            "palette": palette, "accent": accent,
            "logoStyle": _clean_logo_style(st.get("logo_style")),
            "splash": st.get("mini_splash") if st.get("mini_splash") in MINI_SPLASHES else "bar"}


def _bot_core():
    """
    `bot/core.py` — قاعده‌ی افزونه‌های پولی آن‌جاست تا ربات و بکند یکی بخوانند.

    فقط stdlib وارد می‌کند، پس برخلافِ `_bot_handlers` بارشدنش به
    tg/xui/requests بسته نیست. همان شیءِ ماژولی است که handlers می‌گیرد
    (نامِ مسطحِ `core` روی همان مسیر).
    """
    if "core" in _BOT_MODS:
        return _BOT_MODS["core"]
    import sys as _sys
    bot_dir = str(Path(__file__).resolve().parent.parent / "bot")
    if bot_dir not in _sys.path:
        _sys.path.insert(0, bot_dir)
    import core as _c                  # noqa: E402
    _BOT_MODS["core"] = _c
    return _c


def _addon_config(kind="theme"):
    """
    قیمت و مدتِ یک افزونه («theme» پوسته، «store» اشتراکِ فروشگاه) از
    تنظیماتِ مالک: {"price": تومان, "days": روز}. قیمتِ صفر = رایگان برای همه.
    """
    try:
        root = _root_tenant_row()
    except HTTPException:
        return {"price": 0, "days": 30}
    return _bot_core().addon_config(_tenant_settings(root), kind)


def _addon_until(t, kind="theme"):
    """تا کِی این افزونه برای این نماینده باز است؟ ISO یا خالی."""
    return str(_tenant_settings(t).get(_bot_core().ADDONS[kind][1]) or "")


def _addon_open(t, kind="theme"):
    """
    آیا این مستاجر الان این افزونه را دارد؟ قاعده در `core.addon_open`.

    فروشگاهِ خودِ مالک هرگز قفل نیست. پیش‌تر بود: همین که مالک برای
    نماینده‌ها قیمتِ پوسته می‌گذاشت، مینی‌اپِ **خودش** هم به پوسته‌ی
    پیش‌فرض برمی‌گشت — «لوگو و رنگِ شخصی‌سازی‌شده نمی‌آید».
    """
    if not t.get("parent_id"):
        return True
    return _bot_core().addon_open(_tenant_settings(t), t.get("parent_id"),
                                  _addon_config(kind)["price"], kind)


def _addon_blocked(t, kind="theme"):
    """آیا مالک این افزونه را برای این نماینده دستی بسته؟"""
    return bool(t.get("parent_id")) and bool(
        _tenant_settings(t).get(_bot_core().addon_blocked_key(kind)))


def _theme_get(t):
    """
    پوسته‌ی مینی‌اپِ یک فروشگاه — همان برای نماینده (پرتال) و مالک (پنل).

    مالک تا ۱.۱۰۹ هیچ راهی برای شخصی‌سازیِ مینی‌اپِ **خودش** نداشت: استودیو
    فقط در پرتالِ نماینده بود. حالا هر دو از همین‌جا می‌خوانند.
    """
    st = _tenant_settings(t)
    cfg = _addon_config()
    return {
        "accent": _clean_accent(st.get("mini_accent")),
        # آنچه ذخیره شده — حتی اگر قفل بسته باشد، تا رابط نشانش بدهد
        "tpl": st.get("mini_tpl") if st.get("mini_tpl") in MINI_TEMPLATES else "aurora",
        "palette": (st.get("mini_palette") if st.get("mini_palette") in MINI_PALETTES
                    else ("custom" if _clean_accent(st.get("mini_accent")) else "ocean")),
        "logoStyle": _clean_logo_style(st.get("logo_style")),
        "splash": st.get("mini_splash") if st.get("mini_splash") in MINI_SPLASHES else "bar",
        "brand": st.get("brand") or t.get("name") or "",
        "logo": _logo_url(t["id"]),
        "open": _addon_open(t),
        "until": _addon_until(t),
        "blocked": _addon_blocked(t),
        "price": cfg["price"],
        "days": cfg["days"],
        "credit": int(t.get("credit") or 0),
        # اعتبارِ منفی یعنی «پس‌پرداخت» — آخر ماه صورتحساب می‌آید
        "postpaid": int(t.get("credit") or 0) < 0,
    }


def _theme_save(t, payload):
    """ذخیره‌ی پوسته — مشترکِ پرتال و پنلِ مالک. قفل همین‌جاست."""
    if not _addon_open(t):
        raise HTTPException(
            status_code=402,
            detail="پوسته‌ی شخصی برای شما فعال نیست — اول تهیه‌اش کنید")

    p = payload or {}
    st = _tenant_settings(_tenant_row(t["id"]) or t)

    # فقط آنچه آمده عوض می‌شود — رابطِ قدیمی که فقط رنگ می‌فرستاد
    # نباید قالب و لوگو را پاک کند.
    if "accent" in p:
        accent = _clean_accent(p.get("accent"))
        if p.get("accent") and not accent:
            raise HTTPException(status_code=400,
                                detail="رنگ باید به شکل ‎#RRGGBB باشد")
        st["mini_accent"] = accent
    if "tpl" in p:
        if p.get("tpl") not in MINI_TEMPLATES:
            raise HTTPException(status_code=400, detail="این قالب وجود ندارد")
        st["mini_tpl"] = p["tpl"]
    if "palette" in p:
        if p.get("palette") not in MINI_PALETTES:
            raise HTTPException(status_code=400, detail="این پالت وجود ندارد")
        if p["palette"] == "custom" and not _clean_accent(st.get("mini_accent")):
            raise HTTPException(status_code=400,
                                detail="برای رنگِ دلخواه اول یک رنگ انتخاب کنید")
        st["mini_palette"] = p["palette"]
    if "logo_style" in p:
        st["logo_style"] = _clean_logo_style(p.get("logo_style"))
    if "splash" in p:
        # ناشناس ۴۰۰ است، نه «نوار» بی‌صدا — وگرنه انتخاب ذخیره شده به نظر
        # می‌رسید و مشتری چیزِ دیگری می‌دید
        if p.get("splash") not in MINI_SPLASHES:
            raise HTTPException(status_code=400, detail="این سبکِ صفحه‌ی ورود وجود ندارد")
        st["mini_splash"] = p["splash"]

    _save_tenant_settings(t["id"], st)
    return {"ok": True, "accent": _clean_accent(st.get("mini_accent")),
            "theme": _mini_theme(_tenant_row(t["id"]) or t, st)}


def _brand_save(t, payload):
    """نام و برندِ فروشگاه — فقط کلیدهای `PORTAL_BRAND_KEYS`؛ مشترکِ پرتال و مالک."""
    p = payload or {}
    try:
        st = json.loads(t.get("settings") or "{}")
    except (json.JSONDecodeError, TypeError):
        st = {}
    if not isinstance(st, dict):
        st = {}

    touched = []
    for k in PORTAL_BRAND_KEYS:
        if k in p:
            st[k] = str(p[k] or "").strip()[:80]
            touched.append(k)
    if not touched:
        raise HTTPException(status_code=400, detail="چیزی برای تغییر نیست")

    con = _bot_rw()
    try:
        con.execute("UPDATE tenants SET settings=? WHERE id=?",
                    (json.dumps(st, ensure_ascii=False), t["id"]))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


#: «نامحدود» برای کفِ حجمی چند گیگ حساب شود، اگر مالک عددی نگذاشته
UNLIMITED_GB_DEFAULT = 200


def _unlimited_gb():
    """نامحدود = چند گیگ (کف و سقفِ فروشگاه‌های حجمی). قاعده در `core.unlimited_gb`."""
    try:
        return _bot_core().unlimited_gb(_tenant_settings(_root_tenant_row()))
    except HTTPException:
        return UNLIMITED_GB_DEFAULT


def _plan_floor(conf, rates, gb, days, ips):
    """
    کفِ یک پلن — همان عددی که پیش‌نمایش نشان می‌دهد و همان که
    موقعِ ذخیره در `plans.cost` می‌نشیند.

    یک تابع، چون دو مصرف‌کننده دارد: اگر پیش‌نمایش و ذخیره هر کدام
    جدا حساب کنند، نماینده یک کف می‌بیند و از اعتبارش کفِ دیگری کم
    می‌شود.

    **نرخِ حجمی:** وقتی مالک با نماینده روی «هر گیگ» توافق کرده، کف
    حجمِ پلن × نرخِ هر گیگ است — مالک: «گیگی ۳ هزار، ۳۰ گیگ می‌شود ۹۰».
    تا ۱.۱۱۴ این حالت فقط پله‌ها (`rates`) را می‌دید؛ گروهی که فقط نرخِ
    حجمی داشت اصلاً کفی نداشت و هر قیمتی، حتی صفر، ذخیره می‌شد. ماه ضرب
    نمی‌شود: حجمِ پلن سقفِ کلِ دوره است، نه ماهانه. کاربرِ اضافه هم
    چیزی اضافه نمی‌کند — نرخِ حجمی به مصرف است، نه به تعدادِ دستگاه.
    """
    per_gb = _price_per_gb(conf or {})
    # A mixed volume group prices unlimited configs at a rate (task 5): an
    # unlimited plan's floor is that rate, like a rated group's.
    if per_gb and not (gb <= 0 and _volume_mixed(conf)):
        # «نامحدود» این فروشگاه در عمل سقفِ منصفانه دارد — مالک: «نامحدودی
        # که ما تعریف می‌کنیم ۲۰۰ گیگ است». پس کفِ پلنِ نامحدود همان حجم ×
        # نرخ است، نه «نامعلوم». عدد را مالک در «قابلیت‌های نماینده‌ها» عوض
        # می‌کند (`_unlimited_gb`).
        unl = gb <= 0
        eff = _unlimited_gb() if unl else int(gb)
        return {
            "ready": True,
            "cost": eff * per_gb,
            # کف فقط برای قیمت‌گذاری است؛ با فروش از اعتبار کم نمی‌شود —
            # بدهیِ حجمی از مصرفِ واقعی می‌آید (`_volume_bill`). مالک: «اگر
            # ۳۰ گیگ مصرف کرده باشد، پولِ همان را می‌گیریم».
            "charge": 0,
            "base": per_gb,
            "perGb": per_gb,
            "gb": eff,
            "unlimited": unl,
            "perDevice": 0, "extraDevices": 0, "months": 1,
            "estimated": False,
        }

    base, why = _price_with_reason(gb, rates)
    if base is None:
        # صفر برنمی‌گردانیم: صفر یعنی «رایگان است» و این یعنی
        # «نمی‌دانیم». نماینده باید تفاوتشان را ببیند.
        return {"ready": False, "why": why}

    months = _months_from_days(days) if days else 1
    cost, base2, per, extra = _line_amount(gb, rates, months, ips)
    return {
        "ready": True,
        "cost": int(cost or 0),
        "base": int(base2 or 0),
        "perDevice": int(per or 0),
        "extraDevices": int(extra or 0),
        "months": int(months),
        # پلنِ بی‌انقضا چند ماه می‌ماند معلوم نیست؛ یک ماه
        # حساب می‌شود و همین‌جا گفته می‌شود که تخمین است.
        "estimated": not days,
    }


def _refresh_plan_costs(group_key=None):
    """
    `plans.cost` هر نماینده را از نرخِ **امروزِ** مالک دوباره می‌سازد.

    کف موقعِ ذخیره‌ی پلن حساب می‌شود، ولی نرخ مالِ مالک است و هر وقت
    بخواهد عوضش می‌کند. بدونِ این، نرخ بالا می‌رفت و ربات همچنان کفِ
    قدیمی را از اعتبارِ نماینده‌ی پیش‌پرداخت کم می‌کرد — و پلن‌هایی که
    پیش از ۱.۸۶ ذخیره شده‌اند اصلاً کفی نداشتند.

    دو جا صدا زده می‌شود: بعد از ذخیره‌ی نرخِ یک گروه، و یک‌بار موقعِ
    بالاآمدن. برمی‌گرداند: چند پلن عوض شد.
    """
    con = _bot_rw()
    changed = 0
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(plans)")}
        if "cost" not in cols:
            con.execute("ALTER TABLE plans ADD COLUMN cost INTEGER DEFAULT 0")
        sql = ("SELECT * FROM tenants WHERE parent_id IS NOT NULL "
               "AND COALESCE(portal_group,'')<>''")
        args = ()
        if group_key:
            sql += " AND portal_group=?"
            args = (group_key,)
        cap_gb = _unlimited_gb()
        for r in con.execute(sql, args).fetchall():
            t = dict(r)
            conf, rates = _portal_rates(t)
            # ربات به billing.db دسترسی ندارد؛ پس «این فروشگاه حجمی است و
            # نامحدودش چند گیگ است» همین‌جا در تنظیماتِ خودش می‌نشیند
            # (`core.unlimited_cap`). هر بار که نرخ یا «نامحدود» عوض شود و
            # موقعِ بالاآمدن، دوباره نوشته می‌شود.
            try:
                st = json.loads(t.get("settings") or "{}")
                st = st if isinstance(st, dict) else {}
            except (json.JSONDecodeError, TypeError):
                st = {}
            # A mixed group sells real unlimited configs at their rate (task
            # 5), so its bot gets no "unlimited = N GB" cap.
            want = cap_gb if _price_per_gb(conf) and not _volume_mixed(conf) else None
            if st.get("unlimited_cap_gb") != want:
                if want:
                    st["unlimited_cap_gb"] = want
                else:
                    st.pop("unlimited_cap_gb", None)
                con.execute("UPDATE tenants SET settings=? WHERE id=?",
                            (json.dumps(st, ensure_ascii=False), t["id"]))
            for p in con.execute(
                    "SELECT id, gb, days, ip_limit, cost FROM plans "
                    "WHERE tenant_id=? AND COALESCE(is_trial,0)=0",
                    (t["id"],)).fetchall():
                fl = (_plan_floor(conf, rates, int(p["gb"] or 0), int(p["days"] or 0),
                                  int(p["ip_limit"] or 0))
                      if rates or _price_per_gb(conf) else {})
                new = int(fl.get("charge", fl.get("cost")) or 0) if fl.get("ready") else 0
                if new != int(p["cost"] or 0):
                    con.execute("UPDATE plans SET cost=? WHERE id=? AND tenant_id=?",
                                (new, p["id"], t["id"]))
                    changed += 1
        con.commit()
    finally:
        con.close()
    if changed:
        log.info("کفِ %s پلنِ نماینده با نرخِ تازه همگام شد", changed)
    return changed



# ═══════════════════════════════════════════════════════════
#  سفارش‌های نماینده — رسید و تایید
#
#  مشتریِ نماینده از رباتِ *او* سفارش می‌دهد و رسید می‌فرستد. تا
#  امروز تنها جایی که می‌شد تاییدش کرد گروه مدیریت تلگرام بود؛ اگر
#  نماینده گروه نداشت، سفارش برای همیشه در انتظار می‌ماند.
#
#  تاییدکردن یعنی: پول گرفته شده، کانفیگ ساخته شود، مشتری خبردار
#  شود. همان کاری که ربات می‌کند — و عمداً *همان کد* را صدا می‌زنیم،
#  نه یک نسخه‌ی دوم. مسیر پول دو پیاده‌سازی برنمی‌دارد؛ هر اصلاحی که
#  به یکی برسد و به دیگری نه، یک باگ بی‌صداست.
# ═══════════════════════════════════════════════════════════

_BOT_MODS = {}


def _bot_handlers():
    """
    ماژول handlers ربات، با bot/ روی مسیر.

    handlers با نام‌های مسطح import می‌کند (core، db، tg)، پس تا وقتی
    آن پوشه روی sys.path نباشد بارگذاری نمی‌شود.
    """
    if "handlers" in _BOT_MODS:
        return _BOT_MODS["handlers"]
    import sys as _sys
    bot_dir = str(Path(__file__).resolve().parent.parent / "bot")
    if bot_dir not in _sys.path:
        _sys.path.insert(0, bot_dir)
    try:
        import handlers as _h          # noqa: E402
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"منطق ربات بارگذاری نشد: {type(e).__name__}")
    _BOT_MODS["handlers"] = _h
    return _h



@app.post("/api/admin/bot/brand")
def admin_brand_set(payload: dict, x_admin_password: str = Header(...)):
    check_auth(x_admin_password)
    return _brand_save(_root_tenant_row(), payload)


@app.post("/api/admin/bot/logo")
def admin_logo_set(payload: dict, x_admin_password: str = Header(...)):
    check_auth(x_admin_password)
    return _logo_save(_root_tenant_row()["id"], payload)


@app.delete("/api/admin/bot/logo")
def admin_logo_clear(x_admin_password: str = Header(...)):
    check_auth(x_admin_password)
    _logo_clear(_root_tenant_row()["id"])
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}



# ── Pro areas ── docs/specs/2026-09-29-pro-split.md ──────────────────────
# Last in the module, so every core helper Pro code calls already exists.
# Loaded by path as `nexora_pro_api`: bot/ has a `pro` folder too, and a bare
# `import pro` would find whichever sys.path lists first.
PRO_API_DIR = Path(os.getenv("NEXORA_PRO_API_DIR",
                             str(Path(__file__).resolve().parent / "pro")))
PRO_LOADED = False
PRO_ERROR = ""
# This app's own Pro package. Not sys.modules["nexora_pro_api"]: a second load
# of app.py in one process (several tests do it) replaces that entry, and the
# first app's code would then read the second one's module.
PRO_API = None


class _Core:
    """What Pro code sees as `core`: this module, looked up live. A snapshot
    would miss a helper that a test (or a later startup hook) replaces."""

    def __getattr__(self, name):
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(name) from None


def _customer_pro_gate(feature):
    """For routes the shop's customers call (the mini app): locked Pro answers
    in the customer's words. The owner's license message is not theirs to
    read, and the bot menu does everything the mini app does."""
    def _dep():
        if not LIC.allowed(feature):
            raise HTTPException(status_code=403,
                                detail="این بخش فعلاً در دسترس نیست؛ از منوی ربات استفاده کنید.",
                                headers={"X-Nexora-Pro": feature})
    return _dep


class _GatedApp:
    """`app` as seen by Pro code that runs in this namespace: every route it
    declares gets the license gate of the feature its path maps to. Admin
    routes check the password first (pro_required); portal routes the portal
    session (portal_pro_required). Agent routes authenticate inside the
    endpoint, so for them only the license is added here."""

    def __init__(self, real):
        self._real = real

    def _gate(self, path):
        feature = LIC.pro_feature_of(path)
        if feature is None:
            raise RuntimeError(f"Pro route {path} maps to no feature (license.PRO_PATHS); "
                               "refusing to register it ungated")
        if path.startswith("/api/portal/") and path.endswith("/login"):
            return portal_login_pro_required(feature)
        if path.startswith("/api/portal/"):
            return portal_pro_required(feature)
        # The agent and the shop's SMS forwarder authenticate inside the
        # endpoint (signed request / the address's own token); neither can
        # send the admin password. With pro_required the phone's every SMS
        # was a 422 and nothing ever arrived (2.3.0, 2026-10-07).
        if path.startswith(("/api/agent/", "/api/sms/")):
            return LIC.requires(feature)
        if path.startswith("/api/mini/"):
            return _customer_pro_gate(feature)
        if path.startswith("/api/aff/"):
            return _partner_pro_gate(feature)
        return pro_required(feature)

    def __getattr__(self, name):
        real = getattr(self._real, name)
        if name not in ("get", "post", "put", "delete", "patch"):
            return real

        def route(path, *a, **kw):
            kw["dependencies"] = [Depends(self._gate(path))] + list(kw.get("dependencies") or [])
            return real(path, *a, **kw)
        return route


def _exec_pro_namespace(path):
    """Run a Pro file moved verbatim from this module, in this module's
    namespace. It may add names, never rebind one: a Pro file that silently
    replaced a core helper would change the core for everyone."""
    g = globals()
    before = dict(g)
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    g["app"] = _GatedApp(app)
    try:
        exec(code, g)
    finally:
        g["app"] = before["app"]
    clash = [k for k, v in before.items() if not k.startswith("__") and g.get(k) is not v]
    for k in clash:
        g[k] = before[k]
    if clash:
        raise RuntimeError(f"{path.name} rebinds core names: {', '.join(sorted(clash))}")


def _load_pro():
    global PRO_LOADED, PRO_ERROR, PRO_API
    init = PRO_API_DIR / "__init__.py"
    if not init.is_file():
        return                                  # Community edition
    import importlib.util as _ilp
    import sys as _sysp
    # Fresh submodules for every load. Otherwise a second app.py in the same
    # process (tests load it more than once) gets the first load's
    # `nexora_pro_api.insights` back from `from . import ...`, registers it
    # again, and both apps' Pro routes end up reading the second app.
    for _k in [k for k in _sysp.modules if k == "nexora_pro_api" or k.startswith("nexora_pro_api.")]:
        del _sysp.modules[_k]
    try:
        spec = _ilp.spec_from_file_location("nexora_pro_api", init,
                                            submodule_search_locations=[str(PRO_API_DIR)])
        mod = _ilp.module_from_spec(spec)
        _sysp.modules["nexora_pro_api"] = mod
        spec.loader.exec_module(mod)
        mod.register(app, _Core())
        for fname in getattr(mod, "NAMESPACE", ()):
            _exec_pro_namespace(PRO_API_DIR / fname)
        PRO_API, PRO_LOADED = mod, True
    except Exception as e:
        # The core keeps running; the license card shows this. Pro code that
        # is present but silently not running is the worst of both editions.
        PRO_ERROR = f"{type(e).__name__}: {e}"[:300]
        log.exception("Pro code failed to load")


_load_pro()

