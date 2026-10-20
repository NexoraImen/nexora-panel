"""A slow Telegram notification cannot delay receipt acceptance or duplicate it."""
import ast
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / 'bot')]
tmp = tempfile.mkdtemp(prefix='mini_delivery_')
os.environ['BOT_DB_PATH'] = str(Path(tmp) / 'bot.db')
from bot import handlers as H
from fastapi import HTTPException

H.DB.init_db()
tid = H.DB.create_tenant('Delivery test')
db = H.DB.TenantDB(tid)
db.create_user(12345, None, 'Test')
user = db.get_user(12345)
order = db.create_order(user['id'], None, 1000, 1000, paid_from='card')
queued, notified = [], []
ctx = SimpleNamespace(tid=tid, db=db, s={}, notify_group=lambda *a, **k: notified.append((a, k)))

with patch.object(H, '_spawn', side_effect=lambda fn, *args: queued.append((fn, args))), \
     patch.object(H, 'pro', return_value=None):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: H.receipt_submit(ctx, user, order['id'], 'photo',
            rfile='local:receipt.png', photo_bytes=b'image', notify_async=True), range(2)))
    assert sum(ok for ok, _ in results) == 1
    assert len(queued) == 1 and not notified
    accepted = db.get_order(order['id'])
    assert accepted['status'] == 'awaiting' and accepted['receipt_file'] == 'local:receipt.png'
    fn, args = queued.pop()
    fn(*args)
    assert len(notified) == 1 and notified[0][1]['photo'] == b'image'
    assert notified[0][1]['keyboard'], 'Approval buttons must accompany the single receipt'

    source = root / 'backend/pro/mini.py'
    if source.exists():
        tree = ast.parse(source.read_text(encoding='utf-8'))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in ('mini_receipt', 'mini_inbox_send')]
        for node in functions:
            node.decorator_list = []
            node.args.defaults = []
        env = dict(HTTPException=HTTPException, _mini_own_order=lambda t, u, oid: db.get_order(oid),
            _mini_ctx=lambda t: (H, ctx), _image_b64=lambda data: None,
            _bot_db_rw=lambda t: db)
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), env)
        # A lost HTTP response is safe to retry without scheduling another notification.
        assert env['mini_receipt'](order['id'], {'text': 'retry'}, ({'id': tid}, user))['ok']
        assert not queued
        assert env['mini_inbox_send']({'body': 'Support message'}, ({'id': tid}, user))['ok']
        assert len(queued) == 1 and len(db.chat_list(user['id'])) == 1

print('Receipt concurrency and nonblocking mini delivery checks passed')
