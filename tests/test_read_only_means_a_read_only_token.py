"""`read_only` gets its own credential, so the posture is a scope guarantee and not a promise.

`_read_cached` accepted a granted read-write scope as satisfying a required read-only one, so
`load_cached_credentials(read_only=True)` returned the **full-Drive credential** on any machine
that had ever run `login`. `CSA_GW_READ_ONLY=1` therefore installed an empty `Policy` over a
full-write token: a client-side block, not a narrower credential. Any path reaching the
credential without passing the `Policy` gates had full write.

**Why this outranks its severity.** It is GA-#13 from the 2026-07-22 audit, deprioritised then as
*"interim PoC scaffolding"* on the assumption that `from_oauth` / `token.json` never runs in the
shipped server. `mcp/_login.py` and `mcp/_auth_flow.py` exist now, so the assumption is gone. And
**both prior audits name a read-only posture as the primary bound on prompt injection** — which
makes this the top-rated risk's main mitigation failing open.

Two changes, and one alone would not be enough:

  * **A separate cache file.** `token.json` for read-write, `token.readonly.json` for read-only,
    derived from whatever `CSA_GW_TOKEN` is set to. A read-write cache cannot satisfy a read-only
    requirement because it is not the file being read.
  * **Write scopes are refused outright** in a read-only posture. File separation alone is a
    *filename* guarantee: copy a read-write token to the read-only path, or grant broadly at the
    consent screen, and the old hole reopens. The posture now checks what the token actually
    carries.

**`needs_reconsent` is deliberately unchanged.** As a statement about OAuth it is correct — a
write scope really does satisfy a read requirement at Google — and `tests/test_auth.py` is right
to assert it. The defect was never that predicate; it was the *policy* of accepting its answer for
a posture whose whole purpose is a narrower credential. Fixing the predicate would have made a
true thing false.

**Deliberately kept:** refresh still works without a browser, for whichever posture has a token.
The comment being removed cited "headless refresh" as the reason for sharing the cache, and that
reason survives the separation — each file refreshes on its own.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from csa_google_workspace import auth
from csa_google_workspace.exceptions import AuthError

RW = auth.scopes_for(False)
RO = auth.scopes_for(True)


def write_token(path, scopes):
    """A cache file shaped like one `Credentials.to_json()` produces."""
    path.write_text(json.dumps({
        "token": "at", "refresh_token": "rt", "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid", "client_secret": "cs", "scopes": list(scopes),
        "expiry": "2099-01-01T00:00:00",
    }), encoding="utf-8")
    return str(path)


class TestTheTwoPosturesUseDifferentFiles:
    def test_read_write_uses_the_configured_path(self):
        assert auth.token_path_for("/t/token.json", read_only=False) == "/t/token.json"

    def test_read_only_derives_its_own(self):
        assert auth.token_path_for("/t/token.json", read_only=True) == "/t/token.readonly.json"

    @pytest.mark.parametrize("configured,expected", [
        ("/t/token.json", "/t/token.readonly.json"),
        ("/t/token-csa.json", "/t/token-csa.readonly.json"),
        ("/t/token", "/t/token.readonly.json"),          # no extension: still a .json file
        ("~/.csa/tok.json", "~/.csa/tok.readonly.json"), # expansion is the caller's business
    ])
    def test_it_derives_rather_than_requiring_a_second_setting(self, configured, expected):
        """Derived, not configured: an operator who has to set two paths will set one."""
        assert auth.token_path_for(configured, read_only=True) == expected

    def test_the_derivation_is_idempotent(self):
        """An operator may well set CSA_GW_TOKEN to the derived path. Applying the suffix twice
        would point at a `.readonly.readonly.json` that nothing writes."""
        once = auth.token_path_for("/t/token.json", read_only=True)
        assert auth.token_path_for(once, read_only=True) == once

    def test_the_two_never_collide(self):
        assert (auth.token_path_for("/t/token.json", read_only=True)
                != auth.token_path_for("/t/token.json", read_only=False))


class TestAReadWriteCacheCannotSatisfyReadOnly:
    def test_the_original_defect(self, tmp_path):
        """A machine that has run `login` has a read-write token. Asking for read-only used to
        hand it straight back."""
        path = write_token(tmp_path / "token.json", RW)
        with pytest.raises(AuthError):
            auth.load_cached_credentials(path, read_only=True)

    def test_and_the_message_says_what_to_do(self, tmp_path):
        path = write_token(tmp_path / "token.json", RW)
        with pytest.raises(AuthError) as e:
            auth.load_cached_credentials(path, read_only=True)
        message = str(e.value).lower()
        assert "read-only" in message or "read only" in message
        assert "write" in message, "the reason must name the scopes the token actually carries"

    def test_even_a_partial_write_scope_is_refused(self, tmp_path):
        """One write scope among read-only ones is still a write credential."""
        mixed = [*RO, RW[0]]
        path = write_token(tmp_path / "token.json", mixed)
        with pytest.raises(AuthError):
            auth.load_cached_credentials(path, read_only=True)

    def test_a_read_only_token_is_accepted(self, tmp_path):
        """Note the argument: callers pass the CONFIGURED path and the derivation happens
        inside, so the file on disk is the derived one."""
        write_token(tmp_path / "token.readonly.json", RO)
        creds = auth.load_cached_credentials(str(tmp_path / "token.json"), read_only=True)
        assert set(creds.scopes) == set(RO)

    def test_read_write_still_works_as_before(self, tmp_path):
        path = write_token(tmp_path / "token.json", RW)
        creds = auth.load_cached_credentials(path, read_only=False)
        assert set(creds.scopes) == set(RW)

    def test_a_read_only_token_still_cannot_serve_read_write(self, tmp_path):
        """The other direction, which always worked and must keep working."""
        path = write_token(tmp_path / "token.json", RO)
        with pytest.raises(AuthError):
            auth.load_cached_credentials(path, read_only=False)


class TestTheScopePredicateIsUntouched:
    """`needs_reconsent` is a true statement about OAuth and stays one. The fix is a policy
    decision layered above it, not a correction to it."""

    def test_a_write_scope_still_satisfies_a_read_requirement_as_a_scope_fact(self):
        assert auth.needs_reconsent(granted=RW, required=RO) is False

    def test_which_is_why_the_posture_check_is_separate(self, tmp_path):
        """The predicate says yes; the posture says no. Both are correct."""
        assert auth.needs_reconsent(granted=RW, required=RO) is False
        with pytest.raises(AuthError):
            auth.load_cached_credentials(write_token(tmp_path / "t.json", RW), read_only=True)


class TestTheCliNoLongerOverclaims:
    def test_it_does_not_say_narrows_unconditionally(self):
        from csa_google_workspace.mcp import cli
        text = cli.__doc__ or ""
        help_text = getattr(cli, "USAGE", "") or text
        assert "also narrows the OAuth scopes)" not in help_text, (
            "that reads as unconditional; it is true only of a fresh consent")


class TestTheWriterAndTheReaderAgree:
    """The gap this fix nearly introduced, and the reason it is guarded rather than remembered.

    Separating the caches is only useful if everything that WRITES a token derives the path the
    same way everything that READS one does. `mcp/_tools/auth.py` wrote to
    `settings.token_path` directly, so with `CSA_GW_READ_ONLY=1` the `authenticate` tool would
    have written a perfectly good read-only token to `token.json` while the server looked in
    `token.readonly.json` — leaving the posture permanently unsatisfiable, with no error
    explaining why.

    Caught by reading the call sites rather than by a test, which is why there is now a test.
    """

    def test_no_write_site_uses_the_raw_configured_path(self):
        """Reflective on the source, because the failure is a missing call and there is nothing
        to observe at runtime until somebody is stuck."""
        import inspect

        from csa_google_workspace.mcp import _login
        from csa_google_workspace.mcp._tools import auth as auth_tool

        for module in (auth_tool, _login):
            source = inspect.getsource(module)
            # every persistence call must route through the derivation
            for call in ("finish(flow, redirect, settings.token_path)",
                         "_write_token(settings.token_path"):
                assert call not in source, (
                    f"{module.__name__} writes a token to the raw configured path; a read-only "
                    f"posture reads a different file, so the token would land where nothing "
                    f"looks for it")

    def test_a_round_trip_through_the_derived_path_works(self, tmp_path):
        """Write where the writer writes, read where the reader reads, and they must meet."""
        configured = str(tmp_path / "token.json")
        write_token(pathlib.Path(auth.token_path_for(configured, read_only=True)), RO)
        creds = auth.load_cached_credentials(configured, read_only=True)
        assert set(creds.scopes) == set(RO)

    def test_and_the_read_write_token_beside_it_is_untouched(self, tmp_path):
        """The message promises this: consenting read-only must not disturb an existing
        read-write token, or people will not do it."""
        configured = str(tmp_path / "token.json")
        write_token(pathlib.Path(configured), RW)
        write_token(pathlib.Path(auth.token_path_for(configured, read_only=True)), RO)
        assert set(auth.load_cached_credentials(configured, read_only=True).scopes) == set(RO)
        assert set(auth.load_cached_credentials(configured, read_only=False).scopes) == set(RW)
