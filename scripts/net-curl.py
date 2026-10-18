#!/usr/bin/env python3
"""Run curl with selective managed routing; credentials never enter argv."""
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import connectivity as N


def main(args):
    urls = [arg for arg in args if arg.startswith(("https://", "http://"))]
    env = os.environ.copy()
    if len(urls) == 1:
        try:
            proxy = N.proxy_for(urls[0])
        except Exception:
            print("Managed connection is not ready; check connectivity in the panel.", file=sys.stderr)
            return 1
        if proxy:
            if urls[0] == N.OFFICIAL_RELEASE:
                try:
                    with N.release_feed() as response:
                        sys.stdout.buffer.write(response.read())
                    return 0
                except Exception:
                    print("Managed release feed unavailable.", file=sys.stderr)
                    return 1
            env["https_proxy"] = env["HTTPS_PROXY"] = proxy
            env["no_proxy"] = env["NO_PROXY"] = ""
    return subprocess.run(["curl", *args], env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
