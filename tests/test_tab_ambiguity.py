"""D3: a multi-tab spreadsheet makes `comments_by_cell` ambiguous. Say so.

`Location.tab` has always been `None` - nothing sets it. That is the same defect class as
`update_file`'s hard-coded `parents: []`, but with a worse consequence, because here the
*answer* can be wrong rather than merely absent:

`_cellmap.parse_xlsx_comments` walks every `xl/threadedComments/*.xml` member in the export -
one per sheet - and collects them into a flat list with **no record of which sheet each came
from**. So on a workbook with three tabs, a comment anchored at B11 on *Sheet3* is
indistinguishable from one at B11 on *Sheet1*, and `comments_by_cell("B11")` returns both as
though the question had one answer.

TODO.md offered two resolutions: implement tab resolution (`workbook.xml` + rels), or state the
limitation explicitly, on the grounds that *a silently-wrong cell is worse than an absent one*.
This is the second, done properly - not a sentence in a docstring nobody reads, but a field in
the result that is true only when it matters, so a model narrating the answer has to account for
it.

The distinction worth preserving: on a SINGLE-tab workbook there is no ambiguity at all and the
answer is exact. Warning unconditionally would be the "check that fires on correct behaviour"
mistake, and the fix for that is never to mute it later.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

SHEET = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"


def server(*tabs: str):
    backend = FakeBackend(
        {SHEET: {"id": SHEET, "name": "A Sheet", "mimeType": SHEET_MIME}},
        spreadsheets={SHEET: {"sheets": [{"properties": {"title": t, "sheetId": i}}
                                         for i, t in enumerate(tabs)]}},
        comments={SHEET: []})
    return create_server(lambda: Workspace(backend), settings=settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*"}))


def call(app, cell="B11"):
    return asyncio.run(app.call_tool("comments_by_cell",
                                     {"fileId": SHEET, "cell": cell})).structured_content


class TestWhenItIsAmbiguous:
    def test_more_than_one_tab_is_reported_as_ambiguous(self):
        out = call(server("Sheet1", "Sheet2", "Sheet3"))
        assert out["tab_ambiguous"] is True

    def test_the_tabs_are_named_so_a_reader_knows_the_scope(self):
        """"Ambiguous" with no list is a warning somebody cannot act on."""
        out = call(server("Budget", "Notes"))
        assert out["tabs"] == ["Budget", "Notes"]

    def test_the_detail_says_what_the_ambiguity_IS(self):
        """Not "may be inaccurate" - which tab, and why it cannot be known."""
        out = call(server("Sheet1", "Sheet2"))
        detail = out["detail"].lower()
        assert "tab" in detail
        assert "which" in detail or "cannot" in detail


class TestWhenItIsNot:
    def test_a_single_tab_workbook_is_not_ambiguous(self):
        """There is exactly one place B11 can be, so the answer is exact. Warning here would
        be a check firing on correct behaviour."""
        out = call(server("Sheet1"))
        assert out["tab_ambiguous"] is False

    def test_a_single_tab_workbook_still_reports_its_tabs(self):
        out = call(server("Sheet1"))
        assert out["tabs"] == ["Sheet1"]

    def test_the_detail_does_not_manufacture_a_worry(self):
        """Checked by the warning's WORDS, not by the substring "ambiguous" - the first version
        of this test failed on the word "unambiguous", which is the code being right."""
        detail = call(server("Sheet1"))["detail"].lower()
        assert "different tab" not in detail
        assert "which tab" not in detail


class TestTheToolStillDoesItsJob:
    def test_the_comments_key_survives(self):
        """A caveat added beside the payload, not instead of it."""
        assert call(server("Sheet1"))["comments"] == []

    def test_the_description_states_the_limitation(self):
        """The result covers a model that reads results; the description covers one deciding
        whether to call it at all."""
        app = server("Sheet1")
        tool = next(t for t in asyncio.run(app.list_tools()) if t.name == "comments_by_cell")
        assert "tab" in tool.description.lower()


class TestTheLibraryModel:
    def test_location_tab_is_documented_as_unresolved(self):
        """It has never been populated. A field that can never be set is a promise the code
        does not keep, so the docstring has to say which it is."""
        from csa_google_workspace.comments import Location
        assert Location.__doc__ and "tab" in Location.__doc__.lower()

    @pytest.mark.parametrize("cell,row,col", [("B11", 11, 2), ("A1", 1, 1)])
    def test_a_location_still_carries_no_tab(self, cell, row, col):
        from csa_google_workspace._cellmap import location_from_ref
        location = location_from_ref(cell)
        assert (location.row, location.col) == (row, col)
        assert location.tab is None
