#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#   NEXORA — Management CLI
#   Usage:  nexora <command>
# ═══════════════════════════════════════════════════════════════

INSTALL_DIR="${NEXORA_DIR:-/opt/nexora-panel}"
SERVICE="nexora-panel"

C_RESET='\033[0m'; C_BLUE='\033[38;5;33m'; C_LBLUE='\033[38;5;39m'
C_CYAN='\033[38;5;45m'; C_GREEN='\033[38;5;41m'; C_RED='\033[38;5;196m'
C_YELLOW='\033[38;5;220m'; C_GRAY='\033[38;5;245m'; C_WHITE='\033[38;5;255m'
C_BOLD='\033[1m'; C_DIM='\033[2m'

ok()   { echo -e "  ${C_GREEN}✓${C_RESET} $1"; }
bad()  { echo -e "  ${C_RED}✗${C_RESET} $1"; }
warn() { echo -e "  ${C_YELLOW}!${C_RESET} $1"; }
info() { echo -e "  ${C_LBLUE}i${C_RESET} $1"; }

# ═══════════════════════════════════════════════════════════
#  عکس‌برداری از وضعیت فعلی
#
#  یک تابع، دو صداکننده: پیش از update و پیش از rollback.
#
#  قبلاً دو فهرست جدا بودند و فهرستِ rollback هشت مورد کم داشت —
#  از جمله bot.db. یعنی اگر بعد از rollback «بازگردانی تنظیمات» را
#  می‌زدید، دیتابیس زنده‌ی ربات با نسخه‌ی قدیمی بازنویسی می‌شد و
#  نسخه‌ی زنده هیچ‌جا ذخیره نشده بود: هر کاربر، سفارش و موجودی کیف
#  پولی که از آخرین به‌روزرسانی به بعد ساخته شده بود، برای همیشه.
#
#  با یک تابع، دو فهرست نمی‌توانند از هم فاصله بگیرند.
# ═══════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════
#  آیا بیلد واقعاً سالم است؟
#
#  «دستور موفق شد» کافی نیست. دو حالت دیده شده که هر دو خروجیِ
#  «موفق» می‌دهند و پنل را خراب بالا می‌آورند:
#
#    · باندل جاوااسکریپت خیلی کوچک — چیزی وسط بیلد شکسته
#    · CSS تقریباً خالی — Tailwind اجرا نشده، بیلد تمام شده، و پنل
#      بدون هیچ ظاهری بالا می‌آید
#
#  هر کدام از این دو در یک مسیر بررسی می‌شد و در دیگری نه: update
#  فقط JS را می‌دید و rollback فقط CSS. یعنی خرابیِ Tailwind روی
#  به‌روزرسانی — که هر ریلیز اجرا می‌شود — اصلاً گرفته نمی‌شد، و
#  فقط روی rollback که تقریباً هیچ‌وقت اجرا نمی‌شود.
#
#  با یک تابع، نصفه‌بررسی ممکن نیست.
#
#  برمی‌گرداند: ۰ سالم · ۱ خراب، با دلیل در BUILD_WHY
# ═══════════════════════════════════════════════════════════
verify_build() {
  BUILD_WHY=""
  BUILD_SIZES=""

  if [ ! -f dist/index.html ]; then
    BUILD_WHY="dist/index.html ساخته نشد"
    return 1
  fi

  JSF=$(ls -1 dist/assets/*.js 2>/dev/null | head -1)
  if [ -z "$JSF" ]; then
    BUILD_WHY="هیچ فایل جاوااسکریپتی در dist/assets نیست"
    return 1
  fi
  JSZ=$(wc -c < "$JSF" 2>/dev/null || echo 0)
  if [ "${JSZ:-0}" -lt 50000 ]; then
    BUILD_WHY="باندل جاوااسکریپت فقط ${JSZ} بایت است"
    return 1
  fi

  CSSF=$(ls -1 dist/assets/*.css 2>/dev/null | head -1)
  if [ -z "$CSSF" ]; then
    BUILD_WHY="هیچ فایل CSSی نیست — پنل بدون ظاهر بالا می‌آید"
    return 1
  fi
  CSSZ=$(wc -c < "$CSSF" 2>/dev/null || echo 0)
  if [ "${CSSZ:-0}" -lt 15000 ]; then
    BUILD_WHY="CSS فقط ${CSSZ} بایت است — Tailwind احتمالاً اجرا نشده"
    return 1
  fi

  BUILD_SIZES="JS ${JSZ}B · CSS ${CSSZ}B"
  return 0
}


snapshot_to() {
  SNAP_DEST="$1"
  SNAP_FROM="${2:-$VER}"
  mkdir -p "$SNAP_DEST/frontend"

  cp "$INSTALL_DIR/data/config.json"   "$SNAP_DEST/" 2>/dev/null
  cp "$INSTALL_DIR/data/auth.json"     "$SNAP_DEST/" 2>/dev/null
  cp "$INSTALL_DIR/sub-page-index.html" "$SNAP_DEST/" 2>/dev/null
  cp "$INSTALL_DIR/VERSION"            "$SNAP_DEST/" 2>/dev/null
  cp "$INSTALL_DIR/.github"            "$SNAP_DEST/" 2>/dev/null
  cp "$INSTALL_DIR/nexora-cli.sh"      "$SNAP_DEST/" 2>/dev/null

  cp -r "$INSTALL_DIR/backend" "$SNAP_DEST/backend" 2>/dev/null
  rm -rf "$SNAP_DEST/backend/venv" "$SNAP_DEST/backend/__pycache__" 2>/dev/null

  if [ -d "$INSTALL_DIR/bot" ]; then
    cp -r "$INSTALL_DIR/bot" "$SNAP_DEST/bot" 2>/dev/null
    rm -rf "$SNAP_DEST/bot/__pycache__" 2>/dev/null
  fi

  # داده‌ی مشتری‌ها، حسابداری و تانل‌ها — گران‌ترین چیزی که داریم
  #
  # کپی ساده‌ی فایل کافی نیست: این دیتابیس‌ها WAL دارند و هر چیزی که
  # هنوز منتقل نشده در «‎-wal» است، نه در فایل اصلی. یعنی اسنپ‌شاتِ
  # پیش از به‌روزرسانی می‌توانست ساعت‌ها سفارش و پرداخت کم داشته
  # باشد — و همان اسنپ‌شات تنها چیزی است که rollback به آن برمی‌گردد.
  for db in bot.db billing.db tunnels.db; do
    SRC="$INSTALL_DIR/data/$db"
    [ -f "$SRC" ] || continue
    if command -v sqlite3 >/dev/null 2>&1 &&
       sqlite3 "$SRC" ".backup '$SNAP_DEST/$db'" 2>/dev/null; then
      :
    else
      # بدون sqlite3: اول WAL را در فایل اصلی ادغام کن، بعد کپی.
      # اگر آن هم نشد، دست‌کم ‎-wal را همراهش ببر.
      cp "$SRC" "$SNAP_DEST/" 2>/dev/null
      [ -f "$SRC-wal" ] && cp "$SRC-wal" "$SNAP_DEST/" 2>/dev/null
      [ -f "$SRC-shm" ] && cp "$SRC-shm" "$SNAP_DEST/" 2>/dev/null
    fi
  done

  cp -r "$INSTALL_DIR/frontend/src" "$SNAP_DEST/frontend/src" 2>/dev/null
  cp "$INSTALL_DIR/frontend/package.json" "$SNAP_DEST/frontend/" 2>/dev/null
  cp "$INSTALL_DIR/frontend/.env" "$SNAP_DEST/frontend/" 2>/dev/null

  echo "$SNAP_FROM" > "$SNAP_DEST/FROM_VERSION"
}


logo() {
echo ""
echo -e "${C_BLUE}   ╔═══════════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BLUE}   ║${C_RESET}     ${C_BOLD}${C_LBLUE}N E X O R A${C_RESET}   ${C_GRAY}│${C_RESET}   ${C_WHITE}Panel Manager${C_RESET}     ${C_BLUE}║${C_RESET}"
echo -e "${C_BLUE}   ╚═══════════════════════════════════════════════╝${C_RESET}"
echo ""
}

VER=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "unknown")


# Secret admin-panel address (docs/specs/2026-09-28-admin-path-and-aff-payouts.md).
# The backend creates data/admin_path.json on first start; the panel answers
# only on https://<domain>/<path>/ — everything else on the domain is a 404.
panel_url() {
  local f="$INSTALL_DIR/data/admin_path.json" p d i
  for i in 1 2 3 4 5 6 7 8; do [ -f "$f" ] && break; sleep 1; done
  p=$(sed -n 's/.*"path": *"\([a-z0-9_-]*\)".*/\1/p' "$f" 2>/dev/null)
  d=$(sed -n 's/^VITE_API_URL=//p' "$INSTALL_DIR/frontend/.env" 2>/dev/null | tr -d '\r')
  [ -n "$p" ] && echo "${d:-https://<your-domain>}/$p/"
}

case "$1" in

  url)
    logo
    U=$(panel_url)
    if [ -n "$U" ]; then
      echo -e "  ${C_DIM}Admin panel${C_RESET}  ${C_LBLUE}$U${C_RESET}"
      echo ""
      echo -e "  ${C_DIM}Only this address opens the panel — the bare domain shows 404.${C_RESET}"
      echo -e "  ${C_DIM}Do not share it with resellers or affiliates; they have their own links.${C_RESET}"
    else
      bad "Admin address not created yet — is the service running?  nexora status"
    fi
    echo ""
    ;;

  status)
    logo
    echo -e "  ${C_DIM}Version${C_RESET}  ${C_WHITE}$VER${C_RESET}"
    echo ""
    if systemctl is-active --quiet $SERVICE; then
      ok "Backend service:  running"
    else
      bad "Backend service:  stopped"
    fi
    if curl -s --max-time 4 http://127.0.0.1:8100/api/health 2>/dev/null | grep -q '"ok":true'; then
      ok "API health:       responding"
    else
      bad "API health:       no response"
    fi
    if systemctl is-active --quiet nginx; then ok "nginx:            running"; else bad "nginx:            stopped"; fi
    if systemctl is-active --quiet x-ui; then ok "x-ui panel:       running"; else warn "x-ui panel:       not running"; fi
    echo ""
    for d in /root/sub-page /etc/x-ui/sub-page; do
      [ -f "$d/index.html" ] && info "Template: $d/index.html ($(stat -c%s "$d/index.html") bytes)"
    done
    echo ""
    ;;

  logs)
    journalctl -u $SERVICE -f --no-pager
    ;;

  restart)
    logo
    systemctl restart $SERVICE && ok "Service restarted" || bad "Restart failed"
    sleep 3
    curl -s --max-time 4 http://127.0.0.1:8100/api/health 2>/dev/null | grep -q '"ok":true' \
      && ok "API responding" || bad "API not responding — run: nexora logs"
    echo ""
    ;;

  stop)
    systemctl stop $SERVICE && ok "Service stopped"
    ;;

  start)
    systemctl start $SERVICE && ok "Service started"
    ;;

  backup)
    # The whole panel in one zip, the same file as Settings → backup
    # (docs/specs/2026-10-01-admin-bot-backup-ui.md). It used to copy
    # config.json alone: no customers, no accounting, no receipts.
    logo
    BOT_DB_PATH="$INSTALL_DIR/data/bot.db" BILLING_DB_PATH="$INSTALL_DIR/data/billing.db" \
    TUNNEL_DB_PATH="$INSTALL_DIR/data/tunnels.db" \
      "$INSTALL_DIR/backend/venv/bin/python" "$INSTALL_DIR/scripts/full-backup.py" backup \
      --data "$INSTALL_DIR/data" --out /root/backups \
      || bad "Backup failed (see the message above)"
    echo ""
    ;;

  restore)
    logo
    if [ -z "$2" ]; then
      bad "Usage: nexora restore /root/backups/nexora-backup-....zip"
      exit 1
    fi
    # Stopped first: a restore under a bot that is writing orders would mix
    # the two states.
    systemctl stop nexora-bot 2>/dev/null
    systemctl stop $SERVICE 2>/dev/null
    BOT_DB_PATH="$INSTALL_DIR/data/bot.db" BILLING_DB_PATH="$INSTALL_DIR/data/billing.db" \
    TUNNEL_DB_PATH="$INSTALL_DIR/data/tunnels.db" \
      "$INSTALL_DIR/backend/venv/bin/python" "$INSTALL_DIR/scripts/full-backup.py" restore "$2" \
      --data "$INSTALL_DIR/data"
    RC=$?
    systemctl start $SERVICE 2>/dev/null
    systemctl start nexora-bot 2>/dev/null
    [ $RC -eq 0 ] && ok "Panel and bot started again" || bad "Restore did not run; services started again unchanged"
    echo ""
    ;;

  update)
    logo
    echo -e "  ${C_BOLD}Update Nexora Panel${C_RESET}"
    echo ""

    ZIP="$2"

    # اگر فایلی داده نشده، از گیت‌هاب دانلود می‌کنیم
    if [ -z "$ZIP" ]; then
      if [ -f "$INSTALL_DIR/.github" ]; then
        # shellcheck disable=SC1090
        source "$INSTALL_DIR/.github"
      fi

      if [ -z "$GITHUB_REPO" ]; then
        echo -e "  ${C_DIM}Two ways to update:${C_RESET}"
        echo ""
        echo -e "  ${C_WHITE}1)${C_RESET} From a local file:"
        echo -e "     ${C_DIM}nexora update /root/nexora-panel.zip${C_RESET}"
        echo ""
        echo -e "  ${C_WHITE}2)${C_RESET} Automatically from GitHub — set it up once:"
        echo -e "     ${C_DIM}echo 'GITHUB_REPO=\"user/repo\"' > $INSTALL_DIR/.github${C_RESET}"
        echo -e "     ${C_DIM}then just run:  nexora update${C_RESET}"
        echo ""
        exit 1
      fi

      info "Checking GitHub for the latest release..."
      AUTH_HEADER=""
      [ -n "$GITHUB_TOKEN" ] && AUTH_HEADER="-H \"Authorization: token $GITHUB_TOKEN\""

      API="https://api.github.com/repos/$GITHUB_REPO/releases/latest"
      if [ -n "$GITHUB_TOKEN" ]; then
        REL=$(curl -sL -H "Authorization: token $GITHUB_TOKEN" "$API")
      else
        REL=$(curl -sL "$API")
      fi

      TAG=$(echo "$REL" | grep -o '"tag_name": *"[^"]*"' | head -1 | sed 's/.*: *"//;s/"//')
      if [ -z "$TAG" ]; then
        bad "Could not reach GitHub or no release found"
        info "Repo: $GITHUB_REPO"
        echo ""
        exit 1
      fi

      if [ "$TAG" = "v$VER" ] || [ "$TAG" = "$VER" ]; then
        ok "Already on the latest version ($VER)"
        echo ""
        exit 0
      fi

      info "New version available: $TAG  (current: $VER)"
      ZIP="/tmp/nexora-$TAG.zip"
      DL="https://github.com/$GITHUB_REPO/archive/refs/tags/$TAG.zip"

      if [ -n "$GITHUB_TOKEN" ]; then
        curl -sL -H "Authorization: token $GITHUB_TOKEN" -o "$ZIP" "$DL"
      else
        curl -sL -o "$ZIP" "$DL"
      fi

      [ ! -s "$ZIP" ] && { bad "Download failed"; echo ""; exit 1; }
      ok "Downloaded $(du -h "$ZIP" | cut -f1)"
    fi

    [ ! -f "$ZIP" ] && { bad "File not found: $ZIP"; echo ""; exit 1; }

    # 1) Full snapshot so we can roll back if the new version misbehaves
    TS=$(date +%Y%m%d-%H%M%S)
    SNAP="/root/nexora-snapshots/$TS"
    mkdir -p "$SNAP"

    snapshot_to "$SNAP"

    # keep only the 5 most recent snapshots
    ls -1dt /root/nexora-snapshots/*/ 2>/dev/null | tail -n +6 | xargs rm -rf 2>/dev/null

    ok "Snapshot saved → $SNAP"
    info "You can roll back anytime with:  nexora rollback"

    # 2) Read current settings so we can restore them
    API_URL=$(grep -o 'const SUBPAGE_CONFIG_API = "[^"]*"' "$INSTALL_DIR/sub-page-index.html" 2>/dev/null | head -1 | sed 's/.*= "//;s/"//')
    VITE_URL=$(grep VITE_API_URL "$INSTALL_DIR/frontend/.env" 2>/dev/null | cut -d= -f2)
    SUBPAGE_PATH=$(grep -o 'SUBPAGE_HTML_PATH=[^"]*' /etc/systemd/system/nexora-panel.service 2>/dev/null | cut -d= -f2)
    [ -z "$SUBPAGE_PATH" ] && SUBPAGE_PATH="/root/sub-page/index.html"
    info "Preserving API URL: $API_URL"

    # 3) Extract new version
    TMP="/tmp/nexora-update-$TS"
    mkdir -p "$TMP"
    unzip -q -o "$ZIP" -d "$TMP" || { bad "Failed to extract zip"; exit 1; }
    SRC=$(find "$TMP" -name "sub-page-index.html" -exec dirname {} \; | head -1)
    [ -z "$SRC" ] && { bad "Invalid package — sub-page-index.html not found"; exit 1; }
    ok "Package extracted"

    # 4) Replace code, keep data
    #
    # همه‌چیز به‌جز پوشه‌های داده‌ای کپی می‌شود. لیست هاردکد نداریم،
    # چون همان باعث شد پوشه‌ی bot/ در یک نسخه جا بماند. فقط با cp
    # کار می‌کنیم تا روی سرورهای بدون rsync هم مطمئن باشد.
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

    if [ -d "$INSTALL_DIR/bot" ]; then
      BOTN=$(ls -1 "$INSTALL_DIR/bot"/*.py 2>/dev/null | wc -l)
      if [ "$BOTN" -gt 0 ]; then
        ok "Bot module: $BOTN files"
      else
        bad "Bot module copy failed"
      fi
    fi

    # دستور nexora — تا دفعه‌ی بعد کامل باشد
    if [ -f "$INSTALL_DIR/nexora-cli.sh" ]; then
      cp "$INSTALL_DIR/nexora-cli.sh" /usr/local/bin/nexora.new
      chmod +x /usr/local/bin/nexora.new
      mv -f /usr/local/bin/nexora.new /usr/local/bin/nexora
      ok "CLI updated"
    fi

    ok "Code updated (your settings were not touched)"

    # 4b) The Pro package for the new version, licensed servers only. Pro code
    # calls core names, so a package only fits the core it was cut with; it is
    # fetched before the build, so the new panel is built with it. A failure
    # never stops the update: the free edition keeps working and says why.
    if [ -f "$INSTALL_DIR/scripts/pro-fetch.py" ]; then
      if ! python3 "$INSTALL_DIR/scripts/pro-fetch.py" --root "$INSTALL_DIR" --if-licensed; then
        warn "The Pro package for this version was not installed (reason above)."
        warn "The free edition keeps working. Retry later with:  nexora pro"
      fi
    fi

    # 5) Restore API URL into the template
    if [ -n "$API_URL" ]; then
      sed -i "s|const SUBPAGE_CONFIG_API = \"[^\"]*\"|const SUBPAGE_CONFIG_API = \"$API_URL\"|" "$INSTALL_DIR/sub-page-index.html"
      ok "API URL restored"
    fi

    # 6) Deploy template
    cp "$INSTALL_DIR/sub-page-index.html" "$SUBPAGE_PATH"
    chmod 644 "$SUBPAGE_PATH"
    ok "Template deployed → $SUBPAGE_PATH"

    # 7) Rebuild
    #
    # مهم: خروجی بیلد را پنهان نمی‌کنیم. اگر بیلد شکست بخورد و دلیلش
    # را نگوییم، کاربر پنل قدیمی می‌بیند و فکر می‌کند به‌روزرسانی
    # کار نکرده — بدون هیچ سرنخی.
    info "Rebuilding admin panel..."
    cd "$INSTALL_DIR/frontend"
    [ -n "$VITE_URL" ] && echo "VITE_API_URL=$VITE_URL" > .env
    export NODE_OPTIONS="--max-old-space-size=1536"

    # swap موقت برای سرورهای کم‌حافظه — بدون آن بیلد بی‌صدا کشته می‌شود
    MEM=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
    SWP=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
    if [ -n "$MEM" ] && [ $((MEM + SWP)) -lt 1500 ] && [ ! -f /swapfile ]; then
      info "Low memory — creating temporary swap"
      fallocate -l 2G /swapfile 2>/dev/null && chmod 600 /swapfile && \
        mkswap /swapfile > /dev/null 2>&1 && swapon /swapfile > /dev/null 2>&1
    fi

    BUILD_LOG="/tmp/nexora-build.log"

    # بیلد قبلی را نگه می‌داریم. اگر بیلد جدید خراب باشد، به‌جای
    # اینکه پنل صفحه‌ی سفید شود، نسخه‌ی سالم قبلی برمی‌گردد.
    [ -d dist ] && rm -rf dist.prev && cp -r dist dist.prev 2>/dev/null

    npm install --no-fund --no-audit --loglevel=error > "$BUILD_LOG" 2>&1
    npm run build >> "$BUILD_LOG" 2>&1
    BUILD_RC=$?

    # اعتبارسنجی خروجی — فقط «موفق بودن دستور» کافی نیست
    BUILD_OK=0
    if [ $BUILD_RC -eq 0 ] && verify_build; then
      BUILD_OK=1
    fi

    if [ $BUILD_OK -eq 1 ]; then
      rm -rf dist.prev
      ok "Admin panel rebuilt  ($BUILD_SIZES)"
    else
      bad "Build failed${BUILD_WHY:+ — $BUILD_WHY}"
      echo ""
      echo -e "  ${C_DIM}Last lines of the build log:${C_RESET}"
      tail -20 "$BUILD_LOG" 2>/dev/null | sed 's/^/      /'
      echo ""

      if [ -d dist.prev ]; then
        rm -rf dist && mv dist.prev dist
        warn "Previous panel restored — you can still use it"
      fi
      # کدِ تازه (و VERSIONِ تازه) از قبل جایگزین شده بود. بی این خط،
      # «nexora update»ِ بعدی می‌گفت «آخرین نسخه‌اید» و دیگر امتحان
      # نمی‌کرد — پنل با بیلدِ قدیمی می‌ماند و مالک «چیز جدیدی نیامد» می‌دید.
      [ -n "$VER" ] && [ "$VER" != "unknown" ] && echo "$VER" > "$INSTALL_DIR/VERSION"
      warn "Version marker reset to $VER — run  nexora update  again after fixing the cause"
      warn "Full log:  $BUILD_LOG"
      warn "Roll back with:  nexora rollback"
      exit 1
    fi

    # 8) Restart
    cd "$INSTALL_DIR/backend"
    ./venv/bin/pip install -r requirements.txt -q > /dev/null 2>&1

    # ربات: وابستگی‌ها و سرویس (اگر ماژول موجود باشد)
    if [ -d "$INSTALL_DIR/bot" ]; then
      ./venv/bin/pip install -r "$INSTALL_DIR/bot/requirements.txt" -q > /dev/null 2>&1

      if [ ! -f /etc/systemd/system/nexora-bot.service ]; then
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
        ok "Bot service created (start with: nexora bot enable)"
      else
        systemctl daemon-reload
        # اگر ربات از قبل در حال اجرا بود، با کد جدید ری‌استارت شود
        if systemctl is-active --quiet nexora-bot; then
          systemctl restart nexora-bot
          ok "Bot restarted with the new code"
        fi
      fi
    fi

    # هدرهای ضدکش nginx — بدون این، مرورگر بعد از به‌روزرسانی
    # همچنان فایل‌های قدیمی را می‌خواهد
    [ -f "$INSTALL_DIR/scripts/fix-nginx-cache.py" ] && \
      python3 "$INSTALL_DIR/scripts/fix-nginx-cache.py" > /dev/null 2>&1

    systemctl restart $SERVICE
    sleep 4

    if curl -s --max-time 5 http://127.0.0.1:8100/api/health 2>/dev/null | grep -q '"ok":true'; then
      ok "Service restarted successfully"
      systemctl is-active --quiet x-ui && { x-ui restart > /dev/null 2>&1; ok "x-ui restarted"; }
      NEWVER=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "?")
      rm -rf "$TMP"
      echo ""

      # بررسی واقعی: آیا نسخه عوض شد؟ اگر نه، محتوای دانلودشده قدیمی بوده.
      if [ "$NEWVER" = "$VER" ]; then
        warn "Version did not change ($VER)"
        echo ""
        info "The downloaded package contained the same version."
        info "This usually means the GitHub release tag points to an older commit."
        echo ""
        echo -e "  ${C_WHITE}How to fix:${C_RESET}"
        echo -e "    1. Make sure the new files are pushed to GitHub"
        echo -e "    2. Delete the release, then create it again with the same tag"
        echo -e "    3. Run ${C_WHITE}nexora update${C_RESET} again"
        echo ""
        echo -e "  ${C_DIM}Or update directly from a local file:${C_RESET}"
        echo -e "    ${C_WHITE}nexora update /path/to/package.zip${C_RESET}"
        echo ""
      else
        echo -e "  ${C_GREEN}${C_BOLD}UPDATE COMPLETE${C_RESET}   ${C_DIM}$VER → $NEWVER${C_RESET}"
        echo ""
        # since 1.129 the panel lives behind a secret path — say where, every time
        U=$(panel_url)
        [ -n "$U" ] && echo -e "  ${C_DIM}Admin panel${C_RESET}  ${C_LBLUE}$U${C_RESET}   ${C_DIM}(nexora url)${C_RESET}" && echo ""
      fi
    else
      bad "Service failed after update"
      warn "Roll back with:  nexora rollback"
      warn "Check logs:  nexora logs"
      echo ""
      exit 1
    fi
    ;;

  pro)
    # Install (or re-install) the Pro package for this version and license,
    # then rebuild and restart so it loads. The System page's "install the Pro
    # package" button runs this and reads its log.
    logo
    echo -e "  ${C_BOLD}Install the Pro package${C_RESET}"
    echo ""
    python3 "$INSTALL_DIR/scripts/pro-fetch.py" --root "$INSTALL_DIR"
    RC=$?
    if [ $RC -ne 0 ]; then
      bad "Pro package not installed"
      echo ""
      exit 1
    fi
    bash "$0" rebuild || { bad "Build failed; the Pro package is in place, run: nexora rebuild"; exit 1; }
    systemctl restart $SERVICE
    systemctl is-active --quiet nexora-bot && systemctl restart nexora-bot
    sleep 4
    if curl -s --max-time 5 http://127.0.0.1:8100/api/health 2>/dev/null | grep -q '"ok":true'; then
      ok "Services restarted"
      echo ""
      echo -e "  ${C_GREEN}${C_BOLD}PRO INSTALL COMPLETE${C_RESET}"
      echo ""
    else
      bad "The panel did not come back after the restart"
      warn "Check logs:  nexora logs"
      exit 1
    fi
    ;;

  rebuild)
    logo
    echo -e "  ${C_BOLD}Rebuild Admin Panel${C_RESET}"
    echo ""

    # --- Pre-flight checks ---
    NODE_V=$(node --version 2>/dev/null)
    NODE_MAJOR=$(echo "$NODE_V" | sed 's/v//' | cut -d. -f1)
    if [ -z "$NODE_V" ]; then
      bad "Node.js is not installed"
      echo ""; exit 1
    elif [ "$NODE_MAJOR" -lt 20 ] 2>/dev/null; then
      warn "Node.js $NODE_V — version 20+ recommended"
      info "Upgrade:  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && apt install -y nodejs"
      echo ""
    else
      ok "Node.js $NODE_V"
    fi

    MEM=$(free -m | awk '/^Mem:/{print $2}')
    SWP=$(free -m | awk '/^Swap:/{print $2}')
    TOTAL=$((MEM + SWP))
    if [ "$TOTAL" -lt 1500 ]; then
      warn "Only ${TOTAL}MB memory available — build may fail"
      info "Creating temporary swap..."
      if [ ! -f /swapfile ]; then
        fallocate -l 2G /swapfile 2>/dev/null && chmod 600 /swapfile && mkswap /swapfile > /dev/null 2>&1 && swapon /swapfile > /dev/null 2>&1 \
          && ok "2GB swap enabled"
      else
        swapon /swapfile 2>/dev/null && ok "Existing swap activated"
      fi
    else
      ok "Memory: ${MEM}MB RAM + ${SWP}MB swap"
    fi

    DISK=$(df -m "$INSTALL_DIR" 2>/dev/null | awk 'NR==2{print $4}')
    if [ -n "$DISK" ] && [ "$DISK" -lt 1000 ]; then
      warn "Only ${DISK}MB free disk space"
    else
      ok "Disk space: ${DISK}MB free"
    fi

    echo ""
    cd "$INSTALL_DIR/frontend" || { bad "Frontend folder not found"; exit 1; }
    export NODE_OPTIONS="--max-old-space-size=1536"

    info "Installing packages..."
    npm install --no-fund --no-audit --loglevel=error 2>&1 | tail -3
    [ ! -d node_modules ] && { bad "npm install failed"; echo ""; exit 1; }
    ok "Packages ready"

    info "Building (this takes 1-3 minutes)..."
    LOG=/tmp/nexora-rebuild.log
    [ -d dist ] && rm -rf dist.prev && cp -r dist dist.prev 2>/dev/null
    npm run build > "$LOG" 2>&1
    RC=$?
    JSFILE=$(ls -1 dist/assets/*.js 2>/dev/null | head -1)
    JSSIZE=$([ -n "$JSFILE" ] && stat -c%s "$JSFILE" 2>/dev/null || echo 0)
    if [ $RC -eq 0 ] && [ -f dist/index.html ] && [ "$JSSIZE" -gt 50000 ]; then
      rm -rf dist.prev
      ok "Build successful ($(du -sh dist | cut -f1))"
      systemctl reload nginx 2>/dev/null
      echo ""
      echo -e "  ${C_GREEN}${C_BOLD}DONE${C_RESET}  ${C_DIM}Refresh your browser${C_RESET}"
      echo ""
    else
      bad "Build failed"
      echo ""
      tail -20 "$LOG" | sed 's/^/      /'
      echo ""
      grep -qi "heap out of memory\|killed" "$LOG" && warn "Out of memory — add more swap"
      grep -qi "unsupported engine\|EBADENGINE" "$LOG" && warn "Node.js version too old — upgrade to v20+"
      echo ""
      exit 1
    fi
    ;;

  rollback)
    # حالت غیرتعاملی برای فراخوانی از پنل:
    #   nexora rollback <snapshot> --yes --settings=yes|no
    NONINT=""
    ROLL_TARGET=""
    ROLL_SETTINGS="no"
    for a in "$@"; do
      case "$a" in
        --yes) NONINT="1" ;;
        --settings=yes) ROLL_SETTINGS="yes" ;;
        --settings=no)  ROLL_SETTINGS="no" ;;
        rollback) ;;
        *) [ -z "$ROLL_TARGET" ] && ROLL_TARGET="$a" ;;
      esac
    done

    logo
    echo -e "  ${C_BOLD}Roll Back to a Previous Version${C_RESET}"
    echo ""

    SNAPDIR="/root/nexora-snapshots"
    if [ ! -d "$SNAPDIR" ] || [ -z "$(ls -A "$SNAPDIR" 2>/dev/null)" ]; then
      bad "No snapshots found"
      info "Snapshots are created automatically before each update."
      echo ""
      exit 1
    fi

    # List snapshots, newest first
    mapfile -t SNAPS < <(ls -1dt "$SNAPDIR"/*/ 2>/dev/null)
    echo -e "  ${C_WHITE}Available snapshots:${C_RESET}"
    echo ""
    for i in "${!SNAPS[@]}"; do
      S="${SNAPS[$i]}"
      NAME=$(basename "$S")
      FROMV=$(cat "$S/FROM_VERSION" 2>/dev/null || echo "?")
      DATE=$(echo "$NAME" | sed 's/\(....\)\(..\)\(..\)-\(..\)\(..\)\(..\)/\1-\2-\3 \4:\5/')
      echo -e "    ${C_LBLUE}$((i+1))${C_RESET})  ${C_WHITE}v$FROMV${C_RESET}   ${C_DIM}$DATE${C_RESET}"
    done
    echo ""
    if [ -n "$NONINT" ]; then
      PICK=""
      for i in "${!SNAPS[@]}"; do
        [ "$(basename "${SNAPS[$i]}")" = "$ROLL_TARGET" ] && PICK=$((i + 1))
      done
      if [ -z "$PICK" ]; then
        bad "Snapshot not found: $ROLL_TARGET"
        echo ""; exit 1
      fi
    else
      read -p "$(echo -e "  ${C_WHITE}Which snapshot? [1-${#SNAPS[@]}, or 0 to cancel]${C_RESET}: ")" PICK
    fi

    [ "$PICK" = "0" ] || [ -z "$PICK" ] && { echo ""; info "Cancelled"; echo ""; exit 0; }
    if ! [ "$PICK" -ge 1 ] 2>/dev/null || [ "$PICK" -gt "${#SNAPS[@]}" ]; then
      bad "Invalid choice"; echo ""; exit 1
    fi

    TARGET="${SNAPS[$((PICK-1))]}"
    TARGET="${TARGET%/}"
    TARGETV=$(cat "$TARGET/FROM_VERSION" 2>/dev/null || echo "?")

    echo ""
    warn "This will replace the current version ($VER) with v$TARGETV"
    if [ -n "$NONINT" ]; then CONF="yes"; else
      read -p "$(echo -e "  ${C_WHITE}Type 'yes' to confirm${C_RESET}: ")" CONF
    fi
    [ "$CONF" != "yes" ] && { echo ""; info "Cancelled"; echo ""; exit 0; }

    # Snapshot the CURRENT state first, so rollback itself is reversible
    NOWTS=$(date +%Y%m%d-%H%M%S)
    PRE="$SNAPDIR/$NOWTS"
    snapshot_to "$PRE"
    ok "Current state saved (in case you want to come back)"

    echo ""
    info "Restoring v$TARGETV..."

    # Keep the live settings unless the user wants the old ones too
    echo ""
    if [ -n "$NONINT" ]; then
      RESTORE_CFG="$([ "$ROLL_SETTINGS" = "yes" ] && echo "y" || echo "n")"
    else
      read -p "$(echo -e "  ${C_WHITE}Also restore settings from that snapshot? [y/N]${C_RESET}: ")" RESTORE_CFG
    fi

    # --- Restore code ---
    [ -d "$TARGET/backend" ] && {
      find "$INSTALL_DIR/backend" -maxdepth 1 -type f -delete 2>/dev/null
      cp "$TARGET/backend/"*.py "$TARGET/backend/"*.txt "$INSTALL_DIR/backend/" 2>/dev/null
    }
    [ -d "$TARGET/frontend/src" ] && {
      rm -rf "$INSTALL_DIR/frontend/src"
      cp -r "$TARGET/frontend/src" "$INSTALL_DIR/frontend/"
    }
    [ -d "$TARGET/bot" ] && {
      mkdir -p "$INSTALL_DIR/bot"
      rm -rf "$INSTALL_DIR/bot/__pycache__"
      cp "$TARGET/bot/"*.py "$TARGET/bot/"*.txt "$INSTALL_DIR/bot/" 2>/dev/null
    }
    [ -f "$TARGET/frontend/package.json" ] && cp "$TARGET/frontend/package.json" "$INSTALL_DIR/frontend/"
    [ -f "$TARGET/sub-page-index.html" ] && cp "$TARGET/sub-page-index.html" "$INSTALL_DIR/"
    [ -f "$TARGET/VERSION" ] && cp "$TARGET/VERSION" "$INSTALL_DIR/"

    # CLI هم باید به همان نسخه برگردد
    if [ -f "$TARGET/nexora-cli.sh" ]; then
      cp "$TARGET/nexora-cli.sh" "$INSTALL_DIR/"
      chmod +x "$INSTALL_DIR/nexora-cli.sh"
      cp "$INSTALL_DIR/nexora-cli.sh" /usr/local/bin/nexora.new
      chmod +x /usr/local/bin/nexora.new
      mv -f /usr/local/bin/nexora.new /usr/local/bin/nexora
    fi
    ok "Code restored"

    # --- Restore settings if asked ---
    if [[ "$RESTORE_CFG" =~ ^[Yy]$ ]]; then
      [ -f "$TARGET/config.json" ] && cp "$TARGET/config.json" "$INSTALL_DIR/data/" && ok "Settings restored"
      [ -f "$TARGET/auth.json" ] && cp "$TARGET/auth.json" "$INSTALL_DIR/data/" && ok "Password restored"
      # گذاشتن یک bot.db کنار ‎-wal قدیمیِ همان مسیر خطرناک است:
      # SQLite ممکن است آن WAL را روی فایل تازه اعمال کند. پس قبل از
      # کپی، فایل‌های جانبیِ مقصد برداشته می‌شوند و اگر اسنپ‌شات خودش
      # ‎-wal داشت، همراهش می‌آید.
      restore_db() {
        RDB="$1"
        [ -f "$TARGET/$RDB" ] || return 1
        rm -f "$INSTALL_DIR/data/$RDB-wal" "$INSTALL_DIR/data/$RDB-shm"
        cp "$TARGET/$RDB" "$INSTALL_DIR/data/" || return 1
        [ -f "$TARGET/$RDB-wal" ] && cp "$TARGET/$RDB-wal" "$INSTALL_DIR/data/"
        [ -f "$TARGET/$RDB-shm" ] && cp "$TARGET/$RDB-shm" "$INSTALL_DIR/data/"
        return 0
      }

      # هر سرویسی که این فایل‌ها را باز نگه داشته باید *پیش از*
      # جابه‌جایی‌شان بایستد.
      #
      # ربات درست متوقف می‌شد، پنل نه — در حالی که billing.db و
      # tunnels.db را همان پنل باز نگه داشته. کپی‌کردن روی دیتابیسی
      # که یک پروسه‌ی زنده بازش دارد، با WALش و صفحه‌های کش‌شده‌اش،
      # همان کاری است که SQLite صریح می‌گوید نکنید. و پنجره‌اش کوتاه
      # نیست: بازسازی فرانت‌اند بین این‌جا و ری‌استارت چند دقیقه طول
      # می‌کشد، و در تمام آن مدت پنل روی فایلِ عوض‌شده کار می‌کند و
      # می‌تواند همان بازگردانی را بازنویسی کند.
      #
      # trap لازم است چون بین این‌جا و ری‌استارت دو مسیرِ exit هست
      # (شکست بازسازی، و CSS کوچک). بدون آن، یک بازسازیِ ناموفق پنل
      # را خاموش جا می‌گذاشت.
      ROLL_DOWN="1"
      roll_bring_up() {
        [ -n "$ROLL_DOWN" ] || return 0
        ROLL_DOWN=""
        systemctl start $SERVICE 2>/dev/null
        systemctl is-enabled --quiet nexora-bot 2>/dev/null &&
          systemctl start nexora-bot 2>/dev/null
      }
      trap roll_bring_up EXIT
      systemctl stop nexora-bot 2>/dev/null
      systemctl stop $SERVICE 2>/dev/null

      [ -f "$TARGET/bot.db" ] && restore_db bot.db && ok "Bot database restored"
      restore_db billing.db && ok "Billing data restored"
      restore_db tunnels.db && ok "Tunnel data restored"
    else
      info "Current settings kept"
    fi

    # --- Redeploy template ---
    SUBPAGE_PATH=$(grep -o 'SUBPAGE_HTML_PATH=[^"]*' /etc/systemd/system/nexora-panel.service 2>/dev/null | cut -d= -f2)
    [ -z "$SUBPAGE_PATH" ] && SUBPAGE_PATH="/root/sub-page/index.html"
    cp "$INSTALL_DIR/sub-page-index.html" "$SUBPAGE_PATH" 2>/dev/null && chmod 644 "$SUBPAGE_PATH"
    ok "Template redeployed"

    # --- Rebuild ---
    info "Rebuilding admin panel..."
    cd "$INSTALL_DIR/frontend"
    export NODE_OPTIONS="--max-old-space-size=1536"
    npm install --no-fund --no-audit --loglevel=error > /dev/null 2>&1
    if npm run build > /tmp/nexora-rollback.log 2>&1; then
      if ! verify_build; then
        bad "Build unusable — $BUILD_WHY"
        info "Restoring previous build"
        [ -d dist.prev ] && rm -rf dist && mv dist.prev dist
        exit 1
      fi
      ok "Panel rebuilt ($BUILD_SIZES)"
    else
      bad "Rebuild failed — see /tmp/nexora-rollback.log"
      [ -d dist.prev ] && rm -rf dist && mv dist.prev dist && info "Previous build restored"
      exit 1
    fi

    # --- Restart ---
    cd "$INSTALL_DIR/backend"
    ./venv/bin/pip install -r requirements.txt -q > /dev/null 2>&1
    systemctl restart $SERVICE
    systemctl is-enabled --quiet nexora-bot 2>/dev/null && systemctl restart nexora-bot 2>/dev/null
    ROLL_DOWN=""        # از این‌جا به بعد سرویس‌ها بالا هستند
    sleep 4

    if curl -s --max-time 5 http://127.0.0.1:8100/api/health 2>/dev/null | grep -q '"ok":true'; then
      systemctl is-active --quiet x-ui && x-ui restart > /dev/null 2>&1
      echo ""
      echo -e "  ${C_GREEN}${C_BOLD}ROLLBACK COMPLETE${C_RESET}   ${C_DIM}$VER → v$TARGETV${C_RESET}"
      echo ""
      info "To go back forward, run 'nexora rollback' and pick the newest snapshot"
      echo ""
    else
      bad "Service did not start after rollback"
      warn "Check logs:  nexora logs"
      echo ""
      exit 1
    fi
    ;;

  snapshots)
    logo
    SNAPDIR="/root/nexora-snapshots"
    if [ ! -d "$SNAPDIR" ] || [ -z "$(ls -A "$SNAPDIR" 2>/dev/null)" ]; then
      info "No snapshots yet — one is created automatically before each update"
      echo ""
      exit 0
    fi
    echo -e "  ${C_WHITE}Saved snapshots${C_RESET}  ${C_DIM}(newest first, max 5 kept)${C_RESET}"
    echo ""
    for S in $(ls -1dt "$SNAPDIR"/*/ 2>/dev/null); do
      NAME=$(basename "$S")
      FROMV=$(cat "$S/FROM_VERSION" 2>/dev/null || echo "?")
      SIZE=$(du -sh "$S" 2>/dev/null | cut -f1)
      DATE=$(echo "$NAME" | sed 's/\(....\)\(..\)\(..\)-\(..\)\(..\)\(..\)/\1-\2-\3 \4:\5/')
      echo -e "  ${C_GRAY}•${C_RESET} ${C_WHITE}v$FROMV${C_RESET}  ${C_DIM}$DATE  ($SIZE)${C_RESET}"
    done
    echo ""
    info "Restore one with:  nexora rollback"
    echo ""
    ;;

  fix-xui)
    # مسیر دیتابیس x-ui را هم در سرویس و هم در تنظیمات پنل می‌گذارد.
    # دو جا، چون اگر یکی به هر دلیل نخواند، دیگری کار می‌کند.
    NEWPATH="${2:-}"

    if [ -z "$NEWPATH" ]; then
    echo -e "${C_DIM}Looking for the x-ui database...${C_RESET}"
      for p in /etc/x-ui/x-ui.db /usr/local/x-ui/x-ui.db /opt/x-ui/x-ui.db /etc/x-ui/db/x-ui.db; do
        [ -f "$p" ] && { NEWPATH="$p"; break; }
      done
      [ -z "$NEWPATH" ] && NEWPATH=$(find / -name "x-ui.db" -not -path "*/proc/*" 2>/dev/null | head -1)
    fi

    if [ -z "$NEWPATH" ] || [ ! -f "$NEWPATH" ]; then
      err "دیتابیس x-ui پیدا نشد"
    info "Pass it yourself: nexora fix-xui /path/to/x-ui.db"
      exit 1
    fi

    ok "Found: $NEWPATH"

    # مجوز خواندن — فایل اصلی و فایل‌های جانبی WAL
    #
    # اگر x-ui در حالت WAL باشد، فایل‌های -wal و -shm هم لازم‌اند و
    # بدون آن‌ها SQLite کل دیتابیس را باز نمی‌کند.
    FIXED=0
    for f in "$NEWPATH" "$NEWPATH-wal" "$NEWPATH-shm" "$NEWPATH-journal"; do
      if [ -f "$f" ] && [ ! -r "$f" ]; then
        chmod +r "$f" 2>/dev/null && { ok "mode fixed: $(basename "$f")"; FIXED=1; }
      fi
    done
    [ "$FIXED" = "0" ] && ok "Permissions were already fine"

    # پوشه هم باید قابل ورود باشد
    chmod o+x "$(dirname "$NEWPATH")" 2>/dev/null

    if [ -f "$NEWPATH-wal" ]; then
      info "WAL mode is on — the -wal and -shm files must stay readable"
    fi

    # ۱. در سرویس
    SVC="/etc/systemd/system/nexora-panel.service"
    if [ -f "$SVC" ]; then
      if grep -q "XUI_DB_PATH=" "$SVC"; then
        sed -i "s|Environment=\"XUI_DB_PATH=.*\"|Environment=\"XUI_DB_PATH=$NEWPATH\"|" "$SVC"
      else
        sed -i "/^\[Service\]/a Environment=\"XUI_DB_PATH=$NEWPATH\"" "$SVC"
      fi
      systemctl daemon-reload
      ok "Service updated"
    fi

    # ۲. در تنظیمات پنل
    CFG="$INSTALL_DIR/data/config.json"
    if [ -f "$CFG" ]; then
      python3 - "$CFG" "$NEWPATH" <<'PY'
import json, sys
p, path = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(p, encoding="utf-8"))
except Exception:
    d = {}
if not isinstance(d, dict):
    d = {}
adv = d.get("advanced")
if not isinstance(adv, dict):
    adv = d["advanced"] = {}
adv["xuiDbPath"] = path
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
      ok "Saved to panel settings"
    fi

    systemctl restart nexora-panel 2>/dev/null && ok "Panel restarted"
    echo
    ok "Accounting can read x-ui now"
    ;;

  check|diagnose)
    # گزارش کامل: نسخه‌ها، صف کارها، دید فایروال، حسابداری، ربات.
    # وقتی چیزی کار نمی‌کند، این اولین چیزی است که باید اجرا شود.
    if [ -f "$INSTALL_DIR/scripts/nexora-doctor.sh" ]; then
      bash "$INSTALL_DIR/scripts/nexora-doctor.sh" "${2:-}"
    else
      err "scripts/nexora-doctor.sh not found — run: nexora update"
      exit 1
    fi
    ;;

  reseller|nemayande)
    # حساب پنل نماینده — تا لازم نباشد پنل x-ui خودت را به او بدهی.
    if [ -f "$INSTALL_DIR/scripts/reseller.py" ]; then
      shift
      BOT_DB_PATH="$INSTALL_DIR/data/bot.db"         python3 "$INSTALL_DIR/scripts/reseller.py" "$@"
    else
      err "scripts/reseller.py پیدا نشد — اول nexora update بزنید"
      exit 1
    fi
    ;;

  reseller-why|nemayande-why)
    # چرا این نماینده نمی‌تواند بفروشد — هفت قدمِ لازم، به ترتیب، و
    # اولین چیزی که گیر کرده. چهار باگِ پشتِ سرِ هم یک نشانه داشتند
    # («نماینده نمی‌تواند پلن تعریف کند») و هیچ‌کدام از پنل دیده
    # نمی‌شد؛ این همه را یک‌جا می‌گذارد.
    #
    # هیچ رمز، توکن، نام مشتری یا شماره‌ای چاپ نمی‌شود، پس خروجی
    # قابل فرستادن است.
    if [ -f "$INSTALL_DIR/scripts/reseller-why.py" ]; then
      shift
      BOT_DB_PATH="$INSTALL_DIR/data/bot.db" \
      BILLING_DB="$INSTALL_DIR/data/billing.db" \
        python3 "$INSTALL_DIR/scripts/reseller-why.py" "$@"
    else
      err "scripts/reseller-why.py پیدا نشد — اول nexora update بزنید"
      exit 1
    fi
    ;;

  fix-flow)
    # همه‌ی کلاینت‌های vless روی یک flow. بدون آرگومان فقط گزارش
    # می‌دهد؛ با --fix می‌نویسد.
    if [ -f "$INSTALL_DIR/scripts/fix-flow.py" ]; then
      shift
      python3 "$INSTALL_DIR/scripts/fix-flow.py" "$@"
    else
      err "scripts/fix-flow.py پیدا نشد — اول nexora update بزنید"
      exit 1
    fi
    ;;

  billing-why|why-unpriced)
    # چرا یک کانفیگ «بدون نرخ» است — نرخ‌های ثبت‌شده، نام گروه‌ها در
    # x-ui، و اینکه کدام حجم با کدام نرخ جور در می‌آید. هیچ رمز، نام
    # مشتری یا شماره‌ای چاپ نمی‌شود، پس خروجی قابل فرستادن است.
    if [ -f "$INSTALL_DIR/scripts/billing-why.py" ]; then
      python3 "$INSTALL_DIR/scripts/billing-why.py"
    else
      err "scripts/billing-why.py پیدا نشد — اول nexora update بزنید"
      exit 1
    fi
    ;;

  usage-why)
    # چرا عددِ مصرف این است — نسخه‌ی پنل، وضعیتِ ردیابیِ ریست، و
    # مصرفِ هر کانفیگ کنارِ آنچه از دوره‌های ریست‌شده بانک شده.
    # هیچ رمز، نام مشتری یا شماره‌ای چاپ نمی‌شود، پس خروجی
    # قابل فرستادن است.
    if [ -f "$INSTALL_DIR/scripts/usage-why.py" ]; then
      shift
      python3 "$INSTALL_DIR/scripts/usage-why.py" "$@"
    else
      err "scripts/usage-why.py پیدا نشد — اول nexora update بزنید"
      exit 1
    fi
    ;;

  import-topups)
    # شارژهای اعتبارِ نماینده‌ها که پیش از نسخه‌ی ۱.۲۷ فقط در دفتر
    # اعتبار می‌نشستند و به حسابداری نمی‌رسیدند. بدون آرگومان فقط
    # نشان می‌دهد چه چیزی وارد می‌شود؛ با --apply می‌نویسد.
    if [ -f "$INSTALL_DIR/scripts/import-topups.py" ]; then
      # shift لازم است: case روی "$1" است و بدون آن، نام خودِ دستور
      # هم به‌عنوان آرگومان به اسکریپت می‌رسد و argparse ردش می‌کند.
      shift
      BOT_DB_PATH="$INSTALL_DIR/data/bot.db" \
      BILLING_DB_PATH="$INSTALL_DIR/data/billing.db" \
        python3 "$INSTALL_DIR/scripts/import-topups.py" "$@"
    else
      err "scripts/import-topups.py پیدا نشد — اول nexora update بزنید"
      exit 1
    fi
    ;;

  repair-orders)
    # وضعیتِ سفارش‌های کیف پول که پیش از نسخه‌ی ۱.۳۴ اشتباه نوشته
    # می‌شدند: خریدِ تحویل‌شده هیچ‌وقت approved نمی‌شد و تمدیدِ ناموفق
    # approved می‌ماند. بدون آرگومان فقط نشان می‌دهد؛ با --apply
    # می‌نویسد.
    if [ -f "$INSTALL_DIR/scripts/repair-orders.py" ]; then
      # shift لازم است: case روی "$1" است و بدون آن، نام خودِ دستور
      # هم به‌عنوان آرگومان به اسکریپت می‌رسد و argparse ردش می‌کند.
      shift
      BOT_DB_PATH="$INSTALL_DIR/data/bot.db" \
        python3 "$INSTALL_DIR/scripts/repair-orders.py" "$@"
    else
      err "scripts/repair-orders.py پیدا نشد — اول nexora update بزنید"
      exit 1
    fi
    ;;

  repair-referrals)
    # پاداش معرف پیش از نسخه‌ی ۱.۳۸ فقط از مسیر تاییدِ کارت پرداخت
    # می‌شد. دوستی که با کیف پول می‌خرید هیچ سکه‌ای به معرفش
    # نمی‌رساند. بدون آرگومان فقط نشان می‌دهد چه کسی طلبکار است؛
    # سکه تخفیف است، پس پرداختش با --apply و تصمیم خودتان.
    if [ -f "$INSTALL_DIR/scripts/repair-referrals.py" ]; then
      # shift لازم است: case روی "$1" است و بدون آن، نام خودِ دستور
      # هم به‌عنوان آرگومان به اسکریپت می‌رسد و argparse ردش می‌کند.
      shift
      BOT_DB_PATH="$INSTALL_DIR/data/bot.db" \
        python3 "$INSTALL_DIR/scripts/repair-referrals.py" "$@"
    else
      err "scripts/repair-referrals.py پیدا نشد — اول nexora update بزنید"
      exit 1
    fi
    ;;

  doctor)
    logo
    echo -e "  ${C_BOLD}System Check${C_RESET}"
    echo ""

    # نسخه‌ی نصب‌شده در برابر نسخه‌ی CLI
    INSTALLED=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "?")
    echo -e "  ${C_DIM}Installed version :${C_RESET} ${C_WHITE}$INSTALLED${C_RESET}"

    if [ -f "$INSTALL_DIR/nexora-cli.sh" ] && [ -f /usr/local/bin/nexora ]; then
      if cmp -s "$INSTALL_DIR/nexora-cli.sh" /usr/local/bin/nexora; then
        ok "CLI is up to date"
      else
        warn "CLI is OUT OF DATE — new commands may be missing"
        info "Fixing now..."
        cp "$INSTALL_DIR/nexora-cli.sh" /usr/local/bin/nexora.new
        chmod +x /usr/local/bin/nexora.new
        mv -f /usr/local/bin/nexora.new /usr/local/bin/nexora
        ok "CLI updated — run your command again"
      fi
    fi

    echo ""
    # ماژول ربات
    if [ -d "$INSTALL_DIR/bot" ] && [ -f "$INSTALL_DIR/bot/run.py" ]; then
      ok "Bot module:     present ($(ls -1 "$INSTALL_DIR/bot"/*.py 2>/dev/null | wc -l) files)"
    else
      bad "Bot module:     MISSING at $INSTALL_DIR/bot"
      info "Run:  nexora update   (or reinstall)"
    fi

    if [ -f /etc/systemd/system/nexora-bot.service ]; then
      ok "Bot service:    installed"
    else
      warn "Bot service:    not created"
      if [ -d "$INSTALL_DIR/bot" ]; then
        info "Creating it now..."
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
    fi

    # وابستگی ربات
    if [ -d "$INSTALL_DIR/bot" ]; then
      if "$INSTALL_DIR/backend/venv/bin/python" -c "import requests" 2>/dev/null; then
        ok "Bot deps:       installed"
      else
        warn "Bot deps:       missing — installing..."
        "$INSTALL_DIR/backend/venv/bin/pip" install -r "$INSTALL_DIR/bot/requirements.txt" -q > /dev/null 2>&1 \
          && ok "Bot deps installed" || bad "Failed to install"
      fi
    fi

    # دیتابیس
    if [ -f "$INSTALL_DIR/data/bot.db" ]; then
      ok "Bot database:   $(du -h "$INSTALL_DIR/data/bot.db" | cut -f1)"
    else
      info "Bot database:   will be created when you open the bot section in the panel"
    fi

    if [ -f "$INSTALL_DIR/data/billing.db" ]; then
      ok "Billing data:   $(du -h "$INSTALL_DIR/data/billing.db" | cut -f1)"
    else
      info "Billing data:   will be created when you open the accounting section"
    fi

    # تانل‌ها: جدول jobs تا نسخه‌ی ۱.۲۸ کران نداشت.
    #
    # نخ پس‌زمینه هر پنج دقیقه برای هر نود یک کار health صف می‌کند و
    # هیچ چیزی پاکشان نمی‌کرد. از این نسخه به بعد هر چک‌اینِ ایجنت
    # قدیمی‌ها را دور می‌ریزد — ولی فایلی که از قبل بزرگ شده خودش
    # کوچک نمی‌شود: SQLite صفحه‌های آزادشده را دوباره استفاده می‌کند
    # و پس نمی‌دهد. VACUUM آن را پس می‌گیرد.
    if [ -f "$INSTALL_DIR/data/tunnels.db" ]; then
      TDB="$INSTALL_DIR/data/tunnels.db"
      TSZ=$(du -h "$TDB" | cut -f1)
      TKB=$(du -k "$TDB" | cut -f1)
      if [ "${TKB:-0}" -gt 51200 ]; then
        warn "Tunnel data:    $TSZ — larger than it needs to be"
        if command -v sqlite3 >/dev/null 2>&1; then
          TJOBS=$(sqlite3 "$TDB" "SELECT COUNT(*) FROM jobs" 2>/dev/null || echo "?")
          info "Finished agent jobs are pruned now ($TJOBS rows left)."
        fi
        info "Reclaim the space with:  systemctl stop nexora-panel &&"
        info "  sqlite3 $TDB 'VACUUM;' && systemctl start nexora-panel"
      else
        ok "Tunnel data:    $TSZ"
      fi
    fi

    # دسترسی به دیتابیس x-ui — حسابداری بدون آن کار نمی‌کند
    XUI="${XUI_DB:-/etc/x-ui/x-ui.db}"
    if [ -f "$XUI" ]; then
      if [ -r "$XUI" ]; then
        ok "3x-ui database: readable"
      else
        bad "3x-ui database: exists but NOT readable"
        info "Accounting needs read access. Fix with:  chmod +r $XUI"
      fi
    else
      warn "3x-ui database: not found at $XUI"
      info "Accounting will show an error until 3x-ui is installed here"
    fi

    echo ""
    # نام مستعار — اگر نبود می‌سازیم
    if [ ! -e /etc/systemd/system/nexora.service ] && [ -f /etc/systemd/system/nexora-panel.service ]; then
      ln -sf /etc/systemd/system/nexora-panel.service /etc/systemd/system/nexora.service 2>/dev/null
      systemctl daemon-reload 2>/dev/null
      ok "Added alias: systemctl status nexora"
    fi

    systemctl is-active --quiet $SERVICE && ok "Panel:          running" || bad "Panel:          stopped"
    systemctl is-active --quiet nexora-bot && ok "Bot:            running" || warn "Bot:            stopped"
    echo ""
    ;;

  bot)
    logo
    SUB="$2"
    case "$SUB" in
      start)
        systemctl start nexora-bot && ok "Bot started" || bad "Failed to start"
        sleep 3
        systemctl is-active --quiet nexora-bot && ok "Running" || { bad "Not running"; warn "Check:  nexora bot logs"; }
        ;;
      stop)
        systemctl stop nexora-bot && ok "Bot stopped"
        ;;
      restart)
        systemctl restart nexora-bot && ok "Bot restarted"
        sleep 3
        systemctl is-active --quiet nexora-bot && ok "Running" || bad "Not running — check logs"
        ;;
      enable)
        systemctl enable nexora-bot > /dev/null 2>&1 && ok "Bot will start on boot"
        systemctl start nexora-bot && ok "Bot started"
        ;;
      disable)
        systemctl disable nexora-bot > /dev/null 2>&1
        systemctl stop nexora-bot 2>/dev/null
        ok "Bot disabled"
        ;;
      logs)
        journalctl -u nexora-bot -f --no-pager
        ;;
      *)
        if systemctl is-active --quiet nexora-bot 2>/dev/null; then
          ok "Bot service:  running"
        else
          warn "Bot service:  stopped"
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
          warn "Database:     not created yet"
        fi
        echo ""
        echo -e "  ${C_DIM}Commands${C_RESET}"
        echo -e "  ${C_GRAY}├─${C_RESET} ${C_WHITE}nexora bot start${C_RESET}     ${C_DIM}start the bot${C_RESET}"
        echo -e "  ${C_GRAY}├─${C_RESET} ${C_WHITE}nexora bot stop${C_RESET}      ${C_DIM}stop it${C_RESET}"
        echo -e "  ${C_GRAY}├─${C_RESET} ${C_WHITE}nexora bot restart${C_RESET}   ${C_DIM}restart${C_RESET}"
        echo -e "  ${C_GRAY}├─${C_RESET} ${C_WHITE}nexora bot enable${C_RESET}    ${C_DIM}start on boot${C_RESET}"
        echo -e "  ${C_GRAY}└─${C_RESET} ${C_WHITE}nexora bot logs${C_RESET}      ${C_DIM}live logs${C_RESET}"
        echo ""
        ;;
    esac
    ;;

  diagnose)
    bash "$INSTALL_DIR/scripts/diagnose.sh"
    ;;

  password)
    logo
    read -s -p "  New admin password (min 8 chars): " NP; echo ""
    if [ ${#NP} -lt 8 ]; then bad "Too short"; exit 1; fi
    read -s -p "  Confirm: " NP2; echo ""
    [ "$NP" != "$NP2" ] && { bad "Passwords do not match"; exit 1; }
    python3 - "$INSTALL_DIR/data/auth.json" "$NP" << 'PYEOF'
import json, sys, os
path, pw = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump({"password": pw}, open(path, "w"))
os.chmod(path, 0o600)
PYEOF
    ok "Password changed (takes effect immediately)"
    echo ""
    ;;

  *)
    logo
    echo -e "  ${C_BOLD}Commands${C_RESET}"
    echo ""
    echo -e "  ${C_WHITE}nexora url${C_RESET}                    ${C_DIM}show the secret admin-panel address${C_RESET}"
    echo -e "  ${C_WHITE}nexora status${C_RESET}                 ${C_DIM}show service health${C_RESET}"
    echo -e "  ${C_WHITE}nexora logs${C_RESET}                   ${C_DIM}live logs (Ctrl+C to exit)${C_RESET}"
    echo -e "  ${C_WHITE}nexora restart${C_RESET}                ${C_DIM}restart backend${C_RESET}"
    echo -e "  ${C_WHITE}nexora start${C_RESET} / ${C_WHITE}stop${C_RESET}          ${C_DIM}start or stop backend${C_RESET}"
    echo -e "  ${C_WHITE}nexora backup${C_RESET}                 ${C_DIM}whole panel in one zip (/root/backups)${C_RESET}"
    echo -e "  ${C_WHITE}nexora restore FILE${C_RESET}           ${C_DIM}restore that zip (saves the current state first)${C_RESET}"
    echo -e "  ${C_WHITE}nexora update <file.zip>${C_RESET}      ${C_DIM}update to a new version${C_RESET}"
    echo -e "  ${C_WHITE}nexora rebuild${C_RESET}                ${C_DIM}rebuild admin panel (fixes UI issues)${C_RESET}"
    echo -e "  ${C_WHITE}nexora pro${C_RESET}                    ${C_DIM}install the Pro package for this license${C_RESET}"
    echo -e "  ${C_WHITE}nexora rollback${C_RESET}               ${C_DIM}go back to a previous version${C_RESET}"
    echo -e "  ${C_WHITE}nexora snapshots${C_RESET}              ${C_DIM}list saved versions${C_RESET}"
    echo -e "  ${C_WHITE}nexora bot${C_RESET}                    ${C_DIM}manage the Telegram bot${C_RESET}"
    echo -e "  ${C_WHITE}nexora check${C_RESET}                  ${C_DIM}full report: versions, jobs, firewall, billing, bot${C_RESET}"
    echo -e "  ${C_WHITE}nexora doctor${C_RESET}                 ${C_DIM}check and auto-fix common problems${C_RESET}"
    echo -e "  ${C_WHITE}nexora billing-why${C_RESET}            ${C_DIM}why a config shows as having no rate${C_RESET}"
    echo -e "  ${C_WHITE}nexora usage-why${C_RESET}              ${C_DIM}why the usage figure is what it is${C_RESET}"
    echo -e "  ${C_WHITE}nexora import-topups${C_RESET}          ${C_DIM}bring old prepaid top-ups into the books${C_RESET}"
    echo -e "  ${C_WHITE}nexora repair-orders${C_RESET}          ${C_DIM}fix wallet order statuses written before 1.34${C_RESET}"
    echo -e "  ${C_WHITE}nexora repair-referrals${C_RESET}       ${C_DIM}pay referral coins wallet buys never paid${C_RESET}"
    echo -e "  ${C_WHITE}nexora reseller list${C_RESET}          ${C_DIM}reseller portal accounts${C_RESET}"
    echo -e "  ${C_WHITE}nexora reseller-why${C_RESET}           ${C_DIM}why a reseller cannot sell yet${C_RESET}"
    echo -e "  ${C_WHITE}nexora reseller-why --set-miniapp URL${C_RESET}  ${C_DIM}set the mini-app address by hand${C_RESET}"
    echo -e "  ${C_WHITE}nexora fix-flow${C_RESET}               ${C_DIM}put every vless client on the same flow${C_RESET}"
    echo -e "  ${C_WHITE}nexora password${C_RESET}               ${C_DIM}change admin password${C_RESET}"
    echo -e "  ${C_WHITE}nexora diagnose${C_RESET}               ${C_DIM}troubleshoot template issues${C_RESET}"
    echo ""
    echo -e "${C_GRAY}  ─────────────────────────────────────────────────────${C_RESET}"
    echo -e "  ${C_LBLUE}${C_BOLD}NEXORA VPN${C_RESET}  ${C_DIM}·${C_RESET}  ${C_GRAY}t.me/yanexoravpn${C_RESET}"
    echo ""
    ;;
esac
