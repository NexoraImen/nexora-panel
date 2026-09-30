# Security

## Reporting a vulnerability

Please **do not open a public issue**. Nexora runs on servers that hold real money and real
customer data; a published bug is exploitable on all of them until they update.

- Private [security advisory](https://github.com/NexoraImen/nexora-panel/security/advisories/new) in this repository
- Telegram: [@crm_nexoravpn](https://t.me/crm_nexoravpn)

If you can, include the version, the endpoint or path involved, and whether an attacker needs
to be logged in.

## Supported versions

| Version | Status |
|:--|:--|
| 2.x | supported |
| 1.x | upgrade to 2.x — no separate security fixes |

## What Nexora protects by design

**The admin panel is not at `/`.** It lives under a random path; every admin API call must
carry it, otherwise the server answers 404. Resellers and sales partners, who know your domain,
cannot find the admin panel from it.

**The firewall cannot lock you out.** Enabling it with no rule allowing port 22 is refused
without explicit confirmation; the SSH rule needs a separate confirmation to delete; rule
numbers are re-read right before a deletion.

**Automatic reboot is off by default** and separate from service restarts.

**The tunnel agent holds no root password.** The remote server runs an agent that dials out,
opens no ports and understands a fixed set of commands.

**Reading from 3x-ui is read-only** for accounting.

**Licenses are verified offline** with a public key built into the free core; the signing key
never leaves the issuer. When the panel activates or refreshes a license it sends the license key
or id, a fingerprint of this server (a hash, not the raw machine id), the panel version and the
panel domain. The license server also records the IP address the request came from, to
notice one license running on two cloned servers. It sends no customer data. A lapsed license locks only the Pro sections; your
customers' configs, renewals and in-bot purchases keep working.

**The Pro package is signed.** A licensed server downloads the Pro code for its version from the
license server. The package comes with a manifest signed by the same key as licenses, and the
panel checks it with the built-in public key before it unpacks anything, so a hijacked hostname
or a proxy cannot hand your server code to run. It only ever writes the three Pro folders. Each
copy is marked with its license id, and the panel reports that mark when it refreshes.

## What you should do

- Use a strong panel password; the panel is on the internet
- Do not copy the 3x-ui API token anywhere else
- Remove bot tokens and card numbers from screenshots or logs before sharing them
- Run `nexora backup` regularly
