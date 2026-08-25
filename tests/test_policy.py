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


# --- dimension 2: the file allowlist ---------------------------------------

from csa_google_workspace.allowlist import parse_allowlist  # noqa: E402

DOC_URL = "https://docs.google.com/document/d/1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8/edit"
DOC_ID = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
FILES_TWO = {
    DOC_ID: {"id": DOC_ID, "name": "Allowed", "mimeType": DOC, "webViewLink": "https://x"},
    "other": {"id": "other", "name": "Not allowed", "mimeType": DOC, "webViewLink": "https://x"},
}


def _scoped(*capabilities):
    entries = parse_allowlist(DOC_URL)
    return Workspace(PolicyBackend(FakeBackend(dict(FILES_TWO)),
                                   Policy.from_entries(frozenset(capabilities), entries)))


def test_a_listed_file_may_be_written():
    doc = _scoped(policy.COMMENT_CREATE).open(DOC_ID)
    assert doc.create_comment("allowed").content == "allowed"


def test_an_unlisted_file_may_not_be_written():
    doc = _scoped(policy.COMMENT_CREATE).open("other")
    with pytest.raises(exc.ReadOnlyError) as e:
        doc.create_comment("nope")
    message = str(e.value)
    assert "not in the write allowlist" in message
    assert "1 file(s) listed" in message
    assert "cannot be added from here" in message      # not widenable in-band


def test_an_unlisted_file_may_still_be_read():
    """#82 is damage containment, not confidentiality."""
    ws = _scoped(policy.COMMENT_CREATE)
    doc = ws.open("other")
    assert doc.name == "Not allowed"
    assert doc.comments.all() == []


def test_the_two_dimensions_compose_as_a_ceiling_and_a_narrowing():
    """A capability absent from `enabled` cannot be reached by listing the file, and a file
    absent from the list cannot be reached by enabling the capability."""
    listed = _scoped().open(DOC_ID)                     # listed, but no capabilities
    with pytest.raises(exc.ReadOnlyError) as e:
        listed.create_comment("no")
    assert "capability is disabled" in str(e.value)

    unlisted = _scoped(policy.COMMENT_CREATE).open("other")
    with pytest.raises(exc.ReadOnlyError) as e:
        unlisted.create_comment("no")
    assert "not in the write allowlist" in str(e.value)


def test_content_writes_are_file_scoped_too():
    edit = [{"insertText": {"location": {"index": 1}, "text": "x"}}]
    _scoped(policy.CONTENT_WRITE).open(DOC_ID).batch_update(edit)   # allowed
    with pytest.raises(exc.ReadOnlyError):
        _scoped(policy.CONTENT_WRITE).open("other").batch_update(edit)


def test_no_allowlist_means_no_file_restriction():
    """The default, because it is what this library has always done. Flipping it to
    fail-closed is a recorded 1.0.0 decision, not a silent change."""
    ws = Workspace(PolicyBackend(FakeBackend(dict(FILES_TWO)),
                                 Policy.of(policy.COMMENT_CREATE)))
    assert ws.open("other").create_comment("fine").content == "fine"


def test_repr_says_how_many_files_are_in_scope():
    scoped = PolicyBackend(FakeBackend({}), Policy.from_entries(
        frozenset({policy.COMMENT_CREATE}), parse_allowlist(DOC_URL)))
    assert "1 file(s)" in repr(scoped)
    assert "unrestricted" in repr(PolicyBackend(FakeBackend({}), Policy.default()))


def test_every_file_scoped_gate_receives_a_file_id():
    """`Gate.file_scoped` is a claim about the method's first argument. If a gated method
    ever stops taking one, the wrapper fails closed — this asserts the claim is true today
    for every entry, so that failure never reaches a user."""
    import inspect

    from csa_google_workspace.policy import _GATES
    for name, gate in _GATES.items():
        if gate.capability is None or not gate.file_scoped:
            continue
        first = list(inspect.signature(getattr(Backend, name)).parameters)[1]
        assert first == "file_id", f"{name} is file_scoped but its first parameter is {first!r}"
