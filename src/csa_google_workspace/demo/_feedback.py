"""Ask what they thought, and file it where it can be counted.

The demonstration ends with a question because that is the moment somebody has an opinion and
has not yet lost it. An issue filed then is worth more than a survey sent later, and it costs
the person one sentence.

It is also the only honest measure of whether any of this gets used. Download counts say a
package was installed; an issue says a person ran it, watched it work, and had a view. For a
tool nobody is obliged to adopt, that difference is the whole signal.

**Consent is explicit and the wording is plain.** The issue is public, on a public repository,
under their GitHub account and their name. Anybody who would rather not is told how to skip in
the same breath as being asked, and the body is shown in full before anything is filed —
because "we posted your words publicly" is not something to discover afterwards.
"""
from __future__ import annotations

import shutil
import subprocess  # nosec B404 - `gh`, resolved to an absolute path, with a list argv and

# no shell. See _gh() for why this is the narrowest way to file an issue.
import urllib.parse

from .._environment import ISSUES_URL, describe_environment

LABEL = "automated-feedback"

CONSENT = """
  This posts a PUBLIC issue on {repo}, from your GitHub account, with your
  name on it. It will contain: your comment, this run's step-by-step results, and the
  version, OS and Python you ran it on.

  It will NOT contain any document name, link, id or content - the demonstration's files
  are yours and stay out of it.

  Anything is useful. "Worked, no notes" is a data point; so is "the narration is too long".
  Press Enter on its own to skip - nothing is filed, and you will not be asked twice.
"""


def issue_body(comment: str, coverage_report: str) -> str:
    """What gets filed. Environment first, because it is what a triager reads first."""
    environment = describe_environment()
    return "\n".join([
        "*Filed by `csa-google-workspace-mcp demo`, with the author's consent.*",
        "",
        "## What they said",
        "",
        comment.strip() or "_(no comment given)_",
        "",
        "## Environment",
        "",
        "```",
        environment.as_markdown(),
        "```",
        "",
        coverage_report,
        "",
        "---",
        "",
        f"Automated feedback from a demonstration run. Label: `{LABEL}`. No document names, "
        "links, ids or content are included.",
    ])


def title(failed: int) -> str:
    environment = describe_environment()
    outcome = f"{failed} step(s) failed" if failed else "clean run"
    return f"[demo] {environment.server_version} on {environment.os} - {outcome}"


def new_issue_url(the_title: str, body: str) -> str:
    query = urllib.parse.urlencode({"title": the_title, "body": body, "labels": LABEL})
    return f"{ISSUES_URL}/new?{query}"


def _gh() -> str | None:
    """The absolute path to `gh`, or None.

    Resolved rather than invoked by name: a bare "gh" is looked up on PATH at exec time, so a
    directory earlier on PATH decides what runs. This costs nothing and removes that question.

    The server itself never shells out - this is the demonstration, filing an issue the person
    has just read and agreed to, using the credential they already have.
    """
    return shutil.which("gh")


def can_file_directly() -> bool:
    """Is `gh` present AND authenticated? Both, because an unauthenticated `gh` fails at the
    end of a flow the person has already agreed to, which is the worst place to find out."""
    executable = _gh()
    if not executable:
        return False
    result = subprocess.run([executable, "auth", "status"],   # nosec B603 - absolute path,
                            capture_output=True, text=True)   # list argv, no shell
    return result.returncode == 0


def file_issue(the_title: str, body: str, repo: str) -> tuple[bool, str]:
    """File it with `gh`. Returns (filed, message-or-url).

    The label is applied here rather than asked for: every issue this produces is the same
    kind of thing, and a label somebody has to remember is a label that goes missing.
    """
    executable = _gh()
    if not executable:
        return False, "gh is not installed"
    # A list argv with no shell, so the title and body - which contain the person's own words -
    # are arguments and cannot become commands however they are punctuated.
    result = subprocess.run(                                  # nosec B603
        [executable, "issue", "create", "--repo", repo, "--title", the_title, "--body", body,
         "--label", LABEL],
        capture_output=True, text=True)
    if result.returncode == 0:
        return True, result.stdout.strip()
    # A missing label is the common failure on a fresh repo, and it should not lose the
    # feedback: retry once without it rather than making the person paste it by hand.
    if "label" in (result.stderr or "").lower():
        retry = subprocess.run(                               # nosec B603 - as above
            [executable, "issue", "create", "--repo", repo, "--title", the_title,
             "--body", body],
            capture_output=True, text=True)
        if retry.returncode == 0:
            return True, retry.stdout.strip() + f"  (the '{LABEL}' label does not exist yet)"
    return False, (result.stderr or "gh could not create the issue").strip()
