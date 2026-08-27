"""Deleting a reply deletes the reply — not the thread it sits in.

A row carrying an action on a **reply** was refused wholesale, and the refusal said:

    move the action to the row whose thread_id is <parent>

For `reply_comment` and `resolve_comment` that advice is right: Drive has no reply-to-a-reply,
and resolving acts on a thread. For **`delete_comment` it was destructive.** Deleting the parent
deletes the *whole thread*, and Drive's delete strips content **and author** from every part of
it — so following the tool's own instruction destroyed other reviewers' text and attribution,
unrecoverably.

And it landed in the likeliest case rather than an exotic one. `delete_comment` exists to clear
spam, and spam on a shared document usually arrives **as a reply** to a real discussion. So the
advice was most likely to be read in exactly the situation where obeying it wrecked three other
people's work — with no warning, because from the user's side they did what they were told.

`Reply.delete()` already existed, so the capability was there the whole time and only the
register could not reach it. Fixed both ways: a reply row now honours `delete_comment` on the
reply itself, and the refusal for the other two columns says plainly that moving a *delete* to
the parent is not a substitute.

What stays refused, and why:

    reply_comment    on a reply row   Drive has no reply-to-a-reply. Genuinely impossible
    resolve_comment  on a reply row   resolve acts on the thread, not one reply
    delete_comment = FALSE            there is no undelete, same as for a comment
"""
from __future__ import annotations

import asyncio
import csv

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

DOC = "d1"


def build():
    """One thread, three replies. Two are legitimate discussion; `r_spam` is the spam."""
    cs = {DOC: [{
        "id": "t1", "content": "Does section 3 cover key rotation?",
        "author": {"displayName": "Reviewer A"}, "createdTime": "2026-08-20T10:00:00Z",
        "resolved": False,
        "replies": [
            {"id": "r_alice", "content": "Partly - see 3.2", "author": {"displayName": "Alice"},
             "createdTime": "2026-08-20T11:00:00Z"},
            {"id": "r_spam", "content": "BUY CHEAP WATCHES", "author": {"displayName": "Spam"},
             "createdTime": "2026-08-20T12:00:00Z"},
            {"id": "r_bob", "content": "Agree with Alice", "author": {"displayName": "Bob"},
             "createdTime": "2026-08-20T13:00:00Z"},
        ]}]}
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "Draft", "mimeType": "application/vnd.google-apps.document"}},
        documents={DOC: {"body": {"content": []}}}, comments=cs)
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                            "CSA_GW_PROFILE": "full"})
    return create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st), backend


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, {"fileId": DOC, **args})).structured_content


def register(app, tmp_path, *, on_thread_id, column, value):
    """Export, set one cell on one row, hand it back."""
    out = call(app, "export_comments", destination="file", path=str(tmp_path / "r.csv"))
    path = out["written_path"]
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for row in rows:
        if row["thread_id"] == on_thread_id:
            row[column] = value
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    return path


def replies_of(backend, thread="t1"):
    return backend._comments[(DOC, thread)].get("replies", [])


class TestTheSpamGoesAndTheDiscussionStays:
    def test_a_reply_row_delete_removes_that_reply(self, tmp_path):
        app, backend = build()
        path = register(app, tmp_path, on_thread_id="r_spam",
                        column="delete_comment", value="TRUE")
        out = call(app, "apply_comment_actions", path=path, apply=True)
        assert out["deleted"] == 1, f"the reply was not deleted: {out['rows']}"
        gone = [r for r in replies_of(backend) if r["id"] == "r_spam"]
        assert gone and gone[0].get("deleted") is True

    def test_the_other_replies_and_the_thread_survive(self, tmp_path):
        """The whole point. Deleting the parent would have taken all three."""
        app, backend = build()
        path = register(app, tmp_path, on_thread_id="r_spam",
                        column="delete_comment", value="TRUE")
        call(app, "apply_comment_actions", path=path, apply=True)
        survivors = {r["id"]: r for r in replies_of(backend) if not r.get("deleted")}
        assert set(survivors) == {"r_alice", "r_bob"}
        assert survivors["r_alice"]["content"] == "Partly - see 3.2", "Alice's text was lost"
        assert survivors["r_alice"]["author"]["displayName"] == "Alice", "attribution was lost"
        assert backend._comments[(DOC, "t1")].get("deleted") is not True, "the thread was deleted"

    def test_a_dry_run_deletes_nothing_and_says_so_in_would_delete(self, tmp_path):
        """`deleted` is 0 on a dry run and `would_delete` carries the count - a deliberate
        split, so a dry-run response can never be misread as having acted."""
        app, backend = build()
        path = register(app, tmp_path, on_thread_id="r_spam",
                        column="delete_comment", value="TRUE")
        out = call(app, "apply_comment_actions", path=path)
        assert out["would_delete"] == 1, f"the dry run did not report the delete: {out['rows']}"
        assert out["deleted"] == 0, "a dry run must not report a delete as done"
        assert not any(r.get("deleted") for r in replies_of(backend))

    def test_re_running_is_safe(self, tmp_path):
        app, backend = build()
        path = register(app, tmp_path, on_thread_id="r_spam",
                        column="delete_comment", value="TRUE")
        call(app, "apply_comment_actions", path=path, apply=True)
        again = call(app, "apply_comment_actions", path=path, apply=True)
        assert again["failed"] == 0, f"a second run failed: {again['rows']}"
        assert len([r for r in replies_of(backend) if r.get("deleted")]) == 1


class TestTheRefusalNoLongerRecommendsDestroyingTheThread:
    def _refusal(self, tmp_path, column, value="hello"):
        app, _ = build()
        path = register(app, tmp_path, on_thread_id="r_spam", column=column, value=value)
        out = call(app, "apply_comment_actions", path=path)
        detail = " ".join(r["detail"] for r in out["rows"])
        assert out["failed"] == 1, f"expected a refusal, got {out['rows']}"
        return detail

    def test_reply_on_a_reply_row_is_still_refused(self, tmp_path):
        assert "reply" in self._refusal(tmp_path, "reply_comment").lower()

    def test_resolve_on_a_reply_row_is_still_refused(self, tmp_path):
        assert self._refusal(tmp_path, "resolve_comment", "TRUE")

    def test_it_does_not_tell_you_to_move_a_delete_to_the_parent(self, tmp_path):
        """The destructive sentence. It must not read as advice for a delete."""
        detail = self._refusal(tmp_path, "reply_comment").lower()
        assert "delete" in detail, (
            "the refusal should say what to do about delete, since delete DOES work here")
        assert "entire thread" in detail or "whole thread" in detail, (
            "the refusal must warn that deleting the parent destroys the whole thread")

    def test_delete_false_on_a_reply_row_is_refused(self, tmp_path):
        """No undelete for a reply either — consistent with a comment."""
        app, _ = build()
        path = register(app, tmp_path, on_thread_id="r_spam",
                        column="delete_comment", value="FALSE")
        out = call(app, "apply_comment_actions", path=path)
        assert out["failed"] == 1, f"a FALSE delete on a reply was not refused: {out['rows']}"


class TestAReplyRowWithNothingSetIsStillANoOp:
    def test_untouched_reply_rows_do_nothing(self, tmp_path):
        app, backend = build()
        out = call(app, "export_comments", destination="file", path=str(tmp_path / "r.csv"))
        applied = call(app, "apply_comment_actions", path=out["written_path"], apply=True)
        assert (applied["deleted"], applied["failed"]) == (0, 0)
        assert not any(r.get("deleted") for r in replies_of(backend))


class TestTheToolDescriptionSaysDeleteWorksOnAReply:
    @pytest.fixture
    def description(self):
        app, _ = build()
        tools = {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}
        return tools["apply_comment_actions"]

    def test_it_says_a_reply_can_be_deleted_on_its_own_row(self, description):
        assert "reply" in description.lower() and "delete" in description.lower()
