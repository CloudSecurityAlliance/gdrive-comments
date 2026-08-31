"""D3, now that #290 has resolved it: ambiguity is a property of the ANSWER, not of the file.

**History, because this file used to assert the opposite.** `Location.tab` was declared and
never populated, so `comments_by_cell("B11")` on a three-tab workbook returned comments from
every tab as though the question had one answer. TODO.md offered two resolutions - implement tab
resolution, or state the limitation loudly - and the first version of this module was the
*second*: flag `tab_ambiguous` whenever a workbook had more than one tab, on the grounds that a
silently-wrong cell is worse than an absent one.

#290 did the first. `_cellmap` now walks the XLSX relationship graph (`workbook.xml` -> rels ->
each sheet's rels -> its `threadedComments` part) and populates the tab, so a multi-tab workbook
is no longer inherently ambiguous.

That makes the old contract actively wrong: flagging every multi-tab file would cry wolf on
exactly the files the fix made exact. So `tab_ambiguous` now means **"at least one comment in
this result could not be placed on a tab"**, which happens when the graph cannot be walked, and
`unplaced` counts them.

What carries over unchanged is the principle underneath, and it is the reason this file exists:
**a warning must fire only when there is something to warn about.** Muting one that fires on
correct behaviour is a worse fix than never having written it.
"""
from __future__ import annotations

import asyncio

import pytest
from test_cellmap_tabs import build as build_xlsx

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

SHEET = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
WHEN = "2026-08-20T10:00:00"


def server(*tabs: str, xlsx: bytes | None = None, comments=()):
    backend = FakeBackend(
        {SHEET: {"id": SHEET, "name": "A Sheet", "mimeType": SHEET_MIME}},
        spreadsheets={SHEET: {"sheets": [{"properties": {"title": t, "sheetId": i}}
                                         for i, t in enumerate(tabs)]}},
        exports={(SHEET, XLSX_MIME): xlsx} if xlsx else {},
        comments={SHEET: list(comments)})
    return create_server(lambda: Workspace(backend), settings=settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*"}))


def call(app, cell="B11", tab=None):
    args = {"fileId": SHEET, "cell": cell}
    if tab is not None:
        args["tab"] = tab
    return asyncio.run(app.call_tool("comments_by_cell", args)).structured_content


def drive_comment(cid, text):
    return {"id": cid, "content": text, "author": {"displayName": "Kurt"},
            "createdTime": WHEN + "Z", "replies": []}


PLACED = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
    "xl/threadedComments/threadedComment2.xml": [("B11", WHEN, "t1", "look here")]})
# Same workbook, but the graph cannot be walked - so the CELL is known and the SHEET is not.
UNPLACED = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
    "xl/threadedComments/threadedComment2.xml": [("B11", WHEN, "t1", "look here")]},
    omit=("xl/workbook.xml",))
ONE = [drive_comment("s1", "look here")]


class TestAMultiTabWorkbookIsNoLongerInherentlyAmbiguous:
    def test_a_placed_comment_is_not_flagged(self):
        """The regression this file now guards. Before #290 this was reported ambiguous purely
        because the workbook had two tabs, and the answer was in fact exact."""
        out = call(server("Summary", "Detail", xlsx=PLACED, comments=ONE))
        assert out["tab_ambiguous"] is False
        assert out["unplaced"] == 0

    def test_it_names_the_tab_it_found(self):
        out = call(server("Summary", "Detail", xlsx=PLACED, comments=ONE))
        assert [c["tab"] for c in out["comments"]] == ["Detail"]

    def test_the_detail_does_not_manufacture_a_worry(self):
        """Checked by the warning's WORDS, not by the substring "ambiguous" - an earlier version
        of this test failed on the word "unambiguous", which was the code being right."""
        detail = call(server("Summary", "Detail", xlsx=PLACED, comments=ONE))["detail"].lower()
        assert "could not be placed" not in detail


class TestWhenTheTabGenuinelyCannotBeKnown:
    def test_an_unplaced_comment_is_flagged(self):
        out = call(server("Summary", "Detail", xlsx=UNPLACED, comments=ONE))
        assert out["tab_ambiguous"] is True
        assert out["unplaced"] == 1

    def test_the_detail_says_what_the_shortfall_IS(self):
        """Not "may be inaccurate" - how many, and that the rest are exact."""
        detail = call(server("Summary", "Detail", xlsx=UNPLACED, comments=ONE))["detail"]
        assert "1 of 1" in detail or "could not be placed on a tab" in detail

    def test_the_tabs_are_named_so_a_reader_knows_the_scope(self):
        """"Ambiguous" with no list is a warning somebody cannot act on."""
        out = call(server("Budget", "Notes", xlsx=UNPLACED, comments=ONE))
        assert out["tabs"] == ["Budget", "Notes"]

    def test_the_comment_still_carries_its_cell(self):
        """The cell does not depend on the relationship graph, so losing the tab must not cost
        it. Reporting neither would throw away the more valuable half."""
        out = call(server("Summary", "Detail", xlsx=UNPLACED, comments=ONE))
        assert out["comments"][0]["cell"] == "B11"
        assert out["comments"][0]["tab"] is None


class TestNothingToReportIsNotAmbiguous:
    def test_no_comments_is_not_flagged(self):
        """An empty answer has nothing in it to be about the wrong tab. The old contract
        flagged this, because it keyed off the workbook rather than the result."""
        out = call(server("Sheet1", "Sheet2", "Sheet3"))
        assert out["tab_ambiguous"] is False and out["unplaced"] == 0

    def test_a_single_tab_workbook_is_not_ambiguous(self):
        out = call(server("Sheet1"))
        assert out["tab_ambiguous"] is False

    def test_a_single_tab_workbook_still_reports_its_tabs(self):
        out = call(server("Sheet1"))
        assert out["tabs"] == ["Sheet1"]


class TestTheToolStillDoesItsJob:
    def test_the_comments_key_survives(self):
        """A caveat added beside the payload, not instead of it."""
        assert call(server("Sheet1"))["comments"] == []

    def test_the_description_tells_a_model_it_can_narrow_by_tab(self):
        """The result covers a model reading results; the description covers one deciding how
        to call it. A `tab` parameter nothing mentions is a parameter nothing passes."""
        app = server("Sheet1")
        tool = next(t for t in asyncio.run(app.list_tools()) if t.name == "comments_by_cell")
        assert "tab" in tool.description.lower()
        assert "tab" in tool.input_schema["properties"]


class TestTheLibraryModel:
    def test_location_documents_what_an_absent_tab_means(self):
        """`tab=None` is load-bearing: it means "the sheet could not be resolved", never "the
        first sheet". A field whose absent value has a specific meaning has to say so."""
        from csa_google_workspace.comments import Location
        assert Location.__doc__ and "tab" in Location.__doc__.lower()

    @pytest.mark.parametrize("cell,row,col", [("B11", 11, 2), ("A1", 1, 1)])
    def test_a_location_built_without_a_tab_has_none(self, cell, row, col):
        """The default stays None so a caller that does not know the sheet cannot accidentally
        assert one."""
        from csa_google_workspace._cellmap import location_from_ref
        location = location_from_ref(cell)
        assert (location.row, location.col) == (row, col)
        assert location.tab is None
