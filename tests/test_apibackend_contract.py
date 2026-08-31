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
    # #235: both permission mutations. `delete_permission` is the one that matters most here -
    # it returns None, so a retried 5xx that already landed would look like a clean second
    # revocation rather than an error, and the caller would never learn the first one worked.
    b.update_permission("f", "p1", role="reader")
    b.delete_permission("f", "p1")
    # Answering an access request. It returns None, like `delete_permission`, so a retried 5xx
    # that had already landed would look like a clean second resolve - and the mutation it may
    # have already applied is A GRANT OF ACCESS. Worst thing on this list to double-apply
    # silently, because the second call would report success for something already done and
    # nobody would go looking.
    b.resolve_access_proposal("f", "ap1", action="ACCEPT", roles=["reader"])

    assert captured == [False] * 15    # a single True here is a silent double-apply risk


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


class _PermsStub:
    """drive.permissions() double. Pages, and records every call's kwargs."""

    def __init__(self, pages):
        self._pages = pages; self._i = 0; self.calls: list[dict] = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        page = self._pages[self._i]; self._i += 1
        return _Request(page)


class _DriveWithPerms:
    def __init__(self, perms): self._perms = perms

    def permissions(self): return self._perms


class _ServicesWithPerms:
    def __init__(self, perms): self.drive = _DriveWithPerms(perms)


def test_list_permissions_follows_pagination_and_asks_for_the_pii_fields():
    """The default permissions.list response omits emailAddress and displayName, which are
    the entire point of the call. And supportsAllDrives is not optional: a file on a shared
    drive otherwise reports no permissions at all.

    FakeBackend cannot cover either — it has no pages and no `fields` — which is why this
    lives in the ApiBackend contract suite (CLAUDE.md invariant 4).
    """
    perms = _PermsStub([
        {"permissions": [{"id": "p1"}], "nextPageToken": "n1"},
        {"permissions": [{"id": "p2"}]},
    ])
    out = ApiBackend(_ServicesWithPerms(perms)).list_permissions("f")

    assert [p["id"] for p in out] == ["p1", "p2"]
    assert len(perms.calls) == 2
    assert perms.calls[0]["fileId"] == "f"
    assert "emailAddress" in perms.calls[0]["fields"]
    assert "displayName" in perms.calls[0]["fields"]
    assert perms.calls[0]["supportsAllDrives"] is True
    assert "pageToken" not in perms.calls[0]
    assert perms.calls[1]["pageToken"] == "n1"


# --- #235: the permission mutations, against a stub Drive service -----------------
#
# `FakeBackend` cannot catch a wrong field name, a missing `supportsAllDrives`, or a body built
# in the wrong shape - it never sees the request. That is the documented blind spot of the
# fake/real seam, and it is exactly how `Workspace.open()` once leaked a raw `HttpError` past a
# fully green suite.

class _RecordingPerms:
    def __init__(self):
        self.calls = []

    def update(self, **kw):
        self.calls.append(("update", kw))
        return _Chain()

    def delete(self, **kw):
        self.calls.append(("delete", kw))
        return _Chain()


class _DriveRecording:
    def __init__(self, perms):
        self._perms = perms

    def permissions(self):
        return self._perms


class _ServicesRecording:
    def __init__(self, perms):
        self.drive = _DriveRecording(perms)


def test_update_permission_sends_only_the_role_and_supports_shared_drives():
    perms = _RecordingPerms()
    ApiBackend(_ServicesRecording(perms)).update_permission("f1", "p9", role="reader")
    (name, kw), = perms.calls
    assert name == "update"
    assert kw["fileId"] == "f1" and kw["permissionId"] == "p9"
    assert kw["body"] == {"role": "reader"}, (
        "the body must carry the role and nothing else - sending `type` or `emailAddress` on an "
        "update is how a downgrade quietly becomes a different grant")
    assert kw["supportsAllDrives"] is True, (
        "without this the call fails on any shared drive, which is where shared documents live")


def test_delete_permission_sends_no_body_and_supports_shared_drives():
    perms = _RecordingPerms()
    ApiBackend(_ServicesRecording(perms)).delete_permission("f1", "p9")
    (name, kw), = perms.calls
    assert name == "delete"
    assert kw == {"fileId": "f1", "permissionId": "p9", "supportsAllDrives": True}


def test_update_permission_asks_for_the_fields_the_model_needs_back():
    """A downgrade that returns no role leaves the caller unable to confirm what it achieved."""
    perms = _RecordingPerms()
    ApiBackend(_ServicesRecording(perms)).update_permission("f1", "p9", role="commenter")
    fields = perms.calls[0][1]["fields"]
    for wanted in ("id", "role", "type"):
        assert wanted in fields


# --- accessproposals: pagination, and the body `resolve` actually sends ------------
#
# Both invisible to `FakeBackend`, which never sees a request (CLAUDE.md invariant 4).


class _ProposalsStub:
    def __init__(self, pages):
        self._pages, self._i = pages, 0
        self.list_calls, self.resolve_calls = [], []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        page = self._pages[self._i]
        self._i += 1
        return _Request(page)

    def resolve(self, **kwargs):
        self.resolve_calls.append(kwargs)
        return _Request({})


class _DriveWithProposals:
    def __init__(self, stub): self._stub = stub
    def accessproposals(self): return self._stub


class _ServicesWithProposals:
    def __init__(self, stub): self.drive = _DriveWithProposals(stub)


def test_list_access_proposals_follows_pagination():
    """A file with more pending requests than one page is exactly the file somebody needs the
    tool for. Stopping at page one would report a SHORTER queue than exists, which reads as
    "everyone has been dealt with"."""
    stub = _ProposalsStub([
        {"accessProposals": [{"proposalId": "a"}], "nextPageToken": "n1"},
        {"accessProposals": [{"proposalId": "b"}]},
    ])
    out = ApiBackend(_ServicesWithProposals(stub)).list_access_proposals("f")

    assert [p["proposalId"] for p in out] == ["a", "b"]
    assert len(stub.list_calls) == 2
    assert stub.list_calls[0]["fileId"] == "f"
    assert "pageToken" not in stub.list_calls[0]
    assert stub.list_calls[1]["pageToken"] == "n1"


def test_an_empty_page_is_an_empty_list_not_a_crash():
    """Drive omits `accessProposals` entirely when nothing is pending, and "nobody has asked"
    is the common case rather than an edge one."""
    stub = _ProposalsStub([{}])
    assert ApiBackend(_ServicesWithProposals(stub)).list_access_proposals("f") == []


def test_resolve_sends_the_action_and_the_role_google_expects():
    """The field names are Google's, not ours: `action`, `role` (a LIST, despite granting one
    role), `sendNotification`. A wrong name here is a 400 from Google that `FakeBackend` will
    never produce, on the one call that hands out access."""
    stub = _ProposalsStub([{}])
    ApiBackend(_ServicesWithProposals(stub)).resolve_access_proposal(
        "f", "ap1", action="ACCEPT", roles=["writer"], notify=True)

    call = stub.resolve_calls[0]
    assert call["fileId"] == "f" and call["proposalId"] == "ap1"
    assert call["body"] == {"action": "ACCEPT", "sendNotification": True, "role": ["writer"]}


def test_a_denial_sends_no_role_at_all():
    """A DENY carrying a role would be contradictory - naming an access level while refusing
    access - and it is the kind of thing an API accepts today and rejects later."""
    stub = _ProposalsStub([{}])
    ApiBackend(_ServicesWithProposals(stub)).resolve_access_proposal(
        "f", "ap1", action="DENY", notify=False)

    assert stub.resolve_calls[0]["body"] == {"action": "DENY", "sendNotification": False}


# --- labels: two APIs, and the parameter names differ from everything else here -------


class _LabelsFilesStub:
    def __init__(self, pages):
        self._pages, self._i = pages, 0
        self.calls = []

    def listLabels(self, **kwargs):        # noqa: N802 - Google's method name
        self.calls.append(kwargs)
        page = self._pages[self._i]
        self._i += 1
        return _Request(page)


class _LabelDefsStub:
    def __init__(self, result=None):
        self.calls = []
        self._result = result or {}

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return _Request(self._result)


class _DriveForLabels:
    def __init__(self, files): self._files = files
    def files(self): return self._files


class _ServicesForLabels:
    def __init__(self, files=None, defs=None):
        self.drive = _DriveForLabels(files)
        self._defs = defs

    @property
    def drivelabels(self):
        outer = self
        class _DL:
            def labels(self): return outer._defs
        return _DL()


def test_list_file_labels_paginates_with_maxResults_not_pageSize():
    """This endpoint spells its page size `maxResults`, unlike every other list in this backend,
    which uses `pageSize`. Sending `pageSize` is not an error - Google ignores it - so the call
    silently falls back to the default page size and a heavily-labelled file loses labels with
    no failure anywhere."""
    files = _LabelsFilesStub([
        {"labels": [{"id": "L1"}], "nextPageToken": "n1"},
        {"labels": [{"id": "L2"}]},
    ])
    out = ApiBackend(_ServicesForLabels(files=files)).list_file_labels("f")

    assert [x["id"] for x in out] == ["L1", "L2"]
    assert files.calls[0]["maxResults"] == 100
    assert "pageSize" not in files.calls[0], "wrong parameter name; Google would ignore it"
    assert "pageToken" not in files.calls[0]
    assert files.calls[1]["pageToken"] == "n1"


def test_a_file_with_no_labels_is_an_empty_list():
    files = _LabelsFilesStub([{}])
    assert ApiBackend(_ServicesForLabels(files=files)).list_file_labels("f") == []


def test_get_label_definition_asks_the_full_view():
    """`LABEL_VIEW_BASIC` omits `fields`, so without FULL the response cannot name a field or
    resolve a selection choice - which is most of the reason for calling the second API at all.
    The failure is quiet: a well-formed response that simply has no names in it."""
    defs = _LabelDefsStub({"id": "L1"})
    ApiBackend(_ServicesForLabels(defs=defs)).get_label_definition("L1")

    assert defs.calls[0]["view"] == "LABEL_VIEW_FULL"


def test_the_label_id_is_turned_into_a_resource_name():
    """The Drive Labels API addresses labels as `labels/{id}`, while Drive v3 hands back a bare
    id. Passing the bare id through is a 404 on a label that exists."""
    defs = _LabelDefsStub()
    ApiBackend(_ServicesForLabels(defs=defs)).get_label_definition("L1")
    assert defs.calls[0]["name"] == "labels/L1"


def test_an_already_qualified_name_is_not_doubled():
    """Idempotent, because a caller holding a resource name is the likelier mistake than one
    holding a bare id, and `labels/labels/L1` is a 404 that reads like a missing label."""
    defs = _LabelDefsStub()
    ApiBackend(_ServicesForLabels(defs=defs)).get_label_definition("labels/L1")
    assert defs.calls[0]["name"] == "labels/L1"
