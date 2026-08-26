"""Rename, move, trash and share — and the bounds that make them safe to expose.

These are the three operations this server deliberately shipped last. They are the only ones
that can damage or leak something that already exists, so most of what is worth testing is
what they REFUSE: disabled by default, gated per file, no ownership transfer, no permanent
delete. A capability that is on when nobody enabled it is the whole failure mode.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import Policy, PolicyBackend

# A real-shaped id: the allowlist rejects short or placeholder-looking ones, which is a
# feature - it is what catches a URL somebody typed from memory - and means fixtures have to
# look like the real thing.
DOC = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
OTHER = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"
DOC_URL = f"https://docs.google.com/document/d/{DOC}/edit"


def files():
    return {DOC: {"id": DOC, "name": "Original", "parents": ["folderA"],
                  "mimeType": "application/vnd.google-apps.document"}}


def workspace(*, capabilities: str = "all", modify: str = "*") -> Workspace:
    from csa_google_workspace.mcp._config import policy_from_env
    policy = policy_from_env({"CSA_GW_CAPABILITIES": capabilities,
                              "CSA_GW_ALLOWLIST_READ": "*",
                              "CSA_GW_ALLOWLIST_MODIFY": modify})
    return Workspace(PolicyBackend(FakeBackend(files()), policy))


class TestTheLibrary:
    def test_rename_changes_the_name(self):
        document = workspace().open(DOC)
        assert document.rename("Renamed")["name"] == "Renamed"

    def test_rename_refuses_an_empty_name(self):
        """Drive would accept it and leave a file nobody can find in a list."""
        with pytest.raises(ValueError):
            workspace().open(DOC).rename("   ")

    def test_move_without_a_source_adds_a_parent(self):
        """Drive has no "move" - it edits a parent list. A file in two folders is a real Drive
        state, so adding is the honest default and removing is opt-in."""
        result = workspace().open(DOC).move("folderB")
        assert set(result["parents"]) == {"folderA", "folderB"}

    def test_move_with_a_source_relocates(self):
        result = workspace().open(DOC).move("folderB", from_parent_id="folderA")
        assert result["parents"] == ["folderB"]

    def test_trash_is_reversible(self):
        """30 days, and the user can restore it themselves. There is no permanent delete
        anywhere in this library, deliberately."""
        document = workspace().open(DOC)
        assert document.trash()["trashed"] is True
        assert document.untrash()["trashed"] is False

    def test_share_grants_a_role(self):
        permission = workspace().open(DOC).share("someone@example.com", "writer")
        assert permission.role == "writer"
        assert permission.email == "someone@example.com"

    def test_share_refuses_ownership_transfer(self):
        """A different act from sharing: it needs Drive's transferOwnership flag, can leave the
        current owner unable to undo it, and on some account types cannot be reversed. Refusing
        it means a model cannot give a document away by picking a plausible-looking role."""
        with pytest.raises(ValueError, match="ownership"):
            workspace().open(DOC).share("someone@example.com", "owner")

    def test_share_refuses_something_that_is_not_an_address(self):
        with pytest.raises(ValueError):
            workspace().open(DOC).share("not-an-address", "reader")

    def test_share_refuses_an_unknown_role(self):
        with pytest.raises(ValueError, match="unknown role"):
            workspace().open(DOC).share("someone@example.com", "editor")


class TestTheBounds:
    """Two independent gates, and neither can be widened from inside."""

    @pytest.mark.parametrize("action", ["rename", "trash", "share"])
    def test_each_is_off_under_the_default_policy(self, action):
        """The default enables comment and content writes and nothing else. Somebody has to ask
        for these three by name."""
        document = Workspace(PolicyBackend(FakeBackend(files()), Policy.default())).open(DOC)
        with pytest.raises(exc.ReadOnlyError):
            if action == "rename":
                document.rename("x")
            elif action == "trash":
                document.trash()
            else:
                document.share("someone@example.com")

    @pytest.mark.parametrize("action", ["rename", "trash", "share"])
    def test_each_is_refused_for_a_file_outside_the_modify_allowlist(self, action):
        """The capability says WHAT may be done; the allowlist says to WHICH FILE. Enabling the
        capability alone is not enough, which is the point of having two."""
        space = workspace(modify=f"https://docs.google.com/document/d/{OTHER}/edit")
        document = space.open(DOC)
        with pytest.raises(exc.ReadOnlyError):
            if action == "rename":
                document.rename("x")
            elif action == "trash":
                document.trash()
            else:
                document.share("someone@example.com")

    def test_a_narrower_capability_set_still_blocks_the_others(self):
        """file.update on its own does not bring trash or share with it."""
        space = workspace(capabilities="file.update")
        document = space.open(DOC)
        assert document.rename("fine")["name"] == "fine"
        with pytest.raises(exc.ReadOnlyError):
            document.trash()
        with pytest.raises(exc.ReadOnlyError):
            document.share("someone@example.com")


class TestTheTools:
    def server(self, **env):
        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                      "CSA_GW_ALLOWLIST_MODIFY": DOC_URL,
                                      "CSA_GW_PROFILE": "full", **env})
        backend = FakeBackend(files())
        return create_server(lambda: Workspace(backend), settings=settings)

    def call(self, name, args, **env):
        return asyncio.run(self.server(**env).call_tool(name, args)).structured_content

    def test_update_file_renames(self):
        assert self.call("update_file", {"fileId": DOC, "name": "New"})["name"] == "New"

    def test_update_file_with_nothing_to_do_says_so(self):
        """Rather than reporting success for a call that changed nothing - which reads, to a
        model, as confirmation that the rename it meant to request went through."""
        from mcp.server.mcpserver.exceptions import ToolError
        with pytest.raises(ToolError, match="nothing to change"):
            self.call("update_file", {"fileId": DOC})

    def test_trash_and_untrash_use_one_tool(self):
        assert self.call("trash_file", {"fileId": DOC})["trashed"] is True
        assert self.call("trash_file", {"fileId": DOC, "untrash": True})["trashed"] is False

    def test_share_file_returns_the_grant(self):
        out = self.call("share_file", {"fileId": DOC, "emailAddress": "a@b.com",
                                       "role": "commenter"})
        assert out["role"] == "commenter" and out["email"] == "a@b.com"

    def test_the_destructive_ones_are_annotated_as_destructive(self):
        """Clients use this to decide whether to confirm with the user, so an unmarked
        `trash_file` is a file trashed without anybody being asked."""
        tools = {t.name: t.annotations for t in asyncio.run(self.server().list_tools())}
        for name in ("trash_file", "share_file"):
            assert tools[name].destructive_hint is True, name
        # A rename is disruptive rather than destructive: nothing is lost, and marking
        # everything destructive is how a confirmation prompt stops being read.
        assert tools["update_file"].destructive_hint is False

    def test_the_tools_say_the_capability_is_off_by_default(self):
        """The description is where a model learns why a refusal happened, and what the user
        would have to change - which is the difference between reporting and retrying."""
        tools = {t.name: (t.description or "") for t in asyncio.run(self.server().list_tools())}
        for name in ("update_file", "trash_file", "share_file"):
            assert "off unless an operator" in tools[name], name

    def test_share_file_warns_that_it_sends_data_outside(self):
        tools = {t.name: (t.description or "") for t in asyncio.run(self.server().list_tools())}
        assert "OUT OF THE ORGANISATION" in tools["share_file"]
