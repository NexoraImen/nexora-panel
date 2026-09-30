#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#   NEXORA — Diagnose
#
#   Checks the panel, the subscription template, the bot and the
#   3x-ui wiring, and suggests a fix for anything that looks wrong.
#
#   Usage:  nexora diagnose      (or)   bash scripts/diagnose.sh
# ═══════════════════════════════════════════════════════════════

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
XUI_DB="/etc/x-ui/x-ui.db"
ISSUES=0
note_issue() { ISSUES=$((ISSUES + 1)); }

clear
echo ""
echo -e "${C_BLUE}   ╔═══════════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}     ${C_BOLD}${C_LBLUE}N E X O R A${C_RESET}   ${C_GRAY}│${C_RESET}   ${C_WHITE}Diagnose${C_RESET}          ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ╚═══════════════════════════════════════════════╝${C_RESET}"
echo ""

# ─────────── Panel ───────────
step "Panel installation"

if [ -d "$INSTALL_DIR" ]; then
  ok "Directory:    $INSTALL_DIR"
  [ -f "$INSTALL_DIR/VERSION" ] && info "Version:      $(cat "$INSTALL_DIR/VERSION")"
else
  bad "Not installed at $INSTALL_DIR"
  echo ""; exit 1
fi

if systemctl is-active --quiet nexora-panel 2>/dev/null; then
  ok "Service:      running"
else
  bad "Service:      stopped"
  note_issue
  info "Check:  journalctl -u nexora-panel -n 40"
fi

if curl -s --max-time 5 http://127.0.0.1:8100/api/health 2>/dev/null | grep -q '"ok":true'; then
  ok "API:          responding on port 8100"
else
  bad "API:          not responding"
  note_issue
fi

# ─────────── Build ───────────
step "Admin panel build"

DIST="$INSTALL_DIR/frontend/dist"
if [ -f "$DIST/index.html" ]; then
  JSFILE=$(ls -1 "$DIST/assets/"*.js 2>/dev/null | head -1)
  if [ -n "$JSFILE" ]; then
    JSSIZE=$(stat -c%s "$JSFILE" 2>/dev/null || echo 0)
    if [ "$JSSIZE" -gt 50000 ]; then
      ok "Build:        $(basename "$JSFILE") ($((JSSIZE / 1024)) KB)"
    else
      bad "Build:        bundle too small, build was incomplete"
      note_issue
      info "Fix:  nexora rebuild"
    fi
  else
    bad "Build:        no JS bundle found"
    note_issue
    info "Fix:  nexora rebuild"
  fi

  SRC="$INSTALL_DIR/frontend/src/App.jsx"
  if [ -f "$SRC" ] && [ "$SRC" -nt "$DIST/index.html" ]; then
    warn "Build is older than the source code"
    note_issue
    info "The panel is showing the previous version — run:  nexora rebuild"
  fi
else
  bad "Build:        not built yet"
  note_issue
  info "Fix:  nexora rebuild"
fi

# ─────────── nginx ───────────
step "nginx configuration"

NGX="/etc/nginx/conf.d/nexora-panel.conf"
if [ -f "$NGX" ]; then
  ok "Config:       $NGX"
  if grep -q "no-store, no-cache" "$NGX"; then
    ok "Cache:        index.html is never cached"
  else
    bad "Cache:        index.html has no cache headers"
    note_issue
    info "Browsers will keep loading the OLD panel after every update"
    info "Fix:  python3 $INSTALL_DIR/scripts/fix-nginx-cache.py"
  fi
  if nginx -t > /dev/null 2>&1; then
    ok "Syntax:       valid"
  else
    bad "Syntax:       invalid"
    note_issue
  fi
else
  warn "nginx config not found at $NGX"
fi

# ─────────── Template ───────────
step "Subscription page template"

command -v sqlite3 > /dev/null 2>&1 || apt-get install -y sqlite3 > /dev/null 2>&1

if [ -f "$XUI_DB" ]; then
  ok "3x-ui database:  found"
  SUBDIR=$(sqlite3 "$XUI_DB" "SELECT value FROM settings WHERE key='subThemeDir';" 2>/dev/null)
  if [ -n "$SUBDIR" ]; then
    ok "Template dir:    $SUBDIR"
    TPL="${SUBDIR%/}/index.html"
    if [ -f "$TPL" ]; then
      SIZE=$(stat -c%s "$TPL" 2>/dev/null || echo 0)
      ok "Template file:   $((SIZE / 1024)) KB"
      API=$(grep -o 'SUBPAGE_CONFIG_API = "[^"]*"' "$TPL" 2>/dev/null | head -1 | sed 's/.*= "//;s/"//')
      if [ -n "$API" ]; then
        ok "API URL:         $API"
      else
        warn "API URL not set in the template"
        note_issue
        info "Fix:  bash $INSTALL_DIR/scripts/setup-template.sh"
      fi
    else
      bad "Template file missing at $TPL"
      note_issue
      info "Fix:  bash $INSTALL_DIR/scripts/setup-template.sh"
    fi
  else
    warn "subThemeDir is not set in 3x-ui"
    note_issue
    info "Set it in 3x-ui: Panel Settings → Subscription → Template folder"
  fi
else
  warn "3x-ui database not found — is 3x-ui installed?"
fi

if systemctl is-active --quiet x-ui 2>/dev/null; then
  ok "x-ui service:    running"
else
  warn "x-ui service:    stopped"
fi

# ─────────── Bot ───────────
step "Bot module"

if [ -f "$INSTALL_DIR/bot/run.py" ]; then
  N=$(ls -1 "$INSTALL_DIR/bot/"*.py 2>/dev/null | wc -l)
  ok "Module:       present ($N files)"

  if [ -f /etc/systemd/system/nexora-bot.service ]; then
    ok "Service:      installed"
    if systemctl is-active --quiet nexora-bot; then
      ok "Status:       running"
    else
      warn "Status:       stopped"
      info "Start it from the panel, or:  nexora bot start"
    fi
  else
    warn "Service:      not created"
    info "Fix:  nexora doctor"
  fi

  BOTDB="$INSTALL_DIR/data/bot.db"
  if [ -f "$BOTDB" ]; then
    ok "Database:     $(du -h "$BOTDB" | cut -f1)"
    if command -v sqlite3 > /dev/null 2>&1; then
      U=$(sqlite3 "$BOTDB" "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "?")
      P=$(sqlite3 "$BOTDB" "SELECT COUNT(*) FROM orders WHERE status IN ('awaiting','review');" 2>/dev/null || echo "?")
      info "Users: $U   ·   Pending receipts: $P"
    fi
  else
    info "Database:     not created yet"
  fi

  if "$INSTALL_DIR/backend/venv/bin/python" -c "import requests" 2>/dev/null; then
    ok "Dependencies: installed"
  else
    bad "Dependencies: missing"
    note_issue
    info "Fix:  nexora doctor"
  fi
else
  info "Bot module not installed (it is optional)"
fi

# ─────────── CLI ───────────
step "CLI"

if [ -f /usr/local/bin/nexora ] && [ -f "$INSTALL_DIR/nexora-cli.sh" ]; then
  if cmp -s "$INSTALL_DIR/nexora-cli.sh" /usr/local/bin/nexora; then
    ok "Command:      up to date"
  else
    warn "Command:      out of date, newer commands may be missing"
    note_issue
    info "Fix:  nexora doctor"
  fi
else
  warn "Command not installed at /usr/local/bin/nexora"
fi

# ─────────── Resources ───────────
step "Resources"

DISK=$(df -h "$INSTALL_DIR" 2>/dev/null | awk 'NR==2{print $5}' | tr -d '%')
if [ -n "$DISK" ]; then
  if [ "$DISK" -lt 90 ]; then
    ok "Disk:         ${DISK}% used"
  else
    bad "Disk:         ${DISK}% used, running out of space"
    note_issue
  fi
fi

MEM=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
SWP=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
if [ -n "$MEM" ]; then
  TOTAL=$((MEM + SWP))
  if [ "$TOTAL" -ge 1500 ]; then
    ok "Memory:       ${MEM} MB RAM + ${SWP} MB swap"
  else
    warn "Memory:       only ${TOTAL} MB, builds may fail"
    info "A temporary swap file is created automatically during updates"
  fi
fi

# ─────────── Summary ───────────
echo ""
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
if [ "$ISSUES" -eq 0 ]; then
  echo -e "  ${C_BOLD}${C_GREEN}Everything looks healthy${C_RESET}"
else
  echo -e "  ${C_BOLD}${C_YELLOW}${ISSUES} issue(s) found${C_RESET}   ${C_DIM}fixes are listed above${C_RESET}"
  echo ""
  echo -e "  ${C_DIM}Most problems are fixed by:${C_RESET}  ${C_WHITE}nexora doctor${C_RESET}"
fi
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
echo ""
