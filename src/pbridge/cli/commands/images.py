"""Design images as input: analyze (palette + boxes), reference (compare designs against any image)."""
from __future__ import annotations

import shutil
from pathlib import Path

from pbridge.cli.support import Args, out, parse_region
from pbridge.project import ProjectState


def cmd_analyze(args: Args) -> None:
    from pbridge.imaging.analysis import analyze, combined_palette
    region = parse_region(args.region)
    if region and region[2] is None:
        from PIL import Image
        region = (0, region[1], Image.open(args.images[0]).width, region[3])
    analyses = [analyze(image, region, colors=args.colors, box_limit=args.boxes) for image in args.images]
    if len(analyses) == 1:
        out(analyses[0], args)
    else:
        out({"images": analyses, "combined_palette": combined_palette(analyses, count=args.colors + 4)}, args)


def cmd_reference(args: Args) -> None:
    """Make an image the project reference (what `pb compare` / `pb qa` measure designs against)."""
    from PIL import Image
    state = ProjectState.open(); state.init()
    source = Image.open(args.image)
    target = state.path("references", (args.name or Path(args.image).stem) + ".png")
    if args.width and source.width != args.width:
        height = round(source.height * args.width / source.width)
        source.convert("RGB").resize((args.width, height), Image.LANCZOS).save(target)
    elif args.image.lower().endswith(".png"):
        shutil.copyfile(args.image, target)
    else:
        source.convert("RGB").save(target)
    state.config["reference"] = str(target)
    state.save_config()
    width, height = Image.open(target).size
    out({"reference": str(target), "size": [width, height],
         "next": f"build a board of {width}x{height} (spec width/height), then `pb compare` / `pb qa --spec <spec>`"})


def add_analyze(subparsers) -> None:
    parser = subparsers.add_parser("analyze", help="measure design images: palette, background, solid boxes")
    parser.add_argument("images", nargs="+", help="image files (several: also a combined moodboard palette)")
    parser.add_argument("--region", help="only this part: y0,y1 or x,y,w,h (positions stay in image coordinates)")
    parser.add_argument("--colors", type=int, default=8, help="palette size (default 8)")
    parser.add_argument("--boxes", type=int, default=60, help="maximum boxes reported (default 60)")
    parser.set_defaults(handler=cmd_analyze)


def add_reference(subparsers) -> None:
    parser = subparsers.add_parser("reference", help="use an image (mockup, screenshot) as the project reference")
    parser.add_argument("image", help="PNG/JPEG/WebP file")
    parser.add_argument("--width", type=int, help="resize to this width (the board width you will build)")
    parser.add_argument("--name", help="file name in .pbridge/references/ (default: the image name)")
    parser.set_defaults(handler=cmd_reference)


PARSERS = {"analyze": add_analyze, "reference": add_reference}
