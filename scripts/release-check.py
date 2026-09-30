#!/usr/bin/env python3
"""
Release gate — checks everything before a tag.

Why it exists: the release checklist used to live in people's memory — run
the tests, bump the version, write the CHANGELOG, then tag. Memory slips, and
the result is a release with half of it missing. This is the same checklist,
executable: anything missing gives a non-zero exit.

    python3 scripts/release-check.py              # full, before tagging
    python3 scripts/release-check.py --tag v2.0.0 # version consistency only (CI)
    python3 scripts/release-check.py --fast       # no build, no slow suites

The test suites themselves are discovered by tests/run.py — the same runner CI
uses — so the gate and CI cannot run different lists.
"""
import argparse
import importlib.util
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
G, R, Y, D, X = ("\033[38;5;42m", "\033[38;5;203m", "\033[38;5;221m",
                 "\033[38;5;245m", "\033[0m")
_fail = []


def rd(*p):
    return io.open(os.path.join(ROOT, *p), encoding="utf-8").read()


def ok(name, detail=""):
    print(f"  {G}✓{X} {name}" + (f" {D}— {detail}{X}" if detail else ""))


def bad(name, detail=""):
    _fail.append(name)
    print(f"  {R}✗{X} {name}" + (f" {D}— {detail}{X}" if detail else ""))


def check(name, cond, detail=""):
    (ok if cond else bad)(name, detail)
    return cond


def head(t):
    print(f"\n{D}── {t} ──{X}")


def run(cmd, cwd=None):
    """Keeps the output so it is printed only on failure."""
    try:
        p = subprocess.run(cmd, cwd=cwd or ROOT, shell=isinstance(cmd, str),
                           capture_output=True, text=True, timeout=600,
                           encoding="utf-8", errors="replace")
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except FileNotFoundError as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════
def version_checks(tag):
    head("Version")

    ver = rd("VERSION").strip()
    check("VERSION is readable", re.fullmatch(r"\d+\.\d+\.\d+", ver), ver)

    pkg = json.loads(rd("frontend", "package.json")).get("version", "")
    check("package.json matches VERSION", pkg == ver,
          f"VERSION={ver} · package.json={pkg}")

    changelog = rd("CHANGELOG.md")
    check(f"CHANGELOG has a section for {ver}", f"[{ver}]" in changelog,
          f"no '## [{ver}]' heading" if f"[{ver}]" not in changelog else "")

    # a heading alone is not a changelog entry
    m = re.search(r"##\s*\[" + re.escape(ver) + r"\](.*?)(?=\n##\s*\[|\Z)",
                  changelog, re.S)
    body = (m.group(1).strip() if m else "")
    check("CHANGELOG section is not empty", len(body) > 80, f"{len(body)} chars")

    if tag:
        want = tag.lstrip("v")
        check(f"tag {tag} matches VERSION", want == ver, f"tag={want} · VERSION={ver}")
    else:
        # Without this the gate says "ready to release 1.3.0" when 1.3.0 is
        # already published and tagging it again fails.
        okt, out = run(["git", "tag", "--list", f"v{ver}"])
        check(f"{ver} is not tagged yet", not (okt and out.strip()),
              f"v{ver} exists — bump VERSION first" if okt and out.strip() else "")
    return ver


def git_checks():
    head("Repository")

    okc, out = run(["git", "status", "--porcelain"])
    if not okc:
        bad("git is available", out.strip()[:60])
        return
    dirty = [l for l in out.splitlines() if l.strip()]
    check("nothing uncommitted", not dirty, f"{len(dirty)} changed files" if dirty else "")
    for l in dirty[:8]:
        print(f"      {Y}▸{X} {l.strip()}")

    okb, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    check("on branch main", okb and branch.strip() == "main", branch.strip())


def _runner():
    spec = importlib.util.spec_from_file_location("nexora_test_runner",
                                                  os.path.join(ROOT, "tests", "run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_checks(fast):
    head("Tests: bot and backend")
    rc = _runner().main(["bot", "backend"] + (["--fast"] if fast else []))
    check("bot and backend suites", rc == 0)


def frontend_checks(fast):
    head("Frontend")

    if not os.path.isdir(os.path.join(ROOT, "frontend", "node_modules")):
        bad("node_modules installed", "run npm install in frontend/ first")
        return

    if not fast:
        okb, out = run("npm run build", cwd=os.path.join(ROOT, "frontend"))
        check("panel builds", okb, "" if okb else out.strip().splitlines()[-1][:70])
        if not okb:
            return

    rc = _runner().main(["frontend"] + (["--fast"] if fast else []))
    check("frontend suites", rc == 0)


# ═══════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", help="the tag about to be created, e.g. v2.0.0")
    ap.add_argument("--fast", action="store_true", help="no build, no slow suites")
    args = ap.parse_args()

    print(f"\n{D}{'═' * 54}{X}")
    print("  Nexora release gate")
    print(f"{D}{'═' * 54}{X}")

    ver = version_checks(args.tag)

    # In CI the tree is always clean and the suites ran in their own jobs;
    # only version consistency matters there.
    if not args.tag:
        git_checks()
        test_checks(args.fast)
        frontend_checks(args.fast)

    print(f"\n{D}{'─' * 54}{X}")
    if _fail:
        print(f"  {R}Do not release — {len(_fail)} item(s) left:{X}")
        for f in _fail:
            print(f"    {R}▸{X} {f}")
        print()
        return 1

    print(f"  {G}Ready to release {ver}{X}")
    if not args.tag:
        print(f"  {D}git tag -a v{ver} -m \"Nexora {ver}\"{X}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
