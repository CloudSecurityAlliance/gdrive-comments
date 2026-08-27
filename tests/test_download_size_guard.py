"""Refuse an oversized download **before** fetching it, not after.

`download_file_content` on a non-openable file pulled the whole thing into memory with
`get_media().execute()` and only *then* compared it to `MAX_DOWNLOAD_BYTES`. So the cap
protected the *response* and not the *process*: a 2 GB video, or a disk image somebody parked
in Drive, was read into RAM in full and only afterwards refused.

Because the server is a long-lived **stdio child of the MCP client**, an OOM there does not
fail one call — it takes out the session.

And there was no pre-check available even in principle: `get_file_metadata` requested
`fields="id,name,mimeType,webViewLink"`, with **no `size`**, so nothing in the process knew how
big the file was before asking for it.

This is exposure that arrived with a feature. Before non-native download existed, the cap only
ever applied to Google-native *exports*, which Drive bounds itself. It is also reachable with no
malice at all: *"download that file for me"* on a file the user has forgotten is a video.

**Drive returns `size` for uploaded (binary) files and omits it for native Google files** — which
is exactly the split that matters, because the native path is the already-bounded one. So
`FileRef.size_bytes` follows the `parents` convention in the same class: `None` means *not known*,
never *zero*.

The post-download check stays as a backstop. `size` can be absent, and a cap that only trusts
metadata is a cap that trusts the thing it is guarding against.
"""
from __future__ import annotations

import asyncio

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp._tools.content import MAX_DOWNLOAD_BYTES
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

BIG = "big1"
SMALL = "small1"
NATIVE = "doc1"
OVER = MAX_DOWNLOAD_BYTES + 1


def build(*, big_media: bytes | None = None, declare_size: bool = True):
    """A large upload, a small one, and a native Doc.

    `declare_size=False` models Drive omitting `size` — the case the backstop exists for.
    """
    files = {
        BIG: {"id": BIG, "name": "holiday.mp4", "mimeType": "video/mp4"},
        SMALL: {"id": SMALL, "name": "notes.pdf", "mimeType": "application/pdf"},
        NATIVE: {"id": NATIVE, "name": "A Doc",
                 "mimeType": "application/vnd.google-apps.document"},
    }
    if declare_size:
        files[BIG]["size"] = str(OVER)          # Drive returns size as a STRING
        files[SMALL]["size"] = "11"
    media = {SMALL: b"hello world"}
    if big_media is not None:
        media[BIG] = big_media
    backend = FakeBackend(files, documents={NATIVE: {"body": {"content": []}}},
                          media=media, exports={(NATIVE, "text/plain"): b"hi"})
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_PROFILE": "editor"})
    app = create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st)
    return app, backend


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, {**args})).structured_content


class TestItRefusesBeforeReadingTheBytes:
    def test_an_oversized_upload_is_refused(self):
        app, _ = build(big_media=None)      # no media at all: reaching the fetch would KeyError
        with pytest.raises(Exception) as e:
            call(app, "download_file_content", fileId=BIG)
        assert "limit" in str(e.value).lower() or "mib" in str(e.value).lower()

    def test_it_never_fetches_the_bytes(self):
        """The actual defect. With no media registered, any attempt to fetch raises something
        that is *not* the size refusal — so this passes only if the check came first."""
        app, backend = build(big_media=None)
        fetched: list[str] = []
        original = backend.download_file

        def spy(file_id):
            fetched.append(file_id)
            return original(file_id)

        backend.download_file = spy                                   # type: ignore[method-assign]
        with pytest.raises(Exception, match="(?i)limit") as e:
            call(app, "download_file_content", fileId=BIG)
        assert fetched == [], "the bytes were fetched before the size was checked"
        # Matching on the refusal rather than any exception is the point: if the check ran
        # late, the spy would have raised something else entirely and this would not match.
        assert "not downloaded" in str(e.value).lower()

    def test_the_refusal_names_the_actual_size_and_the_cap(self):
        app, _ = build(big_media=None)
        with pytest.raises(Exception) as e:
            call(app, "download_file_content", fileId=BIG)
        message = str(e.value)
        assert str(MAX_DOWNLOAD_BYTES // (1024 * 1024)) in message, "the cap is not named"
        assert "10" in message      # the file's own size, in MiB, rounded


class TestItStillWorksForEverythingElse:
    def test_a_small_upload_downloads(self):
        app, _ = build()
        out = call(app, "download_file_content", fileId=SMALL)
        assert out["size_bytes"] == 11

    def test_a_native_export_is_unaffected(self):
        app, _ = build()
        out = call(app, "download_file_content", fileId=NATIVE, exportMimeType="text/plain")
        assert out["size_bytes"] == 2


class TestTheBackstopSurvives:
    def test_an_undeclared_size_is_still_caught_after_the_fetch(self):
        """Drive omits `size` for some files, and a cap that only trusts metadata trusts the
        thing it is guarding against. The post-download check must stay."""
        app, _ = build(big_media=b"x" * OVER, declare_size=False)
        with pytest.raises(Exception) as e:
            call(app, "download_file_content", fileId=BIG)
        assert "limit" in str(e.value).lower() or "mib" in str(e.value).lower()


class TestSizeIsOnTheFileRef:
    def test_size_bytes_is_populated_for_an_upload(self):
        app, backend = build()
        ws = Workspace(backend=backend)
        assert ws.files.get(BIG).size_bytes == OVER

    def test_size_bytes_is_none_for_a_native_file(self):
        """`None` means NOT KNOWN, following `parents` in the same class. Never zero: a native
        Doc has no `size` in Drive, and reporting 0 would be asserting a fact never checked."""
        app, backend = build()
        ws = Workspace(backend=backend)
        assert ws.files.get(NATIVE).size_bytes is None

    def test_a_string_size_from_drive_becomes_an_int(self):
        """Drive returns `size` as a decimal STRING. A `>` against a string would either raise
        or compare lexicographically, which is worse."""
        app, backend = build()
        ws = Workspace(backend=backend)
        assert isinstance(ws.files.get(SMALL).size_bytes, int)
