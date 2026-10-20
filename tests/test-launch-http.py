"""Launch settings and private images pass through the real ASGI authentication boundary."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
tmp = tempfile.TemporaryDirectory()
os.environ.update(CONFIG_PATH=str(Path(tmp.name) / 'config.json'),
    BOT_DB_PATH=str(Path(tmp.name) / 'bot.db'), BILLING_DB_PATH=str(Path(tmp.name) / 'billing.db'),
    TUNNEL_DB_PATH=str(Path(tmp.name) / 'tunnels.db'), NEXORA_ADMIN_PASSWORD='testpw',
    NEXORA_LICENSE_DIR=str(Path(tmp.name) / 'license'),
    ADMIN_PATH_FILE=str(Path(tmp.name) / 'admin-path.json'))
sys.path[:0] = [str(root), str(root / 'backend'), str(root / 'bot')]
import app as A
from bot import media


async def call(path, method='GET', body=None, headers=None):
    content = json.dumps(body).encode() if body is not None else b''
    scope = dict(type='http', http_version='1.1', method=method, path=path, raw_path=path.encode(),
        query_string=b'', root_path='', scheme='https', server=('test.example', 443),
        client=('127.0.0.1', 1234), headers=[(k.lower().encode(), v.encode()) for k, v in
            {'Content-Type': 'application/json', **(headers or {})}.items()])
    out = {'body': b''}
    delivered = False
    async def receive():
        nonlocal delivered
        if delivered:
            await asyncio.Event().wait()
        delivered = True
        return {'type': 'http.request', 'body': content, 'more_body': False}
    async def send(message):
        if message['type'] == 'http.response.start':
            out['status'] = message['status']
            out['headers'] = dict(message['headers'])
        elif message['type'] == 'http.response.body':
            out['body'] += message.get('body', b'')
    await A.app(scope, receive, send)
    return out


async def checks():
    auth = {'X-Admin-Path': A.admin_path(), 'X-Admin-Password': A._INTERNAL_PW}
    assert (await call('/api/admin/bot/settings', 'PUT', {'name': 'Owner'}, auth))['status'] == 200
    t = A._root_tenant_row()
    h = A._bot_handlers()
    h.DB.update_tenant(t['id'], bot_token='1:test', owner_tg_id=1)
    st = {'cards': [{'number': 'test'}], 'coins': {'enabled': True}, 'brand': 'Original',
          'ai': {'enabled': True, 'base_url': 'https://provider.example/v1', 'model': 'test', 'api_key': 'private-test-key'}}
    h.DB.save_tenant_settings(t['id'], st)
    response = await call('/api/admin/bot/settings', headers=auth)
    saved = json.loads(response['body'])['tenant']['settings']
    assert saved['cards'] == st['cards'] and saved['ai']['api_key'].endswith('…')
    assert b'private-test-key' not in response['body']
    if A.PRO_LOADED:
        with patch.object(A.LIC, 'allowed', return_value=True):
            # A channel-page save races an unrelated shop edit: only AI fields may change.
            changed = {**st, 'brand': 'Concurrent edit'}
            h.DB.save_tenant_settings(t['id'], changed)
            assert (await call('/api/admin/channel/ai', 'PUT', {'tone': 'Short', 'api_key': ''}, auth))['status'] == 200
            fresh = h.DB.tenant_settings(t['id'])
            assert fresh['brand'] == 'Concurrent edit' and fresh['ai']['api_key'] == 'private-test-key'
            assert fresh['ai']['model'] == 'test' and fresh['ai']['tone'] == 'Short'
            assert (await call('/api/admin/channel/ai', 'PUT', {'tone': 'X'}))['status'] == 404
            assert (await call('/api/admin/channel/automation', 'PUT', {'enabled': True, 'topic': '', 'cadence_minutes': 1}, auth))['status'] == 400
            d = h.DB.TenantDB(t['id'])
            d.channel_automation_save(False, 'Saved topic', 360)
            fresh['channel_id'] = '@test_channel'
            h.DB.save_tenant_settings(t['id'], fresh)
            response = await call('/api/admin/channel/automation', 'PUT', {'enabled': True}, auth)
            assert response['status'] == 200, response
            cfg = json.loads(response['body'])['automation']
            assert cfg['topic'] == 'Saved topic' and cfg['cadence_minutes'] == 360
            response = await call('/api/admin/channel/automation', 'PUT', {'enabled': False}, auth)
            cfg = json.loads(response['body'])['automation']
            assert not cfg['enabled'] and cfg['topic'] == 'Saved topic' and cfg['cadence_minutes'] == 360

    media.db.init_db()
    # These are the same database, imported under the application's two supported names.
    media.db.update_tenant(t['id'], bot_token='1:test', owner_tg_id=1)
    image = b'\x89PNG\r\n\x1a\n' + b'image'
    A.AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    legacy = f"{t['id']}_5_legacy.png"
    (A.AVATAR_DIR / legacy).write_bytes(image)
    legacy_path = '/api/public/avatar/' + legacy
    assert (await call(legacy_path))['status'] == 404
    response = await call(legacy_path, headers=auth)
    assert response['status'] == 200 and response['body'] == image
    assert response['headers'][b'cache-control'] == b'private, no-store'
    if A.PRO_LOADED:
        with patch.object(A, 'mini_user', return_value=({'id': t['id']}, {'id': 6})):
            assert (await call(legacy_path, headers={'X-Telegram-Init-Data': 'wrong-user'}))['status'] == 404
        with patch.object(A, 'mini_user', return_value=({'id': t['id']}, {'id': 5})):
            response = await call(legacy_path, headers={'X-Telegram-Init-Data': 'own-user'})
            assert response['body'] == image and response['headers'][b'cache-control'] == b'private, no-store'
    class Bot:
        def __init__(self, token):
            pass
        def send_doc_bytes(self, *a, **k):
            return {'document': {'file_id': 'file'}}
        def file_bytes(self, *a, **k):
            return image
    with patch.object(media, 'Bot', Bot):
        ref = media.retain(t['id'], 'chat', 5, image)
        path = media.url(ref)
        assert (await call(path))['status'] == 404
        assert (await call(path, headers={'X-Admin-Password': A._INTERNAL_PW}))['status'] == 404
        assert (await call(path, headers=auth))['body'] == image
        assert (await call('/api/public/media/' + ref[6:]))['status'] == 404
        for tid in (2, 3):
            with patch.object(A, 'portal_tenant', return_value={'id': tid}, create=True):
                assert (await call(path, headers={'X-Portal-Token': 'other-shop'}))['status'] == 404
        with patch.object(A, 'PRO_LOADED', False):
            assert (await call(path, headers={'X-Portal-Token': 'unavailable-pro'}))['status'] == 404
        if A.PRO_LOADED:
            with patch.object(A, 'mini_user', return_value=({'id': t['id']}, {'id': 6})):
                assert (await call(path, headers={'X-Telegram-Init-Data': 'other-user'}))['status'] == 404
            with patch.object(A, 'mini_user', return_value=({'id': t['id']}, {'id': 5})):
                assert (await call(path, headers={'X-Telegram-Init-Data': 'same-user'}))['body'] == image
        else:
            assert (await call(path, headers={'X-Telegram-Init-Data': 'unavailable-pro'}))['status'] == 404
        with patch.object(Bot, 'file_bytes', side_effect=h.TelegramError('https://api.telegram.org/file/botSECRET/image')):
            failure = await call(path, headers=auth)
            assert failure['status'] == 404 and b'SECRET' not in failure['body'] and b'https://' not in failure['body']
            assert 'تصویر' in json.loads(failure['body'])['detail']
        if A.PRO_LOADED:
            import base64
            chan = h.pro('channel')
            payload = {'body': 'Post', 'photo': base64.b64encode(image).decode()}
            before = len(d.channel_posts())
            with patch.object(A.LIC, 'allowed', return_value=True), patch.object(chan, 'channel_photo_bytes', side_effect=TimeoutError('unavailable')):
                failure = await call('/api/admin/channel/post', 'POST', payload, auth)
                assert failure['status'] == 503 and len(d.channel_posts()) == before
            with patch.object(A.LIC, 'allowed', return_value=True), patch.object(chan, 'channel_photo_bytes', return_value=image), \
                 patch.object(chan, 'channel_send', return_value=(True, 444)):
                retry = await call('/api/admin/channel/post', 'POST', payload, auth)
                assert retry['status'] == 200 and json.loads(retry['body'])['post']['status'] == 'sent'
            with patch.object(A.LIC, 'allowed', return_value=True), patch.object(media, 'retain',
                    side_effect=media.MediaError('destination', 'Shop media destination is not configured')):
                failure = await call('/api/admin/channel/post', 'POST',
                    {'body': 'Post', 'photo': base64.b64encode(image).decode()}, auth)
                assert failure['status'] == 503 and b'Shop media' not in failure['body']
                assert 'مقصد' in json.loads(failure['body'])['detail']


asyncio.run(checks())
print('Real ASGI settings preservation, key secrecy and private media ownership checks passed')
