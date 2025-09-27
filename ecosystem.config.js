// --- Path conventions (override with env vars if needed) ---
const HOME         = process.env.HOME;
const STELAE_DIR   = process.env.STELAE_DIR   || `${HOME}/dev/stelae`;
const APPS_DIR     = process.env.APPS_DIR     || `${HOME}/apps`;
const LOCAL_BIN    = `${HOME}/.local/bin`;
const NVM_BIN      = process.env.NVM_BIN || `${HOME}/.nvm/versions/node/v22.19.0/bin`;

const PROXY_BIN    = process.env.PROXY_BIN    || `${APPS_DIR}/mcp-proxy/build/mcp-proxy`;
const PROXY_CONFIG = process.env.PROXY_CONFIG || `${STELAE_DIR}/config/proxy.json`;

// Workspace root
const PHOENIX_ROOT = process.env.PHOENIX_ROOT || `${HOME}/dev/stelae`;

const STRATA_BIN   = process.env.STRATA_BIN   || `${LOCAL_BIN}/strata`;
const DOCY_BIN     = process.env.DOCY_BIN     || `${LOCAL_BIN}/mcp-server-docy`;
const MEMORY_BIN   = process.env.MEMORY_BIN   || `${LOCAL_BIN}/basic-memory`;
const SHELL_BIN    = process.env.SHELL_BIN    || `${LOCAL_BIN}/terminal_controller`;

// cloudflared
const CLOUDFLARED_BIN = process.env.CLOUDFLARED || "cloudflared";
const PUBLIC_PORT     = process.env.PUBLIC_PORT || "9090";
const CF_TUNNEL_NAME  = process.env.CF_TUNNEL_NAME || "stelae"; // default to your named tunnel

const ENV_PATH = `${process.env.PATH}:${LOCAL_BIN}:${HOME}/.npm-global/bin:${NVM_BIN}`;

function cloudflaredScriptAndArgs() {
  if (CF_TUNNEL_NAME) {
    return { script: CLOUDFLARED_BIN, args: `tunnel run ${CF_TUNNEL_NAME}`, interpreter: "none" };
  }
  return { script: CLOUDFLARED_BIN, args: `tunnel --url http://127.0.0.1:${PUBLIC_PORT} --no-autoupdate`, interpreter: "none" };
}
const cf = cloudflaredScriptAndArgs();

module.exports = {
  apps: [
    // 0) Core proxy on :9090 (public facade for ChatGPT)
    {
      name: "mcp-proxy",
      script: PROXY_BIN,
      args: `--config ${PROXY_CONFIG}`,
      cwd: `${APPS_DIR}/mcp-proxy`,
      env: { PATH: ENV_PATH, MCP_DEFAULT_SERVER: "mem", MCP_DEBUG_LOG: "1"},
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
      out_file: `${STELAE_DIR}/logs/mcp-proxy.out.log`,
      error_file: `${STELAE_DIR}/logs/mcp-proxy.err.log`,
      time: true
    },

    // 1) cloudflared (named tunnel if CF_TUNNEL_NAME, else quick tunnel)
    {
      name: "cloudflared",
      script: cf.script,
      args: cf.args,
      interpreter: cf.interpreter,
      env: { PATH: ENV_PATH },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      out_file: `${STELAE_DIR}/logs/cloudflared.out.log`,
      error_file: `${STELAE_DIR}/logs/cloudflared.err.log`,
      time: true
    },

    // 2) Strata
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

    // 3) Docy
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

    // 4) Memory
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

    // 5) Shell
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
    }
  ]
};
