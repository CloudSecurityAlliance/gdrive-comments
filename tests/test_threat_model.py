"""The living threat model agrees with the frozen snapshot, except where it says it does not.

**#197.** Audit `2026-08-27-01` produced a 35-threat model inside its own directory, because an
audit commits only its own directory. Adopting it as the living `THREAT_MODEL.md` at the
repository root is what this covers.

Adoption was not a copy. The audit ran against `95c6afa` (v0.28.0); by adoption the tree was
v0.30.10 and **thirteen threats had moved status**. A living threat model that lists fixed
threats as `unmitigated` is not cautious, it is unusable — nobody trusts a document that is
wrong about the things they can check, and then nobody reads the rows about things they cannot.

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
AUDIT = ROOT / "docs/security-audits/2026-08-27-defending-code-reference-harness-claude"
SNAPSHOT = AUDIT / "THREAT_MODEL.md"

# The audit's own vocabulary. Closed on purpose: "addressed", "fixed" or "resolved" would each
# read as stronger than `partially_mitigated` while meaning less than `mitigated`.
STATUSES = {"unmitigated", "partially_mitigated", "mitigated", "risk_accepted"}

THREAT_ROW = re.compile(r"^\| (T\d+) \|")


def statuses(path: Path) -> dict[str, str]:
    """id -> status, from the §4 threat table only.

    §0's delta table also has rows starting `| T…`, so it is skipped by requiring the ten-column
    shape of the threat table. Counting §0's rows as threats would make every test here compare
    the document against itself.
    """
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = THREAT_ROW.match(line)
        if not match:
            continue
        fields = line.split("|")
        if len(fields) < 11:          # §0's five-column delta table
            continue
        found[match.group(1)] = fields[8].strip()
    return found


def delta_ids() -> set[str]:
    """The ids §0 claims have moved."""
    text = LIVING.read_text(encoding="utf-8")
    section = text[text.index("## 0. Status since the audit"):text.index("## 1. System context")]
    return {m.group(1) for line in section.splitlines()
            if (m := THREAT_ROW.match(line)) and len(line.split("|")) < 11}


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
        assert len(snapshot) == 35, f"expected 35 threats in the snapshot, parsed {len(snapshot)}"

    def test_every_snapshot_threat_survives_in_the_living_model(self, living, snapshot):
        lost = sorted(set(snapshot) - set(living), key=lambda t: int(t[1:]))
        assert lost == [], (
            f"{lost} are in the audit's model and absent from the living one. A threat may be "
            f"rescored or accepted, and it must not vanish - the ids are stable and are not "
            f"renumbered when rows are removed.")

    def test_the_living_model_invents_no_threats(self, living, snapshot):
        """A new threat is legitimate, but it needs an id from somewhere other than a copy-paste
        of this table - otherwise a duplicated row reads as a distinct finding."""
        invented = sorted(set(living) - set(snapshot), key=lambda t: int(t[1:]))
        assert invented == [], (
            f"{invented} appear only in the living model. If these are genuinely new threats, "
            f"record where they came from; the adoption itself should add none.")


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
        assert "2026-08-27-01" in text and "95c6afa" in text, (
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
