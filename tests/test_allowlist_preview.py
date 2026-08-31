"""What does this configuration actually point at, and is it still there?

**A4, the two remaining #82 items — and they are one feature.** "Allowlist dry-run" and
"dead-entry detection" were tracked separately; resolving each entry against Drive answers both,
because a dead entry is simply what a dry-run finds. Building them apart would have meant two
tools that each walk the list and call Drive.

Two things it is for:

1. **A bare file id is opaque to a human.** `1oW1BM…` tells you nothing, and the operator's own
   `# CCM v5 mapping` comment is an *unverified claim sitting next to a permission* — paste the
   wrong URL under the right label and it actively misleads. The fetched name is evidence; the
   typed one is decoration. Both are reported, and they are not the same field.
2. **A silently dead entry is a policy that says less than its author believes.** A trashed file
   still resolves by id, so nothing complains; the entry just quietly stops covering anything.

**The `*` case answers honestly rather than enumerating.** "Everything your account can reach" is
not a list, and faking one would be worse than the startup warning that already says so.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import exceptions as exc
from csa_google_workspace.allowlist import (
    AllowlistError,
    Listing,
    parse_setting,
    preview,
)

DOC = "1oW1BMdocdocdocdocdocdocdocdocdocdocdocdoc"
SHEET = "1sheetsheetsheetsheetsheetsheetsheetsheet"
GONE = "1gonegonegonegonegonegonegonegonegonegone"
HIDDEN = "1hiddenhiddenhiddenhiddenhiddenhiddenhidd"

SETTING = (
    f"https://docs.google.com/document/d/{DOC}/edit      # CCM v5 mapping, per WG lead\n"
    f"https://docs.google.com/spreadsheets/d/{SHEET}/edit # AICM tracker\n"
    f"https://docs.google.com/document/d/{GONE}/edit\n"
    f"https://docs.google.com/document/d/{HIDDEN}/edit    # someone else's\n"
)

META = {
    DOC: {"id": DOC, "name": "CCM v5 Mapping", "mimeType": "application/vnd.google-apps.document"},
    SHEET: {"id": SHEET, "name": "AICM Tracker",
            "mimeType": "application/vnd.google-apps.spreadsheet", "trashed": True},
}


def fetch(file_id):
    if file_id in META:
        return META[file_id]
    if file_id == HIDDEN:
        raise exc.AccessError("insufficient permission")
    raise exc.NotFoundError(f"file '{file_id}' not found")


def previewed():
    return preview(parse_setting(SETTING, variable="CSA_GW_ALLOWLIST_READ"), fetch)


class TestItNamesWhatTheIdsPointAt:
    def test_the_name_comes_from_drive_not_the_comment(self):
        """The whole point. The operator wrote "CCM v5 mapping"; Drive says "CCM v5 Mapping".
        They agree here, and the value is that they are checked rather than assumed."""
        entry = previewed().entries[0]
        assert entry.name == "CCM v5 Mapping"
        assert entry.reason == "CCM v5 mapping, per WG lead"

    def test_the_fetched_name_and_the_typed_reason_are_separate_fields(self):
        """Never merged. One is evidence, the other is a claim, and collapsing them would hide
        exactly the mismatch this tool exists to surface."""
        entry = previewed().entries[0]
        assert entry.name != entry.reason

    def test_the_type_is_reported_so_a_wrong_paste_is_visible(self):
        """"I meant the spreadsheet" is a real mistake, and it is invisible in a bare id."""
        assert [e.type for e in previewed().entries[:2]] == ["document", "spreadsheet"]

    def test_an_entry_with_no_comment_has_no_reason(self):
        assert previewed().entries[2].reason is None

    def test_the_line_number_survives(self):
        """A 40-entry list in a JSON `env` block is not something you scan; the line number is
        how somebody finds the one to fix."""
        assert [e.line for e in previewed().entries] == [1, 2, 3, 4]


class TestDeadEntriesAreWhatThisFinds:
    def test_a_trashed_file_is_reported_as_trashed_not_ok(self):
        """Dead-entry detection, and it needed no separate feature. A trashed file still
        resolves by id, so nothing else in the system would ever complain."""
        entry = previewed().entries[1]
        assert entry.status == "trashed"
        assert entry.name == "AICM Tracker", "still name it - that is how you know which one died"

    def test_a_missing_file_is_unreachable(self):
        assert previewed().entries[2].status == "unreachable"

    def test_a_forbidden_file_is_also_unreachable_but_says_why(self):
        """Different cause, same consequence: the policy names a file it cannot act on. The
        detail distinguishes "deleted" from "not yours", which need different fixes."""
        entry = previewed().entries[3]
        assert entry.status == "unreachable"
        assert "permission" in (entry.detail or "")

    def test_unreachable_entries_have_no_name(self):
        """Nothing was fetched, so there is nothing to report. Falling back to the typed reason
        here would present a claim as a finding."""
        assert previewed().entries[2].name is None

    def test_the_counts_roll_up(self):
        """So a caller can say "3 of 4 entries are dead" without recounting a list."""
        p = previewed()
        assert (p.ok, p.dead) == (1, 3)

    def test_dead_is_true_when_anything_is_wrong(self):
        assert previewed().has_dead_entries


class TestTheUnrestrictedCaseIsNotFaked:
    def test_star_reports_unrestricted_and_enumerates_nothing(self):
        """"Everything your account can reach" is not a list. Enumerating a Drive to fake one
        would be slow, incomplete, and a different answer than the truth."""
        p = preview(parse_setting("*", variable="CSA_GW_ALLOWLIST_READ"), fetch)
        assert p.unrestricted is True
        assert p.entries == ()
        assert (p.ok, p.dead) == (0, 0)

    def test_it_does_not_call_drive_at_all(self):
        """There is nothing to resolve, and a preview that made API calls to say "everything"
        would be a slow way to print a constant."""
        def explode(file_id):
            raise AssertionError("fetched something while unrestricted")
        preview(parse_setting("*", variable="CSA_GW_ALLOWLIST_READ"), explode)

    def test_a_setting_that_lists_nothing_never_reaches_preview_at_all(self):
        """The parser refuses it rather than returning an empty listing — "unusable" means
        *nothing permitted*, and it is raised so it cannot be mistaken for a quiet default.
        Asserted here because it is why `preview` has no "empty setting" branch to get wrong."""
        with pytest.raises(AllowlistError):
            parse_setting("# only a comment\n", variable="CSA_GW_ALLOWLIST_READ")

    def test_an_empty_listing_is_still_not_unrestricted(self):
        """`nothing permitted` and `everything permitted` are the two ends, and #82's whole
        design rests on never confusing them. A `Scope.nothing()` carries exactly this shape."""
        p = preview(Listing(all_files=False, entries=()), fetch)
        assert p.unrestricted is False
        assert p.entries == ()


class TestReprRedaction:
    def test_the_reason_is_not_in_repr(self):
        """The operator's comment may name people or unannounced work — `Entry.__repr__`
        already redacts it, and this must not undo that by logging the same text."""
        r = repr(previewed().entries[0])
        assert "per WG lead" not in r

    def test_the_document_name_is_not_in_repr_either(self):
        """A document TITLE is content: "Q3 layoffs planning" leaks the thing the id hid."""
        r = repr(previewed().entries[0])
        assert "CCM v5 Mapping" not in r

    def test_repr_keeps_what_an_audit_needs(self):
        r = repr(previewed().entries[0])
        assert DOC in r and "status='ok'" in r


class TestOneFetchPerEntry:
    def test_it_does_not_refetch(self):
        """A 200-entry list should cost 200 calls, not 400. Asserted because the natural way to
        write `status` and `name` is two passes."""
        calls = []

        def counting(file_id):
            calls.append(file_id)
            return fetch(file_id)

        preview(parse_setting(SETTING, variable="X"), counting)
        assert len(calls) == 4
        assert len(set(calls)) == 4

    def test_a_duplicate_url_is_fetched_once(self):
        """The same document listed twice is one file. Parsing may or may not dedupe; the
        preview must not multiply API calls either way."""
        setting = (f"https://docs.google.com/document/d/{DOC}/edit\n"
                   f"https://docs.google.com/document/d/{DOC}/edit?usp=sharing\n")
        calls = []

        def counting(file_id):
            calls.append(file_id)
            return fetch(file_id)

        preview(parse_setting(setting, variable="X"), counting)
        assert len(set(calls)) == 1, "the same id was fetched more than once"


class TestAnUnexpectedErrorIsNotSwallowed:
    def test_an_unrelated_exception_propagates(self):
        """`unreachable` means Drive answered "no". A bug in the fetcher, a network failure, or
        a rate limit is not a fact about the entry, and reporting it as one would turn an
        outage into a report that the operator's list is broken."""
        def boom(file_id):
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError):
            preview(parse_setting(SETTING, variable="X"), boom)
