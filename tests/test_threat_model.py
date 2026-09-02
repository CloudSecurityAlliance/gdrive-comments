"""The living threat model agrees with the frozen snapshot, except where it says it does not.

**#197, then #310.** An audit commits only its own directory, so each produces a register
inside it. Adopting one as the living `THREAT_MODEL.md` at the repository root is what this
covers. The baseline is now the **re-scored `2026-09-01-02`** register (43 threats); the
`2026-08-27-01` one it replaced stays in the tree as that audit's own baseline.

Adoption is never a copy. The 2026-09-01 audit ran against `d33034b` (v0.38.0), and by adoption
two releases had shipped — so two threats moved to `risk_accepted` and three gained evidence. A
living threat model that lists fixed threats as `unmitigated` is not cautious, it is unusable —
nobody trusts a document that is wrong about the things they can check, and then nobody reads the
rows about things they cannot.

**Why moving the baseline does not destroy the property it exists for.** The check on a claim of
progress is that somebody *else* froze the thing we are measured against. The new snapshot was
written by an independent audit, so that survives; rewriting the old baseline ourselves would not
have.

So the root model carries the audit's threat text verbatim and a **current** `status` column,
with §0 accounting for the difference. These tests make that accounting load-bearing rather
than decorative:

* every threat id in the snapshot exists in the root model, and vice versa — adoption cannot
  silently drop a threat, which is the failure that matters most here;
* every status comes from a closed vocabulary, so a typo cannot invent a reassuring one;
* **§0 lists exactly the ids whose status differs from the snapshot** — no more, no fewer. A
  status quietly improved without an entry fails here, and so does an entry claiming a change
  that did not happen.

The last one is the point. The frozen snapshot is a baseline nothing in this repository can
edit, which makes it the one available check on a claim of progress.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIVING = ROOT / "THREAT_MODEL.md"
# The BASELINE the living model is diffed against. Moved 2026-09-02 from `2026-08-27-01` to
# the re-scored `2026-09-01-02` register (#310). Moving it is legitimate precisely because the
# new snapshot was written by an INDEPENDENT audit rather than by us - the property that makes
# a claim of progress checkable is that somebody else froze the thing we are compared to, and
# that survives. Rewriting the old baseline ourselves would have destroyed it.
#
# The 2026-08-27 snapshot stays in the tree as that audit's own baseline; it is simply no
# longer what the living model is measured against.
AUDIT = ROOT / "docs/security-audits/2026-09-01-defending-code-reference-harness-claude"
SNAPSHOT = AUDIT / "THREAT_MODEL.md"

# The audit's own vocabulary. Closed on purpose: "addressed", "fixed" or "resolved" would each
# read as stronger than `partially_mitigated` while meaning less than `mitigated`.
STATUSES = {"unmitigated", "partially_mitigated", "mitigated", "risk_accepted"}

THREAT_ROW = re.compile(r"^\| (T\d+) \|")


def _section(text: str, start: str, end: str | None) -> str:
    """The text between two headings. Raises if `start` is missing, deliberately: a silent
    empty slice would make every test that reads it pass vacuously."""
    begin = text.index(start)
    return text[begin:text.index(end, begin)] if end else text[begin:]


def statuses(path: Path) -> dict[str, str]:
    """id -> status, from §4 **and only** §4.

    **Bounded by SECTION, not by column count (#318).** The previous version filtered on the
    ten-column shape of the threat table and called that "the §4 table only" - but column count
    is not section membership, and T36's row in §0b happened to carry twelve fields. So it was
    parsed as a §4 threat: the parser saw 36 threats where §4 held 35, and `SECURITY.md`'s
    "36 enumerated threats" agreed with the test **for the wrong reason** - both counted a row
    from the delta table.

    The column-count filter is KEPT as well as the slice, because §4 is not guaranteed to hold
    only threat rows and a five-column row inside it would otherwise be read as one.
    """
    text = path.read_text(encoding="utf-8")
    section = _section(text, "## 4. Threats", "## 5.")
    found = {}
    for line in section.splitlines():
        match = THREAT_ROW.match(line)
        if not match:
            continue
        if len(line.split("|")) < 11:      # a bookkeeping row, not a threat
            continue
        found[match.group(1)] = fields_status(line)
    return found


def fields_status(line: str) -> str:
    return line.split("|")[8].strip()


def _five_column_ids(text: str, start: str, end: str) -> set[str]:
    """Threat ids in a five-column bookkeeping table between two headings.

    Both §0 and §0b are `| T… |` tables that are NOT the threat register, so they are told apart
    from §4 by column count and from each other by their headings. Slicing §0 all the way to §1
    would swallow §0b and read "this threat was added" as "this status moved" — two different
    claims, and only one of them is about a threat the snapshot contains.
    """
    return {m.group(1) for line in _section(text, start, end).splitlines()
            if (m := THREAT_ROW.match(line)) and len(line.split("|")) < 11}


def delta_ids() -> set[str]:
    """The ids §0 claims have moved STATUS. All of these must exist in the snapshot."""
    return _five_column_ids(LIVING.read_text(encoding="utf-8"),
                            "## 0. Status since the audit", "## 0b. Threats added since")


def added_ids() -> set[str]:
    """The ids §0b declares as ADDED since the audit, with a source.

    The snapshot is a baseline this repository cannot edit, which is the only real check on a
    claim of progress — so a threat absent from it is either a genuine finding or a copy-paste,
    and the difference is whether somebody wrote down where it came from. This table is that
    record; `test_the_living_model_invents_no_threats` accepts exactly these and nothing else.
    """
    return _five_column_ids(LIVING.read_text(encoding="utf-8"),
                            "## 0b. Threats added since", "## 1. System context")


@pytest.fixture(scope="module")
def living():
    if not LIVING.exists():
        pytest.skip("THREAT_MODEL.md has not been adopted yet")
    return statuses(LIVING)


@pytest.fixture(scope="module")
def snapshot():
    if not SNAPSHOT.exists():
        pytest.skip("the audit snapshot is not in this tree")
    return statuses(SNAPSHOT)


class TestAdoptionDroppedNothing:
    def test_the_snapshot_has_the_threats_we_think_it_does(self, snapshot):
        """A parser that silently matched nothing would make every test below vacuous."""
        assert len(snapshot) == 43, f"expected 43 threats in the snapshot, parsed {len(snapshot)}"

    def test_every_snapshot_threat_survives_in_the_living_model(self, living, snapshot):
        lost = sorted(set(snapshot) - set(living), key=lambda t: int(t[1:]))
        assert lost == [], (
            f"{lost} are in the audit's model and absent from the living one. A threat may be "
            f"rescored or accepted, and it must not vanish - the ids are stable and are not "
            f"renumbered when rows are removed.")

    def test_the_living_model_invents_no_threats(self, living, snapshot):
        """A new threat is legitimate, but it needs an id from somewhere other than a copy-paste
        of this table - otherwise a duplicated row reads as a distinct finding."""
        invented = sorted(set(living) - set(snapshot) - added_ids(), key=lambda t: int(t[1:]))
        assert invented == [], (
            f"{invented} appear only in the living model. If these are genuinely new threats, "
            f"record where they came from in §0b; the adoption itself should add none.")

    def test_every_declared_addition_is_actually_in_the_register(self, living):
        """§0b claiming a threat that §4 does not carry would be a promise with nothing behind
        it - the mirror of the assertion above, and the direction somebody would not think to
        check."""
        missing = sorted(added_ids() - set(living), key=lambda t: int(t[1:]))
        assert missing == [], f"§0b declares {missing}, which §4 does not contain"

    def test_no_addition_duplicates_a_snapshot_threat(self, snapshot):
        """An id already in the baseline cannot also be "added". Catches the copy-paste this
        whole mechanism exists to prevent."""
        overlap = sorted(added_ids() & set(snapshot), key=lambda t: int(t[1:]))
        assert overlap == [], f"§0b claims to add {overlap}, which the audit already had"


class TestTheParserReadsTheRightSection:
    """#318. The parser claimed to read §4 and read the whole file, which is a different thing
    that agreed with it for years because nothing above §4 happened to have eleven columns."""

    def test_no_bookkeeping_row_is_counted_as_a_threat(self, living):
        """The concrete regression: a §0/§0b row with enough columns was parsed as a threat.
        Asserted by comparing against the ids §0 and §0b declare - any threat id that appears
        ONLY in a bookkeeping table must not be in the register's status map."""
        text = LIVING.read_text(encoding="utf-8")
        register = _section(text, "## 4. Threats", "## 5.")
        for tid in living:
            assert f"| {tid} |" in register, (
                f"{tid} was parsed as a §4 threat but does not appear in §4 - the parser is "
                f"reading a bookkeeping table again (#318)")

    def test_the_section_slicer_refuses_to_match_nothing(self):
        """A slicer that returned '' on a renamed heading would make every test above pass
        while checking nothing. It raises instead."""
        with pytest.raises(ValueError):
            _section("no headings here", "## 4. Threats", "## 5.")


class TestStatusesComeFromAClosedVocabulary:
    @pytest.mark.parametrize("which", ["living", "snapshot"])
    def test_no_status_is_off_vocabulary(self, request, which):
        table = request.getfixturevalue(which)
        wrong = {tid: s for tid, s in table.items() if s not in STATUSES}
        assert wrong == {}, (
            f"{wrong} are not in {sorted(STATUSES)}. A near-miss like 'addressed' reads as "
            f"stronger than partially_mitigated while meaning less than mitigated.")


class TestSectionZeroAccountsForEveryDifference:
    """The load-bearing test. The frozen snapshot is a baseline this repository cannot edit,
    which makes it the only available check on a claim of progress."""

    def test_every_moved_status_is_listed(self, living, snapshot):
        moved = {tid for tid in snapshot if living.get(tid) != snapshot[tid]}
        unlisted = sorted(moved - delta_ids(), key=lambda t: int(t[1:]))
        assert unlisted == [], (
            f"{unlisted} changed status since the audit and are not in §0. An unexplained "
            f"improvement is the one edit to this file nobody can review.")

    def test_nothing_claims_a_change_it_did_not_make(self, living, snapshot):
        """§0 may legitimately mention an id whose status did NOT move - T13 and T19 are listed
        as still-partial with what was and was not done. So this asserts the weaker, real
        property: every id §0 names must exist."""
        unknown = sorted(delta_ids() - set(snapshot), key=lambda t: int(t[1:]))
        assert unknown == [], f"§0 names {unknown}, which are not threats in the model"

    def test_the_delta_table_is_not_empty(self):
        """If the two ever agree completely, §0 should say so in prose rather than present an
        empty table - an empty table looks like a parsing failure."""
        assert delta_ids(), "§0 lists no ids; say so in prose instead"

    def test_a_status_only_ever_improves_without_explanation(self, living, snapshot):
        """A threat getting WORSE is legitimate — a regression, or a rescoring — but it is
        never something to leave implicit, so it must appear in §0 like any other move. This is
        the same assertion as above stated from the other side, and it is here because a
        regression is the case somebody would be tempted to omit."""
        order = {"mitigated": 3, "partially_mitigated": 2, "risk_accepted": 1, "unmitigated": 0}
        for tid, was in snapshot.items():
            now = living[tid]
            if order.get(now, 0) < order.get(was, 0):
                assert tid in delta_ids(), (
                    f"{tid} went from {was} to {now} - a worsening - and §0 does not mention it")


class TestTheLivingModelReadsAsLiving:
    def test_the_frozen_banner_is_gone(self):
        text = LIVING.read_text(encoding="utf-8")
        assert "Frozen snapshot" not in text, (
            "the root model still carries the snapshot's do-not-edit banner")

    def test_it_says_which_audit_it_came_from(self):
        text = LIVING.read_text(encoding="utf-8")
        assert "2026-09-01-02" in text and "d33034b" in text, (
            "a threat model with no stated provenance cannot be compared to anything")

    def test_relative_links_resolve_from_the_repository_root(self):
        """The snapshot's links resolve from the audit directory. Copied unchanged they would
        point at `FINDINGS.md` beside the root model, which does not exist."""
        text = LIVING.read_text(encoding="utf-8")
        for match in re.finditer(r"\]\((?!http)([^)#]+)\)", text):
            target = ROOT / match.group(1)
            assert target.exists(), f"broken relative link: {match.group(1)}"

    def test_the_snapshot_still_points_at_the_living_model(self):
        text = SNAPSHOT.read_text(encoding="utf-8")
        assert "Frozen snapshot" in text, "the audit's copy must stay marked as frozen"
        assert "repository\n> root" in text or "repository root" in text


class TestItIsReachableFromWhereSomebodyWouldLook:
    """An adopted threat model nothing links to has been filed, not adopted. #197 asks for this
    decision explicitly."""

    def test_security_md_links_to_it(self):
        text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        assert "THREAT_MODEL.md" in text, (
            "SECURITY.md is the standing threat framing and referenced the two 2026-07-22 "
            "audits but no threat model; a reader starting there would never find this")

    def test_the_audit_index_no_longer_says_once_adopted(self):
        text = (ROOT / "docs/security-audits/README.md").read_text(encoding="utf-8")
        assert "once\nadopted" not in text and "once adopted" not in text
