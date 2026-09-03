"""Five small defects from the 2026-09-02 review, each a guard that did not guard.

They are together in one file because they share a shape rather than a subsystem: in every
case something WAS being checked, and the check was one step away from the thing that
mattered. That is worth keeping visible as a set — a missing guard gets noticed, a guard
aimed slightly wrong reads as covered.

  * **#327** — `has_write_scope` asked *"is one of OUR four write scopes present?"*, which is a
    denylist. Now: *"is everything present inside the read-only set?"*
  * **#326** — every tool returned third-party content and none of them said so.
  * **#315** — the startup notice had a branch for a profile and a branch for an overridden
    profile, and none for the default install that most people run.
  * **#313** — the refusal log recorded the exception MESSAGE, which carries tab titles.
  * **#314** — the register reader checked whether the path was a file BEFORE checking whether
    reading local files was switched off at all.
"""
from __future__ import annotations

import asyncio
import logging

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace, auth, exceptions
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import settings_from_env, startup_warnings
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import IRREVERSIBLE

DOC = "application/vnd.google-apps.document"
FILES = {"f": {"id": "f", "name": "Draft", "mimeType": DOC,
               "webViewLink": "https://x/document/d/f/edit"}}


def build(**kw):
    ws = Workspace(FakeBackend(FILES), **kw)
    return create_server(lambda: ws)


def local_reads_off():
    """A server configured the way `CSA_GW_LOCAL_READ=0` configures one."""
    settings = settings_from_env({"CSA_GW_LOCAL_READ": "0"})
    assert settings.local_read is False, "the premise of these tests"
    return create_server(lambda: Workspace(FakeBackend(FILES)), settings=settings)


# --- #327: a subset check, not a list of the write scopes we happen to know ------------

class TestWriteScopeDetectionIsASubsetCheck:
    """The regression this closes is a scope Google has that this project does not request."""

    def test_the_readonly_set_itself_carries_no_write_scope(self):
        assert auth.has_write_scope(list(auth.scopes_for(read_only=True))) is False

    def test_our_own_write_scopes_are_still_detected(self):
        for scope in auth.scopes_for(read_only=False):
            if scope not in set(auth.scopes_for(read_only=True)):
                assert auth.has_write_scope([scope]) is True, scope

    @pytest.mark.parametrize("stranger", [
        # The one that broke it: a REAL Drive write scope this project never asks for, so it
        # was on no list and answered False. `drive.file` grants create-and-modify on files
        # the app touches - narrower than `drive`, and not remotely read-only.
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive.appdata",
        "https://www.googleapis.com/auth/drive.metadata",
        "https://www.googleapis.com/auth/spreadsheets.currentonly",
        # Not a Google scope at all. Whatever it is, it is not in the read-only set.
        "https://example.invalid/auth/anything",
    ])
    def test_a_scope_we_never_request_is_treated_as_a_write_scope(self, stranger):
        assert auth.has_write_scope([stranger]) is True
        # And it is not rescued by good company.
        assert auth.has_write_scope([*auth.scopes_for(read_only=True), stranger]) is True

    def test_a_readonly_lookalike_is_not_trusted_for_its_suffix(self):
        # `.readonly` in the string is not the test - membership is. A scope for a service
        # this project does not use is outside the set even when it cannot write.
        assert auth.has_write_scope(
            ["https://www.googleapis.com/auth/gmail.readonly"]) is True

    @pytest.mark.parametrize("nothing", [[], None])
    def test_no_scopes_reported_answers_conservatively(self, nothing):
        # Absence is not a licence. `granted` is empty on some refresh paths, and "no write
        # scopes were listed" must not read as "this token cannot write".
        assert auth.has_write_scope(nothing) is True


# --- #326: the annotation that says the result came from somewhere else -----------------

class TestEveryToolIsMarkedOpenWorld:
    def test_no_tool_omits_open_world_hint(self):
        tools = asyncio.run(build().list_tools())
        assert tools, "an empty tool list would pass every assertion below"
        missing = [t.name for t in tools if not t.annotations.open_world_hint]
        assert missing == [], missing

    def test_it_is_on_the_writes_too(self):
        by_name = {t.name: t for t in asyncio.run(build().list_tools())}
        for name in ("create_comment", "replace_text", "trash_file"):
            assert by_name[name].annotations.open_world_hint is True, name
            assert by_name[name].annotations.read_only_hint is False, name


# --- #315: the default install is told what is on ---------------------------------------

class TestTheDefaultInstallIsToldWhatIsEnabled:
    def notice(self, env=None):
        return startup_warnings(settings_from_env(env or {}))

    def test_a_default_install_gets_a_capability_line(self):
        settings = settings_from_env({})
        assert settings.capability_source == "default", "the premise of this test"
        assert any("capabilities" in line for line in startup_warnings(settings))

    def test_it_names_every_enabled_capability_rather_than_counting_them(self):
        text = "\n".join(self.notice())
        enabled = settings_from_env({}).policy.enabled
        assert enabled, "an empty capability set would make the loop below vacuous"
        for capability in enabled:
            assert capability in text, capability

    def test_the_irreversible_ones_are_called_out_separately(self):
        text = "\n".join(self.notice())
        assert "CANNOT BE UNDONE" in text
        for capability in IRREVERSIBLE:
            assert capability in text, capability

    def test_a_narrowed_install_does_not_get_the_default_line(self):
        # The line says "ALL … by default". Saying it when the operator narrowed the set
        # would be the RR-003 failure again: reporting a posture that is not in force.
        for env in ({"CSA_GW_PROFILE": "commenter"},
                    {"CSA_GW_CAPABILITIES": "comment.reply"}):
            text = "\n".join(self.notice(env))
            assert "by default" not in text, env


# --- #313: a refusal is logged by TYPE, never by message --------------------------------

class TestARefusalLogsNoMessage:
    def test_the_message_does_not_reach_the_log_even_at_debug(self, caplog):
        # A tab name is document content, and the library's own refusal quotes the tabs it
        # found. The caller needs that; a log directory under someone else's retention
        # does not.
        secret = "Q3 Layoff Plan"

        class Boom(FakeBackend):
            def get_values(self, *a, **k):
                raise exceptions.NotFoundError(f"no tab named 'x'. present: ['{secret}']")

        server = create_server(lambda: Workspace(Boom(
            {"s": {"id": "s", "name": "Grid",
                   "mimeType": "application/vnd.google-apps.spreadsheet"}})))
        with caplog.at_level(logging.DEBUG, logger="csa_google_workspace.mcp"):
            with pytest.raises(ToolError) as caught:
                asyncio.run(server.call_tool(
                    "read_range", {"fileId": "s", "a1Range": "x!A1"}))

        assert secret in str(caught.value), "the CALLER keeps the full message"
        assert secret not in caplog.text, "the LOG must not"
        assert "NotFoundError" in caplog.text, "and must still say what happened"

    def test_an_unexpected_failure_logs_its_type_and_not_its_message(self, caplog):
        secret = "s3cret-tab-name"

        class Boom(FakeBackend):
            def get_values(self, *a, **k):
                raise RuntimeError(secret)

        server = create_server(lambda: Workspace(Boom(
            {"s": {"id": "s", "name": "Grid",
                   "mimeType": "application/vnd.google-apps.spreadsheet"}})))
        with caplog.at_level(logging.DEBUG, logger="csa_google_workspace.mcp"):
            # A ToolError either way - the SDK wraps an unhandled exception before it
            # leaves the handler. What is under test is the LOG, not the class.
            with pytest.raises(ToolError):
                asyncio.run(server.call_tool(
                    "read_range", {"fileId": "s", "a1Range": "A1"}))
        assert secret not in caplog.text
        assert "RuntimeError" in caplog.text

    def test_a_conflict_reaches_the_caller_with_its_message(self):
        # Not on the translated ladder before this change, so it fell through to the generic
        # handler and the SDK suppressed the text: the caller read "Error executing tool
        # add_tab" and learned nothing. A security fix that also fixed a usability bug.
        class Taken(FakeBackend):
            def sheets_add_tab(self, *a, **k):
                raise exceptions.ConflictError("a tab named 'Comp Bands' already exists")

        server = create_server(lambda: Workspace(Taken(
            {"s": {"id": "s", "name": "Grid",
                   "mimeType": "application/vnd.google-apps.spreadsheet"}},
            spreadsheets={"s": {"sheets": [
                {"properties": {"sheetId": 0, "title": "Sheet1"}}]}})))
        with pytest.raises(ToolError) as caught:
            asyncio.run(server.call_tool("add_tab", {"fileId": "s", "name": "Comp Bands"}))
        assert "already exists" in str(caught.value)


# --- #314: the switch is checked before the filesystem is touched -----------------------

class TestTheLocalReadSwitchIsCheckedFirst:
    """With local reads off, the refusal must not depend on what is on disk.

    `is_file()` first made the tool an existence oracle for any path `expanduser()` can
    reach - inside the switch whose stated purpose is to remove local exposure.
    """

    @pytest.mark.parametrize("path", [
        "~/.ssh/id_rsa",                 # exists on a developer's machine
        "/etc/hosts",                    # exists everywhere
        "/definitely/not/here/xyz.csv",  # exists nowhere
        "/etc",                          # exists, and is not a file
    ])
    def test_the_refusal_is_identical_whatever_is_there(self, path):
        server = local_reads_off()
        with pytest.raises(ToolError) as caught:
            asyncio.run(server.call_tool(
                "apply_comment_actions", {"fileId": "f", "path": path}))
        message = str(caught.value)
        assert "CSA_GW_LOCAL_READ" in message
        assert path not in message, "echoing the probe back is the oracle in smaller form"
        assert "is not a file" not in message

    def test_the_refusals_do_not_differ_between_an_existing_and_a_missing_path(self):
        server = local_reads_off()

        def refusal(path):
            with pytest.raises(ToolError) as caught:
                asyncio.run(server.call_tool(
                    "apply_comment_actions", {"fileId": "f", "path": path}))
            return str(caught.value)

        assert refusal("/etc/hosts") == refusal("/definitely/not/here/xyz.csv")
