"""Narrowing `comments_by_cell` to one tab — and refusing to answer about a tab that is not there.

**Why this refuses rather than returning an empty list.** The consumer is a language model, and
for a model the tool result *is* the world: it has no tab bar to glance at. An empty result for a
misspelled tab is a well-formed wrong answer that becomes a belief with no correction path, and
the realistic sequence is not merely a wrong sentence:

    comments_by_cell("B11", tab="Sheet1")  -> []          # real tabs are Budget / Notes
    "No unresolved comments on B11."                      # confident, false
    update_cells("Budget!B11", ...)                       # overwrites the commented cell

So the empty result acts as a silent PRECONDITION CHECK, and a typo becomes a data-loss
authorisation. Refusing costs one wasted call and self-corrects, because the error carries the
answer: `no tab named 'Sheet1'; present: ['Budget', 'Notes']`. `_errors` maps NotFoundError to
`ToolError("not found: ...")`, so that text reaches the model rather than being suppressed.

It is also the reversible direction: a refusal can be loosened later without breaking anybody,
while quiet-empty could not be tightened once models had learned it.

Matching is case-insensitive, following `add_tab` — Sheets itself treats tab names that way in
A1 references, so `budget` and `Budget` would collide at use anyway.
"""
from __future__ import annotations

import asyncio

import pytest
from test_cellmap_tabs import build as build_xlsx

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.exceptions import NotFoundError
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

SHEET = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
WHEN = "2026-08-20T10:00:00"

# One comment at B11 on Detail, one at B11 on Summary.
BOTH = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
    "xl/threadedComments/threadedComment1.xml": [("B11", WHEN, "t1", "on summary")],
    "xl/threadedComments/threadedComment2.xml": [("B11", WHEN, "t2", "on detail")]})
# Same, but the graph cannot be walked: cells known, sheets not.
NO_GRAPH = build_xlsx([("Summary", "rId5"), ("Detail", "rId6")], comments_by_part={
    "xl/threadedComments/threadedComment1.xml": [("B11", WHEN, "t1", "on summary")]},
    omit=("xl/workbook.xml",))


def drive(cid, text):
    return {"id": cid, "content": text, "author": {"displayName": "Kurt"},
            "createdTime": WHEN + "Z", "replies": []}


def backend(xlsx, comments, tabs=("Summary", "Detail")):
    return FakeBackend(
        {SHEET: {"id": SHEET, "name": "A Sheet", "mimeType": SHEET_MIME}},
        spreadsheets={SHEET: {"sheets": [{"properties": {"title": t, "sheetId": i}}
                                         for i, t in enumerate(tabs)]}},
        exports={(SHEET, XLSX_MIME): xlsx}, comments={SHEET: comments})


def sheet(xlsx, comments, tabs=("Summary", "Detail")):
    return Workspace(backend(xlsx, comments, tabs)).open(SHEET)


def tool(xlsx, comments, tabs=("Summary", "Detail")):
    app = create_server(lambda: Workspace(backend(xlsx, comments, tabs)),
                        settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))
    def call(**kw):
        return asyncio.run(app.call_tool(
            "comments_by_cell", {"fileId": SHEET, "cell": "B11", **kw})).structured_content
    return call


PAIR = [drive("s1", "on summary"), drive("s2", "on detail")]


class TestNarrowingToATab:
    def test_it_returns_only_that_tab(self):
        got = sheet(BOTH, PAIR).comments_by_cell("B11", "Detail")
        assert [c.content for c in got] == ["on detail"]

    def test_without_a_tab_it_returns_every_tab(self):
        """The pre-#290 behaviour, kept: the caller reads `tab` on each result."""
        got = sheet(BOTH, PAIR).comments_by_cell("B11")
        assert sorted(c.content for c in got) == ["on detail", "on summary"]

    def test_matching_is_case_insensitive(self):
        """Following add_tab: Sheets treats tab names case-insensitively in A1 references."""
        got = sheet(BOTH, PAIR).comments_by_cell("B11", "detail")
        assert [c.content for c in got] == ["on detail"]

    def test_surrounding_whitespace_is_tolerated(self):
        got = sheet(BOTH, PAIR).comments_by_cell("B11", "  Detail  ")
        assert [c.content for c in got] == ["on detail"]


class TestAnUnknownTabIsRefused:
    def test_it_raises_rather_than_returning_empty(self):
        with pytest.raises(NotFoundError):
            sheet(BOTH, PAIR).comments_by_cell("B11", "Sheet1")

    def test_the_refusal_names_the_tabs_that_exist(self):
        """The error IS the documentation: a model that guessed gets what to retry with, in the
        same turn. An error without the list is one it can only apologise about."""
        with pytest.raises(NotFoundError) as e:
            sheet(BOTH, PAIR).comments_by_cell("B11", "Sheet1")
        assert "Summary" in str(e.value) and "Detail" in str(e.value)
        assert "Sheet1" in str(e.value), "say which name was rejected"

    def test_the_message_survives_into_the_tool_error(self):
        """`_errors` maps NotFoundError to ToolError; a plain exception would become an
        UnexpectedToolError with the text SUPPRESSED, which would defeat the whole choice."""
        from mcp.server.mcpserver.exceptions import ToolError
        with pytest.raises(ToolError) as e:
            tool(BOTH, PAIR)(tab="Sheet1")
        assert "Summary" in str(e.value) and "Detail" in str(e.value)


class TestTheUnplacedCountSurvivesFiltering:
    """The bug this file was written to catch. Excluding a comment because its tab is unknown
    must not also erase the fact that it exists - otherwise narrowing by a PERFECTLY VALID tab
    reports a confident "nothing here" about a cell that has comments on it."""

    def test_an_unplaced_comment_is_counted_even_when_a_tab_is_named(self):
        out = tool(NO_GRAPH, [drive("s1", "on summary")])(tab="Summary")
        assert out["unplaced"] == 1, "excluded is not the same as nonexistent"
        assert out["tab_ambiguous"] is True

    def test_the_detail_does_not_claim_the_cell_is_clean(self):
        """The hazard is a *precondition* read: "no comments on B11" is what something checks
        before overwriting B11. So the text has to say the cell is not established as clear,
        not merely that a count was lower than expected."""
        detail = tool(NO_GRAPH, [drive("s1", "on summary")])(tab="Summary")["detail"]
        assert "could NOT be placed on a tab" in detail
        assert "not treat this cell as clear" in detail

    def test_the_results_are_still_excluded(self):
        """Reporting them under a tab we cannot confirm would be the opposite error."""
        out = tool(NO_GRAPH, [drive("s1", "on summary")])(tab="Summary")
        assert out["comments"] == []

    def test_a_placed_comment_on_another_tab_is_not_counted_as_unplaced(self):
        """Filtered out for being elsewhere is not the same as unplaceable."""
        out = tool(BOTH, PAIR)(tab="Detail")
        assert out["unplaced"] == 0 and out["tab_ambiguous"] is False
        assert len(out["comments"]) == 1
