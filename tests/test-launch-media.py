"""Media references survive same-bot rotation, isolate shops, and never replay unknown uploads."""
import os
from pathlib import Path
import sys
import tempfile
import json
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'bot')]
tmp = tempfile.TemporaryDirectory()
os.environ['BOT_DB_PATH'] = str(Path(tmp.name) / 'bot.db')
from bot import db, media
db.init_db()
owner = db.create_tenant('Owner', bot_token='1:first', owner_tg_id=1)
shops = [owner] + [db.create_tenant('Reseller', bot_token=f'{n}:key', owner_tg_id=n, parent_id=owner) for n in (2, 3)]
image = b'\x89PNG\r\n\x1a\n' + b'image'
class Bot:
    uploads = 0
    def __init__(self, token):
        self.token = token
    def send_doc_bytes(self, target, blob, filename, topic_id=None):
        Bot.uploads += 1
        return {'document': {'file_id': 'file', 'file_unique_id': 'unique'}}
    def file_bytes(self, fid, limit):
        return image

with patch.object(media, 'Bot', Bot):
    for tid in shops:
        ref = media.retain(tid, 'chat', 123, image, request_id='one')
        assert media.retain(tid, 'chat', 123, image, request_id='one') == ref
        assert media.read(ref, tid) == image
        assert not media.asset(ref, tid + 100)
        try:
            media.read(ref, tid, public=True)
            raise AssertionError('Support photos must require authentication')
        except ValueError:
            pass
        tenant = db.get_tenant(tid)
        identity = tenant['bot_token'].split(':')[0]
        db.update_tenant(tid, bot_token=identity + ':rotated')
        assert media.read(ref, tid) == image
        db.update_tenant(tid, bot_token='999:replacement')
        try:
            media.read(ref, tid)
            raise AssertionError('Replacement bot must not read old references')
        except ValueError:
            pass
        db.update_tenant(tid, bot_token=tenant['bot_token'])
    assert Bot.uploads == 3
    db.update_tenant(owner, owner_tg_id=None, admin_group_id=None)
    try:
        media.retain(owner, 'receipt', 5, image)
    except ValueError:
        pass
    db.update_tenant(owner, owner_tg_id=1)
    assert media.retain(owner, 'receipt', 5, image).startswith('media:')
    before = Bot.uploads
    with patch.object(Bot, 'send_doc_bytes', side_effect=TimeoutError):
        try:
            media.retain(owner, 'receipt', 6, image)
        except ValueError:
            pass
    try:
        media.retain(owner, 'receipt', 6, image)
        raise AssertionError('An uncertain upload must not be repeated')
    except ValueError:
        pass
    assert Bot.uploads == before
    with patch.object(Bot, 'file_bytes', side_effect=TimeoutError):
        try:
            media.retain(owner, 'receipt', 7, image)
        except ValueError:
            pass
    before = Bot.uploads
    with db.conn() as cx:
        row = cx.execute("SELECT state,file_id FROM media_assets WHERE owner_id=7").fetchone()
        assert row['state'] == 'verifying' and row['file_id'] == 'file'
    assert media.retain(owner, 'receipt', 7, image).startswith('media:')
    assert Bot.uploads == before, 'Retry must verify the known file ID without uploading again'
    with db.conn() as cx:
        assert cx.execute("SELECT COUNT(*) FROM media_assets WHERE state='unknown'").fetchone()[0] == 1
    assert not list(Path(tmp.name).glob('*.png'))
    from bot import handlers as H
    class ReceiptBot(Bot):
        attempts = []
        notices = []
        def send_doc_bytes(self, target, blob, filename, topic_id=None):
            self.attempts.append(topic_id)
            if topic_id == 7:
                raise H.TelegramError('Bad Request: message thread not found', 400)
            return {'message_id': 99, 'document': {'file_id': 'file'}}
        def create_topic(self, *a, **k):
            return {'message_thread_id': 9}
        def call(self, method, **payload):
            self.notices.append((method, payload))
            return True
    db.update_tenant(owner, admin_group_id=-100, topics={'receipts': 7})
    bot = ReceiptBot('1:first')
    receipt_ref = media.retain(owner, 'receipt', 8, image, bot=bot)
    assert bot.attempts == [7, 9], 'Only a known rejected topic upload may retry'
    ctx = SimpleNamespace(tid=owner, bot=bot, staff_chat=lambda key: (-100, 9))
    assert media.receipt_notice(ctx, receipt_ref, '🧾' * 1500, {'inline_keyboard': []})
    assert len(bot.notices) == 1 and bot.notices[0][0] == 'editMessageCaption'
    assert len(bot.notices[0][1]['caption'].encode('utf-16-le')) <= 2000

    # Replaced/missing attachments never crash the order callback or remove its actions.
    d = db.TenantDB(owner)
    d.create_user(123, None, 'Buyer')
    user = d.get_user(123)
    notices = []
    receipt_ctx = SimpleNamespace(tid=owner, db=d, bot=bot, staff_chat=lambda key: (-100, 9),
        notify_group=lambda *a, **k: notices.append((a, k)))
    for deleted in (True, False):
        accepted_order = d.create_order(user['id'], None, 10, 10)
        accepted_ref = media.retain(owner, 'receipt', accepted_order['id'], image, bot=bot)
        notice_patch = (patch.object(media, 'receipt_notice', side_effect=H.TelegramError('message to edit not found', 400))
                        if deleted else patch.object(media, 'receipt_notice', return_value=False))
        with notice_patch, patch.object(H, 'pro', return_value=None):
            assert H.receipt_submit(receipt_ctx, user, accepted_order['id'], 'photo', rfile=accepted_ref)[0]
        assert d.get_order(accepted_order['id'])['status'] == 'awaiting'
        assert notices[-1][1]['keyboard']['inline_keyboard'][0][0]['callback_data'] == f"ap:{accepted_order['id']}"
        assert not notices[-1][1].get('photo'), 'Lost archive uses text/actions, never media: as a Telegram photo ID'
    order = d.create_order(user['id'], None, 10, 10)
    sent = []
    fallback_bot = SimpleNamespace(send=lambda *a, **k: sent.append((a, k)),
        send_photo=lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    ctx = SimpleNamespace(tid=owner, db=d, bot=fallback_bot, is_admin=lambda uid: True)
    db.update_tenant(owner, bot_token='999:replaced')
    for ref in (receipt_ref, 'local:missing.png', 'unavailable-file-id'):
        d.exec("UPDATE orders SET receipt_type='photo',receipt_file=? WHERE tenant_id=? AND id=?", (ref, owner, order['id']))
        H.admin_order_detail(ctx, {'tg_id': 1}, 1, None, order['id'])
        assert 'تصویر رسید در دسترس نیست' in sent[-1][0][1] and sent[-1][1].get('keyboard')

    # Exercise the documented operator recovery against an isolated unknown claim.
    db.update_tenant(owner, bot_token='1:first')
    with db.conn() as cx:
        unknown = dict(cx.execute("SELECT * FROM media_assets WHERE state='unknown'").fetchone())
    class RecoveryBot(Bot):
        content = image
        def updates(self, **kwargs):
            return [{'update_id': 90001, 'message': {'message_id': 42, 'chat': {'id': 1, 'type': 'private'},
                'from': {'id': 1}, 'forward_origin': {'type': 'user'},
                'document': {'file_id': 'file', 'file_unique_id': 'unique'}}}]
        def file_bytes(self, *a, **k):
            return self.content
    runbook = root / 'plans/telegram-launch-release-runbook.md'
    if runbook.is_file():  # Internal operator documentation is excluded from Community exports.
        snippet = runbook.read_text(encoding='utf-8').split('```python\n', 1)[1].split('```', 1)[0]
        snippet = snippet.replace('tenant_id = 123', f'tenant_id = {owner}').replace(
            "claim_id = 'replace-with-reviewed-32-character-media-id'", f"claim_id = {unknown['id']!r}")
        before = Bot.uploads
        import bot.tg as telegram
        with patch.object(telegram, 'Bot', RecoveryBot):
            RecoveryBot.content = b'mismatch'
            try:
                exec(compile(snippet, '<operator recovery>', 'exec'), {})
            except AssertionError as exc:
                assert 'mismatch' in str(exc).lower()
            else:
                raise AssertionError('Reconciliation accepted different bytes')
            assert media.asset(unknown['id'])['state'] == 'unknown' and not media.asset(unknown['id'])['file_id']
            RecoveryBot.content = image
            exec(compile(snippet, '<operator recovery>', 'exec'), {})
        assert Bot.uploads == before and media.asset(unknown['id'])['state'] == 'ready'
        with db.conn() as cx:
            assert cx.execute('SELECT status FROM bot_updates WHERE update_id=90001').fetchone()[0] == 'interrupted'
print('Media tenancy, token rotation/replacement, private reads, retry and uncertain retention passed')
