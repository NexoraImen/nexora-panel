#!/usr/bin/env python3
"""
The one-file backup (docs/specs/2026-10-01-admin-bot-backup-ui.md, part A).

A backup is needed once, and that once it has to restore everything: this
builds a realistic data/ folder (three databases, one with rows still in its
WAL; settings; receipts in subfolders), backs it up, restores it into an empty
folder and compares every file and every row. Then the refusals: a tampered
file, a file from a newer panel, a path that climbs out of data/, and no
safety copy. And the real endpoints, through ASGI behind the admin path.

Run: python tests/test-full-backup.py
"""
import asyncio
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="fullbak_")
DATA = Path(TMP) / "data"
DATA.mkdir()
os.environ.update(
    BOT_DB_PATH=str(DATA / "bot.db"), BILLING_DB_PATH=str(DATA / "billing.db"),
    TUNNEL_DB_PATH=str(DATA / "tunnels.db"), NEXORA_ADMIN_PASSWORD="testpw",
    CONFIG_PATH=str(DATA / "config.json"), ADMIN_PATH_FILE=str(DATA / "admin_path.json"))
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


import backup as B                                         # noqa: E402

DBS = {n: DATA / n for n in B.DBS}


def make_db(path, rows, keep_open=False):
    c = sqlite3.connect(str(path))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
    c.executemany("INSERT INTO t (v) VALUES (?)", [(r,) for r in rows])
    c.commit()
    if keep_open:
        return c
    c.close()


def rows(path):
    c = sqlite3.connect(str(path))
    try:
        return [r[0] for r in c.execute("SELECT v FROM t ORDER BY id")]
    finally:
        c.close()


# A connection kept open with autocheckpoint off: the rows live only in the
# -wal file, as on a busy server. A plain file copy would lose them.
_bot = make_db(DATA / "bot.db", [f"order-{i}" for i in range(50)], keep_open=True)
make_db(DATA / "billing.db", ["payment 190000", "payment 3440000"])
make_db(DATA / "tunnels.db", ["tunnel fi"])
(DATA / "config.json").write_text('{"downloadApps": []}', encoding="utf-8")
(DATA / "auth.json").write_text('{"hash": "x"}', encoding="utf-8")
(DATA / "admin_path.json").write_text('{"path": "abc"}', encoding="utf-8")
(DATA / "license_state.json").write_text('{"state": "active"}', encoding="utf-8")
(DATA / "receipts").mkdir()
(DATA / "receipts" / "o12.jpg").write_bytes(b"\xff\xd8receipt")
(DATA / "chat" / "7").mkdir(parents=True)
(DATA / "chat" / "7" / "m1.jpg").write_bytes(b"\xff\xd8chat")
(DATA / "logos").mkdir()
(DATA / "logos" / "shop.png").write_bytes(b"\x89PNGlogo")
# things that must stay out
(DATA / "bot-before-restore-20260101.db").write_bytes(b"old")
(DATA / "config.backup.20260101.json").write_text("{}", encoding="utf-8")
(DATA / "backups").mkdir()
(DATA / "backups" / "old.zip").write_bytes(b"PK")

# ═══════════════════════════════════════════════════════════
head("Build")
# ═══════════════════════════════════════════════════════════
Z = Path(TMP) / "b.zip"
m = B.build(DATA, DBS, "2.0.0", Z, host="nexora-s1")
names = {e["path"] for e in m["files"]}
check("all three databases are in", {"bot.db", "billing.db", "tunnels.db"} <= names, sorted(names))
check("settings, admin path and license are in",
      {"config.json", "auth.json", "admin_path.json", "license_state.json"} <= names)
check("receipts, chat photos and logos, with their folders",
      {"receipts/o12.jpg", "chat/7/m1.jpg", "logos/shop.png"} <= names)
check("old backups and safety copies stay out",
      not any(n.startswith("backups") or "before-restore" in n or "config.backup" in n
              for n in names), sorted(names))
with zipfile.ZipFile(Z) as zf:
    zf.extract("bot.db", Path(TMP) / "peek")
check("rows still in the WAL are in the backup (backup API, not a file copy)",
      len(rows(Path(TMP) / "peek" / "bot.db")) == 50)
_bot.close()

# ═══════════════════════════════════════════════════════════
head("Restore into an empty server")
# ═══════════════════════════════════════════════════════════
NEW = Path(TMP) / "new"
NEW.mkdir()
NDBS = {n: NEW / n for n in B.DBS}
out = B.restore(Z, NEW, NDBS, "2.0.2", Path(TMP) / "safety.zip")
check("every file came back", set(out["restored"]) == names, out["restored"])
check("every row of every database",
      rows(NEW / "bot.db") == rows(DATA / "bot.db")
      and rows(NEW / "billing.db") == ["payment 190000", "payment 3440000"]
      and rows(NEW / "tunnels.db") == ["tunnel fi"])
same = all((NEW / n).read_bytes() == (DATA / n).read_bytes()
           for n in names if n not in B.DBS)
check("every other file byte for byte", same)
check("a safety copy of the state before was written", (Path(TMP) / "safety.zip").exists())

# a restore over a live database with an open connection: the open reader
# sees the restored rows, not a corrupt file
live = sqlite3.connect(str(NEW / "billing.db"))
live.execute("SELECT * FROM t").fetchall()
make_db(NEW / "billing.db", ["added after the backup"])
B.restore(Z, NEW, NDBS, "2.0.2", Path(TMP) / "safety2.zip")
check("restore over an open connection: that connection reads the backup's rows",
      [r[0] for r in live.execute("SELECT v FROM t ORDER BY id")] == ["payment 190000", "payment 3440000"])
live.close()

# ═══════════════════════════════════════════════════════════
head("Refusals")
# ═══════════════════════════════════════════════════════════


def refused(zpath, version="2.0.2", safety=None):
    try:
        B.restore(zpath, NEW, NDBS, version, safety or Path(TMP) / "s.zip")
        return None
    except B.BackupError as e:
        return str(e)


def rezip(src, dst, change=None, extra=None, manifest=None):
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst, "w") as b:
        for n in a.namelist():
            data = a.read(n)
            if n == "manifest.json" and manifest:
                data = json.dumps(manifest(json.loads(data))).encode()
            if change and n == change[0]:
                data = change[1]
            b.writestr(n, data)
        for n, data in (extra or {}).items():
            b.writestr(n, data)


before = rows(NEW / "billing.db")
T1 = Path(TMP) / "tampered.zip"
rezip(Z, T1, change=("billing.db", b"not a database"))
why = refused(T1)
check("a file that does not match its checksum is refused, by name",
      why and "billing.db" in why, why)
check("… and nothing was touched", rows(NEW / "billing.db") == before)

T2 = Path(TMP) / "newer.zip"
rezip(Z, T2, manifest=lambda mm: {**mm, "version": "2.1.0"})
why = refused(T2)
check("a backup from a newer panel is refused, both versions named",
      why and "2.1.0" in why and "2.0.2" in why, why)

T3 = Path(TMP) / "slip.zip"
evil = b"x"
rezip(Z, T3, extra={"../evil.sh": evil}, manifest=lambda mm: {**mm, "files": mm["files"] + [
    {"path": "../evil.sh", "size": 1, "sha256": hashlib.sha256(evil).hexdigest()}]})
why = refused(T3)
check("a path that climbs out of data/ is refused", why and "evil" in why, why)
check("… and was not written", not (Path(TMP) / "evil.sh").exists())

T4 = Path(TMP) / "notzip.zip"
T4.write_bytes(b"hello")
check("not a zip: a sentence, not a stack trace", "zip" in (refused(T4) or ""))

_orig = B.build
B.build = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
why = refused(Z)
B.build = _orig
check("no safety copy, no restore", why and "نسخه‌ی امن" in why, why)

# ═══════════════════════════════════════════════════════════
head("The panel's endpoints, through ASGI behind the admin path")
# ═══════════════════════════════════════════════════════════
import app as AP                                          # noqa: E402

AP.BOT_DB, AP.BILLING_DB = DATA / "bot.db", DATA / "billing.db"
AP._svc = lambda action, unit="nexora-bot": (True, "")


def call(path, headers=None, method="GET", body=b""):
    scope = {"type": "http", "http_version": "1.1", "method": method, "path": path,
             "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "scheme": "https", "server": ("panel.test", 443), "client": ("203.0.113.9", 5555),
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
    out = {"body": b""}
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
            out["headers"] = dict(msg.get("headers") or [])
        elif msg["type"] == "http.response.body":
            out["body"] += msg.get("body", b"")

    asyncio.run(AP.app(scope, receive, send))
    return out["status"], out["body"], out.get("headers", {})


H = {"X-Admin-Password": AP._INTERNAL_PW, "X-Admin-Path": AP.admin_path()}
st, _, _ = call("/api/admin/backup/full", {"X-Admin-Password": AP._INTERNAL_PW})
check("without the admin path: 404", st == 404, st)
st, body, hd = call("/api/admin/backup/full", H)
check("download: a zip with a dated name", st == 200 and body[:2] == b"PK"
      and b"nexora-backup-" in hd.get(b"content-disposition", b""), st)
with zipfile.ZipFile(io.BytesIO(body)) as zf:
    got = set(zf.namelist())
check("… holding the databases and the receipts", {"bot.db", "billing.db", "receipts/o12.jpg"} <= got)
check("a copy stays in data/backups/", any((DATA / "backups").glob("nexora-backup-*.zip")))

make_db(DATA / "billing.db", ["after download"])
st, b2, _ = call("/api/admin/backup/full/restore",
                 {**H, "Content-Type": "application/zip"}, "POST", body)
res = json.loads(b2)
check("upload restores and says what", st == 200 and "billing.db" in res["restored"]
      and res["botRestarted"], b2[:200])
check("… the row added after the backup is gone", "after download" not in rows(DATA / "billing.db"))
st, b3, _ = call("/api/admin/backup/full/restore", {**H, "Content-Type": "application/zip"},
                 "POST", T1.read_bytes())
check("a tampered upload: 400 with the reason", st == 400 and "billing.db" in b3.decode(), b3[:160])
for i in range(12):
    AP.full_backup_file()
check("data/backups/ keeps the ten newest", len(list((DATA / "backups").glob("nexora-backup-*.zip"))) <= 10)

print(f"\n{_ok} passed, {_fail} failed")
sys.exit(1 if _fail else 0)
