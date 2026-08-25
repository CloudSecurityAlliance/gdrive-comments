"""Tool surface of the MCP server, driven in-process against FakeBackend (spec §9).

No network, no credentials, no subprocess: `create_server` takes a provider, so tests
inject `Workspace(FakeBackend(...))` exactly where the CLI injects a real one.
"""
import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace, exceptions
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp.server import create_server

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
FILES = {
    "f": {"id": "f", "name": "Draft", "mimeType": DOC, "webViewLink": "https://x/document/d/f/edit"},
    "s": {"id": "s", "name": "Grid", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s/edit"},
}
DOCUMENTS = {"f": {"body": {"content": [
    {"paragraph": {"elements": [{"textRun": {"content": "hello world\n"}}]}},
]}}}


def build(read_only=False, backend=None):
    be = backend or FakeBackend(FILES, documents=DOCUMENTS)
    ws = Workspace(be, read_only=read_only)
    return create_server(lambda: ws), be


def call(server, name, **args):
    return asyncio.run(server.call_tool(name, args))


# --- registration -----------------------------------------------------------

def test_expected_tools_are_registered():
    server, _ = build()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"open_document", "list_comments", "read_text", "create_comment",
            "reply_comment", "resolve_comment", "comments_by_cell"} <= names


def test_read_tools_are_annotated_read_only():
    server, _ = build()
    by_name = {t.name: t for t in asyncio.run(server.list_tools())}
    for name in ("open_document", "list_comments", "read_text"):
        assert by_name[name].annotations.read_only_hint is True, name
    assert by_name["create_comment"].annotations.read_only_hint is False


# --- reads ------------------------------------------------------------------

def test_open_document_returns_identity():
    server, _ = build()
    out = call(server, "open_document", file="f").structured_content
    assert out["id"] == "f" and out["name"] == "Draft" and out["type"] == "document"


def test_open_document_accepts_a_share_url():
    server, _ = build()
    out = call(server, "open_document", file="https://docs.google.com/document/d/f/edit").structured_content
    assert out["id"] == "f"


def test_read_text_returns_document_text():
    server, _ = build()
    assert "hello world" in call(server, "read_text", file="f").structured_content["text"]


def test_list_comments_returns_structured_comments():
    server, be = build()
    be.create_comment("f", "please review")
    rows = call(server, "list_comments", file="f").structured_content["comments"]
    assert len(rows) == 1 and rows[0]["content"] == "please review" and rows[0]["resolved"] is False


def test_list_comments_can_filter_to_open_only():
    server, be = build()
    done = be.create_comment("f", "handled")
    be.create_reply("f", done["id"], action="resolve")
    be.create_comment("f", "still open")
    rows = call(server, "list_comments", file="f", resolved=False).structured_content["comments"]
    assert [r["content"] for r in rows] == ["still open"]


# --- writes -----------------------------------------------------------------

def test_create_comment_writes_through():
    server, be = build()
    out = call(server, "create_comment", file="f", content="from the agent").structured_content
    assert out["content"] == "from the agent"
    assert [c["content"] for c in be.list_comments("f")] == ["from the agent"]


def test_reply_and_resolve():
    server, be = build()
    c = be.create_comment("f", "q")
    call(server, "reply_comment", file="f", comment_id=c["id"], content="a")
    call(server, "resolve_comment", file="f", comment_id=c["id"])
    assert be.get_comment("f", c["id"])["resolved"] is True


def test_read_only_server_refuses_writes_with_a_clear_error():
    server, _ = build(read_only=True)
    with pytest.raises(ToolError) as ei:
        call(server, "create_comment", file="f", content="nope")
    assert "read-only" in str(ei.value).lower()


# --- error mapping ----------------------------------------------------------

def test_unknown_file_is_a_tool_error_not_a_crash():
    server, _ = build()
    with pytest.raises(ToolError) as ei:
        call(server, "read_text", file="missing")
    assert "not found" in str(ei.value).lower()


def test_capability_a_type_lacks_is_a_clear_tool_error():
    """comments_by_cell is Sheets-only; asking a Doc must explain, not traceback."""
    server, _ = build()
    with pytest.raises(ToolError) as ei:
        call(server, "comments_by_cell", file="f", cell="A1")
    assert "document" in str(ei.value).lower()


def test_missing_credentials_surface_as_a_tool_error_with_the_login_remedy():
    """The server starts fine without a token; the problem appears where the user can read it."""
    def provider():
        raise exceptions.AuthError("no cached credentials; run `csa-google-workspace-mcp login` to authorize")
    server = create_server(provider)
    with pytest.raises(ToolError) as ei:
        call(server, "read_text", file="f")
    assert "login" in str(ei.value)
