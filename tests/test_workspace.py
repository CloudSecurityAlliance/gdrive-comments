import pytest

from csa_google_workspace import Doc, Sheet, Slides, Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.workspace import parse_file_id

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
SLIDES = "application/vnd.google-apps.presentation"
FILES = {
    "d1": {"id": "d1", "name": "Doc", "mimeType": DOC, "webViewLink": "https://x/document/d/d1/edit"},
    "s1": {"id": "s1", "name": "Sheet", "mimeType": SHEET, "webViewLink": "https://x/spreadsheets/d/s1/edit"},
    "p1": {"id": "p1", "name": "Deck", "mimeType": SLIDES, "webViewLink": "https://x/presentation/d/p1/edit"},
}


@pytest.mark.parametrize("value,expected", [
    ("d1", "d1"),
    ("https://docs.google.com/document/d/ABC123/edit?tab=t.0", "ABC123"),
    ("https://docs.google.com/spreadsheets/d/S-9_x/edit#gid=0", "S-9_x"),
    ("https://drive.google.com/file/d/FID/view", "FID"),
])
def test_parse_file_id(value, expected):
    assert parse_file_id(value) == expected


def test_open_returns_typed_subclass():
    ws = Workspace(FakeBackend(FILES))
    assert isinstance(ws.open("d1"), Doc)
    assert isinstance(ws.open("s1"), Sheet)
    assert isinstance(ws.open("p1"), Slides)


def test_open_by_url_extracts_id_then_opens():
    ws = Workspace(FakeBackend(FILES))
    with pytest.warns(DeprecationWarning):
        d = ws.open_by_url("https://docs.google.com/document/d/d1/edit")
    assert isinstance(d, Doc) and d.id == "d1"


def test_read_only_propagates_to_document():
    ws = Workspace(FakeBackend(FILES), read_only=True)
    assert ws.open("d1").read_only is True


def test_from_credentials_wires_apibackend_and_propagates_read_only():
    """`from_credentials` is safe by default: the ApiBackend arrives wrapped in a
    PolicyBackend, and read_only collapses the policy to permitting nothing."""
    from csa_google_workspace.backend import ApiBackend
    from csa_google_workspace.policy import PolicyBackend
    ws = Workspace.from_credentials("sentinel-creds", read_only=True)
    assert ws.read_only is True
    assert isinstance(ws._backend, PolicyBackend)
    assert isinstance(ws._backend._inner, ApiBackend)
    assert ws._backend.policy.enabled == frozenset()


def test_from_credentials_applies_the_default_policy_when_none_is_given():
    from csa_google_workspace.policy import DEFAULT_ENABLED
    ws = Workspace.from_credentials("sentinel-creds")
    assert ws._backend.policy.enabled == DEFAULT_ENABLED


def test_from_credentials_honours_an_explicit_policy():
    from csa_google_workspace import policy as pol
    ws = Workspace.from_credentials("sentinel-creds",
                                    policy=pol.Policy.of(pol.FILE_SHARE))
    assert ws._backend.policy.enabled == frozenset({pol.FILE_SHARE})


def test_the_raw_seam_stays_ungated_for_embedders_who_want_it():
    """`Workspace(backend=...)` is documented as the DI seam and must not be second-guessed:
    an embedder supplying their own backend has already made the decision."""
    from csa_google_workspace.backend import FakeBackend
    from csa_google_workspace.policy import PolicyBackend
    ws = Workspace(FakeBackend({}))
    assert not isinstance(ws._backend, PolicyBackend)


def test_from_credentials_defaults_to_read_write():
    ws = Workspace.from_credentials("sentinel-creds")
    assert ws.read_only is False
