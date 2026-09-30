/*
 * The panel bundles without src/pro (the Community tree).
 * Spec: docs/specs/2026-09-29-pro-split.md ("Done when" 1)
 *
 * A core file that imports a Pro screen directly builds fine in this tree and
 * breaks only in the exported one. This bundles a copy of src/ without pro/,
 * with Vite's import.meta.glob expanded from disk (tests/esbuild-glob.cjs),
 * and then the real tree as a control: the Pro screens must be in that one,
 * or the "none in the Community bundle" check proves nothing.
 *
 * In the frontend group: the Python CI job has no frontend node_modules.
 *
 * Run:  NODE_PATH=frontend/node_modules node tests/test-community-bundle.cjs
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { buildSync } = require("./esbuild-glob.cjs");

const G = "\x1b[38;5;42m", R = "\x1b[38;5;203m", D = "\x1b[38;5;245m", X = "\x1b[0m";
let ok = 0, fail = 0;
const check = (name, cond, detail = "") => {
  if (cond) { ok++; console.log(`  ${G}✓${X} ${name}${detail ? ` ${D}— ${detail}${X}` : ""}`); }
  else { fail++; console.log(`  ${R}✗${X} ${name}${detail ? ` ${D}— ${detail}${X}` : ""}`); }
};

const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "frontend", "src");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "nexora-community-"));
// Names of Pro screens that must never reach the Community bundle.
const PRO_NAMES = ["ChannelSection", "BotStatsSection", "BotPreviewSection",
                   "FirewallRules", "TunnelOverview", "InboundsDoctor", "LinkDiag"];

function bundle(srcDir, out) {
  const opts = {
    entryPoints: [path.join(srcDir, "main.jsx")], bundle: true, format: "esm",
    outfile: out, jsx: "automatic", logLevel: "error",
    nodePaths: [path.join(ROOT, "frontend", "node_modules")],
    loader: { ".js": "jsx", ".css": "empty" },
    define: { "import.meta.env.VITE_API_URL": '""' },
  };
  try { buildSync(opts); return { js: fs.readFileSync(out, "utf8") }; }
  catch (e) { return { err: String(e.message || e).slice(-300) }; }
}

console.log(`\n${D}── The panel bundles without src/pro ──${X}`);
const copy = path.join(TMP, "src");
fs.cpSync(SRC, copy, { recursive: true, filter: (p) => p !== path.join(SRC, "pro") });
const community = bundle(copy, path.join(TMP, "community.js"));
check("the panel bundles with no src/pro/", !community.err, community.err || "");
if (community.js) {
  const leaked = PRO_NAMES.filter((n) => community.js.includes(`function ${n}`));
  check("… and carries none of the Pro screens", leaked.length === 0, leaked.join(", "));
}

if (fs.existsSync(path.join(SRC, "pro"))) {
  const full = bundle(SRC, path.join(TMP, "full.js"));
  const found = full.js ? PRO_NAMES.filter((n) => full.js.includes(`function ${n}`)) : [];
  check("control: the full tree's bundle does carry them (the check above can fail)",
        found.length === PRO_NAMES.length, full.err || `${found.length}/${PRO_NAMES.length}`);
}

fs.rmSync(TMP, { recursive: true, force: true });
console.log(`\n  ${fail ? R : G}${ok} passed, ${fail} failed${X}\n`);
process.exit(fail ? 1 : 0);
