"""A refusal says WHOSE limit it is — Google's, the operator's, or a bug.

**The governing principle (CINO, 2026-09-03).** *Capability is never the constraint; policy
is.* "The MCP server cannot do that" must never be a technical answer. The answer should be
shaped like *"that is risky, so it is gated off and disabled by default — and if you want it on,
it can be on."* Whether to let an AI do something is a business and risk decision, and a missing
implementation quietly makes that decision on somebody's behalf.

So there are exactly two legitimate refusals, and they must be distinguishable **from the
message**, because the message is the only place the distinction lives:

* **UPSTREAM** — Google will not, or not yet. Must cite the measurement and say what would
  unlock it. This is the shape that stops a false "impossible" outliving the fact.
* **NOT ENABLED** — the operator switched it off. Must name the setting, so the answer is
  *"we gated that"* rather than *"that is unsupported"*.

Plus a third that is not a refusal at all: an internal **bug**, which says so.

## Why a test and not a convention

This exact drift already happened. `accept_suggestion` raised *"The Google Docs API has no
accept/reject-suggestion endpoint (verified by probe). A PlaywrightBackend is required."* That
was true of the published surface when written. `acceptSuggestion` was then measured to exist in
Developer Preview on 2026-09-02 — and the message went on telling callers a Playwright backend
was **required** for a capability that had become a matter of enrolment. A model reading it would
report the wrong thing to a user, and nothing failed.
"""
from __future__ import annotations

import inspect
import re

import pytest

from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import ApiBackend, FakeBackend

# The vocabulary. Deliberately shouty and deliberately closed: a reader scanning a message has
# to see the classification without parsing a sentence.
UPSTREAM = "UPSTREAM:"
NOT_ENABLED = ("is disabled", "capability", "CSA_GW_")     # policy refusals name their setting
FAKE = "FAKE BACKEND:"
BUG = "This is a bug"

# Evidence an UPSTREAM claim has to carry. Without a date, "Google cannot do this" is an
# assertion with no expiry, and Google's surface moves - twice this quarter.
MEASURED = re.compile(r"MEASURED \d{4}-\d{2}-\d{2}")


def _raises_unsupported(cls) -> dict[str, str]:
    """`{method name: source}` for every method whose body raises `UnsupportedOperation`."""
    out = {}
    for name, fn in inspect.getmembers(cls, predicate=inspect.isfunction):
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):        # pragma: no cover
            continue
        if "UnsupportedOperation(" in src:
            out[name] = src
    return out


class TestEveryRefusalIsClassified:
    @pytest.mark.parametrize("cls", [ApiBackend, FakeBackend])
    def test_there_are_refusals_to_check(self, cls):
        """Vacuity guard. If a refactor moved these, every assertion below would pass while
        checking nothing — which is the failure mode this repository keeps finding."""
        assert _raises_unsupported(cls), f"no UnsupportedOperation found in {cls.__name__}"

    @pytest.mark.parametrize("cls", [ApiBackend, FakeBackend])
    def test_each_refusal_names_its_kind(self, cls):
        unclassified = []
        for name, src in _raises_unsupported(cls).items():
            if not (UPSTREAM in src or FAKE in src or BUG in src
                    or any(token in src for token in NOT_ENABLED)):
                unclassified.append(f"{cls.__name__}.{name}")
        assert unclassified == [], (
            f"{unclassified} refuse without saying WHOSE limit it is. A caller cannot tell "
            f"'Google will not' from 'the operator switched it off', and the second is "
            f"recoverable by configuration while the first is not. Prefix the message with "
            f"'UPSTREAM:' and cite the measurement, or name the setting that would enable it.")

    def test_every_upstream_claim_cites_a_measurement(self):
        """A dated measurement, because 'Google cannot do this' is a claim with no expiry
        otherwise — and both of ApiBackend's upstream claims went stale within two months."""
        missing = [name for name, src in _raises_unsupported(ApiBackend).items()
                   if UPSTREAM in src and not MEASURED.search(src)]
        assert missing == [], (
            f"{missing} claim an upstream limit without a dated MEASURED line. Google's "
            f"surface moved twice this quarter; an undated claim cannot be reviewed.")

    def test_no_upstream_claim_still_demands_a_playwright_backend(self):
        """The specific drift that motivated all of this.

        `research/comments-apis-2026-09.md` §2.4 retires the `PlaywrightBackend`: both of its
        stated justifications now exist in Google's Developer Preview. A message still calling
        it REQUIRED would be telling a model to reach for a plan this project has abandoned.
        """
        for cls in (ApiBackend, FakeBackend):
            for name, src in _raises_unsupported(cls).items():
                assert "PlaywrightBackend is required" not in src, (
                    f"{cls.__name__}.{name} still says a PlaywrightBackend is required. It is "
                    f"not: the two operations that justified it are gated behind Developer "
                    f"Preview enrolment, not impossible.")


class TestTheUpstreamMessagesSayWhatWouldUNLOCKThem:
    """An upstream refusal that does not say what would change is a dead end presented as a
    fact. The point of the principle is that the answer is never 'sorry, no'."""

    UNLOCKS = ("Developer Preview", "enrolment", "scope", "Workaround", "workaround")

    def test_each_one_offers_a_route_or_a_workaround(self):
        silent = []
        for name, src in _raises_unsupported(ApiBackend).items():
            if UPSTREAM in src and not any(u in src for u in self.UNLOCKS):
                silent.append(name)
        assert silent == [], (
            f"{silent} state an upstream limit without saying what would unlock it or what to "
            f"do instead. 'Not supported' is the answer this principle exists to avoid.")


class TestThePrincipleIsWrittenDownWhereItIsRead:
    def test_the_exception_class_carries_it(self):
        """Not only in a spec. The docstring is what somebody reads when they hit the error and
        go looking, and it is what an agent reads when deciding how to word a reply."""
        doc = exc.UnsupportedOperation.__doc__ or ""
        assert "capability is never the constraint" in doc.lower()
        assert "UPSTREAM" in doc and "NOT ENABLED" in doc
