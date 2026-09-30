"""
شناسایی آی‌پی: این آدرس مال کیست و آیا خودی است؟

چرا وجود دارد:
    دو سؤال که پنل مدام باید جواب بدهد و تا امروز نمی‌توانست:

    ۱. این اتصال‌های زیاد تانل خودم است یا مشتری؟ تشخیص قبلی فقط
       به نام پردازه در خروجی ss نگاه می‌کرد، و چون ss بدون دسترسی
       کافی نام پردازه را نمی‌دهد، فقط بعضی تانل‌ها شناخته می‌شدند.

    ۲. این آی‌پی که دارد رمز SSH را حدس می‌زند، مشتری من است؟

    درباره‌ی سؤال دوم یک واقعیت را صریح بگوییم: **اگر کسی از VPN
    استفاده کند، آی‌پی واقعی‌اش از بیرون قابل کشف نیست.** هیچ روشی
    وجود ندارد و هر ابزاری که ادعایش را بکند دروغ می‌گوید.

    ولی سؤال واقعی مدیر این نیست که «آی‌پی خانه‌اش چیست»؛ این است
    که «اگر این را ببندم، مشتری‌ام را بسته‌ام؟» و آن سؤال جواب دارد:
    همان آی‌پی را در فهرست آی‌پی‌هایی که کلاینت‌های خودمان با آن
    وصل می‌شوند بگرد. اگر بود، پشت آن VPN یک مشتری نشسته.
"""

import ipaddress
import os
import re
import sqlite3
import time
import logging

_log = logging.getLogger("nexora.netid")

#: موتورهای تانلی که پنل نصب می‌کند یا کاربر ممکن است داشته باشد.
#: backpack و backhaul هر دو در نصب‌های واقعی دیده شده‌اند.
TUNNEL_PROCS = (
    "backhaul", "backpack", "chisel", "rathole", "gost", "frpc", "frps",
    "wireguard", "wg-quick", "wstunnel", "hysteria", "tuic", "udp2raw",
    "iodine", "socat", "haproxy", "stunnel", "openvpn",
)

#: پورت‌هایی که معمولاً سمت تانل‌اند، برای وقتی نام پردازه در دسترس نیست
TUNNEL_PORT_HINT = (8460, 8443, 8445, 8090, 2525, 9090, 3080)


def _run(cmd, timeout=10):
    import subprocess
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return p.returncode == 0, p.stdout or ""
    except Exception:
        return False, ""


def normalize(ip):
    """
    یک آدرس را به شکل استانداردش درمی‌آورد.

    ss گاهی ::ffff:127.0.0.1 می‌دهد که همان 127.0.0.1 است. بدون این
    تبدیل، لوپ‌بک از صافی رد می‌شد و در گزارش سرور واقعی ۲۶٪ کل
    اتصال‌ها را به‌عنوان «پرمصرف‌ترین آی‌پی» نشان می‌داد.
    """
    s = str(ip or "").strip().strip("[]")
    if not s:
        return ""
    try:
        addr = ipaddress.ip_address(s)
    except ValueError:
        return s
    # ::ffff:a.b.c.d → a.b.c.d
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return str(addr.ipv4_mapped)
    return str(addr)


def is_local(ip):
    """لوپ‌بک، شبکه‌ی خصوصی، link-local — هیچ‌کدام مشتری نیستند."""
    s = normalize(ip)
    if not s or s in ("*", "0.0.0.0", "::"):
        return True
    try:
        a = ipaddress.ip_address(s)
    except ValueError:
        return False
    return bool(a.is_loopback or a.is_private or a.is_link_local
                or a.is_multicast or a.is_unspecified)


# ═══════════════════════════════════════════════════════════
#  تانل‌ها
# ═══════════════════════════════════════════════════════════

def tunnel_processes():
    """
    پردازه‌های تانلِ در حال اجرا: {pid: نام}.

    از ps می‌خوانیم چون بر خلاف ss نیازی به دسترسی ویژه ندارد و
    نام کامل دستور را می‌دهد — که برای backpack و backhaul لازم است.
    """
    found = {}
    ok, out = _run(["ps", "-eo", "pid,comm,args", "--no-headers"])
    if not ok:
        return found
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 2:
            continue
        pid, comm = parts[0], parts[1]
        args = parts[2] if len(parts) > 2 else ""
        blob = f"{comm} {args}".lower()
        for eng in TUNNEL_PROCS:
            if eng in blob:
                found[pid] = eng
                break
    return found


def tunnel_ports():
    """
    پورت‌هایی که پردازه‌های تانل روی آن گوش می‌دهند یا وصل‌اند.

    وقتی ss نام پردازه را ندهد، پورت تنها سرنخ باقی‌مانده است:
    هر اتصالی روی پورتی که تانل صاحبش است، ترافیک تانل است.
    """
    ports = set()
    procs = tunnel_processes()
    if not procs:
        return ports

    ok, out = _run(["ss", "-tunlpH"], timeout=10)
    if ok:
        for line in out.splitlines():
            low = line.lower()
            if not any(e in low for e in TUNNEL_PROCS):
                continue
            m = re.search(r":(\d+)\s", line)
            if m:
                ports.add(int(m.group(1)))

    # اگر ss نام پردازه نداد، از /proc خود پردازه‌ها می‌خوانیم
    if not ports:
        for pid in procs:
            try:
                for fd in os.listdir(f"/proc/{pid}/fd"):
                    link = os.readlink(f"/proc/{pid}/fd/{fd}")
                    if "socket" not in link:
                        continue
            except Exception:
                continue
    return ports


def tunnel_peers(extra=None):
    """
    آی‌پی‌هایی که سرِ دیگرِ تانل‌اند: {آی‌پی: توضیح}.

    سه منبع، از مطمئن‌ترین به حدسی‌ترین:
      ۱. نودهای ثبت‌شده در خود پنل — قطعی
      ۲. اتصال‌های متعلق به پردازه‌های تانل — قطعی وقتی ss نام بدهد
      ۳. اتصال روی پورت‌هایی که تانل صاحبشان است — حدس خوب

    extra: آی‌پی‌های اضافی که صدازننده می‌داند تانل‌اند.
    """
    peers = dict(extra or {})

    procs = tunnel_processes()
    if procs:
        ok, out = _run(["ss", "-tunpH", "state", "established"], timeout=10)
        if ok:
            for line in out.splitlines():
                low = line.lower()
                f = line.split()
                if len(f) < 5:
                    continue
                ip = normalize(re.sub(r":\d+$", "", f[4]))
                if not ip or is_local(ip):
                    continue
                eng = next((e for e in TUNNEL_PROCS if e in low), None)
                if eng:
                    peers.setdefault(ip, f"تانل ({eng})")

    tports = tunnel_ports()
    if tports:
        ok, out = _run(["ss", "-tunH", "state", "established"], timeout=10)
        if ok:
            for line in out.splitlines():
                f = line.split()
                if len(f) < 5:
                    continue
                lm = re.search(r":(\d+)$", f[3])
                if not lm or int(lm.group(1)) not in tports:
                    continue
                ip = normalize(re.sub(r":\d+$", "", f[4]))
                if ip and not is_local(ip):
                    peers.setdefault(ip, "تانل (بر اساس پورت)")

    return peers


# ═══════════════════════════════════════════════════════════
#  آیا این آی‌پی مشتری من است؟
# ═══════════════════════════════════════════════════════════

_XUI_PATHS = ("/etc/x-ui/x-ui.db", "/usr/local/x-ui/x-ui.db",
              "/opt/x-ui/x-ui.db", "/usr/local/x-ui/bin/x-ui.db")

_IP_CACHE = {"at": 0.0, "data": {}}
_IP_TTL = 120.0


def client_ips():
    """
    آی‌پی‌هایی که کلاینت‌های خودمان با آن‌ها وصل شده‌اند:
    {آی‌پی: [نام کلاینت, ...]}

    سه منبع:
      · جدول محدودیت آی‌پی در x-ui، اگر روشن باشد
      · لاگ access خود Xray
      · اتصال‌های برقرارِ همین لحظه

    این تنها راه واقعی برای جواب‌دادن به «پشت این VPN مشتری من
    نشسته یا نه» است. آی‌پی واقعیِ کسی که از VPN استفاده می‌کند
    از بیرون قابل کشف نیست — ولی اگر همان آی‌پی را کلاینت‌های ما
    هم استفاده می‌کنند، جواب عملاً بله است.
    """
    now = time.time()
    if _IP_CACHE["data"] and now - _IP_CACHE["at"] <= _IP_TTL:
        return _IP_CACHE["data"]

    out = {}

    def note(ip, who):
        ip = normalize(ip)
        if not ip or is_local(ip):
            return
        out.setdefault(ip, [])
        if who and who not in out[ip]:
            out[ip].append(who)

    # ۱) جدول آی‌پی کلاینت‌ها در x-ui (وقتی limit_ip فعال باشد)
    for p in _XUI_PATHS:
        if not os.path.exists(p):
            continue
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)
            con.row_factory = sqlite3.Row
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for tbl, ipcol, namecol in (
                ("inbound_client_ips", "ips", "client_email"),
                ("client_ips", "ips", "email"),
            ):
                if tbl not in tables:
                    continue
                try:
                    for r in con.execute(f"SELECT {namecol}, {ipcol} FROM {tbl}"):
                        who = r[namecol]
                        for ip in re.findall(r"[0-9a-fA-F:.]{3,45}",
                                             str(r[ipcol] or "")):
                            note(ip, who)
                except Exception as _exc:
                    _log.debug("client ip lookup: %s", _exc)
            con.close()
        except Exception as _exc:
            _log.debug("client ip lookup: %s", _exc)
        break

    # ۲) لاگ دسترسی Xray
    for logp in ("/var/log/x-ui/access.log", "/usr/local/x-ui/access.log",
                 "/var/log/xray/access.log"):
        if not os.path.exists(logp):
            continue
        ok, txt = _run(["tail", "-n", "4000", logp], timeout=10)
        if not ok:
            continue
        for line in txt.splitlines():
            m = re.search(r"from ([0-9a-fA-F:.]+):\d+", line)
            if not m:
                continue
            em = re.search(r"email:\s*(\S+)", line)
            note(m.group(1), em.group(1) if em else "کلاینت")
        break

    # ۳) اتصال‌های همین لحظه
    ok, txt = _run(["ss", "-tunH", "state", "established"], timeout=10)
    if ok:
        for line in txt.splitlines():
            f = line.split()
            if len(f) < 5:
                continue
            note(re.sub(r":\d+$", "", f[4]), "")

    _IP_CACHE["at"] = now
    _IP_CACHE["data"] = out
    return out


def identify(ip, tunnels=None, clients=None):
    """
    یک آی‌پی را دسته‌بندی می‌کند.

    خروجی kind یکی از اینهاست:
      local     شبکه‌ی داخلی — اصلاً مشتری نیست
      tunnel    سرِ دیگر تانل خودتان
      customer  همین آی‌پی را کلاینت‌های شما هم استفاده می‌کنند
      unknown   هیچ نشانی از آشنایی
    """
    n = normalize(ip)
    if not n:
        return {"ip": ip, "kind": "unknown", "why": ""}

    if is_local(n):
        return {"ip": n, "kind": "local",
                "why": "آدرس داخلی خود سرور — نه مشتری، نه مهاجم"}

    tun = (tunnels if tunnels is not None else tunnel_peers())
    if n in tun:
        return {"ip": n, "kind": "tunnel", "why": tun[n],
                "label": tun[n]}

    cl = (clients if clients is not None else client_ips())
    if n in cl:
        who = [w for w in cl[n] if w]
        return {"ip": n, "kind": "customer",
                "clients": who[:5],
                "why": ("این آدرس را کلاینت‌های خودتان هم استفاده می‌کنند"
                        + (f" — {', '.join(who[:3])}" if who else ""))}

    return {"ip": n, "kind": "unknown",
            "why": "هیچ کلاینت شناخته‌شده‌ای با این آدرس وصل نشده"}


def explain_vpn():
    """
    متنی که در رابط کنار بخش مهاجم‌ها نشان داده می‌شود.

    عمداً این‌جا و در یک جا نوشته شده تا اگر روزی کسی خواست ادعای
    بزرگ‌تری بکند، اول مجبور شود این را عوض کند.
    """
    return (
        "اگر کسی از VPN استفاده کند، آدرس واقعی‌اش از بیرون قابل کشف "
        "نیست — نه با این پنل و نه با هیچ ابزار دیگری. ولی سؤال واقعی "
        "شما این نیست؛ سؤال این است که «اگر این را ببندم، مشتری‌ام را "
        "بسته‌ام؟» و آن جواب دارد: همین آدرس را در فهرست آدرس‌هایی که "
        "کلاینت‌های خودتان با آن وصل می‌شوند می‌گردیم. اگر پیدا شود، "
        "پشت آن VPN یک مشتری نشسته."
    )


# ═══════════════════════════════════════════════════════════
#  این آدرس مال کیست؟
# ═══════════════════════════════════════════════════════════

#: نشانه‌های میزبان و ارائه‌دهنده‌ی سرور در نام معکوس.
#: آدرسی که به اینها ختم شود، از یک دیتاسنتر می‌آید نه خانه‌ی کسی —
#: یعنی یا سرور خودتان است، یا VPN، یا ماشینی که اسکن می‌کند.
HOSTING_HINTS = {
    "your-server.de": "Hetzner",
    "hetzner": "Hetzner",
    "contabo": "Contabo",
    "ovh.net": "OVH",
    "ovh.ca": "OVH",
    "digitalocean": "DigitalOcean",
    "vultr": "Vultr",
    "linode": "Linode",
    "amazonaws": "AWS",
    "googleusercontent": "Google Cloud",
    "azure": "Azure",
    "scaleway": "Scaleway",
    "leaseweb": "Leaseweb",
    "hostinger": "Hostinger",
    "m247": "M247",
    "datacamp": "DataCamp",
    "servers.com": "Servers.com",
    "arvancloud": "ArvanCloud",
    "cloudflare": "Cloudflare",
}

#: نشانه‌های اپراتور خانگی/موبایل ایران — یعنی احتمالاً یک آدم واقعی
IRAN_ISP_HINTS = {
    "mci.ir": "همراه اول",
    "irancell": "ایرانسل",
    "rightel": "رایتل",
    "shatel": "شاتل",
    "parsonline": "پارس‌آنلاین",
    "asiatech": "آسیاتک",
    "respina": "رسپینا",
    "tci.ir": "مخابرات",
    "datak": "داتک",
    "pishgaman": "پیشگامان",
}

_RDNS_CACHE = {}
_RDNS_TTL = 3600.0


def rdns_many(ips, timeout=1.2, workers=16, budget=3.0):
    """
    نام معکوس چند آدرس، موازی و با سقف زمانی.

    چرا لازم شد:
        نسخه‌ی سریالی برای هر آدرس تا ۱.۵ ثانیه صبر می‌کرد. صفحه‌ی
        «تلاش برای نفوذ» شصت آدرس دارد، یعنی تا نود ثانیه انتظار —
        صفحه عملاً باز نمی‌شد.

        حالا همه با هم پرسیده می‌شوند و کل کار یک سقف زمانی دارد:
        هرچه تا آن لحظه رسیده استفاده می‌شود و بقیه بدون نام می‌مانند.
        نام معکوس یک اطلاعات کمکی است؛ ارزش معطل‌کردن صفحه را ندارد.
    """
    from concurrent.futures import ThreadPoolExecutor, wait

    out, todo = {}, []
    now = time.time()
    for ip in ips:
        n = normalize(ip)
        if not n or is_local(n):
            continue
        hit = _RDNS_CACHE.get(n)
        if hit and now - hit[0] <= _RDNS_TTL:
            out[n] = hit[1]
        elif n not in todo:
            todo.append(n)

    if not todo:
        return out

    # با «with» کار نمی‌کنیم: خروج از آن shutdown(wait=True) می‌زند و
    # منتظر نخ‌هایی می‌ماند که همین حالا در حال اجرا هستند. یعنی بودجه
    # سقف واقعی نبود — یک resolverِ کند می‌توانست صفحه را همان‌قدر
    # معطل کند که قبل از موازی‌کردن معطل می‌کرد.
    pool = ThreadPoolExecutor(max_workers=min(workers, len(todo)))
    try:
        futures = {pool.submit(rdns, n, timeout): n for n in todo}
        done, pending = wait(futures, timeout=budget)
        for f in done:
            n = futures[f]
            try:
                out[n] = f.result() or ""
            except Exception:
                out[n] = ""
        for f in pending:
            # وقت تمام شد — این آدرس بدون نام می‌ماند، ولی صفحه باز می‌شود.
            # نخی که هنوز می‌دود در پس‌زمینه تمام می‌کند و نتیجه‌اش به
            # کش می‌رود، پس دفعه‌ی بعد رایگان است.
            out.setdefault(futures[f], "")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return out


def rdns(ip, timeout=1.5):
    """
    نام معکوس یک آدرس، با کش.

    مهلت عمداً کوتاه است: این فقط یک اطلاعات کمکی است و نباید
    بارگذاری صفحه را به انتظار DNS بیندازد. آدرس‌های بدون نام
    هم کش می‌شوند تا هر بار دوباره تلاش نشود.
    """
    import socket

    n = normalize(ip)
    if not n or is_local(n):
        return ""

    now = time.time()
    hit = _RDNS_CACHE.get(n)
    if hit and now - hit[0] <= _RDNS_TTL:
        return hit[1]

    # setdefaulttimeout عمداً استفاده *نمی‌شود*.
    #
    # آن مقدار سراسریِ کل پردازه است، نه مالِ این نخ. rdns_many تا
    # شانزده‌تا از همین تابع را هم‌زمان می‌دواند، پس نخ‌ها مقدار
    # همدیگر را به‌عنوان «مقدار قبلی» می‌خواندند و آخری ۱.۲ ثانیه را
    # برای همیشه در پردازه جا می‌گذاشت — روی هر سوکت دیگری هم که
    # بعداً مهلت صریح نداشت.
    #
    # و در عمل هم کاری نمی‌کرد: gethostbyaddr از resolver سیستم
    # استفاده می‌کند و مهلت خودش را دارد. مهارِ زمان کار rdns_many
    # است، نه این‌جا.
    name = ""
    try:
        name = socket.gethostbyaddr(n)[0]
    except Exception:
        name = ""

    _RDNS_CACHE[n] = (now, name)
    return name


def owner(ip, ptr=None):
    """
    آدرس از کجاست: دیتاسنتر، اپراتور ایرانی، یا نامشخص.

    این نزدیک‌ترین چیزی است که می‌شود به «آی‌پی واقعی کاربر» رسید.
    اگر کسی از VPN استفاده کند، آنچه می‌بینیم خروجیِ همان VPN است و
    آدرس خانه‌اش از بیرون در دسترس نیست — ولی دست‌کم می‌فهمیم که
    این یک سرور است نه یک خط خانگی، و همین برای تصمیم‌گیری کافی است:

      · دیتاسنتر + تلاش زیاد  →  اسکنر یا VPN؛ بستنش کم‌خطر است
      · اپراتور ایرانی        →  به‌احتمال زیاد یک آدم واقعی
    """
    n = normalize(ip)
    name = ptr if ptr is not None else rdns(n)
    low = (name or "").lower()

    for needle, label in HOSTING_HINTS.items():
        if needle in low:
            return {"kind": "hosting", "label": label, "ptr": name,
                    "why": f"این آدرس متعلق به {label} است — یک دیتاسنتر، "
                           "نه خط خانگی. یعنی یا سرور است یا خروجی VPN."}

    for needle, label in IRAN_ISP_HINTS.items():
        if needle in low:
            return {"kind": "isp", "label": label, "ptr": name,
                    "why": f"اپراتور {label} — به‌احتمال زیاد یک کاربر "
                           "واقعی، نه سرور."}

    if name:
        return {"kind": "named", "label": name.split(".")[-2:] and
                ".".join(name.split(".")[-2:]), "ptr": name,
                "why": "نام معکوس دارد ولی ارائه‌دهنده‌اش شناخته‌شده نیست."}

    return {"kind": "unknown", "label": "", "ptr": "",
            "why": "نام معکوس ندارد — درباره‌ی صاحبش چیزی نمی‌دانیم."}


def rdns_cached(ips):
    """
    فقط آنچه در کش هست — بدون هیچ پرس‌وجوی شبکه.

    صفحه با این ساخته می‌شود تا فوری باز شود. آدرسی که هنوز پرسیده
    نشده اصلاً در خروجی نمی‌آید، پس صدازننده می‌فهمد باید بعداً
    دوباره بپرسد.
    """
    now = time.time()
    out = {}
    for ip in ips:
        n = normalize(ip)
        if not n:
            continue
        hit = _RDNS_CACHE.get(n)
        if hit and now - hit[0] <= _RDNS_TTL:
            out[n] = hit[1]
    return out


def rdns_warm(ips, timeout=1.2, workers=12):
    """
    کش را در پس‌زمینه پر می‌کند و فوری برمی‌گردد.

    صفحه منتظر نمی‌ماند؛ دفعه‌ی بعد که باز شود نام‌ها آماده‌اند.
    یک نخ daemon است، پس اگر سرویس بسته شود مانع نمی‌شود.
    """
    import threading

    todo = []
    now = time.time()
    for ip in ips:
        n = normalize(ip)
        if not n or is_local(n):
            continue
        hit = _RDNS_CACHE.get(n)
        if (not hit or now - hit[0] > _RDNS_TTL) and n not in todo:
            todo.append(n)
    if not todo:
        return 0

    def work():
        from concurrent.futures import ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=min(workers, len(todo))) as p:
                for n in todo:
                    p.submit(rdns, n, timeout)
        except Exception as _exc:
            _log.warning("ip identify worker pool: %s", _exc)

    t = threading.Thread(target=work, daemon=True)
    t.start()
    return len(todo)
