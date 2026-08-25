"""Export-format resolution. The table is per document type on purpose — see
experiments/export-formats/RESULTS.md finding 2: Slides has no Markdown or HTML export,
so one shared enum would hand two thirds of callers an unfixable 400."""
import pytest

from csa_google_workspace import Workspace, _formats
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
PRES = "application/vnd.google-apps.presentation"


def test_alias_resolves_to_mime_type():
    assert _formats.resolve("markdown", "document") == "text/markdown"
    assert _formats.resolve("pdf", "presentation") == "application/pdf"


def test_mime_type_passes_through_when_supported():
    assert _formats.resolve("text/csv", "spreadsheet") == "text/csv"


def test_alias_is_case_and_space_insensitive():
    assert _formats.resolve("  PDF ", "document") == "application/pdf"


def test_markdown_is_rejected_for_a_presentation():
    """The probe's central finding: Slides cannot export Markdown."""
    with pytest.raises(exc.UnsupportedOperation) as e:
        _formats.resolve("markdown", "presentation")
    assert "presentation" in str(e.value)
    assert "application/pdf" in str(e.value)      # the error lists what IS available


def test_unknown_format_is_rejected():
    with pytest.raises(exc.UnsupportedOperation):
        _formats.resolve("application/x-nonsense", "document")


def test_unknown_document_type_is_rejected():
    with pytest.raises(exc.UnsupportedOperation):
        _formats.resolve("pdf", "drawing")


def test_no_image_export_for_the_three_types():
    """"images" in the roadmap was wrong: only drawings export PNG/JPEG/SVG."""
    for doc_type in ("document", "spreadsheet", "presentation"):
        assert not [m for m in _formats.EXPORT_FORMATS[doc_type] if m.startswith("image/")]


def _ws(mime, exports):
    return Workspace(FakeBackend(
        {"f": {"id": "f", "name": "F", "mimeType": mime, "webViewLink": "https://x"}},
        exports=exports))


def test_export_accepts_an_alias():
    doc = _ws(DOC, {("f", "application/pdf"): b"%PDF-x"}).open("f")
    assert doc.export("pdf") == b"%PDF-x"


def test_as_markdown_decodes_the_drive_conversion():
    doc = _ws(DOC, {("f", "text/markdown"): b"# Title\n\n- a\n"}).open("f")
    assert doc.as_markdown() == "# Title\n\n- a\n"


def test_export_rejects_a_format_the_type_cannot_produce_without_calling_google():
    slides = _ws(PRES, {}).open("f")
    with pytest.raises(exc.UnsupportedOperation):
        slides.export("markdown")


def test_export_formats_lists_the_types_formats():
    assert "text/markdown" in _ws(DOC, {}).open("f").export_formats
    assert "text/markdown" not in _ws(PRES, {}).open("f").export_formats
