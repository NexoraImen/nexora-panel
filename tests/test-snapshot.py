#!/usr/bin/env python3
"""
عکس‌برداری پیش از به‌روزرسانی و پیش از بازگردانی.

چرا وجود دارد:
    nexora-cli دو جا از وضعیت فعلی نسخه می‌گرفت — یکی پیش از update،
    یکی پیش از rollback — و هر کدام فهرست جدای خودش را داشت.

    فهرستِ rollback هشت مورد کم داشت، از جمله bot.db.

    یعنی اگر بعد از rollback به «بازگردانی تنظیمات» جواب بله می‌دادید،
    دیتابیس زنده‌ی ربات با نسخه‌ی قدیمی بازنویسی می‌شد و نسخه‌ی زنده
    هیچ‌جا ذخیره نشده بود. هر کاربر، سفارش، اشتراک و موجودی کیف پولی
    که از آخرین به‌روزرسانی به بعد ساخته شده بود، بی‌بازگشت.

    این تست تابع را واقعاً *اجرا* می‌کند روی یک نصبِ ساختگی، نه اینکه
    فقط متن اسکریپت را بخواند.

اجرا:  python3 tests/test-snapshot.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G, R, D, X = "\033[38;5;42m", "\033[38;5;203m", "\033[38;5;245m", "\033[0m"
_ok = _fail = 0


def check(name, cond, detail=""):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  {G}✓{X} {name}" + (f" {D}— {detail}{X}" if detail else ""))
    else:
        _fail += 1
        print(f"  {R}✗{X} {name}" + (f" {D}— {detail}{X}" if detail else ""))


def head(t):
    print(f"\n{D}── {t} ──{X}")


CLI = (ROOT / "nexora-cli.sh").read_text(encoding="utf-8")


def _bash():
    """
    مفسر bash واقعی.

    روی ویندوز، «bash» در PATH معمولاً به WSL می‌رسد که توزیعی نصب
    ندارد و با پیام خودش شکست می‌خورد. Git Bash همان‌جاست و درست کار
    می‌کند. روی لینوکس — یعنی CI — همان bash معمولی.
    """
    for c in ("C:/Program Files/Git/bin/bash.exe",
              "C:/Program Files/Git/usr/bin/bash.exe"):
        if os.path.exists(c):
            return c
    return shutil.which("bash") or "bash"


BASH = _bash()

# ═══════════════════════════════════════════════════════════
head("یک تابع، نه دو فهرست")

check("تابع مشترک تعریف شده", "snapshot_to() {" in CLI)
calls = len(re.findall(r"^\s*snapshot_to\s+\"\$", CLI, re.M))
check("هر دو مسیر از همان استفاده می‌کنند", calls == 2,
      f"{calls} صدازدن — update و rollback")
check("هیچ فهرست دستیِ دومی نمانده",
      '"$PRE/"' not in CLI.replace('snapshot_to "$PRE"', ""),
      "وگرنه دوباره از هم فاصله می‌گیرند")

# ═══════════════════════════════════════════════════════════
head("اجرای واقعی روی یک نصب ساختگی")

TMP = Path(tempfile.mkdtemp())
INST = TMP / "nexora"
(INST / "data").mkdir(parents=True)
(INST / "backend" / "venv").mkdir(parents=True)
(INST / "backend" / "__pycache__").mkdir(parents=True)
(INST / "bot" / "__pycache__").mkdir(parents=True)
(INST / "frontend" / "src" / "sections").mkdir(parents=True)

FILES = {
    "data/config.json": '{"brand":"nexora"}',
    "data/auth.json": '{"password":"x"}',
    "data/bot.db": "BOT-DATA",
    "data/billing.db": "BILL-DATA",
    "data/tunnels.db": "TUN-DATA",
    "sub-page-index.html": "<html></html>",
    "VERSION": "1.2.3",
    ".github": "GITHUB_REPO=x/y",
    "nexora-cli.sh": "#!/bin/bash",
    "backend/app.py": "print(1)",
    "backend/requirements.txt": "fastapi",
    "backend/venv/pyvenv.cfg": "junk",
    "backend/__pycache__/app.pyc": "junk",
    "bot/handlers.py": "print(2)",
    "bot/__pycache__/x.pyc": "junk",
    "frontend/package.json": '{"name":"p"}',
    "frontend/.env": "VITE_API_URL=http://x",
    "frontend/src/App.jsx": "export default 1",
    "frontend/src/sections/billing.jsx": "export const a = 1",
}
for rel, body in FILES.items():
    (INST / rel).write_text(body, encoding="utf-8")

SNAP = TMP / "snap"
harness = TMP / "run.sh"
# فقط همان تابع را بیرون می‌کشیم و اجرا می‌کنیم — بقیه‌ی اسکریپت
# منتظر آرگومان و systemd است
body = CLI[CLI.index("snapshot_to() {"):]
body = body[:body.index("\n}\n") + 3]
harness.write_text(
    'set -e\nINSTALL_DIR="%s"\nVER="1.2.3"\n%s\nsnapshot_to "%s"\n'
    % (INST.as_posix(), body, SNAP.as_posix()), encoding="utf-8")

r = subprocess.run([BASH, str(harness)], capture_output=True, text=True)
check("تابع بدون خطا اجرا می‌شود", r.returncode == 0,
      (r.stderr or "")[:100])

MUST = ["config.json", "auth.json", "bot.db", "billing.db", "tunnels.db",
        "sub-page-index.html", "VERSION", ".github", "nexora-cli.sh",
        "FROM_VERSION", "backend/app.py", "backend/requirements.txt",
        "bot/handlers.py", "frontend/package.json", "frontend/.env",
        "frontend/src/App.jsx", "frontend/src/sections/billing.jsx"]

missing = [f for f in MUST if not (SNAP / f).exists()]
check("هر چیزی که لازم است در نسخه هست", not missing,
      "جامانده: " + "، ".join(missing) if missing else f"{len(MUST)} مورد")

check("دیتابیس ربات واقعاً کپی شده — نه فقط فایل خالی",
      (SNAP / "bot.db").exists()
      and (SNAP / "bot.db").read_text(encoding="utf-8") == "BOT-DATA",
      "همان چیزی که rollback می‌تواند بازنویسی‌اش کند")
check("نسخه‌ی مبدا نوشته شده",
      (SNAP / "FROM_VERSION").read_text(encoding="utf-8").strip() == "1.2.3")

head("زباله‌ها کپی نمی‌شوند")

check("venv کپی نمی‌شود", not (SNAP / "backend" / "venv").exists(),
      "صدها مگابایت بی‌فایده در هر نسخه")
check("__pycache__ بک‌اند کپی نمی‌شود",
      not (SNAP / "backend" / "__pycache__").exists())
check("__pycache__ ربات هم نه",
      not (SNAP / "bot" / "__pycache__").exists(),
      "فایل pyc قدیمی بعد از بازگردانی کد تازه را سایه می‌اندازد")

head("نصب ناقص، اسکریپت را نمی‌شکند")

INST2 = TMP / "minimal"
(INST2 / "data").mkdir(parents=True)
(INST2 / "backend").mkdir(parents=True)
(INST2 / "backend" / "app.py").write_text("x", encoding="utf-8")
SNAP2 = TMP / "snap2"
h2 = TMP / "run2.sh"
h2.write_text('INSTALL_DIR="%s"\nVER="9.9.9"\n%s\nsnapshot_to "%s"\n'
              % (INST2.as_posix(), body, SNAP2.as_posix()), encoding="utf-8")
r2 = subprocess.run([BASH, str(h2)], capture_output=True, text=True)
check("نصبِ بدون ربات و بدون دیتابیس هم کار می‌کند", r2.returncode == 0,
      (r2.stderr or "")[:100])
check("و آن‌چه هست را برمی‌دارد", (SNAP2 / "backend" / "app.py").exists())
check("برای آن‌چه نیست فایل خالی نمی‌سازد",
      not (SNAP2 / "bot.db").exists(),
      "فایل صفر بایت بدتر از نبودن است — موقع بازگردانی داده را پاک می‌کند")

shutil.rmtree(TMP, ignore_errors=True)

# ═══════════════════════════════════════════════════════════
head("اعتبارسنجی بیلد — یک تابع، نه دو نصفه")

# «npm run build موفق شد» کافی نیست. دو حالت دیده شده که هر دو
# خروجی موفق می‌دهند و پنل را خراب بالا می‌آورند: باندل جاوااسکریپتِ
# خیلی کوچک، و CSSِ تقریباً خالی وقتی Tailwind اجرا نشده باشد.
#
# هر کدام در یک مسیر بررسی می‌شد و در دیگری نه: update فقط JS را
# می‌دید و rollback فقط CSS. یعنی خرابیِ Tailwind روی به‌روزرسانی —
# که هر ریلیز اجرا می‌شود — اصلاً گرفته نمی‌شد.

check("تابع مشترک تعریف شده", "verify_build() {" in CLI)
_upd = CLI[CLI.index("\n  update)"):CLI.index("\n  rebuild)")]
_roll = CLI[CLI.index("\n  rollback)"):CLI.index("\n  snapshots)")]
check("به‌روزرسانی از آن استفاده می‌کند", "verify_build" in _upd)
check("بازگردانی هم", "verify_build" in _roll)
# فقط داخل خودِ دستورها می‌گردیم، نه در تابع مشترک — وگرنه بررسی
# روی پیاده‌سازیِ خودش می‌افتد و همیشه قرمز است.
check("هیچ بررسیِ دستیِ دومی در خودِ دستورها نمانده",
      not any(k in _upd or k in _roll
              for k in ("JSSIZE", "-lt 15000", "-gt 50000", "CSSZ=")),
      "وگرنه دوباره هر کدام نصفِ دیگری را می‌سنجد")


def _build_says(js_bytes, css_bytes, index=True):
    """verify_build را روی یک dist ساختگی اجرا می‌کند."""
    d = Path(tempfile.mkdtemp())
    (d / "dist" / "assets").mkdir(parents=True)
    if index:
        (d / "dist" / "index.html").write_text("<html>", encoding="utf-8")
    if js_bytes is not None:
        (d / "dist" / "assets" / "app.js").write_bytes(b"x" * js_bytes)
    if css_bytes is not None:
        (d / "dist" / "assets" / "app.css").write_bytes(b"y" * css_bytes)
    script = (f"set -e\ncd '{d.as_posix()}'\n"
              + CLI[CLI.index("verify_build() {"):CLI.index("snapshot_to() {")]
              + "\nif verify_build; then echo OK; echo \"$BUILD_SIZES\"; "
                "else echo BAD; echo \"$BUILD_WHY\"; fi\n")
    r = subprocess.run([BASH, "-c", script], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
    return (lines[0] if lines else "?"), (lines[1] if len(lines) > 1 else "")


_v, _why = _build_says(400_000, 60_000)
check("بیلد سالم پذیرفته می‌شود", _v == "OK", _why)

_v, _why = _build_says(400_000, 900)
check("CSS خالی رد می‌شود — همان خرابیِ Tailwind", _v == "BAD",
      _why or "پذیرفته شد!")
check("و دلیلش Tailwind را نام می‌برد", "Tailwind" in _why, _why)

_v, _why = _build_says(1200, 60_000)
check("باندل جاوااسکریپتِ کوچک رد می‌شود", _v == "BAD", _why or "پذیرفته شد!")

_v, _why = _build_says(400_000, None)
check("نبودِ فایل CSS هم رد می‌شود", _v == "BAD", _why or "پذیرفته شد!")

_v, _why = _build_says(None, 60_000)
check("نبودِ فایل جاوااسکریپت هم", _v == "BAD", _why or "پذیرفته شد!")

_v, _why = _build_says(400_000, 60_000, index=False)
check("نبودِ index.html هم", _v == "BAD", _why or "پذیرفته شد!")


# ═══════════════════════════════════════════════════════════
head("به‌روزرسانی نباید تنظیمات گیت‌هاب را پاک کند")

# روی سرور، `$INSTALL_DIR/.github` یک *فایل* است که کاربر خودش
# می‌سازد و آدرس مخزن در آن است — همان چیزی که `nexora update` برای
# پیداکردن نسخه‌ی تازه می‌خواند.
#
# در خودِ بسته، `.github/` یک *پوشه* است پر از workflow.
#
# حلقه‌ی سطح‌بالای کپی از `"$SRC"/*` استفاده می‌کند و glob پیش‌فرض
# بش فایل‌های نقطه‌دار را نمی‌گیرد، پس `.github` کاربر دست نمی‌خورد.
# ولی این رفتار *ضمنی* است: کافی است کسی الگو را مثل copy_tree کند
# (که `.[!.]*` را هم می‌گیرد) یا `shopt -s dotglob` بگذارد، تا فایل
# تنظیمات با یک پوشه جایگزین شود و از آن به بعد هر `nexora update`
# بگوید «مخزنی تنظیم نشده».

_copy_loop = CLI[CLI.index('for item in "$SRC"/*'):]
_copy_loop = _copy_loop[:_copy_loop.index("rm -rf \"$INSTALL_DIR/bot/__pycache__\"")]
check("حلقه‌ی کپی فایل‌های نقطه‌دارِ سطح بالا را برنمی‌دارد",
      '"$SRC"/.[!.]*' not in _copy_loop,
      "وگرنه .github کاربر با پوشه‌ی workflowها جایگزین می‌شود")
check("و dotglob هم روشن نشده",
      "dotglob" not in CLI,
      "روشن‌کردنش همان اثر را دارد، از راه دیگر")

# و رفتار واقعی، نه فقط متن
_st = Path(tempfile.mkdtemp())
(_st / "src").mkdir()
(_st / "src" / ".github").mkdir()
(_st / "src" / ".github" / "ci.yml").write_text("on: push", encoding="utf-8")
(_st / "src" / "VERSION").write_text("9.9.9", encoding="utf-8")
(_st / "dst").mkdir()
(_st / "dst" / ".github").write_text('GITHUB_REPO="me/mine"', encoding="utf-8")

_script = (f"cd '{_st.as_posix()}'\n"
           'SKIP_TOP="data"\nSKIP_SUB="node_modules venv dist"\n'
           'SRC=src\nINSTALL_DIR=dst\n'
           'for item in "$SRC"/*; do\n'
           '  [ -e "$item" ] || continue\n'
           '  name=$(basename "$item")\n'
           '  case " $SKIP_TOP " in *" $name "*) continue ;; esac\n'
           '  if [ -d "$item" ]; then mkdir -p "$INSTALL_DIR/$name";\n'
           '  else cp -f "$item" "$INSTALL_DIR/"; fi\n'
           'done\n'
           'cat dst/.github 2>/dev/null || echo "GONE"\n')
_r = subprocess.run([BASH, "-c", _script], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
check("تنظیمات گیت‌هاب بعد از کپی سر جایش است",
      "me/mine" in (_r.stdout or ""),
      (_r.stdout or _r.stderr or "").strip()[:60])
check("و فایل تازه هم کپی شده",
      (_st / "dst" / "VERSION").exists(),
      "یعنی حلقه واقعاً کار کرده، نه اینکه چیزی کپی نشده باشد")


print(f"\n{D}{'─' * 50}{X}")
color = G if not _fail else R
print(f"  {color}{_ok} پاس{X}" + (f" · {R}{_fail} ناموفق{X}" if _fail else ""))
print()
sys.exit(1 if _fail else 0)
