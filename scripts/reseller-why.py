#!/usr/bin/env python3
"""
Why can't this reseller sell?

Walks the whole path a reseller needs, in order, and stops pointing at
the first thing that is missing. Built after a run of bug reports that
all sounded the same ("the reseller can't create a plan") but were four
different causes:

  - the portal login was never enabled
  - no x-ui group, so the rate lookup returned 409
  - the plan editor opened on an empty state with no add button
  - no mini-app url, so the button never appeared in their bot

Each of those needs a different fix, and none of them is visible from
the panel. This puts all of them on one screen.

Output is English on purpose: Persian right-to-left text mixes badly
with left-to-right terminal output, and this is meant to be copied and
pasted.

No password, token, customer name or phone number is printed.

Run:  python3 scripts/reseller-why.py
      python3 scripts/reseller-why.py --name hossein
      python3 scripts/reseller-why.py --set-miniapp https://panel.example.com

The mini-app url is normally written the first time the owner opens the
panel over https. On installs where that never happens -- an older nginx
block that does not forward the proto header, or a panel opened over
plain http -- it stays empty and nothing says why. --set-miniapp writes
it directly, for every tenant.
"""
import argparse
import glob
import json
import os
import sqlite3
import sys

G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")

BOT_PATHS = [
    os.getenv("BOT_DB_PATH") or "",
    os.getenv("BOT_DB") or "",
    "/opt/nexora/data/bot.db",
    "/opt/nexora-panel/data/bot.db",
    "/root/nexora/data/bot.db",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "bot.db"),
]
BILLING_PATHS = [
    os.getenv("BILLING_DB") or "",
    "/opt/nexora/data/billing.db",
    "/opt/nexora-panel/data/billing.db",
    "/root/nexora/data/billing.db",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "billing.db"),
]


def _find(paths, pattern=None):
    for p in paths:
        if p and os.path.exists(p):
            return p
    for hit in sorted(glob.glob(pattern or "")):
        return hit
    return None


def _open(path, write=False):
    uri = f"file:{path}" if write else f"file:{path}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def set_miniapp(bot_path, url):
    """
    آدرسِ مینی‌اپ را برای **همه‌ی** مستاجرها می‌نویسد.

    یکی برای همه درست است: مستاجر از روی امضای توکنِ ربات تشخیص
    داده می‌شود، نه از روی آدرس.
    """
    url = url.strip().rstrip("/")
    if not url.lower().startswith("https://"):
        print(f"{R}the url must start with https://{X}")
        print("Telegram rejects anything else -- and rejects the whole")
        print("message, not just the button.")
        return 2
    if not url.lower().endswith("/app"):
        url = url + "/app"

    con = _open(bot_path, write=True)
    try:
        rows = con.execute("SELECT id, name, settings FROM tenants").fetchall()
        changed = kept = 0
        for r in rows:
            try:
                st = json.loads(r["settings"] or "{}")
            except (TypeError, ValueError):
                st = {}
            if not isinstance(st, dict):
                st = {}
            if str(st.get("miniapp_url") or "").strip() == url:
                kept += 1
                continue
            st["miniapp_url"] = url
            con.execute("UPDATE tenants SET settings=? WHERE id=?",
                        (json.dumps(st, ensure_ascii=False), r["id"]))
            changed += 1
        con.commit()
    finally:
        con.close()

    print()
    print(f"  {G}{url}{X}")
    print(f"  written for {changed} tenant(s), {kept} already had it")
    print()
    print("  Bots pick this up within about half a minute. If the button")
    print("  still does not show, the bot thread has not restarted yet:")
    print("      nexora bot restart")
    print()
    return 0


def _settings(row):
    try:
        st = json.loads(row["settings"] or "{}")
    except (TypeError, ValueError):
        return {}
    return st if isinstance(st, dict) else {}


def _cols(con, table):
    try:
        return {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


#: هر قدم: (برچسب, آیا درست است؟, چه چیزی دیده شد, چه باید کرد)
#: ترتیب مهم است — اولین قرمز، همان چیزی است که باید درست شود.
def addon_price(con):
    """قیمتِ «پوسته‌ی شخصی» از تنظیماتِ مالک. صفر یعنی رایگان."""
    try:
        r = con.execute("SELECT settings FROM tenants WHERE parent_id IS NULL "
                        "ORDER BY id LIMIT 1").fetchone()
        cfg = _settings(r or {}).get("portal_addon") or {}
        return max(0, int(cfg.get("price") or 0))
    except (sqlite3.Error, TypeError, ValueError):
        return 0


def theme_open(st, price):
    """آیا پوسته‌ی شخصیِ این نماینده باز است؟"""
    if price <= 0:
        return True
    until = str(st.get("theme_until") or "")
    if not until:
        return False
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(until[:19]) > _dt.now()
    except (TypeError, ValueError):
        return False


def steps_for(con, bcon, t, cols):
    st = _settings(t)
    out = []

    # ۱. ورود به پنل
    enabled = bool(t["portal_enabled"]) if "portal_enabled" in cols else False
    slug = (t["portal_slug"] if "portal_slug" in cols else "") or ""
    has_pass = bool((t["portal_pass"] if "portal_pass" in cols else "") or "")
    out.append((
        "portal login",
        enabled and slug and has_pass,
        f"enabled={enabled} slug={slug or '-'} password={'set' if has_pass else 'MISSING'}",
        "panel > reseller panel > open their row and set a link and password",
    ))

    # ۲. گروه x-ui — برای کف قیمت و دیدنِ کانفیگ‌ها
    group = (t["portal_group"] if "portal_group" in cols else "") or ""
    out.append((
        "x-ui group",
        bool(group),
        group or "not set",
        "panel > reseller panel > pick their group from the list. "
        "Without it their bot refuses to build configs (a config with no "
        "group is billed to nobody), the price floor is unknown, and they "
        "see no configs.",
    ))

    # ۳. نرخ‌ها — کفِ قیمت از این می‌آید
    rates = []
    if group and bcon is not None:
        try:
            row = bcon.execute(
                "SELECT rates FROM group_config WHERE group_key=?",
                (group,)).fetchone()
            rates = json.loads((row["rates"] if row else "") or "[]")
        except (sqlite3.Error, TypeError, ValueError):
            rates = []
    out.append((
        "rates for that group",
        bool(rates),
        f"{len(rates)} tier(s)" if rates else "none",
        "panel > billing > resellers and rates. Without rates their "
        "invoice is zero and the plan editor cannot show a price floor.",
    ))

    # ۴. ربات تلگرام
    token = (t["bot_token"] or "") if "bot_token" in cols else ""
    out.append((
        "telegram bot",
        bool(token),
        f"@{t['bot_username']}" if token and t["bot_username"] else
        ("connected" if token else "not connected"),
        "the reseller connects it themselves: their panel > my bot",
    ))

    # ۵. مینی‌اپ
    mini = str(st.get("miniapp_url") or "")
    out.append((
        "mini-app url",
        mini.lower().startswith("https://"),
        mini or "not set",
        "open the OWNER panel once over https — it writes this for every "
        "tenant. Needs nexora >= 1.80.0.",
    ))

    # ۶. پلن‌ها
    n_plans = 0
    try:
        n_plans = con.execute(
            "SELECT COUNT(*) c FROM plans WHERE tenant_id=?",
            (t["id"],)).fetchone()["c"]
    except sqlite3.Error:
        n_plans = -1
    out.append((
        "plans",
        n_plans > 0,
        f"{n_plans} plan(s)" if n_plans >= 0 else "table missing",
        "their panel > bot plans > create first plan",
    ))

    # ۷. چیزی برای فروش
    priced = 0
    try:
        priced = con.execute(
            "SELECT COUNT(*) c FROM plans WHERE tenant_id=? AND price>0 "
            "AND is_active=1", (t["id"],)).fetchone()["c"]
    except sqlite3.Error:
        priced = 0
    out.append((
        "an active, priced plan",
        priced > 0,
        f"{priced} of {max(n_plans, 0)}",
        "a plan with price 0 is free; set a price above the floor",
    ))

    # ── پلنِ زیرِ کف ──────────────────────────────────────────────
    #
    # ذخیره‌ی پلنِ زیرِ کف رد می‌شود، ولی اگر مالک بعداً نرخ را بالا
    # ببرد، پلن‌های قبلی زیرِ کفِ تازه می‌افتند و هر فروششان ضرر است.
    try:
        under = con.execute(
            "SELECT COUNT(*) c FROM plans WHERE tenant_id=? AND is_active=1 "
            "AND COALESCE(cost,0)>0 AND price<cost", (t["id"],)).fetchone()["c"]
    except sqlite3.Error:
        under = 0
    out.append((
        "plans above the floor",
        under == 0,
        "all" if under == 0 else f"{under} active plan(s) priced below cost",
        "they lose money on every sale of those plans. Their panel > bot "
        "plans shows the floor and the loss next to each one.",
    ))

    # ── پول: کارت ─────────────────────────────────────────────────
    #
    # ربات کارت را از تنظیماتِ خودِ نماینده می‌خواند. بدونش هر خرید با
    # کارت و هر شارژِ کیف پول می‌ایستد — یعنی ربات هیچ راهی برای
    # گرفتنِ پول ندارد.
    cards = [c for c in (st.get("cards") or [])
             if isinstance(c, dict) and c.get("number") and c.get("active", True)]
    out.append((
        "payment card",
        bool(cards),
        f"{len(cards)} active" if cards else "none",
        "their panel > my bot > payment cards. Without one, every card "
        "purchase and every wallet top-up stops at 'no card number yet'.",
    ))

    # ── رسید: به کسی می‌رسد؟ ─────────────────────────────────────
    owner_tg = t["owner_tg_id"] if "owner_tg_id" in cols else None
    group_id = t["admin_group_id"] if "admin_group_id" in cols else None
    if group_id:
        where = f"admin group {group_id}"
    elif owner_tg:
        where = f"private chat {owner_tg}"
    else:
        where = "NOBODY"
    out.append((
        "receipts reach someone",
        bool(group_id or owner_tg),
        where,
        "their panel > my bot > 'link me to the bot', then Start in Telegram. "
        "Until then receipts from their customers are seen by no one.",
    ))

    # ── پیش‌پرداخت: کفِ ذخیره‌شده ──────────────────────────────────
    #
    # نماینده‌ی پیش‌پرداخت با هر فروش `plans.cost` از اعتبارش کم
    # می‌شود. پلنی که پیش از ۱.۸۶ ذخیره شده این ستون را صفر دارد، پس
    # فروشش از اعتبار چیزی کم نمی‌کند (صورتحساب هنوز می‌شماردش).
    try:
        credit = int(t["credit"]) if "credit" in cols and t["credit"] is not None else -1
    except (TypeError, ValueError):
        credit = -1
    if credit >= 0:
        try:
            zero = con.execute(
                "SELECT COUNT(*) c FROM plans WHERE tenant_id=? AND is_active=1 "
                "AND COALESCE(cost,0)=0", (t["id"],)).fetchone()["c"]
        except sqlite3.Error:
            zero = -1
        out.append((
            "prepaid: plan floors stored",
            zero == 0,
            ("all active plans have a floor" if zero == 0 else
             "cost column missing - update nexora" if zero < 0 else
             f"{zero} active plan(s) with no stored floor"),
            "they open their panel > bot plans and press save once; the "
            "floor is computed and stored. Until then those sales do not "
            "reduce their credit (the invoice still counts them).",
        ))

    # ── هویتِ فروشگاه ───────────────────────────────────────────────
    #
    # اینها نماینده را از فروش بازنمی‌دارند، ولی بدونشان مشتریِ او
    # یک فروشگاهِ بی‌نام می‌بیند — و اگر لوگو نباشد، صفحه‌ی ورود هم
    # چیزی برای نشان‌دادن ندارد.
    brand = str(st.get("brand") or "").strip()
    out.append((
        "shop name",
        bool(brand),
        brand or "not set",
        "their panel > theme > shop name. Without it the customer sees "
        "a nameless shop.",
    ))

    accent = str(st.get("mini_accent") or "").strip()
    palette = str(st.get("mini_palette") or ("custom" if accent else "")).strip()
    tpl = str(st.get("mini_tpl") or "").strip()
    price = addon_price(con)
    unlocked = theme_open(st, price)

    # پوسته دو شرط دارد و هر دو باید دیده شوند: انتخاب شده؟ و اجازه
    # هست؟ نبودِ هر کدام نتیجه‌اش یکی است — پوسته اعمال نمی‌شود — ولی
    # کارِ لازم فرق می‌کند. از ۱.۸۸ قالب و پالت هم هست، نه فقط رنگ.
    chosen = bool(tpl or palette)
    desc = (f"template={tpl or 'aurora'} palette={palette or 'default'}"
            + (f" {accent}" if palette == "custom" else ""))
    if not chosen:
        why, fix = ("no template or palette chosen",
                    "their panel > mini-app theme > pick, then save")
    elif not unlocked:
        why, fix = (f"{desc} chosen but the theme add-on is locked",
                    "panel > reseller panel > shop theme > open it for them, "
                    "or they buy it from their own panel")
    else:
        why, fix = (desc, "")
    out.append(("shop theme", chosen and unlocked, why, fix or "nothing to do"))

    return out


def main():
    ap = argparse.ArgumentParser(description="Why can't a reseller sell?")
    ap.add_argument("--name", help="only this reseller (name or slug)")
    ap.add_argument("--set-miniapp", metavar="URL", dest="set_miniapp",
                    help="write the mini-app url for every tenant")
    args = ap.parse_args()

    bot = _find(BOT_PATHS, "/opt/*/data/bot.db")
    if not bot:
        print(f"{R}bot.db not found{X} — set BOT_DB_PATH and try again")
        return 2
    billing = _find(BILLING_PATHS, "/opt/*/data/billing.db")

    if args.set_miniapp:
        return set_miniapp(bot, args.set_miniapp)

    con = _open(bot)
    bcon = _open(billing) if billing else None
    cols = _cols(con, "tenants")

    try:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM tenants WHERE parent_id IS NOT NULL ORDER BY id")]
    except sqlite3.Error as e:
        print(f"{R}cannot read tenants:{X} {e}")
        return 2

    if args.name:
        want = args.name.strip().lower()
        rows = [r for r in rows
                if want in str(r.get("name") or "").lower()
                or want in str(r.get("portal_slug") or "").lower()]

    # آدرسِ مینی‌اپِ خودِ مالک: اگر آن هم خالی باشد، مشکل از
    # نماینده نیست — پنل هیچ‌وقت روی https باز نشده و تشخیصِ
    # خودکار اصلاً فعال نشده.
    owner_mini = ""
    try:
        orow = con.execute(
            "SELECT settings FROM tenants WHERE parent_id IS NULL "
            "ORDER BY id LIMIT 1").fetchone()
        owner_mini = str(_settings(orow or {}).get("miniapp_url") or "")
    except sqlite3.Error:
        owner_mini = ""

    print()
    print(f"{D}bot.db     {X}{bot}")
    print(f"{D}billing.db {X}{billing or '(not found — rates unknown)'}")
    print(f"{D}owner mini-app {X}{owner_mini or R + 'not set' + X}")
    _price = addon_price(con)
    print(f"{D}theme add-on   {X}"
          + ("free for everyone" if _price <= 0
             else f"{_price:,} toman — resellers must buy it"))
    if not owner_mini:
        print(f"{Y}  the owner has no mini-app url either.{X}")
        print("  That means the panel was never opened over https, so the")
        print("  address was never learned. Set it once, by hand:")
        print(f"      {D}nexora reseller-why --set-miniapp https://<your-panel>{X}")
    print()

    if not rows:
        print(f"{Y}no resellers found.{X}")
        print("A reseller is a tenant with a parent. Create one in")
        print("panel > reseller panel > new reseller.")
        return 0

    blocked = 0
    for t in rows:
        label = t.get("name") or f"#{t['id']}"
        steps = steps_for(con, bcon, t, cols)
        bad = [s for s in steps if not s[1]]

        head = f"{G}ready{X}" if not bad else f"{R}blocked{X}"
        print(f"  {label}  ({head})")
        for name, ok, seen, _fix in steps:
            mark = f"{G}ok {X}" if ok else f"{R}NO {X}"
            print(f"    {mark} {name:<24} {D}{seen}{X}")

        if bad:
            blocked += 1
            # فقط **اولین** مانع. بقیه ممکن است نتیجه‌ی همین باشند.
            name, _ok, _seen, fix = bad[0]
            print()
            print(f"    {Y}fix this first:{X} {name}")
            for line in fix.split(". "):
                if line.strip():
                    print(f"      {line.strip().rstrip('.')}.")
        print()

    total = len(rows)
    if blocked:
        print(f"{R}{blocked} of {total} reseller(s) cannot sell yet.{X}")
    else:
        print(f"{G}all {total} reseller(s) are ready to sell.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
