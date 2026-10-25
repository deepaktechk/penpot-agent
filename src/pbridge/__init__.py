"""pbridge - drive a Penpot file from the terminal through the Penpot MCP server.

Package map (each sub-package has one job):

    project/     per-project state on disk (.pbridge/ folder)
    connection/  MCP client, in-plugin runtime injection, exports
    assets/      image uploads with a content-addressed cache
    capture/     run the headless-Chrome website capture (bundles/node-cli.js)
    convert/     capture layout.json -> buildable spec JSON
    build/       spec JSON -> Penpot shapes (keyed, idempotent), snapshots, autofix
    imaging/     pixel comparison: metrics, offsets, hotspots, overlays
    quality/     capture gate + render gate (thresholds, regressions)
    library/     design tokens (colors, typographies) from a capture
    cli/         the `pb` command line (argument parsing + thin command handlers)
"""

__version__ = "0.1.0"
