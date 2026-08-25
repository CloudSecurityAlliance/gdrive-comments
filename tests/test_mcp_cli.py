"""Entry-point guards (spec §5.1, §9).

These are the tests that would have caught the *original* design, in which `main()` called
`from_oauth` and so could reach `InstalledAppFlow.run_local_server()` — which `print()`s the
consent URL to stdout and blocks on a browser redirect. Under stdio, stdout carries JSON-RPC,
so that corrupts the protocol stream before the session even starts.

Asserting the error text alone would not be enough: it would still pass if consent ran first
and merely failed afterwards. The invariant is the *absence* of the interactive flow, so that
is what is asserted.
"""
import contextlib
import io

import pytest

from csa_google_workspace import auth
from csa_google_workspace.mcp import cli


class Ran(Exception):
    """Raised in place of actually serving stdio."""


def _no_flow(*args, **kwargs):
    raise AssertionError("the stdio server must never construct the interactive OAuth flow")


@pytest.fixture
def no_interactive_flow(monkeypatch):
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", _no_flow)


@pytest.fixture
def captured_server(monkeypatch):
    """Replace MCPServer.run so the server 'starts' without occupying stdio."""
    started = {}

    def fake_run(self, transport="stdio", **kwargs):
        started["transport"] = transport
        raise Ran
    monkeypatch.setattr("mcp.server.MCPServer.run", fake_run)
    return started


# --- the server never prompts ------------------------------------------------

def test_server_starts_with_no_token_and_never_prompts(tmp_path, no_interactive_flow, captured_server):
    """A missing token must NOT stop the server starting: an MCP client renders a startup
    crash as an opaque failure, so the remedy has to reach the user as a tool error instead."""
    env = {"CSA_GW_TOKEN": str(tmp_path / "absent.json")}
    with pytest.raises(Ran):
        cli.main([], env)
    assert captured_server["transport"] == "stdio"


def test_server_startup_writes_nothing_to_stdout(tmp_path, no_interactive_flow, captured_server):
    """stdout is the JSON-RPC channel. One stray print corrupts the stream."""
    env = {"CSA_GW_TOKEN": str(tmp_path / "absent.json")}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(Ran):
        cli.main([], env)
    assert buf.getvalue() == ""


def test_help_goes_to_stderr_not_stdout(capsys):
    assert cli.main(["--help"], {}) == 0
    out, err = capsys.readouterr()
    assert out == "" and "usage:" in err


def test_unknown_argument_is_rejected_on_stderr(capsys):
    assert cli.main(["frobnicate"], {}) == 2
    out, err = capsys.readouterr()
    assert out == "" and "unknown argument" in err


# --- login is the only interactive path --------------------------------------

def test_login_without_client_secrets_reports_the_missing_variable(capsys):
    assert cli.main(["login"], {}) == 2
    assert "CSA_GW_CLIENT_SECRETS" in capsys.readouterr().err


def test_login_runs_the_interactive_flow(tmp_path, monkeypatch, capsys):
    """The mirror image: `login` *must* reach from_oauth, since that is its whole job."""
    called = {}

    def fake_from_oauth(client_secrets, token_path, read_only=False, force=False):
        called["args"] = (client_secrets, token_path, read_only)
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth", fake_from_oauth)

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(tmp_path / "t.json")}
    assert cli.main(["login"], env) == 0
    assert called["args"] == ("/tmp/cs.json", str(tmp_path / "t.json"), False)


def test_read_only_env_reaches_login(tmp_path, monkeypatch):
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda cs, tp, read_only=False, force=False: called.setdefault("ro", read_only))
    cli.main(["login"], {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json",
                         "CSA_GW_TOKEN": str(tmp_path / "t.json"), "CSA_GW_READ_ONLY": "1"})
    assert called["ro"] is True


# --- `login --force` and cached-token reporting -------------------------------
#
# Real failure this addresses: a token cache can hold a perfectly valid token that was
# minted by a DIFFERENT OAuth client (same scopes, different project). `login` then
# reuses it and truthfully reports success, while every API call runs against the wrong
# project's quota and consent screen. Nothing errors; it is just silently wrong.

def test_login_reuses_a_usable_token_without_opening_a_browser(tmp_path, monkeypatch, capsys):
    token = tmp_path / "token.json"
    token.write_text('{"client_id": "111-abc.apps.googleusercontent.com"}')
    monkeypatch.setattr("csa_google_workspace.mcp._login._client_id_of",
                        lambda p: "111-abc.apps.googleusercontent.com")
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: object())
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda *a, **k: called.setdefault("ran", True))

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(token)}
    assert cli.main(["login"], env) == 0
    assert "ran" not in called                       # no browser
    assert "already authorized" in capsys.readouterr().out.lower()


def test_login_force_reauthorizes_even_with_a_usable_token(tmp_path, monkeypatch):
    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: object())
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda cs, tp, read_only=False, force=False: called.update(force=force))

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(token)}
    assert cli.main(["login", "--force"], env) == 0
    assert called["force"] is True                   # cache bypassed, consent re-run


def test_login_warns_when_the_cached_token_is_from_another_client(tmp_path, monkeypatch, capsys):
    """The exact trap: valid token, right scopes, wrong project."""
    token = tmp_path / "token.json"
    token.write_text('{"client_id": "945234811286-old.apps.googleusercontent.com"}')
    monkeypatch.setattr("csa_google_workspace.mcp._login._client_id_of",
                        lambda p: "548573610436-new.apps.googleusercontent.com")
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: object())
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda *a, **k: None)

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(token)}
    assert cli.main(["login"], env) == 0
    err = capsys.readouterr().err.lower()
    assert "different oauth client" in err and "--force" in err


def test_login_with_no_token_authorizes_without_needing_force(tmp_path, monkeypatch):
    token = tmp_path / "absent.json"
    monkeypatch.setattr("csa_google_workspace.mcp._login.load_cached_credentials",
                        lambda tp, ro: (_ for _ in ()).throw(auth.AuthError("no cached credentials")))
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda cs, tp, read_only=False, force=False: called.update(ran=True))

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(token)}
    assert cli.main(["login"], env) == 0
    assert called["ran"] is True


def test_force_flag_is_documented_in_usage(capsys):
    cli.main(["--help"], {})
    assert "--force" in capsys.readouterr().err


# --- branded OAuth success page ----------------------------------------------
#
# google_auth_oauthlib hardcodes `Content-type: text/plain` in _RedirectWSGIApp, so the
# public `success_message=` argument cannot carry markup. Swapping the class for the
# duration of the flow is the only seam — and a cosmetic upgrade must never be able to
# break authorization, so the fallback behaviour is tested as carefully as the feature.

def _wsgi_environ(uri="http://127.0.0.1:8080/?code=abc&state=xyz"):
    from urllib.parse import urlsplit
    u = urlsplit(uri)
    return {"wsgi.url_scheme": "http", "HTTP_HOST": u.netloc, "PATH_INFO": u.path,
            "QUERY_STRING": u.query, "SERVER_NAME": "127.0.0.1", "SERVER_PORT": "8080"}


def test_branded_page_is_served_as_html():
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    with _branded_success_page():
        app = flow._RedirectWSGIApp("ignored")
        captured = {}
        body = app(_wsgi_environ(), lambda status, headers: captured.update(dict(headers)))

    assert "text/html" in captured["Content-type"]
    html = b"".join(body).decode()
    assert "<!doctype html>" in html.lower()
    assert "authorized" in html.lower()


def test_branded_page_still_records_the_redirect_uri():
    """The security-relevant half: last_request_uri carries the auth code and the state
    oauthlib validates. Losing it would break the flow, not just the styling."""
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    with _branded_success_page():
        app = flow._RedirectWSGIApp("ignored")
        app(_wsgi_environ("http://127.0.0.1:8080/?code=THECODE&state=THESTATE"),
            lambda status, headers: None)

    assert "code=THECODE" in app.last_request_uri
    assert "state=THESTATE" in app.last_request_uri


def test_the_original_class_is_restored_afterwards():
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    before = flow._RedirectWSGIApp
    with _branded_success_page():
        assert flow._RedirectWSGIApp is not before
    assert flow._RedirectWSGIApp is before


def test_original_class_is_restored_even_when_the_flow_raises():
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    before = flow._RedirectWSGIApp
    with pytest.raises(RuntimeError):
        with _branded_success_page():
            raise RuntimeError("consent blew up")
    assert flow._RedirectWSGIApp is before


def test_missing_upstream_class_degrades_instead_of_failing(monkeypatch):
    """If upstream renames the private class, login must keep working — plainer, not broken."""
    import google_auth_oauthlib.flow as flow

    from csa_google_workspace.mcp._login import _branded_success_page

    monkeypatch.delattr(flow, "_RedirectWSGIApp")
    with _branded_success_page():
        pass                                    # must not raise


def test_page_embeds_the_logo_and_avoids_the_superseded_orange():
    """Brand: the logo is inlined verbatim (recoloring is forbidden), and the page adds no
    orange of its own — so the asset's older #F98526 never sits beside the current #FF7A00."""
    from csa_google_workspace.mcp._success_page import SUCCESS_HTML

    assert "<svg" in SUCCESS_HTML and "Cloud Security Alliance" in SUCCESS_HTML
    assert "#00549F" in SUCCESS_HTML                      # CSA Blue B500
    assert "#FF7A00" not in SUCCESS_HTML.upper().replace("#F98526", "")
