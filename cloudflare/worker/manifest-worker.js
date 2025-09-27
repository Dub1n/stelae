export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // diag
    if (url.pathname === "/__diag") {
      return new Response(
        JSON.stringify({ ok: true, host: url.host, path: url.pathname, ts: Date.now() }),
        { headers: { "content-type": "application/json" } }
      );
    }

    if (url.pathname === "/.well-known/mcp/manifest.json") {
      let body = await env.MANIFEST_KV.get("manifest_json");

      // fully-formed fallback so connectors never get nulls
      if (!body) {
        body = JSON.stringify({
          name: "Stelae MCP Proxy",
          description: "Edge-served manifest (fallback); KV not populated yet.",
          endpoint: "/mcp",
          endpointURL: `${url.origin}/mcp`,
          prompts: [],
          resources: []
        });
      }

      const headers = {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "public, s-maxage=600, stale-while-revalidate=60, stale-if-error=86400",
        "x-worker": "stelae-manifest"
      };
      return new Response(body, { status: 200, headers });
    }

    // everything else goes to origin (/mcp etc.)
    return fetch(request);
  },
};
