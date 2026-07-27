const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const port = process.env.PORT || "3000";
const repoRoot = process.cwd();
const providerDir = path.join(repoRoot, "vendor", "web3-rpc-provider");

function spawnChild(command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: options.cwd || repoRoot,
    stdio: "inherit",
    windowsHide: true,
    env: process.env,
  });
  child.on("exit", (code, signal) => {
    console.log(`DODO web3-rpc-provider exited code=${code} signal=${signal || ""}`);
    process.exit(code ?? 1);
  });
}

if (!fs.existsSync(providerDir)) {
  console.error(`DODOEX web3-rpc-provider is missing at ${providerDir}`);
  process.exit(1);
}

if (process.platform === "win32") {
  const args = [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "scripts\\start_dodo_rpc_provider.ps1",
    "-Port",
    port,
    "-Foreground",
  ];
  if (process.env.PUPPETEER_EXECUTABLE_PATH) {
    args.push("-BrowserPath", process.env.PUPPETEER_EXECUTABLE_PATH);
  }
  console.log(`Starting DODO web3-rpc-provider wrapper on http://127.0.0.1:${port}`);
  spawnChild("powershell.exe", args);
} else {
  const candidates = [
    process.env.PUPPETEER_EXECUTABLE_PATH,
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
  ].filter(Boolean);
  const browser = candidates.find((candidate) => fs.existsSync(candidate));
  if (!browser) {
    console.error("Set PUPPETEER_EXECUTABLE_PATH to a Chromium/Chrome executable.");
    process.exit(1);
  }
  process.env.PUPPETEER_EXECUTABLE_PATH = browser;
  process.env.PORT = port;
  console.log(`Starting DODO web3-rpc-provider on http://0.0.0.0:${port} using ${browser}`);
  spawnChild("node", ["dist/bootstrap.js"], { cwd: providerDir });
}
k