"""Lookups: fonts (availability in Penpot), api (Penpot plugin API docs)."""
from __future__ import annotations

from pbridge.cli.support import Args, get_bridge, out
from pbridge.connection import MCPClient, discover_mcp_url
from pbridge.project import ProjectState

FONTS_JS = ("return DATA.map(wanted => { "
            "const font = penpot.fonts.all.find(candidate => candidate.name.toLowerCase() === wanted.toLowerCase()); "
            "return {name: wanted, found: !!font, weights: font ? [...new Set(font.variants.map("
            "variant => variant.fontWeight + (variant.fontStyle === 'italic' ? 'i' : '')))].join(',') : null}; });")


def cmd_fonts(args: Args) -> None:
    bridge = get_bridge(args)
    if args.names:
        out(bridge.exec(FONTS_JS, data=args.names))
    else:
        out(bridge.exec("return penpot.fonts.all.length;"))


def cmd_api(args: Args) -> None:
    client = MCPClient(discover_mcp_url(ProjectState.open()))
    arguments = {"type": args.type}
    if args.member:
        arguments["member"] = args.member
    print(client.call("penpot_api_info", arguments).text)


def add_fonts(subparsers) -> None:
    parser = subparsers.add_parser("fonts", help="check fonts exist in Penpot")
    parser.add_argument("names", nargs="*", help="font families (none: count all fonts)")
    parser.set_defaults(handler=cmd_fonts)


def add_api(subparsers) -> None:
    parser = subparsers.add_parser("api", help="Penpot API docs")
    parser.add_argument("type", help="Penpot plugin API type, e.g. Shape, Text, Board")
    parser.add_argument("member", nargs="?", help="a property or method of that type")
    parser.set_defaults(handler=cmd_api)


PARSERS = {"fonts": add_fonts, "api": add_api}
