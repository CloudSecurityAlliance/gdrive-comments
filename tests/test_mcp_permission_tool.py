"""get_file_permissions — a read, so #82's write-narrow allowlist does not gate it."""
import asyncio

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp.server import create_server

DOC = "application/vnd.google-apps.document"
PERMS = [
    {"id": "p1", "type": "user", "role": "owner", "emailAddress": "kurt@example.org"},
    {"id": "p2", "type": "user", "role": "writer", "emailAddress": "rev@example.org"},
    {"id": "p3", "type": "anyone", "role": "reader"},
]


def _server(perms=PERMS):
    be = FakeBackend({"f": {"id": "f", "name": "F", "mimeType": DOC,
                            "webViewLink": "https://x/document/d/f"}},
                     permissions={"f": perms})
    return create_server(lambda: Workspace(be))


def _out(app, name, args):
    return asyncio.run(app.call_tool(name, args)).structured_content


def test_permissions_are_returned_with_emails():
    """Unlike everywhere else here, the email IS the answer — the question is *who*."""
    out = _out(_server(), "get_file_permissions", {"fileId": "f"})
    assert [p["id"] for p in out["permissions"]] == ["p1", "p2", "p3"]
    assert out["permissions"][0]["email"] == "kurt@example.org"


def test_the_rollups_answer_the_two_questions_a_reviewer_asks():
    out = _out(_server(), "get_file_permissions", {"fileId": "f"})
    assert out["public"] is True          # anyone-with-the-link
    assert out["writers"] == 2            # owner + writer, not the reader


def test_a_private_file_reports_public_false():
    out = _out(_server(perms=PERMS[:2]), "get_file_permissions", {"fileId": "f"})
    assert out["public"] is False and out["writers"] == 2


def test_it_accepts_a_share_url():
    out = _out(_server(), "get_file_permissions",
               {"fileId": "https://docs.google.com/document/d/f/edit"})
    assert len(out["permissions"]) == 3


def test_it_is_annotated_read_only():
    tools = {t.name: t for t in asyncio.run(_server().list_tools())}
    assert tools["get_file_permissions"].annotations.read_only_hint is True
