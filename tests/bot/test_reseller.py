"""
فروش از رباتِ نماینده — از رسید تا کانفیگ، و هر جا که می‌تواند بشکند.

تا نسخه‌ی ۱.۸۵ رباتِ هیچ نماینده‌ای نمی‌توانست حتی یک کانفیگ بسازد:
به ستون‌های خالیِ پنلِ خودش وصل می‌شد، گروه نمی‌فرستاد، شناسه‌ی
کانفیگ را با نامِ فارسیِ او می‌ساخت، و اعتبارِ پیش‌پرداخت را دست
نمی‌زد. هیچ تستی هم این را نمی‌دید، چون همه‌ی تست‌ها با مستاجرِ ریشه
کار می‌کردند — همان که پنلِ خودش را دارد.

پس این‌جا هر ادعا با **رفتار** سنجیده می‌شود، و مسیرِ خراب هم
عمداً شکسته می‌شود: وقتی ساخت موفق است، کسرِ اعتبار چه قبلش باشد
چه بعدش، عدد درست درمی‌آید — تفاوت فقط وقتی دیده می‌شود که پنل
کانفیگ را نسازد.

اجرا:  python3 tests/bot/test_reseller.py
"""
import json
import os
# repo root and bot/ — these tests moved from bot/ to tests/bot/ (2.0 layout)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOT_DIR = os.path.join(_ROOT_DIR, "bot")

import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, _ROOT_DIR)

tmp = tempfile.mktemp(suffix=".db")
os.environ["BOT_DB_PATH"] = tmp

from bot import db                # noqa: E402
import bot.handlers as H          # noqa: E402

PASS = FAIL = 0
SENT = []
PANELS = []           # هر اتصالِ x-ui که ساخته شد: (url, user)
CREATED = []          # هر create_subscription: kwargs


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


class FakeBot:
    def __init__(self, token=None):
        self.token = token

    def send(self, chat_id, text, keyboard=None, parse_mode="HTML",
             topic_id=None, **kw):
        SENT.append({"to": chat_id, "text": text, "kb": keyboard,
                     "topic": topic_id})
        return {"message_id": len(SENT), "chat": {"id": chat_id}}

    def send_photo(self, chat_id, photo, caption=None, keyboard=None,
                   topic_id=None):
        SENT.append({"to": chat_id, "text": caption, "photo": photo,
                     "kb": keyboard, "topic": topic_id})
        return {"message_id": len(SENT)}

    def send_photo_bytes(self, chat_id, data, filename="qr.png", caption=None,
                         keyboard=None, topic_id=None):
        SENT.append({"to": chat_id, "text": caption, "bytes": True,
                     "kb": keyboard, "topic": topic_id})
        return {"message_id": len(SENT), "result": {"photo": [{"file_id": "F"}]}}

    def action(self, *a, **k):
        return True

    def edit_markup(self, *a, **k):
        return {}

    def answer_cb(self, *a, **k):
        return True


class FakeXUI:
    """امضای سازنده و create_subscription عیناً مثل XUI واقعی."""

    BREAK = False

    def __init__(self, base_url, username=None, password=None, token=None):
        PANELS.append((base_url, username))
        self.base = base_url

    def inbounds(self):
        return [{"id": 7, "enable": True, "remark": "de"}]

    def find_client(self, inbound_id, email=None):
        return None

    def create_subscription(self, inbound_id, email, gb, days, ip_limit=2,
                            tg_id=None, sub_base_url=None, inbound_ids=None,
                            group=None):
        if not self.base:
            # همان چیزی که XUI واقعی با آدرسِ خالی می‌کند: به هیچ‌جا
            raise H.XUIError("no panel url")
        if FakeXUI.BREAK:
            raise H.XUIError("panel said no")
        CREATED.append({"inbound": inbound_id, "email": email, "group": group,
                        "sub_base": sub_base_url, "gb": gb, "days": days,
                        "ip_limit": ip_limit})
        return {"email": email, "uuid": f"u{len(CREATED)}", "sub_id": email,
                "sub_url": f"{(sub_base_url or 'https://p.test/sub')}/{email}",
                "configs": [], "expiry_ms": 1800000000000, "gb": gb}

    def extend_subscription(self, inbound_id, client_uuid, add_days,
                            add_gb=None, reset_traffic=False, email=None):
        if FakeXUI.BREAK:
            raise H.XUIError("panel said no")
        return {"total_bytes": None}


H.Bot = FakeBot
H.XUI = FakeXUI
db.init_db()

# ── مالک: پنل دارد ───────────────────────────────────────────────
ROOT = db.create_tenant("Nexora", bot_token="1:ROOT", owner_tg_id=999)
db.update_tenant(ROOT, panel_url="http://owner-panel:2053",
                 panel_user="admin", panel_pass="x", default_inbound=7)
db.save_tenant_settings(ROOT, {"sub_base_url": "https://sub.owner.test/s"})


def reseller(name, slug, group, credit, cost=150000, price=250000):
    """نماینده بدونِ پنلِ خودش — همان‌طور که پرتال می‌سازد."""
    tid = db.create_tenant(name, bot_token=f"{slug}:TOK", parent_id=ROOT,
                           credit=credit)
    with db.conn() as c:
        c.execute("UPDATE tenants SET portal_slug=?, portal_group=?, "
                  "inbound_mode='all' WHERE id=?", (slug, group, tid))
    d = db.TenantDB(tid)
    d.exec("INSERT INTO plans (tenant_id,name,price,gb,days,ip_limit,cost) "
           "VALUES (?,?,?,?,?,?,?)", (tid, "ماهانه", price, 50, 30, 1, cost))
    plan = d.plans()[0]
    return tid, d, plan


def ctx_for(tid):
    return H.Ctx(FakeBot(), db.get_tenant(tid))


def order_for(d, plan, tg=5001, kind="new", renew_sub_id=None):
    u = d.get_user(tg) or d.create_user(tg, first_name="مشتری")
    u = d.get_user(tg)
    o = d.create_order(u["id"], plan["id"], plan["price"], plan["price"],
                       kind=kind, renew_sub_id=renew_sub_id)
    oid = o["id"] if isinstance(o, dict) else o
    d.exec("UPDATE orders SET status='awaiting' WHERE tenant_id=? AND id=?",
           (d.tid, oid))
    return oid, u


def credit_of(tid):
    return int(db.get_tenant(tid)["credit"])


def ledger(tid):
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT amount, note FROM credit_tx WHERE tenant_id=? ORDER BY id",
            (tid,))]


# ═══════════════════════════════════════════════════════════
section("اتصال — نماینده به پنلِ مالک وصل می‌شود")
# ═══════════════════════════════════════════════════════════
R1, D1, P1 = reseller("حسین", "hossein", "grp-hossein", credit=-1)
ctx = ctx_for(R1)
ctx.xui                                            # noqa: B018
check("اتصالِ ربات به پنلِ مالک است، نه ستون‌های خالیِ نماینده",
      PANELS and PANELS[-1][0] == "http://owner-panel:2053",
      f"{PANELS[-1] if PANELS else '—'}")

root_ctx = ctx_for(ROOT)
root_ctx.xui                                       # noqa: B018
check("مالک همچنان به پنلِ خودش", PANELS[-1][0] == "http://owner-panel:2053")

# ═══════════════════════════════════════════════════════════
section("فروشِ بدهکار — گروه، پیشوند، لینک")
# ═══════════════════════════════════════════════════════════
oid, u = order_for(D1, P1)
ok, res = H.approve_order(ctx, oid, 1)
check("سفارش تایید شد", ok, str(res)[:80])
c = CREATED[-1] if CREATED else {}
check("کانفیگ در گروهِ نماینده ساخته شد", c.get("group") == "grp-hossein",
      f"group={c.get('group')!r}")
check("شناسه‌ی کانفیگ لاتین و با نشانیِ پرتال است",
      str(c.get("email", "")).startswith("hossein_")
      and str(c.get("email", "")).isascii(), c.get("email"))
check("پایه‌ی لینک از مالک آمد وقتی نماینده ندارد",
      c.get("sub_base") == "https://sub.owner.test/s", c.get("sub_base"))
check("اینباند از پیش‌فرضِ مالک", c.get("inbound") == 7, c.get("inbound"))
o = D1.get_order(oid)
check("سفارش approved شد", o["status"] == "approved", o["status"])
check("بدهکار: اعتباری کم نشد", credit_of(R1) == -1 and not ledger(R1))

# ═══════════════════════════════════════════════════════════
section("بی‌گروه — ساخته نمی‌شود")
# ═══════════════════════════════════════════════════════════
R2, D2, P2 = reseller("بی‌گروه", "nogrp", "", credit=-1)
n0 = len(CREATED)
oid2, _ = order_for(D2, P2)
ok, res = H.approve_order(ctx_for(R2), oid2, 1)
check("نماینده‌ی بی‌گروه فروش نمی‌سازد", not ok, str(res)[:70])
check("و دلیلش را می‌گوید", "گروه" in str(res))
check("و پنل اصلاً صدا زده نشد", len(CREATED) == n0)
check("سفارش approved نماند",
      D2.get_order(oid2)["status"] != "approved", D2.get_order(oid2)["status"])

# ═══════════════════════════════════════════════════════════
section("پیش‌پرداخت — کسر، کمبود، و برگشت")
# ═══════════════════════════════════════════════════════════
R3, D3, P3 = reseller("پیش‌پرداخت", "pre", "grp-pre", credit=400000)
ctx3 = ctx_for(R3)

oid3, u3 = order_for(D3, P3, tg=6001)
ok, res = H.approve_order(ctx3, oid3, 1)
check("فروش انجام شد", ok, str(res)[:60])
check("کفِ پلن از اعتبار کم شد", credit_of(R3) == 250000, credit_of(R3))
lg = ledger(R3)
email3 = CREATED[-1]["email"]
check("دفترِ اعتبار شناسه‌ی کانفیگ را دارد",
      lg and lg[-1]["amount"] == -150000 and email3 in lg[-1]["note"],
      lg[-1] if lg else "—")

# پنل نمی‌سازد → پول برمی‌گردد و سفارش approved نمی‌ماند
FakeXUI.BREAK = True
oid4, _ = order_for(D3, P3, tg=6002)
ok, res = H.approve_order(ctx3, oid4, 1)
FakeXUI.BREAK = False
check("پنل نساخت — فروش شکست خورد", not ok)
check("اعتبار برگشت", credit_of(R3) == 250000, credit_of(R3))
check("سفارش approved نماند", D3.get_order(oid4)["status"] != "approved",
      D3.get_order(oid4)["status"])
check("برگشت در دفتر ثبت شد", ledger(R3)[-1]["amount"] == 150000,
      ledger(R3)[-1])

# کمبود اعتبار → پنل صدا زده نمی‌شود
with db.conn() as cn:
    cn.execute("UPDATE tenants SET credit=100000 WHERE id=?", (R3,))
n0 = len(CREATED)
oid5, _ = order_for(D3, P3, tg=6003)
ok, res = H.approve_order(ctx_for(R3), oid5, 1)
check("اعتبارِ ناکافی — ساخته نشد", not ok and len(CREATED) == n0, str(res)[:70])
# پیامِ تلگرام با core.toman: رقمِ فارسی، نه «150,000»ِ لاتین وسطِ جمله
check("و عددِ لازم و موجودی را می‌گوید", "۱۵۰،۰۰۰" in str(res)
      and "۱۰۰،۰۰۰" in str(res), str(res)[:90])
check("اعتبار دست نخورد", credit_of(R3) == 100000)

# تمدید: کسر، و برگشت اگر پنل تمدید نکرد
with db.conn() as cn:
    cn.execute("UPDATE tenants SET credit=400000 WHERE id=?", (R3,))
sub3 = D3.user_subs(u3["id"])[0]
oid6, _ = order_for(D3, P3, tg=6001, kind="renew", renew_sub_id=sub3["id"])
ok, res = H.approve_order(ctx_for(R3), oid6, 1)
check("تمدید انجام شد", ok, str(res)[:60])
check("تمدید هم کف را کم کرد", credit_of(R3) == 250000, credit_of(R3))

FakeXUI.BREAK = True
oid7, _ = order_for(D3, P3, tg=6001, kind="renew", renew_sub_id=sub3["id"])
ok, res = H.approve_order(ctx_for(R3), oid7, 1)
FakeXUI.BREAK = False
check("تمدیدِ شکسته — اعتبار برگشت", not ok and credit_of(R3) == 250000,
      credit_of(R3))
check("و قفلِ تمدید آزاد شد",
      D3.q("SELECT renewing_at FROM subscriptions WHERE tenant_id=? AND id=?",
           (R3, sub3["id"]), one=True)["renewing_at"] in (None, ""))

# ═══════════════════════════════════════════════════════════
section("مالک — مسیرش همان است که بود")
# ═══════════════════════════════════════════════════════════
DR = db.TenantDB(ROOT)
DR.exec("INSERT INTO plans (tenant_id,name,price,gb,days,ip_limit) "
        "VALUES (?,?,?,?,?,?)", (ROOT, "p", 100000, 10, 30, 1))
oidr, _ = order_for(DR, DR.plans()[0], tg=7001)
ok, res = H.approve_order(root_ctx, oidr, 1)
check("فروشِ مالک", ok, str(res)[:60])
check("بدونِ گروه (مالک گروه ندارد)", CREATED[-1]["group"] is None)

# ═══════════════════════════════════════════════════════════
section("رسید — به کسی می‌رسد")
# ═══════════════════════════════════════════════════════════
c1 = ctx_for(R1)
check("بدونِ گروه و بدونِ صاحب: جایی نیست", c1.staff_chat("receipts") == (None, None))

db.update_tenant(R1, owner_tg_id=424242)
c1 = ctx_for(R1)
check("با صاحبِ وصل‌شده: رسید به پیویِ او",
      c1.staff_chat("receipts") == (424242, None), c1.staff_chat("receipts"))
check("هشدار هم", c1.staff_chat("alerts")[0] == 424242)
check("ولی عضوِ تازه نه — در پیوی سیل است",
      c1.staff_chat("users") == (None, None))

n0 = len(SENT)
c1.notify_group("رسید تست", topic="receipts")
check("notify_group واقعاً به پیوی فرستاد",
      len(SENT) > n0 and SENT[-1]["to"] == 424242)

db.update_tenant(R1, admin_group_id=-100777)
check("گروه اگر باشد اولویت دارد",
      ctx_for(R1).staff_chat("receipts")[0] == -100777)

# ═══════════════════════════════════════════════════════════
section("وصل‌شدن از پرتال — /start own_…")
# ═══════════════════════════════════════════════════════════
R4, D4, _p4 = reseller("وصل", "link", "grp-link", credit=-1)


def claim(tid, code, until_min=30, tg=31337, arg=None):
    st = db.tenant_settings(tid)
    if code is not None:
        st["owner_claim"] = {
            "code": code,
            "until": (datetime.now() + timedelta(minutes=until_min)
                      ).isoformat(timespec="seconds")}
        db.save_tenant_settings(tid, st)
    msg = {"from": {"id": tg, "first_name": "R"}, "chat": {"id": tg,
           "type": "private"}, "text": f"/start own_{arg or code}"}
    H.dispatch(db.get_tenant(tid), FakeBot(), {"message": msg})


claim(R4, "WRONGCODE-1", arg="nope")
check("کدِ اشتباه وصل نمی‌کند", not db.get_tenant(R4)["owner_tg_id"])
check("و می‌گوید چرا", "معتبر نیست" in SENT[-1]["text"])

claim(R4, "OLD-CODE-2", until_min=-1)
check("کدِ منقضی وصل نمی‌کند", not db.get_tenant(R4)["owner_tg_id"])

claim(R4, "GOOD-CODE-3")
check("کدِ درست وصل می‌کند", db.get_tenant(R4)["owner_tg_id"] == 31337,
      db.get_tenant(R4)["owner_tg_id"])
check("کد سوخت", "owner_claim" not in db.tenant_settings(R4))
check("و کدِ معرف ثبت نشد",
      not (D4.get_user(31337) or {}).get("referred_by"))

claim(R4, None, tg=55555, arg="GOOD-CODE-3")
check("همان لینک دوباره کار نمی‌کند",
      db.get_tenant(R4)["owner_tg_id"] == 31337)

# دو Start هم‌زمان: هر دو کدِ زنده را خوانده‌اند. فقط یکی باید برنده شود.
R5, D5, _p5 = reseller("مسابقه", "race", "grp-race", credit=-1)
st5 = db.tenant_settings(R5)
st5["owner_claim"] = {"code": "RACE-CODE", "until": (
    datetime.now() + timedelta(minutes=30)).isoformat(timespec="seconds")}
db.save_tenant_settings(R5, st5)
_stale = db.get_tenant(R5)                       # آنچه نفرِ دوم خوانده بود
claim(R5, None, tg=111, arg="RACE-CODE")         # نفرِ اول برنده
_real_get = H.DB.get_tenant
H.DB.get_tenant = lambda tid: dict(_stale) if tid == R5 else _real_get(tid)
try:
    claim(R5, None, tg=222, arg="RACE-CODE")     # نفرِ دوم با خواندنِ کهنه
finally:
    H.DB.get_tenant = _real_get
check("دو Start هم‌زمان: فقط اولی وصل می‌شود",
      db.get_tenant(R5)["owner_tg_id"] == 111, db.get_tenant(R5)["owner_tg_id"])
check("و دومی می‌فهمد لینک استفاده شد", "همین حالا استفاده شد" in SENT[-1]["text"])

# ═══════════════════════════════════════════════════════════
section("تستِ رایگانِ نماینده — رایگان، بی‌گروه، با عددهای مالک")
# ═══════════════════════════════════════════════════════════
# تصمیمِ مالک: تستِ نماینده مجاز و رایگان است، هزینه با مالک. پس
# نباید در صورتحسابِ نماینده بیاید (بی‌گروه) و نباید از اعتبارش کم
# شود — ولی از تستِ خودِ مالک هم بزرگ‌تر نباشد.
R6, D6, _p6 = reseller("تست‌دار", "trialshop", "grp-trial", credit=300000)
D6.exec("INSERT INTO plans (tenant_id,name,price,gb,days,ip_limit,is_trial,is_active) "
        "VALUES (?,?,?,?,?,?,1,1)", (R6, "تست", 0, 1, 1, 1))
tplan = D6.trial_plan()


def trial_order(tg):
    u = D6.get_user(tg) or D6.create_user(tg, first_name="t")
    u = D6.get_user(tg)
    o = D6.create_order(u["id"], tplan["id"], 0, 0)
    return o["id"] if isinstance(o, dict) else o


# مالک هنوز تست ندارد → تستِ نماینده ساخته نمی‌شود
n0 = len(CREATED)
ok, res = H.provision(ctx_for(R6), trial_order(8001))
check("مالک تست ندارد: تستِ نماینده ساخته نمی‌شود", not ok and len(CREATED) == n0,
      str(res)[:70])

DR.exec("INSERT INTO plans (tenant_id,name,price,gb,days,ip_limit,is_trial,is_active) "
        "VALUES (?,?,?,?,?,?,1,1)", (ROOT, "تست مالک", 0, 2, 1, 1))
ok, res = H.provision(ctx_for(R6), trial_order(8002))
check("زیرِ سقف: ساخته می‌شود", ok, str(res)[:60])
check("بی‌گروه — در صورتحسابِ نماینده نمی‌آید", CREATED[-1]["group"] is None,
      CREATED[-1]["group"])
check("و از اعتبارش چیزی کم نشد", credit_of(R6) == 300000, credit_of(R6))
check("شناسه همچنان مالِ فروشگاه است", CREATED[-1]["email"].startswith("trialshop_"))

check("حجمِ تست همانِ مالک است، نه ردیفِ نماینده (۱ گیگ)", CREATED[-1]["gb"] == 2,
      CREATED[-1]["gb"])

# نماینده ردیفش را بزرگ کرده (مستقیم در دیتابیس) → باز هم عددِ مالک ساخته می‌شود.
# مالک: «حجمش را خودم مشخص می‌کنم، وگرنه ممکن است حجمِ زیاد بگذارد».
D6.exec("UPDATE plans SET gb=50, days=30, ip_limit=5 WHERE tenant_id=? AND id=?",
        (R6, tplan["id"]))
tplan = D6.trial_plan()
ok, res = H.provision(ctx_for(R6), trial_order(8003))
check("ردیفِ ۵۰ گیگی: با ۲ گیگ/۱ روز/۱ کاربرِ مالک ساخته می‌شود",
      ok and (CREATED[-1]["gb"], CREATED[-1]["days"], CREATED[-1]["ip_limit"]) == (2, 1, 1),
      str(CREATED[-1]))

# تنظیمِ جدای مالک برای نماینده‌ها بر تستِ خودش مقدم است
_rs = db.tenant_settings(ROOT)
_rs["reseller_trial"] = {"enabled": True, "gb": 3, "days": 2, "ip_limit": 1}
db.save_tenant_settings(ROOT, _rs)
ok, res = H.provision(ctx_for(R6), trial_order(8004))
check("تنظیمِ «تستِ نماینده‌ها»: ۳ گیگ/۲ روز",
      ok and (CREATED[-1]["gb"], CREATED[-1]["days"]) == (3, 2), str(CREATED[-1]))

# مالک خاموشش کرد → ساخته نمی‌شود، با دلیل
_rs["reseller_trial"] = {"enabled": False, "gb": 3, "days": 2, "ip_limit": 1}
db.save_tenant_settings(ROOT, _rs)
n0 = len(CREATED)
ok, res = H.provision(ctx_for(R6), trial_order(8005))
check("تستِ نماینده‌ها خاموش: ساخته نمی‌شود", not ok and len(CREATED) == n0, str(res)[:70])
check("و دلیل را می‌گوید", "خاموش" in str(res))
_rs.pop("reseller_trial")
db.save_tenant_settings(ROOT, _rs)

# دکمه‌ی تست فقط وقتی پلنی هست
st6 = db.tenant_settings(R4)
st6["trial_enabled"] = True
db.save_tenant_settings(R4, st6)
u4 = D4.get_user(31337) or D4.create_user(31337, first_name="o")
u4 = D4.get_user(31337)
kb4 = str(H.main_menu(ctx_for(R4), u4))
check("تست روشن ولی بی‌پلن: دکمه نشان داده نمی‌شود", "trial" not in kb4,
      "دکمه‌ای که جوابش «فعال نیست» است از نبودنش بدتر است")

# ═══════════════════════════════════════════════════════════
section("اشتراکِ فروشگاه — بی‌اشتراک، ربات و مینی‌اپ نمی‌فروشند")
# ═══════════════════════════════════════════════════════════
# برگه: docs/specs/2026-09-26-reseller-store-subscription.md
# رفتار سنجیده می‌شود، نه متن: هر هسته واقعاً صدا زده می‌شود و پولی
# که نباید جابه‌جا شود، شمرده می‌شود.
R7, D7, P7 = reseller("فروشگاه-بسته", "shut", "grp-shut", 900000)
u7 = D7.get_user(7001) or D7.create_user(7001, first_name="خریدار")
D7.exec("UPDATE users SET balance=? WHERE tenant_id=? AND tg_id=?", (400000, R7, 7001))
u7 = D7.get_user(7001)
st7 = db.tenant_settings(R7)
st7["cards"] = [{"number": "6037000000000000", "holder": "x", "bank": "y"}]
db.save_tenant_settings(R7, st7)


def set_store(price, until=None):
    rs = db.tenant_settings(ROOT)
    rs["store_addon"] = {"price": price, "days": 30}
    db.save_tenant_settings(ROOT, rs)
    st = db.tenant_settings(R7)
    if until is None:
        st.pop("store_until", None)
    else:
        st["store_until"] = until
    db.save_tenant_settings(R7, st)


def n_orders():
    with db.conn() as c:
        return c.execute("SELECT COUNT(*) FROM orders WHERE tenant_id=?", (R7,)).fetchone()[0]


def said(text):
    return bool(SENT) and text in (SENT[-1].get("text") or "")


set_store(0)
check("قیمتِ صفر (پیش‌فرض): باز — به‌روزرسانی فروشِ کسی را قطع نمی‌کند",
      H.store_gate(ctx_for(R7)) is None)

set_store(500000)
c7 = ctx_for(R7)
check("قیمت گذاشته شد، تاریخی نیست: بسته", H.store_gate(c7) == H.core.STORE_CLOSED)

n0 = n_orders()
ok, r = H.card_order(c7, u7, P7["id"])
check("کارت: سفارش ساخته نمی‌شود",
      not ok and r == {"why": "store_closed"} and n_orders() == n0, str(r))

r = H.wallet_purchase(c7, u7, P7["id"])
check("کیف پول: رد می‌شود و موجودی دست نمی‌خورد",
      r == {"ok": False, "why": "store_closed"}
      and D7.get_user(7001)["balance"] == 400000 and n_orders() == n0, str(r)[:80])

try:
    H.topup_order(c7, u7, 100000)
    check("شارژِ کیف پول رد می‌شود", False, "no error")
except ValueError as e:
    check("شارژِ کیف پول رد می‌شود — با همان جمله",
          str(e) == H.core.STORE_CLOSED and n_orders() == n0, str(e)[:60])

SENT.clear()
H.give_trial(c7, {"tg_id": 7001}, 7001, None)
check("تست رایگان: همان جمله", said(H.core.STORE_CLOSED))

SENT.clear()
H.show_plans(c7, {"tg_id": 7001}, 7001, None)
check("دکمه‌ی خرید: همان اول می‌گوید، نه بعد از انتخابِ پلن", said(H.core.STORE_CLOSED))

SENT.clear()
H.checkout(c7, u7, 7001, None, P7["id"], False)
check("پوسته‌ی کارت (checkout) جمله را نشان می‌دهد، نه KeyError", said(H.core.STORE_CLOSED))

SENT.clear()
H.wallet_pay(c7, u7, 7001, None, P7["id"])
check("پوسته‌ی کیف پول هم", said(H.core.STORE_CLOSED))

H.auto_renew_subscription(db.get_tenant(R7), FakeBot(),
                          {"id": 1, "plan_id": P7["id"], "user_id": u7["id"]})
check("تمدیدِ خودکار: نه سفارشی، نه کسری",
      n_orders() == n0 and D7.get_user(7001)["balance"] == 400000)

check("فروشگاهِ مالک هرگز بسته نیست", H.store_gate(ctx_for(ROOT)) is None)

set_store(500000, (datetime.now() + timedelta(days=5)).isoformat(timespec="seconds"))
c7 = ctx_for(R7)
check("با اشتراکِ فعال: باز", H.store_gate(c7) is None)
ok, r = H.card_order(c7, u7, P7["id"])
check("و سفارشِ کارت ساخته می‌شود", ok and n_orders() == n0 + 1, str(r)[:60])

set_store(500000, (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds"))
check("اشتراکِ تمام‌شده: بسته", H.store_gate(ctx_for(R7)) == H.core.STORE_CLOSED)
set_store(500000, "not-a-date")
check("تاریخِ خراب: بسته، نه بازِ بی‌صدا", H.store_gate(ctx_for(R7)) == H.core.STORE_CLOSED)
set_store(0)

print(f"\n{'═' * 52}\n  {PASS} پاس · {FAIL} شکست\n{'═' * 52}")
try:
    os.remove(tmp)
except OSError:
    pass
sys.exit(1 if FAIL else 0)
