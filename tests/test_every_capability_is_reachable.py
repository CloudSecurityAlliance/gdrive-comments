"""A library capability with no tool must be a DECISION, not an oversight.

**#279.** Five things the library already did had no MCP tool — `Sheet.tabs`, `Sheet.clear`,
`Sheet.values`, `Doc.insert_text`, `Doc.delete_range` — and the pattern was not random: *you could
add content but not remove it, and write cells but not clear them.*

They accumulated silently **because nothing checked.** Every other invariant in this repository
that matters has a fail-closed guard — `policy._GATES` refuses an ungated `Backend` method,
`test_backend_conformance` refuses a protocol/fake mismatch, `test_repr_redaction` refuses an
undeclared `@dataclass`. The tool surface had no such guard, so it drifted.

This is that guard. Every public member of the document classes and collections either **has a
tool** or is **named below with a reason**. Adding a capability then forces the decision instead
of defaulting to invisible.

**Why an allowlist with reasons rather than a name-matching heuristic.** Naive matching produces
false positives — `as_text` is genuinely served by `read_file_content`, `share` by `share_file` —
and a heuristic loose enough to accept those is loose enough to accept a real gap. The reason
column is the point: it is what a reviewer reads, and what dates when a member's behaviour changes.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.documents.doc import Doc
from csa_google_workspace.documents.sheet import Sheet
from csa_google_workspace.documents.slides import Slides
from csa_google_workspace.files import FileCollection
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server

# Public members with no tool of their own, and why that is correct. Keyed `Class.member`.
#
# Three kinds of entry, and the distinction matters when reviewing one:
#   SERVED ELSEWHERE - a tool covers it under another name. The gap is nominal.
#   NOT A TOOL SHAPE - it is plumbing, or a helper a tool uses internally.
#   DELIBERATELY OUT  - it could be a tool and is not, by a recorded decision.
NO_TOOL_NEEDED: dict[str, str] = {
    # -- served elsewhere ------------------------------------------------------------------
    "Doc.as_text":            "SERVED: read_file_content",
    "Sheet.as_text":          "SERVED: read_file_content",
    "Slides.as_text":         "SERVED: read_file_content",
    "Doc.as_markdown":        "SERVED: read_file_content(format=) / download_file_content",
    "Doc.paragraphs":         "SERVED: read_file_content returns the text these compose",
    # Reachable through a PARAMETER rather than a tool of its own, which is deliberate: the
    # cost model is one document fetch per CALL, so it has to ride on an existing bulk
    # retrieval. A `get_comment_context(commentId)` tool would invite a loop and turn one fetch
    # into ninety (#358 is explicit that a per-comment follow-up is the thing to avoid).
    "Doc.comment_contexts":   "SERVED: list_comments(context=true) / get_comment(context=true) "
                              "/ export_comments(context=true)",
    "Doc.export":             "SERVED: download_file_content",
    "Sheet.export":           "SERVED: download_file_content",
    "Slides.export":          "SERVED: download_file_content",
    # Reclassified while writing this: these were marked SERVED, and the test below caught
    # that no tool serves them. They are not tool-shaped - a static table behind a round trip.
    "Doc.export_formats":     "NOT A TOOL: a static format table; download_file_content "
                              "converts, and the list itself is documentation",
    "Sheet.export_formats":   "NOT A TOOL: as Doc.export_formats",
    "Sheet.resolve_tab":      "NOT A TOOL: name -> real tab title, used BY comments_by_cell "
                              "(and public only so the MCP layer resolves identically rather "
                              "than drifting). list_tabs already exposes the titles",
    "Slides.export_formats":  "NOT A TOOL: as Doc.export_formats",
    "Doc.share":              "SERVED: share_file",
    "Sheet.share":            "SERVED: share_file",
    "Slides.share":           "SERVED: share_file",
    "Doc.set_role":           "SERVED: update_file_permission",
    "Sheet.set_role":         "SERVED: update_file_permission",
    "Slides.set_role":        "SERVED: update_file_permission",
    "FileCollection.set_role": "SERVED: update_file_permission",
    "Doc.unshare":            "SERVED: unshare_file",
    "Sheet.unshare":          "SERVED: unshare_file",
    "Slides.unshare":         "SERVED: unshare_file",
    "Doc.rename":             "SERVED: update_file",
    "Sheet.rename":           "SERVED: update_file",
    "Slides.rename":          "SERVED: update_file",
    "Doc.move":               "SERVED: update_file (add/remove parent)",
    "Sheet.move":             "SERVED: update_file",
    "Slides.move":            "SERVED: update_file",
    "Doc.untrash":            "SERVED: trash_file(untrash=true)",
    "Sheet.untrash":          "SERVED: trash_file(untrash=true)",
    "Slides.untrash":         "SERVED: trash_file(untrash=true)",
    "Doc.accept_access_proposal":  "SERVED: resolve_access_proposal(approve=true)",
    "Sheet.accept_access_proposal": "SERVED: resolve_access_proposal(approve=true)",
    "Slides.accept_access_proposal": "SERVED: resolve_access_proposal(approve=true)",
    "Doc.deny_access_proposal":    "SERVED: resolve_access_proposal(approve=false)",
    "Sheet.deny_access_proposal":  "SERVED: resolve_access_proposal(approve=false)",
    "Slides.deny_access_proposal": "SERVED: resolve_access_proposal(approve=false)",
    "Doc.find_access_proposal":    "SERVED: list_access_proposals, then match locally - the "
                                   "matching is the caller's once it holds the list",
    "Sheet.find_access_proposal":  "SERVED: list_access_proposals, then match locally",
    "Slides.find_access_proposal": "SERVED: list_access_proposals, then match locally",
    "Sheet.tab_details":      "SERVED: list_tabs returns exactly this",
    "Sheet.values":           "SERVED: read_range",
    "FileCollection.recent":  "SERVED: list_recent_files",
    # -- not a tool shape -----------------------------------------------------------------
    "Doc.reload":             "NOT A TOOL: accessors re-fetch per call, so a tool would be a "
                              "no-op with a confusing name",
    "Sheet.reload":           "NOT A TOOL: as above",
    "Slides.reload":          "NOT A TOOL: as above",
    # -- deliberately out, by recorded decision -------------------------------------------
    "Doc.batch_update":       "OUT: the raw escape hatch, explicitly 'Out (v1)' in "
                              "docs/superpowers/specs/2026-07-23-mcp-server-design.md",
    "Sheet.batch_update":     "OUT: as above",
    "Slides.batch_update":    "OUT: as above",
}

WATCHED = (Doc, Sheet, Slides, FileCollection)


@pytest.fixture(scope="module")
def tool_names() -> set[str]:
    app = create_server(lambda: Workspace(FakeBackend({})),
                        settings=settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                                    "CSA_GW_ALLOWLIST_MODIFY": "*",
                                                    "CSA_GW_PROFILE": "full"}))
    return {t.name for t in asyncio.run(app.list_tools())}


def public_members() -> list[tuple[str, str]]:
    """`(Class.member, member)` for every public method and property on the watched classes."""
    out = []
    for cls in WATCHED:
        for name, value in inspect.getmembers(cls):
            if name.startswith("_"):
                continue
            if inspect.isfunction(value) or isinstance(value, property):
                out.append((f"{cls.__name__}.{name}", name))
    return out


def _has_tool(member: str, tools: set[str]) -> bool:
    """A tool named for it, allowing the file-shaped prefixes the surface actually uses."""
    stem = member.replace("_", "")
    return any(stem == t.replace("_", "") or t.replace("_", "").endswith(stem)
               or t.replace("_", "").startswith(stem) for t in tools)


class TestEveryLibraryCapabilityIsReachableOrDeclared:
    def test_nothing_is_silently_unreachable(self, tool_names):
        """The guard. A new library capability fails here until it gets a tool or a reason."""
        undeclared = sorted(
            key for key, member in public_members()
            if key not in NO_TOOL_NEEDED and not _has_tool(member, tool_names))
        assert undeclared == [], (
            f"these library capabilities have no MCP tool and no recorded reason: {undeclared}. "
            f"Either add a tool, or add the member to NO_TOOL_NEEDED saying why not. #279 exists "
            f"because five of these accumulated while nothing checked.")

    def test_the_declared_list_names_nothing_that_is_gone(self, tool_names):
        """A stale exemption is worse than none: it reads as a considered decision about code
        that no longer exists, and it silently covers a NEW member reusing the name."""
        present = {key for key, _ in public_members()}
        stale = sorted(set(NO_TOOL_NEEDED) - present)
        assert stale == [], f"NO_TOOL_NEEDED names members that no longer exist: {stale}"

    def test_every_reason_says_which_kind_it_is(self):
        """`SERVED` / `NOT A TOOL` / `OUT` are three different claims, and a reader needs to know
        which one they are being asked to accept. A bare sentence invites 'that sounds fine'."""
        vague = sorted(k for k, why in NO_TOOL_NEEDED.items()
                       if not why.startswith(("SERVED", "NOT A TOOL", "OUT")))
        assert vague == [], f"these reasons do not say which kind of exemption they are: {vague}"

    def test_a_served_reason_names_a_tool_that_exists(self, tool_names):
        """The commonest way this list rots: a tool is renamed and the exemption still points at
        the old name, so the member looks covered and is not."""
        broken = []
        for key, why in NO_TOOL_NEEDED.items():
            if not why.startswith("SERVED:"):
                continue
            if not any(tool in why for tool in tool_names):
                broken.append(key)
        assert broken == [], (
            f"these say SERVED but name no existing tool: {broken}. If the tool was renamed, "
            f"update the reason; if it was removed, this is a real gap again.")
