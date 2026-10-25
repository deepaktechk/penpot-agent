"""Command handlers, grouped by topic. Each module exposes `PARSERS = {name: add_<name>}`.

Handlers stay thin: parse arguments, call a workflow / service, print the result.
Every `add_<name>(subparsers)` registers its sub-parser with `set_defaults(handler=cmd_<name>)`.
"""
from pbridge.cli.commands import assets, document, edit, images, inspection, library, misc, qa, render, review, scripting, setup, web

MODULES = (setup, scripting, inspection, document, edit, render, qa, review, assets, images, web, library, misc)

# every command's parser factory, by name
PARSERS = {name: add_parser for module in MODULES for name, add_parser in module.PARSERS.items()}
