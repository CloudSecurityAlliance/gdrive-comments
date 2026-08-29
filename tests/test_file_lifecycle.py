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

    def test_share_is_on_by_default_and_off_below_organizer(self):
        """**REVERSED in v0.31.0.** The default used to refuse `share`; it now permits
        everything, and `file.share` was included deliberately after being argued about.

        The recoverability reasoning did not change and is not gone: a grant is revocable, a
        copy the recipient already took is not, so sharing cannot be undone in the sense that
        matters. That is why it sits on the **top rung** and why it is the first thing an
        operator narrowing this configuration removes — `writer` and `fileOrganizer` both
        refuse it, and this asserts both halves so the reversal cannot be read as the ladder
        collapsing too."""
        from csa_google_workspace.policy import PROFILES
        default = Workspace(PolicyBackend(FakeBackend(files()), Policy.default())).open(DOC)
        default.share("someone@example.com")     # permitted: nothing is off by default

        for profile in ("writer", "fileOrganizer"):
            narrowed = Workspace(PolicyBackend(
                FakeBackend(files()), Policy(enabled=PROFILES[profile]))).open(DOC)
            with pytest.raises(exc.ReadOnlyError):
                narrowed.share("someone@example.com")

    @pytest.mark.parametrize("action", ["rename", "trash"])
    def test_rename_and_trash_are_permitted_by_the_default_policy(self, action):
        """The other half of the v0.21.0 regrouping, asserted rather than implied.

        Both are reversible - a rename can be renamed back, and trash is a 30-day bin the
        file's owner can see and restore from - and withholding trash meant a deployment could
        create files and never tidy them, which left litter in real Drives. That was a worse
        outcome than the one the restriction protected against."""
        document = Workspace(PolicyBackend(FakeBackend(files()), Policy.default())).open(DOC)
        if action == "rename":
            document.rename("x")
        else:
            document.trash()

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


class TestDeletedCommentVisibility:
    """A successful delete used to report failure, and every unit test passed.

    `delete_comment` deletes, then re-fetches so the caller sees what Drive now holds. Drive
    404s a soft-deleted comment unless `includeDeleted` is set, so the re-fetch failed and the
    tool reported "Comment not found" for a comment it had just successfully deleted.

    It survived because `FakeBackend.get_comment` returned deleted comments happily — more
    forgiving than Drive, and therefore useless as a check. The fake now behaves as Drive does,
    which is what makes these tests able to fail.

    Found by running the demonstration against real Google. Nothing offline could have.
    """

    def _doc(self):
        backend = FakeBackend({DOC: {"id": DOC, "name": "D",
                                     "mimeType": "application/vnd.google-apps.document"}})
        return Workspace(backend).open(DOC)

    def test_a_deleted_comment_is_hidden_from_get_by_default(self):
        document = self._doc()
        comment = document.create_comment("bye")
        comment.delete()
        with pytest.raises(exc.NotFoundError):
            document.comments.get(comment.id)

    def test_and_reachable_when_asked_for(self):
        document = self._doc()
        comment = document.create_comment("bye")
        comment.delete()
        fetched = document.comments.get(comment.id, include_deleted=True)
        assert fetched.id == comment.id
        # Drive strips both, which is why the models allow both to be absent.
        assert fetched.content is None
        assert fetched.author is None

    def test_the_tool_reports_the_deletion_rather_than_failing(self):
        """The regression itself, at the layer that had it."""
        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                      "CSA_GW_ALLOWLIST_MODIFY": "*",
                                      "CSA_GW_PROFILE": "full"})
        backend = FakeBackend({DOC: {"id": DOC, "name": "D",
                                     "mimeType": "application/vnd.google-apps.document"}})
        server = create_server(lambda: Workspace(backend), settings=settings)
        made = asyncio.run(server.call_tool(
            "create_comment", {"fileId": DOC, "content": "bye"})).structured_content
        comment_id = made.get("commentId") or made["id"]
        out = asyncio.run(server.call_tool(
            "delete_comment", {"fileId": DOC, "commentId": comment_id})).structured_content
        assert out["id"] == comment_id
        assert out["content"] is None


class TestFromTheEndToEndReport:
    """Two findings from a real run against Google, both about saying the true thing.

    Neither was a crash. Both were a tool reporting something a person would repeat back
    incorrectly, which is the failure mode that survives a green test suite.
    """

    def _sheet(self):
        backend = FakeBackend(
            {DOC: {"id": DOC, "name": "S",
                   "mimeType": "application/vnd.google-apps.spreadsheet"}},
            spreadsheets={DOC: {"sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}]}})
        settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                      "CSA_GW_ALLOWLIST_MODIFY": "*",
                                      "CSA_GW_PROFILE": "full"})
        return create_server(lambda: Workspace(backend), settings=settings)

    def test_the_requested_cell_comes_back_as_linked_cell(self):
        """The report's finding: it asked for B2 and the response said cell=A1.

        A1 is TRUE - Drive anchors an API-created comment there, confirmed by reading the
        anchor out of the XLSX - so the fix is not to lie about `cell` but to also return the
        cell the link points at, which is what a user actually asked about.
        """
        out = asyncio.run(self._sheet().call_tool(
            "create_comment", {"fileId": DOC, "content": "about B2", "cell": "B2"}
        )).structured_content
        assert out["linked_cell"] == "B2"
        assert "range=B2" in out["content"]

    def test_a_comment_with_no_link_has_no_linked_cell(self):
        out = asyncio.run(self._sheet().call_tool(
            "create_comment", {"fileId": DOC, "content": "plain"})).structured_content
        assert out["linked_cell"] is None

    def test_create_comment_says_which_cell_to_quote(self):
        """The description has to resolve the ambiguity, because the data alone cannot."""
        tools = {t.name: (t.description or "")
                 for t in asyncio.run(self._sheet().list_tools())}
        text = tools["create_comment"]
        assert "linked_cell" in text and "quote this" in text
        assert "A1" in text, "it has to say where Drive actually files it"

    def test_a_deleted_thread_is_findable_with_include_deleted(self):
        """The audit finding: a deleted top-level thread vanished from both listing and
        lookup, so "was there ever a comment here?" had no answer through the tool surface."""
        server = self._sheet()
        made = asyncio.run(server.call_tool(
            "create_comment", {"fileId": DOC, "content": "bye"})).structured_content
        comment_id = made.get("commentId") or made["id"]
        asyncio.run(server.call_tool("delete_comment",
                                     {"fileId": DOC, "commentId": comment_id}))

        listed = asyncio.run(server.call_tool(
            "list_comments", {"fileId": DOC})).structured_content["comments"]
        assert listed == [], "deleted threads should be absent by default, as Drive has them"

        with_deleted = asyncio.run(server.call_tool(
            "list_comments", {"fileId": DOC, "includeDeleted": True})
        ).structured_content["comments"]
        assert [c["id"] for c in with_deleted] == [comment_id]
        assert with_deleted[0]["content"] is None
        assert with_deleted[0]["author"] is None

        fetched = asyncio.run(server.call_tool(
            "get_comment", {"fileId": DOC, "commentId": comment_id, "includeDeleted": True})
        ).structured_content
        assert fetched["id"] == comment_id

    def test_list_comments_no_longer_claims_deleted_ones_are_shown(self):
        """The doc said a deleted comment "keeps its place in the thread". True with the flag,
        false without it - and it was written without the flag existing."""
        tools = {t.name: (t.description or "")
                 for t in asyncio.run(self._sheet().list_tools())}
        assert "ABSENT unless you pass `includeDeleted`" in tools["list_comments"]


class TestTheApiReviewFindings:
    """Three things the v0.21.0 pre-1.0.0 API review found, each pinned so it cannot come back.

    The review existed because the MCP tool surface is the contract this project actually has
    to keep - a wire name, a parameter, a result field - and pre-1.0.0 is the only moment any
    of it is free to change. Two of the three were defects rather than preferences.
    """

    def _server(self):
        from csa_google_workspace.mcp import settings_from_env
        from csa_google_workspace.mcp.server import create_server
        backend = FakeBackend(
            {DOC: {"id": DOC, "name": "D", "mimeType": "application/vnd.google-apps.document",
              "parents": ["FOLDER1"]},
             "FOLDER2": {"id": "FOLDER2", "name": "F2",
                         "mimeType": "application/vnd.google-apps.folder"}},
            permissions={DOC: [{"id": "p1", "type": "user", "role": "writer",
                                "emailAddress": "a@b.com"}]})
        return create_server(lambda: Workspace(backend), settings=settings_from_env(
            {"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
             "CSA_GW_PROFILE": "full"}))

    def _call(self, name, args):
        import asyncio
        return asyncio.run(self._server().call_tool(name, args)).structured_content

    def test_update_file_reports_the_parents_the_file_actually_has(self):
        """It returned a hard-coded `[]` until v0.21.0.

        Not a missing answer - a WRONG one, and one that looked like "the file is nowhere",
        which is not a state Drive has. Google was returning the parents all along and the
        library layer was discarding them.
        """
        out = self._call("update_file", {"fileId": DOC, "parentId": "FOLDER2",
                                         "removeParentId": "FOLDER1"})
        assert out["parents"] == ["FOLDER2"]

    def test_a_search_hit_does_not_claim_to_know_the_parents(self):
        """`None` (not asked) and `()` (genuinely none) are different answers.

        `search_files` does not request parents, so a hit reporting an empty list would be
        asserting a fact it never checked - the same missing-vs-empty conflation that made a
        cell-map warning fire on correct behaviour, and that ZERO-DEFECT #17 is about.
        """
        space = workspace()
        space.files.create("New", "document")
        hits = space.files.search("name contains 'New'")
        assert hits and all(hit.parents is None for hit in hits)

    def test_a_permission_does_not_call_its_grantee_kind_type(self):
        """`type` means the DOCUMENT kind everywhere else in this surface - document,
        spreadsheet, presentation - and a model reads these outputs interleaved. One field
        name carrying two unrelated vocabularies is a misreading waiting to happen."""
        permissions = self._call("get_file_permissions", {"fileId": DOC})["permissions"]
        assert permissions[0]["grantee_type"] == "user"
        assert "type" not in permissions[0]
