/* Launches Electron with a clean environment. Electron-based IDE terminals
 * (VS Code, Windsurf, ...) export ELECTRON_RUN_AS_NODE=1, which would make the
 * Electron binary run as plain Node and crash on `require("electron")`. */
const { spawn } = require("node:child_process");
const path = require("node:path");

const electronPath = require("electron"); // resolves to the binary path under Node
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

// `launch.js some/script.js` runs that file as the Electron entry point
// (used by make-icon.js); otherwise launch the app (".") with the given flags.
const args = process.argv.slice(2);
const spawnArgs = args[0]?.endsWith(".js") ? args : [".", ...args];

const child = spawn(electronPath, spawnArgs, {
  stdio: "inherit",
  env,
  cwd: path.resolve(__dirname, ".."),
});
child.on("exit", (code) => process.exit(code ?? 1));
