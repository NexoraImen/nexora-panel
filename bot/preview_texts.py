"""
پیش‌نمایش متن‌های ربات — همان‌طور که مشتری در تلگرام می‌بیند.

بعد از هر بازنویسی متن، این را اجرا کنید و خروجی را بخوانید.
تست نیست؛ ابزار چشمی است تا لحن و فاصله‌گذاری قبل از تحویل دیده شود.

اجرا:  python3 bot/preview_texts.py
"""
import html
import json
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["BOT_DB_PATH"] = tempfile.mktemp(suffix=".db")

from bot import db                # noqa: E402
import bot.tg as tgmod            # noqa: E402
import bot.handlers as H          # noqa: E402

SENT = []


class FakeBot:
    def __init__(self, token=None):
        self.token = token

    def send(self, chat_id, text, keyboard=None, **kw):
        SENT.append({"to": chat_id, "text": text, "kb": keyboard})
        return {"message_id": len(SENT), "chat": {"id": chat_id}}

    def edit(self, chat_id, message_id, text, keyboard=None, **kw):
        SENT.append({"to": chat_id, "text": text, "kb": keyboard})
        return {"message_id": message_id}

    def edit_markup(self, *a, **k):
        return {}

    def answer_cb(self, *a, **k):
        return True

    def send_photo(self, chat_id, photo, caption=None, keyboard=None, **kw):
        SENT.append({"to": chat_id, "text": caption or "[عکس]", "kb": keyboard})
        return {"message_id": len(SENT)}

    def send_photo_bytes(self, chat_id, data, filename="qr.png", caption=None,
                         keyboard=None, **kw):
        # امضا باید با Bot واقعی یکی باشد، وگرنه مسیر کیوآر در
        # پیش‌نمایش بی‌صدا رد می‌شود و دقیقاً همان چیزی را نشان
        # نمی‌دهد که مشتری می‌بیند
        SENT.append({"to": chat_id, "text": caption or "[تصویر کیوآر]",
                     "kb": keyboard, "qr": True, "bytes": len(data or b"")})
        return {"message_id": len(SENT)}

    def copy(self, *a, **k):
        return {"message_id": 1}

    def send_doc(self, *a, **k):
        return {"message_id": 1}

    def member_status(self, *a, **k):
        return "member"

    def me(self):
        return {"username": "NexoraBot"}


class FakeXUI:
    def __init__(self, *a, **kw):
        pass

    def create_subscription(self, inbound_id, email, gb, days, ip_limit=2,
                            tg_id=None, sub_base_url=None, inbound_ids=None,
                            start_on_use=False):
        return {"email": email, "uuid": "u1", "sub_id": email,
                "sub_url": f"https://sub.nexora.ir/sub/{email}",
                "configs": [], "expiry_ms": 1800000000000, "gb": gb}

    def extend_subscription(self, *a, **k):
        return {"ok": True, "expiry_ms": 1800000000000}

    def client_traffic(self, email):
        # ۱۸.۴ گیگ از ۵۰ گیگ مصرف شده — تا نوار مصرف واقعی دیده شود
        return {"email": email, "up": 4 * 1024 ** 3,
                "down": int(14.4 * 1024 ** 3), "total": 0}

    def find_client(self, *a, **k):
        return {"id": "u1"}

    def ping(self):
        return True


tgmod.Bot = FakeBot
H.Bot = FakeBot
H.XUI = FakeXUI

db.init_db()

tid = db.create_tenant("Nexora", bot_token="1:T", owner_tg_id=999)
db.update_tenant(tid, panel_url="http://127.0.0.1:2053", panel_user="a",
                 panel_pass="a", admin_group_id=-100123,
                 topics=json.dumps({"receipts": 2, "users": 3, "stats": 4}))
db.save_tenant_settings(tid, {
    "brand": "نکسورا",
    "cards": [{"number": "6037997512345678", "holder": "علی قلعه‌دوز",
               "bank": "ملی", "active": True}],
    "trial_enabled": True,
    "coins": {"per_referral": 10},
    "inbound_id": 1,
    "support_username": "@nexora_support",
})

D = db.TenantDB(tid)
D.exec("""INSERT INTO plans (tenant_id,name,price,gb,days,ip_limit,inbound_id,
                             description,sort_order)
          VALUES (?,?,?,?,?,?,?,?,?)""",
       (tid, "یک‌ماهه پرسرعت", 190_000, 50, 30, 2, 1,
        "مناسب استفاده‌ی روزمره و تماشای ویدیو.", 1))
plan = D.plans()[0]

tenant = db.get_tenant(tid)
bot = FakeBot()

BOX = 62


#: وقتی روشن باشد، متن خامِ هر پیام هم کنار پیش‌نمایش ذخیره می‌شود تا
#: test_fmt بتواند HTML واقعی را بسنجد، نه نسخه‌ی رنگ‌شده‌ی ترمینال را.
RAW = os.getenv("NEXORA_PREVIEW_RAW") == "1"
RAW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        ".preview-raw.txt")
_raw_blocks = []


def render(title, text, kb=None):
    """نمایش پیام همان‌طور که در تلگرام دیده می‌شود."""
    if RAW:
        _raw_blocks.append(f"{title}\x01{text or ''}")

    print(f"\n\033[38;5;245m{'─' * BOX}\033[0m")
    print(f"\033[38;5;117m{title}\033[0m")
    print(f"\033[38;5;245m{'─' * BOX}\033[0m")

    t = text or "(خالی)"

    # blockquote اول از همه: تلگرام آن را با یک نوار کناری نشان
    # می‌دهد، و کل دلیل استفاده‌مان از آن همین جداشدنِ دیداری است.
    # اگر اینجا رندر نشود، پیش‌نمایش دقیقاً همان چیزی را نشان
    # نمی‌دهد که مشتری می‌بیند و قضاوت روی آن بی‌معنی است.
    def _quote(bar, tint):
        def inner(m):
            body = m.group(1).strip()
            return "\n".join(f"\033[38;5;{tint}m{bar}\033[0m "
                             f"\033[38;5;250m{ln}\033[0m"
                             for ln in body.split("\n"))
        return inner

    # جمع‌شونده اول، وگرنه الگوی ساده آن را هم می‌گیرد و تفاوتشان گم می‌شود
    t = re.sub(r"<blockquote expandable>(.*?)</blockquote>",
               _quote("▾", 180), t, flags=re.S)
    t = re.sub(r"<blockquote>(.*?)</blockquote>", _quote("▌", 108), t, flags=re.S)

    # لینک: در تلگرام فقط متن دیده می‌شود و آدرس زیرش پنهان است
    t = re.sub(r'<a href="([^"]*)">(.*?)</a>',
               lambda m: f"\033[4;38;5;117m{m.group(2)}\033[0m"
                         f"\033[38;5;240m ({m.group(1)})\033[0m",
               t, flags=re.S)

    # تگ‌های تلگرام را به شکل خوانا در ترمینال درمی‌آوریم
    t = re.sub(r"<b>", "\033[1m", t)
    t = re.sub(r"</b>", "\033[0m", t)
    t = re.sub(r"<i>", "\033[3;38;5;245m", t)
    t = re.sub(r"</i>", "\033[0m", t)
    t = re.sub(r"<u>", "\033[4m", t)
    t = re.sub(r"</u>", "\033[0m", t)
    t = re.sub(r"<code>", "\033[38;5;222m", t)
    t = re.sub(r"</code>", "\033[0m", t)
    t = re.sub(r"<pre>", "\033[38;5;222m", t)
    t = re.sub(r"</pre>", "\033[0m", t)
    t = re.sub(r"<s>", "\033[9;38;5;245m", t)
    t = re.sub(r"</s>", "\033[0m", t)
    t = re.sub(r"<tg-spoiler>", "\033[48;5;238m", t)
    t = re.sub(r"</tg-spoiler>", "\033[0m", t)
    print(html.unescape(t))

    if kb:
        try:
            rows = json.loads(kb).get("inline_keyboard", [])
        except (TypeError, ValueError, AttributeError):
            rows = kb if isinstance(kb, list) else []
        for row in rows:
            labels = " | ".join(b.get("text", "") for b in row)
            print(f"\033[38;5;108m[ {labels} ]\033[0m")


def up_msg(tg_id, text, first_name="علی"):
    return {"message": {"message_id": 1, "text": text,
                        "chat": {"id": tg_id, "type": "private"},
                        "from": {"id": tg_id, "first_name": first_name,
                                 "is_bot": False}}}


def up_cb(tg_id, data):
    return {"callback_query": {"id": "c", "data": data,
                               "from": {"id": tg_id, "first_name": "علی",
                                        "is_bot": False},
                               "message": {"message_id": 1,
                                           "chat": {"id": tg_id}}}}


def shot(title, update):
    SENT.clear()
    H.dispatch(tenant, bot, update)
    for m in SENT:
        if m["text"]:
            render(title, m["text"], m.get("kb"))
            title = title + " (ادامه)"


print("\n\033[1m پیش‌نمایش متن‌های ربات نکسورا \033[0m")

shot("۱. خوش‌آمد / منوی اصلی", up_msg(555, "/start"))
D.exec("UPDATE users SET phone='989120000000' WHERE tenant_id=? AND tg_id=?",
       (tid, 555))
shot("۱. خوش‌آمد / منوی اصلی", up_msg(555, "/start"))
shot("۲. لیست پلن‌ها", up_cb(555, "buy"))
shot("۳. جزئیات پلن", up_cb(555, f"plan:{plan['id']}"))
shot("۴. سفارش و کارت‌به‌کارت", up_cb(555, f"chk:{plan['id']}:0"))
shot("۵. بعد از فرستادن رسید", up_msg(555, "واریز شد، ۱۹۰ هزار تومان"))

order = D.q("SELECT * FROM orders WHERE tenant_id=? ORDER BY id DESC LIMIT 1",
            (tid,), one=True)
ctx = H.Ctx(bot, tenant)
SENT.clear()
H.approve_order(ctx, order["id"], 999)
for m in SENT:
    if m["text"] and "تحویل" not in str(m["text"]):
        render("۶. تحویل اشتراک", m["text"], m.get("kb"))
        break

shot("۷. اشتراک‌های من", up_cb(555, "mysubs"))
shot("۸. کیف پول", up_cb(555, "wallet"))
shot("۹. سکه‌ها", up_cb(555, "coins"))
shot("۱۰. دعوت دوستان", up_cb(555, "ref"))
shot("۱۱. سفارش‌های من", up_cb(555, "myorders"))
shot("۱۲. آموزش نصب", up_cb(555, "help"))
shot("۱۳. پشتیبانی", up_cb(555, "support"))

SENT.clear()
H.do_reject(ctx, order["id"], 999, "تصویر رسید خوانا نبود. "
            "یک عکس واضح‌تر یا متن پیامک بانک بفرستید.")
for m in SENT:
    render("۱۴. رد شدن رسید", m["text"], m.get("kb"))
    break

sub = D.q("SELECT s.*, p.name AS plan_name, u.tg_id FROM subscriptions s "
          "LEFT JOIN plans p ON p.id=s.plan_id "
          "LEFT JOIN users u ON u.id=s.user_id "
          "WHERE s.tenant_id=? LIMIT 1", (tid,), one=True)
if sub:
    SENT.clear()
    H.send_expiry_notice(tenant, bot, sub, 3)
    for m in SENT:
        render("۱۵. یادآوری انقضا", m["text"], m.get("kb"))
        break

shot("۱۶. پنل مدیریت", up_cb(999, "admin"))
shot("۱۷. رسیدها (مدیریت)", up_cb(999, "adm:orders"))
shot("۱۸. کاربران (مدیریت)", up_cb(999, "adm:users"))
shot("۱۹. آمار (مدیریت)", up_cb(999, "adm:stats"))
shot("۲۰. پلن‌ها (مدیریت)", up_cb(999, "adm:plans"))
shot("۲۱. جزئیات یک کاربر", up_cb(999, f"adm:u:555"))
shot("۲۲. پیام همگانی", up_cb(999, "adm:bc"))
shot("۲۳. جست‌وجوی کاربر", up_cb(999, "adm:find"))
shot("۲۴. تغییر سکه", up_cb(999, "adm:coin:555"))
shot("۲۵. تغییر موجودی", up_cb(999, "adm:bal:555"))
shot("۲۶. پیام به یک کاربر", up_cb(999, "adm:msg:555"))

# ── صفحه‌ی تمدید ──
_s = D.q("SELECT * FROM subscriptions WHERE tenant_id=? LIMIT 1", (tid,), one=True)
if _s:
    shot("۲۷. تمدید اشتراک", up_cb(555, f"renew:{_s['id']}"))

# ── شارژ کیف پول ──
shot("۲۸. انتخاب مبلغ شارژ", up_cb(555, "topup"))
shot("۲۹. کارت برای شارژ", up_cb(555, "topup:200000"))

# ── همکاری در فروش ──
shot("۳۰. پنل همکار فروش", up_cb(555, "affiliate"))

# ── تیکت و پاسخش ──
SENT.clear()
H.dispatch(tenant, bot, up_cb(555, "support"))
H.dispatch(tenant, bot, up_msg(555, "اینترنتم قطع و وصل می‌شود"))
for m in SENT:
    if m["text"] and "ثبت شد" in str(m["text"]):
        render("۳۱. تیکت ثبت شد", m["text"], m.get("kb"))
        break

_tk = D.q("SELECT * FROM tickets WHERE tenant_id=? ORDER BY id DESC LIMIT 1",
          (tid,), one=True)
if _tk:
    shot("۳۲. پاسخ به تیکت (مدیریت)", up_cb(999, f"tk:{_tk['id']}"))
    SENT.clear()
    H.dispatch(tenant, bot, up_msg(999, "مشکل از سرور بود، الان درست شد."))
    for m in SENT:
        if m["to"] == 555:
            render("۳۳. پاسخ پشتیبانی (از دید مشتری)", m["text"], m.get("kb"))
            break

# ── اطلاع به معرف ──
SENT.clear()
_inv = D.get_user(555)
H.dispatch(tenant, bot, up_msg(7788, f"/start {_inv['ref_code']}", "مهمان"))
for m in SENT:
    if m["to"] == 555:
        render("۳۴. یک نفر با لینک شما آمد", m["text"], m.get("kb"))
        break

# ── سکه بابت خرید زیرمجموعه ──
SENT.clear()
# Earning coins is Pro (bot/pro/loyalty.py); the Community tree has no such text.
_LOY = H.pro("loyalty")
if _LOY is None:
    print("  (۳۵. سکه گرفتید — Pro, not in this tree)")
else:
    _LOY.reward_referrer(ctx, D.get_user(7788), order["id"])
    for m in SENT:
        if m["to"] == 555:
            render("۳۵. سکه گرفتید", m["text"], m.get("kb"))
            break

# ── تمدید خودکار ──
if _s:
    D.exec("UPDATE users SET balance=500000 WHERE tenant_id=? AND tg_id=?", (tid, 555))
    _row = D.q("""SELECT s.*, u.tg_id, u.balance FROM subscriptions s
                  JOIN users u ON u.id=s.user_id
                  WHERE s.tenant_id=? AND s.id=?""", (tid, _s["id"]), one=True)
    SENT.clear()
    try:
        H.auto_renew_subscription(tenant, bot, _row)
        for m in SENT:
            if m["to"] == 555:
                render("۳۶. تمدید خودکار انجام شد", m["text"], m.get("kb"))
                break
    except Exception:
        pass

    # و حالت موجودی ناکافی
    D.exec("UPDATE users SET balance=0 WHERE tenant_id=? AND tg_id=?", (tid, 555))
    _row2 = D.q("""SELECT s.*, u.tg_id, u.balance FROM subscriptions s
                   JOIN users u ON u.id=s.user_id
                   WHERE s.tenant_id=? AND s.id=?""", (tid, _s["id"]), one=True)
    SENT.clear()
    try:
        H.auto_renew_subscription(tenant, bot, _row2)
        for m in SENT:
            if m["to"] == 555:
                render("۳۷. تمدید خودکار ناموفق", m["text"], m.get("kb"))
                break
    except Exception:
        pass

# ── تست رایگان ──
shot("۳۸. تست رایگان", up_cb(7788, "trial"))

# ── وضعیت سفارش ──
shot("۳۹. وضعیت سفارش", up_cb(555, f"ost:{order['id']}"))

# ── گزارش روزانه به گروه ──
SENT.clear()
try:
    H.send_daily_report(tenant)
    for m in SENT:
        render("۴۰. گزارش روزانه (گروه مدیریت)", m["text"], m.get("kb"))
        break
except Exception:
    pass

print(f"\n\033[38;5;245m{'─' * BOX}\033[0m")
print("پایان پیش‌نمایش.\n")

# متن خام برای test_fmt — با \x00 بین پیام‌ها، چون خود پیام‌ها
# هر نویسه‌ی چاپی دیگری می‌توانند داشته باشند.
if RAW:
    with io.open(RAW_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\x00".join(_raw_blocks))
