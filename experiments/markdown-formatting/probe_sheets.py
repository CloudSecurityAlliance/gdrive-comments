"""Can a spreadsheet cell carry formatting through the values API? (No.)

Writes Markdown-looking text through `values.update`, reads the raw `CellData` to show nothing
converted, then applies real per-character-range formatting via `batchUpdate` + `textFormatRuns`
to show where formatting actually lives. Trashes the file in a `finally`.

See RESULTS.md.
"""
from googleapiclient.discovery import build

from csa_google_workspace import Workspace, auth

creds = auth.load_cached_credentials("~/.csa_google_workspace/token.json", read_only=False)
ws = Workspace.from_credentials(creds)
sheets = build("sheets", "v4", credentials=creds).spreadsheets()
ref = ws.files.create("PROBE md in cells (safe to delete)", "spreadsheet")
fid = ref.id; sh = ws.open(fid)
print("created:", fid)
try:
    # 1. write markdown-looking text through the values API
    sh.update("A1:A3", [["**bold?**"], ["# Heading?"], ["- bullet?"]])
    print("values written")
    got = sh.values("A1:A3")
    print("read back  :", got)

    # 2. what does the CELL actually hold - is any of it formatting?
    grid = sheets.get(spreadsheetId=fid, ranges=["A1:A3"], includeGridData=True).execute()
    rows = grid["sheets"][0]["data"][0].get("rowData", [])
    for i, row in enumerate(rows, start=1):
        cell = (row.get("values") or [{}])[0]
        ue = cell.get("userEnteredValue", {})
        runs = cell.get("textFormatRuns")
        fmt = (cell.get("userEnteredFormat") or {}).get("textFormat", {})
        print(f"  A{i}: value={ue!r} textFormatRuns={runs!r} bold={fmt.get('bold')}")

    # 3. can batchUpdate apply real per-run formatting inside one cell?
    sheets.batchUpdate(spreadsheetId=fid, body={"requests": [{
        "updateCells": {
            "range": {"sheetId": 0, "startRowIndex": 4, "endRowIndex": 5,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "rows": [{"values": [{
                "userEnteredValue": {"stringValue": "plain bold plain"},
                "textFormatRuns": [{"startIndex": 0},
                                   {"startIndex": 6, "format": {"bold": True}},
                                   {"startIndex": 10}]}]}],
            "fields": "userEnteredValue,textFormatRuns"}}]}).execute()
    grid2 = sheets.get(spreadsheetId=fid, ranges=["A5"], includeGridData=True).execute()
    c = grid2["sheets"][0]["data"][0]["rowData"][0]["values"][0]
    print()
    print("  A5 per-run formatting applied:", c.get("textFormatRuns"))
    print("  A5 value via values API      :", sh.values("A5"))
finally:
    ws.files.trash(fid); print("\ntrashed:", fid)
