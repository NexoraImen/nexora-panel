"""
لایه‌ی دیتابیس ماژول ربات.

نکته‌ی حیاتی امنیتی: هر جدولی که داده‌ی مستاجر دارد، ستون tenant_id دارد
و همه‌ی دسترسی‌ها از کلاس TenantDB می‌گذرد که خودکار فیلتر می‌کند.
این کار جلوی نشت داده بین مستاجرها را از سطح کد می‌گیرد، نه فقط با
یادآوری به برنامه‌نویس.
"""

import os
import json
import logging
import sqlite3
import secrets
import string
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import contextmanager

# ثبتِ ناموفقِ رویداد بی‌صدا رد می‌شود، ولی دست‌کم در لاگِ سرویس
# دیده شود. بدونِ این، همان except که قرار بود خطا را ببلعد خودش
# NameError می‌داد — یعنی مسیرِ جبران می‌شکست.
log = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("BOT_DB_PATH", "../data/bot.db"))

#: An order is delivered once it has a config (`sub_id`) or a Pro license
#: (`license_id`, Phase 4). Every "may this order still be claimed, rejected
#: or reverted?" check uses this one condition: a license order never gets a
#: sub_id, so a bare `sub_id IS NULL` would let a sold license be rejected,
#: reverted to awaiting, or approved (and paid out) a second time.
#: tests/test-sell-pro-core.py fails on any bare copy.
UNDELIVERED = "sub_id IS NULL AND license_id IS NULL"

#: سقفِ ردیفِ `events` در هر مستاجر. تعریفِ اصلی در `bot/events.py`
#: است؛ این‌جا فقط خوانده می‌شود تا `db` به آن ماژول وابسته نشود.
try:
    from events import MAX_ROWS as EVENT_MAX_ROWS
except ImportError:                      # وقتی به‌صورت `bot.db` بار می‌شود
    from .events import MAX_ROWS as EVENT_MAX_ROWS

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ═══ مستاجرها (هر ربات یک مستاجر) ═══
CREATE TABLE IF NOT EXISTS tenants (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    bot_token         TEXT UNIQUE,
    bot_username      TEXT,
    owner_tg_id       INTEGER,
    parent_id         INTEGER REFERENCES tenants(id) ON DELETE SET NULL,
    is_active         INTEGER DEFAULT 1,
    -- اعتبار واسطه (تومان). برای مستاجر اصلی نامحدود = -1
    credit            INTEGER DEFAULT 0,
    credit_discount   INTEGER DEFAULT 0,      -- درصد تخفیف عمده واسطه
    -- اتصال به پنل 3x-ui
    panel_url         TEXT,
    panel_user        TEXT,
    panel_pass        TEXT,
    panel_token       TEXT,
    default_inbound   INTEGER,
    -- گروه مدیریت
    admin_group_id    INTEGER,
    topics            TEXT DEFAULT '{}',      -- JSON: نگاشت نام تاپیک به id
    settings          TEXT DEFAULT '{}',      -- JSON: برند، کارت‌ها، متن‌ها
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ═══ کاربران ═══
-- ═══════════════════════════════════════════════════════
--  همکاری در فروش
--
--  با «دعوت دوستان» فرق دارد: آن سکه می‌دهد به مشتری عادی،
--  این پورسانت نقدی می‌دهد به کسی که کارش فروش است.
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS affiliates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    code        TEXT NOT NULL,
    tg_id       INTEGER,
    percent     REAL NOT NULL DEFAULT 10,
    active      INTEGER DEFAULT 1,
    note        TEXT,
    password    TEXT,                          -- هَش؛ برای ورود خودِ همکار
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, code)
);

-- هر پورسانت به یک سفارش مشخص گره خورده، تا بعداً قابل ردیابی باشد
CREATE TABLE IF NOT EXISTS affiliate_commissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    affiliate_id  INTEGER NOT NULL REFERENCES affiliates(id) ON DELETE CASCADE,
    order_id      INTEGER,
    user_id       INTEGER,
    order_amount  INTEGER NOT NULL DEFAULT 0,
    percent       REAL NOT NULL DEFAULT 0,
    commission    INTEGER NOT NULL DEFAULT 0,
    status        TEXT DEFAULT 'pending',      -- pending | paid | cancelled
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, order_id)
);

CREATE TABLE IF NOT EXISTS affiliate_payouts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    affiliate_id  INTEGER NOT NULL REFERENCES affiliates(id) ON DELETE CASCADE,
    amount        INTEGER NOT NULL,
    note          TEXT,
    paid_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_aff_code ON affiliates(tenant_id, code);
CREATE INDEX IF NOT EXISTS idx_comm_aff ON affiliate_commissions(affiliate_id, status);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tg_id         INTEGER NOT NULL,
    username      TEXT,
    first_name    TEXT,
    phone         TEXT,
    balance       INTEGER DEFAULT 0,          -- کیف پول (تومان)
    coins         INTEGER DEFAULT 0,
    ref_code      TEXT UNIQUE,
    referred_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    is_blocked    INTEGER DEFAULT 0,
    trial_used    INTEGER DEFAULT 0,
    phone_asked   INTEGER DEFAULT 0,      -- یک‌بار پرسیده‌ایم؟
    lang          TEXT DEFAULT 'fa',
    state         TEXT,                       -- وضعیت مکالمه
    state_data    TEXT DEFAULT '{}',
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen     TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, tg_id)
);
CREATE INDEX IF NOT EXISTS ix_users_tenant ON users(tenant_id, tg_id);

-- ═══ پلن‌ها ═══
CREATE TABLE IF NOT EXISTS plans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    description   TEXT DEFAULT '',
    gb            INTEGER NOT NULL,           -- 0 = نامحدود
    days          INTEGER NOT NULL,
    ip_limit      INTEGER DEFAULT 2,
    price         INTEGER NOT NULL,
    inbound_id    INTEGER,
    is_active     INTEGER DEFAULT 1,
    is_trial      INTEGER DEFAULT 0,
    sort_order    INTEGER DEFAULT 0,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_plans_tenant ON plans(tenant_id);

-- ═══ سفارش‌ها ═══
CREATE TABLE IF NOT EXISTS orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id      INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id        INTEGER REFERENCES plans(id) ON DELETE SET NULL,
    kind           TEXT DEFAULT 'new',        -- new | renew | topup
    amount         INTEGER NOT NULL,          -- مبلغ نهایی
    base_amount    INTEGER NOT NULL,          -- قبل از تخفیف
    coins_used     INTEGER DEFAULT 0,
    discount_code  TEXT,
    discount_pct   INTEGER DEFAULT 0,
    paid_from      TEXT DEFAULT 'card',       -- card | wallet
    status         TEXT DEFAULT 'pending',    -- pending|awaiting|approved|rejected|expired
    receipt_type   TEXT,                      -- photo | text
    receipt_file   TEXT,
    receipt_text   TEXT,
    card_used      TEXT,
    admin_note     TEXT,
    reviewed_by    INTEGER,
    sub_id         INTEGER,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at     TEXT,
    reviewed_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_orders_tenant ON orders(tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_orders_user ON orders(user_id);

-- ═══ اشتراک‌ها ═══
CREATE TABLE IF NOT EXISTS subscriptions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id      INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    plan_id       INTEGER REFERENCES plans(id) ON DELETE SET NULL,
    client_email  TEXT NOT NULL,              -- شناسه در 3x-ui
    client_uuid   TEXT,
    sub_url       TEXT,
    inbound_id    INTEGER,
    gb            INTEGER,
    expires_at    TEXT,
    auto_renew    INTEGER DEFAULT 0,
    is_active     INTEGER DEFAULT 1,
    notified_7d   INTEGER DEFAULT 0,
    notified_3d   INTEGER DEFAULT 0,
    notified_1d   INTEGER DEFAULT 0,
    notified_80p  INTEGER DEFAULT 0,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_subs_tenant ON subscriptions(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS ix_subs_user ON subscriptions(user_id);

-- ═══ تراکنش سکه ═══
CREATE TABLE IF NOT EXISTS coin_tx (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount      INTEGER NOT NULL,             -- مثبت = دریافت، منفی = مصرف
    kind        TEXT NOT NULL,                -- referral|spend|admin|bonus
    note        TEXT,
    ref_user_id INTEGER,
    order_id    INTEGER,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_cointx_user ON coin_tx(user_id);

-- ═══ تراکنش کیف پول ═══
CREATE TABLE IF NOT EXISTS wallet_tx (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount      INTEGER NOT NULL,
    kind        TEXT NOT NULL,                -- deposit|spend|refund|admin
    note        TEXT,
    order_id    INTEGER,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_wtx_user ON wallet_tx(user_id);

-- ═══ کد تخفیف ═══
CREATE TABLE IF NOT EXISTS discounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    code        TEXT NOT NULL,
    percent     INTEGER NOT NULL,
    max_uses    INTEGER DEFAULT 0,            -- 0 = نامحدود
    used_count  INTEGER DEFAULT 0,
    plan_id     INTEGER,
    expires_at  TEXT,
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, code)
);

-- ═══ پست‌های کانال ═══
--
-- برگه: docs/specs/2026-09-19-channel.md
--
-- `claimed_at` برای ادعای اتمی است: «همین حالا» از بک‌اند می‌رود و
-- زمان‌بندی‌شده را زمان‌بندِ ربات برمی‌دارد. بدونِ ادعا، اگر دو دورِ
-- زمان‌بند هم‌پوشانی کنند یک پست دو بار در کانال می‌نشیند — و پستِ
-- تکراری در کانال، برخلاف پیامِ تکراری، جلوی چشمِ همه می‌ماند.
--
-- `error` خالی نمی‌ماند وقتی ارسال شکست بخورد. پستی که نرفته و
-- نمی‌گوید چرا، همان مسیرِ خرابِ بی‌صداست.
CREATE TABLE IF NOT EXISTS channel_posts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    body         TEXT NOT NULL DEFAULT '',
    photo        TEXT,                       -- نامِ فایل، نه خودِ بایت‌ها
    status       TEXT DEFAULT 'draft',       -- draft|queued|sent|failed
    scheduled_at TEXT,
    claimed_at   TEXT,
    sent_at      TEXT,
    message_id   INTEGER,
    error        TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_chpost_due
    ON channel_posts(tenant_id, status, scheduled_at);

-- ═══ تیکت پشتیبانی ═══
CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message     TEXT NOT NULL,
    status      TEXT DEFAULT 'open',          -- open|answered|closed
    answer      TEXT,
    topic_msg   INTEGER,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    answered_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_tickets_tenant ON tickets(tenant_id, status);

-- ═══ صندوق پیام مشتری ═══
--
-- سه چیزِ به‌ظاهر جدا از همین‌جا می‌آیند: خبرِ تاییدِ رسید، خبرِ ردش
-- با متنِ دلیل، و گفتگو با پشتیبانی. هر سه «پیامی از یک طرف به طرف
-- دیگر با وضعیت خوانده‌نشده»‌اند؛ سه جدول یعنی سه جای جدا برای از
-- هم پاشیدن.
--
-- `sender='system'` برای خبرهای خودکار است — همان صندوق، همان نشان.
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sender      TEXT NOT NULL,              -- user | admin | system
    body        TEXT NOT NULL,
    photo       TEXT,                       -- نشانیِ عکس، اگر پیام عکس دارد
    order_id    INTEGER,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    read_at     TEXT                        -- طرفِ مقابل خواندش
);
CREATE INDEX IF NOT EXISTS ix_chat_user
    ON chat_messages(tenant_id, user_id, id);
-- شمارشِ خوانده‌نشده‌ها پرتکرارترین کوئریِ این جدول است
CREATE INDEX IF NOT EXISTS ix_chat_unread
    ON chat_messages(tenant_id, sender, read_at);

-- ═══ لاگ رویدادها (برای آمار و عیب‌یابی) ═══
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   INTEGER,
    user_id     INTEGER,
    kind        TEXT NOT NULL,
    data        TEXT DEFAULT '{}',
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_events_tenant ON events(tenant_id, kind);
"""


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=20)
    con.row_factory = sqlite3.Row

    # WAL: خواندن و نوشتن هم‌زمان همدیگر را قفل نمی‌کنند.
    #
    # در حالت پیش‌فرض (journal=delete) هر نوشتن کل دیتابیس را قفل
    # می‌کند و هر خواننده‌ای باید منتظر بماند. تا وقتی آپدیت‌ها
    # یکی‌یکی پردازش می‌شدند این دیده نمی‌شد، ولی حالا که هشت نخ
    # هم‌زمان کار می‌کنند، دقیقاً همان‌جایی است که به گلوگاه می‌خورد.
    #
    # synchronous=NORMAL در کنار WAL امن است: در برق‌رفتن، آخرین
    # تراکنش‌های commit‌شده سالم می‌مانند.
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA busy_timeout=20000")
    except sqlite3.Error as _exc:
        # روی فایل‌سیستم شبکه‌ای WAL پشتیبانی نمی‌شود — همان حالت
        # پیش‌فرض کار می‌کند، فقط کندتر
        log.warning("db migration/setup (_connect): %s", _exc)

    return con


def ensure_aff_payouts(con):
    """
    درخواستِ تسویه‌ی همکار و رسیدِ پرداخت — برگه:
    docs/specs/2026-09-28-admin-path-and-aff-payouts.md

    یک تابع و دو صداکننده: `_migrate`ِ ربات و بکند (پنل). بکند نمی‌تواند
    منتظر بماند تا ربات بعد از به‌روزرسانی اول بالا بیاید و ستون‌ها را
    بسازد؛ و نوشتنِ همین اسکیما در app.py یعنی دو نسخه که روزی از هم جدا
    می‌شوند. اجرای مکرر بی‌خطر است.
    """
    con.execute("""CREATE TABLE IF NOT EXISTS affiliate_requests (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id     INTEGER NOT NULL,
        affiliate_id  INTEGER NOT NULL,
        amount        INTEGER NOT NULL,
        dest          TEXT,
        holder        TEXT,
        note          TEXT,
        status        TEXT NOT NULL DEFAULT 'pending',  -- pending|paying|paid|rejected|cancelled
        reason        TEXT,
        payout_id     INTEGER,
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
        decided_at    TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_affreq ON affiliate_requests(affiliate_id, status)")
    for table, col, spec in (
            # مقصدِ پرداخت روی خودِ همکار می‌ماند تا دفعه‌ی بعد دوباره تایپ نشود
            ("affiliates", "pay_dest", "TEXT"),
            ("affiliates", "pay_holder", "TEXT"),
            # نامِ فایلِ رسید (نه مسیر)، و درخواستی که این پرداخت جوابِ آن است
            ("affiliate_payouts", "receipt", "TEXT"),
            ("affiliate_payouts", "request_id", "INTEGER")):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        if cols and col not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {spec}")


def _migrate(con):
    """ستون‌های جدید را به دیتابیس‌های موجود اضافه می‌کند."""
    adds = [
        ("users", "phone_asked", "INTEGER DEFAULT 0"),
        # رمزِ ورودِ خودِ همکار فروش — هَش‌شده، مثل رمز پنل.
        # بدون این، همکار برای دیدنِ طلبش باید هر بار از مالک
        # می‌پرسید.
        ("affiliates", "password", "TEXT"),
        # کدام همکار فروش این کاربر را آورده — تا پورسانت هر خریدش
        # به همان نفر برسد، نه فقط خرید اول
        ("users", "affiliate_id", "INTEGER"),
        # اینباندهای هر پلن — خالی یعنی از تنظیم سراسری پیروی کن
        ("plans", "inbound_ids", "TEXT"),
        # کِی برای این کاربر پیگیریِ تست فرستادیم.
        #
        # بدونِ پرچم، هر دورِ زمان‌بند دوباره می‌فرستد — و کسی که
        # نخریده هر ساعت یک پیامِ تبلیغاتی می‌گیرد، که بدتر از
        # نفرستادن است.
        #
        # تاریخ است نه بولین: بعداً می‌شود گفت کِی فرستاده شد و
        # نرخِ تبدیل را حساب کرد.
        ("users", "trial_followup_at", "TEXT"),
        # پیش از تستِ رایگان پرسیده می‌شوند (docs/specs/2026-09-27-shop-funnel.md)
        ("users", "operator", "TEXT"),
        ("users", "device_os", "TEXT"),
        ("users", "real_name", "TEXT"),
        # پیگیریِ تست: کِی گرفت، کدام قدم رفته، کِی خرید
        ("users", "trial_at", "TEXT"),
        # نوع (حجمی / کاربر محدود) و تبِ مدتِ پلن — مسیرِ خرید: نوع ← تب ← پلن
        ("plans", "kind", "TEXT DEFAULT 'volume'"),
        # کِی نظرسنجیِ بعد از خرید/تمدیدِ این سفارش رفت (ادعا پیش از ارسال)
        ("orders", "feedback_at", "TEXT"),
        ("plans", "tab", "TEXT DEFAULT ''"),
        ("users", "trial_step", "INTEGER DEFAULT 0"),
        ("users", "trial_bought_at", "TEXT"),
        # کدِ تخفیفی که مشتری وارد کرده ولی هنوز خرید نکرده.
        #
        # چرا ستونِ خودش و نه `state_data`: وسطِ همین مسیر حالت به
        # `await_receipt` عوض می‌شود و هر چه در state_data بود
        # می‌رود. و چرا نه داخلِ callback_data: تلگرام ۶۴ بایت سقف
        # دارد و کد تا ۴۰ کاراکتر مجاز است — `wpay:{plan}:{sub}:{code}`
        # به ۵۹ بایت می‌رسد. کار می‌کند تا روزی که نکند.
        ("users", "held_discount", "TEXT"),
        # عکسِ پیام — نشانیِ فایل، نه خودِ بایت‌ها.
        #
        # بیشترِ چیزی که مشتری در پشتیبانی می‌خواهد بگوید یک تصویر
        # است: عکسِ خطای اپلیکیشن، رسید، یا صفحه‌ای که کار نمی‌کند.
        # تا حالا باید توصیفش می‌کرد.
        #
        # چرا نشانی و نه بایت: گذاشتنِ base64 در همان ستونِ متن
        # یعنی هر بار خواندنِ گفتگو، همه‌ی عکس‌ها هم از دیتابیس
        # بیرون می‌آیند — حتی وقتی فقط شمارِ نخوانده‌ها را
        # می‌خواهیم.
        ("chat_messages", "photo", "TEXT"),
        # حالت پیش‌فرض: all | default | custom
        ("tenants", "inbound_mode", "TEXT DEFAULT 'all'"),
        ("tenants", "inbound_ids", "TEXT"),
        # نام پلن، همان‌طور که لحظه‌ی خرید بود.
        #
        # plan_id با ON DELETE SET NULL وصل است، پس اگر مدیر پلنی را
        # حذف یا جایگزین کند، نام آن اشتراک از بین می‌رود و مشتری
        # به‌جای «یک‌ماهه پرسرعت» فقط نام اینباند را می‌بیند — چیزی
        # که هیچ‌وقت نخریده. این ستون همان نام را نگه می‌دارد.
        ("subscriptions", "plan_name", "TEXT"),
        # کدام اشتراک قرار است تمدید شود.
        #
        # sub_id موجود *بعد* از ساخت پر می‌شود و نتیجه را نگه می‌دارد؛
        # این یکی مقصد را از همان لحظه‌ی ثبت سفارش مشخص می‌کند.
        ("orders", "renew_sub_id", "INTEGER"),
        # قفلِ کوتاهِ تمدید.
        #
        # extend_subscription تاریخ فعلی را از پنل می‌خواند و بعد
        # تاریخ تازه را می‌نویسد. دو تمدید هم‌زمان روی یک اشتراک —
        # دوباره زدنِ دکمه، یا تمدید خودکاری که هم‌زمان با تمدید دستی
        # اجرا شود — هر دو یک مبدأ می‌خوانند و هر دو همان یک ماه را
        # می‌نویسند. مشتری دو بار پول می‌دهد و یک ماه می‌گیرد.
        ("subscriptions", "renewing_at", "TEXT"),
        # تمدید خودکاری که شکست می‌خورد.
        #
        # تمدید خودکار هر ساعت اجرا می‌شود و شکستش معمولاً همان شکستِ
        # دفعه‌ی پیش است — پنل خواب است، پلن حذف شده، اینباند رفته.
        # بدون این دو ستون، همان خطا شبانه‌روز تکرار می‌شد: ۲۴ سفارش،
        # ۲۴ بار برداشت و بازگرداندن پول، و ۲۴ هشدار در گروه مدیریت
        # برای یک مشتری. عقب‌نشینی تدریجی جلوی سیل را می‌گیرد بی‌آنکه
        # تمدید را رها کند — چون رهاکردنش یعنی مشتری بی‌صدا قطع شود.
        ("subscriptions", "renew_fails", "INTEGER DEFAULT 0"),
        ("subscriptions", "renew_retry_at", "TEXT"),
        # Config lifecycle (docs/specs/2026-09-30-vpn-fixes.md, task 9).
        # pending_days: made with "start after first use"; the days start
        # on the first connection, so there is no expires_at until then.
        ("subscriptions", "pending_days", "INTEGER"),
        # When the sweep first saw it ended (date passed or volume used up).
        ("subscriptions", "ended_at", "TEXT"),
        ("subscriptions", "notified_del", "INTEGER DEFAULT 0"),
        # Gone from 3x-ui: deleted by the sweep, or by hand in the panel.
        ("subscriptions", "deleted_at", "TEXT"),
        ("subscriptions", "deleted_why", "TEXT"),
        # ── ورود نماینده به پنل ──
        #
        # جدا از panel_user/panel_pass که مال خودِ x-ui است و هرگز
        # نباید دست نماینده بیفتد. این‌ها فقط برای ورود به پنل
        # نکسورا هستند.
        #
        # slug همان چیزی است که در آدرس می‌آید: /r/<slug>. مسیر
        # انتخاب شد نه زیردامنه، چون زیردامنه برای هر نماینده یک
        # رکورد DNS و یک گواهی می‌خواهد و راه‌اندازی‌اش دست مدیر
        # است، نه دکمه‌ی پنل.
        ("tenants", "portal_slug", "TEXT"),
        ("tenants", "portal_pass", "TEXT"),
        ("tenants", "portal_enabled", "INTEGER DEFAULT 0"),
        # گروهی که این نماینده در x-ui دارد — کلید همه‌ی محدودسازی‌ها.
        #
        # بدون این، پنل نماینده نمی‌داند کدام کانفیگ‌ها مال اوست و
        # ناچار است یا همه را نشان بدهد یا از روی نام حدس بزند. هیچ
        # کدام قابل قبول نیست.
        ("tenants", "portal_group", "TEXT"),
        # کفِ قیمتِ پلنِ نماینده — آنچه مالک بابتِ هر فروش از او
        # می‌گیرد.
        #
        # نرخ‌ها در دیتابیسِ حسابداری‌اند و ربات به آن دسترسی ندارد.
        # پس بکند همان لحظه‌ی ذخیره‌ی پلن با همان `_line_amount` حسابش
        # می‌کند و این‌جا می‌گذارد، و ربات فقط می‌خواندش. محاسبه‌ی
        # دوم در ربات یعنی دو عدد برای یک پلن.
        ("plans", "cost", "INTEGER DEFAULT 0"),
        # Selling Pro from the owner's bot (docs/specs/2026-09-30-sell-pro.md):
        # a `pro_license` plan says which license and how many periods; the
        # order records the license it delivered (UNDELIVERED) or renews.
        ("plans", "license_plan", "TEXT DEFAULT ''"),
        ("plans", "periods", "INTEGER DEFAULT 1"),
        ("orders", "license_id", "TEXT"),
        ("orders", "renew_license", "TEXT"),
        # Who blocked whom (docs/specs/2026-10-01-admin-bot-backup-ui.md).
        # `is_blocked` used to mean both "the admin banned this person" and
        # "a broadcast found they had blocked the bot", and the bot ignores
        # anyone with it: a customer who unblocked the bot and pressed /start
        # never got an answer again. Now `is_blocked` is a ban only, with who
        # banned in `blocked_by`; `left_at` is "they blocked the bot", and it
        # clears the moment they write again.
        ("users", "blocked_by", "TEXT"),
        ("users", "left_at", "TEXT"),
        # removed by the owner or reseller: off the list, configs deleted,
        # orders kept for the accounts
        ("users", "deleted_at", "TEXT"),
        # When the receipt came (UTC, like created_at), and the one line the
        # SMS check said about it (docs/specs/2026-10-07-sms-auto-approve.md).
        # Nothing stored the receipt's time before; matching the bank's SMS
        # needs it.
        ("orders", "receipt_at", "TEXT"),
        ("orders", "sms_note", "TEXT"),
    ]
    for table, col, spec in adds:
        try:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            if col not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {spec}")
        except sqlite3.Error as _exc:
            log.warning("db migration/setup (_migrate): %s", _exc)

    try:
        ensure_aff_payouts(con)
    except sqlite3.Error as _exc:
        log.warning("db migration/setup (aff payouts): %s", _exc)

    # Pro licenses sold by this bot: what "my subscriptions" lists. The issuer
    # is the truth for expiry; this row is updated with each issue and renewal
    # so the buyer's list needs no network call.
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS pro_licenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            license_id  TEXT NOT NULL UNIQUE,
            plan        TEXT NOT NULL,
            expires     INTEGER,
            key_hint    TEXT NOT NULL DEFAULT '',
            order_id    INTEGER,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_prolic_user "
                    "ON pro_licenses(tenant_id, user_id)")
    except sqlite3.Error as _exc:
        log.warning("db migration/setup (pro_licenses): %s", _exc)

    # دفتر شارژ اعتبار نماینده‌ها.
    #
    # بدون این، تنها ردِ یک شارژ عددِ credit است — و آن عدد با هر
    # ساخت و تمدیدِ نماینده عوض می‌شود. یعنی هیچ‌وقت نمی‌شد فهمید
    # کِی و چقدر شارژ شده. برای چیزی که پول است کافی نیست.
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS credit_tx (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            amount     INTEGER NOT NULL,
            balance    INTEGER,
            note       TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_credit_tenant "
                    "ON credit_tx(tenant_id, id DESC)")
    except sqlite3.Error as _exc:
        log.warning("db migration/setup (_migrate): %s", _exc)

    # Bank deposits read from the shop's forwarded SMS
    # (docs/specs/2026-10-07-sms-auto-approve.md). Amount in toman, paid_at
    # UTC like orders.created_at; `fp` makes a resent SMS a no-op; `order_id`
    # is set once, by a conditional UPDATE, so one deposit pays one order.
    # The SMS text and the balance in it are not kept.
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS bank_deposits (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            fp         TEXT NOT NULL,
            amount     INTEGER NOT NULL,
            paid_at    TEXT NOT NULL,
            card4      TEXT,
            order_id   INTEGER,
            state      TEXT NOT NULL DEFAULT 'new',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, fp)
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_dep_open "
                    "ON bank_deposits(tenant_id, state, amount)")
        # Every SMS that reached the shop's address and what became of it,
        # ignored ones too. Without it a sender that did not match was
        # silent: the owner set it up, paid, and saw nothing (2026-10-07).
        con.execute("""CREATE TABLE IF NOT EXISTS sms_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            sender     TEXT,
            outcome    TEXT,
            at         TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        # 2.3.3: a deposit from a sender not yet trusted, offered for one tap
        lcols = [r[1] for r in con.execute("PRAGMA table_info(sms_log)")]
        for col in ("untrusted INTEGER DEFAULT 0", "amount INTEGER"):
            if col.split()[0] not in lcols:
                con.execute(f"ALTER TABLE sms_log ADD COLUMN {col}")
    except sqlite3.Error as _exc:
        log.warning("db migration/setup (bank_deposits): %s", _exc)

    # نام پلن اشتراک‌های قدیمی را از جدول پلن‌ها پر می‌کنیم.
    #
    # تا وقتی پلن هنوز هست این کار شدنی است؛ بعد از حذفش دیگر هیچ
    # جایی آن نام را ندارد. پس همین یک بار، برای هرچه موجود است.
    try:
        con.execute(
            "UPDATE subscriptions SET plan_name = ("
            "  SELECT name FROM plans WHERE plans.id = subscriptions.plan_id) "
            "WHERE (plan_name IS NULL OR plan_name = '') "
            "  AND plan_id IS NOT NULL")
    except sqlite3.Error as _exc:
        log.warning("db migration/setup (_migrate): %s", _exc)

    # وضعیتِ قدیمیِ «review» همان «awaiting» است: کدِ امروز دیگر آن را
    # نمی‌نویسد، ولی تایید و رد هنوز می‌پذیرندش.
    #
    # سه جا (فهرستِ سفارش‌ها، شمارِ داشبورد، پرتال) آن را جزوِ «در
    # انتظار» می‌شمردند و چهار جا نه (گزارشِ فروش، زنگِ هشدار، فهرست و
    # آمارِ خودِ ربات). پس یک رسید در یک صفحه منتظر بود و در صفحه‌ی
    # دیگر نبود. به‌جای اصلاحِ هفت کوئری، وضعیت یک‌بار یکی می‌شود.
    # این تایید نیست؛ فقط نامِ یک وضعیتِ در انتظار عوض می‌شود.
    try:
        cur = con.execute("UPDATE orders SET status='awaiting' WHERE status='review'")
        if cur.rowcount:
            log.info("migrated %d legacy 'review' orders to 'awaiting'", cur.rowcount)
    except sqlite3.Error as e:
        log.warning("could not migrate legacy 'review' orders: %s", e)


# ═══════════════════════════════════════════════════════════
#  همکاری در فروش
# ═══════════════════════════════════════════════════════════

def affiliate_by_code(tenant_id, code):
    """پیدا کردن همکار از روی کد — برای وقتی کاربر با لینکش می‌آید."""
    con = _connect()
    try:
        r = con.execute(
            "SELECT * FROM affiliates WHERE tenant_id=? AND code=? AND active=1",
            (tenant_id, (code or "").strip())).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def affiliate_by_tg(tenant_id, tg_id):
    con = _connect()
    try:
        r = con.execute(
            "SELECT * FROM affiliates WHERE tenant_id=? AND tg_id=? AND active=1",
            (tenant_id, tg_id)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def record_commission(tenant_id, user_id, order_id, amount):
    """
    ثبت پورسانت یک سفارش.

    فقط وقتی ثبت می‌شود که کاربر همکاری داشته باشد و برای آن
    سفارش قبلاً ثبت نشده باشد — تا اگر تاییدی دوباره اجرا شد،
    پورسانت دو بار حساب نشود.
    """
    if not amount or amount <= 0:
        return None

    con = _connect()
    try:
        # هر دو جست‌وجو به مستاجر محدود می‌شوند.
        #
        # شناسه‌ها سراسری‌اند، پس بدون این هم نتیجه درست درمی‌آمد — تا
        # روزی که صداکننده‌ای user_id یک مستاجر را با tenant_id مستاجر
        # دیگر بدهد. آن‌وقت پورسانت به همکارِ فروشگاه دیگری می‌رسید و
        # هیچ‌جا خطایی هم نمی‌داد. شرط اضافه رایگان است.
        u = con.execute(
            "SELECT affiliate_id FROM users WHERE id=? AND tenant_id=?",
            (user_id, tenant_id)).fetchone()
        if not u or not u["affiliate_id"]:
            return None

        aff = con.execute(
            "SELECT * FROM affiliates WHERE id=? AND tenant_id=? AND active=1",
            (u["affiliate_id"], tenant_id)).fetchone()
        if not aff:
            return None

        commission = round(amount * float(aff["percent"]) / 100)
        if commission <= 0:
            return None

        try:
            con.execute(
                """INSERT INTO affiliate_commissions
                   (tenant_id, affiliate_id, order_id, user_id,
                    order_amount, percent, commission)
                   VALUES (?,?,?,?,?,?,?)""",
                (tenant_id, aff["id"], order_id, user_id,
                 amount, aff["percent"], commission))
            con.commit()
        except sqlite3.IntegrityError:
            # این سفارش قبلاً ثبت شده
            return None

        return {"affiliate": dict(aff), "commission": commission}
    finally:
        con.close()


def affiliate_stats(tenant_id, affiliate_id):
    """آمار یک همکار — فروش، پورسانت، پرداختی و مانده."""
    con = _connect()
    try:
        row = con.execute(
            """SELECT COUNT(*) AS orders,
                      COALESCE(SUM(order_amount),0) AS sales,
                      COALESCE(SUM(commission),0) AS earned,
                      COALESCE(SUM(CASE WHEN status='paid' THEN commission ELSE 0 END),0) AS paid
               FROM affiliate_commissions
               WHERE tenant_id=? AND affiliate_id=? AND status != 'cancelled'""",
            (tenant_id, affiliate_id)).fetchone()

        users = con.execute(
            "SELECT COUNT(*) AS c FROM users WHERE tenant_id=? AND affiliate_id=?",
            (tenant_id, affiliate_id)).fetchone()["c"]

        payouts = con.execute(
            """SELECT COALESCE(SUM(amount),0) AS s FROM affiliate_payouts
               WHERE tenant_id=? AND affiliate_id=?""",
            (tenant_id, affiliate_id)).fetchone()["s"]

        d = dict(row)
        d["users"] = users
        d["payouts"] = payouts
        d["balance"] = d["earned"] - payouts
        return d
    finally:
        con.close()


def init_db():
    """ساخت جداول. اجرای مکرر بی‌خطر است."""
    con = _connect()
    try:
        con.executescript(SCHEMA)
        _migrate(con)
        con.commit()
    finally:
        con.close()


@contextmanager
def conn():
    con = _connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def gen_ref_code(length=6):
    """کد معرف کوتاه و خوانا (بدون کاراکترهای گیج‌کننده مثل O و 0)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ═══════════════════════════════════════════════════════════
#  TenantDB — همه‌ی دسترسی‌ها از این‌جا می‌گذرند
#  هر متد خودکار tenant_id را اعمال می‌کند تا نشت داده ممکن نباشد
# ═══════════════════════════════════════════════════════════

class TenantDB:
    # جداولی که باید حتماً با tenant_id فیلتر شوند
    SCOPED = {"users", "plans", "orders", "subscriptions",
              "coin_tx", "wallet_tx", "discounts", "tickets", "events",
              "chat_messages", "channel_posts"}

    def __init__(self, tenant_id: int):
        if not isinstance(tenant_id, int) or tenant_id <= 0:
            raise ValueError("tenant_id نامعتبر است")
        self.tid = tenant_id

    # ---------- کمکی‌های عمومی ----------
    def q(self, sql: str, params=(), one=False):
        """
        اجرای کوئری. اگر جدولی از SCOPED در FROM باشد ولی tenant_id
        در WHERE نباشد، خطا می‌دهد — محافظ در برابر اشتباه انسانی.
        """
        low = sql.lower()
        if any(f" {t}" in low for t in self.SCOPED) and "tenant_id" not in low:
            raise RuntimeError(
                f"کوئری بدون فیلتر tenant_id روی جدول محافظت‌شده: {sql[:80]}"
            )
        with conn() as c:
            cur = c.execute(sql, params)
            rows = cur.fetchall()
        if one:
            return dict(rows[0]) if rows else None
        return [dict(r) for r in rows]

    def exec(self, sql: str, params=()):
        with conn() as c:
            cur = c.execute(sql, params)
            return cur.lastrowid

    # ---------- کاربران ----------
    def get_user(self, tg_id: int):
        return self.q(
            "SELECT * FROM users WHERE tenant_id=? AND tg_id=?",
            (self.tid, tg_id), one=True
        )

    def get_user_by_id(self, uid: int):
        return self.q(
            "SELECT * FROM users WHERE tenant_id=? AND id=?",
            (self.tid, uid), one=True
        )

    def get_user_by_ref(self, code: str):
        return self.q(
            "SELECT * FROM users WHERE tenant_id=? AND ref_code=?",
            (self.tid, code.upper()), one=True
        )

    def create_user(self, tg_id, username=None, first_name=None, referred_by=None):
        # کد معرف یکتا در کل سیستم (نه فقط مستاجر) تا لینک‌ها قابل تشخیص باشند
        for _ in range(12):
            code = gen_ref_code()
            try:
                uid = self.exec(
                    """INSERT INTO users (tenant_id, tg_id, username, first_name,
                                          ref_code, referred_by)
                       VALUES (?,?,?,?,?,?)""",
                    (self.tid, tg_id, username, first_name, code, referred_by)
                )
                return self.get_user_by_id(uid)
            except sqlite3.IntegrityError as e:
                if "ref_code" in str(e):
                    continue          # برخورد کد، دوباره تلاش
                if "tg_id" in str(e) or "UNIQUE" in str(e):
                    return self.get_user(tg_id)   # کاربر از قبل هست
                raise
        raise RuntimeError("ساخت کد معرف یکتا ناموفق بود")

    def touch_user(self, tg_id):
        self.exec(
            "UPDATE users SET last_seen=CURRENT_TIMESTAMP WHERE tenant_id=? AND tg_id=?",
            (self.tid, tg_id)
        )

    def set_state(self, tg_id, state, data=None):
        self.exec(
            "UPDATE users SET state=?, state_data=? WHERE tenant_id=? AND tg_id=?",
            (state, json.dumps(data or {}, ensure_ascii=False), self.tid, tg_id)
        )

    def clear_state(self, tg_id):
        self.set_state(tg_id, None, {})

    # ---------- گزارشِ کدهای تخفیف ----------
    def discount_report(self):
        """
        سه چیزی که مالک واقعاً می‌پرسد: چقدر تخفیف دادم، کدام کد
        فروش آورد، و پیگیریِ تست جواب داد یا نه.

        **هیچ عددِ تازه‌ای ساخته نمی‌شود.** تفاوتِ `base_amount` و
        `amount` روی خودِ سفارش، همان تخفیفی است که داده شده.

        دو قاعده‌ی خودِ مخزن این‌جا هم هست:

        • **تست خرید نیست.** سفارشِ پلنِ تست با مبلغ صفر ثبت
          می‌شود؛ نشمردنش با `is_trial` است نه با مبلغ، چون سفارشِ
          صددرصد تخفیف‌خورده هم صفر است ولی تبدیل است.

        • **«فروش» با «درآمد» یکی نیست.** این‌جا فروش شمرده می‌شود
          — سفارشی که از کیف پول پرداخت شده هم فروش است، هرچند پولِ
          تازه‌ای با آن نرسیده. ستون همین را می‌گوید و ادعای درآمد
          نمی‌کند.
        """
        base = """FROM orders o
                  LEFT JOIN plans p ON p.id = o.plan_id
                 WHERE o.tenant_id = ?
                   AND o.status = 'approved'
                   AND COALESCE(p.is_trial, 0) = 0
                   AND o.discount_code IS NOT NULL
                   AND TRIM(o.discount_code) <> ''"""

        tot = self.q(
            "SELECT COUNT(*) AS orders, "
            "       COALESCE(SUM(o.amount),0) AS sales, "
            "       COALESCE(SUM(o.base_amount - o.amount),0) AS given, "
            "       COUNT(DISTINCT UPPER(TRIM(o.discount_code))) AS codes "
            + base, (self.tid,), one=True) or {}

        top = self.q(
            "SELECT UPPER(TRIM(o.discount_code)) AS code, "
            "       COUNT(*) AS orders, "
            "       COALESCE(SUM(o.amount),0) AS sales, "
            "       COALESCE(SUM(o.base_amount - o.amount),0) AS given, "
            "       MAX(o.reviewed_at) AS last_at "
            + base +
            " GROUP BY UPPER(TRIM(o.discount_code)) "
            " ORDER BY sales DESC LIMIT 8", (self.tid,))

        # ── پیگیریِ تست ──
        #
        # کدهای `BACK…` را `trial_winback` می‌سازد، هر کدام برای یک
        # نفر. پس «چندتا ساخته شده» یعنی به چند نفر پیام رفته، و
        # «چندتا استفاده شده» یعنی چند نفر برگشتند.
        wb = self.q(
            "SELECT COUNT(*) AS sent, "
            "       COALESCE(SUM(CASE WHEN used_count > 0 THEN 1 ELSE 0 END),0) "
            "         AS used "
            "  FROM discounts WHERE tenant_id=? AND code LIKE 'BACK%'",
            (self.tid,), one=True) or {}

        wbm = self.q(
            "SELECT COUNT(*) AS orders, "
            "       COALESCE(SUM(o.amount),0) AS sales, "
            "       COALESCE(SUM(o.base_amount - o.amount),0) AS given "
            + base + " AND o.discount_code LIKE 'BACK%'",
            (self.tid,), one=True) or {}

        return {
            "total": {k: int(tot.get(k) or 0)
                      for k in ("orders", "sales", "given", "codes")},
            "top": [{"code": r["code"], "orders": int(r["orders"] or 0),
                     "sales": int(r["sales"] or 0),
                     "given": int(r["given"] or 0),
                     "lastAt": r["last_at"] or ""} for r in top],
            "winback": {"sent": int(wb.get("sent") or 0),
                        "used": int(wb.get("used") or 0),
                        "orders": int(wbm.get("orders") or 0),
                        "sales": int(wbm.get("sales") or 0),
                        "given": int(wbm.get("given") or 0)},
        }

    # ---------- پست‌های کانال ----------
    def channel_posts(self, limit=50):
        return self.q(
            "SELECT * FROM channel_posts WHERE tenant_id=? "
            "ORDER BY COALESCE(sent_at, scheduled_at, created_at) DESC, id DESC "
            "LIMIT ?", (self.tid, int(limit)))

    def channel_post(self, pid):
        return self.q("SELECT * FROM channel_posts WHERE tenant_id=? AND id=?",
                      (self.tid, int(pid)), one=True)

    def channel_add(self, body, photo=None, scheduled_at=None, status="draft"):
        pid = self.exec(
            "INSERT INTO channel_posts (tenant_id, body, photo, status, "
            "scheduled_at) VALUES (?,?,?,?,?)",
            (self.tid, body or "", photo or None, status, scheduled_at or None))
        return self.channel_post(pid)

    def channel_claim(self, pid):
        """
        ادعای اتمی پیش از ارسال.

        زمان‌بند و دکمه‌ی «همین حالا بفرست» می‌توانند هم‌زمان یک پست
        را بردارند. پستِ تکراری در کانال جلوی چشمِ همه می‌ماند، پس
        اول ادعا، بعد ارسال — مثل `claim_order`.
        """
        with conn() as c:
            cur = c.execute(
                "UPDATE channel_posts SET claimed_at=CURRENT_TIMESTAMP "
                # `failed` هم هست: پستی که یک‌بار نرفته باید بشود
                # دوباره فرستادش. بدونِ آن، ادعا پس‌دادن در
                # `channel_done` بی‌اثر بود.
                "WHERE tenant_id=? AND id=? "
                "AND status IN ('draft','queued','failed') "
                "AND claimed_at IS NULL",
                (self.tid, int(pid)))
            return bool(cur.rowcount)

    def channel_done(self, pid, message_id=None, error=None):
        """نتیجه‌ی ارسال. شکست هم ثبت می‌شود، با دلیلش."""
        if error:
            # ادعا پس داده می‌شود تا تلاشِ دوباره ممکن بماند
            self.exec(
                "UPDATE channel_posts SET status='failed', error=?, "
                "claimed_at=NULL WHERE tenant_id=? AND id=?",
                (str(error)[:400], self.tid, int(pid)))
        else:
            self.exec(
                "UPDATE channel_posts SET status='sent', error=NULL, "
                "message_id=?, sent_at=CURRENT_TIMESTAMP "
                "WHERE tenant_id=? AND id=?",
                (message_id, self.tid, int(pid)))
        return self.channel_post(pid)

    # ---------- کدِ تخفیفِ در دست ----------
    #
    # «در دست» یعنی وارد شده ولی هنوز خرج نشده. سرِ ساختِ سفارش
    # داخلِ خودِ سفارش ثبت می‌شود و از این‌جا برداشته — ماندنش یعنی
    # خریدِ بعدی هم بی‌آنکه مشتری بخواهد تخفیف بگیرد.
    def set_held_discount(self, tg_id, code):
        self.exec(
            "UPDATE users SET held_discount=? WHERE tenant_id=? AND tg_id=?",
            ((str(code).strip().upper() if code else None), self.tid, tg_id))

    def held_discount(self, tg_id):
        r = self.q("SELECT held_discount FROM users WHERE tenant_id=? AND tg_id=?",
                   (self.tid, tg_id), one=True)
        return ((r or {}).get("held_discount") or "").strip()

    # ---------- سکه ----------
    def spend_coins(self, user_id, amount, kind, note=None, order_id=None):
        """
        خرج‌کردن سکه — اتمی. برمی‌گرداند: (موفق, موجودی تازه)

        چرا لازم است:
            سکه هنگام *تایید* سفارش کم می‌شد، نه هنگام ثبتش. بین آن
            دو، مشتری می‌توانست سفارش دومی با همان سکه‌ها بسازد —
            چون هنوز کم نشده بودند — و بعد هر دو تایید شوند و دو بار
            از یک موجودی برداشته شود.

            و از آن بدتر: مسیر «رد کردن سفارش» سکه را *برمی‌گرداند*،
            در حالی که اصلاً کم نشده بود. یعنی هر سفارشی که رد می‌شد
            به مشتری سکه‌ی رایگان می‌داد.

            حالا سکه همان لحظه‌ی ثبت سفارش رزرو می‌شود و فقط در رد،
            انقضا یا لغو برمی‌گردد — پس هر دو مشکل از ریشه می‌رود.
        """
        amount = abs(int(amount))
        with conn() as c:
            cur = c.execute(
                "UPDATE users SET coins = coins - ? "
                "WHERE tenant_id=? AND id=? AND coins >= ?",
                (amount, self.tid, user_id, amount)
            )
            if not cur.rowcount:
                row = c.execute(
                    "SELECT coins FROM users WHERE tenant_id=? AND id=?",
                    (self.tid, user_id)).fetchone()
                return False, (row["coins"] if row else 0)

            c.execute(
                """INSERT INTO coin_tx (tenant_id, user_id, amount, kind, note,
                                        ref_user_id, order_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (self.tid, user_id, -amount, kind, note, None, order_id)
            )
            row = c.execute(
                "SELECT coins FROM users WHERE tenant_id=? AND id=?",
                (self.tid, user_id)).fetchone()
            return True, (row["coins"] if row else 0)

    def reward_referral(self, referrer_id, referred_id, amount, note,
                        order_id=None):
        """
        پاداش معرف — یک‌بار به ازای هر دوستِ معرفی‌شده. اتمی.

        برمی‌گرداند: پرداخت شد یا نه.

        قاعده‌ی قبلی این بود: «اگر این کاربر هیچ سفارش تاییدشده‌ی
        دیگری ندارد». دو اشکال داشت.

        یکی اینکه قاعده‌ی درستی نبود — چیزی که واقعاً می‌خواهیم «یک
        پاداش برای هر دوست» است، نه «برای اولین سفارش».

        دوم اینکه بین شمردن و پرداخت فاصله بود: دو تایید هم‌زمان یا
        هر دو پاداش می‌دادند، یا — بعد از اینکه ادعای سفارش وضعیت را
        زودتر approved کرد — هیچ‌کدام.

        این‌جا شرط و درج یک دستورند، پس هیچ فاصله‌ای نمی‌ماند.
        """
        amount = int(amount or 0)
        if amount <= 0 or not referrer_id or not referred_id:
            return False

        with conn() as c:
            cur = c.execute(
                """INSERT INTO coin_tx (tenant_id, user_id, amount, kind,
                                        note, ref_user_id, order_id)
                   SELECT ?,?,?,'referral',?,?,?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM coin_tx
                         WHERE tenant_id=? AND kind='referral'
                           AND ref_user_id=?)""",
                (self.tid, referrer_id, amount, note, referred_id, order_id,
                 self.tid, referred_id))
            if not cur.rowcount:
                return False
            paid = c.execute(
                "UPDATE users SET coins = coins + ? WHERE tenant_id=? AND id=?",
                (amount, self.tid, referrer_id))
            if not paid.rowcount:
                # معرف دیگر نیست. ردیفِ پاداش را هم پس می‌گیریم، وگرنه
                # جای «یک پاداش برای هر دوست» را اشغال می‌کند بی‌آنکه
                # چیزی پرداخت شده باشد.
                c.execute("DELETE FROM coin_tx WHERE tenant_id=? AND id=?",
                          (self.tid, cur.lastrowid))
                return False
            return True

    def mark_rejected(self, order_id, admin_tg_id, reason):
        """
        رد سفارش — فقط اگر تحویل نشده باشد. برمی‌گرداند: رد شد یا نه.

        چرا شرطی: رد شدن از دو راه می‌آید — دکمه‌ی گروه مدیریت
        (داخل قفل چت) و مسیر پنل که نخ زمان‌بند اجرایش می‌کند (بیرون
        از آن قفل). و تایید هم همین دو راه را دارد.

        بدون شرط، رد و تایید می‌توانستند هم‌زمان اجرا شوند: مشتری
        کانفیگش را می‌گرفت، پیام «سفارشتان رد شد» را هم می‌گرفت، و
        سکه‌های رزروشده هم به او برمی‌گشت. سه چیز که با هم جور
        نیستند.

        سفارشی که sub_id دارد یعنی کانفیگش ساخته شده — آن دیگر رد
        نمی‌شود.
        """
        with conn() as c:
            cur = c.execute(
                """UPDATE orders
                      SET status='rejected', reviewed_by=?, admin_note=?,
                          reviewed_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=? AND id=?
                      AND status <> 'rejected' AND """ + UNDELIVERED,
                (admin_tg_id, reason, self.tid, order_id))
            return bool(cur.rowcount)

    def get_discount(self, code):
        """
        کدِ همین مستاجر — یا None.

        شرطِ `tenant_id` اختیاری نیست: بدونش مشتریِ یک نماینده کدِ
        نماینده‌ی دیگر را استفاده می‌کند و تخفیفش از جیبِ اشتباه
        می‌رود.
        """
        code = str(code or "").strip().upper()[:40]
        if not code:
            return None
        return self.q(
            "SELECT * FROM discounts WHERE tenant_id=? AND UPPER(code)=?",
            (self.tid, code), one=True)

    def attach_receipt(self, order_id, rtype, rfile, rtext):
        """
        ثبت رسید روی سفارش — فقط اگر هنوز در انتظار پرداخت باشد.

        برمی‌گرداند: ثبت شد یا نه.

        چرا شرطی: جاروکشِ سفارش‌های منقضی روی نخ زمان‌بند می‌دود و
        قفلِ چت را ندارد. اگر مشتری دقیقاً لحظه‌ی پایان مهلت رسید
        بفرستد، جاروکش سفارش را منقضی می‌کند و سکه‌های رزروشده را پس
        می‌دهد — و نوشتنِ بی‌قیدِ رسید بلافاصله سفارش را به awaiting
        برمی‌گرداند.

        نتیجه: سفارش برای تایید می‌رود، ولی سکه‌ها هم به مشتری
        برگشته‌اند. تخفیف را گرفته و سکه‌هایش را هم نگه داشته.
        """
        with conn() as c:
            cur = c.execute(
                """UPDATE orders
                      SET status='awaiting', receipt_type=?, receipt_file=?,
                          receipt_text=?, receipt_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=? AND id=? AND status='pending'""",
                (rtype, rfile, rtext, self.tid, order_id))
            return bool(cur.rowcount)

    def claim_renewal(self, sub_id, stale_minutes=5):
        """
        قفل‌کردن یک اشتراک برای تمدید. اتمی.

        قفلِ مانده بعد از چند دقیقه خودبه‌خود آزاد می‌شود، تا نخی که
        وسط کار مرد اشتراک را برای همیشه قفل نکند.
        """
        with conn() as c:
            cur = c.execute(
                """UPDATE subscriptions SET renewing_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=? AND id=?
                      AND (renewing_at IS NULL
                           OR renewing_at < datetime('now', ?))""",
                (self.tid, sub_id, f"-{int(stale_minutes)} minutes"))
            return bool(cur.rowcount)

    def renew_failed(self, sub_id, max_hours=6):
        """
        یک شکستِ تمدید خودکار را ثبت می‌کند و می‌گوید چندمین است.

        تلاش بعدی به اندازه‌ی همان شماره ساعت عقب می‌افتد، تا سقف
        max_hours. پس شکستِ پایدار به‌جای ۲۴ بار در روز، چهار پنج بار
        تلاش می‌شود — و هیچ‌وقت هم کاملاً رها نمی‌شود.
        """
        with conn() as c:
            row = c.execute(
                "SELECT COALESCE(renew_fails,0) n FROM subscriptions "
                "WHERE tenant_id=? AND id=?", (self.tid, sub_id)).fetchone()
            n = int(row["n"] if row else 0) + 1
            hours = min(n, int(max_hours))
            c.execute(
                "UPDATE subscriptions SET renew_fails=?, "
                "renew_retry_at=datetime('now', ?) "
                "WHERE tenant_id=? AND id=?",
                (n, f"+{hours} hours", self.tid, sub_id))
            return n

    def renew_succeeded(self, sub_id):
        """پرونده‌ی شکست‌ها بسته می‌شود."""
        self.exec(
            "UPDATE subscriptions SET renew_fails=0, renew_retry_at=NULL "
            "WHERE tenant_id=? AND id=?", (self.tid, sub_id))

    def release_renewal(self, sub_id):
        """آزادکردن قفل تمدید — چه موفق، چه ناموفق."""
        with conn() as c:
            c.execute("UPDATE subscriptions SET renewing_at=NULL "
                      "WHERE tenant_id=? AND id=?", (self.tid, sub_id))

    # ---------- نظرِ مشتری ----------
    #
    # یک جدول برای همه‌ی نظرسنجی‌ها (docs/specs/2026-09-27-shop-funnel.md، فاز ۳):
    #   trial8 / trial16  پیگیریِ تست (۸ و ۱۶ ساعت)
    #   buy / renew       چند روز بعد از خرید و تمدید — `ref` شماره‌ی سفارش
    # «رضایت» پیش از خرید (`satisfaction`) از همین خوانده می‌شود.

    #: نظرسنجی‌هایی که «کیفیت» را می‌پرسند (عالی/خوب/معمولی/مشکل)
    QUALITY_KINDS = ("trial8", "buy", "renew")

    @staticmethod
    def _feedback_table(c):
        c.execute("""CREATE TABLE IF NOT EXISTS feedback (
            tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            kind TEXT NOT NULL, ref TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL, text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id, kind, ref))""")
        # یک‌بار: پاسخ‌های ۱.۱۱۹ (جدولِ قدیمیِ نظرِ تست) به همین جدول.
        # نامِ جدول در متغیر است چون عمداً دیگر در اسکیما نیست و test-seams
        # هر «FROM <جدول>» لفظی را با اسکیما می‌سنجد.
        old = "trial_feedback"
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (old,)).fetchone():
            c.execute("INSERT OR IGNORE INTO feedback (tenant_id,user_id,kind,ref,answer,text,created_at) "
                      "SELECT tenant_id, user_id, 'trial' || question, '', answer, text, created_at "
                      f"FROM {old}")
            c.execute(f"DROP TABLE {old}")

    def feedback_set(self, user_id, kind, answer, ref="", text=None):
        """یک نظر — هر (کاربر، نوع، سفارش) یک ردیف؛ پاسخِ تازه جایگزین، متنِ قبلی می‌ماند."""
        with conn() as c:
            self._feedback_table(c)
            c.execute("INSERT INTO feedback (tenant_id,user_id,kind,ref,answer,text) "
                      "VALUES (?,?,?,?,?,?) ON CONFLICT(tenant_id,user_id,kind,ref) DO UPDATE "
                      "SET answer=excluded.answer, text=COALESCE(excluded.text, feedback.text), "
                      "created_at=CURRENT_TIMESTAMP",
                      (self.tid, int(user_id), str(kind), str(ref or ""), str(answer), text))

    def trial_feedback_set(self, user_id, question, answer, text=None):
        """نامِ قدیمی (۱.۱۱۹) — «8»/«16» همان trial8/trial16 است."""
        return self.feedback_set(user_id, f"trial{question}", answer, "", text)

    def satisfaction(self, min_n=10):
        """
        «چند درصد راضی‌اند» برای نشان‌دادن **پیش از خرید** — یا None.

        راضی = «عالی» یا «خوب»، از هر سه نظرسنجیِ کیفیت. زیرِ `min_n` نظر None
        است: «۱۰۰٪ از ۱ نظر» مشتری را گمراه می‌کند. ربات و مینی‌اپ هر دو از
        همین می‌خوانند — یک عدد، یک جا.
        """
        with conn() as c:
            self._feedback_table(c)
            ph = ",".join("?" * len(self.QUALITY_KINDS))
            r = c.execute(f"SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN answer IN ('great','good') "
                          f"THEN 1 ELSE 0 END),0) h FROM feedback WHERE tenant_id=? AND kind IN ({ph})",
                          (self.tid,) + self.QUALITY_KINDS).fetchone()
        n, h = int(r[0] or 0), int(r[1] or 0)
        if n < max(1, int(min_n)):
            return None
        return {"n": n, "pct": round(h * 100 / n)}

    def trial_journey_stats(self):
        """
        آمارِ نظرِ مشتری‌ها برای پنل: تست و تبدیل، پاسخ‌های هر نظرسنجی، رضایتِ
        کلی، و آخرین «مشکل داشتم»ها. فقط کاربرانِ همین فروشگاه.
        """
        with conn() as c:
            self._feedback_table(c)
            tot = c.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN trial_bought_at IS NOT NULL "
                "THEN 1 ELSE 0 END),0) b FROM users WHERE tenant_id=? AND trial_at IS NOT NULL",
                (self.tid,)).fetchone()
            ans = {}
            for r in c.execute("SELECT kind, answer, COUNT(*) n FROM feedback "
                               "WHERE tenant_id=? GROUP BY kind, answer", (self.tid,)):
                ans.setdefault(r[0], {})[r[1]] = int(r[2])
            probs = [dict(r) for r in c.execute(
                "SELECT f.kind, f.text, f.created_at, u.first_name, u.real_name, u.tg_id "
                "FROM feedback f JOIN users u ON u.id=f.user_id "
                "WHERE f.tenant_id=? AND f.answer='bad' AND f.text IS NOT NULL "
                "ORDER BY f.created_at DESC LIMIT 10", (self.tid,))]
        return {"trials": int(tot[0] or 0), "bought": int(tot[1] or 0),
                "answers": ans, "problems": probs, "satisfaction": self.satisfaction(min_n=1)}

    def next_name_seq(self, prefix=""):
        """
        شماره‌ی بعدیِ نامِ کانفیگ در این فروشگاه — اتمی.

        یک `UPDATE … RETURNING`: دو خریدِ هم‌زمان هرگز یک شماره نمی‌گیرند.
        بارِ اول از بزرگ‌ترِ «تعدادِ اشتراک‌های فروشگاه» و «بیشترین شماره‌ی
        نام‌های `پیشوند_عدد`» شروع می‌کند، تا فروشگاهِ قدیمی از ۱ شروع نکند و
        روی نامِ زنده‌ای ننشیند.
        """
        import re as _re
        with conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS name_seq ("
                      "tenant_id INTEGER PRIMARY KEY, n INTEGER NOT NULL)")
            if c.execute("SELECT 1 FROM name_seq WHERE tenant_id=?",
                         (self.tid,)).fetchone() is None:
                # همان پاک‌سازیِ `core.make_email`
                clean = "".join(ch for ch in str(prefix or "") if ch.isalnum()).lower()[:12] or "nx"
                pat = _re.compile(r"^" + _re.escape(clean) + r"_(\d+)$")
                top, count = 0, 0
                for r in c.execute("SELECT client_email FROM subscriptions WHERE tenant_id=?",
                                   (self.tid,)):
                    count += 1
                    m = pat.match(str(r[0] or ""))
                    if m:
                        top = max(top, int(m.group(1)))
                c.execute("INSERT OR IGNORE INTO name_seq (tenant_id, n) VALUES (?,?)",
                          (self.tid, max(top, count)))
            row = c.execute("UPDATE name_seq SET n = n + 1 WHERE tenant_id=? RETURNING n",
                            (self.tid,)).fetchone()
            return int(row[0])

    def claim_trial(self, user_id):
        """
        گرفتن حقِ اشتراک تست، اتمی. برمی‌گرداند: گرفته شد یا نه.

        قبلاً پرچم trial_used *بعد از* ساخت کانفیگ نوشته می‌شد، و
        بینشان یک رفت‌وبرگشت کامل با x-ui فاصله بود. دو بار زدنِ
        دکمه‌ی «تست رایگان» یعنی هر دو نخ پرچم را صفر می‌دیدند و هر
        دو کانفیگ می‌ساختند — یعنی محصول رایگان، به تعداد دفعاتی که
        کسی دکمه را می‌زد.

        این شرط از ریشه می‌بندَدش: فقط اولین نفر می‌تواند پرچم را
        از صفر به یک ببرد.
        """
        with conn() as c:
            cur = c.execute(
                "UPDATE users SET trial_used=1 "
                "WHERE tenant_id=? AND id=? AND trial_used=0",
                (self.tid, user_id))
            return bool(cur.rowcount)

    def release_trial(self, user_id):
        """
        پس‌دادن حقِ تست، وقتی ساخت کانفیگ شکست خورد.

        پیام خطا به مشتری می‌گوید «تست رایگانتان هنوز محفوظ است» —
        و این تابع همان را راست نگه می‌دارد.
        """
        with conn() as c:
            c.execute("UPDATE users SET trial_used=0 WHERE tenant_id=? AND id=?",
                      (self.tid, user_id))

    def claim_order(self, order_id, admin_tg_id, stale_minutes=5):
        """
        ادعای انحصاری یک سفارش، پیش از ساخت کانفیگ. اتمی.

        چرا لازم است: تایید سفارش اول وضعیت را می‌خواند و *بعد از*
        ساخت موفق کانفیگ آن را approved می‌کرد. فاصله‌ی بین این دو یک
        رفت‌وبرگشت کامل با x-ui است — چند ثانیه.

        ربات هشت نخ دارد و دکمه‌ی تایید در گروه مدیریت است. دو بار
        زدن، دو ادمین، یا تایید از پنل هم‌زمان با دکمه‌ی تلگرام: هر
        دو نخ نگهبان را رد می‌کنند، هر دو کانفیگ می‌سازند، و مشتری با
        یک پرداخت دو کانفیگ می‌گیرد و معرفش دو بار سکه.

        شرط اتمی این را از ریشه می‌بندد: فقط یکی می‌تواند برنده شود.

        ادعای مانده هم دوباره قابل‌گرفتن است — اگر نخی وسط ساخت مرد،
        سفارش برای همیشه گیر نمی‌کند.
        """
        with conn() as c:
            cur = c.execute(
                """UPDATE orders
                      SET status='approved', reviewed_by=?,
                          reviewed_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=? AND id=?
                      AND (status <> 'approved'
                           OR (""" + UNDELIVERED + """
                               AND (reviewed_at IS NULL
                                    OR reviewed_at <
                                       datetime('now', ?))))
                      -- ردِ تازه یعنی مسابقه، نه تصمیم.
                      --
                      -- ادمینی که سفارشی را اشتباهی رد کرده باید
                      -- بتواند بعداً تاییدش کند، پس ردِ قدیمی مانع
                      -- نیست. ولی ردی که همین چند دقیقه پیش اتفاق
                      -- افتاده، تقریباً همیشه یعنی مسیر پنل و دکمه‌ی
                      -- گروه با هم اجرا شده‌اند — و نتیجه‌اش مشتری‌ای
                      -- است که هم پیام رد می‌گیرد هم کانفیگ.
                      AND NOT (status = 'rejected'
                               AND reviewed_at IS NOT NULL
                               AND reviewed_at >= datetime('now', ?))""",
                (admin_tg_id, self.tid, order_id,
                 f"-{int(stale_minutes)} minutes",
                 f"-{int(stale_minutes)} minutes"))
            return bool(cur.rowcount)

    #: وضعیت‌هایی که یعنی «فروش نشد» — پول باید برگردد.
    #
    #  approved عمداً این‌جا نیست: سفارشِ تاییدشده یعنی کانفیگ تحویل
    #  شده، و پس‌دادنِ پولِ آن یعنی هدیه‌دادنِ اشتراک.
    REFUND_ON = ("rejected", "expired", "cancelled")

    def close_order(self, order_id, status, note=None, from_status="pending"):
        """
        بستنِ یک سفارشِ باز — تنها راهِ درست عوض‌کردن وضعیت.
        برمی‌گرداند: (ادعا برنده شد, مبلغی که به کیف پول برگشت)

        چرا یک تابع، نه دو تا:
            وضعیتِ سفارش و پولِ سفارش یک چیزند. هر جا این دو از هم
            جدا نوشته شدند، از هم دور افتادند:

            • خرید با کیف پول هیچ‌وقت approved نمی‌شد. کانفیگ ساخته و
              تحویل می‌شد و سفارش pending می‌ماند — و جاروکشِ
              سفارش‌های منقضی نیم‌ساعت بعد آن را «منقضی» می‌کرد. یعنی
              فروشِ انجام‌شده در هیچ آماری دیده نمی‌شد.

            • تمدید خودکار برعکسش را می‌کرد: *قبل* از ساخت، approved
              می‌شد. اگر ساخت شکست می‌خورد پول برمی‌گشت ولی سفارش
              approved می‌ماند — یعنی پولِ برگشته، «فروش» شمرده می‌شد.
              و چون تمدیدِ ناموفق با فاصله دوباره تلاش می‌شود، هر روز
              چند فروشِ خیالی به آمار اضافه می‌کرد.

            دو خطا در دو جهت: جمعشان عددی می‌ساخت که درست به نظر
            می‌رسید و نبود.

        ادعا اول، پرداخت بعد — مثل release_coins. جاروکش در زمان‌بند
        می‌دود و مسیرهای خطا در نخ گفتگو؛ قفلِ چت زمان‌بند را در بر
        نمی‌گیرد. بدون ادعا، هر دو همان سفارش را می‌بینند و هر دو پول
        را برمی‌گردانند.

        مبلغِ برگشتی از خودِ دفتر حساب می‌شود (خرج منهای آنچه قبلاً
        برگشته)، نه از مبلغِ سفارش — پس برگشتِ نصفه هم دوباره‌کاری
        نمی‌سازد.
        """
        with conn() as c:
            # این UPDATE هم ادعا است و هم قفلِ نوشتن را می‌گیرد، پس
            # خواندن‌های بعدی داخل همین تراکنش امن‌اند.
            cur = c.execute(
                "UPDATE orders SET status=?, admin_note=COALESCE(?, admin_note) "
                "WHERE tenant_id=? AND id=? AND status=?",
                (status, note, self.tid, order_id, from_status))
            if not cur.rowcount:
                return False, 0

            # ── ظرفیتِ کدِ تخفیف ──
            #
            # این‌جا، چون این تنها جایی است که سفارش `approved`
            # می‌شود — کارت، کیف پول، تمدید خودکار و مینی‌اپ همه از
            # همین رد می‌شوند. هر جای دیگری یعنی یک مسیر فراموش
            # می‌شود؛ همان اشتباهی که در این مخزن سه بار افتاد.
            #
            # و داخلِ همین تراکنش: ادعای وضعیت قفلِ نوشتن را گرفته،
            # پس دو تاییدِ هم‌زمان نمی‌توانند هر دو ظرفیت بردارند.
            #
            # اگر ظرفیت تمام شده باشد، **قیمتِ سفارش عوض نمی‌شود**.
            # سقف ابزارِ بازاریابی است؛ گرفتنِ مبلغی غیر از آنچه به
            # مشتری گفته‌ایم نیست.
            if status == "approved":
                dcode = c.execute(
                    "SELECT discount_code FROM orders WHERE tenant_id=? AND id=?",
                    (self.tid, order_id)).fetchone()
                dcode = (dcode["discount_code"] if dcode else "") or ""
                if dcode.strip():
                    c.execute(
                        """UPDATE discounts
                              SET used_count = used_count + 1
                            WHERE tenant_id=? AND UPPER(code)=?
                              AND (max_uses = 0 OR used_count < max_uses)""",
                        (self.tid, dcode.strip().upper()))

            if status not in self.REFUND_ON:
                return True, 0

            row = c.execute(
                "SELECT user_id, paid_from FROM orders WHERE tenant_id=? AND id=?",
                (self.tid, order_id)).fetchone()
            if not row or row["paid_from"] != "wallet":
                return True, 0

            spent = c.execute(
                "SELECT COALESCE(SUM(-amount),0) s FROM wallet_tx "
                "WHERE tenant_id=? AND order_id=? AND amount < 0",
                (self.tid, order_id)).fetchone()["s"]
            given = c.execute(
                "SELECT COALESCE(SUM(amount),0) s FROM wallet_tx "
                "WHERE tenant_id=? AND order_id=? AND amount > 0",
                (self.tid, order_id)).fetchone()["s"]
            owed = int(spent) - int(given)
            if owed <= 0:
                return True, 0

            c.execute("UPDATE users SET balance = balance + ? "
                      "WHERE tenant_id=? AND id=?",
                      (owed, self.tid, row["user_id"]))
            c.execute(
                """INSERT INTO wallet_tx (tenant_id, user_id, amount, kind,
                                          note, order_id)
                   VALUES (?,?,?,?,?,?)""",
                (self.tid, row["user_id"], owed, "refund",
                 note or f"بازگشت وجه — سفارش #{order_id}", order_id))
            return True, owed

    def release_coins(self, order_id):
        """
        سکه‌های رزروشده‌ی یک سفارش را برمی‌گرداند. تعدادِ رزروهای
        آزادشده را می‌دهد.

        این‌جا زندگی می‌کند، نه در handlers، چون جاروکشِ خودکارِ
        سفارش‌های منقضی هیچ رباتی در دست ندارد و نمی‌تواند Ctx بسازد.
        وقتی این منطق فقط در handlers بود، آن جاروکش یک UPDATE خام
        می‌زد و رزرو را باز می‌گذاشت — و چون جاروکش همیشه زودتر از
        مشتری به سفارش می‌رسد، عملاً *مسیر اصلیِ* انقضا همان بود.

        هر رزرو *اول* ادعا می‌شود و بعد پرداخت.

        قبلاً برعکس بود: بخوان، سکه را برگردان، بعد رزرو را released
        کن. سه دستور جدا. و این تابع از دو نخ صدا زده می‌شود — جاروکشِ
        سفارش‌های منقضی در زمان‌بند، و مسیر لغو و رد در خودِ گفتگو.
        قفلِ هر گفتگو زمان‌بند را در بر نمی‌گیرد، پس اگر مشتری همان
        لحظه‌ای «لغو» بزند که جاروکش سفارشش را منقضی می‌کند، هر دو
        همان یک ردیفِ hold را می‌بینند و هر دو سکه را برمی‌گردانند.
        مشتری دو برابر سکه می‌گیرد، و سکه تخفیف است — یعنی پول.

        با ادعای اتمی، بازنده‌ی مسابقه هیچ سطری را عوض نمی‌کند و
        چیزی هم پرداخت نمی‌کند. ترتیب عمدی است: اگر بین ادعا و
        پرداخت چیزی قطع شود، سکه برنمی‌گردد — که بد است ولی دیدنی و
        قابل جبران. برعکسش، دو بار پرداختن، بی‌صدا است.
        """
        held = self.q(
            "SELECT * FROM coin_tx WHERE tenant_id=? AND order_id=? "
            "AND kind='hold'", (self.tid, order_id))
        freed = 0
        for tx in held:
            with conn() as c:
                cur = c.execute(
                    "UPDATE coin_tx SET kind='released' "
                    "WHERE tenant_id=? AND id=? AND kind='hold'",
                    (self.tid, tx["id"]))
                if not cur.rowcount:
                    # نخ دیگری همین رزرو را برداشته
                    continue
            self.add_coins(tx["user_id"], abs(int(tx["amount"])), "refund",
                           f"بازگشت سکه — سفارش #{order_id}",
                           order_id=order_id)
            freed += 1
        return freed

    def add_coins(self, user_id, amount, kind, note=None, ref_user_id=None, order_id=None):
        """
        تغییر موجودی سکه — برای پاداش، بازگشت و تنظیم دستی ادمین.

        برای *خرج‌کردن* از spend_coins استفاده کنید؛ این تابع شرطی
        ندارد و موجودی را منفی هم می‌کند.
        """
        with conn() as c:
            # اگر کاربری به‌روز نشد، تراکنشی هم ثبت نمی‌شود.
            #
            # وگرنه دفتر چیزی را نشان می‌دهد که هیچ‌وقت جابه‌جا نشده:
            # تراکنش «+۵۰ سکه» ثبت است و موجودی همان است که بود.
            cur = c.execute(
                "UPDATE users SET coins = coins + ? WHERE tenant_id=? AND id=?",
                (amount, self.tid, user_id)
            )
            if not cur.rowcount:
                return False
            c.execute(
                """INSERT INTO coin_tx (tenant_id, user_id, amount, kind, note,
                                        ref_user_id, order_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (self.tid, user_id, amount, kind, note, ref_user_id, order_id)
            )
            return True

    # ---------- کیف پول ----------
    def add_balance(self, user_id, amount, kind, note=None, order_id=None):
        """
        تغییر موجودی — برای واریز، برگشت پول و تنظیم دستی ادمین.

        برای *خرج‌کردن* از spend_balance استفاده کنید، نه این. این
        تابع شرطی ندارد و موجودی را منفی هم می‌کند.
        """
        with conn() as c:
            # همان قاعده‌ی add_coins: بدون جابه‌جایی، بدون تراکنش.
            cur = c.execute(
                "UPDATE users SET balance = balance + ? WHERE tenant_id=? AND id=?",
                (amount, self.tid, user_id)
            )
            if not cur.rowcount:
                return False
            c.execute(
                """INSERT INTO wallet_tx (tenant_id, user_id, amount, kind, note, order_id)
                   VALUES (?,?,?,?,?,?)""",
                (self.tid, user_id, amount, kind, note, order_id)
            )
            return True

    def spend_balance(self, user_id, amount, kind, note=None, order_id=None):
        """
        خرج‌کردن از کیف پول — اتمی. برمی‌گرداند: (موفق, موجودی تازه)

        چرا جدا از add_balance:
            الگوی قبلی «اول موجودی را بخوان، اگر کافی بود کم کن» بود.
            بین این دو، هر چیز دیگری می‌تواند همان پول را خرج کند —
            و از وقتی ربات با هشت نخ کار می‌کند و زمان‌بند تمدید
            خودکار در نخ جداگانه‌ای می‌دود، این دیگر فرضی نیست:
            مشتری در حال خرید است و هم‌زمان تمدید خودکارش اجرا می‌شود.

            بدتر اینکه UPDATE هیچ شرطی نداشت، پس نتیجه‌ی هر لغزشی
            یک موجودی منفی بود که هیچ‌جا دیده نمی‌شد.

            این‌جا خود دیتابیس شرط را نگه می‌دارد: اگر موجودی کافی
            نباشد هیچ سطری به‌روز نمی‌شود و تراکنشی هم ثبت نمی‌شود.
        """
        amount = abs(int(amount))
        with conn() as c:
            cur = c.execute(
                "UPDATE users SET balance = balance - ? "
                "WHERE tenant_id=? AND id=? AND balance >= ?",
                (amount, self.tid, user_id, amount)
            )
            if not cur.rowcount:
                row = c.execute(
                    "SELECT balance FROM users WHERE tenant_id=? AND id=?",
                    (self.tid, user_id)).fetchone()
                return False, (row["balance"] if row else 0)

            c.execute(
                """INSERT INTO wallet_tx (tenant_id, user_id, amount, kind, note, order_id)
                   VALUES (?,?,?,?,?,?)""",
                (self.tid, user_id, -amount, kind, note, order_id)
            )
            row = c.execute(
                "SELECT balance FROM users WHERE tenant_id=? AND id=?",
                (self.tid, user_id)).fetchone()
            return True, (row["balance"] if row else 0)

    # ---------- پلن‌ها ----------
    def plans(self, active_only=True, include_trial=False):
        sql = "SELECT * FROM plans WHERE tenant_id=?"
        if active_only:
            sql += " AND is_active=1"
        if not include_trial:
            sql += " AND is_trial=0"
        sql += " ORDER BY sort_order, price"
        return self.q(sql, (self.tid,))

    def get_plan(self, pid):
        return self.q("SELECT * FROM plans WHERE tenant_id=? AND id=?",
                      (self.tid, pid), one=True)

    def trial_plan(self):
        return self.q(
            "SELECT * FROM plans WHERE tenant_id=? AND is_trial=1 AND is_active=1 LIMIT 1",
            (self.tid,), one=True
        )

    # ---------- سفارش ----------
    def create_order(self, user_id, plan_id, base_amount, amount,
                     coins_used=0, discount_pct=0, discount_code=None,
                     kind="new", paid_from="card", ttl_minutes=30,
                     renew_sub_id=None, renew_license=None):
        exp = (datetime.now() + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds")
        oid = self.exec(
            """INSERT INTO orders (tenant_id, user_id, plan_id, kind, amount,
                                   base_amount, coins_used, discount_pct,
                                   discount_code, paid_from, expires_at,
                                   renew_sub_id, renew_license)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self.tid, user_id, plan_id, kind, amount, base_amount,
             coins_used, discount_pct, discount_code, paid_from, exp,
             renew_sub_id, renew_license)
        )
        return self.get_order(oid)

    # ── صندوق پیام ──
    #
    # سه چیزِ به‌ظاهر جدا از همین‌جا می‌آیند: تاییدِ رسید، ردش با متنِ
    # دلیل، و گفتگو با پشتیبانی. هر سه یک شکل دارند، پس یک جا.

    def chat_add(self, user_id, sender, body, order_id=None, photo=None):
        """
        یک پیام در صندوق. برمی‌گرداند شناسه‌اش.

        عکسِ بدونِ متن پیامِ معتبری است — پس شرطِ «خالی نباشد» روی
        هر دو با هم است، نه فقط روی متن. اگر فقط متن را می‌سنجید،
        فرستادنِ عکسِ تنها بی‌صدا هیچ‌کاری نمی‌کرد.
        """
        body = str(body or "").strip()
        photo = str(photo or "").strip() or None
        if not body and not photo:
            return None
        return self.exec(
            "INSERT INTO chat_messages (tenant_id, user_id, sender, body, photo, order_id) "
            "VALUES (?,?,?,?,?,?)",
            (self.tid, user_id, sender, body[:4000], photo, order_id))

    def chat_list(self, user_id, limit=100):
        """گفتگوی یک مشتری، قدیمی به تازه."""
        rows = self.q(
            "SELECT * FROM chat_messages WHERE tenant_id=? AND user_id=? "
            "ORDER BY id DESC LIMIT ?", (self.tid, user_id, int(limit)))
        return list(reversed(rows))

    def chat_unread_from_support(self, user_id):
        """Unread messages a person on the support side wrote (sender 'admin').
        System notes (reminders, delivery copies) are not counted: a buyer who
        never opens the mini app piles those up, and counting them stopped
        every support notice for good."""
        r = self.q(
            "SELECT COUNT(*) n FROM chat_messages "
            "WHERE tenant_id=? AND user_id=? AND sender='admin' AND read_at IS NULL",
            (self.tid, user_id), one=True)
        return int((r["n"] if r else 0) or 0)

    def chat_unread_for_user(self, user_id):
        """چند پیامِ نخوانده برای *مشتری* — یعنی از طرفِ ما."""
        r = self.q(
            "SELECT COUNT(*) n FROM chat_messages "
            "WHERE tenant_id=? AND user_id=? AND sender<>'user' AND read_at IS NULL",
            (self.tid, user_id), one=True)
        return int((r["n"] if r else 0) or 0)

    def chat_unread_for_admin(self):
        """چند پیامِ نخوانده برای *مالک* — یعنی از طرفِ مشتری‌ها."""
        r = self.q(
            "SELECT COUNT(*) n FROM chat_messages "
            "WHERE tenant_id=? AND sender='user' AND read_at IS NULL",
            (self.tid,), one=True)
        return int((r["n"] if r else 0) or 0)

    def chat_mark_read(self, user_id, by):
        """
        خوانده‌شدن را ثبت کن.

        `by='user'` یعنی مشتری خواند، پس پیام‌های *ما* خوانده شده‌اند.
        `by='admin'` برعکس. شرط را وارونه ننویس، وگرنه هر طرف
        پیام‌های خودش را «خوانده» می‌کند و نشانِ طرف مقابل هیچ‌وقت
        صفر نمی‌شود.
        """
        if by == "user":
            cond = "sender<>'user'"
        else:
            cond = "sender='user'"
        return self.exec(
            f"UPDATE chat_messages SET read_at=CURRENT_TIMESTAMP "
            f"WHERE tenant_id=? AND user_id=? AND {cond} AND read_at IS NULL",
            (self.tid, user_id))

    def chat_threads(self, limit=60):
        """
        فهرستِ گفتگوها برای پنل — تازه‌ترین اول، با شمارِ نخوانده.
        """
        return self.q(
            """SELECT u.id AS user_id, u.tg_id, u.first_name, u.username,
                      MAX(m.id) AS last_id,
                      MAX(m.created_at) AS last_at,
                      SUM(CASE WHEN m.sender='user' AND m.read_at IS NULL
                               THEN 1 ELSE 0 END) AS unread,
                      (SELECT body FROM chat_messages x
                        WHERE x.tenant_id=m.tenant_id AND x.user_id=m.user_id
                        ORDER BY x.id DESC LIMIT 1) AS last_body,
                      -- بدون این، پیامی که فقط عکس است در فهرست
                      -- گفتگوها یک خطِ خالی می‌شد و به نظر می‌رسید
                      -- چیزی نیامده
                      (SELECT photo FROM chat_messages x
                        WHERE x.tenant_id=m.tenant_id AND x.user_id=m.user_id
                        ORDER BY x.id DESC LIMIT 1) AS last_photo
                 FROM chat_messages m
                 JOIN users u ON u.id = m.user_id
                WHERE m.tenant_id=?
             GROUP BY u.id
             ORDER BY last_id DESC
                LIMIT ?""", (self.tid, int(limit)))

    def get_order(self, oid):
        return self.q("SELECT * FROM orders WHERE tenant_id=? AND id=?",
                      (self.tid, oid), one=True)

    def pending_orders(self):
        return self.q(
            """SELECT o.*, u.tg_id, u.first_name, u.username, p.name AS plan_name
               FROM orders o
               JOIN users u ON u.id = o.user_id
               LEFT JOIN plans p ON p.id = o.plan_id
               WHERE o.tenant_id=? AND o.status='awaiting'
               ORDER BY o.created_at DESC""",
            (self.tid,)
        )

    # ---------- اشتراک ----------
    def user_licenses(self, user_id):
        """Pro licenses this user bought here, newest first (Phase 4)."""
        return self.q("SELECT * FROM pro_licenses WHERE tenant_id=? AND user_id=? "
                      "ORDER BY id DESC", (self.tid, user_id))

    def user_license(self, user_id, license_id):
        """One of this user's licenses, or None: ownership is the WHERE."""
        return self.q("SELECT * FROM pro_licenses WHERE tenant_id=? AND user_id=? "
                      "AND license_id=?", (self.tid, user_id, str(license_id)), one=True)

    def save_license(self, user_id, order_id, license_id, plan, expires, key_hint=None):
        """Record an issued or renewed license. A repeated issue for the same
        order comes back with a new key, so the hint is updated too."""
        with conn() as c:
            c.execute(
                "INSERT INTO pro_licenses (tenant_id, user_id, license_id, plan, expires,"
                " key_hint, order_id) VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(license_id) DO UPDATE SET expires=excluded.expires,"
                " key_hint=CASE WHEN ? IS NULL THEN key_hint ELSE excluded.key_hint END,"
                " updated_at=CURRENT_TIMESTAMP",
                (self.tid, user_id, license_id, plan, expires, key_hint or "",
                 order_id, key_hint))

    def user_subs(self, user_id, active_only=True):
        sql = """SELECT s.*, p.name AS plan_name FROM subscriptions s
                 LEFT JOIN plans p ON p.id = s.plan_id
                 WHERE s.tenant_id=? AND s.user_id=?"""
        if active_only:
            sql += " AND s.is_active=1"
        sql += " ORDER BY s.created_at DESC"
        return self.q(sql, (self.tid, user_id))

    # ---------- آمار ----------
    def stats(self):
        def one(sql, p=()):
            r = self.q(sql, p, one=True)
            return (list(r.values())[0] if r else 0) or 0

        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "users": one("SELECT COUNT(*) FROM users WHERE tenant_id=?", (self.tid,)),
            "users_today": one(
                "SELECT COUNT(*) FROM users WHERE tenant_id=? AND date(created_at)=?",
                (self.tid, today)),
            "active_subs": one(
                "SELECT COUNT(*) FROM subscriptions WHERE tenant_id=? AND is_active=1",
                (self.tid,)),
            "pending": one(
                "SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status='awaiting'",
                (self.tid,)),
            "revenue_today": one(
                """SELECT COALESCE(SUM(amount),0) FROM orders
                   WHERE tenant_id=? AND status='approved' AND date(reviewed_at)=?""",
                (self.tid, today)),
            "revenue_total": one(
                """SELECT COALESCE(SUM(amount),0) FROM orders
                   WHERE tenant_id=? AND status='approved'""",
                (self.tid,)),
            # پنل مدیریت ربات این را می‌خواند؛ نبودنش باعث می‌شد
            # «تیکت باز» همیشه صفر نشان داده شود
            "open_tickets": one(
                "SELECT COUNT(*) FROM tickets WHERE tenant_id=? AND status='open'",
                (self.tid,)),
        }

    def log(self, kind, user_id=None, data=None):
        """
        ثبتِ رویداد — **هرگز کارِ صداکننده را نمی‌شکند.**

        این تابع از داخلِ `except` صدا زده می‌شود: جایی که تحویلِ
        کانفیگ شکست خورده و داریم دلیلش را می‌نویسیم. اگر خودِ
        نوشتن خطا بدهد و بالا برود، یک خطای فرعی جای خطای اصلی را
        می‌گیرد و مسیرِ جبران (برگرداندنِ پول) اجرا نمی‌شود.
        """
        try:
            self.exec(
                "INSERT INTO events (tenant_id, user_id, kind, data) "
                "VALUES (?,?,?,?)",
                (self.tid, user_id, kind,
                 json.dumps(data or {}, ensure_ascii=False))
            )
        except Exception:
            log.debug("ثبت رویداد ناموفق (%s)", kind, exc_info=True)
            return

        # هرس: جدول سقف ندارد و برای همیشه رشد می‌کند. همان‌جا که
        # می‌نویسیم می‌بُریم، نه در یک کارِ زمان‌بندِ جدا — کاری که
        # وصل‌کردنش یادمان برود یعنی سقف وجود ندارد.
        #
        # هر صد تا یک‌بار، نه هر بار: شمردنِ ردیف‌ها در هر ثبت،
        # هزینه‌ای است که هیچ‌چیز نمی‌خرد.
        try:
            if secrets.randbelow(100) == 0:
                self.exec(
                    """DELETE FROM events
                        WHERE tenant_id=? AND id NOT IN (
                            SELECT id FROM events WHERE tenant_id=?
                             ORDER BY id DESC LIMIT ?)""",
                    (self.tid, self.tid, EVENT_MAX_ROWS))
        except Exception:
            log.debug("هرس رویدادها ناموفق", exc_info=True)

    def events(self, limit=50, offset=0, only_errors=False, kinds=None):
        """
        فهرستِ رویدادها با صفحه‌بندیِ شماره‌دار.

        `kinds` فهرستِ نوع‌هایی است که «خطا» شمرده می‌شوند. از
        بیرون داده می‌شود و این‌جا دوباره نوشته نمی‌شود: تعریفش در
        `bot/events.py` است و دو نسخه‌ی این فهرست یعنی روزی فیلترِ
        پنل و فیلترِ ربات دو چیزِ متفاوت بگویند.
        """
        params = [self.tid]

        # فقط فیلترِ نوع از متغیر می‌آید. شرطِ مستاجر **در خودِ متنِ
        # SQL** نوشته می‌شود، نه داخلِ یک `{where}`: هم دروازه‌ی درز
        # و هم نگهبانِ `self.q` متن را می‌خوانند، و شرطی که پشتِ
        # متغیر پنهان شده از دیدِ هر دو غایب است.
        kind_sql = ""
        if only_errors:
            ks = list(kinds or [])
            if not ks:
                # فهرستِ خالی یعنی «هیچ نوعی خطا نیست» — نه «فیلتر
                # را نادیده بگیر». برگرداندنِ همه چیز این‌جا یعنی
                # مالک فکر کند فیلتر کار کرده و نکرده.
                return {"rows": [], "total": 0}
            kind_sql = " AND e.kind IN (%s)" % ",".join("?" * len(ks))
            params += ks

        total = self.q(
            f"SELECT COUNT(*) c FROM events e"
            f" WHERE e.tenant_id=?{kind_sql}",
            tuple(params), one=True)["c"]

        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        rows = self.q(
            f"""SELECT e.id, e.kind, e.data, e.created_at, e.user_id,
                       u.first_name, u.username, u.tg_id
                  FROM events e
                  LEFT JOIN users u ON u.id = e.user_id
                 WHERE e.tenant_id=?{kind_sql}
                 ORDER BY e.id DESC LIMIT ? OFFSET ?""",
            tuple(params) + (limit, offset))
        return {"rows": [dict(r) for r in rows], "total": int(total or 0)}


# ═══════════════════════════════════════════════════════════
#  عملیات سطح سیستم (فراتر از یک مستاجر) — فقط برای مالک اصلی
# ═══════════════════════════════════════════════════════════

def all_tenants(active_only=True):
    sql = "SELECT * FROM tenants"
    if active_only:
        sql += " WHERE is_active=1"
    with conn() as c:
        return [dict(r) for r in c.execute(sql).fetchall()]


def get_tenant(tid):
    with conn() as c:
        r = c.execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()
    return dict(r) if r else None


def root_tenant():
    """مستاجرِ ریشه (مالک). نه «کوچک‌ترین شناسه» — ریشه."""
    with conn() as c:
        r = c.execute("SELECT * FROM tenants WHERE parent_id IS NULL "
                      "ORDER BY id LIMIT 1").fetchone()
    return dict(r) if r else None


def trial_cap():
    """
    تستِ رایگانِ نماینده‌ها — {gb, days, ip_limit}، یا None یعنی «ممکن نیست».

    **عددها را مالک تعیین می‌کند، نه نماینده.** مالک: «حجمش را خودم
    مشخص می‌کنم، وگرنه ممکن است حجمِ زیاد بگذارد». تا ۱.۱۱۴ این فقط سقف
    بود و نماینده زیرِ آن هر عددی می‌گذاشت؛ حالا همین عددها عیناً روی تستِ
    هر نماینده می‌نشینند (بکند موقعِ ذخیره، ربات موقعِ ساخت).

    منبع: تنظیمِ `reseller_trial` مالک (پنل ← قابلیت‌های نماینده‌ها).
    اگر هرگز تنظیم نشده، تستِ خودِ مالک — رفتارِ پیش از این نسخه، تا
    به‌روزرسانی تستِ هیچ نماینده‌ای را بی‌خبر خاموش نکند.
    """
    root = root_tenant()
    if not root:
        return None
    try:
        rs = json.loads(root.get("settings") or "{}")
    except (json.JSONDecodeError, TypeError):
        rs = {}
    spec = rs.get("reseller_trial") if isinstance(rs, dict) else None
    if isinstance(spec, dict):
        if not spec.get("enabled"):
            return None
        try:
            return {"gb": max(0, int(spec.get("gb") or 0)),
                    "days": max(1, int(spec.get("days") or 1)),
                    "ip_limit": max(0, int(spec.get("ip_limit") or 0))}
        except (TypeError, ValueError):
            # تنظیمِ خراب یعنی عددِ نامعلوم — تستِ بی‌سقف نمی‌دهیم
            log.warning("reseller_trial unreadable: %r — reseller trials off", spec)
            return None
    with conn() as c:
        r = c.execute("SELECT gb, days, ip_limit FROM plans WHERE tenant_id=? "
                      "AND is_trial=1 AND is_active=1 ORDER BY id LIMIT 1",
                      (root["id"],)).fetchone()
    return dict(r) if r else None


def panel_source(t):
    """
    ردیفی که اتصالِ x-ui از آن خوانده می‌شود.

    نماینده پنلِ جدا ندارد؛ کانفیگ‌هایش در پنلِ مالک و داخلِ گروهِ
    خودش ساخته می‌شوند. پرتال از روز اول همین را می‌دانست
    (`_portal_xui` در بکند) ولی ربات نه — ربات با ستون‌های خالیِ
    ردیفِ نماینده وصل می‌شد، یعنی به هیچ‌جا. نتیجه: رباتِ هیچ
    نماینده‌ای نمی‌توانست حتی یک کانفیگ بسازد، و تاییدِ سفارش از
    پرتال هم (که همین کد را صدا می‌زند) با همان خطا می‌ایستاد.

    این قاعده دو جا نوشته شده؛ `test-seams` برابری‌شان را می‌سنجد.
    """
    if not t or t.get("panel_url"):
        return t
    if t.get("parent_id"):
        return root_tenant() or t
    return t


def is_prepaid(t):
    """اعتبارِ منفی یا خالی یعنی بدهکاری — آخرِ ماه صورتحساب."""
    try:
        return t is not None and t.get("credit") is not None \
            and int(t.get("credit")) >= 0
    except (TypeError, ValueError):
        return False


def charge_credit(tid, amount, note):
    """
    کسرِ اعتبارِ نماینده‌ی پیش‌پرداخت — اتمی.

    برمی‌گرداند: (اجازه هست؟, موجودیِ فعلی)

    شرط داخلِ خودِ UPDATE است، مثل `_portal_charge` در بکند: الگوی
    «بخوان، اگر بس بود کم کن» بینِ دو قدم برای فروشِ هم‌زمانِ دیگری
    جا باز می‌گذارد و اعتبار منفی می‌شود.

    `note` باید شناسه‌ی کانفیگ را داشته باشد — `_portal_charge_for`
    موقعِ حذف، برگشتی را از روی همین متن پیدا می‌کند.
    """
    amount = max(0, int(amount or 0))
    with conn() as c:
        if amount:
            cur = c.execute(
                "UPDATE tenants SET credit = credit - ? "
                "WHERE id=? AND credit >= ?", (amount, tid, amount))
            if not cur.rowcount:
                r = c.execute("SELECT credit FROM tenants WHERE id=?",
                              (tid,)).fetchone()
                return False, int((r["credit"] if r else 0) or 0)
        r = c.execute("SELECT credit FROM tenants WHERE id=?",
                      (tid,)).fetchone()
        left = int((r["credit"] if r else 0) or 0)
        if amount:
            c.execute("INSERT INTO credit_tx (tenant_id, amount, balance, note) "
                      "VALUES (?,?,?,?)", (tid, -amount, left, str(note)[:200]))
    return True, left


def refund_credit(tid, amount, note):
    """برگرداندنِ همان کسر، وقتی کار روی پنل انجام نشد."""
    amount = max(0, int(amount or 0))
    if not amount:
        return
    with conn() as c:
        c.execute("UPDATE tenants SET credit = credit + ? WHERE id=?",
                  (amount, tid))
        r = c.execute("SELECT credit FROM tenants WHERE id=?",
                      (tid,)).fetchone()
        c.execute("INSERT INTO credit_tx (tenant_id, amount, balance, note) "
                  "VALUES (?,?,?,?)",
                  (tid, amount, int((r["credit"] if r else 0) or 0),
                   str(note)[:200]))


def tenant_by_slug(slug):
    """
    نماینده را از روی نشانیِ لینکش پیدا می‌کند.

    فقط نماینده‌های فعال و آن‌هایی که پنلشان روشن شده. غیرفعال‌کردن
    یک نماینده باید در همان لحظه دسترسی‌اش را ببندد، نه اینکه فقط
    از فهرست پنهانش کند.
    """
    if not slug:
        return None
    with conn() as c:
        r = c.execute(
            "SELECT * FROM tenants WHERE portal_slug=? AND is_active=1 "
            "AND COALESCE(portal_enabled,0)=1",
            (str(slug).strip().lower(),)).fetchone()
    return dict(r) if r else None


def set_portal(tid, slug=None, password=None, enabled=None):
    """
    تنظیم دسترسی پنل یک نماینده. برمی‌گرداند: (موفق, پیام)

    slug یکتاست چون آدرس است. تکراری بودنش یعنی دو نماینده به یک
    لینک می‌رسند، که بدترین اشتباه ممکن در این مسیر است.
    """
    sets, vals = [], []
    if slug is not None:
        clean = "".join(ch for ch in str(slug).strip().lower()
                        if ch.isalnum() or ch in "-_")[:32]
        if not clean:
            return False, "نشانی لینک نامعتبر است"
        with conn() as c:
            taken = c.execute(
                "SELECT id FROM tenants WHERE portal_slug=? AND id<>?",
                (clean, tid)).fetchone()
        if taken:
            return False, "این نشانی برای نماینده‌ی دیگری ثبت شده"
        sets.append("portal_slug=?")
        vals.append(clean)
    if password is not None:
        pw = str(password)
        if len(pw) < 8:
            return False, "رمز باید دست‌کم ۸ نویسه باشد"
        sets.append("portal_pass=?")
        vals.append(pw)
    if enabled is not None:
        sets.append("portal_enabled=?")
        vals.append(1 if enabled else 0)
    if not sets:
        return False, "چیزی برای تغییر نیست"
    vals.append(tid)
    with conn() as c:
        c.execute(f"UPDATE tenants SET {', '.join(sets)} WHERE id=?", vals)
    return True, "ثبت شد"


def get_tenant_by_token(token):
    with conn() as c:
        r = c.execute("SELECT * FROM tenants WHERE bot_token=?", (token,)).fetchone()
    return dict(r) if r else None


def create_tenant(name, bot_token=None, owner_tg_id=None, parent_id=None, **kw):
    with conn() as c:
        cur = c.execute(
            """INSERT INTO tenants (name, bot_token, owner_tg_id, parent_id,
                                    panel_url, panel_user, panel_pass,
                                    default_inbound, credit, credit_discount, settings)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (name, bot_token, owner_tg_id, parent_id,
             kw.get("panel_url"), kw.get("panel_user"), kw.get("panel_pass"),
             kw.get("default_inbound"), kw.get("credit", 0),
             kw.get("credit_discount", 0),
             json.dumps(kw.get("settings", {}), ensure_ascii=False))
        )
        return cur.lastrowid


def update_tenant(tid, **fields):
    if not fields:
        return
    allowed = {"name", "bot_token", "bot_username", "owner_tg_id", "is_active",
               "credit", "credit_discount", "panel_url", "panel_user",
               "panel_pass", "panel_token", "default_inbound",
               "admin_group_id", "topics", "settings"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            if k in ("topics", "settings") and isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(tid)
    with conn() as c:
        c.execute(f"UPDATE tenants SET {', '.join(sets)} WHERE id=?", vals)


def tenant_settings(tid):
    t = get_tenant(tid)
    if not t:
        return {}
    try:
        return json.loads(t.get("settings") or "{}")
    except json.JSONDecodeError:
        return {}


def save_tenant_settings(tid, settings: dict):
    update_tenant(tid, settings=settings)
