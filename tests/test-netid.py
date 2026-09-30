#!/usr/bin/env python3
"""
شناسایی آی‌پی: لوپ‌بک، تانل، و «این مشتری من است؟»

چرا وجود دارد:
    هر باگی که این‌جا می‌سنجیم یک بار روی سرور واقعی دیده شده:

    · ::ffff:127.0.0.1 از صافی رد می‌شد و ۲۶٪ کل اتصال‌ها را
      به‌عنوان «پرمصرف‌ترین آی‌پی» بالای فهرست می‌نشاند
    · backpack و backhaul تانل‌اند ولی شناخته نمی‌شدند
    · تابع _connected_ips کلید "top" را می‌خواند در حالی که
      connections() کلید "byIp" برمی‌گرداند — یعنی تشخیص مشتری
      عملاً هیچ‌وقت کار نکرده بود

اجرا:  python3 tests/test-netid.py
"""
import importlib.util
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


N = load("netid", "backend/netid.py")
NETSRC = io.open(os.path.join(ROOT, "backend", "netid.py"),
                 encoding="utf-8").read()

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


# ═══════════════════════════════════════════════════════════
head("یکسان‌سازی آدرس")

check("::ffff:127.0.0.1 همان 127.0.0.1 است",
      N.normalize("::ffff:127.0.0.1") == "127.0.0.1",
      "روی سرور واقعی ۷۵۱ اتصال بود که مشتری حساب می‌شد")
check("آدرس با براکت پاک می‌شود",
      N.normalize("[2a11:6c7:f39:6b::2]") == "2a11:6c7:f39:6b::2")
check("آی‌پی‌وی۶ فشرده می‌شود",
      N.normalize("2A11:06C7:0F39:006B:0:0:0:2") == "2a11:6c7:f39:6b::2")
check("آدرس ساده دست‌نخورده", N.normalize("95.38.38.14") == "95.38.38.14")
check("ورودی خالی خالی می‌ماند", N.normalize("") == "")
check("متن بی‌ربط نمی‌شکند", N.normalize("سلام") == "سلام")

head("داخلی یا بیرونی")

for ip, want, why in [
    ("::ffff:127.0.0.1", True, "لوپ‌بک نگاشته‌شده — همان باگ سرور"),
    ("127.0.0.1", True, ""),
    ("::1", True, ""),
    ("10.0.0.5", True, "شبکه‌ی خصوصی"),
    ("192.168.1.7", True, ""),
    ("172.16.0.1", True, ""),
    ("169.254.1.1", True, "link-local"),
    ("0.0.0.0", True, ""),
    ("*", True, ""),
    ("95.38.38.14", False, "آی‌پی ایران — مشتری واقعی"),
    ("2a11:6c7:f39:6b::2", False, "آی‌پی‌وی۶ عمومی"),
    ("172.32.0.1", False, "خارج از محدوده‌ی خصوصی"),
]:
    check(f"{ip} {'داخلی' if want else 'عمومی'} است",
          N.is_local(ip) is want, why)

head("موتورهای تانل")

for eng in ("backhaul", "backpack", "chisel", "rathole", "gost",
            "wireguard", "hysteria", "wstunnel"):
    check(f"{eng} شناخته می‌شود", eng in N.TUNNEL_PROCS)
check("فهرست کوتاه نیست", len(N.TUNNEL_PROCS) >= 15,
      f"{len(N.TUNNEL_PROCS)} موتور")

head("دسته‌بندی یک آدرس")

TUN = {"95.38.38.14": "تانل (backhaul)"}
CL = {"5.200.10.20": ["ali_1", "ali_2"], "185.5.5.5": []}

r = N.identify("::ffff:127.0.0.1", tunnels=TUN, clients=CL)
check("لوپ‌بک دسته‌ی local می‌گیرد", r["kind"] == "local")
check("لوپ‌بک نرمال‌شده برمی‌گردد", r["ip"] == "127.0.0.1")

r = N.identify("95.38.38.14", tunnels=TUN, clients=CL)
check("تانل شناخته می‌شود", r["kind"] == "tunnel")
check("نام موتور تانل می‌آید", "backhaul" in r["why"])

r = N.identify("5.200.10.20", tunnels=TUN, clients=CL)
check("مشتری شناخته می‌شود", r["kind"] == "customer")
check("نام کلاینت‌ها برمی‌گردد", r.get("clients") == ["ali_1", "ali_2"])
check("توضیح شامل نام کلاینت است", "ali_1" in r["why"])

r = N.identify("185.5.5.5", tunnels=TUN, clients=CL)
check("کلاینت بی‌نام هم مشتری است", r["kind"] == "customer",
      "آی‌پی در فهرست هست حتی اگر نامش را ندانیم")

r = N.identify("45.9.148.7", tunnels=TUN, clients=CL)
check("آدرس ناشناس ناشناس می‌ماند", r["kind"] == "unknown")
check("دلیل ناشناس‌بودن نوشته می‌شود", "هیچ کلاینت" in r["why"])

head("صداقت درباره‌ی VPN")

note = N.explain_vpn()
check("صریح می‌گوید آدرس پشت VPN قابل کشف نیست",
      "قابل کشف" in note and "نیست" in note,
      "ادعای بیشتر از این، دروغ است")
check("سؤال درست را جای آن می‌گذارد", "مشتری‌ام را" in note)
check("راه‌حل واقعی را توضیح می‌دهد", "کلاینت‌های خودتان" in note)

head("monitor از netid استفاده می‌کند")

MON = io.open(os.path.join(ROOT, "backend", "monitor.py"), encoding="utf-8").read()
check("لوپ‌بک با is_local کنار می‌رود", "_NET.is_local(ip)" in MON)
check("آدرس نرمال می‌شود", "_NET.normalize(" in MON)
check("فهرست ثابت آدرس‌ها حذف شده",
      '("127.0.0.1", "::1", "*", "0.0.0.0")' not in MON)
check("تانل‌ها از netid می‌آیند", "_NET.tunnel_peers(" in MON)
check("بدون netid هم کار می‌کند", "_Fallback" in MON,
      "agent این فایل را تنها اجرا می‌کند")

M = load("monitor", "backend/monitor.py")
check("monitor واقعاً بارگذاری می‌شود", hasattr(M, "snapshot"))
check("backpack در TUNNEL_ENGINES هست", "backpack" in M.TUNNEL_ENGINES)

# ═══════════════════════════════════════════════════════════
head("جست‌وجوی نام معکوس، صفحه را معطل نمی‌کند")

# دو مشکل با هم:
#
#   ۱. rdns با setdefaulttimeout مهلت می‌گذاشت. آن مقدار سراسریِ کل
#      پردازه است، نه مالِ نخ. rdns_many شانزده‌تا را هم‌زمان می‌دواند،
#      پس نخ‌ها مقدار همدیگر را «مقدار قبلی» می‌دیدند و آخری ۱.۲
#      ثانیه را برای همیشه در پردازه جا می‌گذاشت.
#
#   ۲. «with ThreadPoolExecutor» موقع خروج منتظر نخ‌های در حال اجرا
#      می‌ماند. یعنی بودجه سقف واقعی نبود.

import socket as _sock
import time as _t
import threading as _th

_BEFORE = _sock.getdefaulttimeout()

_SLOW = _th.Event()


def _hang(name):
    """جست‌وجویی که جواب نمی‌دهد — مثل DNSِ از کار افتاده."""
    _SLOW.wait(30)
    return ("x", [], ["1.2.3.4"])


_real_gha = _sock.gethostbyaddr
_sock.gethostbyaddr = _hang
N._RDNS_CACHE.clear()

_t0 = _t.time()
_res = N.rdns_many([f"5.200.10.{i}" for i in range(1, 25)],
                   timeout=1.2, workers=8, budget=1.0)
_took = _t.time() - _t0

check("با DNSِ هنگ‌کرده هم سر وقت برمی‌گردد", _took < 3.0,
      f"{_took:.1f} ثانیه با بودجه‌ی ۱ ثانیه")
check("همه‌ی آدرس‌ها جواب دارند — حتی اگر خالی", len(_res) == 24,
      f"{len(_res)} از ۲۴")
check("و نام‌ها خالی‌اند، نه اینکه گم شوند",
      all(v == "" for v in _res.values()))

_SLOW.set()
_t.sleep(0.2)
_sock.gethostbyaddr = _real_gha

check("مهلت سراسری سوکت دست‌نخورده مانده",
      _sock.getdefaulttimeout() == _BEFORE,
      f"{_sock.getdefaulttimeout()} در برابر {_BEFORE}")
# صدازدنِ واقعی را می‌سنجیم، نه متن — کامنتی که توضیح می‌دهد چرا
# استفاده نمی‌شود، خودش شامل همان کلمه است.
check("و کد اصلاً setdefaulttimeout را صدا نمی‌زند",
      "socket.setdefaulttimeout(" not in NETSRC,
      "مقدار سراسری بین نخ‌ها نشت می‌کرد")

head("دسته‌بندی صاحب آدرس")

# این همان تصمیمی است که می‌گوید یک مهاجم دیتاسنتر است یا مشتری شما.
CASES = [
    ("host-5-200-10-20.tehran.mci.ir", "isp"),
    ("abc.hetzner.com", "hosting"),
    ("static.1.2.3.4.clients.your-server.de", "hosting"),
    ("ip-1-2-3-4.pars.ir", "named"),
    ("", "unknown"),
]
for _ptr, _kind in CASES:
    _r = N.owner("1.2.3.4", ptr=_ptr)
    check(f"«{_ptr or 'بدون نام'}» → {_kind}", _r["kind"] == _kind,
          f"{_r['kind']} / {_r['label']}")

check("دیتاسنتر دلیلش را می‌گوید",
      "دیتاسنتر" in N.owner("1.2.3.4", ptr="abc.hetzner.com")["why"])
check("اپراتور ایرانی هم",
      "واقعی" in N.owner("1.2.3.4", ptr="x.mci.ir")["why"],
      "مدیر باید بداند بستن این یعنی از دست دادن مشتری")

_short = [k for k in list(N.HOSTING_HINTS) + list(N.IRAN_ISP_HINTS)
          if len(k) <= 3]
check("هیچ سرنخی آن‌قدر کوتاه نیست که همه را بگیرد", not _short,
      "، ".join(_short) if _short else f"{len(N.HOSTING_HINTS)} دیتاسنتر، "
      f"{len(N.IRAN_ISP_HINTS)} اپراتور")



print(f"\n{D}{'─' * 46}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
