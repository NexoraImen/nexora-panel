#!/usr/bin/env python3
"""
Ban and remove a bot user, for the owner and for a reseller, and the
difference between "banned" and "they blocked the bot"
(docs/specs/2026-10-01-admin-bot-backup-ui.md).

What broke before: a failed broadcast set the same flag as a ban, and the bot
ignores banned users, so a customer who blocked the bot once and came back
never got an answer again. And the mini app let a banned user in.

Run: python tests/test-user-block.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="userblock_")
os.environ.update(
    BOT_DB_PATH=os.path.join(TMP, "bot.db"), BILLING_DB_PATH=os.path.join(TMP, "billing.db"),
    NEXORA_ADMIN_PASSWORD="testpw", CONFIG_PATH=os.path.join(TMP, "config.json"),
    ADMIN_PATH_FILE=os.path.join(TMP, "admin_path.json"), NEXORA_NO_ADMIN_BOT="1")
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


import app as AP                                          # noqa: E402

AP.BOT_DB = Path(os.environ["BOT_DB_PATH"])
H = AP._bot_handlers()
H.DB.init_db()
OWNER = H.DB.create_tenant("owner", bot_token="1:T", owner_tg_id=900, panel_url="http://p")
SHOP = H.DB.create_tenant("shop", bot_token="2:T", owner_tg_id=901, parent_id=OWNER)
DO, DS = H.DB.TenantDB(OWNER), H.DB.TenantDB(SHOP)

XUI_DELETED, PORTAL_DELETED, SENT = [], [], []
H.XUI.delete_client = lambda self, ib, uuid, email=None: XUI_DELETED.append(email)
AP._portal_delete_core = lambda t, email, by_whom=None, refund=True: PORTAL_DELETED.append(email)


class FakeBot:
    def __init__(self, token=None):
        self.token = token

    def send(self, chat_id, text, keyboard=None, **k):
        SENT.append((chat_id, text))
        return {"message_id": 1}

    def __getattr__(self, name):
        return lambda *a, **k: {"ok": True}


H.Bot = FakeBot


def user(d, tg):
    d.create_user(tg, None, f"u{tg}")
    return d.get_user(tg)


def sub(d, u, email):
    return d.exec("INSERT INTO subscriptions (tenant_id,user_id,client_email,client_uuid,inbound_id,is_active) "
                  "VALUES (?,?,?,?,1,1)", (d.tid, u["id"], email, "uuid-" + email))


def call(path, method="GET", body=None, portal=None):
    hd = {"content-type": "application/json"}
    if portal:
        hd["x-portal-token"] = portal
    else:
        hd.update({"x-admin-password": AP._INTERNAL_PW, "x-admin-path": AP.admin_path()})
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
    try:
        return out["status"], json.loads(out["body"] or b"{}")
    except ValueError:
        return out["status"], {}


def upd(tg, text="/start"):
    return {"update_id": 1, "message": {"message_id": 1, "text": text, "date": 0,
                                        "from": {"id": tg, "first_name": "x"},
                                        "chat": {"id": tg, "type": "private"}}}


def answered(tg, text="/start"):
    SENT.clear()
    H.dispatch(H.DB.get_tenant(OWNER), FakeBot("1:T"), upd(tg, text))
    return any(c == tg for c, _ in SENT)


# ═══════════════════════════════════════════════════════════
head("Banned is not the same as 'they blocked the bot'")
# ═══════════════════════════════════════════════════════════
U1 = user(DO, 7001)
check("a normal customer gets an answer", answered(7001))
# what a failed broadcast used to write: the ban flag, nobody named
DO.exec("UPDATE users SET is_blocked=1 WHERE tenant_id=? AND tg_id=7001", (OWNER,))
check("an old broadcast mark: the customer who came back is answered again", answered(7001))
check("… the flag is cleared and it is on record",
      DO.get_user(7001)["is_blocked"] == 0
      and DO.q("SELECT 1 FROM events WHERE tenant_id=? AND kind='user_back'", (OWNER,)))
src = (ROOT / "bot" / "handlers.py").read_text(encoding="utf-8")
bc = src.split('if "blocked" in msg or "deactivated" in msg')[1][:700]
check("a failed broadcast now writes left_at, not the ban flag",
      "left_at=CURRENT_TIMESTAMP" in bc and "is_blocked=1" not in bc)

# ═══════════════════════════════════════════════════════════
head("The owner bans and removes")
# ═══════════════════════════════════════════════════════════
st, j = call("/api/admin/bot/users/7001/block", "POST", {"block": True})
check("ban: 200", st == 200 and j.get("blocked") is True, j)
check("… the bot ignores a banned user, even on /start", not answered(7001))
check("… and the ban is named, so a return does not lift it",
      DO.get_user(7001)["blocked_by"] == "owner")
try:
    AP.mini_user.__wrapped__ if hasattr(AP.mini_user, "__wrapped__") else None
except Exception:
    pass
# the mini app is Pro: the Community tree has no backend/pro/
_mp = ROOT / "backend" / "pro" / "mini.py"
if _mp.exists():
    _ms = _mp.read_text(encoding="utf-8")
    check("the mini app refuses a banned or removed user",
          'row["is_blocked"]' in _ms and "دسترسی شما مسدود است" in _ms)
DO.exec("UPDATE users SET left_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND tg_id=7001", (OWNER,))
check("banned and had blocked the bot: coming back clears 'left', not the ban",
      not answered(7001) and DO.get_user(7001)["is_blocked"] == 1
      and not DO.get_user(7001)["left_at"])
st, j = call("/api/admin/bot/users/7001/block", "POST", {"block": False})
check("unban: answered again", st == 200 and answered(7001))

U2 = user(DO, 7002)
sub(DO, U2, "own_a")
sub(DO, U2, "own_b")
st, j = call("/api/admin/bot/users/7002", "DELETE")
check("remove: every config of theirs is deleted from 3x-ui",
      st == 200 and set(XUI_DELETED) == {"own_a", "own_b"} and j.get("configs") == 2, (st, j, XUI_DELETED))
check("… marked deleted in the bot", all(r["deleted_at"] and r["deleted_why"] == "user_deleted"
      for r in DO.q("SELECT * FROM subscriptions WHERE tenant_id=? AND user_id=?", (OWNER, U2["id"]))))
st, j = call("/api/admin/bot/users")
check("… and off the users list", st == 200 and all(u["tg_id"] != 7002 for u in j.get("users", [])), j.get("users"))
check("… banned too, so /start does not bring them back", not answered(7002))
# The owner (2026-10-02): a removed user could never come back.
_rm = AP._users_page(OWNER, filter="removed")
check("removed users are listed under their own filter, with a count",
      [u["tg_id"] for u in _rm["users"]] == [7002] and _rm["counts"].get("removed") == 1, _rm.get("counts"))
check("… and the other counts leave them out",
      _rm["counts"].get("all") == len(AP._users_page(OWNER)["users"]), _rm.get("counts"))
st, j = call("/api/admin/bot/users/7002/restore", "POST", {})
check("restore: back on the list and answered again",
      st == 200 and any(u["tg_id"] == 7002 for u in AP._users_page(OWNER)["users"]) and answered(7002), (st, j))
check("… on record", bool(DO.q("SELECT 1 FROM events WHERE tenant_id=? AND kind='user_restored'", (OWNER,))))
check("… its deleted configs stay deleted (a returning user buys again)",
      all(r["deleted_at"] for r in DO.q("SELECT * FROM subscriptions WHERE tenant_id=? AND user_id=?",
                                         (OWNER, U2["id"]))))

U3 = user(DO, 7003)
sub(DO, U3, "own_c")
H.XUI.delete_client = lambda self, ib, uuid, email=None: (_ for _ in ()).throw(RuntimeError("panel down"))
st, j = call("/api/admin/bot/users/7003", "DELETE")
check("3x-ui refuses: 502 naming the config, and the user stays listed",
      st == 502 and "own_c" in j.get("detail", "") and not DO.get_user(7003)["deleted_at"], j)
check("… but banned already", DO.get_user(7003)["is_blocked"] == 1)

# ═══════════════════════════════════════════════════════════
head("A reseller bans and removes its own customers")
# ═══════════════════════════════════════════════════════════
S1 = user(DS, 8001)
sub(DS, S1, "shop_x")
O9 = user(DO, 7009)
AP._portal_tenant_override = None
tok = "portal-token-shop"
_pt = AP.portal_tenant if hasattr(AP, "portal_tenant") else None
if _pt is None or not getattr(AP, "PRO_LOADED", False):
    print("  (Community tree: no reseller portal; skipped)")
else:
    AP.app.dependency_overrides[_pt] = lambda: H.DB.get_tenant(SHOP)
    _allowed = AP.LIC.allowed
    AP.LIC.allowed = lambda *a, **k: True       # no license in a test; the gate is tested elsewhere
    st, j = call("/api/portal/users/8001", "DELETE", portal=tok)
    check("a reseller's config goes through the billing core", st == 200 and PORTAL_DELETED == ["shop_x"], (st, j))
    st, j = call("/api/portal/users/7009/block", "POST", {"block": True}, portal=tok)
    check("a reseller cannot ban the owner's customer", st == 404, (st, j))
    check("… who stays unbanned", not DO.get_user(7009)["is_blocked"])
    AP.app.dependency_overrides.clear()
    AP.LIC.allowed = _allowed

print(f"\n{_ok} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
