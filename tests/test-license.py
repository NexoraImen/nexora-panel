#!/usr/bin/env python3
"""
License core: Ed25519 verify, states, grace boundaries, clock rollback, and the
requires() gate on the real app over ASGI.

Spec: docs/specs/2026-09-29-license-core.md ("Done when" lists what is tested).

Every check here is a break-test: it feeds the module something wrong (a
flipped bit, another machine, a second past the boundary) and expects a
refusal. A suite that only feeds valid licenses passes against a module that
accepts everything.

Run:  python3 tests/test-license.py
"""
import asyncio
import base64
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="license_")
os.environ.update(
    NEXORA_LICENSE_DIR=os.path.join(TMP, "data"),
    BOT_DB_PATH=os.path.join(TMP, "bot.db"),
    BILLING_DB_PATH=os.path.join(TMP, "billing.db"), NEXORA_ADMIN_PASSWORD="testpw",
    CONFIG_PATH=os.path.join(TMP, "config.json"),
    ADMIN_PATH_FILE=os.path.join(TMP, "admin_path.json"))
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


import license as LIC                                      # noqa: E402

MID = Path(TMP) / "machine-id"
MID.write_text("0123456789abcdef0123456789abcdef\n")
LIC.MACHINE_ID_FILES = [str(MID)]


# Test-only signer (RFC 8032 §5.1.6). The real one lives on the issuer.
def keypair(secret):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:], LIC._compress(LIC._mul(a, LIC._G))


def sign(secret, msg):
    a, prefix, A = keypair(secret)
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), "little") % LIC._L
    Rb = LIC._compress(LIC._mul(r, LIC._G))
    S = (r + LIC._h(Rb + A + msg) * a) % LIC._L
    return Rb + S.to_bytes(32, "little")


# ═══════════════════════════════════════════════════════════
head("Ed25519 against the RFC 8032 test vectors")
# ═══════════════════════════════════════════════════════════
VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]
for i, (sk, pk, m, sg) in enumerate(VECTORS, 1):
    sk, pk, m, sg = (bytes.fromhex(v) for v in (sk, pk, m, sg))
    check(f"vector {i}: public key derives", keypair(sk)[2] == pk)
    check(f"vector {i}: signature matches", sign(sk, m) == sg)
    check(f"vector {i}: verifies", LIC.verify(pk, m, sg))
    check(f"vector {i}: extra message byte fails", not LIC.verify(pk, m + b"\x00", sg))
    bad_r = bytes([sg[0] ^ 1]) + sg[1:]
    check(f"vector {i}: flipped bit in R fails", not LIC.verify(pk, m, bad_r))
    bad_s = sg[:40] + bytes([sg[40] ^ 1]) + sg[41:]
    check(f"vector {i}: flipped bit in S fails", not LIC.verify(pk, m, bad_s))
    # S + L is the same point equation but a second valid-looking signature.
    s = int.from_bytes(sg[32:], "little") + LIC._L
    check(f"vector {i}: malleable S+L rejected", not LIC.verify(pk, m, sg[:32] + s.to_bytes(32, "little")))
check("wrong key length fails", not LIC.verify(b"\x01" * 31, b"", b"\x00" * 64))

# ═══════════════════════════════════════════════════════════
head("License files")
# ═══════════════════════════════════════════════════════════
SK = b"\x42" * 32
LIC.KEYS = {"t1": keypair(SK)[2]}
FP = LIC.fingerprint()
DAY = 86400
T0 = 1_900_000_000


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make(kid="t1", secret=SK, **over):
    pl = {"license_id": "L-1", "plan": "monthly", "entitlements": list(LIC.FEATURES),
          "machine": FP, "issued": T0, "expires": T0 + 30 * DAY,
          "valid_until": T0 + 30 * DAY, "grace_days": 14}
    pl.update(over)
    body = json.dumps(pl).encode()
    return {"kid": kid, "payload": b64u(body), "sig": b64u(sign(secret, body))}


def put(doc):
    LIC.remove()
    LIC.reset_clock(T0)
    Path(os.environ["NEXORA_LICENSE_DIR"], "license.json").write_text(json.dumps(doc))


def st(now, doc=None):
    if doc is not None:
        put(doc)
    return LIC.status(now)


check("fingerprint is stable", LIC.fingerprint() == FP and len(FP) == 64)
LIC.remove()
s = LIC.status(T0)
check("no file → none, Pro off", s["state"] == "none" and not s["pro"], s["message"])

good = make()
s = st(T0 + DAY, good)
check("valid license → active", s["state"] == "active" and s["pro"], s["message"])

doc = dict(good)
body = json.loads(base64.urlsafe_b64decode(doc["payload"] + "=="))
body["expires"] = T0 + 3650 * DAY
doc["payload"] = b64u(json.dumps(body).encode())
s = st(T0 + DAY, doc)
check("payload edited after signing → invalid", s["state"] == "invalid" and s["reason"] == "bad_signature" and not s["pro"])
s = st(T0 + DAY, make(kid="zz"))
check("unknown kid → invalid", s["state"] == "invalid" and s["reason"] == "unknown_key")
s = st(T0 + DAY, make(secret=b"\x07" * 32))
check("signed by another key → invalid", s["reason"] == "bad_signature")
s = st(T0 + DAY, {"kid": "t1", "payload": "@@@", "sig": "!!"})
check("broken base64 → invalid", s["reason"] == "malformed")
put(good)
Path(os.environ["NEXORA_LICENSE_DIR"], "license.json").write_text("{half a fi")
check("half-written file → invalid, no crash", LIC.status(T0 + DAY)["reason"] == "malformed")
s = st(T0 + DAY, make(grace_days=999))
check("absurd grace_days → malformed", s["reason"] == "malformed")
s = st(T0 + DAY, make(plan="lifetime"))
check("unknown plan → malformed", s["reason"] == "malformed")
s = st(T0 + DAY, make(expires=True))
check("bool where a time belongs → malformed", s["reason"] == "malformed")

s = st(T0 + DAY, make(machine="f" * 64))
check("another server's license → wrong_machine", s["state"] == "wrong_machine" and not s["pro"], s["message"])
put(good)
MID.write_text("ffffffffffffffffffffffffffffffff\n")
s = LIC.status(T0 + DAY)
check("data/ copied to a server with another machine-id → wrong_machine", s["state"] == "wrong_machine")
MID.write_text("0123456789abcdef0123456789abcdef\n")

# ═══════════════════════════════════════════════════════════
head("Grace boundaries, to the second")
# ═══════════════════════════════════════════════════════════
END = T0 + 30 * DAY
LOCK = END + 14 * DAY
put(good)
for label, now, want in [("end − 1 s", END - 1, "active"), ("end", END, "grace"),
                         ("lock − 1 s", LOCK - 1, "grace"), ("lock", LOCK, "expired")]:
    s = LIC.status(now)
    check(f"{label} → {want}", s["state"] == want and s["pro"] == (want != "expired"), s["state"])
LIC.reset_clock(END)          # the loop above ran the clock forward to LOCK
s = LIC.status(END)
check("grace says 'payment' and names the lock time", s["reason"] == "payment" and s["lock_at"] == LOCK, s["message"])
check("grace promises customers stay connected", "قطع نمی‌شوند" in s["message"])

# Paid for a year, but the server has not reached the issuer for 30 days.
doc = make(plan="yearly", expires=T0 + 365 * DAY, valid_until=T0 + 30 * DAY)
s = st(T0 + 31 * DAY, doc)
check("offline validity lapsed, paid period not → grace for 'refresh'",
      s["state"] == "grace" and s["reason"] == "refresh", s["message"])
s = LIC.status(T0 + 45 * DAY)
check("… then expired, still 'refresh', not 'payment'",
      s["state"] == "expired" and s["reason"] == "refresh" and "تازه" in s["message"])

s = st(T0 + 36500 * DAY, make(plan="owner", expires=None, valid_until=None, grace_days=0))
check("owner license: active a century later", s["state"] == "active" and s["pro"])

# ═══════════════════════════════════════════════════════════
head("Clock rollback")
# ═══════════════════════════════════════════════════════════
put(good)
LIC.status(T0 + 20 * DAY)                                  # last_seen advances
s = LIC.status(T0 + 20 * DAY - 25 * 3600)
check("clock back 25 h → clock, Pro off", s["state"] == "clock" and not s["pro"], s["message"])
s = LIC.status(T0 + 20 * DAY - 23 * 3600)
check("clock back 23 h (NTP-sized) → still active", s["state"] == "active")
put(make(expires=T0 + 10 * DAY, valid_until=T0 + 10 * DAY))
LIC.status(T0 + 30 * DAY)                                  # expired, last_seen = +30d
s = LIC.status(T0 + 5 * DAY)
check("expired license + clock set back into the paid period → clock, not active",
      s["state"] == "clock" and not s["pro"])
LIC.reset_clock(T0 + 5 * DAY)
check("a successful refresh (reset_clock) clears it", LIC.status(T0 + 5 * DAY)["state"] == "active")

# ═══════════════════════════════════════════════════════════
head("install(): a bad file never replaces a good one")
# ═══════════════════════════════════════════════════════════
put(good)
res, why = LIC.install(make(machine="f" * 64), now=T0 + DAY)
check("other machine refused", res is None and why == "wrong_machine")
res, why = LIC.install(make(secret=b"\x07" * 32), now=T0 + DAY)
check("bad signature refused", res is None and why == "bad_signature")
check("… and the good license is still there", LIC.status(T0 + DAY)["state"] == "active")
res, why = LIC.install(make(license_id="L-2"), now=T0 + DAY)
check("good one installs", why is None and res["license_id"] == "L-2")

# ═══════════════════════════════════════════════════════════
head("requires() on the real app, over ASGI")
# ═══════════════════════════════════════════════════════════
import app as AP                                           # noqa: E402
from fastapi import Depends                                # noqa: E402


@AP.app.get("/api/admin/_license_probe",
            dependencies=[Depends(AP.pro_required("mini_app"))])
def _probe():
    return {"ok": True}


def call(path, headers=None, method="GET", body=b""):
    scope = {"type": "http", "http_version": "1.1", "method": method, "path": path,
             "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "scheme": "https", "server": ("panel.test", 443), "client": ("203.0.113.9", 5555),
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
    out = {"body": b"", "headers": {}}
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(m):
        if m["type"] == "http.response.start":
            out["status"] = m["status"]
            out["headers"] = {k.decode(): v.decode() for k, v in m.get("headers", [])}
        elif m["type"] == "http.response.body":
            out["body"] += m.get("body", b"")

    asyncio.run(AP.app(scope, receive, send))
    return out["status"], out["body"].decode("utf-8", "replace"), out["headers"]


H = {"X-Admin-Path": AP.admin_path(), "X-Admin-Password": AP._INTERNAL_PW}
now_real = __import__("time").time()
LIC.remove()
LIC.reset_clock(now_real)
code, body, hdr = call("/api/admin/_license_probe", H)
check("no license → 403 with a reason", code == 403 and "Pro" in body, f"{code} {body[:80]}")
check("… and the X-Nexora-Pro header names the feature", hdr.get("x-nexora-pro") == "mini_app")
code, body, _ = call("/api/admin/_license_probe", {"X-Admin-Path": H["X-Admin-Path"]})
check("anonymous caller gets the auth error, not the license state", code in (401, 422), code)
code, body, _ = call("/api/admin/_license_probe", {**H, "X-Admin-Password": "wrong"})
check("wrong password gets 401, not the license state", code == 401, code)
LIC.install(make(issued=int(now_real), expires=int(now_real) + 30 * DAY,
                 valid_until=int(now_real) + 30 * DAY))
code, body, _ = call("/api/admin/_license_probe", H)
check("valid license → 200", code == 200, f"{code} {body[:80]}")
LIC.install(make(issued=int(now_real), entitlements=["resellers"],
                 expires=int(now_real) + 30 * DAY, valid_until=int(now_real) + 30 * DAY))
code, body, _ = call("/api/admin/_license_probe", H)
check("valid license without this feature → 403 'not in this license'", code == 403 and "در این مجوز نیست" in body, body[:80])
try:
    LIC.requires("typo_feature")
    check("unknown feature key refused at import time", False)
except ValueError:
    check("unknown feature key refused at import time", True)

# ═══════════════════════════════════════════════════════════
head("Endpoints against a fake issuer")
# ═══════════════════════════════════════════════════════════
NOW = int(now_real)
fresh = lambda **o: make(issued=NOW, expires=NOW + 30 * DAY, valid_until=NOW + 30 * DAY, **o)
AP.LICENSE_URLS = []
code, body, _ = call("/api/admin/license/activate", {**H, "Content-Type": "application/json"},
                     "POST", json.dumps({"key": "NX-TEST-KEY-1"}).encode())
check("no issuer configured → 502 that says so", code == 502 and "NEXORA_LICENSE_URLS" in body, body[:90])
AP.LICENSE_URLS = ["http://127.0.0.1:9"]
_, err = AP._issuer("activate", {})
check("unreachable issuer → reason names the URL", err and "127.0.0.1:9" in err, (err or "")[:90])

calls = []
answer = {}


def fake_issuer(action, payload):
    calls.append((action, payload))
    return answer.get(action, (None, "down"))


real_issuer, AP._issuer = AP._issuer, fake_issuer
LIC.remove()
answer["activate"] = ({"license": fresh(license_id="L-A")}, None)
code, body, _ = call("/api/admin/license/activate", {**H, "Content-Type": "application/json"},
                     "POST", json.dumps({"key": "NX-TEST-KEY-1"}).encode())
check("activate installs the issued license", code == 200 and json.loads(body)["license_id"] == "L-A", body[:90])
check("… sending this server's fingerprint", calls[-1][1].get("machine") == FP)
answer["activate"] = ({"license": fresh(license_id="L-B", machine="f" * 64)}, None)
code, body, _ = call("/api/admin/license/activate", {**H, "Content-Type": "application/json"},
                     "POST", json.dumps({"key": "NX-TEST-KEY-2"}).encode())
check("issuer returns another machine's license → 502, says why", code == 502 and "این سرور نیست" in body, body[:90])
check("… and L-A is still installed", LIC.status()["license_id"] == "L-A")
code, body, _ = call("/api/admin/license/activate", {**H, "Content-Type": "application/json"},
                     "POST", json.dumps({"key": "x"}).encode())
check("too-short key → 400 before any network call", code == 400 and calls[-1][1].get("key") == "NX-TEST-KEY-2")

answer["refresh"] = (None, "issuer down for test")
code, body, _ = call("/api/admin/license/refresh", H, "POST")
info = LIC.refresh_info()
check("failed refresh → 502 and recorded, not silent", code == 502 and info["ok"] is False and "issuer down" in info["error"])
answer["refresh"] = ({"license": fresh(license_id="L-A", plan="yearly")}, None)
code, body, _ = call("/api/admin/license/refresh", H, "POST")
check("successful refresh → new license, ok recorded", code == 200 and json.loads(body)["plan"] == "yearly" and LIC.refresh_info()["ok"])
check("… and not due again for a week", not LIC.refresh_due())
check("… due after 7 days", LIC.refresh_due(now=NOW + 7 * DAY + 60))

answer["deactivate"] = (None, "issuer down for test")
code, body, _ = call("/api/admin/license/deactivate", H, "POST")
check("deactivate with issuer down → 502, license kept here", code == 502 and LIC.status()["license_id"] == "L-A", body[:90])
answer["deactivate"] = ({"ok": True}, None)
code, body, _ = call("/api/admin/license/deactivate", H, "POST")
check("deactivate → file gone, state none", code == 200 and LIC.status()["state"] == "none")
code, body, _ = call("/api/admin/license", H)
check("GET /api/admin/license answers", code == 200 and "fingerprint" in json.loads(body))
code, _, _ = call("/api/admin/license", {"X-Admin-Path": H["X-Admin-Path"]})
check("… and needs auth", code in (401, 422))
AP._issuer = real_issuer

# ═══════════════════════════════════════════════════════════
head("Installing the Pro package from the panel")
# ═══════════════════════════════════════════════════════════
# The route runs `nexora pro` detached; here the runner is replaced, so the
# test never starts a real install against this checkout.
ran = []
real_run, AP._run_cli_detached = AP._run_cli_detached, lambda cmd: ran.append(cmd)
code, body, _ = call("/api/admin/license/pro-install", H, "POST")
check("no license → 400 that says to activate first, nothing run",
      code == 400 and "فعال" in body and not ran, body[:90])
LIC.install(make(issued=NOW, expires=NOW + 30 * DAY, valid_until=NOW + 30 * DAY))
code, body, _ = call("/api/admin/license/pro-install", H, "POST")
check("active license → `nexora pro` is started, and the answer says so",
      code == 200 and ran == ["pro"] and "Pro" in body, f"{code} {ran}")
code, _, _ = call("/api/admin/license/pro-install", {"X-Admin-Path": H["X-Admin-Path"]}, "POST")
check("… and it needs auth", code in (401, 422) and ran == ["pro"])
AP._run_cli_detached = real_run
LIC.remove()
_ul = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
check("the update button writes the same log the reader follows",
      'f"nohup bash {cli} {command} > {UPDATE_LOG}' in _ul and '"/tmp/nexora-update.log"' not in
      _ul.split("def _run_cli_detached(")[1].split("\ndef ")[0])
check("and the log reader knows when a Pro install ends",
      '"PRO INSTALL COMPLETE"' in _ul
      and "PRO INSTALL COMPLETE" in (ROOT / "nexora-cli.sh").read_text(encoding="utf-8"))

print(f"\n{_ok} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
