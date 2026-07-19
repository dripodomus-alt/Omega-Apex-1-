const { spawn, execFileSync } = require("node:child_process");

const port = process.env.REDIS_PORT || "6379";
const bind = process.env.REDIS_BIND || "127.0.0.1";

function existingRedisHealthy() {
  try {
    const out = execFileSync("redis-cli", ["-h", bind, "-p", port, "ping"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
    return out === "PONG";
  } catch {
    return false;
  }
}

if (existingRedisHealthy()) {
  console.log(`Redis already healthy at ${bind}:${port}; PM2 keeper online.`);
  setInterval(() => {
    if (!existingRedisHealthy()) {
      console.error(`Redis health check failed at ${bind}:${port}`);
      process.exit(1);
    }
  }, 5000);
} else {
  console.log(`Starting Redis on ${bind}:${port}`);
  const child = spawn("redis-server", ["--bind", bind, "--port", port, "--save", "", "--appendonly", "no"], {
    stdio: "inherit",
    windowsHide: true,
  });
  child.on("exit", (code, signal) => {
    console.log(`redis-server exited code=${code} signal=${signal || ""}`);
    process.exit(code ?? 1);
  });
}
