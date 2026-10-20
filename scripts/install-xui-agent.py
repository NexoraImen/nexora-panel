#!/usr/bin/env python3
"""Install the standalone Iran XUI agent (requires existing Python venv support)."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request
import ssl

HOME = Path('/opt/nexora-xui-agent')
UNIT = Path('/etc/systemd/system/nexora-xui-agent.service')
KNOWN_DATABASES = ('/etc/x-ui/x-ui.db', '/usr/local/x-ui/x-ui.db', '/usr/local/x-ui/bin/x-ui.db')


def panel_url(value, *, allow_test_http=False):
    p = urlsplit(value)
    if (not p.hostname or p.username is not None or p.password is not None or p.query or p.fragment
            or (p.scheme != 'https' and not (allow_test_http and p.scheme == 'http'
                and p.hostname in ('localhost', '127.0.0.1', '::1')))
            or not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)*/?', p.path)):
        raise ValueError('Central panel requires a valid HTTPS base URL')
    p.port
    return value.rstrip('/')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(panel, endpoint, data=None):
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    request = Request(panel + '/api/xui-agent/' + endpoint, data=data,
                      headers={'Content-Type': 'application/json'} if data is not None else {})
    with opener.open(request, timeout=45) as response:
        body = response.read(4 * 1024 * 1024 + 1)
        if len(body) > 4 * 1024 * 1024:
            raise ValueError('Central response exceeds limit')
        return body


def private_write(path, data):
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def enroll(panel, code):
    code = code or os.environ.get('NEXORA_XUI_ENROLL_CODE') or getpass.getpass('One-time enrollment code: ')
    if not code:
        raise ValueError('Enrollment code is required')
    result = json.loads(fetch(panel, 'enroll', json.dumps({'code': code}).encode()))
    if (not isinstance(result.get('node_id'), str) or not result['node_id']
            or not isinstance(result.get('token'), str) or not result['token']
            or type(result.get('sequence_floor')) is not int or result['sequence_floor'] < 0):
        raise ValueError('Invalid enrollment response')
    return result


def re_enroll(args, panel):
    config_path = HOME / 'config.json'
    if not config_path.is_file():
        raise ValueError('Re-enrollment requires an existing configuration')
    config = json.loads(config_path.read_text())
    if panel_url(config['panel']) != panel:
        raise ValueError('Re-enrollment central panel must match the existing configuration')
    if not isinstance(config.get('node_id'), str) or not config['node_id']:
        raise ValueError('Existing node identity is missing')
    python = HOME / 'venv/bin/python'
    if not python.is_file() or not UNIT.is_file() or not Path(config['sqlite_path']).is_file():
        raise ValueError('Existing agent runtime, service and local database are required')
    subprocess.run([str(python), '-S', '-c', 'import sqlite3, ssl, urllib.request'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    script = fetch(panel, 'client.py')
    compile(script, 'client.py', 'exec')
    # Quiesce commands before rotating identity; the durable journal survives service restarts.
    subprocess.run(['systemctl', 'stop', 'nexora-xui-agent.service'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        result = enroll(panel, args.code)
        if result['node_id'] != config['node_id']:
            raise ValueError('Enrollment node does not match the existing accounting source')
        config.update(token=result['token'], sequence_floor=result['sequence_floor'])
        private_write(config_path, json.dumps(config).encode())
        private_write(HOME / 'client.py', script)
    finally:
        subprocess.run(['systemctl', 'restart', 'nexora-xui-agent.service'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('XUI agent re-enrolled. Existing credentials, database and journal were preserved.')


def install(args):
    panel = panel_url(args.panel)
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('Run this installer as root on Linux')
    if getattr(args, 're_enroll', False):
        re_enroll(args, panel)
        return
    if (HOME / 'config.json').exists():
        raise ValueError('Agent already configured; preserve its enrollment and journal')
    # Check prerequisites before consuming the one-time code.
    import venv
    if subprocess.run(['systemctl', '--version'], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode:
        raise ValueError('systemd is required')
    HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(HOME, 0o700)
    venv.EnvBuilder(with_pip=False).create(HOME / 'venv')
    script = fetch(panel, 'client.py')
    compile(script, 'client.py', 'exec')
    private_write(HOME / 'client.py', script)
    # Reuse the downloaded standalone client's exact local URL validation.
    import runpy
    client = runpy.run_path(str(HOME / 'client.py'))
    xui_url = client['base_url'](getpass.getpass('Local XUI URL (loopback, include base path): '), local=True)
    token = getpass.getpass('Local XUI API token (blank for username/password): ')
    username = password = ''
    if not token:
        username = getpass.getpass('Local XUI username: ')
        password = getpass.getpass('Local XUI password: ')
        if not username or not password:
            raise ValueError('Local credentials are required')
    detected = next((p for p in KNOWN_DATABASES if Path(p).is_file()), KNOWN_DATABASES[0])
    database = input('XUI SQLite path [' + detected + ']: ').strip() or detected
    if not Path(database).is_file():
        raise ValueError('XUI SQLite database does not exist')
    if input('Confirm this is the local XUI database [yes/no]: ').strip().lower() != 'yes':
        raise ValueError('Database selection was not confirmed')
    enrollment = enroll(panel, args.code)
    config = dict(panel=panel, node_id=enrollment['node_id'], token=enrollment['token'],
                  sequence_floor=enrollment['sequence_floor'],
                  xui_url=xui_url, xui_token=token, xui_username=username,
                  xui_password=password, sqlite_path=str(Path(database).resolve()))
    private_write(HOME / 'config.json', json.dumps(config).encode())
    unit = '''[Unit]
Description=Nexora local XUI agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/nexora-xui-agent/venv/bin/python /opt/nexora-xui-agent/client.py
Restart=on-failure
RestartSec=10
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/nexora-xui-agent

[Install]
WantedBy=multi-user.target
'''
    UNIT.write_text(unit)
    subprocess.run(['systemctl', 'daemon-reload'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['systemctl', 'enable', '--now', 'nexora-xui-agent.service'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('XUI agent installed. Private SQLite snapshots are sent to the central panel.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel', required=True, help='Central HTTPS base URL')
    parser.add_argument('--code', help='One-time enrollment code (or NEXORA_XUI_ENROLL_CODE / hidden prompt)')
    parser.add_argument('--re-enroll', action='store_true', help='Rotate enrollment for the same configured central panel and node')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        install(args)
    except Exception:
        print('Installation failed. Check Python venv support, systemd, connectivity and local settings. No global packages were changed.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
