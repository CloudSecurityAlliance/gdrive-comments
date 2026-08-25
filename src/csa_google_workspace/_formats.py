"""Which export conversions Drive actually offers, per Google document type.

Probed, not remembered: `drive.about.get(fields="exportFormats")` is the same table the
server enforces for `files.export`, so it cannot disagree with itself. See
experiments/export-formats/RESULTS.md (2026-08-25).

The table is keyed by document type because it genuinely differs — a Doc exports Markdown,
a deck does not. One shared enum would hand most callers an unfixable 400.
"""
from __future__ import annotations

from . import exceptions as exc

MARKDOWN = "text/markdown"
PDF = "application/pdf"
PLAIN = "text/plain"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

EXPORT_FORMATS: dict[str, tuple[str, ...]] = {
    "document": (MARKDOWN, "text/x-markdown", PLAIN, "text/html", PDF, "application/rtf",
                 "application/epub+zip", "application/zip", DOCX,
                 "application/vnd.oasis.opendocument.text"),
    "spreadsheet": ("text/csv", "text/tab-separated-values", PDF, "application/zip", XLSX,
                    "application/vnd.oasis.opendocument.spreadsheet",
                    "application/x-vnd.oasis.opendocument.spreadsheet"),
    # Four, and no Markdown, HTML or image among them. The probe's central finding.
    "presentation": (PDF, PLAIN, PPTX, "application/vnd.oasis.opendocument.presentation"),
}

# Models say "pdf", not "application/pdf". Accept both rather than fail a reasonable guess.
ALIASES = {
    "markdown": MARKDOWN, "md": MARKDOWN, "pdf": PDF, "text": PLAIN, "txt": PLAIN,
    "plain": PLAIN, "html": "text/html", "rtf": "application/rtf",
    "epub": "application/epub+zip", "zip": "application/zip", "docx": DOCX,
    "odt": "application/vnd.oasis.opendocument.text", "csv": "text/csv",
    "tsv": "text/tab-separated-values", "xlsx": XLSX,
    "ods": "application/vnd.oasis.opendocument.spreadsheet", "pptx": PPTX,
    "odp": "application/vnd.oasis.opendocument.presentation",
}


def resolve(fmt: str, doc_type: str) -> str:
    """Map a short alias or a mime type to one Drive will accept for `doc_type`.

    Raises `UnsupportedOperation` rather than letting a bad format become a 400 from
    Google, and names the alternatives so the caller can retry without guessing.
    """
    mime = ALIASES.get(fmt.strip().lower(), fmt.strip())
    allowed = EXPORT_FORMATS.get(doc_type)
    if allowed is None:
        raise exc.UnsupportedOperation(f"no export formats are known for {doc_type}s")
    if mime not in allowed:
        raise exc.UnsupportedOperation(
            f"{doc_type}s cannot be exported as {mime!r}. Drive offers: "
            f"{', '.join(sorted(allowed))}")
    return mime
