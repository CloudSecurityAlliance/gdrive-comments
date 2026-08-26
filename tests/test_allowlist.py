"""The write allowlist — #82 dimension 2, in its simplest useful form.

Deliberately a flat list of document URLs: no folders, no patterns. The tests that matter
most are the ones asserting it **fails closed** and that a folder URL is a loud error rather
than a silently-inert entry.
"""
import pytest

from csa_google_workspace.allowlist import (
    AllowlistError,
    parse_allowlist,
    parse_document_url,
    parse_setting,
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
    message = str(e.value)
    assert "bare file id" in message
    assert "can be opened and checked by whoever reviews it" in message


def test_a_dashed_word_is_not_mistaken_for_a_file_id():
    with pytest.raises(AllowlistError):
        parse_document_url("nonsense-one")


# --- the file format --------------------------------------------------------

def test_comments_and_blank_lines_are_ignored_and_the_reason_is_kept():
    listing = parse_allowlist(f"""
        # CSA WG documents.

        {DOC_URL}   # CCM v5 mapping, per WG lead
    """)
    assert len(listing.entries) == 1
    assert listing.entries[0].file_id == DOC_ID
    assert listing.entries[0].reason == "CCM v5 mapping, per WG lead"


def test_an_entry_without_a_reason_is_allowed():
    assert parse_allowlist(DOC_URL).entries[0].reason is None


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
    listing = parse_allowlist(f"{DOC_URL}\n{other}   # same document, pasted differently\n")
    assert len(listing.entries) == 1


def test_an_empty_allowlist_is_refused():
    """Indistinguishable from a typo'd path, and it would silently permit nothing — or, if
    the error were swallowed, everything."""
    with pytest.raises(AllowlistError) as e:
        parse_allowlist("# nothing here\n\n")
    assert "no usable entries" in str(e.value)


def test_line_numbers_survive_comments_and_blanks():
    assert parse_allowlist(f"# a\n\n# b\n{DOC_URL}\n").entries[0].line == 4


def test_entry_repr_does_not_leak_the_reason():
    """A reason may name a person or an unannounced project."""
    entry = parse_allowlist(f"{DOC_URL}  # for Jane's unannounced launch doc").entries[0]
    assert "Jane" not in repr(entry) and "has_reason=True" in repr(entry)


# --- there is no file: a path-shaped value is a diagnosable mistake --------

@pytest.mark.parametrize("path_shaped", [
    "/etc/csa/allow.txt", "~/allow.txt", "./allow.list", "../a.conf", "allowlist.yaml",
    "C:\\Users\\kurt\\allow.txt", "allow.cfg", "/var/tmp/x.json",
])
def test_a_path_shaped_value_says_so(path_shaped):
    """Reading a file would put the real policy somewhere the client config does not show,
    behind a path whose target can change without the config changing."""
    problem = diagnose_url(path_shaped)
    assert problem is not None and "file path" in problem
    assert "set in the environment, not read from a file" in problem


def test_a_url_is_never_mistaken_for_a_path():
    """The path check runs after URL extraction, so a real URL cannot trip it — including a
    Drive URL that happens to end in something dotted."""
    assert diagnose_url(DOC_URL) is None
    assert diagnose_url(f"{DOC_URL}#gid=0") is None


# --- the environment value --------------------------------------------------

def test_a_single_url_is_accepted():
    assert [e.file_id for e in parse_setting(DOC_URL, variable="V").entries] == [DOC_ID]


@pytest.mark.parametrize("separator", [", ", ",", " ", "  ", ";", "\n", "\t"])
def test_any_separator_works_when_there_are_no_comments(separator):
    other = "https://docs.google.com/document/d/2bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/edit"
    assert len(parse_setting(f"{DOC_URL}{separator}{other}", variable="V").entries) == 2


def test_with_comments_only_newlines_separate():
    """The condition that stops a separator and a comment fighting over one character: when
    `#` is present, newlines are the only separator, so the ambiguous case is unreachable."""
    other = "https://docs.google.com/document/d/2bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/edit"
    listing = parse_setting(f"{DOC_URL}  # first, with a comma\n{other}  # second", variable="V")
    assert len(listing.entries) == 2
    assert listing.entries[0].reason == "first, with a comma"


def test_errors_name_the_variable_they_came_from():
    with pytest.raises(AllowlistError) as e:
        parse_setting("https://example.com/nope", variable="CSA_GW_ALLOWLIST_MODIFY")
    assert "CSA_GW_ALLOWLIST_MODIFY" in str(e.value)


# --- the `*` entry ----------------------------------------------------------

def test_a_star_line_means_every_file():
    listing = parse_allowlist("* # all access, DANGEROUS, no file scoping at all")
    assert listing.all_files is True and listing.entries == ()


def test_a_star_short_circuits_the_rest_of_the_file():
    """Once everything is permitted, nothing after it can narrow that — saying otherwise in
    the file would read as a restriction that is not one."""
    assert parse_allowlist(f"*\n{DOC_URL}\n").all_files is True


def test_a_star_warns_because_unrestricted_access_should_be_visible(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        parse_allowlist("*  # yes really")
    assert "EVERY file" in caplog.text


@pytest.mark.parametrize("spelling", ["*", "any", "all", "ANY", " * "])
def test_the_synonyms_for_everything(spelling):
    assert parse_allowlist(spelling).all_files is True


def test_an_empty_file_points_at_the_star_escape_hatch():
    """The error has to name the alternative, or an operator's only obvious move is to delete
    the configuration — which used to mean unrestricted."""
    with pytest.raises(AllowlistError) as e:
        parse_allowlist("# nothing\n")
    assert "`*`" in str(e.value)


def test_a_listing_repr_distinguishes_everything_from_a_set():
    assert repr(parse_allowlist("*")) == "Listing(all_files=True)"
    assert "files=1" in repr(parse_allowlist(DOC_URL))


# --- diagnostics: a specific reason, not "invalid value" --------------------

from csa_google_workspace.allowlist import diagnose_setting, diagnose_url  # noqa: E402


def test_a_usable_url_has_no_diagnosis():
    assert diagnose_url(DOC_URL) is None


def test_a_real_id_containing_placeholder_letters_is_still_accepted():
    """Load-bearing ordering: extraction runs *before* the placeholder check, because a
    genuine 44-character Drive id is random base64url and will occasionally contain a run
    like "AAA". Diagnosing a working URL as a placeholder is worse than any message it
    replaces."""
    real = "https://docs.google.com/document/d/1AAAxxx_bbbBBBcccDDDeeeFFFgggHHH123"
    assert diagnose_url(real) is None
    assert parse_document_url(real) == "1AAAxxx_bbbBBBcccDDDeeeFFFgggHHH123"


@pytest.mark.parametrize("value,expected", [
    ("", "empty"),
    ("    ", "empty"),
    ("https://docs.google.com/document/d/AAA…/edit", "placeholder"),
    ("https://docs.google.com/document/d/<your-id>/edit", "placeholder"),
    ("https://docs.google.com/document/d/", "file id is missing"),
    ("https://docs.google.com/document/", "no '/d/<id>' segment"),
    ("https://example.com/whatever", "not a Google Docs or Drive address"),
    (DOC_ID, "bare file id"),
    ("nonsense-one", "bare file id"),
    (FOLDER_URL, "folder"),
])
def test_each_mistake_gets_its_own_diagnosis(value, expected):
    """Every rung of the ladder is a mistake somebody actually makes. The difference between
    "invalid value" and "the URL stops after /d/, so the file id is missing" is the difference
    between a support conversation and a fix."""
    problem = diagnose_url(value)
    assert problem is not None
    assert expected in problem, problem


def test_the_diagnosis_reaches_the_raised_error():
    with pytest.raises(AllowlistError) as e:
        parse_document_url("https://docs.google.com/document/d/")
    assert "file id is missing" in str(e.value)


def test_unset_and_blank_are_diagnosed_differently():
    """They behave identically and have completely different fixes — one means nobody
    configured it, the other usually means a template or an unexpanded shell variable."""
    unset = diagnose_setting("CSA_GW_ALLOWLIST_MODIFY", None)
    blank = diagnose_setting("CSA_GW_ALLOWLIST_MODIFY", "   ")
    assert "is not set" in unset and "no file to create" in unset
    assert "set but empty" in blank and "not the same as unset" in blank
    assert unset != blank


def test_the_blank_diagnosis_points_at_the_likely_cause():
    blank = diagnose_setting("X", "")
    assert "template" in blank and "shell variable" in blank


# --- whitespace is for the author, not the parser --------------------------

OTHER_ID = "2bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
OTHER_URL = f"https://docs.google.com/document/d/{OTHER_ID}/edit"


def test_entries_can_be_indented_and_aligned_with_spaces_or_tabs():
    """People line these up so the reasons form a column. That has to be free."""
    listing = parse_allowlist(
        f"\t{DOC_URL}\t\t# CCM mapping\n"
        f"    {OTHER_URL}     # AICM tracker\n")
    assert [e.file_id for e in listing.entries] == [DOC_ID, OTHER_ID]
    assert [e.reason for e in listing.entries] == ["CCM mapping", "AICM tracker"]


def test_blank_and_whitespace_only_lines_are_ignored_anywhere():
    listing = parse_allowlist(f"\n   \n\t\n{DOC_URL}\n  \n{OTHER_URL}\n\n")
    assert len(listing.entries) == 2


def test_whole_line_comments_may_themselves_be_indented():
    listing = parse_allowlist(f"    # a heading\n\t# and another\n{DOC_URL}\n")
    assert len(listing.entries) == 1


def test_windows_line_endings_work():
    assert len(parse_allowlist(f"{DOC_URL}\r\n{OTHER_URL}\r\n").entries) == 2


# --- the comment delimiter must not eat a URL fragment ---------------------

def test_a_url_fragment_stays_part_of_the_url():
    """`#gid=0` and `#heading=h.x` are ordinary Drive links. Treating their `#` as a comment
    delimiter turned the anchor into the "reason" and threw the real reason away."""
    entry = parse_allowlist(f"{DOC_URL}#heading=h.abc   # the real reason").entries[0]
    assert entry.file_id == DOC_ID
    assert entry.reason == "the real reason"


def test_a_sheets_gid_anchor_is_not_mistaken_for_a_comment():
    entry = parse_allowlist(
        f"https://docs.google.com/spreadsheets/d/{DOC_ID}/edit#gid=0").entries[0]
    assert entry.reason is None


def test_a_hash_needs_whitespace_before_it_to_start_a_comment():
    assert parse_allowlist(f"{DOC_URL}#notacomment").entries[0].reason is None
    assert parse_allowlist(f"{DOC_URL} #a comment").entries[0].reason == "a comment"
    assert parse_allowlist(f"{DOC_URL}\t#tab first").entries[0].reason == "tab first"


# --- a URL inside a comment is a mistake, loudly ---------------------------

def test_a_url_swallowed_into_a_comment_is_an_error():
    """`a # one, b # two` looks like two entries and parses as one. The consequence is a
    policy with fewer files than its author believes — fail closed *and* loudly, because
    failing closed quietly is how somebody spends an afternoon on it."""
    with pytest.raises(AllowlistError) as e:
        parse_allowlist(f"{DOC_URL} # first, {OTHER_URL} # second")
    message = str(e.value)
    assert "NOT being allowlisted" in message
    assert "own line" in message


def test_the_swallowed_url_error_suggests_the_workaround():
    with pytest.raises(AllowlistError) as e:
        parse_allowlist(f"{DOC_URL} # see also {OTHER_URL}")
    assert "by name rather than by URL" in str(e.value)


def test_a_reason_mentioning_a_non_document_url_is_fine():
    """Only a *document* URL is the tell. A wiki link in a reason is just prose."""
    entry = parse_allowlist(f"{DOC_URL}  # rationale at https://wiki.example.org/why").entries[0]
    assert entry.reason == "rationale at https://wiki.example.org/why"


# --- quoting is the surrounding format's problem, not ours -----------------

@pytest.mark.parametrize("reason", [
    "Kurt's draft",
    'the "final" version',
    "Kurt's \"final\" draft #2",
    "50% done; see §4",
    "reason with, commas and; semicolons",
])
def test_the_reason_is_free_text(reason):
    """Apostrophes, quotes, further `#`s and separators are all fine *here* — whatever holds
    the value, JSON or a shell, has its own quoting rules to satisfy, and that is a different
    layer."""
    assert parse_allowlist(f"{DOC_URL}  # {reason}").entries[0].reason == reason


def test_two_urls_on_one_line_is_an_error_not_a_silent_drop():
    """Same mistake as the swallowed-comment one, wearing different clothes: with a comment
    present, entries split on newlines only, so `a, b  # both` would allowlist just `a`."""
    with pytest.raises(AllowlistError) as e:
        parse_allowlist(f"{DOC_URL}, {OTHER_URL}  # both trackers")
    message = str(e.value)
    assert "contains 2 document URLs" in message
    assert "only the first would be allowlisted" in message


def test_commas_still_separate_when_there_are_no_comments():
    """The separator forms are unchanged — this only bites once a `#` forces newline-only
    splitting, and then it says so instead of dropping one."""
    assert len(parse_setting(f"{DOC_URL}, {OTHER_URL}", variable="V").entries) == 2


@pytest.mark.parametrize("separator", ["\t", "\n", " ", ",", ";", ",\n\t "])
def test_every_separator_shape_works_without_comments(separator):
    assert len(parse_setting(f"{DOC_URL}{separator}{OTHER_URL}", variable="V").entries) == 2


class TestTheHostIsActuallyChecked:
    """The host rung existed and was unreachable.

    Extraction returned "usable" for any URL containing a `/d/<id>/` segment, so the check
    below it never ran and `https://evil.example.com/document/d/<real-id>/edit` was accepted.
    Then the check itself used a bare `endswith`, which blesses `evildocs.google.com` - the
    incomplete-substring family CodeQL flags as `py/incomplete-url-substring-sanitization`.

    Neither was an escalation: the id extracted from such a URL is a real Drive id, so the
    entry granted exactly what listing that id would have granted. What was lost was the check
    - somebody pasting a lookalike domain, or a link-tracker wrapper, had it silently blessed,
    and a reviewer reading the config saw a non-Google URL the tool had apparently approved.
    """

    ID = "1oW1BM5UpGCiwuk8jLJWuou4BECe5INjI8T6rGnAj8x8"

    def url(self, host):
        return f"https://{host}/document/d/{self.ID}/edit"

    @pytest.mark.parametrize("host", ["docs.google.com", "drive.google.com",
                                      "sheets.google.com", "slides.google.com",
                                      "docs.google.com."])
    def test_googles_own_hosts_are_accepted(self, host):
        assert len(parse_allowlist(self.url(host)).entries) == 1

    @pytest.mark.parametrize("host", [
        "evil.example.com",              # plainly not Google
        "docs.google.com.evil.net",      # Google as a prefix of somebody else's domain
        "evildocs.google.com",           # the endswith trap: a suffix, not a subdomain
        "notdrive.google.com",
    ])
    def test_everything_else_is_refused_and_says_why(self, host):
        with pytest.raises(AllowlistError, match="not a Google Docs or Drive address"):
            parse_allowlist(self.url(host))

    def test_a_real_subdomain_is_still_accepted(self):
        """Equality OR a dot boundary - so Google can add a subdomain without a code change,
        while a lookalike registered next door cannot walk in."""
        assert len(parse_allowlist(self.url("eu.docs.google.com")).entries) == 1

    def test_a_bare_id_and_a_path_still_reach_their_own_diagnoses(self):
        """The host rung was hoisted above extraction, so these had to keep working: both parse
        to an empty netloc and must fall through rather than being called bad hosts."""
        with pytest.raises(AllowlistError, match="bare file id"):
            parse_allowlist(self.ID)
        with pytest.raises(AllowlistError, match="file path"):
            parse_allowlist("/Users/someone/allowlist.txt")
