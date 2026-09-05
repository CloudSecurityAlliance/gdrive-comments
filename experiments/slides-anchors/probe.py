#!/usr/bin/env python3
"""Settle what a real Google SLIDES comment anchor looks like, per target.

Docs was measured in `../docs-anchor-states/`, Sheets in `../anchor-probe/`. Slides was the
third addressing model and **nobody here had ever seen one** (#400) — while `anchor_state` was
already being reported for decks, derived entirely from the Docs and Sheets measurements. That
is the shape of every mistake this project has had to correct: a measurement taken on one
surface, stated as though it covered all of them.

## Why a human (or a browser driver) has to place the comments

Same reason as the Docs probe: a comment created through the Drive API has its anchor stored
verbatim and is then treated as un-anchored by the editor. Only the editor mints a real anchor.
`--file-level` and `--furniture` are the halves a script can do; `--dump` reads what the editor
produced.

`--furniture` adds the two elements the interesting cases need and the deck did not have:

* **a shape with NO TEXT** (`zooNoText`, an ellipse). Selecting a shape that *has* text does not
  give you an object-anchored comment — Slides anchors to the word under the cursor instead, the
  same way the Docs editor expands a bare caret to its enclosing word. A shape with nothing to
  quote is the only way to reach an anchored comment carrying no quoted text.
* **a table** (`zooTable`), to find out whether a Slides anchor addresses a *cell* or only the
  table. Sheets needs an XLSX export and a three-hop relationship walk for that answer.

## The targets, and what each decides

| # | target | what it decides |
|---|---|---|
| 1 | the slide, nothing selected | is there a distinct whole-slide anchor type? |
| 2 | a shape that has text, selected as an object | does an object selection anchor to the object? |
| 3 | text inside that shape | does Slides populate `quotedFileContent`? |
| 4 | the speaker notes | can a consumer tell notes from slide body? |
| 5 | a shape with no text | is the `object` anchor state reachable at all? |
| 6 | a table cell | cell-level addressing, or only the table? |

## What the raw output settles

Whether the four-state model (`file` / `object` / `text` / `quote_only`) holds on a third
editor, and whether a Slides anchor is **resolvable** — Docs anchors are opaque `kix.*` ids and
Sheets `range`s are opaque internal ids, so neither can be turned into a location without a
detour. Read the raw JSON. Do not summarise it in RESULTS.md before recording it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from googleapiclient.discovery import build            # noqa: E402

from csa_google_workspace.auth import load_cached_credentials   # noqa: E402

TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")

# The zoo's `slides-comments` specimen. Any deck works; this is the one that was measured.
DEFAULT_FILE = "193nXMbPMKy_Ubon_3AMBA4wWxNdxvA8S_xWCc9_s5xk"


def services():
    creds = load_cached_credentials(os.path.expanduser(TOKEN), read_only=False)
    return build("drive", "v3", credentials=creds), build("slides", "v1", credentials=creds)


def furniture(slides, file_id: str) -> None:
    """The two elements the interesting cases need. Idempotent by object id."""
    requests = [
        {"createShape": {
            "objectId": "zooNoText", "shapeType": "ELLIPSE",
            "elementProperties": {
                "pageObjectId": "p",
                "size": {"width": {"magnitude": 2000000, "unit": "EMU"},
                         "height": {"magnitude": 1200000, "unit": "EMU"}},
                "transform": {"scaleX": 1, "scaleY": 1, "translateX": 5800000,
                              "translateY": 3200000, "unit": "EMU"}}}},
        {"createTable": {
            "objectId": "zooTable", "rows": 2, "columns": 2,
            "elementProperties": {
                "pageObjectId": "p",
                "size": {"width": {"magnitude": 3000000, "unit": "EMU"},
                         "height": {"magnitude": 1000000, "unit": "EMU"}},
                "transform": {"scaleX": 1, "scaleY": 1, "translateX": 500000,
                              "translateY": 3400000, "unit": "EMU"}}}},
        {"insertText": {"objectId": "zooTable", "cellLocation": {"rowIndex": 1, "columnIndex": 0},
                        "text": "Comment on this cell"}},
    ]
    slides.presentations().batchUpdate(presentationId=file_id,
                                       body={"requests": requests}).execute()
    print("created zooNoText (ELLIPSE, no text) and zooTable (2x2) on page p\n")
    print("NOW, IN THE BROWSER, place SIX comments in this order:")
    print("  1. select NOTHING, Insert > Comment            <- is there a whole-slide anchor?")
    print("  2. single-click the text shape, comment        <- object selection")
    print("  3. double-click INTO that shape's text, comment")
    print("  4. double-click a word in the SPEAKER NOTES, comment")
    print("  5. click the ellipse, comment                  <- the no-text case")
    print("  6. double-click a word in a table cell, comment")
    print(f"\nthen: python probe.py --file-id {file_id} --dump --elements")


def file_level(drive, file_id: str) -> None:
    """The baseline a script CAN make: a comment with no anchor at all."""
    out = drive.comments().create(
        fileId=file_id, body={"content": "BASELINE - file-level, created via API, no anchor"},
        fields="id,anchor,quotedFileContent,content").execute()
    print("file-level comment created:\n" + json.dumps(out, indent=2) + "\n")


def dump(drive, file_id: str) -> None:
    """Every comment, raw. The `anchor` and `quotedFileContent` keys are the whole point."""
    fields = ("comments(id,anchor,quotedFileContent,content,createdTime,"
              "author(displayName),resolved),nextPageToken")
    page, n = None, 0
    while True:
        got = drive.comments().list(fileId=file_id, fields=fields, pageSize=100,
                                    includeDeleted=False, pageToken=page).execute()
        for c in got.get("comments", []):
            n += 1
            # The specimen labels its comments SLIDE-1..SLIDE-6 in the first token.
            label = c.get("content", "").split(":")[0][:60]
            print(f"─────────── {label}  ({c.get('id')})")
            print(f"  'anchor' key present : {'anchor' in c}")
            print(f"  anchor raw           : {c.get('anchor')!r}")
            raw = c.get("anchor")
            if raw:
                try:
                    print(f"  anchor PARSED        : {json.dumps(json.loads(raw))}")
                except (ValueError, TypeError):
                    print("  anchor PARSED        : not JSON (opaque string)")
            qfc = c.get("quotedFileContent")
            print(f"  quotedFileContent    : {json.dumps(qfc)}")
        page = got.get("nextPageToken")
        if not page:
            break
    print(f"\n{n} comment(s). Record this verbatim in RESULTS.md before interpreting it.")


def elements(slides, file_id: str) -> None:
    """The presentation's OWN object ids, so an anchor's `targets` can be checked against them.

    This is the comparison that matters: if `targets` names ids that appear here, a Slides
    anchor is resolvable and needs no export-and-parse detour. Note that the notes page is
    listed separately — that is what makes the `page` field checkable.
    """
    pres = slides.presentations().get(presentationId=file_id).execute()
    for pg in pres.get("slides", []):
        print(f"  slide objectId: {pg['objectId']}")
        for el in pg.get("pageElements", []):
            kind = "table" if "table" in el else ("shape" if "shape" in el else "?")
            print(f"    element: {el['objectId']:14} ({kind})")
        notes = pg.get("slideProperties", {}).get("notesPage", {})
        if notes:
            print(f"    notesPage objectId: {notes.get('objectId')}")
            for el in notes.get("pageElements", []):
                print(f"      notes element: {el['objectId']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file-id", default=DEFAULT_FILE)
    ap.add_argument("--furniture", action="store_true")
    ap.add_argument("--file-level", action="store_true")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--elements", action="store_true")
    args = ap.parse_args()

    drive, slides = services()
    if args.furniture:
        furniture(slides, args.file_id)
    if args.file_level:
        file_level(drive, args.file_id)
    if args.dump:
        dump(drive, args.file_id)
    if args.elements:
        elements(slides, args.file_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
