"""Backend seam. ApiBackend uses the real Google APIs; FakeBackend is in-memory for tests.
Operations Google exposes only through the UI raise UnsupportedOperation on ApiBackend; a
future PlaywrightBackend could implement them without changing the public API."""
import copy
from typing import Any, Protocol

from . import _errors
from . import exceptions as exc

# A decoded Google API JSON object. Parameterizes the bare `dict` the Backend once used,
# so embedders reading the typed surface see intent rather than an opaque mapping.
JsonDict = dict[str, Any]


class Backend(Protocol):
    def get_file_metadata(self, file_id: str) -> JsonDict: ...
    def list_permissions(self, file_id: str) -> list[JsonDict]: ...
    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None: ...
    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None: ...
    def list_comments(self, file_id: str, include_deleted: bool = False,
                      start_modified_time: str | None = None) -> list[JsonDict]: ...
    def get_comment(self, file_id: str, comment_id: str,
                    include_deleted: bool = False) -> JsonDict: ...
    def create_comment(self, file_id: str, content: str) -> JsonDict: ...
    def create_reply(self, file_id: str, comment_id: str,
                     content: str | None = None, action: str | None = None) -> JsonDict: ...
    def update_comment(self, file_id: str, comment_id: str, content: str) -> JsonDict: ...
    def update_reply(self, file_id: str, comment_id: str, reply_id: str, content: str) -> JsonDict: ...
    def delete_comment(self, file_id: str, comment_id: str) -> None: ...
    def delete_reply(self, file_id: str, comment_id: str, reply_id: str) -> None: ...
    def export_file(self, file_id: str, mime_type: str) -> bytes: ...
    def download_file(self, file_id: str) -> bytes: ...
    # -- the account axis: no file_id, because there is no file yet ---------
    def search_files(self, query: str, *, page_size: int = 25, order_by: str | None = None,
                     page_token: str | None = None) -> JsonDict: ...
    def create_file(self, name: str, mime_type: str, *, parent_id: str | None = None,
                    content: bytes | None = None,
                    content_mime_type: str | None = None) -> JsonDict: ...
    def update_file_metadata(self, file_id: str, *, name: str | None = None,
                             add_parent: str | None = None,
                             remove_parent: str | None = None) -> JsonDict: ...
    def trash_file(self, file_id: str, *, trashed: bool = True) -> JsonDict: ...
    def create_permission(self, file_id: str, *, email: str | None, role: str,
                          permission_type: str = "user",
                          notify: bool = True) -> JsonDict: ...
    def update_permission(self, file_id: str, permission_id: str, *, role: str) -> JsonDict: ...
    def delete_permission(self, file_id: str, permission_id: str) -> None: ...
    def list_access_proposals(self, file_id: str) -> list[JsonDict]: ...
    def list_file_labels(self, file_id: str) -> list[JsonDict]: ...
    # Not file-scoped: a label DEFINITION belongs to the organisation, not to any one file.
    def get_label_definition(self, label_id: str) -> JsonDict: ...
    def resolve_access_proposal(self, file_id: str, proposal_id: str, *, action: str,
                                roles: list[str] | None = None, view: str | None = None,
                                notify: bool = True) -> None: ...
    def copy_file(self, file_id: str, *, name: str | None = None,
                  parent_id: str | None = None) -> JsonDict: ...
    def get_document(self, file_id: str, suggestions_view_mode: str | None = None) -> JsonDict: ...
    def get_spreadsheet(self, file_id: str) -> JsonDict: ...
    def get_values(self, file_id: str, a1_range: str) -> list[list[Any]]: ...
    def get_presentation(self, file_id: str) -> JsonDict: ...
    def docs_batch_update(self, file_id: str, requests: list[JsonDict]) -> JsonDict: ...
    def sheets_values_update(self, file_id: str, a1_range: str, values: list[list[Any]],
                             value_input_option: str = "RAW") -> JsonDict: ...
    def sheets_values_append(self, file_id: str, a1_range: str, values: list[list[Any]],
                             value_input_option: str = "RAW") -> JsonDict: ...
    def sheets_values_clear(self, file_id: str, a1_range: str) -> JsonDict: ...
    def sheets_batch_update(self, file_id: str, requests: list[JsonDict]) -> JsonDict: ...
    def slides_batch_update(self, file_id: str, requests: list[JsonDict]) -> JsonDict: ...


class FakeBackend:
    """In-memory backend for unit tests. `files` maps file_id -> metadata dict."""

    def __init__(self, files, *, documents=None, spreadsheets=None,
                 values=None, presentations=None, exports=None, media=None, comments=None,
                 permissions=None, access_proposals=None, file_labels=None,
                 label_definitions=None):
        self._files = files
        # Keyed (file_id, comment_id) -> raw Drive comment dict, matching what
        # create_comment() builds. The seed exists for fixtures needing fields
        # create_comment() cannot produce — `quotedFileContent` above all, the only way to
        # exercise quote anchoring.
        self._comments = {(fid, raw["id"]): raw
                          for fid, raws in (comments or {}).items() for raw in raws}
        self._seq = 0
        self._documents = documents or {}
        self._spreadsheets = spreadsheets or {}
        self._values = values or {}
        self._presentations = presentations or {}
        self._exports = exports or {}
        # Raw bytes of UPLOADED files, keyed by id alone - unlike `_exports`, which is keyed by
        # (id, mime) because a Google-native file converts into several formats. An uploaded
        # file has exactly one representation: itself.
        self._media = media or {}
        self._permissions = {fid: list(ps) for fid, ps in (permissions or {}).items()}
        # Pending access requests, keyed by file. Seeded rather than creatable, because the API
        # has no `create` either - a proposal is made from Drive's UI by somebody who does NOT
        # have access, and there is no endpoint on this side that can produce one.
        self._proposals = {fid: list(ps) for fid, ps in (access_proposals or {}).items()}
        # Two halves, because Google splits them across two APIs: which labels are ON a file
        # (Drive v3, opaque ids) and what a label IS (the Drive Labels API, names).
        self._file_labels = {fid: list(ls) for fid, ls in (file_labels or {}).items()}
        self._label_definitions = dict(label_definitions or {})
        self._writes = []

    def get_file_metadata(self, file_id: str) -> dict:
        try:
            return self._files[file_id]
        except KeyError:
            raise exc.NotFoundError(f"file '{file_id}' not found") from None

    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None:
        raise exc.UnsupportedOperation("accept_suggestion is not supported by FakeBackend")

    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None:
        raise exc.UnsupportedOperation("cell-anchored comments are not creatable")

    def _new_id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def _require(self, file_id, comment_id):
        c = self._comments.get((file_id, comment_id))
        if c is None:
            raise exc.NotFoundError(f"comment '{comment_id}' not found")
        return c

    def list_comments(self, file_id, include_deleted=False, start_modified_time=None):
        out = [c for (f, _), c in self._comments.items() if f == file_id]
        if not include_deleted:
            out = [c for c in out if not c.get("deleted")]
        if start_modified_time:
            out = [c for c in out if c.get("modifiedTime", "") >= start_modified_time]
        return [copy.deepcopy(c) for c in out]

    def get_comment(self, file_id, comment_id, include_deleted=False):
        raw = self._require(file_id, comment_id)
        if raw.get("deleted") and not include_deleted:
            # As Drive does. Returning it regardless was the more forgiving behaviour and it
            # hid a real bug for as long as this fake existed.
            raise exc.NotFoundError(f"comment '{comment_id}' not found")
        return copy.deepcopy(raw)

    def create_comment(self, file_id, content):
        self.get_file_metadata(file_id)  # validates the file exists (raises NotFoundError)
        cid = self._new_id("c")
        c = {"id": cid, "content": content, "htmlContent": content, "deleted": False,
             "author": {"displayName": "Test User", "me": True},
             "createdTime": "2026-01-01T00:00:00Z", "modifiedTime": "2026-01-01T00:00:00Z",
             "replies": []}
        self._comments[(file_id, cid)] = c
        return copy.deepcopy(c)

    def create_reply(self, file_id, comment_id, content=None, action=None):
        c = self._require(file_id, comment_id)
        rid = self._new_id("r")
        r = {"id": rid, "content": content or "", "htmlContent": content or "",
             "deleted": False, "author": {"displayName": "Test User", "me": True},
             "createdTime": "2026-01-01T00:00:00Z"}
        if action:
            r["action"] = action
            c["resolved"] = (action == "resolve")   # flip parent (MEASURED)
        c["replies"].append(r)
        return copy.deepcopy(r)

    def update_comment(self, file_id, comment_id, content):
        c = self._require(file_id, comment_id)
        c["content"] = content; c["htmlContent"] = content
        return copy.deepcopy(c)

    def update_reply(self, file_id, comment_id, reply_id, content):
        c = self._require(file_id, comment_id)
        for r in c["replies"]:
            if r["id"] == reply_id:
                r["content"] = content; r["htmlContent"] = content
                return copy.deepcopy(r)
        raise exc.NotFoundError(f"reply '{reply_id}' not found")

    def delete_comment(self, file_id, comment_id):
        c = self._require(file_id, comment_id)
        c["deleted"] = True
        c.pop("content", None); c.pop("htmlContent", None); c.pop("author", None)  # strip (MEASURED)
        for r in c["replies"]:
            r["deleted"] = True
            r.pop("content", None); r.pop("htmlContent", None); r.pop("author", None)

    def delete_reply(self, file_id, comment_id, reply_id):
        c = self._require(file_id, comment_id)
        for r in c["replies"]:
            if r["id"] == reply_id:
                r["deleted"] = True
                r.pop("content", None); r.pop("htmlContent", None); r.pop("author", None)
                return
        raise exc.NotFoundError(f"reply '{reply_id}' not found")

    def _fixture(self, store, key, kind):
        if key not in store:
            raise exc.NotFoundError(f"{kind} '{key}' not found")
        return copy.deepcopy(store[key])

    def download_file(self, file_id):
        if file_id in self._media:
            return self._media[file_id]
        raise exc.NotFoundError(f"no uploaded bytes for {file_id}")

    def export_file(self, file_id, mime_type):
        """A seeded export if there is one, otherwise render what this fake holds.

        Seeded fixtures still win, because the tests that assert exact export bytes depend on
        them. The fallback exists because a fake that cannot export a file it just created
        diverges from Google in a way that hides bugs: every walk-the-whole-surface exercise
        hit a NotFoundError that the real API would never produce, so export was the one
        operation nothing end-to-end could cover.

        The format resolution has already happened by the time a mime type reaches here, so
        rendering it approximately does not paper over a resolution mistake.
        """
        seeded = self._exports.get((file_id, mime_type))
        if seeded is not None:
            return seeded
        self.get_file_metadata(file_id)              # NotFoundError for an unknown file
        if file_id in self._spreadsheets:
            rows = [v for (fid, _), v in self._values.items() if fid == file_id]
            flat = rows[0] if rows else []
            return "\n".join(",".join(str(c) for c in row) for row in flat).encode()
        if file_id in self._documents:
            from . import _content
            return _content.doc_text(self._documents[file_id]).encode()
        if file_id in self._presentations:
            from . import _content
            return "\n".join(_content.slide_text(sl) for sl in
                              self._presentations[file_id].get("slides", [])).encode()
        # A file this fake holds no content for. Fall through to the fixture lookup so it
        # raises exactly as it did before: "nothing to export" and "no fixture seeded" are
        # the same answer, and a test that asserts the error still gets one.
        return self._fixture(self._exports, (file_id, mime_type), "export")

    def list_permissions(self, file_id):
        self.get_file_metadata(file_id)              # validates the file exists
        return [copy.deepcopy(p) for p in self._permissions.get(file_id, [])]

    def create_file(self, name, mime_type, *, parent_id=None, content=None,
                    content_mime_type=None):
        self._seq += 1
        file_id = f"new{self._seq}"
        meta = {"id": file_id, "name": name, "mimeType": mime_type,
                "webViewLink": f"https://x/d/{file_id}"}
        if parent_id:
            meta["parents"] = [parent_id]
        if content is not None:
            # Records what was uploaded so a test can assert conversion happened, which is the
            # only interesting part of create-with-content.
            meta["_uploaded"] = {"bytes": len(content), "as": content_mime_type}
        self._files[file_id] = meta
        # Seed an empty body too. A created file that cannot then be opened or written to is
        # not a useful double — the whole point of creating one is to use it next.
        if mime_type.endswith(".document"):
            self._documents[file_id] = {"body": {"content": []}}
        elif mime_type.endswith(".spreadsheet"):
            self._spreadsheets[file_id] = {"sheets": [
                {"properties": {"sheetId": 0, "title": "Sheet1"}}]}
        elif mime_type.endswith(".presentation"):
            # One slide with one text shape, because that is what Google creates. An empty
            # deck made every shape-addressed operation unreachable in the fake - so
            # `insert_slide_text` could not be exercised without seeding a fixture by hand,
            # and a demo or test that walks a freshly created deck hit a wall the real API
            # does not have.
            self._presentations[file_id] = {"slides": [{
                "objectId": f"slide_{file_id}",
                "pageElements": [{"objectId": f"shape_{file_id}",
                                  "shape": {"text": {"textElements": []}}}]}]}
        return copy.deepcopy(meta)

    def update_file_metadata(self, file_id, *, name=None, add_parent=None,
                             remove_parent=None):
        meta = self._files[file_id] if file_id in self._files else self.get_file_metadata(file_id)
        if name is not None:
            meta["name"] = name
        parents = list(meta.get("parents", []))
        if remove_parent and remove_parent in parents:
            parents.remove(remove_parent)
        if add_parent and add_parent not in parents:
            parents.append(add_parent)
        if parents or "parents" in meta:
            meta["parents"] = parents
        return copy.deepcopy(meta)

    def trash_file(self, file_id, *, trashed=True):
        meta = self._files[file_id] if file_id in self._files else self.get_file_metadata(file_id)
        meta["trashed"] = trashed
        return copy.deepcopy({"id": file_id, "name": meta.get("name"), "trashed": trashed})

    def create_permission(self, file_id, *, email, role, permission_type="user", notify=True):
        self.get_file_metadata(file_id)                # raises NotFoundError
        self._seq += 1
        perm = {"id": f"perm{self._seq}", "type": permission_type, "role": role}
        if email is not None:
            perm["emailAddress"] = email
        self._permissions.setdefault(file_id, []).append(perm)
        return copy.deepcopy(perm)

    def _find_permission(self, file_id, permission_id):
        self.get_file_metadata(file_id)                # raises NotFoundError
        for perm in self._permissions.get(file_id, []):
            if perm["id"] == permission_id:
                return perm
        raise exc.NotFoundError(
            f"no permission {permission_id!r} on {file_id!r}")

    def update_permission(self, file_id, permission_id, *, role):
        perm = self._find_permission(file_id, permission_id)
        perm["role"] = role
        return copy.deepcopy(perm)

    def delete_permission(self, file_id, permission_id):
        perm = self._find_permission(file_id, permission_id)
        self._permissions[file_id].remove(perm)

    def list_access_proposals(self, file_id):
        self.get_file_metadata(file_id)              # raises NotFoundError
        return [copy.deepcopy(p) for p in self._proposals.get(file_id, [])]

    def list_file_labels(self, file_id):
        self.get_file_metadata(file_id)              # raises NotFoundError
        return [copy.deepcopy(label) for label in self._file_labels.get(file_id, [])]

    def get_label_definition(self, label_id):
        try:
            return copy.deepcopy(self._label_definitions[label_id])
        except KeyError:
            raise exc.NotFoundError(f"no label definition for {label_id!r}") from None

    def resolve_access_proposal(self, file_id, proposal_id, *, action,
                                roles=None, view=None, notify=True):
        self.get_file_metadata(file_id)              # raises NotFoundError
        for proposal in self._proposals.get(file_id, []):
            if proposal.get("proposalId") == proposal_id:
                break
        else:
            raise exc.NotFoundError(
                f"no access proposal {proposal_id!r} on {file_id!r}")
        self._proposals[file_id].remove(proposal)
        # ACCEPT grants a permission for real, so the fake grants one too. A fake where
        # accepting changed nothing observable would let a test assert "resolve worked" while
        # the thing resolve EXISTS to do - handing somebody access - went unexercised.
        if action == "ACCEPT":
            self._seq += 1
            perm = {"id": f"perm{self._seq}", "type": "user",
                    "role": (roles or ["reader"])[0],
                    "emailAddress": proposal.get("requesterEmailAddress")}
            self._permissions.setdefault(file_id, []).append(perm)

    def copy_file(self, file_id, *, name=None, parent_id=None):
        source = self.get_file_metadata(file_id)       # raises NotFoundError
        self._seq += 1
        new_id = f"copy{self._seq}"
        meta = {"id": new_id, "name": name or f"Copy of {source.get('name', '')}",
                "mimeType": source["mimeType"], "webViewLink": f"https://x/d/{new_id}"}
        if parent_id:
            meta["parents"] = [parent_id]
        self._files[new_id] = meta
        return copy.deepcopy(meta)

    def search_files(self, query, *, page_size=25, order_by=None, page_token=None):
        """Substring-matches `name contains '...'` / `fullText contains '...'` clauses and
        honours `mimeType = '...'`; anything else matches everything.

        Deliberately not a Drive query engine — that would be a second implementation of
        Google's parser, and the interesting bugs live in `ApiBackend`'s wiring (which is
        why the real query string is asserted in tests/test_apibackend_contract.py). This
        exists so the collection's paging, ordering and wrapping are testable offline.
        """
        matched = [f for f in self._files.values() if self._matches(f, query)]
        matched.sort(key=lambda f: f.get("modifiedTime", ""), reverse=True)
        start = int(page_token) if page_token else 0
        page = matched[start:start + page_size]
        out: dict = {"files": [copy.deepcopy(f) for f in page]}
        if start + page_size < len(matched):
            out["nextPageToken"] = str(start + page_size)
        return out

    @staticmethod
    def _matches(meta, query):
        import re as _re
        for term in _re.findall(r"(?:name|fullText)\s+contains\s+'([^']*)'", query):
            if term.lower() not in meta.get("name", "").lower():
                return False
        for mime in _re.findall(r"mimeType\s*=\s*'([^']*)'", query):
            if meta.get("mimeType") != mime:
                return False
        if "trashed = false" in query and meta.get("trashed"):
            return False
        if "trashed = true" in query and not meta.get("trashed"):
            return False
        return True

    def get_document(self, file_id, suggestions_view_mode=None):
        key = (file_id, suggestions_view_mode)
        if key in self._documents:
            return copy.deepcopy(self._documents[key])
        return self._fixture(self._documents, file_id, "document")

    def get_spreadsheet(self, file_id):
        return self._fixture(self._spreadsheets, file_id, "spreadsheet")

    def get_values(self, file_id, a1_range):
        return copy.deepcopy(self._values.get((file_id, a1_range), []))

    def get_presentation(self, file_id):
        return self._fixture(self._presentations, file_id, "presentation")

    def _replace_all_text_reply(self, file_id, requests):
        """Simulate `replaceAllText` well enough to exercise the occurrence count.

        The count drives real guidance — a model told "0 occurrences" should re-read rather
        than retry — and with the fake always returning 0 that path could not be tested.
        """
        replies: list[JsonDict] = []
        for request in requests:
            spec = request.get("replaceAllText")
            if spec is None:
                replies.append({})
                continue
            find = spec.get("containsText", {}).get("text", "")
            body = self._documents.get(file_id, {})
            from . import _content
            text = _content.doc_text(body) if body else ""
            if not spec.get("containsText", {}).get("matchCase", True):
                count = text.lower().count(find.lower())
            else:
                count = text.count(find)
            replies.append({"replaceAllText": {"occurrencesChanged": count}})
        return {"replies": replies}

    def docs_batch_update(self, file_id, requests):
        self._writes.append((file_id, "docs", requests))
        return self._replace_all_text_reply(file_id, requests)

    def sheets_values_update(self, file_id, a1_range, values, value_input_option="RAW"):
        self._writes.append((file_id, "sheets_values_update", a1_range, values, value_input_option))
        self._values[(file_id, a1_range)] = values
        return {}

    def sheets_values_append(self, file_id, a1_range, values, value_input_option="RAW"):
        self._writes.append((file_id, "sheets_values_append", a1_range, values, value_input_option))
        self._values[(file_id, a1_range)] = self._values.get((file_id, a1_range), []) + values
        return {}

    def sheets_values_clear(self, file_id, a1_range):
        self._writes.append((file_id, "sheets_values_clear", a1_range))
        self._values.pop((file_id, a1_range), None)
        return {}

    def sheets_batch_update(self, file_id, requests):
        self._writes.append((file_id, "sheets", requests))
        return {}

    def slides_batch_update(self, file_id, requests):
        self._writes.append((file_id, "slides", requests))
        return {}


class ApiBackend:
    """Real backend over google-api-python-client. `services` is a ServiceRegistry (Task 4)."""

    def __init__(self, services):
        self._services = services

    def get_file_metadata(self, file_id: str) -> dict:
        # `trashed` is requested for the allowlist preview: a trashed file still RESOLVES by id,
        # so without this field a dead allowlist entry is indistinguishable from a live one and
        # nothing in the system ever notices the policy stopped covering anything.
        return _errors.call(
            self._services.drive.files()
            .get(fileId=file_id, fields="id,name,mimeType,webViewLink,size,trashed",
                 supportsAllDrives=True).execute)

    def accept_suggestion(self, file_id: str, suggestion_id: str) -> None:
        raise exc.UnsupportedOperation(
            "The Google Docs API has no accept/reject-suggestion endpoint "
            "(verified by probe). A PlaywrightBackend is required."
        )

    def create_cell_anchored_comment(self, file_id: str, cell: str, text: str) -> None:
        raise exc.UnsupportedOperation(
            "Cell-anchored comments cannot be created via the API; use a file-level "
            "comment with a #range deep-link instead."
        )

    _CF = "id,anchor,content,htmlContent,resolved,deleted,createdTime,modifiedTime," \
          "author(displayName,emailAddress,me,photoLink),quotedFileContent," \
          "replies(id,content,htmlContent,action,deleted,createdTime,modifiedTime," \
          "author(displayName,emailAddress,me,photoLink))"
    _RF = "id,content,htmlContent,action,deleted,createdTime,modifiedTime," \
          "author(displayName,emailAddress,me,photoLink)"

    def _comments(self):
        return self._services.drive.comments()

    def list_comments(self, file_id, include_deleted=False, start_modified_time=None):
        out, page = [], None
        while True:
            kw = {"fileId": file_id, "includeDeleted": include_deleted,
                  "fields": f"comments({self._CF}),nextPageToken", "pageSize": 100}
            if start_modified_time:
                kw["startModifiedTime"] = start_modified_time
            if page:
                kw["pageToken"] = page
            resp = _errors.call(self._comments().list(**kw).execute)
            out.extend(resp.get("comments", []))
            page = resp.get("nextPageToken")
            if not page:
                return out

    def get_comment(self, file_id, comment_id, include_deleted=False):
        # Drive 404s a soft-deleted comment unless includeDeleted is set, which made a
        # SUCCESSFUL delete report "Comment not found": the tool deleted the comment and then
        # re-fetched it to show what Drive now held. Found by the demonstration against real
        # Google; every unit test passed, because the fake returned deleted comments happily.
        return _errors.call(self._comments().get(
            fileId=file_id, commentId=comment_id, fields=self._CF,
            includeDeleted=include_deleted).execute)

    def create_comment(self, file_id, content):
        return _errors.call(self._comments().create(
            fileId=file_id, body={"content": content}, fields=self._CF).execute,
            idempotent=False)

    def create_reply(self, file_id, comment_id, content=None, action=None):
        body = {}
        if content is not None:
            body["content"] = content
        if action:
            body["action"] = action
        return _errors.call(self._services.drive.replies().create(
            fileId=file_id, commentId=comment_id, body=body, fields=self._RF).execute,
            idempotent=False)

    def update_comment(self, file_id, comment_id, content):
        return _errors.call(self._comments().update(
            fileId=file_id, commentId=comment_id, body={"content": content}, fields=self._CF).execute,
            idempotent=False)

    def update_reply(self, file_id, comment_id, reply_id, content):
        return _errors.call(self._services.drive.replies().update(
            fileId=file_id, commentId=comment_id, replyId=reply_id,
            body={"content": content}, fields=self._RF).execute,
            idempotent=False)

    def delete_comment(self, file_id, comment_id):
        _errors.call(self._comments().delete(fileId=file_id, commentId=comment_id).execute,
                     idempotent=False)

    def delete_reply(self, file_id, comment_id, reply_id):
        _errors.call(self._services.drive.replies().delete(
            fileId=file_id, commentId=comment_id, replyId=reply_id).execute,
            idempotent=False)

    def export_file(self, file_id, mime_type):
        return _errors.call(self._services.drive.files()
                            .export(fileId=file_id, mimeType=mime_type).execute)

    def download_file(self, file_id):
        """Raw bytes of an UPLOADED file — `alt=media`, no conversion.

        Distinct from `export_file`, which is Drive's Google-native conversion and refuses a
        file it did not create. The README's API table has listed `drive.files.get(alt=media)`
        since the download tool shipped; the code did not exist until v0.29.0, so a .docx could
        not be fetched at all.
        """
        return _errors.call(self._services.drive.files()
                            .get_media(fileId=file_id, supportsAllDrives=True).execute)

    # emailAddress and displayName are omitted from the default response, and they are the
    # entire point of this call.
    _PERM_FIELDS = ("permissions(id,type,role,emailAddress,displayName,domain,deleted,"
                    "pendingOwner),nextPageToken")

    def list_permissions(self, file_id):
        out, page = [], None
        while True:
            kw = {"fileId": file_id, "fields": self._PERM_FIELDS, "pageSize": 100,
                  # A file on a shared drive otherwise reports no permissions at all.
                  "supportsAllDrives": True}
            if page:
                kw["pageToken"] = page
            resp = _errors.call(self._services.drive.permissions().list(**kw).execute)
            out.extend(resp.get("permissions", []))
            page = resp.get("nextPageToken")
            if not page:
                return out

    # Requested fields are explicit: the default response omits webViewLink, and asking for
    # everything makes a search of 100 files needlessly large.
    _SEARCH_FIELDS = "nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime)"

    _NEW_FILE_FIELDS = "id, name, mimeType, webViewLink, parents"

    def create_file(self, name, mime_type, *, parent_id=None, content=None,
                    content_mime_type=None):
        body = {"name": name, "mimeType": mime_type}
        if parent_id:
            body["parents"] = [parent_id]
        kw = {"body": body, "fields": self._NEW_FILE_FIELDS, "supportsAllDrives": True}
        if content is not None:
            from googleapiclient.http import MediaInMemoryUpload
            # `body.mimeType` is the *target* and the upload's is the *source*: Drive converts
            # between them, which is how text/markdown becomes a real Doc rather than a file
            # containing markdown. See experiments/export-formats/RESULTS.md finding 6.
            kw["media_body"] = MediaInMemoryUpload(
                content, mimetype=content_mime_type or "text/plain", resumable=False)
        return _errors.call(self._services.drive.files().create(**kw).execute,
                            idempotent=False)

    def copy_file(self, file_id, *, name=None, parent_id=None):
        body = {}
        if name:
            body["name"] = name
        if parent_id:
            body["parents"] = [parent_id]
        return _errors.call(
            self._services.drive.files().copy(
                fileId=file_id, body=body, fields=self._NEW_FILE_FIELDS,
                supportsAllDrives=True).execute,
            idempotent=False)

    def update_file_metadata(self, file_id, *, name=None, add_parent=None,
                             remove_parent=None):
        # Metadata only, exactly as Google's and Claude's `update_file` are: renaming and
        # moving. Editing a file's CONTENT is a different API per type and is what
        # docs_batch_update / sheets_values_update / slides_batch_update are for.
        #
        # Drive moves a file by editing its parent list rather than by taking a destination,
        # so a move is addParents plus removeParents. The caller supplies the parent to
        # remove because a file can legitimately have more than one, and guessing which to
        # detach is not ours to do.
        body = {}
        if name is not None:
            body["name"] = name
        kw = {"fileId": file_id, "body": body, "fields": self._NEW_FILE_FIELDS,
              "supportsAllDrives": True}
        if add_parent:
            kw["addParents"] = add_parent
        if remove_parent:
            kw["removeParents"] = remove_parent
        return _errors.call(self._services.drive.files().update(**kw).execute,
                            idempotent=False)

    def trash_file(self, file_id, *, trashed=True):
        # Trash, not delete. Drive keeps a trashed file for 30 days and `trashed=False`
        # restores it, so this is reversible by the user without an administrator. There is
        # deliberately no wrapper for files().delete(), which is not.
        return _errors.call(
            self._services.drive.files().update(
                fileId=file_id, body={"trashed": trashed},
                fields="id, name, trashed", supportsAllDrives=True).execute,
            idempotent=False)

    def create_permission(self, file_id, *, email, role, permission_type="user", notify=True):
        # The one call in this backend that can move data OUT of the organisation, so it is
        # gated by its own capability, off by default, and file-scoped. See policy._GATES.
        #
        # sendNotificationEmail defaults to True on purpose: a share the recipient is told
        # about is a share somebody can notice and question. Silent grants are how access
        # accumulates unobserved.
        body = {"role": role, "type": permission_type}
        if email is not None:
            body["emailAddress"] = email
        return _errors.call(
            self._services.drive.permissions().create(
                fileId=file_id, body=body, sendNotificationEmail=notify,
                fields="id, type, role, emailAddress, displayName",
                supportsAllDrives=True).execute,
            idempotent=False)

    def update_permission(self, file_id, permission_id, *, role):
        # Downgrading (writer -> reader) is often what is actually wanted, and it keeps the
        # person's access to work they may be mid-way through rather than cutting it dead.
        return _errors.call(
            self._services.drive.permissions().update(
                fileId=file_id, permissionId=permission_id, body={"role": role},
                fields="id, type, role, emailAddress, displayName",
                supportsAllDrives=True).execute,
            idempotent=False)

    def list_access_proposals(self, file_id):
        # "Who has asked for access to this file?" - the OWNER's side of Drive's request-access
        # flow. Note there is no `create`: this API cannot ask for access, only answer.
        #
        # Paginated like every other list here. No `fields` mask: unlike permissions, the
        # default AccessProposal response already carries the fields that matter
        # (requesterEmailAddress, requestMessage, rolesAndViews), and the resource is small.
        out, page = [], None
        while True:
            kw = {"fileId": file_id, "pageSize": 100}
            if page:
                kw["pageToken"] = page
            resp = _errors.call(
                self._services.drive.accessproposals().list(**kw).execute)
            out.extend(resp.get("accessProposals", []))
            page = resp.get("nextPageToken")
            if not page:
                return out

    def list_file_labels(self, file_id):
        # Which labels are applied to this file - as OPAQUE IDS. Drive v3 will not tell you what
        # a label is called; `get_label_definition` is the other half. Note `maxResults`, not
        # `pageSize`: this endpoint spells its page size differently from every other list here.
        out, page = [], None
        while True:
            kw = {"fileId": file_id, "maxResults": 100}
            if page:
                kw["pageToken"] = page
            resp = _errors.call(self._services.drive.files().listLabels(**kw).execute)
            out.extend(resp.get("labels", []))
            page = resp.get("nextPageToken")
            if not page:
                return out

    def get_label_definition(self, label_id):
        # A DIFFERENT API - `drivelabels.googleapis.com`, its own scope, its own enablement -
        # and the only thing that can turn a label id into "Confidential".
        #
        # `LABEL_VIEW_FULL` is required: the basic view omits `fields`, and without those the
        # response cannot name a field or resolve a selection choice, which is most of the point.
        name = label_id if str(label_id).startswith("labels/") else f"labels/{label_id}"
        return _errors.call(
            self._services.drivelabels.labels().get(
                name=name, view="LABEL_VIEW_FULL").execute)

    def resolve_access_proposal(self, file_id, proposal_id, *, action,
                                roles=None, view=None, notify=True):
        # ACCEPT GRANTS A PERMISSION. However administrative "resolve a request" sounds, this
        # is `create_permission` wearing different clothes - the same outbound authority, the
        # same irreversibility once a copy is taken - which is why policy._GATES puts it under
        # `file.share` rather than inventing a gentler capability for it.
        #
        # Google's own scopes agree, and that is the empirical version of the argument: `list`
        # and `get` accept the `.readonly` scopes; `resolve` demands `drive` or `drive.file`.
        body = {"action": action, "sendNotification": notify}
        if roles:
            body["role"] = roles
        if view:
            body["view"] = view
        _errors.call(
            self._services.drive.accessproposals().resolve(
                fileId=file_id, proposalId=proposal_id, body=body).execute,
            idempotent=False)

    def delete_permission(self, file_id, permission_id):
        # Revocation. Note what it does and does not undo: the GRANT is gone, so the person
        # loses access from now on - but a copy they already took is not recalled, and Drive
        # sends no notification. `PROVENANCE.md` rates sharing irreversible *in effect* for
        # exactly that reason, and this narrows the half that was ours rather than Google's.
        _errors.call(
            self._services.drive.permissions().delete(
                fileId=file_id, permissionId=permission_id,
                supportsAllDrives=True).execute,
            idempotent=False)

    def search_files(self, query, *, page_size=25, order_by=None, page_token=None):
        kw = {"q": query, "pageSize": page_size, "fields": self._SEARCH_FIELDS,
              # Shared drives are where collaborative review actually happens; omitting
              # these two silently hides every file that lives in one.
              "includeItemsFromAllDrives": True, "supportsAllDrives": True,
              "spaces": "drive"}
        if order_by:
            kw["orderBy"] = order_by
        if page_token:
            kw["pageToken"] = page_token
        return _errors.call(self._services.drive.files().list(**kw).execute)

    def get_document(self, file_id, suggestions_view_mode=None):
        # `includeTabsContent=True` because a Google Doc can have TABS, and without it the
        # response carries the FIRST TAB ONLY in the legacy top-level `body`, with no `tabs` key
        # and nothing to say the rest exists. Measured: see `experiments/docs-tabs/`.
        #
        # It also MOVES the content: with the flag, top-level `body` comes back EMPTY and
        # everything lives under `tabs[].documentTab.body` - even for a single-tab document. So
        # this line and `_content.doc_tab_bodies` are one change; adding the flag while any
        # consumer still read `body` would turn a silent truncation into a silent blank.
        kw = {"documentId": file_id, "includeTabsContent": True}
        if suggestions_view_mode:
            kw["suggestionsViewMode"] = suggestions_view_mode
        return _errors.call(self._services.docs.documents().get(**kw).execute)

    def get_spreadsheet(self, file_id):
        return _errors.call(self._services.sheets.spreadsheets()
                            .get(spreadsheetId=file_id,
                                 fields="sheets(properties(sheetId,title))").execute)

    def get_values(self, file_id, a1_range):
        resp = _errors.call(self._services.sheets.spreadsheets().values()
                            .get(spreadsheetId=file_id, range=a1_range).execute)
        return resp.get("values", [])

    def get_presentation(self, file_id):
        return _errors.call(self._services.slides.presentations().get(presentationId=file_id).execute)

    def docs_batch_update(self, file_id, requests):
        return _errors.call(self._services.docs.documents().batchUpdate(
            documentId=file_id, body={"requests": requests}).execute,
            idempotent=False)

    def sheets_values_update(self, file_id, a1_range, values, value_input_option="RAW"):
        return _errors.call(self._services.sheets.spreadsheets().values().update(
            spreadsheetId=file_id, range=a1_range, valueInputOption=value_input_option,
            body={"values": values}).execute,
            idempotent=False)

    def sheets_values_append(self, file_id, a1_range, values, value_input_option="RAW"):
        # append is NOT idempotent: a retried request would add the rows twice. Never retry on 5xx.
        return _errors.call(self._services.sheets.spreadsheets().values().append(
            spreadsheetId=file_id, range=a1_range, valueInputOption=value_input_option,
            insertDataOption="INSERT_ROWS", body={"values": values}).execute,
            idempotent=False)

    def sheets_values_clear(self, file_id, a1_range):
        return _errors.call(self._services.sheets.spreadsheets().values().clear(
            spreadsheetId=file_id, range=a1_range, body={}).execute,
            idempotent=False)

    def sheets_batch_update(self, file_id, requests):
        return _errors.call(self._services.sheets.spreadsheets().batchUpdate(
            spreadsheetId=file_id, body={"requests": requests}).execute,
            idempotent=False)

    def slides_batch_update(self, file_id, requests):
        return _errors.call(self._services.slides.presentations().batchUpdate(
            presentationId=file_id, body={"requests": requests}).execute,
            idempotent=False)
