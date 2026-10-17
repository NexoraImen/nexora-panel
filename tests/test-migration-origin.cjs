const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const root = path.join(__dirname, '..');
const req = createRequire(path.join(root, 'frontend/package.json'));
const esbuild = req('esbuild');
const source = fs.readFileSync(path.join(root, 'frontend/src/lib/constants.js'), 'utf8');
for (const [value, expected] of [['""', ''], ['undefined', 'http://localhost:8100'],
  ['"https://api.example.test"', 'https://api.example.test']]) {
  const code = esbuild.transformSync(source, { format: 'cjs',
    define: { 'import.meta.env.VITE_API_URL': value } }).code;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: req });
  assert.equal(module.exports.API_URL, expected);
}

const html = fs.readFileSync(path.join(root, 'sub-page-index.html'), 'utf8');
const start = html.indexOf('async function fetchRemoteConfig()');
const end = html.indexOf('\n        //', html.indexOf('\n        }', start) + 11);
const fn = html.slice(start, html.indexOf('\n        }', start) + 10);
async function checkRemote(ok) {
  const warning = { hidden: true };
  const context = { SUBPAGE_CONFIG_API: 'https://panel.test', URLSearchParams, Date,
    AbortSignal: { timeout: () => undefined }, sanaeiTemplateData: { emails: [] },
    window: { location: { hostname: 'sub.test' } },
    document: { getElementById: () => warning }, console: { warn() {} },
    fetch: async () => ({ ok, status: ok ? 200 : 502, json: async () => ({ brand: 'restored' }) }) };
  vm.createContext(context);
  const result = await vm.runInContext(fn + '\nfetchRemoteConfig()', context);
  assert.equal(warning.hidden, ok);
  assert.equal(result?.brand ?? null, ok ? 'restored' : null);
}
Promise.all([checkRemote(true), checkRemote(false)]).then(() => {
  console.log('5 migration origin and subscription fallback checks passed');
}).catch(error => { console.error(error); process.exitCode = 1; });
