#!/usr/bin/env python3
"""
قیفِ فروشگاه — فاز ۱: نام، تست از مینی‌اپ، سفارشِ باز.

برگه: docs/specs/2026-09-27-shop-funnel.md

روی اسکیمای واقعیِ ربات. مسیرِ تستِ ربات را `tests/bot/test_flow.py` می‌سنجد؛
این‌جا همان هسته از راهِ مینی‌اپ، که تا ۱.۱۱۷ اصلاً نبود (پلنِ تست میانِ
پلن‌ها بود و «خرید»ش خطا می‌داد).

اجرا:  python3 tests/test-shop-funnel.py
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="funnel_")
os.environ.update(
    BOT_DB_PATH=os.path.join(TMP, "bot.db"),
    BILLING_DB_PATH=os.path.join(TMP, "billing.db"), NEXORA_ADMIN_PASSWORD="testpw",
    NEXORA_CONFIG=os.path.join(TMP, "config.json"))
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "bot"), str(ROOT / "backend")]

import db as DB                                          # noqa: E402
DB.DB_PATH = Path(os.environ["BOT_DB_PATH"])
DB.init_db()

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


def err_of(fn):
    try:
        fn()
        return 200, ""
    except Exception as e:          # noqa: BLE001
        return getattr(e, "status_code", 500), str(getattr(e, "detail", e))


OWNER = DB.create_tenant("owner", bot_token="1:root", panel_url="http://p",
                         settings={"brand": "فروشگاه", "trial_enabled": True,
                                   "force_channel": "@shop_vpn",
                                   "cards": [{"number": "6037991122223333",
                                              "holder": "علی", "bank": "ملی"}]})
DO = DB.TenantDB(OWNER)
DO.exec("INSERT INTO plans (tenant_id,name,price,gb,days,ip_limit,is_trial,is_active) "
        "VALUES (?,?,?,?,?,?,1,1)", (OWNER, "تست", 0, 1, 1, 1))
DO.exec("INSERT INTO plans (tenant_id,name,price,gb,days,ip_limit,is_trial,is_active) "
        "VALUES (?,?,?,?,?,?,0,1)", (OWNER, "یک‌ماهه", 150000, 50, 30, 2))
DO.create_user(500, first_name="مریم")

import app as AP                                         # noqa: E402
AP.BOT_DB = Path(os.environ["BOT_DB_PATH"])
H = AP._bot_handlers()
# The mini app is Pro (docs/specs/2026-09-29-pro-split.md). Its sections run
# when the tree has it; otherwise the same state is made the core way (the bot).
PRO = bool(getattr(AP, "PRO_LOADED", False))


SENT = []


class _FakeBot:
    member = "left"

    def __init__(self, *a, **k):
        pass

    def send(self, chat_id, text, keyboard=None, **k):
        SENT.append({"to": chat_id, "text": text, "kb": str(keyboard)})
        return {"message_id": 1}

    def edit(self, chat_id, message_id, text, keyboard=None, **k):
        SENT.append({"to": chat_id, "text": text, "kb": str(keyboard), "edit": True})
        return {"message_id": message_id}

    def answer_cb(self, *a, **k):
        return True

    def send_photo_bytes(self, *a, **k):
        return {"message_id": 2}

    def member_status(self, ch, uid):
        return _FakeBot.member


H.Bot = _FakeBot
BUILT = []


def _fake_provision(ctx, oid):
    BUILT.append(oid)
    o = ctx.db.get_order(oid)
    return True, {"sub_url": "https://sub.test/s/x", "client_email": "shop_1",
                  "order_id": oid, "gb": 1, "plan_name": "تست", "user_id": o["user_id"]}


H.provision = _fake_provision
T = AP._tenant_row(OWNER)


def U():
    return DO.get_user(500)


# ═══════════════════════════════════════════════════════════
head("نامِ کانفیگ: پیشوند_شماره، اتمی")
# ═══════════════════════════════════════════════════════════
for i in range(1, 6):
    DO.exec("INSERT INTO subscriptions (tenant_id,user_id,client_email,is_active) "
            "VALUES (?,?,?,1)", (OWNER, U()["id"], f"shop_{i}"))
n1 = DO.next_name_seq("Shop")
check("فروشگاهِ قدیمی از بعدِ بزرگ‌ترین شماره شروع می‌کند (۶)", n1 == 6, n1)
got = []
ths = [threading.Thread(target=lambda: got.append(DB.TenantDB(OWNER).next_name_seq("shop")))
       for _ in range(12)]
[t.start() for t in ths]
[t.join() for t in ths]
check("دوازده خریدِ هم‌زمان، دوازده شماره‌ی متفاوت", len(set(got)) == 12 and min(got) == 7,
      str(sorted(got)))
check("core.make_email بی آیدیِ تلگرام", H.core.make_email("shop", 200) == "shop_200")

# ═══════════════════════════════════════════════════════════
head("دکمه‌ی تستِ رایگان: اول، سبز، و یک‌بار برای هر نفر")
# ═══════════════════════════════════════════════════════════
_c0 = AP._mini_ctx(T)[1]
_mm = H.main_menu(_c0, U())["inline_keyboard"]
check("تستِ رایگان ردیفِ اولِ منوست", _mm[0][0].get("callback_data") == "trial"
      and _mm[0][0]["text"] == H.TRIAL_BUTTON, str(_mm[0]))
check("و سبز است (style=success)", _mm[0][0].get("style") == "success")
_wt = H.welcome_text(_c0, U())
check("پیامِ خوش‌آمد خطِ پررنگِ «تست رایگان داریم» دارد",
      "<b>🎁 تست رایگان داریم!</b>" in _wt, _wt[:80])
_stc = AP._tenant_settings(T)
_stc["welcome_text"] = "سلام {name} — به {brand} خوش آمدی"
AP._save_tenant_settings(OWNER, _stc)
_c1 = AP._mini_ctx(AP._tenant_row(OWNER))[1]
check("… حتی وقتی فروشگاه متنِ خوش‌آمدِ خودش را دارد",
      "تست رایگان داریم" in H.welcome_text(_c1, U()))
_stc.pop("welcome_text", None)
AP._save_tenant_settings(OWNER, _stc)

# دکمه‌ی رنگی را سرورِ قدیمیِ تلگرام نشناسد، منو باید بی‌رنگ برسد — نه اصلاً نرسد
import tg as _TG                                          # noqa: E402
_calls = []


class _Resp:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


class _Sess:
    def post(self, url, data=None, files=None, timeout=None):
        _calls.append(dict(data or {}))
        if '"style"' in str((data or {}).get("reply_markup") or ""):
            return _Resp({"ok": False, "error_code": 400,
                          "description": "Bad Request: can't parse inline keyboard button"})
        return _Resp({"ok": True, "result": {"message_id": 7}})


_b = _TG.Bot("0:x")
_b._session = _Sess()
_r = _b.send(1, "سلام", keyboard=_TG.kb([[("🎁 تست", "trial", None, "success")], [("خرید", "buy")]]))
check("تلگرام رنگ را رد کرد: یک‌بار بی‌رنگ دوباره فرستاده شد و رسید",
      _r == {"message_id": 7} and len(_calls) == 2 and '"style"' not in _calls[1]["reply_markup"]
      and "_nostyle" not in _calls[1] and "buy" in _calls[1]["reply_markup"], str(_calls)[:160])

# ═══════════════════════════════════════════════════════════
if PRO:
    head("مینی‌اپ: تست جدا از پلن‌ها")
    # ═══════════════════════════════════════════════════════════
    plans = AP.mini_plans(tu=(T, U()))["plans"]
    check("پلنِ تست میانِ پلن‌ها نیست (تا ۱.۱۱۷ بود)", all(not p["isTrial"] for p in plans)
          and len(plans) == 1, str([p["name"] for p in plans]))
    tr = AP.mini_me(tu=(T, U()))["trial"]
    check("/me: تست در دسترس، با سه سؤال و کانال",
          tr["available"] and tr["missing"] == ["operator", "device_os", "real_name"]
          and tr["needChannel"] and tr["channel"] == "https://t.me/shop_vpn", str(tr)[:120])
    check("گزینه‌ها همان فهرستِ core‌اند",
          [o["id"] for o in tr["operators"]] == [k for k, _ in H.core.TRIAL_OPERATORS])

    st, why = err_of(lambda: AP.mini_trial({}, tu=(T, U())))
    check("بی جواب: ۴۰۰ و «اول به سؤال‌ها»", st == 400 and "سؤال" in why, why)
    st, why = err_of(lambda: AP.mini_trial({"operator": "hacker", "os": "ios", "name": "سارا"},
                                            tu=(T, U())))
    check("اپراتورِ ناشناس رد می‌شود", st == 400 and not U().get("operator"), why)
    st, why = err_of(lambda: AP.mini_trial({"operator": "irancell", "os": "ios", "name": "سارا"},
                                            tu=(T, U())))
    check("عضوِ کانال نیست: ۴۰۹، هنوز تستی ساخته نشده",
          st == 409 and "کانال" in why and not BUILT and U()["trial_used"] == 0, why)
    check("ولی جواب‌ها ذخیره شدند (دوباره پرسیده نمی‌شوند)",
          U()["operator"] == "irancell" and U()["device_os"] == "ios" and U()["real_name"] == "سارا")
    _FakeBot.member = "member"
    st, _w = err_of(lambda: AP.mini_trial({}, tu=(T, U())))
    check("عضو شد: تست ساخته شد", st == 200 and len(BUILT) == 1 and U()["trial_used"] == 1, _w)
    o = DO.get_order(BUILT[0])
    check("سفارشِ تست بعد از ساخت approved شد (close_order)", o["status"] == "approved", o["status"])
    st, why = err_of(lambda: AP.mini_trial({}, tu=(T, U())))
    check("دوباره: ۴۰۹ «قبلاً گرفته‌اید»", st == 409 and "قبلاً" in why, why)
    check("و کارتِ تست دیگر نشان داده نمی‌شود", not AP.mini_me(tu=(T, U()))["trial"]["available"])
    _c2 = AP._mini_ctx(T)[1]
    check("گرفته‌شده از مینی‌اپ ← در ربات نه دکمه‌ای، نه خطِ پررنگ",
          all(b.get("callback_data") != "trial" for row in H.main_menu(_c2, U())["inline_keyboard"] for b in row)
          and "تست رایگان داریم" not in H.welcome_text(_c2, U()))
    _nb = len(BUILT)
    check("… و اگر کسی دکمه‌ی قدیمی را بزند، هسته نمی‌سازد",
          H.trial_core(_c2, U()) == (False, "used") and len(BUILT) == _nb)
    DO.create_user(510, first_name="علی")
    _u510 = DO.get_user(510)
    _okb, _resb = H.trial_core(_c2, _u510)
    check("برعکس: کسی که تست را از ربات گرفت…", _okb and len(BUILT) == _nb + 1, str(_resb)[:80])
    _u510 = DO.get_user(510)
    check("… در مینی‌اپ کارتِ تست ندارد", not AP.mini_me(tu=(T, _u510))["trial"]["available"]
          and AP.mini_me(tu=(T, _u510))["trial"]["used"])
    st, why = err_of(lambda: AP.mini_trial({"operator": "mci", "os": "android", "name": "علی"},
                                            tu=(T, DO.get_user(510))))
    check("… و درخواستِ مستقیم هم «قبلاً گرفته‌اید» می‌گیرد، بی ساختِ دوم",
          st == 409 and "قبلاً" in why and len(BUILT) == _nb + 1, why)
    # کاربرِ ۵۱۰ فقط برای همین سنجه بود — آمارِ پایین «یک تست» را می‌شمارد
    _i510 = DO.get_user(510)["id"]
    DO.exec("DELETE FROM orders WHERE tenant_id=? AND user_id=?", (OWNER, _i510))
    DO.exec("DELETE FROM users WHERE tenant_id=? AND id=?", (OWNER, _i510))
    users = AP._users_page(OWNER, q="", limit=10, offset=0)["users"] \
        if hasattr(AP, "_users_page") else []
    check("پاسخ‌ها در «کاربران» خوانا دیده می‌شوند",
          any(x.get("trialInfo") == "سارا · ایرانسل · آیفون" for x in users),
          str([x.get("trialInfo") for x in users]))
else:
    head("Free trial from the bot (Community: no mini app)")
    DO.exec("UPDATE users SET operator='irancell', device_os='ios', real_name='سارا' "
            "WHERE tenant_id=? AND tg_id=500", (OWNER,))
    _FakeBot.member = "member"
    # The bot's own flow: questions answered, member of the channel, then the
    # trial, its delivery and the welcome message the journey checks below.
    H.give_trial(AP._mini_ctx(T)[1], U(), 500, None)
    check("the bot builds the trial", len(BUILT) == 1 and U()["trial_used"] == 1, str(BUILT))
    check("… and the trial order is approved after the config exists (close_order)",
          DO.get_order(BUILT[0])["status"] == "approved")
    check("a second trial is refused", H.trial_core(AP._mini_ctx(T)[1], U()) == (False, "used"))

# ═══════════════════════════════════════════════════════════
if PRO:
    head("سفارشِ باز: زدن، همان کارت و رسید را باز می‌کند")
    # ═══════════════════════════════════════════════════════════
    pid = DO.q("SELECT id FROM plans WHERE tenant_id=? AND is_trial=0", (OWNER,), one=True)["id"]
    od = DO.create_order(U()["id"], pid, 150000, 150000)
    DO.exec("UPDATE orders SET status='pending', card_used='6037-9911-2222-3333' "
            "WHERE tenant_id=? AND id=?", (OWNER, od["id"]))
    r = AP.mini_order_get(od["id"], tu=(T, U()))
    check("همان کارتی که به سفارش داده شد، با نام و بانک",
          r["card"] == {"number": "6037991122223333", "holder": "علی", "bank": "ملی"}, str(r["card"]))
    check("مبلغ و پلن", r["amount"] == 150000 and r["plan"]["name"] == "یک‌ماهه")
    DO.exec("UPDATE orders SET status='awaiting' WHERE tenant_id=? AND id=?", (OWNER, od["id"]))
    st, why = err_of(lambda: AP.mini_order_get(od["id"], tu=(T, U())))
    check("رسید رفته: «منتظرِ تایید»، نه صفحه‌ی کارت", st == 409 and "تایید" in why, why)
    DO.create_user(501, first_name="دیگری")
    st, _w = err_of(lambda: AP.mini_order_get(od["id"], tu=(T, DO.get_user(501))))
    check("سفارشِ کسِ دیگر: ۴۰۴", st == 404)
else:
    pass                                  # the open-order page is the mini app's

# ═══════════════════════════════════════════════════════════
head("پیگیریِ تست — ۰، ۸، ۲۴ ساعت، نظرسنجی، و «خرید موفق»")
# ═══════════════════════════════════════════════════════════
check("پیامِ «تستت فعال شد» با اسمِ خودِ مشتری رفت",
      any("سارا" in m["text"] and "تست فروشگاه برات فعال شد" in m["text"] for m in SENT),
      str([m["text"][:40] for m in SENT][-3:]))
check("و زمانِ تست ثبت شد", bool(U()["trial_at"]) and U()["trial_step"] == 0)

import importlib                                          # noqa: E402
sys.path.insert(0, str(ROOT))
RUN = importlib.import_module("bot.run")
RUN.Bot = _FakeBot
RUN.handlers.Bot = _FakeBot
# The follow-up is Pro since 2.0 (bot/pro/loyalty.py). Where it is, it runs
# licensed here; the Community tree checks that none goes out.
LOY = RUN.handlers.pro("loyalty") is not None
if LOY:
    _pa_run = RUN.handlers.pro_allowed
    RUN.handlers.pro_allowed = lambda f, _o=_pa_run: f == "loyalty" or _o(f)
st0 = AP._tenant_settings(T)
st0["winback"] = {"enabled": True, "percent": 20, "valid_hours": 48}
AP._save_tenant_settings(OWNER, st0)

DO.exec("UPDATE users SET trial_at=datetime('now','-2 hours') WHERE tenant_id=? AND tg_id=500", (OWNER,))
SENT.clear()
RUN.send_trial_journey()
check("۲ ساعت: هنوز چیزی نمی‌رود", not SENT and U()["trial_step"] == 0)
DO.exec("UPDATE users SET trial_at=datetime('now','-9 hours') WHERE tenant_id=? AND tg_id=500", (OWNER,))
RUN.send_trial_journey()
if LOY:
    check("۸ ساعت: نظرسنجیِ کیفیت با ۴ دکمه، با اسم",
          len(SENT) == 1 and "سلام سارا" in SENT[0]["text"] and "tfb:8:bad" in SENT[0]["kb"],
          str(SENT)[:120])
    RUN.send_trial_journey()
    check("دوباره اجرا شد: پیامِ تکراری نه", len(SENT) == 1 and U()["trial_step"] == 1)
else:
    check("Community: no trial follow-up goes out", not SENT and U()["trial_step"] == 0,
          str(SENT)[:80])

ctx = AP._mini_ctx(T)[1]
H.trial_feedback(ctx, U(), 500, 1, "8", "bad")
check("«مشکل داشتم»: توضیح خواسته می‌شود", U()["state"] == "await_trial_problem"
      and "چه مشکلی" in SENT[-1]["text"], SENT[-1]["text"][:50])
H.handle_trial_problem(ctx, {"chat": {"id": 500}, "text": "شب‌ها قطع می‌شود"}, U())
check("و در صندوقِ پیام‌ها نشست",
      any("شب‌ها قطع می‌شود" in (m.get("body") or "") for m in (DO.chat_list(U()["id"]) or [])))
H.trial_feedback(ctx, U(), 500, 1, "16", "speed")
H.trial_feedback(ctx, U(), 500, 1, "16", "hacker")

DO.exec("UPDATE users SET trial_at=datetime('now','-30 hours') WHERE tenant_id=? AND tg_id=500", (OWNER,))
SENT.clear()
RUN.send_trial_journey()
if LOY:
    check("۳۰ ساعت (ربات پایین بود): فقط پیامِ پایان، نه ۱۶ و ۲۴ پشتِ هم",
          len(SENT) == 1 and "تستت به پایان رسید" in SENT[0]["text"] and U()["trial_step"] == 3,
          str([m["text"][:30] for m in SENT]))
    check("با کدِ برگشتِ یک‌بارمصرف", bool(SENT) and "BACK" in SENT[0]["text"] and "۲۰٪" in SENT[0]["text"])
    # A trial far outside the window gets nothing: a license that comes back
    # after a lapse must not send "your trial ended" weeks late.
    DO.exec("UPDATE users SET trial_at=datetime('now','-10 days'), trial_step=0 "
            "WHERE tenant_id=? AND tg_id=500", (OWNER,))
    SENT.clear()
    RUN.send_trial_journey()
    check("a trial 10 days old gets no follow-up (no weeks-late message)",
          not SENT and U()["trial_step"] == 0, str(SENT)[:80])
    DO.exec("UPDATE users SET trial_step=3 WHERE tenant_id=? AND tg_id=500", (OWNER,))
    # Locked: nothing goes out either.
    RUN.handlers.pro_allowed = _pa_run
    DO.exec("UPDATE users SET trial_at=datetime('now','-9 hours'), trial_step=0 "
            "WHERE tenant_id=? AND tg_id=500", (OWNER,))
    SENT.clear()
    RUN.send_trial_journey()
    check("locked: no follow-up goes out", not SENT and U()["trial_step"] == 0, str(SENT)[:80])
    RUN.handlers.pro_allowed = lambda f, _o=_pa_run: f == "loyalty" or _o(f)
    DO.exec("UPDATE users SET trial_step=3 WHERE tenant_id=? AND tg_id=500", (OWNER,))


SENT.clear()
H.deliver(ctx, U(), {"sub_url": "https://sub.test/s/p", "client_email": "shop_40",
                     "gb": 50, "plan_name": "یک‌ماهه"})
check("اولین خریدِ پولی: «خریدت موفق بود» با اسم",
      any("سارا، خریدت با موفقیت انجام شد" in m["text"] for m in SENT),
      str([m["text"][:30] for m in SENT]))
SENT.clear()
H.deliver(ctx, U(), {"sub_url": "https://sub.test/s/q", "client_email": "shop_41", "gb": 50})
check("خریدِ دوم: دوباره نه", not any("خریدت با موفقیت" in m["text"] for m in SENT))

# ═══════════════════════════════════════════════════════════
head("پلن‌ها: نوع ← تبِ مدت ← پلن، با متنِ خودِ فروشگاه")
# ═══════════════════════════════════════════════════════════
import re as _re                                          # noqa: E402
_js = (ROOT / "frontend" / "src" / "lib" / "plankinds.js").read_text(encoding="utf-8")
def _js_list(name):
    """فهرستِ `export const NAME = [...]` در plankinds.js — جفت‌های (id, fa)."""
    part = _js.split(f"export const {name} = [")[1].split("];")[0]
    return _re.findall(r'id: "([a-z_]+)", fa: "([^"]+)"', part)


check("فهرستِ نوع‌ها در core و رابط یکی است",
      _js_list("PLAN_KINDS") == list(H.core.PLAN_KINDS), str(_js_list("PLAN_KINDS")))
check("license plans (monthly/yearly) are the same in core and the panel",
      _js_list("LICENSE_PLANS") == list(H.core.LICENSE_PLANS), str(_js_list("LICENSE_PLANS")))
check("گزینه‌های پیش از تست (پیش‌نمایشِ مینی‌اپ) با core یکی است",
      _js_list("TRIAL_OPERATORS") == list(H.core.TRIAL_OPERATORS)
      and _js_list("TRIAL_OS") == list(H.core.TRIAL_OS))
DO.exec("DELETE FROM plans WHERE tenant_id=? AND is_trial=0", (OWNER,))
for i, (nm, kind, tab) in enumerate([("۳۰ گیگ یک‌ماهه", "volume", "۱ ماهه"),
                                     ("۱۰۰ گیگ دوماهه", "volume", "۲ ماهه"),
                                     ("۲۰۰ گیگ کاربر محدود", "limited", "۱ ماهه")]):
    DO.exec("INSERT INTO plans (tenant_id,name,price,gb,days,ip_limit,is_trial,is_active,"
            "sort_order,kind,tab) VALUES (?,?,?,?,?,?,0,1,?,?,?)",
            (OWNER, nm, 100000 + i, 30, 30, 1, i, kind, tab))
SENT.clear()
H.show_plans(ctx, U(), 500, None)
check("اول نوع (دو نوع هست)", "pk:volume" in SENT[-1]["kb"] and "pk:limited" in SENT[-1]["kb"],
      SENT[-1]["kb"][:120])
H.show_plans(ctx, U(), 500, None, kind="volume")
check("بعد تبِ مدت (دو تب)", "pt:volume:0" in SENT[-1]["kb"] and "۲ ماهه" in SENT[-1]["kb"])
H.show_plans(ctx, U(), 500, None, kind="volume", tab=1)
check("بعد پلن‌های همان تب، با نامِ خودِ فروشگاه",
      "۱۰۰ گیگ دوماهه" in SENT[-1]["kb"] and "۳۰ گیگ" not in SENT[-1]["kb"], SENT[-1]["kb"][:120])
H.show_plans(ctx, U(), 500, None, kind="limited")
check("نوعِ تک‌تب: مرحله‌ی تب پریده می‌شود", "۲۰۰ گیگ کاربر محدود" in SENT[-1]["kb"]
      and "pt:" not in SENT[-1]["kb"])
check("دکمه‌ی پلن: نام + قیمت، بی مشخصاتِ خودکار",
      H.core.plan_line({"name": "طلایی", "gb": 30, "days": 30, "price": 90000}) == f"طلایی · {H.core.toman(90000)} تومان",
      H.core.plan_line({"name": "طلایی", "gb": 30, "days": 30, "price": 90000}))
if PRO:                                   # the mini app is Pro
    mp = AP.mini_plans(tu=(T, U()))["plans"]
    check("مینی‌اپ نوع و تب را می‌گیرد", {(x["kind"], x["tab"]) for x in mp}
          == {("volume", "۱ ماهه"), ("volume", "۲ ماهه"), ("limited", "۱ ماهه")})

# ═══════════════════════════════════════════════════════════
head("Without a license: no satisfaction line, no polls")
# ═══════════════════════════════════════════════════════════
# Customer feedback is Pro (`insights`); the bot preview, the stats and the
# polls themselves are tested in tests/pro/test-shop-funnel-pro.py, which runs
# this file first as its prelude.
import sqlite3 as _sq3c                                   # noqa: E402
for _i in range(12):
    DO.feedback_set(U()["id"], "buy", "great", ref=f"c{_i}")
SENT.clear()
H.show_plans(ctx, U(), 500, None)
check("no license: the plan list shows no satisfaction line, even with 12 answers",
      "راضی‌اند" not in SENT[-1]["text"], SENT[-1]["text"][:90])
if PRO:
    check("… and neither does the mini app", AP.mini_plans(tu=(T, U()))["satisfaction"] is None)
DO.exec("DELETE FROM feedback WHERE tenant_id=? AND ref LIKE 'c%'", (OWNER,))
_pid_c = DO.q("SELECT id FROM plans WHERE tenant_id=? AND is_trial=0 LIMIT 1", (OWNER,), one=True)["id"]
_oc = DO.exec("INSERT INTO orders (tenant_id,user_id,plan_id,kind,amount,base_amount,status,created_at) "
              "VALUES (?,?,?,'new',1000,1000,'approved',datetime('now','-3 days'))", (OWNER, U()["id"], _pid_c))
SENT.clear()
RUN.send_feedback_polls()
check("no license: no poll goes out", not [m for m in SENT if "fb:" in m["kb"]])
_c2 = _sq3c.connect(os.environ["BOT_DB_PATH"])
check("… and the order is left unclaimed, not marked asked",
      _c2.execute("SELECT feedback_at FROM orders WHERE id=?", (_oc,)).fetchone()[0] is None)
_c2.execute("DELETE FROM orders WHERE id=?", (_oc,))
_c2.commit()
_c2.close()

if __name__ == "__main__":
    print(f"\n  {_ok} پاس · {_fail} شکست")
    sys.exit(1 if _fail else 0)
