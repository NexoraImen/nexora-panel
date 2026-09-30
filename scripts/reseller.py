#!/usr/bin/env python3
"""
Reseller portal accounts.

Creates or updates the login a reseller uses for their own panel, so they
never need the owner's x-ui.

Output is English on purpose: right-to-left text mixes badly with
left-to-right terminal output.

    python3 scripts/reseller.py list
    python3 scripts/reseller.py set <name> --slug hossein --group "Hossein dehlagi"
    python3 scripts/reseller.py set <name> --password 'something-long'
    python3 scripts/reseller.py off <name>
"""
import argparse
import glob
import os
import secrets
import sqlite3
import sys

G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")

DB_PATHS = [
    os.getenv("BOT_DB_PATH") or "",
    "/opt/nexora/data/bot.db",
    "/opt/nexora-panel/data/bot.db",
    "/root/nexora/data/bot.db",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "bot.db"),
]

COLS = (("portal_slug", "TEXT"), ("portal_pass", "TEXT"),
        ("portal_enabled", "INTEGER DEFAULT 0"), ("portal_group", "TEXT"))


def _db():
    for p in DB_PATHS:
        if p and os.path.exists(p):
            break
    else:
        hits = glob.glob("/opt/*/data/bot.db")
        p = hits[0] if hits else None
    if not p:
        print(R + "bot.db not found" + X)
        sys.exit(1)
    con = sqlite3.connect(p, timeout=10)
    con.row_factory = sqlite3.Row
    # ستون‌ها با نوع درست. portal_enabled اگر TEXT ساخته شود، عدد ۱
    # به رشته‌ی '1' تبدیل می‌شود و '1' = 1 در SQLite غلط است — یعنی
    # هیچ نماینده‌ای نمی‌تواند وارد شود.
    have = {r[1] for r in con.execute("PRAGMA table_info(tenants)")}
    for col, typ in COLS:
        if col not in have:
            con.execute(f"ALTER TABLE tenants ADD COLUMN {col} {typ}")
    con.commit()
    return con, p


def cmd_list(con, _a):
    rows = con.execute(
        "SELECT id, name, portal_slug, portal_group, portal_enabled, "
        "is_active, credit FROM tenants ORDER BY id").fetchall()
    if not rows:
        print(D + "no tenants" + X)
        return
    print(Y + "-- tenants --" + X)
    for r in rows:
        on = str(r["portal_enabled"] or "0") not in ("0", "", "None")
        mark = (G + "portal ON" + X) if on else (D + "portal off" + X)
        if not r["is_active"]:
            mark = R + "DISABLED" + X
        print(f"  [{r['id']}] {r['name']}  {mark}")
        print(D + f"      link: /r/{r['portal_slug'] or '-'}   "
              f"group: {r['portal_group'] or '-'}   "
              f"credit: {r['credit']}" + X)
        if on and not r["portal_group"]:
            print(R + "      no group set - this reseller sees nothing" + X)


def _find(con, name):
    r = con.execute(
        "SELECT * FROM tenants WHERE name=? OR portal_slug=? OR id=?",
        (name, name, name if str(name).isdigit() else -1)).fetchone()
    if not r:
        print(R + f"no tenant matches '{name}'" + X)
        sys.exit(1)
    return r


def cmd_set(con, a):
    t = _find(con, a.name)
    sets, vals, said = [], [], []

    if a.slug:
        clean = "".join(ch for ch in a.slug.strip().lower()
                        if ch.isalnum() or ch in "-_")[:32]
        if not clean:
            print(R + "invalid slug" + X)
            sys.exit(1)
        taken = con.execute(
            "SELECT name FROM tenants WHERE portal_slug=? AND id<>?",
            (clean, t["id"])).fetchone()
        if taken:
            print(R + f"slug '{clean}' already belongs to {taken['name']}" + X)
            sys.exit(1)
        sets.append("portal_slug=?")
        vals.append(clean)
        said.append(f"link /r/{clean}")

    if a.group is not None:
        sets.append("portal_group=?")
        vals.append(a.group.strip())
        said.append(f"group '{a.group.strip()}'")

    pw = a.password
    if a.generate:
        pw = secrets.token_urlsafe(12)
    if pw:
        if len(pw) < 8:
            print(R + "password must be at least 8 characters" + X)
            sys.exit(1)
        sets.append("portal_pass=?")
        vals.append(pw)
        said.append("password set")

    if not sets:
        print(R + "nothing to change" + X)
        sys.exit(1)

    sets.append("portal_enabled=?")
    vals.append(1)
    vals.append(t["id"])
    con.execute(f"UPDATE tenants SET {', '.join(sets)} WHERE id=?", vals)
    con.commit()

    print(G + f"updated {t['name']}: " + ", ".join(said) + X)
    if a.generate:
        print(Y + f"  password: {pw}" + X)
        print(D + "  shown once - copy it now" + X)

    row = con.execute("SELECT portal_slug, portal_group, portal_pass "
                      "FROM tenants WHERE id=?", (t["id"],)).fetchone()
    if not row["portal_group"]:
        print(R + "  warning: no group set - this reseller will see nothing" + X)
    if not row["portal_pass"]:
        print(R + "  warning: no password set - they cannot log in" + X)


def cmd_off(con, a):
    t = _find(con, a.name)
    con.execute("UPDATE tenants SET portal_enabled=0 WHERE id=?", (t["id"],))
    con.commit()
    print(G + f"portal closed for {t['name']}" + X)
    print(D + "open sessions are dropped on their next request" + X)


def main():
    ap = argparse.ArgumentParser(description="Nexora reseller portal accounts")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="show tenants and their portal state")

    s = sub.add_parser("set", help="create or update a reseller login")
    s.add_argument("name", help="tenant name, slug, or id")
    s.add_argument("--slug", help="the link: /r/<slug>")
    s.add_argument("--group", help="their x-ui group name")
    s.add_argument("--password")
    s.add_argument("--generate", action="store_true",
                   help="make a random password and print it once")

    o = sub.add_parser("off", help="close a reseller's portal")
    o.add_argument("name")

    a = ap.parse_args()
    con, path = _db()
    print(D + f"db: {path}" + X)
    try:
        {"list": cmd_list, "set": cmd_set, "off": cmd_off}[a.cmd](con, a)
    finally:
        con.close()


if __name__ == "__main__":
    main()
