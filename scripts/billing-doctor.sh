#!/usr/bin/env bash
#
# تشخیص مشکل اتصال حسابداری به دیتابیس ۳x-ui
#
#   bash scripts/billing-doctor.sh
#
# این اسکریپت هیچ چیزی را تغییر نمی‌دهد — فقط بررسی می‌کند و
# می‌گوید مشکل کجاست و چطور رفع شود.

set -u

C_OK=$'\033[38;5;42m'; C_BAD=$'\033[38;5;203m'; C_WARN=$'\033[38;5;220m'
C_DIM=$'\033[38;5;245m'; C_ACC=$'\033[38;5;39m'; C_R=$'\033[0m'
ok(){ echo "  ${C_OK}✓${C_R} $1"; }
bad(){ echo "  ${C_BAD}✗${C_R} $1"; }
warn(){ echo "  ${C_WARN}!${C_R} $1"; }
info(){ echo "  ${C_DIM}$1${C_R}"; }
head(){ echo; echo "${C_ACC}── $1 ──${C_R}"; }

INSTALL_DIR="${INSTALL_DIR:-/opt/nexora-panel}"
[ -d "$INSTALL_DIR" ] || INSTALL_DIR="/opt/nexora-subpage-admin"

echo
echo "${C_ACC}Nexora billing diagnostics${C_R}"
echo "${C_DIM}$(date '+%Y-%m-%d %H:%M')${C_R}"

# ─────────────────────────────────────────────
head ". Locating the 3x-ui database"

FOUND=""
for p in /etc/x-ui/x-ui.db /usr/local/x-ui/x-ui.db /opt/x-ui/x-ui.db /etc/x-ui/db/x-ui.db; do
  if [ -f "$p" ]; then
    SIZE=$(du -h "$p" 2>/dev/null | cut -f1)
    PERM=$(stat -c '%a' "$p" 2>/dev/null)
    OWNER=$(stat -c '%U:%G' "$p" 2>/dev/null)
    ok "$p  (${SIZE}, mode ${PERM}, owner ${OWNER})"
    [ -z "$FOUND" ] && FOUND="$p"
  fi
done

if [ -z "$FOUND" ]; then
  bad "No 3x-ui database in the usual locations"
  info "Searching the whole system..."
  DEEP=$(find / -name "x-ui.db" -not -path "*/proc/*" 2>/dev/null | head -5)
  if [ -n "$DEEP" ]; then
    warn "but found here:"
    echo "$DEEP" | while read -r f; do info "  $f"; done
    FOUND=$(echo "$DEEP" | head -1)
  else
    bad "3x-ui is not installed on this server"
    echo
    exit 1
  fi
fi

# ─────────────────────────────────────────────
head ". Which path the panel reads"

CFG="$INSTALL_DIR/data/config.json"
if [ -f "$CFG" ]; then
  MANUAL=$(python3 -c "
import json
try:
    d=json.load(open('$CFG'))
    print((d.get('advanced') or {}).get('xuiDbPath') or '')
except Exception: print('')
" 2>/dev/null)
  if [ -n "$MANUAL" ]; then
    ok "Manual path in the panel: $MANUAL"
    [ -f "$MANUAL" ] || bad "  but that file does not exist"
  else
    info "Manual path in the panel: none"
  fi
else
  warn "Panel config file not found: $CFG"
fi

SVC="/etc/systemd/system/nexora-panel.service"
if [ -f "$SVC" ]; then
  ENVP=$(grep -oP 'XUI_DB_PATH=\K[^"]+' "$SVC" 2>/dev/null | head -1)
  if [ -n "$ENVP" ]; then
    ok "Service variable: $ENVP"
    [ -f "$ENVP" ] || bad "  but that file does not exist"
  else
 warn " XUI_DB_PATH not set in the service"
    info "  Fine if the default path is correct"
  fi
else
  bad "Panel service not found: $SVC"
fi

# ─────────────────────────────────────────────
head ". Which user runs the panel"

RUNAS=$(systemctl show nexora-panel -p User --value 2>/dev/null)
[ -z "$RUNAS" ] && RUNAS="root"
ok "Service user: $RUNAS"

if [ "$RUNAS" != "root" ]; then
  if sudo -u "$RUNAS" test -r "$FOUND" 2>/dev/null; then
    ok "That user can read the database"
  else
    bad "That user cannot read it - this is the problem"
    info "Fix:  chmod +r $FOUND"
    info "  or:  chmod 755 $(dirname "$FOUND")"
  fi
else
  ok "Running as root - access is fine"
fi

# ─────────────────────────────────────────────
head ". WAL side files"

WALF="$FOUND-wal"
if [ -f "$WALF" ]; then
  warn "Database is in WAL mode"
  for f in "$FOUND-wal" "$FOUND-shm"; do
    if [ -f "$f" ]; then
      if [ -r "$f" ]; then
        ok "$(basename "$f") is readable"
      else
        bad "$(basename "$f") is not readable - this is the problem"
        info "Fix:  chmod +r ${FOUND}*"
      fi
    fi
  done
else
  ok "Not in WAL mode - only the main file is needed"
fi

head ". Database contents"

if command -v sqlite3 >/dev/null 2>&1; then
  TABLES=$(sqlite3 "$FOUND" ".tables" 2>&1)
  if echo "$TABLES" | grep -q "clients"; then
    ok "Has a clients table (3.5 or newer)"
    N=$(sqlite3 "$FOUND" "SELECT COUNT(*) FROM clients;" 2>/dev/null)
    info "  $N configs"
    G=$(sqlite3 "$FOUND" "SELECT COUNT(*) FROM client_groups;" 2>/dev/null)
    info "  $G groups"
    if [ "${G:-0}" -gt 0 ]; then
      echo
      info "  Groups:"
      sqlite3 "$FOUND" "SELECT '   • ' || name FROM client_groups;" 2>/dev/null | while read -r l; do
        info "$l"
      done
    fi
  elif echo "$TABLES" | grep -q "inbounds"; then
    warn "Older version - clients live inside inbounds"
    info "  Billing works but groups come from the remark"
  else
    bad "Unknown schema"
    info "  Tables: $(echo "$TABLES" | tr '\n' ' ' | cut -c1-90)"
  fi
else
  warn "sqlite3 is not installed - cannot inspect contents"
  info "Install:  apt install -y sqlite3"
fi

# ─────────────────────────────────────────────
head ". Live test from inside the panel"

VENV="$INSTALL_DIR/backend/venv/bin/python3"
[ -x "$VENV" ] || VENV="python3"

"$VENV" - <<PYEOF 2>&1
import sys, os
sys.path.insert(0, "$INSTALL_DIR/backend")
os.environ.setdefault("CONFIG_PATH", "$INSTALL_DIR/data/config.json")
try:
    import app as A
except Exception as e:
 print(" \033[38;5;203m✗\033[0m Panel failed:", type(e).__name__, str(e)[:80])
    sys.exit(1)

path = A._xui_db_path()
print(f" \033[38;5;245mpath Panel : {path}\033[0m")

con, err = A._xui_conn()
if con:
 print(" \033[38;5;42m✓\033[0m ")
    try:
        n = con.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
 print(f" \033[38;5;245m {n} and \033[0m")
    except Exception as e:
 print(f" \033[38;5;220m!\033[0m and and: {str(e)[:60]}")
    con.close()
else:
    print(f"  \033[38;5;203m✗\033[0m {err}")

clients, groups, rerr = A._read_xui_clients()
if clients is None:
 print(f" \033[38;5;203m✗\033[0m and failed: {rerr}")
else:
 print(f" \033[38;5;42m✓\033[0m {len(clients)} {len(groups or [])} group")
PYEOF

# ─────────────────────────────────────────────
head "Summary"

if [ -n "$FOUND" ]; then
  echo
  echo "  If you saw an error above, set this in the panel:"
  echo
  echo "    ${C_ACC}Accounting > Settings & backup > Manual path${C_R}"
  echo "    ${C_DIM}$FOUND${C_R}"
  echo
  echo "  Or directly via the service:"
  echo
  echo "    ${C_DIM}nexora fix-xui $FOUND${C_R}"
fi
echo
