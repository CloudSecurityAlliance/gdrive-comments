"""A guided demonstration that is also the end-to-end test.

The two are the same artifact seen from different sides. A demonstration has to touch every
feature to be worth watching; an end-to-end test has to touch every feature to be worth running.
Written once, it is a tour for somebody new and a live-fire test for whoever maintains it — and
because people actually run demonstrations, the test gets exercised on real Google far more
often than a suite nobody remembers to opt into.

    csa-google-workspace-mcp demo              # narrated, and asks before each step
    csa-google-workspace-mcp demo --auto       # unattended: start it and come back
    csa-google-workspace-mcp demo --keep       # leave the files behind to look at

It creates a dated folder, then for EACH of Doc, Sheet and deck: creates the file, adds text,
edits it, removes it, comments, replies, edits the comment, resolves, reopens, deletes it,
exports, reads permissions, copies, renames, shares — then searches for what it made, and
trashes it again. Every operation against every type, because comments are one uniform API
across the three while content is three different ones, and that seam is where the bugs are.
"""
from __future__ import annotations

from ._plan import Outcome, Report, Step, build
from ._runner import NOT_EXERCISED, Runner, coverage, narrator, render

__all__ = ["NOT_EXERCISED", "Outcome", "Report", "Runner", "Step", "build", "coverage",
           "narrator", "render"]
