"""Selective routing, credential boundaries and the real loopback bridge."""
import asyncio
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import time
import ssl
import threading
import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import connectivity as N


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class Connectivity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, NEXORA_LICENSE_DIR=self.temp.name)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def grant(self):
        return {"token": "test-credential", "machine": "a" * 64,
                "expires": int(time.time()) + 3600,
                "endpoints": ["wss://relay.example/v1/connect"]}

    def runtime(self, **updates):
        state = {"checked": time.time(), "port": 12345, "ready": True, "state": "connected",
                 "routes": {"telegram": "managed", "github": "managed"},
                 "services": {"telegram": "managed", "github": "managed"}}
        state.update(updates)
        N.write("connect-runtime.json", state)

    def test_grant_validation_and_removal(self):
        grant = self.grant()
        N.install(grant, "a" * 64)
        self.assertEqual(N.read("connectivity.json")["token"], grant["token"])
        for update in ({"machine": "b" * 64}, {"expires": 0}, {"expires": int(time.time()) + 90000},
                       {"endpoints": ["http://relay.example/"]}, {"endpoints": ["wss://u:p@relay.example/"]},
                       {"endpoints": []}, {"token": ""}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                N.install({**grant, **update}, "a" * 64)
        N.remove()
        self.assertEqual(N.read("connectivity.json"), {})
        N.install(None, "a" * 64)
        self.assertFalse(N.lease_due())
        self.assertTrue(N.lease_due(time.time() + 21601))

    def test_routes_are_selective_and_stale_agent_fails_closed(self):
        self.runtime()
        self.assertEqual(N.proxy_for("https://api.telegram.org/botSECRET/getMe"), "http://127.0.0.1:12345")
        for url in ("http://api.telegram.org/", "https://api.telegram.org:444/", "https://api.telegram.org.evil/",
                    "https://127.0.0.1/", "https://private-xui.example/", "https://u@api.github.com/"):
            self.assertIsNone(N.proxy_for(url), url)
        self.runtime(checked=time.time() - 901)
        with self.assertRaises(urllib.error.URLError):
            N.proxy_for("https://api.telegram.org/")
        self.assertIsNone(N.proxy_for("https://private-xui.example/"))

    def test_status_has_no_credentials_or_port(self):
        N.install(self.grant(), "a" * 64)
        self.runtime()
        status = json.dumps(N.status())
        self.assertNotIn("test-credential", status)
        self.assertNotIn("12345", status)
        self.assertTrue(N.status()["ready"])
        self.runtime(checked=0)
        self.assertFalse(N.status()["ready"])

    def test_requests_urllib_and_release_feed(self):
        self.runtime()
        N.install(self.grant(), "a" * 64)
        with patch("requests.Session.request", return_value="ok") as call:
            with N.session() as session:
                self.assertEqual(session.get("https://api.telegram.org/", timeout=3), "ok")
            self.assertEqual(call.call_args.kwargs["proxies"], {"https": "http://127.0.0.1:12345"})
        with patch("urllib.request.urlopen", return_value="direct") as direct:
            self.assertEqual(N.urlopen("https://private-xui.example/"), "direct")
            direct.assert_called_once()
        opener = MagicMock()
        with patch("urllib.request.build_opener", return_value=opener):
            N.urlopen(N.OFFICIAL_RELEASE)
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://relay.example/v1/releases")
        self.assertEqual(req.get_header("Authorization"), "Bearer test-credential")
        req = urllib.request.Request("https://api.telegram.org/")
        with patch.dict(os.environ, NO_PROXY="*", no_proxy="*"):
            N.LoopbackProxy({"https": "http://127.0.0.1:12345"}).proxy_open(req, "http://127.0.0.1:12345", "https")
        self.assertEqual(req.host, "127.0.0.1:12345")
        self.assertEqual(req._tunnel_host, "api.telegram.org")

    def test_install_unit_has_no_host_network_side_effect(self):
        install = module("connect_install", "scripts/install-connect.py")
        text = install.unit(ROOT)
        self.assertIn("127.0.0.1", (ROOT / "scripts/nexora-connect.py").read_text())
        self.assertIn("UMask=0077", text)
        self.assertNotIn("x-ui", text)
        self.assertNotIn("HTTP_PROXY", text)

    def test_rollback_disables_agent_when_old_backend_has_no_support(self):
        root = Path(self.temp.name)
        (root / "backend/venv/bin").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "units").mkdir()
        (root / "scripts/install-connect.py").touch()
        support = root / "backend/connectivity.py"
        support.touch()
        python = root / "backend/venv/bin/python"
        python.write_text('#!/bin/bash\necho agent-started\n', newline="\n")
        python.chmod(0o755)
        (root / "units/nexora-connect.service").write_text('# Managed by Nexora: selective outbound connectivity\n')
        cli = (ROOT / "nexora-cli.sh").read_text(encoding="utf-8")
        body = cli[cli.index("sync_connect() {"):]
        body = body[:body.index("\n}\n") + 3].replace("/etc/systemd/system", (root / "units").as_posix())
        bash = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
        script = root / "test.sh"
        script.write_text('set -e\nINSTALL_DIR="' + root.as_posix() + '"\n' + body +
                          '\nsystemctl() { echo "service $*"; }\nsync_connect\n', encoding="utf-8", newline="\n")
        result = subprocess.run([bash, str(script)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("agent-started", result.stdout)
        support.unlink()
        result = subprocess.run([bash, str(script)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service disable --now nexora-connect", result.stdout)
        self.assertNotIn("x-ui", result.stdout)

    def test_curl_preserves_args_and_scopes_proxy_to_child(self):
        curl = module("connect_curl", "scripts/net-curl.py")
        self.runtime()
        with patch.object(curl.subprocess, "run") as run:
            run.return_value.returncode = 7
            self.assertEqual(curl.main(["-sL", "https://github.com/a/b/archive.zip"]), 7)
            self.assertEqual(run.call_args.args[0], ["curl", "-sL", "https://github.com/a/b/archive.zip"])
            self.assertEqual(run.call_args.kwargs["env"]["https_proxy"], "http://127.0.0.1:12345")
        self.assertNotEqual(os.environ.get("https_proxy"), "http://127.0.0.1:12345")

    def test_uninstall_stops_writers_before_removing_files(self):
        root = Path(self.temp.name)
        units = root / "units"
        units.mkdir()
        for name in ("nexora-panel", "nexora-bot", "nexora-connect"):
            (units / (name + ".service")).touch()
        source = (ROOT / "uninstall.sh").read_text(encoding="utf-8")
        block = source[source.index('step "Removing service"'):source.index("# ── nginx")]
        block = block.replace("/etc/systemd/system", units.as_posix())
        script = root / "uninstall-test.sh"
        script.write_text('set -e\nstep() { :; }\nok() { :; }\nsystemctl() { echo "$*"; }\n' + block,
                          encoding="utf-8", newline="\n")
        bash = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
        result = subprocess.run([bash, str(script)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(units.iterdir()), [])
        for name in ("nexora-panel", "nexora-bot", "nexora-connect"):
            self.assertIn("stop " + name, result.stdout)
        self.assertNotIn("x-ui", result.stdout)

    def test_backup_does_not_transfer_grants(self):
        from backend import backup
        self.assertNotIn("connectivity.json", backup.FILES)
        self.assertNotIn("connect-runtime.json", backup.FILES)

    def test_monitor_automatically_selects_managed_and_direct_paths(self):
        agent = module("connect_monitor", "scripts/nexora-connect.py")
        N.install(self.grant(), "a" * 64)
        async def check():
            for direct in (False, True):
                with patch.object(agent, "probe", side_effect=lambda url, proxy=None: direct or bool(proxy)), patch.object(
                        agent.asyncio, "sleep", side_effect=asyncio.CancelledError()):
                    with self.assertRaises(asyncio.CancelledError): await agent.monitor(12345)
                expected = "direct" if direct else "managed"
                self.assertEqual(N.status()["services"], {"telegram": expected, "github": expected})
                self.assertTrue(N.status()["ready"])
        asyncio.run(check())

    def test_admin_routes_protect_and_redact_state(self):
        import ast
        from fastapi import FastAPI, Depends, Request
        from fastapi.responses import JSONResponse
        harness = module("connect_asgi", "tests/test-restore-progress.py")
        app = FastAPI()
        tree = ast.parse((ROOT / "backend/app.py").read_text(encoding="utf-8"))
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name in {"connectivity_get", "connectivity_check", "_admin_path_gate"}]
        namespace = dict(app=app, NET=N, Depends=Depends, Request=Request, JSONResponse=JSONResponse,
                         _admin_path_ok=lambda value: value == "secret",
                         _is_admin_api=lambda path: path.startswith("/api/admin/"),
                         _FULL_RESTORE_LOCK=threading.Lock(), check_auth=lambda: None, time=time)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "connectivity-routes", "exec"), namespace)
        N.install(self.grant(), "a" * 64)
        self.runtime()
        client = harness.ASGIClient(app)
        response = asyncio.run(client.request("/api/admin/connectivity"))
        self.assertEqual(response.status_code, 404)
        headers = {"X-Admin-Path": "secret"}
        response = asyncio.run(client.request("/api/admin/connectivity", headers=headers))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"test-credential", response.content)
        response = asyncio.run(client.request("/api/admin/connectivity/check", method="POST", headers=headers))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(N.read("connect-recheck.json")["at"], 0)


class Bridge(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = module("connect_agent", "scripts/nexora-connect.py")
        self.server = await asyncio.start_server(self.agent.bridge, "127.0.0.1", 0, limit=8192)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def test_rejected_target_never_opens_remote(self):
        with patch.object(self.agent, "websocket_connect") as remote:
            reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
            writer.write(b"CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n")
            await writer.drain()
            self.assertIn(b"502", await reader.read())
            writer.close()
            await writer.wait_closed()
            remote.assert_not_called()

    async def test_http10_connect_opaque_bytes_and_cleanup(self):
        from unittest.mock import AsyncMock
        output = asyncio.Queue()
        class Socket:
            async def recv(self): return "ready"
            async def send(self, data): await output.put(data)
            def __aiter__(self): return self
            async def __anext__(self): return await output.get()
            close = AsyncMock()
        ws = Socket()
        grant = {"endpoints": ["wss://relay.example/v1/connect"], "token": "test-only"}
        with patch.object(self.agent, "current_grant", return_value=grant), patch.object(
                self.agent, "websocket_connect", new=AsyncMock(return_value=ws)) as remote:
            reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
            writer.write(b"CONNECT api.telegram.org:443 HTTP/1.0\r\n\r\n")
            await writer.drain()
            self.assertIn(b"200", await reader.readuntil(b"\r\n\r\n"))
            payload = b"\x16\x03\x03opaque TLS bytes"
            writer.write(payload)
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)), 2), payload)
            self.assertIsNone(remote.call_args.kwargs["proxy"])
            writer.close()
            await writer.wait_closed()
            for _ in range(20):
                if self.agent._active == 0: break
                await asyncio.sleep(.01)
            self.assertEqual(self.agent._active, 0)
            ws.close.assert_awaited()

    async def test_real_wss_certificate_verification_and_opaque_transport(self):
        from websockets.asyncio.server import serve
        from websockets.asyncio.client import connect
        with tempfile.TemporaryDirectory() as directory:
            certfile, keyfile = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            # Community must not rely on the issuer-only cryptography package.
            openssl = "C:/Program Files/Git/usr/bin/openssl.exe" if os.name == "nt" else shutil.which("openssl")
            self.assertTrue(openssl, "OpenSSL is required to generate temporary TLS test certificates")
            subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                            "-keyout", keyfile.as_posix(), "-out", certfile.as_posix(), "-days", "1",
                            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,DNS:api.telegram.org"],
                           check=True, capture_output=True, timeout=20)
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(certfile, keyfile)
            trusted = ssl.create_default_context(cafile=str(certfile))
            inner_port = None
            async def echo(ws):
                await ws.send("ready")
                if inner_port is None:
                    async for data in ws: await ws.send(data)
                    return
                source, destination = await asyncio.open_connection("127.0.0.1", inner_port)
                async def upload():
                    async for data in ws:
                        destination.write(data)
                        await destination.drain()
                async def download():
                    while data := await source.read(65536): await ws.send(data)
                tasks = [asyncio.create_task(upload()), asyncio.create_task(download())]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks: task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    destination.close()
                    await destination.wait_closed()
            async with serve(echo, "127.0.0.1", 0, ssl=server_context) as remote:
                port = remote.sockets[0].getsockname()[1]
                for host, context, success in (("localhost", trusted, True),
                                                ("localhost", ssl.create_default_context(), False),
                                                ("127.0.0.1", trusted, False)):
                    grant = {"token": "test-only", "endpoints": [f"wss://{host}:{port}/v1/connect"]}
                    def secure_connect(*args, **kwargs): return connect(*args, ssl=context, **kwargs)
                    with patch.object(self.agent, "current_grant", return_value=grant), patch.object(
                            self.agent, "websocket_connect", new=secure_connect):
                        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
                        writer.write(b"CONNECT api.telegram.org:443 HTTP/1.1\r\n\r\n")
                        await writer.drain()
                        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 4)
                        self.assertIn(b"200" if success else b"502", response)
                        if success:
                            writer.write(b"opaque inner TLS")
                            await writer.drain()
                            self.assertEqual(await reader.readexactly(16), b"opaque inner TLS")
                        writer.close()
                        await writer.wait_closed()
                async def https(reader, writer):
                    await reader.readuntil(b"\r\n\r\n")
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 11\r\nConnection: close\r\n\r\n{\"ok\":true}")
                    await writer.drain()
                    writer.close()
                inner = await asyncio.start_server(https, "127.0.0.1", 0, ssl=server_context)
                inner_port = inner.sockets[0].getsockname()[1]
                remote_port = remote.sockets[0].getsockname()[1]
                grant = {"state": "granted", "expires": time.time() + 300, "token": "test-only",
                         "endpoints": [f"wss://localhost:{remote_port}/v1/connect"]}
                original_opener = urllib.request.build_opener
                def trusted_opener(*handlers):
                    return original_opener(*handlers, urllib.request.HTTPSHandler(context=trusted))
                def secure_connect(*args, **kwargs): return connect(*args, ssl=trusted, **kwargs)
                with patch.dict(os.environ, NEXORA_LICENSE_DIR=directory, NO_PROXY="*", no_proxy="*"), patch.object(
                        self.agent, "websocket_connect", new=secure_connect), patch(
                        "urllib.request.build_opener", new=trusted_opener):
                    N.write("connectivity.json", grant)
                    N.write("connect-runtime.json", {"checked": time.time(), "port": self.port,
                        "routes": {"telegram": "managed"}, "services": {"telegram": "managed"}})
                    def get():
                        with N.urlopen("https://api.telegram.org/test", timeout=5) as response:
                            return response.read()
                    self.assertEqual(await asyncio.to_thread(get), b'{"ok":true}')
                inner.close()
                await inner.wait_closed()

    async def test_credential_bearing_websocket_redirect_is_not_followed(self):
        from websockets.asyncio.server import serve
        from websockets.asyncio.client import connect
        from websockets.exceptions import SecurityError
        calls = []
        async def handler(ws): calls.append(ws)
        async with serve(handler, "127.0.0.1", 0) as target:
            port = target.sockets[0].getsockname()[1]
            def redirect(connection, request):
                response = connection.respond(302, "Moved")
                response.headers["Location"] = f"ws://127.0.0.1:{port}/"
                return response
            async with serve(handler, "127.0.0.1", 0, process_request=redirect) as source:
                port = source.sockets[0].getsockname()[1]
                with self.assertRaises(SecurityError):
                    await connect(f"ws://127.0.0.1:{port}", additional_headers={"Authorization": "Bearer test-only"}, proxy=None)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
