"""`demonstration_plan` — how to show somebody what this server does.

Asked "do you have a demo or end-to-end tests to run?", a model connected to this server used
to answer *no*. It was right: the demonstration was a CLI command, invisible from inside a
session, which is the one place people actually ask.

**It returns the plan rather than running it**, and that is the design rather than a shortcut.
A tool that ran seventy-five steps would block a conversation for minutes behind a single call,
and the model would have demonstrated nothing — the tool would have done the work. Handing back
an ordered plan makes the *model* call the real tools, in order, narrating as it goes. That is
a better demonstration, because it is a conversation, and a better test, because it exercises
the thing no unit test can: whether the tool descriptions are good enough for somebody to use
them correctly from a standing start.

It also reports what the CURRENT policy will not allow, because the alternative is a
demonstration that walks somebody into a refusal it could have predicted. There is no default
profile — an unconfigured install permits everything — but a `commenter` install cannot trash
anything, which means it cannot clear up after itself; better said at the start than discovered
as litter in somebody's Drive.
"""
from __future__ import annotations

from mcp.server import MCPServer

from ...demo import build
from ...policy import Policy
from .._config import Settings
from .._schemas import DemonstrationOut, DemonstrationStepOut
from ._base import READ

UNATTENDED = "csa-google-workspace-mcp demo --auto"
NARRATED = "csa-google-workspace-mcp demo"


def register_demo_tools(app: MCPServer, settings: Settings) -> None:

    @app.tool(annotations=READ)
    def demonstration_plan() -> DemonstrationOut:
        """An ordered plan for demonstrating everything this server can do, on real files.

        Use this when somebody asks for a demo, a walkthrough, an end-to-end test, or "show me
        what you can do with my Drive". Returns the steps; YOU carry them out by calling the
        tools named, in order, explaining each one as you go. Work out the arguments yourself
        from each tool's own description - that is part of what the exercise proves.

        It creates REAL files in the user's Drive. Say so before starting, and check they want
        that. `unavailable` lists the steps the current policy will refuse, so you can say up
        front what will be skipped rather than hitting it later - if `cleanup_possible` is
        false, tell them they will have to delete the files by hand, before you create any.

        For an unattended run that also clears up, the command-line version does the whole
        thing without a conversation.
        """
        policy = settings.policy or Policy.default()
        enabled = set(policy.enabled)

        steps: list[DemonstrationStepOut] = []
        unavailable: list[str] = []
        for number, step in enumerate(build("demo", "demo folder", "", keep=True), start=1):
            blocked = bool(step.requires) and step.requires not in enabled
            if blocked and step.requires is not None:
                reason = f"{step.tool} needs the {step.requires} capability, which is off"
                if reason not in unavailable:
                    unavailable.append(reason)
            steps.append({"step": number, "tool": step.tool, "do": step.narrate,
                          "why": step.teaches or None, "available": not blocked,
                          "applies_to": step.group or "account"})

        # Said explicitly, because the plan handed to a model has no cleanup steps in it -
        # it is built with keep=True - so the one refusal that changes what you say BEFORE
        # starting would otherwise be the only one with no reason attached.
        if "file.trash" not in enabled:
            unavailable.append(
                "trash_file needs the file.trash capability, which is off - so nothing here "
                "can clear up after itself, and the user will have to delete the files by "
                "hand. Tell them that before creating anything.")

        return {
            "steps": steps,
            "unavailable": unavailable,
            # Separated from `unavailable` because it is the one that changes what you say
            # BEFORE starting rather than what you skip during.
            "cleanup_possible": "file.trash" in enabled,
            "creates_real_files": True,
            "unattended_command": UNATTENDED,
            "narrated_command": NARRATED,
            "advice": (
                "Tell them these are real files in their own Drive, and that you will list "
                "them at the end. Work through the steps in order - the later ones need ids "
                "from the earlier ones. If cleanup_possible is false, say so before creating "
                "anything, or suggest the command-line version, which can clear up."),
        }
