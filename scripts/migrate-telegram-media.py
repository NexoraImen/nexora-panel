"""Resume verified Telegram media migration. Originals are deliberately retained."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'bot')]


def migrate(directory):
    from bot import db, media
    media.ensure_schema()
    directory = Path(directory).resolve()
    completed, failures = 0, []

    def move(tid, purpose, owner, source, replace):
        nonlocal completed
        try:
            source = source.resolve()
            if not source.is_relative_to(directory) or not source.is_file():
                raise ValueError('Legacy source is missing or outside the data directory')
            if source.stat().st_size > media.MAX_BYTES:
                raise ValueError('Legacy image exceeds the allowed size')
            blob = source.read_bytes()
            ref = media.retain(tid, purpose, owner, blob)
            if media.read(ref, tid=tid) != blob:
                raise ValueError('Retained bytes did not match the original')
            if replace(ref) is False:
                raise ValueError('Attachment changed while migration was running')
            completed += 1
        except Exception as exc:
            failures.append(f'{purpose} {owner}: {type(exc).__name__}')

    with db.conn() as cx:
        receipts = [dict(r) for r in cx.execute("SELECT id,tenant_id,receipt_file FROM orders WHERE receipt_file LIKE 'local:%'")]
        messages = [dict(r) for r in cx.execute("SELECT id,tenant_id,user_id,photo FROM chat_messages WHERE photo LIKE '/api/public/chat-photo/%'")]
        posts = [dict(r) for r in cx.execute("SELECT id,tenant_id,photo FROM channel_posts WHERE photo IS NOT NULL AND photo NOT LIKE 'media:%'")]
        payouts = [dict(r) for r in cx.execute("SELECT p.id,a.tenant_id,p.receipt FROM affiliate_payouts p JOIN affiliates a ON a.id=p.affiliate_id WHERE p.receipt IS NOT NULL AND p.receipt NOT LIKE 'media:%'")]

    def replace(table, column, tid, oid, old, ref, scoped=True):
        with db.conn() as cx:
            clause = ' AND tenant_id=?' if scoped else ''
            params = (ref, oid, old, tid) if scoped else (ref, oid, old)
            cur = cx.execute(f'UPDATE {table} SET {column}=? WHERE id=? AND {column}=?' + clause, params)
            if not cur.rowcount:
                raise ValueError('Attachment changed while migration was running')

    for row in receipts:
        old = row['receipt_file']
        move(row['tenant_id'], 'receipt', row['id'], directory / 'receipts' / old[6:],
             lambda ref, r=row: replace('orders', 'receipt_file', r['tenant_id'], r['id'], r['receipt_file'], ref))
    for row in messages:
        move(row['tenant_id'], 'chat', row['user_id'], directory / 'chat' / row['photo'].rsplit('/', 1)[-1],
             lambda ref, r=row: replace('chat_messages', 'photo', r['tenant_id'], r['id'], r['photo'], media.url(ref)))
    from bot import core
    for row in posts:
        move(row['tenant_id'], 'channel', row['tenant_id'], core.channel_photo_dir() / row['photo'],
             lambda ref, r=row: replace('channel_posts', 'photo', r['tenant_id'], r['id'], r['photo'], ref))
    for row in payouts:
        move(row['tenant_id'], 'payout', row['id'], directory / 'aff-receipts' / row['receipt'],
             lambda ref, r=row: replace('affiliate_payouts', 'receipt', r['tenant_id'], r['id'], r['receipt'], ref, False))
    for tenant in db.all_tenants(active_only=False):
        tid = tenant['id']
        if media.current(tid, 'logo', tid) is None:
            for ext in ('png', 'jpg', 'webp'):
                source = directory / 'logos' / f'{tid}.{ext}'
                if source.is_file():
                    move(tid, 'logo', tid, source, lambda ref, tid=tid: media.bind(tid, 'logo', tid, ref, if_absent=True))
                    break
        for source in sorted((directory / 'avatars').glob(f'{tid}_*')):
            try:
                uid = int(source.name.split('_', 2)[1])
            except (ValueError, IndexError):
                continue
            if media.current(tid, 'avatar', uid) is None:
                move(tid, 'avatar', uid, source, lambda ref, uid=uid, tid=tid: media.bind(tid, 'avatar', uid, ref, if_absent=True))
    return {'completed': completed, 'failures': failures, 'originals_removed': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True)
    args = parser.parse_args()
    os.environ['BOT_DB_PATH'] = str(Path(args.data_dir).resolve() / 'bot.db')
    result = migrate(args.data_dir)
    print(f"Migrated: {result['completed']}; failures: {len(result['failures'])}; original files removed: 0")
    for failure in result['failures']:
        print(failure)
    sys.exit(1 if result['failures'] else 0)
