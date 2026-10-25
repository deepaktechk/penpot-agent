# Troubleshooting

Start with `pb doctor`: its `problems` list names most issues directly.

## Penpot connection

| Symptom | Fix |
|---|---|
| `Penpot MCP URL not found` | register the MCP server in Claude Code under a name containing "penpot", or `export PENPOT_MCP_URL=...` ([penpot-setup.md](penpot-setup.md)) |
| `cannot reach Penpot MCP server` | the server is not running: start your Penpot / `npx @penpot/mcp@stable`; check the URL and port |
| `HTTP 401/403` | the MCP key is wrong or was regenerated: create a new one and update the URL |
| `PLUGIN SUSPENDED` / "Penpot plugin is asleep" | click the Penpot tab and keep it visible; in Chrome add the site to *Settings → Performance → Always keep these sites active* |
| `No Penpot instance connected` | open a design file and connect the plugin (File → MCP Server → Connect) |
| `Task ... timed out` repeatedly | the tab was in the background; keep it visible. pb retries safe operations and builds in batches |

## Capture

| Symptom | Fix |
|---|---|
| `text was painted with a fallback font` | the font did not load: check the family name in `--fonts` matches the site's CSS, try `--wait 3000`; for fonts behind a login or CSP the capture cannot load them |
| `page never became still` | a carousel or animation keeps moving: `--click` to stop it, `--hide` it, or accept the warning |
| `image failed to load` | lazy images behind interactions: `--click`, or `--wait`; broken images on the site itself stay broken |
| cookie banner in the capture | add its selector with `--hide "#cookie-banner"` (common banners are hidden automatically) |
| `No Chrome/Chromium found` | install Chrome/Chromium or set `CHROME_PATH` |
| `Node.js (>= 20) is required` | install Node.js |

## Build and quality

| Symptom | Fix |
|---|---|
| `font not found: X` | the family is not in Penpot: `pb rebuild --font <available family>` or `--font-map "X=Y"`; upload custom fonts to Penpot |
| a section fails the render gate | `pb compare --render latest --region <section> --hotspots 4 --montage 4`, look at the montage, compare `.pbridge/captures/<name>/layout.json` with `.pbridge/specs/<name>.json` |
| `image ... does not match the reference` | the image did not upload or is fitted differently: `pb assets list`, check `fit`/`nat` in the capture |
| `REGRESSION in secNN` | that section got worse than the last good run; something changed in the site, the capture or pb |
| text slightly wider or narrower than the site | Penpot's font differs from the site's (substituted, or another version); use the same family in Penpot |
| shapes from an old build left on the board | rebuild without `--only` removes sections the new spec no longer has; or `pb rm <target>` |

## Still stuck?

Run the failing command with `-v` (timing of every plugin call) and open an
[issue](https://github.com/deepaktechk/penpot-agent/issues) with the command, the output
(pb redacts your MCP key; double-check before posting) and your Penpot, Node.js and OS versions.
