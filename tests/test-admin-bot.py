#!/usr/bin/env python3
"""
The management bot (docs/specs/2026-10-01-admin-bot-backup-ui.md, part B).

What must hold: a stranger, or the owner in a group, gets no answer at all;
every button does what it says through the panel's own functions; the
scheduled backup goes out once per interval and is stamped; server alerts go
to the management bot when one is set and still reach the sales bot's group
when not (or when Telegram refuses); a sales bot's token is refused.

Run: python tests/test-admin-bot.py
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="adminbot_")
DATA = Path(TMP)
os.environ.update(
    BOT_DB_PATH=str(DATA / "bot.db"), BILLING_DB_PATH=str(DATA / "billing.db"),
    NEXORA_ADMIN_PASSWORD="testpw", CONFIG_PATH=str(DATA / "config.json"),
    ADMIN_PATH_FILE=str(DATA / "admin_path.json"), NEXORA_NO_ADMIN_BOT="1")
os.environ.pop("NEXORA_ADMIN_PATH", None)
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "bot"), str(ROOT / "backend")]

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


import adminbot as A                                       # noqa: E402

OWNER, STRANGER = 900, 555


class FakeBot:
    def __init__(self, token="T"):
        self.token, self.out = token, []

    def send(self, chat_id, text, keyboard=None, **k):
        self.out.append(("send", chat_id, text, keyboard))
        return {"message_id": 1}

    def edit(self, chat_id, mid, text, keyboard=None, **k):
        self.out.append(("edit", chat_id, text, keyboard))

    def answer_cb(self, *a, **k):
        pass

    def send_doc(self, chat_id, path, caption=None, **k):
        self.out.append(("doc", chat_id, path, caption))


ZIP = DATA / "nexora-backup-test.zip"
ZIP.write_bytes(b"PK" + b"0" * 100)


class FakeApi:
    def __init__(self):
        self.calls = []

    def status(self):
        self.calls.append("status"); return "STATUS"

    def backup(self):
        self.calls.append("backup"); return ZIP

    def sales(self):
        self.calls.append("sales"); return "SALES"

    def search(self, q):
        self.calls.append(("search", q)); return f"FOUND {q}"

    def restart(self, what):
        self.calls.append(("restart", what)); return True, ""

    def admin_url(self):
        return "https://panel.test/abc/"

    def set_backup_every(self, h):
        self.calls.append(("every", h))


CFG = {"token": "123:ADMIN", "admins": [OWNER], "backupEvery": 24}


def msg(text, frm=OWNER, chat_type="private"):
    return {"update_id": 1, "message": {"text": text, "from": {"id": frm},
                                        "chat": {"id": frm if chat_type == "private" else -100, "type": chat_type}}}


def cb(data, frm=OWNER):
    return {"update_id": 2, "callback_query": {"id": "c", "data": data, "from": {"id": frm},
                                               "message": {"message_id": 5, "chat": {"id": frm, "type": "private"}}}}


# ═══════════════════════════════════════════════════════════
head("Who it answers")
# ═══════════════════════════════════════════════════════════
b, api, st = FakeBot(), FakeApi(), {}
A.handle(CFG, b, api, msg("/start", frm=STRANGER), st)
A.handle(CFG, b, api, cb("bk", frm=STRANGER), st)
check("a stranger gets no answer at all, not even 'no access'", not b.out and not api.calls, b.out)
A.handle(CFG, b, api, msg("/start", chat_type="group"), st)
check("the owner in a group gets nothing either (the backup must not land in a group)", not b.out)
A.handle(CFG, b, api, msg("/start"), st)
check("the owner in private: the menu", b.out and b.out[-1][0] == "send"
      and "ربات مدیریت" in b.out[-1][2], b.out[-1:])
_btns = [x["callback_data"] for r in b.out[-1][3]["inline_keyboard"] for x in r]
check("every button in the menu is handled", set(_btns) == {"st", "bk", "sl", "q", "ab", "url", "rs"}, _btns)

# ═══════════════════════════════════════════════════════════
head("Buttons")
# ═══════════════════════════════════════════════════════════
b.out.clear()
A.handle(CFG, b, api, cb("st"), st)
check("status: the panel's own status text", b.out[-1][2] == "STATUS")
A.handle(CFG, b, api, cb("bk"), st)
check("backup: built and sent as a document to the owner's private chat",
      b.out[-1][0] == "doc" and b.out[-1][1] == OWNER and b.out[-1][2] == str(ZIP), b.out[-1])
A.handle(CFG, b, api, cb("sl"), st)
check("sales of today", b.out[-1][2] == "SALES")
A.handle(CFG, b, api, cb("q"), st)
A.handle(CFG, b, api, msg("ali_12"), st)
check("search: the next message is the query", ("search", "ali_12") in api.calls and b.out[-1][2] == "FOUND ali_12")
A.handle(CFG, b, api, msg("hello"), st)
check("… and only the next one: after that, text shows the menu", ("search", "hello") not in api.calls)
A.handle(CFG, b, api, cb("url"), st)
check("panel address", "panel.test/abc" in b.out[-1][2])
A.handle(CFG, b, api, cb("ab:12"), st)
check("auto-backup interval is saved through the panel", ("every", 12) in api.calls)
A.handle(CFG, b, api, cb("ab:7"), st)
check("… and a made-up interval is not", ("every", 7) not in api.calls)
A.handle(CFG, b, api, cb("rs:bot"), st)
check("restart asks first", not any(c[0] == "restart" for c in api.calls if isinstance(c, tuple))
      and "مطمئنید" in b.out[-1][2])
A.handle(CFG, b, api, cb("rsy:bot"), st)
check("… and restarts on yes", ("restart", "bot") in api.calls)

_big = DATA / "big.zip"
with open(_big, "wb") as f:
    f.seek(A.TG_DOC_LIMIT + 10)
    f.write(b"0")
api.backup = lambda: _big
b.out.clear()
A.send_backup(b, OWNER, api)
check("over 50 MB: says where the file is instead of failing silently",
      b.out[-1][0] == "send" and str(_big) in b.out[-1][2], b.out[-1][2][:80])
api.backup = lambda: (_ for _ in ()).throw(OSError("disk full"))
A.send_backup(b, OWNER, api)
check("a failed backup says so", "ناموفق" in b.out[-1][2])

# ═══════════════════════════════════════════════════════════
head("Scheduled backup")
# ═══════════════════════════════════════════════════════════
api = FakeApi()
b = FakeBot()
A.update(DATA, **CFG)
now = datetime(2026, 10, 1, 12, 0)
check("first time: sent", A.scheduled_backup(A.load(DATA), b, api, DATA, now=now)
      and b.out[-1][0] == "doc", b.out)
check("… and stamped", A.load(DATA).get("lastBackup") == "2026-10-01T12:00:00")
check("an hour later: not again", not A.scheduled_backup(A.load(DATA), b, api, DATA, now=now + timedelta(hours=1)))
check("a day later: again", A.scheduled_backup(A.load(DATA), b, api, DATA, now=now + timedelta(hours=24, minutes=1)))
A.update(DATA, backupEvery=0)
check("off: never", not A.scheduled_backup(A.load(DATA), b, api, DATA, now=now + timedelta(days=9)))
check("the token stays in its own file, not in the panel config",
      "token" in json.loads((DATA / "adminbot.json").read_text(encoding="utf-8")))

# ═══════════════════════════════════════════════════════════
head("Alerts and settings in the panel")
# ═══════════════════════════════════════════════════════════
import app as AP                                          # noqa: E402

AP.BOT_DB = DATA / "bot.db"
H = AP._bot_handlers()
H.DB.init_db()
TID = H.DB.create_tenant("shop", bot_token="777:SALES", owner_tg_id=OWNER)
check("panel config has no bot token in it", "adminBot" not in AP.load_config())

SENT = []


class TgFake(FakeBot):
    refuse = False

    def send(self, chat_id, text, keyboard=None, **k):
        if TgFake.refuse:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        SENT.append((self.token, chat_id, text))

    def me(self):
        return {"username": "nx_admin_bot"}


AP._tg_bot = lambda tok: TgFake(tok)
URLS = []


class _R:
    def read(self):
        return b"{}"


AP.urllib.request.urlopen = lambda req, timeout=None: (URLS.append(req.full_url), _R())[1]
import urllib.request as _ur                              # noqa: E402
_ur.urlopen = AP.urllib.request.urlopen

A.update(DATA, token="123:ADMIN", monitorToken="", admins=[OWNER], backupEvery=24)
AP._health_state.clear()
AP._health_alert("سرور پنل", {"level": "crit", "summary": "دیسک پر", "checks": []}, key="t1")
check("server alert → the management bot, to the owner", SENT and SENT[-1][0] == "123:ADMIN"
      and SENT[-1][1] == OWNER and "دیسک پر" in SENT[-1][2], SENT[-1:])
check("… and not to the sales bot's group", not any("777:SALES" in u for u in URLS), URLS)

A.update(DATA, monitorToken="456:MON")
AP._health_alert("سرور پنل", {"level": "ok", "summary": "", "checks": []}, key="t1")
check("with a monitoring bot set, alerts use it", SENT[-1][0] == "456:MON")

TgFake.refuse = True
AP._health_alert("سرور پنل", {"level": "crit", "summary": "x-ui خاموش", "checks": []}, key="t1")
TgFake.refuse = False
check("management bot refused (owner never pressed Start) → the sales bot's group as before",
      any("777:SALES" in u for u in URLS), URLS)

A.update(DATA, token="", monitorToken="")
URLS.clear()
AP._health_alert("سرور پنل", {"level": "warn", "summary": "رم", "checks": []}, key="t2")
check("no management bot → sales bot, unchanged", any("777:SALES" in u for u in URLS))


def call(path, method="GET", body=None):
    hd = {"x-admin-password": AP._INTERNAL_PW, "x-admin-path": AP.admin_path(),
          "content-type": "application/json"}
    raw = json.dumps(body).encode() if body is not None else b""
    scope = {"type": "http", "http_version": "1.1", "method": method, "path": path,
             "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "scheme": "https", "server": ("panel.test", 443), "client": ("203.0.113.9", 5555),
             "headers": [(k.encode(), v.encode()) for k, v in hd.items()]}
    out = {"body": b""}
    done = {"x": False}

    async def receive():
        if done["x"]:
            return {"type": "http.disconnect"}
        done["x"] = True
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(m):
        if m["type"] == "http.response.start":
            out["status"] = m["status"]
        elif m["type"] == "http.response.body":
            out["body"] += m.get("body", b"")

    asyncio.run(AP.app(scope, receive, send))
    return out["status"], json.loads(out["body"] or b"{}")


st_, j = call("/api/admin/adminbot", "PUT", {"token": "777:SALES"})
check("a sales bot's token is refused, with the reason", st_ == 400 and "فروش" in j.get("detail", ""), j)
st_, j = call("/api/admin/adminbot", "PUT", {"token": "999:NEWADMIN", "admins": [OWNER], "backupEvery": 12})
check("a new token is checked with getMe and saved", st_ == 200 and j["hasToken"]
      and j["usernames"].get("token") == "nx_admin_bot", j)
check("… and never sent back whole", "NEWADMIN" not in json.dumps(j), j.get("token"))
st_, j = call("/api/admin/adminbot", "PUT", {"token": j["token"], "backupEvery": 6})
check("saving the masked value back keeps the real token",
      st_ == 200 and A.load(DATA)["token"] == "999:NEWADMIN" and A.load(DATA)["backupEvery"] == 6)
st_, j = call("/api/admin/adminbot", "PUT", {"admins": ["abc"]})
check("an id that is not a number is refused", st_ == 400)
st_, j = call("/api/admin/adminbot")
check("the sales bot's owner is offered as the admin id", j.get("suggestAdmin") == OWNER, j)
st_, j = call("/api/admin/adminbot/test", "POST", {})
check("test: the menu goes to each admin", st_ == 200 and j["results"][0]["ok"], j)

AP._read_xui_clients = lambda: ([
    {"email": "shop_12", "group": "ali", "used": 5 * 1024 ** 3, "totalGB": 50 * 1024 ** 3,
     "expiry": -30 * 86400000, "enable": True},
    {"email": "other", "group": "", "used": 0, "totalGB": 0, "expiry": 0, "enable": False}], {}, None)
out = AP._AdminBotApi().search("SHOP")
check("config lookup: case-insensitive, usage, pending start shown in words",
      "shop_12" in out and "other" not in out and "از اولین اتصال" in out, out)

# ═══════════════════════════════════════════════════════════
head("The tunnel bot (docs/specs/2026-10-01-bots-and-tunnel-mesh.md)")
# ═══════════════════════════════════════════════════════════
# In 2.1.0 the "tunnel bot" was a token folded inside the management card:
# no menu of its own, no page, and no alert when a tunnel broke.


class TunApi:
    def __init__(self):
        self.calls = []

    def tunnels(self):
        self.calls.append("tn"); return "TUNNELS"

    def diagnosis(self):
        self.calls.append("dg"); return "DIAG"

    def servers(self):
        self.calls.append("sv"); return "SERVERS"

    def recheck(self):
        self.calls.append("rc"); return "RECHECK"


b, tapi, st = FakeBot(), TunApi(), {}
A.handle_tunnel(CFG, b, tapi, msg("/start", frm=STRANGER), st)
A.handle_tunnel(CFG, b, tapi, cb("tn", frm=STRANGER), st)
check("tunnel bot: a stranger gets nothing", not b.out and not tapi.calls)
A.handle_tunnel(CFG, b, tapi, msg("/start", chat_type="group"), st)
check("… nor the owner in a group", not b.out)
A.handle_tunnel(CFG, b, tapi, msg("/start"), st)
_tb = [x["callback_data"] for r in b.out[-1][3]["inline_keyboard"] for x in r]
check("the owner gets the tunnel menu, every button handled",
      "ربات تانل" in b.out[-1][2] and set(_tb) == {"tn", "dg", "sv", "rc"}, _tb)
for k, want in (("tn", "TUNNELS"), ("dg", "DIAG"), ("sv", "SERVERS"), ("rc", "RECHECK")):
    A.handle_tunnel(CFG, b, tapi, cb(k), st)
check("each button shows its own answer", [o[2] for o in b.out[-4:]] == ["TUNNELS", "DIAG", "SERVERS", "RECHECK"],
      [o[2] for o in b.out[-4:]])

ch = A.level_changes({}, {"1": "ok", "2": "bad", "3": "unknown"})
check("first look: only what is not ok is reported, unknown never", ch == [("2", None, "bad")], ch)
ch = A.level_changes({"1": "ok", "2": "bad"}, {"1": "warn", "2": "ok"})
check("a change either way is reported (broke, recovered)",
      sorted(ch) == [("1", "ok", "warn"), ("2", "bad", "ok")], ch)
check("no change, no message", A.level_changes({"1": "bad"}, {"1": "bad"}) == [])

# the panel side: answers without Pro, and the alert tick
_was = (AP.__dict__.get("TUNNELS_OK"), AP.__dict__.get("TUN"), AP.__dict__.get("_link_diag_data"))
AP.TUNNELS_OK = False
check("without the tunnel section the bot says so, it does not fail",
      AP._TunnelBotApi().tunnels() == AP._TUN_OFF and AP._TunnelBotApi().diagnosis() == AP._TUN_OFF)


class FakeTUN:
    @staticmethod
    def list_tunnels():
        return [{"id": 1, "name": "fi-1", "engineName": "rathole", "status": "running", "nodeOnline": True},
                {"id": 2, "name": "de-1", "engineName": "gost", "status": "stopped", "nodeOnline": False}]

    @staticmethod
    def list_nodes():
        return [{"name": "iran-1", "role": "iran", "online": True, "running_count": 1, "tunnel_count": 2}]


DIAG = {"nodes": [{"id": 7, "name": "iran-1", "verdict": {"level": "ok", "title": "سالم"}}]}
AP.TUNNELS_OK, AP.TUN = True, FakeTUN
AP._link_diag_data = lambda: DIAG
_t = AP._TunnelBotApi().tunnels()
check("tunnels: name, engine, on/off, server offline said",
      "fi-1" in _t and "rathole" in _t and "de-1" in _t and "آفلاین" in _t, _t)
check("servers: role in Persian and running/total", "ایران" in AP._TunnelBotApi().servers()
      and "1/2" in AP._TunnelBotApi().servers())

A.update(DATA, token="123:ADMIN", monitorToken="456:TUN", admins=[OWNER])
SENT.clear()
AP._TUN_LEVELS.clear()
check("first pass, all ok: no message", AP._tunnel_alert_tick() == 0 and not SENT)
DIAG["nodes"][0]["verdict"] = {"level": "bad", "title": "تانل قطع است", "fix": "پورت را عوض کنید"}
AP._tunnel_alert_tick()
check("a tunnel breaks: the tunnel bot tells the owner, with what to do",
      SENT and SENT[-1][0] == "456:TUN" and "تانل قطع است" in SENT[-1][2] and "پورت" in SENT[-1][2], SENT[-1:])
n = len(SENT)
AP._tunnel_alert_tick()
check("still broken: not again", len(SENT) == n)
DIAG["nodes"][0]["verdict"] = {"level": "ok", "title": "سالم"}
AP._tunnel_alert_tick()
check("recovered: said once", len(SENT) == n + 1 and "سالم" in SENT[-1][2])
st_, j = call("/api/admin/adminbot/test", "POST", {})
check("test sends the tunnel bot its own menu", any(r["bot"] == "تانل" and r["ok"] for r in j.get("results", [])), j)
AP.TUNNELS_OK, AP.TUN, AP._link_diag_data = _was

print(f"\n{_ok} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
