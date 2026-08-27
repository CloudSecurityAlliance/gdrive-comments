"""Three defects, one theme: the record is destroyed exactly when it is the only record.

`apply_comment_actions` mutates a shared document and then writes the completed markers back to
the register. If anything goes wrong *after* the first mutation lands, the report is the only
account of what happened — and in three separate ways it was falsified or thrown away at
precisely that moment.

**#163 — a partial row reported as untouched.** The per-row `except` reset *every* outcome flag
and appended "Nothing on this row was changed", even when earlier actions on that row had
already succeeded. A row with both a reply and a resolve, where the resolve hit a transient 500,
reported `replied=0, failed=1, "Nothing on this row was changed."` — while the reply was live in
a document forty-two people were reading, and the register had already recorded it as done.

So the artifact and the report disagreed, and the report is what a human reads. Every next step
is wrong from there: re-word and re-send (duplicate), or believe the review is unfinished when
it is not.

The original reasoning is in the code and it is half right — *"a refusal has to be unambiguous
about whether it happened"*. True. It was made unambiguous by being **untrue**. "Reply posted;
resolve failed (rate limited) — re-run to finish" is both.

**#168 — an unguarded `write_back` discarded the whole report.** Called bare, after the
mutations. A read-only volume, an `.xlsx` still open in Excel, an `openpyxl` error — any of them
propagated and took the entire row-by-row report with it, leaving an exception where the only
surviving record should have been. An `.xlsx` locked open in Excel is not exotic; it is the
*expected* state seconds after somebody finishes filling the register in.

**#166 — `write_back` could not survive its own temp file on Windows.** It reopened a
`NamedTemporaryFile` by name (`wb.save(tmp.name)`) and called `os.replace` while the handle was
still open — both `PermissionError` on Windows, which the PowerShell installers make a supported
platform. It failed *after* the replies had been applied, so the crash the markers exist to
survive was the crash that stopped them being written.

The Windows failure cannot be reproduced here, so what is asserted is the portable
consequence of the same defect: `delete=False` means **an exception orphans the temp file** in
the user's own directory, next to their register, forever.
"""
from __future__ import annotations

import asyncio
import csv

import openpyxl
import pytest

from csa_google_workspace import Workspace
from csa_google_workspace._apply import write_back
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

DOC = "d1"


def build():
    cs = {DOC: [{"id": f"t{i}", "content": f"Point {i}", "author": {"displayName": "A"},
                 "createdTime": "2026-08-20T10:00:00Z", "resolved": False, "replies": []}
                for i in range(3)]}
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "Draft", "mimeType": "application/vnd.google-apps.document"}},
        documents={DOC: {"body": {"content": []}}}, comments=cs)
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                            "CSA_GW_PROFILE": "full"})
    return create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st), backend


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, {"fileId": DOC, **args})).structured_content


def register(app, tmp_path, edits, *, suffix="csv"):
    """Export, apply `edits` as {thread_id: {column: value}}, hand the path back."""
    out = call(app, "export_comments", destination="file" if suffix == "csv" else "xlsx",
               path=str(tmp_path / f"r.{suffix}"))
    path = out["written_path"]
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for row in rows:
        for column, value in edits.get(row["thread_id"], {}).items():
            row[column] = value
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    return path


class TestAPartialRowIsReportedAsPartial:
    """#163."""

    @staticmethod
    def _break_resolve(backend):
        """A transient 500 on resolve, after the reply has landed."""
        original = backend.create_reply

        def flaky(file_id, comment_id, content=None, action=None):
            if action:                       # resolve/reopen are ACTION-replies
                raise RuntimeError("backend exploded (503)")
            return original(file_id, comment_id, content=content, action=action)

        backend.create_reply = flaky         # type: ignore[method-assign]

    def test_the_successful_reply_is_still_reported(self, tmp_path):
        app, backend = build()
        path = register(app, tmp_path,
                        {"t0": {"reply_comment": "Fixed in rev 4", "resolve_comment": "TRUE"}})
        self._break_resolve(backend)
        out = call(app, "apply_comment_actions", path=path, apply=True)
        row = next(r for r in out["rows"] if r["thread_id"] == "t0")
        assert row["replied"] is True, f"the posted reply was reported as not done: {row}"
        assert row["failed"] is True, "the failed resolve must still be reported as a failure"
        assert out["replied"] == 1, f"aggregate lost the reply: {out}"

    def test_it_does_not_claim_nothing_changed(self, tmp_path):
        """The falsehood, named. The reply is live in the document."""
        app, backend = build()
        path = register(app, tmp_path,
                        {"t0": {"reply_comment": "Fixed in rev 4", "resolve_comment": "TRUE"}})
        self._break_resolve(backend)
        out = call(app, "apply_comment_actions", path=path, apply=True)
        row = next(r for r in out["rows"] if r["thread_id"] == "t0")
        assert "nothing on this row was changed" not in row["detail"].lower(), (
            f"claimed nothing changed while the reply was posted: {row['detail']}")

    def test_the_reply_really_did_land(self, tmp_path):
        """Guards the premise: if the reply never posted, the test above proves nothing."""
        app, backend = build()
        path = register(app, tmp_path,
                        {"t0": {"reply_comment": "Fixed in rev 4", "resolve_comment": "TRUE"}})
        self._break_resolve(backend)
        call(app, "apply_comment_actions", path=path, apply=True)
        replies = backend._comments[(DOC, "t0")].get("replies", [])
        assert any(r.get("content") == "Fixed in rev 4" for r in replies)

    def test_a_row_that_failed_before_doing_anything_still_says_so(self, tmp_path):
        """The original behaviour was right for this case and must survive."""
        app, _ = build()
        path = register(app, tmp_path, {"t0": {"resolve_comment": "maybe later"}})
        out = call(app, "apply_comment_actions", path=path, apply=True)
        row = next(r for r in out["rows"] if r["thread_id"] == "t0")
        assert row["failed"] is True
        assert "nothing" in row["detail"].lower(), (
            "a row that genuinely did nothing must still say so unambiguously")


class TestTheReportSurvivesAFailedWriteBack:
    """#168."""

    def test_the_report_comes_back_even_if_the_register_cannot_be_updated(
            self, tmp_path, monkeypatch):
        app, backend = build()
        path = register(app, tmp_path, {"t0": {"reply_comment": "Fixed"}})

        def refuse(*a, **k):
            raise PermissionError("the .xlsx is open in Excel")

        monkeypatch.setattr("csa_google_workspace._apply.write_back", refuse)
        out = call(app, "apply_comment_actions", path=path, apply=True)
        assert out["replied"] == 1, f"the report was lost: {out}"
        assert out["rows"], "the row-by-row account was discarded"

    def test_it_says_the_register_was_not_updated_and_that_re_running_is_safe(
            self, tmp_path, monkeypatch):
        app, _ = build()
        path = register(app, tmp_path, {"t0": {"reply_comment": "Fixed"}})

        def refuse(*a, **k):
            raise PermissionError("the .xlsx is open in Excel")

        monkeypatch.setattr("csa_google_workspace._apply.write_back", refuse)
        out = call(app, "apply_comment_actions", path=path, apply=True)
        detail = out["detail"].lower()
        assert "register" in detail, f"the write-back failure is not mentioned: {out['detail']}"
        assert "open in excel" in detail, "the reason must be surfaced, not swallowed"
        assert "re-run" in detail or "safe" in detail, (
            "the user needs telling that re-running will not duplicate the work")

    def test_the_work_still_happened(self, tmp_path, monkeypatch):
        app, backend = build()
        path = register(app, tmp_path, {"t0": {"reply_comment": "Fixed"}})
        monkeypatch.setattr("csa_google_workspace._apply.write_back",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("read-only volume")))
        call(app, "apply_comment_actions", path=path, apply=True)
        replies = backend._comments[(DOC, "t0")].get("replies", [])
        assert any(r.get("content") == "Fixed" for r in replies)


class TestWriteBackLeavesNoOrphanedTempFile:
    """#166, via the portable half of the same defect.

    `delete=False` on a `NamedTemporaryFile` means nothing cleans it up when an exception
    escapes, so a failed write-back left a temp file next to the user's register permanently.
    The Windows `PermissionError` is the other half and cannot be reproduced here.
    """

    def _strays(self, tmp_path, name):
        return [p.name for p in tmp_path.iterdir() if p.name != name]

    def test_a_successful_csv_write_leaves_nothing_behind(self, tmp_path):
        path = tmp_path / "r.csv"
        rows = [{"thread_id": "t0", "reply_comment_completed": "yes"}]
        header = ["thread_id", "reply_comment_completed"]
        path.write_text("thread_id,reply_comment_completed\nt0,\n", encoding="utf-8")
        write_back(path, rows, header)
        assert self._strays(tmp_path, "r.csv") == []
        assert "yes" in path.read_text(encoding="utf-8")

    def test_a_successful_xlsx_write_leaves_nothing_behind(self, tmp_path):
        path = tmp_path / "r.xlsx"
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["thread_id", "reply_comment_completed"]); ws.append(["t0", None])
        wb.save(path)
        write_back(path, [{"thread_id": "t0", "reply_comment_completed": "yes"}],
                   ["thread_id", "reply_comment_completed"])
        assert self._strays(tmp_path, "r.xlsx") == []
        assert openpyxl.load_workbook(path).active["B2"].value == "yes"

    def test_a_failed_write_leaves_nothing_behind(self, tmp_path, monkeypatch):
        """The orphan. An exception mid-write must not leave a temp file in the user's folder."""
        path = tmp_path / "r.csv"
        path.write_text("thread_id,reply_comment_completed\nt0,\n", encoding="utf-8")
        monkeypatch.setattr("csa_google_workspace._apply.os.replace",
                            lambda *a: (_ for _ in ()).throw(PermissionError("locked")))
        with pytest.raises(PermissionError):
            write_back(path, [{"thread_id": "t0", "reply_comment_completed": "yes"}],
                       ["thread_id", "reply_comment_completed"])
        assert self._strays(tmp_path, "r.csv") == [], "a temp file was orphaned next to the register"
