"""The register says WHICH TAB, now that the export can be asked (#290).

Before this, a multi-tab spreadsheet register had no tab column: the cell mapping knew `B4`
and nothing about which sheet, so `export_comments` filled `cell_text_by_tab` — what that cell
holds on *every* tab — and let a human infer the rest from the content.

That fallback is still here and still correct, because the tab is only recoverable when the
XLSX relationship graph can be walked. What changes is that it is now the **exception** rather
than the rule, and the caveat narrows to the rows that actually need it instead of tarring the
whole file.
"""
from __future__ import annotations

import asyncio

from test_cellmap_tabs import build as build_xlsx

from csa_google_workspace import Workspace
from csa_google_workspace._export import COLUMNS
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

SHEET = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
WHEN = "2026-08-20T10:00:00"


def app_for(*, tabs, values, xlsx, comments):
    backend = FakeBackend(
        {SHEET: {"id": SHEET, "name": "A Book", "mimeType": SHEET_MIME}},
        spreadsheets={SHEET: {"sheets": [{"properties": {"title": t, "sheetId": i}}
                                         for i, t in enumerate(tabs)]}},
        values=values, exports={(SHEET, XLSX_MIME): xlsx}, comments={SHEET: comments})
    return create_server(lambda: Workspace(backend),
                         settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))


def rows_for(app):
    out = asyncio.run(app.call_tool("export_comments", {"fileId": SHEET})).structured_content
    return out["rows"], out["caveats"]


def drive_comment(cid, text):
    return {"id": cid, "content": text, "author": {"displayName": "Kurt"},
            "createdTime": WHEN + "Z", "replies": []}


class TestTheColumnExists:
    def test_tab_is_a_reported_column(self):
        assert "tab" in COLUMNS

    def test_it_sits_beside_the_cell_it_qualifies(self):
        """`tab`, `cell`, `cell_text` read as one thought. A tab column at the far end of the
        row is a column nobody lines up with the cell it belongs to."""
        assert COLUMNS.index("tab") == COLUMNS.index("cell") - 1


class TestWhenTheTabIsKnown:
    def test_the_row_names_the_tab(self):
        """The whole point of #290, at the surface a user sees."""
        xlsx = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment2.xml": [("B4", WHEN, "t1", "check this")]})
        app = app_for(tabs=("Summary", "Detail"),
                      values={(SHEET, "Summary"): [[]], (SHEET, "Detail"): [
                          [], [], [], ["", "", "", "the real one"]]},
                      xlsx=xlsx, comments=[drive_comment("s1", "check this")])
        rows, _ = rows_for(app)
        assert rows[0]["tab"] == "Detail"

    def test_cell_text_comes_from_that_tab_only(self):
        """Not `cell_text_by_tab`. Once the tab is known, listing every tab's candidate is
        noise that invites the reader to second-guess a settled answer."""
        xlsx = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment2.xml": [("A1", WHEN, "t1", "check this")]})
        app = app_for(tabs=("Summary", "Detail"),
                      values={(SHEET, "Summary"): [["WRONG"]], (SHEET, "Detail"): [["RIGHT"]]},
                      xlsx=xlsx, comments=[drive_comment("s1", "check this")])
        rows, _ = rows_for(app)
        assert rows[0]["cell_text"] == "RIGHT"
        assert rows[0]["cell_text_by_tab"] is None

    def test_no_caveat_when_every_comment_is_placed(self):
        """A multi-tab workbook is no longer inherently ambiguous, so the blanket warning has
        to go - otherwise it cries wolf on exactly the files this feature fixed."""
        xlsx = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A1", WHEN, "t1", "check this")]})
        app = app_for(tabs=("Summary", "Detail"),
                      values={(SHEET, "Summary"): [["x"]], (SHEET, "Detail"): [["y"]]},
                      xlsx=xlsx, comments=[drive_comment("s1", "check this")])
        _, caveats = rows_for(app)
        assert not any("could not be placed on a tab" in c for c in caveats)


class TestWhenTheTabIsNotKnown:
    """The graph could not be walked. The old behaviour, unchanged."""

    def test_the_tab_is_none_and_the_candidates_come_back(self):
        xlsx = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A1", WHEN, "t1", "check this")]},
            omit=("xl/workbook.xml",))
        app = app_for(tabs=("Summary", "Detail"),
                      values={(SHEET, "Summary"): [["Total"]], (SHEET, "Detail"): [["Lines"]]},
                      xlsx=xlsx, comments=[drive_comment("s1", "check this")])
        rows, caveats = rows_for(app)
        assert rows[0]["tab"] is None
        assert rows[0]["cell_text_by_tab"] == {"Summary": "Total", "Detail": "Lines"}
        assert any("could not be placed on a tab" in c for c in caveats)

    def test_the_caveat_counts_only_the_unplaced_rows(self):
        """"3 of 40 could not be placed" is actionable; "this file is ambiguous" is not, and
        is false about the 37."""
        xlsx = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A1", WHEN, "t1", "placed")]},
            omit=("xl/workbook.xml",))
        app = app_for(tabs=("Summary", "Detail"),
                      values={(SHEET, "Summary"): [["x"]], (SHEET, "Detail"): [["y"]]},
                      xlsx=xlsx, comments=[drive_comment("s1", "placed")])
        _, caveats = rows_for(app)
        tab_caveat = [c for c in caveats if "could not be placed on a tab" in c][0]
        assert "1 of 1" in tab_caveat

    def test_a_single_tab_workbook_still_needs_no_caveat(self):
        xlsx = build_xlsx([("Only", "rId5")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A1", WHEN, "t1", "x")]})
        app = app_for(tabs=("Only",), values={(SHEET, "Only"): [["v"]]},
                      xlsx=xlsx, comments=[drive_comment("s1", "x")])
        rows, caveats = rows_for(app)
        assert rows[0]["cell_text"] == "v"
        assert not any("could not be placed on a tab" in c for c in caveats)

    def test_an_unanchored_comment_is_not_counted_as_unplaced(self):
        """A file-level comment has no cell at all, so it has no tab to be missing. Counting it
        would report ambiguity about a comment that was never about a cell."""
        xlsx = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
            "xl/threadedComments/threadedComment1.xml": [("A1", WHEN, "t1", "anchored")]})
        app = app_for(tabs=("Summary", "Detail"),
                      values={(SHEET, "Summary"): [["x"]], (SHEET, "Detail"): [["y"]]},
                      xlsx=xlsx, comments=[drive_comment("s1", "anchored"),
                                           drive_comment("s2", "no anchor at all")])
        rows, caveats = rows_for(app)
        unanchored = [r for r in rows if r["thread_id"] == "s2"][0]
        assert unanchored["cell"] is None and unanchored["tab"] is None
        assert not any("could not be placed on a tab" in c for c in caveats)
