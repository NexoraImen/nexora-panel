#!/usr/bin/env python3
"""
Repair the panel's nginx config. Three fixes, all idempotent.

1. Cache-control headers.
   index.html points to hashed asset files. If the browser caches
   index.html itself, it keeps asking for the old bundle after every
   update — a bundle that no longer exists or no longer matches the new
   code. The result is a blank page or "useState is not defined".

2. The X-Forwarded-Proto header.
   TLS terminates at nginx, so without this header the request reaches
   uvicorn looking like plain http. The backend then believes the panel
   is not on https and never records the mini-app address — so the
   mini-app button never appears in any bot, the owner's or a
   reseller's, and nothing says why.

   install.sh has had this since the fix, but installs created before it
   still carry the old file and update never rewrote it. This script
   runs on every update, so the repair reaches them.

3. Compression for JS/CSS.
   Stock nginx compresses only text/html. The panel and the mini-app ship
   ~700 KB of JS/CSS that compresses to ~200 KB. On the flaky Iranian
   mobile links the owner and resellers use, the uncompressed download
   stalled mid-way and the mini-app sat on its splash screen.

Usage:
    python3 scripts/fix-nginx-cache.py [path to conf]
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT = "/etc/nginx/conf.d/nexora-panel.conf"

BLOCK = """
    # index.html must never be cached
    location = /index.html {
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        expires -1;
    }
    # Asset files are content-hashed, so they can be cached forever
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
"""


PROTO = "proxy_set_header X-Forwarded-Proto $scheme;"

GZIP = """
    # Compress JS/CSS/JSON (stock nginx only compresses text/html)
    gzip on;
    gzip_vary on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types text/css application/javascript application/json image/svg+xml;
"""


def add_proto(text):
    """
    Put the proto header next to every proxy_pass that lacks it.

    Anchored on `proxy_set_header Host`, which every block that proxies
    already has — matching `proxy_pass` itself would also hit blocks
    that set no headers at all, where the indentation is unknown.

    Returns (new text, how many blocks were fixed).
    """
    out, fixed, pos = [], 0, 0
    for m in re.finditer(r"([ \t]*)proxy_set_header\s+Host\b[^\n]*\n", text):
        # آیا همین بلوک از قبل هدر را دارد؟ پنجره‌ی کوچک دور خودش،
        # نه کلِ فایل — یک بلوکِ درست نباید بقیه را هم درست جلوه دهد.
        # A nearby healthy location must not hide this location's missing header.
        start = text.rfind("{", 0, m.start())
        end = text.find("}", m.end())
        around = text[start:end if end >= 0 else len(text)]
        if re.search(r"(?m)^\s*proxy_set_header\s+X-Forwarded-Proto\b", around):
            continue
        out.append(text[pos:m.end()])
        out.append(f"{m.group(1)}{PROTO}\n")
        pos = m.end()
        fixed += 1
    out.append(text[pos:])
    return "".join(out), fixed


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)

    if not path.exists():
        print(f"!  Config not found: {path}")
        return 1

    text = path.read_text(encoding="utf-8")
    original = text

    need_cache = "no-store, no-cache" not in text
    need_gzip = "gzip_types" not in text
    text, n_proto = add_proto(text)
    text, n_transport = add_restore_transport(text)

    if not need_cache and not n_proto and not need_gzip and not n_transport:
        print("OK Cache headers, X-Forwarded-Proto and compression already configured")
        return 0

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)

    n = 0
    if need_cache:
        # Insert before each "location / {" (both http and https blocks)
        text, n = re.subn(r"(\n\s*location / \{)", BLOCK + r"\1", text)
        if n == 0 and not n_proto:
            print("!  No 'location /' block found — nothing changed")
            return 1

    n_gzip = 0
    if need_gzip:
        # Same anchor as the cache block: once per server block
        text, n_gzip = re.subn(r"(\n\s*location / \{)", GZIP + r"\1", text)

    if text == original:
        print("OK Nothing to change")
        return 0

    path.write_text(text, encoding="utf-8")

    # خلاصه یک‌بار ساخته می‌شود و در هر دو مسیر چاپ — چه nginx
    # باشد چه نباشد. نسخه‌ی قبلی در نبودِ nginx زودتر برمی‌گشت و
    # هیچ‌وقت نمی‌گفت چه عوض کرده؛ تغییر روی دیسک بود و کاربر
    # بی‌خبر.
    done = []
    if n:
        done.append(f"cache headers in {n} block(s)")
    if n_proto:
        done.append(f"X-Forwarded-Proto in {n_proto} block(s)")
    if n_gzip:
        done.append(f"compression in {n_gzip} block(s)")
    if n_transport:
        done.append(f"backup upload/stream settings in {n_transport} block(s)")
    summary = ", ".join(done) or "nothing"

    # Validate; roll back if broken
    try:
        r = subprocess.run(["nginx", "-t"], capture_output=True, timeout=20)
        if r.returncode != 0:
            shutil.copy2(backup, path)
            print("X  Config was invalid — previous version restored")
            print((r.stderr or b"").decode()[:300])
            return 1
    except FileNotFoundError:
        print(f"!  nginx not available — {summary} applied but not verified")
        return 0
    except (OSError, subprocess.TimeoutExpired):
        shutil.copy2(backup, path)
        print("X  nginx validation failed; previous configuration restored")
        return 1

    try:
        reload = subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, timeout=20)
        if reload.returncode:
            raise RuntimeError("nginx reload failed")
    except (OSError, subprocess.TimeoutExpired, RuntimeError):
        shutil.copy2(backup, path)
        print("X  nginx reload failed; previous configuration restored on disk")
        return 1
    print(f"OK {summary}, nginx reloaded")
    if n_proto:
        print("   The panel can now tell it is on https, so the mini-app")
        print("   address gets recorded the next time you open it.")
    return 0


def add_restore_transport(text):
    """Scope larger uploads to the panel API, leaving other sites untouched."""
    changed = 0
    policy = {"client_max_body_size": "256m", "client_body_timeout": "300s",
              "proxy_read_timeout": "300s", "proxy_send_timeout": "300s",
              "proxy_buffering": "off"}

    def patch(match):
        nonlocal changed
        body = match.group(2)
        original = body
        for key, value in policy.items():
            pattern = rf"(?m)^([ \t]*){key}\s+[^;\n]+;"
            if re.search(pattern, body):
                body = re.sub(pattern, lambda m: f"{m[1]}{key} {value};", body)
            else:
                body += f"\n        {key} {value};\n"
        changed += body != original
        return match.group(1) + body + "}"

    return re.sub(r"(location\s+/api/\s*\{)([^{}]*)\}", patch, text), changed


if __name__ == "__main__":
    sys.exit(main())
