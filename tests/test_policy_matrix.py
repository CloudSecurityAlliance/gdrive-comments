"""One capability on at a time, and a narrow allowlist — the two paths a single run cannot see.

An end-to-end run against a real account reported all three disabled capabilities refusing
correctly, and then named its own limit exactly right: *"all three fail at the same gate, so
this run really tested one code path three times — not three independent ones. The allowlist
path never executed at all, since both scopes were `*`."*

That is precisely true. `PolicyBackend.guarded` is a single closure, so every refusal in that
run hit the same `if not self._policy.allows(capability)` line. What it proved is that the gate
works. What it could not prove is that each operation is wired to the *right* capability — a
`_GATES` entry mapping `trash_file` to `file.update` would refuse identically with both off, and
would silently permit trashing for anybody who enabled updates.

So this file does the two things a session cannot:

1. **One capability at a time.** Enable exactly one and assert precisely which operations become
   possible. The expectation below is written out BY HAND rather than derived from `_GATES` -
   deriving it would test the table against itself and pass no matter what it said. Two
   independent statements of intent, and a disagreement means a human looks.

2. **A narrow allowlist.** One file in, one file out, every file-scoped operation attempted
   against both. This is the property the control exists for, and the one no `*`-scoped run can
   reach.

3. **Keep both tables complete.** Added 2026-09-01, after audit `2026-09-01-02` found that the
   hand-written tables had quietly stopped covering the code. Writing them by hand is what
   makes them a second opinion, and the cost is that a GAP in them is silent: `content.delete`
   had no row at all from v0.36.0, and eight gated methods appeared in no lambda, so nothing
   in this file could see them. `TestTheTablesAreComplete` asserts the tables cover every
   capability and every gated method - without deriving what the rows SAY, which would undo
   point 1.

Both are offline and take milliseconds, which is the argument for having them: the run that
found the gap needed a real account, a human, and five minutes.

**One limit worth stating.** This file covers the POLICY layer. `mcp/_capabilities.py` holds a
second, independent map - MCP tool name to capability - which feeds tool descriptions and
`demonstration_plan`, and nothing yet checks that the capability a tool DECLARES is the one
enforcement actually applies. That is where the divergence this file was extended for lived:
`clear_cells` declared one capability while `_GATES` enforced another, and the demo test agreed
with itself because both sides read the same map. Tracked as #325.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import policy_from_env
from csa_google_workspace.policy import _GATES, ALL_CAPABILITIES, PolicyBackend

IN = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
OUT = "1ZZ2CN6VqHDjxvl9kMKXvpv5CFDf6JOkJ9U7sHoBk9y9"
DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"

# What each capability should permit — written independently of `_GATES`, on purpose.
EXPECTED: dict[str, set[str]] = {
    "comment.create": {"create_comment", "create_cell_anchored_comment"},
    "comment.reply": {"create_reply"},
    "comment.resolve": set(),          # reached through create_reply's dynamic gate; see below
    "comment.edit": {"update_comment", "update_reply"},
    "comment.delete": {"delete_comment", "delete_reply"},
    "content.write": {"docs_batch_update", "sheets_values_update", "sheets_values_append",
                      "sheets_values_clear", "sheets_batch_update", "slides_batch_update",
                      "accept_suggestion", "docs_add_tab", "sheets_add_tab"},
    # Structural destruction, as against editing. `sheets_values_clear` is deliberately NOT
    # here - blanking a range is content.write, decided 2026-09-01 and pinned by
    # tests/test_cell_destruction_is_content_write.py, which carries the reasoning.
    "content.delete": {"docs_delete_range", "docs_delete_tab", "sheets_delete_tab"},
    "file.create": {"create_file", "copy_file"},
    "file.update": {"update_file_metadata"},
    "file.trash": {"trash_file"},
    "file.share": {"create_permission", "update_permission", "delete_permission",
                   "resolve_access_proposal"},
}

# A row may legitimately be empty - but only one is, and it has to say so out loud. The old
# filter (`if EXPECTED.get(c)`) skipped every empty row, which meant it could not tell "nothing
# to test here, on purpose" from "nobody wrote this down" - and `content.delete` had no row at
# all from v0.36.0 until 2026-09-01 without a single test noticing.
DELIBERATELY_EMPTY = frozenset({
    # `comment.resolve` gates no Backend method of its own. Resolving is an action-reply, so it
    # is reached through `create_reply`'s dynamic gate; tests/test_policy.py covers that path.
    "comment.resolve",
})

# How to call each gated method with arguments that would succeed if the policy allowed it.
CALLS = {
    "create_comment": lambda b, f: b.create_comment(f, "x"),
    "create_cell_anchored_comment": lambda b, f: b.create_cell_anchored_comment(f, "A1", "x"),
    "create_reply": lambda b, f: b.create_reply(f, "c1", "x"),
    "update_comment": lambda b, f: b.update_comment(f, "c1", "x"),
    "update_reply": lambda b, f: b.update_reply(f, "c1", "r1", "x"),
    "delete_comment": lambda b, f: b.delete_comment(f, "c1"),
    "delete_reply": lambda b, f: b.delete_reply(f, "c1", "r1"),
    "docs_batch_update": lambda b, f: b.docs_batch_update(f, []),
    "sheets_values_update": lambda b, f: b.sheets_values_update(f, "A1", [["x"]], "RAW"),
    "sheets_values_append": lambda b, f: b.sheets_values_append(f, "A1", [["x"]], "RAW"),
    "sheets_values_clear": lambda b, f: b.sheets_values_clear(f, "A1"),
    "sheets_batch_update": lambda b, f: b.sheets_batch_update(f, []),
    "slides_batch_update": lambda b, f: b.slides_batch_update(f, []),
    "accept_suggestion": lambda b, f: b.accept_suggestion(f, "s1"),
    "create_file": lambda b, f: b.create_file("n", DOC_MIME),
    "copy_file": lambda b, f: b.copy_file(f),
    "update_file_metadata": lambda b, f: b.update_file_metadata(f, name="n"),
    "trash_file": lambda b, f: b.trash_file(f),
    "create_permission": lambda b, f: b.create_permission(f, email="a@b.com", role="reader"),
    "update_permission": lambda b, f: b.update_permission(f, "p1", role="reader"),
    "delete_permission": lambda b, f: b.delete_permission(f, "p1"),
    "resolve_access_proposal": lambda b, f: b.resolve_access_proposal(f, "p1", action="deny"),
    "docs_add_tab": lambda b, f: b.docs_add_tab(f, "t"),
    "sheets_add_tab": lambda b, f: b.sheets_add_tab(f, "t"),
    "docs_delete_range": lambda b, f: b.docs_delete_range(f, 1, 2),
    "docs_delete_tab": lambda b, f: b.docs_delete_tab(f, "t1"),
    "sheets_delete_tab": lambda b, f: b.sheets_delete_tab(f, 0),
}


def backend(capabilities: str, modify: str = "*") -> PolicyBackend:
    files = {IN: {"id": IN, "name": "in", "mimeType": DOC_MIME},
             OUT: {"id": OUT, "name": "out", "mimeType": SHEET_MIME}}
    comments = {IN: [{"id": "c1", "content": "x", "author": {"displayName": "A"},
                      "replies": [{"id": "r1", "content": "y"}]}],
                OUT: [{"id": "c1", "content": "x", "author": {"displayName": "A"},
                       "replies": [{"id": "r1", "content": "y"}]}]}
    fake = FakeBackend(files, comments=comments,
                       documents={IN: {"body": {"content": []}}, OUT: {"body": {"content": []}}},
                       spreadsheets={IN: {"sheets": []}, OUT: {"sheets": []}},
                       presentations={IN: {"slides": []}, OUT: {"slides": []}})
    policy = policy_from_env({"CSA_GW_CAPABILITIES": capabilities,
                              "CSA_GW_ALLOWLIST_READ": "*",
                              "CSA_GW_ALLOWLIST_MODIFY": modify})
    return PolicyBackend(fake, policy)


def permitted(guarded: PolicyBackend, file_id: str = IN) -> set[str]:
    """Which gated operations the policy lets through, whatever they then do.

    A `ReadOnlyError` is the policy refusing. Anything else - NotFoundError,
    UnsupportedOperation from the fake - means the call got PAST the gate, which is what is
    being measured. Conflating the two would score an unimplemented method as "refused".
    """
    allowed = set()
    for name, call in CALLS.items():
        try:
            call(guarded, file_id)
            allowed.add(name)
        except exc.ReadOnlyError:
            continue
        except Exception:                # noqa: BLE001 - got past the gate, which is the point
            allowed.add(name)
    return allowed


GATED = {method for method, gate in _GATES.items() if gate.capability}

# `Gate.capability` may be a CALLABLE - `create_reply` is two operations wearing one method
# name, so which capability applies is decided per call. A static table cannot express that, so
# these methods are excluded from the row-vs-gate comparison and covered by EXECUTION instead
# (which is the stronger check anyway). Naming them here rather than filtering on `callable()`
# alone is the point: a SECOND dynamic gate should have to be added to this set deliberately,
# not disappear into an exclusion somebody wrote for the first one.
DYNAMICALLY_GATED = frozenset({"create_reply"})


class TestTheTablesAreComplete:
    """The tables above are hand-written on purpose - that is what makes them a second opinion
    rather than a mirror of `_GATES`. The cost is that a gap in them is silent, and three gaps
    accumulated: `content.delete` had no row from v0.36.0, and eight gated methods were in no
    lambda, so no test in this file could see them.

    These guards close that without deriving the expectations themselves. They assert the
    tables are COMPLETE; what each row SAYS is still written by hand and still has to agree.
    """

    def test_every_capability_has_a_row(self):
        """A capability with no row was skipped by the old `if EXPECTED.get(c)` filter, so
        adding one to `ALL_CAPABILITIES` silently added nothing to this file."""
        missing = set(ALL_CAPABILITIES) - set(EXPECTED)
        assert missing == set(), (
            f"no row in EXPECTED for {sorted(missing)}. Add one saying which operations the "
            f"capability should permit - if the answer is genuinely none, add it to "
            f"DELIBERATELY_EMPTY with the reason, so the next reader knows it was decided.")
        assert set(EXPECTED) <= set(ALL_CAPABILITIES), (
            f"EXPECTED names capabilities that no longer exist: "
            f"{sorted(set(EXPECTED) - set(ALL_CAPABILITIES))}")

    def test_only_declared_capabilities_are_empty(self):
        """An empty row is a claim that a capability gates nothing directly. That can be true,
        and is for `comment.resolve` - but it must be stated, not inferred from a blank."""
        empty = {c for c, ops in EXPECTED.items() if not ops}
        assert empty == DELIBERATELY_EMPTY, (
            f"empty rows are {sorted(empty)} but only {sorted(DELIBERATELY_EMPTY)} are declared "
            f"deliberate. An undeclared empty row tests nothing while looking like it does.")

    def test_every_gated_backend_method_is_exercised(self):
        """The one that would have caught all eight. `permitted()` iterates CALLS, so a gated
        method with no lambda is invisible to every test here - including
        `test_everything_is_permitted_with_all`, which compares against `set(CALLS)` and so
        was measuring the table against itself."""
        missing = GATED - set(CALLS)
        assert missing == set(), (
            f"these Backend methods are gated but never called here, so nothing checks which "
            f"capability they are wired to: {sorted(missing)}. Add a lambda to CALLS and the "
            f"method to its capability's row in EXPECTED.")

    def test_calls_does_not_name_an_ungated_method(self):
        """The other direction: a method that lost its gate should fail loudly here rather than
        keep passing as 'permitted' because nothing refuses it any more."""
        extra = set(CALLS) - GATED
        assert extra == set(), (
            f"CALLS exercises {sorted(extra)}, which policy._GATES does not gate. Either the "
            f"gate was dropped - a real regression - or the entry is stale.")

    def test_every_row_names_only_gated_methods(self):
        """A typo in a row would otherwise show up as a confusing inequality in the
        per-capability test rather than as the spelling mistake it is."""
        named = {m for ops in EXPECTED.values() for m in ops}
        assert named <= GATED, f"EXPECTED names non-gated methods: {sorted(named - GATED)}"

    def test_the_dynamic_gates_are_the_declared_ones(self):
        """An exclusion nobody re-reads is how a real gap hides. If a new method gets a callable
        capability, this fails and somebody decides whether it belongs in the exclusion."""
        dynamic = {m for m, g in _GATES.items() if callable(g.capability)}
        assert dynamic == DYNAMICALLY_GATED, (
            f"policy._GATES gates {sorted(dynamic)} dynamically but this file declares "
            f"{sorted(DYNAMICALLY_GATED)}. A dynamically-gated method is invisible to the "
            f"static row comparison, so it must be listed - and covered by execution.")

    def test_each_row_matches_the_capability_gates_assign(self):
        """`_GATES` and EXPECTED are two independent statements of the same wiring. This is the
        cheap comparison; the per-capability tests below prove it by EXECUTION, which is what
        catches a gate that is right in the table and wrong in the closure."""
        from collections import defaultdict
        by_capability: dict[str, set[str]] = defaultdict(set)
        for method in GATED - DYNAMICALLY_GATED:
            by_capability[_GATES[method].capability].add(method)
        for capability, expected in EXPECTED.items():
            assert expected - DYNAMICALLY_GATED == by_capability[capability], (
                f"for {capability}, EXPECTED says {sorted(expected - DYNAMICALLY_GATED)} but "
                f"policy._GATES says "
                f"{sorted(by_capability[capability])}. Which one is wrong is a DECISION - if "
                f"the gate moved on purpose, the row moves with it and the reason gets written "
                f"down; if not, the gate is the bug.")


class TestOneCapabilityAtATime:
    """The gap the end-to-end run named: is each operation wired to the RIGHT capability?"""

    @pytest.mark.parametrize("capability", sorted(set(ALL_CAPABILITIES) - DELIBERATELY_EMPTY))
    def test_exactly_the_expected_operations_become_possible(self, capability):
        allowed = permitted(backend(capability))
        expected = EXPECTED[capability]
        assert allowed == expected, (
            f"with only {capability} enabled, expected {sorted(expected)} to be permitted but "
            f"got {sorted(allowed)}. Either policy._GATES maps an operation to the wrong "
            f"capability, or the expectation in this file is out of date - and which one is "
            f"wrong is a decision, not a fix.")

    def test_nothing_is_permitted_with_no_capabilities(self):
        """`none` has to mean none. Every gated operation, refused."""
        assert permitted(backend("none")) == set()

    def test_everything_is_permitted_with_all(self):
        """And `all` has to reach every one of them, or something is gated on a capability the
        policy cannot express."""
        assert permitted(backend("all")) == set(CALLS)

    def test_no_capability_is_a_superset_of_another_by_accident(self):
        """Enabling one capability must not smuggle in another's operations. This is the shape
        a mis-wired gate takes: `trash_file` mapped to `file.update` refuses identically when
        both are off, and quietly grants trashing to anybody who enables updates."""
        for capability, expected in EXPECTED.items():
            if not expected:
                continue
            allowed = permitted(backend(capability))
            for other, other_expected in EXPECTED.items():
                if other == capability or not other_expected:
                    continue
                leaked = allowed & other_expected
                assert not leaked, (
                    f"{capability} also permitted {sorted(leaked)}, which belongs to {other}")


class TestANarrowAllowlist:
    """The path that never executed in the live run, because both scopes were `*`."""

    def all_capabilities_one_file(self):
        return backend("all", modify=f"https://docs.google.com/document/d/{IN}/edit")

    def test_a_listed_file_is_writable(self):
        allowed = permitted(self.all_capabilities_one_file(), file_id=IN)
        # `create_file` is not file-scoped - there is no file yet - so it is permitted either
        # way and is not evidence about the allowlist.
        assert "update_file_metadata" in allowed and "trash_file" in allowed

    # Two operations are permitted for an unlisted file, both deliberately, and this test
    # exists partly to state which:
    #
    #   create_file  is not file-scoped. There is no file yet, so there is nothing for the
    #                allowlist to check.
    #   copy_file    is checked against the READ scope, not modify - it reads a source. The
    #                copy it makes has a NEW id, which is not in the modify allowlist either,
    #                so copying cannot be used to obtain a writable duplicate of something
    #                unwritable. That is the point of gating it on read.
    #
    # The first version of this test asserted only `create_file` and failed on `copy_file`,
    # which sent me to policy._GATES to find out which was wrong. It was the test. Naming
    # both here means the next person gets the answer instead of the search.
    PERMITTED_WITHOUT_A_LISTING = {"create_file", "copy_file"}

    def test_an_unlisted_file_is_refused_for_every_file_scoped_write(self):
        """The property the control exists for. Every gated write, refused for a file nobody
        listed - with every capability enabled, so the ONLY thing saying no is the allowlist."""
        allowed = permitted(self.all_capabilities_one_file(), file_id=OUT)
        leaked = allowed - self.PERMITTED_WITHOUT_A_LISTING
        assert leaked == set(), f"these got through for an unlisted file: {sorted(leaked)}"

    def test_a_copy_of_an_unlisted_file_is_not_writable_either(self):
        """The reason copy_file is allowed to read outside the modify list: what it produces is
        a new id, so the copy is no more writable than the original was."""
        guarded = self.all_capabilities_one_file()
        copy = guarded.copy_file(OUT)
        with pytest.raises(exc.ReadOnlyError):
            guarded.trash_file(copy["id"])

    def test_the_refusal_names_the_file_and_the_variable(self):
        """A refusal somebody cannot act on is a refusal they will ask about."""
        with pytest.raises(exc.ReadOnlyError) as raised:
            self.all_capabilities_one_file().trash_file(OUT)
        message = str(raised.value)
        assert OUT in message
        assert "CSA_GW_ALLOWLIST_MODIFY" in message

    def test_reads_are_not_narrowed_by_the_modify_list(self):
        """#82 is damage containment, not confidentiality: the agent already sees what the
        user's credentials see, so narrowing reads buys nothing and breaks triage."""
        guarded = self.all_capabilities_one_file()
        assert guarded.get_file_metadata(OUT)["id"] == OUT

    def test_a_narrowed_modify_list_refuses_a_file_outside_it(self):
        """**Rewritten for the v0.31.0 defaults.** This asserted that an *unset* modify list
        refuses everything; unset now means every file.

        The property worth holding is the one the allowlist exists for, and it is unchanged: a
        file the operator did NOT list cannot be changed, whatever the capabilities say. Tested
        with an explicit narrow list, which is what an operator who wants this now writes."""
        files = {IN: {"id": IN, "name": "in", "mimeType": DOC_MIME},
                 OUT: {"id": OUT, "name": "out", "mimeType": DOC_MIME}}
        policy = policy_from_env({"CSA_GW_CAPABILITIES": "all",
                                  "CSA_GW_ALLOWLIST_READ": "*",
                                  "CSA_GW_ALLOWLIST_MODIFY": f"https://docs.google.com/document/d/{IN}/edit"})
        guarded = PolicyBackend(FakeBackend(files), policy)
        guarded.trash_file(IN)                      # listed
        with pytest.raises(exc.ReadOnlyError):
            guarded.trash_file(OUT)                 # not listed
