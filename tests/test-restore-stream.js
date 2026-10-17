const assert = require("node:assert/strict");

async function main() {
  const { readRestore, RestoreUnknown } = await import("../frontend/src/lib/restore-stream.js");
  const response = (text, split = false) => {
    const bytes = new TextEncoder().encode(text);
    return new Response(new ReadableStream({ start(controller) {
      for (let i = 0; i < bytes.length; i += split ? 3 : bytes.length) {
        controller.enqueue(bytes.slice(i, i + (split ? 3 : bytes.length)));
      }
      controller.close();
    } }), { headers: { "Content-Type": "application/x-ndjson" } });
  };
  const events = [];
  const result = await readRestore(response(
    JSON.stringify({ phase: "verify" }) + "\n" +
    JSON.stringify({ phase: "restore", completed: 3, total: 4 }) + "\n" +
    JSON.stringify({ phase: "complete", result: { restored: ["تنظیمات"], from: "2.3.8" } }), true),
    event => events.push(event));
  assert.deepEqual(result.restored, ["تنظیمات"]);
  assert.equal(events[1].completed, 3);
  await assert.rejects(readRestore(response('{"phase":"verify"}\n'), () => {}), RestoreUnknown);
  await assert.rejects(readRestore(response('invalid JSON\n'), () => {}), RestoreUnknown);
  await assert.rejects(readRestore(response('{"phase":"failed","message":"disk full"}\n'), () => {}),
    error => !(error instanceof RestoreUnknown) && error.message === "disk full");
  const old = await readRestore(Response.json({ restored: ["config.json"] }), () => {});
  assert.deepEqual(old.restored, ["config.json"]);
  const originalTimer = global.setTimeout;
  try {
    global.setTimeout = (fn, ms, ...args) => originalTimer(fn, ms === 45000 ? 1 : ms, ...args);
    await assert.rejects(readRestore(new Response(new ReadableStream({}),
      { headers: { "Content-Type": "application/x-ndjson" } }), () => {}), RestoreUnknown);
  } finally { global.setTimeout = originalTimer; }
  console.log("6 restore stream scenarios passed");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
