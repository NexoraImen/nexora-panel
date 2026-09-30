#!/usr/bin/env python3
"""
Tests point the databases at their own temp dir, by the names the code reads.

The code reads BOT_DB_PATH and BILLING_DB_PATH. Twelve tests set BOT_DB and
BILLING_DB instead, so the setting did nothing and every run of them shared one
database outside the repo (../data): a test could lean on another run's rows,
and one left tenants behind that the next run tripped over
(docs/specs/2026-09-30-vpn-fixes.md, task 10).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAD = re.compile(r'"(BILLING_DB|BOT_DB)"|\b(BILLING_DB|BOT_DB)=(?=os\.path)')
hits = []
for p in sorted((ROOT / "tests").rglob("*.py")):
    if "__pycache__" in p.parts or p.name == Path(__file__).name:
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if BAD.search(line):
            hits.append(f"{p.relative_to(ROOT)}:{i}")
code = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
names_real = '"BOT_DB_PATH"' in code and '"BILLING_DB_PATH"' in code
ok = not hits and names_real
print(("  \u2713 " if ok else "  \u2717 ")
      + "tests set the database env names the code reads (*_PATH)"
      + ("" if ok else f" \u2014 {hits[:6]} real={names_real}"))
print(f"\n  {1 if ok else 0} passed, {0 if ok else 1} failed")
sys.exit(0 if ok else 1)
