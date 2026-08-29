"""A grant can be taken back — and the mutating capability that makes the surface *safer*.

**#235.** `Backend` had `list_permissions` and `create_permission` and nothing else, so this
library could **grant** a permission and could not take one back. An operator who discovered a
wrong share had to leave the tool and go to the Drive UI.

That mattered more once `file.share` landed in the default capability set: the one action whose
effect leaves the organisation was the one action with no undo *here*.

**What is and is not fixed.** `PROVENANCE.md` rates sharing *irreversible in effect*, and that
has two halves:

* **Google's half** — a copy the recipient already took is not recalled, and no notification is
  sent when access is removed. Unfixable, and unchanged by this.
* **Ours** — the grant itself is perfectly revocable in Drive and we had no method for it. That
  is what closes here.

The distinction is load-bearing when reporting a revocation, so the tool description carries it
and `test_the_tool_says_what_revocation_does_not_undo` keeps it there. "Access has been revoked"
alone implies more than happened.

**Same capability as granting**, deliberately. Splitting them would allow a configuration that
can share and cannot un-share — strictly worse than either extreme, and exactly the state this
library was in until now.
"""
from __future__ import annotations

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.exceptions import NotFoundError
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import _GATES, FILE_SHARE, PolicyBackend

DOC = "doc1"
MIME = "application/vnd.google-apps.document"


def workspace(**kw):
    return Workspace(FakeBackend(
        {DOC: {"id": DOC, "name": "A Doc", "mimeType": MIME}},
        permissions={DOC: [{"id": "p1", "type": "user", "role": "writer",
                            "emailAddress": "a@example.com"},
                           {"id": "p2", "type": "user", "role": "reader",
                            "emailAddress": "b@example.com"}]}, **kw))


def server(profile="full"):
    """The Workspace is wrapped in `PolicyBackend` here, and that is not incidental.

    `create_server(lambda: Workspace(FakeBackend(...)))` enforces **nothing** — the provider
    hands over a Workspace and the server uses it as given. That is the DI seam working as
    designed: an embedder supplying their own backend supplies their own gating. Production
    wraps it at `mcp/_config.py`, where `Workspace.from_credentials(..., policy=...)` applies
    `PolicyBackend`.

    A first draft of these tests skipped the wrapper and concluded the capability gate was
    broken, because `share_file` succeeded under `editor` too. It was the test that was wrong.
    Worth the note: a refusal test that silently exercises an ungated backend passes for the
    wrong reason on the day the gate stops working.
    """
    settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                                  "CSA_GW_PROFILE": profile})
    ws = Workspace(PolicyBackend(workspace()._backend, settings.policy))
    return create_server(lambda: ws, settings=settings), ws


class TestRevoking:
    def test_the_grant_is_gone(self):
        ws = workspace()
        doc = ws.open(DOC)
        assert {p.id for p in doc.permissions} == {"p1", "p2"}
        doc.unshare("p1")
        assert {p.id for p in doc.permissions} == {"p2"}

    def test_revoking_one_leaves_the_others(self):
        """The failure that would be silent and expensive: removing more than asked."""
        ws = workspace()
        doc = ws.open(DOC)
        doc.unshare("p1")
        remaining = doc.permissions
        assert len(remaining) == 1 and remaining[0].email == "b@example.com"

    def test_an_unknown_permission_id_is_a_clear_error(self):
        """A permission id is opaque, so a wrong one is easy to produce. It must not silently
        succeed, or a caller believes access was removed when it was not."""
        doc = workspace().open(DOC)
        with pytest.raises(NotFoundError):
            doc.unshare("nope")

    def test_it_is_refused_on_an_unknown_file(self):
        doc = workspace().open(DOC)
        doc.id = "missing"
        with pytest.raises(NotFoundError):
            doc.unshare("p1")


class TestDowngrading:
    """Usually the better answer than revoking: the person keeps seeing work they may be
    part-way through, and stops being able to change it."""

    def test_the_role_changes_and_nothing_else_does(self):
        ws = workspace()
        doc = ws.open(DOC)
        result = doc.set_role("p1", "reader")
        assert result.role == "reader"
        assert result.email == "a@example.com", "the grant's subject must not change"
        assert {p.id for p in doc.permissions} == {"p1", "p2"}, "nobody was removed"

    def test_can_write_follows_the_new_role(self):
        """`can_write` is what a caller checks; a downgrade that left it true would be worse
        than no downgrade, because it reads as done."""
        doc = workspace().open(DOC)
        assert doc.permissions[0].can_write
        assert not doc.set_role("p1", "reader").can_write

    @pytest.mark.parametrize("role", ["owner", "wri ter", "editor", ""])
    def test_a_role_that_is_not_drives_vocabulary_is_refused(self, role):
        """`editor` is the trap: it is Google's UI label for `writer`, so it looks right and is
        not a valid API value. Caught here rather than as a 400 from Google."""
        doc = workspace().open(DOC)
        with pytest.raises(ValueError):
            doc.set_role("p1", role)

    def test_ownership_transfer_is_refused_by_name(self):
        """Same reasoning as `share()`: transfer needs a different API flag and is not
        reversible on every account type. A model must not give a document away by choosing a
        plausible-looking role."""
        doc = workspace().open(DOC)
        with pytest.raises(ValueError, match="(?i)ownership"):
            doc.set_role("p1", "owner")


class TestItIsTheSameAuthorityAsGranting:
    """Not a new capability. A configuration that can share and cannot un-share is strictly
    worse than either extreme, and is where this library was until #235."""

    @pytest.mark.parametrize("method", ["create_permission", "update_permission",
                                        "delete_permission"])
    def test_all_three_are_gated_by_file_share(self, method):
        assert _GATES[method].capability == FILE_SHARE

    @pytest.mark.parametrize("tool", ["update_file_permission", "unshare_file"])
    def test_the_tools_are_refused_without_the_capability(self, tool):
        """`editor` grants everything reversible and not `file.share`."""
        app, _ = server("editor")
        args = {"fileId": DOC, "permissionId": "p1"}
        if tool == "update_file_permission":
            args["role"] = "reader"
        # ToolError, not a bare Exception: the SDK wraps a plain exception as
        # UnexpectedToolError with the message suppressed, so a refusal that arrives that way
        # tells the operator nothing about which capability is off.
        with pytest.raises(ToolError):
            asyncio.run(app.call_tool(tool, args))

    @pytest.mark.parametrize("tool", ["update_file_permission", "unshare_file"])
    def test_and_permitted_with_it(self, tool):
        app, _ = server("full")
        args = {"fileId": DOC, "permissionId": "p1"}
        if tool == "update_file_permission":
            args["role"] = "reader"
        asyncio.run(app.call_tool(tool, args))


class TestTheToolsSayWhatTheyDo:
    def test_the_tool_says_what_revocation_does_not_undo(self):
        """The half that stays broken has to be stated, or a model reports "access has been
        revoked" and implies the copy is gone too."""
        app, _ = server()
        described = {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}
        text = described["unshare_file"]
        assert "not recalled" in text or "NOT recalled" in text
        assert "no notification" in text

    def test_it_tells_the_caller_to_confirm_who(self):
        """A permission id is not human-readable, so picking the wrong one silently removes the
        wrong person - the failure a model cannot detect afterwards."""
        app, _ = server()
        described = {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}
        assert "get_file_permissions" in described["unshare_file"]
        assert "confirm" in described["unshare_file"].lower()

    def test_downgrading_is_offered_as_the_gentler_option(self):
        app, _ = server()
        described = {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}
        assert "update_file_permission" in described["unshare_file"]

    def test_revoking_is_annotated_destructive_and_downgrading_is_not(self):
        """Removing access is destructive; changing a role is a write. A client set to prompt
        on destructive actions should stop on one and not the other."""
        app, _ = server()
        annotations = {t.name: t.annotations for t in asyncio.run(app.list_tools())}
        assert annotations["unshare_file"].destructive_hint is True
        assert annotations["update_file_permission"].destructive_hint is False
