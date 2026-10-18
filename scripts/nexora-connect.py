#!/usr/bin/env python3
"""Loopback-only selective CONNECT bridge; remote transport is authenticated WSS."""
import asyncio
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import connectivity as N

# One initial handshake, no credential-bearing redirect to another host.
os.environ["WEBSOCKETS_MAX_REDIRECTS"] = "1"
from websockets.asyncio.client import connect as websocket_connect

logging.getLogger("websockets").setLevel(logging.CRITICAL)
_active = 0


def current_grant():
    grant = N.read("connectivity.json")
    if grant.get("state") != "granted" or grant.get("expires", 0) <= time.time():
        raise ValueError("Managed access is not available")
    return grant


async def bridge(reader, writer):
    global _active
    tasks = []
    accepted = False
    claimed = False
    try:
        if _active >= 16:
            raise ValueError("Local connection limit reached")
        _active += 1
        claimed = True
        header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 8)
        if len(header) > 8192:
            raise ValueError("Header too large")
        method, authority, version = header.split(b"\r\n", 1)[0].decode("ascii").split()
        parsed = urllib.parse.urlsplit("//" + authority)
        # Python before 3.12 uses HTTP/1.0 for CONNECT tunnels.
        if (method != "CONNECT" or version not in ("HTTP/1.0", "HTTP/1.1") or parsed.port != 443
                or parsed.username or parsed.password or parsed.path
                or parsed.hostname not in N.HOSTS):
            raise ValueError("Target not allowed")
        grant = current_grant()
        ws = None
        for endpoint in grant["endpoints"]:
            candidate = None
            try:
                candidate = await websocket_connect(
                    endpoint + "?host=" + parsed.hostname,
                    additional_headers={"Authorization": "Bearer " + grant["token"]},
                    proxy=None, compression=None, max_size=65536, max_queue=4,
                    open_timeout=8, close_timeout=2)
                if await asyncio.wait_for(candidate.recv(), 8) != "ready":
                    await candidate.close()
                    raise ValueError("Relay was not ready")
                ws = candidate
                break
            except Exception:
                if candidate is not None:
                    await candidate.close()
                continue
        if ws is None:
            raise OSError("No managed endpoint reached")
        try:
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            accepted = True

            async def upload():
                while True:
                    data = await asyncio.wait_for(reader.read(65536), 90)
                    if not data:
                        return
                    await ws.send(data)

            async def download():
                async for data in ws:
                    if not isinstance(data, bytes):
                        raise ValueError("Unexpected relay message")
                    writer.write(data)
                    await writer.drain()

            tasks = [asyncio.create_task(upload()), asyncio.create_task(download())]
            done, _ = await asyncio.wait(tasks, timeout=600, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await ws.close()
    except Exception:
        if not accepted:
            writer.write(b"HTTP/1.1 502 Managed connection unavailable\r\nContent-Length: 0\r\n\r\n")
            try:
                await writer.drain()
            except OSError:
                pass
    finally:
        if claimed:
            _active -= 1
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


def probe(url, proxy=None):
    # Explicit opener avoids inheriting unrelated system proxy settings or loops.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    handler = N.LoopbackProxy({"https": proxy}) if proxy else urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(handler, NoRedirect())
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "nexora-connect"})
        with opener.open(req, timeout=5) as response:
            return 200 <= response.status < 400
    except urllib.error.HTTPError as e:
        # Telegram's root redirects to documentation. This tests the network
        # path only, never whether a particular bot token is valid.
        return 300 <= e.code < 400
    except Exception:
        return False


async def monitor(port):
    local = f"http://127.0.0.1:{port}"
    while True:
        services, routes = {}, {}
        grant = N.read("connectivity.json")
        valid = grant.get("state") == "granted" and grant.get("expires", 0) > time.time()
        for group, urls in (("telegram", ("https://api.telegram.org/",)),
                            ("github", ("https://api.github.com/rate_limit", "https://github.com/",
                                        "https://codeload.github.com/NexoraImen/nexora-panel/zip/HEAD"))):
            async def reachable(proxy=None):
                for url in urls:
                    if not await asyncio.to_thread(probe, url, proxy):
                        return False
                return True
            if await reachable():
                services[group], routes[group] = "direct", "direct"
            elif valid and await reachable(local):
                services[group], routes[group] = "managed", "managed"
            else:
                services[group], routes[group] = "unavailable", "managed" if valid else "direct"
        ready = all(value != "unavailable" for value in services.values())
        fallback = "expired" if grant.get("state") == "granted" else grant.get("state", "waiting_for_license")
        state = "connected" if ready else ("reconnecting" if valid else fallback)
        N.write("connect-runtime.json", {"port": port, "checked": time.time(),
                                         "services": services, "routes": routes,
                                         "ready": ready, "state": state})
        started = time.time()
        while time.time() - started < 300:
            await asyncio.sleep(5)
            if N.read("connect-recheck.json").get("at", 0) > started:
                break


async def main():
    # Ephemeral port avoids taking a listener already used by VPN/tunnel services.
    server = await asyncio.start_server(bridge, "127.0.0.1", 0, limit=8192)
    port = server.sockets[0].getsockname()[1]
    async with server:
        await monitor(port)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
