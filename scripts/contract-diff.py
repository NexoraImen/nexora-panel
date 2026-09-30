#!/usr/bin/env python3
"""
یک مسیر، کنارِ هم: پاسخِ هارنس و پاسخِ واقعیِ بکند — برای اصلاحِ هارنس.

  PYTHONIOENCODING=utf-8 python scripts/contract-diff.py /api/admin/config

از همان فیکسچرِ test-contract استفاده می‌کند. خروجی JSON، انگلیسی.
"""
import json
import os
import subprocess
import sys

sys.argv = [sys.argv[0], "--quiet-import"] + sys.argv[1:]
PATHS = [a for a in sys.argv[2:] if a.startswith("/")]
os.environ["NX_CONTRACT_IMPORT_ONLY"] = "1"
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import importlib.util                                           # noqa: E402
spec = importlib.util.spec_from_file_location("tc", os.path.join(here, "test-contract.py"))
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)

hs = subprocess.run(["node", os.path.join(here, "harness-shapes.cjs"), *PATHS],
                    capture_output=True, text=True, encoding="utf-8")
harn = json.loads(hs.stdout or "{}")
for p in PATHS:
    st, real = tc.call(p)
    print(f"===== {p}  (backend {st})")
    print("--- backend:")
    print(json.dumps(real, ensure_ascii=False, indent=1)[:4000])
    print("--- harness:")
    print(json.dumps(harn.get(p), ensure_ascii=False, indent=1)[:4000])
