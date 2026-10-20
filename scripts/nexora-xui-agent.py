#!/usr/bin/env python3
"""Local API bridge with private database snapshots sent to the central panel."""
import argparse
from contextlib import closing
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import (build_opener, HTTPCookieProcessor, HTTPSHandler,
                            HTTPRedirectHandler, ProxyHandler, Request)

MAX_SNAPSHOT = 64 * 1024 * 1024
MAX_RESPONSE = 4 * 1024 * 1024
HOME = Path('/opt/nexora-xui-agent')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Response:
    def __init__(self, stream):
        self.stream = stream
        self.status_code = stream.getcode()

    def iter_content(self, size):
        while True:
            chunk = self.stream.read(size)
            if not chunk:
                break
            yield chunk

    def json(self):
        body = self.stream.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            raise ValueError('Central response exceeds limit')
        return json.loads(body)

    def close(self):
        self.stream.close()


class Session:
    """Small urllib transport; Iran needs no package repository access."""
    def __init__(self):
        self.headers = {}
        self.trust_env = False
        self.opener = build_opener(ProxyHandler({}), NoRedirect(),
            HTTPSHandler(context=ssl.create_default_context()), HTTPCookieProcessor(CookieJar()))

    def request(self, method, url, **kwargs):
        headers = {**self.headers, **kwargs.get('headers', {})}
        params = kwargs.get('params')
        if params:
            query = params if isinstance(params, str) else urlencode(params, doseq=True)
            url += ('&' if '?' in url else '?') + query
        data = kwargs.get('data')
        if kwargs.get('json') is not None:
            if data is not None:
                raise ValueError('Cannot combine form data and JSON')
            data = json.dumps(kwargs['json']).encode('utf-8')
            headers.setdefault('Content-Type', 'application/json')
        elif isinstance(data, (dict, list, tuple)):
            data = urlencode(data, doseq=True).encode('utf-8')
            headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
        elif isinstance(data, str):
            data = data.encode('utf-8')
        if hasattr(data, 'fileno'):
            headers.setdefault('Content-Length', str(os.fstat(data.fileno()).st_size - data.tell()))
        request = Request(url, data=data, headers=headers, method=method)
        try:
            stream = self.opener.open(request, timeout=kwargs.get('timeout', 45))
        except HTTPError as response:
            return Response(response)
        return Response(stream)

    def close(self):
        self.opener.close()


def base_url(value, *, local=False, allow_test_http=False):
    p = urlsplit(value)
    loopback = p.hostname in ('localhost', '127.0.0.1', '::1')
    if (not p.hostname or p.username is not None or p.password is not None
            or p.query or p.fragment or p.scheme not in ('https', 'http')
            or (local and not loopback)
            or (not local and p.scheme != 'https' and not (allow_test_http and loopback))):
        raise ValueError('Invalid panel URL')
    try:
        p.port
    except ValueError:
        raise ValueError('Invalid panel port') from None
    if not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)*/?', p.path):
        raise ValueError('Invalid panel base path')
    return value.rstrip('/')


def command_args(command):
    method, path = command.get('method'), command.get('path')
    kw = command.get('kwargs', {})
    if (method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')
            or not isinstance(path, str)
            or not re.fullmatch(r'/[A-Za-z0-9_./@+-]+', path)
            or '..' in path or any(s in ('', '.') for s in path.split('/')[1:])
            or not (path.startswith('/panel/api/') or (path == '/openapi.json' and method == 'GET'))
            or not isinstance(kw, dict) or set(kw) - {'data', 'json', 'params'}):
        raise ValueError('Command rejected by local allowlist')
    return method, path, kw


def limited_response(response):
    try:
        body = bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body) > MAX_RESPONSE:
                raise ValueError('Local response exceeds limit')
        return {'status': response.status_code, 'body': body.decode('utf-8', errors='replace')}
    finally:
        response.close()


class Journal:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        os.chmod(path, 0o600)
        self.db.executescript('''
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS commands
                (id TEXT PRIMARY KEY, result TEXT, pending INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value INTEGER);
        ''')
        # A crash can happen after XUI changes state but before we save its response.
        for (ident,) in self.db.execute('SELECT id FROM commands WHERE result IS NULL').fetchall():
            self.finish(ident, {'id': ident, 'state': 'unknown',
                               'response': {'status': 0, 'body': ''},
                               'error': 'Interrupted command; execution was not repeated'})

    def start(self, ident):
        with self.db:
            return self.db.execute('INSERT OR IGNORE INTO commands(id) VALUES(?)', (ident,)).rowcount == 1

    def finish(self, ident, result):
        with self.db:
            self.db.execute('UPDATE commands SET result=?, pending=1 WHERE id=?',
                            (json.dumps(result), ident))

    def saved(self, ident):
        row = self.db.execute('SELECT result FROM commands WHERE id=?', (ident,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def pending(self):
        return [json.loads(r[0]) for r in self.db.execute(
            'SELECT result FROM commands WHERE pending=1 AND result IS NOT NULL LIMIT 10')]

    def acknowledge(self, results):
        with self.db:
            self.db.executemany('UPDATE commands SET pending=0 WHERE id=?', [(r['id'],) for r in results])

    def sequence(self):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES('sequence',0)")
            self.db.execute("UPDATE metadata SET value=value+1 WHERE key='sequence'")
            return self.db.execute("SELECT value FROM metadata WHERE key='sequence'").fetchone()[0]

    def ensure_sequence(self, floor):
        if type(floor) is not int or floor < 0:
            raise ValueError('Invalid snapshot sequence floor')
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES('sequence',?)", (floor,))
            self.db.execute("UPDATE metadata SET value=? WHERE key='sequence' AND value<?", (floor, floor))


class Agent:
    def __init__(self, config, journal, central=None, local=None, *, allow_test_http=False):
        self.config, self.journal = config, journal
        self.panel = base_url(config['panel'], allow_test_http=allow_test_http)
        self.xui = base_url(config['xui_url'], local=True)
        journal.ensure_sequence(config.get('sequence_floor', 0))
        self.central, self.local = central or Session(), local or Session()
        self.central.trust_env = self.local.trust_env = False
        self.central.headers['Authorization'] = 'Bearer ' + config['token']
        if config.get('xui_token'):
            self.local.headers['Authorization'] = 'Bearer ' + config['xui_token']
        self.logged_in = bool(config.get('xui_token'))
        self.snapshot_due = True
        self.last_snapshot = None

    def central_request(self, method, path, **kwargs):
        response = self.central.request(method, self.panel + '/api/xui-agent/' + path,
                                        timeout=45, allow_redirects=False, **kwargs)
        if not 200 <= response.status_code < 300:
            response.close()
            raise RuntimeError('Central request rejected')
        return response

    def snapshot(self):
        captured = time.time()
        sequence = self.journal.sequence()
        with tempfile.TemporaryDirectory(prefix='nexora-xui-') as tmp:
            target = Path(tmp) / 'snapshot.db'
            source = Path(self.config['sqlite_path']).resolve().as_uri() + '?mode=ro'
            started = time.monotonic()
            def progress(status, remaining, total):
                if total * page_size > MAX_SNAPSHOT or time.monotonic() - started > 40:
                    raise ValueError('SQLite backup exceeds size or time limit')
            with closing(sqlite3.connect(source, uri=True)) as src, closing(sqlite3.connect(target)) as dest:
                os.chmod(target, 0o600)
                page_size = src.execute('PRAGMA page_size').fetchone()[0]
                pages = src.execute('PRAGMA page_count').fetchone()[0]
                if pages * page_size > MAX_SNAPSHOT:
                    raise ValueError('SQLite snapshot exceeds limit')
                src.backup(dest, pages=256, progress=progress, sleep=0.05)
            if not 0 < target.stat().st_size <= MAX_SNAPSHOT:
                raise ValueError('Invalid SQLite snapshot size')
            with target.open('rb') as stream:
                response = self.central_request('PUT', 'snapshot', data=stream, headers={
                    'Content-Type': 'application/octet-stream',
                    'X-Snapshot-Sequence': str(sequence),
                    'X-Snapshot-Captured-At': str(captured)})
                response.close()
        self.snapshot_due = False
        self.last_snapshot = time.monotonic()

    def execute(self, command):
        ident = command.get('id')
        if not isinstance(ident, str) or not ident or len(ident) > 256:
            raise ValueError('Invalid command identifier')
        if not self.journal.start(ident):
            result = self.journal.saved(ident)
            if result is not None:
                self.journal.finish(ident, result)
            return result
        result = {'id': ident, 'state': 'failed', 'response': {'status': 0, 'body': ''}}
        dispatched = False
        try:
            method, path, kw = command_args(command)
            if not self.logged_in:
                login = limited_response(self.local.request('POST', self.xui + '/login',
                    data={'username': self.config['xui_username'], 'password': self.config['xui_password']},
                    timeout=45, stream=True, allow_redirects=False))
                if not 200 <= login['status'] < 300 or not json.loads(login['body']).get('success'):
                    raise ValueError('Local login rejected')
                self.logged_in = True
            dispatched = True
            # A timeout can follow an applied mutation; reconcile before reporting its outcome.
            if method != 'GET':
                self.snapshot_due = True
            result['response'] = limited_response(self.local.request(method, self.xui + path,
                timeout=45, stream=True, allow_redirects=False, **kw))
            if result['response']['status'] in (401, 403) and not self.config.get('xui_token'):
                self.logged_in = False
            # HTTP errors are completed transport results used by XUI's version/auth fallbacks.
            result['state'] = 'done'
        except Exception:
            result['state'] = 'unknown' if dispatched else 'failed'
            result['error'] = 'Local request outcome unknown' if dispatched else 'Local request rejected'
        self.journal.finish(ident, result)
        return result

    def cycle(self):
        if self.snapshot_due or self.last_snapshot is None or time.monotonic() - self.last_snapshot >= 30:
            self.snapshot()
        results = self.journal.pending()
        response = self.central_request('POST', 'poll', json={'results': results})
        try:
            payload = response.json()
            commands = payload['commands']
            if not isinstance(commands, list) or len(commands) > 1:
                raise ValueError('Central must send at most one command')
        finally:
            response.close()
        self.journal.acknowledge(results)
        for command in commands:
            self.execute(command)
            if self.snapshot_due:
                self.snapshot()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(HOME / 'config.json'))
    args = parser.parse_args()
    os.umask(0o077)
    try:
        import fcntl
        config_path = Path(args.config)
        with (config_path.parent / 'agent.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if config_path.stat().st_mode & 0o777 != 0o600:
                raise ValueError('Configuration permissions must be 0600')
            config = json.loads(config_path.read_text())
            journal = Journal(config_path.parent / 'journal.db')
            agent = Agent(config, journal)
            while True:
                start = time.monotonic()
                try:
                    agent.cycle()
                except Exception:
                    print('Agent cycle failed; retrying safely', flush=True)
                time.sleep(max(0.1, 1 - (time.monotonic() - start)))
    except Exception:
        print('Agent startup failed; check local configuration and service prerequisites', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
