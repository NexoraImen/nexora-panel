/*
 * esbuild with Vite's `import.meta.glob`.
 *
 * The panel has one glob (frontend/src/ui/pro.jsx: which Pro screens are in
 * this build). esbuild does not know it. Stubbing it to {} made the tests blind
 * to every Pro screen even in the tree that has them, so this expands it the
 * way Vite does, from what is on disk: the Pro screens when the tree has them,
 * none in the Community tree.
 *
 * esbuild's buildSync takes no plugins, so buildSync() here runs the async
 * build in a child process and waits for it. Options must be plain JSON.
 */
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

function globPlugin() {
  return {
    name: "vite-glob",
    setup(b) {
      b.onLoad({ filter: /\.(jsx|js)$/ }, (args) => {
        if (args.path.includes("node_modules")) return undefined;
        const src = fs.readFileSync(args.path, "utf8");
        if (!src.includes("import.meta.glob(")) return undefined;
        const out = src.replace(/import\.meta\.glob\(\s*"([^"]+)"\s*\)/g, (_m, pat) => {
          const rel = path.posix.dirname(pat);
          const dir = path.resolve(path.dirname(args.path), rel);
          const ext = path.extname(pat);
          const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => f.endsWith(ext)).sort() : [];
          const entries = files.map((f) => {
            const spec = JSON.stringify(`${rel}/${f}`);
            return `${spec}: () => import(${spec})`;
          });
          return `({${entries.join(", ")}})`;
        });
        return { contents: out, loader: "jsx" };
      });
    },
  };
}

async function build(options) {
  const esbuild = require("esbuild");
  await esbuild.build({ ...options, plugins: [globPlugin()] });
}

function buildSync(options) {
  execFileSync(process.execPath, [__filename, JSON.stringify(options)], {
    stdio: ["ignore", "inherit", "inherit"], env: process.env,
  });
}

if (require.main === module) {
  build(JSON.parse(process.argv[2])).catch((e) => {
    console.error(e && e.message ? e.message : e);
    process.exit(1);
  });
}

module.exports = { buildSync };
