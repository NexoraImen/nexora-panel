"""Standalone agent safety checks; no server, credentials, or system changes."""
import importlib.util
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sqlite3
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load('xui_agent', 'nexora-xui-agent.py')
I = load('xui_installer', 'install-xui-agent.py')


class Response:
    def __init__(self, body=b'{"success":true}', status=200, payload=None):
        self.body, self.status_code, self.payload = body, status, payload
        self.closed = False

    def iter_content(self, size):
        yield self.body

    def close(self):
        self.closed = True

    def json(self):
        return self.payload if self.payload is not None else json.loads(self.body)


class Session:
    def __init__(self):
        self.headers, self.calls, self.responses = {}, [], []
        self.fail = False
        self.trust_env = True

    def request(self, method, url, **kw):
        if hasattr(kw.get('data'), 'read'):
            kw['data'] = kw['data'].read()
        self.calls.append((method, url, kw))
        if self.fail:
            raise RuntimeError('secret credentials must not appear')
        return self.responses.pop(0) if self.responses else Response(payload={'commands': []})


class AgentTests(unittest.TestCase):
    def assert_loopback_reachable(self, server):
        try:
            with socket.create_connection(server.server_address, timeout=2):
                pass
        except OSError as exc:
            self.fail('Loopback HTTP fixture is unreachable (OS error %s). '
                      'Run with local socket access enabled; this test is mandatory.'
                      % (getattr(exc, 'winerror', None) or exc.errno))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        temp_patch = patch.object(tempfile, 'tempdir', str(self.path))
        temp_patch.start()
        self.addCleanup(temp_patch.stop)
        self.database = self.path / 'xui.db'
        self.source = sqlite3.connect(self.database)
        self.addCleanup(self.source.close)
        self.source.execute('PRAGMA journal_mode=WAL')
        self.source.execute('CREATE TABLE inbounds(id INTEGER)')
        self.source.execute('INSERT INTO inbounds VALUES(42)')
        self.source.commit()
        self.journal = A.Journal(self.path / 'journal.db')
        self.addCleanup(self.journal.db.close)
        self.central, self.local = Session(), Session()
        self.config = dict(panel='https://central.example/base', token='central-secret',
                           xui_url='http://127.0.0.1:54321/hidden', xui_token='local-secret',
                           sqlite_path=str(self.database))
        self.agent = A.Agent(self.config, self.journal, self.central, self.local)
        self.command = dict(id='command-1', method='POST', path='/panel/api/inbounds/add',
                            kwargs={'json': {'id': 1}})

    def test_urls(self):
        for url in ('http://example.com', 'https://a@host', 'https://host/?x=1',
                    'https://host/#fragment', 'https://host/a/../b', 'https://host/%2e',
                    'https://host:bad', 'ftp://host', 'https://host//bad'):
            for validator in (A.base_url, I.panel_url):
                with self.subTest(url=url, validator=validator.__name__), self.assertRaises(ValueError):
                    validator(url)
        for validator in (A.base_url, I.panel_url):
            self.assertEqual(validator('http://localhost:123', allow_test_http=True), 'http://localhost:123')
        for url in ('http://10.0.0.1', 'http://127.0.0.2', 'https://remote', 'http://localhost.evil'):
            with self.assertRaises(ValueError):
                A.base_url(url, local=True)
        self.assertEqual(A.base_url('http://[::1]:5432/base/', local=True), 'http://[::1]:5432/base')

    def test_command_allowlist(self):
        for path in ('/getDb', '/login', '//evil', '/panel/openapi.json',
                     '/panel/api/../login', '/panel/api/%2e%2e/login', '/panel/api/a?url=evil',
                     '/panel/api/a#fragment', '/panel/api//a', '/panel/api/a\\b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                A.command_args(dict(self.command, path=path))
        for key in ('headers', 'url', 'auth', 'verify', 'allow_redirects', 'timeout', 'files'):
            with self.assertRaises(ValueError):
                A.command_args(dict(self.command, kwargs={key: 'bad'}))
        A.command_args(dict(self.command, method='GET', path='/openapi.json'))
        with self.assertRaises(ValueError):
            A.command_args(dict(self.command, method='POST', path='/openapi.json'))

    def test_wal_snapshot_sequence_and_capture(self):
        self.assertTrue(Path(str(self.database) + '-wal').exists())
        self.agent.snapshot()
        self.agent.snapshot()
        first, second = self.central.calls
        self.assertEqual(first[2]['headers']['X-Snapshot-Sequence'], '1')
        self.assertEqual(second[2]['headers']['X-Snapshot-Sequence'], '2')
        self.assertGreater(float(first[2]['headers']['X-Snapshot-Captured-At']), 0)
        backup = self.path / 'uploaded.db'
        backup.write_bytes(first[2]['data'])
        from contextlib import closing
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('SELECT * FROM inbounds').fetchall(), [(42,)])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(first[2]['timeout'], 45)
        self.assertFalse(first[2]['allow_redirects'])
        reopened = A.Journal(self.path / 'journal.db')
        try:
            self.assertEqual(reopened.sequence(), 3)
        finally:
            reopened.db.close()

    def test_duplicate_saved_and_crash_unknown(self):
        result = self.agent.execute(self.command)
        self.assertEqual(result['state'], 'done')
        self.assertEqual(self.agent.execute(self.command), result)
        self.assertEqual(len(self.local.calls), 1)
        self.journal.start('interrupted')
        reopened = A.Journal(self.path / 'journal.db')
        try:
            agent = A.Agent(self.config, reopened, self.central, self.local)
            result = agent.execute(dict(self.command, id='interrupted'))
            self.assertEqual(result['state'], 'unknown')
            self.assertEqual(len(self.local.calls), 1)
        finally:
            reopened.db.close()

    def test_failed_network_never_repeats_local_command(self):
        self.local.fail = True
        result = self.agent.execute(self.command)
        self.assertEqual(result['state'], 'unknown')
        self.assertNotIn('secret', result['error'])
        self.agent.execute(self.command)
        self.assertEqual(len(self.local.calls), 1)
        self.central.fail = True
        with self.assertRaises(RuntimeError):
            self.agent.cycle()
        self.assertEqual(len(self.journal.pending()), 1)
        self.central.fail = False
        self.agent.cycle()
        self.assertEqual(self.journal.pending(), [])
        poll = self.central.calls[-1]
        self.assertEqual(poll[2]['json']['results'][0]['id'], self.command['id'])

    def test_snapshot_before_poll_and_after_modify(self):
        self.central.responses = [Response(), Response(payload={'commands': [self.command]}), Response()]
        self.agent.cycle()
        self.assertEqual([c[0] for c in self.central.calls], ['PUT', 'POST', 'PUT'])
        self.assertEqual(len(self.journal.pending()), 1)
        self.assertFalse(self.local.trust_env)
        self.assertFalse(self.central.trust_env)
        call = self.local.calls[0]
        self.assertEqual(call[1], 'http://127.0.0.1:54321/hidden/panel/api/inbounds/add')
        self.assertFalse(call[2]['allow_redirects'])

    def test_acknowledge_only_included(self):
        self.agent.execute(self.command)
        included = self.journal.pending()
        self.agent.execute(dict(self.command, id='second'))
        self.journal.acknowledge(included)
        self.assertEqual([r['id'] for r in self.journal.pending()], ['second'])

    def test_login_credentials_remain_local(self):
        config = dict(self.config, xui_token='', xui_username='user', xui_password='pass')
        agent = A.Agent(config, self.journal, self.central, self.local)
        self.local.responses = [Response(), Response()]
        self.assertEqual(agent.execute(self.command)['state'], 'done')
        self.assertTrue(self.local.calls[0][1].endswith('/hidden/login'))
        agent.cycle()
        self.assertNotIn('pass', repr(self.central.calls))
        self.assertNotIn('local-secret', repr(self.central.calls))

    def test_response_limit_and_redirect_not_followed(self):
        response = Response(body=b'x' * (A.MAX_RESPONSE + 1))
        with self.assertRaises(ValueError):
            A.limited_response(response)
        self.assertTrue(response.closed)
        self.local.responses = [Response(status=302)]
        self.agent.snapshot_due = False
        self.assertEqual(self.agent.execute(self.command)['state'], 'done')
        self.assertTrue(self.agent.snapshot_due)
        self.central.responses = [Response(status=302)]
        with self.assertRaises(RuntimeError):
            self.agent.snapshot()

    def test_http_errors_are_completed_results_with_mutation_snapshot(self):
        for status in (404, 401, 500):
            with self.subTest(status=status):
                self.agent.snapshot_due = False
                body = 'HTTP error ' + str(status)
                self.local.responses = [Response(body=body.encode(), status=status)]
                command = dict(self.command, id='http-' + str(status))
                result = self.agent.execute(command)
                self.assertEqual(result['state'], 'done')
                self.assertEqual(result['response'], {'status': status, 'body': body})
                self.assertTrue(self.agent.snapshot_due)
                self.assertEqual(self.agent.execute(command), result)
        self.assertEqual(len(self.local.calls), 3)

    def test_applied_mutation_timeout_snapshots_before_unknown_report(self):
        def applied_then_timeout(*args, **kwargs):
            self.source.execute('INSERT INTO inbounds VALUES(43)')
            self.source.commit()
            raise TimeoutError('Local response lost after commit')
        self.central.responses = [Response(), Response(payload={'commands': [self.command]}), Response()]
        with patch.object(self.local, 'request', side_effect=applied_then_timeout) as request:
            self.agent.cycle()
            self.assertEqual([c[0] for c in self.central.calls], ['PUT', 'POST', 'PUT'])
            self.assertEqual(self.journal.saved(self.command['id'])['state'], 'unknown')
            backup = self.path / 'after-timeout.db'
            backup.write_bytes(self.central.calls[-1][2]['data'])
            from contextlib import closing
            with closing(sqlite3.connect(backup)) as db:
                self.assertEqual(db.execute('SELECT id FROM inbounds ORDER BY id').fetchall(), [(42,), (43,)])
            self.agent.cycle()
            sent = self.central.calls[-1][2]['json']['results']
            self.assertEqual(sent[0]['state'], 'unknown')
            self.assertEqual(sent[0]['response'], {'status': 0, 'body': ''})
            self.agent.execute(self.command)
            request.assert_called_once()

    def test_unknown_not_reported_until_reconciliation_snapshot_accepted(self):
        self.local.fail = True
        self.central.responses = [Response(), Response(payload={'commands': [self.command]}), Response(status=503)]
        with self.assertRaises(RuntimeError):
            self.agent.cycle()
        self.assertTrue(self.agent.snapshot_due)
        self.assertEqual(self.journal.pending()[0]['state'], 'unknown')
        self.central.responses = [Response(status=503)]
        with self.assertRaises(RuntimeError):
            self.agent.cycle()
        self.assertEqual([c[0] for c in self.central.calls], ['PUT', 'POST', 'PUT', 'PUT'])
        self.agent.cycle()
        self.assertEqual([c[0] for c in self.central.calls], ['PUT', 'POST', 'PUT', 'PUT', 'PUT', 'POST'])
        self.assertEqual(self.central.calls[-1][2]['json']['results'][0]['state'], 'unknown')
        self.assertEqual(len(self.local.calls), 1)

    def test_help_without_dependencies_or_checkout(self):
        for script in ('install-xui-agent.py', 'nexora-xui-agent.py'):
            result = subprocess.run([sys.executable, '-S', str(ROOT / 'scripts' / script), '--help'],
                                    cwd=self.tmp.name, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_reject_batch_and_preserve_pending(self):
        self.agent.execute(self.command)
        self.central.responses = [Response(), Response(payload={'commands': [self.command, self.command]})]
        with self.assertRaises(ValueError):
            self.agent.cycle()
        self.assertEqual(len(self.journal.pending()), 1)

    def test_real_loopback_api_and_no_redirect(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                calls.append((self.path, self.headers.get('Authorization')))
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                self.send_response(302 if self.path.endswith('/redirect') else 200)
                self.send_header('Location', '/forbidden')
                self.end_headers()
                self.wfile.write(b'{"success":true}')

            def log_message(self, *args):
                pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assert_loopback_reachable(server)
            config = dict(self.config, xui_url='http://127.0.0.1:' + str(server.server_port) + '/base')
            with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
                agent = A.Agent(config, self.journal, central=self.central)
                try:
                    self.assertEqual(agent.execute(self.command)['state'], 'done')
                    redirected = dict(self.command, id='redirect', path='/panel/api/redirect')
                    self.assertEqual(agent.execute(redirected)['response']['status'], 302)
                finally:
                    agent.local.close()
            self.assertEqual(calls, [('/base/panel/api/inbounds/add', 'Bearer local-secret'),
                                     ('/base/panel/api/redirect', 'Bearer local-secret')])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_installer_download_and_enroll_use_only_fixed_origin(self):
        from unittest.mock import MagicMock
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'{}'
        with patch.object(I, 'build_opener', return_value=opener):
            I.fetch('https://central.example/base', 'client.py')
            I.fetch('https://central.example/base', 'enroll', b'{"code":"once"}')
        first, second = opener.open.call_args_list
        self.assertEqual(first.args[0].full_url, 'https://central.example/base/api/xui-agent/client.py')
        self.assertEqual(second.args[0].get_method(), 'POST')
        self.assertEqual(second.args[0].data, b'{"code":"once"}')
        self.assertIsNone(I.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil/'))

    def test_oversize_snapshot_not_uploaded(self):
        with patch.object(A, 'MAX_SNAPSHOT', 100):
            with self.assertRaises(ValueError):
                self.agent.snapshot()
        self.assertEqual(self.central.calls, [])

    def test_poll_failure_keeps_results_and_malformed_reply_does_not_ack(self):
        self.agent.execute(self.command)
        self.central.responses = [Response(), Response(status=503)]
        with self.assertRaises(RuntimeError):
            self.agent.cycle()
        self.assertEqual(len(self.journal.pending()), 1)
        self.central.responses = [Response(payload={'wrong': []})]
        with self.assertRaises(KeyError):
            self.agent.cycle()
        self.assertEqual(len(self.journal.pending()), 1)

    def test_rejected_command_is_saved_without_local_request(self):
        bad = dict(self.command, kwargs={'headers': {'Authorization': 'upstream'}})
        self.assertEqual(self.agent.execute(bad)['state'], 'failed')
        self.assertEqual(self.agent.execute(bad)['state'], 'failed')
        self.assertEqual(self.local.calls, [])

    def test_snapshot_every_30_seconds_with_frequent_polls(self):
        with patch.object(A.time, 'monotonic', return_value=100):
            self.agent.cycle()
        with patch.object(A.time, 'monotonic', return_value=129):
            self.agent.cycle()
        self.assertEqual([c[0] for c in self.central.calls], ['PUT', 'POST', 'POST'])
        with patch.object(A.time, 'monotonic', return_value=130):
            self.agent.cycle()
        self.assertEqual([c[0] for c in self.central.calls], ['PUT', 'POST', 'POST', 'PUT', 'POST'])

    def test_installer_configuration_and_service_without_system_changes(self):
        import argparse
        from contextlib import ExitStack
        import venv
        home = self.path / 'installed'
        unit = self.path / 'agent.service'
        writes = []
        def write(path, data):
            writes.append((path, data))
            path.write_bytes(data)
        with ExitStack() as stack:
            stack.enter_context(patch.object(I, 'HOME', home))
            stack.enter_context(patch.object(I, 'UNIT', unit))
            stack.enter_context(patch.object(I.sys, 'platform', 'linux'))
            stack.enter_context(patch.object(I.os, 'geteuid', return_value=0, create=True))
            builder = stack.enter_context(patch.object(venv, 'EnvBuilder'))
            create = builder.return_value.create
            run = stack.enter_context(patch.object(I.subprocess, 'run'))
            run.return_value.returncode = 0
            fetch = stack.enter_context(patch.object(I, 'fetch', side_effect=[
                b'# standalone client', b'{"node_id":"node","token":"enrolled-secret","sequence_floor":72}']))
            stack.enter_context(patch('runpy.run_path', return_value={'base_url': A.base_url}))
            stack.enter_context(patch.object(I, 'private_write', side_effect=write))
            stack.enter_context(patch.object(I.getpass, 'getpass', side_effect=[
                'http://127.0.0.1:1234/base', '', 'local-user', 'local-password']))
            stack.enter_context(patch('builtins.input', side_effect=[str(self.database), 'yes']))
            stack.enter_context(patch('builtins.print'))
            I.install(argparse.Namespace(panel='https://central.example', code='once'))
        config = json.loads((home / 'config.json').read_text())
        self.assertEqual(config['xui_password'], 'local-password')
        self.assertEqual(config['token'], 'enrolled-secret')
        self.assertEqual(config['sequence_floor'], 72)
        self.assertNotIn('once', (home / 'config.json').read_text())
        self.assertEqual(json.loads(fetch.call_args_list[1].args[2]), {'code': 'once'})
        self.assertNotIn('local-password', repr(fetch.call_args_list))
        create.assert_called_once_with(home / 'venv')
        builder.assert_called_once_with(with_pip=False)
        self.assertIn('NoNewPrivileges=true', unit.read_text())
        self.assertIn('UMask=0077', unit.read_text())
        self.assertTrue(all('apt' not in str(call) and 'pip' not in str(call) for call in run.call_args_list))

    def test_stdlib_session_cookies_forms_json_params_and_http_errors(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                calls.append((self.path, body, self.headers.get('Cookie'), self.headers.get('Content-Type')))
                self.send_response(200 if self.path == '/login' else 404)
                if self.path == '/login':
                    self.send_header('Set-Cookie', 'session=local-cookie; Path=/; HttpOnly')
                self.end_headers()
                self.wfile.write(b'{"success":true}' if self.path == '/login' else b'route missing')

            def do_PUT(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                calls.append((self.path, body, self.headers.get('Content-Length'), self.headers.get('Content-Type')))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, *args):
                pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        session = A.Session()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            self.assert_loopback_reachable(server)
            with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
                login = session.request('POST', base + '/login', data={'username': 'local user', 'password': 'p&ss'})
                self.assertEqual(A.limited_response(login)['status'], 200)
                response = session.request('POST', base + '/panel/api/alternate',
                                           json={'id': 3}, params={'tag': ['a', 'b']})
                result = A.limited_response(response)
                self.assertEqual(result, {'status': 404, 'body': 'route missing'})
                with self.database.open('rb') as stream:
                    upload = session.request('PUT', base + '/snapshot', data=stream,
                                             headers={'Content-Type': 'application/octet-stream'})
                    try:
                        self.assertEqual(upload.json(), {'ok': True})
                    finally:
                        upload.close()
            self.assertEqual(calls[0][1], b'username=local+user&password=p%26ss')
            self.assertEqual(calls[0][3], 'application/x-www-form-urlencoded')
            self.assertEqual(calls[1][0], '/panel/api/alternate?tag=a&tag=b')
            self.assertEqual(json.loads(calls[1][1]), {'id': 3})
            self.assertEqual(calls[1][2], 'session=local-cookie')
            self.assertEqual(calls[1][3], 'application/json')
            self.assertEqual(calls[2][1], self.database.read_bytes())
            self.assertEqual(int(calls[2][2]), self.database.stat().st_size)
            self.assertEqual(calls[2][3], 'application/octet-stream')
        finally:
            session.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_stdlib_tls_verification_is_enabled(self):
        import ssl
        session = A.Session()
        try:
            contexts = [handler._context for handler in session.opener.handlers
                        if isinstance(handler, A.HTTPSHandler)]
            self.assertEqual(len(contexts), 1)
            self.assertTrue(contexts[0].check_hostname)
            self.assertEqual(contexts[0].verify_mode, ssl.CERT_REQUIRED)
        finally:
            session.close()

    @unittest.skipIf(sys.platform == 'win32', 'POSIX permissions require Linux')
    def test_installer_private_file_permissions(self):
        path = self.path / 'config.json'
        I.private_write(path, b'{"secret":"local"}')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.read_bytes(), b'{"secret":"local"}')

    @unittest.skipUnless((ROOT / 'backend/remote_xui.py').exists(), 'Central module is not in this distribution')
    def test_central_contract_and_lost_poll_acknowledgement(self):
        spec = importlib.util.spec_from_file_location('central_xui_contract', ROOT / 'backend/remote_xui.py')
        remote = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(remote)
        central_dir = self.path / 'central'
        central_dir.mkdir()
        with patch.dict(os.environ, {'CONFIG_PATH': str(central_dir / 'config.json')}):
            pair = remote.pair('Iran fixture', 'iran')
            enrollment = remote.enroll(pair['code'])
            node_id = enrollment['node_id']
            class Central(Session):
                lose_ack = False
                def request(inner, method, url, **kw):
                    self.assertEqual(inner.headers['Authorization'], 'Bearer ' + enrollment['token'])
                    remote.authenticate(inner.headers['Authorization'][7:])
                    if url.endswith('/snapshot'):
                        headers = kw['headers']
                        remote.receive_snapshot(node_id, kw['data'].read(),
                            int(headers['X-Snapshot-Sequence']), float(headers['X-Snapshot-Captured-At']))
                        return Response()
                    payload = remote.poll(node_id, kw['json']['results'])
                    if inner.lose_ack:
                        inner.lose_ack = False
                        raise RuntimeError('Acknowledgement lost after central commit')
                    return Response(payload=payload)
            central = Central()
            agent = A.Agent(dict(self.config, token=enrollment['token']), self.journal, central, self.local)
            with remote.connection() as db:
                db.execute('INSERT INTO remote_commands(id,node_id,payload,created) VALUES(?,?,?,?)',
                           (self.command['id'], node_id, json.dumps(self.command), A.time.time()))
            agent.cycle()
            self.assertEqual(len(self.local.calls), 1)
            self.assertEqual(len(self.journal.pending()), 1)
            central.lose_ack = True
            with self.assertRaises(RuntimeError):
                agent.cycle()
            self.assertEqual(len(self.journal.pending()), 1)
            agent.cycle()
            self.assertEqual(self.journal.pending(), [])
            self.assertEqual(len(self.local.calls), 1)
            with remote.connection() as db:
                row = db.execute('SELECT state,result FROM remote_commands WHERE id=?',
                                 (self.command['id'],)).fetchone()
                self.assertEqual(row['state'], 'done')
                self.assertEqual(json.loads(row['result'])['status'], 200)


if __name__ == '__main__':
    unittest.main()
