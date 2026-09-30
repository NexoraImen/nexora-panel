#!/usr/bin/env node
/**
 * پاسخِ ساختگیِ هارنس برای چند مسیر — تا با پاسخِ واقعیِ بکند مقایسه شود.
 *
 * چرا: هارنس داده‌ی خودش را دارد و هیچ‌چیز آن را با بکند هم‌شکل نگه
 * نمی‌داشت. در یک روز چهار مسیر پیدا شد که شکلِ کهنه داشتند (قیف،
 * سفارش‌ها، رویدادهای تانل، فروشِ نماینده) — هر کدام یا باگی را پنهان
 * می‌کرد یا باگی جعلی می‌ساخت. test-contract.py این را صدا می‌زند.
 *
 *   node tests/harness/harness-shapes.cjs /api/admin/bot/funnel /api/admin/...
 *   → JSON: { "<path>": <response> | {"__error": "..."} }
 *
 * خروجی انگلیسی/JSON است — ابزارِ تشخیصی.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const paths = process.argv.slice(2);
const src = fs.readFileSync(path.join(__dirname, "harness-boot.js"), "utf8");

const store = {};
const storage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
  clear: () => { for (const k of Object.keys(store)) delete store[k]; },
};
const win = {
  location: { search: "", pathname: "/harness.html", hostname: "localhost", origin: "http://localhost", href: "http://localhost/harness.html" },
  history: { replaceState() {}, pushState() {} },
  localStorage: storage, sessionStorage: storage,
  navigator: { userAgent: "node" },
  matchMedia: () => ({ matches: false, addListener() {}, removeListener() {} }),
  addEventListener() {}, removeEventListener() {},
  setTimeout, clearTimeout, setInterval, clearInterval,
  Promise, JSON, Math, Date, URLSearchParams, Error, Proxy, Object, Array, String, Number,
  console,
};
win.window = win;
win.self = win;
win.document = { documentElement: { dataset: {}, classList: { add() {}, remove() {} }, style: { setProperty() {} } },
                 addEventListener() {}, createElement: () => ({ style: {}, setAttribute() {} }),
                 head: { appendChild() {} }, body: { appendChild() {} } };
win.fetch = () => Promise.reject(new Error("no real fetch"));

vm.createContext(win);
try {
  vm.runInContext(src, win, { filename: "harness-boot.js" });
} catch (e) {
  console.log(JSON.stringify({ __boot_error: String(e && e.stack || e) }));
  process.exit(0);
}

(async () => {
  const out = {};
  for (const p of paths) {
    try {
      const r = await win.fetch("http://localhost:8100" + p, { method: "GET" });
      out[p] = await r.json();
    } catch (e) {
      out[p] = { __error: String(e && e.message || e) };
    }
  }
  process.stdout.write(JSON.stringify(out));
})();
