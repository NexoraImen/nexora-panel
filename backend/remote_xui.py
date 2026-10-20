"""One remote 3x-ui source, with ordered snapshots and persistent command IDs."""
import contextvars
import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, unquote

MAX_SNAPSHOT = 64 * 1024 * 1024
MAX_REPLY = 4 * 1024 * 1024
FRESH_SECONDS = 90
PIN = contextvars.ContextVar('remote_xui_snapshot', default=None)
ORDER = contextvars.ContextVar('remote_xui_order', default=None)


class SnapshotClients(list):
    """Carry source generation without adding fields to customer data."""
    def __init__(self, rows, path):
        super().__init__(rows)
        self.source, sequence = Path(path).stem.rsplit('-', 1)
        self.sequence = int(sequence)


@contextmanager
def accounting_generation(clients):
    if not isinstance(clients, SnapshotClients):
        yield
        return
    # An older concurrent reader must not infer a traffic reset after a newer one.
    with connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS remote_accounting (source TEXT PRIMARY KEY, sequence INTEGER)')
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT sequence FROM remote_accounting WHERE source=?', (clients.source,)).fetchone()
        if prior and prior['sequence'] > clients.sequence:
            raise RemoteError('گزارش جدیدتری پردازش شده است؛ صفحه حسابداری را تازه کنید')
        yield
        db.execute('INSERT OR REPLACE INTO remote_accounting VALUES(?,?)', (clients.source, clients.sequence))


class RemoteError(RuntimeError):
    pass


class RemoteUncertain(RemoteError):
    remote_uncertain = True


def directory():
    return Path(os.getenv('CONFIG_PATH') or os.getenv('PANEL_CONFIG') or
                str(Path(__file__).resolve().parents[1] / 'data/config.json')).resolve().parent


@contextmanager
def connection():
    root = directory()
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'remote-xui.db'
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        os.chmod(path, 0o600)
        db.executescript('''
            CREATE TABLE IF NOT EXISTS remote_settings (
                id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL DEFAULT 'local',
                region TEXT NOT NULL DEFAULT 'foreign', node_id TEXT, source_url TEXT);
            INSERT OR IGNORE INTO remote_settings(id) VALUES(1);
            CREATE TABLE IF NOT EXISTS remote_nodes (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL,
                code_hash TEXT, expires REAL, token_hash TEXT, revoked INTEGER DEFAULT 0,
                last_seen REAL, snapshot_at REAL, sequence INTEGER DEFAULT 0,
                snapshot_path TEXT);
            CREATE TABLE IF NOT EXISTS remote_commands (
                id TEXT PRIMARY KEY, node_id TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'queued', result TEXT, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS remote_orders (
                tenant_id INTEGER, order_id INTEGER, prior_status TEXT NOT NULL,
                PRIMARY KEY(tenant_id,order_id));
            CREATE TABLE IF NOT EXISTS remote_order_commands (
                command_id TEXT PRIMARY KEY, tenant_id INTEGER, order_id INTEGER);
        ''')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def settings():
    with connection() as db:
        return dict(db.execute('SELECT * FROM remote_settings WHERE id=1').fetchone())


def active():
    return (directory() / 'remote-xui.db').exists() and settings()['mode'] == 'remote'


def status():
    with connection() as db:
        cfg = dict(db.execute('SELECT * FROM remote_settings WHERE id=1').fetchone())
        nodes = [dict(r) for r in db.execute(
            'SELECT id,name,region,last_seen,snapshot_at,revoked FROM remote_nodes ORDER BY name')]
        uncertain = [dict(r) for r in db.execute(
            "SELECT id,node_id,payload,created FROM remote_commands WHERE state='unknown' ORDER BY created")]
        orders = [dict(r) for r in db.execute('SELECT tenant_id,order_id FROM remote_orders ORDER BY order_id')]
    for command in uncertain:
        payload = json.loads(command.pop('payload'))
        command.update(method=payload['method'], path=payload['path'])
    for node in nodes:
        node['online'] = bool(not node['revoked'] and node['last_seen'] and
                              time.time() - node['last_seen'] <= FRESH_SECONDS)
    return {'mode': cfg['mode'], 'region': cfg['region'], 'selected': cfg['node_id'], 'nodes': nodes,
            'uncertain': uncertain, 'orders': orders}


def pair(name, region):
    if region not in ('iran', 'foreign') or not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
        raise RemoteError('نام و موقعیت سرور معتبر نیست')
    code, node_id = secrets.token_urlsafe(32), secrets.token_hex(12)
    expires = time.time() + 600
    with connection() as db:
        db.execute('INSERT INTO remote_nodes(id,name,region,code_hash,expires) VALUES(?,?,?,?,?)',
                   (node_id, name.strip(), region, digest(code), expires))
    return {'code': code, 'node_id': node_id, 'expires': expires}


def enroll(code):
    if not isinstance(code, str) or not 20 <= len(code) <= 100:
        raise RemoteError('کد اتصال معتبر نیست')
    token = secrets.token_urlsafe(48)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        node = db.execute('SELECT id,sequence FROM remote_nodes WHERE code_hash=? AND expires>? AND revoked=0',
                          (digest(code), time.time())).fetchone()
        if not node:
            raise RemoteError('کد اتصال منقضی شده یا قبلاً استفاده شده است')
        db.execute('UPDATE remote_nodes SET code_hash=NULL,token_hash=?,last_seen=? WHERE id=?',
                   (digest(token), time.time(), node['id']))
    return {'node_id': node['id'], 'token': token, 'sequence_floor': node['sequence']}


def repair_pair(node_id):
    code = secrets.token_urlsafe(32)
    expires = time.time() + 600
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT id FROM remote_nodes WHERE id=?', (node_id,)).fetchone():
            raise RemoteError('سرور پیدا نشد')
        db.execute('UPDATE remote_nodes SET code_hash=?,expires=?,token_hash=NULL,revoked=0,'
                   'last_seen=NULL,snapshot_at=NULL WHERE id=?', (digest(code), expires, node_id))
        db.execute("UPDATE remote_commands SET state='unknown' WHERE node_id=? AND state='running'", (node_id,))
        db.execute("UPDATE remote_commands SET state='failed' WHERE node_id=? AND state='queued'", (node_id,))
    return {'code': code, 'node_id': node_id, 'expires': expires}


def authenticate(token):
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        raise RemoteError('دسترسی ایجنت معتبر نیست')
    with connection() as db:
        node = db.execute('SELECT * FROM remote_nodes WHERE token_hash=? AND revoked=0', (digest(token),)).fetchone()
    if not node:
        raise RemoteError('دسترسی ایجنت معتبر نیست')
    return dict(node)


def select(mode, region, node_id, source_url=''):
    if mode not in ('local', 'remote') or region not in ('iran', 'foreign'):
        raise RemoteError('نقش و موقعیت سرور معتبر نیست')
    with connection() as db:
        cfg = db.execute('SELECT * FROM remote_settings WHERE id=1').fetchone()
        if mode == 'remote':
            if not isinstance(node_id, str) or len(node_id) != 24:
                raise RemoteError('سرور انتخاب‌شده معتبر نیست')
            node = db.execute('SELECT * FROM remote_nodes WHERE id=? AND revoked=0', (node_id,)).fetchone()
            require_fresh(node)
            # Billing history is keyed by email; switching panels would corrupt its baselines.
            if cfg['node_id'] and cfg['node_id'] != node_id:
                raise RemoteError('تغییر منبع حسابداری به سروری دیگر نیاز به انتقال و تطبیق اطلاعات دارد')
        db.execute('UPDATE remote_settings SET mode=?,region=?,node_id=?,source_url=? WHERE id=1',
                   (mode, region, node_id if mode == 'remote' else cfg['node_id'],
                    cfg['source_url'] or source_url))


def require_fresh(node):
    if (not node or node['revoked'] or not node['snapshot_at'] or
            time.time() - node['snapshot_at'] > FRESH_SECONDS or not node['snapshot_path'] or
            not (directory() / node['snapshot_path']).is_file()):
        raise RemoteError('اطلاعات تازه از سرور 3x-ui دریافت نشده؛ اتصال ایجنت را بررسی کنید')


def snapshot_path():
    with connection() as db:
        cfg = db.execute('SELECT * FROM remote_settings WHERE id=1').fetchone()
        if cfg['mode'] != 'remote':
            return None
        node = db.execute('SELECT * FROM remote_nodes WHERE id=?', (cfg['node_id'],)).fetchone()
        require_fresh(node)
        pin = PIN.get()
        if pin is not None and node['id'] in pin:
            return Path(pin[node['id']])
        path = directory() / node['snapshot_path']
        if pin is not None:
            pin[node['id']] = str(path)
        return path


def receive_snapshot(node_id, body, sequence, captured):
    if (not 0 < len(body) <= MAX_SNAPSHOT or not body.startswith(b'SQLite format 3\x00') or
            not isinstance(sequence, int) or not 0 < sequence < 2**63 or
            not 0 <= time.time() - captured <= FRESH_SECONDS):
        raise RemoteError('نسخه دیتابیس نامعتبر یا قدیمی است')
    root = directory()
    with tempfile.NamedTemporaryFile(dir=root, suffix='.db', delete=False) as stream:
        temp = Path(stream.name)
        stream.write(body)
    try:
        os.chmod(temp, 0o600)
        con = sqlite3.connect(f'{temp.as_uri()}?mode=ro', uri=True)
        try:
            con.execute('PRAGMA trusted_schema=OFF')
            if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RemoteError('دیتابیس دریافتی سالم نیست')
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'inbounds' not in tables:
                raise RemoteError('فایل دریافتی دیتابیس 3x-ui نیست')
        finally:
            con.close()
        with connection() as db:
            db.execute('BEGIN IMMEDIATE')
            node = db.execute('SELECT * FROM remote_nodes WHERE id=? AND revoked=0', (node_id,)).fetchone()
            if not node or sequence <= node['sequence'] or captured < (node['snapshot_at'] or 0):
                raise RemoteError('گزارش قدیمی یا تکراری رد شد')
            (root / 'remote-xui').mkdir(exist_ok=True)
            name = f'remote-xui/{node_id}-{sequence}.db'
            os.replace(temp, root / name)
            db.execute('UPDATE remote_nodes SET snapshot_path=?,snapshot_at=?,sequence=?,last_seen=? WHERE id=?',
                       (name, captured, sequence, time.time(), node_id))
        # Retain recent immutable files for in-flight reads; never replace an open SQLite file.
        for old in (root / 'remote-xui').glob(f'{node_id}-*.db'):
            if time.time() - old.stat().st_mtime > 3600:
                old.unlink(missing_ok=True)
    except sqlite3.Error as exc:
        raise RemoteError('ساختار دیتابیس دریافتی معتبر نیست') from exc
    finally:
        temp.unlink(missing_ok=True)


def validate_command(method, path, kwargs):
    if not isinstance(path, str):
        raise RemoteError('فرمان 3x-ui مجاز نیست')
    parsed = urlsplit(path)
    decoded = unquote(path)
    if (method not in ('GET', 'POST', 'PUT', 'DELETE') or parsed.scheme or parsed.netloc or
            parsed.query or parsed.fragment or '..' in decoded or '\\' in decoded or '%' in decoded or
            not (path.startswith('/panel/api/') or (path == '/openapi.json' and method == 'GET')) or not isinstance(kwargs, dict) or
            set(kwargs) - {'data', 'json', 'params'}):
        raise RemoteError('فرمان 3x-ui مجاز نیست')


def hold_order(context, command):
    path = Path(os.getenv('BOT_DB_PATH') or directory() / 'bot.db')
    bot = sqlite3.connect(path, timeout=15)
    try:
        with connection() as db:
            db.execute('BEGIN IMMEDIATE')
            bot.execute('BEGIN IMMEDIATE')
            key = (context['tenant_id'], context['order_id'])
            order = bot.execute('SELECT status FROM orders WHERE tenant_id=? AND id=?', key).fetchone()
            prior = db.execute('SELECT prior_status FROM remote_orders WHERE tenant_id=? AND order_id=?', key).fetchone()
            if not order or (order[0] == 'remote_review' and not prior):
                raise RemoteError('سفارش نیاز به بررسی دستی دارد')
            db.execute('INSERT OR IGNORE INTO remote_orders VALUES(?,?,?)', (*key, order[0]))
            db.execute('INSERT INTO remote_order_commands VALUES(?,?,?)', (command, *key))
            bot.execute("UPDATE orders SET status='remote_review',admin_note=? WHERE tenant_id=? AND id=?",
                        (f'بررسی نتیجه فرمان راه دور: {command}', *key))
            bot.commit()
    finally:
        bot.close()


def release_order(context):
    key = (context['tenant_id'], context['order_id'])
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT prior_status FROM remote_orders WHERE tenant_id=? AND order_id=?', key).fetchone()
        if not prior:
            return True
        pending = db.execute("SELECT 1 FROM remote_order_commands l JOIN remote_commands c "
            "ON c.id=l.command_id WHERE l.tenant_id=? AND l.order_id=? "
            "AND c.state NOT IN ('done','failed','reviewed') LIMIT 1", key).fetchone()
        if pending:
            return False
        bot = sqlite3.connect(Path(os.getenv('BOT_DB_PATH') or directory() / 'bot.db'), timeout=15)
        try:
            bot.execute("UPDATE orders SET status=?,admin_note=NULL WHERE tenant_id=? AND id=? AND status='remote_review'",
                        (prior['prior_status'], *key))
            bot.commit()
        finally:
            bot.close()
        db.execute('DELETE FROM remote_orders WHERE tenant_id=? AND order_id=?', key)
    return True


def rpc(node_id, method, path, kwargs, timeout=150):
    validate_command(method, path, kwargs)
    command = secrets.token_hex(16)
    payload = json.dumps({'id': command, 'method': method, 'path': path, 'kwargs': kwargs})
    if len(payload.encode()) > MAX_REPLY:
        raise RemoteError('اندازه درخواست بیش از حد مجاز است')
    with connection() as db:
        node = db.execute('SELECT * FROM remote_nodes WHERE id=?', (node_id,)).fetchone()
        require_fresh(node)
        uncertain = db.execute("SELECT id FROM remote_commands WHERE node_id=? AND state='unknown'", (node_id,)).fetchone()
        if uncertain and method != 'GET':
            raise RemoteError('نتیجه فرمان قبلی نامشخص است؛ پیش از تکرار، وضعیت کانفیگ را بررسی کنید')
        context = ORDER.get() if method != 'GET' else None
        db.execute('INSERT INTO remote_commands(id,node_id,payload,state,created) VALUES(?,?,?,?,?)',
                   (command, node_id, payload, 'preparing' if context else 'queued', time.time()))
    if context:
        hold_order(context, command)
        with connection() as db:
            db.execute("UPDATE remote_commands SET state='queued' WHERE id=? AND state='preparing'", (command,))
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with connection() as db:
            row = db.execute('SELECT state,result FROM remote_commands WHERE id=?', (command,)).fetchone()
        if row['state'] == 'done':
            return json.loads(row['result'])
        if row['state'] == 'unknown':
            raise RemoteUncertain('نتیجه فرمان سرور نامشخص است؛ سفارش و پرداخت برای بررسی نگه داشته شد')
        if row['state'] == 'failed':
            raise RemoteError('فرمان سرور 3x-ui تأیید نشد؛ وضعیت آن را پیش از تکرار بررسی کنید')
        time.sleep(.1)
    with connection() as db:
        db.execute("UPDATE remote_commands SET state=CASE WHEN state='queued' THEN 'failed' ELSE 'unknown' END "
                   "WHERE id=? AND state IN ('queued','running')", (command,))
        row = db.execute('SELECT state,result FROM remote_commands WHERE id=?', (command,)).fetchone()
    if row['state'] == 'done':
        return json.loads(row['result'])
    if row['state'] == 'unknown':
        raise RemoteUncertain('پاسخ سرور نرسید؛ نتیجه فرمان و پرداخت نیاز به بررسی دارد')
    raise RemoteError('فرمان پیش از اجرا متوقف شد؛ ارتباط سرور را بررسی کنید')


def poll(node_id, results):
    if not isinstance(results, list) or len(results) > 10:
        raise RemoteError('پاسخ ایجنت معتبر نیست')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT id FROM remote_nodes WHERE id=? AND revoked=0', (node_id,)).fetchone():
            raise RemoteError('دسترسی ایجنت معتبر نیست')
        for result in results:
            if not isinstance(result, dict) or result.get('state') not in ('done', 'failed', 'unknown'):
                raise RemoteError('نتیجه فرمان معتبر نیست')
            response = result.get('response') or {}
            if result['state'] == 'done' and (not isinstance(response.get('status'), int) or
                    not 100 <= response['status'] <= 599 or not isinstance(response.get('body'), str)):
                raise RemoteError('پاسخ 3x-ui معتبر نیست')
            encoded = json.dumps(response)
            if len(encoded.encode()) > MAX_REPLY:
                raise RemoteError('پاسخ فرمان بیش از حد مجاز است')
            db.execute("UPDATE remote_commands SET state=CASE WHEN state='unknown' THEN 'unknown' ELSE ? END,result=? WHERE id=? AND node_id=? "
                       "AND state IN ('running','unknown')",
                       (result['state'], encoded, result.get('id'), node_id))
        db.execute('UPDATE remote_nodes SET last_seen=? WHERE id=? AND revoked=0', (time.time(), node_id))
        row = db.execute("SELECT id,payload FROM remote_commands WHERE node_id=? AND state IN ('queued','running') "
                         "ORDER BY created LIMIT 1", (node_id,)).fetchone()
        if row:
            db.execute("UPDATE remote_commands SET state='running' WHERE id=?", (row['id'],))
        return {'commands': [json.loads(row['payload'])] if row else []}


def revoke(node_id):
    with connection() as db:
        db.execute('UPDATE remote_nodes SET revoked=1,token_hash=NULL,code_hash=NULL WHERE id=?', (node_id,))
        db.execute("UPDATE remote_commands SET state='failed' WHERE node_id=? AND state='queued'", (node_id,))
        db.execute("UPDATE remote_commands SET state='unknown' WHERE node_id=? AND state='running'", (node_id,))


def resolve(command_id):
    with connection() as db:
        row = db.execute("SELECT node_id,result FROM remote_commands WHERE id=? AND state='unknown'", (command_id,)).fetchone()
        if not row:
            raise RemoteError('فرمان نامشخص پیدا نشد')
        if row['result'] is None:
            raise RemoteError('ایجنت هنوز پایان اجرای این فرمان را تأیید نکرده است؛ اتصال را برقرار کنید')
        linked = db.execute('SELECT 1 FROM remote_order_commands l JOIN remote_orders o '
            'ON o.tenant_id=l.tenant_id AND o.order_id=l.order_id WHERE l.command_id=?', (command_id,)).fetchone()
        if linked:
            raise RemoteError('این فرمان به سفارش مالی متصل است؛ تحویل و پرداخت سفارش باید ابتدا تطبیق داده شود')
        node = db.execute('SELECT * FROM remote_nodes WHERE id=?', (row['node_id'],)).fetchone()
        require_fresh(node)
        # This acknowledges an operator's review; it never replays the original mutation.
        db.execute("UPDATE remote_commands SET state='reviewed' WHERE id=? AND state='unknown'", (command_id,))
