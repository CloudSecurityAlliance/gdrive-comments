"""The `authenticate` tool: browser consent driven from inside the MCP client."""
from __future__ import annotations

import uuid

import anyio
from mcp.server import MCPServer
from mcp.server.elicitation import AcceptedUrlElicitation
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from ... import exceptions as exc
from ...auth import load_cached_credentials, token_path_for
from .._auth_flow import build_flow, consent_url, finish, start_loopback
from .._config import Settings
from .._schemas import AuthOut
from ._base import WRITE


def register_auth_tools(app: MCPServer, settings: Settings) -> None:
    """The `authenticate` tool: browser consent driven from inside the MCP client.

    MCP's own OAuth is for HTTP transports and authenticates the *client to the server*; we
    need the opposite — this server authorizing outbound to Google. For stdio the spec says
    to take credentials from the environment, which is what `login` does. **URL-mode
    elicitation** (added in revision `2026-07-28`) is the sanctioned way to do it in-band:
    the server hands the client a URL to send the user to, and the sensitive exchange
    happens out-of-band, never through the model's context.

    Falls back cleanly. A client without URL elicitation — Claude Desktop today — gets a
    plain instruction to run `login` in a terminal, which is exactly the behaviour before
    this tool existed. And because both clients share one token file, a user who
    authenticates here in Claude Code has also authenticated Claude Desktop.
    """

    @app.tool(annotations=WRITE)
    async def authenticate(ctx: Context, force: bool = False) -> AuthOut:
        """Authorize this server to reach your Google Drive, via your browser.

        Call this when another tool reports missing credentials. Use force=True to
        re-authorize (for example if the cached token belongs to the wrong account)."""
        if not force:
            try:
                await anyio.to_thread.run_sync(
                    lambda: load_cached_credentials(settings.token_path, settings.read_only))
            except exc.AuthError:
                pass
            else:
                return {"status": "already_authorized",
                        "detail": f"A usable token is already cached at "
                                  f"{token_path_for(settings.token_path, settings.read_only)}. "
                                  f"Pass force=true to authorize again."}

        if not settings.client_secrets:
            raise ToolError(
                "No OAuth client is configured, so a consent URL cannot be built. Set "
                "CSA_GW_CLIENT_SECRETS or place the client at "
                "~/.csa_google_workspace/client_secret.json, then run "
                "`csa-google-workspace-mcp login` in a terminal.")

        loopback = start_loopback()
        try:
            flow = build_flow(settings.client_secrets, settings.read_only,
                              loopback.redirect_uri_base)
            url = consent_url(flow)
            elicitation_id = uuid.uuid4().hex

            try:
                answer = await ctx.elicit_url(
                    message=("Authorize access to your Google Docs, Sheets and Slides. "
                             "You will sign in as yourself and reach only your own files."),
                    url=url,
                    elicitation_id=elicitation_id,
                )
            except Exception as e:
                # No URL elicitation support (or the client refused the request). Degrade to
                # the terminal path rather than failing outright.
                raise ToolError(
                    "This client cannot open an authorization URL for me. Run "
                    "`csa-google-workspace-mcp login` in a terminal instead — it does the "
                    "same thing, once.") from e

            if not isinstance(answer, AcceptedUrlElicitation):
                return {"status": "declined",
                        "detail": "Authorization was not started. Nothing changed."}

            # Wait off-thread: the listener blocks, and the event loop must not.
            redirect = await anyio.to_thread.run_sync(lambda: loopback.wait(300.0))
            if not redirect:
                return {"status": "timed_out",
                        "detail": "No response from the browser within 5 minutes. "
                                  "Call authenticate again when ready."}

            await anyio.to_thread.run_sync(
                # token_path_for, not settings.token_path: a read-only posture reads a
                # separate cache (#185), and writing the token where nothing reads it
                # would make CSA_GW_READ_ONLY=1 impossible to satisfy.
                lambda: finish(flow, redirect,
                               token_path_for(settings.token_path, settings.read_only)))
            await ctx.session.send_elicit_complete(elicitation_id)
            return {"status": "authorized",
                    "detail": f"Token cached at "
                        f"{token_path_for(settings.token_path, settings.read_only)}. "
                        f"Both Claude Code and "
                              f"Claude Desktop use this file, so neither needs authorizing again."}
        finally:
            loopback.close()
