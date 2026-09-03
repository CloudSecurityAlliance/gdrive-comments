"""`append_text` appended to the START of every Google Doc, and `insert_text` could not name a tab.

Two defects on the same seam (#391, #390), and they are one file because the cause is one thing:
**a response shape that only one function understood.**

`ApiBackend.get_document` passes `includeTabsContent=True`, which — measured 2026-08-31 — moves
the content into `tabs[].documentTab.body` and leaves the top-level `body` **EMPTY, even for a
single-tab document**. `_content.doc_tab_bodies` was written for exactly that and says so in its
docstring. `Doc.append_text` then read `document["body"]["content"]` itself, got `[]`, fell through
a default of index 1, and **appended to the top of the document**. Confirmed against live Google:

    before: 'FIRST LINE.\nSECOND LINE.\n\n'
    after : '\n>>> APPENDED <<<FIRST LINE.\nSECOND LINE.\n\n'

## Why the whole suite was green

`FakeBackend` fixtures use the legacy `{"body": {"content": […]}}` shape — the one the real API
stopped returning once the flag went on. So every `append_text` test exercised a shape that no
longer occurs, and agreed with itself.

`CLAUDE.md` invariant 4 names this exact blind spot: *"Behavior only `ApiBackend` has needs a
stub-service test, not a `FakeBackend` test… it is exactly how `Workspace.open()` once leaked a raw
`HttpError` past a fully green suite."* Same seam, same outcome. So the tests below drive the
**tabs shape** deliberately, which is the shape that matters, and one of them asserts the *index*
rather than merely that the text arrived.

The live suite missed it too, and that is worth recording: `test_content_write_live` asserts
`"written by the library" in as_text()`, which is true whether the text lands at the start or the
end. A containment check cannot see position.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace._content import doc_tab_end_indices
from csa_google_workspace.backend import FakeBackend

DOC = "application/vnd.google-apps.document"
META = {"d": {"id": "d", "name": "D", "mimeType": DOC}}


def tabs_shape(*tabs) -> dict:
    """What `documents.get(includeTabsContent=True)` really returns: an EMPTY top-level body."""
    return {"body": {}, "tabs": list(tabs)}


def tab(tab_id: str, end: int, title: str | None = None, children: list | None = None) -> dict:
    return {"tabProperties": {"tabId": tab_id, "title": title or tab_id},
            "documentTab": {"body": {"content": [{"endIndex": end}]}},
            "childTabs": children or []}


def doc(document):
    b = FakeBackend(META, documents={"d": document})
    return Workspace(b).open("d"), b


class TestTheEndIsFoundInEitherShape:
    def test_the_tabs_shape_is_read_from_the_tab_body(self):
        """The regression. The top-level body is empty, so a reader of it sees nothing."""
        assert doc_tab_end_indices(tabs_shape(tab("t.0", 99))) == [("t.0", 99)]

    def test_the_legacy_shape_still_works(self):
        """Kept because every FakeBackend fixture uses it, and so does any embedder holding a
        response it fetched without the flag."""
        assert doc_tab_end_indices({"body": {"content": [{"endIndex": 42}]}}) == [(None, 42)]

    def test_every_tab_is_reported_depth_first(self):
        got = doc_tab_end_indices(tabs_shape(
            tab("t.0", 10, children=[tab("t.0.1", 20)]), tab("t.1", 30)))
        assert got == [("t.0", 10), ("t.0.1", 20), ("t.1", 30)]

    def test_a_genuinely_empty_body_is_index_1_not_an_error(self):
        """An empty document starts at 1. This is the honest answer, unlike the old `else 2`
        which was reached when the body could not be FOUND."""
        assert doc_tab_end_indices(tabs_shape(tab("t.0", 0)))  # sanity: a tab is present
        assert doc_tab_end_indices({"body": {"content": []}}) == [(None, 1)]

    def test_a_response_with_no_body_at_all_reports_NOTHING(self):
        """The distinction that makes the fix a fix: "empty" and "unreadable" must not be the
        same value, because the caller refuses on one and proceeds on the other."""
        assert doc_tab_end_indices({}) == []
        assert doc_tab_end_indices({"tabs": []}) == []


class TestAppendGoesToTheEnd:
    def test_it_appends_to_the_end_of_the_TAB_body(self):
        """#391 itself: with the tabs shape this used to compute index 1."""
        d, b = doc(tabs_shape(tab("t.0", 500)))
        d.append_text("tail")
        (_, _, requests), = b._writes
        assert requests == [{"insertText": {"location": {"index": 499, "tabId": "t.0"},
                                            "text": "tail"}}]

    def test_it_does_not_write_to_index_1(self):
        """Stated as its own assertion because index 1 IS the bug, and a future refactor that
        reintroduces a fallback would satisfy a looser test."""
        d, b = doc(tabs_shape(tab("t.0", 500)))
        d.append_text("tail")
        index = b._writes[0][2][0]["insertText"]["location"]["index"]
        assert index != 1, "appending to index 1 is writing to the START of the document"
        assert index == 499

    def test_the_legacy_shape_is_unchanged(self):
        d, b = doc({"body": {"content": [{"endIndex": 42}]}})
        d.append_text("tail")
        (_, _, requests), = b._writes
        assert requests == [{"insertText": {"location": {"index": 41}, "text": "tail"}}]
        assert "tabId" not in requests[0]["insertText"]["location"], (
            "the legacy shape carries no tab id, and inventing 't.0' would be sent as fact")

    def test_a_multi_tab_document_is_REFUSED_rather_than_resolved_to_tab_one(self):
        d, _ = doc(tabs_shape(tab("t.0", 10), tab("t.1", 20)))
        with pytest.raises(ValueError) as caught:
            d.append_text("tail")
        assert "2 tabs" in str(caught.value) and "tab_id" in str(caught.value)

    def test_a_named_tab_on_a_multi_tab_document_works(self):
        d, b = doc(tabs_shape(tab("t.0", 10), tab("t.1", 777)))
        d.append_text("tail", tab_id="t.1")
        assert b._writes[0][2][0]["insertText"]["location"] == {"index": 776, "tabId": "t.1"}

    def test_an_unknown_tab_names_the_ones_that_exist(self):
        d, _ = doc(tabs_shape(tab("t.0", 10), tab("t.1", 20)))
        with pytest.raises(ValueError) as caught:
            d.append_text("tail", tab_id="t.9")
        assert "t.0" in str(caught.value) and "t.1" in str(caught.value)

    def test_an_unreadable_response_refuses_instead_of_guessing(self):
        d, _ = doc({})
        with pytest.raises(ValueError) as caught:
            d.append_text("tail")
        assert "Refusing to guess" in str(caught.value)


class TestInsertCanNameItsTab:
    def test_a_tab_id_reaches_the_request(self):
        d, b = doc(tabs_shape(tab("t.0", 10)))
        d.insert_text("hi", at=5, tab_id="t.3")
        assert b._writes[0][2] == [{"insertText": {"location": {"index": 5, "tabId": "t.3"},
                                                   "text": "hi"}}]

    def test_omitting_it_sends_no_tabId(self):
        """Unchanged for the single-tab case, which is the overwhelming majority."""
        d, b = doc(tabs_shape(tab("t.0", 10)))
        d.insert_text("hi", at=5)
        assert b._writes[0][2] == [{"insertText": {"location": {"index": 5}, "text": "hi"}}]

    def test_the_replace_pair_can_now_target_ONE_tab(self):
        """#390's actual failure: there is no `replace_range`, so a replace is delete+insert,
        and only the delete could name a tab. Both halves must reach the same tab."""
        d, b = doc(tabs_shape(tab("t.0", 10), tab("t.3", 100)))
        d.delete_range(20, 30, tab_id="t.3")
        d.insert_text("new text", at=20, tab_id="t.3")

        # The two halves are recorded differently, because `delete_range` moved onto its own
        # backend method in v0.36.0 so its capability gate could differ. Both are checked, and
        # the assertion is that they name the SAME tab - which is the whole of #390.
        deletes = [w for w in b._writes if w[0] == "docs_delete_range"]
        inserts = [w[2][0]["insertText"]["location"] for w in b._writes
                   if len(w) == 3 and w[1] == "docs"]
        assert deletes == [("docs_delete_range", "d", 20, 30, "t.3")]
        assert inserts == [{"index": 20, "tabId": "t.3"}]
        assert deletes[0][-1] == inserts[0]["tabId"], (
            "delete and insert must reach the same tab; they did not before #390")
