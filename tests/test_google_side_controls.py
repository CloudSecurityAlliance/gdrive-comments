"""The controls Google enforces, as against the ones this server is configured with (#336–#338).

**These are a different KIND of control, and that difference is the whole point.** `policy.py`
builds a ceiling below Drive's and binds only *our own* calls — `README.md` concedes that running
the built-in Drive connector alongside this server "defeats the scoping entirely". A protected
range, `writersCanShare=false` or `driveMembersOnly` binds **every** client.

So *"Google will refuse this"* is a categorically stronger answer than *"our policy is configured
not to"*, and until now the library could not read any of it: the Drive field mask omitted both
restriction fields, `spreadsheets.get` omitted `protectedRanges`, and there was no `drives` surface
at all.

**Read-only by construction rather than by configuration.** There is no write counterpart anywhere
and no capability that would enable one, because a control this broad is the last thing an agent
should be able to lift — an agent that can remove the protection on a document has not been
restricted. Asserted below, so "we chose not to" cannot quietly become "we forgot to gate it".
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import ApiBackend, FakeBackend
from csa_google_workspace.restrictions import FileRestrictions, SharedDrive

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
D, S, DRIVE = "d", "s", "0ADriveId"


def ws(**kw):
    files = {D: {"id": D, "name": "D", "mimeType": DOC},
             S: {"id": S, "name": "S", "mimeType": SHEET}}
    return Workspace(FakeBackend(files, **kw))


class TestProtectedRanges:
    """#336. A protected range is the control that actually prevents an edit."""

    def grid(self, **kw):
        return {"sheets": [{"properties": {"sheetId": 0, "title": "Budget"},
                            "protectedRanges": [kw]}]}

    def test_a_range_is_reported_in_A1_with_its_tab(self):
        """A `GridRange` of zero-based half-open indices is not something a caller should have
        to decode, and `sheetId` alone does not say which tab it names."""
        doc = ws(spreadsheets={S: self.grid(
            protectedRangeId=1, range={"sheetId": 0, "startRowIndex": 1, "endRowIndex": 10,
                                       "startColumnIndex": 1, "endColumnIndex": 4})}).open(S)
        (pr,) = doc.protected_ranges
        assert pr.a1_range == "'Budget'!B2:D10"

    def test_the_conversion_is_half_open_and_zero_based(self):
        """The off-by-one here is silent and produces a plausible-looking range, which is why
        it is asserted on its own: startRow 0 -> row 1, and endRow 3 EXCLUSIVE -> row 3."""
        doc = ws(spreadsheets={S: self.grid(
            protectedRangeId=1, range={"sheetId": 0, "startRowIndex": 0, "endRowIndex": 3,
                                       "startColumnIndex": 0, "endColumnIndex": 1})}).open(S)
        assert doc.protected_ranges[0].a1_range == "'Budget'!A1:A3"

    def test_a_range_with_no_bounds_is_the_WHOLE_TAB(self):
        """The commonest protection there is. Missing bounds mean unbounded, not zero — and
        rendering it as `A1:A1` would report a whole-sheet lock as a single cell."""
        doc = ws(spreadsheets={S: self.grid(
            protectedRangeId=1, range={"sheetId": 0})}).open(S)
        assert doc.protected_ranges[0].a1_range == "'Budget'"

    def test_warning_only_is_NOT_enforcement(self):
        """Google's UI calls it "show a warning when editing this range" — it permits the edit.
        Treating it as protection is the mistake this field exists to prevent."""
        doc = ws(spreadsheets={S: self.grid(
            protectedRangeId=1, warningOnly=True, range={"sheetId": 0})}).open(S)
        pr = doc.protected_ranges[0]
        assert pr.warning_only is True and pr.enforced is False

    def test_ABSENT_warningOnly_means_ENFORCED(self):
        """Google omits the field when false, so defaulting to True would silently downgrade
        every real protection to a warning — the dangerous direction."""
        doc = ws(spreadsheets={S: self.grid(
            protectedRangeId=1, range={"sheetId": 0})}).open(S)
        assert doc.protected_ranges[0].enforced is True

    def test_a_sheet_with_no_protection_reports_an_empty_list(self):
        doc = ws(spreadsheets={S: {"sheets": [
            {"properties": {"sheetId": 0, "title": "Budget"}}]}}).open(S)
        assert doc.protected_ranges == []

    def test_the_repr_shows_neither_the_description_nor_the_editors(self):
        """A description is author-written text about the document and an editor list is
        collaborator PII — invariant 2 applies to both."""
        doc = ws(spreadsheets={S: self.grid(
            protectedRangeId=1, description="Q3 LAYOFF PLAN", range={"sheetId": 0},
            editors={"users": ["bob@example.com"]})}).open(S)
        text = repr(doc.protected_ranges[0])
        assert "LAYOFF" not in text and "bob@example.com" not in text
        assert "editors=1" in text, "the COUNT survives; the addresses do not"

    @pytest.mark.parametrize("fragment", [
        # The OPEN PAREN is load-bearing. `"protectedRanges" in mask` passed a mutation that
        # renamed the field to `protectedRangesX(` — the substring survived. That is the second
        # time today a mask test was written as bare containment and passed a rename (#398 was
        # the first, where a name survived inside the nested `replies(` spec). Assert the
        # request, not the presence of a word.
        "protectedRanges(",
        "warningOnly",
        "requestingUserCanEdit",
        "editors(",
    ])
    def test_the_field_mask_actually_requests_them(self, fragment):
        """`FakeBackend` never sees a mask, so nothing above would catch the real backend
        failing to ask — the same seam that hid #391 and #398."""
        assert fragment in ApiBackend._SHEET_FIELDS, (
            f"{fragment!r} is not in the spreadsheet field mask, so Drive will not return it "
            f"and every protected range will read as absent")


class TestFileRestrictions:
    """#337. Google's version of our `file.share` gate, and it cannot be routed around."""

    def test_both_halves_are_reported(self):
        meta = {"id": D, "name": "D", "mimeType": DOC,
                "copyRequiresWriterPermission": True, "writersCanShare": False,
                "capabilities": {"canEdit": True, "canShare": False}}
        r = FileRestrictions.from_api(meta)
        assert r.copy_requires_writer_permission is True   # configured
        assert r.writers_can_share is False                # configured
        assert r.can_edit is True and r.can_share is False  # effective

    def test_unknown_is_distinguishable_from_unrestricted(self):
        """`None` never means unrestricted. Reporting a restriction we could not read as
        absent is the dangerous direction, and `unknown` is how a caller tells them apart."""
        assert FileRestrictions.from_api({}).unknown is True
        assert FileRestrictions.from_api({"writersCanShare": True}).unknown is False

    def test_a_single_false_capability_is_not_unknown(self):
        """The bug this would be: `all(... is None)` written as `not any(...)` would call a
        file with every capability denied "unknown", i.e. maximally restricted read as
        unread."""
        r = FileRestrictions.from_api({"capabilities": {"canEdit": False}})
        assert r.unknown is False and r.can_edit is False

    @pytest.mark.parametrize("field", ["copyRequiresWriterPermission", "writersCanShare"])
    def test_the_field_mask_requests_the_restrictions(self, field):
        assert field in ApiBackend._FILE_FIELDS

    def test_the_mask_requests_the_effective_capabilities_too(self):
        for cap in ("canEdit", "canComment", "canShare", "canCopy"):
            assert cap in ApiBackend._FILE_FIELDS, cap


class TestSharedDrive:
    """#338. The broadest Google-side controls, and previously unreachable entirely."""

    def raw(self, **restrictions):
        return {"id": DRIVE, "name": "Working Group", "restrictions": restrictions}

    def test_the_restrictions_are_reported(self):
        d = SharedDrive.from_api(self.raw(driveMembersOnly=True, domainUsersOnly=False,
                                          sharingFoldersRequiresOrganizerPermission=True))
        assert d.drive_members_only is True
        assert d.domain_users_only is False
        assert d.sharing_folders_requires_organizer_permission is True

    def test_the_download_restriction_is_reported(self):
        """NOT in the request that asked for this, and set on real drives — which is why the
        field list was probed against the API rather than transcribed from the issue."""
        d = SharedDrive.from_api(self.raw(
            downloadRestriction={"restrictedForReaders": True, "restrictedForWriters": False}))
        assert d.download_restricted_for_readers is True
        assert d.download_restricted_for_writers is False

    def test_a_drive_with_no_restrictions_reports_None_not_False(self):
        """Absent is not the same as switched off: an unread restriction must not read as
        permission, so nothing here fabricates a `False`."""
        d = SharedDrive.from_api({"id": DRIVE, "name": "n"})
        assert d.drive_members_only is None and d.domain_users_only is None

    def test_the_repr_does_not_print_the_drive_name(self):
        """A drive name identifies an organisational unit — a third-party string, treated like
        the others rather than printed into an embedder's logs."""
        d = SharedDrive.from_api(self.raw(driveMembersOnly=True))
        assert "Working Group" not in repr(d)
        assert "members_only=True" in repr(d)

    def test_it_is_reachable_from_the_workspace(self):
        w = ws(drives={DRIVE: self.raw(driveMembersOnly=True)})
        assert w.shared_drive(DRIVE).drive_members_only is True


class TestTheyAreReadOnlyByConstruction:
    """Not "we chose not to expose a write" but "there is nothing to expose".

    Asserted because the distinction erodes silently: a write method added later would be
    gated by whatever `_GATES` entry somebody reached for, and this records that the intent
    was never to have one.
    """

    FORBIDDEN = ("update_drive", "add_protected_range", "remove_protected_range",
                 "update_protected_range", "set_file_restrictions",
                 "update_file_restrictions")

    @pytest.mark.parametrize("name", FORBIDDEN)
    def test_no_backend_write_exists(self, name):
        assert not hasattr(ApiBackend, name), (
            f"{name} exists. These controls bound EVERY client, so an agent able to change one "
            f"has not been restricted - if this is now wanted, it needs its own capability and "
            f"a decision recorded, not a quiet addition.")

    @pytest.mark.parametrize("name", FORBIDDEN)
    def test_no_gate_declares_one(self, name):
        from csa_google_workspace.policy import _GATES
        assert name not in _GATES

    def test_the_read_is_gated_as_a_listing_not_as_a_file(self):
        """A shared drive is not a file, so the file allowlist has no id to match — the same
        shape as `get_label_definition`, which T41 records for the same reason."""
        from csa_google_workspace.policy import _GATES
        gate = _GATES["get_drive"]
        assert gate.capability is None, "a read costs no capability"
        assert gate.file_scoped is False, "a drive id is not a file id"
