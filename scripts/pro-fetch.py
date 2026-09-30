#!/usr/bin/env python3
"""
Download, verify and install the Pro package for this panel version.

Spec: docs/specs/2026-09-29-issuer.md ("Phase 3b: delivering the Pro bundle").

Part of the free core. It asks the owner's license server for the Pro code of
this server's license and version, checks the signed manifest with the public
key in backend/license.py BEFORE anything is unpacked (the bundle is code the
panel will run), unpacks only the three Pro folders, and swaps them in. A
failure at any step leaves the current code as it was and says why.

Output is English: it runs in a Linux terminal (CLAUDE.md).

    python3 scripts/pro-fetch.py [--root /opt/nexora-panel] [--if-licensed]

Exit codes: 0 installed (or, with --if-licensed, nothing to do), 1 failed,
2 no usable license.
"""
import argparse
import base64
import importlib.util
import io
import shutil
import sys
import tarfile
from pathlib import Path

#: The only folders a Pro package may carry. The issuer packs the same list
#: (issuer/bundle.py PRO_DIRS); tests/pro/test-bundle.py checks they agree.
PRO_DIRS = ("backend/pro", "bot/pro", "frontend/src/pro")

NO_FETCH_STATES = ("none", "invalid", "wrong_machine")


def load_license(root):
    spec = importlib.util.spec_from_file_location("license", root / "backend" / "license.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["license"] = mod
    spec.loader.exec_module(mod)
    return mod


def unit_urls(unit="/etc/systemd/system/nexora-panel.service"):
    """NEXORA_LICENSE_URLS as the panel's systemd unit sets it. `nexora update`
    runs in a root shell, not in the service's environment, so an owner who set
    the hostnames only in the unit would otherwise be told none are set."""
    try:
        text = Path(unit).read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip().strip('"')
        if line.startswith("Environment="):
            kv = line[len("Environment="):].strip('"')
            if kv.startswith("NEXORA_LICENSE_URLS="):
                val = kv.split("=", 1)[1]
                return [u.strip().rstrip("/") for u in val.split(",") if u.strip()]
    return []


def members(blob):
    """{path: bytes} of the bundle. Refuses links, absolute paths, `..` and
    anything outside PRO_DIRS: a signed bundle should never contain them, and
    if one does, nothing is written."""
    out = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for m in tar.getmembers():
            name = m.name
            if not m.isfile():
                raise ValueError(f"not a plain file: {name}")
            parts = Path(name).parts
            if name.startswith(("/", "\\")) or ".." in parts or ":" in name:
                raise ValueError(f"unsafe path: {name}")
            if not any(name.startswith(d + "/") for d in PRO_DIRS):
                raise ValueError(f"outside the Pro folders: {name}")
            out[name] = tar.extractfile(m).read()
    if not out:
        raise ValueError("the package is empty")
    return out


def install(root, files):
    """Write into a staging folder, then swap each Pro folder in. The previous
    Pro code is kept aside until every folder is in place, and put back if a
    swap fails half-way."""
    stage = root / ".pro-staging"
    prev = root / ".pro-prev"
    for d in (stage, prev):
        if d.exists():
            shutil.rmtree(d)
    for name, data in files.items():
        dest = stage / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    moved = []
    try:
        for d in PRO_DIRS:
            live, new = root / d, stage / d
            if live.exists():
                aside = prev / d
                aside.parent.mkdir(parents=True, exist_ok=True)
                live.replace(aside)
                moved.append((live, aside))
            if new.exists():
                live.parent.mkdir(parents=True, exist_ok=True)
                new.replace(live)
    except Exception:
        for live, aside in moved:                       # put the old Pro code back
            if live.exists():
                shutil.rmtree(live)
            aside.replace(live)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(prev, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="Install the Nexora Pro package for this license")
    p.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    p.add_argument("--if-licensed", action="store_true",
                   help="exit 0 quietly when this server has no usable license")
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    lic = load_license(root)
    st = lic.status()
    if not st.get("license_id") or st["state"] in NO_FETCH_STATES:
        msg = f"No usable Pro license on this server (state: {st['state']})."
        if a.if_licensed:
            print(f"  i {msg} Skipping the Pro package.")
            return 0
        print(f"  x {msg} Activate a license on the System page first.")
        return 2
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    print(f"  i Fetching the Pro package for {version} (license {st['license_id']})...")
    urls = lic.license_urls() or unit_urls()
    resp, err = lic.issuer_post("/v1/pro/bundle", {
        "license_id": st["license_id"], "machine": lic.fingerprint(), "version": version},
        urls=urls, timeout=60)
    if err:
        # The issuer's own reason is Persian; it is shown as is after the English line.
        print("  x The license server did not give the Pro package.")
        print(f"    {err}")
        return 1
    try:
        blob = base64.b64decode(resp["bundle"], validate=True)
        manifest = resp["manifest"]
    except (KeyError, TypeError, ValueError):
        print("  x The license server's answer was malformed; nothing was installed.")
        return 1
    pl, why = lic.verify_bundle(manifest, blob, st["license_id"], version)
    if pl is None:
        print(f"  x The Pro package failed verification ({why}); nothing was installed.")
        if why == "unknown_key":
            print("    This panel does not know the signing key yet: update the panel first.")
        return 1
    try:
        files = members(blob)
        install(root, files)
    except Exception as e:                              # noqa: BLE001
        print(f"  x Installing the Pro package failed: {type(e).__name__}: {e}")
        print("    The previous code was left as it was.")
        return 1
    print(f"  + Pro package installed: {len(files)} files for {version}.")
    print("    Rebuild the panel and restart the services to load it (nexora pro does both).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
