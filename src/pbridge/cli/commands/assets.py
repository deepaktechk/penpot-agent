"""Image assets: assets list | sync | url URL | file PATH [--crop ...]."""
from __future__ import annotations

from pbridge.assets import AssetStore
from pbridge.cli.support import Args, get_bridge, out


def cmd_assets(args: Args) -> None:
    store = AssetStore(get_bridge(args))
    if args.action == "list":
        out({key: {"src": entry.get("src"),
                   "size": [entry["image"]["width"], entry["image"]["height"]] if entry.get("image") else None}
             for key, entry in store.entries.items()})
    elif args.action == "sync":
        out({"registered": store.sync()})
    elif args.action == "url":
        out({"key": store.from_url(args.src, args.key, args.force)})
    elif args.action == "file":
        crop = [int(value) for value in args.crop.split(",")] if args.crop else None
        if crop and len(crop) == 4 and args.crop_wh:        # x,y,w,h -> x0,y0,x1,y1
            crop = [crop[0], crop[1], crop[0] + crop[2], crop[1] + crop[3]]
        out({"key": store.from_file(args.src, args.key, crop=crop, quantize=args.quantize, scale=args.scale, fmt=args.fmt)})


def add_assets(subparsers) -> None:
    parser = subparsers.add_parser("assets", help="image assets: list|sync|url|file")
    parser.add_argument("action", choices=["list", "sync", "url", "file"], help="list cached, re-register all, upload a URL or a file")
    parser.add_argument("src", nargs="?", help="URL or file path")
    parser.add_argument("--key", help="asset key (default: derived from the name)")
    parser.add_argument("--force", action="store_true", help="upload again even if cached")
    parser.add_argument("--crop", help="x0,y0,x1,y1 (or x,y,w,h with --crop-wh)"); parser.add_argument("--crop-wh", action="store_true")
    parser.add_argument("--quantize", type=int, help="reduce to N colours (smaller PNG)")
    parser.add_argument("--scale", type=float, help="resize factor")
    parser.add_argument("--fmt", help="re-encode, e.g. JPEG for photos")
    parser.set_defaults(handler=cmd_assets)


PARSERS = {"assets": add_assets}
