"""Tenant/bot-scoped Telegram references; upload claims survive process failure."""
import hashlib
import json
import secrets
import sqlite3
import threading

from bot import db
from bot.tg import Bot

PREFIX = 'media:'
MAX_BYTES = 3 * 1024 * 1024
PUBLIC = {'logo'}
_initialized = set()
_schema_lock = threading.Lock()


class MediaError(ValueError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def ensure_schema():
    with _schema_lock:
        path = str(db.DB_PATH.resolve())
        if path in _initialized:
            with db.conn() as cx:
                cols = {r['name'] for r in cx.execute('PRAGMA table_info(media_assets)')}
                bindings = cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media_bindings'").fetchone()
            if bindings and {'file_type', 'archive_chat_id', 'archive_message_id'} <= cols:
                return
        if path not in _initialized:
            _initialized.add(path)
        db.init_db()


def invalidate_schema():
    with _schema_lock:
        _initialized.clear()


def bot_key(tenant):
    token = (tenant or {}).get('bot_token') or ''
    if not token:
        raise MediaError('bot_missing', 'Shop bot is not configured')
    identity = token.partition(':')[0]
    if not identity.isdecimal():
        raise MediaError('bot_missing', 'Shop bot identity is invalid')
    return 'telegram:' + str(int(identity))


def asset(ref, tid=None):
    mid = str(ref or '').removeprefix(PREFIX).rsplit('/', 1)[-1]
    if len(mid) != 32 or any(c not in '0123456789abcdef' for c in mid):
        return None
    ensure_schema()
    with db.conn() as cx:
        row = cx.execute('SELECT * FROM media_assets WHERE id=?', (mid,)).fetchone()
    if not row or (tid is not None and row['tenant_id'] != tid):
        return None
    return dict(row)


def retain(tid, purpose, owner_id, blob, request_id=None, bot=None):
    ensure_schema()
    if not blob or len(blob) > MAX_BYTES:
        raise ValueError('Image is empty or too large')
    tenant = db.get_tenant(tid)
    key = bot_key(tenant)
    digest = hashlib.sha256(blob).hexdigest()
    request_id = str(request_id or digest)
    if len(request_id) > 128:
        raise ValueError('Upload request ID is too long')
    mid = secrets.token_hex(16)
    with db.conn() as cx:
        won = cx.execute('INSERT OR IGNORE INTO media_assets '
            '(id,tenant_id,bot_key,purpose,owner_id,request_id,state,digest,size) '
            "VALUES(?,?,?,?,?,?,'uploading',?,?)",
            (mid, tid, key, purpose, owner_id, request_id, digest, len(blob))).rowcount
        row = dict(cx.execute('SELECT * FROM media_assets WHERE tenant_id=? AND bot_key=? '
            'AND purpose=? AND owner_id=? AND request_id=?',
            (tid, key, purpose, owner_id, request_id)).fetchone())
    if row['digest'] != digest:
        raise ValueError('Upload request ID was already used for another image')
    if not won:
        if row['state'] == 'ready':
            return PREFIX + row['id']
        if row.get('file_id'):
            mid = row['id']
        elif row['state'] != 'failed':
            raise MediaError('unknown', 'Upload outcome needs review; image has not been accepted')
        else:
            with db.conn() as cx:
                won = cx.execute("UPDATE media_assets SET state='uploading',error=NULL WHERE id=? AND state='failed'",
                                 (row['id'],)).rowcount
            if not won:
                raise MediaError('unknown', 'Upload is already in progress')
            mid = row['id']
    sent = False
    file_id = row.get('file_id')
    try:
        target = (tenant.get('admin_group_id') if purpose == 'receipt' else None) or tenant.get('owner_tg_id') or tenant.get('admin_group_id')
        if not target and not file_id:
            raise MediaError('destination', 'Shop media destination is not configured')
        bot = bot or Bot(tenant['bot_token'])
        if not file_id:
            topics = tenant.get('topics') or '{}'
            topics = json.loads(topics) if isinstance(topics, str) else topics
            topic = topics.get('receipts') if purpose == 'receipt' and target == tenant.get('admin_group_id') else None
            sent = True
            if purpose == 'receipt' and target == tenant.get('admin_group_id'):
                from bot.handlers import Ctx
                ctx = Ctx(bot, tenant)
                target, topic = ctx.staff_chat('receipts')
                result = ctx._send_staff(target, topic, 'receipts', '', None, None, retry=True,
                                         document=(blob, 'image.bin'), raise_errors=True) or {}
            else:
                result = bot.send_doc_bytes(target, blob, filename='image.bin', topic_id=topic) or {}
            document = result.get('document') or {}
            file_id = document.get('file_id')
            if file_id:
                # Commit Telegram's known answer before verification or attachment can fail.
                with db.conn() as cx:
                    cx.execute("UPDATE media_assets SET state='verifying',file_id=?,file_unique_id=?,archive_chat_id=?,archive_message_id=? WHERE id=?",
                               (file_id, document.get('file_unique_id'), target, result.get('message_id'), mid))
        if not file_id or bot.file_bytes(file_id, limit=MAX_BYTES) != blob:
            raise ValueError('Telegram image retention could not be verified')
        with db.conn() as cx:
            cx.execute("UPDATE media_assets SET state='ready',error=NULL WHERE id=?", (mid,))
        return PREFIX + mid
    except Exception as exc:
        with db.conn() as cx:
            known = not sent or getattr(exc, 'code', None) in (400, 401, 403, 404, 413, 429)
            cx.execute("UPDATE media_assets SET state=?,error=? WHERE id=?",
                       ('verifying' if file_id else 'failed' if known else 'unknown', type(exc).__name__, mid))
        reason = ('verifying' if file_id else getattr(exc, 'reason', 'upload_failed' if known else 'unknown'))
        raise MediaError(reason, 'Image was not accepted: retention failed or is uncertain') from None


def read(ref, tid=None, public=False):
    row = asset(ref, tid)
    if not row or row['state'] != 'ready' or (public and row['purpose'] not in PUBLIC):
        raise ValueError('Image is unavailable')
    tenant = db.get_tenant(row['tenant_id'])
    if not tenant or bot_key(tenant) != row['bot_key']:
        raise MediaError('replaced', 'Image belongs to a replaced shop bot; restore access before reading')
    blob = Bot(tenant['bot_token']).file_bytes(row['file_id'], limit=MAX_BYTES)
    if len(blob) != row['size'] or hashlib.sha256(blob).hexdigest() != row['digest']:
        raise ValueError('Retained image verification failed')
    return blob


def retain_existing(tid, purpose, owner_id, file_id, bot):
    """An incoming Telegram image already has storage; verify before recording acceptance."""
    ensure_schema()
    tenant = db.get_tenant(tid)
    key = bot_key(tenant)
    blob = bot.file_bytes(file_id, limit=MAX_BYTES)
    if not blob or len(blob) > MAX_BYTES or not (blob.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff'))
            or (blob[:4] == b'RIFF' and blob[8:12] == b'WEBP')):
        raise ValueError('Incoming image could not be retained')
    request = hashlib.sha256(str(file_id).encode()).hexdigest()
    with db.conn() as cx:
        cx.execute('INSERT OR IGNORE INTO media_assets '
            '(id,tenant_id,bot_key,purpose,owner_id,request_id,state,file_type,file_id,size,digest) '
            "VALUES(?,?,?,?,?,?,'ready','photo',?,?,?)",
            (secrets.token_hex(16), tid, key, purpose, owner_id, request, file_id,
             len(blob), hashlib.sha256(blob).hexdigest()))
        row = cx.execute('SELECT id FROM media_assets WHERE tenant_id=? AND bot_key=? '
            'AND purpose=? AND owner_id=? AND request_id=?', (tid, key, purpose, owner_id, request)).fetchone()
    return PREFIX + row['id'], blob


def receipt_bytes(ref, tid):
    if str(ref or '').startswith(PREFIX):
        return read(ref, tid=tid)
    if str(ref or '').startswith('local:'):
        name = ref[6:]
        if '/' in name or '\\' in name or '..' in name:
            raise ValueError('Invalid legacy receipt')
        source = db.DB_PATH.parent / 'receipts' / name
        if not source.is_file() or source.stat().st_size > MAX_BYTES:
            raise ValueError('Legacy receipt is unavailable')
        return source.read_bytes()
    tenant = db.get_tenant(tid)
    return Bot(tenant['bot_token']).file_bytes(ref, limit=MAX_BYTES)


def receipt_notice(ctx, ref, caption, keyboard):
    row = asset(ref, ctx.tid)
    gid, _ = ctx.staff_chat('receipts')
    if not row or row['state'] != 'ready' or not row['archive_message_id'] or row['archive_chat_id'] != gid:
        return False
    mode = 'HTML'
    if len(caption.encode('utf-16-le')) > 2000:
        from bot.fmt import plain
        caption, mode = plain(caption).encode('utf-16-le')[:2000].decode('utf-16-le', 'ignore'), None
    ctx.bot.call('editMessageCaption', chat_id=gid, message_id=row['archive_message_id'],
                 caption=caption, parse_mode=mode, reply_markup=keyboard)
    return True


def url(ref):
    row = asset(ref)
    return ('/api/public/media/' if row and row['purpose'] in PUBLIC else '/api/private-media/') + ref.removeprefix(PREFIX)


def current(tid, purpose, owner_id):
    with db.conn() as cx:
        try:
            row = cx.execute('SELECT media_id AS id FROM media_bindings WHERE tenant_id=? AND purpose=? AND owner_id=?',
                             (tid, purpose, owner_id)).fetchone()
        except sqlite3.OperationalError:
            return None
    return (PREFIX + row['id'] if row['id'] else '') if row else None


def clear(tid, purpose, owner_id):
    ensure_schema()
    with db.conn() as cx:
        cx.execute("INSERT INTO media_bindings VALUES(?,?,?,'') ON CONFLICT(tenant_id,purpose,owner_id) DO UPDATE SET media_id=''",
                   (tid, purpose, owner_id))


def bind(tid, purpose, owner_id, ref, *, if_absent=False):
    row = asset(ref, tid)
    if not row or row['state'] != 'ready' or row['purpose'] != purpose or row['owner_id'] != owner_id:
        raise ValueError('Image does not belong to this attachment')
    with db.conn() as cx:
        action = 'DO NOTHING' if if_absent else 'DO UPDATE SET media_id=excluded.media_id'
        return bool(cx.execute('INSERT INTO media_bindings VALUES(?,?,?,?) ON CONFLICT(tenant_id,purpose,owner_id) '
                              + action, (tid, purpose, owner_id, row['id'])).rowcount)
