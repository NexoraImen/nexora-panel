#!/usr/bin/env python3
"""
تست هم‌زمانی حلقه‌ی ربات.

چرا وجود دارد:
    گزارش شد «ربات کند است و با کاربر زیاد به مشکل می‌خورد». علتش
    این بود که آپدیت‌ها یکی‌یکی پردازش می‌شدند: ساخت کانفیگ چند ثانیه
    طول می‌کشد و در تمام آن مدت هیچ پیام دیگری جلو نمی‌رفت.

    این تست دو چیز را می‌سنجد که هر دو باید هم‌زمان درست باشند:
      ۱. کاربرهای مختلف موازی پیش بروند (سرعت)
      ۲. پیام‌های یک کاربر به‌ترتیب بمانند (درستی)

    دومی مهم‌تر است: موازی‌سازی‌ای که ترتیب گفت‌وگوی یک نفر را به هم
    بزند، از کندی بدتر است.

اجرا:  python3 tests/test-bot-throughput.py
"""
import io
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

G, R, D, X = "\033[38;5;42m", "\033[38;5;203m", "\033[38;5;245m", "\033[0m"
_ok = _fail = 0

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


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


# ═══════════ بازسازی منطق حلقه ═══════════
# همان ساختار run.py، بدون تلگرام و دیتابیس، تا فقط رفتار
# هم‌زمانی سنجیده شود.

POOL_SIZE = 8
WORK = 0.25          # هر آپدیت چقدر طول می‌کشد (شبیه ساخت کانفیگ)


def make_runner(pool_size):
    chat_locks = {}
    guard = threading.Lock()
    done = []
    done_lock = threading.Lock()

    def chat_lock(cid):
        with guard:
            lk = chat_locks.get(cid)
            if lk is None:
                lk = chat_locks[cid] = threading.Lock()
        return lk

    def handle(cid, seq):
        with chat_lock(cid):
            time.sleep(WORK)
            with done_lock:
                done.append((cid, seq))

    return ThreadPoolExecutor(max_workers=pool_size), handle, done


head("سرعت با چند کاربر هم‌زمان")

N_USERS = 8
pool, handle, done = make_runner(POOL_SIZE)
t0 = time.time()
for uid in range(N_USERS):
    pool.submit(handle, uid, 0)
pool.shutdown(wait=True)
parallel = time.time() - t0

serial = N_USERS * WORK
check(f"{N_USERS} کاربر هم‌زمان پردازش شدند", len(done) == N_USERS, str(len(done)))
check("موازی از سریالی سریع‌تر است",
      parallel < serial * 0.5,
      f"موازی {parallel:.2f}s در برابر سریالی {serial:.2f}s")
check("همه در حدود یک نوبت تمام شدند",
      parallel < WORK * 2.5, f"{parallel:.2f}s")

head("ترتیب پیام‌های یک کاربر")

pool2, handle2, done2 = make_runner(POOL_SIZE)
SEQ = 6
for i in range(SEQ):
    pool2.submit(handle2, 999, i)
pool2.shutdown(wait=True)

order = [s for c, s in done2 if c == 999]
check("همه‌ی پیام‌های کاربر پردازش شدند", len(order) == SEQ, str(len(order)))
check("ترتیب حفظ شد", order == sorted(order), str(order))

head("کاربر کند، بقیه را بلوکه نمی‌کند")

pool3, _, done3 = make_runner(POOL_SIZE)
locks3 = {}
g3 = threading.Lock()
res3 = []
r3lock = threading.Lock()


def slow_or_fast(cid, delay):
    time.sleep(delay)
    with r3lock:
        res3.append(cid)


pool3.submit(slow_or_fast, "کند", 1.2)
time.sleep(0.05)
for i in range(5):
    pool3.submit(slow_or_fast, f"سریع{i}", 0.05)
pool3.shutdown(wait=True)

fast_done = [c for c in res3 if c.startswith("سریع")]
check("کاربران سریع زودتر از کاربر کند تمام شدند",
      res3.index("کند") == len(res3) - 1,
      " ← ".join(res3[:3]) + " ... ")
check("هیچ کاربری گم نشد", len(res3) == 6, str(len(res3)))

head("کش تنظیمات در Ctx")

import tempfile   # noqa: E402
os.environ["BOT_DB_PATH"] = tempfile.mktemp(suffix=".db")
sys.path.insert(0, os.path.join(ROOT, "bot"))

from bot import db as _db          # noqa: E402
import bot.tg as _tg               # noqa: E402
import bot.handlers as _H          # noqa: E402


class _FakeBot:
    def __init__(self, token=None):
        self.token = token

    def __getattr__(self, n):
        return lambda *a, **k: {"message_id": 1, "chat": {"id": 1}}


_tg.Bot = _FakeBot
_H.Bot = _FakeBot
_db.init_db()
_tid = _db.create_tenant("T", bot_token="1:X", owner_tg_id=9)
_db.save_tenant_settings(_tid, {"brand": "Nexora", "coins": {"per_referral": 10}})
_tenant = _db.get_tenant(_tid)

_reads = {"n": 0}
_orig = _db.tenant_settings


def _counting(tid):
    _reads["n"] += 1
    return _orig(tid)


_db.tenant_settings = _counting
_H.DB.tenant_settings = _counting

_ctx = _H.Ctx(_FakeBot(), _tenant)
_reads["n"] = 0
for _ in range(30):
    _ctx.s
check("۳۰ دسترسی به ctx.s فقط یک بار دیسک می‌خورد",
      _reads["n"] == 1, f"{_reads['n']} بار خواندن")

# تغییر تنظیمات از پنل باید بعد از TTL دیده شود
_H.Ctx.CACHE_TTL = 0.05
_ctx2 = _H.Ctx(_FakeBot(), _tenant)
_ = _ctx2.s
_db.save_tenant_settings(_tid, {"brand": "عوض‌شده"})
time.sleep(0.12)
check("تغییر تنظیمات پنل بعد از TTL دیده می‌شود",
      _ctx2.s.get("brand") == "عوض‌شده", str(_ctx2.s.get("brand")))

_ctx3 = _H.Ctx(_FakeBot(), _tenant)
_ = _ctx3.s
_ctx3.invalidate()
_reads["n"] = 0
_ = _ctx3.s
check("invalidate کش را دور می‌ریزد", _reads["n"] == 1, f"{_reads['n']} بار")

_db.tenant_settings = _orig
_H.DB.tenant_settings = _orig
_H.Ctx.CACHE_TTL = 2

head("تنظیمات واقعی run.py")

import importlib.util   # noqa: E402
spec = importlib.util.spec_from_file_location(
    "_run_probe", os.path.join(ROOT, "bot", "run.py"))
src = open(os.path.join(ROOT, "bot", "run.py"), encoding="utf-8").read()

check("استخر نخ در حلقه هست", "ThreadPoolExecutor" in src)
check("قفل هر چت هست", "chat_lock" in src)
check("Bot بیرون حلقه ساخته می‌شود",
      "if tg is None or tg.token" in src)
check("اندازه‌ی استخر قابل تنظیم است", "BOT_POOL_SIZE" in src)
check("dispatch مستقیم در حلقه صدا زده نمی‌شود",
      "pool.submit(handle" in src and
      "\n                    handlers.dispatch(tenant, tg, up)" not in src)

# ═══════════════════════════════════════════════════════════
head("هرسِ قفل‌ها نباید قفلِ دستِ کسی را بردارد")

# قفلِ هر چت تنها چیزی است که جلوی دوباره‌پردازش‌شدن یک کاربر را
# می‌گیرد.
#
# نسخه‌ی قبلی قفل را داخل نگهبان برمی‌داشت، نگهبان را رها می‌کرد، و
# *بعد* قفل را می‌گرفت. در آن فاصله قفل در جدول بود ولی هنوز
# locked() نبود — و شرط هرس دقیقاً همان not v.locked() بود. پس
# آپدیتی از چتی دیگر می‌توانست همان قفل را بردارد، و آپدیت بعدیِ
# همان چت قفلِ تازه‌ای می‌ساخت: دو پردازش هم‌زمان روی یک چت.
#
# و این فقط بالای پنج هزار چت رخ می‌داد — یعنی وقتی ربات شلوغ است و
# احتمال دو آپدیت هم‌زمان بیشترین است.

import importlib.util as _ilu   # noqa: E402

_spec = _ilu.spec_from_file_location(
    "botrun_locks", os.path.join(ROOT, "bot", "run.py"))
_RUN = _ilu.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_RUN)
    _loaded = True
except Exception as _e:
    _loaded = False
    print(f"  {R}bot/run.py بارگذاری نشد: {_e}{X}")

check("bot/run.py بارگذاری شد", _loaded)

if _loaded:
    check("قفل‌ها بیرون از حلقه و قابل آزمودن‌اند",
          hasattr(_RUN, "ChatLocks") and hasattr(_RUN, "chat_id_of"),
          "وگرنه هیچ راهی برای سنجیدنشان نیست")

    _CL = _RUN.ChatLocks(limit=50)
    _inside = 0
    _overlap = 0
    _seen = threading.Lock()
    _in_gate = threading.Event()

    def _use(cid, hold_for, gate=None):
        global _inside, _overlap
        with _CL.hold(cid):
            with _seen:
                _inside += 1
                if _inside > 1:
                    _overlap += 1
            if gate:
                gate.set()
            time.sleep(hold_for)
            with _seen:
                _inside -= 1

    # یک آپدیت چت ۷ را نگه می‌دارد، و هم‌زمان ترافیک چت‌های دیگر
    # جدول را از سقف رد می‌کند
    _t1 = threading.Thread(target=_use, args=(7, 0.35), kwargs={"gate": _in_gate})
    _t1.start()
    _in_gate.wait(2)
    for _o in range(1000, 1070):
        with _CL.hold(_o):
            pass
    check("قفلی که دستِ کسی است هرس نمی‌شود", 7 in _CL._locks,
          "شمارنده‌ی در حال استفاده، ردیف را نگه می‌دارد")

    _t2 = threading.Thread(target=_use, args=(7, 0.05))
    _t2.start()
    _t1.join()
    _t2.join()
    check("یک چت دو بار هم‌زمان پردازش نمی‌شود", _overlap == 0,
          f"{_overlap} هم‌پوشانی")

    # و جدول هنوز کران دارد
    for _o in range(2000, 2200):
        with _CL.hold(_o):
            pass
    check("جدول قفل‌ها هنوز کران دارد", _CL.size() <= 60,
          f"{_CL.size()} ردیف با سقف ۵۰")

    # شمارنده بعد از رهاشدن به صفر برمی‌گردد، وگرنه هیچ ردیفی
    # دیگر هرس‌شدنی نیست و جدول بی‌کران می‌شود
    _CL2 = _RUN.ChatLocks(limit=10)
    for _o in range(50):
        with _CL2.hold(_o):
            pass
    check("ردیف رهاشده دوباره هرس‌شدنی می‌شود", _CL2.size() <= 12,
          f"{_CL2.size()} ردیف — اگر شمارنده صفر نشود، هیچ‌چیز هرس نمی‌شود")

    # ── و اینکه هرس بر چه پایه‌ای تصمیم می‌گیرد ──
    #
    # این یکی عمداً ساختاری است، نه رفتاری.
    #
    # باگِ اصلی در فاصله‌ی بین «تحویل قفل» و «گرفتن قفل» زندگی می‌کرد.
    # با API فعلی آن فاصله از بیرون قابل رسیدن نیست — قفل همان‌جا و
    # همان لحظه گرفته می‌شود — پس هیچ تست رفتاری‌ای نمی‌تواند به آن
    # برسد. این را با برگرداندن عمدیِ شرط قدیمی امتحان کردم: همه‌ی
    # بررسی‌های رفتاری سبز ماندند.
    #
    # پس خودِ قاعده سنجیده می‌شود: تصمیمِ هرس باید بر پایه‌ی شمارنده
    # باشد، نه locked(). قفلی که تحویل داده شده ولی هنوز گرفته نشده،
    # locked() نیست.
    _RUNSRC = io.open(os.path.join(ROOT, "bot", "run.py"),
                      encoding="utf-8").read()
    _hold = _RUNSRC[_RUNSRC.index("def hold(self, cid):"):]
    _hold = _hold[:_hold.index("def size(self)")]
    # فقط خطوط اجرایی، بدون کامنت.
    #
    # اولین نسخه‌ی این بررسی کل فایل را می‌گشت و روی *داکstring
    # خودِ کلاس* افتاد — همان‌جا که نوشته شده بود شرط قدیمی چه بود.
    # تستی که توضیحِ کنار کد راضی‌اش کند، کد را نمی‌سنجد.
    _code = "\n".join(
        (ln.split("#")[0] if "#" in ln else ln)
        for ln in _hold.split("\n"))

    check("هرس بر پایه‌ی شمارنده است، نه locked()",
          "if v[1] == 0]" in _code and "locked()" not in _code,
          "قفلِ تحویل‌داده‌شده‌ی هنوز گرفته‌نشده، locked() نیست")

    check("شمارنده پیش از هرس بالا می‌رود",
          _hold.index("ent[1] += 1") < _hold.index("self._limit"),
          "اگر بعدش باشد، همان ردیف در همان فراخوانی هرس می‌شود")
    check("و شمارنده در finally پایین می‌آید",
          "finally:" in _hold and "ent[1] -= 1" in _hold,
          "وگرنه یک استثنا ردیف را برای همیشه غیرقابل‌هرس می‌کند")

    # شناسه‌ی چت از هر دو شکل آپدیت
    check("شناسه‌ی چت از پیام خوانده می‌شود",
          _RUN.chat_id_of({"message": {"chat": {"id": 55}}}) == 55)
    check("و از دکمه‌ی شیشه‌ای هم",
          _RUN.chat_id_of(
              {"callback_query": {"message": {"chat": {"id": 66}}}}) == 66)
    check("و اگر پیامی نبود، از فرستنده",
          _RUN.chat_id_of({"callback_query": {"from": {"id": 77}}}) == 77,
          "بدون این، همه‌ی چنین آپدیت‌هایی روی یک قفل جمع می‌شدند")


print(f"\n{D}{'─' * 46}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
