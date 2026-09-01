"""The demonstration, run offline, on every commit.

This is the point of building it against `FakeBackend` as well as real Google: a demo nobody
runs between releases rots, and a rotted demo is worse than none, because it is the first thing
a new person sees. Running the whole matrix here means a tool whose arguments change breaks CI
rather than breaking somebody's first impression.

The coverage assertion is the one that matters. It is computed from the server's own registry,
so adding a tool without adding it to the plan fails here — which is what keeps "it exercises
everything" true rather than merely once-true.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.demo import NOT_EXERCISED, Runner, build, coverage, render
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

# A real, writable export directory for the whole module. The plan writes a register to disk,
# and the default destination is `~/Downloads` - which exists on the machines the demonstration
# actually runs on and NOT on a CI runner, where the step failed on all five Pythons while
# passing locally. Refusing to create a missing directory is deliberate (a typo must not
# silently start writing somewhere unexpected), so the fix belongs in the test environment
# rather than in the product.
_EXPORT_DIR = tempfile.mkdtemp(prefix="csa-demo-export-")

FULL = {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*", "CSA_GW_PROFILE": "full",
        "CSA_GW_EXPORT_DIR": _EXPORT_DIR}


@pytest.fixture(autouse=True)
def _quiet():
    """The Sheets cell map warns when it cannot export; expected here and noisy."""
    logging.disable(logging.WARNING)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture
def server():
    backend = FakeBackend({})
    return create_server(lambda: Workspace(backend), settings=settings_from_env(FULL))


@pytest.fixture
def report(server):
    return Runner(server).run(prefix="demo-test", folder_name="Demo folder",
                              share_with="someone@example.com")


def test_the_whole_demonstration_runs(report):
    """Every step, end to end. A failure here is a broken tool or a broken plan, and the
    message names which step and why."""
    assert report.failed == [], "\n".join(
        f"{o.step.tool}: {o.detail}" for o in report.failed)


def test_nothing_is_silently_skipped(report):
    """A skip is how a capability-gated step behaves when the capability is off - but under the
    `full` profile nothing should be gated, so a skip here means a step could not get what it
    needed from an earlier one.

    The cleanup tail is the one legitimate exception: it has more trash slots than files, on
    purpose, because the plan is built before anything has run. Those announce themselves as
    "nothing left to tidy" and are the normal way it ends.
    """
    unexpected = [o for o in report.skipped if o.detail != "nothing left to tidy"]
    assert unexpected == [], "\n".join(
        f"{o.step.tool}: {o.detail}" for o in unexpected)


def test_the_cleanup_trashes_everything_it_made(report):
    """It used to trash one file to DEMONSTRATE trashing, and stop - which is a demo of
    cleanup rather than cleanup, and the difference is somebody else's Drive filling up."""
    cleanup = [o for o in report.outcomes if o.step.group == "cleanup"]
    assert {o.step.tool for o in cleanup} == {"trash_file"}

    # The invariant that actually proves it, and does not depend on counting artefacts: the
    # tail must run out of THINGS before it runs out of SLOTS. A run that used every slot may
    # have had more to trash than it could reach, so a trailing "nothing left to tidy" is the
    # evidence that the Drive is clear.
    assert cleanup[-1].status == "skipped" and cleanup[-1].detail == "nothing left to tidy", (
        "the cleanup used every slot it had, so it may have left something behind; "
        "raise _MAX_CLEANUP in demo/_plan.py")

    # And the folder itself, which is the one a person notices.
    assert report.state.get("folder_id")
    assert len([o for o in cleanup if o.status == "ok"]) >= 4


def test_it_exercises_every_tool_the_server_registers(server, report):
    """The claim this whole thing rests on, computed rather than asserted by hand.

    A new tool that nobody adds to the plan lands here, which is the only way "it covers
    everything" survives contact with future work.
    """
    exercised, untouched, excused = coverage(server, report)
    assert untouched == set(), (
        f"registered but never exercised: {sorted(untouched)}. Add a step to demo/_plan.py, "
        f"or add it to NOT_EXERCISED with the reason it cannot be automated.")
    registered = {t.name for t in asyncio.run(server.list_tools())}
    assert len(exercised) + len(excused) == len(registered)


def test_what_cannot_be_automated_is_named_not_omitted(server):
    """`authenticate` waits for a human. Excusing it by name keeps it visible in the report;
    dropping it from the count silently would make 100% mean less than it says."""
    registered = {t.name for t in asyncio.run(server.list_tools())}
    assert set(NOT_EXERCISED) <= registered
    assert all(reason for reason in NOT_EXERCISED.values())


def test_every_file_type_gets_the_full_operation_set(report):
    """The matrix, not a list. Comments are one API across all three types and content is
    three - so exercising comments only on a Doc would prove nothing about the other two."""
    per_type: dict[str, set[str]] = {}
    for outcome in report.outcomes:
        if outcome.step.group in ("document", "spreadsheet", "presentation"):
            per_type.setdefault(outcome.step.group, set()).add(outcome.step.tool)
    assert set(per_type) == {"document", "spreadsheet", "presentation"}

    # The comment lifecycle, in full, on each of them.
    lifecycle = {"create_comment", "get_comment", "list_comments", "reply_comment",
                 "edit_comment", "resolve_comment", "reopen_comment", "delete_comment"}
    for kind, tools in per_type.items():
        assert lifecycle <= tools, f"{kind} is missing {sorted(lifecycle - tools)}"

    # And add / edit / remove content, by whichever tool that type uses for it.
    assert {"append_text", "replace_text"} <= per_type["document"]
    assert {"update_cells", "append_rows"} <= per_type["spreadsheet"]
    assert {"insert_slide_text", "replace_text", "list_slides"} <= per_type["presentation"]


def test_a_disabled_capability_is_skipped_not_failed():
    """The demonstration has to be runnable on a default install. Refusing to start would make
    the safest configuration the one that cannot be shown.

    **The default no longer refuses anything (v0.31.0)**, so this runs against `commenter` — a
    narrowed profile an operator might actually choose. The property under test never was "the
    default refuses things"; it is that a *refused* capability produces a SKIP rather than a
    failed run, and that needs some profile that refuses something.

    Asserted against the profile's own capability set rather than a hard-coded list, so it keeps
    testing the property if the grouping moves again."""
    backend = FakeBackend({})
    server = create_server(lambda: Workspace(backend), settings=settings_from_env(
        {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
         "CSA_GW_PROFILE": "commenter",
         "CSA_GW_EXPORT_DIR": _EXPORT_DIR}))
    report = Runner(server).run(prefix="demo-test", folder_name="Demo",
                                share_with="someone@example.com")
    from csa_google_workspace.policy import PROFILES
    enabled = set(PROFILES["commenter"])
    gated = [o for o in report.outcomes if o.step.requires]
    assert gated, "the plan no longer exercises any gated tool"

    refused = [o for o in gated if o.step.requires not in enabled]
    assert refused, "the plan no longer exercises anything the DEFAULT policy refuses"
    assert all(o.status == "skipped" for o in refused)
    assert all("capability" in o.detail for o in refused)

    # The other half: a step whose capability the default DOES grant must not be skipped for
    # that reason - otherwise "runnable on a default install" would be satisfied by a run that
    # skipped everything.
    permitted = [o for o in gated if o.step.requires in enabled]
    assert permitted, "the plan no longer exercises any gated tool the default permits"
    assert not any(o.status == "skipped" and "capability" in (o.detail or "")
                   for o in permitted)
    assert report.failed == []


def test_the_report_names_what_it_did_not_cover(server):
    """A coverage report that omits its gaps is a coverage report that can be believed when it
    should not be."""
    from csa_google_workspace.demo import Report
    text = render(server, Report())
    assert "Not exercised" in text
    assert "`create_comment`" in text


def test_the_plan_can_be_read_without_a_google_account():
    """It is data, so "what does this exercise?" is answerable before anything runs - which is
    what lets the coverage test above exist at all."""
    steps = build("p", "folder", "a@b.c", keep=False)
    assert len(steps) > 50
    assert all(step.narrate for step in steps), "every step has to be describable"
    assert all(step.group for step in steps)


def test_keep_skips_the_cleanup():
    with_cleanup = build("p", "f", "a@b.c", keep=False)
    without = build("p", "f", "a@b.c", keep=True)
    assert len(with_cleanup) > len(without)
    assert not [s for s in without if s.group == "cleanup"]


class TestFeedback:
    """The closing question, and the promises made while asking it.

    Most of these check what the issue does NOT contain. It carries somebody's words to a
    public tracker under their own name, so "it will not include your documents" has to be
    true rather than merely intended.
    """

    def test_the_body_carries_the_comment_and_the_environment(self):
        from csa_google_workspace._environment import describe_environment
        from csa_google_workspace.demo._feedback import issue_body
        body = issue_body("worked fine", "## What ran\n\n67 steps ok")
        assert "worked fine" in body
        assert describe_environment().server_version in body
        assert "67 steps ok" in body

    def test_the_body_says_it_was_filed_with_consent(self):
        """A reader of the issue should be able to tell it was not scraped."""
        from csa_google_workspace.demo._feedback import issue_body
        assert "consent" in issue_body("x", "y").lower()

    def test_an_empty_comment_still_produces_a_readable_issue(self):
        from csa_google_workspace.demo._feedback import issue_body
        assert "no comment given" in issue_body("   ", "coverage")

    def test_the_consent_text_says_public_and_says_what_is_excluded(self):
        """Both halves matter: somebody deciding needs to know it is public AND that their
        documents are not in it. Either alone leaves the decision under-informed."""
        from csa_google_workspace.demo._feedback import CONSENT
        text = CONSENT.lower()
        assert "public" in text
        assert "not contain" in text and "link" in text
        assert "skip" in text or "enter to skip" in text.replace("\n", " ")

    def test_the_title_names_the_version_and_the_outcome(self):
        from csa_google_workspace.demo._feedback import title
        assert "clean run" in title(0)
        assert "failed" in title(3)

    def test_the_url_carries_the_label(self):
        from csa_google_workspace.demo._feedback import LABEL, new_issue_url
        assert LABEL in new_issue_url("t", "b")

    def test_nothing_from_the_demo_state_reaches_the_issue(self, server):
        """The strongest version of the promise: run the whole demonstration, then check that
        no id or name it produced appears anywhere in the issue body."""
        from csa_google_workspace.demo._feedback import issue_body
        report = Runner(server).run(prefix="demo-secret-prefix", folder_name="Secret folder",
                                    share_with="private@example.com")
        body = issue_body("a comment", render(server, report))
        ids = [value for key, value in report.state.items()
               if key.endswith("_id") and isinstance(value, str)]
        assert ids, "the run produced no ids, so this test is not checking anything"
        for value in ids:
            assert value not in body
        assert "Secret folder" not in body
        assert "private@example.com" not in body


def test_a_google_rejection_reaches_the_model_readably():
    """A Drive 400 used to become an UnexpectedToolError, whose message the SDK suppresses.

    `search_files` takes Drive's raw `q` syntax, so a model that passes free text gets a 400 -
    and with the message dropped it saw "Error executing tool search_files" and had nothing to
    correct. Found by the demonstration doing exactly that on its first real run.
    """
    from mcp.server.mcpserver.exceptions import ToolError

    from csa_google_workspace import exceptions as exc

    class Rejecting(FakeBackend):
        def search_files(self, *a, **k):
            raise exc.ApiError(400, "invalid", "Invalid Value")

    server = create_server(lambda: Workspace(Rejecting({})),
                           settings=settings_from_env(FULL))
    with pytest.raises(ToolError, match="Google rejected the request"):
        asyncio.run(server.call_tool("search_files", {"query": "not drive syntax"}))


def test_the_demo_sends_drive_syntax_not_free_text():
    """The step that got it wrong, pinned. `name contains '...'`, not the words alone."""
    steps = {s.tool: s for s in build("my-prefix", "f", "a@b.c", keep=True)}
    args = steps["search_files"].args({"prefix": "my-prefix"})
    assert args["query"] == "name contains 'my-prefix'"


class TestDiscoverableFromMcp:
    """Asked "do you have a demo or end-to-end tests to run?", a connected model answered NO.

    It was right: the demonstration was a CLI command, invisible from inside a session, which
    is the one place people actually ask. These pin the fix, and the thing the same session
    got right without being told - that a default profile cannot clear up after itself.
    """

    def plan(self, profile="editor"):
        server = create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env(
            {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
             "CSA_GW_PROFILE": profile}))
        return asyncio.run(server.call_tool("demonstration_plan", {})).structured_content

    def test_a_model_can_find_the_demonstration(self):
        out = self.plan()
        assert out["steps"], "no plan came back, so a model still has nothing to offer"
        assert out["unattended_command"].endswith("demo --auto")

    def test_the_instructions_point_at_it(self):
        """A tool nobody looks for is a tool nobody finds. The server has to volunteer it."""
        from csa_google_workspace.mcp.server import INSTRUCTIONS
        assert "demonstration_plan" in INSTRUCTIONS
        assert "demo" in INSTRUCTIONS.lower()

    def test_it_returns_a_plan_rather_than_running_anything(self):
        """Running 75 steps inside one call would block a conversation for minutes and would
        demonstrate nothing - the tool would have done the work, not the model."""
        before = self.plan()
        after = self.plan()
        assert before == after, "calling it twice changed something, so it is not inert"

    def test_it_says_the_files_are_real(self):
        assert self.plan()["creates_real_files"] is True

    def test_the_default_profile_can_now_clear_up_after_itself(self):
        """The inverse of the test this replaces, and the point of the v0.21.0 regrouping.

        `editor` used to lack `file.trash`, so a demonstration created real files in somebody's
        Drive with no way to remove them. Withholding a REVERSIBLE capability produced
        irreversible litter, which is the wrong trade: trash is a 30-day bin the owner
        controls, and files left behind are forever until a human notices them."""
        out = self.plan("editor")
        assert out["cleanup_possible"] is True
        assert not any("file.trash" in reason for reason in out["unavailable"])

    def test_a_default_profile_is_still_told_what_it_cannot_do(self):
        """Cleanup working does not mean nothing is refused - the default still declines the
        three that cannot be undone, and the plan says so before anything is created."""
        out = self.plan("editor")
        reasons = " ".join(out["unavailable"])
        assert "comment.edit" in reasons or "comment.delete" in reasons
        assert "file.share" in reasons

    def test_a_full_profile_has_nothing_to_warn_about(self):
        out = self.plan("full")
        assert out["cleanup_possible"] is True
        assert out["unavailable"] == []

    def test_gated_steps_are_marked_unavailable_individually(self):
        """So a walkthrough can skip precisely, rather than stopping at the first refusal."""
        out = self.plan("editor")
        blocked = [s for s in out["steps"] if not s["available"]]
        assert blocked
        # The default refuses exactly what cannot be undone. Named, rather than
        # checked with `<=`, because the previous version of this test would have passed on a
        # plan that predicted NOTHING - and that is what it was doing: before v0.21.0 most
        # gated steps carried no `requires` at all, so they were reported "available" and the
        # walkthrough discovered the refusal by hitting it.
        assert {s["tool"] for s in blocked} == {
            "edit_comment", "delete_comment",
            # All three share-shaped tools, because ungranting is the same authority as
            # granting: a profile that cannot share cannot un-share either. That is the right
            # pairing - a configuration able to revoke but not grant would be odd, and one able
            # to grant but not revoke is the state this library was in until #235.
            "share_file", "update_file_permission", "unshare_file",
            # The STRUCTURAL deletes, added in v0.36.0 with `content.delete`: an `editor` writes
            # cells, appends rows, inserts text and adds tabs, and is refused the operations that
            # remove a tab or a range - the things editing cannot reach.
            #
            # `clear_cells` WAS in this set and should not have been. It is gated `content.write`
            # in `policy._GATES`; `mcp/_capabilities.py` said `content.delete`, so the plan
            # predicted a refusal that would never happen - and this test, naming the set
            # explicitly, pinned the wrong prediction. Found as F1 by audit 2026-09-01-02.
            #
            # It stays `content.write` deliberately: withholding it would not prevent the
            # destruction (`update_cells` overwrites just as thoroughly) and would make somebody
            # write a placeholder that looks like data. See
            # tests/test_cell_destruction_is_content_write.py.
            "delete_range", "delete_tab", "delete_document_tab"}

    @pytest.mark.parametrize("profile,expected", [
        # `content.delete` joins each set in v0.36.0. The `editor` (=writer) row is refused the
        # STRUCTURAL deletes - removing a tab or a range - and NOT cell clearing, which is
        # `content.write`. The capability was split out for what editing cannot reach, not to
        # separate destructive from non-destructive: editing a spreadsheet is destructive too.
        ("reader", {"comment.create", "comment.reply", "comment.resolve", "comment.edit",
                    "comment.delete", "content.write", "content.delete", "file.create",
                    "file.update", "file.trash", "file.share"}),
        ("commenter", {"comment.edit", "comment.delete", "content.write", "content.delete",
                       "file.create", "file.update", "file.trash", "file.share"}),
        ("editor", {"comment.edit", "comment.delete", "content.delete", "file.share"}),
        ("full", set()),
    ])
    def test_the_plan_predicts_every_refusal_for_every_profile(self, profile, expected):
        """The property `demonstration_plan` exists for: say up front what will be skipped.

        It was quietly false for three of these four profiles. `requires` is now derived from
        the server's own tool->capability map rather than hand-annotated, so a gated step
        cannot be unannotated - which is what let a `reader` walk into sixteen unpredicted
        refusals one at a time."""
        out = self.plan(profile)
        named = {reason.split("needs the ")[1].split(" capability")[0]
                 for reason in out["unavailable"] if "needs the " in reason}
        assert named == expected

    def test_every_step_says_what_it_applies_to(self):
        """A model narrating "now the same thing on a Sheet" needs to know which is which."""
        out = self.plan("full")
        assert {s["applies_to"] for s in out["steps"]} >= {
            "account", "document", "spreadsheet", "presentation"}
