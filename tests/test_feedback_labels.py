"""Two feedback paths, two labels — because they are not the same kind of report.

The bug this fixes: both paths file into the same tracker and only one carried a label, so an
issue from a model helping a user was indistinguishable from a hand-written one. That defeats
the point of labelling at all, and #145's audit loop assumes the machine-assisted reports can
be filtered out.

They are separated rather than merged because triage order differs:

    automated-feedback   a demonstration run reporting on ITSELF. Unprompted, nobody is
                         blocked, and the interesting signal is the aggregate - twenty runs
                         all skipping the same step is a design problem.
    assisted-report      a PERSON has a problem right now and a model helped them describe
                         it. Somebody is stuck. Read these first.

Collapsing them loses that, which is why the test below asserts they stay distinct rather than
just asserting each is set.
"""
from __future__ import annotations

import asyncio
import urllib.parse

import pytest

from csa_google_workspace import Workspace, _environment
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.demo import _feedback as demo_feedback
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server


@pytest.fixture
def server():
    return create_server(lambda: Workspace(FakeBackend()),
                         settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*"}))


def labels_in(url: str) -> list[str]:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return query.get("labels", [])


class TestTheTwoLabelsAreDistinct:
    def test_neither_is_empty(self):
        assert _environment.DEMO_FEEDBACK_LABEL
        assert _environment.ASSISTED_REPORT_LABEL

    def test_they_are_not_the_same(self):
        """The whole point. If somebody 'simplifies' these into one constant, the tracker
        stops being able to answer 'is anybody actually stuck?'"""
        assert _environment.DEMO_FEEDBACK_LABEL != _environment.ASSISTED_REPORT_LABEL


class TestReportAProblemLabelsItsIssue:
    def test_the_prefilled_url_carries_the_assisted_report_label(self, server):
        out = asyncio.run(server.call_tool("report_a_problem", {})).structured_content
        assert labels_in(out["new_issue_url"]) == [_environment.ASSISTED_REPORT_LABEL]

    def test_the_label_is_reported_so_the_model_can_say_which_it_is(self, server):
        out = asyncio.run(server.call_tool("report_a_problem", {})).structured_content
        assert out["label"] == _environment.ASSISTED_REPORT_LABEL

    def test_it_does_not_use_the_demonstration_label(self, server):
        """The regression this file exists for, stated as its own test: before the fix this
        path carried NO label, and the obvious wrong fix is to give it the demo's one."""
        out = asyncio.run(server.call_tool("report_a_problem", {})).structured_content
        assert _environment.DEMO_FEEDBACK_LABEL not in labels_in(out["new_issue_url"])


class TestTheDemonstrationKeepsItsOwnLabel:
    def test_the_prefilled_url_still_carries_it(self):
        url = demo_feedback.new_issue_url("A title", "A body")
        assert labels_in(url) == [_environment.DEMO_FEEDBACK_LABEL]

    def test_the_module_constant_is_the_shared_one(self):
        """Defined once, in _environment, beside ISSUES_URL - the two labels and the tracker
        they belong to are one fact about where feedback goes."""
        assert demo_feedback.LABEL == _environment.DEMO_FEEDBACK_LABEL

    def test_the_body_still_names_the_label_it_will_be_filed_under(self):
        body = demo_feedback.issue_body("It worked", "24/24")
        assert _environment.DEMO_FEEDBACK_LABEL in body
