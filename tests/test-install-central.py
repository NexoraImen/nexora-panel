"""Run the installer's central/local branches with host mutations stubbed out."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "install.sh").read_text(encoding="utf-8")
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")


class CentralInstaller(unittest.TestCase):
    def shell(self, source, *args):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "check.sh"
            script.write_text(source, encoding="utf-8", newline="\n")
            return subprocess.run([BASH, script.as_posix(), *args], cwd=ROOT,
                                  capture_output=True, text=True, timeout=10)

    def test_flag_and_default(self):
        parser = SOURCE.split('INSTALL_DIR="', 1)[0]
        for args, expected, code in [((), "false", 0), (("--central",), "true", 0),
                                     (("--central", "--prepare"), "", 2), (("--bad",), "", 2)]:
            with self.subTest(args=args):
                result = self.shell(parser + '\nprintf "%s" "$CENTRAL"\n', *args)
                self.assertEqual(result.returncode, code, result.stderr)
                if not code:
                    self.assertEqual(result.stdout, expected)

    def test_central_skips_local_template_database_and_service_binding(self):
        block = SOURCE.split('# ═══════════════════ STEP 5 — Template ═══════════════════', 1)[1]
        block = block.split('# ═══════════════════ STEP 6 — Service ═══════════════════', 1)[0]
        result = self.shell('''CENTRAL=true
INSTALL_DIR=/opt/nexora-panel
info() { :; }
step() { exit 41; }
mkdir() { exit 42; }
cp() { exit 43; }
python3() { exit 44; }
''' + block + '\nprintf "%s|%s" "$SUBPAGE_HTML" "$XUI_ENV"\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '/opt/nexora-panel/sub-page-index.html|')

    def test_xui_restart_is_local_only(self):
        block = SOURCE.split('if [ "$CENTRAL" = false ] && systemctl is-active --quiet x-ui', 1)[1]
        block = 'if [ "$CENTRAL" = false ] && systemctl is-active --quiet x-ui' + block.split('\nfi', 1)[0] + '\nfi\n'
        for central, expected in [('true', ''), ('false', 'checked\nrestarted\n')]:
            result = self.shell('CENTRAL=' + central + '''
systemctl() { echo checked; }
x-ui() { echo restarted >&3; }
ok() { :; }
exec 3>&1
''' + block)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected)

    def test_central_requires_https_and_agent_access(self):
        guards = [line for line in SOURCE.splitlines() if line.startswith('[ "$CENTRAL" = true ] &&') and '&& die ' in line]
        self.assertEqual(len(guards), 3)
        cases = [('3', '', 'true', False), ('1', '192.0.2.1', 'true', False),
                 ('1', '', 'false', False), ('1', '', 'true', True), ('2', '', 'true', True)]
        for ssl, ip, ready, accepted in cases:
            with self.subTest(ssl=ssl, ip=ip, ready=ready):
                prelude = f'CENTRAL=true\nSSL_CHOICE={ssl}\nALLOW_IP="{ip}"\nSSL_READY={ready}\ndie() {{ echo "$1" >&2; exit 1; }}\n'
                result = self.shell(prelude + '\n'.join(guards) + '\nexit 0\n')
                self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_shell_syntax(self):
        result = subprocess.run([BASH, '-n', str(ROOT / 'install.sh')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
