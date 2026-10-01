"""
The management bot (docs/specs/2026-10-01-admin-bot-backup-ui.md, part B).

A second Telegram bot that belongs to the owner, not to his customers: status,
the one-file backup (now and on a schedule), today's sales, a config lookup,
restarts, the secret panel address, and the server/tunnel alerts that used to
land in the sales bot's group.

Why it runs in the panel process and not next to the sales bot: everything it
does already lives in the panel (the backup, the health checks, the 3x-ui
read, systemctl), so it calls those directly instead of keeping a second copy
of any of them. And it keeps answering while the sales bot is down, which is
exactly when "restart the sales bot" is needed.

This module holds the conversation only. What each button does is `api`,
supplied by the panel (`app._adminbot_api`), so the tests drive it with fakes.
"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("nexora.adminbot")

#: Telegram refuses documents over 50 MB from a bot.
TG_DOC_LIMIT = 50 * 1024 * 1024
BACKUP_EVERY_CHOICES = (0, 6, 12, 24)
DEFAULT_BACKUP_EVERY = 24


def settings(raw):
    """The saved settings (`data/adminbot.json`), with defaults. Never None.
    Its own file, not the panel config: the config is exported, kept in a
    history table and saved back whole by other pages, and none of those
    should carry or overwrite a bot token."""
    a = raw or {}
    admins = []
    for x in a.get("admins") or []:
        try:
            admins.append(int(str(x).strip()))
        except (TypeError, ValueError):
            continue
    every = a.get("backupEvery", DEFAULT_BACKUP_EVERY)
    try:
        every = int(every)
    except (TypeError, ValueError):
        every = DEFAULT_BACKUP_EVERY
    return {"token": (a.get("token") or "").strip(),
            "monitorToken": (a.get("monitorToken") or "").strip(),
            "admins": admins,
            "backupEvery": every if every in BACKUP_EVERY_CHOICES else DEFAULT_BACKUP_EVERY}


def _kb(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r] for r in rows]}


EVERY_FA = {0: "خاموش", 6: "هر ۶ ساعت", 12: "هر ۱۲ ساعت", 24: "روزی یک‌بار"}


def menu_kb():
    return _kb([
        [("📊 وضعیت", "st"), ("💾 پشتیبان", "bk")],
        [("💰 فروش امروز", "sl"), ("🔎 جست‌وجوی کانفیگ", "q")],
        [("⏱ پشتیبانِ خودکار", "ab"), ("🔗 نشانیِ پنل", "url")],
        [("🔄 ری‌استارت", "rs")],
    ])


def back_kb():
    return _kb([[("‹ منو", "m")]])


MENU_TEXT = "🛠 <b>ربات مدیریت نکسورا</b>\n\nچه کاری انجام بدهم؟"


def send_backup(bot, chat_id, api, why=""):
    """Build the zip and send it; too big for Telegram → say where it is."""
    try:
        path = Path(api.backup())
    except Exception as e:
        log.warning("admin bot: backup failed: %s", e)
        bot.send(chat_id, f"❌ ساختِ پشتیبان ناموفق بود: <code>{type(e).__name__}</code>", back_kb())
        return False
    size = path.stat().st_size
    if size > TG_DOC_LIMIT:
        bot.send(chat_id, f"💾 پشتیبان ساخته شد ولی {size // (1024 * 1024)} مگابایت است و تلگرام "
                          f"بیشتر از ۵۰ مگابایت نمی‌پذیرد.\nروی سرور: <code>{path}</code>\n"
                          "یا از پنل: تنظیمات ← پنل، رمز و پشتیبان.", back_kb())
        return True
    cap = (f"💾 <b>پشتیبانِ کاملِ پنل</b>{why}\n{datetime.now():%Y-%m-%d %H:%M}\n"
           "توکن‌های ربات داخلش است؛ جایی امن نگهش دارید.\n"
           "بازیابی: پنل ← تنظیمات ← «بازیابی از فایل»، یا <code>nexora restore</code>.")
    bot.send_doc(chat_id, str(path), caption=cap)
    return True


def handle(cfg, bot, api, update, state):
    """
    One update. `state` is a dict kept by the loop (who is typing a search).
    Only ids in `admins`, only in private chats; anyone else gets no answer at
    all, so the bot does not even confirm it exists.
    """
    s = settings(cfg)
    msg = update.get("message")
    cb = update.get("callback_query")
    src = msg or (cb or {}).get("message") or {}
    chat = src.get("chat") or {}
    who = ((msg or cb or {}).get("from") or {}).get("id")
    if chat.get("type") != "private" or who not in s["admins"]:
        if who is not None:
            log.info("admin bot: ignored update from %s", who)
        return
    cid = chat["id"]

    if msg is not None:
        text = (msg.get("text") or "").strip()
        if state.get(cid) == "search" and text and not text.startswith("/"):
            state.pop(cid, None)
            bot.send(cid, api.search(text), back_kb())
            return
        state.pop(cid, None)
        bot.send(cid, MENU_TEXT, menu_kb())
        return

    data = cb.get("data") or ""
    mid = src.get("message_id")
    bot.answer_cb(cb.get("id"))

    def show(text, kb=None):
        try:
            bot.edit(cid, mid, text, kb or back_kb())
        except Exception:
            bot.send(cid, text, kb or back_kb())

    if data == "m":
        state.pop(cid, None)
        show(MENU_TEXT, menu_kb())
    elif data == "st":
        show(api.status())
    elif data == "bk":
        show("⏳ در حالِ ساختِ پشتیبان…")
        send_backup(bot, cid, api)
    elif data == "sl":
        show(api.sales())
    elif data == "q":
        state[cid] = "search"
        show("🔎 نام یا ایمیلِ کانفیگ (یا بخشی از آن) را بفرستید.")
    elif data == "url":
        u = api.admin_url()
        show(f"🔗 نشانیِ پنلِ مدیریت:\n<code>{u}</code>\n\nاین نشانی را به کسی ندهید."
             if u else "نشانیِ پنل هنوز معلوم نیست؛ روی سرور: <code>nexora url</code>")
    elif data == "ab":
        rows = [[((("✅ " if s["backupEvery"] == h else "") + EVERY_FA[h]), f"ab:{h}")]
                for h in BACKUP_EVERY_CHOICES]
        show("⏱ <b>پشتیبانِ خودکار</b>\nفایلِ کامل همین‌جا برایتان فرستاده می‌شود.",
             _kb(rows + [[("‹ منو", "m")]]))
    elif data.startswith("ab:"):
        try:
            h = int(data[3:])
        except ValueError:
            h = -1
        if h in BACKUP_EVERY_CHOICES:
            api.set_backup_every(h)
            show(f"⏱ پشتیبانِ خودکار: <b>{EVERY_FA[h]}</b>")
    elif data == "rs":
        show("🔄 کدام را دوباره راه بیندازم؟",
             _kb([[("🤖 ربات فروش", "rs:bot"), ("🖥 پنل", "rs:panel")], [("‹ منو", "m")]]))
    elif data in ("rs:bot", "rs:panel"):
        name = "ربات فروش" if data == "rs:bot" else "پنل"
        show(f"مطمئنید {name} دوباره راه‌اندازی شود؟",
             _kb([[("بله، ری‌استارت", "rsy:" + data[3:]), ("نه", "m")]]))
    elif data in ("rsy:bot", "rsy:panel"):
        what = data[4:]
        if what == "panel":
            # The panel is this process: say it first, the restart cuts us off.
            show("🔄 پنل دوباره راه‌اندازی می‌شود؛ حدودِ ۱۰ ثانیه.")
        ok, why = api.restart(what)
        if what == "bot":
            show("✅ ربات فروش دوباره راه افتاد." if ok else f"❌ ری‌استارت نشد: {why}")
        elif not ok:
            bot.send(cid, f"❌ ری‌استارتِ پنل نشد: {why}", back_kb())


def backup_due(every_hours, last_iso, now=None):
    """Is a scheduled backup due? `last_iso` is when the last one was sent."""
    if not every_hours:
        return False
    now = now or datetime.now()
    if not last_iso:
        return True
    try:
        last = datetime.fromisoformat(str(last_iso)[:19])
    except ValueError:
        return True
    return now - last >= timedelta(hours=every_hours)


FILE = "adminbot.json"
_LOCK = threading.Lock()


def load(data_dir):
    try:
        d = json.loads((Path(data_dir) / FILE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def update(data_dir, **changes):
    """Read, change, write, under one lock: the panel's Save and the
    scheduler's "last backup" stamp must not overwrite each other."""
    with _LOCK:
        d = load(data_dir)
        d.update(changes)
        p = Path(data_dir) / FILE
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
        return d


def scheduled_backup(raw, bot, api, data_dir, now=None):
    """Send the scheduled backup to every admin when due. Returns True if sent."""
    s = settings(raw)
    if not s["token"] or not s["admins"] or not backup_due(s["backupEvery"], raw.get("lastBackup"), now):
        return False
    sent = False
    for cid in s["admins"]:
        try:
            sent = send_backup(bot, cid, api, why=" (خودکار)") or sent
        except Exception as e:
            log.warning("admin bot: scheduled backup to %s failed: %s", cid, e)
    if sent:
        update(data_dir, lastBackup=(now or datetime.now()).isoformat(timespec="seconds"))
    return sent


def loop(make_bot, api, data_dir, stop):
    """
    Long-poll while a token is set; check the backup schedule between polls.
    `stop` is a threading.Event. Network errors back off; a bad token is said
    once in the log and waited out (the owner fixes it in Settings).
    """
    offset, bot, tok, backoff, state = None, None, None, 1, {}
    last_sched = 0.0
    while not stop.is_set():
        cfg = load(data_dir)
        s = settings(cfg)
        if not s["token"]:
            bot, tok = None, None
            stop.wait(30)
            continue
        if s["token"] != tok:
            bot, tok, offset = make_bot(s["token"]), s["token"], None
        try:
            if time.time() - last_sched > 300:
                last_sched = time.time()
                scheduled_backup(cfg, bot, api, data_dir)
            for up in bot.updates(offset=offset, timeout=25) or []:
                offset = up["update_id"] + 1
                try:
                    handle(cfg, bot, api, up, state)
                except Exception:
                    log.exception("admin bot: update %s failed", up.get("update_id"))
            backoff = 1
        except Exception as e:
            log.warning("admin bot: %s", str(e)[:200])
            stop.wait(min(backoff, 120))
            backoff = min(backoff * 2, 120)


# ── The tunnel bot (docs/specs/2026-10-01-bots-and-tunnel-mesh.md) ──────────
# Its own token (`monitorToken`), the same admin ids. In 2.1.0 it was only a
# token that alerts could use; the owner asked twice for a bot of its own for
# tunnels, with something to press.

TUNNEL_MENU_TEXT = "📡 <b>ربات تانل نکسورا</b>\n\nتانل‌ها و سرورهای شما. چه چیزی را ببینم؟"


def tunnel_menu_kb():
    return _kb([
        [("📡 تانل‌ها", "tn"), ("🩺 عیب‌یابی", "dg")],
        [("🖥 سرورها", "sv"), ("🔄 بررسیِ دوباره", "rc")],
    ])


def tunnel_back_kb():
    return _kb([[("‹ منو", "tm")]])


def handle_tunnel(cfg, bot, api, update, state):
    """One update for the tunnel bot: admins only, private chats only."""
    s = settings(cfg)
    msg = update.get("message")
    cb = update.get("callback_query")
    src = msg or (cb or {}).get("message") or {}
    chat = src.get("chat") or {}
    who = ((msg or cb or {}).get("from") or {}).get("id")
    if chat.get("type") != "private" or who not in s["admins"]:
        if who is not None:
            log.info("tunnel bot: ignored update from %s", who)
        return
    cid = chat["id"]
    if msg is not None:
        bot.send(cid, TUNNEL_MENU_TEXT, tunnel_menu_kb())
        return
    data = cb.get("data") or ""
    mid = src.get("message_id")
    bot.answer_cb(cb.get("id"))

    def show(text, kb=None):
        try:
            bot.edit(cid, mid, text, kb or tunnel_back_kb())
        except Exception:
            bot.send(cid, text, kb or tunnel_back_kb())

    if data == "tm":
        show(TUNNEL_MENU_TEXT, tunnel_menu_kb())
    elif data == "tn":
        show(api.tunnels())
    elif data == "dg":
        show(api.diagnosis())
    elif data == "sv":
        show(api.servers())
    elif data == "rc":
        show(api.recheck())


def _poll(key, handler, make_bot, api, data_dir, stop, on_tick=None):
    """Long-poll the bot whose token is settings()[key] while one is set."""
    offset, bot, tok, backoff, state = None, None, None, 1, {}
    last_tick = 0.0
    while not stop.is_set():
        cfg = load(data_dir)
        token = settings(cfg)[key]
        if not token:
            bot, tok = None, None
            stop.wait(30)
            continue
        if token != tok:
            bot, tok, offset = make_bot(token), token, None
        try:
            if on_tick and time.time() - last_tick > 300:
                last_tick = time.time()
                on_tick(cfg, bot)
            for up in bot.updates(offset=offset, timeout=25) or []:
                offset = up["update_id"] + 1
                try:
                    handler(cfg, bot, api, up, state)
                except Exception:
                    log.exception("%s bot: update %s failed", key, up.get("update_id"))
            backoff = 1
        except Exception as e:
            log.warning("%s bot: %s", key, str(e)[:200])
            stop.wait(min(backoff, 120))
            backoff = min(backoff * 2, 120)


def loop_tunnel(make_bot, api, data_dir, stop):
    _poll("monitorToken", handle_tunnel, make_bot, api, data_dir, stop)


def level_changes(prev, now_levels):
    """
    Which servers' diagnosis changed enough to tell the owner: a change of
    level, or the first look at a server that is not ok. Unknown is never
    reported (no data yet is not a fault). Returns [(id, old, new)].
    """
    out = []
    for nid, lvl in now_levels.items():
        if lvl == "unknown":
            continue
        old = prev.get(nid)
        if old == lvl:
            continue
        if old is None and lvl == "ok":
            continue
        out.append((nid, old, lvl))
    return out
