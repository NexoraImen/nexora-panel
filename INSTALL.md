# Installing Nexora

## Requirements

- Ubuntu 20.04+ or Debian 11+, as root
- 3x-ui already installed on the same server for a local installation, or on a
  separate agent host for a central installation
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

### Central panel on a separate internet-connected host

On the central host (for example, outside Iran), use:

```bash
sudo bash install.sh --central
```

This installs the same panel and bot without requiring local 3x-ui. It skips the
local subscription template, XUI database edits and XUI restart. Ordinary installs
and `--prepare` keep their existing behavior; the two flags cannot be combined.
The central installer requires HTTPS and an empty IP restriction, because the
remote agent must reach the public agent API. Admin APIs remain authenticated.
Cloudflare Origin certificates require a proxied hostname with a publicly trusted
edge certificate; an agent connecting directly cannot trust an Origin certificate.
If certificate setup fails, central installation stops rather than claiming a
working HTTP-only agent connection. Packages and partially installed services may
already exist at that point; fix TLS before continuing setup.

1. Register the owner bot in «اتصال و تنظیمات». Keep sales stopped until the
   remote source is verified. A new installation starts in local mode until this
   setup is completed; `--central` does not invent a remote source or credentials.
2. Open Bot → «اتصال سرور 3x-ui» and choose the central host's actual region.
3. Enter the remote node's name and region, then create a pairing code. The code
   expires in ten minutes, works once, and is held only in the current page.
4. Copy the complete installer command returned by the panel. Run it as root on
   the host that already runs 3x-ui. It downloads a Python installer with
   `curl --fail` to a file, then runs `python3` with `--panel` and `--code`.
   Do not pipe the download directly into a shell or save the secret in docs/logs.
5. The agent host needs Python 3 with venv support, systemd, and outbound HTTPS to
   the central panel. The agent uses only the Python standard library; it needs
   neither pip nor access to PyPI. Install `python3-venv` if needed.
   The installer prompts for the local loopback XUI URL (including its
   base path), API token or credentials, and the confirmed local SQLite path.
   These credentials stay on the agent host. No public XUI listener is needed.
6. Return to the page and press «تازه‌سازی». Confirm a fresh snapshot, choose
   central/remote mode and the node, then save. The backend rejects missing,
   revoked or snapshots older than 90 seconds; an online heartbeat alone is not
   sufficient. Switching an established accounting source to a different node
   requires migration and reconciliation, and is rejected by this selector.
7. Run the existing bot connection/provisioning test before enabling sales.
   Revoking the selected node stops remote operations until a valid connection
   is restored. Revocation keeps its history visible in the node list.

For a revoked node or a lost agent token, use «اتصال دوباره» on that existing
node, including a revoked one. Confirm that it is the same 3x-ui/accounting source:
the old token is invalidated immediately, while the node ID, snapshot sequence
and history are preserved. Previous snapshot data is cleared; fresh data is
required before remote operations resume. The new code and complete command
appear in the existing pairing area. Run the returned command with `--re-enroll`
on that same host. With an existing configuration the installer preserves its
local credential source and command journal; without a configuration it follows
normal installation. Do not create a different node to replace the same source.

If a command's result is uncertain, the connection page shows its ID, node,
method, path and creation time, without its request body. Check the actual result
on the XUI host and reconcile the order and payment before pressing the review
confirmation. This needs a fresh snapshot and only records your review; it never
replays the command. The page never acknowledges uncertain commands automatically.
Orders awaiting delivery/payment reconciliation are listed separately, even after
an agent reports a terminal command result. Automatic retries and refunds stay
paused; use the orders page to inspect them. The command-review endpoint cannot
clear a financial order hold or a command whose terminal result is still pending.

The agent installer does not install Nexora's subscription-page template on the
remote XUI host. Existing subscription pages remain in place; configuring a
custom template there is a separate step.

For frontend preview, build the single-bundle harness as described in AGENTS.md,
then open `/harness.html#/bot-source` (or select the page in the bot menu).
The fixture includes fresh, stale-but-online, pending, offline and revoked nodes.
Use `?xui=empty`, `?xui=error`, `?xui=uncertain` or `?xui=orders` to exercise
empty/error/recovery/order-hold states. Pairing and
revocation are simulated and never contact a real server.

### Preparing beside an active 3x-ui server

For migration to a host that already serves customers, use the preparation mode
instead of the ordinary installer:

```bash
sudo bash install.sh --prepare
```

Use a clean Git checkout of the intended release. Only committed files are
deployed; untracked local files and source `data/` are not transferred.
This mode installs prerequisites, builds the frontend with same-origin API calls,
creates an application venv, and prepares systemd units under `/opt/nexora-panel`.
It refuses an existing destination or registered Nexora service. APT plans that
upgrade or remove installed packages are refused; needrestart is suspended for
this invocation. If necessary, a checksum-verified official Node 24 toolchain is
installed separately under `/opt/nexora-toolchain`, leaving system Node intact.

**Preparation does not activate the panel.** Neither Nexora service is started or
enabled. The nginx site is saved as `/opt/nexora-panel/nginx-prepared.conf`, outside
active nginx includes. Its eventual web listener is `127.0.0.1:18080`, proxying the
backend at `127.0.0.1:8100`. Installing the nginx package may start its default
HTTP server; preparation refuses an occupied port 80 when nginx is absent.
No XUI database/template, XUI service, tunnel, firewall, DNS or cron change is
requested by the preparation script. The ordinary installer retains its existing
behavior; these guarantees apply only to `--prepare`.

Before activation, verify the backup and destination XUI mapping, securely set
the admin password, and resolve the destination license. Both units require
`data/auth.json` and `data/activation-approved`; do not create the approval marker
before these checks. Keep the old customer bot as the sole poller until cutover.
The admin management bot is disabled in the prepared panel unit. Activation,
TLS/domain cutover, backup restoration and CLI installation are separate steps.

If preparation fails, it exits nonzero without starting Nexora. Download/build
failures can leave packages or a partial installation behind; do not rerun over
that directory or delete it without first checking its contents.

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

For the first upgrade from an older CLI that restarts x-ui, use the verified
2.3.9 CLI to perform the update. The old running updater retains its old behavior
even if it replaces its own file while updating. Do not run that old updater on
a busy VPN host expecting the new no-XUI-restart behavior to apply retroactively.

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

## Automatic update source

`nexora update` uses `NexoraImen/nexora-panel` by default. New installations
save settings in `/opt/nexora-panel/.nexora-update.conf` (owner-only access).
Existing `.github` settings files remain supported; `.github/` workflow
directories are left untouched. When both files exist, the new file takes
precedence. Preserve custom repository and token settings when changing hosts;
never share the settings file in diagnostic output.

## Restoring a panel ZIP after migration

The panel API accepts ZIP uploads up to 256 MiB. New installations and the nginx
repair run during updates configure that limit and unbuffered restore progress.
A reverse proxy in front of Nexora can impose a smaller independent limit.
HTTP 413 means that request was rejected before restoration, so increasing the
correct proxy limit is necessary; importing the same ZIP repeatedly cannot fix it.
Use `nexora restore /path/to/backup.zip` for larger files.

When the destination already has `license.json`, restoration keeps its existing
`install_id` and license clock state instead of binding the signed license to a
different identity. The result lists preserved files. Keep the destination
activation and verify Pro after restoring; the ZIP does not contain the signed
license or the foreign issuer's private state. Existing 3x-ui data is not part
of this archive and must not be replaced by Nexora restoration.

## International connectivity

Managed connectivity requires Python 3.9 or newer. Ubuntu 22.04+ provides a
compatible system Python; Ubuntu 20.04's default Python 3.8 is insufficient.

The System page reports the Telegram and GitHub network paths and offers a fresh
check. Activated installations automatically receive managed access when the
provider has enabled it. Customers enter no proxy hostname, port or SSH key.
The independent `nexora-connect` service listens only on loopback, prefers direct
access, and routes selected Telegram/GitHub HTTPS traffic through the provider
when necessary. It does not change XUI traffic, host routes or firewall rules.

Initial installation still needs access to the package sources, and activation
and renewal need the license endpoints. The provider's relay hostname must be
reachable from Iran over HTTPS. Network readiness does not validate a bot token;
use the bot section for that check. Connectivity credentials are excluded from
panel ZIP backups and are renewed for the destination installation.

## Uninstalling

```bash
sudo bash /opt/nexora-panel/uninstall.sh
```

It asks before removing anything, and offers to keep the subscription-page template.
