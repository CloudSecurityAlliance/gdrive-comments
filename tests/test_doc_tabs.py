"""A Google Doc can have tabs, and reading only the first one was silent truncation.

**Measured 2026-08-31 against live Google** — `experiments/docs-tabs/RESULTS.md`. A two-tab
document read back as a one-tab document:

    get() default           : ONE ---   | has 'tabs': False
    get(includeTabsContent) : ONE TWO   | has 'tabs': True
    Doc.as_text()           : 'MARKER_TAB_ONE\\n\\n'

Tab 2's text was real, retrievable with one parameter, and dropped without a word. Same shape as
the `list_labels` hazard: **reporting less than exists, silently, is the dangerous direction.**

Sharper here than for a general Drive tool. A comment's `quoted_text` comes from *Drive*, not from
the Docs body — so `list_comments` would report a comment anchored in tab 2 **with its passage**,
while `read_file_content` returned a document not containing that passage. Triage would proceed on
partial context and look complete.

**The trap that made this one change rather than two.** With `includeTabsContent=True` the
top-level `body` comes back **EMPTY** and content moves to `tabs[].documentTab.body` — *even for a
single-tab document*. Adding the flag while any consumer still read `body` would have converted a
truncation into a blank. There were three such consumers (`doc_text`, `doc_paragraphs`,
`extract_suggestions`), which is why they now share one walker.
"""
from __future__ import annotations

from csa_google_workspace._content import doc_paragraphs, doc_tab_bodies, doc_text
from csa_google_workspace.suggestions import extract_suggestions


def para(text, **run):
    return {"paragraph": {"elements": [{"textRun": {"content": text, **run}}]}}


def tab(title, *elements, children=()):
    return {"tabProperties": {"title": title},
            "documentTab": {"body": {"content": list(elements)}},
            "childTabs": list(children)}


LEGACY = {"body": {"content": [para("legacy body text\n")]}}

TABBED = {"tabs": [
    tab("Overview", para("first tab text\n")),
    tab("Details", para("second tab text\n")),
]}

NESTED = {"tabs": [
    tab("Parent", para("parent text\n"),
        children=[tab("Child", para("child text\n"))]),
    tab("Sibling", para("sibling text\n")),
]}


class TestTheLegacyShapeStillWorks:
    """Kept deliberately: every `FakeBackend` fixture in this suite uses `body`, and so does any
    embedder holding a response it fetched itself."""

    def test_body_is_read_when_there_is_no_tabs_key(self):
        assert doc_text(LEGACY) == "legacy body text\n"

    def test_the_title_is_none_rather_than_invented(self):
        """`"Tab 1"` would be a fabrication — in the legacy shape there is genuinely no tab name
        in the response to report."""
        assert doc_tab_bodies(LEGACY) == [(None, LEGACY["body"]["content"])]

    def test_an_empty_document_is_empty_not_an_error(self):
        assert doc_text({}) == ""
        assert doc_paragraphs({}) == []


class TestEveryTabIsRead:
    def test_text_from_both_tabs_is_present(self):
        """The bug, directly: this returned only the first tab."""
        out = doc_text(TABBED)
        assert "first tab text" in out
        assert "second tab text" in out, "tab 2 was dropped — that is the bug"

    def test_tabs_are_named_when_there_is_more_than_one(self):
        """Following the precedent `Sheet.as_text()` already set for multi-tab spreadsheets,
        rather than inventing a second convention for the same idea."""
        out = doc_text(TABBED)
        assert "# Overview" in out and "# Details" in out

    def test_a_single_tab_gets_no_header(self):
        """The common case must read exactly as it did before. A `# Tab 1` appearing on every
        one-tab document would be a visible regression for every existing caller."""
        one = {"tabs": [tab("Tab 1", para("only text\n"))]}
        assert doc_text(one) == "only text\n"

    def test_order_follows_the_document(self):
        out = doc_text(TABBED)
        assert out.index("first tab text") < out.index("second tab text")

    def test_an_untitled_tab_says_so_rather_than_going_unlabelled(self):
        """Silently omitting the header for one tab in a multi-tab render would make its text
        look like a continuation of the tab above."""
        d = {"tabs": [tab("Named", para("a\n")),
                      {"documentTab": {"body": {"content": [para("b\n")]}}}]}
        assert "# (untitled tab)" in doc_text(d)


class TestNestingIsDepthFirst:
    """Tabs nest — `childTabs`, `nestingLevel`, `parentTabId` all exist because they do."""

    def test_a_child_tab_is_read(self):
        assert "child text" in doc_text(NESTED)

    def test_a_child_follows_its_parent_rather_than_all_top_level_tabs(self):
        """Breadth-first would put the child after `Sibling`, which is not the order anybody
        reading the document would predict."""
        out = doc_text(NESTED)
        assert out.index("parent text") < out.index("child text") < out.index("sibling text")

    def test_titles_include_nested_ones(self):
        assert [t for t, _ in doc_tab_bodies(NESTED)] == ["Parent", "Child", "Sibling"]


class TestParagraphsDoNotGainPseudoEntries:
    def test_paragraphs_span_every_tab(self):
        assert doc_paragraphs(TABBED) == ["first tab text", "second tab text"]

    def test_tab_titles_are_NOT_injected_as_paragraphs(self):
        """`as_text` gets headers; `paragraphs` must not. It is a list of paragraphs, and
        inserting headings that are not paragraphs would corrupt any index a caller derives
        from it — a caller who wants boundaries wants `doc_tab_bodies`."""
        out = doc_paragraphs(TABBED)
        assert not any(p.startswith("#") for p in out)
        assert len(out) == 2


class TestSuggestionsSpanTabs:
    """The third of three consumers, and the easiest to forget — which is the argument for one
    shared walker rather than three fixes."""

    def test_a_suggestion_in_the_second_tab_is_found(self):
        d = {"tabs": [
            tab("One", para("kept\n")),
            tab("Two", para("proposed\n", suggestedInsertionIds=["sug-2"])),
        ]}
        found = extract_suggestions(d)
        assert [s.suggestion_id for s in found] == ["sug-2"]
        assert found[0].kind == "insertion"

    def test_suggestions_in_both_tabs_are_found(self):
        d = {"tabs": [
            tab("One", para("a\n", suggestedInsertionIds=["sug-1"])),
            tab("Two", para("b\n", suggestedInsertionIds=["sug-2"])),
        ]}
        assert {s.suggestion_id for s in extract_suggestions(d)} == {"sug-1", "sug-2"}

    def test_the_legacy_shape_still_yields_suggestions(self):
        d = {"body": {"content": [para("x\n", suggestedInsertionIds=["sug-legacy"])]}}
        assert [s.suggestion_id for s in extract_suggestions(d)] == ["sug-legacy"]
