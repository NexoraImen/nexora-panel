#!/usr/bin/env python3
"""Install only Nexora's managed-connection unit; never change host routing."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

MARKER = "# Managed by Nexora: selective outbound connectivity\n"


def unit(root):
    root = Path(root).resolve()
    if any(c in str(root) for c in "\n\r\t %\"'"):
        raise ValueError("Panel path must not contain whitespace, quotes or percent signs")
    return MARKER + f"""[Unit]
Description=Nexora managed outbound connection
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={root}
Environment=NEXORA_LICENSE_DIR={root}/data
ExecStart={root}/backend/venv/bin/python {root}/scripts/nexora-connect.py
Restart=on-failure
RestartSec=10
User=root
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths={root}/data
PrivateTmp=true
MemoryMax=128M
LimitNOFILE=256

[Install]
WantedBy=multi-user.target
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--unit-out', type=Path, help='Render a stopped unit into a preparation directory only')
    args = parser.parse_args()
    root = args.root.resolve()
    if os.name != 'posix' or os.geteuid() != 0:
        parser.error('Run as root on Linux')
    if not (root / 'backend/venv/bin/python').is_file() or not (root / 'scripts/nexora-connect.py').is_file():
        parser.error('Panel Python environment or connection agent is missing')
    try:
        rendered = unit(root)
    except ValueError as error:
        parser.error(str(error))
    if args.unit_out:
        args.unit_out.write_text(rendered, encoding='utf-8', newline='\n')
        print('Stopped managed connection unit rendered; no service changes.')
        return
    destination = Path('/etc/systemd/system/nexora-connect.service')
    if destination.exists() and not destination.read_text().startswith(MARKER):
        parser.error('Existing nexora-connect unit is not managed by Nexora; left unchanged')
    (root / 'data').mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(rendered)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', 'nexora-connect'], check=True)
    subprocess.run(['systemctl', 'restart', 'nexora-connect'], check=True)
    print('Managed connection agent started.')


if __name__ == '__main__':
    main()
