"""
رویدادهای ربات — یک تعریف، دو مصرف‌کننده.

چرا این فایل جداست و نه دو دیکشنری در دو جا:
    نگاشتِ «نوعِ رویداد → متنِ فارسی» هم در ربات لازم است (برای
    پیامِ گروه) و هم در پنل (برای فهرست). همین شکلِ «یک قاعده، دو
    جا» هفت بار در این مخزن باگ شده. پس یک تعریف این‌جا می‌ماند،
    ربات مستقیم و پنل از راهِ API می‌خواندش.

چرا تابعِ خالص و بدون دیتابیس:
    تا بدونِ FastAPI و بدونِ sqlite تست شود. همان کاری که
    `ideas.py` و `fmt.py` می‌کنند.
"""

#: سقفِ ردیف در هر مستاجر. `tunnels.py` پانصد نگه می‌دارد، این‌جا
#: بیشتر: رباتِ پرفروش روزی ده‌ها رویداد دارد و مالک باید بتواند
#: ماهِ قبل را هم ببیند.
MAX_ROWS = 5000

#: هر نوعِ رویداد: برچسبِ فارسی، شدت، و اینکه گروهِ مدیریت همان
#: لحظه خبر شود یا نه.
#:
#: `alert` فقط برای چیزهایی روشن است که **پولِ مشتری** را معلق
#: می‌گذارند. اگر همه چیز هشدار بدهد، هیچ چیز هشدار نیست — گروه
#: پر می‌شود و مالک یاد می‌گیرد نگاهش نکند.
KINDS = {
    # ── پول معلق مانده: گروه باید همان لحظه بفهمد ──
    "provision_failed": {
        "label": "ساختِ کانفیگ ناموفق",
        "level": "error", "alert": True,
    },
    "deliver_failed": {
        "label": "کانفیگ ساخته شد ولی به مشتری نرسید",
        "level": "error", "alert": True,
    },
    "order_deliver_failed": {
        "label": "تحویلِ سفارشِ تاییدشده ناموفق",
        "level": "error", "alert": True,
    },
    "renew_failed": {
        "label": "تمدید خودکار ناموفق",
        "level": "error", "alert": True,
    },

    # ── خراب است ولی پولی معلق نیست: فقط در فهرست ──
    "usage_failed": {
        "label": "خواندنِ مصرف از پنل ناموفق",
        "level": "error", "alert": False,
    },
    "reminder_failed": {
        "label": "ارسالِ یادآوریِ انقضا ناموفق",
        "level": "error", "alert": False,
    },
    "traffic_warn_failed": {
        "label": "ارسالِ هشدارِ حجم ناموفق",
        "level": "error", "alert": False,
    },
    "channel_failed": {
        "label": "ارسالِ پستِ کانال ناموفق",
        "level": "error", "alert": False,
    },
    "winback_failed": {
        "label": "پیگیریِ تست ناموفق",
        "level": "error", "alert": False,
    },
    "report_failed": {
        "label": "گزارشِ روزانه ناموفق",
        "level": "error", "alert": False,
    },
    "token_invalid": {
        "label": "توکن ربات نامعتبر شد و ربات غیرفعال شد",
        "level": "error", "alert": False,
    },
    "scheduler_failed": {
        "label": "خطا در زمان‌بند",
        "level": "error", "alert": False,
    },
    # A paid order's payout (partner commission, referrer coins) that could
    # not be written: money owed to someone, so it is listed, not only logged.
    "payout_failed": {
        "label": "پورسانت یا پاداشِ یک فروش ثبت نشد",
        "level": "error", "alert": False,
    },
    # Pro locked when the order was paid: not paid, and not paid later either.
    "payout_skipped": {
        "label": "Pro قفل بود؛ پورسانت یا پاداشِ این فروش داده نشد",
        "level": "warn", "alert": False,
    },

    # The hourly config sweep (backend/app.py `_sub_lifecycle_tick`). These
    # were written to the list without a label, so the owner saw an hourly
    # "unknown event" and no way to tell that the sweep had stopped itself.
    "sub_sweep_skipped": {
        "label": "پاک‌سازیِ ساعتی انجام نشد: بیشترِ کانفیگ‌ها در پنل پیدا نشدند و پنل هم جواب نداد",
        "level": "warn", "alert": False,
    },
    "sub_delete_failed": {
        "label": "پاک‌کردنِ کانفیگِ تمدیدنشده ناموفق",
        "level": "error", "alert": False,
    },
    "sub_gone": {
        "label": "کانفیگ در پنل حذف شده بود؛ از ربات هم برداشته شد",
        "level": "info", "alert": False,
    },
    "sub_back": {
        "label": "کانفیگی که «در پنل نیست» علامت خورده بود دوباره در 3x-ui پیدا شد و برگشت",
        "level": "info", "alert": False,
    },
    "sub_deleted": {
        "label": "کانفیگِ تمدیدنشده پاک شد",
        "level": "info", "alert": False,
    },

    # ── اتفاق‌های عادی، برای اینکه فهرست فقط خطا نباشد ──
    "provision": {
        "label": "کانفیگ ساخته شد",
        "level": "ok", "alert": False,
    },
    "user_back": {
        "label": "کاربری که پیش‌تر ربات را بلاک کرده بود برگشت و دوباره پذیرفته شد",
        "level": "info", "alert": False,
    },
    "user_blocked": {
        "label": "کاربر مسدود شد",
        "level": "warn", "alert": False,
    },
    "user_unblocked": {
        "label": "مسدودیِ کاربر برداشته شد",
        "level": "info", "alert": False,
    },
    "user_restored": {
        "label": "کاربرِ حذف‌شده یا مسدود بازگردانده شد",
        "level": "info", "alert": False,
    },
    "user_deleted": {
        "label": "کاربر حذف شد و کانفیگ‌هایش پاک شد",
        "level": "warn", "alert": False,
    },
    "signup": {
        "label": "کاربر تازه",
        "level": "info", "alert": False,
    },
    "owner_linked": {
        "label": "صاحبِ فروشگاه به ربات وصل شد",
        "level": "info", "alert": False,
    },
}

#: نوعی که در `KINDS` نباشد. بی‌صدا دور انداخته نمی‌شود — با همین
#: برچسب نشان داده می‌شود تا معلوم شود یک‌جا نوعِ تازه‌ای اضافه شده
#: و این فهرست به‌روز نشده.
UNKNOWN = {"label": "رویدادِ ناشناخته", "level": "warn", "alert": False}


def meta(kind):
    """مشخصاتِ یک نوع. هیچ‌وقت None برنمی‌گرداند."""
    return KINDS.get(kind, UNKNOWN)


def is_alert(kind):
    return bool(meta(kind).get("alert"))


def label(kind):
    return meta(kind)["label"]


def level(kind):
    return meta(kind)["level"]


#: سطح‌هایی که «خطا» شمرده می‌شوند — فیلترِ «فقط خطاها» از همین
#: می‌خواند، نه از فهرستی که جدا نوشته شده باشد.
ERROR_LEVELS = ("error",)


def is_error(kind):
    return level(kind) in ERROR_LEVELS


def describe(kind, data=None):
    """
    یک خطِ فارسیِ خوانا از رویداد.

    `data` هرچه باشد اضافه می‌شود ولی **کوتاه**: متنِ خطای خام
    گاهی چند کیلوبایت است و ردیفِ جدول را می‌ترکاند.
    """
    d = data if isinstance(data, dict) else {}
    out = label(kind)

    bits = []
    if d.get("order"):
        bits.append(f"سفارش #{d['order']}")
    if d.get("sub"):
        bits.append(f"اشتراک #{d['sub']}")
    if d.get("post"):
        bits.append(f"پست #{d['post']}")
    if d.get("email"):
        bits.append(str(d["email"])[:64])
    if d.get("missing") and d.get("of"):
        bits.append(f"{d['missing']} از {d['of']} کانفیگ")
    if bits:
        out += ": " + " · ".join(bits)

    err = d.get("error")
    if err:
        out += f" · {str(err)[:200]}"
    return out


def alert_text(kind, data=None, who=None):
    """
    متنِ پیامِ گروه. HTML، چون `notify_group` همان را می‌فرستد.

    بدونِ `esc` این‌جا: تنها ورودیِ کنترل‌نشده `error` و `who` است و
    هر دو در خودِ صداکننده esc می‌شوند. این تابع فقط چیدمان است.
    """
    d = data if isinstance(data, dict) else {}
    head = f"⚠️ <b>{label(kind)}</b>"
    lines = [head, ""]
    if who:
        lines.append(f"مشتری: {who}")
    if d.get("order"):
        lines.append(f"سفارش: <code>#{d['order']}</code>")
    if d.get("sub"):
        lines.append(f"اشتراک: <code>#{d['sub']}</code>")
    if d.get("error"):
        lines.append(f"<code>{str(d['error'])[:200]}</code>")
    return "\n".join(lines)
