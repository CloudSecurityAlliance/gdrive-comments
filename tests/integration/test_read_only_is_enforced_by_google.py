"""L2-RO — prove the read-only posture is refused by GOOGLE, not merely by our own guard.

Spec: `docs/superpowers/specs/2026-09-05-conformance-rig.md` §5a.

**There are three layers of read-only and only one of them is proof.**

* **client guard** (`_require_writable` -> `ReadOnlyError`) proves *our code declined to try*,
  and survives nothing — it is our own code.
* **token scope** (`CSA_GW_READ_ONLY=1` -> `.readonly` only) proves **Google refuses the call**,
  and survives a bug in the guard, a bypassed policy, and a stolen token.
* **capability gating** proves an operator's configured ceiling.

The same asymmetry `restrictions.py` records: *"Google will refuse this"* is categorically
stronger than *"our policy is configured not to"*.

**Everything that existed before this file tested layer one.**
`tests/oauth/test_oauth_flow.py::test_read_only_oauth_session_reads_but_refuses_writes` says so
in its own docstring — *"blocks writes at the client guard"* — and thirteen offline files assert
`ReadOnlyError` the same way. Nothing anywhere confirmed the read-only **token** cannot write.

That is not hypothetical. **#327 was exactly this bug**: `has_write_scope` was an allowlist of
four known write scopes, so a token carrying `drive.file` — a real write scope this project
never requests — answered `False` and was accepted as read-only. A credential that could write,
treated as one that could not, in the check whose whole job is preventing that.

So these tests **go around our own client guard on purpose**, straight to the Drive service with
the read-only credentials. The guard is precisely what is *not* under test here; if it fires
first, the test has not done what it claims and fails as inconclusive rather than passing.
"""
from __future__ import annotations

import contextlib
import os

import pytest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from csa_google_workspace import exceptions as exc
from csa_google_workspace.auth import (
    has_write_scope,
    load_cached_credentials,
    token_path_for,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("CSA_GW_INTEGRATION") != "1",
    reason="set CSA_GW_INTEGRATION=1 to run live Google tests",
)

TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")

# Google answers an out-of-scope write with one of these. Both are accepted because the code
# has been observed to vary by endpoint; what is NOT accepted is anything that is not a refusal
# from Google, which is the whole point of the file.
REFUSAL_STATUSES = (401, 403)


def _creds(read_only: bool):
    """Credentials for one posture, or skip. Each posture has its OWN cache file."""
    path = token_path_for(os.path.expanduser(TOKEN), read_only)
    if not os.path.exists(path):
        posture = "CSA_GW_READ_ONLY=1 " if read_only else ""
        pytest.skip(
            f"no {'read-only' if read_only else 'read-write'} token at {path}. "
            f"Authorize it: {posture}csa-google-workspace-mcp login"
        )
    return load_cached_credentials(path, read_only=read_only)


def _drive(read_only: bool):
    """A RAW Drive client — no Workspace, no PolicyBackend, no client guard.

    Going around our own guard is the entire technique. Through `Workspace`,
    `_require_writable()` raises `ReadOnlyError` before a request is ever made, so the call
    never reaches Google and the interesting question is never asked.
    """
    return build("drive", "v3", credentials=_creds(read_only))


def _assert_google_refused(caught, what: str):
    """The assertion that makes this file worth having.

    A test that accepted *either* `ReadOnlyError` or a Google 403 would silently degrade into
    testing the client guard the moment the guard fired first — which is exactly how this
    property came to be untested.
    """
    assert not isinstance(caught, exc.ReadOnlyError), (
        f"{what}: our OWN guard refused this, so the request never reached Google and this "
        f"test proved nothing about the token. Inconclusive, not passing."
    )
    assert isinstance(caught, HttpError), f"{what}: expected a refusal from Google, got {caught!r}"
    status = int(getattr(caught.resp, "status", 0) or 0)
    assert status in REFUSAL_STATUSES, (
        f"{what}: Google answered {status}, which is not a refusal. "
        f"If this write SUCCEEDED, treat it as a security finding, not a test failure."
    )


# ---------------------------------------------------------------- the configuration check

def test_the_read_only_credential_carries_no_write_scope():
    """What the token was GRANTED. Necessary, and on its own not sufficient — see below."""
    granted = list(_creds(read_only=True).scopes or [])
    assert granted, "the credential reports no scopes at all; refusing to read that as safe"
    assert not has_write_scope(granted), f"read-only credential carries a write scope: {granted}"
    non_readonly = [s for s in granted if not s.endswith(".readonly")]
    assert not non_readonly, f"granted scopes that are not .readonly: {non_readonly}"


def test_the_two_postures_do_not_share_a_cache_file():
    """#185: separate files are what make the guarantee 'which file exists'.

    If read-only could ever be satisfied from the read-write cache, `CSA_GW_READ_ONLY=1` would
    be a client-side policy over a full-write credential — which is the #327 failure wearing a
    different hat.
    """
    rw = token_path_for(os.path.expanduser(TOKEN), False)
    ro = token_path_for(os.path.expanduser(TOKEN), True)
    assert rw != ro, "both postures resolve to the same cache file"


# ---------------------------------------------------------------- read-only must still READ

def test_read_only_can_actually_read():
    """A posture that refuses everything is not a passing read-only, it is a broken credential.

    Worth its own test: every assertion below is about a refusal, and a dead token would make
    all of them pass for the wrong reason.
    """
    me = _drive(read_only=True).about().get(fields="user(emailAddress)").execute()
    assert me["user"]["emailAddress"], "read-only credential cannot even identify itself"


# ---------------------------------------------------------------- the refusals that matter

def test_google_refuses_a_FILE_CREATE_from_the_read_only_token():
    """The broadest write there is, and the easiest to clean up if it wrongly succeeds."""
    drive = _drive(read_only=True)
    name = "L2RO-SHOULD-NEVER-EXIST"
    created = None
    try:
        created = drive.files().create(
            body={"name": name, "mimeType": "application/vnd.google-apps.document"},
            fields="id").execute()
    except Exception as e:                                   # noqa: BLE001 - classified below
        _assert_google_refused(e, "files.create")
        return
    finally:
        if created:
            # It should not exist. Remove it anyway - a write succeeding does not make the
            # artefact wanted, and leaving it turns one finding into two problems.
            with contextlib.suppress(Exception):
                _drive(read_only=False).files().update(
                    fileId=created["id"], body={"trashed": True}).execute()
    pytest.fail(
        "SECURITY FINDING, not a test failure: a READ-ONLY credential created a file. "
        f"Granted scopes: {list(_creds(read_only=True).scopes or [])}. "
        "Stop using this posture and report it."
    )


def test_google_refuses_a_COMMENT_CREATE_from_the_read_only_token():
    """The write this library exists for, against a file the posture can genuinely see.

    The target is a throwaway made with the read-write credential, so a wrongly-succeeded write
    lands somewhere disposable — never on the zoo, which is public and cited by id.
    """
    rw = _drive(read_only=False)
    fid = rw.files().create(
        body={"name": "L2RO-target-THROWAWAY",
              "mimeType": "application/vnd.google-apps.document"}, fields="id").execute()["id"]
    try:
        try:
            _drive(read_only=True).comments().create(
                fileId=fid, body={"content": "this must never be posted"},
                fields="id").execute()
        except Exception as e:                               # noqa: BLE001 - classified below
            _assert_google_refused(e, "comments.create")
        else:
            pytest.fail(
                "SECURITY FINDING, not a test failure: a READ-ONLY credential posted a comment."
            )

        # "Refused" and "nothing changed" are different statements. Check the second one too:
        # a 403 does not by itself prove no side effect landed.
        after = rw.comments().list(fileId=fid, fields="comments(id)", pageSize=10).execute()
        assert after.get("comments", []) == [], "a comment exists despite the refusal"
    finally:
        with contextlib.suppress(Exception):
            rw.files().update(fileId=fid, body={"trashed": True}).execute()


# ---------------------------------------------------------------- the weaker layer, labelled

def test_the_client_guard_also_refuses_and_that_is_the_WEAKER_check():
    """Layer one, kept for completeness and labelled so it cannot be mistaken for layer two.

    This is what every pre-existing read-only test asserts. It proves our code declined to try,
    which is worth having and is not evidence about the token. The tests above are.
    """
    from csa_google_workspace import Workspace
    ws = Workspace.from_credentials(_creds(read_only=True), read_only=True)
    assert ws.read_only is True
    fid = _drive(read_only=False).files().create(
        body={"name": "L2RO-guard-THROWAWAY",
              "mimeType": "application/vnd.google-apps.document"}, fields="id").execute()["id"]
    try:
        with pytest.raises(exc.ReadOnlyError):
            ws.open(fid).create_comment("blocked before it reaches Google")
    finally:
        with contextlib.suppress(Exception):
            _drive(read_only=False).files().update(
                fileId=fid, body={"trashed": True}).execute()
