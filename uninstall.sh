#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#   NEXORA — Uninstaller
#   Removes the admin panel cleanly
# ═══════════════════════════════════════════════════════════════

INSTALL_DIR="/opt/nexora-panel"
SERVICE="nexora-panel"

C_RESET='\033[0m'; C_BLUE='\033[38;5;33m'; C_LBLUE='\033[38;5;39m'
C_CYAN='\033[38;5;45m'; C_GREEN='\033[38;5;41m'; C_RED='\033[38;5;196m'
C_YELLOW='\033[38;5;220m'; C_GRAY='\033[38;5;245m'; C_WHITE='\033[38;5;255m'
C_BOLD='\033[1m'; C_DIM='\033[2m'

ok()   { echo -e "  ${C_GREEN}✓${C_RESET} $1"; }
bad()  { echo -e "  ${C_RED}✗${C_RESET} $1"; }
warn() { echo -e "  ${C_YELLOW}!${C_RESET} $1"; }
info() { echo -e "  ${C_LBLUE}i${C_RESET} $1"; }
step() { echo ""; echo -e "${C_BOLD}${C_CYAN}▸ $1${C_RESET}"; }

clear
echo ""
echo -e "${C_BLUE}   ╔═══════════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}                                               ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}     ${C_BOLD}${C_LBLUE}N E X O R A${C_RESET}   ${C_GRAY}│${C_RESET}   ${C_WHITE}Uninstaller${C_RESET}       ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}                                               ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ╚═══════════════════════════════════════════════╝${C_RESET}"
echo ""

[ "$EUID" -ne 0 ] && { bad "Must run as root"; echo ""; exit 1; }

# ── What will be removed ──
echo -e "  ${C_WHITE}This will remove:${C_RESET}"
echo -e "  ${C_GRAY}├─${C_RESET} Backend service  ${C_DIM}(nexora-panel)${C_RESET}"
echo -e "  ${C_GRAY}├─${C_RESET} Admin panel files  ${C_DIM}($INSTALL_DIR)${C_RESET}"
echo -e "  ${C_GRAY}├─${C_RESET} nginx site config"
echo -e "  ${C_GRAY}├─${C_RESET} nexora CLI command"
echo -e "  ${C_GRAY}└─${C_RESET} Daily backup cron job"
echo ""
echo -e "  ${C_WHITE}This will NOT touch:${C_RESET}"
echo -e "  ${C_GRAY}├─${C_RESET} Your x-ui panel or its database"
echo -e "  ${C_GRAY}├─${C_RESET} Your VPN configs or customers"
echo -e "  ${C_GRAY}└─${C_RESET} SSL certificates"
echo ""

read -p "$(echo -e "  ${C_WHITE}Continue? Type 'yes' to confirm${C_RESET}: ")" CONFIRM
[ "$CONFIRM" != "yes" ] && { echo ""; info "Cancelled — nothing was removed"; echo ""; exit 0; }

# ── Backup settings first ──
step "Backing up your settings"
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="/root/nexora-backup-$TS"
mkdir -p "$BACKUP_DIR"

SAVED=false
if [ -f "$INSTALL_DIR/data/config.json" ]; then
  cp "$INSTALL_DIR/data/config.json" "$BACKUP_DIR/" && SAVED=true
fi
[ -f "$INSTALL_DIR/data/auth.json" ] && cp "$INSTALL_DIR/data/auth.json" "$BACKUP_DIR/"
[ -f "$INSTALL_DIR/sub-page-index.html" ] && cp "$INSTALL_DIR/sub-page-index.html" "$BACKUP_DIR/"

if [ "$SAVED" = true ]; then
  ok "Settings saved to $BACKUP_DIR"
  info "You can restore them if you reinstall later"
else
  warn "No settings found to back up"
fi

# ── Subscription template ──
step "Subscription template"
TEMPLATE_FOUND=""
for d in /root/sub-page /etc/x-ui/sub-page; do
  [ -f "$d/index.html" ] && TEMPLATE_FOUND="$d"
done

REMOVE_TEMPLATE=false
if [ -n "$TEMPLATE_FOUND" ]; then
  echo ""
  warn "Custom subscription template found at: $TEMPLATE_FOUND"
  info "If you remove it, x-ui will fall back to its default page."
  echo ""
  read -p "$(echo -e "  ${C_WHITE}Remove the template too? [y/N]${C_RESET}: ")" RT
  [[ "$RT" =~ ^[Yy]$ ]] && REMOVE_TEMPLATE=true
fi

# ── Stop and remove service ──
step "Removing service"
if systemctl is-active --quiet $SERVICE 2>/dev/null; then
  systemctl stop $SERVICE
  ok "Service stopped"
fi
if systemctl is-enabled --quiet $SERVICE 2>/dev/null; then
  systemctl disable $SERVICE > /dev/null 2>&1
  ok "Service disabled"
fi
if [ -f "/etc/systemd/system/$SERVICE.service" ]; then
  rm -f "/etc/systemd/system/$SERVICE.service"
  systemctl daemon-reload
  ok "Service file removed"
fi

# ── nginx ──
step "Removing nginx configuration"
if [ -f /etc/nginx/conf.d/nexora-panel.conf ]; then
  cp /etc/nginx/conf.d/nexora-panel.conf "$BACKUP_DIR/nginx-nexora-panel.conf" 2>/dev/null
  rm -f /etc/nginx/conf.d/nexora-panel.conf
  if nginx -t > /dev/null 2>&1; then
    systemctl reload nginx
    ok "nginx config removed and reloaded"
  else
    warn "nginx config test failed — check manually:  nginx -t"
  fi
else
  info "No nginx config found"
fi

# ── CLI ──
step "Removing CLI"
[ -f /usr/local/bin/nexora ] && { rm -f /usr/local/bin/nexora; ok "nexora command removed"; } \
                            || info "CLI not installed"

# ── cron ──
step "Removing scheduled backup"
if crontab -l 2>/dev/null | grep -q "nexora-panel/data/config.json"; then
  crontab -l 2>/dev/null | grep -v "nexora-panel/data/config.json" | crontab -
  ok "Backup cron job removed"
else
  info "No cron job found"
fi

# ── Template ──
if [ "$REMOVE_TEMPLATE" = true ] && [ -n "$TEMPLATE_FOUND" ]; then
  step "Removing subscription template"
  rm -rf "$TEMPLATE_FOUND"
  ok "Template removed from $TEMPLATE_FOUND"

  # Clear the path in x-ui database
  XUI_DB=""
  for p in /etc/x-ui/x-ui.db /usr/local/x-ui/bin/x-ui.db /usr/local/x-ui/x-ui.db; do
    [ -f "$p" ] && XUI_DB="$p" && break
  done
  if [ -n "$XUI_DB" ] && command -v python3 > /dev/null 2>&1; then
    python3 - "$XUI_DB" << 'PYEOF' > /dev/null 2>&1
import sqlite3, sys, shutil, time
db = sys.argv[1]
try: shutil.copy(db, f"{db}.bak-{int(time.time())}")
except Exception: pass
try:
    con = sqlite3.connect(db)
    row = con.execute("SELECT key FROM settings WHERE lower(key) LIKE '%theme%' LIMIT 1;").fetchone()
    if row:
        con.execute("UPDATE settings SET value='' WHERE key=?", (row[0],)); con.commit()
    con.close()
except Exception: pass
PYEOF
    ok "Template path cleared from x-ui settings"
    systemctl is-active --quiet x-ui && { x-ui restart > /dev/null 2>&1; ok "x-ui restarted"; }
  fi
fi

# ── Files ──
step "Removing panel files"
if [ -d "$INSTALL_DIR" ]; then
  rm -rf "$INSTALL_DIR"
  ok "Removed $INSTALL_DIR"
else
  info "Install directory not found"
fi

# ── Done ──
echo ""
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
echo -e "  ${C_BOLD}${C_GREEN}UNINSTALL COMPLETE${C_RESET}"
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
echo ""
echo -e "  ${C_DIM}Your settings backup:${C_RESET} ${C_WHITE}$BACKUP_DIR${C_RESET}"
echo ""

if [ "$REMOVE_TEMPLATE" = false ] && [ -n "$TEMPLATE_FOUND" ]; then
  info "Template kept at $TEMPLATE_FOUND — it still works with built-in defaults"
  echo ""
fi

echo -e "  ${C_DIM}To reinstall later:${C_RESET}"
echo -e "  ${C_WHITE}git clone https://github.com/NexoraImen/nexora-panel.git${C_RESET}"
echo -e "  ${C_WHITE}cd nexora-panel && sudo bash install.sh${C_RESET}"
echo ""
echo -e "${C_GRAY}  ─────────────────────────────────────────────────────${C_RESET}"
echo -e "  ${C_LBLUE}${C_BOLD}NEXORA VPN${C_RESET}  ${C_DIM}·${C_RESET}  ${C_GRAY}t.me/yanexoravpn${C_RESET}"
echo -e "${C_GRAY}  ─────────────────────────────────────────────────────${C_RESET}"
echo ""
