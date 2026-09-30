"""
تست جامع منطق ربات — بدون نیاز به تلگرام یا پنل واقعی.

اجرا:  python3 tests/bot/test_bot.py
"""
import os
# repo root and bot/ — these tests moved from bot/ to tests/bot/ (2.0 layout)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOT_DIR = os.path.join(_ROOT_DIR, "bot")

import sys
import tempfile

sys.path.insert(0, _ROOT_DIR)

from bot import core, db

PASS = FAIL = 0


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


# ═══════════════════ سیستم سکه ═══════════════════
section("سیستم سکه و تخفیف پلکانی")

s = core.coin_settings({})
check("پله‌های پیش‌فرض", len(s["tiers"]) == 5, f"{len(s['tiers'])} پله")

for coins, expect in [(0, 0), (19, 0), (20, 10), (39, 10), (40, 20), (99, 40), (100, 50), (500, 50)]:
    t = core.tier_for(coins, s)
    got = t["percent"] if t else 0
    check(f"{coins} سکه → {expect}٪", got == expect, f"دریافت: {got}٪")

nt = core.next_tier(25, s)
check("پله بعدی از ۲۵ سکه", nt and nt["coins"] == 40, f"{nt['coins'] if nt else '-'} سکه")
check("سقف: پله بعدی بعد از ۱۰۰", core.next_tier(100, s) is None)

p = core.coin_progress(30, s)
check("نمایش پیشرفت", p["current_percent"] == 10 and p["next"]["need"] == 10,
      f"الان {p['current_percent']}٪ | {p['next']['need']} سکه تا پله بعد")

# مصرف سکه
amount = 100_000
res = core.apply_coins(amount, 40, s)
check("۴۰ سکه روی ۱۰۰ هزار", res["discount"] == 20_000 and res["price"] == 80_000,
      f"تخفیف {res['discount']:,} → پرداختی {res['price']:,}")
check("سکه‌ها مصرف شدند", res["coins_used"] == 40, f"{res['coins_used']} سکه")

res2 = core.apply_coins(amount, 15, s)
check("کمتر از حد نصاب تخفیف ندارد", res2["discount"] == 0 and res2["coins_used"] == 0)

res3 = core.apply_coins(amount, 250, s)
check("سقف ۵۰٪ رعایت می‌شود", res3["discount"] == 50_000,
      f"تخفیف {res3['discount']:,} از {amount:,}")
check("فقط سکه لازم مصرف می‌شود", res3["coins_used"] == 100,
      f"{res3['coins_used']} از ۲۵۰ سکه")

# ═══════════════════ قیمت‌گذاری ═══════════════════
section("قیمت‌گذاری سفارش")

PRICE = 200_000

o = core.price_order(PRICE, coin_cfg=s)
check("بدون تخفیف", o["final"] == 200_000, f"{o['final']:,} تومان")

o = core.price_order(PRICE, coins=60, coin_cfg=s, use_coins=True)
check("با ۶۰ سکه (۳۰٪)", o["final"] == 140_000, f"{o['final']:,} تومان")
check("سکه‌های مصرفی ثبت شد", o["coins_used"] == 60, f"{o['coins_used']} سکه")

o = core.price_order(PRICE, coins=60, coin_cfg=s, use_coins=True, discount_percent=10)
check("کد تخفیف + سکه", o["final"] == 126_000,
      f"{o['final']:,} (۱۰٪ کد سپس ۳۰٪ سکه)")
check("تفکیک تخفیف‌ها", o["code_discount"] == 20_000 and o["coin_discount"] == 54_000,
      f"کد {o['code_discount']:,} | سکه {o['coin_discount']:,}")

o = core.price_order(PRICE, coins=100, coin_cfg=s, use_coins=True,
                     discount_percent=20, reseller_discount=25)
check("سه تخفیف با هم", o["final"] > 0, f"{o['final']:,} تومان")
check("قیمت هرگز منفی نمی‌شود", o["final"] >= 0)

o = core.price_order(PRICE, coins=10, coin_cfg=s, use_coins=True)
check("سکه ناکافی اثری ندارد", o["final"] == 200_000 and o["coins_used"] == 0)

# ═══════════════════ دیتابیس و جداسازی مستاجر ═══════════════════
section("دیتابیس و جداسازی مستاجرها")

tmp = tempfile.mktemp(suffix=".db")
os.environ["BOT_DB_PATH"] = tmp
import importlib
importlib.reload(db)
db.init_db()

t1 = db.create_tenant("Nexora", bot_token="111:AAA", owner_tg_id=100)
t2 = db.create_tenant("Macan", bot_token="222:BBB", owner_tg_id=200, parent_id=t1)
check("ساخت دو مستاجر", bool(t1 and t2 and t1 != t2), f"id: {t1}, {t2}")

tn2 = db.get_tenant(t2)
check("رابطه والد-فرزند", tn2["parent_id"] == t1, f"والد: {tn2['parent_id']}")
check("یافتن مستاجر با توکن", db.get_tenant_by_token("222:BBB")["id"] == t2)

A = db.TenantDB(t1)
B = db.TenantDB(t2)

# محافظ ضد نشت
try:
    A.q("SELECT * FROM users")
    leaked = True
except Exception:
    leaked = False
check("کوئری بدون tenant_id رد می‌شود", not leaked, "محافظ فعال است")

try:
    db.TenantDB(0)
    badid = True
except ValueError:
    badid = False
check("tenant_id نامعتبر رد می‌شود", not badid)

ur1 = A.create_user(555, first_name="کاربر نکسورا")
ur2 = B.create_user(555, first_name="کاربر ماکان")
u1, u2 = ur1["id"], ur2["id"]
check("یک آیدی تلگرام در دو مستاجر", u1 != u2, f"دو رکورد جدا: id={u1}, id={u2}")

g1 = A.get_user(555)
g2 = B.get_user(555)
check("داده‌ها جدا هستند",
      g1["first_name"] == "کاربر نکسورا" and g2["first_name"] == "کاربر ماکان")

check("کد معرف ساخته شد", bool(g1["ref_code"]), g1["ref_code"])
check("یافتن کاربر با کد معرف", A.get_user_by_ref(g1["ref_code"])["id"] == u1)
check("کد معرف حساس به حروف نیست", A.get_user_by_ref(g1["ref_code"].lower())["id"] == u1)
check("کد معرف بین مستاجرها نشت نمی‌کند", B.get_user_by_ref(g1["ref_code"]) is None)

# ═══════════════════ سکه و کیف پول ═══════════════════
section("تراکنش سکه و کیف پول")

A.add_coins(u1, 10, "referral", "دعوت دوست")
A.add_coins(u1, 10, "referral", "دعوت دوست")
check("افزودن سکه", A.get_user(555)["coins"] == 20, f"{A.get_user(555)['coins']} سکه")

A.add_coins(u1, -20, "spend", "استفاده در سفارش")
check("مصرف سکه", A.get_user(555)["coins"] == 0)
check("سکه‌ی مستاجر دیگر دست‌نخورده", B.get_user(555)["coins"] == 0)

A.add_balance(u1, 500_000, "topup", "شارژ اولیه")
check("شارژ کیف پول", A.get_user(555)["balance"] == 500_000,
      f"{A.get_user(555)['balance']:,} تومان")

A.add_balance(u1, -200_000, "purchase", "خرید پلن")
check("برداشت از کیف پول", A.get_user(555)["balance"] == 300_000,
      f"{A.get_user(555)['balance']:,} تومان")

# ═══════════════════ پلن و سفارش ═══════════════════
section("پلن و چرخه سفارش")

A.exec("INSERT INTO plans (tenant_id,name,price,gb,days,sort_order) VALUES (?,?,?,?,?,?)",
       (t1, "۳۰ گیگ ماهانه", 200_000, 30, 30, 1))
B.exec("INSERT INTO plans (tenant_id,name,price,gb,days,sort_order) VALUES (?,?,?,?,?,?)",
       (t2, "پلن ماکان", 250_000, 30, 30, 1))
pa, pb = A.plans(), B.plans()
check("پلن‌ها جدا هستند", len(pa) == 1 and len(pb) == 1 and pa[0]["name"] != pb[0]["name"],
      f"{pa[0]['name']} ↔ {pb[0]['name']}")

A.exec("INSERT INTO plans (tenant_id,name,price,gb,days,is_trial) VALUES (?,?,?,?,?,1)",
       (t1, "تست رایگان", 0, 1, 1))
check("پلن تست از لیست عادی جداست", len(A.plans()) == 1 and A.trial_plan() is not None,
      "پلن تست فقط با trial_plan() برمی‌گردد")

orow = A.create_order(u1, pa[0]["id"], 200_000, 200_000)
oid = orow["id"]
check("ساخت سفارش", bool(oid), f"سفارش #{oid}")
check("مهلت پرداخت تنظیم شد", bool(orow["expires_at"]), "۳۰ دقیقه")

o = A.get_order(oid)
check("وضعیت اولیه", o["status"] in ("pending", "awaiting"), o["status"])
check("سفارش مستاجر دیگر دیده نمی‌شود", B.get_order(oid) is None)

A.exec("""UPDATE orders SET status='awaiting', receipt_type='photo', receipt_file='file_123'
          WHERE tenant_id=? AND id=?""", (t1, oid))
check("ثبت رسید", A.get_order(oid)["receipt_file"] == "file_123")
check("در صف بررسی", len(A.pending_orders()) >= 1, f"{len(A.pending_orders())} سفارش")
check("صف بررسی مستاجر دیگر خالی است", len(B.pending_orders()) == 0)

# وضعیتِ قدیمیِ «review» — در بعضی صفحه‌ها «در انتظار» بود و در بعضی
# نه. بعد از init دیگر نباید وجود داشته باشد، و همان رسید باید در صفِ
# بررسیِ خودِ ربات هم دیده شود.
_n0 = len(A.pending_orders())
A.exec("UPDATE orders SET status='review' WHERE tenant_id=? AND id=?", (t1, oid))
check("رسیدِ «review» پیش از مهاجرت از صف بیرون است",
      len(A.pending_orders()) == _n0 - 1, "همان ناسازگاری‌ای که مهاجرت می‌بندد")
db.init_db()
check("مهاجرت «review» را «awaiting» می‌کند",
      A.get_order(oid)["status"] == "awaiting", A.get_order(oid)["status"])
check("و رسید دوباره در صفِ بررسی است", len(A.pending_orders()) == _n0)

A.exec("UPDATE orders SET status='approved' WHERE tenant_id=? AND id=?", (t1, oid))
check("تایید سفارش", A.get_order(oid)["status"] == "approved")

# ═══════════════════ اشتراک ═══════════════════
section("اشتراک")

A.exec("""INSERT INTO subscriptions
          (tenant_id,user_id,order_id,plan_id,client_email,sub_url,gb,expires_at)
          VALUES (?,?,?,?,?,?,?,datetime('now','+30 days'))""",
       (t1, u1, oid, pa[0]["id"], "nexora_555_1", "https://sub.test/abc", 30))
subs = A.user_subs(u1)
check("اشتراک کاربر ثبت شد", len(subs) == 1 and subs[0]["sub_url"] == "https://sub.test/abc")
check("اشتراک مستاجر دیگر جداست", len(B.user_subs(u2)) == 0)

sub = subs[0]
check("پرچم‌های یادآوری آماده‌اند",
      all(sub[k] == 0 for k in ("notified_7d", "notified_3d", "notified_1d", "notified_80p")),
      "۷ روز / ۳ روز / ۱ روز / ۸۰٪ حجم")
check("تمدید خودکار پیش‌فرض خاموش", sub["auto_renew"] == 0)

d = core.days_left(sub["expires_at"])
check("محاسبه روز باقی‌مانده", 29 <= d <= 30, f"{d} روز")

# ═══════════════════ اعتبار واسطه ═══════════════════
section("اعتبار واسطه")

db.update_tenant(t2, credit=500_000)
check("شارژ اعتبار واسطه", db.get_tenant(t2)["credit"] == 500_000,
      f"{db.get_tenant(t2)['credit']:,} تومان")

# ═══════════════════ تنظیمات مستاجر ═══════════════════
section("تنظیمات هر مستاجر")

db.save_tenant_settings(t1, {"cards": [{"number": "6037-1111", "holder": "علی"}],
                             "coins": {"per_referral": 15}})
st1 = db.tenant_settings(t1)
check("ذخیره تنظیمات", st1["coins"]["per_referral"] == 15)
check("تنظیمات مستاجرها جداست", db.tenant_settings(t2).get("coins") is None)

merged = core.coin_settings(st1["coins"])
check("ادغام با پیش‌فرض", merged["per_referral"] == 15 and len(merged["tiers"]) == 5,
      f"سکه هر معرفی: {merged['per_referral']} | {len(merged['tiers'])} پله پیش‌فرض حفظ شد")

custom = core.coin_settings({"tiers": [{"coins": 50, "percent": 25},
                                       {"coins": 10, "percent": 5}]})
check("پله‌های سفارشی مرتب می‌شوند", custom["tiers"][0]["coins"] == 10,
      f"{[t['coins'] for t in custom['tiers']]}")

# ═══════════════════ ابزارهای نمایش ═══════════════════
section("ابزارهای نمایش")

check("قالب‌بندی تومان", len(core.toman(1234567)) > 7, core.toman(1234567))

# تاریخ شمسی — مشتری ایرانی «2027-01-15» را نمی‌خواند
_d = core.fa_date("2027-01-15")
check("تاریخ شمسی می‌شود", "دی" in _d and "۱۴۰۵" in _d, _d)
check("تاریخ کوتاه شمسی", core.fa_date("2027-01-15", False) == "۱۴۰۵/۱۰/۲۵",
      core.fa_date("2027-01-15", False))
check("اول فروردین درست تبدیل می‌شود",
      core.fa_date("2026-03-21").startswith("۱ فروردین"),
      core.fa_date("2026-03-21"))
# نمایش تاریخ نباید بتواند پیام را از کار بیندازد
check("ورودی خراب خطا نمی‌دهد", core.fa_date("خراب") == "خراب")
check("ورودی خالی خطا نمی‌دهد", core.fa_date(None) == "" and core.fa_date("") == "")
check("قالب‌بندی حجم", "۳۰" in core.fmt_gb(30), core.fmt_gb(30))
check("حجم نامحدود", "نامحدود" in core.fmt_gb(0), core.fmt_gb(0))
check("مدت نامحدود", "محدودیت" in core.fmt_days(0) or "نامحدود" in core.fmt_days(0),
      core.fmt_days(0))

# ارقامی که کاربر می‌خواند فارسی‌اند، ولی چیزهای قابل‌کپی نه —
# رقم فارسی داخل شماره‌ی کارت یعنی مشتری نمی‌تواند پیست کند.
check("ارقام خواندنی فارسی‌اند", not any(c.isdigit() and c.isascii()
                                        for c in core.toman(190000)),
      core.toman(190000))
check("شماره کارت لاتین می‌ماند", "6037" in core.fmt_card("6037997512345678"),
      core.fmt_card("6037997512345678"))

email = core.make_email("Sh-op", 200)
check("نامِ کانفیگ: پیشوند_شماره — بی آیدیِ تلگرام", email == "shop_200", email)

cards = [{"number": "6037111122223333", "holder": "علی"},
         {"number": "5892444455556666", "holder": "علی", "active": False}]
picked = [core.pick_card(cards) for _ in range(8)]
check("کارت غیرفعال انتخاب نمی‌شود",
      all(p["number"].startswith("6037") for p in picked), "۸ بار تست شد")
check("بدون کارت فعال → None", core.pick_card([]) is None)
check("قالب‌بندی شماره کارت", "-" in core.fmt_card("6037111122223333"),
      core.fmt_card("6037111122223333"))

# ═══════════════════ آمار ═══════════════════
section("آمار")

s1 = A.stats()
check("آمار مستاجر اول", s1["users"] == 1, f"{s1['users']} کاربر")
s2 = B.stats()
check("آمار مستاجر دوم جداست", s2["users"] == 1 and s2.get("revenue", 0) == 0,
      f"{s2['users']} کاربر")

# ═══════════════════ چند روز از انقضا گذشته ═══════════════════
section("چند روز از انقضا گذشته")

# days_left عمداً هیچ‌وقت منفی نمی‌دهد — ده‌ها جا روی «صفر یعنی تمام
# شده» حساب باز کرده‌اند. ولی صفحه‌ی «اشتراک‌های من» از همان برای
# ساختن «چند روز پیش منقضی شده» استفاده می‌کرد، پس همیشه می‌نوشت
# «۰ روز پیش» — چه دیروز تمام شده بود چه سه ماه پیش.

from datetime import datetime as _d3, timedelta as _t3


def _iso(days):
    return (_d3.now() + _t3(days=days)).isoformat()


check("منقضی‌شده‌ی دیروز یک روز", core.days_past(_iso(-1.2)) == 1,
      str(core.days_past(_iso(-1.2))))
check("منقضی‌شده‌ی سی روز پیش، سی", core.days_past(_iso(-30.5)) == 30,
      str(core.days_past(_iso(-30.5))))
check("اشتراک فعال صفر است", core.days_past(_iso(10)) == 0)
check("بدون تاریخ هم صفر", core.days_past(None) == 0)
check("تاریخ خراب خطا نمی‌دهد", core.days_past("چیزی نیست") == 0)

check("days_left همچنان منفی نمی‌دهد", core.days_left(_iso(-30)) == 0,
      "قرارداد قبلی دست‌نخورده — جاهای دیگر رویش حساب کرده‌اند")
check("و دو تابع با هم جور درمی‌آیند",
      core.days_left(_iso(-5)) == 0 and core.days_past(_iso(-5)) == 5)

_SRC_H = open(os.path.join(_BOT_DIR,
                           "handlers.py"), encoding="utf-8").read()
check("صفحه‌ی اشتراک‌ها از تابع تازه استفاده می‌کند",
      'core.days_past(s.get("expires_at"))' in _SRC_H,
      "وگرنه همچنان «۰ روز پیش» می‌نویسد")
check("و برای امروز جمله‌ی درست دارد",
      "منقضی شد" in _SRC_H,
      "«۰ روز پیش منقضی شده» جمله‌ی فارسی نیست")



os.unlink(tmp)

# ═══════════════════ نتیجه ═══════════════════
print(f"\n{'═' * 52}")
print(f"  نتیجه:  {PASS} پاس  |  {FAIL} ناموفق")
print(f"{'═' * 52}\n")
sys.exit(1 if FAIL else 0)
