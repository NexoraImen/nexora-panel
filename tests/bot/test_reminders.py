#!/usr/bin/env python3
"""
یادآوری انقضا باید یک‌بار برسد، نه سه‌بار پشت سر هم.

چرا وجود دارد:
    زمان‌بند هر ساعت سه آستانه را به ترتیب بررسی می‌کرد و روی اولین
    آستانه‌ی بازِ پیدا شده «break» می‌زد:

        for day, flag in ((7, "notified_7d"), (3, ...), (1, ...)):
            if left <= day and not s[flag]:
                send(...); set(flag); break

    برای اشتراکی که با ۳۰ روز شروع می‌شود این درست کار می‌کند. ولی
    اشتراکی که با ۱ روز باقی‌مانده وارد پنجره می‌شود — پلن کوتاه،
    یادآوری‌های تازه‌روشن‌شده، یا رباتی که چند ساعت خواب بوده —
    هم‌زمان داخل هر سه آستانه است:

        ساعت ۱: آستانه‌ی ۷ باز است  →  «فقط یک روز مانده»
        ساعت ۲: آستانه‌ی ۳ باز است  →  «فقط یک روز مانده»
        ساعت ۳: آستانه‌ی ۱ باز است  →  «فقط یک روز مانده»

    سه پیام یکسان در سه ساعت، برای مشتری‌ای که همان بار اول فهمیده
    بود. متنِ پیام‌ها هم دقیقاً یکی است، چون هر سه با همان left ساخته
    می‌شوند — پس حتی به نظر هم نمی‌رسد که عمدی باشد.

    این تست زمان‌بند واقعی را با ساعت‌های پشت‌سرهم می‌دواند و پیام‌ها
    را می‌شمارد.

اجرا:  python3 tests/bot/test_reminders.py
"""
import os
# repo root and bot/ — these tests moved from bot/ to tests/bot/ (2.0 layout)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOT_DIR = os.path.join(_ROOT_DIR, "bot")

import sys
import tempfile
from datetime import datetime, timedelta

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


os.environ["BOT_DB_PATH"] = tempfile.mktemp(suffix=".db")
sys.path.insert(0, _ROOT_DIR)

from bot import db as DB      # noqa: E402
from bot import run as RUN    # noqa: E402
from bot import handlers      # noqa: E402

DB.init_db()
tid = DB.create_tenant("تست یادآوری", bot_token="123:TEST", owner_tg_id=999)
d = DB.TenantDB(tid)

pid = d.exec("INSERT INTO plans (tenant_id, name, gb, days, price)"
             " VALUES (?,?,?,?,?)", (tid, "یک‌ماهه", 50, 30, 190000))


# ── ربات و اعلان قلابی؛ فقط می‌شماریم چه رفت ──
SENT = []


class FakeBot:
    def __init__(self, token):
        self.token = token

    def send(self, *a, **k):
        return {"ok": True}


def fake_notice(tenant, bot, sub, days_left):
    SENT.append((sub["id"], days_left))


RUN.Bot = FakeBot
# نسخه‌ی واقعی را نگه می‌داریم: بدونش صدازدنِ آن در آخرِ فایل همین
# قلابی را صدا می‌زند و متنِ واقعی هرگز ساخته نمی‌شود.
REAL_EXPIRY = handlers.send_expiry_notice
handlers.send_expiry_notice = fake_notice


def new_sub(days_from_now, tg_id, auto_renew=0, active=1):
    """اشتراکی که n روز دیگر منقضی می‌شود."""
    uid = d.exec("INSERT INTO users (tenant_id, tg_id, first_name)"
                 " VALUES (?,?,?)", (tid, tg_id, f"کاربر {tg_id}"))
    exp = (datetime.now() + timedelta(days=days_from_now, hours=1)).isoformat()
    return d.exec(
        "INSERT INTO subscriptions (tenant_id, user_id, plan_id, client_email,"
        " gb, expires_at, is_active, auto_renew) VALUES (?,?,?,?,?,?,?,?)",
        (tid, uid, pid, f"e_{tg_id}", 50, exp, active, auto_renew))


def tick():
    """یک دور زمان‌بند، مثل هر ساعت روی سرور."""
    RUN.send_expiry_reminders()


def sent_for(sid):
    return [x for x in SENT if x[0] == sid]


def set_exp(sid, days_from_now):
    d.exec("UPDATE subscriptions SET expires_at=? WHERE tenant_id=? AND id=?",
           ((datetime.now() + timedelta(days=days_from_now, hours=1)).isoformat(),
            tid, sid))


# ═══════════════════════════════════════════════════════════
head("اشتراک دور از انقضا کاری ندارد")

far = new_sub(25, 100100)
tick()
check("۲۵ روز مانده — هیچ پیامی نمی‌رود", not sent_for(far),
      f"{len(sent_for(far))} پیام")


# ═══════════════════════════════════════════════════════════
head("اشتراکی که با یک روز باقی‌مانده وارد پنجره می‌شود")

late = new_sub(1, 100200)
SENT.clear()
for _ in range(3):        # سه ساعت پشت سر هم
    tick()

n = len(sent_for(late))
check("در سه ساعت فقط یک پیام می‌گیرد", n == 1,
      f"{n} پیام" + (" — هر سه آستانه یکی‌یکی باز شدند" if n > 1 else ""))
check("و متن‌ها تکراری نیستند", len({x[1] for x in sent_for(late)}) == n,
      "سه بار «یک روز مانده» یعنی مشتری فکر می‌کند ربات خراب است")

flags = d.q("SELECT notified_7d, notified_3d, notified_1d FROM subscriptions"
            " WHERE tenant_id=? AND id=?", (tid, late), one=True)
check("هر سه آستانه با همان یک پیام بسته می‌شوند",
      flags and flags["notified_7d"] and flags["notified_3d"]
      and flags["notified_1d"],
      "چون اشتراک هم‌زمان داخل هر سه بود")


# ═══════════════════════════════════════════════════════════
head("اشتراک عادی هر آستانه را جدا می‌گیرد")

norm = new_sub(6, 100300)
SENT.clear()

tick()
check("۶ روز مانده — یادآوری اول می‌رود", len(sent_for(norm)) == 1,
      f"{len(sent_for(norm))} پیام")

tick()
check("ساعت بعد چیز تازه‌ای نمی‌رود", len(sent_for(norm)) == 1,
      f"{len(sent_for(norm))} پیام")

set_exp(norm, 2)
tick()
check("وقتی به ۲ روز رسید، یادآوری دوم می‌رود", len(sent_for(norm)) == 2,
      f"{len(sent_for(norm))} پیام")

set_exp(norm, 0)
tick()
check("و روز آخر، یادآوری سوم", len(sent_for(norm)) == 3,
      f"{len(sent_for(norm))} پیام")

tick()
check("بعد از آن دیگر تمام", len(sent_for(norm)) == 3,
      "اشتراک منقضی هر ساعت پیام نمی‌گیرد")

days = [x[1] for x in sent_for(norm)]
check("هر پیام عدد روزِ خودش را دارد", days == sorted(days, reverse=True),
      " ← ".join(str(x) for x in days))


# ═══════════════════════════════════════════════════════════
head("مواردی که اصلاً نباید پیام بگیرند")

off = new_sub(1, 100400, active=0)
SENT.clear()
tick()
check("اشتراک غیرفعال پیام نمی‌گیرد", not sent_for(off))

noexp = d.exec(
    "INSERT INTO subscriptions (tenant_id, user_id, plan_id, client_email,"
    " gb, expires_at, is_active) VALUES (?,?,?,?,?,NULL,1)",
    (tid, d.q("SELECT id FROM users WHERE tenant_id=? LIMIT 1", (tid,),
              one=True)["id"], pid, "e_noexp", 50))
SENT.clear()
tick()
check("اشتراک بدون تاریخ انقضا پیام نمی‌گیرد", not sent_for(noexp),
      "نامحدود است، انقضایی ندارد")

# یادآوری خاموش‌شده در تنظیمات
quiet = new_sub(1, 100500)
DB.save_tenant_settings(tid, {**DB.tenant_settings(tid),
                              "reminders": {"enabled": False}})
SENT.clear()
tick()
check("وقتی یادآوری خاموش است هیچ‌کس پیام نمی‌گیرد", not SENT,
      f"{len(SENT)} پیام")
DB.save_tenant_settings(tid, {**DB.tenant_settings(tid),
                              "reminders": {"enabled": True}})


# ═══════════════════════════════════════════════════════════
head("آستانه‌ها را مالک تعیین می‌کند")

# تا ۱.۷۱.۰ این عددها ثابتِ ماژول بودند: مالکی که می‌خواست ۱۴ روز
# مانده هم خبر بدهد، هیچ راهی نداشت.


def set_rem(**kw):
    cfg = DB.tenant_settings(tid)
    DB.save_tenant_settings(tid, {**cfg, "reminders": {**(cfg.get("reminders") or {}),
                                                       "enabled": True, **kw}})


set_rem(days=[14, 3, 1])
far14 = new_sub(12, 100440)
SENT.clear()
tick()
check("عددِ سفارشیِ اسلات واقعاً اثر می‌کند", len(sent_for(far14)) == 1,
      "۱۲ روز مانده و آستانه ۱۴ — با عددِ پیش‌فرضِ ۷ هیچ پیامی نمی‌رفت")

# اسلاتِ اول خاموش، دومی ۳ روز. پنج روز مانده یعنی هیچ آستانه‌ای
# رد نشده — با پیش‌فرضِ ۷ حتماً پیام می‌رفت.
set_rem(days=[0, 3, 0])
mid = new_sub(5, 100441)
SENT.clear()
tick()
check("اسلاتِ صفر خاموش است", not sent_for(mid),
      "۵ روز مانده و اسلاتِ ۷ خاموش — با پیش‌فرض پیام می‌رفت")
set_exp(mid, 2)
SENT.clear()
tick()
check("ولی اسلاتِ روشن سرِ جایش است", len(sent_for(mid)) == 1,
      "صفر یعنی همان یک آستانه خاموش، نه همه")
SENT.clear()
tick()
check("و همان یک‌بار", not sent_for(mid), "پرچم بسته می‌ماند")

set_rem(days=[0, 0, 0])
none3 = new_sub(2, 100442)
SENT.clear()
tick()
check("هر سه اسلاتِ صفر یعنی یادآوریِ انقضا خاموش", not SENT,
      f"{len(SENT)} پیام")

set_rem(days=[7, 3, 1])

# ── آستانه‌ی حجم ──
check("درصدِ پیش‌فرض ۸۰ می‌ماند",
      RUN.traffic_pct({}) == 80 and RUN.traffic_pct({"reminders": {}}) == 80)
check("عددِ سفارشی خوانده می‌شود",
      RUN.traffic_pct({"reminders": {"traffic_pct": 95}}) == 95)
check("صفر یعنی هشدارِ حجم خاموش",
      RUN.traffic_pct({"reminders": {"traffic_pct": 0}}) == 0)
check("عددِ بی‌معنی به پیش‌فرض برمی‌گردد",
      RUN.traffic_pct({"reminders": {"traffic_pct": 500}}) == 80
      and RUN.traffic_pct({"reminders": {"traffic_pct": "x"}}) == 80,
      "۵۰۰٪ یعنی هشدار هیچ‌وقت نمی‌رود — بی‌صدا")

check("فهرستِ خراب هم ربات را نمی‌خواباند",
      RUN.expiry_steps({"reminders": {"days": "۷"}}) == RUN.EXPIRY_STEPS
      and RUN.expiry_steps({"reminders": {"days": [None, "x"]}}) == (),
      "تنظیماتِ دستکاری‌شده نباید زمان‌بند را بشکند")


head("تمدید، یادآوری‌ها را برای دوره‌ی تازه باز می‌کند")

SRC = open(os.path.join(_BOT_DIR,
                        "handlers.py"), encoding="utf-8").read()
check("مسیر تمدید پرچم‌ها را صفر می‌کند",
      SRC.count("notified_7d=0, notified_3d=0, notified_1d=0") >= 2,
      "وگرنه مشتری بعد از اولین تمدید دیگر هیچ یادآوری نمی‌گیرد")

renewed = new_sub(1, 100600)
tick()
check("قبل از تمدید یک پیام گرفت", len(sent_for(renewed)) == 1)
d.exec("UPDATE subscriptions SET expires_at=?, notified_7d=0, notified_3d=0,"
       " notified_1d=0 WHERE tenant_id=? AND id=?",
       ((datetime.now() + timedelta(days=30)).isoformat(), tid, renewed))
tick()
check("بعد از تمدید، دوباره ساکت می‌شود", len(sent_for(renewed)) == 1,
      "۳۰ روز مانده، چیزی برای یادآوری نیست")
set_exp(renewed, 6)
tick()
check("و در دوره‌ی بعد دوباره یادآوری می‌کند", len(sent_for(renewed)) == 2)


# ═══════════════════════════════════════════════════════════
head("هشدار حجم — پرچمی که هیچ‌وقت پُر نمی‌شد")

# notified_80p از روز اول در جدول بود و دو جای کد صفرش می‌کردند،
# ولی هیچ‌جا ست نمی‌شد. یعنی هشدار «حجمت دارد تمام می‌شود» هرگز
# نرفته بود: مشتری حجمش تمام می‌شد، اتصالش می‌خوابید، و اولین
# خبری که می‌گرفت قطع‌شدن بود.

GB = 1024 ** 3
USAGE = {}
TSENT = []


class FakeXUI:
    def all_client_traffic(self):
        return dict(USAGE)


class FakeCtx:
    def __init__(self, bot, tenant):
        self.xui = FakeXUI()
        # `Ctx` واقعی تنظیماتِ مستاجر را در `.s` دارد و کدِ ربات از
        # آن می‌خواند. قلابی‌ای که نداشته باشد، تستی می‌سازد که سبز
        # است و در عمل AttributeError می‌دهد.
        self.s = DB.tenant_settings(tenant["id"]) if tenant else {}
        self.bot = bot


def fake_traffic_notice(tenant, bot, sub, used_gb, total_gb):
    TSENT.append((sub["id"], used_gb, total_gb))


REAL_NOTICE = handlers.send_traffic_notice
t_row = DB.get_tenant(tid)

# برابریِ قلابی با اصل: هر چیزی که کدِ ربات روی Ctx صدا می‌زند باید
# روی قلابی هم باشد. قلابی‌ای که یکی را نداشته باشد، تستِ سبزی
# می‌سازد که در عمل AttributeError است.
for _attr in ("s", "xui", "bot"):
    check(f"Ctx‌ِ قلابی «{_attr}» دارد",
          hasattr(FakeCtx(None, t_row), _attr),
          "وگرنه تستِ سبز چیزی را تضمین می‌کند که در عمل خطا می‌دهد")

handlers.Ctx = FakeCtx
handlers.send_traffic_notice = fake_traffic_notice


def tick_traffic():
    RUN.send_traffic_warnings()


def tsent_for(sid):
    return [x for x in TSENT if x[0] == sid]


def email_of(sid):
    return d.q("SELECT client_email FROM subscriptions WHERE tenant_id=? AND id=?",
               (tid, sid), one=True)["client_email"]


light = new_sub(20, 200100)      # ۵۰ گیگ
USAGE[email_of(light)] = (10 * GB, 5 * GB)      # ۱۵ از ۵۰ = ۳۰٪
tick_traffic()
check("۳۰٪ مصرف — هشداری نمی‌رود", not tsent_for(light))

heavy = new_sub(20, 200200)
USAGE[email_of(heavy)] = (30 * GB, 12 * GB)     # ۴۲ از ۵۰ = ۸۴٪
TSENT.clear()
tick_traffic()
check("۸۴٪ مصرف — هشدار می‌رود", len(tsent_for(heavy)) == 1,
      f"{len(tsent_for(heavy))} هشدار")
check("عدد مصرف درست به پیام می‌رسد",
      tsent_for(heavy) and tsent_for(heavy)[0][1] == 42.0,
      str(tsent_for(heavy) and tsent_for(heavy)[0][1]))

tick_traffic()
tick_traffic()
check("ساعت‌های بعد تکرار نمی‌شود", len(tsent_for(heavy)) == 1,
      "پرچم notified_80p حالا واقعاً ست می‌شود")

flag = d.q("SELECT notified_80p FROM subscriptions WHERE tenant_id=? AND id=?",
           (tid, heavy), one=True)
check("پرچم در دیتابیس بسته شد", flag and flag["notified_80p"] == 1)

edge = new_sub(20, 200300)
USAGE[email_of(edge)] = (40 * GB, 0)            # دقیقاً ۸۰٪
TSENT.clear()
tick_traffic()
check("دقیقاً ۸۰٪ هم هشدار می‌گیرد", len(tsent_for(edge)) == 1,
      "مرز شامل است، وگرنه یک قدم عقب‌تر هیچ‌وقت هشدار نمی‌گرفت")

head("مواردی که نباید هشدار حجم بگیرند")

unlim = d.exec(
    "INSERT INTO subscriptions (tenant_id, user_id, plan_id, client_email,"
    " gb, expires_at, is_active) VALUES (?,?,?,?,0,?,1)",
    (tid, d.q("SELECT id FROM users WHERE tenant_id=? LIMIT 1", (tid,),
              one=True)["id"], pid, "e_unlim",
     (datetime.now() + timedelta(days=20)).isoformat()))
USAGE["e_unlim"] = (900 * GB, 0)
TSENT.clear()
tick_traffic()
check("اشتراک نامحدود هشدار نمی‌گیرد", not tsent_for(unlim),
      "حجمی ندارد که تمام شود")

gone = new_sub(-3, 200400)
USAGE[email_of(gone)] = (49 * GB, 0)
TSENT.clear()
tick_traffic()
check("اشتراک منقضی هشدار حجم نمی‌گیرد", not tsent_for(gone),
      "تاریخش تمام شده، مصرفش دیگر مهم نیست")

dead = new_sub(20, 200500, active=0)
USAGE[email_of(dead)] = (49 * GB, 0)
TSENT.clear()
tick_traffic()
check("اشتراک غیرفعال هشدار نمی‌گیرد", not tsent_for(dead))

missing = new_sub(20, 200600)     # در پنل پیدا نمی‌شود
TSENT.clear()
tick_traffic()
check("کلاینتی که پنل نمی‌شناسد رد می‌شود", not tsent_for(missing),
      "بدون خطا، بدون هشدار اشتباه")

head("تمدید، هشدار حجم را هم باز می‌کند")

check("مسیر تمدید notified_80p را صفر می‌کند",
      SRC.count("notified_80p=0") >= 2,
      "وگرنه مشتری فقط یک‌بار در کل عمرش هشدار حجم می‌گرفت")

d.exec("UPDATE subscriptions SET notified_80p=0 WHERE tenant_id=? AND id=?",
       (tid, heavy))
TSENT.clear()
tick_traffic()
check("بعد از تمدید دوباره هشدار می‌دهد", len(tsent_for(heavy)) == 1,
      "دوره‌ی تازه، حجم تازه")



head("آستانه‌ی حجم را هم مالک تعیین می‌کند")

# از راهِ خودِ زمان‌بند، نه صدازدنِ مستقیمِ تابع: تا وقتی این نبود،
# برگرداندنِ مقایسه به `TRAFFIC_WARN_PCT` هیچ دروازه‌ای را قرمز
# نمی‌کرد.
set_rem(traffic_pct=95)
d.exec("UPDATE subscriptions SET notified_80p=0 WHERE tenant_id=? AND id=?",
       (tid, heavy))
TSENT.clear()
tick_traffic()
check("آستانه‌ی ۹۵٪ یعنی ۸۴٪ هنوز هشدار نمی‌گیرد", not tsent_for(heavy),
      f"{len(tsent_for(heavy))} هشدار — با ثابتِ ۸۰ حتماً می‌رفت")

set_rem(traffic_pct=80)
TSENT.clear()
tick_traffic()
check("و با ۸۰٪ همان لحظه می‌رود", len(tsent_for(heavy)) == 1)

set_rem(traffic_pct=0)
d.exec("UPDATE subscriptions SET notified_80p=0 WHERE tenant_id=? AND id=?",
       (tid, heavy))
TSENT.clear()
tick_traffic()
check("و صفر یعنی هیچ‌کس هشدارِ حجم نمی‌گیرد", not TSENT, f"{len(TSENT)} هشدار")

set_rem(traffic_pct=80)
d.exec("UPDATE subscriptions SET notified_80p=0 WHERE tenant_id=? AND id=?",
       (tid, heavy))


head("متن هشدار واقعاً ساخته می‌شود")

# تست‌های بالا send_traffic_notice را قلابی کرده‌اند، پس اگر خودِ متن
# موقع ساخته‌شدن خطا بدهد کسی نمی‌فهمد. این‌جا تابع واقعی را با یک
# ربات قلابی صدا می‌زنیم و به متنِ تولیدشده نگاه می‌کنیم.
RENDER = []


class CaptureBot:
    def send(self, chat_id, text, keyboard=None, **k):
        RENDER.append((text, keyboard))
        return {"ok": True}


class RenderCtx(FakeCtx):
    """Ctx واقعی به پنل وصل می‌شود؛ فقط sub_label را لازم داریم."""

    def sub_label(self, sub, **k):
        return str(sub.get("plan_name") or "اشتراک")


handlers.Ctx = RenderCtx
srow = d.q("SELECT s.*, u.tg_id FROM subscriptions s JOIN users u"
           " ON u.id=s.user_id WHERE s.tenant_id=? AND s.id=?",
           (tid, heavy), one=True)
REAL_NOTICE(t_row, CaptureBot(), srow, 42.0, 50)

check("پیام ساخته و فرستاده شد", len(RENDER) == 1)
body = RENDER[0][0] if RENDER else ""
check("درصد مصرف در متن هست", "۸۴" in body, body.split("\n")[0][:60])
check("باقی‌مانده در متن هست", "۸" in body and "باقی" in body)
check("دکمه‌ی تمدید همین اشتراک را هدف می‌گیرد",
      RENDER and f"renew:{heavy}" in str(RENDER[0][1]),
      "نه «خرید» کلی که مشتری دوباره باید حدس بزند")
check("تگ‌های HTML باز و بسته‌اند",
      body.count("<b>") == body.count("</b>")
      and body.count("<blockquote") == body.count("</blockquote>"),
      "تلگرام پیام با تگ ناقص را اصلاً نمی‌فرستد")

handlers.Ctx = RenderCtx

head("متنِ سفارشی هم دکمه‌ی درست را دارد")

# `expiry_text` از قبل بود ولی مسیرش دکمه‌ی «خرید» کلی می‌داد، نه
# تمدیدِ همین اشتراک — در حالی که کامنتِ خودِ کد در مسیرِ پیش‌فرض
# می‌گوید چرا این غلط است. یک قاعده، دو جا، اصلاح در یکی.
_cfg = DB.tenant_settings(tid)
DB.save_tenant_settings(tid, {**_cfg, "expiry_text":
                              "⏰ {days} روز مانده از {label}"})
_t2 = DB.get_tenant(tid)
RENDER.clear()
_esub = d.q("SELECT s.*, u.tg_id FROM subscriptions s JOIN users u"
            " ON u.id=s.user_id WHERE s.tenant_id=? AND s.id=?",
            (tid, heavy), one=True)
REAL_EXPIRY(_t2, CaptureBot(), _esub, 3)
check("متنِ سفارشیِ انقضا اعمال می‌شود",
      RENDER and "۳ روز مانده" not in RENDER[0][0]
      and "3 روز مانده" in RENDER[0][0],
      RENDER[0][0][:40] if RENDER else "—")
check("و جای‌گذارِ {label} پر می‌شود",
      RENDER and "{label}" not in RENDER[0][0])
check("و دکمه‌اش همین اشتراک را هدف می‌گیرد",
      RENDER and f"renew:{heavy}" in str(RENDER[0][1]),
      "قبلاً «buy» می‌داد: فهرستِ کلِ پلن‌ها و حدس‌زدنِ دوباره")

DB.save_tenant_settings(tid, {**_cfg, "expiry_text": ""})

# ── متنِ حجم ──
_cfg = DB.tenant_settings(tid)
DB.save_tenant_settings(tid, {
    **_cfg, "reminders": {**(_cfg.get("reminders") or {}), "enabled": True,
                          "traffic_text": "{pct}٪ رفت · {left} گیگ مانده از {total}"}})
_t3 = DB.get_tenant(tid)
RENDER.clear()
REAL_NOTICE(_t3, CaptureBot(), _esub, 42.0, 50)
_body = RENDER[0][0] if RENDER else ""
check("متنِ سفارشیِ حجم اعمال می‌شود", "رفت" in _body, _body[:50])
check("و همه‌ی جای‌گذارها پر می‌شوند",
      "{" not in _body, _body[:50])
check("و دکمه‌اش هم همین اشتراک را هدف می‌گیرد",
      RENDER and f"renew:{heavy}" in str(RENDER[0][1]))

DB.save_tenant_settings(tid, _cfg)
handlers.Ctx = FakeCtx



print(f"\n{D}{'─' * 50}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
