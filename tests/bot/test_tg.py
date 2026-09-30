#!/usr/bin/env python3
"""
کلاینت تلگرام — به‌ویژه وقتی تلگرام می‌گوید «آهسته‌تر».

چرا وجود دارد:
    call سه بار تلاش می‌کند، و همان سه تا بین خطای شبکه و محدودیت
    نرخ مشترک بود. ولی این دو یکی نیستند: خطای شبکه یعنی چیزی خراب
    است، و ۴۲۹ یعنی تلگرام *صریح* می‌گوید چند ثانیه صبر کن و دوباره
    بفرست.

    بدتر اینکه اگر هر سه تلاش به ۴۲۹ می‌خورد، پیام خطای نهایی
    «شبکه در دسترس نبود: None» بود — چون last_err هیچ‌وقت ست نشده
    بود. مدیری که پیام همگانی می‌فرستاد و چند نفر جا می‌ماندند،
    دنبال مشکل شبکه می‌گشت در حالی که فقط باید آهسته‌تر می‌فرستاد.

اجرا:  python3 tests/bot/test_tg.py
"""
import os
# repo root and bot/ — these tests moved from bot/ to tests/bot/ (2.0 layout)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOT_DIR = os.path.join(_ROOT_DIR, "bot")

import sys

sys.path.insert(0, _BOT_DIR)

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


import tg as T  # noqa: E402

SLEPT = []
T.time.sleep = lambda n: SLEPT.append(n)


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


class _Session:
    """سشن قلابی که دنباله‌ی مشخصی از پاسخ‌ها می‌دهد."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def post(self, url, **kw):
        self.calls += 1
        item = self.script.pop(0) if self.script else self.script_default
        if isinstance(item, Exception):
            raise item
        return _Resp(item)


def bot_with(script):
    b = T.Bot("1:TEST")
    b._session = _Session(script)
    return b


OK = {"ok": True, "result": {"message_id": 1}}
RATE = {"ok": False, "error_code": 429, "description": "Too Many Requests",
        "parameters": {"retry_after": 2}}
BAD = {"ok": False, "error_code": 400, "description": "chat not found"}


# ═══════════════════════════════════════════════════════════
head("مسیر عادی")

b = bot_with([OK])
SLEPT.clear()
check("پیام موفق نتیجه می‌دهد", b.call("sendMessage", chat_id=1) == {"message_id": 1})
check("و بی‌دلیل صبر نمی‌کند", not SLEPT)

head("محدودیت نرخ — صبر و تلاش دوباره")

b = bot_with([RATE, OK])
SLEPT.clear()
res = b.call("sendMessage", chat_id=1)
check("بعد از یک ۴۲۹ پیام می‌رسد", res == {"message_id": 1})
check("به اندازه‌ای که تلگرام گفت صبر می‌کند", SLEPT == [2], str(SLEPT))

b = bot_with([RATE, RATE, RATE, OK])
SLEPT.clear()
res = b.call("sendMessage", chat_id=1)
check("سه بار ۴۲۹ هم پیام را نمی‌اندازد", res == {"message_id": 1},
      "قبلاً سهمیه‌ی تلاش با خطای شبکه مشترک بود و همین‌جا تمام می‌شد")
check("و هر بار صبر کرده", SLEPT == [2, 2, 2], str(SLEPT))

head("وقتی واقعاً کوتاه نمی‌آید")

b = bot_with([RATE] * 12)
SLEPT.clear()
err = None
try:
    b.call("sendMessage", chat_id=1)
except T.TelegramError as e:
    err = e
check("سرانجام تسلیم می‌شود", err is not None)
check("و می‌گوید محدودیت نرخ بود، نه «شبکه»",
      err and "شبکه" not in str(err), str(err)[:70])
check("کد خطا ۴۲۹ است", err and err.code == 429, str(err and err.code))
check("بی‌نهایت تلاش نمی‌کند", len(SLEPT) <= 8, f"{len(SLEPT)} بار صبر")

head("خطای منطقی فوراً بالا می‌رود")

b = bot_with([BAD])
SLEPT.clear()
err = None
try:
    b.call("sendMessage", chat_id=1)
except T.TelegramError as e:
    err = e
check("chat not found تلاش مجدد ندارد", b._session.calls == 1,
      f"{b._session.calls} درخواست")
check("و متنش حفظ می‌شود", err and "chat not found" in str(err))
check("بدون صبر", not SLEPT)

head("خطای شبکه سه بار، بعد تسلیم")

import requests as _rq  # noqa: E402

b = bot_with([_rq.ConnectionError("قطع"), _rq.ConnectionError("قطع"),
              _rq.ConnectionError("قطع")])
SLEPT.clear()
err = None
try:
    b.call("sendMessage", chat_id=1)
except T.TelegramError as e:
    err = e
check("خطای شبکه گزارش می‌شود", err and "شبکه" in str(err), str(err)[:60])
check("سه بار تلاش شده", b._session.calls == 3, f"{b._session.calls} درخواست")

b = bot_with([_rq.ConnectionError("قطع"), OK])
check("و یک قطعی گذرا پیام را نمی‌اندازد",
      b.call("sendMessage", chat_id=1) == {"message_id": 1})


print(f"\n{D}{'─' * 50}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
