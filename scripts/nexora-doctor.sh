#!/usr/bin/env bash
#
# Nexora Doctor — one report that answers "why is X not working".
#
# Why this exists:
#   Fixing things by guessing wastes everyone's time. Three separate
#   problems in this project were each chased twice before the real cause
#   appeared in a log the maintainer happened to paste.
#
#   This collects, in one pass, everything those investigations needed:
#   versions on disk vs versions running, the agent job queue and where it
#   stalls, what the firewall can and cannot see, whether accounting can
#   read x-ui, and which ports are open and who owns them.
#
#   Output is English on purpose: Persian mixed into shell output collides
#   with terminal bidi handling and scrambles addresses and numbers.
#
# Usage:
#   bash scripts/nexora-doctor.sh            full report
#   bash scripts/nexora-doctor.sh --brief    problems only
#
set -uo pipefail

BRIEF=0
[ "${1:-}" = "--brief" ] && BRIEF=1

C_R=$'\033[0m'; C_B=$'\033[1m'; C_D=$'\033[38;5;245m'
C_G=$'\033[38;5;42m'; C_Y=$'\033[38;5;221m'; C_E=$'\033[38;5;203m'
C_W=$'\033[38;5;255m'

PROBLEMS=0
WARNINGS=0

section() { [ "$BRIEF" = "1" ] && return; echo ""; echo "${C_W}$1${C_R}"
            echo "${C_D}──────────────────────────────────────────────${C_R}"; }
ok()   { [ "$BRIEF" = "1" ] && return; echo "  ${C_G}OK${C_R}   $1"; }
warn() { WARNINGS=$((WARNINGS+1)); echo "  ${C_Y}WARN${C_R} $1"; }
bad()  { PROBLEMS=$((PROBLEMS+1));  echo "  ${C_E}BAD${C_R}  $1"; }
info() { [ "$BRIEF" = "1" ] && return; echo "       ${C_D}$1${C_R}"; }
fix()  { echo "       ${C_D}fix: $1${C_R}"; }

INSTALL_DIR="${INSTALL_DIR:-/opt/nexora-panel}"
BOT_DB="$INSTALL_DIR/data/bot.db"
TUN_DB="$INSTALL_DIR/data/tunnels.db"
BILL_DB="$INSTALL_DIR/data/billing.db"

echo ""
echo "${C_B}Nexora Doctor${C_R}"
echo "${C_D}$(date '+%Y-%m-%d %H:%M')  ·  $(hostname)${C_R}"

# ═══ 1. Versions ═══
section "1. Versions"

DISK_VER=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "?")
echo "  panel on disk : ${C_W}${DISK_VER}${C_R}"

# What the running process actually serves — a panel that was updated but
# not restarted keeps serving the old code, and every symptom looks like
# "the fix did not work".
RUN_VER=$(curl -fsS --max-time 5 "http://127.0.0.1:8100/api/public/version" 2>/dev/null \
          | sed -n 's/.*"version"[: ]*"\([^"]*\)".*/\1/p')
[ -z "$RUN_VER" ] && RUN_VER=$(systemctl show nexora-panel -p ActiveEnterTimestamp --value 2>/dev/null)

SVC_START=$(systemctl show nexora-panel -p ActiveEnterTimestamp --value 2>/dev/null)
FILE_TIME=$(stat -c %y "$INSTALL_DIR/backend/app.py" 2>/dev/null | cut -d. -f1)
echo "  app.py changed: ${C_D}${FILE_TIME:-?}${C_R}"
echo "  panel started : ${C_D}${SVC_START:-?}${C_R}"

if [ -n "$FILE_TIME" ] && [ -n "$SVC_START" ]; then
  F_EPOCH=$(date -d "$FILE_TIME" +%s 2>/dev/null || echo 0)
  S_EPOCH=$(date -d "$SVC_START" +%s 2>/dev/null || echo 0)
  if [ "$F_EPOCH" -gt "$S_EPOCH" ] && [ "$F_EPOCH" -gt 0 ]; then
    bad "panel code is newer than the running process"
    info "the update landed but the service still runs the old code"
    fix "systemctl restart nexora-panel"
  else
    ok "running process is up to date with the files"
  fi
fi

AGENT_VER=$(grep -oP '^VERSION = "\K[^"]+' /opt/nexora-agent/nexora-agent.py 2>/dev/null)
[ -n "$AGENT_VER" ] && echo "  local agent   : ${C_D}${AGENT_VER}${C_R}"

# ═══ 2. Services ═══
section "2. Services"

for svc in nexora-panel nexora-bot nexora-agent x-ui nginx; do
  if ! systemctl list-unit-files "$svc.service" >/dev/null 2>&1; then continue; fi
  if systemctl is-active --quiet "$svc"; then
    MEM=$(systemctl show "$svc" -p MemoryCurrent --value 2>/dev/null)
    if [ -n "$MEM" ] && [ "$MEM" != "[not set]" ] && [ "$MEM" -gt 0 ] 2>/dev/null; then
      ok "$svc up — $((MEM/1024/1024))MB"
    else
      ok "$svc up"
    fi
  else
    bad "$svc is not running"
    fix "systemctl status $svc -n 30"
  fi
done

# ═══ 3. Agent job queue ═══
section "3. Agent jobs — where they stall"

if [ -r "$TUN_DB" ] && command -v sqlite3 >/dev/null 2>&1; then
  NODES=$(sqlite3 "$TUN_DB" "SELECT COUNT(*) FROM nodes WHERE enabled=1;" 2>/dev/null)
  echo "  enabled nodes : ${C_W}${NODES:-0}${C_R}"

  if [ "${NODES:-0}" -gt 0 ]; then
    sqlite3 -separator '|' "$TUN_DB" \
      "SELECT id, name, COALESCE(agent_version,'-'),
              COALESCE(last_seen,'never') FROM nodes WHERE enabled=1;" \
      2>/dev/null | while IFS='|' read -r nid nname nver nseen; do
        echo "  node #$nid ${C_W}${nname}${C_R} — agent ${nver}, last seen ${nseen}"
      done

    # A job stuck on 'taken' means the agent picked it up and never
    # answered. That is what a self-restarting update looks like.
    STUCK=$(sqlite3 "$TUN_DB" \
      "SELECT COUNT(*) FROM jobs WHERE status='taken'
         AND taken_at < datetime('now','-5 minutes');" 2>/dev/null)
    QUEUED=$(sqlite3 "$TUN_DB" \
      "SELECT COUNT(*) FROM jobs WHERE status='queued'
         AND created_at < datetime('now','-5 minutes');" 2>/dev/null)
    FAILED=$(sqlite3 "$TUN_DB" \
      "SELECT COUNT(*) FROM jobs WHERE status='failed'
         AND created_at > datetime('now','-1 day');" 2>/dev/null)

    [ "${STUCK:-0}" -gt 0 ] && {
      warn "${STUCK} job(s) taken by the agent with no answer"
      info "the panel requeues these on the agent's next check-in"
      info "if the count keeps growing, the agent is failing mid-job"
      fix "journalctl -u nexora-agent -n 80 --no-pager"
    }
    [ "${QUEUED:-0}" -gt 0 ] && {
      bad "${QUEUED} job(s) waiting with no agent to take them"
      fix "on the node: systemctl status nexora-agent"
    }
    [ "${FAILED:-0}" -gt 0 ] && {
      warn "${FAILED} job(s) failed in the last day"
      echo ""
      echo "  ${C_D}last failures:${C_R}"
      sqlite3 -separator '|' "$TUN_DB" \
        "SELECT id, action, substr(COALESCE(result,''),1,90) FROM jobs
          WHERE status='failed' ORDER BY id DESC LIMIT 5;" 2>/dev/null \
        | while IFS='|' read -r j a r; do
            echo "       #$j $a — $r"
          done
    }

    SYSMON=$(sqlite3 "$TUN_DB" \
      "SELECT COUNT(*) FROM nodes WHERE enabled=1
         AND (sysmon IS NULL OR sysmon='');" 2>/dev/null)
    if [ "${SYSMON:-0}" -gt 0 ]; then
      bad "${SYSMON} node(s) have never stored a monitoring report"
      info "jobs may be running but the result is not being saved"
    else
      ok "every node has a stored monitoring report"
    fi
  fi
else
  info "tunnels database not readable — no nodes configured yet?"
fi

# ═══ 4. Firewall visibility ═══
section "4. Firewall — what it can see"

if command -v ufw >/dev/null 2>&1; then
  if ufw status 2>/dev/null | grep -q "Status: active"; then
    ok "ufw is active"
  else
    warn "ufw is installed but off — saved rules have no effect yet"
  fi
  RULES=$(ufw show added 2>/dev/null | grep -c '^ufw ')
  info "${RULES:-0} rule(s) saved"
else
  info "ufw is not installed — only blackhole blocking is available"
fi

XDB=""
for p in /etc/x-ui/x-ui.db /usr/local/x-ui/x-ui.db /opt/x-ui/x-ui.db; do
  [ -r "$p" ] && XDB="$p" && break
done

if command -v ss >/dev/null 2>&1; then
  # The panel only warns about ports it can attribute to a process.
  # Ports whose owner it cannot see are the ones that cause confusion.
  # پورت‌های اینباند xray را از خود x-ui می‌گیریم. بدون این فهرست
  # نمی‌شود سوکت موقتِ خروجی را از یک اینباند واقعیِ UDP جدا کرد.
  XPORTS=""
  if [ -n "$XDB" ] && command -v sqlite3 >/dev/null 2>&1; then
    XPORTS=$(sqlite3 "$XDB" "SELECT port FROM inbounds;" 2>/dev/null \
             | tr '\n' ' ')
  fi
  HAVEX=0
  [ -n "$XPORTS" ] && HAVEX=1

  echo ""
  echo "  ${C_D}listening ports and their owners:${C_R}"
  # TCP اول چاپ می‌شود: پورت‌هایی که واقعاً اهمیت دارند — SSH، وب،
  # پنل، تانل — همه TCP هستند، و ss آن‌ها را بعد از UDP می‌دهد.
  # سقف قبلی (۴۰ ردیف) دقیقاً همین‌ها را می‌خورد و گزارش را از
  # سوکت‌های موقت xray پر می‌کرد.
  ss -tulpnH 2>/dev/null | awk -v xports=" ${XPORTS}" -v have="$HAVEX" '
    {
      split($5, a, ":"); port = a[length(a)]
      proc = "-"
      if (match($0, /users:\(\("[^"]+"/)) {
        proc = substr($0, RSTART+9, RLENGTH-10)
      }
      key = $1 " " port " " proc
      if (seen[key]++) next

      # xray برای هر ترافیک خروجی یک سوکت UDP موقت باز می‌کند. اگر
      # پورت در اینباندهای x-ui نباشد سرویس نیست — و با هر ری‌استارت
      # عدد تازه می‌گیرد، پس نامش هم به درد نمی‌خورد.
      if ($1 == "udp" && have == 1 && proc ~ /xray|sing-box/ && index(xports, " " port " ") == 0) { eph++; next }

      if ($1 == "tcp") t[++tn] = sprintf("       %-6s %-8s %s", $1, port, proc)
      else             u[++un] = sprintf("       %-6s %-8s %s", $1, port, proc)
    }
    END {
      for (i = 1; i <= tn; i++) print t[i]
      for (i = 1; i <= un; i++) print u[i]
      if (eph > 0) printf "       %-6s %-8s %s\n", "udp", "+" eph, "ephemeral xray sockets — outbound, not services"
    }'

  NOPROC=$(ss -tulpnH 2>/dev/null | grep -cv 'users:(')
  [ "${NOPROC:-0}" -gt 0 ] && {
    warn "${NOPROC} listening socket(s) have no visible process name"
    info "the panel cannot tell what these are, so it will not guess"
    fix "run this script with sudo so process names are visible"
  }
fi

# Tunnel engines must never be proposed for closing.
echo ""
TUNPROC=$(ps -eo comm,args --no-headers 2>/dev/null \
  | grep -ciE 'backhaul|backpack|chisel|rathole|gost|frpc|frps|wstunnel|hysteria' || true)
if [ "${TUNPROC:-0}" -gt 0 ]; then
  ok "${TUNPROC} tunnel process(es) running"
  ps -eo pid,comm --no-headers 2>/dev/null \
    | grep -iE 'backhaul|backpack|chisel|rathole|gost|frpc|frps|wstunnel|hysteria' \
    | head -6 | while read -r pid comm; do
        PORTS=$(ss -tulpnH 2>/dev/null | grep "pid=$pid," \
                | sed -E 's/.*[:.]([0-9]+) .*/\1/' | sort -u | tr '\n' ' ')
        echo "       $comm (pid $pid) → ports: ${PORTS:-none visible}"
      done
  info "these ports must stay open — the panel protects them"
else
  info "no tunnel process detected on this server"
fi

# ═══ 5. Accounting ═══
section "5. Accounting — can it read x-ui"

if [ -z "$XDB" ]; then
  bad "x-ui database not readable"
  fix "nexora fix-xui"
else
  ok "x-ui database: $XDB"
  if command -v sqlite3 >/dev/null 2>&1; then
    TOT=$(sqlite3 "$XDB" "SELECT COUNT(*) FROM client_traffics;" 2>/dev/null)
    ENA=$(sqlite3 "$XDB" "SELECT COUNT(*) FROM client_traffics WHERE enable=1;" 2>/dev/null)
    echo "  clients: ${C_W}${TOT:-?}${C_R} total, ${C_W}${ENA:-?}${C_R} enabled"

    HASG=$(sqlite3 "$XDB" \
      "SELECT COUNT(*) FROM pragma_table_info('clients') WHERE name='group_name';" 2>/dev/null)
    HASC=$(sqlite3 "$XDB" \
      "SELECT COUNT(*) FROM pragma_table_info('clients') WHERE name='created_at';" 2>/dev/null)

    if [ "${HASC:-0}" = "1" ]; then
      # شکلِ ذخیره‌سازی تاریخ مهم است: x-ui در نسخه‌های مختلف
      # created_at را متنی یا عددی نگه می‌دارد، و حسابداری باید هر
      # دو را بفهمد. این خط می‌گوید روی این سرور کدام است.
      CTYPE=$(sqlite3 "$XDB" \
        "SELECT typeof(created_at) FROM clients
          WHERE created_at IS NOT NULL AND created_at<>'' LIMIT 1;" 2>/dev/null)
      CSAMP=$(sqlite3 "$XDB" \
        "SELECT created_at FROM clients
          WHERE created_at IS NOT NULL AND created_at<>'' LIMIT 1;" 2>/dev/null)
      [ -n "$CTYPE" ] && info "created_at: ${CTYPE} — نمونه: ${CSAMP}"

      NULLC=$(sqlite3 "$XDB" \
        "SELECT COUNT(*) FROM clients WHERE created_at IS NULL OR created_at='';" 2>/dev/null)
      if [ "${NULLC:-0}" -gt 0 ]; then
        warn "${NULLC} client(s) have no creation date in x-ui"
        info "months are estimated for these — set a group start date"
      else
        ok "every client has a creation date"
      fi
    else
      warn "this x-ui version does not record client creation dates"
      info "month counts come from the group start date instead"
      fix "panel > Accounting > set a start date per group"
    fi

    [ "${HASG:-0}" = "1" ] && {
      echo ""
      echo "  ${C_D}clients per group:${C_R}"
      sqlite3 -separator '|' "$XDB" \
        "SELECT CASE WHEN group_name IS NULL OR TRIM(group_name)=''
                     THEN '(no group)' ELSE group_name END g, COUNT(*)
           FROM clients GROUP BY g ORDER BY COUNT(*) DESC LIMIT 15;" 2>/dev/null \
        | while IFS='|' read -r g n; do printf "       %-26s %s\n" "$g" "$n"; done
    }
  fi
fi

if [ -r "$BILL_DB" ] && command -v sqlite3 >/dev/null 2>&1; then
  NOSTART=$(sqlite3 "$BILL_DB" \
    "SELECT COUNT(*) FROM group_config
      WHERE billable=1 AND (period_start IS NULL OR period_start='');" 2>/dev/null)
  [ "${NOSTART:-0}" -gt 0 ] && {
    warn "${NOSTART} billable group(s) have no start date"
    info "their configs count as one month each"
    # نام گروه را می‌گوییم: با یازده گروه، «یکی از آن‌ها» یعنی مدیر
    # باید همه را یکی‌یکی باز کند تا ببیند کدام است.
    sqlite3 "$BILL_DB" \
      "SELECT COALESCE(NULLIF(TRIM(label),''), group_key) FROM group_config
        WHERE billable=1 AND (period_start IS NULL OR period_start='')
        ORDER BY 1 LIMIT 10;" 2>/dev/null \
      | while read -r g; do echo "       ${C_W}${g}${C_R}"; done
    fix "panel > Accounting > dashboard > set start date"
  }
fi

# ═══ 6. Bot ═══
section "6. Bot"

if [ -r "$BOT_DB" ] && command -v sqlite3 >/dev/null 2>&1; then
  JMODE=$(sqlite3 "$BOT_DB" "PRAGMA journal_mode;" 2>/dev/null)
  [ "$JMODE" = "wal" ] && ok "WAL on — readers and writers do not block" \
                       || warn "journal mode is $JMODE, not wal"

  NEG=$(sqlite3 "$BOT_DB" \
    "SELECT COUNT(*) FROM users WHERE balance < 0 OR coins < 0;" 2>/dev/null)
  [ "${NEG:-0}" -gt 0 ] && {
    bad "${NEG} user(s) have a negative balance or coin count"
    info "this should be impossible since 1.7.1 — report it"
  } || ok "no negative balances"

  HOLD=$(sqlite3 "$BOT_DB" \
    "SELECT COUNT(*) FROM coin_tx t JOIN orders o ON o.id = t.order_id
      WHERE t.kind='hold' AND o.status IN ('rejected','expired');" 2>/dev/null)
  [ "${HOLD:-0}" -gt 0 ] && {
    warn "${HOLD} coin hold(s) on orders that ended — not released"
    fix "report this; the release path may have missed them"
  }
else
  info "bot database not readable"
fi

# ═══ 7. Disk and logs ═══
section "7. Disk"

USE=$(df -P / | awk 'NR==2{gsub("%","",$5); print $5}')
[ "${USE:-0}" -ge 90 ] && bad "root filesystem ${USE}% full" \
  || ok "root filesystem ${USE}% used"

for db in "$BOT_DB" "$TUN_DB" "$BILL_DB"; do
  [ -f "$db" ] || continue
  SZ=$(du -h "$db" 2>/dev/null | cut -f1)
  info "$(basename "$db"): $SZ"
done

# ═══ Summary ═══
echo ""
echo "${C_D}──────────────────────────────────────────────${C_R}"
if [ "$PROBLEMS" -gt 0 ]; then
  echo "  ${C_E}${PROBLEMS} problem(s)${C_R}, ${C_Y}${WARNINGS} warning(s)${C_R}"
  echo "  ${C_D}Copy this whole output. BAD lines come first.${C_R}"
elif [ "$WARNINGS" -gt 0 ]; then
  echo "  ${C_Y}${WARNINGS} warning(s)${C_R}, no blocking problems"
else
  echo "  ${C_G}Everything checks out${C_R}"
fi
echo ""
