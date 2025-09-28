export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    console.log(JSON.stringify({
      stage: "incoming",
      path: url.pathname,
      method: request.method,
      ua: request.headers.get("user-agent") || null,
      ts: Date.now()
    }));

    // diag
    if (url.pathname === "/__diag") {
      return new Response(
        JSON.stringify({ ok: true, host: url.host, path: url.pathname, ts: Date.now() }),
        { headers: { "content-type": "application/json" } }
      );
    }

    if (url.pathname === "/") {
      return Response.redirect(`${url.origin}/mcp`, 307);
    }

    if (url.pathname === "/.well-known/mcp/manifest.json") {
      const allowedToolNames = ["fetch", "search"]; // enforce ChatGPT verifier expectations
      const fallbackTools = {
        fetch: {
          name: "fetch",
          description: "Connector-compliant fetch placeholder exposed at the edge.",
          inputSchema: {
            type: "object",
            properties: {
              url: { title: "Url", type: "string" }
            },
            required: ["url"]
          }
        },
        search: {
          name: "search",
          description: "Connector-compliant search placeholder exposed at the edge.",
          inputSchema: {
            type: "object",
            properties: {
              query: { title: "Query", type: "string" }
            },
            required: ["query"]
          }
        }
      };

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

      try {
        const parsed = JSON.parse(body);
        parsed.endpointURL = `${url.origin}/mcp`;
        if (!parsed.protocolVersion) {
          parsed.protocolVersion = "2024-11-05";
        }
        if (!parsed.servers || parsed.servers.length === 0) {
          parsed.servers = [
            {
              name: parsed.name || "Stelae MCP Proxy",
              url: `${url.origin}/mcp`,
              transport: "streamable-http",
              version: parsed.version || "1.0.0"
            }
          ];
        } else {
          parsed.servers = parsed.servers.map((srv) => ({
            ...srv,
            transport: srv.transport || "streamable-http",
            url: srv.url || `${url.origin}/mcp`
          }));
        }

        const manifestTools = Array.isArray(parsed.tools) ? parsed.tools : [];
        parsed.tools = allowedToolNames.map((name) => {
          const existing = manifestTools.find((tool) => tool && tool.name === name);
          return existing || fallbackTools[name];
        });

        body = JSON.stringify(parsed);
      } catch (err) {
        console.log(JSON.stringify({ stage: "manifest_parse_error", error: `${err}` }));
      }

      console.log(JSON.stringify({ path: url.pathname, ua: request.headers.get("user-agent"), ts: Date.now() }))
      const headers = {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "public, s-maxage=600, stale-while-revalidate=60, stale-if-error=86400",
        "x-worker": "stelae-manifest"
      };
      return new Response(body, { status: 200, headers });
    }

    // everything else goes to origin (/mcp etc.)
    console.log(JSON.stringify({
      stage: "proxy",
      path: url.pathname,
      method: request.method,
      forwardTo: "origin"
    }));
    return fetch(request);
  },
};
