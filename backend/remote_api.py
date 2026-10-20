"""HTTP boundaries for the central panel and its outbound 3x-ui agent."""
import shlex
import time
import json
from pathlib import Path

from fastapi import Header, HTTPException, Request
from fastapi.responses import FileResponse


def register(app, remote, check_auth, root_tenant, save_url, origin):
    def agent(authorization):
        try:
            return remote.authenticate((authorization or '').removeprefix('Bearer '))
        except remote.RemoteError as exc:
            raise HTTPException(401, detail=str(exc)) from None

    @app.get('/api/admin/remote-xui')
    def remote_status(x_admin_password: str = Header(...)):
        check_auth(x_admin_password)
        return remote.status()

    @app.put('/api/admin/remote-xui')
    def remote_select(body: dict, x_admin_password: str = Header(...)):
        check_auth(x_admin_password)
        root = root_tenant()
        if not root:
            raise HTTPException(409, detail='ابتدا ربات مالک را در اتصال و تنظیمات ثبت کنید')
        cfg = remote.settings()
        mode, region, node_id = body.get('mode'), body.get('region'), body.get('node_id')
        try:
            if mode == 'remote':
                if not isinstance(node_id, str) or len(node_id) != 24:
                    raise remote.RemoteError('سرور انتخاب‌شده معتبر نیست')
                # A fresh database does not prove that the local API credentials work.
                response = remote.rpc(node_id, 'GET', '/panel/api/inbounds/list', {})
                try:
                    result = json.loads(response['body'])
                except (ValueError, TypeError):
                    result = None
                if (response['status'] != 200 or not isinstance(result, dict) or
                        result.get('success') is False or result.get('obj') is None):
                    raise remote.RemoteError('ایجنت پاسخ می‌دهد ولی ورود و خواندن API سنایی تأیید نشد؛ تنظیمات محلی ایجنت را بررسی کنید')
            remote.select(mode, region, node_id, root.get('panel_url') or '')
            url = f'agent://{node_id}' if mode == 'remote' else cfg.get('source_url') or root.get('panel_url') or ''
            save_url(root['id'], url)
        except remote.RemoteError as exc:
            raise HTTPException(409, detail=str(exc)) from None
        return remote.status()

    @app.post('/api/admin/remote-xui/pair')
    def remote_pair(body: dict, x_admin_password: str = Header(...)):
        check_auth(x_admin_password)
        return pairing_command(body=body)

    def pairing_command(body=None, node_id=None):
        base = origin().rstrip('/')
        if not base.startswith('https://'):
            raise HTTPException(409, detail='برای اتصال ایجنت، دامنه HTTPS پنل را تنظیم کنید')
        try:
            result = remote.repair_pair(node_id) if node_id else remote.pair(body.get('name'), body.get('region'))
        except remote.RemoteError as exc:
            raise HTTPException(400, detail=str(exc)) from None
        installer = base + '/api/xui-agent/install.py'
        result.update(installer_url=installer, command_hint=(
            f'curl --fail --silent --show-error {shlex.quote(installer)} -o /root/install-nexora-xui.py && '
            f'python3 /root/install-nexora-xui.py --panel {shlex.quote(base)} --code {shlex.quote(result["code"])}'
            + (' --re-enroll' if node_id else '')))
        return result

    @app.post('/api/admin/remote-xui/node/{node_id}/pair')
    def remote_repair(node_id: str, x_admin_password: str = Header(...)):
        check_auth(x_admin_password)
        return pairing_command(node_id=node_id)

    @app.delete('/api/admin/remote-xui/node/{node_id}')
    def remote_revoke(node_id: str, x_admin_password: str = Header(...)):
        check_auth(x_admin_password)
        remote.revoke(node_id)
        return {'ok': True}

    @app.post('/api/admin/remote-xui/command/{command_id}/resolve')
    def remote_resolve(command_id: str, body: dict, x_admin_password: str = Header(...)):
        check_auth(x_admin_password)
        if body.get('reviewed') is not True:
            raise HTTPException(400, detail='بررسی نتیجه روی سرور و تطبیق سفارش باید تأیید شود')
        try:
            remote.resolve(command_id)
        except remote.RemoteError as exc:
            raise HTTPException(409, detail=str(exc)) from None
        return {'ok': True}

    @app.get('/api/xui-agent/install.py')
    def agent_installer():
        return FileResponse(Path(__file__).resolve().parents[1] / 'scripts/install-xui-agent.py',
                            media_type='text/x-python', headers={'Cache-Control': 'no-store'})

    @app.get('/api/xui-agent/client.py')
    def agent_client():
        return FileResponse(Path(__file__).resolve().parents[1] / 'scripts/nexora-xui-agent.py',
                            media_type='text/x-python', headers={'Cache-Control': 'no-store'})

    @app.post('/api/xui-agent/enroll')
    def agent_enroll(body: dict):
        try:
            return remote.enroll(body.get('code'))
        except remote.RemoteError as exc:
            raise HTTPException(401, detail=str(exc)) from None

    @app.post('/api/xui-agent/poll')
    def agent_poll(body: dict, authorization: str = Header(None)):
        node = agent(authorization)
        try:
            return remote.poll(node['id'], body.get('results', []))
        except remote.RemoteError as exc:
            raise HTTPException(400, detail=str(exc)) from None

    @app.put('/api/xui-agent/snapshot')
    async def agent_snapshot(request: Request, authorization: str = Header(None),
                             x_snapshot_sequence: int = Header(...),
                             x_snapshot_captured_at: float = Header(...)):
        node = agent(authorization)
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > remote.MAX_SNAPSHOT:
                raise HTTPException(413, detail='اندازه دیتابیس بیش از حد مجاز است')
        try:
            remote.receive_snapshot(node['id'], bytes(body), x_snapshot_sequence, x_snapshot_captured_at)
        except remote.RemoteError as exc:
            raise HTTPException(409, detail=str(exc)) from None
        return {'ok': True, 'received': time.time()}
