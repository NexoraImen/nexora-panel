"""The installer must identify its release before any host mutation."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "install.sh").read_text(encoding="utf-8")
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")


class InstallerVersion(unittest.TestCase):
    def initialize(self, version):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if version is not None:
                (root / "VERSION").write_text(version, encoding="utf-8")
            script = root / "install.sh"
            script.write_text(SOURCE.split("\nclear\n", 1)[0] + '\nprintf "RELEASE=%s\\n" "$VERSION"\n',
                              encoding="utf-8", newline="\n")
            return subprocess.run([BASH, script.as_posix()], cwd=ROOT,
                                  capture_output=True, text=True, timeout=10)

    def test_source_release_instead_of_working_directory(self):
        for version in ("2.3.8\n", "3.7.19\n", "3.0.0-rc.1\n"):
            with self.subTest(version=version):
                result = self.initialize(version)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("RELEASE=" + version.strip(), result.stdout)

    def test_missing_empty_or_malformed_release_stops(self):
        for version in (None, "", "garbage", "2.3.8\n1.2.0", "2.3.8/../../other"):
            with self.subTest(version=version):
                result = self.initialize(version)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("RELEASE=", result.stdout)

    def test_deployment_does_not_overwrite_copied_version(self):
        self.assertNotIn('echo "$VERSION" > "$INSTALL_DIR/VERSION"', SOURCE)
        self.assertNotIn('VERSION="1.2.0"', SOURCE)
        self.assertLess(SOURCE.index('VERSION=$(cat "$SCRIPT_DIR/VERSION")'),
                        SOURCE.index("apt-get update"))


if __name__ == "__main__":
    unittest.main()
