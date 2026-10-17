"""Automatic updates work with workflow directories and legacy credentials."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = (ROOT / 'nexora-cli.sh').read_text(encoding='utf-8')
INSTALL = (ROOT / 'install.sh').read_text(encoding='utf-8')
BASH = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash')


class UpdateSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def run_shell(self, source, **env):
        script = self.path / 'test.sh'
        script.write_text(source, encoding='utf-8', newline='\n')
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ('GITHUB_REPO', 'GITHUB_TOKEN', 'BASH_ENV')}
        return subprocess.run([BASH, script.as_posix()], cwd=self.path,
                              env={**clean_env, **env}, capture_output=True,
                              text=True, timeout=15)

    def update(self, **env):
        # A matching release stops before snapshots, downloads or service actions.
        block = CLI.split('  update)\n', 1)[1].split('    TS=$(date', 1)[0]
        prefix = '''INSTALL_DIR="$PWD"
VER=2.3.9
logo(){ :; }
info(){ echo "$1"; }
bad(){ echo "$1"; }
ok(){ echo "$1"; }
curl(){ printf '%s\\n' "$*" >&2; echo '{"tag_name":"v2.3.9"}'; }
'''
        return self.run_shell(prefix + block, **env)

    def test_defaults_with_missing_config_or_workflow_directory(self):
        for directory in (False, True):
            if directory:
                (self.path / '.github').mkdir()
            result = self.update()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('repos/NexoraImen/nexora-panel/releases/latest', result.stderr)
            self.assertIn('Already on the latest', result.stdout)

    def test_legacy_custom_repo_and_token_are_preserved(self):
        (self.path / '.github').write_text('GITHUB_REPO="custom/repo"\nGITHUB_TOKEN="secret"\n')
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('repos/custom/repo/releases/latest', result.stderr)
        self.assertIn('Authorization: token secret', result.stderr)
        self.assertNotIn('secret', result.stdout)

    def test_new_config_takes_precedence(self):
        (self.path / '.github').write_text('GITHUB_REPO="legacy/repo"\n')
        (self.path / '.nexora-update.conf').write_text('GITHUB_REPO="modern/repo"\n')
        result = self.update()
        self.assertIn('repos/modern/repo/releases/latest', result.stderr)
        self.assertNotIn('legacy/repo', result.stderr)

    def test_explicit_environment_works_without_config(self):
        result = self.update(GITHUB_REPO='override/repo')
        self.assertIn('repos/override/repo/releases/latest', result.stderr)

    def test_invalid_config_stops_before_network(self):
        (self.path / '.nexora-update.conf').write_text('GITHUB_REPO=(\n')
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Could not load update settings', result.stdout)
        self.assertNotIn('releases/latest', result.stderr)

    def test_settings_file_is_not_exported_or_committed(self):
        # Community checks intentionally run outside a Git checkout.
        subprocess.run(['git', 'init', '--quiet'], cwd=self.path, check=True,
                       capture_output=True)
        shutil.copy2(ROOT / '.gitignore', self.path / '.gitignore')
        result = subprocess.run(['git', 'check-ignore', '.nexora-update.conf'],
                                cwd=self.path, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def installer(self):
        block = INSTALL.split('# Enable automatic updates from GitHub\n', 1)[1]
        block = block.split('\nif systemctl', 1)[0]
        return self.run_shell('INSTALL_DIR="$PWD"\nok(){ echo "OK:$1"; }\n'
                              'warn(){ echo "WARN:$1"; }\n' + block)

    def test_installer_handles_workflow_directory_and_existing_settings(self):
        (self.path / '.github').mkdir()
        result = self.installer()
        self.assertIn('OK:Auto-update enabled', result.stdout)
        config = self.path / '.nexora-update.conf'
        self.assertIn('NexoraImen/nexora-panel', config.read_text())
        config.write_text('GITHUB_REPO="keep/me"\n')
        self.installer()
        self.assertIn('keep/me', config.read_text())
        self.assertTrue((self.path / '.github').is_dir())

    def test_installer_keeps_legacy_settings(self):
        (self.path / '.github').write_text('GITHUB_REPO="keep/legacy"\n')
        self.installer()
        self.assertFalse((self.path / '.nexora-update.conf').exists())

    def test_installer_reports_write_failure(self):
        # A dangling parent avoids permission-dependent behavior when CI is root.
        block = INSTALL.split('# Enable automatic updates from GitHub\n', 1)[1].split('\nif systemctl', 1)[0]
        result = self.run_shell('INSTALL_DIR="$PWD/missing"\nok(){ echo "OK"; }\n'
                                'warn(){ echo "WARN"; }\n' + block)
        self.assertIn('WARN', result.stdout)
        self.assertNotIn('OK', result.stdout)

    def test_snapshot_preserves_new_config(self):
        (self.path / '.nexora-update.conf').write_text('GITHUB_REPO="keep/snapshot"\n')
        (self.path / 'snapshot/frontend').mkdir(parents=True)
        fn = re.search(r'^snapshot_to\(\) \{.*?^\}', CLI, re.M | re.S).group()
        self.run_shell('INSTALL_DIR="$PWD"\nVER=2.3.9\n' + fn + '\nsnapshot_to "$PWD/snapshot"\n')
        self.assertEqual((self.path / 'snapshot/.nexora-update.conf').read_text(),
                         'GITHUB_REPO="keep/snapshot"\n')

    def test_verification_does_not_print_tokens(self):
        for name in ('.github', '.nexora-update.conf'):
            (self.path / name).write_text('GITHUB_REPO="custom/repo"\nGITHUB_TOKEN="PRIVATE_SECRET"\n')
            source = (ROOT / 'scripts/verify.sh').read_text(encoding='utf-8')
            result = self.run_shell(source, INSTALL_DIR=self.path.as_posix())
            self.assertIn('Update source: custom/repo', result.stdout)
            self.assertNotIn('PRIVATE_SECRET', result.stdout + result.stderr)
            (self.path / name).unlink()

    def test_legacy_template_uses_public_frontend_origin(self):
        (self.path / 'frontend').mkdir()
        (self.path / 'sub-page-index.html').write_text('const SUBPAGE_CONFIG_API = "http://localhost:8100";')
        (self.path / 'frontend/.env').write_text('VITE_API_URL=https://panel.example.test\n')
        block = CLI.split('    API_URL=$(grep', 1)[1].split('    SUBPAGE_PATH=', 1)[0]
        result = self.run_shell('INSTALL_DIR="$PWD"\nAPI_URL=$(grep' + block + '\necho "API=$API_URL"\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('API=https://panel.example.test', result.stdout)

    def test_template_setup_does_not_restart_customer_vpn(self):
        source = (ROOT / 'scripts/setup-template.sh').read_text(encoding='utf-8')
        self.assertNotRegex(source, r'(?:systemctl\s+restart\s+x-ui|x-ui\s+restart)')

    def test_inline_token_is_not_printed_by_diagnostics(self):
        (self.path / '.nexora-update.conf').write_text('GITHUB_REPO="custom/repo"; GITHUB_TOKEN="PRIVATE_SECRET"\n')
        source = (ROOT / 'scripts/verify.sh').read_text(encoding='utf-8')
        result = self.run_shell(source, INSTALL_DIR=self.path.as_posix())
        self.assertIn('Update source: custom/repo', result.stdout)
        self.assertNotIn('PRIVATE_SECRET', result.stdout + result.stderr)

    def test_installed_subscription_template_uses_actual_protocol(self):
        deployed = self.path / 'sub'
        deployed.mkdir()
        block = INSTALL.split('nginx -t > /dev/null 2>&1 || die', 1)[1]
        block = block[block.index('# The subscription page'):].split('\nsystemctl reload nginx', 1)[0]
        for secure, protocol in [('false', 'http'), ('true', 'https')]:
            for file in (self.path / 'sub-page-index.html', deployed / 'index.html'):
                file.write_text('const SUBPAGE_CONFIG_API = "http://localhost:8100";')
            result = self.run_shell('INSTALL_DIR="$PWD"\nSUBPAGE_DIR="$PWD/sub"\n'
                                    'PANEL_DOMAIN=panel.example.test\n' + block, SSL_READY=secure)
            self.assertEqual(result.returncode, 0, result.stderr)
            for file in (self.path / 'sub-page-index.html', deployed / 'index.html'):
                self.assertIn(f'"{protocol}://panel.example.test"', file.read_text())

    def test_updater_keeps_custom_api_but_removes_legacy_panel_origin(self):
        block = CLI.split('    # Legacy installers baked', 1)[1].split('    export NODE_OPTIONS', 1)[0]
        for api in ('https://panel.test', 'https://custom-api.test'):
            result = self.run_shell('# Legacy installers baked' + block,
                                    API_URL='https://panel.test', VITE_URL=api)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = '' if api == 'https://panel.test' else api
            self.assertEqual((self.path / '.env').read_text(), f'VITE_API_URL={expected}\n')


if __name__ == '__main__':
    unittest.main()
