"""The discovery tools, and one guard for a whole class of silent bug."""
import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp.server import create_server

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
FILES = {
    "a": {"id": "a", "name": "Budget 2026", "mimeType": SHEET, "webViewLink": "https://x/d/a",
          "modifiedTime": "2026-08-20T10:00:00.000Z"},
    "b": {"id": "b", "name": "CCM mapping notes", "mimeType": DOC, "webViewLink": "https://x/d/b",
          "modifiedTime": "2026-08-24T10:00:00.000Z"},
}


def _server():
    return create_server(lambda: Workspace(FakeBackend(dict(FILES))))


def _call(app, name, args):
    return asyncio.run(app.call_tool(name, args))


def test_search_files_returns_refs_with_type_and_link():
    out = _call(_server(), "search_files", {"query": "name contains 'CCM'"}).structured_content
    assert [f["id"] for f in out["files"]] == ["b"]
    assert out["files"][0]["type"] == "document"
    assert out["files"][0]["url"].endswith("/d/b")
    assert out["files"][0]["modified_time"].startswith("2026-08-24")


def test_search_files_takes_no_file_id():
    """The first tools on the account axis — nothing to open yet."""
    tools = {t.name: t for t in asyncio.run(_server().list_tools())}
    assert "fileId" not in tools["search_files"].input_schema["properties"]
    assert tools["search_files"].input_schema["required"] == ["query"]


def test_search_files_honours_limit():
    out = _call(_server(), "search_files",
                {"query": "name contains 'e'", "limit": 1}).structured_content
    assert len(out["files"]) == 1


def test_search_files_rejects_an_empty_query_readably():
    with pytest.raises(ToolError):
        _call(_server(), "search_files", {"query": " "})


def test_list_recent_files_is_newest_first():
    out = _call(_server(), "list_recent_files", {}).structured_content
    assert [f["id"] for f in out["files"]] == ["b", "a"]


def test_list_recent_files_rejects_an_unknown_order_by():
    with pytest.raises(ToolError) as e:
        _call(_server(), "list_recent_files", {"orderBy": "whenever"})
    assert "lastModified" in str(e.value)


def test_the_search_description_carries_the_mime_type_guidance():
    """Borrowed from the claude.ai connector: models put type words in `name` clauses."""
    tools = {t.name: t for t in asyncio.run(_server().list_tools())}
    desc = tools["search_files"].description
    assert "mimeType" in desc and "vnd.google-apps.document" in desc
    assert "{" not in desc                    # no unsubstituted placeholder reached the model


def test_every_tool_has_a_non_empty_description():
    """A guard for a silent failure that already happened once: an f-string is not a string
    literal, so using one as a docstring leaves __doc__ as None. The tool still registers,
    the schema still looks right, and the model gets no guidance at all."""
    undescribed = [t.name for t in asyncio.run(_server().list_tools())
                   if not (t.description or "").strip()]
    assert undescribed == []
