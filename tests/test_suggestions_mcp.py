"""Docs suggestions through MCP — gate B2, the last thing the library had and the server did not.

Two surfaces, and they answer different questions:

    list_suggestions(fileId)                    what has been suggested, as objects
    read_file_content(fileId, suggestions=...)   what the document WOULD say

The second is the one that gets used in practice. "Show me the document as if every suggestion
were accepted" is the review question, and answering it by listing edits and asking a model to
apply them in its head is how you get a confident wrong answer. Google renders it server-side;
all we have to do is not hide the parameter.

The thing both surfaces must communicate, loudly and repeatedly, is that **accept and reject do
not exist**. The Docs API has no endpoint for either (proven by full API enumeration, see
research/docs-suggestions-reference.md). A model that has just listed six suggestions will try to
accept them, and the only thing standing between it and a confident lie to the user is the wording
of these descriptions. So there is a test for the wording.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

DOC = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
SHEET = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"


def _run(text: str, **ids) -> dict:
    return {"textRun": {"content": text, **ids}}


def _para(*runs) -> dict:
    return {"paragraph": {"elements": list(runs)}}


# One document, four renderings — which is exactly what the Docs API gives you for a file with
# suggestions in it, and why the `suggestions` parameter is a view selector rather than a filter.
PLAIN = {"body": {"content": [_para(_run("Default view.\n"))]}}
INLINE = {"body": {"content": [
    _para(_run("The "), _run("very ", suggestedInsertionIds=["sug1"]),
          _run("quick "), _run("brown ", suggestedDeletionIds=["sug2"]),
          _run("fox.\n"))]}}
ACCEPTED = {"body": {"content": [_para(_run("The very quick fox.\n"))]}}
REJECTED = {"body": {"content": [_para(_run("The quick brown fox.\n"))]}}


@pytest.fixture
def server():
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Doc", "mimeType": "application/vnd.google-apps.document"},
         SHEET: {"id": SHEET, "name": "A Sheet",
                 "mimeType": "application/vnd.google-apps.spreadsheet"}},
        documents={(DOC, None): PLAIN,
                   (DOC, "SUGGESTIONS_INLINE"): INLINE,
                   (DOC, "PREVIEW_SUGGESTIONS_ACCEPTED"): ACCEPTED,
                   (DOC, "PREVIEW_WITHOUT_SUGGESTIONS"): REJECTED},
        spreadsheets={SHEET: {"sheets": [{"properties": {"title": "Tab1", "sheetId": 0}}]}},
        values={(SHEET, "Tab1"): [["a", "b"]]})
    return create_server(lambda: Workspace(backend), settings=settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*"}))


def call(server, name, args):
    return asyncio.run(server.call_tool(name, args))


class TestListSuggestions:
    def test_it_returns_each_suggestion_with_its_id_kind_and_text(self, server):
        out = call(server, "list_suggestions", {"fileId": DOC}).structured_content
        found = {(s["suggestion_id"], s["kind"], s["text"]) for s in out["suggestions"]}
        assert found == {("sug1", "insertion", "very "), ("sug2", "deletion", "brown ")}

    def test_it_says_accept_and_reject_are_impossible(self, server):
        """In the RESULT, not only the description.

        A model reads the description once, when it decides which tool to call, and then reads
        the result. By the time it is composing "shall I accept these?", the description is
        several thousand tokens behind it and the result is in front of it."""
        out = call(server, "list_suggestions", {"fileId": DOC}).structured_content
        assert out["can_accept_or_reject"] is False
        assert "no" in out["detail"].lower() and "api" in out["detail"].lower()

    def test_a_document_with_no_suggestions_is_an_empty_list_not_an_error(self, server):
        """And the detail still explains the state, because "none" and "cannot tell" differ."""
        backend = FakeBackend(
            {DOC: {"id": DOC, "name": "Clean",
                   "mimeType": "application/vnd.google-apps.document"}},
            documents={(DOC, "SUGGESTIONS_INLINE"): PLAIN})
        clean = create_server(lambda: Workspace(backend),
                             settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))
        out = call(clean, "list_suggestions", {"fileId": DOC}).structured_content
        assert out["suggestions"] == []
        assert out["detail"]

    def test_a_spreadsheet_is_refused_by_naming_the_type(self, server):
        """Suggestions are a Docs feature. The refusal has to say which file this is, or the
        model tries the same call again on the same id."""
        with pytest.raises(Exception, match="spreadsheet"):
            call(server, "list_suggestions", {"fileId": SHEET})

    def test_no_suggestion_author_is_promised(self, server):
        """The Docs API does not expose one. A schema field for it would be permanently null,
        and a permanently-null field invites somebody to attribute an edit to nobody."""
        out = call(server, "list_suggestions", {"fileId": DOC}).structured_content
        assert all("author" not in s for s in out["suggestions"])


class TestReadFileContentPreview:
    def test_accepted_renders_the_document_as_if_every_suggestion_were_taken(self, server):
        out = call(server, "read_file_content",
                   {"fileId": DOC, "suggestions": "accepted"}).structured_content
        assert out["text"].strip() == "The very quick fox."

    def test_rejected_renders_it_as_if_none_were(self, server):
        out = call(server, "read_file_content",
                   {"fileId": DOC, "suggestions": "rejected"}).structured_content
        assert out["text"].strip() == "The quick brown fox."

    def test_inline_keeps_the_suggested_text_in_place(self, server):
        out = call(server, "read_file_content",
                   {"fileId": DOC, "suggestions": "inline"}).structured_content
        assert "very" in out["text"] and "brown" in out["text"]

    def test_omitting_it_is_unchanged_behaviour(self, server):
        """The parameter is additive: existing callers must read exactly what they read before."""
        before = call(server, "read_file_content", {"fileId": DOC}).structured_content
        assert before["text"].strip() == "Default view."

    def test_an_unknown_view_lists_the_legal_ones(self, server):
        """The model cannot guess 'accepted' from nothing, so the error has to teach it."""
        with pytest.raises(Exception) as raised:
            call(server, "read_file_content", {"fileId": DOC, "suggestions": "maybe"})
        message = str(raised.value)
        assert "accepted" in message and "rejected" in message and "inline" in message

    def test_tab_and_suggestions_together_are_refused(self, server):
        """One is Sheets-only, the other Docs-only, so together they are always a mistake -
        and silently ignoring one of them would answer a question nobody asked."""
        with pytest.raises(Exception, match="together"):
            call(server, "read_file_content",
                 {"fileId": DOC, "suggestions": "accepted", "tab": "Tab1"})

    def test_suggestions_on_a_spreadsheet_names_the_type(self, server):
        with pytest.raises(Exception, match="spreadsheet|document"):
            call(server, "read_file_content", {"fileId": SHEET, "suggestions": "accepted"})


class TestTheDescriptionsCarryTheOneFactModelsGetWrong:
    """Accept/reject being impossible is not a detail; it is the whole shape of the feature.

    This is a wording test, which is unusual and deliberate. The failure mode it guards is a
    model telling a user "I've accepted your suggestions" after calling a tool that cannot -
    and the only control on that path is what these descriptions say."""

    def _tool(self, server, name):
        return next(t for t in asyncio.run(server.list_tools()) if t.name == name)

    def test_list_suggestions_says_so(self, server):
        text = self._tool(server, "list_suggestions").description.lower()
        assert "cannot" in text or "no way" in text or "not possible" in text
        assert "accept" in text

    def test_read_file_content_explains_what_the_preview_is_for(self, server):
        text = self._tool(server, "read_file_content").description.lower()
        assert "suggestions" in text
        assert "accepted" in text and "rejected" in text
