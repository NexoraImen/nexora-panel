"""Launch regressions use isolated shops and the real shared financial cores."""
import os
from pathlib import Path
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'bot')]
tmp = tempfile.TemporaryDirectory()
os.environ['BOT_DB_PATH'] = str(Path(tmp.name) / 'bot.db')
from bot import handlers as H

H.DB.init_db()
owner = H.DB.create_tenant('Owner', owner_tg_id=10)
shops = [owner] + [H.DB.create_tenant('Reseller', parent_id=owner) for _ in range(2)]
for tid in shops:
    d = H.DB.TenantDB(tid)
    d.create_user(123, None, 'Buyer')
    user = d.get_user(123)
    order = d.create_order(user['id'], None, 1000, 1000, kind='topup')
    assert d.claim_order(order['id'], 10)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _: d.credit_topup(order['id']), range(16))) == 1
    d.exec("UPDATE orders SET reviewed_at='2000-01-01' WHERE tenant_id=? AND id=?", (tid, order['id']))
    assert not d.claim_order(order['id'], 10), 'Stale top-up cannot be credited twice'
    assert d.get_user(123)['balance'] == 1000
    assert H.core.order_delivered(d.get_order(order['id']))
    assert not d.mark_rejected(order['id'], 10, 'reject')
    assert not d.close_order(order['id'], 'expired', from_status='approved')[0]
    with H.DB.conn() as cx:
        assert not cx.execute('SELECT 1 FROM orders WHERE id=? AND ' + H.DB.UNDELIVERED,
                              (order['id'],)).fetchone()
    assert not H.DB.TenantDB(tid + 1000).credit_topup(order['id'])

    # A restart after approval but before credit is recoverable once, with no prior debit.
    restart = d.create_order(user['id'], None, 500, 500, kind='topup')
    assert d.claim_order(restart['id'], 10)
    d.exec("UPDATE orders SET reviewed_at='2000-01-01' WHERE tenant_id=? AND id=?", (tid, restart['id']))
    assert d.claim_order(restart['id'], 10)
    assert d.credit_topup(restart['id']) and not d.credit_topup(restart['id'])
    assert d.get_user(123)['balance'] == 1500

    # Notification failure cannot undo an already committed top-up.
    notify = d.create_order(user['id'], None, 200, 200, kind='topup')
    bot = SimpleNamespace(send=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline')))
    ctx = SimpleNamespace(tid=tid, db=d, bot=bot)
    try:
        H.approve_order(ctx, notify['id'], 10)
    except RuntimeError:
        pass
    assert d.get_user(123)['balance'] == 1700
    assert not d.mark_rejected(notify['id'], 10, 'reject')
    assert not H.approve_order(ctx, notify['id'], 10)[0]
    from bot import run as R
    H.DB.update_tenant(tid, bot_token=f'{tid}:test')
    for queued in ('panel_approve', 'panel_reject'):
        d.exec('UPDATE orders SET status=? WHERE tenant_id=? AND id=?', (queued, tid, notify['id']))
        with patch.object(R, 'Bot', return_value=bot), patch.object(R.handlers, 'Ctx', return_value=ctx):
            R.process_panel_approvals()
        assert d.get_order(notify['id'])['status'] == 'approved'
        assert d.get_user(123)['balance'] == 1700

    expired = d.create_order(user['id'], None, 10, 10, ttl_minutes=-1)
    snapshot = d.get_order(expired['id'])
    assert d.attach_receipt(expired['id'], 'text', None, 'bank evidence')
    ctx = SimpleNamespace(tid=tid, db=d)
    # Force the precise interleaving: expiry read precedes a successful receipt claim.
    with patch.object(d, 'get_order', return_value=snapshot):
        assert H.receipt_submit(ctx, user, expired['id'], 'text', rtext='late')[0] is False
    assert d.get_order(expired['id'])['status'] == 'awaiting'
    assert d.get_order(expired['id'])['receipt_text'] == 'bank evidence'

    H.DB.update_tenant(tid, portal_group='test', portal_slug=f'shop{tid}', default_inbound=1)
    d.exec('UPDATE tenants SET portal_group=?,portal_slug=? WHERE id=?', ('test', f'shop{tid}', tid))
    tenant = H.DB.get_tenant(tid)
    pid = d.exec('INSERT INTO plans(tenant_id,name,price,days,gb,inbound_id) VALUES(?,?,100,30,10,1)', (tid, 'Plan'))
    sid = d.exec("INSERT INTO subscriptions(tenant_id,user_id,client_email,client_uuid,inbound_id,expires_at,gb) "
                 "VALUES(?,?,'expired','uuid',1,'2000-01-01',10)", (tid, user['id']))
    d.create_user(124, None, 'Other buyer')
    foreign = d.exec("INSERT INTO subscriptions(tenant_id,user_id,client_email,inbound_id) VALUES(?,?,'foreign',1)",
                     (tid, d.get_user(124)['id']))
    class XUI:
        extended = 0
        def extend_subscription(self, *a, **k):
            self.extended += 1
            return {'total_bytes': 20 * 1024 ** 3}
        def create_subscription(self, *a, **k):
            raise AssertionError('An explicit renewal must never create another subscription')
    xui = XUI()
    ctx = SimpleNamespace(tid=tid, db=d, s={}, tenant=tenant, xui=xui)
    for target in (0, 999999, foreign):
        order = d.create_order(user['id'], pid, 100, 100, kind='renew', renew_sub_id=target)
        assert not H._provision(ctx, order['id'])[0]
    d.exec("UPDATE subscriptions SET deleted_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND id=?", (tid, sid))
    order = d.create_order(user['id'], pid, 100, 100, kind='renew', renew_sub_id=sid)
    assert not H._provision(ctx, order['id'])[0] and xui.extended == 0
    d.exec('UPDATE subscriptions SET deleted_at=NULL WHERE tenant_id=? AND id=?', (tid, sid))
    result = H._provision(ctx, order['id'])
    assert result[0] and xui.extended == 1, result

# Reconcile historical linked credits without changing customer money or ledger history.
d = H.DB.TenantDB(owner)
user = d.get_user(123)
legacy = d.create_order(user['id'], None, 100, 100, kind='topup')
uncredited = d.create_order(user['id'], None, 200, 200, kind='topup')
d.exec("UPDATE orders SET status='rejected',credited_at=NULL WHERE tenant_id=? AND id=?", (owner, legacy['id']))
d.add_balance(user['id'], 100, 'topup', order_id=legacy['id'])
before_balance = d.get_user(123)['balance']
with H.DB.conn() as cx:
    before_ledger = tuple(cx.execute('SELECT COUNT(*),SUM(amount) FROM wallet_tx').fetchone())
H.DB.init_db()
H.DB.init_db()
assert d.get_order(legacy['id'])['status'] == 'approved' and H.core.order_delivered(d.get_order(legacy['id']))
assert not H.core.order_delivered(d.get_order(uncredited['id'])) and d.get_order(uncredited['id'])['status'] == 'pending'
assert d.get_user(123)['balance'] == before_balance
with H.DB.conn() as cx:
    assert tuple(cx.execute('SELECT COUNT(*),SUM(amount) FROM wallet_tx').fetchone()) == before_ledger

# SQL and Python intentionally treat every non-NULL marker conservatively as delivered.
with H.DB.conn() as cx:
    for field in ('sub_id', 'license_id', 'credited_at'):
        for marker in (None, 0, '', 'evidence'):
            row = {'sub_id': None, 'license_id': None, 'credited_at': None, field: marker}
            sql = cx.execute('SELECT NOT (' + H.DB.UNDELIVERED + ') AS delivered FROM '
                '(SELECT ? AS sub_id,? AS license_id,? AS credited_at)', tuple(row.values())).fetchone()['delivered']
            assert bool(sql) == H.core.order_delivered(row)
print('Owner/two reseller top-ups, crash recovery, expiry, renewal ownership/deletion and SQL/Python parity passed')
