#!/usr/bin/env bash
#
# Why is the server slow?
#
# This does not guess. It measures, and for every number it says where
# the line between fine and bad actually is.
#
# Run:  sudo bash scripts/slow-doctor.sh
#
set -u

R=$'\e[38;5;203m'; G=$'\e[38;5;42m'; Y=$'\e[38;5;220m'
D=$'\e[38;5;245m'; W=$'\e[1m'; X=$'\e[0m'

ok()   { echo "  ${G}OK${X}   $1"; }
warn() { echo "  ${Y}WARN${X} $1"; }
bad()  { echo "  ${R}BAD${X}  $1"; }
info() { echo "       ${D}$1${X}"; }
# NOT named "head": a shell function shadows the coreutil of the same
# name, so every `| head -N` in this script was calling this function
# with "-N" as a title. That is why the process list, the busiest
# peers and the Xray section all printed separator lines as data.
section() { echo ""; echo "${W}$1${X}"; echo "${D}──────────────────────────────────────────────${X}"; }

echo ""
echo "${W}Nexora — slowness report${X}"
echo "${D}$(date '+%Y-%m-%d %H:%M')  ·  $(hostname)${X}"

# ═══ 1. CPU ═══
section "1. CPU load"
CORES=$(nproc 2>/dev/null || echo 1)
LOAD1=$(awk '{print $1}' /proc/loadavg 2>/dev/null || echo 0)
LOAD5=$(awk '{print $2}' /proc/loadavg 2>/dev/null || echo 0)
RATIO=$(awk -v l="$LOAD1" -v c="$CORES" 'BEGIN{printf "%.2f", l/c}')
echo "  load 1min: ${W}$LOAD1${X}   5min: $LOAD5   cores: $CORES"
echo "  load per core: ${W}$RATIO${X}   ${D}(1.00 = fully busy)${X}"

if awk -v r="$RATIO" 'BEGIN{exit !(r>1.5)}'; then
  bad "CPU is saturated — this alone makes everything slow"
elif awk -v r="$RATIO" 'BEGIN{exit !(r>0.7)}'; then
  warn "CPU is working hard; little headroom left for spikes"
else
  ok "CPU has headroom"
fi

echo ""
echo "  ${D}Top CPU consumers:${X}"
ps -eo pcpu,pmem,rss,comm --sort=-pcpu 2>/dev/null | head -7 \
  | awk 'NR==1{printf "       %-6s %-6s %-9s %s\n","%CPU","%MEM","RSS","COMMAND"; next}
         {printf "       %-6s %-6s %-9s %s\n", $1, $2, int($3/1024)"M", $4}'

# ═══ 2. Memory ═══
section "2. Memory"
if [ -r /proc/meminfo ]; then
  MT=$(awk '/MemTotal/{print $2}' /proc/meminfo)
  MA=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
  ST=$(awk '/SwapTotal/{print $2}' /proc/meminfo)
  SF=$(awk '/SwapFree/{print $2}' /proc/meminfo)
  USED=$(( (MT - MA) * 100 / MT ))
  echo "  used: ${W}${USED}%${X}   free: $((MA/1024)) MB of $((MT/1024)) MB"
  if   [ "$USED" -ge 90 ]; then bad "memory nearly exhausted — the kernel is thrashing"
  elif [ "$USED" -ge 75 ]; then warn "memory filling up"
  else ok "plenty of memory"; fi

  if [ "${ST:-0}" -gt 0 ]; then
    SU=$(( (ST - SF) * 100 / ST ))
    if [ "$SU" -ge 20 ]; then
      bad "swap is ${SU}% used — the server is paging to disk"
    else
      ok "swap barely touched (${SU}%)"
    fi
  else
    info "no swap configured"
  fi
fi

# ═══ 3. Disk ═══
section "3. Disk"
df -h / 2>/dev/null | awk 'NR==2{printf "  root: %s of %s used (%s)\n", $3, $2, $5}'
DPCT=$(df / 2>/dev/null | awk 'NR==2{gsub("%","",$5); print $5}')
if [ "${DPCT:-0}" -ge 90 ]; then bad "disk almost full — SQLite and logs suffer"
else ok "disk space is fine"; fi

DD=$(dd if=/dev/zero of=/tmp/.nx-io bs=1M count=64 oflag=direct 2>&1 | tail -1)
rm -f /tmp/.nx-io
echo "  write: ${D}${DD}${X}"
case "$DD" in
  *GB/s) ok "disk is fast" ;;
  *MB/s)
    NUM=$(echo "$DD" | grep -oE '[0-9.]+ MB/s' | grep -oE '^[0-9.]+')
    if awk -v n="${NUM:-999}" 'BEGIN{exit !(n<50)}'; then
      bad "disk is slow — the bot database lives here"
    else ok "disk speed acceptable"; fi ;;
esac

# ═══ 4. Services ═══
section "4. Services"
for s in nexora-panel nexora-bot x-ui nginx; do
  systemctl list-unit-files 2>/dev/null | grep -q "^$s" || continue
  ST=$(systemctl is-active "$s" 2>/dev/null)
  RS=$(systemctl show "$s" -p NRestarts --value 2>/dev/null || echo 0)
  MEM=$(systemctl show "$s" -p MemoryCurrent --value 2>/dev/null)
  MB="?"; [ "${MEM:-0}" -gt 0 ] 2>/dev/null && MB=$((MEM/1024/1024))
  if [ "$ST" != "active" ]; then
    bad "$s is $ST"
  elif [ "${RS:-0}" -gt 5 ]; then
    warn "$s up but restarted ${RS} times — unstable (${MB}MB)"
  else
    ok "$s up — ${MB}MB"
  fi
done

# ═══ 5. Telegram latency ═══
section "5. Telegram latency"
info "this dominates how fast the bot feels"
T=$(curl -o /dev/null -s -w '%{time_connect} %{time_total}' -m 15 \
      https://api.telegram.org 2>/dev/null)
if [ -n "$T" ]; then
  TC=$(echo "$T" | awk '{print $1}'); TT=$(echo "$T" | awk '{print $2}')
  echo "  connect: ${W}${TC}s${X}   total: ${W}${TT}s${X}"
  if   awk -v t="$TT" 'BEGIN{exit !(t>2)}';   then
    bad "very high latency — every bot reply costs at least this"
    info "if this server is in Iran, the bot needs a tunnel or proxy"
  elif awk -v t="$TT" 'BEGIN{exit !(t>0.8)}'; then
    warn "noticeable latency — the bot will feel sluggish"
  else ok "latency to Telegram is good"; fi
else
  bad "Telegram unreachable from this server — the bot cannot work"
fi

# ═══ 6. Bot database ═══
section "6. Bot database"
BOTDB=""
for p in /opt/nexora/data/bot.db /opt/nexora-panel/data/bot.db; do
  [ -f "$p" ] && BOTDB="$p" && break
done
if [ -n "$BOTDB" ]; then
  echo "  $BOTDB  (${W}$(du -h "$BOTDB" | cut -f1)${X})"
  if command -v sqlite3 >/dev/null 2>&1; then
    U=$(sqlite3 "$BOTDB" "SELECT COUNT(*) FROM users" 2>/dev/null || echo ?)
    O=$(sqlite3 "$BOTDB" "SELECT COUNT(*) FROM orders" 2>/dev/null || echo ?)
    S=$(sqlite3 "$BOTDB" "SELECT COUNT(*) FROM subscriptions WHERE is_active=1" 2>/dev/null || echo ?)
    JM=$(sqlite3 "$BOTDB" "PRAGMA journal_mode" 2>/dev/null || echo ?)
    echo "  users: $U   orders: $O   active subs: $S   journal: ${W}${JM}${X}"
    if [ "$JM" = "wal" ]; then
      ok "WAL on — readers and writers do not block each other"
    else
      warn "WAL off — every write locks the whole database"
      info "fix: sqlite3 $BOTDB 'PRAGMA journal_mode=WAL;' && systemctl restart nexora-bot"
    fi
  fi
else
  info "bot database not found"
fi

# ═══ 7. Connections ═══
section "7. Active connections"
if command -v ss >/dev/null 2>&1; then
  # ss -tun with a state filter drops the State column, so the peer is
  # the last field. Using $NF instead of a fixed index is what makes
  # this work for both tcp and udp rows, and for IPv6.
  RAW=$(ss -tunH state established 2>/dev/null)
  TOT=$(printf '%s\n' "$RAW" | grep -c . )
  echo "  established: ${W}${TOT}${X}"

  PEERS=$(printf '%s\n' "$RAW" | awk 'NF>=5 {print $NF}' \
          | sed -E 's/:[0-9]+$//; s/^\[//; s/\]$//' \
          | grep -vE '^(127\.0\.0\.1|::1|\*|0\.0\.0\.0|)$')

  UNIQ=$(printf '%s\n' "$PEERS" | sort -u | grep -c .)
  echo "  unique peer IPs: ${W}${UNIQ}${X}"

  if [ "$UNIQ" -gt 0 ]; then
    echo ""
    echo "  ${D}Busiest peers:${X}"
    printf '%s\n' "$PEERS" | sort | uniq -c | sort -rn | head -8 \
      | awk -v tot="$TOT" '{
          pct = tot>0 ? ($1*100/tot) : 0
          printf "       %-40s %6d  (%.1f%%)\n", $2, $1, pct
        }'

    TOPN=$(printf '%s\n' "$PEERS" | sort | uniq -c | sort -rn | head -1 | awk '{print $1}')
    TOPIP=$(printf '%s\n' "$PEERS" | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')
    if [ "${TOPN:-0}" -gt 0 ] && [ "$TOT" -gt 0 ]; then
      SHARE=$(awk -v n="$TOPN" -v t="$TOT" 'BEGIN{printf "%.0f", n*100/t}')
      if [ "$SHARE" -ge 30 ]; then
        warn "$TOPIP holds ${SHARE}% of all connections"
        info "if that is your own tunnel node, this is expected"
        info "otherwise: one account shared widely, or a scan"
      fi
    fi
  fi

  echo ""
  echo "  ${D}Busiest local ports:${X}"
  printf '%s\n' "$RAW" | awk 'NF>=5 {print $(NF-1)}' \
    | sed -E 's/.*:([0-9]+)$/\1/' | sort | uniq -c | sort -rn | head -6 \
    | awk '{printf "       port %-8s %6d\n", $2, $1}'

  # Connections per active subscription tells you whether the count is
  # normal customer usage or something else entirely.
  # The denominator has to be every enabled client in x-ui, not just the
  # bot's subscriptions. Resellers sell too, and dividing 2250 connections
  # by only the bot's 6 subscriptions produced a scary number that meant
  # nothing. XE is filled in by the x-ui section below; when it is not
  # available we fall back to the bot count and say so.
  XDB_EARLY=""
  for c in /etc/x-ui/x-ui.db /usr/local/x-ui/x-ui.db \
           /opt/x-ui/x-ui.db /usr/local/x-ui/bin/x-ui.db; do
    [ -r "$c" ] && XDB_EARLY="$c" && break
  done
  ACTIVE=""
  if [ -n "$XDB_EARLY" ] && command -v sqlite3 >/dev/null 2>&1; then
    ACTIVE=$(sqlite3 "$XDB_EARLY" \
      "SELECT COUNT(*) FROM client_traffics WHERE enable=1;" 2>/dev/null)
  fi
  BASIS="clients across all channels"
  if [ -z "${ACTIVE:-}" ] || [ "${ACTIVE:-0}" -le 0 ]; then
    ACTIVE="${S:-0}"
    BASIS="bot subscriptions only — x-ui not readable"
  fi

  if [ -n "${ACTIVE:-}" ] && [ "${ACTIVE:-0}" -gt 0 ] 2>/dev/null; then
    PER=$(awk -v c="$TOT" -v s="$ACTIVE" 'BEGIN{printf "%.0f", c/s}')
    echo ""
    echo "  ${W}${PER}${X} connections per active client  ${D}(${TOT} / ${ACTIVE})${X}"
    info "basis: ${BASIS}"
    if [ "$PER" -gt 200 ]; then
      bad "far more connections than your clients can explain"
      info "likely a scan, or one config shared very widely"
    elif [ "$PER" -gt 60 ]; then
      warn "high per client — normal for heavy use, worth a look"
    else
      ok "in the normal range for VPN traffic"
    fi
  fi

  # The bot is only one of the sales channels. Resellers have their own
  # clients in x-ui, grouped by group_name, and those are billed through
  # the panel's accounting — not by the bot. So "clients the bot did not
  # sell" is normal and expected; what matters is whether every client
  # belongs to a channel you can account for.
  XDB=""
  for c in /etc/x-ui/x-ui.db /usr/local/x-ui/x-ui.db \
           /opt/x-ui/x-ui.db /usr/local/x-ui/bin/x-ui.db; do
    [ -r "$c" ] && XDB="$c" && break
  done

  if [ -n "$XDB" ] && command -v sqlite3 >/dev/null 2>&1; then
    echo ""
    echo "  ${D}Clients in the x-ui panel itself:${X}"

    XC=$(sqlite3 "$XDB" "SELECT COUNT(*) FROM client_traffics;" 2>/dev/null)
    XE=$(sqlite3 "$XDB" "SELECT COUNT(*) FROM client_traffics WHERE enable=1;" 2>/dev/null)
    XU=$(sqlite3 "$XDB" \
      "SELECT COUNT(*) FROM client_traffics WHERE (up+down) > 0;" 2>/dev/null)

    echo "       total clients:   ${W}${XC:-?}${X}"
    echo "       enabled:         ${W}${XE:-?}${X}"
    echo "       with traffic:    ${W}${XU:-?}${X}"

    # Clients per reseller group. This is the number that explains a
    # large connection count on a panel that sells through resellers.
    HAS_GROUP=$(sqlite3 "$XDB" \
      "SELECT COUNT(*) FROM pragma_table_info('clients') WHERE name='group_name';" \
      2>/dev/null)

    if [ "${HAS_GROUP:-0}" = "1" ]; then
      echo ""
      echo "  ${D}Clients per reseller group:${X}"
      sqlite3 -separator '|' "$XDB" \
        "SELECT CASE WHEN group_name IS NULL OR TRIM(group_name)=''
                     THEN '(no group)' ELSE group_name END AS g,
                COUNT(*)
         FROM clients GROUP BY g ORDER BY COUNT(*) DESC LIMIT 12;" \
        2>/dev/null \
        | awk -F'|' '{printf "       %-28s %6s clients\n", $1, $2}'

      UNGROUPED=$(sqlite3 "$XDB" \
        "SELECT COUNT(*) FROM clients
         WHERE group_name IS NULL OR TRIM(group_name)='';" 2>/dev/null)
      GROUPED=$(sqlite3 "$XDB" \
        "SELECT COUNT(*) FROM clients
         WHERE group_name IS NOT NULL AND TRIM(group_name)<>'';" 2>/dev/null)

      echo ""
      echo "       ${W}${GROUPED:-0}${X} clients belong to a reseller group"
      echo "       ${W}${UNGROUPED:-0}${X} clients have no group"

      # Only ungrouped clients beyond the bot's own subscriptions are
      # genuinely unaccounted. Reseller clients are billed by the panel,
      # so counting them as "unknown" would be wrong and alarming.
      if [ -n "${UNGROUPED:-}" ] && [ -n "${S:-}" ] \
         && [ "${UNGROUPED:-0}" -gt "${S:-0}" ]; then
        LOOSE=$(( UNGROUPED - S ))
        echo ""
        warn "${LOOSE} clients have no reseller group and were not sold by the bot"
        info "these are the only ones not accounted for by any channel"
        info "put them in a group so accounting can bill them:"
        info "panel > Billing > All clients"
      else
        ok "every client belongs to the bot or to a reseller group"
        info "so the connection count is explained by real customers"
      fi
    else
      info "this x-ui version has no group column — per-reseller"
      info "breakdown is not available, see panel > Billing"
    fi

    # Traffic per client separates "one shared link" from "many users".
    echo ""
    echo "  ${D}Heaviest clients by traffic:${X}"
    sqlite3 -separator '|' "$XDB" \
      "SELECT email, (up+down)/1073741824 FROM client_traffics
       ORDER BY (up+down) DESC LIMIT 8;" 2>/dev/null \
      | awk -F'|' '{printf "       %-28s %6s GB\n", $1, $2}'
    info "one client far above the rest usually means a shared config"
    info "traffic spread evenly means simply many real users"
  elif [ -z "$XDB" ]; then
    info "x-ui database not found — cannot compare with panel clients"
  fi

  if [ "$TOT" -gt 2000 ]; then
    echo ""
    warn "over 2000 established connections — this is what your CPU is doing"
    info "each one costs Xray memory and scheduling time"
  fi
fi

# ═══ 8. Xray ═══
section "8. Xray"
XPID=$(pgrep -x xray 2>/dev/null | head -1)
if [ -n "$XPID" ]; then
  XFD=$(ls /proc/"$XPID"/fd 2>/dev/null | wc -l)
  XLIM=$(awk '/Max open files/{print $4}' /proc/"$XPID"/limits 2>/dev/null)
  XMEM=$(awk '/VmRSS/{print int($2/1024)}' /proc/"$XPID"/status 2>/dev/null)
  echo "  pid $XPID   memory: ${W}${XMEM:-?}MB${X}   open files: ${W}${XFD}${X} / ${XLIM:-?}"
  if [ -n "$XLIM" ] && [ "$XLIM" != "unlimited" ] && [ "${XFD:-0}" -gt 0 ]; then
    PCT=$(( XFD * 100 / XLIM ))
    if [ "$PCT" -ge 80 ]; then
      bad "file descriptors ${PCT}% used — new connections will start failing"
      info "raise LimitNOFILE in the x-ui service unit"
    elif [ "$PCT" -ge 50 ]; then
      warn "file descriptors ${PCT}% used"
    else
      ok "file descriptor headroom is fine"
    fi
  fi
else
  info "xray process not found under that name"
fi

section "What to send"
info "Copy this whole output. BAD lines come first, WARN next."
echo ""
