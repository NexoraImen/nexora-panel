"""
The channel from /start (2.3.8).

The owner: «as soon as he presses start, ask him to join the channel». The
forced join existed but asked only before the plans and the free trial. Each
claim here is behaviour, through `dispatch`, on a fake Telegram:

  - /start: the channel first, before the phone question and the menu;
  - the referral code is kept even when the channel stops him;
  - «عضو شدم» not joined: other words (an identical edit would be refused and
    sent again as a second message); joined: the phone question, then menu;
  - «back to menu» cannot step round it;
  - staff are never stopped; off at /start → the old order; Telegram unable
    to check (bot not admin in the channel) → not stopped.

Run:  PYTHONIOENCODING=utf-8 python tests/bot/test_start_channel.py
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BOT_DB_PATH"] = tempfile.mktemp(suffix=".db")

from bot import db                # noqa: E402
import bot.handlers as H          # noqa: E402

PASS = FAIL = 0
SENT = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))


class Tg:
    status = "left"
    broken = False

    def __init__(self, token=None):
        self.token = token

    def send(self, chat_id, text, keyboard=None, topic_id=None, **k):
        SENT.append({"to": chat_id, "text": text, "kb": keyboard, "edit": False})
        return {"message_id": len(SENT)}

    def edit(self, chat_id, message_id, text, keyboard=None, **k):
        SENT.append({"to": chat_id, "text": text, "kb": keyboard, "edit": True})
        return {"message_id": message_id}

    def member_status(self, chat_id, user_id):
        if Tg.broken:
            raise RuntimeError("Bad Request: member list is inaccessible")
        return Tg.status

    def answer_cb(self, *a, **k):
        return True

    def __getattr__(self, name):
        return lambda *a, **k: {"message_id": 1}


db.init_db()
TID = db.create_tenant("shop", bot_token="1:T", owner_tg_id=999)
db.save_tenant_settings(TID, {"force_channel_on": True, "force_channel": "@nexora_ch"})
bot = Tg()


def tenant():
    return db.get_tenant(TID)


def start(uid, text="/start", name="علی"):
    SENT.clear()
    H.dispatch(tenant(), bot, {"update_id": 1, "message": {
        "message_id": 1, "text": text, "chat": {"id": uid, "type": "private"},
        "from": {"id": uid, "first_name": name, "is_bot": False}}})


def press(uid, data):
    SENT.clear()
    H.dispatch(tenant(), bot, {"update_id": 2, "callback_query": {
        "id": "c", "data": data, "from": {"id": uid, "first_name": "علی", "is_bot": False},
        "message": {"message_id": 7, "chat": {"id": uid}}}})


def said(word):
    return any(word in m["text"] for m in SENT)


def buttons():
    out = []
    for m in SENT:
        for row in (m["kb"] or {}).get("inline_keyboard", []) if isinstance(m["kb"], dict) else []:
            out += [b.get("callback_data") or b.get("url") for b in row]
    return out


D = H.DB.TenantDB(TID)
start(1000, name="معرف")                       # someone who invites, already in
Tg.status = "member"
inviter = D.get_user(1000)

Tg.status = "left"
start(555, f"/start {inviter['ref_code']}")
check("/start: the channel first, nothing else", said("یک قدم مانده") and len(SENT) == 1
      and not said("شماره تماس"), [m["text"][:30] for m in SENT])
check("… with the join link and «عضو شدم»", "https://t.me/nexora_ch" in buttons() and "joined" in buttons(),
      buttons())
check("… the phone question not asked yet", not (D.get_user(555) or {}).get("phone_asked"))
check("the referral code is kept although he was stopped",
      (D.get_user(555) or {}).get("referred_by") in (inviter["id"], inviter["tg_id"]), D.get_user(555))

press(555, "joined")
check("«عضو شدم» without joining: other words, edited in place",
      said("هنوز عضویتتان دیده نشد") and SENT[0]["edit"] and len(SENT) == 1, SENT)
press(555, "menu")
check("«back to menu» does not step round it", said("یک قدم مانده") and not said("خرید"),
      [m["text"][:30] for m in SENT])

Tg.status = "member"
press(555, "joined")
check("joined: then the phone question", said("شماره تماس"), [m["text"][:30] for m in SENT])
press(555, "menu")
check("… and the menu after", not said("یک قدم مانده") and not said("شماره تماس") and SENT,
      [m["text"][:30] for m in SENT])

Tg.status = "left"
start(999)
check("staff are never stopped", not said("یک قدم مانده"), [m["text"][:30] for m in SENT])

db.save_tenant_settings(TID, {"force_channel_on": True, "force_channel": "@nexora_ch",
                              "force_channel_start": False})
start(556)
check("asked only before buying (start off): the old order, phone first",
      said("شماره تماس") and not said("یک قدم مانده"), [m["text"][:30] for m in SENT])
press(556, "buy")
check("… and the plans still stop him", said("یک قدم مانده"))

db.save_tenant_settings(TID, {"force_channel_on": True, "force_channel": "@nexora_ch"})
Tg.broken = True
start(557)
check("Telegram cannot check (bot not admin there): not stopped", not said("یک قدم مانده"))
Tg.broken = False

db.save_tenant_settings(TID, {"force_channel_on": False, "force_channel": "@nexora_ch"})
start(558)
check("forced join off: nothing asked", not said("یک قدم مانده"))

print(f"\n  {PASS} passed · {FAIL} failed")
sys.exit(1 if FAIL else 0)
