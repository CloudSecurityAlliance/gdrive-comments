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
`ALL_CAPABILITIES` is Drive-side names and none of them gates a filesystem write, so
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
from csa_google_workspace.mcp._capabilities import TOOL_CAPABILITIES
from csa_google_workspace.mcp.server import INSTRUCTIONS, create_server
from csa_google_workspace.policy import ALL_CAPABILITIES, PolicyBackend


# Hand-written on purpose. Deriving it from the code would test the code against itself; the
# question "does this tool touch the filesystem or create a file?" is one a person answers by
# reading it, and a new tool belongs on this list by a deliberate act.
# DERIVED, not hand-listed (#319). The list version named 13 tools while 27 are gated, so
# SIXTEEN mutating tools could have been re-annotated `read_only_hint=True` with the suite
# staying green - including `delete_comment`, `clear_cells` and `resolve_access_proposal`, which
# grants a stranger access to a document. Its anti-staleness guard fired on a name that no
# longer existed and never on a mutating tool that was never added, which is precisely the
# defect class #184 was filed about.
#
# A tool gated on a capability mutates something by definition, so `TOOL_CAPABILITIES` already
# knows the answer and cannot fall behind the way a literal can.
def _gated_tools() -> set[str]:
    return {name for name, capability in TOOL_CAPABILITIES.items() if capability}


# The two that write OUTSIDE the capability model, so no gate names them. Declared with
# reasons rather than folded in silently, and asserted disjoint from the derived set below -
# if either ever gains a capability, that assertion fails and somebody decides deliberately
# instead of ending up with a stale duplicate.
WRITES_WITHOUT_A_CAPABILITY = {
    "export_comments": 'destination="file"/"xlsx" writes a path and "sheet" creates a Drive '
                       "file, but the tool itself is ungated - see "
                       "test_mcp_capabilities.py::test_the_reverse_is_deliberately_not_asserted",
    "authenticate": "writes the token cache, which is local state and not a Drive capability",
}


def touches_storage() -> set[str]:
    return _gated_tools() | set(WRITES_WITHOUT_A_CAPABILITY)


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
            name for name in touches_storage()
            if name in tools and getattr(tools[name].annotations, "read_only_hint", False)]
        assert offenders == [], (
            f"annotated read-only while writing: {sorted(offenders)}. The spec maps "
            f"readOnlyHint to 'skip the confirmation dialog' for a trusted server, so this "
            f"suppresses the client's approval prompt.")

    def test_no_storage_tool_claims_to_be_idempotent(self, tools):
        """A retry that creates a second file is not a retry."""
        offenders = [
            name for name in touches_storage()
            if name in tools and getattr(tools[name].annotations, "idempotent_hint", False)]
        assert offenders == [], f"annotated idempotent while writing: {sorted(offenders)}"

    def test_the_set_names_no_tool_that_has_gone(self, tools):
        """The old hand-written list had a staleness guard for exactly this, and it was the
        WEAKER half: it could only fire on a name that had been removed, never on a mutating
        tool that was never added. The set is derived now, so the removal case is all that is
        left to check — and it still is, because `TOOL_CAPABILITIES` can name a tool that no
        longer exists."""
        gone = sorted(touches_storage() - set(tools))
        assert gone == [], (
            f"these are treated as touching storage but are not registered: {gone}. Either a "
            f"tool was renamed and TOOL_CAPABILITIES not updated, or a declared exception is "
            f"stale.")

    def test_a_genuinely_read_only_tool_is_still_annotated_read_only(self, tools):
        """The counterweight: broadening WRITE until it means nothing would also pass the
        assertions above."""
        for name in ("list_comments", "get_comment", "read_file_content", "search_files"):
            assert tools[name].annotations.read_only_hint is True, (
                f"{name} reads and should say so, or the annotation carries no information")


class TestTheStorageSetIsDerived:
    """#319. The hand-written version named 13 of 27 gated tools, and its staleness guard could
    only fire on a name that had been REMOVED - never on a mutating tool that was never added."""

    def test_every_gated_tool_is_treated_as_touching_storage(self, tools):
        missing = sorted(_gated_tools() - touches_storage())
        assert missing == [], f"derivation dropped {missing}"

    def test_the_declared_exceptions_are_not_also_gated(self):
        """If one of them gains a capability the derivation covers it, and the declaration
        becomes a stale duplicate that nothing would otherwise notice."""
        overlap = sorted(set(WRITES_WITHOUT_A_CAPABILITY) & _gated_tools())
        assert overlap == [], (
            f"{overlap} are now gated, so the derived set already includes them - remove them "
            f"from WRITES_WITHOUT_A_CAPABILITY rather than carrying both")

    def test_the_exceptions_still_exist_as_tools(self, tools):
        """The failure the old list could catch, kept: a declared name that no longer exists."""
        stale = sorted(set(WRITES_WITHOUT_A_CAPABILITY) - set(tools))
        assert stale == [], f"{stale} are declared but no longer registered"

    def test_it_covers_more_than_the_old_hand_list_did(self, tools):
        """A regression guard on the FIX, not on the code: if somebody replaces the derivation
        with a literal again, this notices. 27 gated plus 2 ungated writers."""
        assert len(touches_storage()) >= 27, (
            f"only {len(touches_storage())} tools treated as touching storage; the hand-written "
            f"version managed 13 and that was the bug")


class TestTheInstructionsDoNotInventControls:
    CAPABILITY_SHAPED = re.compile(r"\b([a-z]+\.[a-z_]+)\b")
    # `foo.bar`-shaped tokens that could be a capability. Filenames, hostnames and mime types
    # are the same shape, so the first segment has to look like one of ours.
    NAMESPACES = {"comment", "content", "file", "export", "account", "policy"}

    def model_facing_capability_tokens(self, tools) -> set[str]:
        """Every capability-shaped token in anything the model reads.

        **Widened 2026-09-01.** This guard used to read `INSTRUCTIONS` alone, and by the time
        audit `2026-09-01-02` looked (#320) there were ZERO dotted tokens left in it - so the
        input set was empty and the assertion passed without checking anything.

        Widening it is not just about restoring an input. It is the same lesson as #332, where
        the default-posture claims MOVED from `INSTRUCTIONS` to the tool descriptions and the
        guard aimed at `INSTRUCTIONS` never saw them. The claims live in the descriptions; a
        guard that reads only the preamble is looking at the wrong surface.
        """
        texts = [t.description or "" for t in tools.values()] + [INSTRUCTIONS]
        named = {t for text in texts for t in self.CAPABILITY_SHAPED.findall(text)}
        return {t for t in named if t.split(".")[0] in self.NAMESPACES}

    def test_the_guard_has_something_to_check(self, tools):
        """Asserted separately so a future emptying fails HERE, naming the cause, rather than
        turning the test below into a green no-op.

        Note what is NOT asserted: that any particular capability is mentioned. Requiring that
        would push a count or a name into prose that a constant controls, which is the drift
        this repository keeps fixing. The claim is only that the guard is still looking at
        something."""
        assert self.model_facing_capability_tokens(tools), (
            "no capability-shaped token appears in any tool description or in INSTRUCTIONS, so "
            "the check below cannot fail. Either the model-facing text stopped naming "
            "capabilities - which is a real change worth noticing - or this guard is reading "
            "the wrong surface, as it was before #320.")

    def test_every_capability_named_in_model_facing_text_exists(self, tools):
        unknown = self.model_facing_capability_tokens(tools) - set(ALL_CAPABILITIES)
        assert unknown == set(), (
            f"model-facing text names capabilities that do not exist: {sorted(unknown)}. A "
            f"model reading this will reason the path is gated when it is not.")

    def test_it_does_not_claim_an_operator_gate_on_writing_a_file(self):
        """The specific false claim. Kept as its own assertion because the phrasing is what a
        model acts on, and a generic capability check would not have caught prose."""
        assert "only if the operator enabled it" not in INSTRUCTIONS, (
            "no capability gates a filesystem write - every name in ALL_CAPABILITIES is "
            "Drive-side")

    def test_it_still_explains_where_the_file_goes(self):
        """Removing the false claim must not remove the useful half: a model needs to know the
        destination is configurable, or it will not mention it to the user."""
        assert "CSA_GW_EXPORT_DIR" in INSTRUCTIONS
