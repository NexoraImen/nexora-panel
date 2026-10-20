// Render the real component against the same stateful API fixtures as the preview.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.dirname(__dirname);
const { build } = require(path.join(ROOT, "frontend/node_modules/esbuild"));
const { JSDOM } = require(path.join(ROOT, "frontend/node_modules/jsdom"));
const source = fs.readFileSync(path.join(ROOT, "frontend/src/sections/remote-xui.jsx"), "utf8");
const backend = fs.readFileSync(path.join(ROOT, "backend/remote_xui.py"), "utf8");
assert.equal(source.match(/const FRESH_SECONDS = (\d+)/)[1], backend.match(/^FRESH_SECONDS = (\d+)/m)[1], "snapshot display expiry must match backend");

async function main() {
  const result = await build({ stdin: { contents: `import React from "react";
    import {createRoot} from "react-dom/client";
    import {RemoteXuiSection} from "./frontend/src/sections/remote-xui.jsx";
    window.root = createRoot(document.getElementById("root"));
    window.root.render(<RemoteXuiSection password="test-password"/>);`, resolveDir: ROOT, loader: "jsx" },
    bundle: true, write: false, format: "iife", nodePaths: [path.join(ROOT, "frontend/node_modules")],
    define: { "import.meta.env.VITE_API_URL": '""', "process.env.NODE_ENV": '"test"' } });
  const tick = () => new Promise((r) => setTimeout(r, 40));
  const boot = async (query = "") => {
    const dom = new JSDOM('<div id="root"></div>', { url: "https://panel.example.com/harness.html" + query,
      runScripts: "outside-only", pretendToBeVisual: true });
    const w = dom.window, calls = [], copied = [], errors = [];
    w.console.error = (...args) => errors.push(args.join(" "));
    w.eval(fs.readFileSync(path.join(ROOT, "tests/harness/harness-boot.js"), "utf8"));
    const fetch = w.fetch;
    w.fetch = async (url, options = {}) => {
      calls.push({ url, ...options });
      const reply = await fetch(url, options);
      const json = await reply.json();
      return { ...reply, json: async () => JSON.parse(JSON.stringify(json)) };
    };
    Object.defineProperty(w.navigator, "clipboard", { value: { writeText: async (text) => copied.push(text) } });
    w.eval(result.outputFiles[0].text); await tick(); await tick();
    const text = () => w.document.body.textContent;
    const buttons = (label) => [...w.document.querySelectorAll("button")].filter((b) => b.textContent === label);
    const click = async (label) => { const b = buttons(label).find((b) => !b.disabled); assert(b, label); b.click(); await tick(); };
    const change = async (label, value) => {
      const el = w.document.querySelector(`[aria-label="${label}"]`); assert(el, label);
      const proto = el.tagName === "INPUT" ? w.HTMLInputElement.prototype : w.HTMLSelectElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
      el.dispatchEvent(new w.Event(el.tagName === "INPUT" ? "input" : "change", { bubbles: true })); await tick();
    };
    const close = () => { assert.deepEqual(errors, []); w.root.unmount(); dom.window.close(); };
    return { w, calls, copied, text, buttons, click, change, close };
  };

  const ui = await boot();
  try {
    assert(ui.text().includes("اطلاعات تازه است"), ui.text());
    assert(ui.text().includes("اطلاعات قدیمی است"), "online heartbeat must not hide stale snapshot");
    assert(ui.text().includes("اطلاعات موجود نیست"));
    assert(ui.text().includes("دریافت اطلاعات: ۲ ساعت پیش"));
    assert(ui.text().includes("منبع فعلی"));
    assert(ui.w.document.querySelector('option[value="iran-revoked"]').disabled);
    const year = new Intl.DateTimeFormat("fa-IR", { year: "numeric", timeZone: "Asia/Tehran" }).format(new Date());
    assert(ui.text().includes(year), "timestamps use Persian calendar");
    await ui.change("سرور 3x-ui", "iran-stale"); await ui.click("ذخیره اتصال");
    assert(ui.text().includes("اطلاعات تازه از سرور"), "backend rejection must be visible");
    await ui.change("سرور 3x-ui", "iran-primary"); await ui.click("ذخیره اتصال");
    assert.deepEqual(JSON.parse(ui.calls.filter((c) => c.method === "PUT").at(-1).body), { mode: "remote", region: "foreign", node_id: "iran-primary" });
    await ui.change("حالت اتصال", "local"); await ui.click("ذخیره اتصال");
    assert.equal(JSON.parse(ui.calls.filter((c) => c.method === "PUT").at(-1).body).node_id, null);
    assert(ui.text().includes("منبع راه دور قبلی"));
    assert(!ui.text().includes("منبع فعلی"));
    const gets = ui.calls.filter((c) => !c.method).length; await tick();
    assert.equal(ui.calls.filter((c) => !c.method).length, gets, "no polling");
    await ui.click("تازه‌سازی"); assert.equal(ui.calls.filter((c) => !c.method).length, gets + 1);
    assert(ui.buttons("ساخت کد یک‌بارمصرف")[0].disabled);
    await ui.change("نام سرور", "  سرور آزمایشی  "); await ui.click("ساخت کد یک‌بارمصرف");
    assert.deepEqual(JSON.parse(ui.calls.find((c) => c.method === "POST").body), { name: "سرور آزمایشی", region: "iran" });
    const command = ui.w.document.querySelector('[aria-label="دستور نصب"]'); assert(command.readOnly);
    assert(command.value.includes("curl --fail")); assert(command.value.includes("&& python3"));
    assert(command.value.includes("--panel https://panel.example.com --code harness-only-code-1"));
    assert(!command.value.includes("|"));
    await ui.click("کپی دستور نصب"); assert.equal(ui.copied[0], command.value);
    assert(!Object.values(ui.w.localStorage).join().includes("harness-only-code"));
    assert(!Object.values(ui.w.sessionStorage).join().includes("harness-only-code"));
    await ui.click("پنهان‌کردن کد و دستور"); assert(!ui.w.document.querySelector('[aria-label="کد اتصال"]'));
    await ui.click("لغو اتصال"); assert(ui.w.document.querySelector('[role="dialog"]'));
    await ui.click("انصراف"); assert(!ui.calls.some((c) => c.method === "DELETE"));
    await ui.click("لغو اتصال");
    ui.w.document.querySelector('[role="dialog"] button:last-child').click(); await tick();
    assert(ui.calls.some((c) => c.method === "DELETE" && c.url.endsWith("/node/iran-primary")));
    assert(ui.text().includes("اتصال سرور لغو شد"));
    const beforeRepair = await (await ui.w.fetch("/api/admin/remote-xui")).json();
    assert.equal(beforeRepair.nodes.find((n) => n.id === "iran-primary").revoked, 1);
    const posts = ui.calls.filter((c) => c.method === "POST").length;
    await ui.click("اتصال دوباره");
    const dialog = ui.w.document.querySelector('[role="dialog"]');
    assert(dialog.textContent.includes("همان سرور 3x-ui و همان منبع حسابداری"));
    assert(dialog.textContent.includes("توکن قبلی بلافاصله باطل می‌شود"));
    assert(dialog.textContent.includes("شناسه و تاریخچه حذف نمی‌شوند"));
    await ui.click("انصراف");
    assert.equal(ui.calls.filter((c) => c.method === "POST").length, posts, "cancel does not rotate token");
    await ui.click("اتصال دوباره");
    ui.w.document.querySelector('[role="dialog"] button:last-child').click(); await tick(); await tick();
    assert(ui.calls.some((c) => c.method === "POST" && c.url === "/api/admin/remote-xui/node/iran-primary/pair"));
    const repairCommand = ui.w.document.querySelector('[aria-label="دستور نصب"]');
    assert(repairCommand.readOnly && repairCommand.value.endsWith(" --re-enroll"));
    assert.equal(ui.w.document.querySelectorAll('[aria-label="کد اتصال"]').length, 1, "reuse existing pairing panel");
    const afterRepair = await (await ui.w.fetch("/api/admin/remote-xui")).json();
    assert.deepEqual(afterRepair.nodes.map((n) => n.id), beforeRepair.nodes.map((n) => n.id));
    assert.equal(afterRepair.selected, beforeRepair.selected);
    assert.equal(afterRepair.nodes.find((n) => n.id === "iran-primary").snapshot_at, null);
    await ui.change("حالت اتصال", "remote"); await ui.click("ذخیره اتصال");
    assert(ui.text().includes("اطلاعات تازه از سرور"), "repaired source still requires fresh data");
    const adminCalls = ui.calls.filter((c) => c.headers);
    assert(adminCalls.length > 0 && adminCalls.every((c) => c.headers["X-Admin-Password"] === "test-password"));
  } finally { ui.close(); }
  const recovery = await boot("?xui=uncertain");
  try {
    assert(recovery.text().includes("نتیجهٔ این فرمان‌ها نامشخص است"));
    assert(recovery.text().includes("/panel/api/inbounds/addClient"));
    assert(!recovery.calls.some((c) => c.method === "POST"), "never resolve automatically");
    await recovery.click("تأیید بررسی نتیجه"); await recovery.click("انصراف");
    assert(!recovery.calls.some((c) => c.method === "POST"));
    const fetch = recovery.w.fetch;
    for (const detail of ["اطلاعات تازه از سرور دریافت نشده", "سفارش در انتظار تطبیق مالی است", "نتیجه نهایی فرمان از ایجنت دریافت نشده"]) {
      recovery.w.fetch = (url, options) => options?.method === "POST"
        ? Promise.resolve({ ok: false, status: 409, json: async () => ({ detail }) })
        : fetch(url, options);
      await recovery.click("تأیید بررسی نتیجه");
      await recovery.click("نتیجه را روی سرور بررسی و سفارش و پرداخت را تطبیق داده‌ام");
      assert(recovery.text().includes(detail));
      assert.equal(recovery.buttons("تأیید بررسی نتیجه").length, 1, "failed review stays actionable without force-clear");
    }
    recovery.w.fetch = fetch;
    await recovery.click("تأیید بررسی نتیجه");
    await recovery.click("نتیجه را روی سرور بررسی و سفارش و پرداخت را تطبیق داده‌ام");
    const resolve = recovery.calls.find((c) => c.method === "POST");
    assert.equal(resolve.url, "/api/admin/remote-xui/command/uncertain-1/resolve");
    assert.deepEqual(JSON.parse(resolve.body), { reviewed: true });
    assert.equal(recovery.buttons("تأیید بررسی نتیجه").length, 0);
    assert(recovery.text().includes("فرمان دوباره اجرا نشد"));
    assert.equal(recovery.calls.filter((c) => c.method === "POST").length, 1, "review sends no replay");
  } finally { recovery.close(); }
  const held = await boot("?xui=orders");
  try {
    assert.equal(held.w.document.querySelectorAll('a[href="#/bot-orders"]').length, 2);
    assert(held.text().includes("سفارش #4101 در انتظار تطبیق تحویل و پرداخت است؛ تلاش مجدد و برگشت خودکار متوقف است."));
    assert(held.text().includes("فروشگاه 1") && held.text().includes("فروشگاه 2"));
    assert.equal(held.buttons("تأیید بررسی نتیجه").length, 0, "financial holds remain visible even without uncertain commands");
    assert(!held.calls.some((c) => c.method), "financial hold does not trigger writes");
  } finally { held.close(); }
  for (const [query, expected] of [["?xui=empty", "هنوز سروری متصل نشده"], ["?xui=error", "دریافت وضعیت سرور 3x-ui ناموفق بود"]]) {
    const page = await boot(query);
    try { assert(page.text().includes(expected)); if (query.includes("empty")) {
      await page.change("حالت اتصال", "remote"); assert(page.buttons("ذخیره اتصال")[0].disabled);
    } } finally { page.close(); }
  }
  console.log("PASS remote-xui: real UI + stateful harness, freshness parity, local/remote save, errors, manual reload, pairing/copy/no persistence, revoke/cancel, uncertain review/rejections/no replay, financial holds/order links, empty/error states");
}
main().catch((e) => { console.error(e); process.exitCode = 1; });
