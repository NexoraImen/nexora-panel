const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.dirname(__dirname);
const { build } = require(path.join(root, 'frontend/node_modules/esbuild'));
const { JSDOM } = require(path.join(root, 'frontend/node_modules/jsdom'));

(async () => {
  const bundle = await build({ stdin: { contents: `import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {hydrateMedia,PrivateImage} from './frontend/src/lib/private-media.js';
    import {Avatar} from './frontend/src/ui/index.jsx';
    const data={messages:Array.from({length:300},(_,i)=>({body:'Support text',photo:'/api/private-media/'+String(i).padStart(32,'0')}))};
    const registered=hydrateMedia(data,{'X-Portal-Token':'test-shop-session'});
    window.synchronous=registered===data;
    window.root=createRoot(document.getElementById('root'));
    window.showAvatar=()=>window.root.render(<Avatar name="Customer" id={1} src={data.messages[0].photo}/>);
    window.showBacklog=()=>window.root.render(<main>{Array.from({length:8},(_,i)=><PrivateImage key={i} src={'/api/private-media/'+String(i+1000).padStart(32,'0')}/>)}</main>);
    window.showUnmount=()=>window.root.render(<PrivateImage src={'/api/private-media/'+'9'.repeat(32)}/>);
    window.root.render(<main><p>Support text stays usable</p><button onClick={()=>window.clicked=true}>Reply</button>
      {data.messages.slice(0,12).map((m,i)=><PrivateImage key={i} src={m.photo} loading={i===11?'lazy':i===10?'eager':undefined}/>)}</main>);`, loader: 'jsx', resolveDir: root },
    bundle: true, write: false, format: 'iife', define: { 'import.meta.env.VITE_API_URL': '""' },
    nodePaths: [path.join(root, 'frontend/node_modules')] });
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://panel.example/r/shop', runScripts: 'dangerously' });
  const w = dom.window;
  const pending = [];
  const observers = [];
  w.IntersectionObserver = class {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe(element) { this.element = element; }
    disconnect() { this.disconnected = true; }
  };
  let calls = 0;
  let active = 0, maximum = 0;
  w.fetch = async (url, options) => {
    calls++;
    assert.equal(options.headers['X-Portal-Token'], 'test-shop-session');
    assert(!String(url).includes('test-shop-session'), 'Credentials must stay in headers');
    active++; maximum = Math.max(maximum, active);
    return new Promise((resolve) => pending.push(() => { active--; resolve({ ok: false, status: 404 }); }));
  };
  const tick = () => new Promise((resolve) => setTimeout(resolve, 30));
  w.eval(bundle.outputFiles[0].text);
  await tick(); await tick();
  assert(w.synchronous, 'Registering media must never wait on downloads');
  assert.equal(maximum, 4);
  assert(w.document.body.textContent.includes('Support text stays usable'));
  w.document.querySelector('button').click();
  assert(w.clicked, 'Actions remain usable during remote image requests');
  for (let i = 0; i < 6; i++) { pending.splice(0).forEach((resolve) => resolve()); await tick(); }
  assert.equal(calls, 11, 'Default/eager fetch normally; offscreen lazy attachment must not fetch');
  assert.equal(observers.length, 1);
  observers[0].callback([{ isIntersecting: false }]);
  await tick();
  assert.equal(calls, 11);
  observers[0].callback([{ isIntersecting: true }]);
  await tick();
  assert.equal(calls, 12, 'Visible lazy attachment starts its authenticated fetch');
  pending.splice(0).forEach((resolve) => resolve());
  await tick();
  assert.equal(w.document.querySelectorAll('[role="img"]').length, 12);
  assert(w.document.body.textContent.includes('تصویر در دسترس نیست'));
  assert(w.document.querySelector('button'), 'Failed attachments must not remove actions');
  assert.equal(maximum, 4);
  w.showAvatar();
  await tick();
  pending.splice(0).forEach((resolve) => resolve());
  await tick();
  assert.equal(w.document.querySelector('.fx-avatar').textContent, 'C', 'Avatar fetch failure restores its existing initials fallback');
  assert(!w.document.body.textContent.includes('تصویر در دسترس نیست'), 'Tiny avatar must not show attachment prose');
  const realSetTimeout = w.setTimeout.bind(w), realClearTimeout = w.clearTimeout.bind(w);
  const deadlines = new Map(), backlog = [];
  let now = 0, timerId = 1000000;
  w.setTimeout = (fn, ms, ...args) => {
    if (ms !== 20000) return realSetTimeout(fn, ms, ...args);
    deadlines.set(++timerId, { due: now + ms, fn });
    return timerId;
  };
  w.clearTimeout = (id) => deadlines.delete(id) || realClearTimeout(id);
  const advance = (ms) => {
    now += ms;
    for (const [id, timer] of [...deadlines]) if (timer.due <= now) { deadlines.delete(id); timer.fn(); }
  };
  w.fetch = (url, options) => {
    assert.equal(options.headers['X-Portal-Token'], 'test-shop-session');
    return new Promise((resolve, reject) => {
      backlog.push({ resolve, signal: options.signal });
      options.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    });
  };
  w.showBacklog(); await tick();
  assert.equal(backlog.length, 4);
  assert.equal(deadlines.size, 4, 'Queued work has no network deadline before receiving a slot');
  advance(19000);
  backlog.slice(0,4).forEach((r) => r.resolve({ ok: false }));
  await tick();
  assert.equal(backlog.length, 8);
  advance(2000); await tick();
  assert(backlog.slice(4).every((r) => !r.signal.aborted), 'Backlog receives its full timeout after starting, even after 20 seconds mounted');
  const pngBytes = w.atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==');
  const png = new w.Blob([Uint8Array.from(pngBytes, (ch) => ch.charCodeAt(0))], { type: 'image/png' });
  backlog.slice(4).forEach((r) => r.resolve({ ok: true, blob: async () => png }));
  await tick(); await tick();
  assert.equal(w.document.querySelectorAll('img').length, 4);
  assert([...w.document.querySelectorAll('img')].every((img) => img.src.startsWith('data:image/png;base64,')));
  assert.equal(deadlines.size, 0, 'Completed reads clear their deadlines');
  w.showUnmount(); await tick();
  assert.equal(deadlines.size, 1);
  w.root.unmount(); dom.window.close();
  assert.equal(deadlines.size, 0, 'Unmount clears active read deadlines');
  const harness = new JSDOM('', { url: 'https://panel.example/harness.html', runScripts: 'outside-only' });
  try {
    harness.window.eval(require('node:fs').readFileSync(path.join(root, 'tests/harness/harness-boot.js'), 'utf8'));
    const request = async (url, body) => (await harness.window.fetch('/api/admin/channel/' + url,
      body ? { method: 'PUT', body: JSON.stringify(body) } : undefined)).json();
    assert.equal((await request('ai')).automation.enabled, false);
    await request('automation', { enabled: true, topic: 'Saved topic', cadence_minutes: 60 });
    const saved = (await request('ai')).automation;
    assert(saved.enabled && saved.topic === 'Saved topic' && saved.cadence_minutes === 60 && saved.next_run > Date.now() / 1000);
    await request('automation', { enabled: false });
    const disabled = (await request('ai')).automation;
    assert(!disabled.enabled && disabled.next_run === null && disabled.topic === 'Saved topic');
  } finally { harness.window.close(); }
  console.log('PrivateImage: authenticated bounded background reads, failure isolation, usable text/actions passed');
})().catch((error) => { console.error(error); process.exitCode = 1; });
