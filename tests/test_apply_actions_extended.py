"""Unresolve, delete, and the three filters the library already had.

Four changes, and two of them are the CINO's corrections to my first design.

**`resolve_comment` is a genuine true/false.** I had false meaning "do nothing", which wastes
half the column: *"it makes sense that they might want to unresolve a comment."* So `true`
resolves, `false` REOPENS, and empty leaves it alone. Three states, three spellings, and the
one that means "I did not decide" is the blank one.

**`delete_comment`, for spam.** A review on a public-ish document collects junk, and removing it
one thread at a time is the same drudgery the register exists to end. It is also the sharpest
action here: Drive's soft delete strips the content *and the author*, permanently, and the
capability is off in every profile but `full`.

**`author` and `since` on the export**, which `CommentCollection.filter` has always supported
and the MCP layer simply never passed through — the fourth time this month a capability existed
in the library and not in the server. `includeResolved` already defaulted to True, so "all the
comments unless you say otherwise" was already the behaviour; this pins it.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

DOC = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
DOC_MIME = "application/vnd.google-apps.document"


def threads():
    return {DOC: [
        {"id": "t1", "content": "Open point", "author": {"displayName": "Alice"},
         "createdTime": "2026-08-20T10:00:00Z", "modifiedTime": "2026-08-20T10:00:00Z",
         "resolved": False, "replies": []},
        {"id": "t2", "content": "Settled point", "author": {"displayName": "Bob"},
         "createdTime": "2026-08-10T10:00:00Z", "modifiedTime": "2026-08-10T10:00:00Z",
         "resolved": True, "replies": []},
        {"id": "t3", "content": "BUY CHEAP WATCHES", "author": {"displayName": "Spam"},
         "createdTime": "2026-08-25T10:00:00Z", "modifiedTime": "2026-08-25T10:00:00Z",
         "resolved": False, "replies": []},
    ]}


def build(profile="full", cs=None):
    """A server whose backend is actually POLICY-WRAPPED.

    `create_server(lambda: Workspace(raw_backend))` does not apply the policy - the real
    `WorkspaceProvider` wraps it, and a test that skips that step exercises an ungated
    backend while appearing to test a profile. The first version of this file did exactly
    that, and `comment.delete` "succeeded" under `editor`; the harness was wrong, not the
    gate.
    """
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Draft", "mimeType": DOC_MIME}},
        documents={DOC: {"body": {"content": []}}}, comments=cs or threads())
    settings = settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
         "CSA_GW_PROFILE": profile})
    guarded = PolicyBackend(backend, settings.policy)
    app = create_server(lambda: Workspace(guarded), settings=settings)
    return app, backend


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, {"fileId": DOC, **args})).structured_content


def sheet(tmp_path, rows):
    import csv

    from csa_google_workspace._export import COLUMNS
    path = tmp_path / "actions.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS)); w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    return path


class TestResolveIsTrueFalseNotTrueBlank:
    def test_false_REOPENS_a_resolved_thread(self, tmp_path):
        """The correction: false was doing nothing, which wasted half the column."""
        app, backend = build()
        path = sheet(tmp_path, [{"thread_id": "t2", "resolve_comment": "false"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["reopened"] == 1
        assert not backend._comments[(DOC, "t2")].get("resolved")

    def test_true_still_resolves(self, tmp_path):
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "resolve_comment": "true"}])
        assert call(app, "apply_comment_actions",
                    path=str(path), apply=True)["resolved"] == 1

    def test_empty_still_means_leave_it_alone(self, tmp_path):
        """Three states, and the blank one has to stay 'I did not decide' - otherwise every
        untouched row reopens every resolved thread."""
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t2", "resolve_comment": ""}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["resolved"] == 0 and out["reopened"] == 0

    def test_reopening_an_open_thread_is_a_no_op(self, tmp_path):
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "resolve_comment": "false"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["reopened"] == 0
        assert any("already open" in r["detail"].lower() for r in out["rows"])


class TestDeleting:
    def test_it_deletes(self, tmp_path):
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t3", "delete_comment": "true"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["deleted"] == 1

    def test_it_is_refused_without_the_capability(self, tmp_path):
        """`comment.delete` is off in every profile but `full`, because Drive's soft delete
        strips the content AND the author, permanently."""
        app, _ = build(profile="editor")
        path = sheet(tmp_path, [{"thread_id": "t3", "delete_comment": "true"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["deleted"] == 0 and out["failed"] == 1

    def test_delete_with_a_reply_on_the_same_row_is_refused(self, tmp_path):
        """Replying to something you are about to destroy is incoherent, and silently doing
        one of the two would be a guess about which was meant."""
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t3", "delete_comment": "true",
                                 "reply_comment": "noted"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["deleted"] == 0 and out["failed"] == 1
        assert any("same row" in r["detail"] for r in out["rows"])

    def test_an_already_deleted_thread_reports_that_not_missing(self, tmp_path):
        """A deleted comment is ABSENT from a normal listing, so a naive re-run says 'no such
        comment' - which reads like the wrong sheet rather than work already done."""
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t3", "delete_comment": "true"}])
        call(app, "apply_comment_actions", path=str(path), apply=True)
        # Wipe the marker: the crash-after-delete case.
        import csv
        rows = list(csv.DictReader(path.open()))
        for r in rows:
            r["delete_comment_completed"] = ""
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["failed"] == 0
        assert any("already deleted" in r["detail"].lower() for r in out["rows"])

    def test_the_dry_run_counts_it(self, tmp_path):
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t3", "delete_comment": "true"}])
        assert call(app, "apply_comment_actions", path=str(path))["would_delete"] == 1


class TestTheExportFilters:
    def test_all_comments_by_default_resolved_included(self):
        app, _ = build()
        out = call(app, "export_comments", destination="rows")
        assert out["thread_count"] == 3

    def test_only_unresolved_when_asked(self):
        app, _ = build()
        out = call(app, "export_comments", destination="rows", includeResolved=False)
        assert out["thread_count"] == 2

    def test_by_author(self):
        app, _ = build()
        out = call(app, "export_comments", destination="rows", author="Alice")
        assert out["thread_count"] == 1
        assert out["rows"][0]["author"] == "Alice"

    def test_since_a_date(self):
        """Comments carry a timestamp, and Drive filters on it server-side."""
        app, _ = build()
        out = call(app, "export_comments", destination="rows", since="2026-08-24")
        assert out["thread_count"] == 1          # only the 2026-08-25 one

    def test_since_accepts_a_full_timestamp_too(self):
        app, _ = build()
        out = call(app, "export_comments", destination="rows",
                   since="2026-08-24T00:00:00Z")
        assert out["thread_count"] == 1

    def test_an_unparseable_since_says_so(self):
        app, _ = build()
        with pytest.raises(Exception, match="since"):
            call(app, "export_comments", destination="rows", since="last tuesday")

    def test_filters_combine(self):
        app, _ = build()
        out = call(app, "export_comments", destination="rows",
                   includeResolved=False, author="Spam")
        assert out["thread_count"] == 1

    def test_the_author_is_in_the_exported_rows(self):
        """Asked directly: yes. It is the column a register is sorted by."""
        app, _ = build()
        out = call(app, "export_comments", destination="rows")
        assert all("author" in r for r in out["rows"])
        assert {r["author"] for r in out["rows"] if not r["reply_to"]} == {
            "Alice", "Bob", "Spam"}
