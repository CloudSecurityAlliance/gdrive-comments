"""Every refusal names the row, the value, and what to do instead.

A 205-row register is not something you scan. "resolve_comment is 'maybe later'" is a good
message and still leaves somebody searching a spreadsheet for the cell that says it — so every
outcome carries the **spreadsheet row number**, which is what a person actually navigates by.

Two messages were weak and are the ones this file mostly exists for:

**"no comment 't99' on this file"** said what was wrong and nothing about what to do. It is also
the most likely real error — a register exported from a different document, or one whose ids got
mangled by a sort — so it now says so. And when *most* rows fail that way, the report says it
once at the top, because 205 identical row-level messages bury the single fact that matters:
this is the wrong file.

**The reply-row refusal** told somebody actions belong on the thread's row without naming which
row that is. It now names the thread.
"""
from __future__ import annotations

import asyncio
import csv

from csa_google_workspace import Workspace
from csa_google_workspace._export import COLUMNS
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

DOC = "d1"


def build():
    cs = {DOC: [{"id": "t1", "content": "P", "author": {"displayName": "A"},
                 "createdTime": "2026-08-20T10:00:00Z", "resolved": False,
                 "replies": [{"id": "r1", "content": "x", "author": {"displayName": "B"}}]}]}
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "Draft", "mimeType": "application/vnd.google-apps.document"}},
        documents={DOC: {"body": {"content": []}}}, comments=cs)
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                            "CSA_GW_PROFILE": "full"})
    return create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st)


def run(tmp_path, rows, apply=True):
    path = tmp_path / "x.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS)); w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    return asyncio.run(build().call_tool(
        "apply_comment_actions",
        {"fileId": DOC, "path": str(path), "apply": apply})).structured_content


class TestEveryOutcomeNamesItsRow:
    def test_the_row_number_matches_the_spreadsheet(self, tmp_path):
        """Header is row 1, so the first data row is 2 - what the spreadsheet shows in the
        margin, not a zero-based index somebody has to translate."""
        out = run(tmp_path, [{"thread_id": "t1"}, {"thread_id": "t1"}])
        assert [r["row"] for r in out["rows"]] == [2, 3]

    def test_a_failure_names_its_row(self, tmp_path):
        out = run(tmp_path, [{"thread_id": "t1"},
                             {"thread_id": "t1", "resolve_comment": "maybe later"}])
        bad = next(r for r in out["rows"] if r["failed"])
        assert bad["row"] == 3


class TestTheNotFoundMessageSaysWhatToDo:
    def test_it_suggests_the_likely_cause(self, tmp_path):
        out = run(tmp_path, [{"thread_id": "t99", "reply_comment": "hi"}])
        detail = out["rows"][0]["detail"].lower()
        assert "t99" in out["rows"][0]["detail"]
        assert "different document" in detail or "another document" in detail

    def test_a_register_from_the_wrong_file_is_called_out_once_at_the_top(self, tmp_path):
        """205 identical row messages bury the one fact that matters."""
        out = run(tmp_path, [{"thread_id": f"x{i}", "reply_comment": "hi"} for i in range(5)])
        assert out["failed"] == 5
        assert "different document" in out["detail"].lower()

    def test_a_single_bad_row_is_NOT_called_out_as_a_wrong_file(self, tmp_path):
        """One mangled id among many good rows is a typo, not the wrong register - saying
        otherwise would send somebody looking for a problem they do not have."""
        rows = [{"thread_id": "t1", "resolve_comment": "TRUE"},
                {"thread_id": "t1"}, {"thread_id": "t1"}, {"thread_id": "t1"},
                {"thread_id": "nope", "reply_comment": "hi"}]
        out = run(tmp_path, rows)
        assert out["failed"] == 1
        assert "different document" not in out["detail"].lower()


class TestTheReplyRowMessageNamesTheThread:
    def test_it_says_which_row_to_move_the_action_to(self, tmp_path):
        out = run(tmp_path, [{"thread_id": "r1", "reply_to": "t1", "reply_comment": "hi"}])
        assert "t1" in out["rows"][0]["detail"]


class TestTheMessagesStillNameTheValueAndTheOptions:
    def test_resolve(self, tmp_path):
        detail = run(tmp_path, [{"thread_id": "t1", "resolve_comment": "Y3S"}])["rows"][0]["detail"]
        for expected in ("Y3S", "TRUE", "FALSE", "NO_CHANGE"):
            assert expected in detail

    def test_delete(self, tmp_path):
        detail = run(tmp_path, [{"thread_id": "t1", "delete_comment": "sure"}])["rows"][0]["detail"]
        assert "sure" in detail and "TRUE" in detail and "NO_CHANGE" in detail

    def test_delete_false_explains_there_is_no_undelete(self, tmp_path):
        detail = run(tmp_path, [{"thread_id": "t1", "delete_comment": "FALSE"}])["rows"][0]["detail"]
        assert "undo" in detail.lower() and "NO_CHANGE" in detail

    def test_nothing_was_changed_is_stated(self, tmp_path):
        """A refusal has to be unambiguous about whether it happened. "invalid value" leaves
        somebody wondering whether half the row went through."""
        detail = run(tmp_path, [{"thread_id": "t1", "resolve_comment": "Y3S"}])["rows"][0]["detail"]
        assert "nothing" in detail.lower() or "not changed" in detail.lower()
