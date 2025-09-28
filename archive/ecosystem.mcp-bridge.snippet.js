module.exports = {
  apps: [
    {
      name: "mcp-bridge",
      cwd: "/home/gabri/dev/stelae",
      script: "bash",
      args: [
        "-lc",
        "python3 -m pip install -q -r bridge/requirements.txt && uvicorn bridge.stream_http_bridge:app --host 0.0.0.0 --port 9090"
      ],
      env: {
        UPSTREAM_BASE: "http://127.0.0.1:9092",
        PUBLIC_BASE_URL: "https://mcp.infotopology.xyz"
      },
      max_restarts: 10,
      restart_delay: 1000
    }
  ]
};
