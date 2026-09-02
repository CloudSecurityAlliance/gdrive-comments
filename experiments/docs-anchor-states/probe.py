#!/usr/bin/env python3
"""Settle what a real Google DOCS comment anchor looks like, per anchor state.

The 2026-07-09 `anchor-probe` measured **Sheets** and is the reason
`research/google-drive-comments-reference.md` §7 is correct. Docs was never measured, and two
open issues turn on it:

* **#361** — can a consumer tell "the commenter selected nothing" from "there is no anchor"
  from "the field is absent"? Today all three arrive as a falsy `quoted_text`.
* **#358** — anchors as a *localization hint*. Its highest-ranked request is a context window
  around the anchor, and whether that is buildable **for the comments that need it most**
  depends entirely on whether a Docs anchor carries a resolvable position.

## Why a human has to place the comments

Measured in the Sheets probe: a comment created through the Drive API has its anchor **stored
verbatim** and is then treated as *un-anchored* by the editor. Google says so too — "developers
can define their own format … Google Workspace editor apps treat these comments as un-anchored
comments." So an API-created comment cannot produce a real anchor, and no amount of scripting
substitutes for a right-click in the UI.

`--create` and `--file-level` are the halves a script can do; `--dump` reads what your hands
produced.

## The states, and why each is in the list

| # | state | how to make it | what it decides |
|---|---|---|---|
| 1 | file-level | `--file-level` (API, no anchor) | the baseline: what "no anchor at all" looks like |
| 2 | cursor, nothing selected | click in text, do NOT select, comment | **#361's live 2-of-90.** Anchor present? |
| 3 | normal selection | select a few words, comment | the easy case, for contrast |
| 4 | whole paragraph | select a full paragraph, comment | does the anchor's span scale, or is it positional only? |
| 5 | across paragraphs | select from one paragraph into the next | #358 §3's "crosses a paragraph boundary" |
| 6 | on an image | click the image, comment | #358's caveat list: is there anything to quote? |
| 7 | in a table cell | click inside a table cell, comment | same |

## What the raw output settles

Google's ONE published Docs example is `{"region": {"kind": "drive#commentRegion", "line": N,
"rev": "head"}}` — which carries a **position**. If real anchors look like that, a context
window is buildable even with no quoted text. If they are `kix.*` opaque ids, then for state 2
there is nothing to locate and #358's top request is unbuildable **precisely where it matters**,
which is a finding worth more than a feature.

Read the raw JSON. Do not summarise it in the results file before recording it.
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

# Numbered, so a `line` in an anchor can be compared against something. Deliberately varied in
# length: a three-word anchor and a three-paragraph anchor need different amounts of help, which
# is #358 §1's argument for structural rather than character-count context.
PARAGRAPHS = [
    "PROBE DOCUMENT - anchor states. Every paragraph is numbered so an anchor carrying a line "
    "or index can be checked against a known position.",
    "P1. Short paragraph.",
    "P2. This paragraph is deliberately longer, so that selecting three words out of it "
    "produces an anchor whose span is much smaller than the point the comment is making - "
    "which is the sloppy-selection case the whole exercise is about.",
    "P3. The taxonomy in this section is wrong.",
    "P4. Second-to-last paragraph, for a selection that crosses from here",
    "P5. into this one.",
]


def services():
    creds = load_cached_credentials(TOKEN, read_only=False)
    return build("drive", "v3", credentials=creds), build("docs", "v1", credentials=creds)


def create(drive, docs) -> str:
    """A throwaway Doc with numbered paragraphs, a table and an image placeholder."""
    meta = drive.files().create(
        body={"name": "PROBE anchor states (throwaway)",
              "mimeType": "application/vnd.google-apps.document"},
        fields="id,webViewLink").execute()
    file_id = meta["id"]
    # Inserted in reverse at index 1, so the order comes out as written without arithmetic.
    requests = [{"insertText": {"location": {"index": 1}, "text": p + "\n"}}
                for p in reversed(PARAGRAPHS)]
    requests.append({"insertTable": {"rows": 2, "columns": 2,
                                     "endOfSegmentLocation": {"segmentId": ""}}})
    docs.documents().batchUpdate(documentId=file_id, body={"requests": requests}).execute()
    print(f"created: {meta['webViewLink']}\n")
    print("NOW, IN THE BROWSER, place SIX comments in this order:")
    print("  2. click inside P1 but select NOTHING, then Insert > Comment   <- the #361 case")
    print("  3. select the three words 'taxonomy in this' in P3, comment")
    print("  4. select the WHOLE of P2, comment")
    print("  5. select from the end of P4 into the start of P5, comment")
    print("  6. click a table cell, comment")
    print("  7. insert any image, click it, comment")
    print(f"\nthen: python probe.py --file-id {file_id} --dump --structure")
    return file_id


def file_level(drive, file_id: str) -> None:
    """State 1, which a script CAN make: a comment with no anchor at all."""
    out = drive.comments().create(
        fileId=file_id, body={"content": "STATE 1 - file-level, created via API with no anchor"},
        fields="id,anchor,quotedFileContent,content").execute()
    print("file-level comment created:\n" + json.dumps(out, indent=2) + "\n")


def dump(drive, file_id: str) -> None:
    """Every comment, raw. The `anchor` and `quotedFileContent` keys are the whole point."""
    fields = ("comments(id,anchor,quotedFileContent,content,createdTime,author(displayName),"
              "resolved,replies(id,content,action)),nextPageToken")
    page, n = None, 0
    while True:
        got = drive.comments().list(fileId=file_id, fields=fields, pageSize=100,
                                    includeDeleted=False, pageToken=page).execute()
        for c in got.get("comments", []):
            n += 1
            print(f"─────────── comment {n}: {c.get('id')}")
            print(f"  content            : {c.get('content','')[:70]!r}")
            # THE THREE-STATE QUESTION (#361), asked of the raw payload rather than of a model.
            print(f"  'anchor' key present            : {'anchor' in c}")
            print(f"  anchor raw                      : {c.get('anchor')!r}")
            print(f"  'quotedFileContent' key present : {'quotedFileContent' in c}")
            qfc = c.get("quotedFileContent")
            print(f"  quotedFileContent raw           : {json.dumps(qfc)}")
            if qfc is not None:
                print(f"    .value present : {'value' in qfc}   .value: {qfc.get('value')!r}")
            # If the anchor is JSON, show its shape - Google's one published Docs example
            # carries {"region":{"kind":"drive#commentRegion","line":N,"rev":"head"}}.
            raw = c.get("anchor")
            if raw:
                try:
                    print(f"  anchor PARSED                   : {json.dumps(json.loads(raw))}")
                except (ValueError, TypeError):
                    print("  anchor PARSED                   : not JSON (opaque string)")
        page = got.get("nextPageToken")
        if not page:
            break
    print(f"\n{n} comment(s). Record this output verbatim in RESULTS.md before interpreting it.")


def structure(docs, file_id: str) -> None:
    """What the DOCS API would give a context window to work with, independent of anchors.

    Asked separately because it decides whether #358's §1 and §2 are buildable at all: a
    context window needs paragraph boundaries, and a structural path needs the heading chain.
    """
    doc = docs.documents().get(documentId=file_id, includeTabsContent=True).execute()
    tabs = doc.get("tabs") or []
    print(f"tabs: {len(tabs)}   (top-level 'body' present: {'body' in doc})")
    body = (tabs[0]["documentTab"]["body"] if tabs else doc.get("body", {}))
    for el in body.get("content", []):
        if "paragraph" in el:
            para = el["paragraph"]
            style = para.get("paragraphStyle", {}).get("namedStyleType")
            runs = "".join(r.get("textRun", {}).get("content", "")
                           for r in para.get("elements", []))
            print(f"  [{el.get('startIndex')}..{el.get('endIndex')}] {style:16} "
                  f"{runs.strip()[:60]!r}")
        elif "table" in el:
            print(f"  [{el.get('startIndex')}..{el.get('endIndex')}] TABLE "
                  f"{len(el['table'].get('tableRows', []))} rows")
    print("\nNote what is and is not here: startIndex/endIndex per element (so a character "
          "offset IS resolvable to a paragraph), namedStyleType (so a heading chain is "
          "derivable) - and NO page number anywhere, which is #358 §4.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file-id")
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--file-level", action="store_true")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--structure", action="store_true")
    args = ap.parse_args()

    drive, docs = services()
    file_id = args.file_id
    if args.create:
        file_id = create(drive, docs)
    if not file_id:
        print("need --file-id (or --create)", file=sys.stderr)
        return 2
    if args.file_level:
        file_level(drive, file_id)
    if args.dump:
        dump(drive, file_id)
    if args.structure:
        structure(docs, file_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
