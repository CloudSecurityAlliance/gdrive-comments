"""Permissions: a per-file, uniform Drive concern, so a mixin beside CommentsMixin."""
import pytest

from csa_google_workspace import Permission, Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
PRES = "application/vnd.google-apps.presentation"

PERMS = [
    {"id": "p1", "type": "user", "role": "owner", "displayName": "Kurt S",
     "emailAddress": "kurt@example.org"},
    {"id": "p2", "type": "user", "role": "commenter", "displayName": "Reviewer",
     "emailAddress": "rev@example.org"},
    {"id": "p3", "type": "domain", "role": "writer", "domain": "example.org"},
    {"id": "p4", "type": "anyone", "role": "reader"},
]


def _doc(mime=DOC, perms=PERMS):
    be = FakeBackend({"f": {"id": "f", "name": "F", "mimeType": mime, "webViewLink": "https://x"}},
                     permissions={"f": perms})
    return Workspace(be).open("f")


def test_permissions_are_parsed_from_the_api_shape():
    perms = _doc().permissions
    assert [p.id for p in perms] == ["p1", "p2", "p3", "p4"]
    assert perms[0].email == "kurt@example.org" and perms[0].display_name == "Kurt S"
    assert perms[2].domain == "example.org" and perms[2].email is None


def test_can_write_covers_writer_and_above_but_not_commenter():
    perms = {p.id: p for p in _doc().permissions}
    assert perms["p1"].can_write and perms["p3"].can_write       # owner, writer
    assert not perms["p2"].can_write and not perms["p4"].can_write  # commenter, reader


def test_is_public_detects_anyone_with_the_link():
    perms = {p.id: p for p in _doc().permissions}
    assert perms["p4"].is_public
    assert not perms["p1"].is_public


def test_the_mixin_is_uniform_across_document_types():
    """One Drive API for all three types — the same reason comments are a mixin."""
    for mime in (DOC, SHEET, PRES):
        assert len(_doc(mime).permissions) == 4


def test_a_missing_file_still_raises_not_found():
    be = FakeBackend({})
    with pytest.raises(exc.NotFoundError):
        Workspace(be)._backend.list_permissions("nope")


def test_no_permissions_is_an_empty_list_not_an_error():
    assert _doc(perms=[]).permissions == []


def test_repr_does_not_leak_the_email():
    """Same rule as Author: email is PII, embedders log these objects. It is still on the
    attribute and still returned by the tool — the tool is *about* who has access."""
    p = Permission.from_api(PERMS[0])
    text = repr(p)
    assert "kurt@example.org" not in text and "Kurt S" not in text
    assert "owner" in text and "named=True" in text


def test_repr_says_when_a_grant_names_nobody():
    assert "named=False" in repr(Permission.from_api(PERMS[3]))


def test_deleted_and_pending_owner_are_carried():
    p = Permission.from_api({"id": "x", "type": "user", "role": "writer",
                             "deleted": True, "pendingOwner": True})
    assert p.deleted and p.pending_owner
