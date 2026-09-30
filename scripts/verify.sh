#!/usr/bin/env bash
#
# Check whether the files on this server match the release they claim to be.
#
#   sudo bash scripts/verify.sh
#
# Every time the panel looked broken after an update, the cause was the same:
# the release on GitHub was older than the fix. This script says so directly
# instead of leaving you to guess.

set -u

G=$'\033[38;5;42m'; R=$'\033[38;5;203m'; Y=$'\033[38;5;220m'
D=$'\033[38;5;245m'; A=$'\033[38;5;39m'; X=$'\033[0m'

ok(){ echo "  ${G}OK${X}    $1"; }
bad(){ echo "  ${R}FAIL${X}  $1"; }
warn(){ echo "  ${Y}WARN${X}  $1"; }
info(){ echo "  ${D}$1${X}"; }

DIR="${INSTALL_DIR:-/opt/nexora-panel}"
[ -d "$DIR" ] || { bad "Panel not found at $DIR"; exit 1; }
cd "$DIR"

echo
echo "${A}Nexora source verification${X}"
echo

# ── version ──
VER=$(cat VERSION 2>/dev/null || echo "?")
ok "Installed version: $VER"

REPO=$(cat .github 2>/dev/null || echo "")
[ -n "$REPO" ] && info "Update source: $REPO"

# ── the stylesheet ──
echo
CSS="frontend/src/index.css"
if [ ! -f "$CSS" ]; then
  bad "$CSS is missing"
  exit 1
fi

LINES=$(wc -l < "$CSS")
info "Stylesheet: $LINES lines"

FAILED=0

check_css() {
  local label="$1" pattern="$2" min="$3"
  local n
  n=$(grep -c -- "$pattern" "$CSS" 2>/dev/null || echo 0)
  if [ "$n" -ge "$min" ]; then
    ok "$label"
  else
    bad "$label — found $n, expected at least $min"
    FAILED=$((FAILED + 1))
  fi
}

check_css "Tailwind directives"        "@tailwind"   3
check_css "Colour variables (:root)"   "^:root"      1
check_css "--bg defined and used"      "[-][-]bg"    2
check_css "Card class"                 "\.fx-card"   1
check_css "Sidebar class"              "\.fx-side"   1
check_css "IRANSansX font"             "IRANSansX"   1

# body must carry the page background
if grep -A 6 '^body {' "$CSS" | grep -q 'background'; then
  ok "body has a background"
else
  bad "body has no background — the page renders colourless"
  FAILED=$((FAILED + 1))
fi

# the form-font rule must carry nothing else
FONTRULE=$(awk '/^input, select/,/^}/' "$CSS" | grep -c ':' || echo 0)
if [ "$FONTRULE" -le 1 ]; then
  ok "Form-font rule holds only the font"
else
  bad "Form-font rule has $FONTRULE properties — it should have one"
  info "Extra properties here override every button and input"
  FAILED=$((FAILED + 1))
fi

# ── the built output ──
echo
BUILT=$(ls frontend/dist/assets/*.css 2>/dev/null | head -1)
if [ -z "$BUILT" ]; then
  warn "No build output — run: sudo bash scripts/rebuild.sh"
else
  SZ=$(wc -c < "$BUILT")
  if [ "$SZ" -lt 15000 ]; then
    bad "Built stylesheet is only ${SZ} bytes — Tailwind did not run"
    FAILED=$((FAILED + 1))
  else
    ok "Built stylesheet: ${SZ} bytes"
  fi
  grep -q -- '--bg' "$BUILT" \
    && ok "Built stylesheet contains --bg" \
    || { bad "Built stylesheet has no --bg"; FAILED=$((FAILED + 1)); }
fi

# ── what the server actually sends ──
echo
CONF=$(ls /etc/nginx/conf.d/nexora-panel.conf 2>/dev/null | head -1)
DOMAIN=""
[ -n "$CONF" ] && DOMAIN=$(grep -oP 'server_name\s+\K[^;]+' "$CONF" | head -1 | tr -d ' ')

if [ -n "$DOMAIN" ]; then
  LIVE=$(curl -sk --max-time 10 "https://$DOMAIN/" 2>/dev/null \
         | grep -oP '(?<=href=")/assets/[^"]+\.css' | head -1)
  if [ -n "$LIVE" ]; then
    CT=$(curl -skI --max-time 10 "https://$DOMAIN$LIVE" 2>/dev/null \
         | grep -i '^content-type' | tr -d '\r')
    LSZ=$(curl -sk --max-time 10 "https://$DOMAIN$LIVE" 2>/dev/null | wc -c)
    echo "$CT" | grep -qi 'text/css' \
      && ok "Server sends CSS as text/css (${LSZ} bytes)" \
      || { bad "Wrong content type: $CT"; info "Run: sudo bash scripts/fix-nginx.sh";
           FAILED=$((FAILED + 1)); }
  else
    warn "Could not read the page to find its stylesheet"
  fi
fi

# ── verdict ──
echo
echo "${D}──────────────────────────────────────────────${X}"
if [ "$FAILED" -eq 0 ]; then
  echo "  ${G}Everything checks out.${X}"
  echo "  ${D}If the panel still looks wrong, it is browser cache:${X}"
  echo "  ${D}refresh with Ctrl+Shift+R, not F5.${X}"
else
  echo "  ${R}${FAILED} problem(s) found.${X}"
  echo
  echo "  ${Y}The source files on this server are older than the fix.${X}"
  echo "  ${D}nexora update pulls from GitHub Releases, so a release that${X}"
  echo "  ${D}predates the fix will keep reinstalling the broken files.${X}"
  echo
  echo "  ${D}Publish the current build as a new release, then:${X}"
  echo "    nexora update"
  echo "    sudo bash scripts/rebuild.sh"
fi
echo
