from .. import _content, _context, _formats
from .. import suggestions as _suggestions
from ..base import Document, occurrences_changed

_VIEW = {"inline": "SUGGESTIONS_INLINE", "accepted": "PREVIEW_SUGGESTIONS_ACCEPTED",
         "rejected": "PREVIEW_WITHOUT_SUGGESTIONS"}


class Doc(Document):
    """Google Docs: read (as_text/paragraphs/suggestions) + write. Accept/reject of suggestions is not
    offered — no API endpoint exists."""

    def comment_contexts(self, comments: list, *, paragraphs: int = 0) -> list:
        """The passage around each comment's anchor — one `Context` per comment, aligned to input.

        Takes the WHOLE LIST on purpose. Locating a quote needs the document, so this is **one**
        fetch for ninety comments where a per-comment call would be ninety — and accessors
        re-fetch by design (no caching layer, settled 2026-08-30), so the loop genuinely
        re-downloads it each time. Making the batch the API is how that cost stays visible.

        **Never `None`, and never a silent gap.** A comment with no quoted text — file-level,
        or anchored to a non-text object — comes back as `KIND_NO_QUOTE` with a note saying so,
        rather than as an absence a caller has to interpret. "We looked and there was nothing
        to look for" and "we never looked" must not arrive as the same value.

        See `_context` for why the anchor itself cannot be used, and why quoted text is
        nevertheless almost always present.
        """
        raw = self._backend.get_document(self.id)
        return [_context.build(raw, getattr(c, "quoted_text", None), paragraphs=paragraphs)
                for c in comments]

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

    def insert_text(self, text: str, at: int, tab_id: str | None = None) -> None:
        """Insert text at a character index, optionally in a named tab.

        `tab_id` added in v0.45.0 (#390). Without it the Docs API applies the request to the
        FIRST tab — and `delete_range` has always accepted one, so a caller composing a
        replace out of the pair (there is no `replace_range`) deleted from the tab they named
        and inserted into tab 1. No error from either call; the corruption was only visible by
        reading two tabs.

        The omission was documented as *"a real limitation of index-addressed Docs requests,
        not a choice"*. **That was wrong** — measured 2026-09-03 by sending a bogus tab id,
        which came back *"Cannot apply request to an invalid tab ID"*, i.e. parsed and
        validated. `insertText.location` takes a `tabId` exactly as `Range` does.
        """
        self._require_writable()
        location: dict = {"index": at}
        if tab_id:
            location["tabId"] = tab_id
        self._backend.docs_batch_update(self.id, [{"insertText": {"location": location,
                                                                  "text": text}}])

    def append_text(self, text: str, tab_id: str | None = None) -> None:
        """Add text to the end of the document — or of one tab.

        **This appended to the START of every Google Doc until v0.45.0 (#391).** It read
        `document["body"]["content"]` while `get_document` passes `includeTabsContent=True`,
        which leaves the top-level `body` EMPTY and moves everything under
        `tabs[].documentTab.body`. So `content` was `[]`, a default of index 1 was used, and
        the text went to the top. Silently, on every call. `_content.doc_tab_end_indices` now
        owns that shape knowledge, which is the actual fix — the bug was a second reader of a
        response shape that only one function understood.

        **A multi-tab document with no `tab_id` is REFUSED**, rather than resolved to the first
        tab. "The end of the document" has no meaning when there are several ends, and #390 is
        the argument: a refusal the caller can see beats a default they cannot. Nothing relies
        on the old behaviour, because the old behaviour was to write to the beginning.
        """
        self._require_writable()
        ends = _content.doc_tab_end_indices(self._backend.get_document(self.id))
        if not ends:
            # Could not find a body at all - distinct from finding an empty one, which yields
            # index 1. Refusing is the point: the old code's plausible-looking default is
            # exactly what let #391 run undetected.
            raise ValueError(
                "cannot determine where this document ends: the response carried neither a "
                "top-level `body` nor any `tabs`. Refusing to guess an index, because "
                "guessing one here appends to the wrong place without failing.")
        if tab_id is None:
            if len(ends) > 1:
                raise ValueError(
                    f"this document has {len(ends)} tabs, so 'the end' is ambiguous. Pass "
                    f"tab_id to say which one; `document_tabs` lists them. Refusing rather "
                    f"than appending to the first tab, which is a silent wrong answer.")
            target, end = ends[0]
        else:
            match = [(t, e) for t, e in ends if t == tab_id]
            if not match:
                known = [t for t, _ in ends if t]
                raise ValueError(f"no tab {tab_id!r} in this document. Present: "
                                 f"{known or '(the response carries no tab ids)'}")
            target, end = match[0]
        location: dict = {"index": max(1, end - 1)}
        if target:
            location["tabId"] = target
        self._backend.docs_batch_update(self.id, [{"insertText": {"location": location,
                                                                  "text": text}}])

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
