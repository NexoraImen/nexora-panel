"""Legacy evidence survives interrupted verified migration, resumption and a full backup."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch
import zipfile
from contextlib import closing

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'bot'), str(root / 'backend')]
tmp = tempfile.TemporaryDirectory()
data = Path(tmp.name)
os.environ['BOT_DB_PATH'] = str(data / 'bot.db')
from bot import db, media, core
import backup
db.init_db()
tid = db.create_tenant('Migration', bot_token='1:test', owner_tg_id=1)
d = db.TenantDB(tid)
d.create_user(123, None, 'Customer')
uid = d.get_user(123)['id']
image = b'\x89PNG\r\n\x1a\n' + b'original evidence'
for folder in ('receipts', 'chat', 'aff-receipts', 'logos', 'avatars'):
    (data / folder).mkdir()
files = [data / 'receipts/shared.png', data / 'chat/photo.png', data / 'aff-receipts/payout.png',
         data / f'logos/{tid}.png', data / f'avatars/{tid}_{uid}_legacy.png']
channel_dir = core.channel_photo_dir()
channel_dir.mkdir(parents=True, exist_ok=True)
files.append(channel_dir / 'channel.png')
for file in files:
    file.write_bytes(image)
oids = [d.create_order(uid, None, 100, 100)['id'] for _ in range(2)]
for oid in oids:
    d.exec("UPDATE orders SET receipt_type='photo',receipt_file='local:shared.png' WHERE tenant_id=? AND id=?", (tid, oid))
d.chat_add(uid, 'user', 'Evidence', photo='/api/public/chat-photo/photo.png')
d.channel_add('Old post', photo='channel.png')
aid = d.exec("INSERT INTO affiliates(tenant_id,name,code) VALUES(?,'Affiliate','test')", (tid,))
d.exec("INSERT INTO affiliate_payouts(tenant_id,affiliate_id,amount,receipt) VALUES(?,?,10,'payout.png')", (tid, aid))
spec = importlib.util.spec_from_file_location('migration', root / 'scripts/migrate-telegram-media.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
class Bot:
    uploads = 0
    fail_once = True
    def __init__(self, token):
        pass
    def send_doc_bytes(self, *args, **kwargs):
        Bot.uploads += 1
        return {'document': {'file_id': f'file{Bot.uploads}'}}
    def file_bytes(self, *args, **kwargs):
        if Bot.fail_once:
            Bot.fail_once = False
            raise TimeoutError('Lost verification response')
        return image
with patch.object(media, 'Bot', Bot):
    first = migration.migrate(data)
    assert first['failures'] and d.get_order(oids[0])['receipt_file'] == 'local:shared.png'
    assert all(file.read_bytes() == image for file in files)
    uploaded = Bot.uploads
    second = migration.migrate(data)
    assert not second['failures'] and second['originals_removed'] == 0
    assert Bot.uploads == uploaded, 'Restart must reuse the known uploaded file ID'
    for oid in oids:
        assert media.receipt_bytes(d.get_order(oid)['receipt_file'], tid) == image
    assert not migration.migrate(data)['completed']
    assert all(file.read_bytes() == image for file in files)

# The bot database snapshot includes the durable reference and bindings, never image bytes.
archive = data / 'backup.zip'
backup.build(data, {'bot.db': data / 'bot.db'}, 'test', archive)
with zipfile.ZipFile(archive) as z:
    db_entry = next(n for n in z.namelist() if n.endswith('bot.db'))
    restored = data / 'restored.db'
    restored.write_bytes(z.read(db_entry))
with closing(sqlite3.connect(restored)) as cx:
    assert cx.execute("SELECT COUNT(*) FROM media_assets WHERE state='ready'").fetchone()[0] >= 6
    assert cx.execute('SELECT COUNT(*) FROM media_bindings').fetchone()[0] == 2

# A newer binding or explicit deletion can win while a legacy upload is in flight.
real_retain = media.retain
with patch.object(media, 'Bot', Bot):
    newer = real_retain(tid, 'avatar', 1001, image, request_id='newer-upload')
    for race_uid, deleted in ((1001, False), (1002, True)):
        source = data / f'avatars/{tid}_{race_uid}_legacy.png'
        source.write_bytes(image)
        def racing_retain(shop, purpose, owner, blob, **kwargs):
            ref = real_retain(shop, purpose, owner, blob, **kwargs)
            if purpose == 'avatar' and owner == race_uid:
                if deleted:
                    media.clear(shop, purpose, owner)
                else:
                    media.bind(shop, purpose, owner, newer)
            return ref
        with patch.object(media, 'retain', side_effect=racing_retain):
            assert migration.migrate(data)['failures']
        assert media.current(tid, 'avatar', race_uid) == ('' if deleted else newer)
        assert source.read_bytes() == image

# A restore can replace the same DB path while the media module remains loaded.
with closing(sqlite3.connect(db.DB_PATH)) as cx:
    cx.executescript('DROP TABLE media_bindings; DROP TABLE media_assets;')
for purpose in ('avatar', 'logo'):
    media.clear(tid, purpose, uid)
    assert media.current(tid, purpose, uid) == '', 'Legacy deletion initializes schema before its first retain'
with patch.object(media, 'Bot', Bot):
    assert media.retain(tid, 'chat', uid, image).startswith('media:')
print('Interrupted migration, original/shared evidence, resumable verification and backup metadata passed')
