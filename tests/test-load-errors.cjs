/**
 * خطای خواندن باید دیده شود — نه «خالی است».
 *
 * چرا وجود دارد:
 *     بیست‌وشش جای پنل `fetch(...).then((r) => r.json())` داشتند و وضعیت
 *     را نمی‌سنجیدند، و چند جا خطا را کلاً می‌بلعیدند. نتیجه هر بار یک
 *     دروغِ آرام بود:
 *       - فایروال «ufw نصب نیست» می‌گفت و دستورِ نصب می‌داد، روی سروری
 *         که ufw داشت؛
 *       - کارتِ بازگردانی «هنوز نسخه‌ای نیست» می‌گفت؛
 *       - آی‌پی‌های بسته‌شده «۰» می‌گفت؛
 *       - فرمِ نگهداری با مقدارهای خالی باز می‌شد و «ذخیره» `{error: true}`
 *         را روی سرور می‌نوشت؛
 *       - کانفیگِ سرورِ خارج خالی بود و دکمه‌ی کپی داشت.
 *
 *     `test-ui-safety` شکلِ متنیِ این اشتباه را رد می‌کند. این فایل رفتار
 *     را می‌سنجد: هر صفحه را با پاسخِ ۵۰۰ برای مسیرِ خودش واقعاً mount
 *     می‌کند و می‌بیند دلیلِ سرور روی صفحه آمده یا نه.
 *
 * اجرا:  NODE_PATH=frontend/node_modules node tests/test-load-errors.cjs
 */
const path = require("path");
// esbuild plus Vite's import.meta.glob, expanded from disk (tests/esbuild-glob.cjs).
const { buildSync: globBuildSync } = require("./esbuild-glob.cjs");
const fs = require("fs");

const ROOT = path.dirname(__dirname);
const G = "\x1b[38;5;42m", R = "\x1b[38;5;203m", D = "\x1b[38;5;245m", X = "\x1b[0m";
let ok = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) ok++; else fail++;
  console.log(`  ${cond ? G + "✓" : R + "✗"}${X} ${name}` + (detail ? ` ${D}— ${detail}${X}` : ""));
}

let JSDOM, esbuild;
try { ({ JSDOM } = require("jsdom")); } catch {
  console.log("jsdom پیدا نشد.  npm i jsdom  را در frontend اجرا کنید"); process.exit(1);
}
try { esbuild = require("esbuild"); } catch {
  console.log("esbuild پیدا نشد — همراه vite نصب می‌شود"); process.exit(1);
}

// ═══════════ محیط مرورگر ═══════════
const dom = new JSDOM("<!doctype html><html><body></body></html>",
                      { pretendToBeVisual: true, url: "https://panel.test/" });
for (const k of ["window", "document", "navigator", "HTMLElement", "Element", "Node", "localStorage"]) {
  global[k] = k === "window" ? dom.window : dom.window[k];
}
global.IS_REACT_ACT_ENVIRONMENT = true;
global.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16);
global.cancelAnimationFrame = (id) => clearTimeout(id);
dom.window.matchMedia = global.matchMedia = () => ({
  matches: false, addListener() {}, removeListener() {},
  addEventListener() {}, removeEventListener() {},
});

//: مسیری که باید بشکند؛ بقیه یک شیءِ خالیِ موفق می‌گیرند
let failRe = null, tag = "";
const LICENSED = { pro: true, state: "active", features: {}, denials: {},
                   entitlements: ["mini_app", "loyalty", "affiliates", "resellers", "accounting",
                                  "diagnostics", "insights", "channel", "monitoring_multi", "subpage_templates"] };
global.fetch = (url, opts) => {
  const u = String(url).split("?")[0];
  const get = !opts || !opts.method || opts.method === "GET";
  const bad = failRe && get && failRe.test(u);
  // پوسته‌ی پرتال بی‌`me` به صفحه‌ی ورود برمی‌گردد؛ پاسخِ معقول می‌گیرد
  const body = bad ? { detail: tag }
    : /\/api\/portal\/me$/.test(u) ? { id: 1, name: "فروشگاه", slug: "shop", portalGroup: "g" }
    // Licensed, so Pro pieces inside core screens (the dashboard's debt card)
    // ask their routes; in the Community tree they are absent and say so.
    : /\/api\/admin\/license$/.test(u) ? LICENSED
    : {};
  return Promise.resolve({
    ok: !bad, status: bad ? 500 : 200,
    json: () => Promise.resolve(body),
    blob: () => Promise.resolve({}),
    headers: { get: () => null },
  });
};

// ═══════════ ساخت ═══════════
const OUT = path.join(ROOT, "frontend", ".test-build");
fs.mkdirSync(OUT, { recursive: true });
const S = (f) => JSON.stringify(path.join(ROOT, "frontend", "src", "sections", f).split(path.sep).join("/"));
// Pro screens (docs/specs/2026-09-29-pro-split.md) are checked only when their
// file is in this tree; the Community tree has no src/pro/ and says so below.
const PRO_SRC = path.join(ROOT, "frontend", "src", "pro");
const hasPro = (f) => fs.existsSync(path.join(PRO_SRC, f));
const P = (f) => JSON.stringify(path.join(PRO_SRC, f).split(path.sep).join("/"));
const entry = path.join(OUT, "load-errors-entry.jsx");
fs.writeFileSync(entry, [
  `export { BotReportSection } from ${S("bot/stats.jsx")};`,
  ...(hasPro("insights.jsx") ? [`export { default as BotStatsSection } from ${P("insights.jsx")};`] : []),
  `export { ThemesSection } from ${S("bot/themes.jsx")};`,
  ...(hasPro("affiliates.jsx") ? [`export { BotAffiliates } from ${P("affiliates.jsx")};`] : []),
  `export { RollbackCard, UpdateCard, SystemSection } from ${S("system.jsx")};`,
  `export { UsageHistoryCard, TopClientsCard, MaintenanceCard } from ${S("monitoring.jsx")};`,
  ...(hasPro("nodes-monitor.jsx") ? [`export { NodesMonitor } from ${P("nodes-monitor.jsx")};`] : []),
  ...(hasPro("tunnel.jsx") ? [`export { TunnelOverview, NodeDiagnoseModal, TunnelMonitorModal, TunnelConfigModal } from ${P("tunnel.jsx")};`] : []),
  ...(hasPro("firewall.jsx") ? [`export { FirewallRules, FirewallBlocked } from ${P("firewall.jsx")};`] : []),
  ...(hasPro("expenses.jsx") ? [`export { BillingExpenses, BillingLedger } from ${P("expenses.jsx")};`] : []),
  ...(hasPro("mini.jsx") ? [`export { default as Mini } from ${P("mini.jsx")};`] : []),
  ...(hasPro("portal/index.jsx") ? [`export { default as Portal } from ${P("portal/index.jsx")};`] : []),
  `export { BotOrdersSection } from ${S("bot/orders.jsx")};`,
  `export { BotUsersSection } from ${S("bot/users.jsx")};`,
  `export { BotPlansSection } from ${S("bot/plans.jsx")};`,
  `export { BotEventsSection } from ${S("bot/events.jsx")};`,
  `export { BotInboxSection } from ${S("bot/inbox.jsx")};`,
  ...(hasPro("discounts.jsx") ? [`export { BotDiscountsSection } from ${P("discounts.jsx")};`] : []),
  ...(hasPro("coins.jsx") ? [`export { BotCoinsSection } from ${P("coins.jsx")};`] : []),
  `export { BotTextsSection } from ${S("bot/texts.jsx")};`,
  `export { BotSection } from ${S("bot/connection.jsx")};`,
  ...(hasPro("channel.jsx") ? [`export { default as ChannelSection } from ${P("channel.jsx")};`] : []),
  `export { OverviewSection } from ${S("subpage.jsx")};`,
  ...(hasPro("intrusion.jsx") ? [`export { FirewallIntrusion } from ${P("intrusion.jsx")};`] : []),
  ...(hasPro("portal-admin.jsx") ? [`export { PortalAdmin, ResellerFeatures, ResellerInbounds } from ${P("portal-admin.jsx")};`] : []),
  `export { BillingSettings } from ${S("billing-settings.jsx")};`,
  ...(hasPro("billing.jsx") ? [`export { BillingClients, BillingPayments, BillingDash, BillingInvoice, BillingPeriod, BillingGroups } from ${P("billing.jsx")};`] : []),
].join("\n"));
globBuildSync({
  entryPoints: [entry], bundle: true, format: "cjs", platform: "node",
  outfile: path.join(OUT, "load-errors.cjs"), jsx: "automatic",
  external: ["react", "react-dom", "react-dom/client", "react-dom/server", "lucide-react"],
  logLevel: "silent",
  define: { "import.meta.env.VITE_API_URL": '"http://localhost:8100"' },
  loader: { ".js": "jsx" },
});
const React = require("react");
const { act } = React;
const ReactDOMClient = require("react-dom/client");
const C = require(path.join(OUT, "load-errors.cjs"));

const tick = () => act(async () => { await new Promise((r) => setTimeout(r, 30)); });

async function mountFailing(Comp, props, route, i) {
  failRe = new RegExp(route);
  tag = `FAKE-500-${i}`;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOMClient.createRoot(host);
  let err = null;
  const origErr = console.error;
  console.error = () => {};
  try {
    await act(async () => { root.render(React.createElement(Comp, props)); });
    for (let k = 0; k < 6; k++) await tick();
  } catch (e) { err = e; }
  const text = document.body.textContent || "";
  try { await act(async () => { root.unmount(); }); } catch { /* مهم نیست */ }
  console.error = origErr;
  host.remove();
  document.body.innerHTML = "";
  return { err, shown: text.includes(tag), text };
}

const pw = { password: "x" };
const noop = () => {};
const tunnel = { id: 1, name: "t1" };
const CASES = [
  ...(hasPro("insights.jsx") ? [["قیفِ تبدیل", C.BotStatsSection, pw, "/bot/funnel$"]] : []),
  ["گزارشِ فروش", C.BotReportSection, pw, "/bot/users/report$"],
  ["قالب‌ها", C.ThemesSection, { ...pw, config: {}, setConfig: noop }, "/api/admin/themes$"],
  ...(hasPro("affiliates.jsx") ? [["همکاری در فروش", C.BotAffiliates, pw, "/bot/affiliates$"]] : []),
  ["بازگردانی — نه «نسخه‌ای نیست»", C.RollbackCard, pw, "/api/admin/snapshots$"],
  ["بررسیِ نسخه — نه «تنظیم نشده»", C.UpdateCard, pw, "/api/admin/check-update$"],
  ["وضعیتِ سیستم", C.SystemSection, pw, "/api/admin/system$"],
  ["تاریخچه‌ی مصرف", C.UsageHistoryCard, pw, "/api/admin/usage-history$"],
  ["پرمصرف‌ترین مشتری‌ها", C.TopClientsCard, pw, "/api/admin/top-clients$"],
  ["نگهداری — نه فرمِ خالی", C.MaintenanceCard, pw, "/api/admin/maintenance$"],
  ...(hasPro("nodes-monitor.jsx") ? [
    ["سرورهای دیگر — نه «سروری نیست»", C.NodesMonitor, pw, "/api/admin/tunnel/overview$"],
  ] : []),
  ...(hasPro("tunnel.jsx") ? [
    ["داشبوردِ تانل", C.TunnelOverview, pw, "/api/admin/tunnel/overview$"],
    ["چرا نود آفلاین است", C.NodeDiagnoseModal, { ...pw, nodeId: 1, onClose: noop }, "/tunnel/node/1/check$"],
    ["کیفیتِ تانل", C.TunnelMonitorModal, { ...pw, tunnel, onClose: noop }, "/tunnel/1/metrics$"],
    ["کانفیگِ خارج — نه جعبه‌ی خالی با دکمه‌ی کپی", C.TunnelConfigModal, { ...pw, tunnel, onClose: noop }, "/tunnel/1/config$"],
  ] : []),
  ...(hasPro("billing.jsx") ? [["واسطه‌ها و نرخ", C.BillingGroups, pw, "/billing/groups$"]] : []),
  ...(hasPro("firewall.jsx") ? [
    ["قواعدِ فایروال — نه «ufw نصب نیست»", C.FirewallRules, pw, "/api/admin/firewall$"],
    ["آی‌پی‌های بسته‌شده — نه «۰»", C.FirewallBlocked, pw, "/api/admin/firewall/blocked$"],
  ] : []),
  ...(hasPro("expenses.jsx") ? [
    ["نرخِ ارز در هزینه‌ها", C.BillingExpenses, pw, "/billing/fx$"],
    ["فهرستِ هزینه‌ها", C.BillingExpenses, pw, "/billing/expenses$"],
    ["دفترِ کل", C.BillingLedger, pw, "/billing/ledger$"],
  ] : []),
  ...(hasPro("billing.jsx") ? [
    ["همه‌ی کاربرانِ حسابداری", C.BillingClients, pw, "/billing/clients$"],
    ["پرداخت‌ها", C.BillingPayments, pw, "/billing/payments$"],
    ["داشبوردِ حسابداری", C.BillingDash, pw, "/billing/groups$"],
    ["صورتحساب — فهرستِ واسطه‌ها", C.BillingInvoice, pw, "/billing/groups$"],
    ["صورتحسابِ دوره — فهرستِ واسطه‌ها", C.BillingPeriod, pw, "/billing/groups$"],
  ] : []),
  // Core: the x-ui path and the backup stay free (a lapse never stops a backup).
  ["تنظیماتِ حسابداری", C.BillingSettings, pw, "/billing/xui-path$"],
  ["سفارش‌های ربات", C.BotOrdersSection, pw, "/bot/orders$"],
  ["کاربرانِ ربات", C.BotUsersSection, pw, "/bot/users$"],
  ["پلن‌های ربات", C.BotPlansSection, pw, "/bot/plans$"],
  ["رویدادهای ربات", C.BotEventsSection, pw, "/bot/events$"],
  ["پیام‌ها", C.BotInboxSection, pw, "/bot/inbox$"],
  ...(hasPro("discounts.jsx") ? [["کدهای تخفیف", C.BotDiscountsSection, pw, "/bot/discounts$"]] : []),
  ...(hasPro("coins.jsx") ? [["سکه و دعوت", C.BotCoinsSection, pw, "/bot/settings$"]] : []),
  ["متن‌ها و یادآوری‌ها", C.BotTextsSection, pw, "/bot/settings$"],
  ["اتصال و تنظیماتِ ربات", C.BotSection, pw, "/bot/status$"],
  ...(hasPro("intrusion.jsx") ? [["تلاش برای نفوذ", C.FirewallIntrusion, pw, "/firewall/intrusion$"]] : []),
  ...(hasPro("portal-admin.jsx") ? [
    ["نماینده‌ها و دسترسی", C.PortalAdmin, pw, "/tenant/portal-list$"],
    ["اینباندِ نماینده‌ها", C.ResellerInbounds, pw, "/tenant/portal-list$"],
    // سه منبعِ جدا در یک کارت: هر کدام که نیاید، دلیلش باید روی صفحه باشد
    ["قابلیت‌های نماینده‌ها · پوسته", C.ResellerFeatures, pw, "/api/admin/portal-addon$"],
    ["قابلیت‌های نماینده‌ها · فروشگاه", C.ResellerFeatures, pw, "/api/admin/store-addon$"],
    ["قابلیت‌های نماینده‌ها · تست", C.ResellerFeatures, pw, "/api/admin/reseller-trial$"],
    ["قابلیت‌های نماینده‌ها · نامحدود", C.ResellerFeatures, pw, "/api/admin/reseller-unlimited$"],
  ] : []),
  // خواندنِ تنظیماتِ ربات که شکست بخورد، ذخیره‌ی بعدی (PUTِ جایگزین‌کننده)
  // همه‌چیز را پاک می‌کرد — خطا باید دیده شود، نه فرمی با پیش‌فرض‌ها
  ...(hasPro("discounts.jsx") ? [["پیگیریِ تست — نه فرمِ پیش‌فرض", C.BotDiscountsSection, pw, "/bot/settings$"]] : []),
  ["پاسخ‌های آماده — نه ذخیره‌ی خالی", C.BotInboxSection, pw, "/bot/settings$"],
  ...(hasPro("channel.jsx") ? [
    ["کانال", C.ChannelSection, pw, "/api/admin/channel$"],
    ["آدرسِ کانال — نه ذخیره‌ی خالی", C.ChannelSection, pw, "/bot/settings$"],
    // Sub-panels that do not hold the page, but are not silent either.
    ["کانال — پیشنهادها", C.ChannelSection, pw, "/channel/suggestions$"],
    ["کانال — وضعیتِ هوش مصنوعی", C.ChannelSection, pw, "/channel/ai$"],
  ] : []),
  ...(hasPro("billing.jsx") ? [
    ["داشبوردِ اشتراک — بدهیِ نماینده‌ها", C.OverviewSection,
     { ...pw, config: {}, stats: {}, navigate: noop, dirty: false }, "/billing/overview$"],
  ] : []),
];

(async () => {
  console.log(`\n${D}── خطای خواندن روی صفحه دیده می‌شود (${CASES.length} صفحه) ──${X}`);
  if (!hasPro("channel.jsx")) console.log(`  ${D}Community tree: no src/pro/, Pro screens not checked here${X}`);
  for (let i = 0; i < CASES.length; i++) {
    const [name, Comp, props, route] = CASES[i];
    if (typeof Comp !== "function") { check(name, false, "کامپوننت export نشده"); continue; }
    const r = await mountFailing(Comp, props, route, i);
    check(name, !r.err && r.shown,
          r.err ? `کرش: ${String(r.err.message).slice(0, 80)}` : r.shown ? "" : `دلیلِ سرور روی صفحه نیامد (${route})`);
  }
  // ── پرتالِ نماینده: کلِ اپ با توکن، صفحه از آدرس (#) ──
  //
  // صفحه‌های پرتال export نشده‌اند و پشتِ ورودند؛ پس خودِ اپ mount می‌شود.
  // مسیرِ هر صفحه جدا شکسته می‌شود، نه مسیرهای پوسته (me، summary، …) —
  // وگرنه خطای پوسته «دلیل» را نشان می‌داد و صفحه‌ی خراب سبز می‌شد.
  console.log(`
${D}── پرتالِ نماینده ──${X}`);
  // The reseller portal is Pro (src/pro/portal/); none in the Community tree.
  const PORTAL = !hasPro("portal/index.jsx") ? [] : [
    ["پرتال · سفارش‌ها", "orders", "/api/portal/orders$"],
    ["پرتال · پلن‌ها", "plans", "/api/portal/bot-plans$"],
    ["پرتال · ربات و پرداخت", "bot", "/api/portal/bot$"],
    ["پرتال · پوسته‌ی مینی‌اپ", "theme", "/api/portal/theme$"],
    ["پرتال · مشتری‌ها", "users", "/api/portal/users$"],
    ["پرتال · چت", "chat", "/api/portal/inbox$"],
    ["پرتال · متن‌ها و قفلِ کانال", "texts", "/api/portal/bot-settings$"],
    ["پرتال · رویدادها", "events", "/api/portal/events$"],
    // The funnel card is Pro (insights): nothing to check in the Community tree.
    ...(hasPro("insights.jsx") ? [["پرتال · قیفِ فروش در داشبورد", "home", "/api/portal/funnel$"]] : []),
  ];
  for (let i = 0; i < PORTAL.length; i++) {
    const [name, page, route] = PORTAL[i];
    localStorage.setItem("nexora_portal_token", "t");
    dom.reconfigure({ url: `https://panel.test/r/shop#${page}` });
    const r = await mountFailing(C.Portal, {}, route, 500 + i);
    check(name, !r.err && r.shown,
          r.err ? `کرش: ${String(r.err.message).slice(0, 80)}` : r.shown ? "" : `دلیلِ سرور روی صفحه نیامد (${route})`);
  }
  localStorage.removeItem("nexora_portal_token");

  // ── مینی‌اپِ مشتری ──
  //
  // سفارش‌های باز مهم‌ترین مورد است: اگر بی‌صدا خالی شوند، مشتری فکر
  // می‌کند رسیدش نرسیده و دوباره پول می‌دهد.
  console.log(`
${D}── مینی‌اپ ──${X}`);
  // The mini app is Pro (src/pro/mini.jsx); none in the Community tree.
  const MINI = !hasPro("mini.jsx") ? [] : [
    ["مینی‌اپ · حسابِ من", "/api/mini/me$"],
    ["مینی‌اپ · اشتراک‌ها", "/api/mini/subs$"],
    ["مینی‌اپ · پلن‌ها", "/api/mini/plans$"],
    ["مینی‌اپ · سفارش‌های باز — نه «سفارشی ندارید»", "/api/mini/orders$"],
  ];
  // بیرون از تلگرام اپ فقط «از داخلِ تلگرام باز کنید» نشان می‌دهد. یک
  // WebAppِ ساختگی: هر متدِ SDK یک هیچ‌کارِ بی‌خطر است.
  const noop = new Proxy(function () {}, {
    get: (t, k) => (k === "then" ? undefined : k === Symbol.toPrimitive ? () => "" : noop),
    apply: () => undefined,
  });
  const WEBAPP = { initData: "query_id=test", initDataUnsafe: {}, colorScheme: "dark",
                   themeParams: {}, platform: "tdesktop", version: "7.10",
                   safeAreaInset: { top: 0, bottom: 0 }, contentSafeAreaInset: { top: 0, bottom: 0 } };
  dom.window.Telegram = { WebApp: new Proxy(WEBAPP, { get: (t, k) => (k in t ? t[k] : noop) }) };
  for (let i = 0; i < MINI.length; i++) {
    const [name, route] = MINI[i];
    dom.reconfigure({ url: "https://panel.test/app" });
    const r = await mountFailing(C.Mini, {}, route, 700 + i);
    check(name, !r.err && r.shown,
          r.err ? `کرش: ${String(r.err.message).slice(0, 80)}` : r.shown ? "" : `دلیلِ سرور روی صفحه نیامد (${route})`);
  }
  delete dom.window.Telegram;
  dom.reconfigure({ url: "https://panel.test/" });

  // Community tree: the debt card on the dashboard says accounting is not in
  // this build, in words, instead of an empty card or a 404 shown as a failure.
  if (!hasPro("billing.jsx")) {
    const r = await mountFailing(C.OverviewSection,
      { ...pw, config: {}, stats: {}, navigate: noop, dirty: false }, "/billing/overview$", 998);
    check("Community: the debt card says why it is empty", !r.err && !r.shown && r.text.includes("بسته‌ی Pro"),
          r.err ? String(r.err.message).slice(0, 80) : "");
  }

  // نشانه‌ی اینکه آزمون کور نیست: بدونِ شکستن، همان برچسب نباید دیده شود
  const blind = await mountFailing(C.BotOrdersSection, pw, "^$never", 999);
  check("آزمون کور نیست — بدونِ خطا، برچسب دیده نمی‌شود", !blind.shown);

  // پوشه‌ی ساخت در .gitignore نیست؛ اگر بماند، release-check درختِ کثیف می‌بیند
  fs.rmSync(entry, { force: true });
  fs.rmSync(path.join(OUT, "load-errors.cjs"), { force: true });
  try { fs.rmdirSync(OUT); } catch { /* test-components هم از همین پوشه استفاده می‌کند */ }
  console.log(`\n  ${fail ? R : G}${ok} پاس · ${fail} ناموفق${X}\n`);
  process.exit(fail ? 1 : 0);
})();
