"""A tool description names the capability it needs. It does not say whether that capability is on.

**#332**, filed by audit `2026-09-01-02` after #305 fixed the strings without fixing the guard.

The class had already recurred once when it was filed. The 2026-08-27 audit recommended asserting
that capability claims in the server `INSTRUCTIONS` exist in `ALL_CAPABILITIES`; that was built.
The claims then reappeared in tool **descriptions**, which that guard does not read, and survived
eleven releases after the defaults reversed — until two independent audits found them on the same
day.

Then it recurred a second time within hours: the fix for those descriptions replaced *"OFF by
default"* with *"**on by default**"*, which was true when written and is the same hand-maintained
sentence in the same place. **The defect is not the value; it is that current state was written
where it has to be maintained by hand.**

So the rule is the stronger one #332 asked for: a description names the capability it requires and
**stops**. `describe_configuration` computes current state from the live policy and cannot drift, so
that is where a model is sent.

## The distinction this file has to draw

Nine default-state phrases existed across the fifty descriptions when this was written, and they
were two unrelated things:

* **Parameter defaults** — *"`role` defaults to READER"*, *"`sendNotification` defaults to true"*,
  *"Defaults to Drive's own 'Copy of …' name"*. These describe the **function signature**. They
  cannot drift, they are useful, and one of them (`role` defaulting to reader rather than to what
  the requester asked for) is load-bearing security behaviour. **Keep.**
* **Policy state** — *"on by default"*, *"off unless an operator"*. These describe **configuration**,
  which changes underneath the sentence. **Forbid.**

The split is lexical and matches the semantics: policy claims say a capability *is on or off*;
parameter defaults say a value *defaults to* something.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

# Claims about whether a capability is currently permitted. Hand-maintained, and therefore drifting.
POLICY_STATE_CLAIMS = (
    "on by default",
    "off by default",
    "off unless",
    "enabled by default",
    "disabled by default",
    "DEFAULT_ENABLED",
    "DEFAULT_DISABLED",
)

# Deliberately NOT forbidden: `defaults to …` and `by default you get …` describe a PARAMETER, not
# the policy. Asserted below so a future tightening cannot quietly swallow them.
PARAMETER_DEFAULT_MARKERS = ("defaults to", "by default you get")


def descriptions() -> dict[str, str]:
    """Every registered tool's description, from the live registry.

    Read from the server rather than by grepping `_tools/`, because the point of the finding is
    that a guard enumerating by hand falls behind while one deriving from the registry does not —
    a tool added in a new module is covered here automatically.
    """
    app = create_server(lambda: Workspace(FakeBackend({})),
                        settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))
    return {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}


class TestNoDescriptionStatesPolicy:
    def test_no_tool_claims_a_capability_is_on_or_off(self):
        offenders = []
        for name, described in sorted(descriptions().items()):
            flat = " ".join(described.split())
            for claim in POLICY_STATE_CLAIMS:
                if claim.lower() in flat.lower():
                    offenders.append(f"{name}: {claim!r}")
        assert offenders == [], (
            "tool descriptions state current policy, which is maintained by hand and has drifted "
            f"twice: {offenders}. Name the capability and let `describe_configuration` answer "
            f"whether it is on.")

    def test_the_guard_covers_every_registered_tool(self):
        """The 2026-08-27 guard read only `INSTRUCTIONS`, so the claims moved to descriptions and
        were not seen. This one enumerates the registry, so a new module is covered without
        anybody remembering to widen it."""
        found = descriptions()
        assert len(found) > 40, f"only {len(found)} descriptions enumerated; the registry is not being read"


class TestParameterDefaultsSurvive:
    """The over-correction would be as bad: these are the function's contract, and one of them is
    a security decision."""

    def test_parameter_defaults_are_still_documented_somewhere(self):
        joined = " ".join(descriptions().values()).lower()
        assert any(marker in joined for marker in PARAMETER_DEFAULT_MARKERS), (
            "no parameter default is documented anywhere - a tightening has gone too far")

    def test_resolve_access_proposal_still_says_it_grants_reader(self):
        """Load-bearing: `accept` defaults to `reader` rather than the role the requester asked
        for, so the one field an attacker fully controls cannot select their own access level. A
        model needs to know that, and it is a parameter default, not policy."""
        described = descriptions()["resolve_access_proposal"].lower()
        assert "reader" in described
        assert "defaults to" in described

    def test_share_file_still_says_notification_defaults_on(self):
        described = descriptions()["share_file"].lower()
        assert "sendnotification" in described and "defaults to true" in described


class TestDescriptionsStillSayWhatIsRequired:
    """Removing the state claim must not remove the capability name - that is what lets a model
    explain a refusal instead of retrying it."""

    @pytest.mark.parametrize("name,capability", [
        ("update_file", "file.update"),
        ("trash_file", "file.trash"),
        ("share_file", "file.share"),
        ("clear_cells", "content.write"),
        ("delete_tab", "content.delete"),
    ])
    def test_the_capability_is_named(self, name, capability):
        assert capability in descriptions()[name], f"{name} does not name {capability}"

    def test_the_three_lifecycle_tools_point_at_describe_configuration(self):
        """Where current state actually lives. Without this the descriptions would be silent on
        the question rather than answering it a better way."""
        found = descriptions()
        for name in ("update_file", "trash_file"):
            assert "describe_configuration" in found[name], (
                f"{name} removed the state claim without pointing anywhere")


class TestTheServerInstructionsAreCoveredToo:
    """Where the 2026-08-27 guard was aimed. Kept in scope so the claims cannot move BACK."""

    def test_the_instructions_state_no_policy(self):
        from csa_google_workspace.mcp.server import INSTRUCTIONS

        flat = " ".join(INSTRUCTIONS.split())
        for claim in POLICY_STATE_CLAIMS:
            assert claim.lower() not in flat.lower(), f"INSTRUCTIONS states policy: {claim!r}"
