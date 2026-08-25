"""Folding comment threads into document text.

Anchoring is by unique quoted-text match, not by position: the Drive anchor is an opaque
range id (CLAUDE.md fact 3), so there is no index to insert at. Ambiguous or absent quotes
degrade to an unanchored listing rather than guessing a location."""
from csa_google_workspace.mcp import _inline


class _A:
    def __init__(self, name): self.display_name = name


class _R:
    def __init__(self, author, content): self.author, self.content = _A(author), content


class _C:
    def __init__(self, cid, content, quoted=None, resolved=False, replies=(), cell=None):
        self.id, self.content, self.quoted_text = cid, content, quoted
        self.author, self.resolved, self.replies = _A("Jane Doe"), resolved, list(replies)
        self.location = type("L", (), {"cell": cell})() if cell else None


TEXT = "The revenue was 4.2M last quarter. The margin held.\n"


def test_a_unique_quote_gets_an_inline_marker():
    out = _inline.inline_comments(TEXT, [_C("c1", "check this", quoted="4.2M")])
    assert "4.2M[[C1]]" in out


def test_the_thread_block_carries_content_replies_and_state():
    out = _inline.inline_comments(TEXT, [
        _C("c1", "check this", quoted="4.2M", replies=[_R("Kurt", "fixed")])])
    assert "[C1]" in out and "Jane Doe: check this" in out and "Kurt: fixed" in out


def test_an_absent_quote_is_listed_as_unanchored_not_guessed():
    out = _inline.inline_comments(TEXT, [_C("c1", "hm", quoted="nowhere in the text")])
    assert "[[C1]]" not in out
    assert "not anchored" in out and "hm" in out


def test_an_ambiguous_quote_is_not_anchored():
    """"The" appears twice; inserting after the first would be a guess."""
    out = _inline.inline_comments(TEXT, [_C("c1", "which one?", quoted="The")])
    assert "[[C1]]" not in out and "not anchored" in out


def test_a_sheets_comment_is_located_by_cell():
    out = _inline.inline_comments("a,b\n", [_C("c1", "wrong total", cell="B11")])
    assert "B11" in out


def test_resolved_state_is_stated():
    out = _inline.inline_comments(TEXT, [_C("c1", "done", quoted="margin", resolved=True)])
    assert "resolved" in out


def test_a_soft_deleted_comment_does_not_render_as_none():
    """Soft delete strips content AND author (probe-verified); both models are Optional."""
    c = _C("c1", None, quoted="margin"); c.author = None
    out = _inline.inline_comments(TEXT, [c])
    assert "(deleted)" in out and "None" not in out


def test_no_comments_returns_the_text_unchanged():
    assert _inline.inline_comments(TEXT, []) == TEXT


def test_the_block_is_labelled_untrusted():
    out = _inline.inline_comments(TEXT, [_C("c1", "x", quoted="margin")])
    assert "untrusted" in out.lower()


def test_threads_are_numbered_in_order():
    out = _inline.inline_comments(TEXT, [_C("c1", "a", quoted="revenue"),
                                         _C("c2", "b", quoted="margin")])
    assert "revenue[[C1]]" in out and "margin[[C2]]" in out
