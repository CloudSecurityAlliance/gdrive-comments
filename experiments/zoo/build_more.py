#!/usr/bin/env python3
"""Stage everything the API can, so a browser session is pure clicking.

Three things `build.py` did not do:

* **The comment LIFECYCLE, fully through the API.** Resolve and reopen are *action-replies*
  rather than a field update (measured 2026-07-20), which is exactly why they are reachable
  without a browser and exactly why naive code misses them. Soft delete is `comments.delete`.
  So `docs-lifecycle` needs no hands for its lifecycle at all — an earlier version of the
  specimen said it did, which was wrong.
* **Spreadsheet specimens** — notes (which the comments API cannot see) and a header row that
  is not row 1 (so the header guess is demonstrably wrong).
* **A deck** — for #400, where nothing in this project has ever looked at what a Slides comment
  contains.

**What it deliberately does not do is place an anchored comment**, because it cannot: only the
editor mints an anchor. Everything here is the *material*, staged so the hand-placement session
is clicking rather than setting up.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from _content import SHEET_SPECIMENS, SLIDE_SPECIMENS, body  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

from csa_google_workspace.auth import load_cached_credentials  # noqa: E402

TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")
TODAY = _dt.date.today().isoformat()
SHEET = "application/vnd.google-apps.spreadsheet"
DECK = "application/vnd.google-apps.presentation"


def services():
    c = load_cached_credentials(TOKEN, read_only=False)
    return (build("drive", "v3", credentials=c), build("sheets", "v4", credentials=c),
            build("slides", "v1", credentials=c), build("docs", "v1", credentials=c))


def find_or_make(drive, name, parent, drive_id, mime):
    q = (f"name = '{name}' and mimeType = '{mime}' and '{parent}' in parents "
         f"and trashed = false")
    hit = drive.files().list(q=q, corpora="drive", driveId=drive_id,
                             includeItemsFromAllDrives=True, supportsAllDrives=True,
                             fields="files(id)").execute().get("files", [])
    if hit:
        return hit[0]["id"], False
    made = drive.files().create(body={"name": name, "mimeType": mime, "parents": [parent]},
                                supportsAllDrives=True, fields="id").execute()
    return made["id"], True


def stage_lifecycle(drive, file_id: str) -> dict:
    """The whole comment lifecycle, through the API. No browser anywhere in here.

    Ordered so the resulting thread reads as a story: a comment, replies, a resolve, a reopen.
    `resolved` is asserted at each step because the interesting fact is that it is ABSENT
    before anything happens rather than false.
    """
    out = {}
    c = drive.comments().create(fileId=file_id, fields="id,resolved", body={
        "content": "LIFECYCLE 1 - a thread that gets replies, then a resolve, then a reopen. "
                   "Note that `resolved` is ABSENT on this comment right now, not false."}
    ).execute()
    out["thread"] = c["id"]
    out["resolved_key_present_at_creation"] = "resolved" in c

    for text in ("A first reply.",
                 "A second reply, so the thread has a shape."):
        drive.replies().create(fileId=file_id, commentId=c["id"], fields="id",
                               body={"content": text}).execute()
    # RESOLVE is a reply carrying an action, not a PATCH.
    drive.replies().create(fileId=file_id, commentId=c["id"], fields="id,action",
                           body={"action": "resolve",
                                 "content": "Resolving - and this reply IS the resolve."}).execute()
    # REOPEN, likewise - and deliberately with NO content, because a blank action-reply is a
    # state change and not a mistake. Naive code renders it as an empty comment.
    drive.replies().create(fileId=file_id, commentId=c["id"], fields="id,action",
                           body={"action": "reopen"}).execute()

    after = drive.comments().get(fileId=file_id, commentId=c["id"],
                                 fields="id,resolved,replies(id,action,content)").execute()
    out["resolved_after_reopen"] = after.get("resolved")
    out["replies"] = [(r.get("action"), bool(r.get("content"))) for r in after.get("replies", [])]

    # A tombstone: soft delete strips BOTH content and author.
    doomed = drive.comments().create(fileId=file_id, fields="id", body={
        "content": "LIFECYCLE 2 - this comment is about to be soft-deleted, so what remains is "
                   "a tombstone: the id and the timestamps survive, the content and the AUTHOR "
                   "do not."}).execute()
    drive.comments().delete(fileId=file_id, commentId=doomed["id"]).execute()
    tomb = drive.comments().get(fileId=file_id, commentId=doomed["id"], includeDeleted=True,
                                fields="id,deleted,content,author").execute()
    out["tombstone"] = {"deleted": tomb.get("deleted"),
                        "content_survives": bool(tomb.get("content")),
                        "author_survives": bool((tomb.get("author") or {}).get("displayName"))}
    return out


def stage_sheet_notes(sheets, file_id: str) -> None:
    """Notes on cells — the thing `comments.list` cannot see."""
    sheets.spreadsheets().batchUpdate(spreadsheetId=file_id, body={"requests": [
        {"updateCells": {
            "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 4,
                      "startColumnIndex": 0, "endColumnIndex": 2},
            "rows": [
                {"values": [{"userEnteredValue": {"stringValue": "Item"}},
                            {"userEnteredValue": {"stringValue": "Count"}}]},
                {"values": [{"userEnteredValue": {"stringValue": "Widgets"}},
                            {"userEnteredValue": {"numberValue": 7},
                             "note": "A NOTE, not a comment. No author, no thread, cannot be "
                                     "replied to or resolved."}]},
                {"values": [{"userEnteredValue": {"stringValue": "Gadgets"}},
                            {"userEnteredValue": {"numberValue": 12},
                             "note": "A second note. `list_comments` on this file returns ZERO "
                                     "- truthfully, and misleadingly."}]},
                {"values": [{"userEnteredValue": {"stringValue": "Sprockets"}},
                            {"userEnteredValue": {"numberValue": 3},
                             "note": "A third. Use `list_notes` for these."}]}],
            "fields": "userEnteredValue,note"}}]}).execute()


def stage_offset_header(sheets, file_id: str) -> None:
    """A grid whose real header row is row 4, under a title block."""
    rows = [["QUARTERLY SUMMARY - this row is a TITLE, not a header"], [], [],
            ["Region", "Q3 actual", "Q3 target"],
            ["Southwest", "388000", "400000"],
            ["Northeast", "412000", "400000"]]
    sheets.spreadsheets().values().update(
        spreadsheetId=file_id, range="A1:C6", valueInputOption="RAW",
        body={"values": [r + [""] * (3 - len(r)) for r in rows]}).execute()


def stage_deck(slides, file_id: str) -> None:
    """A deck with every kind of comment target: shape, text, table, empty shape, notes.

    `zooNoText` and `zooTable` are not decoration. Measured 2026-09-05
    (`experiments/slides-anchors/`):

    * selecting a shape that HAS text does not produce an object-anchored comment — Slides
      anchors to the word under the cursor instead — so a shape with **nothing to quote** is
      the only way to reach the `object` anchor state on a deck;
    * a table is the only way to ask whether a Slides anchor addresses a **cell**. (It does
      not; it names the table.)
    """
    pres = slides.presentations().get(presentationId=file_id).execute()
    first = pres["slides"][0]["objectId"]
    slides.presentations().batchUpdate(presentationId=file_id, body={"requests": [
        {"createShape": {"objectId": "zooShape1", "shapeType": "TEXT_BOX",
                         "elementProperties": {
                             "pageObjectId": first,
                             "size": {"width": {"magnitude": 3000000, "unit": "EMU"},
                                      "height": {"magnitude": 1000000, "unit": "EMU"}},
                             "transform": {"scaleX": 1, "scaleY": 1, "translateX": 500000,
                                           "translateY": 500000, "unit": "EMU"}}}},
        {"insertText": {"objectId": "zooShape1",
                        "text": "Text inside a shape. Comment on this text, and on the shape "
                                "itself, and compare the two anchors."}},
        # The no-text case. An ELLIPSE because it obviously holds no text, where an empty
        # TEXT_BOX looks like a mistake somebody should fix.
        {"createShape": {"objectId": "zooNoText", "shapeType": "ELLIPSE",
                         "elementProperties": {
                             "pageObjectId": first,
                             "size": {"width": {"magnitude": 2000000, "unit": "EMU"},
                                      "height": {"magnitude": 1200000, "unit": "EMU"}},
                             "transform": {"scaleX": 1, "scaleY": 1, "translateX": 5800000,
                                           "translateY": 3200000, "unit": "EMU"}}}},
        {"createTable": {"objectId": "zooTable", "rows": 2, "columns": 2,
                         "elementProperties": {
                             "pageObjectId": first,
                             "size": {"width": {"magnitude": 3000000, "unit": "EMU"},
                                      "height": {"magnitude": 1000000, "unit": "EMU"}},
                             "transform": {"scaleX": 1, "scaleY": 1, "translateX": 500000,
                                           "translateY": 3400000, "unit": "EMU"}}}},
        {"insertText": {"objectId": "zooTable", "text": "Header alpha",
                        "cellLocation": {"rowIndex": 0, "columnIndex": 0}}},
        {"insertText": {"objectId": "zooTable", "text": "Header beta",
                        "cellLocation": {"rowIndex": 0, "columnIndex": 1}}},
        {"insertText": {"objectId": "zooTable", "text": "Comment on this cell",
                        "cellLocation": {"rowIndex": 1, "columnIndex": 0}}},
        {"insertText": {"objectId": "zooTable", "text": "Leave this one alone",
                        "cellLocation": {"rowIndex": 1, "columnIndex": 1}}},
    ]}).execute()
    # Speaker notes live on a separate page; its id has to be read back.
    pres = slides.presentations().get(presentationId=file_id).execute()
    notes = pres["slides"][0].get("slideProperties", {}).get("notesPage", {})
    for el in notes.get("pageElements", []):
        if el.get("shape", {}).get("placeholder", {}).get("type") == "BODY":
            slides.presentations().batchUpdate(presentationId=file_id, body={"requests": [
                {"insertText": {"objectId": el["objectId"],
                                "text": "Speaker notes. A separate element tree - comment "
                                        "here too, and see whether the anchor differs."}}]}
            ).execute()
            break


# Measured on this deck at 8pt in a 8.5M x 4.7M EMU box: about 3200 characters reach the
# bottom edge of the slide. 2400 leaves room for a heading and for the next paragraph to be a
# long one, since the split lands on a blank line and never mid-sentence.
_PAGE_BUDGET = 2400


def _paginate(text: str) -> list[str]:
    """Split the specimen into slide-sized chunks on blank lines.

    On a blank line rather than a character count because the alternative is a page break in
    the middle of a measured finding, and a reader who sees half of one has been told something
    false rather than something incomplete. A single paragraph longer than the budget is
    emitted whole and allowed to overflow — truncating documentation to fit its container is
    the failure this whole exercise is correcting.
    """
    pages: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if current and len(candidate) > _PAGE_BUDGET:
            pages.append(current)
            current = block
        else:
            current = candidate
    if current:
        pages.append(current)
    return pages


def document_deck(slides, drive, file_id: str, text: str) -> None:
    """Put the specimen's documentation on a README SLIDE, and a pointer in a comment.

    A file-level comment was the obvious home and it does not fit: **Drive caps comment content
    at 4096 UTF-8 bytes** (measured 2026-09-05 — `403 commentLengthLimitExceeded`, which this
    library now raises as `InvalidInputError` rather than letting it masquerade as a permission
    problem). The documentation is 4972 bytes, so the medium chose itself.

    Same shape as the decision the Sheets specimens already made — documentation went to a
    README *tab* there — and the same placement rule for the same reason: the README goes
    **LAST**. A README tab at index 0 silently changed what every unqualified A1 read returned,
    and a README slide at index 0 would silently change what "the first slide" means to
    everything that opens this deck, including the thumbnail.

    The pointer comment is kept because it is the only part of a deck a Drive-level tool sees
    without opening it — and it is deliberately SHORT, so it cannot drift past the cap again.
    """
    pages = _paginate(text)
    pres = slides.presentations().get(presentationId=file_id).execute()
    index = len(pres.get("slides", []))
    requests: list[dict] = []
    for n, chunk in enumerate(pages, 1):
        slide_id, box_id = f"zooReadme{n}", f"zooReadmeText{n}"
        heading = f"README ({n} of {len(pages)})\n\n"
        requests += [
            {"createSlide": {"objectId": slide_id, "insertionIndex": index + n - 1,
                             "slideLayoutReference": {"predefinedLayout": "BLANK"}}},
            {"createShape": {"objectId": box_id, "shapeType": "TEXT_BOX",
                             "elementProperties": {
                                 "pageObjectId": slide_id,
                                 "size": {"width": {"magnitude": 8500000, "unit": "EMU"},
                                          "height": {"magnitude": 4700000, "unit": "EMU"}},
                                 "transform": {"scaleX": 1, "scaleY": 1, "translateX": 300000,
                                               "translateY": 200000, "unit": "EMU"}}}},
            {"insertText": {"objectId": box_id, "text": heading + chunk}},
            # 8pt with the text PAGINATED to fit. Font size alone cannot solve this: the whole
            # specimen at a size that fits one slide is unreadable, and Slides does not clip
            # overflow, it just draws it outside the canvas — so a single slide LOOKS fine in
            # the editor and loses its last third in presentation and thumbnail views.
            {"updateTextStyle": {"objectId": box_id,
                                 "style": {"fontSize": {"magnitude": 8, "unit": "PT"}},
                                 "textRange": {"type": "ALL"}, "fields": "fontSize"}},
        ]
    slides.presentations().batchUpdate(presentationId=file_id,
                                       body={"requests": requests}).execute()
    drive.comments().create(fileId=file_id, body={"content": (
        "SPECIMEN — comments on a deck. The documentation for this file is on its LAST slide, "
        "titled README, because Drive caps a comment at 4096 UTF-8 bytes and the explanation is "
        "longer than that. Findings are in experiments/slides-anchors/RESULTS.md in the "
        "csa-google-workspace repository.")}, fields="id").execute()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", required=True, help="the `comments` folder id")
    ap.add_argument("--drive", required=True)
    ap.add_argument("--lifecycle", help="file id of docs-lifecycle, to stage its threads")
    args = ap.parse_args()

    drive, sheets, slides, _docs = services()
    findings: dict = {}

    if args.lifecycle:
        print("staging the comment lifecycle through the API...")
        findings["lifecycle"] = stage_lifecycle(drive, args.lifecycle)
        print(json.dumps(findings["lifecycle"], indent=2))

    for name in SHEET_SPECIMENS:
        fid, created = find_or_make(drive, name, args.folder, args.drive, SHEET)
        if created:
            if "notes" in name:
                stage_sheet_notes(sheets, fid)
            else:
                stage_offset_header(sheets, fid)
        print(f"  {'created' if created else 'exists ':<8} {name:<32} {fid}")
        findings.setdefault("sheets", {})[name] = fid

    for name in SLIDE_SPECIMENS:
        fid, created = find_or_make(drive, name, args.folder, args.drive, DECK)
        if created:
            stage_deck(slides, fid)
        print(f"  {'created' if created else 'exists ':<8} {name:<32} {fid}")
        findings.setdefault("slides", {})[name] = fid

    # WHERE the self-documentation goes, per type - and the first attempt got this wrong in a
    # way worth recording. A file-level COMMENT was used for both, which broke
    # `sheets-notes-are-not-comments`: a specimen whose entire lesson is "this file returns
    # ZERO comments" returned one, because the documentation was itself a comment. The
    # documentation has to live somewhere that does not participate in what is being
    # demonstrated.
    #
    # So: a SHEET gets a `README` tab (a grid can hold prose in cells, and a tab keeps it out
    # of the data), and a DECK gets a file-level comment (a comment count is not what the
    # deck specimen demonstrates - its anchors are - and a comment is visible in the editor).
    for name in SHEET_SPECIMENS:
        fid = findings["sheets"][name]
        titles = [sh["properties"]["title"] for sh in sheets.spreadsheets().get(
            spreadsheetId=fid, fields="sheets(properties(title))").execute()["sheets"]]
        if "README" in titles:
            continue
        sheets.spreadsheets().batchUpdate(spreadsheetId=fid, body={"requests": [
            # LAST, not first. A README tab at index 0 silently changes what an UNQUALIFIED
        # A1 range reads - measured while building this, when the verifier started
        # reading the documentation instead of the data. A documentation tab must not
        # alter the file's default behaviour.
        {"addSheet": {"properties": {"title": "README", "index": 99}}}]}).execute()
        spec = SHEET_SPECIMENS[name]
        text = body(spec["title"], spec["what"], spec["why"], spec["look"], spec["by_hand"],
                    spec["material"], date=TODAY, axis="sheets")
        sheets.spreadsheets().values().update(
            spreadsheetId=fid, range="README!A1", valueInputOption="RAW",
            body={"values": [[line] for line in text.split("\n")]}).execute()
        print(f"  documented {name} in a README TAB (not a comment - see the note above)")
        # And remove any documentation comment a previous run left, which is what made the
        # notes specimen contradict itself.
        for c in drive.comments().list(fileId=fid, fields="comments(id,content)",
                                       pageSize=50).execute().get("comments", []):
            if c.get("content", "").startswith("SPECIMEN"):
                drive.comments().delete(fileId=fid, commentId=c["id"]).execute()
                print("    removed a documentation comment that broke the specimen")

    for name in SLIDE_SPECIMENS:
        fid = findings["slides"][name]
        existing = drive.comments().list(fileId=fid, fields="comments(id)",
                                         pageSize=1).execute().get("comments", [])
        if existing:
            continue
        spec = SLIDE_SPECIMENS[name]
        text = body(spec["title"], spec["what"], spec["why"], spec["look"], spec["by_hand"],
                    spec["material"], date=TODAY, axis="slides", placed=spec.get("placed"))
        document_deck(slides, drive, fid, text)
        print(f"  documented {name} on a README SLIDE (see the note in document_deck)")

    out = os.path.join(os.path.dirname(__file__), "manifest_more.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(findings, fh, indent=2)
        fh.write("\n")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
