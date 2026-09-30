"""
تست کلاینت 3x-ui روی یک پنل شبیه‌سازی‌شده‌ی نسخه‌ی ۳.

چرا این تست وجود دارد:
    چرخه‌ی ساخت کانفیگ چند بار «درست شده» اعلام شد و نشده بود، چون
    هیچ تستی رفتار واقعی پنل را نمی‌سنجید. این فایل همان رفتار را —
    طبق مشخصات رسمی OpenAPI نسخه‌ی ۳.۷ — شبیه‌سازی می‌کند:

      * /panel/api/clients/add فقط JSON می‌خواند؛ form رد می‌شود
      * پنل خودش uuid می‌سازد؛ کلید id یک عددِ ردیف دیتابیس است
      * مسیر به‌روزرسانی /panel/api/clients/update/{email} است،
        و /panel/api/inbounds/updateClient اصلاً وجود ندارد
      * حذف با ایمیل انجام می‌شود و پاسخ خالی ۲۰۴ یعنی موفق

    هر کدام از این‌ها یک‌بار باگ واقعی بوده‌اند.

اجرا:  python3 test_xui.py
"""
import io
import json
import os
# repo root and bot/ — these tests moved from bot/ to tests/bot/ (2.0 layout)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOT_DIR = os.path.join(_ROOT_DIR, "bot")

import re
import sys
import threading
import uuid as uuidlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote

# bot/ was this file's own folder before the move, so `import xui` worked by accident
sys.path.insert(0, _BOT_DIR)
import xui as X  # noqa: E402

G, R, D, X0 = "\033[38;5;42m", "\033[38;5;203m", "\033[38;5;245m", "\033[0m"
_ok = _fail = 0


def section(t):
    print(f"\n{D}{'─' * 52}{X0}\n{t}\n{D}{'─' * 52}{X0}")


def check(name, cond, detail=""):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  {G}✅{X0} {name}" + (f" {D}— {detail}{X0}" if detail else ""))
    else:
        _fail += 1
        print(f"  {R}❌{X0} {name}" + (f" {D}— {detail}{X0}" if detail else ""))


# ═══════════════ پنل شبیه‌سازی‌شده ═══════════════

# فقط مسیرهایی که کلاینت ما به آن‌ها نیاز دارد — با همان نام‌های
# واقعی نسخه‌ی ۳. نبودن updateClient اینجا عمدی است.
SPEC = {"paths": {
    "/panel/api/inbounds/list": {"get": {}},
    "/panel/api/inbounds/get/{id}": {"get": {}},
    "/panel/api/setting/all": {"post": {}},
    "/panel/api/clients/add": {"post": {}},
    "/panel/api/clients/get/{email}": {"get": {}},
    "/panel/api/clients/list": {"get": {}},
    "/panel/api/clients/update/{email}": {"post": {}},
    "/panel/api/clients/del/{email}": {"post": {}},
    "/panel/api/clients/bulkDel": {"post": {}},
    "/panel/api/clients/traffic/{email}": {"get": {}},
    "/panel/api/clients/links/{email}": {"get": {}},
    "/panel/api/clients/resetTraffic/{email}": {"post": {}},
}}

INBOUNDS = [
    {"id": 28, "remark": "DE", "protocol": "vless", "port": 443, "enable": True},
    {"id": 41, "remark": "FI", "protocol": "vless", "port": 8443, "enable": True},
    {"id": 47, "remark": "FR", "protocol": "vless", "port": 443, "enable": True},
    {"id": 45, "remark": "TR", "protocol": "trojan", "port": 2096, "enable": False},
]

CLIENTS, ATTACH, SEEN = {}, {}, []
_row = [14800]


#: وضعیت قابل‌تغییر پنل شبیه‌سازی‌شده، برای ساختن حالت‌های خراب
STATE = {"expired": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _login_page(self):
        """
        همان چیزی که 3x-ui وقتی نشست منقضی شده باشد برمی‌گرداند:
        ریدایرکت به /login، و چون requests دنبال ریدایرکت می‌رود،
        نتیجه HTTP 200 با بدنه‌ی HTML است — نه ۴۰۱.
        """
        b = b"<!DOCTYPE html><html><body>login</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _send(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _ok(self, obj=None, msg=""):
        self._send({"success": True, "msg": msg, "obj": obj})

    def _fail(self, msg, code=200):
        self._send({"success": False, "msg": msg}, code)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if "application/json" not in (self.headers.get("Content-Type") or "").lower():
            return None, "invalid request body: expected JSON"
        try:
            return json.loads(raw or b"{}"), None
        except ValueError:
            return None, "malformed JSON"

    def do_GET(self):
        p = unquote(self.path.split("?")[0])
        SEEN.append(("GET", p))

        if p == "/panel/api/openapi.json":
            return self._send(SPEC)
        if p == "/panel/api/inbounds/list":
            return self._ok(INBOUNDS)
        if p == "/panel/api/clients/list":
            return self._ok(list(CLIENTS.values()))

        m = re.fullmatch(r"/panel/api/clients/get/(.+)", p)
        if m:
            c = CLIENTS.get(m.group(1))
            if not c:
                return self._fail("client not found")
            # پاسخ نسخه‌ی ۳ تودرتوست
            return self._ok({"client": c, "inboundIds": ATTACH.get(c["email"], []),
                             "usedTraffic": {"up": 1024, "down": 2048},
                             "externalLinks": []})

        m = re.fullmatch(r"/panel/api/clients/traffic/(.+)", p)
        if m:
            c = CLIENTS.get(m.group(1))
            if not c:
                return self._fail("client not found")
            return self._ok({"email": c["email"], "up": 1048576, "down": 2097152,
                             "total": c["totalGB"], "uuid": c["uuid"]})

        m = re.fullmatch(r"/panel/api/clients/links/(.+)", p)
        if m:
            c = CLIENTS.get(m.group(1))
            if not c:
                return self._fail("client not found")
            return self._ok([f"vless://{c['uuid']}@h:{i}#{c['email']}"
                             for i in ATTACH.get(c["email"], [])])

        return self._fail(f"no route {p}", 404)

    def do_POST(self):
        # نشست منقضی — تا وقتی دوباره لاگین نشده، همه‌چیز صفحه‌ی ورود
        if STATE.get("expired") and "/login" not in self.path:
            # expired عددی است: هر بار یکی کم می‌شود، پس می‌شود حالتی
            # ساخت که فقط *یک بار* صفحه‌ی ورود بیاید و بعد درست شود
            STATE["expired"] -= 1
            # بدنه باید خوانده شود، وگرنه سرور سوکت را با داده‌ی
            # خوانده‌نشده می‌بندد و سیستم‌عامل RST می‌فرستد — کلاینت
            # آن را ConnectionAborted می‌بیند. بقیه‌ی مسیرهای این
            # handler همین کار را می‌کنند؛ این یکی جا افتاده بود و
            # تست را حدود یک بار در هر ده اجرا می‌انداخت.
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            return self._login_page()
        p = unquote(self.path.split("?")[0])

        if p == "/login":
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            return self._ok(msg="ok")

        if p == "/panel/api/setting/all":
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            return self._ok({"subEnable": True, "subURI": "",
                             "subDomain": "sub.example.ir", "subPort": 2096,
                             "subPath": "/sub/", "subCertFile": "/c.pem"})

        if p == "/panel/api/clients/add":
            body, err = self._body()
            SEEN.append(("POST", p, "json" if body is not None else "form"))
            if err:
                return self._fail(err, 400)
            cl = (body or {}).get("client")
            if not isinstance(cl, dict) or not cl.get("email"):
                return self._fail("client email is required", 400)
            ids = [int(x) for x in (body.get("inboundIds") or [])]
            if not ids:
                return self._fail("inboundIds is required", 400)
            email = cl["email"]
            _row[0] += 1
            CLIENTS[email] = {
                "id": _row[0],                    # عدد، نه uuid
                "uuid": str(uuidlib.uuid4()),     # uuid واقعی
                "email": email,
                "enable": bool(cl.get("enable", True)),
                "totalGB": int(cl.get("totalGB") or 0),
                "expiryTime": int(cl.get("expiryTime") or 0),
                "limitIp": int(cl.get("limitIp") or 0),
                "limitHwid": int(cl.get("limitHwid") or 0),
                "tgId": int(cl.get("tgId") or 0),
                "subId": cl.get("subId") or email,
                "flow": cl.get("flow") or "",
            }
            ATTACH[email] = ids
            return self._ok(msg="Client added")

        m = re.fullmatch(r"/panel/api/clients/update/(.+)", p)
        if m:
            body, err = self._body()
            SEEN.append(("POST", p, "json" if body is not None else "form"))
            if err:
                return self._fail(err, 400)
            c = CLIENTS.get(m.group(1))
            if not c:
                return self._fail("client not found")
            for k in ("totalGB", "expiryTime", "limitIp", "limitHwid", "tgId"):
                if k in body:
                    c[k] = int(body[k] or 0)
            if "enable" in body:
                c["enable"] = bool(body["enable"])
            return self._ok(msg="Client updated")

        m = re.fullmatch(r"/panel/api/clients/del/(.+)", p)
        if m:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            email = m.group(1)
            if email not in CLIENTS:
                return self._fail("client not found")
            CLIENTS.pop(email)
            ATTACH.pop(email, None)
            # حذف، بدنه‌ی خالی با ۲۰۴ می‌دهد — این نباید خطا حساب شود
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        return self._fail(f"no route {p}", 404)


srv = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"

print(f"\n{D}پنل شبیه‌سازی‌شده روی {BASE}{X0}")
c = X.XUI(BASE, "admin", "admin")
EMAIL = "nexora_555_1"

# ═══════════════ اتصال ═══════════════
section("اتصال و کشف مسیر")
check("خواندن اینباندها", len(c.inbounds()) == 4)
check("خواندن مسیرها از OpenAPI", len(c.discover()) == len(SPEC["paths"]))
check("مسیر افزودن شناخته شد",
      c.has_route("/panel/api/clients/add", "POST") is True)
check("مسیر به‌روزرسانی نسخه‌ی ۳ شناخته شد",
      c.has_route(f"/panel/api/clients/update/{EMAIL}", "POST") is True)
check("مسیر قدیمی updateClient وجود ندارد",
      c.has_route("/panel/api/inbounds/updateClient/x", "POST") is False)

# ═══════════════ ساخت ═══════════════
section("ساخت اشتراک")
res = c.create_subscription(41, EMAIL, gb=50, days=30, ip_limit=2,
                            tg_id=555, inbound_ids=[28, 41, 47])
panel = CLIENTS.get(EMAIL)
check("کلاینت در پنل ساخته شد", panel is not None)
check("بدنه به‌صورت JSON فرستاده شد", c._body_style == "json", str(c._body_style))
check("به هر ۳ اینباند وصل شد", sorted(ATTACH.get(EMAIL, [])) == [28, 41, 47],
      str(ATTACH.get(EMAIL)))

# مهم‌ترین بررسی این فایل: پنل uuid خودش را می‌سازد. اگر آن را
# نخوانیم، هر تمدید و مسدودکردنی بعداً روی شناسه‌ی اشتباه می‌رود.
check("uuid برگشتی همان uuid پنل است", res["uuid"] == panel["uuid"],
      f"ما={res['uuid']} پنل={panel['uuid']}")
check("id عددیِ پنل با uuid اشتباه نشده", res["uuid"] != panel["id"],
      f"id عددی={panel['id']}")
check("حجم درست ثبت شد", panel["totalGB"] == 50 * 1024 ** 3)
check("tgId درست ثبت شد", panel["tgId"] == 555)
check("کانفیگ‌ها گرفته شدند", len(res["configs"]) == 3,
      f"{len(res['configs'])} کانفیگ")

# ═══════════════ لینک اشتراک ═══════════════
section("لینک اشتراک")
check("بدون دامنه‌ی مدیر، از تنظیمات پنل ساخته می‌شود",
      res["sub_url"] == f"https://sub.example.ir:2096/sub/{res['sub_id']}",
      str(res["sub_url"]))

c2 = X.XUI(BASE, "admin", "admin")
r2 = c2.create_subscription(41, "nexora_666_1", gb=10, days=7, tg_id=666,
                            sub_base_url="https://my.dom/sub", inbound_ids=[41])
check("دامنه‌ی مدیر اولویت دارد",
      r2["sub_url"] == f"https://my.dom/sub/{r2['sub_id']}", str(r2["sub_url"]))

# ═══ آدرس اشتراک نباید از روی شناسه‌ی تلگرام ساختنی باشد ═══
#
# قبلاً subId دقیقاً همان ایمیل بود: prefix_tgid_seq. مسیر اشتراک در
# 3x-ui رمز نمی‌خواهد، پس کسی که یک کانفیگ خودش را دارد پیشوند و
# دامنه را می‌داند و می‌تواند بازه‌ای از شناسه‌های تلگرام را پویش کند
# و اشتراک زنده‌ی بقیه را بردارد.
check("شناسه‌ی لینک دیگر همان ایمیل نیست", res["sub_id"] != EMAIL,
      res["sub_id"])
# «۵۵۵ در رشته نباشد» تستِ درستی نبود: بخش تصادفیِ شناسه شانزده رقم
# هگز است و «۵۵۵» در حدود ۰٫۳٪ از آن‌ها تصادفی ظاهر می‌شود — یعنی
# تقریباً یک اجرا از هر سیصد تا، بی‌آنکه چیزی خراب باشد. روی CI افتاد.
#
# خاصیتی که واقعاً اهمیت دارد «ساختنی‌نبودن» است، نه نبودِ یک رشته:
# شناسه نباید ساختارِ قدیمی (prefix_tgid_seq) را داشته باشد، و دو بار
# ساختنش با همان ورودی نباید یک نتیجه بدهد.
check("ساختار قدیمیِ prefix_tgid_seq دیگر نیست",
      "_555_" not in res["sub_id"],
      "هگز زیرخط ندارد، پس این بررسی تصادفی نیست")
check("و از روی ایمیل هم بازتولید نمی‌شود",
      X.XUI.make_sub_id(EMAIL) != res["sub_id"],
      "همان ورودی، شناسه‌ی دیگری — یعنی پویش بی‌فایده است")
check("ولی پیشوند برند می‌ماند", res["sub_id"].startswith("nexora_"),
      res["sub_id"])
check("هر بار متفاوت است",
      X.XUI.make_sub_id(EMAIL) != X.XUI.make_sub_id(EMAIL))
check("و برای آدرس امن است",
      re.fullmatch(r"[A-Za-z0-9_]+", res["sub_id"]) is not None,
      res["sub_id"])
check("ایمیل کلاینت دست‌نخورده می‌ماند", panel["email"] == EMAIL,
      "برند صفحه‌ی اشتراک از ایمیل خوانده می‌شود، نه از آدرس")

# ═══════════════ حجم بعد از تمدید ═══════════════
section("حجم بعد از تمدید")

# تمدید حجم را *جمع* می‌کند و شمارنده‌ی مصرف را صفر نمی‌کند، پس هر دو
# عدد روی هم می‌روند و با هم می‌خوانند. ولی ربات حجمِ ذخیره‌شده‌اش را
# به‌روز نمی‌کرد و همان اندازه‌ی پلن می‌ماند — یعنی مصرفِ تجمعی با
# سقفِ یک دوره سنجیده می‌شد. مشتری‌ای که ۴۵ از ۱۰۰ گیگ خرج کرده بود
# «۹۰٪» می‌دید و همان روز اولِ دوره‌ی تازه هشدار اتمام حجم می‌گرفت.

_g = X.XUI(BASE, "admin", "admin")
_ge = "nexora_777_1"
_gr = _g.create_subscription(41, _ge, gb=50, days=30, tg_id=777,
                             inbound_ids=[41])
_gp = _g.find_client(41, email=_ge)
check("حجم اولیه ۵۰ گیگ است", _gp["totalGB"] == 50 * 1024 ** 3,
      str(_gp["totalGB"]))

_ext = _g.extend_subscription(41, _gr["uuid"], add_days=30, add_gb=50,
                              email=_ge)
check("تمدید حجم نهایی را برمی‌گرداند", "total_bytes" in _ext,
      "بدون این، ربات باید همان فرمول را دوباره بنویسد و از پنل جدا بیفتد")
check("و عددش با پنل می‌خواند",
      _ext["total_bytes"] == _g.find_client(41, email=_ge)["totalGB"],
      str(_ext["total_bytes"]))
check("حجم جمع شده، نه جایگزین",
      _ext["total_bytes"] == 100 * 1024 ** 3,
      f"{_ext['total_bytes'] / 1024 ** 3:.0f} گیگ")
check("و به گیگ درست تبدیل می‌شود",
      int(round(_ext["total_bytes"] / (1024 ** 3))) == 100)

# تمدید با پلن نامحدود
_ext2 = _g.extend_subscription(41, _gr["uuid"], add_days=30, add_gb=0,
                               email=_ge)
check("پلن نامحدود حجم را صفر می‌کند", _ext2["total_bytes"] == 0,
      "صفر در x-ui یعنی نامحدود")

# تمدید بدون دست‌زدن به حجم
_ext3 = _g.extend_subscription(41, _gr["uuid"], add_days=10, email=_ge)
check("تمدیدِ فقط‌زمان حجم را دست نمی‌زند", _ext3["total_bytes"] == 0,
      "همان چیزی که بود برمی‌گردد، نه None")

HSRC = io.open(os.path.join(_BOT_DIR,
                            "handlers.py"), encoding="utf-8").read()
check("ربات همان عدد را ذخیره می‌کند",
      'ext.get("total_bytes")' in HSRC and "SET expires_at=?, gb=?" in HSRC,
      "وگرنه نوار مصرف و هشدار ۸۰٪ هر دو با سقف اشتباه می‌سنجند")


# ═══════════════ خواندن ═══════════════
section("خواندن کلاینت")
check("با ایمیل", (c.find_client(41, email=EMAIL) or {}).get("email") == EMAIL)
check("با uuid", (c.find_client(41, client_uuid=res["uuid"]) or {}).get("email") == EMAIL)
check("مصرف خوانده شد", (c.client_traffic(EMAIL) or {}).get("up") == 1048576)

# ═══════════════ تمدید ═══════════════
section("تمدید و تغییر وضعیت")
c.extend_subscription(41, res["uuid"], add_days=30, add_gb=50, email=EMAIL)
check("حجم بعد از تمدید دو برابر شد",
      CLIENTS[EMAIL]["totalGB"] == 100 * 1024 ** 3,
      f"{CLIENTS[EMAIL]['totalGB'] / 1024 ** 3:.0f} GB")
check("انقضا جلو رفت", CLIENTS[EMAIL]["expiryTime"] > 0)

c.set_enabled(41, res["uuid"], False, email=EMAIL)
check("غیرفعال‌کردن اعمال شد", CLIENTS[EMAIL]["enable"] is False)
c.set_enabled(41, res["uuid"], True, email=EMAIL)
check("فعال‌کردن دوباره اعمال شد", CLIENTS[EMAIL]["enable"] is True)

# تمدید بدون ایمیل هم باید کار کند — کاربران قدیمی که فقط uuid دارند
c.extend_subscription(41, res["uuid"], add_days=10)
check("تمدید فقط با uuid هم کار می‌کند", CLIENTS[EMAIL]["expiryTime"] > 0)


# ═══════════════ نشست منقضی ═══════════════
section("وقتی نشست پنل منقضی می‌شود")

# 3x-ui در این حالت به صفحه‌ی ورود ریدایرکت می‌کند و requests دنبالش
# می‌رود، پس پاسخ HTTP 200 با بدنه‌ی HTML است — نه ۴۰۱.
#
# کد قبلی هر بدنه‌ی غیر JSON با وضعیت ۲xx را «موفق ولی بدون محتوا»
# حساب می‌کرد و None برمی‌گرداند. یعنی تمدید بی‌صدا هیچ کاری نمی‌کرد
# و ربات به مشتری می‌گفت «تمدید شد».

before = CLIENTS[EMAIL]["expiryTime"]
STATE["expired"] = 99
c._logged_in = True          # کلاینت هنوز فکر می‌کند نشست باز است

failed = None
try:
    c.extend_subscription(41, res["uuid"], add_days=30, email=EMAIL)
except X.XUIError as e:
    failed = str(e)

STATE["expired"] = 0

check("تمدیدِ ناموفق بی‌صدا «موفق» اعلام نمی‌شود",
      failed is not None or CLIENTS[EMAIL]["expiryTime"] != before,
      "یا خطا می‌دهد یا واقعاً انجام می‌شود — سکوت بدترین حالت است")
check("و تاریخ انقضا دست‌نخورده می‌ماند اگر خطا داد",
      failed is None or CLIENTS[EMAIL]["expiryTime"] == before,
      "وگرنه نصفه‌کاره نوشته شده")
if failed:
    check("پیام خطا قابل‌فهم است",
          "JSON" in failed or "ورود" in failed or "نشست" in failed,
          failed[:70])

# پاسخ خالیِ واقعی (مثل حذف) همچنان باید موفق باشد
c.set_enabled(41, res["uuid"], True, email=EMAIL)
check("پاسخ خالیِ معتبر همچنان موفق است", CLIENTS[EMAIL]["enable"] is True,
      "نباید این اصلاح، حذف و پاسخ‌های ۲۰۴ را بشکند")


# وقتی ورود دوباره جواب می‌دهد، عملیات باید خودش کامل شود
before2 = CLIENTS[EMAIL]["expiryTime"]
STATE["expired"] = 1          # فقط یک بار صفحه‌ی ورود
c._logged_in = True
c.extend_subscription(41, res["uuid"], add_days=7, email=EMAIL)
check("نشستِ منقضی خودش ترمیم می‌شود",
      CLIENTS[EMAIL]["expiryTime"] > before2,
      "یک بار دوباره لاگین می‌کند و کار را تمام می‌کند — نه خطا به مشتری")
check("و بیش از یک بار تلاش نمی‌کند", STATE["expired"] == 0,
      "حلقه‌ی بی‌پایانِ لاگین بدتر از خطاست")

# ═══════════════ حذف ═══════════════
section("حذف")
c.delete_client(41, res["uuid"], email=EMAIL)
check("کلاینت از پنل پاک شد", EMAIL not in CLIENTS)

print(f"\n{D}{'═' * 52}{X0}")
color = G if not _fail else R
print(f"  نتیجه:  {color}{_ok} پاس{X0}  |  "
      f"{R if _fail else D}{_fail} ناموفق{X0}")
print(f"{D}{'═' * 52}{X0}\n")
srv.shutdown()
sys.exit(1 if _fail else 0)
