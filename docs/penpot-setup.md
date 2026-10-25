# Penpot setup

`pb` needs three things from Penpot:

1. the **MCP server** (it receives `pb`'s requests),
2. the **MCP plugin** running in a Penpot browser tab with your design file open (it executes them),
3. the **MCP URL**, so `pb` can reach the server.

Official reference: [help.penpot.app/mcp](https://help.penpot.app/mcp/).

## Option 1 — Penpot with built-in MCP (design.penpot.app or a recent self-hosted Penpot)

1. In Penpot: **Your account → Integrations → MCP Server**, set the status to enabled and generate a
   key. The key is shown only once.
2. Your MCP URL is `https://<your-penpot-domain>/mcp/stream?userToken=<key>`
   (on the official service the domain is `design.penpot.app`).
3. Open a design file and connect: **File → MCP Server → Connect**.

### Self-hosted with Docker

The maintainer runs penpot-agent against self-hosted Penpot 2.18 with the official
`docker-compose.yaml`, plus:

```yaml
x-flags: &penpot-flags
  PENPOT_FLAGS: ... enable-mcp            # add to the flags you already have

services:
  penpot-frontend:
    depends_on:
      - penpot-mcp                        # the frontend proxies /mcp to this service
  penpot-mcp:
    image: "penpotapp/mcp:${PENPOT_VERSION:-2.18}"
    restart: always
    networks:
      - penpot
```
Restart (`docker compose up -d`), then follow steps 1–3 with your own domain (for a local install
e.g. `http://localhost:9001/mcp/stream?userToken=<key>`). Check the
[Penpot MCP README](https://github.com/penpot/penpot/blob/main/mcp/README.md) for the current
options of your Penpot version.

## Option 2 — local MCP server

```bash
npx -y @penpot/mcp@stable          # keep this terminal running
```
In Penpot open a design file, **Plugins → Load from URL** → `http://localhost:4400/manifest.json`,
run the plugin and click **Connect to MCP server**. The MCP URL is `http://localhost:4401/mcp`.
Some Chromium browsers block a https Penpot page from talking to `http://localhost`: allow local
network access for the site, or use Firefox.

## Give `pb` the MCP URL

`pb` looks in this order (first match wins):

1. the `PENPOT_MCP_URL` environment variable;
2. `"mcp_url"` in the project's `.pbridge/config.json`;
3. a `.mcp.json` in the project folder or a parent (Claude Code project-scoped servers);
4. `~/.claude.json` — servers added to Claude Code with a name containing "penpot".

If you use Claude Code, register the server once and both Claude and `pb` will use it:

```bash
claude mcp add --transport http --scope user penpot "https://<domain>/mcp/stream?userToken=<key>"
# or, as the Penpot docs suggest:  npx -y add-mcp -g -n penpot "<URL>"
```
Otherwise put `export PENPOT_MCP_URL="<URL>"` in your shell profile.

> The URL contains your personal key. `pb` never prints it (errors show `userToken=***`) and keeps
> `.pbridge/` out of git (`pb init` writes a `.gitignore` there). Don't commit a `.mcp.json` that contains it.

## Keep the plugin connected

- Only one browser tab can own the MCP connection; keep it **open and preferably visible**.
- Browsers throttle background tabs (timers run about once a minute). `pb` notices, shows a desktop
  notification ("click the Penpot tab") and waits up to `PBRIDGE_WAIT` seconds (default 600).
- Chrome: **Settings → Performance → Always keep these sites active** → add your Penpot site
  (or pin the tab).
- If the plugin disconnects (tab reloaded or unloaded), reconnect it from the File menu; `pb`
  re-injects its runtime automatically.

## Check

```bash
pb doctor
```
`server`, `tools` and `plugin` (file and page name) show up when everything is connected.
