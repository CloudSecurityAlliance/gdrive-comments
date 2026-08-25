"""Loopback OAuth pieces for in-band authorization, without `run_local_server()`.

`InstalledAppFlow.run_local_server()` cannot be used here for two reasons: it `print()`s
the consent URL to stdout (which is the JSON-RPC channel), and it blocks the calling
thread until the browser redirect arrives. In-band auth needs the URL as a *value* to
hand to the client, and needs the wait to happen without stalling the event loop.

So the flow is driven directly:

    start_loopback()            -> a listener on 127.0.0.1:<random port>
    authorization_url(flow)     -> the URL to show the user
    wait_for_redirect(listener) -> the full redirect URI, once Google calls back
    flow.fetch_token(authorization_response=...)

`fetch_token` is given the whole redirect URI rather than a bare code, so oauthlib
validates the `state` parameter for us — that check is what stops a CSRF-style injected
authorization code, and losing it would be the easy mistake in hand-rolling this.

Loopback with a random port is Google's documented pattern for desktop clients ("start an
HTTP listener on a random available port"), and no redirect URI needs pre-registering.
The out-of-band copy/paste alternative no longer exists — Google removed it — so a
listener is not optional.
"""
from __future__ import annotations

import threading
import wsgiref.simple_server
import wsgiref.util
from dataclasses import dataclass, field

from ..auth import _write_token, scopes_for
from ._success_page import SUCCESS_HTML


class _Collector:
    """WSGI app that records the redirect URI and shows the branded success page."""

    def __init__(self) -> None:
        self.redirect_uri: str | None = None
        self.arrived = threading.Event()

    def __call__(self, environ, start_response):
        start_response("200 OK", [("Content-type", "text/html; charset=utf-8")])
        self.redirect_uri = wsgiref.util.request_uri(environ)
        self.arrived.set()
        return [SUCCESS_HTML.encode("utf-8")]


@dataclass
class Loopback:
    """A one-shot local listener for the OAuth redirect."""

    port: int
    _server: wsgiref.simple_server.WSGIServer
    _collector: _Collector
    _thread: threading.Thread = field(repr=False)

    @property
    def redirect_uri_base(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def wait(self, timeout: float) -> str | None:
        """Block until the redirect arrives, or `timeout` seconds pass."""
        self._collector.arrived.wait(timeout)
        return self._collector.redirect_uri

    def close(self) -> None:
        try:
            self._server.server_close()
        except OSError:
            pass


def start_loopback() -> Loopback:
    """Bind 127.0.0.1 on a free port and serve exactly one request, off-thread."""
    collector = _Collector()
    # allow_reuse_address off: fail fast rather than silently share a port.
    wsgiref.simple_server.WSGIServer.allow_reuse_address = False
    server = wsgiref.simple_server.make_server("127.0.0.1", 0, collector,
                                               handler_class=_QuietHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    return Loopback(port=server.server_port, _server=server,
                    _collector=collector, _thread=thread)


class _QuietHandler(wsgiref.simple_server.WSGIRequestHandler):
    """wsgiref logs each request to stderr by default; silence it.

    stderr is safe under stdio (only stdout carries JSON-RPC), but a bare access-log line
    in the middle of an MCP session is noise the user cannot act on.
    """

    def log_message(self, format, *args):  # noqa: A002 - signature fixed by the stdlib
        pass


def build_flow(client_secrets: str, read_only: bool, redirect_uri: str):
    """A google_auth_oauthlib Flow pointed at our loopback, with our scopes."""
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(client_secrets, scopes=scopes_for(read_only))
    flow.redirect_uri = redirect_uri
    return flow


def consent_url(flow) -> str:
    """The URL to send the user to. `prompt='consent'` so re-auth actually re-prompts."""
    url, _state = flow.authorization_url(access_type="offline", prompt="consent")
    return url


def finish(flow, redirect_uri: str, token_path: str) -> None:
    """Exchange the redirect for a token and persist it with the usual hardening.

    Passing the full `authorization_response` (not a bare code) is deliberate: oauthlib
    validates the `state` parameter from it.
    """
    flow.fetch_token(authorization_response=redirect_uri)
    _write_token(token_path, flow.credentials)
