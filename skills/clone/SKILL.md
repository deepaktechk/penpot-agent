---
name: clone
description: Clone a live web page into a new Penpot board pixel-accurately, then iterate until the visual quality gate passes.
argument-hint: "<url> [board name] [--font Family]"
---

# Clone a web page into Penpot

Arguments: $ARGUMENTS — a URL, optionally a board name and the main font family.

Follow the `penpot-agent` skill (sections 0–2). In short:

**This skill creates a new design: use it only when the user asked for a clone or a new design.**
To fix or change part of a design that already exists, do not clone again: modify the existing
board in place (`penpot-agent` skill, "Most important rule"). After the first build, every fix in
the steps below also touches only the sections or elements that need it.

0. **Layout choice.** **Ask the user how layers are positioned — before capturing, every new clone.** This is the user's
   choice, never yours: do not pick one, do not assume one from a previous project. Ask with a question
   (the AskUserQuestion tool in Claude Code) offering exactly these two options:
   - **Absolute** — every layer at a fixed x/y. Pixel-exact; nothing moves when the design is edited.
   - **Auto layout** — Penpot flex layouts wherever they reproduce the page exactly (edit a text and
     its neighbours move), fixed x/y everywhere else. Same accuracy gate.
   Pass the answer as `--layout absolute` or `--layout auto` on the first `pb rebuild` / `pb clone`;
   pb saves it for the project. If pb stops with "How should pb position the layers…", you skipped
   this step: ask now. Existing projects keep their saved choice (change it only when the user asks).
1. **Project folder.** One folder per site. Use the current folder only if its `.pbridge/` belongs
   to this same site; otherwise create one named after the site's domain
   (`mkdir example_com && cd example_com && pb init`). Never capture a second site into another
   site's folder: its builds would overwrite that site's board. Run `pb doctor`; if it lists
   problems, run the `setup` skill first.
2. **Inspect the site.** Find the web fonts it really uses (open the page in Chrome or read its CSS),
   cookie banners or chat widgets to hide, carousels or tabs to click. Check fonts with `pb fonts ...`.
3. **Capture.** `pb -c capture <url> --name <name> --fonts "<Family>"`. The capture gate must PASS.
   If it fails, fix the cause (fonts, `--hide`, `--click`, `--wait`) and capture again; never `--force`.
4. **Build.** `pb -c rebuild --board "<Board> – Landing Page" --after '*' --font <Family> --layout <absolute|auto> --fix --hotspots 6 --montage 6`
   with a long timeout, output saved to a file. Later rebuilds keep unchanged sections (`--all` forces all).
5. **Review.** Read the montage in `.pbridge/diffs/` and the worst sections. For each problem area:
   `pb -c compare --render latest --region x,y,w,h --hotspots 4 --montage 4`, find the cause in
   `.pbridge/captures/<name>/layout.json` vs `.pbridge/specs/<name>.json`, rebuild only those
   sections (`--only secNN`).
6. **Report** to the user: the board name, the layout mode, the page diff %, the gate verdict, warnings that remain
   and anything not reproducible automatically (filters, video, canvas...).

Ask the user to keep the Penpot tab visible during builds and exports.
