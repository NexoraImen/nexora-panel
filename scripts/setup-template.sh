#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#   NEXORA — Deploy subscription template
#
#   Copies the subscription page template to the folder 3x-ui reads
#   from, wires the API URL into it, and points 3x-ui at that folder.
#
#   Usage:  bash scripts/setup-template.sh [api-url]
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
DEST_DIR="${TEMPLATE_DIR:-/root/sub-page}"
API_URL="$1"

clear
echo ""
echo -e "${C_BLUE}   ╔═══════════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}     ${C_BOLD}${C_LBLUE}N E X O R A${C_RESET}   ${C_GRAY}│${C_RESET}   ${C_WHITE}Template Setup${C_RESET}    ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ╚═══════════════════════════════════════════════╝${C_RESET}"
echo ""

[ "$EUID" -ne 0 ] && { bad "Run this as root"; echo ""; exit 1; }

# ─── Source file ───
step "Locating the template"

SRC=""
for c in "$INSTALL_DIR/sub-page-index.html" "./sub-page-index.html" "$(dirname "$0")/../sub-page-index.html"; do
  [ -f "$c" ] && { SRC="$c"; break; }
done

if [ -z "$SRC" ]; then
  bad "sub-page-index.html not found"
  info "Run this from the package folder, or install the panel first"
  echo ""; exit 1
fi

SRC_SIZE=$(stat -c%s "$SRC")
ok "Found: $SRC ($((SRC_SIZE / 1024)) KB)"

# ─── API URL ───
step "API URL"

if [ -z "$API_URL" ]; then
  # Reuse whatever is already deployed
  CURRENT=$(grep -o 'SUBPAGE_CONFIG_API = "[^"]*"' "$DEST_DIR/index.html" 2>/dev/null | head -1 | sed 's/.*= "//;s/"//')
  if [ -n "$CURRENT" ]; then
    API_URL="$CURRENT"
    ok "Reusing the existing URL: $API_URL"
  else
    # Fall back to the panel domain from nginx
    DOMAIN=$(grep -oP 'server_name \K[^;]+' /etc/nginx/conf.d/nexora-panel.conf 2>/dev/null | head -1 | tr -d ' ')
    if [ -n "$DOMAIN" ]; then
      API_URL="https://$DOMAIN"
      ok "Detected from nginx: $API_URL"
    else
      bad "Could not determine the API URL"
      info "Pass it explicitly:  bash scripts/setup-template.sh https://panel.example.com"
      echo ""; exit 1
    fi
  fi
else
  ok "Using: $API_URL"
fi

# ─── Which user runs x-ui ───
step "Checking 3x-ui"

if [ ! -f "$XUI_DB" ]; then
  warn "3x-ui database not found at $XUI_DB"
  info "The template will still be deployed, but you must set the folder manually"
fi

PANEL_USER=$(ps -o user= -C x-ui 2>/dev/null | head -1)
if [ -n "$PANEL_USER" ] && [ "$PANEL_USER" != "root" ]; then
  info "x-ui runs as '$PANEL_USER', so /root is not readable by it"
  DEST_DIR="/etc/x-ui/sub-page"
  info "Using $DEST_DIR instead"
fi

# ─── Deploy ───
step "Deploying"

mkdir -p "$DEST_DIR"
cp "$SRC" "$DEST_DIR/index.html"

# Wire the API URL into the template
sed -i "s|const SUBPAGE_CONFIG_API = \"[^\"]*\"|const SUBPAGE_CONFIG_API = \"$API_URL\"|" "$DEST_DIR/index.html"

chmod 755 "$DEST_DIR"
chmod 644 "$DEST_DIR/index.html"
[ -n "$PANEL_USER" ] && [ "$PANEL_USER" != "root" ] && chown -R "$PANEL_USER" "$DEST_DIR" 2>/dev/null

DEPLOYED=$(stat -c%s "$DEST_DIR/index.html")
ok "Copied to $DEST_DIR/index.html ($((DEPLOYED / 1024)) KB)"

VERIFY=$(grep -o 'SUBPAGE_CONFIG_API = "[^"]*"' "$DEST_DIR/index.html" | head -1 | sed 's/.*= "//;s/"//')
if [ "$VERIFY" = "$API_URL" ]; then
  ok "API URL written into the template"
else
  bad "API URL was not written correctly"
fi

# ─── Point 3x-ui at it ───
step "Pointing 3x-ui at the folder"

if [ -f "$XUI_DB" ]; then
  command -v sqlite3 > /dev/null 2>&1 || apt-get install -y sqlite3 > /dev/null 2>&1

  if command -v sqlite3 > /dev/null 2>&1; then
    cp "$XUI_DB" "${XUI_DB}.bak-$(date +%s)" 2>/dev/null
    sqlite3 "$XUI_DB" \
      "INSERT INTO settings (key, value) VALUES ('subThemeDir', '$DEST_DIR/')
       ON CONFLICT(key) DO UPDATE SET value = '$DEST_DIR/';" 2>/dev/null

    SET=$(sqlite3 "$XUI_DB" "SELECT value FROM settings WHERE key='subThemeDir';" 2>/dev/null)
    if [ "$SET" = "$DEST_DIR/" ]; then
      ok "subThemeDir set to $SET"
      systemctl restart x-ui > /dev/null 2>&1 && ok "x-ui restarted"
    else
      warn "Could not write subThemeDir automatically"
      info "Set it manually in the 3x-ui panel to: $DEST_DIR/"
    fi
  else
    warn "sqlite3 unavailable"
    info "Set the template folder manually in 3x-ui to: $DEST_DIR/"
  fi
else
  info "Set the template folder manually in 3x-ui to: $DEST_DIR/"
fi

# ─── Done ───
echo ""
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
echo -e "  ${C_BOLD}${C_GREEN}Template deployed${C_RESET}"
echo -e "${C_GRAY}  ═════════════════════════════════════════════════════${C_RESET}"
echo ""
echo -e "  ${C_DIM}Folder :${C_RESET}  ${C_WHITE}$DEST_DIR/${C_RESET}"
echo -e "  ${C_DIM}API    :${C_RESET}  ${C_WHITE}$API_URL${C_RESET}"
echo ""
echo -e "  ${C_DIM}Open any subscription link to verify it renders.${C_RESET}"
echo -e "  ${C_DIM}If it does not, run:${C_RESET}  ${C_WHITE}nexora diagnose${C_RESET}"
echo ""
