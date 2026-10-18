"""Exercise the real preparation shell without installing packages or services."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def shell_path(path):
    value = path.as_posix()
    return "/" + value[0].lower() + value[2:] if os.name == "nt" else value


BASH = shutil.which("bash")
if os.name == "nt":
    BASH = "C:/Program Files/Git/bin/bash.exe"

STUB = r'''#!/bin/bash
set -eu
name=${0##*/}
printf '%s %s\n' "$name" "$*" >> "$TEST_LOG"
case $name in
  uname) [[ $1 == -s ]] && echo Linux || echo x86_64 ;;
  ss) [[ ${CASE:-} != port-busy ]] || echo 'LISTEN 0 128 0.0.0.0:80' ;;
  systemctl) [[ ${1:-} != show ]] || echo not-found ;;
  apt-get)
    if [[ ${1:-} == -s ]]; then
      case ${CASE:-} in
        upgrade) echo 'Inst libexample [1.0] (2.0 Ubuntu)' ;;
        remove) echo 'Remv example [1.0]' ;;
        *) echo 'Inst nginx (1.24 Ubuntu)' ;;
      esac
    elif [[ ${CASE:-} == apt-fail && ${1:-} == -y ]]; then exit 17; fi ;;
  node)
    if [[ ${CASE:-} == checksum || ${CASE:-} == no-checksum ]]; then echo 18
    elif [[ ${CASE:-} == download-success && ! -f $TEST_READY ]]; then echo 18
    elif [[ ${1:-} == -p ]]; then echo 24
    else echo v24.22.0; fi ;;
  npm)
    [[ ${1:-} != --version ]] || { echo 11; exit 0; }
    [[ ${CASE:-} != npm-fail ]] || exit 18
    if [[ ${1:-} == run ]]; then
      [[ ${CASE:-} != build-fail ]] || exit 19
      mkdir -p dist
      echo '<html>test</html>' > dist/index.html
    fi ;;
  python3)
    mkdir "$3" "$3/bin"
    printf '#!/bin/bash\nexit 0\n' > "$3/bin/pip"
    printf '#!/bin/bash\nprintf "connect-prepare %%s\\n" "$*" >> "$TEST_LOG"\nexit 0\n' > "$3/bin/python"
    chmod +x "$3/bin/pip" "$3/bin/python" ;;
  curl)
    while [[ $# -gt 0 ]]; do
      if [[ $1 == -o ]]; then
        if [[ $2 == */sums ]]; then
          [[ ${CASE:-} == no-checksum ]] && : > "$2" || \
            printf '%064d  node-v24.22.0-linux-x64.tar.xz\n' 0 > "$2"
        else echo archive > "$2"; fi
        break
      fi
      shift
    done ;;
  sha256sum) [[ ${CASE:-} == download-success ]] || exit 20 ;;
  tar)
    if [[ ${1:-} == -xJf ]]; then
      mkdir "$4/bin"
      cp "$TEST_BIN/node" "$TEST_BIN/npm" "$4/bin/"
      touch "$TEST_READY"
    else exec /usr/bin/tar "$@"; fi ;;
esac
'''


class Preparation(unittest.TestCase):
    def run_case(self, case="", existing=False, unit=False):
        self.tmp = tempfile.TemporaryDirectory(prefix="nexora-prepare-")
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        src, dest, units, tools = [base / p for p in ("source", "dest", "units", "tools")]
        for folder in (src / "scripts", src / "backend", src / "bot", src / "frontend", units, base / "bin"):
            folder.mkdir(parents=True, exist_ok=True)
        (src / "VERSION").write_text("2.3.8\n")
        (src / "backend/requirements.txt").write_text("fastapi\n")
        (src / "bot/requirements.txt").write_text("requests\n")
        (src / "bot/run.py").write_text("# fixture\n")
        (src / "frontend/package.json").write_text("{}")
        (src / "frontend/package-lock.json").write_text("{}")
        (src / "frontend/.env").write_text("SECRET=must-not-copy")
        (src / "data").mkdir()
        (src / "data/customer.db").write_text("must-not-copy")
        if existing:
            dest.mkdir()
            (dest / "customer.db").write_text("preserve")
        if unit:
            (units / "nexora-bot.service").write_text("preserve")
        script = (ROOT / "scripts/install-prepare.sh").read_text(encoding="utf-8")
        for key, value in (("DEST", dest), ("UNITS", units), ("TOOLS", tools)):
            script = script.replace(f"{key}=" + {
                "DEST": "/opt/nexora-panel", "UNITS": "/etc/systemd/system",
                "TOOLS": "/opt/nexora-toolchain"}[key], f'{key}="{shell_path(value)}"')
        script = script.replace('[[ $EUID == 0 ]]', '[[ 0 == 0 ]]')
        # Hosted CI images may ship nginx; this fixture models a fresh host.
        script = script.replace('SOURCE=$(cd', '''command() {
  if [[ ${1:-} == -v && ${2:-} == nginx ]]; then return 1; fi
  builtin command "$@"
}
SOURCE=$(cd''', 1)
        if os.name == "nt":
            # NTFS cannot model Unix modes; retain file operations, omit chmod.
            script = script.replace("mkdir -m 755", "mkdir").replace("mkdir -m 700", "mkdir")
            script = script.replace("chmod -R a+rX dist", ":")
            script = script.replace('chmod a+rx "$DEST/frontend"', ":")
            script = script.replace('chmod 644 "$DEST/nginx-prepared.conf"', ":")
            script = script.replace("install -m 600", "cp")
        target = src / "scripts/install-prepare.sh"
        target.write_text(script, encoding="utf-8", newline="\n")
        subprocess.run(["git", "init", "-q", str(src)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(src), "add", "VERSION", "backend", "bot",
                        "frontend/package.json", "frontend/package-lock.json", "scripts"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(src), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                       check=True, capture_output=True)
        if case == "dirty":
            (src / "VERSION").write_text("unreviewed\n")
        for name in ("uname", "ss", "systemctl", "apt-get", "node", "npm", "python3", "curl", "sha256sum", "tar"):
            stub = base / "bin" / name
            stub.write_text(STUB, encoding="utf-8", newline="\n")
            stub.chmod(0o755)
        env = dict(os.environ, CASE=case, TEST_LOG=shell_path(base / "calls"),
                   TEST_READY=shell_path(base / "ready"), TEST_BIN=shell_path(base / "bin"))
        # Set PATH inside bash: Windows subprocess PATH uses different separators.
        command = 'export PATH="$1:$PATH"; exec bash "$2"'
        if os.name == "nt":
            command = 'export PATH="$(cygpath -u "$1"):$PATH"; exec bash "$2"'
        result = subprocess.run([BASH, "-c", command, "test", (base / "bin").as_posix(),
                                 target.as_posix()], env=env, capture_output=True, text=True,
                                timeout=30)
        calls = (base / "calls").read_text() if (base / "calls").exists() else ""
        return result, calls, dest, units

    def test_success_prepares_without_activation(self):
        result, calls, dest, units = self.run_case()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + calls)
        self.assertIn("PREPARATION COMPLETE", result.stdout)
        self.assertTrue((dest / "frontend/dist/index.html").exists())
        if os.name != "nt":
            self.assertEqual((dest / "frontend").stat().st_mode & 0o005, 0o005)
            self.assertEqual((dest / "frontend/dist").stat().st_mode & 0o005, 0o005)
            self.assertEqual((dest / "frontend/dist/index.html").stat().st_mode & 0o004, 0o004)
        self.assertEqual((dest / "VERSION").read_text(), "2.3.8\n")
        self.assertFalse((dest / "data/customer.db").exists())
        self.assertFalse((dest / "data/activation-approved").exists())
        self.assertEqual((dest / "frontend/.env").read_text(), "VITE_API_URL=\n")
        self.assertIn("listen 127.0.0.1:18080", (dest / "nginx-prepared.conf").read_text())
        service = (units / "nexora-panel.service").read_text()
        self.assertIn("ConditionPathExists=", service)
        self.assertIn("/data/auth.json", service)
        self.assertNotRegex(calls, r"systemctl (start|restart|reload|enable)\b")
        self.assertNotIn("x-ui", calls)
        self.assertIn("npm ci", calls)
        self.assertTrue((units / "nexora-bot.service").exists())

    def test_isolated_node_download(self):
        result, calls, dest, units = self.run_case("download-success")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + calls)
        self.assertIn("sha256sum -c check", calls)
        self.assertIn("tar -xJf", calls)
        self.assertTrue((dest.parent / "tools/bin/node").exists())
        self.assertTrue((units / "nexora-panel.service").exists())

    def test_existing_destination_is_preserved(self):
        result, calls, dest, _ = self.run_case(existing=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((dest / "customer.db").read_text(), "preserve")
        self.assertNotIn("apt-get", calls)

    def test_existing_unit_is_preserved(self):
        result, calls, _, units = self.run_case(unit=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((units / "nexora-bot.service").read_text(), "preserve")
        self.assertNotIn("apt-get", calls)

    def test_package_mutations_are_refused(self):
        for case in ("upgrade", "remove"):
            with self.subTest(case=case):
                result, calls, dest, _ = self.run_case(case)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("apt-get -y", calls)
                self.assertFalse(dest.exists())

    def test_occupied_http_port_is_refused(self):
        result, calls, dest, _ = self.run_case("port-busy")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Port 80 is occupied", result.stderr)
        self.assertNotIn("apt-get", calls)
        self.assertFalse(dest.exists())

    def test_dirty_source_is_refused(self):
        result, calls, dest, _ = self.run_case("dirty")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Source has tracked edits", result.stderr)
        self.assertNotIn("apt-get", calls)
        self.assertFalse(dest.exists())

    def test_failures_do_not_publish_services(self):
        for case in ("apt-fail", "npm-fail", "build-fail", "checksum", "no-checksum"):
            with self.subTest(case=case):
                result, calls, _, units = self.run_case(case)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("PREPARATION COMPLETE", result.stdout)
                self.assertFalse((units / "nexora-panel.service").exists())
                self.assertNotIn("systemctl daemon-reload", calls)
                expected = {"apt-fail": "apt-get -y", "npm-fail": "npm ci",
                            "build-fail": "npm run build", "checksum": "sha256sum -c"}
                if case in expected:
                    self.assertIn(expected[case], calls)
                else:
                    self.assertIn("checksum entry missing", result.stderr)

    def test_entrypoint_does_not_fall_through(self):
        result = subprocess.run([BASH, str(ROOT / "install.sh"), "--invalid"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
