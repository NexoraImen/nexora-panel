#!/usr/bin/env python3
"""
Put every client on the same Xray flow.

New configs already get xtls-rprx-vision: it is the default in the panel
client both the bot and the reseller portal use. Older configs, or ones
made by hand in x-ui, can be missing it — and a REALITY config without
the flow does not connect.

This reports which clients are missing it, and with --fix sets it.

Output is English on purpose: right-to-left text mixes badly with
left-to-right terminal output.

    python3 scripts/fix-flow.py
    python3 scripts/fix-flow.py --fix
"""
import argparse
import glob
import json
import os
import sqlite3
import sys

G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")

WANT = "xtls-rprx-vision"

XUI_PATHS = ["/etc/x-ui/x-ui.db", "/usr/local/x-ui/x-ui.db",
             "/usr/local/x-ui/bin/x-ui.db", "/etc/x-ui/db/x-ui.db"]

#: فقط این پروتکل‌ها flow می‌خواهند. گذاشتنش روی بقیه بی‌معنا و مضر است.
FLOW_PROTOCOLS = {"vless"}


def _find():
    for p in XUI_PATHS:
        if os.path.exists(p):
            return p
    hits = glob.glob("/etc/x-ui/*.db") or glob.glob("/usr/local/x-ui/*.db")
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser(description="Align Xray flow across clients")
    ap.add_argument("--fix", action="store_true",
                    help="actually write the flow (default: report only)")
    ap.add_argument("--flow", default=WANT, help=f"flow to set (default {WANT})")
    a = ap.parse_args()

    path = _find()
    if not path:
        print(R + "x-ui.db not found" + X)
        sys.exit(1)
    print(D + f"db: {path}" + X)

    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row

    # کدام اینباندها vless هستند — فقط آن‌ها flow می‌خواهند
    vless = set()
    try:
        for r in con.execute("SELECT id, protocol FROM inbounds"):
            if (r["protocol"] or "").lower() in FLOW_PROTOCOLS:
                vless.add(r["id"])
    except Exception as e:
        print(R + f"cannot read inbounds: {str(e)[:100]}" + X)
        sys.exit(1)
    print(D + f"vless inbounds: {sorted(vless) or '-'}" + X)

    cols = {r[1] for r in con.execute("PRAGMA table_info(clients)")}
    if "clients" not in {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}:
        print(R + "no clients table - this panel is an older build" + X)
        sys.exit(1)
    if "flow" not in cols:
        print(R + "clients table has no flow column" + X)
        sys.exit(1)

    has_ib = "inbound_id" in cols
    sel = "email, flow" + (", inbound_id" if has_ib else "")
    rows = [dict(r) for r in con.execute(f"SELECT {sel} FROM clients")]

    missing, wrong, fine, skipped = [], [], 0, 0
    for r in rows:
        if has_ib and vless and r.get("inbound_id") not in vless:
            skipped += 1
            continue
        f = (r.get("flow") or "").strip()
        if not f:
            missing.append(r["email"])
        elif f != a.flow:
            wrong.append((r["email"], f))
        else:
            fine += 1

    print()
    print(Y + "-- flow --" + X)
    print(G + f"  {fine} already on {a.flow}" + X)
    if skipped:
        print(D + f"  {skipped} skipped (not a vless inbound)" + X)
    if missing:
        print(R + f"  {len(missing)} have no flow at all" + X)
        for e in missing[:12]:
            print(D + f"      {e}" + X)
        if len(missing) > 12:
            print(D + f"      ... and {len(missing) - 12} more" + X)
    if wrong:
        print(Y + f"  {len(wrong)} are on a different flow" + X)
        for e, f in wrong[:12]:
            print(D + f"      {e}: {f}" + X)

    todo = len(missing) + len(wrong)
    if not todo:
        print()
        print(G + "nothing to do" + X)
        con.close()
        return

    if not a.fix:
        print()
        print(Y + f"run again with --fix to set {a.flow} on {todo} clients" + X)
        con.close()
        return

    names = missing + [e for e, _f in wrong]
    try:
        con.executemany("UPDATE clients SET flow=? WHERE email=?",
                        [(a.flow, e) for e in names])
        con.commit()
    except Exception as e:
        print(R + f"write failed: {str(e)[:120]}" + X)
        con.close()
        sys.exit(1)
    con.close()

    print()
    print(G + f"set {a.flow} on {todo} clients" + X)
    print(Y + "restart x-ui so it reloads the config:" + X)
    print(D + "  x-ui restart" + X)


if __name__ == "__main__":
    main()
