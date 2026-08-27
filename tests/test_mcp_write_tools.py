"""The tools that close the advertised-but-missing gap: content writes and file creation."""
import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp._config import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
PRES = "application/vnd.google-apps.presentation"
FILES = {
    "d": {"id": "d", "name": "Doc", "mimeType": DOC, "webViewLink": "https://x/d/d"},
    "s": {"id": "s", "name": "Sheet", "mimeType": SHEET, "webViewLink": "https://x/d/s"},
    "p": {"id": "p", "name": "Deck", "mimeType": PRES, "webViewLink": "https://x/d/p"},
}
BODY = {"body": {"content": [{"paragraph": {"elements": [
    {"textRun": {"content": "the revenue was 4.2M\n"}}]}}]}}


def _app(profile="editor", modify="*", read="*"):
    """Build a server whose Workspace actually carries the settings' policy.

    Note the PolicyBackend wrapper. `create_server(get_workspace, settings=...)` does NOT apply
    the policy — `WorkspaceProvider` does, and a caller supplying its own Workspace bypasses it
    by design (the raw `Workspace(backend=...)` seam is documented as unguarded). An earlier
    version of this helper omitted the wrapper and every policy assertion here passed
    vacuously.
    """
    be = FakeBackend(dict(FILES), documents={"d": BODY},
                     spreadsheets={"s": {"sheets": [
                         {"properties": {"sheetId": 0, "title": "Sheet1"}}]}},
                     presentations={"p": {"slides": []}})
    env = {"CSA_GW_ALLOWLIST_READ": read, "CSA_GW_ALLOWLIST_MODIFY": modify,
           "CSA_GW_PROFILE": profile}
    settings = settings_from_env(env)
    workspace = Workspace(PolicyBackend(be, settings.policy))
    return create_server(lambda: workspace, settings=settings), be


def _out(app, name, args):
    return asyncio.run(app.call_tool(name, args)).structured_content


# --- content writes ---------------------------------------------------------

def test_replace_text_reports_the_count():
    app, _ = _app()
    out = _out(app, "replace_text", {"fileId": "d", "find": "4.2M", "replace": "4.3M"})
    assert out["occurrences_changed"] == 1 and "replaced 1" in out["detail"]


def test_zero_replacements_is_a_result_not_an_error():
    """A model that treats 0 as failure will retry the same string forever. The detail says
    what to do instead."""
    app, _ = _app()
    out = _out(app, "replace_text", {"fileId": "d", "find": "nowhere", "replace": "x"})
    assert out["occurrences_changed"] == 0
    assert "differs from" in out["detail"]


def test_append_text_is_documents_only():
    app, _ = _app()
    _out(app, "append_text", {"fileId": "d", "text": "\nmore"})
    with pytest.raises(ToolError) as e:
        _out(app, "append_text", {"fileId": "s", "text": "x"})
    assert "spreadsheet" in str(e.value)


def test_update_cells_writes_and_counts():
    app, be = _app()
    out = _out(app, "update_cells", {"fileId": "s", "a1Range": "Sheet1!A1:B2",
                                     "values": [["a", "b"], ["c", "d"]]})
    assert out["occurrences_changed"] == 4
    assert be._writes, "the write did not reach the backend"


def test_update_cells_defaults_to_raw_and_user_entered_is_opt_in():
    """CHANGED in 0.30.0 (#181). This asserted USER_ENTERED "so formulas work" - true, and the
    wrong default: it made Google evaluate text derived from untrusted comment bodies as a
    formula, server-side, where IMPORTXML and friends fetch outbound. The legitimate half of
    the original intent is kept below - a formula is still writable, just deliberately.

    Full reasoning and the payload shapes: tests/test_raw_is_the_default.py.
    """
    app, be = _app()
    _out(app, "update_cells", {"fileId": "s", "a1Range": "A1", "values": [["=SUM(B1:B2)"]]})
    assert not any("USER_ENTERED" in str(w) for w in be._writes), \
        "a bare update_cells must not let Google parse the value as a formula"

    app, be = _app()
    _out(app, "update_cells", {"fileId": "s", "a1Range": "A1", "values": [["=SUM(B1:B2)"]],
                               "valueInputOption": "USER_ENTERED"})
    assert any("USER_ENTERED" in str(w) for w in be._writes), \
        "writing a real formula on purpose must still work"


def test_update_cells_rejects_a_flat_list():
    """`values` is rows-of-cells. A flat list would silently write one row of characters."""
    app, _ = _app()
    with pytest.raises(ToolError):
        _out(app, "update_cells", {"fileId": "s", "a1Range": "A1", "values": ["a", "b"]})


def test_insert_slide_text_is_decks_only():
    app, _ = _app()
    with pytest.raises(ToolError) as e:
        _out(app, "insert_slide_text", {"fileId": "d", "objectId": "x", "text": "y"})
    assert "slide decks" in str(e.value)


def test_content_writes_need_the_capability():
    app, _ = _app(profile="commenter")
    with pytest.raises(ToolError) as e:
        _out(app, "replace_text", {"fileId": "d", "find": "a", "replace": "b"})
    assert "content.write" in str(e.value)


def test_content_writes_respect_the_modify_allowlist():
    app, _ = _app(modify="https://docs.google.com/document/d/somethingelseentirely/edit")
    with pytest.raises(ToolError) as e:
        _out(app, "replace_text", {"fileId": "d", "find": "a", "replace": "b"})
    assert "not in the modify allowlist" in str(e.value)


# --- creation ---------------------------------------------------------------

@pytest.mark.parametrize("kind", ["document", "spreadsheet", "presentation", "folder"])
def test_create_file_makes_each_kind(kind):
    app, _ = _app()
    out = _out(app, "create_file", {"name": f"a {kind}", "kind": kind})
    assert out["name"] == f"a {kind}" and out["url"]
    assert (out["mime_type"] == "application/vnd.google-apps.folder") == (kind == "folder")


def test_create_file_rejects_an_unknown_kind():
    app, _ = _app()
    with pytest.raises(ToolError) as e:
        _out(app, "create_file", {"name": "x", "kind": "pdf"})
    assert "presentation" in str(e.value)          # the error lists the real kinds


def test_create_file_with_markdown_uploads_it_for_conversion():
    """The other half of the round-trip: Doc.as_markdown() out, this in. Drive converts, so
    `# Heading` becomes a heading rather than a literal hash."""
    app, be = _app()
    out = _out(app, "create_file", {"name": "n", "kind": "document",
                                    "content": "# Title\n\n- one\n- two\n"})
    uploaded = be._files[out["id"]]["_uploaded"]
    assert uploaded["as"] == "text/markdown" and uploaded["bytes"] > 0


def test_create_file_refuses_content_for_a_spreadsheet():
    app, _ = _app()
    with pytest.raises(ToolError) as e:
        _out(app, "create_file", {"name": "n", "kind": "spreadsheet", "content": "a,b"})
    assert "only supported for documents" in str(e.value)


def test_create_file_accepts_a_parent():
    app, be = _app()
    folder = _out(app, "create_file", {"name": "f", "kind": "folder"})
    child = _out(app, "create_file", {"name": "c", "kind": "document",
                                      "parentId": folder["id"]})
    assert be._files[child["id"]]["parents"] == [folder["id"]]


def test_create_is_not_restricted_by_the_modify_allowlist():
    """A file that does not exist yet cannot be damaged. Writing to it afterwards is gated."""
    app, _ = _app(modify="https://docs.google.com/document/d/somethingelseentirely/edit")
    created = _out(app, "create_file", {"name": "n", "kind": "document"})
    with pytest.raises(ToolError) as e:
        _out(app, "append_text", {"fileId": created["id"], "text": "x"})
    assert "not in the modify allowlist" in str(e.value)


def test_create_needs_the_file_create_capability():
    app, _ = _app(profile="commenter")
    with pytest.raises(ToolError) as e:
        _out(app, "create_file", {"name": "n", "kind": "document"})
    assert "file.create" in str(e.value)


def test_copy_file_produces_a_new_id():
    app, _ = _app()
    out = _out(app, "copy_file", {"fileId": "d"})
    assert out["id"] != "d" and "Copy of Doc" in out["name"]


def test_copy_file_needs_the_source_readable():
    """copy_file reads a source, so the source must be in the READ scope — and the copy it
    produces is a new file, hence not in the modify allowlist either. Copying cannot be used to
    obtain a writable duplicate of something unwritable."""
    app, _ = _app(read="https://docs.google.com/document/d/somethingelseentirely/edit")
    with pytest.raises(ToolError) as e:
        _out(app, "copy_file", {"fileId": "d"})
    assert "read allowlist" in str(e.value)
