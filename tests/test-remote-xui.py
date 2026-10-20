"""Exercise pairing, immutable snapshots and command ownership without real servers."""
import concurrent.futures
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import remote_xui as R
from backend import backup as B


def refused(fn, *args):
    try:
        fn(*args)
    except R.RemoteError:
        return
    raise AssertionError('Unsafe request accepted')


with tempfile.TemporaryDirectory() as tmp:
    os.environ['CONFIG_PATH'] = str(Path(tmp) / 'config.json')
    pair = R.pair('Test source', 'iran')
    auth = R.enroll(pair['code'])
    node = auth['node_id']
    assert R.authenticate(auth['token'])['id'] == node
    refused(R.enroll, pair['code'])
    refused(R.select, 'remote', 'foreign', node)
    path = Path(tmp) / 'fixture.db'
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE inbounds(id INTEGER PRIMARY KEY,settings TEXT)')
        db.commit()
    body = path.read_bytes()
    R.receive_snapshot(node, body, 1, time.time())
    R.select('remote', 'foreign', node, 'http://localhost:1234')
    assert R.active()
    token = R.PIN.set({})
    first = R.snapshot_path()
    R.receive_snapshot(node, body, 2, time.time())
    assert R.snapshot_path() == first and first.exists()
    R.PIN.reset(token)
    assert R.snapshot_path() != first
    older = R.SnapshotClients([], first)
    newer = R.SnapshotClients([], R.snapshot_path())
    with R.accounting_generation(newer):
        pass
    def consume_old():
        with R.accounting_generation(older):
            raise AssertionError('An older snapshot changed accounting baselines')
    refused(consume_old)
    refused(R.receive_snapshot, node, body, 1, time.time())
    refused(R.receive_snapshot, node, body, 3, time.time() - 100)
    refused(R.receive_snapshot, node, b'not sqlite', 3, time.time())
    for bad in ('https://example.invalid/panel/api/test', '/panel/api/../login',
                '/panel/api/%2e%2e/login', '/panel/api/%252e%252e/login', '/login'):
        refused(R.validate_command, 'POST', bad, {})
    other = R.enroll(R.pair('Other source', 'iran')['code'])['node_id']
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(R.rpc, node, 'GET', '/panel/api/inbounds/list', {}, 3)
        deadline = time.monotonic() + 2
        commands = []
        while not commands and time.monotonic() < deadline:
            commands = R.poll(node, [])['commands']
            time.sleep(.01)
        assert commands
        command = commands[0]
        result = {'id': command['id'], 'state': 'done',
                  'response': {'status': 200, 'body': '{"success":true}'}}
        R.poll(other, [result])
        assert not future.done(), 'Another agent completed an unowned command'
        assert R.poll(node, [])['commands'][0]['id'] == command['id']
        R.poll(node, [result])
        assert future.result()['status'] == 200
        future = pool.submit(R.rpc, node, 'POST', '/panel/api/inbounds/addClient', {}, .4)
        commands = []
        deadline = time.monotonic() + 1
        while not commands and time.monotonic() < deadline:
            commands = R.poll(node, [])['commands']
            time.sleep(.01)
        assert commands
        command = commands[0]
        try:
            future.result()
        except R.RemoteUncertain:
            pass
        else:
            raise AssertionError('Dispatched timeout lost its uncertainty marker')
        refused(R.resolve, command['id'])
        R.poll(node, [{'id': command['id'], 'state': 'done',
                       'response': {'status': 200, 'body': '{"success":true}'}}])
        assert R.status()['uncertain'], 'Late success must not silently permit a repeated mutation'
        R.resolve(command['id'])
        assert not R.status()['uncertain']
    manifest = B.build(tmp, {'remote-xui.db': Path(tmp) / 'remote-xui.db'},
                       '2.4.0', Path(tmp) / 'backup.zip')
    stored = [f['path'] for f in manifest['files'] if f['path'].startswith('remote-xui/')]
    assert stored == [f'remote-xui/{node}-2.db'], 'Backup must include the selected snapshot, not its old cache'
    B.verify(Path(tmp) / 'backup.zip', '2.4.0')
    with R.connection() as db:
        db.execute('UPDATE remote_nodes SET snapshot_at=? WHERE id=?', (time.time() - 100, node))
    refused(R.snapshot_path)
    R.revoke(node)
    refused(R.authenticate, auth['token'])
    refused(R.poll, node, [])
    renewed = R.enroll(R.repair_pair(node)['code'])
    assert renewed['node_id'] == node and renewed['sequence_floor'] == 2
    refused(R.authenticate, auth['token'])
    refused(R.snapshot_path)
    R.receive_snapshot(node, body, renewed['sequence_floor'] + 1, time.time())
    R.select('remote', 'foreign', node)
    assert R.authenticate(renewed['token'])['id'] == node
    assert R.settings()['node_id'] == node, 'Re-enrollment must retain the accounting source identity'
    R.select('local', 'foreign', None)
    assert R.snapshot_path() is None

print('Remote source safety checks passed')
