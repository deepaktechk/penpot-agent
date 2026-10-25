---
name: clone
description: Clone a live web page into a new Penpot board pixel-accurately, then iterate until the visual quality gate passes.
argument-hint: "<url> [board name] [--font Family]"
---

# Clone a web page into Penpot

Arguments: $ARGUMENTS — a URL, optionally a board name and the main font family.

Follow the `penpot-agent` skill (sections 0–2). In short:

1. **Project folder.** Use the current folder if it has `.pbridge/`; otherwise create one named after
   the site's domain (`mkdir example_com && cd example_com && pb init`). Run `pb doctor`; if it lists
   problems, run the `setup` skill first.
2. **Inspect the site.** Find the web fonts it really uses (open the page in Chrome or read its CSS),
   cookie banners or chat widgets to hide, carousels or tabs to click. Check fonts with `pb fonts ...`.
3. **Capture.** `pb -c capture <url> --name <name> --fonts "<Family>"`. The capture gate must PASS.
   If it fails, fix the cause (fonts, `--hide`, `--click`, `--wait`) and capture again; never `--force`.
4. **Build.** `pb -c rebuild --board "<Board> – Landing Page" --after '*' --font <Family> --fix --hotspots 6 --montage 6`
   with a long timeout, output saved to a file.
5. **Review.** Read the montage in `.pbridge/diffs/` and the worst sections. For each problem area:
   `pb -c compare --render latest --region x,y,w,h --hotspots 4 --montage 4`, find the cause in
   `.pbridge/captures/<name>/layout.json` vs `.pbridge/specs/<name>.json`, rebuild only those
   sections (`--only secNN`).
6. **Report** to the user: the board name, the page diff %, the gate verdict, warnings that remain
   and anything not reproducible automatically (filters, video, canvas...).

Ask the user to keep the Penpot tab visible during builds and exports.
