import pytest

from csa_google_workspace import Workspace
from csa_google_workspace import exceptions as exc
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC, "webViewLink": "https://x/document/d/d/edit"}}


def doc(read_only=False, document=None):
    b = FakeBackend(META, documents={"d": document or {"body": {"content": [{"endIndex": 10}]}}})
    return Workspace(b, read_only=read_only).open("d"), b


def test_replace_text_builds_replaceAllText():
    d, b = doc()
    result = d.replace_text("old", "new")
    assert b._writes == [("d", "docs", [{"replaceAllText": {
        "containsText": {"text": "old", "matchCase": True}, "replaceText": "new"}}])]
    assert isinstance(result, int) and result == 0  # FakeBackend returns {} -> defaults to 0


def test_replace_text_match_case_false():
    d, b = doc()
    d.replace_text("old", "new", match_case=False)
    assert b._writes == [("d", "docs", [{"replaceAllText": {
        "containsText": {"text": "old", "matchCase": False}, "replaceText": "new"}}])]


def test_insert_text_builds_insertText_at_index():
    d, b = doc()
    d.insert_text("hi", at=5)
    assert b._writes == [("d", "docs", [{"insertText": {"location": {"index": 5}, "text": "hi"}}])]


def test_append_text_inserts_before_final_newline():
    d, b = doc(document={"body": {"content": [{"endIndex": 42}]}})
    d.append_text("tail")
    assert b._writes == [("d", "docs", [{"insertText": {"location": {"index": 41}, "text": "tail"}}])]


def test_delete_range_goes_through_its_own_backend_method_not_the_batch():
    """**Rewritten in v0.36.0, and the reversal is the point.**

    This used to assert `delete_range` built a `deleteContentRange` request through
    `docs_batch_update`. It no longer does, deliberately: `policy._GATES` gates at the `Backend`
    seam, and the generic batch method **cannot tell a delete from an edit**. A delete riding on
    it was therefore ungatable apart from editing, so `content.delete` could not exist.

    So the shape assertion moved to `tests/test_apibackend_contract.py`, where the actual request
    body is checked against a stub service; what belongs here is that the *right seam* is used.
    """
    d, b = doc()
    d.delete_range(3, 7)
    assert b._writes == [("docs_delete_range", "d", 3, 7, None)]


def test_delete_range_can_target_a_tab():
    """Index-addressed Docs requests apply to the FIRST tab unless given a `tabId` - measured in
    experiments/docs-tabs/. Without this argument, deleting a range in tab 2 silently edits
    tab 1, which is the worst available outcome for a delete."""
    d, b = doc()
    d.delete_range(3, 7, tab_id="t.abc")
    assert b._writes == [("docs_delete_range", "d", 3, 7, "t.abc")]


def test_writes_blocked_when_read_only():
    d, _ = doc(read_only=True)
    for call in (lambda: d.replace_text("a", "b"), lambda: d.insert_text("x", 1),
                 lambda: d.append_text("x"), lambda: d.delete_range(1, 2),
                 lambda: d.batch_update([{}])):
        with pytest.raises(exc.ReadOnlyError):
            call()


def test_replace_text_handles_empty_replies_list():
    """Backend returns empty replies list instead of missing key or default."""
    class FakeBackendEmptyReplies(FakeBackend):
        def docs_batch_update(self, file_id, requests):
            self._writes.append((file_id, "docs", requests))
            return {"replies": []}

    b = FakeBackendEmptyReplies(META, documents={"d": {"body": {"content": [{"endIndex": 10}]}}})
    d = Workspace(b).open("d")
    result = d.replace_text("old", "new")
    assert result == 0  # Should fall back to 0, not crash on IndexError
