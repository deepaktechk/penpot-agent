"""The Penpot file itself: page (list/create/open), version (save/list), code (design -> HTML/CSS), tokens."""
from __future__ import annotations

import json
from pathlib import Path

from pbridge.cli.support import TARGET_HELP, Args, get_bridge, out, resolve_target

PAGES_JS = """
    const current = penpot.currentPage && penpot.currentPage.id;
    return penpot.currentFile.pages.map(page => ({id: page.id, name: page.name, current: page.id === current}));"""
# find a page by name or id; create it when asked; make it the active page (where shapes are created)
OPEN_PAGE_JS = """
    let page = penpot.currentFile.pages.find(candidate => candidate.name === DATA.page || candidate.id === DATA.page);
    if (!page && DATA.create) { page = penpot.createPage(); page.name = DATA.page; }
    if (!page) throw new Error("page not found: " + DATA.page);
    await penpot.openPage(page);
    return {id: page.id, name: page.name};"""
SAVE_VERSION_JS = """
    const version = await penpot.currentFile.saveVersion(DATA);
    return {label: version.label, createdAt: String(version.createdAt)};"""
LIST_VERSIONS_JS = """
    const versions = await penpot.currentFile.findVersions();
    return versions.map(version => ({label: version.label, createdAt: String(version.createdAt), autosave: version.isAutosave}));"""
CODE_JS = """
    const shape = pb.byId(DATA.id);
    if (!shape) throw new Error("shape not found");
    return {
      markup: penpot.generateMarkup([shape], {type: DATA.type}),
      css: penpot.generateStyle([shape], {type: "css", withPrelude: true, includeChildren: true}),
      fonts: await penpot.generateFontFaces([shape]),
    };"""
# create (or extend) a token set; existing tokens with the same name are kept
TOKENS_JS = """
    const catalog = penpot.library.local.tokens;
    let tokenSet = catalog.sets.find(candidate => candidate.name === DATA.set);
    if (!tokenSet) tokenSet = catalog.addSet({name: DATA.set, active: true});
    const existing = new Set(tokenSet.tokens.map(token => token.name));
    let added = 0;
    for (const token of DATA.tokens) {
      if (existing.has(token.name)) continue;
      tokenSet.addToken({type: token.type, name: token.name, value: token.value}); added++;
    }
    return {set: tokenSet.name, added, total: tokenSet.tokens.length};"""


def open_page(bridge, page: str, create: bool = True) -> dict:
    """Make `page` the active page (created when missing); later builds go there."""
    return bridge.exec(OPEN_PAGE_JS, data={"page": page, "create": create}, timeout=120)


def cmd_page(args: Args) -> None:
    bridge = get_bridge(args)
    if args.action == "list":
        out(bridge.exec(PAGES_JS), args)
    else:
        out(open_page(bridge, args.name, create=args.action == "create"), args)


def cmd_version(args: Args) -> None:
    bridge = get_bridge(args)
    if args.action == "save":
        out(bridge.exec(SAVE_VERSION_JS, data=args.label or "pb checkpoint", timeout=120), args)
    else:
        out(bridge.exec(LIST_VERSIONS_JS, timeout=120), args)


def cmd_code(args: Args) -> None:
    """Penpot's own code generation for a board/layer -> index.html + style.css + fonts.css."""
    bridge = get_bridge(args)
    code = bridge.exec(CODE_JS, data={"id": resolve_target(bridge, args.target), "type": args.type}, timeout=300)
    folder = Path(args.out); folder.mkdir(parents=True, exist_ok=True)
    (folder / "style.css").write_text(code["css"])
    (folder / "fonts.css").write_text(code["fonts"] or "")
    if args.type == "html":
        page = ('<!doctype html>\n<html>\n<head>\n<meta charset="utf-8">\n<link rel="stylesheet" href="fonts.css">\n'
                '<link rel="stylesheet" href="style.css">\n</head>\n<body>\n' + code["markup"] + "\n</body>\n</html>\n")
        (folder / "index.html").write_text(page)
    else:
        (folder / "design.svg").write_text(code["markup"])
    out({"folder": str(folder), "files": sorted(path.name for path in folder.iterdir())}, args)


def design_tokens(layout: dict, colors: int, families: int = 4) -> list[dict]:
    """Penpot design tokens from a capture: colours, font sizes, font families, font weights."""
    from pbridge.convert.fonts import css_weight
    from pbridge.library import extract_tokens
    palette, typographies = extract_tokens(layout, colors, 50)
    tokens = [{"type": "color", "name": f"color.{index + 1:02d}", "value": color} for index, color in enumerate(palette)]
    sizes = sorted({round(float(style[1].replace("px", ""))) for style in typographies})
    tokens += [{"type": "fontSizes", "name": f"font-size.{size}", "value": str(size)} for size in sizes]
    family_names = list(dict.fromkeys(style[0] for style in typographies))[:families]
    tokens += [{"type": "fontFamilies", "name": "font-family." + name.lower().replace(" ", "-"), "value": name} for name in family_names]
    weights = sorted({css_weight(style[2]) for style in typographies})
    tokens += [{"type": "fontWeights", "name": f"font-weight.{weight}", "value": str(weight)} for weight in weights]
    return tokens


def cmd_tokens(args: Args) -> None:
    """Capture -> Penpot design tokens (a token set), the 2.x token system (see also `pb library`)."""
    bridge = get_bridge(args)
    capture_dir = Path(args.capture or bridge.state.config.get("capture", ""))
    tokens = design_tokens(json.loads((capture_dir / "layout.json").read_text()), args.colors)
    if args.dry:
        out({"set": args.set, "tokens": tokens}, args)
    else:
        out(bridge.exec(TOKENS_JS, data={"set": args.set, "tokens": tokens}, timeout=300), args)


def add_page(subparsers) -> None:
    parser = subparsers.add_parser("page", help="pages of the file: list | create NAME | open NAME")
    parser.add_argument("action", choices=["list", "create", "open"])
    parser.add_argument("name", nargs="?", help="page name (or id for open)")
    parser.set_defaults(handler=cmd_page)


def add_version(subparsers) -> None:
    parser = subparsers.add_parser("version", help="named file versions in Penpot: save [LABEL] | list")
    parser.add_argument("action", choices=["save", "list"])
    parser.add_argument("label", nargs="?", help="version label (save)")
    parser.set_defaults(handler=cmd_version)


def add_code(subparsers) -> None:
    parser = subparsers.add_parser("code", help="design -> HTML/CSS (or SVG) with Penpot's code generator")
    parser.add_argument("target", nargs="?", default="page", help=TARGET_HELP + " (default: page)")
    parser.add_argument("--out", default="code", help="output folder (default ./code)")
    parser.add_argument("--type", choices=["html", "svg"], default="html", help="markup type (default html)")
    parser.set_defaults(handler=cmd_code)


def add_tokens(subparsers) -> None:
    parser = subparsers.add_parser("tokens", help="design tokens (colours, font sizes/families/weights) from the capture")
    parser.add_argument("--capture", help="capture folder (default: the current capture)")
    parser.add_argument("--set", default="Site", help="token set name (default Site)")
    parser.add_argument("--colors", type=int, default=12, help="number of colour tokens (default 12)")
    parser.add_argument("--dry", action="store_true", help="only print the tokens")
    parser.set_defaults(handler=cmd_tokens)


PARSERS = {"page": add_page, "version": add_version, "code": add_code, "tokens": add_tokens}
