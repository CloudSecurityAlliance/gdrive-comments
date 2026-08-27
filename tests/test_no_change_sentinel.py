"""`NO_CHANGE`: a default that is safe to apply untouched, and says so on every row.

The problem it solves, demonstrated rather than argued. `FALSE` in `resolve_comment` means
**reopen** - an action, not an absence - so pre-filling the column with `FALSE` and applying an
untouched register reopened every already-resolved thread:

    resolved before : 3 of 6
    applied         -> 3 reopened
    resolved after  : 0 of 6

Blank was the safe default but says nothing: an empty cell cannot tell you whether the column
means anything, and a reader has to know the convention. `NO_CHANGE` is both - safe to apply and
self-explaining, sitting in the cell next to a dropdown that shows the alternatives.

So the columns are genuinely THREE-state, and the code says so: `decision()` returns act /
reverse / none rather than a bool that has to carry an absence as well.

    resolve_comment   TRUE -> resolve    FALSE -> reopen     NO_CHANGE / blank -> nothing
    delete_comment    TRUE -> delete     FALSE -> REFUSED    NO_CHANGE / blank -> nothing

`FALSE` is refused on delete rather than offered or ignored. Next to the word "delete" it reads
as *undo the delete*, and there is none - so the dropdown does not offer it, and a hand-typed
one fails loudly rather than doing nothing while somebody believes a restore happened.

**Blank must keep working.** Cells get cleared, sorts leave gaps, CSVs round-trip through tools
that drop a lone sentinel. A default nobody can accidentally destroy is not a default at all.
"""
from __future__ import annotations

import asyncio
import csv

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace._apply import ACT, NO_CHANGE, NONE, REVERSE, decision
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

DOC = "d1"


def build(resolved_every_other=True):
    cs = {DOC: [{"id": f"t{i}", "content": f"Point {i}", "author": {"displayName": "A"},
                 "createdTime": "2026-08-20T10:00:00Z",
                 "resolved": bool(resolved_every_other and i % 2 == 0), "replies": []}
                for i in range(6)]}
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "Draft", "mimeType": "application/vnd.google-apps.document"}},
        documents={DOC: {"body": {"content": []}}}, comments=cs)
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                            "CSA_GW_PROFILE": "full"})
    app = create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st)
    return app, backend


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, {"fileId": DOC, **args})).structured_content


class TestTheTriState:
    @pytest.mark.parametrize("value,expected", [
        ("TRUE", ACT), ("yes", ACT), ("1", ACT),
        ("FALSE", REVERSE), ("no", REVERSE), ("0", REVERSE),
        ("NO_CHANGE", NONE), ("no_change", NONE), ("No Change", NONE), ("", NONE),
        ("   ", NONE), (None, NONE),
    ])
    def test_it_reads_three_states(self, value, expected):
        assert decision(value) is expected

    def test_anything_else_is_unreadable_not_guessed(self):
        """"maybe later" closing somebody's open question is worse than a refusal."""
        assert decision("maybe later") is None


class TestApplyingAnUntouchedRegisterChangesNothing:
    """The whole point. This is the test that would have caught the pre-filled-FALSE hazard."""

    def test_an_untouched_register_applied_unchanged_is_a_no_op(self, tmp_path):
        app, backend = build()
        before = sum(1 for c in backend._comments.values() if c.get("resolved"))
        path = tmp_path / "r.csv"
        out = call(app, "export_comments", destination="file", path=str(path))
        applied = call(app, "apply_comment_actions", path=out["written_path"], apply=True)
        after = sum(1 for c in backend._comments.values() if c.get("resolved"))
        assert (applied["resolved"], applied["reopened"], applied["deleted"]) == (0, 0, 0)
        assert applied["failed"] == 0, "an untouched register must not produce failures"
        assert after == before, "applying an untouched register changed the document"

    def test_the_export_leaves_the_decision_columns_BLANK(self, tmp_path):
        """Blank, not pre-filled. Blank has always been the safe default, and a column of
        blanks lets somebody see at a glance which rows they have touched - `NO_CHANGE` on all
        205 rows is noise to read past. The dropdown carries the discoverability instead."""
        app, _ = build()
        out = call(app, "export_comments", destination="file", path=str(tmp_path / "r.csv"))
        rows = list(csv.DictReader(open(out["written_path"], encoding="utf-8")))
        assert all(r["resolve_comment"] == "" for r in rows)
        assert all(r["delete_comment"] == "" for r in rows)

    def test_reply_is_blank_too(self, tmp_path):
        """Free text; blank obviously means no reply."""
        app, _ = build()
        out = call(app, "export_comments", destination="file", path=str(tmp_path / "r.csv"))
        rows = list(csv.DictReader(open(out["written_path"], encoding="utf-8")))
        assert all(r["reply_comment"] == "" for r in rows)


class TestBlankStillWorks:
    """Cells get cleared, sorts leave gaps, and CSVs pass through tools that drop a lone
    sentinel. A default somebody can accidentally destroy is not a default."""

    def test_blank_resolve_does_nothing(self, tmp_path):
        app, backend = build()
        path = _sheet(tmp_path, [{"thread_id": "t0", "resolve_comment": ""}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert (out["resolved"], out["reopened"], out["failed"]) == (0, 0, 0)

    def test_blank_delete_does_nothing(self, tmp_path):
        app, _ = build()
        path = _sheet(tmp_path, [{"thread_id": "t1", "delete_comment": ""}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert (out["deleted"], out["failed"]) == (0, 0)


class TestTheActionsStillWork:
    def test_true_resolves(self, tmp_path):
        app, _ = build()
        path = _sheet(tmp_path, [{"thread_id": "t1", "resolve_comment": "TRUE"}])
        assert call(app, "apply_comment_actions",
                    path=str(path), apply=True)["resolved"] == 1

    def test_false_reopens(self, tmp_path):
        app, _ = build()
        path = _sheet(tmp_path, [{"thread_id": "t0", "resolve_comment": "FALSE"}])
        assert call(app, "apply_comment_actions",
                    path=str(path), apply=True)["reopened"] == 1

    def test_false_on_delete_is_REFUSED_not_quietly_ignored(self, tmp_path):
        """FALSE next to "delete" reads as *undo the delete*, and there is none - Drive strips
        a comment's text and author permanently. Treating it as a silent no-op would leave
        somebody believing a restore had happened, so it fails and says why."""
        app, _ = build()
        path = _sheet(tmp_path, [{"thread_id": "t1", "delete_comment": "FALSE"}])
        out = call(app, "apply_comment_actions", path=str(path), apply=True)
        assert (out["deleted"], out["failed"]) == (0, 1)
        assert any("no way to undo" in r["detail"].lower() for r in out["rows"])


class TestTheDropdownOffersIt:
    def test_no_change_is_in_both(self, tmp_path):
        openpyxl = pytest.importorskip("openpyxl")
        app, _ = build()
        out = call(app, "export_comments", destination="xlsx", path=str(tmp_path / "r.xlsx"))
        ws = openpyxl.load_workbook(out["written_path"]).active
        offered = " ".join(dv.formula1 for dv in ws.data_validations.dataValidation)
        assert offered.count(NO_CHANGE) == 2

    def test_every_offered_value_is_readable(self, tmp_path):
        openpyxl = pytest.importorskip("openpyxl")
        app, _ = build()
        out = call(app, "export_comments", destination="xlsx", path=str(tmp_path / "r.xlsx"))
        ws = openpyxl.load_workbook(out["written_path"]).active
        for dv in ws.data_validations.dataValidation:
            for value in dv.formula1.strip('"').split(","):
                assert decision(value) is not None, f"{value!r} is offered but unreadable"


def _sheet(tmp_path, rows):
    from csa_google_workspace._export import COLUMNS
    path = tmp_path / "actions.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS)); w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    return path
