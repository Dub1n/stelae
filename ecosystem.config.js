// --- Path conventions (override with env vars if needed) ---
const HOME         = process.env.HOME;
const STELAE_DIR   = process.env.STELAE_DIR   || `${HOME}/dev/stelae`;
const APPS_DIR     = process.env.APPS_DIR     || `${HOME}/apps`;
const LOCAL_BIN    = `${HOME}/.local/bin`;
const NVM_BIN      = process.env.NVM_BIN || `${HOME}/.nvm/versions/node/v22.19.0/bin`;

const PROXY_BIN    = process.env.PROXY_BIN    || `${APPS_DIR}/mcp-proxy/build/mcp-proxy`;
const PROXY_CONFIG = process.env.PROXY_CONFIG || `${STELAE_DIR}/config/proxy.json`;

const PHOENIX_ROOT = process.env.PHOENIX_ROOT || `${HOME}/dev/stelae`;

const STRATA_BIN   = process.env.STRATA_BIN   || `${LOCAL_BIN}/strata`;
const DOCY_BIN     = process.env.DOCY_BIN     || `${LOCAL_BIN}/mcp-server-docy`;
const MEMORY_BIN   = process.env.MEMORY_BIN   || `${LOCAL_BIN}/basic-memory`;
const SHELL_BIN    = process.env.SHELL_BIN    || `${LOCAL_BIN}/terminal_controller`;

const PYTHON_BIN   = process.env.PYTHON || "python3";

// cloudflared bits
const CF_BIN    = process.env.CLOUDFLARED || `${NVM_BIN}/cloudflared`;
const CF_CONF   = process.env.CF_CONF     || `${HOME}/.cloudflared/stelae.yml`;
const CF_TUNNEL = process.env.CF_TUNNEL_NAME || `stelae`;

const ENV_PATH = `${process.env.PATH}:${LOCAL_BIN}:${HOME}/.npm-global/bin:${NVM_BIN}`;

module.exports = {
  apps: [
    // 0) Core proxy on :9090 (public facade for ChatGPT)
    {
      name: "mcp-proxy",
      script: PROXY_BIN,
      args: `--config ${PROXY_CONFIG}`,
      cwd: `${APPS_DIR}/mcp-proxy`,
      env: { PATH: ENV_PATH, MCP_DEFAULT_SERVER: "mem", MCP_DEBUG_LOG: "1" },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
      out_file: `${STELAE_DIR}/logs/mcp-proxy.out.log`,
      error_file: `${STELAE_DIR}/logs/mcp-proxy.err.log`,
      time: true
    },

    // 1) Strata
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

    // 2) Docy
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

    // 3) Memory
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

    // 4) Shell
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

    // 5) cloudflared (named tunnel, sticky)
    {
      name: "cloudflared",
      script: CF_BIN,
      args: `tunnel run ${CF_TUNNEL} --config ${CF_CONF} --no-autoupdate --loglevel info`,
      interpreter: "none",
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 50,
      restart_delay: 1500,
      out_file: `${STELAE_DIR}/logs/cloudflared.out.log`,
      error_file: `${STELAE_DIR}/logs/cloudflared.err.log`,
      time: true
    },

    // 6) public watchdog (restart cloudflared on repeated failures)
    {
      name: "watchdog",
      script: PYTHON_BIN,
      args: `${STELAE_DIR}/scripts/watch_public_mcp.py`,
      env: {
        PATH: ENV_PATH,
        PUBLIC_BASE_URL: process.env.PUBLIC_BASE_URL || "https://mcp.infotopology.xyz",
        WATCH_INTERVAL: process.env.WATCH_INTERVAL || "60",
        FAIL_THRESHOLD: process.env.FAIL_THRESHOLD || "3",
        CF_PM2_NAME: "cloudflared"
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/watchdog.out.log`,
      error_file: `${STELAE_DIR}/logs/watchdog.err.log`,
      time: true
    }
  ]
};
