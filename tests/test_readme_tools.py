"""The README's tool list must equal what the server registers.

It had drifted, and in the direction that costs most: the list named fifteen tools while the
server registered twenty-five, so every content-write tool, `create_file`, `copy_file`,
`list_slides`, `edit_comment` and `delete_comment` were invisible to anyone deciding whether
this project does what they need. A README that undersells is not a cosmetic problem - it is
the only thing most readers will ever look at.

Prose is checked by nobody, so it is checked here instead.
"""
from __future__ import annotations

import asyncio
import pathlib
import re

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

README = pathlib.Path(__file__).resolve().parent.parent / "README.md"


def registered_tools() -> set[str]:
    """Every tool a fully configured server exposes.

    Settings are supplied because three tools (`authenticate`, `describe_configuration`,
    `report_a_problem`) register only with them, and it is the configured server the README
    describes.
    """
    settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"})
    server = create_server(lambda: Workspace(FakeBackend()), settings=settings)
    return {tool.name for tool in asyncio.run(server.list_tools())}


def documented_tools() -> set[str]:
    """Tool names from the README's own tool table.

    Bounded to that table rather than the whole file: the comparison tables further down name
    tools alongside `—` rows for capabilities that have no tool, and prose elsewhere mentions
    tools in passing. Only the table that claims to be the list is the list.
    """
    text = README.read_text()
    start = text.index("**Tools** —")
    end = text.index("The find-and-read names", start)
    return set(re.findall(r"`([a-z_]+)`", text[start:end]))


def test_the_readme_lists_every_tool_the_server_registers():
    missing = registered_tools() - documented_tools()
    assert missing == set(), (
        f"registered but not in the README's tool table: {sorted(missing)}. A reader deciding "
        f"whether this project does what they need will never find them.")


def test_the_readme_does_not_promise_tools_that_do_not_exist():
    invented = documented_tools() - registered_tools()
    assert invented == set(), (
        f"the README's tool table names tools the server does not register: {sorted(invented)}")


def test_the_stated_count_matches():
    """The count is the first thing a skimmer reads, so it has to be true."""
    stated = re.search(r"\*\*Tools\*\* — (\d+),", README.read_text())
    assert stated, "the tool table no longer states a count"
    assert int(stated.group(1)) == len(registered_tools())
