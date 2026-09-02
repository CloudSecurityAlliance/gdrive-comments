#!/usr/bin/env python3
"""Are Sheets NOTES reachable, and can a cell comment report its row/column headers?

#358 §5 and §6. Neither needs a human: notes are writable through the Sheets API, so this
creates the state it then reads.

**Why notes matter more than their size suggests.** A note is not a comment: no author, no
thread, and critically **not repliable and not resolvable**. A workflow built on reply-and-resolve
has no destination for one. #358's own words on the failure mode are the reason this is here:

> tell us notes exist even before they can be read. A silent zero is the expensive failure. We
> once had a `resolved` field parsed against the wrong vocabulary, which turned 17 closed threads
> into 0 while every test stayed green.

So the question is not only "can we read notes" but "can we *count* them cheaply enough to
mention them in `caveats` when we are not returning them".

§6 is the spreadsheet analogue of surrounding context. `cell_text` already answers *"B11, which
reads Q3 revenue"*; what is missing is *"in the row labelled Northeast, column Q3 actual"* — and
a comment on the wrong cell is only detectable against its neighbours.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from googleapiclient.discovery import build            # noqa: E402

from csa_google_workspace.auth import load_cached_credentials   # noqa: E402

TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")

GRID = [
    ["",          "Q3 actual", "Q3 plan", "Variance"],
    ["Northeast", "412000",    "400000",  "12000"],
    ["Southwest", "388000",    "410000",  "-22000"],
    ["Central",   "455000",    "450000",  "5000"],
]


def main() -> int:
    creds = load_cached_credentials(TOKEN, read_only=False)
    drive = build("drive", "v3", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)

    made = drive.files().create(
        body={"name": "PROBE notes and headers (throwaway)",
              "mimeType": "application/vnd.google-apps.spreadsheet"},
        fields="id,webViewLink").execute()
    file_id = made["id"]
    print(f"created: {made['webViewLink']}\n")

    sheets.spreadsheets().values().update(
        spreadsheetId=file_id, range="A1", valueInputOption="RAW",
        body={"values": GRID}).execute()

    # A NOTE on B3 (Southwest / Q3 actual) — the cell whose variance is bad, which is exactly
    # where a human would leave one. Written through the API to prove the write path exists.
    sheets.spreadsheets().batchUpdate(spreadsheetId=file_id, body={"requests": [
        {"updateCells": {
            "range": {"sheetId": 0, "startRowIndex": 2, "endRowIndex": 3,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rows": [{"values": [{"note": "NOTE: restated after the Q3 audit. Not a comment - "
                                          "no author, no thread, cannot be replied to."}]}],
            "fields": "note"}},
    ]}).execute()
    print("note written to B3 via the Sheets API (so the write path exists)\n")

    # ── §5: can we READ it, and how cheaply can we COUNT notes?
    got = sheets.spreadsheets().get(
        spreadsheetId=file_id,
        fields="sheets(properties(sheetId,title),data(rowData(values(note))))").execute()
    notes = []
    for sheet in got.get("sheets", []):
        title = sheet["properties"]["title"]
        for r, row in enumerate(sheet.get("data", [{}])[0].get("rowData", [])):
            for c, cell in enumerate(row.get("values", [])):
                if cell.get("note"):
                    notes.append((title, r, c, cell["note"]))
    print(f"§5 NOTES READABLE: {len(notes)} found")
    for title, r, c, text in notes:
        print(f"   {title}!{chr(65 + c)}{r + 1}  {text[:60]!r}")
    print("   the fields mask above is the whole cost - one `spreadsheets.get`, no grid values,\n"
          "   so COUNTING notes for a caveat is cheap even when not returning them.\n")

    # Does a note appear anywhere in the COMMENTS API? It must not - they are different objects.
    dc = drive.comments().list(fileId=file_id, fields="comments(id,content)").execute()
    print(f"§5 the Drive comments API sees {len(dc.get('comments', []))} comment(s) on this file "
          f"- a note is NOT a comment, confirmed rather than assumed\n")

    # ── §6: the headers that make a cell comment interpretable
    values = sheets.spreadsheets().values().get(
        spreadsheetId=file_id, range="A1:D4").execute().get("values", [])
    row_i, col_i = 2, 1                      # B3
    print("§6 HEADERS for a comment on B3:")
    print(f"   cell_text (already shipped) : {values[row_i][col_i]!r}")
    print(f"   column header (row 1)       : {values[0][col_i]!r}")
    print(f"   row header (column A)       : {values[row_i][0]!r}")
    print("   -> 'B3, which reads 388000, in the row labelled Southwest, column Q3 actual'")
    print("   Derived from the SAME grid `cell_text` already fetches: no extra call, and the\n"
          "   header row/column is a heuristic (row 1 / column A) that has to be stated as one.")

    print(f"\nthrowaway file id: {file_id}   (trash it when done)")
    print(json.dumps({"file_id": file_id, "notes_found": len(notes)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
