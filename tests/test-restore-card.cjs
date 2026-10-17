const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const vm = require("node:vm");
const { createRequire } = require("node:module");
const req = createRequire(path.join(__dirname, "../frontend/package.json"));
const React = req("react");
const { act } = React;
const { createRoot } = req("react-dom/client");
const { JSDOM } = req("jsdom");
const esbuild = req("esbuild");

async function main() {
  const { readRestore, RestoreUnknown } = await import(pathToFileURL(path.join(__dirname,
    "../frontend/src/lib/restore-stream.js")).href);
  const source = fs.readFileSync(path.join(__dirname, "../frontend/src/sections/subpage.jsx"), "utf8");
  const start = source.indexOf("export function BackupCard(");
  const end = source.indexOf("\n}\n", start) + 3;
  const code = esbuild.transformSync(source.slice(start, end).replace("export function", "function") +
    "\nmodule.exports = BackupCard;", { loader: "jsx", format: "cjs" }).code;
  const dom = new JSDOM('<div id="root"></div>', { url: "https://panel.test/secret/" });
  Object.assign(global, { window: dom.window, document: dom.window.document,
    IS_REACT_ACT_ENVIRONMENT: true });
  let controller;
  let refreshes = 0;
  const Icon = () => React.createElement("span");
  const context = { module: { exports: {} }, window: dom.window, React, useState: React.useState,
    useEffect: React.useEffect, readRestore, RestoreUnknown, setInterval, clearInterval,
    setTimeout, Date, Blob, URL, API_URL: "", confirm: () => true,
    fetch: async () => new Response(new ReadableStream({ start(value) { controller = value; } }),
      { headers: { "Content-Type": "application/x-ndjson" } }),
    errMsg: error => error.message, errText: (detail, fallback) => detail || fallback,
    faNum: String, okJson: async response => response.json(),
    Msg: ({ msg }) => React.createElement("div", { "data-kind": msg?.t }, msg?.m),
    Loader2: Icon, Upload: Icon, Download: Icon, ChevronDown: Icon };
  vm.runInNewContext(code, context);
  const BackupCard = context.module.exports;
  const tick = () => new Promise(resolve => setTimeout(resolve, 0));
  const push = event => controller.enqueue(new TextEncoder().encode(JSON.stringify(event) + "\n"));
  let root;
  async function mount() {
    if (root) await act(async () => root.unmount());
    root = createRoot(document.getElementById("root"));
    await act(async () => root.render(React.createElement(BackupCard,
      { password: "test", onRestored: async () => { refreshes++; throw new Error("auth changed"); } })));
    const input = document.querySelector('input[accept=".zip,application/zip"]');
    Object.defineProperty(input, "files", { configurable: true, value: [new dom.window.File(["zip"], "backup.zip")] });
    await act(async () => { input.dispatchEvent(new dom.window.Event("change", { bubbles: true })); await tick(); });
    return input;
  }
  const input = await mount();
  assert.equal(input.disabled, true);
  await act(async () => { push({ phase: "verify" }); await tick(); });
  assert.match(document.querySelector('[role="status"]').textContent, /بررسی سلامت/);
  await act(async () => { push({ phase: "restore", completed: 2, total: 4 }); await tick(); });
  assert.match(document.querySelector('[role="status"]').textContent, /2 از 4 فایل/);
  await act(async () => {
    push({ phase: "complete", result: { restored: ["config.json"], from: "2.3.8" } });
    controller.close(); await tick();
  });
  assert.equal(refreshes, 1);
  assert.match(document.body.textContent, /بازیابی انجام شد/);
  assert.equal(document.querySelector('[data-kind="ok"]') !== null, true);
  const second = await mount();
  await act(async () => { push({ phase: "verify" }); controller.close(); await tick(); });
  assert.match(document.body.textContent, /نامشخص/);
  assert.equal(second.disabled, true);
  assert.equal(refreshes, 1);
  await act(async () => root.unmount());
  dom.window.close();
  console.log("2 restore card journeys passed (live progress, refresh failure, unknown result)");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
