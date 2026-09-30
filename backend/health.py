"""
بررسی سلامت سرور.

هدف: مشکلی که هنوز به مشتری نرسیده را قبل از شکایتش پیدا کند.

هر بررسی سه حالت دارد — ok، warn، crit — و هرکدام یک راهنمای
عملی همراه دارد. بدون آن راهنما، دانستن اینکه «دیسک ۹۲ درصد پر
است» کمکی نمی‌کند.

این ماژول عمداً به هیچ کتابخانه‌ی بیرونی وابسته نیست، چون همین
کد از طریق agent روی سرور ایران هم اجرا می‌شود که ممکن است
اینترنت محدود داشته باشد.
"""

import os
import re
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import logging

_log = logging.getLogger("nexora.health")

OK, WARN, CRIT = "ok", "warn", "crit"


def _run(cmd, timeout=12):
    """اجرای دستور. همیشه فهرست، نه رشته — تا shell دخالت نکند."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except Exception:
        return False, ""


def _check(key, title, level, detail, hint=""):
    return {"key": key, "title": title, "level": level,
            "detail": detail, "hint": hint}


# ═══════════════════════════════════════════════════════════
#  منابع
# ═══════════════════════════════════════════════════════════

def check_disk():
    """
    فضای دیسک.

    لاگ Xray روی سروری با ترافیک بالا سریع بزرگ می‌شود. دیسک پر
    یعنی همه‌چیز می‌ایستد — دیتابیس نوشته نمی‌شود، لاگ نمی‌رود،
    و سرویس‌ها یکی‌یکی می‌افتند.
    """
    try:
        t, u, f = shutil.disk_usage("/")
    except Exception as e:
        return _check("disk", "فضای دیسک", WARN, f"خوانده نشد: {e}")

    pct = round(u * 100 / t)
    gb_free = round(f / (1024 ** 3), 1)
    detail = f"{pct}٪ پر · {gb_free} GB آزاد"

    if pct >= 92:
        return _check("disk", "فضای دیسک", CRIT, detail,
                      "لاگ‌ها را پاک کنید: journalctl --vacuum-size=200M "
                      "و بزرگ‌ترین پوشه‌ها را با du -sh /* ببینید")
    if pct >= 82:
        return _check("disk", "فضای دیسک", WARN, detail,
                      "پیش از پر شدن، لاگ‌های قدیمی را پاک کنید")
    return _check("disk", "فضای دیسک", OK, detail)


def check_memory():
    """
    حافظه و swap.

    وقتی حافظه تمام شود، کرنل یک فرآیند را می‌کشد — و معمولاً
    همان چیزی است که بیشترین حافظه را دارد، یعنی xray.
    """
    try:
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, _, v = line.partition(":")
            info[k] = int(v.strip().split()[0])
    except Exception as e:
        return _check("memory", "حافظه", WARN, f"خوانده نشد: {e}")

    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", 0)
    sw_total = info.get("SwapTotal", 0)
    sw_free = info.get("SwapFree", 0)

    if not total:
        return _check("memory", "حافظه", WARN, "اطلاعات ناقص")

    pct = round((total - avail) * 100 / total)
    mb_free = round(avail / 1024)
    detail = f"{pct}٪ مصرف · {mb_free} MB آزاد"

    if sw_total:
        sw_pct = round((sw_total - sw_free) * 100 / sw_total)
        detail += f" · swap {sw_pct}٪"

    if pct >= 93:
        return _check("memory", "حافظه", CRIT, detail,
                      "خطر کشته شدن xray. اگر swap ندارید بسازید: "
                      "fallocate -l 2G /swapfile && chmod 600 /swapfile && "
                      "mkswap /swapfile && swapon /swapfile")
    if pct >= 85:
        return _check("memory", "حافظه", WARN, detail,
                      "فضای حافظه کم است — سرویس‌های غیرضروری را ببندید")
    if not sw_total and total < 1500 * 1024:
        return _check("memory", "حافظه", WARN, detail + " · بدون swap",
                      "روی سرور کم‌حافظه، نبود swap یعنی هر اوج مصرف "
                      "می‌تواند xray را بکشد")
    return _check("memory", "حافظه", OK, detail)


def check_load():
    """
    بار پردازنده.

    عدد loadavg را بر تعداد هسته تقسیم می‌کنیم؛ بار ۴ روی چهار
    هسته یعنی پر ولی سالم، همان بار روی یک هسته یعنی بحران.
    """
    try:
        one, five, fifteen = os.getloadavg()
        cores = os.cpu_count() or 1
    except Exception as e:
        return _check("load", "بار پردازنده", WARN, f"خوانده نشد: {e}")

    ratio = one / cores
    detail = f"{one:.2f} / {five:.2f} / {fifteen:.2f} روی {cores} هسته"

    if ratio >= 2.5:
        return _check("load", "بار پردازنده", CRIT, detail,
                      "سرور جا ندارد. با top ببینید چه چیزی مصرف می‌کند")
    if ratio >= 1.4:
        return _check("load", "بار پردازنده", WARN, detail,
                      "بار بالاست — اگر ادامه داشت، ارتقا لازم است")
    return _check("load", "بار پردازنده", OK, detail)


def check_uptime():
    """مدت روشن بودن — ری‌استارت تازه ممکن است نشانه‌ی مشکل باشد."""
    try:
        up = float(Path("/proc/uptime").read_text().split()[0])
    except Exception as e:
        # سکوت نه: بررسی‌ای که نتوانسته اندازه بگیرد باید همین را
        # بگوید، وگرنه از فهرست غیب می‌شود و مدیر فکر می‌کند سنجیده
        # شده و سالم بوده. همان کاری که check_disk و check_load
        # می‌کنند.
        return _check("uptime", "مدت روشن بودن", WARN, f"خوانده نشد: {e}")

    days = int(up // 86400)
    hours = int((up % 86400) // 3600)
    detail = f"{days} روز و {hours} ساعت" if days else f"{hours} ساعت"

    if up < 900:
        return _check("uptime", "مدت روشن بودن", WARN, detail,
                      "سرور به‌تازگی ری‌استارت شده — اگر خودتان نکردید، "
                      "با dmesg -T | tail -40 دلیلش را ببینید")
    return _check("uptime", "مدت روشن بودن", OK, detail)


# ═══════════════════════════════════════════════════════════
#  سرویس‌ها
# ═══════════════════════════════════════════════════════════

def check_services(names=None):
    """
    سرویس‌های حیاتی.

    ری‌استارت‌های مکرر هم بررسی می‌شود: سرویسی که فعال است ولی
    ده بار ری‌استارت شده، مشکلی دارد که هنوز خودش را کامل نشان
    نداده — و همان است که بعداً وسط شب می‌افتد.
    """
    names = names or ["x-ui", "nexora-panel", "nginx", "nexora-bot"]
    out = []

    for name in names:
        active, _ = _run(["systemctl", "is-active", "--quiet", name])
        exists, _ = _run(["systemctl", "cat", name])

        if not exists:
            continue

        ok_show, raw = _run(["systemctl", "show", name,
                             "-p", "NRestarts,ActiveState,SubState", "--value"])
        parts = raw.splitlines() if ok_show else []
        restarts = 0
        try:
            restarts = int(parts[0]) if parts else 0
        except (ValueError, IndexError):
            pass

        state = parts[1] if len(parts) > 1 else ("active" if active else "?")

        if not active:
            out.append(_check(f"svc_{name}", f"سرویس {name}", CRIT,
                              f"متوقف است ({state})",
                              f"systemctl status {name} و "
                              f"journalctl -u {name} -n 40 --no-pager"))
        elif restarts >= 5:
            out.append(_check(f"svc_{name}", f"سرویس {name}", WARN,
                              f"فعال ولی {restarts} بار ری‌استارت شده",
                              f"journalctl -u {name} -n 60 --no-pager | grep -i error"))
        else:
            out.append(_check(f"svc_{name}", f"سرویس {name}", OK, "فعال"))

    return out


def check_listening(ports=None):
    """
    پورت‌هایی که باید باز باشند.

    اگر پورتی که مشتری به آن وصل می‌شود شنونده نداشته باشد،
    اتصال رد می‌شود — و از داخل سرور هیچ خطایی دیده نمی‌شود.
    """
    ports = ports or []
    if not ports:
        return []

    ok, out = _run(["ss", "-lntu"])
    if not ok:
        # قبلاً این‌جا [] برمی‌گشت: بررسی به‌کلی از صفحه‌ی سلامت غیب
        # می‌شد. و این همان بررسی‌ای است که «مشتری وصل نمی‌شود» را
        # پیدا می‌کند — نبودنش از هشدارش بدتر است.
        return [_check("ports", "پورت‌های سرویس", WARN,
                       "خوانده نشد — دستور ss جواب نداد",
                       "بسته‌ی iproute2 نصب است؟ با ss -lntup دستی ببینید")]

    listening = set()
    for m in re.finditer(r":(\d+)\s", out):
        listening.add(int(m.group(1)))

    if not listening:
        return [_check("ports", "پورت‌های سرویس", WARN,
                       "هیچ پورت شنونده‌ای دیده نشد",
                       "خروجی ss خالی یا غیرمنتظره بود — دستی بررسی کنید")]

    missing = [p for p in ports if int(p) not in listening]
    if missing:
        return [_check("ports", "پورت‌های سرویس", CRIT,
                       "شنونده ندارند: " + "، ".join(str(p) for p in missing),
                       "مشتری به این پورت‌ها وصل می‌شود ولی چیزی پشتشان "
                       "نیست. با ss -lntup ببینید چه باز است")]
    return [_check("ports", "پورت‌های سرویس", OK,
                   f"{len(ports)} پورت باز است")]


# ═══════════════════════════════════════════════════════════
#  شبکه
# ═══════════════════════════════════════════════════════════

#: چند ثانیه به DNS فرصت بدهیم پیش از اینکه «بی‌جواب» حسابش کنیم.
DNS_DEADLINE = 4.0


def _resolve_ms(host, deadline):
    """
    یک resolve با مهلت. برمی‌گرداند: (میلی‌ثانیه یا None, خطا)

    gethostbyname مهلت نمی‌پذیرد — از resolver سیستم می‌رود و
    مهلت خودش را دارد که می‌تواند ده‌ها ثانیه باشد. بدون مهار، *این*
    بررسی که اصلاً برای تشخیص DNS کند نوشته شده، خودش هنگ می‌کرد و
    کل گزارش سلامت را نگه می‌داشت — هم در پنل، هم روی نود ایران.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TO

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        t0 = time.perf_counter()
        fut = pool.submit(socket.gethostbyname, host)
        try:
            fut.result(timeout=deadline)
        except _TO:
            return None, ""
        except Exception as e:
            return None, type(e).__name__
        return round((time.perf_counter() - t0) * 1000), ""
    finally:
        # منتظر نخی که هنوز روی resolver گیر است نمی‌مانیم
        pool.shutdown(wait=False, cancel_futures=True)


def check_dns():
    """
    DNS.

    اگر resolve کند یا خراب باشد، همه‌چیز کند می‌شود بدون اینکه
    خطای مشخصی بدهد.
    """
    ms, err = _resolve_ms("cloudflare.com", DNS_DEADLINE)
    if ms is None:
        return _check(
            "dns", "DNS", CRIT,
            (f"resolve نشد: {err}" if err
             else f"بیش از {DNS_DEADLINE} ثانیه جواب نداد"),
            "محتویات /etc/resolv.conf را ببینید")

    servers = []
    try:
        for line in Path("/etc/resolv.conf").read_text().splitlines():
            if line.startswith("nameserver"):
                servers.append(line.split()[1])
    except Exception as _exc:
        # بی‌این، «سروری تعریف نشده» و «فایل خوانده نشد» یک شکل بودند
        _log.warning("reading /etc/resolv.conf: %s", _exc)

    detail = f"{ms} ms" + (f" · {', '.join(servers[:3])}" if servers else "")

    if ms > 900:
        return _check("dns", "DNS", WARN, detail,
                      "resolve کند است — nameserver سریع‌تری بگذارید")
    return _check("dns", "DNS", OK, detail)


def check_ipv6():
    """
    IPv6 مرده.

    اگر سرور آدرس IPv6 داشته باشد ولی مسیرش کار نکند، Xray برای
    هر دامنه‌ای که رکورد AAAA دارد اول سراغ آن می‌رود و تا timeout
    معلق می‌ماند. کاربر این را به‌صورت «باز نمی‌شود» می‌بیند.
    """
    ok, out = _run(["ip", "-6", "addr", "show", "scope", "global"])
    if not ok:
        # این بدترین حالتِ سکوت بود: وقتی دستور ip جواب نمی‌داد،
        # has_v6 روی False می‌ماند و نتیجه می‌شد «تنظیم نشده — مشکلی
        # نیست». یعنی دقیقاً همان وضعیتی که این بررسی برای پیدا کردنش
        # ساخته شده — IPv6 شکسته — به مدیر «سالم» گزارش می‌شد.
        return _check("ipv6", "IPv6", WARN, "خوانده نشد — دستور ip جواب نداد",
                      "بسته‌ی iproute2 نصب است؟ با ip -6 addr دستی ببینید")

    if "inet6" not in out:
        return _check("ipv6", "IPv6", OK, "تنظیم نشده — مشکلی نیست")

    works = False
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(("2001:4860:4860::8888", 53))
        s.close()
        works = True
    except Exception:
        pass

    if works:
        return _check("ipv6", "IPv6", OK, "تنظیم شده و کار می‌کند")

    return _check("ipv6", "IPv6", CRIT, "آدرس دارد ولی مسیر کار نمی‌کند",
                  "این باعث می‌شود سایت‌هایی مثل گوگل کند باز شوند. در "
                  "Xray خروجی direct را روی UseIPv4 بگذارید، یا آدرس IPv6 "
                  "را از netplan بردارید")


def check_time():
    """
    اختلاف زمان.

    TLS به زمان درست وابسته است. اختلاف چند دقیقه‌ای باعث می‌شود
    اتصال‌ها با خطای گواهی رد شوند.
    """
    # بدون --value و بدون -p می‌خوانیم.
    #
    # قبلاً `timedatectl show -p NTPSynchronized,Timezone --value` بود و
    # فرض شده بود خروجی به همان ترتیبِ خواسته‌شده می‌آید. نمی‌آید —
    # systemd ویژگی‌ها را به ترتیب داخلی خودش چاپ می‌کند و Timezone
    # قبل از NTPSynchronized است. پس خط اول همیشه نام منطقه‌ی زمانی
    # بود، هیچ‌وقت "yes" نمی‌شد، و این بررسی *همیشه* هشدار می‌داد.
    #
    # نتیجه: مدیر دستور پیشنهادی را می‌زد، سرور از اول هم همگام بود،
    # و هشدار سر جایش می‌ماند. خواندن جفت‌های KEY=value به ترتیب
    # وابسته نیست و روی نسخه‌های قدیمی‌تر systemd هم کار می‌کند.
    ok, out = _run(["timedatectl", "show"])
    if not ok:
        return None

    vals = {}
    for line in out.splitlines():
        k, sep, v = line.partition("=")
        if sep:
            vals[k.strip()] = v.strip()

    raw = vals.get("NTPSynchronized")
    if raw is None:
        # systemd این ویژگی را ندارد. حدس‌زدن بدتر از نگفتن است.
        return None

    tz = vals.get("Timezone") or "?"
    if raw.strip().lower() != "yes":
        return _check("time", "همگام‌سازی زمان", WARN,
                      f"همگام نیست · {tz}",
                      "timedatectl set-ntp true — و اگر باز هم همگام نشد: "
                      "systemctl enable --now systemd-timesyncd")
    return _check("time", "همگام‌سازی زمان", OK, f"همگام · {tz}")


# ═══════════════════════════════════════════════════════════
#  کرنل و لاگ
# ═══════════════════════════════════════════════════════════

def check_kernel():
    """
    خطاهای کرنل.

    OOM kill مهم‌ترین چیزی است که اینجا پیدا می‌شود: یعنی حافظه
    تمام شده و کرنل چیزی را کشته — احتمالاً xray.
    """
    ok, out = _run(["dmesg", "-T", "--level=err,crit,alert,emerg"], timeout=15)
    if not ok:
        ok, out = _run(["journalctl", "-k", "-p", "err", "-n", "60",
                        "--no-pager"], timeout=15)
    if not ok or not out:
        return None

    lines = out.strip().splitlines()[-60:]
    oom = [l for l in lines if "out of memory" in l.lower()
           or "oom-killer" in l.lower() or "killed process" in l.lower()]

    if oom:
        who = ""
        m = re.search(r"Killed process \d+ \((\w+)\)", " ".join(oom))
        if m:
            who = f" — قربانی: {m.group(1)}"
        return _check("kernel", "خطاهای کرنل", CRIT,
                      f"{len(oom)} مورد کمبود حافظه{who}",
                      "حافظه تمام شده و کرنل فرآیندی را کشته. "
                      "swap اضافه کنید یا رم را بالا ببرید")

    if len(lines) > 25:
        return _check("kernel", "خطاهای کرنل", WARN,
                      f"{len(lines)} خطا در لاگ",
                      "dmesg -T --level=err | tail -30")

    return _check("kernel", "خطاهای کرنل", OK,
                  "بدون خطای مهم" if not lines else f"{len(lines)} مورد جزئی")


#: جاهایی که گواهی TLS نگهداری می‌شود.
#
#  certbot برای هر دامنه یک پوشه به نام خودِ دامنه می‌سازد، پس نام
#  پوشه همان دامنه است و لازم نیست جایی تنظیمش کنیم.
CERT_DIRS = (Path("/etc/letsencrypt/live"), Path("/etc/nexora/ssl"))

#: ماه‌های openssl. از strptime با %b استفاده نمی‌کنیم چون به locale
#: سیستم وابسته است: روی سروری که LC_TIME انگلیسی نیست، «Dec» را
#: نمی‌شناسد و کل بررسی بی‌صدا کنار می‌رود.
_MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1)}


def _cert_files(domain=None):
    """فایل‌های گواهی که روی این سرور هست: [(نام, مسیر)]"""
    out = []
    if domain:
        for p in (Path(f"/etc/letsencrypt/live/{domain}/fullchain.pem"),
                  Path(f"/etc/nexora/ssl/{domain}.crt")):
            if p.exists():
                out.append((domain, p))

    for base in CERT_DIRS:
        try:
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir()):
                if child.is_dir():
                    f = child / "fullchain.pem"
                    if f.exists():
                        out.append((child.name, f))
                elif child.suffix in (".crt", ".pem"):
                    out.append((child.stem, child))
        except OSError:
            continue

    seen, uniq = set(), []
    for name, p in out:
        if str(p) not in seen:
            seen.add(str(p))
            uniq.append((name, p))
    return uniq


def _cert_expiry(path):
    """تاریخ انقضای یک گواهی (UTC)، یا None اگر خوانده نشد."""
    ok, out = _run(["openssl", "x509", "-enddate", "-noout", "-in", str(path)])
    if not ok or "notAfter=" not in out:
        return None
    raw = out.split("notAfter=", 1)[1].strip()
    m = re.match(r"([A-Za-z]{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+(\d{4})",
                 raw)
    if not m or m.group(1) not in _MONTHS:
        return None
    try:
        return datetime(int(m.group(6)), _MONTHS[m.group(1)], int(m.group(2)),
                        int(m.group(3)), int(m.group(4)), int(m.group(5)),
                        tzinfo=timezone.utc)
    except ValueError:
        return None


def check_cert(domain=None):
    """
    گواهی SSL — منقضی شود، صفحه‌ی اشتراک برای هیچ مشتری باز نمی‌شود.

    دامنه لازم نیست داده شود.

    قبلاً بدون domain فوراً None برمی‌گرداند، و domain از
    advanced.panelDomain می‌آمد — کلیدی که هیچ رابط کاربری، هیچ
    مرحله‌ی نصب و هیچ پیش‌فرضی آن را نمی‌نوشت. یعنی این بررسی روی
    هیچ سروری اجرا نمی‌شد و هشدارِ «گواهی دارد تمام می‌شود» هرگز
    نمی‌آمد.

    حالا خودش پوشه‌های گواهی را می‌گردد. certbot پوشه را به نام دامنه
    می‌سازد، پس نام دامنه هم از همان‌جا می‌آید.

    اگر هیچ گواهی‌ای نبود None برمی‌گرداند — سروری که فقط HTTP دارد
    نباید هشدار بگیرد. ولی اگر گواهی *هست* و خوانده نشد، هشدار
    می‌دهد: ندانستنِ تاریخ انقضا خودش خبر است.
    """
    files = _cert_files(domain)
    if not files:
        return None

    soonest = None
    for name, path in files:
        exp = _cert_expiry(path)
        if exp and (soonest is None or exp < soonest[1]):
            soonest = (name, exp)

    if soonest is None:
        return _check("cert", "گواهی SSL", WARN,
                      f"{len(files)} گواهی پیدا شد ولی تاریخشان خوانده نشد",
                      "روی سرور: openssl x509 -enddate -noout -in "
                      + str(files[0][1]))

    name, exp = soonest
    days = (exp - datetime.now(timezone.utc)).days
    detail = f"{name} · {days} روز مانده · {exp:%Y-%m-%d}"

    if days < 0:
        return _check("cert", "گواهی SSL", CRIT, f"{name} منقضی شده",
                      "certbot renew --force-renewal && systemctl reload nginx")
    if days <= 10:
        return _check("cert", "گواهی SSL", WARN, detail, "certbot renew")
    return _check("cert", "گواهی SSL", OK, detail)


# ═══════════════════════════════════════════════════════════
#  اجرای همه
# ═══════════════════════════════════════════════════════════

def run_all(ports=None, domain=None, services=None):
    """
    همه‌ی بررسی‌ها.

    برمی‌گرداند: {level, checks, summary} — که level بدترین حالت
    پیداشده است، چون یک مورد بحرانی کافی است که کل سرور مشکل‌دار
    حساب شود.
    """
    checks = []

    for fn in (check_disk, check_memory, check_load, check_uptime,
               check_dns, check_ipv6, check_time, check_kernel):
        try:
            r = fn()
            if r:
                checks.append(r)
        except Exception as e:
            checks.append(_check(fn.__name__, fn.__name__, WARN,
                                 f"بررسی ناموفق: {type(e).__name__}"))

    # این سه تا `except: pass` بودند — یعنی اگر گروهی می‌ترکید، کل
    # آن گروه بی‌صدا از فهرست بیرون می‌رفت. حلقه‌ی بالا از همان اول
    # درست عمل می‌کرد و یک WARN می‌گذاشت؛ این پایین نه.
    def _group(key, title, fn, *a):
        try:
            return fn(*a) or []
        except Exception as e:
            # کلید از نام خودِ بررسی می‌آید، نه از تابعی که پاس شده —
            # وگرنه هر بار که چیزی جایش را بگیرد، شناسه‌اش هم عوض
            # می‌شود و صفحه نمی‌داند این کدام بررسی بوده.
            return [_check(key, title, WARN,
                           f"بررسی ناموفق: {type(e).__name__}")]

    checks += _group("check_services", "سرویس‌های حیاتی",
                     check_services, services)
    checks += _group("check_listening", "پورت‌های سرویس",
                     check_listening, ports)

    try:
        c = check_cert(domain)
        if c:
            checks.append(c)
    except Exception as e:
        checks.append(_check("cert", "گواهی SSL", WARN,
                             f"بررسی ناموفق: {type(e).__name__}"))

    crit = [c for c in checks if c["level"] == CRIT]
    warn = [c for c in checks if c["level"] == WARN]

    level = CRIT if crit else (WARN if warn else OK)
    if crit:
        summary = f"{len(crit)} مشکل جدی"
        if warn:
            summary += f" و {len(warn)} هشدار"
    elif warn:
        summary = f"{len(warn)} هشدار"
    else:
        summary = "همه‌چیز سالم است"

    return {
        "level": level,
        "summary": summary,
        "checks": checks,
        "counts": {"ok": len(checks) - len(crit) - len(warn),
                   "warn": len(warn), "crit": len(crit)},
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_all(), ensure_ascii=False, indent=2))
