// --- Path conventions (override with env vars if needed) ---
const HOME         = process.env.HOME;
const STELAE_DIR   = process.env.STELAE_DIR   || `${HOME}/dev/stelae`;
const APPS_DIR     = process.env.APPS_DIR     || `${HOME}/apps`;
const VENDOR_DIR   = process.env.VENDOR_DIR   || `${APPS_DIR}/vendor`;
const LOCAL_BIN    = `${HOME}/.local/bin`;
const NVM_BIN      = process.env.NVM_BIN || `${HOME}/.nvm/versions/node/v22.19.0/bin`;
const PROXY_BIN    = process.env.PROXY_BIN    || `${APPS_DIR}/mcp-proxy/build/mcp-proxy`;
const PROXY_CONFIG = process.env.PROXY_CONFIG || `${STELAE_DIR}/config/proxy.json`;

// Phoenix repo roots (adjust if yours differs)
const PHOENIX_ROOT = process.env.PHOENIX_ROOT || `${HOME}/dev/stelae`;
const MEMORY_DIR   = process.env.MEMORY_DIR   || `${PHOENIX_ROOT}/.ai/memory`;

// Common executables (override via env if layout differs)
const STRATA_BIN   = process.env.STRATA_BIN   || `${LOCAL_BIN}/strata`;
const DOCY_BIN     = process.env.DOCY_BIN     || `${LOCAL_BIN}/mcp-server-docy`;
const MEMORY_BIN   = process.env.MEMORY_BIN   || `${LOCAL_BIN}/basic-memory`;
const SHELL_BIN    = process.env.SHELL_BIN    || `${LOCAL_BIN}/terminal_controller`;

// Bridge venv python (create it with `make bridge-venv`)
const BRIDGE_PY    = process.env.BRIDGE_PY    || `${HOME}/.venvs/stelae-bridge/bin/python`;

// Ensure PATH includes pipx and npm global bins (common WSL gotcha)
const ENV_PATH = `${process.env.PATH}:${LOCAL_BIN}:${HOME}/.npm-global/bin:${NVM_BIN}`;

module.exports = {
  apps: [
    // 0) Streamable HTTP bridge on :9090 (ChatGPT hits this)
    {
      name: "mcp-bridge",
      cwd: STELAE_DIR,
      script: "bash",
      args: [
        "-lc",
        `${BRIDGE_PY} -m uvicorn bridge.stream_http_bridge:app --host 0.0.0.0 --port 9090`
      ],
      env: {
        PATH: ENV_PATH,
        UPSTREAM_BASE: "http://127.0.0.1:9092",
        PUBLIC_BASE_URL: "https://mcp.infotopology.xyz"
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 1000,
      out_file: `${STELAE_DIR}/logs/mcp-bridge.out.log`,
      error_file: `${STELAE_DIR}/logs/mcp-bridge.err.log`,
      time: true
    },

    // 1) Core proxy now on :9092 (the bridge proxies to this)
    {
      name: "mcp-proxy",
      script: PROXY_BIN,
      args: `--config ${PROXY_CONFIG}`,
      cwd: `${APPS_DIR}/mcp-proxy`,
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
      out_file: `${STELAE_DIR}/logs/mcp-proxy.out.log`,
      error_file: `${STELAE_DIR}/logs/mcp-proxy.err.log`,
      time: true
    },

    // 2) Strata (progressive discovery router)
    {
      name: "strata",
      script: STRATA_BIN,
      interpreter: "none",
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/strata.out.log`,
      error_file: `${STELAE_DIR}/logs/strata.err.log`,
      time: true
    },

    // 3) Docs fetcher (Docy)
    {
      name: "docy",
      script: DOCY_BIN,
      interpreter: "none",
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/docy.out.log`,
      error_file: `${STELAE_DIR}/logs/docy.err.log`,
      time: true
    },

    // 4) Memory (portable, plain files)
    {
      name: "memory",
      script: MEMORY_BIN,
      interpreter: "none",
      args: "mcp --transport stdio",
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/memory.out.log`,
      error_file: `${STELAE_DIR}/logs/memory.err.log`,
      time: true
    },

    // 5) Shell / command executor (tighten allowlist as needed)
    {
      name: "shell",
      script: SHELL_BIN,
      interpreter: "none",
      args: `--workdir ${PHOENIX_ROOT} --allow npm,pytest,make,python,git`,
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/shell.out.log`,
      error_file: `${STELAE_DIR}/logs/shell.err.log`,
      time: true
    },

    // 6) 1mcp agent (discovery/install sidecar)
    {
      name: "1mcp",
      script: process.env.ONE_MCP_BIN || "1mcp",
      interpreter: "none",
      args: "--transport stdio",
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
