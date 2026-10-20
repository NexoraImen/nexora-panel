"""
One file that restores the whole panel (docs/specs/2026-10-01-admin-bot-backup-ui.md,
part A).

Before this there were three backups (settings, bot, accounting), each its
own button, and none of them held the tunnels database, receipts, logos, the
license state or the secret admin path. The owner had to remember three
downloads, and a restore on a new server still came back incomplete.

Pure functions over paths, no FastAPI: the panel, the CLI and the management
bot call the same three functions, and the tests run them on a temp folder.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

FORMAT = 1

#: What is state under data/. An allowlist, not "everything but": a file left
#: out of a blocklist would be a secret or a 2 GB log riding along; a file left
#: out of this list is named by the test that compares it with the code.
FILES = ("config.json", "auth.json", "admin_path.json", "license_state.json",
         "install_id", "usage-history.json", "adminbot.json")
DIRS = ("logos", "receipts", "avatars", "chat", "aff-receipts", "channel", "remote-xui")
DBS = ("bot.db", "billing.db", "tunnels.db", "remote-xui.db")

#: A zip that unpacks to more than this is not ours.
MAX_UNPACKED = 4 * 1024 ** 3
MAX_UPLOAD = 256 * 1024 ** 2


class BackupError(Exception):
    """Refused, with a reason the owner can read (Persian: it is shown in the UI)."""


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _db_copy(src, dest):
    """A consistent copy through SQLite's backup API. A plain file copy misses
    whatever still sits in the -wal file: hours of orders, on a busy bot."""
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    d = sqlite3.connect(str(dest))
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def _vtuple(v):
    out = []
    for p in str(v or "0").split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def build(data_dir, dbs, version, out_path, host=""):
    """
    Write the backup zip to `out_path`. `dbs` maps each name in DBS to its real
    path (the bot and billing paths come from environment variables, so they
    are not always under `data_dir`). Returns the manifest.
    """
    data_dir = Path(data_dir)
    entries = []
    remote_files = set()
    with tempfile.TemporaryDirectory() as tmp, \
            zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        def add(src, arc):
            zf.write(src, arc)
            entries.append({"path": arc, "size": os.path.getsize(src), "sha256": _sha(src)})

        for name in DBS:
            p = Path(dbs.get(name) or data_dir / name)
            if p.exists():
                snap = Path(tmp) / name
                _db_copy(p, snap)
                add(snap, name)
                if name == 'remote-xui.db':
                    con = sqlite3.connect(snap)
                    try:
                        remote_files = {r[0] for r in con.execute(
                            'SELECT snapshot_path FROM remote_nodes WHERE snapshot_path IS NOT NULL')}
                    finally:
                        con.close()
        for name in FILES:
            p = data_dir / name
            if p.is_file():
                add(p, name)
        for d in DIRS:
            root = data_dir / d
            if not root.is_dir():
                continue
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    arc = f"{d}/{f.relative_to(root).as_posix()}"
                    if d == 'remote-xui' and arc not in remote_files:
                        continue
                    add(f, arc)
        manifest = {"format": FORMAT, "version": version, "host": host,
                    "createdAt": datetime.now().isoformat(timespec="seconds"),
                    "files": entries}
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return manifest


def _allowed(arc):
    """Only names this module writes. Anything else (`../`, an absolute path, a
    file we do not know) is refused before a byte is written."""
    p = PurePosixPath(arc)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        return False
    if arc in FILES or arc in DBS:
        return True
    return p.parts[0] in DIRS and len(p.parts) >= 2


def verify(zip_path, version):
    """Read and check a backup without touching anything. Returns the manifest."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise BackupError("این فایل پشتیبانِ نکسورا نیست (zip نیست).")
    with zf:
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except (KeyError, ValueError):
            raise BackupError("این فایل پشتیبانِ نکسورا نیست (manifest ندارد).")
        if manifest.get("format") != FORMAT:
            raise BackupError(f"قالبِ پشتیبان ({manifest.get('format')}) را این نسخه نمی‌شناسد.")
        if _vtuple(manifest.get("version")) > _vtuple(version):
            raise BackupError(f"این پشتیبان از نسخه‌ی {manifest.get('version')} است و پنل "
                              f"{version}. اول پنل را به‌روز کنید، بعد بازیابی.")
        total = 0
        names = set(zf.namelist())
        for e in manifest.get("files") or []:
            arc = e.get("path", "")
            if not _allowed(arc) or arc not in names:
                raise BackupError(f"فایلِ ناشناخته یا گم‌شده در پشتیبان: {arc}")
            total += int(e.get("size") or 0)
            h = hashlib.sha256()
            with zf.open(arc) as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest() != e.get("sha256"):
                raise BackupError(f"فایلِ {arc} در پشتیبان خراب است (checksum نمی‌خواند).")
        if total > MAX_UNPACKED:
            raise BackupError("حجمِ بازشده‌ی این پشتیبان غیرعادی است.")
        return manifest


def restore(zip_path, data_dir, dbs, version, safety_path, host="", progress=None, prepare=None):
    """
    Restore a verified backup over the live state. A safety backup of the
    current state is written to `safety_path` first; without it nothing is
    touched, because this overwrites money (payments, wallet balances).
    Returns {"restored": [...], "safety": path}.
    """
    report = progress or (lambda **state: None)
    report(phase="verify")
    manifest = verify(zip_path, version)
    if prepare:
        prepare()
    report(phase="safety", total=len(manifest["files"]), completed=0)
    try:
        build(data_dir, dbs, version, safety_path, host=host)
    except Exception as e:
        raise BackupError(f"نسخه‌ی امن از وضعیتِ فعلی گرفته نشد ({type(e).__name__})؛ "
                          "بازیابی انجام نشد.")
    data_dir = Path(data_dir)
    done = []
    # The signed destination license is not in the archive. Its identity must
    # stay paired with it when importing business data from another server.
    preserve = {"install_id", "license_state.json"} if (data_dir / "license.json").is_file() else set()
    kept = []
    report(phase="restore", total=len(manifest["files"]), completed=0)
    with zipfile.ZipFile(zip_path) as zf, tempfile.TemporaryDirectory() as tmp:
        for e in manifest["files"]:
            arc = e["path"]
            if arc in preserve and (data_dir / arc).is_file():
                kept.append(arc)
                report(phase="restore", total=len(manifest["files"]), completed=len(done) + len(kept))
                continue
            if arc in DBS:
                live = Path(dbs.get(arc) or data_dir / arc)
                live.parent.mkdir(parents=True, exist_ok=True)
                src = Path(tmp) / arc
                with zf.open(arc) as f, open(src, "wb") as o:
                    shutil.copyfileobj(f, o)
                # Into the live file through the backup API, not a file
                # replace: the panel and the bot hold open connections, and a
                # replaced file under an open WAL connection is a corrupt one.
                s = sqlite3.connect(str(src))
                d = sqlite3.connect(str(live), timeout=30)
                try:
                    s.backup(d)
                finally:
                    d.close()
                    s.close()
            else:
                dest = data_dir.joinpath(*PurePosixPath(arc).parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                part = dest.with_name(dest.name + ".restoring")
                with zf.open(arc) as f, open(part, "wb") as o:
                    shutil.copyfileobj(f, o)
                os.replace(part, dest)
            done.append(arc)
            report(phase="restore", total=len(manifest["files"]), completed=len(done) + len(kept))
    return {"restored": done, "safety": str(safety_path), "from": manifest.get("version"),
            "createdAt": manifest.get("createdAt"), "preserved": kept}
