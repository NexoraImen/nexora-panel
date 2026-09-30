#!/usr/bin/env bash
#
# بازسازی اجباری پنل.
#
#   sudo bash scripts/rebuild.sh
#
# وقتی پنل با ظاهر خراب یا داده‌ی «undefined» بالا می‌آید، معمولاً
# یعنی پوشه‌ی dist قدیمی مانده — یا بیلد قبلی نیمه‌کاره تمام شده و
# فایل‌های قبلی سر جایشان مانده‌اند.
#
# این اسکریپت همه‌چیز را از صفر می‌سازد و قبل از جایگزینی بررسی
# می‌کند که خروجی واقعاً سالم است.

set -u

OK=$'\033[38;5;42m'; BAD=$'\033[38;5;203m'; WARN=$'\033[38;5;220m'
DIM=$'\033[38;5;245m'; ACC=$'\033[38;5;39m'; RS=$'\033[0m'

ok(){ echo "  ${OK}✓${RS} $1"; }
bad(){ echo "  ${BAD}✗${RS} $1"; }
warn(){ echo "  ${WARN}!${RS} $1"; }
info(){ echo "  ${DIM}$1${RS}"; }

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }

DIR="${INSTALL_DIR:-/opt/nexora-panel}"
[ -d "$DIR/frontend" ] || { bad "Panel not found at $DIR not found"; exit 1; }

echo
echo "${ACC}Rebuilding the panel${RS}"
echo

cd "$DIR/frontend"

# ── ۱. نگه داشتن نسخه‌ی فعلی ──
if [ -d dist ]; then
  rm -rf dist.backup
  cp -r dist dist.backup
  ok "Current build saved"
fi

# ── ۲. پاکسازی کامل ──
info "Clearing build cache..."
rm -rf dist node_modules/.vite .vite 2>/dev/null
ok "Cache cleared"

# ── ۳. آدرس API ──
DOMAIN=$(grep -oP 'server_name\s+\K[^;]+' /etc/nginx/conf.d/nexora-panel.conf 2>/dev/null \
         | head -1 | tr -d ' ')
if [ -n "$DOMAIN" ]; then
  echo "VITE_API_URL=https://$DOMAIN" > .env
  ok "API address: https://$DOMAIN"
else
  warn "No domain found - .env left as is"
fi

# ── ۴. وابستگی‌ها ──
info "Installing dependencies..."
export NODE_OPTIONS="--max-old-space-size=1536"

MEM=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
SWP=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
if [ -n "$MEM" ] && [ $((MEM + SWP)) -lt 1500 ] && [ ! -f /swapfile ]; then
  warn "Low memory - creating temporary swap"
  fallocate -l 2G /swapfile 2>/dev/null && chmod 600 /swapfile && \
    mkswap /swapfile > /dev/null 2>&1 && swapon /swapfile > /dev/null 2>&1
fi

npm install --no-fund --no-audit --loglevel=error > /tmp/nexora-rebuild.log 2>&1
ok "Dependencies installed"

# ── ۵. بیلد ──
info "Building the panel..."
if ! npm run build >> /tmp/nexora-rebuild.log 2>&1; then
  bad "Build failed — /tmp/nexora-rebuild.log"
  tail -15 /tmp/nexora-rebuild.log | sed 's/^/    /'
  [ -d dist.backup ] && mv dist.backup dist && info "Previous build restored"
  exit 1
fi

# ── ۶. بررسی خروجی ──
echo
CSS=$(ls dist/assets/*.css 2>/dev/null | head -1)
JS=$(ls dist/assets/*.js 2>/dev/null | head -1)

if [ -z "$CSS" ]; then
  bad "No stylesheet was produced"
  [ -d dist.backup ] && rm -rf dist && mv dist.backup dist
  exit 1
fi

CSSZ=$(wc -c < "$CSS")
JSZ=$(wc -c < "$JS" 2>/dev/null || echo 0)

if [ "$CSSZ" -lt 15000 ]; then
  bad "CSS is too small (${CSSZ}B) — Tailwind did not run"
  info "The panel would render unstyled"
  [ -d dist.backup ] && rm -rf dist && mv dist.backup dist && info "Previous build restored"
  exit 1
fi
ok "CSS: $(basename "$CSS") — ${CSSZ} bytes"
ok "JS:  $(basename "$JS") — ${JSZ} bytes"

# محتوای واقعی — نبودشان یعنی فایل منبع اشتباه است، نه بیلد
MISSING=""
for token in "--bg" "--surface" "fx-card" "fx-side" "IRANSansX"; do
  if grep -q -- "$token" "$CSS"; then
    ok "contains $token"
  else
    bad "missing $token"
    MISSING="$MISSING $token"
  fi
done

if [ -n "$MISSING" ]; then
  echo
  bad "The stylesheet is incomplete:$MISSING"
  info "The build worked, but the source file is missing these definitions."
  info "This usually means the release on GitHub is older than the fix."
  info "Check src/index.css has a :root block with --bg and the other colour"
  info "variables, then publish a new release before updating again."
  [ -d dist.backup ] && rm -rf dist && mv dist.backup dist && info "Previous build restored"
  exit 1
fi

rm -rf dist.backup

# ── ۷. nginx ──
echo
if command -v nginx >/dev/null 2>&1; then
  if nginx -t 2>/dev/null; then
    systemctl reload nginx && ok "nginx reloaded"
  else
    bad "nginx config has a problem:"
    nginx -t 2>&1 | sed 's/^/    /'
    info "Run: sudo bash scripts/fix-nginx.sh"
  fi
fi

systemctl restart nexora-panel 2>/dev/null && ok "Panel service restarted"

# ── ۸. تست از بیرون ──
echo
if [ -n "$DOMAIN" ]; then
  LIVE=$(curl -sk "https://$DOMAIN/" 2>/dev/null | grep -oP '(?<=href=")/assets/[^"]+\.css' | head -1)
  if [ -n "$LIVE" ]; then
    CT=$(curl -skI "https://$DOMAIN$LIVE" 2>/dev/null | grep -i "^content-type" | tr -d '\r')
    SZ=$(curl -sk "https://$DOMAIN$LIVE" 2>/dev/null | wc -c)
    if echo "$CT" | grep -qi "text/css" && [ "$SZ" -gt 15000 ]; then
      ok "Server delivers CSS correctly (${SZ}B)"
    else
      bad "Problem serving: $CT (${SZ}B)"
      info "Run: sudo bash scripts/fix-nginx.sh"
    fi
  fi
fi

echo
ok "Done"
echo
echo " ${WARN}Note:${RS} and ${ACC}Ctrl+Shift+R${RS} from "
echo "  ${DIM}A plain F5 will serve the old files from cache${RS}"
echo
