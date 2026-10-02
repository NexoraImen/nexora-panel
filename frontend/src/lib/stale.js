/**
 * A page file the update deleted (docs/specs/2026-10-01-bots-and-tunnel-mesh.md).
 *
 * `nexora update` rebuilds the panel and the old page chunks are gone. A tab
 * opened before the update still asks for them, and the owner saw «این بخش
 * باز نشد · Failed to fetch dynamically imported module …/minitheme-BHAzYTFm.js»
 * on most bot pages after every update. The cure is the new build: reload the
 * page once. Once, guarded by a timestamp, so a real network failure does not
 * become a reload loop.
 */
const KEY = "nx-stale-reload";

export function isStaleChunk(err) {
  const m = String((err && (err.message || err)) || "");
  return /dynamically imported module|Importing a module script failed|error loading dynamically imported|Loading chunk \S+ failed|Unable to preload CSS/i.test(m);
}

/** Reload once per minute at most. Returns true if a reload was started. */
export function reloadForNewBuild() {
  let last = 0;
  try { last = Number(sessionStorage.getItem(KEY)) || 0; } catch { /* private mode */ }
  if (Date.now() - last < 60000) return false;
  try { sessionStorage.setItem(KEY, String(Date.now())); } catch { /* private mode */ }
  window.location.reload();
  return true;
}

export function watchStaleChunks() {
  // Vite fires this when a lazy page's file (or its CSS) cannot be loaded
  window.addEventListener("vite:preloadError", (e) => {
    if (reloadForNewBuild()) e.preventDefault();
  });
}
