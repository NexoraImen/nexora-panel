#!/usr/bin/env python3
"""
One test runner for everything: CI and scripts/release-check.py both call it.

Why it exists: CI and the release gate used to keep two hand-written lists of
test files. They drifted — CI never ran five suites (contract, linkcheck,
inbound-doctor, repair-orders, repair-referrals), so a break there was green
on every push and only the local gate could see it. Tests are now *discovered*:
a new file named tests/test-*.py|js|cjs or tests/bot/test_*.py runs everywhere
without being listed anywhere.

    python tests/run.py                 # all groups
    python tests/run.py bot backend     # CI python job
    python tests/run.py frontend        # CI frontend job (needs a built panel)
    python tests/run.py --fast          # skip the slow suites
    python tests/run.py --list          # show what would run
"""
import argparse
import glob
import os
import subprocess
import tempfile
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# A Windows console is cp1252: the first ✓ would kill the runner itself.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")

# Python tests that need the built panel (frontend/dist) run with the frontend.
NEEDS_BUILD = {"tests/test-serve.py"}
# Minutes, not seconds. --fast skips them.
SLOW = {"tests/test-bot-throughput.py"}
# Exit code 0 is not enough for these (see run_group).
TRACEBACK_FAILS = {"bot/preview_texts.py"}
# Checks that are not named test-* but belong to the gate.
EXTRA = {
    "backend": ["scripts/check-api-contract.py", "bot/preview_texts.py"],
}


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def discover():
    j = lambda *p: sorted(rel(f) for f in glob.glob(os.path.join(ROOT, *p)))
    # tests/pro/ holds the Pro areas' tests; it is absent in the public
    # (Community) tree, and glob then simply finds nothing.
    py = j("tests", "test-*.py") + j("tests", "pro", "test-*.py")
    return {
        "bot": j("tests", "bot", "test_*.py") + j("tests", "pro", "test_*.py"),
        "backend": [f for f in py if f not in NEEDS_BUILD] + EXTRA["backend"],
        "frontend": j("tests", "test-*.cjs") + j("tests", "test-*.js")
                    + [f for f in py if f in NEEDS_BUILD],
    }


def command(f):
    return (["node", f] if f.endswith((".js", ".cjs")) else [sys.executable, f])


def tail(p):
    # A traceback wins: when a test dies on an exception, stdout is only what it
    # printed before dying. Otherwise stdout — stderr is mostly the app's own
    # logging, and showing it hid the actual failed check (first CI run of
    # test-contract printed three log lines and not the drift).
    err = (p.stderr or "").strip()
    if "Traceback" in err:
        return err[-1200:]
    out = (p.stdout or "").strip()
    fails = [l for l in out.splitlines() if any(k in l for k in ("✗", "FAIL", "❌", "≠", "invents", "lacks"))]
    return "\n".join(fails[-12:]) if fails else out[-800:]


def run_group(name, files, env):
    print(f"\n{D}── {name} · {len(files)} suites ──{X}")
    broken = []
    for f in files:
        t0 = time.time()
        try:
            p = subprocess.run(command(f), cwd=ROOT, env=env, timeout=900,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            okk = p.returncode == 0
            # Tests log expected exceptions on purpose ("ufw gone"), so a
            # traceback alone is not a failure — except for the text preview,
            # which catches a broken page, prints it and still exits 0.
            if f in TRACEBACK_FAILS and "Traceback" in (p.stdout or "") + (p.stderr or ""):
                okk = False
            detail = "" if okk else tail(p)
        except Exception as e:  # timeout, missing interpreter
            okk, detail = False, f"{type(e).__name__}: {e}"
        mark = f"{G}✓{X}" if okk else f"{R}✗{X}"
        print(f"  {mark} {f} {D}{time.time() - t0:.1f}s{X}")
        if not okk:
            broken.append(f)
            for line in detail.splitlines()[-14:]:
                print(f"      {D}{line}{X}")
    return broken


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run Nexora's test suites.")
    ap.add_argument("groups", nargs="*", help="bot, backend, frontend (default: all)")
    ap.add_argument("--fast", action="store_true", help="skip slow suites")
    ap.add_argument("--list", action="store_true", help="print the suites and exit")
    a = ap.parse_args(argv)

    found = discover()
    unknown = [g for g in a.groups if g not in found]
    if unknown:
        ap.error(f"unknown group: {', '.join(unknown)} (choose from {', '.join(found)})")
    groups = a.groups or list(found)
    plan = {g: [f for f in found[g] if not (a.fast and f in SLOW)] for g in groups}

    if a.list:
        for g, fs in plan.items():
            print(f"{g} ({len(fs)})")
            for f in fs:
                print(f"  {f}")
        return 0

    # NEXORA_LICENSE_DIR: any suite that touches a license route would
    # otherwise write install_id into the repo's data/ (it got committed once).
    env = dict(os.environ, PYTHONIOENCODING="utf-8",
               NODE_PATH=os.path.join(ROOT, "frontend", "node_modules"),
               NEXORA_LICENSE_DIR=tempfile.mkdtemp(prefix="nexora_license_"))
    if "frontend" in plan and not os.path.isdir(os.path.join(ROOT, "frontend", "dist")):
        print(f"{R}frontend/dist is missing{X} — build first: cd frontend && npm run build")
        return 1

    broken = []
    for g, fs in plan.items():
        broken += run_group(g, fs, env)

    total = sum(len(fs) for fs in plan.values())
    print()
    if broken:
        print(f"  {R}{len(broken)} of {total} suites failed:{X}")
        for f in broken:
            print(f"    {R}▸{X} {f}")
        return 1
    print(f"  {G}all {total} suites passed{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
