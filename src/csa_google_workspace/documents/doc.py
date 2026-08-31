from .. import _content, _formats
from .. import suggestions as _suggestions
from ..base import Document, occurrences_changed

_VIEW = {"inline": "SUGGESTIONS_INLINE", "accepted": "PREVIEW_SUGGESTIONS_ACCEPTED",
         "rejected": "PREVIEW_WITHOUT_SUGGESTIONS"}


class Doc(Document):
    """Google Docs: read (as_text/paragraphs/suggestions) + write. Accept/reject of suggestions is not
    offered — no API endpoint exists."""

    def as_text(self, suggestions: str | None = None) -> str:
        if suggestions is not None and suggestions not in _VIEW:
            raise ValueError(f"suggestions must be one of {sorted(_VIEW)} or None")
        mode = _VIEW[suggestions] if suggestions else None
        return _content.doc_text(self._backend.get_document(self.id, mode))

    def as_markdown(self) -> str:
        """This document as Markdown.

        Drive's own conversion, so headings, lists, tables and links survive — unlike
        `as_text()`, which is text runs only. This is the format CSA's `document-pipeline`
        plugin consumes (Markdown -> tagged PDF/UA-1), which makes a Doc a usable *source*
        for a publishing toolchain rather than a dead end.
        """
        return self.export(_formats.MARKDOWN).decode("utf-8")

    @property
    def suggestions(self) -> list[_suggestions.Suggestion]:
        doc = self._backend.get_document(self.id, "SUGGESTIONS_INLINE")
        return _suggestions.extract_suggestions(doc)

    @property
    def paragraphs(self) -> list[str]:
        return _content.doc_paragraphs(self._backend.get_document(self.id))

    def replace_text(self, find: str, replace: str, match_case: bool = True) -> int:
        self._require_writable()
        resp = self._backend.docs_batch_update(self.id, [{"replaceAllText": {
            "containsText": {"text": find, "matchCase": match_case}, "replaceText": replace}}])
        return occurrences_changed(resp)

    def insert_text(self, text: str, at: int) -> None:
        self._require_writable()
        self._backend.docs_batch_update(self.id, [{"insertText": {"location": {"index": at}, "text": text}}])

    def append_text(self, text: str) -> None:
        self._require_writable()
        content = self._backend.get_document(self.id).get("body", {}).get("content", [])
        end = content[-1].get("endIndex", 2) if content else 2
        self._backend.docs_batch_update(self.id, [{"insertText": {"location": {"index": end - 1}, "text": text}}])

    def delete_range(self, start: int, end: int, tab_id: str | None = None) -> None:
        """Delete a character range. **Requires `content.delete`, not `content.write`.**

        Moved off `docs_batch_update` onto a dedicated backend method in v0.36.0, so the gate can
        differ: the generic batch method cannot tell a delete from an edit, and a delete riding on
        it was ungatable apart from editing.

        `tab_id` addresses a specific tab; without it the request applies to the FIRST tab, which
        is what every index-addressed Docs request does. Get ids from `tabs`.
        """
        self._require_writable()
        self._backend.docs_delete_range(self.id, start, end, tab_id)

    @property
    def document_tabs(self) -> list[dict]:
        """Each tab as `{title, tab_id, index, nesting_level}`, depth-first through nesting.

        **NOT called `tabs`, and that is not cosmetic.** `_export.py` duck-types on
        `getattr(document, "tabs")` and uses each value as a DICT KEY, which worked while only
        `Sheet.tabs` existed and returned strings. Naming this one `tabs` made
        `export_comments` raise `unhashable type: 'dict'` on a Doc - caught by the demo, not by
        a unit test, because nothing else crossed the two types.

        Same hazard the tool surface avoided by calling these `list_document_tabs` rather than
        overloading `list_tabs`: a Sheets tab and a Docs tab are different resources sharing a
        word, and duck-typing on that word is what turns the collision into a crash.

        **Docs tabs nest** — `childTabs`, `parentTabId`, `nestingLevel` — so this is a flattened
        tree in document order, with `nesting_level` preserving the shape a flat list would
        otherwise discard. Empty for a document read in the legacy shape, where the response
        carries no tab metadata at all rather than one implicit tab.
        """
        raw = self._backend.get_document(self.id)
        out: list[dict] = []

        def walk(tab: dict, depth: int) -> None:
            props = tab.get("tabProperties") or {}
            out.append({"title": props.get("title", ""),
                        "tab_id": props.get("tabId", ""),
                        "index": props.get("index"),
                        # Google sends nestingLevel; depth is the fallback when it does not.
                        "nesting_level": props.get("nestingLevel", depth)})
            for child in tab.get("childTabs") or []:
                walk(child, depth + 1)

        for tab in raw.get("tabs") or []:
            walk(tab, 0)
        return out

    def add_tab(self, title: str | None = None) -> dict:
        """Add a tab. Google auto-titles it (`"Tab 2"`) when `title` is omitted.

        Unlike `Sheet.add_tab` this does NOT refuse a duplicate title, because Docs tabs are
        addressed by `tabId` rather than by name — two tabs may legitimately share a title, and
        refusing would invent a constraint Google does not have.
        """
        self._require_writable()
        return self._backend.docs_add_tab(self.id, title)

    def delete_tab(self, tab_id: str) -> None:
        """Delete a tab **by id**. Requires `content.delete`.

        By id and not by title, deliberately: Docs permits duplicate titles, so a
        delete-by-name would be ambiguous exactly when it matters. Get ids from `tabs`.
        """
        self._require_writable()
        self._backend.docs_delete_tab(self.id, tab_id)

    def batch_update(self, requests: list) -> dict:
        self._require_writable()
        return self._backend.docs_batch_update(self.id, requests)
