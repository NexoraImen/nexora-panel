#!/usr/bin/env bash
#
# رفع پیکربندی nginx که ظاهر پنل را می‌شکند.
#
#   sudo bash scripts/fix-nginx.sh
#
# مشکل: یک بلوک «location /fonts/» با «types { }» در پیکربندی
# آمده بود. آن دستور همه‌ی نگاشت‌های MIME را پاک می‌کند، پس nginx
# فایل CSS را با نوع application/octet-stream می‌فرستد و مرورگر
# آن را به‌عنوان استایل نمی‌پذیرد — نتیجه‌اش پنل بدون ظاهر است.

set -u

OK=$'\033[38;5;42m'; BAD=$'\033[38;5;203m'; WARN=$'\033[38;5;220m'
DIM=$'\033[38;5;245m'; ACC=$'\033[38;5;39m'; RS=$'\033[0m'

ok(){ echo "  ${OK}✓${RS} $1"; }
bad(){ echo "  ${BAD}✗${RS} $1"; }
warn(){ echo "  ${WARN}!${RS} $1"; }
info(){ echo "  ${DIM}$1${RS}"; }

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }

CONF="/etc/nginx/conf.d/nexora-panel.conf"
[ -f "$CONF" ] || CONF=$(grep -rl "nexora" /etc/nginx/ 2>/dev/null | head -1)

echo
echo "${ACC}Repairing nginx config${RS}"
echo

if [ -z "$CONF" ] || [ ! -f "$CONF" ]; then
  bad "config nexora not found"
  exit 1
fi
ok "config: $CONF"

# ── پشتیبان ──
BK="$CONF.bak-$(date +%Y%m%d-%H%M%S)"
cp "$CONF" "$BK"
ok "backup: $(basename "$BK")"

# ── حذف بلوک خراب ──
if grep -q "location /fonts/" "$CONF"; then
  warn "Found the broken block - removing"
  python3 - "$CONF" <<'PY'
import re, sys
p = sys.argv[1]
c = open(p, encoding="utf-8").read()

# بلوک location /fonts/ با همه‌ی محتوای تودرتویش
out, i = [], 0
while True:
    m = re.search(r'\n[^\n]*location\s+/fonts/\s*\{', c[i:])
    if not m:
        out.append(c[i:])
        break
    start = i + m.start()
    out.append(c[i:start])
    # پیدا کردن آکولاد بسته‌ی متناظر
    j = i + m.end() - 1
    depth = 0
    while j < len(c):
        if c[j] == '{':
            depth += 1
        elif c[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    i = j + 1

c = "".join(out)
# کامنت یتیم بالای بلوک
c = re.sub(r'\n\s*#[^\n]*فونت[^\n]*نام ثابت[^\n]*', '', c)
c = re.sub(r'\n\s*#[^\n]*وگرنه بعد از تعویض فونت[^\n]*', '', c)
c = re.sub(r'\n{3,}', '\n\n', c)
open(p, "w", encoding="utf-8").write(c)
PY
  ok "removed"
else
  ok "No broken block"
fi

# ── مطمئن شویم mime.types هست ──
if ! grep -q "include.*mime.types" /etc/nginx/nginx.conf; then
  warn "mime.types missing from nginx.conf - adding"
  sed -i '/http\s*{/a\    include /etc/nginx/mime.types;\n    default_type application/octet-stream;' \
      /etc/nginx/nginx.conf
  ok "added"
else
  ok "mime.types in place"
fi

# ── بررسی و اعمال ──
echo
if nginx -t 2>/dev/null; then
  ok "config valid"
  systemctl reload nginx && ok "nginx reloaded"
else
  bad "config invalid — rolling back"
  nginx -t 2>&1 | sed 's/^/    /'
  cp "$BK" "$CONF"
  systemctl reload nginx 2>/dev/null
  exit 1
fi

# ── تست واقعی ──
echo
DOMAIN=$(grep -oP 'server_name\s+\K[^;]+' "$CONF" | head -1 | tr -d ' ')
if [ -n "$DOMAIN" ]; then
  CSS=$(curl -sk "https://$DOMAIN/" 2>/dev/null | grep -oP '(?<=href=")/assets/[^"]+\.css' | head -1)
  if [ -n "$CSS" ]; then
    CT=$(curl -skI "https://$DOMAIN$CSS" 2>/dev/null | grep -i "^content-type" | tr -d '\r')
    SZ=$(curl -sk "https://$DOMAIN$CSS" 2>/dev/null | wc -c)
    if echo "$CT" | grep -qi "text/css"; then
      ok "CSS served with the correct type ($SZ bytes)"
    else
      bad "MIME type still wrong: $CT"
    fi
  else
    warn "No CSS link on the page - the panel may not be built"
    info "Run: nexora update"
  fi
fi

echo
ok "Done — Refresh the browser with Ctrl+Shift+R"
echo
