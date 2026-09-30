#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#   NEXORA VPN — Subscription Page Manager
#   Automated Installer
#   Channel: t.me/yanexoravpn
# ═══════════════════════════════════════════════════════════════

set -o pipefail

VERSION="1.2.0"
INSTALL_DIR="/opt/nexora-panel"
SSL_DIR="/etc/nginx/ssl"

C_RESET='\033[0m'; C_BLUE='\033[38;5;33m'; C_LBLUE='\033[38;5;39m'
C_CYAN='\033[38;5;45m'; C_GREEN='\033[38;5;41m'; C_RED='\033[38;5;196m'
C_YELLOW='\033[38;5;220m'; C_GRAY='\033[38;5;245m'; C_WHITE='\033[38;5;255m'
C_BOLD='\033[1m'; C_DIM='\033[2m'

ok()   { echo -e "  ${C_GREEN}✓${C_RESET} $1"; }
bad()  { echo -e "  ${C_RED}✗${C_RESET} $1"; }
warn() { echo -e "  ${C_YELLOW}!${C_RESET} $1"; }
info() { echo -e "  ${C_LBLUE}i${C_RESET} $1"; }
step() { echo ""; echo -e "${C_BOLD}${C_CYAN}▸ $1${C_RESET}"; }
die()  { bad "$1"; echo ""; exit 1; }

clear
echo ""
echo -e "${C_BLUE}   ╔═══════════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}                                               ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}     ${C_BOLD}${C_LBLUE}N E X O R A${C_RESET}   ${C_GRAY}│${C_RESET}   ${C_WHITE}VPN Platform${C_RESET}      ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}                                               ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ╚═══════════════════════════════════════════════╝${C_RESET}"
echo ""
echo -e "${C_WHITE}      Subscription Page Manager${C_RESET}  ${C_DIM}v${VERSION}${C_RESET}"
echo -e "${C_GRAY}      Telegram: ${C_LBLUE}t.me/yanexoravpn${C_RESET}"
echo ""

[ "$EUID" -ne 0 ] && die "Must run as root.  Try:  sudo bash install.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ ! -d "$SCRIPT_DIR/backend" ] && die "backend/ not found. Run from inside the project folder."

# ═══════════════════ STEP 1 — Configuration ═══════════════════
step "Configuration"
echo ""

while true; do
  read -p "$(echo -e "  ${C_WHITE}Admin panel domain${C_RESET} ${C_DIM}(e.g. panel.yoursite.com)${C_RESET}: ")" PANEL_DOMAIN
  PANEL_DOMAIN=$(echo "$PANEL_DOMAIN" | tr -d ' ' | sed 's|https\?://||; s|/.*||')
  if [ -z "$PANEL_DOMAIN" ]; then bad "Domain cannot be empty"
  elif ! echo "$PANEL_DOMAIN" | grep -qE '^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,}$'; then
    bad "Invalid domain format"
  else break; fi
done

echo ""
while true; do
  read -s -p "$(echo -e "  ${C_WHITE}Admin password${C_RESET} ${C_DIM}(min 8 chars)${C_RESET}: ")" ADMIN_PW; echo ""
  if [ ${#ADMIN_PW} -lt 8 ]; then bad "Password must be at least 8 characters"; continue; fi
  read -s -p "$(echo -e "  ${C_WHITE}Confirm password${C_RESET}: ")" ADMIN_PW2; echo ""
  [ "$ADMIN_PW" != "$ADMIN_PW2" ] && bad "Passwords do not match" || break
done

echo ""
echo -e "  ${C_WHITE}SSL certificate method:${C_RESET}"
echo -e "    ${C_LBLUE}1${C_RESET})  Let's Encrypt  ${C_DIM}(automatic — domain must point to this server)${C_RESET}"
echo -e "    ${C_LBLUE}2${C_RESET})  Cloudflare Origin  ${C_DIM}(paste certificate manually)${C_RESET}"
echo -e "    ${C_LBLUE}3${C_RESET})  Skip  ${C_DIM}(HTTP only)${C_RESET}"
echo ""
read -p "$(echo -e "  ${C_WHITE}Choice [1-3]${C_RESET}: ")" SSL_CHOICE
SSL_CHOICE=${SSL_CHOICE:-1}

EMAIL=""
if [ "$SSL_CHOICE" = "1" ]; then
  echo ""
  read -p "$(echo -e "  ${C_WHITE}Email for Let's Encrypt${C_RESET}: ")" EMAIL
  [ -z "$EMAIL" ] && EMAIL="admin@$PANEL_DOMAIN"
fi

echo ""
read -p "$(echo -e "  ${C_WHITE}Restrict panel to your IP?${C_RESET} ${C_DIM}(empty = allow all)${C_RESET}: ")" ALLOW_IP

echo ""
echo -e "${C_GRAY}  ─────────────────────────────────────────────────────${C_RESET}"
echo -e "  ${C_DIM}Panel domain :${C_RESET} ${C_WHITE}$PANEL_DOMAIN${C_RESET}"
SSL_LABEL="None (HTTP)"
[ "$SSL_CHOICE" = "1" ] && SSL_LABEL="Let's Encrypt"
[ "$SSL_CHOICE" = "2" ] && SSL_LABEL="Cloudflare Origin"
echo -e "  ${C_DIM}SSL method   :${C_RESET} ${C_WHITE}$SSL_LABEL${C_RESET}"
echo -e "  ${C_DIM}IP restrict  :${C_RESET} ${C_WHITE}${ALLOW_IP:-none}${C_RESET}"
echo -e "  ${C_DIM}Install path :${C_RESET} ${C_WHITE}$INSTALL_DIR${C_RESET}"
echo -e "${C_GRAY}  ─────────────────────────────────────────────────────${C_RESET}"
echo ""
read -p "$(echo -e "  ${C_WHITE}Proceed? [y/N]${C_RESET}: ")" CONFIRM
[[ ! "$CONFIRM" =~ ^[Yy]$ ]] && { echo ""; info "Cancelled"; echo ""; exit 0; }

# ═══════════════════ STEP 2 — System update & resources ═══════════════════
step "Preparing system"
export DEBIAN_FRONTEND=noninteractive

info "Updating package lists..."
apt-get update -qq > /dev/null 2>&1
ok "Package lists updated"

info "Upgrading installed packages (this may take a few minutes)..."
apt-get upgrade -y -qq > /dev/null 2>&1
ok "System packages upgraded"

# --- Memory check: Vite needs headroom to build ---
TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
TOTAL_SWAP=$(free -m | awk '/^Swap:/{print $2}')
AVAILABLE=$((TOTAL_MEM + TOTAL_SWAP))

info "Memory: ${TOTAL_MEM}MB RAM + ${TOTAL_SWAP}MB swap"

if [ "$AVAILABLE" -lt 1800 ]; then
  warn "Low memory detected — the frontend build needs ~1.5GB"
  if [ "$TOTAL_SWAP" -lt 1024 ] && [ ! -f /swapfile ]; then
    info "Creating a 2GB swap file..."
    if fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none 2>/dev/null; then
      chmod 600 /swapfile
      mkswap /swapfile > /dev/null 2>&1
      swapon /swapfile > /dev/null 2>&1
      grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
      ok "Swap enabled (2GB) — build will now have enough memory"
    else
      warn "Could not create swap — build may fail on this server"
    fi
  elif [ -f /swapfile ]; then
    swapon /swapfile 2>/dev/null
    ok "Existing swap file activated"
  fi
else
  ok "Sufficient memory available"
fi

# ═══════════════════ STEP 3 — Dependencies ═══════════════════
step "Installing dependencies"
apt-get install -y -qq python3 python3-venv python3-pip nginx unzip curl sqlite3 > /dev/null 2>&1 \
  || die "Failed to install base packages"
ok "Base packages installed"

NODE_OK=false
if command -v node > /dev/null 2>&1; then
  NODE_MAJOR=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
  if [ -n "$NODE_MAJOR" ] && [ "$NODE_MAJOR" -ge 20 ] 2>/dev/null; then
    NODE_OK=true
    ok "Node.js $(node --version) — compatible"
  else
    warn "Node.js $(node --version) is too old — Vite 5 needs Node 20 or newer"
    info "Upgrading Node.js to version 20..."
  fi
else
  info "Installing Node.js 20..."
fi

if [ "$NODE_OK" = false ]; then
  # حذف نسخه‌ی قدیمی مخزن اوبونتو تا با نسخه‌ی جدید تداخل نکند
  apt-get remove -y -qq nodejs npm > /dev/null 2>&1
  apt-get autoremove -y -qq > /dev/null 2>&1
  rm -f /etc/apt/sources.list.d/nodesource.list

  curl -fsSL https://deb.nodesource.com/setup_20.x 2>/dev/null | bash - > /dev/null 2>&1
  apt-get install -y -qq nodejs > /dev/null 2>&1

  NODE_MAJOR=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
  if [ -z "$NODE_MAJOR" ] || [ "$NODE_MAJOR" -lt 20 ] 2>/dev/null; then
    die "Node.js 20 installation failed. Current: $(node --version 2>/dev/null || echo 'not installed')

Try installing manually:
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs"
  fi
  ok "Node.js upgraded to $(node --version)"
fi

ok "npm $(npm --version 2>/dev/null)"

# ═══════════════════ STEP 3 — Deploy files ═══════════════════
step "Deploying files"
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
  if [ -f "$INSTALL_DIR/data/config.json" ]; then
    cp "$INSTALL_DIR/data/config.json" /tmp/nexora-cfg-keep.json
    info "Existing configuration preserved"
  fi
  mkdir -p "$INSTALL_DIR"
  cp -r "$SCRIPT_DIR"/. "$INSTALL_DIR"/ 2>/dev/null
  if [ -f /tmp/nexora-cfg-keep.json ]; then
    mkdir -p "$INSTALL_DIR/data"
    cp /tmp/nexora-cfg-keep.json "$INSTALL_DIR/data/config.json"
    rm -f /tmp/nexora-cfg-keep.json
  fi
fi
echo "$VERSION" > "$INSTALL_DIR/VERSION"
ok "Files deployed to $INSTALL_DIR"

# ═══════════════════ STEP 4 — Backend ═══════════════════
step "Setting up backend"
cd "$INSTALL_DIR/backend"
python3 -m venv venv > /dev/null 2>&1 || die "Failed to create virtualenv"
./venv/bin/pip install --upgrade pip -q > /dev/null 2>&1
./venv/bin/pip install -r requirements.txt -q > /dev/null 2>&1 || die "pip install failed"
ok "Python environment ready"

# ═══════════════════ STEP 5 — Template ═══════════════════
step "Installing subscription template"
PANEL_USER=$(ps -o user= -C x-ui 2>/dev/null | head -1 | tr -d ' ')
[ -z "$PANEL_USER" ] && PANEL_USER="root"

if [ "$PANEL_USER" = "root" ]; then
  SUBPAGE_DIR="/root/sub-page"
else
  SUBPAGE_DIR="/etc/x-ui/sub-page"
  info "x-ui runs as '$PANEL_USER' — using $SUBPAGE_DIR"
fi

mkdir -p "$SUBPAGE_DIR"
sed -i "s|const SUBPAGE_CONFIG_API = \"[^\"]*\"|const SUBPAGE_CONFIG_API = \"https://$PANEL_DOMAIN\"|" \
  "$INSTALL_DIR/sub-page-index.html"
cp "$INSTALL_DIR/sub-page-index.html" "$SUBPAGE_DIR/index.html"
chmod 755 "$SUBPAGE_DIR"; chmod 644 "$SUBPAGE_DIR/index.html"

SRC_SZ=$(stat -c%s "$INSTALL_DIR/sub-page-index.html")
DST_SZ=$(stat -c%s "$SUBPAGE_DIR/index.html")
[ "$SRC_SZ" -ne "$DST_SZ" ] && die "Template copy incomplete"
ok "Template installed ($DST_SZ bytes) → $SUBPAGE_DIR/"

XUI_DB=""
for p in /etc/x-ui/x-ui.db /usr/local/x-ui/bin/x-ui.db /usr/local/x-ui/x-ui.db; do
  [ -f "$p" ] && XUI_DB="$p" && break
done

THEME_SET=false
if [ -n "$XUI_DB" ]; then
  RESULT=$(python3 - "$XUI_DB" "$SUBPAGE_DIR/" << 'PYEOF'
import sqlite3, sys, shutil, time
db, val = sys.argv[1], sys.argv[2]
try: shutil.copy(db, f"{db}.bak-{int(time.time())}")
except Exception: pass
try:
    con = sqlite3.connect(db)
    row = con.execute("SELECT key FROM settings WHERE lower(key) LIKE '%theme%' LIMIT 1;").fetchone()
    if row:
        con.execute("UPDATE settings SET value=? WHERE key=?", (val, row[0])); con.commit(); print("OK")
    else: print("NOKEY")
    con.close()
except Exception as e: print("ERR")
PYEOF
)
  [ "$RESULT" = "OK" ] && { ok "Template path registered in x-ui database"; THEME_SET=true; } \
                       || warn "Could not auto-register path — set it manually in x-ui"
fi

# ═══════════════════ STEP 6 — Service ═══════════════════
step "Creating system service"
cat > /etc/systemd/system/nexora-panel.service << EOF
[Unit]
Description=Nexora Subscription Page Manager
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/backend
Environment="NEXORA_SUBPAGE_ADMIN_PASSWORD=$ADMIN_PW"
Environment="ALLOWED_ORIGIN=*"
Environment="CONFIG_PATH=$INSTALL_DIR/data/config.json"
Environment="AUTH_PATH=$INSTALL_DIR/data/auth.json"
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="XUI_DB_PATH=/etc/x-ui/x-ui.db"
Environment="TUNNEL_DB_PATH=$INSTALL_DIR/data/tunnels.db"
Environment="SUBPAGE_HTML_PATH=$SUBPAGE_DIR/index.html"
ExecStart=$INSTALL_DIR/backend/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8100
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
chmod 600 /etc/systemd/system/nexora-panel.service

# نام مستعار: systemctl status nexora هم کار کند.
# خیلی‌ها «nexora» را می‌زنند چون نام دستور همین است.
ln -sf /etc/systemd/system/nexora-panel.service /etc/systemd/system/nexora.service 2>/dev/null
systemctl daemon-reload
systemctl enable nexora-panel > /dev/null 2>&1
systemctl restart nexora-panel
sleep 4
curl -s http://127.0.0.1:8100/api/health 2>/dev/null | grep -q '"ok":true' \
  || die "Backend failed. Check:  journalctl -u nexora-panel -n 30"
ok "Backend running on port 8100"

# ═══════════════════ STEP 7 — Frontend ═══════════════════
step "Building admin panel"
cd "$INSTALL_DIR/frontend"
echo "VITE_API_URL=https://$PANEL_DOMAIN" > .env

# Give Node enough heap; Vite + lucide-react needs headroom on small VPS
export NODE_OPTIONS="--max-old-space-size=1536"

info "Installing npm packages (2-4 minutes, please wait)..."
if ! timeout 900 npm install --no-fund --no-audit --loglevel=error 2>&1 | grep -vi "warn" | tail -3; then
  if [ ! -d node_modules ]; then
    die "npm install failed or timed out. Check your internet connection and try again."
  fi
fi
[ ! -d node_modules ] && die "npm install produced no node_modules"
ok "Packages installed"

info "Compiling (1-3 minutes — do not interrupt)..."

# Run build in background so we can show a live progress indicator.
# A silent hang is the #1 confusing failure on low-memory servers.
BUILD_LOG="/tmp/nexora-build.log"
npm run build > "$BUILD_LOG" 2>&1 &
BUILD_PID=$!

SPIN='|/-\'
SEC=0
while kill -0 $BUILD_PID 2>/dev/null; do
  printf "\r  ${C_LBLUE}%s${C_RESET} building... %ds" "${SPIN:SEC%4:1}" "$SEC"
  sleep 1
  SEC=$((SEC + 1))
  if [ $SEC -gt 600 ]; then
    kill $BUILD_PID 2>/dev/null
    printf "\r%*s\r" 50 ""
    bad "Build timed out after 10 minutes"
    info "Last output:"
    tail -15 "$BUILD_LOG" | sed 's/^/      /'
    die "Try running manually:  cd $INSTALL_DIR/frontend && npm run build"
  fi
done

wait $BUILD_PID
BUILD_RC=$?
printf "\r%*s\r" 50 ""

if [ $BUILD_RC -ne 0 ] || [ ! -f dist/index.html ]; then
  bad "Build failed"
  echo ""
  info "Error output:"
  tail -20 "$BUILD_LOG" | sed 's/^/      /'
  echo ""
  if grep -qi "heap out of memory\|killed\|SIGKILL" "$BUILD_LOG"; then
    warn "Out of memory during build."
    info "Fix: create swap space, then re-run this installer:"
    echo -e "      ${C_WHITE}fallocate -l 2G /swapfile && chmod 600 /swapfile${C_RESET}"
    echo -e "      ${C_WHITE}mkswap /swapfile && swapon /swapfile${C_RESET}"
  elif grep -qi "unsupported engine\|requires node\|EBADENGINE" "$BUILD_LOG"; then
    warn "Node.js version is incompatible."
    info "Current: $(node --version).  Required: v20 or newer."
    echo -e "      ${C_WHITE}curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -${C_RESET}"
    echo -e "      ${C_WHITE}sudo apt-get install -y nodejs${C_RESET}"
  elif grep -qi "ENOSPC\|no space left" "$BUILD_LOG"; then
    warn "Disk is full."
    info "Free up space and try again:  df -h"
  fi
  echo ""
  exit 1
fi

ok "Admin panel built ($(du -sh dist 2>/dev/null | cut -f1))"
rm -f "$BUILD_LOG"

# ═══════════════════ STEP 8 — SSL ═══════════════════
step "SSL certificate"
mkdir -p "$SSL_DIR"
SSL_READY=false
USE_CERTBOT=false

case "$SSL_CHOICE" in
  1)
    apt-get install -y -qq certbot python3-certbot-nginx > /dev/null 2>&1
    cat > /etc/nginx/conf.d/nexora-panel.conf << EOF
server {
    listen 80;
    server_name $PANEL_DOMAIN;
    root $INSTALL_DIR/frontend/dist;
    index index.html;

    # index.html هرگز کش نمی‌شود — وگرنه بعد از به‌روزرسانی، مرورگر
    # همچنان به فایل‌های قدیمی اشاره می‌کند و پنل خراب به نظر می‌رسد.
    location = /index.html {
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        expires -1;
    }
    # فایل‌های assets نام یکتا دارند، پس بلندمدت کش می‌شوند
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    # JS/CSS فشرده — nginx پیش‌فرض فقط html را فشرده می‌کند و روی
    # اینترنتِ کُند مینی‌اپ پشتِ اسپلش می‌ماند
    gzip on;
    gzip_vary on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types text/css application/javascript application/json image/svg+xml;
    location / { try_files \$uri /index.html; }
    location /api/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        # بدون این، بک‌اند نمی‌داند پنل روی https باز شده — TLS این‌جا
        # تمام می‌شود و درخواست به شکل http به uvicorn می‌رسد. اولین
        # قربانی‌اش ثبتِ خودکار آدرس مینی‌اپ بود که هیچ‌وقت انجام نشد.
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    nginx -t > /dev/null 2>&1 && systemctl reload nginx
    if certbot --nginx -d "$PANEL_DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect > /dev/null 2>&1; then
      ok "Let's Encrypt certificate issued"
      SSL_READY=true; USE_CERTBOT=true
      systemctl enable certbot.timer > /dev/null 2>&1
      ok "Auto-renewal enabled"
    else
      warn "Let's Encrypt failed — check that DNS points to this server"
      info "You can retry later with:  certbot --nginx -d $PANEL_DOMAIN"
    fi
    ;;
  2)
    echo ""
    info "Cloudflare → SSL/TLS → Origin Server → Create Certificate"
    echo ""
    echo -e "  ${C_WHITE}Paste ORIGIN CERTIFICATE${C_RESET} ${C_DIM}(Ctrl+D when done)${C_RESET}:"
    cat > "$SSL_DIR/panel-cert.pem"
    echo ""
    echo -e "  ${C_WHITE}Paste PRIVATE KEY${C_RESET} ${C_DIM}(Ctrl+D when done)${C_RESET}:"
    cat > "$SSL_DIR/panel-key.pem"
    chmod 600 "$SSL_DIR/panel-key.pem"
    if [ -s "$SSL_DIR/panel-cert.pem" ] && [ -s "$SSL_DIR/panel-key.pem" ]; then
      ok "Cloudflare Origin certificate saved"; SSL_READY=true
    else
      warn "Certificate empty — falling back to HTTP"
    fi
    ;;
  *) warn "SSL skipped — HTTP only" ;;
esac

# ═══════════════════ STEP 9 — nginx ═══════════════════
step "Configuring nginx"
IP_RULE=""
[ -n "$ALLOW_IP" ] && IP_RULE="        allow $ALLOW_IP;
        deny all;"

if [ "$USE_CERTBOT" = true ]; then
  [ -n "$ALLOW_IP" ] && sed -i "0,/location \/ {/s||location / {\n$IP_RULE|" /etc/nginx/conf.d/nexora-panel.conf
elif [ "$SSL_READY" = true ]; then
  cat > /etc/nginx/conf.d/nexora-panel.conf << EOF
server {
    listen 80;
    server_name $PANEL_DOMAIN;
    return 301 https://\$host\$request_uri;
}
server {
    listen 443 ssl;
    http2 on;
    server_name $PANEL_DOMAIN;
    ssl_certificate     $SSL_DIR/panel-cert.pem;
    ssl_certificate_key $SSL_DIR/panel-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    root $INSTALL_DIR/frontend/dist;
    index index.html;

    location = /index.html {
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        expires -1;
    }
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    gzip on;
    gzip_vary on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types text/css application/javascript application/json image/svg+xml;
    location / {
$IP_RULE
        try_files \$uri /index.html;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        # بدون این، بک‌اند نمی‌داند پنل روی https باز شده — TLS این‌جا
        # تمام می‌شود و درخواست به شکل http به uvicorn می‌رسد. اولین
        # قربانی‌اش ثبتِ خودکار آدرس مینی‌اپ بود که هیچ‌وقت انجام نشد.
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }
}
EOF
else
  cat > /etc/nginx/conf.d/nexora-panel.conf << EOF
server {
    listen 80;
    server_name $PANEL_DOMAIN;
    root $INSTALL_DIR/frontend/dist;
    index index.html;

    location = /index.html {
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        expires -1;
    }
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    gzip on;
    gzip_vary on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types text/css application/javascript application/json image/svg+xml;
    location / {
$IP_RULE
        try_files \$uri /index.html;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        # بدون این، بک‌اند نمی‌داند پنل روی https باز شده — TLS این‌جا
        # تمام می‌شود و درخواست به شکل http به uvicorn می‌رسد. اولین
        # قربانی‌اش ثبتِ خودکار آدرس مینی‌اپ بود که هیچ‌وقت انجام نشد.
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }
}
EOF
fi

nginx -t > /dev/null 2>&1 || die "nginx config test failed. Run:  nginx -t"
systemctl reload nginx
ok "nginx configured"
[ -n "$ALLOW_IP" ] && ok "Access restricted to $ALLOW_IP"

# ═══════════════════ STEP 9.5 — Bot module (optional) ═══════════════════
if [ -d "$INSTALL_DIR/bot" ]; then
  step "Setting up bot module"

  "$INSTALL_DIR/backend/venv/bin/pip" install -r "$INSTALL_DIR/bot/requirements.txt" -q > /dev/null 2>&1

  cat > /etc/systemd/system/nexora-bot.service << EOF
[Unit]
Description=Nexora Telegram Bot
After=network.target nexora-panel.service

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/bot
Environment="BOT_DB_PATH=$INSTALL_DIR/data/bot.db"
Environment="PANEL_CONFIG=$INSTALL_DIR/data/config.json"
ExecStart=$INSTALL_DIR/backend/venv/bin/python run.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF

  chmod 600 /etc/systemd/system/nexora-bot.service
  systemctl daemon-reload
  ok "Bot module installed (not started — configure the token in the panel first)"
  info "Start it later with:  nexora bot start"
fi

# ═══════════════════ STEP 10 — Final ═══════════════════
step "Final touches"
if command -v ufw > /dev/null 2>&1; then
  ufw allow 80/tcp > /dev/null 2>&1; ufw allow 443/tcp > /dev/null 2>&1
  ok "Firewall ports 80/443 opened"
fi

mkdir -p /root/backups
CRON_JOB="0 3 * * * cp $INSTALL_DIR/data/config.json /root/backups/config-\$(date +\\%Y\\%m\\%d).json 2>/dev/null"
(crontab -l 2>/dev/null | grep -v "nexora-panel/data/config.json"; echo "$CRON_JOB") | crontab -
ok "Daily backup scheduled (03:00 → /root/backups/)"

if [ -f "$INSTALL_DIR/nexora-cli.sh" ]; then
  cp "$INSTALL_DIR/nexora-cli.sh" /usr/local/bin/nexora && chmod +x /usr/local/bin/nexora
  ok "CLI installed — type 'nexora' for management commands"
fi

# ربات: اگر ماژول هست، سرویس را فعال می‌کنیم تا با ورود توکن در پنل
# خودش شروع به کار کند — بدون نیاز به دستور دستی
if [ -d "$INSTALL_DIR/bot" ] && [ -f /etc/systemd/system/nexora-bot.service ]; then
  systemctl enable nexora-bot > /dev/null 2>&1
  systemctl start nexora-bot > /dev/null 2>&1
  sleep 2
  if systemctl is-active --quiet nexora-bot; then
    ok "Bot service running — it will activate once you add a token in the panel"
  else
    info "Bot service enabled — it starts automatically after you add a token"
  fi
fi

# Enable automatic updates from GitHub
if [ ! -f "$INSTALL_DIR/.github" ]; then
  echo 'GITHUB_REPO="NexoraImen/nexora-panel"' > "$INSTALL_DIR/.github"
  chmod 600 "$INSTALL_DIR/.github"
  ok "Auto-update enabled — run 'nexora update' anytime"
fi

if systemctl is-active --quiet x-ui 2>/dev/null; then
  x-ui restart > /dev/null 2>&1 || systemctl restart x-ui > /dev/null 2>&1
  ok "x-ui panel restarted"
fi

PROTO="http"; [ "$SSL_READY" = true ] && PROTO="https"

echo ""
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
echo -e "  ${C_BOLD}${C_GREEN}INSTALLATION COMPLETE${C_RESET}"
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
echo ""
# The panel answers only on its secret path (backend writes data/admin_path.json
# on first start). Showing the bare domain here would send the owner to a 404.
ADMIN_P=""
for _i in 1 2 3 4 5 6 7 8 9 10; do
  [ -f "$INSTALL_DIR/data/admin_path.json" ] && break; sleep 1
done
ADMIN_P=$(sed -n 's/.*"path": *"\([a-z0-9_-]*\)".*/\1/p' "$INSTALL_DIR/data/admin_path.json" 2>/dev/null)
echo -e "  ${C_DIM}Admin panel  :${C_RESET} ${C_LBLUE}${PROTO}://${PANEL_DOMAIN}/${ADMIN_P}${ADMIN_P:+/}${C_RESET}"
[ -z "$ADMIN_P" ] && echo -e "  ${C_YELLOW}  address not ready yet — run: nexora url${C_RESET}"
echo -e "  ${C_DIM}Template dir :${C_RESET} ${C_WHITE}${SUBPAGE_DIR}/${C_RESET}"
echo -e "  ${C_DIM}Version      :${C_RESET} ${C_WHITE}${VERSION}${C_RESET}"
echo ""

if [ "$THEME_SET" = false ]; then
  echo -e "  ${C_YELLOW}${C_BOLD}ACTION REQUIRED${C_RESET}"
  echo -e "  ${C_DIM}x-ui panel → Settings → Subscription → Sub Theme Directory${C_RESET}"
  echo -e "  ${C_DIM}Set to:${C_RESET} ${C_WHITE}${SUBPAGE_DIR}/${C_RESET}   ${C_DIM}then run:${C_RESET} ${C_WHITE}x-ui restart${C_RESET}"
  echo ""
fi

echo -e "  ${C_DIM}Management commands${C_RESET}"
echo -e "  ${C_GRAY}├─${C_RESET} ${C_WHITE}nexora status${C_RESET}      ${C_DIM}service status${C_RESET}"
echo -e "  ${C_GRAY}├─${C_RESET} ${C_WHITE}nexora logs${C_RESET}        ${C_DIM}live logs${C_RESET}"
echo -e "  ${C_GRAY}├─${C_RESET} ${C_WHITE}nexora restart${C_RESET}     ${C_DIM}restart service${C_RESET}"
echo -e "  ${C_GRAY}├─${C_RESET} ${C_WHITE}nexora update${C_RESET}      ${C_DIM}update to latest version${C_RESET}"
echo -e "  ${C_GRAY}└─${C_RESET} ${C_WHITE}nexora diagnose${C_RESET}    ${C_DIM}troubleshoot${C_RESET}"
echo ""
echo -e "${C_GRAY}  ─────────────────────────────────────────────────────${C_RESET}"
echo -e "  ${C_LBLUE}${C_BOLD}NEXORA VPN${C_RESET}  ${C_DIM}·${C_RESET}  ${C_GRAY}Fast · Secure · Reliable${C_RESET}"
echo -e "  ${C_GRAY}t.me/yanexoravpn${C_RESET}"
echo -e "${C_GRAY}  ─────────────────────────────────────────────────────${C_RESET}"
echo ""
