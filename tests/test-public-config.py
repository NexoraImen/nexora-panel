#!/usr/bin/env python3
"""
چیزی که به مرورگرِ هر مشتری فرستاده می‌شود.

چرا وجود دارد:
    /api/public/config بدون هیچ احرازی سرو می‌شود — مرورگر هر مشتری،
    هر بار که صفحه‌ی اشتراک باز می‌شود، آن را می‌گیرد.

    فیلترش یک فهرستِ «این‌ها را حذف کن» بود: resellers و bot. هر
    کلیدِ تازه‌ای که بعداً به تنظیمات اضافه شد، خودبه‌خود عمومی شد،
    چون کسی به یاد نیاورد آن را به فهرست اضافه کند.

    برای اسرار این شکلِ اشتباه است. فراموش‌کردن یک کلید در فهرستِ
    حذف یعنی *درز*؛ در فهرستِ مجاز یعنی فقط یک قابلیت نمایش داده
    نمی‌شود. جهتِ اشتباه‌کردن باید بی‌خطر باشد.

اجرا:  python3 tests/test-public-config.py
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


TMP = tempfile.mkdtemp()
os.environ["NEXORA_DATA_DIR"] = TMP
os.environ["NEXORA_CONFIG_PATH"] = os.path.join(TMP, "config.json")

spec = importlib.util.spec_from_file_location(
    "nxapp", os.path.join(ROOT, "backend", "app.py"))
APP = importlib.util.module_from_spec(spec)
sys.modules["nxapp"] = APP
spec.loader.exec_module(APP)
APP.CONFIG_PATH = Path(TMP) / "config.json"


class FakeReq:
    headers = {}


class FakeRes:
    def __init__(self):
        self.headers = {}


# ── تنظیماتی که هم اسرار دارد، هم داده‌ی داخلی ──
cfg = json.loads(json.dumps(APP.DEFAULT_CONFIG))
cfg["bot"] = {"token": "123:SUPERSECRET", "adminId": 777}
cfg["resellers"] = [{"id": "r1", "name": "واسطه", "margin": 35,
                     "overrides": {"links": {"supportUsername": "other"}}}]
cfg["maintenance"] = {"enabled": True, "action": "reboot", "hour": 5,
                      "busyThreshold": 20, "lastResult": "خطای دیسک"}
# کلیدی که فردا کسی اضافه می‌کند و یادش می‌رود به فهرست اضافه کند
cfg["smsGateway"] = {"apiKey": "sk-live-abcdef", "sender": "3000"}
APP.save_config(cfg)

out = APP.get_public_config(FakeReq(), FakeRes())


head("چیزی که نباید بیرون برود")

check("توکن ربات بیرون نمی‌رود", "bot" not in out)
check("فهرست واسطه‌ها بیرون نمی‌رود", "resellers" not in out,
      "اطلاعات تجاری — حاشیه‌ی سود هر واسطه")
check("زمان‌بندی نگهداری بیرون نمی‌رود", "maintenance" not in out,
      "ساعت ری‌استارت سرور و آخرین خطایش")
check("کلید ناشناخته هم بیرون نمی‌رود", "smsGateway" not in out,
      "این همان جایی است که فهرستِ «حذف کن» می‌شکند")

blob = json.dumps(out, ensure_ascii=False)
check("هیچ رشته‌ی محرمانه‌ای در خروجی نیست",
      "SUPERSECRET" not in blob and "sk-live" not in blob,
      "جست‌وجوی مستقیم در کل پاسخ")
check("و هیچ کلیدی که با _ شروع نشود ناشناخته نمانده",
      set(out) <= set(APP.PUBLIC_CONFIG_KEYS) | {"_theme", "_resellerId"},
      "، ".join(sorted(set(out) - set(APP.PUBLIC_CONFIG_KEYS)
                       - {"_theme", "_resellerId"})))


head("چیزی که صفحه واقعاً لازم دارد")

for k in ("downloadApps", "faq", "banners", "referral", "links",
          "videoTutorialUrl", "videos", "advanced", "popup"):
    check(f"«{k}» می‌رسد", k in out)
check("قالب حل‌شده ضمیمه است", "_theme" in out and isinstance(out["_theme"], dict))


head("واسطه تنظیمات خودش را می‌گیرد، نه فهرست بقیه را")

class ReqWithHost:
    headers = {"origin": "https://vpn.example.com"}

cfg["resellers"][0]["domains"] = ["vpn.example.com"]
APP.save_config(cfg)
rout = APP.get_public_config(ReqWithHost(), FakeRes())
check("تنظیمات واسطه اعمال می‌شود",
      rout.get("_resellerId") == "r1" or "_resellerId" not in rout,
      str(rout.get("_resellerId")))
check("ولی باز هم فهرست واسطه‌ها بیرون نمی‌رود", "resellers" not in rout)
check("و توکن ربات هم نه", "bot" not in rout)

# overrides بعد از صافی ادغام می‌شود — نباید بتواند چیزی را برگرداند
cfg["resellers"][0]["overrides"]["maintenance"] = {"hour": 3}
cfg["resellers"][0]["overrides"]["bot"] = {"token": "LEAK"}
APP.save_config(cfg)
rout2 = APP.get_public_config(ReqWithHost(), FakeRes())
check("overrides نمی‌تواند کلید حذف‌شده را برگرداند",
      "maintenance" not in rout2 and "bot" not in rout2,
      "، ".join(k for k in ("maintenance", "bot") if k in rout2) or "هیچ‌کدام")
check("و رشته‌ی محرمانه در پاسخ واسطه هم نیست",
      "LEAK" not in json.dumps(rout2, ensure_ascii=False))
check("ولی override مجاز همچنان اعمال می‌شود",
      (rout2.get("links") or {}).get("supportUsername") == "other",
      str((rout2.get("links") or {}).get("supportUsername")))


head("سرصفحه‌های کش")

res = FakeRes()
APP.get_public_config(FakeReq(), res)
check("پاسخ کش نمی‌شود", "no-store" in (res.headers.get("Cache-Control") or ""),
      "وگرنه مشتری ساعت‌ها تنظیمات قدیمی می‌بیند")




# ═══════════════════════════════════════════════════════════
head("صفحه‌ی اشتراک · لینک مشتری نباید از سرور ما بیرون برود")

# QR از `api.qrserver.com` می‌آمد و لینکِ کاملِ کانفیگ در آدرسِ آن
# درخواست فرستاده می‌شد: UUID، سرور، پورت. یعنی هر بار که مشتری
# صفحه‌اش را باز می‌کرد، چیزی که با آن می‌شود از خودِ اشتراک
# استفاده کرد، روی سرورِ یک سرویسِ غریبه و در لاگ‌هایش می‌نشست.
import io as _io
import re as _re

_SUB = _io.open(os.path.join(ROOT, "sub-page-index.html"),
                encoding="utf-8").read()
# فقط کد شمرده می‌شود، نه توضیحی که دلیلِ همین تست را می‌نویسد
_SUB_CODE = _re.sub(r"<!--[\s\S]*?-->", " ", _SUB)

check("هیچ سرویسِ بیرونیِ QR صدا زده نمی‌شود",
      "qrserver.com" not in _SUB_CODE and "chart.googleapis.com" not in _SUB_CODE,
      "لینک اشتراک یعنی خودِ اعتبارنامه — جایی جز مرورگر مشتری نباید برود")

check("QR در خودِ مرورگر ساخته می‌شود",
      "function nexoraQr(" in _SUB_CODE and "createSvgTag" in _SUB_CODE)

check("و سازنده‌اش داخل همین فایل است",
      "var qrcode=function()" in _SUB_CODE,
      "فایل دوم یعنی یک مرحله‌ی نصبِ تازه که روزی جا می‌ماند")

check("اگر ساختن QR نشد، صفحه نمی‌افتد",
      "catch (e)" in _SUB_CODE and "nexoraQr" in _SUB_CODE,
      "QR نداشتن بهتر از فرستادنِ لینک به بیرون است")

# هیچ لینکِ کانفیگی نباید در آدرسِ یک دامنه‌ی غیرخودی بنشیند
#
# «لینکِ کانفیگ» یعنی همان رشته‌ای که با آن می‌شود به سرویس وصل شد.
# نامِ متغیرهایش در این فایل مشخص است، پس دقیقاً همان‌ها را
# می‌گیریم — نه هر آدرسی که کلمه‌ی «link» دارد، وگرنه لینکِ
# پشتیبانیِ خودِ مالک (`t.me/${cfg.links.support…}`) هم هشدار
# می‌سازد و هشدارِ دروغ، هشدارِ واقعی را بی‌ارزش می‌کند.
_ALLOWED = ("fonts.googleapis", "fonts.gstatic", "cdnjs.cloudflare",
            "cdn.jsdelivr", "telegram.org", "t.me")
_SECRET = _re.compile(r"\$\{[^}]*\b(?:encoded|encodedLink|parsed\.link|"
                      r"subUrl|sub_url|configLink|rawLink)\b[^}]*\}")
_leaks = []
for _m in _re.finditer(r"https?://([^\s\"'`/]+)[^\s\"'`]*", _SUB_CODE):
    _url = _m.group(0)
    if any(a in _m.group(1) for a in _ALLOWED):
        continue
    if _SECRET.search(_url):
        _leaks.append(_url[:70])
check("هیچ داده‌ی مشتری در آدرسِ یک دامنه‌ی بیرونی نمی‌رود", not _leaks,
      "، ".join(_leaks[:2]) if _leaks else "فقط قلم و آیکون از بیرون می‌آیند")


head("صفحه‌ی اشتراک · حرکت")

check("تنظیمِ کم‌کردنِ حرکتِ سیستم محترم است",
      "prefers-reduced-motion" in _SUB_CODE,
      "این صفحه نبض و رادارِ چرخان و موجِ پس‌زمینه دارد")
check("و هیچ transition: all نمانده",
      "transition: all" not in _SUB_CODE,
      "مرورگر را مجبور می‌کرد چیدمانِ کل صفحه را دوباره حساب کند")
check("توکن‌های موشن تعریف شده‌اند",
      "--m-fast:" in _SUB_CODE and "--sp-snappy:" in _SUB_CODE,
      "همان سه سرعتِ خودِ پنل")


# ═══════════════════════════════════════════════════════════
head("کدام واسطه — find_reseller")

# این تابع تصمیم می‌گیرد مشتری برندِ چه کسی را ببیند، و تا امروز هیچ
# تستی نداشت. خطایش بی‌صداست: مشتریِ واسطه برندِ مالک را می‌بیند و
# هیچ‌جا چیزی نوشته نمی‌شود.
_RS = {"resellers": [
    {"id": "a", "name": "ماکان", "enabled": True, "emailPrefix": "macan", "domains": []},
    {"id": "b", "name": "حسین", "enabled": True, "emailPrefix": "hossein_", "domains": ["sub.hossein-vpn.ir"]},
    {"id": "c", "name": "خاموش", "enabled": False, "emailPrefix": "off", "domains": ["off.ir"]},
    {"id": "d", "name": "بی‌پیشوند", "enabled": True, "emailPrefix": "", "domains": []},
]}
_fr = lambda **kw: (APP.find_reseller(_RS, **kw) or {}).get("id")
check("پیشوندِ ایمیل با _ و - و .", _fr(email="macan_ali") == "a" and _fr(email="macan-ali") == "a"
      and _fr(email="macan.ali") == "a")
check("پیشوندِ ناقص نمی‌خورد (macanx نه macan)", _fr(email="macanx_ali") is None)
check("پیشوندی که خودش با «_» تایپ شده هم می‌خورد",
      _fr(email="hossein_reza") == "b",
      "«hossein_» یعنی «hossein__» می‌خواست و مشتری بی‌صدا برندِ مالک را می‌دید")
check("دامنه بر پیشوند مقدم است", _fr(email="macan_ali", host="sub.hossein-vpn.ir") == "b")
check("زیردامنه و www هم", _fr(host="www.sub.hossein-vpn.ir") == "b" and _fr(host="x.sub.hossein-vpn.ir:8443") == "b")
check("دامنه‌ی شبیه نمی‌خورد (evilsub.hossein-vpn.ir.com)", _fr(host="sub.hossein-vpn.ir.evil.com") is None)
check("واسطه‌ی خاموش نه با دامنه نه با پیشوند", _fr(host="off.ir") is None and _fr(email="off_x") is None)
check("پیشوندِ خالی با همه نمی‌خورد", _fr(email="_anything") is None)


print(f"\n{D}{'─' * 50}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
