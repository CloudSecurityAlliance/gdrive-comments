"""The account axis: `workspace.files`.

The first thing here that is not reached through `open(file_id)`, because you cannot open a
file you are trying to find. Shape per
docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md.
"""
from datetime import datetime

import pytest

from csa_google_workspace import Workspace, exceptions
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.files import FileRef

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
PDF = "application/pdf"

FILES = {
    "a": {"id": "a", "name": "Budget 2026", "mimeType": SHEET,
          "webViewLink": "https://x/spreadsheets/d/a", "modifiedTime": "2026-08-20T10:00:00.000Z"},
    "b": {"id": "b", "name": "CCM mapping notes", "mimeType": DOC,
          "webViewLink": "https://x/document/d/b", "modifiedTime": "2026-08-24T10:00:00.000Z"},
    "c": {"id": "c", "name": "Old budget", "mimeType": SHEET,
          "webViewLink": "https://x/spreadsheets/d/c", "modifiedTime": "2026-01-01T10:00:00.000Z",
          "trashed": True},
    "d": {"id": "d", "name": "Scan of a contract", "mimeType": PDF,
          "webViewLink": "https://x/file/d/d", "modifiedTime": "2026-08-22T10:00:00.000Z"},
}


def _ws(read_only=False):
    return Workspace(FakeBackend(dict(FILES)), read_only=read_only)


def test_search_matches_on_name():
    hits = _ws().files.search("name contains 'budget'")
    assert [h.id for h in hits] == ["a"]                 # 'c' is trashed


def test_search_excludes_trashed_by_default():
    """files.list returns binned items unless the query says otherwise — a real footgun."""
    assert "c" not in [h.id for h in _ws().files.search("name contains 'budget'")]


def test_a_query_mentioning_trashed_is_left_alone():
    hits = _ws().files.search("name contains 'budget' and trashed = true")
    assert [h.id for h in hits] == ["c"]


def test_search_honours_a_mime_type_clause():
    hits = _ws().files.search(f"mimeType = '{DOC}'")
    assert [h.id for h in hits] == ["b"]


def test_search_rejects_an_empty_query_rather_than_listing_the_drive():
    with pytest.raises(ValueError):
        _ws().files.search("   ")


def test_limit_is_honoured_across_pages():
    """FakeBackend pages at page_size, so a limit above it must walk nextPageToken."""
    many = {str(i): {"id": str(i), "name": f"note {i}", "mimeType": DOC,
                     "webViewLink": f"https://x/document/d/{i}"} for i in range(250)}
    ws = Workspace(FakeBackend(many))
    assert len(ws.files.search("name contains 'note'", limit=150)) == 150


def test_limit_below_one_is_rejected():
    with pytest.raises(ValueError):
        _ws().files.search("name contains 'x'", limit=0)


def test_recent_returns_newest_first():
    assert [h.id for h in _ws().files.recent(limit=2)] == ["b", "d"]


def test_recent_rejects_an_unknown_order_by():
    with pytest.raises(ValueError) as e:
        _ws().files.recent(order_by="whenever")
    assert "lastModified" in str(e.value)


def test_modified_time_is_parsed_to_a_datetime():
    hit = next(h for h in _ws().files.recent(limit=5) if h.id == "b")
    assert isinstance(hit.modified_time, datetime) and hit.modified_time.year == 2026


def test_type_is_none_for_a_file_the_library_cannot_open():
    hit = next(h for h in _ws().files.recent(limit=5) if h.id == "d")
    assert hit.type is None and hit.openable is False
    assert hit.mime_type == PDF                          # still reported, not hidden


def test_open_upgrades_a_hit_to_a_typed_document():
    hit = next(h for h in _ws().files.search("name contains 'CCM'"))
    doc = hit.open()
    assert doc.type == "document" and doc.id == "b"


def test_open_on_an_unopenable_type_is_a_clear_error():
    hit = next(h for h in _ws().files.recent(limit=5) if h.id == "d")
    with pytest.raises(exceptions.UnsupportedOperation):
        hit.open()


def test_open_carries_read_only_through():
    hit = next(h for h in _ws(read_only=True).files.search("name contains 'CCM'"))
    with pytest.raises(exceptions.ReadOnlyError):
        hit.open().create_comment("nope")


def test_a_hand_built_fileref_is_detached():
    ref = FileRef(id="x", name="n", mime_type=DOC, url="u")
    with pytest.raises(exceptions.DetachedError):
        ref.open()


def test_repr_does_not_leak_the_file_name():
    """A title can be as sensitive as the contents ("2026 Layoff Plan"), and embedders log
    these objects — same rule as the comment models."""
    ref = FileRef(id="x", name="2026 Layoff Plan", mime_type=DOC, url="u")
    text = repr(ref)
    assert "Layoff" not in text and "name_chars=16" in text and "x" in text
