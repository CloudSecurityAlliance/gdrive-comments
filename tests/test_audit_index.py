"""The audit index is generated, and its coverage claim is checked against the tree.

**#198.** `docs/security-audits/README.md` was the one file every audit had to edit — its index
row and the coverage-by-module table — in a workflow built so that parallel audit agents never
share a file. It was the last shared mutable document, and so the only thing two concurrent
audits could collide over.

Both tables now come from per-audit front matter. The half that matters is coverage: each audit
**enumerates** the files it saw, and the table is computed against the tracked tree, so a group
nothing covers reads *not yet audited* by itself. A hand-maintained coverage claim is how the
July-to-August gap stayed invisible — the tree went from 16 modules to 53 and the table still
said "first covered by".

**Three bugs, all found by looking at output rather than reading code**, all the same kind: a
table that was confidently wrong while looking plausible.

1. `fnmatch`'s `*` crosses `/`, so `src/csa_google_workspace/*.py` matched every module in
   every subpackage. The top-level group reported 53 files instead of 20 and rendered
   "partial — 16/53" for a group that is fully covered.
2. "First covered by" broke on the first audit covering *any* file in a group, so an earlier
   partial hid a later full pass — `src/` top level read "partial — 12/20 at 2026-07-22" while
   the 2026-08-27 audit covers all twenty.
3. **A glob claims the future.** The 2026-08-27 record declared
   `.github/workflows/*.yml`; its target commit is `95c6afa`, and the directory gained
   `controls.yml` the next day. The table read *fully covered* for a directory whose newest
   file no audit had seen — the precise overstatement this issue exists to prevent, reproduced
   by the fix for it. Coverage is enumerated now, and a test rejects a glob in that field.

A generated table that is wrong is worse than the hand-written one it replaced, because nobody
re-reads a generated file. Hence tests on the matcher and on the verdict logic, not just on
the wiring.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/gen_audit_index.py"
INDEX = ROOT / "docs/security-audits/README.md"


@pytest.fixture(scope="module")
def gen():
    """Registered in `sys.modules` before executing: the script uses `from __future__ import
    annotations` with a `@dataclass`, and `dataclasses` resolves the string annotations via
    `sys.modules[cls.__module__]`. A path-loaded module absent from `sys.modules` makes that
    lookup return `None` and every test error inside the standard library."""
    spec = importlib.util.spec_from_file_location("gen_audit_index", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[spec.name]
        raise
    return module


class TestGlobsDoNotCrossDirectories:
    """Bug 1. `fnmatch` alone is wrong here in the direction that looks right."""

    def test_a_star_does_not_match_a_separator(self, gen):
        assert not gen.matches("src/csa_google_workspace/mcp/server.py",
                               "src/csa_google_workspace/*.py"), (
            "a top-level glob matched a file two directories down; this is the fnmatch trap")

    def test_a_direct_child_matches(self, gen):
        assert gen.matches("src/csa_google_workspace/policy.py",
                           "src/csa_google_workspace/*.py")

    def test_a_deeper_pattern_matches_at_its_own_depth(self, gen):
        assert gen.matches("tests/integration/test_live.py", "tests/*/*.py")
        assert not gen.matches("tests/test_policy.py", "tests/*/*.py")

    def test_an_exact_path_matches_only_itself(self, gen):
        assert gen.matches("pyproject.toml", "pyproject.toml")
        assert not gen.matches("docs/pyproject.toml", "pyproject.toml")

    def test_depth_mismatch_never_matches(self, gen):
        assert not gen.matches("a/b/c.py", "a/*.py")
        assert not gen.matches("a/b.py", "a/*/*.py")


class TestTheVerdictReportsTheEarliestFullPass:
    """Bug 2. An earlier partial audit must not hide a later complete one."""

    class FakeAudit:
        def __init__(self, date, patterns, tool="t"):
            self.date, self.patterns = date, patterns
            self.meta = {"tool": tool}

        def covers(self, file):
            return file in self.patterns

    def render(self, gen, audits, files):
        return gen.render_coverage(audits, files)

    def test_a_later_full_pass_wins_over_an_earlier_partial(self, gen, monkeypatch):
        monkeypatch.setattr(gen, "GROUPS", [("g", ["x/*.py"])])
        early = self.FakeAudit("2026-01-01", {"x/a.py"})
        late = self.FakeAudit("2026-06-01", {"x/a.py", "x/b.py"})
        out = self.render(gen, [late, early], ["x/a.py", "x/b.py"])
        assert "2026-06-01" in out and "partial" not in out

    def test_partial_is_reported_as_partial_with_the_count(self, gen, monkeypatch):
        monkeypatch.setattr(gen, "GROUPS", [("g", ["x/*.py"])])
        audit = self.FakeAudit("2026-01-01", {"x/a.py"})
        out = self.render(gen, [audit], ["x/a.py", "x/b.py"])
        assert "partial" in out and "1/2" in out

    def test_an_uncovered_group_says_so(self, gen, monkeypatch):
        """The property the whole exercise is for: a module nobody audited surfaces by itself,
        not when somebody thinks to look."""
        monkeypatch.setattr(gen, "GROUPS", [("g", ["x/*.py"])])
        audit = self.FakeAudit("2026-01-01", set())
        out = self.render(gen, [audit], ["x/a.py"])
        assert "not yet audited" in out

    def test_a_group_with_no_files_is_omitted_rather_than_shown_uncovered(self, gen,
                                                                         monkeypatch):
        """A directory that does not exist is not an audit gap, and listing it as one would
        train the reader to skip the rows that matter."""
        monkeypatch.setattr(gen, "GROUPS", [("gone", ["nowhere/*.py"])])
        assert "gone" not in self.render(gen, [self.FakeAudit("2026-01-01", set())], ["x/a.py"])


class TestNoTrackedCodeIsInvisibleToTheCoverageTable:
    """The dangerous direction of a hand-maintained group list: an unlisted directory does not
    appear as uncovered, it does not appear at all - which reads as "nothing to report"."""

    def test_every_tracked_python_file_falls_into_a_group(self, gen):
        files = gen.tracked_files()
        grouped = {f for _name, patterns in gen.GROUPS for f in files
                   if any(gen.matches(f, p) for p in patterns)}
        ungrouped = sorted(f for f in files if f.endswith(".py") and f not in grouped)
        assert ungrouped == [], (
            f"{ungrouped} are tracked Python files in no coverage group, so the table cannot "
            f"say whether they have been audited. Add a group in gen_audit_index.py.")


class TestCoverageIsMeasuredInLinesNotJustFiles:
    """#322. The table counted FILES, and a file does not stop being listed as covered when it
    triples in size — roughly 3,400 of 4,061 new `src/` lines sat inside files marked fully
    covered.

    Counting lines TODAY would not fix it: that counts growth the audit never read as covered.
    The honest number is the size a file was **when the audit saw it**, which git still has,
    against the size it is now. The effect is visible immediately — `mcp/_tools/` reads as fully
    covered by file and **63% by line**.
    """

    def test_an_unresolvable_commit_yields_no_number_rather_than_a_wrong_one(self, gen):
        """The normal case in CI: `actions/checkout` is shallow, so an audit's `target_commit`
        is usually absent. Degrading to the older, weaker file-only claim is right; inventing a
        percentage from today's line counts would be worse than the bug being fixed."""
        assert gen.lines_at("0000000000000000000000000000000000000000",
                            ["src/csa_google_workspace/policy.py"]) == {}
        assert gen.lines_at("", ["src/csa_google_workspace/policy.py"]) == {}

    def test_no_paths_is_not_an_error(self, gen):
        assert gen.lines_at("HEAD", []) == {}

    def test_it_counts_the_file_as_it_was_then_not_now(self, gen):
        """The whole point, asserted against real history: `policy.py` has grown since the
        2026-08-27 audit read it, and the coverage number must reflect what was read."""
        then = gen.lines_at("95c6afa", ["src/csa_google_workspace/policy.py"])
        now = gen.lines_now(["src/csa_google_workspace/policy.py"])
        assert then, "the 2026-08-27 audit commit should be resolvable in a full clone"
        assert then["src/csa_google_workspace/policy.py"] < now["src/csa_google_workspace/policy.py"], (
            "policy.py has grown since that audit; if this ever fails the fixture changed, not "
            "the mechanism")

    def test_the_generated_table_carries_a_line_share(self, gen):
        """End to end: at least one group reports one, or the feature is not wired in."""
        table = gen.render_coverage(gen.load_audits(), gen.tracked_files())
        assert "% of lines" in table

    def test_a_group_can_be_fully_covered_by_file_and_partly_by_line(self, gen):
        """The exact overstatement #322 describes, present in this repository today."""
        table = gen.render_coverage(gen.load_audits(), gen.tracked_files())
        rows = [r for r in table.splitlines()
                if "% of lines" in r and "partial" not in r]
        assert rows, "no group is fully-covered-by-file with a line share to compare against"
        shares = [int(r.split("· ")[-1].split("%")[0]) for r in rows]
        assert any(s < 100 for s in shares), (
            "every fully-covered group also reads 100% of lines, which would mean the "
            "file-based count was never overstating anything - check the mechanism")


class TestEveryRecordCarriesWhatTheIndexNeeds:
    REQUIRED = ["audit_id", "date_completed", "tool", "human_interaction", "automation",
                "review_depth", "modules_covered"]

    def test_three_records_are_discovered(self, gen):
        """Two 2026-07-22 records plus the 2026-08-27 one. A discovery glob that quietly stopped
        matching would render an index missing an audit, which is the worst kind of wrong here."""
        assert len(gen.load_audits()) >= 3

    def test_each_record_has_the_required_front_matter(self, gen):
        for audit in gen.load_audits():
            missing = [k for k in self.REQUIRED if audit.meta.get(k) in (None, "")]
            assert missing == [], f"{audit.path.name} is missing {missing}"

    def test_no_two_records_share_an_audit_id(self, gen):
        """#331. Two audits ran against `d33034b` on 2026-09-01 and BOTH front matters claimed
        `2026-09-01-01`.

        Not an edge case: the corpus is designed so parallel audits never share a file, which
        makes same-day audits expected rather than exceptional - and `audit_id` is what a
        `REMEDIATION.md`, an issue trail and the threat-model baseline all point at. Two records
        disagreeing about which is `-01` is the one ambiguity this design does not otherwise
        have, and nothing detected it; the collision was found by reading.

        `SCHEMA.md` now states the tie-break (earliest `date_completed` takes the lower suffix)
        and this asserts it was applied.
        """
        seen: dict[str, str] = {}
        clashes = []
        for audit in gen.load_audits():
            key = str(audit.meta.get("audit_id"))
            if key in seen:
                clashes.append(f"{key}: {seen[key]} and {audit.path.parent.name}")
            seen[key] = audit.path.parent.name
        assert clashes == [], (
            f"duplicate audit_id(s): {clashes}. SCHEMA.md's tie-break rule assigns the lower "
            f"suffix by earliest date_completed - renumber the later record and say why in its "
            f"README, leaving its frozen findings as written.")

    def test_modules_covered_is_a_list_of_strings(self, gen):
        for audit in gen.load_audits():
            covered = audit.meta["modules_covered"]
            assert isinstance(covered, list) and all(isinstance(c, str) for c in covered), (
                f"{audit.path.name}: modules_covered must be a list of glob strings")

    def test_every_record_enumerates_rather_than_globs(self, gen):
        """A glob claims the future, and that is not hypothetical.

        The 2026-08-27 record was first written with `.github/workflows/*.yml`, and its target
        commit is 95c6afa. That glob claimed `controls.yml` - written the following day, which
        the audit never saw - and the coverage table read "fully covered" for a directory whose
        newest file was unaudited. Caught by checking the generated output against
        `git ls-tree`, not by reading the front matter.

        Enumeration cannot overstate: a file absent from the list is uncovered, so a group
        correctly flips to `partial - 3/4` the moment something is added. The lists come from
        the audited tree itself (`git ls-tree -r <target_commit>`), which is both easy and the
        only source that cannot be optimistic.

        Globs stay valid for `GROUPS` in the generator, where they describe the repository's
        layout rather than anyone's coverage claim.
        """
        for audit in gen.load_audits():
            globbed = [c for c in audit.meta["modules_covered"] if "*" in c or "?" in c]
            assert globbed == [], (
                f"{audit.path.name} claims coverage by glob {globbed}. A glob matches files "
                f"added after the audit ran. Enumerate from "
                f"`git ls-tree -r {audit.meta.get('target_commit', '<commit>')}`.")


class TestTheCommittedIndexIsCurrent:
    """What CI runs. Offline: it reads the tree and `git ls-files`, no network."""

    def test_the_markers_are_present(self):
        text = INDEX.read_text(encoding="utf-8")
        for marker in ("BEGIN GENERATED INDEX", "END GENERATED INDEX",
                       "BEGIN GENERATED COVERAGE", "END GENERATED COVERAGE"):
            assert marker in text, f"{marker} is missing; the generator cannot splice"

    def test_check_mode_passes_on_the_committed_file(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--check"],
                                capture_output=True, text=True, cwd=ROOT)
        assert result.returncode == 0, (
            f"the committed index is stale. Run `python scripts/gen_audit_index.py`.\n"
            f"{result.stdout}{result.stderr}")

    def test_check_mode_does_not_write(self):
        """CI must never rewrite the file it is checking - the committed copy has to stay the
        reviewed one."""
        before = INDEX.read_bytes()
        subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, cwd=ROOT)
        assert INDEX.read_bytes() == before


class TestTheIndexNoLongerClaimsToBeASharedFile:
    """The document used to name itself as the workflow's one contention point. Leaving that
    text in place would tell the next audit to edit a generated table."""

    def test_it_does_not_tell_a_reader_to_update_the_table_by_hand(self):
        text = INDEX.read_text(encoding="utf-8")
        assert "When adding a record, update this table." not in text
        assert "generated" in text.lower()

    def test_the_schema_says_the_index_is_generated(self):
        schema = (ROOT / "docs/security-audits/SCHEMA.md").read_text(encoding="utf-8")
        assert "gen_audit_index" in schema, (
            "SCHEMA.md still instructs an audit to update the index; it is generated now")
