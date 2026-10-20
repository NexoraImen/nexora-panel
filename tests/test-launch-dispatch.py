"""Exercise real polling, durable deduplication, per-chat ordering and restart recovery."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'bot')]
tmp = tempfile.TemporaryDirectory()
os.environ['BOT_DB_PATH'] = str(Path(tmp.name) / 'bot.db')
from bot import run as R

R.db.init_db()
tid = R.db.create_tenant('Polling test', bot_token='1:test')
tenant = R.db.get_tenant(tid)
def update(uid, cid):
    return {'update_id': uid, 'message': {'chat': {'id': cid}, 'text': '/start'}}

seen = []
fast = threading.Event()
class Bot:
    def __init__(self, token):
        self.token = token
    def updates(self, offset=0, timeout=25):
        if not offset:
            return [update(1, 10), update(1, 10), update(2, 10), update(3, 20),
                    {'update_id': 4, 'callback_query': 'bad'}, None]
        assert fast.wait(3), 'A busy chat blocked an unrelated user'
        R._stop.set()
        return []

def dispatch(t, bot, up):
    if up['update_id'] == 1:
        assert fast.wait(3)
    if up['update_id'] == 3:
        fast.set()
    seen.append(up['update_id'])

with patch.object(R, 'Bot', Bot), patch.object(R, '_sync_menu_button'), \
     patch.object(R.handlers, 'Ctx'), patch.object(R.handlers, 'dispatch', side_effect=dispatch):
    R.tenant_loop(tid)
assert sorted(seen) == [1, 2, 3] and seen.index(1) < seen.index(2)
R._stop.clear()
key = 'telegram:1'
with R.db.conn() as cx:
    for uid, state in [(5, 'pending'), (6, 'running')]:
        cx.execute('INSERT INTO bot_updates VALUES(?,?,?,?,?,NULL,?)',
                   (tid, key, uid, json.dumps(update(uid, 10)), state, 10))
with patch.object(R.handlers, 'dispatch', side_effect=lambda t, b, u: seen.append(u['update_id'])):
    dispatcher = R.UpdateDispatcher(tid, Bot('1:rotated'), limit=2)
    dispatcher.recover(tenant)
    dispatcher.admit(tenant, update(1, 10))
    dispatcher.close()
assert seen.count(5) == 1 and 6 not in seen and seen.count(1) == 1
with R.db.conn() as cx:
    assert cx.execute('SELECT status FROM bot_updates WHERE update_id=6').fetchone()['status'] == 'interrupted'

# A full same-chat burst cannot consume other chats' worker slots.
release = threading.Event()
other = threading.Event()
def slow(t, b, u):
    if u['message']['chat']['id'] == 30:
        release.wait(3)
    else:
        other.set()
with patch.object(R.handlers, 'dispatch', side_effect=slow):
    dispatcher = R.UpdateDispatcher(tid, Bot('1:test'), limit=2)
    dispatcher.admit(tenant, update(7, 30))
    assert dispatcher.admit(tenant, update(8, 30))
    assert not dispatcher.admit(tenant, update(9, 30)), 'Per-chat durable backlog must be bounded'
    assert dispatcher.admit(tenant, update(10, 40))
    assert other.wait(2), 'A waiting chat consumed another chat worker slot'
    release.set()
    dispatcher.close()
with patch.object(R.handlers, 'dispatch', side_effect=lambda t, b, u: seen.append(u['update_id'])):
    dispatcher = R.UpdateDispatcher(tid, Bot('1:test'), limit=2)
    with patch.object(dispatcher.pool, 'submit', side_effect=RuntimeError('Rejected')):
        assert dispatcher.admit(tenant, update(11, 50))
        assert not dispatcher.active
    dispatcher.admit(tenant, update(11, 50))
    dispatcher.close()
assert seen.count(11) == 1

# A database failure releases the active chat; a later pump can recover its untouched tail.
dispatcher = R.UpdateDispatcher(tid, Bot('1:test'))
with patch.object(dispatcher.pool, 'submit', side_effect=RuntimeError('Rejected')):
    dispatcher.admit(tenant, update(12, 60))
    dispatcher.admit(tenant, update(13, 60))
with patch.object(R.db, 'conn', side_effect=RuntimeError('Database unavailable')):
    dispatcher.active.add(60)
    dispatcher.drain(60)
assert not dispatcher.active
with patch.object(R.handlers, 'dispatch', side_effect=lambda t, b, u: seen.append(u['update_id'])):
    dispatcher.pump()
    dispatcher.close()
assert seen.count(12) == seen.count(13) == 1
# A week-idle Telegram bot can restart its update-ID sequence below the old watermark.
clock = [1_000_000.0]
epoch_tid = R.db.create_tenant('Idle epoch', bot_token='88:test')
epoch_seen = []
epoch_done = threading.Event()
with R.db.conn() as cx:
    cx.execute('INSERT INTO bot_updates(tenant_id,bot_key,update_id,payload,status,chat_id) '
        "VALUES(?,?,5,?,'running',88)", (epoch_tid, 'telegram:88', json.dumps(update(5, 88))))
    cx.execute('INSERT INTO bot_watermarks VALUES(?,?,?)', (epoch_tid, 'telegram:88', 800000))
class EpochBot(Bot):
    high = low = advanced = False
    def updates(self, offset=0, timeout=25):
        if not self.high:
            assert offset == 0
            self.high = True
            return [update(900000, 88)]
        assert epoch_done.wait(2)
        if not self.advanced:
            clock[0] += 7 * 86400 + 1
            self.advanced = True
            return []
        if not self.low:
            if offset:
                threading.Event().wait(.001)
                return []
            self.low = True
            return [update(50, 89)]
        assert offset == 51
        R._stop.set()
        return []
def epoch_dispatch(t, b, u):
    epoch_seen.append(u['update_id'])
    epoch_done.set()
with patch.object(R.time, 'time', side_effect=lambda: clock[0]), patch.object(R, 'Bot', EpochBot), \
     patch.object(R, '_sync_menu_button'), patch.object(R.handlers, 'Ctx'), \
     patch.object(R.handlers, 'dispatch', side_effect=epoch_dispatch):
    R.tenant_loop(epoch_tid)
assert epoch_seen == [900000, 50]
with R.db.conn() as cx:
    assert cx.execute("SELECT status FROM bot_updates WHERE tenant_id=? AND update_id=5", (epoch_tid,)).fetchone()['status'] == 'interrupted'
    assert cx.execute('SELECT epoch FROM bot_poll_state WHERE tenant_id=?', (epoch_tid,)).fetchone()['epoch'] == 1
R._stop.clear()
# The same update ID is independent across shops and replaced bots, but not token rotation.
other_tid = R.db.create_tenant('Other shop', bot_token='1:other')
identities = []
with patch.object(R.handlers, 'dispatch', side_effect=lambda t, b, u: identities.append((t['id'], b.token, u['update_id']))):
    for shop, token in ((other_tid, '1:other'), (tid, '2:replacement'), (tid, '1:rotated-again')):
        dispatcher = R.UpdateDispatcher(shop, Bot(token))
        dispatcher.admit(R.db.get_tenant(shop), update(1, 10))
        dispatcher.close()
assert identities == [(other_tid, '1:other', 1), (tid, '2:replacement', 1)]

# The actual dispatcher catches handler errors; its explicit failure must survive durable drain.
from types import SimpleNamespace
with patch.object(R.handlers, 'Ctx', return_value=SimpleNamespace(notify_group=lambda *a, **k: None)), \
     patch.object(R.handlers, '_on_message', side_effect=ValueError('Broken handler')) as handler:
    dispatcher = R.UpdateDispatcher(tid, Bot('1:test'))
    dispatcher.admit(tenant, update(20000, 77))
    dispatcher.close()
assert handler.call_count == 1
with R.db.conn() as cx:
    failed = cx.execute('SELECT status,payload FROM bot_updates WHERE tenant_id=? AND update_id=20000', (tid,)).fetchone()
    assert failed['status'] == 'interrupted' and json.loads(failed['payload'])['update_id'] == 20000

# A failed outcome write leaves running evidence; the next pump quarantines it before its tail.
from contextlib import contextmanager
dispatcher = R.UpdateDispatcher(tid, Bot('1:test'))
with patch.object(dispatcher.pool, 'submit', side_effect=RuntimeError('Rejected')):
    dispatcher.admit(tenant, update(20001, 78))
    dispatcher.admit(tenant, update(20002, 78))
real_conn = R.db.conn
class OutcomeFault:
    def __init__(self, cx):
        self.cx = cx
    def execute(self, sql, *args):
        if "SET status='done'" in sql:
            raise RuntimeError('Outcome write failed')
        return self.cx.execute(sql, *args)
@contextmanager
def fault_conn():
    with real_conn() as cx:
        yield OutcomeFault(cx)
outcomes = []
with patch.object(R.handlers, 'dispatch', side_effect=lambda t, b, u: outcomes.append(u['update_id'])):
    with patch.object(R.db, 'conn', side_effect=fault_conn):
        dispatcher.active.add(78)
        dispatcher.drain(78)
    with real_conn() as cx:
        assert cx.execute('SELECT status FROM bot_updates WHERE tenant_id=? AND update_id=20001', (tid,)).fetchone()['status'] == 'running'
    dispatcher.active.add(78)
    dispatcher.pump()
    with real_conn() as cx:
        assert cx.execute('SELECT status FROM bot_updates WHERE tenant_id=? AND update_id=20001', (tid,)).fetchone()['status'] == 'running', 'Active chat claims must not be quarantined'
    dispatcher.active.remove(78)
    dispatcher.pump()
    dispatcher.close()
assert outcomes == [20001, 20002]
with real_conn() as cx:
    row = cx.execute('SELECT status,payload FROM bot_updates WHERE tenant_id=? AND update_id=20001', (tid,)).fetchone()
    assert row['status'] == 'interrupted' and row['payload'] != '{}'

prune_tid = R.db.create_tenant('Retention', bot_token='99:test')
dispatcher = R.UpdateDispatcher(prune_tid, Bot('99:test'))
with R.db.conn() as cx:
    cx.executemany("INSERT INTO bot_updates(tenant_id,bot_key,update_id,payload,status,chat_id) VALUES(?,? ,?,'{}','done',1)",
                   [(prune_tid, dispatcher.key, n) for n in range(1, 10006)])
    cx.execute("INSERT INTO bot_updates(tenant_id,bot_key,update_id,payload,status,chat_id) VALUES(?,?,0,'evidence','interrupted',1)", (prune_tid, dispatcher.key))
dispatcher.prune()
dispatcher.close()
with R.db.conn() as cx:
    assert cx.execute("SELECT COUNT(*) FROM bot_updates WHERE tenant_id=? AND status='done'", (prune_tid,)).fetchone()[0] == 10000
    assert cx.execute("SELECT payload FROM bot_updates WHERE tenant_id=? AND status='interrupted'", (prune_tid,)).fetchone()[0] == 'evidence'

batch_tid = R.db.create_tenant('Batch order', bot_token='100:test')
attempts = []
original_admit = R.UpdateDispatcher.admit
def reject_once(self, t, up):
    attempts.append(up['update_id'])
    if attempts == [1, 2]:
        return False
    return original_admit(self, t, up)
class BatchBot(Bot):
    polls = 0
    def updates(self, offset=0, timeout=25):
        self.polls += 1
        if self.polls == 1:
            assert offset == 0
            return [update(1, 1), update(2, 1), update(3, 1)]
        if self.polls == 2:
            assert offset == 2
            return [update(2, 1), update(3, 1)]
        assert offset == 4
        R._stop.set()
        return []
with patch.object(R, 'Bot', BatchBot), patch.object(R.UpdateDispatcher, 'admit', reject_once), \
     patch.object(R, '_sync_menu_button'), patch.object(R.handlers, 'Ctx'), patch.object(R.handlers, 'dispatch'):
    R.tenant_loop(batch_tid)
R._stop.clear()
assert attempts == [1, 2, 2, 3], attempts
print('Actual polling, admission rejection/starvation, durable restart and week-idle epoch checks passed')
