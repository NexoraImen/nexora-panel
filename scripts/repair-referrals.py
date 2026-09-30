#!/usr/bin/env python3
"""
Pay the referral coins that wallet purchases never paid.

The bot tells people: any friend who comes through your link and buys
earns you N coins. It does not mention how the friend pays.

But the reward only ran on the card-approval path. A friend who paid from
their wallet balance, or whose subscription renewed automatically, earned
their inviter nothing. The sales-partner commission covered all three
paths; the referral reward covered one.

The code now pays on all three. This finds the people who were promised
coins before that and never got them.

Coins are a discount, so this hands out real value. It shows what it would
pay and writes nothing unless you pass --apply.

Output is English on purpose: right-to-left text mixes badly with
left-to-right terminal output.

    python3 scripts/repair-referrals.py            # show who is owed
    python3 scripts/repair-referrals.py --apply    # pay them

Running it twice is safe: paying goes through the same once-per-friend
rule the bot uses, so a second run finds nothing.
"""
import argparse
import glob
import os
import sys

G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "bot"))

BOT_PATHS = [
    os.getenv("BOT_DB_PATH") or "",
    "/opt/nexora/data/bot.db",
    "/opt/nexora-panel/data/bot.db",
    "/root/nexora/data/bot.db",
    os.path.join(ROOT, "data", "bot.db"),
]

#: Friends who bought something real and whose inviter was never paid.
#
#  Trial plans are excluded: taking the free trial is not buying, and the
#  promise was about buying.
OWED = """
    SELECT u.id          AS friend_id,
           u.tg_id       AS friend_tg,
           u.first_name  AS friend_name,
           u.referred_by AS inviter_id,
           r.tg_id       AS inviter_tg,
           r.first_name  AS inviter_name,
           (SELECT MIN(o.id) FROM orders o
              LEFT JOIN plans p ON p.id = o.plan_id
             WHERE o.user_id = u.id AND o.status = 'approved'
               AND COALESCE(p.is_trial, 0) = 0) AS order_id
      FROM users u
      JOIN users r ON r.id = u.referred_by
     WHERE u.tenant_id = ?
       AND u.referred_by IS NOT NULL
       AND EXISTS (SELECT 1 FROM orders o
                     LEFT JOIN plans p ON p.id = o.plan_id
                    WHERE o.user_id = u.id AND o.status = 'approved'
                      AND COALESCE(p.is_trial, 0) = 0)
       AND NOT EXISTS (SELECT 1 FROM coin_tx c
                        WHERE c.tenant_id = u.tenant_id
                          AND c.kind = 'referral'
                          AND c.ref_user_id = u.id)
     ORDER BY u.id
"""


def _find_db():
    for p in BOT_PATHS:
        if p and os.path.exists(p):
            return p
    hits = glob.glob("/opt/*/data/bot.db")
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser(
        description="Pay referral coins that wallet purchases never paid.")
    ap.add_argument("--apply", action="store_true",
                    help="actually pay them (default: show only)")
    args = ap.parse_args()

    path = _find_db()
    if not path:
        print(R + "bot.db not found" + X)
        return 1
    os.environ["BOT_DB_PATH"] = path

    import core                                       # noqa: E402
    import db as botdb                                # noqa: E402

    botdb.DB_PATH = __import__("pathlib").Path(path)
    print(D + "bot : " + path + X)
    print()

    total_coins = 0
    total_people = 0

    for t in botdb.all_tenants():
        tid = t["id"]
        settings = botdb.tenant_settings(tid)
        cs = core.coin_settings(settings.get("coins"))
        amount = int(cs.get("per_referral") or 0)

        tdb = botdb.TenantDB(tid)
        try:
            rows = tdb.q(OWED, (tid,))
        except Exception as e:
            print(R + "tenant %s: %s" % (tid, str(e)[:100]) + X)
            continue
        if not rows:
            continue

        label = t.get("name") or ("tenant %s" % tid)
        if amount <= 0:
            print(Y + "%s: %d owed, but the referral rate is 0 - skipped"
                  % (label, len(rows)) + X)
            print(D + "  Set a rate in the bot's coin settings first." + X)
            print()
            continue

        print(G + "%s  -  %d coins each" % (label, amount) + X)
        print(D + "    %-11s %-18s %-12s %s"
              % ("inviter", "name", "friend", "order") + X)
        paid_here = 0
        for r in rows:
            inv = (r["inviter_name"] or "")[:16]
            fri = (r["friend_name"] or "")[:16]
            mark = " "
            if args.apply:
                ok = tdb.reward_referral(
                    r["inviter_id"], r["friend_id"], amount,
                    "پاداش معرفی — خرید %s" % (fri or r["friend_tg"]),
                    order_id=r["order_id"])
                mark = "+" if ok else "."
                if ok:
                    paid_here += 1
            print("  %s %-11s %-18s %-12s #%s"
                  % (mark, r["inviter_tg"], inv, fri, r["order_id"]))
        n = paid_here if args.apply else len(rows)
        total_people += n
        total_coins += n * amount
        print(D + "  %d %s %s, %d coins"
              % (n, "person" if n == 1 else "people",
                 "paid" if args.apply else "owed", n * amount) + X)
        print()

    if not total_people:
        print(G + "Nobody is owed referral coins." + X)
        return 0

    print(D + "=" * 52 + X)
    print("%s: %d %s, %d coins"
          % ("paid" if args.apply else "would pay", total_people,
             "person" if total_people == 1 else "people", total_coins))
    print()
    if not args.apply:
        print(Y + "Nothing written. Re-run with --apply to pay them." + X)
        print(D + "  Coins are a discount, so this gives away real value - "
                  "your call." + X)
    return 0


if __name__ == "__main__":
    sys.exit(main())
