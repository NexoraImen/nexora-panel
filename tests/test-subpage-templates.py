#!/usr/bin/env python3
"""
Subscription-page templates without a license: only classic.

Spec: docs/specs/2026-09-29-pro-split.md ("Templates"). The licensed half is
tests/pro/test-subpage-templates-pro.py, which runs this file as its prelude.

Run:  python3 tests/test-subpage-templates.py
"""
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="tpl_")
os.environ.update(
    NEXORA_LICENSE_DIR=os.path.join(TMP, "license"),
    BOT_DB_PATH=os.path.join(TMP, "bot.db"),
    BILLING_DB_PATH=os.path.join(TMP, "billing.db"), NEXORA_ADMIN_PASSWORD="testpw",
    CONFIG_PATH=os.path.join(TMP, "config.json"), NEXORA_CONFIG=os.path.join(TMP, "config.json"),
    ADMIN_PATH_FILE=os.path.join(TMP, "admin_path.json"))
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "bot"), str(ROOT / "backend")]

G, R, D, X = "\033[38;5;42m", "\033[38;5;203m", "\033[38;5;245m", "\033[0m"
_ok = _fail = 0


def check(name, cond, detail=""):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  {G}✓{X} {name}" + (f" {D}— {detail}{X}" if detail else ""))
    else:
        _fail += 1
        print(f"  {R}✗{X} {name}" + (f" {D}— {detail}{X}" if detail else ""))


def head(t):
    print(f"\n{D}── {t} ──{X}")


import app as AP                                           # noqa: E402

PW = AP._INTERNAL_PW
AP.LIC.remove()


def status_of(fn):
    try:
        fn()
        return 200, {}
    except Exception as e:                                  # noqa: BLE001
        return getattr(e, "status_code", 500), getattr(e, "headers", None) or {}


head("Without a license: classic only")
cfg = AP.load_config()
th = AP.resolve_theme(cfg, "wallet", None)
check("a saved Pro template renders as classic, with no template CSS",
      th["template"] == "classic" and "css" not in th, th.get("template"))
code, hdr = status_of(lambda: AP.pick_theme({"template": "wallet"}, x_admin_password=PW))
check("picking a Pro template: 403 naming the feature",
      code == 403 and hdr.get("X-Nexora-Pro") == "subpage_templates", code)
check("picking classic still works",
      status_of(lambda: AP.pick_theme({"template": "classic"}, x_admin_password=PW))[0] == 200)
lt = AP.list_themes(x_admin_password=PW)
check("the picker is told they are locked, and why",
      lt["templatesLocked"] is True and "Pro" in lt["templatesWhy"], lt["templatesWhy"][:60])

head("The free page carries only classic")
PAGE = (ROOT / "sub-page-index.html").read_text(encoding="utf-8")
check("no Pro template CSS in the free page",
      all(f"body.tpl-{t}" not in PAGE for t in ("wallet", "console", "analytics")))
check("… and it injects whatever CSS the theme brings",
      "theme.css ||" in PAGE and "nx-tpl-css" in PAGE)

if __name__ == "__main__":
    print(f"\n{_ok} passed, {_fail} failed")
    sys.exit(1 if _fail else 0)
