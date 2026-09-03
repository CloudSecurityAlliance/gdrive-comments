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
from csa_google_workspace.policy import (
    ALL_CAPABILITIES,
    DEFAULT_DISABLED,
    IRREVERSIBLE,
)

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


# Spelled-out numbers, because that is how the stale claims were actually written. The original
# guard matched `\d+` only, so `all ten capabilities` in CLAUDE.md - wrong from the day
# `content.delete` made eleven - was invisible to the one test built to catch exactly that
# (#320). A detector that cannot see the form the defect takes is not a detector.
# `one` is deliberately absent. "one capability off an otherwise-right profile" and "how much of
# one capability lives in a single method" are determiners, not claims about the total - three of
# the six matches in this repository, and a detector nobody trusts is a detector nobody runs. A
# total of exactly one is not a state this policy model can reach.
_NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_COUNT_CLAIM = re.compile(
    r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r")\s+(?:\w+\s+)?capabilit", re.I)


# NOT every count of capabilities is a count of ALL of them. "Four capabilities are irreversible"
# is correct and always will be, and a detector that read it as a claim about the total would
# report a true sentence as drift - which is how a checker gets switched off. So the number is
# compared against the set the SENTENCE names, taken from the words that follow it.
_SUBSETS = (("irreversible", lambda: len(IRREVERSIBLE)),
            ("off by default", lambda: len(DEFAULT_DISABLED)),
            ("disabled by default", lambda: len(DEFAULT_DISABLED)))


def _claimed_counts(text: str) -> list[tuple[str, int, int]]:
    """Every "<N> capabilities" claim, as (what was written, the number, what it should be)."""
    found = []
    for match in _COUNT_CLAIM.finditer(text):
        written = match.group(1)
        number = int(written) if written.isdigit() else _NUMBER_WORDS[written.lower()]
        # The clause the count belongs to, normalised - a claim can wrap across a line.
        context = " ".join(text[match.start():match.end() + 90].split()).lower()
        expected = len(ALL_CAPABILITIES)
        for word, size in _SUBSETS:
            if word in context:
                expected = size(); break
        found.append((match.group(0).strip(), number, expected))
    return found


class TestTheCapabilityCountIsRight:
    @pytest.mark.parametrize("name", DOCS)
    def test_no_doc_miscounts_the_capabilities(self, name):
        path = ROOT / name
        if not path.exists():
            pytest.skip(f"{name} is not in this tree")
        text = without_historical_notes(path.read_text(encoding="utf-8"))
        for written, number, expected in _claimed_counts(text):
            assert number == expected, (
                f"{name} says {written!r} -> {number}, but the set that sentence names has "
                f"{expected}. Prefer removing the number - a count in prose that a constant "
                f"controls will drift again - unless the sentence genuinely needs it.")

    def test_the_detector_fires_on_a_planted_claim(self):
        """**This is how a guard with no input proves it is alive.**

        The property "no doc miscounts" is satisfied trivially when no doc states a count, and
        that is the preferred state - a number in prose that a constant controls is drift
        waiting to happen. So the fix for the vacuity is NOT to require a count somewhere; it
        is to test the DETECTOR against synthetic input, which holds whether or not any real
        document says anything.
        """
        wrong = len(ALL_CAPABILITIES) + 1
        for planted in (f"all {wrong} capabilities are on",
                        "all ten capabilities are on",      # the form that actually shipped
                        f"the {wrong} capability names"):
            found = _claimed_counts(planted)
            assert found, f"the detector missed {planted!r} entirely"
            assert any(n != e for _, n, e in found), (
                f"the detector read {planted!r} but did not see the number as wrong")

    def test_the_detector_does_not_fire_on_a_correct_claim(self):
        """The counterweight: a detector that flags everything gets switched off."""
        for fine in (f"all {len(ALL_CAPABILITIES)} capabilities are on",
                     # A SUBSET count, which is the false positive that would have retired this
                     # guard - README's "Four capabilities are irreversible" is simply true.
                     f"{len(IRREVERSIBLE)} capabilities are irreversible and flagged as such",
                     # And a determiner, which is why `one` is not a number word here.
                     "one capability off an otherwise-right profile"):
            assert all(n == e for _, n, e in _claimed_counts(fine)), (
                f"the detector wrongly flagged {fine!r}")


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


class TestNoLiveDocumentAssertsTheOldClosedPosture:
    """**#321.** The narrow version matched three literal phrases across three files -
    `"unset means nothing is permitted"`, `"both allowlists fail closed"`, `"both fail closed"` -
    and every surviving drift site used DIFFERENT wording, in a file not on the list. A guard
    keyed to three spellings of a claim is a guard against those three spellings.

    So this delegates to `check_doc_claims.py`'s detector rather than growing a second one. That
    one already does the three things a literal search cannot:

    * **normalises whitespace first**, because a claim straddling a line break is invisible to
      line-based matching - `TODO.md` has *"capabilities that were\n off by default"*, where the
      negation that makes it correct sits on the previous line;
    * **requires a subject nearby**, so the three sentences about *caching* - which genuinely is
      off by default - are not reported;
    * **skips negations and past tense**, because *"nothing is off by default"* and *"these were
      off by default"* are the true statements, and a detector with a 92% false-positive rate is
      one nobody runs.

    Moving it here makes it a REQUIRED check. The script is advisory by design - failing a PR
    because a paragraph has not caught up trains people to write a hollow sentence to get green -
    but this particular claim is the one that already shipped wrong for eleven releases, on the
    surface a model reads as authority, so it earns a gate.

    Frozen records are out of scope by construction rather than by exclusion: `DOCS` and
    `DOC_GLOBS` never contained `docs/security-audits/` or `docs/correctness-reports/`, whose
    whole job is to QUOTE the defect. That distinction matters - an exclusion list would have had
    to be maintained, and would have hidden true positives the way excluding the README once hid
    "34 tools" (RR-003).
    """

    def _detector(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cdc", ROOT / "scripts" / "check_doc_claims.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_no_live_document_or_docstring_claims_a_closed_default(self):
        from csa_google_workspace.policy import DEFAULT_DISABLED
        cdc = self._detector()
        sources = sorted((ROOT / cdc.SOURCE_ROOT).rglob("*.py"))
        problems = cdc._posture_problems(
            cdc._docs() + sources,
            anything_disabled=bool(DEFAULT_DISABLED),
            # Hardcoded rather than read from the environment: this asserts a property of the
            # PROSE against the shipped default, and a test that consulted CSA_GW_* would
            # change its mind based on the shell it ran in.
            unset_is_everything=True)
        assert problems == [], (
            "these assert a closed default that the constants contradict:\n  "
            + "\n  ".join(problems)
            + "\n\nIf a sentence is deliberately historical, wrap it in *( ... )* so it reads "
              "as a quotation rather than a claim.")

    def test_the_detector_fires_on_a_planted_claim(self):
        """A guard whose input can legitimately be empty is proved alive by running it against
        synthetic input, not by demanding the input be non-empty. Same technique as the
        capability-count detector; the lesson is #320's."""
        cdc = self._detector()
        planted = "The `file.share` capability is off by default and must be named explicitly."
        assert cdc._posture_problems(
            [_Planted(planted)], anything_disabled=False, unset_is_everything=True), (
            "the detector did not flag a plain 'off by default' claim about a capability")

    def test_the_detector_does_not_fire_on_history_or_on_caching(self):
        """The counterweight, and the reason the narrow version was replaced rather than
        widened: 12 of 13 bare-phrase matches in this repository were correct."""
        cdc = self._detector()
        for fine in ("Nothing is off by default since v0.31.0.",
                     "These descriptions said `file.share` was off by default for eleven releases.",
                     "Caching is off by default and there is no caching layer at all."):
            assert cdc._posture_problems(
                [_Planted(fine)], anything_disabled=False, unset_is_everything=True) == [], (
                f"wrongly flagged: {fine!r}")


class _Planted:
    """A path-like carrying text, so the detector can be exercised without writing a file."""

    def __init__(self, text: str):
        self._text = text
        self.name = "planted.md"

    def read_text(self, encoding: str = "utf-8") -> str:
        return self._text


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


class TestTheModuleInventoryWalksTheWholeTree:
    """The inventory check inspects subpackages, not just the top level (#329).

    **The glob was `*.py`** — top level only — so `mcp/` and `documents/` were never walked, and
    `mcp/_flavours.py`, `mcp/_logging.py` and `mcp/_capabilities.py` went undocumented while the
    check reported no problems. A guard that only inspects the directory where things were
    originally written stops working the first time the tree grows a subpackage, and reports
    success while doing it.

    Asserted here rather than left to `check_doc_claims.py` alone because that script is
    **advisory** — it opens one weekly issue rather than failing a PR. The property that it
    *looks in the right places* is cheap to pin and is what silently regressed.
    """

    def check_problems(self) -> list[str]:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_cdc", ROOT / "scripts/check_doc_claims.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.check()

    def test_it_is_clean_right_now(self):
        """Vacuity guard: if this is dirty, the tests below prove nothing about the mechanism."""
        assert self.check_problems() == []

    def test_every_subpackage_is_described(self):
        """The direction that broke. A whole directory nobody is told about is worse than a
        module nobody is told about, and it was the invisible case."""
        pkg = ROOT / "src/csa_google_workspace"
        subs = [d.relative_to(pkg).as_posix() for d in pkg.iterdir()
                if d.is_dir() and (d / "__init__.py").exists()]
        assert subs, "no subpackages found - this test would pass vacuously"
        guide = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        for sub in subs:
            assert f"`{sub}/`" in guide or f"`{sub}`" in guide, (
                f"the `{sub}/` subpackage is not mentioned in CLAUDE.md's layout section")

    # The three `mcp/` modules the 2026-09-01 audit found missing (F24, #329). A hand-written
    # list of three, and that IS the derive-don't-list rule being applied rather than broken:
    # the general check deliberately accepts a directory-level mention for a subpackage module,
    # because demanding a line for each of twenty `mcp/` internals would make it cry wolf. So
    # these are pinned individually for the reason CLAUDE.md gives for its other narrow guards
    # — they are the claims that have ALREADY gone wrong. Each carries a decision an agent
    # needs: the surface ceiling, the tool-vs-Backend capability split, and the
    # operation-never-content logging rule.
    AUDIT_FOUND_MISSING = ("mcp/_flavours.py", "mcp/_capabilities.py", "mcp/_logging.py")

    @pytest.mark.parametrize("module", AUDIT_FOUND_MISSING)
    def test_the_modules_the_audit_found_missing_are_named(self, module):
        guide = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        assert f"`{module}`" in guide, (
            f"{module} is not named in CLAUDE.md. The audit found it missing once (F24); the "
            f"general inventory check accepts a directory-level mention for subpackage modules, "
            f"so nothing else would catch it going missing again.")

    def test_those_modules_still_exist_where_the_guard_expects(self):
        """Otherwise the guard above would pass by describing modules that had been moved or
        deleted — a documented ghost, which is worse than an undocumented module."""
        for module in self.AUDIT_FOUND_MISSING:
            assert (ROOT / "src/csa_google_workspace" / module).exists(), (
                f"{module} no longer exists; CLAUDE.md describes it and this guard requires it")

    def test_a_new_top_level_module_would_be_reported(self, tmp_path, monkeypatch):
        """Proves the check FAILS when it should, which "it is clean right now" cannot."""
        pkg = ROOT / "src/csa_google_workspace"
        planted = pkg / "_zzz_drift_probe.py"
        planted.write_text('"""Temporary, planted by a test."""\n', encoding="utf-8")
        try:
            problems = self.check_problems()
        finally:
            planted.unlink()
        assert any("_zzz_drift_probe.py" in p for p in problems), (
            "a new undocumented top-level module was not reported")

    def test_a_new_SUBPACKAGE_would_be_reported(self):
        """The #329 case itself: the one the old glob could not see."""
        pkg = ROOT / "src/csa_google_workspace"
        planted = pkg / "_zzz_drift_pkg"
        planted.mkdir()
        (planted / "__init__.py").write_text('"""Temporary."""\n', encoding="utf-8")
        try:
            problems = self.check_problems()
        finally:
            (planted / "__init__.py").unlink()
            planted.rmdir()
        assert any("_zzz_drift_pkg" in p for p in problems), (
            "a new undocumented subpackage was not reported - this is exactly what the "
            "top-level-only glob missed")


class TestAProposedSpecIsNotAClaim:
    """A design document describes intent; the posture guard reads it as an assertion.

    The guard exists because thirteen released claims of a closed default survived eleven
    releases after the default reversed — text telling an operator they were protected when
    they were not. A spec proposing that three capabilities be OFF by default is not that: it
    is a proposal, and it has to be writable before it is true.

    **The exemption is narrow on purpose**, and these tests pin both halves of it: only
    `docs/superpowers/specs/`, and only while the document declares its own status. **A spec
    whose design ships must drop the marker, and the guard then starts reading it** — which is
    exactly the moment its sentences become claims about the product.
    """

    def check(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_cdc2", ROOT / "scripts/check_doc_claims.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def planted(self, tmp_path, relative: str, text: str):
        p = tmp_path / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    CLAIM = "Three capabilities are OFF by default, which is the whole design."

    def test_a_proposed_spec_is_exempt(self, tmp_path):
        cdc = self.check()
        path = self.planted(tmp_path, "docs/superpowers/specs/x.md",
                            "# X\n\n**Status: proposed, 2026-09-03.**\n\n" + self.CLAIM)
        assert cdc._posture_problems([path], anything_disabled=False,
                                     unset_is_everything=True) == []

    def test_the_SAME_spec_without_the_marker_is_NOT_exempt(self, tmp_path):
        """The half that makes the exemption safe: drop the status line and it is read as a
        claim again. Otherwise the directory would have quietly stopped being checked."""
        cdc = self.check()
        path = self.planted(tmp_path, "docs/superpowers/specs/x.md", "# X\n\n" + self.CLAIM)
        assert cdc._posture_problems([path], anything_disabled=False,
                                     unset_is_everything=True) != []

    def test_the_exemption_does_not_apply_outside_the_specs_directory(self, tmp_path):
        """A status marker in a README would otherwise silence the guard on shipped text."""
        cdc = self.check()
        path = self.planted(tmp_path, "README.md",
                            "**Status: proposed.**\n\n" + self.CLAIM)
        assert cdc._posture_problems([path], anything_disabled=False,
                                     unset_is_everything=True) != []

    def test_the_marker_must_be_near_the_TOP(self, tmp_path):
        """Only the first few hundred characters are read, so a status line buried at the end
        of a long shipped document cannot retroactively exempt it."""
        cdc = self.check()
        path = self.planted(tmp_path, "docs/superpowers/specs/x.md",
                            "# X\n\n" + self.CLAIM + "\n\n" + ("filler. " * 200)
                            + "\n\nStatus: proposed")
        assert cdc._posture_problems([path], anything_disabled=False,
                                     unset_is_everything=True) != []

    def test_the_real_spec_declares_its_status(self):
        """The document this exemption was added for. If somebody implements it and drops the
        marker, this test tells them the guard is now reading their file — which is correct."""
        spec = ROOT / ("docs/superpowers/specs/"
                       "2026-09-03-full-api-coverage-and-admin-capabilities.md")
        assert spec.exists()
        assert "Status: proposed" in spec.read_text(encoding="utf-8")[:400]
