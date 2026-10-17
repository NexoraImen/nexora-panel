"""Actual restore core and ASGI route, isolated from app startup threads."""
import ast
import asyncio
import json
import logging
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import backup as B
TREE = ast.parse((ROOT / "backend/app.py").read_text(encoding="utf-8"))


class ASGIClient:
    def __init__(self, app):
        self.app = app

    async def request(self, path, headers=None, method="GET", content=b""):
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
                 "http_version": "1.1", "method": method, "path": path,
                 "raw_path": path.encode(), "query_string": b"", "root_path": "",
                 "scheme": "http", "server": ("test", 80), "client": ("127.0.0.1", 1234),
                 "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
        sent = False
        result = types.SimpleNamespace(content=b"", headers={})

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": content, "more_body": False}
            await asyncio.Event().wait()

        async def send(message):
            if message["type"] == "http.response.start":
                result.status_code = message["status"]
                result.headers = {k.decode(): v.decode() for k, v in message["headers"]}
            elif message["type"] == "http.response.body":
                result.content += message.get("body", b"")

        await self.app(scope, receive, send)
        result.text = result.content.decode()
        result.json = lambda: json.loads(result.text)
        return result

    async def post(self, path, **kwargs):
        return await self.request(path, method="POST", **kwargs)

    async def get(self, path, **kwargs):
        return await self.request(path, **kwargs)


class RestoreProgress(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        (self.data / "config.json").write_text('{"brand": "test"}')
        self.archive = self.data / "source.zip"
        B.build(self.data, {}, "2.3.8", self.archive)
        self.body = self.archive.read_bytes()
        self.actions = []
        self.lock = threading.Lock()
        app = FastAPI()
        self.ns = dict(app=app, Request=Request, Header=Header, HTTPException=HTTPException,
                       JSONResponse=JSONResponse, _threading=threading, json=json,
                       CONFIG_PATH=self.data / "config.json", BACKUP=B,
                       _FULL_RESTORE_LOCK=self.lock, log=logging.getLogger("restore-test"),
                       _backup_dir=lambda: self.data, _backup_dbs=lambda: {},
                       _panel_version=lambda: "2.3.8", _backup_host=lambda: "test",
                       _svc_active=lambda: False,
                       _svc=lambda action: (self.actions.append(action) is None, ""),
                       check_auth=self.auth, _admin_path_ok=lambda path: path == "secret",
                       _is_admin_api=lambda path: path.startswith("/api/admin/"))
        names = {"_restore_full_upload", "backup_full_restore", "_admin_path_gate"}
        nodes = [n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "restore-routes", "exec"), self.ns)

        @app.get("/api/health")
        def health():
            return {"ok": True}

        @app.get("/api/admin/ping")
        def ping():
            return {"ok": True}

        self.client = ASGIClient(app)
        self.headers = {"X-Admin-Password": "pw", "X-Admin-Path": "secret"}
        self.path = "/api/admin/backup/full/restore"

    @staticmethod
    def auth(password):
        if password != "pw":
            raise HTTPException(401, "Unauthorized")

    async def post(self, stream=False, body=None):
        headers = dict(self.headers)
        if stream:
            headers["Accept"] = "application/x-ndjson"
        return await self.client.post(self.path, headers=headers, content=self.body if body is None else body)

    async def test_progress_matches_actual_core_boundaries(self):
        events = []
        result = B.restore(self.archive, self.data, {}, "2.3.8", self.data / "safe.zip",
                           progress=lambda **event: events.append(event))
        self.assertEqual([e["phase"] for e in events[:3]], ["verify", "safety", "restore"])
        self.assertEqual(events[-1]["completed"], len(result["restored"]))
        self.assertEqual(events[-1]["total"], len(result["restored"]))

    async def test_existing_stopped_bot_stays_stopped(self):
        response = await self.post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["botRestarted"])
        self.assertEqual(self.actions, [])
        self.assertFalse(self.lock.locked())

    async def test_running_bot_is_stopped_then_resumed(self):
        self.ns["_svc_active"] = lambda: True
        response = await self.post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.actions, ["stop", "start"])
        self.assertTrue(response.json()["botRestarted"])

    async def test_corrupt_backup_does_not_stop_bot(self):
        self.ns["_svc_active"] = lambda: True
        response = await self.post(body=b"not a zip")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.actions, [])
        self.assertFalse(self.lock.locked())

    async def test_missing_authorization_or_upload_does_not_take_lock(self):
        for headers, expected in (({}, 404), ({**self.headers, "X-Admin-Password": "bad"}, 401)):
            response = await self.client.post(self.path, headers=headers, content=self.body)
            self.assertEqual(response.status_code, expected)
            self.assertFalse(self.lock.locked())
        self.assertEqual((await self.post(body=b"")).status_code, 400)
        self.assertFalse(self.lock.locked())

    async def test_stop_or_safety_failure_does_not_write_destination(self):
        self.ns["_svc_active"] = lambda: True
        before = (self.data / "config.json").read_bytes()
        self.ns["_svc"] = lambda action: (False, "stop refused")
        with patch.object(B, "build") as build:
            response = await self.post()
            self.assertEqual(response.status_code, 400)
            build.assert_not_called()
        self.assertEqual((self.data / "config.json").read_bytes(), before)
        self.ns["_svc"] = lambda action: (self.actions.append(action) is None, "")
        with patch.object(B, "build", side_effect=OSError("disk full")):
            response = await self.post()
        self.assertEqual(response.status_code, 400)
        self.assertIn("نسخه‌ی امن", response.json()["detail"])
        self.assertEqual((self.data / "config.json").read_bytes(), before)
        self.assertEqual(self.actions, ["stop"])
        self.assertFalse(self.lock.locked())

    async def test_health_responsive_and_other_requests_are_explicit(self):
        entered, release = threading.Event(), threading.Event()

        def slow(*args, progress, prepare, **kwargs):
            progress(phase="safety")
            entered.set()
            release.wait(4)
            return {"restored": [], "from": "2.3.8"}

        with patch.object(B, "restore", slow):
            task = asyncio.create_task(self.post())
            try:
                for _ in range(100):
                    if entered.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(entered.is_set())
                started = time.monotonic()
                response = await asyncio.wait_for(self.client.get("/api/health"), .5)
                self.assertTrue(response.json()["ok"])
                self.assertLess(time.monotonic() - started, .5)
                self.assertEqual((await self.post()).status_code, 409)
                blocked = await self.client.get("/api/admin/ping", headers=self.headers)
                self.assertEqual(blocked.status_code, 503)
                self.assertIn("بازیابی", blocked.json()["detail"])
                hidden = await self.client.get("/api/admin/ping")
                self.assertEqual(hidden.status_code, 404)
            finally:
                release.set()
                await task

    async def test_stream_has_terminal_success_or_failure(self):
        for body, terminal in ((self.body, "complete"), (b"bad zip", "failed")):
            response = await self.post(stream=True, body=body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["x-accel-buffering"], "no")
            events = [json.loads(line) for line in response.text.splitlines()]
            self.assertEqual(events[-1]["phase"], terminal)
            self.assertFalse(self.lock.locked())

    async def test_disconnect_does_not_release_live_worker_lock(self):
        entered, release = threading.Event(), threading.Event()

        def slow(*args, progress, prepare, **kwargs):
            entered.set()
            release.wait(4)
            return {"restored": [], "from": "2.3.8"}

        request = types.SimpleNamespace(headers={"accept": "application/x-ndjson"})
        async def body():
            return self.body
        request.body = body
        with patch.object(B, "restore", slow):
            try:
                response = await self.ns["backup_full_restore"](request, "pw")
                await anext(response.body_iterator)
                await response.body_iterator.aclose()
                self.assertTrue(self.lock.locked())
                self.assertEqual((await self.post()).status_code, 409)
            finally:
                release.set()
                for _ in range(100):
                    if not self.lock.locked():
                        break
                    await asyncio.sleep(.01)
            self.assertFalse(self.lock.locked())

    async def test_partial_failure_keeps_bot_stopped_and_reports_truthfully(self):
        self.ns["_svc_active"] = lambda: True

        def fail(*args, progress, prepare, **kwargs):
            prepare()
            raise B.BackupError("simulated write error")

        with patch.object(B, "restore", fail):
            response = await self.post()
        self.assertEqual(response.status_code, 400)
        self.assertIn("خاموش", response.json()["detail"])
        self.assertEqual(self.actions, ["stop"])
        self.assertFalse(self.lock.locked())


if __name__ == "__main__":
    unittest.main()
