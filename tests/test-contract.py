#!/usr/bin/env python3
"""
قرارداد بین هارنس و بکند — شکلِ پاسخِ ساختگی با پاسخِ واقعی.

چرا لازم شد: هارنس (tests/harness/harness-boot.js) تنها جایی است که پنل را
می‌بینیم، و داده‌اش را هیچ‌چیز با بکند هم‌شکل نگه نمی‌داشت. در یک روز
چهار مسیر پیدا شد با شکلِ کهنه:
  · قیف ({seen, bought} به‌جای {steps, segments}) — صفحه «NaN٪» نشان می‌داد
  · سفارش‌ها — فیلترِ status نادیده گرفته می‌شد و شبیهِ باگِ پنل بود
  · رویدادهای تانل ({at, kind, text} به‌جای {created_at, level, message})
  · فروشِ نماینده ({revenue} به‌جای {sold, received, …}) — کاشی هرگز دیده نمی‌شد
هر کدام یا باگی را پنهان می‌کرد یا باگی جعلی می‌ساخت.

این‌جا هر مسیرِ GETِ /api/admin بدونِ پارامترِ مسیر، روی یک بکندِ واقعی با
دیتابیس‌های ساختگی صدا زده می‌شود (بدونِ httpx — یک صداکننده‌ی ASGIِ
کوچک) و کلیدهایش با پاسخِ هارنس مقایسه می‌شوند:

  «هارنس اختراع کرده» — کلیدی که هارنس دارد و بکند نه. فرانت ممکن است
     روی چیزی نوشته شده باشد که روی سرور هرگز نمی‌آید: باگِ واقعی.
  «هارنس ندارد»      — کلیدی که بکند دارد و هارنس نه. صفحه در هارنس
     شاخه‌ای را نشان نمی‌دهد که روی سرور هست.

اجرا:  PYTHONIOENCODING=utf-8 python tests/test-contract.py [--all]
"""
import asyncio
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="nx-contract-"))
G, R, D, Y, X = "\033[38;5;42m", "\033[38;5;203m", "\033[38;5;245m", "\033[38;5;214m", "\033[0m"
SHOW_ALL = "--all" in sys.argv

# ── محیط: همه چیز در پوشه‌ی موقت ──
os.environ["CONFIG_PATH"] = str(TMP / "config.json")
os.environ["BOT_DB_PATH"] = str(TMP / "bot.db")
os.environ["BILLING_DB_PATH"] = str(TMP / "billing.db")
os.environ["TUNNEL_DB_PATH"] = str(TMP / "tunnels.db")
os.environ["NEXORA_ADMIN_PASSWORD"] = "testpw"
# GET /api/admin/license writes install_id and last_seen: into TMP, not data/.
os.environ["NEXORA_LICENSE_DIR"] = str(TMP / "license")
XUI = TMP / "x-ui.db"
os.environ["XUI_DB_PATH"] = str(XUI)

# ── x-ui ساختگی ──
GB = 1024 ** 3
NOW_MS = int(time.time() * 1000)
con = sqlite3.connect(XUI)
con.executescript("""
CREATE TABLE inbounds (id INTEGER PRIMARY KEY, user_id INTEGER, up INTEGER, down INTEGER,
  total INTEGER, remark TEXT, enable INTEGER, expiry_time INTEGER, listen TEXT, port INTEGER,
  protocol TEXT, settings TEXT, stream_settings TEXT, tag TEXT, sniffing TEXT);
CREATE TABLE client_traffics (id INTEGER PRIMARY KEY, inbound_id INTEGER, enable INTEGER,
  email TEXT, up INTEGER, down INTEGER, expiry_time INTEGER, total INTEGER, reset INTEGER,
  last_online INTEGER DEFAULT 0);
""")
clients = []
for i, (em, grp) in enumerate([("ali_1", "ali"), ("ali_2", "ali"), ("sara_1", "sara"), ("solo_1", "")], 1):
    clients.append({"id": f"uuid-{i}", "email": em, "enable": True, "totalGB": 50 * GB,
                    "expiryTime": NOW_MS + 20 * 86400000, "limitIp": 1, "subId": f"s{i}",
                    "group": grp, "comment": grp})
    con.execute("INSERT INTO client_traffics (inbound_id,enable,email,up,down,expiry_time,total)"
                " VALUES (1,1,?,?,?,?,?)", (em, GB, 9 * GB, NOW_MS + 20 * 86400000, 50 * GB))
con.execute("INSERT INTO inbounds (id,remark,enable,port,protocol,settings,stream_settings,tag,up,down,total,expiry_time)"
            " VALUES (1,'de-1',1,443,'vless',?,'{}','inbound-443',0,0,0,0)",
            (json.dumps({"clients": clients}),))
con.commit()
con.close()

# ── ربات ساختگی ──
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bot"))
sys.path.insert(0, str(ROOT / "backend"))
import db as botdb                                              # noqa: E402
botdb.DB_PATH = TMP / "bot.db"
botdb.init_db()
tid = botdb.create_tenant("Owner", bot_token="123:TEST", owner_tg_id=1)
T = botdb.TenantDB(tid)
u1 = T.create_user(1001, "ali", "علی")
T.exec("UPDATE users SET phone='989120000001', balance=50000, coins=12 WHERE id=?", (u1["id"],))
T.exec("INSERT INTO plans (tenant_id,name,price,gb,days) VALUES (?,?,?,?,?)", (tid, "یک‌ماهه", 100000, 30, 30))
pid = T.plans()[0]["id"]
o1 = T.create_order(u1["id"], pid, 100000, 100000)
T.exec("UPDATE orders SET status='approved' WHERE id=?", (o1["id"],))
o2 = T.create_order(u1["id"], pid, 100000, 100000)
T.exec("UPDATE orders SET status='awaiting' WHERE id=?", (o2["id"],))
T.exec("INSERT INTO subscriptions (tenant_id,user_id,plan_id,client_email,is_active,expires_at)"
       " VALUES (?,?,?,?,1,datetime('now','+10 day'))", (tid, u1["id"], pid, "ali_1"))
T.create_user(1002, None, "رضا", referred_by=u1["id"])
# یک همکارِ فروش — بی‌این فهرستِ همکارها خالی است و دروازه‌ی «فیلدِ خوانده‌شده» کور
T.exec("INSERT INTO affiliates (tenant_id,name,code,percent,active,tg_id) VALUES (?,?,?,?,1,?)",
       (tid, "همکار", "AF1", 10, 9001))
# یک نماینده — بی‌این فهرستِ نماینده‌ها خالی است و کلیدهای هر ردیف سنجیده نمی‌شود
_rc = sqlite3.connect(TMP / "bot.db")
_rc.execute("INSERT INTO tenants (name, bot_token, owner_tg_id, parent_id, portal_slug, portal_group, credit) "
            "VALUES (?,?,?,?,?,?,?)", ("نماینده", "456:TEST", 2, tid, "rep1", "ali", 1200000))
_rc.commit()
_rc.close()

import app as APP                                               # noqa: E402

# ── تانل ساختگی — بی‌این، آرایه‌های nodes/tunnels/events خالی‌اند و چیزی
#    برای مقایسه نمی‌ماند (فضای کاریِ ۲)
if getattr(APP, "TUN", None):
    _T = APP.TUN
    _n1 = _T.create_node("ایران-۱", role="iran")["id"]
    _n2 = _T.create_node("آلمان-۱", role="foreign")["id"]
    _T.touch_node(_n1, {"version": "1.4.0", "os": "Ubuntu 22.04", "cpu": 23.5, "mem": 41.2,
                        "disk": 37.0, "uptime": 86400 * 12, "ip": "10.0.0.1"})
    _T.touch_node(_n2, {"version": "1.4.0", "os": "Debian 12", "cpu": 11.0, "mem": 28.4,
                        "disk": 22.0, "uptime": 86400 * 30, "ip": "10.0.0.2"})
    _tid = _T.create_tunnel({"name": "تانل ۱", "engine": "backhaul", "node_id": _n1,
                             "foreign_node": _n2, "remote_host": "10.0.0.2",
                             "bridge_port": 3080, "ports": [443, 8443]})
    _T.set_status(_tid, "running")
    _T.log(node_id=_n1, tunnel_id=_tid, level="warn", message="تأخیرِ تانل بالای ۳۰۰ میلی‌ثانیه")
    # سنجش و مانیتورینگِ نود — بی‌این هر دو مسیر شاخه‌ی «هنوز چیزی
    # نرسیده» را می‌دهند و شکلِ اصلیِ داده هرگز مقایسه نمی‌شود.
    # نسخه‌ی ایجنت ۱.۵ به بالا، وگرنه sysmon «ایجنتِ قدیمی» می‌گوید.
    _T.touch_node(_n1, {"version": "1.5.2", "os": "Ubuntu 22.04", "cpu": 23.5, "mem": 41.2,
                        "disk": 37.0, "uptime": 86400 * 12, "ip": "10.0.0.1"})
    for _ms in (48.0, 52.5, 61.0):
        _T.save_metrics(_tid, {"tcp": {"443": {"ok": True, "avg": _ms, "min": _ms - 6, "max": _ms + 9,
                                               "jitter": 3.1, "loss": 0},
                                       "8443": {"ok": True, "avg": _ms + 2, "min": _ms - 4, "max": _ms + 11,
                                                "jitter": 2.4, "loss": 0}},
                               "icmp": {"avg": _ms - 3}, "http": {"avg": _ms + 40}})
    if getattr(APP, "MONITOR", None):
        _T.save_sysmon(_n1, {"kind": "sysmon", "data": APP.MONITOR.snapshot()})
    _T.queue_job(_n1, "logs", {"tunnel_id": _tid})
    _T.save_health(_n1, {"level": "ok", "summary": "سالم", "counts": {"ok": 1, "warn": 0, "crit": 0},
                         "checks": [{"key": "dns", "title": "DNS", "level": "ok", "detail": "10 ms", "hint": ""}],
                         "at": "2026-09-24 20:00:00"})
# ── فایروال و تشخیصِ نفوذ ساختگی (فضای کاریِ ۳) ──
# روی ویندوز ufw و journalctl نیست، پس هر مسیرِ فایروال «ready: false»
# می‌داد و هیچ‌وقت مقایسه نمی‌شد. خروجیِ دستورها ساختگی است، ولی تجزیه
# همان کدِ واقعیِ firewall.py/intrusion.py است — شکل از خودِ بکند می‌آید.
import types as _types                                            # noqa: E402
_WHICH = _types.SimpleNamespace(which=lambda n: f"/usr/sbin/{n}")
_UFW = ("Status: active\n\n     To                         Action      From\n"
        "     --                         ------      ----\n"
        "[ 1] 22/tcp                     ALLOW IN    Anywhere\n"
        "[ 2] 443                        ALLOW IN    Anywhere\n"
        "[ 3] Anywhere                   DENY IN     203.0.113.50\n")
_SS = ('tcp   LISTEN 0 4096 0.0.0.0:443 0.0.0.0:* users:(("xray",pid=812,fd=3))\n'
       'tcp   LISTEN 0 128  0.0.0.0:22  0.0.0.0:* users:(("sshd",pid=640,fd=3))\n')


def _fw_run(cmd, timeout=15):
    c = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
    if c.startswith("ufw status"):
        return True, _UFW + ("Default: deny (incoming), allow (outgoing), disabled (routed)\n"
                             if "verbose" in c else "")
    if c.startswith("ufw show added"):
        return True, "ufw allow 22/tcp\nufw allow 443\n"
    if c.startswith("ip route show type blackhole"):
        return True, "blackhole 203.0.113.60 \nblackhole 203.0.113.61 \n"
    if c.startswith("systemctl is-active"):
        return False, "inactive"
    if c.startswith("ss "):
        return True, "Netid State Recv-Q Send-Q Local Peer Process\n" + _SS
    return True, ""


if getattr(APP, "FIREWALL", None):
    APP.FIREWALL.shutil = _WHICH
    APP.FIREWALL._run = _fw_run
    APP.FIREWALL.UFW_DEFAULTS = str(TMP / "ufw-defaults")
if getattr(APP, "INTRUSION", None):
    _AUTH = "\n".join(
        f"Sep 24 {10 + i // 6:02d}:{i % 6 * 9:02d}:11 srv sshd[{900 + i}]: Failed password for "
        f"{'root' if i % 3 else 'invalid user admin'} from 203.0.113.{40 + i % 4} port {50000 + i} ssh2"
        for i in range(24)) + "\nSep 24 12:00:01 srv sshd[1]: Accepted publickey for root from 198.51.100.7 port 51000 ssh2\n"
    APP.INTRUSION.shutil = _WHICH
    APP.INTRUSION._ran_ok = lambda cmd, timeout=20: (True, _AUTH if "journalctl" in cmd else "")
    APP.INTRUSION._run = lambda cmd, timeout=20: (
        "Port 22\nPasswordAuthentication yes\nPermitRootLogin yes\n" if "sshd_config" in cmd else "")

# تاریخچه‌ی مصرف — مسیرِ پیش‌فرض بیرون از مخزن است و خالی؛ بی‌این
# samples/hourly هیچ‌وقت عضوی برای مقایسه نداشتند
APP.HISTORY_PATH = TMP / "history.json"
APP.HISTORY_PATH.write_text(json.dumps(
    [{"t": f"2026-09-24T{h:02d}:00", "cpu": 20.0 + h, "mem": 50.0, "conn": 300 + 20 * h, "ips": 80 + h}
     for h in range(24)]), encoding="utf-8")
APP.BOT_DB = TMP / "bot.db"
APP.BILLING_DB = TMP / "billing.db"
APP.ADMIN_PASSWORD = "testpw"
APP.AUTH_PATH = TMP / "auth.json"
APP.load_password = lambda: "testpw"

# The live FX source is on the internet. Without this stub the contract depended
# on tgju.org being reachable: offline, the backend returns its {error, hint}
# fallback and /billing/fx "drifted" although neither side had changed.
if getattr(APP, "FX", None):                  # accounting (Pro); absent in the Community tree
    APP.FX._fetch_tgju = lambda timeout=12: {
        "current": {"price_eur": {"p": "1,120,000", "ts": "2026-09-24 12:00:00"}}}

# Everything below used to come from the machine the test ran on: a built
# frontend/dist, /tmp/nexora-update.log and /root/nexora-snapshots left over
# from earlier runs. On a clean CI runner none exist (and /root is not even
# readable), so three routes answered in their "nothing yet" shape and the
# contract failed there while passing locally. The state is now the test's own.
APP.UPDATE_LOG = str(TMP / "update.log")
Path(APP.UPDATE_LOG).write_text("✓ backup\nUPDATE COMPLETE\n", encoding="utf-8")
APP.SNAP_DIR = TMP / "snapshots"
(APP.SNAP_DIR / "20260924-120000").mkdir(parents=True, exist_ok=True)
(APP.SNAP_DIR / "20260924-120000" / "VERSION").write_text("2.0.0", encoding="utf-8")
(APP.SNAP_DIR / "20260924-120000" / "config.json").write_text("{}", encoding="utf-8")
_BUILT = TMP / "built-root"
(_BUILT / "frontend" / "dist").mkdir(parents=True, exist_ok=True)
(_BUILT / "frontend" / "src").mkdir(parents=True, exist_ok=True)
(_BUILT / "frontend" / "src" / "App.jsx").write_text("", encoding="utf-8")
(_BUILT / "frontend" / "dist" / "index.html").write_text("", encoding="utf-8")
_build_info = APP._frontend_build_info


def _built_panel():
    # the real function, pointed at a root whose panel is built
    real = APP._root_dir
    APP._root_dir = lambda: _BUILT
    try:
        return _build_info()
    finally:
        APP._root_dir = real


APP._frontend_build_info = _built_panel

# یک گروهِ صورتحساب‌دار — بی‌این صورتحسابی نیست و ردیف‌هایش سنجیده نمی‌شوند
if APP.PRO_LOADED:                          # accounting (Pro); no invoices without it
    APP.billing_group_put("de-1", {"billable": True, "rates": [{"gb": 50, "price": 120000, "perDevice": 20000}]},
                          x_admin_password="testpw")


# ── صداکننده‌ی ASGI، بی‌وابستگی ──
async def _asgi_get(path, headers):
    q = ""
    if "?" in path:
        path, q = path.split("?", 1)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": q.encode(),
             "root_path": "", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
             "client": ("127.0.0.1", 1234), "server": ("testserver", 80)}
    got = {"status": 0, "body": b""}
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(3600)

    async def send(msg):
        if msg["type"] == "http.response.start":
            got["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            got["body"] += msg.get("body", b"")

    await asyncio.wait_for(APP.app(scope, receive, send), timeout=20)
    return got["status"], got["body"]


def call(path):
    try:
        # از ۱.۱۲۹ مسیرهای مدیر پشتِ نشانیِ مخفی‌اند؛ بی این هدر همه ۴۰۴ می‌گیرند
        st, body = asyncio.run(_asgi_get(path, {"X-Admin-Password": "testpw",
                                                "X-Admin-Path": APP.admin_path()}))
        try:
            return st, json.loads(body.decode("utf-8") or "null")
        except Exception:
            return st, {"__nonjson": body[:80].decode("utf-8", "replace")}
    except Exception as e:                                      # noqa: BLE001
        return 0, {"__exc": f"{type(e).__name__}: {e}"[:120]}


def keys(v, prefix="", only=None):
    """کلیدهای سطحِ اول، و کلیدهای اولین عضوِ هر آرایه‌ی شیء (یک سطح).

    `only`: فقط آرایه‌ها/شیءهایی که این‌جا هم پُرند باز می‌شوند — آرایه‌ی
    خالیِ بکند (فیکسچرِ کوچک) کلیدِ عضو ندارد و نباید «اختراع» شمرده شود."""
    out = set()
    if isinstance(v, dict):
        for k, x in v.items():
            out.add(prefix + k)
            if only is not None and not only.get(k):
                continue
            if isinstance(x, list) and x and isinstance(x[0], dict):
                out |= {prefix + k + "[]." + kk for kk in x[0].keys()}
            elif isinstance(x, dict) and not prefix:
                out |= {prefix + k + "." + kk for kk in x.keys()}
    return out


#: مسیرهایی که باید هم‌شکل بمانند. با هر فضای کاری که بازسازی می‌شود
#: (docs/specs/2026-09-24-panel-overhaul.md) این فهرست بزرگ‌تر می‌شود؛
#: مسیری که یک‌بار درست شد، دوباره کهنه نمی‌شود.
MUST_MATCH = {
    # فضای ۱ — صفحه‌ی اشتراک
    "/api/admin/config", "/api/admin/config/history", "/api/admin/themes",
    "/api/admin/stats", "/api/admin/system", "/api/admin/github",
    "/api/admin/maintenance", "/api/admin/snapshots", "/api/admin/update-log",
    "/api/admin/bot/users/report",
    # پیش‌تر درست‌شده‌ها
    "/api/admin/bot/funnel", "/api/admin/bot/alerts", "/api/admin/bot/discounts",
    "/api/admin/bot/inbox",
    # فضای ۲ — تانل و مانیتورینگ
    "/api/admin/tunnel/overview", "/api/admin/monitor", "/api/admin/health/all",
    "/api/admin/top-clients", "/api/admin/usage-history",
    "/api/admin/tunnel/1/metrics", "/api/admin/tunnel/1/config",
    "/api/admin/tunnel/node/1/sysmon", "/api/admin/tunnel/node/1/check",
    "/api/admin/tunnel/node/1/diagnose", "/api/admin/tunnel/1/jobs",
    # فضای ۳ — فایروال
    "/api/admin/firewall", "/api/admin/firewall/blocked", "/api/admin/firewall/intrusion",
    "/api/admin/firewall/suggest", "/api/admin/firewall/preflight", "/api/admin/firewall/rollback-state",
    # فضای ۴ — ربات
    "/api/admin/bot/status", "/api/admin/bot/orders", "/api/admin/bot/users", "/api/admin/bot/plans",
    "/api/admin/bot/affiliates", "/api/admin/bot/events", "/api/admin/bot/settings",
    # فضای ۵ — نمایندگی
    "/api/admin/tenant/portal-list",
    # فضای ۶ — حسابداری
    "/api/admin/billing/overview", "/api/admin/billing/groups", "/api/admin/billing/ledger",
    "/api/admin/billing/payments", "/api/admin/billing/expenses", "/api/admin/billing/clients",
    "/api/admin/billing/fx", "/api/admin/billing/xui-path",
}

#: Pro routes (license.PRO_PATHS, docs/specs/2026-09-29-pro-split.md) exist
#: only when the Pro code is in the tree, so they are held to the same rule only
#: then; in the Community tree they would read as "missing" and fail the gate
#: for nothing.
MUST_MATCH |= {"/api/admin/channel", "/api/admin/channel/ai", "/api/admin/channel/suggestions"}
if APP.PRO_LOADED:
    # Compare shapes, not the lock: every Pro route answers as if licensed.
    APP.LIC.allowed = lambda feature, st=None: True
else:
    MUST_MATCH = {p for p in MUST_MATCH if APP.LIC.pro_feature_of(p) is None}

#: مسیرهای پارامتری با یک شناسه‌ی واقعی از فیکسچر — فهرستِ خودکار
#: هر مسیرِ «{…}» دار را کنار می‌گذارد، پس بی‌این زیرمسیرهای تانل هیچ‌وقت
#: سنجیده نمی‌شدند و هارنس کلِ overview را برای همه‌شان برمی‌گرداند.
CONCRETE = [
    "/api/admin/tunnel/1/metrics", "/api/admin/tunnel/1/config",
    "/api/admin/tunnel/node/1/sysmon", "/api/admin/tunnel/node/1/check",
    "/api/admin/tunnel/node/1/diagnose", "/api/admin/tunnel/1/jobs",
]


def main():
    # مسیرهایی که عمداً بیرون‌اند — با دلیل
    SKIP = {
        "/api/admin/export": "فایل برمی‌گرداند، نه JSON",
        "/api/admin/bot/users/export": "CSV برمی‌گرداند",
        "/api/admin/bot/users/report/pdf": "PDF برمی‌گرداند",
        "/api/admin/firewall/blackhole/export": "فایل برمی‌گرداند",
    }

    routes = sorted({r.path for r in APP.app.routes
                     if getattr(r, "methods", None) and "GET" in r.methods
                     and r.path.startswith("/api/admin") and "{" not in r.path})
    routes = [p for p in routes if p not in SKIP] + CONCRETE

    hs = subprocess.run(["node", str(ROOT / "tests" / "harness" / "harness-shapes.cjs"), *routes],
                        capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
    try:
        HARN = json.loads(hs.stdout or "{}")
    except Exception:
        print(f"{R}harness-shapes failed:{X} {hs.stdout[:200]} {hs.stderr[:300]}")
        sys.exit(1)
    if "__boot_error" in HARN:
        print(f"{R}harness boot error:{X} {HARN['__boot_error'][:300]}")
        sys.exit(1)

    print(f"\n{D}── contract: harness vs backend, {len(routes)} admin GET routes ──{X}")
    drift = compared = skipped = 0
    done = set()
    broken = []
    for p in routes:
        st, real = call(p)
        fake = HARN.get(p)
        if st != 200 or not isinstance(real, dict) or (len(real) <= 2 and real.get("ready") is False):
            skipped += 1
            if SHOW_ALL:
                why = real.get("error") or real.get("detail") or real.get("__exc") or "" if isinstance(real, dict) else ""
                print(f"  {D}- {p:44} backend {st} {str(why)[:60]}{X}")
            continue
        if not isinstance(fake, dict) or fake == {"ready": True} or "__error" in fake:
            skipped += 1
            if SHOW_ALL:
                print(f"  {D}- {p:44} harness has no specific mock{X}")
            continue
        compared += 1
        done.add(p)
        kr, kf = keys(real), keys(fake, only=real)
        invented = sorted(kf - kr)
        missing = sorted(kr - kf)
        if invented or missing:
            drift += 1
            if p in MUST_MATCH:
                broken.append(p)
            print(f"  {Y}≠{X} {p}")
            if invented:
                print(f"      {R}harness invents:{X} {', '.join(invented[:10])}")
            if missing:
                print(f"      {D}harness lacks:  {', '.join(missing[:10])}{X}")
        elif SHOW_ALL:
            print(f"  {G}={X} {p}")

    print(f"\n  compared {compared}, drift {drift}, skipped {skipped} (backend not ready on empty fixtures or no mock)")
    # مسیرِ «باید هم‌شکل» که مقایسه نشد هم خطاست — یعنی دروازه بی‌صدا کور شده
    # «باید هم‌شکل» که *مقایسه نشد* هم خطاست، نه فقط آن‌که در فهرست نیست.
    # یک‌بار جایگزینیِ داده در هارنس تابعِ fetch را پاک کرد: همه‌ی مسیرها
    # «هارنس mock ندارد» شدند، رد شدند، و دروازه سبز ماند.
    lost = sorted(p for p in MUST_MATCH if p not in done)
    if broken or lost:
        print(f"  {R}FAIL{X} must-match drifted: {', '.join(broken)}" + (f"  missing routes: {', '.join(lost)}" if lost else "") + "\n")
        sys.exit(1)
    print(f"  {G}OK{X} all {len(MUST_MATCH)} must-match routes agree with the backend\n")
    if not field_reads():
        sys.exit(1)
    if not billing_columns():
        sys.exit(1)
    sys.exit(0)


def billing_columns():
    """
    ستون‌هایی که کوئری‌های حسابداری می‌خوانند، در اسکیمای واقعیِ billing.db.

    همان دروازه‌ی `test-seams` برای جدول‌های ربات — که هشدارِ سلامت را
    گرفت: کوئری ستونِ ناموجود می‌خواند و `except: pass` می‌بلعید. اسکیمای
    حسابداری فقط با import کردنِ خودِ app ساخته می‌شود، پس این‌جاست.
    """
    import ast as _ast
    import re as _re
    c = APP._billing_conn()
    try:
        tables = {r[0]: {x[1] for x in c.execute(f"PRAGMA table_info({r[0]})")}
                  for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        c.close()
    src = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    bad = []
    for node in _ast.walk(_ast.parse(src)):
        if isinstance(node, _ast.Constant) and isinstance(node.value, str):
            txt = node.value
        elif isinstance(node, _ast.JoinedStr):
            txt = "".join(v.value for v in node.values
                          if isinstance(v, _ast.Constant) and isinstance(v.value, str))
        else:
            continue
        flat = " ".join(txt.split())
        if _re.search(r"\bJOIN\b", flat, _re.I):
            continue
        for m in _re.finditer(r"SELECT\s+(.+?)\s+FROM\s+(\w+)\b", flat, _re.I):
            cols = tables.get(m.group(2))
            if cols is None:
                continue
            for col in m.group(1).split(","):
                w = col.strip().split()[0] if col.strip() else ""
                if _re.fullmatch(r"[a-z_]+", w) and w != "distinct" and w not in cols:
                    bad.append(f"app.py:{node.lineno} {m.group(2)}.{w}")
        for m in _re.finditer(r"UPDATE\s+(\w+)\s+SET\s+([a-z_]+)\s*=", flat, _re.I):
            cols = tables.get(m.group(1))
            if cols is not None and m.group(2) not in cols:
                bad.append(f"app.py:{node.lineno} {m.group(1)}.{m.group(2)}")
    print(f"{D}── billing columns: queries vs real billing.db ({len(tables)} tables) ──{X}")
    for b in sorted(set(bad)):
        print(f"  {R}✗{X} {b}")
    if not bad:
        print(f"  {G}OK{X} every billing column the queries use exists\n")
    return len(tables) > 3 and not bad


#: رابط فقط فیلدی را بخواند که بکند واقعاً می‌فرستد.
#
# شکلِ هارنس را بالا با بکند می‌سنجیم؛ ولی خودِ JSX هم می‌توانست فیلدِ
# خیالی بخواند. ردیف‌های صورتحساب `it.lineTotal` می‌خواندند که بکند هرگز
# نفرستاده بود (نامش amount است): روی سرور همه‌ی ردیف‌ها «بدون نرخ» بودند
# و جمعِ بالای صفحه درست. همین نوع در «تلاش برای نفوذ» (a.tries،
# a.blocked) و همکاری در فروش (totalPaid) هم پیدا شد.
#
# (فایل، آغازِ بلوکِ رندر، متغیرِ حلقه، مسیر، مسیرِ آرایه در JSON، کلیدهای
#  شرطیِ مجاز — آن‌هایی که بکند فقط گاهی می‌گذارد)
FIELD_READS = [
    ("pro/billing.jsx", "(inv.items || []).map((it, i) =>", "it",
     "/api/admin/billing/invoice/de-1", ["items"], set()),
    ("sections/bot/orders.jsx", "orders.map((o) =>", "o",
     "/api/admin/bot/orders?status=all", ["orders"], set()),
    ("pro/affiliates.jsx", "list.map((a) =>", "a",
     "/api/admin/bot/affiliates", ["affiliates"], set()),
    ("pro/intrusion.jsx", "pageRows.map((a) =>", "a",
     "/api/admin/firewall/intrusion", ["ssh", "attempts"],
     {"owner", "ownerKind", "ownerWhy", "ptr", "clients"}),
    # سطحِ بالا: کلِ یک کامپوننت، `d` خودِ پاسخ است (path خالی)
    # هزینه‌ها `d.count` و `d.trafficCost` می‌خواند که بکند نمی‌فرستاد
    # `error` را خودِ رابط می‌گذارد (catchِ useJson)، نه بکند
    ("pro/expenses.jsx", "export function BillingExpenses(", "d",
     "/api/admin/billing/expenses", [], {"error"}),
    ("pro/expenses.jsx", "export function BillingLedger(", "d",
     "/api/admin/billing/ledger", [], set()),
    # فهرست‌های اصلیِ هر بخش — هیچ‌کدام امروز شبح ندارند؛ برای اینکه نداشته بمانند
    ("pro/billing.jsx", "(data.clients || []).map((c, i) =>", "c",
     "/api/admin/billing/clients", ["clients"], set()),
    ("sections/bot/plans.jsx", "{plans.map((p, i) =>", "p",
     "/api/admin/bot/plans", ["plans"], set()),
    ("sections/bot/users.jsx", "{users.map((u) =>", "u",
     "/api/admin/bot/users", ["users"], set()),
    ("sections/bot/stats.jsx", "(d.buyers || []).map((b) =>", "b",
     "/api/admin/bot/users/report", ["buyers"], set()),
    ("pro/tunnel.jsx", "(data.nodes || []).map((n) =>", "n",
     "/api/admin/tunnel/overview", ["nodes"], set()),
    ("pro/tunnel.jsx", "(data.tunnels || []).map((t) =>", "t",
     "/api/admin/tunnel/overview", ["tunnels"], set()),
    ("pro/tunnel.jsx", "{servers.map((sv, i) =>", "sv",
     "/api/admin/health/all", ["servers"], set()),
    ("pro/nodes-monitor.jsx", "{d.jobs.map((j) =>", "j",
     "/api/admin/tunnel/1/jobs", ["jobs"], set()),
    ("pro/nodes-monitor.jsx", "{nodes.map((n) =>", "n",
     "/api/admin/tunnel/overview", ["nodes"], set()),
    ("pro/expenses.jsx", "(d.owing || []).map((g) =>", "g",
     "/api/admin/billing/ledger", ["debtors"], set()),
    ("pro/intrusion.jsx", "(d.advice || []).map((a, idx) =>", "a",
     "/api/admin/firewall/intrusion", ["advice"], set()),
]


def _block(src, anchor):
    if anchor.startswith("export function"):
        a = src.index(anchor)
        b = src.find(chr(10) + "export function", a + 10)
        return src[a:b if b > 0 else len(src)]
    i = src.index(anchor) + len(anchor)
    depth, j = 1, src.index("(", src.index(anchor))
    # از پرانتزِ «map(» تا جفتش
    j = src.index("map(", src.index(anchor)) + 3
    depth = 0
    for k in range(j, min(len(src), j + 12000)):
        if src[k] == "(":
            depth += 1
        elif src[k] == ")":
            depth -= 1
            if depth == 0:
                return src[j:k]
    return src[i:i + 6000]


def field_reads():
    import re as _re
    bad = []
    for f, anchor, var, route, path, optional in FIELD_READS:
        if f.startswith("pro/") and not (ROOT / "frontend" / "src" / "pro").is_dir():
            continue                    # a Pro screen; none in the Community tree
        src = io.open(ROOT / "frontend" / "src" / f, encoding="utf-8").read()
        if anchor not in src:
            bad.append(f"{f}: anchor gone «{anchor}» — update FIELD_READS")
            continue
        reads = set(_re.findall(r"(?<![\w.])" + var + r"\.([A-Za-z_]\w*)", _block(src, anchor)))
        st, body = call(route)
        rows = body
        for k in path:
            rows = (rows or {}).get(k) if isinstance(rows, dict) else None
        if isinstance(rows, dict):
            rows = [rows]
        if st != 200 or not rows:
            bad.append(f"{f}: backend {route} gave no rows (status {st}) — gate would be blind")
            continue
        keys = set().union(*(r.keys() for r in rows if isinstance(r, dict))) | optional
        ghost = sorted(reads - keys)
        if ghost:
            bad.append(f"{f}: reads {', '.join(var + '.' + g for g in ghost)} — not in {route}")
    print(f"{D}── field reads: JSX vs backend rows ({len(FIELD_READS)} renderers) ──{X}")
    for b in bad:
        print(f"  {R}✗{X} {b}")
    if not bad:
        print(f"  {G}OK{X} every field these renderers read exists in the backend response\n")
    return not bad


if __name__ == "__main__" and os.environ.get("NX_CONTRACT_IMPORT_ONLY") != "1":
    main()
