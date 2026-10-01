#!/usr/bin/env python3
"""
`nexora sweep`: run the config cleanup now and print, shop by shop, what it
saw in 3x-ui and why it did what it did. The same function as the panel's
«همگام‌سازی با 3x-ui» button (backend/app.py `sub_sweep_report`).

Why it exists: configs deleted in 3x-ui stayed in the mini app on the owner's
server, and nothing could say why. Output is English (terminal rule), and it
prints config emails only: no names, phone numbers or tokens.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
os.environ.setdefault("CONFIG_PATH", str(DATA / "config.json"))
os.environ.setdefault("BOT_DB_PATH", str(DATA / "bot.db"))
os.environ.setdefault("BILLING_DB_PATH", str(DATA / "billing.db"))
os.environ.setdefault("XUI_DB_PATH", "/etc/x-ui/x-ui.db")
os.environ["NEXORA_NO_ADMIN_BOT"] = "1"
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "bot")]
os.chdir(ROOT / "backend")

import app  # noqa: E402

r = app.sub_sweep_report()
print(f"x-ui database: {r['xuiPath']}")
if not r["ok"]:
    print(f"STOPPED: {r['why']}")
    sys.exit(1)
print(f"configs in x-ui: {r['xuiClients']}")
for s in r["shops"]:
    kind = "reseller" if s.get("reseller") else "owner"
    print(f"\nshop #{s['id']} ({kind})")
    if s.get("error"):
        print(f"  ERROR: {s['error']}")
        continue
    print(f"  bot configs checked: {s.get('checked', 0)}")
    print(f"  decision: {s.get('why')}")
    if s.get("skipped"):
        print(f"  NOTHING MARKED: {s['skipped']}")
    print(f"  removed from the bot now: {s.get('gone', 0)}"
          f"  ended: {s.get('ended', 0)}  warned: {s.get('warned', 0)}  deleted: {s.get('deleted', 0)}")
    for e in s.get("missing") or []:
        print(f"    not in x-ui: {e}")
