#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#   NEXORA — Repair
#
#   Use this when an update left the installation inconsistent:
#   the bot folder is missing, the nexora command is outdated,
#   or the panel shows a blank page.
#
#   Usage — run from inside the extracted package:
#       bash scripts/repair.sh
# ═══════════════════════════════════════════════════════════════

set -o pipefail

C_RESET='\033[0m'; C_BLUE='\033[38;5;33m'; C_LBLUE='\033[38;5;39m'
C_CYAN='\033[38;5;45m'; C_GREEN='\033[38;5;41m'; C_RED='\033[38;5;196m'
C_YELLOW='\033[38;5;220m'; C_GRAY='\033[38;5;245m'; C_WHITE='\033[38;5;255m'
C_BOLD='\033[1m'; C_DIM='\033[2m'

ok()   { echo -e "  ${C_GREEN}✓${C_RESET} $1"; }
bad()  { echo -e "  ${C_RED}✗${C_RESET} $1"; }
warn() { echo -e "  ${C_YELLOW}!${C_RESET} $1"; }
info() { echo -e "  ${C_LBLUE}i${C_RESET} $1"; }
step() { echo ""; echo -e "${C_BOLD}${C_CYAN}▸ $1${C_RESET}"; }

INSTALL_DIR="${NEXORA_DIR:-/opt/nexora-panel}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

clear
echo ""
echo -e "${C_BLUE}   ╔═══════════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}     ${C_BOLD}${C_LBLUE}N E X O R A${C_RESET}   ${C_GRAY}│${C_RESET}   ${C_WHITE}Repair${C_RESET}            ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ╚═══════════════════════════════════════════════╝${C_RESET}"
echo ""

[ "$EUID" -ne 0 ] && { bad "Run this as root"; echo ""; exit 1; }

if [ ! -d "$INSTALL_DIR" ]; then
  bad "Panel not found at $INSTALL_DIR"
  info "If installed elsewhere:  NEXORA_DIR=/path bash scripts/repair.sh"
  echo ""; exit 1
fi

if [ ! -f "$SRC/sub-page-index.html" ]; then
  bad "Run this from inside the extracted package folder"
  info "Current path: $SRC"
  echo ""; exit 1
fi

echo -e "  ${C_DIM}Source :${C_RESET} ${C_WHITE}$SRC${C_RESET}"
echo -e "  ${C_DIM}Target :${C_RESET} ${C_WHITE}$INSTALL_DIR${C_RESET}"
echo -e "  ${C_DIM}Version:${C_RESET} ${C_WHITE}$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo '?') -> $(cat "$SRC/VERSION" 2>/dev/null || echo '?')${C_RESET}"

# ─── Backup ───
step "Backing up"
TS=$(date +%Y%m%d-%H%M%S)
SNAP="/root/nexora-snapshots/$TS"
mkdir -p "$SNAP"
cp "$INSTALL_DIR/data/config.json" "$SNAP/" 2>/dev/null
cp "$INSTALL_DIR/data/auth.json" "$SNAP/" 2>/dev/null
cp "$INSTALL_DIR/data/bot.db" "$SNAP/" 2>/dev/null
cp "$INSTALL_DIR/nexora-cli.sh" "$SNAP/" 2>/dev/null
cp "$INSTALL_DIR/VERSION" "$SNAP/" 2>/dev/null
ok "Saved to $SNAP"

# ─── Preserve current settings ───
API_URL=$(grep -o 'const SUBPAGE_CONFIG_API = "[^"]*"' "$INSTALL_DIR/sub-page-index.html" 2>/dev/null | head -1 | sed 's/.*= "//;s/"//')
VITE_URL=$(grep VITE_API_URL "$INSTALL_DIR/frontend/.env" 2>/dev/null | cut -d= -f2)
SUBPAGE_PATH=$(grep -o 'SUBPAGE_HTML_PATH=[^"]*' /etc/systemd/system/nexora-panel.service 2>/dev/null | cut -d= -f2)
[ -z "$SUBPAGE_PATH" ] && SUBPAGE_PATH="/root/sub-page/index.html"
[ -n "$API_URL" ] && info "Preserving API URL: $API_URL"

# ─── Copy code ───
step "Updating code"

SKIP_TOP="data"
SKIP_SUB="node_modules venv dist __pycache__ .git .env"

copy_tree() {
  local from="$1" to="$2"
  mkdir -p "$to"
  local entry name
  for entry in "$from"/* "$from"/.[!.]*; do
    [ -e "$entry" ] || continue
    name=$(basename "$entry")
    case " $SKIP_SUB " in *" $name "*) continue ;; esac
    if [ -d "$entry" ]; then
      copy_tree "$entry" "$to/$name"
    else
      cp -f "$entry" "$to/$name" 2>/dev/null
    fi
  done
}

for item in "$SRC"/*; do
  [ -e "$item" ] || continue
  name=$(basename "$item")
  case " $SKIP_TOP " in *" $name "*) continue ;; esac
  case " $SKIP_SUB " in *" $name "*) continue ;; esac
  if [ -d "$item" ]; then
    copy_tree "$item" "$INSTALL_DIR/$name"
  else
    cp -f "$item" "$INSTALL_DIR/" 2>/dev/null
  fi
done

rm -rf "$INSTALL_DIR/bot/__pycache__" "$INSTALL_DIR/backend/__pycache__" 2>/dev/null
chmod +x "$INSTALL_DIR"/*.sh 2>/dev/null
ok "Backend, frontend and scripts"

if [ -d "$INSTALL_DIR/bot" ]; then
  BOTN=$(ls -1 "$INSTALL_DIR/bot"/*.py 2>/dev/null | wc -l)
  if [ "$BOTN" -gt 0 ]; then ok "Bot module ($BOTN files)"; else bad "Bot module copy failed"; fi
fi

[ -n "$API_URL" ] && sed -i "s|const SUBPAGE_CONFIG_API = \"[^\"]*\"|const SUBPAGE_CONFIG_API = \"$API_URL\"|" "$INSTALL_DIR/sub-page-index.html"

if [ -f "$INSTALL_DIR/nexora-cli.sh" ]; then
  cp "$INSTALL_DIR/nexora-cli.sh" /usr/local/bin/nexora.new
  chmod +x /usr/local/bin/nexora.new
  mv -f /usr/local/bin/nexora.new /usr/local/bin/nexora
  ok "nexora command updated"
fi

# ─── Deploy template ───
step "Deploying subscription template"
if [ -n "$SUBPAGE_PATH" ]; then
  mkdir -p "$(dirname "$SUBPAGE_PATH")"
  cp "$INSTALL_DIR/sub-page-index.html" "$SUBPAGE_PATH"
  chmod 644 "$SUBPAGE_PATH"
  ok "-> $SUBPAGE_PATH"
fi

# ─── Dependencies ───
step "Installing dependencies"
"$INSTALL_DIR/backend/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q > /dev/null 2>&1
ok "Backend packages"

if [ -f "$INSTALL_DIR/bot/requirements.txt" ]; then
  "$INSTALL_DIR/backend/venv/bin/pip" install -r "$INSTALL_DIR/bot/requirements.txt" -q > /dev/null 2>&1
  ok "Bot packages"
fi

# ─── Bot service ───
if [ -d "$INSTALL_DIR/bot" ] && [ ! -f /etc/systemd/system/nexora-bot.service ]; then
  cat > /etc/systemd/system/nexora-bot.service << BOTEOF
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
BOTEOF
  chmod 600 /etc/systemd/system/nexora-bot.service
  systemctl daemon-reload
  ok "Bot service created"
fi

# ─── Build panel ───
step "Building admin panel"
cd "$INSTALL_DIR/frontend" || exit 1
[ -n "$VITE_URL" ] && echo "VITE_API_URL=$VITE_URL" > .env
export NODE_OPTIONS="--max-old-space-size=1536"

MEM=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
SWP=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
if [ -n "$MEM" ] && [ $((MEM + SWP)) -lt 1500 ] && [ ! -f /swapfile ]; then
  info "Low memory — creating temporary swap"
  fallocate -l 2G /swapfile 2>/dev/null && chmod 600 /swapfile && \
    mkswap /swapfile > /dev/null 2>&1 && swapon /swapfile > /dev/null 2>&1 && ok "Swap enabled"
fi

[ -d dist ] && rm -rf dist.prev && cp -r dist dist.prev 2>/dev/null

BUILD_LOG=/tmp/nexora-repair-build.log
rm -rf node_modules/.vite 2>/dev/null
npm install --no-fund --no-audit --loglevel=error > "$BUILD_LOG" 2>&1
npm run build >> "$BUILD_LOG" 2>&1
RC=$?

JSFILE=$(ls -1 dist/assets/*.js 2>/dev/null | head -1)
if [ -n "$JSFILE" ]; then JSSIZE=$(stat -c%s "$JSFILE" 2>/dev/null || echo 0); else JSSIZE=0; fi

if [ $RC -eq 0 ] && [ -f dist/index.html ] && [ "$JSSIZE" -gt 50000 ]; then
  rm -rf dist.prev
  ok "Panel built ($((JSSIZE / 1024)) KB)"
else
  bad "Build failed"
  echo ""
  echo -e "  ${C_DIM}Last lines of the build log:${C_RESET}"
  tail -20 "$BUILD_LOG" 2>/dev/null | sed 's/^/      /'
  echo ""
  if [ -d dist.prev ]; then
    rm -rf dist && mv dist.prev dist
    warn "Previous panel restored — it still works"
  fi
  warn "Full log: $BUILD_LOG"
  echo ""
  exit 1
fi

# ─── nginx cache headers ───
step "Configuring nginx"
if [ -f "$INSTALL_DIR/scripts/fix-nginx-cache.py" ]; then
  python3 "$INSTALL_DIR/scripts/fix-nginx-cache.py" 2>&1 | sed 's/^/  /'
else
  warn "Cache-header script not found"
fi

# ─── Restart ───
step "Restarting services"
systemctl restart nexora-panel
sleep 4
if curl -s --max-time 6 http://127.0.0.1:8100/api/health 2>/dev/null | grep -q '"ok":true'; then
  ok "Panel is running"
else
  bad "Panel did not come up"
  warn "Check:  journalctl -u nexora-panel -n 30"
fi

systemctl is-active --quiet nexora-bot 2>/dev/null && { systemctl restart nexora-bot; ok "Bot restarted"; }
systemctl is-active --quiet x-ui 2>/dev/null && { x-ui restart > /dev/null 2>&1; ok "x-ui restarted"; }

# ─── Done ───
echo ""
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
echo -e "  ${C_BOLD}${C_GREEN}REPAIR COMPLETE${C_RESET}   ${C_DIM}version $(cat "$INSTALL_DIR/VERSION" 2>/dev/null)${C_RESET}"
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
echo ""
echo -e "  ${C_YELLOW}Important:${C_RESET} open the panel with a hard refresh"
echo -e "  ${C_GRAY}└─${C_RESET} ${C_WHITE}Ctrl + Shift + R${C_RESET}  ${C_DIM}(Cmd + Shift + R on Mac)${C_RESET}"
echo ""

if [ -d "$INSTALL_DIR/bot" ]; then
  echo -e "  ${C_DIM}Next steps for the bot:${C_RESET}"
  echo -e "  ${C_GRAY}|-${C_RESET} Panel > Bot > Connection: add your token"
  echo -e "  ${C_GRAY}|-${C_RESET} Panel > Bot > Plans: create at least one plan"
  echo -e "  ${C_GRAY}\`-${C_RESET} Start it from the panel, or:  ${C_WHITE}nexora bot start${C_RESET}"
  echo ""
fi

echo -e "  ${C_DIM}Health check:${C_RESET}  ${C_WHITE}nexora doctor${C_RESET}"
echo -e "  ${C_DIM}Roll back:${C_RESET}     ${C_WHITE}nexora rollback${C_RESET}"
echo ""
