"""
Every API route declared in the source, read statically: the `@app.<method>`
decorators in backend/app.py and backend/pro/*.py, and the `ROUTES` tables
of backend/pro/*.py.

tests/test-seams.py and scripts/check-api-contract.py both read routes through
this one function. Two readers drift, and a Pro route one of them could not
see was reported as a panel call to nowhere
(docs/specs/2026-09-29-pro-split.md).
"""
import re
from pathlib import Path

_CORE = re.compile(r'@app\.(get|post|put|delete|patch)\(\s*"([^"]+)"')
_PRO = re.compile(r'\(\s*"(GET|POST|PUT|DELETE|PATCH)",\s*"(/api[^"]+)"')


def route_decls(root):
    """[(method, path, file)] for every declared route; method is lower case."""
    root = Path(root)
    app = root / "backend" / "app.py"
    out = [(m.group(1), m.group(2), "backend/app.py")
           for m in _CORE.finditer(app.read_text(encoding="utf-8"))]
    pro = root / "backend" / "pro"
    for f in sorted(pro.glob("*.py")) if pro.is_dir() else []:
        text = f.read_text(encoding="utf-8")
        out += [(m.group(1).lower(), m.group(2), f"backend/pro/{f.name}")
                for m in _PRO.finditer(text)]
        # Files moved verbatim from app.py (NAMESPACE in backend/pro/__init__.py)
        # keep their @app decorators.
        out += [(m.group(1), m.group(2), f"backend/pro/{f.name}")
                for m in _CORE.finditer(text)]
    return out
