import { cpSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { spawn } from "node:child_process";

// Next's standalone output needs its public and static assets alongside server.js.
const root = process.cwd();
const output = resolve(root, ".next/standalone");
if (!existsSync(resolve(output, "server.js"))) {
  console.error("No production build found. Run npm run build first.");
  process.exit(1);
}

const args = process.argv.slice(2);
const env = { ...process.env, HOSTNAME: "127.0.0.1", PORT: process.env.PORT || "3000" };
for (let i = 0; i < args.length; i += 2) {
  if (!["--hostname", "--port"].includes(args[i]) || !args[i + 1]) {
    console.error("Usage: npm start -- [--hostname 127.0.0.1] [--port 3000]");
    process.exit(1);
  }
  env[args[i] === "--port" ? "PORT" : "HOSTNAME"] = args[i + 1];
}
if (!/^\d+$/.test(env.PORT) || Number(env.PORT) < 1 || Number(env.PORT) > 65535) {
  console.error("Port must be an integer between 1 and 65535.");
  process.exit(1);
}
mkdirSync(resolve(output, ".next"), { recursive: true });
cpSync(resolve(root, ".next/static"), resolve(output, ".next/static"), { recursive: true });
if (existsSync(resolve(root, "public"))) {
  cpSync(resolve(root, "public"), resolve(output, "public"), { recursive: true });
}
const server = spawn(process.execPath, [resolve(output, "server.js")], { env, stdio: "inherit" });
server.on("error", error => { console.error(error.message); process.exitCode = 1; });
server.on("exit", code => { process.exitCode = code ?? 1; });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill(signal));
