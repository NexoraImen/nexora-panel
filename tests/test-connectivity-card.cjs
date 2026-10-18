const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createRequire } = require("node:module");
const req = createRequire(path.join(__dirname, "../frontend/package.json"));
const React = req("react");
const { act } = React;
const { createRoot } = req("react-dom/client");
const { JSDOM } = req("jsdom");
const source = fs.readFileSync(path.join(__dirname, "../frontend/src/sections/system.jsx"), "utf8");
const start = source.indexOf("export function ConnectivityCard(");
const end = source.indexOf("\n}\n", start) + 3;
const code = req("esbuild").transformSync(source.slice(start, end).replace("export function", "function") +
  "\nmodule.exports = ConnectivityCard;", { loader: "jsx", format: "cjs" }).code;

async function main() {
  const dom = new JSDOM('<div id="root"></div>', { url: "https://panel.test/secret/" });
  Object.assign(global, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
  let state = { state: "connected", services: { telegram: "managed", github: "direct" } };
  let failing = false;
  const calls = [];
  const context = { module: { exports: {} }, React, useState: React.useState, useEffect: React.useEffect,
    API_URL: "", setInterval: () => 1, clearInterval: () => {},
    fetch: async (url, options) => {
      calls.push([url, options]);
      if (failing) throw new Error("network unavailable");
      return { ok: true, json: async () => state };
    },
    okJson: async response => response.json(),
    Msg: ({ msg }) => React.createElement("div", { role: "alert" }, msg?.m) };
  vm.runInNewContext(code, context);
  let root;
  async function mount() {
    if (root) await act(async () => root.unmount());
    root = createRoot(document.getElementById("root"));
    await act(async () => root.render(React.createElement(context.module.exports, { password: "test-password" })));
  }
  await mount();
  assert.match(document.body.textContent, /مسیر مدیریت‌شده/);
  assert.match(document.body.textContent, /اتصال مستقیم/);
  assert.equal(document.querySelectorAll("input").length, 0);
  assert.equal(calls[0][1].headers["X-Admin-Password"], "test-password");
  await act(async () => document.querySelector("button").click());
  assert.equal(calls.at(-1)[0], "/api/admin/connectivity/check");
  assert.equal(calls.at(-1)[1].method, "POST");
  state = { state: "provider_unconfigured", services: {} };
  await mount();
  assert.match(document.body.textContent, /ارائه‌دهنده آماده نشده/);
  state = { state: "agent_unavailable", services: {} };
  await mount();
  assert.match(document.body.textContent, /گزارش تازه‌ای نداده/);
  failing = true;
  await mount();
  assert.match(document.querySelector('[role="alert"]').textContent, /network unavailable/);
  await act(async () => root.unmount());
  dom.window.close();
  console.log("Connectivity card: managed/direct, recheck, provider, stale agent and failure states passed.");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
