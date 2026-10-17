"""Backup transport repairs reach old installs without touching other sites."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nginx_fix', ROOT / 'scripts/fix-nginx-cache.py')
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)
OLD = '''server {
    location / { try_files $uri /index.html; }
    location /api/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_read_timeout 60s;
    }
}
'''


class RestoreNginx(unittest.TestCase):
    def test_each_api_location_is_repaired_once(self):
        fixed, count = N.add_restore_transport(OLD * 2)
        self.assertEqual(count, 2)
        self.assertEqual(fixed.count('client_max_body_size 256m;'), 2)
        self.assertEqual(fixed.count('proxy_read_timeout 300s;'), 2)
        self.assertEqual(fixed.count('proxy_buffering off;'), 2)
        self.assertNotIn('60s', fixed)
        self.assertEqual(N.add_restore_transport(fixed), (fixed, 0))

    def test_non_panel_locations_are_unchanged(self):
        other = 'server { location /other/ { proxy_pass http://other; } }'
        self.assertEqual(N.add_restore_transport(other), (other, 0))

    def test_nearby_healthy_location_does_not_hide_missing_proto(self):
        healthy = OLD.replace('proxy_read_timeout 60s;',
                              'proxy_set_header X-Forwarded-Proto $scheme;')
        result, count = N.add_proto(healthy + OLD)
        self.assertEqual(count, 1)
        self.assertEqual(result.count('proxy_set_header X-Forwarded-Proto'), 2)

    def test_installer_and_preparation_match_upgrade_policy(self):
        for name, count in [('install.sh', 3), ('scripts/install-prepare.sh', 1)]:
            source = (ROOT / name).read_text(encoding='utf-8')
            self.assertEqual(source.count('client_max_body_size 256m;'), count)
            self.assertEqual(source.count('proxy_buffering off;'), count)
            self.assertEqual(source.count('proxy_read_timeout 300s;'), count)

    def run_main(self, responses):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'panel.conf'
            config.write_text(OLD, encoding='utf-8')
            with patch.object(N.sys, 'argv', ['fix', str(config)]), \
                    patch.object(N.subprocess, 'run', side_effect=responses):
                result = N.main()
            return result, config.read_text(encoding='utf-8')

    def test_invalid_config_is_rolled_back(self):
        result, text = self.run_main([types.SimpleNamespace(returncode=1, stderr=b'invalid')])
        self.assertEqual(result, 1)
        self.assertEqual(text, OLD)

    def test_reload_failure_is_not_reported_as_success(self):
        result, text = self.run_main([types.SimpleNamespace(returncode=0),
                                     types.SimpleNamespace(returncode=1)])
        self.assertEqual(result, 1)
        self.assertEqual(text, OLD)

    def test_validation_timeout_restores_configuration(self):
        result, text = self.run_main([subprocess.TimeoutExpired('nginx', 20)])
        self.assertEqual(result, 1)
        self.assertEqual(text, OLD)

    def test_success_retains_transport_policy(self):
        result, text = self.run_main([types.SimpleNamespace(returncode=0),
                                     types.SimpleNamespace(returncode=0)])
        self.assertEqual(result, 0)
        self.assertIn('client_max_body_size 256m;', text)


if __name__ == '__main__':
    unittest.main()
