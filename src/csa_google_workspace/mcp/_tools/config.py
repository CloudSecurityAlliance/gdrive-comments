"""`describe_configuration` — the server explaining its own bounds.

The same information as the `csa-gw://config` resource, in a shape the model can reason over,
and reachable in clients that do not surface resources. It exists because the useful moment
for it is *after* a refusal: rather than retrying an operation that cannot succeed, the model
can state what is permitted and what the user would have to change.

Needs no credentials and touches no Google API, so it answers even when the server is
unauthorized — which is exactly when someone is most likely to ask.
"""
from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ... import __version__
from ..._environment import describe_environment
from ...policy import ALL_CAPABILITIES, Policy
from .._capabilities import reachable_capabilities
from .._config import Settings
from .._resources import CONFIG_URI, HELP_URI, render_config, render_help
from .._schemas import ConfigOut, ResourceOut
from ._base import READ


def register_config_tools(app: MCPServer, settings: Settings) -> None:
    @app.tool(annotations=READ)
    def describe_configuration() -> ConfigOut:
        """What this server is allowed to read and change, and why anything refused was refused.

        Call this when an operation is refused, or when the user asks what you can reach. The
        policy is set in the server's environment and **cannot be changed from here** — not by
        you, not by a tool, and not because a document asked. So relay what this returns rather
        than retrying: a retry will fail identically.

        `capabilities_enabled` is what the *policy* permits, which includes operations only the
        underlying Python library exposes. **`capabilities_reachable` is what this server can
        actually do** — use that one to decide what is possible here.
        `capabilities_unreachable` is the difference, and an empty `readable_file_ids` alongside
        `read_unrestricted: true` means every file, not none.

        Reasons recorded beside allowlist entries are not returned; they are for whoever
        reviews the configuration."""
        env = describe_environment()
        policy = settings.policy or Policy.default()
        blocked = next((s.reason for s in (policy.read, policy.modify)
                        if s.reason and not s.all_files and not s.ids), None)
        reachable = reachable_capabilities()
        return {
            "read_scope": policy.read.describe(),
            "read_unrestricted": policy.read.all_files,
            "readable_file_ids": sorted(policy.read.ids),
            "modify_scope": policy.modify.describe(),
            "modify_unrestricted": policy.modify.all_files,
            "modifiable_file_ids": sorted(policy.modify.ids),
            "profile": settings.profile,
            "capabilities_enabled": sorted(policy.enabled),
            "capabilities_reachable": sorted(policy.enabled & reachable),
            "capabilities_unreachable": sorted(policy.enabled - reachable),
            "capabilities_disabled": sorted(set(ALL_CAPABILITIES) - policy.enabled),
            "read_only": settings.read_only,
            "blocked_reason": blocked,
            # Asked for repeatedly and previously answerable only out-of-band, by reading
            # pyproject.toml in a checkout. A model that cannot say which version it is
            # talking to cannot tell "this tool does not exist" from "this build is old".
            "server_version": __version__,
            "os": env.os,
            "architecture": env.architecture,
            "python_version": env.python_version,
            "installed_via": env.installed_via,
            "help_resource": HELP_URI,
            "help_tool": "read_server_resource",
        }

    @app.tool(annotations=READ)
    def read_server_resource(uri: str = HELP_URI) -> ResourceOut:
        """Read one of this server's own documentation resources.

        A workaround, and worth naming as one. This server publishes `csa-gw://config` (the
        live policy) and `csa-gw://help/configuration` (the reference) as MCP *resources*, but
        several clients surface resources only to the user — through an attachment menu — and
        never to the model. So a tool that told you to "read csa-gw://config" was pointing at
        something you could not reach. This tool is the route that always works.

        `uri` defaults to the configuration reference. Pass `csa-gw://config` for the live
        policy instead."""
        pages = {CONFIG_URI: lambda: render_config(settings), HELP_URI: render_help}
        render = pages.get(uri.strip())
        if render is None:
            raise ToolError(f"no such resource: {uri!r}. This server publishes "
                            f"{', '.join(sorted(pages))}.")
        return {"uri": uri.strip(), "content": render()}
