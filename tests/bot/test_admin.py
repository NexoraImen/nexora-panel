#!/usr/bin/env python3
"""
تست پنل مدیریت داخل ربات.

این تست‌ها جریان واقعی را از دکمه تا نتیجه دنبال می‌کنند — نه فقط
صدا زدن مستقیم توابع. چند باگ (تشخیص ادمین، chat_id تعریف‌نشده)
دقیقاً به این دلیل پیدا شدند که مسیر کامل تست شد.

اجرا:  python3 test_admin.py
"""

import json
import os
# repo root and bot/ — these tests moved from bot/ to tests/bot/ (2.0 layout)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOT_DIR = os.path.join(_ROOT_DIR, "bot")

import sys
import tempfile

sys.path.insert(0, _BOT_DIR)
os.environ.setdefault("BOT_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

import db as DB          # noqa: E402
import handlers as H     # noqa: E402

PASS = FAIL = 0
SENT = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def section(t):
    print(f"\n{'─' * 52}\n{t}\n{'─' * 52}")


class FakeBot:
    def send(self, cid, txt, keyboard=None, **k):
        SENT.append({"to": cid, "t": txt, "kb": keyboard})
        return {"message_id": len(SENT)}

    def send_msg(self, cid, txt, **k):
        SENT.append({"to": cid, "t": txt})
        return {"message_id": len(SENT)}

    def edit(self, cid, mid, txt, keyboard=None, **k):
        SENT.append({"to": cid, "t": txt, "kb": keyboard})
        return {"message_id": mid}

    def send_photo(self, cid, photo, caption=None, keyboard=None, **k):
        SENT.append({"to": cid, "t": caption or "[عکس]", "photo": True})
        return {"message_id": len(SENT)}

    def answer_cb(self, *a, **k):
        return True

    def __getattr__(self, n):
        return lambda *a, **k: {"message_id": 1}


def setup():
    DB.init_db()
    tid = DB.create_tenant("Nexora", "123:ABC")
    # آیدی به‌صورت رشته ذخیره می‌شود — دقیقاً مثل فرم پنل
    DB.update_tenant(tid, owner_tg_id="555")

    with DB.conn() as cx:
        cx.execute(
            "INSERT INTO users (tenant_id,tg_id,first_name,ref_code) VALUES (?,?,?,?)",
            (tid, 555, "مدیر", "ADM"))
        cx.execute(
            "INSERT INTO users (tenant_id,tg_id,first_name,username,ref_code,coins,balance) "
            "VALUES (?,?,?,?,?,?,?)",
            (tid, 777, "علی", "ali", "REF1", 45, 0))
        cx.execute(
            "INSERT INTO plans (tenant_id,name,gb,days,price,is_active) VALUES (?,?,?,?,?,1)",
            (tid, "استاندارد", 60, 30, 250000))
        cx.execute(
            "INSERT INTO orders (tenant_id,user_id,plan_id,amount,base_amount,status) "
            "VALUES (?,?,?,?,?,?)",
            (tid, 2, 1, 250000, 250000, "awaiting"))
    return tid


def main():
    tid = setup()
    tenant = DB.get_tenant(tid)
    D = DB.TenantDB(tid)

    def click(data, uid=555):
        SENT.clear()
        H.dispatch(tenant, FakeBot(), {"callback_query": {
            "id": "1", "data": data,
            "from": {"id": uid, "first_name": "X"},
            "message": {"message_id": 10, "chat": {"id": uid}},
        }})
        return SENT[-1]["t"] if SENT else None

    def send(text, uid=555):
        SENT.clear()
        H.dispatch(tenant, FakeBot(), {"message": {
            "message_id": 11, "text": text,
            "from": {"id": uid, "first_name": "X"},
            "chat": {"id": uid},
        }})
        return SENT[-1]["t"] if SENT else None

    print("\n" + "═" * 52)
    print("  تست پنل مدیریت ربات")
    print("═" * 52)

    # ── تشخیص ادمین ──
    section("تشخیص ادمین")
    ctx = H.Ctx(FakeBot(), tenant)
    check("owner رشته‌ای با عدد تلگرام", ctx.is_admin(555))
    check("کاربر عادی ادمین نیست", not ctx.is_admin(777))

    for val in ("555", 555, " 555 "):
        DB.update_tenant(tid, owner_tg_id=val)
        c2 = H.Ctx(FakeBot(), DB.get_tenant(tid))
        check(f"owner={val!r}", c2.is_admin(555))
    DB.update_tenant(tid, owner_tg_id="555")

    admin_u = D.get_user(555)
    normal_u = D.get_user(777)
    menu_admin = json.dumps(H.main_menu(ctx, admin_u), ensure_ascii=False)
    menu_user = json.dumps(H.main_menu(ctx, normal_u), ensure_ascii=False)
    check("دکمه پنل در منوی ادمین", "پنل مدیریت" in menu_admin)
    check("کاربر عادی دکمه ندارد", "پنل مدیریت" not in menu_user)

    # ── مسیریابی ──
    section("مسیریابی دکمه‌ها")
    for data, expect in [
        ("admin", "پنل مدیریت"),
        ("adm:orders", "رسید"),
        ("adm:o:1", "سفارش #1"),
        ("adm:users", "کاربران"),
        ("adm:u:777", "علی"),
        ("adm:stats", "آمار"),
        ("adm:plans", "پلن"),
        ("adm:bc", "همگانی"),
        ("adm:coin:777", "سکه"),
        ("adm:bal:777", "مبلغ"),
        ("adm:msg:777", "پیام"),
    ]:
        r = click(data)
        check(data, bool(r) and expect in r, (r or "پاسخی نیامد")[:34])

    # ── امنیت ──
    section("کنترل دسترسی")
    r = click("adm:orders", uid=777)
    check("کاربر عادی به رسیدها نمی‌رسد", r is None or "دسترسی" in str(r))
    r = click("adm:u:555", uid=777)
    check("کاربر عادی جزئیات نمی‌بیند", r is None or "دسترسی" in str(r))

    # ── جریان کامل: سکه ──
    section("جریان افزودن سکه")
    click("adm:coin:777")
    check("درخواست مقدار", D.get_user(555).get("state") == "adm_coin")
    send("25")
    check("سکه اعمال شد", D.get_user(777)["coins"] == 70, f"45 → {D.get_user(777)['coins']}")
    check("وضعیت پاک شد", not D.get_user(555).get("state"))
    check("کاربر مطلع شد", any(s.get("to") == 777 for s in SENT))

    # کسر
    click("adm:coin:777")
    send("-20")
    check("کسر سکه", D.get_user(777)["coins"] == 50, f"70 → {D.get_user(777)['coins']}")

    # ── جریان: کیف پول ──
    section("جریان شارژ کیف پول")
    click("adm:bal:777")
    send("50000")
    check("شارژ شد", D.get_user(777)["balance"] == 50000)

    # ── جریان: پیام همگانی ──
    section("پیام همگانی")
    click("adm:bc")
    send("سلام همگی")
    delivered = [s for s in SENT if s.get("t") == "سلام همگی"]
    check("به همه رسید", len(delivered) == 2, f"{len(delivered)} کاربر")
    check("گزارش به ادمین", any("ارسال شد" in s.get("t", "") for s in SENT))

    # ── جریان: جستجو ──
    section("جستجوی کاربر")
    click("adm:find")
    r = send("علی")
    check("نتیجه پیدا شد", bool(r) and "نتیجه" in r)
    click("adm:find")
    r = send("وجودندارد۱۲۳")
    check("بدون نتیجه هم مدیریت می‌شود", bool(r) and "یافت نشد" in r)

    # ── آمار پنل مدیریت ──
    # رگرسیون: stats() کلید revenue و open_tickets نداشت، پس
    # «فروش کل» و «تیکت باز» همیشه صفر نشان داده می‌شدند.
    section("آمار پنل مدیریت")

    st = D.stats()
    check("stats کلید فروش کل دارد", "revenue_total" in st, str(sorted(st)[:3]))
    check("stats کلید تیکت باز دارد", "open_tickets" in st)

    D.exec("INSERT INTO tickets (tenant_id,user_id,message,status) "
           "VALUES (?,?,?,'open')", (tid, D.get_user(777)["id"], "تست"))
    check("تیکت باز شمرده می‌شود", D.stats()["open_tickets"] == 1,
          str(D.stats()["open_tickets"]))

    D.exec("INSERT INTO orders (tenant_id,user_id,plan_id,amount,base_amount,status) "
           "VALUES (?,?,?,?,?,'approved')", (tid, 2, 1, 250000, 250000))
    check("فروش کل جمع می‌شود", D.stats()["revenue_total"] == 250000,
          str(D.stats()["revenue_total"]))

    r = click("adm:stats")
    check("صفحه آمار مبلغ واقعی را نشان می‌دهد",
          bool(r) and "۲۵۰،۰۰۰" in r,
          (r or "").replace("\n", " ")[-32:])

    # ── مسدودسازی ──
    section("مسدودسازی")
    click("adm:blk:777")
    check("مسدود شد", D.get_user(777)["is_blocked"] == 1)
    click("adm:blk:777")
    check("رفع مسدودی", D.get_user(777)["is_blocked"] == 0)

    # ── ورودی نامعتبر ──
    section("ورودی نامعتبر")
    click("adm:coin:777")
    r = send("سلام")
    check("عدد نامعتبر رد می‌شود", bool(r) and "معتبر" in r)
    check("سکه تغییر نکرد", D.get_user(777)["coins"] == 50)

    print("\n" + "═" * 52)
    print(f"  نتیجه:  {PASS} پاس  |  {FAIL} ناموفق")
    print("═" * 52 + "\n")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
