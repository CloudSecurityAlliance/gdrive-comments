"""The profiles are Google Drive's roles, and the defaults are open.

**#195, v0.31.0.** Two changes that arrived together and are easier to read together.

**The ladder mirrors Drive.** `reader` · `commenter` · `writer` · `fileOrganizer` · `organizer`,
named as the Drive API names them — because an operator already holds Google's model of who may
do what to a file, and a more precise model sharing none of its words makes them hold two.

Drive also settled a question our own reasoning had got wrong: the audit proposed taking
`file.share` *off* the ladder, on the grounds that "more privileged" does not imply "may
disclose". **Google disagrees, in the most-used implementation of this problem** — its `writer`
explicitly cannot share, and sharing is reserved to Manager and Owner. So disclosure *is* a
ladder property, at the top.

**The defaults are open.** Everything on, both allowlists `*`. The argument is in
`policy.DEFAULT_ENABLED`; the part that makes it coherent rather than a retreat is that **a
capability enabled here is not a permission granted** — every call still runs as the authorizing
user against Drive's ACLs, so this model is a ceiling *below* Drive's and "everything on" means
*subtract nothing; let Drive decide*.

What must not be lost with it, and is asserted below: the ladder still orders on recoverability,
a malformed list is still refused, and `PolicyBackend` still fails closed on an unlisted method —
that last one is a code-safety invariant rather than a posture.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.policy import (
    ALL_CAPABILITIES,
    FILE_SHARE,
    IRREVERSIBLE,
    PROFILE_ALIASES,
    PROFILES,
    UI_LABELS,
    Policy,
    PolicyBackend,
    resolve_profile,
)

DOC = "doc1"
FILES = {DOC: {"id": DOC, "name": "A Doc", "mimeType": "application/vnd.google-apps.document"}}


class TestTheLadderIsDrives:
    def test_the_five_roles_are_drives_api_names(self):
        assert list(PROFILES) == ["reader", "commenter", "writer", "fileOrganizer", "organizer"]

    def test_each_rung_contains_the_one_below(self):
        names = list(PROFILES)
        for narrower, wider in zip(names, names[1:], strict=False):
            assert PROFILES[narrower] < PROFILES[wider], f"{narrower} ⊄ {wider}"

    def test_writer_cannot_share_which_is_the_point(self):
        """Drive's Writer explicitly cannot share; sharing belongs to Manager and Owner. The
        audit proposed making `file.share` orthogonal to the ladder — Google's answer is that it
        sits at the top of it, and Google's answer wins here."""
        assert FILE_SHARE not in PROFILES["writer"]
        assert FILE_SHARE not in PROFILES["fileOrganizer"]
        assert FILE_SHARE in PROFILES["organizer"]

    def test_fileorganizer_makes_the_previously_inexpressible_posture_expressible(self):
        """The audit's actual complaint: `full` bundled comment destruction with disclosure, so
        *"may destroy comment history, may never share"* had no name. It does now."""
        caps = PROFILES["fileOrganizer"]
        assert {"comment.edit", "comment.delete"} <= caps
        assert FILE_SHARE not in caps


class TestOurOldVocabularyStillWorks:
    @pytest.mark.parametrize("alias,target", sorted(PROFILE_ALIASES.items()))
    def test_an_alias_is_the_identical_set_not_an_approximation(self, alias, target):
        """An alias that quietly means something slightly different from what it aliases is
        worse than no alias: the configuration keeps working while doing something else."""
        assert PROFILES[resolve_profile(alias)] == PROFILES[target]

    @pytest.mark.parametrize("spelling", ["FILEORGANIZER", "  fileOrganizer ", "fileorganizer"])
    def test_case_and_whitespace_do_not_matter(self, spelling):
        """`fileOrganizer` is camelCase — Drive's spelling, not ours. An earlier draft
        lowercased the input and compared against the raw keys, so the *documented* name was
        rejected as unknown."""
        assert resolve_profile(spelling) == "fileOrganizer"


class TestAGoogleInterfaceLabelIsRefusedByNamingTheRightWord:
    """Config accepts one spelling. But somebody writing `manager` has not made a typo — they
    used Google's own interface label, and a bare "unknown profile" would send them to the
    documentation to learn that the thing they already know is called something else here."""

    @pytest.mark.parametrize("label,target", sorted(UI_LABELS.items()))
    def test_the_refusal_names_the_api_role(self, label, target):
        with pytest.raises(ValueError) as e:
            resolve_profile(label)
        assert target in str(e.value)
        assert "interface label" in str(e.value)

    def test_owner_is_redirected_with_the_ceiling_explained(self):
        """`owner` maps to `organizer`, and that is not a plain synonym: Drive's Owner can
        permanently delete and this library cannot, so the redirect says so rather than
        implying the two are equivalent."""
        with pytest.raises(ValueError) as e:
            resolve_profile("owner")
        assert "permanent delete" in str(e.value)

    def test_something_genuinely_unknown_lists_the_real_names(self):
        with pytest.raises(ValueError) as e:
            resolve_profile("superuser")
        for name in PROFILES:
            assert name in str(e.value)


class TestTheDefaultsAreOpen:
    def test_an_unconfigured_server_permits_every_capability_and_every_file(self):
        settings = settings_from_env({})
        assert settings.policy is not None
        assert settings.policy.enabled == frozenset(ALL_CAPABILITIES)
        assert settings.policy.read.all_files and settings.policy.modify.all_files

    def test_the_default_equals_organizer(self):
        assert Policy.default().enabled == PROFILES["organizer"]

    def test_share_works_out_of_the_box(self):
        """Argued about and included deliberately: not on the get-work-done path, so enabling it
        removes no real friction, while being the only capability whose effect leaves the
        organisation. Overruled on the grounds that Drive owns sharing policy — recorded here
        because a default that was argued about is worth being able to find."""
        doc = Workspace(PolicyBackend(FakeBackend(dict(FILES)), Policy.default())).open(DOC)
        doc.share("someone@example.com")

    def test_the_local_switches_default_on_and_are_not_capabilities(self):
        """They cannot contain confidential data — by the time either runs the content is in the
        model's context. Listing them beside `file.share` would invite an operator to believe
        switching them off prevents disclosure."""
        settings = settings_from_env({})
        assert settings.local_read and settings.local_write
        for name in ("local.read", "local.write", "local_read", "local_write"):
            assert name not in ALL_CAPABILITIES

    @pytest.mark.parametrize("value,expected", [
        ("0", False), ("false", False), ("off", False), ("disabled", False),
        ("1", True), ("yes", True), ("on", True), ("", True),
    ])
    def test_the_local_switches_read_a_closed_set_of_values(self, value, expected):
        env = {"CSA_GW_LOCAL_WRITE": value} if value else {}
        assert settings_from_env(env).local_write is expected

    def test_an_unrecognised_switch_value_is_an_error_not_a_guess(self):
        """The failure mode of guessing is that somebody who tried to turn a thing off believes
        they did."""
        with pytest.raises(ValueError, match="(?i)yes/no"):
            settings_from_env({"CSA_GW_LOCAL_WRITE": "disable"})


class TestWhatTheReversalMustNotHaveTakenWithIt:
    """Three properties that had nothing to do with the default and would be easy to lose while
    changing it."""

    def test_the_ladder_still_orders_on_recoverability(self):
        assert IRREVERSIBLE <= PROFILES["organizer"]
        assert not IRREVERSIBLE & PROFILES["writer"]

    def test_a_narrowed_profile_still_refuses(self):
        """The default being open does not mean the gate stopped working — it means nobody is
        standing in it until an operator says so."""
        narrowed = Workspace(PolicyBackend(FakeBackend(dict(FILES)),
                                           Policy(enabled=PROFILES["commenter"])))
        with pytest.raises(exc.ReadOnlyError):
            narrowed.open(DOC).share("someone@example.com")

    def test_policybackend_still_fails_closed_on_an_unlisted_method(self):
        """A CODE-SAFETY invariant, not a posture, and it must not be simplified away alongside
        the default. A `Backend` method with no `_GATES` entry is refused rather than delegated,
        so forgetting one turns the method off rather than leaving it ungoverned."""
        guarded = PolicyBackend(FakeBackend(dict(FILES)), Policy.default())
        with pytest.raises(exc.UnsupportedOperation, match="_GATES"):
            guarded.a_method_nobody_declared("f")
