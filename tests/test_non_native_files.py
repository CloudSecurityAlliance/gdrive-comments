"""Uploaded files — .docx, .pdf, .png — and what this server can honestly say about them.

Found by a plain question: *"if I upload a docx and call read_file_content on it, what
happens?"* The answer was worse than the README claimed, in three ways at once.

**Everything failed, not just text extraction.** `read_file_content`, `get_file_metadata` and
`download_file_content` all route through `open()`, which MIME-dispatches on a three-entry table
and raises before any type-specific logic runs. So *"what is this file?"* — pure metadata, no
parsing — failed on a PDF.

**The README promised code that did not exist.** Its API table listed
`drive.files.get(alt=media)` for uploaded files. There was no `alt=media` anywhere in `src/`.

**`search_files` and `open()` disagreed.** Search deliberately returns non-native files —
`FileRef.type` is `None` for a PDF, and its docstring says *"pretending otherwise would hide
results"*. So search said "here it is" and nothing could then tell you anything about it.

The split that fixes it is one this repo already made once, for `update_file` and `trash_file`:
**metadata and raw bytes go through the account axis**, which has never cared about file type,
and only *text extraction* needs `open()`. Reading TEXT out of a PDF or an image stays
unsupported on purpose — that means parsing untrusted binary formats in-process, on the read
path `SECURITY.md` names as the primary risk. Handing over bytes parses nothing.
"""
from __future__ import annotations

import asyncio
import base64

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOC, DOCX, PDF = "gdoc1", "docx1", "pdf1"
BYTES = b"PK\x03\x04 not really a docx"


def build():
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Google Doc",
               "mimeType": "application/vnd.google-apps.document"},
         # webViewLink included because the real backend requests it - a fixture that omits
         # it tests a file Drive never returns.
         DOCX: {"id": DOCX, "name": "Report.docx", "mimeType": DOCX_MIME,
                "webViewLink": "https://drive.google.com/file/d/docx1/view"},
         PDF: {"id": PDF, "name": "Paper.pdf", "mimeType": "application/pdf",
               "webViewLink": "https://drive.google.com/file/d/pdf1/view"}},
        documents={DOC: {"body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": "hello\n"}}]}}]}}},
        media={DOCX: BYTES, PDF: b"%PDF-1.7 fake"})
    return create_server(lambda: Workspace(backend),
                         settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, args)).structured_content


class TestMetadataWorksOnAnything:
    """"What is this file?" is metadata. There is nothing to parse and nothing to refuse."""

    @pytest.mark.parametrize("file_id,name", [(DOCX, "Report.docx"), (PDF, "Paper.pdf")])
    def test_it_identifies_an_uploaded_file(self, file_id, name):
        out = call(build(), "get_file_metadata", fileId=file_id)
        assert out["name"] == name
        assert out["url"]

    def test_the_type_is_null_not_a_lie(self, file_id=PDF):
        """`None` means "not a type this library can open", which is what `FileRef` has always
        reported for a search hit. Inventing a type here would contradict search."""
        out = call(build(), "get_file_metadata", fileId=PDF)
        assert out["type"] is None
        assert out["mime_type"] == "application/pdf"

    def test_there_is_no_snippet_and_it_says_why(self):
        """A snippet is extracted text, and there is no text extraction for a PDF. Silently
        omitting it would look like an empty document."""
        out = call(build(), "get_file_metadata", fileId=PDF)
        assert out["snippet"] is None
        assert "pdf" in out["detail"].lower() or "text" in out["detail"].lower()

    def test_a_google_doc_still_gets_its_snippet(self):
        out = call(build(), "get_file_metadata", fileId=DOC)
        assert out["type"] == "document"
        assert out["snippet"] and "hello" in out["snippet"]


class TestDownloadingRawBytes:
    """The capability the README already promised: `drive.files.get(alt=media)`."""

    def test_an_uploaded_file_downloads_as_itself(self):
        out = call(build(), "download_file_content", fileId=DOCX)
        assert base64.b64decode(out["content_base64"]) == BYTES
        assert out["mime_type"] == DOCX_MIME

    def test_an_export_format_is_refused_for_an_uploaded_file(self):
        """`exportMimeType` is Drive's Google-native conversion. Asking for markdown from a
        .docx would silently return the .docx, which is worse than a refusal."""
        with pytest.raises(Exception, match="exportMimeType|Google-native|already"):
            call(build(), "download_file_content", fileId=DOCX, exportMimeType="markdown")

    def test_a_google_doc_still_exports(self):
        out = call(build(), "download_file_content", fileId=DOC,
                   exportMimeType="text/plain")
        assert out["mime_type"] == "text/plain"


class TestReadingTEXTStaysUnsupported:
    """Deliberately. Extracting text from a PDF or an image means parsing an untrusted binary
    format in-process, on the read path SECURITY.md names as the primary risk. Handing over
    bytes parses nothing, which is why one is supported and the other is not."""

    @pytest.mark.parametrize("file_id", [DOCX, PDF])
    def test_read_file_content_refuses(self, file_id):
        from mcp.server.mcpserver.exceptions import ToolError
        with pytest.raises(ToolError):
            call(build(), "read_file_content", fileId=file_id)

    def test_the_refusal_names_the_format_and_what_to_do(self):
        """The old message was the raw mime type and nothing else - it did not say what kind
        of file that is, what this server does read, or what to do about it."""
        with pytest.raises(Exception) as raised:
            call(build(), "read_file_content", fileId=DOCX)
        message = str(raised.value).lower()
        assert "word" in message or "docx" in message, "name the format in human terms"
        assert "google doc" in message, "say what it CAN read"
        assert "download_file_content" in message, "name the tool that does work"

    def test_the_pdf_refusal_names_pdf(self):
        with pytest.raises(Exception) as raised:
            call(build(), "read_file_content", fileId=PDF)
        assert "pdf" in str(raised.value).lower()


class TestSearchAndMetadataNoLongerDisagree:
    def test_a_file_search_finds_can_also_be_identified(self):
        """The inconsistency this fixes: search said "here is a PDF" and nothing could then
        answer a single question about it."""
        app = build()
        found = call(app, "search_files", query="name contains 'Paper'")["files"]
        assert found
        for hit in found:
            meta = call(app, "get_file_metadata", fileId=hit["id"])
            assert meta["id"] == hit["id"]
