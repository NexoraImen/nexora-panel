#!/usr/bin/env python3
"""
Correct wallet order statuses recorded before the status fix.

An order's status is what every sales figure counts. Two paths wrote it
wrongly, in opposite directions:

  * A wallet purchase was never marked approved. The config was built and
    delivered, the order stayed `pending`, and the sweeper marked it
    `expired` half an hour later. A real sale, in no figure at all.

  * An auto-renewal was marked approved BEFORE the config was built. When
    the panel call failed the money went back but the order stayed
    approved - refunded money counted as a sale. A stuck subscription is
    retried with backoff and never abandoned, so it added several phantom
    sales a day.

The code no longer does either. This repairs the rows already written.

What identifies them: `sub_id` is set only after the panel call succeeds.
So a wallet order with a config is a real sale, and a renewal without one
is not.

Output is English on purpose: right-to-left text mixes badly with
left-to-right terminal output.

    python3 scripts/repair-orders.py            # show what would change
    python3 scripts/repair-orders.py --apply    # write it

Running it twice is safe: the second run finds nothing, because the rows
no longer match.
"""
import argparse
import glob
import os
import sqlite3
import sys

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

NOTE_SOLD = "اصلاح: فروش کیف پول که ثبت نشده بود"
NOTE_FAILED = "اصلاح: تمدید ناموفق که فروش شمرده شده بود"

#: Delivered, paid for, never marked as a sale.
#
#  Money left the wallet and none came back, and a config exists. The
#  `expired` ones are the same order after the sweeper reached it.
SOLD = """
    SELECT id, user_id, amount, kind, status, created_at
      FROM orders
     WHERE paid_from = 'wallet'
       AND status IN ('pending', 'expired')
       AND sub_id IS NOT NULL
       AND EXISTS (SELECT 1 FROM wallet_tx w
                    WHERE w.order_id = orders.id AND w.amount < 0)
       AND NOT EXISTS (SELECT 1 FROM wallet_tx w
                        WHERE w.order_id = orders.id AND w.amount > 0)
     ORDER BY id
"""

#: Counted as a sale, but no config was ever built.
#
#  Only renewals: those were the ones approved before the panel call. A
#  wallet purchase was never approved at all, so it cannot be here.
FAILED = """
    SELECT id, user_id, amount, kind, status, created_at
      FROM orders
     WHERE paid_from = 'wallet'
       AND status = 'approved'
       AND kind = 'renew'
       AND sub_id IS NULL
     ORDER BY id
"""

#: Money left the wallet, no config was built, and nothing came back.
#
#  The bot stopping between taking the money and building the config.
#  Rare, but the customer is out of pocket, so it is reported and never
#  changed: only the owner can say whether to refund or to deliver.
STRANDED = """
    SELECT id, user_id, amount, kind, status, created_at
      FROM orders
     WHERE paid_from = 'wallet'
       AND status IN ('pending', 'expired')
       AND sub_id IS NULL
       AND EXISTS (SELECT 1 FROM wallet_tx w
                    WHERE w.order_id = orders.id AND w.amount < 0)
       AND NOT EXISTS (SELECT 1 FROM wallet_tx w
                        WHERE w.order_id = orders.id AND w.amount > 0)
     ORDER BY id
"""


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


def _show(title, rows, colour):
    print(colour + title + X)
    if not rows:
        print(D + "  none" + X)
        print()
        return 0
    print(D + "  %-7s %-8s %14s  %-8s %s"
          % ("order", "user", "amount", "kind", "date") + X)
    total = 0
    for r in rows:
        total += int(r["amount"] or 0)
        print("  #%-6d %-8s %14s  %-8s %s"
              % (r["id"], r["user_id"], "{:,}".format(int(r["amount"] or 0)),
                 r["kind"] or "-", (r["created_at"] or "")[:10]))
    print(D + "  " + "-" * 50 + X)
    print("  %-16s %14s" % ("total", "{:,}".format(total)))
    print()
    return total


def main():
    ap = argparse.ArgumentParser(
        description="Repair wallet order statuses written before the fix.")
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default: show only)")
    args = ap.parse_args()

    bot, bot_path = _open(BOT_PATHS, "/opt/*/data/bot.db", "bot.db")
    print(D + "bot : " + bot_path + X)
    print()

    try:
        tables = {r["name"] for r in bot.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"orders", "wallet_tx"} <= tables:
            print(Y + "No orders/wallet_tx tables - nothing to repair." + X)
            return 0

        sold = bot.execute(SOLD).fetchall()
        failed = bot.execute(FAILED).fetchall()
        stranded = bot.execute(STRANDED).fetchall()

        gained = _show("Sales that were never counted  ->  approved",
                       sold, G)
        lost = _show("Refunded renewals counted as sales  ->  rejected",
                     failed, Y)

        if stranded:
            _show("Paid for, never delivered, never refunded  ->  "
                  "LEFT ALONE, decide yourself", stranded, R)
            print(D + "  Those are not touched. Refund from the panel, or "
                      "build the config by hand." + X)
            print()

        if not sold and not failed:
            print(G + "Nothing to repair." + X)
            return 0

        print(D + "=" * 54 + X)
        delta = gained - lost
        print("reported sales change: %s%s"
              % ("+" if delta >= 0 else "-", "{:,}".format(abs(delta))))
        print(D + "  (%s added, %s removed)"
              % ("{:,}".format(gained), "{:,}".format(lost)) + X)
        print()

        # A renewal approved before the panel call, where the panel then
        # failed, normally had its money returned. If the bot died in
        # between it did not. That money is a separate question from the
        # status, so say which rows to look at rather than guessing.
        unsure = [r["id"] for r in failed if not bot.execute(
            "SELECT 1 FROM wallet_tx WHERE order_id=? AND amount>0 LIMIT 1",
            (r["id"],)).fetchone()]
        if unsure:
            print(Y + "Check by hand: %d of those have no refund tied to "
                      "the order." % len(unsure) + X)
            print(D + "  Older refunds were not tagged with the order id, so "
                      "most are fine." + X)
            print(D + "  Orders: "
                  + ", ".join("#%d" % i for i in unsure[:20])
                  + (" ..." if len(unsure) > 20 else "") + X)
            print(D + "  The status below is right either way: no config was "
                      "built, so it was not a sale." + X)
            print()

        if not args.apply:
            print(Y + "Nothing written. Re-run with --apply to repair." + X)
            return 0

        with bot:
            for r in sold:
                bot.execute(
                    "UPDATE orders SET status='approved', "
                    "admin_note=COALESCE(admin_note, ?) WHERE id=?",
                    (NOTE_SOLD, r["id"]))
            for r in failed:
                bot.execute(
                    "UPDATE orders SET status='rejected', "
                    "admin_note=COALESCE(admin_note, ?) WHERE id=?",
                    (NOTE_FAILED, r["id"]))
        print(G + "Repaired %d order(s): %d marked approved, %d marked "
                  "rejected." % (len(sold) + len(failed), len(sold),
                                 len(failed)) + X)
    finally:
        bot.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
