# server-setup-commands

## init

```bash
# Create the DNS record
cloudflared tunnel route dns stelae mcp.infotopology.xyz

# Run the tunnel
cloudflared tunnel run stelae

# Keep it in PM2 or a system service:
pm2 start "cloudflared tunnel run stelae" --name cloudflared
pm2 save

# Update your .env
PUBLIC_BASE_URL=https://mcp.yourdomain.com
PUBLIC_SSE_URL=${PUBLIC_BASE_URL}/stream

# then
make render-proxy
source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env

# verify
curl -s https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | jq .
curl -skI https://mcp.infotopology.xyz/stream
```

## restart

```bash
make render-proxy
source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
```
