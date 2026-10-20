"""Remote enrollment and admin actions pass the real hidden-path/auth boundary."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import sqlite3
import time
from contextlib import closing
from unittest.mock import patch

tmp = tempfile.mkdtemp(prefix='remote_api_')
os.environ.update(CONFIG_PATH=str(Path(tmp) / 'config.json'),
    BOT_DB_PATH=str(Path(tmp) / 'bot.db'), BILLING_DB_PATH=str(Path(tmp) / 'billing.db'),
    TUNNEL_DB_PATH=str(Path(tmp) / 'tunnels.db'),
    ADMIN_PATH_FILE=str(Path(tmp) / 'admin-path.json'), NEXORA_ADMIN_PASSWORD='testpw')
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'backend'), str(root / 'bot')]
import app as A


async def call(path, method='GET', body=None, headers=None):
    data = b'' if body is None else json.dumps(body).encode()
    scope = dict(type='http', http_version='1.1', method=method, path=path,
        raw_path=path.encode(), query_string=b'', root_path='', scheme='https',
        server=('central.example', 443), client=('127.0.0.1', 1234),
        headers=[(k.lower().encode(), v.encode()) for k, v in
                 {'Content-Type': 'application/json', **(headers or {})}.items()])
    out = {'body': b''}
    delivered = False
    async def receive():
        nonlocal delivered
        if delivered:
            await asyncio.Event().wait()
        delivered = True
        return {'type': 'http.request', 'body': data, 'more_body': False}
    async def send(message):
        if message['type'] == 'http.response.start':
            out['status'] = message['status']
        elif message['type'] == 'http.response.body':
            out['body'] += message.get('body', b'')
    await A.app(scope, receive, send)
    return out


async def checks():
    admin = '/api/admin/remote-xui'
    headers = {'X-Admin-Path': A.admin_path(), 'X-Admin-Password': A._INTERNAL_PW}
    assert (await call(admin))['status'] == 404
    assert (await call(admin, headers={'X-Admin-Path': A.admin_path()}))['status'] in (401, 422)
    result = await call(admin, headers=headers)
    assert result['status'] == 200 and json.loads(result['body'])['mode'] == 'local'
    assert (await call('/api/xui-agent/poll', 'POST', {'results': []}))['status'] == 401
    pair = A.REMOTE.pair('API test', 'iran')
    enrolled = await call('/api/xui-agent/enroll', 'POST', {'code': pair['code']})
    assert enrolled['status'] == 200
    credentials = json.loads(enrolled['body'])
    assert (await call('/api/xui-agent/enroll', 'POST', {'code': pair['code']}))['status'] == 401
    bearer = {'Authorization': 'Bearer ' + credentials['token']}
    assert (await call('/api/xui-agent/poll', 'POST', {'results': []}, bearer))['status'] == 200
    assert (await call('/api/admin/bot/settings', 'PUT', {'name': 'Central test'}, headers))['status'] == 200
    sample = Path(tmp) / 'source.db'
    with closing(sqlite3.connect(sample)) as db:
        db.execute('CREATE TABLE inbounds(id INTEGER PRIMARY KEY,settings TEXT)')
        db.commit()
    A.REMOTE.receive_snapshot(pair['node_id'], sample.read_bytes(), 1, time.time())
    selection = {'mode': 'remote', 'region': 'foreign', 'node_id': pair['node_id']}
    with patch.object(A.REMOTE, 'rpc', return_value={'status': 200, 'body': '<html>Login</html>'}):
        assert (await call(admin, 'PUT', selection, headers))['status'] == 409
        assert A.REMOTE.settings()['mode'] == 'local'
    with patch.object(A.REMOTE, 'rpc', return_value={'status': 200, 'body': '{"success":true,"obj":[]}'}):
        assert (await call(admin, 'PUT', selection, headers))['status'] == 200
    assert A._root_tenant_row()['panel_url'] == 'agent://' + pair['node_id']
    assert (await call(admin + '/node/' + pair['node_id'], 'DELETE', headers=headers))['status'] == 200
    assert (await call('/api/xui-agent/poll', 'POST', {'results': []}, bearer))['status'] == 401


asyncio.run(checks())
print('Remote API authorization checks passed')
