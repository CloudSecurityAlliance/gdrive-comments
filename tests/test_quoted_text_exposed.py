"""The anchor text a comment is *about* — the most useful column, and the server withheld it.

Asked whether the tool could "export the comments to a spreadsheet with the text each one is
about", the answer turned out to be no, for a reason nobody had noticed: Drive returns
`quotedFileContent` (the passage a Docs comment is attached to), the library models it as
`Comment.quoted_text`, and **the MCP surface dropped it.** `CommentOut` carried id, author,
content, resolved, created_time, cell, linked_cell and replies - everything except *what the
comment is pointing at*.

So a model could list twenty comments on a draft and could not tell you which paragraph any of
them referred to. For comment triage - the single thing this project exists for - that is the
column somebody actually wants.

Same class as gate B2: a capability the library had and the server did not. Worth noting how it
stayed hidden. `quoted_text` *was* reachable, but only inside `_inline.py`, which uses it to
anchor comments into text for `read_file_content(includeComments=true)`. A field with one internal
consumer looks used, so nothing flagged it as absent from the schema.

With it exposed, "export the comments to a spreadsheet" needs no new tool at all: list_comments
plus create_file plus update_cells already compose to it. The missing piece was the data, not the
plumbing.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

DOC = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
DOC_MIME = "application/vnd.google-apps.document"
QUOTE = "the shared responsibility model"


@pytest.fixture
def server():
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Draft", "mimeType": DOC_MIME}},
        comments={DOC: [
            {"id": "c1", "content": "Is this still accurate?",
             "author": {"displayName": "A Reviewer"},
             "quotedFileContent": {"value": QUOTE, "mimeType": "text/html"},
             "replies": [{"id": "r1", "content": "Checking.",
                          "author": {"displayName": "Someone"}}]},
            # A comment on the FILE rather than on a passage. Drive returns no
            # quotedFileContent for these, and they are common - "looks good to me".
            {"id": "c2", "content": "Looks good overall.",
             "author": {"displayName": "Another"}, "replies": []},
        ]})
    return create_server(lambda: Workspace(backend), settings=settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*"}))


def call(app, name, args):
    return asyncio.run(app.call_tool(name, args)).structured_content


class TestListComments:
    def test_it_reports_the_passage_each_comment_is_about(self, server):
        found = {c["id"]: c for c in call(server, "list_comments", {"fileId": DOC})["comments"]}
        assert found["c1"]["quoted_text"] == QUOTE

    def test_a_file_level_comment_reports_none_not_an_empty_string(self, server):
        """`None` means "not attached to a passage"; `""` would mean "attached to nothing",
        which is not a state Drive has. The distinction decides whether a register's row is
        blank or says "whole document"."""
        found = {c["id"]: c for c in call(server, "list_comments", {"fileId": DOC})["comments"]}
        assert found["c2"]["quoted_text"] is None


class TestGetComment:
    def test_one_thread_reports_it_too(self, server):
        out = call(server, "get_comment", {"fileId": DOC, "commentId": "c1"})
        assert out["quoted_text"] == QUOTE


class TestEverythingNeededForARegister:
    """The concrete ask: a spreadsheet of the comments on a draft. No new tool - these are the
    columns, and they all have to come off one call."""

    def test_one_call_yields_every_column(self, server):
        comment = call(server, "list_comments", {"fileId": DOC})["comments"][0]
        for column in ("id", "author", "content", "quoted_text", "resolved", "created_time",
                       "replies"):
            assert column in comment, f"a comment register has no {column} column"

    def test_replies_are_nested_so_a_thread_stays_one_row(self, server):
        comment = next(c for c in call(server, "list_comments", {"fileId": DOC})["comments"]
                       if c["id"] == "c1")
        assert len(comment["replies"]) == 1
        assert comment["replies"][0]["content"] == "Checking."


class TestTheRedactionStillHolds:
    def test_a_repr_does_not_leak_the_quoted_passage(self):
        """`quoted_text` is document text, and these models get logged by embedders. Exposing
        it through the schema must not expose it through `repr`."""
        from csa_google_workspace.comments import Comment
        comment = Comment.from_api({"id": "c1", "content": "x",
                                    "quotedFileContent": {"value": "SECRET PASSAGE"}})
        assert "SECRET PASSAGE" not in repr(comment)
