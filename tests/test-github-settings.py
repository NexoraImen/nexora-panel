"""Exercise all four update-settings API callers with real ASGI requests."""
import ast
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from backend import connectivity as NET
TREE = ast.parse((ROOT / 'backend/app.py').read_text(encoding='utf-8'))
spec = importlib.util.spec_from_file_location('restore_asgi_harness', ROOT / 'tests/test-restore-progress.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class GithubSettings(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'VERSION').write_text('2.3.10')
        self.environment = patch.dict(os.environ, GITHUB_REPO='', GITHUB_TOKEN='',
                                       NEXORA_LICENSE_DIR=str(self.root / 'data'))
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.launched = []
        self.requests = []
        self.network = patch('urllib.request.urlopen', side_effect=self.urlopen)
        self.network.start()
        self.addCleanup(self.network.stop)
        app = FastAPI()
        self.ns = dict(app=app, Header=Header, HTTPException=HTTPException, Request=Request,
                       JSONResponse=JSONResponse, json=json, os=os, Path=Path, _re=re,
                       urllib=urllib, NET=NET, log=logging.getLogger('github-test'),
                       __file__=str(self.root / 'backend/app.py'), _root_dir=lambda: self.root,
                       check_auth=self.auth, _run_cli_detached=self.launched.append,
                       UPDATE_LOG='/tmp/test-update.log', _FULL_RESTORE_LOCK=threading.Lock(),
                       _admin_path_ok=lambda value: value == 'secret',
                       _is_admin_api=lambda path: path.startswith('/api/admin/'))
        names = {'_github_repo', '_github_settings', 'github_get', 'github_put', 'check_update',
                 'run_update', '_admin_path_gate'}
        nodes = [n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'github-routes', 'exec'), self.ns)
        self.client = harness.ASGIClient(app)
        self.headers = {'X-Admin-Path': 'secret', 'X-Admin-Password': 'pw'}

    @staticmethod
    def auth(password):
        if password != 'pw':
            raise HTTPException(401, 'Unauthorized')

    def urlopen(self, req, **kwargs):
        self.requests.append(req)
        return io.BytesIO(b'{"tag_name":"v2.3.10","body":"release"}')

    async def request(self, path, method='GET', payload=None):
        headers = {**self.headers, 'Content-Type': 'application/json'}
        body = json.dumps(payload).encode() if payload is not None else b''
        return await self.client.request('/api/admin/' + path, headers=headers,
                                         method=method, content=body)

    async def test_default_repo_with_workflow_directory_in_all_callers(self):
        (self.root / '.github').mkdir()
        settings = await self.request('github')
        self.assertEqual(settings.json(), {'repo': 'NexoraImen/nexora-panel', 'configured': True})
        check = await self.request('check-update')
        self.assertTrue(check.json()['configured'])
        self.assertEqual(check.json()['latestVersion'], '2.3.10')
        launched = await self.request('run-update', 'POST')
        self.assertEqual(launched.status_code, 200)
        self.assertEqual(self.launched, ['update'])
        saved = await self.request('github', 'PUT', {'repo': 'custom/repo'})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue((self.root / '.github').is_dir())
        self.assertTrue((self.root / '.nexora-update.conf').is_file())
        self.assertEqual((await self.request('github')).json()['repo'], 'custom/repo')

    async def test_no_settings_defaults_to_official(self):
        self.assertEqual((await self.request('github')).json()['repo'], 'NexoraImen/nexora-panel')

    async def test_legacy_token_is_used_and_not_returned(self):
        (self.root / '.github').write_text('GITHUB_REPO="private/repo"\nGITHUB_TOKEN="PRIVATE_SECRET"\n')
        settings = await self.request('github')
        check = await self.request('check-update')
        self.assertEqual(settings.json()['repo'], 'private/repo')
        self.assertNotIn('PRIVATE_SECRET', settings.text + check.text)
        self.assertEqual(self.requests[-1].get_header('Authorization'), 'token PRIVATE_SECRET')

    async def test_modern_file_takes_precedence(self):
        (self.root / '.github').write_text('GITHUB_REPO=legacy/repo\n')
        (self.root / '.nexora-update.conf').write_text('GITHUB_REPO=modern/repo\n')
        self.assertEqual((await self.request('github')).json()['repo'], 'modern/repo')
        self.assertEqual((await self.request('check-update')).json()['repo'], 'modern/repo')

    async def test_save_keeps_existing_same_repository_token(self):
        (self.root / '.github').write_text('GITHUB_REPO=private/repo; GITHUB_TOKEN=PRIVATE_SECRET\n')
        saved = await self.request('github', 'PUT', {'repo': 'https://github.com/private/repo.git'})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.requests[-1].get_header('Authorization'), 'token PRIVATE_SECRET')
        self.assertIn('PRIVATE_SECRET', (self.root / '.nexora-update.conf').read_text())
        self.assertNotIn('PRIVATE_SECRET', saved.text)
        if os.name != 'nt':
            self.assertEqual((self.root / '.nexora-update.conf').stat().st_mode & 0o777, 0o600)

    async def test_reset_uses_official_default_without_old_token(self):
        (self.root / '.github').write_text('GITHUB_REPO=private/repo\nGITHUB_TOKEN=PRIVATE_SECRET\n')
        result = await self.request('github', 'PUT', {'repo': ''})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['repo'], 'NexoraImen/nexora-panel')
        self.assertNotIn('PRIVATE_SECRET', (self.root / '.nexora-update.conf').read_text())
        self.assertIsNone(self.requests[-1].get_header('Authorization'))

    async def test_shell_injection_and_bad_types_are_rejected_before_network(self):
        for repo in ('owner/repo";touch /tmp/unsafe', 'owner/repo\nGITHUB_TOKEN=bad',
                     'owner/repo;echo bad', '../repo', 'owner/..', [], 12):
            result = await self.request('github', 'PUT', {'repo': repo})
            self.assertEqual(result.status_code, 400, result.text)
        self.assertFalse(self.requests)
        self.assertFalse((self.root / '.nexora-update.conf').exists())

    async def test_network_failure_stays_configured_and_does_not_overwrite(self):
        old = self.root / '.nexora-update.conf'
        old.write_text('GITHUB_REPO=custom/repo\n')
        before = old.read_bytes()
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('PRIVATE_SECRET')):
            check = await self.request('check-update')
            save = await self.request('github', 'PUT', {'repo': 'other/repo'})
        self.assertTrue(check.json()['configured'])
        self.assertIn('error', check.json())
        self.assertNotIn('PRIVATE_SECRET', check.text + save.text)
        self.assertEqual(save.status_code, 400)
        self.assertEqual(old.read_bytes(), before)

    async def test_failed_atomic_replace_preserves_old_settings(self):
        old = self.root / '.nexora-update.conf'
        old.write_text('GITHUB_REPO=custom/repo\n')
        before = old.read_bytes()
        with patch('os.replace', side_effect=OSError('disk full')):
            result = await self.request('github', 'PUT', {'repo': 'other/repo'})
        self.assertEqual(result.status_code, 500)
        self.assertEqual(old.read_bytes(), before)
        self.assertEqual(list(self.root.glob('.nexora-update.conf.*')), [])

    async def test_api_and_bash_updater_choose_same_repo(self):
        cli = (ROOT / 'nexora-cli.sh').read_text(encoding='utf-8')
        section = cli.split('  update)\n', 1)[1].split('      info "Checking GitHub', 1)[0]
        script = self.root / 'choice.sh'
        script.write_text('INSTALL_DIR="$PWD"\nlogo(){ :; }\nbad(){ :; }\n' +
                          section + '\nfi\necho "SELECTED=$GITHUB_REPO"\n',
                          encoding='utf-8', newline='\n')
        bash = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else 'bash'
        for legacy, modern, directory in [(None, None, False), (None, None, True),
                                           ('legacy/repo', None, False),
                                           ('legacy/repo', 'modern/repo', False)]:
            for name in ('.github', '.nexora-update.conf'):
                path = self.root / name
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink(missing_ok=True)
            if directory:
                (self.root / '.github').mkdir()
            for name, repo in (('.github', legacy), ('.nexora-update.conf', modern)):
                if repo:
                    (self.root / name).write_text(f'GITHUB_REPO="{repo}"\n')
            selected = (await self.request('github')).json()['repo']
            result = subprocess.run([bash, str(script)], cwd=self.root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SELECTED=' + selected, result.stdout)

    async def test_admin_path_gate_still_hides_settings(self):
        result = await self.client.get('/api/admin/github')
        self.assertEqual(result.status_code, 404)
        self.assertFalse(self.requests)


if __name__ == '__main__':
    unittest.main()
