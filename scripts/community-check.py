#!/usr/bin/env python3
"""
Run the test suite on the Community tree: this repo without its Pro paths.

Spec: docs/specs/2026-09-29-pro-split.md ("Done when" 1).

The public repo (Phase 5) gets exactly this tree. A core file that still
needs Pro code builds and passes here in the private tree and breaks only
there, after release. This copies every tracked file except the Pro paths
into a temporary folder, builds the panel there, and runs tests/run.py.

    python scripts/community-check.py            # all groups
    python scripts/community-check.py backend    # one group

Exit code is the suite's. Output is English (terminal rule).
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: Never in the public repo. The same list the export (Phase 5) drops.
PRIVATE = ("backend/pro/", "bot/pro/", "frontend/src/pro/", "tests/pro/", "issuer/")


def tracked():
    # Tracked and new (not yet committed, not ignored) files: the working tree
    # as it would be committed, so a check before the commit sees the commit.
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def link_dir(src, dst):
    """node_modules is not tracked and is large: link it instead of copying."""
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", dst, src], check=True,
                       stdout=subprocess.DEVNULL)
    else:
        os.symlink(src, dst)


def main(argv):
    tmp = tempfile.mkdtemp(prefix="nexora-community-")
    tree = os.path.join(tmp, "repo")
    files = [p for p in tracked() if not p.startswith(PRIVATE)]
    for rel in files:
        src = os.path.join(ROOT, rel)
        if not os.path.isfile(src):
            continue                                      # deleted but not yet committed
        dst = os.path.join(tree, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    left = [p for p in PRIVATE if os.path.exists(os.path.join(tree, p))]
    if left:
        print(f"FAIL: private paths leaked into the Community tree: {left}")
        return 1
    print(f"Community tree: {len(files)} files in {tree}")

    rc = check_tree(tree, argv)
    if rc == 0:
        unlink_modules(tree)
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"\nCommunity tree kept for inspection: {tree}")
    return rc


def check_tree(tree, argv=()):
    """Build the panel inside `tree` and run every suite there. Shared with
    scripts/export-public.py, so the export is checked by these same steps and
    not by a second copy of them. Leaves the node_modules link in place (a
    failed tree is kept for inspection); unlink_modules() removes it."""
    link_dir(os.path.join(ROOT, "frontend", "node_modules"),
             os.path.join(tree, "frontend", "node_modules"))
    npx = "npx.cmd" if os.name == "nt" else "npx"
    fe = os.path.join(tree, "frontend")
    for env_extra in ({}, {"NEXORA_SINGLE_BUNDLE": "1"}):
        r = subprocess.run([npx, "vite", "build"], cwd=fe, env={**os.environ, **env_extra},
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print("FAIL: the Community panel does not build:\n" + (r.stdout + r.stderr)[-1500:])
            return 1
    subprocess.run(["node", os.path.join("tests", "harness", "make-harness.js")], cwd=tree,
                   capture_output=True)
    print("Community panel built. Running the suites...\n")
    r = subprocess.run([sys.executable, "-u", os.path.join("tests", "run.py"), "--fast", *argv],
                       cwd=tree, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return r.returncode


def unlink_modules(tree):
    """Remove the node_modules link itself, before any rmtree: rmtree must
    never walk into the real frontend/node_modules through it."""
    nm = os.path.join(tree, "frontend", "node_modules")
    if os.path.lexists(nm):
        if os.name == "nt":
            os.rmdir(nm)
        else:
            os.unlink(nm)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
