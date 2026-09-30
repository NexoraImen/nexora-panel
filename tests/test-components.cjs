/**
 * هر کامپوننت را واقعاً رندر می‌کند.
 *
 * چرا وجود دارد:
 *     ConfirmModal به createPortal آرگومان مقصد نمی‌داد. نتیجه‌اش خطای
 *     React #200 و سیاه‌شدن کل صفحه بود — هر بار که کاربر دکمه‌ی
 *     «بستن آی‌پی» را می‌زد.
 *
 *     تست‌های الگویی این را نگرفتند چون کد از نظر متنی سالم به نظر
 *     می‌رسید؛ فقط اجرای واقعی لوش می‌دهد. و test-panel-runtime هم
 *     نگرفت چون فقط صفحه‌ی اول را رندر می‌کند و هیچ مودالی باز نمی‌شود.
 *
 *     پس این فایل تک‌تک کامپوننت‌های رابط را با داده‌ی واقعی رندر
 *     می‌کند و مطمئن می‌شود هیچ‌کدام خطا نمی‌دهند.
 *
 * اجرا:  node tests/test-components.cjs
 */
const path = require("path");
// esbuild plus Vite's import.meta.glob, expanded from disk (tests/esbuild-glob.cjs).
const { buildSync: globBuildSync } = require("./esbuild-glob.cjs");
const fs = require("fs");

const ROOT = path.dirname(__dirname);
const G = "\x1b[38;5;42m", R = "\x1b[38;5;203m",
      D = "\x1b[38;5;245m", X = "\x1b[0m";
let ok = 0, fail = 0;

function check(name, cond, detail) {
  if (cond) {
    ok++;
    console.log(`  ${G}✓${X} ${name}` + (detail ? ` ${D}— ${detail}${X}` : ""));
  } else {
    fail++;
    console.log(`  ${R}✗${X} ${name}` + (detail ? ` ${D}— ${detail}${X}` : ""));
  }
}
function head(t) { console.log(`\n${D}── ${t} ──${X}`); }

let JSDOM;
try {
  ({ JSDOM } = require("jsdom"));
} catch {
  console.log("jsdom پیدا نشد.  npm i jsdom  را در frontend اجرا کنید");
  process.exit(1);
}

// ═══════════ محیط مرورگر ═══════════
const dom = new JSDOM("<!doctype html><html><body><div id=root></div></body></html>",
                      { pretendToBeVisual: true, url: "https://panel.test/" });
global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;
global.HTMLElement = dom.window.HTMLElement;
global.Element = dom.window.Element;
global.Node = dom.window.Node;
global.localStorage = dom.window.localStorage;
//: هر چیزی که رابط از سرور خواست، این‌جا می‌ماند.
//
//  بعضی باگ‌ها فقط در *آدرس* دیده می‌شوند، نه در چیزی که رندر شده:
//  فیلدی که مقدارش به کوئری نمی‌چسبد، دقیقاً همان‌قدر سالم به نظر
//  می‌رسد که فیلدی که می‌چسبد.
const asked = [];
let reply = {};
global.fetch = (url) => {
  asked.push(String(url));
  const body = typeof reply === "function" ? reply(String(url)) : reply;
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
    blob: () => Promise.resolve({}),
  });
};
global.IS_REACT_ACT_ENVIRONMENT = true;
// jsdom این دو را نمی‌سازد و CountUp بدونشان می‌افتد
global.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16);
global.cancelAnimationFrame = (id) => clearTimeout(id);

let React, ReactDOMServer;
try {
  React = require("react");
  ReactDOMServer = require("react-dom/server");
} catch (e) {
  console.log("react پیدا نشد:", e.message);
  process.exit(1);
}

// ═══════════ ساخت ماژول‌های JSX ═══════════
let esbuild;
try {
  esbuild = require("esbuild");
} catch {
  console.log("esbuild پیدا نشد — همراه vite نصب می‌شود");
  process.exit(1);
}

const OUT = path.join(ROOT, "frontend", ".test-build");
fs.rmSync(OUT, { recursive: true, force: true });

globBuildSync({
  entryPoints: [path.join(ROOT, "frontend", "src", "ui", "index.jsx")],
  bundle: true,
  format: "cjs",
  platform: "node",
  outfile: path.join(OUT, "ui.cjs"),
  jsx: "automatic",
  external: ["react", "react-dom", "react-dom/server", "lucide-react"],
  logLevel: "silent",
  // import.meta.env مال Vite است و در Node وجود ندارد؛ بدون این،
  // خود بارگذاری ماژول می‌افتد و هیچ تستی اجرا نمی‌شود.
  define: { "import.meta.env.VITE_API_URL": '"http://localhost:8100"' },
});

const UI = require(path.join(OUT, "ui.cjs"));

// ═══════════ رندر ═══════════
function render(name, el) {
  try {
    const html = ReactDOMServer.renderToStaticMarkup(el);
    return { ok: true, html };
  } catch (e) {
    return { ok: false, err: e.message };
  }
}

head("مودال‌ها — همان‌جا که صفحه سیاه می‌شد");

// createPortal در رندر سمت سرور کار نمی‌کند، پس مستقیم در مرورگر
// جعلی mount می‌کنیم — همان مسیری که کاربر طی می‌کند.
let ReactDOMClient;
try {
  ReactDOMClient = require("react-dom/client");
} catch (e) {
  console.log("react-dom/client پیدا نشد:", e.message);
  process.exit(1);
}

const { act } = require("react");

function mount(name, el) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOMClient.createRoot(host);
  let err = null;
  try {
    act(() => { root.render(el); });
  } catch (e) {
    err = e;
  }
  const html = document.body.innerHTML;
  try { act(() => { root.unmount(); }); } catch { /* مهم نیست */ }
  host.remove();
  return { err, html };
}

const noop = () => {};

let r = mount("ConfirmModal", React.createElement(UI.ConfirmModal, {
  title: "بستن این آی‌پی",
  desc: "۴۵.۹.۱۴۸.۷ با ۱۲۰ تلاش ناموفق بسته می‌شود.",
  confirmLabel: "بستن",
  onConfirm: noop,
  onCancel: noop,
}));
check("ConfirmModal بدون خطا رندر می‌شود", !r.err,
      r.err ? String(r.err.message).slice(0, 90) : "همان باگ صفحه‌ی سیاه");
check("ConfirmModal متنش را نشان می‌دهد",
      !r.err && r.html.includes("بستن این آی‌پی"));
check("ConfirmModal دکمه‌ی تایید دارد",
      !r.err && r.html.includes("بستن"));

r = mount("Modal", React.createElement(UI.Modal, {
  title: "ویرایش", onClose: noop,
  children: React.createElement("div", null, "محتوا"),
}));
check("Modal بدون خطا رندر می‌شود", !r.err,
      r.err ? String(r.err.message).slice(0, 90) : "");

head("اجزای پایه");

const CASES = [
  ["Field", { label: "نام", children: React.createElement("input") }],
  ["Toggle", { checked: true, onChange: noop, label: "فعال" }],
  ["SectionHead", { title: "بخش", desc: "توضیح" }],
  ["EmptyState", { text: "چیزی نیست" }],
  ["InfoBox", { children: "یک نکته" }],
  ["InfoBox", { children: "هشدار", tone: "warn" }],
  ["Collapse", { title: "جزئیات فنی", children: "بدنه" }],
  ["Collapse", { title: "باز", open: true, children: "بدنه" }],
  ["MiniMarkdown", { text: ["### Fixed", "- **یک** مورد با `code`", "- دومی", "", "پاراگراف"].join("\n") }],
  ["MiniMarkdown", { text: "" }],
  ["StatusChip", { ok: true }],
  ["Msg", { msg: { t: "ok", m: "انجام شد" } }],
  ["Msg", { msg: { t: "err", m: "ناموفق" } }],
  ["Msg", { msg: null }],
  ["Toast", { message: "ذخیره شد", type: "ok" }],
  ["CountUp", { value: 1234 }],
  ["StatTile", { label: "فروش", value: "۱۲۳" }],
  ["Segmented", { value: 7, onChange: noop, items: [[7, "۷"], [30, "۳۰"]] }],
  ["NumberStepper", { value: 5, onChange: noop, min: 0, max: 10 }],
  ["Sparkline", { data: [1, 5, 3, 8, 2] }],
  ["AreaChart", { data: [4, 9, 2, 11, 7, 3], label: "روند" }],
  // یک نقطه: نباید بیفتد، باید پیام «داده کافی نیست» بدهد
  ["AreaChart", { data: [5] }],
  ["AreaChart", { data: [] }],
  // مقدار خراب لای داده‌ی درست — نباید NaN وارد مسیر SVG کند
  ["AreaChart", { data: [3, null, 7, NaN, 5, undefined, 2] }],
  ["Tabs", { items: [{ key: "a", label: "یک" }, { key: "b", label: "دو" }],
             active: "a", onChange: noop }],
  // بدون آیکون — قبلاً همین حالت کل بخش را می‌انداخت
  ["EmptyState", { text: "بدون آیکون" }],
];

for (const [name, props] of CASES) {
  const C = UI[name];
  if (!C) { check(`${name} export شده`, false, "در ui/index.jsx نیست"); continue; }
  const res = mount(name, React.createElement(C, props));
  check(`${name} بدون خطا رندر می‌شود`, !res.err,
        res.err ? String(res.err.message).slice(0, 80) : "");
}

head("مرز خطا");

function Boom() { throw new Error("انفجار عمدی"); }
r = mount("ErrorBoundary", React.createElement(
  UI.ErrorBoundary, null, React.createElement(Boom)));
check("مرز خطا جلوی سقوط را می‌گیرد", !r.err,
      "کامپوننت داخلش عمداً خطا داد");
check("مرز خطا پیام نشان می‌دهد",
      !r.err && r.html.includes("این بخش باز نشد"));
check("مرز خطا می‌گوید بقیه سالم است",
      !r.err && r.html.includes("بقیه‌ی پنل سالم است"));

// ═══════════ صفحه‌ی صورتحساب ═══════════
//
// شکایت مالک: فاکتور تمدیدهای دوره‌های تسویه‌شده را دوباره حساب
// می‌کرد. حالا یک فیلد تاریخ دارد و آن تاریخ باید واقعاً به سرور
// برسد — چیزی که فقط با mount کردن واقعی معلوم می‌شود.
async function invoiceScreen() {
  head("صفحه‌ی صورتحساب — تاریخ باید به سرور برسد");
  // Accounting is Pro (src/pro/billing.jsx); the Community tree has none.
  const INV_SRC = path.join(ROOT, "frontend", "src", "pro", "billing.jsx");
  if (!fs.existsSync(INV_SRC)) {
    console.log(`  ${D}Community tree: no src/pro/billing.jsx, invoice screen not checked here${X}`);
    return;
  }

  globBuildSync({
    entryPoints: [INV_SRC],
    bundle: true,
    format: "cjs",
    platform: "node",
    outfile: path.join(OUT, "billing.cjs"),
    jsx: "automatic",
    external: ["react", "react-dom", "react-dom/server", "lucide-react"],
    logLevel: "silent",
    define: { "import.meta.env.VITE_API_URL": '"http://localhost:8100"' },
  });
  const B = require(path.join(OUT, "billing.cjs"));

  const OVERVIEW = {
    ready: true,
    groups: [{
      name: "unlimited", key: "unlimited", label: "unlimited",
      billed: true, billable: true, configs: 40,
      settledUntil: "2026-06-17", periodStart: "2025-01-01",
    }],
  };
  const INVOICE = {
    label: "unlimited",
    since: "2026-06-17", sinceWhy: "تسویه‌شده تا", sinceJalali: "1405/03/27",
    items: [{ email: "user_01", gb: 0, months: 3, renewals: 3,
              certain: false, drift: 1, lineTotal: 570000 }],
    totalAmount: 22770000, paid: 2000000, balance: 20770000,
    unpricedVolumes: [], unpricedWhy: [],
    totals: { before: 2, beforeMonths: 6, due: 22770000 },
  };
  asked.length = 0;
  reply = (u) => (u.includes("/invoice/") ? INVOICE : OVERVIEW);

  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOMClient.createRoot(host);
  const settle = () => act(async () => {
    await new Promise((r) => setTimeout(r, 30));
  });

  try {
    await act(async () => {
      root.render(React.createElement(B.BillingInvoice, { password: "x" }));
    });
    await settle();

    const txt = () => host.textContent;
    const btn = (label) => [...host.querySelectorAll("button")]
      .find((b) => b.textContent.includes(label));

    check("فیلد «حساب کن از تاریخ» هست", txt().includes("حساب کن از تاریخ"));
    check("و وقتی خالی است می‌گوید پیش‌فرض چیست",
          txt().includes("خالی یعنی از"),
          "فاکتورِ کوتاه نباید غافلگیرکننده باشد");

    const gen = btn("نمایش صورتحساب");
    check("دکمه‌ی نمایش صورتحساب هست", !!gen);
    if (gen) {
      await act(async () => { gen.click(); });
      await settle();
      check("بالای فاکتور می‌گوید از کی حساب شده",
            txt().includes("تا امروز"), "۱۴۰۵/۰۳/۲۷ تا امروز");
      check("و می‌گوید چند کانفیگ کنار ماند و چرا",
            txt().includes("روی این فاکتور نیامد"));
    }

    const urls = asked.filter((u) => u.includes("/invoice/"));
    check("مسیر فاکتور قطعه‌ی جعلی ندارد",
          urls.length > 0 && urls.every((u) => !u.includes("/pdf:")),
          urls[0] || "");

    const picker = btn("پیش‌فرضِ همین گروه");
    check("انتخابگر تاریخ باز می‌شود", !!picker);
    if (picker) {
      await act(async () => { picker.click(); });
      // تقویم با portal روی body می‌نشیند، نه داخل host
      const day = [...document.body.querySelectorAll("button")]
        .find((b) => /^[۰-۹]+$/.test(b.textContent.trim()));
      check("تقویم روزهایش را نشان می‌دهد", !!day,
            "اگر داخل والدِ transform‌دار حبس شود، هیچ روزی رندر نمی‌شود");
      if (day) {
        await act(async () => { day.click(); });
        await settle();
        const gen2 = btn("نمایش صورتحساب");
        await act(async () => { gen2.click(); });
        await settle();
        const last = asked[asked.length - 1];
        check("تاریخ انتخاب‌شده واقعاً به سرور می‌رسد",
              /\?start=\d{4}-\d{2}-\d{2}$/.test(last), last);
      }
    }
  } catch (e) {
    check("صفحه‌ی صورتحساب بدون خطا کار می‌کند", false,
          String(e.message).slice(0, 90));
  } finally {
    try { await act(async () => { root.unmount(); }); } catch { /* مهم نیست */ }
    host.remove();
  }
}


head("هیچ createPortal بی‌مقصد نماند");

const uiSrc = fs.readFileSync(
  path.join(ROOT, "frontend", "src", "ui", "index.jsx"), "utf8");
const portals = uiSrc.split("createPortal(").length - 1;
const targets = (uiSrc.match(/document\.body,?\s*\)/g) || []).length;
check("هر createPortal مقصد دارد", portals > 1 && targets >= portals - 1,
      `${portals} پرتال · ${targets} مقصد`);

invoiceScreen().then(() => {
  fs.rmSync(OUT, { recursive: true, force: true });

  console.log(`\n${D}${"─".repeat(46)}${X}`);
  console.log(`  ${fail ? R : G}${ok} پاس${X}` + (fail ? ` · ${R}${fail} ناموفق${X}` : ""));
  console.log();
  process.exit(fail ? 1 : 0);
}, (e) => {
  // بدون این، شکستِ بخش ناهمگام یک unhandled rejection می‌شد و تست
  // با کد صفر تمام می‌شد — یعنی سبز، در حالی که چیزی اجرا نشده.
  console.log(`  ${R}✗${X} بخش صورتحساب اجرا نشد ${D}— ${e.message}${X}`);
  process.exit(1);
});
