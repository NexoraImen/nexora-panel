"""A lazy-loaded edition can start alphabetically with a tiny feature stub."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = (ROOT / "nexora-cli.sh").read_text(encoding="utf-8")
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
VERIFY = CLI[CLI.index("verify_build() {"):CLI.index("snapshot_to() {")]


class SplitBuild(unittest.TestCase):
    def verify(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dist/assets").mkdir(parents=True)
            for name, size in files.items():
                (root / "dist" / name).write_bytes(b"x" * size)
            result = subprocess.run([BASH, "-c", VERIFY +
                                     '\nif verify_build; then echo OK; else echo "BAD:$BUILD_WHY"; fi'],
                                    cwd=root, capture_output=True, text=True, encoding="utf-8",
                                    timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

    def test_split_and_single_builds(self):
        for extra in ({}, {"assets/aff-off.js": 260, "assets/mini-off.js": 250}):
            with self.subTest(extra=extra):
                self.assertEqual(self.verify({"index.html": 2000, "assets/index.js": 24_640,
                                              "assets/app.js": 350_090,
                                              "assets/index.css": 212_780, **extra}), "OK")

    def test_missing_or_incomplete_assets(self):
        full = {"index.html": 2000, "assets/app.js": 350_000, "assets/app.css": 60_000}
        for missing in full:
            with self.subTest(missing=missing):
                self.assertTrue(self.verify({k: v for k, v in full.items() if k != missing}).startswith("BAD:"))
        self.assertTrue(self.verify({**full, "assets/app.js": 250}).startswith("BAD:"))
        self.assertTrue(self.verify({**full, "assets/app.css": 900}).startswith("BAD:"))

    def test_rebuild_uses_shared_validation(self):
        rebuild = CLI[CLI.index("\n  rebuild)"):CLI.index("\n  rollback)")]
        self.assertIn("&& verify_build; then", rebuild)
        self.assertNotIn("JSSIZE", rebuild)

    def test_repair_and_diagnosis_count_the_same_chunks(self):
        expression = "wc -c dist/assets/*.js 2>/dev/null | awk 'END {print $1+0}'"
        for name in ("nexora-cli.sh", "scripts/repair.sh", "scripts/diagnose.sh"):
            with self.subTest(name=name):
                source = (ROOT / name).read_text(encoding="utf-8").replace('"$DIST"/', 'dist/')
                self.assertIn(expression, source)

    def test_panel_update_and_rollback_do_not_restart_customer_vpn(self):
        for start, end in (("\n  update)", "\n  rebuild)"), ("\n  rollback)", "\n  snapshots)")):
            with self.subTest(command=start):
                command = CLI[CLI.index(start):CLI.index(end)]
                self.assertNotRegex(command, r"x-ui restart|systemctl restart x-ui")


if __name__ == "__main__":
    unittest.main()
