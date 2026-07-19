const { spawn, execFileSync } = require("node:child_process");

const port = process.env.ANVIL_PORT || "8545";
const host = process.env.ANVIL_HOST || (process.platform === "win32" ? "127.0.0.1" : "0.0.0.0");
const chainId = process.env.ANVIL_CHAIN_ID || "137";

function spawnChild(command, args) {
  const child = spawn(command, args, {
    cwd: process.cwd(),
    stdio: "inherit",
    windowsHide: true,
  });
  child.on("exit", (code, signal) => {
    console.log(`anvil fork wrapper exited code=${code} signal=${signal || ""}`);
    process.exit(code ?? 1);
  });
}

console.log(`Starting Omega Anvil fork wrapper on http://${host}:${port}`);

if (process.platform === "win32") {
  spawnChild("powershell.exe", [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "scripts\\start_anvil_fork.ps1",
    "-Port",
    port,
    "-HostAddress",
    host,
    "-ChainId",
    chainId,
  ]);
} else {
  let forkUrl = "";
  try {
    const out = execFileSync("python3", ["-m", "omega_v5.fork_rpc", "--print-url"], {
      cwd: process.cwd(),
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    forkUrl = out.split(/\r?\n/).map((line) => line.trim()).find((line) => /^https?:\/\//.test(line)) || "";
  } catch (error) {
    console.error(`Could not resolve a Polygon fork RPC URL: ${error.message}`);
    process.exit(1);
  }
  if (!forkUrl) {
    console.error("Could not resolve a Polygon fork RPC URL.");
    process.exit(1);
  }
  const args = ["--host", host, "--port", port, "--chain-id", chainId, "--fork-url", forkUrl];
  if (process.env.ANVIL_VERBOSE !== "true") {
    args.push("--quiet");
  }
  spawnChild("anvil", args);
}
