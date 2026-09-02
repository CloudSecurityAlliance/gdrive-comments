"""Search returns who owns a file and when it was made, and can order by any Drive key.

Both were prerequisites for the work-handoff inventory
(`docs/superpowers/specs/2026-09-02-work-handoff-inventory.md`), and both were the same shape of
gap: **Drive would have returned the fact for free in the same call, and we did not ask.**
`_SEARCH_FIELDS` requested five fields, so an inventory over hundreds of files would have paid one
extra `files.get` per row for `owners` and `createdTime`.

The ordering half is sharper than it looks. `createdTime` was *filterable* through the query
string all along — `createdTime > '2026-01-01'` always worked — but **not sortable**, because
`ORDER_BY` held three keys and Drive has eleven. So "the oldest thing they made" was unreachable
while "things made after January" was not, which is a strange seam to leave in an API.

Three properties are asserted here that are easy to get wrong later:

**`None` and `()` mean different things for `owners`.** A file in a shared drive genuinely has no
owners — the drive owns it — so an empty tuple is a real answer. `None` means the call did not
ask. Collapsing them would report every shared-drive file as "ownership unknown".

**`last_modifying_user` is the most recent editor only.** It answers *"who touched this last"* and
never *"did this person ever edit it"*. The tests name that, because the inventory spec depends on
the distinction and a reader who assumes otherwise builds a wrong sweep.

**`asc` is accepted and then dropped.** Ascending is Drive's own default, so echoing it back is
noise — but refusing an explicit `name asc` to save four characters would be worse.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import FileActor, Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.files import ORDER_BY, ORDER_KEYS

DOC = "application/vnd.google-apps.document"
F = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
ALICE = {"displayName": "Alice Adams", "emailAddress": "alice@example.org", "me": False}
BOB = {"displayName": "Bob Brown", "emailAddress": "bob@example.org", "me": True}


def ws(**extra):
    raw = {"id": F, "name": "Budget", "mimeType": DOC, "webViewLink": f"https://x/{F}",
           "modifiedTime": "2026-08-01T10:00:00Z"}
    raw.update(extra)
    return Workspace(FakeBackend({F: raw}))


class TestTheFieldsAnInventoryNeeds:
    def test_created_time_comes_back(self):
        got = ws(createdTime="2024-03-04T09:00:00Z").files.search("name contains 'Budget'")[0]
        assert got.created_time is not None
        assert (got.created_time.year, got.created_time.month) == (2024, 3)

    def test_owners_come_back_with_name_and_email(self):
        got = ws(owners=[ALICE]).files.search("name contains 'Budget'")[0]
        assert got.owners == (FileActor("Alice Adams", "alice@example.org", False),)

    def test_several_owners_are_all_reported(self):
        """Drive's `owners` is a list and consumer accounts have reported more than one.
        Taking `[0]` and calling it 'the owner' would quietly drop a co-owner."""
        got = ws(owners=[ALICE, BOB]).files.search("name contains 'Budget'")[0]
        assert got.owners is not None and len(got.owners) == 2

    def test_no_owners_is_an_empty_tuple_not_none(self):
        """The shared-drive case, and the distinction the field exists to preserve: the DRIVE
        owns the file, so `[]` from Drive is a real answer about ownership."""
        got = ws(owners=[], driveId="0ABCdefGHIjklUk9PVA").files.search("name contains 'B'")[0]
        assert got.owners == ()
        assert got.owners is not None, "an empty owner list must not read as 'not asked'"

    def test_unasked_owners_stay_none(self):
        """No `owners` key at all - which is what a response that never requested them looks
        like. Reporting `()` here would assert a fact nothing checked."""
        assert ws().files.search("name contains 'Budget'")[0].owners is None

    def test_drive_id_is_reported_and_none_means_my_drive(self):
        """#338: an inventory that cannot say which drive a file is in mis-attributes work."""
        assert ws(driveId="0ABC").files.search("name contains 'B'")[0].drive_id == "0ABC"
        assert ws().files.search("name contains 'B'")[0].drive_id is None

    def test_last_modifying_user_is_the_most_recent_editor_only(self):
        """Named explicitly because the inventory spec turns on it. This field cannot answer
        'did Alice ever edit this' - if Alice edited and Bob edited after, Drive reports Bob
        and Alice is invisible. That is why edited/commented are separate signals and why the
        complete answer needs revisions."""
        got = ws(lastModifyingUser=BOB).files.search("name contains 'B'")[0]
        assert got.last_modifying_user == FileActor("Bob Brown", "bob@example.org", True)

    def test_get_one_file_carries_the_same_facts(self):
        """`get()` answers the same question one row at a time, so it asks for the same fields
        - otherwise 'who owns this?' would depend on whether you searched or fetched."""
        got = ws(owners=[ALICE], createdTime="2024-03-04T09:00:00Z").files.get(F)
        assert got.owners is not None and got.created_time is not None


class TestTheActorModel:
    def test_repr_hides_the_email(self):
        """Redacted like every other model here - an owner's email is personal data and
        embedders log these objects. Guarded here as well as in test_repr_redaction."""
        text = repr(FileActor("Alice Adams", "alice@example.org"))
        assert "alice@example.org" not in text and "Alice" not in text
        assert "has_email=True" in text

    def test_a_missing_email_is_visible_rather_than_papered_over(self):
        """Drive usually supplies an email here, unlike a comment author. When it does not,
        that is worth being able to see rather than silently falling back to a name."""
        assert FileActor.from_api({"displayName": "X"}).email is None


class TestOrderingByAnyDriveKey:
    def test_created_time_is_now_sortable(self):
        """The gap this closes: `createdTime` was filterable through the query string all
        along and not sortable, which is a strange seam to leave."""
        assert Workspace(FakeBackend({}))  # sanity
        from csa_google_workspace.files import FileCollection
        assert FileCollection._order("createdTime desc") == "createdTime desc"

    @pytest.mark.parametrize("key", sorted(ORDER_KEYS - set(ORDER_BY)))
    def test_every_drive_key_is_accepted(self, key):
        """Excludes the one key that is also a legacy alias - see the collision test below.
        Derived by set difference rather than hand-listed, so a future alias cannot make this
        parametrize silently disagree with the code."""
        from csa_google_workspace.files import FileCollection
        assert FileCollection._order(key) == key

    def test_the_one_colliding_name_resolves_to_the_alias(self):
        """`recency` is BOTH a legacy alias meaning `recency desc` and a real Drive key whose
        bare form Drive reads as ASCENDING. The alias wins on purpose: `recency` is the
        documented default of `recent()` and is published to the model, so letting the bare
        key win would silently reverse every existing caller's results.

        Found by this file's own parametrize, which is the argument for enumerating the key
        set rather than spot-checking three of them."""
        from csa_google_workspace.files import FileCollection
        assert "recency" in ORDER_KEYS and "recency" in ORDER_BY
        assert FileCollection._order("recency") == "recency desc"
        assert FileCollection._order("recency asc") == "recency", "the escape hatch"

    def test_asc_is_accepted_then_dropped(self):
        """Ascending is Drive's default, so sending it back is noise - but refusing an
        explicit `name asc` would be worse than accepting it."""
        from csa_google_workspace.files import FileCollection
        assert FileCollection._order("name asc") == "name"
        assert FileCollection._order("name desc") == "name desc"

    def test_the_three_legacy_aliases_still_mean_what_they_meant(self):
        """`recent(order_by="recency")` is a documented default and all three are published to
        the model. Each keeps its `desc`, because that is the behaviour callers have."""
        from csa_google_workspace.files import FileCollection
        for alias, expected in ORDER_BY.items():
            assert FileCollection._order(alias) == expected

    @pytest.mark.parametrize("bad", ["whenever", "createdTime sideways", "createdTime desc asc",
                                     "", "   ", "created_time"])
    def test_an_unknown_ordering_is_refused_locally(self, bad):
        """Still validated rather than forwarded. An unknown string reaches Google as a 400
        whose body the caller never sees, so a typo would surface as 'Google rejected the
        request' with nothing to act on."""
        from csa_google_workspace.files import FileCollection
        with pytest.raises(ValueError):
            FileCollection._order(bad)

    def test_the_refusal_names_what_would_have_worked(self):
        from csa_google_workspace.files import FileCollection
        with pytest.raises(ValueError) as raised:
            FileCollection._order("createdTime sideways")
        assert "'asc' or 'desc'" in str(raised.value)

    def test_none_still_means_do_not_send_order_by(self):
        """Drive rejects `orderBy=None`; omitting it is not the same as sending it."""
        from csa_google_workspace.files import FileCollection
        assert FileCollection._order(None) is None
