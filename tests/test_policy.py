"""Capability gating — #82's first dimension.

The tests that matter most here are the two structural ones: that `_GATES` covers every
`Backend` method (so a new method cannot arrive ungated), and that an unlisted name fails
closed rather than delegating.
"""
import pytest

from csa_google_workspace import Workspace, policy
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import Backend, FakeBackend
from csa_google_workspace.policy import Policy, PolicyBackend

DOC = "application/vnd.google-apps.document"
FILES = {"f": {"id": "f", "name": "F", "mimeType": DOC, "webViewLink": "https://x"}}


def _protocol_methods():
    return {n for n, v in vars(Backend).items() if callable(v) and not n.startswith("_")}


# --- the structural guards --------------------------------------------------

def test_every_backend_method_has_a_declared_gate():
    """A `Backend` method with no entry in `_GATES` is one whose gate nobody decided. This
    is the guard that makes the wrapper fail closed as the protocol grows — without it, the
    next method added would be silently ungated."""
    missing = sorted(_protocol_methods() - set(policy._GATES))
    assert missing == [], f"no capability gate declared for: {missing}"


def test_gates_do_not_name_methods_that_do_not_exist():
    """A stale entry is a gate protecting nothing, and reads like protection."""
    stale = sorted(set(policy._GATES) - _protocol_methods())
    assert stale == []


def test_an_undeclared_method_is_refused_not_delegated():
    class _Extra(FakeBackend):
        def some_new_write(self, file_id):        # pragma: no cover - never reached
            return "should not happen"

    backend = PolicyBackend(_Extra(dict(FILES)), Policy.default())
    with pytest.raises(exc.UnsupportedOperation) as e:
        backend.some_new_write("f")
    assert "_GATES" in str(e.value)


# --- defaults --------------------------------------------------------------

def test_the_default_policy_preserves_todays_behaviour():
    """Comment and content writes already worked; turning them off here would be a silent
    behaviour change dressed up as a security improvement."""
    p = Policy.default()
    for capability in (policy.COMMENT_CREATE, policy.COMMENT_REPLY, policy.COMMENT_RESOLVE,
                       policy.COMMENT_EDIT, policy.COMMENT_DELETE, policy.CONTENT_WRITE,
                       policy.FILE_CREATE):
        assert p.allows(capability), capability


def test_the_dangerous_three_are_off_by_default():
    """update/trash/share each alter or expose a file that already exists, and each is one
    Google's own MCP server declines to offer."""
    p = Policy.default()
    for capability in (policy.FILE_UPDATE, policy.FILE_TRASH, policy.FILE_SHARE):
        assert not p.allows(capability), capability


def test_default_enabled_and_disabled_together_cover_everything():
    assert (policy.DEFAULT_ENABLED | policy.DEFAULT_DISABLED) == set(policy.ALL_CAPABILITIES)
    assert not (policy.DEFAULT_ENABLED & policy.DEFAULT_DISABLED)


# --- enforcement -----------------------------------------------------------

def _ws(*capabilities):
    """Scopes left at their permissive library default, so these exercise capabilities only."""
    return Workspace(PolicyBackend(FakeBackend(dict(FILES)), Policy.of(*capabilities)))


def test_reads_are_never_gated():
    """#82 is damage containment, not confidentiality: the agent already sees what the
    user's credentials see."""
    doc = _ws().open("f")                              # no capabilities at all
    assert doc.name == "F"
    assert doc.comments.all() == []


def test_a_disabled_capability_refuses_the_write():
    doc = _ws().open("f")
    with pytest.raises(exc.ReadOnlyError) as e:
        doc.create_comment("nope")
    assert "comment.create" in str(e.value)
    assert "cannot be turned on from here" in str(e.value)


def test_an_enabled_capability_permits_the_write():
    doc = _ws(policy.COMMENT_CREATE).open("f")
    assert doc.create_comment("fine").content == "fine"


def test_reply_and_resolve_are_separately_gated_despite_one_backend_method():
    """create_reply carries both: resolve/reopen is an action-reply, never a PATCH. Gating
    on the method name alone would let anyone who may reply also close the thread."""
    doc = _ws(policy.COMMENT_CREATE, policy.COMMENT_REPLY).open("f")
    comment = doc.create_comment("thread")
    comment.reply("adding to it")                       # allowed
    with pytest.raises(exc.ReadOnlyError) as e:
        comment.resolve()
    assert "comment.resolve" in str(e.value)


def test_resolve_without_reply_is_also_possible():
    doc = _ws(policy.COMMENT_CREATE, policy.COMMENT_RESOLVE).open("f")
    comment = doc.create_comment("thread")
    comment.resolve()
    assert doc.comments.get(comment.id).resolved is True
    with pytest.raises(exc.ReadOnlyError):
        comment.reply("not allowed")


def test_content_write_gates_every_content_method():
    doc = _ws().open("f")
    with pytest.raises(exc.ReadOnlyError):
        doc.batch_update([{"insertText": {"location": {"index": 1}, "text": "x"}}])


# --- Policy construction ---------------------------------------------------

def test_of_rejects_an_unknown_capability_and_lists_the_known_ones():
    with pytest.raises(ValueError) as e:
        Policy.of("file.nuke")
    assert "file.nuke" in str(e.value) and "file.share" in str(e.value)


def test_with_enabled_widens_and_without_narrows():
    p = Policy.of(policy.COMMENT_CREATE)
    assert p.with_enabled(policy.FILE_SHARE).allows(policy.FILE_SHARE)
    assert not p.with_enabled(policy.FILE_SHARE).without(policy.FILE_SHARE).allows(policy.FILE_SHARE)


def test_repr_names_the_enabled_set_and_the_wrapped_backend():
    text = repr(PolicyBackend(FakeBackend({}), Policy.of(policy.FILE_TRASH)))
    assert "FakeBackend" in text and "file.trash" in text


# --- dimension 2: the read and modify allowlists ---------------------------

from csa_google_workspace.allowlist import parse_allowlist  # noqa: E402
from csa_google_workspace.policy import Scope  # noqa: E402

DOC_URL = "https://docs.google.com/document/d/1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8/edit"
DOC_ID = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
FILES_TWO = {
    DOC_ID: {"id": DOC_ID, "name": "Allowed", "mimeType": DOC, "webViewLink": "https://x"},
    "other": {"id": "other", "name": "Not allowed", "mimeType": DOC, "webViewLink": "https://x"},
}
ONE_FILE = Scope.from_listing(parse_allowlist(DOC_URL))


def _ws2(*capabilities, read=None, modify=None):
    pol = Policy(enabled=frozenset(capabilities),
                 read=read or Scope.everything(),
                 modify=modify or Scope.everything())
    return Workspace(PolicyBackend(FakeBackend(dict(FILES_TWO)), pol))


# --- the modify scope -------------------------------------------------------

def test_a_listed_file_may_be_written():
    doc = _ws2(policy.COMMENT_CREATE, modify=ONE_FILE).open(DOC_ID)
    assert doc.create_comment("allowed").content == "allowed"


def test_an_unlisted_file_may_not_be_written():
    doc = _ws2(policy.COMMENT_CREATE, modify=ONE_FILE).open("other")
    with pytest.raises(exc.ReadOnlyError) as e:
        doc.create_comment("nope")
    message = str(e.value)
    assert "not in the modify allowlist" in message
    assert "CSA_GW_ALLOWLIST_MODIFY" in message
    assert "cannot be changed from here" in message      # not widenable in-band


def test_an_unlisted_file_is_still_readable_when_read_is_wide():
    """The whole point of splitting the two: READ=* with MODIFY locked down."""
    ws = _ws2(policy.COMMENT_CREATE, modify=ONE_FILE)
    assert ws.open("other").name == "Not allowed"
    assert ws.open("other").comments.all() == []


# --- the read scope ---------------------------------------------------------

def test_a_read_outside_the_read_scope_is_refused():
    with pytest.raises(exc.AccessError) as e:
        _ws2(read=ONE_FILE).open("other")
    assert "CSA_GW_ALLOWLIST_READ" in str(e.value)


def test_a_refused_read_is_an_access_error_not_a_read_only_error():
    """Nothing about writing is involved, and the exception type is part of the API."""
    with pytest.raises(exc.AccessError):
        _ws2(read=ONE_FILE).open("other")
    assert not issubclass(exc.AccessError, exc.ReadOnlyError)


def test_a_read_inside_the_read_scope_works():
    assert _ws2(read=ONE_FILE).open(DOC_ID).name == "Allowed"


def test_search_results_outside_the_read_scope_are_filtered_out():
    """A listing has no single file to check, so the results are filtered. Anything outside
    the read scope must not be *named* either, or search enumerates what the policy excludes."""
    hits = _ws2(read=ONE_FILE).files.search("name contains 'llowed'")
    assert [h.id for h in hits] == [DOC_ID]          # "Not allowed" also matches the query


def test_search_is_unfiltered_when_read_is_everything():
    hits = _ws2().files.search("name contains 'llowed'")
    assert {h.id for h in hits} == {DOC_ID, "other"}


def test_nothing_is_readable_when_the_read_scope_is_empty():
    """Fail closed: the MCP server's default when nothing is configured."""
    ws = Workspace(PolicyBackend(FakeBackend(dict(FILES_TWO)),
                                 Policy(enabled=frozenset(), read=Scope.nothing(),
                                        modify=Scope.nothing())))
    with pytest.raises(exc.AccessError) as e:
        ws.open(DOC_ID)
    assert "no read allowlist is configured" in str(e.value)
    assert ws.files.search("name contains 'llowed'") == []


# --- composition ------------------------------------------------------------

def test_the_three_bounds_are_each_a_ceiling():
    listed = _ws2(modify=ONE_FILE).open(DOC_ID)          # in scope, no capability
    with pytest.raises(exc.ReadOnlyError) as e:
        listed.create_comment("no")
    assert "capability is disabled" in str(e.value)

    unlisted = _ws2(policy.COMMENT_CREATE, modify=ONE_FILE).open("other")
    with pytest.raises(exc.ReadOnlyError) as e:
        unlisted.create_comment("no")
    assert "not in the modify allowlist" in str(e.value)


def test_content_writes_are_modify_scoped_too():
    edit = [{"insertText": {"location": {"index": 1}, "text": "x"}}]
    _ws2(policy.CONTENT_WRITE, modify=ONE_FILE).open(DOC_ID).batch_update(edit)
    with pytest.raises(exc.ReadOnlyError):
        _ws2(policy.CONTENT_WRITE, modify=ONE_FILE).open("other").batch_update(edit)


def test_a_star_scope_permits_everything():
    everything = Scope.from_listing(parse_allowlist("*"))
    assert everything.allows("anything-at-all")
    _ws2(policy.COMMENT_CREATE, modify=everything).open("other").create_comment("fine")


# --- Scope itself -----------------------------------------------------------

def test_scope_distinguishes_everything_from_nothing():
    """Collapsing these into one representation is how a fail-closed default becomes
    fail-open during a refactor."""
    assert Scope.everything().allows("x") and not Scope.nothing().allows("x")
    assert Scope.everything().describe() == "every file"
    assert Scope.nothing().describe() == "no files"
    assert ONE_FILE.describe() == "1 listed file(s)"


def test_the_library_default_is_permissive_unlike_the_server():
    """`Workspace.from_credentials` is called by a developer who has made a decision; the MCP
    server is configuration handed to a model. Two artifacts, two defaults."""
    assert Policy.default().read.all_files and Policy.default().modify.all_files


# --- Policy construction ---------------------------------------------------

def test_with_scopes_leaves_capabilities_alone():
    p = Policy.of(policy.COMMENT_CREATE).with_scopes(modify=ONE_FILE)
    assert p.enabled == frozenset({policy.COMMENT_CREATE})
    assert p.modify is ONE_FILE and p.read.all_files


def test_repr_describes_both_scopes():
    text = repr(PolicyBackend(FakeBackend({}), Policy.of(policy.COMMENT_CREATE)
                              .with_scopes(modify=ONE_FILE)))
    assert "read=every file" in text and "modify=1 listed file(s)" in text


def test_every_file_scoped_gate_receives_a_file_id():
    """`Gate.file_scoped` is a claim about the method's first argument. If a gated method ever
    stops taking one, the wrapper fails closed — this asserts the claim holds today, so that
    failure never reaches a user."""
    import inspect

    from csa_google_workspace.policy import _GATES
    for name, gate in _GATES.items():
        if not gate.file_scoped:
            continue
        first = list(inspect.signature(getattr(Backend, name)).parameters)[1]
        assert first == "file_id", f"{name} is file_scoped but its first parameter is {first!r}"


def test_every_gate_declares_a_known_access_kind():
    from csa_google_workspace.policy import _GATES, MODIFY, READ
    for name, gate in _GATES.items():
        assert gate.access in (READ, MODIFY), f"{name} has access={gate.access!r}"


# --- the three configuration outcomes --------------------------------------

def test_the_three_outcomes_are_everything_a_list_or_nothing():
    """`*`, specific files, and anything else — blank, unset, malformed — is the third case,
    which fails closed."""
    from csa_google_workspace.allowlist import AllowlistError
    assert Scope.from_listing(parse_allowlist("*")).allows("anything")
    assert ONE_FILE.allows(DOC_ID) and not ONE_FILE.allows("other")
    assert not Scope.nothing().allows(DOC_ID)
    for unusable in ("", "   ", "# only comments\n", "https://example.com/x"):
        with pytest.raises((AllowlistError, ValueError)):
            parse_allowlist(unusable)


def test_a_denial_says_why_the_scope_is_empty_not_just_that_it_is():
    """The reason is carried on the Scope so the message can name which variable to set and
    why it currently yields nothing. "Denied" alone is not actionable."""
    reason = "CSA_GW_ALLOWLIST_MODIFY is set but empty — which is not the same as unset."
    ws = Workspace(PolicyBackend(
        FakeBackend(dict(FILES_TWO)),
        Policy(enabled=frozenset({policy.COMMENT_CREATE}),
               read=Scope.everything(), modify=Scope.nothing(reason=reason))))
    with pytest.raises(exc.ReadOnlyError) as e:
        ws.open(DOC_ID).create_comment("x")
    message = str(e.value)
    assert "set but empty" in message                 # the specific diagnosis
    assert "CSA_GW_ALLOWLIST_MODIFY" in message       # what to change
    assert "`*`" in message                           # and the escape hatch


def test_an_empty_scope_without_a_reason_still_produces_a_usable_message():
    ws = Workspace(PolicyBackend(
        FakeBackend(dict(FILES_TWO)),
        Policy(enabled=frozenset({policy.COMMENT_CREATE}), modify=Scope.nothing())))
    with pytest.raises(exc.ReadOnlyError) as e:
        ws.open(DOC_ID).create_comment("x")
    assert "no modify allowlist is configured" in str(e.value)


# --- named capability profiles ---------------------------------------------

def test_the_editor_profile_is_exactly_the_historical_default():
    """Held together here rather than by a module-level assert, which bandit flags and
    `python -O` strips. If they drift, an install silently changes what it may do."""
    assert policy.PROFILES["editor"] == policy.DEFAULT_ENABLED


def test_profiles_ascend():
    """Each profile must be a superset of the one before, or "pick the next one up" stops
    being sound advice."""
    from itertools import pairwise  # 3.10+, and exactly this idiom
    names = ["reader", "commenter", "editor", "full"]
    for narrower, wider in pairwise(names):
        assert policy.PROFILES[narrower] < policy.PROFILES[wider], f"{narrower} ⊄ {wider}"


def test_full_is_every_capability_and_reader_is_none():
    assert policy.PROFILES["full"] == set(policy.ALL_CAPABILITIES)
    assert policy.PROFILES["reader"] == frozenset()


def test_no_profile_names_an_unknown_capability():
    for name, capabilities in policy.PROFILES.items():
        unknown = capabilities - set(policy.ALL_CAPABILITIES)
        assert not unknown, f"profile {name} names {unknown}"


def test_commenter_cannot_touch_content_or_the_file_itself():
    """The distinction the profile exists to make: joining the conversation is not editing."""
    commenter = policy.PROFILES["commenter"]
    for forbidden in (policy.CONTENT_WRITE, policy.COMMENT_DELETE, policy.FILE_CREATE,
                      policy.FILE_UPDATE, policy.FILE_TRASH, policy.FILE_SHARE):
        assert forbidden not in commenter, forbidden


def test_a_commenter_profile_refuses_a_content_edit_end_to_end():
    ws = Workspace(PolicyBackend(FakeBackend(dict(FILES)),
                                 Policy(enabled=policy.PROFILES["commenter"])))
    doc = ws.open("f")
    doc.create_comment("allowed")
    with pytest.raises(exc.ReadOnlyError) as e:
        doc.batch_update([{"insertText": {"location": {"index": 1}, "text": "x"}}])
    assert "content.write" in str(e.value)
