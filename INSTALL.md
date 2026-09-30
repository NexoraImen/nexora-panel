# Installing Nexora

## Requirements

- Ubuntu 20.04+ or Debian 11+, as root
- 3x-ui already installed on the same server
- A domain (or subdomain) pointing at the server, for the admin panel
- 1 GB of RAM (the installer adds swap if memory is low)

## Install

```bash
git clone https://github.com/NexoraImen/nexora-panel.git
cd nexora-panel
sudo bash install.sh
```

The installer asks:

| Question | Notes |
|:--|:--|
| Admin panel domain | e.g. `panel.example.com` |
| Admin password | typed twice, not shown |
| SSL | 1 Let's Encrypt (needs an email; the domain must already point here) · 2 Cloudflare Origin (paste the certificate) · 3 skip, HTTP only |
| Restrict the panel to your IP | leave empty to allow all |
| Proceed | nothing changes before you confirm |

It then installs the backend, bot and panel under `/opt/nexora-panel`, sets up nginx and
systemd services, builds the panel, and installs the `nexora` command.

### The panel's secret address

The admin panel does **not** live at `/` — anyone who opens your domain sees "page not found".
The real address has a random path, printed at the end of the install and sent to the owner
in Telegram once the bot is connected:

```bash
nexora url
```

If the address leaks, rotate it from the panel: settings, tab «پنل، رمز و پشتیبان» (panel, password and backup), card «نشانیِ پنل».

## Connecting the bot

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
   It must **not** be the token of 3x-ui's own bot — Telegram allows only one process per token.
2. In the panel: Bot → Connection, paste the token.
3. In 3x-ui: Settings → Security, create an API token and paste it into the same page.
4. Press **Run test**. Nexora creates a real test config, reads it back and deletes it, so
   "connected" means the bot can actually deliver — not just that a password was accepted.
5. Add a plan and a card number.
6. Start the bot from the panel.

## Updating

```bash
nexora update
```

A snapshot is taken first. If anything goes wrong:

```bash
nexora rollback
```

Settings (`data/config.json`), the bot database and the accounting database are kept across
updates and rollbacks.

## When something is wrong

| Symptom | Run |
|:--|:--|
| Anything, first | `nexora check` — a full report, safe to send (no tokens, passwords or customer names) |
| Common problems | `nexora doctor` — checks and fixes what it can |
| Panel loads without styles | `sudo bash /opt/nexora-panel/scripts/fix-nginx.sh` |
| Accounting cannot read 3x-ui | `nexora fix-xui` |
| Full traceback instead of a generic error | `python3 /opt/nexora-panel/scripts/billing-trace.py` |
| An update half-applied | `sudo bash /opt/nexora-panel/scripts/repair.sh` |

Logs:

```bash
nexora logs
```

## Uninstalling

```bash
sudo bash /opt/nexora-panel/uninstall.sh
```

It asks before removing anything, and offers to keep the subscription-page template.
