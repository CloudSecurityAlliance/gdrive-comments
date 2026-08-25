"""The in-band `authenticate` tool (URL elicitation).

MCP's own OAuth is HTTP-only and points the other way (client -> server); this server
authorizes outbound to Google. URL-mode elicitation, added in revision 2026-07-28, is the
sanctioned way to drive that from inside a client: the server hands over a URL and the
sensitive exchange happens out-of-band, never through the model's context.

The fallback matters as much as the feature: Claude Desktop has no elicitation support
today, so a client that cannot do it must get a usable instruction rather than a failure.
"""
import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace, exceptions
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import Settings
from csa_google_workspace.mcp.server import create_server

DOC = "application/vnd.google-apps.document"
FILES = {"f": {"id": "f", "name": "D", "mimeType": DOC, "webViewLink": "u"}}


def build(**settings_kw):
    ws = Workspace(FakeBackend(FILES))
    settings = Settings(**{"token_path": "/nonexistent/token.json", **settings_kw})
    return create_server(lambda: ws, settings=settings)


def call(server, name, **args):
    return asyncio.run(server.call_tool(name, args))


def test_authenticate_is_registered_and_not_read_only():
    server = build()
    by_name = {t.name: t for t in asyncio.run(server.list_tools())}
    assert "authenticate" in by_name
    assert by_name["authenticate"].annotations.read_only_hint is False


def test_authenticate_without_a_client_says_how_to_use_login():
    """No client secrets means no consent URL can be built. Point at the terminal path."""
    server = build(client_secrets=None)
    with pytest.raises(ToolError) as ei:
        call(server, "authenticate")
    msg = str(ei.value)
    assert "login" in msg and "CSA_GW_CLIENT_SECRETS" in msg


def test_authenticate_reports_when_a_token_already_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("csa_google_workspace.mcp._tools.auth.load_cached_credentials",
                        lambda tp, ro: object())
    out = call(build(client_secrets=str(tmp_path / "c.json")),
               "authenticate").structured_content
    assert out["status"] == "already_authorized"
    assert "force" in out["detail"]


def test_force_skips_the_already_authorized_shortcut(tmp_path, monkeypatch):
    """With force=True it must proceed to the flow even though a token is cached."""
    monkeypatch.setattr("csa_google_workspace.mcp._tools.auth.load_cached_credentials",
                        lambda tp, ro: object())
    server = build(client_secrets=None)          # no client -> fails *past* the shortcut
    with pytest.raises(ToolError) as ei:
        call(server, "authenticate", force=True)
    assert "No OAuth client" in str(ei.value)


def test_client_without_url_elicitation_gets_the_terminal_instruction(tmp_path, monkeypatch):
    """Claude Desktop today. A missing capability must not surface as a crash."""
    secrets = tmp_path / "c.json"; secrets.write_text("{}")
    monkeypatch.setattr("csa_google_workspace.mcp._tools.auth.load_cached_credentials",
                        lambda tp, ro: (_ for _ in ()).throw(exceptions.AuthError("none")))
    monkeypatch.setattr("csa_google_workspace.mcp._tools.auth.build_flow",
                        lambda cs, ro, uri: object())
    monkeypatch.setattr("csa_google_workspace.mcp._tools.auth.consent_url",
                        lambda flow: "https://accounts.google.com/o/oauth2/auth?x=1")

    async def unsupported(*a, **k):
        raise RuntimeError("elicitation/create not supported")
    monkeypatch.setattr("mcp.server.mcpserver.Context.elicit_url", unsupported)

    with pytest.raises(ToolError) as ei:
        call(build(client_secrets=str(secrets)), "authenticate")
    assert "login" in str(ei.value) and "terminal" in str(ei.value)
