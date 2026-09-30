#!/usr/bin/env python3
"""
Why does the panel show this usage number?

Run this ON THE SERVER. It answers one question with facts instead of
guesses: is the usage figure the panel shows the real total, and if not,
why not.

It checks, in order, the four things that can go wrong:

  1. Is the running panel new enough to track usage across resets?
     (the `last_used` / `used_before` columns only exist from 1.66.0)
  2. Has the tracker ever observed these clients? A client the panel has
     never looked at has no baseline, so a reset before that moment is
     gone for good.
  3. What does x-ui report right now, and what has the panel banked from
     earlier (pre-reset) periods?
  4. Do the numbers the API would return match what x-ui holds?

Output is English on purpose: Persian right-to-left text mixes badly with
left-to-right terminal output, and this is meant to be copied and pasted.

No password, token, customer name or phone number is printed. Client
emails are shortened.

Run:  python3 scripts/usage-why.py            (all groups)
      python3 scripts/usage-why.py "group"    (one group)
"""
import glob
import os
import sqlite3
import sys
import time

G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")

GB = 1024 ** 3

BILLING_PATHS = [
    "/opt/nexora/data/billing.db",
    "/opt/nexora-panel/data/billing.db",
    "/root/nexora/data/billing.db",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "billing.db"),
]
XUI_PATHS = ["/etc/x-ui/x-ui.db", "/usr/local/x-ui/x-ui.db",
             "/usr/local/x-ui/bin/x-ui.db", "/etc/x-ui/db/x-ui.db"]
VERSION_PATHS = [
    "/opt/nexora/VERSION", "/opt/nexora-panel/VERSION", "/root/nexora/VERSION",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "VERSION"),
]


def _find(paths, extra_glob=None):
    for p in paths:
        if os.path.exists(p):
            return p
    if extra_glob:
        hits = glob.glob(extra_glob)
        if hits:
            return hits[0]
    return None


def _find_newest(paths):
    """
    The same rule backend/app.py `_xui_db_path` uses: among the files that
    exist, take the one written most recently.

    It has to be the same rule, or this tool names a file the panel is not
    actually reading - which is worse than not reporting at all. x-ui
    writes traffic every few seconds, so the newest mtime is the live
    database.
    """
    found = []
    for p in paths:
        try:
            if os.path.exists(p):
                found.append((os.stat(p).st_mtime, p))
        except OSError:
            continue
    if not found:
        return None
    found.sort(reverse=True)
    return found[0][1]


def _open(path):
    con = sqlite3.connect("file:" + path + "?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def head(t):
    print(f"\n{D}{'=' * 62}{X}\n  {t}\n{D}{'=' * 62}{X}")


def short(email, n=22):
    e = str(email or "")
    return e if len(e) <= n else e[:n - 1] + "…"


def main():
    want_group = sys.argv[1] if len(sys.argv) > 1 else None

    # ---- 1. which panel version is actually running ----
    head("1. Panel version")
    vpath = _find(VERSION_PATHS)
    version = "unknown"
    if vpath:
        try:
            version = open(vpath).read().strip()
        except OSError:
            pass
    print(f"  VERSION file : {vpath or 'not found'}")
    print(f"  version      : {version}")
    if version != "unknown":
        parts = version.split(".")
        try:
            num = tuple(int(p) for p in parts[:3])
        except ValueError:
            num = ()
        if num and num < (1, 66, 1):
            print(f"  {R}This panel predates the usage-across-resets fix "
                  f"(1.66.1).{X}")
            print(f"  {R}Nothing below will show banked usage, because the "
                  f"running code never records it.{X}")
            print(f"  {Y}Update the server first, then run this again.{X}")
        else:
            print(f"  {G}New enough to track usage across resets.{X}")

    # ---- 2. databases ----
    head("2. Databases")
    bpath = _find(BILLING_PATHS, "/opt/*/data/billing.db")
    xpath = _find_newest(XUI_PATHS)
    print(f"  billing.db   : {bpath or 'NOT FOUND'}")
    print(f"  x-ui.db      : {xpath or 'NOT FOUND'}")
    if not bpath or not xpath:
        print(f"\n  {R}Cannot continue without both databases.{X}")
        return 1

    # WAL side files must be readable or the panel sees stale/empty tables
    for suf in ("-wal", "-shm"):
        side = xpath + suf
        if os.path.exists(side):
            ok = os.access(side, os.R_OK)
            print(f"  {os.path.basename(side):<14} exists, readable={ok}"
                  + ("" if ok else f"   {R}<- panel may read stale data{X}"))

    # More than one x-ui.db on the box is the single most common cause of
    # "usage never changes and does not match the x-ui panel": the panel
    # reads a dead copy left behind by a reinstall or a migration.
    others = []
    for p in XUI_PATHS:
        if os.path.exists(p):
            try:
                st = os.stat(p)
            except OSError:
                continue
            others.append((st.st_mtime, st.st_size, p))
    if len(others) > 1:
        others.sort(reverse=True)
        print(f"\n  {R}More than one x-ui.db found:{X}")
        for mt, size, p in others:
            age = time.time() - mt
            when = (f"{int(age // 60)}m ago" if age < 3600
                    else f"{int(age // 3600)}h ago" if age < 86400
                    else f"{int(age // 86400)}d ago")
            mark = f"   {G}<- panel is using this{X}" if p == xpath else ""
            live = f"  {Y}<- newest, x-ui is writing here{X}" if p == others[0][2] else ""
            print(f"    {p:<34} {size / 1024:>8,.0f} KB  last write {when:<10}"
                  f"{mark}{live}")
        if xpath != others[0][2]:
            print(f"\n  {R}The panel is NOT reading the file x-ui writes "
                  f"to.{X}")
            print(f"  {Y}That is why the number never changes.{X}")
        else:
            print(f"\n  {Y}Two databases is the usual reason usage looks "
                  f"frozen and does{X}")
            print(f"  {Y}not match the x-ui panel - one is a leftover from a "
                  f"reinstall.{X}")
            print(f"  {D}The panel now picks the most recently written file. "
                  f"If that is{X}")
            print(f"  {D}not the right one, set the path explicitly under "
                  f"Settings & Backup.{X}")
    else:
        try:
            age = time.time() - os.stat(xpath).st_mtime
            when = (f"{int(age // 60)} minutes" if age < 3600
                    else f"{int(age // 3600)} hours")
            ok = age < 6 * 3600
            print(f"  last write   : {when} ago"
                  + ("" if ok else
                     f"   {R}<- x-ui does not seem to write here{X}"))
        except OSError:
            pass

    bcon = _open(bpath)
    xcon = _open(xpath)

    # ---- 3. is the tracker present and has it ever run ----
    head("3. Usage tracker state")
    cols = {r[1] for r in bcon.execute("PRAGMA table_info(client_seen)")}
    has_cols = {"last_used", "used_before"} <= cols
    print(f"  client_seen columns : {'present' if has_cols else 'MISSING'}")
    if not has_cols:
        print(f"  {R}The columns that bank pre-reset usage do not exist.{X}")
        print(f"  {Y}This means the running panel has never started with "
              f"1.66.0+ code.{X}")
        print(f"  {Y}Update and restart the panel, then open any accounting "
              f"page once.{X}")
        return 1

    tracked = bcon.execute(
        "SELECT COUNT(*) n FROM client_seen WHERE last_used IS NOT NULL"
    ).fetchone()["n"]
    total_seen = bcon.execute("SELECT COUNT(*) n FROM client_seen").fetchone()["n"]
    banked = bcon.execute(
        "SELECT COUNT(*) n FROM client_seen WHERE COALESCE(used_before,0) > 0"
    ).fetchone()["n"]
    banked_gb = bcon.execute(
        "SELECT COALESCE(SUM(used_before),0) s FROM client_seen"
    ).fetchone()["s"] / GB

    print(f"  clients known       : {total_seen}")
    print(f"  with a baseline     : {tracked}"
          + ("" if tracked else f"   {R}<- tracker has never run{X}"))
    print(f"  with banked usage   : {banked}   ({banked_gb:,.1f} GB total)")

    if tracked == 0:
        print(f"\n  {R}No client has a usage baseline yet.{X}")
        print(f"  {Y}The tracker records one the first time an accounting "
              f"page is opened.{X}")
        print(f"  {Y}Open the accounting dashboard once, then run this "
              f"again.{X}")
    elif banked == 0:
        print(f"\n  {Y}The tracker is running, but no traffic reset has been "
              f"observed yet.{X}")
        print(f"  {D}That is expected if nothing has been reset since the "
              f"update.{X}")
        print(f"  {D}Resets that happened BEFORE the update cannot be "
              f"recovered: x-ui keeps no history.{X}")

    # ---- 4. per-client comparison ----
    head("4. What x-ui holds vs what the panel will report")

    # Sum, do not overwrite: client_traffics has one row per (inbound,
    # email), so a client on two inbounds has two rows. Keeping only the
    # last one is what made the panel disagree with the x-ui panel.
    traffic = {}
    legs = {}
    try:
        for r in xcon.execute("SELECT email, up, down FROM client_traffics"):
            em = r["email"]
            traffic[em] = traffic.get(em, 0) + int((r["up"] or 0) + (r["down"] or 0))
            legs[em] = legs.get(em, 0) + 1
    except sqlite3.Error as e:
        print(f"  {R}cannot read client_traffics: {e}{X}")
        return 1

    multi = sum(1 for n in legs.values() if n > 1)
    if multi:
        print(f"  {D}{multi} of {len(legs)} clients appear on more than one "
              f"inbound;{X}")
        print(f"  {D}their rows are summed (before 1.66.3 only the last row "
              f"counted).{X}")

    rows = []
    try:
        cols_c = {r[1] for r in xcon.execute("PRAGMA table_info(clients)")}
        sel = "email, total_gb" + (", group_name" if "group_name" in cols_c else "")
        sel += ", reset" if "reset" in cols_c else ""
        for r in xcon.execute(f"SELECT {sel} FROM clients"):
            d = dict(r)
            rows.append((d.get("email"),
                         (d.get("group_name") or "").strip() or "(no group)",
                         int(d.get("total_gb") or 0),
                         int(d.get("reset") or 0)))
    except sqlite3.Error as e:
        print(f"  {R}cannot read clients: {e}{X}")
        return 1

    before = {r["email"]: int(r["used_before"] or 0)
              for r in bcon.execute("SELECT email, used_before FROM client_seen")}
    lastu = {r["email"]: r["last_used"]
             for r in bcon.execute("SELECT email, last_used FROM client_seen")}

    groups = {}
    shown = 0
    print(f"  {'client':<23}{'group':<18}{'now':>9}{'banked':>9}"
          f"{'total':>9}{'reset':>7}")
    print(f"  {D}{'-' * 60}{X}")
    for email, group, quota, resets in sorted(rows, key=lambda r: r[1]):
        if want_group and group != want_group:
            continue
        now = traffic.get(email, 0)
        bank = before.get(email, 0)
        tot = now + bank
        g = groups.setdefault(group, {"now": 0, "bank": 0, "n": 0})
        g["now"] += now
        g["bank"] += bank
        g["n"] += 1
        # only print rows where something is interesting, or a small db
        interesting = bank > 0 or resets > 0 or len(rows) <= 40
        if interesting and shown < 60:
            shown += 1
            flag = ""
            if resets > 0 and bank == 0:
                flag = f"  {Y}<- reset, nothing banked{X}"
            if email not in lastu or lastu.get(email) is None:
                flag = f"  {R}<- never observed{X}"
            print(f"  {short(email):<23}{short(group, 16):<18}"
                  f"{now / GB:>8.1f}G{bank / GB:>8.1f}G{tot / GB:>8.1f}G"
                  f"{resets:>7}{flag}")

    if shown == 0:
        print(f"  {D}(no rows matched){X}")

    head("5. Group totals - this is what the accounting pages show")
    print(f"  {'group':<24}{'configs':>9}{'now':>11}{'total':>11}")
    print(f"  {D}{'-' * 56}{X}")
    for group in sorted(groups):
        g = groups[group]
        tot = g["now"] + g["bank"]
        diff = f"  {G}+{(tot - g['now']) / GB:,.0f}G banked{X}" if g["bank"] else ""
        print(f"  {short(group, 22):<24}{g['n']:>9}"
              f"{g['now'] / GB:>10.1f}G{tot / GB:>10.1f}G{diff}")

    head("6. Does this match the x-ui panel?")
    print("  The x-ui panel shows, for each client:  up + down  from")
    print("  client_traffics - which is the 'now' column above.")
    print()
    print("  So a row where 'now' differs from what x-ui shows on screen")
    print("  means the two are reading different files. Check section 2.")
    print()
    print("  A row where 'total' is bigger than 'now' is expected: that is")
    print("  usage banked before a traffic reset, which x-ui itself forgets.")

    head("7. Reading this")
    print("  now     = what x-ui reports for the current period")
    print("  banked  = usage from earlier periods, saved before a reset")
    print("  total   = now + banked; this is what accounting uses from 1.66.1")
    print()
    print("  If 'total' equals 'now' everywhere and you expected more:")
    print("    - the reset happened before the panel was updated, and")
    print("      x-ui keeps no history of it, so it cannot be recovered;")
    print("    - from now on it is recorded, as long as an accounting page")
    print("      is opened at least sometimes (it refreshes every 40s while")
    print("      open).")
    print()
    print("  If a row says 'never observed', the panel has not read that")
    print("  client yet; open the accounting dashboard once.")

    bcon.close()
    xcon.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
