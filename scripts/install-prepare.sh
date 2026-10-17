#!/bin/bash
# Preparation must not launch writers against an unverified restored database.
set -Eeuo pipefail
umask 077
trap 'echo "Preparation failed at line $LINENO: $BASH_COMMAND" >&2' ERR

SOURCE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEST=/opt/nexora-panel
UNITS=/etc/systemd/system
TOOLS=/opt/nexora-toolchain
die() { echo "ERROR: $*" >&2; exit 1; }

[[ $EUID == 0 ]] || die "Run as root."
[[ $(uname -s) == Linux ]] || die "Linux is required."
[[ -f $SOURCE/VERSION && -f $SOURCE/backend/requirements.txt && -f $SOURCE/frontend/package.json ]] \
  || die "Run from a complete Nexora source checkout."
command -v git >/dev/null || die "Git is required; run from a clean release checkout."
[[ -e $SOURCE/.git ]] || die "Run from the root of a Git checkout."
git -C "$SOURCE" rev-parse --verify HEAD >/dev/null
git -C "$SOURCE" diff --quiet HEAD -- || die "Source has tracked edits; use a clean release checkout."
[[ ! -e $DEST && ! -L $DEST ]] || die "$DEST already exists; preparation never overwrites an installation."
for unit in nexora-panel nexora-bot nexora; do
  [[ ! -e $UNITS/$unit.service && ! -L $UNITS/$unit.service ]] \
    || die "Existing $unit.service; preparation refused."
  [[ $(systemctl show "$unit.service" -p LoadState --value) == not-found ]] \
    || die "$unit.service is already registered."
done
case $(uname -m) in
  x86_64) ARCH=x64 ;;
  aarch64) ARCH=arm64 ;;
  *) die "Unsupported Node architecture: $(uname -m)" ;;
esac
command -v apt-get >/dev/null || die "Ubuntu/Debian APT is required."
if ! command -v nginx >/dev/null; then
  command -v ss >/dev/null || die "ss is required to check nginx's default port."
  LISTENERS=$(ss -H -lnt 'sport = :80')
  [[ -z $LISTENERS ]] || die "Port 80 is occupied; refusing nginx package auto-start."
fi
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT
export LC_ALL=C DEBIAN_FRONTEND=noninteractive NEEDRESTART_SUSPEND=1

echo "Preparing Nexora. Existing XUI services and data will not be configured."
apt-get update
PACKAGES=(python3 python3-venv ca-certificates curl tar xz-utils nginx)
apt-get -s --no-upgrade --no-remove install "${PACKAGES[@]}" > "$WORK/apt-plan"
cat "$WORK/apt-plan"
# --no-upgrade alone can still upgrade dependencies; reject those plans too.
if LC_ALL=C grep -Eq '^(Remv |Inst [^ ]+ \[)' "$WORK/apt-plan"; then
  die "APT proposes upgrading or removing existing packages; nothing installed."
fi
apt-get -y --no-upgrade --no-remove install "${PACKAGES[@]}"

NODE_MAJOR=0
if command -v node >/dev/null && command -v npm >/dev/null; then
  NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
fi
if [[ $NODE_MAJOR != 22 && $NODE_MAJOR != 24 ]]; then
  curl --fail --show-error --location --proto '=https' --tlsv1.2 \
    --connect-timeout 15 --max-time 60 \
    https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt -o "$WORK/sums"
  awk -v arch="$ARCH" '$2 ~ ("^node-v24\\.[0-9]+\\.[0-9]+-linux-" arch "\\.tar\\.xz$") {print}' \
    "$WORK/sums" > "$WORK/check"
  [[ $(wc -l < "$WORK/check") == 1 ]] || die "Node checksum entry missing or duplicated."
  read -r HASH ARCHIVE < "$WORK/check"
  [[ $HASH =~ ^[a-fA-F0-9]{64}$ ]] || die "Invalid Node checksum."
  NODE_VERSION=${ARCHIVE#node-}
  NODE_VERSION=${NODE_VERSION%-linux-*}
  curl --fail --show-error --location --proto '=https' --tlsv1.2 \
    --connect-timeout 15 --max-time 600 \
    "https://nodejs.org/dist/$NODE_VERSION/$ARCHIVE" -o "$WORK/$ARCHIVE"
  (cd "$WORK" && sha256sum -c check)
  [[ ! -e $TOOLS && ! -L $TOOLS ]] || die "$TOOLS exists; refusing to overwrite it."
  mkdir -m 755 "$TOOLS"
  tar -xJf "$WORK/$ARCHIVE" -C "$TOOLS" --strip-components=1
  export PATH="$TOOLS/bin:$PATH"
fi
node --version
npm --version

# Only committed files belong in a deployment, never local backups or secrets.
mkdir -m 755 "$DEST"
git -C "$SOURCE" archive HEAD | tar -C "$DEST" --exclude=data --exclude=issuer -xf -
mkdir -m 700 "$DEST/data"
python3 -m venv "$DEST/backend/venv"
"$DEST/backend/venv/bin/pip" install -r "$DEST/backend/requirements.txt"
if [[ -f $DEST/bot/requirements.txt ]]; then
  "$DEST/backend/venv/bin/pip" install -r "$DEST/bot/requirements.txt"
fi
(
  cd "$DEST/frontend"
  # The old hostname may still serve the source panel during migration.
  printf 'VITE_API_URL=\n' > .env
  export VITE_API_URL= NODE_OPTIONS=--max-old-space-size=1536
  if [[ -f package-lock.json ]]; then
    timeout 900 npm ci --no-fund --no-audit
  else
    timeout 900 npm install --no-fund --no-audit
  fi
  timeout 900 npm run build
  [[ -s dist/index.html ]] || die "Frontend build did not produce dist/index.html."
  chmod a+rx "$DEST/frontend"
  chmod -R a+rX dist
)

for unit in nexora-panel nexora-bot; do
  if [[ $unit == nexora-panel ]]; then
    CWD=backend
    START="$DEST/backend/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8100"
  else
    [[ -f $DEST/bot/run.py ]] || continue
    CWD=bot
    START="$DEST/backend/venv/bin/python run.py"
  fi
  cat > "$WORK/$unit.service" <<EOF
[Unit]
Description=Nexora prepared service ($unit)
After=network.target
ConditionPathExists=$DEST/data/activation-approved
ConditionPathExists=$DEST/data/auth.json

[Service]
Type=simple
WorkingDirectory=$DEST/$CWD
Environment=CONFIG_PATH=$DEST/data/config.json
Environment=AUTH_PATH=$DEST/data/auth.json
Environment=PANEL_CONFIG=$DEST/data/config.json
Environment=BOT_DB_PATH=$DEST/data/bot.db
Environment=BILLING_DB_PATH=$DEST/data/billing.db
Environment=TUNNEL_DB_PATH=$DEST/data/tunnels.db
Environment=SUBPAGE_HTML_PATH=$DEST/sub-page-index.html
Environment=NEXORA_NO_ADMIN_BOT=1
ExecStart=$START
Restart=on-failure
RestartSec=10
User=root
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
done

# Kept outside nginx's active include directories until deliberate activation.
cat > "$DEST/nginx-prepared.conf" <<EOF
server {
    listen 127.0.0.1:18080;
    server_name localhost;
    root $DEST/frontend/dist;
    index index.html;
    location = /index.html { add_header Cache-Control "no-store" always; }
    location / { try_files \$uri /index.html; }
    location /api/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
chmod 644 "$DEST/nginx-prepared.conf"
for file in "$WORK"/*.service; do install -m 600 "$file" "$UNITS/"; done
systemctl daemon-reload
echo "PREPARATION COMPLETE: Nexora services are stopped and not enabled."
echo "Prepared web: 127.0.0.1:18080; backend: 127.0.0.1:8100 (not listening yet)."
echo "Before activation: verify backup/XUI mapping, set auth.json and check license."
echo "Do not create data/activation-approved until those checks are complete."
echo "No XUI configuration, tunnel, firewall, DNS or cron change was requested."
echo "Installing nginx may start its default web server; Nexora site is inactive."
