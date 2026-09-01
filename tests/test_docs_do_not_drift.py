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
# Matches "40 tools" / "40-tools" and nothing else. NOTE, measured 2026-08-31: after the
# competitor survey landed, this pattern finds NO self-counts in README.md at all - it phrases
# its own totals as "**Tools** - 40," and "| MCP tools | 8 | 11 | **40** |", neither of which is
# `<n> tools`. So this test's README coverage is currently VACUOUS, not merely redundant.
#
# That is tolerable only because README's count is genuinely guarded elsewhere:
# `test_readme_tools.py::test_the_stated_count_matches` and
# `test_the_stated_tool_counts_are_arithmetic_that_holds` both fail on a wrong total (verified by
# changing it). If those ever go, widen this pattern rather than trusting the green tick here.
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
#
# The second group is the COMMUNITY servers surveyed in README's "wider field" table. Added
# 2026-08-31 when that table landed: `piotr-agier ships 115 tools` was read as this project
# claiming 115, because the line names a competitor rather than Google. Their counts are no more
# computable from here than Google's are, and the survey's own verification date covers them.
ABOUT_SOMEONE_ELSE = re.compile(
    r"google|claude\.ai|claude's|drivemcp|docsmcp|sheetsmcp|slidesmcp|connector|theirs"
    r"|piotr-agier|taylorwilsdon|a-bonus|aaronsb|isaacphi|felores|dbuxton|phact"
    r"|stanislawherjan|us-all|composio|klavis|pipedream|zapier", re.I)


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


    def test_it_names_every_tool_the_server_actually_exposes(self):
        """The version assertion above was satisfiable by the HEADER alone.

        That is how "Current release **v0.2.3**" survived in the body for roughly thirty-five
        releases while the "Last verified" line kept being refreshed: bumping the header made
        the test pass, and nothing looked at what the file claimed. Fifteen tools from
        v0.33.0-v0.36.0 were missing from the inventory when this was written.

        A count would not have caught it either - the count said 50 and was right. Only naming
        them is checkable, so that is what is checked.
        """
        import asyncio

        from csa_google_workspace import Workspace
        from csa_google_workspace.backend import FakeBackend
        from csa_google_workspace.mcp import settings_from_env
        from csa_google_workspace.mcp.server import create_server

        path = ROOT / "INTERFACE-RESOURCES.md"
        if not path.exists():
            pytest.skip("INTERFACE-RESOURCES.md is not in this tree")
        text = path.read_text(encoding="utf-8")
        app = create_server(lambda: Workspace(FakeBackend({})),
                            settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))
        tools = sorted(tool.name for tool in asyncio.run(app.list_tools()))
        missing = [name for name in tools if f"`{name}`" not in text]
        assert missing == [], (
            f"INTERFACE-RESOURCES.md is the interface inventory and does not name "
            f"{len(missing)} tool(s) the server exposes: {missing}. Add them to the Surface "
            f"list - an inventory that silently omits a capability understates the server to "
            f"whoever is reviewing what it can do.")

    def test_it_does_not_state_a_stale_current_release(self):
        """The specific rot: a hard-coded release number in prose. Any `Current release
        **vX.Y.Z**` must be THIS version, so the claim cannot drift while the header is
        refreshed."""
        import re
        path = ROOT / "INTERFACE-RESOURCES.md"
        if not path.exists():
            pytest.skip("INTERFACE-RESOURCES.md is not in this tree")
        text = path.read_text(encoding="utf-8")
        # Skip the parenthetical that RECORDS the old value as history.
        claimed = re.findall(r"Current release \*\*v([0-9]+\.[0-9]+\.[0-9]+)\*\*", text)
        assert claimed, "expected a 'Current release **vX.Y.Z**' claim to check"
        assert set(claimed) == {__version__}, (
            f"INTERFACE-RESOURCES.md claims current release {claimed}, but this is "
            f"{__version__}")


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

    def test_the_irreversible_three_are_named_and_sit_at_the_top_of_the_ladder(self):
        """**RESTATED in v0.31.0**, and the restatement is deliberate rather than a test being
        fixed to pass.

        This used to assert that the capabilities *described* as irreversible were exactly
        `DEFAULT_DISABLED` — tying the prose "the line is drawn on: can this be undone?" to the
        data. That assertion encoded the one-ladder model, where recoverability decided what was
        ON. Nothing is off by default now, so the old form would compare against an empty set
        and pass vacuously, which is worse than failing.

        What still has to hold is the half that survived: recoverability no longer decides the
        default, but it still orders the ladder, and the three that cannot be undone are still
        the ones an operator is choosing when they pick the top rung.
        """
        from csa_google_workspace.policy import CAPABILITY_NOTES, IRREVERSIBLE, PROFILES

        described = {c for c, (_m, undo) in CAPABILITY_NOTES.items() if undo.startswith("NO")}
        assert described == set(IRREVERSIBLE), (
            f"capabilities described as irreversible {sorted(described)} are not `IRREVERSIBLE` "
            f"{sorted(IRREVERSIBLE)} - one of the two is lying")
        assert set(IRREVERSIBLE) <= PROFILES["organizer"]
        assert not set(IRREVERSIBLE) & PROFILES["writer"], (
            "an irreversible capability reachable from `writer` would make the ladder's whole "
            "ordering meaningless")


# This repository deliberately RECORDS what a document used to get wrong, next to the correction
# — it is how the reasoning survives, and this file is full of the practice. That collides with
# any guard that greps for the wrong sentence, because a quotation of it looks identical to an
# assertion of it.
#
# The convention that resolves it: a historical aside is wrapped in `*( ... )*`. Guards strip
# those spans before asserting, so "here is what this used to say" stays free to write while
# "here is what is true" stays checked. `scripts/check_doc_claims.py` states the same rule in
# prose — if a claim is deliberately historical, say so in the text.
_HISTORICAL_ASIDE = re.compile(r"\*\(.*?\)\*", re.DOTALL)


def without_historical_notes(text: str) -> str:
    """`text` with `*( ... )*` asides removed, so a quoted mistake is not read as a live claim."""
    return _HISTORICAL_ASIDE.sub(" ", text)


class TestSecurityMdDescribesTheACTUALDefaults:
    """The three claims `SECURITY.md` had backwards until 2026-08-31, all in the same direction.

    v0.31.0 reversed the defaults — everything on, both allowlists `*` — and the security document
    went on saying the opposite for several releases:

    * *"The default refuses rename/move, trash and share"* — all three are enabled.
    * *"Both fail closed in the MCP server: unset means nothing is permitted"* — unset means every
      file. What fails closed is a **malformed** list, which is a different statement.
    * a section headed *"Read-only by default"* — `CSA_GW_READ_ONLY` is off unless set.

    **Every one understated the reach**, which is the dangerous direction: a reader who believes
    the default is narrow does not narrow it. This is the same failure the `describe` resource had
    at the same time, so it is not a coincidence of one file — it is what happens when a default
    changes and the prose describing it lives somewhere else.

    Pinned against the constants rather than against a form of words, so a rewrite is free and a
    reversal is not.
    """

    def _security(self) -> str:
        path = ROOT / "SECURITY.md"
        if not path.exists():
            pytest.skip("SECURITY.md is not in this tree")
        return without_historical_notes(path.read_text(encoding="utf-8"))

    def test_it_does_not_claim_the_default_refuses_what_the_default_allows(self):
        from csa_google_workspace.policy import DEFAULT_ENABLED

        text = self._security()
        for capability, phrase in (("file.update", "rename/move"),
                                   ("file.trash", "trash"),
                                   ("file.share", "share")):
            if capability in DEFAULT_ENABLED:
                assert f"default\n  refuses {phrase}" not in text, (
                    f"{capability} is enabled by default and SECURITY.md says it is refused")
        assert "The default\n  refuses rename/move, trash and share" not in text

    def test_it_states_the_capability_default_correctly(self):
        """Asserted positively as well, because deleting the false sentence and saying nothing
        would also pass the test above while leaving a reader with no answer."""
        from csa_google_workspace.policy import DEFAULT_DISABLED

        text = self._security().lower()
        if not DEFAULT_DISABLED:
            assert "enabled by default" in text, (
                "everything is on by default and SECURITY.md does not say so anywhere")

    def test_it_does_not_claim_an_unset_allowlist_permits_nothing(self):
        """`unset` and `malformed` are different, and only one of them fails closed. Conflating
        them is how the sentence came to claim a bound that is not there."""
        from csa_google_workspace.mcp._config import settings_from_env

        unset = settings_from_env({})
        if unset.policy.modify.all_files:
            text = self._security()
            assert "unset means nothing is\n  permitted" not in text
            assert "unset means nothing is permitted" not in text

    def test_no_heading_claims_read_only_is_the_default(self):
        from csa_google_workspace.mcp._config import settings_from_env

        if settings_from_env({}).read_only:
            pytest.skip("read-only really is the default now; the heading would be correct")
        text = self._security()
        assert "## Read-only by default" not in text, (
            "read_only is OFF unless set; a heading saying otherwise is the most inviting "
            "sentence in the file to get backwards")


class TestTheReadmeDoesNotContradictTheProfileLadder:
    """README footnote 7 said the file-lifecycle tools were *"off in every profile but `full`"*
    and that *"the default `editor` profile cannot rename, share or trash anything"*.

    Three things wrong by v0.31.0, and the document disagreed with itself: `writer` **may** rename
    and trash (both reversible), nothing is off by default, and there is no default profile at all.
    The profile table a few hundred lines above it said the right thing the whole time.

    Pinned against `PROFILES` rather than against wording, so the prose can be rewritten freely and
    only a false claim fails.
    """

    def _readme(self) -> str:
        return without_historical_notes((ROOT / "README.md").read_text(encoding="utf-8"))

    def test_it_does_not_claim_writer_cannot_rename_or_trash(self):
        from csa_google_workspace.policy import PROFILES

        writer = PROFILES["writer"]
        text = self._readme()
        if "file.update" in writer and "file.trash" in writer:
            assert "cannot rename, share or trash anything" not in text, (
                "`writer` holds file.update and file.trash; the README says it holds neither")

    def test_it_does_not_call_any_profile_the_default(self):
        """Nothing is a default profile — an unset `CSA_GW_PROFILE` means every capability, not a
        named rung. Calling one "the default" invites an operator to assume a bound exists."""
        text = self._readme()
        for profile in ("editor", "writer", "commenter", "reader", "organizer", "full"):
            assert f"default `{profile}` profile" not in text, (
                f"README calls `{profile}` the default profile; there is no default profile")

    def test_capabilities_the_readme_calls_organizer_only_really_are(self):
        """The claim worth keeping true, since it is the one an operator leans on: `file.share`
        is the capability that moves data out of the organisation, and it must not become
        reachable from a lower rung without this sentence changing."""
        from csa_google_workspace.policy import PROFILES

        if "`file.share` is not, in effect" in self._readme():
            reachable = {p for p, caps in PROFILES.items() if "file.share" in caps}
            assert reachable == {"organizer"}, (
                f"README says file.share is organizer-only; it is reachable from {reachable}")


class TestTheConfigurationContractIsToldOneWay:
    """RR-003, an external correctness review's only P0 (2026-09-01).

    v0.31.0 reversed the defaults. Eleven releases later the repository still told the *old* story
    in four surfaces nobody had re-read — and the worst of them was not prose in a file:

    * `README.md` line 31, in the **opening bullets**: *"Every destructive capability is off until
      an operator names it, and the file allowlists fail closed."*
    * `README.md`: *"963 offline tests"* (1631) and *"34 tools"* (50).
    * `README.md`: *"Unset means nothing is permitted"* and *"It fails closed."*
    * **`cli.py`'s `--help`**: profile names `editor | full`, *"Default: editor"*, *"Both FAIL
      CLOSED"*.
    * **`configure`'s printed output**: *"BOTH allowlists fail closed, so nothing is reachable
      until you set CSA_GW_ALLOWLIST_READ"* — told to an operator **at the moment they set the
      server up**. A wrong sentence in a file nobody opens is a defect; a wrong sentence printed
      during setup is somebody believing they are scoped when they are not.
    * `_config.py`'s docstring, which is the version an AI remediation agent preserves while
      changing the code around it.

    Two lessons this class exists to hold:

    1. **`--help` and `configure` output are documentation that lives in `.py` files.** The earlier
       sweep treated drift as a docs task and never opened them.
    2. **Suppressing a false positive by excluding a whole file excludes its true positives too.**
       `check_doc_claims.py` had `OWN_TOOL_COUNT_FILES = {"CLAUDE.md", "INTERFACE-RESOURCES.md"}`
       to quiet the README's competitor comparisons — and that exclusion is exactly what hid
       *"34 tools"* in the README's own introduction. Exclude the sentence, never the document.
    """

    def test_no_surface_claims_an_unset_allowlist_permits_nothing(self):
        """The single sentence that outlived its truth in five files."""
        from csa_google_workspace.mcp._config import settings_from_env

        if not settings_from_env({}).policy.modify.all_files:
            pytest.skip("unset really does permit nothing now")

        for path in ("README.md", "SECURITY.md", "TODO.md"):
            text = without_historical_notes((ROOT / path).read_text(encoding="utf-8")).lower()
            for phrase in ("unset means nothing is permitted",
                           "both allowlists fail closed",
                           "both fail closed"):
                assert phrase not in text, f"{path} still says {phrase!r}; unset permits everything"

    def test_the_cli_help_does_not_promise_a_closed_default(self):
        """`--help` is the first thing an operator reads and it lives in code, which is why the
        docs sweep missed it."""
        from csa_google_workspace.mcp._config import settings_from_env

        if not settings_from_env({}).policy.modify.all_files:
            pytest.skip("unset really does permit nothing now")
        help_text = without_historical_notes(_usage_text()).lower()
        assert "fail closed: unset means nothing is permitted" not in help_text
        assert "safe default" not in help_text, (
            "there is no safe default: every capability is on unless narrowed")

    def test_the_cli_help_uses_the_real_profile_vocabulary(self):
        """It advertised `editor | full` as the profile names and `editor` as *the default*.
        Both are wrong: the names mirror Drive's roles, and there is no default profile."""
        from csa_google_workspace.policy import PROFILES

        help_text = _usage_text()
        for profile in sorted(PROFILES):
            assert profile in help_text, f"--help does not mention the `{profile}` profile"
        assert "Default: editor" not in help_text, "there is no default profile"

    def test_configure_does_not_tell_an_operator_they_are_scoped_when_they_are_not(self):
        """The sharpest of the RR-003 sites: printed during setup, not buried in a file."""
        import inspect

        from csa_google_workspace.mcp import cli
        source = inspect.getsource(cli)
        # The comment recording the bug legitimately quotes the old text; the printed string
        # must not.
        printed = "\n".join(line for line in source.splitlines()
                            if not line.lstrip().startswith("#"))
        assert "nothing is reachable" not in printed, (
            "configure told the operator nothing is reachable until they set an allowlist, at "
            "the moment they were setting the server up")


def _usage_text() -> str:
    """The `--help` text. Read from the `USAGE` constant rather than by capturing stdout: the
    first version of this helper redirected stdout, got an empty string, and reported that
    `--help` was missing a profile name it in fact lists. A capture that can silently return
    nothing makes every assertion built on it vacuous."""
    from csa_google_workspace.mcp import cli
    return cli.USAGE
