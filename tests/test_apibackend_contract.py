"""ApiBackend behaviors that FakeBackend cannot exercise (audit findings #6, #7):
comment-list pagination, and the non-idempotent wiring on every write method.
Both are only otherwise covered by the never-in-CI live suite.
"""
from csa_google_workspace.backend import ApiBackend

# --- #6: list_comments must follow nextPageToken and preserve filters ----------

class _Request:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _PagedComments:
    def __init__(self, pages):
        self._pages = pages
        self._i = 0
        self.calls = []          # kwargs of each list() call, in order

    def list(self, **kwargs):
        self.calls.append(kwargs)
        page = self._pages[self._i]
        self._i += 1
        return _Request(page)


class _Drive:
    def __init__(self, comments):
        self._comments = comments

    def comments(self):
        return self._comments


class _Services:
    def __init__(self, comments):
        self.drive = _Drive(comments)


def test_list_comments_paginates_and_preserves_filters():
    paged = _PagedComments([
        {"comments": [{"id": "c1"}, {"id": "c2"}], "nextPageToken": "tok"},
        {"comments": [{"id": "c3"}]},   # no nextPageToken -> stop
    ])
    backend = ApiBackend(_Services(paged))

    out = backend.list_comments("file1", include_deleted=True,
                                start_modified_time="2026-01-01T00:00:00Z")

    assert [c["id"] for c in out] == ["c1", "c2", "c3"]     # all pages, not truncated
    assert len(paged.calls) == 2
    assert "pageToken" not in paged.calls[0]                # first call: no token
    assert paged.calls[1]["pageToken"] == "tok"             # second: carried the token
    # filters preserved across pages
    assert paged.calls[0]["includeDeleted"] is True and paged.calls[1]["includeDeleted"] is True
    assert paged.calls[0]["startModifiedTime"] == "2026-01-01T00:00:00Z"
    assert paged.calls[1]["startModifiedTime"] == "2026-01-01T00:00:00Z"


# --- #7: every write must pass idempotent=False so 5xx never double-applies -----

class _Chain:
    """Accepts any attribute access and any call, returning itself; .execute() -> {}.
    Lets each write method build its request without a real Google client."""
    def __getattr__(self, name):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def execute(self):
        return {}


def test_all_writes_are_non_idempotent(monkeypatch):
    captured = []

    def fake_call(fn, *args, idempotent=True, _sleep=None, **kwargs):
        captured.append(idempotent)
        return {}

    monkeypatch.setattr("csa_google_workspace.backend._errors.call", fake_call)
    b = ApiBackend(_Chain())

    b.create_comment("f", "hi")
    b.create_reply("f", "c", content="x")
    b.update_comment("f", "c", "x")
    b.update_reply("f", "c", "r", "x")
    b.delete_comment("f", "c")
    b.delete_reply("f", "c", "r")
    b.docs_batch_update("f", [])
    b.sheets_values_update("f", "A1", [[1]])
    b.sheets_values_append("f", "A1", [[1]])
    b.sheets_values_clear("f", "A1")
    b.sheets_batch_update("f", [])
    b.slides_batch_update("f", [])

    assert captured == [False] * 12    # a single True here is a silent double-apply risk


class _FilesStub:
    """Minimal drive.files() double. The module's other stubs are shaped for comments()."""

    def __init__(self, result):
        self.result = result
        self.calls: dict = {}

    def list(self, **kwargs):
        self.calls.update(kwargs)
        return _Request(self.result)


class _DriveWithFiles:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


class _ServicesWithFiles:
    def __init__(self, files):
        self.drive = _DriveWithFiles(files)


def test_search_files_sends_the_query_and_shared_drive_flags():
    """`ApiBackend` is the only place the real Drive query string is built, and FakeBackend
    is deliberately not a Drive query engine — so the wiring is asserted here.

    includeItemsFromAllDrives/supportsAllDrives are not optional polish: shared drives are
    where collaborative review happens, and omitting them silently hides every file in one.
    """
    files = _FilesStub({"files": [{"id": "a"}], "nextPageToken": "t2"})
    out = ApiBackend(_ServicesWithFiles(files)).search_files(
        "name contains 'x'", page_size=7, order_by="modifiedTime desc", page_token="t1")

    assert out["files"] == [{"id": "a"}]
    assert files.calls["q"] == "name contains 'x'"
    assert files.calls["pageSize"] == 7
    assert files.calls["orderBy"] == "modifiedTime desc"
    assert files.calls["pageToken"] == "t1"
    assert files.calls["includeItemsFromAllDrives"] is True
    assert files.calls["supportsAllDrives"] is True
    assert "webViewLink" in files.calls["fields"]
    assert "nextPageToken" in files.calls["fields"]


def test_search_files_omits_order_by_and_page_token_when_unset():
    """Sending orderBy=None is not the same as omitting it; Drive rejects the former."""
    files = _FilesStub({"files": []})
    ApiBackend(_ServicesWithFiles(files)).search_files("q")
    assert "orderBy" not in files.calls and "pageToken" not in files.calls
