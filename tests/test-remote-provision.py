"""Remote execution uncertainty must hold money and prevent provisioning replay."""
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'bot'))
TMP = tempfile.TemporaryDirectory(prefix='.remote-provision-', dir=ROOT)
os.environ.update(BOT_DB_PATH=str(Path(TMP.name) / 'bot.db'),
                  BILLING_DB_PATH=str(Path(TMP.name) / 'billing.db'),
                  CONFIG_PATH=str(Path(TMP.name) / 'config.json'))
from bot import handlers as H, run as R
from backend import remote_xui as REMOTE

D = H.DB
# run imports the package alias; both modules must use the same isolated file.
R.db = D


class Uncertain(RuntimeError):
    remote_uncertain = True


class RemoteProvisionTests(unittest.TestCase):
    def setUp(self):
        D.init_db()
        self.tid = D.create_tenant('remote-test', bot_token=self.id(), default_inbound=1)
        self.db = D.TenantDB(self.tid)
        self.uid = self.db.create_user(10000 + self.tid, first_name='Buyer')['id']
        self.user = self.db.get_user_by_id(self.uid)
        self.pid = self.db.exec('INSERT INTO plans (tenant_id,name,price,gb,days,inbound_id) '
                                'VALUES (?,\'Plan\',100,10,30,1)', (self.tid,))
        self.db.add_balance(self.uid, 500, 'deposit')
        self.xui = Mock(base='agent://test')
        self.xui.find_client.return_value = None
        self.ctx = SimpleNamespace(tid=self.tid, db=self.db, s={},
                                   tenant=D.get_tenant(self.tid), xui=self.xui,
                                   bot=Mock(), notify_group=Mock(), is_admin=lambda _: False)
        self.patches = [patch.object(H, 'store_gate', return_value=False),
                        patch.object(H, '_sellable', return_value=True),
                        patch.object(H, 'record'), patch.object(H, 'after_paid_order')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.calls = 0

    def mutation(self, *args, **kwargs):
        self.calls += 1
        context = REMOTE.ORDER.get()
        self.assertEqual(context['tenant_id'], self.tid)
        command = f'{self.tid}-{self.calls}'
        with REMOTE.connection() as db:
            db.execute('INSERT INTO remote_commands(id,node_id,payload,state,created) '
                       'VALUES (?,\'test\',\'{}\',\'unknown\',0)', (command,))
        REMOTE.hold_order(context, command)
        raise Uncertain('response lost after remote mutation')

    def order(self, **kwargs):
        return self.db.create_order(self.uid, self.pid, 100, 100, **kwargs)

    def assert_held(self, oid):
        self.assertEqual(self.db.get_order(oid)['status'], 'remote_review')
        self.assertIn('بررسی', self.db.get_order(oid)['admin_note'])
        self.assertIsNone(REMOTE.ORDER.get())
        self.assertFalse(self.db.claim_order(oid, 1, stale_minutes=0))
        self.assertFalse(self.db.mark_rejected(oid, 1, 'reject'))
        for status in ('approved', 'rejected', 'expired', 'cancelled'):
            self.assertEqual(self.db.close_order(oid, status, from_status='remote_review'), (False, 0))

    def test_wallet_create_holds_payment_and_blocks_replay(self):
        self.xui.create_subscription.side_effect = self.mutation
        result = H.wallet_purchase(self.ctx, self.user, self.pid)
        self.assertEqual(result['why'], 'remote_review')
        oid = self.db.q('SELECT id FROM orders WHERE tenant_id=?', (self.tid,), one=True)['id']
        self.assert_held(oid)
        self.assertEqual(self.db.get_user_by_id(self.uid)['balance'], 400)
        self.db.exec("UPDATE orders SET expires_at='2000-01-01' WHERE id=?", (oid,))
        self.assertEqual(H.wallet_purchase(self.ctx, self.user, self.pid)['why'], 'remote_review')
        self.assertFalse(H.provision(self.ctx, oid)[0])
        self.assertEqual(self.calls, 1)
        H.after_paid_order.assert_not_called()
        with patch.object(R.db, 'all_tenants', return_value=[self.ctx.tenant]), patch.object(R, 'Bot'):
            R.expire_stale_orders()
        self.assert_held(oid)

    def test_card_approval_keeps_hold_and_coins(self):
        order = self.order()
        self.db.exec("UPDATE orders SET status='awaiting',coins_used=5 WHERE id=?", (order['id'],))
        self.db.add_coins(self.uid, 10, 'reward')
        self.assertTrue(self.db.spend_coins(self.uid, 5, 'hold', order_id=order['id'])[0])
        self.xui.create_subscription.side_effect = self.mutation
        self.assertEqual(H.approve_order(self.ctx, order['id'], 1), (False, H.ORDER_BUSY))
        self.assert_held(order['id'])
        self.assertFalse(H.do_reject(self.ctx, order['id'], 1, 'reject'))
        self.assertEqual(self.db.get_order(order['id'])['coins_used'], 5)
        self.assertEqual(self.db.release_coins(order['id']), 0)
        self.assertEqual(self.db.get_user_by_id(self.uid)['coins'], 5)
        self.assertEqual(H.approve_order(self.ctx, order['id'], 1), (False, H.ORDER_BUSY))
        self.assertEqual(self.calls, 1)
        H.after_paid_order.assert_not_called()

    def test_prepaid_renewal_holds_reseller_credit_and_auto_retry(self):
        self.db.exec("UPDATE tenants SET parent_id=999,portal_group='reseller',credit=1000 WHERE id=?", (self.tid,))
        self.db.exec('UPDATE plans SET cost=40 WHERE id=?', (self.pid,))
        sid = self.db.exec('INSERT INTO subscriptions '
                           '(tenant_id,user_id,plan_id,client_email,client_uuid,inbound_id,gb,expires_at,auto_renew) '
                           "VALUES (?,?,?,'existing','uuid',1,10,'2020-01-01',1)",
                           (self.tid, self.uid, self.pid))
        sub = self.db.q('SELECT * FROM subscriptions WHERE tenant_id=? AND id=?', (self.tid, sid), one=True)
        self.xui.extend_subscription.side_effect = self.mutation
        with patch.object(H, 'Ctx', return_value=self.ctx), patch.object(D, 'is_prepaid', return_value=True), \
                patch.object(D, 'refund_credit') as refund:
            H.auto_renew_subscription(self.ctx.tenant, self.ctx.bot, sub)
            H.auto_renew_subscription(self.ctx.tenant, self.ctx.bot, sub)
            refund.assert_not_called()
        order = self.db.q('SELECT * FROM orders WHERE tenant_id=?', (self.tid,), one=True)
        self.assert_held(order['id'])
        self.assertEqual(order['renew_sub_id'], sid)
        self.assertEqual(self.db.get_user_by_id(self.uid)['balance'], 400)
        self.assertEqual(D.get_tenant(self.tid)['credit'], 960)
        self.assertFalse(self.db.claim_renewal(sid, stale_minutes=0))
        self.assertEqual(self.calls, 1)
        with patch.object(R.db, 'all_tenants', return_value=[self.ctx.tenant]), patch.object(R, 'Bot'), \
                patch.object(R.handlers, 'auto_renew_subscription') as renew:
            R.run_auto_renew()
            renew.assert_not_called()

    def test_definite_failure_releases_hold_and_refunds(self):
        def fail(*args, **kwargs):
            context = REMOTE.ORDER.get()
            command = f'failed-{self.tid}'
            with REMOTE.connection() as db:
                db.execute('INSERT INTO remote_commands(id,node_id,payload,state,created) '
                           'VALUES (?,\'test\',\'{}\',\'failed\',0)', (command,))
            REMOTE.hold_order(context, command)
            raise H.XUIError('rejected before execution')
        self.xui.create_subscription.side_effect = fail
        result = H.wallet_purchase(self.ctx, self.user, self.pid)
        self.assertEqual(result['why'], 'provision')
        self.assertEqual(self.db.get_user_by_id(self.uid)['balance'], 500)
        self.assertEqual(self.db.q('SELECT status FROM orders WHERE tenant_id=?', (self.tid,), one=True)['status'], 'rejected')
        self.assertIsNone(REMOTE.ORDER.get())

    def test_late_success_does_not_release_interrupted_delivery(self):
        def late(*args, **kwargs):
            try:
                self.mutation()
            except Uncertain:
                with REMOTE.connection() as db:
                    db.execute("UPDATE remote_commands SET state='done' WHERE id=?", (f'{self.tid}-1',))
                raise
        self.xui.create_subscription.side_effect = late
        self.assertEqual(H.wallet_purchase(self.ctx, self.user, self.pid)['why'], 'remote_review')
        oid = self.db.q('SELECT id FROM orders WHERE tenant_id=?', (self.tid,), one=True)['id']
        self.assert_held(oid)
        self.assertEqual(self.db.get_user_by_id(self.uid)['balance'], 400)

    def test_prepaid_create_does_not_refund_reseller(self):
        self.db.exec("UPDATE tenants SET parent_id=999,portal_group='reseller',credit=1000 WHERE id=?", (self.tid,))
        self.db.exec('UPDATE plans SET cost=40 WHERE id=?', (self.pid,))
        self.xui.create_subscription.side_effect = self.mutation
        with patch.object(D, 'is_prepaid', return_value=True), patch.object(D, 'refund_credit') as refund:
            self.assertEqual(H.wallet_purchase(self.ctx, self.user, self.pid)['why'], 'remote_review')
            refund.assert_not_called()
        self.assertEqual(D.get_tenant(self.tid)['credit'], 960)

    def test_trial_retains_claim_on_uncertainty(self):
        self.db.exec('UPDATE plans SET is_trial=1,price=0 WHERE id=?', (self.pid,))
        self.xui.create_subscription.side_effect = self.mutation
        self.assertFalse(H.trial_core(self.ctx, self.user)[0])
        self.assertTrue(self.db.get_user_by_id(self.uid)['trial_used'])
        self.assertFalse(H.trial_core(self.ctx, self.user)[0])
        self.assertEqual(self.calls, 1)

    def test_running_command_keeps_hold_even_without_exception(self):
        order = self.order()
        def pending(ctx, oid):
            try:
                self.mutation()
            except Uncertain:
                with REMOTE.connection() as db:
                    db.execute("UPDATE remote_commands SET state='running' WHERE id=?", (f'{self.tid}-1',))
            return False, 'interrupted'
        with patch.object(H, '_provision', side_effect=pending):
            self.assertFalse(H.provision(self.ctx, order['id'])[0])
        self.assert_held(order['id'])

    def test_scheduler_error_cannot_overwrite_hold(self):
        order = self.order()
        self.db.exec("UPDATE orders SET status='panel_approve' WHERE id=?", (order['id'],))
        def fail(ctx, oid, admin_tg_id):
            self.db.exec("UPDATE orders SET status='remote_review',admin_note='manual check' WHERE id=?", (oid,))
            raise RuntimeError('worker interrupted after dispatch')
        with patch.object(R.handlers, 'approve_order', side_effect=fail), \
                patch.object(R.handlers, 'Ctx', return_value=self.ctx), patch.object(R, 'Bot'), patch.object(R, '_event'):
            R.process_panel_approvals()
        self.assertEqual(self.db.get_order(order['id'])['status'], 'remote_review')

    def test_success_restores_pending_before_close(self):
        def success(*args, **kwargs):
            try:
                self.mutation()
            except Uncertain:
                with REMOTE.connection() as db:
                    db.execute("UPDATE remote_commands SET state='done' WHERE id=?", (f'{self.tid}-1',))
            return {'uuid': 'created', 'sub_url': 'https://example.test/sub', 'expiry_ms': 0}
        self.xui.create_subscription.side_effect = success
        self.assertTrue(H.wallet_purchase(self.ctx, self.user, self.pid)['ok'])
        self.assertEqual(self.db.q('SELECT status FROM orders WHERE tenant_id=?', (self.tid,), one=True)['status'], 'approved')
        self.assertEqual(self.db.get_user_by_id(self.uid)['balance'], 400)
        self.assertIsNone(REMOTE.ORDER.get())

    def portal_credit_case(self, name):
        # Execute the production handler without starting the app or loading unrelated Pro routes.
        source = ROOT / 'backend/pro/resellers.py'
        if not source.exists():
            self.skipTest('Pro reseller handlers are not installed')
        node = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
                    if isinstance(n, ast.FunctionDef) and n.name == name)
        node.decorator_list = []
        node.args.defaults = []
        client = Mock()
        charge = Mock(side_effect=lambda t, amount, note: D.charge_credit(t['id'], amount, note))
        refund = Mock(side_effect=lambda t, amount: D.refund_credit(t['id'], amount, 'definite failure'))
        scope = dict(HTTPException=HTTPException,
                     _portal_group=lambda t: 'reseller',
                     _portal_rates=lambda t: ({}, [{'gb': 10, 'price': 100}]),
                     _price_per_gb=lambda conf: 0, _months_from_days=lambda days: 1,
                     _line_amount=lambda *args: (100, 100, 0, 0),
                     _read_xui_clients=lambda: ([], [], None),
                     _portal_new_email=lambda *args: 'new-client',
                     _portal_xui=lambda t: (client, H.XUIError),
                     _portal_inbound=lambda *args: 1,
                     _portal_inbound_ids=lambda *args: [1],
                     _portal_live=lambda *args: ({'totalGB': 10, 'limitIp': 1}, {}, 'uuid', 1),
                     _gb_of=lambda value: 10, _by_usage=lambda *args: False,
                     _portal_charge=charge, _portal_refund=refund)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
        for failure, expected_status, expected_credit in (
                (Uncertain('execution unknown'), 409, 900),
                (H.XUIError('rejected before execution'), 502, 1000)):
            with self.subTest(handler=name, failure=type(failure).__name__):
                self.db.exec('UPDATE tenants SET credit=1000 WHERE id=?', (self.tid,))
                client.add_client.side_effect = failure
                client.extend_subscription.side_effect = failure
                charge.reset_mock()
                refund.reset_mock()
                with self.assertRaises(HTTPException) as caught:
                    scope[name]({'gb': 10, 'months': 1, 'email': 'existing'}, {'id': self.tid})
                self.assertEqual(caught.exception.status_code, expected_status)
                self.assertEqual(D.get_tenant(self.tid)['credit'], expected_credit)
                self.assertEqual(charge.call_count, 1)
                self.assertEqual(refund.call_count, int(expected_status == 502))

    def test_portal_create_credit_on_uncertain_and_definite_failure(self):
        self.portal_credit_case('portal_create')

    def test_portal_renew_credit_on_uncertain_and_definite_failure(self):
        self.portal_credit_case('portal_renew')


if __name__ == '__main__':
    unittest.main()
