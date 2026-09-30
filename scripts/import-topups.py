#!/usr/bin/env python3
"""
Bring prepaid top-ups into the accounting books.

Until now two money systems ran side by side and never spoke. A postpaid
reseller pays at month end and it is stored in `payments`, which every
accounting screen reads. A prepaid reseller pays up front and it was
stored only in `credit_tx`, which none of them read.

So money that really arrived was missing from "received" and from the
profit figure, and a reseller who had already paid showed up as owing the
full amount.

New top-ups are recorded in both places from now on. This imports the ones
made before that.

Output is English on purpose: right-to-left text mixes badly with
left-to-right terminal output.

    python3 scripts/import-topups.py            # show what would be imported
    python3 scripts/import-topups.py --apply    # write them

Running it twice is safe: every imported row is tagged with the credit_tx
id it came from, and tagged rows are skipped.
"""
import argparse
import glob
import os
import sqlite3
import sys
from datetime import datetime

G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")

BOT_PATHS = [
    os.getenv("BOT_DB_PATH") or "",
    "/opt/nexora/data/bot.db",
    "/opt/nexora-panel/data/bot.db",
    "/root/nexora/data/bot.db",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "bot.db"),
]
BILL_PATHS = [
    os.getenv("BILLING_DB_PATH") or "",
    "/opt/nexora/data/billing.db",
    "/opt/nexora-panel/data/billing.db",
    "/root/nexora/data/billing.db",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "billing.db"),
]

#: A refund is credit going back because the panel call failed. It is not
#  money arriving, so it must not become a payment.
REFUND_MARK = "بازگشت"

#: How an imported row is tagged, so a second run can recognise it.
TAG = "[credit_tx #%d]"


def _open(paths, pattern, what):
    for p in paths:
        if p and os.path.exists(p):
            break
    else:
        hits = glob.glob(pattern)
        p = hits[0] if hits else None
    if not p:
        print(R + what + " not found" + X)
        sys.exit(1)
    con = sqlite3.connect(p, timeout=10)
    con.row_factory = sqlite3.Row
    return con, p


def main():
    ap = argparse.ArgumentParser(
        description="Import prepaid credit top-ups into payments.")
    ap.add_argument("--apply", action="store_true",
                    help="write the rows (default: show only)")
    args = ap.parse_args()

    bot, bot_path = _open(BOT_PATHS, "/opt/*/data/bot.db", "bot.db")
    bill, bill_path = _open(BILL_PATHS, "/opt/*/data/billing.db", "billing.db")
    print(D + "bot     : " + bot_path + X)
    print(D + "billing : " + bill_path + X)
    print()

    try:
        tables = {r["name"] for r in bot.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "credit_tx" not in tables:
            print(Y + "No credit_tx table - nothing to import." + X)
            return 0

        cols = {r[1] for r in bot.execute("PRAGMA table_info(tenants)")}
        group_col = "portal_group" if "portal_group" in cols else None
        if not group_col:
            print(R + "tenants has no portal_group column - update first." + X)
            return 1

        tenants = {r["id"]: r for r in bot.execute(
            "SELECT id, name, portal_group FROM tenants")}
        rows = [dict(r) for r in bot.execute(
            "SELECT id, tenant_id, amount, note, created_at FROM credit_tx "
            "WHERE amount > 0 ORDER BY id")]
    finally:
        bot.close()

    try:
        seen = " ".join(r[0] or "" for r in bill.execute(
            "SELECT note FROM payments"))
    except sqlite3.Error:
        seen = ""

    pending, skipped = [], []
    for r in rows:
        tag = TAG % r["id"]
        note = r["note"] or ""
        if tag in seen:
            skipped.append((r, "already imported"))
            continue
        if REFUND_MARK in note:
            skipped.append((r, "refund, not money in"))
            continue
        t = tenants.get(r["tenant_id"])
        group = ((t["portal_group"] if t else "") or "").strip()
        if not group:
            skipped.append((r, "reseller has no group set"))
            continue
        pending.append((r, group, t["name"] if t else "?"))

    if skipped:
        # The note is Persian and would wreck the column alignment this
        # whole file is English to preserve. The id is enough to find it.
        print(D + "Skipped:" + X)
        for r, why in skipped:
            print("  %s#%-5d %14s   %s%s"
                  % (D, r["id"], "{:,}".format(r["amount"]), why, X))
        print()

    if not pending:
        print(G + "Nothing to import." + X)
        return 0

    print("%-6s %-14s %14s  %-12s %s"
          % ("tx", "reseller", "amount", "date", "group"))
    print(D + "-" * 66 + X)
    total = 0
    for r, group, name in pending:
        total += r["amount"]
        print("#%-5d %-14s %14s  %-12s %s"
              % (r["id"], name[:14], "{:,}".format(r["amount"]),
                 (r["created_at"] or "")[:10], group))
    print(D + "-" * 66 + X)
    print("%-21s %14s" % ("total", "{:,}".format(total)))
    print()

    if not args.apply:
        print(Y + "Nothing written. Re-run with --apply to import." + X)
        return 0

    try:
        with bill:
            for r, group, _name in pending:
                bill.execute(
                    "INSERT INTO payments (group_key, amount, paid_at, note) "
                    "VALUES (?,?,?,?)",
                    (group, int(r["amount"]),
                     (r["created_at"] or datetime.now().isoformat())[:10],
                     ("credit top-up " + TAG % r["id"] + " "
                      + (r["note"] or ""))[:200]))
        print(G + "Imported %d payment(s), %s total."
              % (len(pending), "{:,}".format(total)) + X)
    finally:
        bill.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
