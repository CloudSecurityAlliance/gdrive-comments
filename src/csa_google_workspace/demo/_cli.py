"""`csa-google-workspace-mcp demo` — run the demonstration against a real account."""
from __future__ import annotations

import datetime
import sys
from collections.abc import Mapping, Sequence

from ._plan import Step
from ._runner import Runner, narrator, render

USAGE = """usage: csa-google-workspace-mcp demo [--auto] [--keep] [--share EMAIL]

  --auto          run every step without asking. Start it and come back.
  --keep          leave the files behind instead of trashing them
  --share EMAIL   address to share one file with (default: your own account)
  --no-feedback   skip the closing question (implied by --auto)

Creates a dated folder in your Drive, then for each of a Doc, a Sheet and a deck: creates it,
adds text, edits it, removes it, comments, replies, edits the comment, resolves it, reopens it,
deletes it, exports, reads permissions, copies, renames and shares. Then searches for what it
made, and trashes it again.

Every operation against every file type, on purpose: comments are one uniform Drive API across
the three, and content is three separate ones. The seam between those is where the bugs are.

Nothing here is simulated - these are real files in your real Drive, created by your own
credentials, and the demonstration is also this project's end-to-end test.
"""


def _echo(line: str) -> None:
    # stderr throughout: stdout belongs to the JSON-RPC channel, and a `demo` run shares a
    # process image with the server. One stray byte on stdout corrupts a session.
    print(line, file=sys.stderr)


def _ask(step: Step) -> bool:
    if step.teaches:
        _echo("")
        _echo(f"  Next: {step.narrate}")
        for line in step.teaches.split(". "):
            if line.strip():
                _echo(f"        {line.strip().rstrip('.')}.")
    answer = input(f"  {step.narrate}? [Y/n/q] ").strip().lower()
    if answer in ("q", "quit"):
        raise KeyboardInterrupt
    return answer in ("", "y", "yes")


def main(argv: Sequence[str], env: Mapping[str, str]) -> int:
    argv = list(argv)
    if "-h" in argv or "--help" in argv:
        _echo(USAGE)
        return 0
    auto = "--auto" in argv
    keep = "--keep" in argv
    # Unattended runs do not ask for feedback: there is nobody there to give it, and a prompt
    # nobody answers would hang a run somebody started before going for coffee.
    no_feedback = "--no-feedback" in argv or auto
    repo = env.get("CSA_GW_DEMO_REPO", REPO)
    share_with = env.get("CSA_GW_DEMO_SHARE", "")
    if "--share" in argv:
        index = argv.index("--share")
        if index + 1 >= len(argv):
            _echo("--share needs an email address")
            return 2
        share_with = argv[index + 1]

    # Built exactly as `serve` builds it - same provider, same settings, same policy - so the
    # demonstration exercises the server a client would get, not a variant assembled for it.
    from ..mcp._config import WorkspaceProvider, settings_from_env
    from ..mcp.server import create_server

    settings = settings_from_env(env)
    server = create_server(WorkspaceProvider(settings), settings=settings)

    # No colon: the prefix is interpolated into a Drive query string later, and punctuation
    # that has to be escaped there buys nothing here.
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H%M")
    prefix = f"csa-gw demo {stamp}"
    _echo(f"Creating a folder called {prefix!r} in your Drive.")
    if not share_with:
        _echo("No --share address given, so the sharing step will be skipped. Pass")
        _echo("--share you@example.com to exercise it - sharing needs a real recipient.")
    if not auto:
        _echo("Press Enter at each step, n to skip it, q to stop. Nothing is simulated:")
        _echo("these are real files, made with your own credentials.")
    _echo("")

    runner = Runner(server, on_event=narrator(_echo, teach=not auto),
                    confirm=None if auto else _ask)
    try:
        report = runner.run(prefix=prefix, folder_name=prefix,
                            share_with=share_with or "", keep=keep)
    except KeyboardInterrupt:
        _echo("\nStopped. Anything already created is in the folder above.")
        return 1

    _echo("")
    coverage_report = render(server, report)
    _echo(coverage_report)
    if report.state.get("folder_url"):
        _echo(f"The folder: {report.state['folder_url']}")
    if keep:
        _echo("Left in place, as asked. Trash the folder when you are done with it.")

    if not no_feedback:
        _feedback(coverage_report, len(report.failed), repo)
    return 1 if report.failed else 0


REPO = "CloudSecurityAlliance/csa-google-workspace"


def _feedback(coverage_report: str, failed: int, repo: str) -> None:
    """Ask, show, confirm, file. In that order, and never skipping the middle two."""
    from ._feedback import CONSENT, can_file_directly, file_issue, issue_body, new_issue_url, title

    _echo("")
    _echo("  One last thing: how was that?")
    _echo(CONSENT.format(repo=repo))
    try:
        comment = input("  Your answer (Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        _echo("")
        return
    if not comment:
        _echo("  Skipped - nothing was filed.")
        return

    body = issue_body(comment, coverage_report)
    the_title = title(failed)
    _echo("")
    _echo("  This is exactly what would be posted:")
    _echo("  " + "-" * 72)
    for line in body.split("\n"):
        _echo(f"  | {line}")
    _echo("  " + "-" * 72)
    try:
        if input("  Post it? [y/N] ").strip().lower() not in ("y", "yes"):
            _echo("  Not posted.")
            return
    except (EOFError, KeyboardInterrupt):
        _echo("")
        return

    if can_file_directly():
        filed, message = file_issue(the_title, body, repo)
        _echo(f"  {message}" if filed else f"  Could not file it: {message}")
        if filed:
            return
    _echo("  Open this to post it yourself:")
    _echo(f"  {new_issue_url(the_title, body)}")
