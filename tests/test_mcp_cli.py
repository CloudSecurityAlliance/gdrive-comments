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

    def fake_from_oauth(client_secrets, token_path, read_only=False):
        called["args"] = (client_secrets, token_path, read_only)
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth", fake_from_oauth)

    env = {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json", "CSA_GW_TOKEN": str(tmp_path / "t.json")}
    assert cli.main(["login"], env) == 0
    assert called["args"] == ("/tmp/cs.json", str(tmp_path / "t.json"), False)


def test_read_only_env_reaches_login(tmp_path, monkeypatch):
    called = {}
    monkeypatch.setattr("csa_google_workspace.workspace.Workspace.from_oauth",
                        lambda cs, tp, read_only=False: called.setdefault("ro", read_only))
    cli.main(["login"], {"CSA_GW_CLIENT_SECRETS": "/tmp/cs.json",
                         "CSA_GW_TOKEN": str(tmp_path / "t.json"), "CSA_GW_READ_ONLY": "1"})
    assert called["ro"] is True
