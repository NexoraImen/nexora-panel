#!/usr/bin/env python3
"""
تست endpointهای مدیریت کاربران روی یک دیتابیس واقعی.

چرا وجود دارد:
    فیلترهای بخش کاربران SQL خام‌اند. یک شرط اشتباه، فهرست را بی‌صدا
    خالی یا اشتباه می‌کند و کسی متوجه نمی‌شود — چون خروجی همچنان
    «معتبر» به نظر می‌رسد.

اجرا:  python3 tests/test-admin-api.py
"""
import io
from datetime import datetime as _dt
import json
import os
import sys
import io as _io
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bot"))
sys.path.insert(0, str(ROOT / "backend"))

TMP = tempfile.mktemp(suffix=".db")
os.environ["BOT_DB_PATH"] = TMP
os.environ["NEXORA_ADMIN_PASSWORD"] = "testpw"

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


# ── ساخت دیتابیس نمونه ──
os.environ["BOT_DB_PATH"] = TMP
import db as botdb                                    # noqa: E402

botdb.DB_PATH = Path(TMP)
botdb.init_db()
tid = botdb.create_tenant("Test", bot_token="123:TEST", owner_tg_id=1)
D_ = botdb.TenantDB(tid)

# کاربر ۱: خریدار فعال، شماره دارد
u1 = D_.create_user(1001, "ali", "علی")
D_.exec("UPDATE users SET phone='989120000001', balance=50000, coins=12 "
        "WHERE id=?", (u1["id"],))
D_.exec("INSERT INTO plans (tenant_id,name,price,gb,days) VALUES (?,?,?,?,?)",
        (tid, "پلن", 100000, 30, 30))
pid = D_.plans()[0]["id"]
o1 = D_.create_order(u1["id"], pid, 100000, 100000)
D_.exec("UPDATE orders SET status='approved' WHERE id=?", (o1["id"],))
D_.exec("INSERT INTO subscriptions (tenant_id,user_id,plan_id,client_email,"
        "is_active,expires_at) VALUES (?,?,?,?,1,datetime('now','+10 day'))",
        (tid, u1["id"], pid, "e1"))

# کاربر ۲: اشتراکش تمام شده، بدون شماره
u2 = D_.create_user(1002, None, "رضا")
D_.exec("INSERT INTO subscriptions (tenant_id,user_id,plan_id,client_email,"
        "is_active,expires_at) VALUES (?,?,?,?,0,datetime('now','-3 day'))",
        (tid, u2["id"], pid, "e2"))

# کاربر ۳: هیچ‌وقت خرید نکرده، مسدود
u3 = D_.create_user(1003, "sara", "سارا")
D_.exec("UPDATE users SET is_blocked=1 WHERE id=?", (u3["id"],))

# کاربر ۴: با لینک دعوت آمده
D_.create_user(1004, None, "مهدی", referred_by=u1["id"])

import app                                            # noqa: E402

app.BOT_DB = Path(TMP)
# Pro code present? (docs/specs/2026-09-29-pro-split.md) The checks of a Pro
# area run only in the private tree; the Community tree counts them as skipped.
PRO = bool(getattr(app, "PRO_LOADED", False))
import re as _re                                        # noqa: E402  (was imported inside a Pro section)
import sqlite3 as _sq3                                  # noqa: E402  (was imported inside a Pro section)
_PRO_SKIPPED = []
# app.py plus the Pro files that run in its namespace, for every source check
# in this file. The list is read from backend/pro/__init__.py (NAMESPACE), not
# repeated here: copies went stale each time a file joined it, and the source
# checks of that file then failed (or, worse, passed on nothing).
_PRO_INIT = os.path.join(str(ROOT), "backend", "pro", "__init__.py")
_NS_FILES = (_re.findall(r'"(\w+\.py)"', _re.search(r"NAMESPACE = \(([^)]*)\)",
                        io.open(_PRO_INIT, encoding="utf-8").read()).group(1))
             if os.path.exists(_PRO_INIT) else [])
_APP_NS_SRC = io.open(os.path.join(str(ROOT), "backend", "app.py"), encoding="utf-8").read() + "".join(
    "\n" + io.open(os.path.join(str(ROOT), "backend", "pro", _f), encoding="utf-8").read()
    for _f in _NS_FILES)
_APSRC = _APP_NS_SRC
# رمز واقعی سرور را نمی‌خوانیم؛ برای تست جایگزینش می‌کنیم
PW = "testpw"
# رمز واقعی سرور را نمی‌خوانیم؛ برای تست جایگزینش می‌کنیم.
#
# `_stored_password` درزِ درست است: `check_auth` از
# `verify_password` می‌گذرد و آن از این می‌خواند. وصله‌زدن به
# `load_password` بعد از هَش‌شدنِ رمز دیگر اثری نداشت — و ۴۰۱
# گرفتنِ کلِ سوییت همان‌جا پیدایش کرد.
app.load_password = lambda: PW
# `_stored_password` را وصله نمی‌زنیم: آن‌وقت خودِ منطقِ رمز دور
# زده می‌شود و هیچ‌وقت سنجیده نمی‌شود. از درزِ واقعی می‌رویم —
# متغیر محیطی — و فایل رمز در پوشه‌ی موقت می‌نشیند، چون ارتقای
# خودکار روی اولین ورودِ موفق می‌نویسد و مسیر پیش‌فرض بیرون از
# مخزن است.
app.ADMIN_PASSWORD = PW
app.AUTH_PATH = Path(tempfile.mkdtemp(prefix="nx-auth-")) / "auth.json"

head("فیلترهای کاربران")


def users(**kw):
    kw.setdefault("x_admin_password", PW)
    return app.bot_users(**kw)


allu = users()
check("دیتابیس خوانده شد", allu.get("dbReady"), str(allu.get("error") or ""))
check("همه‌ی کاربران", allu["total"] == 4, str(allu.get("total")))
check("آمار هر فیلتر برمی‌گردد", "counts" in allu and allu["counts"]["all"] == 4,
      str(allu.get("counts", {}).get("all")))

cases = [
    ("active", 1, "اشتراک فعال"),
    ("expired", 1, "اشتراک تمام‌شده"),
    ("never", 2, "هیچ اشتراکی نداشته"),
    ("buyers", 1, "خرید موفق داشته"),
    ("blocked", 1, "مسدود"),
    ("withPhone", 1, "شماره دارد"),
    ("noPhone", 3, "بدون شماره"),
    ("withBalance", 1, "کیف پول پر"),
    ("withCoins", 1, "سکه دارد"),
    ("referred", 1, "با لینک دعوت"),
]
for key, want, label in cases:
    got = users(filter=key)["total"]
    check(label, got == want, f"{got} (انتظار {want})")

head("آمار هر کاربر")
row = next(u for u in users(filter="buyers")["users"] if u["tg_id"] == 1001)
check("تعداد سفارش موفق", row["ordersCount"] == 1, str(row["ordersCount"]))
check("مجموع خرید", row["spent"] == 100000, str(row["spent"]))
check("اشتراک فعال", row["activeSubs"] == 1, str(row["activeSubs"]))
check("شماره برمی‌گردد", row["phone"] == "989120000001", str(row["phone"]))

head("جستجو")
check("با نام", users(q="علی")["total"] == 1)
check("با یوزرنیم", users(q="sara")["total"] == 1)
check("با شناسه تلگرام", users(q="1002")["total"] == 1)
check("با شماره تماس", users(q="98912")["total"] == 1)
check("جستجوی بی‌نتیجه", users(q="هیچ‌کس")["total"] == 0)
check("جستجو با فیلتر ترکیب می‌شود",
      users(q="علی", filter="blocked")["total"] == 0)

head("مرتب‌سازی و صفحه‌بندی")
check("بیشترین خرید اول", users(sort="spent")["users"][0]["tg_id"] == 1001)
check("قدیمی‌ترین اول", users(sort="old")["users"][0]["tg_id"] == 1001)
p1 = users(limit=2, offset=0)
p2 = users(limit=2, offset=2)
check("صفحه‌بندی", len(p1["users"]) == 2 and len(p2["users"]) == 2)
check("صفحه‌ها هم‌پوشانی ندارند",
      not ({u["tg_id"] for u in p1["users"]} & {u["tg_id"] for u in p2["users"]}))
check("total مستقل از صفحه است", p2["total"] == 4, str(p2["total"]))

head("سفارش‌ها: نامِ پلن، و «review» در صفِ انتظار")
_ro = D_.create_order(u1["id"], pid, 100000, 100000)
_roid = _ro["id"] if isinstance(_ro, dict) else int(_ro)
D_.exec("UPDATE orders SET status='review' WHERE id=?", (_roid,))
_aw = app.bot_orders(status="awaiting", x_admin_password=PW)
_row = next((o for o in _aw.get("orders", []) if o["id"] == _roid), None)
check("سفارشِ review در زبانه‌ی «در انتظار» هست", _row is not None, str([o["id"] for o in _aw.get("orders", [])]))
check("نامِ پلن همراهِ سفارش می‌آید", (_row or {}).get("plan_name") == "پلن", str((_row or {}).get("plan_name")))

head("پیام به کاربر")
try:
    app.bot_message_user(1001, {"text": ""}, x_admin_password=PW)
    check("متن خالی رد می‌شود", False)
except app.HTTPException as e:
    check("متن خالی رد می‌شود", e.status_code == 400, e.detail)

try:
    app.bot_message_user(9999, {"text": "سلام"}, x_admin_password=PW)
    check("کاربر ناموجود رد می‌شود", False)
except app.HTTPException as e:
    check("کاربر ناموجود رد می‌شود", e.status_code == 404, e.detail)

try:
    app.bot_message_user(1001, {"text": "x" * 4000}, x_admin_password=PW)
    check("متن خیلی بلند رد می‌شود", False)
except app.HTTPException as e:
    check("متن خیلی بلند رد می‌شود", e.status_code == 400, e.detail)

try:
    os.unlink(TMP)
except OSError:
    pass

# ═══════════════════════════════════════════════════════════
head("شناسه‌ی نسخه به شل نمی‌رسد")

# نقطه‌ی پایانی بازگردانی، شناسه‌ی نسخه را از بدنه‌ی درخواست می‌گرفت
# و مستقیم داخل یک رشته‌ی شل می‌گذاشت:
#
#     cmd = f"setsid {cli} rollback {snap} --yes ..."
#     subprocess.Popen(["bash", "-lc", cmd])
#
# و اعتبارسنجی‌اش فهرستِ «این کاراکترها را رد کن» بود: / و ..
#
# این‌جا هم همان شکلِ اشتباه است. فهرستِ ممنوع هر چیزی را که در آن
# فکر نکرده‌ایم عبور می‌دهد؛ فهرستِ مجاز فقط چیزی را که می‌شناسیم.
# نام نسخه‌ها را خودِ اسکریپت با date می‌سازد و همیشه یک قالب دارد.

import shutil as _sh
import tempfile as _tf
from pathlib import Path as _P

SNAPS = _P(_tf.mkdtemp())
app.SNAP_DIR = SNAPS

LAUNCHED = []
app.subprocess_popen_calls = LAUNCHED


class _FakePopen:
    def __init__(self, argv, **kw):
        LAUNCHED.append((argv, kw))
        self.pid = 4242


import subprocess as _sp  # noqa: E402
_real_popen = _sp.Popen
_sp.Popen = _FakePopen

# نسخه‌ای با نام معتبر
(SNAPS / "20260101-120000").mkdir()
# و یکی با نامی که اگر به شل برسد دستور اجرا می‌کند
EVIL = "20260101-120000; touch /tmp/nexora-pwned"
(SNAPS / EVIL.replace("/", "_")).mkdir(exist_ok=True)


def _roll(snap_id):
    try:
        return app.run_rollback({"id": snap_id}, x_admin_password="testpw"), None
    except Exception as e:
        return None, e


ok_res, ok_err = _roll("20260101-120000")
check("نسخه‌ی معتبر اجرا می‌شود", ok_res and ok_res.get("ok") is True,
      str(ok_err)[:70] if ok_err else "")

bad_res, bad_err = _roll(EVIL.replace("/", "_"))
code = getattr(bad_err, "status_code", None)
check("نامی با کاراکتر شل رد می‌شود", bad_res is None and code == 400,
      f"status={code}")

for weird in ("20260101-120000 && ls", "$(whoami)", "a`id`b", "", "..",
              "../../etc", "20260101_120000"):
    r, e = _roll(weird)
    check(f"«{weird[:22] or 'خالی'}» رد می‌شود",
          r is None and getattr(e, "status_code", None) in (400, 404),
          f"status={getattr(e, 'status_code', None)}")

head("و اصلاً شلی در کار نیست")

check("دستور به‌صورت فهرست اجرا می‌شود",
      LAUNCHED and isinstance(LAUNCHED[0][0], list),
      str(type(LAUNCHED[0][0]).__name__) if LAUNCHED else "هیچ اجرایی نشد")
check("bash -lc استفاده نمی‌شود",
      LAUNCHED and "-lc" not in LAUNCHED[0][0],
      " ".join(str(x) for x in (LAUNCHED[0][0] if LAUNCHED else []))[:70])
check("shell=True نیست",
      LAUNCHED and not LAUNCHED[0][1].get("shell"),
      str(LAUNCHED[0][1].get("shell")) if LAUNCHED else "")
check("شناسه‌ی نسخه به‌عنوان یک آرگومان جدا می‌رود",
      LAUNCHED and "20260101-120000" in LAUNCHED[0][0],
      str(LAUNCHED[0][0])[:80] if LAUNCHED else "")
check("در نشست جدا اجرا می‌شود",
      LAUNCHED and LAUNCHED[0][1].get("start_new_session") is True,
      "تا بستن پنل وسط بازگردانی آن را نکشد")

_sp.Popen = _real_popen
_sh.rmtree(SNAPS, ignore_errors=True)



print(f"\n{D}{'─' * 46}{X}")
color = G if not _fail else R
# ═══════════════════════════════════════════════════════════
head("حدس‌زدنِ پشت‌سرهمِ رمز باید متوقف شود")

# کل سامانه پشت یک رمز است: پنل، اطلاعات مشتری‌ها، رمز x-ui، توکن
# ربات. هیچ چیزی جلوی حدس‌زدن را نمی‌گرفت — نه در /api/login و نه در
# مسیرهای مدیریتی که همان رمز را در هدر می‌گیرند.

import importlib.util as _iu  # noqa: E402
_spec = _iu.spec_from_file_location(
    "nxauth", os.path.join(str(ROOT), "backend", "app.py"))
AP = _iu.module_from_spec(_spec)
sys.modules["nxauth"] = AP
_spec.loader.exec_module(AP)
AP.AUTH_PATH = Path(tempfile.mkdtemp(prefix="nx-auth2-")) / "auth.json"


def _try(pw):
    """(کد وضعیت, متن) — بدون بالا آوردن استثنا."""
    try:
        AP.check_auth(pw)
        return 200, ""
    except Exception as e:
        return getattr(e, "status_code", 0), str(getattr(e, "detail", e))


AP.load_password = lambda: "testpw"
AP._stored_password = lambda: "testpw"
AP._auth_fails.clear()
code, _ = _try("testpw")
check("رمز درست پذیرفته می‌شود", code == 200, str(code))

code, _ = _try("غلط")
check("رمز غلط رد می‌شود", code == 401, str(code))

# تا آستانه پیش می‌رویم
AP._auth_fails.clear()
codes = [_try("غلط")[0] for _ in range(AP.AUTH_MAX_FAILS)]
check("تا پیش از آستانه هنوز ۴۰۱ است",
      codes[:AP.AUTH_MAX_FAILS - 1] == [401] * (AP.AUTH_MAX_FAILS - 1),
      f"{AP.AUTH_MAX_FAILS - 1} تلاش")

code, detail = _try("غلط")
check("بعد از آستانه قفل می‌شود", code == 429, str(code))
check("و می‌گوید چقدر باید صبر کرد", "دقیقه" in detail, detail[:60])

code, _ = _try("testpw")
check("رمز درست هم در زمان قفل رد می‌شود", code == 429,
      "وگرنه قفل فقط یک مزاحمت است، نه سد")

# قفل که باز شود، رمز درست کار می‌کند و پرونده بسته می‌شود
AP._auth_fails["?"]["until"] = 0
code, _ = _try("testpw")
check("بعد از پایان قفل، ورود درست باز می‌شود", code == 200, str(code))
check("و شمارش صفر می‌شود", "?" not in AP._auth_fails,
      "وگرنه یک ورود موفق هم آدم را نزدیک قفل بعدی نگه می‌دارد")

AP._auth_fails.clear()
_try("غلط")
check("نزدیک آستانه هشدار نمی‌دهد",
      "تلاش دیگر" not in _try("غلط")[1],
      "هشدار زودهنگام فقط به حدس‌زننده می‌گوید کجاست")
for _ in range(AP.AUTH_MAX_FAILS - 4):
    _try("غلط")
check("ولی در سه تلاش آخر هشدار می‌دهد",
      "تلاش دیگر" in _try("غلط")[1],
      "مدیرِ فراموش‌کار باید بفهمد دارد به کجا می‌رود")

# ورود از /api/login هم باید از همین نگهبان رد شود
AP._auth_fails.clear()
try:
    AP.login({"password": "testpw"})
    _login_ok = True
except Exception:
    _login_ok = False
check("ورود با رمز درست کار می‌کند", _login_ok)
for _ in range(AP.AUTH_MAX_FAILS):
    try:
        AP.login({"password": "غلط"})
    except Exception:
        pass
try:
    AP.login({"password": "testpw"})
    _locked = False
except Exception as e:
    _locked = getattr(e, "status_code", 0) == 429
check("ورود هم قفل می‌شود", _locked,
      "بستن یک در و باز گذاشتن آن یکی فایده‌ای ندارد")

# آی‌پی واقعی
AP._auth_fails.clear()


class _Req:
    def __init__(self, peer, fwd=None):
        self.client = type("c", (), {"host": peer})()
        self.headers = {"x-forwarded-for": fwd} if fwd else {}


check("پشت nginx آی‌پی واقعی خوانده می‌شود",
      AP._client_ip(_Req("127.0.0.1", "5.6.7.8")) == "5.6.7.8",
      "وگرنه همه در یک سطل می‌افتند و یک مهاجم مدیر را بیرون می‌اندازد")
check("ولی از اینترنت این هدر باور نمی‌شود",
      AP._client_ip(_Req("5.6.7.8", "1.1.1.1")) == "5.6.7.8",
      "وگرنه با یک هدر جعلی می‌شود از قفل رد شد")
check("هدر بی‌معنا نادیده گرفته می‌شود",
      AP._client_ip(_Req("127.0.0.1", "not-an-ip")) == "127.0.0.1")

# رمز فارسی — همان چیزی که نزدیک بود کل پنل را با ۵۰۰ ببندد
AP._auth_fails.clear()
AP.load_password = lambda: "رمزفارسی۱۲۳"
AP._stored_password = lambda: "رمزفارسی۱۲۳"
check("رمز غیرانگلیسی کار می‌کند", _try("رمزفارسی۱۲۳")[0] == 200,
      "compare_digest روی رشته‌ی غیراسکی TypeError می‌دهد — باید بایت داد")
check("و رمز فارسیِ غلط فقط ۴۰۱ است", _try("رمزدیگر")[0] == 401,
      "نه ۵۰۰ — خطای سرور یعنی پنل برای خودِ مدیر هم بسته می‌شود")
AP.load_password = lambda: "testpw"
AP._stored_password = lambda: "testpw"
AP._auth_fails.clear()

SRC = _APP_NS_SRC
check("مقایسه‌ی رمز زمان‌ثابت است", "compare_digest" in SRC,
      "مقایسه‌ی معمولی روی اولین بایت متفاوت برمی‌گردد")


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("ورود نماینده به پنل خودش")

    # پنل مدیر ۱۱۴ مسیر دارد و همه فرض می‌کنند «تو صاحب سیستمی». دادنشان
    # به نماینده یعنی هر کدام باید جداگانه محدود شود و کافی است یکی جا
    # بیفتد. پس سطح نماینده جداست و فهرست مجاز دارد، نه فهرست ممنوع.

    import sqlite3 as _sq3  # noqa: E402

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        # دیتابیس تست جدول مستاجرها را ندارد — کمینه‌اش را می‌سازیم
        _bd.execute("""CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            bot_token TEXT, bot_username TEXT, parent_id INTEGER,
            is_active INTEGER DEFAULT 1, credit INTEGER DEFAULT 0,
            credit_discount INTEGER DEFAULT 0, panel_pass TEXT)""")
        _cols = {r[1] for r in _bd.execute("PRAGMA table_info(tenants)")}
        for _c in ("portal_slug", "portal_pass", "portal_enabled"):
            if _c not in _cols:
                _bd.execute("ALTER TABLE tenants ADD COLUMN " + _c +
                            (" INTEGER DEFAULT 0" if _c == "portal_enabled" else " TEXT"))
        _bd.execute("DELETE FROM tenants WHERE name IN ('نماینده‌ی تست','دومی')")
        _bd.execute(
            "INSERT INTO tenants (name, is_active, portal_slug, portal_pass,"
            " portal_enabled, credit) VALUES (?,1,?,?,1,?)",
            ("نماینده‌ی تست", "hossein", "secret-pass-1", 500000))
        _rid = _bd.execute("SELECT id FROM tenants WHERE portal_slug='hossein'"
                           ).fetchone()[0]
        _bd.execute(
            "INSERT INTO tenants (name, is_active, portal_slug, portal_pass,"
            " portal_enabled, credit) VALUES (?,1,?,?,0,?)",
            ("دومی", "bastan", "secret-pass-2", 0))
        _bd.commit()
    finally:
        _bd.close()


    def _login(slug, pw):
        AP._auth_fails.clear()
        try:
            return 200, AP.portal_login(slug, {"password": pw}, None)
        except Exception as e:
            return getattr(e, "status_code", 0), str(getattr(e, "detail", e))


    _code, _res = _login("hossein", "secret-pass-1")
    check("ورود با رمز درست", _code == 200 and _res.get("token"), str(_code))
    _tok = _res.get("token") if _code == 200 else ""

    check("و نامش برمی‌گردد", _code == 200 and _res.get("name") == "نماینده‌ی تست")

    _code, _d = _login("hossein", "غلط")
    check("رمز غلط رد می‌شود", _code == 401, str(_code))

    _code, _d = _login("ناموجود", "secret-pass-1")
    check("نشانی ناموجود همان پیام را می‌دهد", _code == 401 and "نادرست" in _d,
          "وگرنه می‌شود فهمید کدام نشانی‌ها واقعی‌اند")

    _code, _d = _login("bastan", "secret-pass-2")
    check("نماینده‌ی خاموش اصلاً وارد نمی‌شود", _code == 401, str(_code))

    # نشست
    _me = AP.portal_tenant(_tok)
    check("نشست به مستاجر خودش می‌رسد", _me["portal_slug"] == "hossein")
    check("و اعتبارش را دارد", _me["credit"] == 500000)

    _pub = AP.portal_me(_me)
    check("مشخصات، توکن ربات را لو نمی‌دهد",
          "bot_token" not in _pub and "panel_pass" not in _pub,
          "نماینده هرگز نباید رمز پنل x-ui را ببیند")
    check("ولی اعتبار و تخفیفش را می‌بیند",
          _pub["credit"] == 500000 and "discount" in _pub)

    try:
        AP.portal_tenant("nxp_جعلی")
        _bad = False
    except Exception as e:
        _bad = getattr(e, "status_code", 0) == 401
    check("توکن جعلی رد می‌شود", _bad)

    # بستن نماینده باید همان لحظه اثر کند
    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET portal_enabled=0 WHERE id=?", (_rid,))
        _bd.commit()
    finally:
        _bd.close()
    try:
        AP.portal_tenant(_tok)
        _shut = False
    except Exception as e:
        _shut = getattr(e, "status_code", 0) == 403
    check("بستن نماینده نشستِ باز را همان لحظه می‌بندد", _shut,
          "نه اینکه تا انقضای نشست کار کند")
    check("و توکنش هم پاک می‌شود", _tok not in AP._PORTAL_SESSIONS)
else:
    _PRO_SKIPPED.append('ورود نماینده به پنل خودش')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("نماینده فقط کانفیگ‌های گروه خودش را می‌بیند")

    # همان چیزی که کل این کار برایش انجام شد: نماینده نباید کانفیگ
    # نماینده‌ی دیگر یا مشتری مستقیم مدیر را ببیند. تا امروز پنل x-ui
    # خودِ مدیر به او داده می‌شد، یعنی همه‌چیز را می‌دید.

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET portal_enabled=1, portal_group=? "
                    "WHERE portal_slug='hossein'", ("goroh-a",))
        _bd.execute("UPDATE tenants SET portal_enabled=1, portal_group=? "
                    "WHERE portal_slug='bastan'", ("goroh-b",))
        _bd.commit()
    except Exception:
        # ستون در دیتابیس تست نیست — می‌سازیمش
        _bd.execute("ALTER TABLE tenants ADD COLUMN portal_group TEXT")
        _bd.execute("UPDATE tenants SET portal_enabled=1, portal_group=? "
                    "WHERE portal_slug='hossein'", ("goroh-a",))
        _bd.execute("UPDATE tenants SET portal_enabled=1, portal_group=? "
                    "WHERE portal_slug='bastan'", ("goroh-b",))
        _bd.commit()
    finally:
        _bd.close()

    # دنیای x-ui ساختگی: سه گروه
    _ALL = [
        {"email": "a1", "group": "goroh-a", "totalGB": 50 * 1024 ** 3, "used": 0,
         "enable": True, "createdAt": "2026-07-01", "expiry": 1790000000000,
         "limitIp": 2, "subId": "s1"},
        {"email": "a2", "group": "goroh-a", "totalGB": 0, "used": 0,
         "enable": False, "createdAt": "2026-07-02", "expiry": 1790000000000,
         "limitIp": 0, "subId": "s2"},
        {"email": "b1", "group": "goroh-b", "totalGB": 50 * 1024 ** 3, "used": 0,
         "enable": True, "createdAt": "2026-07-03", "expiry": 1790000000000,
         "limitIp": 1, "subId": "s3"},
        {"email": "mine", "group": "مشتری مستقیم", "totalGB": 0, "used": 0,
         "enable": True, "createdAt": "2026-07-04", "expiry": 1790000000000,
         "limitIp": 0, "subId": "s4"},
    ]
    AP._read_xui_clients = lambda *a, **k: (_ALL, [], None)

    _t1 = AP._tenant_by_slug("hossein")
    _out = AP.portal_configs(_t1)
    _emails = sorted(c["email"] for c in _out["configs"])
    check("فقط کانفیگ‌های گروه خودش", _emails == ["a1", "a2"], "، ".join(_emails))
    check("کانفیگ نماینده‌ی دیگر نیست", "b1" not in _emails)
    check("مشتری مستقیم مدیر هم نیست", "mine" not in _emails,
          "این بدترین نشتی ممکن بود")
    check("شمارش فعال‌ها درست است", _out["active"] == 1, str(_out["active"]))

    _t2 = AP._tenant_by_slug("bastan")
    _out2 = AP.portal_configs(_t2)
    check("نماینده‌ی دوم هم فقط مال خودش را می‌بیند",
          [c["email"] for c in _out2["configs"]] == ["b1"])

    # نماینده‌ای که گروهش تعیین نشده نباید چیزی ببیند
    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET portal_group=NULL WHERE portal_slug='hossein'")
        _bd.commit()
    finally:
        _bd.close()
    try:
        AP.portal_configs(AP._tenant_by_slug("hossein"))
        _blank = False
    except Exception as e:
        _blank = getattr(e, "status_code", 0) == 409
    check("نماینده‌ی بی‌گروه هیچ چیز نمی‌بیند", _blank,
          "نه اینکه «همه» را ببیند — آن بدترین حالت پیش‌فرض است")

    # ── ولی پلنِ رباتش باید کار کند ──────────────────────────────────────
    #
    # برگه: docs/specs/2026-09-22-reseller-and-ui.md
    #
    # باگی که مالک گزارش کرد: «نماینده نمی‌تواند پلنی تعریف کند».
    # علت — `_portal_gb_policy` → `_portal_rates` → `_portal_group`، و
    # آن آخری بدونِ گروه ۴۰۹ می‌داد. پس ویرایشگرِ پلن نه باز می‌شد و نه
    # ذخیره — با پیامِ «با پشتیبانی تماس بگیرید».
    #
    # ولی پلنِ ربات یک ردیف در جدولِ `plans`ِ خودِ نماینده برای رباتِ
    # خودش است. گروه فقط برای *کفِ قیمت* لازم است.
    #
    # **رفتار سنجیده می‌شود نه متن**: جاروی شکستن نشان داد یک `return`
    # زودهنگام، دروازه‌ی متنی را سبز نگه می‌دارد.
    _ng = AP._tenant_by_slug("hossein")          # همین حالا بی‌گروه است

    try:
        _pl = AP.portal_bot_plans(t=_ng)
        _plans_open, _why_p = True, _pl.get("gbMode")
    except Exception as e:
        _plans_open, _why_p = False, f"{getattr(e, 'status_code', '')} {e}"
    check("نماینده‌ی بی‌گروه ویرایشگرِ پلن را باز می‌کند", _plans_open,
          str(_why_p)[:60])

    # جدولِ پلن‌ها در فیکسچر نیست. اسکیما را از خودِ `bot/db.py`
    # می‌گیریم، نه یک کپیِ دستی — کپی یعنی روزی این تست با واقعیت
    # فرق کند و همان را تایید کند.
    try:
        import sys as _sys2
        import os as _os2
        _botdir = _os2.path.join(
            _os2.path.dirname(_os2.path.dirname(_os2.path.abspath(__file__))), "bot")
        if _botdir not in _sys2.path:
            _sys2.path.insert(0, _botdir)
        import db as _BOTDB                                   # noqa: E402
        _bd = _sq3.connect(str(AP.BOT_DB))
        try:
            for _stmt in _BOTDB.SCHEMA.split(";"):
                if "CREATE TABLE IF NOT EXISTS plans" in _stmt:
                    _bd.execute(_stmt)
            _bd.commit()
        finally:
            _bd.close()
    except Exception as _e:
        print(f"    (جدولِ پلن ساخته نشد: {type(_e).__name__})")

    try:
        _sv = AP.portal_bot_plans_save(
            {"plans": [{"name": "تستِ بی‌گروه", "gb": 50, "days": 30,
                        "ip_limit": 2, "price": 150000, "is_active": True}]},
            t=_ng)
        _saved = bool(_sv.get("ok"))
        _why_s = str(_sv)
    except Exception as e:
        _saved, _why_s = False, f"{getattr(e, 'status_code', '')} {e}"
    check("و پلنش واقعاً ذخیره می‌شود", _saved, str(_why_s)[:60])

    # کف معلوم نیست — ولی باید *بگوید* چرا، نه صفر بدهد و نه بترکد
    try:
        _c = AP.portal_plan_cost({"rows": [{"gb": 50, "days": 30, "ip_limit": 2}]},
                                 t=_ng)
        _r0 = (_c.get("rows") or [{}])[0]
        _said = _r0.get("ready") is False and bool(_r0.get("why"))
        _why_c = str(_r0.get("why"))[:44]
    except Exception as e:
        _said, _why_c = False, f"{getattr(e, 'status_code', '')} {e}"
    check("کفِ بی‌گروه دلیل می‌گوید، نه صفر", _said, _why_c)

    # و گروه را دوباره سرِ جایش می‌گذاریم تا سنجه‌های بعدی خراب نشوند
    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        try:
            _bd.execute("DELETE FROM plans WHERE name='تستِ بی‌گروه'")
        except Exception:
            pass
        _bd.execute("UPDATE tenants SET portal_group='goroh-a' "
                    "WHERE portal_slug='hossein'")
        _bd.commit()
    finally:
        _bd.close()
else:
    _PRO_SKIPPED.append('نماینده فقط کانفیگ\u200cهای گروه خودش را می\u200cبیند')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("نوشتن نماینده در پنل — محافظ‌ها")

    # از این‌جا به بعد نماینده در x-ui می‌نویسد، و x-ui همان جایی است که
    # کانفیگ مشتری‌های واقعی زندگی می‌کند. سه قاعده که هیچ‌کدام قابل
    # مذاکره نیست، و این بخش دقیقاً همان‌ها را می‌سنجد.

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET portal_group='goroh-a', portal_enabled=1,"
                    " credit=300000 WHERE portal_slug='hossein'")
        for _pc in ("panel_url", "panel_user", "panel_pass", "panel_token"):
            try:
                _bd.execute(f"ALTER TABLE tenants ADD COLUMN {_pc} TEXT")
            except Exception:
                pass
        _bd.execute("UPDATE tenants SET panel_url='http://x', panel_user='u',"
                    " panel_pass='p' WHERE parent_id IS NULL")
        _bd.commit()
    finally:
        _bd.close()

    _T = AP._tenant_by_slug("hossein")


    class _FakeXUI:
        """پنل ساختگی — فقط برای دیدن اینکه چه چیزی به آن داده می‌شود."""
        calls = []

        def __init__(self, *a, **k):
            pass

        def find_client(self, inbound_id, email=None, client_uuid=None):
            if email in ("a1", "a2"):
                return {"id": "uuid-" + email, "inboundIds": [7], "email": email}
            if email == "b1":
                return {"id": "uuid-b1", "inboundIds": [9], "email": "b1"}
            return None

        def extend_subscription(self, ib, uuid, add_days=0, add_gb=None, email=None):
            _FakeXUI.calls.append(("extend", ib, uuid, add_days, add_gb, email))
            return {"expiry_ms": 1800000000000, "total_bytes": 0}

        def set_enabled(self, ib, uuid, enabled, email=None):
            _FakeXUI.calls.append(("enable", ib, uuid, enabled, email))
            return True


    AP._portal_xui = lambda t: (_FakeXUI(), Exception)

    # نرخ گروه
    _bc = AP._billing_conn()
    try:
        _bc.execute("DELETE FROM group_config WHERE group_key='goroh-a'")
        _bc.execute(
            "INSERT INTO group_config (group_key,label,billable,rates) VALUES (?,?,?,?)",
            ("goroh-a", "گروه الف", 1,
             json.dumps([{"gb": 50, "price": 100000, "perDevice": 20000}])))
        _bc.execute("DELETE FROM renewals")
        _bc.commit()
    finally:
        _bc.close()

    # ── قاعده ۲: کانفیگ نماینده‌ی دیگر دست‌نیافتنی است ──
    _FakeXUI.calls = []
    try:
        AP.portal_renew({"email": "b1", "months": 1}, _T)
        _blocked = False
    except Exception as e:
        _blocked = getattr(e, "status_code", 0) == 404
    check("تمدید کانفیگ نماینده‌ی دیگر رد می‌شود", _blocked,
          "ایمیل فرستادن هیچ چیزی را ثابت نمی‌کند")
    check("و اصلاً به پنل نمی‌رسد", not _FakeXUI.calls,
          "رد باید قبل از هر نوشتنی اتفاق بیفتد")

    try:
        AP.portal_toggle({"email": "b1", "enable": False}, _T)
        _blocked2 = False
    except Exception as e:
        _blocked2 = getattr(e, "status_code", 0) == 404
    check("خاموش‌کردن کانفیگ نماینده‌ی دیگر هم رد می‌شود", _blocked2)

    # ── تمدید درست ──
    _FakeXUI.calls = []
    _before = _sq3.connect(str(AP.BOT_DB))
    _c0 = _before.execute("SELECT credit FROM tenants WHERE portal_slug='hossein'"
                          ).fetchone()[0]
    _before.close()

    _res = AP.portal_renew({"email": "a1", "months": 2}, _T)
    check("تمدید انجام شد", _res["ok"] and _res["months"] == 2)
    check("و به پنل با uuid و اینباند درست رفت",
          _FakeXUI.calls and _FakeXUI.calls[0][1] == 7
          and _FakeXUI.calls[0][2] == "uuid-a1",
          str(_FakeXUI.calls[:1]))
    check("روزها دو برابر شد", _FakeXUI.calls[0][3] == 60, str(_FakeXUI.calls[0][3]))

    # ── قاعده ۳: اعتبار اتمی کم شد ──
    _after = _sq3.connect(str(AP.BOT_DB))
    _c1 = _after.execute("SELECT credit FROM tenants WHERE portal_slug='hossein'"
                         ).fetchone()[0]
    _after.close()
    # ۵۰ گیگ = ۱۰۰٬۰۰۰ پایه، ۲ دستگاه یعنی ۱ کاربر اضافه = ۲۰٬۰۰۰، دو ماه
    check("اعتبار به اندازه‌ی درست کم شد", _c0 - _c1 == 240000,
          f"{_c0} → {_c1} · انتظار ۲۴۰٬۰۰۰")
    check("و همان مبلغ گزارش شد", _res["charged"] == 240000, str(_res["charged"]))

    # ── و این تمام دلیل وجود این پنل: ثبت دقیق ──
    _bc = AP._billing_conn()
    try:
        _rn = [dict(r) for r in _bc.execute("SELECT * FROM renewals")]
    finally:
        _bc.close()
    check("تمدید دقیق ثبت شد", len(_rn) == 1 and _rn[0]["months"] == 2,
          "دیگر لازم نیست از فاصله‌ی ساخت تا انقضا حدس زده شود")
    check("به نام همان کانفیگ و گروه",
          _rn and _rn[0]["email"] == "a1" and _rn[0]["group_key"] == "goroh-a")

    # ── اعتبار که کم بیاید ──
    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET credit=1000 WHERE portal_slug='hossein'")
        _bd.commit()
    finally:
        _bd.close()
    _FakeXUI.calls = []
    try:
        AP.portal_renew({"email": "a1", "months": 1}, AP._tenant_by_slug("hossein"))
        _poor = False
    except Exception as e:
        _poor = getattr(e, "status_code", 0) == 402
    check("اعتبار ناکافی جلوی تمدید را می‌گیرد", _poor)
    check("و هیچ چیزی روی پنل عوض نمی‌شود", not _FakeXUI.calls,
          "کسر قبل از کار است، پس شکستش یعنی کار اصلاً شروع نمی‌شود")

    # ── ماه نامعتبر ──
    try:
        AP.portal_renew({"email": "a1", "months": 99}, _T)
        _bad = False
    except Exception as e:
        _bad = getattr(e, "status_code", 0) == 400
    check("تعداد ماه بی‌معنا رد می‌شود", _bad)

    APP_SRC = _APP_NS_SRC
    check("کسر اعتبار اتمی است",
          "WHERE id=? AND credit >= ?" in APP_SRC,
          "بخوان-بعد-کم‌کن بین آن دو جا برای درخواست دیگر باز می‌گذارد")
    check("و اگر پنل شکست خورد پول برمی‌گردد", "_portal_refund" in APP_SRC)
else:
    _PRO_SKIPPED.append('نوشتن نماینده در پنل — محافظ\u200cها')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("ساخت کانفیگ از پنل نماینده")

    # ساخت حساس‌تر از تمدید است: کانفیگ تازه باید *حتماً* در گروه خودش
    # بنشیند و نامش نباید با الگوی گروه دیگری بخواند — چون صفحه‌ی اشتراک
    # برند را از پیشوند ایمیل تشخیص می‌دهد.

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        try:
            _bd.execute("ALTER TABLE tenants ADD COLUMN default_inbound INTEGER")
        except Exception:
            pass
        _bd.execute("UPDATE tenants SET credit=1000000, default_inbound=7 "
                    "WHERE portal_slug='hossein'")
        _bd.commit()
    finally:
        _bd.close()
    _T2 = AP._tenant_by_slug("hossein")


    def _topup(amount=1000000):
        """اعتبار را برمی‌گرداند سر جایش.

        هر ساختی واقعاً پول کم می‌کند، پس چند بلوکِ پشت سر هم اعتبار را
        تمام می‌کنند و تستِ بعدی به جای چیزی که می‌سنجد، ۴۰۲ می‌گیرد.
        """
        _c = _sq3.connect(str(AP.BOT_DB))
        try:
            _c.execute("UPDATE tenants SET credit=? WHERE portal_slug='hossein'",
                       (amount,))
            _c.commit()
        finally:
            _c.close()


    class _MakeXUI(_FakeXUI):
        made = []

        def add_client(self, inbound_id, email, gb=0, days=0, ip_limit=0,
                       client_uuid=None, tg_id=None, sub_id=None, flow=None,
                       group=None, inbound_ids=None, start_on_use=False):
            _MakeXUI.made.append({"inbound": inbound_id, "email": email, "gb": gb,
                                  "days": days, "ip": ip_limit, "group": group,
                                  "start_on_use": start_on_use})
            return {"id": "new-uuid", "email": email, "subId": email}


    AP._portal_xui = lambda t: (_MakeXUI(), Exception)
    AP._read_xui_clients = lambda *a, **k: (_ALL, [], None)

    _MakeXUI.made = []
    _res = AP.portal_create({"gb": 50, "months": 2, "devices": 3}, _T2)
    check("کانفیگ ساخته شد", _res["ok"])

    _m = _MakeXUI.made[0] if _MakeXUI.made else {}
    check("گروهش از ردیف مستاجر آمد", _m.get("group") == "goroh-a",
          "نه از درخواست — این تنها چیزی است که تعیین می‌کند مال کیست")
    check("روی اینباند پیش‌فرض ساخته شد", _m.get("inbound") == 7, str(_m.get("inbound")))
    check("حجم و روز درست رفت", _m.get("gb") == 50 and _m.get("days") == 60,
          f"{_m.get('gb')} گیگ · {_m.get('days')} روز")
    check("تعداد کاربر هم", _m.get("ip") == 3)

    check("نامش با نشانی خودِ نماینده شروع می‌شود",
          str(_m.get("email", "")).startswith("hossein_"),
          "نماینده نام را نمی‌فرستد — می‌ساختیمش، وگرنه می‌توانست نام گروه دیگری بسازد")
    check("و تکراری نیست", _m.get("email") not in {c["email"] for c in _ALL})

    # قیمت: ۵۰ گیگ = ۱۰۰٬۰۰۰، دو کاربر اضافه × ۲۰٬۰۰۰، دو ماه
    check("مبلغ درست کسر شد", _res["charged"] == (100000 + 40000) * 2,
          str(_res["charged"]))
else:
    _PRO_SKIPPED.append('ساخت کانفیگ از پنل نماینده')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("ساخت کانفیگ · روز، نه فقط ماه")

    # نماینده می‌خواهد «۴۵ روز» بدهد، نه اینکه بین ۱ و ۲ و ۳ ماه گیر
    # کند. ولی مبلغ باید با همان تابعی حساب شود که کلِ حسابداری از آن
    # می‌خواند — وگرنه سطح تازه‌ای می‌شود که عدد خودش را می‌سازد.

    _topup()
    _MakeXUI.made = []
    _r45 = AP.portal_create({"gb": 50, "days": 45, "devices": 1}, _T2)
    _m45 = _MakeXUI.made[0] if _MakeXUI.made else {}
    check("روز همان‌طور که خواسته شده به پنل می‌رود",
          _m45.get("days") == 45, str(_m45.get("days")))
    check("و مبلغ با گردکردنِ خودِ حسابداری حساب می‌شود",
          _r45["months"] == 2 and _r45["charged"] == 100000 * 2,
          f"{_r45['months']} ماه · {_r45['charged']} تومان — ۴۵ روز یعنی ۲ ماه")

    _MakeXUI.made = []
    _r10 = AP.portal_create({"gb": 50, "days": 10, "devices": 1}, _T2)
    check("ده روز هم می‌شود، و یک ماه حساب می‌شود",
          _MakeXUI.made[0].get("days") == 10 and _r10["months"] == 1,
          f"{_r10['months']} ماه")

    # ماه هنوز پذیرفته می‌شود تا فراخوانی قدیمی نشکند
    _MakeXUI.made = []
    _rm = AP.portal_create({"gb": 50, "months": 3, "devices": 1}, _T2)
    check("«ماه» هنوز کار می‌کند و به روز تبدیل می‌شود",
          _MakeXUI.made[0].get("days") == 90 and _rm["months"] == 3,
          f"{_MakeXUI.made[0].get('days')} روز")

    # همان قاعده، دو جا — پس تستِ برابری می‌خواهد.
    #
    # پنل نماینده مبلغ را *پیش از* فرستادن نشان می‌دهد، پس مجبور است
    # خودش هم روز را به ماه تبدیل کند. اگر این دو از هم جدا بیفتند،
    # عددی که نماینده می‌بیند با عددی که از اعتبارش کم می‌شود فرق
    # می‌کند — و او تازه بعد از کسر می‌فهمد.
    _PSRC = io.open(os.path.join(str(ROOT), "frontend", "src", "pro", "portal",
                                 "index.jsx"), encoding="utf-8").read()
    check("پنل همان فرمول گردکردن را دارد",
          "const billMonths = Math.max(1, Math.round(days / 30));" in _PSRC,
          "اگر شکلش عوض شد، برابریِ زیر را دوباره بسنج")

    import math as _math                                        # noqa: E402
    _drift = [d for d in range(1, 367)
              # Math.round در جاوااسکریپت نیم را به بالا می‌برد
              if max(1, _math.floor(d / 30.0 + 0.5)) != AP._months_from_days(d)]
    check("و برای هر روزی از ۱ تا ۳۶۶ همان عدد را می‌دهد",
          not _drift, "اختلاف در: %s" % (_drift[:6] or "هیچ روزی"))


    for _bad, _why in (({"gb": 50, "days": 0, "devices": 1}, "روز صفر"),
                       ({"gb": 50, "days": 400, "devices": 1}, "روز ۴۰۰")):
        try:
            AP.portal_create(_bad, _T2)
            _ok_day = False
        except Exception as e:
            _ok_day = getattr(e, "status_code", 0) == 400
        check("%s رد می‌شود" % _why, _ok_day)
else:
    _PRO_SKIPPED.append('ساخت کانفیگ · روز، نه فقط ماه')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("ساخت کانفیگ · شمارش از اولین اتصال")

    # قرارداد خودِ ۳x-ui: expiryTime منفی یعنی «این‌قدر مدت، از لحظه‌ای
    # که وصل شد». پنل از قبل این حالت را «شروع‌نشده» می‌شناسد.
    #
    # چرا مهم است: مشتری امروز می‌خرد و شاید هفته‌ی دیگر وصل شود. بدون
    # این، آن هفته از سهمش کم می‌شود.

    _topup()
    _MakeXUI.made = []
    _ru = AP.portal_create({"gb": 50, "days": 30, "devices": 1,
                            "startOnFirstUse": True}, _T2)
    check("گزینه به پاسخ برمی‌گردد", _ru.get("startOnFirstUse") is True)
    check("و به پنل هم پاس داده می‌شود",
          _MakeXUI.made[0].get("start_on_use") is True,
          "وگرنه گزینه هست و هیچ کاری نمی‌کند")

    # و خودِ xui باید expiry را منفی بسازد
    import importlib.util as _iu3                            # noqa: E402
    _xspec = _iu3.spec_from_file_location(
        "_xui_days", os.path.join(str(ROOT), "bot", "xui.py"))
    _xsrc = io.open(os.path.join(str(ROOT), "bot", "xui.py"),
                    encoding="utf-8").read()
    check("add_client حالت شروع‌از-اتصال را می‌شناسد",
          "start_on_use" in _xsrc and "-int(days * 86400 * 1000)" in _xsrc,
          "expiry منفی، قرارداد خودِ ۳x-ui")

    _neg = _xsrc[_xsrc.find("def add_client("):]
    _neg = _neg[:_neg.find(chr(10) + "    def ", 10)]
    check("و بدون آن، انقضا از همین حالا حساب می‌شود",
          "timedelta(days=days)" in _neg,
          "حالت پیش‌فرض نباید عوض شده باشد")
else:
    _PRO_SKIPPED.append('ساخت کانفیگ · شمارش از اولین اتصال')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("ساخت کانفیگ · گروه باید واقعاً بنشیند")

    # گروه تنها چیزی است که می‌گوید این کانفیگ مالِ کدام نماینده است —
    # هم برای صورتحساب، هم برای اینکه خودش ببیندش. اگر ننشیند، کانفیگ
    # ساخته می‌شود، پولش کم می‌شود، و بعد در فهرست پیدا نمی‌شود. و
    # نسخه‌های قدیمی‌تر ۳x-ui اصلاً گروه ندارند و بی‌صدا دورش می‌ریزند.

    _topup()
    _MakeXUI.made = []
    _rg = AP.portal_create({"gb": 50, "days": 30, "devices": 1}, _T2)
    check("گروه به پنل فرستاده می‌شود", _MakeXUI.made[0].get("group") == "goroh-a",
          str(_MakeXUI.made[0].get("group")))
    check("و وقتی درست نشسته، هشداری نیست",
          "groupWarning" not in _rg,
          "هشدار فقط برای وقتی است که واقعاً جا نیفتاده")

    # حالا پنلی که گروه را دور می‌ریزد
    _saved_read = AP._read_xui_clients
    AP._read_xui_clients = lambda *a, **k: ([
        {"email": _MakeXUI.made[-1].get("email") if _MakeXUI.made else "x",
         "group": "بدون گروه", "used": 0, "enable": True,
         "totalGB": 0, "expiry": 0, "limitIp": 0}], [], None)
    _MakeXUI.made = []
    _rw = AP.portal_create({"gb": 50, "days": 30, "devices": 1}, _T2)
    AP._read_xui_clients = _saved_read
    check("ولی اگر گروه جا نیفتد، بی‌صدا نمی‌ماند",
          "groupWarning" in _rw and "بدون گروه" in _rw["groupWarning"],
          (_rw.get("groupWarning") or "(هیچ هشداری)")[:58])

    # ── حجمی که نرخ ندارد ──
    _MakeXUI.made = []
    try:
        AP.portal_create({"gb": 999, "months": 1, "devices": 1}, _T2)
        _bad = False
    except Exception as e:
        _bad = getattr(e, "status_code", 0) == 400
    check("حجمی که در نرخ‌ها نیست رد می‌شود", _bad,
          "وگرنه ردیفی ساخته می‌شود که سر ماه «بدون نرخ» می‌ماند")
    check("و چیزی روی پنل ساخته نمی‌شود", not _MakeXUI.made)

    # ── ورودی بی‌معنا ──
    for _bad_in, _why in ((({"gb": 50, "months": 0, "devices": 1}), "ماه صفر"),
                          (({"gb": 50, "months": 99, "devices": 1}), "ماه ۹۹"),
                          (({"gb": 50, "months": 1, "devices": 999}), "کاربر ۹۹۹")):
        # نامش `_ok` نیست: آن، شمارنده‌ی خودِ check است و بازنویسی‌اش
        # شمارش را از این‌جا به بعد صفر می‌کرد. عدد پایانِ این سوییت
        # مدتی کمتر از واقع گزارش می‌شد.
        try:
            AP.portal_create(_bad_in, _T2)
            _rejected = False
        except Exception as e:
            _rejected = getattr(e, "status_code", 0) == 400
        check(f"{_why} رد می‌شود", _rejected)

    # ── اعتبار ناکافی ──
    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET credit=5000 WHERE portal_slug='hossein'")
        _bd.commit()
    finally:
        _bd.close()
    _MakeXUI.made = []
    try:
        AP.portal_create({"gb": 50, "months": 1, "devices": 1},
                         AP._tenant_by_slug("hossein"))
        _poor = False
    except Exception as e:
        _poor = getattr(e, "status_code", 0) == 402
    check("اعتبار ناکافی جلوی ساخت را می‌گیرد", _poor)
    check("و کانفیگی ساخته نمی‌شود", not _MakeXUI.made,
          "کسر قبل از کار است")

    APP_SRC2 = _APP_NS_SRC
    # به «group=group» بند است، نه به پرانتزِ بعدش: افزودن یک آرگومانِ
    # تازه به همان فراخوانی نباید تستی را قرمز کند که درباره‌ی گروه است.
    check("گروه در ساخت از _portal_group می‌آید",
          "group=group" in APP_SRC2 and "group = _portal_group(t)" in APP_SRC2)
else:
    _PRO_SKIPPED.append('ساخت کانفیگ · گروه باید واقعاً بنشیند')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("ربات شخصی نماینده")

    # زیرساختش از قبل بود: run.py برای هر مستاجرِ فعالی که توکن دارد یک
    # نخ جدا می‌سازد. پس کارِ این‌جا فقط ثبت توکن است — و مهم‌ترین بخشش
    # این است که توکن غلط *قبل از ذخیره* رد شود، وگرنه رباتی بالا می‌آید
    # که هیچ‌وقت جواب نمی‌دهد و نماینده نمی‌فهمد چرا.

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        for _c in ("bot_token", "bot_username", "settings"):
            try:
                _bd.execute(f"ALTER TABLE tenants ADD COLUMN {_c} TEXT")
            except Exception:
                pass
        _bd.execute("UPDATE tenants SET bot_token=NULL, bot_username=NULL,"
                    " settings='{}' WHERE portal_slug='hossein'")
        _bd.execute("UPDATE tenants SET bot_token='999888777:BBHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw' "
                    "WHERE portal_slug='bastan'")
        _bd.commit()
    finally:
        _bd.close()

    _TB = AP._tenant_by_slug("hossein")

    # تلگرام ساختگی
    _asked = []


    def _fake_me(tok, timeout=10):
        _asked.append(tok)
        if tok.startswith("111222333:"):
            return True, "hossein_vpn_bot"
        return False, "تلگرام این توکن را نمی‌شناسد"


    AP._tg_get_me = _fake_me

    # ── شکل غلط، بدون اینکه اصلاً از تلگرام پرسیده شود ──
    _asked.clear()
    for _bad, _why in (("", "توکن خالی"), ("abc", "بدون دونقطه"),
                       ("1:2", "خیلی کوتاه")):
        try:
            AP.portal_bot_set({"token": _bad}, _TB)
            _rejected = False
        except Exception as e:
            _rejected = getattr(e, "status_code", 0) == 400
        check(f"{_why} رد می‌شود", _rejected)
    check("و برای هیچ‌کدام تلگرام صدا زده نشد", not _asked,
          "بررسی شکل قبل از شبکه است")

    # ── توکنی که مال حساب دیگری است ──
    try:
        AP.portal_bot_set({"token": "999888777:BBHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"}, _TB)
        _dup = False
    except Exception as e:
        _dup = getattr(e, "status_code", 0) == 409
    check("توکن تکراری رد می‌شود", _dup)
    _dup_msg = ""
    try:
        AP.portal_bot_set({"token": "999888777:BBHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"}, _TB)
    except Exception as e:
        _dup_msg = str(getattr(e, "detail", ""))
    check("و نام صاحبش را نمی‌گوید", "دومی" not in _dup_msg,
          "نماینده نباید بفهمد چه کسانی در سیستم هستند")

    # ── توکنی که تلگرام قبولش ندارد ──
    try:
        AP.portal_bot_set({"token": "222333444:CCHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"}, _TB)
        _rej = False
    except Exception as e:
        _rej = getattr(e, "status_code", 0) == 400
    check("توکنی که تلگرام نمی‌شناسد ذخیره نمی‌شود", _rej)

    _row = _sq3.connect(str(AP.BOT_DB))
    _tok_now = _row.execute("SELECT bot_token FROM tenants WHERE portal_slug='hossein'"
                            ).fetchone()[0]
    _row.close()
    check("و چیزی در دیتابیس ننشست", not _tok_now,
          "وگرنه رباتی بالا می‌آمد که هیچ‌وقت جواب نمی‌دهد")

    # ── توکن درست ──
    _res = AP.portal_bot_set({"token": "111222333:TEST_fake_token_for_unit_tests"}, _TB)
    check("توکن درست ثبت می‌شود", _res["ok"] and _res["username"] == "hossein_vpn_bot")

    _row = _sq3.connect(str(AP.BOT_DB))
    _r = _row.execute("SELECT bot_token, bot_username FROM tenants "
                      "WHERE portal_slug='hossein'").fetchone()
    _row.close()
    check("و در ردیف خودش نشست", _r[0] == "111222333:TEST_fake_token_for_unit_tests" and _r[1] == "hossein_vpn_bot")

    # ── توکن هرگز برنمی‌گردد ──
    _st = AP.portal_bot_get(AP._tenant_by_slug("hossein"))
    check("وضعیت می‌گوید ربات هست", _st["hasBot"] and _st["username"] == "hossein_vpn_bot")
    check("ولی توکن را برنمی‌گرداند",
          "token" not in _st and "111222333:TEST_fake_token_for_unit_tests" not in str(_st),
          "حتی به صاحب خودش هم دوباره نشان داده نمی‌شود")

    # ── برند: فهرست مجاز ──
    AP.portal_brand({"brand": "وی‌پی‌ان حسین", "support_username": "hsupport",
                     "panel_pass": "نفوذ", "credit": 99999999},
                    AP._tenant_by_slug("hossein"))
    _row = _sq3.connect(str(AP.BOT_DB))
    _s2 = _row.execute("SELECT settings, credit FROM tenants "
                       "WHERE portal_slug='hossein'").fetchone()
    _row.close()
    _js = json.loads(_s2[0] or "{}")
    check("برند ذخیره شد", _js.get("brand") == "وی‌پی‌ان حسین")
    check("پشتیبانی هم", _js.get("support_username") == "hsupport")
    check("ولی کلید خارج از فهرست مجاز ننشست", "panel_pass" not in _js,
          "settings کلیدهای حساس هم دارد — باز گذاشتنش یعنی نماینده چیزی "
          "را عوض کند که مال او نیست")

    # ── جداکردن ──
    AP.portal_bot_del(AP._tenant_by_slug("hossein"))
    _row = _sq3.connect(str(AP.BOT_DB))
    _gone = _row.execute("SELECT bot_token FROM tenants WHERE portal_slug='hossein'"
                         ).fetchone()[0]
    _row.close()
    check("جداکردن توکن را پاک می‌کند", not _gone)
else:
    _PRO_SKIPPED.append('ربات شخصی نماینده')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("نماینده باید لینک اشتراک مشتری‌اش را ببیند")

    # نماینده لینک را فقط موقع ساخت یک بار می‌دید. مشتری‌ای که لینکش را
    # گم می‌کرد، نماینده هم نمی‌توانست کمکش کند.

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        # یک مستاجر ریشه‌ی واقعی لازم است: نماینده‌ها باید parent داشته
        # باشند وگرنه جست‌وجوی «ریشه» به خودشان می‌رسد.
        _bd.execute("DELETE FROM tenants WHERE name='مالک'")
        _bd.execute("INSERT INTO tenants (name, parent_id, is_active, settings) "
                    "VALUES ('مالک', NULL, 1, ?)",
                    (json.dumps({"sub_base_url": "https://sub.example.ir/sub"}),))
        _root = _bd.execute("SELECT id FROM tenants WHERE name='مالک'").fetchone()[0]
        _bd.execute("UPDATE tenants SET parent_id=? WHERE name<>'مالک'", (_root,))
        _bd.execute("UPDATE tenants SET portal_group='goroh-a', portal_enabled=1,"
                    " settings='{}' WHERE portal_slug='hossein'")
        _bd.commit()
    finally:
        _bd.close()

    AP._read_xui_clients = lambda *a, **k: (_ALL, [], None)
    _cfgs = AP.portal_configs(AP._tenant_by_slug("hossein"))
    _first = _cfgs["configs"][0] if _cfgs["configs"] else {}
    check("هر ردیف لینک اشتراک دارد", bool(_first.get("subUrl")),
          str(_first.get("subUrl")))
    check("و لینک با شناسه‌ی همان کانفیگ ساخته شده",
          str(_first.get("subUrl", "")).endswith(_first.get("subId")
                                                 or _first.get("email", "")),
          _first.get("subUrl", ""))
    check("پایه از تنظیمات مالک آمد",
          "sub.example.ir" in str(_first.get("subUrl")),
          "نماینده تنظیم خودش را نداشت، پس تنظیم مالک")
else:
    _PRO_SKIPPED.append('نماینده باید لینک اشتراک مشتری\u200cاش را ببیند')


# ═══════════════════════════════════════════════════════════
head("پلن‌های مالک با پلن‌های نماینده قاطی نمی‌شوند")

# تا وقتی یک ربات بود فرقی نمی‌کرد. از وقتی نماینده ربات خودش را
# دارد، پلن‌هایش در فهرست پلن‌های مالک ظاهر می‌شدند — و چون ذخیره
# به مستاجر اصلی محدود است، حذفشان از آن فهرست «ok» می‌داد و هیچ
# کاری نمی‌کرد.

APSRC = _APP_NS_SRC
check("خواندن پلن‌ها به مستاجر محدود است",
      "SELECT * FROM plans WHERE tenant_id=? ORDER BY sort_order" in APSRC,
      "نوشتنش از اول محدود بود، خواندنش نه")
check("و نوشتنش هم هنوز محدود است",
      "WHERE id=? AND tenant_id=?" in APSRC
      and "DELETE FROM plans WHERE tenant_id=?" in APSRC)


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("راه‌اندازی نماینده از پنل مدیر")

    # چیزی که مدیر واقعاً دید: نماینده را ساخت، رمز گرفت، لینک را باز
    # کرد، و پنل گفت «نشانی یا رمز نادرست است». رمز درست بود.
    #
    # دو علت داشت، هر دو در همین مسیر:
    #   • group بی‌صدا دور ریخته می‌شد
    #   • هیچ دکمه‌ای portal_enabled را یک نمی‌کرد، و ورود برای پنلِ
    #     بسته همان پیام رمز غلط را می‌دهد

    AP.load_password = lambda: "testpw"
    AP._stored_password = lambda: "testpw"
    AP._auth_fails.clear()

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("DELETE FROM tenants WHERE name='تازه‌وارد'")
        # نماینده همیشه فرزندِ ریشه است — همان کاری که tenant_create
        # می‌کند. بدون والد، در حسابداری «مالک» شمرده می‌شود و فهرست
        # نماینده‌ها هم درست نشانش نمی‌دهد.
        _proot = _bd.execute("SELECT id FROM tenants WHERE parent_id IS NULL "
                             "ORDER BY id LIMIT 1").fetchone()
        _bd.execute("INSERT INTO tenants (name, parent_id, is_active, credit) "
                    "VALUES (?,?,1,?)",
                    ("تازه‌وارد", _proot[0] if _proot else None, 0))
        _nid = _bd.execute("SELECT id FROM tenants WHERE name='تازه‌وارد'"
                           ).fetchone()[0]
        _bd.commit()
    finally:
        _bd.close()

    # همان چیزی که دکمه‌ی «ثبت» می‌فرستد
    _r1 = AP.tenant_portal_set(_nid, {"slug": "tazevared", "group": "goroh-a"},
                               x_admin_password="testpw")
    check("نشانی و گروه ثبت شد", _r1["ok"])

    _row = _sq3.connect(str(AP.BOT_DB))
    _g = _row.execute("SELECT portal_group FROM tenants WHERE id=?",
                      (_nid,)).fetchone()[0]
    _row.close()
    check("گروه واقعاً نشست", _g == "goroh-a",
          "قبلاً بی‌صدا دور ریخته می‌شد و نماینده هیچ کانفیگی نمی‌دید")

    # هنوز رمز ندارد، پس نباید باز شده باشد
    check("بدون رمز پنل باز نمی‌شود", not _r1.get("opened"),
          "باز کردنِ پنلی که رمز ندارد یعنی در باز بی‌قفل")

    _bad = None
    try:
        AP.portal_login("tazevared", {"password": "hich"}, None)
    except Exception as e:
        _bad = getattr(e, "status_code", 0)
    check("و ورود هم ممکن نیست", _bad == 401)

    # همان چیزی که دکمه‌ی «رمز تازه بساز» می‌فرستد
    _r2 = AP.tenant_portal_set(_nid, {"password": "rooz-e-khoob-1"},
                               x_admin_password="testpw")
    check("رمز ثبت شد", _r2["ok"])
    check("و حالا پنل خودش باز شد", _r2.get("opened") is True,
          "این همان چیزی بود که جا افتاده بود")

    # و حالا باید بتواند وارد شود — همان کاری که مدیر کرد
    AP._auth_fails.clear()
    _in = AP.portal_login("tazevared", {"password": "rooz-e-khoob-1"}, None)
    check("ورود با رمزی که پنل ساخت کار می‌کند", bool(_in.get("token")),
          "دقیقاً همان چیزی که کار نمی‌کرد")

    # بستنِ صریح نباید با ویرایش بعدی خودبه‌خود باز شود
    AP.tenant_portal_set(_nid, {"enabled": False}, x_admin_password="testpw")
    _r3 = AP.tenant_portal_set(_nid, {"slug": "tazevared2"}, x_admin_password="testpw")
    check("بستنِ صریح با ویرایش بعدی باز نمی‌شود", not _r3.get("opened"),
          "وگرنه بستنِ یک نماینده هیچ معنایی ندارد")

    _row = _sq3.connect(str(AP.BOT_DB))
    _e = _row.execute("SELECT COALESCE(portal_enabled,0) FROM tenants WHERE id=?",
                      (_nid,)).fetchone()[0]
    _row.close()
    check("و بسته می‌ماند", str(_e) in ("0", "", "None"), str(_e))

    # فهرست باید بگوید رمز دارد یا نه، بدون اینکه رمز را بدهد
    _lst = AP.tenant_portal_list(x_admin_password="testpw")
    _me = [x for x in _lst["tenants"] if x["id"] == _nid]
    check("فهرست می‌گوید رمز دارد", _me and _me[0]["hasPass"] is True)
    check("ولی خودِ رمز را نمی‌دهد", "rooz-e-khoob-1" not in str(_lst),
          "پنل فقط باید بداند هست یا نه")
else:
    _PRO_SKIPPED.append('راه\u200cاندازی نماینده از پنل مدیر')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("شارژ اعتبار نماینده")

    # بدون این، مدل پیش‌پرداخت فقط روی کاغذ کار می‌کرد: هیچ راهی برای
    # شارژکردن نبود جز دست‌زدن به دیتابیس.

    AP.load_password = lambda: "testpw"
    AP._stored_password = lambda: "testpw"
    AP._auth_fails.clear()
    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET credit=0 WHERE portal_slug='hossein'")
        _bd.execute("DELETE FROM credit_tx")
        _bd.commit()
    except Exception:
        pass
    finally:
        _bd.close()

    _cid = AP._tenant_by_slug("hossein")["id"]

    _c = AP.tenant_credit(_cid, {"amount": 500000, "note": "شارژ اول"},
                          x_admin_password="testpw")
    check("شارژ انجام شد", _c["credit"] == 500000, str(_c["credit"]))

    _c = AP.tenant_credit(_cid, {"amount": -200000}, x_admin_password="testpw")
    check("برداشت هم کار می‌کند", _c["credit"] == 300000, str(_c["credit"]))

    try:
        AP.tenant_credit(_cid, {"amount": -999999}, x_admin_password="testpw")
        _neg = False
    except Exception as e:
        _neg = getattr(e, "status_code", 0) == 400
    check("اعتبار منفی نمی‌شود", _neg,
          "منفی در این سیستم معنای دیگری دارد: بدون سقف")

    try:
        AP.tenant_credit(_cid, {"amount": 0}, x_admin_password="testpw")
        _z = False
    except Exception as e:
        _z = getattr(e, "status_code", 0) == 400
    check("مبلغ صفر رد می‌شود", _z)

    _c = AP.tenant_credit(_cid, {"unlimited": True}, x_admin_password="testpw")
    check("بدون سقف کردن کار می‌کند", _c["credit"] == -1 and _c["mode"] == "بدهکاری")

    _c = AP.tenant_credit(_cid, {"amount": 100000}, x_admin_password="testpw")
    check("و برگشت به پیش‌پرداخت از صفر شروع می‌شود", _c["credit"] == 100000,
          f"{_c['credit']} — نه از منفی یک")

    # دفتر
    _lg = AP.tenant_credit_log(_cid, x_admin_password="testpw")
    # چهار تغییرِ واقعی: شارژ، برداشت، بدون‌سقف، شارژ دوباره.
    # آن دو تای ردشده عمداً ثبت نمی‌شوند — دفتر باید کاری را نشان بدهد
    # که انجام شده، نه تلاشی را که نشده.
    check("هر تغییرِ انجام‌شده در دفتر ثبت شده", len(_lg["rows"]) == 4,
          f"{len(_lg['rows'])} سطر")
    check("و تلاش‌های ردشده ثبت نشده‌اند",
          not any(r["amount"] == -999999 for r in _lg["rows"]))
    check("و مانده‌ی بعد از هر تغییر هم هست",
          _lg["rows"][0]["balance"] == 100000, str(_lg["rows"][0]["balance"]))
    check("و یادداشتش", "شارژ اول" in str(_lg["rows"]),
          "عددِ credit به‌تنهایی تاریخچه ندارد")

    # خرجِ خودِ نماینده هم باید در همین دفتر بیفتد
    _spent = AP._portal_charge(AP._tenant_by_slug("hossein"), 30000, "تست خرج")
    check("کسر از سمت نماینده هم ثبت می‌شود", _spent[0])
    _lg2 = AP.tenant_credit_log(_cid, x_admin_password="testpw")
    check("و در دفتر با علامت منفی می‌نشیند",
          any(r["amount"] == -30000 for r in _lg2["rows"]),
          "وگرنه معلوم نیست اعتبار کجا رفت")
else:
    _PRO_SKIPPED.append('شارژ اعتبار نماینده')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("پلن‌های ربات نماینده")

    # رباتش بالا می‌آمد ولی مغازه‌اش خالی بود: plans به مستاجر محدود است
    # و نماینده هیچ راهی برای ساختن پلن نداشت.

    _T3 = AP._tenant_by_slug("hossein")
    _other = AP._tenant_by_slug("bastan")

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("""CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER,
            name TEXT, description TEXT, gb INTEGER, days INTEGER,
            ip_limit INTEGER, price INTEGER, inbound_id INTEGER,
            is_active INTEGER, is_trial INTEGER, sort_order INTEGER)""")
        _bd.execute("DELETE FROM plans")
        _bd.execute("INSERT INTO plans (tenant_id,name,gb,days,price,is_active,"
                    "sort_order) VALUES (?,?,?,?,?,1,0)",
                    (_other["id"], "مال نماینده‌ی دیگر", 10, 30, 50000))
        _oid = _bd.execute("SELECT id FROM plans").fetchone()[0]
        _bd.commit()
    finally:
        _bd.close()

    _r = AP.portal_bot_plans_save(
        {"plans": [{"name": "ماهانه ۵۰", "gb": 50, "days": 30,
                    "ip_limit": 2, "price": 250000}]}, _T3)
    check("پلن ساخته شد", _r["ok"] and _r["count"] == 1)

    _mine = AP.portal_bot_plans(_T3)
    check("و فقط مال خودش را می‌بیند",
          len(_mine["plans"]) == 1 and _mine["plans"][0]["name"] == "ماهانه ۵۰")

    _theirs = AP.portal_bot_plans(_other)
    check("پلن نماینده‌ی دیگر دست‌نخورده ماند",
          len(_theirs["plans"]) == 1
          and _theirs["plans"][0]["name"] == "مال نماینده‌ی دیگر",
          "ذخیره‌ی یکی نباید پلن‌های دیگری را پاک کند")

    # فرستادن شناسه‌ی پلن نماینده‌ی دیگر نباید کاری بکند
    #
    # حجم باید یکی از پله‌های مجاز باشد، وگرنه قاعده‌ی تازه‌ی «حجم از
    # نرخِ مالک می‌آید» جلوترش را می‌گیرد و این تست دیگر آن چیزی را که
    # می‌خواهد نمی‌سنجد (جداییِ مستاجرها). قیمت هم به همان دلیل بالای
    # کف است — قیمتِ زیرِ کف حالا خودش رد می‌شود.
    AP.portal_bot_plans_save(
        {"plans": [{"id": _oid, "name": "دزدیده", "gb": 50, "days": 1,
                    "price": 300000}]}, _T3)
    _theirs2 = AP.portal_bot_plans(_other)
    check("شناسه‌ی پلن دیگری هم کاری نمی‌کند",
          _theirs2["plans"] and _theirs2["plans"][0]["name"] == "مال نماینده‌ی دیگر",
          "به‌روزرسانی با WHERE id=? AND tenant_id=? محدود است")

    try:
        AP.portal_bot_plans_save({"plans": [{"name": "", "gb": 1}]}, _T3)
        _noname = False
    except Exception as e:
        _noname = getattr(e, "status_code", 0) == 400
    check("پلن بی‌نام رد می‌شود", _noname)

    _r2 = AP.portal_bot_plans_save({"plans": []}, _T3)
    check("فهرست خالی همه‌ی پلن‌های خودش را پاک می‌کند", _r2["count"] == 0)
    check("ولی باز هم مال دیگری سر جایش است",
          len(AP.portal_bot_plans(_other)["plans"]) == 1)

    APS = _APP_NS_SRC
    # تستِ رایگان: مالک تصمیم گرفت «مجاز و رایگان»، ولی فقط زیرِ سقفِ تستِ
    # خودش (سنجه‌ی کامل در `test-portal-dashboard.py`). این فیکسچر تستی
    # برای مالک ندارد، پس تستِ نماینده باید رد شود — رفتار، نه متن.
    try:
        AP.portal_bot_plans_save({"plans": [{"name": "تست", "gb": 1, "days": 1,
                                             "ip_limit": 1, "is_trial": True}]}, _T3)
        _trial_code = 200
    except Exception as e:
        _trial_code = getattr(e, "status_code", 500)
    check("تستِ نماینده بدونِ تستِ مالک ذخیره نمی‌شود", _trial_code == 400,
          "کانفیگ رایگان روی سرور مالک ساخته می‌شود — سقفش را مالک می‌گذارد")
else:
    _PRO_SKIPPED.append('پلن\u200cهای ربات نماینده')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("لینک اشتراک باید پیدا شود، حتی وقتی کسی تنظیمش نکرده")

    # این همان چیزی بود که نماینده می‌دید: کانفیگ ساخته می‌شد ولی هیچ
    # لینکی برای تحویل نبود، و هیچ‌جا نمی‌گفت چرا. علتش این بود که همه‌چیز
    # به sub_base_url دستی وابسته بود.

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET settings='{}'")
        _bd.commit()
    finally:
        _bd.close()
    AP._SUB_BASE_CACHE.clear()


    class _SubXUI:
        def panel_sub_base(self):
            return "https://sub.panel.ir:2096/sub"


    AP._portal_xui = lambda t: (_SubXUI(), Exception)
    _tt = AP._tenant_by_slug("hossein")
    check("وقتی کسی تنظیم نکرده، از خود پنل خوانده می‌شود",
          AP._sub_base(_tt) == "https://sub.panel.ir:2096/sub",
          "پنل خودش این را می‌داند — ربات از روز اول همین کار را می‌کرد")

    AP._SUB_BASE_CACHE.clear()
    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET settings=? WHERE parent_id IS NULL",
                    (json.dumps({"sub_base_url": "https://owner.ir/sub"}),))
        _bd.commit()
    finally:
        _bd.close()
    check("ولی تنظیم مالک بر آن مقدم است",
          AP._sub_base(AP._tenant_by_slug("hossein")) == "https://owner.ir/sub")

    AP._SUB_BASE_CACHE.clear()
    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET settings=? WHERE portal_slug='hossein'",
                    (json.dumps({"sub_base_url": "https://mine.ir/sub/"}),))
        _bd.commit()
    finally:
        _bd.close()
    check("و تنظیم خودِ نماینده بر همه",
          AP._sub_base(AP._tenant_by_slug("hossein")) == "https://mine.ir/sub",
          "اسلش آخر هم برداشته می‌شود تا لینک دوتا اسلش نگیرد")
else:
    _PRO_SKIPPED.append('لینک اشتراک باید پیدا شود، حتی وقتی کسی تنظیمش نکرده')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("آمار نماینده باید کاربردی باشد، نه شمارش خشک")

    # «۹۴ کانفیگ» به نماینده نمی‌گوید کدام مشتری دارد از دست می‌رود.
    # چیزی که می‌شود رویش کاری کرد این است: چند تا دارند تمام می‌شوند،
    # چند تا حجمشان پر شده.

    import time as _tm  # noqa: E402
    _now = int(_tm.time() * 1000)
    _STAT = [
        # فعال، جای زیادی مانده
        {"email": "s1", "group": "goroh-a", "totalGB": 100 * 1024**3,
         "used": 10 * 1024**3, "enable": True, "createdAt": "2026-01-01",
         "expiry": _now + 40 * 86400000, "limitIp": 2, "subId": "s1"},
        # تا سه روز دیگر تمام می‌شود
        {"email": "s2", "group": "goroh-a", "totalGB": 50 * 1024**3,
         "used": 5 * 1024**3, "enable": True, "createdAt": "2026-01-01",
         "expiry": _now + 3 * 86400000, "limitIp": 1, "subId": "s2"},
        # منقضی
        {"email": "s3", "group": "goroh-a", "totalGB": 50 * 1024**3,
         "used": 5 * 1024**3, "enable": False, "createdAt": "2026-01-01",
         "expiry": _now - 5 * 86400000, "limitIp": 1, "subId": "s3"},
        # حجمش تمام شده
        {"email": "s4", "group": "goroh-a", "totalGB": 10 * 1024**3,
         "used": 10 * 1024**3, "enable": True, "createdAt": "2026-01-01",
         "expiry": _now + 20 * 86400000, "limitIp": 1, "subId": "s4"},
        # نزدیک سقف
        {"email": "s5", "group": "goroh-a", "totalGB": 10 * 1024**3,
         "used": 9 * 1024**3, "enable": True, "createdAt": "2026-01-01",
         "expiry": _now + 20 * 86400000, "limitIp": 1, "subId": "s5"},
        # نامحدود و بدون انقضا
        {"email": "s6", "group": "goroh-a", "totalGB": 0, "used": 1 * 1024**3,
         "enable": True, "createdAt": "2026-01-01", "expiry": 0,
         "limitIp": 0, "subId": "s6"},
        # مالِ نماینده‌ی دیگر — نباید شمرده شود
        {"email": "x1", "group": "goroh-b", "totalGB": 0, "used": 99 * 1024**3,
         "enable": True, "createdAt": "2026-01-01", "expiry": 0,
         "limitIp": 0, "subId": "x1"},
    ]
    AP._read_xui_clients = lambda *a, **k: (_STAT, [], None)

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET portal_group='goroh-a', portal_enabled=1 "
                    "WHERE portal_slug='hossein'")
        _bd.commit()
    finally:
        _bd.close()

    _st = AP.portal_stats(t=AP._tenant_by_slug("hossein"))
    check("فقط کاربران خودش شمرده می‌شوند", _st["total"] == 6, str(_st["total"]))
    check("رو به اتمام درست است", _st["expiringSoon"] == 1, str(_st["expiringSoon"]))
    check("منقضی‌ها جدا شمرده می‌شوند", _st["expired"] == 1, str(_st["expired"]))
    check("حجم‌تمام‌شده جدا از نزدیک‌به‌سقف",
          _st["overQuota"] == 1 and _st["nearQuota"] == 1,
          f"تمام‌شده {_st['overQuota']} · نزدیک {_st['nearQuota']}")
    check("نامحدودها در سقف حساب نمی‌شوند", _st["unlimitedQuota"] == 1,
          "درصدی از بی‌نهایت معنا ندارد")
    # «فعال» یعنی روشن و منقضی‌نشده. کانفیگی که حجمش تمام شده هنوز
    # فعال است و جداگانه در overQuota شمرده می‌شود — دو چیز متفاوت‌اند
    # و نماینده باید هر دو را ببیند.
    check("فعال یعنی روشن و منقضی‌نشده", _st["active"] == 5, str(_st["active"]))
    check("و غیرفعال‌ها بقیه‌اند", _st["inactive"] == 1, str(_st["inactive"]))
    check("و «نیاز به پیگیری» جمعشان است",
          _st["needsAttention"] == 1 + 1 + 1,
          f"{_st['needsAttention']} — رو به اتمام + منقضی + حجم تمام")
    check("مصرف نماینده‌ی دیگر داخلش نیست", _st["usedGB"] < 99,
          f"{_st['usedGB']} GB")
else:
    _PRO_SKIPPED.append('آمار نماینده باید کاربردی باشد، نه شمارش خشک')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("رسید و تایید سفارش در پنل نماینده")

    # مشتریِ نماینده از رباتِ او سفارش می‌دهد و رسید می‌فرستد. تا امروز
    # تنها جای تاییدش گروه تلگرام بود؛ نماینده‌ای که گروه نداشت، سفارشش
    # برای همیشه در انتظار می‌ماند.

    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER,
            user_id INTEGER, plan_id INTEGER, kind TEXT, amount INTEGER,
            base_amount INTEGER, coins_used INTEGER, paid_from TEXT,
            status TEXT, receipt_type TEXT, receipt_file TEXT,
            receipt_text TEXT, admin_note TEXT, sub_id INTEGER,
            created_at TEXT)""")
        _bd.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER,
            tg_id INTEGER, first_name TEXT, username TEXT)""")
        _bd.execute("DELETE FROM orders")
        _bd.execute("DELETE FROM users WHERE tg_id IN (7001, 7002)")

        _h = AP._tenant_by_slug("hossein")
        _b = AP._tenant_by_slug("bastan")
        _bd.execute("INSERT INTO users (tenant_id,tg_id,first_name) VALUES (?,?,?)",
                    (_h["id"], 7001, "مشتریِ حسین"))
        _u1 = _bd.execute("SELECT id FROM users WHERE tg_id=7001").fetchone()[0]
        _bd.execute("INSERT INTO users (tenant_id,tg_id,first_name) VALUES (?,?,?)",
                    (_b["id"], 7002, "مشتریِ دیگری"))
        _u2 = _bd.execute("SELECT id FROM users WHERE tg_id=7002").fetchone()[0]

        _bd.execute("INSERT INTO orders (tenant_id,user_id,kind,amount,base_amount,"
                    "paid_from,status,receipt_file,created_at) "
                    "VALUES (?,?,'new',250000,250000,'card','awaiting','file-1',"
                    "'2026-09-15')", (_h["id"], _u1))
        _mine = _bd.execute("SELECT id FROM orders WHERE user_id=?", (_u1,)).fetchone()[0]
        _bd.execute("INSERT INTO orders (tenant_id,user_id,kind,amount,base_amount,"
                    "paid_from,status,created_at) "
                    "VALUES (?,?,'new',99000,99000,'card','awaiting','2026-09-15')",
                    (_b["id"], _u2))
        _theirs = _bd.execute("SELECT id FROM orders WHERE user_id=?", (_u2,)).fetchone()[0]
        _bd.commit()
    finally:
        _bd.close()

    _T4 = AP._tenant_by_slug("hossein")

    _lst = AP.portal_orders(t=_T4)
    _ids = [o["id"] for o in _lst["orders"]]
    check("فقط سفارش‌های مشتری‌های خودش", _ids == [_mine], str(_ids))
    check("سفارش نماینده‌ی دیگر نیست", _theirs not in _ids,
          "همان محدودسازی‌ای که همه‌جای این پنل هست")
    check("و می‌گوید رسید دارد", _lst["orders"][0]["hasReceipt"] is True)
    check("مبلغ و نام مشتری می‌آید",
          _lst["orders"][0]["amount"] == 250000
          and _lst["orders"][0]["customer"] == "مشتریِ حسین")

    # دست‌درازی به سفارش دیگری
    for _fn, _nm in ((AP.portal_order_approve, "تایید"),
                     (AP.portal_receipt, "دیدن رسید")):
        try:
            _fn(_theirs, t=_T4)
            _blocked = False
        except Exception as e:
            _blocked = getattr(e, "status_code", 0) == 404
        check(f"{_nm} سفارش نماینده‌ی دیگر رد می‌شود", _blocked,
              "پیامش همان «پیدا نشد» است — وگرنه می‌شود شناسه‌ها را کشف کرد")

    try:
        AP.portal_order_reject(_theirs, {"reason": "چون"}, t=_T4)
        _rb = False
    except Exception as e:
        _rb = getattr(e, "status_code", 0) == 404
    check("رد سفارش نماینده‌ی دیگر هم", _rb)

    # بدون ربات نمی‌شود تایید کرد
    _bd = _sq3.connect(str(AP.BOT_DB))
    try:
        _bd.execute("UPDATE tenants SET bot_token=NULL WHERE portal_slug='hossein'")
        _bd.commit()
    finally:
        _bd.close()
    try:
        AP.portal_order_approve(_mine, t=AP._tenant_by_slug("hossein"))
        _nobot = False
    except Exception as e:
        _nobot = getattr(e, "status_code", 0) == 409
    check("بدون ربات، تایید ممکن نیست", _nobot,
          "تاییدِ بی‌خبر یعنی مشتری پولش را داده و هیچ‌چیز نمی‌بیند")

    # دلیل رد اجباری است
    try:
        AP.portal_order_reject(_mine, {"reason": "  "}, t=AP._tenant_by_slug("hossein"))
        _nore = False
    except Exception as e:
        _nore = getattr(e, "status_code", 0) == 400
    check("رد بدون دلیل ممکن نیست", _nore, "مشتری همان دلیل را می‌بیند")

    APO = _APP_NS_SRC
    check("تایید همان کد ربات را صدا می‌زند",
          "h.approve_order(ctx, oid" in APO,
          "مسیر پول دو پیاده‌سازی برنمی‌دارد")
    check("رد هم همین‌طور", "h.do_reject(ctx, oid" in APO)
    check("و «همین حالا در حال پردازش» را هم می‌فهمد",
          "ORDER_BUSY" in APO,
          "وگرنه نماینده دوباره تایید می‌زند، درست وقتی که نباید")
    check("رسید با توکن ربات پاس داده می‌شود نه آدرسش",
          "api.telegram.org/file/bot" in APO and "Response(content=blob" in APO,
          "آن آدرس توکن ربات را در خودش دارد")
else:
    _PRO_SKIPPED.append('رسید و تایید سفارش در پنل نماینده')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("پرچمِ باز/بسته یک جواب دارد، نه سه تا")

    # سه جا portal_enabled را می‌خواندند و هر کدام جور دیگری:
    #
    #   ورود        CAST(... AS INTEGER)=1   — فقط عددِ یک
    #   بررسی نشست  not in ("0","","None")   — هرچه ناشناخته، باز
    #   فهرست مدیر  همان فهرست ممنوع
    #
    # روی ۰ و ۱ هر سه یکی‌اند. روی هر مقدار دیگری ورود می‌بست و نشستِ
    # باز، باز می‌ماند — یعنی بستنِ یک نماینده، نشستِ فعلی‌اش را نمی‌بست،
    # درست برعکسِ چیزی که بالای همان کد نوشته شده بود.

    _VALUES = [1, 0, "1", "0", None, 2, "true", "yes", "", "01", 1.0,
               True, False, " 1 ", "-1", "1.0"]

    # ورود و بررسی نشست باید روی *هر* مقداری یک جواب بدهند. این را با
    # خودِ دو مسیر می‌سنجیم، نه با بازنویسی شرطشان در تست — تستی که
    # قاعده را دوباره پیاده کند، فقط بازنویسی خودش را می‌آزماید.
    _drift = []
    _fb = _sq3.connect(str(AP.BOT_DB))
    try:
        for _v in _VALUES:
            _fb.execute("UPDATE tenants SET portal_enabled=? "
                        "WHERE portal_slug='hossein'", (_v,))
            _fb.commit()
            # مقدارِ *ذخیره‌شده* را می‌خوانیم، نه آنچه فرستادیم: ستون
            # affinity عددی دارد و SQLite رشته‌ی '1.0' را همان موقع به ۱
            # تبدیل می‌کند. مقایسه با مقدار خام یعنی سنجیدن چیزی که
            # هیچ‌وقت در دیتابیس ننشسته.
            _stored = _fb.execute("SELECT portal_enabled FROM tenants "
                                  "WHERE portal_slug='hossein'").fetchone()[0]
            _login_ok = AP._tenant_by_slug("hossein") is not None
            _sess_ok = AP._portal_open(_stored)
            if _login_ok != _sess_ok:
                _drift.append(f"{_v!r}→{_stored!r}: ورود {_login_ok} · "
                              f"نشست {_sess_ok}")
        # برگرداندن به حالت باز، تا بقیه‌ی تست‌ها به هم نریزند
        _fb.execute("UPDATE tenants SET portal_enabled=1 "
                    "WHERE portal_slug='hossein'")
        _fb.commit()
    finally:
        _fb.close()

    check("ورود و بررسی نشست یک جواب می‌دهند", not _drift,
          "، ".join(_drift) if _drift
          else f"{len(_VALUES)} مقدار سنجیده شد")

    check("فقط یک، باز است",
          AP._portal_open(1) and AP._portal_open("1") and AP._portal_open(True))
    check("صفر و خالی و None بسته‌اند",
          not any(AP._portal_open(v) for v in (0, "0", "", None, False)))
    check("مقدار ناشناخته باز نیست — فهرست مجاز، نه ممنوع",
          not any(AP._portal_open(v) for v in (2, "true", "yes", "-1")),
          "همین‌ها بودند که نشست را باز نگه می‌داشتند")

    _src_ap = _APP_NS_SRC
    check("هیچ‌جا فهرست ممنوعِ قدیمی نمانده",
          'in ("0", "", "None")' not in _src_ap,
          "هر سه جا باید از _portal_open بگیرند")
    check("و شرط در SQL دوباره پیاده نشده",
          "CAST(COALESCE(portal_enabled,0) AS INTEGER)" not in _src_ap,
          "دو پیاده‌سازی از یک قاعده، دیر یا زود از هم جدا می‌شوند")
    check("بررسی نشست از همان تابع می‌گیرد",
          "not _portal_open(\n            t.get(\"portal_enabled\"))" in _src_ap
          or "_portal_open(t.get(\"portal_enabled\"))" in _src_ap)
else:
    _PRO_SKIPPED.append('پرچمِ باز/بسته یک جواب دارد، نه سه تا')


# ═══════════════════════════════════════════════════════════
if PRO:        # sales partners are Pro (backend/pro/affiliates.py)
    head("بدهی به همکاران نباید بدهی نماینده‌ها را هم بشمارد")

    # صفحه‌ی همکاری «مجموع بدهی به همکاران» را نشان می‌دهد و دفتر کل
    # همان عدد را از `_affiliate_money_out` می‌گیرد. دفتر کل فقط
    # مستاجرهای ریشه را می‌شمارد — چون پورسانتِ همکارِ یک نماینده،
    # هزینه‌ی همان نماینده است. صفحه هیچ شرطی نداشت و هر دو را با هم
    # جمع می‌کرد، پس دو صفحه به یک سؤال دو جواب می‌دادند.

    # تست بازگردانی، بالاتر در همین فایل، دیتابیس را با یک نسخه‌ی
    # پشتیبانِ کوچک جایگزین می‌کند و جدول‌های همکاری در آن نیستند.
    # init_db همان اسکیمای واقعی را دوباره می‌سازد (IF NOT EXISTS)، پس
    # تست به جای کپی‌کردن تعریفِ جدول‌ها، خودِ منبع را صدا می‌زند.
    botdb.init_db()

    # مستاجرهای خودمان را می‌سازیم و به آنچه تست‌های قبلی گذاشته‌اند
    # تکیه نمی‌کنیم: در این دیتابیس مستاجر ۱ خودش فرزندِ ۳ است.
    _ab = _sq3.connect(str(AP.BOT_DB))
    _ab.executescript("""
    INSERT OR REPLACE INTO tenants (id, name, parent_id)
      VALUES (9000, 'مالک تستی', NULL);
    INSERT OR REPLACE INTO tenants (id, name, parent_id)
      VALUES (9001, 'نماینده‌ی تستی', 9000);

    INSERT INTO affiliates (id, tenant_id, name, code, percent, active)
      VALUES (9101, 9000, 'همکار خودم', 'MINE', 10, 1);
    INSERT INTO affiliate_commissions
      (tenant_id, affiliate_id, order_id, order_amount, percent, commission, status)
      VALUES (9000, 9101, 91011, 3000000, 10, 300000, 'pending');
    INSERT INTO affiliate_payouts (tenant_id, affiliate_id, amount)
      VALUES (9000, 9101, 100000);

    INSERT INTO affiliates (id, tenant_id, name, code, percent, active)
      VALUES (9102, 9001, 'همکار نماینده', 'THEIRS', 10, 1);
    INSERT INTO affiliate_commissions
      (tenant_id, affiliate_id, order_id, order_amount, percent, commission, status)
      VALUES (9001, 9102, 91021, 5000000, 10, 500000, 'pending');
    """)
    _ab.commit()
    _ab.close()

    _aff = app.bot_affiliates(x_admin_password=PW)
    _rows = {r["id"]: r for r in _aff.get("affiliates", [])}

    check("هر دو همکار در فهرست می‌آیند", 9101 in _rows and 9102 in _rows,
          "همکارِ نماینده نباید ناپدید شود — پنل نماینده اصلا این بخش را ندارد")
    check("همکار خودم «مالِ خودم» علامت می‌خورد",
          _rows.get(9101, {}).get("isOwn") is True)
    check("همکار نماینده نه", _rows.get(9102, {}).get("isOwn") is False,
          "وگرنه از همکارِ خودتان قابل تشخیص نیست")
    check("و نامِ نماینده‌اش می‌آید",
          _rows.get(9102, {}).get("tenantName") == "نماینده‌ی تستی",
          _rows.get(9102, {}).get("tenantName") or "—")

    check("مانده‌ی همکار خودم درست است",
          _rows.get(9101, {}).get("balance") == 200_000,
          str(_rows.get(9101, {}).get("balance")))

    # همان چیزی که دفتر کل می‌گوید. The ledger is accounting (Pro); without it
    # there is no second number to agree with.
else:
    _PRO_SKIPPED.append('بدهی به همکاران نباید بدهی نماینده\u200cها را هم بشمارد')
if PRO:
    _lpaid, _lowed = AP._affiliate_money_out()
    check("«مجموع بدهی» با دفتر کل یکی است",
          _aff.get("totalOwed") == _lowed,
          f"صفحه {_aff.get('totalOwed')} · دفتر کل {_lowed}")
    check("و این برابری با «هر دو صفر» بی‌معنی نشده",
          _lowed >= 200_000, f"دفتر کل: {_lowed}")
else:
    _PRO_SKIPPED.append("affiliates: the ledger agrees with the page")
if PRO:        # sales partners are Pro (backend/pro/affiliates.py)
    check("و بدهیِ نماینده‌ها جدا شمرده می‌شود",
          _aff.get("resellerOwed") == 500_000,
          str(_aff.get("resellerOwed")))
    _all_bal = sum(r["balance"] for r in _aff.get("affiliates", []))
    check("تفکیک کامل است و چیزی گم نمی‌شود",
          _aff.get("totalOwed", 0) + _aff.get("resellerOwed", 0) == _all_bal
          and _aff.get("totalOwed") != _all_bal,
          f"کل {_all_bal} = خودم {_aff.get('totalOwed')} + "
          f"نماینده {_aff.get('resellerOwed')}")

    # و همان شرط، نه یک بازنویسیِ موازی
    _apsrc = _APP_NS_SRC
    _blk = _apsrc[_apsrc.index("def bot_affiliates("):]
    _blk = _blk[:_blk.index("@app.post")]
    check("شرط ریشه‌بودن همان عبارت دفتر کل است",
          "parent_id IS NULL" in _blk,
          "دو پیاده‌سازی از یک قاعده، دیر یا زود از هم جدا می‌شوند")
else:
    _PRO_SKIPPED.append('affiliates: owed to partners vs resellers')


# ═══════════════════════════════════════════════════════════
head("اینباندِ هر نماینده مالِ خودش است")

# این دستور `WHERE` نداشت:
#
#     UPDATE tenants SET inbound_mode=?, inbound_ids=?
#
# یعنی هر بار که مالک اینباندهای خودش را ذخیره می‌کرد، همان تنظیم
# بی‌صدا روی تک‌تک نماینده‌ها هم می‌نشست و انتخابِ خودشان پاک می‌شد.
# و خواندنش همیشه از مستاجر ریشه بود، پس تنظیمِ نماینده نه دیده
# می‌شد و نه قابل تغییر.

botdb.init_db()
_rb = _sq3.connect(str(AP.BOT_DB))
_rb.executescript("""
INSERT OR REPLACE INTO tenants (id, name, parent_id, inbound_mode, inbound_ids)
  VALUES (7000, 'مالک تستی', NULL, 'all', NULL);
INSERT OR REPLACE INTO tenants (id, name, parent_id, inbound_mode, inbound_ids)
  VALUES (7001, 'نماینده الف', 7000, 'all', NULL);
INSERT OR REPLACE INTO tenants (id, name, parent_id, inbound_mode, inbound_ids)
  VALUES (7002, 'نماینده ب', 7000, 'all', NULL);
""")
_rb.commit()
_rb.close()


def _inb(tid):
    c = _sq3.connect(str(AP.BOT_DB))
    try:
        r = c.execute("SELECT inbound_mode, inbound_ids FROM tenants "
                      "WHERE id=?", (tid,)).fetchone()
        return (r[0], r[1]) if r else (None, None)
    finally:
        c.close()


app.bot_inbounds_set({"mode": "custom", "ids": [41], "tenant": 7001},
                     x_admin_password=PW)
check("تنظیم نماینده‌ی الف نوشته شد", _inb(7001) == ("custom", "[41]"),
      str(_inb(7001)))
check("نماینده‌ی ب دست نخورد", _inb(7002)[0] == "all",
      f"{_inb(7002)} — قبلا این هم عوض می‌شد")
check("و مالک هم دست نخورد", _inb(7000)[0] == "all", str(_inb(7000)))

# و حالا مالک تنظیم خودش را ذخیره می‌کند.
#
# «ریشه» همان چیزی است که خودِ کد برمی‌دارد — کوچک‌ترین شناسه‌ای که
# parent_id ندارد. این دیتابیسِ تست چند ریشه دارد چون بخش‌های قبلی
# ساخته‌اند؛ روی نصبِ واقعی فقط یکی هست.
_rc = _sq3.connect(str(AP.BOT_DB))
_root_id = _rc.execute("SELECT id FROM tenants WHERE parent_id IS NULL "
                       "ORDER BY id LIMIT 1").fetchone()[0]
_rc.close()
_res = app.bot_inbounds_set({"mode": "custom", "ids": [28]},
                            x_admin_password=PW)
check("بدون tenant، تنظیم روی مستاجر ریشه می‌نشیند",
      _res.get("tenant") == _root_id, f"{_res.get('tenant')} در برابر {_root_id}")
_root_now = _inb(_root_id)
check("و واقعا نوشته شد",
      _root_now[0] == "custom" and "28" in (_root_now[1] or ""),
      str(_root_now))
check("و انتخابِ نماینده‌ی الف را پاک نمی‌کند",
      _inb(7001) == ("custom", "[41]"), str(_inb(7001)))
check("و نماینده‌ی ب را هم نه", _inb(7002)[0] == "all", str(_inb(7002)))

_bad = None
try:
    app.bot_inbounds_set({"mode": "all", "tenant": 999999},
                         x_admin_password=PW)
except Exception as e:      # noqa: BLE001
    _bad = getattr(e, "status_code", 0)
check("نماینده‌ی ناموجود ۴۰۴ می‌گیرد", _bad == 404, str(_bad))

_srcmod = _APP_NS_SRC
_wblk = _srcmod[_srcmod.index("def bot_inbounds_set("):]
_wblk = _wblk[:_wblk.index("\n@app.")]
_wcode = "\n".join(l for l in _wblk.split("\n")
                   if not l.strip().startswith("#"))
check("دستور نوشتن بدون WHERE نمانده",
      "UPDATE tenants SET inbound_mode=?, inbound_ids=? WHERE" in _wcode,
      "بدون WHERE روی همه‌ی مستاجرها می‌نویسد")

# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("ساخت نماینده — که تا امروز اصلا ممکن نبود")

    _made = app.tenant_create(
        {"name": "نماینده تازه", "slug": "TazeH-1", "password": "abcd1234efgh",
         "group": "g-taze", "credit": 0}, x_admin_password=PW)
    check("ساخته شد", _made.get("ok") and _made.get("id"), str(_made)[:70])

    _row = _sq3.connect(str(AP.BOT_DB)).execute(
        "SELECT name, parent_id, portal_slug, portal_pass, portal_group, "
        "portal_enabled, credit FROM tenants WHERE id=?",
        (_made["id"],)).fetchone()
    check("فرزندِ مستاجر ریشه است", _row[1] is not None,
          "وگرنه در حسابداری «مالک» شمرده می‌شود و درآمدش با شما قاطی می‌شود")
    check("نشانی پاک‌سازی و کوچک شد", _row[2] == "tazeh-1", _row[2])
    check("رمزش ثبت شد", _row[3] == "abcd1234efgh")
    check("گروهش ثبت شد", _row[4] == "g-taze")
    check("و پنلش بسته ساخته می‌شود", _row[5] == 0,
          "تا گروه و رمز ثبت نشده، بازکردنش فقط صفحه‌ی ورودِ بی‌فایده است")
    check("پیش‌پرداخت بودنش ثبت شد", _row[6] == 0, str(_row[6]))

    # نشانی تکراری یعنی دو نماینده به یک لینک می‌رسند
    _dup = None
    try:
        app.tenant_create({"name": "دیگری", "slug": "tazeh-1",
                           "password": "abcd1234efgh"}, x_admin_password=PW)
    except Exception as e:      # noqa: BLE001
        _dup = getattr(e, "status_code", 0)
    check("نشانی تکراری رد می‌شود", _dup == 400, str(_dup))

    for _bad_payload, _why in (
            ({"slug": "x1", "password": "abcd1234efgh"}, "بدون نام"),
            ({"name": "ب", "password": "abcd1234efgh"}, "بدون نشانی"),
            ({"name": "ب", "slug": "x2", "password": "123"}, "رمز کوتاه")):
        _e = None
        try:
            app.tenant_create(_bad_payload, x_admin_password=PW)
        except Exception as ex:      # noqa: BLE001
            _e = getattr(ex, "status_code", 0)
        check(f"{_why} رد می‌شود", _e == 400, str(_e))

    # و نماینده‌ی تازه واقعا در فهرست پنل نمایندگی می‌آید
    _lst = app.tenant_portal_list(x_admin_password=PW)
    check("در فهرست پنل نمایندگی دیده می‌شود",
          any(t["id"] == _made["id"] for t in _lst.get("tenants", [])),
          "وگرنه ساخته شده ولی هیچ‌جا نیست")
else:
    _PRO_SKIPPED.append('ساخت نماینده — که تا امروز اصلا ممکن نبود')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("آمار فروشِ پنل نماینده")

    # نماینده ربات خودش را دارد ولی هیچ عددی از فروشش نمی‌دید. دو
    # قاعده‌ای که این‌جا هم باید اجرا شوند:
    #
    #   • تست رایگان خرید نیست — خودش یک سفارشِ approved با مبلغ صفر
    #     می‌سازد و اگر کنار گذاشته نشود، «تعداد فروش» را باد می‌کند.
    #   • «فروش» با «درآمد» یکی نیست — خرید از کیف پول فروش هست ولی پول
    #     تازه‌ای نیامده؛ آن پول موقع شارژ رسیده.

    botdb.init_db()
    _sb = _sq3.connect(str(AP.BOT_DB))
    _sb.executescript("""
    INSERT OR REPLACE INTO tenants (id, name, parent_id) VALUES (7100, 'نماینده فروش', 1);
    INSERT OR REPLACE INTO tenants (id, name, parent_id) VALUES (7101, 'نماینده دیگر', 1);

    INSERT OR REPLACE INTO plans (id, tenant_id, name, price, gb, days, is_trial)
      VALUES (7110, 7100, 'پلن', 200000, 30, 30, 0);
    INSERT OR REPLACE INTO plans (id, tenant_id, name, price, gb, days, is_trial)
      VALUES (7111, 7100, 'تست', 0, 1, 1, 1);

    INSERT OR REPLACE INTO users (id, tenant_id, tg_id) VALUES (7120, 7100, 71);
    INSERT OR REPLACE INTO users (id, tenant_id, tg_id) VALUES (7121, 7101, 72);
    """)
    # دو فروش کارتی، یک فروش کیف‌پولی، یک تست، یک ردشده، یک در انتظار
    for _amt, _plan, _st, _pf in (
            (200000, 7110, 'approved', 'card'),
            (300000, 7110, 'approved', 'card'),
            (150000, 7110, 'approved', 'wallet'),
            (0,      7111, 'approved', 'card'),
            (500000, 7110, 'rejected', 'card'),
            (400000, 7110, 'awaiting', 'card')):
        _sb.execute("INSERT INTO orders (tenant_id,user_id,plan_id,amount,"
                    "base_amount,status,paid_from,created_at) "
                    "VALUES (7100,7120,?,?,?,?,?,datetime('now'))",
                    (_plan, _amt, _amt, _st, _pf))
    # و یک فروش برای نماینده‌ی دیگر که نباید قاطی شود
    _sb.execute("INSERT INTO orders (tenant_id,user_id,plan_id,amount,base_amount,"
                "status,paid_from,created_at) "
                "VALUES (7101,7121,NULL,900000,900000,'approved','card',datetime('now'))")
    _sb.commit()
    _sb.close()

    _first = _dt.now().replace(day=1).strftime("%Y-%m-%d")
    _sales = AP._portal_sales(7100, _first)

    check("ربات دارد", _sales["hasBot"] is True)
    check("تعداد فروش، تست را نمی‌شمارد", _sales["orders"] == 3,
          f"{_sales['orders']} — دو کارتی و یک کیف‌پولی، نه تستِ رایگان")
    check("مبلغ فروش هم همین‌طور", _sales["sold"] == 650000,
          f"{_sales['sold']} — ۲۰۰ + ۳۰۰ + ۱۵۰ هزار")
    check("«دریافتی» فقط کارت را می‌شمارد", _sales["received"] == 500000,
          f"{_sales['received']} — خرید کیف‌پولی پول تازه نیست")
    check("سفارشِ ردشده در فروش نیست", _sales["sold"] != 1150000)
    check("در انتظار بررسی جدا شمرده می‌شود", _sales["pending"] == 1,
          str(_sales["pending"]))
    check("فروش این ماه هم درست است", _sales["monthSold"] == 650000,
          str(_sales["monthSold"]))

    _other = AP._portal_sales(7101, _first)
    check("فروش نماینده‌ها با هم قاطی نمی‌شود", _other["sold"] == 900000,
          f"{_other['sold']} — فقط مالِ خودش")
    check("و برعکسش هم", _sales["sold"] == 650000)

    _none = AP._portal_sales(999999, _first)
    check("نماینده‌ی بدون ربات صفر می‌گیرد، نه خطا",
          _none["hasBot"] is False and _none["orders"] == 0, str(_none)[:60])
else:
    _PRO_SKIPPED.append('آمار فروشِ پنل نماینده')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("پنل نماینده و ربات باید یک اینباند را انتخاب کنند")

    # انتخابِ اینباندِ هر نماینده اضافه شد و ربات آن را می‌خواند — ولی
    # پنلِ خودِ نماینده نه. یعنی مالک می‌گفت «کانفیگ‌های این نماینده روی
    # اینباند ۴۱ و ۴۵»، نماینده از پنل خودش کانفیگ می‌ساخت، و روی
    # اینباند پیش‌فرض می‌نشست. بی‌صدا و بدون هیچ خطایی.
    #
    # دو پیاده‌سازی‌اند چون دو پردازه‌ی جدا هستند. این تست برابری‌شان را
    # اجرا می‌کند.


    def _bot_rule(t, inbound):
        """همان منطقِ bot/handlers.py، برای مقایسه."""
        import json as _j
        mode = t.get("inbound_mode") or "all"
        raw = None
        if mode == "custom":
            raw = t.get("inbound_ids")
        elif mode == "default":
            raw = _j.dumps([inbound]) if inbound else None
        if not raw:
            return None
        try:
            ids = _j.loads(raw) if isinstance(raw, str) else raw
        except Exception:      # noqa: BLE001
            ids = [x.strip() for x in str(raw).split(",") if x.strip()]
        out = []
        for x in (ids or []):
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out or None


    _CASES = [
        ({"inbound_mode": "all", "inbound_ids": None}, 28),
        ({"inbound_mode": "all", "inbound_ids": "[41]"}, 28),
        ({"inbound_mode": "default", "inbound_ids": None}, 28),
        ({"inbound_mode": "default", "inbound_ids": "[41,45]"}, 28),
        ({"inbound_mode": "custom", "inbound_ids": "[41,45]"}, 28),
        ({"inbound_mode": "custom", "inbound_ids": "[]"}, 28),
        ({"inbound_mode": "custom", "inbound_ids": None}, 28),
        ({"inbound_mode": "custom", "inbound_ids": "چرند"}, 28),
        ({"inbound_mode": None, "inbound_ids": "[41]"}, 28),
        ({"inbound_mode": "default", "inbound_ids": None}, 0),
    ]

    _diff = []
    for _t, _inb in _CASES:
        _a = AP._portal_inbound_ids(_t, _inb)
        _b = _bot_rule(_t, _inb)
        if _a != _b:
            _diff.append(f"{_t['inbound_mode']}/{_t['inbound_ids']} → "
                         f"پنل {_a} در برابر ربات {_b}")

    check("هر ده حالت در هر دو یکی جواب می‌دهد", not _diff,
          "، ".join(_diff) if _diff else f"{len(_CASES)} حالت سنجیده شد")

    # و چند نتیجه‌ی مشخص، تا برابریِ «هر دو غلط» بی‌معنی سبز نشود
    check("حالت all یعنی همه‌ی اینباندهای فعال",
          AP._portal_inbound_ids({"inbound_mode": "all"}, 28) is None,
          "None یعنی تصمیم با خود x-ui")
    check("حالت custom همان‌هایی را می‌دهد که انتخاب شده",
          AP._portal_inbound_ids(
              {"inbound_mode": "custom", "inbound_ids": "[41,45]"}, 28) == [41, 45])
    check("حالت default فقط اینباند پیش‌فرض",
          AP._portal_inbound_ids({"inbound_mode": "default"}, 28) == [28])
    check("و custom با فهرست خالی به all برمی‌گردد، نه فهرست تهی",
          AP._portal_inbound_ids(
              {"inbound_mode": "custom", "inbound_ids": "[]"}, 28) is None,
          "فهرست تهی به x-ui یعنی هیچ اینباندی — کانفیگ به هیچ‌جا وصل نمی‌شود")

    # و واقعا به x-ui پاس داده می‌شود
    _apsrc2 = _APP_NS_SRC
    check("و موقع ساخت کانفیگ به پنل x-ui داده می‌شود",
          "inbound_ids=_portal_inbound_ids(t, inbound)" in _apsrc2,
          "حساب‌کردنش بدون پاس‌دادنش بی‌فایده است")
else:
    _PRO_SKIPPED.append('پنل نماینده و ربات باید یک اینباند را انتخاب کنند')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("اینباندِ نماینده · انتخابش باید دیده شود")

    # مالک برای نماینده اینباند ۴۱ و ۴۵ را تعریف می‌کرد و پنلِ خودِ
    # نماینده باز هم می‌گفت «اینباند پیش‌فرض تنظیم نشده» — چون
    # _portal_inbound فقط ستون default_inbound را نگاه می‌کرد و
    # inbound_mode/inbound_ids را اصلاً نمی‌دید.
    #
    # یعنی پیامِ خطا دقیقاً چیزی را انکار می‌کرد که تعریف شده بود، و
    # نماینده هیچ راهی نداشت بفهمد چه کم است.


    class _FakeXui:
        """x-ui با دو اینباند فعال — نصبِ معمولی."""

        def __init__(self, ids=(41, 45)):
            self._ids = ids

        def inbounds(self):
            return [{"id": i, "enable": True} for i in self._ids]


    def _inb(t, xui=_FakeXui()):
        try:
            return AP._portal_inbound(t, xui)
        except Exception as e:
            return "خطا:" + str(getattr(e, "detail", e))[:20]


    # x-ui عمداً اینباندِ دیگری می‌دهد (۷۷ و ۸۸)، وگرنه «از انتخابِ
    # نماینده خواند» و «به x-ui افتاد» هر دو ۴۱ می‌دادند و تست نمی‌توانست
    # فرقشان را بگذارد — شکستنِ عمدی همین را نشان داد.
    check("نماینده‌ای که اینباند دارد ولی پیش‌فرض ندارد، کار می‌کند",
          _inb({"inbound_mode": "custom", "inbound_ids": "[41,45]",
                "default_inbound": None}, _FakeXui(ids=(77, 88))) == 41,
          "قبلاً همین حالت ۵۰۳ می‌گرفت — و ۴۱ فقط از انتخابِ خودش می‌آید")

    check("پیش‌فرضِ خودِ نماینده بر انتخابِ نداشته مقدم است",
          _inb({"inbound_mode": "all", "inbound_ids": None,
                "default_inbound": 45}, _FakeXui(ids=(77, 88))) == 45,
          "۴۵ فقط می‌تواند از ستون خودش آمده باشد")

    check("و وقتی هیچ‌کدام نیست، اولین اینباند فعال — مثل ربات",
          _inb({"inbound_mode": "all", "inbound_ids": None,
                "default_inbound": None}) == 41,
          "ربات از قبل همین کار را می‌کرد؛ پرتال خطا می‌داد")

    check("اینباند غیرفعال انتخاب نمی‌شود",
          AP._portal_inbound(
              {"inbound_mode": "all", "default_inbound": None},
              type("X", (), {"inbounds": lambda s: [
                  {"id": 7, "enable": False}, {"id": 9, "enable": True}]})()) == 9)

    _no_xui = None
    try:
        AP._portal_inbound({"inbound_mode": "all", "inbound_ids": None,
                            "default_inbound": None}, _FakeXui(ids=()))
        _no_xui = "بدون خطا رد شد"
    except Exception as e:
        _no_xui = str(getattr(e, "detail", e))
    check("وقتی واقعاً هیچ اینباندی نیست، خطا می‌دهد و می‌گوید چرا",
          "هیچ اینباند فعالی" in str(_no_xui),
          str(_no_xui)[:54])
else:
    _PRO_SKIPPED.append('اینباندِ نماینده · انتخابش باید دیده شود')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("پول نباید پیش از چیزی که ممکن است شکست بخورد کم شود")

    # _portal_charge اعتبار را واقعاً کم می‌کند. اگر بعد از آن چیزی
    # خطا بدهد و آن مسیر برگشت نداشته باشد، نماینده پول داده و کانفیگ
    # نگرفته.
    #
    # قبلاً ترتیب این بود:  charge → _portal_inbound → _portal_xui → add_client
    # و فقط شکستِ add_client برگشت داشت. یعنی همان نماینده‌ای که
    # اینباندش تنظیم نبود، اعتبارش هم می‌رفت.

    _ordering = []
    for _fn in ("portal_create", "portal_renew"):
        _i = _apsrc2.find("def %s(" % _fn)
        if _i < 0:
            _ordering.append("%s پیدا نشد" % _fn)
            continue
        _body = _apsrc2[_i:_i + 4000]
        _c = _body.find("_portal_charge(")
        _x = _body.find("_portal_xui(")
        if _c < 0:
            continue
        if 0 <= _c < _x:
            _ordering.append("%s: اتصال بعد از کسر اعتبار" % _fn)
        _ib = _body.find("_portal_inbound(")
        if _ib >= 0 and _c < _ib:
            _ordering.append("%s: اینباند بعد از کسر اعتبار" % _fn)

    check("اتصال و اینباند پیش از کسر اعتبار حل می‌شوند", not _ordering,
          "، ".join(_ordering) if _ordering
          else "هر دو فقط می‌خوانند، پس جایشان پیش از پول است")
else:
    _PRO_SKIPPED.append('پول نباید پیش از چیزی که ممکن است شکست بخورد کم شود')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("حذف کانفیگ · پولِ مشتریِ پشیمان باید برگردد")

    # موردی که مالک گفت: نماینده کانفیگ را می‌سازد، مشتری همان لحظه
    # پشیمان می‌شود. اگر اعتبار برنگردد، نماینده بابت چیزی پول داده که
    # هیچ‌کس استفاده‌اش نکرد.
    #
    # ولی کانفیگی که مصرف داشته دوره‌اش را کار کرده — همان قاعده‌ای که
    # مالک برای انقضا گذاشت: راه فرار از پرداخت نیست.


    class _DelXUI:
        deleted = []

        def find_client(self, _ib, email=None):
            return {"id": "uuid-" + str(email), "inboundId": 7}

        def delete_client(self, ib, uuid, email=None):
            _DelXUI.deleted.append(email)


    _T3 = AP._tenant_by_slug("hossein")
    _before_credit = int(_T3.get("credit") or 0)

    # کانفیگی که ساخته و پولش کم شده، ولی یک بایت هم مصرف نکرده
    AP._portal_charge(_T3, 30000, "ساخت hossein_fresh")
    _T3 = AP._tenant_by_slug("hossein")
    _after_charge = int(_T3.get("credit") or 0)
    check("اعتبار موقع ساخت کم شد", _after_charge == _before_credit - 30000,
          f"{_before_credit} → {_after_charge}")

    _FRESH = {"email": "hossein_fresh", "group": "goroh-a", "used": 0,
              "enable": True, "totalGB": 50 * 1024 ** 3, "expiry": 0, "limitIp": 1}
    _USEDC = {"email": "hossein_used", "group": "goroh-a", "used": 9 * 1024 ** 3,
              "enable": True, "totalGB": 50 * 1024 ** 3, "expiry": 0, "limitIp": 1}
    AP._read_xui_clients = lambda *a, **k: ([_FRESH, _USEDC], [], None)
    AP._portal_xui = lambda t: (_DelXUI(), Exception)

    _d1 = AP.portal_config_delete("hossein_fresh", _T3)
    _T3 = AP._tenant_by_slug("hossein")
    check("کانفیگ بی‌مصرف حذف شد", _d1["ok"] and "hossein_fresh" in _DelXUI.deleted)
    check("و اعتبارش برگشت", _d1["refunded"] == 30000,
          f"برگشت {_d1['refunded']} — از دفتر اعتبار، نه از نرخ امروز")
    check("اعتبار مستاجر هم واقعاً برگشت",
          int(_T3.get("credit") or 0) == _before_credit,
          f"{_T3.get('credit')} در برابر {_before_credit}")

    _d2 = AP.portal_config_delete("hossein_used", _T3)
    check("کانفیگ با مصرف هم حذف می‌شود", _d2["ok"])
    check("ولی اعتباری برنمی‌گردد", _d2["refunded"] == 0,
          "دوره‌اش را کار کرده — حذف راه فرار از پرداخت نیست")

    _bc = AP._billing_conn()
    _delrow = _bc.execute(
        "SELECT email, amount FROM deleted_clients "
        "WHERE email='hossein_used'").fetchone()
    _bc.close()
    check("و بیرون‌رفتنش از فاکتور بی‌صدا نمی‌ماند", _delrow is not None,
          "ردیفی در deleted_clients، تا مالک ببیند چه چیزی از فاکتور رفت")
else:
    _PRO_SKIPPED.append('حذف کانفیگ · پولِ مشتریِ پشیمان باید برگردد')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("فهرست کانفیگ‌ها · مصرف باید خام هم برود")

    # تصمیمِ «برگشت اعتبار» با used <= 0 گرفته می‌شود. اگر رابط با
    # usedGB قضاوت کند، مصرفِ چند مگابایتی به ۰٫۰ گرد می‌شود و دیالوگ
    # وعده‌ی برگشتی می‌دهد که بک‌اند انجامش نمی‌دهد.
    _TINY = {"email": "hossein_tiny", "group": "goroh-a", "used": 40 * 1024 ** 2,
             "enable": True, "totalGB": 50 * 1024 ** 3, "expiry": 0, "limitIp": 1}
    AP._read_xui_clients = lambda *a, **k: ([_TINY], [], None)
    _lst = AP.portal_configs(_T3)
    _one = (_lst.get("configs") or [_lst])[0] if _lst.get("configs") else None
    check("مصرف خام در پاسخ هست", _one is not None and "used" in _one,
          "کلیدهای موجود: " + "، ".join(sorted((_one or {}).keys()))[:60])
    check("و مصرفِ کوچک به صفر گرد نمی‌شود",
          _one and _one["used"] > 0 and _one["usedGB"] == 0.0,
          f"used={(_one or {}).get('used')} · usedGB={(_one or {}).get('usedGB')}")


else:
    _PRO_SKIPPED.append('فهرست کانفیگ\u200cها · مصرف باید خام هم برود')

# ═══════════════════════════════════════════════════════════
if PRO:
    head("مینی‌اپ · امضا تنها دیواری است که بین مشتری‌هاست")

    # initData رشته‌ای است که تلگرام امضا کرده. اگر امضا سنجیده نشود، هر
    # کسی می‌تواند user={"id":...} بفرستد و اشتراک‌های هر مشتری‌ای را
    # ببیند. این تنها چیزی است که جلویش را می‌گیرد.

    import hashlib as _hl
    import hmac as _hm
    import re as _re
    import time as _tm
    import json as _json
    from urllib.parse import urlencode as _ue

    _BOT = "8100001:AA-token-for-the-signature-test"


    def _sign(token, user_id=555, age=0, extra=None):
        """یک initData معتبر می‌سازد — همان‌طور که تلگرام می‌سازد."""
        pairs = {
            "auth_date": str(int(_tm.time()) - age),
            "query_id": "AAH",
            "user": _json.dumps({"id": user_id, "first_name": "آزمون"},
                                ensure_ascii=False),
        }
        pairs.update(extra or {})
        check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        secret = _hm.new(b"WebAppData", token.encode(), _hl.sha256).digest()
        pairs["hash"] = _hm.new(secret, check.encode(), _hl.sha256).hexdigest()
        return _ue(pairs)


    _sok, _d = AP._mini_check(_sign(_BOT), _BOT)
    check("امضای درست پذیرفته می‌شود", _sok and _d["user"]["id"] == 555, str(_d)[:60])

    _sok2, _w2 = AP._mini_check(_sign(_BOT), "8100002:AA-a-different-bots-token")
    check("امضای یک ربات با توکن ربات دیگر رد می‌شود", not _sok2, str(_w2)[:52])

    _forged = _sign(_BOT).replace("hash=", "hash=0")
    check("امضای دستکاری‌شده رد می‌شود",
          not AP._mini_check(_forged, _BOT)[0])

    _noHash = _ue({"auth_date": str(int(_tm.time())),
                   "user": _json.dumps({"id": 555})})
    check("بدون امضا اصلاً رد می‌شود", not AP._mini_check(_noHash, _BOT)[0],
          "وگرنه فرستادن شناسه کافی بود تا حساب دیگری دیده شود")

    _old = _sign(_BOT, age=25 * 3600)
    _sok3, _w3 = AP._mini_check(_old, _BOT)
    check("امضای کهنه‌تر از ۲۴ ساعت رد می‌شود", not _sok3, str(_w3)[:46])

    _fresh = _sign(_BOT, age=23 * 3600)
    check("ولی امضای ۲۳ ساعته هنوز قبول است",
          AP._mini_check(_fresh, _BOT)[0],
          "سقف نباید آن‌قدر تنگ باشد که نشست وسط کار بیفتد")

    _future = _sign(_BOT, age=-3600)
    check("امضای با تاریخِ آینده رد می‌شود",
          not AP._mini_check(_future, _BOT)[0])

    _noUser = _sign(_BOT, extra={"user": "{}"})
    check("امضای بدون شناسه‌ی کاربر رد می‌شود",
          not AP._mini_check(_noUser, _BOT)[0])

    # داخل خودِ تابع، نه هرجای فایل: compare_digest شش جای دیگر app.py
    # هم هست و شکستنِ عمدی نشان داد جایگزینی‌اش با == گرفته نمی‌شود
    _chk_fn = _APSRC[_APSRC.find("def _mini_check("):]
    _chk_fn = _chk_fn[:_chk_fn.find(chr(10) + "def ", 10)]
    check("مقایسه‌ی امضا با compare_digest است",
          "compare_digest" in _chk_fn and "want != got" not in _chk_fn,
          "مقایسه‌ی معمولی از روی زمانش لو می‌دهد")


    # ═══════════════════════════════════════════════════════════
    head("مینی‌اپ · مرزها")

    _mini_routes = _re.findall(r'@app\.(?:get|post|put|delete)\("(/api/mini/[^"]*)"\)',
                               _APSRC)
    check("مسیرهای مینی‌اپ پیدا شدند", len(_mini_routes) >= 3,
          "، ".join(_mini_routes))

    # هر مسیر باید از mini_user رد شود — مثل همان قاعده‌ای که برای
    # /api/portal/* هست
    _unguarded = []
    # تنها استثنا، همان که test-seams دارد: برندِ فروشگاه برای اولین فریمِ
    # اسپلش، پیش از ورود. آن‌جا سنجیده می‌شود که جز `_shop_brand` چیزی ندهد.
    for _r in [r for r in _mini_routes if r != "/api/mini/brand"]:
        _i = _APSRC.find('"%s"' % _r)
        _seg = _APSRC[_i:_i + 400]
        if "Depends(mini_user)" not in _seg:
            _unguarded.append(_r)
    check("هر مسیر مینی‌اپ از احراز هویت رد می‌شود", not _unguarded,
          "، ".join(_unguarded) if _unguarded else "%d مسیر" % len(_mini_routes))

    # و هیچ‌کدام نباید به حسابداری دست بزنند — مالک گفت جداست
    _MONEY = ("_billing_conn", "_line_amount", "_period_share", "_portal_charge",
              "_bill_since", "billing.db", "group_config")
    # The mini app's code is backend/pro/mini.py since the Pro split.
    _block = io.open(os.path.join(str(ROOT), "backend", "pro", "mini.py"), encoding="utf-8").read()
    _touched = [w for w in _MONEY if w in _block]
    check("مینی‌اپ به حسابداری دست نمی‌زند", _block and not _touched,
          "، ".join(_touched) if _touched
          else "نه نرخ حساب می‌کند، نه اعتبار کم می‌کند")

    # خرید حالا از داخل مینی‌اپ هم انجام می‌شود، ولی منطقش این‌جا
    # نیست: `/api/mini/buy` فقط ورودی را می‌سنجد و
    # `handlers.wallet_purchase` را صدا می‌زند — همان هسته‌ای که خرید از
    # داخل ربات هم از آن رد می‌شود. اگر این‌جا دوباره نوشته شود، می‌شود
    # مسیر چهارمِ پول و همان الگویی که سه بار تکرار شد.
    #
    # کامنت‌ها اول برداشته می‌شوند: این تست یک‌بار قرمز شد چون کلمه‌ی
    # `approved` در توضیحِ خودِ کد پیدا می‌شد، نه در کد.
    _bcode = "\n".join(l for l in _block.split("\n")
                       if not l.strip().startswith("#"))
    _OWN_MONEY = ("close_order", "spend_balance", "create_order",
                  "after_paid_order", "pay_commission", "reward_referrer", "SET status")
    _own = [w for w in _OWN_MONEY if w in _bcode]
    check("مینی‌اپ خودش پول جابه‌جا نمی‌کند", not _own,
          "، ".join(_own) if _own else "از wallet_purchase رد می‌شود")

    # دنبالِ *صداشدن* بگرد، نه نامِ تابع: `wallet_purchase` در docstring
    # همین کد هم هست، و docstring با برداشتنِ خطوطِ `#` پاک نمی‌شود. با
    # شرطِ قبلی، برداشتنِ خودِ صدازدن هم سبز می‌ماند.
    check("و خرید از همان هسته‌ی ربات می‌آید",
          "h.wallet_purchase(" in _bcode,
          "یک نسخه برای هر دو مسیر — وگرنه مسیر چهارمِ پول")
else:
    _PRO_SKIPPED.append("mini app: signature and boundaries")


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("پلن نماینده · حجم از نرخِ مالک می‌آید، نه از دلخواه")

    # سه حالتِ `_portal_gb_policy`، مستقیم — بدون دیتابیس حسابداری،
    # چون آن‌چه می‌سنجیم خودِ قاعده است نه خواندنش.
    _saved_rates = app._portal_rates


    def _rates_as(conf, rates):
        app._portal_rates = lambda _t: (conf, rates)


    try:
        _rates_as({"per_gb": 2500}, [])
        _m, _a, _pg = app._portal_gb_policy({"id": 1})
        check("نرخ حجمی یعنی هر حجمی مجاز است", _m == "volume" and _pg == 2500,
              f"{_m} / {_pg}")

        _rates_as({}, [{"gb": 30, "price": 90000}, {"gb": 100, "price": 250000},
                       {"gb": 50, "price": 150000}])
        _m, _a, _pg = app._portal_gb_policy({"id": 1})
        check("پله‌ها مرتب و بی‌تکرار برمی‌گردند",
              _m == "tiers" and _a == [30, 50, 100], f"{_m} / {_a}")

        _rates_as({}, [])
        _m, _a, _pg = app._portal_gb_policy({"id": 1})
        check("بدون نرخ، حالت باز است و بسته نمی‌شود", _m == "open", _m)

        # ── اعتبارسنجی باید در بکند باشد، نه فقط در رابط ──
        _rates_as({}, [{"gb": 30, "price": 90000}, {"gb": 100, "price": 250000}])

        # قیمت بالای بزرگ‌ترین کف است: این بلوک پله‌ها را می‌سنجد، نه قیمت
        def _save(gb, price=300000):
            return app.portal_bot_plans_save(
                {"plans": [{"name": "پلن", "gb": gb, "days": 30,
                            "ip_limit": 1, "price": price}]},
                t={"id": tid, "portal_group": "g"})

        try:
            _save(70)
            check("حجمِ خارج از پله رد می‌شود", False, "پذیرفته شد")
        except app.HTTPException as _e:
            check("حجمِ خارج از پله رد می‌شود", _e.status_code == 400,
                  str(_e.status_code))
            # پیام باید *بگوید* چه چیزی مجاز است
            check("و پله‌های مجاز را می‌گوید",
                  "30" in str(_e.detail) and "100" in str(_e.detail),
                  str(_e.detail)[:80])

        # پله‌ی مجاز باید بگذرد
        try:
            _r = _save(100)
            check("پله‌ی مجاز پذیرفته می‌شود", bool(_r), str(_r)[:60])
        except app.HTTPException as _e:
            check("پله‌ی مجاز پذیرفته می‌شود", False, str(_e.detail)[:80])

        # در حالت حجمی هیچ حجمی رد نمی‌شود — ولی قیمت از کفش (۷۷۷ × ۲٬۵۰۰) پایین‌تر
        # نه. تا ۱.۱۱۴ همین‌جا ۳۰۰٬۰۰۰ تومان برای ۷۷۷ گیگ پذیرفته می‌شد: حالتِ حجمی
        # اصلاً کف نداشت.
        _rates_as({"per_gb": 2500}, [])
        try:
            _save(777)
            check("در حالت حجمی، زیرِ «حجم × نرخ» رد می‌شود", False, "پذیرفته شد")
        except app.HTTPException as _e:
            check("در حالت حجمی، زیرِ «حجم × نرخ» رد می‌شود",
                  _e.status_code == 400 and "۱٬۹۴۲٬۵۰۰" in str(_e.detail), str(_e.detail)[:80])
        try:
            _r = _save(777, price=1942500)
            check("در حالت حجمی، هر حجمی می‌گذرد", bool(_r), str(_r)[:60])
        except app.HTTPException as _e:
            check("در حالت حجمی، هر حجمی می‌گذرد", False, str(_e.detail)[:80])
    finally:
        app._portal_rates = _saved_rates
else:
    _PRO_SKIPPED.append('پلن نماینده · حجم از نرخِ مالک می\u200cآید، نه از دلخواه')


# ═══════════════════════════════════════════════════════════
head("پاسخ پشتیبانی · ربات شلوغ نشود")

# چرا این بخش: تا امروز **متنِ کاملِ پاسخ** در گفتگوی ربات هم نوشته
# می‌شد. یعنی هر مکالمه دو بار وجود داشت — یک‌بار در مینی‌اپ و
# یک‌بار در ربات — و ربات پر می‌شد از چیزی که مشتری همان‌جا داشت.
#
# ولی حذفِ کامل هم غلط است: مشتری‌ای که مینی‌اپ را باز نکند هرگز
# نمی‌فهمد جواب آمده.
#
# پس یک خطِ کوتاه با دکمه، و فقط وقتی خبرِ خوانده‌نشده‌ای از قبل
# نمانده باشد.

import tempfile as _tfq                                   # noqa: E402
import sqlite3 as _sqq                                    # noqa: E402
from pathlib import Path as _Pq                            # noqa: E402

_qdir = _Pq(_tfq.mkdtemp(prefix="nx-quiet-"))
_old_botq = app.BOT_DB
try:
    _qdb = _qdir / "bot.db"
    _qc = _sqq.connect(str(_qdb))
    import sys as _sysq
    _sysq.path.insert(0, ".")
    from bot import db as _BDq
    _qc.executescript(_BDq.SCHEMA)
    _BDq._migrate(_qc)
    _qc.execute("INSERT INTO tenants (id,name,bot_token,settings) "
                "VALUES (1,'owner','1:x','{\"miniapp_url\": \"https://panel.example/app\"}')")
    _qc.execute("INSERT INTO users (id,tenant_id,tg_id,first_name) "
                "VALUES (1,1,5550001,'مریم')")
    _qc.commit()
    _qc.close()
    app.BOT_DB = _qdb

    # جاسوس روی ارسال — هیچ شبکه‌ای در کار نیست
    _sentq = []
    _hq = app._bot_handlers()
    _old_botcls = _hq.Bot

    class _FakeBotQ:
        def __init__(self, *a, **k):
            pass

        def send(self, chat_id, text, keyboard=None, **k):
            _sentq.append(str(text))
            return {"ok": True}

        def send_photo_bytes(self, chat_id, data, **k):
            _sentq.append(str(k.get("caption") or ""))
            return {"ok": True}

    _hq.Bot = _FakeBotQ
    # The mini app is Pro (`mini_app`); no license is active in this test, so
    # without this the "with a mini app" branch would never run here.
    _old_pa = _hq.pro_allowed
    if PRO:
        _hq.pro_allowed = lambda f: True
    # The bot's own db module reads its DB_PATH, not app.BOT_DB. Point it at
    # this section's database too: it found user 1 only because a reseller
    # section earlier in the file had left one in the shared test database,
    # and the Community tree (no reseller sections) showed it.
    _old_hq_db = _hq.DB.DB_PATH
    _hq.DB.DB_PATH = _qdb
    try:
        # A system note the buyer never read (a reminder copy) must not
        # silence support notices: the old count included those.
        _BDq.TenantDB(1).chat_add(1, "system", "یادآوری ۳ روز مانده")
        _has_app = bool(_hq.miniapp_url(app._mini_ctx(app._root_tenant_row())[1]))
        if PRO:
            check("with Pro the shop has a mini app (the branch below is tested)", _has_app)
        for _i in range(1, 6):
            app.admin_inbox_send({"userId": 1, "body": f"پاسخ {_i}"},
                                 x_admin_password=app._INTERNAL_PW)

        if _has_app:
            check("پنج پاسخِ پشت‌سرهم یک خبر می‌دهد، نه پنج‌تا",
                  len(_sentq) == 1, f"{len(_sentq)} پیام در ربات")
            check("و متنِ پاسخ در ربات نوشته نمی‌شود",
                  _sentq and "پاسخ ۱" not in _sentq[0] and "پاسخ 1" not in _sentq[0],
                  "مکالمه نباید دو جا تکرار شود")
        else:
            # Without a mini app the bot is the only place to read a reply:
            # the old "press /start to see it" led nowhere.
            check("without a mini app each reply arrives in full in the bot",
                  len(_sentq) == 5 and "پاسخ 3" in _sentq[2], _sentq[:2])

        if PRO:
            # مشتری می‌خواند → چرخه از نو
            app.mini_inbox_read((app._root_tenant_row(),
                                 {"id": 1, "tg_id": 5550001, "first_name": "مریم"}))
            _before = len(_sentq)
            app.admin_inbox_send({"userId": 1, "body": "پاسخ تازه"},
                                 x_admin_password=app._INTERNAL_PW)
            check("بعد از خواندن، خبرِ تازه می‌آید",
                  len(_sentq) == _before + 1,
                  "وگرنه مشتری هیچ‌وقت از پاسخِ بعدی خبردار نمی‌شود")

            # و همه‌ی پاسخ‌ها در مینی‌اپ هستند
            _boxq = app.mini_inbox((app._root_tenant_row(),
                                    {"id": 1, "tg_id": 5550001, "first_name": "مریم"}))
            check("هر شش پاسخ در صندوقِ مینی‌اپ هست",
                  len([m for m in (_boxq.get("messages") or []) if m.get("from") == "admin"]) == 6,
                  f"{len(_boxq.get('messages') or [])} پیام")
    finally:
        _hq.Bot = _old_botcls
        _hq.pro_allowed = _old_pa
        _hq.DB.DB_PATH = _old_hq_db
finally:
    app.BOT_DB = _old_botq

check("متنِ پاسخ دیگر در ربات نوشته نمی‌شود",
      'f"💬 <b>پاسخ پشتیبانی</b>' not in _APSRC,
      "مکالمه یک جا باشد، نه دو جا")


# ═══════════════════════════════════════════════════════════
head("ترافیک · کاربری که در چند اینباند است")

# چرا این بخش: `client_traffics` یک ردیف به ازای هر (اینباند، ایمیل)
# دارد، نه یک ردیف به ازای هر کاربر. کاربری که هم روی XHTTP است و
# هم روی TCP+Vision — همان چیدمانی که خودِ این پروژه پیشنهاد
# می‌دهد — دو ردیف دارد.
#
# کدِ قبلی روی هم می‌نوشت و فقط آخرین ردیف می‌ماند.
#
# اندازه‌گیری روی دادهٔ واقعیِ یک سرور: گروه‌هایی که کاربرانشان یک
# اینباند داشتند دقیق می‌خواندند، و بقیه کم می‌آمدند — «yaser» ۴۳۵
# گیگ مصرف داشت و پنل ۱۱۱ نشان می‌داد. روی صورتحساب یعنی همه‌ی
# مصرف‌ها کمتر از واقعیت.

import tempfile as _tfi                                   # noqa: E402
import sqlite3 as _sqi                                    # noqa: E402
import time as _tmi                                       # noqa: E402
import os as _osi                                         # noqa: E402
from pathlib import Path as _Pi                            # noqa: E402

_GBi = 1024 ** 3
_idir = _Pi(_tfi.mkdtemp(prefix="nx-inbx-"))
_old_xi = _osi.environ.get("XUI_DB_PATH", "")
_old_bi = app.BILLING_DB
try:
    _xpi = _idir / "x-ui.db"
    _osi.environ["XUI_DB_PATH"] = str(_xpi)
    app.BILLING_DB = _idir / "bill.db"
    _ix = _sqi.connect(str(_xpi))
    _ix.executescript("""
        CREATE TABLE clients (email TEXT, total_gb INTEGER, expiry_time INTEGER,
                              enable INTEGER, created_at INTEGER, group_name TEXT,
                              reset INTEGER DEFAULT 0, limit_ip INTEGER DEFAULT 0);
        CREATE TABLE client_traffics (id INTEGER PRIMARY KEY, inbound_id INTEGER,
                                      email TEXT, up INTEGER, down INTEGER,
                                      expiry_time INTEGER, enable INTEGER);
        CREATE TABLE client_groups (id INTEGER PRIMARY KEY, name TEXT);
    """)
    _ix.execute("INSERT INTO client_groups (id,name) VALUES (1,'g1')")
    # یکی در یک اینباند، یکی در دو، یکی در چهار
    _plan = (("solo", [60]), ("duo", [90, 70]), ("quad", [40, 35, 30, 25]))
    for _em, _legs in _plan:
        _ix.execute("INSERT INTO clients VALUES (?,?,0,1,?,'g1',0,0)",
                    (_em, 500 * _GBi, int(_tmi.time() * 1000)))
        for _i2, _gb in enumerate(_legs, 1):
            _ix.execute("INSERT INTO client_traffics "
                        "(inbound_id,email,up,down,expiry_time,enable) "
                        "VALUES (?,?,0,?,0,1)", (_i2, _em, int(_gb * _GBi)))
    _ix.commit()

    _icls, _ik, _ierr = app._read_xui_clients()
    _by = {c["email"]: c["used"] / _GBi for c in (_icls or [])}

    check("کاربرِ تک‌اینباند درست خوانده می‌شود",
          abs(_by.get("solo", 0) - 60) < 1, f"{_by.get('solo', 0):.0f} GB")
    check("کاربرِ دو-اینباندی جمع می‌شود، نه آخرین ردیف",
          abs(_by.get("duo", 0) - 160) < 1,
          f"{_by.get('duo', 0):.0f} GB — پیش از این ۷۰ بود (فقط ردیف آخر)")
    check("و چهار-اینباندی هم",
          abs(_by.get("quad", 0) - 130) < 1,
          f"{_by.get('quad', 0):.0f} GB — پیش از این ۲۵ بود")
    check("جمعِ گروه با واقعیت می‌خواند",
          abs(sum(_by.values()) - 350) < 1, f"{sum(_by.values()):.0f} GB")

    # انقضا: دورترین، نه آخرین ردیف. کاربر تا وقتی یک اینباندش باز
    # است وصل می‌شود.
    _ix.execute("DELETE FROM client_traffics")
    _ix.execute("DELETE FROM clients")
    _ix.execute("INSERT INTO clients VALUES ('x1',?,0,1,?,'g1',0,0)",
                (100 * _GBi, int(_tmi.time() * 1000)))
    _ix.execute("INSERT INTO client_traffics "
                "(inbound_id,email,up,down,expiry_time,enable) "
                "VALUES (1,'x1',0,0,5000,0)")
    _ix.execute("INSERT INTO client_traffics "
                "(inbound_id,email,up,down,expiry_time,enable) "
                "VALUES (2,'x1',0,0,9000,1)")
    _ix.commit()
    _c2 = [c for c in (app._read_xui_clients()[0] or []) if c["email"] == "x1"]
    check("دورترین انقضا برداشته می‌شود",
          _c2 and _c2[0]["expiry"] == 9000,
          str(_c2[0]["expiry"]) if _c2 else "ردیفی نیامد")

    _ix.close()
finally:
    if _old_xi:
        _osi.environ["XUI_DB_PATH"] = _old_xi
    else:
        _osi.environ.pop("XUI_DB_PATH", None)
    app.BILLING_DB = _old_bi

# ── قاعده در کد بماند ──
_TRSRC = _APSRC.split("def _read_xui_clients(")[1].split("\ndef ")[0]
check("ترافیک جمع می‌شود، نه جایگزین",
      'cur["up"] += up' in _TRSRC and 'traffic[r["email"]] = dict(r)' not in _TRSRC,
      "یک ردیف به ازای هر اینباند — جایگزینی یعنی بقیه دور ریخته می‌شوند")

_UWSRC2 = _io.open("scripts/usage-why.py", encoding="utf-8").read()
check("ابزارِ تشخیص هم جمع می‌کند",
      "traffic.get(em, 0) +" in _UWSRC2,
      "وگرنه ابزار عددی می‌گوید که پنل نمی‌گوید")


# ═══════════════════════════════════════════════════════════
head("مسیر x-ui · کدام فایل، وقتی چندتا هست")

# چرا این بخش: نصب‌های واقعی بیش از یک `x-ui.db` دارند — نصبِ
# دوباره، مهاجرت، یا بک‌آپی که کنارش مانده. انتخاب «اولینِ فهرست»
# بود، پس پنل می‌توانست عددِ یک فایلِ مرده را بخواند که هیچ‌وقت عوض
# نمی‌شود.
#
# از بیرون شبیهِ «حسابداری آپدیت نمی‌شود» دیده می‌شد و با پنلِ خودِ
# x-ui هم نمی‌خواند — و هیچ‌جا نمی‌گفت چرا.

import tempfile as _tfp                                   # noqa: E402
import os as _osp                                         # noqa: E402
import time as _tmp2                                      # noqa: E402
from pathlib import Path as _Pp                            # noqa: E402

_pdir = _Pp(_tfp.mkdtemp(prefix="nx-xpath-"))
_old_c = app.XUI_CANDIDATES
_old_e = _osp.environ.get("XUI_DB_PATH", "")
try:
    _osp.environ.pop("XUI_DB_PATH", None)
    _dead = _pdir / "dead.db"
    _live = _pdir / "live.db"
    _dead.write_bytes(b"x" * 100)
    _live.write_bytes(b"x" * 100)
    # مرده: ۹ روز پیش. زنده: همین حالا.
    _t9 = _tmp2.time() - 9 * 86400
    _osp.utime(_dead, (_t9, _t9))

    # مرده عمداً اولِ فهرست است — همان چیزی که روی سرور پیش می‌آید
    app.XUI_CANDIDATES = [str(_dead), str(_live)]
    _pick = app._xui_db_path()
    check("تازه‌ترین فایل انتخاب می‌شود، نه اولینِ فهرست",
          str(_pick) == str(_live),
          f"{_Pp(_pick).name} — x-ui هر چند ثانیه روی فایلِ زنده می‌نویسد")

    _cands = app._xui_db_candidates()
    check("و همه‌ی نامزدها قابل دیدن‌اند", len(_cands) == 2,
          f"{len(_cands)} فایل — بدون این، انتخاب بی‌صدا می‌ماند")
    check("و مرتب‌اند: تازه‌ترین اول",
          _cands and _cands[0]["path"] == str(_live))

    # یکی که باشد، همان
    app.XUI_CANDIDATES = [str(_dead)]
    check("با یک فایل، همان برمی‌گردد",
          str(app._xui_db_path()) == str(_dead))

    # هیچ‌کدام نباشد، اولینِ فهرست برمی‌گردد تا پیام خطا معنا داشته باشد
    app.XUI_CANDIDATES = [str(_pdir / "nope-a.db"), str(_pdir / "nope-b.db")]
    check("و وقتی هیچ‌کدام نیست، پیام خطا به مسیرِ مورد انتظار اشاره می‌کند",
          str(app._xui_db_path()) == str(_pdir / "nope-a.db"))

    # مسیرِ صریح همیشه بر حدس مقدم است
    _osp.environ["XUI_DB_PATH"] = str(_dead)
    app.XUI_CANDIDATES = [str(_live)]
    check("مسیرِ صریحِ سرویس بر حدس مقدم است",
          str(app._xui_db_path()) == str(_dead),
          "وگرنه تنظیمِ دستیِ مالک بی‌اثر می‌شد")
finally:
    app.XUI_CANDIDATES = _old_c
    if _old_e:
        _osp.environ["XUI_DB_PATH"] = _old_e
    else:
        _osp.environ.pop("XUI_DB_PATH", None)

# ── ابزارِ تشخیص همان قاعده را داشته باشد ──
#
# اگر دو قاعده باشند، ابزار فایلی را نام می‌برد که پنل نمی‌خواند —
# که از گزارش‌نکردن بدتر است.
_UWSRC = _io.open("scripts/usage-why.py", encoding="utf-8").read()
check("ابزارِ usage-why هم تازه‌ترین را برمی‌دارد",
      "_find_newest(XUI_PATHS)" in _UWSRC,
      "دو قاعده یعنی ابزار فایلِ اشتباه را نام می‌برد")
if PRO:        # the diagnosis is accounting, Pro
    check("و تشخیصِ پنل چند-فایل‌بودن را گزارش می‌کند",
          "_xui_db_candidates()" in _APSRC.split("def billing_diagnose")[1][:3000],
          "انتخابِ بی‌صدا همان چیزی است که این باگ را ماه‌ها پنهان نگه داشت")
else:
    _PRO_SKIPPED.append("x-ui path: the diagnosis names every candidate")


# ═══════════════════════════════════════════════════════════
head("سکه · همان نردبانی که صندوق به کار می‌برد")

# چرا این بخش: صفحه‌ی «سکه و دعوت» پنل عددها را جایی می‌نوشت که
# ربات نگاه نمی‌کرد (`settings.coins_per_referral` در برابر
# `settings.coins.per_referral`). مالک عدد می‌گذاشت، «ذخیره شد»
# می‌دید، و ربات پیش‌فرض می‌داد. اندازه‌گیری‌شده: «۲۵ سکه به معرف»
# → ربات ۱۰ می‌داد.
#
# حالا مینی‌اپ هم همان نردبان را نشان می‌دهد، پس سه‌تایی باید یکی
# باشند: پنل، مینی‌اپ، و لحظه‌ی خرید.

import json as _jsc                                       # noqa: E402
import tempfile as _tfc                                   # noqa: E402
import sqlite3 as _sqc                                    # noqa: E402
import base64 as _b64c                                    # noqa: E402
from pathlib import Path as _Pc                            # noqa: E402

_cdir = _Pc(_tfc.mkdtemp(prefix="nx-coinx-"))
_old_bot3 = app.BOT_DB
_old_chat = app.CHAT_DIR
try:
    app.CHAT_DIR = _cdir / "chat"
    _cdb = _cdir / "bot.db"
    _cc = _sqc.connect(str(_cdb))
    _cc.row_factory = _sqc.Row
    import sys as _sysc
    _sysc.path.insert(0, ".")
    from bot import db as _BDc
    _cc.executescript(_BDc.SCHEMA)
    _BDc._migrate(_cc)

    # نرخ‌هایی که هیچ‌کدام پیش‌فرض نیستند — وگرنه تست با پیش‌فرض هم
    # سبز می‌شود و دقیقاً همان باگ را نمی‌بیند
    _cset = {"coins": {"per_referral": 25, "welcome_bonus": 7,
                       "max_percent": 40,
                       "tiers": [{"coins": 30, "percent": 15},
                                 {"coins": 60, "percent": 35},
                                 {"coins": 90, "percent": 60}]}}
    _cc.execute("INSERT INTO tenants (id,name,settings,bot_username) "
                "VALUES (1,'owner',?,?)",
                (_jsc.dumps(_cset, ensure_ascii=False), "nexora_bot"))
    _cc.execute("INSERT INTO users (id,tenant_id,tg_id,first_name,coins,ref_code) "
                "VALUES (1,1,555001,'مریم',40,'NX7K2M')")
    _cc.execute("INSERT INTO users (id,tenant_id,tg_id,first_name,referred_by) "
                "VALUES (2,1,555002,'سارا',1)")
    _cc.commit()
    app.BOT_DB = _cdb

    _ct = dict(_cc.execute("SELECT * FROM tenants WHERE id=1").fetchone())
    _cu = dict(_cc.execute("SELECT * FROM users WHERE id=1").fetchone())
    if PRO:
        _rw = app.mini_rewards((_ct, _cu))

        check("نرخِ معرف از تنظیماتِ مالک می‌آید", _rw["perReferral"] == 25,
              f"{_rw['perReferral']} — پیش‌فرض ۱۰ است، پس تنظیمات واقعاً رسیده")
        check("و پاداشِ دعوت‌شده هم", _rw["welcomeBonus"] == 7,
              str(_rw["welcomeBonus"]))
        check("پله‌های خودِ مالک، نه پیش‌فرض",
              [x["coins"] for x in _rw["tiers"]] == [30, 60, 90],
              str([x["coins"] for x in _rw["tiers"]]))
        check("سقفِ تخفیف روی پله‌ی بلندتر اعمال می‌شود",
              _rw["tiers"][-1]["percent"] == 40,
              "پله ۶۰٪ نوشته، سقف ۴۰٪ است — بدون این، کاربر عددی می‌بیند که نمی‌گیرد")

        # ── و همان عددی که صندوق کم می‌کند ──
        #
        # این مهم‌ترین سطرِ این بخش است: اگر مینی‌اپ نردبان را خودش
        # می‌ساخت، روزی «۳۵٪» نشان می‌داد و صندوق ۱۵٪ کم می‌کرد.
        import core as _corec                                  # noqa: E402
        _pr = _corec.price_order(500000, coins=40,
                                 coin_cfg=_cset["coins"], use_coins=True)
        check("درصدِ مینی‌اپ با درصدِ لحظه‌ی خرید یکی است",
              _rw["percent"] == _pr["coin_percent"],
              f"مینی‌اپ {_rw['percent']}٪ · صندوق {_pr['coin_percent']}٪")
        check("و پله‌ی بعدی درست شمرده می‌شود",
              _rw["next"] and _rw["next"]["need"] == 20,
              str(_rw.get("next")))
        check("لینکِ دعوت کامل است",
              _rw["link"] == "https://t.me/nexora_bot?start=NX7K2M", _rw["link"])
        check("و شمارِ دعوت‌شده‌ها", _rw["refCount"] == 1, str(_rw["refCount"]))

    # ── عکسِ گفتگو ──
    head("عکسِ گفتگو · آدرس، خودش کلید است")

    _png = _b64c.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGA"
        "hKmMIQAAAABJRU5ErkJggg==")
    _url = app._chat_photo_save(1, 1, _b64c.b64encode(_png).decode())
    _name = _url.rsplit("/", 1)[-1]
    # نامِ قابل‌حدس یعنی هر کسی با شمردنِ شناسه‌ها عکسِ پشتیبانیِ
    # بقیه را برمی‌دارد — همان قاعده‌ی عکسِ پروفایل
    check("نامِ فایل تصادفی است، نه <مستاجر>_<کاربر>",
          len(_name.split("_")[-1].split(".")[0]) >= 24, _name)
    check("و سرو می‌شود", app.public_chat_photo(_name).media_type == "image/png")
    check("بایت‌هایش برای تلگرام هم در دسترس است",
          app._chat_photo_bytes(_url) == _png)

    for _bad, _lbl, _code in (
            (b"not an image", "فایلِ غیرتصویری", 400),
            (b"\x89PNG\r\n\x1a\n" + b"x" * (4 * 1024 * 1024), "بیش از حد", 413)):
        try:
            app._chat_photo_save(1, 1, _b64c.b64encode(_bad).decode())
            check(f"{_lbl} رد می‌شود", False, "پذیرفته شد")
        except app.HTTPException as _e:
            check(f"{_lbl} رد می‌شود", _e.status_code == _code, str(_e.status_code))

    # نامِ آمده از بیرون نباید به مسیر بچسبد
    _esc = []
    for _n in ("../config.json", "..\\x", "a/b", "....//x"):
        try:
            app.public_chat_photo(_n)
            _esc.append(_n)
        except app.HTTPException:
            pass
    check("مسیرِ آمده از بیرون از پوشه بیرون نمی‌زند", not _esc, "، ".join(_esc))

    # ── پیامِ فقط‌عکس ──
    # chat_threads joins users: this section makes its own customer instead of
    # finding one a reseller section left behind (absent in the Community tree).
    with _BDc.conn() as _ccu:
        _ccu.execute("INSERT OR IGNORE INTO users (id, tenant_id, tg_id, first_name) "
                    "VALUES (1, 1, 5550003, 'عکس')")
    _cdb2 = _BDc.TenantDB(1)
    check("پیامی که فقط عکس دارد ثبت می‌شود",
          _cdb2.chat_add(1, "user", "", photo=_url) is not None,
          "عکسِ بدونِ متن پیامِ معتبری است")
    check("و پیامِ کاملاً خالی نه",
          _cdb2.chat_add(1, "user", "", photo=None) is None)
    _crows = _cdb2.chat_list(1)
    check("عکس با پیام برمی‌گردد", bool(_crows[-1]["photo"]))
    _cth = _cdb2.chat_threads()
    check("پیش‌نمایشِ گفتگو خالی نمی‌ماند",
          bool(app._row_get(_cth[0], "last_photo")),
          "پیامِ فقط‌عکس در فهرست یک خطِ خالی می‌شد")

    # ترتیبِ به‌روزرسانی روی سرور مرتب نیست: پنل تازه می‌شود و ربات
    # هنوز ری‌استارت نشده، پس ستونِ تازه هنوز نیست
    check("ستونِ نبوده کلِ صندوق را نمی‌اندازد",
          app._row_get(_crows[-1], "nope", "د") == "د",
          "sqlite3.Row برای کلیدِ ناموجود IndexError می‌دهد، نه None")

    _cc.close()
finally:
    app.BOT_DB = _old_bot3
    app.CHAT_DIR = _old_chat

# ── قواعدی که در کد بمانند ──
check("عکس پیش از ثبتِ پیام ذخیره می‌شود",
      _APSRC.find("_chat_photo_save(t[\"id\"], uid, raw)")
      < _APSRC.find('db.chat_add(uid, "admin"'),
      "برعکسش یعنی ردیفی که به عکسِ ناموجود اشاره می‌کند")
# The customer's photo reaches the group from the mini app's chat (Pro).
if PRO:
    check("گروهِ مدیریت خودِ عکس را می‌بیند",
          "photo=blob" in _APSRC,
          "«عکس فرستاد» بدونِ عکس یعنی مالک باید پنل را باز کند")


# ═══════════════════════════════════════════════════════════
if PRO:        # sales partners are Pro (backend/pro/affiliates.py)
    head("همکار فروش · یک عدد، دو جا")

    # چرا این بخش: همکار حالا خودش مانده‌اش را می‌بیند. اگر آن عدد با
    # عددِ پنلِ مالک یکی نباشد، همان می‌شود موضوعِ بحث — و هیچ‌کدام
    # نمی‌توانند ثابت کنند حق با آن‌هاست.

    import tempfile as _tfa2                                  # noqa: E402
    import sqlite3 as _sqa                                    # noqa: E402
    from pathlib import Path as _Pa                           # noqa: E402

    _adir = _Pa(_tfa2.mkdtemp(prefix="nx-affx-"))
    _old_bot2 = app.BOT_DB
    try:
        _adb = _adir / "bot.db"
        _c = _sqa.connect(str(_adb))
        import sys as _sysa
        _sysa.path.insert(0, ".")
        from bot import db as _BDa
        _c.executescript(_BDa.SCHEMA)
        _BDa._migrate(_c)
        _c.execute("INSERT INTO tenants (id,name) VALUES (1,'owner')")
        _c.execute("INSERT INTO affiliates (id,tenant_id,name,code,percent) "
                   "VALUES (1,1,'رضا','AFF1',10)")
        _c.execute("INSERT INTO affiliates (id,tenant_id,name,code,percent) "
                   "VALUES (2,1,'سارا','AFF2',15)")
        for _u, _a in ((1, 1), (2, 1), (3, 2)):
            _c.execute("INSERT INTO users (id,tenant_id,tg_id,first_name,affiliate_id) "
                       "VALUES (?,1,?,?,?)", (_u, 7000 + _u, f"کاربر{_u}", _a))
        for _o, _u, _amt, _aff, _p in ((1, 1, 500000, 1, 10), (2, 2, 300000, 1, 10),
                                       (3, 3, 200000, 2, 15)):
            _c.execute("INSERT INTO orders (id,tenant_id,user_id,amount,base_amount,status) "
                       "VALUES (?,1,?,?,?, 'approved')", (_o, _u, _amt, _amt))
            _c.execute("INSERT INTO affiliate_commissions "
                       "(tenant_id,affiliate_id,order_id,user_id,order_amount,percent,commission) "
                       "VALUES (1,?,?,?,?,?,?)",
                       (_aff, _o, _u, _amt, _p, round(_amt * _p / 100)))
        _c.commit()
        app.BOT_DB = _adb

        # ── تسویه‌ی جزئی ──
        #
        # نسخه‌ی قبلی از مبلغِ همین پرداخت کم می‌کرد و وقتی به پورسانتی
        # می‌رسید که از باقی‌مانده بزرگ‌تر بود `break` می‌زد — باقی‌مانده
        # دور ریخته می‌شد و وضعیت‌ها با واقعیت جور درنمی‌آمد.
        check("مانده‌ی اولیه درست است", app._affiliate_balance(_c, 1) == 80000,
              str(app._affiliate_balance(_c, 1)))
        app.bot_affiliate_payout(1, {"amount": 60000}, x_admin_password=app._INTERNAL_PW)
        check("پرداختِ جزئی مانده را درست کم می‌کند",
              app._affiliate_balance(_c, 1) == 20000, str(app._affiliate_balance(_c, 1)))
        app.bot_affiliate_payout(1, {"amount": 20000}, x_admin_password=app._INTERNAL_PW)
        _st = [r[0] for r in _c.execute(
            "SELECT status FROM affiliate_commissions WHERE affiliate_id=1 ORDER BY id")]
        check("و بعد از تسویه‌ی کامل، هیچ پورسانتی pending نمی‌ماند",
              _st == ["paid", "paid"], "، ".join(_st))
        check("و مانده صفر می‌شود", app._affiliate_balance(_c, 1) == 0)

        # ── رمز و ورود ──
        class _Rq:
            client = type("C", (), {"host": "9.9.9.9"})()
            headers = {}

        app.bot_affiliate_password(1, {"password": "aff-secret"},
                                   x_admin_password=app._INTERNAL_PW)
        try:
            app.aff_login({"code": "AFF1", "password": "bad"}, _Rq())
            check("رمز غلط رد می‌شود", False, "پذیرفته شد")
        except app.HTTPException as _e:
            check("رمز غلط رد می‌شود", _e.status_code == 401, str(_e.status_code))

        # پیامِ «کد نیست» باید همان پیامِ «رمز غلط» باشد، وگرنه با
        # امتحان‌کردن می‌شود فهمید چه کدهایی وجود دارند
        try:
            app.aff_login({"code": "NOPE", "password": "x"}, _Rq())
            _d1 = ""
        except app.HTTPException as _e:
            _d1 = str(_e.detail)
        try:
            app.aff_login({"code": "AFF1", "password": "bad"}, _Rq())
            _d2 = ""
        except app.HTTPException as _e:
            _d2 = str(_e.detail)
        check("کدِ ناموجود و رمزِ غلط یک پیام می‌دهند", _d1 == _d2 and bool(_d1),
              "وگرنه می‌شود فهمید چه کدهایی هست")

        _tok = app.aff_login({"code": "aff1", "password": "aff-secret"}, _Rq())
        check("ورود با کدِ کوچک هم کار می‌کند", bool(_tok.get("token")))

        # ── مرز ──
        _sm = app.aff_summary(app.aff_session(_tok["token"]))
        check("همکار فقط مشتری‌های خودش را می‌بیند",
              all(u["first_name"] != "کاربر3" for u in _sm["users"]),
              "کاربر۳ مالِ همکارِ دیگر است")
        check("و فقط پورسانت‌های خودش را",
              all(c["order_id"] != 3 for c in _sm["commissions"]))

        # ── همان عدد ──
        _own = [a for a in app.bot_affiliates(x_admin_password=app._INTERNAL_PW)["affiliates"]
                if a["id"] == 1][0]
        check("مانده‌ی همکار با عددِ پنلِ مالک یکی است",
              _sm["balance"] == _own["balance"],
              f"همکار {_sm['balance']} ≠ مالک {_own['balance']}")

        # ── غیرفعال ──
        _c.execute("UPDATE affiliates SET active=0 WHERE id=1")
        _c.commit()
        try:
            app.aff_session(_tok["token"])
            check("همکارِ غیرفعال همان لحظه بیرون می‌رود", False, "هنوز باز است")
        except app.HTTPException as _e:
            check("همکارِ غیرفعال همان لحظه بیرون می‌رود", _e.status_code == 403,
                  str(_e.status_code))
        _c.close()
    finally:
        app.BOT_DB = _old_bot2

    # ── قواعدی که در کد بمانند ──
    _AFSRC = _APSRC[_APSRC.find("def aff_summary("):]
    _AFSRC = _AFSRC[:_AFSRC.find("\n@app.")]
    check("خلاصه‌ی همکار مانده را دوباره حساب نمی‌کند",
          "_affiliate_balance(con, aid)" in _AFSRC,
          "دو نسخه یعنی روزی دو عدد")
    check("و هر کوئری‌اش به خودِ همکار محدود است",
          _AFSRC.count("affiliate_id = ?") + _AFSRC.count("affiliate_id=?") >= 3,
          "بدون شرط، دادهٔ همکارِ دیگر هم می‌آید")
    # از ۱.۱۲۹ همکار درخواستِ تسویه می‌دهد و لغوش می‌کند — **فقط** همین دو. پول
    # ثبت نمی‌کند و درصد عوض نمی‌کند؛ مسیرِ نوشتنیِ سومی یعنی کسی دستش را بیش از
    # این باز کرده (docs/specs/2026-09-28-admin-path-and-aff-payouts.md).
    _AFF_WRITES_OK = ('@app.post("/api/aff/login")', '@app.post("/api/aff/logout")',
                      '@app.post("/api/aff/request")', '@app.post("/api/aff/request/{rid}/cancel")')
    _aff_rest = _APSRC
    for _w in _AFF_WRITES_OK:
        _aff_rest = _aff_rest.replace(_w, "")
    check("همکار جز درخواست و لغوِ تسویه هیچ مسیرِ نوشتنی ندارد",
          '@app.post("/api/aff/' not in _aff_rest and '@app.put("/api/aff/' not in _aff_rest
          and '@app.delete("/api/aff/' not in _aff_rest,
          "همکار پول ثبت نمی‌کند و درصد عوض نمی‌کند")
else:
    _PRO_SKIPPED.append('همکار فروش · یک عدد، دو جا')


# ═══════════════════════════════════════════════════════════
head("رمز پنل · هَش، و بدون قفل‌شدنِ کسی")

# چرا: `auth.json` خودِ رمز را داشت. هر کسی که آن فایل را می‌خواند
# — پشتیبانِ لو رفته، اسنپ‌شاتِ جابه‌جاشده — مستقیم به پنل، رمز
# x-ui، توکن ربات و داده‌ی همه‌ی مشتری‌ها می‌رسید.
#
# و خطرِ خودِ این تغییر، قفل‌شدنِ مالک پشتِ پنلِ خودش است. پس
# بیشترِ این تست‌ها دقیقاً همان را می‌سنجند.

import tempfile as _tfw                                   # noqa: E402
import json as _jsw                                       # noqa: E402
from pathlib import Path as _Pw                           # noqa: E402

_pwdir = _Pw(_tfw.mkdtemp(prefix="nx-pw-"))
_old_auth, _old_env = app.AUTH_PATH, app.ADMIN_PASSWORD
try:
    app.AUTH_PATH = _pwdir / "auth.json"
    app.ADMIN_PASSWORD = "env-secret"

    # ── نصبِ قدیمی، رمزِ متنِ ساده ──
    app.AUTH_PATH.write_text(_jsw.dumps({"password": "old-plain"}), encoding="utf-8")
    check("رمزِ متنِ سادهٔ قدیمی هنوز کار می‌کند", app.verify_password("old-plain"),
          "ردکردنش یعنی قفل‌شدنِ هر نصبی که از قبل هست")
    _body = app.AUTH_PATH.read_text(encoding="utf-8")
    check("و همان ورود، فایل را ارتقا می‌دهد",
          _jsw.loads(_body)["password"].startswith("pbkdf2_sha256$"))
    check("و متنِ ساده دیگر روی دیسک نیست", "old-plain" not in _body,
          "کلِ هدفِ این کار همین یک خط است")
    check("و بعد از ارتقا هنوز همان رمز می‌خورد", app.verify_password("old-plain"))
    check("رمزِ غلط رد می‌شود", not app.verify_password("nope"))

    # ── تغییر رمز ──
    app.save_password("a-new-password")
    check("رمزِ تازه کار می‌کند", app.verify_password("a-new-password"))
    check("و قبلی دیگر نه", not app.verify_password("old-plain"))
    check("و ذخیره‌شده هَش است",
          _jsw.loads(app.AUTH_PATH.read_text(encoding="utf-8"))["password"]
          .startswith("pbkdf2_sha256$"))

    # ── نصبِ تازه: فقط متغیر محیطی ──
    app.AUTH_PATH.unlink()
    check("رمزِ متغیر محیطی کار می‌کند", app.verify_password("env-secret"))

    # ── رمز فارسی ──
    #
    # `compare_digest` روی رشته‌ی غیراسکی TypeError می‌دهد؛ یک‌بار
    # همین کلِ پنل را با ۵۰۰ بست، نه فقط ورود را.
    app.save_password("رمزِ فارسیِ من")
    check("رمز فارسی کار می‌کند", app.verify_password("رمزِ فارسیِ من"))
    check("و رمزِ فارسیِ غلط رد می‌شود", not app.verify_password("رمز دیگر"))

    # ── فایلِ خراب نباید در را باز بگذارد ──
    app.AUTH_PATH.write_text("{ خراب", encoding="utf-8")
    check("فایلِ خراب، پنل را باز نمی‌گذارد", not app.verify_password("anything"),
          "برگشت به متغیر محیطی، نه پذیرفتنِ هر چیزی")
    check("ولی رمزِ محیطی هنوز کار می‌کند", app.verify_password("env-secret"))

    # ── نشانه‌ی درونی ──
    check("نشانه‌ی درونی قابلِ حدس نیست", len(app._INTERNAL_PW) > 40)
    check("و پیشوندش به‌تنهایی در را باز نمی‌کند",
          not app.verify_password("internal:"))
finally:
    app.AUTH_PATH, app.ADMIN_PASSWORD = _old_auth, _old_env

# ── قواعدی که باید در کد بمانند ──
check("ذخیره همیشه هَش می‌نویسد", "_pw_hash(new_password)" in _APSRC,
      "اگر یک‌جا متنِ ساده بنویسد، همان یک نصب لو می‌رود")
check("و PBKDF2 است نه هَشِ ساده", "pbkdf2_hmac" in _APSRC,
      "SHAی خالی سریع است، و سرعت همان چیزی است که حدس‌زننده می‌خواهد")
check("تعدادِ تکرار کم نیست", app.PW_ITERS >= 100_000, str(app.PW_ITERS))
check("مقایسه زمان‌ثابت است", "compare_digest" in _APSRC)

# هیچ‌جا نباید مقدارِ ذخیره‌شده را مستقیم با ورودی مقایسه کند
check("مقایسه‌ی خام با load_password نمانده",
      "!= load_password()" not in _APSRC and "== load_password()" not in _APSRC,
      "با هَش‌شدن، مقایسه‌ی مستقیم همیشه غلط می‌شود")
check("و رمزِ ذخیره‌شده به عنوان هدر پاس داده نمی‌شود",
      "x_admin_password=load_password()" not in _APSRC,
      "آن مسیر با هَش‌شدن بی‌صدا می‌شکست")


# ═══════════════════════════════════════════════════════════
head("تنظیمات روی دیتابیس · نه نصفه، نه بی‌صدا، نه پاک‌شده")

# چرا این بخش: تنظیمات در یک فایل JSON بود که (۱) اتمی نوشته
# نمی‌شد، (۲) وقتی خراب می‌شد بی‌صدا به پیش‌فرض برمی‌گشت — یعنی
# برند و پالت و فهرست نماینده‌ها پاک می‌شد و هیچ‌جا نمی‌گفت چرا —
# و (۳) آخرین ذخیره کارِ بقیه را می‌برد.

import tempfile as _tfc                                   # noqa: E402
import sqlite3 as _sqc                                     # noqa: E402
import json as _jsc                                        # noqa: E402
from pathlib import Path as _Pc                            # noqa: E402

_cdir = _Pc(_tfc.mkdtemp(prefix="nx-cfgt-"))
_old_bot, _old_cfg = app.BOT_DB, app.CONFIG_PATH
_old_ready = app._CFG_READY
try:
    app.BOT_DB = _cdir / "bot.db"
    app.CONFIG_PATH = _cdir / "config.json"
    app._CFG_READY = False
    app._CFG_LOCAL = __import__("threading").local()
    app._CFG_CACHE["version"] = None

    # ── مهاجرت ──
    app.CONFIG_PATH.write_text(_jsc.dumps({
        "links": {"channelUsername": "old_chan"},
        "resellers": [{"name": "حسین", "slug": "hossein", "enabled": True}],
        "theme": "emerald",
    }, ensure_ascii=False), encoding="utf-8")

    _c1 = app.load_config()
    check("از config.json مهاجرت می‌کند",
          _c1["links"].get("channelUsername") == "old_chan",
          str(_c1["links"].get("channelUsername")))
    check("و نماینده‌ها با آن می‌آیند",
          [r["name"] for r in _c1.get("resellers", [])] == ["حسین"])
    check("و مهاجرتِ قالبِ قدیمی هنوز کار می‌کند",
          _c1.get("template") == "classic" and _c1.get("palette") == "forest",
          f"{_c1.get('template')}/{_c1.get('palette')}")
    check("و فایل پاک نمی‌شود", app.CONFIG_PATH.exists(),
          "فایل پشتیبانِ مالک است؛ پاک‌کردنش راهِ برگشت را می‌بندد")

    # ── رفت‌وبرگشت ──
    _c1["links"]["channelUsername"] = "new_chan"
    _v = app.save_config(_c1)
    check("ذخیره نسخه را جلو می‌برد", _v == 2, str(_v))
    check("و خواندنِ دوباره همان را می‌دهد",
          app.load_config()["links"]["channelUsername"] == "new_chan")

    # ── دو تبِ باز ──
    _ver = app.config_version()
    app.save_config(app.load_config())          # تبِ اول
    try:
        app.save_config(app.load_config(), expected_version=_ver)
        check("ذخیره‌ی کهنه رد می‌شود", False, "پذیرفته شد — کارِ تبِ اول پاک شد")
    except app.HTTPException as _e:
        check("ذخیره‌ی کهنه رد می‌شود", _e.status_code == 409, str(_e.status_code))

    # ── خرابیِ عمدی ──
    #
    # این مهم‌ترین تستِ این بخش است: رفتارِ قبلی «بی‌صدا پیش‌فرض»
    # بود، که از خطا بدتر است چون پنل سالم به نظر می‌رسد.
    _cc = _sqc.connect(str(app.BOT_DB))
    _cc.execute("UPDATE panel_config SET body='{این JSON نیست' WHERE id=1")
    _cc.commit(); _cc.close()
    app._CFG_CACHE["version"] = None
    _back = app.load_config()
    check("بدنه‌ی خراب از تاریخچه ترمیم می‌شود",
          _back["links"].get("channelUsername") == "new_chan",
          "پیش‌فرض یعنی تنظیماتِ مالک بی‌صدا پاک شد")

    # ── تاریخچه و برگشت ──
    _h = app.config_history()
    check("تاریخچه نسخه‌ها را نگه می‌دارد", len(_h) >= 2, f"{len(_h)} نسخه")
    _target = [x for x in _h if x["version"] == 1]
    if _target:
        _rb = app.config_rollback(1)
        check("برگشت به نسخه‌ی قبل مقدارِ همان را می‌دهد",
              _rb["links"].get("channelUsername") == "old_chan",
              str(_rb["links"].get("channelUsername")))
        check("و خودِ برگشت هم یک نسخه‌ی تازه است",
              app.config_version() > 1, str(app.config_version()))
    check("نسخه‌ی ناموجود خطای تمیز می‌دهد", True)
    try:
        app.config_rollback(9999)
        check("نسخه‌ی ناموجود رد می‌شود", False, "پذیرفته شد")
    except app.HTTPException as _e:
        check("نسخه‌ی ناموجود رد می‌شود", _e.status_code == 404, str(_e.status_code))
finally:
    app.BOT_DB, app.CONFIG_PATH = _old_bot, _old_cfg
    app._CFG_READY = _old_ready
    app._CFG_LOCAL = __import__("threading").local()
    app._CFG_CACHE["version"] = None

# ── قواعدی که باید در کد بمانند ──
_CSRC = _APSRC[_APSRC.find("def save_config("):]
_CSRC = _CSRC[:_CSRC.find("def config_history")]
check("ذخیره پیش از نوشتن ادعا می‌کند", "BEGIN IMMEDIATE" in _CSRC,
      "تراکنشِ deferred یعنی دو نویسنده هر دو نسخه‌ی N را می‌خوانند")
check("و نسخه‌ی قبلی در تاریخچه می‌نشیند",
      "INSERT INTO panel_config_history" in _CSRC)

_LSRC = _APSRC[_APSRC.find("def _cfg_raw("):]
_LSRC = _LSRC[:_LSRC.find("def config_version")]
check("خرابی لاگِ بلند دارد", "log.error" in _LSRC,
      "بی‌صدا برگشتن به پیش‌فرض همان باگی است که این بخش برایش نوشته شد")

check("هدرِ نسخه از CORS بیرون داده می‌شود",
      'expose_headers=["X-Config-Version"]' in _APSRC,
      "وگرنه در حالت cross-origin نامرئی است و محافظ بی‌صدا از کار می‌افتد")


# ═══════════════════════════════════════════════════════════
head("هشدارها · فقط مالِ خودِ مالک")

# چرا این تست: کوئریِ هشدارها هیچ `tenant_id` نداشت، پس رسیدِ
# مشتریِ *نماینده* هم به مالک هشدار می‌داد — کاری که اصلاً مالِ او
# نیست و نماینده خودش باید جوابش را بدهد. همان دامِ
# «FROM … بدون شرط» که در این مخزن پنج بار پیدا شد.
_ASRC = _APSRC[_APSRC.find("def admin_alerts("):]
_ASRC = _ASRC[:_ASRC.find("\n@app.")]
check("هشدارها به مستاجرِ ریشه محدودند", "_root_tenant_row()" in _ASRC,
      "وگرنه رسیدِ نماینده هم به مالک هشدار می‌دهد")
check("و کوئری‌ها شرطِ مستاجر دارند",
      _ASRC.count("tenant_id = ?") >= 2 or _ASRC.count("tenant_id=?") >= 2,
      "شمارشِ بدون شرط، عددِ کسِ دیگری را نشان می‌دهد")

# «چقدر منتظر مانده» همان چیزی است که دیرشدن را نشان می‌دهد؛ بدون
# آن، فهرست فقط می‌گوید چند تا، نه کدام دارد دیر می‌شود
check("چقدر منتظر مانده را برمی‌گرداند", '"waitedMin"' in _ASRC)
check("و قدیمی‌ترین اول می‌آید", 'key=lambda x: -x["waitedMin"]' in _ASRC,
      "تازه‌ترین اول یعنی آنکه دیر شده ته فهرست گم می‌شود")
check("و نامِ فرستنده هم می‌آید", '"name": who(r)' in _ASRC,
      "«۲ رسید» نمی‌گوید کیست")


# ═══════════════════════════════════════════════════════════
head("پروفایلِ مشتری · واقعاً می‌نشیند")

# چرا رفت‌وبرگشتِ کامل و نه فقط خواندنِ کد: مالک گزارش داد که
# پروفایل ذخیره نمی‌شود. هر لایه جدا درست بود؛ تنها چیزی که
# می‌توانست جواب بدهد، نوشتن و بعد *خواندنِ دوباره* بود.
import tempfile as _tfp                                  # noqa: E402
import sqlite3 as _sq3                                   # noqa: E402
from pathlib import Path as _Pp                          # noqa: E402

_pdb = _Pp(_tfp.mkdtemp(prefix="nx-prof-")) / "bot.db"
_old_db = app.BOT_DB
try:
    import sys as _sys
    _sys.path.insert(0, ".")
    from bot import db as _BD
    _c = _sq3.connect(str(_pdb))
    _c.executescript(_BD.SCHEMA)
    _c.execute("INSERT OR IGNORE INTO tenants (id, name) VALUES (1,'owner')")
    _c.execute("INSERT INTO users (tenant_id, tg_id, first_name) VALUES (1, 555, 'Ali')")
    _c.commit()
    _uid = _c.execute("SELECT id FROM users WHERE tg_id=555").fetchone()[0]

    if PRO:
        app.BOT_DB = _pdb
        _t = {"id": 1, "name": "x"}
        _u = {"id": _uid, "first_name": "Ali", "phone": ""}
        _out = app.mini_profile_save({"name": "علی رضایی", "phone": "09058676388"}, (_t, _u))
        check("ذخیره پاسخِ موفق می‌دهد", _out.get("ok") is True, str(_out)[:60])

        _row = _c.execute("SELECT first_name, phone FROM users WHERE id=?", (_uid,)).fetchone()
        check("و نام واقعاً در دیتابیس نشست", _row[0] == "علی رضایی", str(_row[0]))
        check("و شماره هم نشست", _row[1] == "09058676388", str(_row[1]))

        # نامِ خالی نباید نامِ قبلی را پاک کند
        app.mini_profile_save({"name": "", "phone": ""}, (_t, _u))
        _row2 = _c.execute("SELECT first_name, phone FROM users WHERE id=?", (_uid,)).fetchone()
        check("و ارسالِ خالی، چیزی را پاک نمی‌کند",
              _row2[0] == "علی رضایی" and _row2[1] == "09058676388", str(_row2))

        # شماره‌ی بی‌ربط باید رد شود، نه اینکه ستون را خراب کند
        try:
            app.mini_profile_save({"name": "", "phone": "سلام!!"}, (_t, _u))
            check("شماره‌ی بی‌ربط رد می‌شود", False, "پذیرفته شد")
        except app.HTTPException as _e:
            check("شماره‌ی بی‌ربط رد می‌شود", _e.status_code == 400, str(_e.status_code))
    _c.close()
finally:
    app.BOT_DB = _old_db


# ═══════════════════════════════════════════════════════════
head("عکس پروفایل · نامِ فایل خودش کلید است")

import base64 as _b64a                                 # noqa: E402
import tempfile as _tfa                                # noqa: E402
app.AVATAR_DIR = Path(_tfa.mkdtemp(prefix="nx-av-"))

_PNG_A = _b64a.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

_u1 = app._avatar_save(7, 11, _b64a.b64encode(_PNG_A).decode())
check("عکس ذخیره می‌شود", _u1.startswith("/api/public/avatar/"), _u1)

# نام نباید قابلِ حدس باشد: `7_11.png` یعنی هر کسی با شمردنِ
# شناسه‌ها عکسِ هر مشتری را برمی‌دارد.
_fname = _u1.rsplit("/", 1)[-1]
check("و نامش قابلِ حدس نیست", _fname not in ("7_11.png", "11.png")
      and len(_fname) > 18, _fname)

check("و دوباره پیدا می‌شود", app._avatar_url(7, 11) == _u1, app._avatar_url(7, 11))

# عکسِ تازه، قبلی را پاک می‌کند — وگرنه پوشه پر می‌شود از عکس‌های
# مرده که هیچ‌کس نمی‌داند مالِ کیست
_u2 = app._avatar_save(7, 11, _b64a.b64encode(_PNG_A).decode())
_left = sorted(p.name for p in app.AVATAR_DIR.glob("7_11_*"))
check("و فقط یکی می‌ماند", len(_left) == 1, "، ".join(_left))
check("و نشانی عوض می‌شود", _u2 != _u1, f"{_u1} → {_u2}")

# فرمت
for _name, _blob in (("SVG", b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'),
                     ("متن", b"hello there, not a picture")):
    try:
        app._avatar_save(7, 12, _b64a.b64encode(_blob).decode())
        check(f"{_name} رد می‌شود", False, "پذیرفته شد")
    except app.HTTPException as _e:
        check(f"{_name} رد می‌شود", _e.status_code == 400, str(_e.status_code))

# سقف
try:
    app._avatar_save(7, 13, "A" * (900 * 1024))
    check("عکسِ بزرگ رد می‌شود", False, "پذیرفته شد")
except app.HTTPException as _e:
    check("عکسِ بزرگ رد می‌شود", _e.status_code == 413, str(_e.status_code))

# مسیرِ خطرناک — با فایلِ واقعی، وگرنه تست بی‌خود سبز می‌ماند
_out = app.AVATAR_DIR.parent / "hidden.png"
_out.write_bytes(_PNG_A)
_BAD = ["../hidden.png", "a/b.png"]
_BAD.append(".." + chr(92) + "hidden.png")
try:
    for _b in _BAD:
        try:
            app.public_avatar(_b)
            check("مسیرِ خطرناک رد می‌شود (%s)" % _b[:14], False, "سرو شد")
        except app.HTTPException as _e:
            check("مسیرِ خطرناک رد می‌شود (%s)" % _b[:14],
                  _e.status_code == 404, str(_e.status_code))
finally:
    try:
        _out.unlink()
    except OSError:
        pass

# پاک‌کردن
app._avatar_clear(7, 11)
check("بعد از پاک‌کردن، نشانی خالی است", app._avatar_url(7, 11) == "")

if PRO:
    # و نوشتن باید از mini_user بگذرد، خواندن نه
    _ps = _APSRC[_APSRC.find("def mini_avatar_set("):]
    _ps = _ps[:_ps.find("def mini_avatar_clear")]
    check("نوشتنِ عکس پشتِ احراز هویت است", "Depends(mini_user)" in _ps,
          "وگرنه هر کسی عکسِ هر کسی را عوض می‌کند")
    check("و شناسه از نشست می‌آید نه از بدنه",
          '_avatar_save(t["id"], u["id"]' in _ps,
          "شناسه‌ی آمده از بدنه یعنی نوشتن روی پروفایل دیگری")
else:
    _PRO_SKIPPED.append('mini app: avatar write is behind mini_user')


# ═══════════════════════════════════════════════════════════
head("رسیدِ تصویری · گم نشود، حتی بدون گروه تلگرام")

import base64 as _b64r                                 # noqa: E402
import tempfile as _tf2                                # noqa: E402
app.RECEIPT_DIR = Path(_tf2.mkdtemp(prefix="nx-rcpt-"))

# کوچک‌ترین PNG معتبر (۱×۱ شفاف)
_PNG_R = _b64r.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

_ref = app._receipt_save(4242, _PNG_R)
check("رسید روی دیسک ذخیره می‌شود", bool(_ref), str(_ref))
check("و ارجاعش «محلی» علامت می‌خورد",
      str(_ref).startswith("local:"), str(_ref))

_p = app._receipt_local(_ref)
check("و دوباره پیدا می‌شود", _p is not None and _p.exists(), str(_p))

# چیزی که تصویر نیست، ذخیره نمی‌شود
check("متن به‌جای تصویر رد می‌شود",
      app._receipt_save(4243, b"not an image at all") is None)

# ارجاعِ تلگرامی نباید به دیسک نگاه کند
check("ارجاع تلگرامی محلی شمرده نمی‌شود",
      app._receipt_local("BAADBAADrwADBREAAX") is None)

# و مسیرِ آمده از بیرون نباید از پوشه بیرون بزند.
#
# فایلِ هدف را واقعاً می‌سازیم: بدون آن، `p.exists()` خودش False
# می‌شود و تست *به دلیل اشتباه* سبز می‌ماند — یعنی برداشتنِ
# نگهبان هم قرمزش نمی‌کند.
_outside = app.RECEIPT_DIR.parent / "secret.png"
_outside.write_bytes(_PNG_R)
(app.RECEIPT_DIR / "sub").mkdir(exist_ok=True)
(app.RECEIPT_DIR / "sub" / "b.png").write_bytes(_PNG_R)
_EVIL = ["local:../secret.png", "local:sub/b.png"]
_EVIL.append("local:.." + chr(92) + "secret.png")
try:
    for _evil in _EVIL:
        check("مسیرِ خطرناک رد می‌شود (%s)" % _evil[6:22],
              app._receipt_local(_evil) is None,
              "فایلِ هدف واقعاً وجود دارد، پس این تست بی‌خود سبز نمی‌شود")
finally:
    try:
        _outside.unlink()
    except OSError:
        pass

# ── و مهم‌ترین چیز: `mini_receipt` باید *اول* روی دیسک بگذارد ──
#
# نسخه‌ی اول عکس را فقط به گروه مدیریت آپلود می‌کرد. بدون گروه،
# `receipt_file` خالی می‌ماند در حالی که `receipt_type` هنوز "photo"
# بود — پنل ۴۰۴ می‌داد و عکس برای همیشه گم می‌شد.
if PRO:
    _mr = _APSRC[_APSRC.find("def mini_receipt("):]
    _mr = _mr[:_mr.find("def _mini_own_order")]
    _mr_code = "\n".join(l for l in _mr.split("\n")
                         if not l.strip().startswith("#"))
    check("mini_receipt اول روی دیسک می‌نویسد",
          "_receipt_save(oid, blob)" in _mr_code,
          "وگرنه بدون گروه تلگرام، عکس گم می‌شود")
    check("و همان ارجاع را به هسته می‌دهد",
          "rfile=local_ref" in _mr_code,
          "اگر ندهد، هسته فقط file_id تلگرام را ذخیره می‌کند")
else:
    _PRO_SKIPPED.append('mini app: receipt goes to disk first')

# و هسته نباید ارجاعِ محلی را با file_id عوض کند
_H2 = io.open(os.path.join(str(ROOT), "bot", "handlers.py"),
              encoding="utf-8").read()
_rs = _H2[_H2.find("def receipt_submit("):]
_rs = _rs[:_rs.find("def _receipt_caption")]
check("هسته ارجاع محلی را جایگزین نمی‌کند",
      "if uploaded and not rfile:" in _rs,
      "وگرنه همان وابستگی برمی‌گردد که باعث گم‌شدن رسید شده بود")


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("لوگوی برند · فقط تصویر، و فقط مالِ خودت")

    import base64 as _b64                                  # noqa: E402
    import tempfile as _tf                                 # noqa: E402

    app.LOGO_DIR = Path(_tf.mkdtemp(prefix="nx-logo-"))

    # کوچک‌ترین PNG معتبر (۱×۱ شفاف)
    _PNG = _b64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    _JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
    _WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 30

    # SVG عمداً باید رد شود: می‌تواند <script> داشته باشد و از دامنه‌ی
    # خودِ ما سرو می‌شود — یعنی XSS روی پنل.
    _SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


    def _put(blob, tid=None, raw=None):
        data = raw if raw is not None else _b64.b64encode(blob).decode()
        return app.tenant_logo_set(tid if tid is not None else tid_root,
                                   {"data": data}, x_admin_password=PW)


    # مستاجرِ ریشه برای تست
    tid_root = tid

    for _name, _blob in (("PNG", _PNG), ("JPEG", _JPG), ("WebP", _WEBP)):
        try:
            _r = _put(_blob)
            check(f"{_name} پذیرفته می‌شود", _r.get("ok"), str(_r))
        except Exception as _e:
            check(f"{_name} پذیرفته می‌شود", False, str(_e)[:80])

    for _name, _blob in (("SVG", _SVG), ("متن ساده", b"just text, not an image")):
        try:
            _put(_blob)
            check(f"{_name} رد می‌شود", False, "پذیرفته شد — نباید")
        except app.HTTPException as _e:
            check(f"{_name} رد می‌شود", _e.status_code == 400, str(_e.status_code))

    # سقفِ حجم — و باید *قبل* از دیکد بگیرد
    try:
        _put(None, raw="A" * (900 * 1024))
        check("فایل بزرگ رد می‌شود", False, "پذیرفته شد")
    except app.HTTPException as _e:
        check("فایل بزرگ رد می‌شود", _e.status_code == 413, str(_e.status_code))

    # فقط یک فایل باید بماند، نه سه‌تا با پسوندهای مختلف
    _put(_PNG)
    _files = sorted(p.name for p in app.LOGO_DIR.glob(f"{tid_root}.*"))
    check("فقط یک فایل برای هر مستاجر می‌ماند", len(_files) == 1, "، ".join(_files))

    # سرو
    _resp = app.public_logo(tid_root)
    check("لوگو سرو می‌شود", _resp.media_type == "image/png", str(_resp.media_type))
    check("و کش دارد", "max-age" in (_resp.headers.get("cache-control") or ""),
          str(_resp.headers.get("cache-control")))

    # مستاجرِ نبوده
    try:
        app.tenant_logo_set(999999, {"data": _b64.b64encode(_PNG).decode()},
                            x_admin_password=PW)
        check("مستاجرِ ناموجود رد می‌شود", False, "پذیرفته شد")
    except app.HTTPException as _e:
        check("مستاجرِ ناموجود رد می‌شود", _e.status_code == 404, str(_e.status_code))

    # پاک‌کردن
    app.tenant_logo_clear(tid_root, x_admin_password=PW)
    check("بعد از پاک‌کردن، نشانی خالی است", app._logo_url(tid_root) == "",
          app._logo_url(tid_root) or "خالی")
    try:
        app.public_logo(tid_root)
        check("و سرو هم ۴۰۴ می‌دهد", False, "هنوز سرو می‌شود")
    except app.HTTPException as _e:
        check("و سرو هم ۴۰۴ می‌دهد", _e.status_code == 404, str(_e.status_code))

    # نماینده فقط مالِ خودش — شناسه از نشست می‌آید نه از بدنه
    _psrc = _APSRC[_APSRC.find("def portal_logo_set("):]
    _psrc = _psrc[:_psrc.find("@app.delete")]
    check("مسیر نماینده شناسه را از بدنه نمی‌گیرد",
          '_logo_save(t["id"]' in _psrc and "payload.get(\"tid\")" not in _psrc,
          "وگرنه فرستادنِ شناسه‌ی دیگری کافی است تا لوگوی او عوض شود")
else:
    _PRO_SKIPPED.append('لوگوی برند · فقط تصویر، و فقط مالِ خودت')


# ═══════════════════════════════════════════════════════════
head("مینی‌اپ · ربات باید مسیر مستقل بماند")

# مشتری‌های ما همان کسانی‌اند که اینترنتشان محدود است. اگر دامنه بالا
# نیاید، مینی‌اپ صفحه‌ی سفید می‌شود و تلگرام چیزی نمی‌گوید. پس هر
# کاری که از مینی‌اپ می‌شود کرد باید از منوی ربات هم بشود.
_H = io.open(os.path.join(str(ROOT), "bot", "handlers.py"),
             encoding="utf-8").read()

# داخل خودِ main_menu، نه هرجای فایل: همین متن‌ها در حالت‌های خالی
# هم به کار رفته‌اند و شکستنِ عمدی نشان داد حذفشان از منو گرفته
# نمی‌شود
_menu = _H[_H.find("def main_menu("):]
_menu = _menu[:_menu.find(chr(10) + "def ", 10)]
for _must in ("🛒 خرید اشتراک", "📊 اشتراک‌های من", "👛 کیف پول"):
    check("دکمه‌ی «%s» هنوز در منوی ربات هست" % _must.split(" ", 1)[-1],
          _must in _menu, "مینی‌اپ اضافه است، نه جایگزین")

# آدرس مینی‌اپ باید خودش پیدا شود، نه اینکه منتظر بماند کسی پرش کند.
#
# تنظیمی که باید آدم انجامش بدهد، انجام نمی‌شود — و آن‌وقت قابلیتی
# داریم که ساخته شده و هیچ‌کس نمی‌بیندش. همان چیزی که سر پنل
# نمایندگی افتاد و سر اینباند پیش‌فرض.
#
# راهش این است: اولین باری که مدیر پنل را روی https باز می‌کند،
# بک‌اند دامنه‌ی خودش را از هدر Host می‌بیند و آدرس را ثبت می‌کند.


class _Req:
    def __init__(self, **h):
        self.headers = h


def _stored_mini():
    _c = _sq3.connect(str(AP.BOT_DB))
    _c.row_factory = _sq3.Row
    _r = _c.execute("SELECT settings FROM tenants WHERE parent_id IS NULL "
                    "ORDER BY id LIMIT 1").fetchone()
    _c.close()
    try:
        return json.loads(_r["settings"] or "{}").get("miniapp_url") or ""
    except Exception:
        return ""


def _clear_mini():
    _c = _sq3.connect(str(AP.BOT_DB))
    _c.row_factory = _sq3.Row
    _r = _c.execute("SELECT id, settings FROM tenants WHERE parent_id IS NULL "
                    "ORDER BY id LIMIT 1").fetchone()
    _st = json.loads(_r["settings"] or "{}")
    _st.pop("miniapp_url", None)
    _c.execute("UPDATE tenants SET settings=? WHERE id=?",
               (json.dumps(_st, ensure_ascii=False), _r["id"]))
    _c.commit()
    _c.close()


_clear_mini()
AP._learn_panel_origin(_Req(host="panel.example.com",
                            **{"x-forwarded-proto": "https"}))
check("بازکردن پنل، آدرس مینی‌اپ را خودش ثبت می‌کند",
      _stored_mini() == "https://panel.example.com/app",
      _stored_mini() or "(هیچ) — قابلیتی که کسی نمی‌بیندش")

_clear_mini()
AP._learn_panel_origin(_Req(host="panel.example.com:8443",
                            **{"x-forwarded-proto": "https"}))
check("پورت هم نگه داشته می‌شود",
      _stored_mini() == "https://panel.example.com:8443/app", _stored_mini())

# هدر Host را فرستنده تعیین می‌کند. اگر بی‌شرط ثبتش کنیم، کسی
# می‌تواند مینی‌اپِ مشتری‌ها را به صفحه‌ی خودش ببرد.
for _h, _why in ((("http"), "بدون https"), ((""), "بدون هدر proto")):
    _clear_mini()
    AP._learn_panel_origin(_Req(host="panel.example.com",
                                **({"x-forwarded-proto": _h} if _h else {})))
    check("%s چیزی ثبت نمی‌کند" % _why, _stored_mini() == "",
          "تلگرام هم http را رد می‌کند؛ ثبتش فقط مقدار مرده می‌سازد")

# و بدون آن هدر هم باید کار کند.
#
# نسخه‌ی اول فقط x-forwarded-proto را می‌خواند و روی نصب‌های واقعی
# هیچ‌وقت ثبت نشد: بلوک nginx خودمان آن هدر را جلو نمی‌فرستاد، پس
# درخواست به شکل http می‌رسید و شرط همیشه رد می‌شد. مالک آخرین نسخه
# را نصب کرد و هیچ دکمه‌ای ندید.
_clear_mini()
AP._learn_panel_origin(_Req(host="panel.example.com",
                            referer="https://panel.example.com/"))
check("بدون هدر پروکسی هم، از نوار آدرسِ مرورگر یاد می‌گیرد",
      _stored_mini() == "https://panel.example.com/app",
      _stored_mini() or "(هیچ) — همان چیزی که روی سرور واقعی افتاد")

_clear_mini()
AP._learn_panel_origin(_Req(host="10.0.0.5:8100",
                            referer="https://panel.example.com:8443/#/x"))
check("و دامنه را از خودِ Referer می‌گیرد، نه از Host",
      _stored_mini() == "https://panel.example.com:8443/app", _stored_mini())

_clear_mini()
AP._learn_panel_origin(_Req(host="panel.example.com",
                            origin="https://panel.example.com"))
check("هدر Origin هم پذیرفته است",
      _stored_mini() == "https://panel.example.com/app", _stored_mini())

# ولی http در هیچ شکلی قبول نیست — تلگرام خودِ پیام را رد می‌کند
_clear_mini()
AP._learn_panel_origin(_Req(host="panel.example.com",
                            referer="http://panel.example.com/"))
check("Refererِ http چیزی ثبت نمی‌کند", _stored_mini() == "",
      "وگرنه دکمه‌ای می‌ساخت که کل منوی ربات را از کار می‌اندازد")

_clear_mini()
AP._learn_panel_origin(_Req(host="panel.example.com",
                            referer="https://good.ir@evil.com/x"))
check("Refererِ آلوده هم رد می‌شود", _stored_mini() == "",
      "@ در آدرس یعنی هاستِ واقعی چیز دیگری است")

# و همان قاعده در nginx هم باید نوشته باشد، وگرنه نصب تازه دوباره
# همان‌جا می‌ماند
_INST = io.open(os.path.join(str(ROOT), "install.sh"), encoding="utf-8").read()
check("nginx هم هدر پروتکل را جلو می‌فرستد",
      _INST.count("X-Forwarded-Proto") >= 3,
      "%d بلوک — ریشه‌ی خودِ باگ" % _INST.count("X-Forwarded-Proto"))

# ولی `install.sh` فقط نصبِ **تازه** را درست می‌کند. نصبی که پیش از
# آن اصلاح بالا آمده، فایلِ قدیمی را دارد و تا ابد این باگ را
# خواهد داشت — مگر اینکه به‌روزرسانی تعمیرش کند.
#
# روی سرورِ واقعیِ مالک دقیقاً همین شد: آدرس مینی‌اپ هیچ‌وقت ثبت
# نشد و دکمه در هیچ رباتی ظاهر نشد.
_FIXNG = io.open(os.path.join(str(ROOT), "scripts/fix-nginx-cache.py"),
                 encoding="utf-8").read()
check("به‌روزرسانی نصب‌های قدیمی را هم تعمیر می‌کند",
      "X-Forwarded-Proto" in _FIXNG and "def add_proto(" in _FIXNG,
      "نصبِ موجود فایلِ قدیمی را دارد")

_CLI = io.open(os.path.join(str(ROOT), "nexora-cli.sh"),
               encoding="utf-8").read()
check("و آن تعمیر در هر به‌روزرسانی اجرا می‌شود",
      "scripts/fix-nginx-cache.py" in _CLI,
      "تعمیری که صدا زده نشود، وجود ندارد")

# فشرده‌سازی: nginx پیش‌فرض فقط html را فشرده می‌کند. ~۷۰۰ کیلوبایت JS/CSS
# روی اینترنتِ قطع‌ووصل وسطِ راه می‌ماند و مینی‌اپ پشتِ اسپلش می‌ایستاد —
# مالک و نماینده هر دو دیدند. رفتار سنجیده می‌شود، نه متن: خودِ اسکریپت روی
# یک پیکربندیِ قدیمیِ دوبلوکی اجرا می‌شود.
import subprocess as _sp9                                    # noqa: E402
_ngd = tempfile.mkdtemp(prefix="ng_")
_ngf = os.path.join(_ngd, "nexora-panel.conf")
_old_conf = ("server {\n    listen 80;\n    location / { try_files $uri /index.html; }\n"
             "    location /api/ {\n        proxy_pass http://127.0.0.1:8100;\n"
             "        proxy_set_header Host $host;\n    }\n}\n") * 2
io.open(_ngf, "w", encoding="utf-8").write(_old_conf)
# PATH بی‌nginx: ماشینِ CI (اوبونتوی گیت‌هاب) nginx دارد و `nginx -t` ِ
# بی‌روت آن‌جا شکست می‌خورد، پس اسکریپت درست رفتار می‌کرد و پیکربندی را
# برمی‌گرداند — و این تست «۰ بلوک» می‌دید. روی سرور با روت اجرا می‌شود.
_ngenv = dict(os.environ, PATH=os.path.dirname(sys.executable))
_sp9.run([sys.executable, os.path.join(str(ROOT), "scripts/fix-nginx-cache.py"), _ngf],
         capture_output=True, timeout=60, env=_ngenv)
_new_conf = io.open(_ngf, encoding="utf-8").read()
check("به‌روزرسانی JS/CSS را فشرده می‌کند — در هر دو بلوک",
      _new_conf.count("gzip_types") == 2 and "application/javascript" in _new_conf,
      "%d بلوک" % _new_conf.count("gzip_types"))
_sp9.run([sys.executable, os.path.join(str(ROOT), "scripts/fix-nginx-cache.py"), _ngf],
         capture_output=True, timeout=60, env=_ngenv)
check("اجرای دوباره چیزی را تکرار نمی‌کند",
      io.open(_ngf, encoding="utf-8").read().count("gzip_types") == 2)
check("نصبِ تازه هم فشرده می‌فرستد (هر سه قالبِ install.sh)",
      _INST.count("gzip_types") == 3, "%d" % _INST.count("gzip_types"))

_clear_mini()
AP._learn_panel_origin(_Req(host="evil.com/x?a=b",
                            **{"x-forwarded-proto": "https"}))
check("هاستِ آلوده ثبت نمی‌شود", _stored_mini() == "",
      "وگرنه مینی‌اپِ مشتری به صفحه‌ی دیگری می‌رفت")

_clear_mini()
_c9 = _sq3.connect(str(AP.BOT_DB))
_c9.row_factory = _sq3.Row
_r9 = _c9.execute("SELECT id, settings FROM tenants WHERE parent_id IS NULL "
                  "ORDER BY id LIMIT 1").fetchone()
_s9 = json.loads(_r9["settings"] or "{}")
_s9["miniapp_url"] = "https://my.own.example.com/app"
_c9.execute("UPDATE tenants SET settings=? WHERE id=?",
            (json.dumps(_s9, ensure_ascii=False), _r9["id"]))
_c9.commit()
_c9.close()
AP._learn_panel_origin(_Req(host="panel.example.com",
                            **{"x-forwarded-proto": "https"}))
check("و انتخابِ خودِ مالک را بازنویسی نمی‌کند",
      _stored_mini() == "https://my.own.example.com/app", _stored_mini())

# و واقعاً از مسیر API صدا زده می‌شود.
#
# تست‌های بالا تابع را مستقیم صدا می‌زنند، پس اگر فراخوانی از خودِ
# نقطه‌ی API برداشته شود همه‌شان سبز می‌مانند — شکستنِ عمدی همین را
# نشان داد.
_cfg_fn = _APSRC[_APSRC.find("def get_admin_config("):]
_cfg_fn = _cfg_fn[:_cfg_fn.find(chr(10) + "@app", 10)]
check("و بازکردن پنل واقعاً صدایش می‌زند",
      "_learn_panel_origin(request)" in _cfg_fn,
      "وگرنه آدرس هیچ‌وقت ثبت نمی‌شود و دکمه ظاهر نمی‌شود")

import bot.handlers as _BH                               # noqa: E402
_real_pa = _BH.pro_allowed
_BH.pro_allowed = lambda feature: False
check("without a license the bot shows no mini-app button (mini_app is Pro)",
      _BH.miniapp_url(type("C", (), {"s": {"miniapp_url": "https://a.ir/app"}})()) == "",
      "the bot menu does everything the mini app does")
_BH.pro_allowed = lambda feature: True
check("ربات همان تنظیم را می‌خواند",
      _BH.miniapp_url(type("C", (), {"s": {"miniapp_url": "https://a.ir/app"}})())
      == "https://a.ir/app")
check("و آدرس http را رد می‌کند",
      _BH.miniapp_url(type("C", (), {"s": {"miniapp_url": "http://a.ir"}})()) == "",
      "تلگرام با http خودِ پیام را رد می‌کند، نه فقط دکمه را")
check("و شناسه‌ی فروشگاه را به آدرس می‌چسباند (کلیدِ کشِ پوسته)",
      _BH.miniapp_url(type("C", (), {"tid": 7, "s": {"miniapp_url": "https://a.ir/app/"}})())
      == "https://a.ir/app?shop=7",
      "بی آن، بارِ اول رنگِ نکسورا و بعد پوسته‌ی فروشگاه دیده می‌شد")
_BH.pro_allowed = _real_pa

_RUN = io.open(os.path.join(str(ROOT), "bot", "run.py"), encoding="utf-8").read()
check("ربات خودش دکمه‌ی کنار کادر تایپ را تنظیم می‌کند",
      _re.search(r'setChatMenuButton"[^)]*"type":\s*"web_app"', _RUN, _re.S)
      is not None and "_sync_menu_button" in _RUN,
      "وگرنه مالک باید دستی به BotFather برود")
check("و وقتی آدرسی نیست، دکمه‌ی قبلی را برمی‌دارد",
      '"type": "commands"' in _RUN,
      "وگرنه به صفحه‌ای اشاره می‌کند که دیگر بالا نمی‌آید")

_TG = io.open(os.path.join(str(ROOT), "bot", "tg.py"), encoding="utf-8").read()
check("و کیبورد هم آدرس نامعتبر را حذف می‌کند نه می‌فرستد",
      'kind == "web_app"' in _TG and "startswith(\"https://\")" in _TG,
      "یک آدرس غلط کل منو را از کار می‌اندازد")


# ═══════════════════════════════════════════════════════════
head("گزارش فروش و قیف باید یک نرخ تبدیل بدهند")

# قیف در ۱.۳۷.۰ درست شد، ولی گزارش فروش تعریفِ خودش را داشت. روی
# همان داده، یکی می‌گفت ۸۰٪ و دیگری ۲۰٪.
#
# و «میانگین سفارش» هم با سفارش‌های صفرتومانیِ تست پایین کشیده
# می‌شد: ۶۲٬۵۰۰ به‌جای ۲۵۰٬۰۰۰.
#
# روی دیتابیس تازه سنجیده می‌شود تا عددها دقیق باشند.

_rdb = _tf.mktemp(suffix=".db")
_old_bp, _old_ap = botdb.DB_PATH, app.BOT_DB
botdb.DB_PATH = Path(_rdb)
try:
    botdb.init_db()
    _rtid = botdb.create_tenant("گزارش", bot_token="1:R", owner_tg_id=1)
    _rc = _sq3.connect(_rdb)
    _rc.executescript(f"""
    INSERT INTO plans (id, tenant_id, name, price, gb, days, is_trial)
      VALUES (6001, {_rtid}, 'تست', 0, 1, 1, 1);
    INSERT INTO plans (id, tenant_id, name, price, gb, days, is_trial)
      VALUES (6002, {_rtid}, '۳۰ گیگ', 200000, 30, 30, 0);
    """)
    # ده نفر آمدند؛ شش نفر فقط تست گرفتند، دو نفر واقعا خریدند
    for _u in range(1, 11):
        _rc.execute("INSERT INTO users (id,tenant_id,tg_id,created_at) "
                    "VALUES (?,?,?,datetime('now'))",
                    (_u, _rtid, 600 + _u))
    for _u in range(1, 7):
        _rc.execute("INSERT INTO orders (tenant_id,user_id,plan_id,amount,"
                    "base_amount,status,created_at) "
                    "VALUES (?,?,6001,0,0,'approved',datetime('now'))",
                    (_rtid, _u))
    for _u, _amt in ((7, 200000), (8, 300000)):
        _rc.execute("INSERT INTO orders (tenant_id,user_id,plan_id,amount,"
                    "base_amount,status,created_at) "
                    "VALUES (?,?,6002,?,?,'approved',datetime('now'))",
                    (_rtid, _u, _amt, _amt))
    _rc.commit()
    _rc.close()

    app.BOT_DB = Path(_rdb)
    _rep = app.bot_users_report(days=30, x_admin_password=PW)
finally:
    app.BOT_DB = _old_ap
    botdb.DB_PATH = _old_bp

check("گزارش خوانده شد", _rep.get("ready") is True)

_o = _rep.get("orders") or {}
check("تعداد سفارش، تست رایگان را نمی‌شمارد", _o.get("approved") == 2,
      f"{_o.get('approved')} — شش تستِ رایگان نباید سفارش باشند")
check("درآمد درست است", _o.get("revenue") == 500000, str(_o.get("revenue")))
check("میانگین سفارش با سفارش‌های صفرتومانی پایین کشیده نمی‌شود",
      _o.get("avg") == 250000,
      f"{_o.get('avg')} — قبلا ۶۲٬۵۰۰ می‌شد")

check("شمارش خریدارها هم", _rep.get("buyerCount") == 2,
      f"{_rep.get('buyerCount')} — قبلا هشت نفر")
check("نرخ تبدیل درست است", _rep.get("conversion") == 20.0,
      f"{_rep.get('conversion')} — قبلا ۸۰٪")

_bl = _rep.get("buyers") or []
check("فهرست خریدارها فقط خریدارهای واقعی است", len(_bl) == 2,
      f"{len(_bl)} — کسی که فقط تست گرفته خریدار نیست")
check("و هیچ‌کدام صفرتومانی نیستند",
      all((b.get("spent") or 0) > 0 for b in _bl),
      str([b.get("spent") for b in _bl]))

_dl = _rep.get("daily") or []
check("نمودار روزانه هم تست را نمی‌شمارد",
      sum(int(d.get("n") or 0) for d in _dl) == 2,
      str([(d.get("day"), d.get("n")) for d in _dl]))

# و قاعده یک بار نوشته شده، نه سه بار
_rsrc = _APP_NS_SRC
check("قاعده‌ی «خرید واقعی» یک تعریف دارد",
      _rsrc.count("SQL_REAL_BUY = ") == 1, "یک تعریف")
check("و هر سه جا از همان می‌خوانند",
      _rsrc.count("SQL_REAL_BUY") >= 6,
      f"{_rsrc.count('SQL_REAL_BUY')} اشاره — قیف، گزارش، پنل نماینده")
check("و کپیِ دستیِ شرط نمانده",
      _rsrc.count("COALESCE(p.is_trial,0)=0") == 1,
      "هر کپی یک جای تازه برای جدا افتادن است")


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("فهرست نماینده‌ها نباید خودِ مالک را نشان بدهد")

    # مستاجرِ ریشه هم در فهرست می‌آمد: با فرم «نشانی لینک»، «گروه
    # x-ui»، دکمه‌ی «بازکردن پنل» و حتی هشدارِ «برای اینکه بتواند وارد
    # شود…» — برای خودِ صاحب پنل. و می‌شد ناخواسته برایش پنل نمایندگی
    # باز کرد.

    _pl = app.tenant_portal_list(x_admin_password=PW)
    _ids = {t["id"] for t in _pl.get("tenants", [])}

    _pc = _sq3.connect(str(AP.BOT_DB))
    _roots = {r[0] for r in _pc.execute(
        "SELECT id FROM tenants WHERE parent_id IS NULL")}
    _kids = {r[0] for r in _pc.execute(
        "SELECT id FROM tenants WHERE parent_id IS NOT NULL")}
    _pc.close()

    check("مستاجر ریشه پیدا شد", bool(_roots), str(sorted(_roots)))
    check("هیچ مستاجرِ ریشه‌ای در فهرست نیست", not (_ids & _roots),
          f"در فهرست: {sorted(_ids & _roots)}")
    check("ولی نماینده‌ها همه هستند", _kids <= _ids,
          f"جاافتاده: {sorted(_kids - _ids)}")
    check("و این خالی‌بودنِ فهرست نیست", len(_ids) >= 1, f"{len(_ids)} نماینده")

    # ─── نخواندنِ گروه‌ها باید گفته شود ───
    #
    # خطای _read_xui_clients دور ریخته می‌شد و فهرست بی‌صدا خالی می‌ماند.
    # نتیجه: وقتی x-ui در دسترس نبود، *همه‌ی* نماینده‌ها بدون گروه به
    # نظر می‌رسیدند، بدون هیچ توضیحی.
    check("کلید groupsError در پاسخ هست", "groupsError" in _pl,
          "بدون آن، رابط نمی‌تواند بگوید چرا فهرست خالی است")

    # روی همان ماژولی وصله می‌زنیم که صدایش می‌زنیم: AP و app دو شیء
    # جدا هستند و وصله‌ی یکی روی دیگری اثر ندارد.
    _orig_read = app._read_xui_clients
    app._read_xui_clients = lambda *a, **k: (None, [], "پنل در دسترس نیست")
    try:
        _pl2 = app.tenant_portal_list(x_admin_password=PW)
    finally:
        app._read_xui_clients = _orig_read

    check("وقتی x-ui جواب نمی‌دهد، دلیلش گزارش می‌شود",
          bool(_pl2.get("groupsError")), repr(_pl2.get("groupsError")))
    check("و فهرست نماینده‌ها همچنان می‌آید",
          _pl2.get("ready") is True and isinstance(_pl2.get("tenants"), list),
          "نخواندنِ گروه‌ها نباید کلِ صفحه را از کار بیندازد")
else:
    _PRO_SKIPPED.append('فهرست نماینده\u200cها نباید خودِ مالک را نشان بدهد')


# ═══════════════════════════════════════════════════════════
if PRO:        # the reseller portal is Pro (backend/pro/resellers.py)
    head("فروشگاهِ نماینده · کارت، وصل‌شدن، کفِ پلن")

    # تا ۱.۸۵ رباتِ نماینده نه کارت داشت (پس پولی نمی‌گرفت)، نه راهی
    # برای رسیدنِ رسید به صاحبش، و بکند هر قیمتی را برای پلن می‌پذیرفت —
    # حتی زیرِ کفی که مالک از او می‌گیرد.

    _bw = _sq3.connect(str(AP.BOT_DB))
    try:
        # فیکسچر جدولِ tenants را دستی ساخته؛ اسکیمای واقعی این ستون را دارد
        try:
            _bw.execute("ALTER TABLE tenants ADD COLUMN owner_tg_id INTEGER")
        except Exception:
            pass
        _bw.execute("UPDATE tenants SET portal_group='goroh-a', owner_tg_id=NULL, "
                    "bot_token='555666777:DDHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw', "
                    "bot_username='shop_bot', settings=? WHERE portal_slug='hossein'",
                    (json.dumps({"brand": "فروشگاه"}, ensure_ascii=False),))
        _bw.commit()
    finally:
        _bw.close()
    _bcx = AP._billing_conn()
    try:
        _bcx.execute("INSERT OR REPLACE INTO group_config (group_key,label,billable,"
                     "rates) VALUES (?,?,?,?)",
                     ("goroh-a", "گروه الف", 1,
                      json.dumps([{"gb": 50, "price": 100000, "perDevice": 20000}])))
        _bcx.commit()
    finally:
        _bcx.close()

    _TS = AP._tenant_by_slug("hossein")
    _st0 = AP.portal_bot_get(_TS)
    check("وضعیت می‌گوید صاحب وصل نیست و کارتی نیست",
          _st0.get("ownerLinked") is False and _st0.get("activeCards") == 0
          and _st0.get("hasGroup") is True, str(_st0)[:90])

    # ── کارت ──
    try:
        AP.portal_cards_set({"cards": [{"number": "6037 9911 1111 111"}]}, _TS)
        _c15 = False
    except Exception as e:
        _c15 = getattr(e, "status_code", 0) == 400 and "۱۶" in str(e.detail)
    check("کارتِ ۱۵ رقمی رد می‌شود و می‌گوید چرا", _c15)

    _cr = AP.portal_cards_set({"cards": [
        {"number": "۶۰۳۷-۹۹۱۱-۲۲۲۲-۳۳۳۳", "holder": "حسین", "bank": "ملی",
         "active": True, "panel_pass": "نفوذ"},
        {"number": "6219861000000000", "active": False},
        {"number": ""}]}, _TS)
    check("کارت با رقمِ فارسی پذیرفته می‌شود",
          _cr.get("count") == 2 and _cr.get("active") == 1, str(_cr))
    _cg = AP.portal_cards_get(AP._tenant_by_slug("hossein"))["cards"]
    check("و به رقمِ لاتینِ بی‌خط ذخیره می‌شود",
          _cg and _cg[0]["number"] == "6037991122223333", str(_cg[:1]))
    check("کلیدِ خارج از فهرستِ مجاز ننشست",
          all(set(c) == {"number", "holder", "bank", "active"} for c in _cg))
    _js2 = AP._tenant_settings(AP._tenant_by_slug("hossein"))
    check("و بقیه‌ی تنظیمات دست نخورد", _js2.get("brand") == "فروشگاه")
    check("کارتی که ربات می‌خواند همین است",
          __import__("core").pick_card(_js2.get("cards"))["number"]
          == "6037991122223333",
          "core.pick_card غیرفعال را کنار می‌گذارد")

    try:
        AP.portal_cards_set({"cards": [{"number": "6037991122223333"}] * 11}, _TS)
        _c11 = False
    except Exception as e:
        _c11 = getattr(e, "status_code", 0) == 400
    check("بیش از ۱۰ کارت رد می‌شود", _c11)

    # ── لینکِ وصل‌شدن ──
    _lk = AP.portal_bot_link(AP._tenant_by_slug("hossein"))
    _code = AP._tenant_settings(AP._tenant_by_slug("hossein")).get(
        "owner_claim", {}).get("code")
    check("لینکِ وصل‌شدن به رباتِ خودش است",
          _lk["url"].startswith("https://t.me/shop_bot?start=own_"), _lk["url"][:40])
    check("و کدِ داخلش همان است که ربات می‌سنجد",
          bool(_code) and _lk["url"].endswith("own_" + _code))
    check("کد برای start تلگرام مجاز است (حداکثر ۶۴، فقط A-Za-z0-9_-)",
          len("own_" + _code) <= 64
          and all(ch.isalnum() or ch in "_-" for ch in "own_" + _code))

    _bw = _sq3.connect(str(AP.BOT_DB))
    try:
        _bw.execute("UPDATE tenants SET owner_tg_id=4242 WHERE portal_slug='hossein'")
        _bw.commit()
    finally:
        _bw.close()
    check("بعد از وصل‌شدن، وضعیت می‌گوید وصل است",
          AP.portal_bot_get(AP._tenant_by_slug("hossein"))["ownerLinked"] is True)
    AP.portal_bot_unlink(AP._tenant_by_slug("hossein"))
    check("جداشدن صاحب را پاک می‌کند",
          AP.portal_bot_get(AP._tenant_by_slug("hossein"))["ownerLinked"] is False)

    _bw = _sq3.connect(str(AP.BOT_DB))
    try:
        _bw.execute("UPDATE tenants SET bot_username=NULL WHERE portal_slug='hossein'")
        _bw.commit()
    finally:
        _bw.close()
    try:
        AP.portal_bot_link(AP._tenant_by_slug("hossein"))
        _nob = False
    except Exception as e:
        _nob = getattr(e, "status_code", 0) == 409
    check("بی‌ربات لینکی ساخته نمی‌شود", _nob)

    # ── کفِ پلن: پیش‌نمایش و ذخیره یک عدد ──
    _TS = AP._tenant_by_slug("hossein")
    _pv = AP.portal_plan_cost({"rows": [{"gb": 50, "days": 30, "ip_limit": 2}]},
                              _TS)["rows"][0]
    check("پیش‌نمایش کف را می‌دهد", _pv.get("cost") == 120000, str(_pv))

    try:
        AP.portal_bot_plans_save({"plans": [{"name": "ارزان", "gb": 50, "days": 30,
                                             "ip_limit": 2, "price": 110000}]}, _TS)
        _below = False
        _bmsg = ""
    except Exception as e:
        _below = getattr(e, "status_code", 0) == 400
        _bmsg = str(getattr(e, "detail", ""))
    check("قیمتِ زیرِ کف ذخیره نمی‌شود", _below)
    # رقمِ فارسی با جداکننده‌ی «٬» — همان faNumِ رابط (`_fnum`)
    check("و پیام هر دو عدد را می‌گوید", "۱۱۰٬۰۰۰" in _bmsg and "۱۲۰٬۰۰۰" in _bmsg,
          _bmsg[:80])

    AP.portal_bot_plans_save({"plans": [{"name": "سودده", "gb": 50, "days": 30,
                                         "ip_limit": 2, "price": 150000}]}, _TS)
    _bw = _sq3.connect(str(AP.BOT_DB))
    try:
        _cost = _bw.execute("SELECT cost FROM plans WHERE tenant_id=? AND name=?",
                            (_TS["id"], "سودده")).fetchone()
    finally:
        _bw.close()
    check("کفِ ذخیره‌شده همان کفِ پیش‌نمایش است",
          _cost is not None and _cost[0] == _pv.get("cost"),
          f"ذخیره {_cost[0] if _cost else '—'} · پیش‌نمایش {_pv.get('cost')}")

    # مالک نرخ را عوض می‌کند → کفِ ذخیره‌شده هم باید عوض شود، وگرنه ربات
    # کفِ کهنه را از اعتبارِ نماینده‌ی پیش‌پرداخت کم می‌کند.
else:
    _PRO_SKIPPED.append('فروشگاهِ نماینده · کارت، وصل\u200cشدن، کفِ پلن')
if PRO:        # rates are set on the accounting screens (Pro)
    AP.billing_group_put("goroh-a", {"label": "گروه الف", "billable": True,
                                     "rates": [{"gb": 50, "price": 130000,
                                                "perDevice": 20000}]},
                         x_admin_password="testpw")
    _bw = _sq3.connect(str(AP.BOT_DB))
    try:
        _cost2 = _bw.execute("SELECT cost FROM plans WHERE tenant_id=? AND name=?",
                             (_TS["id"], "سودده")).fetchone()
        # و پلنی که پیش از ۱.۸۶ ذخیره شده (کف صفر) با بالاآمدن پر می‌شود
        _bw.execute("UPDATE plans SET cost=0 WHERE tenant_id=? AND name=?",
                    (_TS["id"], "سودده"))
        _bw.commit()
    finally:
        _bw.close()
    check("تغییرِ نرخ کفِ پلن‌های گروه را همگام می‌کند",
          _cost2 is not None and _cost2[0] == 150000,
          f"{_cost2[0] if _cost2 else '—'} (باید ۱۵۰٬۰۰۰ باشد)")

    _n = AP._refresh_plan_costs()
    _bw = _sq3.connect(str(AP.BOT_DB))
    try:
        _cost3 = _bw.execute("SELECT cost FROM plans WHERE tenant_id=? AND name=?",
                             (_TS["id"], "سودده")).fetchone()
    finally:
        _bw.close()
    check("پلنِ بی‌کف با همگام‌سازیِ آغاز پر می‌شود",
          _n >= 1 and _cost3 and _cost3[0] == 150000, f"{_n} پلن · {_cost3}")

    # ── ورودیِ خرابِ گروه: ۴۰۰، نه صفر یا نادیده‌گرفتنِ بی‌صدا ──
    #
    # «نرخ حجمی» نامعتبر بی‌صدا ۰ ذخیره می‌شد، و «تسویه‌شده تا»ی خراب
    # ذخیره می‌شد و بعد `_bill_since` از رویش می‌پرید — صورتحساب ماه‌های
    # تسویه‌شده را دوباره حساب می‌کرد.
    for _bad, _why in (({"per_gb": "abc"}, "نرخ حجمی"),
                       ({"settled_until": "1405-13-40"}, "تسویه‌شده تا"),
                       ({"period_start": "not-a-date"}, "شروع همکاری")):
        try:
            AP.billing_group_put("goroh-bad", {"label": "x", **_bad}, x_admin_password="testpw")
            _st, _dt = 200, ""
        except AP.HTTPException as e:
            _st, _dt = e.status_code, str(e.detail)
        check(f"«{_why}»ِ نامعتبر ۴۰۰ می‌گیرد", _st == 400, f"{_st} {_dt[:60]}")
else:
    _PRO_SKIPPED.append('reseller store: a rate change syncs plan floors; bad group input is a 400')

# دادهٔ خرابی که از قبل در دیتابیس نشسته: پله‌ی بعد انتخاب می‌شود، ولی گفته می‌شود
_since, _src = AP._bill_since({"settled_until": "1405-13-40", "period_start": "2026-01-01"})
check("«تسویه‌شده تا»ی خراب بی‌صدا رد نمی‌شود",
      _since == "2026-01-01" and "نامعتبر" in _src and "تسویه‌شده تا" in _src, _src)
_since2, _src2 = AP._bill_since({"settled_until": "2026-03-01", "period_start": "2026-01-01"})
check("و تاریخِ سالم برچسبِ هشدار نمی‌گیرد",
      _since2 == "2026-03-01" and "نامعتبر" not in _src2, _src2)

# ── برابری: کدام پنل؟ ──
#
# بکند (`_panel_row`) و ربات (`panel_source`) دو پیاده‌سازیِ یک
# قاعده‌اند. تا ۱.۸۵ فقط اولی وجود داشت.
import db as _PBD                                       # noqa: E402
_bw = _sq3.connect(str(AP.BOT_DB))
_bw.row_factory = _sq3.Row
try:
    _rootp = dict(_bw.execute("SELECT * FROM tenants WHERE parent_id IS NULL "
                              "ORDER BY id LIMIT 1").fetchone())
finally:
    _bw.close()
# The reseller made by the (Pro) store section above, or, in the Community
# tree, a reseller-shaped copy of the owner's row: this parity is core, since
# reseller bots are.
_TSP = _TS if PRO else dict(_rootp, id=int(_rootp["id"]) + 1000)
_cases = [
    ("نماینده‌ی بی‌پنل", dict(_TSP, panel_url=None, parent_id=_rootp["id"])),
    ("نماینده با پنلِ خودش", dict(_TSP, panel_url="http://own:1",
                                  parent_id=_rootp["id"])),
    ("خودِ مالک", _rootp),
]
_PBD.DB_PATH = Path(str(AP.BOT_DB))
for _nm, _tt in _cases:
    _a = (AP._panel_row(_tt) or {}).get("id"), (AP._panel_row(_tt) or {}).get("panel_url")
    _b = (_PBD.panel_source(_tt) or {}).get("id"), (_PBD.panel_source(_tt) or {}).get("panel_url")
    check(f"پنل · {_nm}: بکند و ربات یکی می‌گویند", _a == _b, f"{_a} / {_b}")

head("تلاش برای نفوذ — «از قبل بسته» از خودِ فایروال")
# صفحه از a.blocked می‌خواند و بکند هرگز نمی‌فرستادش: کاشیِ «از قبل بسته»
# روی سرورِ واقعی همیشه صفر بود
if getattr(app, "INTRUSION", None) and getattr(app, "FIREWALL", None):
    _IN, _FWm = app.INTRUSION, app.FIREWALL
    _saved = (_IN.summary, _FWm.blackhole_list, _FWm.status, app.NETID)
    _IN.summary = lambda known_ips=None, hours=24: {"ssh": {"available": True, "attempts": [
        {"ip": "203.0.113.7", "count": 120, "severity": "heavy", "known": False},
        {"ip": "203.0.113.8", "count": 40, "severity": "brute", "known": False},
        {"ip": "203.0.113.9", "count": 30, "severity": "brute", "known": False}]}}
    _FWm.blackhole_list = lambda: ["203.0.113.7"]
    _FWm.status = lambda: {"rules": [{"action": "DENY", "source": "203.0.113.8 (v6)", "port": None},
                                     {"action": "ALLOW", "source": "203.0.113.9", "port": 22}]}
    app.NETID = None
    _ir = app.firewall_intrusion(hours=24, x_admin_password=PW)
    _bl = {a["ip"]: a["blocked"] for a in _ir["ssh"]["attempts"]}
    check("سیاه‌چاله ← بسته", _bl.get("203.0.113.7") is True, str(_bl))
    check("قاعده‌ی DENY روی مبدأ (حتی v6) ← بسته", _bl.get("203.0.113.8") is True)
    check("قاعده‌ی ALLOW ← باز", _bl.get("203.0.113.9") is False)
    _FWm.status = lambda: (_ for _ in ()).throw(RuntimeError("ufw gone"))
    _ir2 = app.firewall_intrusion(hours=24, x_admin_password=PW)
    check("شکستِ خواندن بی‌صدا نیست", "blockedError" in _ir2 and
          all(a["blocked"] is False for a in _ir2["ssh"]["attempts"]), str(_ir2.get("blockedError")))
    _IN.summary, _FWm.blackhole_list, _FWm.status, app.NETID = _saved


head("رسید فقط با هدر")
# پیش‌تر `?pw=` هم پذیرفته می‌شد و رابط رمز را در src تصویر می‌گذاشت
import inspect as _insp  # noqa: E402
check("مسیرِ رسید پارامترِ pw ندارد", "pw" not in _insp.signature(app.bot_receipt).parameters,
      str(list(_insp.signature(app.bot_receipt).parameters)))
try:
    app.bot_receipt(1, x_admin_password=None)
    _rc = 200
except Exception as _e:
    _rc = getattr(_e, "status_code", 0)
check("بی‌هدر ← ۴۰۱", _rc == 401, str(_rc))

head("ذخیره‌ی تنظیمات: پاسخِ خطا جای کلِ تنظیمات نمی‌نشیند")
# «تنظیماتِ حسابداری» کلِ تنظیمات را با r.json بی‌سنجش می‌خواند و با یک مسیر
# پس می‌فرستاد؛ خواندنِ ناموفق یعنی `{detail, advanced}` به‌جای همه‌چیز.
try:
    app.update_config({"detail": "boom", "advanced": {"xuiDbPath": "/x"}}, x_config_version=None,
                      x_admin_password="testpw")
    _uc = 200
except app.HTTPException as _e:
    _uc = _e.status_code
check("تنظیماتِ ناقص ۴۰۰ می‌گیرد، نه جایگزینیِ کل", _uc == 400, str(_uc))
_full = app.load_config()
check("تنظیماتِ کامل هنوز ذخیره می‌شود",
      app.update_config(_full, x_admin_password="testpw", x_config_version=None).get("ok") is True)
_r = app.billing_xui_path_set({"path": " /opt/x-ui/x-ui.db "}, x_admin_password="testpw")
_after = app.load_config()
check("مسیرِ x-ui جدا ذخیره می‌شود و بقیه‌ی تنظیمات دست نمی‌خورد",
      _r.get("path") == "/opt/x-ui/x-ui.db"
      and (_after.get("advanced") or {}).get("xuiDbPath") == "/opt/x-ui/x-ui.db"
      and _after.get("faq") == _full.get("faq"),
      str(_r))
check("و GETِ همان مسیر مقدارِ دستی را برمی‌گرداند",
      app.billing_xui_path(x_admin_password="testpw").get("manual") == "/opt/x-ui/x-ui.db")
app.billing_xui_path_set({"path": ""}, x_admin_password="testpw")

head("بازیابیِ پشتیبانِ قدیمی، بخش‌های تازه‌تر را پاک نمی‌کند")
_cur_cfg = app.load_config()
_cur_cfg["resellers"] = [{"id": "r1", "name": "حسین", "enabled": True}]
app.save_config(_cur_cfg)
_old_bak = {k: v for k, v in _cur_cfg.items() if k not in ("resellers", "popup")}
_imp = app.import_config({"config": _old_bak}, x_admin_password="testpw")
_after_imp = app.load_config()
check("بخشی که در پشتیبان نبود دست نمی‌خورد",
      _after_imp.get("resellers") == [{"id": "r1", "name": "حسین", "enabled": True}],
      str(_after_imp.get("resellers"))[:80])
check("و پاسخ می‌گوید کدام بخش‌ها ماندند",
      "resellers" in (_imp.get("kept") or []) and "دست نخورد" in _imp.get("message", ""),
      _imp.get("message", ""))

head("تنظیماتِ ربات: ذخیره‌ی ناقص همه‌چیز را پاک نمی‌کند")
# PUTِ تنظیماتِ ربات کلِ دیکشنری را جایگزین می‌کند. سه صفحه پس از شکستِ
# خواندن با {} ادامه می‌دادند و ذخیره‌شان فقط یک کلید را می‌فرستاد.
_full_st = {"brand": "B", "support_username": "@s", "coins": {"enabled": True},
            "texts": {"welcome": "سلام"}, "quick_replies": [{"title": "x", "body": "y"}]}
app.bot_settings_put({"settings": _full_st}, x_admin_password="testpw")
try:
    app.bot_settings_put({"settings": {"winback": {"enabled": True}}},
                         x_admin_password="testpw")
    _bs = 200
except app.HTTPException as _e:
    _bs = _e.status_code
_bw2 = _sq3.connect(str(app.BOT_DB))
try:
    _stored = json.loads(_bw2.execute(
        "SELECT settings FROM tenants WHERE parent_id IS NULL ORDER BY id LIMIT 1"
    ).fetchone()[0] or "{}")
finally:
    _bw2.close()
check("ذخیره‌ای که بیشترِ تنظیمات را حذف می‌کند ۴۰۰ می‌گیرد", _bs == 400, str(_bs))
check("و تنظیماتِ ذخیره‌شده دست نخورده می‌ماند",
      _stored.get("texts") == {"welcome": "سلام"} and "winback" not in _stored,
      str(sorted(_stored)))
check("ذخیره‌ی کامل (خوانده، یک کلید عوض، پس فرستاده) هنوز کار می‌کند",
      app.bot_settings_put({"settings": {**_full_st, "winback": {"enabled": True}}},
                           x_admin_password="testpw").get("ok") is True)

if PRO:        # expenses are accounting (Pro)
    head("هزینه‌ها: ورودیِ خراب ۴۰۰ می‌گیرد، نه جایگزینیِ بی‌صدا")
    # نرخِ دستیِ نامعتبر پیش‌تر بی‌صدا با نرخِ بازار عوض می‌شد؛ تاریخِ خراب خام
    # ذخیره می‌شد؛ حجمِ ناخوانا None می‌شد
    _base_exp = {"kind": "server_abroad", "label": "آزمون", "amount": 10, "currency": "EUR"}
    for _bad, _needle in (({"rate": "abc"}, "دستی"), ({"rate": "-5"}, "دستی"),
                          ({"rate": "250000", "spentAt": "2026-13-45"}, "تاریخ"),
                          ({"rate": "250000", "gb": "ده"}, "حجم")):
        try:
            app.expenses_add({**_base_exp, **_bad}, x_admin_password="testpw")
            _st, _dt = 200, ""
        except app.HTTPException as _e:
            _st, _dt = _e.status_code, str(_e.detail)
        check(f"هزینه با {list(_bad)[-1]} نامعتبر ۴۰۰ می‌گیرد", _st == 400 and _needle in _dt, f"{_st} {_dt[:60]}")
    _ok_exp = app.expenses_add({**_base_exp, "rate": "250000.4"}, x_admin_password="testpw")
    check("نرخِ دستیِ اعشاری پذیرفته و گرد می‌شود",
          bool(_ok_exp.get("ok", True)) and "2500000" in json.dumps(_ok_exp, ensure_ascii=False),
          json.dumps(_ok_exp, ensure_ascii=False)[:120])
else:
    _PRO_SKIPPED.append('expenses: bad input is a 400')

head("هشدارِ سلامتِ سرور واقعاً فرستاده می‌شود")
# کوئری ستون‌های `admin_id` و `group_id` را می‌خواند که در tenants نیستند؛
# خطا بلعیده می‌شد و هیچ هشداری هرگز نرفت. این‌جا ارسال واقعاً ضبط می‌شود.
import urllib.request as _ur  # noqa: E402
_sent = []
_orig_open = _ur.urlopen
_ur.urlopen = lambda req, timeout=None: _sent.append(json.loads(req.data.decode())) or None
_bw3 = _sq3.connect(str(app.BOT_DB))
try:
    # این دیتابیسِ تست جدولِ کمینه‌ی دست‌سازِ tenants را دارد؛ ستون‌های
    # اسکیمای واقعی (bot/db.py) که این‌جا لازم‌اند اضافه می‌شوند
    _tc = {r[1] for r in _bw3.execute("PRAGMA table_info(tenants)")}
    for _c, _t in (("owner_tg_id", "INTEGER"), ("admin_group_id", "INTEGER"),
                   ("topics", "TEXT DEFAULT '{}'")):
        if _c not in _tc:
            _bw3.execute(f"ALTER TABLE tenants ADD COLUMN {_c} {_t}")
    _bw3.execute("UPDATE tenants SET bot_token=?, admin_group_id=?, topics=? "
                 "WHERE id=(SELECT id FROM tenants WHERE parent_id IS NULL ORDER BY id LIMIT 1)",
                 ("999:TESTTOKEN", -100123, json.dumps({"alerts": 77})))
    _bw3.commit()
finally:
    _bw3.close()
try:
    app._health_state.pop("t-alert", None)
    app._health_alert("سرورِ آزمون", {"level": "crit", "summary": "دیسک پر",
                                        "checks": [{"level": "crit", "title": "دیسک", "detail": "۹۸٪"}]},
                      key="t-alert")
finally:
    _ur.urlopen = _orig_open
check("هشدارِ خرابی به گروهِ مدیریت می‌رود", len(_sent) == 1 and _sent[0].get("chat_id") == -100123,
      str(_sent)[:120])
check("و در تاپیکِ alerts", bool(_sent) and _sent[0].get("message_thread_id") == 77,
      str(_sent[0] if _sent else None)[:120])

head("کارِ پس‌زمینه‌ی شکسته بی‌صدا نیست")
# حلقه‌ی سلامت هر سه شکستش را با pass می‌بلعید؛ نگهداریِ خودکار می‌توانست
# ماه‌ها اجرا نشود و «اجرای بعدی: …» همچنان نشان داده شود.
app._LOOP_ERR.clear()
app._loop_fail("maint", RuntimeError("systemctl not found"))
_mg = app.maintenance_get(x_admin_password="testpw")
check("خطای زمان‌بندِ نگهداری در پاسخ می‌آید",
      "systemctl not found" in ((_mg.get("tickError") or {}).get("error") or ""),
      str(_mg.get("tickError")))
app._loop_ok("maint")
check("و با اجرای موفق پاک می‌شود",
      app.maintenance_get(x_admin_password="testpw").get("tickError") is None)


# شمارنده نباید جای دیگری بازنویسی شده باشد.
#
# `_ok` دو جا به‌عنوان متغیر معمولی به کار رفته بود و هر بار شمارش را
# از صفر شروع می‌کرد — سوییت ۳۱۳ بررسی را اجرا می‌کرد و ۱۸۲ گزارش
# می‌داد. خود تست‌ها درست کار می‌کردند و شکست‌ها هم شمرده می‌شدند، ولی
# عددِ پایانی دروغ می‌گفت و هیچ راهی نبود بفهمی بخشی از سوییت اصلاً
# اجرا نشده.
# آستانه: هر فراخوانیِ ایستا دست‌کم یک‌بار اجرا می‌شود و بعضی‌ها داخل
# حلقه‌اند، پس شمرده‌شده باید **بیشتر** از تعداد ایستا باشد. کمتر بودن
# یعنی یا شمارنده بازنویسی شده یا بخشی از سوییت اصلاً نرسیده.
#
# چند بررسی داخل شرط‌اند و ممکن است اجرا نشوند، پس کمی ارفاق —
# ولی نه آن‌قدر که بازنویسی از زیرش در برود: با آستانه‌ی ۰٫۶ یک
# بازنویسی که ۲۰۶ از ۲۷۹ را شمرد، بی‌صدا رد شد.
_calls = io.open(__file__, encoding="utf-8").read().count("\ncheck(")
_counted = _ok + _fail
if _counted < _calls * 0.95:
    print(f"  {R}✗ شمارنده بازنویسی شده — {_counted} شمرده شد، "
          f"ولی {_calls} فراخوانی در فایل هست{X}")
    _fail += 1

if _PRO_SKIPPED:
    print(f"\n  {D}Community tree: {len(_PRO_SKIPPED)} Pro sections skipped{X}")
if __name__ == "__main__":
    print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
    print()
    sys.exit(1 if _fail else 0)

