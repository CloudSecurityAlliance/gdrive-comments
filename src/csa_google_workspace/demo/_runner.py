"""Execute the plan through the real MCP server, and report what it covered.

**Through the server, not the library.** The plan could call `Workspace` directly and would be
shorter for it, but then it would prove nothing about the surface an MCP client actually meets:
the published schemas, the structured output, the error translation, the annotations, the policy
gates. Those are where the bugs that reached users have lived — a parameter alias that published
a correct schema and failed every call, a tool that shipped with no description, a `TypedDict`
that returned null structured content below Python 3.12. Driving `call_tool` catches that class;
driving the library does not.

The consequence worth stating: the same plan runs against `FakeBackend` offline, so CI proves
the matrix is *executable* on every commit, and against real Google when somebody runs the demo.
One list, two backends, and the offline run is what stops the demo rotting between uses.

Coverage is measured against the server's own registry rather than a maintained list, so "100%"
is a computed number. A tool that exists and is never exercised shows up as a gap, which is the
only way that claim can stay true as tools are added.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from typing import Any

from ._plan import Outcome, Report, State, Step, build, initial_state

# Never exercised, and named rather than quietly absent — a coverage report that silently
# excludes things is a coverage report that can be gamed.
NOT_EXERCISED = {
    "authenticate": "opens a browser and waits for a human; the demo cannot answer it",
}


class Runner:
    """Runs steps, threads state between them, and records what happened."""

    def __init__(self, server: Any, *, on_event: Callable[[str, Any], None] | None = None,
                 confirm: Callable[[Step], bool] | None = None):
        self._server = server
        self._on_event = on_event or (lambda kind, payload: None)
        # `confirm` is what makes the narrated mode narrated: returning False skips a step,
        # and returning True after printing `teaches` is the whole of "step through it with me".
        self._confirm = confirm

    def _enabled(self) -> set[str]:
        out = asyncio.run(self._server.call_tool("describe_configuration", {}))
        return set(out.structured_content.get("capabilities_enabled", []))

    def run(self, *, prefix: str, folder_name: str, share_with: str,
            keep: bool = False) -> Report:
        state: State = initial_state(prefix, folder_name, share_with)
        report = Report(state=state)
        enabled = self._enabled()

        for step in build(prefix, folder_name, share_with, keep=keep):
            outcome = self._one(step, state, enabled)
            report.outcomes.append(outcome)
            self._on_event("step", outcome)
        self._on_event("done", report)
        return report

    def _one(self, step: Step, state: State, enabled: set[str]) -> Outcome:
        if step.requires and step.requires not in enabled:
            return Outcome(step, "skipped",
                           f"needs the {step.requires} capability, which is off")
        if self._confirm is not None and not self._confirm(step):
            return Outcome(step, "skipped", "you chose to skip this one")
        try:
            args = step.args(state)
        except IndexError:
            # A cleanup slot with nothing left to trash. There are more slots than files on
            # purpose, so this is the normal way the tail of the cleanup ends.
            return Outcome(step, "skipped", "nothing left to tidy")
        except KeyError as missing:
            # An earlier step did not produce what this one needs. Reported as a skip rather
            # than a failure: the fault is upstream and is already recorded there.
            return Outcome(step, "skipped", f"nothing to work with ({missing})")

        started = time.monotonic()
        try:
            result = asyncio.run(self._server.call_tool(step.tool, args))
        except Exception as error:                       # noqa: BLE001 - reported, not raised
            elapsed = time.monotonic() - started
            status = "skipped" if step.optional else "failed"
            return Outcome(step, status, f"{type(error).__name__}: {error}", seconds=elapsed)

        elapsed = time.monotonic() - started
        content = result.structured_content
        if step.captures and content is not None:
            try:
                step.captures(state, content)
            except Exception as error:                   # noqa: BLE001
                return Outcome(step, "failed", f"could not read the result: {error}",
                               result=content, seconds=elapsed)
        return Outcome(step, "ok", result=content, seconds=elapsed)


def coverage(server: Any, report: Report) -> tuple[set[str], set[str], dict[str, str]]:
    """(exercised, untouched, excused) — measured against the registry, not a list."""
    registered = {tool.name for tool in asyncio.run(server.list_tools())}
    exercised = report.tools_exercised() & registered
    untouched = registered - exercised - set(NOT_EXERCISED)
    excused = {name: why for name, why in NOT_EXERCISED.items() if name in registered}
    return exercised, untouched, excused


def render(server: Any, report: Report) -> str:
    """The summary a person reads, and the body of a feedback issue."""
    exercised, untouched, excused = coverage(server, report)
    registered = len(asyncio.run(server.list_tools()))
    counted = len(exercised) + len(excused)

    lines = [
        "## What ran",
        "",
        f"{report.ok} steps ok, {len(report.skipped)} skipped, {len(report.failed)} failed.",
        f"Tools exercised: {len(exercised)} of {registered} "
        f"({counted}/{registered} counting the ones that cannot be automated).",
        "",
    ]

    by_group: dict[str, list[Outcome]] = {}
    for outcome in report.outcomes:
        by_group.setdefault(outcome.step.group or "other", []).append(outcome)
    mark = {"ok": "ok  ", "skipped": "skip", "failed": "FAIL"}
    for group, outcomes in by_group.items():
        lines.append(f"### {group}")
        lines.append("")
        lines.append("```")
        for outcome in outcomes:
            detail = f"  - {outcome.detail}" if outcome.detail else ""
            lines.append(f"{mark[outcome.status]}  {outcome.step.tool:24}"
                         f"{outcome.step.narrate}{detail}")
        lines.append("```")
        lines.append("")

    if untouched:
        lines += ["### Not exercised", "",
                  "These are registered and the demonstration never called them, which is a "
                  "gap in the demonstration rather than in the server:", "",
                  *(f"- `{name}`" for name in sorted(untouched)), ""]
    if excused:
        lines += ["### Cannot be automated", "",
                  *(f"- `{name}` — {why}" for name, why in sorted(excused.items())), ""]
    return "\n".join(lines)


def narrator(echo: Callable[[str], None], *, teach: bool) -> Callable[[str, Any], None]:
    """Prints each step as it happens. `teach` adds the why."""
    def on_event(kind: str, payload: Any) -> None:
        if kind != "step":
            return
        outcome: Outcome = payload
        symbol = {"ok": "  ok  ", "skipped": " skip ", "failed": " FAIL "}[outcome.status]
        echo(f"{symbol} {outcome.step.narrate}")
        if outcome.detail:
            echo(f"        {outcome.detail}")
        if teach and outcome.step.teaches and outcome.status == "ok":
            for line in _wrap(outcome.step.teaches, 76):
                echo(f"        {line}")
            echo("")
    return on_event


def _wrap(text: str, width: int) -> Iterable[str]:
    import textwrap
    return textwrap.wrap(text, width=width)
