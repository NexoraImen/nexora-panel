"""
The admin group's topics (2.3.8).

Until 2.3.8 the connection page said «the bot makes the topics» and nothing
ever made one: `create_topic` was never called, so every notification landed
in General, and half of them did not even name a topic. Each claim here is
behaviour, on a fake Telegram:

  - a topic is made the first time it is needed, once, and kept;
  - kinds that share a topic (renewals → sales) land in one thread;
  - a group without topics: General, and no retry storm;
  - a topic deleted in the group is made again and the message resent;
  - two notifications at once make one topic, not two;
  - every `notify_group` in bot/ names a topic that exists (ast scan);
  - the scheduled backup reaches the admin group without a management bot.

Run:  PYTHONIOENCODING=utf-8 python tests/bot/test_topics.py
"""
import ast
import glob
import json
import os
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BOT_DB_PATH"] = tempfile.mktemp(suffix=".db")

from bot import db                # noqa: E402
import bot.handlers as H          # noqa: E402
TelegramError = H.TelegramError   # handlers catch their own copy of tg (two module objects)

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))


class Tg:
    def __init__(self):
        self.made, self.sent, self.refuse, self.lost, self.slow = [], [], False, set(), 0
        self.tries = 0
        self.next = 100

    def create_topic(self, chat_id, name, icon_color=None):
        self.tries += 1
        if self.slow:
            time.sleep(self.slow)
        if self.refuse:
            raise TelegramError("Bad Request: the chat is not a forum")
        self.next += 1
        self.made.append((chat_id, name, self.next))
        return {"message_thread_id": self.next, "name": name}

    def send(self, chat_id, text, keyboard=None, topic_id=None, **k):
        if topic_id in self.lost:
            raise TelegramError("Bad Request: message thread not found")
        self.sent.append((chat_id, topic_id, text))
        return {"message_id": 1}


db.init_db()
TID = db.create_tenant("owner", bot_token="1:T", owner_tg_id=555)
db.update_tenant(TID, admin_group_id=-100777)


def ctx(tg):
    return H.Ctx(tg, H.DB.get_tenant(TID))


def topics():
    return json.loads(H.DB.get_tenant(TID).get("topics") or "{}")


print("\n── made when needed, once ──")
tg = Tg()
ctx(tg).notify_group("رسید", topic="receipts")
check("the first receipt makes the receipts topic, with its title",
      [m[1] for m in tg.made] == [H.TOPICS["receipts"]] and tg.made[0][0] == -100777, tg.made)
check("… and is sent into it", tg.sent[-1][:2] == (-100777, tg.made[0][2]), tg.sent)
ctx(tg).notify_group("رسید ۲", topic="receipts")
check("the second does not make another", len(tg.made) == 1 and tg.sent[-1][1] == tg.made[0][2])
check("the id is kept in the tenant", topics().get("receipts") == tg.made[0][2], topics())

print("\n── shared topics ──")
ctx(tg).notify_group("تمدید", topic="renewals")
ctx(tg).notify_group("خرید", topic="sales")
check("renewals and sales: one thread", tg.sent[-1][1] == tg.sent[-2][1] and topics().get("sales"),
      tg.sent[-2:])
check("no topic named after an alias", "renewals" not in topics())

print("\n── a group without topics ──")
db.update_tenant(TID, topics={})
H._TOPIC_FAILED.clear()
tg = Tg()
tg.refuse = True
ctx(tg).notify_group("هشدار", topic="alerts")
check("not a forum: sent to General anyway", tg.sent[-1][:2] == (-100777, None), tg.sent)
ctx(tg).notify_group("هشدار ۲", topic="alerts")
ctx(tg).notify_group("رسید", topic="receipts")
check("… and not asked again on every message (one try in ten minutes)", len(tg.sent) == 3
      and tg.tries == 1 and H._TOPIC_FAILED.get(TID), tg.tries)
H._TOPIC_FAILED[TID] = time.monotonic() - 601
tg.refuse = False
ctx(tg).notify_group("هشدار ۳", topic="alerts")
check("ten minutes later, topics on: made", tg.made and tg.sent[-1][1] == tg.made[-1][2])

class NoTopics(Tg):
    create_topic = None                 # a client that cannot make topics at all


H._TOPIC_FAILED.clear()
db.update_tenant(TID, topics={})
nt = NoTopics()
ctx(nt).notify_group("رسید", topic="receipts")
check("any failure making a topic (not only Telegram's): General, the message not lost",
      nt.sent and nt.sent[-1][:2] == (-100777, None), nt.sent)
H._TOPIC_FAILED.clear()
ctx(tg).notify_group("هشدار ۳", topic="alerts")

print("\n── a topic deleted in the group ──")
old = topics()["alerts"]
tg.lost.add(old)
ctx(tg).notify_group("دیسک پر", topic="alerts")
new = topics()["alerts"]
check("made again and the message resent there", new != old and tg.sent[-1] == (-100777, new, "دیسک پر"),
      (old, new, tg.sent[-1:]))

print("\n── two at once ──")
db.update_tenant(TID, topics={})
tg = Tg()
tg.slow = 0.2
th = [threading.Thread(target=ctx(tg).notify_group, args=(f"م{i}",), kwargs={"topic": "users"})
      for i in range(4)]
for t in th:
    t.start()
for t in th:
    t.join()
check("four notifications at once make one topic", len(tg.made) == 1
      and {s[1] for s in tg.sent} == {tg.made[0][2]}, (tg.made, tg.sent))

print("\n── all at once, at the bot's start ──")
db.update_tenant(TID, topics={})
tg = Tg()
ctx(tg).ensure_topics()
check("every topic made", sorted(topics()) == sorted(H.TOPICS) and len(tg.made) == len(H.TOPICS))
ctx(tg).ensure_topics()
check("… and not again", len(tg.made) == len(H.TOPICS))

print("\n── no group ──")
db.update_tenant(TID, admin_group_id=None)
tg = Tg()
ctx(tg).notify_group("رسید", topic="receipts")
ctx(tg).notify_group("کاربر تازه", topic="users")
check("waiting kinds go to the owner's chat, the rest nowhere",
      [s[:2] for s in tg.sent] == [(555, None)] and not tg.made, tg.sent)
db.update_tenant(TID, admin_group_id=-100777)

print("\n── every staff message names a real topic ──")
known = set(H.TOPICS) | set(H.TOPIC_ALIAS)
bad = []
for path in glob.glob(os.path.join(_ROOT, "bot", "**", "*.py"), recursive=True):
    src = open(path, encoding="utf-8").read()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("notify_group", "staff_chat")
                and not (isinstance(node.func.value, ast.Name) and node.func.value.id == "self")):
            kw = {k.arg: k.value for k in node.keywords}
            arg = kw.get("topic") or (node.args[0] if node.func.attr == "staff_chat" and node.args else None)
            val = arg.value if isinstance(arg, ast.Constant) else None
            if val not in known:
                bad.append(f"{os.path.relpath(path, _ROOT)}:{node.lineno} topic={val!r}")
check("no notify_group / staff_chat without a known topic", not bad, bad)
check("every alias points at a topic", all(v in H.TOPICS for v in H.TOPIC_ALIAS.values()))

print("\n── the scheduled backup, with no management bot ──")
sys.path.insert(0, os.path.join(_ROOT, "backend"))
import adminbot as AB              # noqa: E402

DATA = tempfile.mkdtemp()


class Api:
    def __init__(self, ok):
        self.ok, self.calls = ok, []

    def group_backup(self, why=""):
        self.calls.append(why)
        return self.ok


api = Api(True)
check("due, no management bot: the admin group gets it",
      AB.scheduled_backup({"backupEvery": 24}, None, api, DATA) and api.calls == [" (خودکار)"])
check("… and the schedule is stamped", AB.load(DATA).get("lastBackup"))
check("… not again before it is due", not AB.scheduled_backup(AB.load(DATA), None, api, DATA)
      and len(api.calls) == 1)
api2, D2 = Api(False), tempfile.mkdtemp()
AB.scheduled_backup({"backupEvery": 24}, None, api2, D2)
check("no group: nothing sent, not stamped (tried again later)", not AB.load(D2).get("lastBackup"))
check("backups off (0): nothing", not AB.scheduled_backup({"backupEvery": 0}, None, Api(True), tempfile.mkdtemp()))

print(f"\n  {PASS} passed · {FAIL} failed")
sys.exit(1 if FAIL else 0)
