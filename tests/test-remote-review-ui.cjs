const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.dirname(__dirname);
const { build } = require(path.join(ROOT, "frontend/node_modules/esbuild"));
const { JSDOM } = require(path.join(ROOT, "frontend/node_modules/jsdom"));

(async () => {
  if (!fs.existsSync(path.join(ROOT, "frontend/src/pro/mini.jsx"))) {
    console.log("SKIP remote-review mini UI: Pro source absent"); return;
  }
  const result = await build({ stdin: { contents: `import React from "react";
    import {createRoot} from "react-dom/client";
    import {StatusPill} from "./frontend/src/ui/index.jsx";
    import {BotOrdersSection} from "./frontend/src/sections/bot/orders.jsx";
    import {PendingOrders, api} from "./frontend/src/pro/mini.jsx";
    window.miniApi = api;
    window.root = createRoot(document.getElementById("root"));
    window.showAdmin = () => window.root.render(<BotOrdersSection password="test"/>);
    window.showMini = orders => window.root.render(<><StatusPill s="remote_review"/>
      <PendingOrders orders={orders} onOpen={o => window.opened = o.id}/></>);
    window.showAdmin();`, resolveDir: ROOT, loader: "jsx" }, bundle: true, write: false,
    format: "iife", nodePaths: [path.join(ROOT, "frontend/node_modules")],
    define: { "import.meta.env.VITE_API_URL": '""', "process.env.NODE_ENV": '"test"' },
    plugins: [{ name: "test-private-mini-components", setup(b) {
      b.onLoad({ filter: /[\\/]pro[\\/]mini\.jsx$/ }, (args) => ({ loader: "jsx",
        contents: fs.readFileSync(args.path, "utf8") + "\nexport {PendingOrders, api};" }));
    } }] });
  const dom = new JSDOM('<div id="root"></div>', { url: "https://panel.example.com/harness.html",
    runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window, calls = [], errors = [];
  const tick = () => new Promise((r) => setTimeout(r, 60));
  w.console.error = (...args) => errors.push(args.join(" "));
  w.URL.createObjectURL = () => "blob:test-receipt";
  w.URL.revokeObjectURL = () => {};
  w.eval(fs.readFileSync(path.join(ROOT, "tests/harness/harness-boot.js"), "utf8"));
  const fetch = w.fetch;
  w.fetch = (url, opt) => { calls.push({ url, opt }); return fetch(url, opt); };
  try {
    w.eval(result.outputFiles[0].text); await tick(); await tick();
    const tab = [...w.document.querySelectorAll("button")].find((b) => b.textContent.trim() === "در انتظار تطبیق");
    assert(tab, "admin filter exposes remote_review: " + w.document.body.textContent + errors.join(" ")); tab.click(); await tick(); await tick();
    assert(calls.some((c) => c.url.endsWith("/api/admin/bot/orders?status=remote_review")));
    assert(w.document.querySelector(".fx-pill").textContent === "در انتظار تطبیق");
    assert.equal(w.document.querySelectorAll(".ord-act").length, 0, "held order cannot be approved/rejected");
    const orders = (await (await fetch("/api/mini/orders")).json()).orders;
    w.showMini([...orders, { id: 99, status: "approved", plan: "Delivered order" }]); await tick();
    assert(w.document.body.textContent.includes("در انتظار تطبیق تحویل و پرداخت"));
    assert(w.document.body.textContent.includes("منتظر رسید شماست"));
    assert(w.document.body.textContent.includes("رسید فرستاده شده — در انتظار تایید"));
    assert(!w.document.body.textContent.includes("Delivered order"));
    const held = [...w.document.querySelectorAll(".mn-pend-row")].find((el) => el.textContent.includes("در انتظار تطبیق"));
    assert(!held.querySelector(".mn-pend-go"), "no payment arrow on held orders");
    held.click(); assert.equal(w.opened, 4102);
    w.fetch = async () => ({ ok: false, status: 409, json: async () => ({ detail: "پرداخت نگه داشته شده و تحویل نیاز به تطبیق دارد" }) });
    await assert.rejects(() => w.miniApi("/api/mini/buy", { method: "POST", body: { planId: 1 } }),
      /پرداخت نگه داشته شده و تحویل نیاز به تطبیق دارد/);
    assert.deepEqual(errors, []);
    console.log("PASS remote_review: admin pill/filter, no approval/rejection, mini held/pending/awaiting labels, 409 payment-hold detail");
  } finally { w.root?.unmount(); dom.window.close(); }
})().catch((e) => { console.error(e); process.exitCode = 1; });
