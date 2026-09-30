#!/usr/bin/env python3
"""
تست زمان‌بندی نگهداری و شمارش اتصال‌ها.

چرا وجود دارد:
    این کد می‌تواند سرور فروش را ری‌استارت کند. یک اشتباه در شرط
    پنجره یعنی ریبوت وسط پیک مصرف. پس هر دو نگهبان — «ریبوت بدون
    تایید صریح اجرا نشود» و «وقت شلوغی رد شود» — تست دارند.

اجرا:  python3 tests/test-maintenance.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

G, R, D, X = "\033[38;5;42m", "\033[38;5;203m", "\033[38;5;245m", "\033[0m"
_ok = _fail = 0

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.environ["CONFIG_PATH"] = os.path.join(tempfile.mkdtemp(), "config.json")

import app        # noqa: E402
import monitor    # noqa: E402


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


# ═══════════ زمان‌بندی ═══════════
head("زمان‌بندی نگهداری")

ran = []
app._maint_run = lambda a: (ran.append(a), (True, "شبیه‌سازی"))[1]
app._maint_busy = lambda: (0, 0)
now = datetime.now()


def setup(**kw):
    m = dict(app.MAINT_DEFAULT)
    m.update(kw)
    app._maint_save(m)
    ran.clear()


setup(enabled=False, hour=now.hour, minute=now.minute)
app._maint_tick()
check("وقتی خاموش است اجرا نمی‌شود", ran == [])

setup(enabled=True, hour=now.hour, minute=now.minute)
app._maint_tick()
check("داخل پنجره اجرا می‌شود", ran == ["xray"], str(ran))

_before = list(ran)
app._maint_tick()
check("دو بار در یک روز اجرا نمی‌شود", ran == _before, str(ran))

_t = now + timedelta(hours=3)
setup(enabled=True, hour=_t.hour, minute=_t.minute)
app._maint_tick()
check("خارج از پنجره اجرا نمی‌شود", ran == [])

setup(enabled=True, hour=now.hour, minute=now.minute,
      days=[(now.weekday() + 1) % 7])
app._maint_tick()
check("در روزی که انتخاب نشده اجرا نمی‌شود", ran == [])

setup(enabled=True, hour=now.hour, minute=now.minute, days=[now.weekday()])
app._maint_tick()
check("در روز انتخاب‌شده اجرا می‌شود", ran == ["xray"], str(ran))

head("نگهبان‌های ایمنی")

setup(enabled=True, action="reboot", confirmedReboot=False,
      hour=now.hour, minute=now.minute)
app._maint_tick()
check("ریبوت بدون تایید صریح اجرا نمی‌شود", ran == [], str(ran))

setup(enabled=True, action="reboot", confirmedReboot=True,
      hour=now.hour, minute=now.minute)
app._maint_tick()
check("ریبوت با تایید صریح اجرا می‌شود", ran == ["reboot"], str(ran))

app._maint_busy = lambda: (50, 50)
setup(enabled=True, hour=now.hour, minute=now.minute,
      skipIfBusy=True, busyThreshold=20)
app._maint_tick()
check("وقت شلوغی ری‌استارت نمی‌کند", ran == [])
check("دلیل رد شدن ثبت می‌شود",
      "رد شد" in (app._maint_conf().get("lastResult") or ""),
      app._maint_conf().get("lastResult"))

app._maint_busy = lambda: (5, 5)
setup(enabled=True, hour=now.hour, minute=now.minute,
      skipIfBusy=True, busyThreshold=20)
app._maint_tick()
check("زیر آستانه اجرا می‌شود", ran == ["xray"], str(ran))

head("اعتبارسنجی endpoint")

app.check_auth = lambda pw=None: True
PW = "x"

try:
    app.maintenance_set({"enabled": True, "action": "reboot",
                         "confirmedReboot": False}, PW)
    check("endpoint ریبوت بدون تایید را رد می‌کند", False, "رد نشد")
except Exception as e:
    check("endpoint ریبوت بدون تایید را رد می‌کند",
          getattr(e, "status_code", None) == 400, str(e)[:60])

r = app.maintenance_set({"enabled": True, "action": "reboot",
                         "confirmedReboot": True, "hour": 4}, PW)
check("با تایید پذیرفته می‌شود", r.get("ok") and r["action"] == "reboot")

try:
    app.maintenance_set({"hour": 99}, PW)
    check("ساعت نامعتبر رد می‌شود", False, "رد نشد")
except Exception as e:
    check("ساعت نامعتبر رد می‌شود", getattr(e, "status_code", None) == 400)

try:
    app.maintenance_run_now({"action": "reboot"}, PW)
    check("اجرای دستی ریبوت بدون confirm رد می‌شود", False, "رد نشد")
except Exception as e:
    check("اجرای دستی ریبوت بدون confirm رد می‌شود",
          getattr(e, "status_code", None) == 400)

# ═══════════ اتصال‌ها ═══════════
head("شمارش اتصال‌ها")

SAMPLE = """tcp   0 0 10.0.0.5:443        91.99.12.4:51201
tcp   0 0 10.0.0.5:443        91.99.12.4:51202
tcp   0 0 10.0.0.5:443        91.99.12.4:51203
tcp   0 0 10.0.0.5:8443       5.113.7.9:44001
tcp   0 0 127.0.0.1:5432      127.0.0.1:39112
udp   0 0 10.0.0.5:51820      2.180.3.1:5000
"""
monitor._has = lambda b: True
monitor._run = lambda cmd, timeout=8: (True, SAMPLE)
c = monitor.connections()

check("کل اتصال‌ها شمرده شد", c["total"] == 5, str(c["total"]))
check("لوپ‌بک کنار گذاشته شد",
      all(x["ip"] != "127.0.0.1" for x in c["byIp"]))
check("IPهای یکتا", c["uniqueIps"] == 3, str(c["uniqueIps"]))
check("پرمصرف‌ترین IP اول است",
      c["byIp"][0]["ip"] == "91.99.12.4" and c["byIp"][0]["count"] == 3,
      str(c["byIp"][0]))
check("درصد محاسبه شد", c["byIp"][0]["pct"] == 60.0, str(c["byIp"][0]["pct"]))
check("پرترافیک‌ترین پورت", c["byPort"][0]["port"] == 443, str(c["byPort"][0]))
check("زیر آستانه، هشدار غیرعادی نمی‌دهد", c["heavy"] == [], str(c["heavy"]))

BIG = "".join(f"tcp 0 0 10.0.0.5:443 91.99.12.4:{50000 + i}\n" for i in range(30))
BIG += "".join(f"tcp 0 0 10.0.0.5:443 5.5.5.{i}:44001\n" for i in range(10))
monitor._run = lambda cmd, timeout=8: (True, BIG)
c2 = monitor.connections()
check("IP با سهم غیرعادی علامت می‌خورد",
      any(h["ip"] == "91.99.12.4" for h in c2["heavy"]), str(c2["heavy"]))

monitor._has = lambda b: False
check("بدون ss خالی برمی‌گردد نه خطا", monitor.connections() == {})

print(f"\n{D}{'─' * 46}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
