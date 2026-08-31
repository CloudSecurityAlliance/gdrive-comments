"""The version a client sees must be the version that is running.

**RR-002**, found by an external audit and true since the server first shipped. `MCPServer`
defaults `version` to `""` and this project never passed it, so every MCP client showed the server
as version-less — while `describe_configuration` correctly reported the real one.

Two sources of truth for the same fact, one of them blank. The blank one is the one clients
display, so it is the one that matters for a bug report: "which version are you running?" had no
answer that a user could read off their client.

**Why a test rather than just the fix.** It is one keyword argument, invisible in review, with a
default that is *falsy rather than absent* — so nothing raised, nothing warned, and the wire
response stayed well-formed. That is precisely the shape that regresses during a refactor of the
constructor call.
"""
from __future__ import annotations

import asyncio

from csa_google_workspace import Workspace, __version__
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server


def server():
    return create_server(lambda: Workspace(FakeBackend({})), settings=settings_from_env({}))


class TestTheVersionIsReported:
    def test_the_server_carries_the_package_version(self):
        assert server().version == __version__

    def test_it_is_not_the_sdk_default(self):
        """`MCPServer` defaults `version` to `""`, which is falsy rather than absent — so the
        omission produced a valid response with a blank field instead of an error."""
        assert server().version != ""

    def test_it_looks_like_a_version(self):
        """A guard against passing something that is merely non-empty. `__version__` is the
        single source of truth (`pyproject.toml` reads it dynamically), so this also catches
        somebody hardcoding a literal here and letting the two drift."""
        parts = server().version.split(".")
        assert len(parts) >= 3, server().version
        assert all(p and p[0].isdigit() for p in parts[:3]), server().version

    def test_it_agrees_with_what_describe_configuration_says(self):
        """The two paths that report a version must not disagree — the whole defect was that one
        of them was blank while the other was right, so equality is the property to hold."""
        out = asyncio.run(server().call_tool("describe_configuration", {}))
        reported = out.structured_content["server_version"]
        assert reported == server().version == __version__

    def test_a_flavour_does_not_change_it(self):
        """`instructions` is composed per flavour at construction, right beside `version` in the
        same call — so a future edit there could plausibly drop one while adjusting the other."""
        for flavour in ("full", "google", "claude"):
            app = create_server(lambda: Workspace(FakeBackend({})),
                                settings=settings_from_env({"CSA_GW_FLAVOUR": flavour}))
            assert app.version == __version__, flavour

    def test_a_server_built_without_settings_still_reports_it(self):
        """The library-embedder path takes a different branch through `create_server`; the
        version is not settings-derived and must not become so."""
        app = create_server(lambda: Workspace(FakeBackend({})))
        assert app.version == __version__
