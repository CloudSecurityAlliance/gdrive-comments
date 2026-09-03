"""An assigned comment is visible: `assignee_email` and `mentioned_emails` (#398).

**The library did exactly what its own README warned against.** That section says:

> `mentionedEmailAddresses` and `assigneeEmailAddress` exist but only if you ask. Omit them from
> the field mask and structured @mentions look like they do not exist. We concluded exactly that
> in an early probe and were wrong.

And `_CF` omitted both, with zero occurrences of either in `src/`. So an **assignment** — the one
comment state that carries an obligation rather than an opinion — read as an ordinary comment, and
*"which comments are assigned to me"* could not be answered at all.

Three things MEASURED against live Google on 2026-09-03 shape these tests:

* both fields are **real**: a mask accepts them where `action` and an invented name are refused;
* **`fields=*` OMITS them**, so the wildcard is not a way to discover they exist — which is why
  the fix is naming them in the mask and why a test asserts the mask keeps naming them;
* they are **read-only**: `comments.create` accepts either in the body, returns **200**, and
  stores neither. Third instance of that pattern in one day, after `keepForever` and the anchor
  trap, so it is asserted here as a documented property rather than left to be rediscovered.

Replies carry both too, and `quotedFileContent` is refused on a reply — so a reply is not merely a
narrower comment, and its assignee is its own fact.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace._export import REPORTED, comment_rows
from csa_google_workspace.backend import ApiBackend, FakeBackend
from csa_google_workspace.comments import Comment, Reply

DOC = "application/vnd.google-apps.document"
F = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
BOB, ANA = "bob@example.com", "ana@example.com"


def raw(**kw):
    d = {"id": "c1", "content": "please fix", "author": {"displayName": "A"}}
    d.update(kw)
    return d


class TestTheModelCarriesThem:
    def test_an_assigned_comment_reports_its_assignee(self):
        c = Comment.from_api(raw(assigneeEmailAddress=BOB))
        assert c.assignee_email == BOB

    def test_mentions_come_back_as_a_tuple(self):
        c = Comment.from_api(raw(mentionedEmailAddresses=[BOB, ANA]))
        assert c.mentioned_emails == (BOB, ANA)

    def test_absent_is_None_and_an_empty_tuple_not_a_crash(self):
        """Drive omits both when unset, which is the overwhelmingly common case."""
        c = Comment.from_api(raw())
        assert c.assignee_email is None and c.mentioned_emails == ()

    def test_a_reply_carries_its_OWN_assignee(self):
        """Reassignment happens on a reply, so this is not the parent's value repeated."""
        r = Reply.from_api({"id": "r1", "content": "over to you", "assigneeEmailAddress": ANA})
        assert r.assignee_email == ANA

    def test_a_thread_can_change_hands_across_its_replies(self):
        """The sequence is the information: the last assigned row is the current owner."""
        c = Comment.from_api(raw(assigneeEmailAddress=BOB, replies=[
            {"id": "r1", "content": "not mine"},
            {"id": "r2", "content": "taking it", "assigneeEmailAddress": ANA}]))
        assert [c.assignee_email, c.replies[0].assignee_email, c.replies[1].assignee_email] \
            == [BOB, None, ANA]


class TestTheFieldsAreNamedInTheMask:
    """The actual defect was the mask, not the model. Asserted against `ApiBackend`'s own
    constant, because `FakeBackend` never sees a field mask and so cannot catch this."""

    @pytest.mark.parametrize("name", ["mentionedEmailAddresses", "assigneeEmailAddress"])
    def test_the_comment_mask_names_it_at_the_TOP_LEVEL(self, name):
        """Sliced before `replies(`, not searched with `in`.

        The first version of this test asserted `name in ApiBackend._CF` and a mutation
        removing the TOP-LEVEL request passed it — because the same name survives inside the
        nested replies spec, so the substring was still present. That is exactly the failure
        CLAUDE.md names: *never ask whether the right string is present*. A comment's own
        assignee and its replies' assignees are two requests, and one can go missing while
        the other keeps the test green.
        """
        top_level = ApiBackend._CF[:ApiBackend._CF.index("replies(")]
        assert name in top_level, (
            f"{name} is not requested for the COMMENT itself (it may still be requested for "
            f"replies, which is a different field). Drive will not return it, and an assigned "
            f"comment reads as an ordinary one - `fields=*` does NOT include it either")

    @pytest.mark.parametrize("name", ["mentionedEmailAddresses", "assigneeEmailAddress"])
    def test_the_reply_mask_names_it_too(self, name):
        assert name in ApiBackend._RF, f"{name} is missing from the reply mask"

    def test_the_comment_mask_requests_them_inside_replies_as_well(self):
        """`_CF` fetches replies nested, so the nested spec needs them independently of
        `_RF` - a real trap, since the two look interchangeable and are not."""
        nested = ApiBackend._CF[ApiBackend._CF.index("replies("):]
        for name in ("mentionedEmailAddresses", "assigneeEmailAddress"):
            assert name in nested, f"{name} missing from the nested replies spec in _CF"


class TestTheyReachBothConsumerSurfaces:
    def _ws(self, comments):
        return Workspace(FakeBackend({F: {"id": F, "name": "n", "mimeType": DOC}},
                                     comments={F: comments},
                                     documents={F: {"body": {"content": []}}}))

    def test_the_mcp_result_carries_them(self):
        from csa_google_workspace.mcp._schemas import comment_out
        doc = self._ws([raw(assigneeEmailAddress=BOB, mentionedEmailAddresses=[ANA])]).open(F)
        out = comment_out(doc.comments.all()[0])
        assert out["assignee_email"] == BOB
        assert out["mentioned_emails"] == [ANA]

    def test_a_reply_in_the_mcp_result_carries_them(self):
        from csa_google_workspace.mcp._schemas import comment_out
        doc = self._ws([raw(replies=[{"id": "r1", "content": "yours",
                                      "assigneeEmailAddress": ANA}])]).open(F)
        assert comment_out(doc.comments.all()[0])["replies"][0]["assignee_email"] == ANA

    def test_the_register_has_the_column(self):
        assert "assigned_to" in REPORTED and "mentions" in REPORTED

    def test_the_register_fills_it_in(self):
        doc = self._ws([raw(assigneeEmailAddress=BOB, mentionedEmailAddresses=[ANA, BOB])]).open(F)
        _, rows, _ = comment_rows(doc, list(doc.comments.all()))
        assert rows[0]["assigned_to"] == BOB
        assert rows[0]["mentions"] == f"{ANA}, {BOB}"

    def test_an_unassigned_comment_leaves_the_cell_EMPTY_not_the_word_None(self):
        """A register is read by people. `"None"` in a cell is a bug that looks like data."""
        doc = self._ws([raw()]).open(F)
        _, rows, _ = comment_rows(doc, list(doc.comments.all()))
        assert rows[0]["assigned_to"] == "" and rows[0]["mentions"] == ""


class TestThePiiIsRedactedFromRepr:
    """Invariant 2: these objects get logged by embedders, and these fields are the email
    addresses of real collaborators — exactly what `Author.email` is already omitted for."""

    def test_a_comment_repr_shows_no_address(self):
        c = Comment.from_api(raw(assigneeEmailAddress=BOB, mentionedEmailAddresses=[ANA]))
        assert BOB not in repr(c) and ANA not in repr(c)

    def test_but_it_still_says_WHETHER_it_is_assigned(self):
        """Redaction must not cost the fact that an obligation exists — that is the part a
        log reader needs, and it discloses nothing about who."""
        assigned = repr(Comment.from_api(raw(assigneeEmailAddress=BOB)))
        assert "assigned=True" in assigned
        assert "assigned=False" in repr(Comment.from_api(raw()))

    def test_a_reply_repr_shows_no_address_either(self):
        r = Reply.from_api({"id": "r1", "content": "x", "assigneeEmailAddress": BOB,
                            "mentionedEmailAddresses": [ANA]})
        assert BOB not in repr(r) and ANA not in repr(r)
        assert "assigned=True" in repr(r) and "mentions=1" in repr(r)
