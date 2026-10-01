"""
تست انتها-به-انتها: یک کاربر واقعی از /start تا دریافت کانفیگ.

تلگرام و پنل 3x-ui هر دو شبیه‌سازی می‌شوند، پس این تست بدون
سرور واقعی هم اجرا می‌شود و کل مسیر را می‌سنجد.

اجرا:  python3 tests/bot/test_flow.py
"""
import io
import json
import os
# repo root and bot/ — these tests moved from bot/ to tests/bot/ (2.0 layout)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOT_DIR = os.path.join(_ROOT_DIR, "bot")

import sys
import tempfile

sys.path.insert(0, _ROOT_DIR)

tmp = tempfile.mktemp(suffix=".db")
os.environ["BOT_DB_PATH"] = tmp

from bot import db, core          # noqa: E402
import bot.tg as tgmod            # noqa: E402
import bot.handlers as H          # noqa: E402
import bot.xui as xuimod          # noqa: E402

# Payouts (partner commission, referrer coins) are Pro since 2.0 and run
# through handlers.after_paid_order. With the Pro modules present this file
# tests them licensed; tests/pro/test_payouts.py covers the locked and the
# failing cases. The Community tree has no payouts: there the checks below
# expect none, and that the sale still closes.
PRO_PAY = H.pro("affiliates") is not None and H.pro("loyalty") is not None
if PRO_PAY:
    _pa0 = H.pro_allowed
    H.pro_allowed = lambda f, _pa0=_pa0: f in ("affiliates", "loyalty") or _pa0(f)

PASS = FAIL = 0
SENT = []
ACTIONS = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def section(t):
    print(f"\n{'─' * 52}\n{t}\n{'─' * 52}")


# ═══════════════ شبیه‌ساز تلگرام ═══════════════
class FakeBot:
    def __init__(self, token=None):
        self.token = token

    def send(self, chat_id, text, keyboard=None, parse_mode="HTML",
             topic_id=None, **kw):
        SENT.append({"to": chat_id, "text": text, "kb": keyboard, "topic": topic_id})
        return {"message_id": len(SENT), "chat": {"id": chat_id}}

    def edit(self, chat_id, message_id, text, keyboard=None, parse_mode="HTML"):
        SENT.append({"to": chat_id, "text": text, "kb": keyboard, "edit": True})
        return {"message_id": message_id}

    def edit_markup(self, chat_id, message_id, keyboard=None):
        return {"message_id": message_id}

    def answer_cb(self, cb_id, text=None, alert=False):
        return True

    def send_photo(self, chat_id, photo, caption=None, keyboard=None, topic_id=None):
        SENT.append({"to": chat_id, "text": caption or "[عکس]", "photo": True,
                     "topic": topic_id})
        return {"message_id": len(SENT)}

    def send_photo_bytes(self, chat_id, data, filename="qr.png", caption=None,
                         keyboard=None):
        # امضای واقعی؛ اگر عوض شود این تست باید بشکند نه اینکه بی‌صدا
        # از کنارش رد شود
        SENT.append({"to": chat_id, "text": caption or "[تصویر]",
                     "photoBytes": bytes(data), "file": filename})
        return {"message_id": len(SENT)}

    def action(self, chat_id, kind="typing"):
        ACTIONS.append({"to": chat_id, "kind": kind})
        return True

    def copy(self, chat_id, from_chat_id, message_id, caption=None, **kw):
        SENT.append({"to": chat_id, "text": caption or "[کپی]", "topic": kw.get("topic_id")})
        return {"message_id": len(SENT)}

    def send_doc(self, *a, **k):
        return {"message_id": 1}

    def member_status(self, chat_id, user_id):
        return "member"

    def me(self):
        return {"username": "NexoraTestBot"}


# ═══════════════ شبیه‌ساز پنل 3x-ui ═══════════════
class FakeXUI:
    """شبیه‌ساز پنل 3x-ui با همان امضای واقعی."""
    NEG = False
    LAST_ON_USE = None

    def __init__(self, *a, **kw):
        self.created = []
        self.extended = []

    def create_subscription(self, inbound_id, email, gb, days, ip_limit=2,
                            tg_id=None, sub_base_url=None, inbound_ids=None,
                            start_on_use=False):
        self.created.append(email)
        FakeXUI.LAST_ON_USE = start_on_use
        base = sub_base_url or "https://sub.nexora.test/sub"
        # Like 3x-ui: "start after first use" answers with a negative
        # duration. Off by default here so older checks keep their dates.
        if FakeXUI.NEG and start_on_use and days:
            return {"email": email, "uuid": f"uuid-{len(self.created)}", "sub_id": email,
                    "sub_url": f"{base.rstrip('/')}/{email}", "configs": [],
                    "expiry_ms": -int(days) * 86400000, "gb": gb}
        return {
            "email": email,
            "uuid": f"uuid-{len(self.created)}",
            "sub_id": email,
            "sub_url": f"{base.rstrip('/')}/{email}",
            "configs": [],
            "expiry_ms": 1800000000000,
            "gb": gb,
        }

    def extend_subscription(self, inbound_id, client_uuid, add_days,
                            add_gb=None, reset_traffic=False, email=None):
        # امضا باید عیناً با XUI واقعی بخواند، وگرنه تستِ سبز
        # چیزی را تضمین نمی‌کند که در عمل TypeError می‌دهد
        self.extended.append(email or client_uuid)
        return {"ok": True, "expiry_ms": 1800000000000}

    def inbounds(self):
        return [{"id": 28, "remark": "FR-1", "enable": True},
                {"id": 41, "remark": "FR-2", "enable": True},
                {"id": 45, "remark": "TR", "enable": False}]

    def client_traffic(self, email):
        return {"email": email, "up": 0, "down": 0, "total": 0}

    def find_client(self, inbound_id, email=None, client_uuid=None):
        return {"id": "uuid-1", "email": email}

    def ping(self):
        return True


tgmod.Bot = FakeBot
H.Bot = FakeBot
H.XUI = FakeXUI

db.init_db()

# ═══════════════ آماده‌سازی ═══════════════
section("آماده‌سازی مستاجر")

tid = db.create_tenant("Nexora", bot_token="123:TEST", owner_tg_id=999)
db.update_tenant(tid, panel_url="http://127.0.0.1:2053", panel_user="admin",
                 panel_pass="admin", admin_group_id=-100123,
                 topics=json.dumps({"receipts": 2, "users": 3, "stats": 4,
                                    "renewals": 5, "alerts": 6}))
db.save_tenant_settings(tid, {
    "brand": "Nexora VPN",
    "cards": [{"number": "6037111122223333", "holder": "علی محمدی", "active": True}],
    "trial_enabled": True,
    "coins": {"per_referral": 10},
    "inbound_id": 1,
})

D = db.TenantDB(tid)
D.exec("""INSERT INTO plans (tenant_id,name,price,gb,days,inbound_id,sort_order)
          VALUES (?,?,?,?,?,?,?)""", (tid, "۳۰ گیگ / ۳۰ روز", 200_000, 30, 30, 1, 1))
D.exec("""INSERT INTO plans (tenant_id,name,price,gb,days,inbound_id,is_trial)
          VALUES (?,?,?,?,?,?,1)""", (tid, "تست رایگان", 0, 1, 1, 1))
plan = D.plans()[0]
check("مستاجر و پلن آماده", bool(tid and plan), f"پلن: {plan['name']}")

tenant = db.get_tenant(tid)
bot = FakeBot()


def up_msg(tg_id, text, first_name="علی"):
    return {"update_id": len(SENT) + 1,
            "message": {"message_id": 1, "text": text,
                        "chat": {"id": tg_id, "type": "private"},
                        "from": {"id": tg_id, "first_name": first_name,
                                 "is_bot": False}}}


def up_cb(tg_id, data):
    return {"update_id": len(SENT) + 1,
            "callback_query": {"id": "cb1", "data": data,
                               "from": {"id": tg_id, "first_name": "علی", "is_bot": False},
                               "message": {"message_id": 1, "chat": {"id": tg_id}}}}


def last():
    return SENT[-1]["text"] if SENT else ""


# ═══════════════ جریان کاربر ═══════════════
section("جریان کاربر: /start تا خرید")

SENT.clear()
H.dispatch(tenant, bot, up_msg(555, "/start"))
u = D.get_user(555)
check("کاربر ساخته شد", bool(u), f"کد معرف: {u['ref_code'] if u else '—'}")
check("پیام خوش‌آمد ارسال شد", len(SENT) > 0 and len(last()) > 10)

SENT.clear()
H.dispatch(tenant, bot, up_cb(555, "buy"))
check("لیست پلن‌ها نمایش داده شد", "پلن" in last() or plan["name"] in last())
check("پلن تست در لیست خرید نیست", "تست رایگان" not in last())

SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"plan:{plan['id']}"))
check("جزئیات پلن", plan["name"] in last() or "200" in last().replace("،", ","))

SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"chk:{plan['id']}:0"))
order = D.q("SELECT * FROM orders WHERE tenant_id=? ORDER BY id DESC", (tid,), one=True)
check("سفارش ساخته شد", bool(order), f"#{order['id'] if order else '—'}")
check("شماره کارت نمایش داده شد", "6037" in last().replace("-", ""))
check("وضعیت انتظار رسید", D.get_user(555)["state"] == "await_receipt",
      D.get_user(555)["state"] or "—")

# ═══════════════ رسید ═══════════════
section("ارسال و تایید رسید")

SENT.clear()
photo_msg = {"update_id": 99,
             "message": {"message_id": 5,
                         "chat": {"id": 555, "type": "private"},
                         "from": {"id": 555, "first_name": "علی", "is_bot": False},
                         "photo": [{"file_id": "PHOTO123"}]}}
H.dispatch(tenant, bot, photo_msg)
order = D.get_order(order["id"])
check("رسید ثبت شد", order["receipt_file"] == "PHOTO123" or order["receipt_type"] == "photo",
      f"وضعیت: {order['status']}")
check("در صف بررسی قرار گرفت", order["status"] in ("awaiting", "review"), order["status"])

to_group = [s for s in SENT if s["to"] == -100123]
check("اعلان در گروه مدیریت", len(to_group) > 0, f"{len(to_group)} پیام")
check("در تاپیک رسیدها", any(s.get("topic") == 2 for s in to_group))

SENT.clear()
H.dispatch(tenant, bot, up_cb(999, f"ap:{order['id']}"))
order = D.get_order(order["id"])
check("سفارش تایید شد", order["status"] == "approved", order["status"])

sub = D.q("SELECT * FROM subscriptions WHERE tenant_id=? ORDER BY id DESC", (tid,), one=True)
check("اشتراک ساخته شد", bool(sub), sub["client_email"] if sub else "—")
check("لینک اشتراک تولید شد", bool(sub and sub["sub_url"]),
      sub["sub_url"] if sub else "—")

to_user = [s for s in SENT if s["to"] == 555]
check("کانفیگ برای کاربر ارسال شد", len(to_user) > 0, f"{len(to_user)} پیام")

# ═══════════════ معرفی و سکه ═══════════════
section("سیستم معرفی و سکه")

inviter = D.get_user(555)
SENT.clear()
H.dispatch(tenant, bot, up_msg(777, f"/start {inviter['ref_code']}", "رضا"))
u2 = D.get_user(777)
check("کاربر دعوت‌شده ثبت شد", bool(u2))
check("رابطه معرف ثبت شد", u2["referred_by"] == inviter["id"],
      f"معرف: {u2['referred_by']}")

check("قبل از خرید سکه‌ای داده نمی‌شود", D.get_user(555)["coins"] == 0,
      f"{D.get_user(555)['coins']} سکه")

o2 = D.create_order(u2["id"], plan["id"], 200_000, 200_000)
D.exec("UPDATE orders SET status='awaiting' WHERE tenant_id=? AND id=?", (tid, o2["id"]))
SENT.clear()
H.dispatch(tenant, bot, up_cb(999, f"ap:{o2['id']}"))
if PRO_PAY:
    check("بعد از خرید زیرمجموعه، معرف سکه گرفت", D.get_user(555)["coins"] == 10,
          f"{D.get_user(555)['coins']} سکه")
else:
    # Earning coins is Pro. Spending them is core, so the same 10 coins are
    # given by hand and the spending checks below run in both trees.
    check("Community: no referral coins", D.get_user(555)["coins"] == 0,
          f"{D.get_user(555)['coins']} سکه")
    D.add_coins(inviter["id"], 10, "bonus", "stand-in for the Pro referral reward")

# خوددعوتی
SENT.clear()
self_ref = D.get_user(777)["ref_code"]
H.dispatch(tenant, bot, up_msg(777, f"/start {self_ref}"))
check("خوددعوتی مسدود است", D.get_user(777)["referred_by"] != u2["id"])

# ═══════════════ تخفیف با سکه ═══════════════
section("خرید با تخفیف سکه")

D.add_coins(inviter["id"], 30, "bonus", "تست")
check("موجودی سکه", D.get_user(555)["coins"] == 40, f"{D.get_user(555)['coins']} سکه")

SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"chk:{plan['id']}:1"))
o3 = D.q("SELECT * FROM orders WHERE tenant_id=? ORDER BY id DESC", (tid,), one=True)
check("تخفیف سکه اعمال شد", o3["amount"] == 160_000,
      f"{core.toman(o3['amount'])} از {core.toman(o3['base_amount'])} تومان")
check("سکه‌های مصرفی ثبت شد", o3["coins_used"] == 40, f"{o3['coins_used']} سکه")

# ═══════════════ کیف پول ═══════════════
section("کیف پول و تمدید خودکار")

D.add_balance(inviter["id"], 500_000, "topup", "شارژ تست")
SENT.clear()
H.dispatch(tenant, bot, up_cb(555, "wallet"))
check("نمایش کیف پول", "۵۰۰" in last().replace("،", "").replace(",", ""),
      "موجودی نمایش داده شد")

D.exec("UPDATE subscriptions SET auto_renew=1, expires_at=datetime('now','+1 day') "
       "WHERE tenant_id=? AND id=?", (tid, sub["id"]))
srow = D.q("""SELECT s.*, u.tg_id, u.balance FROM subscriptions s
              JOIN users u ON u.id=s.user_id WHERE s.tenant_id=? AND s.id=?""",
           (tid, sub["id"]), one=True)
bal_before = D.get_user(555)["balance"]
SENT.clear()
H.auto_renew_subscription(tenant, bot, srow)
bal_after = D.get_user(555)["balance"]
check("تمدید خودکار از کیف پول", bal_after == bal_before - plan["price"],
      f"{core.toman(bal_before)} → {core.toman(bal_after)}")
check("به کاربر اطلاع داده شد", any("تمدید" in s["text"] for s in SENT))

# موجودی ناکافی
D.exec("UPDATE users SET balance=1000 WHERE tenant_id=? AND id=?", (tid, inviter["id"]))
srow = D.q("""SELECT s.*, u.tg_id, u.balance FROM subscriptions s
              JOIN users u ON u.id=s.user_id WHERE s.tenant_id=? AND s.id=?""",
           (tid, sub["id"]), one=True)
SENT.clear()
H.auto_renew_subscription(tenant, bot, srow)
check("موجودی ناکافی → فقط هشدار", D.get_user(555)["balance"] == 1000,
      "پولی کسر نشد")
check("کاربر مطلع شد", any("کافی" in s["text"] for s in SENT))

# ═══════════════ یادآوری ═══════════════
section("یادآوری انقضا")

SENT.clear()
H.send_expiry_notice(tenant, bot, srow, 3)
check("یادآوری ۳ روزه", any("3" in s["text"] or "۳" in s["text"] for s in SENT))
SENT.clear()
H.send_expiry_notice(tenant, bot, srow, 0)
check("یادآوری روز آخر", any("امروز" in s["text"] for s in SENT))

# ═══════════════ تست رایگان ═══════════════
section("اشتراک تست رایگان")

# پیش از لینک: اپراتور و سیستم‌عامل با دکمه، نام تایپی (تصمیمِ مالک،
# docs/specs/2026-09-27-shop-funnel.md). مسیری که مشتری واقعاً می‌رود.
SENT.clear()
H.dispatch(tenant, bot, up_cb(777, "trial"))
check("اول اپراتور پرسیده می‌شود، نه لینک",
      "اپراتور" in last() and D.get_user(777)["trial_used"] == 0, last()[:60])
check("دکمه‌های اپراتور همان فهرستِ core‌اند",
      "tinfo:op:irancell" in str(SENT[-1].get("kb")))
H.dispatch(tenant, bot, up_cb(777, "tinfo:op:hacker"))
check("کلیدِ ناشناس ذخیره نمی‌شود", not D.get_user(777).get("operator"))
H.dispatch(tenant, bot, up_cb(777, "tinfo:op:irancell"))
check("بعد سیستم‌عامل", "دستگاه" in last() and D.get_user(777)["operator"] == "irancell")
H.dispatch(tenant, bot, up_cb(777, "tinfo:os:ios"))
check("بعد نام", "اسم" in last())
H.dispatch(tenant, bot, up_msg(777, "https://spam.example"))
check("لینک به‌جای نام پذیرفته نمی‌شود", not D.get_user(777).get("real_name")
      and D.get_user(777)["trial_used"] == 0)
H.dispatch(tenant, bot, up_msg(777, "  سارا   احمدی "))
check("نام ذخیره شد (فاصله‌ها تمیز)", D.get_user(777)["real_name"] == "سارا احمدی")
check("تست رایگان فعال شد", D.get_user(777)["trial_used"] == 1)
SENT.clear()
H.dispatch(tenant, bot, up_cb(777, "trial"))
check("بار دوم رد می‌شود", any("قبلا" in s["text"] or "قبلاً" in s["text"] or
                                 "یک‌بار" in s["text"] for s in SENT) or len(SENT) > 0)

# ═══════════════ دسترسی ادمین ═══════════════
section("کنترل دسترسی")

o4 = D.create_order(u2["id"], plan["id"], 200_000, 200_000)
SENT.clear()
H.dispatch(tenant, bot, up_cb(777, f"ap:{o4['id']}"))
check("کاربر عادی نمی‌تواند تایید کند",
      D.get_order(o4["id"])["status"] != "approved",
      D.get_order(o4["id"])["status"])

D.exec("UPDATE users SET is_blocked=1 WHERE tenant_id=? AND tg_id=?", (tid, 777))
SENT.clear()
H.dispatch(tenant, bot, up_msg(777, "/start"))
check("کاربر مسدود پاسخی نمی‌گیرد", len(SENT) == 0)

# ═══════════════ پورسانت همکار فروش ═══════════════
# رگرسیون: مبلغ سفارش در ستون amount است، نه final_price/price.
# وقتی این‌جا از نام اشتباه خوانده می‌شد، مبلغ صفر می‌شد و
# record_commission بی‌صدا None برمی‌گرداند — یعنی هیچ پورسانتی
# برای هیچ فروشی ثبت نمی‌شد.
section("پورسانت همکار فروش")

D.exec("INSERT INTO affiliates (tenant_id,name,code,tg_id,percent) "
       "VALUES (?,?,?,?,?)", (tid, "همکار تست", "AFFX", 888, 20))
aff_row = D.q("SELECT * FROM affiliates WHERE tenant_id=? AND code='AFFX'",
              (tid,), one=True)

D.create_user(444, "buyer", "خریدار")
buyer = D.get_user(444)
D.exec("UPDATE users SET affiliate_id=? WHERE tenant_id=? AND id=?",
       (aff_row["id"], tid, buyer["id"]))

aff_order = D.create_order(buyer["id"], plan["id"], plan["price"], plan["price"])
D.exec("UPDATE orders SET status='awaiting' WHERE tenant_id=? AND id=?",
       (tid, aff_order["id"]))

SENT.clear()
ok_aff, _ = H.approve_order(H.Ctx(bot, tenant), aff_order["id"], 999)
comm = D.q("SELECT * FROM affiliate_commissions WHERE tenant_id=? AND order_id=?",
           (tid, aff_order["id"]), one=True)
check("سفارش همکار تایید شد", ok_aff)
if PRO_PAY:
    check("پورسانت ثبت شد", bool(comm),
          "هیچ ردیفی ثبت نشد" if not comm else "ثبت شد")
    check("مبلغ فروش درست خوانده شد",
          bool(comm) and comm["order_amount"] == plan["price"],
          f"{(comm or {}).get('order_amount')} به‌جای {plan['price']}")
    check("پورسانت ۲۰٪ درست حساب شد",
          bool(comm) and comm["commission"] == round(plan["price"] * 0.2),
          f"{(comm or {}).get('commission')}")
    check("همکار مطلع شد", any(s["to"] == 888 for s in SENT))
else:
    check("Community: no commission, and the sale still closed",
          not comm and D.get_order(aff_order["id"])["status"] == "approved")

# توابع همکار در ماژول db هستند نه روی TenantDB. وقتی از روی
# ctx.db صدا زده می‌شدند AttributeError می‌گرفتند و این صفحه‌ها
# اصلاً باز نمی‌شدند.
SENT.clear()
H.dispatch(tenant, bot, up_cb(888, "affiliate"))
if PRO_PAY:
    check("پنل همکار باز می‌شود", bool(last()) and "همکاری در فروش" in last(),
          (last() or "پاسخی نیامد")[:34])
    check("مانده‌ی همکار نمایش داده شد", "مانده" in (last() or ""))

    SENT.clear()
    H.dispatch(tenant, bot, up_cb(888, "aff_list"))
    check("ریز فروش‌های همکار باز می‌شود", "ریز فروش‌ها" in (last() or ""),
          (last() or "پاسخی نیامد")[:34])
else:
    # The partner panel is Pro: an old panel button still answers, and says so.
    check("Community: the partner panel button answers that it is not available",
          "در دسترس نیست" in (last() or ""), (last() or "پاسخی نیامد")[:40])

SENT.clear()
H.dispatch(tenant, bot, up_msg(333, f"/start aff_{aff_row['code']}"))
newcomer = D.get_user(333)
check("ورود با لینک همکار ثبت می‌شود",
      bool(newcomer) and newcomer["affiliate_id"] == aff_row["id"],
      f"affiliate_id={(newcomer or {}).get('affiliate_id')}")

# ═══════════════ گزارش ═══════════════
section("گزارش روزانه")

SENT.clear()
H.send_daily_report(tenant)
rep = [s for s in SENT if s["to"] == -100123]
check("گزارش به گروه رفت", len(rep) > 0)
check("در تاپیک آمار", any(s.get("topic") == 4 for s in rep))

# ═══════════════ کیوآر و حالت تایپ ═══════════════
section("کیوآر و حالت تایپ")

import qr as _qr   # noqa: E402

_png = _qr.make("https://sub.example.ir/sub/nexora_555_1")
check("segno نصب است", _qr.available())
check("کیوآر ساخته می‌شود", bool(_png) and _png[:8] == b"\x89PNG\r\n\x1a\n",
      f"{len(_png or b'')} بایت")
check("بدون داده کیوآر نمی‌سازد", _qr.make("") is None)

SENT.clear()
H._send_delivery(H.Ctx(bot, tenant), D.get_user(555),
                 "متن کانفیگ", "https://sub.example.ir/sub/nexora_555_1")
_photos = [s for s in SENT if s.get("photoBytes")]
check("کیوآر همراه کانفیگ فرستاده می‌شود", len(_photos) == 1,
      f"{len(_photos)} تصویر")
check("تصویر واقعاً PNG است",
      bool(_photos) and _photos[0]["photoBytes"][:8] == b"\x89PNG\r\n\x1a\n")
check("متن کانفیگ هم جدا رسیده",
      any("متن کانفیگ" in s["text"] for s in SENT))

# بدون لینک، کیوآری در کار نیست
SENT.clear()
H._send_delivery(H.Ctx(bot, tenant), D.get_user(555), "بدون لینک", None)
check("بدون لینک کیوآر فرستاده نمی‌شود",
      not any(s.get("photoBytes") for s in SENT))

check("پیام‌ها از blockquote استفاده می‌کنند",
      "<blockquote>" in H._waiting_text(H.Ctx(bot, tenant), 1),
      "متن انتظار")

# حالت تایپ باید در مسیر واقعی تایید رسید زده شده باشد — ACTIONS از
# ابتدای اجرا جمع شده است
check("هنگام تایید رسید، «در حال تایپ» نشان داده می‌شود",
      any(a["kind"] == "typing" for a in ACTIONS),
      f"{len(ACTIONS)} بار")

# ═══════════════ اطلاع به معرف ═══════════════
section("اطلاع به معرف")

# معرف باید *همان لحظه‌ی ثبت‌نام* خبردار شود. قبلاً فقط گروه مدیریت
# خبر می‌گرفت و خود معرف هیچ سیگنالی نداشت — از دیدش لینک دعوت کار
# نمی‌کرد، چون سکه هم فقط بعد از خرید می‌آمد و گاهی روزها سکوت بود.
inviter = D.get_user(555)
SENT.clear()
H.dispatch(tenant, bot, up_msg(7788, f"/start {inviter['ref_code']}", "مهمان"))

to_inviter = [s for s in SENT if s["to"] == 555]
if PRO_PAY:
    check("معرف همان لحظه خبردار شد", len(to_inviter) > 0, f"{len(to_inviter)} پیام")
else:
    check("Community: the join notice is Pro, none is sent", not to_inviter,
          f"{len(to_inviter)} پیام")
if to_inviter:
    t = to_inviter[0]["text"]
    check("نام دعوت‌شده آمده", "مهمان" in t)
    check("تعداد کل دعوت‌ها آمده", "نفر را دعوت" in t)
    check("می‌گوید سکه بعد از خرید می‌آید", "خرید" in t and "سکه" in t, t[:60])
    check("از blockquote استفاده شده", "<blockquote>" in t)

newbie = D.get_user(7788)
check("رابطه‌ی معرف ثبت شد", newbie and newbie["referred_by"] == inviter["id"])

# خوددعوتی نباید پیام بسازد
SENT.clear()
H.dispatch(tenant, bot, up_msg(4242, f"/start {inviter['ref_code']}"))
D.exec("DELETE FROM users WHERE tenant_id=? AND tg_id=?", (tid, 4242))

# ═══════════════ دکمه‌ی تمدید ═══════════════
section("دکمه‌ی تمدید")

# این دکمه در «اشتراک‌های من» ساخته می‌شد ولی هیچ شاخه‌ای در
# dispatch نداشت: کاربر می‌زد، هیچ اتفاقی نمی‌افتاد، و چون callback
# بی‌صدا None برمی‌گرداند حتی خطایی در لاگ نبود.
mysub = D.q("SELECT * FROM subscriptions WHERE tenant_id=? AND user_id=? LIMIT 1",
            (tid, inviter["id"]), one=True)
SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"renew:{mysub['id']}"))
check("دکمه‌ی تمدید پاسخ می‌دهد", len(SENT) > 0, f"{len(SENT)} پیام")
if SENT:
    rt = SENT[-1]["text"]
    check("نام پلن نشان داده می‌شود", plan["name"] in rt, rt[:70])
    check("مبلغ تمدید آمده", "مبلغ تمدید" in rt)
    check("blockquote توضیحی دارد", "<blockquote>" in rt)

SENT.clear()
H.dispatch(tenant, bot, up_cb(555, "renew:99999"))
check("اشتراک ناموجود خطای تمیز می‌دهد",
      SENT and "پیدا نشد" in SENT[-1]["text"], SENT[-1]["text"][:40] if SENT else "—")

# ═══════════════ دیپ‌لینک مینی‌اپ ═══════════════
section("دیپ‌لینک مینی‌اپ")

# مینی‌اپ دکمه‌هایی داشت که به `?start=wallet` می‌رفتند، ولی /start
# این مقدار را فقط «کد معرف» می‌خواند و چون کد معتبری نبود بی‌صدا
# دورش می‌ریخت. یعنی دکمه ربات را باز می‌کرد ولی کاربر در منوی
# اصلی رها می‌شد.
SENT.clear()
H.dispatch(tenant, bot, up_msg(555, "/start wallet"))
check("start=wallet به کیف پول می‌رود",
      SENT and "کیف پول" in SENT[-1]["text"],
      SENT[-1]["text"][:60] if SENT else "—")

SENT.clear()
H.dispatch(tenant, bot, up_msg(555, "/start buy"))
check("start=buy به خرید می‌رود",
      SENT and ("خرید اشتراک" in SENT[-1]["text"] or "پلن" in SENT[-1]["text"]),
      SENT[-1]["text"][:60] if SENT else "—")

SENT.clear()
H.dispatch(tenant, bot, up_msg(555, f"/start renew_{mysub['id']}"))
check("start=renew_<id> روی همان اشتراک باز می‌شود",
      SENT and "مبلغ تمدید" in SENT[-1]["text"],
      SENT[-1]["text"][:60] if SENT else "—")

# شناسه‌ی دست‌کاری‌شده نباید اشتراکِ کسِ دیگری را نشان دهد
SENT.clear()
H.dispatch(tenant, bot, up_msg(555, "/start renew_99999"))
check("شناسه‌ی جعلی به اشتراک کسی نمی‌رسد",
      SENT and "پیدا نشد" in SENT[-1]["text"],
      SENT[-1]["text"][:40] if SENT else "—")

# پیلودِ ناشناس نباید کاربر را گم کند — منوی اصلی، نه سکوت
SENT.clear()
H.dispatch(tenant, bot, up_msg(555, "/start چیزخاصی"))
check("پیلود ناشناس به منوی اصلی می‌رسد", len(SENT) > 0, f"{len(SENT)} پیام")

# و کلمه‌های رزرو نباید کد معرف خوانده شوند: کد معرف شش حرف بزرگ
# از همان الفباست، پس WALLET می‌تواند روزی کدِ واقعیِ کسی باشد — و
# آن‌وقت هر کسی که روی «شارژ» بزند بی‌صدا زیرمجموعه‌اش می‌شود.
check("wallet جزو کلمه‌های رزرو است", "wallet" in H.DEEP_WORDS)
check("و کد معرف فقط وقتی خوانده می‌شود که رزرو نباشد",
      "DEEP_WORDS" in io.open("bot/handlers.py", encoding="utf-8").read()
      .split("def _get_or_create")[1].split("def ")[0],
      "وگرنه برخوردِ کد، معرف را اشتباه می‌بندد")

# ═══════════════ پاسخ به تیکت ═══════════════
section("پاسخ به تیکت")

# دکمه‌ی «✍️ پاسخ» در گروه مدیریت ساخته می‌شد ولی هیچ شاخه‌ای در
# dispatch نداشت — ادمین می‌زد و هیچ اتفاقی نمی‌افتاد، پس عملاً هیچ
# تیکتی از داخل تلگرام جواب داده نمی‌شد.
SENT.clear()
H.dispatch(tenant, bot, up_cb(555, "support"))     # وارد حالت await_ticket
H.dispatch(tenant, bot, up_msg(555, "اینترنتم قطع می‌شود"))
tk = D.q("SELECT * FROM tickets WHERE tenant_id=? ORDER BY id DESC LIMIT 1",
         (tid,), one=True)
check("تیکت ثبت شد", bool(tk), f"#{tk['id']}" if tk else "—")

if tk:
    SENT.clear()
    H.dispatch(tenant, bot, up_cb(999, f"tk:{tk['id']}"))
    check("دکمه‌ی پاسخ، ورودی می‌خواهد",
          any("پاسخ به تیکت" in s["text"] for s in SENT), f"{len(SENT)} پیام")

    SENT.clear()
    H.dispatch(tenant, bot, up_msg(999, "مشکل از سرور بود، الان درست شد."))

    to_user = [s for s in SENT if s["to"] == 555]
    check("پاسخ به مشتری رسید", len(to_user) > 0, f"{len(to_user)} پیام")
    if to_user:
        rt = to_user[0]["text"]
        check("متن پاسخ در پیام هست", "الان درست شد" in rt)
        check("شماره پیگیری ذکر شده", f"#{tk['id']}" in rt)
        check("از blockquote استفاده شده", "<blockquote>" in rt)

    after = D.q("SELECT * FROM tickets WHERE tenant_id=? AND id=?",
                (tid, tk["id"]), one=True)
    check("تیکت به answered تغییر کرد",
          after and after["status"] == "answered",
          after["status"] if after else "—")
    check("متن پاسخ ذخیره شد",
          after and "الان درست شد" in (after["answer"] or ""))

# ═══════════════ دکمه‌ی کپی ═══════════════
section("دکمه‌ی کپی")

from tg import kb as _kbc   # noqa: E402

_ck = _kbc([[("کپی", "6037997512345678", "copy")],
            [("لینک", "https://a.ir", "url")],
            [("منو", "menu")]])
_flat = [b for r in _ck["inline_keyboard"] for b in r]
check("دکمه‌ی کپی ساخته می‌شود",
      any(b.get("copy_text", {}).get("text") == "6037997512345678" for b in _flat))
check("کپی با callback قاطی نمی‌شود",
      not any("callback_data" in b and "copy_text" in b for b in _flat))
check("مقدار خالی دکمه‌ی کپی نمی‌سازد",
      not [b for r in _kbc([[("کپی", "", "copy")]])["inline_keyboard"] for b in r])

# شماره‌ی کارت باید بدون خط تیره کپی شود، وگرنه اپ بانک رد می‌کند
SENT.clear()
H.checkout(H.Ctx(bot, tenant), D.get_user(555), 555, None, plan["id"], 0)
_last_kb = SENT[-1].get("kb") or {}
_copies = [b.get("copy_text", {}).get("text")
           for r in _last_kb.get("inline_keyboard", []) for b in r
           if "copy_text" in b]
check("شماره کارت بدون خط تیره کپی می‌شود",
      any(c and c.isdigit() and len(c) == 16 for c in _copies), str(_copies))

# ═══════════════ دکمه‌ی url نامعتبر ═══════════════
section("دکمه‌ی url نامعتبر")

# تلگرام دکمه‌ی شیشه‌ای را فقط با http/https/tg می‌پذیرد. اسکیم
# اپلیکیشن‌ها (happ://) کل پیام را رد می‌کرد، نه فقط آن دکمه را —
# یعنی کانفیگ ساخته می‌شد ولی هیچ‌وقت به مشتری نمی‌رسید.
from tg import kb as _kb, valid_button_url as _vbu   # noqa: E402

check("اسکیم اپلیکیشن نامعتبر است", not _vbu("happ://add/x"))
check("https معتبر است", _vbu("https://sub.example.ir/sub/x"))
check("tg معتبر است", _vbu("tg://resolve?domain=x"))

_mixed = _kb([[("اپ", "happ://add/x", "url"), ("سایت", "https://a.ir", "url")],
              [("منو", "menu")]])
_urls = [b.get("url") for r in _mixed["inline_keyboard"] for b in r if "url" in b]
check("دکمه‌ی نامعتبر حذف می‌شود، معتبر می‌ماند",
      _urls == ["https://a.ir"], str(_urls))
check("دکمه‌ی callback دست‌نخورده می‌ماند",
      any("callback_data" in b for r in _mixed["inline_keyboard"] for b in r))

# دکمه‌ی کپی تلگرام — لینک اشتراک با یک ضربه در کلیپ‌بورد
_cp = _kb([[("کپی", "https://sub.ir/x", "copy")], [("خالی", "", "copy")]])
_flat = [b for r in _cp["inline_keyboard"] for b in r]
check("دکمه‌ی کپی ساخته می‌شود",
      len(_flat) == 1 and _flat[0].get("copy_text", {}).get("text") == "https://sub.ir/x",
      str(_flat))
check("دکمه‌ی کپی خالی ساخته نمی‌شود", len(_flat) == 1)

# و اگر باز هم تلگرام صفحه‌کلید را رد کرد، متن باید برسد
_real_send = FakeBot.send
_calls = {"n": 0}


def _picky_send(self, chat_id, text, keyboard=None, **k):
    _calls["n"] += 1
    if keyboard is not None:
        raise H.TelegramError("Bad Request: BUTTON_URL_INVALID")
    return _real_send(self, chat_id, text, keyboard=None, **k)


FakeBot.send = _picky_send
SENT.clear()
H._send_delivery(H.Ctx(bot, tenant), D.get_user(555), "متن کانفیگ", "happ://x")
FakeBot.send = _real_send
check("رد شدن صفحه‌کلید، جلوی رسیدن کانفیگ را نمی‌گیرد",
      any("متن کانفیگ" in s["text"] for s in SENT), f"{len(SENT)} پیام")

# ═══════════════ شکست ساخت کانفیگ هنگام تایید ═══════════════
section("شکست ساخت کانفیگ هنگام تایید")

# سناریوی واقعی گزارش‌شده: ادمین ✅ می‌زند، کانفیگ ساخته نمی‌شود،
# هیچ پیامی نمی‌آید و همان رسید دوباره منتظر تایید می‌ماند.
# دو باگ داشت: نتیجه‌ی approve_order دور ریخته می‌شد، و سفارش قبل از
# ساخت کانفیگ approved می‌شد و بعد برای همیشه گیر می‌کرد.
u3 = D.get_user(555)
o_fail = D.create_order(u3["id"], plan["id"], plan["price"], plan["price"])
D.exec("UPDATE orders SET status='awaiting' WHERE tenant_id=? AND id=?",
       (tid, o_fail["id"]))

_real_create = H.XUI.create_subscription


def _boom(self, *a, **k):
    raise H.XUIError("پنل: inbound not found")


H.XUI.create_subscription = _boom
SENT.clear()
H.dispatch(tenant, bot, up_cb(999, f"ap:{o_fail['id']}"))
o_after = D.get_order(o_fail["id"])

check("سفارش با شکست ساخت، approved نمی‌شود",
      o_after["status"] != "approved", o_after["status"])
admin_msgs = [s for s in SENT if s["to"] == 999]
check("خطا به ادمین گزارش می‌شود", len(admin_msgs) > 0,
      f"{len(admin_msgs)} پیام")
check("متن خطای واقعی پنل دیده می‌شود",
      any("inbound not found" in s["text"] for s in admin_msgs))
check("برای مشتری کانفیگی فرستاده نمی‌شود",
      len([s for s in SENT if s["to"] == 555]) == 0)

# حالا مشکل رفع شد — تایید دوباره باید کار کند، نه اینکه بگوید
# «قبلاً تایید شده»
H.XUI.create_subscription = _real_create
SENT.clear()
H.dispatch(tenant, bot, up_cb(999, f"ap:{o_fail['id']}"))
o_retry = D.get_order(o_fail["id"])
check("تلاش دوباره بعد از رفع مشکل موفق است",
      o_retry["status"] == "approved", o_retry["status"])
check("این بار کانفیگ برای مشتری رفت",
      len([s for s in SENT if s["to"] == 555]) > 0)

# ═══════════════ اینباند پیش‌فرض تنظیم‌نشده ═══════════════
section("اینباند پیش‌فرض تنظیم‌نشده")

# روی سرور واقعی، default_inbound خالی بود و پلن هم inbound_id نداشت.
# قبلاً provision همین‌جا شکست می‌خورد و مشتری بعد از پرداخت هیچ
# کانفیگی نمی‌گرفت — بدترین حالت ممکن.
D.exec("UPDATE tenants SET default_inbound=NULL WHERE id=?", (tid,))
D.exec("""INSERT INTO plans (tenant_id,name,price,gb,days,inbound_id,sort_order)
          VALUES (?,?,?,?,?,?,?)""", (tid, "بدون اینباند", 150_000, 20, 20, None, 9))
free_plan = [p for p in D.plans() if p["name"] == "بدون اینباند"][0]

u2 = D.get_user(555)
o_free = D.create_order(u2["id"], free_plan["id"], free_plan["price"],
                        free_plan["price"])
ctx_free = H.Ctx(bot, db.get_tenant(tid))
okp, resp = H.provision(ctx_free, o_free["id"])
check("بدون اینباند پیش‌فرض هم کانفیگ ساخته می‌شود", okp,
      resp if not okp else f"اشتراک #{resp.get('id')}")
if okp:
    made = D.q("SELECT inbound_id FROM subscriptions WHERE tenant_id=? AND id=?",
               (tid, resp["id"]), one=True)
    check("اولین اینباند فعال انتخاب شد", made and made["inbound_id"] == 28,
          f"inbound #{made['inbound_id'] if made else '—'}")

# ═══════════════════════════════════════════════════════════
section("همکار نمی‌تواند مشتریِ خودش شود")

# مسیر «دعوت دوست» شرط خوددعوتی را داشت، مسیر همکاری نداشت. همکاری
# که هنوز با ربات کار نکرده، با بازکردن لینک خودش مشتریِ خودش می‌شد
# و از هر خریدِ خودش پورسانت می‌گرفت — تخفیفی که قرار نبود باشد.

HSRC = io.open(H.__file__, encoding="utf-8").read()
_blk = HSRC[HSRC.index('if arg.startswith("aff_")'):]
_blk = _blk[:_blk.index("u = ctx.db.create_user")]
check("شرط خودمعرفی برای همکار هم هست",
      'affiliate.get("tg_id") == tg_user["id"]' in _blk,
      "همان قاعده‌ای که مسیر دعوت دوست دارد")
check("و در آن حالت اصلا وصل نمی‌شود", "affiliate = None" in _blk)
check("مسیر دعوت دوست هنوز شرط خودش را دارد",
      'inviter["tg_id"] != tg_user["id"]' in _blk,
      "اصلاح این یکی نباید آن یکی را برداشته باشد")


# ═══════════════════════════════════════════════════════════
section("وضعیت سفارش باید درباره‌ی پول راست بگوید")

# دو خطا در دو جهت، که جمعشان عددی می‌ساخت که درست به نظر می‌رسید:
#
#   • خرید با کیف پول هیچ‌وقت approved نمی‌شد. کانفیگ ساخته و تحویل
#     می‌شد و سفارش pending می‌ماند؛ جاروکشِ سفارش‌های منقضی نیم‌ساعت
#     بعد آن را «منقضی» می‌کرد. فروشِ انجام‌شده در هیچ آماری نبود.
#
#   • تمدید خودکار برعکس: *قبل* از ساخت approved می‌شد. اگر ساخت
#     شکست می‌خورد پول برمی‌گشت و سفارش approved می‌ماند — پولِ
#     برگشته «فروش» شمرده می‌شد. و تمدیدِ ناموفق رها نمی‌شود؛ با
#     فاصله دوباره تلاش می‌کند، پس هر روز چند فروشِ خیالی.

from datetime import datetime as _dt      # noqa: E402

H.dispatch(tenant, bot, up_msg(777, "/start", "مریم"))
_w = D.get_user(777)
D.add_balance(_w["id"], 1_000_000, "topup", "شارژ تست")
_w = D.get_user(777)

SENT.clear()
H.wallet_pay(H.Ctx(bot, tenant), _w, 777, None, plan["id"])
_o = D.q("SELECT * FROM orders WHERE tenant_id=? AND user_id=? "
         "ORDER BY id DESC LIMIT 1", (tid, _w["id"]), one=True)

check("خرید با کیف پول approved می‌شود", _o["status"] == "approved",
      f"وضعیت: {_o['status']} — قبلاً pending می‌ماند")
check("و پول کم شده", D.get_user(777)["balance"] == 800_000,
      core.toman(D.get_user(777)["balance"]))

# همان کوئریِ جاروکش در bot/run.py، عیناً
D.exec("UPDATE orders SET expires_at=datetime('now','-1 hour') "
       "WHERE tenant_id=? AND id=?", (tid, _o["id"]))
_swept = D.q("""SELECT id FROM orders
                WHERE tenant_id=? AND status='pending'
                  AND expires_at IS NOT NULL AND expires_at < ?""",
             (tid, _dt.now().isoformat()))
check("جاروکش سفارشِ تحویل‌شده را منقضی نمی‌کند",
      not any(r["id"] == _o["id"] for r in _swept),
      "فروشِ انجام‌شده نباید «منقضی» شود")

# ─── تمدید خودکارِ ناموفق ───
_sub = D.q("SELECT * FROM subscriptions WHERE tenant_id=? AND user_id=? "
           "ORDER BY id DESC LIMIT 1", (tid, _w["id"]), one=True)
check("اشتراک ساخته شد", bool(_sub))

_bal_before = D.get_user(777)["balance"]
_orig_extend = FakeXUI.extend_subscription


def _panel_down(self, *a, **k):
    raise RuntimeError("پنل در دسترس نیست")


FakeXUI.extend_subscription = _panel_down
try:
    H.auto_renew_subscription(tenant, bot, _sub)
finally:
    FakeXUI.extend_subscription = _orig_extend

_o2 = D.q("SELECT * FROM orders WHERE tenant_id=? AND user_id=? "
          "ORDER BY id DESC LIMIT 1", (tid, _w["id"]), one=True)
check("تمدیدِ ناموفق فروش شمرده نمی‌شود", _o2["status"] != "approved",
      f"وضعیت: {_o2['status']} — قبلاً approved می‌ماند")
check("و پول برگشته", D.get_user(777)["balance"] == _bal_before,
      core.toman(D.get_user(777)["balance"]))

_ref = D.q("SELECT * FROM wallet_tx WHERE tenant_id=? AND order_id=? "
           "AND amount > 0", (tid, _o2["id"]), one=True)
check("برگشتِ وجه به سفارش گره خورده", bool(_ref),
      "بدون order_id در دفتر پیدا نمی‌شد")

# ─── ادعا: پول فقط یک بار برمی‌گردد ───
_bal_now = D.get_user(777)["balance"]
_again = D.close_order(_o2["id"], "expired")
check("بستنِ دوباره‌ی همان سفارش برنده نمی‌شود", _again == (False, 0),
      str(_again))
check("و پول دوبار برنمی‌گردد", D.get_user(777)["balance"] == _bal_now,
      "جاروکش و مسیر لغو هر دو می‌توانند همین سفارش را ببینند")

# ─── سفارشِ تاییدشده هرگز پس داده نمی‌شود ───
_o3 = D.create_order(_w["id"], plan["id"], plan["price"], plan["price"],
                     paid_from="wallet")
D.spend_balance(_w["id"], plan["price"], "spend", "خرید", _o3["id"])
_b3 = D.get_user(777)["balance"]
_won3, _back3 = D.close_order(_o3["id"], "approved")
check("سفارشِ approved پول پس نمی‌دهد", (_won3, _back3) == (True, 0),
      "وگرنه هر فروش یک اشتراکِ هدیه می‌شد")
check("و موجودی دست نخورده می‌ماند", D.get_user(777)["balance"] == _b3)

# ─── شاخه‌ی «موجودی وسطِ کار تمام شد» ───
# این شاخه هرگز اجرا نشده بود: ستونی که می‌نوشت وجود ندارد، پس
# به‌جای مدیریتِ مسابقه، خطای SQL می‌داد.
import sqlite3 as _sq3      # noqa: E402

_con = _sq3.connect(tmp)
try:
    _cols = [r[1] for r in _con.execute("PRAGMA table_info(orders)")]
finally:
    _con.close()
check("ستون reject_reason واقعاً وجود ندارد", "reject_reason" not in _cols,
      "پس هر دستوری که به آن اشاره کند خطا می‌دهد")

# نکته‌ی دام‌دار: handlers با «import db as DB» ماژول را برمی‌دارد و
# این فایل با «from bot import db». اینها دو شیء ماژولِ جدا هستند که
# فقط یک فایلِ دیتابیس مشترک دارند — پس وصله‌زدن به db.TenantDB هیچ
# اثری روی چیزی که handlers صدا می‌زند ندارد. باید همانی را وصله زد
# که خودش در دست دارد.
_orig_spend = H.DB.TenantDB.spend_balance
H.DB.TenantDB.spend_balance = lambda self, *a, **k: (False, 0)
try:
    _raised = None
    try:
        H.wallet_pay(H.Ctx(bot, tenant), D.get_user(777), 777, None, plan["id"])
    except Exception as e:      # noqa: BLE001
        _raised = e
finally:
    H.DB.TenantDB.spend_balance = _orig_spend

check("شاخه‌ی کسریِ لحظه‌ی آخر دیگر خطا نمی‌دهد", _raised is None,
      f"{type(_raised).__name__}: {_raised}" if _raised else "")
_o4 = D.q("SELECT * FROM orders WHERE tenant_id=? AND user_id=? "
          "ORDER BY id DESC LIMIT 1", (tid, _w["id"]), one=True)
check("و سفارشِ بی‌پرداخت رد می‌شود", _o4["status"] == "rejected",
      f"وضعیت: {_o4['status']}")
check("دلیل در admin_note می‌نشیند — همان ستونی که پنل می‌خواند",
      "کافی نبود" in (_o4["admin_note"] or ""), _o4["admin_note"] or "—")


# ═══════════════════════════════════════════════════════════
section("تست رایگان هم تا ساخته نشود «فروش» نیست")

# همان قاعده‌ی مسیر کارت و کیف پول، در سومین جایی که جا افتاده بود:
# سفارشِ تست *قبل* از ساخت approved می‌شد. اگر ساخت شکست می‌خورد،
# حقِ تست پس داده می‌شد ولی سفارش approved می‌ماند — و قیف تبدیل،
# کاربری را که هیچ‌وقت چیزی نگرفت «خرید موفق» می‌شمرد.

_tplan = D.q("SELECT * FROM plans WHERE tenant_id=? AND is_trial=1",
             (tid,), one=True)
check("پلن تست هست", bool(_tplan))

# ── تستِ موفق ──
SENT.clear()
H.dispatch(tenant, bot, up_msg(888, "/start", "سارا"))
# این بخش هسته را می‌سنجد، نه سؤال‌ها — اطلاعاتِ پیش از تست از قبل داده شده
D.exec("UPDATE users SET operator='mci', device_os='android', real_name='سارا' "
       "WHERE tenant_id=? AND tg_id IN (888, 889)", (tid,))
H.dispatch(tenant, bot, up_cb(888, "trial"))
_tu = D.get_user(888)
_to = D.q("SELECT * FROM orders WHERE tenant_id=? AND user_id=? "
          "ORDER BY id DESC LIMIT 1", (tid, _tu["id"]), one=True)
check("حق تست مصرف شد", _tu["trial_used"] == 1)
check("سفارشِ تستِ موفق approved می‌شود", _to and _to["status"] == "approved",
      f"وضعیت: {_to['status'] if _to else '—'}")
check("و کانفیگ واقعا ساخته شد",
      bool(D.q("SELECT 1 FROM subscriptions WHERE tenant_id=? AND user_id=?",
               (tid, _tu["id"]), one=True)))

# ── تستی که ساختش شکست می‌خورد ──
_orig_create = FakeXUI.create_subscription


def _no_panel(self, *a, **k):
    raise RuntimeError("پنل در دسترس نیست")


H.dispatch(tenant, bot, up_msg(889, "/start", "نگار"))
D.exec("UPDATE users SET operator='mci', device_os='android', real_name='نگار' "
       "WHERE tenant_id=? AND tg_id=889", (tid,))
FakeXUI.create_subscription = _no_panel
try:
    H.dispatch(tenant, bot, up_cb(889, "trial"))
finally:
    FakeXUI.create_subscription = _orig_create

_fu = D.get_user(889)
_fo = D.q("SELECT * FROM orders WHERE tenant_id=? AND user_id=? "
          "ORDER BY id DESC LIMIT 1", (tid, _fu["id"]), one=True)
check("حق تست پس داده می‌شود", _fu["trial_used"] == 0,
      "پیام به کاربر می‌گوید «تست رایگانتان هنوز محفوظ است»")
check("و سفارشِ ناموفق approved نمی‌ماند",
      _fo and _fo["status"] != "approved",
      f"وضعیت: {_fo['status'] if _fo else '—'}")
check("بلکه رد می‌شود", _fo and _fo["status"] == "rejected",
      f"وضعیت: {_fo['status'] if _fo else '—'}")

# و چون حق تست برگشته، دوباره می‌تواند امتحان کند
H.dispatch(tenant, bot, up_cb(889, "trial"))
check("و کاربر می‌تواند دوباره امتحان کند",
      D.get_user(889)["trial_used"] == 1,
      "وگرنه کسی که تقصیری نداشت، تستش را از دست می‌داد")


# ═══════════════════════════════════════════════════════════
section("پاداش معرف به روشِ پرداخت ربطی ندارد")

# ربات به کاربر می‌گوید: «هر دوستی که با لینک شما بیاید و *خرید کند*،
# N سکه به شما می‌رسد». هیچ حرفی از روشِ پرداخت نیست.
#
# ولی پاداش فقط از مسیر تاییدِ کارت پرداخت می‌شد. دوستی که با کیف پول
# می‌خرید — یا تمدید خودکارش اجرا می‌شد — هیچ سکه‌ای به معرفش
# نمی‌رساند. پورسانتِ همکار فروش هر سه مسیر را داشت؛ پاداشِ معرف فقط
# یکی را.

_inv_tg, _fr_tg = 990, 991
H.dispatch(tenant, bot, up_msg(_inv_tg, "/start", "معرف"))
_inv = D.get_user(_inv_tg)
H.dispatch(tenant, bot, up_msg(_fr_tg, f"/start {_inv['ref_code']}", "دوست"))
_fr = D.get_user(_fr_tg)
check("رابطه‌ی معرفی برقرار شد", _fr["referred_by"] == _inv["id"])

_coins_before = D.get_user(_inv_tg)["coins"]
check("هنوز پاداشی نگرفته", _coins_before == 0, str(_coins_before))

D.add_balance(_fr["id"], 1_000_000, "topup", "شارژ تست")
SENT.clear()
H.wallet_pay(H.Ctx(bot, tenant), D.get_user(_fr_tg), _fr_tg, None, plan["id"])

_ord = D.q("SELECT * FROM orders WHERE tenant_id=? AND user_id=? "
           "ORDER BY id DESC LIMIT 1", (tid, _fr["id"]), one=True)
check("خرید با کیف پول انجام شد", _ord and _ord["status"] == "approved",
      f"وضعیت: {_ord['status'] if _ord else '—'}")

_per = int(core.coin_settings(
    H.Ctx(bot, tenant).s.get("coins")).get("per_referral") or 0)
check("نرخ پاداش تعریف شده", _per > 0, f"{_per} سکه")

_coins_after = D.get_user(_inv_tg)["coins"]
_want = _per if PRO_PAY else 0          # Community: no referral reward at all
check("معرف پاداشش را از خریدِ کیف‌پولی هم می‌گیرد" if PRO_PAY
      else "Community: no referral reward, and the wallet sale still closed",
      _coins_after == _coins_before + _want,
      f"{_coins_before} → {_coins_after} (باید {_coins_before + _want})")

# و دو بار نه — قاعده «یک پاداش برای هر دوست» است
D.add_balance(_fr["id"], 1_000_000, "topup", "شارژ دوم")
H.wallet_pay(H.Ctx(bot, tenant), D.get_user(_fr_tg), _fr_tg, None, plan["id"])
check("و خرید دوم پاداش دوباره نمی‌دهد",
      D.get_user(_inv_tg)["coins"] == _coins_before + _want,
      f"{D.get_user(_inv_tg)['coins']} سکه")

# هر سه مسیرِ خرید باید هر دو پرداخت را انجام دهند
_hsrc0 = io.open(H.__file__, encoding="utf-8").read()


def _calls_in(func_name):
    import ast as _a
    _t = _a.parse(_hsrc0)
    for _n in _a.walk(_t):
        if isinstance(_n, _a.FunctionDef) and _n.name == func_name:
            out = set()
            for _c in _a.walk(_n):
                if isinstance(_c, _a.Call):
                    _f = _c.func
                    out.add(getattr(_f, "id", None) or getattr(_f, "attr", None))
            return out
    return set()


# `wallet_pay` دیگر خودش پول جابه‌جا نمی‌کند — پوسته‌ی تلگرامیِ
# `wallet_purchase` است و مینی‌اپ هم همان هسته را صدا می‌زند. پس
# اسکن باید روی جایی باشد که پول واقعاً حرکت می‌کند، نه روی پوسته.
#
# Since 2.0 the payouts are Pro, behind one hook: each core calls
# `after_paid_order` and names neither payout, so a core can no longer pay one
# and forget the other. The hook runs both (PAYOUTS), and
# tests/pro/test_payouts.py checks it really pays both on each path.
_PAYOUT_NAMES = {"_pay_commission", "_reward_referrer", "pay_commission",
                 "reward_referrer", "record_commission", "reward_referral"}
for _path in ("wallet_purchase", "approve_order", "auto_renew_subscription"):
    _c = _calls_in(_path)
    check(f"{_path} پرداخت‌های فروش را از قلاب می‌دهد", "after_paid_order" in _c,
          "یکی از این دو بدون دیگری یعنی یک وعده‌ی نگه‌داشته‌نشده")
    check(f"{_path} هیچ پرداختی را خودش به نام صدا نمی‌زند",
          not (_c & _PAYOUT_NAMES), ", ".join(sorted(_c & _PAYOUT_NAMES)))
check("قلاب هر دو پرداخت را دارد",
      [a for a, _f, _k in H.PAYOUTS] == ["affiliates", "loyalty"], str(H.PAYOUTS))

# و پوسته باید واقعاً از هسته رد شود، نه اینکه نسخه‌ی خودش را داشته
# باشد. بدون این، کسی می‌تواند منطق را دوباره داخل wallet_pay
# بنویسد و اسکنِ بالا همچنان سبز بماند — چون به wallet_purchase
# نگاه می‌کند.
_shell = _calls_in("wallet_pay")
check("wallet_pay خودش پول جابه‌جا نمی‌کند",
      "wallet_purchase" in _shell
      and "spend_balance" not in _shell
      and "create_order" not in _shell,
      "پوسته فقط پیام می‌سازد؛ پول در هسته حرکت می‌کند")

# اشتراکِ فروشگاه: هر هسته‌ای که پول می‌گیرد یا کانفیگ می‌دهد، دروازه را
# صدا می‌زند (docs/specs/2026-09-26-reseller-store-subscription.md). رفتار
# را test_reseller می‌سنجد؛ این فقط نمی‌گذارد هسته‌ی ششمی بی‌دروازه بیاید
# یا یکی از این پنج در بازنویسی دروازه‌اش را جا بیندازد.
for _path in ("card_order", "wallet_purchase", "topup_order", "give_trial",
              "auto_renew_subscription"):
    check(f"{_path} پیش از فروش اشتراکِ فروشگاه را می‌سنجد",
          "store_gate" in _calls_in(_path))
check("receipt_submit دروازه را صدا نمی‌زند",
      "store_gate" not in _calls_in("receipt_submit"),
      "رسیدِ سفارشی که وقتِ باز بودن ساخته شد، پولی است که در راه است")


# ═══════════════════════════════════════════════════════════
section("هر رویدادِ پولی باید در گروه مدیریت دیده شود")

# شارژ کیف پول، تمدید خودکار و خریدِ کارتی (که با رسیدش می‌آید) هر
# کدام خودشان را به گروه اعلام می‌کنند. خریدِ کیف‌پولی تنها موردی بود
# که هیچ ردی نداشت — و چون تاییدِ ادمین هم نمی‌خواهد، کل آن روشِ
# پرداخت در لحظه نامرئی بود.

_ntg, _nadmin = 992, tenant.get("admin_group_id")
check("گروه مدیریت تنظیم است", bool(_nadmin), str(_nadmin))

H.dispatch(tenant, bot, up_msg(_ntg, "/start", "خریدار"))
_nu = D.get_user(_ntg)
D.add_balance(_nu["id"], 1_000_000, "topup", "شارژ تست")

SENT.clear()
H.wallet_pay(H.Ctx(bot, tenant), D.get_user(_ntg), _ntg, None, plan["id"])

_to_group = [m for m in SENT if m.get("to") == _nadmin]
check("گروه مدیریت خبردار می‌شود", len(_to_group) >= 1,
      f"{len(_to_group)} پیام به گروه")
_txt = " ".join(m.get("text") or "" for m in _to_group)
check("و پیام می‌گوید خرید با کیف پول بوده", "کیف پول" in _txt,
      _txt[:60] or "—")
check("نام پلن در پیام هست", plan["name"] in _txt)
check("مبلغ هم در پیام هست",
      core.toman(plan["price"]) in _txt.replace("،", "،"),
      core.toman(plan["price"]))
check("و مشتری هم شناسایی می‌شود", str(_ntg) in _txt)

# تمدید با کیف پول باید از خرید تازه قابل تشخیص باشد
_nsub = D.q("SELECT * FROM subscriptions WHERE tenant_id=? AND user_id=? "
            "ORDER BY id DESC LIMIT 1", (tid, _nu["id"]), one=True)
SENT.clear()
H.wallet_pay(H.Ctx(bot, tenant), D.get_user(_ntg), _ntg, None, plan["id"],
             renew_sub_id=_nsub["id"])
_txt2 = " ".join(m.get("text") or "" for m in SENT
                 if m.get("to") == _nadmin)
check("تمدیدِ کیف‌پولی هم اعلام می‌شود", bool(_txt2.strip()))
check("و «تمدید» بودنش مشخص است", "تمدید" in _txt2, _txt2[:60] or "—")


# ── هسته‌ی خرید، همان که مینی‌اپ هم صدایش می‌زند ──
#
# مسیر چهارمِ پول در این مخزن است. سه مسیر قبلی هر کدام یک‌بار یک
# قاعده را فراموش کردند، پس این یکی باید رفتارش سنجیده شود نه فقط
# ساختارش.
section("خرید از مینی‌اپ — همان هسته، بدون پوسته")

_mtg = 7788
D.create_user(_mtg, None, "خریدارِ مینی‌اپ")
_mu = D.get_user(_mtg)
D.add_balance(_mu["id"], 500_000, "topup", "شارژ مینی‌اپ")

_before = D.get_user(_mtg)["balance"]
_r = H.wallet_purchase(H.Ctx(bot, tenant), D.get_user(_mtg), plan["id"])
check("خرید از هسته موفق است", _r.get("ok"), str(_r.get("why") or "—"))

_mo = D.q("SELECT * FROM orders WHERE tenant_id=? AND user_id=? "
          "ORDER BY id DESC LIMIT 1", (tid, _mu["id"]), one=True)
check("سفارش approved شد", _mo and _mo["status"] == "approved",
      f"وضعیت: {_mo['status'] if _mo else '—'}")
check("و کانفیگش هم ساخته شده", bool(_mo and _mo["sub_id"]),
      "approved بدون sub_id یعنی همان باگی که سه بار پیدا شد")
check("پول از کیف پول کم شد",
      D.get_user(_mtg)["balance"] == _before - plan["price"],
      f"{_before} → {D.get_user(_mtg)['balance']}")
check("و از راه کیف پول ثبت شده", _mo and _mo["paid_from"] == "wallet",
      str(_mo["paid_from"] if _mo else "—"))

# موجودی کم: هیچ سفارشی نباید بماند و هیچ پولی نباید کم شود
_ptg = 7789
D.create_user(_ptg, None, "بی‌پول")
_pu = D.get_user(_ptg)
_pbal = D.get_user(_ptg)["balance"]
_open_before = D.q("SELECT COUNT(*) n FROM orders WHERE tenant_id=? AND user_id=?",
                   (tid, _pu["id"]), one=True)["n"]
_r2 = H.wallet_purchase(H.Ctx(bot, tenant), D.get_user(_ptg), plan["id"])
check("خرید بی‌پول رد می‌شود", not _r2.get("ok") and _r2.get("why") == "low_balance",
      str(_r2.get("why") or "ok"))
check("و کسری را می‌گوید", int(_r2.get("short") or 0) > 0,
      f"{_r2.get('short')} تومان")
_open_after = D.q("SELECT COUNT(*) n FROM orders WHERE tenant_id=? AND user_id=?",
                  (tid, _pu["id"]), one=True)["n"]
check("و هیچ سفارشی جا نمی‌گذارد", _open_after == _open_before,
      f"{_open_before} → {_open_after}")
check("و هیچ پولی کم نمی‌کند", D.get_user(_ptg)["balance"] == _pbal)

# ── و مهم‌ترین حالت: ساخت کانفیگ شکست بخورد ──
#
# این همان باگی است که در این مخزن سه بار پیدا شد — `approved`
# نوشته می‌شد و بعد ساخت شکست می‌خورد، پس پولِ برگشته «فروش» شمرده
# می‌شد. تستِ مسیر موفق این را نمی‌گیرد: آن‌جا سفارش در هر دو حالت
# approved تمام می‌شود و تفاوتی دیده نمی‌شود.
_mbal = D.get_user(_mtg)["balance"]
_keep = H.XUI.create_subscription


def _fail_provision(self, *a, **k):
    raise H.XUIError("پنل: inbound not found")


H.XUI.create_subscription = _fail_provision
try:
    _r4 = H.wallet_purchase(H.Ctx(bot, tenant), D.get_user(_mtg), plan["id"])
finally:
    H.XUI.create_subscription = _keep

check("ساختِ ناموفق، خرید را رد می‌کند",
      not _r4.get("ok") and _r4.get("why") == "provision", str(_r4.get("why")))

_fo = D.q("SELECT * FROM orders WHERE tenant_id=? AND user_id=? "
          "ORDER BY id DESC LIMIT 1", (tid, _mu["id"]), one=True)
check("و سفارش approved نمی‌ماند", _fo and _fo["status"] != "approved",
      f"وضعیت: {_fo['status'] if _fo else '—'} — approved بدون کانفیگ یعنی "
      "پولِ برگشته در آمار فروش می‌نشیند")
check("و پول کامل برمی‌گردد", D.get_user(_mtg)["balance"] == _mbal,
      f"{_mbal} → {D.get_user(_mtg)['balance']}")


# پلنِ نبوده
_r3 = H.wallet_purchase(H.Ctx(bot, tenant), D.get_user(_mtg), 999999)
check("پلنِ ناموجود رد می‌شود",
      not _r3.get("ok") and _r3.get("why") == "no_plan", str(_r3.get("why")))


# ── رسید هم یک هسته دارد ──
#
# مینی‌اپ هم رسید می‌گیرد. اگر آن‌جا دوباره نوشته شود، دو مسیرِ رسید
# می‌شود و روزی یکی‌شان اعلانِ گروه را جا می‌اندازد — آن‌وقت مشتری
# پول داده و هیچ‌کس خبر ندارد.
section("رسید — یک هسته، دو در")

_rshell = _calls_in("handle_receipt")
check("handle_receipt خودش رسید را ثبت نمی‌کند",
      "receipt_submit" in _rshell and "attach_receipt" not in _rshell,
      "پوسته فقط پیام می‌سازد")

_rcore = _calls_in("receipt_submit")
check("هسته ادعای اتمی می‌زند", "attach_receipt" in _rcore,
      "بدون ادعا، جاروکشِ مهلت و این مسیر هر دو یک سفارش را برمی‌دارند")
check("و گروه مدیریت را خبر می‌کند",
      "notify_group" in _rcore or "send_photo" in _rcore,
      "رسیدی که کسی نبیند، پولی است که گم می‌شود")

# رفتار: رسید روی سفارشِ باز می‌نشیند و وضعیت را awaiting می‌کند
_rtg = 7790
D.create_user(_rtg, None, "کارت‌به‌کارتی")
_ru = D.get_user(_rtg)
_ro = D.create_order(_ru["id"], plan["id"], plan["price"], plan["price"],
                     paid_from="card")
_ok, _why = H.receipt_submit(H.Ctx(bot, tenant), D.get_user(_rtg),
                             _ro["id"], "text", rtext="واریز شد")
check("رسید ثبت می‌شود", _ok, str(_why))
check("و سفارش awaiting می‌شود",
      D.get_order(_ro["id"])["status"] == "awaiting",
      D.get_order(_ro["id"])["status"])

# دو بار نه — سفارشی که awaiting است دیگر pending نیست
_ok2, _why2 = H.receipt_submit(H.Ctx(bot, tenant), D.get_user(_rtg),
                               _ro["id"], "text", rtext="دوباره")
check("رسید دوم روی همان سفارش نمی‌نشیند",
      not _ok2 and _why2 == "closed", str(_why2))

# مهلتِ گذشته
_ro2 = D.create_order(_ru["id"], plan["id"], plan["price"], plan["price"],
                      paid_from="card")
D.exec("UPDATE orders SET expires_at=? WHERE tenant_id=? AND id=?",
       ("2020-01-01T00:00:00", tid, _ro2["id"]))
_ok3, _why3 = H.receipt_submit(H.Ctx(bot, tenant), D.get_user(_rtg),
                               _ro2["id"], "text", rtext="دیر")
check("رسیدِ بعد از مهلت رد می‌شود",
      not _ok3 and _why3 == "expired", str(_why3))
check("و سفارش منقضی می‌شود",
      D.get_order(_ro2["id"])["status"] == "expired",
      D.get_order(_ro2["id"])["status"])


# و هیچ مسیر تازه‌ای نباید دوباره خام approved بنویسد.
#
# این الگو سه بار پیدا شد: کیف پول، تمدید خودکار، و تست رایگان. هر
# سه یک شکل داشتند — approved پیش از ساخت کانفیگ. حالا همه از
# close_order می‌گذرند و این اسکن جلوی چهارمی را می‌گیرد.
#
# کامنت‌ها اول برداشته می‌شوند: سه بار تستی سبز مانده چون رشته‌ای که
# دنبالش بودم در توضیحِ خودم پیدا می‌شد، نه در کد.
_hsrc = io.open(H.__file__, encoding="utf-8").read()
_hcode = "\n".join(l for l in _hsrc.split("\n")
                   if not l.strip().startswith("#"))
check("هیچ‌جای handlers خام approved نمی‌نویسد",
      "SET status='approved'" not in _hcode,
      "برای تاییدِ سفارش از ctx.db.close_order استفاده کنید")


# ═══════════════════════════════════════════════════════════
#  کد تخفیف
#
#  برگه‌اش: docs/specs/2026-09-19-discount-and-trial-winback.md
#
#  جدول `discounts` و `core.validate_discount` از قبل بودند و
#  **صفر بار** صدا زده می‌شدند. حالا که وصل شده‌اند، این‌ها را
#  نگه می‌داریم.
# ═══════════════════════════════════════════════════════════
section("کد تخفیف")

import re as _redc                                            # noqa: E402

_dctx = H.Ctx(bot, tenant)
_other = db.create_tenant("دیگری", bot_token="9:TEST", owner_tg_id=888)

D.exec("INSERT INTO discounts (tenant_id,code,percent,max_uses,is_active) "
       "VALUES (?,'HALF',50,2,1)", (tid,))
D.exec("INSERT INTO discounts (tenant_id,code,percent,max_uses,is_active) "
       "VALUES (?,'DEAD',30,0,0)", (tid,))
db.TenantDB(_other).exec(
    "INSERT INTO discounts (tenant_id,code,percent,max_uses,is_active) "
    "VALUES (?,'FOREIGN',90,0,1)", (_other,))

_e, _p, _r = H.find_discount(_dctx, "half")
check("کد بدونِ توجه به بزرگ و کوچک پیدا می‌شود", _p == 50, f"{_p}٪")
_e, _p, _r = H.find_discount(_dctx, " HALF ")
check("و فاصله‌ی اضافه اذیت نمی‌کند", _p == 50, f"{_p}٪")
_e, _p, _r = H.find_discount(_dctx, "FOREIGN")
check("کدِ مستاجرِ دیگر پیدا نمی‌شود", _p == 0 and bool(_e),
      "وگرنه تخفیفِ مشتری از جیبِ نماینده‌ی دیگر می‌رود")
_e, _p, _r = H.find_discount(_dctx, "DEAD")
check("کدِ خاموش رد می‌شود", _p == 0 and bool(_e), str(_e))
_e, _p, _r = H.find_discount(_dctx, "")
check("کدِ خالی خطا می‌دهد، نه صد درصد تخفیف", _p == 0 and bool(_e), str(_e))

# ترتیب عمدی است: اول کد، بعد سکه. جابه‌جا شدنش یعنی عددِ امروز با
# عددِ دیروز قابل مقایسه نیست، بی‌آنکه چیزی خطا بدهد.
_pr = core.price_order(200_000, coins=40, use_coins=True,
                       coin_cfg={"tiers": [{"coins": 20, "percent": 10}]},
                       discount_percent=25)
check("کد اول اعمال می‌شود، بعد سکه",
      _pr["code_discount"] == 50_000 and _pr["coin_discount"] == 15_000,
      f"کد {_pr['code_discount']} · سکه {_pr['coin_discount']}")


def _mk_disc_order():
    return D.create_order(D.get_user(555)["id"], plan["id"],
                          200_000, 100_000,
                          discount_pct=50, discount_code="HALF")["id"]


def _disc_used():
    r = D.q("SELECT used_count FROM discounts WHERE tenant_id=? AND code='HALF'",
            (tid,), one=True)
    return int(r["used_count"]) if r else -1


# ظرفیت سرِ *تایید* مصرف می‌شود، نه سرِ ساخت — وگرنه سه نفر که
# صفحه‌ی پرداخت را باز کردند و رفتند، کد را تمام می‌کنند.
_o1, _o2, _o3 = _mk_disc_order(), _mk_disc_order(), _mk_disc_order()
check("ساختِ سفارش ظرفیت نمی‌سوزاند", _disc_used() == 0, str(_disc_used()))
D.close_order(_o1, "approved")
D.close_order(_o2, "approved")
check("هر تایید یک ظرفیت برمی‌دارد", _disc_used() == 2, str(_disc_used()))
D.close_order(_o3, "approved")
check("و از سقف رد نمی‌شود", _disc_used() == 2, str(_disc_used()))
check("ولی قیمتِ سفارشِ روی مرز عوض نمی‌شود",
      int(D.get_order(_o3)["amount"]) == 100_000,
      "سقف ابزارِ بازاریابی است، نه بهانه‌ی گرفتنِ مبلغی جز آنچه گفته‌ایم")

D.exec("UPDATE discounts SET used_count=0, max_uses=1 "
       "WHERE tenant_id=? AND code='HALF'", (tid,))
_o4 = _mk_disc_order()
D.close_order(_o4, "rejected", "تست")
check("سفارشِ ردشده ظرفیت نمی‌سوزاند", _disc_used() == 0, str(_disc_used()))

_HSRC = io.open("bot/handlers.py", encoding="utf-8").read()
_DBSRC = io.open("bot/db.py", encoding="utf-8").read()

check("ظرفیت فقط در close_order برداشته می‌شود",
      _DBSRC.count("SET used_count = used_count + 1") == 1,
      "هر جای دیگری یعنی یک مسیر فراموشش می‌کند — سه بار افتاده")

# ── پایه‌ی پورسانت ──
#
# تا وقتی تخفیفی نبود، «قیمتِ پلن» و «مبلغِ پرداختی» یک عدد بودند و
# سه صداکننده‌ی _pay_commission هر کدام یکی را می‌دادند بی‌آنکه فرقی
# دیده شود. با کد تخفیف این دو از هم جدا می‌شوند و پورسانت روی پولی
# داده می‌شود که هرگز نرسیده.
# Commission lives in bot/pro/affiliates.py since 2.0 (Community: none).
_AFF_PY = os.path.join(_ROOT_DIR, "bot", "pro", "affiliates.py")
if os.path.exists(_AFF_PY):
    _AFSRC = io.open(_AFF_PY, encoding="utf-8").read()
    _pc = _AFSRC.split("def pay_commission(")[1].split("\ndef ")[0]
    check("پورسانت مبلغ را از خودِ سفارش می‌خواند",
          "ctx.db.get_order(order_id)" in _pc,
          "پایه یک جا تعیین شود، نه سه جا")
    _calls = _redc.findall(r"(?<!def )pay_commission\(([^)]*)\)", _AFSRC + _HSRC)
    check("و هیچ صداکننده‌ای مبلغ پاس نمی‌دهد",
          _calls and all(len(a.split(",")) == 3 for a in _calls),
          " | ".join(a for a in _calls if len(a.split(",")) != 3) or f"{len(_calls)} صداکننده")

check("هر دو هسته‌ی خرید از core.price_order می‌گذرند",
      _HSRC.count("core.price_order(") >= 2, "قیمت یک هسته دارد")

# ═══════════════════════════════════════════════════════════
#  کد تخفیف از داخلِ خودِ ربات
#
#  برگه‌اش: docs/specs/2026-09-19-discount-in-bot.md
#
#  در ۱.۶۹.۰ کد فقط از مینی‌اپ قابل واردکردن بود — و در همان
#  نسخه پیگیریِ تست ساخته شد که کد را **در تلگرام** می‌فرستد.
#  یعنی ربات کدی می‌فرستاد که خودش قبولش نمی‌کرد.
#
#  این‌ها از راه `dispatch` سنجیده می‌شوند، نه با خواندنِ متنِ
#  کد: دکمه‌ای که در روتر وصل نشده باشد، این‌جا خودش را نشان
#  می‌دهد.
# ═══════════════════════════════════════════════════════════
section("کد تخفیف در ربات")

_bd = D.get_user(555)
D.exec("UPDATE users SET balance=500000, held_discount=NULL "
       "WHERE tenant_id=? AND tg_id=555", (tid,))
D.exec("UPDATE discounts SET used_count=0, max_uses=9 "
       "WHERE tenant_id=? AND code='HALF'", (tid,))

SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"plan:{plan['id']}"))
check("صفحه‌ی پلن دکمه‌ی کد تخفیف دارد", "کد تخفیف دارم" in str(SENT[-1]),
      "کدی که راهِ واردکردن ندارد، قابلیت نیست")

SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"dsc:{plan['id']}"))
check("دکمه کار می‌کند و کد را می‌پرسد", "کدتان را همین‌جا بفرستید" in last(),
      "دکمه‌ی بی‌جواب از نبودِ دکمه بدتر است")
check("و حالت عوض می‌شود",
      D.get_user(555)["state"] == "await_discount",
      str(D.get_user(555)["state"]))

SENT.clear()
H.dispatch(tenant, bot, up_msg(555, "NOPE"))
check("کدِ اشتباه دلیلش را می‌گوید", "پیدا نشد" in last(), last()[:40])
check("و کدِ بی‌اعتبار نگه داشته نمی‌شود", not D.held_discount(555))

SENT.clear()
H.dispatch(tenant, bot, up_msg(555, " half "))
check("کد با فاصله و حروفِ کوچک پذیرفته می‌شود",
      D.held_discount(555) == "HALF", repr(D.held_discount(555)))
def _btn_labels(entry):
    """برچسبِ همه‌ی دکمه‌های یک پیام — فقط دکمه‌ها، نه متن."""
    raw = (entry or {}).get("kb")
    if isinstance(raw, str):
        raw = json.loads(raw)
    return [b.get("text", "")
            for row in ((raw or {}).get("inline_keyboard") or [])
            for b in row]


_buy = [b for b in _btn_labels(SENT[-1]) if "خرید" in b]
check("و قیمتِ تازه روی خودِ دکمه می‌نشیند",
      bool(_buy) and all(core.toman(200_000) not in b for b in _buy)
      and any(core.toman(100_000) in b for b in _buy),
      " · ".join(_buy) or "دکمه‌ی خریدی نبود")

# ── کارت ──
SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"chk:{plan['id']}:0"))
_o = D.q("SELECT id, amount, base_amount, discount_pct, discount_code "
         "FROM orders WHERE tenant_id=? AND user_id=? ORDER BY id DESC LIMIT 1",
         (tid, _bd["id"]), one=True)
check("خریدِ کارتی کد را با خود می‌برد",
      int(_o["amount"]) == 100_000 and int(_o["discount_pct"]) == 50,
      f"{_o['amount']} تومان · {_o['discount_pct']}٪")
check("و پایه‌ی سفارش قیمتِ پلن می‌ماند",
      int(_o["base_amount"]) == 200_000,
      "تفاوتِ این دو همان تخفیفی است که گزارش‌ها از رویش حساب می‌کنند")
check("کد بعد از ساختِ سفارش برداشته می‌شود", not D.held_discount(555),
      "ماندنش یعنی خریدِ بعدی هم بی‌آنکه بخواهد تخفیف می‌گیرد")

# ── کیف پول ──
D.close_order(_o["id"], "rejected", "تست")
D.set_held_discount(555, "HALF")
SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"wpay:{plan['id']}"))
_w = D.q("SELECT amount, discount_pct, paid_from FROM orders "
         "WHERE tenant_id=? AND user_id=? ORDER BY id DESC LIMIT 1",
         (tid, _bd["id"]), one=True)
check("خریدِ کیف پولی هم کد را با خود می‌برد",
      int(_w["amount"]) == 100_000 and _w["paid_from"] == "wallet",
      f"{_w['amount']} تومان · {_w['paid_from']}")
check("و آن‌جا هم کد می‌ماند نمی‌ماند", not D.held_discount(555))
# The amount the buyer and the group are told is the one charged. Both once
# printed the plan's list price although the wallet had paid half.
_paid_msg = [m["text"] for m in SENT if "کم شد" in (m["text"] or "")]
check("پیامِ خریدار مبلغِ کسرشده را می‌گوید، نه قیمتِ پلن",
      _paid_msg and core.toman(100_000) in _paid_msg[-1]
      and core.toman(plan["price"]) not in _paid_msg[-1], _paid_msg[-1:])
_grp_msg = [m["text"] for m in SENT
            if m["to"] == -100123 and "خرید با کیف پول" in (m["text"] or "")]
check("اعلانِ گروه هم مبلغِ پرداختی را می‌گوید و تخفیف را نام می‌برد",
      _grp_msg and f"مبلغ: {core.toman(100_000)} تومان" in _grp_msg[-1]
      and "کد تخفیف" in _grp_msg[-1], _grp_msg[-1:])

# ── کدی که بین دیدنِ صفحه و زدنِ دکمه از کار افتاد ──
D.exec("INSERT INTO discounts (tenant_id,code,percent,max_uses,used_count,"
       "is_active) VALUES (?,'SPENT',40,1,1,1)", (tid,))
D.set_held_discount(555, "SPENT")
SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"plan:{plan['id']}"))
check("کدِ پرشده بی‌صدا دور انداخته نمی‌شود",
      "ظرفیت این کد تمام شده" in str(SENT[-1]),
      "قیمتی که بی‌توضیح به حالتِ اول برگردد یعنی مشتری فکر می‌کند اشتباه زده")
check("و از دستِ کاربر برداشته می‌شود", not D.held_discount(555))

# ── دکمه‌ی برداشتن ──
D.set_held_discount(555, "HALF")
SENT.clear()
H.dispatch(tenant, bot, up_cb(555, f"dscx:{plan['id']}"))
check("دکمه‌ی برداشتنِ کد کار می‌کند", not D.held_discount(555))
check("و قیمت به حالتِ اول برمی‌گردد", core.toman(200_000) in str(SENT[-1]))

# ── پوسته هنوز پوسته است ──
_sh = _HSRC.split("def checkout(")[1].split("\ndef ")[0]
check("پوسته‌ی کارت خودش قیمت حساب نمی‌کند",
      "core.price_order(" not in _sh and "create_order(" not in _sh,
      "قیمت همان‌جایی حساب شود که برای مینی‌اپ حساب می‌شود")
_wh = _HSRC.split("def wallet_pay(")[1].split("\ndef ")[0]
check("پوسته‌ی کیف پول هم", "core.price_order(" not in _wh
      and "spend_balance(" not in _wh)

check("کدِ مستاجرِ دیگر از این مسیر هم پیدا نمی‌شود",
      H.find_discount(_dctx, "FOREIGN")[1] == 0,
      "همان اعتبارسنج، پس همان قاعده")

# The follow-up and win-back messages are Pro since 2.0 (bot/pro/loyalty.py).
_LOY_PY = os.path.join(_ROOT_DIR, "bot", "pro", "loyalty.py")
_LOYSRC = io.open(_LOY_PY, encoding="utf-8").read() if os.path.exists(_LOY_PY) else None
if _LOYSRC is not None:
    check("پیامِ پیگیری می‌گوید کد را کجا باید زد",
          "کد تخفیف دارم" in _LOYSRC,
          "کدی که فرستاده می‌شود باید راهِ استفاده‌اش هم گفته شود")
    check("و دکمه‌اش حتی بدونِ مینی‌اپ هم هست",
          'kb([[("🛒 دیدن پلن‌ها", "buy")]])' in _LOYSRC,
          "مستاجرِ بی‌مینی‌اپ وگرنه کدی می‌فرستد که مشتری راهی به پلن‌ها ندارد")


# ═══════════════════════════════════════════════════════════
#  پیگیریِ کسی که تست گرفته و نخریده
# ═══════════════════════════════════════════════════════════
section("پیگیری تست")

_RSRC = io.open("bot/run.py", encoding="utf-8").read()
if _LOYSRC is not None:
    _wb = _LOYSRC.split("def trial_winback(")[1].split("\ndef ")[0]

    # «نخریده» یعنی هیچ سفارشِ approvedِ غیرِتست. مبلغ کافی نیست: تستِ
    # صفر تومانی و سفارشِ صددرصد تخفیف‌خورده هر دو صفرند ولی یکی تبدیل
    # است و دیگری نه — و تستِ رایگان خودش یک سفارشِ approved می‌سازد.
    check("پیگیری فقط به کسی می‌رود که خریدِ پولی نکرده",
          "COALESCE(p.is_trial, 0) = 0" in _wb,
          "وگرنه به مشتریِ فعلی هم تخفیف می‌دهیم")
    check("و فقط یک‌بار",
          "u.trial_followup_at IS NULL" in _wb
          and "SET trial_followup_at=CURRENT_TIMESTAMP" in _wb,
          "بدونِ پرچم، هر ساعت یک پیامِ تبلیغاتی می‌رود")
    check("پرچم چه پیام برود چه نرود زده می‌شود",
          _wb.index("SET trial_followup_at") > _wb.index("log.debug(\"ارسال پیگیری"),
          "کسی که بلاک کرده وگرنه هر ساعت یک کدِ تازه می‌گیرد")
    check("کدش یک‌بارمصرف و زمان‌دار است",
          "max_uses, expires_at, is_active) VALUES (?,?,?,1,?,1)" in _wb,
          "کدِ مشترک را یک نفر در گروه می‌گذارد و همه استفاده می‌کنند")
    check("خاموش بودن یعنی هیچ",
          'wb.get("enabled")' in _wb and "continue" in _wb)
else:
    print("  (Community: the win-back and follow-up messages are Pro — not checked here)")

check("زمان‌بند صدایش می‌زند",
      "trial_winback()" in _RSRC.split("def scheduler_loop(")[1],
      "تابعی که هیچ‌کس صدا نمی‌زند، قابلیت نیست")


# ═══════════════════════════════════════════════════════════
#  گزارشِ کدهای تخفیف
#
#  تا امروز تنها بازخوردِ مالک `used_count` بود: «چند بار». این
#  می‌گوید **چقدر** — و پیگیریِ تست جواب داد یا نه.
#
#  هیچ عددی تازه ساخته نمی‌شود: تفاوتِ base_amount و amount روی
#  خودِ سفارش، همان تخفیفی است که داده شده.
# ═══════════════════════════════════════════════════════════
section("گزارشِ کدهای تخفیف")

_ru = D.get_user(555)["id"]
_rplan = [p for p in D.plans() if not p.get("is_trial")][0]["id"]
_rtrial = D.exec(
    "INSERT INTO plans (tenant_id,name,price,gb,days,is_active,is_trial) "
    "VALUES (?,'تستِ گزارش',0,1,1,1,1)", (tid,))
D.exec("DELETE FROM orders WHERE tenant_id=?", (tid,))
D.exec("DELETE FROM discounts WHERE tenant_id=? AND code LIKE 'BACK%'", (tid,))


def _rorder(plan, base, amt, code, status="approved"):
    return D.exec(
        "INSERT INTO orders (tenant_id,user_id,plan_id,amount,base_amount,"
        "status,discount_code) VALUES (?,?,?,?,?,?,?)",
        (tid, _ru, plan, amt, base, status, code))


_rorder(_rplan, 200_000, 140_000, "OFF30")
_rorder(_rplan, 200_000, 140_000, "OFF30")
_rorder(_rplan, 200_000, 100_000, "HALFX")
_rorder(_rplan, 200_000, 140_000, "OFF30", status="rejected")
_rorder(_rplan, 200_000, 200_000, None)
_rorder(_rtrial, 0, 0, "OFF30")          # دام: مبلغش صفر است ولی تبدیل نیست

_rep = D.discount_report()
_t = _rep["total"]

check("فقط سفارشِ تاییدشده‌ی کددار شمرده می‌شود", _t["orders"] == 3,
      f"{_t['orders']} سفارش — ردشده و بی‌کد نباید بیایند")
check("سفارشِ پلنِ تست شمرده نمی‌شود",
      _t["orders"] == 3 and _t["sales"] == 380_000,
      "تستِ صفرتومانی و سفارشِ صددرصد تخفیف‌خورده هر دو صفرند؛ "
      "سنجش با is_trial است نه با مبلغ")
check("تخفیف از تفاوتِ پایه و پرداختی می‌آید", _t["given"] == 220_000,
      f"{_t['given']} — ۶۰+۶۰+۱۰۰")
check("و شمارشِ کدها یکتاست", _t["codes"] == 2, str(_t["codes"]))

_top = {x["code"]: x for x in _rep["top"]}
check("هر کد جدا شمرده می‌شود",
      _top["OFF30"]["orders"] == 2 and _top["HALFX"]["orders"] == 1,
      "ردشده در OFF30 نباید بیاید")
check("و بر اساس فروش مرتب است",
      [x["code"] for x in _rep["top"]] == ["OFF30", "HALFX"],
      "مالک می‌خواهد بداند کدام کد بیشتر آورد")

# ── پیگیریِ تست ──
for _i, _used in ((1, 1), (2, 0), (3, 0)):
    D.exec("INSERT INTO discounts (tenant_id,code,percent,max_uses,used_count,"
           "is_active) VALUES (?,?,30,1,?,1)", (tid, f"BACKZ{_i}", _used))
_rorder(_rplan, 200_000, 140_000, "BACKZ1")

_wb = D.discount_report()["winback"]
check("پیگیری می‌گوید به چند نفر کد رفت", _wb["sent"] == 3, str(_wb["sent"]))
check("و چند نفر برگشتند", _wb["used"] == 1, str(_wb["used"]))
check("و چقدر فروش آورد", _wb["sales"] == 140_000, str(_wb["sales"]))
check("کدهای پیگیری از کدهای دیگر جدا شمرده می‌شوند",
      _wb["orders"] == 1 and D.discount_report()["total"]["orders"] == 4,
      "وگرنه نمی‌شود فهمید کدام فروش از پیگیری آمده")

# ── جداییِ مستاجر ──
db.TenantDB(_other).exec(
    "INSERT INTO orders (tenant_id,user_id,plan_id,amount,base_amount,status,"
    "discount_code) VALUES (?,1,1,9999999,9999999,'approved','OFF30')", (_other,))
check("گزارشِ یک مستاجر سفارشِ مستاجرِ دیگر را نمی‌بیند",
      D.discount_report()["total"]["sales"] < 9_000_000,
      "همان کلاسِ باگی که در این مخزن بارها افتاده")

_DBS = io.open("bot/db.py", encoding="utf-8").read()
_fn = _DBS.split("def discount_report(")[1].split("\n    def ")[0]
check("گزارش تستِ رایگان را با is_trial کنار می‌گذارد، نه با مبلغ",
      "COALESCE(p.is_trial, 0) = 0" in _fn,
      "سفارشِ صددرصد تخفیف‌خورده هم صفر است ولی تبدیل است")
check("و فقط سفارشِ تاییدشده را می‌شمارد",
      "o.status = 'approved'" in _fn)


# ═══════════════════════════════════════════════════════════
#  رویدادها — برگه: docs/specs/2026-09-22-bot-events.md
# ═══════════════════════════════════════════════════════════
section("رویدادها")

import events as _EV           # noqa: E402
_HSRC = io.open("bot/handlers.py", encoding="utf-8").read()
_RSRC = io.open("bot/run.py", encoding="utf-8").read()

# ── یک در، نه پنج تا ────────────────────────────────────────────────
#
# اولین نسخه فقط دو `except` را ثبت می‌کرد و probe نشان داد پنلِ
# خاموش از راهِ «اینباند پیدا نشد» بیرون می‌رود — سفارش شکست
# می‌خورد و هیچ رویدادی ثبت نمی‌شد. حالا بدنه `_provision` است و
# پوسته تنها نقطه‌ی ثبت.
_shell = _HSRC.split("def provision(ctx, order_id):")[1].split("\ndef _provision(")[0]
check("شکستِ ساختِ کانفیگ از یک نقطه ثبت می‌شود",
      _shell.count('record(ctx, "provision_failed"') == 1
      and "_provision(ctx, order_id)" in _shell,
      "پنج راهِ شکست، یک درِ خروج")
check("و بدنه خودش چیزی ثبت نمی‌کند",
      'record(ctx, "provision_failed"' not in
      _HSRC.split("def _provision(ctx, order_id):")[1],
      "دو ثبت یعنی دو پیام در گروه")

# ── و همین را با رفتار بسنج، نه با متن ──────────────────────────────
#
# جاروی شکستن: با `if False:` به‌جای `if not ok:` دروازه‌ی بالا سبز
# ماند، چون متنِ `record(...)` هنوز در فایل بود. دروازه‌ای که شکلِ
# کد را می‌سنجد، رفتار را تضمین نمی‌کند.
class _BrokenXUI:
    def __getattr__(self, _n):
        def _boom(*a, **k):
            raise H.XUIError("پنل جواب نداد")
        return _boom


_ev_tid = db.create_tenant("رویداد", bot_token="9:T", owner_tg_id=9)
_ED = db.TenantDB(_ev_tid)
_ED.exec("""INSERT INTO plans (tenant_id,name,price,gb,days,inbound_id)
            VALUES (?,?,?,?,?,?)""", (_ev_tid, "یک‌ماهه", 100_000, 10, 30, 1))
_ED.exec("INSERT INTO users (tenant_id,tg_id,first_name) VALUES (?,?,?)",
         (_ev_tid, 777, "نسرین"))
_eu = _ED.get_user(777)
_eoid = _ED.exec(
    "INSERT INTO orders (tenant_id,user_id,plan_id,amount,base_amount,status)"
    " VALUES (?,?,?,?,?,'pending')",
    (_ev_tid, _eu["id"], _ED.plans()[0]["id"], 100_000, 100_000))

_ectx = H.Ctx(FakeBot(), db.get_tenant(_ev_tid))
# `ctx.xui` امضای اتصال را از خودِ مستاجر می‌سازد و اگر فرق کند
# دوباره `XUI(...)` می‌سازد — پس نشاندنِ `_xui` کافی نیست و خودِ
# کلاس باید عوض شود. (اولین نسخه‌ی این تست همین را جا انداخت و
# `FakeXUI` موفق شد؛ تست غلط بود نه کد.)
_real_xui, H.XUI = H.XUI, lambda *a, **k: _BrokenXUI()
try:
    _eok, _ewhy = H.provision(_ectx, _eoid)
finally:
    H.XUI = _real_xui

_erows = [r["kind"] for r in _ED.events()["rows"]]
check("ساختِ کانفیگِ شکست‌خورده واقعاً رویداد ثبت می‌کند",
      not _eok and "provision_failed" in _erows,
      "، ".join(_erows) or "هیچ رویدادی ثبت نشد")

# و شکستی که از `except` نمی‌آید هم باید ثبت شود — همان راهی که
# probe پیدایش کرد: «اینباند پیدا نشد» یک `return False` ساده است.
# پلنی که وجود ندارد: `provision` این‌جا با یک `return False` ساده
# بیرون می‌رود، نه با raise
_eoid2 = _ED.exec(
    "INSERT INTO orders (tenant_id,user_id,plan_id,amount,base_amount,status)"
    " VALUES (?,?,?,?,?,'pending')",
    (_ev_tid, _eu["id"], 999_999, 999, 999))
_before = _ED.events()["total"]
H.provision(_ectx, _eoid2)
check("و شکستی که استثنا نیست هم ثبت می‌شود",
      _ED.events()["total"] > _before,
      "پلنِ پیدانشده یک return ساده است، نه raise")

# ── ثبت نباید کارِ اصلی را بشکند — باز هم با رفتار ──────────────────
#
# با `raise` به‌جای `return` دروازه‌ی متنی سبز ماند، چون `except`
# هنوز در فایل بود.
class _DeadDB(db.TenantDB):
    def exec(self, *a, **k):
        raise RuntimeError("دیسک پر است")


try:
    _DeadDB(_ev_tid).log("provision_failed", None, {"order": 1})
    _quiet = True
except Exception:
    _quiet = False
check("ثبتِ ناموفقِ رویداد، صداکننده را نمی‌شکند", _quiet,
      "از داخلِ except صدا زده می‌شود؛ خطای فرعی مسیرِ جبران را می‌بندد")


# ── تصمیمِ «گروه را خبر کن» مالِ events.py است، نه صداکننده ─────────
check("تصمیمِ هشدار یک‌جاست",
      _HSRC.count("EV.is_alert(kind)") == 1
      and _RSRC.count("handlers.EV.is_alert(kind)") == 1,
      "هر جای شکست که خودش تصمیم بگیرد، دهمی فراموشش می‌کند")

# ── هر نوعی که ثبت می‌شود باید در KINDS باشد ────────────────────────
#
# نوعِ ناشناخته بی‌صدا دور انداخته نمی‌شود، ولی «رویدادِ ناشناخته»
# در فهرستِ مالک هم چیزی به او نمی‌گوید.
import ast as _ast            # noqa: E402
import glob                   # noqa: E402
import re as _re              # noqa: E402

# با ast، نه regex: صدازدن‌های `_event(t["id"], "reminder_failed", …)`
# اولین آرگومانشان یک اندیس است نه نام، و regexِ اول شش تا از نُه
# صدازدن را ندید — دروازه‌ای که کمتر از واقعیت می‌بیند، سبزِ دروغ
# می‌دهد.
_used = set()
# The panel writes events into the same list (the hourly config sweep), and
# its four kinds were missing: the owner saw "unknown event" every hour.
_PANEL_SRCS = [io.open(p, encoding="utf-8").read() for p in
               ["backend/app.py"] + sorted(glob.glob("backend/pro/*.py"))]
for _src in [_HSRC, _RSRC] + _PANEL_SRCS:
    for _n in _ast.walk(_ast.parse(_src)):
        if not isinstance(_n, _ast.Call):
            continue
        _f = _n.func
        _name = (_f.id if isinstance(_f, _ast.Name)
                 else _f.attr if isinstance(_f, _ast.Attribute) else "")
        if _name not in ("record", "_event", "log"):
            continue
        for _a in _n.args:
            if isinstance(_a, _ast.Constant) and isinstance(_a.value, str):
                _used.add(_a.value)
                break
_unknown = sorted(_used - set(_EV.KINDS))
check("هر نوعی که ربات ثبت می‌کند در KINDS تعریف شده", not _unknown,
      "، ".join(_unknown) if _unknown else f"{len(_used)} نوع")

# ── فهرستِ «خطا» یک تعریف دارد ──────────────────────────────────────
check("فیلترِ «فقط خطاها» از events.py می‌خواند",
      "is_error" in io.open("backend/app.py", encoding="utf-8").read()
      and _EV.is_error("provision_failed") and not _EV.is_error("signup"),
      "دو نسخه‌ی این فهرست یعنی دو جوابِ متفاوت")

# ── و هیچ آماری از events شمرده نمی‌شود ─────────────────────────────
#
# دو منبعِ حقیقت برای یک عدد، همان باگی است که این مخزن هفت بار دیده.
_APP = io.open("backend/app.py", encoding="utf-8").read()
_agg = _re.findall(r"(?:COUNT|SUM)\([^)]*\)[^;\"']{0,80}FROM events", _APP)
check("هیچ عددِ فروشی از جدولِ رویدادها شمرده نمی‌شود", not _agg,
      f"{len(_agg)} شمارش" if _agg else "فروش فقط از orders")

# ── ثبت نباید کارِ اصلی را بشکند ────────────────────────────────────
_logfn = _DBS.split("    def log(self, kind")[1].split("\n    def ")[0]
check("ثبتِ رویداد خطا بالا نمی‌برد",
      _logfn.count("except Exception") >= 2,
      "از داخلِ except صدا زده می‌شود؛ خطای فرعی نباید جای اصلی را بگیرد")
check("و جدول سقف دارد",
      "DELETE FROM events" in _logfn and "EVENT_MAX_ROWS" in _logfn,
      f"سقف {_EV.MAX_ROWS} ردیف در هر مستاجر")


# ── Start after first use (docs/specs/2026-09-30-vpn-fixes.md, task 9) ──
section("شروع از اولین اتصال")
_otg = 88001
D.create_user(_otg, None, "on-use")
D.exec("UPDATE users SET balance=10000000 WHERE tenant_id=? AND tg_id=?", (tid, _otg))
FakeXUI.NEG = True
_ro = H.wallet_purchase(H.Ctx(bot, tenant), D.get_user(_otg), plan["id"])
_so = D.q("SELECT * FROM subscriptions WHERE tenant_id=? AND user_id=? ORDER BY id DESC",
          (tid, D.get_user(_otg)["id"]), one=True)
check("خرید با «شروع از اولین اتصال» ساخته می‌شود (پیش‌فرض روشن)",
      _ro.get("ok") and FakeXUI.LAST_ON_USE is True, _ro.get("why"))
check("تاریخ ندارد و روزهایش در انتظارِ اولین اتصال است",
      _so and not _so["expires_at"] and _so["pending_days"] == plan["days"], dict(_so or {}))
_wo = H.welcome_text(H.Ctx(bot, tenant), D.get_user(_otg))
check("خوش‌آمد می‌گوید «از اولین اتصال»، نه «بدون محدودیت زمانی»",
      "از اولین اتصال" in _wo and "بدون محدودیت زمانی" not in _wo, _wo[-120:])
_rr = H.wallet_purchase(H.Ctx(bot, tenant), D.get_user(_otg), plan["id"], renew_sub_id=_so["id"])
_so2 = D.q("SELECT * FROM subscriptions WHERE tenant_id=? AND id=?", (tid, _so["id"]), one=True)
check("تمدیدِ شروع‌نشده روزها را جمع می‌کند و هنوز تاریخ ندارد",
      _rr.get("ok") and _so2["pending_days"] == 2 * plan["days"] and not _so2["expires_at"],
      dict(_so2))
_st = db.tenant_settings(tid)
_st["start_on_first_use"] = False
db.save_tenant_settings(tid, _st)
H.wallet_purchase(H.Ctx(bot, db.get_tenant(tid)), D.get_user(_otg), plan["id"])
check("خاموش‌کردنش در تنظیمات: از همان لحظه شمرده می‌شود",
      FakeXUI.LAST_ON_USE is False)
_st["start_on_first_use"] = True
db.save_tenant_settings(tid, _st)
FakeXUI.NEG = False


# ── Support replies (docs/specs/2026-09-30-vpn-fixes.md, task 4) ──
section("پاسخ پشتیبانی: یک راه، ربات شلوغ نشود")
_stg = 88002
D.create_user(_stg, None, "support")
_su = D.get_user(_stg)
_sent_to = lambda: [m for m in SENT if m["to"] == _stg]

SENT.clear()
H.support_reply(H.Ctx(bot, db.get_tenant(tid)), _su, "جواب اول")
_nomini = _sent_to()
check("بی مینی‌اپ: متنِ کامل در ربات می‌آید (جای دیگری برای خواندنش نیست)",
      len(_nomini) == 1 and "جواب اول" in _nomini[0]["text"], _nomini[:1])
check("و در صندوق هم ثبت می‌شود",
      any(m["body"] == "جواب اول" and m["sender"] == "admin" for m in D.chat_list(_su["id"])))

_old_pro = H.pro_allowed
H.pro_allowed = lambda f: True
_st = db.tenant_settings(tid)
_st["miniapp_url"] = "https://panel.example/app"
db.save_tenant_settings(tid, _st)
D.exec("UPDATE chat_messages SET read_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND user_id=?",
       (tid, _su["id"]))
D.chat_add(_su["id"], "system", "یادآوری: ۳ روز مانده")      # never read
SENT.clear()
for _k in range(3):
    H.support_reply(H.Ctx(bot, db.get_tenant(tid)), _su, f"جواب {_k}")
_withmini = _sent_to()
check("با مینی‌اپ: سه پاسخ، یک خبر (یادداشتِ خوانده‌نشده‌ی سیستم مانعش نشد)",
      len(_withmini) == 1, len(_withmini))
check("خبر متنِ پاسخ را ندارد", _withmini and "جواب 0" not in _withmini[0]["text"])
_kbs = json.dumps(_withmini[0]["kb"] if _withmini else {}, ensure_ascii=False)
check("دکمه‌اش خودِ گفتگو را باز می‌کند (tab=chat)", "tab=chat" in _kbs and "web_app" in _kbs, _kbs[:160])
D.exec("UPDATE chat_messages SET read_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND user_id=? "
       "AND sender='admin'", (tid, _su["id"]))
SENT.clear()
H.support_reply(H.Ctx(bot, db.get_tenant(tid)), _su, "جواب بعد از خواندن")
check("بعد از خواندن، خبرِ تازه می‌آید", len(_sent_to()) == 1)
_srcH = open(H.__file__, encoding="utf-8").read()
check("پیامِ ادمین و پاسخِ تیکت از همین راه می‌روند",
      _srcH.count("support_reply(ctx, u, txt") == 2
      and 'f"💬 <b>پیام از پشتیبانی</b>' not in _srcH)

# ── /start: trial first and green, the mini app suggested (task 6) ──
section("استارت: دکمه‌ی تست و پیشنهادِ اپلیکیشن")
_wa = H.welcome_text(H.Ctx(bot, db.get_tenant(tid)), _su)
check("خوش‌آمد اپلیکیشن را پیشنهاد می‌کند", "اپلیکیشن" in _wa and "پشتیبانی" in _wa, _wa[-160:])
_mm = H.main_menu(H.Ctx(bot, db.get_tenant(tid)), _su)
_rows = _mm["inline_keyboard"]
_app_btn = [b for r in _rows for b in r if "web_app" in b]
check("دکمه‌ی اپلیکیشن رنگی است (primary)", _app_btn and _app_btn[0].get("style") == "primary",
      _app_btn[:1])
_st["trial_enabled"] = True
db.save_tenant_settings(tid, _st)
_has_trial = bool(D.trial_plan())
if _has_trial:
    _rows = H.main_menu(H.Ctx(bot, db.get_tenant(tid)), D.get_user(_stg))["inline_keyboard"]
    check("تست رایگان اولین دکمه است و سبز",
          _rows[0][0].get("callback_data") == "trial" and _rows[0][0].get("style") == "success",
          _rows[0])
H.pro_allowed = _old_pro
_st.pop("miniapp_url", None)
_st.pop("trial_enabled", None)
db.save_tenant_settings(tid, _st)
_wn = H.welcome_text(H.Ctx(bot, db.get_tenant(tid)), _su)
check("بی مینی‌اپ، پیشنهادش هم نیست", "اپلیکیشن" not in _wn)


os.unlink(tmp)

print(f"\n{'═' * 52}")
print(f"  نتیجه:  {PASS} پاس  |  {FAIL} ناموفق")
print(f"{'═' * 52}\n")
sys.exit(1 if FAIL else 0)
