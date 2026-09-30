#!/usr/bin/env python3
"""
Diagnose config creation.

    cd /opt/nexora-panel
    python3 scripts/xui-trace.py

Prints exactly what the panel was asked and what it answered, step by
step, in English so it stays readable on any terminal.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bot"))
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("CONFIG_PATH", str(ROOT / "data" / "config.json"))
os.environ.setdefault("BOT_DB_PATH", str(ROOT / "data" / "bot.db"))

G = "\033[38;5;42m"
R = "\033[38;5;203m"
Y = "\033[38;5;220m"
D = "\033[38;5;245m"
B = "\033[38;5;39m"
X = "\033[0m"


def ok(m):
    print(f"  {G}OK{X}    {m}")


def bad(m):
    print(f"  {R}FAIL{X}  {m}")


def info(m):
    print(f"  {D}{m}{X}")


def head(m):
    print(f"\n{B}-- {m} --{X}")


print(f"\n{B}Nexora config creation diagnostics{X}")

# ── credentials ──
head("1. Panel credentials")

import sqlite3

db = ROOT / "data" / "bot.db"
if not db.exists():
    bad(f"Bot database not found at {db}")
    sys.exit(1)

con = sqlite3.connect(str(db))
con.row_factory = sqlite3.Row
row = con.execute(
    "SELECT panel_url, panel_user, panel_pass, panel_token, default_inbound "
    "FROM tenants LIMIT 1").fetchone()
con.close()

if not row or not row["panel_url"]:
    bad("No panel URL configured")
    info("Set it in the panel: Bot > Connection & settings")
    sys.exit(1)

t = dict(row)
ok(f"URL: {t['panel_url']}")
ok("Auth: API token" if t.get("panel_token") else
   f"Auth: username ({t.get('panel_user') or '?'})")
info(f"Default inbound: {t.get('default_inbound') or 'not set'}")

# ── connect ──
head("2. Connection")

try:
    from xui import XUI, XUIError
except Exception as e:
    bad(f"Cannot import the client: {e}")
    sys.exit(1)

client = XUI(t["panel_url"], t.get("panel_user"), t.get("panel_pass"),
             t.get("panel_token"))

try:
    client.login()
    ok("Logged in")
except Exception as e:
    bad(f"Login failed: {e}")
    sys.exit(1)

try:
    inbounds = client.inbounds()
    ok(f"{len(inbounds)} inbounds")
    for i in inbounds[:6]:
        info(f"  #{i.get('id')}  {i.get('remark') or ''}")
except Exception as e:
    bad(f"Cannot read inbounds: {e}")
    sys.exit(1)

# ── routes ──
head("3. API routes")

try:
    routes = client.discover()
except Exception as e:
    routes = {}
    info(f"discover() raised: {e}")

if routes:
    ok(f"{len(routes)} routes read from the panel's OpenAPI spec")
    interesting = [p for p in routes
                   if "client" in p.lower() or "addclient" in p.lower()]
    for p in sorted(interesting)[:12]:
        info(f"  {','.join(sorted(routes[p]))}  {p}")
    if not interesting:
        info("  no client-related routes found")
else:
    info("No OpenAPI spec served - paths will be probed by trial and error")

# ── request schema ──
head("4. Expected request body")

# which path will actually be used
create_path = None
for cand in ("/panel/api/clients/add", "/panel/api/clients",
             "/panel/api/clients/create"):
    if client.has_route(cand, "POST"):
        create_path = cand
        break

if create_path:
    ok(f"Create path: {create_path}")
else:
    info("No create path found among the known candidates")
    create_path = "/panel/api/clients"

attach = [p for p in (routes or {}) if "attach" in p.lower()]
if attach:
    info(f"Attach paths available: {', '.join(sorted(attach)[:3])}")

# Print the panel's own definition for this route. If the parser
# above misses it, the raw spec still shows what the panel wants.
spec = getattr(client, "_spec", None)
if spec:
    node = (spec.get("paths") or {}).get(create_path, {}).get("post")
    if node:
        import json as _j
        raw = _j.dumps(node, ensure_ascii=False)
        info("Panel's definition for this route:")
        for i in range(0, min(len(raw), 1400), 110):
            info("  " + raw[i:i + 110])
    else:
        info(f"The spec has no POST entry for {create_path}")

schema = None
try:
    schema = client.request_schema(create_path, "post")
except Exception as e:
    info(f"request_schema raised: {e}")

if schema:
    props = list((schema.get("properties") or {}).keys())
    req = schema.get("required") or []
    ok(f"{len(props)} fields declared")
    info(f"  fields:   {', '.join(props[:14])}")
    info(f"  required: {', '.join(req) if req else 'none declared'}")
else:
    info("No schema declared for POST /panel/api/clients")
    info("The client will try known body shapes instead")

# ── real attempt ──
head("5. Creating a test config")

inbound = t.get("default_inbound") or (inbounds[0]["id"] if inbounds else None)
if not inbound:
    bad("No inbound to use")
    sys.exit(1)

import secrets as _s
email = f"nexora_trace_{_s.token_hex(3)}"
info(f"inbound {inbound}, email {email}")

# capture what gets sent, so a rejection can be read against it
sent = []
_orig = client._req
def _spy(method, path, raw=False, **kw):
    if "client" in path:
        body = kw.get("json") or kw.get("data")
        if body:
            kind = "json" if kw.get("json") else "form"
            sent.append((path, kind, list(body.keys())))
    return _orig(method, path, raw=raw, **kw)
client._req = _spy

created = None
try:
    created = client.add_client(int(inbound), email, gb=1, days=1)
    ok("Panel accepted the request")
    if sent:
        p, kind, keys = sent[-1]
        info(f"Used: {p} as {kind}")
        info(f"Fields: {', '.join(keys[:8])}")
except XUIError as e:
    bad(f"{e}")
    print()
    if sent:
        info(f"Bodies that were tried ({len(sent)}):")
        for p, kind, keys in sent:
            info(f"  [{kind:4}] {p}  ->  {', '.join(keys[:7])}")
    print()
    info("The panel names the field it wants in the message above.")
    info("Compare it with the fields sent and report both.")
    sys.exit(1)
except Exception as e:
    bad(f"{type(e).__name__}: {e}")
    sys.exit(1)

# ── verify ──
head("6. Reading it back")

# which GET routes the panel offers for reading a client back
gets = sorted(p for p, ms in (routes or {}).items()
              if "GET" in ms and "client" in p.lower())
if gets:
    info(f"Client GET routes ({len(gets)}):")
    for p in gets[:10]:
        info(f"  {p}")

try:
    found = client.find_client(int(inbound), email=email)
    if found:
        ok("Config exists in the panel")
        info(f"  fields: {', '.join(list(found.keys())[:10])}")

        # The uuid we keep must be the uuid the panel issued. When it is
        # not, the config still works for the customer but every later
        # renew / disable / delete looks up a uuid that does not exist.
        panel_uuid = client._client_uuid(found)
        ours = (created or {}).get("id")
        if panel_uuid and ours == panel_uuid:
            ok(f"uuid matches the panel  ({panel_uuid})")
        elif panel_uuid:
            bad("uuid MISMATCH — renewals and blocking will fail")
            info(f"  we stored : {ours}")
            info(f"  panel has : {panel_uuid}")
        else:
            info(f"  panel returned no uuid-shaped field; ours: {ours}")
    else:
        bad("Panel accepted the request but the config could not be read")
        info("Every GET route above was tried. If one of them is the right")
        info("one, report it and the lookup will use it directly.")
except Exception as e:
    info(f"Lookup raised: {type(e).__name__}: {e}")

# ── cleanup ──
head("7. Cleanup")

try:
    if created and created.get("id"):
        client.delete_client(int(inbound), created["id"], email=email)
        ok("Test config removed")
except Exception as e:
    info(f"Could not remove it: {e}")
    info(f"Delete {email} manually from the panel")

print()
print(f"  {G}Config creation works.{X}")
print()
