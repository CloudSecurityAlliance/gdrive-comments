"""Built-in MCP server — a delivery layer over the library (phase 2).

Adds no document logic; it maps MCP tools/resources/prompts onto the existing
`Workspace` API. Importing this package does not import the `mcp` SDK; only
`server` and `__main__` do, so the optional `[mcp]` extra stays optional.
"""
from ._config import Settings, WorkspaceProvider, settings_from_env

__all__ = ["Settings", "WorkspaceProvider", "settings_from_env", "main"]


def main() -> None:
    """Console-script entry point. Imported lazily so `[mcp]` stays optional."""
    import sys

    from .cli import main as _main
    sys.exit(_main())
