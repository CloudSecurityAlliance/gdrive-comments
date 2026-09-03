"""Plain-text extraction helpers for Docs/Slides API responses. Text runs only."""


def _para_text(paragraph: dict) -> str:
    return "".join(e.get("textRun", {}).get("content", "")
                   for e in paragraph.get("elements", []))


def _element_text(el: dict) -> str:
    if "paragraph" in el:
        return _para_text(el["paragraph"])
    if "table" in el:
        parts: list[str] = []
        for row in el["table"].get("tableRows", []):
            for cell in row.get("tableCells", []):
                parts.extend(_element_text(c) for c in cell.get("content", []))
        return "".join(parts)
    return ""


def doc_tab_bodies(document: dict) -> list[tuple[str | None, list]]:
    """`[(tab_title, content_elements), …]` — **every tab**, depth-first through nesting.

    **A Google Doc can have tabs, and they nest.** Measured 2026-08-31 (see
    `experiments/docs-tabs/`), and the response shape is the trap:

    * `documents.get()` **without** `includeTabsContent` populates the legacy top-level `body`
      with **the first tab only**, and omits `tabs` entirely. A twelve-tab document reads back
      as a one-tab document, with nothing saying so — which is why this exists.
    * `documents.get(includeTabsContent=True)` moves the content into
      `tabs[].documentTab.body` and leaves the top-level `body` **EMPTY** — even for a
      single-tab document.

    That second point is why the flag and this walker had to land together: passing the flag
    while any consumer still read `body` would have turned a truncation into a blank.

    The legacy branch is kept rather than removed, and not only for old responses: every
    `FakeBackend` fixture in the test suite uses the `body` shape, and so does any embedder
    holding a response it fetched itself.

    `title` is `None` in the legacy branch, because in that shape there is genuinely no tab
    name to report — as against `"Tab 1"`, which would be an invention.
    """
    tabs = document.get("tabs")
    if not tabs:
        return [(None, document.get("body", {}).get("content", []))]

    out: list[tuple[str | None, list]] = []

    def walk(tab: dict) -> None:
        props = tab.get("tabProperties") or {}
        body = (tab.get("documentTab") or {}).get("body") or {}
        out.append((props.get("title"), body.get("content", [])))
        # Depth-first, so a child tab's text follows its parent's rather than being appended
        # after every top-level tab. Tabs nest (`childTabs`, `nestingLevel`, `parentTabId`), and
        # flattening in document order is the only ordering a reader would predict.
        for child in tab.get("childTabs") or []:
            walk(child)

    for tab in tabs:
        walk(tab)
    return out


def doc_tab_end_indices(document: dict) -> list[tuple[str | None, int]]:
    """`[(tab_id, end_index), …]` per tab — where text would go to be APPENDED.

    Lives beside `doc_tab_bodies` because it needs the identical two-shape knowledge, and
    #391 is what happens when that knowledge is duplicated instead: `Doc.append_text` read
    `document["body"]["content"]` directly, which `includeTabsContent=True` leaves **EMPTY**,
    so it fell through to a default of index 1 and appended to the **START of every Google
    Doc**. Silently, on every call, for as long as the flag has been set.

    `end_index` is the body's own `endIndex` — one PAST the final newline — so a caller
    appending inside the document inserts at `end_index - 1`. Returned raw rather than
    pre-decremented, because a caller wanting the end for some other purpose should not have
    to un-apply an offset it did not ask for.

    **Returns `[]` when the shape yields no body at all**, which is the distinction that makes
    the fix a fix. A tab whose content is genuinely empty comes back with an index; a response
    this function cannot read comes back empty, so the caller can tell "the document is empty"
    from "I could not find the document", and refuse rather than invent a plausible position.
    That is the whole lesson of #391 — the old default was wrong precisely because it looked
    reasonable.

    `tab_id` is `None` in the legacy branch: that shape carries no tab id, and inventing
    `"t.0"` would be a guess that later gets sent to the API as fact.
    """
    def end_of(content: list) -> int:
        # An empty body still starts at index 1, so 1 is the honest answer for a genuinely
        # empty tab - as against the old `else 2`, which was reached when the body could not
        # be FOUND and is a different situation entirely.
        return content[-1].get("endIndex", 1) if content else 1

    tabs = document.get("tabs")
    if not tabs:
        if "body" not in document:
            return []
        return [(None, end_of(document.get("body", {}).get("content", [])))]

    out: list[tuple[str | None, int]] = []

    def walk(tab: dict) -> None:
        props = tab.get("tabProperties") or {}
        body = (tab.get("documentTab") or {}).get("body") or {}
        out.append((props.get("tabId"), end_of(body.get("content", []))))
        for child in tab.get("childTabs") or []:
            walk(child)

    for tab in tabs:
        walk(tab)
    return out


def doc_text(document: dict) -> str:
    """Every tab's text, headed by tab name when there is more than one.

    The `# <tab>` header follows the precedent `Sheet.as_text()` already set for multi-tab
    spreadsheets, rather than inventing a second convention for the same idea. Omitted for a
    single tab, so the common case is unchanged.
    """
    bodies = doc_tab_bodies(document)
    if len(bodies) == 1:
        return "".join(_element_text(el) for el in bodies[0][1])
    parts = []
    for title, content in bodies:
        parts.append(f"# {title}\n" if title else "# (untitled tab)\n")
        parts.append("".join(_element_text(el) for el in content))
    return "".join(parts)


def doc_paragraphs(document: dict) -> list[str]:
    """Paragraphs across every tab, in document order.

    Deliberately NOT prefixed with tab names: this is a list of paragraphs, and injecting
    pseudo-paragraphs that are really headings would corrupt any index a caller derives from it.
    A caller who needs the boundaries wants `doc_tab_bodies` or `as_text`.
    """
    out = []
    for _title, content in doc_tab_bodies(document):
        for el in content:
            if "paragraph" in el:
                out.append(_para_text(el["paragraph"]).rstrip("\n"))
    return out


def _page_element_text(pe: dict) -> str:
    """Extract text from a Slides pageElement: shape text, table cell text (recursively),
    and nested elementGroup children (recursively)."""
    parts = []
    for te in pe.get("shape", {}).get("text", {}).get("textElements", []):
        parts.append(te.get("textRun", {}).get("content", ""))
    for row in pe.get("table", {}).get("tableRows", []):
        for cell in row.get("tableCells", []):
            for te in cell.get("text", {}).get("textElements", []):
                parts.append(te.get("textRun", {}).get("content", ""))
    for child in pe.get("elementGroup", {}).get("children", []):
        parts.append(_page_element_text(child))
    return "".join(parts)


def slide_text(slide: dict) -> str:
    return "".join(_page_element_text(pe) for pe in slide.get("pageElements", []))


def slide_notes(slide: dict) -> str:
    notes = (slide.get("slideProperties", {}).get("notesPage", {}))
    return "".join(_page_element_text(pe) for pe in notes.get("pageElements", []))
