"""The register becomes a worksheet you can apply back — and survives being interrupted.

The export made 205 threads readable. This makes them actionable: sort by reviewer, triage in a
grid, draft replies where you are already looking at the passage, apply in one pass. Google Docs
cannot do that at all.

It is also a **bulk mutation of a shared document driven by a file**, which is a far sharper
thing than an export, so the design is mostly about the ways it can go wrong.

**Two layers of idempotency, and one is not enough.** The obvious protection is a `*_completed`
column the importer ticks as it goes, so a re-run skips finished rows. That handles the ordinary
case and fails in exactly the interesting one: the reply posts, and the process dies *before* the
tick is written. The sheet says not-done; the document says done. A re-run on the marker alone
would post it twice, to a thread forty-two people are reading.

So the marker is the *fast* path and the live document is the *authority*: before posting, look
for a reply with this exact text from this user already on the thread. As the CINO put it —
there is no real reason to post a completely identical reply twice — so an exact match is a
duplicate, and `force` exists for the rare case where somebody means it.

Resolve needs no such care: `resolved` is already the state, so a resolved thread is skipped on
its own evidence.
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


def comments(*, replies=(), resolved=False):
    return {DOC: [
        {"id": "t1", "content": "Fix the reference", "author": {"displayName": "Reviewer"},
         "quotedFileContent": {"value": "the shared responsibility model"},
         "createdTime": "2026-08-20T10:00:00Z", "resolved": resolved,
         "replies": list(replies)},
        {"id": "t2", "content": "Second point", "author": {"displayName": "Other"},
         "createdTime": "2026-08-20T11:00:00Z", "replies": []},
    ]}


def build(cs=None, **env):
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Draft", "mimeType": DOC_MIME}},
        documents={DOC: {"body": {"content": []}}}, comments=cs or comments())
    app = create_server(lambda: Workspace(backend), settings=settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
         "CSA_GW_PROFILE": "full", **env}))
    return app, backend


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, {"fileId": DOC, **args})).structured_content


def sheet(tmp_path, rows, name="actions.csv"):
    """A filled-in register, as somebody would hand it back."""
    import csv

    from csa_google_workspace._export import COLUMNS
    path = tmp_path / name
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    return path


class TestTheColumnsExist:
    def test_the_export_carries_the_four_action_columns(self):
        app, _ = build()
        out = call(app, "export_comments", destination="rows")
        for column in ("reply_comment", "resolve_comment",
                       "reply_comment_completed", "resolve_comment_completed"):
            assert column in out["columns"]

    def test_they_survive_the_empty_column_trim(self, tmp_path):
        """`used_columns` drops columns empty for every row - and these are ALWAYS empty on
        export, because they are inputs. Dropping them would remove the very thing somebody
        is meant to fill in."""
        app, _ = build()
        call(app, "export_comments", destination="xlsx", path=str(tmp_path / "r.xlsx"))
        openpyxl = pytest.importorskip("openpyxl")
        header = [c.value for c in next(
            openpyxl.load_workbook(tmp_path / "r.xlsx").active.iter_rows(max_row=1))]
        assert "reply_comment" in header and "resolve_comment" in header


class TestApplyingReplies:
    def test_a_reply_is_posted(self, tmp_path):
        app, backend = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed, thanks."}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["replied"] == 1
        posted = [r["content"] for r in backend._comments[(DOC, "t1")]["replies"]]
        assert "Fixed, thanks." in posted

    def test_an_empty_cell_does_nothing(self, tmp_path):
        app, backend = build()
        path = sheet(tmp_path, [{"thread_id": "t1"}, {"thread_id": "t2"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["replied"] == 0 and out["resolved"] == 0

    def test_a_reply_row_is_refused(self, tmp_path):
        """Drive replies are flat - you reply to a THREAD, never to a reply. A row with
        `reply_to` set is somebody filling in the wrong line."""
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "r9", "reply_to": "t1",
                                 "reply_comment": "no"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["replied"] == 0
        assert any("reply_to" in r["detail"] for r in out["rows"])


class TestIdempotencyLayerOneTheMarkers:
    def test_a_completed_reply_is_skipped(self, tmp_path):
        app, backend = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed.",
                                 "reply_comment_completed": "yes"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["replied"] == 0
        assert not backend._comments[(DOC, "t1")]["replies"]

    def test_the_marker_is_written_back(self, tmp_path):
        """So the next run can skip it without asking Google."""
        import csv
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed."}])
        call(app, "apply_comment_actions", path=str(path), apply=True)
        row = next(csv.DictReader(path.open(encoding="utf-8")))
        assert row["reply_comment_completed"].lower() in ("yes", "true", "done")

    def test_a_dry_run_writes_no_marker(self, tmp_path):
        import csv
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed."}])
        call(app, "apply_comment_actions", path=str(path))
        row = next(csv.DictReader(path.open(encoding="utf-8")))
        assert not row["reply_comment_completed"]


class TestIdempotencyLayerTwoTheDocument:
    """The case the markers cannot cover: posted, then died before ticking."""

    def test_an_identical_reply_already_mine_is_not_posted_again(self, tmp_path):
        app, backend = build(comments(replies=[
            {"id": "r1", "content": "Fixed, thanks.",
             "author": {"displayName": "Me", "me": True}}]))
        # The sheet still says not-done - exactly the crash-after-post state.
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed, thanks."}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["replied"] == 0
        assert len(backend._comments[(DOC, "t1")]["replies"]) == 1
        assert any("already" in r["detail"].lower() for r in out["rows"])

    def test_the_same_text_from_SOMEBODY_ELSE_does_not_block_it(self, tmp_path):
        """Only my own duplicate is evidence that I already did this."""
        app, backend = build(comments(replies=[
            {"id": "r1", "content": "Fixed, thanks.",
             "author": {"displayName": "Someone else"}}]))
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed, thanks."}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["replied"] == 1

    def test_whitespace_does_not_defeat_the_check(self, tmp_path):
        app, _ = build(comments(replies=[
            {"id": "r1", "content": "Fixed, thanks.",
             "author": {"displayName": "Me", "me": True}}]))
        path = sheet(tmp_path, [{"thread_id": "t1",
                                 "reply_comment": "  Fixed, thanks.\n"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["replied"] == 0

    def test_force_posts_it_anyway(self, tmp_path):
        """For the rare case somebody means it. It has to be asked for explicitly."""
        app, backend = build(comments(replies=[
            {"id": "r1", "content": "Fixed, thanks.",
             "author": {"displayName": "Me", "me": True}}]))
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed, thanks."}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True, force=True)
        assert out["replied"] == 1
        assert len(backend._comments[(DOC, "t1")]["replies"]) == 2


class TestResolving:
    @pytest.mark.parametrize("value", ["true", "TRUE", "yes", "y", "1", "x"])
    def test_truthy_spellings_resolve(self, tmp_path, value):
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "resolve_comment": value}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["resolved"] == 1, value

    @pytest.mark.parametrize("value", ["false", "no", "0", ""])
    def test_falsy_spellings_do_nothing(self, tmp_path, value):
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "resolve_comment": value}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["resolved"] == 0, value

    def test_an_unrecognised_value_is_refused_not_guessed(self, tmp_path):
        """"maybe later" must fail loudly. Guessing at a value that resolves somebody's
        thread is worse than refusing the row."""
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "resolve_comment": "maybe later"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["resolved"] == 0
        assert any("maybe later" in r["detail"] for r in out["rows"])

    def test_an_already_resolved_thread_is_skipped(self, tmp_path):
        """`resolved` is the state itself, so it needs no marker to be idempotent."""
        app, _ = build(comments(resolved=True))
        path = sheet(tmp_path, [{"thread_id": "t1", "resolve_comment": "true"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["resolved"] == 0
        assert any("already" in r["detail"].lower() for r in out["rows"])

    def test_reply_lands_before_resolve(self, tmp_path):
        """Resolving posts its own visible action-reply. The substantive reply has to come
        first or the thread reads backwards."""
        app, backend = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed.",
                                 "resolve_comment": "true"}])
        call(app, "apply_comment_actions", path=str(path), apply=True)
        contents = [r.get("content") for r in backend._comments[(DOC, "t1")]["replies"]]
        assert contents[0] == "Fixed."


class TestTheDryRunIsTheDefault:
    def test_nothing_happens_without_apply(self, tmp_path):
        app, backend = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed.",
                                 "resolve_comment": "true"}])
        out = call(app, "apply_comment_actions", path=str(path))
        assert not backend._comments[(DOC, "t1")]["replies"]
        assert out["applied"] is False

    def test_it_still_reports_what_it_would_do(self, tmp_path):
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "Fixed.",
                                 "resolve_comment": "true"}])
        out = call(app, "apply_comment_actions", path=str(path))
        assert out["would_reply"] == 1 and out["would_resolve"] == 1

    def test_a_dry_run_names_what_it_would_skip(self, tmp_path):
        app, _ = build(comments(resolved=True))
        path = sheet(tmp_path, [{"thread_id": "t1", "resolve_comment": "true"}])
        out = call(app, "apply_comment_actions", path=str(path))
        assert out["would_resolve"] == 0


class TestPerRowOutcomes:
    def test_every_row_is_accounted_for(self, tmp_path):
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "t1", "reply_comment": "a"},
                                {"thread_id": "t2", "resolve_comment": "true"},
                                {"thread_id": "nope", "reply_comment": "b"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert len(out["rows"]) == 3
        assert all(r.get("detail") for r in out["rows"])

    def test_a_failing_row_does_not_stop_the_others(self, tmp_path):
        """205 rows and #113 fails: the other 204 must still land, and the report must say
        which was which."""
        app, _ = build()
        path = sheet(tmp_path, [{"thread_id": "nope", "reply_comment": "a"},
                                {"thread_id": "t2", "reply_comment": "b"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert out["replied"] == 1
        assert out["failed"] == 1
