"""Managed egress state and selective clients. No global proxy or routing changes."""
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOSTS = {
    "api.telegram.org": "telegram",
    "api.github.com": "github", "github.com": "github",
    "codeload.github.com": "github", "raw.githubusercontent.com": "github",
    "objects.githubusercontent.com": "github", "release-assets.githubusercontent.com": "github",
}
OFFICIAL_RELEASE = "https://api.github.com/repos/NexoraImen/nexora-panel/releases/latest"


def directory():
    return Path(os.getenv("NEXORA_LICENSE_DIR", str(Path(__file__).resolve().parents[1] / "data")))


def read(name):
    try:
        value = json.loads((directory() / name).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write(name, value):
    root = directory()
    root.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root,
                                         prefix=".connect-", delete=False) as f:
            temporary = Path(f.name)
            json.dump(value, f)
        os.replace(temporary, root / name)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install(grant, machine):
    """Called only after the accompanying license signature and binding pass."""
    if not grant:
        write("connectivity.json", {"state": "provider_unconfigured", "checked": time.time()})
        return
    try:
        endpoints = grant["endpoints"]
        valid = (grant["machine"] == machine and isinstance(grant["token"], str)
                 and 1 <= len(grant["token"]) <= 4096
                 and isinstance(grant["expires"], int)
                 and time.time() < grant["expires"] <= time.time() + 86460
                 and isinstance(endpoints, list) and 1 <= len(endpoints) <= 4)
        for endpoint in endpoints:
            url = urllib.parse.urlsplit(endpoint)
            valid = valid and (url.scheme == "wss" and bool(url.hostname)
                               and not url.username and not url.password
                               and not url.query and not url.fragment)
        if not valid:
            raise ValueError("invalid managed grant")
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid managed connection grant") from None
    write("connectivity.json", {**grant, "state": "granted", "checked": time.time()})
    write("connect-recheck.json", {"at": time.time()})


def lease_due(now=None):
    now = time.time() if now is None else now
    grant = read("connectivity.json")
    if grant.get("state") != "granted":
        return now - grant.get("checked", 0) >= 6 * 3600
    return grant.get("expires", 0) - now < 12 * 3600


def remove():
    for name in ("connectivity.json", "connect-runtime.json", "connect-recheck.json"):
        (directory() / name).unlink(missing_ok=True)


def target(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme == "https" and parsed.port in (None, 443) and not parsed.username:
            return HOSTS.get(parsed.hostname)
    except (ValueError, TypeError):
        pass
    return None


def proxy_for(url):
    group = target(url)
    if not group:
        return None
    runtime = read("connect-runtime.json")
    if runtime.get("routes", {}).get(group) != "managed":
        return None
    if (time.time() - runtime.get("checked", 0) > 900
            or runtime.get("services", {}).get(group) != "managed"
            or not isinstance(runtime.get("port"), int) or not 1 <= runtime["port"] <= 65535):
        raise urllib.error.URLError("Managed connection is not ready; check panel connectivity status")
    return f"http://127.0.0.1:{runtime['port']}"


class LoopbackProxy(urllib.request.ProxyHandler):
    def proxy_open(self, request, proxy, protocol):
        # Ambient NO_PROXY must not bypass an explicitly selected managed path.
        request.set_proxy(urllib.parse.urlsplit(proxy).netloc, "http")
        return None


def urlopen(request, timeout=15):
    url = request.full_url if hasattr(request, "full_url") else request
    proxy = proxy_for(url)
    if proxy:
        if url == OFFICIAL_RELEASE:
            return release_feed(timeout)
        return urllib.request.build_opener(LoopbackProxy({"https": proxy})).open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def release_feed(timeout=15):
    grant = read("connectivity.json")
    if grant.get("expires", 0) <= time.time():
        raise urllib.error.URLError("Managed access expired")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for endpoint in grant.get("endpoints", []):
        parsed = urllib.parse.urlsplit(endpoint)
        url = urllib.parse.urlunsplit(("https", parsed.netloc, "/v1/releases", "", ""))
        try:
            return opener.open(urllib.request.Request(url, headers={
                "Authorization": "Bearer " + grant["token"]}), timeout=timeout)
        except (OSError, urllib.error.URLError):
            continue
    raise urllib.error.URLError("Managed release feed unavailable")


def session():
    import requests

    class ManagedSession(requests.Session):
        def request(self, method, url, **kwargs):
            try:
                proxy = proxy_for(url)
            except urllib.error.URLError as e:
                raise requests.ConnectionError(str(e.reason)) from None
            if proxy:
                kwargs["proxies"] = {"https": proxy}
            return super().request(method, url, **kwargs)

    return ManagedSession()


def request(method, url, **kwargs):
    with session() as client:
        return client.request(method, url, **kwargs)


def status():
    """Only allowlisted health data; never grant tokens or internal listener ports."""
    grant = read("connectivity.json")
    runtime = read("connect-runtime.json")
    fresh = time.time() - runtime.get("checked", 0) <= 900
    state = grant.get("state", "waiting_for_license")
    if state == "granted":
        state = "agent_unavailable" if grant.get("expires", 0) > time.time() else "expired"
    return {"state": runtime.get("state", "starting") if fresh else state,
            "agent_ready": fresh,
            "ready": bool(fresh and runtime.get("ready")),
            "checked": runtime.get("checked") if fresh else None,
            "services": {key: runtime.get("services", {}).get(key, "waiting") if fresh else "waiting"
                         for key in ("telegram", "github")}}
