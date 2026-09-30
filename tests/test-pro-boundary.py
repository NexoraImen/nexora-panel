#!/usr/bin/env python3
"""
The line between the free core and the Pro areas.

Spec: docs/specs/2026-09-29-pro-split.md ("Rules" and "Done when").

This runs in both trees. In the private tree it checks the Pro code obeys the
rules; in the Community tree (no pro/ folders) it checks the core stands on
its own. Each check is a way the split has broken, or would break, silently:
a Pro route that forgot its gate answers everyone; a renamed core helper fails
only when a customer clicks; a bare `import pro` picks whichever folder
sys.path lists first.

Run:  python3 tests/test-pro-boundary.py
"""
import ast
import asyncio
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="proboundary_")
ENV = dict(
    NEXORA_LICENSE_DIR=os.path.join(TMP, "license"),
    BOT_DB_PATH=os.path.join(TMP, "bot.db"),
    BILLING_DB_PATH=os.path.join(TMP, "billing.db"), NEXORA_ADMIN_PASSWORD="testpw",
    CONFIG_PATH=os.path.join(TMP, "config.json"),
    ADMIN_PATH_FILE=os.path.join(TMP, "admin_path.json"))
os.environ.update(ENV)
os.environ.pop("NEXORA_ADMIN_PATH", None)
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


PRO_API = sorted((ROOT / "backend" / "pro").glob("*.py"))
HAS_PRO = bool(PRO_API)

# ═══════════════════════════════════════════════════════════
head("No bare `import pro`")
# ═══════════════════════════════════════════════════════════
bare = []
for d in ("backend", "bot", "tests", "scripts", "issuer"):
    for f in glob.glob(str(ROOT / d / "**" / "*.py"), recursive=True):
        for i, line in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*(import pro\b|from pro\b)", line):
                bare.append(f"{Path(f).relative_to(ROOT)}:{i}")
check("nothing imports `pro` by its bare name", not bare, ", ".join(bare[:5]))

# Nor a module that moved into backend/pro. Updates copy files and delete none,
# so a server updated from 1.x still has backend/firewall.py (and fx.py, ...);
# a bare `import firewall` finds that stale copy first and runs it silently.
_moved = {Path(f).stem for f in glob.glob(str(ROOT / "backend" / "pro" / "*.py"))} - {"__init__"}
stale = []
for f in glob.glob(str(ROOT / "backend" / "**" / "*.py"), recursive=True):
    for i, line in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
        m = re.match(r"\s*(?:import|from)\s+(\w+)", line)
        if m and m.group(1) in _moved:
            stale.append(f"{Path(f).relative_to(ROOT)}:{i} ({m.group(1)})")
check("no bare import of a module that moved into backend/pro",
      not stale if HAS_PRO else True, ", ".join(stale[:5]) or f"{len(_moved)} modules")

# ═══════════════════════════════════════════════════════════
head("Pro code only calls core names that exist")
# ═══════════════════════════════════════════════════════════
import license as LIC                                      # noqa: E402
import app as AP                                           # noqa: E402

used = {}
# Only the register(app, core) modules reach the core through `C`/`core`; the
# files that run in the app namespace use plain names, and the modules moved
# there (tunnels.py, firewall.py, ...) have locals of their own.
for f in [f for f in PRO_API if "def register(app, core)" in f.read_text(encoding="utf-8")]:
    for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id in ("C", "core")):
            used.setdefault(n.attr, f.name)
missing = sorted(k for k in used if k not in vars(AP))
check(f"all {len(used)} core names used by backend/pro exist in app.py", not missing,
      ", ".join(f"{k} ({used[k]})" for k in missing))

# ═══════════════════════════════════════════════════════════
head("Every Pro route asks the license")
# ═══════════════════════════════════════════════════════════
check("Pro code loaded without error" if HAS_PRO else "Community tree: no Pro code, nothing loaded",
      AP.PRO_LOADED == HAS_PRO and AP.PRO_ERROR == "", AP.PRO_ERROR)
PRO_DIR = str(ROOT / "backend" / "pro").replace("\\", "/")


def from_pro(r):
    """A route whose endpoint was written in backend/pro/: a register() module,
    or a file run in the app namespace (its functions belong to `app`, so the
    module name says nothing; the file they were compiled from does)."""
    code = getattr(getattr(r, "endpoint", None), "__code__", None)
    return bool(code) and code.co_filename.replace("\\", "/").startswith(PRO_DIR)


pro_routes = [r for r in AP.app.routes if from_pro(r)]


def gated(r):
    """The right gate for the kind of route: the admin password, the portal
    session or (agents authenticate inside the endpoint) the license alone."""
    want = ("portal_login_pro_required." if r.path.startswith("/api/portal/") and r.path.endswith("/login")
            else "portal_pro_required." if r.path.startswith("/api/portal/")
            else "requires." if r.path.startswith("/api/agent/")
            else "_customer_pro_gate." if r.path.startswith("/api/mini/")
            else "_partner_pro_gate." if r.path.startswith("/api/aff/") else "pro_required.")
    return any(getattr(d.call, "__qualname__", "").startswith(want)
               for d in r.dependant.dependencies)


ungated = [r.path for r in pro_routes if not gated(r)]
if HAS_PRO:
    check(f"{len(pro_routes)} Pro routes registered", len(pro_routes) > 0)
    sys.path.insert(0, str(ROOT / "scripts"))
    from route_decls import route_decls                     # noqa: E402
    declared = {(m.upper(), path) for m, path, f in route_decls(ROOT) if f.startswith("backend/pro/")}
    live = {(m, r.path) for r in pro_routes for m in r.methods}
    check("every route declared in backend/pro is live, and no other",
          declared == live, f"declared only: {sorted(declared - live)[:3]} live only: {sorted(live - declared)[:3]}")
check("each one has the right gate (auth first, then license)", not ungated, ", ".join(ungated))
unmapped = sorted({r.path for r in pro_routes if LIC.pro_feature_of(r.path) is None})
check("every Pro route's path is in license.PRO_PATHS", not unmapped, ", ".join(unmapped))
core_paths = {(r.path, m) for r in AP.app.routes if r not in pro_routes
              for m in (getattr(r, "methods", None) or ())}
twice = sorted({r.path for r in pro_routes for m in r.methods if (r.path, m) in core_paths})
check("no Pro route shadows a core route", not twice, ", ".join(twice))


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
LIC.remove()
bad = []
for r in pro_routes:
    path = re.sub(r"\{[^}]+\}", "1", r.path)
    for m in r.methods:
        if path.startswith("/api/portal/") and path.endswith("/login"):
            # No session exists before login: the license answers, in the
            # reseller's words (never the owner's license message).
            code, body, hdr = call(path, {}, m, b'{"password": "x"}')
            if code != 403 or not hdr.get("x-nexora-pro") or AP.RESELLER_LOCKED not in body:
                bad.append(f"{m} {path} (portal login) → {code}")
            continue
        if path.startswith("/api/portal/"):
            # Needs a portal session to reach the license; here only the
            # order is checked: no session -> the portal's 401, never 403.
            code, _, hdr = call(path, {}, m, b"{}")
            if code != 401 or hdr.get("x-nexora-pro"):
                bad.append(f"{m} {path} without a session → {code}")
            continue
        if path.startswith("/api/aff/"):
            # The partner app has its own session, checked inside the
            # endpoint: the license answers first, in the partner's words.
            code, body, hdr = call(path, {}, m, b"{}")
            if code != 403 or not hdr.get("x-nexora-pro") or AP.PARTNER_LOCKED not in body:
                bad.append(f"{m} {path} (partner) → {code}")
            continue
        if path.startswith(("/api/agent/", "/api/mini/")):
            # Agents (node token) and mini-app customers (Telegram signature)
            # authenticate inside the endpoint, so the license answers first;
            # nothing but the license state is exposed.
            code, _, hdr = call(path, {}, m, b"{}")
            if code != 403 or not hdr.get("x-nexora-pro"):
                bad.append(f"{m} {path} (agent) → {code}")
            continue
        code, body, hdr = call(path, H, m, b"{}")
        if code != 403 or not hdr.get("x-nexora-pro"):
            bad.append(f"{m} {path} → {code}")
        code, _, _ = call(path, {"X-Admin-Path": H["X-Admin-Path"]}, m, b"{}")
        if code not in (401, 422):
            bad.append(f"{m} {path} anonymous → {code}")
check("with no license: 403 + X-Nexora-Pro for everyone logged in, auth error for anyone else",
      not bad, "; ".join(bad[:4]))
# With a session, a locked portal answers in the reseller's words too: the
# owner's license state (grace, clock, payment) is not the reseller's to read.
_dep = AP.portal_pro_required("resellers")
try:
    _dep(t={"id": 1})
    _pr = (200, "", {})
except AP.HTTPException as e:
    _pr = (e.status_code, str(e.detail), e.headers or {})
check("a reseller with a session reads the portal's words, not the owner's license",
      _pr[0] == 403 and _pr[1] == AP.RESELLER_LOCKED and _pr[2].get("X-Nexora-Pro") == "resellers",
      f"{_pr[0]} {_pr[1][:60]}")

# Core paths under a Pro prefix (PRO_PATHS value None): the owner's data. A
# lapsed license must never stop a backup, so these answer with no license.
_core_under_pro = [p for p, f in LIC.PRO_PATHS.items() if f is None]
_locked = []
_asked = 0
for p in _core_under_pro:
    # Each with its own method: a GET to the POST-only restore answers 405,
    # which is "not 403" and would prove nothing. An empty restore is a 400
    # before anything is written.
    for r in AP.app.routes:
        if getattr(r, "path", None) != p:
            continue
        for m in r.methods:
            _asked += 1
            code, _, hdr = call(p, H, m, b"{}")
            if code in (403, 404, 405) or hdr.get("x-nexora-pro"):
                _locked.append(f"{m} {p} → {code}")
check("with no license: backup, restore and the x-ui path still answer",
      _asked >= len(_core_under_pro) and not _locked, "; ".join(_locked) or f"{_asked} routes")
code, body, _ = call("/api/admin/license", H)
view = json.loads(body) if code == 200 else {}
check("license view names every feature and its lock reason",
      set(view.get("features", {})) == set(LIC.FEATURES)
      and set(view.get("denials", {})) == set(LIC.FEATURES), code)
check("… and whether Pro code loaded", view.get("pro_loaded") is HAS_PRO and view.get("pro_error") == "")

if HAS_PRO:
    import importlib.util as _ilu
    _sp2 = _ilu.spec_from_file_location("app_second_copy", ROOT / "backend" / "app.py")
    _A2 = _ilu.module_from_spec(_sp2)
    _sp2.loader.exec_module(_A2)
    # Seen once: the second load reused the first one's Pro submodules and
    # re-pointed them, so the first app's funnel read the second app's database.
    check("a second app.py in one process leaves the first app's Pro code on the first app",
          all(a.C._root_tenant_row is AP._root_tenant_row
              for a in AP.PRO_API.AREAS if hasattr(a, "C"))
          and _A2.PRO_API is not AP.PRO_API)

# ═══════════════════════════════════════════════════════════
head("The panel's Pro keys are real feature keys")
# ═══════════════════════════════════════════════════════════
src = "\n".join(Path(f).read_text(encoding="utf-8")
                for f in glob.glob(str(ROOT / "frontend" / "src" / "**" / "*.js*"), recursive=True))
keys = set(re.findall(r'\bpro: "([a-z_]+)"', src)) | set(re.findall(r'\bfeature="([a-z_]+)"', src))
check("every nav `pro:` and ProSection `feature=` is in license.FEATURES",
      keys and keys <= set(LIC.FEATURES), sorted(keys - set(LIC.FEATURES)))

# ═══════════════════════════════════════════════════════════
head("Community edition and broken Pro code (fresh processes)")
# ═══════════════════════════════════════════════════════════
PROBE = r'''
import asyncio, json, os, sys
sys.path[:0] = [os.environ["R"] + "/bot", os.environ["R"] + "/backend"]
import app as AP
import handlers as HB
paths = {r.path for r in AP.app.routes}
print(json.dumps({"loaded": AP.PRO_LOADED, "error": AP.PRO_ERROR,
                  "channel_route": "/api/admin/channel" in paths,
                  "bot_channel": HB.pro("channel") is not None,
                  "check_auth_ok": callable(AP.check_auth)}))
'''


def probe(api_dir, bot_dir):
    env = {**os.environ, **ENV, "R": str(ROOT), "PYTHONIOENCODING": "utf-8",
           "NEXORA_PRO_API_DIR": api_dir, "NEXORA_PRO_BOT_DIR": bot_dir,
           "BOT_DB_PATH": os.path.join(TMP, "p.db"), "BOT_DB_PATH": os.path.join(TMP, "p.db")}
    p = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=str(ROOT))
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {"crash": (p.stderr or p.stdout)[-300:]}


empty = os.path.join(TMP, "empty")
os.makedirs(empty)
r = probe(empty, empty)
check("without pro/: the panel starts, no Pro route, nothing reported broken",
      r.get("loaded") is False and r.get("error") == "" and r.get("channel_route") is False, r)
check("… and the bot finds no channel module (and says None, not an error)",
      r.get("bot_channel") is False, r)

broken = os.path.join(TMP, "broken")
os.makedirs(broken)
Path(broken, "__init__.py").write_text("raise RuntimeError('half-copied Pro bundle')\n")
r = probe(broken, empty)
check("broken Pro code: the core still starts", "crash" not in r and r.get("loaded") is False, r)
check("… and the error is kept for the license card", "half-copied Pro bundle" in r.get("error", ""), r)

# Code run in the app namespace (NAMESPACE): its two refusals.
_ns_init = 'AREAS = ()\nNAMESPACE = ("x.py",)\n' \
           'def register(app, core):\n    pass\n'
unmapped = os.path.join(TMP, "unmapped")
os.makedirs(unmapped)
Path(unmapped, "__init__.py").write_text(_ns_init)
Path(unmapped, "x.py").write_text('@app.get("/api/admin/elsewhere")\ndef _x():\n    return {}\n')
r = probe(unmapped, empty)
check("a moved route whose path maps to no feature stops the load (never live ungated)",
      "maps to no feature" in r.get("error", "") and r.get("loaded") is False, r)
rebind = os.path.join(TMP, "rebind")
os.makedirs(rebind)
Path(rebind, "__init__.py").write_text(_ns_init)
Path(rebind, "x.py").write_text("check_auth = None\n")
r = probe(rebind, empty)
check("moved code that rebinds a core name is refused, and the core name restored",
      "rebinds core names: check_auth" in r.get("error", "") and r.get("check_auth_ok") is True, r)

# The frontend half of "builds without Pro" is tests/test-community-bundle.cjs
# (frontend group: the Python CI job has no frontend node_modules).

print(f"\n{_ok} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
