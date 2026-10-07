"""
نقطه‌ی شروع ماژول ربات Nexora.

این فایل دو کار می‌کند:
  ۱. برای هر مستاجر فعال، یک حلقه‌ی polling تلگرام اجرا می‌کند
  ۲. یک زمان‌بند برای کارهای دوره‌ای (یادآوری، تمدید خودکار، بک‌آپ)

اجرا:
    python3 -m bot.run

متغیرهای محیطی:
    BOT_DB_PATH   مسیر دیتابیس (پیش‌فرض ../data/bot.db)
    BOT_LOG_LEVEL INFO | DEBUG
"""
import contextlib
import logging
import os
import secrets
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import db, core, handlers
from bot.tg import Bot, TelegramError, kb

log = logging.getLogger("nexora.bot")

_stop = threading.Event()
_workers = {}          # tenant_id → Thread
_lock = threading.Lock()

#: چند آپدیت هم‌زمان برای هر مستاجر.
#: هشت یعنی هشت کاربر می‌توانند هم‌زمان کانفیگ بگیرند بدون
#: اینکه منتظر هم بمانند؛ بالاتر از این، محدودیت نرخ تلگرام
#: و پنل 3x-ui گلوگاه می‌شوند نه ما.
POOL_SIZE = int(os.getenv("BOT_POOL_SIZE", "8"))


#: بالای این تعداد چت، قدیمی‌ها هرس می‌شوند.
CHAT_LOCK_LIMIT = int(os.getenv("BOT_CHAT_LOCKS", "5000"))


class ChatLocks:
    """
    یک قفل برای هر چت — و تضمینِ اینکه هرس، قفلی را که دستِ کسی است
    برندارد.

    چرا این تضمین لازم است:
        نسخه‌ی قبلی قفل را داخل نگهبان برمی‌داشت، نگهبان را رها
        می‌کرد، و *بعد* قفل را می‌گرفت. بین این دو لحظه، قفل در
        جدول بود ولی هنوز `locked()` نبود — و شرط هرس دقیقاً همان
        `not v.locked()` بود.

        پس آپدیتِ دیگری از چتی دیگر می‌توانست وسط همین فاصله جدول
        را هرس کند و همان قفل را بردارد. آپدیت بعدیِ همان چت، قفلِ
        *تازه‌ای* می‌ساخت و دو پردازش هم‌زمان روی یک چت اجرا می‌شدند.

        قفلِ هر چت تنها چیزی است که جلوی دوباره‌پردازش‌شدن یک کاربر
        را می‌گیرد. این یعنی دقیقاً بالای پنج هزار چت — یعنی وقتی
        ربات شلوغ است و احتمال دو آپدیت هم‌زمان بیشترین است — آن
        محافظت بی‌صدا از کار می‌افتاد.

    حالا هر ردیف یک شمارنده دارد: تا کسی آن را در دست دارد یا در
    صفِ گرفتنش است، هرس نمی‌شود.
    """

    def __init__(self, limit=None):
        self._limit = int(limit or CHAT_LOCK_LIMIT)
        self._locks = {}           # cid → [Lock, شمارنده]
        self._guard = threading.Lock()

    @contextlib.contextmanager
    def hold(self, cid):
        with self._guard:
            ent = self._locks.get(cid)
            if ent is None:
                ent = self._locks[cid] = [threading.Lock(), 0]
            ent[1] += 1
            if len(self._locks) > self._limit:
                # شمارنده‌ی خودِ این چت الان دست‌کم یک است، پس شرط
                # پایین آن را هم کنار می‌گذارد — بدون نیاز به استثنا.
                for k in [k for k, v in list(self._locks.items())
                          if v[1] == 0][:self._limit // 2]:
                    self._locks.pop(k, None)
        try:
            with ent[0]:
                yield
        finally:
            with self._guard:
                ent[1] -= 1

    def size(self):
        with self._guard:
            return len(self._locks)


def _event(tid, kind, user_id=None, data=None, who=None):
    """
    ثبتِ رویدادِ زمان‌بند، و اگر پولی معلق است خبرکردنِ گروه.

    چرا این‌جا یک تابع است و نه `d.log(...)` در نُه جای شکست:
        هر جای شکست که خودش تصمیم بگیرد «گروه را خبر کنم یا نه»،
        دهمی فراموشش می‌کند. تصمیم مالِ `events.KINDS` است.

    و چرا مستاجر و ربات را خودش می‌سازد: در چند جای شکست، `tenant`
    یا `tg` هنوز ساخته نشده‌اند — خطا دقیقاً موقعِ ساختنشان بوده.
    اتکا به متغیرِ محلی آن‌جا `NameError` می‌دهد و خطای اصلی را
    گم می‌کند.

    هیچ‌وقت خطا بالا نمی‌برد.
    """
    try:
        d = db.TenantDB(tid)
    except Exception:
        log.debug("ثبت رویداد ناموفق (%s)", kind, exc_info=True)
        return

    if not handlers.EV.is_alert(kind):
        d.log(kind, user_id, data)
        return

    # هشدار لازم است: `handlers.record` هم ثبت می‌کند هم می‌فرستد.
    try:
        t = db.get_tenant(tid)
        if t and t.get("bot_token"):
            handlers.record(handlers.Ctx(Bot(t["bot_token"]), t),
                            kind, user_id, data, who=who)
            return
    except Exception:
        log.debug("هشدار گروه ناموفق (%s)", kind, exc_info=True)
    # ربات در دسترس نبود — دست‌کم ردیفِ جدول ثبت شود
    d.log(kind, user_id, data)


def chat_id_of(update):
    """شناسه‌ی چتِ یک آپدیت — پیام یا دکمه‌ی شیشه‌ای."""
    msg = (update.get("message") or update.get("callback_query", {})
           .get("message") or {})
    cid = (msg.get("chat") or {}).get("id")
    if cid is None:
        cid = ((update.get("callback_query") or {}).get("from")
               or {}).get("id", 0)
    return cid


# ═══════════════════════════════════════════════════════════
#  حلقه‌ی هر مستاجر
# ═══════════════════════════════════════════════════════════

def _sync_menu_button(tenant, tg, name):
    """
    دکمه‌ی کنار کادر تایپ را خودِ ربات تنظیم می‌کند.

    چرا این‌جا و نه با دست در BotFather: تنظیمی که باید آدم انجامش
    بدهد، انجام نمی‌شود — و آن‌وقت قابلیتی داریم که ساخته شده و هیچ‌کس
    نمی‌بیندش. همان چیزی که سر پنل نمایندگی افتاد.

    هر بار که نخِ مستاجر بالا می‌آید یک‌بار صدا زده می‌شود، نه در هر
    دور حلقه. اگر آدرس عوض شود، ریستارتِ بعدی جاش می‌اندازد.

    شکستش نباید ربات را متوقف کند: دکمه‌ی منو راحتی است، نه شرطِ کار
    کردن. همه‌ی کارها از منوی درون‌پیام هم در دسترس‌اند.
    """
    try:
        url = handlers.miniapp_url(handlers.Ctx(tg, tenant))
    except Exception:
        log.debug("%s: ساختن آدرس مینی‌اپ ناموفق", name, exc_info=True)
        return

    try:
        if url:
            tg.call("setChatMenuButton", menu_button={
                "type": "web_app", "text": "اپلیکیشن",
                "web_app": {"url": url},
            })
            log.info("%s: دکمه‌ی مینی‌اپ روی %s تنظیم شد", name, url)
        else:
            # آدرسی نیست — دکمه‌ی قبلی باید برداشته شود، وگرنه به
            # صفحه‌ای اشاره می‌کند که دیگر بالا نمی‌آید
            tg.call("setChatMenuButton", menu_button={"type": "commands"})
    except Exception as e:
        log.warning("%s: تنظیم دکمه‌ی مینی‌اپ ناموفق: %s", name, str(e)[:120])


def tenant_loop(tenant_id: int):
    """
    حلقه‌ی polling یک مستاجر.

    اگر توکن نامعتبر شود یا مستاجر غیرفعال شود، حلقه تمیز خارج می‌شود.
    خطاهای موقت شبکه باعث توقف نمی‌شوند — با backoff دوباره تلاش می‌کند.
    """
    offset = 0
    backoff = 1
    tg = None
    name = f"tenant-{tenant_id}"

    # ── چرا اینجا استخر نخ داریم ──
    #
    # قبلاً آپدیت‌ها یکی‌یکی و پشت‌سرهم پردازش می‌شدند. ساخت کانفیگ
    # در 3x-ui چند ثانیه طول می‌کشد (لاگین، افزودن کلاینت، بازخوانی،
    # گرفتن لینک) و در تمام آن مدت *هیچ* پیام دیگری پردازش نمی‌شد.
    # با ده کاربر هم‌زمان، نفر دهم ده‌ها ثانیه منتظر می‌ماند.
    #
    # حالا هر آپدیت به استخر می‌رود، ولی پیام‌های یک کاربر با قفلِ
    # همان چت سریالی می‌مانند — وگرنه دو پیام پشت‌سرهم یک نفر
    # می‌توانستند جابه‌جا اجرا شوند و وضعیت گفت‌وگو خراب شود.
    pool = ThreadPoolExecutor(max_workers=POOL_SIZE,
                              thread_name_prefix=f"{name}-w")
    chat_locks = ChatLocks()

    def handle(tenant_snapshot, bot, update):
        try:
            with chat_locks.hold(chat_id_of(update)):
                handlers.dispatch(tenant_snapshot, bot, update)
        except Exception:
            log.exception("%s: خطا در پردازش آپدیت %s",
                          name, update.get("update_id"))

    while not _stop.is_set():
        try:
            tenant = db.get_tenant(tenant_id)
            if not tenant or not tenant["is_active"] or not tenant["bot_token"]:
                log.info("%s: غیرفعال یا بدون توکن — خروج", name)
                return

            # Bot را یک‌بار می‌سازیم و نگه می‌داریم.
            #
            # قبلاً در هر دور حلقه یکی نو ساخته می‌شد، یعنی نشست
            # requests و اتصال باز TLS هر بار دور ریخته می‌شد و
            # فراخوانی بعدی از صفر دست می‌داد. روی مسیر ایران به
            # تلگرام، همین تنهایی چند صد میلی‌ثانیه به هر پیام
            # اضافه می‌کرد.
            if tg is None or tg.token != tenant["bot_token"]:
                tg = Bot(tenant["bot_token"])
                _sync_menu_button(tenant, tg, name)
                # the admin group's topics, all at once (handlers.TOPICS)
                try:
                    handlers.Ctx(tg, tenant).ensure_topics()
                except Exception as e:
                    log.warning("%s: admin group topics not made: %s", name, e)

            updates = tg.updates(offset=offset, timeout=25)
            backoff = 1

            for up in updates:
                offset = up["update_id"] + 1
                if _stop.is_set():
                    break
                pool.submit(handle, tenant, tg, up)

        except TelegramError as e:
            msg = str(e)
            if "401" in msg or "Unauthorized" in msg:
                log.error("%s: توکن نامعتبر است — غیرفعال شد", name)
                _event(tenant_id, "token_invalid", None, {"error": msg[:200]})
                db.update_tenant(tenant_id, is_active=0)
                return
            log.warning("%s: خطای تلگرام: %s", name, msg)
            _stop.wait(min(backoff, 60))
            backoff = min(backoff * 2, 60)

        except Exception:
            log.exception("%s: خطای غیرمنتظره", name)
            _stop.wait(min(backoff, 60))
            backoff = min(backoff * 2, 60)


def sync_workers():
    """
    مستاجرهای فعال را با نخ‌های در حال اجرا هماهنگ می‌کند.
    مستاجر جدید → نخ جدید. مستاجر حذف/غیرفعال → نخ خودش خارج می‌شود.
    """
    with _lock:
        active = {t["id"] for t in db.all_tenants(active_only=True) if t["bot_token"]}

        # حذف نخ‌های تمام‌شده
        for tid in list(_workers):
            if not _workers[tid].is_alive():
                _workers.pop(tid, None)

        for tid in active:
            if tid not in _workers:
                th = threading.Thread(target=tenant_loop, args=(tid,),
                                      name=f"tenant-{tid}", daemon=True)
                th.start()
                _workers[tid] = th
                log.info("ربات مستاجر %s راه‌اندازی شد", tid)


# ═══════════════════════════════════════════════════════════
#  کارهای دوره‌ای
# ═══════════════════════════════════════════════════════════

def expire_stale_orders():
    """سفارش‌هایی که مهلت پرداختشان گذشته را منقضی می‌کند."""
    n = 0
    for t in db.all_tenants():
        d = db.TenantDB(t["id"])
        rows = d.q(
            """SELECT id FROM orders
               WHERE tenant_id=? AND status='pending'
                 AND expires_at IS NOT NULL AND expires_at < ?""",
            (t["id"], datetime.now().isoformat())
        )
        tg = Bot(t["bot_token"]) if t["bot_token"] else None
        for r in rows:
            # ادعا، نه دستورِ خام: اگر همین لحظه مشتری «لغو» بزند یا
            # نخ دیگری سفارش را ببندد، تنها یکی از ما باید پول را
            # برگرداند. close_order پولِ کیف پول را هم برمی‌گرداند —
            # سفارشِ کیف‌پولیِ نیمه‌کاره (مثلاً ربات وسطِ ساختِ کانفیگ
            # ری‌استارت شده) وگرنه با پولِ کم‌شده منقضی می‌شد.
            won, money = d.close_order(r["id"], "expired")
            if not won:
                continue

            # رزرو سکه باید همین‌جا آزاد شود. سه مسیر دستی این کار را
            # می‌کردند، ولی این جاروکش هر دو دقیقه می‌دود و همیشه
            # زودتر از مشتری به سفارش می‌رسد — پس در عمل سکه‌ها هیچ
            # وقت برنمی‌گشتند.
            back = d.release_coins(r["id"])
            n += 1

            if tg and money:
                # پولِ برگشته باید گفته شود. سکه یک چیز است و پول
                # چیز دیگر؛ مشتری نباید خودش حدس بزند کدام برگشت.
                try:
                    row = d.q("SELECT u.tg_id FROM orders o JOIN users u"
                              " ON u.id=o.user_id WHERE o.tenant_id=?"
                              " AND o.id=?", (t["id"], r["id"]), one=True)
                    if row and row["tg_id"]:
                        tg.send(row["tg_id"],
                                "⌛️ <b>این سفارش ناتمام ماند</b>\n\n"
                                f"مبلغ <b>{core.toman(money)}</b> تومان به "
                                "کیف پولتان برگشت.")
                except Exception:
                    log.debug("اطلاع بازگشت وجه ناموفق", exc_info=True)

            if tg and back:
                # مشتری باید بداند چرا سکه‌هایش برگشت، وگرنه فقط یک
                # عدد عوض‌شده می‌بیند.
                try:
                    row = d.q("SELECT u.tg_id FROM orders o JOIN users u"
                              " ON u.id=o.user_id WHERE o.tenant_id=?"
                              " AND o.id=?", (t["id"], r["id"]), one=True)
                    if row and row["tg_id"]:
                        tg.send(row["tg_id"],
                                "⌛️ <b>مهلت پرداخت این سفارش تمام شد</b>\n\n"
                                "سکه‌هایی که استفاده کرده بودید به حسابتان "
                                "برگشت و دوباره قابل استفاده‌اند.\n\n"
                                "اگر واریز کرده‌اید نگران نباشید — "
                                "رسیدتان را برای پشتیبانی بفرستید.")
                except Exception:
                    log.debug("اطلاع انقضای سفارش ناموفق", exc_info=True)
    if n:
        log.info("%s سفارش منقضی شد", n)


#: آستانه‌های یادآوری انقضا — از دور به نزدیک.
#: سه اسلاتِ یادآوری، و پرچمی که هر کدام می‌بندد.
#:
#: عددها پیش‌فرض‌اند و مالک از پنل عوضشان می‌کند. نامِ ستون‌ها
#: دیگر معنای عددی ندارند — «اسلاتِ اول/دوم/سوم»اند. سه اسلاتِ
#: ثابت ماند چون پرچم سه ستونِ مشخص است؛ فهرستِ آزاد یعنی
#: `notified_14d` هم لازم است، یا یک جدولِ تازه.
EXPIRY_STEPS = ((7, "notified_7d"), (3, "notified_3d"), (1, "notified_1d"))
EXPIRY_FLAGS = tuple(f for _d, f in EXPIRY_STEPS)


def expiry_steps(cfg):
    """
    آستانه‌های یادآوری برای این مستاجر.

    صفر یعنی همان اسلات خاموش — نه همه‌ی یادآوری‌ها. برای خاموشیِ
    کامل `reminders.enabled` هست.

    مرتب‌سازیِ نزولی فقط برای خواناییِ لاگ است؛ منطقِ «هر آستانه‌ای
    که مشتری از آن رد شده با یک پیام بسته می‌شود» به ترتیب وابسته
    نیست.
    """
    days = (cfg.get("reminders") or {}).get("days")
    if not isinstance(days, (list, tuple)):
        return EXPIRY_STEPS
    out = []
    for i, flag in enumerate(EXPIRY_FLAGS):
        try:
            d = int(days[i]) if i < len(days) else 0
        except (TypeError, ValueError):
            d = 0
        if d > 0:
            out.append((d, flag))
    return tuple(sorted(out, key=lambda x: -x[0]))


def send_expiry_reminders():
    """
    یادآوری انقضا در ۷، ۳ و ۱ روز مانده.

    هر یادآوری فقط یک‌بار ارسال می‌شود (پرچم notified_*) تا کاربر
    با پیام تکراری آزار نبیند.
    """
    now = datetime.now(timezone.utc)
    for t in db.all_tenants(active_only=True):
        if not t["bot_token"]:
            continue
        d = db.TenantDB(t["id"])
        cfg = db.tenant_settings(t["id"])
        if cfg.get("reminders", {}).get("enabled") is False:
            continue

        # هر سه اسلات خاموش یعنی این مستاجر یادآوریِ انقضا نمی‌خواهد
        steps = expiry_steps(cfg)
        if not steps:
            continue

        tg = Bot(t["bot_token"])
        subs = d.q(
            """SELECT s.*, u.tg_id FROM subscriptions s
               JOIN users u ON u.id = s.user_id
               WHERE s.tenant_id=? AND s.is_active=1 AND s.expires_at IS NOT NULL""",
            (t["id"],)
        )

        for s in subs:
            left = core.days_left(s["expires_at"])
            if left is None:
                continue

            # اشتراکی که با ۱ روز باقی‌مانده وارد پنجره می‌شود، هم‌زمان
            # داخل هر سه آستانه است. قبلاً هر ساعت یکی از آن‌ها باز
            # می‌شد و همان پیام دوباره می‌رفت — سه «فقط یک روز مانده»
            # در سه ساعت. پس هر آستانه‌ای که کاربر از آن رد شده با
            # همان یک پیام بسته می‌شود.
            inside = [flag for day, flag in steps if left <= day]
            if not inside or all(s[f] for f in inside):
                continue

            try:
                handlers.send_expiry_notice(t, tg, s, left)
            except Exception as _e:
                log.exception("ارسال یادآوری ناموفق (اشتراک %s)", s["id"])
                _event(t["id"], "reminder_failed", s.get("user_id"),
                       {"sub": s["id"], "error": str(_e)[:200]})
                continue    # پرچم را نمی‌بندیم تا ساعت بعد دوباره تلاش شود

            d.exec(
                "UPDATE subscriptions SET " + ", ".join(f"{f}=1" for f in inside)
                + " WHERE tenant_id=? AND id=?",
                (t["id"], s["id"])
            )
            log.info("یادآوری %s روز برای اشتراک %s", left, s["id"])


#: از چند درصد مصرف هشدار بدهیم.
#: درصدِ پیش‌فرضِ هشدارِ حجم. مالک از پنل عوضش می‌کند؛ صفر یعنی
#: این هشدار برای آن مستاجر خاموش است.
TRAFFIC_WARN_PCT = 80


def traffic_pct(cfg):
    """آستانه‌ی هشدارِ حجم — صفر یعنی خاموش."""
    v = (cfg.get("reminders") or {}).get("traffic_pct")
    if v is None or v == "":
        return TRAFFIC_WARN_PCT
    try:
        v = int(v)
    except (TypeError, ValueError):
        return TRAFFIC_WARN_PCT
    return v if 0 <= v <= 100 else TRAFFIC_WARN_PCT


def send_traffic_warnings():
    """
    هشدار حجم، وقتی مصرف از ۸۰٪ گذشت.

    پرچم notified_80p از روز اول در جدول بود و مسیر تمدید هم صفرش
    می‌کرد، ولی هیچ‌جا ست نمی‌شد — یعنی این هشدار هرگز نرفته بود.
    برای مشتری‌ای که حجمش وسط ماه تمام می‌شود، این تنها خبری است که
    می‌تواند قبل از قطعی بگیرد.

    مصرف را یک‌جا از پنل می‌گیریم (یک درخواست برای همه)، نه یکی‌یکی.
    """
    for t in db.all_tenants(active_only=True):
        if not t["bot_token"]:
            continue
        cfg = db.tenant_settings(t["id"])
        if cfg.get("reminders", {}).get("enabled") is False:
            continue

        want = traffic_pct(cfg)
        if not want:
            continue

        d = db.TenantDB(t["id"])
        subs = d.q(
            """SELECT s.*, u.tg_id FROM subscriptions s
               JOIN users u ON u.id = s.user_id
               WHERE s.tenant_id=? AND s.is_active=1 AND s.notified_80p=0
                 AND s.gb > 0""",
            (t["id"],)
        )
        if not subs:
            continue

        tg = Bot(t["bot_token"])
        ctx = handlers.Ctx(tg, t)
        try:
            usage = ctx.xui.all_client_traffic()
        except Exception as _e:
            log.exception("گرفتن مصرف ناموفق (مستاجر %s)", t["id"])
            _event(t["id"], "usage_failed", None, {"error": str(_e)[:200]})
            continue

        for s in subs:
            # اشتراکی که تاریخش تمام شده، مصرفش دیگر مهم نیست
            left = core.days_left(s["expires_at"]) if s["expires_at"] else None
            if left is not None and left <= 0:
                continue

            pair = usage.get(s["client_email"])
            if pair is None:
                continue
            used_gb = round(sum(pair) / (1024 ** 3), 1)
            total_gb = s["gb"] or 0
            if not total_gb or used_gb * 100 < want * total_gb:
                continue

            try:
                handlers.send_traffic_notice(t, tg, s, used_gb, total_gb)
            except Exception as _e:
                log.exception("هشدار حجم ناموفق (اشتراک %s)", s["id"])
                _event(t["id"], "traffic_warn_failed", s.get("user_id"),
                       {"sub": s["id"], "error": str(_e)[:200]})
                continue

            d.exec("UPDATE subscriptions SET notified_80p=1"
                   " WHERE tenant_id=? AND id=?", (t["id"], s["id"]))
            log.info("هشدار حجم %s٪ برای اشتراک %s",
                     int(used_gb * 100 / total_gb), s["id"])


def run_auto_renew():
    """
    تمدید خودکار از کیف پول برای اشتراک‌هایی که auto_renew دارند.

    فقط وقتی انجام می‌شود که موجودی کافی باشد؛ در غیر این‌صورت به کاربر
    اطلاع داده می‌شود تا خودش شارژ کند.
    """
    for t in db.all_tenants(active_only=True):
        if not t["bot_token"]:
            continue
        d = db.TenantDB(t["id"])
        tg = Bot(t["bot_token"])

        # اشتراکی که تلاش بعدی‌اش هنوز نرسیده کنار گذاشته می‌شود.
        # بدون این، شکستِ پایدار هر ساعت تکرار می‌شد.
        subs = d.q(
            """SELECT s.*, u.tg_id, u.balance FROM subscriptions s
               JOIN users u ON u.id = s.user_id
               WHERE s.tenant_id=? AND s.is_active=1 AND s.auto_renew=1
                 AND (s.renew_retry_at IS NULL
                      OR s.renew_retry_at <= datetime('now'))""",
            (t["id"],)
        )

        for s in subs:
            left = core.days_left(s["expires_at"])
            if left is None or left > 1:
                continue
            try:
                handlers.auto_renew_subscription(t, tg, s)
            except Exception as _e:
                log.exception("تمدید خودکار ناموفق (اشتراک %s)", s["id"])
                _event(t["id"], "renew_failed", s.get("user_id"),
                       {"sub": s["id"], "error": str(_e)[:200]})


def daily_report():
    """گزارش روزانه در گروه مدیریت هر مستاجر."""
    for t in db.all_tenants(active_only=True):
        if not t["bot_token"]:
            continue
        try:
            handlers.send_daily_report(t)
        except Exception as _e:
            log.exception("گزارش روزانه ناموفق (مستاجر %s)", t["id"])
            _event(t["id"], "report_failed", None, {"error": str(_e)[:200]})


def sms_sweep():
    """
    Orders and bank deposits the SMS check could not pair within its window,
    said once in each shop's group (docs/specs/2026-10-07-sms-auto-approve.md).
    """
    sp = handlers.pro("smspay")
    if not sp:
        return
    for t in db.all_tenants(active_only=True):
        if not t.get("bot_token"):
            continue
        try:
            ctx = handlers.Ctx(Bot(t["bot_token"]), t)
            if sp.enabled(ctx):
                sp.sweep(ctx)
        except Exception:
            log.exception("sms sweep failed for shop %s", t.get("id"))


def process_panel_approvals():
    """
    سفارش‌هایی که از پنل مدیریت تایید شده‌اند را تحویل می‌دهد.

    پنل به 3x-ui و تلگرام دسترسی ندارد، پس فقط وضعیت را روی
    panel_approve می‌گذارد؛ ربات اینجا کار را تمام می‌کند:
    ساخت کانفیگ، ارسال به مشتری، اعطای سکه معرف.
    """
    try:
        with db.conn() as cx:
            rows = cx.execute(
                "SELECT id, tenant_id, status, admin_note FROM orders "
                "WHERE status IN ('panel_approve','panel_reject') LIMIT 20"
            ).fetchall()
    except Exception as e:
        log.warning("خواندن سفارش‌های پنل ناموفق: %s", e)
        return

    for r in rows:
        oid, tid = r["id"], r["tenant_id"]
        try:
            tenant = db.get_tenant(tid)
            if not tenant or not tenant.get("bot_token"):
                continue

            tg = Bot(tenant["bot_token"])
            ctx = handlers.Ctx(tg, tenant)

            if r["status"] == "panel_reject":
                done = handlers.do_reject(ctx, oid, 0,
                                          r["admin_note"] or "رسید تایید نشد.")
                if done:
                    log.info("سفارش %s از پنل رد شد", oid)
                else:
                    # رد شرطی است و تنها دلیل شکستش این است که کانفیگ
                    # ساخته شده. سفارش باید از حالت panel_reject بیرون
                    # بیاید، وگرنه هر بیست ثانیه دوباره تلاش می‌شود و
                    # صف تا ابد همین یکی را می‌چرخاند.
                    log.warning("سفارش %s رد نشد — کانفیگش ساخته شده", oid)
                    with db.conn() as cx:
                        cx.execute(
                            "UPDATE orders SET status='approved', admin_note=? "
                            "WHERE id=? AND status='panel_reject'",
                            ("رد نشد چون کانفیگ قبلاً تحویل شده بود", oid))
                continue

            ok, note = handlers.approve_order(ctx, oid, admin_tg_id=0)

            if ok:
                log.info("سفارش %s از پنل تحویل شد", oid)
            elif note == handlers.ORDER_BUSY:
                # نخ دیگری همین سفارش را برداشته و همین حالا وسط ساخت
                # کانفیگ است. دست زدن به وضعیت یعنی نوشتن روی ادعای او.
                log.info("سفارش %s دست نخ دیگری است — رها می‌کنیم", oid)
            else:
                log.warning("تحویل سفارش %s ناموفق: %s", oid, note)
                with db.conn() as cx:
                    cx.execute(
                        "UPDATE orders SET status='awaiting', admin_note=? "
                        "WHERE id=? AND " + db.UNDELIVERED,
                        (f"تحویل ناموفق: {str(note)[:120]}", oid))
        except Exception as e:
            log.error("خطا در تحویل سفارش %s: %s", oid, e)
            _event(tid, "order_deliver_failed", None,
                   {"order": oid, "error": str(e)[:200]})
            try:
                with db.conn() as cx:
                    cx.execute(
                        "UPDATE orders SET status='awaiting', admin_note=? "
                        "WHERE id=? AND " + db.UNDELIVERED,
                        (f"خطای تحویل: {str(e)[:120]}", oid))
            except Exception as e2:
                # اگر برگرداندن هم نشد، سفارش «تاییدشده» می‌ماند بی‌آنکه
                # کانفیگی ساخته شده باشد — همان چیزی که قاعده‌ی «approved
                # فقط بعد از ساخت» جلویش را می‌گیرد. پیش‌تر pass بود.
                log.error("reverting undelivered order %s to awaiting failed: %s", oid, e2)
                _event(tid, "order_deliver_failed", None,
                       {"order": oid, "error": f"revert failed: {str(e2)[:160]}"})


def send_trial_journey():
    """
    The trial follow-up (Pro, `loyalty`): bot/pro/loyalty.py. Locked, none
    goes out, and its 72-hour window means none arrives weeks late when the
    license comes back.
    """
    loy = handlers.pro("loyalty")
    if loy and handlers.pro_allowed("loyalty"):
        loy.send_trial_journey(db, Bot, handlers, _event)


def send_feedback_polls():
    """
    Polls a few days after a purchase or renewal (Pro, `insights`).

    The sending is `bot/pro/insights.py`. While Pro is locked none go out: the
    orders keep `feedback_at` empty, and the two-day window means none of them
    is asked weeks late when the license comes back.
    """
    ins = handlers.pro("insights")
    if ins and handlers.pro_allowed("insights"):
        ins.send_feedback_polls(db, Bot, handlers, _event)


def trial_winback():
    """
    The win-back code for a trial that did not buy (Pro, `loyalty`):
    bot/pro/loyalty.py. Locked, none goes out; the window keeps a returning
    license from sending codes for trials long gone.
    """
    loy = handlers.pro("loyalty")
    if loy and handlers.pro_allowed("loyalty"):
        loy.trial_winback(db, Bot, handlers, _event)


#: Shown on a post that came due while Pro was locked. Sending a promotion
#: weeks late, when the license comes back, is worse than not sending it; a post
#: that silently stays queued forever is worse than both.
LOCKED_POST_ERROR = "Pro در زمانِ ارسالِ این پست قفل بود؛ پست نرفت"


def send_due_posts():
    """
    Channel posts whose time has come (Pro, `channel`).

    Spec: docs/specs/2026-09-29-pro-split.md ("Channel specifics"). The sending
    itself is `bot/pro/channel.py`; the core only decides whether it may run.
    """
    chan = handlers.pro("channel")
    if chan and handlers.pro_allowed("channel"):
        chan.send_due_posts(db, Bot, handlers.Ctx, _event)
        return
    expire_locked_posts()


def expire_locked_posts():
    """Due posts while Pro is locked or absent: failed, with the reason."""
    for t in db.all_tenants(active_only=True):
        try:
            d = db.TenantDB(t["id"])
            due = d.q("""SELECT id FROM channel_posts
                          WHERE tenant_id=? AND status='queued' AND claimed_at IS NULL
                            AND scheduled_at IS NOT NULL
                            AND scheduled_at <= datetime('now', 'localtime')""",
                      (t["id"],))
            for p in due:
                if d.channel_claim(p["id"]):
                    d.channel_done(p["id"], error=LOCKED_POST_ERROR)
            if due:
                log.warning("%s channel posts not sent: Pro locked (tenant %s)",
                            len(due), t["id"])
        except Exception as _e:
            log.exception("expiring locked channel posts failed (tenant %s)", t["id"])
            _event(t["id"], "channel_failed", None, {"error": str(_e)[:200]})


_MINI_STATE = {"allowed": None}


def sync_menu_buttons_on_license_change():
    """Telegram keeps a menu button until told otherwise. Set when the tenant
    thread starts, it outlived a lapsed license: customers tapped it and got
    the mini app's "not available" page. Re-sync every bot when the answer
    changes, either way."""
    now = handlers.pro_allowed("mini_app")
    was, _MINI_STATE["allowed"] = _MINI_STATE["allowed"], now
    if was is None or was == now:
        return
    for t in db.all_tenants(active_only=True):
        if t["bot_token"]:
            _sync_menu_button(dict(t), Bot(t["bot_token"]), f"tenant-{t['id']}")


def scheduler_loop():
    """
    زمان‌بند ساده و بدون وابستگی خارجی.

    از APScheduler استفاده نمی‌کنیم تا نصب سبک بماند؛ این حلقه
    برای بازه‌های چنددقیقه‌ای کاملاً کافی است.
    """
    last = {"orders": 0, "panel": 0, "reminders": 0, "renew": 0, "report_day": None}

    while not _stop.is_set():
        now = time.time()
        try:
            if now - last["orders"] > 120:
                expire_stale_orders()
                last["orders"] = now

            # پستِ زمان‌بندی‌شده نباید ساعت‌ها دیر برود؛ دقیقه‌ای
            # یک‌بار کافی است و تقریباً هیچ هزینه‌ای ندارد.
            if now - last.get("posts", 0) > 60:
                send_due_posts()
                sync_menu_buttons_on_license_change()
                sms_sweep()
                last["posts"] = now

            # تاییدهای پنل را سریع‌تر بررسی می‌کنیم — مشتری منتظر است
            if now - last.get("panel", 0) > 20:
                process_panel_approvals()
                last["panel"] = now

            if now - last["reminders"] > 3600:
                send_expiry_reminders()
                send_traffic_warnings()
                trial_winback()
                last["reminders"] = now

            # پیگیریِ تست ساعتِ خودش را دارد (۸/۱۶/۲۴)؛ هر ۱۰ دقیقه کافی است
            if now - last.get("journey", 0) > 600:
                send_trial_journey()
                send_feedback_polls()
                last["journey"] = now

            if now - last["renew"] > 3600:
                run_auto_renew()
                last["renew"] = now

            today = datetime.now().date()
            if datetime.now().hour == 23 and last["report_day"] != today:
                daily_report()
                last["report_day"] = today

            # اگر پنل اعلام کرده تنظیمات عوض شده، نخ‌ها را همگام می‌کنیم.
            # این باعث قطعی نمی‌شود؛ فقط مستاجرهای جدید/غیرفعال را می‌گیرد.
            try:
                with db.conn() as cx:
                    row = cx.execute(
                        "SELECT value FROM bot_flags WHERE key='reload'").fetchone()
                    if row and row["value"] != last.get("reload_seen"):
                        last["reload_seen"] = row["value"]
                        log.info("پنل تغییر تنظیمات را اعلام کرد — همگام‌سازی")
            except Exception as e:
                # sync_workers پایین‌تر به‌هرحال اجرا می‌شود؛ فقط گفته شود
                log.warning("reading reload flag failed: %s", e)

            sync_workers()

        except Exception as _e:
            log.exception("خطا در زمان‌بند")
            try:
                for _t in db.all_tenants(active_only=True):
                    _event(_t["id"], "scheduler_failed", None,
                           {"error": str(_e)[:200]})
            except Exception:
                log.debug("ثبت خطای زمان‌بند ناموفق", exc_info=True)

        _stop.wait(30)


# ═══════════════════════════════════════════════════════════
#  اجرا
# ═══════════════════════════════════════════════════════════

def shutdown(signum, frame):
    log.info("سیگنال %s — در حال خاموش شدن...", signum)
    _stop.set()


def main():
    logging.basicConfig(
        level=os.getenv("BOT_LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    db.init_db()
    log.info("دیتابیس آماده: %s", db.DB_PATH)

    tenants = [t for t in db.all_tenants(active_only=True) if t["bot_token"]]
    if not tenants:
        log.warning("هیچ مستاجر فعالی با توکن ربات پیدا نشد — منتظر پیکربندی از پنل")
    else:
        log.info("%s مستاجر فعال", len(tenants))

    sync_workers()

    sch = threading.Thread(target=scheduler_loop, name="scheduler", daemon=True)
    sch.start()
    log.info("زمان‌بند فعال شد")

    try:
        while not _stop.is_set():
            _stop.wait(1)
    except KeyboardInterrupt:
        _stop.set()

    log.info("خاموش شد")


if __name__ == "__main__":
    main()
