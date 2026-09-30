"""
مانیتورینگ زنده‌ی سرور — مخصوص سروری که کارش VPN است.

فرق این با health.py:
    health.py یک عکس لحظه‌ای «سالم/ناسالم» می‌دهد. این ماژول عددها را
    هم می‌دهد: چقدر مصرف می‌شود، چه چیزی مصرف می‌کند، ترافیک در هر
    ثانیه چقدر است، چند نفر وصل‌اند، چه پورت‌هایی باز است.

    و مهم‌تر: هر عدد با «آستانه» و «چرا مهم است» می‌آید. عدد خام بدون
    مرجع بی‌فایده است — کسی که load=3 را می‌بیند نمی‌داند خوب است یا
    بد، مگر اینکه بداند سرور چند هسته دارد.

اصل کار:
    فقط دستورهای خواندنی از یک فهرست ثابت. هیچ ورودی کاربر به شل
    نمی‌رود.

اجرای مستقیم برای دیباگ:
    python3 backend/monitor.py
"""
import ipaddress
import json
import os
import re
import shutil
import subprocess
import time
import logging

_log = logging.getLogger("nexora.monitor")


def _load_netid():
    """
    ماژول شناسایی آی‌پی، با جایگزین داخلی.

    این فایل را agent روی سرورهای دیگر به‌تنهایی دانلود و اجرا
    می‌کند، جایی که netid.py ممکن است کنارش نباشد. پس نبودنش نباید
    مانیتورینگ را از کار بیندازد — یک نسخه‌ی کوچک از همان کارها
    این‌جا هست تا دست‌کم لوپ‌بک درست کنار گذاشته شود.
    """
    try:
        import netid
        return netid
    except ImportError:
        pass
    try:
        import importlib.util
        from pathlib import Path
        p = Path(__file__).resolve().parent / "netid.py"
        if p.exists():
            spec = importlib.util.spec_from_file_location("netid", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    except Exception:
        pass

    class _Fallback:
        #: باید *دقیقاً* با netid.TUNNEL_PROCS یکی باشد.
        #
        #  این فهرست تعیین می‌کند کدام اتصال «تانل خودمان» است. تانل‌ها
        #  از ترافیک مشتری جدا می‌شوند (وگرنه صدها اتصالِ سرور ایران
        #  همیشه «غیرعادی» به نظر می‌رسد) و از بستنِ دسته‌ای هم مصون
        #  می‌مانند.
        #
        #  یعنی نامی که این‌جا جا بیفتد، اتصالِ تانلِ خودتان را به
        #  «مشتریِ پرمصرف» تبدیل می‌کند — و آن یکی از فهرست محافظت‌شده
        #  بیرون می‌ماند.
        #
        #  سه نام (openvpn، iodine، udp2raw) واقعاً جا افتاده بودند:
        #  به netid اضافه شدند و به این کپی نه. تست اکنون برابری این دو
        #  را اجرا می‌کند.
        TUNNEL_PROCS = ("backhaul", "backpack", "chisel", "rathole", "gost",
                        "frpc", "frps", "wireguard", "wg-quick", "wstunnel",
                        "hysteria", "tuic", "udp2raw", "iodine", "socat",
                        "haproxy", "stunnel", "openvpn")

        @staticmethod
        def normalize(ip):
            s = str(ip or "").strip().strip("[]")
            if not s:
                return ""
            try:
                a = ipaddress.ip_address(s)
            except ValueError:
                return s
            if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
                return str(a.ipv4_mapped)
            return str(a)

        @classmethod
        def is_local(cls, ip):
            s = cls.normalize(ip)
            if not s or s in ("*", "0.0.0.0", "::"):
                return True
            try:
                a = ipaddress.ip_address(s)
            except ValueError:
                return False
            return bool(a.is_loopback or a.is_private or a.is_link_local
                        or a.is_multicast or a.is_unspecified)

        @staticmethod
        def tunnel_peers(extra=None):
            return dict(extra or {})

    return _Fallback


_NET = _load_netid()

OK, WARN, CRIT = "ok", "warn", "crit"

#: فاصله‌ی دو نمونه برای محاسبه‌ی نرخ (ثانیه). کوتاه، چون کاربر
#: منتظر پاسخ صفحه است.
SAMPLE = 0.6


def _run(cmd, timeout=8):
    """اجرای دستور خواندنی. همیشه فهرست، نه رشته — تا shell دخالت نکند."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception:
        return False, ""


def _read(path, default=""):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return default


def _has(binary):
    return shutil.which(binary) is not None


def _level(value, warn, crit):
    """سطح بر اساس دو آستانه. بالاتر یعنی بدتر."""
    if value is None:
        return OK
    if value >= crit:
        return CRIT
    if value >= warn:
        return WARN
    return OK


def _metric(key, title, value, unit="", level=OK, detail="", why="",
            hint="", pct=None, extra=None):
    """
    یک سنجه.

    why: چرا این عدد مهم است و از کجا به بعد خطرناک می‌شود. بدون این،
         ادمین عدد را می‌بیند و نمی‌داند باید نگران باشد یا نه — که
         دقیقاً همان چیزی است که آدم را از مانیتورینگ فراری می‌دهد.
    """
    return {"key": key, "title": title, "value": value, "unit": unit,
            "level": level, "detail": detail, "why": why, "hint": hint,
            "pct": pct, "extra": extra or {}}


_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa(v):
    """فارسی‌کردن ارقام. متن‌های این ماژول را ادمین می‌خواند، نه کپی می‌کند."""
    return str(v).translate(_FA)


def _hb(n):
    """بایت خوانا، با ارقام فارسی."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    for u in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or u == "PB":
            return _fa(f"{n:.1f}") + f" {u}" if u != "B" else _fa(int(n)) + " B"
        n /= 1024
    return _fa(f"{n:.1f}") + " PB"


# ═══════════════════════════════════════════════════════════
#  پردازنده و بار
# ═══════════════════════════════════════════════════════════

def _cpu_times():
    line = _read("/proc/stat").split("\n")[0]
    parts = [float(x) for x in line.split()[1:] if x.replace(".", "").isdigit()]
    if len(parts) < 4:
        return None
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    return sum(parts), idle


def sample_rates():
    """
    یک خواب، دو شمارنده.

    هم CPU و هم شبکه نرخ‌اند: باید دو بار خوانده شوند و بینشان صبر
    شود. قبلاً هر کدام خواب خودش را داشت، یعنی هر عکس‌برداری ۱.۲
    ثانیه فقط منتظر می‌ماند — در حالی که همان یک پنجره برای هر دو
    کافی است.

    برمی‌گرداند: {"cpu": (قبل, بعد), "net": (قبل, بعد)}
    """
    c0, n0 = _cpu_times(), _net_counters()
    time.sleep(SAMPLE)
    return {"cpu": (c0, _cpu_times()), "net": (n0, _net_counters())}


def cpu(sample=None):
    cores = os.cpu_count() or 1

    if sample:
        a, b = sample
    else:
        a = _cpu_times()
        time.sleep(SAMPLE)
        b = _cpu_times()

    usage = None
    if a and b:
        dt, di = b[0] - a[0], b[1] - a[1]
        if dt > 0:
            usage = round(max(0.0, min(100.0, (1 - di / dt) * 100)), 1)

    out = [_metric(
        "cpu", "مصرف پردازنده", usage, "٪",
        _level(usage, 75, 92), f"{_fa(usage)}٪ از {_fa(cores)} هسته" if usage is not None else "—",
        "بالای ۷۵٪ یعنی سرور دارد به سقف می‌رسد و تأخیر کاربران بالا می‌رود. "
        "بالای ۹۲٪ یعنی همین حالا کند شده.",
        "با «سنگین‌ترین پردازه‌ها» پایین ببینید چه چیزی مصرف می‌کند.",
        pct=usage, extra={"cores": cores})]

    try:
        l1, l5, l15 = os.getloadavg()
        per = round(l1 / cores, 2)
        out.append(_metric(
            "load", "بار سیستم", round(l1, 2), "",
            _level(per, 1.0, 2.0),
            _fa(f"{l1:.2f} · {l5:.2f} · {l15:.2f}") + "  (۱ و ۵ و ۱۵ دقیقه)",
            f"این عدد را باید بر تعداد هسته‌ها تقسیم کرد. سرور شما {_fa(cores)} هسته "
            f"دارد، پس بار {_fa(cores)} یعنی دقیقاً پر. الان {_fa(per)} برابر ظرفیت است.",
            "اگر بار بالاست ولی مصرف پردازنده پایین، معمولاً دیسک یا شبکه گلوگاه است.",
            pct=min(100, round(per * 100)), extra={"per_core": per,
                                                   "l5": round(l5, 2),
                                                   "l15": round(l15, 2)}))
    except Exception:
        pass

    return out


def top_processes(n=8):
    """سنگین‌ترین پردازه‌ها بر اساس پردازنده و حافظه."""
    ok, out = _run(["ps", "-eo", "pid,comm,%cpu,%mem,etimes", "--sort=-%cpu"])
    if not ok:
        return []
    rows = []
    for line in out.strip().split("\n")[1:n + 1]:
        p = line.split(None, 4)
        if len(p) < 5:
            continue
        try:
            rows.append({"pid": int(p[0]), "name": p[1],
                         "cpu": float(p[2]), "mem": float(p[3]),
                         "uptime": int(p[4])})
        except ValueError:
            continue
    return rows


# ═══════════════════════════════════════════════════════════
#  حافظه و دیسک
# ═══════════════════════════════════════════════════════════

def memory():
    info = {}
    for line in _read("/proc/meminfo").split("\n"):
        m = re.match(r"(\w+):\s+(\d+)", line)
        if m:
            info[m.group(1)] = int(m.group(2)) * 1024

    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    used = total - avail
    pct = round(used * 100 / total, 1) if total else None

    out = [_metric(
        "memory", "حافظه", pct, "٪", _level(pct, 85, 95),
        f"{_hb(used)} از {_hb(total)} — {_hb(avail)} آزاد",
        "بالای ۸۵٪ یعنی فضای مانور کم شده. اگر پر شود، هسته پردازه‌ها را "
        "می‌کشد و Xray هم می‌تواند قربانی شود — یعنی قطعی سرویس.",
        "اگر همیشه بالاست، یا مصرف واقعی زیاد است یا نشتی حافظه دارید.",
        pct=pct, extra={"total": total, "used": used, "available": avail})]

    st, sf = info.get("SwapTotal", 0), info.get("SwapFree", 0)
    if st:
        su = st - sf
        spct = round(su * 100 / st, 1)
        out.append(_metric(
            "swap", "حافظه‌ی مجازی", spct, "٪", _level(spct, 40, 75),
            f"{_hb(su)} از {_hb(st)}",
            "استفاده‌ی زیاد از swap یعنی رم واقعی کم آمده. سرور کار می‌کند "
            "ولی کند — و برای VPN، کندی یعنی شکایت کاربر.",
            "اگر مدام بالاست، رم سرور را زیاد کنید."))
    return out


def disks():
    ok, out = _run(["df", "-PB1"])
    if not ok:
        return []
    rows = []
    for line in out.strip().split("\n")[1:]:
        p = line.split()
        if len(p) < 6 or not p[0].startswith("/"):
            continue
        try:
            total, used, avail = int(p[1]), int(p[2]), int(p[3])
        except ValueError:
            continue
        if total < 100 * 1024 ** 2:      # پارتیشن‌های ریز سیستمی
            continue
        pct = round(used * 100 / total, 1) if total else 0
        rows.append(_metric(
            f"disk:{p[5]}", f"دیسک {p[5]}", pct, "٪", _level(pct, 80, 92),
            f"{_hb(used)} از {_hb(total)} — {_hb(avail)} آزاد",
            "دیسک پر یعنی لاگ نوشته نمی‌شود، دیتابیس ربات خطا می‌دهد و "
            "بک‌آپ ساخته نمی‌شود. زیر ۸٪ آزاد وارد منطقه‌ی خطر می‌شوید.",
            "بزرگ‌ترین مصرف‌کننده معمولاً لاگ‌هاست: journalctl --vacuum-size=200M",
            pct=pct, extra={"mount": p[5], "total": total, "used": used}))
    return rows


# ═══════════════════════════════════════════════════════════
#  شبکه — مهم‌ترین بخش برای سرور VPN
# ═══════════════════════════════════════════════════════════

def _net_counters():
    res = {}
    for line in _read("/proc/net/dev").split("\n")[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        if name == "lo" or name.startswith(("veth", "docker", "br-")):
            continue
        f = rest.split()
        if len(f) >= 9:
            try:
                res[name] = (int(f[0]), int(f[8]))
            except ValueError:
                pass
    return res


def network(sample=None):
    if sample:
        a, b = sample
    else:
        a = _net_counters()
        time.sleep(SAMPLE)
        b = _net_counters()

    rx = tx = 0
    per_if = []
    for name, (rx1, tx1) in b.items():
        rx0, tx0 = a.get(name, (rx1, tx1))
        r = max(0, int((rx1 - rx0) / SAMPLE))
        t = max(0, int((tx1 - tx0) / SAMPLE))
        rx += r
        tx += t
        per_if.append({"name": name, "rx": r, "tx": t,
                       "rxTotal": rx1, "txTotal": tx1})
    per_if.sort(key=lambda x: x["rx"] + x["tx"], reverse=True)

    total = rx + tx
    mbps = round(total * 8 / 1_000_000, 1)

    out = [_metric(
        "throughput", "ترافیک لحظه‌ای", mbps, "Mbps",
        _level(mbps, 700, 940),
        f"دریافت {_hb(rx)}/s · ارسال {_hb(tx)}/s",
        "این همان چیزی است که مشتری‌های شما دارند مصرف می‌کنند. اگر به سقف "
        "پورت سرور (معمولاً ۱ گیگابیت) نزدیک شود، سرعت همه افت می‌کند.",
        "اگر مدام نزدیک سقف است، یا کاربر را کم کنید یا پورت بالاتر بگیرید.",
        pct=min(100, round(mbps / 10)), extra={"rx": rx, "tx": tx,
                                               "interfaces": per_if[:5]})]

    # تعداد اتصال‌های برقرار — معیار مستقیم «چند نفر الان وصل‌اند»
    est = None
    if _has("ss"):
        ok, o = _run(["ss", "-tun", "state", "established"])
        if ok:
            est = max(0, len(o.strip().split("\n")) - 1)
    if est is not None:
        out.append(_metric(
            "connections", "اتصال‌های فعال", est, "",
            _level(est, 3000, 9000), f"{_fa(est)} اتصال برقرار",
            "هر کاربر VPN معمولاً چند اتصال هم‌زمان باز می‌کند. عدد خیلی بالا "
            "یا می‌گوید کاربر زیاد دارید، یا کسی دارد سوءاستفاده می‌کند.",
            "برای دیدن پرمصرف‌ترین IPها: ss -tn state established | awk '{print $5}'"))

    # نشست‌های TIME-WAIT — نشانه‌ی فشار یا حمله
    if _has("ss"):
        ok, o = _run(["ss", "-tan"])
        if ok:
            tw = o.count("TIME-WAIT")
            sw = o.count("SYN-RECV")
            if sw > 200:
                out.append(_metric(
                    "synflood", "اتصال‌های نیمه‌باز", sw, "",
                    _level(sw, 200, 800), f"{_fa(sw)} اتصال در حالت SYN-RECV",
                    "تعداد زیاد اتصال نیمه‌باز معمولاً یعنی حمله‌ی SYN flood — "
                    "کسی دارد سرور را با درخواست‌های ناتمام خسته می‌کند.",
                    "فعال‌کردن syncookies: sysctl -w net.ipv4.tcp_syncookies=1"))
            elif tw > 8000:
                out.append(_metric(
                    "timewait", "نشست‌های در حال بسته‌شدن", tw, "",
                    WARN, f"{_fa(tw)} نشست TIME-WAIT",
                    "عدد خیلی بالا یعنی اتصال‌ها سریع باز و بسته می‌شوند و "
                    "ممکن است پورت‌های سرور ته بکشد.",
                    "معمولاً با تنظیم tcp_tw_reuse حل می‌شود."))
    return out



def _is_loopback(host):
    """فقط ۱۲۷.x و ::۱ — نه هر آدرس خصوصی."""
    try:
        return ipaddress.ip_address(str(host).strip("[]")).is_loopback
    except ValueError:
        return str(host).strip("[]").lower() in ("localhost", "")


def listening():
    """
    پورت‌های باز رو به اینترنت — سطح حمله‌ی شما.

    هر پورت باز یک در است. ادمینی که نمی‌داند چه درهایی باز است،
    نمی‌تواند بداند از کجا ضربه می‌خورد.
    """
    if not _has("ss"):
        return []
    ok, out = _run(["ss", "-tulpnH"])
    if not ok:
        return []

    #: پورت‌هایی که برای این سرویس طبیعی‌اند
    known = {22: "SSH", 80: "HTTP", 443: "HTTPS", 2053: "پنل/کلادفلر",
             2083: "کلادفلر", 2087: "کلادفلر", 2096: "اشتراک",
             8443: "Xray", 51820: "WireGuard"}

    rows = []
    seen = set()
    for line in out.strip().split("\n"):
        f = line.split()
        if len(f) < 5:
            continue
        proto, local = f[0], f[4]
        m = re.search(r":(\d+)$", local)
        if not m:
            continue
        port = int(m.group(1))
        host = local[:m.start()]

        # «عمومی» یعنی از بیرون این ماشین قابل دسترسی — نه فقط
        # ۰.۰.۰.۰ و *.
        #
        # فهرست ثابت قبلی هر سرویسی را که به آی‌پی مشخصِ خود سرور
        # بسته شده بود «غیرعمومی» می‌دید، و چون suggest و preflight
        # پورت‌های غیرعمومی را رد می‌کنند، آن سرویس‌ها اصلاً در
        # فایروال دیده نمی‌شدند. تانل‌ها دقیقاً همین‌طور بسته
        # می‌شوند — پس درست همان‌هایی که بیشتر اهمیت داشتند غایب
        # بودند.
        bare = host.strip("[]")
        if bare in ("0.0.0.0", "*", "::", ""):
            public = True
            scope = "همه‌ی رابط‌ها"
        elif _is_loopback(bare):
            # فقط لوپ‌بک واقعاً بیرون از این ماشین در دسترس نیست.
            #
            # آدرس خصوصی (۱۰.x یا ۱۹۲.۱۶۸.x) را ufw هم فیلتر می‌کند،
            # پس اگر «غیرعمومی» حسابش کنیم، بررسی پیش از روشن‌کردن
            # فایروال آن را نمی‌بیند و همان سرویس قطع می‌شود.
            public = False
            scope = "فقط روی خود سرور"
        else:
            public = True
            scope = f"روی {bare}"

        proc = ""
        pm = re.search(r'users:\(\("([^"]+)"', line)
        if pm:
            proc = pm.group(1)
        key = (port, proto, proc)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"port": port, "proto": proto, "process": proc,
                     "public": public, "bind": bare, "scope": scope,
                     "known": known.get(port, ""),
                     "risk": "high" if (public and port not in known
                                        and port < 1024) else
                             ("medium" if public and port not in known else "low")})
    rows.sort(key=lambda r: (r["risk"] != "high", r["risk"] != "medium", r["port"]))
    return rows


#: کش پیرهای تانل. نودها ماه‌ها ثابت‌اند، ولی بدون کش هر بار
#: نمونه‌گیری یک `ss` اضافه اجرا می‌شد — روی صفحه‌ای که هر ۸ ثانیه
#: تازه می‌شود، همان یکی هم بار بی‌دلیل است.
_PEERS_CACHE = {"at": 0.0, "data": {}}
_PEERS_TTL = 120


def _tunnel_peers():
    """
    آی‌پی‌هایی که خودِ ما به آن‌ها تانل داریم.

    این‌ها ذاتاً اتصال زیاد دارند — کل ترافیک مشتری‌های ایران از
    همین‌ها رد می‌شود. بدون شناختنشان، همیشه بالای فهرست «مصرف
    غیرعادی» می‌نشینند و مدیر را دنبال نخود سیاه می‌فرستند.

    منبع: دیتابیس تانل پنل، به‌علاوه‌ی هر پیری که پردازه‌اش یکی از
    موتورهای شناخته‌شده‌ی تانل باشد.
    """
    now = time.time()
    if now - _PEERS_CACHE["at"] < _PEERS_TTL:
        return _PEERS_CACHE["data"]

    peers = {}

    # ۱) از دیتابیس تانل
    for p in ("/opt/nexora/data/tunnels.db", "/opt/nexora-panel/data/tunnels.db"):
        if not os.path.exists(p):
            continue
        try:
            import sqlite3
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)
            con.row_factory = sqlite3.Row
            try:
                rows = con.execute(
                    "SELECT host, name FROM nodes WHERE host IS NOT NULL").fetchall()
                for r in rows:
                    h = (r["host"] or "").strip()
                    if h:
                        peers[h] = r["name"] or "نود تانل"
            except Exception as _exc:
                _log.debug("tunnel peers query: %s", _exc)
            con.close()
        except Exception:
            pass
        break

    # ۲) از روی پردازه‌های موتور تانل که اتصال باز دارند
    if _has("ss"):
        ok, out = _run(["ss", "-tunpH", "state", "established"], timeout=10)
        if ok:
            for line in out.splitlines():
                low = line.lower()
                if not any(e in low for e in TUNNEL_ENGINES):
                    continue
                f = line.split()
                if len(f) < 5:
                    continue
                m = re.match(r"^(.*):(\d+)$", f[4])
                if m:
                    peers.setdefault(m.group(1).strip("[]"), "موتور تانل")

    _PEERS_CACHE["at"] = now
    _PEERS_CACHE["data"] = peers
    return peers


#: نام پردازه‌ی موتورهای تانلی که پنل نصب می‌کند.
#: فهرست کامل‌تر در netid.TUNNEL_PROCS است؛ این‌جا فقط برای
#: سازگاری با کدی که از قبل به آن ارجاع می‌دهد باقی مانده.
TUNNEL_ENGINES = _NET.TUNNEL_PROCS


def connections(top=8):
    """
    اتصال‌های برقرار — چه کسی دارد از سرور استفاده می‌کند.

    پورت باز می‌گوید «چه دری باز است»؛ این می‌گوید «الان چه کسی از
    آن در تو آمده». برای فروشنده‌ی VPN مهم‌ترین سؤال همین است: وقتی
    سرور کند می‌شود، کدام IP بیشترین سهم را دارد.

    تانل‌ها جدا حساب می‌شوند: سرور ایرانِ خودتان ذاتاً صدها اتصال
    دارد و اگر کنار مشتری‌ها بنشیند، همیشه «غیرعادی» به نظر می‌رسد
    و هشدار واقعی را زیر نویز دفن می‌کند.

    خروجی:
      total      کل اتصال‌های برقرار
      uniqueIps  چند IP یکتا
      byIp       پرمصرف‌ترین IPها با تعداد اتصال
      byPort     پرترافیک‌ترین پورت‌های محلی
      heavy      IPهایی که سهمشان غیرعادی است (بدون تانل‌ها)
      tunnels    اتصال‌های تانل، جدا
    """
    if not _has("ss"):
        return {}

    ok, out = _run(["ss", "-tunH", "state", "established"], timeout=10)
    if not ok:
        return {}

    by_ip, by_port = {}, {}
    total = 0
    for line in out.strip().split("\n"):
        f = line.split()
        # ss: netid recv send local:port peer:port
        if len(f) < 5:
            continue
        local, peer = f[3], f[4]

        lm = re.search(r":(\d+)$", local)
        pm = re.search(r"^(.*):(\d+)$", peer)
        if not lm or not pm:
            continue

        ip = _NET.normalize(pm.group(1))
        # اتصال‌های داخلی خودِ سرور، مصرف مشتری نیستند.
        #
        # صافیِ قبلی فهرست ثابتی از آدرس‌ها بود و ::ffff:127.0.0.1 را
        # نمی‌گرفت — روی سرور واقعی همان یک مورد ۲۶٪ کل اتصال‌ها را
        # به‌عنوان «پرمصرف‌ترین آی‌پی» بالای فهرست می‌نشاند.
        if _NET.is_local(ip):
            continue

        total += 1
        by_ip[ip] = by_ip.get(ip, 0) + 1
        lp = int(lm.group(1))
        by_port[lp] = by_port.get(lp, 0) + 1

    if not total:
        return {"total": 0, "uniqueIps": 0, "byIp": [], "byPort": [], "heavy": []}

    ranked = sorted(by_ip.items(), key=lambda kv: kv[1], reverse=True)

    try:
        # نودهای ثبت‌شده در پنل + هر پردازه‌ی تانلی که واقعاً اجرا می‌شود
        peers = _NET.tunnel_peers(extra=_tunnel_peers())
    except Exception:
        try:
            peers = _tunnel_peers()
        except Exception:
            peers = {}

    tunnels = [{"ip": ip, "name": peers[ip], "count": n,
                "pct": round(n * 100.0 / total, 1)}
               for ip, n in ranked if ip in peers]

    # «غیرعادی» یعنی یک IP بیش از ۱۵٪ کل اتصال‌ها را گرفته و دست‌کم
    # ۲۰ اتصال دارد. زیر این حد، نوسان طبیعی است و هشدار دادنش فقط
    # نویز می‌سازد.
    #
    # تانل‌های خودمان از این حساب بیرون‌اند: کل ترافیک مشتری‌های
    # ایران از آن‌ها رد می‌شود، پس همیشه بالای فهرست می‌نشستند و
    # هشدار واقعی را دفن می‌کردند.
    heavy = [{"ip": ip, "count": n, "pct": round(n * 100.0 / total, 1)}
             for ip, n in ranked
             if ip not in peers and n >= 20 and n * 100.0 / total >= 15]

    return {
        "total": total,
        "uniqueIps": len(by_ip),
        "byIp": [{"ip": ip, "count": n, "pct": round(n * 100.0 / total, 1),
                  "tunnel": peers.get(ip) or ""}
                 for ip, n in ranked[:top]],
        "byPort": [{"port": p, "count": n}
                   for p, n in sorted(by_port.items(),
                                      key=lambda kv: kv[1], reverse=True)[:top]],
        "heavy": heavy,
        "tunnels": tunnels,
        "tunnelConns": sum(t["count"] for t in tunnels),
    }


# ═══════════════════════════════════════════════════════════
#  Xray و سرویس‌ها
# ═══════════════════════════════════════════════════════════

def _svc_state(name):
    ok, out = _run(["systemctl", "is-active", name])
    return out.strip() or ("active" if ok else "unknown")


def services(names=None):
    names = names or ["xray", "x-ui", "nginx", "nexora-bot", "nexora-api",
                      "fail2ban", "ssh", "sshd"]
    rows = []
    for n in names:
        ok, out = _run(["systemctl", "show", n,
                        "--property=LoadState,ActiveState,SubState,"
                        "MainPID,MemoryCurrent,NRestarts"])
        if not ok or "LoadState=not-found" in out:
            continue
        d = dict(x.split("=", 1) for x in out.strip().split("\n") if "=" in x)
        active = d.get("ActiveState", "")
        restarts = int(d.get("NRestarts", "0") or 0)
        mem = d.get("MemoryCurrent", "")
        mem = int(mem) if mem.isdigit() else None
        rows.append({
            "name": n,
            "active": active,
            "sub": d.get("SubState", ""),
            "pid": d.get("MainPID", ""),
            "memory": mem,
            "restarts": restarts,
            "level": OK if active == "active" else CRIT,
            # ری‌استارت مکرر یعنی سرویس بالا می‌آید و می‌افتد — از
            # «خاموش» بدتر است چون در نگاه اول سالم به نظر می‌رسد
            "flapping": restarts > 3,
        })
    return rows


def xray():
    """وضعیت اختصاصی Xray — قلب سرویس."""
    out = []
    state = _svc_state("xray")
    running = state == "active"
    out.append(_metric(
        "xray", "سرویس Xray", "روشن" if running else "خاموش", "",
        OK if running else CRIT,
        f"وضعیت systemd: {state}",
        "اگر Xray خاموش باشد هیچ کاربری وصل نمی‌شود، حتی اگر پنل و ربات "
        "سالم کار کنند.",
        "" if running else "systemctl restart xray"))

    # خطاهای اخیر — زودتر از شکایت مشتری خبر می‌دهد
    ok, log = _run(["journalctl", "-u", "xray", "--since", "-30min",
                    "-p", "warning", "--no-pager", "-n", "40"])
    if ok:
        lines = [x for x in log.strip().split("\n")
                 if x and "-- No entries" not in x]
        n = len(lines)
        out.append(_metric(
            "xray_errors", "خطاهای Xray (۳۰ دقیقه اخیر)", n, "",
            _level(n, 5, 30), f"{_fa(n)} خط هشدار یا خطا",
            "چند خطای پراکنده طبیعی است. انبوه خطا یعنی یا کانفیگ مشکل دارد "
            "یا سرور خارج در دسترس نیست.",
            "برای دیدن: journalctl -u xray -p warning --since -30min",
            extra={"lines": lines[-8:]}))
    return out


# ═══════════════════════════════════════════════════════════
#  بسته‌ها و امنیت
# ═══════════════════════════════════════════════════════════

def packages():
    """به‌روزرسانی‌های در انتظار — مخصوصاً امنیتی."""
    if not _has("apt-get"):
        return []
    ok, out = _run(["apt-get", "-s", "upgrade"], timeout=25)
    if not ok:
        return []
    lines = [x for x in out.split("\n") if x.startswith("Inst ")]
    total = len(lines)
    sec = len([x for x in lines if "security" in x.lower()])
    return [_metric(
        "updates", "به‌روزرسانی در انتظار", total, "بسته",
        CRIT if sec else _level(total, 25, 80),
        f"{_fa(total)} بسته — {_fa(sec)} مورد امنیتی",
        "به‌روزرسانی امنیتی یعنی حفره‌ای عمومی شده که کد سوءاستفاده‌اش هم "
        "معمولاً منتشر است. روی سروری که پورت باز به اینترنت دارد، این "
        "فوری‌ترین ریسک است.",
        "apt update && apt upgrade" if total else "",
        extra={"security": sec,
               "sample": [x.split()[1] for x in lines[:10] if len(x.split()) > 1]})]


def _re_status(text):
    """آیا خروجی ufw وضعیت active را گزارش می‌کند؟ (نه inactive)"""
    return re.search(r"^\s*status:\s*active\s*$", text or "",
                     re.IGNORECASE | re.MULTILINE)


def security():
    out = []

    # تلاش‌های ناموفق ورود SSH — نشانه‌ی حمله‌ی brute force
    def _scan():
        return _run(["journalctl", "-u", "ssh", "-u", "sshd", "--since", "-24h",
                     "--no-pager", "-g", "Failed password"], timeout=15)

    now = time.time()
    hit = _CACHE.get("_ssh_scan")
    if hit and now - hit[0] < SSH_SCAN_TTL:
        ok, log = hit[1]
    else:
        ok, log = _scan()
        _CACHE["_ssh_scan"] = (now, (ok, log))

    if ok:
        n = len([x for x in log.split("\n") if "Failed password" in x])
        ips = re.findall(r"from ([\d.]+)", log)
        top = {}
        for ip in ips:
            top[ip] = top.get(ip, 0) + 1
        worst = sorted(top.items(), key=lambda kv: -kv[1])[:5]
        out.append(_metric(
            "ssh_failed", "ورود ناموفق SSH (۲۴ ساعت)", n, "",
            _level(n, 100, 1000), f"{_fa(n)} تلاش ناموفق از {_fa(len(top))} آدرس",
            "روی هر سرور عمومی چند صد تلاش خودکار در روز عادی است. عدد خیلی "
            "بالا از یک IP یعنی هدف‌گیری مشخص.",
            "ورود با رمز را ببندید و فقط کلید بگذارید؛ یا fail2ban نصب کنید.",
            extra={"topIps": [{"ip": i, "n": c} for i, c in worst]}))

    # fail2ban
    if _has("fail2ban-client"):
        ok, o = _run(["fail2ban-client", "status"])
        if ok:
            jails = re.search(r"Jail list:\s*(.*)", o)
            out.append(_metric(
                "fail2ban", "fail2ban", "فعال", "", OK,
                f"جیل‌ها: {jails.group(1).strip() if jails else '—'}",
                "fail2ban آدرس‌هایی را که مکرر شکست می‌خورند خودکار می‌بندد."))
    else:
        out.append(_metric(
            "fail2ban", "fail2ban", "نصب نیست", "", WARN,
            "روی این سرور پیدا نشد",
            "بدون آن، تلاش‌های brute force بی‌وقفه ادامه پیدا می‌کنند.",
            "apt install fail2ban"))

    # فایروال
    if _has("ufw"):
        ok, o = _run(["ufw", "status"])
        # دقت کنید: «inactive» خودش شامل «active» است. جست‌وجوی ساده‌ی
        # زیررشته، فایروالِ خاموش را روشن گزارش می‌کرد — یعنی دقیقاً
        # در لحظه‌ای که باید هشدار می‌داد، ساکت می‌ماند.
        act = bool(_re_status(o))
        out.append(_metric(
            "firewall", "فایروال", "روشن" if act else "خاموش", "",
            OK if act else WARN,
            o.strip().split("\n")[0] if o else "—",
            "فایروال خاموش یعنی هر پورتی که سهواً باز شود، مستقیم از اینترنت "
            "در دسترس است."))
    return out


# ═══════════════════════════════════════════════════════════
#  جمع‌بندی
# ═══════════════════════════════════════════════════════════

def _uptime():
    try:
        return int(float(_read("/proc/uptime", "0").split()[0]))
    except Exception:
        return 0


#: کش کوتاه‌مدت برای بخش‌های گران.
#
# هر فراخوانی snapshot چند subprocess اجرا می‌کند: ss برای پورت‌ها،
# ss دوباره برای اتصال‌ها، systemctl برای هر سرویس، ps برای پردازه‌ها.
# صفحه‌ی مانیتورینگ هر چند ثانیه تازه می‌شود و بعضی از این‌ها اصلاً
# در آن بازه عوض نمی‌شوند — فهرست پورت‌های باز ساعت‌ها ثابت است.
#
# مقدار TTL بر اساس اینکه هر داده واقعاً چقدر سریع عوض می‌شود:
_CACHE = {}
_CACHE_TTL = {
    "ports": 30.0,        # پورت باز به‌ندرت عوض می‌شود
    "processes": 10.0,
    "services": 15.0,
    "connections": 4.0,   # سریع عوض می‌شود، ولی نه در کمتر از ۴ ثانیه

    # apt-get -s upgrade با مهلت ۲۵ ثانیه، در هر تازه‌سازی صفحه اجرا
    # می‌شد. فهرست بسته‌های قابل‌ارتقا ساعتی یک‌بار هم تازه است.
    "packages": 3600.0,
}

#: اسکن ۲۴ ساعت لاگ SSH گران است — همان کاری که صفحه‌ی نفوذ هم می‌کند.
#
#  فقط *همین* تکه کش می‌شود، نه کل بخش امنیت. وضعیت فایروال و
#  fail2ban باید زنده بماند: اگر مدیر همین الان فایروال را روشن کند
#  و پنل پنج دقیقه بگوید خاموش است، هشدار بی‌معنی می‌شود.
SSH_SCAN_TTL = 300.0


def _cached(name, fn):
    ttl = _CACHE_TTL.get(name)
    if not ttl:
        return fn()
    now = time.time()
    hit = _CACHE.get(name)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    val = fn()
    _CACHE[name] = (now, val)
    return val


def snapshot(include=None):
    """
    یک عکس کامل.

    include: زیرمجموعه‌ی بخش‌ها، برای وقتی صفحه فقط بخشی را می‌خواهد.
    """
    want = set(include or ["cpu", "memory", "disk", "network", "xray",
                           "services", "ports", "packages", "security",
                           "processes", "connections"])
    metrics, sections = [], {}

    def add(name, fn, into_metrics=True):
        if name not in want:
            return
        try:
            r = _cached(name, fn)
            sections[name] = r
            if into_metrics and isinstance(r, list) and r and isinstance(r[0], dict) \
                    and "level" in r[0] and "key" in r[0]:
                metrics.extend(r)
        except Exception as e:
            sections[name] = []
            metrics.append(_metric(name, name, None, "", WARN,
                                   f"خواندن ناموفق: {type(e).__name__}"))

    # وقتی هر دو خواسته شده‌اند، یک پنجره‌ی نمونه‌برداری برای هر دو
    rates = sample_rates() if ("cpu" in want and "network" in want) else None

    add("cpu", (lambda: cpu(rates["cpu"])) if rates else cpu)
    add("memory", memory)
    add("disk", disks)
    add("network", (lambda: network(rates["net"])) if rates else network)
    add("xray", xray)
    add("packages", packages)
    add("security", security)
    add("services", services, into_metrics=False)
    add("ports", listening, into_metrics=False)
    add("processes", top_processes, into_metrics=False)
    add("connections", connections, into_metrics=False)

    # یک IP که سهم غیرعادی از اتصال‌ها گرفته، معمولاً یا اشتراک‌گذاری
    # حساب است یا اسکن. هر دو باید به چشم ادمین بیاید.
    for h in (sections.get("connections") or {}).get("heavy", []):
        metrics.append(_metric(
            f"conn:{h['ip']}", f"اتصال زیاد از {h['ip']}",
            h["count"], "اتصال", WARN,
            f"{_fa(h['pct'])}٪ از کل اتصال‌های سرور",
            "یک IP با این سهم یعنی یا یک حساب بین چند نفر پخش شده "
            "یا کسی دارد سرور را اسکن می‌کند.",
            f"ss -tunp | grep {h['ip']}"))

    for s in sections.get("services", []):
        if s["level"] == CRIT:
            metrics.append(_metric(
                f"svc:{s['name']}", f"سرویس {s['name']}", "خاموش", "", CRIT,
                f"وضعیت: {s['active']}",
                "این سرویس باید روشن باشد.",
                f"systemctl restart {s['name']}"))
        elif s.get("flapping"):
            metrics.append(_metric(
                f"svc:{s['name']}", f"سرویس {s['name']}", "ناپایدار", "", WARN,
                f"{_fa(s['restarts'])} بار ری‌استارت شده",
                "سرویسی که مدام بالا و پایین می‌شود از خاموش بدتر است، چون "
                "در نگاه اول سالم به نظر می‌رسد.",
                f"journalctl -u {s['name']} -n 50"))

    crit = [m for m in metrics if m["level"] == CRIT]
    warn = [m for m in metrics if m["level"] == WARN]
    level = CRIT if crit else (WARN if warn else OK)

    if crit:
        headline = crit[0]["title"]
        summary = f"{_fa(len(crit))} مشکل جدی" + (f" و {_fa(len(warn))} هشدار" if warn else "")
    elif warn:
        headline = warn[0]["title"]
        summary = f"{_fa(len(warn))} هشدار"
    else:
        headline = ""
        summary = "سرور سالم است"

    return {
        "level": level,
        "summary": summary,
        "headline": headline,
        "metrics": metrics,
        "sections": sections,
        "counts": {"ok": len(metrics) - len(crit) - len(warn),
                   "warn": len(warn), "crit": len(crit)},
        "host": {
            "uptime": _uptime(),
            "cores": os.cpu_count() or 1,
            "kernel": _read("/proc/sys/kernel/osrelease", "").strip(),
            "hostname": _read("/proc/sys/kernel/hostname", "").strip(),
        },
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "took": None,
    }


if __name__ == "__main__":
    t0 = time.time()
    snap = snapshot()
    snap["took"] = round(time.time() - t0, 2)
    print(json.dumps(snap, ensure_ascii=False, indent=2))
