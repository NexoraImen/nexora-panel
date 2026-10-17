// A lost response is not proof that a destructive server operation failed.
export class RestoreUnknown extends Error {}

export async function readRestore(res, onProgress) {
  if (!(res.headers.get("Content-Type") || "").includes("application/x-ndjson")) {
    try { return await res.json(); }
    catch { throw new RestoreUnknown("پاسخ نهایی خوانده نشد؛ نتیجهٔ بازیابی نامشخص است. دوباره فایل نفرستید."); }
  }
  if (!res.body?.getReader) throw new RestoreUnknown("مرورگر پاسخ زندهٔ بازیابی را دریافت نکرد؛ وضعیت سرور را بررسی کنید.");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let terminal = null;
  try {
    while (!terminal) {
      let timeout;
      let chunk;
      try {
        chunk = await Promise.race([reader.read(), new Promise((_, reject) => {
          timeout = setTimeout(() => reject(new Error("restore heartbeat lost")), 45000);
        })]);
      } finally { clearTimeout(timeout); }
      const { done, value } = chunk;
      pending += decoder.decode(value, { stream: !done });
      const lines = pending.split("\n");
      pending = lines.pop();
      if (done && pending.trim()) { lines.push(pending); pending = ""; }
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        onProgress(event);
        if (event.phase === "complete" || event.phase === "failed") { terminal = event; break; }
      }
      if (done) break;
    }
  } catch {
    throw new RestoreUnknown("ارتباط قطع شد؛ بازیابی ممکن است روی سرور ادامه داشته باشد. دوباره فایل نفرستید و وضعیت سرور را بررسی کنید.");
  } finally {
    if (!terminal) reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  if (!terminal) throw new RestoreUnknown("پاسخ نهایی نرسید؛ نتیجهٔ بازیابی نامشخص است. دوباره فایل نفرستید.");
  if (terminal.phase === "failed") throw new Error(terminal.message || "بازیابی کامل نشد؛ وضعیت سرور را بررسی کنید.");
  return terminal.result;
}
