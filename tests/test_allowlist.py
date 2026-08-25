"""The write allowlist — #82 dimension 2, in its simplest useful form.

Deliberately a flat list of document URLs: no folders, no patterns. The tests that matter
most are the ones asserting it **fails closed** and that a folder URL is a loud error rather
than a silently-inert entry.
"""
import pytest

from csa_google_workspace.allowlist import (
    AllowlistError,
    load_allowlist,
    parse_allowlist,
    parse_document_url,
)

DOC_URL = "https://docs.google.com/document/d/1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8/edit?tab=t.0"
DOC_ID = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"
FOLDER_URL = "https://drive.google.com/drive/folders/1HXZuiBGXD263XdaEOT3siAsakQEuQzVt"


# --- URL normalisation ------------------------------------------------------

@pytest.mark.parametrize("url", [
    DOC_URL,
    f"https://docs.google.com/document/d/{DOC_ID}/edit",
    f"https://docs.google.com/document/d/{DOC_ID}/edit#heading=h.abc",
    f"https://docs.google.com/spreadsheets/d/{DOC_ID}/edit#gid=0",
    f"https://docs.google.com/presentation/d/{DOC_ID}/edit",
    f"https://drive.google.com/file/d/{DOC_ID}/view?usp=sharing",
    f"https://drive.google.com/open?id={DOC_ID}",
    f"  {DOC_URL}  ",
])
def test_every_url_form_for_one_document_normalises_to_one_id(url):
    """Matching is by file id, so a pasted link with a tab anchor and a bare id are the same
    entry. It also means a *copy* has a different id and is therefore not allowlisted."""
    assert parse_document_url(url) == DOC_ID


def test_a_folder_url_is_a_loud_error_not_an_inert_entry():
    """The important one. Treated as an opaque id, a folder URL would never match any file —
    so the entry would protect nothing while looking in the file like protection."""
    with pytest.raises(AllowlistError) as e:
        parse_document_url(FOLDER_URL)
    message = str(e.value)
    assert "folder" in message and "not supported" in message
    assert "TODO.md" in message                # points at where the design question lives


def test_a_folder_url_with_a_user_prefix_is_also_rejected():
    with pytest.raises(AllowlistError):
        parse_document_url("https://drive.google.com/drive/u/0/folders/1HXZuiBGXD263XdaEO")


@pytest.mark.parametrize("junk", ["", "   ", "not a url", "https://example.com/whatever",
                                 "short", "https://docs.google.com/document/"])
def test_nonsense_is_rejected(junk):
    with pytest.raises(AllowlistError):
        parse_document_url(junk)


def test_a_bare_file_id_is_rejected_even_though_open_accepts_one():
    """Drive ids are unstructured base64url, so a bare id is indistinguishable from a typo —
    an earlier version of this parser accepted `nonsense-one` as an id. A URL is also
    *clickable*, so whoever reviews the entry can see what they are granting."""
    with pytest.raises(AllowlistError) as e:
        parse_document_url(DOC_ID)
    assert "full URL, not a bare file id" in str(e.value)


def test_a_dashed_word_is_not_mistaken_for_a_file_id():
    with pytest.raises(AllowlistError):
        parse_document_url("nonsense-one")


# --- the file format --------------------------------------------------------

def test_comments_and_blank_lines_are_ignored_and_the_reason_is_kept():
    entries = parse_allowlist(f"""
        # CSA WG documents.

        {DOC_URL}   # CCM v5 mapping, per WG lead
    """)
    assert len(entries) == 1
    assert entries[0].file_id == DOC_ID
    assert entries[0].reason == "CCM v5 mapping, per WG lead"


def test_an_entry_without_a_reason_is_allowed():
    assert parse_allowlist(DOC_URL)[0].reason is None


def test_every_bad_line_is_reported_not_just_the_first():
    """An operator fixing a curated list of thirty URLs should not need thirty runs to find
    thirty typos."""
    with pytest.raises(AllowlistError) as e:
        parse_allowlist(f"{DOC_URL}\nnonsense-one\n{FOLDER_URL}\nnonsense-two\n")
    message = str(e.value)
    assert "3 unusable line(s)" in message
    assert ":2:" in message and ":3:" in message and ":4:" in message


def test_a_duplicate_is_dropped_not_an_error():
    other = f"https://docs.google.com/document/d/{DOC_ID}/edit#heading=h.x"
    entries = parse_allowlist(f"{DOC_URL}\n{other}   # same document, pasted differently\n")
    assert len(entries) == 1


def test_an_empty_allowlist_is_refused():
    """Indistinguishable from a typo'd path, and it would silently permit nothing — or, if
    the error were swallowed, everything."""
    with pytest.raises(AllowlistError) as e:
        parse_allowlist("# nothing here\n\n")
    assert "no usable entries" in str(e.value)


def test_line_numbers_survive_comments_and_blanks():
    entries = parse_allowlist(f"# a\n\n# b\n{DOC_URL}\n")
    assert entries[0].line == 4


def test_entry_repr_does_not_leak_the_reason():
    """A reason may name a person or an unannounced project."""
    entry = parse_allowlist(f"{DOC_URL}  # for Jane's unannounced launch doc")[0]
    assert "Jane" not in repr(entry) and "has_reason=True" in repr(entry)


# --- loading from disk (fail closed) ---------------------------------------

def test_a_missing_file_is_a_hard_failure_not_a_fallback():
    """The failure being avoided: an operator who believes writes are scoped when they are
    not, because the path had a typo."""
    with pytest.raises(AllowlistError) as e:
        load_allowlist("/nonexistent/path/allowlist.txt")
    assert "hard failure" in str(e.value)


def test_a_directory_instead_of_a_file_is_a_hard_failure(tmp_path):
    with pytest.raises(AllowlistError):
        load_allowlist(str(tmp_path))


def test_a_good_file_loads(tmp_path):
    path = tmp_path / "allow.txt"
    path.write_text(f"# ok\n{DOC_URL}  # reason here\n", encoding="utf-8")
    entries = load_allowlist(str(path))
    assert [e.file_id for e in entries] == [DOC_ID]


def test_the_source_path_appears_in_the_error(tmp_path):
    path = tmp_path / "allow.txt"
    path.write_text("garbage\n", encoding="utf-8")
    with pytest.raises(AllowlistError) as e:
        load_allowlist(str(path))
    assert str(path) in str(e.value)
