// ~/dev/stelae/ecosystem.config.js

// --- Path conventions (override with env vars if needed) ---
const HOME         = process.env.HOME;
const STELAE_DIR   = process.env.STELAE_DIR   || `${HOME}/dev/stelae`;
const APPS_DIR     = process.env.APPS_DIR     || `${HOME}/apps`;
const VENDOR_DIR   = process.env.VENDOR_DIR   || `${APPS_DIR}/vendor`;

const PROXY_BIN    = process.env.PROXY_BIN    || `${APPS_DIR}/mcp-proxy/build/mcp-proxy`;
const PROXY_CONFIG = process.env.PROXY_CONFIG || `${STELAE_DIR}/config/proxy.json`;

// Phoenix repo roots (adjust if yours differs)
const PHOENIX_ROOT = process.env.PHOENIX_ROOT || `${HOME}/dev/Phoenix`;
const TASKS_DB     = process.env.TASKS_DB     || `${PHOENIX_ROOT}/.ai/tasks.json`;
const MEMORY_DIR   = process.env.MEMORY_DIR   || `${PHOENIX_ROOT}/.ai/memory`;

// Ensure PATH includes pipx and npm global bins (common WSL gotcha)
const ENV_PATH = `${process.env.PATH}:${HOME}/.local/bin:${HOME}/.npm-global/bin`;

module.exports = {
  apps: [
    // 1) Core proxy (single public URL exposed via cloudflared)
    {
      name: "mcp-proxy",
      script: PROXY_BIN,
      args: `--config ${PROXY_CONFIG}`,
      cwd: `${APPS_DIR}/mcp-proxy`,
      env: { PATH: ENV_PATH },
      // Ops defaults
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
      // Logs
      out_file: `${STELAE_DIR}/logs/mcp-proxy.out.log`,
      error_file: `${STELAE_DIR}/logs/mcp-proxy.err.log`,
      time: true
    },

    // 2) Strata (progressive discovery router)
    {
      name: "strata",
      script: "strata-mcp",
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/strata.out.log`,
      error_file: `${STELAE_DIR}/logs/strata.err.log`,
      time: true
    },

    // 3) Docs fetcher (Docy) — optional, remove if unused
    {
      name: "docy",
      script: "mcp-server-docy",
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/docy.out.log`,
      error_file: `${STELAE_DIR}/logs/docy.err.log`,
      time: true
    },

    // 4) Tasks (local JSON task stack)
    {
      name: "tasks",
      script: "mcp-tasks",
      args: `--db ${TASKS_DB}`,
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/tasks.out.log`,
      error_file: `${STELAE_DIR}/logs/tasks.err.log`,
      time: true
    },

    // 5) Memory (portable, plain files)
    {
      name: "memory",
      script: "basic-memory",
      args: `--store ${MEMORY_DIR}`,
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/memory.out.log`,
      error_file: `${STELAE_DIR}/logs/memory.err.log`,
      time: true
    },

    // 6) Shell / command executor (pick one; default here: terminal-controller-mcp)
    //    Tighten allowlist for your workflow. You can swap to mcp-shell if preferred.
    {
      name: "shell",
      script: "terminal-controller-mcp",
      args: `--workdir ${PHOENIX_ROOT} --allow npm,pytest,make,python,git`,
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/shell.out.log`,
      error_file: `${STELAE_DIR}/logs/shell.err.log`,
      time: true
    },

    // 7) 1mcpserver (discovery/install sidecar)
    //    If you installed via pipx, 'one_mcp_server' may be directly available.
    //    Using module form is robust across envs; adjust cwd if you cloned the repo.
    {
      name: "1mcp",
      script: "python3",
      args: "-m one_mcp_server",
      cwd: `${VENDOR_DIR}/1mcpserver`,
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/1mcp.out.log`,
      error_file: `${STELAE_DIR}/logs/1mcp.err.log`,
      time: true
    }
  ]
};
