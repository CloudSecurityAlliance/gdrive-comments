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

Both are offline and take milliseconds, which is the argument for having them: the run that
found the gap needed a real account, a human, and five minutes.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import policy_from_env
from csa_google_workspace.policy import ALL_CAPABILITIES, PolicyBackend

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
                      "accept_suggestion"},
    "file.create": {"create_file", "copy_file"},
    "file.update": {"update_file_metadata"},
    "file.trash": {"trash_file"},
    "file.share": {"create_permission"},
}

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


class TestOneCapabilityAtATime:
    """The gap the end-to-end run named: is each operation wired to the RIGHT capability?"""

    @pytest.mark.parametrize("capability", [c for c in ALL_CAPABILITIES
                                            if EXPECTED.get(c)])
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

    def test_an_empty_modify_list_refuses_everything_file_scoped(self):
        """Unset means nothing, not everything - the fail-closed property."""
        files = {IN: {"id": IN, "name": "in", "mimeType": DOC_MIME}}
        policy = policy_from_env({"CSA_GW_CAPABILITIES": "all",
                                  "CSA_GW_ALLOWLIST_READ": "*"})
        guarded = PolicyBackend(FakeBackend(files), policy)
        with pytest.raises(exc.ReadOnlyError):
            guarded.trash_file(IN)
