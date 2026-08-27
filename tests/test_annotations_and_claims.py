"""Annotations must match what a tool does, and the instructions must not invent controls.

Two structural guards, both from #184, both catching a class rather than an instance.

**Annotations drive the client's approval decision.** The MCP spec maps `readOnlyHint: true` to
*"skip the confirmation dialog"* and `idempotentHint: true` to *"safe to retry"* **for a trusted
server** — which a locally-installed stdio server is. `export_comments` carried `READ`
(`read_only_hint=True, destructive_hint=False, idempotent_hint=True`) while writing a file to a
model-chosen absolute path, creating Drive files, and appending `-TIMESTAMP` rather than
overwriting, so a retry makes a *second* file. All three fields were false, in the permissive
direction.

**And the server told the model about a control that did not exist.** `INSTRUCTIONS` said
`destination="file"` works *"only if the operator enabled it"*. There is no such enablement:
`ALL_CAPABILITIES` is ten Drive-side names and none of them gates a filesystem write, so
`PROFILE=reader` with `READ_ONLY=1` and both allowlists empty still left the path live.

That is worse than a missing feature. A model reading it will reason that the path is gated, and
so will an operator reading it in `describe_configuration` — an imaginary control is more
dangerous than an absent one, because it stops people looking for the real gap.

The lesson these two share with #181 is the reason they are guarded structurally rather than
fixed and forgotten: **a claim about behaviour, made anywhere other than in the behaviour, drifts
from it.** `CLAUDE.md` invariant 10 puts it as *a type is not a contract with the model; the
description is.*
"""
from __future__ import annotations

import asyncio
import re

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import INSTRUCTIONS, create_server
from csa_google_workspace.policy import ALL_CAPABILITIES, PolicyBackend

# Hand-written on purpose. Deriving it from the code would test the code against itself; the
# question "does this tool touch the filesystem or create a file?" is one a person answers by
# reading it, and a new tool belongs on this list by a deliberate act.
TOUCHES_STORAGE = {
    "export_comments",        # destination="file"/"xlsx" write a path; "sheet" creates a Drive file
    "apply_comment_actions",  # rewrites the register in place
    "create_file", "copy_file", "update_file", "trash_file", "share_file",
    "replace_text", "append_text", "insert_slide_text", "update_cells", "append_rows",
    "authenticate",           # writes the token cache
}


@pytest.fixture
def tools():
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                            "CSA_GW_PROFILE": "full"})
    app = create_server(lambda: Workspace(PolicyBackend(FakeBackend({}), st.policy)),
                        settings=st)
    return {t.name: t for t in asyncio.run(app.list_tools())}


class TestNothingThatWritesClaimsToBeReadOnly:
    def test_no_storage_tool_is_annotated_read_only(self, tools):
        offenders = [
            name for name in TOUCHES_STORAGE
            if name in tools and getattr(tools[name].annotations, "read_only_hint", False)]
        assert offenders == [], (
            f"annotated read-only while writing: {sorted(offenders)}. The spec maps "
            f"readOnlyHint to 'skip the confirmation dialog' for a trusted server, so this "
            f"suppresses the client's approval prompt.")

    def test_no_storage_tool_claims_to_be_idempotent(self, tools):
        """A retry that creates a second file is not a retry."""
        offenders = [
            name for name in TOUCHES_STORAGE
            if name in tools and getattr(tools[name].annotations, "idempotent_hint", False)]
        assert offenders == [], f"annotated idempotent while writing: {sorted(offenders)}"

    def test_the_list_is_still_current(self, tools):
        """If a name on the list disappears, the list is stale and silently checking nothing."""
        gone = sorted(TOUCHES_STORAGE - set(tools))
        assert gone == [], (
            f"TOUCHES_STORAGE names tools that no longer exist: {gone}. Renamed or removed - "
            f"either way the guard above stopped covering them.")

    def test_a_genuinely_read_only_tool_is_still_annotated_read_only(self, tools):
        """The counterweight: broadening WRITE until it means nothing would also pass the
        assertions above."""
        for name in ("list_comments", "get_comment", "read_file_content", "search_files"):
            assert tools[name].annotations.read_only_hint is True, (
                f"{name} reads and should say so, or the annotation carries no information")


class TestTheInstructionsDoNotInventControls:
    CAPABILITY_SHAPED = re.compile(r"\b([a-z]+\.[a-z_]+)\b")

    def test_every_capability_named_in_the_instructions_exists(self):
        named = set(self.CAPABILITY_SHAPED.findall(INSTRUCTIONS))
        # `foo.bar`-shaped tokens that are not capabilities: filenames, hostnames, mime types.
        plausible = {t for t in named if t.split(".")[0] in
                     {"comment", "content", "file", "export", "account", "policy"}}
        unknown = plausible - set(ALL_CAPABILITIES)
        assert unknown == set(), (
            f"the instructions name capabilities that do not exist: {sorted(unknown)}. A model "
            f"reading this will reason the path is gated when it is not.")

    def test_it_does_not_claim_an_operator_gate_on_writing_a_file(self):
        """The specific false claim. Kept as its own assertion because the phrasing is what a
        model acts on, and a generic capability check would not have caught prose."""
        assert "only if the operator enabled it" not in INSTRUCTIONS, (
            "no capability gates a filesystem write - ALL_CAPABILITIES is ten Drive-side names")

    def test_it_still_explains_where_the_file_goes(self):
        """Removing the false claim must not remove the useful half: a model needs to know the
        destination is configurable, or it will not mention it to the user."""
        assert "CSA_GW_EXPORT_DIR" in INSTRUCTIONS
