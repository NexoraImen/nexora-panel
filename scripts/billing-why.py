#!/usr/bin/env python3
"""
Why is a config billed as "no rate"?

Runs on the server and puts the three deciding facts side by side:

  1. the rates recorded for each billing group
  2. the group names as they actually appear in x-ui, and whether they
     match the recorded keys
  3. the real quota of each group's configs, and which rate it matches

Output is English on purpose: Persian right-to-left text mixes badly with
left-to-right terminal output, and this is meant to be copied and pasted.

No password, token, customer name or phone number is printed.

Run:  python3 scripts/billing-why.py
"""
import glob
import json
import os
import sqlite3
import sys

G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")

BILLING_PATHS = [
    "/opt/nexora/data/billing.db",
    "/opt/nexora-panel/data/billing.db",
    "/root/nexora/data/billing.db",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "billing.db"),
]
XUI_PATHS = ["/etc/x-ui/x-ui.db", "/usr/local/x-ui/x-ui.db",
             "/usr/local/x-ui/bin/x-ui.db", "/etc/x-ui/db/x-ui.db"]


def _find(paths, extra_glob=None):
    for p in paths:
        if os.path.exists(p):
            return p
    if extra_glob:
        hits = glob.glob(extra_glob)
        if hits:
            return hits[0]
    return None


def _open(path):
    con = sqlite3.connect("file:" + path + "?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _gb_of(total):
    """The same conversion the billing code does."""
    try:
        total = int(total or 0)
    except (TypeError, ValueError):
        return 0
    return total // (1024 ** 3) if total > 1024 else total


def _price_for(gb, rates):
    """
    Mirrors backend/app.py _price_with_reason, so what this prints is
    what the panel will actually charge.
    """
    valid = []
    for r in rates or []:
        try:
            valid.append((int(r.get("gb", -1)), int(r.get("price", 0))))
        except (TypeError, ValueError, AttributeError):
            continue
    if not valid:
        return None, "no readable rate for this group"

    for g, price in valid:
        if g == gb:
            return price, None

    if gb > 0:
        higher = sorted((v for v in valid if v[0] > gb), key=lambda v: v[0])
        if higher:
            return higher[0][1], None
        vol = [v for v in valid if v[0] > 0]
        if vol:
            return max(vol, key=lambda v: v[0])[1], None
        flat = [v for v in valid if v[0] == 0]
        if flat:
            return flat[0][1], None
        return None, "no rate in this group applies to " + str(gb) + " GB"

    vol = [v for v in valid if v[0] > 0]
    if vol:
        return max(vol, key=lambda v: v[0])[1], None
    return None, "no usable rate for this group"


def main():
    bpath = _find(BILLING_PATHS, "/opt/*/data/billing.db")
    xpath = _find(XUI_PATHS)

    if not bpath:
        print(R + "billing.db not found" + X)
        sys.exit(1)
    if not xpath:
        print(R + "x-ui.db not found" + X)
        sys.exit(1)

    print(D + "billing: " + bpath + X)
    print(D + "x-ui:    " + xpath + X + "\n")

    # ── 1) recorded rates ──
    con = _open(bpath)
    conf = {}
    try:
        for r in con.execute("SELECT * FROM group_config"):
            d = dict(r)
            try:
                d["_rates"] = json.loads(d.get("rates") or "[]")
            except Exception:
                d["_rates"] = []
            conf[d["group_key"]] = d
    finally:
        con.close()

    print(Y + "-- groups configured in billing --" + X)
    if not conf:
        print("  " + R + "none configured" + X)
    for k, d in sorted(conf.items()):
        parts = []
        for r in d["_rates"]:
            try:
                g = int(r.get("gb", 0) or 0)
            except (TypeError, ValueError):
                g = 0
            parts.append(("unlimited" if g == 0 else str(g) + "GB")
                         + "=" + str(r.get("price")))
        rt = ", ".join(parts) or (R + "NO RATES" + X)
        print("  [" + k + "]  billable=" + ("yes" if d.get("billable") else "no")
              + "  rates: " + rt)
        if d.get("per_gb"):
            print("      " + Y + "per-GB rate " + str(d["per_gb"])
                  + " is set - the tiered rates above are IGNORED" + X)
        if d.get("settled_until"):
            print("      " + D + "settled until " + str(d["settled_until"])
                  + " - anything before is not counted" + X)
        if d.get("period_start"):
            print("      " + D + "period starts " + str(d["period_start"]) + X)

    # ── 2) real groups in x-ui ──
    con = _open(xpath)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(clients)")}
        if "group_name" not in cols:
            print("\n" + R + "clients table has no group_name column - "
                  "this panel is an older build" + X)
            sys.exit(1)
        # The quota column is named differently across x-ui builds. Pick it
        # off the schema, like the backend does, instead of guessing.
        qcol = next((c for c in ("total_gb", "total", "totalGB") if c in cols),
                    None)
        if not qcol:
            print("\n" + R + "no quota column in clients - found: "
                  + ", ".join(sorted(cols)) + X)
            sys.exit(1)
        rows = [{"group_name": r[0], "total": r[1], "enable": r[2]}
                for r in con.execute(
                    "SELECT group_name, " + qcol + ", enable FROM clients")]
    finally:
        con.close()

    groups = {}
    for r in rows:
        g = r.get("group_name") or ""
        groups.setdefault(g, []).append(r)

    print("\n" + Y + "-- real groups in x-ui --" + X)
    billed = unpriced = unconfigured = 0

    for g, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        shown = g if g else "(no group)"
        known = g in conf
        mark = (G + "configured" + X) if known else (R + "NOT in billing" + X)
        print("  [" + shown + "] - " + str(len(items)) + " configs  " + mark)

        if not known:
            unconfigured += len(items)
            near = [k for k in conf if k.strip().lower() == g.strip().lower()]
            if near:
                print("      " + R + "but [" + near[0] + "] is configured - "
                      "differs only by spacing or letter case" + X)
            continue

        d = conf[g]
        if not d.get("billable"):
            print("      " + D + "billing is OFF for this group" + X)
            continue
        if d.get("per_gb"):
            print("      " + D + "billed per GB used, not per config" + X)
            continue

        buckets = {}
        for it in items:
            gb = _gb_of(it.get("total"))
            buckets[gb] = buckets.get(gb, 0) + 1

        for gb, n in sorted(buckets.items()):
            price, why = _price_for(gb, d["_rates"])
            label = "unlimited" if gb == 0 else str(gb) + "GB"
            if price is None:
                unpriced += n
                print("      " + R + "X  " + str(n) + " x " + label
                      + ": " + why + X)
            else:
                billed += price * n
                print("      " + G + "OK " + str(n) + " x " + label
                      + " -> " + format(price, ",") + X)

    print("\n" + Y + "-- summary --" + X)
    print("  monthly total for configured groups: "
          + format(billed, ",") + " toman")
    if unpriced:
        print("  " + R + str(unpriced) + " configs still have no rate" + X)
    else:
        print("  " + G + "every config in a configured group has a rate" + X)
    if unconfigured:
        print("  " + Y + str(unconfigured)
              + " configs are in groups with no billing setup at all" + X)

    print("\n" + D + "No customer name, phone number or password is in this "
          "output." + X)


if __name__ == "__main__":
    main()
