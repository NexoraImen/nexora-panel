# Changelog

Each entry says what was broken and why, not a list of commits.
History before 2.0 lives with the 1.x line.

## [2.0.0] - 2026-09-30

### New home

Nexora moves to [NexoraImen/nexora-panel](https://github.com/NexoraImen/nexora-panel).
A 1.x server switches once by pointing its update source here, then updates as usual:
`echo 'GITHUB_REPO="NexoraImen/nexora-panel"' > /opt/nexora-panel/.github` and `nexora update`.
Settings, the bot database and the accounting database are kept.

### Subscription page: contact links belong to the operator

The template hard-coded Nexora's own support and channel handles, and the default settings
carried them too. On any other operator's server, whenever the panel settings did not reach the
page, their customers were sent to Nexora's support. Now the links come from the panel's
usernames, then from 3x-ui's own "support URL" setting; with neither, the buttons hide instead
of pointing somewhere else.

### Pro license

The free edition now knows, on the server and without going online, whether this server holds a
valid Pro license. The System page shows the license state and its reason, and a Pro license is
activated, refreshed or moved to another server from there. When a license lapses, the page says
which of two things happened, because the fix differs: the payment ran out, or the server has not
reached the license server for 30 days. Pro keeps working through a grace period and then locks.
End customers are never cut off. If a server is reinstalled or lost before it could deactivate,
the seller releases the license and the same key activates the new server.

### Pro areas are visible, and say why they are locked

The first Pro areas now live apart from the free core: channel posting; sales insights (the funnel, customer feedback polls, the satisfaction line and the bot preview); the server tools (connection diagnostics, the inbound doctor, the firewall and intrusion view, other servers, tunnels and their traffic); the subscription-page templates other than classic; and the Telegram mini app. A lapsed license never stops a running tunnel, customers of a shop whose mini app is locked are pointed to the bot menu (which does everything the mini app does), and a customer's subscription page falls back to classic instead of breaking. Without a license their
menu items keep their place with a "Pro" mark, and each page says which feature it is and why it
is locked, in the same words the server uses. A post that comes due while Pro is locked is marked
as not sent, with that reason, instead of going out weeks late when the license returns. While a
license is in its grace period, or the server clock or machine does not match, a strip above
every page says so until it is fixed.

Reseller accounting (overview, rates, invoices and their PDF, periods, payments and settling,
expenses, the ledger, the all-clients list) is Pro too, and so is the reseller's own summary in
their portal, which is the same invoice seen from their side. What stays free is the data and its
safety: the accounting database, its backup and restore, and the x-ui database path, which the
whole panel reads. A lapsed license never stops a backup. The dashboard's debt card says in one
line that accounting is locked, instead of showing the locked answer as a failure.

The reseller portal and the owner's reseller management are Pro as well. A lapsed license locks
the portal and those screens, never a reseller's bot: it keeps selling, delivering and renewing
for its customers. A reseller whose portal is locked reads that the portal is not available and
to ask the shop's owner, not the owner's license trouble, which is not theirs to read.

Coins, invites, discount codes, the trial follow-up and win-back (loyalty) and the sales partners
(affiliates) are Pro. The three ways a purchase is paid (card, wallet, automatic renewal) now pay
the partner's commission and the inviter's coins through one call, so a path can no longer pay one
and forget the other, as each once did. While Pro is locked, those payouts are not made and each
skipped one is listed in the bot's events, so the owner can settle by hand; they are not paid weeks
later when the license returns. A failed payout is listed too, and never stops a delivery. What a
customer already has keeps working: coins they earned can still be spent, and a discount code they
hold can still be used. The trial follow-up and win-back now only reach trials of the last few days:
before, turning them on (or a license coming back) sent "your trial ended, here is a code" to trials
weeks old. A failed commission record used to be logged only at debug level; it is now an error in
the events list.

### The Pro package arrives signed

A licensed server gets its Pro code from the license server, for exactly its panel version, never
from GitHub. `nexora update` fetches it before it builds, `nexora pro` installs it on demand, and
the System page offers "install the Pro package" when a license is active but no Pro code is loaded.
The package is checked against a signature made by the license key before a single file is
unpacked, and only the three Pro folders are ever written; a failed install leaves the previous code
in place and says why. Each copy carries its license id.

A server updated from 1.x keeps the old copies of the modules that moved into the Pro folder,
because an update copies files and deletes none. The Pro code imported some of them by bare
name, which finds that stale copy first and runs it without a word, so a fix to the module would
never have taken effect. It now loads them from the Pro folder only, and a test refuses a bare
import of any module that lives there.

### Pro licenses are sold from the bot

On the server that runs the license issuer, a plan can be a Pro license: bought in the bot by card
or wallet like any plan, delivered as a key the moment it is paid, listed under "my subscriptions"
and renewed from there. The order is approved only after the issuer has made the license; with the
issuer down, the wallet is refunded or the receipt stays pending, and the group is told why. A
retried or doubled approval gets the same license back, never a second one. Resellers cannot sell
licenses, and on every other server the plan kind does not appear at all.

While building it, "this order was delivered" turned out to mean "it has a config" in five places.
A license order has no config, so it could have been rejected after delivery, put back in the queue,
or approved again a few minutes later with the partner's commission paid twice. Those checks now
read one condition that knows both.

A bot whose plans on sale are all Pro licenses is a Pro store. Its menu says "buy Nexora Pro" and
"my licenses", and it has no VPN install guide. The same goes for its welcome text, empty pages and
hints. Nothing needs to be turned on for this; it follows from what is for sale.

### Wallet purchases with a discount code showed the undiscounted price

The wallet was charged the discounted amount, but the buyer's "taken from your wallet" message, the
mini-app's answer and the admin group's notice all said the plan's list price. Now all three show
what was charged, and the group notice names the code's percent and the list price beside it.

### One test runner

CI and the release gate each kept a hand-written list of test files, and they had drifted: CI
never ran five suites (API contract, link check, inbound doctor, and the two repair tools), so
a break in any of them was green on every push. `tests/run.py` now discovers every
`tests/test-*` and `tests/bot/test_*` file; both CI and `scripts/release-check.py` call it.
A new test file runs everywhere without being listed anywhere.

The API-contract test also depended on a live exchange-rate site: offline, the backend returned
its fallback shape and the test reported drift although nothing had changed. The rate source
is now stubbed in that test.

### Layout

Tests live in `tests/` (bot tests in `tests/bot/`, the panel harness in `tests/harness/`), and
operational scripts in `scripts/`. The root keeps only `install.sh`, `nexora-cli.sh` and
`uninstall.sh`. `nexora` commands were updated to the new paths.
