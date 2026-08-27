"""Three smaller defects from the same review, and one of them explains the other nine.

**#164 — a safe re-run cried "DIFFERENT DOCUMENT".** `missing.append(number)` ran *before* the
already-deleted tombstone check, and the row was never taken back out. So re-running a delete
register — the most ordinary flow the feature has, run it twice — reported every row correctly as
"already deleted" and then headed the report:

    4 of 4 rows name a comment this file does not have. This register was most likely
    exported from a DIFFERENT DOCUMENT.

That warning exists to catch a genuinely serious mistake: applying a register to the wrong file.
Firing it on the normal path **trains people to ignore it**, which is exactly when it stops
protecting anybody. A safety message that cries wolf is worse than no message, because it spends
the attention it will need later.

The existing test used a **1-row** register, which stays under the `max(3, …)` threshold, so the
warning could never fire in CI. Reproduced here with four rows.

**#169 — `force` was inert exactly when it was meant to be used.** The
`reply_comment_completed` marker was checked *before* the `force` branch, so `force` only ever
overrode the live-document duplicate check and never the marker. But the person who genuinely
means "say it again" is, almost by definition, working from a register that has **already been
applied once** — which is when the markers exist. So `force` did nothing in its own use case, and
silently: the row reported "already marked done", indistinguishable from `force` having been
honoured and found nothing to do.

Scoped deliberately. `force` now overrides the **reply** marker, because re-posting the same text
is a coherent thing to want. It does **not** invent semantics for the other two: an
already-resolved thread is skipped on `comment.resolved` rather than on its marker, and there is
no such thing as re-deleting a deleted comment. Those two now say so instead of looking satisfied.

**#165 — the demo applied the Doc's register to Sheets and Slides, and passed green.** The
`apply_comment_actions` step was the only one in `per_type()` that did not bind `key=key`,
resolving its target as `document_id or spreadsheet_id or presentation_id`. `document_id` is
populated first, so the spreadsheet and presentation groups applied *their own* register against
the **Doc**.

It passed because a demo register has nothing filled in, so every row reports "no change
requested" — a green step demonstrating the wrong pairing. That is why the round trip was
unverified for two of three file types, and it is the reason the boolean-`FALSE` defect (#161) and
the docstring contradiction (#162) were not caught here: the demo never exercised a register
against the file it came from.
"""
from __future__ import annotations

import asyncio
import csv

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.demo import _plan
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

DOC = "d1"
ME = {"displayName": "Me", "me": True}


def build(threads=4):
    cs = {DOC: [{"id": f"t{i}", "content": f"Point {i}", "author": {"displayName": "A"},
                 "createdTime": "2026-08-20T10:00:00Z", "resolved": False, "replies": []}
                for i in range(threads)]}
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "Draft", "mimeType": "application/vnd.google-apps.document"}},
        documents={DOC: {"body": {"content": []}}}, comments=cs)
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                            "CSA_GW_PROFILE": "full"})
    return create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st), backend


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, {"fileId": DOC, **args})).structured_content


def register(app, tmp_path, column, value, *, only=None):
    out = call(app, "export_comments", destination="file", path=str(tmp_path / "r.csv"))
    path = out["written_path"]
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for row in rows:
        if row["reply_to"]:                       # thread rows only
            continue
        if only is None or row["thread_id"] in only:
            row[column] = value
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    return path


class TestASafeReRunDoesNotCryWolf:
    """#164. Four rows, so the `max(3, …)` threshold is actually reachable."""

    def test_re_running_a_delete_register_does_not_claim_the_wrong_document(self, tmp_path):
        app, _ = build(threads=4)
        path = register(app, tmp_path, "delete_comment", "TRUE")
        first = call(app, "apply_comment_actions", path=path, apply=True)
        assert first["deleted"] == 4, f"precondition: expected 4 deletes, got {first}"
        again = call(app, "apply_comment_actions", path=path, apply=True)
        assert "different document" not in again["detail"].lower(), (
            f"a normal re-run was reported as the wrong document: {again['detail']}")

    def test_every_row_still_reports_already_deleted(self, tmp_path):
        app, _ = build(threads=4)
        path = register(app, tmp_path, "delete_comment", "TRUE")
        call(app, "apply_comment_actions", path=path, apply=True)
        again = call(app, "apply_comment_actions", path=path, apply=True)
        details = [r["detail"] for r in again["rows"] if not r["thread_id"].startswith("r")]
        assert all("already deleted" in d for d in details), details
        assert again["failed"] == 0

    def test_a_genuinely_wrong_file_still_warns(self, tmp_path):
        """The warning must keep working, or fixing the false positive removed the control."""
        app, _ = build(threads=4)
        path = register(app, tmp_path, "resolve_comment", "TRUE")
        other = FakeBackend(
            {DOC: {"id": DOC, "name": "Other", "mimeType": "application/vnd.google-apps.document"}},
            documents={DOC: {"body": {"content": []}}},
            comments={DOC: [{"id": "zzz", "content": "unrelated",
                             "author": {"displayName": "B"}, "resolved": False, "replies": []}]})
        st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                                "CSA_GW_PROFILE": "full"})
        wrong = create_server(lambda: Workspace(PolicyBackend(other, st.policy)), settings=st)
        out = call(wrong, "apply_comment_actions", path=path, apply=True)
        assert "different document" in out["detail"].lower(), out["detail"]


class TestForceOverridesTheMarkerItWasMeantFor:
    """#169."""

    def test_force_reposts_a_reply_whose_marker_is_already_ticked(self, tmp_path):
        app, backend = build(threads=1)
        path = register(app, tmp_path, "reply_comment", "Fixed")
        call(app, "apply_comment_actions", path=path, apply=True)      # ticks the marker
        assert len(backend._comments[(DOC, "t0")]["replies"]) == 1
        out = call(app, "apply_comment_actions", path=path, apply=True, force=True)
        assert out["replied"] == 1, f"force did nothing on an applied register: {out['rows']}"
        assert len(backend._comments[(DOC, "t0")]["replies"]) == 2

    def test_without_force_the_marker_still_skips(self, tmp_path):
        app, backend = build(threads=1)
        path = register(app, tmp_path, "reply_comment", "Fixed")
        call(app, "apply_comment_actions", path=path, apply=True)
        again = call(app, "apply_comment_actions", path=path, apply=True)
        assert again["replied"] == 0
        assert len(backend._comments[(DOC, "t0")]["replies"]) == 1

    def test_resolve_reports_the_threads_own_state_not_a_tick_box(self, tmp_path):
        """Why `force` is scoped to reply, asserted rather than assumed.

        A re-run of a resolve row never reaches the marker at all: the thread is already
        resolved, so it is skipped on `comment.resolved` - the document's own state - and the
        row says "already resolved". That is not silence, and it is not a tick-box: there is
        genuinely nothing for `force` to override, because resolving an already-resolved thread
        is not a thing a person can mean.

        Written after asserting the opposite and being wrong. The marker branch exists for the
        crash window where the register says done and the document has not caught up.
        """
        app, _ = build(threads=1)
        path = register(app, tmp_path, "resolve_comment", "TRUE")
        call(app, "apply_comment_actions", path=path, apply=True)
        again = call(app, "apply_comment_actions", path=path, apply=True, force=True)
        detail = again["rows"][0]["detail"].lower()
        assert "already resolved" in detail, detail
        assert again["resolved"] == 0, "force must not re-resolve an already-resolved thread"


class TestTheDemoAppliesEachRegisterToItsOwnFile:
    """#165 — the gap that let the others through."""

    KINDS = {"document": "DOC", "spreadsheet": "SHEET", "presentation": "DECK"}

    def test_every_kind_has_an_apply_step(self):
        for kind in self.KINDS:
            names = [s.tool for s in _plan.per_type(kind)]
            assert "apply_comment_actions" in names, f"{kind} has no apply step"

    def test_each_kind_targets_its_own_file(self):
        """The defect, asserted structurally: resolve the step's arguments against a state where
        all three ids differ, and check each kind picks the id for ITSELF. Before the fix every
        one of them resolved to the Doc, because `document_id` is first in the `or` chain."""
        state = {"document_id": "DOC", "spreadsheet_id": "SHEET", "presentation_id": "DECK",
                 "register": "/tmp/r.csv"}
        for kind, expected in self.KINDS.items():
            step = next(s for s in _plan.per_type(kind) if s.tool == "apply_comment_actions")
            got = step.args(dict(state))["fileId"]
            assert got == expected, (
                f"the {kind} group applies its register to {got}, not {expected}")
