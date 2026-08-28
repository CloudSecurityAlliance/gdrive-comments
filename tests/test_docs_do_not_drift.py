"""A number stated in prose must match the code, or it will not.

The audit found `INTERFACE-RESOURCES.md` reporting **v0.2.3, nine tools**, and *"content-write
tools are not exposed through MCP yet"* — false for roughly fifteen releases — while `CLAUDE.md`
said **32 tools** and `README.md` said **34**. Three files, three answers, one registry.

None of that was carelessness. Each number was correct when written; **prose that states a count
has a shelf life**, and nothing was measuring it. This session added another twelve releases on
top, so the gap widened while the issue sat open — which is the argument for a test rather than
a correction.

`tests/test_readme_tools.py` already checks the README's tool *table* against the registry. It
did not catch any of this, because a table of names and a sentence saying "34 tools" are
different claims and only one was guarded.

**What this asserts, and what it deliberately does not.** Only *mechanical* claims: a tool count,
a capability count, a version. Those have one right answer and it is computable. Comparative
claims about other products — how many tools Google's Drive server has, what the claude.ai
connector can do — cannot be tested from here, which is why the comparison table carries a
verification date instead. Two different problems; conflating them would produce a test that
either passes vacuously or fails on somebody else's release schedule.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from csa_google_workspace import Workspace, __version__
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import ALL_CAPABILITIES

ROOT = Path(__file__).resolve().parent.parent

# Files that describe the interface to a reader. Hand-listed: a doc joins this set when
# somebody decides it makes countable claims, not because of where it lives.
DOCS = ["README.md", "CLAUDE.md", "INTERFACE-RESOURCES.md"]

# "34 tools", "nine tools", "34-tool server"
COUNT = re.compile(r"\b(\d+|nine|ten|eleven|twelve)[\s-]tools?\b", re.I)
WORDS = {"nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


@pytest.fixture(scope="module")
def tool_count():
    settings = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                                  "CSA_GW_PROFILE": "full"})
    server = create_server(lambda: Workspace(FakeBackend({})), settings=settings)
    return len(asyncio.run(server.list_tools()))


# Lines describing SOMEBODY ELSE'S server. Their counts are comparative claims about a third
# party, which this test explicitly does not police - they cannot be computed from here, and
# they are covered instead by the verification date on the comparison table. Without this, the
# first version of this test flagged README's "8 tools" for Google's Drive server as our drift.
ABOUT_SOMEONE_ELSE = re.compile(
    r"google|claude\.ai|claude's|drivemcp|docsmcp|sheetsmcp|slidesmcp|connector|theirs", re.I)


def stated_counts(text: str) -> list[int]:
    """Counts this project makes about ITSELF, one line at a time."""
    out = []
    for line in text.splitlines():
        if ABOUT_SOMEONE_ELSE.search(line):
            continue
        for match in COUNT.finditer(line):
            token = match.group(1).lower()
            out.append(WORDS.get(token) or int(token))
    return out


class TestEveryStatedToolCountIsTheRealOne:
    @pytest.mark.parametrize("name", DOCS)
    def test_the_counts_in_this_file_are_current(self, name, tool_count):
        path = ROOT / name
        if not path.exists():
            pytest.skip(f"{name} is not in this tree")
        stated = stated_counts(path.read_text(encoding="utf-8"))
        wrong = [n for n in stated if n != tool_count]
        assert wrong == [], (
            f"{name} claims {wrong} tool(s); the registry has {tool_count}. Every one of these "
            f"was right when written - that is the point. Update it, or stop stating a number.")

    def test_at_least_one_doc_states_a_count(self, tool_count):
        """A guard that finds no claims anywhere is passing vacuously."""
        found = sum(len(stated_counts((ROOT / n).read_text(encoding="utf-8")))
                    for n in DOCS if (ROOT / n).exists())
        assert found > 0, "no document states a tool count; this test is asserting nothing"


class TestNoDocumentClaimsTheWrongVersionOfItself:
    """`INTERFACE-RESOURCES.md` described the server as of v0.2.3 while carrying a
    'Last verified' date — the date said it was current and the content was not."""

    def test_interface_resources_is_verified_against_this_version(self):
        path = ROOT / "INTERFACE-RESOURCES.md"
        if not path.exists():
            pytest.skip("INTERFACE-RESOURCES.md is not in this tree")
        text = path.read_text(encoding="utf-8")
        assert __version__ in text, (
            f"INTERFACE-RESOURCES.md does not mention the current version ({__version__}). It "
            f"carries a 'Last verified' line, so a stale body under a fresh-looking date is "
            f"worse than no date at all.")


class TestNoDocumentSaysContentWritesAreMissing:
    """A specific false claim worth its own assertion, because it survived fifteen releases and
    understates the server by an entire capability axis. It appeared in two files and was fixed
    in each separately, which is exactly the shape that comes back."""

    @pytest.mark.parametrize("name", DOCS)
    def test_it_does_not_say_content_writes_are_unexposed(self, name):
        path = ROOT / name
        if not path.exists():
            pytest.skip(f"{name} is not in this tree")
        # Emphasis stripped first: the claim survived in INTERFACE-RESOURCES.md as
        # "are **not** exposed through MCP yet", which a literal substring search misses. A
        # guard defeated by markdown is a guard defeated by ordinary editing.
        text = re.sub(r"[*_`]", "", path.read_text(encoding="utf-8")).lower()
        text = " ".join(text.split())
        assert "not exposed through mcp yet" not in text, (
            f"{name} still says content writes are not exposed; they shipped in v0.13.0")


class TestTheCapabilityCountIsRight:
    @pytest.mark.parametrize("name", DOCS)
    def test_no_doc_miscounts_the_capabilities(self, name):
        path = ROOT / name
        if not path.exists():
            pytest.skip(f"{name} is not in this tree")
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\b(\d+)\s+capabilit", text, re.I):
            assert int(match.group(1)) == len(ALL_CAPABILITIES), (
                f"{name} claims {match.group(1)} capabilities; there are "
                f"{len(ALL_CAPABILITIES)}")


class TestEveryConfigVariableIsDocumented:
    """`csa-gw://help/configuration` opens by calling itself the reference to *every* variable.

    It described five and the code read ten. The missing ones were not trivia: `CSA_GW_TOKEN`
    points at the credential, and `CSA_GW_EXPORT_DIR` decides where an authorized `.csv` write
    lands on the host. A reference that names some of the variables is worse than one that
    names none, because the omissions read as "there are no others".

    The variables are discovered by **scanning the source**, so adding one and documenting it
    nowhere fails here rather than in somebody's configuration.
    """

    IGNORED = {"CSA_GW_ALLOWLIST"}  # the legacy combined name, retained only to reject it

    def env_vars_the_code_reads(self) -> set[str]:
        found: set[str] = set()
        for path in (ROOT / "src").rglob("*.py"):
            found |= set(re.findall(r"\bCSA_GW_[A-Z_]+\b", path.read_text(encoding="utf-8")))
        return {v for v in found if v not in self.IGNORED and len(v) > len("CSA_GW_")}

    def test_the_reference_names_every_one_of_them(self):
        from csa_google_workspace.mcp._resources import render_help

        text = render_help()
        undocumented = sorted(v for v in self.env_vars_the_code_reads() if v not in text)
        assert undocumented == [], (
            f"{undocumented} are read by the code and absent from the configuration "
            f"reference, which calls itself the reference to every variable")

    def test_the_scan_finds_something(self):
        """A regex that silently stopped matching would make the test above pass on air."""
        assert len(self.env_vars_the_code_reads()) >= 8


class TestTheProfileTableMatchesThePolicy:
    """The reference's profile table was hand-written and had drifted in both directions: it
    gave `editor` the ability to "tidy comments" (`comment.edit`/`comment.delete` are `full`)
    and put rename/move and trash under `full` (both are `editor`).

    That mattered more than a stale README because a model reads this resource to explain a
    refusal — so the wrong copy is delivered to a user with the server's authority behind it,
    and an operator choosing a profile from it picks the wrong one.

    It is now rendered from `PROFILES`. These tests assert the rendering is faithful, since
    "generated" is only worth something if the generator is right.
    """

    def test_every_profile_appears(self):
        from csa_google_workspace.mcp._resources import render_help
        from csa_google_workspace.policy import PROFILES

        text = render_help()
        for name in PROFILES:
            assert f"| `{name}` |" in text, f"profile {name} is missing from the reference"

    def test_a_profile_never_claims_a_capability_it_lacks(self):
        """The specific defect: `editor` advertising comment editing."""
        from csa_google_workspace.mcp._resources import _profile_rows
        from csa_google_workspace.policy import CAPABILITY_NOTES, PROFILES

        rows = dict(zip(PROFILES, _profile_rows(), strict=True))
        for name, caps in PROFILES.items():
            for capability, (meaning, _undo) in CAPABILITY_NOTES.items():
                claimed = capability not in caps and meaning in rows[name]
                assert not claimed, (
                    f"the `{name}` row advertises {capability!r} ({meaning!r}), which that "
                    f"profile does not have")

    def test_each_capability_is_named_with_its_reversibility(self):
        from csa_google_workspace.mcp._resources import render_help
        from csa_google_workspace.policy import ALL_CAPABILITIES, CAPABILITY_NOTES

        text = render_help()
        for capability in ALL_CAPABILITIES:
            assert f"`{capability}`" in text, (
                f"{capability} is a value of CSA_GW_CAPABILITIES and is named nowhere a "
                f"reader could find it")
            assert CAPABILITY_NOTES[capability][1] in text

    def test_notes_cover_exactly_the_capabilities(self):
        from csa_google_workspace.policy import ALL_CAPABILITIES, CAPABILITY_NOTES

        assert set(CAPABILITY_NOTES) == set(ALL_CAPABILITIES), (
            "CAPABILITY_NOTES and ALL_CAPABILITIES disagree; the reference renders from the "
            "first and the server enforces the second")

    def test_the_irreversible_three_are_exactly_the_ones_off_by_default(self):
        """Ties the prose ('the line is drawn on: can this be undone?') to the data."""
        from csa_google_workspace.policy import CAPABILITY_NOTES, DEFAULT_DISABLED

        irreversible = {c for c, (_m, undo) in CAPABILITY_NOTES.items()
                        if undo.startswith("NO")}
        assert irreversible == set(DEFAULT_DISABLED), (
            f"capabilities described as irreversible {sorted(irreversible)} are not the set "
            f"disabled by default {sorted(DEFAULT_DISABLED)} - one of the two is lying")
