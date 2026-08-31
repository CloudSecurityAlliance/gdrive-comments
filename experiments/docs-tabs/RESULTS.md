# Google Docs tabs — a multi-tab document read back as a one-tab document

**Measured 2026-08-31** against live Google, on throwaway documents created and trashed by
[`probe.py`](./probe.py). Confirms a **bug** ([#280](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/280)),
fixed in the same change that added this directory.

## The finding

```
created:  1tIcBPFfr2vZmFvihehVBfpORDrslLMAzU0ZmzKCLyCs
tab 2:    t.ukmzy66yb0w3  - text inserted

  get() default           : ONE ---   | has 'tabs': False
  get(includeTabsContent) : ONE TWO   | has 'tabs': True
  library as_text()       : 'MARKER_TAB_ONE\n\n'
  tabs: [('Tab 1', 0), ('Tab 2', 1)]
```

| read mode | tab 1 | tab 2 | `tabs` key |
|---|---|---|---|
| `documents.get()` — what the library called | present | **MISSING** | absent |
| `documents.get(includeTabsContent=True)` | present | present | present |
| `Doc.as_text()` before the fix | present | **MISSING** | — |

**A two-tab document read back as though it had one.** Tab 2's content was real, retrievable with
one parameter, and dropped without a word.

## The trap in the fix, which is why the flag alone is not the fix

Measured on a **single-tab** document:

```
  includeTabsContent=False -> body populated: 1     tabs: absent
  includeTabsContent=True  -> body populated: 0     tabs: 1
      tab0 title='Tab 1' documentTab.body populated=True childTabs=0
```

With the flag, the top-level `body` comes back **EMPTY** and content moves entirely to
`tabs[].documentTab.body` — *even when there is only one tab*.

So the flag and the walker are **one change**. There were three consumers reading `body`
(`doc_text`, `doc_paragraphs`, `extract_suggestions`); adding the flag while any of them still
read `body` would have converted a silent truncation into a silent blank. They now share
`_content.doc_tab_bodies`, which is also what stops the next consumer being fixed in two places
out of three.

## What is NOT affected — an overstatement corrected

The first write-up of this claimed *"every Docs write is implicitly tab 1 only"*, inferring it from
`Location.tabId` and `Range.tabId` existing. **Wrong for `replace_text`:**

```
  replace_text("FINDME", "REPLACED")  ->  occurrences_changed = 2
    Tab 1    FINDME left: 0   REPLACED present: True
    Tab 2    FINDME left: 0   REPLACED present: True
```

`ReplaceAllTextRequest.tabsCriteria` is **optional**, and omitting it means **all tabs**. The
`tabId` fields apply to *index-addressed* requests, not to `replaceAllText`.

| operation | multi-tab behaviour | verdict |
|---|---|---|
| `as_text` / `paragraphs` / `read_file_content` | tab 1 only | **was the bug; fixed** |
| `suggestions` | tab 1 only | **same bug; fixed** |
| `replace_text` | all tabs | correct already |
| `append_text` | tab 1 | defensible, undocumented |
| `insert_text` / `delete_range` | tab 1 unless `tabId` given | needs a `tab=` argument to be usable |

## Incidental findings worth keeping

- **`addDocumentTab` works through the existing `batch_update`.** Docs tabs are creatable today,
  so a Docs `add_tab` tool would be pure exposure — as the Sheets one is in
  [#278](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/278) /
  [#279](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/279).
- Google **auto-titles** a new tab (`"Tab 2"`) and assigns `index`.
- Tabs **nest**: `childTabs`, `parentTabId`, `nestingLevel`. The walker is depth-first, because
  document order is the only ordering a reader would predict.
- Docs `batchUpdate` has **40 request types**, including `deleteTab` and
  `updateDocumentTabProperties`.

## Contrast: Sheets got this right

`Sheet.as_text()` already rendered **every** tab, prefixed with `# <tab>` when there is more than
one, and its docstring said so. So this was not a systemic blind spot about tabs — Sheets was
taught about them and Docs was not, and there was no shared abstraction to fix in one place. The
Docs fix follows the same `# <tab>` convention rather than inventing a second one.
