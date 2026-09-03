#!/usr/bin/env python3
"""Settle the FOURTH anchor state: quoted text with no anchor (#372).

A consumer measured 90 real threads and found **4 with `anchored=false` and substantial
`quoted_text`** — one of 244 characters, which this library's own context resolution placed in a
specific paragraph. The documented contract says `anchored=false` means the comment is about the
whole file, so a consumer branching on it mishandles those four silently, in the confident
direction.

## Why the existing measurement missed it

`experiments/docs-anchor-states/` (2026-09-02) produced the three-state table now quoted in
`comments.py`, `_schemas.py` and two tool docstrings. Every comment in that run was created **by
the editor**, plus one file-level comment created through the API. The editor cannot produce a
quote without an anchor — so the shape was unreachable by construction, and the table is complete
for editor-created comments while being stated as complete for all of them.

**This probe needs no browser, and that is the whole point.** The previous one needed a human
because only the editor can mint a real anchor. The shape here is the opposite: one only the API
can make. `quotedFileContent` is documented as *settable at create*
(`research/google-drive-comments-reference.md` §3), so `comments.create` produces it directly.

## Why a tool would create such a comment on purpose

Measured in `experiments/anchor-probe/` (2026-07-09): an API-supplied anchor is stored verbatim
and returned intact, and the editors then treat the comment as **un-anchored**. So a client that
knows this omits the anchor as useless while still recording what it quoted. That is a *sensible*
client, not a broken one — which is why this shape should be expected on any file another tool
has written to, not treated as corruption.

## What each create decides

| # | sent | decides |
|---|---|---|
| A | `content` only | the control: file-level, both keys absent (already known) |
| B | `content` + `quotedFileContent` | **THE ISSUE.** Does Drive store and return a quote with no anchor? |
| C | same, `mimeType: text/plain` | does the mimeType round-trip, or does Drive normalise to `text/html`? |
| D | `content` + `anchor` + `quotedFileContent` | does an API-created comment keep BOTH? |
| E | `content` + `anchor` only | anchor-without-quote from the API, not just from an image |
| F | `content` + a quote with newlines and padding | is the value verbatim, or normalised? |

## What it cannot decide

Whether the reporter's four rows came from an API client. That is inference from the id pattern
plus documented writability. This proves the shape is **producible**; provenance in someone
else's file is not observable from here.

It also cannot say how the editor RENDERS a quoted-but-unanchored comment — that needs eyes on a
browser, and is noted as a follow-up rather than guessed at.

Read the raw JSON. Do not summarise it in RESULTS.md before recording it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from googleapiclient.discovery import build  # noqa: E402

from csa_google_workspace import Workspace  # noqa: E402
from csa_google_workspace.auth import load_cached_credentials  # noqa: E402

TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")

# Length-matched to the reporter's rows (119, 111, 244 characters) so a length-dependent
# truncation somewhere would show up rather than hiding behind a short fixture.
PARAGRAPHS = [
    "PROBE DOCUMENT - API-created comment states (#372). Every comment on this file is created "
    "through the Drive API, which is the only way to reach the state being measured.",
    "P1. The taxonomy in this section conflates two different failure modes, and the "
    "consequence is that a reader cannot tell which one they are looking at from the text "
    "alone. That is the passage a 244-character quotation would cover, and it is here so the "
    "quote sent below has something real to correspond to in the document body.",
    "P2. A shorter paragraph, about a hundred and eleven characters long, for the middle case.",
]
# The exact text of P1, so `quotedFileContent` corresponds to real document content the way a
# genuine client's would - a quote matching nothing would be a different (and easier) test.
QUOTE_LONG = PARAGRAPHS[1][4:248]
QUOTE_SHORT = PARAGRAPHS[2][4:]
# Shaped like a real Docs anchor (`kix.` + an opaque id), because sending obvious junk would
# test Drive's validation rather than its storage.
FAKE_ANCHOR = "kix.probe372anchornotreal"

CREATES = [
    ("A file-level control (content only)",
     {"content": "A - control: no anchor, no quote"}),
    ("B quote, NO anchor - the reported fourth state",
     {"content": "B - quotedFileContent with no anchor",
      "quotedFileContent": {"mimeType": "text/html", "value": QUOTE_LONG}}),
    ("C same as B but mimeType text/plain",
     {"content": "C - does mimeType round-trip",
      "quotedFileContent": {"mimeType": "text/plain", "value": QUOTE_SHORT}}),
    ("D anchor AND quote",
     {"content": "D - both fields set",
      "anchor": FAKE_ANCHOR,
      "quotedFileContent": {"mimeType": "text/html", "value": QUOTE_SHORT}}),
    ("E anchor only, no quote",
     {"content": "E - anchor with nothing quoted", "anchor": FAKE_ANCHOR}),
    ("F quote with newlines and padding - is the value verbatim?",
     {"content": "F - whitespace fidelity",
      "quotedFileContent": {"mimeType": "text/html",
                            "value": "  leading spaces\nand a newline\ttab  "}}),
]

FIELDS = ("id,anchor,content,quotedFileContent,createdTime,author(displayName),resolved,deleted")


def services():
    creds = load_cached_credentials(TOKEN, read_only=False)
    return build("drive", "v3", credentials=creds), build("docs", "v1", credentials=creds)


def create_doc(drive, docs) -> str:
    meta = drive.files().create(
        body={"name": "PROBE api-created comment states (throwaway)",
              "mimeType": "application/vnd.google-apps.document"},
        fields="id,webViewLink").execute()
    file_id = meta["id"]
    requests = [{"insertText": {"location": {"index": 1}, "text": p + "\n"}}
                for p in reversed(PARAGRAPHS)]
    docs.documents().batchUpdate(documentId=file_id, body={"requests": requests}).execute()
    print(f"created: {meta['webViewLink']}\nfile id: {file_id}\n")
    return file_id


def create_comments(drive, file_id: str) -> None:
    """Each create printed with what was SENT beside what came BACK, one beside the other.

    Printed as a pair on purpose: the interesting result is a field that was sent and did not
    come back, and a dump of only the response cannot show that.
    """
    for label, body in CREATES:
        print(f"─────────── {label}")
        print("  SENT     : " + json.dumps(body, ensure_ascii=False))
        try:
            got = drive.comments().create(fileId=file_id, body=body, fields=FIELDS).execute()
        except Exception as e:                                   # noqa: BLE001 - report, continue
            print(f"  REFUSED  : {type(e).__name__}: {e}\n")
            continue
        print("  RETURNED : " + json.dumps(got, ensure_ascii=False))
        sent_q = (body.get("quotedFileContent") or {}).get("value")
        got_q = (got.get("quotedFileContent") or {}).get("value")
        print(f"  'anchor' key back        : {'anchor' in got}   value: {got.get('anchor')!r}")
        print(f"  'quotedFileContent' back : {'quotedFileContent' in got}")
        if sent_q is not None:
            print(f"  quote VERBATIM           : {sent_q == got_q}")
            if sent_q != got_q:
                print(f"    sent {sent_q!r}\n    got  {got_q!r}")
            sent_m = (body.get("quotedFileContent") or {}).get("mimeType")
            got_m = (got.get("quotedFileContent") or {}).get("mimeType")
            print(f"  mimeType sent/back       : {sent_m!r} -> {got_m!r}")
        if body.get("anchor") and got.get("anchor") != body.get("anchor"):
            print(f"  ANCHOR CHANGED           : sent {body['anchor']!r} got {got.get('anchor')!r}")
        print()


def dump_raw(drive, file_id: str) -> None:
    """`comments.list` with the SAME field mask the library uses, so nothing is masked out."""
    print("=== raw comments.list ===")
    page = None
    while True:
        got = drive.comments().list(fileId=file_id, fields=f"comments({FIELDS}),nextPageToken",
                                    pageSize=100, includeDeleted=False, pageToken=page).execute()
        for c in got.get("comments", []):
            qfc = c.get("quotedFileContent")
            print(f"  {c.get('content','')[:34]:<36} "
                  f"anchor={'YES' if 'anchor' in c else 'no ':<4} "
                  f"quoted={'YES' if qfc else 'no ':<4} "
                  f"len={len((qfc or {}).get('value') or '')}")
        page = got.get("nextPageToken")
        if not page:
            break


def dump_library(file_id: str) -> None:
    """THE POINT: what does OUR model say about each of these?

    The raw dump above proves what Drive returns. This proves what a consumer of this library
    sees, which is the thing #372 is actually about - and the two must be read together, because
    `anchored` is derived and a derivation is exactly where the divergence lives.
    """
    print("\n=== through the library (Comment.anchored) ===")
    ws = Workspace.from_credentials(load_cached_credentials(TOKEN, read_only=False))
    doc = ws.open(file_id)
    print(f"  {'comment':<36} {'anchored':<9} {'quoted?':<8} quote len")
    for c in doc.comments:
        n = len(c.quoted_text or "")
        flag = "  <-- FOURTH STATE" if (not c.anchored and n) else ""
        print(f"  {(c.content or '')[:34]:<36} {str(c.anchored):<9} "
              f"{str(c.quoted_text is not None):<8} {n}{flag}")


def trash(drive, file_id: str) -> None:
    drive.files().update(fileId=file_id, body={"trashed": True}).execute()
    print(f"\ntrashed {file_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file-id")
    ap.add_argument("--create", action="store_true", help="make a throwaway Doc")
    ap.add_argument("--comments", action="store_true", help="create the six comments")
    ap.add_argument("--dump", action="store_true", help="raw list + through the library")
    ap.add_argument("--trash", action="store_true", help="trash the throwaway Doc")
    args = ap.parse_args()

    drive, docs = services()
    file_id = args.file_id
    if args.create:
        file_id = create_doc(drive, docs)
    if not file_id:
        print("need --file-id (or --create)", file=sys.stderr)
        return 2
    if args.comments:
        create_comments(drive, file_id)
    if args.dump:
        dump_raw(drive, file_id)
        dump_library(file_id)
    if args.trash:
        trash(drive, file_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
