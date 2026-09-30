"""
کلاینت API پنل 3x-ui.

طبق مستندات رسمی، احراز هویت یا با لاگین (کوکی نشست) انجام می‌شود
یا با توکن API از مسیر Settings → Security → API Token به‌صورت Bearer.
همه‌ی endpointها زیر /panel/api/ هر دو حالت را می‌پذیرند.
"""

import re
import json
import secrets
import time
import uuid as uuidlib
import logging
from datetime import datetime, timedelta

import requests

log = logging.getLogger("nexora.xui")


class XUIError(Exception):
    pass


class XUI:
    def __init__(self, base_url, username=None, password=None, token=None,
                 timeout=20, all_inbounds=True, default_flow="xtls-rprx-vision"):
        self.base = (base_url or "").rstrip("/")
        self.username = username
        self.password = password
        self.token = token
        self.timeout = timeout
        self.s = requests.Session()
        self._logged_in = False
        # مسیرهایی که یک‌بار جواب داده‌اند — تا هر بار دوباره نگردیم
        self._path_cache = {}
        self._routes = None
        self._spec = None
        self._body_style = None
        # مشتری روی همه‌ی اینباندها کانفیگ بگیرد، تا اگر یکی افتاد
        # بقیه کار کنند
        self.all_inbounds = all_inbounds
        self.default_flow = default_flow
        self._used_shape_attaches = False
        self._api_mode = None
        self._settings = None

    # ---------- احراز هویت ----------
    def _headers(self):
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def login(self):
        """اگر توکن داریم نیازی به لاگین نیست."""
        if self.token:
            self._logged_in = True
            return True
        if not (self.username and self.password):
            raise XUIError("نام کاربری یا رمز پنل تنظیم نشده است")

        r = self.s.post(f"{self.base}/login",
                        data={"username": self.username, "password": self.password},
                        timeout=self.timeout)
        try:
            data = r.json()
        except ValueError:
            raise XUIError(f"پاسخ نامعتبر از پنل (HTTP {r.status_code})")

        if not data.get("success"):
            raise XUIError(data.get("msg") or "ورود به پنل ناموفق بود")
        self._logged_in = True
        return True

    def _req(self, method, path, raw=False, _retried=False, **kw):
        """
        درخواست به پنل.

        raw=True برای پاسخ‌هایی که ساختار {success, obj} ندارند —
        مثل مشخصات OpenAPI که یک JSON استاندارد است.
        """
        if not self._logged_in:
            self.login()

        url = f"{self.base}{path}"
        kw.setdefault("timeout", self.timeout)
        kw["headers"] = {**self._headers(), **kw.get("headers", {})}

        r = self.s.request(method, url, **kw)

        # نشست منقضی شده — یک‌بار دوباره لاگین می‌کنیم
        if r.status_code in (401, 403) and not self.token:
            self._logged_in = False
            self.login()
            r = self.s.request(method, url, **kw)

        try:
            data = r.json()
        except ValueError:
            body = (r.text or "").strip()

            # بعضی مسیرها — مثل حذف — بدنه‌ی خالی برمی‌گردانند.
            # اگر کد وضعیت موفق بود، این خطا نیست.
            if 200 <= r.status_code < 300 and not body:
                return None

            # بدنه‌ی *غیرخالیِ* غیر JSON با وضعیت ۲۰۰ یعنی پنل صفحه‌ی
            # ورود را برگردانده: نشست منقضی شده و 3x-ui به /login
            # ریدایرکت کرده، و requests دنبالش رفته.
            #
            # قبلاً همین حالت هم «موفق ولی بدون محتوا» حساب می‌شد و
            # None برمی‌گشت — یعنی تمدید و مسدودکردن بی‌صدا هیچ کاری
            # نمی‌کردند و ربات به مشتری می‌گفت انجام شد.
            if 200 <= r.status_code < 300 and not _retried and not self.token:
                self._logged_in = False
                self.login()
                kw.pop("headers", None)
                return self._req(method, path, raw=raw, _retried=True, **kw)

            snippet = body[:120].replace("\n", " ")
            raise XUIError(
                f"پاسخ غیر JSON از {path} (HTTP {r.status_code})"
                + (f": {snippet}" if snippet else "")
                + " — احتمالاً نشست پنل منقضی شده یا آدرس پنل درست نیست")

        if raw:
            return data

        if not data.get("success", False):
            raise XUIError(data.get("msg") or f"خطا در {path}")
        return data.get("obj")

    # ---------- inbound ----------
    def inbounds(self):
        return self._req("GET", "/panel/api/inbounds/list") or []

    def inbound(self, inbound_id):
        return self._req("GET", f"/panel/api/inbounds/get/{inbound_id}")

    # ---------- کلاینت ----------
    def discover(self):
        """
        خواندن فهرست واقعی مسیرها از خود پنل.

        ۳x-ui از نسخه‌ی ۳ مشخصات OpenAPI را سرو می‌کند. به‌جای
        حدس زدن اینکه کدام نسخه چه مسیری دارد، همان را می‌خوانیم.
        این تنها راهی است که با نسخه‌های آینده هم کار می‌کند.
        """
        if self._routes is not None:
            return self._routes

        for path in ("/panel/api/openapi.json", "/openapi.json",
                     "/panel/openapi.json"):
            try:
                spec = self._req("GET", path, raw=True)
                if isinstance(spec, dict) and spec.get("paths"):
                    self._spec = spec
                    self._routes = {
                        p: set(m.upper() for m in ms)
                        for p, ms in spec["paths"].items()
                    }
                    return self._routes
            except Exception:
                continue

        self._routes = {}
        return self._routes

    def has_route(self, path, method="POST"):
        """آیا پنل این مسیر را دارد؟"""
        routes = self.discover()
        if not routes:
            return None          # نمی‌دانیم — باید امتحان کرد
        for p, methods in routes.items():
            # مسیرهای پارامتری مثل /clients/{email}
            pattern = re.sub(r"\{[^}]+\}", "[^/]+", p)
            if re.fullmatch(pattern, path) and method.upper() in methods:
                return True
        return False

    def request_schema(self, path, method="post"):
        """
        فیلدهایی که پنل برای یک مسیر انتظار دارد.

        مشخصات OpenAPI نه‌فقط مسیرها بلکه شکل بدنه را هم دارد. با
        خواندنش دیگر لازم نیست شکل‌های مختلف را حدس بزنیم — دقیقاً
        همان چیزی را می‌سازیم که پنل می‌خواهد.
        """
        self.discover()
        if not self._spec:
            return None

        node = (self._spec.get("paths") or {}).get(path, {}).get(method.lower())
        if not node:
            return None

        body = ((node.get("requestBody") or {}).get("content") or {})
        schema = None
        for ctype in ("application/json", "*/*"):
            if ctype in body:
                schema = body[ctype].get("schema")
                break
        if not schema:
            return None

        # ارجاع به تعریف مشترک را دنبال می‌کنیم
        seen = 0
        while isinstance(schema, dict) and "$ref" in schema and seen < 5:
            ref = schema["$ref"].split("/")[-1]
            schema = ((self._spec.get("components") or {})
                      .get("schemas", {}).get(ref))
            seen += 1

        return schema if isinstance(schema, dict) else None

    @staticmethod
    def _client_uuid(rec):
        """
        uuid واقعی کلاینت از رکورد پنل.

        در نسخه‌ی ۳ کلید id عدد است (ردیف دیتابیس) و uuid رشته‌ی
        واقعی. در نسخه‌های قدیمی برعکس، id همان uuid بود. پس هر دو
        را نگاه می‌کنیم و فقط چیزی را می‌پذیریم که شکل uuid داشته
        باشد — وگرنه یک عدد را به‌جای uuid ذخیره می‌کنیم.
        """
        if not isinstance(rec, dict):
            return None
        for key in ("uuid", "id"):
            v = rec.get(key)
            if isinstance(v, str) and re.fullmatch(
                    r"[0-9a-fA-F-]{32,40}", v.strip()):
                return v.strip()
        return None

    def _try_paths(self, candidates, label):
        """
        امتحان چند مسیر تا یکی جواب دهد.

        مسیرهای API بین نسخه‌های ۳x-ui عوض شده‌اند و از بیرون
        نمی‌شود فهمید کدام نسخه کدام را دارد. به‌جای حدس زدن،
        امتحان می‌کنیم و اولین مسیری که ۴۰۴ نمی‌دهد را نگه می‌داریم.
        """
        cached = self._path_cache.get(label)
        if cached:
            for method, path, payload in candidates:
                if path == cached:
                    return self._req(method, path, **payload)

        tried = []
        for method, path, payload in candidates:
            try:
                res = self._req(method, path, **payload)
                self._path_cache[label] = path
                return res
            except XUIError as e:
                msg = str(e)
                tried.append(f"{path} → {msg[:60]}")
                # فقط وقتی مسیر نبود ادامه می‌دهیم؛ خطای واقعی را
                # نباید پنهان کنیم
                if "404" not in msg and "not found" not in msg.lower():
                    raise

        raise XUIError(
            f"هیچ مسیری برای {label} جواب نداد. امتحان شد:\n" + "\n".join(tried))

    def add_client(self, inbound_id, email, gb=0, days=0, ip_limit=0,
                   client_uuid=None, tg_id=None, sub_id=None, flow=None,
                   group=None, inbound_ids=None, start_on_use=False):
        """
        افزودن کلاینت به inbound.

        gb=0 یعنی نامحدود، days=0 یعنی بدون انقضا.
        مقدار expiryTime به میلی‌ثانیه است.

        `start_on_use` یعنی «از اولین اتصال حساب کن»، نه از همین
        حالا. قرارداد خودِ ۳x-ui است: expiryTime منفی را مدت
        می‌فهمد و شمارش را وقتی شروع می‌کند که کلاینت اولین بار
        وصل شود.

        چرا لازم است: مشتری امروز می‌خرد و شاید هفته‌ی دیگر وصل
        شود. بدون این، آن هفته از سهمش کم می‌شود و حق دارد شاکی
        باشد.
        """
        client_uuid = client_uuid or str(uuidlib.uuid4())
        expiry = 0
        if days and days > 0:
            if start_on_use:
                expiry = -int(days * 86400 * 1000)
            else:
                expiry = int((datetime.now()
                              + timedelta(days=days)).timestamp() * 1000)

        client = {
            "id": client_uuid,
            "email": email,
            "enable": True,
            "totalGB": int(gb * 1024 ** 3) if gb else 0,
            "expiryTime": expiry,
            "limitIp": int(ip_limit or 0),
            "tgId": str(tg_id or ""),
            "subId": sub_id or email,
            "reset": 0,
        }
        # flow پیش‌فرض xtls-rprx-vision است — بدون آن، کانفیگ
        # REALITY کار نمی‌کند
        eff_flow = flow if flow is not None else self.default_flow
        if eff_flow:
            client["flow"] = eff_flow

        settings = json.dumps({"clients": [client]})

        # ── نسخه‌ی ۳: کلاینت مستقل است ──
        #
        # در معماری جدید، کلاینت جدا ساخته می‌شود و بعد به یک یا
        # چند inbound وصل می‌شود. این با مدل قدیمی که کلاینت داخل
        # JSON اینباند بود کاملاً فرق دارد.
        # مسیر ساخت در نسخه‌ی ۳ — از فهرست واقعی مسیرهای پنل
        create_path = None
        for cand in ("/panel/api/clients/add", "/panel/api/clients",
                     "/panel/api/clients/create"):
            if self.has_route(cand, "POST"):
                create_path = cand
                break
        if create_path is None and self.has_route("/panel/api/clients", "POST") is None:
            create_path = "/panel/api/clients"

        if create_path:
            # شکل بدنه بین نسخه‌های ۳.x فرق کرده. همان روش کشف
            # مسیر را برای شکل بدنه هم به‌کار می‌بریم: هرکدام که
            # پذیرفته شد را نگه می‌داریم.
            base = {
                "email": email,
                "id": client["id"],
                "totalGB": client.get("totalGB", 0),
                "expiryTime": client.get("expiryTime", 0),
                "limitIp": client.get("limitIp", 0),
                "enable": True,
                "subId": client.get("subId") or email,
                "tgId": client.get("tgId") or "",
                "reset": 0,
            }
            if group:
                base["groupName"] = group

            # اگر پنل شکل بدنه را اعلام کرده باشد، همان را می‌سازیم
            # به‌جای اینکه حدس بزنیم
            shapes = []
            schema = self.request_schema(create_path, "post")
            if schema:
                props = schema.get("properties") or {}
                if props:
                    # نگاشت نام‌های ما به نام‌هایی که پنل می‌خواهد
                    aliases = {
                        "email": ["email", "Email", "name", "remark"],
                        "id": ["id", "uuid", "Id", "clientId"],
                        "totalGB": ["totalGB", "total_gb", "totalBytes", "total"],
                        "expiryTime": ["expiryTime", "expiry_time", "expiry"],
                        "limitIp": ["limitIp", "limit_ip", "ipLimit"],
                        "enable": ["enable", "enabled", "active"],
                        "subId": ["subId", "sub_id", "subscriptionId"],
                        "tgId": ["tgId", "tg_id", "telegramId"],
                        "groupName": ["groupName", "group_name", "group"],
                        "inboundId": ["inboundId", "inbound_id", "inbound"],
                        "inboundIds": ["inboundIds", "inbound_ids"],
                    }
                    built = {}
                    for ours, names in aliases.items():
                        for n in names:
                            if n in props:
                                if ours == "inboundId":
                                    built[n] = inbound_id
                                elif ours == "inboundIds":
                                    built[n] = [inbound_id]
                                elif ours == "groupName":
                                    if group:
                                        built[n] = group
                                else:
                                    built[n] = base.get(ours)
                                break
                    # فیلدهای اجباری که نگاشت نداشتند
                    for req in (schema.get("required") or []):
                        if req not in built:
                            built[req] = base.get(req, "")
                    if built.get(
                            next((n for n in aliases["email"] if n in props), "email")):
                        shapes.append(built)

            # شکل رسمی نسخه‌ی ۳ — از مثالی که خود پنل در مشخصات
            # OpenAPI می‌دهد:
            #
            #   {"client": {...}, "inboundIds": [3, 5]}
            #
            # این یک درخواست هم کلاینت را می‌سازد و هم به اینباند
            # وصل می‌کند، پس مرحله‌ی attach جدا لازم ندارد.
            # شناسه‌ی uuid فرستاده نمی‌شود؛ پنل خودش می‌سازد.
            official = {
                "client": {
                    "email": email,
                    "totalGB": base.get("totalGB", 0),
                    "expiryTime": base.get("expiryTime", 0),
                    "tgId": int(tg_id or 0),
                    "limitIp": int(ip_limit or 0),
                    "limitHwid": 0,
                    "enable": True,
                },
                "inboundIds": self._target_inbounds(inbound_id, inbound_ids),
            }
            if group:
                official["client"]["groupName"] = group
            if base.get("subId"):
                official["client"]["subId"] = base["subId"]
            if eff_flow:
                official["client"]["flow"] = eff_flow

            shapes.insert(0, official)

            settings_str = json.dumps({"clients": [base]}, ensure_ascii=False)
            shapes += [
                {"client": base, "inboundIds": [int(inbound_id)]},
                {"id": inbound_id, "settings": settings_str},
                {"inboundId": inbound_id, "settings": settings_str},
                {"settings": settings_str},
            ]

            # اگر schema نبود یا ناقص بود، شکل‌های شناخته‌شده
            shapes += [
                base,
                {"clients": [base]},
                {"client": base},
                {"inboundId": inbound_id, **base},
                {"inboundIds": [inbound_id], **base},
            ]

            # ترتیب مهم است: مشخصات رسمی نسخه‌ی ۳ صریح می‌گوید
            # «Body is JSON»، پس اول JSON می‌فرستیم. form فقط برای
            # نسخه‌های قدیمی‌تر نگه داشته شده که مسیر addClient را
            # با data= می‌خواندند.
            last_err = None
            done = False

            for shape in shapes:
                if done:
                    break

                form = {}
                for k, v in shape.items():
                    if isinstance(v, (dict, list)):
                        form[k] = json.dumps(v, ensure_ascii=False)
                    elif isinstance(v, bool):
                        form[k] = "true" if v else "false"
                    elif v is not None:
                        form[k] = str(v)

                for kind, kwargs in (("json", {"json": shape}),
                                     ("form", {"data": form})):
                    try:
                        self._req("POST", create_path, **kwargs)
                        self._body_style = kind
                        self._used_shape_attaches = "inboundIds" in shape
                        last_err = None
                        done = True
                        break
                    except XUIError as e:
                        last_err = e
                        if "404" in str(e):
                            done = True
                            break

            if last_err is None:
                # وصل کردن به اینباند — بدون این، کلاینت ساخته
                # می‌شود ولی هیچ‌جا فعال نیست و مشتری چیزی نمی‌گیرد.
                #
                # نام مسیر و شکل بدنه بین نسخه‌ها فرق دارد، پس چند
                # ترکیب امتحان می‌شود تا یکی بگیرد.
                attach_tries = [
                    ("/panel/api/clients/bulkAttach",
                     {"emails": [email], "inboundIds": [inbound_id]}),
                    ("/panel/api/clients/attach",
                     {"email": email, "inboundIds": [inbound_id]}),
                    (f"/panel/api/clients/{email}/attach",
                     {"inboundIds": [inbound_id]}),
                    (f"/panel/api/clients/attach/{email}",
                     {"inboundIds": [inbound_id]}),
                    (f"/panel/api/clients/{email}/inbounds",
                     {"inboundIds": [inbound_id]}),
                ]
                # شکل رسمی خودش وصل می‌کند
                if self._body_style and self._used_shape_attaches:
                    self._path_cache["افزودن کلاینت"] = create_path
                    # پنل خودش uuid می‌سازد و ما آن را نفرستادیم، پس
                    # باید بخوانیمش. دو نکته که قبلاً اشتباه بود:
                    #
                    #   ۱. مسیر خواندن /panel/api/clients/get/{email} است،
                    #      نه /panel/api/clients/{email} — آن یکی اصلاً
                    #      وجود ندارد و بی‌صدا ۴۰۴ می‌داد.
                    #   ۲. در ClientRecord نسخه‌ی ۳، کلید id یک عددِ
                    #      ردیف دیتابیس است و uuid واقعی در کلید uuid
                    #      می‌آید. برداشتن id یعنی ذخیره‌ی یک عدد
                    #      به‌جای uuid.
                    #
                    # بدون این، هر تمدید یا غیرفعال‌کردن بعدی روی
                    # شناسه‌ی اشتباه می‌رود و «کلاینت پیدا نشد» می‌دهد.
                    made = self.find_client(inbound_id, email=email)
                    real = self._client_uuid(made)
                    if real:
                        client["id"] = real
                    else:
                        log.warning("uuid واقعی کلاینت %s از پنل خوانده نشد؛ "
                                    "عملیات بعدی با ایمیل انجام می‌شود", email)
                    return client

                attached = False
                for p, body in attach_tries:
                    if self.has_route(p, "POST") is False:
                        continue
                    form = {k: (json.dumps(v) if isinstance(v, (list, dict))
                                else str(v))
                            for k, v in body.items()}
                    for kwargs in ({"data": form}, {"json": body}):
                        try:
                            self._req("POST", p, **kwargs)
                            attached = True
                            break
                        except XUIError:
                            continue
                    if attached:
                        break

                if not attached:
                    # کلاینت ساخته شده ولی به جایی وصل نیست — این
                    # حالت بدتر از شکست کامل است چون بی‌صدا می‌ماند
                    raise XUIError(
                        f"کلاینت {email} ساخته شد ولی به اینباند {inbound_id} "
                        "وصل نشد. مسیر اتصال در این نسخه‌ی پنل شناخته نشد.")

                self._path_cache["افزودن کلاینت"] = create_path
                return client

        # ── نسخه‌های قدیمی‌تر ──
        self._try_paths([
            ("POST", "/panel/api/inbounds/addClient",
             {"data": {"id": inbound_id, "settings": settings}}),
            ("POST", "/panel/api/inbounds/addClient",
             {"json": {"id": inbound_id, "settings": settings}}),
            ("POST", "/panel/api/clients/add",
             {"json": {"inboundId": inbound_id, **client}}),
            ("POST", "/panel/api/clients",
             {"json": {"inboundId": inbound_id, **client}}),
            ("POST", f"/panel/api/inbounds/{inbound_id}/clients",
             {"json": client}),
        ], "افزودن کلاینت")
        return client

    # فیلدهایی که مسیر به‌روزرسانی نسخه‌ی ۳ می‌پذیرد. پنل ردیف را
    # *جایگزین* می‌کند نه patch، پس هر چیزی که نفرستیم پاک می‌شود —
    # برای همین از رکورد فعلی پرش می‌کنیم.
    _UPDATE_FIELDS = ("email", "totalGB", "expiryTime", "limitIp", "limitHwid",
                      "tgId", "enable", "subId", "flow", "group", "comment")

    def update_client(self, inbound_id, client_uuid=None, email=None, **changes):
        """
        به‌روزرسانی کلاینت.

        در نسخه‌ی ۳ مسیر درست POST /panel/api/clients/update/{email} است.
        مسیر قدیمی inbounds/updateClient اصلاً وجود ندارد — تا وقتی
        همان را صدا می‌زدیم، تمدید و مسدودکردن هیچ‌وقت کار نمی‌کرد.

        شناسه‌ی اصلی در این نسخه ایمیل است نه uuid، پس اگر ایمیل
        داشته باشیم مستقیم از آن استفاده می‌کنیم.
        """
        current = None
        if email:
            current = self.find_client(inbound_id, email=email)
        if current is None and client_uuid:
            current = self.find_client(inbound_id, client_uuid=client_uuid)
        if not current:
            raise XUIError("کلاینت پیدا نشد")

        client = dict(current)
        for k, v in changes.items():
            client[k] = v

        target = client.get("email") or email
        upd_path = f"/panel/api/clients/update/{target}"
        if target and self.has_route(upd_path, "POST") is not False:
            body = {k: client[k] for k in self._UPDATE_FIELDS if k in client}
            # پنل این‌ها را عدد می‌خواهد؛ رشته را رد می‌کند
            for k in ("totalGB", "expiryTime", "limitIp", "limitHwid", "tgId"):
                if k in body:
                    try:
                        body[k] = int(body[k] or 0)
                    except (TypeError, ValueError):
                        body[k] = 0
            if "enable" in body:
                body["enable"] = bool(body["enable"])
            self._req("POST", upd_path, json=body)
            self._path_cache["به‌روزرسانی کلاینت"] = upd_path
            return client

        # ── نسخه‌های قدیمی‌تر ──
        settings = json.dumps({"clients": [client]})
        uid = client_uuid or self._client_uuid(client)
        self._try_paths([
            ("POST", f"/panel/api/inbounds/updateClient/{uid}",
             {"data": {"id": inbound_id, "settings": settings}}),
            ("POST", f"/panel/api/inbounds/updateClient/{uid}",
             {"json": {"id": inbound_id, "settings": settings}}),
            ("POST", f"/panel/api/clients/{uid}",
             {"json": {"inboundId": inbound_id, **client}}),
            ("PUT", f"/panel/api/clients/{uid}",
             {"json": {"inboundId": inbound_id, **client}}),
        ], "به‌روزرسانی کلاینت")
        return client

    def find_client(self, inbound_id, email=None, client_uuid=None):
        """
        پیدا کردن کلاینت.

        در نسخه‌های جدید کلاینت‌ها ممکن است در JSON اینباند نباشند،
        پس اگر آنجا پیدا نشد از مسیر مستقل هم می‌پرسیم.
        """
        # در نسخه‌ی ۳ کلاینت‌ها مستقل‌اند و داخل JSON اینباند نیستند،
        # پس اول همان‌جا می‌پرسیم — سریع‌تر و درست‌تر است
        # مسیر خواندن از فهرست واقعی پنل — نه حدس
        def _unwrap(d):
            """
            پاسخ نسخه‌ی ۳ تودرتوست: داده‌های کلاینت داخل کلید
            client، و مصرف و اینباندها کنارش. صافش می‌کنیم تا
            بقیه‌ی کد مثل قبل با یک دیکشنری ساده کار کند.
            """
            if not isinstance(d, dict):
                return d
            inner = d.get("client")
            if not isinstance(inner, dict):
                return d
            flat = dict(inner)
            for k in ("inboundIds", "usedTraffic", "externalLinks",
                      "tunnelAllowedIPs", "up", "down", "total"):
                if k in d:
                    flat[k] = d[k]
            return flat

        if email:
            # مسیر واقعی نسخه‌ی ۳ اول می‌آید
            candidates = [
                f"/panel/api/clients/get/{email}",
                f"/panel/api/clients/{email}",
                f"/panel/api/clients/byEmail/{email}",
                f"/panel/api/clients/getClient/{email}",
            ]

            for p in candidates:
                if self.has_route(p, "GET") is False:
                    continue
                try:
                    found = self._req("GET", p)
                    if isinstance(found, dict) and found:
                        return _unwrap(found)
                    if isinstance(found, list) and found:
                        return _unwrap(found[0])
                except (XUIError, TypeError, ValueError):
                    continue

            # هیچ مسیر تکی جواب نداد — از فهرست کامل می‌گردیم.
            # کندتر است ولی وقتی نام مسیر عوض شده باشد تنها راه است.
            for p in ("/panel/api/clients/list", "/panel/api/clients",
                      "/panel/api/clients/all"):
                if self.has_route(p, "GET") is False:
                    continue
                try:
                    rows = self._req("GET", p)
                    if isinstance(rows, dict):
                        rows = (rows.get("clients") or rows.get("data")
                                or rows.get("items") or [])
                    if isinstance(rows, list):
                        for r in rows:
                            flat = _unwrap(r)
                            if isinstance(flat, dict) and flat.get("email") == email:
                                return flat
                except (XUIError, TypeError, ValueError):
                    continue

        # جست‌وجو با uuid.
        #
        # در نسخه‌ی ۳ کلاینت‌ها داخل JSON اینباند نیستند، پس حلقه‌ی
        # پایین (که settings اینباند را می‌خواند) همیشه خالی برمی‌گشت
        # و هر تمدید/غیرفعال‌کردنی «کلاینت پیدا نشد» می‌داد. اینجا از
        # فهرست واقعی کلاینت‌ها می‌گردیم.
        if client_uuid and not email:
            for p in ("/panel/api/clients/list", "/panel/api/clients"):
                if self.has_route(p, "GET") is False:
                    continue
                try:
                    rows = self._req("GET", p)
                    if isinstance(rows, dict):
                        rows = (rows.get("clients") or rows.get("data")
                                or rows.get("items") or [])
                    if isinstance(rows, list):
                        for r in rows:
                            flat = _unwrap(r)
                            if self._client_uuid(flat) == client_uuid:
                                return flat
                except (XUIError, TypeError, ValueError):
                    continue

        try:
            inb = self.inbound(inbound_id)
        except XUIError:
            inb = None
        if not inb:
            return None
        try:
            settings = json.loads(inb.get("settings") or "{}")
        except json.JSONDecodeError:
            return None
        for c in settings.get("clients", []):
            if email and c.get("email") == email:
                return c
            if client_uuid and c.get("id") == client_uuid:
                return c
        return None

    def delete_client(self, inbound_id, client_uuid, email=None):
        """
        حذف کلاینت.

        نسخه‌ی ۳ با ایمیل کار می‌کند نه uuid، و مسیرش بین نسخه‌ها
        فرق دارد — پس از فهرست واقعی مسیرهای پنل انتخاب می‌شود.
        """
        tries = []

        if email:
            tries += [
                ("POST", f"/panel/api/clients/del/{email}", {}),
                ("POST", f"/panel/api/clients/delete/{email}", {}),
                ("DELETE", f"/panel/api/clients/{email}", {}),
                ("POST", "/panel/api/clients/bulkDel",
                 {"json": {"emails": [email]}}),
            ]

        tries += [
            ("POST", f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}", {}),
            ("POST", f"/panel/api/clients/del/{client_uuid}", {}),
            ("DELETE", f"/panel/api/clients/{client_uuid}", {}),
        ]

        # فقط مسیرهایی که پنل واقعاً دارد
        known = [t for t in tries
                 if self.has_route(t[1], t[0]) is not False]
        return self._try_paths(known or tries, "حذف کلاینت")

    def client_traffic(self, email):
        """
        مصرف کلاینت بر اساس ایمیل.

        نسخه‌ی ۳ مسیر اختصاصی دارد؛ نسخه‌های قدیمی‌تر از inbounds
        می‌خوانند. هر کدام که پنل داشته باشد استفاده می‌شود.
        """
        for p in (f"/panel/api/clients/traffic/{email}",
                  f"/panel/api/inbounds/getClientTraffics/{email}"):
            if self.has_route(p, "GET") is False:
                continue
            try:
                r = self._req("GET", p)
                if r:
                    return r
            except XUIError:
                continue
        return None

    def all_client_traffic(self):
        """
        مصرف همه‌ی کلاینت‌ها با یک درخواست: {ایمیل: (up, down)}.

        برای کار ساعتی روی دویست کلاینت، دویست درخواست به پنل زدن
        هم کند است هم بی‌دلیل — لیست اینباندها همین را یک‌جا دارد
        (clientStats). اگر پنل آن را نداشت، {} برمی‌گردانیم و صداکننده
        به client_traffic تک‌به‌تک برمی‌گردد.
        """
        out = {}
        try:
            for ib in (self.inbounds() or []):
                for st in (ib.get("clientStats") or []):
                    em = st.get("email")
                    if em:
                        out[em] = (int(st.get("up") or 0),
                                   int(st.get("down") or 0))
        except (XUIError, AttributeError, TypeError, ValueError):
            return {}
        return out

    def reset_client_traffic(self, inbound_id, email):
        for method, p, body in (
            ("POST", f"/panel/api/clients/resetTraffic/{email}", {}),
            ("POST", "/panel/api/clients/bulkResetTraffic",
             {"json": {"emails": [email]}}),
            ("POST", f"/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}", {}),
        ):
            if self.has_route(p, method) is False:
                continue
            try:
                return self._req(method, p, **body)
            except XUIError:
                continue
        raise XUIError("مسیر ریست ترافیک در این نسخه‌ی پنل پیدا نشد")

    # ---------- عملیات سطح بالا ----------
    def panel_settings(self):
        """تنظیمات پنل — یک‌بار خوانده و کش می‌شود."""
        if self._settings is not None:
            return self._settings
        self._settings = {}
        if self.has_route("/panel/api/setting/all", "POST") is not False:
            try:
                got = self._req("POST", "/panel/api/setting/all")
                if isinstance(got, dict):
                    self._settings = got
            except XUIError as _exc:
                log.debug("x-ui probe (panel_settings): %s", _exc)
        return self._settings

    def panel_sub_base(self):
        """
        آدرس پایه‌ی اشتراک از دید خود پنل.

        وقتی مدیر دامنه‌ی سفارشی نداده، تنها راه ساختن یک لینک
        اشتراکِ درست همین است — سرویس subscription روی پورت و مسیر
        جدا از پنل اجرا می‌شود، پس آدرس پنل به‌تنهایی جواب نمی‌دهد.
        بدون این، مشتری هیچ لینکی نمی‌گرفت.
        """
        s = self.panel_settings()
        if not s or s.get("subEnable") is False:
            return None

        uri = str(s.get("subURI") or "").strip()
        if uri.startswith("http"):
            return uri.rstrip("/")

        host = str(s.get("subDomain") or "").strip()
        if not host:
            m = re.match(r"https?://([^:/]+)", self.base)
            host = m.group(1) if m else ""
        if not host:
            return None

        port = s.get("subPort")
        path = str(s.get("subPath") or "/sub/").strip()
        if not path.startswith("/"):
            path = "/" + path
        scheme = "https" if (s.get("subCertFile") or self.base.startswith("https")) else "http"

        netloc = host
        if port and int(port) not in (80, 443):
            netloc = f"{host}:{int(port)}"
        return f"{scheme}://{netloc}{path}".rstrip("/")

    def _target_inbounds(self, inbound_id, only=None):
        """
        اینباندهایی که کلاینت به آن‌ها وصل می‌شود.

        سه حالت:
          only داده شده  → همان فهرست، هر چه مدیر تعیین کرده
          all_inbounds   → همه‌ی اینباندهای فعال
          هیچ‌کدام       → فقط اینباند پیش‌فرض

        دادن چند اینباند یعنی اگر یکی از سرورها افتاد، مشتری
        همچنان کانفیگ کارآمد دارد.
        """
        if only:
            ids = []
            for x in only:
                try:
                    ids.append(int(x))
                except (TypeError, ValueError):
                    continue
            if ids:
                return ids

        if not self.all_inbounds:
            return [int(inbound_id)]

        try:
            ids = [int(i["id"]) for i in self.inbounds()
                   if i.get("enable", True)]
            return ids or [int(inbound_id)]
        except Exception:
            return [int(inbound_id)]

    @staticmethod
    def make_sub_id(email):
        """
        شناسه‌ی لینک اشتراک — با پیشوند برند، ولی غیرقابل‌حدس.

        قبلاً subId دقیقاً خود ایمیل بود: prefix_tgid_seq. یعنی آدرس
        اشتراک هر مشتری از روی شناسه‌ی تلگرامش ساختنی بود، و مسیر
        اشتراک در 3x-ui رمز نمی‌خواهد — همین‌طور که هیچ لینک اشتراکی
        نمی‌خواهد. امنیتش تماماً به حدس‌نزدنی‌بودن همان رشته است.

        خطر واقعی حدسِ هدف‌دار نیست، پویش است: کسی که یک کانفیگ خودش
        را دارد پیشوند و دامنه را می‌داند، و بعد کافی است بازه‌ای از
        شناسه‌های تلگرام را با seq کوچک امتحان کند تا اشتراک زنده‌ی
        بقیه را برداشت کند. خودِ 3x-ui به همین دلیل subId تصادفی
        می‌سازد؛ ما آن را با چیزی قابل‌شمارش عوض کرده بودیم.

        پیشوند می‌ماند چون ممکن است جایی مسیردهی روی آن بسته باشد؛
        برند صفحه‌ی اشتراک از *ایمیل* کلاینت خوانده می‌شود نه از این،
        پس تصادفی‌کردنش چیزی را خراب نمی‌کند.

        اشتراک‌های موجود دست نمی‌خورند: subId و لینکشان در دیتابیس
        ذخیره است و همان می‌ماند.
        """
        prefix = (str(email or "").split("_")[0] or "nx")[:12]
        return f"{prefix}_{secrets.token_hex(8)}"

    def create_subscription(self, inbound_id, email, gb, days, ip_limit=2,
                            tg_id=None, sub_base_url=None, inbound_ids=None,
                            group=None):
        """
        ساخت اشتراک کامل و برگرداندن اطلاعات لازم برای ارسال به مشتری.

        `group` برای فروشگاهِ نماینده است: کانفیگ در پنلِ مالک ساخته
        می‌شود و گروه تنها چیزی است که می‌گوید مالِ کیست.
        """
        sub_id = self.make_sub_id(email)
        client = self.add_client(inbound_id, email, gb=gb, days=days,
                                 ip_limit=ip_limit, tg_id=tg_id, sub_id=sub_id,
                                 inbound_ids=inbound_ids, group=group)

        sub_url = None
        configs = []

        # دامنه‌ی سفارشی مدیر بر لینک پنل اولویت دارد.
        #
        # اگر مدیر دامنه‌ی جدا برای اشتراک گذاشته — مثلاً یک دامنه‌ی
        # تمیز پشت کلادفلر — لینک باید همان باشد، نه آدرس پنل که
        # ممکن است پورت غیراستاندارد یا مسیر مخفی داشته باشد.
        if sub_base_url:
            sub_url = f"{sub_base_url.rstrip('/')}/{sub_id}"
        else:
            # مدیر دامنه نداده — از تنظیمات خود پنل می‌سازیم.
            # قبلاً اینجا خالی می‌ماند و مشتری هیچ لینکی نمی‌گرفت.
            try:
                pb = self.panel_sub_base()
            except Exception:
                pb = None
            if pb:
                sub_url = f"{pb}/{sub_id}"

        # کانفیگ‌های تکی را همیشه از پنل می‌گیریم، چون از پیکربندی
        # واقعی اینباند ساخته می‌شوند
        for p in (f"/panel/api/clients/links/{email}",
                  f"/panel/api/clients/subLinks/{sub_id}"):
            if self.has_route(p, "GET") is False:
                continue
            try:
                data = self._req("GET", p)
                if isinstance(data, dict):
                    # فقط اگر مدیر دامنه نداده باشد
                    if not sub_base_url:
                        sub_url = (data.get("subUrl") or data.get("subscriptionUrl")
                                   or data.get("url") or sub_url)
                    for key in ("links", "configs", "externalLinks", "items"):
                        v = data.get(key)
                        if isinstance(v, list):
                            configs += [x for x in v if isinstance(x, str)]
                elif isinstance(data, list):
                    configs += [x for x in data if isinstance(x, str)]
                if sub_url or configs:
                    break
            except XUIError:
                continue



        return {
            "email": email,
            "uuid": client["id"],
            "sub_id": sub_id,
            "sub_url": sub_url,
            "configs": configs,
            "expiry_ms": client["expiryTime"],
            "gb": gb,
        }

    def extend_subscription(self, inbound_id, client_uuid, add_days, add_gb=None,
                            reset_traffic=False, email=None):
        """
        تمدید: روز اضافه می‌شود. اگر اشتراک منقضی شده باشد، از امروز
        حساب می‌شود؛ وگرنه به تاریخ فعلی اضافه می‌شود.

        ایمیل شناسه‌ی مطمئن‌تری از uuid است — در نسخه‌ی ۳ کلید اصلی
        همان است — پس اگر داشته باشیم اول با آن می‌گردیم.
        """
        current = None
        if email:
            current = self.find_client(inbound_id, email=email)
        if current is None:
            current = self.find_client(inbound_id, client_uuid=client_uuid)
        if not current:
            raise XUIError("کلاینت پیدا نشد")

        now_ms = int(time.time() * 1000)
        cur_exp = int(current.get("expiryTime") or 0)
        base = cur_exp if cur_exp > now_ms else now_ms
        new_exp = base + add_days * 86400 * 1000 if add_days else cur_exp

        changes = {"expiryTime": new_exp, "enable": True}
        total_bytes = int(current.get("totalGB") or 0)
        if add_gb is not None:
            changes["totalGB"] = (total_bytes + int(add_gb * 1024 ** 3)
                                  if add_gb else 0)
            total_bytes = changes["totalGB"]

        self.update_client(inbound_id, client_uuid,
                           email=email or current.get("email"), **changes)

        if reset_traffic:
            try:
                self.reset_client_traffic(inbound_id, current.get("email"))
            except XUIError as _exc:
                log.debug("x-ui probe (extend_subscription): %s", _exc)

        # حجمِ نهایی را هم برمی‌گردانیم.
        #
        # تمدید حجم را *جمع* می‌کند و شمارنده‌ی مصرف را صفر نمی‌کند،
        # پس هر دو عدد روی هم می‌روند و با هم می‌خوانند. ولی ربات
        # حجمِ ذخیره‌شده‌اش را به‌روز نمی‌کرد و همان اندازه‌ی پلن
        # می‌ماند — یعنی مصرفِ تجمعی با سقفِ یک دوره سنجیده می‌شد.
        # صداکننده این عدد را می‌نویسد تا دو طرف یکی بمانند.
        return {"expiry_ms": new_exp, "total_bytes": total_bytes}

    def set_enabled(self, inbound_id, client_uuid, enabled: bool, email=None):
        return self.update_client(inbound_id, client_uuid, email=email,
                                  enable=bool(enabled))

    def detect_api(self):
        """
        تشخیص معماری پنل.

        از نسخه‌ی ۳.۴ به بعد، 3x-ui کلاینت‌ها را در جدول مستقل نگه می‌دارد
        و endpointهای تازه‌ای دارد (/panel/api/clients/*). نسخه‌های قدیمی‌تر
        کلاینت را داخل JSON هر inbound ذخیره می‌کنند.

        برمی‌گرداند: "modern" یا "legacy"
        نتیجه کش می‌شود تا هر بار درخواست اضافه نزنیم.
        """
        if getattr(self, "_api_mode", None):
            return self._api_mode

        self._api_mode = "legacy"
        try:
            if not self._logged_in:
                self.login()
            r = self.s.get(
                f"{self.base}/panel/api/clients/list/paged",
                params={"page": 1, "pageSize": 1},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code == 200:
                try:
                    body = r.json()
                    if isinstance(body, dict) and body.get("success") is not False:
                        self._api_mode = "modern"
                except ValueError as _exc:
                    log.debug("x-ui probe (detect_api): %s", _exc)
        except (requests.RequestException, XUIError) as _exc:
            log.debug("x-ui probe (detect_api): %s", _exc)

        return self._api_mode

    def ping(self):
        """تست اتصال — برای نمایش وضعیت در پنل."""
        try:
            self.login()
            inbs = self.inbounds()
            mode = self.detect_api()
            label = "معماری جدید (۳.۴+)" if mode == "modern" else "معماری کلاسیک"
            return True, f"اتصال برقرار است · {len(inbs)} inbound · {label}"
        except XUIError as e:
            return False, str(e)
        except requests.RequestException as e:
            return False, f"شبکه: {e}"
