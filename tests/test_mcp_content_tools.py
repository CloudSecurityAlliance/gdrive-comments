"""The three aligned content tools.

Names and parameter names match Google's Drive MCP server and the claude.ai Drive connector
exactly — see research/drive-mcp-servers-and-api-surface.md. Parameters are camelCase
because the wire contract is, and because a pydantic alias does not work here: it publishes
the right schema and then fails every call.
"""
import asyncio
import base64

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp.server import create_server

DOC = "application/vnd.google-apps.document"
PRES = "application/vnd.google-apps.presentation"
BODY = {"body": {"content": [{"paragraph": {"elements": [
    {"textRun": {"content": "Hello world. This is the body.\n"}}]}}]}}


def _server(mime=DOC, **kw):
    backend = FakeBackend(
        {"f": {"id": "f", "name": "F", "mimeType": mime, "webViewLink": "https://x/d/f"}},
        documents={"f": BODY}, presentations={"f": {"slides": []}}, **kw)
    return create_server(lambda: Workspace(backend))


def _call(app, name, args):
    # asyncio.run, matching tests/test_mcp_server.py's existing `call` helper.
    return asyncio.run(app.call_tool(name, args))


def _structured(result):
    """`structured_content` — snake_case in mcp 2.x; `structuredContent` no longer exists."""
    return result.structured_content


def _names(app):
    return [t.name for t in asyncio.run(app.list_tools())]


# --- get_file_metadata ------------------------------------------------------

def test_get_file_metadata_returns_identity_and_a_snippet():
    out = _structured(_call(_server(), "get_file_metadata", {"fileId": "f"}))
    assert out["id"] == "f" and out["type"] == "document" and out["mime_type"] == DOC
    assert out["snippet"].startswith("Hello world")


def test_get_file_metadata_suppresses_the_snippet_on_request():
    out = _structured(_call(_server(), "get_file_metadata",
                            {"fileId": "f", "excludeContentSnippets": True}))
    assert out["snippet"] is None


def test_get_file_metadata_accepts_a_share_url_not_only_a_bare_id():
    """A strict superset of their contract: users paste URLs."""
    out = _structured(_call(_server(), "get_file_metadata",
                            {"fileId": "https://docs.google.com/document/d/f/edit"}))
    assert out["id"] == "f"


# --- read_file_content -----------------------------------------------------

def test_read_file_content_returns_text():
    out = _structured(_call(_server(), "read_file_content", {"fileId": "f"}))
    assert out["text"].startswith("Hello world")


def test_read_file_content_rejects_tab_on_a_document_with_a_readable_error():
    with pytest.raises(ToolError) as e:
        _call(_server(), "read_file_content", {"fileId": "f", "tab": "Sheet1"})
    assert "spreadsheet" in str(e.value)


def test_read_file_content_can_include_comments():
    app = _server(comments={"f": [
        {"id": "c1", "content": "check this", "quotedFileContent": {"value": "Hello world"},
         "author": {"displayName": "Jane Doe"}, "replies": []}]})
    out = _structured(_call(app, "read_file_content",
                            {"fileId": "f", "includeComments": True}))
    assert "[[C1]]" in out["text"] and "check this" in out["text"]
    assert "untrusted" in out["text"].lower()


def test_read_file_content_without_include_comments_leaves_text_alone():
    app = _server(comments={"f": [
        {"id": "c1", "content": "check this", "quotedFileContent": {"value": "Hello world"},
         "author": {"displayName": "Jane Doe"}, "replies": []}]})
    out = _structured(_call(app, "read_file_content", {"fileId": "f"}))
    assert "[[C1]]" not in out["text"] and "check this" not in out["text"]


# --- download_file_content -------------------------------------------------

def test_download_defaults_to_markdown_for_a_document():
    app = _server(exports={("f", "text/markdown"): b"# Title\n"})
    out = _structured(_call(app, "download_file_content", {"fileId": "f"}))
    assert out["mime_type"] == "text/markdown"
    assert base64.b64decode(out["content_base64"]) == b"# Title\n"
    assert out["size_bytes"] == 8


def test_download_honours_an_explicit_format_alias():
    app = _server(exports={("f", "application/pdf"): b"%PDF-x"})
    out = _structured(_call(app, "download_file_content",
                            {"fileId": "f", "exportMimeType": "pdf"}))
    assert out["mime_type"] == "application/pdf"


def test_download_rejects_an_impossible_format_locally_and_lists_alternatives():
    with pytest.raises(ToolError) as e:
        _call(_server(), "download_file_content",
              {"fileId": "f", "exportMimeType": "application/x-nonsense"})
    assert "text/markdown" in str(e.value)


def test_download_rejects_markdown_for_a_deck():
    """The probe's central finding, reaching the user as a local error not a 400."""
    with pytest.raises(ToolError) as e:
        _call(_server(mime=PRES), "download_file_content",
              {"fileId": "f", "exportMimeType": "markdown"})
    assert "presentation" in str(e.value) and "application/pdf" in str(e.value)


def test_download_refuses_an_oversized_export():
    app = _server(exports={("f", "application/pdf"): b"x" * (10 * 1024 * 1024 + 1)})
    with pytest.raises(ToolError) as e:
        _call(app, "download_file_content", {"fileId": "f", "exportMimeType": "pdf"})
    assert "read_file_content" in str(e.value)


# --- the renames -----------------------------------------------------------

def test_the_old_names_are_gone_and_the_new_ones_are_registered():
    names = _names(_server())
    assert "open_document" not in names and "read_text" not in names
    for expected in ("get_file_metadata", "read_file_content", "download_file_content"):
        assert expected in names


def test_every_content_tool_takes_fileId():
    tools = {t.name: t for t in asyncio.run(_server().list_tools())}
    for name in ("get_file_metadata", "read_file_content", "download_file_content"):
        assert "fileId" in tools[name].input_schema["properties"]
        assert tools[name].input_schema["required"] == ["fileId"]
