#!/usr/bin/env python3
"""
`nexora backup` / `nexora restore FILE`: the same one-file backup as the panel's
Settings page (backend/backup.py), from the server's shell.

The shell path matters for two cases the panel cannot cover: a backup larger
than the web server accepts as an upload, and a new server whose panel is not
set up yet. Output is English: RTL text breaks in a Linux terminal.

usage: full-backup.py backup  [--data DIR] [--out DIR]
       full-backup.py restore FILE [--data DIR]
"""
import argparse
import os
import socket
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import backup as B  # noqa: E402


def dbs(data):
    return {"bot.db": Path(os.getenv("BOT_DB_PATH", data / "bot.db")),
            "billing.db": Path(os.getenv("BILLING_DB_PATH", data / "billing.db")),
            "tunnels.db": Path(os.getenv("TUNNEL_DB_PATH", data / "tunnels.db"))}


def version():
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("backup", "restore"))
    ap.add_argument("file", nargs="?")
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--out", default="/root/backups")
    a = ap.parse_args()
    data = Path(a.data)
    host = socket.gethostname()[:40] or "panel"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if a.cmd == "backup":
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"nexora-backup-{host}-{stamp}.zip"
        m = B.build(data, dbs(data), version(), p, host=host)
        size = p.stat().st_size / 1024 / 1024
        print(f"Backup saved: {p}  ({len(m['files'])} files, {size:.1f} MB)")
        print("It holds bot tokens: keep it somewhere private.")
        return 0
    if not a.file:
        print("restore needs a file: nexora restore /root/backups/nexora-backup-....zip")
        return 2
    safety = data / "backups" / f"before-restore-{stamp}.zip"
    safety.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = B.restore(Path(a.file), data, dbs(data), version(), safety, host=host)
    except B.BackupError as e:
        # The reason is written for the panel (Persian); say it plainly here.
        print("Restore refused. Nothing was changed.")
        print(f"Reason (as the panel shows it): {e}")
        return 1
    print(f"Restored {len(r['restored'])} files from a {r.get('from')} backup "
          f"made {r.get('createdAt')}.")
    print(f"The state before the restore is saved at: {r['safety']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
