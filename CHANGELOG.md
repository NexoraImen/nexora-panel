# Changelog

Each entry says what was broken and why, not a list of commits.
History before 2.0 lives with the 1.x line.

## [2.3.6] - 2026-10-07

### «چرا این‌قدر؟»: what the traffic costs, who uses it, who pays for it

The owner: "based on the cost I am losing money, and I do not know where the
problem is." The page from 2.2.1 could only say whether the network wastes
bytes: tunnel overhead, a flood on the IP, resends. It could not say whether
the traffic is paid for. A healthy tunnel still loses money when a few
unlimited or flat-price customers use most of it. Three things are new under
«تانل» → «حجمِ ترافیک» → «چرا این‌قدر؟»:

- **Cost.** For each server, the price per GB from the datacenter's invoice
  and what it bills (in + out, out only, or in only). The page then shows the
  window's cost and what each GB a customer uses costs, with both servers
  and the tunnel's overhead included. A price that is not entered is shown as
  missing, never guessed.
- **Who pays.** Each customer's usage is classed by the invoice's own rules:
  per GB, flat rate, the owner's bot, free trial, or on no bill. For each
  class the page shows its cost and what you get for it.
- **Top customers.** The ten biggest users in the window, with group, how
  they pay, whether they are unlimited, and how many IPs 3x-ui saw.

New findings, each with a fix: a per-GB reseller paying less than a GB
costs (with the loss in toman), the bot's sales not covering its customers'
traffic over 30 days, unlimited configs over 20% of usage, traffic on no bill
over 15%, flat-price groups over 25%, ten customers over half of all usage,
and anyone over 30 GB a day. A money loss becomes the page's verdict.

3x-ui keeps only a running total per customer, so the panel now records
each customer's usage by day (kept 90 days). "Who used it" fills in from the
update onwards, and the page says how much of the window it covers.

## [2.3.5] - 2026-10-07

### The collapsed menu, in every menu mode

2.3.4 fixed the collapsed rail for the default menu (accordion) only. The
owner uses «کشویی» (dropdown), and there the item icons were squeezed to 0px:
the rail showed the workspace box and an empty blue box (the active item with
no icon). The rules are now written once for all three modes (accordion,
dropdown, icon rail), and each mode was measured in the harness: every icon
16px wide, nothing outside the rail, no sideways scroll. In the dropdown mode
the workspace list opens beside the rail instead of being cut by it.

The floating names in the collapsed rail never showed: they sat outside the
rail, which clipped them, and they were what gave it a sideways scrollbar. Each
button now carries its name as a title.

### «پیامک‌هایی که به پنل رسید»: columns, pages, no repeated sender

Each row was a flex line with space between, so the time moved with the length
of the text beside it and the columns never lined up. A row is now a grid:
three fixed columns from 640px, two lines on a phone. Both lists (SMS and
deposits) have numbered pages of 10. The panel keeps the last 30 SMS (it
showed only 15). The result no longer repeats the sender («از «+98…»: واریز
نیست»): the sender has its own column.

## [2.3.4] - 2026-10-07

### «تأیید خودکار رسید»: the QR sets up the phone app by itself, and every SMS is signed

In 2.3.3 the QR opened a page with the address, and the owner still had to
paste it into SMS to URL Forwarder and pick the right options by hand. The app
has no link or QR import; it does have Settings → Import of its own rules
file. So now:

1. the QR opens a setup page (a 30-minute code, not the permanent address)
   with one button that downloads `nexora-sms.json`;
2. in the app: ⋮ → Settings → Import → that file. Nothing is typed.

The file is the app's own backup format, checked key by key and type by type
against the app's source code: the panel's address, the app's default
template, and three things a hand setup always missed:

- **Signed SMS.** The app signs each body with HMAC-SHA256. Once one signed SMS
  has arrived, an unsigned one or a wrong signature is refused (401) and shown
  on the page with the reason. Before this, the address alone was enough to
  post a deposit, and the address sits in every proxy log on the way.
- **Only deposit SMS leave the phone.** A text filter (واریز / نشست / به حساب
  شما) keeps one-time codes and personal messages on the phone.
- **Failed sends are kept and retried.** If the server is down for an hour,
  a payment is not lost.

A fixed rule key means importing twice replaces the rule instead of adding a
second one that would send every SMS twice. «آدرس تازه» also makes a new
secret, so a lost phone stops counting.

### The collapsed menu spilled out of its rail

The layers button at the top («جمع کردن منو») shrank the menu to a 68px rail,
but the collapse rules were written for the old flat menu, and the default
menu is now the accordion. Its arrows, group titles and Pro marks, and the
«سرویس فعال» card, kept their width. They spilled out of the rail and gave it
a sideways scrollbar. The rule meant to turn alert counts into dots had never
matched anything (`.fx-side.collapsed`; the class is on `body`). The rail now
shows icons only, with a name on hover and a dot for alerts. The phone drawer
is unchanged.

### Buttons on phones were 32px even where the page asked for 44

The phone rule that gives every button at least 32px sat after Tailwind in the
stylesheet. It won over every page's own `min-h-[44px]`. It is now a floor
(`:where()`), so the larger size a page asks for applies.

## [2.3.3] - 2026-10-07

### «تأیید خودکار رسید»: set up in three steps, and three holes closed

Setup meant typing a 60-character address into a phone app and knowing the
bank's exact sender name. The page is now three steps that turn green by
themselves:

1. install the app (Google Play / F-Droid buttons);
2. scan the QR with the phone's camera: the phone opens a page that says
   "connected" and copies the address;
3. make a small test deposit, then tap «بله، این بانکِ من است» when the
   panel asks. Several cards on different banks: one test deposit each.

Holes found while checking it:

- **Any sender was accepted.** Anyone could text the owner's phone «واریز …
  به حساب شما نشست» from their own number, together with a fake receipt.
  Now only senders the owner trusted with that tap count. A mobile number
  cannot be trusted, since banks never text from one. Senders compare exactly,
  so "xBlu" is not "Blu".
- **A fake receipt could take a real buyer's money.** If two people bought
  the same plan, one paid and had not yet sent the receipt, and the other
  sent a fake receipt, the deposit matched the fake one: the real buyer's
  order was not compared because it was not "awaiting" yet. Any open order of
  the same amount now makes it manual.
- **The same SMS from two phones made two deposits.** The phone's received
  time was part of the duplicate check. When the SMS has its own time, the
  check uses the sender and the text only.

A test now runs the whole path: a real card order, a real receipt, the
bank's SMS through the panel, the config built and delivered.

## [2.3.2] - 2026-10-07

### The phone's SMS was refused before it reached the panel

In 2.3.0 and 2.3.1 every SMS from the phone was answered "send the admin
password" (422), which a phone cannot do, so no deposit ever arrived. The
panel puts a gate in front of each Pro route, and that gate asks for the
admin password everywhere except on routes that authenticate themselves.
The SMS address authenticates with its own token but was not in that
exception. It is now, with the license still checked. The tests had called
the function directly and never went through the gate. A test now sends the
phone's real request through the whole app.

## [2.3.1] - 2026-10-07

### «تأیید خودکار رسید» says what happened to every SMS

The owner set it up, made a test deposit, and saw nothing: no deposit and no
reason why. An SMS the panel ignored (a sender not on the list, a withdrawal,
an amount it could not read) was dropped without a word, so "the phone never
sent it" and "the panel threw it away" looked the same. The page now lists
every SMS that reached the panel with what became of it, naming the sender
when it is the reason. When the list is empty, it says nothing reached the
panel and shows the four things on the phone that cause that: the address
opened in the phone's browser, the exact sender name, the SMS permission,
and battery optimisation.

## [2.3.0] - 2026-10-07

### Card receipts approved by the bank's own SMS

Approving a card payment meant opening each receipt and checking the bank by
hand, and a fake receipt looked like a real one. Now the owner's Android phone
forwards the bank's deposit SMS to the panel (SMS to URL Forwarder), and the
panel approves an order when the money and the receipt agree:

- Same amount, and the SMS and the customer's receipt within 10 minutes of
  each other. Both must be there; whichever arrives second runs the check.
- One deposit, one order, unique both ways. Two orders with the same amount
  at the same time, a wrong amount, a late payment, a fake receipt, or a phone
  that was offline all stay manual. The group and the order show one line:
  «با پیامک بانک تطبیق نخورد — دستی بررسی کنید».
- Approval is the ✅ button's own path: the config is built before the order
  is approved, with commission and coins as before. One deposit can never pay
  two orders, and a resent SMS is ignored.
- Blu Bank's SMS is read to the toman (rial ÷ 10), never the balance line.
  Withdrawals are ignored, and an amount without ریال/تومان is not guessed.
  Only the amount, the time and a fingerprint are kept, never the balance.

«ربات تلگرام» → «تأیید خودکار رسید»: on/off, the phone's address, the
sender, the phone setup steps, a box to test any bank's SMS without approving
anything, and the last deposits with the order each one paid. For the owner's
shop for now; per-reseller later.

## [2.2.3] - 2026-10-06

### Every page measured from 320 to 1920 px

All 57 admin pages were measured at 320, 360, 390, 412, 430, 768, 820, 1024,
1280, 1366 and 1920 px; the reseller portal, the mini app and the
subscription page at 320; dialogs opened on a 320 px phone. No page scrolls
sideways at any width. What was still squeezed on narrow screens is fixed:

- Chart tooltips (every chart): positioned at the middle of the chart, they
  had half its width to fit into, and on a 320 px phone a date range wrapped
  into a 33 px column. They now take the width of their text, never more than
  the screen.
- The tunnel event rows and the server monitor's command row: a 167 px group
  beside the text left the text about 55 px. They wrap onto a second line now.
- Tables on phones: a 7-column table still left one column at 55 px; table
  cells no longer shrink below 64 px (the table scrolls inside its card).
- «کلاینت‌ها»: the amount column was 43 px, so «برای این گروه هیچ نرخی…»
  stood one word a line. It has a minimum width now.

## [2.2.2] - 2026-10-06

### The chat on a phone

«پیام‌ها» (owner) and «چت با مشتری» (reseller portal) share one screen.
Below 820 px it stacked the conversation list above the conversation: an
empty "pick a conversation" box filled the screen, an opened conversation
started below the list, the owner scrolled down to answer, and there was no
way back but scrolling up. Opening one also slid the page sideways, because
"scroll to the last message" scrolled every container up to the page. Now a
phone shows the list or a conversation, as Telegram does. An open
conversation is one screen tall with the reply box on it, ‹ goes back to the
list, and only the message log scrolls. The reply box's placeholder no longer
explains Shift+Enter on a phone, where it wrapped into a clipped second line.

### Pages wider than a phone

Measured at 375 px on every page of the admin panel, the reseller portal and
the mini app. Three pages scrolled sideways because a «۲۴ ساعت / ۷ روز» style
switch was 66 to 85 px too wide; it now scrolls inside its own row. Five
tables (ledger, expenses, firewall rules, intrusion attempts, other servers'
monitoring) squeezed 5 to 7 columns into 60 px cells, one word a line; they
keep readable columns now and scroll inside their card.

## [2.2.1] - 2026-10-06

### A per-GB reseller stayed "settled" while he kept using it

After a settlement, the dashboard and «واسطه‌ها و نرخ» showed 0 for a per-GB
reseller however much he used. The dashboard billed usage only once it had
seen a config made inside the current period, and that check came after the
line that skips configs made before the settlement. A reseller who made his
configs once and was then settled had none, so his usage bill fell out of the
dashboard. The invoice and his own portal showed the right sum all along.
Every billable per-GB group is now billed by usage, the same way the invoice
does it.

### The invoice charged resellers for the owner's own bot sales

A config sold by the owner's bot is the owner's customer. The dashboard always
left it out of a reseller's debt, even when it sat in the reseller's group,
but the invoice, the period page and so the reseller's portal billed it. Now
all of them leave it out and say how many were left out.

### «بررسی حساب‌ها» (Check the accounts)

A button on «واسطه‌ها و نرخ». For every reseller it shows the dashboard's
figure next to the invoice's (they must be the same number), plus each reason
a config is not counted: no rate, never used, before the settlement,
estimated months, sold by your own bot, and the GB × rate line. It found both
defects above.

### «چرا این‌قدر؟» on the Iran server's traffic

«تانل» → «حجمِ ترافیک» explains why an Iran server moves more than expected:
the share that goes to the customers, to the tunnel to the foreign server, to
SSH, and to everything else. It compares that with the foreign servers and
with what the customers really used in 3x-ui. Each finding comes with how to
fix it: a flood or scans on the IP, a service on the Iran server that is not
the tunnel (xray running there directly, a web server), tunnel overhead from
the transport (ws/wss/grpc/KCP), resends to customers, how datacenters bill
in versus out, and Iranian sites going through the tunnel.

The split comes from three iptables chains on the Iran server that only
count. Every rule returns and none accepts or drops, so filtering is
unchanged. They arrive with the panel's update; no agent update is needed.

### The traffic total counted tunnel interfaces twice

The traffic page added a GRE, 6to4 or WireGuard interface on top of the
physical card it rides on, so the same bytes counted twice. Only the physical
card is counted now; tunnel interfaces are listed apart. The first reading
after the update takes a new starting point instead of putting the whole
difference into one hour.

### Restoring a removed bot user

«کاربران ربات» → «فیلتر» → «حذف‌شده» lists removed users, each with a restore
button (for the owner, and for resellers in their portal). The person comes
back; configs deleted from 3x-ui do not.

## [2.2.0] - 2026-10-01

### "This section did not open" after every update

`nexora update` rebuilds the panel and the old page files are gone. A tab
opened before the update still asked for them, and most bot pages showed «این
بخش باز نشد · Failed to fetch dynamically imported module». The panel now
reloads itself once when that happens, and the new version comes up.

### Configs deleted in 3x-ui, for real this time

The cleanup took "half the shop missing at once" for a bad read and then asked
the shop's 3x-ui API to confirm. On the owner's server that API did not
answer, so nothing was ever removed. A bad read is now one that finds none of
the shop's configs; if the read finds any, it read the right panel and the
rest are gone. A config marked gone that shows up in 3x-ui again comes back by
itself. The customer page in «کاربران ربات» hides deleted configs and reads
usage from the same 3x-ui read. Some 3x-ui versions answer an unknown config
with an empty "success" object; that no longer counts as "found".

### The period invoice lost the evening's configs on a UTC server

Config dates are on Tehran's clock; the billing pages' "today" was the
server's. On a server running UTC, from 20:30 to midnight UTC every day a
config made that evening counted as tomorrow and was left out of the current
period page. Both now use Tehran's date.

### Tunnels: iptables, Realm, automatic rollback, speed test

Ideas from XRayMesh, built by us (its license forbids reusing its code):

- **iptables**: the fastest relay, nothing to install. The Iran server
  forwards the ports straight to the foreign server's IP.
- **Realm**: a light TCP and UDP relay, also on the Iran server only.
- **Automatic rollback**: after a tunnel change the server checks that the
  tunnel works; if it does not, it puts the previous version back and says so.
- **Speed test**: «تانل» ← «سرورها» ← «تست سرعت» measures the speed between
  that server and the panel's server.

These need agent 1.7.0; the panel says so when a server's agent is older.

### Calmer pages

The logo spacing control is four steps (the slider filled the wrong way in
right-to-left), custom CSS is folded, the inbound choice is one selector, the
password fields sit in one row, empty states are a third of their height, and
the tunnel dashboard offers a button to make the first tunnel.

## [2.1.3] - 2026-10-01

### The backup bot was built, but where no one would look

The full backup and the management bot (2.1.0) sat under «تنظیمات ظاهری», the
appearance settings, while «ربات تلگرام» ← «بک‌آپ ربات», the page the owner
opened to find them, offered only the old bot-only file. That page is now
«ربات مدیریت و پشتیبان»: the full backup, and the management bot that sends
the same file to Telegram on a schedule. Accounting's «تنظیمات و بک‌آپ» links
to it.

### A tunnel bot of its own

«تانل» ← «ربات تانل» is a new page for a separate Telegram bot. In Telegram it
has its own menu: 📡 تانل‌ها (each tunnel, its engine, on or off, its server
online), 🩺 عیب‌یابی (each server's verdict and what to do), 🖥 سرورها, and 🔄
بررسیِ دوباره. And it speaks up: when a server's connection turns bad it says
so with what to do, and again when it recovers. Before, a broken tunnel showed
only on the diagnosis page. Server health alerts go to it too.

## [2.1.2] - 2026-10-01

### Configs deleted in 3x-ui still showed in the mini app

The cleanup only looked at configs the bot had marked active, while the mini
app listed every config not marked deleted. A config the bot had switched off
but 3x-ui had deleted was in neither, so it stayed. The cleanup now checks
every listed config. And it says why: the bot users page has «همگام‌سازی با
3x-ui», which runs it at once and names, shop by shop, what was removed or why
not; `nexora sweep` prints the same on the server.

### A customer who once blocked the bot was ignored forever

When a broadcast could not reach someone who had blocked the bot, it set the
same flag as a ban, and the bot ignores banned users. So a customer who
unblocked the bot and pressed /start never got an answer again. "Left the
bot" is its own mark now and clears the moment they write; a ban names who
set it. Old unnamed flags are treated as "left": those customers get in when
they come back, and it is on record in the bot events.

### Ban or remove a bot user, for the owner and for resellers

The users list has two new buttons. Ban: the bot and the mini app stop
answering that person (the mini app used to let a banned user in). Remove:
also deletes every config of theirs from 3x-ui and takes them off the list;
orders and payments stay in the accounts. A reseller can do the same for its
own customers only, and its configs are deleted through the billing core, so
usage stays on its bill.

### A volume reseller could not make configs from the portal

The portal's «کانفیگ تازه» offered only volumes that had their own rate row.
A reseller priced per GB had nothing to choose, or only «نامحدود». It now
takes any volume, and «نامحدود» says what it costs: the monthly unlimited
rate when the owner set one.

### Tables, not boxes

«واسطه‌ها و نرخ» lists resellers only; direct-customer groups open on demand,
and a name is not repeated under itself. «قابلیت‌های نماینده‌ها» is four rows.
The reseller's plan cards lost their repeated hints and three-line profit box.

## [2.1.1] - 2026-10-01

### The panel is calmer on every page, not only on six

2.1.0 tidied six pages; the rest still had the same shared parts that made
them long: 18 px card padding, 44 px number steppers with a slider under each
that repeated the stepper, 142 px number tiles, three-line info boxes, tall
switch rows. Those parts are tighter now, so every page shrinks at once. And
where a page wasted the width, it became a table:

- «واسطه‌ها و نرخ» is one table (name, configs, usage, amount due, switch)
  instead of a full-width card per reseller; the reseller editor picks its
  pricing model and payment period from small selectors, not rows of big
  buttons.
- «رویدادهای ربات» is one line per event: what, who, when.
- The sales report's four big cards are one strip.
- Settings that are switched off fold away (trial follow-up, forced channel
  membership) instead of sitting greyed out under the switch.
- The subscription page's section switches are two columns of short rows.
- Inbound advice shows three lines of reasons, the settings table on demand.

Measured on the same screen: trial follow-up 1,322 → 961 px, settings 1,409 →
1,130, bot connection 1,407 → 1,260, inbound advice 1,071 → 916, an event row
79 → 39 px, a reseller row 110 → 56.

### The mini app's home screen

Home showed the three newest subscriptions as full cards, and a config just
deleted in 3x-ui stayed there as "active, 0 MB" until the hourly cleanup. Home
now has one row, «اشتراک‌های من», that opens the subscriptions tab; opening
the mini app runs that shop's cleanup on the spot; and a config with no
volume cap says «نامحدود», not «۰ مگابایت». The cleanup itself runs every 15
minutes now instead of hourly.

## [2.1.0] - 2026-10-01

### Configs deleted in 3x-ui stayed in the bot

The hourly cleanup refused to touch a shop when half its configs vanished at
once, taking that for a bad read of the 3x-ui database. A shop with eight
configs whose owner deleted five test ones looked exactly like that, so the
cleanup skipped it every hour and the deleted configs stayed in the bot. It
now asks the shop's own 3x-ui about each missing config and only stands down
when that panel does not answer. The skip was also listed as "unknown event"
in the bot's events page; the cleanup's events now have names.

### The free-trial button did not show for the owner

Each account sees the trial once, and the owner had used his while testing, so
the button he had just switched on never appeared for him. An admin now always
sees it and can take it again. The plans page also said the trial was on when
the trial plan itself was switched off.

### Some switches saved a page element instead of on/off

The shared switch component handed its click event to the page, and four
settings (trial follow-up, coins, the channel's AI, monitoring) saved that
event as their value. The trial follow-up's Save then failed with "Converting
circular structure to JSON". The switch now passes on/off.

### One backup file for the whole panel

There were three separate backups (settings, bot, accounting), and none held
the tunnels, receipts, logos, license or the panel's secret address. Settings
→ «پنل، رمز و پشتیبان» now downloads one zip with all of it and restores it,
after checking every file's checksum and keeping a copy of the current state.
On the server: `nexora backup` and `nexora restore FILE`.

### A management bot, separate from the sales bot

A second Telegram bot just for the owner: server status, the backup (now or
every 6/12/24 hours), today's sales, a config lookup, restarts and the panel
address. Server and tunnel alerts go to it instead of the sales bot's group
(or to a separate monitoring bot, if one is set). Without it, alerts go where
they went before.

### Calmer pages

- The sales report's daily chart drew only the days that sold, as bars
  stretched across the card: three sales were three walls. It now shows every
  day of the range, and a bar is at most 40 px wide.
- «واسطه‌ها و نرخ» warned «نیاز به تنظیم» for every group whose billing is
  off, which is how the owner's own direct customers are meant to be. Those
  are one quiet line now; the warning is kept for a reseller with no rate.
  Every reseller row shows its amount (also zero), and the editor shows the
  invoice's figure since the last settlement instead of lifetime usage × rate.
- The funnel's four big cards, the inbounds page's three tiles and the
  resellers page's tiles are one strip each; empty feedback boxes and
  zero-cost expense categories fold into a line; history rows are shorter.

## [2.0.1] - 2026-09-30

### The bot's messages read like a person wrote them

About a hundred messages to customers and to the admin group were rewritten in plain
Persian: fewer dashes and filler, no promises the shop did not make, bold only where
the reader has to look. What each message says is unchanged.

### Configs start on first use, and ended ones are cleaned up

Configs the bot made counted their days from the purchase, so a buyer who
connected a week later lost that week. They now start on the first
connection (a switch in the bot settings, on by default), and renewing one
that has not started adds to its days instead of restarting it from today.

A config deleted by hand in 3x-ui stayed in the mini app and in "my
subscriptions" forever. An hourly job in the panel now hides it, and deletes
configs that ended and were not renewed for five days (one day's warning to
the buyer; the number of days is a setting, 0 turns it off). A reseller's
config is deleted through the same code as the portal's delete button, so its
usage and period share stay on the bill.

### Volume resellers can have a monthly rate for unlimited configs

A group with a per-GB price billed every config by usage, so there was no way
to sell a reseller volume configs by usage and unlimited ones at a fixed rate.
A volume group with an unlimited rate now does exactly that on every
accounting page, and the reseller portal makes a real unlimited config for it.

### Mini app and support chat

The mini app showed its splash twice (the page's, then its own). The
subscriptions tab listed a buyer's whole history as full cards; it is paged
now, with live subscriptions first. On many Android phones the chat had no
height limit, so the page grew with every message, and each refresh pulled a
reader back to the bottom; the chat now scrolls inside its own box.

Support replies sent from the bot's admin menu or a ticket printed the whole
text into the bot and never reached the mini app chat, and the panel's "new
reply" notice stopped forever once a buyer had any unread reminder. All
replies now go to the chat with one notice until read, or in full when the
shop has no mini app (where the old "press /start" led nowhere).

### /start

The free trial switch sits next to the plans now, with a line that says why
the green button is or is not shown. The welcome text suggests the mini app.

### Connection diagnosis

A working tunnel over UDP always read "not connected", because only TCP
connections were counted; the kernel's connection table now counts too. A
firewall that drops ping made a working tunnel read "path broken"; when the
tunnel carries traffic such a probe is shown as unanswered instead. The check
ran every minute on every server and now runs hourly by default (your choice
on the page), with "check now" for the moment. Inbound advice names today's
choices: XHTTP with Reality, and a CDN path for when an IP is blocked.

### Panel

Card grids no longer leave a lone card in a half-empty last row. When an
update leaves the panel's UI older than the server, a banner says so and
gives the command that fixes it.

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
