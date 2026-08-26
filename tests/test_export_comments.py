"""Bulk comment export — the shape you can hand to a spreadsheet or to another tool.

Two audiences, and neither of them is an AI, which is the point:

- **Somebody who would rather work in a spreadsheet.** A register of every open thread, with
  the text each one is about, is how review has always been done. This makes that better, not
  obsolete.
- **Another tool entirely.** Flat rows with a thread id feed anything - a notebook, a BI tool,
  `grep`. Nested JSON does not.

The missing data was never the comments; it was **what each comment is pointing at**. For a Doc
that is `quoted_text`, exposed in v0.23.0. For a Sheet it is the CELL'S CONTENT, and this is
that: a comment on B11 is meaningless in a register unless the register also says B11 holds
"Q3 revenue".

Which produces an unexpected answer to the multi-tab problem (D3). We cannot know which tab a
comment is on - the export carries no correlation from a `threadedComments` member back to a
sheet name. But we can report B11 **on every tab**, and the content then tells a human which it
was: if B11 is empty on Sheet1 and says "Q3 revenue" on Sheet2, the comment is about Sheet2.
That resolves the ambiguity in practice without the code guessing, which is better than either
guessing or refusing.
"""
from __future__ import annotations

import asyncio
import io
import zipfile

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

DOC = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
SHEET = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"
DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"


NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"


def _xlsx(ref: str, text: str, author: str = "Reviewer",
          when: str = "2026-08-20T10:00:00") -> bytes:
    """A minimal XLSX carrying one threaded comment.

    Needed because a Sheets comment's CELL is not in the Drive API at all - the anchor is an
    opaque range id, and recovering A1 means exporting the workbook and parsing it. So a test
    that wants `cell` populated has to provide the export, exactly as reality does. The first
    version of this file assumed otherwise and asserted `cell == "A1"` against a fake with no
    export; the assertion was wrong, not the code.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        # The persons member is required, not decoration: the cell map correlates a Drive
        # comment to an XLSX anchor by (author, text, timestamp-to-the-second), because there
        # is no shared id - and the author comes from resolving personId through here. Omitting
        # it makes the author None, the match fails, and `cell` comes back empty. That is what
        # the first version of this fixture did.
        z.writestr("xl/persons/person.xml",
                   f'<personList xmlns="{NS}"><person displayName="{author}" id="P1"/>'
                   f'</personList>')
        z.writestr("xl/threadedComments/threadedComment1.xml",
                   f'<ThreadedComments xmlns="{NS}"><threadedComment ref="{ref}" '
                   f'dT="{when}" personId="P1"><text>{text}</text></threadedComment>'
                   f'</ThreadedComments>')
    return buf.getvalue()


def build(*, sheet_tabs=("Sheet1",), values=None, comments=None, exports=None):
    files = {DOC: {"id": DOC, "name": "A Draft", "mimeType": DOC_MIME},
             SHEET: {"id": SHEET, "name": "A Book", "mimeType": SHEET_MIME}}
    backend = FakeBackend(
        files,
        documents={DOC: {"body": {"content": []}}},
        spreadsheets={SHEET: {"sheets": [{"properties": {"title": t, "sheetId": i}}
                                         for i, t in enumerate(sheet_tabs)]}},
        values=values or {},
        exports=exports or {},
        comments=comments or {})
    return create_server(lambda: Workspace(backend), settings=settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*"}))


def call(app, file_id):
    return asyncio.run(app.call_tool("export_comments", {"fileId": file_id})).structured_content


DOC_COMMENTS = {DOC: [
    {"id": "c1", "content": "Is this accurate?", "author": {"displayName": "Reviewer"},
     "quotedFileContent": {"value": "the shared responsibility model"},
     "createdTime": "2026-08-20T10:00:00Z",
     "replies": [{"id": "r1", "content": "Checking.", "author": {"displayName": "Kurt"},
                  "createdTime": "2026-08-20T11:00:00Z"}]},
]}


class TestTheShape:
    def test_it_reports_the_columns_in_order(self):
        """So writing a spreadsheet is a loop, not a judgement call about column order."""
        out = call(build(comments=DOC_COMMENTS), DOC)
        assert out["columns"][0] == "thread_id"
        assert "quoted_text" in out["columns"] and "author" in out["columns"]

    def test_every_row_has_every_column(self):
        out = call(build(comments=DOC_COMMENTS), DOC)
        for row in out["rows"]:
            assert set(row) == set(out["columns"])

    def test_a_reply_is_its_own_row_pointing_at_its_thread(self):
        """Flat, with a thread id - the lossless shape. One-row-per-thread is trivially
        derived from this; the reverse is not."""
        out = call(build(comments=DOC_COMMENTS), DOC)
        assert len(out["rows"]) == 2
        top = next(r for r in out["rows"] if not r["reply_to"])
        reply = next(r for r in out["rows"] if r["reply_to"])
        assert reply["reply_to"] == top["thread_id"]
        assert reply["text"] == "Checking."


class TestADocumentRegister:
    def test_the_passage_is_on_the_row(self):
        out = call(build(comments=DOC_COMMENTS), DOC)
        top = next(r for r in out["rows"] if not r["reply_to"])
        assert top["quoted_text"] == "the shared responsibility model"

    def test_a_reply_carries_no_passage_of_its_own(self):
        """Only the top-level comment anchors to text; a reply inherits its thread's."""
        out = call(build(comments=DOC_COMMENTS), DOC)
        reply = next(r for r in out["rows"] if r["reply_to"])
        assert reply["quoted_text"] is None


SHEET_COMMENTS = {SHEET: [
    {"id": "s1", "content": "Where is this from?", "author": {"displayName": "Reviewer"},
     "createdTime": "2026-08-20T10:00:00Z", "replies": []},
]}
# The comment's text and timestamp must match the export's, because that is how the cell map
# correlates a Drive comment to an XLSX anchor - there is no shared id.
SHEET_EXPORT = {(SHEET, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
                _xlsx("A1", "Where is this from?")}


class TestASpreadsheetRegister:
    """The new half: the cell's CONTENT, not just its address."""

    def test_a_single_tab_workbook_reports_the_cell_text(self):
        app = build(sheet_tabs=("Sheet1",),
                    values={(SHEET, "Sheet1"): [["Item", "Count"], ["Widgets", "7"]]},
                    exports=SHEET_EXPORT, comments=SHEET_COMMENTS)
        out = call(app, SHEET)
        row = out["rows"][0]
        # The API anchors every API-made comment at A1, so A1 is what is looked up.
        assert row["cell"] == "A1"
        assert row["cell_text"] == "Item"

    def test_a_multi_tab_workbook_reports_the_candidates_per_tab(self):
        """It cannot know WHICH tab - so it says what that cell holds on each, and the
        content tells a human which one the comment was about."""
        app = build(sheet_tabs=("Summary", "Detail"),
                    values={(SHEET, "Summary"): [["Total"]],
                            (SHEET, "Detail"): [["Line items"]]},
                    exports=SHEET_EXPORT, comments=SHEET_COMMENTS)
        out = call(app, SHEET)
        row = out["rows"][0]
        assert row["cell_text_by_tab"] == {"Summary": "Total", "Detail": "Line items"}

    def test_a_multi_tab_workbook_says_why_the_tab_is_absent(self):
        app = build(sheet_tabs=("Summary", "Detail"),
                    values={(SHEET, "Summary"): [["Total"]]}, comments=SHEET_COMMENTS)
        out = call(app, SHEET)
        assert any("tab" in c.lower() for c in out["caveats"])

    def test_a_single_tab_workbook_has_no_tab_caveat(self):
        """The answer is exact, so warning would be noise."""
        app = build(sheet_tabs=("Only",), values={(SHEET, "Only"): [["x"]]},
                    comments=SHEET_COMMENTS)
        out = call(app, SHEET)
        assert not any("tab" in c.lower() for c in out["caveats"])

    def test_an_empty_cell_is_reported_as_empty_not_missing(self):
        app = build(sheet_tabs=("Only",), values={(SHEET, "Only"): []},
                    exports=SHEET_EXPORT, comments=SHEET_COMMENTS)
        out = call(app, SHEET)
        assert out["rows"][0]["cell_text"] == ""


class TestItIsUsableInBulk:
    def test_no_comments_is_an_empty_row_set_with_the_columns_intact(self):
        """So a caller writing a spreadsheet still gets a header row."""
        out = call(build(comments={DOC: []}), DOC)
        assert out["rows"] == []
        assert out["columns"]

    def test_it_says_how_many_threads_and_rows(self):
        out = call(build(comments=DOC_COMMENTS), DOC)
        assert out["thread_count"] == 1
        assert out["row_count"] == 2

    def test_it_is_a_read_only_tool(self):
        app = build(comments=DOC_COMMENTS)
        tool = next(t for t in asyncio.run(app.list_tools()) if t.name == "export_comments")
        assert tool.annotations.read_only_hint is True
