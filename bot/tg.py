"""
کلاینت سبک Telegram Bot API.

عمداً از فریم‌ورک استفاده نشده تا وابستگی اضافه نصب نشود و
رفتار کاملاً قابل پیش‌بینی بماند. فقط requests لازم است.
"""

import json
import time
import logging

import requests

log = logging.getLogger("nexora.tg")

#: چند بار حاضریم برای محدودیت نرخ صبر کنیم.
#
#  سخاوتمندتر از تلاش شبکه، چون ۴۲۹ خرابی نیست: تلگرام دارد
#  می‌گوید کی دوباره بیا. ولی بی‌نهایت هم نه — یک ربات که تا ابد
#  صبر کند، بقیه‌ی صف را هم نگه می‌دارد.
NET_RATE_LIMIT_TRIES = 6

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    def __init__(self, description, code=None):
        super().__init__(description)
        self.description = description
        self.code = code


class Bot:
    """
    کلاینت Bot API تلگرام.

    دو تایم‌اوت جدا دارد و این عمدی است:

      timeout      برای فراخوانی‌های عادی (ارسال پیام، ویرایش، حذف)
      poll_timeout برای getUpdates که long-polling است و *باید* منتظر بماند

    قبلاً هر دو یکی بودند (۲۵ ثانیه). یعنی یک sendMessage که روی شبکه‌ی
    کند گیر می‌کرد، تا ۲۵ ثانیه کل حلقه‌ی ربات را نگه می‌داشت و در آن
    مدت هیچ پیام دیگری پردازش نمی‌شد. با اتصال ایران به تلگرام این
    اتفاق کم نیست.
    """

    def __init__(self, token: str, timeout: int = 10, poll_timeout: int = 25):
        self.token = token
        self.timeout = timeout
        self.poll_timeout = poll_timeout
        self._session = requests.Session()
        # نگه‌داشتن اتصال باز: هر فراخوانی جدید دست‌دادن TLS دوباره
        # انجام نمی‌دهد. روی مسیر پرتأخیر، همین بیشترین صرفه‌جویی است.
        try:
            ad = requests.adapters.HTTPAdapter(pool_connections=4,
                                               pool_maxsize=8, max_retries=0)
            self._session.mount("https://", ad)
        except Exception as _exc:
            # فقط کارایی است، نه درستی — ولی بی‌صدا نه
            log.debug("http adapter tuning: %s", _exc)

    # ---------- هسته ----------
    def call(self, method: str, **params):
        """
        فراخوانی متد. خطاهای موقت شبکه سه بار تلاش مجدد می‌شوند،
        ولی خطاهای منطقی تلگرام (مثل chat not found) بلافاصله بالا می‌روند.
        """
        files = params.pop("_files", None)
        payload = {
            k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in params.items() if v is not None
        }

        # getUpdates باید تا سقف long-poll منتظر بماند؛ بقیه نه.
        # به تایم‌اوت شبکه چند ثانیه اضافه می‌کنیم تا خودِ درخواست
        # زودتر از سروری که عمداً نگهش داشته قطع نشود.
        if method == "getUpdates":
            net_timeout = int(params.get("timeout") or self.poll_timeout) + 5
        else:
            net_timeout = self.timeout

        # خطای شبکه و محدودیت نرخ دو چیز متفاوت‌اند و سهمیه‌شان هم
        # باید جدا باشد. خطای شبکه یعنی چیزی خراب است؛ ۴۲۹ یعنی
        # تلگرام صریح می‌گوید چند ثانیه صبر کن و دوباره بفرست.
        #
        # قبلاً هر دو از یک سهمیه‌ی سه‌تایی می‌خوردند، پس سه بار ۴۲۹
        # پشت هم — که در ارسال همگانی کاملاً عادی است — پیام را
        # می‌انداخت.
        last_err = None
        net_tries = rate_waits = 0
        while net_tries < 3 and rate_waits < NET_RATE_LIMIT_TRIES:
            attempt = net_tries
            try:
                r = self._session.post(
                    API.format(token=self.token, method=method),
                    data={k: v for k, v in payload.items() if k != "_nostyle"},
                    files=files, timeout=net_timeout
                )
                data = r.json()
                if data.get("ok"):
                    return data.get("result")

                desc = data.get("description", "خطای نامشخص")
                code = data.get("error_code")

                # رنگِ دکمه ویژگیِ تازه‌ی تلگرام است. اگر سرورِ تلگرام آن را
                # نپذیرد، یک فیلدِ ناشناخته کلِ پیام — یعنی کلِ منو — را از
                # کار می‌اندازد. پس یک‌بار بی‌رنگ دوباره می‌فرستیم: منوی
                # بی‌رنگ خیلی بهتر از منویی است که هرگز نمی‌رسد.
                if (code == 400 and '"style"' in str(payload.get("reply_markup") or "")
                        and not payload.get("_nostyle")):
                    log.warning("رنگِ دکمه پذیرفته نشد (%s) — بی‌رنگ فرستاده شد", desc)
                    rm = json.loads(payload["reply_markup"])
                    for row in rm.get("inline_keyboard") or []:
                        for b in row:
                            b.pop("style", None)
                    payload["reply_markup"] = json.dumps(rm, ensure_ascii=False)
                    payload["_nostyle"] = "1"
                    continue

                # محدودیت نرخ — صبر و تلاش مجدد
                if code == 429:
                    wait = (data.get("parameters") or {}).get("retry_after", 3)
                    rate_waits += 1
                    time.sleep(min(wait, 30))
                    continue

                raise TelegramError(desc, code)

            except requests.RequestException as e:
                last_err = e
                net_tries += 1
                time.sleep(1.5 * (attempt + 1))

        # پیام خطا باید بگوید واقعاً چه شد. قبلاً حتی وقتی علت
        # محدودیت نرخ بود، «شبکه در دسترس نبود: None» می‌داد — و مدیری
        # که پیام همگانی فرستاده بود دنبال مشکل شبکه می‌گشت.
        if rate_waits and not last_err:
            raise TelegramError(
                f"تلگرام محدودیت نرخ گذاشت — بعد از {rate_waits} بار صبر هم "
                "اجازه نداد. آهسته‌تر بفرستید.", 429)
        raise TelegramError(f"شبکه در دسترس نبود: {last_err}")

    # ---------- پیام ----------
    @staticmethod
    def _safe_html(text):
        """
        اگر ساختار HTML پیام خراب باشد، تلگرام کل پیام را رد می‌کند و
        کاربر هیچ چیزی نمی‌بیند. به‌جای آن، این‌جا خطا لاگ می‌شود و
        پیام بدون قالب‌بندی می‌رود — زشت‌تر، ولی رسیده.
        """
        try:
            from fmt import check, plain
        except ImportError:
            return text
        bad = check(text)
        if not bad:
            return text
        log.error("HTML پیام معیوب بود، بدون قالب فرستاده شد: %s", "; ".join(bad[:3]))
        return plain(text)

    def send(self, chat_id, text, keyboard=None, parse_mode="HTML",
             preview=False, reply_to=None, topic_id=None):
        if parse_mode == "HTML":
            text = self._safe_html(text)
        return self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=keyboard,
            link_preview_options={"is_disabled": not preview},
            reply_to_message_id=reply_to,
            message_thread_id=topic_id,
        )

    def edit(self, chat_id, message_id, text, keyboard=None, parse_mode="HTML"):
        if parse_mode == "HTML":
            text = self._safe_html(text)
        try:
            return self.call(
                "editMessageText",
                chat_id=chat_id, message_id=message_id, text=text,
                parse_mode=parse_mode, reply_markup=keyboard,
                link_preview_options={"is_disabled": True},
            )
        except TelegramError as e:
            # ویرایش به همان محتوا خطا می‌دهد — بی‌ضرر است
            if "not modified" in e.description.lower():
                return None
            raise

    def edit_markup(self, chat_id, message_id, keyboard=None):
        try:
            return self.call("editMessageReplyMarkup", chat_id=chat_id,
                             message_id=message_id, reply_markup=keyboard)
        except TelegramError as e:
            if "not modified" in e.description.lower():
                return None
            raise

    def delete(self, chat_id, message_id):
        try:
            return self.call("deleteMessage", chat_id=chat_id, message_id=message_id)
        except TelegramError:
            return None

    def answer_cb(self, cb_id, text=None, alert=False):
        try:
            return self.call("answerCallbackQuery", callback_query_id=cb_id,
                             text=text, show_alert=alert)
        except TelegramError:
            return None

    def send_photo(self, chat_id, photo, caption=None, keyboard=None, topic_id=None):
        return self.call("sendPhoto", chat_id=chat_id, photo=photo,
                         caption=caption, parse_mode="HTML",
                         reply_markup=keyboard, message_thread_id=topic_id)

    def send_photo_bytes(self, chat_id, data, filename="qr.png", caption=None,
                         keyboard=None, topic_id=None):
        """
        ارسال تصویری که همین‌جا ساخته شده — مثل کیوآر لینک اشتراک.

        فایل مستقیم آپلود می‌شود و هیچ‌جای بیرون نمی‌رود؛ لینک اشتراک
        رمز مشتری است و نباید به سرویس کیوآرساز شخص ثالث برود.
        """
        # بایت خام می‌فرستیم نه BytesIO: اگر تلاش مجدد لازم شود،
        # جریانِ یک‌بار خوانده‌شده خالی است ولی بایت‌ها دوباره خوانده
        # می‌شوند.
        # نوعِ محتوا از خودِ بایت‌ها، نه از پسوندِ نامِ فایل: عکسِ
        # گفتگو ممکن است JPEG یا WebP باشد و اعلامِ image/png برای
        # آن، تلگرام را به رد یا فشرده‌سازیِ بد می‌رساند.
        ctype = ("image/png" if data[:8] == b"\x89PNG\r\n\x1a\n"
                 else "image/webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP"
                 else "image/jpeg")
        return self.call("sendPhoto", chat_id=chat_id, caption=caption,
                         parse_mode="HTML", reply_markup=keyboard,
                         message_thread_id=topic_id,
                         _files={"photo": (filename, bytes(data), ctype)})

    def action(self, chat_id, kind="typing"):
        """
        نشان‌دادن «در حال تایپ».

        ساخت کانفیگ چند ثانیه طول می‌کشد و در آن مدت مشتری فقط یک
        صفحه‌ی ساکت می‌بیند و فکر می‌کند ربات گیر کرده. این حالت
        خودش بعد از ۵ ثانیه پاک می‌شود، پس نیازی به لغو ندارد.
        """
        try:
            return self.call("sendChatAction", chat_id=chat_id, action=kind)
        except TelegramError:
            return None

    def send_doc(self, chat_id, path, caption=None, topic_id=None):
        with open(path, "rb") as f:
            return self.call("sendDocument", chat_id=chat_id, caption=caption,
                             parse_mode="HTML", message_thread_id=topic_id,
                             _files={"document": f})

    def copy(self, chat_id, from_chat_id, message_id, caption=None,
             keyboard=None, topic_id=None):
        return self.call("copyMessage", chat_id=chat_id, from_chat_id=from_chat_id,
                         message_id=message_id, caption=caption, parse_mode="HTML",
                         reply_markup=keyboard, message_thread_id=topic_id)

    # ---------- گروه و تاپیک ----------
    def create_topic(self, chat_id, name, icon_color=None):
        return self.call("createForumTopic", chat_id=chat_id, name=name,
                         icon_color=icon_color)

    def get_chat(self, chat_id):
        return self.call("getChat", chat_id=chat_id)

    def member_status(self, chat_id, user_id):
        """وضعیت عضویت کاربر در کانال — برای عضویت اجباری."""
        try:
            m = self.call("getChatMember", chat_id=chat_id, user_id=user_id)
            return (m or {}).get("status")
        except TelegramError:
            return None

    # ---------- دریافت به‌روزرسانی ----------
    def me(self):
        return self.call("getMe")

    def updates(self, offset=None, timeout=25):
        return self.call("getUpdates", offset=offset, timeout=timeout,
                         allowed_updates=["message", "callback_query",
                                          "my_chat_member"]) or []

    def drop_webhook(self):
        try:
            return self.call("deleteWebhook", drop_pending_updates=False)
        except TelegramError:
            return None


# ---------- کمکی‌های صفحه‌کلید ----------

def contact_kb(button_text="ارسال شماره من", skip_text=None):
    """
    کیبورد پایین صفحه با دکمه‌ی درخواست شماره.

    تلگرام فقط از طریق ReplyKeyboard با request_contact شماره می‌دهد —
    دکمه‌های شیشه‌ای این قابلیت را ندارند.
    """
    rows = [[{"text": button_text, "request_contact": True}]]
    if skip_text:
        rows.append([{"text": skip_text}])
    return {
        "keyboard": rows,
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def remove_kb():
    """برداشتن کیبورد پایین صفحه."""
    return {"remove_keyboard": True}


#: تنها اسکیم‌هایی که تلگرام در دکمه‌ی شیشه‌ای می‌پذیرد.
#
# اسکیم اپلیکیشن‌ها (happ://، v2rayng://، v2box://) را رد می‌کند و
# خطای BUTTON_URL_INVALID می‌دهد — و این خطا *کل پیام* را از بین
# می‌برد، نه فقط آن دکمه را. یعنی کانفیگ ساخته می‌شد ولی هیچ‌وقت
# به دست مشتری نمی‌رسید.
_OK_SCHEMES = ("http://", "https://", "tg://")


def valid_button_url(url):
    """آیا تلگرام این آدرس را در دکمه می‌پذیرد؟"""
    return isinstance(url, str) and url.lower().startswith(_OK_SCHEMES)


def kb(rows):
    """
    صفحه‌کلید شیشه‌ای. هر ردیف لیستی از (متن، داده) یا (متن، داده, 'url').

    دکمه‌ی url با اسکیم غیرمجاز حذف می‌شود — یک دکمه‌ی نمایش‌داده‌نشده
    خیلی بهتر از پیامی است که اصلاً ارسال نمی‌شود.
    """
    out = []
    for row in rows:
        line = []
        for item in row:
            if item is None:
                continue
            text, data = item[0], item[1]
            kind = item[2] if len(item) > 2 else None
            if kind == "url":
                if not valid_button_url(data):
                    continue
                line.append({"text": text, "url": data})
            elif kind == "web_app":
                # مینی‌اپ. تلگرام فقط https را باز می‌کند و با هر چیز
                # دیگری خودِ *پیام* را رد می‌کند — یعنی یک آدرس غلط
                # کل منو را از کار می‌اندازد، نه فقط یک دکمه را. پس
                # مثل url، دکمه‌ی نامعتبر حذف می‌شود نه فرستاده.
                if not data or not str(data).lower().startswith("https://"):
                    continue
                btn = {"text": text, "web_app": {"url": str(data)}}
                # Colour too: the mini app button is the one the owner wants
                # every buyer to notice (task 6).
                if len(item) > 3 and item[3] in ("success", "primary", "danger"):
                    btn["style"] = item[3]
                line.append(btn)
            elif kind == "copy":
                # دکمه‌ی کپی تلگرام: با یک ضربه متن در کلیپ‌بورد
                # می‌نشیند. برای لینک اشتراک بهترین حالت است — کاربر
                # لازم نیست متن را انتخاب کند و اشتباه ببرد.
                if not data:
                    continue
                line.append({"text": text, "copy_text": {"text": str(data)[:256]}})
            else:
                btn = {"text": text, "callback_data": data}
                # رنگِ دکمه (Bot API 9.4: success سبز، primary آبی، danger قرمز).
                # فقط برای دکمه‌ای که باید دیده شود — مثلِ «تست رایگان».
                style = item[3] if len(item) > 3 else None
                if style in ("success", "primary", "danger"):
                    btn["style"] = style
                line.append(btn)
        if line:
            out.append(line)
    return {"inline_keyboard": out}


def esc(s):
    """امن‌سازی متن برای parse_mode=HTML."""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
